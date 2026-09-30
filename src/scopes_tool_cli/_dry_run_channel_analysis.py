"""CLI dry-run planning for channel, display, measurement, reference, DVM, DEMO, and WGEN commands."""

from __future__ import annotations

import argparse

from scopes_tool_core.capabilities import ScopeCapabilities
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
    channel_probe_ratio_command,
    channel_probe_ratio_query,
    channel_probe_skew_command,
    channel_probe_skew_query,
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
    validate_channel_label,
    validate_channel_offset,
    validate_channel_range,
    validate_channel_scale,
    validate_probe_ratio,
    validate_probe_skew,
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
from scopes_tool_core.measurements import (
    measurement_results_query,
    validate_measure_results_dump_supported,
    validate_measure_statistics_supported,
)
from scopes_tool_core.planning import (
    MeasurePlanRequest,
    MeasureSweepPlanRequest,
    plan_measure,
    plan_measure_sweep,
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

from .commands import channel_display, measurement_analysis


def _plan_channel_analysis(
    args: argparse.Namespace, capabilities: ScopeCapabilities
) -> tuple[list[str], list[dict[str, str]], dict[str, object]] | None:
    command = args.command
    if command == "channel-summary":
        return ["*IDN?", *channel_summary_queries(capabilities)], [], {
            "channels": [],
        }

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
        "measure-menu",
        "measure-install",
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

    if command == "annotation":
        operation, commands, result = channel_display._annotation_plan(args, capabilities)
        result["operation"] = operation
        return commands + [":SYSTem:ERRor?"], [], result

    if command == "measure-stats":
        channel = validate_analog_channel(args.channel, capabilities)
        items = measurement_analysis._parse_stats_items(args.items)
        validate_measure_statistics_supported(capabilities)
        commands = measurement_analysis._measure_stats_planned_scpi(channel, items, args.mode, reset=args.reset, max_count=args.max_count)
        return commands + [":SYSTem:ERRor?"], [], {"channel": channel, "items": list(items), "mode": args.mode, "reset": bool(args.reset), "max_count": args.max_count, "settle_seconds": args.settle_seconds, "records": []}
    return None


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
