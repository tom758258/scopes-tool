"""CLI dry-run planning for timebase, trigger, cursor, and trigger wait commands."""

from __future__ import annotations

import argparse

from scopes_tool_core.capabilities import ScopeCapabilities
from scopes_tool_core.channel import validate_analog_channel
from scopes_tool_core.cursor import (
    cursor_auto_timebase_dry_run_plan,
    cursor_auto_timebase_json,
    cursor_auto_vertical_dry_run_plan,
    cursor_auto_vertical_json,
    cursor_configure_commands,
    cursor_query_commands,
)
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.timebase import (
    timebase_position_command,
    timebase_position_query,
    timebase_reference_command,
    timebase_reference_query,
    timebase_scale_command,
    timebase_scale_query,
    validate_timebase_position,
    validate_timebase_reference,
    validate_timebase_scale,
)
from scopes_tool_core.trigger import (
    TriggerWaitConfig,
    TriggerWaitResult,
    delay_trigger_configure_commands,
    delay_trigger_query_commands,
    edge_burst_trigger_configure_commands,
    edge_burst_trigger_query_commands,
    edge_trigger_external_level_command,
    edge_trigger_external_level_query,
    edge_trigger_level_channel_command,
    edge_trigger_level_channel_query,
    edge_trigger_level_command,
    edge_trigger_level_query,
    edge_trigger_slope_command,
    edge_trigger_slope_query,
    edge_trigger_source_command,
    edge_trigger_source_query,
    external_trigger_probe_command,
    external_trigger_probe_query,
    external_trigger_range_command,
    external_trigger_range_query,
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
    trigger_edge_coupling_command,
    trigger_edge_coupling_query,
    trigger_edge_reject_command,
    trigger_edge_reject_query,
    trigger_edge_source_command,
    trigger_edge_source_query,
    trigger_hf_reject_command,
    trigger_hf_reject_query,
    trigger_mode_command,
    trigger_mode_edge_command,
    trigger_mode_query,
    trigger_noise_reject_command,
    trigger_noise_reject_query,
    trigger_sweep_command,
    trigger_sweep_query,
    tv_trigger_configure_commands,
    tv_trigger_query_commands,
    validate_external_trigger_probe_attenuation,
    validate_external_trigger_range,
    validate_external_trigger_units,
    validate_or_trigger_pattern,
    validate_pattern_trigger_pattern,
    validate_trigger_level,
)
from scopes_tool_core.trigger_holdoff import (
    trigger_holdoff_commands,
    trigger_holdoff_query,
    validate_trigger_holdoff,
)


def _plan_trigger(
    args: argparse.Namespace, capabilities: ScopeCapabilities
) -> tuple[list[str], list[dict[str, str]], dict[str, object]] | None:
    command = args.command
    if command == "single-wait":
        config = TriggerWaitConfig(
            timeout_ms=args.trigger_timeout_ms,
            poll_interval_ms=args.trigger_poll_interval_ms,
            force_on_timeout=args.force_trigger_on_timeout,
        )
        planned = ["*IDN?", single_command(), operation_condition_query()]
        if config.force_on_timeout:
            planned.extend([force_trigger_command(), operation_condition_query()])
        planned.append(":SYSTem:ERRor?")
        result = TriggerWaitResult(
            outcome="unknown",
            forced=False,
            timed_out=False,
            poll_count=0,
            elapsed_ms=0.0,
            capture_block_reason="dry_run",
        ).to_json(config)
        return planned, [], {"operation": "single-wait", **result}

    if command == "timebase-scale":
        scale = None if args.timebase_scale_query else validate_timebase_scale(args.timebase_scale_value)
        planned = [timebase_scale_query()] if args.timebase_scale_query else [timebase_scale_command(scale)]
        return planned + [":SYSTem:ERRor?"], [], {"operation": "query" if args.timebase_scale_query else "set", "command": planned[0], "seconds_per_division": scale}
    if command == "timebase-position":
        position = None if args.timebase_position_query else validate_timebase_position(args.timebase_position_value)
        planned = [timebase_position_query()] if args.timebase_position_query else [timebase_position_command(position)]
        return planned + [":SYSTem:ERRor?"], [], {"operation": "query" if args.timebase_position_query else "set", "command": planned[0], "position_seconds": position}
    if command == "timebase-reference":
        reference = None if args.timebase_reference_query else validate_timebase_reference(args.timebase_reference_value)
        planned = [timebase_reference_query()] if args.timebase_reference_query else [timebase_reference_command(reference)]
        return planned + [":SYSTem:ERRor?"], [], {"operation": "query" if args.timebase_reference_query else "set", "command": planned[0], "reference": reference}

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
    if command == "trigger-mode":
        if args.query:
            command_text = trigger_mode_query()
            return [command_text, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "command": command_text,
            }
        command_text = trigger_mode_command(args.mode)
        return [command_text, ":SYSTem:ERRor?"], [], {
            "operation": "configure",
            "command": command_text,
            "mode": args.mode,
            "state_changing": True,
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
            commands = cursor_query_commands(capabilities)
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        if args.cursor_off:
            return [":MARKer:MODE OFF", ":SYSTem:ERRor?"], [], {"operation": "off", "command": ":MARKer:MODE OFF"}
        channel = validate_analog_channel(args.source_channel, capabilities)
        commands = cursor_configure_commands(
            channel,
            x1_seconds=args.x1,
            x2_seconds=args.x2,
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

    if command == "force-trigger":
        planned = ["*IDN?", force_trigger_command(), ":SYSTem:ERRor?"]
        return planned, [], {
            "operation": "force-trigger",
            "scpi_command": force_trigger_command(),
            "planned_scpi": list(planned),
            "state_changing": True,
        }
    return None
