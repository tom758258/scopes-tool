"""Model-guarded basic waveform event search controls."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .capabilities import ScopeCapabilities
from .errors import ParameterValidationError, SearchResponseError
from .scpi import SCPIClient
from .serial import validate_serial_bus, validate_serial_mode


SEARCH_MODES = (
    "serial1",
    "serial2",
    "edge",
    "glitch",
    "runt",
    "transition",
    "peak",
)

_SEARCH_MODE_COMMANDS = {
    "serial1": "SERial1",
    "serial2": "SERial2",
    "edge": "EDGE",
    "glitch": "GLITch",
    "runt": "RUNT",
    "transition": "TRANsition",
    "peak": "PEAK",
}

_SEARCH_MODE_READBACKS = {
    "SER1": "serial1",
    "SERIAL1": "serial1",
    "SER2": "serial2",
    "SERIAL2": "serial2",
    "EDGE": "edge",
    "GLIT": "glitch",
    "GLITCH": "glitch",
    "RUNT": "runt",
    "TRAN": "transition",
    "TRANSITION": "transition",
    "PEAK": "peak",
}

UART_SEARCH_MODES = (
    "rx-data",
    "rx-1",
    "rx-0",
    "rx-any",
    "tx-data",
    "tx-1",
    "tx-0",
    "tx-any",
    "parity-error",
    "any-error",
)

_UART_SEARCH_MODE_TOKENS = {
    "rx-data": "RDATa",
    "rx-1": "RD1",
    "rx-0": "RD0",
    "rx-any": "RDX",
    "tx-data": "TDATa",
    "tx-1": "TD1",
    "tx-0": "TD0",
    "tx-any": "TDX",
    "parity-error": "PARityerror",
    "any-error": "AERRor",
}

_UART_SEARCH_MODE_READBACKS = {
    "RDAT": "rx-data",
    "RDATA": "rx-data",
    "RD1": "rx-1",
    "RD0": "rx-0",
    "RDX": "rx-any",
    "TDAT": "tx-data",
    "TDATA": "tx-data",
    "TD1": "tx-1",
    "TD0": "tx-0",
    "TDX": "tx-any",
    "PAR": "parity-error",
    "PARITYERROR": "parity-error",
    "AERR": "any-error",
    "AERROR": "any-error",
}

SEARCH_QUALIFIERS = (
    "equal",
    "not-equal",
    "greater-than",
    "less-than",
)

_SEARCH_QUALIFIER_TOKENS = {
    "equal": "EQUal",
    "not-equal": "NOTequal",
    "greater-than": "GREaterthan",
    "less-than": "LESSthan",
}

_SEARCH_QUALIFIER_READBACKS = {
    "EQU": "equal",
    "EQUAL": "equal",
    "NOT": "not-equal",
    "NOTEQUAL": "not-equal",
    "GRE": "greater-than",
    "GREATERTHAN": "greater-than",
    "LESS": "less-than",
    "LESSTHAN": "less-than",
}

I2C_SEARCH_MODES = (
    "read7",
    "write7",
    "nack",
    "address-nack",
    "read7-data2",
    "write7-data2",
    "restart",
    "eeprom-read",
)

_I2C_SEARCH_MODE_TOKENS = {
    "read7": "READ7",
    "write7": "WRITE7",
    "nack": "NACKnowledge",
    "address-nack": "ANACk",
    "read7-data2": "R7Data2",
    "write7-data2": "W7Data2",
    "restart": "RESTart",
    "eeprom-read": "READEprom",
}

_I2C_SEARCH_MODE_READBACKS = {
    "READ7": "read7",
    "WRITE7": "write7",
    "WRIT7": "write7",
    "NACK": "nack",
    "NACKNOWLEDGE": "nack",
    "ANAC": "address-nack",
    "ANACK": "address-nack",
    "R7D2": "read7-data2",
    "R7DATA2": "read7-data2",
    "W7D2": "write7-data2",
    "W7DATA2": "write7-data2",
    "REST": "restart",
    "RESTART": "restart",
    "READE": "eeprom-read",
    "READEPROM": "eeprom-read",
}

_I2C_SEARCH_MODE_UNSUPPORTED_READBACKS = {"ADDR", "ADDRESS"}

SPI_SEARCH_MODES = (
    "mosi",
    "miso",
)

_SPI_SEARCH_MODE_TOKENS = {
    "mosi": "MOSI",
    "miso": "MISO",
}

_SPI_SEARCH_MODE_READBACKS = {
    "MOSI": "mosi",
    "MISO": "miso",
}

CAN_SEARCH_MODES = (
    "data",
    "id-data",
    "id-either",
    "id-remote",
    "all-errors",
    "overload",
    "error",
)

_CAN_SEARCH_MODE_TOKENS = {
    "data": "DATA",
    "id-data": "IDData",
    "id-either": "IDEither",
    "id-remote": "IDRemote",
    "all-errors": "ALLerrors",
    "overload": "OVERload",
    "error": "ERRor",
}

_CAN_SEARCH_MODE_READBACKS = {
    "DATA": "data",
    "IDD": "id-data",
    "IDDATA": "id-data",
    "IDE": "id-either",
    "IDEITHER": "id-either",
    "IDR": "id-remote",
    "IDREMOTE": "id-remote",
    "ALL": "all-errors",
    "ALLERRORS": "all-errors",
    "OVER": "overload",
    "OVERLOAD": "overload",
    "ERR": "error",
    "ERROR": "error",
}

_CAN_SEARCH_MODE_UNSUPPORTED_READBACKS = {
    "ACK",
    "ACKERROR",
    "FORM",
    "FORMERROR",
    "STUF",
    "STUFF",
    "STUFERROR",
    "STUFFERROR",
    "CRC",
    "CRCERROR",
    "MESS",
    "MESSAGE",
    "MSIG",
    "MSIGNAL",
}

CAN_SEARCH_ID_MODES = (
    "standard",
    "extended",
)

_CAN_SEARCH_ID_MODE_TOKENS = {
    "standard": "STANdard",
    "extended": "EXTended",
}

_CAN_SEARCH_ID_MODE_READBACKS = {
    "STAN": "standard",
    "STANDARD": "standard",
    "EXT": "extended",
    "EXTENDED": "extended",
}


@dataclass(frozen=True)
class SearchState:
    enabled: bool
    raw_state: str | None = None

    def to_json(self) -> dict[str, object]:
        return {"enabled": self.enabled, "raw_state": self.raw_state}


@dataclass(frozen=True)
class SearchModeState:
    mode: str | None
    enabled: bool | None
    raw_mode: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "raw_mode": self.raw_mode,
        }


@dataclass(frozen=True)
class SearchCountState:
    count: int
    raw_count: str

    def to_json(self) -> dict[str, object]:
        return {"count": self.count, "raw_count": self.raw_count}


@dataclass(frozen=True)
class SearchEventState:
    event: int
    raw: str | None = None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {"event": self.event}
        if self.raw is not None:
            payload["raw"] = self.raw
        return payload


@dataclass(frozen=True)
class SerialSearchUartState:
    bus: int
    search_enabled: bool | None = None
    raw_search_state: str | None = None
    search_mode: str | None = None
    raw_search_mode: str | None = None
    selected: bool | None = None
    mode: str | None = None
    raw_mode: str | None = None
    data: int | None = None
    raw_data: str | None = None
    qualifier: str | None = None
    raw_qualifier: str | None = None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {"bus": self.bus}
        if self.search_enabled is not None:
            payload["search_enabled"] = self.search_enabled
        if self.raw_search_state is not None:
            payload["raw_search_state"] = self.raw_search_state
        if self.search_enabled is not None:
            payload["search_mode"] = self.search_mode
        if self.raw_search_mode is not None:
            payload["raw_search_mode"] = self.raw_search_mode
        if self.selected is not None:
            payload["selected"] = self.selected
        payload["mode"] = self.mode
        if self.raw_mode is not None:
            payload["raw_mode"] = self.raw_mode
        if self.search_enabled is not None or self.data is not None:
            payload["data"] = self.data
        if self.raw_data is not None:
            payload["raw_data"] = self.raw_data
        if self.search_enabled is not None or self.qualifier is not None:
            payload["qualifier"] = self.qualifier
        if self.raw_qualifier is not None:
            payload["raw_qualifier"] = self.raw_qualifier
        return payload


@dataclass(frozen=True)
class SerialSearchI2CState:
    bus: int
    search_enabled: bool | None = None
    raw_search_state: str | None = None
    search_mode: str | None = None
    raw_search_mode: str | None = None
    selected: bool | None = None
    mode: str | None = None
    raw_mode: str | None = None
    address: int | None = None
    raw_address: str | None = None
    data: int | None = None
    raw_data: str | None = None
    data2: int | None = None
    raw_data2: str | None = None
    qualifier: str | None = None
    raw_qualifier: str | None = None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {"bus": self.bus}
        if self.search_enabled is not None:
            payload["search_enabled"] = self.search_enabled
        if self.raw_search_state is not None:
            payload["raw_search_state"] = self.raw_search_state
        if self.search_enabled is not None:
            payload["search_mode"] = self.search_mode
        if self.raw_search_mode is not None:
            payload["raw_search_mode"] = self.raw_search_mode
        if self.selected is not None:
            payload["selected"] = self.selected
        payload["mode"] = self.mode
        if self.raw_mode is not None:
            payload["raw_mode"] = self.raw_mode
        if self.search_enabled is not None or self.address is not None:
            payload["address"] = self.address
        if self.raw_address is not None:
            payload["raw_address"] = self.raw_address
        if self.search_enabled is not None or self.data is not None:
            payload["data"] = self.data
        if self.raw_data is not None:
            payload["raw_data"] = self.raw_data
        if self.search_enabled is not None or self.data2 is not None:
            payload["data2"] = self.data2
        if self.raw_data2 is not None:
            payload["raw_data2"] = self.raw_data2
        if self.search_enabled is not None or self.qualifier is not None:
            payload["qualifier"] = self.qualifier
        if self.raw_qualifier is not None:
            payload["raw_qualifier"] = self.raw_qualifier
        return payload


@dataclass(frozen=True)
class SerialSearchSpiState:
    bus: int
    search_enabled: bool | None = None
    raw_search_state: str | None = None
    search_mode: str | None = None
    raw_search_mode: str | None = None
    selected: bool | None = None
    mode: str | None = None
    raw_mode: str | None = None
    data: str | None = None
    raw_data: str | None = None
    width: int | None = None
    raw_width: str | None = None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {"bus": self.bus}
        if self.search_enabled is not None:
            payload["search_enabled"] = self.search_enabled
        if self.raw_search_state is not None:
            payload["raw_search_state"] = self.raw_search_state
        if self.search_enabled is not None:
            payload["search_mode"] = self.search_mode
        if self.raw_search_mode is not None:
            payload["raw_search_mode"] = self.raw_search_mode
        if self.selected is not None:
            payload["selected"] = self.selected
        payload["mode"] = self.mode
        if self.raw_mode is not None:
            payload["raw_mode"] = self.raw_mode
        if self.search_enabled is not None or self.data is not None:
            payload["data"] = self.data
        if self.raw_data is not None:
            payload["raw_data"] = self.raw_data
        if self.search_enabled is not None or self.width is not None:
            payload["width"] = self.width
        if self.raw_width is not None:
            payload["raw_width"] = self.raw_width
        return payload


@dataclass(frozen=True)
class SerialSearchCanState:
    bus: int
    search_enabled: bool | None = None
    raw_search_state: str | None = None
    search_mode: str | None = None
    raw_search_mode: str | None = None
    selected: bool | None = None
    mode: str | None = None
    raw_mode: str | None = None
    data: str | None = None
    raw_data: str | None = None
    data_length: int | None = None
    raw_data_length: str | None = None
    id: str | None = None
    raw_id: str | None = None
    id_mode: str | None = None
    raw_id_mode: str | None = None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {"bus": self.bus}
        if self.search_enabled is not None:
            payload["search_enabled"] = self.search_enabled
        if self.raw_search_state is not None:
            payload["raw_search_state"] = self.raw_search_state
        if self.search_enabled is not None:
            payload["search_mode"] = self.search_mode
        if self.raw_search_mode is not None:
            payload["raw_search_mode"] = self.raw_search_mode
        if self.selected is not None:
            payload["selected"] = self.selected
        payload["mode"] = self.mode
        if self.raw_mode is not None:
            payload["raw_mode"] = self.raw_mode
        if self.search_enabled is not None or self.data is not None:
            payload["data"] = self.data
        if self.raw_data is not None:
            payload["raw_data"] = self.raw_data
        if self.search_enabled is not None or self.data_length is not None:
            payload["data_length"] = self.data_length
        if self.raw_data_length is not None:
            payload["raw_data_length"] = self.raw_data_length
        if self.search_enabled is not None or self.id is not None:
            payload["id"] = self.id
        if self.raw_id is not None:
            payload["raw_id"] = self.raw_id
        if self.search_enabled is not None or self.id_mode is not None:
            payload["id_mode"] = self.id_mode
        if self.raw_id_mode is not None:
            payload["raw_id_mode"] = self.raw_id_mode
        return payload


class SearchController:
    """Controller for Search Basic Pack v1 and Serial Search P3."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure_state(self, enabled: bool) -> SearchState:
        require_search_basic(self.capabilities)
        self.scpi.write(search_state_command(enabled))
        return SearchState(enabled=enabled)

    def query_state(self) -> SearchState:
        require_search_basic(self.capabilities)
        raw = self.scpi.query(search_state_query()).strip()
        return SearchState(enabled=parse_search_state(raw), raw_state=raw)

    def configure_mode(self, mode: str) -> SearchModeState:
        canonical = validate_search_mode(mode, self.capabilities)
        self.scpi.write(search_state_command(True))
        self.scpi.write(search_mode_command(canonical))
        return SearchModeState(mode=canonical, enabled=True)

    def query_mode(self) -> SearchModeState:
        require_search_basic(self.capabilities)
        raw = self.scpi.query(search_mode_query()).strip()
        mode, enabled = parse_search_mode(raw)
        return SearchModeState(mode=mode, enabled=enabled, raw_mode=raw)

    def query_count(self) -> SearchCountState:
        require_search_basic(self.capabilities)
        return parse_search_count(self.scpi.query(search_count_query()))

    def set_event(self, event: int) -> SearchEventState:
        require_search_event_navigation(self.capabilities)
        canonical_event = validate_search_event(event)
        self.scpi.write(search_event_command(canonical_event))
        return SearchEventState(event=canonical_event)

    def query_event(self) -> SearchEventState:
        require_search_event_navigation(self.capabilities)
        raw = self.scpi.query(search_event_query()).strip()
        return parse_search_event(raw)

    def configure_serial_search_uart(
        self,
        bus: int,
        mode: str,
        data: int | None = None,
        qualifier: str | None = None,
    ) -> SerialSearchUartState:
        canonical_bus = validate_serial_search_bus(bus, self.capabilities)
        validate_serial_mode("uart", self.capabilities)
        canonical_mode = validate_uart_search_mode(mode)
        canonical_data = validate_uart_data(data) if data is not None else None
        canonical_qualifier = (
            validate_search_qualifier(qualifier) if qualifier is not None else None
        )

        cmds = serial_search_uart_configure_commands(
            canonical_bus,
            canonical_mode,
            data=canonical_data,
            qualifier=canonical_qualifier,
        )
        for cmd in cmds:
            self.scpi.write(cmd)

        return SerialSearchUartState(
            bus=canonical_bus,
            mode=canonical_mode,
            data=canonical_data,
            qualifier=canonical_qualifier,
        )

    def query_serial_search_uart(self, bus: int) -> SerialSearchUartState:
        canonical_bus = validate_serial_search_bus(bus, self.capabilities)
        validate_serial_mode("uart", self.capabilities)

        cmds = serial_search_uart_query_commands(canonical_bus)
        responses = [self.scpi.query(cmd).strip() for cmd in cmds]

        raw_state, raw_search_mode, raw_mode, raw_data, raw_qualifier = responses

        search_enabled = parse_search_state(raw_state)
        parsed_search_mode, _ = parse_search_mode(raw_search_mode)
        selected = search_enabled and (parsed_search_mode == f"serial{canonical_bus}")

        mode, _ = parse_uart_search_mode(raw_mode)
        data, _ = parse_uart_data_query(raw_data)
        qualifier, _ = parse_search_qualifier(raw_qualifier)

        return SerialSearchUartState(
            bus=canonical_bus,
            search_enabled=search_enabled,
            raw_search_state=raw_state,
            search_mode=parsed_search_mode,
            raw_search_mode=raw_search_mode,
            selected=selected,
            mode=mode,
            raw_mode=raw_mode,
            data=data,
            raw_data=raw_data,
            qualifier=qualifier,
            raw_qualifier=raw_qualifier,
        )

    def configure_serial_search_i2c(
        self,
        bus: int,
        mode: str,
        address: int | None = None,
        data: int | None = None,
        data2: int | None = None,
        qualifier: str | None = None,
    ) -> SerialSearchI2CState:
        canonical_bus = validate_serial_search_bus(bus, self.capabilities)
        validate_serial_mode("i2c", self.capabilities)
        canonical_mode = validate_i2c_search_mode(mode)
        canonical_address = (
            validate_i2c_pattern_value(address, "address") if address is not None else None
        )
        canonical_data = (
            validate_i2c_pattern_value(data, "data") if data is not None else None
        )
        canonical_data2 = (
            validate_i2c_pattern_value(data2, "data2") if data2 is not None else None
        )
        canonical_qualifier = (
            validate_search_qualifier(qualifier) if qualifier is not None else None
        )

        cmds = serial_search_i2c_configure_commands(
            canonical_bus,
            canonical_mode,
            address=canonical_address,
            data=canonical_data,
            data2=canonical_data2,
            qualifier=canonical_qualifier,
        )
        for cmd in cmds:
            self.scpi.write(cmd)

        return SerialSearchI2CState(
            bus=canonical_bus,
            mode=canonical_mode,
            address=canonical_address,
            data=canonical_data,
            data2=canonical_data2,
            qualifier=canonical_qualifier,
        )

    def query_serial_search_i2c(self, bus: int) -> SerialSearchI2CState:
        canonical_bus = validate_serial_search_bus(bus, self.capabilities)
        validate_serial_mode("i2c", self.capabilities)

        cmds = serial_search_i2c_query_commands(canonical_bus)
        responses = [self.scpi.query(cmd).strip() for cmd in cmds]

        (
            raw_state,
            raw_search_mode,
            raw_mode,
            raw_address,
            raw_data,
            raw_data2,
            raw_qualifier,
        ) = responses

        search_enabled = parse_search_state(raw_state)
        parsed_search_mode, _ = parse_search_mode(raw_search_mode)
        selected = search_enabled and (parsed_search_mode == f"serial{canonical_bus}")

        mode, _ = parse_i2c_search_mode(raw_mode)
        address, _ = parse_i2c_pattern_query(raw_address, "I2C address")
        data, _ = parse_i2c_pattern_query(raw_data, "I2C data")
        data2, _ = parse_i2c_pattern_query(raw_data2, "I2C data2")
        qualifier, _ = parse_search_qualifier(raw_qualifier)

        return SerialSearchI2CState(
            bus=canonical_bus,
            search_enabled=search_enabled,
            raw_search_state=raw_state,
            search_mode=parsed_search_mode,
            raw_search_mode=raw_search_mode,
            selected=selected,
            mode=mode,
            raw_mode=raw_mode,
            address=address,
            raw_address=raw_address,
            data=data,
            raw_data=raw_data,
            data2=data2,
            raw_data2=raw_data2,
            qualifier=qualifier,
            raw_qualifier=raw_qualifier,
        )

    def configure_serial_search_spi(
        self,
        bus: int,
        mode: str,
        data: str | None = None,
        width: int | None = None,
    ) -> SerialSearchSpiState:
        canonical_bus = validate_serial_search_bus(bus, self.capabilities)
        validate_serial_mode("spi", self.capabilities)
        canonical_mode = validate_spi_search_mode(mode)
        canonical_data = (
            validate_pattern_hex_x(data, "SPI search data") if data is not None else None
        )
        canonical_width = validate_spi_width(width) if width is not None else None

        cmds = serial_search_spi_configure_commands(
            canonical_bus,
            canonical_mode,
            data=canonical_data,
            width=canonical_width,
        )
        for cmd in cmds:
            self.scpi.write(cmd)

        return SerialSearchSpiState(
            bus=canonical_bus,
            mode=canonical_mode,
            data=canonical_data,
            width=canonical_width,
        )

    def query_serial_search_spi(self, bus: int) -> SerialSearchSpiState:
        canonical_bus = validate_serial_search_bus(bus, self.capabilities)
        validate_serial_mode("spi", self.capabilities)

        cmds = serial_search_spi_query_commands(canonical_bus)
        responses = [self.scpi.query(cmd).strip() for cmd in cmds]

        raw_state, raw_search_mode, raw_mode, raw_data, raw_width = responses

        search_enabled = parse_search_state(raw_state)
        parsed_search_mode, _ = parse_search_mode(raw_search_mode)
        selected = search_enabled and (parsed_search_mode == f"serial{canonical_bus}")

        mode, _ = parse_spi_search_mode(raw_mode)
        data, _ = parse_pattern_query(raw_data)
        width, _ = parse_spi_width_query(raw_width)

        return SerialSearchSpiState(
            bus=canonical_bus,
            search_enabled=search_enabled,
            raw_search_state=raw_state,
            search_mode=parsed_search_mode,
            raw_search_mode=raw_search_mode,
            selected=selected,
            mode=mode,
            raw_mode=raw_mode,
            data=data,
            raw_data=raw_data,
            width=width,
            raw_width=raw_width,
        )

    def configure_serial_search_can(
        self,
        bus: int,
        mode: str,
        data: str | None = None,
        data_length: int | None = None,
        id_val: str | None = None,
        id_mode: str | None = None,
    ) -> SerialSearchCanState:
        canonical_bus = validate_serial_search_bus(bus, self.capabilities)
        validate_serial_mode("can", self.capabilities)
        canonical_mode = validate_can_search_mode(mode)
        canonical_data = (
            validate_pattern_hex_x(data, "CAN search data") if data is not None else None
        )
        canonical_data_length = (
            validate_can_data_length(data_length) if data_length is not None else None
        )
        canonical_id = (
            validate_pattern_hex_x(id_val, "CAN search ID") if id_val is not None else None
        )
        canonical_id_mode = (
            validate_can_id_mode(id_mode) if id_mode is not None else None
        )

        cmds = serial_search_can_configure_commands(
            canonical_bus,
            canonical_mode,
            data=canonical_data,
            data_length=canonical_data_length,
            id_val=canonical_id,
            id_mode=canonical_id_mode,
        )
        for cmd in cmds:
            self.scpi.write(cmd)

        return SerialSearchCanState(
            bus=canonical_bus,
            mode=canonical_mode,
            data=canonical_data,
            data_length=canonical_data_length,
            id=canonical_id,
            id_mode=canonical_id_mode,
        )

    def query_serial_search_can(self, bus: int) -> SerialSearchCanState:
        canonical_bus = validate_serial_search_bus(bus, self.capabilities)
        validate_serial_mode("can", self.capabilities)

        cmds = serial_search_can_query_commands(canonical_bus)
        responses = [self.scpi.query(cmd).strip() for cmd in cmds]

        (
            raw_state,
            raw_search_mode,
            raw_mode,
            raw_data,
            raw_data_length,
            raw_id,
            raw_id_mode,
        ) = responses

        search_enabled = parse_search_state(raw_state)
        parsed_search_mode, _ = parse_search_mode(raw_search_mode)
        selected = search_enabled and (parsed_search_mode == f"serial{canonical_bus}")

        mode, _ = parse_can_search_mode(raw_mode)
        data, _ = parse_pattern_query(raw_data)
        data_length, _ = parse_can_data_length_query(raw_data_length)
        id_val, _ = parse_pattern_query(raw_id)
        id_mode, _ = parse_can_id_mode(raw_id_mode)

        return SerialSearchCanState(
            bus=canonical_bus,
            search_enabled=search_enabled,
            raw_search_state=raw_state,
            search_mode=parsed_search_mode,
            raw_search_mode=raw_search_mode,
            selected=selected,
            mode=mode,
            raw_mode=raw_mode,
            data=data,
            raw_data=raw_data,
            data_length=data_length,
            raw_data_length=raw_data_length,
            id=id_val,
            raw_id=raw_id,
            id_mode=id_mode,
            raw_id_mode=raw_id_mode,
        )
def search_state_command(enabled: bool) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("Search enabled value must be a boolean.")
    return f":SEARch:STATe {1 if enabled else 0}"


def search_state_query() -> str:
    return ":SEARch:STATe?"


def search_mode_command(mode: str) -> str:
    canonical = normalize_search_mode(mode)
    return f":SEARch:MODE {_SEARCH_MODE_COMMANDS[canonical]}"


def search_mode_query() -> str:
    return ":SEARch:MODE?"


def search_count_query() -> str:
    return ":SEARch:COUNt?"


def search_event_command(event: int) -> str:
    canonical_event = validate_search_event(event)
    return f":SEARch:EVENt {canonical_event}"


def search_event_query() -> str:
    return ":SEARch:EVENt?"


def validate_search_event(event: int) -> int:
    if isinstance(event, bool) or not isinstance(event, int) or event <= 0:
        raise ParameterValidationError("Search event must be a positive integer.")
    return event


def require_search_event_navigation(capabilities: ScopeCapabilities) -> None:
    if not capabilities.supports_search_event_navigation:
        raise ParameterValidationError(
            "Search event navigation is not supported by the selected model profile."
        )


def normalize_search_mode(mode: str) -> str:
    if not isinstance(mode, str) or mode not in _SEARCH_MODE_COMMANDS:
        raise ParameterValidationError(
            "Search mode must be one of: " + ", ".join(SEARCH_MODES) + "."
        )
    return mode


def validate_search_mode(mode: str, capabilities: ScopeCapabilities) -> str:
    require_search_basic(capabilities)
    canonical = normalize_search_mode(mode)
    if canonical not in capabilities.search_modes:
        raise ParameterValidationError(
            f"Search mode {canonical!r} is not supported by the selected "
            f"{capabilities.series} model profile."
        )
    return canonical


def require_search_basic(capabilities: ScopeCapabilities) -> None:
    if not capabilities.supports_search_basic:
        raise ParameterValidationError(
            "Search Basic Pack v1 is not supported by the selected model profile."
        )


def validate_serial_search_bus(bus: int, capabilities: ScopeCapabilities) -> int:
    canonical_bus = validate_serial_bus(bus, capabilities)
    validate_search_mode(f"serial{canonical_bus}", capabilities)
    return canonical_bus


def validate_uart_search_mode(mode: str) -> str:
    if not isinstance(mode, str) or mode not in _UART_SEARCH_MODE_TOKENS:
        raise ParameterValidationError(
            "UART search mode must be one of: " + ", ".join(UART_SEARCH_MODES) + "."
        )
    return mode


def validate_uart_data(data: int) -> int:
    if isinstance(data, bool) or not isinstance(data, int) or data < 0 or data > 255:
        raise ParameterValidationError(
            "UART search data must be an integer from 0 through 255."
        )
    return data


def validate_search_qualifier(qualifier: str) -> str:
    if not isinstance(qualifier, str) or qualifier not in _SEARCH_QUALIFIER_TOKENS:
        raise ParameterValidationError(
            "Search qualifier must be one of: " + ", ".join(SEARCH_QUALIFIERS) + "."
        )
    return qualifier


def validate_i2c_search_mode(mode: str) -> str:
    if not isinstance(mode, str) or mode not in _I2C_SEARCH_MODE_TOKENS:
        raise ParameterValidationError(
            "I2C search mode must be one of: " + ", ".join(I2C_SEARCH_MODES) + "."
        )
    return mode


def validate_i2c_pattern_value(val: int, name: str) -> int:
    if isinstance(val, bool) or not isinstance(val, int):
        raise ParameterValidationError(f"I2C search {name} must be an integer.")
    return val


def validate_spi_search_mode(mode: str) -> str:
    if not isinstance(mode, str) or mode not in _SPI_SEARCH_MODE_TOKENS:
        raise ParameterValidationError(
            "SPI search mode must be one of: " + ", ".join(SPI_SEARCH_MODES) + "."
        )
    return mode


def validate_pattern_hex_x(pattern: str, name: str = "pattern") -> str:
    if not isinstance(pattern, str):
        raise ParameterValidationError(f"{name} pattern must be a string.")
    cleaned = pattern.strip()
    if not (cleaned.startswith("0x") or cleaned.startswith("0X")):
        raise ParameterValidationError(
            f"{name} pattern must start with '0x' or '0X'."
        )
    raw_hex = cleaned[2:]
    if not raw_hex or not re.fullmatch(r"[0-9a-fA-FxX]+", raw_hex):
        raise ParameterValidationError(
            f"{name} pattern must contain at least one hexadecimal character or 'X' wildcard after '0x'."
        )
    return f"0x{raw_hex.upper()}"


def validate_spi_width(width: int) -> int:
    if isinstance(width, bool) or not isinstance(width, int) or width < 1 or width > 10:
        raise ParameterValidationError(
            "SPI search width must be an integer from 1 through 10."
        )
    return width


def validate_can_search_mode(mode: str) -> str:
    if not isinstance(mode, str) or mode not in _CAN_SEARCH_MODE_TOKENS:
        raise ParameterValidationError(
            "CAN search mode must be one of: " + ", ".join(CAN_SEARCH_MODES) + "."
        )
    return mode


def validate_can_data_length(length: int) -> int:
    if isinstance(length, bool) or not isinstance(length, int) or length < 1 or length > 8:
        raise ParameterValidationError(
            "CAN search data length must be an integer from 1 through 8."
        )
    return length


def validate_can_id_mode(mode: str) -> str:
    if not isinstance(mode, str) or mode not in _CAN_SEARCH_ID_MODE_TOKENS:
        raise ParameterValidationError(
            "CAN search ID mode must be one of: " + ", ".join(CAN_SEARCH_ID_MODES) + "."
        )
    return mode


def serial_search_uart_configure_commands(
    bus: int,
    mode: str,
    data: int | None = None,
    qualifier: str | None = None,
) -> list[str]:
    scpi_mode = _UART_SEARCH_MODE_TOKENS[mode]
    cmds = [
        search_state_command(True),
        search_mode_command(f"serial{bus}"),
        f":SEARch:SERial:UART:MODE {scpi_mode}",
    ]
    if data is not None:
        cmds.append(f":SEARch:SERial:UART:DATA {data}")
    if qualifier is not None:
        scpi_qual = _SEARCH_QUALIFIER_TOKENS[qualifier]
        cmds.append(f":SEARch:SERial:UART:QUALifier {scpi_qual}")
    return cmds


def serial_search_uart_query_commands(bus: int) -> list[str]:
    return [
        search_state_query(),
        search_mode_query(),
        ":SEARch:SERial:UART:MODE?",
        ":SEARch:SERial:UART:DATA?",
        ":SEARch:SERial:UART:QUALifier?",
    ]


def serial_search_i2c_configure_commands(
    bus: int,
    mode: str,
    address: int | None = None,
    data: int | None = None,
    data2: int | None = None,
    qualifier: str | None = None,
) -> list[str]:
    scpi_mode = _I2C_SEARCH_MODE_TOKENS[mode]
    cmds = [
        search_state_command(True),
        search_mode_command(f"serial{bus}"),
        f":SEARch:SERial:IIC:MODE {scpi_mode}",
    ]
    if address is not None:
        cmds.append(f":SEARch:SERial:IIC:PATTern:ADDRess {address}")
    if data is not None:
        cmds.append(f":SEARch:SERial:IIC:PATTern:DATA {data}")
    if data2 is not None:
        cmds.append(f":SEARch:SERial:IIC:PATTern:DATA2 {data2}")
    if qualifier is not None:
        scpi_qual = _SEARCH_QUALIFIER_TOKENS[qualifier]
        cmds.append(f":SEARch:SERial:IIC:QUALifier {scpi_qual}")
    return cmds


def serial_search_i2c_query_commands(bus: int) -> list[str]:
    return [
        search_state_query(),
        search_mode_query(),
        ":SEARch:SERial:IIC:MODE?",
        ":SEARch:SERial:IIC:PATTern:ADDRess?",
        ":SEARch:SERial:IIC:PATTern:DATA?",
        ":SEARch:SERial:IIC:PATTern:DATA2?",
        ":SEARch:SERial:IIC:QUALifier?",
    ]


def serial_search_spi_configure_commands(
    bus: int,
    mode: str,
    data: str | None = None,
    width: int | None = None,
) -> list[str]:
    scpi_mode = _SPI_SEARCH_MODE_TOKENS[mode]
    cmds = [
        search_state_command(True),
        search_mode_command(f"serial{bus}"),
        f":SEARch:SERial:SPI:MODE {scpi_mode}",
    ]
    if data is not None:
        cmds.append(f':SEARch:SERial:SPI:PATTern:DATA "{data}"')
    if width is not None:
        cmds.append(f":SEARch:SERial:SPI:PATTern:WIDTh {width}")
    return cmds


def serial_search_spi_query_commands(bus: int) -> list[str]:
    return [
        search_state_query(),
        search_mode_query(),
        ":SEARch:SERial:SPI:MODE?",
        ":SEARch:SERial:SPI:PATTern:DATA?",
        ":SEARch:SERial:SPI:PATTern:WIDTh?",
    ]


def serial_search_can_configure_commands(
    bus: int,
    mode: str,
    data: str | None = None,
    data_length: int | None = None,
    id_val: str | None = None,
    id_mode: str | None = None,
) -> list[str]:
    scpi_mode = _CAN_SEARCH_MODE_TOKENS[mode]
    cmds = [
        search_state_command(True),
        search_mode_command(f"serial{bus}"),
        f":SEARch:SERial:CAN:MODE {scpi_mode}",
    ]
    if data is not None:
        cmds.append(f':SEARch:SERial:CAN:PATTern:DATA "{data}"')
    if data_length is not None:
        cmds.append(f":SEARch:SERial:CAN:PATTern:DATA:LENGth {data_length}")
    if id_val is not None:
        cmds.append(f':SEARch:SERial:CAN:PATTern:ID "{id_val}"')
    if id_mode is not None:
        scpi_id_mode = _CAN_SEARCH_ID_MODE_TOKENS[id_mode]
        cmds.append(f":SEARch:SERial:CAN:PATTern:ID:MODE {scpi_id_mode}")
    return cmds


def serial_search_can_query_commands(bus: int) -> list[str]:
    return [
        search_state_query(),
        search_mode_query(),
        ":SEARch:SERial:CAN:MODE?",
        ":SEARch:SERial:CAN:PATTern:DATA?",
        ":SEARch:SERial:CAN:PATTern:DATA:LENGth?",
        ":SEARch:SERial:CAN:PATTern:ID?",
        ":SEARch:SERial:CAN:PATTern:ID:MODE?",
    ]


def parse_search_state(raw: str) -> bool:
    normalized = raw.strip().upper()
    if normalized in {"1", "+1", "ON"}:
        return True
    if normalized in {"0", "+0", "OFF"}:
        return False
    raise SearchResponseError(f"Could not parse search state response: {raw!r}")


def parse_search_mode(raw: str) -> tuple[str | None, bool]:
    normalized = raw.strip().upper()
    if normalized == "OFF":
        return None, False
    try:
        return _SEARCH_MODE_READBACKS[normalized], True
    except KeyError as exc:
        raise SearchResponseError(f"Could not parse search mode response: {raw!r}") from exc


def parse_search_count(raw: str) -> SearchCountState:
    raw_count = raw.strip()
    try:
        count = int(raw_count)
    except ValueError as exc:
        raise SearchResponseError(
            f"Could not parse search count response: {raw!r}"
        ) from exc
    if count < 0:
        raise SearchResponseError(f"Could not parse search count response: {raw!r}")
    return SearchCountState(count=count, raw_count=raw_count)


def parse_search_event(raw: str) -> SearchEventState:
    raw_event = raw.strip()
    try:
        event = int(raw_event)
    except ValueError as exc:
        raise SearchResponseError(
            f"Could not parse search event response: {raw!r}"
        ) from exc
    if event < 0:
        raise SearchResponseError(f"Could not parse search event response: {raw!r}")
    return SearchEventState(event=event, raw=raw_event)


def parse_uart_search_mode(raw: str) -> tuple[str | None, str]:
    cleaned = raw.strip()
    upper = cleaned.upper()
    try:
        return _UART_SEARCH_MODE_READBACKS[upper], cleaned
    except KeyError as exc:
        raise SearchResponseError(
            f"Could not parse UART serial search mode response: {cleaned!r}"
        ) from exc


def parse_search_qualifier(raw: str) -> tuple[str | None, str]:
    cleaned = raw.strip()
    upper = cleaned.upper()
    try:
        return _SEARCH_QUALIFIER_READBACKS[upper], cleaned
    except KeyError as exc:
        raise SearchResponseError(
            f"Could not parse search qualifier response: {cleaned!r}"
        ) from exc


def parse_i2c_search_mode(raw: str) -> tuple[str | None, str]:
    cleaned = raw.strip()
    upper = cleaned.upper()
    if upper in _I2C_SEARCH_MODE_UNSUPPORTED_READBACKS:
        return None, cleaned
    try:
        return _I2C_SEARCH_MODE_READBACKS[upper], cleaned
    except KeyError as exc:
        raise SearchResponseError(
            f"Could not parse I2C serial search mode response: {cleaned!r}"
        ) from exc


def parse_spi_search_mode(raw: str) -> tuple[str | None, str]:
    cleaned = raw.strip()
    upper = cleaned.upper()
    try:
        return _SPI_SEARCH_MODE_READBACKS[upper], cleaned
    except KeyError as exc:
        raise SearchResponseError(
            f"Could not parse SPI serial search mode response: {cleaned!r}"
        ) from exc


def parse_can_search_mode(raw: str) -> tuple[str | None, str]:
    cleaned = raw.strip()
    upper = cleaned.upper()
    if upper in _CAN_SEARCH_MODE_UNSUPPORTED_READBACKS:
        return None, cleaned
    try:
        return _CAN_SEARCH_MODE_READBACKS[upper], cleaned
    except KeyError as exc:
        raise SearchResponseError(
            f"Could not parse CAN serial search mode response: {cleaned!r}"
        ) from exc


def parse_can_id_mode(raw: str) -> tuple[str | None, str]:
    cleaned = raw.strip()
    upper = cleaned.upper()
    try:
        return _CAN_SEARCH_ID_MODE_READBACKS[upper], cleaned
    except KeyError as exc:
        raise SearchResponseError(
            f"Could not parse CAN ID mode response: {cleaned!r}"
        ) from exc


def _parse_integer_query(
    raw: str,
    field: str,
    validator=None,
) -> tuple[int, str]:
    cleaned = raw.strip()
    try:
        value = int(cleaned)
    except ValueError as exc:
        raise SearchResponseError(
            f"Could not parse {field} response: {cleaned!r}"
        ) from exc
    if validator is not None:
        try:
            validator(value)
        except ParameterValidationError as exc:
            raise SearchResponseError(
                f"Could not parse {field} response: {cleaned!r}"
            ) from exc
    return value, cleaned


def parse_uart_data_query(raw: str) -> tuple[int, str]:
    return _parse_integer_query(raw, "UART serial search data", validate_uart_data)


def parse_i2c_pattern_query(raw: str, field: str) -> tuple[int, str]:
    return _parse_integer_query(raw, field)


def parse_spi_width_query(raw: str) -> tuple[int, str]:
    return _parse_integer_query(raw, "SPI serial search width", validate_spi_width)


def parse_can_data_length_query(raw: str) -> tuple[int, str]:
    return _parse_integer_query(
        raw, "CAN serial search data length", validate_can_data_length
    )


def parse_int_query(raw: str) -> tuple[int, str]:
    return _parse_integer_query(raw, "integer")


def parse_pattern_query(raw: str) -> tuple[str | None, str]:
    cleaned = raw.strip()
    if not cleaned:
        raise SearchResponseError(
            f"Could not parse serial search pattern response: {cleaned!r}"
        )
    if cleaned[0] in {'"', "'"}:
        quote = cleaned[0]
        if len(cleaned) < 2 or cleaned[-1] != quote:
            raise SearchResponseError(
                f"Could not parse serial search pattern response: {cleaned!r}"
            )
        unquoted = cleaned[1:-1]
    elif cleaned[-1] in {'"', "'"}:
        raise SearchResponseError(
            f"Could not parse serial search pattern response: {cleaned!r}"
        )
    else:
        unquoted = cleaned
    try:
        canonical = validate_pattern_hex_x(unquoted, "serial search")
        return canonical, cleaned
    except ParameterValidationError as exc:
        raise SearchResponseError(
            f"Could not parse serial search pattern response: {cleaned!r}"
        ) from exc
