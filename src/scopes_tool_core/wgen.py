"""Basic waveform generator controls for supported InfiniiVision X-Series scopes."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .capabilities import ScopeCapabilities
from .errors import ParameterValidationError, WgenResponseError
from .scpi import SCPIClient


WGEN_FUNCTION_TOKENS = {
    "sine": "SINusoid",
    "square": "SQUare",
    "ramp": "RAMP",
    "pulse": "PULSe",
    "noise": "NOISe",
    "dc": "DC",
}
WGEN_FUNCTIONS = tuple(WGEN_FUNCTION_TOKENS)
WGEN_LOAD_TOKENS = {
    "one-meg": "ONEMeg",
    "fifty": "FIFTy",
}
WGEN_LOADS = tuple(WGEN_LOAD_TOKENS)

_WGEN_FUNCTION_READBACKS = {
    "SIN": "sine",
    "SINUSOID": "sine",
    "SQU": "square",
    "SQUARE": "square",
    "RAMP": "ramp",
    "PULS": "pulse",
    "PULSE": "pulse",
    "NOIS": "noise",
    "NOISE": "noise",
    "DC": "dc",
}
_WGEN_LOAD_READBACKS = {
    "ONEM": "one-meg",
    "ONEMEG": "one-meg",
    "1MEG": "one-meg",
    "1E6": "one-meg",
    "1E+6": "one-meg",
    "1000000": "one-meg",
    "FIFT": "fifty",
    "FIFTY": "fifty",
    "50": "fifty",
}


@dataclass(frozen=True)
class WgenOutputState:
    enabled: bool
    output_raw: str

    def to_json(self) -> dict[str, object]:
        return {"enabled": self.enabled, "output_raw": self.output_raw}


@dataclass(frozen=True)
class WgenFunctionState:
    function: str | None
    function_scpi: str | None
    function_raw: str

    def to_json(self) -> dict[str, object]:
        return {
            "function": self.function,
            "function_scpi": self.function_scpi,
            "function_raw": self.function_raw,
        }


@dataclass(frozen=True)
class WgenFrequencyState:
    frequency_hz: float
    frequency_raw: str

    def to_json(self) -> dict[str, object]:
        return {
            "frequency_hz": self.frequency_hz,
            "frequency_raw": self.frequency_raw,
        }


@dataclass(frozen=True)
class WgenVoltageState:
    amplitude_volts: float
    voltage_raw: str

    def to_json(self) -> dict[str, object]:
        return {
            "amplitude_volts": self.amplitude_volts,
            "voltage_raw": self.voltage_raw,
        }


@dataclass(frozen=True)
class WgenOffsetState:
    offset_volts: float
    offset_raw: str

    def to_json(self) -> dict[str, object]:
        return {"offset_volts": self.offset_volts, "offset_raw": self.offset_raw}


@dataclass(frozen=True)
class WgenLoadState:
    load: str
    load_scpi: str
    load_raw: str

    def to_json(self) -> dict[str, object]:
        return {
            "load": self.load,
            "load_scpi": self.load_scpi,
            "load_raw": self.load_raw,
        }


@dataclass(frozen=True)
class WgenState:
    enabled: bool
    output_raw: str
    function: str | None
    function_scpi: str | None
    function_raw: str
    frequency_hz: float
    frequency_raw: str
    amplitude_volts: float
    voltage_raw: str
    offset_volts: float
    offset_raw: str
    load: str
    load_scpi: str
    load_raw: str

    def to_json(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "output_raw": self.output_raw,
            "function": self.function,
            "function_scpi": self.function_scpi,
            "function_raw": self.function_raw,
            "frequency_hz": self.frequency_hz,
            "frequency_raw": self.frequency_raw,
            "amplitude_volts": self.amplitude_volts,
            "voltage_raw": self.voltage_raw,
            "offset_volts": self.offset_volts,
            "offset_raw": self.offset_raw,
            "load": self.load,
            "load_scpi": self.load_scpi,
            "load_raw": self.load_raw,
        }


class WgenController:
    """Controller for waveform generator controls."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        _wgen_root(capabilities)
        self.scpi = scpi
        self.capabilities = capabilities

    def configure_output(self, enabled: bool) -> None:
        self.scpi.write(wgen_output_command(enabled, self.capabilities))

    def query_output(self) -> WgenOutputState:
        raw = self.scpi.query(wgen_output_query(self.capabilities)).strip()
        return WgenOutputState(parse_wgen_bool(raw), raw)

    def configure_function(self, function: str) -> None:
        self.scpi.write(wgen_function_command(function, self.capabilities))

    def query_function(self) -> WgenFunctionState:
        raw = self.scpi.query(wgen_function_query(self.capabilities)).strip()
        function = parse_wgen_function(raw)
        token = None if function is None else WGEN_FUNCTION_TOKENS[function]
        return WgenFunctionState(function, token, raw)

    def configure_frequency(self, frequency_hz: float) -> None:
        self.scpi.write(wgen_frequency_command(frequency_hz, self.capabilities))

    def query_frequency(self) -> WgenFrequencyState:
        raw = self.scpi.query(wgen_frequency_query(self.capabilities)).strip()
        return WgenFrequencyState(parse_wgen_number(raw, "frequency"), raw)

    def configure_voltage(self, amplitude_volts: float) -> None:
        self.scpi.write(wgen_voltage_command(amplitude_volts, self.capabilities))

    def query_voltage(self) -> WgenVoltageState:
        raw = self.scpi.query(wgen_voltage_query(self.capabilities)).strip()
        return WgenVoltageState(parse_wgen_number(raw, "voltage"), raw)

    def configure_offset(self, offset_volts: float) -> None:
        self.scpi.write(wgen_offset_command(offset_volts, self.capabilities))

    def query_offset(self) -> WgenOffsetState:
        raw = self.scpi.query(wgen_offset_query(self.capabilities)).strip()
        return WgenOffsetState(parse_wgen_number(raw, "offset"), raw)

    def configure_load(self, load: str) -> None:
        self.scpi.write(wgen_load_command(load, self.capabilities))

    def query_load(self) -> WgenLoadState:
        raw = self.scpi.query(wgen_load_query(self.capabilities)).strip()
        load = parse_wgen_load(raw)
        return WgenLoadState(load, WGEN_LOAD_TOKENS[load], raw)

    def query(self) -> WgenState:
        output = self.query_output()
        function = self.query_function()
        frequency = self.query_frequency()
        voltage = self.query_voltage()
        offset = self.query_offset()
        load = self.query_load()
        return WgenState(
            enabled=output.enabled,
            output_raw=output.output_raw,
            function=function.function,
            function_scpi=function.function_scpi,
            function_raw=function.function_raw,
            frequency_hz=frequency.frequency_hz,
            frequency_raw=frequency.frequency_raw,
            amplitude_volts=voltage.amplitude_volts,
            voltage_raw=voltage.voltage_raw,
            offset_volts=offset.offset_volts,
            offset_raw=offset.offset_raw,
            load=load.load,
            load_scpi=load.load_scpi,
            load_raw=load.load_raw,
        )


def wgen_output_command(enabled: bool, capabilities: ScopeCapabilities) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("WGEN output enabled value must be a boolean.")
    return f"{_wgen_root(capabilities)}:OUTPut {'ON' if enabled else 'OFF'}"


def wgen_output_query(capabilities: ScopeCapabilities) -> str:
    return f"{_wgen_root(capabilities)}:OUTPut?"


def wgen_function_command(function: str, capabilities: ScopeCapabilities) -> str:
    function = validate_wgen_function(function)
    return f"{_wgen_root(capabilities)}:FUNCtion {WGEN_FUNCTION_TOKENS[function]}"


def wgen_function_query(capabilities: ScopeCapabilities) -> str:
    return f"{_wgen_root(capabilities)}:FUNCtion?"


def wgen_frequency_command(frequency_hz: float, capabilities: ScopeCapabilities) -> str:
    value = validate_wgen_frequency(frequency_hz)
    return f"{_wgen_root(capabilities)}:FREQuency {value:g}"


def wgen_frequency_query(capabilities: ScopeCapabilities) -> str:
    return f"{_wgen_root(capabilities)}:FREQuency?"


def wgen_voltage_command(amplitude_volts: float, capabilities: ScopeCapabilities) -> str:
    value = validate_wgen_amplitude(amplitude_volts)
    return f"{_wgen_root(capabilities)}:VOLTage {value:g}"


def wgen_voltage_query(capabilities: ScopeCapabilities) -> str:
    return f"{_wgen_root(capabilities)}:VOLTage?"


def wgen_offset_command(offset_volts: float, capabilities: ScopeCapabilities) -> str:
    value = validate_wgen_offset(offset_volts)
    return f"{_wgen_root(capabilities)}:VOLTage:OFFSet {value:g}"


def wgen_offset_query(capabilities: ScopeCapabilities) -> str:
    return f"{_wgen_root(capabilities)}:VOLTage:OFFSet?"


def wgen_load_command(load: str, capabilities: ScopeCapabilities) -> str:
    load = validate_wgen_load(load)
    return f"{_wgen_root(capabilities)}:OUTPut:LOAD {WGEN_LOAD_TOKENS[load]}"


def wgen_load_query(capabilities: ScopeCapabilities) -> str:
    return f"{_wgen_root(capabilities)}:OUTPut:LOAD?"


def wgen_query_commands(capabilities: ScopeCapabilities) -> list[str]:
    return [
        wgen_output_query(capabilities),
        wgen_function_query(capabilities),
        wgen_frequency_query(capabilities),
        wgen_voltage_query(capabilities),
        wgen_offset_query(capabilities),
        wgen_load_query(capabilities),
    ]


def validate_wgen_function(function: str) -> str:
    if not isinstance(function, str) or function not in WGEN_FUNCTION_TOKENS:
        raise ParameterValidationError(
            "WGEN function must be one of: " + ", ".join(WGEN_FUNCTIONS) + "."
        )
    return function


def validate_wgen_frequency(frequency_hz: float) -> float:
    value = _validate_wgen_numeric(frequency_hz, "frequency")
    if value <= 0.0:
        raise ParameterValidationError("WGEN frequency must be greater than zero.")
    return value


def validate_wgen_amplitude(amplitude_volts: float) -> float:
    value = _validate_wgen_numeric(amplitude_volts, "amplitude")
    if not 0.0 < value <= 5.0:
        raise ParameterValidationError(
            "WGEN amplitude must be greater than zero and at most 5.0 volts."
        )
    return value


def validate_wgen_offset(offset_volts: float) -> float:
    value = _validate_wgen_numeric(offset_volts, "offset")
    if not -2.5 <= value <= 2.5:
        raise ParameterValidationError(
            "WGEN offset must be between -2.5 and 2.5 volts."
        )
    return value


def validate_wgen_load(load: str) -> str:
    if not isinstance(load, str) or load not in WGEN_LOAD_TOKENS:
        raise ParameterValidationError(
            "WGEN load must be one of: " + ", ".join(WGEN_LOADS) + "."
        )
    return load


def parse_wgen_bool(raw: str) -> bool:
    normalized = raw.strip().upper()
    if normalized in {"1", "+1", "ON", "TRUE"}:
        return True
    if normalized in {"0", "+0", "OFF", "FALSE"}:
        return False
    raise WgenResponseError(f"Could not parse WGEN output response: {raw!r}")


def parse_wgen_function(raw: str) -> str | None:
    return _WGEN_FUNCTION_READBACKS.get(raw.strip().upper())


def parse_wgen_load(raw: str) -> str:
    normalized = raw.strip().upper().replace(" ", "")
    load = _WGEN_LOAD_READBACKS.get(normalized)
    if load is not None:
        return load
    try:
        numeric = float(normalized)
    except ValueError:
        numeric = math.nan
    if numeric == 1_000_000.0:
        return "one-meg"
    if numeric == 50.0:
        return "fifty"
    raise WgenResponseError(f"Could not parse WGEN load response: {raw!r}")


def parse_wgen_number(raw: str, field: str) -> float:
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise WgenResponseError(
            f"Could not parse WGEN {field} response: {raw!r}"
        ) from exc
    if not math.isfinite(value):
        raise WgenResponseError(f"Could not parse WGEN {field} response: {raw!r}")
    return value


def _validate_wgen_numeric(value: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParameterValidationError(f"WGEN {field} must be a number.")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ParameterValidationError(f"WGEN {field} must be finite.")
    return normalized


def _wgen_root(capabilities: ScopeCapabilities) -> str:
    if not capabilities.supports_wgen or not capabilities.wgen_scpi_root:
        raise ParameterValidationError(
            "WGEN is not supported by this model profile."
        )
    return capabilities.wgen_scpi_root
