from __future__ import annotations

import argparse

from scopes_tool_core.fft import (
    FFT_DETECTION_TYPES,
    FFT_GATES,
    FFT_OPERATIONS,
    FFT_PHASE_REFERENCES,
)
from scopes_tool_core.math import (
    MATH_COMPOSITE_OPERATIONS,
    MATH_FILTER_OPERATIONS,
    MATH_OPERATIONS,
    MATH_SOURCES,
    MATH_TRANSFORM_SOURCES,
    MATH_TRANSFORMS,
    MATH_TREND_MEASUREMENTS,
    MATH_VISUALIZATION_OPERATIONS,
)
from scopes_tool_core.trigger_holdoff import (
    validate_trigger_holdoff,
)
from scopes_tool_core.channel import (
    validate_channel_offset,
    validate_channel_scale,
    validate_probe_ratio,
    validate_probe_skew,
)
from scopes_tool_core.cleanup import CLEANUP_PROFILES
from scopes_tool_core.demo import DEMO_FUNCTIONS
from scopes_tool_core.wgen import WGEN_FUNCTIONS, WGEN_LOADS
from scopes_tool_core.dvm import DVM_MODES
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.measurements import (
    MEASUREMENT_ITEM_CHOICES,
    MEASUREMENT_WINDOW_CHOICES,
)
from scopes_tool_core.save_export import (
    SAVE_IMAGE_FORMATS,
    SAVE_IMAGE_PALETTES,
    SAVE_WAVEFORM_FORMATS,
)
from scopes_tool_core.search import (
    CAN_SEARCH_ID_MODES,
    CAN_SEARCH_MODES,
    I2C_SEARCH_MODES,
    SEARCH_MODES,
    SEARCH_QUALIFIERS,
    SPI_SEARCH_MODES,
    UART_SEARCH_MODES,
)
from scopes_tool_core.serial import (
    CAN_SIGNAL_DEFINITIONS,
    CAN_TRIGGER_ID_MODES,
    CAN_TRIGGER_TYPES,
    I2C_ADDRESS_SIZES,
    I2C_TRIGGER_QUALIFIERS,
    I2C_TRIGGER_TYPES,
    SERIAL_BIT_ORDERS,
    SERIAL_LISTER_DISPLAYS,
    SERIAL_LISTER_REFERENCES,
    SERIAL_MODES,
    SPI_CLOCK_SLOPES,
    SPI_FRAMINGS,
    SPI_TRIGGER_TYPES,
    UART_PARITIES,
    UART_POLARITIES,
    UART_TRIGGER_QUALIFIERS,
    UART_TRIGGER_TYPES,
)
from scopes_tool_core.simulator_config import PRESET_NAMES
from scopes_tool_core.timebase import (
    validate_timebase_position,
    validate_timebase_scale,
)
from scopes_tool_core.trigger import validate_trigger_level
from scopes_tool_core.waveform import SUPPORTED_WAVEFORM_POINTS


_SERIAL_SOURCE_HELP = (
    "channelN or external; source availability may depend on the other "
    "configured Serial bus; query both buses after an instrument settings conflict"
)


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

    manifest_parser = subparsers.add_parser(
        "manifest",
        allow_abbrev=False,
        help=(
            "print static tool identity and Worker protocol compatibility "
            "without hardware access"
        ),
    )
    manifest_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="write a single machine-readable JSON object to stdout",
    )

    capabilities_parser = subparsers.add_parser(
        "capabilities",
        allow_abbrev=False,
        help=(
            "print registered model capability data from Core without "
            "hardware access"
        ),
    )
    capabilities_parser.add_argument(
        "--model",
        default=None,
        help=(
            "canonical physical model ID; defaults to keysight-dsox4024a "
            "following the existing CLI planning-model policy"
        ),
    )
    capabilities_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="write a single machine-readable JSON object to stdout",
    )

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
    _add_channel_arg(channel_display_parser)
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
    _add_channel_arg(channel_label_parser)
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
    _add_channel_arg(channel_scale_parser)
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
    _add_channel_arg(channel_offset_parser)
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
    _add_channel_arg(channel_coupling_parser)
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
    _add_channel_arg(channel_probe_parser)
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
    _add_channel_arg(channel_bandwidth_limit_parser)
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
    _add_channel_arg(channel_impedance_parser)
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
    _add_channel_arg(channel_invert_parser)
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
    _add_channel_arg(channel_range_parser)
    range_action = channel_range_parser.add_mutually_exclusive_group(required=True)
    range_action.add_argument("--volts-full-scale", dest="range_value", type=_positive_float, help="full-scale range in volts")
    range_action.add_argument("--query", dest="range_query", action="store_true", help="query the channel full-scale range")

    channel_units_parser = subparsers.add_parser(
        "channel-units",
        help="set or query one analog channel units",
    )
    _add_scope_connection_args(channel_units_parser)
    _add_channel_arg(channel_units_parser)
    units_action = channel_units_parser.add_mutually_exclusive_group(required=True)
    units_action.add_argument("--units", dest="units_value", choices=("volt", "amp"), help="channel units")
    units_action.add_argument("--query", dest="units_query", action="store_true", help="query channel units")

    channel_vernier_parser = subparsers.add_parser(
        "channel-vernier",
        help="enable, disable, or query one analog channel vernier scaling",
    )
    _add_scope_connection_args(channel_vernier_parser)
    _add_channel_arg(channel_vernier_parser)
    vernier_action = channel_vernier_parser.add_mutually_exclusive_group(required=True)
    vernier_action.add_argument("--on", dest="vernier_action", action="store_const", const="on", help="turn channel vernier on")
    vernier_action.add_argument("--off", dest="vernier_action", action="store_const", const="off", help="turn channel vernier off")
    vernier_action.add_argument("--query", dest="vernier_action", action="store_const", const="query", help="query channel vernier")

    channel_probe_skew_parser = subparsers.add_parser(
        "channel-probe-skew",
        help="set or query one analog channel probe skew",
    )
    _add_scope_connection_args(channel_probe_skew_parser)
    _add_channel_arg(channel_probe_skew_parser)
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
        "dvm-query", allow_abbrev=False, help="query aggregate DVM state"
    )
    _add_scope_connection_args(dvm_query_parser)
    dvm_query_parser.add_argument("--query", action="store_true", required=True)

    demo_query_parser = subparsers.add_parser(
        "demo-query", allow_abbrev=False, help="query aggregate DEMO output state"
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
        "wgen-query", allow_abbrev=False, help="query aggregate WGEN state"
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
    _add_bus_arg(serial_query_parser)

    serial_mode_parser = subparsers.add_parser(
        "serial-mode",
        allow_abbrev=False,
        help="configure or query serial decode bus mode",
    )
    _add_scope_connection_args(serial_mode_parser)
    _add_bus_arg(serial_mode_parser)
    serial_mode_action = serial_mode_parser.add_mutually_exclusive_group(required=True)
    serial_mode_action.add_argument("--query", action="store_true")
    serial_mode_action.add_argument("--mode", choices=SERIAL_MODES)

    serial_display_parser = subparsers.add_parser(
        "serial-display",
        allow_abbrev=False,
        help="configure or query serial decode bus display state",
    )
    _add_scope_connection_args(serial_display_parser)
    _add_bus_arg(serial_display_parser)
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
        default=None,
        help=(
            "host CSV output path for :LISTer:DATA? payload; defaults to "
            "data/<UTC+8 timestamp>-lister.csv"
        ),
    )

    serial_uart_parser = subparsers.add_parser(
        "serial-uart", allow_abbrev=False, help="configure or query basic UART decode settings"
    )
    _add_scope_connection_args(serial_uart_parser)
    _add_bus_arg(serial_uart_parser)
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
    _add_bus_arg(serial_uart_trigger_parser)
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
    _add_bus_arg(serial_i2c_trigger_parser)
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
    _add_bus_arg(serial_spi_trigger_parser)
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
    _add_bus_arg(serial_can_trigger_parser)
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
    _add_bus_arg(serial_i2c_parser)
    serial_i2c_parser.add_argument("--query", action="store_true")
    serial_i2c_parser.add_argument("--clock-source", help=_SERIAL_SOURCE_HELP)
    serial_i2c_parser.add_argument("--data-source", help=_SERIAL_SOURCE_HELP)
    serial_i2c_parser.add_argument("--address-size", choices=I2C_ADDRESS_SIZES)

    serial_spi_parser = subparsers.add_parser(
        "serial-spi", allow_abbrev=False, help="configure or query basic SPI decode settings"
    )
    _add_scope_connection_args(serial_spi_parser)
    _add_bus_arg(serial_spi_parser)
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
    _add_bus_arg(serial_can_parser)
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
    _add_bus_arg(serial_search_uart_parser)
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
    _add_bus_arg(serial_search_i2c_parser)
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
    _add_bus_arg(serial_search_spi_parser)
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
    _add_bus_arg(serial_search_can_parser)
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
    _add_slot_arg(reference_save_parser)
    reference_save_parser.add_argument("--source-channel", type=_positive_int, required=True)

    reference_display_parser = subparsers.add_parser(
        "reference-display", help="set or query reference waveform display state"
    )
    _add_scope_connection_args(reference_display_parser)
    _add_slot_arg(reference_display_parser)
    reference_display_action = reference_display_parser.add_mutually_exclusive_group(required=True)
    reference_display_action.add_argument("--query", action="store_true")
    reference_display_action.add_argument("--state", choices=("on", "off"))

    reference_label_parser = subparsers.add_parser(
        "reference-label", help="set or query a reference waveform label"
    )
    _add_scope_connection_args(reference_label_parser)
    _add_slot_arg(reference_label_parser)
    reference_label_action = reference_label_parser.add_mutually_exclusive_group(required=True)
    reference_label_action.add_argument("--query", action="store_true")
    reference_label_action.add_argument("--text")

    reference_clear_parser = subparsers.add_parser(
        "reference-clear", help="clear a reference waveform slot"
    )
    _add_scope_connection_args(reference_clear_parser)
    _add_slot_arg(reference_clear_parser)

    reference_query_parser = subparsers.add_parser(
        "reference-query", help="query reference waveform display and label state"
    )
    _add_scope_connection_args(reference_query_parser)
    _add_slot_arg(reference_query_parser)

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
    _add_function_arg(fft_parser)
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
    _add_function_arg(math_display_parser)
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
    _add_function_arg(math_vertical_parser)
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
    _add_function_arg(math_operator_parser)
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
    _add_function_arg(math_transform_parser)
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
    _add_function_arg(math_filter_parser)
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
    _add_function_arg(math_visualization_parser)
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
    _add_function_arg(math_clear_parser)

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


def _add_channel_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--channel",
        type=_positive_int,
        required=True,
        help="analog channel number, validated against the detected scope model",
    )


def _add_bus_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bus", type=_positive_int, required=True)


def _add_function_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--function", type=_positive_int, required=True)


def _add_slot_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--slot", type=_positive_int, required=True)


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

