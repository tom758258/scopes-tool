"""Finite segmented-memory waveform capture and host-side export."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import time

from .batch import (
    batch_iso_timestamp,
    capture_batch_scpi_logging,
    default_batch_output_dir,
    idn_manifest_dict,
    relative_manifest_path,
    write_batch_manifest,
)
from .capabilities import ScopeCapabilities
from .channel import validate_analog_channel
from .errors import OscilloscopeError, ParameterValidationError
from .operations import OperationResult
from .output_files import write_capture_csv_file
from .scope import Oscilloscope
from .segmented import (
    SegmentedMemoryController,
    ensure_segmented_memory_supported,
    segmented_count_command,
    segmented_index_command,
    segmented_mode_command,
    segmented_mode_query,
    segmented_time_tag_query,
    segmented_waveform_all_command,
    segmented_waveform_count_query,
    segmented_waveform_all_supported,
    validate_segmented_count,
)
from .waveform import (
    SUPPORTED_WAVEFORM_POINTS,
    validate_word_format_supported,
    validate_waveform_points,
    waveform_byte_order_command,
    waveform_data_query,
    waveform_format_byte_command,
    waveform_format_word_command,
    waveform_preamble_query,
    waveform_points_command,
    waveform_source_command,
    waveform_unsigned_command,
)


SEGMENTED_CAPTURE_DEFAULT_BASE_DIR = Path("data") / "segmented_captures"


@dataclass(frozen=True)
class SegmentedCaptureRequest:
    """Validated inputs for one finite segmented-memory capture run."""

    channel: int
    segments: int
    points: int = 1000
    waveform_format: str = "byte"
    timeout_ms: int = 30000
    poll_interval_ms: int = 100
    output_dir: str | Path | None = None
    log_scpi: bool = False


class SegmentedCaptureTimeout(OscilloscopeError):
    """Raised internally when finite segmented acquisition does not complete."""


def validate_segmented_capture_request(
    request: SegmentedCaptureRequest,
    capabilities: ScopeCapabilities | None = None,
) -> None:
    """Validate static inputs and, when available, model capabilities."""

    for name in ("channel", "segments", "points", "timeout_ms", "poll_interval_ms"):
        value = getattr(request, name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ParameterValidationError(f"segmented capture {name} must be an integer.")

    if request.channel < 1:
        raise ParameterValidationError("segmented capture channel must be at least 1.")
    if request.segments < 2 and capabilities is None:
        raise ParameterValidationError(
            "segmented memory count must be between 2 and the profile maximum."
        )
    if request.timeout_ms < 1:
        raise ParameterValidationError("segmented capture timeout must be a positive integer.")
    if request.poll_interval_ms < 1:
        raise ParameterValidationError(
            "segmented capture poll interval must be a positive integer."
        )

    if not isinstance(request.waveform_format, str):
        raise ParameterValidationError("segmented capture format must be byte or word.")
    waveform_format = request.waveform_format.lower()
    if waveform_format not in {"byte", "word"}:
        raise ParameterValidationError("segmented capture format must be byte or word.")

    if capabilities is None:
        if request.points not in SUPPORTED_WAVEFORM_POINTS:
            supported = ", ".join(str(value) for value in SUPPORTED_WAVEFORM_POINTS)
            raise ParameterValidationError(
                f"waveform capture supports only these point counts: {supported}."
            )
        return

    ensure_segmented_memory_supported(capabilities)
    validate_analog_channel(request.channel, capabilities)
    validate_segmented_count(request.segments, capabilities)
    validate_waveform_points(request.points, capabilities)
    if waveform_format == "word":
        validate_word_format_supported(capabilities)


def validate_segmented_capture_output_path(output_dir: str | Path | None) -> None:
    """Validate an explicit output directory without creating it."""

    if output_dir is None:
        return
    path = Path(output_dir)
    if not path.exists():
        return
    if not path.is_dir():
        raise OscilloscopeError(f"output directory path is not a directory: {path}")
    try:
        has_contents = any(path.iterdir())
    except OSError as exc:
        raise OscilloscopeError(f"could not inspect output directory: {path}") from exc
    if has_contents:
        raise OscilloscopeError(f"output directory must be empty: {path}")


def segmented_capture_output_path(output_dir: str | Path | None) -> Path:
    """Resolve an output path without creating files or directories."""

    if output_dir is not None:
        return Path(output_dir)
    return default_batch_output_dir(base_dir=SEGMENTED_CAPTURE_DEFAULT_BASE_DIR)


def _prepare_output_dir(output_dir: str | Path | None) -> Path:
    if output_dir is None:
        path = default_batch_output_dir(base_dir=SEGMENTED_CAPTURE_DEFAULT_BASE_DIR)
        try:
            path.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise OscilloscopeError(
                f"could not create output directory {path}: {exc.strerror or exc}"
            ) from exc
        return path

    validate_segmented_capture_output_path(output_dir)
    path = Path(output_dir)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OscilloscopeError(
            f"could not create output directory {path}: {exc.strerror or exc}"
        ) from exc
    return path


def _waveform_capture_commands(channel: int, points: int, waveform_format: str) -> list[str]:
    commands = [waveform_source_command(channel)]
    if waveform_format == "word":
        commands.extend(
            [
                waveform_format_word_command(),
                waveform_byte_order_command("MSBFirst"),
                waveform_unsigned_command(True),
            ]
        )
    else:
        commands.append(waveform_format_byte_command())
    commands.extend(
        [waveform_points_command(points), waveform_preamble_query(), waveform_data_query()]
    )
    return commands


def plan_segmented_capture(
    request: SegmentedCaptureRequest,
    capabilities: ScopeCapabilities,
    *,
    firmware: str | None = None,
) -> tuple[list[str], list[dict[str, str]], dict[str, object]]:
    """Return concrete dry-run SCPI and artifact metadata."""

    validate_segmented_capture_request(request, capabilities)
    validate_segmented_capture_output_path(request.output_dir)
    output_dir = segmented_capture_output_path(request.output_dir)
    waveform_format = request.waveform_format.upper()
    width = max(4, len(str(request.segments)))
    files = [
        {"kind": "manifest", "path": str(output_dir / "manifest.json")},
        {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
    ]
    planned = [
        "*IDN?",
        segmented_mode_query(),
        ":ACQuire:TYPE?",
        segmented_mode_command("segmented"),
        segmented_count_command(request.segments),
        ":SINGle",
        segmented_waveform_count_query(),
    ]
    if segmented_waveform_all_supported(capabilities, firmware):
        planned.append(segmented_waveform_all_command(False))
    for index in range(1, request.segments + 1):
        planned.extend(
            [segmented_index_command(index), segmented_time_tag_query()]
        )
        planned.extend(_waveform_capture_commands(request.channel, request.points, request.waveform_format))
        files.append(
            {
                "kind": "csv",
                "path": str(output_dir / f"segment_{index:0{width}d}.csv"),
            }
        )
    planned.extend([segmented_mode_query(), ":SYSTem:ERRor?"])
    result = {
        "operation": "segmented-capture",
        "status": "planned",
        "output_dir": str(output_dir),
        "manifest_path": str(output_dir / "manifest.json"),
        "scpi_log_path": str(output_dir / "scpi.log"),
        "channel": request.channel,
        "requested_segments": request.segments,
        "configured_segments": request.segments,
        "acquired_segments": None,
        "exported_segments": 0,
        "points": request.points,
        "format": waveform_format,
        "initial_mode": None,
        "final_mode": None,
        "polling": {
            "command": segmented_waveform_count_query(),
            "timeout_ms": request.timeout_ms,
            "poll_interval_ms": request.poll_interval_ms,
            "runtime_behavior": "repeat until requested count is acquired or timeout",
        },
    }
    return planned, files, result


def _system_error_json(entry) -> dict[str, object]:
    return {
        "code": entry.code,
        "message": entry.message,
        "raw": entry.raw,
        "is_error": entry.is_error,
    }


def _backend_json(scope: Oscilloscope) -> dict[str, object]:
    return {
        "backend": getattr(scope.backend, "backend", None),
        "timeout_ms": getattr(scope.backend, "timeout", None),
    }


def _write_manifest(manifest: dict[str, object], path: Path) -> None:
    write_batch_manifest(manifest, path)


def _best_effort_final_state(
    scope: Oscilloscope,
    controller: SegmentedMemoryController,
) -> tuple[str | None, dict[str, object] | None]:
    final_mode: str | None = None
    system_error: dict[str, object] | None = None
    try:
        final_mode = controller.query_mode()
    except Exception:
        pass
    try:
        system_error = _system_error_json(scope.query_system_error())
    except Exception:
        pass
    return final_mode, system_error


def _error_text(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


def _is_visa_timeout(exc: Exception) -> bool:
    """Return whether an exception chain contains a VISA read timeout."""

    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if getattr(current, "error_code", None) in {
            -1073807339,
            "-1073807339",
        }:
            return True
        if "VI_ERROR_TMO" in str(current):
            return True
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return False


def run_segmented_capture(
    scope: Oscilloscope,
    resource: str,
    request: SegmentedCaptureRequest,
) -> OperationResult:
    """Run finite segmented acquisition and stream one CSV per segment."""

    validate_segmented_capture_request(request)
    output_dir = _prepare_output_dir(request.output_dir)
    manifest_path = output_dir / "manifest.json"
    scpi_log_path = output_dir / "scpi.log"
    waveform_format = request.waveform_format.upper()
    width = max(4, len(str(request.segments)))
    start_time = batch_iso_timestamp()
    manifest: dict[str, object] = {
        "schema_version": 1,
        "operation": "segmented-capture",
        "start_time": start_time,
        "end_time": None,
        "status": "running",
        "resource": resource,
        "backend": getattr(scope.backend, "backend", None),
        "timeout_ms": request.timeout_ms,
        "idn": None,
        "channel": request.channel,
        "requested_segments": request.segments,
        "configured_segments": None,
        "acquired_segments": 0,
        "exported_segments": 0,
        "points": request.points,
        "format": waveform_format,
        "poll_interval_ms": request.poll_interval_ms,
        "initial_mode": None,
        "final_mode": None,
        "segments": [],
        "system_error": None,
        "error": None,
    }
    files = [
        {"kind": "manifest", "path": str(manifest_path)},
        {"kind": "scpi_log", "path": str(scpi_log_path)},
    ]
    idn = None
    system_error: dict[str, object] | None = None
    final_mode: str | None = None
    primary_error: Exception | None = None
    target_started = False
    acquired_segments = 0
    exported_segments = 0
    session_query_timed_out = False
    human = [f"Resource: {resource}"]
    controller: SegmentedMemoryController | None = None

    try:
        with capture_batch_scpi_logging(
            scpi_log_path,
            echo_to_stderr=request.log_scpi,
        ):
            try:
                _write_manifest(manifest, manifest_path)
                idn = scope.query_idn()
                manifest["idn"] = idn_manifest_dict(idn)
                capabilities = scope.capabilities
                validate_segmented_capture_request(request, capabilities)
                assert capabilities is not None
                controller = SegmentedMemoryController(scope.scpi, capabilities)

                manifest["initial_mode"] = controller.query_mode()
                target_started = True
                controller.enable(request.segments)
                manifest["configured_segments"] = request.segments
                scope.single()

                deadline = time.monotonic() + request.timeout_ms / 1000.0
                timed_out = False
                original_timeout = scope.scpi.timeout
                polling_exception: Exception | None = None
                try:
                    while True:
                        remaining_seconds = deadline - time.monotonic()
                        if remaining_seconds <= 0:
                            timed_out = True
                            break

                        remaining_ms = max(1, math.ceil(remaining_seconds * 1000))
                        scope.scpi.set_timeout(remaining_ms)
                        try:
                            acquired_segments = controller.query_acquired_count()
                        except Exception as exc:
                            if _is_visa_timeout(exc):
                                session_query_timed_out = True
                                raise SegmentedCaptureTimeout(
                                    "segmented capture polling read timed out after "
                                    f"{request.timeout_ms} ms with {acquired_segments} of "
                                    f"{request.segments} segments acquired."
                                ) from exc
                            raise

                        manifest["acquired_segments"] = acquired_segments
                        if acquired_segments >= request.segments:
                            break
                        time.sleep(request.poll_interval_ms / 1000.0)
                except Exception as exc:
                    polling_exception = exc
                    raise
                finally:
                    try:
                        scope.scpi.set_timeout(original_timeout)
                    except Exception:
                        if polling_exception is None:
                            raise

                if timed_out:
                    primary_error = SegmentedCaptureTimeout(
                        "segmented capture timed out after "
                        f"{request.timeout_ms} ms with {acquired_segments} of "
                        f"{request.segments} segments acquired."
                    )

                export_count = min(acquired_segments, request.segments)
                if export_count and segmented_waveform_all_supported(
                    capabilities, idn.firmware
                ):
                    controller.set_waveform_all(False)
                for index in range(1, export_count + 1):
                    scope.select_segmented_memory(index)
                    time_tag_s = scope.query_segmented_time_tag()
                    if waveform_format == "WORD":
                        capture = scope.capture_waveform_word(
                            request.channel, points=request.points
                        )
                    else:
                        capture = scope.capture_waveform_byte(
                            request.channel, points=request.points
                        )
                    csv_path = output_dir / f"segment_{index:0{width}d}.csv"
                    written_csv = write_capture_csv_file(capture, csv_path)
                    files.append({"kind": "csv", "path": str(written_csv)})
                    csv_name = relative_manifest_path(written_csv, output_dir)
                    segment_entry = {
                        "index": index,
                        "time_tag_s": time_tag_s,
                        "actual_points": len(capture.raw_samples),
                        "csv": csv_name,
                    }
                    segments = manifest["segments"]
                    assert isinstance(segments, list)
                    segments.append(segment_entry)
                    exported_segments += 1
                    manifest["exported_segments"] = exported_segments
                    _write_manifest(manifest, manifest_path)

                final_mode, system_error = _best_effort_final_state(scope, controller)
                manifest["final_mode"] = final_mode
                manifest["system_error"] = system_error
                if primary_error is None and final_mode != "segmented":
                    primary_error = OscilloscopeError(
                        "segmented capture did not remain in segmented mode."
                    )
                if primary_error is None and (
                    system_error is None or system_error["is_error"]
                ):
                    primary_error = OscilloscopeError(
                        "segmented capture finished with an instrument system error."
                    )
            except Exception as exc:
                primary_error = primary_error or exc
                if controller is not None and target_started and not session_query_timed_out:
                    is_average_rejection = (
                        isinstance(exc, ParameterValidationError)
                        and "cannot be enabled while acquisition type is average" in str(exc)
                    )
                    if not is_average_rejection:
                        final_mode, system_error = _best_effort_final_state(scope, controller)
                        manifest["final_mode"] = final_mode
                        manifest["system_error"] = system_error

            if primary_error is None:
                status = "completed"
            elif exported_segments:
                status = "partial"
            else:
                status = "failed"
            error_text = None if primary_error is None else _error_text(primary_error)
            manifest["status"] = status
            manifest["end_time"] = batch_iso_timestamp()
            manifest["acquired_segments"] = acquired_segments
            manifest["exported_segments"] = exported_segments
            manifest["error"] = error_text
            _write_manifest(manifest, manifest_path)
    except Exception as exc:
        primary_error = primary_error or exc
        manifest["status"] = "partial" if exported_segments else "failed"
        manifest["end_time"] = batch_iso_timestamp()
        manifest["acquired_segments"] = acquired_segments
        manifest["exported_segments"] = exported_segments
        manifest["error"] = _error_text(primary_error)
        try:
            _write_manifest(manifest, manifest_path)
        except Exception:
            pass

    if idn is not None:
        human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])
    human.extend(
        [
            f"Output directory: {output_dir}",
            f"Manifest: {manifest_path}",
            f"SCPI log: {scpi_log_path}",
            f"Exported segments: {exported_segments}/{request.segments}",
        ]
    )
    result = {
        "operation": "segmented-capture",
        "status": manifest["status"],
        "output_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "scpi_log_path": str(scpi_log_path),
        "channel": request.channel,
        "requested_segments": request.segments,
        "configured_segments": manifest["configured_segments"],
        "acquired_segments": acquired_segments,
        "exported_segments": exported_segments,
        "points": request.points,
        "format": waveform_format,
        "initial_mode": manifest["initial_mode"],
        "final_mode": final_mode,
        "error": manifest["error"],
        "polling": {
            "command": segmented_waveform_count_query(),
            "timeout_ms": request.timeout_ms,
            "poll_interval_ms": request.poll_interval_ms,
        },
    }
    if system_error is not None:
        human.append(f"System error: {system_error['raw']}")
    if primary_error is not None:
        human.append(f"Error: {_error_text(primary_error)}")
    return OperationResult(
        0 if primary_error is None else 1,
        result,
        files,
        system_error,
        human,
        idn=idn,
        **_backend_json(scope),
    )
