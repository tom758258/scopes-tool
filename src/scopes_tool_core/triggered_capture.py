"""Finite triggered waveform capture series workflow."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Callable, Mapping, Sequence

from .batch import (
    batch_capture_paths,
    batch_iso_timestamp,
    capture_actual_points,
    idn_manifest_dict,
    prepare_batch_output_dir,
    relative_manifest_path,
    system_error_manifest_dict,
    write_batch_manifest,
)
from .capabilities import ScopeCapabilities
from .errors import OscilloscopeError, ParameterValidationError
from .operations import (
    OperationResult,
    _capture_waveform,
    _trigger_wait_classifier_profile,
)
from .output_files import write_capture_csv_file, write_capture_metadata_file
from .planning import OperationPlan, planned_waveform_scpi, resolve_capture_channels
from .scope import Oscilloscope
from .trigger import (
    operation_condition_query,
    single_command,
    wait_for_current_trigger_completion,
)
from .triggered_measurement import _trigger_failure, _trigger_wait_config
from .waveform import validate_waveform_points, validate_word_format_supported
from .workflow import (
    ProgressReporter,
    StopRequested,
    WorkflowProgress,
    interruptible_wait,
    workflow_scpi_logging,
)


TRIGGERED_CAPTURE_SERIES_SCHEMA_VERSION = 1
TRIGGERED_CAPTURE_SERIES_DEFAULT_BASE_DIR = (
    Path("data") / "triggered_capture_series"
)

SampleReporter = Callable[[Mapping[str, object]], None]


@dataclass(frozen=True)
class TriggeredCaptureSeriesRequest:
    """Inputs for one finite triggered waveform capture series."""

    channels: Sequence[int | str]
    count: int
    trigger_timeout_seconds: float
    points: int = 1000
    waveform_format: str = "byte"
    interval_seconds: float = 0.0
    output_dir: str | Path | None = None
    log_scpi: bool = False


def plan_triggered_capture_series(
    request: TriggeredCaptureSeriesRequest,
    capabilities: ScopeCapabilities,
) -> OperationPlan:
    """Validate and plan one representative cycle without hardware or files."""

    normalized = _normalize_request(request, capabilities)
    output_dir = (
        Path(request.output_dir)
        if request.output_dir is not None
        else TRIGGERED_CAPTURE_SERIES_DEFAULT_BASE_DIR / "DRY-RUN"
    )
    files = _planned_files(output_dir, request.count)
    planned = [single_command(), operation_condition_query()]
    planned.extend(
        planned_waveform_scpi(
            normalized["channels"],
            normalized["waveform_format"],
            normalized["points"],
        )
    )
    planned.append(":SYSTem:ERRor?")
    result = {
        "status": "planned",
        "channels": list(normalized["channels"]),
        "points": normalized["points"],
        "format": str(normalized["waveform_format"]).upper(),
        "requested_count": request.count,
        "completed_count": 0,
        "trigger_timeout_seconds": float(request.trigger_timeout_seconds),
        "interval_seconds": float(request.interval_seconds),
        "cycles": [],
        "output_dir": str(output_dir),
        "manifest_path": str(output_dir / "manifest.json"),
        "scpi_log_path": str(output_dir / "scpi.log"),
        "error": None,
    }
    return OperationPlan(tuple(planned), tuple(files), result)


def run_triggered_capture_series(
    scope: Oscilloscope,
    resource: str,
    request: TriggeredCaptureSeriesRequest,
    *,
    stop_requested: StopRequested | None = None,
    progress_reporter: ProgressReporter | None = None,
    sample_reporter: SampleReporter | None = None,
) -> OperationResult:
    """Run a finite Single, trigger-wait, and waveform capture series."""

    _validate_request_fields(request)
    if _stop_requested(stop_requested):
        return _pre_start_cancelled_result(request)

    idn = scope.query_idn()
    if scope.capabilities is None:
        raise OscilloscopeError("Capabilities unavailable for this model")
    normalized = _normalize_request(request, scope.capabilities)
    channels = normalized["channels"]
    points = normalized["points"]
    waveform_format = normalized["waveform_format"]

    output_dir = prepare_batch_output_dir(
        request.output_dir,
        base_dir=TRIGGERED_CAPTURE_SERIES_DEFAULT_BASE_DIR,
    )
    manifest_path = output_dir / "manifest.json"
    scpi_log_path = output_dir / "scpi.log"
    files = [
        {"kind": "manifest", "path": str(manifest_path)},
        {"kind": "scpi_log", "path": str(scpi_log_path)},
    ]
    manifest: dict[str, object] = {
        "schema_version": TRIGGERED_CAPTURE_SERIES_SCHEMA_VERSION,
        "start_time": batch_iso_timestamp(),
        "end_time": None,
        "status": "running",
        "resource": resource,
        "backend": getattr(scope.backend, "backend", None),
        "timeout_ms": getattr(scope.backend, "timeout", None),
        "idn": idn_manifest_dict(idn),
        "channels": list(channels),
        "points": points,
        "format": str(waveform_format).upper(),
        "requested_count": request.count,
        "completed_count": 0,
        "trigger_timeout_seconds": float(request.trigger_timeout_seconds),
        "interval_seconds": float(request.interval_seconds),
        "cycles": [],
        "files": _relative_files(files, output_dir),
        "error": None,
    }
    human = [
        f"Triggered capture series: {request.count} cycle(s)",
        f"Channels: {', '.join(f'CH{channel}' for channel in channels)}",
        f"Points: {points}",
        f"Format: {str(waveform_format).upper()}",
        f"Trigger timeout seconds: {float(request.trigger_timeout_seconds):.12g}",
        f"Interval seconds: {float(request.interval_seconds):.12g}",
        f"Output directory: {output_dir}",
    ]
    last_system_error: dict[str, object] | None = None
    current_cycle = 0
    reporter_failed = False

    try:
        _write_manifest(manifest, manifest_path)
        with workflow_scpi_logging(
            scpi_log_path,
            echo_to_stderr=request.log_scpi,
        ):
            start_perf = time.perf_counter()
            for index in range(1, request.count + 1):
                current_cycle = index
                if _stop_requested(stop_requested):
                    return _finish_result(
                        "cancelled", 130, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope, error=None,
                    )

                scope.single()
                trigger = wait_for_current_trigger_completion(
                    scope.scpi,
                    _trigger_wait_config(request.trigger_timeout_seconds),
                    classifier_profile=_trigger_wait_classifier_profile(scope),
                    stop_requested=stop_requested,
                )
                if trigger.outcome == "cancelled":
                    return _finish_result(
                        "cancelled", 130, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope, error=None,
                    )
                if trigger.outcome != "natural":
                    error = _trigger_failure(
                        index,
                        trigger.outcome,
                        trigger.elapsed_ms,
                        trigger.error,
                    )
                    return _finish_result(
                        "error", 1, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope, error=error,
                    )
                if _stop_requested(stop_requested):
                    return _finish_result(
                        "cancelled", 130, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope, error=None,
                    )

                capture = _capture_waveform(
                    scope,
                    channels,
                    waveform_format,
                    points,
                )
                csv_path, metadata_path = batch_capture_paths(
                    output_dir,
                    index,
                    request.count,
                )
                written_csv = write_capture_csv_file(capture, csv_path)
                files.append({"kind": "csv", "path": str(written_csv)})
                written_metadata = write_capture_metadata_file(
                    capture,
                    metadata_path,
                    idn=idn,
                    resource=resource,
                )
                files.append({"kind": "metadata", "path": str(written_metadata)})

                entry = scope.query_system_error()
                last_system_error = system_error_manifest_dict(entry)
                if entry.is_error:
                    error = {
                        "type": "instrument_error",
                        "cycle_index": index,
                        "message": entry.format(),
                    }
                    return _finish_result(
                        "instrument_error", 1, manifest, manifest_path,
                        scpi_log_path, files, human, idn, last_system_error,
                        scope, error=error,
                    )

                timestamp_iso = batch_iso_timestamp()
                elapsed_seconds = time.perf_counter() - start_perf
                cycle = {
                    "index": index,
                    "timestamp_iso": timestamp_iso,
                    "elapsed_seconds": elapsed_seconds,
                    "trigger_elapsed_seconds": trigger.elapsed_ms / 1000.0,
                    "csv": relative_manifest_path(written_csv, output_dir),
                    "metadata": relative_manifest_path(written_metadata, output_dir),
                    "actual_points": capture_actual_points(capture),
                    "system_error": dict(last_system_error),
                }
                candidate = copy.deepcopy(manifest)
                candidate["completed_count"] = index
                candidate_cycles = candidate["cycles"]
                assert isinstance(candidate_cycles, list)
                candidate_cycles.append(cycle)
                candidate["files"] = _relative_files(files, output_dir)
                _write_manifest(candidate, manifest_path)
                manifest = candidate

                human.extend(
                    [
                        f"Cycle {index}/{request.count}:",
                        f"CSV: {written_csv}",
                        f"Metadata: {written_metadata}",
                        f"System error: {entry.format()}",
                    ]
                )
                try:
                    if sample_reporter is not None:
                        sample_reporter(dict(cycle))
                    if progress_reporter is not None:
                        progress_reporter(
                            WorkflowProgress(
                                completed_count=index,
                                total_count=request.count,
                                elapsed_seconds=time.perf_counter() - start_perf,
                            )
                        )
                except Exception:
                    reporter_failed = True
                    raise

                if index >= request.count:
                    return _finish_result(
                        "completed", 0, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope, error=None,
                    )
                if _stop_requested(stop_requested):
                    return _finish_result(
                        "cancelled", 130, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope, error=None,
                    )
                if request.interval_seconds > 0 and not interruptible_wait(
                    request.interval_seconds,
                    stop_requested=stop_requested,
                ):
                    return _finish_result(
                        "cancelled", 130, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope, error=None,
                    )
    except KeyboardInterrupt:
        return _finish_result(
            "interrupted", 130, manifest, manifest_path, scpi_log_path,
            files, human, idn, last_system_error, scope,
            error="KeyboardInterrupt", best_effort=True,
        )
    except (OSError, OscilloscopeError) as exc:
        if reporter_failed:
            raise
        error = {
            "type": type(exc).__name__,
            "cycle_index": current_cycle or None,
            "message": str(exc),
        }
        return _finish_result(
            "error", 1, manifest, manifest_path, scpi_log_path, files,
            human, idn, last_system_error, scope, error=error,
            best_effort=True,
        )

    raise AssertionError("finite triggered capture series exited without a result")


def _validate_request_fields(request: TriggeredCaptureSeriesRequest) -> None:
    if isinstance(request.count, bool) or not isinstance(request.count, int):
        raise ParameterValidationError("triggered capture series count must be an integer")
    if request.count < 1:
        raise ParameterValidationError("triggered capture series count must be at least 1")
    _finite_number(
        request.trigger_timeout_seconds,
        "triggered capture series trigger timeout seconds",
        positive=True,
    )
    _finite_number(
        request.interval_seconds,
        "triggered capture series interval seconds",
        positive=False,
    )
    if isinstance(request.channels, (str, bytes)) or not isinstance(
        request.channels, Sequence
    ):
        raise ParameterValidationError(
            "triggered capture series channels must be a sequence"
        )
    for channel in request.channels:
        if isinstance(channel, bool) or not isinstance(channel, (int, str)):
            raise ParameterValidationError(
                "triggered capture series channels must contain integers or all"
            )
    if not isinstance(request.waveform_format, str) or (
        request.waveform_format.lower() not in {"byte", "word"}
    ):
        raise ParameterValidationError(
            "triggered capture series format must be byte or word"
        )
    if not isinstance(request.log_scpi, bool):
        raise ParameterValidationError(
            "triggered capture series log_scpi must be a boolean"
        )
    if request.output_dir is not None and not isinstance(
        request.output_dir, (str, Path)
    ):
        raise ParameterValidationError(
            "triggered capture series output_dir must be a path or string"
        )


def _finite_number(value: object, label: str, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParameterValidationError(f"{label} must be a finite number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ParameterValidationError(f"{label} must be a finite number")
    if positive and parsed <= 0:
        raise ParameterValidationError(f"{label} must be greater than zero")
    if not positive and parsed < 0:
        raise ParameterValidationError(f"{label} must be non-negative")
    return parsed


def _normalize_request(
    request: TriggeredCaptureSeriesRequest,
    capabilities: ScopeCapabilities,
) -> dict[str, object]:
    _validate_request_fields(request)
    channels = resolve_capture_channels(request.channels, capabilities)
    points = validate_waveform_points(request.points, capabilities)
    waveform_format = request.waveform_format.lower()
    if waveform_format == "word":
        validate_word_format_supported(capabilities)
    return {
        "channels": channels,
        "points": points,
        "waveform_format": waveform_format,
    }


def _planned_files(output_dir: Path, count: int) -> list[dict[str, str]]:
    files = [
        {"kind": "manifest", "path": str(output_dir / "manifest.json")},
        {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
    ]
    for index in range(1, count + 1):
        csv_path, metadata_path = batch_capture_paths(output_dir, index, count)
        files.extend(
            [
                {"kind": "csv", "path": str(csv_path)},
                {"kind": "metadata", "path": str(metadata_path)},
            ]
        )
    return files


def _relative_files(
    files: Sequence[Mapping[str, str]],
    output_dir: Path,
) -> list[dict[str, str]]:
    return [
        {
            "kind": item["kind"],
            "path": relative_manifest_path(item["path"], output_dir),
        }
        for item in files
    ]


def _write_manifest(manifest: Mapping[str, object], path: Path) -> None:
    try:
        write_batch_manifest(manifest, path)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise OscilloscopeError(
            f"could not write triggered capture series manifest {path}: {reason}"
        ) from exc


def _finish_result(
    status: str,
    exit_code: int,
    manifest: dict[str, object],
    manifest_path: Path,
    scpi_log_path: Path,
    files: list[dict[str, str]],
    human: list[str],
    idn: object,
    system_error: dict[str, object] | None,
    scope: Oscilloscope,
    *,
    error: dict[str, object] | str | None,
    best_effort: bool = False,
) -> OperationResult:
    manifest["status"] = status
    manifest["end_time"] = batch_iso_timestamp()
    manifest["files"] = _relative_files(files, manifest_path.parent)
    manifest["error"] = error
    if best_effort:
        try:
            _write_manifest(manifest, manifest_path)
        except OscilloscopeError:
            pass
    else:
        _write_manifest(manifest, manifest_path)
    human.extend(
        [
            f"Triggered capture series status: {status}",
            f"Manifest: {manifest_path}",
            f"SCPI log: {scpi_log_path}",
        ]
    )
    result = {
        "status": status,
        "channels": list(manifest["channels"]),
        "points": manifest["points"],
        "format": manifest["format"],
        "requested_count": manifest["requested_count"],
        "completed_count": manifest["completed_count"],
        "trigger_timeout_seconds": manifest["trigger_timeout_seconds"],
        "interval_seconds": manifest["interval_seconds"],
        "cycles": list(manifest["cycles"]),
        "output_dir": str(manifest_path.parent),
        "manifest_path": str(manifest_path),
        "scpi_log_path": str(scpi_log_path),
        "error": error,
    }
    return OperationResult(
        exit_code,
        result,
        files,
        system_error,
        human,
        idn=idn,
        backend=getattr(scope.backend, "backend", None),
        timeout_ms=getattr(scope.backend, "timeout", None),
    )


def _pre_start_cancelled_result(
    request: TriggeredCaptureSeriesRequest,
) -> OperationResult:
    result = {
        "status": "cancelled",
        "channels": [],
        "points": request.points,
        "format": request.waveform_format.upper(),
        "requested_count": request.count,
        "completed_count": 0,
        "trigger_timeout_seconds": float(request.trigger_timeout_seconds),
        "interval_seconds": float(request.interval_seconds),
        "cycles": [],
        "output_dir": None,
        "manifest_path": None,
        "scpi_log_path": None,
        "error": None,
    }
    return OperationResult(130, result, human_lines=["Triggered capture series cancelled."])


def _stop_requested(callback: StopRequested | None) -> bool:
    return callback is not None and callback()
