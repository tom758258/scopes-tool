"""Worker argument normalization for Serial and Search commands."""

from __future__ import annotations

import argparse
from typing import Any

from scopes_tool_core.capabilities import ScopeCapabilities, capabilities_for_model_id
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError
from scopes_tool_core.search import (
    validate_can_data_length,
    validate_can_id_mode,
    validate_can_search_criteria,
    validate_can_search_mode,
    validate_i2c_pattern_value,
    validate_i2c_search_mode,
    validate_pattern_hex_x,
    validate_search_qualifier,
    validate_serial_search_bus,
    validate_spi_search_mode,
    validate_spi_search_pattern_width,
    validate_spi_width,
    validate_uart_data,
    validate_uart_search_mode,
)
from scopes_tool_core.serial import (
    validate_serial_can_trigger_request,
    validate_serial_i2c_trigger_request,
    validate_serial_spi_trigger_request,
    validate_serial_uart_trigger_request,
)


def _normalize_serial_search_worker_arguments(
    command: str, arguments: dict[str, Any], runtime: WorkerRuntime
) -> dict[str, Any]:
    if command not in {
        "serial-search-uart",
        "serial-search-i2c",
        "serial-search-spi",
        "serial-search-can",
    }:
        return arguments

    capabilities = capabilities_for_model_id(runtime.model)
    if not capabilities.supports_search_basic:
        raise OscilloscopeError(
            f"Search is not supported by the selected "
            f"{capabilities.series} model profile."
        )

    protocol = command.removeprefix("serial-search-")
    if protocol not in capabilities.serial_modes:
        raise OscilloscopeError(
            f"Serial mode {protocol!r} is not supported by the selected "
            f"{capabilities.series} model profile."
        )

    if "bus" not in arguments:
        raise OscilloscopeError(f"{command} requires bus")
    bus = arguments["bus"]
    if isinstance(bus, bool) or not isinstance(bus, int):
        raise OscilloscopeError(f"{command} argument bus must be an integer")
    try:
        validate_serial_search_bus(bus, capabilities)
    except ParameterValidationError as exc:
        raise OscilloscopeError(str(exc)) from exc

    allowed_by_cmd = {
        "serial-search-uart": {"bus", "query", "mode", "data", "qualifier"},
        "serial-search-i2c": {"bus", "query", "mode", "address", "data", "data2", "qualifier"},
        "serial-search-spi": {"bus", "query", "mode", "data", "width"},
        "serial-search-can": {"bus", "query", "mode", "data", "data_length", "id", "id_mode"},
    }
    allowed = allowed_by_cmd[command]
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for {command}: {sorted(unknown)[0]}"
        )

    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                f"{command} argument query must be strictly boolean True"
            )
        if len(set(arguments) - {"bus", "query"}) > 0:
            raise OscilloscopeError(
                f"{command} query cannot be combined with configure options"
            )
        return dict(arguments)

    if "mode" not in arguments:
        raise OscilloscopeError(f"{command} configure requires mode")

    mode = arguments["mode"]
    if not isinstance(mode, str):
        raise OscilloscopeError(f"{command} argument mode must be a string")

    try:
        if protocol == "uart":
            validate_uart_search_mode(mode)
            if "data" in arguments:
                data = arguments["data"]
                if isinstance(data, bool) or not isinstance(data, int):
                    raise OscilloscopeError(f"{command} argument data must be an integer")
                validate_uart_data(data)
            if "qualifier" in arguments:
                q = arguments["qualifier"]
                if not isinstance(q, str):
                    raise OscilloscopeError(f"{command} argument qualifier must be a string")
                validate_search_qualifier(q)
        elif protocol == "i2c":
            validate_i2c_search_mode(mode)
            for f_name in ("address", "data", "data2"):
                if f_name in arguments:
                    val = arguments[f_name]
                    if isinstance(val, bool) or not isinstance(val, int):
                        raise OscilloscopeError(f"{command} argument {f_name} must be an integer")
                    validate_i2c_pattern_value(val, f_name)
            if "qualifier" in arguments:
                q = arguments["qualifier"]
                if not isinstance(q, str):
                    raise OscilloscopeError(f"{command} argument qualifier must be a string")
                validate_search_qualifier(q)
        elif protocol == "spi":
            validate_spi_search_mode(mode)
            canonical_data = None
            canonical_width = None
            if "data" in arguments:
                data = arguments["data"]
                if not isinstance(data, str):
                    raise OscilloscopeError(f"{command} argument data must be a string")
                canonical_data = validate_pattern_hex_x(data, "data")
            if "width" in arguments:
                width = arguments["width"]
                if isinstance(width, bool) or not isinstance(width, int):
                    raise OscilloscopeError(f"{command} argument width must be an integer")
                canonical_width = validate_spi_width(width)
            validate_spi_search_pattern_width(canonical_data, canonical_width)
        elif protocol == "can":
            canonical_mode = validate_can_search_mode(mode)
            canonical_data = None
            canonical_data_length = None
            canonical_id = None
            canonical_id_mode = None
            if "data" in arguments:
                data = arguments["data"]
                if not isinstance(data, str):
                    raise OscilloscopeError(f"{command} argument data must be a string")
                canonical_data = validate_pattern_hex_x(data, "data")
            if "data_length" in arguments:
                length = arguments["data_length"]
                if isinstance(length, bool) or not isinstance(length, int):
                    raise OscilloscopeError(f"{command} argument data_length must be an integer")
                canonical_data_length = validate_can_data_length(length)
            if "id" in arguments:
                cid = arguments["id"]
                if not isinstance(cid, str):
                    raise OscilloscopeError(f"{command} argument id must be a string")
                canonical_id = validate_pattern_hex_x(cid, "id")
            if "id_mode" in arguments:
                id_mode = arguments["id_mode"]
                if not isinstance(id_mode, str):
                    raise OscilloscopeError(f"{command} argument id_mode must be a string")
                canonical_id_mode = validate_can_id_mode(id_mode)
            validate_can_search_criteria(
                canonical_mode,
                data=canonical_data,
                data_length=canonical_data_length,
                id_val=canonical_id,
                id_mode=canonical_id_mode,
            )
    except ParameterValidationError as exc:
        raise OscilloscopeError(str(exc)) from exc

    return dict(arguments)


def _normalize_search_worker_arguments(
    command: str, arguments: dict[str, Any], runtime: WorkerRuntime
) -> dict[str, Any]:
    if command not in {"search-state", "search-mode", "search-count", "search-event"}:
        return arguments

    if command == "search-event":
        capabilities = capabilities_for_model_id(runtime.model)
        if not capabilities.supports_search_event_navigation:
            raise OscilloscopeError(
                f"Search event navigation is not supported by the selected "
                f"{capabilities.series} model profile."
            )
        allowed = {"query", "event"}
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for search-event: {sorted(unknown)[0]}"
            )
        if "query" in arguments and "event" in arguments:
            raise OscilloscopeError(
                "search-event query cannot be combined with configure options"
            )
        if arguments.get("query") is True:
            if set(arguments) != {"query"}:
                raise OscilloscopeError("search-event query requires exactly query=true")
            return dict(arguments)
        if "query" in arguments:
            raise OscilloscopeError("search-event argument query must be exactly true")
        if "event" not in arguments or set(arguments) != {"event"}:
            raise OscilloscopeError("search-event configure requires exactly event")
        event = arguments["event"]
        if isinstance(event, bool) or not isinstance(event, int):
            raise OscilloscopeError("search-event argument event must be an integer")
        if event <= 0:
            raise OscilloscopeError("search-event argument event must be a positive integer")
        return dict(arguments)

    if command == "search-count":
        if set(arguments) != {"query"} or arguments.get("query") is not True:
            raise OscilloscopeError("search-count requires exactly query=true")
        return dict(arguments)

    configure_key = "enabled" if command == "search-state" else "mode"
    allowed = {"query", configure_key}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for {command}: {sorted(unknown)[0]}"
        )
    if arguments.get("query") is True:
        if set(arguments) != {"query"}:
            raise OscilloscopeError(
                f"{command} query cannot be combined with configure arguments"
            )
        return dict(arguments)
    if "query" in arguments:
        raise OscilloscopeError(f"{command} argument query must be exactly true")
    if set(arguments) != {configure_key}:
        raise OscilloscopeError(
            f"{command} configure requires exactly {configure_key}"
        )

    value = arguments[configure_key]
    if command == "search-state":
        if not isinstance(value, bool):
            raise OscilloscopeError("search-state argument enabled must be a boolean")
        return {"enabled": "true" if value else "false"}

    if not isinstance(value, str):
        raise OscilloscopeError("search-mode argument mode must be a string")
    canonical_modes = {
        "serial1",
        "serial2",
        "edge",
        "glitch",
        "runt",
        "transition",
        "peak",
    }
    if value not in canonical_modes:
        raise OscilloscopeError(
            "search-mode argument mode must be one of: serial1, serial2, edge, "
            "glitch, runt, transition, peak"
        )
    capabilities = capabilities_for_model_id(runtime.model)
    if value not in capabilities.search_modes:
        raise OscilloscopeError(
            f"Search mode {value!r} is not supported by the selected "
            f"{capabilities.series} model profile."
        )
    return dict(arguments)


def _normalize_serial_worker_arguments(
    command: str,
    arguments: dict[str, Any],
    capabilities: ScopeCapabilities | None = None,
) -> dict[str, Any]:
    if command not in {
        "serial-status",
        "serial-mode",
        "serial-enable",
        "serial-disable",
        "serial-uart-set",
        "serial-uart-show",
        "serial-trigger-uart-set",
        "serial-trigger-uart-show",
        "serial-trigger-i2c-set",
        "serial-trigger-i2c-show",
        "serial-trigger-spi-set",
        "serial-trigger-spi-show",
        "serial-trigger-can-set",
        "serial-trigger-can-show",
        "serial-i2c-set",
        "serial-i2c-show",
        "serial-spi-set",
        "serial-spi-show",
        "serial-can-set",
        "serial-can-show",
        "serial-lister-status",
        "serial-lister-display",
        "serial-lister-reference",
        "serial-data",
    }:
        return arguments

    if command == "serial-lister-status":
        if arguments:
            raise OscilloscopeError("serial-lister-status accepts only an empty object")
        return {}
    if command == "serial-lister-display":
        allowed = {"query", "selection"}
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for {command}: {sorted(unknown)[0]}"
            )
        if arguments.get("query") is True:
            if set(arguments) != {"query"}:
                raise OscilloscopeError(
                    f"{command} query cannot be combined with configure arguments"
                )
            return {"query": True}
        if "query" in arguments:
            raise OscilloscopeError(f"{command} argument query must be exactly true")
        if set(arguments) != {"selection"} or not isinstance(
            arguments["selection"], str
        ):
            raise OscilloscopeError(
                f"{command} configure requires exactly selection"
            )
        if arguments["selection"] not in {"off", "bus1", "bus2", "all"}:
            raise OscilloscopeError(
                f"{command} argument selection must be one of: off, bus1, bus2, all"
            )
        return dict(arguments)
    if command == "serial-lister-reference":
        allowed = {"query", "reference"}
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for {command}: {sorted(unknown)[0]}"
            )
        if arguments.get("query") is True:
            if set(arguments) != {"query"}:
                raise OscilloscopeError(
                    f"{command} query cannot be combined with configure arguments"
                )
            return {"query": True}
        if "query" in arguments:
            raise OscilloscopeError(f"{command} argument query must be exactly true")
        if set(arguments) != {"reference"} or not isinstance(
            arguments["reference"], str
        ):
            raise OscilloscopeError(
                f"{command} configure requires exactly reference"
            )
        if arguments["reference"] not in {"trigger", "previous"}:
            raise OscilloscopeError(
                f"{command} argument reference must be one of: trigger, previous"
            )
        return dict(arguments)
    if command == "serial-data":
        if set(arguments) != {"output"} or not isinstance(arguments["output"], str):
            raise OscilloscopeError(
                "serial-data requires exactly a string output"
            )
        if not arguments["output"]:
            raise OscilloscopeError("serial-data output must not be empty")
        return dict(arguments)

    if command in {"serial-trigger-i2c-set", "serial-trigger-i2c-show", "serial-trigger-spi-set", "serial-trigger-spi-show", "serial-trigger-can-set", "serial-trigger-can-show"}:
        fields_by_command = {
            "serial-trigger-i2c-set": {"type", "address", "data", "data2", "qualifier"},
            "serial-trigger-i2c-show": set(),
            "serial-trigger-spi-set": {"type", "width", "data"},
            "serial-trigger-spi-show": set(),
            "serial-trigger-can-set": {"type", "id", "id_mode", "data", "data_length"},
            "serial-trigger-can-show": set(),
        }
        allowed = {"bus"} | fields_by_command[command]
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for {command}: {sorted(unknown)[0]}"
            )
        query = command.endswith("-show")
        validator = {
            "serial-trigger-i2c-set": validate_serial_i2c_trigger_request,
            "serial-trigger-i2c-show": validate_serial_i2c_trigger_request,
            "serial-trigger-spi-set": validate_serial_spi_trigger_request,
            "serial-trigger-spi-show": validate_serial_spi_trigger_request,
            "serial-trigger-can-set": validate_serial_can_trigger_request,
            "serial-trigger-can-show": validate_serial_can_trigger_request,
        }[command]
        values = {
            key: arguments.get(key) for key in fields_by_command[command]
        }
        canonical = validator(
            arguments.get("bus"), query=query, capabilities=capabilities, **values
        )
        normalized: dict[str, Any] = {"bus": canonical[0]}
        if query:
            return normalized
        elif command == "serial-trigger-i2c-set":
            _, trigger_type, address, data, data2, qualifier = canonical
            normalized.update(type=trigger_type)
            for key, value in {
                "address": address, "data": data, "data2": data2, "qualifier": qualifier
            }.items():
                if value is not None:
                    normalized[key] = value
        elif command == "serial-trigger-spi-set":
            _, trigger_type, width, data = canonical
            normalized.update(type=trigger_type, width=width, data=data)
        else:
            _, trigger_type, id_value, id_mode, data, data_length = canonical
            normalized.update(type=trigger_type)
            for key, value in {
                "id": id_value, "id_mode": id_mode, "data": data,
                "data_length": data_length,
            }.items():
                if value is not None:
                    normalized[key] = value
        return normalized

    if command in {"serial-trigger-uart-set", "serial-trigger-uart-show"}:
        query = command.endswith("-show")
        allowed = {"bus"} | (set() if query else {"type", "data", "qualifier"})
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for {command}: {sorted(unknown)[0]}"
            )
        bus, trigger_type, data, qualifier = validate_serial_uart_trigger_request(
            arguments.get("bus"),
            query=query,
            type=None if query else arguments.get("type"),
            data=None if query else arguments.get("data"),
            qualifier=None if query else arguments.get("qualifier"),
            capabilities=capabilities,
        )
        normalized: dict[str, Any] = {"bus": bus}
        if query:
            return normalized
        else:
            normalized.update(
                type=trigger_type,
                **(
                    {"data": data, "qualifier": qualifier}
                    if data is not None
                    else {}
                ),
            )
        return normalized

    if command in {"serial-uart-set", "serial-uart-show", "serial-i2c-set", "serial-i2c-show", "serial-spi-set", "serial-spi-show", "serial-can-set", "serial-can-show"}:
        query = command.endswith("-show")
        fields_by_command = {
            "serial-uart-set": {"rx_source", "tx_source", "baud_rate", "data_bits", "parity", "polarity", "bit_order"},
            "serial-uart-show": set(),
            "serial-i2c-set": {"clock_source", "data_source", "address_size"},
            "serial-i2c-show": set(),
            "serial-spi-set": {"clock_source", "mosi_source", "miso_source", "frame_source", "clock_slope", "bit_order", "word_width", "framing", "clock_timeout"},
            "serial-spi-show": set(),
            "serial-can-set": {"source", "baud_rate", "signal_definition", "sample_point"},
            "serial-can-show": set(),
        }
        allowed = {"bus"} | fields_by_command[command]
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for {command}: {sorted(unknown)[0]}"
            )
        bus = arguments.get("bus")
        if isinstance(bus, bool) or not isinstance(bus, int):
            raise OscilloscopeError(f"{command} argument bus must be an integer")
        if query:
            return {"bus": bus}
        fields = fields_by_command[command]
        if not any(field in arguments for field in fields):
            raise OscilloscopeError(
                f"{command} configure requires at least one setting"
            )
        for field, value in arguments.items():
            if field in {"rx_source", "tx_source", "clock_source", "data_source", "mosi_source", "miso_source", "frame_source", "source", "parity", "polarity", "bit_order", "address_size", "clock_slope", "framing", "signal_definition"} and not isinstance(value, str):
                raise OscilloscopeError(f"{command} argument {field} must be a string")
            if field in {"baud_rate", "data_bits", "word_width"} and (isinstance(value, bool) or not isinstance(value, int)):
                raise OscilloscopeError(f"{command} argument {field} must be an integer")
            if field in {"clock_timeout", "sample_point"} and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise OscilloscopeError(f"{command} argument {field} must be a number")
        return dict(arguments)

    if command == "serial-status":
        if set(arguments) != {"bus"}:
            raise OscilloscopeError("serial-status requires exactly bus")
        bus = arguments["bus"]
        if isinstance(bus, bool) or not isinstance(bus, int):
            raise OscilloscopeError("serial-status argument bus must be an integer")
        return dict(arguments)

    if command in {"serial-enable", "serial-disable"}:
        if set(arguments) != {"bus"}:
            raise OscilloscopeError(f"{command} requires exactly bus")
        bus = arguments["bus"]
        if isinstance(bus, bool) or not isinstance(bus, int):
            raise OscilloscopeError(f"{command} argument bus must be an integer")
        return {"bus": bus}

    if command != "serial-mode":
        return arguments
    allowed = {"bus", "query", "mode"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for {command}: {sorted(unknown)[0]}"
        )
    bus = arguments.get("bus")
    if isinstance(bus, bool) or not isinstance(bus, int):
        raise OscilloscopeError(f"{command} argument bus must be an integer")
    if arguments.get("query") is True:
        if set(arguments) != {"bus", "query"}:
            raise OscilloscopeError(
                f"{command} query cannot be combined with configure arguments"
            )
        return dict(arguments)
    if "query" in arguments:
        raise OscilloscopeError(f"{command} argument query must be exactly true")
    if set(arguments) != {"bus", "mode"}:
        raise OscilloscopeError(
            f"{command} configure requires exactly bus and mode"
        )
    value = arguments["mode"]
    if not isinstance(value, str):
        raise OscilloscopeError("serial-mode argument mode must be a string")
    return dict(arguments)


def _serial_uart_trigger_worker_namespace(
    arguments: dict[str, Any], runtime: WorkerRuntime
) -> argparse.Namespace:
    """Build a serial trigger runtime namespace without CLI parsing."""

    namespace = argparse.Namespace(
        command=arguments["command"],
        bus=arguments["bus"],
        query=arguments.get("query", False),
        type=arguments.get("type"),
        data=arguments.get("data"),
        qualifier=arguments.get("qualifier"),
        data2=arguments.get("data2"),
        address=arguments.get("address"),
        width=arguments.get("width"),
        id=arguments.get("id"),
        id_mode=arguments.get("id_mode"),
        data_length=arguments.get("data_length"),
        simulate=runtime.mode == "simulate",
        dry_run=False,
        live=runtime.mode == "live",
        model=runtime.model,
        resource=runtime.resource,
        json=True,
        log_scpi=False,
        visa_library=None,
    )
    return namespace
