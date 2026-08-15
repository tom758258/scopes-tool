from __future__ import annotations

import argparse

from scopes_tool_core.advanced import (
    trigger_holdoff_commands,
    trigger_holdoff_query,
    validate_trigger_holdoff,
)
from scopes_tool_core.capabilities import ScopeCapabilities
from scopes_tool_core.channel import validate_analog_channel
from scopes_tool_core.errors import OscilloscopeError
import scopes_tool_core.search
from scopes_tool_core.search import (
    require_search_basic,
    search_count_query,
    search_event_command,
    search_event_query,
    search_mode_command,
    search_mode_query,
    search_state_command,
    search_state_query,
    serial_search_can_configure_commands,
    serial_search_can_query_commands,
    serial_search_i2c_configure_commands,
    serial_search_i2c_query_commands,
    serial_search_spi_configure_commands,
    serial_search_spi_query_commands,
    serial_search_uart_configure_commands,
    serial_search_uart_query_commands,
    validate_serial_search_bus,
)
from scopes_tool_core.serial import validate_serial_mode
from scopes_tool_core.trigger import (
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
    glitch_trigger_configure_commands,
    glitch_trigger_query_commands,
    normalize_edge_slope,
    or_trigger_configure_commands,
    or_trigger_query_commands,
    pattern_trigger_configure_commands,
    pattern_trigger_query_commands,
    runt_trigger_configure_commands,
    runt_trigger_high_level_query,
    runt_trigger_low_level_query,
    runt_trigger_query_commands,
    setup_hold_trigger_configure_commands,
    setup_hold_trigger_query_commands,
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
    trigger_high_level_query,
    trigger_low_level_query,
    trigger_mode_edge_command,
    trigger_noise_reject_command,
    trigger_noise_reject_query,
    trigger_sweep_command,
    trigger_sweep_query,
    tv_trigger_configure_commands,
    tv_trigger_query_commands,
    validate_external_trigger_probe_attenuation,
    validate_external_trigger_range,
    validate_external_trigger_units,
    validate_trigger_level,
)

from .. import preflight, runtime


def _cmd_serial_search(args: argparse.Namespace) -> int:
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

        protocol = args.command.removeprefix("serial-search-")
        if args.query:
            query_fn = getattr(scope, f"query_serial_search_{protocol}")
            state = query_fn(args.bus)
            cmds_fn = getattr(scopes_tool_core.search, f"serial_search_{protocol}_query_commands")
            commands = cmds_fn(args.bus)
            runtime._json_update_result(
                operation="query",
                protocol=protocol,
                commands=commands,
                **state.to_json(),
            )
            print(f"Serial search {protocol} bus {state.bus} selected: {state.selected}")
            for command in commands:
                print(f"Command: {command}")
        else:
            settings = preflight._canonical_serial_search_settings(args)
            config_fn = getattr(scope, f"configure_serial_search_{protocol}")
            state = config_fn(args.bus, **settings)
            cmds_fn = getattr(scopes_tool_core.search, f"serial_search_{protocol}_configure_commands")
            scpi_cmds = cmds_fn(args.bus, **settings)
            runtime._json_update_result(
                operation="configure",
                protocol=protocol,
                commands=scpi_cmds,
                state_changing=True,
                **state.to_json(),
            )
            print(f"Serial search {protocol} bus {state.bus} configured mode: {state.mode}")
            for command in scpi_cmds:
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _dry_run_serial_search_plan(
    args: argparse.Namespace, capabilities: ScopeCapabilities | None
) -> tuple[list[str], list[dict[str, str]], dict[str, object]]:
    if capabilities is not None:
        require_search_basic(capabilities)
        canonical_bus = validate_serial_search_bus(args.bus, capabilities)
    else:
        canonical_bus = args.bus
    protocol = args.command.removeprefix("serial-search-")
    if capabilities is not None:
        validate_serial_mode(protocol, capabilities)

    if args.query:
        query_builders = {
            "uart": serial_search_uart_query_commands,
            "i2c": serial_search_i2c_query_commands,
            "spi": serial_search_spi_query_commands,
            "can": serial_search_can_query_commands,
        }
        cmds = query_builders[protocol](canonical_bus)
        result = {
            "operation": "query",
            "protocol": protocol,
            "bus": canonical_bus,
            "commands": cmds,
        }
        return [*cmds, ":SYSTem:ERRor?"], [], result

    canonical_settings = preflight._canonical_serial_search_settings(args)

    configure_builders = {
        "uart": serial_search_uart_configure_commands,
        "i2c": serial_search_i2c_configure_commands,
        "spi": serial_search_spi_configure_commands,
        "can": serial_search_can_configure_commands,
    }
    scpi_cmds = configure_builders[protocol](canonical_bus, **canonical_settings)
    json_settings = dict(canonical_settings)
    if "id_val" in json_settings:
        json_settings["id"] = json_settings.pop("id_val")
    result = {
        "operation": "configure",
        "protocol": protocol,
        "bus": canonical_bus,
        "commands": scpi_cmds,
        "state_changing": True,
        **json_settings,
    }
    return [*scpi_cmds, ":SYSTem:ERRor?"], [], result



def _cmd_trigger_edge(args: argparse.Namespace) -> int:
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

        if args.edge_query:
            if any(value is not None for value in (args.source_channel, args.level, args.slope)):
                raise OscilloscopeError(
                    "--query cannot be combined with --source-channel, --level, or --slope"
                )
            print("Planned query: edge trigger source, level, and slope")
            state = scope.query_trigger_edge()
            runtime._json_update_result(
                operation="query",
                commands=[edge_trigger_source_query(), edge_trigger_level_query(), edge_trigger_slope_query()],
                source_channel=state.source_channel,
                level_volts=state.level_volts,
                slope=state.slope,
            )
            print(f"Command: {edge_trigger_source_query()}")
            print(f"Source: CH{state.source_channel}")
            print(f"Command: {edge_trigger_level_query()}")
            print(f"Level V: {state.level_volts:.12g}")
            print(f"Command: {edge_trigger_slope_query()}")
            print(f"Slope: {state.slope}")
        else:
            if args.source_channel is None or args.level is None or args.slope is None:
                raise OscilloscopeError(
                    "trigger-edge requires --source-channel, --level, and --slope unless --query is used"
                )
            channel = validate_analog_channel(args.source_channel, scope.capabilities)
            level = validate_trigger_level(args.level)
            slope = normalize_edge_slope(args.slope)
            print(
                f"Planned change: edge trigger CH{channel}, level {level:.12g} V, "
                f"slope {args.slope}"
            )
            scope.configure_trigger_edge(channel, level, slope)
            runtime._json_update_result(
                operation="set",
                commands=[trigger_mode_edge_command(), edge_trigger_source_command(channel), edge_trigger_level_command(level), edge_trigger_slope_command(slope)],
                source_channel=channel,
                level_volts=level,
                slope=slope,
            )
            print(f"Command: {trigger_mode_edge_command()}")
            print(f"Command: {edge_trigger_source_command(channel)}")
            print(f"Command: {edge_trigger_level_command(level)}")
            print(f"Command: {edge_trigger_slope_command(slope)}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_edge_source(args: argparse.Namespace) -> int:
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

        if args.trigger_edge_source_query:
            command = trigger_edge_source_query()
            print("Planned query: Edge Trigger source")
            state = scope.query_trigger_edge_source()
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Command: {command}")
            print(f"Source: {state.source or state.raw_source}")
            if state.source_channel is not None:
                print(f"Source channel: CH{state.source_channel}")
        else:
            if args.source_channel is not None:
                source = "analog-channel"
                source_channel = validate_analog_channel(
                    args.source_channel, scope.capabilities
                )
            else:
                source = args.source
                source_channel = None
            command = trigger_edge_source_command(
                source,
                source_channel=source_channel,
                capabilities=scope.capabilities,
            )
            print(f"Planned change: Edge Trigger source {source}")
            scope.configure_trigger_edge_source(
                source=source,
                source_channel=source_channel,
            )
            runtime._json_update_result(
                operation="set",
                command=command,
                source=source,
                source_channel=source_channel,
            )
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_edge_slope(args: argparse.Namespace) -> int:
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

        if args.trigger_edge_slope_query:
            command = edge_trigger_slope_query()
            print("Planned query: Edge Trigger slope")
            state = scope.query_trigger_edge_slope()
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Command: {command}")
            print(f"Slope: {state.slope or state.raw_slope}")
        else:
            slope = args.slope
            command = edge_trigger_slope_command(normalize_edge_slope(slope))
            print(f"Planned change: Edge Trigger slope {slope}")
            scope.configure_trigger_edge_slope(slope=slope)
            runtime._json_update_result(operation="set", command=command, slope=slope)
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_edge_level(args: argparse.Namespace) -> int:
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

        channel = validate_analog_channel(args.source_channel, scope.capabilities)
        if args.trigger_edge_level_query:
            command = edge_trigger_level_channel_query(channel)
            print(f"Planned query: Edge Trigger level for CH{channel}")
            state = scope.query_trigger_edge_level(source_channel=channel)
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Command: {command}")
            print(f"Level: {state.level_volts} V")
        else:
            level_volts = validate_trigger_level(args.level_volts)
            command = edge_trigger_level_channel_command(channel, level_volts)
            print(f"Planned change: Edge Trigger level for CH{channel}")
            scope.configure_trigger_edge_level(
                source_channel=channel,
                level_volts=level_volts,
            )
            runtime._json_update_result(
                operation="set",
                command=command,
                source_channel=channel,
                level_volts=level_volts,
            )
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_external_trigger_range(args: argparse.Namespace) -> int:
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

        if args.external_trigger_range_query:
            command = external_trigger_range_query()
            print("Planned query: External trigger range")
            state = scope.query_external_trigger_range()
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Command: {command}")
            print(f"External trigger range V: {state.range_volts}")
        else:
            range_volts = validate_external_trigger_range(args.range_volts)
            command = external_trigger_range_command(range_volts)
            print("Planned change: External trigger range")
            scope.configure_external_trigger_range(range_volts)
            runtime._json_update_result(
                operation="set",
                command=command,
                range_volts=range_volts,
            )
            print(f"Command: {command}")
            print(f"External trigger range V: {range_volts}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_edge_external_level(args: argparse.Namespace) -> int:
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

        if args.trigger_edge_external_level_query:
            command = edge_trigger_external_level_query()
            print("Planned query: External Edge Trigger level")
            state = scope.query_trigger_edge_external_level()
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Command: {command}")
            print(f"External Edge level V: {state.level_volts}")
        else:
            level_volts = validate_trigger_level(args.level_volts)
            command = edge_trigger_external_level_command(level_volts)
            print("Planned change: External Edge Trigger level")
            scope.configure_trigger_edge_external_level(level_volts=level_volts)
            runtime._json_update_result(
                operation="set",
                command=command,
                level_volts=level_volts,
            )
            print(f"Command: {command}")
            print(f"External Edge level V: {level_volts}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_external_trigger_input(args: argparse.Namespace) -> int:
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

        if args.command == "external-trigger-probe":
            if args.external_trigger_probe_query:
                command = external_trigger_probe_query()
                print("Planned query: External trigger probe attenuation")
                state = scope.query_external_trigger_probe()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"Command: {command}")
                print(f"External trigger probe attenuation: {state.attenuation}")
            else:
                attenuation = validate_external_trigger_probe_attenuation(args.attenuation)
                command = external_trigger_probe_command(attenuation)
                print("Planned change: External trigger probe attenuation")
                scope.configure_external_trigger_probe(attenuation)
                runtime._json_update_result(
                    operation="set", command=command, attenuation=attenuation
                )
                print(f"Command: {command}")
                print(f"External trigger probe attenuation: {attenuation}")
        elif args.command == "external-trigger-units":
            if args.external_trigger_units_query:
                command = external_trigger_units_query()
                print("Planned query: External trigger input units")
                state = scope.query_external_trigger_units()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"Command: {command}")
                print(f"External trigger units: {state.units}")
            else:
                units = validate_external_trigger_units(args.units)
                command = external_trigger_units_command(units)
                print("Planned change: External trigger input units")
                scope.configure_external_trigger_units(units)
                runtime._json_update_result(operation="set", command=command, units=units)
                print(f"Command: {command}")
                print(f"External trigger units: {units}")
        else:
            command = external_trigger_settings_query()
            print("Planned query: External trigger input settings")
            state = scope.query_external_trigger_settings()
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Command: {command}")
            print(f"External trigger probe attenuation: {state.probe_attenuation}")
            print(f"External trigger range: {state.range_value}")
            print(f"External trigger units: {state.units}")
            print(f"External trigger bandwidth limit enabled: {state.bandwidth_limit_enabled}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_search(args: argparse.Namespace) -> int:
    if args.command in {
        "serial-search-uart",
        "serial-search-i2c",
        "serial-search-spi",
        "serial-search-can",
    }:
        return _cmd_serial_search(args)
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

        if args.command == "search-state":
            if args.query:
                command = search_state_query()
                state = scope.query_search_state()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
            else:
                command = search_state_command(args.enabled)
                state = scope.configure_search_state(args.enabled)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    **state.to_json(),
                    state_changing=True,
                )
            print(f"Command: {command}")
            print(f"Search enabled: {state.enabled}")
        elif args.command == "search-mode":
            if args.query:
                command = search_mode_query()
                state = scope.query_search_mode()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"Command: {command}")
            else:
                state = scope.configure_search_mode(args.mode)
                commands = [search_state_command(True), search_mode_command(args.mode)]
                runtime._json_update_result(
                    operation="configure",
                    commands=commands,
                    **state.to_json(),
                    state_changing=True,
                )
                for command in commands:
                    print(f"Command: {command}")
            print(f"Search enabled: {state.enabled}")
            print(f"Search mode: {state.mode}")
        elif args.command == "search-event":
            if args.query:
                command = search_event_query()
                state = scope.query_search_event()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"Command: {command}")
                print(f"Search event: {state.event}")
            else:
                command = search_event_command(args.event)
                state = scope.configure_search_event(args.event)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    **state.to_json(),
                    state_changing=True,
                )
                print(f"Command: {command}")
                print(f"Search event set to {state.event}")
        else:
            command = search_count_query()
            state = scope.query_search_count()
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Command: {command}")
            print(f"Search count: {state.count}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_common(args: argparse.Namespace) -> int:
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

        if args.command == "trigger-sweep":
            if args.trigger_sweep_query:
                command = trigger_sweep_query()
                print("Planned query: trigger sweep mode")
                state = scope.query_trigger_sweep()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"Command: {command}")
                print(f"Mode: {state.mode}")
            else:
                command = trigger_sweep_command(args.mode)
                print(f"Planned change: trigger sweep {args.mode}")
                scope.configure_trigger_sweep(args.mode)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    mode=args.mode,
                    state_changing=True,
                )
                print(f"Command: {command}")
        elif args.command == "trigger-noise-reject":
            if args.trigger_noise_reject_query:
                command = trigger_noise_reject_query()
                print("Planned query: trigger noise reject")
                state = scope.query_trigger_noise_reject()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"Command: {command}")
                print(f"Enabled: {state.enabled}")
            else:
                command = trigger_noise_reject_command(args.enabled)
                print(f"Planned change: trigger noise reject {args.enabled}")
                scope.configure_trigger_noise_reject(args.enabled)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    enabled=args.enabled,
                    state_changing=True,
                )
                print(f"Command: {command}")
        elif args.command == "trigger-hf-reject":
            if args.trigger_hf_reject_query:
                command = trigger_hf_reject_query()
                print("Planned query: trigger high-frequency reject")
                state = scope.query_trigger_hf_reject()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"Command: {command}")
                print(f"Enabled: {state.enabled}")
            else:
                command = trigger_hf_reject_command(args.enabled)
                print(f"Planned change: trigger high-frequency reject {args.enabled}")
                scope.configure_trigger_hf_reject(args.enabled)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    enabled=args.enabled,
                    state_changing=True,
                )
                print(f"Command: {command}")

        elif args.command == "trigger-edge-coupling":
            if args.trigger_edge_coupling_query:
                command = trigger_edge_coupling_query()
                print("Planned query: Edge Trigger coupling")
                state = scope.query_trigger_edge_coupling()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"Command: {command}")
                print(f"Coupling: {state.coupling}")
            else:
                command = trigger_edge_coupling_command(args.coupling)
                print(f"Planned change: Edge Trigger coupling {args.coupling}")
                scope.configure_trigger_edge_coupling(args.coupling)
                runtime._json_update_result(
                    operation="set",
                    command=command,
                    coupling=args.coupling,
                )
                print(f"Command: {command}")

        elif args.command == "trigger-edge-reject":
            if args.trigger_edge_reject_query:
                command = trigger_edge_reject_query()
                print("Planned query: Edge Trigger reject")
                state = scope.query_trigger_edge_reject()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"Command: {command}")
                print(f"Reject: {state.reject}")
            else:
                command = trigger_edge_reject_command(args.reject)
                print(f"Planned change: Edge Trigger reject {args.reject}")
                scope.configure_trigger_edge_reject(args.reject)
                runtime._json_update_result(
                    operation="set",
                    command=command,
                    reject=args.reject,
                )
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_glitch(args: argparse.Namespace) -> int:
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

        if args.glitch_query:
            commands = glitch_trigger_query_commands()
            print("Planned query: pulse-width trigger state")
            state = scope.query_glitch_trigger()
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            print(f"Mode: {state.mode or state.raw['mode']}")
            print(f"Source: {state.source}")
            if state.channel is not None:
                print(f"Channel: CH{state.channel}")
            if state.digital is not None:
                print(f"Digital: D{state.digital}")
            print(f"Polarity: {state.polarity or state.raw['polarity']}")
            print(f"Qualifier: {state.qualifier or state.raw['qualifier']}")
            if state.level_volts is None:
                print(f"Level V: {state.raw['level']}")
            else:
                print(f"Level V: {state.level_volts:.12g}")
        else:
            commands = glitch_trigger_configure_commands(
                channel=args.channel,
                polarity=args.polarity,
                qualifier=args.qualifier,
                capabilities=scope.capabilities,
                time_seconds=args.time_seconds,
                min_time_seconds=args.min_time_seconds,
                max_time_seconds=args.max_time_seconds,
                level_volts=args.level_volts,
            )
            print(
                f"Planned change: pulse-width trigger CH{args.channel}, polarity {args.polarity}, "
                f"qualifier {args.qualifier}"
            )
            scope.configure_glitch_trigger(
                channel=args.channel,
                polarity=args.polarity,
                qualifier=args.qualifier,
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
            runtime._json_update_result(**result)
            for command in commands:
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_runt(args: argparse.Namespace) -> int:
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

        if args.runt_query:
            commands = runt_trigger_query_commands()
            print("Planned query: runt trigger state")
            state = scope.query_runt_trigger()
            commands = [command for command in commands if "<source>" not in command]
            if state.channel is not None:
                commands.extend(
                    [
                        runt_trigger_low_level_query(state.channel),
                        runt_trigger_high_level_query(state.channel),
                    ]
                )
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            print(f"Mode: {state.mode or state.raw['mode']}")
            print(f"Source: {state.source}")
            if state.channel is not None:
                print(f"Channel: CH{state.channel}")
            print(f"Polarity: {state.polarity or state.raw['polarity']}")
            print(f"Qualifier: {state.qualifier or state.raw['qualifier']}")
            if state.time_seconds is None:
                print(f"Time s: {state.raw['time']}")
            else:
                print(f"Time s: {state.time_seconds:.12g}")
            if state.low_level_volts is not None:
                print(f"Low level V: {state.low_level_volts:.12g}")
            if state.high_level_volts is not None:
                print(f"High level V: {state.high_level_volts:.12g}")
        else:
            commands = runt_trigger_configure_commands(
                channel=args.channel,
                polarity=args.polarity,
                qualifier=args.qualifier,
                capabilities=scope.capabilities,
                time_seconds=args.time_seconds,
                low_level_volts=args.low_level_volts,
                high_level_volts=args.high_level_volts,
            )
            print(
                f"Planned change: runt trigger CH{args.channel}, polarity {args.polarity}, "
                f"qualifier {args.qualifier}"
            )
            scope.configure_runt_trigger(
                channel=args.channel,
                polarity=args.polarity,
                qualifier=args.qualifier,
                time_seconds=args.time_seconds,
                low_level_volts=args.low_level_volts,
                high_level_volts=args.high_level_volts,
            )
            runtime._json_update_result(
                operation="set",
                commands=commands,
                channel=args.channel,
                source=f"CHANnel{args.channel}",
                polarity=args.polarity,
                qualifier=args.qualifier,
                time_seconds=args.time_seconds,
                low_level_volts=args.low_level_volts,
                high_level_volts=args.high_level_volts,
                state_changing=True,
            )
            for command in commands:
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_transition(args: argparse.Namespace) -> int:
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

        if args.transition_query:
            commands = transition_trigger_query_commands()
            print("Planned query: transition trigger state")
            state = scope.query_transition_trigger()
            if state.channel is not None:
                commands.extend(
                    [
                        trigger_low_level_query(state.channel),
                        trigger_high_level_query(state.channel),
                    ]
                )
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            print(f"Mode: {state.mode or state.raw['mode']}")
            print(f"Source: {state.source}")
            if state.channel is not None:
                print(f"Channel: CH{state.channel}")
            print(f"Slope: {state.slope or state.raw['slope']}")
            print(f"Qualifier: {state.qualifier or state.raw['qualifier']}")
            if state.time_seconds is None:
                print(f"Time s: {state.raw['time']}")
            else:
                print(f"Time s: {state.time_seconds:.12g}")
            if state.low_level_volts is not None:
                print(f"Low level V: {state.low_level_volts:.12g}")
            if state.high_level_volts is not None:
                print(f"High level V: {state.high_level_volts:.12g}")
        else:
            commands = transition_trigger_configure_commands(
                channel=args.channel,
                slope=args.slope,
                qualifier=args.qualifier,
                capabilities=scope.capabilities,
                time_seconds=args.time_seconds,
                low_level_volts=args.low_level_volts,
                high_level_volts=args.high_level_volts,
            )
            print(
                f"Planned change: transition trigger CH{args.channel}, slope {args.slope}, "
                f"qualifier {args.qualifier}"
            )
            scope.configure_transition_trigger(
                channel=args.channel,
                slope=args.slope,
                qualifier=args.qualifier,
                time_seconds=args.time_seconds,
                low_level_volts=args.low_level_volts,
                high_level_volts=args.high_level_volts,
            )
            runtime._json_update_result(
                operation="set",
                commands=commands,
                channel=args.channel,
                source=f"CHANnel{args.channel}",
                slope=args.slope,
                qualifier=args.qualifier,
                time_seconds=args.time_seconds,
                low_level_volts=args.low_level_volts,
                high_level_volts=args.high_level_volts,
                state_changing=True,
            )
            for command in commands:
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_delay(args: argparse.Namespace) -> int:
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

        if args.delay_query:
            commands = delay_trigger_query_commands()
            print("Planned query: delay trigger state")
            state = scope.query_delay_trigger()
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            print(f"Mode: {state.mode or state.raw['mode']}")
            print(f"Arm source: {state.arm_source}")
            if state.arm_channel is not None:
                print(f"Arm channel: CH{state.arm_channel}")
            if state.arm_digital is not None:
                print(f"Arm digital: D{state.arm_digital}")
            print(f"Arm slope: {state.arm_slope or state.raw['arm_slope']}")
            print(f"Trigger source: {state.trigger_source}")
            if state.trigger_channel is not None:
                print(f"Trigger channel: CH{state.trigger_channel}")
            if state.trigger_digital is not None:
                print(f"Trigger digital: D{state.trigger_digital}")
            print(f"Trigger slope: {state.trigger_slope or state.raw['trigger_slope']}")
            if state.time_seconds is None:
                print(f"Time s: {state.raw['time']}")
            else:
                print(f"Time s: {state.time_seconds:.12g}")
            if state.count is None:
                print(f"Count: {state.raw['count']}")
            else:
                print(f"Count: {state.count}")
        else:
            commands = delay_trigger_configure_commands(
                arm_channel=args.arm_channel,
                arm_slope=args.arm_slope,
                trigger_channel=args.trigger_channel,
                trigger_slope=args.trigger_slope,
                time_seconds=args.time_seconds,
                count=args.count,
                capabilities=scope.capabilities,
            )
            print(
                f"Planned change: delay trigger arm CH{args.arm_channel} {args.arm_slope}, "
                f"trigger CH{args.trigger_channel} {args.trigger_slope}"
            )
            scope.configure_delay_trigger(
                arm_channel=args.arm_channel,
                arm_slope=args.arm_slope,
                trigger_channel=args.trigger_channel,
                trigger_slope=args.trigger_slope,
                time_seconds=args.time_seconds,
                count=args.count,
            )
            runtime._json_update_result(
                operation="set",
                commands=commands,
                arm_channel=args.arm_channel,
                arm_source=f"CHANnel{args.arm_channel}",
                arm_slope=args.arm_slope,
                trigger_channel=args.trigger_channel,
                trigger_source=f"CHANnel{args.trigger_channel}",
                trigger_slope=args.trigger_slope,
                time_seconds=args.time_seconds,
                count=args.count,
                state_changing=True,
            )
            for command in commands:
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_setup_hold(args: argparse.Namespace) -> int:
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

        if args.setup_hold_query:
            commands = setup_hold_trigger_query_commands()
            print("Planned query: setup-hold trigger state")
            state = scope.query_setup_hold_trigger()
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            print(f"Mode: {state.mode or state.raw_mode}")
            print(f"Clock source: {state.clock_source}")
            if state.clock_channel is not None:
                print(f"Clock channel: CH{state.clock_channel}")
            if state.clock_digital is not None:
                print(f"Clock digital: D{state.clock_digital}")
            print(f"Data source: {state.data_source}")
            if state.data_channel is not None:
                print(f"Data channel: CH{state.data_channel}")
            if state.data_digital is not None:
                print(f"Data digital: D{state.data_digital}")
            print(f"Slope: {state.slope or state.raw['slope']}")
            if state.setup_time_seconds is None:
                print(f"Setup time s: {state.raw['setup_time']}")
            else:
                print(f"Setup time s: {state.setup_time_seconds:.12g}")
            if state.hold_time_seconds is None:
                print(f"Hold time s: {state.raw['hold_time']}")
            else:
                print(f"Hold time s: {state.hold_time_seconds:.12g}")
        else:
            commands = setup_hold_trigger_configure_commands(
                clock_channel=args.clock_channel,
                data_channel=args.data_channel,
                slope=args.slope,
                setup_time_seconds=args.setup_time,
                hold_time_seconds=args.hold_time,
                capabilities=scope.capabilities,
            )
            print(
                f"Planned change: setup-hold trigger clock CH{args.clock_channel}, "
                f"data CH{args.data_channel}, slope {args.slope}"
            )
            state = scope.configure_setup_hold_trigger(
                clock_channel=args.clock_channel,
                data_channel=args.data_channel,
                slope=args.slope,
                setup_time_seconds=args.setup_time,
                hold_time_seconds=args.hold_time,
            )
            runtime._json_update_result(
                operation="configure",
                commands=commands,
                mode=state.mode,
                clock_source=state.clock_source,
                clock_channel=state.clock_channel,
                clock_source_kind=state.clock_source_kind,
                data_source=state.data_source,
                data_channel=state.data_channel,
                data_source_kind=state.data_source_kind,
                slope=state.slope,
                setup_time_seconds=state.setup_time_seconds,
                hold_time_seconds=state.hold_time_seconds,
                raw=state.raw,
                state_changing=True,
            )
            for command in commands:
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_edge_burst(args: argparse.Namespace) -> int:
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

        if args.edge_burst_query:
            commands = edge_burst_trigger_query_commands()
            print("Planned query: Nth Edge Burst trigger state")
            state = scope.query_edge_burst_trigger()
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            if state.raw_level is not None:
                print(f"Command: :TRIGger:EDGE:LEVel? CHANnel{state.source_channel}")
            print(f"Mode: {state.mode or state.raw_mode}")
            print(f"Source: {state.raw_source}")
            if state.source_channel is not None:
                print(f"Source channel: CH{state.source_channel}")
            print(f"Slope: {state.slope or state.raw_slope}")
            print(f"Count: {state.count if state.count is not None else state.raw_count}")
            if state.idle_time is None:
                print(f"Idle time s: {state.raw_idle_time}")
            else:
                print(f"Idle time s: {state.idle_time:.12g}")
            if state.level_volts is not None:
                print(f"Level V: {state.level_volts:.12g}")
        else:
            commands = edge_burst_trigger_configure_commands(
                source_channel=args.source_channel,
                slope=args.slope,
                count=args.count,
                idle_time=args.idle_time,
                capabilities=scope.capabilities,
                level_volts=args.level_volts,
            )
            print(
                f"Planned change: Nth Edge Burst trigger CH{args.source_channel}, "
                f"{args.slope}, count {args.count}"
            )
            state = scope.configure_edge_burst_trigger(
                source_channel=args.source_channel,
                slope=args.slope,
                count=args.count,
                idle_time=args.idle_time,
                level_volts=args.level_volts,
            )
            result = state.to_json()
            result.update(
                {
                    "operation": "configure",
                    "commands": commands,
                    "source": state.raw_source,
                    "state_changing": True,
                }
            )
            runtime._json_update_result(**result)
            for command in commands:
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_tv(args: argparse.Namespace) -> int:
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

        if args.tv_query:
            commands = tv_trigger_query_commands()
            print("Planned query: TV trigger state")
            state = scope.query_tv_trigger()
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            print(f"Mode: {state.mode or 'unknown'}")
            print(f"Source: {state.source_raw}")
            if state.source_channel is not None:
                print(f"Source channel: CH{state.source_channel}")
            print(f"Standard: {state.standard or state.standard_raw}")
            print(f"TV mode: {state.tv_mode or state.tv_mode_raw}")
            print(f"Line: {state.line if state.line is not None else state.line_raw}")
            print(f"Polarity: {state.polarity or state.polarity_raw}")
        else:
            commands = tv_trigger_configure_commands(
                source_channel=args.source_channel,
                standard=args.standard,
                mode=args.mode,
                polarity=args.polarity,
                capabilities=scope.capabilities,
                line=args.line,
            )
            print(
                f"Planned change: TV trigger CH{args.source_channel}, "
                f"{args.standard}, {args.mode}, {args.polarity}"
            )
            state = scope.configure_tv_trigger(
                source_channel=args.source_channel,
                standard=args.standard,
                mode=args.mode,
                polarity=args.polarity,
                line=args.line,
            )
            result = state.to_json()
            result.update(
                {
                    "operation": "configure",
                    "commands": commands,
                    "state_changing": True,
                }
            )
            runtime._json_update_result(**result)
            for command in commands:
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_pattern(args: argparse.Namespace) -> int:
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

        if args.pattern_query:
            commands = pattern_trigger_query_commands()
            print("Planned query: pattern trigger state")
            state = scope.query_pattern_trigger()
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            print(f"Mode: {state.mode or state.raw['mode']}")
            print(f"Format: {state.format or state.raw['format']}")
            print(f"Pattern: {state.pattern if state.pattern is not None else state.raw['pattern']}")
            print(f"Qualifier: {state.qualifier or state.raw['qualifier']}")
            if state.edge_source_raw is not None:
                print(f"Edge source: {state.edge_source_raw}")
            if state.edge_raw is not None:
                print(f"Edge: {state.edge_raw}")
        else:
            commands = pattern_trigger_configure_commands(
                pattern=args.pattern,
                capabilities=scope.capabilities,
            )
            print(f"Planned change: pattern trigger {args.pattern.upper()}")
            state = scope.configure_pattern_trigger(args.pattern)
            runtime._json_update_result(
                operation="set",
                commands=commands,
                mode=state.mode,
                format=state.format,
                pattern=state.pattern,
                qualifier=state.qualifier,
                state_changing=True,
            )
            for command in commands:
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_or(args: argparse.Namespace) -> int:
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

        if args.or_query:
            commands = or_trigger_query_commands()
            print("Planned query: OR trigger state")
            state = scope.query_or_trigger()
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            print(f"Mode: {state.mode or state.raw_mode}")
            print(f"Pattern: {state.pattern if state.pattern is not None else state.raw_pattern}")
        else:
            commands = or_trigger_configure_commands(
                pattern=args.pattern,
                capabilities=scope.capabilities,
            )
            state = scope.configure_or_trigger(args.pattern)
            print(f"Planned change: OR trigger {state.pattern}")
            runtime._json_update_result(
                operation="set",
                commands=commands,
                mode=state.mode,
                pattern=state.pattern,
                raw_pattern=state.raw_pattern,
                state_changing=True,
            )
            for command in commands:
                print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0



def _cmd_trigger_holdoff(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        if args.holdoff_query:
            seconds = scope.query_trigger_holdoff()
            runtime._json_update_result(operation="query", command=trigger_holdoff_query(), seconds=seconds)
            print(f"Command: {trigger_holdoff_query()}")
            print(f"Holdoff seconds: {seconds:.12g}")
        else:
            seconds = validate_trigger_holdoff(args.holdoff_seconds)
            scope.set_trigger_holdoff(seconds)
            commands = trigger_holdoff_commands(seconds)
            runtime._json_update_result(operation="set", command=commands[-1], commands=commands, seconds=seconds)
            for command in commands:
                print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0

