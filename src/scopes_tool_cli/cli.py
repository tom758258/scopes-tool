"""Command line interface for oscilloscope checks."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
import logging
import math
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
    SegmentedCaptureRequest,
    plan_segmented_capture,
    run_segmented_capture,
    validate_segmented_capture_output_path,
    validate_segmented_capture_request,
)
from scopes_tool_core.advanced import (
    FFT_DETECTION_TYPES,
    FFT_GATES,
    FFT_OPERATIONS,
    FFT_PHASE_REFERENCES,
    MATH_COMPOSITE_OPERATIONS,
    MATH_FILTER_OPERATIONS,
    MATH_OPERATIONS,
    MATH_SOURCES,
    MATH_TREND_MEASUREMENTS,
    MATH_TRANSFORM_SOURCES,
    MATH_TRANSFORMS,
    MATH_VISUALIZATION_OPERATIONS,
    autoscale_commands,
    cursor_auto_vertical_dry_run_plan,
    cursor_auto_vertical_json,
    cursor_auto_timebase_dry_run_plan,
    cursor_auto_timebase_json,
    cursor_configure_commands,
    fft_configure_commands,
    fft_advanced_query_commands,
    fft_query_commands,
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
    setup_recall_command,
    setup_save_command,
    trigger_holdoff_commands,
    trigger_holdoff_query,
    validate_trigger_holdoff,
)
from scopes_tool_core.batch import (
    batch_capture_paths,
)
from scopes_tool_core.measure_logger import measure_log_paths
from scopes_tool_core.operations import (
    AcquisitionCheckRequest,
    CaptureBatchRequest,
    CaptureRequest,
    MeasureLogRequest,
    MeasureRequest,
    MeasureSweepRequest,
    SmokeRequest,
    _OperationError,
    run_acquisition_check,
    run_capture,
    run_capture_batch,
    run_doctor,
    run_measure_log,
    run_measure,
    run_measure_sweep,
    run_smoke,
)
from scopes_tool_core.workflow import StopRequested
from scopes_tool_core.sequence import (
    SequenceRequest,
    load_sequence_document,
    plan_sequence,
    run_sequence,
)
from scopes_tool_core.triggered_measurement import (
    TriggeredMeasureLoopRequest,
    plan_triggered_measure_loop,
    run_triggered_measure_loop,
)
from scopes_tool_core.triggered_capture import (
    TriggeredCaptureSeriesRequest,
    plan_triggered_capture_series,
    run_triggered_capture_series,
)
from scopes_tool_core.measure_until import (
    MeasureUntilRequest,
    plan_measure_until,
    run_measure_until,
)
from scopes_tool_core.output_files import (
    capture_output_paths,
    default_capture_csv_path,
    write_serial_lister_csv,
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
from scopes_tool_core.save_export import (
    SAVE_IMAGE_FORMATS,
    SAVE_IMAGE_PALETTES,
    SAVE_WAVEFORM_FORMATS,
    save_filename_command,
    save_filename_query,
    save_image_command,
    save_image_factors_command,
    save_image_factors_query,
    save_image_format_command,
    save_image_format_query,
    save_image_ink_saver_command,
    save_image_ink_saver_query,
    save_image_palette_command,
    save_image_palette_query,
    save_pwd_command,
    save_pwd_query,
    save_waveform_command,
    save_waveform_format_command,
    save_waveform_format_query,
    save_waveform_length_command,
    save_waveform_length_max_query,
    save_waveform_length_query,
    validate_save_filename_base,
    validate_save_quoted_string,
    validate_save_waveform_length,
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
from scopes_tool_core.cleanup import CLEANUP_PROFILES, plan_cleanup
from scopes_tool_core.display import (
    display_label_command,
    display_label_query,
)
from scopes_tool_core.dvm import (
    DVM_MODES,
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
    MEASUREMENT_ITEM_CHOICES,
    MEASUREMENT_WINDOW_CHOICES,
    is_pair_measurement_item,
    measurement_query,
    measurement_results_query,
    normalize_measurement_item,
    parse_statistics_results,
    pair_measurement_query,
    validate_measure_results_dump_supported,
)
from scopes_tool_core.demo import (
    DEMO_FUNCTIONS,
    demo_function_command,
    demo_function_query,
    demo_output_command,
    demo_output_query,
    demo_phase_command,
    demo_phase_query,
    demo_query_commands,
    validate_demo_function,
    validate_demo_phase,
)
from scopes_tool_core.wgen import (
    WGEN_FUNCTIONS,
    WGEN_LOADS,
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
    CAN_SEARCH_ID_MODES,
    CAN_SEARCH_MODES,
    I2C_SEARCH_MODES,
    SEARCH_MODES,
    SEARCH_QUALIFIERS,
    SPI_SEARCH_MODES,
    UART_SEARCH_MODES,
    search_count_query,
    search_event_command,
    search_event_query,
    search_mode_command,
    search_mode_query,
    search_state_command,
    search_state_query,
    validate_can_data_length,
    validate_can_id_mode,
    validate_can_search_criteria,
    validate_can_search_mode,
    validate_i2c_pattern_value,
    validate_i2c_search_mode,
    validate_pattern_hex_x,
    validate_search_event,
    validate_search_mode,
    validate_search_qualifier,
    validate_spi_search_pattern_width,
    validate_spi_search_mode,
    validate_spi_width,
    validate_uart_data,
    validate_uart_search_mode,
)
from scopes_tool_core.serial import (
    CAN_TRIGGER_ID_MODES,
    CAN_TRIGGER_TYPES,
    CAN_SIGNAL_DEFINITIONS,
    I2C_ADDRESS_SIZES,
    I2C_TRIGGER_QUALIFIERS,
    I2C_TRIGGER_TYPES,
    SERIAL_BIT_ORDERS,
    SERIAL_MODES,
    SERIAL_LISTER_DISPLAYS,
    SERIAL_LISTER_REFERENCES,
    SPI_CLOCK_SLOPES,
    SPI_FRAMINGS,
    SPI_TRIGGER_TYPES,
    UART_PARITIES,
    UART_POLARITIES,
    UART_TRIGGER_QUALIFIERS,
    UART_TRIGGER_TYPES,
    serial_bus_query,
    serial_display_command,
    serial_display_query,
    serial_mode_command,
    serial_mode_query,
    serial_can_configure_commands,
    serial_can_query_commands,
    serial_lister_data_query,
    serial_lister_display_command,
    serial_lister_display_query,
    serial_lister_query_commands,
    serial_lister_reference_command,
    serial_lister_reference_query,
    serial_i2c_configure_commands,
    serial_i2c_query_commands,
    serial_spi_configure_commands,
    serial_spi_query_commands,
    serial_uart_configure_commands,
    serial_uart_query_commands,
    serial_uart_trigger_configure_commands,
    serial_uart_trigger_data_query,
    serial_uart_trigger_qualifier_query,
    serial_uart_trigger_type_query,
    serial_i2c_trigger_configure_commands,
    serial_i2c_trigger_data2_query,
    serial_i2c_trigger_data_query,
    serial_i2c_trigger_address_query,
    serial_i2c_trigger_qualifier_query,
    serial_i2c_trigger_type_query,
    serial_spi_trigger_configure_commands,
    serial_spi_trigger_data_query,
    serial_spi_trigger_type_query,
    serial_spi_trigger_width_query,
    serial_can_trigger_configure_commands,
    serial_can_trigger_data_length_query,
    serial_can_trigger_data_query,
    serial_can_trigger_id_mode_query,
    serial_can_trigger_id_query,
    serial_can_trigger_type_query,
    validate_serial_uart_trigger_request,
    validate_serial_i2c_trigger_request,
    validate_serial_spi_trigger_request,
    validate_serial_can_trigger_request,
    normalize_can_signal_definition,
    normalize_i2c_address_size,
    normalize_serial_bit_order,
    normalize_serial_source,
    normalize_spi_clock_slope,
    normalize_spi_framing,
    normalize_uart_parity,
    normalize_uart_polarity,
    validate_can_baud_rate,
    validate_can_sample_point,
    validate_uart_baud_rate,
    validate_serial_bus,
    validate_serial_mode,
    validate_serial_lister_display,
    validate_serial_lister_reference,
    validate_spi_framing_clock_timeout,
    require_serial_decode,
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
    ScreenshotOptions,
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
    write_screenshot,
    write_screenshot_png,
)
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatedSignal, simulator_idn
from scopes_tool_core.simulator_config import (
    PRESET_NAMES,
    parse_simulate_signal_spec,
    validate_simulator_args,
)
from scopes_tool_core.timebase import (
    timebase_position_command,
    timebase_position_query,
    timebase_scale_command,
    timebase_scale_query,
    validate_timebase_position,
    validate_timebase_scale,
)
from scopes_tool_core.trigger import (
    TriggerWaitConfig,
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
    normalize_edge_burst_slope,
    normalize_delay_slope,
    normalize_glitch_qualifier,
    normalize_runt_qualifier,
    normalize_setup_hold_slope,
    normalize_transition_qualifier,
    normalize_transition_slope,
    operation_condition_query,
    or_trigger_configure_commands,
    or_trigger_query_commands,
    pattern_trigger_configure_commands,
    pattern_trigger_query_commands,
    normalize_trigger_sweep,
    runt_trigger_configure_commands,
    runt_trigger_query_commands,
    setup_hold_trigger_configure_commands,
    setup_hold_trigger_query_commands,
    single_command,
    transition_trigger_configure_commands,
    transition_trigger_query_commands,
    trigger_mode_edge_command,
    trigger_mode_query,
    trigger_mode_serial_command,
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
    validate_delay_trigger_count,
    validate_delay_trigger_time,
    validate_edge_burst_count,
    validate_edge_burst_idle_time,
    validate_external_trigger_range,
    validate_external_trigger_probe_attenuation,
    validate_external_trigger_units,
    validate_or_trigger_pattern,
    validate_pattern_trigger_pattern,
    validate_setup_hold_trigger_time,
    validate_trigger_level,
    validate_trigger_time,
)
from scopes_tool_core.visa_backend import (
    is_asrl_resource,
    list_visa_resources,
    verify_asrl_resource_live,
)
from scopes_tool_core.waveform import (
    MultiChannelWaveformCapture,
    SUPPORTED_WAVEFORM_POINTS,
    WORD_BYTE_ORDER,
    WORD_UNSIGNED,
    WaveformCapture,
    waveform_byte_order_command,
    validate_word_format_supported,
    validate_waveform_channels,
    validate_waveform_points,
    waveform_time_axis_tolerance_summary,
    waveform_data_query,
    waveform_format_byte_command,
    waveform_format_word_command,
    waveform_points_command,
    waveform_preamble_query,
    waveform_source_command,
    waveform_unsigned_command,
)

from . import preflight, runtime
from .commands import acquisition, channel_display, measurement_analysis, system, trigger_search
_CAPTURE_DEFAULT_TIMEZONE = timezone(timedelta(hours=8), name="UTC+8")
AUTOSCALE_SYSTEM_ERROR_TIMEOUT_MS = 15000
CLI_SCHEMA_VERSION = 2
_SERIAL_SOURCE_HELP = (
    "channelN or external; source availability may depend on the other "
    "configured Serial bus; query both buses after an instrument settings conflict"
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the `scopes-tool` command line interface."""

    parser = _build_parser()
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scopes-tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    worker_parser = subparsers.add_parser("worker", help="run the local Scopes worker")
    worker_parser.set_defaults(lifecycle_command=True)
    worker_parser.add_argument("--host", default="127.0.0.1")
    worker_parser.add_argument("--port", type=int, default=8765)
    mode_group = worker_parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--simulate", action="store_true")
    mode_group.add_argument("--live", action="store_true")
    worker_parser.add_argument("--model", default="keysight-dsox4024a")
    worker_parser.add_argument("--resource", default=None)
    worker_parser.add_argument("--artifact-root", default="data/worker")
    worker_parser.add_argument("--queue-max", type=_positive_int, default=32)
    worker_parser.add_argument("--format", choices=("jsonl", "text"), default="jsonl")

    send_parser = subparsers.add_parser(
        "send-command", help="enqueue a command in a running Scopes worker"
    )
    send_parser.set_defaults(lifecycle_command=True)
    send_parser.add_argument("--host", default="127.0.0.1")
    send_parser.add_argument("--port", type=int, required=True)
    send_parser.add_argument("--command", dest="worker_command", required=True)
    send_parser.add_argument("--arguments-json", default="{}")
    send_parser.add_argument("--job-id", default=None)
    send_parser.add_argument("--timeout-ms", type=_positive_int, default=5000)
    send_parser.add_argument("--format", choices=("text", "json"), default="text")
    send_parser.add_argument("--json", dest="client_json", action="store_true")
    send_parser.add_argument("--dry-run", action="store_true")

    status_parser = subparsers.add_parser("status", help="query worker runtime status")
    status_parser.set_defaults(lifecycle_command=True)
    status_parser.add_argument("--host", default="127.0.0.1")
    status_parser.add_argument("--port", type=int, required=True)
    status_parser.add_argument("--timeout-ms", type=_positive_int, default=5000)
    status_parser.add_argument("--format", choices=("text", "json"), default="text")
    status_parser.add_argument("--json", dest="client_json", action="store_true")

    stop_parser = subparsers.add_parser("stop", help="request cooperative worker stop")
    stop_parser.set_defaults(lifecycle_command=True)
    stop_parser.add_argument("--host", default="127.0.0.1")
    stop_parser.add_argument("--port", type=int, required=True)
    stop_parser.add_argument("--timeout-ms", type=_positive_int, default=5000)
    stop_parser.add_argument("--format", choices=("text", "json"), default="text")
    stop_parser.add_argument("--json", dest="client_json", action="store_true")

    wait_parser = subparsers.add_parser(
        "wait-ready", help="wait until worker status is reachable"
    )
    wait_parser.set_defaults(lifecycle_command=True)
    wait_parser.add_argument("--host", default="127.0.0.1")
    wait_parser.add_argument("--port", type=int, required=True)
    wait_parser.add_argument("--timeout-ms", type=_positive_int, default=10000)
    wait_parser.add_argument("--format", choices=("text", "json"), default="text")
    wait_parser.add_argument("--json", dest="client_json", action="store_true")

    list_resources_parser = subparsers.add_parser(
        "list-resources",
        help="list VISA resource strings reported by the selected backend",
    )
    list_resources_parser.add_argument(
        "--visa-library",
        default=None,
        help="optional PyVISA library argument, such as @py",
    )
    list_resources_parser.add_argument(
        "--live-only",
        action="store_true",
        help="only print resources that open and respond to *IDN?",
    )
    list_resources_parser.add_argument(
        "--log-scpi",
        action="store_true",
        help="write SCPI command and response logs to stderr when --live-only is used",
    )
    list_resources_parser.add_argument(
        "--serial-read-termination",
        choices=("CRLF", "LF", "CR", "NONE"),
        help="ASRL live discovery read termination compatibility setting",
    )
    list_resources_parser.add_argument(
        "--serial-write-termination",
        choices=("CRLF", "LF", "CR", "NONE"),
        help="ASRL live discovery write termination compatibility setting",
    )
    list_resources_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="write a single machine-readable JSON object to stdout",
    )

    hardware_report_parser = subparsers.add_parser(
        "hardware-report",
        help="render hardware report JSON files as a Markdown summary",
    )
    hardware_report_parser.add_argument(
        "report_paths",
        nargs="+",
        help="report JSON files from smoke or acquisition-check",
    )

    identify_parser = subparsers.add_parser(
        "identify",
        help="open one resource and verify basic communication with *IDN?",
    )
    _add_scope_connection_args(identify_parser)

    check_error_parser = subparsers.add_parser(
        "check-error",
        help="read the oscilloscope system error queue",
    )
    _add_scope_connection_args(check_error_parser)
    check_error_parser.add_argument(
        "--all",
        dest="drain",
        action="store_true",
        help="read until no error is returned or --max-reads is reached",
    )
    check_error_parser.add_argument(
        "--max-reads",
        type=_positive_int,
        default=30,
        help="maximum reads when --all is used",
    )

    system_clear_status_parser = subparsers.add_parser(
        "system-clear-status",
        allow_abbrev=False,
        help="clear status and event data with *CLS",
    )
    _add_scope_connection_args(system_clear_status_parser)

    cleanup_parser = subparsers.add_parser(
        "cleanup",
        allow_abbrev=False,
        help="clear common automation leftovers without resetting the instrument",
    )
    _add_scope_connection_args(cleanup_parser)
    cleanup_parser.add_argument(
        "--profile",
        choices=CLEANUP_PROFILES,
        default="minimal",
        help="cleanup profile; defaults to minimal",
    )

    for command, help_text in (
        ("system-opc", "query operation completion with *OPC?"),
        ("system-status-byte", "query the status byte with *STB?"),
        ("system-standard-event", "destructively read the standard event register"),
        ("system-operation-status", "query the operation condition register"),
        ("system-options", "query installed option tokens with *OPT?"),
    ):
        command_parser = subparsers.add_parser(
            command, allow_abbrev=False, help=help_text
        )
        _add_scope_connection_args(command_parser)
        command_parser.add_argument("--query", action="store_true", required=True)

    run_parser = subparsers.add_parser("run", help="start repetitive acquisitions")
    _add_scope_connection_args(run_parser)

    stop_acquisition_parser = subparsers.add_parser(
        "stop-acquisition", help="stop acquisitions"
    )
    _add_scope_connection_args(stop_acquisition_parser)

    single_parser = subparsers.add_parser(
        "single",
        help="start one single acquisition without waiting",
    )
    _add_scope_connection_args(single_parser)

    force_trigger_parser = subparsers.add_parser(
        "force-trigger",
        help="force one trigger event without waiting for acquisition completion",
    )
    _add_scope_connection_args(force_trigger_parser)

    channel_summary_parser = subparsers.add_parser(
        "channel-summary",
        help="query common setup fields for all analog channels",
    )
    _add_scope_connection_args(channel_summary_parser)

    channel_display_parser = subparsers.add_parser(
        "channel-display",
        help="enable, disable, or query one analog channel display",
    )
    _add_scope_connection_args(channel_display_parser)
    channel_display_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="analog channel number, validated against the detected scope model",
    )
    display_action = channel_display_parser.add_mutually_exclusive_group(required=True)
    display_action.add_argument(
        "--on",
        dest="display_action",
        action="store_const",
        const="on",
        help="turn the channel display on",
    )
    display_action.add_argument(
        "--off",
        dest="display_action",
        action="store_const",
        const="off",
        help="turn the channel display off",
    )
    display_action.add_argument(
        "--query",
        dest="display_action",
        action="store_const",
        const="query",
        help="query the channel display state",
    )

    channel_label_parser = subparsers.add_parser(
        "channel-label",
        help="set or query one analog channel label",
    )
    _add_scope_connection_args(channel_label_parser)
    channel_label_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="analog channel number, validated against the detected scope model",
    )
    label_action = channel_label_parser.add_mutually_exclusive_group(required=True)
    label_action.add_argument(
        "--text",
        dest="label_text",
        help="channel label text",
    )
    label_action.add_argument(
        "--query",
        dest="label_query",
        action="store_true",
        help="query the channel label text",
    )

    channel_scale_parser = subparsers.add_parser(
        "channel-scale",
        help="set or query one analog channel vertical scale",
    )
    _add_scope_connection_args(channel_scale_parser)
    channel_scale_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="analog channel number, validated against the detected scope model",
    )
    scale_action = channel_scale_parser.add_mutually_exclusive_group(required=True)
    scale_action.add_argument(
        "--volts-per-division",
        dest="scale_value",
        type=_positive_float,
        help="vertical scale in volts per division",
    )
    scale_action.add_argument(
        "--query",
        dest="scale_query",
        action="store_true",
        help="query the channel vertical scale",
    )

    channel_offset_parser = subparsers.add_parser(
        "channel-offset",
        help="set or query one analog channel vertical offset",
    )
    _add_scope_connection_args(channel_offset_parser)
    channel_offset_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="analog channel number, validated against the detected scope model",
    )
    offset_action = channel_offset_parser.add_mutually_exclusive_group(required=True)
    offset_action.add_argument(
        "--volts",
        dest="offset_value",
        type=_finite_float,
        help="vertical offset in volts",
    )
    offset_action.add_argument(
        "--query",
        dest="offset_query",
        action="store_true",
        help="query the channel vertical offset",
    )

    channel_coupling_parser = subparsers.add_parser(
        "channel-coupling",
        help="set or query one analog channel input coupling",
    )
    _add_scope_connection_args(channel_coupling_parser)
    channel_coupling_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="analog channel number, validated against the detected scope model",
    )
    coupling_action = channel_coupling_parser.add_mutually_exclusive_group(required=True)
    coupling_action.add_argument(
        "--coupling",
        dest="coupling_value",
        choices=("ac", "dc"),
        help="input coupling",
    )
    coupling_action.add_argument(
        "--query",
        dest="coupling_query",
        action="store_true",
        help="query the channel input coupling",
    )

    channel_probe_parser = subparsers.add_parser(
        "channel-probe",
        help="set or query one analog channel probe ratio",
    )
    _add_scope_connection_args(channel_probe_parser)
    channel_probe_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="analog channel number, validated against the detected scope model",
    )
    probe_action = channel_probe_parser.add_mutually_exclusive_group(required=True)
    probe_action.add_argument(
        "--ratio",
        dest="probe_ratio",
        type=_probe_ratio_float,
        help="probe attenuation ratio, such as 1, 10, or 100",
    )
    probe_action.add_argument(
        "--query",
        dest="probe_query",
        action="store_true",
        help="query the channel probe ratio",
    )

    channel_bandwidth_limit_parser = subparsers.add_parser(
        "channel-bandwidth-limit",
        help="enable, disable, or query one analog channel bandwidth limit",
    )
    _add_scope_connection_args(channel_bandwidth_limit_parser)
    channel_bandwidth_limit_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="analog channel number, validated against the detected scope model",
    )
    bandwidth_action = channel_bandwidth_limit_parser.add_mutually_exclusive_group(
        required=True
    )
    bandwidth_action.add_argument(
        "--on",
        dest="bandwidth_action",
        action="store_const",
        const="on",
        help="turn the channel bandwidth limit on",
    )
    bandwidth_action.add_argument(
        "--off",
        dest="bandwidth_action",
        action="store_const",
        const="off",
        help="turn the channel bandwidth limit off",
    )
    bandwidth_action.add_argument(
        "--query",
        dest="bandwidth_action",
        action="store_const",
        const="query",
        help="query the channel bandwidth limit state",
    )

    channel_impedance_parser = subparsers.add_parser(
        "channel-impedance",
        help="set or query one analog channel input impedance",
    )
    _add_scope_connection_args(channel_impedance_parser)
    channel_impedance_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="analog channel number, validated against the detected scope model",
    )
    impedance_action = channel_impedance_parser.add_mutually_exclusive_group(required=True)
    impedance_action.add_argument(
        "--impedance",
        dest="impedance_value",
        choices=("one-meg", "fifty"),
        help="input impedance",
    )
    impedance_action.add_argument(
        "--query",
        dest="impedance_query",
        action="store_true",
        help="query the channel input impedance",
    )
    channel_impedance_parser.add_argument(
        "--allow-50-ohm",
        action="store_true",
        help="required before setting 50 ohm input impedance",
    )

    channel_invert_parser = subparsers.add_parser(
        "channel-invert",
        help="enable, disable, or query one analog channel inversion",
    )
    _add_scope_connection_args(channel_invert_parser)
    channel_invert_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="analog channel number, validated against the detected scope model",
    )
    invert_action = channel_invert_parser.add_mutually_exclusive_group(required=True)
    invert_action.add_argument("--on", dest="invert_action", action="store_const", const="on", help="turn channel inversion on")
    invert_action.add_argument("--off", dest="invert_action", action="store_const", const="off", help="turn channel inversion off")
    invert_action.add_argument("--query", dest="invert_action", action="store_const", const="query", help="query channel inversion")

    channel_range_parser = subparsers.add_parser(
        "channel-range",
        allow_abbrev=False,
        help="set or query one analog channel full-scale range",
    )
    _add_scope_connection_args(channel_range_parser)
    channel_range_parser.add_argument("--channel", type=_positive_int, required=True, help="analog channel number, validated against the detected scope model")
    range_action = channel_range_parser.add_mutually_exclusive_group(required=True)
    range_action.add_argument("--volts-full-scale", dest="range_value", type=_positive_float, help="full-scale range in volts")
    range_action.add_argument("--query", dest="range_query", action="store_true", help="query the channel full-scale range")

    channel_units_parser = subparsers.add_parser(
        "channel-units",
        help="set or query one analog channel units",
    )
    _add_scope_connection_args(channel_units_parser)
    channel_units_parser.add_argument("--channel", type=_positive_int, required=True, help="analog channel number, validated against the detected scope model")
    units_action = channel_units_parser.add_mutually_exclusive_group(required=True)
    units_action.add_argument("--units", dest="units_value", choices=("volt", "amp"), help="channel units")
    units_action.add_argument("--query", dest="units_query", action="store_true", help="query channel units")

    channel_vernier_parser = subparsers.add_parser(
        "channel-vernier",
        help="enable, disable, or query one analog channel vernier scaling",
    )
    _add_scope_connection_args(channel_vernier_parser)
    channel_vernier_parser.add_argument("--channel", type=_positive_int, required=True, help="analog channel number, validated against the detected scope model")
    vernier_action = channel_vernier_parser.add_mutually_exclusive_group(required=True)
    vernier_action.add_argument("--on", dest="vernier_action", action="store_const", const="on", help="turn channel vernier on")
    vernier_action.add_argument("--off", dest="vernier_action", action="store_const", const="off", help="turn channel vernier off")
    vernier_action.add_argument("--query", dest="vernier_action", action="store_const", const="query", help="query channel vernier")

    channel_probe_skew_parser = subparsers.add_parser(
        "channel-probe-skew",
        help="set or query one analog channel probe skew",
    )
    _add_scope_connection_args(channel_probe_skew_parser)
    channel_probe_skew_parser.add_argument("--channel", type=_positive_int, required=True, help="analog channel number, validated against the detected scope model")
    probe_skew_action = channel_probe_skew_parser.add_mutually_exclusive_group(required=True)
    probe_skew_action.add_argument("--seconds", dest="probe_skew_seconds", type=_probe_skew_float, help="probe skew in seconds")
    probe_skew_action.add_argument("--query", dest="probe_skew_query", action="store_true", help="query probe skew")

    display_label_parser = subparsers.add_parser(
        "display-label",
        help="enable, disable, or query front-panel labels",
    )
    _add_scope_connection_args(display_label_parser)
    display_label_action = display_label_parser.add_mutually_exclusive_group(required=True)
    display_label_action.add_argument(
        "--on",
        dest="display_label_action",
        action="store_const",
        const="on",
        help="turn display labels on",
    )
    display_label_action.add_argument(
        "--off",
        dest="display_label_action",
        action="store_const",
        const="off",
        help="turn display labels off",
    )
    display_label_action.add_argument(
        "--query",
        dest="display_label_action",
        action="store_const",
        const="query",
        help="query display label state",
    )

    display_clear_parser = subparsers.add_parser(
        "display-clear",
        help="clear waveform display data and associated measurements",
    )
    _add_scope_connection_args(display_clear_parser)

    display_persistence_parser = subparsers.add_parser(
        "display-persistence",
        help="set or query display persistence",
    )
    _add_scope_connection_args(display_persistence_parser)
    display_persistence_parser.add_argument(
        "--query", action="store_true", help="query display persistence"
    )
    display_persistence_parser.add_argument(
        "--mode", help="minimum or infinite persistence"
    )
    display_persistence_parser.add_argument(
        "--seconds", type=float, help="finite persistence in seconds, 0.1-60.0"
    )

    display_intensity_parser = subparsers.add_parser(
        "display-intensity",
        help="set or query waveform display intensity",
    )
    _add_scope_connection_args(display_intensity_parser)
    display_intensity_parser.add_argument(
        "--query", action="store_true", help="query waveform intensity"
    )
    display_intensity_parser.add_argument(
        "--value", type=int, help="waveform intensity, 0-100"
    )

    display_vectors_parser = subparsers.add_parser(
        "display-vectors",
        help="turn vectors on or query vector display state",
    )
    _add_scope_connection_args(display_vectors_parser)
    display_vectors_parser.add_argument(
        "--query", action="store_true", help="query display vectors"
    )
    display_vectors_parser.add_argument(
        "--on", action="store_true", help="turn display vectors on"
    )
    display_vectors_parser.add_argument("--off", action="store_true", help=argparse.SUPPRESS)

    measure_clear_parser = subparsers.add_parser(
        "measure-clear", help="clear installed screen measurements"
    )
    _add_scope_connection_args(measure_clear_parser)

    measure_show_parser = subparsers.add_parser(
        "measure-show", help="turn measurement markers on or query their state"
    )
    _add_scope_connection_args(measure_show_parser)
    measure_show_action = measure_show_parser.add_mutually_exclusive_group(required=True)
    measure_show_action.add_argument("--on", action="store_true")
    measure_show_action.add_argument("--query", action="store_true")
    measure_show_action.add_argument("--off", action="store_true", help=argparse.SUPPRESS)

    measure_source_parser = subparsers.add_parser(
        "measure-source", help="set or query default analog measurement sources"
    )
    _add_scope_connection_args(measure_source_parser)
    measure_source_parser.add_argument("--query", action="store_true")
    measure_source_parser.add_argument("--source-channel", type=_positive_int)
    measure_source_parser.add_argument("--source2-channel", type=_positive_int)

    measure_window_parser = subparsers.add_parser(
        "measure-window", help="set or query the measurement window"
    )
    _add_scope_connection_args(measure_window_parser)
    measure_window_action = measure_window_parser.add_mutually_exclusive_group(required=True)
    measure_window_action.add_argument("--query", action="store_true")
    measure_window_action.add_argument("--window", choices=MEASUREMENT_WINDOW_CHOICES)

    dvm_enable_parser = subparsers.add_parser(
        "dvm-enable", allow_abbrev=False, help="configure or query DVM enable state"
    )
    _add_scope_connection_args(dvm_enable_parser)
    dvm_enable_parser.add_argument("--query", action="store_true")
    dvm_enable_parser.add_argument("--enabled", type=_strict_bool_arg)

    dvm_source_parser = subparsers.add_parser(
        "dvm-source", allow_abbrev=False, help="configure or query the analog DVM source"
    )
    _add_scope_connection_args(dvm_source_parser)
    dvm_source_parser.add_argument("--query", action="store_true")
    dvm_source_parser.add_argument("--channel", type=_positive_int)

    dvm_mode_parser = subparsers.add_parser(
        "dvm-mode", allow_abbrev=False, help="configure or query DVM voltage mode"
    )
    _add_scope_connection_args(dvm_mode_parser)
    dvm_mode_parser.add_argument("--query", action="store_true")
    dvm_mode_parser.add_argument("--mode", choices=DVM_MODES)

    dvm_auto_range_parser = subparsers.add_parser(
        "dvm-auto-range", allow_abbrev=False, help="configure or query DVM auto range"
    )
    _add_scope_connection_args(dvm_auto_range_parser)
    dvm_auto_range_parser.add_argument("--query", action="store_true")
    dvm_auto_range_parser.add_argument("--enabled", type=_strict_bool_arg)

    dvm_current_parser = subparsers.add_parser(
        "dvm-current", allow_abbrev=False, help="query the current DVM voltage reading"
    )
    _add_scope_connection_args(dvm_current_parser)
    dvm_current_parser.add_argument("--query", action="store_true", required=True)

    dvm_query_parser = subparsers.add_parser(
        "dvm-query", allow_abbrev=False, help="query aggregate DVM Common Pack v1 state"
    )
    _add_scope_connection_args(dvm_query_parser)
    dvm_query_parser.add_argument("--query", action="store_true", required=True)

    demo_query_parser = subparsers.add_parser(
        "demo-query", allow_abbrev=False, help="query aggregate Demo Output Pack v1 state"
    )
    _add_scope_connection_args(demo_query_parser)

    demo_output_parser = subparsers.add_parser(
        "demo-output", allow_abbrev=False, help="configure or query built-in DEMO output"
    )
    _add_scope_connection_args(demo_output_parser)
    demo_output_action = demo_output_parser.add_mutually_exclusive_group(required=True)
    demo_output_action.add_argument("--query", action="store_true")
    demo_output_action.add_argument("--enabled", type=_strict_bool_arg)

    demo_function_parser = subparsers.add_parser(
        "demo-function", allow_abbrev=False, help="configure or query built-in DEMO function"
    )
    _add_scope_connection_args(demo_function_parser)
    demo_function_action = demo_function_parser.add_mutually_exclusive_group(required=True)
    demo_function_action.add_argument("--query", action="store_true")
    demo_function_action.add_argument("--function", choices=DEMO_FUNCTIONS)

    demo_phase_parser = subparsers.add_parser(
        "demo-phase", allow_abbrev=False, help="configure or query built-in DEMO phase"
    )
    _add_scope_connection_args(demo_phase_parser)
    demo_phase_action = demo_phase_parser.add_mutually_exclusive_group(required=True)
    demo_phase_action.add_argument("--query", action="store_true")
    demo_phase_action.add_argument("--degrees", type=float)

    wgen_query_parser = subparsers.add_parser(
        "wgen-query", allow_abbrev=False, help="query aggregate WGEN Basic P1 state"
    )
    _add_scope_connection_args(wgen_query_parser)

    wgen_output_parser = subparsers.add_parser(
        "wgen-output", allow_abbrev=False, help="configure or query WGEN output"
    )
    _add_scope_connection_args(wgen_output_parser)
    wgen_output_action = wgen_output_parser.add_mutually_exclusive_group(required=True)
    wgen_output_action.add_argument("--query", action="store_true")
    wgen_output_action.add_argument("--enabled", type=_strict_bool_arg)

    wgen_function_parser = subparsers.add_parser(
        "wgen-function", allow_abbrev=False, help="configure or query WGEN function"
    )
    _add_scope_connection_args(wgen_function_parser)
    wgen_function_action = wgen_function_parser.add_mutually_exclusive_group(required=True)
    wgen_function_action.add_argument("--query", action="store_true")
    wgen_function_action.add_argument("--function", choices=WGEN_FUNCTIONS)

    wgen_frequency_parser = subparsers.add_parser(
        "wgen-frequency", allow_abbrev=False, help="configure or query WGEN frequency"
    )
    _add_scope_connection_args(wgen_frequency_parser)
    wgen_frequency_action = wgen_frequency_parser.add_mutually_exclusive_group(required=True)
    wgen_frequency_action.add_argument("--query", action="store_true")
    wgen_frequency_action.add_argument("--hz", type=float)

    wgen_voltage_parser = subparsers.add_parser(
        "wgen-voltage", allow_abbrev=False, help="configure or query WGEN amplitude"
    )
    _add_scope_connection_args(wgen_voltage_parser)
    wgen_voltage_action = wgen_voltage_parser.add_mutually_exclusive_group(required=True)
    wgen_voltage_action.add_argument("--query", action="store_true")
    wgen_voltage_action.add_argument("--amplitude", type=float)

    wgen_offset_parser = subparsers.add_parser(
        "wgen-offset", allow_abbrev=False, help="configure or query WGEN offset"
    )
    _add_scope_connection_args(wgen_offset_parser)
    wgen_offset_action = wgen_offset_parser.add_mutually_exclusive_group(required=True)
    wgen_offset_action.add_argument("--query", action="store_true")
    wgen_offset_action.add_argument("--volts", type=float)

    wgen_load_parser = subparsers.add_parser(
        "wgen-load", allow_abbrev=False, help="configure or query WGEN output load"
    )
    _add_scope_connection_args(wgen_load_parser)
    wgen_load_action = wgen_load_parser.add_mutually_exclusive_group(required=True)
    wgen_load_action.add_argument("--query", action="store_true")
    wgen_load_action.add_argument("--load", choices=WGEN_LOADS)

    serial_query_parser = subparsers.add_parser(
        "serial-query",
        allow_abbrev=False,
        help="query raw aggregate serial decode bus setup",
    )
    _add_scope_connection_args(serial_query_parser)
    serial_query_parser.add_argument("--bus", type=_positive_int, required=True)

    serial_mode_parser = subparsers.add_parser(
        "serial-mode",
        allow_abbrev=False,
        help="configure or query serial decode bus mode",
    )
    _add_scope_connection_args(serial_mode_parser)
    serial_mode_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_mode_action = serial_mode_parser.add_mutually_exclusive_group(required=True)
    serial_mode_action.add_argument("--query", action="store_true")
    serial_mode_action.add_argument("--mode", choices=SERIAL_MODES)

    serial_display_parser = subparsers.add_parser(
        "serial-display",
        allow_abbrev=False,
        help="configure or query serial decode bus display state",
    )
    _add_scope_connection_args(serial_display_parser)
    serial_display_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_display_action = serial_display_parser.add_mutually_exclusive_group(
        required=True
    )
    serial_display_action.add_argument("--query", action="store_true")
    serial_display_action.add_argument("--enabled", type=_strict_bool_arg)

    serial_lister_query_parser = subparsers.add_parser(
        "serial-lister-query",
        allow_abbrev=False,
        help="query global Serial Lister display and reference state",
    )
    _add_scope_connection_args(serial_lister_query_parser)

    serial_lister_display_parser = subparsers.add_parser(
        "serial-lister-display",
        allow_abbrev=False,
        help="configure or query global Serial Lister display selection",
    )
    _add_scope_connection_args(serial_lister_display_parser)
    serial_lister_display_action = serial_lister_display_parser.add_mutually_exclusive_group(
        required=True
    )
    serial_lister_display_action.add_argument("--query", action="store_true")
    serial_lister_display_action.add_argument(
        "--selection",
        choices=SERIAL_LISTER_DISPLAYS,
        help="canonical selection: off, bus1, bus2, or all",
    )

    serial_lister_reference_parser = subparsers.add_parser(
        "serial-lister-reference",
        allow_abbrev=False,
        help="configure or query global Serial Lister reference",
    )
    _add_scope_connection_args(serial_lister_reference_parser)
    serial_lister_reference_action = serial_lister_reference_parser.add_mutually_exclusive_group(
        required=True
    )
    serial_lister_reference_action.add_argument("--query", action="store_true")
    serial_lister_reference_action.add_argument(
        "--reference", choices=SERIAL_LISTER_REFERENCES
    )

    serial_lister_export_parser = subparsers.add_parser(
        "serial-lister-export",
        allow_abbrev=False,
        help="export host-side Serial Lister CSV data",
    )
    _add_scope_connection_args(serial_lister_export_parser)
    serial_lister_export_parser.add_argument(
        "--output",
        dest="output_path",
        required=True,
        help="host CSV output path for :LISTer:DATA? payload",
    )

    serial_uart_parser = subparsers.add_parser(
        "serial-uart", allow_abbrev=False, help="configure or query basic UART decode settings"
    )
    _add_scope_connection_args(serial_uart_parser)
    serial_uart_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_uart_parser.add_argument("--query", action="store_true")
    serial_uart_parser.add_argument("--rx-source", help=_SERIAL_SOURCE_HELP)
    serial_uart_parser.add_argument("--tx-source", help=_SERIAL_SOURCE_HELP)
    serial_uart_parser.add_argument("--baud-rate", type=int)
    serial_uart_parser.add_argument("--data-bits", type=int)
    serial_uart_parser.add_argument("--parity", choices=UART_PARITIES)
    serial_uart_parser.add_argument("--polarity", choices=UART_POLARITIES)
    serial_uart_parser.add_argument("--bit-order", choices=SERIAL_BIT_ORDERS)

    serial_uart_trigger_parser = subparsers.add_parser(
        "serial-trigger-uart",
        allow_abbrev=False,
        help="configure or query basic UART trigger criteria",
    )
    _add_scope_connection_args(serial_uart_trigger_parser)
    serial_uart_trigger_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_uart_trigger_parser.add_argument("--query", action="store_true")
    serial_uart_trigger_parser.add_argument("--type", choices=UART_TRIGGER_TYPES)
    serial_uart_trigger_parser.add_argument("--data", type=int)
    serial_uart_trigger_parser.add_argument(
        "--qualifier", choices=UART_TRIGGER_QUALIFIERS
    )

    serial_i2c_trigger_parser = subparsers.add_parser(
        "serial-trigger-i2c",
        allow_abbrev=False,
        help="configure or query basic I2C trigger criteria",
    )
    _add_scope_connection_args(serial_i2c_trigger_parser)
    serial_i2c_trigger_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_i2c_trigger_parser.add_argument("--query", action="store_true")
    serial_i2c_trigger_parser.add_argument("--type", choices=I2C_TRIGGER_TYPES)
    serial_i2c_trigger_parser.add_argument("--address", type=_integer_value)
    serial_i2c_trigger_parser.add_argument("--data", type=_integer_value)
    serial_i2c_trigger_parser.add_argument("--data2", type=_integer_value)
    serial_i2c_trigger_parser.add_argument(
        "--qualifier", choices=I2C_TRIGGER_QUALIFIERS
    )

    serial_spi_trigger_parser = subparsers.add_parser(
        "serial-trigger-spi",
        allow_abbrev=False,
        help="configure or query basic SPI trigger criteria",
    )
    _add_scope_connection_args(serial_spi_trigger_parser)
    serial_spi_trigger_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_spi_trigger_parser.add_argument("--query", action="store_true")
    serial_spi_trigger_parser.add_argument("--type", choices=SPI_TRIGGER_TYPES)
    serial_spi_trigger_parser.add_argument("--width", type=int)
    serial_spi_trigger_parser.add_argument("--data")

    serial_can_trigger_parser = subparsers.add_parser(
        "serial-trigger-can",
        allow_abbrev=False,
        help="configure or query basic CAN trigger criteria",
    )
    _add_scope_connection_args(serial_can_trigger_parser)
    serial_can_trigger_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_can_trigger_parser.add_argument("--query", action="store_true")
    serial_can_trigger_parser.add_argument("--type", choices=CAN_TRIGGER_TYPES)
    serial_can_trigger_parser.add_argument("--id")
    serial_can_trigger_parser.add_argument("--id-mode", choices=CAN_TRIGGER_ID_MODES)
    serial_can_trigger_parser.add_argument("--data")
    serial_can_trigger_parser.add_argument("--data-length", type=int)

    serial_i2c_parser = subparsers.add_parser(
        "serial-i2c", allow_abbrev=False, help="configure or query basic I2C decode settings"
    )
    _add_scope_connection_args(serial_i2c_parser)
    serial_i2c_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_i2c_parser.add_argument("--query", action="store_true")
    serial_i2c_parser.add_argument("--clock-source", help=_SERIAL_SOURCE_HELP)
    serial_i2c_parser.add_argument("--data-source", help=_SERIAL_SOURCE_HELP)
    serial_i2c_parser.add_argument("--address-size", choices=I2C_ADDRESS_SIZES)

    serial_spi_parser = subparsers.add_parser(
        "serial-spi", allow_abbrev=False, help="configure or query basic SPI decode settings"
    )
    _add_scope_connection_args(serial_spi_parser)
    serial_spi_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_spi_parser.add_argument("--query", action="store_true")
    serial_spi_parser.add_argument("--clock-source", help=_SERIAL_SOURCE_HELP)
    serial_spi_parser.add_argument("--mosi-source", help=_SERIAL_SOURCE_HELP)
    serial_spi_parser.add_argument("--miso-source", help=_SERIAL_SOURCE_HELP)
    serial_spi_parser.add_argument("--frame-source", help=_SERIAL_SOURCE_HELP)
    serial_spi_parser.add_argument("--clock-slope", choices=SPI_CLOCK_SLOPES)
    serial_spi_parser.add_argument("--bit-order", choices=SERIAL_BIT_ORDERS)
    serial_spi_parser.add_argument("--word-width", type=int)
    serial_spi_parser.add_argument(
        "--framing",
        choices=SPI_FRAMINGS,
        help="canonical framing: chip-select, no-chip-select, or timeout",
    )
    serial_spi_parser.add_argument(
        "--clock-timeout",
        type=float,
        help=(
            "SPI clock timeout; only valid when the same configure request "
            "also provides --framing timeout"
        ),
    )

    serial_can_parser = subparsers.add_parser(
        "serial-can", allow_abbrev=False, help="configure or query basic CAN decode settings"
    )
    _add_scope_connection_args(serial_can_parser)
    serial_can_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_can_parser.add_argument("--query", action="store_true")
    serial_can_parser.add_argument("--source", help=_SERIAL_SOURCE_HELP)
    serial_can_parser.add_argument("--baud-rate", type=int)
    serial_can_parser.add_argument("--signal-definition", choices=CAN_SIGNAL_DEFINITIONS)
    serial_can_parser.add_argument("--sample-point", type=float)

    search_state_parser = subparsers.add_parser(
        "search-state", allow_abbrev=False, help="configure or query waveform search state"
    )
    _add_scope_connection_args(search_state_parser)
    search_state_parser.add_argument("--query", action="store_true")
    search_state_parser.add_argument("--enabled", type=_strict_bool_arg)

    search_mode_parser = subparsers.add_parser(
        "search-mode", allow_abbrev=False, help="configure or query waveform search mode"
    )
    _add_scope_connection_args(search_mode_parser)
    search_mode_parser.add_argument("--query", action="store_true")
    search_mode_parser.add_argument("--mode", choices=SEARCH_MODES)

    search_count_parser = subparsers.add_parser(
        "search-count", allow_abbrev=False, help="query waveform search event count"
    )
    _add_scope_connection_args(search_count_parser)
    search_count_parser.add_argument("--query", action="store_true", required=True)

    search_event_parser = subparsers.add_parser(
        "search-event", allow_abbrev=False, help="configure or query selected search event"
    )
    _add_scope_connection_args(search_event_parser)
    search_event_action = search_event_parser.add_mutually_exclusive_group(required=True)
    search_event_action.add_argument("--query", action="store_true")
    search_event_action.add_argument("--event", type=_positive_int)

    serial_search_uart_parser = subparsers.add_parser(
        "serial-search-uart",
        allow_abbrev=False,
        help="configure or query UART search criteria",
    )
    _add_scope_connection_args(serial_search_uart_parser)
    serial_search_uart_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_search_uart_parser.add_argument("--query", action="store_true")
    serial_search_uart_parser.add_argument("--mode", choices=UART_SEARCH_MODES)
    serial_search_uart_parser.add_argument("--data", type=int)
    serial_search_uart_parser.add_argument("--qualifier", choices=SEARCH_QUALIFIERS)

    serial_search_i2c_parser = subparsers.add_parser(
        "serial-search-i2c",
        allow_abbrev=False,
        help="configure or query I2C search criteria",
    )
    _add_scope_connection_args(serial_search_i2c_parser)
    serial_search_i2c_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_search_i2c_parser.add_argument("--query", action="store_true")
    serial_search_i2c_parser.add_argument("--mode", choices=I2C_SEARCH_MODES)
    serial_search_i2c_parser.add_argument("--address", type=int)
    serial_search_i2c_parser.add_argument("--data", type=int)
    serial_search_i2c_parser.add_argument("--data2", type=int)
    serial_search_i2c_parser.add_argument("--qualifier", choices=SEARCH_QUALIFIERS)

    serial_search_spi_parser = subparsers.add_parser(
        "serial-search-spi",
        allow_abbrev=False,
        help="configure or query SPI search criteria",
    )
    _add_scope_connection_args(serial_search_spi_parser)
    serial_search_spi_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_search_spi_parser.add_argument("--query", action="store_true")
    serial_search_spi_parser.add_argument("--mode", choices=SPI_SEARCH_MODES)
    serial_search_spi_parser.add_argument("--data")
    serial_search_spi_parser.add_argument("--width", type=int)

    serial_search_can_parser = subparsers.add_parser(
        "serial-search-can",
        allow_abbrev=False,
        help="configure or query CAN search criteria",
    )
    _add_scope_connection_args(serial_search_can_parser)
    serial_search_can_parser.add_argument("--bus", type=_positive_int, required=True)
    serial_search_can_parser.add_argument("--query", action="store_true")
    serial_search_can_parser.add_argument("--mode", choices=CAN_SEARCH_MODES)
    serial_search_can_parser.add_argument("--data")
    serial_search_can_parser.add_argument("--data-length", type=int)
    serial_search_can_parser.add_argument("--id")
    serial_search_can_parser.add_argument("--id-mode", choices=CAN_SEARCH_ID_MODES)

    save_pwd_parser = subparsers.add_parser(
        "save-pwd", allow_abbrev=False, help="configure or query the instrument save directory"
    )
    _add_scope_connection_args(save_pwd_parser)
    save_pwd_action = save_pwd_parser.add_mutually_exclusive_group(required=True)
    save_pwd_action.add_argument("--query", action="store_true")
    save_pwd_action.add_argument("--path")

    save_filename_parser = subparsers.add_parser(
        "save-filename", allow_abbrev=False, help="configure or query the instrument save base name"
    )
    _add_scope_connection_args(save_filename_parser)
    save_filename_action = save_filename_parser.add_mutually_exclusive_group(required=True)
    save_filename_action.add_argument("--query", action="store_true")
    save_filename_action.add_argument("--name")

    save_image_format_parser = subparsers.add_parser(
        "save-image-format", allow_abbrev=False, help="configure or query instrument image save format"
    )
    _add_scope_connection_args(save_image_format_parser)
    save_image_format_action = save_image_format_parser.add_mutually_exclusive_group(
        required=True
    )
    save_image_format_action.add_argument("--query", action="store_true")
    save_image_format_action.add_argument("--format", choices=SAVE_IMAGE_FORMATS)

    save_image_palette_parser = subparsers.add_parser(
        "save-image-palette", allow_abbrev=False, help="configure or query instrument image palette"
    )
    _add_scope_connection_args(save_image_palette_parser)
    save_image_palette_action = save_image_palette_parser.add_mutually_exclusive_group(
        required=True
    )
    save_image_palette_action.add_argument("--query", action="store_true")
    save_image_palette_action.add_argument("--palette", choices=SAVE_IMAGE_PALETTES)

    for command, help_text in (
        ("save-image-ink-saver", "configure or query instrument image ink saver"),
        ("save-image-factors", "configure or query instrument image factors"),
    ):
        setting_parser = subparsers.add_parser(
            command, allow_abbrev=False, help=help_text
        )
        _add_scope_connection_args(setting_parser)
        action = setting_parser.add_mutually_exclusive_group(required=True)
        action.add_argument("--query", action="store_true")
        action.add_argument("--enabled", type=_strict_bool_arg)

    save_image_parser = subparsers.add_parser(
        "save-image", allow_abbrev=False, help="save an image on instrument-side storage"
    )
    _add_scope_connection_args(save_image_parser)
    save_image_parser.add_argument("--filename", required=True)

    save_waveform_format_parser = subparsers.add_parser(
        "save-waveform-format",
        allow_abbrev=False,
        help="configure or query instrument waveform save format",
    )
    _add_scope_connection_args(save_waveform_format_parser)
    save_waveform_format_action = save_waveform_format_parser.add_mutually_exclusive_group(
        required=True
    )
    save_waveform_format_action.add_argument("--query", action="store_true")
    save_waveform_format_action.add_argument("--format", choices=SAVE_WAVEFORM_FORMATS)

    save_waveform_length_parser = subparsers.add_parser(
        "save-waveform-length",
        allow_abbrev=False,
        help="configure or query instrument waveform save length",
    )
    _add_scope_connection_args(save_waveform_length_parser)
    save_waveform_length_action = save_waveform_length_parser.add_mutually_exclusive_group(
        required=True
    )
    save_waveform_length_action.add_argument("--query", action="store_true")
    save_waveform_length_action.add_argument("--points", type=int)

    save_waveform_length_max_parser = subparsers.add_parser(
        "save-waveform-length-max",
        allow_abbrev=False,
        help="query maximum-length waveform save mode",
    )
    _add_scope_connection_args(save_waveform_length_max_parser)
    save_waveform_length_max_parser.add_argument(
        "--query", action="store_true", required=True
    )

    save_waveform_parser = subparsers.add_parser(
        "save-waveform", allow_abbrev=False, help="save waveform data on instrument-side storage"
    )
    _add_scope_connection_args(save_waveform_parser)
    save_waveform_parser.add_argument("--filename", required=True)

    reference_save_parser = subparsers.add_parser(
        "reference-save", help="copy an analog channel into a reference waveform slot"
    )
    _add_scope_connection_args(reference_save_parser)
    reference_save_parser.add_argument("--slot", type=_positive_int, required=True)
    reference_save_parser.add_argument("--source-channel", type=_positive_int, required=True)

    reference_display_parser = subparsers.add_parser(
        "reference-display", help="set or query reference waveform display state"
    )
    _add_scope_connection_args(reference_display_parser)
    reference_display_parser.add_argument("--slot", type=_positive_int, required=True)
    reference_display_action = reference_display_parser.add_mutually_exclusive_group(required=True)
    reference_display_action.add_argument("--query", action="store_true")
    reference_display_action.add_argument("--state", choices=("on", "off"))

    reference_label_parser = subparsers.add_parser(
        "reference-label", help="set or query a reference waveform label"
    )
    _add_scope_connection_args(reference_label_parser)
    reference_label_parser.add_argument("--slot", type=_positive_int, required=True)
    reference_label_action = reference_label_parser.add_mutually_exclusive_group(required=True)
    reference_label_action.add_argument("--query", action="store_true")
    reference_label_action.add_argument("--text")

    reference_clear_parser = subparsers.add_parser(
        "reference-clear", help="clear a reference waveform slot"
    )
    _add_scope_connection_args(reference_clear_parser)
    reference_clear_parser.add_argument("--slot", type=_positive_int, required=True)

    reference_query_parser = subparsers.add_parser(
        "reference-query", help="query reference waveform display and label state"
    )
    _add_scope_connection_args(reference_query_parser)
    reference_query_parser.add_argument("--slot", type=_positive_int, required=True)

    annotation_parser = subparsers.add_parser(
        "annotation",
        help="set, clear, or query display annotation text",
    )
    _add_scope_connection_args(annotation_parser)
    annotation_parser.add_argument(
        "--slot",
        type=_positive_int,
        default=1,
        help="annotation slot; 4000X supports 1-10, 2000X/3000X support 1",
    )
    annotation_parser.add_argument("--query", action="store_true", help="query annotation state")
    annotation_parser.add_argument("--on", action="store_true", help="turn annotation on")
    annotation_parser.add_argument("--off", action="store_true", help="turn annotation off")
    annotation_parser.add_argument("--text", help="annotation text")
    annotation_parser.add_argument("--clear", action="store_true", help="clear annotation text")
    annotation_parser.add_argument("--color", help="annotation text color")
    annotation_parser.add_argument("--background", help="annotation background color")
    annotation_parser.add_argument("--x", type=_nonnegative_int, help="4000X annotation x position, 0-800")
    annotation_parser.add_argument("--y", type=_nonnegative_int, help="4000X annotation y position, 0-480")

    timebase_scale_parser = subparsers.add_parser(
        "timebase-scale",
        help="set or query horizontal scale",
    )
    _add_scope_connection_args(timebase_scale_parser)
    scale_action = timebase_scale_parser.add_mutually_exclusive_group(required=True)
    scale_action.add_argument(
        "--seconds-per-division",
        dest="timebase_scale_value",
        type=_positive_timebase_float,
        help="horizontal scale in seconds per division",
    )
    scale_action.add_argument(
        "--query",
        dest="timebase_scale_query",
        action="store_true",
        help="query the horizontal scale",
    )

    timebase_position_parser = subparsers.add_parser(
        "timebase-position",
        help="set or query horizontal position",
    )
    _add_scope_connection_args(timebase_position_parser)
    position_action = timebase_position_parser.add_mutually_exclusive_group(required=True)
    position_action.add_argument(
        "--seconds",
        dest="timebase_position_value",
        type=_finite_timebase_float,
        help="horizontal position in seconds",
    )
    position_action.add_argument(
        "--query",
        dest="timebase_position_query",
        action="store_true",
        help="query the horizontal position",
    )

    edge_trigger_parser = subparsers.add_parser(
        "trigger-edge",
        help="configure or query analog edge trigger settings",
    )
    _add_scope_connection_args(edge_trigger_parser)
    edge_trigger_parser.add_argument(
        "--query",
        dest="edge_query",
        action="store_true",
        help="query analog edge trigger source, level, and slope",
    )
    edge_trigger_parser.add_argument(
        "--source-channel",
        type=_positive_int,
        default=None,
        help="analog channel used as the edge trigger source",
    )
    edge_trigger_parser.add_argument(
        "--level",
        type=_trigger_level_float,
        default=None,
        help="edge trigger level in volts",
    )
    edge_trigger_parser.add_argument(
        "--slope",
        choices=("positive", "negative", "either", "alternate"),
        default=None,
        help="edge trigger slope",
    )

    edge_trigger_source_parser = subparsers.add_parser(
        "trigger-edge-source",
        allow_abbrev=False,
        help="configure or query the Edge Trigger source only",
    )
    _add_scope_connection_args(edge_trigger_source_parser)
    edge_trigger_source_parser.add_argument(
        "--query",
        dest="trigger_edge_source_query",
        action="store_true",
        help="query the Edge Trigger source",
    )
    edge_trigger_source_parser.add_argument(
        "--source-channel",
        type=_positive_int,
        default=None,
        help="analog channel used as the Edge Trigger source",
    )
    edge_trigger_source_parser.add_argument(
        "--source",
        choices=("external", "line"),
        default=None,
        help="non-analog Edge Trigger source",
    )

    edge_trigger_slope_parser = subparsers.add_parser(
        "trigger-edge-slope",
        allow_abbrev=False,
        help="configure or query Edge Trigger slope only",
    )
    _add_scope_connection_args(edge_trigger_slope_parser)
    edge_trigger_slope_parser.add_argument(
        "--query",
        dest="trigger_edge_slope_query",
        action="store_true",
        help="query Edge Trigger slope",
    )
    edge_trigger_slope_parser.add_argument(
        "--slope",
        choices=("positive", "negative", "either", "alternate"),
        default=None,
        help="Edge Trigger slope",
    )

    edge_trigger_level_parser = subparsers.add_parser(
        "trigger-edge-level",
        allow_abbrev=False,
        help="configure or query one analog Edge Trigger level only",
    )
    _add_scope_connection_args(edge_trigger_level_parser)
    edge_trigger_level_parser.add_argument(
        "--query",
        dest="trigger_edge_level_query",
        action="store_true",
        help="query the named analog Edge Trigger level",
    )
    edge_trigger_level_parser.add_argument(
        "--source-channel",
        type=_positive_int,
        default=None,
        help="named analog channel for the Edge Trigger level",
    )
    edge_trigger_level_parser.add_argument(
        "--level-volts",
        type=float,
        default=None,
        help="Edge Trigger level in volts for the named analog channel",
    )

    external_trigger_range_parser = subparsers.add_parser(
        "external-trigger-range",
        allow_abbrev=False,
        help="configure or query the dedicated External trigger input range",
    )
    _add_scope_connection_args(external_trigger_range_parser)
    external_trigger_range_parser.add_argument(
        "--query",
        dest="external_trigger_range_query",
        action="store_true",
        help="query the External trigger input range",
    )
    external_trigger_range_parser.add_argument(
        "--range-volts",
        type=float,
        default=None,
        help="External trigger input range in volts",
    )

    edge_trigger_external_level_parser = subparsers.add_parser(
        "trigger-edge-external-level",
        allow_abbrev=False,
        help="configure or query the External-qualified Edge Trigger level",
    )
    _add_scope_connection_args(edge_trigger_external_level_parser)
    edge_trigger_external_level_parser.add_argument(
        "--query",
        dest="trigger_edge_external_level_query",
        action="store_true",
        help="query the External-qualified Edge Trigger level",
    )
    edge_trigger_external_level_parser.add_argument(
        "--level-volts",
        type=float,
        default=None,
        help="External-qualified Edge Trigger level in volts",
    )

    external_trigger_probe_parser = subparsers.add_parser(
        "external-trigger-probe",
        allow_abbrev=False,
        help="configure or query the External trigger probe attenuation",
    )
    _add_scope_connection_args(external_trigger_probe_parser)
    external_trigger_probe_parser.add_argument(
        "--query",
        dest="external_trigger_probe_query",
        action="store_true",
        help="query the External trigger probe attenuation",
    )
    external_trigger_probe_parser.add_argument(
        "--attenuation",
        type=float,
        default=None,
        help="External trigger probe attenuation",
    )

    external_trigger_units_parser = subparsers.add_parser(
        "external-trigger-units",
        allow_abbrev=False,
        help="configure or query the External trigger input units",
    )
    _add_scope_connection_args(external_trigger_units_parser)
    external_trigger_units_parser.add_argument(
        "--query",
        dest="external_trigger_units_query",
        action="store_true",
        help="query the External trigger input units",
    )
    external_trigger_units_parser.add_argument(
        "--units",
        choices=("volts", "amps"),
        default=None,
        help="External trigger input units",
    )

    external_trigger_settings_parser = subparsers.add_parser(
        "external-trigger-settings",
        allow_abbrev=False,
        help="query aggregate External trigger input settings",
    )
    _add_scope_connection_args(external_trigger_settings_parser)
    external_trigger_settings_parser.add_argument(
        "--query",
        action="store_true",
        required=True,
        help="query aggregate External trigger input settings",
    )

    trigger_sweep_parser = subparsers.add_parser(
        "trigger-sweep",
        allow_abbrev=False,
        help="configure or query common trigger sweep mode",
    )
    _add_scope_connection_args(trigger_sweep_parser)
    trigger_sweep_parser.add_argument(
        "--query",
        dest="trigger_sweep_query",
        action="store_true",
        help="query trigger sweep mode",
    )
    trigger_sweep_parser.add_argument(
        "--mode",
        choices=("auto", "normal"),
        default=None,
        help="trigger sweep mode",
    )

    trigger_noise_reject_parser = subparsers.add_parser(
        "trigger-noise-reject",
        allow_abbrev=False,
        help="configure or query common trigger noise reject",
    )
    _add_scope_connection_args(trigger_noise_reject_parser)
    trigger_noise_reject_parser.add_argument(
        "--query",
        dest="trigger_noise_reject_query",
        action="store_true",
        help="query trigger noise reject",
    )
    trigger_noise_reject_parser.add_argument(
        "--enabled",
        type=_strict_bool_arg,
        default=None,
        help="true to enable noise reject, false to disable it",
    )

    trigger_hf_reject_parser = subparsers.add_parser(
        "trigger-hf-reject",
        allow_abbrev=False,
        help="configure or query common trigger high-frequency reject",
    )
    _add_scope_connection_args(trigger_hf_reject_parser)
    trigger_hf_reject_parser.add_argument(
        "--query",
        dest="trigger_hf_reject_query",
        action="store_true",
        help="query trigger high-frequency reject",
    )
    trigger_hf_reject_parser.add_argument(
        "--enabled",
        type=_strict_bool_arg,
        default=None,
        help="true to enable high-frequency reject, false to disable it",
    )

    trigger_edge_coupling_parser = subparsers.add_parser(
        "trigger-edge-coupling",
        allow_abbrev=False,
        help="configure or query Edge Trigger coupling",
    )
    _add_scope_connection_args(trigger_edge_coupling_parser)
    trigger_edge_coupling_parser.add_argument(
        "--query",
        dest="trigger_edge_coupling_query",
        action="store_true",
        help="query Edge Trigger coupling",
    )
    trigger_edge_coupling_parser.add_argument(
        "--coupling",
        choices=("ac", "dc", "lf-reject"),
        default=None,
        help="Edge Trigger coupling mode",
    )

    trigger_edge_reject_parser = subparsers.add_parser(
        "trigger-edge-reject",
        allow_abbrev=False,
        help="configure or query Edge Trigger reject filter",
    )
    _add_scope_connection_args(trigger_edge_reject_parser)
    trigger_edge_reject_parser.add_argument(
        "--query",
        dest="trigger_edge_reject_query",
        action="store_true",
        help="query Edge Trigger reject filter",
    )
    trigger_edge_reject_parser.add_argument(
        "--reject",
        choices=("off", "lf-reject", "hf-reject"),
        default=None,
        help="Edge Trigger reject filter",
    )

    glitch_trigger_parser = subparsers.add_parser(
        "trigger-pulse-width",
        help="configure or query analog pulse-width trigger settings",
    )
    _add_scope_connection_args(glitch_trigger_parser)
    glitch_trigger_parser.add_argument(
        "--query",
        dest="glitch_query",
        action="store_true",
        help="query pulse-width trigger state",
    )
    glitch_trigger_parser.add_argument(
        "--channel",
        type=_positive_int,
        default=None,
        help="analog channel used as the pulse-width trigger source",
    )
    glitch_trigger_parser.add_argument(
        "--polarity",
        choices=("positive", "negative"),
        default=None,
        help="pulse-width trigger pulse polarity",
    )
    glitch_trigger_parser.add_argument(
        "--qualifier",
        choices=("greater-than", "less-than", "range"),
        default=None,
        help="pulse-width trigger qualifier",
    )
    glitch_trigger_parser.add_argument(
        "--time-seconds",
        type=_positive_float,
        default=None,
        help="pulse-width threshold in seconds for greater-than or less-than qualifiers",
    )
    glitch_trigger_parser.add_argument(
        "--min-time-seconds",
        type=_positive_float,
        default=None,
        help="lower pulse-width bound in seconds for range qualifier",
    )
    glitch_trigger_parser.add_argument(
        "--max-time-seconds",
        type=_positive_float,
        default=None,
        help="upper pulse-width bound in seconds for range qualifier",
    )
    glitch_trigger_parser.add_argument(
        "--level-volts",
        type=_trigger_level_float,
        default=None,
        help="optional pulse-width trigger level in volts",
    )

    runt_trigger_parser = subparsers.add_parser(
        "trigger-runt",
        help="configure or query analog runt trigger settings",
    )
    _add_scope_connection_args(runt_trigger_parser)
    runt_trigger_parser.add_argument(
        "--query",
        dest="runt_query",
        action="store_true",
        help="query runt trigger state",
    )
    runt_trigger_parser.add_argument(
        "--channel",
        type=_positive_int,
        default=None,
        help="analog channel used as the runt trigger source",
    )
    runt_trigger_parser.add_argument(
        "--polarity",
        choices=("positive", "negative", "either"),
        default=None,
        help="runt trigger polarity",
    )
    runt_trigger_parser.add_argument(
        "--qualifier",
        choices=("greater-than", "less-than", "none"),
        default=None,
        help="runt trigger qualifier",
    )
    runt_trigger_parser.add_argument(
        "--time-seconds",
        type=_positive_float,
        default=None,
        help="runt time threshold for greater-than or less-than qualifiers",
    )
    runt_trigger_parser.add_argument(
        "--low-level-volts",
        type=_trigger_level_float,
        default=None,
        help="lower runt threshold in volts",
    )
    runt_trigger_parser.add_argument(
        "--high-level-volts",
        type=_trigger_level_float,
        default=None,
        help="upper runt threshold in volts",
    )

    transition_trigger_parser = subparsers.add_parser(
        "trigger-transition",
        help="configure or query analog transition trigger settings",
    )
    _add_scope_connection_args(transition_trigger_parser)
    transition_trigger_parser.add_argument(
        "--query",
        dest="transition_query",
        action="store_true",
        help="query transition trigger state",
    )
    transition_trigger_parser.add_argument(
        "--channel",
        type=_positive_int,
        default=None,
        help="analog channel used as the transition trigger source",
    )
    transition_trigger_parser.add_argument(
        "--slope",
        choices=("positive", "negative"),
        default=None,
        help="transition trigger slope",
    )
    transition_trigger_parser.add_argument(
        "--qualifier",
        choices=("greater-than", "less-than"),
        default=None,
        help="transition trigger qualifier",
    )
    transition_trigger_parser.add_argument(
        "--time-seconds",
        type=_positive_float,
        default=None,
        help="transition time threshold in seconds",
    )
    transition_trigger_parser.add_argument(
        "--low-level-volts",
        type=_trigger_level_float,
        default=None,
        help="lower transition threshold in volts",
    )
    transition_trigger_parser.add_argument(
        "--high-level-volts",
        type=_trigger_level_float,
        default=None,
        help="upper transition threshold in volts",
    )

    delay_trigger_parser = subparsers.add_parser(
        "trigger-delay",
        help="configure or query analog edge-then-edge delay trigger settings",
    )
    _add_scope_connection_args(delay_trigger_parser)
    delay_trigger_parser.add_argument(
        "--query",
        dest="delay_query",
        action="store_true",
        help="query delay trigger state",
    )
    delay_trigger_parser.add_argument(
        "--arm-channel",
        type=_positive_int,
        default=None,
        help="analog channel used as the delay trigger arm source",
    )
    delay_trigger_parser.add_argument(
        "--arm-slope",
        choices=("positive", "negative"),
        default=None,
        help="delay trigger arm slope",
    )
    delay_trigger_parser.add_argument(
        "--trigger-channel",
        type=_positive_int,
        default=None,
        help="analog channel used as the delay trigger source",
    )
    delay_trigger_parser.add_argument(
        "--trigger-slope",
        choices=("positive", "negative"),
        default=None,
        help="delay trigger slope",
    )
    delay_trigger_parser.add_argument(
        "--time-seconds",
        type=_positive_float,
        default=None,
        help="delay trigger time in seconds",
    )
    delay_trigger_parser.add_argument(
        "--count",
        type=_positive_int,
        default=None,
        help="Nth trigger edge count",
    )

    setup_hold_trigger_parser = subparsers.add_parser(
        "trigger-setup-hold",
        help="configure or query DSO analog setup-hold trigger settings",
    )
    _add_scope_connection_args(setup_hold_trigger_parser)
    setup_hold_trigger_parser.add_argument(
        "--query",
        dest="setup_hold_query",
        action="store_true",
        help="query setup-hold trigger state",
    )
    setup_hold_trigger_parser.add_argument(
        "--clock-channel",
        type=_positive_int,
        default=None,
        help="analog channel used as the setup-hold clock source",
    )
    setup_hold_trigger_parser.add_argument(
        "--data-channel",
        type=_positive_int,
        default=None,
        help="analog channel used as the setup-hold data source",
    )
    setup_hold_trigger_parser.add_argument(
        "--slope",
        default=None,
        help="setup-hold clock slope",
    )
    setup_hold_trigger_parser.add_argument(
        "--setup-time",
        type=float,
        default=None,
        help="setup time in seconds",
    )
    setup_hold_trigger_parser.add_argument(
        "--hold-time",
        type=float,
        default=None,
        help="hold time in seconds",
    )

    edge_burst_trigger_parser = subparsers.add_parser(
        "trigger-edge-burst",
        allow_abbrev=False,
        help="configure or query DSO analog Nth Edge Burst trigger settings",
    )
    _add_scope_connection_args(edge_burst_trigger_parser)
    edge_burst_trigger_parser.add_argument(
        "--query",
        dest="edge_burst_query",
        action="store_true",
        help="query Nth Edge Burst trigger state",
    )
    edge_burst_trigger_parser.add_argument(
        "--source-channel",
        type=_positive_int,
        default=None,
        help="analog channel used as the Nth Edge Burst trigger source",
    )
    edge_burst_trigger_parser.add_argument(
        "--slope",
        choices=("positive", "negative"),
        default=None,
        help="Nth Edge Burst trigger slope",
    )
    edge_burst_trigger_parser.add_argument(
        "--count",
        type=_positive_int,
        default=None,
        help="Nth Edge Burst edge count",
    )
    edge_burst_trigger_parser.add_argument(
        "--idle-time",
        type=float,
        default=None,
        help="Nth Edge Burst idle time in seconds",
    )
    edge_burst_trigger_parser.add_argument(
        "--level-volts",
        type=_trigger_level_float,
        default=None,
        help="optional analog edge level in volts",
    )

    tv_trigger_parser = subparsers.add_parser(
        "trigger-tv",
        allow_abbrev=False,
        help="configure or query DSO analog basic TV trigger settings",
    )
    _add_scope_connection_args(tv_trigger_parser)
    tv_trigger_parser.add_argument(
        "--query",
        dest="tv_query",
        action="store_true",
        help="query TV trigger state",
    )
    tv_trigger_parser.add_argument(
        "--source-channel",
        type=_positive_int,
        default=None,
        help="analog channel used as the TV trigger source",
    )
    tv_trigger_parser.add_argument(
        "--standard",
        choices=("ntsc", "pal", "palm", "secam"),
        default=None,
        help="basic TV trigger standard",
    )
    tv_trigger_parser.add_argument(
        "--mode",
        choices=(
            "field1",
            "field2",
            "all-fields",
            "all-lines",
            "line-field1",
            "line-field2",
            "line-alternate",
        ),
        default=None,
        help="basic TV trigger mode",
    )
    tv_trigger_parser.add_argument(
        "--polarity",
        choices=("positive", "negative"),
        default=None,
        help="TV trigger polarity",
    )
    tv_trigger_parser.add_argument(
        "--line",
        type=_positive_int,
        default=None,
        help="TV line number for line-field1, line-field2, or line-alternate",
    )

    pattern_trigger_parser = subparsers.add_parser(
        "trigger-pattern",
        help="configure or query DSO ASCII pattern trigger settings",
    )
    _add_scope_connection_args(pattern_trigger_parser)
    pattern_trigger_parser.add_argument(
        "--query",
        dest="pattern_query",
        action="store_true",
        help="query pattern trigger state",
    )
    pattern_trigger_parser.add_argument(
        "--pattern",
        dest="pattern",
        default=None,
        help="raw ASCII pattern using only 0, 1, and X",
    )

    or_trigger_parser = subparsers.add_parser(
        "trigger-or",
        help="configure or query DSO analog OR trigger settings",
    )
    _add_scope_connection_args(or_trigger_parser)
    or_trigger_parser.add_argument(
        "--query",
        dest="or_query",
        action="store_true",
        help="query OR trigger state",
    )
    or_trigger_parser.add_argument(
        "--pattern",
        dest="pattern",
        default=None,
        help="raw OR trigger edge pattern using only R, F, E, and X",
    )

    cursor_parser = subparsers.add_parser(
        "cursor",
        help="query, hide, or configure manual marker cursors",
    )
    _add_scope_connection_args(cursor_parser)
    cursor_action = cursor_parser.add_mutually_exclusive_group(required=True)
    cursor_action.add_argument("--query", dest="cursor_query", action="store_true")
    cursor_action.add_argument("--off", dest="cursor_off", action="store_true")
    cursor_action.add_argument("--x1", type=_measurement_finite_float, default=None)
    cursor_parser.add_argument("--source-channel", type=_positive_int, default=None)
    cursor_parser.add_argument("--x2", type=_measurement_finite_float, default=None)
    cursor_parser.add_argument("--y1", type=_measurement_finite_float, default=None)
    cursor_parser.add_argument("--y2", type=_measurement_finite_float, default=None)
    cursor_parser.add_argument(
        "--auto-timebase",
        action="store_true",
        help="widen horizontal scale before setting cursors if X positions are outside the visible range",
    )
    cursor_parser.add_argument(
        "--auto-vertical",
        action="store_true",
        help="adjust source channel vertical scale/offset before setting Y cursors if needed",
    )

    trigger_holdoff_parser = subparsers.add_parser(
        "trigger-holdoff",
        help="set or query trigger holdoff seconds",
    )
    _add_scope_connection_args(trigger_holdoff_parser)
    holdoff_action = trigger_holdoff_parser.add_mutually_exclusive_group(required=True)
    holdoff_action.add_argument("--query", dest="holdoff_query", action="store_true")
    holdoff_action.add_argument("--seconds", dest="holdoff_seconds", type=_holdoff_seconds_arg)

    measure_parser = subparsers.add_parser(
        "measure",
        help="query one read-only measurement item for one or two analog channels",
    )
    _add_scope_connection_args(measure_parser)
    measure_parser.add_argument(
        "--channel",
        type=_positive_int,
        default=None,
        help="analog channel number, validated against the detected scope model",
    )
    measure_parser.add_argument(
        "--source-channel",
        type=_positive_int,
        default=None,
        help="source analog channel number; --channel is a compatibility alias",
    )
    measure_parser.add_argument(
        "--reference-channel",
        type=_positive_int,
        default=None,
        help="reference analog channel number for phase or delay measurements",
    )
    measure_parser.add_argument(
        "--item",
        choices=MEASUREMENT_ITEM_CHOICES,
        required=True,
        help="measurement item to query",
    )
    measure_parser.add_argument(
        "--time",
        dest="time_s",
        type=_measurement_finite_float,
        default=None,
        help="trigger-relative time in seconds for y_at_x",
    )
    measure_parser.add_argument(
        "--level",
        type=_measurement_finite_float,
        default=None,
        help="voltage level for time_at_value",
    )
    measure_parser.add_argument(
        "--slope",
        choices=("positive", "negative"),
        default=None,
        help="edge or crossing slope for time_at_edge and time_at_value",
    )
    measure_parser.add_argument(
        "--occurrence",
        type=_positive_int,
        default=None,
        help="positive edge or crossing occurrence for time_at_edge and time_at_value",
    )

    measure_results_parser = subparsers.add_parser(
        "measure-results",
        help="query currently displayed front-panel measurement results",
    )
    _add_scope_connection_args(measure_results_parser)

    measure_stats_parser = subparsers.add_parser(
        "measure-stats",
        help="rebuild front-panel measurements and query statistics",
    )
    _add_scope_connection_args(measure_stats_parser)
    measure_stats_parser.add_argument("--channel", type=_positive_int, required=True)
    measure_stats_parser.add_argument("--items", required=True)
    measure_stats_parser.add_argument(
        "--mode",
        choices=("all", "current", "min", "max", "mean", "stddev", "count"),
        default="all",
    )
    measure_stats_parser.add_argument("--reset", action="store_true")
    measure_stats_parser.add_argument("--max-count", type=_positive_int, default=None)
    measure_stats_parser.add_argument(
        "--settle-seconds",
        type=_nonnegative_finite_float,
        default=None,
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="collect a read-only scope configuration snapshot for diagnostics",
    )
    _add_scope_connection_args(doctor_parser)

    measure_sweep_parser = subparsers.add_parser(
        "measure-sweep",
        help="query multiple read-only measurements and summarize failures",
    )
    _add_scope_connection_args(measure_sweep_parser)
    measure_sweep_parser.add_argument(
        "--channel",
        type=_capture_channel_arg,
        action="append",
        default=None,
        help="analog channel number; repeat or use all. Defaults to all channels",
    )
    measure_sweep_parser.add_argument(
        "--items",
        default="vpp,frequency,period,vrms",
        help="comma-separated single-channel measurement items",
    )
    measure_sweep_parser.add_argument(
        "--pair",
        action="append",
        default=[],
        metavar="SRC:REF",
        help="source/reference channel pair such as 1:2; repeatable",
    )
    measure_sweep_parser.add_argument(
        "--pair-items",
        default="phase,delay",
        help="comma-separated pair measurement items; only used with --pair",
    )

    capture_parser = subparsers.add_parser(
        "capture",
        help="capture one or more analog channel waveforms to CSV and metadata JSON",
    )
    _add_scope_connection_args(capture_parser)
    capture_parser.add_argument(
        "--channel",
        type=_capture_channel_arg,
        action="append",
        required=True,
        help=(
            "analog channel number; repeat for aligned multi-channel CSV output, "
            "or use all for every analog channel on the detected model"
        ),
    )
    capture_parser.add_argument(
        "--points",
        type=_waveform_points_arg,
        default=1000,
        help="waveform point count; supported values: 1000, 5000, 10000",
    )
    capture_parser.add_argument(
        "--format",
        dest="waveform_format",
        choices=("byte", "word"),
        default="byte",
        help="waveform transfer format; defaults to byte",
    )
    capture_parser.add_argument(
        "--csv",
        dest="csv_path",
        default=None,
        help="output CSV path; defaults to data/<UTC+8 timestamp>.csv",
    )
    capture_parser.add_argument(
        "--meta",
        dest="meta_path",
        default=None,
        help="output metadata JSON path; defaults to <csv stem>_meta.json",
    )
    capture_parser.add_argument(
        "--plot",
        dest="plot_path",
        default=None,
        help="optional output PNG plot path",
    )
    capture_parser.add_argument(
        "--allow-time-axis-tolerance",
        action="store_true",
        help=(
            "allow small multi-channel time-axis drift up to half the first "
            "channel sample interval"
        ),
    )
    capture_parser.add_argument(
        "--wait-trigger",
        action="store_true",
        help="arm a single acquisition and poll for trigger completion before capture",
    )
    capture_parser.add_argument(
        "--trigger-timeout-ms",
        type=_positive_int,
        default=None,
        help="finite trigger wait timeout in milliseconds; required with --wait-trigger",
    )
    capture_parser.add_argument(
        "--trigger-poll-interval-ms",
        type=_positive_int,
        default=100,
        help="trigger wait polling interval in milliseconds; defaults to 100",
    )
    capture_parser.add_argument(
        "--force-trigger-on-timeout",
        action="store_true",
        help="after trigger wait timeout, send :TRIGger:FORCe and continue finite polling",
    )

    capture_batch_parser = subparsers.add_parser(
        "capture-batch",
        help="capture a finite batch of analog waveforms into one output directory",
    )
    _add_scope_connection_args(capture_batch_parser)
    capture_batch_parser.add_argument(
        "--channel",
        type=_capture_channel_arg,
        action="append",
        required=True,
        help=(
            "analog channel number; repeat for aligned multi-channel CSV output, "
            "or use all for every analog channel on the detected model"
        ),
    )
    capture_batch_parser.add_argument(
        "--points",
        type=_waveform_points_arg,
        default=1000,
        help="waveform point count; supported values: 1000, 5000, 10000",
    )
    capture_batch_parser.add_argument(
        "--format",
        dest="waveform_format",
        choices=("byte", "word"),
        default="byte",
        help="waveform transfer format; defaults to byte",
    )
    capture_batch_parser.add_argument(
        "--count",
        type=_positive_int,
        required=True,
        help="finite number of waveform captures to run",
    )
    capture_batch_parser.add_argument(
        "--interval-seconds",
        type=_nonnegative_finite_float,
        default=0.0,
        help="seconds to sleep between captures; defaults to 0",
    )
    capture_batch_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "output directory; defaults to data/captures/<UTC+8 timestamp>. "
            "If provided, it must not exist or must be empty"
        ),
    )

    measure_log_parser = subparsers.add_parser(
        "measure-log",
        help="log a finite batch of single-channel and channel-pair measurements to CSV",
    )
    _add_scope_connection_args(measure_log_parser)
    measure_log_parser.add_argument(
        "--channel",
        "--source-channel",
        dest="channel",
        type=_capture_channel_arg,
        action="append",
        default=None,
        help="analog channel number to log; repeat for multiple channels, or use all",
    )
    measure_log_parser.add_argument(
        "--items",
        default="vpp,frequency",
        help="comma-separated single-channel measurements; defaults to vpp,frequency",
    )
    measure_log_parser.add_argument(
        "--pair",
        action="append",
        default=[],
        help="repeatable source/reference channel pairs (SRC:REF)",
    )
    measure_log_parser.add_argument(
        "--pair-items",
        default="phase,delay",
        help="comma-separated pair measurements; defaults to phase,delay",
    )
    measure_log_parser.add_argument(
        "--interval-seconds",
        type=_nonnegative_finite_float,
        default=1.0,
        help="seconds to sleep between log rows; defaults to 1.0",
    )
    measure_log_parser.add_argument(
        "--count",
        type=_positive_int,
        default=None,
        help="total number of log rows to capture; required unless --duration-seconds is set",
    )
    measure_log_parser.add_argument(
        "--duration-seconds",
        type=_positive_plain_float,
        default=None,
        help="maximum duration in seconds; required unless --count is set",
    )
    measure_log_parser.add_argument(
        "--output-dir",
        default=None,
        help="output directory; if provided, it must not exist or must be empty",
    )
    measure_log_parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="abort logging immediately if an instrument system error is detected",
    )

    measure_until_parser = subparsers.add_parser(
        "measure-until",
        allow_abbrev=False,
        help="query one measurement until a numeric condition matches or times out",
    )
    _add_scope_connection_args(measure_until_parser)
    measure_until_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="one analog channel number",
    )
    measure_until_parser.add_argument(
        "--item",
        required=True,
        help="one non-parameterized single-channel measurement item",
    )
    measure_until_parser.add_argument(
        "--operator",
        choices=("gt", "gte", "lt", "lte"),
        required=True,
        help="numeric comparison operator",
    )
    measure_until_parser.add_argument(
        "--threshold",
        type=_measurement_finite_float,
        required=True,
        help="finite threshold in the measurement item's native unit",
    )
    measure_until_parser.add_argument(
        "--timeout-seconds",
        type=_positive_plain_float,
        required=True,
        help="positive finite workflow timeout",
    )
    measure_until_parser.add_argument(
        "--interval-seconds",
        type=_nonnegative_finite_float,
        default=1.0,
        help="interruptible wait after a persisted non-matching sample; defaults to 1.0",
    )
    measure_until_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "workflow run directory; defaults to "
            "data/measure_until/<UTC+8 timestamp>"
        ),
    )

    triggered_measure_loop_parser = subparsers.add_parser(
        "triggered-measure-loop",
        allow_abbrev=False,
        help="run a finite Single, trigger-wait, and measurement loop",
    )
    _add_scope_connection_args(triggered_measure_loop_parser)
    triggered_measure_loop_parser.add_argument(
        "--channel",
        "--source-channel",
        dest="channel",
        type=_capture_channel_arg,
        action="append",
        default=None,
        help="analog channel to measure; repeat for multiple channels, or use all",
    )
    triggered_measure_loop_parser.add_argument(
        "--items",
        default="vpp,frequency",
        help="comma-separated single-channel measurements; defaults to vpp,frequency",
    )
    triggered_measure_loop_parser.add_argument(
        "--pair",
        action="append",
        default=[],
        help="repeatable source/reference channel pairs (SRC:REF)",
    )
    triggered_measure_loop_parser.add_argument(
        "--pair-items",
        default="phase,delay",
        help="comma-separated pair measurements; defaults to phase,delay",
    )
    triggered_measure_loop_parser.add_argument(
        "--count",
        type=_positive_int,
        required=True,
        help="finite number of trigger and measurement cycles",
    )
    triggered_measure_loop_parser.add_argument(
        "--trigger-timeout-seconds",
        type=_positive_plain_float,
        required=True,
        help="positive finite timeout for each trigger wait",
    )
    triggered_measure_loop_parser.add_argument(
        "--interval-seconds",
        type=_nonnegative_finite_float,
        default=0.0,
        help="interruptible wait after a persisted cycle; defaults to 0",
    )
    triggered_measure_loop_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "workflow run directory; defaults to "
            "data/triggered_measure_loops/<UTC+8 timestamp>"
        ),
    )

    triggered_capture_series_parser = subparsers.add_parser(
        "triggered-capture-series",
        allow_abbrev=False,
        help="run a finite Single, trigger-wait, and waveform capture series",
    )
    _add_scope_connection_args(triggered_capture_series_parser)
    triggered_capture_series_parser.add_argument(
        "--channel",
        type=_capture_channel_arg,
        action="append",
        required=True,
        help=(
            "analog channel number; repeat for aligned multi-channel CSV output, "
            "or use all for every analog channel on the detected model"
        ),
    )
    triggered_capture_series_parser.add_argument(
        "--points",
        type=_waveform_points_arg,
        default=1000,
        help="waveform point count; supported values: 1000, 5000, 10000",
    )
    triggered_capture_series_parser.add_argument(
        "--format",
        dest="waveform_format",
        choices=("byte", "word"),
        default="byte",
        help="waveform transfer format; defaults to byte",
    )
    triggered_capture_series_parser.add_argument(
        "--count",
        type=_positive_int,
        required=True,
        help="finite number of triggered waveform capture cycles",
    )
    triggered_capture_series_parser.add_argument(
        "--trigger-timeout-seconds",
        type=_positive_plain_float,
        required=True,
        help="positive finite timeout for each trigger wait",
    )
    triggered_capture_series_parser.add_argument(
        "--interval-seconds",
        type=_nonnegative_finite_float,
        default=0.0,
        help="interruptible wait after a persisted cycle; defaults to 0",
    )
    triggered_capture_series_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "workflow run directory; defaults to "
            "data/triggered_capture_series/<UTC+8 timestamp>"
        ),
    )

    sequence_parser = subparsers.add_parser(
        "sequence",
        allow_abbrev=False,
        help="run a finite ordered Generic Sequence v1 JSON document",
    )
    _add_scope_connection_args(sequence_parser)
    sequence_parser.add_argument(
        "--file",
        dest="sequence_file",
        required=True,
        help="Generic Sequence v1 JSON document path",
    )
    sequence_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "sequence run directory; defaults to data/sequences/<UTC+8 timestamp>. "
            "If provided, it must not exist or must be empty"
        ),
    )

    screenshot_parser = subparsers.add_parser(
        "screenshot",
        help="capture the current oscilloscope screen to an image file",
    )
    _add_scope_connection_args(screenshot_parser)
    screenshot_parser.add_argument(
        "--output",
        dest="output_path",
        default=None,
        help="output image path; defaults to data/<UTC+8 timestamp>.<format>",
    )
    screenshot_parser.add_argument(
        "--background",
        choices=("black", "white"),
        default=None,
        help="screenshot background color; defaults to black",
    )
    screenshot_parser.add_argument("--format", choices=("png", "bmp", "bmp8bit"))
    screenshot_parser.add_argument("--ink-saver", type=_strict_bool_arg)
    screenshot_parser.add_argument(
        "--palette", choices=("color", "grayscale", "none")
    )
    screenshot_parser.add_argument(
        "--layout", choices=("landscape", "portrait")
    )
    screenshot_parser.add_argument(
        "--query-hardcopy",
        action="store_true",
        help="query hardcopy state without capturing image bytes",
    )

    smoke_parser = subparsers.add_parser(
        "smoke",
        help="run a capture-safe diagnostic smoke test and write a report directory",
    )
    _add_scope_connection_args(smoke_parser)
    smoke_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "output directory; defaults to data/hardware_smoke/<UTC+8 timestamp>. "
            "If provided, it must not exist or must be empty"
        ),
    )

    sample_rate_parser = subparsers.add_parser(
        "sample-rate",
        help="query the current analog acquisition sample rate",
    )
    _add_scope_connection_args(sample_rate_parser)
    sample_rate_parser.add_argument(
        "--query",
        dest="sample_rate_query",
        action="store_true",
        required=True,
        help="query the current analog acquisition sample rate",
    )
    sample_rate_parser.add_argument(
        "--maximum",
        dest="sample_rate_maximum",
        action="store_true",
        help="query the maximum analog acquisition sample rate",
    )

    acquisition_points_parser = subparsers.add_parser(
        "acquisition-points",
        help="query the current analog acquisition points",
    )
    _add_scope_connection_args(acquisition_points_parser)
    acquisition_points_parser.add_argument(
        "--query",
        dest="acquisition_points_query_flag",
        action="store_true",
        required=True,
        help="query the current analog acquisition points",
    )

    record_length_parser = subparsers.add_parser(
        "record-length",
        help="query the current analog acquisition record length",
    )
    _add_scope_connection_args(record_length_parser)
    record_length_parser.add_argument(
        "--query",
        dest="record_length_query_flag",
        action="store_true",
        required=True,
        help="query the current analog acquisition record length",
    )

    segmented_memory_parser = subparsers.add_parser(
        "segmented-memory",
        allow_abbrev=False,
        help="query or configure segmented-memory acquisition",
    )
    _add_scope_connection_args(segmented_memory_parser)
    segmented_operation_group = segmented_memory_parser.add_mutually_exclusive_group(
        required=True
    )
    segmented_operation_group.add_argument(
        "--query",
        action="store_true",
        help="query segmented-memory state",
    )
    segmented_operation_group.add_argument(
        "--enable",
        action="store_true",
        help="enable segmented-memory acquisition",
    )
    segmented_operation_group.add_argument(
        "--disable",
        action="store_true",
        help="disable segmented-memory acquisition",
    )
    segmented_memory_parser.add_argument(
        "--segments",
        type=int,
        default=None,
        help="configured segmented-memory count when enabling",
    )

    segmented_capture_parser = subparsers.add_parser(
        "segmented-capture",
        allow_abbrev=False,
        help="capture finite segmented waveforms to per-segment CSV files",
    )
    _add_scope_connection_args(segmented_capture_parser)
    segmented_capture_parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="single analog channel number",
    )
    segmented_capture_parser.add_argument(
        "--segments",
        type=int,
        required=True,
        help="requested segmented acquisition count",
    )
    segmented_capture_parser.add_argument(
        "--points",
        type=_waveform_points_arg,
        default=1000,
        help="waveform point count; supported values: 1000, 5000, 10000",
    )
    segmented_capture_parser.add_argument(
        "--format",
        dest="waveform_format",
        choices=("byte", "word"),
        default="byte",
        help="waveform transfer format; defaults to byte",
    )
    segmented_capture_parser.add_argument(
        "--timeout-ms",
        type=_positive_int,
        default=30000,
        help="finite segmented acquisition timeout in milliseconds",
    )
    segmented_capture_parser.add_argument(
        "--poll-interval-ms",
        type=_positive_int,
        default=100,
        help="operation-condition readiness polling interval in milliseconds",
    )
    segmented_capture_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "output directory; defaults to data/segmented_captures/<UTC+8 timestamp>. "
            "If provided, it must not exist or must be empty"
        ),
    )

    acquisition_parser = subparsers.add_parser(
        "acquisition",
        help="configure or query acquisition type and average count",
    )
    _add_scope_connection_args(acquisition_parser)
    acquisition_parser.add_argument(
        "--query",
        dest="acq_query",
        action="store_true",
        help="query acquisition type and average count",
    )
    acquisition_parser.add_argument(
        "--type",
        dest="acq_type",
        default=None,
        help=(
            "acquisition type: normal/norm, average/aver/avg, "
            "high_resolution/high-resolution/hresolution/hres, peak/peak_detect/peak-detect"
        ),
    )
    acquisition_parser.add_argument(
        "--count",
        dest="acq_count",
        type=_positive_int,
        default=None,
        help="average count (only valid with --type average)",
    )

    autoscale_parser = subparsers.add_parser("autoscale", help="run oscilloscope autoscale")
    _add_scope_connection_args(autoscale_parser)
    autoscale_parser.add_argument(
        "--source-channel",
        type=_positive_int,
        action="append",
        default=None,
        help="analog channel source; repeat to autoscale selected sources",
    )
    autoscale_parser.add_argument(
        "--acquire-mode",
        choices=("normal", "current"),
        default=None,
    )
    autoscale_parser.add_argument(
        "--channels",
        choices=("all", "displayed"),
        default=None,
    )

    setup_save_parser = subparsers.add_parser("setup-save", help="save setup to slot or file")
    _add_scope_connection_args(setup_save_parser)
    save_target = setup_save_parser.add_mutually_exclusive_group(required=True)
    save_target.add_argument("--slot", type=_setup_slot_arg, default=None)
    save_target.add_argument("--file", dest="setup_file", default=None)

    setup_recall_parser = subparsers.add_parser("setup-recall", help="recall setup from slot or file")
    _add_scope_connection_args(setup_recall_parser)
    recall_target = setup_recall_parser.add_mutually_exclusive_group(required=True)
    recall_target.add_argument("--slot", type=_setup_slot_arg, default=None)
    recall_target.add_argument("--file", dest="setup_file", default=None)

    fft_parser = subparsers.add_parser("fft", help="configure or query FFT math function")
    _add_scope_connection_args(fft_parser)
    fft_parser.add_argument("--query", dest="fft_query", action="store_true")
    fft_parser.add_argument("--function", type=_positive_int, required=True)
    fft_parser.add_argument("--source-channel", type=_positive_int, default=None)
    fft_parser.add_argument("--units", choices=("decibel", "vrms"), default=None)
    fft_parser.add_argument(
        "--window",
        choices=("rectangular", "hanning", "flattop", "bharris", "bartlett"),
        default=None,
    )
    fft_parser.add_argument("--center-hz", type=_nonnegative_finite_float, default=None)
    fft_parser.add_argument("--span-hz", type=_positive_plain_float, default=None)
    fft_parser.add_argument("--fft-operation", choices=FFT_OPERATIONS, default=None)
    fft_parser.add_argument("--start-hz", type=_measurement_finite_float, default=None)
    fft_parser.add_argument("--stop-hz", type=_measurement_finite_float, default=None)
    fft_parser.add_argument("--gate", choices=FFT_GATES, default=None)
    fft_parser.add_argument(
        "--phase-reference", choices=FFT_PHASE_REFERENCES, default=None
    )
    fft_parser.add_argument(
        "--detection-type", choices=FFT_DETECTION_TYPES, default=None
    )
    fft_parser.add_argument("--detection-points", type=_positive_int, default=None)
    fft_parser.add_argument("--display", choices=("on", "off"), default=None)

    math_display_parser = subparsers.add_parser(
        "math-display",
        allow_abbrev=False,
        help="enable, disable, or query one instrument-side Math waveform display",
    )
    _add_scope_connection_args(math_display_parser)
    math_display_parser.add_argument("--function", type=_positive_int, required=True)
    math_display_action = math_display_parser.add_mutually_exclusive_group(
        required=True
    )
    math_display_action.add_argument(
        "--on", dest="math_display_action", action="store_const", const="on"
    )
    math_display_action.add_argument(
        "--off", dest="math_display_action", action="store_const", const="off"
    )
    math_display_action.add_argument(
        "--query", dest="math_display_action", action="store_const", const="query"
    )

    math_vertical_parser = subparsers.add_parser(
        "math-vertical",
        allow_abbrev=False,
        help="configure or query instrument-side Math waveform vertical controls",
    )
    _add_scope_connection_args(math_vertical_parser)
    math_vertical_parser.add_argument("--function", type=_positive_int, required=True)
    math_vertical_parser.add_argument(
        "--query", dest="math_vertical_query", action="store_true"
    )
    math_vertical_size = math_vertical_parser.add_mutually_exclusive_group()
    math_vertical_size.add_argument(
        "--scale", type=_positive_plain_float, default=None
    )
    math_vertical_size.add_argument(
        "--range", dest="range_value", type=_positive_plain_float, default=None
    )
    math_vertical_parser.add_argument(
        "--offset", type=_measurement_finite_float, default=None
    )

    math_operator_parser = subparsers.add_parser(
        "math-operator",
        allow_abbrev=False,
        help="configure or query an instrument-side dual-source Math operator",
    )
    _add_scope_connection_args(math_operator_parser)
    math_operator_parser.add_argument("--function", type=_positive_int, required=True)
    math_operator_parser.add_argument(
        "--query", dest="math_operator_query", action="store_true"
    )
    math_operator_parser.add_argument(
        "--operation", dest="math_operation", choices=MATH_OPERATIONS, default=None
    )
    math_operator_parser.add_argument("--source1", choices=MATH_SOURCES, default=None)
    math_operator_parser.add_argument("--source2", choices=MATH_SOURCES, default=None)

    math_composite_parser = subparsers.add_parser(
        "math-composite-source",
        allow_abbrev=False,
        help="configure or query the 2000X/3000X global Math composite source",
    )
    _add_scope_connection_args(math_composite_parser)
    math_composite_parser.add_argument(
        "--query", dest="math_composite_query", action="store_true"
    )
    math_composite_parser.add_argument(
        "--operation",
        dest="math_composite_operation",
        choices=MATH_COMPOSITE_OPERATIONS,
        default=None,
    )
    math_composite_parser.add_argument("--source1", choices=MATH_SOURCES, default=None)
    math_composite_parser.add_argument("--source2", choices=MATH_SOURCES, default=None)

    math_transform_parser = subparsers.add_parser(
        "math-transform",
        allow_abbrev=False,
        help="configure or query an instrument-side single-source Math transform",
    )
    _add_scope_connection_args(math_transform_parser)
    math_transform_parser.add_argument("--function", type=_positive_int, required=True)
    math_transform_parser.add_argument(
        "--query", dest="math_transform_query", action="store_true"
    )
    math_transform_parser.add_argument(
        "--operation",
        dest="math_transform_operation",
        choices=MATH_TRANSFORMS,
        default=None,
    )
    math_transform_parser.add_argument(
        "--source", choices=MATH_TRANSFORM_SOURCES, default=None
    )
    math_transform_parser.add_argument(
        "--input-offset", type=_measurement_finite_float, default=None
    )
    math_transform_parser.add_argument(
        "--gain", type=_measurement_finite_float, default=None
    )
    math_transform_parser.add_argument(
        "--linear-offset", type=_measurement_finite_float, default=None
    )

    math_filter_parser = subparsers.add_parser(
        "math-filter",
        allow_abbrev=False,
        help="configure or query an instrument-side single-source Math filter",
    )
    _add_scope_connection_args(math_filter_parser)
    math_filter_parser.add_argument("--function", type=_positive_int, required=True)
    math_filter_parser.add_argument(
        "--query", dest="math_filter_query", action="store_true"
    )
    math_filter_parser.add_argument(
        "--operation",
        dest="math_filter_operation",
        choices=MATH_FILTER_OPERATIONS,
        default=None,
    )
    math_filter_parser.add_argument(
        "--source", choices=MATH_TRANSFORM_SOURCES, default=None
    )
    math_filter_parser.add_argument(
        "--cutoff-hz", type=_positive_plain_float, default=None
    )
    math_filter_parser.add_argument("--average-count", type=_positive_int, default=None)
    math_filter_parser.add_argument("--smooth-points", type=_positive_int, default=None)

    math_visualization_parser = subparsers.add_parser(
        "math-visualization",
        allow_abbrev=False,
        help="configure or query an instrument-side Math visualization",
    )
    _add_scope_connection_args(math_visualization_parser)
    math_visualization_parser.add_argument(
        "--function", type=_positive_int, required=True
    )
    math_visualization_parser.add_argument(
        "--query", dest="math_visualization_query", action="store_true"
    )
    math_visualization_parser.add_argument(
        "--operation",
        dest="math_visualization_operation",
        choices=MATH_VISUALIZATION_OPERATIONS,
        default=None,
    )
    math_visualization_parser.add_argument(
        "--source", choices=MATH_TRANSFORM_SOURCES, default=None
    )
    math_visualization_parser.add_argument(
        "--source2", choices=MATH_SOURCES, default=None
    )
    math_visualization_parser.add_argument(
        "--measurement", choices=MATH_TREND_MEASUREMENTS, default=None
    )
    math_visualization_parser.add_argument(
        "--measurement-slot", type=_positive_int, default=None
    )

    math_clear_parser = subparsers.add_parser(
        "math-clear",
        allow_abbrev=False,
        help="clear one supported instrument-side Math accumulation",
    )
    _add_scope_connection_args(math_clear_parser)
    math_clear_parser.add_argument("--function", type=_positive_int, required=True)

    acquisition_check_parser = subparsers.add_parser(
        "acquisition-check",
        help="run the acquisition configuration hardware validation workflow",
    )
    _add_scope_connection_args(acquisition_check_parser)
    acquisition_check_parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "output directory; defaults to data/hardware_acquisition/<UTC+8 timestamp>. "
            "If provided, it must not exist or must be empty"
        ),
    )
    acquisition_check_parser.add_argument(
        "--average-count",
        type=_positive_int,
        default=16,
        help="average acquisition count to validate; defaults to 16",
    )
    acquisition_check_parser.add_argument(
        "--check-only",
        action="store_true",
        help="only query the current acquisition configuration and system error",
    )
    acquisition_check_parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="stop the workflow after the first acquisition step with a system error",
    )
    acquisition_check_parser.add_argument(
        "--restore-type",
        action="store_true",
        help="restore the initial acquisition type after the workflow completes",
    )
    return parser


def _add_scope_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--resource",
        default=None,
        help="VISA resource string. Defaults to SCOPES_TOOL_RESOURCE.",
    )
    parser.add_argument(
        "--visa-library",
        default=None,
        help="optional PyVISA library argument, such as @py",
    )
    parser.add_argument(
        "--log-scpi",
        action="store_true",
        help="write SCPI command and response logs to stderr",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="write a single machine-readable JSON object to stdout",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="use the deterministic hardware-free simulator backend",
    )
    parser.add_argument(
        "--simulate-signal",
        dest="simulate_signals",
        action="append",
        default=[],
        metavar="CH:shape:frequency_hz:vpp_v:offset_v:phase_deg[:noise_rms_v]",
        help=(
            "override one simulator channel signal; repeat per channel. "
            "Only valid with --simulate"
        ),
    )
    parser.add_argument(
        "--simulate-preset",
        choices=PRESET_NAMES,
        default=None,
        help="apply a built-in simulator preset; only valid with --simulate",
    )
    parser.add_argument(
        "--simulate-scenario",
        default=None,
        help="load simulator scenario JSON; only valid with --simulate",
    )
    parser.add_argument(
        "--simulate-system-error",
        dest="simulate_system_errors",
        action="append",
        default=[],
        metavar="CODE",
        help="seed one simulator system error code; repeatable and only valid with --simulate",
    )
    parser.add_argument(
        "--simulate-binary-transfer-failure",
        action="store_true",
        help="fail simulator waveform binary transfers; only valid with --simulate",
    )
    parser.add_argument(
        "--simulate-invalid-measurement",
        dest="simulate_invalid_measurement_channels",
        action="append",
        default=[],
        metavar="CH",
        help="make simulator measurements invalid for a channel; repeatable and only valid with --simulate",
    )
    parser.add_argument(
        "--simulate-display-off",
        dest="simulate_display_off_channels",
        action="append",
        default=[],
        metavar="CH",
        help="start a simulator channel display off; repeatable and only valid with --simulate",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate arguments and report the planned SCPI without opening a backend",
    )
    parser.add_argument(
        "--model",
        default="keysight-dsox4024a",
        help=(
            "canonical physical model ID used for dry-run and simulation planning; "
            "live execution uses the identity detected from *IDN?; "
            "defaults to keysight-dsox4024a"
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="one-shot compatibility flag for live mode; cannot be combined with --simulate or --dry-run",
    )


def _dispatch_command(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    if args.command == "list-resources":
        return _cmd_list_resources(args)
    if args.command == "hardware-report":
        return _cmd_hardware_report(args)
    if args.command == "identify":
        return system._cmd_verify(args)
    if args.command == "check-error":
        return system._cmd_check_error(args)
    if args.command in {
        "system-clear-status",
        "system-opc",
        "system-status-byte",
        "system-standard-event",
        "system-operation-status",
        "system-options",
    }:
        return system._cmd_system_status(args)
    if args.command == "cleanup":
        return system._cmd_cleanup(args)
    if args.command in system._CONTROL_COMMANDS:
        return system._cmd_control(args)
    if args.command == "force-trigger":
        return system._cmd_force_trigger(args)
    if args.command == "channel-summary":
        return channel_display._cmd_channel_summary(args)
    if args.command == "channel-display":
        return channel_display._cmd_channel_display(args)
    if args.command == "channel-label":
        return channel_display._cmd_channel_label(args)
    if args.command == "channel-scale":
        return channel_display._cmd_channel_scale(args)
    if args.command == "channel-offset":
        return channel_display._cmd_channel_offset(args)
    if args.command == "channel-coupling":
        return channel_display._cmd_channel_coupling(args)
    if args.command == "channel-probe":
        return channel_display._cmd_channel_probe(args)
    if args.command == "channel-bandwidth-limit":
        return channel_display._cmd_channel_bandwidth_limit(args)
    if args.command == "channel-impedance":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "channel-invert":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "channel-range":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "channel-units":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "channel-vernier":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "channel-probe-skew":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "display-label":
        return channel_display._cmd_display_label(args)
    if args.command in {
        "display-clear",
        "display-persistence",
        "display-intensity",
        "display-vectors",
    }:
        return channel_display._cmd_display_common(args)
    if args.command in {
        "measure-clear",
        "measure-show",
        "measure-source",
        "measure-window",
    }:
        return measurement_analysis._cmd_measurement_control(args)
    if args.command in {
        "dvm-enable",
        "dvm-source",
        "dvm-mode",
        "dvm-auto-range",
        "dvm-current",
        "dvm-query",
    }:
        return measurement_analysis._cmd_dvm(args)
    if args.command in {"demo-query", "demo-output", "demo-function", "demo-phase"}:
        return measurement_analysis._cmd_demo(args)
    if args.command in {
        "wgen-query",
        "wgen-output",
        "wgen-function",
        "wgen-frequency",
        "wgen-voltage",
        "wgen-offset",
        "wgen-load",
    }:
        return measurement_analysis._cmd_wgen(args)
    if args.command in {
        "serial-query",
        "serial-mode",
        "serial-display",
        "serial-uart",
        "serial-trigger-uart",
        "serial-trigger-i2c",
        "serial-trigger-spi",
        "serial-trigger-can",
        "serial-i2c",
        "serial-spi",
        "serial-can",
        "serial-lister-query",
        "serial-lister-display",
        "serial-lister-reference",
        "serial-lister-export",
    }:
        return _cmd_serial(args)
    if args.command in {
        "search-state",
        "search-mode",
        "search-count",
        "search-event",
        "serial-search-uart",
        "serial-search-i2c",
        "serial-search-spi",
        "serial-search-can",
    }:
        return trigger_search._cmd_search(args)
    if args.command in {
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
        return _cmd_save_export(args)
    if args.command in {
        "reference-save",
        "reference-display",
        "reference-label",
        "reference-clear",
        "reference-query",
    }:
        return measurement_analysis._cmd_reference_waveform(args)
    if args.command == "annotation":
        return channel_display._cmd_annotation(args)
    if args.command == "timebase-scale":
        return channel_display._cmd_timebase_scale(args)
    if args.command == "timebase-position":
        return channel_display._cmd_timebase_position(args)
    if args.command == "trigger-edge":
        return trigger_search._cmd_trigger_edge(args)
    if args.command == "trigger-edge-source":
        return trigger_search._cmd_trigger_edge_source(args)
    if args.command == "trigger-edge-slope":
        return trigger_search._cmd_trigger_edge_slope(args)
    if args.command == "trigger-edge-level":
        return trigger_search._cmd_trigger_edge_level(args)
    if args.command == "external-trigger-range":
        return trigger_search._cmd_external_trigger_range(args)
    if args.command == "trigger-edge-external-level":
        return trigger_search._cmd_trigger_edge_external_level(args)
    if args.command in {
        "external-trigger-probe",
        "external-trigger-units",
        "external-trigger-settings",
    }:
        return trigger_search._cmd_external_trigger_input(args)
    if args.command in {
        "trigger-sweep",
        "trigger-noise-reject",
        "trigger-hf-reject",
        "trigger-edge-coupling",
        "trigger-edge-reject",
    }:
        return trigger_search._cmd_trigger_common(args)
    if args.command == "trigger-pulse-width":
        return trigger_search._cmd_trigger_glitch(args)
    if args.command == "trigger-runt":
        return trigger_search._cmd_trigger_runt(args)
    if args.command == "trigger-transition":
        return trigger_search._cmd_trigger_transition(args)
    if args.command == "trigger-delay":
        return trigger_search._cmd_trigger_delay(args)
    if args.command == "trigger-setup-hold":
        return trigger_search._cmd_trigger_setup_hold(args)
    if args.command == "trigger-edge-burst":
        return trigger_search._cmd_trigger_edge_burst(args)
    if args.command == "trigger-tv":
        return trigger_search._cmd_trigger_tv(args)
    if args.command == "trigger-pattern":
        return trigger_search._cmd_trigger_pattern(args)
    if args.command == "trigger-or":
        return trigger_search._cmd_trigger_or(args)
    if args.command == "cursor":
        return measurement_analysis._cmd_cursor(args)
    if args.command == "trigger-holdoff":
        return trigger_search._cmd_trigger_holdoff(args)
    if args.command == "measure":
        return _cmd_measure(args)
    if args.command == "measure-results":
        return measurement_analysis._cmd_measure_results(args)
    if args.command == "measure-stats":
        return measurement_analysis._cmd_measure_stats(args)
    if args.command == "doctor":
        return _cmd_doctor(args)
    if args.command == "measure-sweep":
        return _cmd_measure_sweep(args)
    if args.command == "capture":
        return _cmd_capture(args)
    if args.command == "capture-batch":
        return _cmd_capture_batch(args, stop_requested=stop_requested)
    if args.command == "measure-log":
        return _cmd_measure_log(args, stop_requested=stop_requested)
    if args.command == "measure-until":
        return _cmd_measure_until(args, stop_requested=stop_requested)
    if args.command == "triggered-measure-loop":
        return _cmd_triggered_measure_loop(args, stop_requested=stop_requested)
    if args.command == "triggered-capture-series":
        return _cmd_triggered_capture_series(args, stop_requested=stop_requested)
    if args.command == "sequence":
        return _cmd_sequence(args, stop_requested=stop_requested)
    if args.command == "screenshot":
        return _cmd_screenshot(args)
    if args.command == "smoke":
        return _cmd_smoke(args)
    if args.command == "sample-rate":
        return acquisition._cmd_sample_rate(args)

    if args.command == "segmented-memory":
        return acquisition._cmd_segmented_memory(args)

    if args.command == "segmented-capture":
        return _cmd_segmented_capture(args)

    if args.command == "acquisition-points":
        return acquisition._cmd_acquisition_points(args)

    if args.command == "record-length":
        return acquisition._cmd_record_length(args)

    if args.command == "acquisition":
        return acquisition._cmd_acquisition(args)
    if args.command == "autoscale":
        return _cmd_autoscale(args)
    if args.command == "setup-save":
        return _cmd_setup_save(args)
    if args.command == "setup-recall":
        return _cmd_setup_recall(args)
    if args.command == "fft":
        return measurement_analysis._cmd_fft(args)
    if args.command == "math-display":
        return measurement_analysis._cmd_math_display(args)
    if args.command == "math-vertical":
        return measurement_analysis._cmd_math_vertical(args)
    if args.command == "math-operator":
        return measurement_analysis._cmd_math_operator(args)
    if args.command == "math-composite-source":
        return measurement_analysis._cmd_math_composite_source(args)
    if args.command == "math-transform":
        return measurement_analysis._cmd_math_transform(args)
    if args.command == "math-filter":
        return measurement_analysis._cmd_math_filter(args)
    if args.command == "math-visualization":
        return measurement_analysis._cmd_math_visualization(args)
    if args.command == "math-clear":
        return measurement_analysis._cmd_math_clear(args)
    if args.command == "acquisition-check":
        return _cmd_acquisition_check(args)
    raise OscilloscopeError("missing command")


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


def _measure_operation_request(args: argparse.Namespace) -> MeasureRequest:
    return MeasureRequest(
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
        trigger_wait = _capture_trigger_wait_config(args)
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
        output_path = Path(args.output_path)
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
            commands = _serial_uart_trigger_commands(
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
            commands = _serial_i2c_trigger_commands(args, trigger_type=trigger_type)
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
            commands = _serial_spi_trigger_commands(args, trigger_type=trigger_type)
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
            commands = _serial_can_trigger_commands(args, trigger_type=trigger_type)
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
        commands = _serial_protocol_commands(args, capabilities)
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
                    **_serial_protocol_settings(args),
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
        target, result, waits_for_completion = _save_export_plan(args)
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
        planned = trigger_holdoff_commands(seconds)
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
        output_path = _screenshot_output_path(args, format_name)
        file_kind = "png" if format_name == "png" else "bmp"
        files = [{"kind": file_kind, "path": str(output_path)}]
        ink_saver_plan = None
        if preflight._uses_screenshot_format_pack(args):
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
        csv_path = Path(args.csv_path) if args.csv_path is not None else _default_capture_csv_path()
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


def _json_set_files(files: list[dict[str, object]]) -> None:
    if runtime._JSON_RECORD is not None:
        runtime._JSON_RECORD["files"] = files


def _apply_operation_result(result) -> None:
    if runtime._JSON_RECORD is None:
        return
    runtime._JSON_RECORD["result"] = result.result
    runtime._JSON_RECORD["files"] = result.files
    runtime._JSON_RECORD["system_error"] = result.system_error
    if result.backend is not None:
        runtime._JSON_RECORD["backend"] = result.backend


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
















































def _save_export_plan(
    args: argparse.Namespace,
) -> tuple[str, dict[str, object], bool]:
    command = args.command
    result: dict[str, object] = {"instrument_side": True}
    if command == "save-pwd":
        target = save_pwd_query() if args.query else save_pwd_command(args.path)
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(path=args.path, state_changing=True)
    elif command == "save-filename":
        target = save_filename_query() if args.query else save_filename_command(args.name)
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(name=args.name, state_changing=True)
    elif command == "save-image-format":
        target = (
            save_image_format_query()
            if args.query
            else save_image_format_command(args.format)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(format=args.format, state_changing=True)
    elif command == "save-image-palette":
        target = (
            save_image_palette_query()
            if args.query
            else save_image_palette_command(args.palette)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(palette=args.palette, state_changing=True)
    elif command == "save-image-ink-saver":
        target = (
            save_image_ink_saver_query()
            if args.query
            else save_image_ink_saver_command(args.enabled)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(enabled=args.enabled, state_changing=True)
    elif command == "save-image-factors":
        target = (
            save_image_factors_query()
            if args.query
            else save_image_factors_command(args.enabled)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(enabled=args.enabled, state_changing=True)
    elif command == "save-image":
        target = save_image_command(args.filename)
        result.update(
            operation="save-image",
            filename=args.filename,
            command=target,
            state_changing=True,
        )
        return target, result, True
    elif command == "save-waveform-format":
        target = (
            save_waveform_format_query()
            if args.query
            else save_waveform_format_command(args.format)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(format=args.format, state_changing=True)
    elif command == "save-waveform-length":
        target = (
            save_waveform_length_query()
            if args.query
            else save_waveform_length_command(args.points)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(points=args.points, state_changing=True)
    elif command == "save-waveform-length-max":
        target = save_waveform_length_max_query()
        result.update(operation="query", command=target)
    else:
        target = save_waveform_command(args.filename)
        result.update(
            operation="save-waveform",
            filename=args.filename,
            command=target,
            state_changing=True,
        )
        return target, result, True
    return target, result, False


def _cmd_save_export(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        target, result, waits_for_completion = _save_export_plan(args)

        if args.command == "save-pwd":
            if args.query:
                state = scope.query_save_pwd()
                result.update(state.to_json())
                print(f"Instrument save directory: {state.path}")
            else:
                scope.configure_save_pwd(args.path)
                print(f"Instrument save directory: {args.path}")
        elif args.command == "save-filename":
            if args.query:
                state = scope.query_save_filename()
                result.update(state.to_json())
                print(f"Instrument save base name: {state.name}")
            else:
                scope.configure_save_filename(args.name)
                print(f"Instrument save base name: {args.name}")
        elif args.command == "save-image-format":
            if args.query:
                state = scope.query_save_image_format()
                result.update(state.to_json())
                print(f"Instrument image save format: {state.format}")
            else:
                scope.configure_save_image_format(args.format)
                print(f"Instrument image save format: {args.format}")
        elif args.command == "save-image-palette":
            if args.query:
                state = scope.query_save_image_palette()
                result.update(state.to_json())
                print(f"Instrument image save palette: {state.palette}")
            else:
                scope.configure_save_image_palette(args.palette)
                print(f"Instrument image save palette: {args.palette}")
        elif args.command == "save-image-ink-saver":
            if args.query:
                state = scope.query_save_image_ink_saver()
                result.update(state.to_json())
                print(f"Instrument image ink saver: {state.enabled}")
            else:
                scope.configure_save_image_ink_saver(args.enabled)
                print(f"Instrument image ink saver: {args.enabled}")
        elif args.command == "save-image-factors":
            if args.query:
                state = scope.query_save_image_factors()
                result.update(state.to_json())
                print(f"Instrument image factors: {state.enabled}")
            else:
                scope.configure_save_image_factors(args.enabled)
                print(f"Instrument image factors: {args.enabled}")
        elif args.command == "save-image":
            operation = scope.save_image(args.filename)
            result.update(operation.to_json(), state_changing=True)
            print(f"Instrument-side image saved as: {args.filename}")
        elif args.command == "save-waveform-format":
            if args.query:
                state = scope.query_save_waveform_format()
                result.update(state.to_json())
                print(f"Instrument waveform save format: {state.format}")
            else:
                scope.configure_save_waveform_format(args.format)
                print(f"Instrument waveform save format: {args.format}")
        elif args.command == "save-waveform-length":
            if args.query:
                state = scope.query_save_waveform_length()
                result.update(state.to_json())
                print(f"Instrument waveform save length: {state.points}")
            else:
                scope.configure_save_waveform_length(args.points)
                print(f"Instrument waveform save length: {args.points}")
        elif args.command == "save-waveform-length-max":
            state = scope.query_save_waveform_length_max()
            result.update(state.to_json())
            print(f"Maximum waveform save length enabled: {state.enabled}")
        else:
            operation = scope.save_waveform(args.filename)
            result.update(operation.to_json(), state_changing=True)
            print(f"Instrument-side waveform saved as: {args.filename}")

        runtime._json_update_result(**result)
        print(f"Command: {target}")
        if waits_for_completion:
            print(f"Operation complete query: {system_opc_query()}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0






def _serial_protocol_settings(args: argparse.Namespace) -> dict[str, object]:
    fields = {
        "serial-uart": ("rx_source", "tx_source", "baud_rate", "data_bits", "parity", "polarity", "bit_order"),
        "serial-i2c": ("clock_source", "data_source", "address_size"),
        "serial-spi": ("clock_source", "mosi_source", "miso_source", "frame_source", "clock_slope", "bit_order", "word_width", "framing", "clock_timeout"),
        "serial-can": ("source", "baud_rate", "signal_definition", "sample_point"),
    }[args.command]
    return {field: getattr(args, field) for field in fields if getattr(args, field) is not None}


def _serial_protocol_commands(
    args: argparse.Namespace, capabilities: ScopeCapabilities
) -> list[str]:
    settings = preflight._serial_cli_values(
        capabilities,
        protocol=args.command,
        **_serial_protocol_settings(args),
    )
    mode = {"serial-uart": "uart", "serial-i2c": "i2c", "serial-spi": "spi", "serial-can": "can"}[args.command]
    if args.query:
        query_builders = {
            "serial-uart": serial_uart_query_commands,
            "serial-i2c": serial_i2c_query_commands,
            "serial-spi": serial_spi_query_commands,
            "serial-can": serial_can_query_commands,
        }
        return [serial_mode_query(args.bus), *query_builders[args.command](args.bus).values()]
    builders = {
        "serial-uart": serial_uart_configure_commands,
        "serial-i2c": serial_i2c_configure_commands,
        "serial-spi": serial_spi_configure_commands,
        "serial-can": serial_can_configure_commands,
    }
    return [serial_mode_command(args.bus, mode), *builders[args.command](args.bus, settings)]


def _serial_uart_trigger_read_commands(
    bus: int, mode: str | None, trigger_type: str | None
) -> list[str]:
    commands = [trigger_mode_query()]
    if mode != "uart":
        return commands
    commands.append(serial_uart_trigger_type_query(bus))
    if trigger_type in {"rx-data", "tx-data"}:
        commands.extend(
            [
                serial_uart_trigger_data_query(bus),
                serial_uart_trigger_qualifier_query(bus),
            ]
        )
    return commands


def _serial_uart_trigger_commands(
    args: argparse.Namespace,
    *,
    mode: str | None = "uart",
    trigger_type: str | None = None,
) -> list[str]:
    commands = [serial_mode_query(args.bus)]
    if not args.query:
        commands.extend(
            serial_uart_trigger_configure_commands(
                args.bus,
                args.type,
                args.data,
                args.qualifier,
            )
        )
        commands.append(trigger_mode_serial_command(args.bus))
    commands.extend(_serial_uart_trigger_read_commands(args.bus, mode, trigger_type))
    return commands


def _serial_i2c_trigger_read_commands(
    bus: int, mode: str | None, trigger_type: str | None
) -> list[str]:
    commands = [trigger_mode_query()]
    if mode != "i2c":
        return commands
    commands.append(serial_i2c_trigger_type_query(bus))
    if trigger_type == "address-no-ack":
        commands.append(serial_i2c_trigger_address_query(bus))
    elif trigger_type in {"read7", "write7", "write10", "read-eeprom"}:
        commands.extend([serial_i2c_trigger_address_query(bus), serial_i2c_trigger_data_query(bus)])
        if trigger_type == "read-eeprom":
            commands.append(serial_i2c_trigger_qualifier_query(bus))
    elif trigger_type in {"read7-data2", "write7-data2"}:
        commands.extend([
            serial_i2c_trigger_address_query(bus),
            serial_i2c_trigger_data_query(bus),
            serial_i2c_trigger_data2_query(bus),
        ])
    return commands


def _serial_i2c_trigger_commands(
    args: argparse.Namespace, *, mode: str | None = "i2c", trigger_type: str | None = None
) -> list[str]:
    commands = [serial_mode_query(args.bus)]
    if not args.query:
        commands.extend(
            serial_i2c_trigger_configure_commands(
                args.bus, args.type, args.address, args.data, args.data2, args.qualifier
            )
        )
        commands.append(trigger_mode_serial_command(args.bus))
    commands.extend(_serial_i2c_trigger_read_commands(args.bus, mode, trigger_type))
    return commands


def _serial_spi_trigger_read_commands(
    bus: int, mode: str | None, trigger_type: str | None
) -> list[str]:
    commands = [trigger_mode_query()]
    if mode != "spi":
        return commands
    commands.append(serial_spi_trigger_type_query(bus))
    if trigger_type in {"mosi", "miso"}:
        commands.extend([
            serial_spi_trigger_width_query(bus, trigger_type),
            serial_spi_trigger_data_query(bus, trigger_type),
        ])
    return commands


def _serial_spi_trigger_commands(
    args: argparse.Namespace, *, mode: str | None = "spi", trigger_type: str | None = None
) -> list[str]:
    commands = [serial_mode_query(args.bus)]
    if not args.query:
        commands.extend(
            serial_spi_trigger_configure_commands(args.bus, args.type, args.width, args.data)
        )
        commands.append(trigger_mode_serial_command(args.bus))
    commands.extend(_serial_spi_trigger_read_commands(args.bus, mode, trigger_type))
    return commands


def _serial_can_trigger_read_commands(
    bus: int, mode: str | None, trigger_type: str | None
) -> list[str]:
    commands = [trigger_mode_query()]
    if mode != "can":
        return commands
    commands.append(serial_can_trigger_type_query(bus))
    if trigger_type in {"data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data"}:
        commands.extend([serial_can_trigger_id_mode_query(bus), serial_can_trigger_id_query(bus)])
    if trigger_type == "id-and-data":
        commands.extend([serial_can_trigger_data_length_query(bus), serial_can_trigger_data_query(bus)])
    return commands


def _serial_can_trigger_commands(
    args: argparse.Namespace, *, mode: str | None = "can", trigger_type: str | None = None
) -> list[str]:
    commands = [serial_mode_query(args.bus)]
    if not args.query:
        commands.extend(
            serial_can_trigger_configure_commands(
                args.bus, args.type, args.id, args.id_mode, args.data, args.data_length
            )
        )
        commands.append(trigger_mode_serial_command(args.bus))
    commands.extend(_serial_can_trigger_read_commands(args.bus, mode, trigger_type))
    return commands


def _cmd_serial(args: argparse.Namespace) -> int:
    if args.command in {
        "serial-lister-query",
        "serial-lister-display",
        "serial-lister-reference",
        "serial-lister-export",
    }:
        return _cmd_serial_lister(args)
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        print(f"Series: {idn.series or 'unknown'}")
        if scope.capabilities is None:
            print("Capabilities: unavailable for this model")
            return 1

        if args.command == "serial-query":
            command = serial_bus_query(args.bus)
            state = scope.query_serial(args.bus)
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Serial bus {state.bus} raw setup: {state.raw}")
        elif args.command == "serial-mode":
            if args.query:
                command = serial_mode_query(args.bus)
                state = scope.query_serial_mode(args.bus)
                operation = "query"
            else:
                command = serial_mode_command(args.bus, args.mode)
                state = scope.configure_serial_mode(args.bus, args.mode)
                operation = "configure"
            runtime._json_update_result(
                operation=operation,
                command=command,
                **state.to_json(),
                **({"state_changing": True} if not args.query else {}),
            )
            print(f"Serial bus {state.bus} mode: {state.mode}")
        elif args.command == "serial-display":
            if args.query:
                command = serial_display_query(args.bus)
                state = scope.query_serial_display(args.bus)
                operation = "query"
            else:
                command = serial_display_command(args.bus, args.enabled)
                state = scope.configure_serial_display(args.bus, args.enabled)
                operation = "configure"
            runtime._json_update_result(
                operation=operation,
                command=command,
                **state.to_json(),
                **({"state_changing": True} if not args.query else {}),
            )
            print(f"Serial bus {state.bus} display enabled: {state.enabled}")
        elif args.command == "serial-trigger-uart":
            if args.query:
                state = scope.query_serial_uart_trigger(args.bus)
                operation = "query"
                commands = _serial_uart_trigger_commands(
                    args,
                    mode=state.mode,
                    trigger_type=state.type,
                )
            else:
                state = scope.configure_serial_uart_trigger(
                    args.bus,
                    type=args.type,
                    data=args.data,
                    qualifier=args.qualifier,
                )
                operation = "configure"
                commands = _serial_uart_trigger_commands(
                    args,
                    mode=state.mode,
                    trigger_type=state.type,
                )
            runtime._json_update_result(
                operation=operation,
                commands=commands,
                **state.to_json(),
                **({"state_changing": True} if not args.query else {}),
            )
            print(
                f"Serial bus {state.bus} UART trigger: "
                f"{state.type or 'unavailable'}"
            )
        elif args.command in {
            "serial-trigger-i2c", "serial-trigger-spi", "serial-trigger-can"
        }:
            protocol = args.command.removeprefix("serial-trigger-")
            if args.query:
                state = getattr(scope, f"query_serial_{protocol}_trigger")(args.bus)
                operation = "query"
            else:
                settings = {
                    "i2c": {"type": args.type, "address": getattr(args, "address", None), "data": args.data, "data2": getattr(args, "data2", None), "qualifier": getattr(args, "qualifier", None)},
                    "spi": {"type": args.type, "width": getattr(args, "width", None), "data": args.data},
                    "can": {"type": args.type, "id": getattr(args, "id", None), "id_mode": getattr(args, "id_mode", None), "data": args.data, "data_length": getattr(args, "data_length", None)},
                }[protocol]
                state = getattr(scope, f"configure_serial_{protocol}_trigger")(
                    args.bus, **settings
                )
                operation = "configure"
            if protocol == "i2c":
                commands = _serial_i2c_trigger_commands(
                    args, mode=state.mode, trigger_type=state.type
                )
            elif protocol == "spi":
                commands = _serial_spi_trigger_commands(
                    args, mode=state.mode, trigger_type=state.type
                )
            else:
                commands = _serial_can_trigger_commands(
                    args, mode=state.mode, trigger_type=state.type
                )
            runtime._json_update_result(
                operation=operation,
                commands=commands,
                **state.to_json(),
                **({"state_changing": True} if not args.query else {}),
            )
            print(
                f"Serial bus {state.bus} {protocol.upper()} trigger: "
                f"{state.type or 'unavailable'}"
            )
        else:
            protocol = args.command.removeprefix("serial-")
            commands = _serial_protocol_commands(args, scope.capabilities)
            command = commands[0]
            settings = _serial_protocol_settings(args)
            if args.query:
                state = getattr(scope, f"query_serial_{protocol}")(args.bus)
                operation = "query"
            else:
                state = getattr(scope, f"configure_serial_{protocol}")(
                    args.bus, **settings
                )
                operation = "configure"
            runtime._json_update_result(
                operation=operation,
                commands=commands,
                **state.to_json(),
                **({"state_changing": True} if not args.query else {}),
            )
            print(f"Serial bus {state.bus} {protocol} mode: {state.mode}")

        if args.command in {
            "serial-trigger-uart", "serial-trigger-i2c", "serial-trigger-spi", "serial-trigger-can"
        }:
            for command in commands:
                print(f"Command: {command}")
        else:
            print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        if (
            args.command in {"serial-uart", "serial-i2c", "serial-spi", "serial-can"}
            and not args.query
            and entry.code == -221
            and entry.message == "Settings conflict"
        ):
            print("Hint: Requested Serial settings conflict with current instrument state.")
            print("Hint: Query both Serial buses.")
            print(
                "Hint: Check whether the other bus already uses the requested "
                "analog channels or protocol resources."
            )
        return 1 if entry.is_error else 0


def _cmd_serial_lister(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        print(f"Series: {idn.series or 'unknown'}")
        if scope.capabilities is None:
            print("Capabilities: unavailable for this model")
            return 1

        if args.command == "serial-lister-query":
            commands = list(serial_lister_query_commands().values())
            state = scope.query_serial_lister()
            runtime._json_update_result(
                operation="query",
                commands=commands,
                **state.to_json(),
            )
            print(f"Lister display: {state.display}")
            print(f"Lister reference: {state.reference}")
            for command in commands:
                print(f"Command: {command}")
        elif args.command == "serial-lister-display":
            if args.query:
                command = serial_lister_display_query()
                state = scope.query_serial_lister_display()
                operation = "query"
            else:
                command = serial_lister_display_command(args.selection)
                state = scope.configure_serial_lister_display(args.selection)
                operation = "configure"
            runtime._json_update_result(
                operation=operation,
                command=command,
                **state.to_json(),
                **({"state_changing": True} if not args.query else {}),
            )
            print(f"Lister display: {state.display}")
            print(f"Command: {command}")
        elif args.command == "serial-lister-reference":
            if args.query:
                command = serial_lister_reference_query()
                state = scope.query_serial_lister_reference()
                operation = "query"
            else:
                command = serial_lister_reference_command(args.reference)
                state = scope.configure_serial_lister_reference(args.reference)
                operation = "configure"
            runtime._json_update_result(
                operation=operation,
                command=command,
                **state.to_json(),
                **({"state_changing": True} if not args.query else {}),
            )
            print(f"Lister reference: {state.reference}")
            print(f"Command: {command}")
        else:
            command = serial_lister_data_query()
            payload = scope.query_serial_lister_data()
            output_path = Path(args.output_path)
            written_path = write_serial_lister_csv(payload, output_path)
            runtime._json_update_result(
                operation="export",
                command=command,
                output_path=str(written_path),
                bytes_written=len(payload),
            )
            _json_set_files([{"kind": "csv", "path": str(written_path)}])
            print(f"Command: {command}")
            print(f"Lister CSV: {written_path} ({len(payload)} bytes)")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0




def _cmd_doctor(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        result = run_doctor(scope, resource)
        if result.idn is not None:
            runtime._json_record_scope(scope, result.idn)
        _apply_operation_result(result)
        for line in result.human_lines:
            print(line)
        return result.exit_code


def _cmd_measure_sweep(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        result = run_measure_sweep(
            scope,
            resource,
            MeasureSweepRequest(
                channels=args.channel,
                items=args.items,
                pairs=tuple(args.pair),
                pair_items=args.pair_items,
            ),
        )
        if result.idn is not None:
            runtime._json_record_scope(scope, result.idn)
        _apply_operation_result(result)
        for line in result.human_lines:
            print(line)
        return result.exit_code


def _cmd_measure(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_measure(scope, resource, _measure_operation_request(args))
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code






def _cmd_capture(args: argparse.Namespace) -> int:
    trigger_wait = _capture_trigger_wait_config(args)
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    csv_path = Path(args.csv_path) if args.csv_path is not None else _default_capture_csv_path()
    meta_path = Path(args.meta_path) if args.meta_path is not None else csv_path.with_name(
        f"{csv_path.stem}_meta.json"
    )
    plot_path = Path(args.plot_path) if args.plot_path is not None else None

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_capture(
            scope,
            resource,
            CaptureRequest(
                channels=args.channel,
                points=args.points,
                waveform_format=args.waveform_format,
                csv_path=csv_path,
                meta_path=meta_path,
                plot_path=plot_path,
                allow_time_axis_tolerance=args.allow_time_axis_tolerance,
                trigger_wait=trigger_wait,
            ),
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code


def _capture_trigger_wait_config(args: argparse.Namespace) -> TriggerWaitConfig | None:
    wait_trigger = bool(getattr(args, "wait_trigger", False))
    timeout_ms = getattr(args, "trigger_timeout_ms", None)
    poll_interval_ms = int(getattr(args, "trigger_poll_interval_ms", 100))
    force_on_timeout = bool(getattr(args, "force_trigger_on_timeout", False))
    if not wait_trigger:
        if timeout_ms is not None:
            raise OscilloscopeError("--trigger-timeout-ms requires --wait-trigger")
        if force_on_timeout:
            raise OscilloscopeError("--force-trigger-on-timeout requires --wait-trigger")
        return None
    if timeout_ms is None:
        raise OscilloscopeError("--trigger-timeout-ms is required with --wait-trigger")
    if poll_interval_ms > timeout_ms:
        raise OscilloscopeError(
            "--trigger-poll-interval-ms must be less than or equal to --trigger-timeout-ms"
        )
    return TriggerWaitConfig(
        timeout_ms=timeout_ms,
        poll_interval_ms=poll_interval_ms,
        force_on_timeout=force_on_timeout,
    )


def _cmd_capture_batch(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        try:
            operation_result = run_capture_batch(
                scope,
                resource,
                CaptureBatchRequest(
                    channels=args.channel,
                    points=args.points,
                    waveform_format=args.waveform_format,
                    requested_count=args.count,
                    interval_seconds=args.interval_seconds,
                    output_dir=args.output_dir,
                    log_scpi=args.log_scpi,
                ),
                stop_requested=stop_requested,
            )
        except _OperationError as exc:
            operation_result = exc.result
            if operation_result.idn is not None:
                runtime._json_record_scope(scope, operation_result.idn)
            _apply_operation_result(operation_result)
            for line in operation_result.human_lines:
                print(line)
            raise OscilloscopeError(str(exc)) from exc

        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _cmd_measure_log(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        try:
            operation_result = run_measure_log(
                scope,
                resource,
                MeasureLogRequest(
                    channels=args.channel,
                    items=args.items,
                    pairs=tuple(args.pair),
                    pair_items=args.pair_items,
                    interval_seconds=args.interval_seconds,
                    requested_count=args.count,
                    requested_duration_seconds=args.duration_seconds,
                    output_dir=args.output_dir,
                    stop_on_error=args.stop_on_error,
                    log_scpi=args.log_scpi,
                ),
                stop_requested=stop_requested,
            )
        except _OperationError as exc:
            operation_result = exc.result
            if operation_result.idn is not None:
                runtime._json_record_scope(scope, operation_result.idn)
            _apply_operation_result(operation_result)
            for line in operation_result.human_lines:
                print(line)
            raise OscilloscopeError(str(exc)) from exc
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code


def _cmd_measure_until(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_measure_until(
            scope,
            resource,
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
            stop_requested=stop_requested,
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _cmd_triggered_measure_loop(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_triggered_measure_loop(
            scope,
            resource,
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
            stop_requested=stop_requested,
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _cmd_triggered_capture_series(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_triggered_capture_series(
            scope,
            resource,
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
            stop_requested=stop_requested,
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _cmd_sequence(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    document = load_sequence_document(args.sequence_file)
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_sequence(
            scope,
            resource,
            SequenceRequest(
                document,
                output_dir=args.output_dir,
                log_scpi=bool(args.log_scpi),
            ),
            stop_requested=stop_requested,
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _cmd_screenshot(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        print(f"Series: {idn.series or 'unknown'}")
        if scope.capabilities is None:
            print("Capabilities: unavailable for this model")
            return 1

        if args.query_hardcopy:
            state = scope.query_hardcopy_state()
            hardcopy = {
                "area": state.area,
                "ink_saver": state.ink_saver,
                "palette": state.palette,
                "layout": state.layout,
                "format": state.format,
                "raw_area": state.raw_area,
                "raw_ink_saver": state.raw_ink_saver,
                "raw_palette": state.raw_palette,
                "raw_layout": state.raw_layout,
                "raw_format": state.raw_format,
            }
            runtime._json_update_result(operation="query", hardcopy=hardcopy)
            print(f"Area: {state.area} (raw: {state.raw_area})")
            print(f"Ink saver: {state.ink_saver} (raw: {state.raw_ink_saver})")
            print(f"Palette: {state.palette} (raw: {state.raw_palette})")
            print(f"Layout: {state.layout} (raw: {state.raw_layout})")
            print(f"Format: {state.format} (raw: {state.raw_format})")
            entry = scope.query_system_error()
            runtime._json_record_system_error(entry)
            print(f"System error: {entry.format()}")
            return 1 if entry.is_error else 0

        options = preflight._screenshot_options(args)
        format_name = options.format or "png"
        output_path = _screenshot_output_path(args, format_name)
        background = args.background or DEFAULT_SCREENSHOT_BACKGROUND
        display_format = {"png": "PNG", "bmp": "BMP", "bmp8bit": "BMP8bit"}[
            format_name
        ]
        print(
            f"Planned capture: current screen {display_format} image with {background} background"
        )
        print(f"Screenshot timeout ms: {SCREENSHOT_TIMEOUT_MS} (temporary)")
        if preflight._uses_screenshot_format_pack(args):
            capture = scope.capture_screenshot(options=options, background=background)
            if options.ink_saver is not None:
                print(f"Command: {hardcopy_inksaver_command(options.ink_saver)}")
            else:
                print(
                    "Command: "
                    + hardcopy_inksaver_command(
                        hardcopy_inksaver_for_background(background)
                    )
                )
            if options.palette is not None:
                print(f"Command: {hardcopy_palette_command(options.palette)}")
            if options.layout is not None:
                print(f"Command: {hardcopy_layout_command(options.layout)}")
            print(f"Command: {hardcopy_screen_dump_data_query(format_name)}")
            written_image = _write_screenshot(capture, output_path, format_name)
        else:
            capture = scope.capture_screenshot_png(background=background)
            print(
                f"Command: {hardcopy_inksaver_command(hardcopy_inksaver_for_background(background))}"
            )
            print(f"Command: {screenshot_data_query()}")
            written_image = _write_screenshot_png(capture, output_path)
        file_kind = "png" if format_name == "png" else "bmp"
        files = [{"kind": file_kind, "path": str(written_image)}]
        _json_set_files(files)
        result = dict(
            format=capture.format_name,
            palette=(options.palette if preflight._uses_screenshot_format_pack(args) else capture.palette),
            background=capture.background,
            ink_saver=options.ink_saver,
            layout=options.layout,
            options={
                "format": options.format,
                "ink_saver": options.ink_saver,
                "palette": options.palette,
                "layout": options.layout,
            },
            byte_count=len(capture.data),
            timeout_ms=SCREENSHOT_TIMEOUT_MS,
            image_path=str(written_image),
            files=files,
        )
        if format_name == "png":
            result["png_path"] = str(written_image)
        runtime._json_update_result(**result)
        print(f"Format: {capture.format_name}")
        if capture.palette is not None:
            print(f"Palette: {capture.palette}")
        print(f"Background: {capture.background}")
        print(f"Bytes: {len(capture.data)}")
        if format_name == "png":
            print(f"PNG: {written_image}")
        else:
            print(f"BMP: {written_image}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_smoke(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        try:
            operation_result = run_smoke(
                scope,
                resource,
                SmokeRequest(output_dir=args.output_dir, log_scpi=args.log_scpi),
            )
        except _OperationError as exc:
            operation_result = exc.result
            if operation_result.idn is not None:
                runtime._json_record_scope(scope, operation_result.idn)
            _apply_operation_result(operation_result)
            for line in operation_result.human_lines:
                print(line)
            raise OscilloscopeError(str(exc)) from exc
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code


def _cmd_segmented_capture(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    request = preflight._segmented_capture_request(args)
    with runtime._open_scope(args, resource) as scope:
        operation_result = run_segmented_capture(scope, resource, request)
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code






def _cmd_autoscale(args: argparse.Namespace) -> int:
    return _cmd_simple_advanced(args, "autoscale")


def _cmd_setup_save(args: argparse.Namespace) -> int:
    return _cmd_simple_advanced(args, "setup-save")


def _cmd_setup_recall(args: argparse.Namespace) -> int:
    return _cmd_simple_advanced(args, "setup-recall")




















def _cmd_simple_advanced(args: argparse.Namespace, command_name: str) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        if scope.capabilities is None:
            print("Capabilities: unavailable for this model")
            return 1
        if command_name == "autoscale":
            channels = None if not args.source_channel else tuple(validate_analog_channel(channel, scope.capabilities) for channel in args.source_channel)
            scope.autoscale(channels, acquire_mode=args.acquire_mode, channels_mode=args.channels)
            commands = autoscale_commands(channels, acquire_mode=args.acquire_mode, channels_mode=args.channels, capabilities=scope.capabilities)
            runtime._json_update_result(operation="run", commands=commands, source_channels=None if channels is None else list(channels))
        elif command_name == "setup-save":
            scope.save_setup(slot=args.slot, file_spec=args.setup_file)
            commands = [setup_save_command(slot=args.slot, file_spec=args.setup_file)]
            runtime._json_update_result(operation="save", command=commands[0], slot=args.slot, file=args.setup_file)
        else:
            scope.recall_setup(slot=args.slot, file_spec=args.setup_file)
            commands = [setup_recall_command(slot=args.slot, file_spec=args.setup_file)]
            runtime._json_update_result(operation="recall", command=commands[0], slot=args.slot, file=args.setup_file)
        for command in commands:
            print(f"Command: {command}")
        if command_name == "autoscale" and not getattr(args, "simulate", False):
            print(
                "System error timeout ms: "
                f"{AUTOSCALE_SYSTEM_ERROR_TIMEOUT_MS} (temporary)"
            )
            entry = _query_system_error_with_temporary_timeout(
                scope, AUTOSCALE_SYSTEM_ERROR_TIMEOUT_MS
            )
            if entry.code == -113 and getattr(args, "source_channel", None):
                fallback_command = ":AUToscale"
                print(
                    "Autoscale source form was rejected; "
                    f"retrying with {fallback_command}"
                )
                scope.scpi.write(fallback_command)
                commands.append(fallback_command)
                runtime._json_update_result(
                    commands=commands,
                    fallback="bare_autoscale_after_source_undefined_header",
                )
                entry = _query_system_error_with_temporary_timeout(
                    scope, AUTOSCALE_SYSTEM_ERROR_TIMEOUT_MS
                )
        else:
            entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _query_system_error_with_temporary_timeout(scope: Oscilloscope, timeout_ms: int):
    original_timeout = scope.scpi.timeout
    scope.scpi.set_timeout(timeout_ms)
    try:
        return scope.query_system_error()
    finally:
        scope.scpi.set_timeout(original_timeout)


def _cmd_acquisition_check(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        try:
            operation_result = run_acquisition_check(
                scope,
                resource,
                AcquisitionCheckRequest(
                    output_dir=args.output_dir,
                    average_count=args.average_count,
                    check_only=bool(getattr(args, "check_only", False)),
                    stop_on_error=bool(getattr(args, "stop_on_error", False)),
                    restore_type=bool(getattr(args, "restore_type", False)),
                    log_scpi=args.log_scpi,
                ),
            )
        except _OperationError as exc:
            operation_result = exc.result
            if operation_result.idn is not None:
                runtime._json_record_scope(scope, operation_result.idn)
            _apply_operation_result(operation_result)
            for line in operation_result.human_lines:
                print(line)
            raise OscilloscopeError(str(exc)) from exc
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code


def _default_capture_csv_path(now: datetime | None = None) -> Path:
    if now is None:
        capture_time = datetime.now(_CAPTURE_DEFAULT_TIMEZONE)
    elif now.tzinfo is None:
        capture_time = now.replace(tzinfo=_CAPTURE_DEFAULT_TIMEZONE)
    else:
        capture_time = now.astimezone(_CAPTURE_DEFAULT_TIMEZONE)

    return Path("data") / capture_time.strftime("%Y-%m-%d-%H-%M-%S.csv")


def _default_screenshot_path(
    now: datetime | None = None, *, extension: str = ".png"
) -> Path:
    if now is None:
        capture_time = datetime.now(_CAPTURE_DEFAULT_TIMEZONE)
    elif now.tzinfo is None:
        capture_time = now.replace(tzinfo=_CAPTURE_DEFAULT_TIMEZONE)
    else:
        capture_time = now.astimezone(_CAPTURE_DEFAULT_TIMEZONE)

    return Path("data") / (capture_time.strftime("%Y-%m-%d-%H-%M-%S") + extension)


def _screenshot_output_path(args: argparse.Namespace, format_name: str) -> Path:
    if args.output_path is not None:
        return Path(args.output_path)
    if format_name == "png":
        return _default_screenshot_path()
    return _default_screenshot_path(extension=".bmp")


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


def _write_screenshot_png(capture, output_path: Path) -> Path:
    try:
        return write_screenshot_png(capture, output_path)
    except OSError as exc:
        raise OscilloscopeError(
            _format_output_file_error("screenshot PNG", output_path, exc)
        ) from exc


def _write_screenshot(capture, output_path: Path, format_name: str) -> Path:
    try:
        return write_screenshot(capture, output_path)
    except OSError as exc:
        label = "screenshot PNG" if format_name == "png" else "screenshot BMP"
        raise OscilloscopeError(
            _format_output_file_error(label, output_path, exc)
        ) from exc


def _write_json_file(
    payload: dict[str, object],
    path: Path,
    *,
    file_kind: str,
) -> Path:
    return write_json_file(payload, path, file_kind=file_kind)


def _write_json_file_best_effort(payload: dict[str, object], path: Path) -> None:
    write_json_file_best_effort(payload, path)


def _format_output_file_error(file_kind: str, path: Path, exc: OSError) -> str:
    reason = exc.strerror or str(exc)
    if file_kind.startswith("screenshot"):
        message = f"could not write {file_kind} file {path}: {reason}"
    else:
        message = f"could not write waveform {file_kind} file {path}: {reason}"
    if isinstance(exc, PermissionError):
        if file_kind.startswith("screenshot"):
            message += (
                ". The file may be open in another program, "
                "or the folder may not be writable."
            )
        else:
            message += (
                ". The file may be open in another program, such as Excel, "
                "or the folder may not be writable."
            )
    return message


def _format_plain_output_file_error(file_kind: str, path: Path, exc: OSError) -> str:
    reason = exc.strerror or str(exc)
    message = f"could not write {file_kind} file {path}: {reason}"
    if isinstance(exc, PermissionError):
        message += ". The file may be open in another program, or the folder may not be writable."
    return message


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _integer_value(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer or 0x hexadecimal value") from exc


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _capture_channel_arg(value: str) -> int | str:
    if value.strip().lower() == "all":
        return "all"
    try:
        return _positive_int(value)
    except argparse.ArgumentTypeError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer or all") from exc


def _finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_channel_offset(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_channel_scale(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _nonnegative_finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not parsed == parsed or parsed in (float("inf"), float("-inf")):
        raise argparse.ArgumentTypeError("must be finite")
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _probe_ratio_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_probe_ratio(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _probe_skew_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_probe_skew(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _finite_timebase_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_timebase_position(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _positive_timebase_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_timebase_scale(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _trigger_level_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_trigger_level(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _holdoff_seconds_arg(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    try:
        return validate_trigger_holdoff(parsed)
    except OscilloscopeError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _strict_bool_arg(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("must be true or false")


def _setup_slot_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0 or parsed > 9:
        raise argparse.ArgumentTypeError("must be between 0 and 9")
    return parsed


def _positive_plain_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not parsed == parsed or parsed in (float("inf"), float("-inf")):
        raise argparse.ArgumentTypeError("must be finite")
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _measurement_finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not parsed == parsed or parsed in (float("inf"), float("-inf")):
        raise argparse.ArgumentTypeError("must be a finite number")
    return parsed


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


def _waveform_points_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed not in SUPPORTED_WAVEFORM_POINTS:
        supported = ", ".join(str(point_count) for point_count in SUPPORTED_WAVEFORM_POINTS)
        raise argparse.ArgumentTypeError(
            f"waveform capture supports only these point counts: {supported}"
        )
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
