"""Finite waveform capture batch operation."""

from __future__ import annotations

from .status import status_fields

from pathlib import Path
import math
import time
from typing import Callable, Mapping

from .batch import (
    BatchManifest,
    batch_capture_paths,
    batch_iso_timestamp,
    capture_actual_points,
    idn_manifest_dict,
    prepare_batch_output_dir,
    relative_manifest_path,
    system_error_manifest_dict,
    write_batch_manifest,
)
from .errors import OscilloscopeError
from .operation_support import (
    _append_session_header,
    _capture_waveform,
    _format_actual_points,
    _format_channel_list,
    _scope_backend_json,
    _waveform_capture_commands,
)
from .operation_types import (
    CaptureBatchRequest,
    OperationResult,
    _OperationError,
)
from .output_files import write_capture_csv_file, write_capture_metadata_file
from .planning import resolve_capture_channels
from .scope import Oscilloscope
from .waveform import validate_waveform_points, validate_word_format_supported
from .workflow import (
    ProgressReporter,
    StopRequested,
    WorkflowProgress,
    drain_preexisting_system_errors,
    interruptible_wait,
    workflow_scpi_logging,
)


def run_capture_batch(
    scope: Oscilloscope,
    resource: str,
    request: CaptureBatchRequest,
    *,
    stop_requested: StopRequested | None = None,
    progress_reporter: ProgressReporter | None = None,
    sample_reporter: Callable[[Mapping[str, object]], None] | None = None,
) -> OperationResult:
    """Run a finite waveform capture batch and write its artifacts."""

    if request.requested_count < 1:
        raise OscilloscopeError("capture-batch count must be at least 1")
    if not math.isfinite(request.interval_seconds) or request.interval_seconds < 0:
        raise OscilloscopeError(
            "capture-batch interval seconds must be a non-negative finite number"
        )

    output_dir = prepare_batch_output_dir(request.output_dir)
    manifest_path = output_dir / "manifest.json"
    scpi_log_path = output_dir / "scpi.log"
    manifest = BatchManifest(
        start_time=batch_iso_timestamp(),
        end_time=None,
        status="running",
        resource=resource,
        backend=None,
        timeout_ms=None,
        idn=None,
        channels=[],
        points=request.points,
        format=request.waveform_format.upper(),
        requested_count=request.requested_count,
        interval_seconds=request.interval_seconds,
    )
    files = [
        {"kind": "manifest", "path": str(manifest_path)},
        {"kind": "scpi_log", "path": str(scpi_log_path)},
    ]
    human: list[str] = []
    idn = None
    last_system_error: dict[str, object] | None = None
    reporter_failed = False

    try:
        with workflow_scpi_logging(
            scpi_log_path,
            echo_to_stderr=request.log_scpi,
        ):
            idn = scope.query_idn()
            manifest.backend = getattr(scope.backend, "backend", None)
            manifest.timeout_ms = getattr(scope.backend, "timeout", None)
            manifest.idn = idn_manifest_dict(idn)
            _append_session_header(human, scope, resource)
            human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])

            if scope.capabilities is None:
                human.append("Capabilities: unavailable for this model")
                manifest.status = "error"
                manifest.error = "Capabilities unavailable for this model"
                manifest.end_time = batch_iso_timestamp()
                _write_batch_manifest(manifest, manifest_path)
                human.extend(
                    [
                        f"Output directory: {output_dir}",
                        f"SCPI log: {scpi_log_path}",
                        f"Manifest: {manifest_path}",
                    ]
                )
                return _capture_batch_operation_result(
                    1,
                    manifest,
                    manifest_path,
                    scpi_log_path,
                    files,
                    human,
                    idn,
                    last_system_error,
                    scope,
                )

            channels = resolve_capture_channels(request.channels, scope.capabilities)
            points = validate_waveform_points(request.points, scope.capabilities)
            waveform_format = request.waveform_format.upper()
            if request.waveform_format.lower() == "word":
                validate_word_format_supported(scope.capabilities)
            for _entry in drain_preexisting_system_errors(scope):
                human.append(f"Pre-operation stale system error drained: {_entry.format()}")
            manifest.channels = list(channels)
            manifest.points = points
            manifest.format = waveform_format
            _write_batch_manifest(manifest, manifest_path)

            human.extend(
                [
                    f"Planned batch capture: {_format_channel_list(channels)}, "
                    f"{points} points, {waveform_format} format, "
                    f"{request.requested_count} captures",
                    f"Interval seconds: {request.interval_seconds}",
                    f"Output directory: {output_dir}",
                    *_waveform_capture_commands(
                        channels,
                        request.waveform_format,
                        points,
                    ),
                ]
            )
            start_perf = time.perf_counter()

            for index in range(1, request.requested_count + 1):
                if stop_requested is not None and stop_requested():
                    return _cancel_capture_batch(
                        manifest,
                        manifest_path,
                        scpi_log_path,
                        files,
                        human,
                        idn,
                        last_system_error,
                        scope,
                    )

                capture = _capture_waveform(
                    scope,
                    channels,
                    request.waveform_format,
                    points,
                )
                csv_path, meta_path = batch_capture_paths(
                    output_dir,
                    index,
                    request.requested_count,
                )
                written_csv = write_capture_csv_file(capture, csv_path)
                written_meta = write_capture_metadata_file(
                    capture,
                    meta_path,
                    idn=idn,
                    resource=resource,
                )
                entry = scope.workflow_status()
                last_system_error = system_error_manifest_dict(entry)
                capture_entry = {
                    "index": index,
                    "csv": relative_manifest_path(written_csv, output_dir),
                    "metadata": relative_manifest_path(written_meta, output_dir),
                    "actual_points": capture_actual_points(capture),
                    **status_fields(dict(last_system_error)),
                }
                manifest.captures.append(capture_entry)
                files.extend(
                    [
                        {"kind": "csv", "path": str(written_csv)},
                        {"kind": "metadata", "path": str(written_meta)},
                    ]
                )
                _write_batch_manifest(manifest, manifest_path)
                human.extend(
                    [
                        f"Capture {index}/{request.requested_count}:",
                        _format_actual_points(capture),
                        f"CSV: {written_csv}",
                        f"Metadata: {written_meta}",
                        f"System error: {entry.format()}",
                    ]
                )

                try:
                    if sample_reporter is not None:
                        sample_reporter(dict(capture_entry))
                    if progress_reporter is not None:
                        progress_reporter(
                            WorkflowProgress(
                                completed_count=index,
                                total_count=request.requested_count,
                                elapsed_seconds=time.perf_counter() - start_perf,
                            )
                        )
                except Exception:
                    reporter_failed = True
                    raise

                if entry.is_error:
                    manifest.status = "instrument_error"
                    manifest.end_time = batch_iso_timestamp()
                    _write_batch_manifest(manifest, manifest_path)
                    human.extend(
                        [
                            f"SCPI log: {scpi_log_path}",
                            f"Manifest: {manifest_path}",
                        ]
                    )
                    return _capture_batch_operation_result(
                        1,
                        manifest,
                        manifest_path,
                        scpi_log_path,
                        files,
                        human,
                        idn,
                        last_system_error,
                        scope,
                    )

                if index >= request.requested_count:
                    break

                if stop_requested is not None and stop_requested():
                    return _cancel_capture_batch(
                        manifest,
                        manifest_path,
                        scpi_log_path,
                        files,
                        human,
                        idn,
                        last_system_error,
                        scope,
                    )
                if (
                    index < request.requested_count
                    and request.interval_seconds > 0
                    and not interruptible_wait(
                        request.interval_seconds,
                        stop_requested=stop_requested,
                    )
                ):
                    return _cancel_capture_batch(
                        manifest,
                        manifest_path,
                        scpi_log_path,
                        files,
                        human,
                        idn,
                        last_system_error,
                        scope,
                    )

            manifest.status = "completed"
            manifest.end_time = batch_iso_timestamp()
            _write_batch_manifest(manifest, manifest_path)
            human.extend(
                [f"SCPI log: {scpi_log_path}", f"Manifest: {manifest_path}"]
            )
            return _capture_batch_operation_result(
                0,
                manifest,
                manifest_path,
                scpi_log_path,
                files,
                human,
                idn,
                last_system_error,
                scope,
            )
    except KeyboardInterrupt:
        manifest.status = "interrupted"
        manifest.end_time = batch_iso_timestamp()
        manifest.error = "KeyboardInterrupt"
        _write_batch_manifest_best_effort(manifest, manifest_path)
        return _capture_batch_operation_result(
            130,
            manifest,
            manifest_path,
            scpi_log_path,
            files,
            human,
            idn,
            last_system_error,
            scope,
        )
    except OscilloscopeError as exc:
        if reporter_failed:
            raise
        if manifest.status == "running":
            manifest.status = "error"
            manifest.end_time = batch_iso_timestamp()
            manifest.error = str(exc)
            _write_batch_manifest_best_effort(manifest, manifest_path)
        raise _OperationError(
            exc,
            _capture_batch_operation_result(
                1,
                manifest,
                manifest_path,
                scpi_log_path,
                files,
                human,
                idn,
                last_system_error,
                scope,
            ),
        ) from exc
    except OSError as exc:
        if reporter_failed:
            raise
        manifest.status = "error"
        manifest.end_time = batch_iso_timestamp()
        manifest.error = str(exc)
        _write_batch_manifest_best_effort(manifest, manifest_path)
        error = OscilloscopeError(f"could not write SCPI log file {scpi_log_path}: {exc}")
        raise _OperationError(
            error,
            _capture_batch_operation_result(
                1,
                manifest,
                manifest_path,
                scpi_log_path,
                files,
                human,
                idn,
                last_system_error,
                scope,
            ),
        ) from exc


def _capture_batch_operation_result(
    exit_code: int,
    manifest: BatchManifest,
    manifest_path: Path,
    scpi_log_path: Path,
    files: list[dict[str, str]],
    human: list[str],
    idn: object | None,
    system_error: dict[str, object] | None,
    scope: Oscilloscope,
) -> OperationResult:
    captures = []
    for entry in manifest.captures:
        item = dict(entry)
        actual_points = item.get("actual_points")
        if isinstance(actual_points, int) and len(manifest.channels) == 1:
            item["actual_points"] = {
                f"CH{manifest.channels[0]}": actual_points,
            }
        captures.append(item)
    result = {
        "status": manifest.status,
        "channels": list(manifest.channels),
        "format": manifest.format,
        "points": manifest.points,
        "requested_count": manifest.requested_count,
        "completed_count": len(manifest.captures),
        "manifest_path": str(manifest_path),
        "scpi_log_path": str(scpi_log_path),
        "captures": captures,
        "error": manifest.error,
    }
    return OperationResult.from_status(
        exit_code,
        result,
        list(files),
        system_error,
        list(human),
        idn=idn,
        **_scope_backend_json(scope),
    )


def _cancel_capture_batch(
    manifest: BatchManifest,
    manifest_path: Path,
    scpi_log_path: Path,
    files: list[dict[str, str]],
    human: list[str],
    idn: object | None,
    system_error: dict[str, object] | None,
    scope: Oscilloscope,
) -> OperationResult:
    manifest.status = "cancelled"
    manifest.error = None
    manifest.end_time = batch_iso_timestamp()
    _write_batch_manifest(manifest, manifest_path)
    human.extend([f"SCPI log: {scpi_log_path}", f"Manifest: {manifest_path}"])
    return _capture_batch_operation_result(
        130,
        manifest,
        manifest_path,
        scpi_log_path,
        files,
        human,
        idn,
        system_error,
        scope,
    )


def _write_batch_manifest_best_effort(
    manifest: BatchManifest,
    manifest_path: Path,
) -> None:
    try:
        write_batch_manifest(manifest, manifest_path)
    except OSError:
        pass


def _write_batch_manifest(
    manifest: BatchManifest,
    manifest_path: Path,
) -> None:
    try:
        write_batch_manifest(manifest, manifest_path)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise OscilloscopeError(
            f"could not write batch manifest JSON file {manifest_path}: {reason}"
        ) from exc
