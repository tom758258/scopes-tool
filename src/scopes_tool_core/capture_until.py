"""Finite waveform capture-until-condition workflow."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Callable, Mapping, Sequence

from .batch import (
    batch_iso_timestamp,
    capture_actual_points,
    idn_manifest_dict,
    prepare_batch_output_dir,
    relative_manifest_path,
    system_error_manifest_dict,
    write_batch_manifest,
)
from .capabilities import ScopeCapabilities
from .channel import validate_analog_channel
from .errors import OscilloscopeError, ParameterValidationError
from .operations import OperationResult, _capture_waveform
from .output_files import write_capture_csv_file, write_capture_metadata_file
from .planning import OperationPlan, planned_waveform_scpi, resolve_capture_channels
from .scope import Oscilloscope
from .waveform import MultiChannelWaveformCapture, WaveformCapture, validate_waveform_points, validate_word_format_supported
from .waveform_analysis import (
    validate_waveform_metric,
    validate_waveform_operator,
    waveform_condition_matches,
    waveform_metric,
)
from .workflow import (
    ProgressReporter,
    StopRequested,
    WorkflowProgress,
    drain_preexisting_system_errors,
    interruptible_wait,
    workflow_scpi_logging,
)


CAPTURE_UNTIL_SCHEMA_VERSION = 1
CAPTURE_UNTIL_DEFAULT_BASE_DIR = Path("data") / "capture_until"
SampleReporter = Callable[[Mapping[str, object]], None]


@dataclass(frozen=True)
class CaptureUntilRequest:
    """Inputs for one finite waveform condition workflow."""

    channels: Sequence[int | str]
    condition_channel: int
    metric: str
    operator: str
    threshold: float
    timeout_seconds: float
    points: int = 1000
    waveform_format: str = "byte"
    count: int = 1
    interval_seconds: float = 0.0
    output_dir: str | Path | None = None
    log_scpi: bool = False


def plan_capture_until(
    request: CaptureUntilRequest,
    capabilities: ScopeCapabilities,
) -> OperationPlan:
    """Validate and plan one representative capture/evaluation iteration."""

    normalized = _normalize_request(request, capabilities)
    output_dir = (
        Path(request.output_dir)
        if request.output_dir is not None
        else CAPTURE_UNTIL_DEFAULT_BASE_DIR / "DRY-RUN"
    )
    csv_path, metadata_path = _match_paths(output_dir, 1, request.count)
    files = (
        {"kind": "manifest", "path": str(output_dir / "manifest.json")},
        {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
        {"kind": "csv", "path": str(csv_path)},
        {"kind": "metadata", "path": str(metadata_path)},
    )
    planned = list(
        planned_waveform_scpi(
            normalized["channels"],
            normalized["waveform_format"],
            normalized["points"],
        )
    )
    planned.append(":SYSTem:ERRor?")
    return OperationPlan(
        tuple(planned),
        files,
        _result_shape(
            "planned",
            normalized,
            request,
            output_dir=output_dir,
            completed_count=0,
            capture_count=0,
            termination_reason=None,
            error=None,
        ),
    )


def run_capture_until(
    scope: Oscilloscope,
    resource: str,
    request: CaptureUntilRequest,
    *,
    stop_requested: StopRequested | None = None,
    progress_reporter: ProgressReporter | None = None,
    sample_reporter: SampleReporter | None = None,
) -> OperationResult:
    """Capture, analyze, and persist only exact matching acquisitions."""

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
    condition_channel = normalized["condition_channel"]

    output_dir = prepare_batch_output_dir(
        request.output_dir, base_dir=CAPTURE_UNTIL_DEFAULT_BASE_DIR
    )
    manifest_path = output_dir / "manifest.json"
    scpi_log_path = output_dir / "scpi.log"
    files: list[dict[str, str]] = [
        {"kind": "manifest", "path": str(manifest_path)},
        {"kind": "scpi_log", "path": str(scpi_log_path)},
    ]
    manifest: dict[str, object] = {
        "schema_version": CAPTURE_UNTIL_SCHEMA_VERSION,
        "start_time": batch_iso_timestamp(),
        "end_time": None,
        "status": "running",
        "resource": resource,
        "backend": getattr(scope.backend, "backend", None),
        "timeout_ms": getattr(scope.backend, "timeout", None),
        "idn": idn_manifest_dict(idn),
        "channels": list(channels),
        "condition_channel": condition_channel,
        "points": points,
        "format": str(waveform_format).upper(),
        "metric": request.metric,
        "operator": request.operator,
        "threshold": float(request.threshold),
        "requested_count": request.count,
        "completed_count": 0,
        "capture_count": 0,
        "timeout_seconds": float(request.timeout_seconds),
        "interval_seconds": float(request.interval_seconds),
        "termination_reason": None,
        "matches": [],
        "files": _relative_files(files, output_dir),
        "error": None,
    }
    human = [
        f"Capture until: CH{condition_channel} {request.metric} {request.operator} "
        f"{float(request.threshold):.12g}",
        f"Channels: {', '.join(f'CH{channel}' for channel in channels)}",
        f"Matches to capture: {request.count}",
        f"Timeout seconds: {float(request.timeout_seconds):.12g}",
        f"Interval seconds: {float(request.interval_seconds):.12g}",
        f"Output directory: {output_dir}",
    ]
    last_system_error: dict[str, object] | None = None
    reporter_failed = False
    current_capture = 0

    try:
        _write_manifest(manifest, manifest_path)
        with workflow_scpi_logging(scpi_log_path, echo_to_stderr=request.log_scpi):
            for entry in drain_preexisting_system_errors(scope):
                human.append(f"Pre-operation stale system error drained: {entry.format()}")
            start_perf = time.perf_counter()
            while int(manifest["completed_count"]) < request.count:
                if _stop_requested(stop_requested):
                    return _finish_result(
                        "cancelled", 130, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope, error=None,
                        termination_reason=None,
                    )
                if time.perf_counter() - start_perf >= float(request.timeout_seconds):
                    return _finish_result(
                        "error", 1, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope,
                        error=_condition_timeout_error(request.timeout_seconds),
                        termination_reason="condition_timeout",
                    )

                current_capture += 1
                capture = _capture_waveform(scope, channels, waveform_format, points)
                entry = scope.query_system_error()
                last_system_error = system_error_manifest_dict(entry)
                manifest["capture_count"] = current_capture
                if entry.is_error:
                    return _finish_result(
                        "instrument_error", 1, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope,
                        error={
                            "type": "instrument_error",
                            "capture_index": current_capture,
                            "message": entry.format(),
                        },
                        termination_reason=None,
                    )

                condition_capture = _capture_for_channel(capture, condition_channel)
                metric_value = waveform_metric(condition_capture, request.metric)
                matched = waveform_condition_matches(
                    metric_value, request.operator, float(request.threshold)
                )
                match_entry = None
                if matched:
                    match_index = int(manifest["completed_count"]) + 1
                    csv_path, metadata_path = _match_paths(
                        output_dir, match_index, request.count
                    )
                    written_csv = write_capture_csv_file(capture, csv_path)
                    written_metadata = write_capture_metadata_file(
                        capture, metadata_path, idn=idn, resource=resource
                    )
                    files.extend(
                        [
                            {"kind": "csv", "path": str(written_csv)},
                            {"kind": "metadata", "path": str(written_metadata)},
                        ]
                    )
                    match_entry = {
                        "match_index": match_index,
                        "capture_index": current_capture,
                        "timestamp_iso": batch_iso_timestamp(),
                        "elapsed_seconds": time.perf_counter() - start_perf,
                        "metric_value": metric_value,
                        "csv": relative_manifest_path(written_csv, output_dir),
                        "metadata": relative_manifest_path(written_metadata, output_dir),
                        "actual_points": capture_actual_points(capture),
                    }
                    candidate = copy.deepcopy(manifest)
                    candidate["completed_count"] = match_index
                    matches = candidate["matches"]
                    assert isinstance(matches, list)
                    matches.append(match_entry)
                    candidate["files"] = _relative_files(files, output_dir)
                    _write_manifest(candidate, manifest_path)
                    manifest = candidate
                else:
                    _write_manifest(manifest, manifest_path)

                update = {
                    "capture_index": current_capture,
                    "matched": matched,
                    "metric_value": metric_value,
                    "completed_count": manifest["completed_count"],
                }
                if match_entry is not None:
                    update["match"] = dict(match_entry)
                try:
                    if sample_reporter is not None:
                        sample_reporter(update)
                    if progress_reporter is not None:
                        progress_reporter(
                            WorkflowProgress(
                                completed_count=int(manifest["completed_count"]),
                                total_count=request.count,
                                elapsed_seconds=time.perf_counter() - start_perf,
                            )
                        )
                except Exception:
                    reporter_failed = True
                    raise

                if int(manifest["completed_count"]) >= request.count:
                    return _finish_result(
                        "completed", 0, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope, error=None,
                        termination_reason="condition_met",
                    )
                if _stop_requested(stop_requested):
                    return _finish_result(
                        "cancelled", 130, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope, error=None,
                        termination_reason=None,
                    )
                remaining = float(request.timeout_seconds) - (
                    time.perf_counter() - start_perf
                )
                wait_seconds = min(float(request.interval_seconds), max(0.0, remaining))
                if wait_seconds > 0 and not interruptible_wait(
                    wait_seconds, stop_requested=stop_requested
                ):
                    return _finish_result(
                        "cancelled", 130, manifest, manifest_path, scpi_log_path,
                        files, human, idn, last_system_error, scope, error=None,
                        termination_reason=None,
                    )
    except KeyboardInterrupt:
        return _finish_result(
            "interrupted", 130, manifest, manifest_path, scpi_log_path,
            files, human, idn, last_system_error, scope,
            error="KeyboardInterrupt", termination_reason=None, best_effort=True,
        )
    except (OSError, OscilloscopeError) as exc:
        if reporter_failed:
            raise
        return _finish_result(
            "error", 1, manifest, manifest_path, scpi_log_path, files, human,
            idn, last_system_error, scope,
            error={
                "type": type(exc).__name__,
                "capture_index": current_capture or None,
                "message": str(exc),
            },
            termination_reason=None,
            best_effort=True,
        )
    raise AssertionError("finite capture until exited without a result")


def _validate_request_fields(request: CaptureUntilRequest) -> None:
    if isinstance(request.count, bool) or not isinstance(request.count, int):
        raise ParameterValidationError("capture until count must be an integer")
    if not 1 <= request.count <= 255:
        raise ParameterValidationError("capture until count must be between 1 and 255")
    if isinstance(request.condition_channel, bool) or not isinstance(
        request.condition_channel, int
    ):
        raise ParameterValidationError("capture until condition channel must be an integer")
    if isinstance(request.channels, (str, bytes)) or not isinstance(
        request.channels, Sequence
    ):
        raise ParameterValidationError("capture until channels must be a sequence")
    if not isinstance(request.waveform_format, str) or request.waveform_format.lower() not in {
        "byte", "word"
    }:
        raise ParameterValidationError("capture until format must be byte or word")
    validate_waveform_metric(request.metric)
    validate_waveform_operator(request.operator)
    _finite_number(request.threshold, "capture until threshold")
    _finite_number(request.timeout_seconds, "capture until timeout seconds", positive=True)
    _finite_number(
        request.interval_seconds,
        "capture until interval seconds",
        nonnegative=True,
    )
    if request.output_dir is not None and not isinstance(request.output_dir, (str, Path)):
        raise ParameterValidationError("capture until output_dir must be a path or string")
    if not isinstance(request.log_scpi, bool):
        raise ParameterValidationError("capture until log_scpi must be a boolean")


def _normalize_request(
    request: CaptureUntilRequest, capabilities: ScopeCapabilities
) -> dict[str, object]:
    _validate_request_fields(request)
    channels = resolve_capture_channels(request.channels, capabilities)
    condition_channel = validate_analog_channel(request.condition_channel, capabilities)
    if condition_channel not in channels:
        raise ParameterValidationError(
            "capture until condition channel must be included in selected channels"
        )
    points = validate_waveform_points(request.points, capabilities)
    waveform_format = request.waveform_format.lower()
    if waveform_format == "word":
        validate_word_format_supported(capabilities)
    return {
        "channels": channels,
        "condition_channel": condition_channel,
        "points": points,
        "waveform_format": waveform_format,
    }


def _capture_for_channel(
    capture: WaveformCapture | MultiChannelWaveformCapture, channel: int
) -> WaveformCapture:
    if isinstance(capture, WaveformCapture):
        if capture.channel == channel:
            return capture
    else:
        for item in capture.captures:
            if item.channel == channel:
                return item
    raise OscilloscopeError(f"condition channel CH{channel} missing from waveform capture")


def _match_paths(output_dir: Path, index: int, count: int) -> tuple[Path, Path]:
    width = max(3, len(str(count)))
    stem = f"match_{index:0{width}d}"
    return output_dir / f"{stem}.csv", output_dir / f"{stem}_meta.json"


def _finite_number(
    value: object,
    label: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParameterValidationError(f"{label} must be a finite number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ParameterValidationError(f"{label} must be a finite number")
    if positive and parsed <= 0:
        raise ParameterValidationError(f"{label} must be greater than zero")
    if nonnegative and parsed < 0:
        raise ParameterValidationError(f"{label} must be non-negative")
    return parsed


def _condition_timeout_error(timeout_seconds: float) -> dict[str, object]:
    return {
        "type": "condition_timeout",
        "message": (
            "waveform condition did not collect all requested matches within "
            f"{float(timeout_seconds):.12g} seconds"
        ),
    }


def _write_manifest(manifest: Mapping[str, object], path: Path) -> None:
    try:
        write_batch_manifest(manifest, path)
    except OSError as exc:
        raise OscilloscopeError(
            f"could not write capture until manifest {path}: {exc.strerror or exc}"
        ) from exc


def _relative_files(
    files: Sequence[Mapping[str, str]], output_dir: Path
) -> list[dict[str, str]]:
    return [
        {
            "kind": item["kind"],
            "path": relative_manifest_path(item["path"], output_dir),
        }
        for item in files
    ]


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
    termination_reason: str | None,
    best_effort: bool = False,
) -> OperationResult:
    manifest["status"] = status
    manifest["end_time"] = batch_iso_timestamp()
    manifest["termination_reason"] = termination_reason
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
            f"Capture until status: {status}",
            f"Matches: {manifest['completed_count']}/{manifest['requested_count']}",
            f"Waveform acquisitions: {manifest['capture_count']}",
            f"Manifest: {manifest_path}",
            f"SCPI log: {scpi_log_path}",
        ]
    )
    result = _result_shape(
        status,
        {
            "channels": tuple(manifest["channels"]),
            "condition_channel": manifest["condition_channel"],
            "points": manifest["points"],
            "waveform_format": str(manifest["format"]).lower(),
        },
        CaptureUntilRequest(
            channels=tuple(manifest["channels"]),
            condition_channel=int(manifest["condition_channel"]),
            metric=str(manifest["metric"]),
            operator=str(manifest["operator"]),
            threshold=float(manifest["threshold"]),
            timeout_seconds=float(manifest["timeout_seconds"]),
            points=int(manifest["points"]),
            waveform_format=str(manifest["format"]).lower(),
            count=int(manifest["requested_count"]),
            interval_seconds=float(manifest["interval_seconds"]),
        ),
        output_dir=manifest_path.parent,
        completed_count=int(manifest["completed_count"]),
        capture_count=int(manifest["capture_count"]),
        termination_reason=termination_reason,
        error=error,
    )
    result["manifest_path"] = str(manifest_path)
    result["scpi_log_path"] = str(scpi_log_path)
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


def _result_shape(
    status: str,
    normalized: Mapping[str, object],
    request: CaptureUntilRequest,
    *,
    output_dir: Path | None,
    completed_count: int,
    capture_count: int,
    termination_reason: str | None,
    error: dict[str, object] | str | None,
) -> dict[str, object]:
    return {
        "status": status,
        "channels": list(normalized["channels"]),
        "condition_channel": normalized["condition_channel"],
        "points": normalized["points"],
        "format": str(normalized["waveform_format"]).upper(),
        "metric": request.metric,
        "operator": request.operator,
        "threshold": float(request.threshold),
        "requested_count": request.count,
        "completed_count": completed_count,
        "capture_count": capture_count,
        "timeout_seconds": float(request.timeout_seconds),
        "interval_seconds": float(request.interval_seconds),
        "termination_reason": termination_reason,
        "output_dir": str(output_dir) if output_dir is not None else None,
        "manifest_path": str(output_dir / "manifest.json") if output_dir is not None else None,
        "scpi_log_path": str(output_dir / "scpi.log") if output_dir is not None else None,
        "error": error,
    }


def _pre_start_cancelled_result(request: CaptureUntilRequest) -> OperationResult:
    return OperationResult(
        130,
        {
            "status": "cancelled",
            "channels": [],
            "condition_channel": request.condition_channel,
            "points": request.points,
            "format": request.waveform_format.upper(),
            "metric": request.metric,
            "operator": request.operator,
            "threshold": float(request.threshold),
            "requested_count": request.count,
            "completed_count": 0,
            "capture_count": 0,
            "timeout_seconds": float(request.timeout_seconds),
            "interval_seconds": float(request.interval_seconds),
            "termination_reason": None,
            "output_dir": None,
            "manifest_path": None,
            "scpi_log_path": None,
            "error": None,
        },
        human_lines=["Capture until cancelled."],
    )


def _stop_requested(callback: StopRequested | None) -> bool:
    return callback is not None and callback()
