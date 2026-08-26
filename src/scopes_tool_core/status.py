"""Instrument status and error parsing helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass

from .errors import StatusResponseError, SystemErrorParseError
from .scpi import SCPIClient


SYSTEM_CLEAR_STATUS_COMMAND = "*CLS"
SYSTEM_OPC_QUERY = "*OPC?"
SYSTEM_STATUS_BYTE_QUERY = "*STB?"
SYSTEM_STANDARD_EVENT_QUERY = "*ESR?"
SYSTEM_OPERATION_STATUS_QUERY = ":OPERegister:CONDition?"
SYSTEM_OPTIONS_QUERY = "*OPT?"


@dataclass(frozen=True)
class SystemErrorEntry:
    """One entry read from the oscilloscope system error queue."""

    code: int
    message: str
    raw: str

    @property
    def is_error(self) -> bool:
        """Return whether this entry represents an instrument error."""

        return self.code != 0

    def format(self) -> str:
        """Return a stable human-readable representation."""

        return f'{self.code:+d}, "{self.message}"'


@dataclass(frozen=True)
class OperationCompleteState:
    """Successful `*OPC?` completion state."""

    complete: bool
    raw: str

    def to_json(self) -> dict[str, object]:
        return {"complete": self.complete, "raw": self.raw}


@dataclass(frozen=True)
class StatusRegisterState:
    """Parsed integer status register with stable low-to-high set bits."""

    value: int
    raw: str
    set_bits: tuple[int, ...]

    def to_json(self) -> dict[str, object]:
        return {"value": self.value, "raw": self.raw, "set_bits": self.set_bits}


@dataclass(frozen=True)
class SystemOptionsState:
    """Parsed comma-separated `*OPT?` response."""

    options: tuple[str, ...]
    raw: str

    def to_json(self) -> dict[str, object]:
        return {"raw": self.raw, "options": self.options}


class StatusController:
    """Controller for system and status controls."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def clear_status(self) -> None:
        self.scpi.write(system_clear_status_command())

    def query_operation_complete(self) -> OperationCompleteState:
        return parse_operation_complete(self.scpi.query(system_opc_query()))

    def query_status_byte(self) -> StatusRegisterState:
        return parse_status_register(self.scpi.query(system_status_byte_query()), maximum=255)

    def query_standard_event_status(self) -> StatusRegisterState:
        return parse_status_register(
            self.scpi.query(system_standard_event_query()), maximum=255
        )

    def query_operation_status(self) -> StatusRegisterState:
        return parse_status_register(
            self.scpi.query(system_operation_status_query()), maximum=65535
        )

    def query_system_options(self) -> SystemOptionsState:
        return parse_system_options(self.scpi.query(system_options_query()))


def system_clear_status_command() -> str:
    return SYSTEM_CLEAR_STATUS_COMMAND


def system_opc_query() -> str:
    return SYSTEM_OPC_QUERY


def system_status_byte_query() -> str:
    return SYSTEM_STATUS_BYTE_QUERY


def system_standard_event_query() -> str:
    return SYSTEM_STANDARD_EVENT_QUERY


def system_operation_status_query() -> str:
    return SYSTEM_OPERATION_STATUS_QUERY


def system_options_query() -> str:
    return SYSTEM_OPTIONS_QUERY


def parse_operation_complete(response: str) -> OperationCompleteState:
    """Parse the only successful `*OPC?` response supported by this pack."""

    raw = response.strip()
    if raw != "1":
        raise StatusResponseError(
            f"Invalid operation complete response; expected '1': {response!r}"
        )
    return OperationCompleteState(complete=True, raw=raw)


def parse_status_register(response: str, *, maximum: int) -> StatusRegisterState:
    """Parse one bounded non-negative integer status register response."""

    raw = response.strip()
    if not raw:
        raise StatusResponseError("Status register response cannot be empty.")
    try:
        value = int(raw, 10)
    except ValueError as exc:
        raise StatusResponseError(
            f"Invalid integer status register response: {response!r}"
        ) from exc
    if value < 0 or value > maximum:
        raise StatusResponseError(
            f"Status register response must be in range 0..{maximum}: {response!r}"
        )
    return StatusRegisterState(
        value=value,
        raw=raw,
        set_bits=tuple(bit for bit in range(maximum.bit_length()) if value & (1 << bit)),
    )


def parse_system_options(response: str) -> SystemOptionsState:
    """Parse trimmed comma-separated option tokens while preserving the raw value."""

    raw = response.strip()
    if not raw:
        raise StatusResponseError("System options response cannot be empty.")
    options = tuple(part.strip() for part in raw.split(","))
    if any(not option for option in options):
        raise StatusResponseError(f"Invalid system options response: {response!r}")
    return SystemOptionsState(options=options, raw=raw)


def parse_system_error(response: str) -> SystemErrorEntry:
    """Parse one `:SYSTem:ERRor?` response."""

    raw = response.strip()
    try:
        row = next(csv.reader([raw], skipinitialspace=True))
    except csv.Error as exc:
        raise SystemErrorParseError(f"Invalid system error response: {response!r}") from exc

    if len(row) != 2:
        raise SystemErrorParseError(f"Invalid system error response: {response!r}")

    code_text, message = row
    try:
        code = int(code_text)
    except ValueError as exc:
        raise SystemErrorParseError(f"Invalid system error code: {code_text!r}") from exc

    return SystemErrorEntry(code=code, message=message, raw=raw)
