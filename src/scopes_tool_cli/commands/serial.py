from __future__ import annotations

import argparse
from pathlib import Path

from .. import preflight, runtime
from scopes_tool_core.capabilities import ScopeCapabilities
from scopes_tool_core.output_files import write_serial_lister_csv
from scopes_tool_core.serial import (
    serial_bus_query,
    serial_can_configure_commands,
    serial_can_query_commands,
    serial_can_trigger_configure_commands,
    serial_can_trigger_data_length_query,
    serial_can_trigger_data_query,
    serial_can_trigger_id_mode_query,
    serial_can_trigger_id_query,
    serial_can_trigger_type_query,
    serial_display_command,
    serial_display_query,
    serial_i2c_configure_commands,
    serial_i2c_query_commands,
    serial_i2c_trigger_address_query,
    serial_i2c_trigger_configure_commands,
    serial_i2c_trigger_data2_query,
    serial_i2c_trigger_data_query,
    serial_i2c_trigger_qualifier_query,
    serial_i2c_trigger_type_query,
    serial_lister_data_query,
    serial_lister_display_command,
    serial_lister_display_query,
    serial_lister_query_commands,
    serial_lister_reference_command,
    serial_lister_reference_query,
    serial_mode_command,
    serial_mode_query,
    serial_spi_configure_commands,
    serial_spi_query_commands,
    serial_spi_trigger_configure_commands,
    serial_spi_trigger_data_query,
    serial_spi_trigger_type_query,
    serial_spi_trigger_width_query,
    serial_uart_configure_commands,
    serial_uart_query_commands,
    serial_uart_trigger_configure_commands,
    serial_uart_trigger_data_query,
    serial_uart_trigger_qualifier_query,
    serial_uart_trigger_type_query,
)
from scopes_tool_core.trigger import (
    trigger_mode_query,
    trigger_mode_serial_command,
)


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
            runtime._json_set_files([{"kind": "csv", "path": str(written_path)}])
            print(f"Command: {command}")
            print(f"Lister CSV: {written_path} ({len(payload)} bytes)")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0
