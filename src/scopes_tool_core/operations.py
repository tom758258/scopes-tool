"""Reusable agent-core oscilloscope operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import time
from typing import Callable, Mapping, Sequence

from .acquisition import (
    acquisition_count_command,
    acquisition_count_query,
    acquisition_type_command,
    acquisition_type_query,
    normalize_acquisition_type,
    validate_acquisition_count,
)
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
from .measurements import (
    is_pair_measurement_item,
    measurement_query,
    normalize_measurement_item,
    pair_measurement_query,
)
from .measure_logger import (
    MeasureLogManifest,
    log_measurements_workflow,
    measure_log_paths,
    prepare_measure_log_output_dir,
)
from .output_files import (
    capture_output_paths,
    write_capture_csv_file,
    write_capture_metadata_file,
    write_capture_plot_file,
    write_json_file,
    write_json_file_best_effort,
    write_screenshot_png_file,
)
from .planning import (
    parse_measurement_item_list,
    parse_pair_specs,
    resolve_capture_channels,
    resolve_pair_measurement_channels,
    resolve_single_measurement_channel,
    resolve_sweep_channels,
)
from .scope import Oscilloscope
from .trigger import (
    TriggerWaitConfig,
    parse_trigger_mode,
    trigger_mode_query,
    wait_for_trigger_completion,
)
from .waveform import (
    MultiChannelWaveformCapture,
    WaveformCapture,
    validate_waveform_vertical_unit,
    validate_word_format_supported,
    validate_waveform_points,
    waveform_time_axis_tolerance_summary,
)
from .workflow import (
    ProgressReporter,
    StopRequested,
    WorkflowProgress,
    drain_preexisting_system_errors,
    interruptible_wait,
    workflow_scpi_logging,
)

_DEFAULT_TIMEZONE = timezone(timedelta(hours=8), name="UTC+8")


@dataclass(frozen=True)
class OperationResult:
    exit_code: int
    result: dict[str, object]
    files: list[dict[str, str]] = field(default_factory=list)
    system_error: dict[str, object] | None = None
    human_lines: list[str] = field(default_factory=list)
    idn: object | None = None
    backend: str | None = None
    timeout_ms: int | None = None


@dataclass(frozen=True)
class CaptureRequest:
    channels: Sequence[int | str]
    points: int
    waveform_format: str = "byte"
    csv_path: str | Path | None = None
    meta_path: str | Path | None = None
    plot_path: str | Path | None = None
    allow_time_axis_tolerance: bool = False
    trigger_wait: TriggerWaitConfig | None = None


@dataclass(frozen=True)
class CaptureBatchRequest:
    """Normalized request for one finite waveform capture batch."""

    channels: Sequence[int | str]
    points: int = 1000
    waveform_format: str = "byte"
    requested_count: int = 1
    interval_seconds: float = 0.0
    output_dir: str | Path | None = None
    log_scpi: bool = False


@dataclass(frozen=True)
class MeasureRequest:
    item: str
    channel: int | None = None
    source_channel: int | None = None
    reference_channel: int | None = None
    time_s: float | None = None
    level: float | None = None
    slope: str | None = None
    occurrence: int | None = None


@dataclass(frozen=True)
class MeasureSweepRequest:
    channels: Sequence[int | str] | None = None
    items: str = "vpp,frequency,period,vrms"
    pairs: Sequence[str] = ()
    pair_items: str = "phase,delay"


@dataclass(frozen=True)
class MeasureLogRequest:
    """Normalized request for one finite measurement logging run."""

    channels: Sequence[int | str] | None = None
    items: str = "vpp,frequency"
    pairs: Sequence[str] = ()
    pair_items: str = "phase,delay"
    interval_seconds: float = 1.0
    requested_count: int | None = None
    requested_duration_seconds: float | None = None
    output_dir: str | Path | None = None
    save_results: bool = True
    stop_on_error: bool = False
    log_scpi: bool = False


@dataclass(frozen=True)
class SmokeRequest:
    output_dir: str | Path | None = None
    log_scpi: bool = False


@dataclass(frozen=True)
class AcquisitionCheckRequest:
    output_dir: str | Path | None = None
    average_count: int = 16
    check_only: bool = False
    stop_on_error: bool = False
    restore_type: bool = False
    log_scpi: bool = False


def run_capture(
    scope: Oscilloscope,
    resource: str,
    request: CaptureRequest,
    *,
    _establish_error_boundary: bool = True,
) -> OperationResult:
    """Capture waveform data and write the requested artifacts."""

    human: list[str] = []
    idn = scope.query_idn()
    _append_session_header(human, scope, resource)
    human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])
    if scope.capabilities is None:
        return OperationResult(1, {}, human_lines=human, idn=idn, **_scope_backend_json(scope))

    csv_path, meta_path, plot_path = capture_output_paths(
        request.csv_path,
        request.meta_path,
        request.plot_path,
    )
    channels = resolve_capture_channels(request.channels, scope.capabilities)
    points = validate_waveform_points(request.points, scope.capabilities)
    waveform_format = request.waveform_format.upper()
    if request.waveform_format.lower() == "word":
        validate_word_format_supported(scope.capabilities)
    if _establish_error_boundary:
        for _entry in drain_preexisting_system_errors(scope):
            human.append(f"Pre-operation stale system error drained: {_entry.format()}")
    if len(channels) == 1:
        human.append(
            f"Planned capture: CH{channels[0]}, {points} points, {waveform_format} format"
        )
    else:
        human.append(
            f"Planned capture: {_format_channel_list(channels)}, {points} points, "
            f"{waveform_format} format"
        )
    trigger_json = None
    if request.trigger_wait is not None:
        human.append(
            "Trigger wait: arming single acquisition and polling operation condition"
        )
        trigger_wait = wait_for_trigger_completion(
            scope.scpi,
            request.trigger_wait,
            classifier_profile=_trigger_wait_classifier_profile(scope),
        )
        trigger_json = trigger_wait.to_json(request.trigger_wait)
        if not trigger_wait.capture_allowed:
            entry = scope.query_system_error()
            system_error = _system_error_json(entry)
            result = {
                "channels": list(channels),
                "requested_points": points,
                "format": waveform_format,
                "files": [],
                "trigger": trigger_json,
            }
            human.extend(
                [
                    f"Trigger wait outcome: {trigger_wait.outcome}",
                    f"System error: {entry.format()}",
                ]
            )
            return OperationResult(
                1,
                result,
                [],
                system_error,
                human,
                idn=idn,
                **_scope_backend_json(scope),
            )
    capture = _capture_waveform(scope, channels, request.waveform_format, points)
    human.extend(_waveform_capture_commands(channels, request.waveform_format, points))

    time_axis_tolerance = None
    if request.allow_time_axis_tolerance and isinstance(capture, MultiChannelWaveformCapture):
        time_axis_tolerance = waveform_time_axis_tolerance_summary(capture)
    written_csv = write_capture_csv_file(
        capture,
        csv_path,
        allow_time_axis_tolerance=request.allow_time_axis_tolerance,
    )
    written_meta = write_capture_metadata_file(
        capture,
        meta_path,
        idn=idn,
        resource=resource,
        time_axis_tolerance=time_axis_tolerance,
    )
    files = [
        {"kind": "csv", "path": str(written_csv)},
        {"kind": "metadata", "path": str(written_meta)},
    ]
    if plot_path is not None:
        written_plot = write_capture_plot_file(capture, plot_path)
        files.append({"kind": "plot_png", "path": str(written_plot)})
    result = {
        "channels": list(channels),
        "requested_points": points,
        "format": waveform_format,
        "files": files,
        **_waveform_capture_summary(capture),
    }
    if trigger_json is not None:
        result["trigger"] = trigger_json
    if time_axis_tolerance is not None:
        result["time_axis_tolerance"] = time_axis_tolerance
    entry = scope.query_system_error()
    system_error = _system_error_json(entry)
    human.extend(
        [
            *([f"Trigger wait outcome: {trigger_json['outcome']}"] if trigger_json is not None else []),
            _format_actual_points(capture),
            f"CSV: {written_csv}",
            f"Metadata: {written_meta}",
        ]
    )
    if plot_path is not None:
        human.append(f"Plot: {plot_path}")
    human.append(f"System error: {entry.format()}")
    return OperationResult(
        1 if entry.is_error else 0,
        result,
        files,
        system_error,
        human,
        idn=idn,
        **_scope_backend_json(scope),
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
                entry = scope.query_system_error()
                last_system_error = system_error_manifest_dict(entry)
                capture_entry = {
                    "index": index,
                    "csv": relative_manifest_path(written_csv, output_dir),
                    "metadata": relative_manifest_path(written_meta, output_dir),
                    "actual_points": capture_actual_points(capture),
                    "system_error": dict(last_system_error),
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


def run_doctor(scope: Oscilloscope, resource: str) -> OperationResult:
    """Return a read-only diagnostic snapshot for an open scope."""

    human: list[str] = []
    idn = scope.query_idn()
    _append_session_header(human, scope, resource)
    human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])
    if scope.capabilities is None:
        human.append("Capabilities: unavailable for this model")
        return OperationResult(1, {}, human_lines=human, idn=idn, **_scope_backend_json(scope))
    snapshot = doctor_snapshot(scope)
    entry = scope.query_system_error()
    trigger = snapshot["edge_trigger"]
    human.extend(
        [
            "Doctor snapshot:",
            f"Acquisition type: {snapshot['acquisition']['type']}",
            f"Average count: {snapshot['acquisition']['count']}",
            f"Channels: {_format_channel_list([item['channel'] for item in snapshot['channels']])}",
            f"Timebase scale: {snapshot['timebase']['scale_seconds_per_division']}",
            f"Timebase position: {snapshot['timebase']['position_seconds']}",
            "Edge trigger: "
            f"CH{trigger['source_channel']}, {trigger['level_volts']:.12g} V, "
            f"{trigger['slope']}",
            f"System error: {entry.format()}",
        ]
    )
    return OperationResult(
        1 if entry.is_error else 0,
        snapshot,
        system_error=_system_error_json(entry),
        human_lines=human,
        idn=idn,
        **_scope_backend_json(scope),
    )


def run_measure(
    scope: Oscilloscope,
    resource: str,
    request: MeasureRequest,
    *,
    _establish_error_boundary: bool = True,
) -> OperationResult:
    """Run one read-only measurement query."""

    human: list[str] = []
    idn = scope.query_idn()
    _append_session_header(human, scope, resource)
    human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])
    if scope.capabilities is None:
        human.append("Capabilities: unavailable for this model")
        return OperationResult(1, {}, human_lines=human, idn=idn, **_scope_backend_json(scope))
    item = normalize_measurement_item(request.item)
    kwargs = _measurement_query_kwargs(request, item)
    if is_pair_measurement_item(item):
        source, reference = resolve_pair_measurement_channels(request, scope.capabilities, item)
        command = pair_measurement_query(item, source, reference, capabilities=scope.capabilities)
        human.append(f"Planned query: CH{source} to CH{reference} {item} measurement")
    else:
        channel = resolve_single_measurement_channel(request, scope.capabilities)
        command = measurement_query(item, channel, capabilities=scope.capabilities, **kwargs)
        human.append(
            f"Planned query: CH{channel} {item} measurement"
            f"{_format_measurement_parameters(kwargs)}"
        )
    if _establish_error_boundary:
        for _entry in drain_preexisting_system_errors(scope):
            human.append(f"Pre-operation stale system error drained: {_entry.format()}")
    if is_pair_measurement_item(item):
        measurement = scope.query_pair_measurement(source, reference, item)
    else:
        measurement = scope.query_measurement(channel, item, **kwargs)
    result = {"command": command, **_measurement_result_json(measurement, parameters=kwargs)}
    entry = scope.query_system_error()
    human.extend(
        [
            f"Command: {command}",
            f"Measurement: {measurement.item}",
            f"Channel: {measurement.channel}",
        ]
    )
    if measurement.reference_channel is not None:
        human.append(f"Reference channel: {measurement.reference_channel}")
    human.append(f"Valid: {'true' if measurement.valid else 'false'}")
    if measurement.valid:
        if measurement.value is None:
            raise OscilloscopeError("measurement result was marked valid without a numeric value")
        human.append(f"Value {measurement.unit}: {_format_optional_number(measurement.value)}")
    else:
        human.append("Value: unavailable")
    human.append(f"Raw response: {measurement.raw_value}")
    if measurement.reason is not None:
        human.append(f"Reason: {measurement.reason}")
    human.append(f"System error: {entry.format()}")
    exit_code = 1 if entry.is_error or not measurement.valid else 0
    return OperationResult(
        exit_code,
        result,
        system_error=_system_error_json(entry),
        human_lines=human,
        idn=idn,
        **_scope_backend_json(scope),
    )


def run_measure_sweep(
    scope: Oscilloscope,
    resource: str,
    request: MeasureSweepRequest,
) -> OperationResult:
    """Run a multi-channel measurement sweep."""

    human: list[str] = []
    idn = scope.query_idn()
    _append_session_header(human, scope, resource)
    human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])
    if scope.capabilities is None:
        human.append("Capabilities: unavailable for this model")
        return OperationResult(1, {}, human_lines=human, idn=idn, **_scope_backend_json(scope))

    channels = resolve_sweep_channels(request.channels, scope.capabilities)
    items = parse_measurement_item_list(request.items, allow_pair=False)
    pairs = parse_pair_specs(request.pairs, scope.capabilities)
    pair_items = parse_measurement_item_list(request.pair_items, allow_pair=True)
    for channel in channels:
        for item in items:
            measurement_query(item, channel, capabilities=scope.capabilities)
    for _entry in drain_preexisting_system_errors(scope):
        human.append(f"Pre-operation stale system error drained: {_entry.format()}")
    measurements: list[dict[str, object]] = []
    human.append(f"Planned sweep: {_format_channel_list(channels)}; items {', '.join(items)}")
    for channel in channels:
        for item in items:
            command = measurement_query(item, channel, capabilities=scope.capabilities)
            human.append(f"Command: {command}")
            measurements.append(_run_sweep_measurement(scope, command, channel, item))
    for source_channel, reference_channel in pairs:
        for item in pair_items:
            try:
                command = pair_measurement_query(
                    item,
                    source_channel,
                    reference_channel,
                    capabilities=scope.capabilities,
                )
                human.append(f"Command: {command}")
                measurements.append(
                    _run_sweep_pair_measurement(
                        scope,
                        command,
                        source_channel,
                        reference_channel,
                        item,
                    )
                )
            except OscilloscopeError as exc:
                measurements.append(
                    _sweep_error_record(
                        item=item,
                        channel=source_channel,
                        reference_channel=reference_channel,
                        command=None,
                        exc=exc,
                        system_error=None,
                    )
                )
    summary = measure_sweep_summary(measurements)
    human.append(
        "Summary: "
        f"{summary['valid_count']} valid, "
        f"{summary['invalid_count']} invalid, "
        f"{summary['error_count']} errors"
    )
    result = {
        "channels": list(channels),
        "items": list(items),
        "pairs": [
            {"source_channel": source, "reference_channel": reference}
            for source, reference in pairs
        ],
        "pair_items": list(pair_items),
        "measurements": measurements,
        "summary": summary,
    }
    return OperationResult(
        1 if summary["invalid_count"] or summary["error_count"] else 0,
        result,
        human_lines=human,
        idn=idn,
        **_scope_backend_json(scope),
    )


def run_measure_log(
    scope: Oscilloscope,
    resource: str,
    request: MeasureLogRequest,
    *,
    stop_requested: StopRequested | None = None,
    progress_reporter: ProgressReporter | None = None,
    sample_reporter: Callable[[Mapping[str, object]], None] | None = None,
) -> OperationResult:
    """Run a finite measurement logger and return its structured outcome."""

    if request.requested_count is None and request.requested_duration_seconds is None:
        raise OscilloscopeError(
            "measure-log requires --count or --duration-seconds so the run is finite"
        )
    if not isinstance(request.save_results, bool):
        raise OscilloscopeError("measure-log save_results must be a boolean")
    output_dir = (
        prepare_measure_log_output_dir(request.output_dir)
        if request.save_results
        else None
    )
    csv_path, manifest_path, scpi_log_path = (
        measure_log_paths(output_dir)
        if output_dir is not None
        else (None, None, None)
    )
    files = [
        {"kind": kind, "path": str(path)}
        for kind, path in (("csv", csv_path), ("manifest", manifest_path), ("scpi_log", scpi_log_path))
        if path is not None
    ]
    human: list[str] = []
    idn = None
    channels: tuple[int, ...] = ()
    items: tuple[str, ...] = ()
    pairs: tuple[tuple[int, int], ...] = ()
    pair_items: tuple[str, ...] = ()
    reporter_failed = False

    def report_progress(progress: WorkflowProgress) -> None:
        nonlocal reporter_failed
        if progress_reporter is None:
            return
        try:
            progress_reporter(progress)
        except Exception:
            reporter_failed = True
            raise

    def report_sample(sample: Mapping[str, object]) -> None:
        nonlocal reporter_failed
        if sample_reporter is None:
            return
        try:
            sample_reporter(sample)
        except Exception:
            reporter_failed = True
            raise

    try:
        with workflow_scpi_logging(scpi_log_path, echo_to_stderr=request.log_scpi):
            idn = scope.query_idn()
            _append_session_header(human, scope, resource)
            human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])
            if scope.capabilities is None:
                raise OscilloscopeError("Capabilities unavailable for this model")
            channels = resolve_capture_channels(
                request.channels or ("all",),
                scope.capabilities,
            )
            items = parse_measurement_item_list(request.items, allow_pair=False)
            pairs = parse_pair_specs(request.pairs, scope.capabilities)
            pair_items = parse_measurement_item_list(request.pair_items, allow_pair=True)
            for _entry in drain_preexisting_system_errors(scope):
                human.append(f"Pre-operation stale system error drained: {_entry.format()}")
            workflow = log_measurements_workflow(
                scope=scope,
                resource=resource,
                output_dir=output_dir,
                csv_path=csv_path,
                manifest_path=manifest_path,
                scpi_log_path=scpi_log_path,
                channels=list(channels),
                items=list(items),
                pairs=list(pairs),
                pair_items=list(pair_items),
                interval_seconds=request.interval_seconds,
                requested_count=request.requested_count,
                requested_duration_seconds=request.requested_duration_seconds,
                stop_on_error=request.stop_on_error,
                stop_requested=stop_requested,
                progress_reporter=report_progress if progress_reporter is not None else None,
                sample_reporter=report_sample if sample_reporter is not None else None,
            )
        human.extend(workflow.human_lines)
        if scpi_log_path is not None:
            human.append(f"SCPI log: {scpi_log_path}")
        return OperationResult(
            workflow.exit_code,
            _measure_log_result_json(
                workflow.manifest,
                csv_path,
                manifest_path,
                scpi_log_path,
            ),
            files,
            workflow.system_error,
            human,
            idn=idn,
            **_scope_backend_json(scope),
        )
    except OscilloscopeError as exc:
        if reporter_failed:
            raise
        result, system_error = _measure_log_failure_result(
            manifest_path=manifest_path,
            csv_path=csv_path,
            scpi_log_path=scpi_log_path,
            channels=channels,
            items=items,
            pairs=pairs,
            pair_items=pair_items,
            request=request,
            error=str(exc),
        )
        raise _OperationError(
            exc,
            OperationResult(
                1,
                result,
                files,
                system_error,
                human,
                idn=idn,
                **_scope_backend_json(scope),
            ),
        ) from exc
    except OSError as exc:
        if reporter_failed:
            raise
        error = OscilloscopeError(
            f"could not write SCPI log file {scpi_log_path}: {exc}"
        )
        result, system_error = _measure_log_failure_result(
            manifest_path=manifest_path,
            csv_path=csv_path,
            scpi_log_path=scpi_log_path,
            channels=channels,
            items=items,
            pairs=pairs,
            pair_items=pair_items,
            request=request,
            error=str(error),
        )
        raise _OperationError(
            error,
            OperationResult(
                1,
                result,
                files,
                system_error,
                human,
                idn=idn,
                **_scope_backend_json(scope),
            ),
        ) from exc


def run_smoke(scope: Oscilloscope, resource: str, request: SmokeRequest) -> OperationResult:
    """Run the capture-safe smoke workflow and write its report."""

    output_dir = _prepare_output_dir(
        Path(request.output_dir) if request.output_dir is not None else _default_output_dir("hardware_smoke")
    )
    report_path = output_dir / "report.json"
    scpi_log_path = output_dir / "scpi.log"
    capture_csv_path = output_dir / "capture.csv"
    capture_meta_path = output_dir / "capture_meta.json"
    screenshot_path = output_dir / "screen.png"
    files = _smoke_file_list(output_dir)
    report = _smoke_report(resource, files)
    human: list[str] = []
    idn = None
    try:
        with workflow_scpi_logging(scpi_log_path, echo_to_stderr=request.log_scpi):
            idn = scope.query_idn()
            report["backend"] = getattr(scope.backend, "backend", None)
            report["timeout_ms"] = getattr(scope.backend, "timeout", None)
            report["idn"] = idn_manifest_dict(idn)
            _append_session_header(human, scope, resource)
            human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])
            if scope.capabilities is None:
                raise OscilloscopeError("Capabilities unavailable for this model")
            for _entry in drain_preexisting_system_errors(scope):
                human.append(f"Pre-operation stale system error drained: {_entry.format()}")
            doctor = doctor_snapshot(scope)
            report["doctor"] = doctor
            measurements = []
            for item in ("vpp", "vrms"):
                command = measurement_query(item, 1, capabilities=scope.capabilities)
                human.append(f"Command: {command}")
                measurement = scope.query_measurement(1, item)
                record = {
                    "command": command,
                    **_measurement_result_json(measurement, parameters={}),
                    "system_error": None,
                }
                measurements.append(record)
                if record.get("valid") is False:
                    warnings = report.setdefault("warnings", [])
                    if isinstance(warnings, list):
                        warnings.append(
                            f"CH1 {item} measurement invalid: {record.get('reason')}"
                        )
            report["measurements"] = measurements
            human.append("Planned capture: CH1, 1000 points, BYTE format")
            capture = scope.capture_waveform_byte(1, points=1000)
            written_csv = write_capture_csv_file(capture, capture_csv_path)
            written_meta = write_capture_metadata_file(
                capture,
                capture_meta_path,
                idn=idn,
                resource=resource,
            )
            report["capture"] = {
                "csv": str(written_csv),
                "metadata": str(written_meta),
                **_waveform_capture_summary(capture),
            }
            human.append("Planned capture: current screen PNG image with black background")
            screenshot = scope.capture_screenshot_png(background="black")
            written_png = write_screenshot_png_file(screenshot, screenshot_path)
            report["screenshot"] = {
                "png_path": str(written_png),
                "format": screenshot.format_name,
                "palette": screenshot.palette,
                "background": screenshot.background,
                "byte_count": len(screenshot.data),
            }
            entry = scope.query_system_error()
            system_error = _system_error_json(entry)
            report["post_check_error"] = system_error
            report["status"] = "instrument_error" if entry.is_error else "completed"
            report["end_time"] = batch_iso_timestamp()
            write_json_file(report, report_path, file_kind="smoke report JSON")
            human.extend(
                [
                    f"Output directory: {output_dir}",
                    f"Report: {report_path}",
                    f"SCPI log: {scpi_log_path}",
                    f"System error: {entry.format()}",
                ]
            )
            result = {
                "status": report["status"],
                "output_dir": str(output_dir),
                "report_path": str(report_path),
                "scpi_log_path": str(scpi_log_path),
                "files": files,
                "doctor": doctor,
                "measurements": measurements,
                "capture": report["capture"],
                "screenshot": report["screenshot"],
                "warnings": report["warnings"],
            }
            return OperationResult(
                1 if entry.is_error else 0,
                result,
                files,
                system_error,
                human,
                idn=idn,
                **_scope_backend_json(scope),
            )
    except OscilloscopeError as exc:
        report["status"] = "error"
        report["end_time"] = batch_iso_timestamp()
        report["error"] = str(exc)
        write_json_file_best_effort(report, report_path)
        result = {
            "status": report["status"],
            "output_dir": str(output_dir),
            "report_path": str(report_path),
            "scpi_log_path": str(scpi_log_path),
            "files": files,
            "warnings": report["warnings"],
            "error": str(exc),
        }
        raise _OperationError(exc, OperationResult(1, result, files, human_lines=human, idn=idn, **_scope_backend_json(scope))) from exc


def run_acquisition_check(
    scope: Oscilloscope,
    resource: str,
    request: AcquisitionCheckRequest,
) -> OperationResult:
    """Run the finite acquisition configuration check workflow."""

    average_count = validate_acquisition_count(request.average_count)
    if request.check_only and request.restore_type:
        raise OscilloscopeError("--check-only cannot be combined with --restore-type")
    output_dir = _prepare_output_dir(
        Path(request.output_dir)
        if request.output_dir is not None
        else _default_output_dir("hardware_acquisition")
    )
    report_path = output_dir / "report.json"
    scpi_log_path = output_dir / "scpi.log"
    files = _acquisition_check_file_list(output_dir)
    report = _acquisition_report(resource, files, average_count, request)
    human: list[str] = []
    idn = None
    try:
        with workflow_scpi_logging(scpi_log_path, echo_to_stderr=request.log_scpi):
            idn = scope.query_idn()
            report["backend"] = getattr(scope.backend, "backend", None)
            report["timeout_ms"] = getattr(scope.backend, "timeout", None)
            report["idn"] = idn_manifest_dict(idn)
            _append_session_header(human, scope, resource)
            human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])
            if scope.capabilities is None:
                raise OscilloscopeError("Capabilities unavailable for this model")
            for _entry in drain_preexisting_system_errors(scope):
                human.append(f"Pre-operation stale system error drained: {_entry.format()}")
            steps: list[dict[str, object]] = []
            if request.check_only:
                initial_step = _run_acquisition_query_step(scope, "initial-query", human)
                steps.append(initial_step)
                report["initial_acquisition"] = initial_step.get("readback")
                final_step = initial_step
                report["termination_reason"] = "check_only"
            else:
                initial_step = _run_acquisition_query_step(scope, "initial-query", human)
                steps.append(initial_step)
                report["initial_acquisition"] = initial_step.get("readback")
                final_step = initial_step
                for step_name, acquisition_type, step_count in (
                    ("set-normal", "normal", None),
                    ("set-average", "average", average_count),
                    ("set-high-resolution", "high_resolution", None),
                    ("set-peak", "peak", None),
                ):
                    step = _run_acquisition_type_step(
                        scope,
                        step_name,
                        acquisition_type,
                        human,
                        count=step_count,
                    )
                    steps.append(step)
                    if request.stop_on_error and step["status"] == "instrument_error":
                        report["stopped_on_error"] = True
                        report["termination_reason"] = "stopped_on_error"
                        final_step = step
                        break
                    if step_name == "set-average":
                        steps.append(_run_acquisition_query_step(scope, "post-average-query", human))
                    final_step = step
                if report["termination_reason"] is None:
                    report["termination_reason"] = "completed"
                if not report["stopped_on_error"]:
                    final_step = _run_acquisition_query_step(scope, "final-query", human)
                    steps.append(final_step)
            report["steps"] = steps
            report["final_acquisition"] = final_step.get("readback")
            post_check = _system_error_from_step(final_step)
            report["post_check_error"] = post_check
            report["status"] = (
                "instrument_error"
                if any(_step_has_system_error(step) for step in steps)
                else "completed"
            )
            if report["termination_reason"] == "completed" and report["status"] == "instrument_error":
                report["termination_reason"] = "completed_with_errors"
            restore_error = None
            if report["restore"]["requested"]:
                report["restore"]["attempted"] = True
                try:
                    _restore_acquisition_type(scope, report["initial_acquisition"])
                    report["restore"]["succeeded"] = True
                except OscilloscopeError as exc:
                    report["restore"]["succeeded"] = False
                    report["restore"]["error"] = str(exc)
                    report["status"] = "error"
                    report["termination_reason"] = "restore_failed"
                    restore_error = exc
            report["end_time"] = batch_iso_timestamp()
            write_json_file(report, report_path, file_kind="acquisition report JSON")
            human.extend(
                [
                    f"Output directory: {output_dir}",
                    f"Report: {report_path}",
                    f"SCPI log: {scpi_log_path}",
                ]
            )
            if post_check is not None:
                human.append(f"System error: {post_check['raw']}")
            result = {
                "status": report["status"],
                "output_dir": str(output_dir),
                "report_path": str(report_path),
                "scpi_log_path": str(scpi_log_path),
                "average_count": average_count,
                "check_only": request.check_only,
                "stopped_on_error": report["stopped_on_error"],
                "initial_acquisition": report["initial_acquisition"],
                "restore": report["restore"],
                "termination_reason": report["termination_reason"],
                "steps": steps,
                "final_acquisition": report["final_acquisition"],
                "files": files,
            }
            op_result = OperationResult(
                1 if report["status"] == "instrument_error" else 0,
                result,
                files,
                post_check,
                human,
                idn=idn,
                **_scope_backend_json(scope),
            )
            if restore_error is not None:
                raise _OperationError(restore_error, op_result) from restore_error
            return op_result
    except OscilloscopeError as exc:
        report["status"] = "error"
        report["end_time"] = batch_iso_timestamp()
        report["error"] = str(exc)
        write_json_file_best_effort(report, report_path)
        result = {
            "status": report["status"],
            "output_dir": str(output_dir),
            "report_path": str(report_path),
            "scpi_log_path": str(scpi_log_path),
            "average_count": average_count,
            "check_only": request.check_only,
            "stopped_on_error": report["stopped_on_error"],
            "initial_acquisition": report["initial_acquisition"],
            "restore": report["restore"],
            "termination_reason": report["termination_reason"],
            "steps": report["steps"],
            "final_acquisition": report["final_acquisition"],
            "files": files,
            "error": str(exc),
        }
        raise _OperationError(exc, OperationResult(1, result, files, human_lines=human, idn=idn, **_scope_backend_json(scope))) from exc


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
    return OperationResult(
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


class _OperationError(OscilloscopeError):
    def __init__(self, original: OscilloscopeError, result: OperationResult) -> None:
        super().__init__(str(original))
        self.result = result


def _measure_log_result_json(
    manifest: MeasureLogManifest,
    csv_path: Path | None,
    manifest_path: Path | None,
    scpi_log_path: Path | None,
) -> dict[str, object]:
    data = manifest.to_json_dict()
    return {
        "status": data["status"],
        "channels": data["channels"],
        "items": data["items"],
        "pairs": data["pairs"],
        "pair_items": data["pair_items"],
        "interval_seconds": data["interval_seconds"],
        "requested_count": data["requested_count"],
        "requested_duration_seconds": data["requested_duration_seconds"],
        "completed_rows": data["completed_rows"],
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
        "scpi_log_path": str(scpi_log_path) if scpi_log_path is not None else None,
        "csv_path": str(csv_path) if csv_path is not None else None,
        "error": data["error"],
        "last_measurement": data["last_measurement"],
    }


def _measure_log_failure_result(
    *,
    manifest_path: Path | None,
    csv_path: Path | None,
    scpi_log_path: Path | None,
    channels: Sequence[int],
    items: Sequence[str],
    pairs: Sequence[tuple[int, int]],
    pair_items: Sequence[str],
    request: MeasureLogRequest,
    error: str,
) -> tuple[dict[str, object], dict[str, object] | None]:
    data: dict[str, object] = {}
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path is not None else {}
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, json.JSONDecodeError):
        pass
    rows = data.get("rows")
    if not isinstance(rows, list):
        rows = []
    system_error = None
    if rows and isinstance(rows[-1], dict):
        candidate = rows[-1].get("system_error")
        if isinstance(candidate, dict):
            system_error = candidate
    result = {
        "status": data.get("status", "error"),
        "channels": data.get("channels", list(channels)),
        "items": data.get("items", list(items)),
        "pairs": data.get(
            "pairs",
            [f"{source}:{reference}" for source, reference in pairs],
        ),
        "pair_items": data.get("pair_items", list(pair_items)),
        "interval_seconds": data.get("interval_seconds", request.interval_seconds),
        "requested_count": data.get("requested_count", request.requested_count),
        "requested_duration_seconds": data.get(
            "requested_duration_seconds",
            request.requested_duration_seconds,
        ),
        "completed_rows": data.get("completed_rows", 0),
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
        "scpi_log_path": str(scpi_log_path) if scpi_log_path is not None else None,
        "csv_path": str(csv_path) if csv_path is not None else None,
        "error": data.get("error", error),
        "last_measurement": data.get("last_measurement"),
    }
    return result, system_error


def doctor_snapshot(scope: Oscilloscope) -> dict[str, object]:
    if scope.capabilities is None:
        raise OscilloscopeError("Capabilities unavailable for this model")
    acquisition = scope.query_acquisition_config()
    channels = []
    for channel in range(1, scope.capabilities.analog_channels + 1):
        channels.append(
            {
                "channel": channel,
                "display": scope.query_channel_display(channel),
                "scale_volts_per_division": scope.query_channel_scale(channel),
                "offset_volts": scope.query_channel_offset(channel),
                "coupling": scope.query_channel_coupling(channel),
                "probe_ratio": scope.query_channel_probe_ratio(channel),
                "bandwidth_limit": scope.query_channel_bandwidth_limit(channel),
            }
        )
    timebase = {
        "scale_seconds_per_division": scope.query_timebase_scale(),
        "position_seconds": scope.query_timebase_position(),
    }
    trigger = scope.query_trigger_edge()
    return {
        **_scope_backend_json(scope),
        "acquisition": {"type": acquisition.type, "count": acquisition.count},
        "channels": channels,
        "timebase": timebase,
        "edge_trigger": {
            "source_channel": trigger.source_channel,
            "level_volts": trigger.level_volts,
            "slope": trigger.slope,
        },
    }


def query_instrument_summary(scope: Oscilloscope) -> dict[str, object]:
    """Read the small, common instrument state used by status surfaces."""

    if scope.capabilities is None:
        raise OscilloscopeError("Capabilities unavailable for this model")

    channel_entries = scope.query_channel_summary()
    channels = [
        {
            "channel": entry.channel,
            "display": entry.display,
            "units": entry.units,
            "scale": entry.scale,
            "offset": entry.offset,
        }
        for entry in channel_entries
    ]
    channel_units = {entry.channel: entry.units for entry in channel_entries}

    raw_trigger_type = scope.scpi.query(trigger_mode_query()).strip()
    trigger_type = parse_trigger_mode(raw_trigger_type) or raw_trigger_type
    trigger: dict[str, object] = {
        "type": trigger_type,
        "source": None,
        "source_channel": None,
        "level": None,
        "units": None,
        "slope": None,
        "sweep": scope.query_trigger_sweep().mode,
    }
    if trigger_type == "edge":
        source = scope.query_trigger_edge_source()
        slope = scope.query_trigger_edge_slope()
        trigger["source"] = source.source or source.raw_source
        trigger["source_channel"] = source.source_channel
        trigger["slope"] = slope.slope or slope.raw_slope
        if (
            source.source == "analog-channel"
            and source.source_channel is not None
            and 1 <= source.source_channel <= scope.capabilities.analog_channels
        ):
            level = scope.query_trigger_edge_level(
                source_channel=source.source_channel
            )
            trigger["level"] = level.level_volts
            trigger["units"] = channel_units.get(source.source_channel)

    return {
        "channels": channels,
        "timebase": {
            "scale": scope.query_timebase_scale(),
            "position": scope.query_timebase_position(),
        },
        "trigger": trigger,
    }


def measure_sweep_summary(measurements: Sequence[dict[str, object]]) -> dict[str, int]:
    valid_count = 0
    invalid_count = 0
    error_count = 0
    for measurement in measurements:
        if measurement.get("error") is not None:
            error_count += 1
        elif measurement.get("valid") is True:
            valid_count += 1
        else:
            invalid_count += 1
    return {
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "error_count": error_count,
    }


def _capture_waveform(
    scope: Oscilloscope,
    channels: Sequence[int],
    waveform_format: str,
    points: int,
) -> WaveformCapture | MultiChannelWaveformCapture:
    if len(channels) == 1:
        if waveform_format.lower() == "word":
            return scope.capture_waveform_word(channels[0], points=points)
        return scope.capture_waveform_byte(channels[0], points=points)
    if waveform_format.lower() == "word":
        return scope.capture_waveforms_word(channels, points=points)
    return scope.capture_waveforms_byte(channels, points=points)


def _run_sweep_measurement(
    scope: Oscilloscope,
    command: str,
    channel: int,
    item: str,
) -> dict[str, object]:
    try:
        result = scope.query_measurement(channel, item)
        system_error = scope.query_system_error()
        return {
            "command": command,
            **_measurement_result_json(result, parameters={}),
            "system_error": _system_error_json(system_error),
        }
    except OscilloscopeError as exc:
        system_error = _query_system_error_best_effort(scope)
        return _sweep_error_record(
            item=item,
            channel=channel,
            reference_channel=None,
            command=command,
            exc=exc,
            system_error=system_error,
        )


def _run_sweep_pair_measurement(
    scope: Oscilloscope,
    command: str,
    source_channel: int,
    reference_channel: int,
    item: str,
) -> dict[str, object]:
    try:
        result = scope.query_pair_measurement(source_channel, reference_channel, item)
        system_error = scope.query_system_error()
        return {
            "command": command,
            **_measurement_result_json(result, parameters={}),
            "system_error": _system_error_json(system_error),
        }
    except OscilloscopeError as exc:
        system_error = _query_system_error_best_effort(scope)
        return _sweep_error_record(
            item=item,
            channel=source_channel,
            reference_channel=reference_channel,
            command=command,
            exc=exc,
            system_error=system_error,
        )


def _query_system_error_best_effort(scope: Oscilloscope):
    try:
        return scope.query_system_error()
    except OscilloscopeError:
        return None


def _sweep_error_record(
    *,
    item: str,
    channel: int,
    reference_channel: int | None,
    command: str | None,
    exc: OscilloscopeError,
    system_error,
) -> dict[str, object]:
    return {
        "item": item,
        "channel": channel,
        "reference_channel": reference_channel,
        "value": None,
        "unit": None,
        "valid": False,
        "raw_value": None,
        "reason": str(exc),
        "command": command,
        "system_error": None if system_error is None else _system_error_json(system_error),
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }


def _measurement_query_kwargs(request: MeasureRequest, item: str) -> dict[str, object]:
    from .planning import MeasurePlanRequest, measurement_query_kwargs

    return measurement_query_kwargs(
        MeasurePlanRequest(
            item=request.item,
            channel=request.channel,
            source_channel=request.source_channel,
            reference_channel=request.reference_channel,
            time_s=request.time_s,
            level=request.level,
            slope=request.slope,
            occurrence=request.occurrence,
        ),
        item,
    )


def _run_acquisition_query_step(
    scope: Oscilloscope,
    name: str,
    human: list[str],
) -> dict[str, object]:
    commands = [acquisition_type_query(), acquisition_count_query(), ":SYSTem:ERRor?"]
    human.extend([f"Step: {name}", f"Command: {commands[0]}", f"Command: {commands[1]}"])
    config = scope.query_acquisition_config()
    entry = scope.query_system_error()
    human.extend(
        [
            f"Acquisition type: {config.type}",
            f"Average count: {config.count}",
            f"System error: {entry.format()}",
        ]
    )
    return {
        "name": name,
        "operation": "query",
        "commands": commands,
        "readback": {"type": config.type, "count": config.count},
        "system_error": _system_error_json(entry),
        "status": "instrument_error" if entry.is_error else "completed",
    }


def _run_acquisition_type_step(
    scope: Oscilloscope,
    name: str,
    acquisition_type: str,
    human: list[str],
    *,
    count: int | None = None,
) -> dict[str, object]:
    normalized = normalize_acquisition_type(acquisition_type)
    commands = [acquisition_type_command(normalized)]
    if count is not None:
        commands.append(acquisition_count_command(count))
    commands.append(":SYSTem:ERRor?")
    human.append(f"Step: {name}")
    human.extend(f"Command: {command}" for command in commands[:-1])
    scope.set_acquisition_type(acquisition_type)
    if count is not None:
        scope.set_acquisition_count(count)
    entry = scope.query_system_error()
    human.append(f"System error: {entry.format()}")
    return {
        "name": name,
        "operation": "set",
        "type": acquisition_type,
        "scpi_type": normalized,
        "count": count,
        "commands": commands,
        "readback": {"type": acquisition_type, "count": count},
        "system_error": _system_error_json(entry),
        "status": "instrument_error" if entry.is_error else "completed",
    }


def _restore_acquisition_type(scope: Oscilloscope, initial) -> None:
    if not isinstance(initial, dict):
        return
    initial_type = initial.get("type")
    if not isinstance(initial_type, str):
        return
    scope.set_acquisition_type(initial_type)


def _step_has_system_error(step: dict[str, object]) -> bool:
    system_error = step.get("system_error")
    return isinstance(system_error, dict) and bool(system_error.get("is_error"))


def _system_error_from_step(step: dict[str, object]) -> dict[str, object] | None:
    system_error = step.get("system_error")
    if isinstance(system_error, dict):
        return system_error
    return None


def _smoke_report(resource: str, files: list[dict[str, str]]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "start_time": batch_iso_timestamp(),
        "end_time": None,
        "status": "running",
        "resource": resource,
        "backend": None,
        "timeout_ms": None,
        "idn": None,
        "doctor": None,
        "measurements": [],
        "capture": None,
        "screenshot": None,
        "post_check_error": None,
        "warnings": [],
        "files": files,
        "error": None,
    }


def _acquisition_report(
    resource: str,
    files: list[dict[str, str]],
    average_count: int,
    request: AcquisitionCheckRequest,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "start_time": batch_iso_timestamp(),
        "end_time": None,
        "status": "running",
        "resource": resource,
        "backend": None,
        "timeout_ms": None,
        "idn": None,
        "average_count": average_count,
        "check_only": request.check_only,
        "stopped_on_error": False,
        "initial_acquisition": None,
        "restore": {
            "requested": request.restore_type,
            "attempted": False,
            "succeeded": None,
            "error": None,
        },
        "termination_reason": None,
        "steps": [],
        "final_acquisition": None,
        "post_check_error": None,
        "files": files,
        "error": None,
    }


def _prepare_output_dir(output_dir: Path) -> Path:
    if output_dir.exists():
        existing = {item.name for item in output_dir.iterdir()}
    else:
        existing = set()
    if existing:
        raise OscilloscopeError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _default_output_dir(kind: str, now: datetime | None = None) -> Path:
    base_path = Path("data") / kind
    if now is None:
        capture_time = datetime.now(_DEFAULT_TIMEZONE)
    elif now.tzinfo is None:
        capture_time = now.replace(tzinfo=_DEFAULT_TIMEZONE)
    else:
        capture_time = now.astimezone(_DEFAULT_TIMEZONE)
    stem = capture_time.strftime("%Y-%m-%d-%H-%M-%S")
    candidate = base_path / stem
    suffix = 2
    while candidate.exists():
        candidate = base_path / f"{stem}-{suffix}"
        suffix += 1
    return candidate


def _smoke_file_list(output_dir: Path) -> list[dict[str, str]]:
    return [
        {"kind": "report", "path": str(output_dir / "report.json")},
        {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
        {"kind": "csv", "path": str(output_dir / "capture.csv")},
        {"kind": "metadata", "path": str(output_dir / "capture_meta.json")},
        {"kind": "png", "path": str(output_dir / "screen.png")},
    ]


def _acquisition_check_file_list(output_dir: Path) -> list[dict[str, str]]:
    return [
        {"kind": "report", "path": str(output_dir / "report.json")},
        {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
    ]


def _scope_backend_json(scope: Oscilloscope) -> dict[str, object]:
    return {
        "backend": getattr(scope.backend, "backend", None),
        "timeout_ms": getattr(scope.backend, "timeout", None),
    }


def _trigger_wait_classifier_profile(scope: Oscilloscope) -> str:
    if getattr(scope.backend, "backend", None) == "Keysight simulator":
        return "simulator"
    if scope.capabilities is not None and scope.capabilities.series in {
        "2000X",
        "3000X",
        "4000X",
    }:
        return scope.capabilities.series.lower()
    return "live"


def _system_error_json(entry) -> dict[str, object]:
    return {
        "code": entry.code,
        "message": entry.message,
        "raw": entry.raw,
        "is_error": entry.is_error,
    }


def _measurement_result_json(result, *, parameters: dict[str, object]) -> dict[str, object]:
    return {
        "item": result.item,
        "channel": result.channel,
        "reference_channel": result.reference_channel,
        "value": result.value,
        "unit": result.unit,
        "valid": result.valid,
        "raw_value": result.raw_value,
        "reason": result.reason,
        "parameters": parameters,
    }


def _waveform_preamble_json(preamble) -> dict[str, object]:
    return {
        "raw": preamble.raw,
        "format_code": preamble.format_code,
        "type_code": preamble.type_code,
        "points": preamble.points,
        "count": preamble.count,
        "x_increment": preamble.x_increment,
        "x_origin": preamble.x_origin,
        "x_reference": preamble.x_reference,
        "y_increment": preamble.y_increment,
        "y_origin": preamble.y_origin,
        "y_reference": preamble.y_reference,
    }


def _waveform_capture_summary(
    capture: WaveformCapture | MultiChannelWaveformCapture,
) -> dict[str, object]:
    if isinstance(capture, MultiChannelWaveformCapture):
        summaries = [_single_waveform_capture_summary(item) for item in capture.captures]
        return {
            "actual_points": {
                f"CH{item['channel']}": item["actual_points"] for item in summaries
            },
            "captures": summaries,
        }
    single = _single_waveform_capture_summary(capture)
    return {"actual_points": single["actual_points"], "captures": [single]}


def _single_waveform_capture_summary(capture: WaveformCapture) -> dict[str, object]:
    return {
        "channel": capture.channel,
        "vertical_unit": validate_waveform_vertical_unit(capture.vertical_unit),
        "requested_points": capture.requested_points,
        "actual_points": len(capture.raw_samples),
        "format": capture.format_name,
        "preamble": _waveform_preamble_json(capture.preamble),
        "byte_order": capture.byte_order,
        "unsigned": capture.unsigned,
    }


def _append_session_header(human: list[str], scope: Oscilloscope, resource: str) -> None:
    human.append(f"Resource: {resource}")
    backend = getattr(scope.backend, "backend", None)
    if backend is not None:
        human.append(f"PyVISA backend: {backend}")
    timeout = getattr(scope.backend, "timeout", None)
    if timeout is not None:
        human.append(f"Timeout ms: {timeout}")


def _format_channel_list(channels: Sequence[int]) -> str:
    return ", ".join(f"CH{channel}" for channel in channels)


def _format_measurement_parameters(values: dict[str, object]) -> str:
    if not values:
        return ""
    labels = {
        "time_s": "time",
        "level": "level",
        "slope": "slope",
        "occurrence": "occurrence",
    }
    formatted = ", ".join(f"{labels[key]}={value}" for key, value in values.items())
    return f" ({formatted})"


def _format_optional_number(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.12g}"


def _format_actual_points(capture: WaveformCapture | MultiChannelWaveformCapture) -> str:
    if isinstance(capture, MultiChannelWaveformCapture):
        per_channel = ", ".join(
            f"CH{item.channel}={len(item.raw_samples)}" for item in capture.captures
        )
        return f"Actual points: {per_channel}"
    return f"Actual points: {len(capture.raw_samples)}"


def _waveform_capture_commands(
    channels: Sequence[int],
    waveform_format: str,
    points: int,
) -> list[str]:
    from .planning import planned_waveform_scpi

    return [f"Command: {command}" for command in planned_waveform_scpi(channels, waveform_format, points)]
