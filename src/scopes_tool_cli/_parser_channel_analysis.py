"""CLI parsers for channel, display, screen measure, DVM, DEMO, and WGEN commands."""

from __future__ import annotations

import argparse

from scopes_tool_core.demo import DEMO_FUNCTIONS
from scopes_tool_core.dvm import DVM_MODES
from scopes_tool_core.measurements import (
    MEASUREMENT_INSTALL_ITEM_CHOICES,
    MEASUREMENT_WINDOW_CHOICES,
)
from scopes_tool_core.wgen import WGEN_FUNCTIONS, WGEN_LOADS

from ._parser_common import (
    _add_channel_arg,
    _add_scope_connection_args,
    _finite_float,
    _positive_float,
    _positive_int,
    _probe_ratio_float,
    _probe_skew_float,
    _strict_bool_arg,
)


def _register_channel_analysis_parsers(subparsers) -> None:
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

    measure_menu_parser = subparsers.add_parser(
        "measure-menu", help="open the instrument Measurement interface"
    )
    _add_scope_connection_args(measure_menu_parser)

    measure_install_parser = subparsers.add_parser(
        "measure-install", help="install one front-panel measurement"
    )
    _add_scope_connection_args(measure_install_parser)
    measure_install_parser.add_argument(
        "--source-channel", type=_positive_int, required=True
    )
    measure_install_parser.add_argument(
        "--item", choices=MEASUREMENT_INSTALL_ITEM_CHOICES, required=True
    )

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
