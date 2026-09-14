"""Basic waveform generator controls for supported InfiniiVision X-Series scopes."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

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

# Programmer's Guide limits for the supported common waveform functions.
# Amplitude/offset limits below are High-Z values; 50 ohm contexts halve them
# (2000X states both pairs explicitly; 3000X/4000X tables carry the halving
# note on both columns). The 2000X guide gives no numeric offset range, so the
# historical +/-2.5 V check is preserved as a compatibility fallback there.
_WGEN_FREQUENCY_LIMITS_HZ = {
    "2000X": {
        "sine": (0.1, 20.0e6),
        "square": (0.1, 10.0e6),
        "ramp": (0.1, 100.0e3),
        "pulse": (0.1, 10.0e6),
    },
    "3000X": {
        "sine": (0.1, 20.0e6),
        "square": (0.1, 10.0e6),
        "ramp": (0.1, 200.0e3),
        "pulse": (0.1, 10.0e6),
    },
    "4000X": {
        "sine": (0.1, 20.0e6),
        "square": (0.1, 10.0e6),
        "ramp": (0.1, 200.0e3),
        "pulse": (0.1, 10.0e6),
    },
}
_WGEN_FREQUENCY_NA_FUNCTIONS = ("noise", "dc")
_WGEN_AMPLITUDE_LIMITS_VPP = {
    "2000X": (0.02, 5.0),
    "3000X": (0.02, 5.0),
    "4000X": (0.02, 10.0),
}
_WGEN_OFFSET_LIMITS_VOLTS = {
    # 2000X offset numeric range is not established by the available guide
    # text; None keeps the historical +/-2.5 V compatibility fallback.
    "2000X": None,
    "3000X": {
        "sine": 2.5,
        "square": 2.5,
        "ramp": 2.5,
        "pulse": 2.5,
        "noise": 2.5,
        "dc": 2.5,
    },
    "4000X": {
        "sine": 4.0,
        "square": 5.0,
        "ramp": 5.0,
        "pulse": 5.0,
        "noise": 5.0,
        "dc": 10.0,
    },
}
_WGEN_4000X_INTERACTION_AMPLITUDE_VPP = 0.04
_WGEN_4000X_INTERACTION_OFFSET_VOLTS = 0.5
_WGEN_HZ_LABELS = {
    0.1: "100 mHz",
    100.0e3: "100 kHz",
    200.0e3: "200 kHz",
    10.0e6: "10 MHz",
    20.0e6: "20 MHz",
}

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
        function = self.query_function().function
        self.scpi.write(
            wgen_frequency_command(
                frequency_hz, self.capabilities, function=function
            )
        )

    def query_frequency(self) -> WgenFrequencyState:
        raw = self.scpi.query(wgen_frequency_query(self.capabilities)).strip()
        return WgenFrequencyState(parse_wgen_number(raw, "frequency"), raw)

    def configure_voltage(self, amplitude_volts: float) -> None:
        function = self.query_function().function
        load = self.query_load().load
        if self.capabilities.series == "4000X":
            offset = self.query_offset().offset_volts
        else:
            offset = None
        self.scpi.write(
            wgen_voltage_command(
                amplitude_volts,
                self.capabilities,
                function=function,
                load=load,
                offset=offset,
            )
        )

    def query_voltage(self) -> WgenVoltageState:
        raw = self.scpi.query(wgen_voltage_query(self.capabilities)).strip()
        return WgenVoltageState(parse_wgen_number(raw, "voltage"), raw)

    def configure_offset(self, offset_volts: float) -> None:
        function = self.query_function().function
        load = self.query_load().load
        amplitude = (
            self.query_voltage().amplitude_volts
            if self.capabilities.series == "4000X"
            else None
        )
        self.scpi.write(
            wgen_offset_command(
                offset_volts,
                self.capabilities,
                function=function,
                load=load,
                amplitude=amplitude,
            )
        )

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


def wgen_frequency_command(
    frequency_hz: float,
    capabilities: ScopeCapabilities,
    *,
    function: str | None = None,
) -> str:
    value = validate_wgen_frequency(
        frequency_hz, series=capabilities.series, function=function
    )
    return f"{_wgen_root(capabilities)}:FREQuency {value:g}"


def wgen_frequency_query(capabilities: ScopeCapabilities) -> str:
    return f"{_wgen_root(capabilities)}:FREQuency?"


def wgen_voltage_command(
    amplitude_volts: float,
    capabilities: ScopeCapabilities,
    *,
    function: str | None = None,
    load: str | None = None,
    offset: float | None = None,
) -> str:
    value = validate_wgen_amplitude(
        amplitude_volts,
        series=capabilities.series,
        function=function,
        load=load,
        offset=offset,
    )
    return f"{_wgen_root(capabilities)}:VOLTage {value:g}"


def wgen_voltage_query(capabilities: ScopeCapabilities) -> str:
    return f"{_wgen_root(capabilities)}:VOLTage?"


def wgen_offset_command(
    offset_volts: float,
    capabilities: ScopeCapabilities,
    *,
    function: str | None = None,
    load: str | None = None,
    amplitude: float | None = None,
) -> str:
    value = validate_wgen_offset(
        offset_volts,
        series=capabilities.series,
        function=function,
        load=load,
        amplitude=amplitude,
    )
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


def validate_wgen_frequency(
    frequency_hz: float,
    *,
    series: str | None = None,
    function: str | None = None,
) -> float:
    value = _validate_wgen_numeric(frequency_hz, "frequency")
    if series is None:
        # Legacy context-free validation.
        if value <= 0.0:
            raise ParameterValidationError("WGEN frequency must be greater than zero.")
        return value
    limits = _wgen_series_table(series, _WGEN_FREQUENCY_LIMITS_HZ, "frequency")
    if function is None:
        # Series planning envelope across the supported common functions.
        lower = min(lower for lower, _ in limits.values())
        upper = max(upper for _, upper in limits.values())
        label = "the current waveform"
    elif function in _WGEN_FREQUENCY_NA_FUNCTIONS:
        raise ParameterValidationError(
            f"WGEN frequency is not applicable to the {function} waveform."
        )
    elif function in limits:
        lower, upper = limits[function]
        label = f"the {function} waveform"
    else:
        raise ParameterValidationError(f"Unknown WGEN function: {function!r}.")
    if not lower <= value <= upper:
        raise ParameterValidationError(
            f"WGEN frequency must be between {_format_wgen_hz(lower)} and "
            f"{_format_wgen_hz(upper)} for {label} on {series}."
        )
    return value


def validate_wgen_amplitude(
    amplitude_volts: float,
    *,
    series: str | None = None,
    function: str | None = None,
    load: str | None = None,
    offset: float | None = None,
) -> float:
    value = _validate_wgen_numeric(amplitude_volts, "amplitude")
    if series is None:
        # Legacy context-free validation.
        if not 0.0 < value <= 5.0:
            raise ParameterValidationError(
                "WGEN amplitude must be greater than zero and at most 5.0 volts."
            )
        return value
    if function == "dc":
        raise ParameterValidationError(
            "WGEN amplitude is not applicable to the DC waveform; "
            "set the DC level with offset."
        )
    if function is not None and function not in WGEN_FUNCTION_TOKENS:
        raise ParameterValidationError(f"Unknown WGEN function: {function!r}.")
    lower, upper = _wgen_amplitude_bounds(series, load)
    if not lower <= value <= upper:
        raise ParameterValidationError(
            f"WGEN amplitude must be between {lower:g} and {upper:g} Vpp "
            f"({_wgen_load_label(load)} load) on {series}."
        )
    if series == "4000X" and function != "dc" and offset is not None:
        _check_wgen_4000x_amplitude_offset_interaction(value, offset)
    return value


def validate_wgen_offset(
    offset_volts: float,
    *,
    series: str | None = None,
    function: str | None = None,
    load: str | None = None,
    amplitude: float | None = None,
) -> float:
    value = _validate_wgen_numeric(offset_volts, "offset")
    if series is None:
        # Legacy context-free validation.
        if not -2.5 <= value <= 2.5:
            raise ParameterValidationError(
                "WGEN offset must be between -2.5 and 2.5 volts."
            )
        return value
    bound = _wgen_offset_bound(series, function, load)
    if not -bound <= value <= bound:
        raise ParameterValidationError(
            f"WGEN offset must be between {-bound:g} and {bound:g} volts "
            f"({_wgen_load_label(load)} load) on {series}."
        )
    if (
        series == "4000X"
        and function != "dc"
        and amplitude is not None
    ):
        _check_wgen_4000x_amplitude_offset_interaction(amplitude, value)
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


def _wgen_series_table(series: str, table: dict[str, Any], what: str) -> Any:
    try:
        return table[series]
    except KeyError:
        raise ParameterValidationError(
            f"Unknown WGEN {what} series: {series!r}."
        ) from None


def _format_wgen_hz(value: float) -> str:
    return _WGEN_HZ_LABELS.get(value, f"{value:g} Hz")


def _wgen_load_label(load: str | None) -> str:
    if load == "fifty":
        return "50 ohm"
    return "High-Z"


def _wgen_halved_bounds(lower: float, upper: float, load: str | None) -> tuple[float, float]:
    if load is None or load == "one-meg":
        return lower, upper
    if load == "fifty":
        return lower / 2.0, upper / 2.0
    raise ParameterValidationError(f"Unknown WGEN load: {load!r}.")


def _wgen_amplitude_bounds(series: str, load: str | None) -> tuple[float, float]:
    table = _wgen_series_table(series, _WGEN_AMPLITUDE_LIMITS_VPP, "amplitude")
    return _wgen_halved_bounds(table[0], table[1], load)


def _check_wgen_4000x_amplitude_offset_interaction(
    amplitude_vpp: float, offset_volts: float
) -> None:
    if (
        amplitude_vpp < _WGEN_4000X_INTERACTION_AMPLITUDE_VPP
        and abs(offset_volts) > _WGEN_4000X_INTERACTION_OFFSET_VOLTS
    ):
        raise ParameterValidationError(
            "On 4000X, offset is limited to +/-500 mV while the amplitude "
            "is below 40 mVpp; setting a larger offset requires at least "
            "40 mVpp."
        )


def _wgen_offset_bound(
    series: str, function: str | None, load: str | None
) -> float:
    if load is not None and load not in WGEN_LOAD_TOKENS:
        raise ParameterValidationError(f"Unknown WGEN load: {load!r}.")
    table = _wgen_series_table(series, _WGEN_OFFSET_LIMITS_VOLTS, "offset")
    if table is None:
        # 2000X offset numeric range is not established by the available
        # Programmer's Guide text; preserve the existing +/-2.5 V check as a
        # compatibility fallback.
        return 2.5
    if function is None:
        # Series planning envelope across the supported common functions.
        bound = max(abs(limit) for limit in table.values())
    elif function in table:
        bound = abs(table[function])
    else:
        raise ParameterValidationError(f"Unknown WGEN function: {function!r}.")
    if load == "fifty":
        return bound / 2.0
    return bound


def _wgen_root(capabilities: ScopeCapabilities) -> str:
    if not capabilities.supports_wgen or not capabilities.wgen_scpi_root:
        raise ParameterValidationError(
            "WGEN is not supported by this model profile."
        )
    return capabilities.wgen_scpi_root
