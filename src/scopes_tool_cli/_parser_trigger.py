"""CLI parsers for trigger, cursor, and external trigger input commands."""

from __future__ import annotations

from scopes_tool_core.cursor import CURSOR_FUNCTIONS
from scopes_tool_core.trigger import TRIGGER_MODES

from ._parser_common import (
    _add_scope_connection_args,
    _holdoff_seconds_arg,
    _measurement_finite_float,
    _positive_float,
    _positive_int,
    _strict_bool_arg,
    _trigger_level_float,
)


def _register_trigger_parsers(subparsers) -> None:
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

    trigger_mode_parser = subparsers.add_parser(
        "trigger-mode",
        allow_abbrev=False,
        help="configure or query trigger type",
    )
    _add_scope_connection_args(trigger_mode_parser)
    trigger_mode_parser.add_argument(
        "--query",
        action="store_true",
        help="query trigger type",
    )
    trigger_mode_parser.add_argument(
        "--mode",
        choices=TRIGGER_MODES,
        default=None,
        help="canonical trigger type",
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
    cursor_query_off = cursor_parser.add_mutually_exclusive_group(required=False)
    cursor_query_off.add_argument("--query", dest="cursor_query", action="store_true")
    cursor_query_off.add_argument("--off", dest="cursor_off", action="store_true")
    cursor_parser.add_argument("--x1", type=_measurement_finite_float, default=None)
    cursor_parser.add_argument("--source-channel", type=_positive_int, default=None)
    cursor_parser.add_argument("--x2", type=_measurement_finite_float, default=None)
    cursor_parser.add_argument("--y1", type=_measurement_finite_float, default=None)
    cursor_parser.add_argument("--y2", type=_measurement_finite_float, default=None)
    cursor_parser.add_argument(
        "--function",
        dest="cursor_function",
        choices=CURSOR_FUNCTIONS,
        default=None,
        help="select the cursor function explicitly; the model decides the default from the requested axes",
    )
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
