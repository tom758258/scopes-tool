"""Reusable agent-core oscilloscope operations."""

from __future__ import annotations

from .status import status_payload, status_fields

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from .acquisition import (
    AcquisitionResponseError,
    normalize_acquisition_type,
    validate_acquisition_count,
)
from .batch import batch_iso_timestamp, idn_manifest_dict
from .capabilities import operation_supported
from .errors import OscilloscopeError, VisaBackendError
from .measurements import (
    is_pair_measurement_item,
    measurement_query,
    normalize_measurement_item,
    pair_measurement_query,
)
from .operation_support import (
    _append_session_header,
    _capture_waveform,
    _format_actual_points,
    _format_channel_list,
    _scope_backend_json,
    _waveform_capture_commands,
)
from .operation_types import (
    AcquisitionCheckRequest,
    CaptureRequest,
    MeasureRequest,
    MeasureSweepRequest,
    OperationResult,
    SmokeRequest,
    _OperationError,
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
    workflow_step_scpi,
    parse_measurement_item_list,
    parse_pair_specs,
    resolve_capture_channels,
    resolve_pair_measurement_channels,
    resolve_single_measurement_channel,
    resolve_sweep_channels,
)
from .scope import Oscilloscope
from .segmented import (
    parse_acquisition_mode,
    segmented_mode_query,
)
from .trigger import (
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
    StopRequested,
    drain_preexisting_system_errors,
    workflow_scpi_logging,
)

_DEFAULT_TIMEZONE = timezone(timedelta(hours=8), name="UTC+8")


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
        return OperationResult.from_status(1, {}, human_lines=human, idn=idn, **_scope_backend_json(scope))

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
    if _establish_error_boundary and operation_supported(scope.capabilities, "check-error"):
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
            "Trigger wait: arming single acquisition and polling for completion"
        )
        trigger_wait = scope.single_wait(request.trigger_wait)
        trigger_json = trigger_wait.to_json(request.trigger_wait)
        if not trigger_wait.capture_allowed:
            entry = scope.post_command_status("capture") if _establish_error_boundary else scope.workflow_status()
            system_error = _system_error_json(entry) if getattr(entry, "is_system_error_queue", True) else None
            result = {
                "channels": list(channels),
                "requested_points": points,
                "format": waveform_format,
                "files": [],
                "trigger": trigger_json,
            }
            if not getattr(entry, "is_system_error_queue", True):
                result["post_command_status"] = entry.to_json()
            human.extend(
                [
                    f"Trigger wait outcome: {trigger_wait.outcome}",
                    f"{getattr(entry, 'status_label', 'System error')}: {entry.format()}",
                ]
            )
            return OperationResult.from_status(
                1,
                result,
                [],
                system_error,
                human,
                idn=idn,
                **_scope_backend_json(scope),
            )
    capture = _capture_waveform(scope, channels, request.waveform_format, points)
    if operation_supported(scope.capabilities, "check-error"):
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
    entry = scope.post_command_status("capture") if _establish_error_boundary else scope.workflow_status()
    system_error = _system_error_json(entry) if getattr(entry, "is_system_error_queue", True) else None
    if not getattr(entry, "is_system_error_queue", True):
        result["post_command_status"] = entry.to_json()
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
    human.append(f"{getattr(entry, 'status_label', 'System error')}: {entry.format()}")
    return OperationResult.from_status(
        1 if entry.is_error else 0,
        result,
        files,
        system_error,
        human,
        idn=idn,
        **_scope_backend_json(scope),
    )


def run_doctor(scope: Oscilloscope, resource: str) -> OperationResult:
    """Return a read-only diagnostic snapshot for an open scope."""

    human: list[str] = []
    idn = scope.query_idn()
    _append_session_header(human, scope, resource)
    human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])
    if scope.capabilities is None:
        human.append("Capabilities: unavailable for this model")
        return OperationResult.from_status(1, {}, human_lines=human, idn=idn, **_scope_backend_json(scope))
    entry = scope.preflight_status(diagnostic=True)[0]
    if entry.is_error:
        human.append(f"System error: {entry.format()}")
        return OperationResult.from_status(
            1,
            {"failure_reason": "preexisting_system_error"},
            system_error=_system_error_json(entry),
            human_lines=human,
            idn=idn,
            **_scope_backend_json(scope),
        )
    snapshot = doctor_snapshot(scope)
    entry = scope.workflow_status()
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
            f"{trigger.get('source', 'CH' + str(trigger['source_channel']))}, "
            f"{_format_optional_number(trigger['level_volts'])} V, "
            f"{trigger['slope']}",
            f"System error: {entry.format()}",
        ]
    )
    return OperationResult.from_status(
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
        return OperationResult.from_status(1, {}, human_lines=human, idn=idn, **_scope_backend_json(scope))
    item = normalize_measurement_item(request.item)
    kwargs = _measurement_query_kwargs(request, item)
    if is_pair_measurement_item(item):
        source, reference = resolve_pair_measurement_channels(request, scope.capabilities, item)
        command = pair_measurement_query(item, source, reference, capabilities=scope.capabilities)
        human.append(f"Planned query: CH{source} to CH{reference} {item} measurement")
    else:
        channel = resolve_single_measurement_channel(request, scope.capabilities)
        command = scope.measurement_query_command(channel, item, **kwargs)
        human.append(
            f"Planned query: CH{channel} {item} measurement"
            f"{_format_measurement_parameters(kwargs)}"
        )
    if _establish_error_boundary and operation_supported(scope.capabilities, "check-error"):
        for _entry in drain_preexisting_system_errors(scope):
            human.append(f"Pre-operation stale system error drained: {_entry.format()}")
    if is_pair_measurement_item(item):
        measurement = scope.query_pair_measurement(source, reference, item)
    else:
        measurement = scope.query_measurement(channel, item, **kwargs)
    result = {"command": command, **_measurement_result_json(measurement, parameters=kwargs)}
    entry = scope.post_command_status("measure") if _establish_error_boundary else scope.workflow_status()
    if not getattr(entry, "is_system_error_queue", True):
        result["post_command_status"] = entry.to_json()
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
    human.append(f"{getattr(entry, 'status_label', 'System error')}: {entry.format()}")
    exit_code = 1 if entry.is_error or not measurement.valid else 0
    return OperationResult.from_status(
        exit_code,
        result,
        system_error=_system_error_json(entry) if getattr(entry, "is_system_error_queue", True) else None,
        human_lines=human,
        idn=idn,
        **_scope_backend_json(scope),
    )


def run_measure_sweep(
    scope: Oscilloscope,
    resource: str,
    request: MeasureSweepRequest,
    *,
    stop_requested: StopRequested | None = None,
) -> OperationResult:
    """Run a multi-channel measurement sweep."""

    human: list[str] = []
    idn = scope.query_idn()
    _append_session_header(human, scope, resource)
    human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])
    if scope.capabilities is None:
        human.append("Capabilities: unavailable for this model")
        return OperationResult.from_status(1, {}, human_lines=human, idn=idn, **_scope_backend_json(scope))

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
    cancelled = False
    transport_failed = False
    for channel in channels:
        for item in items:
            if stop_requested is not None and stop_requested():
                cancelled = True
                break
            command = scope.measurement_query_command(channel, item)
            human.append(f"Command: {command}")
            record = _run_sweep_measurement(scope, command, channel, item)
            measurements.append(record)
            if _sweep_must_stop(scope, record):
                transport_failed = True
                break
        if cancelled or transport_failed:
            break
    if not cancelled and not transport_failed:
        for source_channel, reference_channel in pairs:
            for item in pair_items:
                if stop_requested is not None and stop_requested():
                    cancelled = True
                    break
                try:
                    command = pair_measurement_query(
                        item,
                        source_channel,
                        reference_channel,
                        capabilities=scope.capabilities,
                    )
                    human.append(f"Command: {command}")
                    record = _run_sweep_pair_measurement(
                        scope,
                        command,
                        source_channel,
                        reference_channel,
                        item,
                    )
                    measurements.append(record)
                    if _sweep_must_stop(scope, record):
                        transport_failed = True
                        break
                except OscilloscopeError as exc:
                    record = _sweep_error_record(
                        item=item,
                        channel=source_channel,
                        reference_channel=reference_channel,
                        command=None,
                        exc=exc,
                        system_error=None,
                    )
                    measurements.append(record)
                    if _sweep_must_stop(scope, record):
                        transport_failed = True
                        break
            if cancelled or transport_failed:
                break
    summary = measure_sweep_summary(measurements)
    if cancelled:
        human.append("Sweep cancelled.")
    if transport_failed:
        human.append("Sweep stopped after transport error.")
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
    if measurements and measurements[-1].get("post_command_status") is not None:
        result["post_command_status"] = measurements[-1]["post_command_status"]
    if cancelled:
        return OperationResult.from_status(
            130,
            result,
            human_lines=human,
            idn=idn,
            **_scope_backend_json(scope),
        )
    return OperationResult.from_status(
        1 if summary["invalid_count"] or summary["error_count"] else 0,
        result,
        human_lines=human,
        idn=idn,
        **_scope_backend_json(scope),
    )


def _is_visa_timeout(exc: BaseException) -> bool:
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


def run_smoke(scope: Oscilloscope, resource: str, request: SmokeRequest) -> OperationResult:
    """Run the capture-safe smoke workflow, optionally writing its report."""

    if request.save_artifacts:
        output_dir = _prepare_output_dir(
            Path(request.output_dir) if request.output_dir is not None else _default_output_dir("hardware_smoke")
        )
        report_path = output_dir / "report.json"
        scpi_log_path = output_dir / "scpi.log"
        capture_csv_path = output_dir / "capture.csv"
        capture_meta_path = output_dir / "capture_meta.json"
        screenshot_path = output_dir / "screen.png"
        files = _smoke_file_list(output_dir)
    else:
        output_dir = None
        report_path = None
        scpi_log_path = None
        capture_csv_path = None
        capture_meta_path = None
        screenshot_path = None
        files = []
    report = _smoke_report(resource, files)
    report["save_artifacts"] = request.save_artifacts
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
            if not operation_supported(scope.capabilities, "smoke"):
                raise OscilloscopeError("smoke is unsupported for this model")
            for _entry in drain_preexisting_system_errors(scope):
                human.append(f"Pre-operation stale system error drained: {_entry.format()}")
            doctor = doctor_snapshot(scope)
            report["doctor"] = doctor
            measurements = []
            report["measurements"] = measurements
            for item in ("vpp", "vrms"):
                command = scope.measurement_query_command(1, item)
                human.append(f"Command: {command}")
                try:
                    measurement = scope.query_measurement(1, item)
                except VisaBackendError as exc:
                    if not _is_visa_timeout(exc):
                        raise
                    timeout_message = (
                        f"Smoke measurement query timed out for {command!r}. "
                        "The acquisition may not be ready. Smoke stopped without "
                        "further instrument queries because the VISA session may "
                        "no longer be synchronized."
                    )
                    human.append(timeout_message)
                    raise OscilloscopeError(timeout_message) from exc
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
            human.append("Planned capture: CH1, 1000 points, BYTE format")
            capture = scope.capture_waveform_byte(1, points=1000)
            written_csv = (
                write_capture_csv_file(capture, capture_csv_path)
                if capture_csv_path is not None
                else None
            )
            written_meta = (
                write_capture_metadata_file(
                    capture,
                    capture_meta_path,
                    idn=idn,
                    resource=resource,
                )
                if capture_meta_path is not None
                else None
            )
            report["capture"] = {
                "csv": str(written_csv) if written_csv is not None else None,
                "metadata": str(written_meta) if written_meta is not None else None,
                **_waveform_capture_summary(capture),
            }
            human.append("Planned capture: current screen PNG image with black background")
            screenshot = scope.capture_screenshot_png(background="black")
            written_png = (
                write_screenshot_png_file(screenshot, screenshot_path)
                if screenshot_path is not None
                else None
            )
            report["screenshot"] = {
                "png_path": str(written_png) if written_png is not None else None,
                "format": screenshot.format_name,
                "palette": screenshot.palette,
                "background": screenshot.background,
                "byte_count": len(screenshot.data),
            }
            entry = scope.workflow_status()
            system_error = _system_error_json(entry)
            report["post_check_error"] = status_fields(system_error)["system_error"]
            if "post_command_status" in status_fields(system_error):
                report["post_command_status"] = system_error
            report["status"] = "instrument_error" if entry.is_error else "completed"
            report["end_time"] = batch_iso_timestamp()
            if report_path is not None:
                write_json_file(report, report_path, file_kind="smoke report JSON")
                human.extend(
                    [
                        f"Output directory: {output_dir}",
                        f"Report: {report_path}",
                        f"SCPI log: {scpi_log_path}",
                    ]
                )
            human.append(f"System error: {entry.format()}")
            result = {
                "status": report["status"],
                "save_artifacts": request.save_artifacts,
                "output_dir": str(output_dir) if output_dir is not None else None,
                "report_path": str(report_path) if report_path is not None else None,
                "scpi_log_path": str(scpi_log_path) if scpi_log_path is not None else None,
                "files": files,
                "doctor": doctor,
                "measurements": measurements,
                "capture": report["capture"],
                "screenshot": report["screenshot"],
                "warnings": report["warnings"],
            }
            return OperationResult.from_status(
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
        if report_path is not None:
            write_json_file_best_effort(report, report_path)
        result = {
            "status": report["status"],
            "save_artifacts": request.save_artifacts,
            "output_dir": str(output_dir) if output_dir is not None else None,
            "report_path": str(report_path) if report_path is not None else None,
            "scpi_log_path": str(scpi_log_path) if scpi_log_path is not None else None,
            "files": files,
            "warnings": report["warnings"],
            "doctor": report.get("doctor"),
            "measurements": report.get("measurements"),
            "capture": report.get("capture"),
            "screenshot": report.get("screenshot"),
            "error": str(exc),
        }
        raise _OperationError(exc, OperationResult.from_status(1, result, files, human_lines=human, idn=idn, **_scope_backend_json(scope))) from exc


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
            scope.validate_acquisition_count(average_count)
            for _entry in drain_preexisting_system_errors(scope):
                human.append(f"Pre-operation stale system error drained: {_entry.format()}")
            steps: list[dict[str, object]] = []
            report["steps"] = steps

            def stop_after(step: dict[str, object]) -> bool:
                status = _system_error_from_step(step) or {}
                must_stop = status.get("complete") is False or (
                    request.stop_on_error and step["status"] == "instrument_error"
                )
                if must_stop:
                    report["stopped_on_error"] = True
                    report["termination_reason"] = "stopped_on_error"
                return must_stop

            initial_step = _run_acquisition_query_step(scope, "initial-query", human)
            steps.append(initial_step)
            report["initial_acquisition"] = initial_step.get("readback")
            final_step = initial_step
            if request.check_only:
                report["termination_reason"] = "check_only"
            elif not stop_after(initial_step):
                for step_name, acquisition_type, step_count in (
                    ("set-normal", "normal", None),
                    ("set-average", "average", average_count),
                    ("set-high-resolution", "high_resolution", None),
                    ("set-peak", "peak", None),
                ):
                    if scope.capabilities.acquisition_modes is not None and acquisition_type not in scope.capabilities.acquisition_modes:
                        steps.append({"name": step_name, "type": acquisition_type,
                                      "status": "skipped", "reason": "acquisition_mode_not_supported"})
                        continue
                    step = _run_acquisition_type_step(
                        scope,
                        step_name,
                        acquisition_type,
                        human,
                        count=step_count,
                    )
                    steps.append(step)
                    final_step = step
                    if stop_after(step):
                        break
                    if step_name == "set-average":
                        final_step = _run_acquisition_query_step(scope, "post-average-query", human)
                        steps.append(final_step)
                        if stop_after(final_step):
                            break
                if report["termination_reason"] is None:
                    report["termination_reason"] = "completed"
                if not report["stopped_on_error"]:
                    final_step = _run_acquisition_query_step(scope, "final-query", human)
                    steps.append(final_step)
            report["steps"] = steps
            report["final_acquisition"] = final_step.get("readback")
            post_check = _system_error_from_step(final_step)
            report["post_check_error"] = status_fields(post_check)["system_error"]
            if "post_command_status" in status_fields(post_check):
                report["post_command_status"] = post_check
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
                    if "post_command_status" in report:
                        restore_step = _run_acquisition_query_step(scope, "restore-query", human)
                        report["restore"].update(status_fields(_system_error_from_step(restore_step)))
                        report["restore"]["readback"] = restore_step["readback"]
                        if _step_has_system_error(restore_step):
                            raise OscilloscopeError("Acquisition restore reported an instrument error")
                        if restore_step["readback"]["type"] != report["initial_acquisition"]["type"]:
                            raise OscilloscopeError("Acquisition restore readback did not match the initial type")
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
            op_result = OperationResult.from_status(
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
        raise _OperationError(exc, OperationResult.from_status(
            1, result, files, report.get("post_command_status"),
            human_lines=human, idn=idn, **_scope_backend_json(scope),
        )) from exc


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
    trigger = scope.doctor_trigger_snapshot()
    return {
        **_scope_backend_json(scope),
        "acquisition": {"type": acquisition.type, "count": acquisition.count},
        "channels": channels,
        "timebase": timebase,
        "edge_trigger": trigger,
    }


def query_instrument_summary(scope: Oscilloscope) -> dict[str, object]:
    """Read the small, common instrument state used by status surfaces."""

    if scope.capabilities is None:
        raise OscilloscopeError("Capabilities unavailable for this model")

    from .tektronix import TektronixOscilloscope
    if isinstance(scope, TektronixOscilloscope):
        summary = scope._query_instrument_summary()
        summary["acquisition"] = query_acquisition_summary(scope)
        return summary

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
        "acquisition": query_acquisition_summary(scope),
    }


def query_acquisition_summary(scope: Oscilloscope) -> dict[str, str]:
    """Keep memory mode and sampling type independent, including read failures."""
    mode = query_acquisition_mode_best_effort(scope)
    try:
        acquisition_type = scope.query_acquisition_type()
    except Exception:
        acquisition_type = "unknown"
    return {"mode": mode, "type": acquisition_type}


def query_acquisition_mode_best_effort(scope: Oscilloscope) -> str:
    """Read the acquisition mode without failing the surrounding summary."""

    from .capabilities import operation_supported
    if scope.capabilities is not None and scope.capabilities.fixed_acquisition_memory_mode is not None:
        return scope.capabilities.fixed_acquisition_memory_mode
    if scope.capabilities is not None and not operation_supported(scope.capabilities, "segmented-memory"):
        return "unknown"
    try:
        return parse_acquisition_mode(scope.scpi.query(segmented_mode_query()))
    except Exception:
        return "unknown"


def query_acquisition_readouts(scope: Oscilloscope) -> dict[str, float | int | None]:
    """Read low-level acquisition readouts with capability-aware routing."""
    result: dict[str, float | int | None] = {
        "sample_rate": None,
        "acquisition_points": None,
        "record_length": None,
    }
    from .capabilities import operation_supported
    for field, operation in (("sample_rate", "sample-rate"),
                             ("acquisition_points", "acquisition-points"),
                             ("record_length", "record-length")):
        capabilities = scope.capabilities
        if operation == "record-length" and capabilities is None:
            continue
        if capabilities is not None:
            if not operation_supported(capabilities, operation):
                continue
            if operation == "record-length" and capabilities.supported_operations is None and capabilities.series != "4000X":
                continue
        result[field] = scope._query_acquisition_readout(operation)[0]
    return result


def measure_sweep_summary(measurements: Sequence[dict[str, object]]) -> dict[str, int]:
    valid_count = 0
    invalid_count = 0
    error_count = 0
    for measurement in measurements:
        if measurement.get("error") is not None or (measurement.get("post_command_status") or {}).get("is_error"):
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


def _run_sweep_measurement(
    scope: Oscilloscope,
    command: str,
    channel: int,
    item: str,
) -> dict[str, object]:
    try:
        result = scope.query_measurement(channel, item)
        system_error = scope.workflow_status()
        return {
            "command": command,
            **_measurement_result_json(result, parameters={}),
            **status_fields(_system_error_json(system_error)),
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
        system_error = scope.workflow_status()
        return {
            "command": command,
            **_measurement_result_json(result, parameters={}),
            **status_fields(_system_error_json(system_error)),
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


def _sweep_must_stop(scope: Oscilloscope, record: dict[str, object]) -> bool:
    error = record.get("error") or {}
    if error.get("type") == "VisaBackendError":
        return True
    if not operation_supported(scope.capabilities, "check-error"):
        status = record.get("post_command_status") or {}
        return bool(error) or status.get("complete") is False
    return False


def _query_system_error_best_effort(scope: Oscilloscope):
    # A failed native checkpoint must not start another destructive SESR read.
    if not operation_supported(scope.capabilities, "check-error"):
        return None
    try:
        return scope.workflow_status()
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
        **status_fields(None if system_error is None else _system_error_json(system_error)),
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
    commands = workflow_step_scpi(scope.capabilities, "acquisition-query") + workflow_step_scpi(scope.capabilities, "status")
    human.extend([f"Step: {name}", f"Command: {commands[0]}", f"Command: {commands[1]}"])
    config = scope.query_acquisition_config()
    entry = scope.workflow_status()
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
        **status_fields(_system_error_json(entry)),
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
    commands = workflow_step_scpi(scope.capabilities, "acquisition-set", type=acquisition_type, count=count)
    commands += workflow_step_scpi(scope.capabilities, "status")
    human.append(f"Step: {name}")
    human.extend(f"Command: {command}" for command in commands[:-1])
    scope.set_acquisition_type(acquisition_type)
    if count is not None:
        scope.set_acquisition_count(count)
    entry = scope.workflow_status()
    human.append(f"System error: {entry.format()}")
    return {
        "name": name,
        "operation": "set",
        "type": acquisition_type,
        "scpi_type": normalized,
        "count": count,
        "commands": commands,
        "readback": {"type": acquisition_type, "count": count},
        **status_fields(_system_error_json(entry)),
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
    system_error = step.get("post_command_status") or step.get("system_error")
    return isinstance(system_error, dict) and bool(system_error.get("is_error"))


def _system_error_from_step(step: dict[str, object]) -> dict[str, object] | None:
    system_error = step.get("post_command_status") or step.get("system_error")
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
    return status_payload(entry)


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
