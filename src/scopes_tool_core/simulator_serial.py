"""Simulated Serial protocol, trigger, display, and Lister SCPI handling."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .simulator_support import (
    SimulatorBackendError,
    _parse_scpi_bool_write,
    _parse_scpi_string_arg,
)
from .serial import (
    SERIAL_MODE_TOKENS,
    parse_serial_can_trigger_id_mode,
    parse_serial_can_trigger_type,
    parse_serial_i2c_trigger_qualifier,
    parse_serial_i2c_trigger_type,
    parse_serial_spi_trigger_type,
    normalize_serial_trigger_pattern,
    parse_serial_mode,
    parse_serial_uart_trigger_qualifier,
    parse_serial_uart_trigger_type,
    serial_uart_trigger_qualifier_readback,
    serial_uart_trigger_type_readback,
    serial_can_trigger_type_readback,
    serial_i2c_trigger_qualifier_readback,
    serial_i2c_trigger_type_readback,
    serial_spi_trigger_type_readback,
)

if TYPE_CHECKING:
    from .simulator_backend import SimulatorBackend


def apply_serial_write(backend: SimulatorBackend, command: str) -> bool:
    """Apply one Serial write in the original command matching order."""

    if match := re.fullmatch(r":SBUS(\d+):MODE (.+)", command, re.IGNORECASE):
        bus = backend._validate_serial_bus(int(match.group(1)))
        canonical = parse_serial_mode(match.group(2))
        if canonical is None or canonical not in backend._capabilities.serial_modes:
            raise SimulatorBackendError(
                f"Serial mode {match.group(2)!r} is not supported by "
                f"simulator model {backend.model}."
            )
        backend.serial_modes[bus] = SERIAL_MODE_TOKENS[canonical]
    elif match := re.fullmatch(
        r":SBUS(\d+):DISPLAY (.+)", command, re.IGNORECASE
    ):
        bus = backend._validate_serial_bus(int(match.group(1)))
        backend.serial_display[bus] = _parse_scpi_bool_write(command)
    elif match := re.fullmatch(r":LISTer:DISPlay (.+)", command, re.IGNORECASE):
        value = _canonical_lister_display(match.group(1))
        if value == "SBUS2" and backend._capabilities.serial_bus_count < 2:
            raise SimulatorBackendError(
                f"Simulator model {backend.model} does not support Lister bus2 display."
            )
        backend.lister_display = value
    elif match := re.fullmatch(r":LISTer:REFerence (.+)", command, re.IGNORECASE):
        backend.lister_reference = _canonical_lister_reference(match.group(1))
    elif apply_serial_uart_trigger_write(backend, command):
        pass
    elif apply_serial_i2c_trigger_write(backend, command):
        pass
    elif apply_serial_spi_trigger_write(backend, command):
        pass
    elif apply_serial_can_trigger_write(backend, command):
        pass
    elif apply_serial_protocol_write(backend, command):
        pass
    else:
        return False
    return True


def query_lister(backend: SimulatorBackend, command: str) -> str | None:
    """Return a Lister setting, or None for an unrelated query."""

    upper = command.upper()
    if upper == ":LISTER:DISPLAY?":
        return backend.lister_display
    if upper == ":LISTER:REFERENCE?":
        return backend.lister_reference
    return None


def query_serial(backend: SimulatorBackend, command: str) -> str | None:
    """Return a Serial response in the original command matching order."""

    serial_uart_trigger_value = query_serial_uart_trigger(backend, command)
    if serial_uart_trigger_value is not None:
        return serial_uart_trigger_value
    serial_i2c_trigger_value = query_serial_i2c_trigger(backend, command)
    if serial_i2c_trigger_value is not None:
        return serial_i2c_trigger_value
    serial_spi_trigger_value = query_serial_spi_trigger(backend, command)
    if serial_spi_trigger_value is not None:
        return serial_spi_trigger_value
    serial_can_trigger_value = query_serial_can_trigger(backend, command)
    if serial_can_trigger_value is not None:
        return serial_can_trigger_value
    serial_protocol_value = query_serial_protocol(backend, command)
    if serial_protocol_value is not None:
        return serial_protocol_value
    serial_match = re.fullmatch(
        r":SBUS(\d+)(?::(MODE|DISPLAY))?\?", command, re.IGNORECASE
    )
    if serial_match is not None:
        bus = backend._validate_serial_bus(int(serial_match.group(1)))
        setting = serial_match.group(2)
        if setting is None:
            enabled = 1 if backend.serial_display[bus] else 0
            return (
                f":SBUS{bus}:DISP {enabled};"
                f"MODE {backend.serial_modes[bus]};"
            )
        if setting.upper() == "MODE":
            return backend.serial_modes[bus]
        return "1" if backend.serial_display[bus] else "0"
    return None


def apply_serial_protocol_write(backend: SimulatorBackend, command: str) -> bool:
    match = re.fullmatch(r":SBUS(\d+):(UART|IIC|SPI|CAN):(.+?)\s+(.+)", command, re.IGNORECASE)
    if match is None:
        return False
    bus = backend._validate_serial_bus(int(match.group(1)))
    key = _serial_protocol_field_key(bus, match.group(2), match.group(3))
    if key is None:
        raise SimulatorBackendError(f"Unsupported simulator serial command: {command}")
    backend.serial_protocol_settings[bus][key] = match.group(4).strip()
    return True


def apply_serial_uart_trigger_write(backend: SimulatorBackend, command: str) -> bool:
    match = re.fullmatch(
        r":SBUS(\d+):UART:TRIGger:(TYPE|DATA|QUALifier)\s+(.+)",
        command,
        re.IGNORECASE,
    )
    if match is None:
        return False
    bus = backend._validate_serial_bus(int(match.group(1)))
    field_name = match.group(2).upper()
    value = match.group(3).strip()
    if field_name == "TYPE":
        backend.serial_uart_trigger_types[bus] = serial_uart_trigger_type_readback(
            parse_serial_uart_trigger_type(value)
        )
    elif field_name == "DATA":
        try:
            data = int(value)
        except ValueError as exc:
            raise SimulatorBackendError(
                f"Unsupported simulator UART trigger data: {value!r}"
            ) from exc
        if not 0 <= data <= 255:
            raise SimulatorBackendError(
                "Simulator UART trigger data must be in range 0-255."
            )
        backend.serial_uart_trigger_data[bus] = data
    else:
        backend.serial_uart_trigger_qualifiers[bus] = (
            serial_uart_trigger_qualifier_readback(
                parse_serial_uart_trigger_qualifier(value)
            )
        )
    return True


def query_serial_uart_trigger(backend: SimulatorBackend, command: str) -> str | None:
    match = re.fullmatch(
        r":SBUS(\d+):UART:TRIGger:(TYPE|DATA|QUALifier)\?",
        command,
        re.IGNORECASE,
    )
    if match is None:
        return None
    bus = backend._validate_serial_bus(int(match.group(1)))
    field_name = match.group(2).upper()
    if field_name == "TYPE":
        return backend.serial_uart_trigger_types[bus]
    if field_name == "DATA":
        return str(backend.serial_uart_trigger_data[bus])
    return backend.serial_uart_trigger_qualifiers[bus]


def apply_serial_i2c_trigger_write(backend: SimulatorBackend, command: str) -> bool:
    match = re.fullmatch(
        r":SBUS(\d+):IIC:TRIGger:(TYPE|PATTern:ADDRess|PATTern:DATA|PATTern:DATa2|QUALifier)\s+(.+)",
        command,
        re.IGNORECASE,
    )
    if match is None:
        return False
    bus = backend._validate_serial_bus(int(match.group(1)))
    field_name = match.group(2).upper()
    value = match.group(3).strip()
    if field_name == "TYPE":
        backend.serial_i2c_trigger_types[bus] = serial_i2c_trigger_type_readback(
            parse_serial_i2c_trigger_type(value)
        )
    elif field_name.endswith("ADDRESS"):
        backend.serial_i2c_trigger_addresses[bus] = int(value, 0)
    elif field_name.endswith("DATA2"):
        backend.serial_i2c_trigger_data2[bus] = int(value, 0)
    elif field_name.endswith("DATA"):
        backend.serial_i2c_trigger_data[bus] = int(value, 0)
    else:
        backend.serial_i2c_trigger_qualifiers[bus] = serial_i2c_trigger_qualifier_readback(
            parse_serial_i2c_trigger_qualifier(value)
        )
    return True


def query_serial_i2c_trigger(backend: SimulatorBackend, command: str) -> str | None:
    match = re.fullmatch(
        r":SBUS(\d+):IIC:TRIGger:(TYPE|PATTern:ADDRess|PATTern:DATA|PATTern:DATa2|QUALifier)\?",
        command,
        re.IGNORECASE,
    )
    if match is None:
        return None
    bus = backend._validate_serial_bus(int(match.group(1)))
    field_name = match.group(2).upper()
    if field_name == "TYPE":
        return backend.serial_i2c_trigger_types[bus]
    if field_name.endswith("ADDRESS"):
        return str(backend.serial_i2c_trigger_addresses[bus])
    if field_name.endswith("DATA2"):
        return str(backend.serial_i2c_trigger_data2[bus])
    if field_name.endswith("DATA"):
        return str(backend.serial_i2c_trigger_data[bus])
    return backend.serial_i2c_trigger_qualifiers[bus]


def apply_serial_spi_trigger_write(backend: SimulatorBackend, command: str) -> bool:
    match = re.fullmatch(
        r":SBUS(\d+):SPI:TRIGger:(TYPE|PATTern:(MOSI|MISO):(WIDTh|DATA))\s+(.+)",
        command,
        re.IGNORECASE,
    )
    if match is None:
        return False
    bus = backend._validate_serial_bus(int(match.group(1)))
    field_name = match.group(2).upper()
    channel = (match.group(3) or "").upper()
    value = match.group(5).strip()
    if field_name == "TYPE":
        backend.serial_spi_trigger_types[bus] = serial_spi_trigger_type_readback(
            parse_serial_spi_trigger_type(value)
        )
    elif field_name.endswith("WIDTH"):
        backend.serial_spi_trigger_widths[bus][channel] = int(value)
    else:
        backend.serial_spi_trigger_data[bus][channel] = normalize_serial_trigger_pattern(
            _parse_scpi_string_arg(value), "SPI trigger data", max_bits=64
        )
    return True


def query_serial_spi_trigger(backend: SimulatorBackend, command: str) -> str | None:
    match = re.fullmatch(
        r":SBUS(\d+):SPI:TRIGger:(TYPE|PATTern:(MOSI|MISO):(WIDTh|DATA))\?",
        command,
        re.IGNORECASE,
    )
    if match is None:
        return None
    bus = backend._validate_serial_bus(int(match.group(1)))
    field_name = match.group(2).upper()
    channel = (match.group(3) or "").upper()
    if field_name == "TYPE":
        return backend.serial_spi_trigger_types[bus]
    if field_name.endswith("WIDTH"):
        return str(backend.serial_spi_trigger_widths[bus][channel])
    return f'"{backend.serial_spi_trigger_data[bus][channel]}"'


def apply_serial_can_trigger_write(backend: SimulatorBackend, command: str) -> bool:
    condition = re.fullmatch(
        r":SBUS(\d+):CAN:TRIGger\s+(.+)", command, re.IGNORECASE
    )
    if condition is not None:
        bus = backend._validate_serial_bus(int(condition.group(1)))
        backend.serial_can_trigger_types[bus] = serial_can_trigger_type_readback(
            parse_serial_can_trigger_type(condition.group(2).strip())
        )
        return True
    match = re.fullmatch(
        r":SBUS(\d+):CAN:TRIGger:PATTern:(ID:MODE|ID|DATA:LENGth|DATA)\s+(.+)",
        command,
        re.IGNORECASE,
    )
    if match is None:
        return False
    bus = backend._validate_serial_bus(int(match.group(1)))
    field_name = match.group(2).upper()
    value = match.group(3).strip()
    if field_name == "ID:MODE":
        backend.serial_can_trigger_id_modes[bus] = "STAN" if parse_serial_can_trigger_id_mode(value) == "standard" else "EXT"
    elif field_name == "ID":
        backend.serial_can_trigger_ids[bus] = normalize_serial_trigger_pattern(
            _parse_scpi_string_arg(value), "CAN trigger ID", max_bits=29
        )
    elif field_name == "DATA:LENGTH":
        backend.serial_can_trigger_data_lengths[bus] = int(value)
    else:
        backend.serial_can_trigger_data[bus] = normalize_serial_trigger_pattern(
            _parse_scpi_string_arg(value), "CAN trigger data", max_bits=64
        )
    return True


def query_serial_can_trigger(backend: SimulatorBackend, command: str) -> str | None:
    condition = re.fullmatch(r":SBUS(\d+):CAN:TRIGger\?", command, re.IGNORECASE)
    if condition is not None:
        bus = backend._validate_serial_bus(int(condition.group(1)))
        return backend.serial_can_trigger_types[bus]
    match = re.fullmatch(
        r":SBUS(\d+):CAN:TRIGger:PATTern:(ID:MODE|ID|DATA:LENGth|DATA)\?",
        command, re.IGNORECASE
    )
    if match is None:
        return None
    bus = backend._validate_serial_bus(int(match.group(1)))
    field_name = match.group(2).upper()
    if field_name == "ID:MODE":
        return backend.serial_can_trigger_id_modes[bus]
    if field_name == "ID":
        return f'"{backend.serial_can_trigger_ids[bus]}"'
    if field_name == "DATA:LENGTH":
        return str(backend.serial_can_trigger_data_lengths[bus])
    return f'"{backend.serial_can_trigger_data[bus]}"'


def query_serial_protocol(backend: SimulatorBackend, command: str) -> str | None:
    match = re.fullmatch(r":SBUS(\d+):(UART|IIC|SPI|CAN):(.+?)\?", command, re.IGNORECASE)
    if match is None:
        return None
    bus = backend._validate_serial_bus(int(match.group(1)))
    key = _serial_protocol_field_key(bus, match.group(2), match.group(3))
    if key is None:
        raise SimulatorBackendError(f"Unsupported simulator serial query: {command}")
    value = backend.serial_protocol_settings[bus][key]
    return _serial_protocol_query_value(key, value)


def _serial_protocol_field_key(bus: int, protocol: str, suffix: str) -> str | None:
    prefix = protocol.upper() + ":"
    paths = {
        "UART:SOURCE:RX": "uart_rx_source",
        "UART:SOURCE:TX": "uart_tx_source",
        "UART:BAUDRATE": "uart_baud_rate",
        "UART:WIDTH": "uart_data_bits",
        "UART:PARITY": "uart_parity",
        "UART:POLARITY": "uart_polarity",
        "UART:BITORDER": "uart_bit_order",
        "IIC:SOURCE:CLOCK": "iic_clock_source",
        "IIC:SOURCE:DATA": "iic_data_source",
        "IIC:ASIZE": "iic_address_size",
        "SPI:SOURCE:CLOCK": "spi_clock_source",
        "SPI:SOURCE:FRAME": "spi_frame_source",
        "SPI:SOURCE:MOSI": "spi_mosi_source",
        "SPI:SOURCE:MISO": "spi_miso_source",
        "SPI:CLOCK:SLOPE": "spi_clock_slope",
        "SPI:BITORDER": "spi_bit_order",
        "SPI:WIDTH": "spi_word_width",
        "SPI:FRAMING": "spi_framing",
        "SPI:CLOCK:TIMEOUT": "spi_clock_timeout",
        "CAN:SOURCE": "can_source",
        "CAN:SIGNAL:BAUDRATE": "can_baud_rate",
        "CAN:SIGNAL:DEFINITION": "can_signal_definition",
        "CAN:SAMPLEPOINT": "can_sample_point",
    }
    return paths.get(prefix + suffix.upper())


def _serial_protocol_query_value(key: str, value: str) -> str:
    if key.endswith("_bit_order"):
        return {"LSBFirst": "LSBF", "MSBFirst": "MSBF"}.get(value, value)
    if key == "spi_clock_slope":
        return {"POSitive": "POS", "NEGative": "NEG"}.get(value, value)
    if key == "spi_framing":
        return {"CHIPselect": "CHIP", "NCHipselect": "NCH", "TIMeout": "TIM"}.get(value, value)
    return value


def _canonical_lister_display(raw: str) -> str:
    values = {
        "OFF": "OFF",
        "0": "OFF",
        "SBUS1": "SBUS1",
        "ON": "SBUS1",
        "1": "SBUS1",
        "SBUS2": "SBUS2",
        "2": "SBUS2",
        "ALL": "ALL",
    }
    try:
        return values[raw.strip().upper()]
    except KeyError as exc:
        raise SimulatorBackendError(
            f"Unsupported simulator Lister display: {raw!r}"
        ) from exc


def _canonical_lister_reference(raw: str) -> str:
    values = {
        "TRIGGER": "TRIGger",
        "TRIG": "TRIGger",
        "PREVIOUS": "PREVious",
        "PREV": "PREVious",
    }
    try:
        return values[raw.strip().upper()]
    except KeyError as exc:
        raise SimulatorBackendError(
            f"Unsupported simulator Lister reference: {raw!r}"
        ) from exc
