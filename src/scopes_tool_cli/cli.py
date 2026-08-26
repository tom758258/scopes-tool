"""Command line interface for oscilloscope checks."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from scopes_tool_core.acquisition import (
    acquisition_count_command,
    acquisition_count_query,
    acquisition_points_query,
    acquisition_type_command,
    acquisition_type_query,
    normalize_acquisition_type,
    record_length_query,
    validate_acquisition_count,
)
from scopes_tool_core.segmented import (
    ensure_segmented_memory_supported,
    segmented_count_command,
    segmented_mode_command,
    segmented_mode_query,
    validate_segmented_count,
)
from scopes_tool_core.segmented_capture import (
    plan_segmented_capture,
)
from scopes_tool_core.cursor import (
    cursor_auto_vertical_dry_run_plan,
    cursor_auto_vertical_json,
    cursor_auto_timebase_dry_run_plan,
    cursor_auto_timebase_json,
    cursor_configure_commands,
)
from scopes_tool_core.fft import (
    fft_configure_commands,
    fft_advanced_query_commands,
    fft_query_commands,
)
from scopes_tool_core.math import (
    math_display_command,
    math_display_query,
    math_clear_command,
    math_composite_source_commands,
    math_composite_source_query_commands,
    math_operator_commands,
    math_operator_query_commands,
    math_filter_commands,
    math_filter_query_commands,
    math_transform_commands,
    math_transform_query_commands,
    math_visualization_commands,
    math_visualization_query_commands,
    math_vertical_commands,
    math_vertical_query_commands,
)
from scopes_tool_core.setup import (
    autoscale_commands,
    setup_recall_command,
    setup_save_command,
)
from scopes_tool_core.trigger_holdoff import (
    trigger_holdoff_commands,
    trigger_holdoff_query,
    validate_trigger_holdoff,
)
from scopes_tool_core.batch import (
    batch_capture_paths,
)
from scopes_tool_core.measure_logger import measure_log_paths
from scopes_tool_core.workflow import StopRequested
from scopes_tool_core.sequence import (
    SequenceRequest,
    load_sequence_document,
    plan_sequence,
)
from scopes_tool_core.triggered_measurement import (
    TriggeredMeasureLoopRequest,
    plan_triggered_measure_loop,
)
from scopes_tool_core.triggered_capture import (
    TriggeredCaptureSeriesRequest,
    plan_triggered_capture_series,
)
from scopes_tool_core.measure_until import (
    MeasureUntilRequest,
    plan_measure_until,
)
from scopes_tool_core.output_files import (
    write_json_file,
    write_json_file_best_effort,
)
from scopes_tool_core.planning import (
    AcquisitionCheckPlanRequest,
    CapturePlanRequest,
    MeasurePlanRequest,
    MeasureSweepPlanRequest,
    SmokePlanRequest,
    plan_acquisition_check,
    plan_capture,
    plan_doctor,
    plan_measure,
    plan_measure_sweep,
    plan_smoke,
)
from scopes_tool_core.capabilities import (
    ScopeCapabilities,
    capabilities_for_model_id,
)
from scopes_tool_core.channel import (
    channel_bandwidth_limit_command,
    channel_bandwidth_limit_query,
    channel_coupling_command,
    channel_coupling_query,
    channel_display_command,
    channel_display_query,
    channel_impedance_command,
    channel_impedance_query,
    channel_invert_command,
    channel_invert_query,
    channel_label_command,
    channel_label_query,
    channel_offset_command,
    channel_offset_query,
    channel_probe_skew_command,
    channel_probe_skew_query,
    channel_probe_ratio_command,
    channel_probe_ratio_query,
    channel_range_command,
    channel_range_query,
    channel_scale_command,
    channel_scale_query,
    channel_summary_queries,
    channel_units_command,
    channel_units_query,
    channel_vernier_command,
    channel_vernier_query,
    normalize_channel_coupling,
    normalize_channel_impedance,
    normalize_channel_units,
    validate_analog_channel,
    validate_channel_impedance_supported,
    validate_channel_offset,
    validate_channel_label,
    validate_channel_range,
    validate_channel_scale,
    validate_probe_skew,
    validate_probe_ratio,
)
from scopes_tool_core.cleanup import plan_cleanup
from scopes_tool_core.display import (
    display_label_command,
    display_label_query,
)
from scopes_tool_core.dvm import (
    dvm_auto_range_command,
    dvm_auto_range_query,
    dvm_current_query,
    dvm_enable_command,
    dvm_enable_query,
    dvm_mode_command,
    dvm_mode_query,
    dvm_query_commands,
    dvm_source_command,
    dvm_source_query,
)
from scopes_tool_core.errors import (
    OscilloscopeError,
    ParameterValidationError,
)
from scopes_tool_core.idn import parse_idn
from scopes_tool_core.measurements import (
    is_pair_measurement_item,
    measurement_query,
    measurement_results_query,
    normalize_measurement_item,
    pair_measurement_query,
    validate_measure_results_dump_supported,
)
from scopes_tool_core.demo import (
    demo_function_command,
    demo_function_query,
    demo_output_command,
    demo_output_query,
    demo_phase_command,
    demo_phase_query,
    demo_query_commands,
    validate_demo_phase,
)
from scopes_tool_core.wgen import (
    wgen_frequency_command,
    wgen_frequency_query,
    wgen_function_command,
    wgen_function_query,
    wgen_load_command,
    wgen_load_query,
    wgen_offset_command,
    wgen_offset_query,
    wgen_output_command,
    wgen_output_query,
    wgen_query_commands,
    wgen_voltage_command,
    wgen_voltage_query,
)
from scopes_tool_core.search import (
    search_count_query,
    search_event_command,
    search_event_query,
    search_mode_command,
    search_mode_query,
    search_state_command,
    search_state_query,
    validate_search_event,
    validate_search_mode,
)
from scopes_tool_core.serial import (
    serial_bus_query,
    serial_display_command,
    serial_display_query,
    serial_mode_command,
    serial_mode_query,
    serial_lister_data_query,
    serial_lister_display_command,
    serial_lister_display_query,
    serial_lister_query_commands,
    serial_lister_reference_command,
    serial_lister_reference_query,
    validate_serial_uart_trigger_request,
    validate_serial_i2c_trigger_request,
    validate_serial_spi_trigger_request,
    validate_serial_can_trigger_request,
    validate_serial_mode,
    validate_serial_lister_display,
    validate_serial_lister_reference,
)
from scopes_tool_core.status import (
    system_clear_status_command,
    system_opc_query,
    system_operation_status_query,
    system_options_query,
    system_standard_event_query,
    system_status_byte_query,
)
from scopes_tool_core.screenshot import (
    DEFAULT_SCREENSHOT_BACKGROUND,
    SCREENSHOT_TIMEOUT_MS,
    hardcopy_area_query,
    hardcopy_format_query,
    hardcopy_inksaver_command,
    hardcopy_inksaver_for_background,
    hardcopy_inksaver_query,
    hardcopy_layout_command,
    hardcopy_layout_query,
    hardcopy_palette_command,
    hardcopy_palette_query,
    hardcopy_screen_dump_data_query,
    screenshot_data_query,
)
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatedSignal, simulator_idn
from scopes_tool_core.simulator_config import parse_simulate_signal_spec
from scopes_tool_core.timebase import (
    timebase_position_command,
    timebase_position_query,
    timebase_scale_command,
    timebase_scale_query,
    validate_timebase_position,
    validate_timebase_scale,
)
from scopes_tool_core.trigger import (
    delay_trigger_configure_commands,
    delay_trigger_query_commands,
    edge_burst_trigger_configure_commands,
    edge_burst_trigger_query_commands,
    edge_trigger_level_command,
    edge_trigger_level_channel_command,
    edge_trigger_level_channel_query,
    edge_trigger_external_level_command,
    edge_trigger_external_level_query,
    edge_trigger_level_query,
    edge_trigger_slope_command,
    edge_trigger_slope_query,
    edge_trigger_source_command,
    edge_trigger_source_query,
    external_trigger_range_command,
    external_trigger_range_query,
    external_trigger_probe_command,
    external_trigger_probe_query,
    external_trigger_settings_query,
    external_trigger_units_command,
    external_trigger_units_query,
    force_trigger_command,
    glitch_trigger_configure_commands,
    glitch_trigger_query_commands,
    normalize_edge_slope,
    operation_condition_query,
    or_trigger_configure_commands,
    or_trigger_query_commands,
    pattern_trigger_configure_commands,
    pattern_trigger_query_commands,
    runt_trigger_configure_commands,
    runt_trigger_query_commands,
    setup_hold_trigger_configure_commands,
    setup_hold_trigger_query_commands,
    single_command,
    transition_trigger_configure_commands,
    transition_trigger_query_commands,
    trigger_mode_edge_command,
    trigger_mode_query,
    trigger_hf_reject_command,
    trigger_hf_reject_query,
    trigger_noise_reject_command,
    trigger_noise_reject_query,
    trigger_edge_coupling_command,
    trigger_edge_coupling_query,
    trigger_edge_reject_command,
    trigger_edge_reject_query,
    trigger_edge_source_command,
    trigger_edge_source_query,
    trigger_sweep_command,
    trigger_sweep_query,
    tv_trigger_configure_commands,
    tv_trigger_query_commands,
    validate_external_trigger_range,
    validate_external_trigger_probe_attenuation,
    validate_external_trigger_units,
    validate_or_trigger_pattern,
    validate_pattern_trigger_pattern,
    validate_trigger_level,
)
from scopes_tool_core.visa_backend import (
    is_asrl_resource,
    list_visa_resources,
    verify_asrl_resource_live,
)
from scopes_tool_core.waveform import (
    MultiChannelWaveformCapture,
    WORD_BYTE_ORDER,
    WORD_UNSIGNED,
    WaveformCapture,
    waveform_byte_order_command,
    validate_word_format_supported,
    validate_waveform_channels,
    validate_waveform_points,
    waveform_data_query,
    waveform_format_byte_command,
    waveform_format_word_command,
    waveform_points_command,
    waveform_preamble_query,
    waveform_source_command,
    waveform_unsigned_command,
)

from . import dispatch as cli_dispatch
from . import parser as cli_parser
from . import preflight, runtime
from .commands import (
    acquisition,
    channel_display,
    measurement_analysis,
    introspection,
    serial,
    system,
    trigger_search,
    workflows,
)
CLI_SCHEMA_VERSION = 2


def main(argv: Sequence[str] | None = None) -> int:
    """Run the `scopes-tool` command line interface."""

    parser = cli_parser._build_parser()
    args = parser.parse_args(argv)

    try:
        preflight.validate_pre_open_args(args)
    except OscilloscopeError as exc:
        if getattr(args, "json_output", False):
            payload = _json_envelope(args, ok=False, mode=_safe_mode(args))
            payload["error"] = _json_error(exc)
            _write_json(payload)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "lifecycle_command", False):
        try:
            from .worker import dispatch_lifecycle_command

            return dispatch_lifecycle_command(args)
        except OscilloscopeError as exc:
            if getattr(args, "client_json", False):
                _write_json(
                    {
                        "schema_version": CLI_SCHEMA_VERSION,
                        "timestamp_utc": _utc_timestamp(),
                        "ok": False,
                        "status": "error",
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    }
                )
            else:
                print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.command == "manifest":
        return introspection.cmd_manifest(args)

    if args.command == "capabilities":
        return introspection.cmd_capabilities(args)

    if getattr(args, "json_output", False):
        return _run_json_command(args)

    try:
        if runtime._resolve_cli_mode(args) == "dry_run":
            return _run_text_dry_run_command(args)
        return _dispatch_command(args)
    except OscilloscopeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error("missing command")
    return 2



def _dispatch_command(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    if args.command == "list-resources":
        return _cmd_list_resources(args)
    if args.command == "hardware-report":
        return _cmd_hardware_report(args)
    return cli_dispatch._dispatch_command(
        args,
        stop_requested=stop_requested,
    )




def _measure_plan_request(args: argparse.Namespace) -> MeasurePlanRequest:
    return MeasurePlanRequest(
        item=args.item,
        channel=args.channel,
        source_channel=args.source_channel,
        reference_channel=args.reference_channel,
        time_s=args.time_s,
        level=args.level,
        slope=args.slope,
        occurrence=args.occurrence,
    )




def _parse_simulate_signal_specs(
    specs: Sequence[str], capabilities: ScopeCapabilities
) -> dict[int, SimulatedSignal]:
    signals: dict[int, SimulatedSignal] = {}
    for spec in specs:
        channel, signal = _parse_simulate_signal_spec(spec)
        validate_analog_channel(channel, capabilities)
        if channel in signals:
            raise OscilloscopeError(f"duplicate --simulate-signal for CH{channel}")
        signals[channel] = signal
    return signals


def _parse_simulate_signal_spec(spec: str) -> tuple[int, SimulatedSignal]:
    return parse_simulate_signal_spec(spec)


def _parse_simulate_signal_channel(token: str) -> int:
    normalized = token.strip().upper()
    if normalized.startswith("CH"):
        normalized = normalized[2:]
    try:
        channel = int(normalized)
    except ValueError as exc:
        raise OscilloscopeError(
            "--simulate-signal channel must be CHn or a positive integer"
        ) from exc
    if channel < 1:
        raise OscilloscopeError("--simulate-signal channel must be at least 1")
    return channel


def _run_json_command(args: argparse.Namespace) -> int:
    payload, code = _execute_json_command(args)
    _write_json(payload)
    return code


def _execute_json_command(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> tuple[dict[str, object], int]:
    try:
        mode = runtime._resolve_cli_mode(args)
        if mode == "dry_run":
            payload = _dry_run_payload(args)
            return payload, 0

        runtime._JSON_RECORD = {"result": {}, "files": [], "system_error": None}
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = _dispatch_command(args, stop_requested=stop_requested)
        payload = _json_envelope(args, ok=(code == 0), mode=mode)
        _apply_json_record(payload)
        result = payload.setdefault("result", {})
        if isinstance(result, dict):
            result["human_output"] = buffer.getvalue().splitlines()
        payload["scpi"]["sent"] = runtime._backend_history()
        return payload, code
    except OscilloscopeError as exc:
        payload = _json_envelope(args, ok=False, mode=_safe_mode(args))
        _apply_json_record(payload)
        payload["error"] = _json_error(exc)
        payload["scpi"]["sent"] = runtime._backend_history()
        return payload, 3 if payload["error"].get("type") == "identity_mismatch" else 1
    finally:
        runtime._JSON_RECORD = None


def _run_text_dry_run_command(args: argparse.Namespace) -> int:
    payload = _dry_run_payload(args)
    _print_text_dry_run_payload(payload)
    return 0


def _print_text_dry_run_payload(payload: dict[str, object]) -> None:
    resource = payload.get("resource")
    if resource is not None:
        print(f"Resource: {resource}")

    idn = payload.get("idn")
    if isinstance(idn, dict):
        model = idn.get("model")
        series = idn.get("series")
        if model is not None:
            print(f"Model: {model}")
        print(f"Series: {series or 'unknown'}")

    result = payload.get("result")
    if isinstance(result, dict):
        _print_text_dry_run_summary(str(payload.get("command")), result)
        commands = result.get("commands")
        if not isinstance(commands, list):
            command = result.get("command")
            commands = [command] if isinstance(command, str) else None
    else:
        commands = None

    if not isinstance(commands, list):
        scpi = payload.get("scpi")
        if isinstance(scpi, dict):
            commands = scpi.get("planned")

    if isinstance(commands, list):
        for command in commands:
            print(f"Command: {command}")

    files = payload.get("files")
    if isinstance(files, list):
        for file_info in files:
            if isinstance(file_info, dict):
                kind = file_info.get("kind")
                path = file_info.get("path")
                if kind is not None and path is not None:
                    print(f"Planned file: {kind}: {path}")


def _print_text_dry_run_summary(command: str, result: dict[str, object]) -> None:
    if command == "measure-until":
        print(
            "Planned measure until condition: "
            f"CH{result.get('channel')} {result.get('item')} "
            f"{result.get('operator')} {result.get('threshold')}"
        )
        return
    if command == "triggered-capture-series":
        print(
            "Planned triggered capture series: "
            f"{result.get('requested_count')} cycle(s)"
        )
        return
    if command == "triggered-measure-loop":
        print(
            "Planned triggered measurement loop: "
            f"{result.get('requested_count')} cycle(s)"
        )
        return
    if command == "sequence":
        print(
            "Planned sequence: "
            f"{result.get('loop_count')} loop(s), "
            f"{result.get('step_count')} step(s), "
            f"{result.get('total_step_executions')} execution(s)"
        )
        steps = result.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    print(
                        f"Planned step {step.get('step_index')}: "
                        f"{step.get('action')} {step.get('parameters')}"
                    )
        return
    operation = result.get("operation")
    if command == "trigger-edge-burst":
        if operation == "query":
            print("Planned query: Nth Edge Burst trigger state")
            return
        source_channel = result.get("source_channel")
        slope = result.get("slope")
        count = result.get("count")
        print(
            f"Planned change: Nth Edge Burst trigger CH{source_channel}, "
            f"{slope}, count {count}"
        )
        return

    if operation == "query":
        print(f"Planned query: {command}")
    elif operation is not None:
        print(f"Planned change: {command}")
    else:
        print(f"Planned command: {command}")


def _safe_mode(args: argparse.Namespace) -> str:
    try:
        return runtime._resolve_cli_mode(args)
    except OscilloscopeError:
        return "dry_run" if getattr(args, "dry_run", False) else "simulate" if getattr(args, "simulate", False) else "live"


def _json_error(exc: OscilloscopeError) -> dict[str, object]:
    message = str(exc)
    if message.startswith("identity_mismatch: "):
        details = {"type": "identity_mismatch", "message": message}
        for item in message.removeprefix("identity_mismatch: ").split("; "):
            key, _, value = item.partition("=")
            if key == "expected_model":
                details["expected_model"] = value
            elif key == "actual_idn":
                details["actual_idn"] = value
        return details
    return {"type": type(exc).__name__, "message": message}


def _json_envelope(args: argparse.Namespace, *, ok: bool, mode: str) -> dict[str, object]:
    resource = None
    if hasattr(args, "resource"):
        resource = args.resource or (f"SIM::{args.model}::INSTR" if mode == "simulate" else f"DRY::{args.model}::INSTR" if mode == "dry_run" else os.environ.get("SCOPES_TOOL_RESOURCE"))
    idn = None
    capabilities = None
    if mode in {"simulate", "dry_run"} and hasattr(args, "model"):
        try:
            idn = _idn_json(simulator_idn(args.model))
            capabilities = runtime._capabilities_json(capabilities_for_model_id(args.model))
        except OscilloscopeError:
            idn = None
            capabilities = None
    return {
        "schema_version": CLI_SCHEMA_VERSION,
        "timestamp_utc": _utc_timestamp(),
        "ok": ok,
        "command": args.command,
        "mode": mode,
        "resource": resource,
        "backend": "Keysight simulator" if mode == "simulate" else None,
        "idn": idn,
        "capabilities": capabilities,
        "scpi": {"planned": [], "sent": []},
        "result": {},
        "files": [],
        "system_error": None,
        "error": None,
    }


def _dry_run_payload(args: argparse.Namespace) -> dict[str, object]:
    payload = _json_envelope(args, ok=True, mode="dry_run")
    capabilities = capabilities_for_model_id(args.model)
    planned, files, result = _dry_run_plan(args, capabilities)
    payload["scpi"]["planned"] = planned
    payload["files"] = files
    payload["result"] = result
    return payload


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dry_run_plan(args: argparse.Namespace, capabilities: ScopeCapabilities) -> tuple[list[str], list[dict[str, str]], dict[str, object]]:
    command = args.command
    if command == "measure-until":
        plan = plan_measure_until(
            MeasureUntilRequest(
                channel=args.channel,
                item=args.item,
                operator=args.operator,
                threshold=args.threshold,
                timeout_seconds=args.timeout_seconds,
                interval_seconds=args.interval_seconds,
                output_dir=args.output_dir,
                log_scpi=bool(args.log_scpi),
            ),
            capabilities,
        )
        return list(plan.planned_scpi), list(plan.files), plan.result
    if command == "triggered-capture-series":
        plan = plan_triggered_capture_series(
            TriggeredCaptureSeriesRequest(
                channels=args.channel,
                points=args.points,
                waveform_format=args.waveform_format,
                count=args.count,
                trigger_timeout_seconds=args.trigger_timeout_seconds,
                interval_seconds=args.interval_seconds,
                output_dir=args.output_dir,
                log_scpi=bool(args.log_scpi),
            ),
            capabilities,
        )
        return list(plan.planned_scpi), list(plan.files), plan.result
    if command == "triggered-measure-loop":
        plan = plan_triggered_measure_loop(
            TriggeredMeasureLoopRequest(
                channels=args.channel,
                items=args.items,
                pairs=tuple(args.pair),
                pair_items=args.pair_items,
                count=args.count,
                trigger_timeout_seconds=args.trigger_timeout_seconds,
                interval_seconds=args.interval_seconds,
                output_dir=args.output_dir,
                log_scpi=bool(args.log_scpi),
            ),
            capabilities,
        )
        return list(plan.planned_scpi), list(plan.files), plan.result
    if command == "sequence":
        request = SequenceRequest(
            load_sequence_document(args.sequence_file),
            output_dir=args.output_dir,
            log_scpi=bool(args.log_scpi),
        )
        plan = plan_sequence(request, capabilities)
        return list(plan.planned_scpi), list(plan.files), plan.result
    if command == "capture":
        trigger_wait = workflows._capture_trigger_wait_config(args)
        plan = plan_capture(
            CapturePlanRequest(
                channels=args.channel,
                points=args.points,
                waveform_format=args.waveform_format,
                csv_path=args.csv_path,
                meta_path=args.meta_path,
                plot_path=args.plot_path,
            ),
            capabilities,
        )
        planned = list(plan.planned_scpi)
        result = dict(plan.result)
        if trigger_wait is not None:
            wait_scpi = [single_command(), operation_condition_query()]
            if trigger_wait.force_on_timeout:
                wait_scpi.extend([force_trigger_command(), operation_condition_query()])
            planned = wait_scpi + planned
            result["trigger"] = {
                "wait_enabled": True,
                "arm_command": single_command(),
                "poll_source": "operation_condition",
                "poll_command": operation_condition_query(),
                "timeout_ms": trigger_wait.timeout_ms,
                "poll_interval_ms": trigger_wait.poll_interval_ms,
                "force_on_timeout": trigger_wait.force_on_timeout,
                "force_command": force_trigger_command(),
                "outcome": "unknown",
                "forced": False,
                "timed_out": False,
                "poll_count": 0,
                "elapsed_ms": 0.0,
                "condition_values": [],
                "raw_values": [],
                "capture_allowed": False,
                "capture_block_reason": "dry_run",
                "error": None,
            }
        return planned, list(plan.files), result
    if command == "doctor":
        plan = plan_doctor(capabilities)
        return list(plan.planned_scpi), list(plan.files), plan.result
    if command == "channel-summary":
        return ["*IDN?", *channel_summary_queries(capabilities)], [], {
            "channels": [],
        }
    if command == "cleanup":
        plan = plan_cleanup(args.profile, capabilities)
        return ["*IDN?", *plan.commands], [], plan.to_json()
    if command == "measure":
        plan = plan_measure(_measure_plan_request(args), capabilities)
        return list(plan.planned_scpi), list(plan.files), plan.result
    if command == "measure-results":
        validate_measure_results_dump_supported(capabilities)
        target = measurement_results_query()
        return [target], [], {
            "operation": "query",
            "command": target,
            "raw": "",
            "items": [],
            "statistics_items": [],
        }
    if command == "measure-sweep":
        plan = plan_measure_sweep(
            MeasureSweepPlanRequest(
                channels=args.channel,
                items=args.items,
                pairs=tuple(args.pair),
                pair_items=args.pair_items,
            ),
            capabilities,
        )
        return list(plan.planned_scpi), list(plan.files), plan.result
    if command == "smoke":
        plan = plan_smoke(SmokePlanRequest(output_dir=args.output_dir), capabilities)
        return list(plan.planned_scpi), list(plan.files), plan.result
    if command == "acquisition-check":
        plan = plan_acquisition_check(
            AcquisitionCheckPlanRequest(
                output_dir=args.output_dir,
                average_count=args.average_count,
                check_only=bool(getattr(args, "check_only", False)),
                stop_on_error=bool(getattr(args, "stop_on_error", False)),
                restore_type=bool(getattr(args, "restore_type", False)),
            )
        )
        return list(plan.planned_scpi), list(plan.files), plan.result
    if command == "identify":
        return ["*IDN?"], [], {
            "idn": _idn_json(simulator_idn(args.model)),
            "capabilities": runtime._capabilities_json(capabilities),
            "backend": None,
            "timeout_ms": None,
        }
    if command == "check-error":
        count = args.max_reads if args.drain else 1
        return [":SYSTem:ERRor?"] * count, [], {"drain": bool(args.drain), "max_reads": count, "entries": []}
    if command == "system-clear-status":
        target = system_clear_status_command()
        return [target, ":SYSTem:ERRor?"], [], {
            "operation": "clear",
            "command": target,
            "cleared": True,
        }
    system_queries = {
        "system-opc": system_opc_query,
        "system-status-byte": system_status_byte_query,
        "system-standard-event": system_standard_event_query,
        "system-operation-status": system_operation_status_query,
        "system-options": system_options_query,
    }
    if command in system_queries:
        target = system_queries[command]()
        return [target, ":SYSTem:ERRor?"], [], {
            "operation": "query",
            "command": target,
        }
    if command in system._CONTROL_COMMANDS:
        action, scpi = system._CONTROL_COMMANDS[command]
        return [scpi, ":SYSTem:ERRor?"], [], {"action": action, "command": scpi}
    if command == "channel-display":
        channel = validate_analog_channel(args.channel, capabilities)
        query = args.display_action == "query"
        enabled = None if query else args.display_action == "on"
        planned = [channel_display_query(channel)] if query else [channel_display_command(channel, enabled)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if query else "set", "command": planned[0], "display": enabled}
    if command == "channel-label":
        channel = validate_analog_channel(args.channel, capabilities)
        text = None if args.label_query else validate_channel_label(args.label_text, capabilities)
        planned = [channel_label_query(channel)] if args.label_query else [channel_label_command(channel, text, capabilities)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if args.label_query else "set", "command": planned[0], "text": text}
    if command == "channel-scale":
        channel = validate_analog_channel(args.channel, capabilities)
        scale = None if args.scale_query else validate_channel_scale(args.scale_value)
        planned = [channel_scale_query(channel)] if args.scale_query else [channel_scale_command(channel, scale)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if args.scale_query else "set", "command": planned[0], "volts_per_division": scale}
    if command == "channel-offset":
        channel = validate_analog_channel(args.channel, capabilities)
        offset = None if args.offset_query else validate_channel_offset(args.offset_value)
        planned = [channel_offset_query(channel)] if args.offset_query else [channel_offset_command(channel, offset)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if args.offset_query else "set", "command": planned[0], "volts": offset}
    if command == "channel-coupling":
        channel = validate_analog_channel(args.channel, capabilities)
        coupling = None if args.coupling_query else normalize_channel_coupling(args.coupling_value)
        planned = [channel_coupling_query(channel)] if args.coupling_query else [channel_coupling_command(channel, coupling)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if args.coupling_query else "set", "command": planned[0], "coupling": coupling}
    if command == "channel-probe":
        channel = validate_analog_channel(args.channel, capabilities)
        ratio = None if args.probe_query else validate_probe_ratio(args.probe_ratio)
        planned = [channel_probe_ratio_query(channel)] if args.probe_query else [channel_probe_ratio_command(channel, ratio)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if args.probe_query else "set", "command": planned[0], "probe_ratio": ratio}
    if command == "channel-bandwidth-limit":
        channel = validate_analog_channel(args.channel, capabilities)
        query = args.bandwidth_action == "query"
        enabled = None if query else args.bandwidth_action == "on"
        planned = [channel_bandwidth_limit_query(channel)] if query else [channel_bandwidth_limit_command(channel, enabled)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if query else "set", "command": planned[0], "bandwidth_limit": enabled}
    if command == "channel-impedance":
        channel = validate_analog_channel(args.channel, capabilities)
        impedance = None if args.impedance_query else normalize_channel_impedance(args.impedance_value)
        if impedance is not None:
            validate_channel_impedance_supported(impedance, capabilities)
        planned = [channel_impedance_query(channel)] if args.impedance_query else [channel_impedance_command(channel, impedance)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if args.impedance_query else "set", "command": planned[0], "impedance": impedance}
    if command == "channel-invert":
        channel = validate_analog_channel(args.channel, capabilities)
        query = args.invert_action == "query"
        enabled = None if query else args.invert_action == "on"
        planned = [channel_invert_query(channel)] if query else [channel_invert_command(channel, enabled)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if query else "set", "command": planned[0], "invert": enabled}
    if command == "channel-range":
        channel = validate_analog_channel(args.channel, capabilities)
        range_volts = None if args.range_query else validate_channel_range(args.range_value)
        planned = [channel_range_query(channel)] if args.range_query else [channel_range_command(channel, range_volts)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if args.range_query else "set", "command": planned[0], "range_volts": range_volts}
    if command == "channel-units":
        channel = validate_analog_channel(args.channel, capabilities)
        units = None if args.units_query else normalize_channel_units(args.units_value)
        planned = [channel_units_query(channel)] if args.units_query else [channel_units_command(channel, units)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if args.units_query else "set", "command": planned[0], "units": units}
    if command == "channel-vernier":
        channel = validate_analog_channel(args.channel, capabilities)
        query = args.vernier_action == "query"
        enabled = None if query else args.vernier_action == "on"
        planned = [channel_vernier_query(channel)] if query else [channel_vernier_command(channel, enabled)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if query else "set", "command": planned[0], "vernier": enabled}
    if command == "channel-probe-skew":
        channel = validate_analog_channel(args.channel, capabilities)
        skew = None if args.probe_skew_query else validate_probe_skew(args.probe_skew_seconds)
        planned = [channel_probe_skew_query(channel)] if args.probe_skew_query else [channel_probe_skew_command(channel, skew)]
        return planned + [":SYSTem:ERRor?"], [], {"channel": channel, "operation": "query" if args.probe_skew_query else "set", "command": planned[0], "probe_skew_seconds": skew}
    if command == "display-label":
        query = args.display_label_action == "query"
        enabled = None if query else args.display_label_action == "on"
        planned = [display_label_query()] if query else [display_label_command(enabled)]
        return planned + [":SYSTem:ERRor?"], [], {"operation": "query" if query else "set", "command": planned[0], "display_label": enabled}
    if command in {
        "display-clear",
        "display-persistence",
        "display-intensity",
        "display-vectors",
    }:
        target, result = channel_display._display_common_plan(args)
        return ["*IDN?", target, ":SYSTem:ERRor?"], [], result
    if command in {
        "measure-clear",
        "measure-show",
        "measure-source",
        "measure-window",
    }:
        commands, result = measurement_analysis._measurement_control_plan(args, capabilities)
        return ["*IDN?", *commands, ":SYSTem:ERRor?"], [], result
    if command in {
        "reference-save",
        "reference-display",
        "reference-label",
        "reference-clear",
        "reference-query",
    }:
        commands, result = measurement_analysis._reference_waveform_plan(args, capabilities)
        return ["*IDN?", *commands, ":SYSTem:ERRor?"], [], result
    if command == "dvm-enable":
        target = dvm_enable_query() if args.query else dvm_enable_command(args.enabled)
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(enabled=args.enabled, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "dvm-source":
        channel = None if args.query else validate_analog_channel(args.channel, capabilities)
        target = dvm_source_query() if args.query else dvm_source_command(
            channel, capabilities=capabilities
        )
        result = {"operation": "query" if args.query else "configure", "command": target}
        if channel is not None:
            result.update(source_channel=channel, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "dvm-mode":
        target = dvm_mode_query() if args.query else dvm_mode_command(args.mode)
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(mode=args.mode, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "dvm-auto-range":
        target = dvm_auto_range_query() if args.query else dvm_auto_range_command(args.enabled)
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(auto_range_enabled=args.enabled, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "dvm-current":
        target = dvm_current_query()
        return [target, ":SYSTem:ERRor?"], [], {"operation": "query", "command": target}
    if command == "dvm-query":
        commands = dvm_query_commands()
        return [*commands, ":SYSTem:ERRor?"], [], {
            "operation": "query",
            "commands": commands,
        }
    if command == "demo-query":
        commands = demo_query_commands()
        return [*commands, ":SYSTem:ERRor?"], [], {
            "operation": "query",
            "commands": commands,
        }
    if command == "demo-output":
        target = demo_output_query() if args.query else demo_output_command(args.enabled)
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(enabled=args.enabled, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "demo-function":
        target = demo_function_query() if args.query else demo_function_command(
            args.function, capabilities=capabilities
        )
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(function=args.function, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "demo-phase":
        target = demo_phase_query() if args.query else demo_phase_command(args.degrees)
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(degrees=validate_demo_phase(args.degrees), state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "wgen-query":
        commands = wgen_query_commands(capabilities)
        return [*commands, ":SYSTem:ERRor?"], [], {
            "operation": "query",
            "commands": commands,
        }
    if command == "wgen-output":
        target = (
            wgen_output_query(capabilities)
            if args.query
            else wgen_output_command(args.enabled, capabilities)
        )
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(enabled=args.enabled, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "wgen-function":
        target = (
            wgen_function_query(capabilities)
            if args.query
            else wgen_function_command(args.function, capabilities)
        )
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(function=args.function, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "wgen-frequency":
        target = (
            wgen_frequency_query(capabilities)
            if args.query
            else wgen_frequency_command(args.hz, capabilities)
        )
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(frequency_hz=args.hz, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "wgen-voltage":
        target = (
            wgen_voltage_query(capabilities)
            if args.query
            else wgen_voltage_command(args.amplitude, capabilities)
        )
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(amplitude_volts=args.amplitude, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "wgen-offset":
        target = (
            wgen_offset_query(capabilities)
            if args.query
            else wgen_offset_command(args.volts, capabilities)
        )
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(offset_volts=args.volts, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "wgen-load":
        target = (
            wgen_load_query(capabilities)
            if args.query
            else wgen_load_command(args.load, capabilities)
        )
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(load=args.load, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "serial-query":
        target = serial_bus_query(args.bus)
        return [target, ":SYSTem:ERRor?"], [], {
            "operation": "query",
            "command": target,
            "bus": args.bus,
        }
    if command == "serial-mode":
        target = (
            serial_mode_query(args.bus)
            if args.query
            else serial_mode_command(
                args.bus, validate_serial_mode(args.mode, capabilities)
            )
        )
        result = {
            "operation": "query" if args.query else "configure",
            "command": target,
            "bus": args.bus,
        }
        if not args.query:
            result.update(mode=args.mode, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "serial-display":
        target = (
            serial_display_query(args.bus)
            if args.query
            else serial_display_command(args.bus, args.enabled)
        )
        result = {
            "operation": "query" if args.query else "configure",
            "command": target,
            "bus": args.bus,
        }
        if not args.query:
            result.update(enabled=args.enabled, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "serial-lister-query":
        commands = list(serial_lister_query_commands().values())
        return [*commands, ":SYSTem:ERRor?"], [], {
            "operation": "query",
            "commands": commands,
        }
    if command == "serial-lister-display":
        target = (
            serial_lister_display_query()
            if args.query
            else serial_lister_display_command(
                validate_serial_lister_display(args.selection, capabilities)
            )
        )
        result = {
            "operation": "query" if args.query else "configure",
            "command": target,
        }
        if not args.query:
            result.update(display=args.selection, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "serial-lister-reference":
        target = (
            serial_lister_reference_query()
            if args.query
            else serial_lister_reference_command(
                validate_serial_lister_reference(args.reference, capabilities)
            )
        )
        result = {
            "operation": "query" if args.query else "configure",
            "command": target,
        }
        if not args.query:
            result.update(reference=args.reference, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "serial-lister-export":
        output_path = serial._serial_lister_output_path(args)
        target = serial_lister_data_query()
        return [target, ":SYSTem:ERRor?"], [
            {"kind": "csv", "path": str(output_path)}
        ], {
            "operation": "export",
            "command": target,
            "output_path": str(output_path),
            "bytes_written": None,
        }
    if command == "serial-trigger-uart":
        bus, trigger_type, data, qualifier = validate_serial_uart_trigger_request(
            args.bus,
            query=args.query,
            type=args.type,
            data=args.data,
            qualifier=args.qualifier,
            capabilities=capabilities,
        )
        if args.query:
            commands = [
                serial_mode_query(bus),
                trigger_mode_query(),
            ]
            result = {
                "operation": "query",
                "commands": commands,
                "protocol": "uart",
                "bus": bus,
            }
        else:
            commands = serial._serial_uart_trigger_commands(
                args,
                mode="uart",
                trigger_type=trigger_type,
            )
            result = {
                "operation": "configure",
                "commands": commands,
                "protocol": "uart",
                "bus": bus,
                "mode": "uart",
                "raw_mode": None,
                "selected": True,
                "trigger_mode": f"serial{bus}",
                "raw_trigger_mode": None,
                "type": trigger_type,
                "raw_type": None,
                "data": data,
                "raw_data": None,
                "qualifier": qualifier,
                "raw_qualifier": None,
                "state_changing": True,
            }
        return [*commands, ":SYSTem:ERRor?"], [], result
    if command == "serial-trigger-i2c":
        bus, trigger_type, address, data, data2, qualifier = validate_serial_i2c_trigger_request(
            args.bus, query=args.query, type=args.type, address=args.address,
            data=args.data, data2=args.data2, qualifier=args.qualifier,
            capabilities=capabilities,
        )
        if args.query:
            commands = [serial_mode_query(bus), trigger_mode_query()]
            result = {"operation": "query", "commands": commands, "protocol": "i2c", "bus": bus}
        else:
            commands = serial._serial_i2c_trigger_commands(args, trigger_type=trigger_type)
            result = {
                "operation": "configure", "commands": commands, "protocol": "i2c", "bus": bus,
                "mode": "i2c", "raw_mode": None, "selected": True,
                "trigger_mode": f"serial{bus}", "raw_trigger_mode": None,
                "type": trigger_type, "raw_type": None,
                "address": address, "raw_address": None,
                "data": data, "raw_data": None,
                "data2": data2, "raw_data2": None,
                "qualifier": qualifier, "raw_qualifier": None,
                "state_changing": True,
            }
        return [*commands, ":SYSTem:ERRor?"], [], result
    if command == "serial-trigger-spi":
        bus, trigger_type, width, data = validate_serial_spi_trigger_request(
            args.bus, query=args.query, type=args.type, width=args.width, data=args.data,
            capabilities=capabilities,
        )
        if args.query:
            commands = [serial_mode_query(bus), trigger_mode_query()]
            result = {"operation": "query", "commands": commands, "protocol": "spi", "bus": bus}
        else:
            commands = serial._serial_spi_trigger_commands(args, trigger_type=trigger_type)
            result = {
                "operation": "configure", "commands": commands, "protocol": "spi", "bus": bus,
                "mode": "spi", "raw_mode": None, "selected": True,
                "trigger_mode": f"serial{bus}", "raw_trigger_mode": None,
                "type": trigger_type, "raw_type": None,
                "width": width, "raw_width": None, "data": data, "raw_data": None,
                "state_changing": True,
            }
        return [*commands, ":SYSTem:ERRor?"], [], result
    if command == "serial-trigger-can":
        bus, trigger_type, id_value, id_mode, data, data_length = validate_serial_can_trigger_request(
            args.bus, query=args.query, type=args.type, id=args.id, id_mode=args.id_mode,
            data=args.data, data_length=args.data_length, capabilities=capabilities,
        )
        if args.query:
            commands = [serial_mode_query(bus), trigger_mode_query()]
            result = {"operation": "query", "commands": commands, "protocol": "can", "bus": bus}
        else:
            commands = serial._serial_can_trigger_commands(args, trigger_type=trigger_type)
            result = {
                "operation": "configure", "commands": commands, "protocol": "can", "bus": bus,
                "mode": "can", "raw_mode": None, "selected": True,
                "trigger_mode": f"serial{bus}", "raw_trigger_mode": None,
                "type": trigger_type, "raw_type": None,
                "id": id_value, "raw_id": None, "id_mode": id_mode, "raw_id_mode": None,
                "data": data, "raw_data": None, "data_length": data_length,
                "raw_data_length": None, "state_changing": True,
            }
        return [*commands, ":SYSTem:ERRor?"], [], result
    if command in {"serial-uart", "serial-i2c", "serial-spi", "serial-can"}:
        commands = serial._serial_protocol_commands(args, capabilities)
        result = {
            "operation": "query" if args.query else "configure",
            "commands": commands,
            "bus": args.bus,
        }
        if not args.query:
            result.update(
                preflight._serial_cli_values(
                    capabilities,
                    protocol=command,
                    **serial._serial_protocol_settings(args),
                ),
                state_changing=True,
            )
        return [*commands, ":SYSTem:ERRor?"], [], result
    if command == "search-state":
        target = search_state_query() if args.query else search_state_command(args.enabled)
        result = {"operation": "query" if args.query else "configure", "command": target}
        if not args.query:
            result.update(enabled=args.enabled, state_changing=True)
        return [target, ":SYSTem:ERRor?"], [], result
    if command == "search-mode":
        if args.query:
            target = search_mode_query()
            return [target, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": target,
            }
        mode = validate_search_mode(args.mode, capabilities)
        commands = [search_state_command(True), search_mode_command(mode)]
        return [*commands, ":SYSTem:ERRor?"], [], {
            "operation": "configure",
            "commands": commands,
            "mode": mode,
            "enabled": True,
            "state_changing": True,
        }
    if command == "search-count":
        target = search_count_query()
        return [target, ":SYSTem:ERRor?"], [], {
            "operation": "query",
            "command": target,
        }
    if command == "search-event":
        if capabilities is not None and not capabilities.supports_search_event_navigation:
            raise ParameterValidationError(
                "Search event navigation is not supported by the selected model profile."
            )
        if args.query:
            target = search_event_query()
            return [target, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": target,
            }
        canonical_event = validate_search_event(args.event)
        target = search_event_command(canonical_event)
        return [target, ":SYSTem:ERRor?"], [], {
            "operation": "configure",
            "command": target,
            "event": canonical_event,
            "state_changing": True,
        }
    if command in {
        "serial-search-uart",
        "serial-search-i2c",
        "serial-search-spi",
        "serial-search-can",
    }:
        return trigger_search._dry_run_serial_search_plan(args, capabilities)
    if command in {
        "save-pwd",
        "save-filename",
        "save-image-format",
        "save-image-palette",
        "save-image-ink-saver",
        "save-image-factors",
        "save-image",
        "save-waveform-format",
        "save-waveform-length",
        "save-waveform-length-max",
        "save-waveform",
    }:
        target, result, waits_for_completion = workflows._save_export_plan(args)
        planned = ["*IDN?", target]
        if waits_for_completion:
            planned.append(system_opc_query())
        if command == "save-waveform" and capabilities.series == "4000X":
            planned.append(operation_condition_query())
        planned.append(":SYSTem:ERRor?")
        return planned, [], result
    if command == "annotation":
        operation, commands, result = channel_display._annotation_plan(args, capabilities)
        result["operation"] = operation
        return commands + [":SYSTem:ERRor?"], [], result
    if command == "timebase-scale":
        scale = None if args.timebase_scale_query else validate_timebase_scale(args.timebase_scale_value)
        planned = [timebase_scale_query()] if args.timebase_scale_query else [timebase_scale_command(scale)]
        return planned + [":SYSTem:ERRor?"], [], {"operation": "query" if args.timebase_scale_query else "set", "command": planned[0], "seconds_per_division": scale}
    if command == "timebase-position":
        position = None if args.timebase_position_query else validate_timebase_position(args.timebase_position_value)
        planned = [timebase_position_query()] if args.timebase_position_query else [timebase_position_command(position)]
        return planned + [":SYSTem:ERRor?"], [], {"operation": "query" if args.timebase_position_query else "set", "command": planned[0], "position_seconds": position}
    if command == "trigger-edge":
        if args.edge_query:
            commands = [edge_trigger_source_query(), edge_trigger_level_query(), edge_trigger_slope_query()]
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        if args.source_channel is None or args.level is None or args.slope is None:
            raise OscilloscopeError("trigger-edge configure requires --source-channel, --level, and --slope")
        channel = validate_analog_channel(args.source_channel, capabilities)
        slope = normalize_edge_slope(args.slope)
        commands = [trigger_mode_edge_command(), edge_trigger_source_command(channel), edge_trigger_level_command(args.level), edge_trigger_slope_command(slope)]
        return commands + [":SYSTem:ERRor?"], [], {"operation": "set", "commands": commands, "source_channel": channel, "level_volts": args.level, "slope": slope}
    if command == "trigger-edge-source":
        if args.trigger_edge_source_query:
            command_text = trigger_edge_source_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        if args.source_channel is not None:
            channel = validate_analog_channel(args.source_channel, capabilities)
            command_text = trigger_edge_source_command(
                "analog-channel",
                source_channel=channel,
                capabilities=capabilities,
            )
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "set",
                "command": command_text,
                "source": "analog-channel",
                "source_channel": channel,
            }
        command_text = trigger_edge_source_command(args.source)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "set",
            "command": command_text,
            "source": args.source,
            "source_channel": None,
        }
    if command == "trigger-edge-slope":
        if args.trigger_edge_slope_query:
            command_text = edge_trigger_slope_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        slope = normalize_edge_slope(args.slope)
        command_text = edge_trigger_slope_command(slope)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "set",
            "command": command_text,
            "slope": args.slope,
        }
    if command == "trigger-edge-level":
        channel = validate_analog_channel(args.source_channel, capabilities)
        if args.trigger_edge_level_query:
            command_text = edge_trigger_level_channel_query(channel)
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
                "source_channel": channel,
            }
        level_volts = validate_trigger_level(args.level_volts)
        command_text = edge_trigger_level_channel_command(channel, level_volts)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "set",
            "command": command_text,
            "source_channel": channel,
            "level_volts": level_volts,
        }
    if command == "external-trigger-range":
        if args.external_trigger_range_query:
            command_text = external_trigger_range_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        range_volts = validate_external_trigger_range(args.range_volts)
        command_text = external_trigger_range_command(range_volts)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "set",
            "command": command_text,
            "range_volts": range_volts,
        }
    if command == "trigger-edge-external-level":
        if args.trigger_edge_external_level_query:
            command_text = edge_trigger_external_level_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        level_volts = validate_trigger_level(args.level_volts)
        command_text = edge_trigger_external_level_command(level_volts)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "set",
            "command": command_text,
            "level_volts": level_volts,
        }
    if command == "external-trigger-probe":
        if args.external_trigger_probe_query:
            command_text = external_trigger_probe_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        attenuation = validate_external_trigger_probe_attenuation(args.attenuation)
        command_text = external_trigger_probe_command(attenuation)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "set",
            "command": command_text,
            "attenuation": attenuation,
        }
    if command == "external-trigger-units":
        if args.external_trigger_units_query:
            command_text = external_trigger_units_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        units = validate_external_trigger_units(args.units)
        command_text = external_trigger_units_command(units)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "set",
            "command": command_text,
            "units": units,
        }
    if command == "external-trigger-settings":
        command_text = external_trigger_settings_query()
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "query",
            "command": command_text,
        }
    if command == "trigger-sweep":
        if args.trigger_sweep_query:
            command_text = trigger_sweep_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        command_text = trigger_sweep_command(args.mode)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "configure",
            "command": command_text,
            "mode": args.mode,
            "state_changing": True,
        }
    if command == "trigger-noise-reject":
        if args.trigger_noise_reject_query:
            command_text = trigger_noise_reject_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        command_text = trigger_noise_reject_command(args.enabled)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "configure",
            "command": command_text,
            "enabled": args.enabled,
            "state_changing": True,
        }
    if command == "trigger-hf-reject":
        if args.trigger_hf_reject_query:
            command_text = trigger_hf_reject_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        command_text = trigger_hf_reject_command(args.enabled)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "configure",
            "command": command_text,
            "enabled": args.enabled,
            "state_changing": True,
        }
    if command == "trigger-edge-coupling":
        if args.trigger_edge_coupling_query:
            command_text = trigger_edge_coupling_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        command_text = trigger_edge_coupling_command(args.coupling)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "set",
            "command": command_text,
            "coupling": args.coupling,
        }
    if command == "trigger-edge-reject":
        if args.trigger_edge_reject_query:
            command_text = trigger_edge_reject_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        command_text = trigger_edge_reject_command(args.reject)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "set",
            "command": command_text,
            "reject": args.reject,
        }
    if command == "trigger-pulse-width":
        if args.glitch_query:
            commands = glitch_trigger_query_commands()
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        commands = glitch_trigger_configure_commands(
            channel=args.channel,
            polarity=args.polarity,
            qualifier=args.qualifier,
            capabilities=capabilities,
            time_seconds=args.time_seconds,
            min_time_seconds=args.min_time_seconds,
            max_time_seconds=args.max_time_seconds,
            level_volts=args.level_volts,
        )
        result: dict[str, object] = {
            "operation": "set",
            "commands": commands,
            "channel": args.channel,
            "source": f"CHANnel{args.channel}",
            "polarity": args.polarity,
            "qualifier": args.qualifier,
            "level_volts": args.level_volts,
            "state_changing": True,
        }
        if args.qualifier in {"greater-than", "less-than"}:
            result["time_seconds"] = args.time_seconds
        else:
            result["min_time_seconds"] = args.min_time_seconds
            result["max_time_seconds"] = args.max_time_seconds
        return commands + [":SYSTem:ERRor?"], [], result
    if command == "trigger-runt":
        if args.runt_query:
            commands = runt_trigger_query_commands()
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        commands = runt_trigger_configure_commands(
            channel=args.channel,
            polarity=args.polarity,
            qualifier=args.qualifier,
            capabilities=capabilities,
            time_seconds=args.time_seconds,
            low_level_volts=args.low_level_volts,
            high_level_volts=args.high_level_volts,
        )
        result: dict[str, object] = {
            "operation": "set",
            "commands": commands,
            "channel": args.channel,
            "source": f"CHANnel{args.channel}",
            "polarity": args.polarity,
            "qualifier": args.qualifier,
            "time_seconds": args.time_seconds,
            "low_level_volts": args.low_level_volts,
            "high_level_volts": args.high_level_volts,
            "state_changing": True,
        }
        return commands + [":SYSTem:ERRor?"], [], result
    if command == "trigger-transition":
        if args.transition_query:
            commands = transition_trigger_query_commands()
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        commands = transition_trigger_configure_commands(
            channel=args.channel,
            slope=args.slope,
            qualifier=args.qualifier,
            capabilities=capabilities,
            time_seconds=args.time_seconds,
            low_level_volts=args.low_level_volts,
            high_level_volts=args.high_level_volts,
        )
        result: dict[str, object] = {
            "operation": "set",
            "commands": commands,
            "channel": args.channel,
            "source": f"CHANnel{args.channel}",
            "slope": args.slope,
            "qualifier": args.qualifier,
            "time_seconds": args.time_seconds,
            "low_level_volts": args.low_level_volts,
            "high_level_volts": args.high_level_volts,
            "state_changing": True,
        }
        return commands + [":SYSTem:ERRor?"], [], result
    if command == "trigger-delay":
        if args.delay_query:
            commands = delay_trigger_query_commands()
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        commands = delay_trigger_configure_commands(
            arm_channel=args.arm_channel,
            arm_slope=args.arm_slope,
            trigger_channel=args.trigger_channel,
            trigger_slope=args.trigger_slope,
            time_seconds=args.time_seconds,
            count=args.count,
            capabilities=capabilities,
        )
        result: dict[str, object] = {
            "operation": "set",
            "commands": commands,
            "arm_channel": args.arm_channel,
            "arm_source": f"CHANnel{args.arm_channel}",
            "arm_slope": args.arm_slope,
            "trigger_channel": args.trigger_channel,
            "trigger_source": f"CHANnel{args.trigger_channel}",
            "trigger_slope": args.trigger_slope,
            "time_seconds": args.time_seconds,
            "count": args.count,
            "state_changing": True,
        }
        return commands + [":SYSTem:ERRor?"], [], result
    if command == "trigger-setup-hold":
        if args.setup_hold_query:
            commands = setup_hold_trigger_query_commands()
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        commands = setup_hold_trigger_configure_commands(
            clock_channel=args.clock_channel,
            data_channel=args.data_channel,
            slope=args.slope,
            setup_time_seconds=args.setup_time,
            hold_time_seconds=args.hold_time,
            capabilities=capabilities,
        )
        result: dict[str, object] = {
            "operation": "configure",
            "mode": "setup-hold",
            "commands": commands,
            "clock_source": f"CHANnel{args.clock_channel}",
            "clock_channel": args.clock_channel,
            "clock_source_kind": "channel",
            "data_source": f"CHANnel{args.data_channel}",
            "data_channel": args.data_channel,
            "data_source_kind": "channel",
            "slope": args.slope,
            "setup_time_seconds": args.setup_time,
            "hold_time_seconds": args.hold_time,
            "state_changing": True,
        }
        return commands + [":SYSTem:ERRor?"], [], result
    if command == "trigger-edge-burst":
        if args.edge_burst_query:
            commands = edge_burst_trigger_query_commands(include_level_for_channel=1)
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        commands = edge_burst_trigger_configure_commands(
            source_channel=args.source_channel,
            slope=args.slope,
            count=args.count,
            idle_time=args.idle_time,
            capabilities=capabilities,
            level_volts=args.level_volts,
        )
        result: dict[str, object] = {
            "operation": "configure",
            "mode": "edge-burst",
            "commands": commands,
            "source_channel": args.source_channel,
            "source": f"CHANnel{args.source_channel}",
            "slope": args.slope,
            "count": args.count,
            "idle_time": args.idle_time,
            "state_changing": True,
        }
        if args.level_volts is not None:
            result["level_volts"] = args.level_volts
        return commands + [":SYSTem:ERRor?"], [], result
    if command == "trigger-tv":
        if args.tv_query:
            commands = tv_trigger_query_commands()
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        commands = tv_trigger_configure_commands(
            source_channel=args.source_channel,
            standard=args.standard,
            mode=args.mode,
            polarity=args.polarity,
            capabilities=capabilities,
            line=args.line,
        )
        result: dict[str, object] = {
            "operation": "configure",
            "mode": "tv",
            "commands": commands,
            "source_channel": args.source_channel,
            "source_raw": f"CHANnel{args.source_channel}",
            "standard": args.standard,
            "tv_mode": args.mode,
            "polarity": args.polarity,
            "line": args.line,
            "state_changing": True,
        }
        return commands + [":SYSTem:ERRor?"], [], result
    if command == "trigger-pattern":
        if args.pattern_query:
            commands = pattern_trigger_query_commands()
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        normalized = validate_pattern_trigger_pattern(args.pattern, capabilities)
        commands = pattern_trigger_configure_commands(
            pattern=args.pattern,
            capabilities=capabilities,
        )
        return commands + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "commands": commands,
            "mode": "pattern",
            "format": "ascii",
            "pattern": normalized,
            "qualifier": "entered",
            "state_changing": True,
        }
    if command == "trigger-or":
        if args.or_query:
            commands = or_trigger_query_commands()
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        normalized = validate_or_trigger_pattern(args.pattern, capabilities)
        commands = or_trigger_configure_commands(
            pattern=args.pattern,
            capabilities=capabilities,
        )
        return commands + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "commands": commands,
            "mode": "or",
            "pattern": normalized,
            "raw_pattern": normalized,
            "state_changing": True,
        }
    if command == "cursor":
        if args.cursor_query:
            commands = measurement_analysis._cursor_query_commands()
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        if args.cursor_off:
            return [":MARKer:MODE OFF", ":SYSTem:ERRor?"], [], {"operation": "off", "command": ":MARKer:MODE OFF"}
        if args.source_channel is None or args.x2 is None:
            raise OscilloscopeError("cursor configure requires --source-channel, --x1, and --x2")
        channel = validate_analog_channel(args.source_channel, capabilities)
        commands = cursor_configure_commands(
            channel,
            args.x1,
            args.x2,
            y1_volts=args.y1,
            y2_volts=args.y2,
            capabilities=capabilities,
        )
        auto_timebase = (
            cursor_auto_timebase_dry_run_plan()
            if getattr(args, "auto_timebase", False)
            else None
        )
        auto_vertical = (
            cursor_auto_vertical_dry_run_plan(channel)
            if getattr(args, "auto_vertical", False)
            else None
        )
        planned = (
            (list(auto_timebase.commands) if auto_timebase is not None else [])
            + (list(auto_vertical.commands) if auto_vertical is not None else [])
            + commands
        )
        result = {
            "operation": "set",
            "commands": commands,
            "source_channel": channel,
            "x1_seconds": args.x1,
            "x2_seconds": args.x2,
            "y1_volts": args.y1,
            "y2_volts": args.y2,
        }
        if auto_timebase is not None:
            result["auto_timebase"] = cursor_auto_timebase_json(auto_timebase)
        if auto_vertical is not None:
            result["auto_vertical"] = cursor_auto_vertical_json(auto_vertical)
        return planned + [":SYSTem:ERRor?"], [], result
    if command == "trigger-holdoff":
        if args.holdoff_query:
            return [trigger_holdoff_query(), ":SYSTem:ERRor?"], [], {"operation": "query", "command": trigger_holdoff_query()}
        seconds = validate_trigger_holdoff(args.holdoff_seconds)
        planned = trigger_holdoff_commands(
            seconds, series=capabilities.series
        )
        return planned + [":SYSTem:ERRor?"], [], {"operation": "set", "command": planned[-1], "commands": planned, "seconds": seconds}
    if command == "measure":
        item = normalize_measurement_item(args.item)
        kwargs = _measurement_query_kwargs(args, item)
        result: dict[str, object] = {"item": item, "parameters": kwargs}
        if is_pair_measurement_item(item):
            source, reference = _resolve_pair_measurement_channels(args, capabilities, item)
            planned = [pair_measurement_query(item, source, reference, capabilities=capabilities, **kwargs)]
            result.update({"channel": source, "reference_channel": reference})
        else:
            channel = _resolve_single_measurement_channel(args, capabilities)
            planned = [measurement_query(item, channel, capabilities=capabilities, **kwargs)]
            result["channel"] = channel
        return planned + [":SYSTem:ERRor?"], [], result
    if command == "measure-stats":
        channel = validate_analog_channel(args.channel, capabilities)
        items = measurement_analysis._parse_stats_items(args.items)
        commands = measurement_analysis._measure_stats_planned_scpi(channel, items, args.mode, reset=args.reset, max_count=args.max_count)
        return commands + [":SYSTem:ERRor?"], [], {"channel": channel, "items": list(items), "mode": args.mode, "reset": bool(args.reset), "max_count": args.max_count, "settle_seconds": args.settle_seconds, "records": []}
    if command == "doctor":
        planned = _doctor_planned_scpi(capabilities)
        return planned, [], {
            "backend": None,
            "timeout_ms": None,
            "acquisition": {},
            "channels": [],
            "timebase": {},
            "edge_trigger": {},
        }
    if command == "measure-sweep":
        channels = _resolve_sweep_channels(args.channel, capabilities)
        items = _parse_measurement_item_list(args.items, allow_pair=False)
        pairs = _parse_pair_specs(args.pair, capabilities)
        pair_items = _parse_measurement_item_list(args.pair_items, allow_pair=True)
        planned = _measure_sweep_planned_scpi(channels, items, pairs, pair_items, capabilities)
        return planned, [], {
            "channels": list(channels),
            "items": list(items),
            "pairs": [{"source_channel": source, "reference_channel": reference} for source, reference in pairs],
            "pair_items": list(pair_items),
            "measurements": [],
            "summary": {"valid_count": 0, "invalid_count": 0, "error_count": 0},
        }
    if command in {"capture", "capture-batch"}:
        channels = _resolve_capture_channels(args.channel, capabilities)
        points = validate_waveform_points(args.points, capabilities)
        if args.waveform_format == "word":
            validate_word_format_supported(capabilities)
        planned = _planned_waveform_scpi(channels, args.waveform_format, points) + [":SYSTem:ERRor?"]
        files = _planned_capture_files(args, command)
        result = {"channels": list(channels), "points": points, "format": args.waveform_format.upper(), "files": files}
        if command == "capture":
            result["requested_points"] = points
        else:
            result.update({"status": "planned", "requested_count": args.count, "completed_count": 0, "captures": [], "manifest_path": files[0]["path"], "scpi_log_path": files[1]["path"]})
        return planned, files, result
    if command == "measure-log":
        channels = _resolve_capture_channels(args.channel or ("all",), capabilities)
        items = _parse_measurement_item_list(args.items, allow_pair=False)
        pairs = _parse_pair_specs(args.pair, capabilities)
        pair_items = _parse_measurement_item_list(args.pair_items, allow_pair=True)
        planned = _measure_log_planned_scpi(channels, items, pairs, pair_items, capabilities)
        files = _planned_measure_log_files(args)
        result = {
            "status": "planned",
            "channels": list(channels),
            "items": list(items),
            "pairs": [f"{src}:{ref}" for src, ref in pairs],
            "pair_items": list(pair_items),
            "interval_seconds": args.interval_seconds,
            "requested_count": args.count,
            "requested_duration_seconds": args.duration_seconds,
            "completed_rows": 0,
            "files": files,
            "manifest_path": files[1]["path"],
            "scpi_log_path": files[2]["path"],
            "csv_path": files[0]["path"],
        }
        return planned, files, result
    if command == "screenshot":
        if args.query_hardcopy:
            planned = [
                hardcopy_area_query(),
                hardcopy_inksaver_query(),
                hardcopy_palette_query(),
                hardcopy_layout_query(),
                hardcopy_format_query(),
                ":SYSTem:ERRor?",
            ]
            return planned, [], {"operation": "query", "hardcopy": None}
        options = preflight._screenshot_options(args)
        background = args.background or DEFAULT_SCREENSHOT_BACKGROUND
        format_name = options.format or "png"
        output_path = workflows._screenshot_output_path(args, format_name)
        file_kind = "png" if format_name == "png" else "bmp"
        files = [{"kind": file_kind, "path": str(output_path)}]
        ink_saver_plan = None
        if preflight._uses_screenshot_hardcopy_controls(args):
            planned = []
            if options.ink_saver is not None:
                planned.append(hardcopy_inksaver_command(options.ink_saver))
                ink_saver_plan = {
                    "mode": "explicit",
                    "target": options.ink_saver,
                    "restore": None,
                }
            else:
                background_ink_saver = hardcopy_inksaver_for_background(background)
                planned.extend(
                    [
                        hardcopy_inksaver_query(),
                        hardcopy_inksaver_command(background_ink_saver),
                    ]
                )
                ink_saver_plan = {
                    "mode": "temporary_background",
                    "target": background_ink_saver,
                    "restore": "queried_state_if_changed",
                }
            if options.palette is not None:
                planned.append(hardcopy_palette_command(options.palette))
            if options.layout is not None:
                planned.append(hardcopy_layout_command(options.layout))
            planned.append(hardcopy_screen_dump_data_query(format_name))
        else:
            planned = [
                hardcopy_inksaver_command(hardcopy_inksaver_for_background(background)),
                screenshot_data_query(),
            ]
        result = {
            "format": {"png": "PNG", "bmp": "BMP", "bmp8bit": "BMP8bit"}[format_name],
            "background": background,
            "ink_saver": options.ink_saver,
            "palette": options.palette,
            "layout": options.layout,
            "options": {
                "format": options.format,
                "ink_saver": options.ink_saver,
                "palette": options.palette,
                "layout": options.layout,
            },
            "timeout_ms": SCREENSHOT_TIMEOUT_MS,
            "files": files,
            "image_path": str(output_path),
        }
        if format_name == "png":
            result["png_path"] = str(output_path)
        if ink_saver_plan is not None:
            result["ink_saver_plan"] = ink_saver_plan
        return planned + [":SYSTem:ERRor?"], files, result
    if command == "smoke":
        output_dir = Path(args.output_dir) if args.output_dir is not None else Path("data") / "hardware_smoke" / "DRY-RUN"
        files = _smoke_file_list(output_dir)
        planned = (
            _doctor_planned_scpi(capabilities)
            + [
                measurement_query("vpp", 1, capabilities=capabilities),
                measurement_query("vrms", 1, capabilities=capabilities),
            ]
            + _planned_waveform_scpi((1,), "byte", 1000)
            + [
                hardcopy_inksaver_command(hardcopy_inksaver_for_background("black")),
                screenshot_data_query(),
                ":SYSTem:ERRor?",
            ]
        )
        return planned, files, {
            "status": "planned",
            "output_dir": str(output_dir),
            "files": files,
            "doctor": {},
            "measurements": [],
            "capture": {},
            "screenshot": {},
            "warnings": [],
        }
    if command == "acquisition-check":
        average_count = validate_acquisition_count(args.average_count)
        check_only = bool(getattr(args, "check_only", False))
        stop_on_error = bool(getattr(args, "stop_on_error", False))
        restore_type = bool(getattr(args, "restore_type", False))
        if check_only and restore_type:
            raise OscilloscopeError("--check-only cannot be combined with --restore-type")
        output_dir = (
            Path(args.output_dir)
            if args.output_dir is not None
            else Path("data") / "hardware_acquisition" / "DRY-RUN"
        )
        files = _acquisition_check_file_list(output_dir)
        planned = _acquisition_check_planned_scpi(
            average_count,
            check_only=check_only,
            stop_on_error=stop_on_error,
            restore_type=restore_type,
        )
        return planned, files, {
            "status": "planned",
            "output_dir": str(output_dir),
            "report_path": str(output_dir / "report.json"),
            "scpi_log_path": str(output_dir / "scpi.log"),
            "average_count": average_count,
            "check_only": check_only,
            "stopped_on_error": False,
            "initial_acquisition": None,
            "restore": {
                "requested": restore_type,
                "attempted": False,
                "succeeded": None,
                "error": None,
            },
            "termination_reason": None,
            "steps": [],
            "final_acquisition": None,
            "files": files,
        }
    if command == "force-trigger":
        planned = ["*IDN?", force_trigger_command(), ":SYSTem:ERRor?"]
        return planned, [], {
            "operation": "force-trigger",
            "scpi_command": force_trigger_command(),
            "planned_scpi": list(planned),
            "state_changing": True,
        }
    if command == "sample-rate":
        query_command = acquisition._sample_rate_query_command(args)
        planned = ["*IDN?", query_command, ":SYSTem:ERRor?"]
        result = {
            "operation": "query",
            "scpi_command": query_command,
            "planned_scpi": list(planned),
            "unit": "Hz",
        }
        if getattr(args, "sample_rate_maximum", False):
            result["query_kind"] = "maximum"
        return planned, [], result
    if command == "segmented-memory":
        if args.query:
            ensure_segmented_memory_supported(capabilities)
            return ["*IDN?", segmented_mode_query(), ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "mode": None,
                "configured_segments": None,
                "acquired_segments": None,
                "selected_segment": None,
                "time_tag_s": None,
                "raw_mode": None,
                "raw_configured_segments": None,
                "raw_acquired_segments": None,
                "raw_selected_segment": None,
                "raw_time_tag": None,
            }
        if args.enable:
            validated_segments = validate_segmented_count(
                args.segments, capabilities
            )
            return [
                "*IDN?",
                acquisition_type_query(),
                segmented_mode_command("segmented"),
                segmented_count_command(validated_segments),
                ":SYSTem:ERRor?",
            ], [], {
                "operation": "enable",
                "mode": "segmented",
                "configured_segments": validated_segments,
            }
        ensure_segmented_memory_supported(capabilities)
        return ["*IDN?", segmented_mode_command("realtime"), ":SYSTem:ERRor?"], [], {
            "operation": "disable",
            "mode": "realtime",
            "configured_segments": None,
        }
    if command == "segmented-capture":
        return plan_segmented_capture(preflight._segmented_capture_request(args), capabilities)
    if command == "acquisition-points":
        planned = ["*IDN?", acquisition_points_query(), ":SYSTem:ERRor?"]
        return planned, [], {
            "operation": "query",
            "scpi_command": acquisition_points_query(),
            "planned_scpi": list(planned),
            "unit": "points",
        }
    if command == "record-length":
        if capabilities.series != "4000X":
            raise ParameterValidationError(
                "record-length requires a 4000X capability profile."
            )
        planned = ["*IDN?", record_length_query(), ":SYSTem:ERRor?"]
        return planned, [], {
            "operation": "query",
            "scpi_command": record_length_query(),
            "planned_scpi": list(planned),
            "unit": "points",
        }
    if command == "acquisition":
        if args.acq_query and (args.acq_type is not None or args.acq_count is not None):
            raise OscilloscopeError("--query cannot be combined with --type or --count")
        if args.acq_query:
            commands = [acquisition_type_query(), acquisition_count_query()]
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        if args.acq_type is None:
            raise OscilloscopeError("acquisition command requires --query or --type")
        normalized = normalize_acquisition_type(args.acq_type)
        planned = [acquisition_type_command(normalized)]
        count = None
        if args.acq_count is not None:
            count = validate_acquisition_count(args.acq_count)
            planned.append(acquisition_count_command(count))
        return planned + [":SYSTem:ERRor?"], [], {"operation": "set", "commands": planned, "type": args.acq_type, "scpi_type": normalized, "count": count}
    if command == "autoscale":
        channels = None if not args.source_channel else tuple(validate_analog_channel(channel, capabilities) for channel in args.source_channel)
        planned = autoscale_commands(channels, acquire_mode=args.acquire_mode, channels_mode=args.channels, capabilities=capabilities)
        return planned + [":SYSTem:ERRor?"], [], {"operation": "run", "commands": planned, "source_channels": None if channels is None else list(channels), "acquire_mode": args.acquire_mode, "channels": args.channels}
    if command == "setup-save":
        planned = [setup_save_command(slot=args.slot, file_spec=args.setup_file)]
        return planned + [system_opc_query(), ":SYSTem:ERRor?"], [], {"operation": "save", "command": planned[0], "slot": args.slot, "file": args.setup_file}
    if command == "setup-recall":
        planned = [setup_recall_command(slot=args.slot, file_spec=args.setup_file)]
        return planned + [system_opc_query(), ":SYSTem:ERRor?"], [], {"operation": "recall", "command": planned[0], "slot": args.slot, "file": args.setup_file}
    if command == "fft":
        if args.fft_query:
            commands = fft_query_commands(args.function, capabilities=capabilities)
            if capabilities.supports_advanced_fft:
                commands += fft_advanced_query_commands(
                    args.function, capabilities=capabilities
                )
            return commands + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "commands": commands,
                "function": args.function,
                "fft_operation": None,
                "fft_operation_canonical": None,
                "start_hz": None,
                "stop_hz": None,
                "gate": None,
                "phase_reference": None,
                "detection_type": None,
                "detection_points": None,
                "bin_size_hz": None,
                "sample_rate_hz": None,
                "resolution_bandwidth_hz": None,
            }
        assert args.source_channel is not None
        commands = fft_configure_commands(
            args.function,
            args.source_channel,
            units=args.units,
            window=args.window,
            center_hz=args.center_hz,
            span_hz=args.span_hz,
            display=None if args.display is None else args.display == "on",
            fft_operation=args.fft_operation or "fft",
            start_hz=args.start_hz,
            stop_hz=args.stop_hz,
            gate=args.gate,
            phase_reference=args.phase_reference,
            detection_type=args.detection_type,
            detection_points=args.detection_points,
            capabilities=capabilities,
        )
        return commands + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "commands": commands,
            "function": args.function,
            "source_channel": args.source_channel,
            "fft_operation_canonical": args.fft_operation or "fft",
            "units": args.units,
            "window": args.window,
            "center_hz": args.center_hz,
            "span_hz": args.span_hz,
            "start_hz": args.start_hz,
            "stop_hz": args.stop_hz,
            "gate": args.gate,
            "phase_reference": args.phase_reference,
            "detection_type": args.detection_type,
            "detection_points": args.detection_points,
            "display": args.display,
        }
    if command == "math-display":
        if args.math_display_action == "query":
            planned = math_display_query(args.function, capabilities=capabilities)
            return [planned, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "enabled": None,
                "raw": None,
            }
        enabled = args.math_display_action == "on"
        planned = math_display_command(
            args.function, enabled, capabilities=capabilities
        )
        return [planned, ":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "enabled": enabled,
            "command": planned,
        }
    if command == "math-vertical":
        if args.math_vertical_query:
            planned = math_vertical_query_commands(
                args.function, capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "scale": None,
                "range": None,
                "offset": None,
            }
        planned = math_vertical_commands(
            args.function,
            scale=args.scale,
            range_value=args.range_value,
            offset=args.offset,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "scale": args.scale,
            "range": args.range_value,
            "offset": args.offset,
            "commands": planned,
        }
    if command == "math-composite-source":
        if args.math_composite_query:
            planned = math_composite_source_query_commands(
                capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "math_operation": None,
                "operation_raw": None,
                "source1": None,
                "source1_raw": None,
                "source2": None,
                "source2_raw": None,
            }
        planned = math_composite_source_commands(
            args.math_composite_operation,
            args.source1,
            args.source2,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "math_operation": args.math_composite_operation,
            "source1": args.source1,
            "source2": args.source2,
            "commands": planned,
        }
    if command == "math-operator":
        if args.math_operator_query:
            planned = math_operator_query_commands(
                args.function, capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "math_operation": None,
                "operation_raw": None,
                "source1": None,
                "source1_raw": None,
                "source2": None,
                "source2_raw": None,
            }
        planned = math_operator_commands(
            args.function,
            args.math_operation,
            args.source1,
            args.source2,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "math_operation": args.math_operation,
            "source1": args.source1,
            "source2": args.source2,
            "commands": planned,
        }
    if command == "math-transform":
        if args.math_transform_query:
            planned = math_transform_query_commands(
                args.function, capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "math_operation": None,
                "operation_raw": None,
                "source": None,
                "source_raw": None,
                "input_offset": None,
                "gain": None,
                "linear_offset": None,
            }
        planned = math_transform_commands(
            args.function,
            args.math_transform_operation,
            args.source,
            input_offset=args.input_offset,
            gain=args.gain,
            linear_offset=args.linear_offset,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "math_operation": args.math_transform_operation,
            "source": args.source,
            "input_offset": args.input_offset,
            "gain": args.gain,
            "linear_offset": args.linear_offset,
            "commands": planned,
        }
    if command == "math-filter":
        if args.math_filter_query:
            planned = math_filter_query_commands(
                args.function, capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "math_operation": None,
                "operation_raw": None,
                "source": None,
                "source_raw": None,
                "cutoff_hz": None,
                "average_count": None,
                "smooth_points": None,
            }
        planned = math_filter_commands(
            args.function,
            args.math_filter_operation,
            args.source,
            cutoff_hz=args.cutoff_hz,
            average_count=args.average_count,
            smooth_points=args.smooth_points,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "math_operation": args.math_filter_operation,
            "source": args.source,
            "cutoff_hz": args.cutoff_hz,
            "average_count": args.average_count,
            "smooth_points": args.smooth_points,
            "commands": planned,
        }
    if command == "math-visualization":
        if args.math_visualization_query:
            planned = math_visualization_query_commands(
                args.function, capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "math_operation": None,
                "operation_raw": None,
                "source": None,
                "source_raw": None,
                "source2": None,
                "source2_raw": None,
                "measurement": None,
                "measurement_raw": None,
                "measurement_slot": None,
            }
        planned = math_visualization_commands(
            args.function,
            args.math_visualization_operation,
            source=args.source,
            source2=args.source2,
            measurement=args.measurement,
            measurement_slot=args.measurement_slot,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "math_operation": args.math_visualization_operation,
            "source": args.source,
            "source2": args.source2,
            "measurement": args.measurement,
            "measurement_slot": args.measurement_slot,
            "commands": planned,
        }
    if command == "math-clear":
        planned = math_clear_command(args.function, capabilities=capabilities)
        return [planned, ":SYSTem:ERRor?"], [], {
            "operation": "clear",
            "function": args.function,
            "cleared": True,
            "command": planned,
        }
    return [], [], {}










def _acquisition_check_planned_scpi(
    average_count: int,
    *,
    check_only: bool = False,
    stop_on_error: bool = False,
    restore_type: bool = False,
) -> list[str]:
    if check_only:
        return ["*IDN?", acquisition_type_query(), acquisition_count_query(), ":SYSTem:ERRor?"]
    return [
        "*IDN?",
        acquisition_type_query(),
        acquisition_count_query(),
        ":SYSTem:ERRor?",
        acquisition_type_command("NORMal"),
        ":SYSTem:ERRor?",
        acquisition_type_command("AVERage"),
        acquisition_count_command(average_count),
        ":SYSTem:ERRor?",
        acquisition_type_query(),
        acquisition_count_query(),
        ":SYSTem:ERRor?",
        acquisition_type_command("HRESolution"),
        ":SYSTem:ERRor?",
        acquisition_type_command("PEAK"),
        ":SYSTem:ERRor?",
        acquisition_type_query(),
        acquisition_count_query(),
        ":SYSTem:ERRor?",
    ]


def _planned_waveform_scpi(channels: Sequence[int], waveform_format: str, points: int) -> list[str]:
    planned: list[str] = []
    for channel in channels:
        planned.append(waveform_source_command(channel))
        if waveform_format == "word":
            planned.extend([waveform_format_word_command(), waveform_byte_order_command(WORD_BYTE_ORDER), waveform_unsigned_command(WORD_UNSIGNED)])
        else:
            planned.append(waveform_format_byte_command())
        planned.extend([waveform_points_command(points), waveform_preamble_query(), waveform_data_query()])
    return planned








def _doctor_planned_scpi(capabilities: ScopeCapabilities) -> list[str]:
    planned = [
        "*IDN?",
        acquisition_type_query(),
        acquisition_count_query(),
    ]
    for channel in range(1, capabilities.analog_channels + 1):
        planned.extend(
            [
                channel_display_query(channel),
                channel_scale_query(channel),
                channel_offset_query(channel),
                channel_coupling_query(channel),
                channel_probe_ratio_query(channel),
                channel_bandwidth_limit_query(channel),
            ]
        )
    planned.extend(
        [
            timebase_scale_query(),
            timebase_position_query(),
            edge_trigger_source_query(),
            edge_trigger_level_query(),
            edge_trigger_slope_query(),
            ":SYSTem:ERRor?",
        ]
    )
    return planned


def _measure_sweep_planned_scpi(
    channels: Sequence[int],
    items: Sequence[str],
    pairs: Sequence[tuple[int, int]],
    pair_items: Sequence[str],
    capabilities: ScopeCapabilities,
) -> list[str]:
    planned = ["*IDN?"]
    for channel in channels:
        for item in items:
            planned.append(measurement_query(item, channel, capabilities=capabilities))
            planned.append(":SYSTem:ERRor?")
    for source_channel, reference_channel in pairs:
        for item in pair_items:
            try:
                planned.append(
                    pair_measurement_query(
                        item,
                        source_channel,
                        reference_channel,
                        capabilities=capabilities,
                    )
                )
                planned.append(":SYSTem:ERRor?")
            except OscilloscopeError:
                continue
    return planned


def _planned_capture_files(args: argparse.Namespace, command: str) -> list[dict[str, str]]:
    if command == "capture":
        csv_path = Path(args.csv_path) if args.csv_path is not None else workflows._default_capture_csv_path()
        meta_path = Path(args.meta_path) if args.meta_path is not None else csv_path.with_name(f"{csv_path.stem}_meta.json")
        files = [{"kind": "csv", "path": str(csv_path)}, {"kind": "metadata", "path": str(meta_path)}]
        if args.plot_path is not None:
            files.append({"kind": "plot_png", "path": str(Path(args.plot_path))})
        return files
    output_dir = Path(args.output_dir) if args.output_dir is not None else Path("data") / "captures" / "DRY-RUN"
    files = [{"kind": "manifest", "path": str(output_dir / "manifest.json")}, {"kind": "scpi_log", "path": str(output_dir / "scpi.log")}]
    for index in range(1, args.count + 1):
        csv_path, meta_path = batch_capture_paths(output_dir, index, args.count)
        files.extend([{"kind": "csv", "path": str(csv_path)}, {"kind": "metadata", "path": str(meta_path)}])
    return files


def _planned_measure_log_files(args: argparse.Namespace) -> list[dict[str, str]]:
    output_dir = (
        Path(args.output_dir)
        if args.output_dir is not None
        else Path("data") / "measure_logs" / "DRY-RUN"
    )
    csv_path, manifest_path, scpi_log_path = measure_log_paths(output_dir)
    return [
        {"kind": "csv", "path": str(csv_path)},
        {"kind": "manifest", "path": str(manifest_path)},
        {"kind": "scpi_log", "path": str(scpi_log_path)},
    ]


def _measure_log_planned_scpi(
    channels: Sequence[int],
    items: Sequence[str],
    pairs: Sequence[tuple[int, int]],
    pair_items: Sequence[str],
    capabilities: ScopeCapabilities,
) -> list[str]:
    planned = []
    for channel in channels:
        for item in items:
            planned.append(measurement_query(item, channel, capabilities=capabilities))
    for source_channel, reference_channel in pairs:
        for item in pair_items:
            planned.append(
                pair_measurement_query(
                    item,
                    source_channel,
                    reference_channel,
                    capabilities=capabilities,
                )
            )
    planned.append(":SYSTem:ERRor?")
    return planned


def _idn_json(raw: str) -> dict[str, str | None]:
    idn = parse_idn(raw)
    return {"raw": idn.raw, "vendor": idn.vendor, "model": idn.model, "serial": idn.serial, "firmware": idn.firmware, "series": idn.series}


def _write_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _apply_json_record(payload: dict[str, object]) -> None:
    if runtime._JSON_RECORD is None:
        return
    result = runtime._JSON_RECORD.get("result")
    if isinstance(result, dict):
        payload_result = payload.setdefault("result", {})
        if isinstance(payload_result, dict):
            payload_result.update(result)
    for key in ("idn", "capabilities", "backend", "system_error"):
        if key in runtime._JSON_RECORD:
            payload[key] = runtime._JSON_RECORD[key]
    files = runtime._JSON_RECORD.get("files")
    if isinstance(files, list):
        payload["files"] = files




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


def _waveform_capture_summary(capture: WaveformCapture | MultiChannelWaveformCapture) -> dict[str, object]:
    if isinstance(capture, MultiChannelWaveformCapture):
        summaries = [_single_waveform_capture_summary(item) for item in capture.captures]
        return {
            "actual_points": {f"CH{item['channel']}": item["actual_points"] for item in summaries},
            "captures": summaries,
        }
    single = _single_waveform_capture_summary(capture)
    return {"actual_points": single["actual_points"], "captures": [single]}


def _single_waveform_capture_summary(capture: WaveformCapture) -> dict[str, object]:
    return {
        "channel": capture.channel,
        "requested_points": capture.requested_points,
        "actual_points": len(capture.raw_samples),
        "format": capture.format_name,
        "preamble": _waveform_preamble_json(capture.preamble),
        "byte_order": capture.byte_order,
        "unsigned": capture.unsigned,
    }


def _cmd_list_resources(args: argparse.Namespace) -> int:
    listing = list_visa_resources(visa_library=args.visa_library)
    print(f"PyVISA backend: {listing.backend}")
    runtime._json_update_result(
        backend=listing.backend,
        resources=list(listing.resources),
        live_only=bool(args.live_only),
        live_resources=[],
    )
    if runtime._JSON_RECORD is not None:
        runtime._JSON_RECORD["backend"] = listing.backend
    if args.live_only:
        runtime._configure_scpi_logging(args)
        return _print_live_resources(
            listing.resources,
            visa_library=args.visa_library,
            serial_read_termination=args.serial_read_termination,
            serial_write_termination=args.serial_write_termination,
        )

    print("Resources:")
    if not listing.resources:
        print("  <none>")
        return 0

    for resource in listing.resources:
        print(f"  {resource}")
    return 0


def _print_live_resources(
    resources: tuple[str, ...],
    visa_library: str | None,
    *,
    serial_read_termination: str | None = None,
    serial_write_termination: str | None = None,
) -> int:
    print("Live resources:")
    live_count = 0
    live_resources = []
    verification_failures = []
    for resource in resources:
        if is_asrl_resource(resource):
            verification = verify_asrl_resource_live(
                resource,
                visa_library=visa_library,
                serial_read_termination=serial_read_termination,
                serial_write_termination=serial_write_termination,
            )
            if not verification.live or verification.raw_idn is None:
                verification_failures.append(_visa_verification_json(verification))
                continue
            try:
                idn = parse_idn(verification.raw_idn)
            except OscilloscopeError as exc:
                verification_failures.append(
                    _visa_verification_json(verification, detail=str(exc))
                )
                continue
        else:
            try:
                with Oscilloscope.open(resource, visa_library=visa_library) as scope:
                    idn = scope.query_idn()
            except OscilloscopeError:
                continue

        live_count += 1
        live_resources.append({"resource": resource, "idn": runtime._idn_object_json(idn)})
        print(f"  {resource}")
        print(f"    IDN: {idn.raw}")

    if live_count == 0:
        print("  <none>")
    result_update = {"live_resources": live_resources}
    if verification_failures:
        result_update["verification_failures"] = verification_failures
    runtime._json_update_result(**result_update)
    return 0


def _visa_verification_json(
    verification,
    *,
    detail: str | None = None,
) -> dict[str, object]:
    return {
        "resource": verification.resource,
        "live": verification.live,
        "raw_idn": verification.raw_idn,
        "detail": detail if detail is not None else verification.detail,
    }
































































































































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


def _cmd_hardware_report(args: argparse.Namespace) -> int:
    for index, path_text in enumerate(args.report_paths):
        path = Path(path_text)
        report = _load_report_json(path)
        if index:
            print()
        print(_render_hardware_report(report, path))
    return 0


def _load_report_json(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise OscilloscopeError(
            _format_plain_output_file_error("report JSON", path, exc)
        ) from exc
    except json.JSONDecodeError as exc:
        raise OscilloscopeError(f"could not parse report JSON {path}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise OscilloscopeError(f"report JSON must contain an object: {path}")
    return data


def _render_hardware_report(report: dict[str, object], path: Path) -> str:
    report_type = _detect_hardware_report_type(report)
    lines = [f"# Hardware Report: {path}"]
    lines.append(f"- Type: {report_type}")
    lines.append(f"- Status: {report.get('status')}")
    lines.append(f"- Model: {_report_model(report)}")
    lines.append(f"- Firmware: {_report_firmware(report)}")
    lines.append(f"- Resource: {_report_resource(report)}")
    lines.append(f"- Backend: {_report_backend(report)}")
    lines.append("")
    lines.append("## Commands")
    for command in _report_commands(report):
        lines.append(f"- {command}")
    lines.append("")
    lines.append("## Output Files")
    for kind, file_path in _report_files(report):
        lines.append(f"- {kind}: {file_path}")
    lines.append("")
    lines.append("## Result")
    lines.extend(_render_report_result(report))
    errors = _report_errors(report)
    if errors:
        lines.append("")
        lines.append("## Errors")
        lines.extend(errors)
    cleanup = _report_cleanup(report)
    if cleanup:
        lines.append("")
        lines.append("## Cleanup")
        lines.extend(cleanup)
    return "\n".join(lines)


def _detect_hardware_report_type(report: dict[str, object]) -> str:
    if "doctor" in report or "capture" in report or "screenshot" in report:
        return "smoke"
    if "steps" in report or "average_count" in report or "check_only" in report:
        return "acquisition-check"
    return "unknown"


def _report_model(report: dict[str, object]) -> str:
    idn = report.get("idn")
    if isinstance(idn, dict):
        model = idn.get("model")
        if isinstance(model, str) and model:
            return model
    return "unknown"


def _report_firmware(report: dict[str, object]) -> str:
    idn = report.get("idn")
    if isinstance(idn, dict):
        firmware = idn.get("firmware")
        if isinstance(firmware, str) and firmware:
            return firmware
    return "unknown"


def _report_resource(report: dict[str, object]) -> str:
    value = report.get("resource")
    return str(value) if value is not None else "unknown"


def _report_backend(report: dict[str, object]) -> str:
    value = report.get("backend")
    return str(value) if value is not None else "unknown"


def _report_commands(report: dict[str, object]) -> list[str]:
    commands: list[str] = []
    if report.get("idn") is not None:
        commands.append("*IDN?")
    steps = report.get("steps")
    saw_final_error_query = False
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_commands = step.get("commands")
            if isinstance(step_commands, list):
                commands.extend(str(command) for command in step_commands)
            if step.get("name") in {"final-query", "final-system-error"}:
                saw_final_error_query = True
    if isinstance(report.get("capture"), dict):
        commands.extend(["<capture waveform>", "<capture screenshot>"])
    if saw_final_error_query and ":SYSTem:ERRor?" not in commands:
        commands.append(":SYSTem:ERRor?")
    return commands or ["unknown"]


def _report_files(report: dict[str, object]) -> list[tuple[str, str]]:
    files = []
    for entry in report.get("files", []):
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        path = entry.get("path")
        if isinstance(kind, str) and isinstance(path, str):
            files.append((kind, path))
    if not files:
        if "report" in report:
            files.append(("report", str(report.get("report"))))
    return files


def _render_report_result(report: dict[str, object]) -> list[str]:
    lines: list[str] = []
    status = report.get("status")
    lines.append(f"- Status: {status}")
    if "average_count" in report:
        lines.append(f"- Average Count: {report.get('average_count')}")
    if "check_only" in report:
        lines.append(f"- Check Only: {report.get('check_only')}")
    if "stopped_on_error" in report:
        lines.append(f"- Stopped On Error: {report.get('stopped_on_error')}")
    if report.get("initial_acquisition") is not None:
        lines.append(f"- Initial Acquisition: {report.get('initial_acquisition')}")
    if report.get("final_acquisition") is not None:
        lines.append(f"- Final Acquisition: {report.get('final_acquisition')}")
    if report.get("termination_reason") is not None:
        lines.append(f"- Termination Reason: {report.get('termination_reason')}")
    if isinstance(report.get("doctor"), dict):
        lines.append(f"- Doctor: {report.get('doctor')}")
    if isinstance(report.get("measurements"), list):
        lines.append(f"- Measurements: {len(report.get('measurements', []))}")
    if isinstance(report.get("capture"), dict):
        lines.append(f"- Capture: {report.get('capture')}")
    if isinstance(report.get("screenshot"), dict):
        lines.append(f"- Screenshot: {report.get('screenshot')}")
    if report.get("post_check_error") is not None:
        lines.append(f"- Post Check Error: {report.get('post_check_error')}")
    return lines


def _report_errors(report: dict[str, object]) -> list[str]:
    lines: list[str] = []
    error = report.get("error")
    if error is not None:
        lines.append(f"- Report Error: {error}")
    restore = report.get("restore")
    if isinstance(restore, dict):
        restore_error = restore.get("error")
        if restore_error is not None:
            lines.append(f"- Restore Error: {restore_error}")
    for step in report.get("steps", []):
        if not isinstance(step, dict):
            continue
        system_error = step.get("system_error")
        if isinstance(system_error, dict) and system_error.get("is_error"):
            lines.append(
                f"- {step.get('name')}: {system_error.get('code')} {system_error.get('message')}"
            )
    return lines


def _report_cleanup(report: dict[str, object]) -> list[str]:
    lines: list[str] = []
    restore = report.get("restore")
    if isinstance(restore, dict):
        lines.append(f"- Restore Requested: {restore.get('requested')}")
        lines.append(f"- Restore Attempted: {restore.get('attempted')}")
        lines.append(f"- Restore Succeeded: {restore.get('succeeded')}")
    return lines


def _print_waveform_capture_commands(
    channels: Sequence[int], waveform_format: str, points: int
) -> None:
    for channel in channels:
        print(f"Command: {waveform_source_command(channel)}")
        if waveform_format == "word":
            print(f"Command: {waveform_format_word_command()}")
            print(f"Command: {waveform_byte_order_command(WORD_BYTE_ORDER)}")
            print(f"Command: {waveform_unsigned_command(WORD_UNSIGNED)}")
        else:
            print(f"Command: {waveform_format_byte_command()}")
        print(f"Command: {waveform_points_command(points)}")
        print(f"Command: {waveform_preamble_query()}")
        print(f"Command: {waveform_data_query()}")


def _format_channel_list(channels: Sequence[int]) -> str:
    return ", ".join(f"CH{channel}" for channel in channels)



def _resolve_capture_channels(
    raw_channels: Sequence[int | str], capabilities: ScopeCapabilities
) -> tuple[int, ...]:
    if any(channel == "all" for channel in raw_channels):
        if len(raw_channels) != 1:
            raise OscilloscopeError(
                "error: --channel all cannot be combined with explicit channel numbers"
            )
        return validate_waveform_channels(
            tuple(range(1, capabilities.analog_channels + 1)), capabilities
        )

    return validate_waveform_channels(raw_channels, capabilities)


def _resolve_sweep_channels(
    raw_channels: Sequence[int | str] | None,
    capabilities: ScopeCapabilities,
) -> tuple[int, ...]:
    return _resolve_capture_channels(raw_channels or ("all",), capabilities)


def _parse_measurement_item_list(value: str, *, allow_pair: bool) -> tuple[str, ...]:
    items = []
    for token in value.split(","):
        stripped = token.strip()
        if not stripped:
            continue
        item = normalize_measurement_item(stripped)
        if allow_pair:
            if not is_pair_measurement_item(item):
                raise OscilloscopeError(
                    "--pair-items can only contain phase or delay measurements"
                )
        elif is_pair_measurement_item(item):
            raise OscilloscopeError(
                "--items can only contain single-channel measurements"
            )
        items.append(item)
    if not items:
        option = "--pair-items" if allow_pair else "--items"
        raise OscilloscopeError(f"{option} must contain at least one measurement item")
    return tuple(items)




def _parse_pair_specs(
    values: Sequence[str],
    capabilities: ScopeCapabilities,
) -> tuple[tuple[int, int], ...]:
    pairs = []
    for value in values:
        parts = value.split(":")
        if len(parts) != 2:
            raise OscilloscopeError("--pair must use SRC:REF, for example 1:2")
        try:
            source = int(parts[0])
            reference = int(parts[1])
        except ValueError as exc:
            raise OscilloscopeError("--pair channels must be integers") from exc
        source = validate_analog_channel(source, capabilities)
        reference = validate_analog_channel(reference, capabilities)
        if source == reference:
            raise OscilloscopeError("--pair source and reference channels must differ")
        pairs.append((source, reference))
    return tuple(pairs)


def _doctor_snapshot(scope: Oscilloscope) -> dict[str, object]:
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
        **runtime._scope_backend_json(scope),
        "acquisition": {
            "type": acquisition.type,
            "count": acquisition.count,
        },
        "channels": channels,
        "timebase": timebase,
        "edge_trigger": {
            "source_channel": trigger.source_channel,
            "level_volts": trigger.level_volts,
            "slope": trigger.slope,
        },
    }


def _run_sweep_measurement(
    scope: Oscilloscope,
    command: str,
    channel: int,
    item: str,
) -> dict[str, object]:
    try:
        result = scope.query_measurement(channel, item)
        system_error = scope.query_system_error()
        runtime._json_record_system_error(system_error)
        return {
            "command": command,
            **_measurement_result_json(result, parameters={}),
            "system_error": runtime._system_error_json(system_error),
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
        runtime._json_record_system_error(system_error)
        return {
            "command": command,
            **_measurement_result_json(result, parameters={}),
            "system_error": runtime._system_error_json(system_error),
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
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        return entry
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
        "system_error": None if system_error is None else runtime._system_error_json(system_error),
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }


def _measure_sweep_summary(measurements: Sequence[dict[str, object]]) -> dict[str, int]:
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






def _write_json_file(
    payload: dict[str, object],
    path: Path,
    *,
    file_kind: str,
) -> Path:
    return write_json_file(payload, path, file_kind=file_kind)


def _write_json_file_best_effort(payload: dict[str, object], path: Path) -> None:
    write_json_file_best_effort(payload, path)




def _format_plain_output_file_error(file_kind: str, path: Path, exc: OSError) -> str:
    reason = exc.strerror or str(exc)
    message = f"could not write {file_kind} file {path}: {reason}"
    if isinstance(exc, PermissionError):
        message += ". The file may be open in another program, or the folder may not be writable."
    return message




def _measurement_query_kwargs(args: argparse.Namespace, item: str) -> dict[str, object]:
    values: dict[str, object] = {}
    if args.time_s is not None:
        values["time_s"] = args.time_s
    if args.level is not None:
        values["level"] = args.level
    if args.slope is not None:
        values["slope"] = args.slope
    if args.occurrence is not None:
        values["occurrence"] = args.occurrence

    if is_pair_measurement_item(item):
        if values:
            raise OscilloscopeError(
                "--time, --level, --slope, and --occurrence cannot be used with "
                "phase or delay measurements"
            )
        return {}

    if item == "y_at_x":
        if args.time_s is None:
            raise OscilloscopeError("y_at_x measurement requires --time")
        if any(value is not None for value in (args.level, args.slope, args.occurrence)):
            raise OscilloscopeError(
                "--level, --slope, and --occurrence cannot be used with y_at_x"
            )
        return values

    if item == "time_at_edge":
        if args.time_s is not None or args.level is not None:
            raise OscilloscopeError("--time and --level cannot be used with time_at_edge")
        values.setdefault("slope", "positive")
        values.setdefault("occurrence", 1)
        return values

    if item == "time_at_value":
        if args.level is None:
            raise OscilloscopeError("time_at_value measurement requires --level")
        if args.time_s is not None:
            raise OscilloscopeError("--time cannot be used with time_at_value")
        values.setdefault("slope", "positive")
        values.setdefault("occurrence", 1)
        return values

    if values:
        raise OscilloscopeError(
            "--time, --level, --slope, and --occurrence can only be used with "
            "y_at_x, time_at_edge, or time_at_value"
        )
    return {}


def _resolve_measurement_source_channel(args: argparse.Namespace) -> int | None:
    if args.channel is not None and args.source_channel is not None:
        raise OscilloscopeError("--channel cannot be combined with --source-channel")
    return args.source_channel if args.source_channel is not None else args.channel


def _resolve_single_measurement_channel(
    args: argparse.Namespace, capabilities: ScopeCapabilities
) -> int:
    if args.reference_channel is not None:
        raise OscilloscopeError(
            "--reference-channel can only be used with phase or delay measurements"
        )
    channel = _resolve_measurement_source_channel(args)
    if channel is None:
        raise OscilloscopeError("measure requires --channel or --source-channel")
    return validate_analog_channel(channel, capabilities)


def _resolve_pair_measurement_channels(
    args: argparse.Namespace,
    capabilities: ScopeCapabilities,
    item: str,
) -> tuple[int, int]:
    source_channel = _resolve_measurement_source_channel(args)
    if source_channel is None or args.reference_channel is None:
        raise OscilloscopeError(
            f"{item} measurement requires --source-channel or --channel, "
            "plus --reference-channel"
        )
    source_channel = validate_analog_channel(source_channel, capabilities)
    reference_channel = validate_analog_channel(args.reference_channel, capabilities)
    if source_channel == reference_channel:
        raise OscilloscopeError("source channel and reference channel must be different")
    return source_channel, reference_channel


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




if __name__ == "__main__":
    raise SystemExit(main())
