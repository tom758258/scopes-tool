"""Model-guarded basic serial decode bus controls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
import re

from .capabilities import ScopeCapabilities
from .display import parse_display_label
from .errors import (
    ChannelResponseError,
    ParameterValidationError,
    SerialResponseError,
)
from .scpi import SCPIClient
from .trigger import parse_trigger_mode, trigger_mode_query, trigger_mode_serial_command


SERIAL_MODES = (
    "a429",
    "can",
    "cxpi",
    "flexray",
    "i2s",
    "i2c",
    "lin",
    "m1553",
    "manchester",
    "nrz",
    "sent",
    "spi",
    "uart",
    "usb",
    "usb-pd",
)

SERIAL_MODE_TOKENS = {
    "a429": "A429",
    "can": "CAN",
    "cxpi": "CXPI",
    "flexray": "FLEXray",
    "i2s": "I2S",
    "i2c": "IIC",
    "lin": "LIN",
    "m1553": "M1553",
    "manchester": "MANChester",
    "nrz": "NRZ",
    "sent": "SENT",
    "spi": "SPI",
    "uart": "UART",
    "usb": "USB",
    "usb-pd": "USBPd",
}

UART_PARITIES = ("even", "odd", "none")
UART_POLARITIES = ("high", "low")
UART_TRIGGER_TYPES = (
    "rx-start",
    "rx-stop",
    "rx-data",
    "tx-start",
    "tx-stop",
    "tx-data",
    "parity-error",
)
UART_TRIGGER_QUALIFIERS = (
    "equal",
    "not-equal",
    "greater-than",
    "less-than",
)
I2C_TRIGGER_TYPES = (
    "start",
    "stop",
    "restart",
    "read7",
    "read-eeprom",
    "write7",
    "write10",
    "missing-ack",
    "address-no-ack",
    "read7-data2",
    "write7-data2",
)
I2C_TRIGGER_QUALIFIERS = UART_TRIGGER_QUALIFIERS
SPI_TRIGGER_TYPES = ("mosi", "miso")
CAN_TRIGGER_TYPES = (
    "start-of-frame",
    "id-and-data",
    "error",
    "data-frame-id",
    "any-frame-id",
    "remote-frame-id",
    "all-errors",
    "overload",
    "ack-error",
)
CAN_TRIGGER_ID_MODES = ("standard", "extended")
SERIAL_BIT_ORDERS = ("lsb-first", "msb-first")
I2C_ADDRESS_SIZES = ("bit7", "bit8")
SPI_CLOCK_SLOPES = ("positive", "negative")
SPI_FRAMINGS = ("chip-select", "no-chip-select", "timeout")
CAN_SIGNAL_DEFINITIONS = ("canh", "canl", "rx", "tx", "difl", "difh")
SERIAL_LISTER_DISPLAYS = ("off", "bus1", "bus2", "all")
SERIAL_LISTER_REFERENCES = ("trigger", "previous")

_UART_PARITY_TOKENS = {"even": "EVEN", "odd": "ODD", "none": "NONE"}
_UART_POLARITY_TOKENS = {"high": "HIGH", "low": "LOW"}
_UART_TRIGGER_TYPE_TOKENS = {
    "rx-start": "RSTArt",
    "rx-stop": "RSTOp",
    "rx-data": "RDATa",
    "tx-start": "TSTArt",
    "tx-stop": "TSTOp",
    "tx-data": "TDATa",
    "parity-error": "PARityerror",
}
_UART_TRIGGER_TYPE_READBACKS = {
    "RSTA": "rx-start",
    "RSTART": "rx-start",
    "RSTO": "rx-stop",
    "RSTOP": "rx-stop",
    "RDAT": "rx-data",
    "RDATA": "rx-data",
    "TSTA": "tx-start",
    "TSTART": "tx-start",
    "TSTO": "tx-stop",
    "TSTOP": "tx-stop",
    "TDAT": "tx-data",
    "TDATA": "tx-data",
    "PAR": "parity-error",
    "PARITYERROR": "parity-error",
}
_UART_TRIGGER_TYPE_READBACKS_FOR_CANONICAL = {
    "rx-start": "RSTA",
    "rx-stop": "RSTO",
    "rx-data": "RDAT",
    "tx-start": "TSTA",
    "tx-stop": "TSTO",
    "tx-data": "TDAT",
    "parity-error": "PAR",
}
_UART_TRIGGER_QUALIFIER_TOKENS = {
    "equal": "EQUal",
    "not-equal": "NOTequal",
    "greater-than": "GREaterthan",
    "less-than": "LESSthan",
}
_UART_TRIGGER_QUALIFIER_READBACKS = {
    "EQU": "equal",
    "EQUAL": "equal",
    "NOT": "not-equal",
    "NOTEQUAL": "not-equal",
    "GRE": "greater-than",
    "GREATERTHAN": "greater-than",
    "LESS": "less-than",
    "LESSTHAN": "less-than",
}
_UART_TRIGGER_QUALIFIER_READBACKS_FOR_CANONICAL = {
    "equal": "EQU",
    "not-equal": "NOT",
    "greater-than": "GRE",
    "less-than": "LESS",
}
_I2C_TRIGGER_TYPE_TOKENS = {
    "start": "STARt",
    "stop": "STOP",
    "restart": "RESTart",
    "read7": "READ7",
    "read-eeprom": "READEprom",
    "write7": "WRITe7",
    "write10": "WRITe10",
    "missing-ack": "NACKnowledge",
    "address-no-ack": "ANACk",
    "read7-data2": "R7Data2",
    "write7-data2": "W7Data2",
}
_I2C_TRIGGER_TYPE_READBACKS = {
    "STAR": "start", "START": "start", "STOP": "stop",
    "REST": "restart", "RESTART": "restart", "READ7": "read7",
    "READE": "read-eeprom", "READEPROM": "read-eeprom",
    "WRIT7": "write7", "WRITE7": "write7", "WRIT10": "write10",
    "WRITE10": "write10", "NACK": "missing-ack",
    "NACKNOWLEDGE": "missing-ack", "ANAC": "address-no-ack",
    "ANACK": "address-no-ack", "R7D2": "read7-data2",
    "R7DATA2": "read7-data2", "W7D2": "write7-data2",
    "W7DATA2": "write7-data2",
}
_I2C_TRIGGER_QUALIFIER_TOKENS = {
    "equal": "EQUal", "not-equal": "NOTequal", "less-than": "LESSthan",
    "greater-than": "GREaterthan",
}
_I2C_TRIGGER_QUALIFIER_READBACKS = {
    "EQU": "equal", "EQUAL": "equal", "NOT": "not-equal",
    "NOTEQUAL": "not-equal", "LESS": "less-than", "LESSTHAN": "less-than",
    "GRE": "greater-than", "GREATERTHAN": "greater-than",
}
_SPI_TRIGGER_TYPE_TOKENS = {"mosi": "MOSI", "miso": "MISO"}
_SPI_TRIGGER_TYPE_READBACKS = {"MOSI": "mosi", "MISO": "miso"}
_CAN_TRIGGER_TYPE_TOKENS = {
    "start-of-frame": "SOF", "id-and-data": "DATA", "error": "ERRor",
    "data-frame-id": "IDData", "any-frame-id": "IDEither",
    "remote-frame-id": "IDRemote", "all-errors": "ALLerrors",
    "overload": "OVERload", "ack-error": "ACKerror",
}
_CAN_TRIGGER_TYPE_READBACKS = {
    "SOF": "start-of-frame", "DATA": "id-and-data", "ERR": "error",
    "ERROR": "error", "IDD": "data-frame-id", "IDDATA": "data-frame-id",
    "IDE": "any-frame-id", "IDEITHER": "any-frame-id",
    "IDR": "remote-frame-id", "IDREMOTE": "remote-frame-id",
    "ALL": "all-errors", "ALLERRORS": "all-errors", "OVER": "overload",
    "OVERLOAD": "overload", "ACK": "ack-error", "ACKERROR": "ack-error",
}
_CAN_TRIGGER_ID_MODE_TOKENS = {"standard": "STANdard", "extended": "EXTended"}
_CAN_TRIGGER_ID_MODE_READBACKS = {
    "STAN": "standard", "STANDARD": "standard", "EXT": "extended",
    "EXTENDED": "extended",
}
_BIT_ORDER_TOKENS = {"lsb-first": "LSBFirst", "msb-first": "MSBFirst"}
_I2C_ADDRESS_SIZE_TOKENS = {"bit7": "BIT7", "bit8": "BIT8"}
_SPI_SLOPE_TOKENS = {"positive": "POSitive", "negative": "NEGative"}
_SPI_FRAMING_TOKENS = {
    "chip-select": "CHIPselect",
    "no-chip-select": "NCHipselect",
    "timeout": "TIMeout",
}
_CAN_SIGNAL_TOKENS = {
    "canh": "CANH",
    "canl": "CANL",
    "rx": "RX",
    "tx": "TX",
    "difl": "DIFL",
    "difh": "DIFH",
}
_SERIAL_LISTER_DISPLAY_TOKENS = {
    "off": "OFF",
    "bus1": "SBUS1",
    "bus2": "SBUS2",
    "all": "ALL",
}
_SERIAL_LISTER_REFERENCE_TOKENS = {
    "trigger": "TRIGger",
    "previous": "PREVious",
}

_SERIAL_MODE_READBACKS = {
    "A429": "a429",
    "CAN": "can",
    "CXPI": "cxpi",
    "FLEX": "flexray",
    "FLEXRAY": "flexray",
    "I2S": "i2s",
    "IIC": "i2c",
    "LIN": "lin",
    "M1553": "m1553",
    "MANC": "manchester",
    "MANCHESTER": "manchester",
    "NRZ": "nrz",
    "SENT": "sent",
    "SPI": "spi",
    "UART": "uart",
    "USB": "usb",
    "USBP": "usb-pd",
    "USBPD": "usb-pd",
}


@dataclass(frozen=True)
class SerialQueryState:
    bus: int
    raw: str

    def to_json(self) -> dict[str, object]:
        return {"bus": self.bus, "raw": self.raw}


@dataclass(frozen=True)
class SerialModeState:
    bus: int
    mode: str | None
    raw_mode: str | None = None

    def to_json(self) -> dict[str, object]:
        return {"bus": self.bus, "mode": self.mode, "raw_mode": self.raw_mode}


@dataclass(frozen=True)
class SerialDisplayState:
    bus: int
    enabled: bool
    raw_state: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "bus": self.bus,
            "enabled": self.enabled,
            "raw_state": self.raw_state,
        }


@dataclass(frozen=True)
class SerialUartState:
    bus: int
    mode: str
    raw_mode: str | None = None
    rx_source: str | None = None
    raw_rx_source: str | None = None
    tx_source: str | None = None
    raw_tx_source: str | None = None
    baud_rate: int | None = None
    raw_baud_rate: str | None = None
    data_bits: int | None = None
    raw_data_bits: str | None = None
    parity: str | None = None
    raw_parity: str | None = None
    polarity: str | None = None
    raw_polarity: str | None = None
    bit_order: str | None = None
    raw_bit_order: str | None = None

    def to_json(self) -> dict[str, object]:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class SerialUartTriggerState:
    protocol: str
    bus: int
    mode: str | None
    raw_mode: str | None
    selected: bool
    trigger_mode: str | None
    raw_trigger_mode: str | None
    type: str | None
    raw_type: str | None
    data: int | None
    raw_data: str | None
    qualifier: str | None
    raw_qualifier: str | None

    def to_json(self) -> dict[str, object]:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class SerialI2CTriggerState:
    protocol: str
    bus: int
    mode: str | None
    raw_mode: str | None
    selected: bool
    trigger_mode: str | None
    raw_trigger_mode: str | None
    type: str | None
    raw_type: str | None
    address: int | None
    raw_address: str | None
    data: int | None
    raw_data: str | None
    data2: int | None
    raw_data2: str | None
    qualifier: str | None
    raw_qualifier: str | None

    def to_json(self) -> dict[str, object]:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class SerialSpiTriggerState:
    protocol: str
    bus: int
    mode: str | None
    raw_mode: str | None
    selected: bool
    trigger_mode: str | None
    raw_trigger_mode: str | None
    type: str | None
    raw_type: str | None
    width: int | None
    raw_width: str | None
    data: str | None
    raw_data: str | None

    def to_json(self) -> dict[str, object]:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class SerialCanTriggerState:
    protocol: str
    bus: int
    mode: str | None
    raw_mode: str | None
    selected: bool
    trigger_mode: str | None
    raw_trigger_mode: str | None
    type: str | None
    raw_type: str | None
    id: str | None
    raw_id: str | None
    id_mode: str | None
    raw_id_mode: str | None
    data: str | None
    raw_data: str | None
    data_length: int | None
    raw_data_length: str | None

    def to_json(self) -> dict[str, object]:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class SerialI2CState:
    bus: int
    mode: str
    raw_mode: str | None = None
    clock_source: str | None = None
    raw_clock_source: str | None = None
    data_source: str | None = None
    raw_data_source: str | None = None
    address_size: str | None = None
    raw_address_size: str | None = None

    def to_json(self) -> dict[str, object]:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class SerialSpiState:
    bus: int
    mode: str
    raw_mode: str | None = None
    clock_source: str | None = None
    raw_clock_source: str | None = None
    mosi_source: str | None = None
    raw_mosi_source: str | None = None
    miso_source: str | None = None
    raw_miso_source: str | None = None
    frame_source: str | None = None
    raw_frame_source: str | None = None
    clock_slope: str | None = None
    raw_clock_slope: str | None = None
    bit_order: str | None = None
    raw_bit_order: str | None = None
    word_width: int | None = None
    raw_word_width: str | None = None
    framing: str | None = None
    raw_framing: str | None = None
    clock_timeout: float | None = None
    raw_clock_timeout: str | None = None

    def to_json(self) -> dict[str, object]:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class SerialCanState:
    bus: int
    mode: str
    raw_mode: str | None = None
    source: str | None = None
    raw_source: str | None = None
    baud_rate: int | None = None
    raw_baud_rate: str | None = None
    signal_definition: str | None = None
    raw_signal_definition: str | None = None
    sample_point: float | None = None
    raw_sample_point: str | None = None

    def to_json(self) -> dict[str, object]:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class SerialListerState:
    display: str
    reference: str
    raw_display: str
    raw_reference: str

    def to_json(self) -> dict[str, object]:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class SerialListerDisplayState:
    display: str
    raw_display: str | None = None

    def to_json(self) -> dict[str, object]:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class SerialListerReferenceState:
    reference: str
    raw_reference: str | None = None

    def to_json(self) -> dict[str, object]:
        return {key: value for key, value in self.__dict__.items()}


class SerialController:
    """Controller for the supported basic serial decode controls."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def query(self, bus: int) -> SerialQueryState:
        canonical_bus = validate_serial_bus(bus, self.capabilities)
        raw = self.scpi.query(serial_bus_query(canonical_bus)).strip()
        return SerialQueryState(bus=canonical_bus, raw=raw)

    def configure_mode(self, bus: int, mode: str) -> SerialModeState:
        canonical_bus = validate_serial_bus(bus, self.capabilities)
        canonical_mode = validate_serial_mode(mode, self.capabilities)
        self.scpi.write(serial_mode_command(canonical_bus, canonical_mode))
        return SerialModeState(bus=canonical_bus, mode=canonical_mode)

    def query_mode(self, bus: int) -> SerialModeState:
        canonical_bus = validate_serial_bus(bus, self.capabilities)
        raw = self.scpi.query(serial_mode_query(canonical_bus)).strip()
        return SerialModeState(
            bus=canonical_bus,
            mode=parse_serial_mode(raw),
            raw_mode=raw,
        )

    def configure_display(self, bus: int, enabled: bool) -> SerialDisplayState:
        canonical_bus = validate_serial_bus(bus, self.capabilities)
        self.scpi.write(serial_display_command(canonical_bus, enabled))
        return SerialDisplayState(bus=canonical_bus, enabled=enabled)

    def query_display(self, bus: int) -> SerialDisplayState:
        canonical_bus = validate_serial_bus(bus, self.capabilities)
        raw = self.scpi.query(serial_display_query(canonical_bus)).strip()
        try:
            enabled = parse_display_label(raw)
        except ChannelResponseError as exc:
            raise SerialResponseError(
                f"Could not parse serial display response: {raw!r}"
            ) from exc
        return SerialDisplayState(
            bus=canonical_bus,
            enabled=enabled,
            raw_state=raw,
        )

    def query_lister(self) -> SerialListerState:
        require_serial_decode(self.capabilities)
        commands = serial_lister_query_commands()
        raw_display = self.scpi.query(commands["display"])
        display = parse_serial_lister_display(raw_display)
        if display == "bus2" and self.capabilities.serial_bus_count < 2:
            raise SerialResponseError(
                f"Lister display response selected bus2, but the selected "
                f"{self.capabilities.series} model has only one serial bus."
            )
        raw_reference = self.scpi.query(commands["reference"])
        reference = parse_serial_lister_reference(raw_reference)
        return SerialListerState(
            display=display,
            reference=reference,
            raw_display=raw_display,
            raw_reference=raw_reference,
        )

    def configure_lister_display(self, display: str) -> SerialListerDisplayState:
        canonical = validate_serial_lister_display(display, self.capabilities)
        self.scpi.write(serial_lister_display_command(canonical))
        return SerialListerDisplayState(display=canonical)

    def query_lister_display(self) -> SerialListerDisplayState:
        require_serial_decode(self.capabilities)
        raw = self.scpi.query(serial_lister_display_query())
        display = parse_serial_lister_display(raw)
        if display == "bus2" and self.capabilities.serial_bus_count < 2:
            raise SerialResponseError(
                f"Lister display response selected bus2, but the selected "
                f"{self.capabilities.series} model has only one serial bus."
            )
        return SerialListerDisplayState(display=display, raw_display=raw)

    def configure_lister_reference(self, reference: str) -> SerialListerReferenceState:
        canonical = validate_serial_lister_reference(reference, self.capabilities)
        self.scpi.write(serial_lister_reference_command(canonical))
        return SerialListerReferenceState(reference=canonical)

    def query_lister_reference(self) -> SerialListerReferenceState:
        require_serial_decode(self.capabilities)
        raw = self.scpi.query(serial_lister_reference_query())
        return SerialListerReferenceState(
            reference=parse_serial_lister_reference(raw),
            raw_reference=raw,
        )

    def query_lister_data(self) -> bytes:
        require_serial_decode(self.capabilities)
        return parse_serial_lister_binary_block(
            self.scpi.query_binary_bytes(serial_lister_data_query())
        )

    def configure_uart(
        self,
        bus: int,
        *,
        rx_source: str | None = None,
        tx_source: str | None = None,
        baud_rate: int | None = None,
        data_bits: int | None = None,
        parity: str | None = None,
        polarity: str | None = None,
        bit_order: str | None = None,
    ) -> SerialUartState:
        canonical_bus = validate_serial_bus(bus, self.capabilities)
        validate_serial_mode("uart", self.capabilities)
        values = _normalize_uart_values(
            self.capabilities,
            rx_source=rx_source,
            tx_source=tx_source,
            baud_rate=baud_rate,
            data_bits=data_bits,
            parity=parity,
            polarity=polarity,
            bit_order=bit_order,
        )
        if not any(value is not None for value in values.values()):
            raise ParameterValidationError("serial-uart configure requires at least one setting.")
        self.scpi.write(serial_mode_command(canonical_bus, "uart"))
        for command in serial_uart_configure_commands(canonical_bus, values):
            self.scpi.write(command)
        return SerialUartState(bus=canonical_bus, mode="uart", **values)

    def query_uart(self, bus: int) -> SerialUartState:
        canonical_bus, raw_mode = self._query_protocol_mode(bus, "uart")
        commands = serial_uart_query_commands(canonical_bus)
        raw_rx_source = self.scpi.query(commands["rx_source"]).strip()
        rx_source = parse_serial_source(raw_rx_source, self.capabilities)
        raw_tx_source = self.scpi.query(commands["tx_source"]).strip()
        tx_source = parse_serial_source(raw_tx_source, self.capabilities)
        raw_baud_rate = self.scpi.query(commands["baud_rate"]).strip()
        baud_rate = _parse_serial_int_validated(
            raw_baud_rate,
            "UART baud rate",
            lambda value: validate_uart_baud_rate(value, self.capabilities),
        )
        raw_data_bits = self.scpi.query(commands["data_bits"]).strip()
        data_bits = _parse_serial_int_validated(
            raw_data_bits,
            "UART data bits",
            lambda value: _validate_int(value, "UART data bits", 5, 9),
        )
        raw_parity = self.scpi.query(commands["parity"]).strip()
        parity = parse_uart_parity(raw_parity)
        raw_polarity = self.scpi.query(commands["polarity"]).strip()
        polarity = parse_uart_polarity(raw_polarity)
        raw_bit_order = self.scpi.query(commands["bit_order"]).strip()
        bit_order = parse_serial_bit_order(raw_bit_order)
        return SerialUartState(
            bus=canonical_bus,
            mode="uart",
            raw_mode=raw_mode,
            rx_source=rx_source,
            raw_rx_source=raw_rx_source,
            tx_source=tx_source,
            raw_tx_source=raw_tx_source,
            baud_rate=baud_rate,
            raw_baud_rate=raw_baud_rate,
            data_bits=data_bits,
            raw_data_bits=raw_data_bits,
            parity=parity,
            raw_parity=raw_parity,
            polarity=polarity,
            raw_polarity=raw_polarity,
            bit_order=bit_order,
            raw_bit_order=raw_bit_order,
        )

    def configure_uart_trigger(
        self,
        bus: int,
        *,
        type: str | None = None,
        data: int | None = None,
        qualifier: str | None = None,
    ) -> SerialUartTriggerState:
        canonical_bus, canonical_type, canonical_data, canonical_qualifier = (
            validate_serial_uart_trigger_request(
                bus,
                type=type,
                data=data,
                qualifier=qualifier,
                capabilities=self.capabilities,
            )
        )
        raw_mode = self.scpi.query(serial_mode_query(canonical_bus)).strip()
        mode = parse_serial_mode(raw_mode)
        if mode != "uart":
            raise SerialResponseError(
                f"Serial bus {canonical_bus} is in mode {mode!r}; expected 'uart'."
            )

        for command in serial_uart_trigger_configure_commands(
            canonical_bus,
            canonical_type,
            canonical_data,
            canonical_qualifier,
        ):
            self.scpi.write(command)
        self.scpi.write(trigger_mode_serial_command(canonical_bus))
        return self._query_uart_trigger_state(canonical_bus, raw_mode=raw_mode)

    def query_uart_trigger(self, bus: int) -> SerialUartTriggerState:
        canonical_bus, _, _, _ = validate_serial_uart_trigger_request(
            bus,
            query=True,
            capabilities=self.capabilities,
        )
        raw_mode = self.scpi.query(serial_mode_query(canonical_bus)).strip()
        return self._query_uart_trigger_state(canonical_bus, raw_mode=raw_mode)

    def _query_uart_trigger_state(
        self, bus: int, *, raw_mode: str
    ) -> SerialUartTriggerState:
        mode = parse_serial_mode(raw_mode)
        raw_trigger_mode = self.scpi.query(trigger_mode_query()).strip()
        trigger_mode = parse_trigger_mode(raw_trigger_mode)
        selected = mode == "uart" and trigger_mode == f"serial{bus}"
        if mode != "uart":
            return SerialUartTriggerState(
                protocol="uart",
                bus=bus,
                mode=mode,
                raw_mode=raw_mode,
                selected=selected,
                trigger_mode=trigger_mode,
                raw_trigger_mode=raw_trigger_mode,
                type=None,
                raw_type=None,
                data=None,
                raw_data=None,
                qualifier=None,
                raw_qualifier=None,
            )

        raw_type = self.scpi.query(serial_uart_trigger_type_query(bus)).strip()
        trigger_type = parse_serial_uart_trigger_type(raw_type)
        raw_data = None
        data = None
        raw_qualifier = None
        qualifier = None
        if trigger_type in {"rx-data", "tx-data"}:
            raw_data = self.scpi.query(serial_uart_trigger_data_query(bus)).strip()
            data = parse_serial_uart_trigger_data(raw_data)
            raw_qualifier = self.scpi.query(
                serial_uart_trigger_qualifier_query(bus)
            ).strip()
            qualifier = parse_serial_uart_trigger_qualifier(raw_qualifier)
        return SerialUartTriggerState(
            protocol="uart",
            bus=bus,
            mode=mode,
            raw_mode=raw_mode,
            selected=selected,
            trigger_mode=trigger_mode,
            raw_trigger_mode=raw_trigger_mode,
            type=trigger_type,
            raw_type=raw_type,
            data=data,
            raw_data=raw_data,
            qualifier=qualifier,
            raw_qualifier=raw_qualifier,
        )

    def configure_i2c_trigger(
        self,
        bus: int,
        *,
        type: str | None = None,
        address: int | None = None,
        data: int | None = None,
        data2: int | None = None,
        qualifier: str | None = None,
    ) -> SerialI2CTriggerState:
        canonical_bus, canonical_type, canonical_address, canonical_data, canonical_data2, canonical_qualifier = (
            validate_serial_i2c_trigger_request(
                bus,
                type=type,
                address=address,
                data=data,
                data2=data2,
                qualifier=qualifier,
                capabilities=self.capabilities,
            )
        )
        raw_mode = self.scpi.query(serial_mode_query(canonical_bus)).strip()
        if parse_serial_mode(raw_mode) != "i2c":
            raise SerialResponseError(
                f"Serial bus {canonical_bus} is in mode {parse_serial_mode(raw_mode)!r}; expected 'i2c'."
            )
        for command in serial_i2c_trigger_configure_commands(
            canonical_bus, canonical_type, canonical_address, canonical_data,
            canonical_data2, canonical_qualifier,
        ):
            self.scpi.write(command)
        self.scpi.write(trigger_mode_serial_command(canonical_bus))
        return self._query_i2c_trigger_state(canonical_bus, raw_mode=raw_mode)

    def query_i2c_trigger(self, bus: int) -> SerialI2CTriggerState:
        canonical_bus, _, _, _, _, _ = validate_serial_i2c_trigger_request(
            bus, query=True, capabilities=self.capabilities
        )
        raw_mode = self.scpi.query(serial_mode_query(canonical_bus)).strip()
        return self._query_i2c_trigger_state(canonical_bus, raw_mode=raw_mode)

    def _query_i2c_trigger_state(
        self, bus: int, *, raw_mode: str
    ) -> SerialI2CTriggerState:
        mode = parse_serial_mode(raw_mode)
        raw_trigger_mode = self.scpi.query(trigger_mode_query()).strip()
        trigger_mode = parse_trigger_mode(raw_trigger_mode)
        selected = mode == "i2c" and trigger_mode == f"serial{bus}"
        empty = dict(
            type=None, raw_type=None, address=None, raw_address=None,
            data=None, raw_data=None, data2=None, raw_data2=None,
            qualifier=None, raw_qualifier=None,
        )
        if mode != "i2c":
            return SerialI2CTriggerState(
                protocol="i2c", bus=bus, mode=mode, raw_mode=raw_mode,
                selected=selected, trigger_mode=trigger_mode,
                raw_trigger_mode=raw_trigger_mode, **empty,
            )
        raw_type = self.scpi.query(serial_i2c_trigger_type_query(bus)).strip()
        trigger_type = parse_serial_i2c_trigger_type(raw_type)
        raw_address = raw_data = raw_data2 = raw_qualifier = None
        address = data = data2 = qualifier = None
        if trigger_type in {
            "address-no-ack", "read7", "write7", "write10",
            "read7-data2", "write7-data2", "read-eeprom",
        }:
            raw_address = self.scpi.query(serial_i2c_trigger_address_query(bus)).strip()
            address = parse_serial_i2c_trigger_address(raw_address, trigger_type)
        if trigger_type in {"read7", "write7", "write10", "read7-data2", "write7-data2", "read-eeprom"}:
            raw_data = self.scpi.query(serial_i2c_trigger_data_query(bus)).strip()
            data = parse_serial_i2c_trigger_data(raw_data)
        if trigger_type in {"read7-data2", "write7-data2"}:
            raw_data2 = self.scpi.query(serial_i2c_trigger_data2_query(bus)).strip()
            data2 = parse_serial_i2c_trigger_data(raw_data2, "I2C trigger data2")
        if trigger_type == "read-eeprom":
            raw_qualifier = self.scpi.query(serial_i2c_trigger_qualifier_query(bus)).strip()
            qualifier = parse_serial_i2c_trigger_qualifier(raw_qualifier)
        return SerialI2CTriggerState(
            protocol="i2c", bus=bus, mode=mode, raw_mode=raw_mode,
            selected=selected, trigger_mode=trigger_mode,
            raw_trigger_mode=raw_trigger_mode, type=trigger_type,
            raw_type=raw_type, address=address, raw_address=raw_address,
            data=data, raw_data=raw_data, data2=data2, raw_data2=raw_data2,
            qualifier=qualifier, raw_qualifier=raw_qualifier,
        )

    def configure_spi_trigger(
        self,
        bus: int,
        *,
        type: str | None = None,
        width: int | None = None,
        data: str | None = None,
    ) -> SerialSpiTriggerState:
        canonical_bus, canonical_type, canonical_width, canonical_data = (
            validate_serial_spi_trigger_request(
                bus, type=type, width=width, data=data,
                capabilities=self.capabilities,
            )
        )
        raw_mode = self.scpi.query(serial_mode_query(canonical_bus)).strip()
        if parse_serial_mode(raw_mode) != "spi":
            raise SerialResponseError(
                f"Serial bus {canonical_bus} is in mode {parse_serial_mode(raw_mode)!r}; expected 'spi'."
            )
        for command in serial_spi_trigger_configure_commands(
            canonical_bus, canonical_type, canonical_width, canonical_data
        ):
            self.scpi.write(command)
        self.scpi.write(trigger_mode_serial_command(canonical_bus))
        return self._query_spi_trigger_state(canonical_bus, raw_mode=raw_mode)

    def query_spi_trigger(self, bus: int) -> SerialSpiTriggerState:
        canonical_bus, _, _, _ = validate_serial_spi_trigger_request(
            bus, query=True, capabilities=self.capabilities
        )
        raw_mode = self.scpi.query(serial_mode_query(canonical_bus)).strip()
        return self._query_spi_trigger_state(canonical_bus, raw_mode=raw_mode)

    def _query_spi_trigger_state(
        self, bus: int, *, raw_mode: str
    ) -> SerialSpiTriggerState:
        mode = parse_serial_mode(raw_mode)
        raw_trigger_mode = self.scpi.query(trigger_mode_query()).strip()
        trigger_mode = parse_trigger_mode(raw_trigger_mode)
        selected = mode == "spi" and trigger_mode == f"serial{bus}"
        if mode != "spi":
            return SerialSpiTriggerState(
                protocol="spi", bus=bus, mode=mode, raw_mode=raw_mode,
                selected=selected, trigger_mode=trigger_mode,
                raw_trigger_mode=raw_trigger_mode, type=None, raw_type=None,
                width=None, raw_width=None, data=None, raw_data=None,
            )
        raw_type = self.scpi.query(serial_spi_trigger_type_query(bus)).strip()
        trigger_type = parse_serial_spi_trigger_type(raw_type)
        raw_width = self.scpi.query(serial_spi_trigger_width_query(bus, trigger_type)).strip()
        width = parse_serial_spi_trigger_width(raw_width)
        raw_data = self.scpi.query(serial_spi_trigger_data_query(bus, trigger_type)).strip()
        data = parse_serial_trigger_pattern(
            raw_data, "SPI trigger data", max_bits=width
        )
        return SerialSpiTriggerState(
            protocol="spi", bus=bus, mode=mode, raw_mode=raw_mode,
            selected=selected, trigger_mode=trigger_mode,
            raw_trigger_mode=raw_trigger_mode, type=trigger_type,
            raw_type=raw_type, width=width, raw_width=raw_width,
            data=data, raw_data=raw_data,
        )

    def configure_can_trigger(
        self,
        bus: int,
        *,
        type: str | None = None,
        id: str | None = None,
        id_mode: str | None = None,
        data: str | None = None,
        data_length: int | None = None,
    ) -> SerialCanTriggerState:
        canonical_bus, canonical_type, canonical_id, canonical_id_mode, canonical_data, canonical_length = (
            validate_serial_can_trigger_request(
                bus, type=type, id=id, id_mode=id_mode, data=data,
                data_length=data_length, capabilities=self.capabilities,
            )
        )
        raw_mode = self.scpi.query(serial_mode_query(canonical_bus)).strip()
        if parse_serial_mode(raw_mode) != "can":
            raise SerialResponseError(
                f"Serial bus {canonical_bus} is in mode {parse_serial_mode(raw_mode)!r}; expected 'can'."
            )
        for command in serial_can_trigger_configure_commands(
            canonical_bus, canonical_type, canonical_id, canonical_id_mode,
            canonical_data, canonical_length,
        ):
            self.scpi.write(command)
        self.scpi.write(trigger_mode_serial_command(canonical_bus))
        return self._query_can_trigger_state(canonical_bus, raw_mode=raw_mode)

    def query_can_trigger(self, bus: int) -> SerialCanTriggerState:
        canonical_bus, _, _, _, _, _ = validate_serial_can_trigger_request(
            bus, query=True, capabilities=self.capabilities
        )
        raw_mode = self.scpi.query(serial_mode_query(canonical_bus)).strip()
        return self._query_can_trigger_state(canonical_bus, raw_mode=raw_mode)

    def _query_can_trigger_state(
        self, bus: int, *, raw_mode: str
    ) -> SerialCanTriggerState:
        mode = parse_serial_mode(raw_mode)
        raw_trigger_mode = self.scpi.query(trigger_mode_query()).strip()
        trigger_mode = parse_trigger_mode(raw_trigger_mode)
        selected = mode == "can" and trigger_mode == f"serial{bus}"
        if mode != "can":
            return SerialCanTriggerState(
                protocol="can", bus=bus, mode=mode, raw_mode=raw_mode,
                selected=selected, trigger_mode=trigger_mode,
                raw_trigger_mode=raw_trigger_mode, type=None, raw_type=None,
                id=None, raw_id=None, id_mode=None, raw_id_mode=None,
                data=None, raw_data=None, data_length=None, raw_data_length=None,
            )
        raw_type = self.scpi.query(serial_can_trigger_type_query(bus)).strip()
        trigger_type = parse_serial_can_trigger_type(raw_type)
        raw_id = raw_id_mode = raw_data = raw_length = None
        id_value = id_mode = data = data_length = None
        if trigger_type in {"data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data"}:
            raw_id_mode = self.scpi.query(serial_can_trigger_id_mode_query(bus)).strip()
            id_mode = parse_serial_can_trigger_id_mode(raw_id_mode)
            raw_id = self.scpi.query(serial_can_trigger_id_query(bus)).strip()
            id_value = parse_serial_trigger_pattern(
                raw_id, "CAN trigger ID", max_bits=29
            )
        if trigger_type == "id-and-data":
            raw_length = self.scpi.query(serial_can_trigger_data_length_query(bus)).strip()
            data_length = parse_serial_can_trigger_data_length(raw_length)
            raw_data = self.scpi.query(serial_can_trigger_data_query(bus)).strip()
            data = parse_serial_trigger_pattern(
                raw_data, "CAN trigger data", max_bits=64
            )
        return SerialCanTriggerState(
            protocol="can", bus=bus, mode=mode, raw_mode=raw_mode,
            selected=selected, trigger_mode=trigger_mode,
            raw_trigger_mode=raw_trigger_mode, type=trigger_type,
            raw_type=raw_type, id=id_value, raw_id=raw_id,
            id_mode=id_mode, raw_id_mode=raw_id_mode, data=data,
            raw_data=raw_data, data_length=data_length,
            raw_data_length=raw_length,
        )

    def configure_i2c(
        self,
        bus: int,
        *,
        clock_source: str | None = None,
        data_source: str | None = None,
        address_size: str | None = None,
    ) -> SerialI2CState:
        canonical_bus = validate_serial_bus(bus, self.capabilities)
        validate_serial_mode("i2c", self.capabilities)
        values = _normalize_i2c_values(
            self.capabilities,
            clock_source=clock_source,
            data_source=data_source,
            address_size=address_size,
        )
        if not any(value is not None for value in values.values()):
            raise ParameterValidationError("serial-i2c configure requires at least one setting.")
        self.scpi.write(serial_mode_command(canonical_bus, "i2c"))
        for command in serial_i2c_configure_commands(canonical_bus, values):
            self.scpi.write(command)
        return SerialI2CState(bus=canonical_bus, mode="i2c", **values)

    def query_i2c(self, bus: int) -> SerialI2CState:
        canonical_bus, raw_mode = self._query_protocol_mode(bus, "i2c")
        commands = serial_i2c_query_commands(canonical_bus)
        raw_clock_source = self.scpi.query(commands["clock_source"]).strip()
        clock_source = parse_serial_source(raw_clock_source, self.capabilities)
        raw_data_source = self.scpi.query(commands["data_source"]).strip()
        data_source = parse_serial_source(raw_data_source, self.capabilities)
        raw_address_size = self.scpi.query(commands["address_size"]).strip()
        address_size = parse_i2c_address_size(raw_address_size)
        return SerialI2CState(
            bus=canonical_bus,
            mode="i2c",
            raw_mode=raw_mode,
            clock_source=clock_source,
            raw_clock_source=raw_clock_source,
            data_source=data_source,
            raw_data_source=raw_data_source,
            address_size=address_size,
            raw_address_size=raw_address_size,
        )

    def configure_spi(
        self,
        bus: int,
        *,
        clock_source: str | None = None,
        mosi_source: str | None = None,
        miso_source: str | None = None,
        frame_source: str | None = None,
        clock_slope: str | None = None,
        bit_order: str | None = None,
        word_width: int | None = None,
        framing: str | None = None,
        clock_timeout: float | None = None,
    ) -> SerialSpiState:
        canonical_bus = validate_serial_bus(bus, self.capabilities)
        validate_serial_mode("spi", self.capabilities)
        values = _normalize_spi_values(
            self.capabilities,
            clock_source=clock_source,
            mosi_source=mosi_source,
            miso_source=miso_source,
            frame_source=frame_source,
            clock_slope=clock_slope,
            bit_order=bit_order,
            word_width=word_width,
            framing=framing,
            clock_timeout=clock_timeout,
        )
        if not any(value is not None for value in values.values()):
            raise ParameterValidationError("serial-spi configure requires at least one setting.")
        self.scpi.write(serial_mode_command(canonical_bus, "spi"))
        for command in serial_spi_configure_commands(canonical_bus, values):
            self.scpi.write(command)
        return SerialSpiState(bus=canonical_bus, mode="spi", **values)

    def query_spi(self, bus: int) -> SerialSpiState:
        canonical_bus, raw_mode = self._query_protocol_mode(bus, "spi")
        commands = serial_spi_query_commands(canonical_bus)
        raw_clock_source = self.scpi.query(commands["clock_source"]).strip()
        clock_source = parse_serial_source(raw_clock_source, self.capabilities)
        raw_frame_source = self.scpi.query(commands["frame_source"]).strip()
        frame_source = parse_serial_source(raw_frame_source, self.capabilities)
        raw_mosi_source = self.scpi.query(commands["mosi_source"]).strip()
        mosi_source = parse_serial_source(raw_mosi_source, self.capabilities)
        raw_miso_source = self.scpi.query(commands["miso_source"]).strip()
        miso_source = parse_serial_source(raw_miso_source, self.capabilities)
        raw_clock_slope = self.scpi.query(commands["clock_slope"]).strip()
        clock_slope = parse_spi_clock_slope(raw_clock_slope)
        raw_bit_order = self.scpi.query(commands["bit_order"]).strip()
        bit_order = parse_serial_bit_order(raw_bit_order)
        raw_word_width = self.scpi.query(commands["word_width"]).strip()
        word_width = _parse_serial_int_validated(
            raw_word_width,
            "SPI word width",
            lambda value: _validate_int(value, "SPI word width", 4, 16),
        )
        raw_framing = self.scpi.query(commands["framing"]).strip()
        framing = parse_spi_framing(raw_framing)
        raw_clock_timeout = self.scpi.query(commands["clock_timeout"]).strip()
        clock_timeout = _parse_serial_float_validated(
            raw_clock_timeout,
            "SPI clock timeout",
            lambda value: _validate_float(value, "SPI clock timeout", 1e-7, 10.0),
        )
        return SerialSpiState(
            bus=canonical_bus,
            mode="spi",
            raw_mode=raw_mode,
            clock_source=clock_source,
            raw_clock_source=raw_clock_source,
            mosi_source=mosi_source,
            raw_mosi_source=raw_mosi_source,
            miso_source=miso_source,
            raw_miso_source=raw_miso_source,
            frame_source=frame_source,
            raw_frame_source=raw_frame_source,
            clock_slope=clock_slope,
            raw_clock_slope=raw_clock_slope,
            bit_order=bit_order,
            raw_bit_order=raw_bit_order,
            word_width=word_width,
            raw_word_width=raw_word_width,
            framing=framing,
            raw_framing=raw_framing,
            clock_timeout=clock_timeout,
            raw_clock_timeout=raw_clock_timeout,
        )

    def configure_can(
        self,
        bus: int,
        *,
        source: str | None = None,
        baud_rate: int | None = None,
        signal_definition: str | None = None,
        sample_point: float | None = None,
    ) -> SerialCanState:
        canonical_bus = validate_serial_bus(bus, self.capabilities)
        validate_serial_mode("can", self.capabilities)
        values = _normalize_can_values(
            self.capabilities,
            source=source,
            baud_rate=baud_rate,
            signal_definition=signal_definition,
            sample_point=sample_point,
        )
        if not any(value is not None for value in values.values()):
            raise ParameterValidationError("serial-can configure requires at least one setting.")
        self.scpi.write(serial_mode_command(canonical_bus, "can"))
        for command in serial_can_configure_commands(canonical_bus, values):
            self.scpi.write(command)
        return SerialCanState(bus=canonical_bus, mode="can", **values)

    def query_can(self, bus: int) -> SerialCanState:
        canonical_bus, raw_mode = self._query_protocol_mode(bus, "can")
        commands = serial_can_query_commands(canonical_bus)
        raw_source = self.scpi.query(commands["source"]).strip()
        source = parse_serial_source(raw_source, self.capabilities)
        raw_baud_rate = self.scpi.query(commands["baud_rate"]).strip()
        baud_rate = _parse_serial_int_validated(
            raw_baud_rate,
            "CAN baud rate",
            validate_can_baud_rate,
        )
        raw_signal_definition = self.scpi.query(commands["signal_definition"]).strip()
        signal_definition = parse_can_signal_definition(raw_signal_definition)
        raw_sample_point = self.scpi.query(commands["sample_point"]).strip()
        sample_point = _parse_serial_float_validated(
            raw_sample_point,
            "CAN sample point",
            lambda value: validate_can_sample_point(value, self.capabilities),
        )
        return SerialCanState(
            bus=canonical_bus,
            mode="can",
            raw_mode=raw_mode,
            source=source,
            raw_source=raw_source,
            baud_rate=baud_rate,
            raw_baud_rate=raw_baud_rate,
            signal_definition=signal_definition,
            raw_signal_definition=raw_signal_definition,
            sample_point=sample_point,
            raw_sample_point=raw_sample_point,
        )

    def _query_protocol_mode(self, bus: int, expected: str) -> tuple[int, str]:
        canonical_bus = validate_serial_bus(bus, self.capabilities)
        raw_mode = self.scpi.query(serial_mode_query(canonical_bus)).strip()
        actual = parse_serial_mode(raw_mode)
        if actual != expected:
            raise SerialResponseError(
                f"Serial bus {canonical_bus} is in mode {actual!r}; expected {expected!r}."
            )
        return canonical_bus, raw_mode


def serial_uart_configure_commands(bus: int, values: dict[str, object]) -> list[str]:
    bus = _validate_positive_bus(bus)
    commands: list[str] = []
    if values.get("rx_source") is not None:
        commands.append(f":SBUS{bus}:UART:SOURce:RX {_serial_source_token(values['rx_source'])}")
    if values.get("tx_source") is not None:
        commands.append(f":SBUS{bus}:UART:SOURce:TX {_serial_source_token(values['tx_source'])}")
    if values.get("baud_rate") is not None:
        commands.append(f":SBUS{bus}:UART:BAUDrate {values['baud_rate']}")
    if values.get("data_bits") is not None:
        commands.append(f":SBUS{bus}:UART:WIDTh {values['data_bits']}")
    if values.get("parity") is not None:
        commands.append(f":SBUS{bus}:UART:PARity {_UART_PARITY_TOKENS[values['parity']]}")
    if values.get("polarity") is not None:
        commands.append(f":SBUS{bus}:UART:POLarity {_UART_POLARITY_TOKENS[values['polarity']]}")
    if values.get("bit_order") is not None:
        commands.append(f":SBUS{bus}:UART:BITorder {_BIT_ORDER_TOKENS[values['bit_order']]}")
    return commands


def serial_uart_query_commands(bus: int) -> dict[str, str]:
    bus = _validate_positive_bus(bus)
    root = f":SBUS{bus}:UART:"
    return {
        "rx_source": root + "SOURce:RX?",
        "tx_source": root + "SOURce:TX?",
        "baud_rate": root + "BAUDrate?",
        "data_bits": root + "WIDTh?",
        "parity": root + "PARity?",
        "polarity": root + "POLarity?",
        "bit_order": root + "BITorder?",
    }


def serial_i2c_configure_commands(bus: int, values: dict[str, object]) -> list[str]:
    bus = _validate_positive_bus(bus)
    commands: list[str] = []
    if values.get("clock_source") is not None:
        commands.append(f":SBUS{bus}:IIC:SOURce:CLOCk {_serial_source_token(values['clock_source'])}")
    if values.get("data_source") is not None:
        commands.append(f":SBUS{bus}:IIC:SOURce:DATA {_serial_source_token(values['data_source'])}")
    if values.get("address_size") is not None:
        commands.append(f":SBUS{bus}:IIC:ASIZe {_I2C_ADDRESS_SIZE_TOKENS[values['address_size']]}")
    return commands


def serial_i2c_query_commands(bus: int) -> dict[str, str]:
    bus = _validate_positive_bus(bus)
    root = f":SBUS{bus}:IIC:"
    return {
        "clock_source": root + "SOURce:CLOCk?",
        "data_source": root + "SOURce:DATA?",
        "address_size": root + "ASIZe?",
    }


def serial_spi_configure_commands(bus: int, values: dict[str, object]) -> list[str]:
    bus = _validate_positive_bus(bus)
    commands: list[str] = []
    source_fields = (
        ("clock_source", "CLOCk"),
        ("frame_source", "FRAMe"),
        ("mosi_source", "MOSI"),
        ("miso_source", "MISO"),
    )
    for field, token in source_fields:
        if values.get(field) is not None:
            commands.append(
                f":SBUS{bus}:SPI:SOURce:{token} {_serial_source_token(values[field])}"
            )
    if values.get("clock_slope") is not None:
        commands.append(f":SBUS{bus}:SPI:CLOCk:SLOPe {_SPI_SLOPE_TOKENS[values['clock_slope']]}")
    if values.get("bit_order") is not None:
        commands.append(f":SBUS{bus}:SPI:BITorder {_BIT_ORDER_TOKENS[values['bit_order']]}")
    if values.get("word_width") is not None:
        commands.append(f":SBUS{bus}:SPI:WIDTh {values['word_width']}")
    if values.get("framing") is not None:
        commands.append(f":SBUS{bus}:SPI:FRAMing {_SPI_FRAMING_TOKENS[values['framing']]}")
    if values.get("clock_timeout") is not None:
        commands.append(f":SBUS{bus}:SPI:CLOCk:TIMeout {_format_serial_number(values['clock_timeout'])}")
    return commands


def serial_spi_query_commands(bus: int) -> dict[str, str]:
    bus = _validate_positive_bus(bus)
    root = f":SBUS{bus}:SPI:"
    return {
        "clock_source": root + "SOURce:CLOCk?",
        "frame_source": root + "SOURce:FRAMe?",
        "mosi_source": root + "SOURce:MOSI?",
        "miso_source": root + "SOURce:MISO?",
        "clock_slope": root + "CLOCk:SLOPe?",
        "bit_order": root + "BITorder?",
        "word_width": root + "WIDTh?",
        "framing": root + "FRAMing?",
        "clock_timeout": root + "CLOCk:TIMeout?",
    }


def serial_can_configure_commands(bus: int, values: dict[str, object]) -> list[str]:
    bus = _validate_positive_bus(bus)
    commands: list[str] = []
    if values.get("source") is not None:
        commands.append(f":SBUS{bus}:CAN:SOURce {_serial_source_token(values['source'])}")
    if values.get("baud_rate") is not None:
        commands.append(f":SBUS{bus}:CAN:SIGNal:BAUDrate {values['baud_rate']}")
    if values.get("signal_definition") is not None:
        commands.append(
            f":SBUS{bus}:CAN:SIGNal:DEFinition {_CAN_SIGNAL_TOKENS[values['signal_definition']]}"
        )
    if values.get("sample_point") is not None:
        commands.append(f":SBUS{bus}:CAN:SAMPlepoint {_format_serial_number(values['sample_point'])}")
    return commands


def serial_can_query_commands(bus: int) -> dict[str, str]:
    bus = _validate_positive_bus(bus)
    root = f":SBUS{bus}:CAN:"
    return {
        "source": root + "SOURce?",
        "baud_rate": root + "SIGNal:BAUDrate?",
        "signal_definition": root + "SIGNal:DEFinition?",
        "sample_point": root + "SAMPlepoint?",
    }


def serial_lister_display_command(display: str) -> str:
    canonical = normalize_serial_lister_display(display)
    return f":LISTer:DISPlay {_SERIAL_LISTER_DISPLAY_TOKENS[canonical]}"


def serial_lister_display_query() -> str:
    return ":LISTer:DISPlay?"


def serial_lister_reference_command(reference: str) -> str:
    canonical = normalize_serial_lister_reference(reference)
    return f":LISTer:REFerence {_SERIAL_LISTER_REFERENCE_TOKENS[canonical]}"


def serial_lister_reference_query() -> str:
    return ":LISTer:REFerence?"


def serial_lister_query_commands() -> dict[str, str]:
    return {
        "display": serial_lister_display_query(),
        "reference": serial_lister_reference_query(),
    }


def serial_lister_data_query() -> str:
    return ":LISTer:DATA?"


def normalize_serial_lister_display(value: str) -> str:
    return _normalize_choice(value, SERIAL_LISTER_DISPLAYS, "Lister display")


def validate_serial_lister_display(
    value: str, capabilities: ScopeCapabilities
) -> str:
    require_serial_decode(capabilities)
    canonical = normalize_serial_lister_display(value)
    if canonical == "bus2" and capabilities.serial_bus_count < 2:
        raise ParameterValidationError(
            f"Lister display bus2 is not supported by the selected "
            f"{capabilities.series} model profile."
        )
    return canonical


def parse_serial_lister_display(raw: str) -> str:
    normalized = raw.strip().upper()
    readbacks = {
        "OFF": "off",
        "0": "off",
        "SBUS1": "bus1",
        "ON": "bus1",
        "1": "bus1",
        "SBUS2": "bus2",
        "2": "bus2",
        "ALL": "all",
    }
    try:
        return readbacks[normalized]
    except KeyError as exc:
        raise SerialResponseError(
            f"Could not parse Lister display response: {raw!r}"
        ) from exc


def normalize_serial_lister_reference(value: str) -> str:
    return _normalize_choice(value, SERIAL_LISTER_REFERENCES, "Lister reference")


def validate_serial_lister_reference(
    value: str, capabilities: ScopeCapabilities
) -> str:
    require_serial_decode(capabilities)
    return normalize_serial_lister_reference(value)


def parse_serial_lister_reference(raw: str) -> str:
    normalized = raw.strip().upper()
    readbacks = {
        "TRIGGER": "trigger",
        "TRIG": "trigger",
        "PREVIOUS": "previous",
        "PREV": "previous",
    }
    try:
        return readbacks[normalized]
    except KeyError as exc:
        raise SerialResponseError(
            f"Could not parse Lister reference response: {raw!r}"
        ) from exc


def parse_serial_lister_binary_block(raw: bytes) -> bytes:
    if len(raw) < 3 or raw[:1] != b"#" or not raw[1:2].isdigit():
        raise SerialResponseError("Malformed Lister binary block header.")
    length_digits = raw[1] - ord("0")
    if length_digits == 0:
        raise SerialResponseError("Indefinite-length Lister binary blocks are unsupported.")
    header_end = 2 + length_digits
    if len(raw) < header_end:
        raise SerialResponseError("Malformed Lister binary block length header.")
    length_bytes = raw[2:header_end]
    if not length_bytes.isdigit():
        raise SerialResponseError("Malformed Lister binary block length.")
    payload_length = int(length_bytes)
    payload_end = header_end + payload_length
    if len(raw) < payload_end:
        raise SerialResponseError("Truncated Lister binary block payload.")
    payload = raw[header_end:payload_end]
    trailing = raw[payload_end:]
    if trailing not in {b"", b"\n", b"\r\n"}:
        raise SerialResponseError("Malformed Lister binary block terminator.")
    return payload


def normalize_serial_source(value: str, capabilities: ScopeCapabilities) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError("Serial source must be channelN or external.")
    if value == "external":
        return value
    match = re.fullmatch(r"channel([1-9]\d*)", value)
    if match is None:
        raise ParameterValidationError(
            "Serial source must be channel1 through channelN or external."
        )
    channel = int(match.group(1))
    if channel < 1 or channel > capabilities.analog_channels:
        raise ParameterValidationError(
            f"Serial source channel{channel} is not supported by the selected "
            f"{capabilities.series} model profile; expected channel1 through "
            f"channel{capabilities.analog_channels} or external."
        )
    return f"channel{channel}"


def parse_serial_source(raw: str, capabilities: ScopeCapabilities) -> str:
    normalized = raw.strip().upper()
    if normalized in {"EXT", "EXTERNAL"}:
        return "external"
    match = re.fullmatch(r"CHAN(?:NEL)?(\d+)", normalized)
    if match is not None:
        try:
            return normalize_serial_source(f"channel{match.group(1)}", capabilities)
        except ParameterValidationError as exc:
            raise SerialResponseError(
                f"Could not parse serial source response: {raw!r}"
            ) from exc
    raise SerialResponseError(f"Could not parse serial source response: {raw!r}")


def _serial_source_token(value: object) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError("Serial source must be normalized before command generation.")
    if value == "external":
        return "EXTernal"
    return f"CHANnel{value.removeprefix('channel')}"


def normalize_uart_parity(value: str) -> str:
    return _normalize_choice(value, UART_PARITIES, "UART parity")


def parse_uart_parity(raw: str) -> str:
    return _parse_choice(raw, {token: canonical for canonical, token in _UART_PARITY_TOKENS.items()}, "UART parity")


def normalize_uart_polarity(value: str) -> str:
    return _normalize_choice(value, UART_POLARITIES, "UART polarity")


def parse_uart_polarity(raw: str) -> str:
    return _parse_choice(raw, {token: canonical for canonical, token in _UART_POLARITY_TOKENS.items()}, "UART polarity")


def normalize_serial_bit_order(value: str) -> str:
    return _normalize_choice(value, SERIAL_BIT_ORDERS, "serial bit order")


def parse_serial_bit_order(raw: str) -> str:
    readbacks = {"LSBF": "lsb-first", "LSBFIRST": "lsb-first", "MSBF": "msb-first", "MSBFIRST": "msb-first"}
    return _parse_choice(raw, readbacks, "serial bit order")


def normalize_i2c_address_size(value: str) -> str:
    return _normalize_choice(value, I2C_ADDRESS_SIZES, "I2C address size")


def parse_i2c_address_size(raw: str) -> str:
    return _parse_choice(raw, {"BIT7": "bit7", "BIT8": "bit8"}, "I2C address size")


def normalize_spi_clock_slope(value: str) -> str:
    return _normalize_choice(value, SPI_CLOCK_SLOPES, "SPI clock slope")


def parse_spi_clock_slope(raw: str) -> str:
    return _parse_choice(raw, {"POS": "positive", "POSITIVE": "positive", "NEG": "negative", "NEGATIVE": "negative"}, "SPI clock slope")


def normalize_spi_framing(value: str) -> str:
    return _normalize_choice(value, SPI_FRAMINGS, "SPI framing")


def validate_spi_framing_clock_timeout(
    framing: object | None, clock_timeout: object | None
) -> None:
    if clock_timeout is not None and framing != "timeout":
        raise ParameterValidationError(
            "SPI clock timeout is only valid when framing is explicitly set to timeout."
        )


def parse_spi_framing(raw: str) -> str:
    return _parse_choice(raw, {"CHIP": "chip-select", "CHIPSELECT": "chip-select", "NCH": "no-chip-select", "NCHIPSELECT": "no-chip-select", "TIM": "timeout", "TIMEOUT": "timeout"}, "SPI framing")


def normalize_can_signal_definition(value: str) -> str:
    return _normalize_choice(value, CAN_SIGNAL_DEFINITIONS, "CAN signal definition")


def parse_can_signal_definition(raw: str) -> str:
    return _parse_choice(raw, {"CANH": "canh", "CANL": "canl", "RX": "rx", "TX": "tx", "DIFL": "difl", "DIFF": "difl", "DIFFERENTIAL": "difl", "DIFH": "difh"}, "CAN signal definition")


def _normalize_choice(value: str, choices: tuple[str, ...], label: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ParameterValidationError(f"{label} must be one of: {', '.join(choices)}.")
    return value


def _parse_choice(raw: str, readbacks: dict[str, str], label: str) -> str:
    try:
        return readbacks[raw.strip().upper()]
    except KeyError as exc:
        raise SerialResponseError(f"Could not parse {label} response: {raw!r}") from exc


def _serial_source_values(capabilities: ScopeCapabilities, *values: str | None) -> list[str | None]:
    return [None if value is None else normalize_serial_source(value, capabilities) for value in values]


def _normalize_uart_values(capabilities: ScopeCapabilities, **values: object) -> dict[str, object]:
    rx_source, tx_source = _serial_source_values(capabilities, values["rx_source"], values["tx_source"])
    return {
        "rx_source": rx_source,
        "tx_source": tx_source,
        "baud_rate": None if values["baud_rate"] is None else validate_uart_baud_rate(values["baud_rate"], capabilities),
        "data_bits": None if values["data_bits"] is None else _validate_int(values["data_bits"], "UART data bits", 5, 9),
        "parity": None if values["parity"] is None else normalize_uart_parity(values["parity"]),
        "polarity": None if values["polarity"] is None else normalize_uart_polarity(values["polarity"]),
        "bit_order": None if values["bit_order"] is None else normalize_serial_bit_order(values["bit_order"]),
    }


def _normalize_i2c_values(capabilities: ScopeCapabilities, **values: object) -> dict[str, object]:
    clock_source, data_source = _serial_source_values(capabilities, values["clock_source"], values["data_source"])
    return {
        "clock_source": clock_source,
        "data_source": data_source,
        "address_size": None if values["address_size"] is None else normalize_i2c_address_size(values["address_size"]),
    }


def _normalize_spi_values(capabilities: ScopeCapabilities, **values: object) -> dict[str, object]:
    clock_source, mosi_source, miso_source, frame_source = _serial_source_values(
        capabilities,
        values["clock_source"],
        values["mosi_source"],
        values["miso_source"],
        values["frame_source"],
    )
    normalized = {
        "clock_source": clock_source,
        "mosi_source": mosi_source,
        "miso_source": miso_source,
        "frame_source": frame_source,
        "clock_slope": None if values["clock_slope"] is None else normalize_spi_clock_slope(values["clock_slope"]),
        "bit_order": None if values["bit_order"] is None else normalize_serial_bit_order(values["bit_order"]),
        "word_width": None if values["word_width"] is None else _validate_int(values["word_width"], "SPI word width", 4, 16),
        "framing": None if values["framing"] is None else normalize_spi_framing(values["framing"]),
        "clock_timeout": None if values["clock_timeout"] is None else _validate_float(values["clock_timeout"], "SPI clock timeout", 1e-7, 10.0),
    }
    validate_spi_framing_clock_timeout(
        normalized["framing"], normalized["clock_timeout"]
    )
    return normalized


def _normalize_can_values(capabilities: ScopeCapabilities, **values: object) -> dict[str, object]:
    source = _serial_source_values(capabilities, values["source"])[0]
    return {
        "source": source,
        "baud_rate": None if values["baud_rate"] is None else validate_can_baud_rate(values["baud_rate"]),
        "signal_definition": None if values["signal_definition"] is None else normalize_can_signal_definition(values["signal_definition"]),
        "sample_point": None if values["sample_point"] is None else validate_can_sample_point(values["sample_point"], capabilities),
    }


def validate_uart_baud_rate(value: object, capabilities: ScopeCapabilities) -> int:
    baud = _validate_int(value, "UART baud rate", 100, 12_000_000)
    if baud > 8_000_000 and capabilities.series != "4000X":
        raise ParameterValidationError("UART baud rate above 8,000,000 is supported only on 4000X.")
    if baud > 8_000_000 and baud not in {10_000_000, 12_000_000}:
        raise ParameterValidationError("UART baud rate must be 100-8000000, 10000000, or 12000000.")
    return baud


def validate_can_baud_rate(value: object) -> int:
    baud = _validate_int(value, "CAN baud rate", 10_000, 5_000_000)
    if baud == 5_000_000:
        return baud
    if baud % 100 != 0 or baud > 4_000_000:
        raise ParameterValidationError("CAN baud rate must be 10000-4000000 in 100 b/s increments or 5000000.")
    return baud


def validate_can_sample_point(value: object, capabilities: ScopeCapabilities) -> float:
    sample = _validate_float(value, "CAN sample point", 30.0, 90.0)
    if capabilities.series == "4000X":
        return sample
    if sample not in {60.0, 62.5, 68.0, 70.0, 75.0, 80.0, 87.5}:
        raise ParameterValidationError(
            "CAN sample point must be one of 60, 62.5, 68, 70, 75, 80, or 87.5 on 2000X/3000X."
        )
    return sample


def _validate_int(value: object, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ParameterValidationError(f"{label} must be an integer in range {minimum}-{maximum}.")
    return value


def _validate_float(value: object, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParameterValidationError(f"{label} must be a number in range {minimum}-{maximum}.")
    numeric = float(value)
    if not math.isfinite(numeric) or not minimum <= numeric <= maximum:
        raise ParameterValidationError(f"{label} must be a number in range {minimum}-{maximum}.")
    return numeric


def _parse_serial_int(raw: str, label: str) -> int:
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise SerialResponseError(f"Could not parse {label} response: {raw!r}") from exc


def _parse_serial_int_validated(
    raw: str, label: str, validator: Callable[[int], int]
) -> int:
    value = _parse_serial_int(raw, label)
    try:
        return validator(value)
    except ParameterValidationError as exc:
        raise SerialResponseError(f"Invalid {label} response: {raw!r}") from exc


def _parse_serial_float(raw: str, label: str) -> float:
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise SerialResponseError(f"Could not parse {label} response: {raw!r}") from exc
    if not math.isfinite(value):
        raise SerialResponseError(f"Could not parse {label} response: {raw!r}")
    return value


def _parse_serial_float_validated(
    raw: str, label: str, validator: Callable[[float], float]
) -> float:
    value = _parse_serial_float(raw, label)
    try:
        return validator(value)
    except ParameterValidationError as exc:
        raise SerialResponseError(f"Invalid {label} response: {raw!r}") from exc


def _format_serial_number(value: object) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def serial_bus_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}?"


def serial_mode_command(bus: int, mode: str) -> str:
    canonical_mode = normalize_serial_mode(mode)
    return f":SBUS{_validate_positive_bus(bus)}:MODE {SERIAL_MODE_TOKENS[canonical_mode]}"


def serial_mode_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:MODE?"


def serial_uart_trigger_type_command(bus: int, trigger_type: str) -> str:
    canonical_type = normalize_serial_uart_trigger_type(trigger_type)
    return (
        f":SBUS{_validate_positive_bus(bus)}:UART:TRIGger:TYPE "
        f"{_UART_TRIGGER_TYPE_TOKENS[canonical_type]}"
    )


def serial_uart_trigger_type_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:UART:TRIGger:TYPE?"


def serial_uart_trigger_data_command(bus: int, data: int) -> str:
    canonical_data = _validate_int(data, "UART trigger data", 0, 255)
    return f":SBUS{_validate_positive_bus(bus)}:UART:TRIGger:DATA {canonical_data}"


def serial_uart_trigger_data_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:UART:TRIGger:DATA?"


def serial_uart_trigger_qualifier_command(bus: int, qualifier: str) -> str:
    canonical_qualifier = normalize_serial_uart_trigger_qualifier(qualifier)
    return (
        f":SBUS{_validate_positive_bus(bus)}:UART:TRIGger:QUALifier "
        f"{_UART_TRIGGER_QUALIFIER_TOKENS[canonical_qualifier]}"
    )


def serial_uart_trigger_qualifier_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:UART:TRIGger:QUALifier?"


def serial_uart_trigger_configure_commands(
    bus: int,
    trigger_type: str,
    data: int | None,
    qualifier: str | None,
) -> list[str]:
    canonical_type = normalize_serial_uart_trigger_type(trigger_type)
    commands = [serial_uart_trigger_type_command(bus, canonical_type)]
    if canonical_type in {"rx-data", "tx-data"}:
        if data is None or qualifier is None:
            raise ParameterValidationError(
                "UART data trigger requires data and qualifier."
            )
        commands.extend(
            [
                serial_uart_trigger_data_command(bus, data),
                serial_uart_trigger_qualifier_command(bus, qualifier),
            ]
        )
    return commands


def serial_i2c_trigger_type_command(bus: int, trigger_type: str) -> str:
    canonical = normalize_serial_i2c_trigger_type(trigger_type)
    return f":SBUS{_validate_positive_bus(bus)}:IIC:TRIGger:TYPE {_I2C_TRIGGER_TYPE_TOKENS[canonical]}"


def serial_i2c_trigger_type_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:IIC:TRIGger:TYPE?"


def serial_i2c_trigger_address_command(bus: int, address: int, trigger_type: str) -> str:
    canonical = _validate_i2c_trigger_address(address, trigger_type)
    return f":SBUS{_validate_positive_bus(bus)}:IIC:TRIGger:PATTern:ADDRess {canonical}"


def serial_i2c_trigger_address_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:IIC:TRIGger:PATTern:ADDRess?"


def serial_i2c_trigger_data_command(bus: int, data: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:IIC:TRIGger:PATTern:DATA {_validate_int(data, 'I2C trigger data', 0, 255)}"


def serial_i2c_trigger_data_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:IIC:TRIGger:PATTern:DATA?"


def serial_i2c_trigger_data2_command(bus: int, data2: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:IIC:TRIGger:PATTern:DATa2 {_validate_int(data2, 'I2C trigger data2', 0, 255)}"


def serial_i2c_trigger_data2_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:IIC:TRIGger:PATTern:DATa2?"


def serial_i2c_trigger_qualifier_command(bus: int, qualifier: str) -> str:
    canonical = normalize_serial_i2c_trigger_qualifier(qualifier)
    return f":SBUS{_validate_positive_bus(bus)}:IIC:TRIGger:QUALifier {_I2C_TRIGGER_QUALIFIER_TOKENS[canonical]}"


def serial_i2c_trigger_qualifier_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:IIC:TRIGger:QUALifier?"


def serial_i2c_trigger_configure_commands(
    bus: int,
    trigger_type: str,
    address: int | None,
    data: int | None,
    data2: int | None,
    qualifier: str | None,
) -> list[str]:
    canonical = normalize_serial_i2c_trigger_type(trigger_type)
    commands = [serial_i2c_trigger_type_command(bus, canonical)]
    if address is not None:
        commands.append(serial_i2c_trigger_address_command(bus, address, canonical))
    if data is not None:
        commands.append(serial_i2c_trigger_data_command(bus, data))
    if data2 is not None:
        commands.append(serial_i2c_trigger_data2_command(bus, data2))
    if qualifier is not None:
        commands.append(serial_i2c_trigger_qualifier_command(bus, qualifier))
    return commands


def serial_spi_trigger_type_command(bus: int, trigger_type: str) -> str:
    canonical = normalize_serial_spi_trigger_type(trigger_type)
    return f":SBUS{_validate_positive_bus(bus)}:SPI:TRIGger:TYPE {_SPI_TRIGGER_TYPE_TOKENS[canonical]}"


def serial_spi_trigger_type_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:SPI:TRIGger:TYPE?"


def serial_spi_trigger_width_command(bus: int, trigger_type: str, width: int) -> str:
    canonical = normalize_serial_spi_trigger_type(trigger_type)
    return f":SBUS{_validate_positive_bus(bus)}:SPI:TRIGger:PATTern:{canonical.upper()}:WIDTh {validate_serial_spi_trigger_width(width)}"


def serial_spi_trigger_width_query(bus: int, trigger_type: str) -> str:
    canonical = normalize_serial_spi_trigger_type(trigger_type)
    return f":SBUS{_validate_positive_bus(bus)}:SPI:TRIGger:PATTern:{canonical.upper()}:WIDTh?"


def serial_spi_trigger_data_command(bus: int, trigger_type: str, data: str) -> str:
    canonical_type = normalize_serial_spi_trigger_type(trigger_type)
    canonical_data = normalize_serial_trigger_pattern(data, "SPI trigger data")
    return f':SBUS{_validate_positive_bus(bus)}:SPI:TRIGger:PATTern:{canonical_type.upper()}:DATA "{canonical_data}"'


def serial_spi_trigger_data_query(bus: int, trigger_type: str) -> str:
    canonical = normalize_serial_spi_trigger_type(trigger_type)
    return f":SBUS{_validate_positive_bus(bus)}:SPI:TRIGger:PATTern:{canonical.upper()}:DATA?"


def serial_spi_trigger_configure_commands(
    bus: int, trigger_type: str, width: int, data: str
) -> list[str]:
    canonical_type = normalize_serial_spi_trigger_type(trigger_type)
    return [
        serial_spi_trigger_type_command(bus, canonical_type),
        serial_spi_trigger_width_command(bus, canonical_type, width),
        serial_spi_trigger_data_command(bus, canonical_type, data),
    ]


def serial_can_trigger_type_command(bus: int, trigger_type: str) -> str:
    canonical = normalize_serial_can_trigger_type(trigger_type)
    return f":SBUS{_validate_positive_bus(bus)}:CAN:TRIGger {_CAN_TRIGGER_TYPE_TOKENS[canonical]}"


def serial_can_trigger_type_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:CAN:TRIGger?"


def serial_can_trigger_id_mode_command(bus: int, id_mode: str) -> str:
    canonical = normalize_serial_can_trigger_id_mode(id_mode)
    return f":SBUS{_validate_positive_bus(bus)}:CAN:TRIGger:PATTern:ID:MODE {_CAN_TRIGGER_ID_MODE_TOKENS[canonical]}"


def serial_can_trigger_id_mode_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:CAN:TRIGger:PATTern:ID:MODE?"


def serial_can_trigger_id_command(bus: int, value: str) -> str:
    canonical = normalize_serial_trigger_pattern(value, "CAN trigger ID")
    return f':SBUS{_validate_positive_bus(bus)}:CAN:TRIGger:PATTern:ID "{canonical}"'


def serial_can_trigger_id_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:CAN:TRIGger:PATTern:ID?"


def serial_can_trigger_data_command(bus: int, data: str) -> str:
    canonical = normalize_serial_trigger_pattern(data, "CAN trigger data")
    return f':SBUS{_validate_positive_bus(bus)}:CAN:TRIGger:PATTern:DATA "{canonical}"'


def serial_can_trigger_data_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:CAN:TRIGger:PATTern:DATA?"


def serial_can_trigger_data_length_command(bus: int, length: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:CAN:TRIGger:PATTern:DATA:LENGth {validate_serial_can_trigger_data_length(length)}"


def serial_can_trigger_data_length_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:CAN:TRIGger:PATTern:DATA:LENGth?"


def serial_can_trigger_configure_commands(
    bus: int,
    trigger_type: str,
    id: str | None,
    id_mode: str | None,
    data: str | None,
    data_length: int | None,
) -> list[str]:
    canonical_type = normalize_serial_can_trigger_type(trigger_type)
    commands: list[str] = []
    if id_mode is not None:
        commands.append(serial_can_trigger_id_mode_command(bus, id_mode))
    if id is not None:
        commands.append(serial_can_trigger_id_command(bus, id))
    if data_length is not None:
        commands.append(serial_can_trigger_data_length_command(bus, data_length))
    if data is not None:
        commands.append(serial_can_trigger_data_command(bus, data))
    commands.append(serial_can_trigger_type_command(bus, canonical_type))
    return commands


def serial_display_command(bus: int, enabled: bool) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("Serial display enabled value must be a boolean.")
    return f":SBUS{_validate_positive_bus(bus)}:DISPlay {1 if enabled else 0}"


def serial_display_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:DISPlay?"


def validate_serial_bus(bus: int, capabilities: ScopeCapabilities) -> int:
    require_serial_decode(capabilities)
    canonical_bus = _validate_positive_bus(bus)
    if canonical_bus > capabilities.serial_bus_count:
        raise ParameterValidationError(
            f"Serial bus {canonical_bus} is not supported by the selected "
            f"{capabilities.series} model profile; expected 1 through "
            f"{capabilities.serial_bus_count}."
        )
    return canonical_bus


def normalize_serial_mode(mode: str) -> str:
    if not isinstance(mode, str) or mode not in SERIAL_MODE_TOKENS:
        raise ParameterValidationError(
            "Serial mode must be one of: " + ", ".join(SERIAL_MODES) + "."
        )
    return mode


def validate_serial_mode(mode: str, capabilities: ScopeCapabilities) -> str:
    require_serial_decode(capabilities)
    canonical = normalize_serial_mode(mode)
    if canonical not in capabilities.serial_modes:
        raise ParameterValidationError(
            f"Serial mode {canonical!r} is not supported by the selected "
            f"{capabilities.series} model profile."
        )
    return canonical


def validate_serial_uart_trigger_request(
    bus: int,
    *,
    query: bool = False,
    type: str | None = None,
    data: object | None = None,
    qualifier: str | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> tuple[int, str | None, int | None, str | None]:
    """Validate one UART trigger query or configure request."""

    if not isinstance(query, bool):
        raise ParameterValidationError(
            "serial-trigger-uart query must be a boolean."
        )
    canonical_bus = (
        validate_serial_bus(bus, capabilities)
        if capabilities is not None
        else _validate_positive_bus(bus)
    )
    if capabilities is not None:
        validate_serial_mode("uart", capabilities)

    if query:
        if type is not None or data is not None or qualifier is not None:
            raise ParameterValidationError(
                "serial-trigger-uart --query cannot be combined with configure arguments."
            )
        return canonical_bus, None, None, None

    if type is None:
        raise ParameterValidationError(
            "serial-trigger-uart configure requires --type."
        )
    canonical_type = normalize_serial_uart_trigger_type(type)
    data_type = canonical_type in {"rx-data", "tx-data"}
    if data_type:
        if data is None or qualifier is None:
            raise ParameterValidationError(
                "serial-trigger-uart data types require --data and --qualifier."
            )
        canonical_data = _validate_int(data, "UART trigger data", 0, 255)
        canonical_qualifier = normalize_serial_uart_trigger_qualifier(qualifier)
        return canonical_bus, canonical_type, canonical_data, canonical_qualifier
    if data is not None or qualifier is not None:
        raise ParameterValidationError(
            "serial-trigger-uart non-data types cannot use --data or --qualifier."
        )
    return canonical_bus, canonical_type, None, None


def validate_serial_i2c_trigger_request(
    bus: int,
    *,
    query: bool = False,
    type: str | None = None,
    address: object | None = None,
    data: object | None = None,
    data2: object | None = None,
    qualifier: str | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> tuple[int, str | None, int | None, int | None, int | None, str | None]:
    """Validate one I2C trigger query or configure request."""

    canonical_bus = _validate_trigger_request_bus(
        bus, query, "i2c", capabilities
    )
    supplied = {"address": address, "data": data, "data2": data2, "qualifier": qualifier}
    if query:
        if type is not None or any(value is not None for value in supplied.values()):
            raise ParameterValidationError(
                "serial-trigger-i2c --query cannot be combined with configure arguments."
            )
        return canonical_bus, None, None, None, None, None
    if type is None:
        raise ParameterValidationError("serial-trigger-i2c configure requires --type.")
    canonical_type = normalize_serial_i2c_trigger_type(type)
    requirements = {
        "start": (set(), set(supplied)),
        "stop": (set(), set(supplied)),
        "restart": (set(), set(supplied)),
        "missing-ack": (set(), set(supplied)),
        "address-no-ack": ({"address"}, {"data", "data2", "qualifier"}),
        "read7": ({"address", "data"}, {"data2", "qualifier"}),
        "write7": ({"address", "data"}, {"data2", "qualifier"}),
        "write10": ({"address", "data"}, {"data2", "qualifier"}),
        "read7-data2": ({"address", "data", "data2"}, {"qualifier"}),
        "write7-data2": ({"address", "data", "data2"}, {"qualifier"}),
        "read-eeprom": ({"address", "data", "qualifier"}, {"data2"}),
    }
    required, forbidden = requirements[canonical_type]
    for field in required:
        if supplied[field] is None:
            raise ParameterValidationError(
                f"serial-trigger-i2c type {canonical_type!r} requires --{field.replace('_', '-')}."
            )
    for field in forbidden:
        if supplied[field] is not None:
            raise ParameterValidationError(
                f"serial-trigger-i2c type {canonical_type!r} cannot use --{field.replace('_', '-')}."
            )
    canonical_address = None
    if address is not None:
        canonical_address = _validate_i2c_trigger_address(address, canonical_type)
    canonical_data = (
        None if data is None else _coerce_i2c_trigger_value(data, "I2C trigger data", 0xFF)
    )
    canonical_data2 = (
        None if data2 is None else _coerce_i2c_trigger_value(data2, "I2C trigger data2", 0xFF)
    )
    canonical_qualifier = (
        None if qualifier is None else normalize_serial_i2c_trigger_qualifier(qualifier)
    )
    return (
        canonical_bus, canonical_type, canonical_address, canonical_data,
        canonical_data2, canonical_qualifier,
    )


def validate_serial_spi_trigger_request(
    bus: int,
    *,
    query: bool = False,
    type: str | None = None,
    width: object | None = None,
    data: str | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> tuple[int, str | None, int | None, str | None]:
    """Validate one SPI trigger query or configure request."""

    canonical_bus = _validate_trigger_request_bus(bus, query, "spi", capabilities)
    if query:
        if type is not None or width is not None or data is not None:
            raise ParameterValidationError(
                "serial-trigger-spi --query cannot be combined with configure arguments."
            )
        return canonical_bus, None, None, None
    if type is None:
        raise ParameterValidationError("serial-trigger-spi configure requires --type.")
    if width is None or data is None:
        raise ParameterValidationError(
            "serial-trigger-spi configure requires --type, --width, and --data."
        )
    canonical_type = normalize_serial_spi_trigger_type(type)
    canonical_width = validate_serial_spi_trigger_width(width)
    canonical_data = normalize_serial_trigger_pattern(
        data, "SPI trigger data", max_bits=canonical_width
    )
    return canonical_bus, canonical_type, canonical_width, canonical_data


def validate_serial_can_trigger_request(
    bus: int,
    *,
    query: bool = False,
    type: str | None = None,
    id: str | None = None,
    id_mode: str | None = None,
    data: str | None = None,
    data_length: object | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> tuple[int, str | None, str | None, str | None, str | None, int | None]:
    """Validate one CAN trigger query or configure request."""

    canonical_bus = _validate_trigger_request_bus(bus, query, "can", capabilities)
    if query:
        if type is not None or id is not None or id_mode is not None or data is not None or data_length is not None:
            raise ParameterValidationError(
                "serial-trigger-can --query cannot be combined with configure arguments."
            )
        return canonical_bus, None, None, None, None, None
    if type is None:
        raise ParameterValidationError("serial-trigger-can configure requires --type.")
    canonical_type = normalize_serial_can_trigger_type(type)
    supplied = {"id": id, "id_mode": id_mode, "data": data, "data_length": data_length}
    requirements = {
        "start-of-frame": ({}, {"id", "id_mode", "data", "data_length"}),
        "error": ({}, {"id", "id_mode", "data", "data_length"}),
        "all-errors": ({}, {"id", "id_mode", "data", "data_length"}),
        "overload": ({}, {"id", "id_mode", "data", "data_length"}),
        "ack-error": ({}, {"id", "id_mode", "data", "data_length"}),
        "data-frame-id": ({"id", "id_mode"}, {"data", "data_length"}),
        "any-frame-id": ({"id", "id_mode"}, {"data", "data_length"}),
        "remote-frame-id": ({"id", "id_mode"}, {"data", "data_length"}),
        "id-and-data": ({"id", "id_mode", "data", "data_length"}, set()),
    }
    required, forbidden = requirements[canonical_type]
    for field in required:
        if supplied[field] is None:
            raise ParameterValidationError(
                f"serial-trigger-can type {canonical_type!r} requires --{field.replace('_', '-')}."
            )
    for field in forbidden:
        if supplied[field] is not None:
            raise ParameterValidationError(
                f"serial-trigger-can type {canonical_type!r} cannot use --{field.replace('_', '-')}."
            )
    canonical_id_mode = None if id_mode is None else normalize_serial_can_trigger_id_mode(id_mode)
    canonical_id = (
        None if id is None else normalize_serial_trigger_pattern(id, "CAN trigger ID", max_bits=29)
    )
    canonical_data = (
        None if data is None else normalize_serial_trigger_pattern(data, "CAN trigger data", max_bits=64)
    )
    canonical_length = (
        None if data_length is None else validate_serial_can_trigger_data_length(data_length)
    )
    return canonical_bus, canonical_type, canonical_id, canonical_id_mode, canonical_data, canonical_length


def _validate_trigger_request_bus(
    bus: int,
    query: bool,
    protocol: str,
    capabilities: ScopeCapabilities | None,
) -> int:
    if not isinstance(query, bool):
        raise ParameterValidationError(f"serial-trigger-{protocol} query must be a boolean.")
    canonical_bus = (
        validate_serial_bus(bus, capabilities)
        if capabilities is not None
        else _validate_positive_bus(bus)
    )
    if capabilities is not None:
        validate_serial_mode(protocol, capabilities)
    return canonical_bus


def normalize_serial_i2c_trigger_type(value: str) -> str:
    return _normalize_choice(value, I2C_TRIGGER_TYPES, "I2C trigger type")


def parse_serial_i2c_trigger_type(raw: str) -> str:
    return _parse_choice(raw, _I2C_TRIGGER_TYPE_READBACKS, "I2C trigger type")


def serial_i2c_trigger_type_readback(trigger_type: str) -> str:
    canonical = normalize_serial_i2c_trigger_type(trigger_type)
    return {
        "start": "STAR", "stop": "STOP", "restart": "REST",
        "read7": "READ7", "read-eeprom": "READE", "write7": "WRIT7",
        "write10": "WRIT10", "missing-ack": "NACK",
        "address-no-ack": "ANAC", "read7-data2": "R7D2",
        "write7-data2": "W7D2",
    }[canonical]


def normalize_serial_i2c_trigger_qualifier(value: str) -> str:
    return _normalize_choice(value, I2C_TRIGGER_QUALIFIERS, "I2C trigger qualifier")


def parse_serial_i2c_trigger_qualifier(raw: str) -> str:
    return _parse_choice(raw, _I2C_TRIGGER_QUALIFIER_READBACKS, "I2C trigger qualifier")


def serial_i2c_trigger_qualifier_readback(qualifier: str) -> str:
    canonical = normalize_serial_i2c_trigger_qualifier(qualifier)
    return {
        "equal": "EQU",
        "not-equal": "NOT",
        "less-than": "LESS",
        "greater-than": "GRE",
    }[canonical]


def normalize_serial_spi_trigger_type(value: str) -> str:
    return _normalize_choice(value, SPI_TRIGGER_TYPES, "SPI trigger type")


def parse_serial_spi_trigger_type(raw: str) -> str:
    return _parse_choice(raw, _SPI_TRIGGER_TYPE_READBACKS, "SPI trigger type")


def serial_spi_trigger_type_readback(trigger_type: str) -> str:
    return _SPI_TRIGGER_TYPE_TOKENS[normalize_serial_spi_trigger_type(trigger_type)]


def validate_serial_spi_trigger_width(value: object) -> int:
    return _validate_int(value, "SPI trigger width", 4, 64)


def parse_serial_spi_trigger_width(raw: str) -> int:
    return _parse_serial_int_validated(raw, "SPI trigger width", validate_serial_spi_trigger_width)


def normalize_serial_can_trigger_type(value: str) -> str:
    return _normalize_choice(value, CAN_TRIGGER_TYPES, "CAN trigger type")


def parse_serial_can_trigger_type(raw: str) -> str:
    return _parse_choice(raw, _CAN_TRIGGER_TYPE_READBACKS, "CAN trigger type")


def serial_can_trigger_type_readback(trigger_type: str) -> str:
    canonical = normalize_serial_can_trigger_type(trigger_type)
    return {
        "start-of-frame": "SOF", "id-and-data": "DATA", "error": "ERR",
        "data-frame-id": "IDD", "any-frame-id": "IDE", "remote-frame-id": "IDR",
        "all-errors": "ALL", "overload": "OVER", "ack-error": "ACK",
    }[canonical]


def normalize_serial_can_trigger_id_mode(value: str) -> str:
    return _normalize_choice(value, CAN_TRIGGER_ID_MODES, "CAN trigger ID mode")


def parse_serial_can_trigger_id_mode(raw: str) -> str:
    return _parse_choice(raw, _CAN_TRIGGER_ID_MODE_READBACKS, "CAN trigger ID mode")


def validate_serial_can_trigger_data_length(value: object) -> int:
    return _validate_int(value, "CAN trigger data length", 1, 8)


def parse_serial_can_trigger_data_length(raw: str) -> int:
    return _parse_serial_int_validated(raw, "CAN trigger data length", validate_serial_can_trigger_data_length)


def normalize_serial_trigger_pattern(
    value: str, label: str = "Serial trigger", *, max_bits: int | None = None
) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError(f"{label} pattern must be a string.")
    cleaned = value.strip()
    if not cleaned:
        raise ParameterValidationError(f"{label} pattern must not be empty.")
    if cleaned.startswith(("0x", "0X")):
        payload = cleaned[2:]
        if not payload or not re.fullmatch(r"[0-9a-fA-FxX]+", payload):
            raise ParameterValidationError(
                f"{label} pattern must contain hexadecimal characters or X."
            )
        if max_bits is not None and len(payload) > math.ceil(max_bits / 4):
            raise ParameterValidationError(f"{label} pattern exceeds {max_bits} bits.")
        return f"0x{payload.upper()}"
    if not re.fullmatch(r"[01xX]+", cleaned):
        raise ParameterValidationError(
            f"{label} pattern must be binary 0/1/X or hexadecimal 0x/X."
        )
    if max_bits is not None and len(cleaned) > max_bits:
        raise ParameterValidationError(f"{label} pattern exceeds {max_bits} bits.")
    return cleaned.upper()


def parse_serial_trigger_pattern(
    raw: str, label: str = "Serial trigger", *, max_bits: int | None = None
) -> str:
    cleaned = raw.strip()
    if len(cleaned) >= 2 and cleaned[0] == '"' and cleaned[-1] == '"':
        cleaned = cleaned[1:-1]
    try:
        return normalize_serial_trigger_pattern(cleaned, label, max_bits=max_bits)
    except ParameterValidationError as exc:
        raise SerialResponseError(f"Could not parse {label} response: {raw!r}") from exc


def _coerce_i2c_trigger_value(value: object, label: str, maximum: int) -> int:
    if isinstance(value, bool):
        raise ParameterValidationError(f"{label} must be an integer in range 0-{maximum}.")
    if isinstance(value, int):
        numeric = value
    elif isinstance(value, str):
        try:
            numeric = int(value.strip(), 0)
        except ValueError as exc:
            raise ParameterValidationError(f"{label} must be an integer in range 0-{maximum}.") from exc
    else:
        raise ParameterValidationError(f"{label} must be an integer in range 0-{maximum}.")
    if not 0 <= numeric <= maximum:
        raise ParameterValidationError(f"{label} must be an integer in range 0-{maximum}.")
    return numeric


def _validate_i2c_trigger_address(value: object, trigger_type: str) -> int:
    maximum = 0x3FF if trigger_type == "write10" else 0x7F
    return _coerce_i2c_trigger_value(value, "I2C trigger address", maximum)


def parse_serial_i2c_trigger_address(raw: str, trigger_type: str) -> int:
    try:
        value = int(raw.strip(), 0)
        return _validate_i2c_trigger_address(value, trigger_type)
    except (ValueError, ParameterValidationError) as exc:
        raise SerialResponseError(f"Could not parse I2C trigger address response: {raw!r}") from exc


def parse_serial_i2c_trigger_data(raw: str, label: str = "I2C trigger data") -> int:
    try:
        value = int(raw.strip(), 0)
        return _coerce_i2c_trigger_value(value, label, 0xFF)
    except (ValueError, ParameterValidationError) as exc:
        raise SerialResponseError(f"Could not parse {label} response: {raw!r}") from exc


def parse_serial_mode(raw: str) -> str | None:
    normalized = raw.strip().upper()
    if normalized == "NONE":
        return None
    try:
        return _SERIAL_MODE_READBACKS[normalized]
    except KeyError as exc:
        raise SerialResponseError(
            f"Could not parse serial mode response: {raw!r}"
        ) from exc


def normalize_serial_uart_trigger_type(value: str) -> str:
    return _normalize_choice(value, UART_TRIGGER_TYPES, "UART trigger type")


def parse_serial_uart_trigger_type(raw: str) -> str:
    return _parse_choice(raw, _UART_TRIGGER_TYPE_READBACKS, "UART trigger type")


def serial_uart_trigger_type_readback(trigger_type: str) -> str:
    canonical = normalize_serial_uart_trigger_type(trigger_type)
    return _UART_TRIGGER_TYPE_READBACKS_FOR_CANONICAL[canonical]


def normalize_serial_uart_trigger_qualifier(value: str) -> str:
    return _normalize_choice(
        value, UART_TRIGGER_QUALIFIERS, "UART trigger qualifier"
    )


def parse_serial_uart_trigger_qualifier(raw: str) -> str:
    return _parse_choice(
        raw, _UART_TRIGGER_QUALIFIER_READBACKS, "UART trigger qualifier"
    )


def serial_uart_trigger_qualifier_readback(qualifier: str) -> str:
    canonical = normalize_serial_uart_trigger_qualifier(qualifier)
    return _UART_TRIGGER_QUALIFIER_READBACKS_FOR_CANONICAL[canonical]


def parse_serial_uart_trigger_data(raw: str) -> int:
    return _parse_serial_int_validated(
        raw,
        "UART trigger data",
        lambda value: _validate_int(value, "UART trigger data", 0, 255),
    )


def require_serial_decode(capabilities: ScopeCapabilities) -> None:
    if not capabilities.supports_serial_decode:
        raise ParameterValidationError(
            "Serial Basic P0 is not supported by the selected model profile."
        )


def _validate_positive_bus(bus: int) -> int:
    if isinstance(bus, bool) or not isinstance(bus, int) or bus <= 0:
        raise ParameterValidationError("Serial bus must be a positive integer.")
    return bus
