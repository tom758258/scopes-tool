"""CLI pre-open validation for Trigger and External Trigger commands."""

from __future__ import annotations

import argparse

from scopes_tool_core.channel import validate_analog_channel
from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.trigger import (
    normalize_edge_burst_slope,
    normalize_delay_slope,
    normalize_glitch_qualifier,
    normalize_runt_qualifier,
    normalize_setup_hold_slope,
    normalize_transition_qualifier,
    normalize_transition_slope,
    normalize_trigger_sweep,
    trigger_mode_command,
    tv_trigger_configure_commands,
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

from ._preflight_common import _pre_open_capabilities


def _validate_trigger_edge_args(args: argparse.Namespace) -> None:
    configure_values = (
        getattr(args, "source_channel", None),
        getattr(args, "level", None),
        getattr(args, "slope", None),
    )
    if getattr(args, "edge_query", False):
        if any(value is not None for value in configure_values):
            raise ParameterValidationError(
                "trigger-edge --query cannot be combined with configure options."
            )
        return
    if not all(value is not None for value in configure_values):
        raise ParameterValidationError(
            "trigger-edge configure requires --source-channel, --level, and --slope."
        )

def _validate_trigger_edge_source_args(args: argparse.Namespace) -> None:
    source_channel = getattr(args, "source_channel", None)
    source = getattr(args, "source", None)
    if getattr(args, "trigger_edge_source_query", False):
        if source_channel is not None or source is not None:
            raise ParameterValidationError(
                "trigger-edge-source --query cannot be combined with configure options."
            )
        return
    if source_channel is not None and source is not None:
        raise ParameterValidationError(
            "trigger-edge-source --source-channel cannot be combined with --source."
        )
    if source_channel is None and source is None:
        raise ParameterValidationError(
            "trigger-edge-source requires --query, --source-channel, or --source."
        )

def _validate_trigger_edge_slope_args(args: argparse.Namespace) -> None:
    query = getattr(args, "trigger_edge_slope_query", False)
    slope = getattr(args, "slope", None)
    if query:
        if slope is not None:
            raise ParameterValidationError(
                "trigger-edge-slope --query cannot be combined with --slope."
            )
        return
    if slope is None:
        raise ParameterValidationError("trigger-edge-slope requires --query or --slope.")

def _validate_trigger_edge_level_args(args: argparse.Namespace) -> None:
    source_channel = getattr(args, "source_channel", None)
    query = getattr(args, "trigger_edge_level_query", False)
    level_volts = getattr(args, "level_volts", None)
    if source_channel is None:
        raise ParameterValidationError("trigger-edge-level requires --source-channel.")
    if query:
        if level_volts is not None:
            raise ParameterValidationError(
                "trigger-edge-level --query cannot be combined with --level-volts."
            )
        return
    if level_volts is None:
        raise ParameterValidationError(
            "trigger-edge-level requires --query or --level-volts."
        )
    validate_trigger_level(level_volts)

def _validate_external_trigger_range_args(args: argparse.Namespace) -> None:
    query = getattr(args, "external_trigger_range_query", False)
    range_volts = getattr(args, "range_volts", None)
    if query:
        if range_volts is not None:
            raise ParameterValidationError(
                "external-trigger-range --query cannot be combined with --range-volts."
            )
        return
    if range_volts is None:
        raise ParameterValidationError(
            "external-trigger-range requires --query or --range-volts."
        )
    validate_external_trigger_range(range_volts)

def _validate_trigger_edge_external_level_args(args: argparse.Namespace) -> None:
    query = getattr(args, "trigger_edge_external_level_query", False)
    level_volts = getattr(args, "level_volts", None)
    if query:
        if level_volts is not None:
            raise ParameterValidationError(
                "trigger-edge-external-level --query cannot be combined with --level-volts."
            )
        return
    if level_volts is None:
        raise ParameterValidationError(
            "trigger-edge-external-level requires --query or --level-volts."
        )
    validate_trigger_level(level_volts)

def _validate_external_trigger_probe_args(args: argparse.Namespace) -> None:
    query = getattr(args, "external_trigger_probe_query", False)
    attenuation = getattr(args, "attenuation", None)
    if query:
        if attenuation is not None:
            raise ParameterValidationError(
                "external-trigger-probe --query cannot be combined with --attenuation."
            )
        return
    if attenuation is None:
        raise ParameterValidationError(
            "external-trigger-probe requires --query or --attenuation."
        )
    validate_external_trigger_probe_attenuation(attenuation)

def _validate_external_trigger_units_args(args: argparse.Namespace) -> None:
    query = getattr(args, "external_trigger_units_query", False)
    units = getattr(args, "units", None)
    if query:
        if units is not None:
            raise ParameterValidationError(
                "external-trigger-units --query cannot be combined with --units."
            )
        return
    if units is None:
        raise ParameterValidationError("external-trigger-units requires --query or --units.")
    validate_external_trigger_units(units)

def _validate_external_trigger_settings_args(args: argparse.Namespace) -> None:
    if not getattr(args, "query", False):
        raise ParameterValidationError("external-trigger-settings requires --query.")

def _validate_trigger_mode_args(args: argparse.Namespace) -> None:
    if args.query:
        if args.mode is not None:
            raise ParameterValidationError(
                "trigger-mode --query cannot be combined with configure options."
            )
        return
    if args.mode is None:
        raise ParameterValidationError("trigger-mode configure requires --mode.")
    trigger_mode_command(args.mode)
    capabilities = _pre_open_capabilities(args)
    if capabilities is not None and capabilities.trigger_modes is not None:
        if args.mode not in capabilities.trigger_modes:
            raise ParameterValidationError(
                f"trigger-mode {args.mode} is unsupported for {args.model}."
            )


def _validate_trigger_sweep_args(args: argparse.Namespace) -> None:
    if getattr(args, "trigger_sweep_query", False):
        if getattr(args, "mode", None) is not None:
            raise ParameterValidationError(
                "trigger-sweep --query cannot be combined with configure options."
            )
        return
    if getattr(args, "mode", None) is None:
        raise ParameterValidationError("trigger-sweep configure requires --mode.")
    normalize_trigger_sweep(args.mode)

def _validate_trigger_reject_args(args: argparse.Namespace, command: str) -> None:
    query_attr = (
        "trigger_noise_reject_query"
        if command == "trigger-noise-reject"
        else "trigger_hf_reject_query"
    )
    if getattr(args, query_attr, False):
        if getattr(args, "enabled", None) is not None:
            raise ParameterValidationError(
                f"{command} --query cannot be combined with configure options."
            )
        return
    if getattr(args, "enabled", None) is None:
        raise ParameterValidationError(f"{command} configure requires --enabled.")
    if not isinstance(args.enabled, bool):
        raise ParameterValidationError(f"{command} --enabled must be true or false.")

def _validate_edge_coupling_args(args: argparse.Namespace) -> None:
    if getattr(args, "trigger_edge_coupling_query", False):
        if getattr(args, "coupling", None) is not None:
            raise ParameterValidationError(
                "trigger-edge-coupling --query cannot be combined with configure options."
            )
        return
    if getattr(args, "coupling", None) is None:
        raise ParameterValidationError(
            "trigger-edge-coupling configure requires --coupling."
        )

def _validate_edge_reject_args(args: argparse.Namespace) -> None:
    if getattr(args, "trigger_edge_reject_query", False):
        if getattr(args, "reject", None) is not None:
            raise ParameterValidationError(
                "trigger-edge-reject --query cannot be combined with configure options."
            )
        return
    if getattr(args, "reject", None) is None:
        raise ParameterValidationError(
            "trigger-edge-reject configure requires --reject."
        )

def _validate_trigger_glitch_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "channel", None),
        getattr(args, "polarity", None),
        getattr(args, "qualifier", None),
        getattr(args, "time_seconds", None),
        getattr(args, "min_time_seconds", None),
        getattr(args, "max_time_seconds", None),
        getattr(args, "level_volts", None),
    )
    if getattr(args, "glitch_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-pulse-width --query cannot be combined with configure options."
            )
        return

    if args.channel is None or args.polarity is None or args.qualifier is None:
        raise ParameterValidationError(
            "trigger-pulse-width configure requires --channel, --polarity, and --qualifier."
        )

    qualifier = normalize_glitch_qualifier(args.qualifier)
    if qualifier in {"GREaterthan", "LESSthan"}:
        if args.time_seconds is None:
            raise ParameterValidationError(
                "trigger-pulse-width greater-than and less-than require --time-seconds."
            )
        if args.min_time_seconds is not None or args.max_time_seconds is not None:
            raise ParameterValidationError(
                "trigger-pulse-width greater-than and less-than reject range timing options."
            )
        validate_trigger_time(args.time_seconds)
        return

    if args.time_seconds is not None:
        raise ParameterValidationError("trigger-pulse-width range rejects --time-seconds.")
    if args.min_time_seconds is None or args.max_time_seconds is None:
        raise ParameterValidationError(
            "trigger-pulse-width range requires --min-time-seconds and --max-time-seconds."
        )
    min_time = validate_trigger_time(args.min_time_seconds)
    max_time = validate_trigger_time(args.max_time_seconds)
    if min_time >= max_time:
        raise ParameterValidationError(
            "trigger-pulse-width --min-time-seconds must be less than --max-time-seconds."
        )

def _validate_trigger_runt_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "channel", None),
        getattr(args, "polarity", None),
        getattr(args, "qualifier", None),
        getattr(args, "time_seconds", None),
        getattr(args, "low_level_volts", None),
        getattr(args, "high_level_volts", None),
    )
    if getattr(args, "runt_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-runt --query cannot be combined with configure options."
            )
        return

    if (
        args.channel is None
        or args.polarity is None
        or args.qualifier is None
        or args.low_level_volts is None
        or args.high_level_volts is None
    ):
        raise ParameterValidationError(
            "trigger-runt configure requires --channel, --polarity, --qualifier, "
            "--low-level-volts, and --high-level-volts."
        )

    qualifier = normalize_runt_qualifier(args.qualifier)
    low_level = validate_trigger_level(args.low_level_volts)
    high_level = validate_trigger_level(args.high_level_volts)
    if low_level >= high_level:
        raise ParameterValidationError(
            "trigger-runt --low-level-volts must be less than --high-level-volts."
        )

    if qualifier in {"GREaterthan", "LESSthan"}:
        if args.time_seconds is None:
            raise ParameterValidationError(
                "trigger-runt greater-than and less-than require --time-seconds."
            )
        validate_trigger_time(args.time_seconds)
        return

    if args.time_seconds is not None:
        raise ParameterValidationError("trigger-runt qualifier none rejects --time-seconds.")

def _validate_trigger_transition_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "channel", None),
        getattr(args, "slope", None),
        getattr(args, "qualifier", None),
        getattr(args, "time_seconds", None),
        getattr(args, "low_level_volts", None),
        getattr(args, "high_level_volts", None),
    )
    if getattr(args, "transition_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-transition --query cannot be combined with configure options."
            )
        return

    if (
        args.channel is None
        or args.slope is None
        or args.qualifier is None
        or args.time_seconds is None
        or args.low_level_volts is None
        or args.high_level_volts is None
    ):
        raise ParameterValidationError(
            "trigger-transition configure requires --channel, --slope, --qualifier, "
            "--time-seconds, --low-level-volts, and --high-level-volts."
        )

    normalize_transition_slope(args.slope)
    normalize_transition_qualifier(args.qualifier)
    validate_trigger_time(args.time_seconds)
    low_level = validate_trigger_level(args.low_level_volts)
    high_level = validate_trigger_level(args.high_level_volts)
    if low_level >= high_level:
        raise ParameterValidationError(
            "trigger-transition --low-level-volts must be less than --high-level-volts."
        )

def _validate_trigger_delay_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "arm_channel", None),
        getattr(args, "arm_slope", None),
        getattr(args, "trigger_channel", None),
        getattr(args, "trigger_slope", None),
        getattr(args, "time_seconds", None),
        getattr(args, "count", None),
    )
    if getattr(args, "delay_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-delay --query cannot be combined with configure options."
            )
        return

    if (
        args.arm_channel is None
        or args.arm_slope is None
        or args.trigger_channel is None
        or args.trigger_slope is None
        or args.time_seconds is None
        or args.count is None
    ):
        raise ParameterValidationError(
            "trigger-delay configure requires --arm-channel, --arm-slope, "
            "--trigger-channel, --trigger-slope, --time-seconds, and --count."
        )

    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        validate_analog_channel(args.arm_channel, capabilities)
        validate_analog_channel(args.trigger_channel, capabilities)
    normalize_delay_slope(args.arm_slope)
    normalize_delay_slope(args.trigger_slope)
    validate_delay_trigger_time(args.time_seconds)
    validate_delay_trigger_count(args.count)

def _validate_trigger_setup_hold_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "clock_channel", None),
        getattr(args, "data_channel", None),
        getattr(args, "slope", None),
        getattr(args, "setup_time", None),
        getattr(args, "hold_time", None),
    )
    if getattr(args, "setup_hold_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-setup-hold --query cannot be combined with configure options."
            )
        return

    if (
        args.clock_channel is None
        or args.data_channel is None
        or args.slope is None
        or args.setup_time is None
        or args.hold_time is None
    ):
        raise ParameterValidationError(
            "trigger-setup-hold configure requires --clock-channel, --data-channel, "
            "--slope, --setup-time, and --hold-time."
        )

    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        validate_analog_channel(args.clock_channel, capabilities)
        validate_analog_channel(args.data_channel, capabilities)
    normalize_setup_hold_slope(args.slope)
    validate_setup_hold_trigger_time(args.setup_time, "setup")
    validate_setup_hold_trigger_time(args.hold_time, "hold")

def _validate_trigger_edge_burst_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "source_channel", None),
        getattr(args, "slope", None),
        getattr(args, "count", None),
        getattr(args, "idle_time", None),
        getattr(args, "level_volts", None),
    )
    if getattr(args, "edge_burst_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-edge-burst --query cannot be combined with configure options."
            )
        return

    if (
        args.source_channel is None
        or args.slope is None
        or args.count is None
        or args.idle_time is None
    ):
        raise ParameterValidationError(
            "trigger-edge-burst configure requires --source-channel, --slope, "
            "--count, and --idle-time."
        )

    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        validate_analog_channel(args.source_channel, capabilities)
    normalize_edge_burst_slope(args.slope)
    validate_edge_burst_count(args.count)
    validate_edge_burst_idle_time(args.idle_time)
    if args.level_volts is not None:
        validate_trigger_level(args.level_volts)

def _validate_trigger_tv_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "source_channel", None),
        getattr(args, "standard", None),
        getattr(args, "mode", None),
        getattr(args, "polarity", None),
        getattr(args, "line", None),
    )
    if getattr(args, "tv_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-tv --query cannot be combined with configure options."
            )
        return

    if (
        args.source_channel is None
        or args.standard is None
        or args.mode is None
        or args.polarity is None
    ):
        raise ParameterValidationError(
            "trigger-tv configure requires --source-channel, --standard, --mode, and --polarity."
        )

    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        tv_trigger_configure_commands(
            source_channel=args.source_channel,
            standard=args.standard,
            mode=args.mode,
            polarity=args.polarity,
            capabilities=capabilities,
            line=args.line,
        )

def _validate_trigger_pattern_args(args: argparse.Namespace) -> None:
    if getattr(args, "pattern_query", False):
        if args.pattern is not None:
            raise ParameterValidationError(
                "trigger-pattern --query cannot be combined with --pattern."
            )
        return
    if args.pattern is None:
        raise ParameterValidationError("trigger-pattern configure requires --pattern.")
    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        validate_pattern_trigger_pattern(args.pattern, capabilities)

def _validate_trigger_or_args(args: argparse.Namespace) -> None:
    if getattr(args, "or_query", False):
        if args.pattern is not None:
            raise ParameterValidationError(
                "trigger-or --query cannot be combined with --pattern."
            )
        return
    if args.pattern is None:
        raise ParameterValidationError("trigger-or configure requires --pattern.")
    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        validate_or_trigger_pattern(args.pattern, capabilities)
