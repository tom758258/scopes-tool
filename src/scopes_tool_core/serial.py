"""Model-guarded basic serial decode bus controls."""

from __future__ import annotations

from dataclasses import dataclass

from .capabilities import ScopeCapabilities
from .display import parse_display_label
from .errors import ParameterValidationError, SerialResponseError
from .scpi import SCPIClient


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


class SerialController:
    """Controller for Serial Basic P0."""

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
        return SerialDisplayState(
            bus=canonical_bus,
            enabled=parse_display_label(raw),
            raw_state=raw,
        )


def serial_bus_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}?"


def serial_mode_command(bus: int, mode: str) -> str:
    canonical_mode = normalize_serial_mode(mode)
    return f":SBUS{_validate_positive_bus(bus)}:MODE {SERIAL_MODE_TOKENS[canonical_mode]}"


def serial_mode_query(bus: int) -> str:
    return f":SBUS{_validate_positive_bus(bus)}:MODE?"


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


def require_serial_decode(capabilities: ScopeCapabilities) -> None:
    if not capabilities.supports_serial_decode:
        raise ParameterValidationError(
            "Serial Basic P0 is not supported by the selected model profile."
        )


def _validate_positive_bus(bus: int) -> int:
    if isinstance(bus, bool) or not isinstance(bus, int) or bus <= 0:
        raise ParameterValidationError("Serial bus must be a positive integer.")
    return bus
