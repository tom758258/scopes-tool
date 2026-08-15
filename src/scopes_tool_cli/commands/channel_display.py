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
    channel_probe_skew_command,
    channel_probe_skew_query,
    channel_probe_ratio_command,
    channel_probe_ratio_query,
    channel_range_command,
    channel_range_query,
    channel_scale_command,
    channel_scale_query,
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
from scopes_tool_core.display import (
    annotation_commands,
    annotation_query_commands,
    display_clear_command,
    display_intensity_command,
    display_intensity_query,
    display_label_command,
    display_label_query,
    display_persistence_command,
    display_persistence_query,
    display_vectors_command,
    display_vectors_query,
    normalize_annotation_background,
    normalize_annotation_color,
    validate_annotation_slot,
    validate_display_intensity,
    validate_display_persistence,
)
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError
from scopes_tool_core.timebase import (
    timebase_position_command,
    timebase_position_query,
    timebase_scale_command,
    timebase_scale_query,
    validate_timebase_position,
    validate_timebase_scale,
)

from .. import runtime

def _annotation_plan(
    args: argparse.Namespace, capabilities: ScopeCapabilities
) -> tuple[str, list[str], dict[str, object]]:
    query_setters = (
        args.on,
        args.off,
        args.text is not None,
        args.clear,
        args.color is not None,
        args.background is not None,
        args.x is not None,
        args.y is not None,
    )
    if args.query and any(query_setters):
        raise OscilloscopeError(
            "--query cannot be combined with --on, --off, --text, --clear, --color, --background, --x, or --y"
        )
    if args.on and args.off:
        raise OscilloscopeError("--on and --off are mutually exclusive")
    if args.clear and args.text is not None:
        raise OscilloscopeError("--clear and --text are mutually exclusive")
    if not args.query and not any(query_setters):
        raise OscilloscopeError("annotation requires --query or at least one setter/action")
    slot = validate_annotation_slot(args.slot, capabilities)
    if args.query:
        commands = annotation_query_commands(slot=slot, capabilities=capabilities)
        return (
            "query",
            commands,
            {
                "commands": commands,
                "slot": slot,
                "enabled": None,
                "text": None,
                "color": None,
                "background": None,
                "x": None,
                "y": None,
            },
        )
    enabled = None
    if args.on:
        enabled = True
    elif args.off:
        enabled = False
    commands = annotation_commands(
        capabilities=capabilities,
        slot=slot,
        enabled=enabled,
        clear=args.clear,
        text=args.text,
        color=args.color,
        background=args.background,
        x=args.x,
        y=args.y,
    )
    return (
        "set",
        commands,
        {
            "commands": commands,
            "slot": slot,
            "enabled": enabled,
            "text": args.text,
            "clear": bool(args.clear),
            "color": None if args.color is None else normalize_annotation_color(args.color),
            "background": None if args.background is None else normalize_annotation_background(args.background),
            "x": args.x,
            "y": args.y,
        },
    )

def _display_common_plan(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    command = args.command
    if command == "display-clear":
        target = display_clear_command()
        return target, {"operation": command, "command": target}
    if command == "display-persistence":
        if args.query:
            target = display_persistence_query()
            return target, {
                "operation": command,
                "command": target,
                "mode": None,
                "seconds": None,
            }
        value = args.mode if args.mode is not None else args.seconds
        mode, seconds = validate_display_persistence(value)
        target = display_persistence_command(value)
        return target, {
            "operation": command,
            "command": target,
            "mode": mode,
            "seconds": seconds,
        }
    if command == "display-intensity":
        if args.query:
            target = display_intensity_query()
            return target, {"operation": command, "command": target, "value": None}
        value = validate_display_intensity(args.value)
        target = display_intensity_command(value)
        return target, {"operation": command, "command": target, "value": value}
    if command == "display-vectors":
        if args.query:
            target = display_vectors_query()
            return target, {"operation": command, "command": target, "value": None}
        target = display_vectors_command(True)
        return target, {"operation": command, "command": target, "value": True}
    raise ParameterValidationError(f"unsupported display command: {command}")

def _cmd_channel_display(args: argparse.Namespace) -> int:
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

        channel = validate_analog_channel(args.channel, scope.capabilities)
        if args.display_action == "query":
            command = channel_display_query(channel)
            print(f"Planned query: CH{channel} display state")
            enabled = scope.query_channel_display(channel)
            runtime._json_update_result(channel=channel, operation="query", command=command, display=enabled)
            print(f"Command: {command}")
            print(f"Display: {'ON' if enabled else 'OFF'}")
        else:
            enabled = args.display_action == "on"
            command = channel_display_command(channel, enabled)
            print(f"Planned change: CH{channel} display {'ON' if enabled else 'OFF'}")
            scope.set_channel_display(channel, enabled)
            runtime._json_update_result(channel=channel, operation="set", command=command, display=enabled)
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _cmd_channel_summary(args: argparse.Namespace) -> int:
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

        channels = [entry.to_json() for entry in scope.query_channel_summary()]
        runtime._json_update_result(channels=channels)
        for channel in channels:
            print(
                f"CH{channel['channel']}: "
                f"display={_format_summary_bool(channel['display'])}, "
                f"label={channel['label'] or '-'}, "
                f"scale={_format_summary_value(channel['scale'])}, "
                f"offset={_format_summary_value(channel['offset'])}, "
                f"coupling={channel['coupling'] or '-'}, "
                f"impedance={channel['impedance'] or '-'}, "
                f"bandwidth_limit={_format_summary_bool(channel['bandwidth_limit'])}, "
                f"probe_ratio={_format_summary_value(channel['probe_ratio'])}, "
                f"probe_skew={_format_summary_value(channel['probe_skew'])}"
            )
        return 0

def _format_summary_bool(value: object) -> str:
    if value is None:
        return "-"
    return "on" if value is True else "off"

def _format_summary_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)

def _cmd_channel_label(args: argparse.Namespace) -> int:
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

        channel = validate_analog_channel(args.channel, scope.capabilities)
        if args.label_query:
            command = channel_label_query(channel)
            print(f"Planned query: CH{channel} label")
            text = scope.query_channel_label(channel)
            runtime._json_update_result(channel=channel, operation="query", command=command, text=text)
            print(f"Command: {command}")
            print(f"Label: {text}")
        else:
            text = validate_channel_label(args.label_text, scope.capabilities)
            command = channel_label_command(channel, text, scope.capabilities)
            print(f"Planned change: CH{channel} label")
            scope.set_channel_label(channel, text)
            runtime._json_update_result(channel=channel, operation="set", command=command, text=text)
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _cmd_channel_scale(args: argparse.Namespace) -> int:
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

        channel = validate_analog_channel(args.channel, scope.capabilities)
        if args.scale_query:
            command = channel_scale_query(channel)
            print(f"Planned query: CH{channel} scale")
            scale = scope.query_channel_scale(channel)
            runtime._json_update_result(channel=channel, operation="query", command=command, volts_per_division=scale)
            print(f"Command: {command}")
            print(f"Scale V/div: {scale:.12g}")
        else:
            scale = validate_channel_scale(args.scale_value)
            command = channel_scale_command(channel, scale)
            print(f"Planned change: CH{channel} scale {scale:.12g} V/div")
            scope.set_channel_scale(channel, scale)
            runtime._json_update_result(channel=channel, operation="set", command=command, volts_per_division=scale)
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _cmd_channel_offset(args: argparse.Namespace) -> int:
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

        channel = validate_analog_channel(args.channel, scope.capabilities)
        if args.offset_query:
            command = channel_offset_query(channel)
            print(f"Planned query: CH{channel} offset")
            offset = scope.query_channel_offset(channel)
            runtime._json_update_result(channel=channel, operation="query", command=command, volts=offset)
            print(f"Command: {command}")
            print(f"Offset V: {offset:.12g}")
        else:
            offset = validate_channel_offset(args.offset_value)
            command = channel_offset_command(channel, offset)
            print(f"Planned change: CH{channel} offset {offset:.12g} V")
            scope.set_channel_offset(channel, offset)
            runtime._json_update_result(channel=channel, operation="set", command=command, volts=offset)
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _cmd_channel_coupling(args: argparse.Namespace) -> int:
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

        channel = validate_analog_channel(args.channel, scope.capabilities)
        if args.coupling_query:
            command = channel_coupling_query(channel)
            print(f"Planned query: CH{channel} coupling")
            coupling = scope.query_channel_coupling(channel)
            runtime._json_update_result(channel=channel, operation="query", command=command, coupling=coupling)
            print(f"Command: {command}")
            print(f"Coupling: {coupling.upper()}")
        else:
            coupling = normalize_channel_coupling(args.coupling_value)
            command = channel_coupling_command(channel, coupling)
            print(f"Planned change: CH{channel} coupling {coupling.upper()}")
            scope.set_channel_coupling(channel, coupling)
            runtime._json_update_result(channel=channel, operation="set", command=command, coupling=coupling)
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _cmd_channel_probe(args: argparse.Namespace) -> int:
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

        channel = validate_analog_channel(args.channel, scope.capabilities)
        if args.probe_query:
            command = channel_probe_ratio_query(channel)
            print(f"Planned query: CH{channel} probe ratio")
            ratio = scope.query_channel_probe_ratio(channel)
            runtime._json_update_result(channel=channel, operation="query", command=command, probe_ratio=ratio)
            print(f"Command: {command}")
            print(f"Probe ratio: {ratio:.12g}")
        else:
            ratio = validate_probe_ratio(args.probe_ratio)
            command = channel_probe_ratio_command(channel, ratio)
            print(f"Planned change: CH{channel} probe ratio {ratio:.12g}")
            scope.set_channel_probe_ratio(channel, ratio)
            runtime._json_update_result(channel=channel, operation="set", command=command, probe_ratio=ratio)
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _cmd_channel_bandwidth_limit(args: argparse.Namespace) -> int:
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

        channel = validate_analog_channel(args.channel, scope.capabilities)
        if args.bandwidth_action == "query":
            command = channel_bandwidth_limit_query(channel)
            print(f"Planned query: CH{channel} bandwidth limit")
            enabled = scope.query_channel_bandwidth_limit(channel)
            runtime._json_update_result(channel=channel, operation="query", command=command, bandwidth_limit=enabled)
            print(f"Command: {command}")
            print(f"Bandwidth limit: {'ON' if enabled else 'OFF'}")
        else:
            enabled = args.bandwidth_action == "on"
            command = channel_bandwidth_limit_command(channel, enabled)
            state = "ON" if enabled else "OFF"
            print(f"Planned change: CH{channel} bandwidth limit {state}")
            scope.set_channel_bandwidth_limit(channel, enabled)
            runtime._json_update_result(channel=channel, operation="set", command=command, bandwidth_limit=enabled)
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _cmd_channel_advanced_setting(args: argparse.Namespace) -> int:
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

        channel = validate_analog_channel(args.channel, scope.capabilities)
        command = args.command

        if command == "channel-impedance":
            if args.impedance_query:
                scpi = channel_impedance_query(channel)
                print(f"Planned query: CH{channel} impedance")
                impedance = scope.query_channel_impedance(channel)
                runtime._json_update_result(channel=channel, operation="query", command=scpi, impedance=impedance)
                print(f"Command: {scpi}")
                print(f"Impedance: {_format_channel_impedance(impedance)}")
            else:
                impedance = normalize_channel_impedance(args.impedance_value)
                validate_channel_impedance_supported(impedance, scope.capabilities)
                scpi = channel_impedance_command(channel, impedance)
                print(f"Planned change: CH{channel} impedance {_format_channel_impedance(impedance)}")
                scope.set_channel_impedance(channel, impedance)
                runtime._json_update_result(channel=channel, operation="set", command=scpi, impedance=impedance)
                print(f"Command: {scpi}")
        elif command == "channel-invert":
            if args.invert_action == "query":
                scpi = channel_invert_query(channel)
                print(f"Planned query: CH{channel} invert")
                enabled = scope.query_channel_invert(channel)
                runtime._json_update_result(channel=channel, operation="query", command=scpi, invert=enabled)
                print(f"Command: {scpi}")
                print(f"Invert: {'ON' if enabled else 'OFF'}")
            else:
                enabled = args.invert_action == "on"
                scpi = channel_invert_command(channel, enabled)
                print(f"Planned change: CH{channel} invert {'ON' if enabled else 'OFF'}")
                scope.set_channel_invert(channel, enabled)
                runtime._json_update_result(channel=channel, operation="set", command=scpi, invert=enabled)
                print(f"Command: {scpi}")
        elif command == "channel-range":
            if args.range_query:
                scpi = channel_range_query(channel)
                print(f"Planned query: CH{channel} range")
                range_volts = scope.query_channel_range(channel)
                runtime._json_update_result(channel=channel, operation="query", command=scpi, range_volts=range_volts)
                print(f"Command: {scpi}")
                print(f"Range V: {range_volts:.12g}")
            else:
                range_volts = validate_channel_range(args.range_value)
                scpi = channel_range_command(channel, range_volts)
                print(f"Planned change: CH{channel} range {range_volts:.12g} V")
                scope.set_channel_range(channel, range_volts)
                runtime._json_update_result(channel=channel, operation="set", command=scpi, range_volts=range_volts)
                print(f"Command: {scpi}")
        elif command == "channel-units":
            if args.units_query:
                scpi = channel_units_query(channel)
                print(f"Planned query: CH{channel} units")
                units = scope.query_channel_units(channel)
                runtime._json_update_result(channel=channel, operation="query", command=scpi, units=units)
                print(f"Command: {scpi}")
                print(f"Units: {units}")
            else:
                units = normalize_channel_units(args.units_value)
                scpi = channel_units_command(channel, units)
                print(f"Planned change: CH{channel} units {units}")
                scope.set_channel_units(channel, units)
                runtime._json_update_result(channel=channel, operation="set", command=scpi, units=units)
                print(f"Command: {scpi}")
        elif command == "channel-vernier":
            if args.vernier_action == "query":
                scpi = channel_vernier_query(channel)
                print(f"Planned query: CH{channel} vernier")
                enabled = scope.query_channel_vernier(channel)
                runtime._json_update_result(channel=channel, operation="query", command=scpi, vernier=enabled)
                print(f"Command: {scpi}")
                print(f"Vernier: {'ON' if enabled else 'OFF'}")
            else:
                enabled = args.vernier_action == "on"
                scpi = channel_vernier_command(channel, enabled)
                print(f"Planned change: CH{channel} vernier {'ON' if enabled else 'OFF'}")
                scope.set_channel_vernier(channel, enabled)
                runtime._json_update_result(channel=channel, operation="set", command=scpi, vernier=enabled)
                print(f"Command: {scpi}")
        elif command == "channel-probe-skew":
            if args.probe_skew_query:
                scpi = channel_probe_skew_query(channel)
                print(f"Planned query: CH{channel} probe skew")
                skew = scope.query_channel_probe_skew(channel)
                runtime._json_update_result(channel=channel, operation="query", command=scpi, probe_skew_seconds=skew)
                print(f"Command: {scpi}")
                print(f"Probe skew s: {skew:.12g}")
            else:
                skew = validate_probe_skew(args.probe_skew_seconds)
                scpi = channel_probe_skew_command(channel, skew)
                print(f"Planned change: CH{channel} probe skew {skew:.12g} s")
                scope.set_channel_probe_skew(channel, skew)
                runtime._json_update_result(channel=channel, operation="set", command=scpi, probe_skew_seconds=skew)
                print(f"Command: {scpi}")
        else:
            raise ParameterValidationError(f"unsupported channel command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _format_channel_impedance(impedance: str) -> str:
    return "one-meg" if impedance == "one_meg" else "fifty"

def _cmd_display_label(args: argparse.Namespace) -> int:
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

        if args.display_label_action == "query":
            command = display_label_query()
            print("Planned query: display labels")
            enabled = scope.query_display_label()
            runtime._json_update_result(operation="query", command=command, display_label=enabled)
            print(f"Command: {command}")
            print(f"Display labels: {'ON' if enabled else 'OFF'}")
        else:
            enabled = args.display_label_action == "on"
            command = display_label_command(enabled)
            print(f"Planned change: display labels {'ON' if enabled else 'OFF'}")
            scope.set_display_label(enabled)
            runtime._json_update_result(operation="set", command=command, display_label=enabled)
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _cmd_display_common(args: argparse.Namespace) -> int:
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

        target, result = _display_common_plan(args)
        if args.command == "display-clear":
            print("Planned change: clear display")
            scope.clear_display()
            runtime._json_update_result(**result)
            print(f"Command: {target}")
            print("Display cleared")
        elif args.command == "display-persistence":
            if args.query:
                print("Planned query: display persistence")
                state = scope.query_display_persistence()
                runtime._json_update_result(
                    operation=args.command,
                    command=target,
                    mode=state.mode,
                    seconds=state.seconds,
                    raw_value=state.raw_value,
                )
                print(f"Command: {target}")
                print(f"Persistence: {_format_display_persistence(state.mode, state.seconds)}")
            else:
                print("Planned change: display persistence")
                value = args.mode if args.mode is not None else args.seconds
                scope.set_display_persistence(value)
                runtime._json_update_result(**result)
                print(f"Command: {target}")
        elif args.command == "display-intensity":
            if args.query:
                print("Planned query: display intensity")
                value, raw = scope.query_display_intensity()
                runtime._json_update_result(
                    operation=args.command,
                    command=target,
                    value=value,
                    raw_value=raw,
                )
                print(f"Command: {target}")
                print(f"Intensity: {value}")
            else:
                print(f"Planned change: display intensity {args.value}")
                scope.set_display_intensity(args.value)
                runtime._json_update_result(**result)
                print(f"Command: {target}")
        elif args.command == "display-vectors":
            if args.query:
                print("Planned query: display vectors")
                value, raw = scope.query_display_vectors()
                runtime._json_update_result(
                    operation=args.command,
                    command=target,
                    value=value,
                    raw_value=raw,
                )
                print(f"Command: {target}")
                print(f"Vectors: {'ON' if value else 'OFF'}")
            else:
                print("Planned change: display vectors ON")
                scope.set_display_vectors_on()
                runtime._json_update_result(**result)
                print(f"Command: {target}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _format_display_persistence(mode: str | None, seconds: float | None) -> str:
    if seconds is not None:
        return f"{seconds:.12g} s"
    return mode or "unknown"

def _cmd_annotation(args: argparse.Namespace) -> int:
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

        operation, commands, result = _annotation_plan(args, scope.capabilities)
        if operation == "query":
            print(f"Planned query: annotation slot {args.slot}")
            state = scope.query_annotation(slot=args.slot)
            runtime._json_update_result(
                operation="query",
                commands=commands,
                slot=state.slot,
                enabled=state.enabled,
                text=state.text,
                color=state.color,
                background=state.background,
                x=state.x,
                y=state.y,
            )
            for command in commands:
                print(f"Command: {command}")
            print(f"Annotation: {'ON' if state.enabled else 'OFF'}")
            print(f"Text: {state.text}")
            print(f"Color: {state.color}")
            print(f"Background: {state.background}")
            if state.x is not None and state.y is not None:
                print(f"Position: {state.x},{state.y}")
        else:
            print(f"Planned change: annotation slot {args.slot}")
            if args.clear:
                scope.clear_annotation(slot=args.slot)
            if args.text is not None:
                scope.set_annotation_text(args.text, slot=args.slot)
            if args.color is not None:
                scope.set_annotation_color(args.color, slot=args.slot)
            if args.background is not None:
                scope.set_annotation_background(args.background, slot=args.slot)
            if args.x is not None or args.y is not None:
                scope.set_annotation_position(args.x, args.y, slot=args.slot)
            if args.on:
                scope.set_annotation_enabled(True, slot=args.slot)
            if args.off:
                scope.set_annotation_enabled(False, slot=args.slot)
            runtime._json_update_result(operation="set", **result)
            for command in commands:
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _cmd_timebase_scale(args: argparse.Namespace) -> int:
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

        if args.timebase_scale_query:
            command = timebase_scale_query()
            print("Planned query: timebase scale")
            scale = scope.query_timebase_scale()
            runtime._json_update_result(operation="query", command=command, seconds_per_division=scale)
            print(f"Command: {command}")
            print(f"Timebase scale s/div: {scale:.12g}")
        else:
            scale = validate_timebase_scale(args.timebase_scale_value)
            command = timebase_scale_command(scale)
            print(f"Planned change: timebase scale {scale:.12g} s/div")
            scope.set_timebase_scale(scale)
            runtime._json_update_result(operation="set", command=command, seconds_per_division=scale)
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

def _cmd_timebase_position(args: argparse.Namespace) -> int:
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

        if args.timebase_position_query:
            command = timebase_position_query()
            print("Planned query: timebase position")
            position = scope.query_timebase_position()
            runtime._json_update_result(operation="query", command=command, position_seconds=position)
            print(f"Command: {command}")
            print(f"Timebase position s: {position:.12g}")
        else:
            position = validate_timebase_position(args.timebase_position_value)
            command = timebase_position_command(position)
            print(f"Planned change: timebase position {position:.12g} s")
            scope.set_timebase_position(position)
            runtime._json_update_result(operation="set", command=command, position_seconds=position)
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

