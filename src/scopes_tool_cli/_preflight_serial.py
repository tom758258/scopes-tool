"""CLI pre-open validation for Serial decode, Search, and Serial Search."""

from __future__ import annotations

import argparse
import math

from scopes_tool_core.capabilities import ScopeCapabilities
from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.search import (
    require_search_basic,
    validate_can_data_length,
    validate_can_id_mode,
    validate_can_search_criteria,
    validate_can_search_mode,
    validate_i2c_pattern_value,
    validate_i2c_search_mode,
    validate_pattern_hex_x,
    validate_search_event,
    validate_search_mode,
    validate_search_qualifier,
    validate_serial_search_bus,
    validate_spi_search_pattern_width,
    validate_spi_search_mode,
    validate_spi_width,
    validate_uart_data,
    validate_uart_search_mode,
)
from scopes_tool_core.serial import (
    serial_can_configure_commands,
    serial_i2c_configure_commands,
    serial_spi_configure_commands,
    serial_uart_configure_commands,
    validate_serial_uart_trigger_request,
    validate_serial_i2c_trigger_request,
    validate_serial_spi_trigger_request,
    validate_serial_can_trigger_request,
    normalize_can_signal_definition,
    normalize_i2c_address_size,
    normalize_serial_bit_order,
    normalize_serial_source,
    normalize_spi_clock_slope,
    normalize_spi_framing,
    normalize_uart_parity,
    normalize_uart_polarity,
    validate_can_baud_rate,
    validate_can_sample_point,
    validate_uart_baud_rate,
    validate_serial_bus,
    validate_serial_mode,
    validate_serial_lister_display,
    validate_serial_lister_reference,
    validate_spi_framing_clock_timeout,
    require_serial_decode,
)

from ._preflight_common import _pre_open_capabilities


def _validate_serial_args(args: argparse.Namespace) -> None:
    if args.command in {
        "serial-lister-status",
        "serial-lister-display",
        "serial-lister-reference",
        "serial-data",
    }:
        _validate_serial_lister_args(args)
        return
    capabilities = _pre_open_capabilities(args)
    if args.command in {"serial-trigger-uart-set", "serial-trigger-uart-show"}:
        query = args.command.endswith("-show")
        validate_serial_uart_trigger_request(
            args.bus,
            query=query,
            type=None if query else args.type,
            data=None if query else args.data,
            qualifier=None if query else args.qualifier,
            capabilities=capabilities,
        )
        return
    trigger_validators = {
        "serial-trigger-i2c-set": validate_serial_i2c_trigger_request,
        "serial-trigger-i2c-show": validate_serial_i2c_trigger_request,
        "serial-trigger-spi-set": validate_serial_spi_trigger_request,
        "serial-trigger-spi-show": validate_serial_spi_trigger_request,
        "serial-trigger-can-set": validate_serial_can_trigger_request,
        "serial-trigger-can-show": validate_serial_can_trigger_request,
    }
    if args.command in trigger_validators:
        query = args.command.endswith("-show")
        trigger_validators[args.command](
            args.bus,
            query=query,
            **{
                key: getattr(args, key, None)
                for key in {
                    "serial-trigger-i2c-set": {"type", "address", "data", "data2", "qualifier"},
                    "serial-trigger-i2c-show": {"type", "address", "data", "data2", "qualifier"},
                    "serial-trigger-spi-set": {"type", "width", "data"},
                    "serial-trigger-spi-show": {"type", "width", "data"},
                    "serial-trigger-can-set": {"type", "id", "id_mode", "data", "data_length"},
                    "serial-trigger-can-show": {"type", "id", "id_mode", "data", "data_length"},
                }[args.command]
            },
            capabilities=capabilities,
        )
        return
    if capabilities is not None:
        validate_serial_bus(args.bus, capabilities)
        if args.command == "serial-mode" and not args.query:
            validate_serial_mode(args.mode, capabilities)
    if args.command in {"serial-uart-set", "serial-i2c-set", "serial-spi-set", "serial-can-set"}:
        _validate_serial_protocol_args(args, capabilities)

def _validate_serial_lister_args(args: argparse.Namespace) -> None:
    capabilities = _pre_open_capabilities(args)
    if capabilities is None:
        return
    require_serial_decode(capabilities)
    if args.command == "serial-lister-display" and not args.query:
        validate_serial_lister_display(args.selection, capabilities)
    elif args.command == "serial-lister-reference" and not args.query:
        validate_serial_lister_reference(args.reference, capabilities)

def _validate_serial_protocol_args(
    args: argparse.Namespace, capabilities: ScopeCapabilities | None
) -> None:
    fields_by_command = {
        "serial-uart-set": ("rx_source", "tx_source", "baud_rate", "data_bits", "parity", "polarity", "bit_order"),
        "serial-i2c-set": ("clock_source", "data_source", "address_size"),
        "serial-spi-set": ("clock_source", "mosi_source", "miso_source", "frame_source", "clock_slope", "bit_order", "word_width", "framing", "clock_timeout"),
        "serial-can-set": ("source", "baud_rate", "signal_definition", "sample_point"),
    }
    fields = fields_by_command[args.command]
    supplied = {field: getattr(args, field) for field in fields if getattr(args, field) is not None}
    if not supplied:
        raise ParameterValidationError(
            f"{args.command} configure requires at least one setting."
        )
    if capabilities is None:
        return
    protocol_mode = {
        "serial-uart-set": "uart",
        "serial-i2c-set": "i2c",
        "serial-spi-set": "spi",
        "serial-can-set": "can",
    }[args.command]
    validate_serial_mode(protocol_mode, capabilities)
    if args.command == "serial-uart-set":
        serial_uart_configure_commands(
            args.bus,
            _serial_cli_values(
                capabilities,
                protocol=args.command,
                rx_source=args.rx_source,
                tx_source=args.tx_source,
                baud_rate=args.baud_rate,
                data_bits=args.data_bits,
                parity=args.parity,
                polarity=args.polarity,
                bit_order=args.bit_order,
            ),
        )
    elif args.command == "serial-i2c-set":
        serial_i2c_configure_commands(
            args.bus,
            _serial_cli_values(
                capabilities,
                protocol=args.command,
                clock_source=args.clock_source,
                data_source=args.data_source,
                address_size=args.address_size,
            ),
        )
    elif args.command == "serial-spi-set":
        serial_spi_configure_commands(
            args.bus,
            _serial_cli_values(
                capabilities,
                protocol=args.command,
                clock_source=args.clock_source,
                mosi_source=args.mosi_source,
                miso_source=args.miso_source,
                frame_source=args.frame_source,
                clock_slope=args.clock_slope,
                bit_order=args.bit_order,
                word_width=args.word_width,
                framing=args.framing,
                clock_timeout=args.clock_timeout,
            ),
        )
    else:
        serial_can_configure_commands(
            args.bus,
            _serial_cli_values(
                capabilities,
                protocol=args.command,
                source=args.source,
                baud_rate=args.baud_rate,
                signal_definition=args.signal_definition,
                sample_point=args.sample_point,
            ),
        )

def _serial_cli_values(
    capabilities: ScopeCapabilities, *, protocol: str | None = None, **values: object
) -> dict[str, object]:
    normalized = dict(values)
    source_fields = {
        "rx_source", "tx_source", "clock_source", "data_source", "mosi_source",
        "miso_source", "frame_source", "source",
    }
    for field in source_fields:
        if normalized.get(field) is not None:
            normalized[field] = normalize_serial_source(normalized[field], capabilities)
    if normalized.get("parity") is not None:
        normalized["parity"] = normalize_uart_parity(normalized["parity"])
    if normalized.get("polarity") is not None:
        normalized["polarity"] = normalize_uart_polarity(normalized["polarity"])
    if normalized.get("bit_order") is not None:
        normalized["bit_order"] = normalize_serial_bit_order(normalized["bit_order"])
    if normalized.get("address_size") is not None:
        normalized["address_size"] = normalize_i2c_address_size(normalized["address_size"])
    if normalized.get("clock_slope") is not None:
        normalized["clock_slope"] = normalize_spi_clock_slope(normalized["clock_slope"])
    if normalized.get("framing") is not None:
        normalized["framing"] = normalize_spi_framing(normalized["framing"])
    if normalized.get("signal_definition") is not None:
        normalized["signal_definition"] = normalize_can_signal_definition(normalized["signal_definition"])
    if normalized.get("baud_rate") is not None:
        if protocol == "serial-can-set":
            normalized["baud_rate"] = validate_can_baud_rate(normalized["baud_rate"])
        else:
            normalized["baud_rate"] = validate_uart_baud_rate(normalized["baud_rate"], capabilities)
    if normalized.get("data_bits") is not None:
        if isinstance(normalized["data_bits"], bool) or not isinstance(normalized["data_bits"], int) or not 5 <= normalized["data_bits"] <= 9:
            raise ParameterValidationError("UART data bits must be an integer in range 5-9.")
    if normalized.get("word_width") is not None:
        if isinstance(normalized["word_width"], bool) or not isinstance(normalized["word_width"], int) or not 4 <= normalized["word_width"] <= 16:
            raise ParameterValidationError("SPI word width must be an integer in range 4-16.")
    if normalized.get("clock_timeout") is not None:
        value = normalized["clock_timeout"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1e-7 <= float(value) <= 10.0 or not math.isfinite(float(value)):
            raise ParameterValidationError("SPI clock timeout must be a number in range 1e-07-10.0.")
    if protocol == "serial-spi-set":
        validate_spi_framing_clock_timeout(
            normalized.get("framing"), normalized.get("clock_timeout")
        )
    if normalized.get("sample_point") is not None:
        normalized["sample_point"] = validate_can_sample_point(normalized["sample_point"], capabilities)
    return normalized

def _validate_search_args(args: argparse.Namespace) -> None:
    command = args.command
    capabilities = _pre_open_capabilities(args)
    if command == "search-event":
        if capabilities is not None and not capabilities.supports_search_event_navigation:
            raise ParameterValidationError(
                "Search event navigation is not supported by the selected model profile."
            )
        if args.query and args.event is not None:
            raise ParameterValidationError(
                "search-event --query cannot be combined with configure options."
            )
        if not args.query and args.event is None:
            raise ParameterValidationError(
                "search-event configure requires --event."
            )
        if not args.query and args.event is not None:
            validate_search_event(args.event)
        return

    if capabilities is not None and not capabilities.supports_search_basic:
        raise ParameterValidationError(
            "Search is not supported by the selected model profile."
        )
    if command == "search-count":
        return
    query = bool(getattr(args, "query", False))
    configure_key = "enabled" if command == "search-state" else "mode"
    value = getattr(args, configure_key, None)
    if query:
        if value is not None:
            raise ParameterValidationError(
                f"{command} --query cannot be combined with configure options."
            )
        return
    if value is None:
        raise ParameterValidationError(
            f"{command} configure requires --{configure_key}."
        )
    if command == "search-mode" and capabilities is not None:
        validate_search_mode(value, capabilities)

def _extract_serial_search_settings(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "serial-search-can":
        settings = {}
        if getattr(args, "mode", None) is not None:
            settings["mode"] = args.mode
        if getattr(args, "data", None) is not None:
            settings["data"] = args.data
        if getattr(args, "data_length", None) is not None:
            settings["data_length"] = args.data_length
        if getattr(args, "id", None) is not None:
            settings["id_val"] = args.id
        if getattr(args, "id_mode", None) is not None:
            settings["id_mode"] = args.id_mode
        return settings
    fields = {
        "serial-search-uart": ("mode", "data", "qualifier"),
        "serial-search-i2c": ("mode", "address", "data", "data2", "qualifier"),
        "serial-search-spi": ("mode", "data", "width"),
    }[args.command]
    return {f: getattr(args, f) for f in fields if getattr(args, f) is not None}

def _canonical_serial_search_settings(
    args: argparse.Namespace,
) -> dict[str, object]:
    settings = _extract_serial_search_settings(args)
    if "mode" not in settings or settings["mode"] is None:
        raise ParameterValidationError(f"{args.command} configure requires --mode.")

    protocol = args.command.removeprefix("serial-search-")
    canonical_settings = dict(settings)
    if protocol == "uart":
        canonical_settings["mode"] = validate_uart_search_mode(settings["mode"])
        if "data" in settings:
            canonical_settings["data"] = validate_uart_data(settings["data"])
        if "qualifier" in settings:
            canonical_settings["qualifier"] = validate_search_qualifier(settings["qualifier"])
    elif protocol == "i2c":
        canonical_settings["mode"] = validate_i2c_search_mode(settings["mode"])
        if "address" in settings:
            canonical_settings["address"] = validate_i2c_pattern_value(settings["address"], "address")
        if "data" in settings:
            canonical_settings["data"] = validate_i2c_pattern_value(settings["data"], "data")
        if "data2" in settings:
            canonical_settings["data2"] = validate_i2c_pattern_value(settings["data2"], "data2")
        if "qualifier" in settings:
            canonical_settings["qualifier"] = validate_search_qualifier(settings["qualifier"])
    elif protocol == "spi":
        canonical_settings["mode"] = validate_spi_search_mode(settings["mode"])
        if "data" in settings:
            canonical_settings["data"] = validate_pattern_hex_x(settings["data"], "data")
        if "width" in settings:
            canonical_settings["width"] = validate_spi_width(settings["width"])
        validate_spi_search_pattern_width(
            canonical_settings.get("data"), canonical_settings.get("width")
        )
    elif protocol == "can":
        canonical_settings["mode"] = validate_can_search_mode(settings["mode"])
        if "data" in settings:
            canonical_settings["data"] = validate_pattern_hex_x(settings["data"], "data")
        if "data_length" in settings:
            canonical_settings["data_length"] = validate_can_data_length(settings["data_length"])
        if "id_val" in settings:
            canonical_settings["id_val"] = validate_pattern_hex_x(settings["id_val"], "id")
        if "id_mode" in settings:
            canonical_settings["id_mode"] = validate_can_id_mode(settings["id_mode"])
        validate_can_search_criteria(
            canonical_settings["mode"],
            data=canonical_settings.get("data"),
            data_length=canonical_settings.get("data_length"),
            id_val=canonical_settings.get("id_val"),
            id_mode=canonical_settings.get("id_mode"),
        )
    return canonical_settings

def _validate_serial_search_args(args: argparse.Namespace) -> None:
    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        require_search_basic(capabilities)
        validate_serial_search_bus(args.bus, capabilities)
        protocol = args.command.removeprefix("serial-search-")
        validate_serial_mode(protocol, capabilities)

    query = bool(getattr(args, "query", False))
    settings = _extract_serial_search_settings(args)
    if query:
        if settings:
            raise ParameterValidationError(
                f"{args.command} --query cannot be combined with configure options."
            )
        return

    if "mode" not in settings:
        raise ParameterValidationError(f"{args.command} configure requires --mode.")

    protocol = args.command.removeprefix("serial-search-")
    if protocol == "uart":
        validate_uart_search_mode(settings["mode"])
        if "data" in settings:
            validate_uart_data(settings["data"])
        if "qualifier" in settings:
            validate_search_qualifier(settings["qualifier"])
    elif protocol == "i2c":
        validate_i2c_search_mode(settings["mode"])
        if "address" in settings:
            validate_i2c_pattern_value(settings["address"], "address")
        if "data" in settings:
            validate_i2c_pattern_value(settings["data"], "data")
        if "data2" in settings:
            validate_i2c_pattern_value(settings["data2"], "data2")
        if "qualifier" in settings:
            validate_search_qualifier(settings["qualifier"])
    elif protocol == "spi":
        validate_spi_search_mode(settings["mode"])
        canonical_data = None
        canonical_width = None
        if "data" in settings:
            canonical_data = validate_pattern_hex_x(settings["data"], "data")
        if "width" in settings:
            canonical_width = validate_spi_width(settings["width"])
        validate_spi_search_pattern_width(canonical_data, canonical_width)
    elif protocol == "can":
        canonical_mode = validate_can_search_mode(settings["mode"])
        canonical_data = None
        canonical_data_length = None
        canonical_id = None
        canonical_id_mode = None
        if "data" in settings:
            canonical_data = validate_pattern_hex_x(settings["data"], "data")
        if "data_length" in settings:
            canonical_data_length = validate_can_data_length(settings["data_length"])
        if "id_val" in settings:
            canonical_id = validate_pattern_hex_x(settings["id_val"], "id")
        if "id_mode" in settings:
            canonical_id_mode = validate_can_id_mode(settings["id_mode"])
        validate_can_search_criteria(
            canonical_mode,
            data=canonical_data,
            data_length=canonical_data_length,
            id_val=canonical_id,
            id_mode=canonical_id_mode,
        )
