"""CLI dry-run planning for serial decode, serial trigger, and waveform search commands."""

from __future__ import annotations

import argparse

from scopes_tool_core.capabilities import ScopeCapabilities
from scopes_tool_core.errors import ParameterValidationError
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
    serial_display_command,
    serial_display_query,
    serial_lister_data_query,
    serial_lister_display_command,
    serial_lister_display_query,
    serial_lister_query_commands,
    serial_lister_reference_command,
    serial_lister_reference_query,
    serial_mode_command,
    serial_mode_query,
    validate_serial_can_trigger_request,
    validate_serial_i2c_trigger_request,
    validate_serial_lister_display,
    validate_serial_lister_reference,
    validate_serial_mode,
    validate_serial_spi_trigger_request,
    validate_serial_uart_trigger_request,
)
from scopes_tool_core.trigger import trigger_mode_query

from . import preflight
from . import _preflight_serial as preflight_serial_module
from .commands import serial, trigger_search


def _plan_serial_search(
    args: argparse.Namespace, capabilities: ScopeCapabilities
) -> tuple[list[str], list[dict[str, str]], dict[str, object]] | None:
    command = args.command
    if command == "serial-status":
        commands = [serial_mode_query(args.bus), serial_display_query(args.bus)]
        return [*commands, ":SYSTem:ERRor?"], [], {
            "operation": "status",
            "commands": commands,
            "bus": args.bus,
            "mode": None,
            "raw_mode": None,
            "display": None,
            "protocol": None,
            "config": None,
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
    if command in {"serial-enable", "serial-disable"}:
        enabled = command == "serial-enable"
        target = serial_display_command(args.bus, enabled)
        return [target, ":SYSTem:ERRor?"], [], {
            "operation": "configure",
            "command": target,
            "bus": args.bus,
            "enabled": enabled,
            "state_changing": True,
        }
    if command == "serial-lister-status":
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
    if command == "serial-data":
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
    if command in {"serial-trigger-uart-set", "serial-trigger-uart-show"}:
        query = command.endswith("-show")
        bus, trigger_type, data, qualifier = validate_serial_uart_trigger_request(
            args.bus,
            query=query,
            type=None if query else args.type,
            data=None if query else args.data,
            qualifier=None if query else args.qualifier,
            capabilities=capabilities,
        )
        if query:
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
    if command in {"serial-trigger-i2c-set", "serial-trigger-i2c-show"}:
        query = command.endswith("-show")
        bus, trigger_type, address, data, data2, qualifier = validate_serial_i2c_trigger_request(
            args.bus, query=query, type=None if query else args.type, address=None if query else args.address,
            data=None if query else args.data, data2=None if query else args.data2, qualifier=None if query else args.qualifier,
            capabilities=capabilities,
        )
        if query:
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
    if command in {"serial-trigger-spi-set", "serial-trigger-spi-show"}:
        query = command.endswith("-show")
        bus, trigger_type, width, data = validate_serial_spi_trigger_request(
            args.bus, query=query, type=None if query else args.type, width=None if query else args.width, data=None if query else args.data,
            capabilities=capabilities,
        )
        if query:
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
    if command in {"serial-trigger-can-set", "serial-trigger-can-show"}:
        query = command.endswith("-show")
        bus, trigger_type, id_value, id_mode, data, data_length = validate_serial_can_trigger_request(
            args.bus, query=query, type=None if query else args.type, id=None if query else args.id, id_mode=None if query else args.id_mode,
            data=None if query else args.data, data_length=None if query else args.data_length, capabilities=capabilities,
        )
        if query:
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
    if command in {"serial-uart-set", "serial-uart-show", "serial-i2c-set", "serial-i2c-show", "serial-spi-set", "serial-spi-show", "serial-can-set", "serial-can-show"}:
        query = command.endswith("-show")
        commands = serial._serial_protocol_commands(args, capabilities)
        result = {
            "operation": "query" if query else "configure",
            "commands": commands,
            "bus": args.bus,
        }
        if not query:
            result.update(
                preflight_serial_module._serial_cli_values(
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
    return None
