"""Common DVM controls for supported InfiniiVision X-Series scopes."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .capabilities import ScopeCapabilities
from .channel import validate_analog_channel
from .errors import DvmResponseError, ParameterValidationError
from .scpi import SCPIClient


DVM_MODES = ("dc", "dc-rms", "ac-rms")
DVM_INVALID_SENTINEL_ABS_MIN = 9.0e37
DVM_INVALID_SENTINEL_REASON = "invalid DVM sentinel"
DVM_NONFINITE_REASON = "non-finite DVM value"

_DVM_MODE_COMMANDS = {
    "dc": "DC",
    "dc-rms": "DCRMs",
    "ac-rms": "ACRMs",
}

_DVM_MODE_READBACKS = {
    "DC": "dc",
    "DCRM": "dc-rms",
    "DCRMS": "dc-rms",
    "ACRM": "ac-rms",
    "ACRMS": "ac-rms",
}


@dataclass(frozen=True)
class DvmBooleanState:
    enabled: bool
    raw_enabled: str

    def to_json(self) -> dict[str, object]:
        return {"enabled": self.enabled, "raw_enabled": self.raw_enabled}


@dataclass(frozen=True)
class DvmSourceState:
    source_channel: int
    raw_source: str

    def to_json(self) -> dict[str, object]:
        return {
            "source_channel": self.source_channel,
            "raw_source": self.raw_source,
        }


@dataclass(frozen=True)
class DvmModeState:
    mode: str
    raw_mode: str

    def to_json(self) -> dict[str, object]:
        return {"mode": self.mode, "raw_mode": self.raw_mode}


@dataclass(frozen=True)
class DvmAutoRangeState:
    auto_range_enabled: bool
    raw_auto_range: str

    def to_json(self) -> dict[str, object]:
        return {
            "auto_range_enabled": self.auto_range_enabled,
            "raw_auto_range": self.raw_auto_range,
        }


@dataclass(frozen=True)
class DvmReading:
    value: float | None
    raw_value: str
    valid: bool
    reason: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "value": self.value,
            "raw_value": self.raw_value,
            "valid": self.valid,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DvmState:
    enabled: bool
    source_channel: int
    mode: str
    auto_range_enabled: bool
    value: float | None
    valid: bool
    reason: str | None
    raw: dict[str, str]

    def to_json(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "source_channel": self.source_channel,
            "mode": self.mode,
            "auto_range_enabled": self.auto_range_enabled,
            "value": self.value,
            "valid": self.valid,
            "reason": self.reason,
            "raw": dict(self.raw),
        }


class DvmController:
    """Controller for DVM controls."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure_enable(self, enabled: bool) -> None:
        self.scpi.write(dvm_enable_command(enabled))

    def query_enable(self) -> DvmBooleanState:
        raw = self.scpi.query(dvm_enable_query()).strip()
        return DvmBooleanState(parse_dvm_bool(raw), raw)

    def configure_source(self, channel: int) -> None:
        self.scpi.write(dvm_source_command(channel, capabilities=self.capabilities))

    def query_source(self) -> DvmSourceState:
        raw = self.scpi.query(dvm_source_query()).strip()
        channel = parse_dvm_source(raw)
        validate_analog_channel(channel, self.capabilities)
        return DvmSourceState(channel, raw)

    def configure_mode(self, mode: str) -> None:
        self.scpi.write(dvm_mode_command(mode))

    def query_mode(self) -> DvmModeState:
        raw = self.scpi.query(dvm_mode_query()).strip()
        return DvmModeState(parse_dvm_mode(raw), raw)

    def configure_auto_range(self, enabled: bool) -> None:
        self.scpi.write(dvm_auto_range_command(enabled))

    def query_auto_range(self) -> DvmAutoRangeState:
        raw = self.scpi.query(dvm_auto_range_query()).strip()
        return DvmAutoRangeState(parse_dvm_bool(raw), raw)

    def query_current(self) -> DvmReading:
        return parse_dvm_current(self.scpi.query(dvm_current_query()))

    def query(self) -> DvmState:
        enabled = self.query_enable()
        source = self.query_source()
        mode = self.query_mode()
        auto_range = self.query_auto_range()
        current = self.query_current()
        return DvmState(
            enabled=enabled.enabled,
            source_channel=source.source_channel,
            mode=mode.mode,
            auto_range_enabled=auto_range.auto_range_enabled,
            value=current.value,
            valid=current.valid,
            reason=current.reason,
            raw={
                "enabled": enabled.raw_enabled,
                "source": source.raw_source,
                "mode": mode.raw_mode,
                "auto_range": auto_range.raw_auto_range,
                "current": current.raw_value,
            },
        )


def dvm_enable_command(enabled: bool) -> str:
    return f":DVM:ENABle {_dvm_bool_token(enabled)}"


def dvm_enable_query() -> str:
    return ":DVM:ENABle?"


def dvm_source_command(channel: int, *, capabilities: ScopeCapabilities) -> str:
    channel = validate_analog_channel(channel, capabilities)
    return f":DVM:SOURce CHANnel{channel}"


def dvm_source_query() -> str:
    return ":DVM:SOURce?"


def dvm_mode_command(mode: str) -> str:
    return f":DVM:MODE {normalize_dvm_mode(mode)}"


def dvm_mode_query() -> str:
    return ":DVM:MODE?"


def dvm_auto_range_command(enabled: bool) -> str:
    return f":DVM:ARANge {_dvm_bool_token(enabled)}"


def dvm_auto_range_query() -> str:
    return ":DVM:ARANge?"


def dvm_current_query() -> str:
    return ":DVM:CURRent?"


def dvm_query_commands() -> list[str]:
    return [
        dvm_enable_query(),
        dvm_source_query(),
        dvm_mode_query(),
        dvm_auto_range_query(),
        dvm_current_query(),
    ]


def normalize_dvm_mode(mode: str) -> str:
    if not isinstance(mode, str) or mode not in _DVM_MODE_COMMANDS:
        raise ParameterValidationError(
            "DVM mode must be one of: dc, dc-rms, ac-rms."
        )
    return _DVM_MODE_COMMANDS[mode]


def parse_dvm_mode(raw: str) -> str:
    try:
        return _DVM_MODE_READBACKS[raw.strip().upper()]
    except KeyError as exc:
        raise DvmResponseError(f"Could not parse DVM mode response: {raw!r}") from exc


def parse_dvm_bool(raw: str) -> bool:
    normalized = raw.strip().upper()
    if normalized in {"1", "+1", "ON"}:
        return True
    if normalized in {"0", "+0", "OFF"}:
        return False
    raise DvmResponseError(f"Could not parse DVM boolean response: {raw!r}")


def parse_dvm_source(raw: str) -> int:
    normalized = raw.strip().upper()
    for prefix in ("CHANNEL", "CHAN"):
        if normalized.startswith(prefix):
            suffix = normalized[len(prefix) :]
            if suffix.isdigit() and int(suffix) >= 1:
                return int(suffix)
    raise DvmResponseError(f"Could not parse DVM source response: {raw!r}")


def parse_dvm_current(raw: str) -> DvmReading:
    raw_value = raw.strip()
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise DvmResponseError(f"Could not parse DVM current response: {raw!r}") from exc
    if not math.isfinite(value):
        return DvmReading(None, raw_value, False, DVM_NONFINITE_REASON)
    if abs(value) >= DVM_INVALID_SENTINEL_ABS_MIN:
        return DvmReading(None, raw_value, False, DVM_INVALID_SENTINEL_REASON)
    return DvmReading(value, raw_value, True)


def _dvm_bool_token(enabled: bool) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("DVM enabled value must be a boolean.")
    return "1" if enabled else "0"
