"""Finite retained-window waveform monitoring workflow."""

from __future__ import annotations

import csv
from collections import deque
from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Callable, Mapping, Sequence

from .batch import (
    batch_iso_timestamp,
    idn_manifest_dict,
    prepare_batch_output_dir,
    relative_manifest_path,
    system_error_manifest_dict,
    write_batch_manifest,
)
from .capabilities import ScopeCapabilities
from .errors import OscilloscopeError, ParameterValidationError
from .operations import OperationResult, _capture_waveform
from .planning import OperationPlan, planned_waveform_scpi, resolve_capture_channels
from .scope import Oscilloscope
from .waveform import (
    MultiChannelWaveformCapture,
    WaveformCapture,
    validate_waveform_points,
    validate_word_format_supported,
    waveform_vertical_unit_suffix,
)
from .workflow import (
    ProgressReporter,
    StopRequested,
    WorkflowProgress,
    drain_preexisting_system_errors,
    interruptible_wait,
    workflow_scpi_logging,
)


CAPTURE_MONITOR_SCHEMA_VERSION = 1
CAPTURE_MONITOR_DEFAULT_BASE_DIR = Path("data") / "capture_monitor"
DEFAULT_RETENTION_POINTS = 250_000
RETENTION_POLICY = "drop_oldest"
TIME_AXIS_SEMANTICS = "per_capture_repeated_acquisitions"
MonitorUpdateReporter = Callable[[Mapping[str, object]], None]


@dataclass(frozen=True)
class CaptureMonitorRequest:
    """Inputs for one finite retained-window waveform monitor."""

    channels: Sequence[int | str]
    count: int
    points: int = 1000
    waveform_format: str = "byte"
    interval_seconds: float = 0.0
    retention_points: int = DEFAULT_RETENTION_POINTS
    save_results: bool = True
    output_dir: str | Path | None = None
    log_scpi: bool = False


@dataclass(frozen=True)
class MonitorCaptureChunk:
    """Minimum retained data for one completed waveform acquisition."""

    capture_index: int
    global_start_index: int
    time_s: tuple[float, ...]
    channel_values: dict[int, tuple[float, ...]]
    channel_units: dict[int, str]

    @property
    def point_count(self) -> int:
        return len(self.time_s)


def plan_capture_monitor(
    request: CaptureMonitorRequest,
    capabilities: ScopeCapabilities,
) -> OperationPlan:
    """Validate and plan one representative monitor capture."""

    normalized = _normalize_request(request, capabilities)
    output_dir = None
    if request.save_results:
        output_dir = (
            Path(request.output_dir)
            if request.output_dir is not None
            else CAPTURE_MONITOR_DEFAULT_BASE_DIR / "DRY-RUN"
        )
    csv_path, manifest_path, scpi_log_path = _workflow_paths(output_dir)
    files = tuple(
        {"kind": kind, "path": str(path)}
        for kind, path in (
            ("csv", csv_path),
            ("manifest", manifest_path),
            ("scpi_log", scpi_log_path),
        )
        if path is not None
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
            completed_count=0,
            total_observed_points=0,
            retained_points=0,
            dropped_points=0,
            metrics={},
            first_retained_capture_index=None,
            last_retained_capture_index=None,
            output_dir=output_dir,
            error=None,
        ),
    )


def run_capture_monitor(
    scope: Oscilloscope,
    resource: str,
    request: CaptureMonitorRequest,
    *,
    stop_requested: StopRequested | None = None,
    progress_reporter: ProgressReporter | None = None,
    sample_reporter: MonitorUpdateReporter | None = None,
) -> OperationResult:
    """Capture a finite series while retaining a bounded in-memory window."""

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

    output_dir = (
        prepare_batch_output_dir(
            request.output_dir, base_dir=CAPTURE_MONITOR_DEFAULT_BASE_DIR
        )
        if request.save_results
        else None
    )
    csv_path, manifest_path, scpi_log_path = _workflow_paths(output_dir)
    files = [
        {"kind": kind, "path": str(path)}
        for kind, path in (
            ("csv", csv_path),
            ("manifest", manifest_path),
            ("scpi_log", scpi_log_path),
        )
        if path is not None
    ]
    manifest: dict[str, object] = {
        "schema_version": CAPTURE_MONITOR_SCHEMA_VERSION,
        "start_time": batch_iso_timestamp(),
        "end_time": None,
        "status": "running",
        "resource": resource,
        "backend": getattr(scope.backend, "backend", None),
        "timeout_ms": getattr(scope.backend, "timeout", None),
        "idn": idn_manifest_dict(idn),
        "channels": list(channels),
        "points_per_capture": points,
        "format": str(waveform_format).upper(),
        "requested_count": request.count,
        "completed_count": 0,
        "interval_seconds": float(request.interval_seconds),
        "retention_limit_points_per_channel": request.retention_points,
        "total_observed_points_per_channel": 0,
        "retained_points_per_channel": 0,
        "dropped_points_per_channel": 0,
        "first_retained_capture_index": None,
        "last_retained_capture_index": None,
        "overall_metrics": {},
        "retention_policy": RETENTION_POLICY,
        "time_axis_semantics": TIME_AXIS_SEMANTICS,
        "files": _relative_files(files, output_dir) if output_dir is not None else [],
        "error": None,
    }
    human = [
        f"Capture monitor: {request.count} capture(s)",
        f"Channels: {', '.join(f'CH{channel}' for channel in channels)}",
        f"Points per capture: {points}",
        f"Retention: {request.retention_points} points per channel",
        f"Interval seconds: {float(request.interval_seconds):.12g}",
        "Repeated acquisitions may contain acquisition and communication gaps.",
    ]
    human.append(
        f"Output directory: {output_dir}"
        if output_dir is not None
        else "Result file saving: disabled"
    )
    retained: deque[MonitorCaptureChunk] = deque()
    retained_points = 0
    dropped_points = 0
    total_observed_points = 0
    running: dict[int, dict[str, float | str]] = {}
    last_system_error: dict[str, object] | None = None
    reporter_failed = False
    current_capture = 0

    try:
        if manifest_path is not None:
            _write_manifest(manifest, manifest_path)
        with workflow_scpi_logging(scpi_log_path, echo_to_stderr=request.log_scpi):
            for entry in drain_preexisting_system_errors(scope):
                human.append(f"Pre-operation stale system error drained: {entry.format()}")
            start_perf = time.perf_counter()
            for index in range(1, request.count + 1):
                current_capture = index
                if _stop_requested(stop_requested):
                    return _finish_result(
                        "cancelled", 130, manifest, retained, csv_path,
                        manifest_path, scpi_log_path, files, human, idn,
                        last_system_error, scope, error=None,
                    )

                capture = _capture_waveform(scope, channels, waveform_format, points)
                entry = scope.query_system_error()
                last_system_error = system_error_manifest_dict(entry)
                if entry.is_error:
                    return _finish_result(
                        "instrument_error", 1, manifest, retained, csv_path,
                        manifest_path, scpi_log_path, files, human, idn,
                        last_system_error, scope,
                        error={
                            "type": "instrument_error",
                            "capture_index": index,
                            "message": entry.format(),
                        },
                    )

                chunk = _monitor_chunk(capture, index, total_observed_points)
                if chunk.point_count > request.retention_points:
                    raise OscilloscopeError(
                        "capture monitor acquisition exceeds the retention point limit"
                    )
                total_observed_points += chunk.point_count
                _update_running_metrics(running, chunk)
                dropped_capture_count = 0
                while retained and (
                    retained_points + chunk.point_count > request.retention_points
                ):
                    removed = retained.popleft()
                    retained_points -= removed.point_count
                    dropped_points += removed.point_count
                    dropped_capture_count += 1
                retained.append(chunk)
                retained_points += chunk.point_count

                manifest["completed_count"] = index
                manifest["total_observed_points_per_channel"] = total_observed_points
                manifest["retained_points_per_channel"] = retained_points
                manifest["dropped_points_per_channel"] = dropped_points
                manifest["first_retained_capture_index"] = retained[0].capture_index
                manifest["last_retained_capture_index"] = retained[-1].capture_index
                manifest["overall_metrics"] = _metrics_snapshot(running)
                if manifest_path is not None:
                    _write_manifest(manifest, manifest_path)

                update = _transient_update(
                    chunk,
                    request,
                    completed_count=index,
                    total_observed_points=total_observed_points,
                    retained_points=retained_points,
                    dropped_points=dropped_points,
                    dropped_capture_count=dropped_capture_count,
                    metrics=_metrics_snapshot(running),
                )
                try:
                    if sample_reporter is not None:
                        sample_reporter(update)
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
                        "completed", 0, manifest, retained, csv_path,
                        manifest_path, scpi_log_path, files, human, idn,
                        last_system_error, scope, error=None,
                    )
                if _stop_requested(stop_requested):
                    return _finish_result(
                        "cancelled", 130, manifest, retained, csv_path,
                        manifest_path, scpi_log_path, files, human, idn,
                        last_system_error, scope, error=None,
                    )
                if request.interval_seconds > 0 and not interruptible_wait(
                    request.interval_seconds, stop_requested=stop_requested
                ):
                    return _finish_result(
                        "cancelled", 130, manifest, retained, csv_path,
                        manifest_path, scpi_log_path, files, human, idn,
                        last_system_error, scope, error=None,
                    )
    except KeyboardInterrupt:
        return _finish_result(
            "interrupted", 130, manifest, retained, csv_path, manifest_path,
            scpi_log_path, files, human, idn, last_system_error, scope,
            error="KeyboardInterrupt", best_effort=True,
        )
    except (OSError, OscilloscopeError) as exc:
        if reporter_failed:
            raise
        return _finish_result(
            "error", 1, manifest, retained, csv_path, manifest_path,
            scpi_log_path, files, human, idn, last_system_error, scope,
            error={
                "type": type(exc).__name__,
                "capture_index": current_capture or None,
                "message": str(exc),
            },
            best_effort=True,
        )
    raise AssertionError("finite capture monitor exited without a result")


def write_capture_monitor_csv(
    chunks: Sequence[MonitorCaptureChunk], path: str | Path
) -> Path:
    """Write a retained monitor window with explicit acquisition boundaries."""

    if not chunks:
        raise OscilloscopeError("capture monitor retained window is empty")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    channels = tuple(chunks[0].channel_values)
    units = chunks[0].channel_units
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "capture_index",
                "global_sample_index",
                "sample_index",
                "time_s",
                *(
                    f"ch{channel}_{waveform_vertical_unit_suffix(units[channel])}"
                    for channel in channels
                ),
            )
        )
        for chunk in chunks:
            for sample_index, time_value in enumerate(chunk.time_s):
                writer.writerow(
                    (
                        chunk.capture_index,
                        chunk.global_start_index + sample_index,
                        sample_index,
                        time_value,
                        *(chunk.channel_values[channel][sample_index] for channel in channels),
                    )
                )
    return output_path


def _validate_request_fields(request: CaptureMonitorRequest) -> None:
    if isinstance(request.count, bool) or not isinstance(request.count, int):
        raise ParameterValidationError("capture monitor count must be an integer")
    if request.count < 1:
        raise ParameterValidationError("capture monitor count must be at least 1")
    if isinstance(request.channels, (str, bytes)) or not isinstance(
        request.channels, Sequence
    ):
        raise ParameterValidationError("capture monitor channels must be a sequence")
    if not isinstance(request.waveform_format, str) or request.waveform_format.lower() not in {
        "byte", "word"
    }:
        raise ParameterValidationError("capture monitor format must be byte or word")
    _finite_nonnegative(request.interval_seconds, "capture monitor interval seconds")
    if isinstance(request.retention_points, bool) or not isinstance(
        request.retention_points, int
    ):
        raise ParameterValidationError("capture monitor retention points must be an integer")
    if not isinstance(request.save_results, bool):
        raise ParameterValidationError("capture monitor save_results must be a boolean")
    if request.output_dir is not None and not isinstance(request.output_dir, (str, Path)):
        raise ParameterValidationError("capture monitor output_dir must be a path or string")
    if not isinstance(request.log_scpi, bool):
        raise ParameterValidationError("capture monitor log_scpi must be a boolean")


def _normalize_request(
    request: CaptureMonitorRequest, capabilities: ScopeCapabilities
) -> dict[str, object]:
    _validate_request_fields(request)
    channels = resolve_capture_channels(request.channels, capabilities)
    points = validate_waveform_points(request.points, capabilities)
    if request.retention_points < points:
        raise ParameterValidationError(
            "capture monitor retention points must be at least points per capture"
        )
    if request.retention_points % points != 0:
        raise ParameterValidationError(
            "capture monitor retention points must be a multiple of points per capture"
        )
    waveform_format = request.waveform_format.lower()
    if waveform_format == "word":
        validate_word_format_supported(capabilities)
    return {
        "channels": channels,
        "points": points,
        "waveform_format": waveform_format,
    }


def _finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParameterValidationError(f"{label} must be a finite number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ParameterValidationError(f"{label} must be a finite number")
    if parsed < 0:
        raise ParameterValidationError(f"{label} must be non-negative")
    return parsed


def _monitor_chunk(
    capture: WaveformCapture | MultiChannelWaveformCapture,
    capture_index: int,
    global_start_index: int,
) -> MonitorCaptureChunk:
    captures = capture.captures if isinstance(capture, MultiChannelWaveformCapture) else (capture,)
    reference = captures[0]
    if not reference.time_s:
        raise OscilloscopeError("capture monitor waveform contains no samples")
    channel_values: dict[int, tuple[float, ...]] = {}
    channel_units: dict[int, str] = {}
    for item in captures:
        if item.time_s != reference.time_s:
            raise OscilloscopeError("capture monitor channel time axes are not aligned")
        if len(item.vertical_values) != len(reference.time_s):
            raise OscilloscopeError("capture monitor channel sample counts are not aligned")
        channel_values[item.channel] = tuple(item.vertical_values)
        channel_units[item.channel] = item.vertical_unit
    return MonitorCaptureChunk(
        capture_index=capture_index,
        global_start_index=global_start_index,
        time_s=tuple(reference.time_s),
        channel_values=channel_values,
        channel_units=channel_units,
    )


def _update_running_metrics(
    running: dict[int, dict[str, float | str]], chunk: MonitorCaptureChunk
) -> None:
    for channel, values in chunk.channel_values.items():
        minimum = min(values)
        maximum = max(values)
        current = running.get(channel)
        if current is None:
            running[channel] = {
                "minimum": minimum,
                "maximum": maximum,
                "abs_max": max(abs(minimum), abs(maximum)),
                "unit": chunk.channel_units[channel],
            }
            continue
        current["minimum"] = min(float(current["minimum"]), minimum)
        current["maximum"] = max(float(current["maximum"]), maximum)
        current["abs_max"] = max(
            float(current["abs_max"]), abs(minimum), abs(maximum)
        )


def _metrics_snapshot(
    running: Mapping[int, Mapping[str, float | str]]
) -> dict[str, dict[str, float | str]]:
    return {
        f"CH{channel}": {
            "maximum": float(values["maximum"]),
            "minimum": float(values["minimum"]),
            "peak_to_peak": float(values["maximum"]) - float(values["minimum"]),
            "abs_max": float(values["abs_max"]),
            "unit": str(values["unit"]),
        }
        for channel, values in running.items()
    }


def _transient_update(
    chunk: MonitorCaptureChunk,
    request: CaptureMonitorRequest,
    *,
    completed_count: int,
    total_observed_points: int,
    retained_points: int,
    dropped_points: int,
    dropped_capture_count: int,
    metrics: Mapping[str, object],
) -> dict[str, object]:
    return {
        "capture_index": chunk.capture_index,
        "global_start_index": chunk.global_start_index,
        "time_s": list(chunk.time_s),
        "channels": {
            f"CH{channel}": {
                "unit": chunk.channel_units[channel],
                "values": list(values),
            }
            for channel, values in chunk.channel_values.items()
        },
        "completed_count": completed_count,
        "requested_count": request.count,
        "total_observed_points": total_observed_points,
        "retained_points": retained_points,
        "dropped_points": dropped_points,
        "dropped_capture_count": dropped_capture_count,
        "retention_points": request.retention_points,
        "metrics": dict(metrics),
    }


def _workflow_paths(
    output_dir: Path | None,
) -> tuple[Path | None, Path | None, Path | None]:
    if output_dir is None:
        return None, None, None
    return (
        output_dir / "retained_waveforms.csv",
        output_dir / "manifest.json",
        output_dir / "scpi.log",
    )


def _write_manifest(manifest: Mapping[str, object], path: Path) -> None:
    try:
        write_batch_manifest(manifest, path)
    except OSError as exc:
        raise OscilloscopeError(
            f"could not write capture monitor manifest {path}: {exc.strerror or exc}"
        ) from exc


def _relative_files(
    files: Sequence[Mapping[str, str]], output_dir: Path | None
) -> list[dict[str, str]]:
    if output_dir is None:
        return []
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
    retained: Sequence[MonitorCaptureChunk],
    csv_path: Path | None,
    manifest_path: Path | None,
    scpi_log_path: Path | None,
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
    manifest["error"] = error
    if csv_path is not None and retained:
        if best_effort:
            try:
                write_capture_monitor_csv(retained, csv_path)
            except (OSError, OscilloscopeError):
                pass
        else:
            try:
                write_capture_monitor_csv(retained, csv_path)
            except OSError as exc:
                raise OscilloscopeError(
                    f"could not write capture monitor CSV {csv_path}: {exc.strerror or exc}"
                ) from exc
    elif csv_path is not None:
        files[:] = [item for item in files if item["kind"] != "csv"]
    manifest["files"] = _relative_files(files, manifest_path.parent if manifest_path else None)
    if manifest_path is not None:
        if best_effort:
            try:
                _write_manifest(manifest, manifest_path)
            except OscilloscopeError:
                pass
        else:
            _write_manifest(manifest, manifest_path)
    human.extend(
        [
            f"Capture monitor status: {status}",
            f"Completed captures: {manifest['completed_count']}/{manifest['requested_count']}",
            f"Observed points per channel: {manifest['total_observed_points_per_channel']}",
            f"Retained points per channel: {manifest['retained_points_per_channel']}",
            f"Dropped points per channel: {manifest['dropped_points_per_channel']}",
        ]
    )
    if manifest_path is not None:
        if retained:
            human.append(f"Retained waveform CSV: {csv_path}")
        human.extend([f"Manifest: {manifest_path}", f"SCPI log: {scpi_log_path}"])
    normalized = {
        "channels": tuple(manifest["channels"]),
        "points": manifest["points_per_capture"],
        "waveform_format": str(manifest["format"]).lower(),
    }
    result = _result_shape(
        status,
        normalized,
        CaptureMonitorRequest(
            channels=tuple(manifest["channels"]),
            count=int(manifest["requested_count"]),
            points=int(manifest["points_per_capture"]),
            waveform_format=str(manifest["format"]).lower(),
            interval_seconds=float(manifest["interval_seconds"]),
            retention_points=int(manifest["retention_limit_points_per_channel"]),
            save_results=manifest_path is not None,
        ),
        completed_count=int(manifest["completed_count"]),
        total_observed_points=int(manifest["total_observed_points_per_channel"]),
        retained_points=int(manifest["retained_points_per_channel"]),
        dropped_points=int(manifest["dropped_points_per_channel"]),
        metrics=dict(manifest["overall_metrics"]),
        first_retained_capture_index=manifest["first_retained_capture_index"],
        last_retained_capture_index=manifest["last_retained_capture_index"],
        output_dir=manifest_path.parent if manifest_path is not None else None,
        error=error,
    )
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
    request: CaptureMonitorRequest,
    *,
    completed_count: int,
    total_observed_points: int,
    retained_points: int,
    dropped_points: int,
    metrics: Mapping[str, object],
    first_retained_capture_index: object,
    last_retained_capture_index: object,
    output_dir: Path | None,
    error: dict[str, object] | str | None,
) -> dict[str, object]:
    csv_path, manifest_path, scpi_log_path = _workflow_paths(output_dir)
    return {
        "status": status,
        "channels": list(normalized["channels"]),
        "points": normalized["points"],
        "format": str(normalized["waveform_format"]).upper(),
        "requested_count": request.count,
        "completed_count": completed_count,
        "interval_seconds": float(request.interval_seconds),
        "retention_points": request.retention_points,
        "total_observed_points": total_observed_points,
        "retained_points": retained_points,
        "dropped_points": dropped_points,
        "first_retained_capture_index": first_retained_capture_index,
        "last_retained_capture_index": last_retained_capture_index,
        "metrics": dict(metrics),
        "retention_policy": RETENTION_POLICY,
        "time_axis_semantics": TIME_AXIS_SEMANTICS,
        "save_results": request.save_results,
        "output_dir": str(output_dir) if output_dir is not None else None,
        "csv_path": str(csv_path) if csv_path is not None else None,
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
        "scpi_log_path": str(scpi_log_path) if scpi_log_path is not None else None,
        "error": error,
    }


def _pre_start_cancelled_result(request: CaptureMonitorRequest) -> OperationResult:
    return OperationResult(
        130,
        {
            "status": "cancelled",
            "channels": [],
            "points": request.points,
            "format": request.waveform_format.upper(),
            "requested_count": request.count,
            "completed_count": 0,
            "interval_seconds": float(request.interval_seconds),
            "retention_points": request.retention_points,
            "total_observed_points": 0,
            "retained_points": 0,
            "dropped_points": 0,
            "first_retained_capture_index": None,
            "last_retained_capture_index": None,
            "metrics": {},
            "retention_policy": RETENTION_POLICY,
            "time_axis_semantics": TIME_AXIS_SEMANTICS,
            "save_results": request.save_results,
            "output_dir": None,
            "csv_path": None,
            "manifest_path": None,
            "scpi_log_path": None,
            "error": None,
        },
        human_lines=["Capture monitor cancelled."],
    )


def _stop_requested(callback: StopRequested | None) -> bool:
    return callback is not None and callback()
