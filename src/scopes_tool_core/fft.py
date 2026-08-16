"""FFT controls and command/readback helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

from .capabilities import ScopeCapabilities
from .channel import validate_analog_channel
from .errors import ChannelResponseError, ParameterValidationError
from .math import (
    _format_number,
    math_function_scpi_prefix,
    parse_math_display,
    parse_math_source,
    validate_finite_number,
    validate_nonnegative,
    validate_positive,
)
from .scpi import SCPIClient


_FFT_UNITS = {"decibel": "DECibel", "vrms": "VRMS"}

_FFT_WINDOWS = {
    "rectangular": "RECTangular",
    "hanning": "HANNing",
    "flattop": "FLATtop",
    "bharris": "BHARris",
    "bartlett": "BARTlett",
}

FFT_OPERATIONS = ("fft", "fft-phase")

FFT_GATES = ("none", "zoom")

FFT_PHASE_REFERENCES = ("trigger", "display")

FFT_DETECTION_TYPES = (
    "off",
    "sample",
    "positive-peak",
    "negative-peak",
    "normal",
    "average",
)

_FFT_OPERATION_TOKENS = {"fft": "FFT", "fft-phase": "FFTPhase"}

_FFT_OPERATION_READBACKS = {
    "FFT": "fft",
    "FFTP": "fft-phase",
    "FFTPHASE": "fft-phase",
}

_FFT_GATE_TOKENS = {"none": "NONE", "zoom": "ZOOM"}

_FFT_GATE_READBACKS = {"NONE": "none", "ZOOM": "zoom"}

_FFT_PHASE_REFERENCE_TOKENS = {
    "trigger": "TRIGger",
    "display": "DISPlay",
}

_FFT_PHASE_REFERENCE_READBACKS = {
    "TRIG": "trigger",
    "TRIGGER": "trigger",
    "DISP": "display",
    "DISPLAY": "display",
}

_FFT_DETECTION_TYPE_TOKENS = {
    "off": "OFF",
    "sample": "SAMPle",
    "positive-peak": "PPOSitive",
    "negative-peak": "PNEGative",
    "normal": "NORMal",
    "average": "AVERage",
}

_FFT_DETECTION_TYPE_READBACKS = {
    "OFF": "off",
    "SAMP": "sample",
    "SAMPLE": "sample",
    "PPOS": "positive-peak",
    "PPOSITIVE": "positive-peak",
    "PNEG": "negative-peak",
    "PNEGATIVE": "negative-peak",
    "NORM": "normal",
    "NORMAL": "normal",
    "AVER": "average",
    "AVERAGE": "average",
}

@dataclass(frozen=True)
class FFTState:
    function: int
    operation: str
    source_channel: int
    units: str
    window: str
    center_hz: float
    span_hz: float
    display: bool
    operation_canonical: str | None = None
    start_hz: float | None = None
    stop_hz: float | None = None
    gate: str | None = None
    phase_reference: str | None = None
    detection_type: str | None = None
    detection_points: int | None = None
    bin_size_hz: float | None = None
    sample_rate_hz: float | None = None
    resolution_bandwidth_hz: float | None = None

class FFTController:
    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(
        self,
        function: int,
        source_channel: int,
        *,
        units: str | None = None,
        window: str | None = None,
        center_hz: float | None = None,
        span_hz: float | None = None,
        display: bool | None = None,
        fft_operation: str = "fft",
        start_hz: float | None = None,
        stop_hz: float | None = None,
        gate: str | None = None,
        phase_reference: str | None = None,
        detection_type: str | None = None,
        detection_points: int | None = None,
    ) -> None:
        for command in fft_configure_commands(
            function,
            source_channel,
            units=units,
            window=window,
            center_hz=center_hz,
            span_hz=span_hz,
            display=display,
            fft_operation=fft_operation,
            start_hz=start_hz,
            stop_hz=stop_hz,
            gate=gate,
            phase_reference=phase_reference,
            detection_type=detection_type,
            detection_points=detection_points,
            capabilities=self.capabilities,
        ):
            self.scpi.write(command)

    def query(self, function: int) -> FFTState:
        commands = fft_query_commands(function, capabilities=self.capabilities)
        (
            operation_command,
            source_command,
            units_command,
            window_command,
            center_command,
            span_command,
            display_command,
        ) = commands
        operation = self.scpi.query(operation_command)
        operation_canonical = parse_fft_operation(operation)
        source = self.scpi.query(source_command).strip()
        source_canonical = parse_math_source(
            source, capabilities=self.capabilities
        )
        state = FFTState(
            function=function,
            operation=operation,
            operation_canonical=operation_canonical,
            source_channel=int(source_canonical.removeprefix("channel")),
            units=self.scpi.query(units_command),
            window=self.scpi.query(window_command),
            center_hz=_query_fft_finite_number(
                self.scpi, center_command, "center frequency"
            ),
            span_hz=_query_fft_finite_number(
                self.scpi, span_command, "frequency span"
            ),
            display=parse_math_display(self.scpi.query(display_command)),
        )
        if not self.capabilities.supports_advanced_fft:
            return state
        advanced_commands = fft_advanced_query_commands(
            function,
            include_phase_reference=operation_canonical == "fft-phase",
            capabilities=self.capabilities,
        )
        (
            start_command,
            stop_command,
            gate_command,
            detection_type_command,
            detection_points_command,
            bin_size_command,
            sample_rate_command,
            resolution_bandwidth_command,
            *phase_commands,
        ) = advanced_commands
        return replace(
            state,
            start_hz=_query_fft_finite_number(
                self.scpi, start_command, "start frequency"
            ),
            stop_hz=_query_fft_finite_number(
                self.scpi, stop_command, "stop frequency"
            ),
            gate=parse_fft_gate(self.scpi.query(gate_command)),
            detection_type=parse_fft_detection_type(
                self.scpi.query(detection_type_command)
            ),
            detection_points=parse_fft_detection_points_response(
                self.scpi.query(detection_points_command)
            ),
            bin_size_hz=_query_fft_finite_number(
                self.scpi, bin_size_command, "bin size"
            ),
            sample_rate_hz=_query_fft_finite_number(
                self.scpi, sample_rate_command, "sample rate"
            ),
            resolution_bandwidth_hz=_query_fft_finite_number(
                self.scpi, resolution_bandwidth_command, "resolution bandwidth"
            ),
            phase_reference=(
                parse_fft_phase_reference(self.scpi.query(phase_commands[0]))
                if phase_commands
                else None
            ),
        )

def fft_configure_commands(
    function: int,
    source_channel: int,
    *,
    units: str | None = None,
    window: str | None = None,
    center_hz: float | None = None,
    span_hz: float | None = None,
    display: bool | None = None,
    fft_operation: str = "fft",
    start_hz: float | None = None,
    stop_hz: float | None = None,
    gate: str | None = None,
    phase_reference: str | None = None,
    detection_type: str | None = None,
    detection_points: int | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    channel = (
        validate_analog_channel(source_channel, capabilities)
        if capabilities is not None
        else source_channel
    )
    operation_token = normalize_fft_operation(fft_operation)
    if fft_operation == "fft-phase" and units is not None:
        raise ParameterValidationError(
            "--units is not supported with --fft-operation fft-phase; omit --units."
        )
    advanced_values = (
        start_hz,
        stop_hz,
        gate,
        phase_reference,
        detection_type,
        detection_points,
    )
    if (
        capabilities is not None
        and not capabilities.supports_advanced_fft
        and (
            fft_operation != "fft"
            or any(value is not None for value in advanced_values)
        )
    ):
        raise ParameterValidationError(
            "FFT Phase and advanced FFT controls require a 4000X capability profile."
        )
    if (center_hz is not None or span_hz is not None) and (
        start_hz is not None or stop_hz is not None
    ):
        raise ParameterValidationError(
            "--center-hz/--span-hz cannot be combined with --start-hz/--stop-hz."
        )
    if phase_reference is not None and fft_operation != "fft-phase":
        raise ParameterValidationError(
            "--phase-reference is only valid with --fft-operation fft-phase."
        )
    validated_start = (
        None
        if start_hz is None
        else validate_finite_number(start_hz, "--start-hz")
    )
    validated_stop = (
        None if stop_hz is None else validate_finite_number(stop_hz, "--stop-hz")
    )
    if (
        validated_start is not None
        and validated_stop is not None
        and validated_start > validated_stop
    ):
        raise ParameterValidationError(
            "--start-hz must be less than or equal to --stop-hz."
        )
    commands = [
        f"{prefix}:OPERation {operation_token}",
        f"{prefix}:SOURce1 CHANnel{channel}",
    ]
    if units is not None:
        commands.append(f"{prefix}:FFT:VTYPe {normalize_fft_units(units)}")
    if window is not None:
        commands.append(f"{prefix}:FFT:WINDow {normalize_fft_window(window)}")
    if center_hz is not None:
        commands.append(f"{prefix}:FFT:CENTer {_format_number(validate_nonnegative(center_hz, '--center-hz'))}")
    if span_hz is not None:
        commands.append(f"{prefix}:FFT:SPAN {_format_number(validate_positive(span_hz, '--span-hz'))}")
    if validated_start is not None:
        commands.append(f"{prefix}:FREQuency:STARt {_format_number(validated_start)}")
    if validated_stop is not None:
        commands.append(f"{prefix}:FREQuency:STOP {_format_number(validated_stop)}")
    if gate is not None:
        commands.append(f"{prefix}:GATE {normalize_fft_gate(gate)}")
    if phase_reference is not None:
        commands.append(
            f"{prefix}:PHASe:REFerence {normalize_fft_phase_reference(phase_reference)}"
        )
    if detection_type is not None:
        commands.append(
            f"{prefix}:DETection:TYPE {normalize_fft_detection_type(detection_type)}"
        )
    if detection_points is not None:
        commands.append(
            f"{prefix}:DETection:POINts {validate_fft_detection_points(detection_points)}"
        )
    if display is not None:
        commands.append(f"{prefix}:DISPlay {'ON' if display else 'OFF'}")
    return commands

def fft_query_commands(
    function: int, capabilities: ScopeCapabilities | None = None
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    return [
        f"{prefix}:OPERation?",
        f"{prefix}:SOURce1?",
        f"{prefix}:FFT:VTYPe?",
        f"{prefix}:FFT:WINDow?",
        f"{prefix}:FFT:CENTer?",
        f"{prefix}:FFT:SPAN?",
        f"{prefix}:DISPlay?",
    ]

def fft_advanced_query_commands(
    function: int,
    *,
    include_phase_reference: bool = False,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    if capabilities is not None and not capabilities.supports_advanced_fft:
        raise ParameterValidationError(
            "Advanced FFT queries require a 4000X capability profile."
        )
    commands = [
        f"{prefix}:FREQuency:STARt?",
        f"{prefix}:FREQuency:STOP?",
        f"{prefix}:GATE?",
        f"{prefix}:DETection:TYPE?",
        f"{prefix}:DETection:POINts?",
        f"{prefix}:BSIZe?",
        f"{prefix}:SRATe?",
        f"{prefix}:RBWidth?",
    ]
    if include_phase_reference:
        commands.append(f"{prefix}:PHASe:REFerence?")
    return commands

def normalize_fft_units(value: str) -> str:
    try:
        return _FFT_UNITS[value.strip().lower()]
    except KeyError as exc:
        raise ParameterValidationError("--units must be decibel or vrms.") from exc

def normalize_fft_window(value: str) -> str:
    try:
        return _FFT_WINDOWS[value.strip().lower()]
    except KeyError as exc:
        raise ParameterValidationError(
            "--window must be rectangular, hanning, flattop, bharris, or bartlett."
        ) from exc

def normalize_fft_operation(value: str) -> str:
    try:
        return _FFT_OPERATION_TOKENS[value]
    except (KeyError, TypeError) as exc:
        raise ParameterValidationError(
            "--fft-operation must be fft or fft-phase."
        ) from exc

def parse_fft_operation(raw: str) -> str:
    try:
        return _FFT_OPERATION_READBACKS[raw.strip().upper()]
    except (KeyError, AttributeError) as exc:
        raise ChannelResponseError(
            f"Could not parse FFT operation response: {raw!r}"
        ) from exc

def normalize_fft_gate(value: str) -> str:
    try:
        return _FFT_GATE_TOKENS[value]
    except (KeyError, TypeError) as exc:
        raise ParameterValidationError("--gate must be none or zoom.") from exc

def parse_fft_gate(raw: str) -> str:
    try:
        return _FFT_GATE_READBACKS[raw.strip().upper()]
    except (KeyError, AttributeError) as exc:
        raise ChannelResponseError(
            f"Could not parse FFT gate response: {raw!r}"
        ) from exc

def normalize_fft_phase_reference(value: str) -> str:
    try:
        return _FFT_PHASE_REFERENCE_TOKENS[value]
    except (KeyError, TypeError) as exc:
        raise ParameterValidationError(
            "--phase-reference must be trigger or display."
        ) from exc

def parse_fft_phase_reference(raw: str) -> str:
    try:
        return _FFT_PHASE_REFERENCE_READBACKS[raw.strip().upper()]
    except (KeyError, AttributeError) as exc:
        raise ChannelResponseError(
            f"Could not parse FFT phase reference response: {raw!r}"
        ) from exc

def normalize_fft_detection_type(value: str) -> str:
    try:
        return _FFT_DETECTION_TYPE_TOKENS[value]
    except (KeyError, TypeError) as exc:
        raise ParameterValidationError(
            "--detection-type must be off, sample, positive-peak, "
            "negative-peak, normal, or average."
        ) from exc

def parse_fft_detection_type(raw: str) -> str:
    try:
        return _FFT_DETECTION_TYPE_READBACKS[raw.strip().upper()]
    except (KeyError, AttributeError) as exc:
        raise ChannelResponseError(
            f"Could not parse FFT detection type response: {raw!r}"
        ) from exc

def validate_fft_detection_points(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ParameterValidationError("--detection-points must be an integer.")
    if value < 640 or value > 65536:
        raise ParameterValidationError(
            "--detection-points must be between 640 and 65536."
        )
    return value

def parse_fft_detection_points_response(raw: str) -> int:
    try:
        numeric_value = float(raw)
        if not math.isfinite(numeric_value) or not numeric_value.is_integer():
            raise ValueError
        return validate_fft_detection_points(int(numeric_value))
    except (TypeError, ValueError, OverflowError, ParameterValidationError) as exc:
        raise ChannelResponseError(
            f"Could not parse FFT detection points response: {raw!r}"
        ) from exc

def _query_fft_finite_number(
    scpi: SCPIClient, command: str, setting_name: str
) -> float:
    raw = scpi.query(command)
    try:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError
        return value
    except (TypeError, ValueError, OverflowError) as exc:
        raise ChannelResponseError(
            f"Could not parse FFT {setting_name} response: {raw!r}"
        ) from exc
