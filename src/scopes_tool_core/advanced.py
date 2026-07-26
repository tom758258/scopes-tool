"""Advanced InfiniiVision runtime controls."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import PureWindowsPath
from typing import Callable, Sequence

from .capabilities import ScopeCapabilities
from .channel import (
    channel_offset_command,
    channel_offset_query,
    channel_scale_command,
    channel_scale_query,
    validate_analog_channel,
)
from .errors import ChannelResponseError, ParameterValidationError
from .scpi import SCPIClient


TRIGGER_HOLDOFF_MIN_SECONDS = 40e-9
TRIGGER_HOLDOFF_MAX_SECONDS = 10.0

_AUTOSCALE_ACQUIRE_MODES = {"normal": "NORMal", "current": "CURRent"}
_AUTOSCALE_CHANNEL_MODES = {"all": "ALL", "displayed": "DISPlayed"}
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
MATH_OPERATIONS = ("add", "subtract", "multiply", "divide")
MATH_SOURCES = ("channel1", "channel2", "channel3", "channel4")
MATH_TRANSFORM_SOURCES = MATH_SOURCES + (
    "composite",
    "math1",
    "math2",
    "math3",
)
MATH_COMPOSITE_OPERATIONS = ("add", "subtract", "multiply")
MATH_TRANSFORMS = (
    "differentiate",
    "integrate",
    "sqrt",
    "absolute",
    "square",
    "ln",
    "log10",
    "exp",
    "exp10",
    "linear",
)
MATH_FILTER_OPERATIONS = (
    "low-pass",
    "high-pass",
    "average",
    "smooth",
    "envelope",
)
MATH_VISUALIZATION_OPERATIONS = (
    "magnify",
    "trend",
    "maximum",
    "minimum",
    "peak",
    "max-hold",
    "min-hold",
)
MATH_TREND_MEASUREMENTS = (
    "vavg",
    "ac_rms",
    "vratio",
    "period",
    "frequency",
    "positive_width",
    "negative_width",
    "duty_cycle",
    "rise_time",
    "fall_time",
)
_MATH_OPERATION_TOKENS = {
    "add": "ADD",
    "subtract": "SUBTract",
    "multiply": "MULTiply",
    "divide": "DIVide",
}
_MATH_OPERATION_READBACKS = {
    "ADD": "add",
    "SUBT": "subtract",
    "SUBTRACT": "subtract",
    "MULT": "multiply",
    "MULTIPLY": "multiply",
    "DIV": "divide",
    "DIVIDE": "divide",
}
_MATH_COMPOSITE_OPERATION_TOKENS = {
    "add": "ADD",
    "subtract": "SUBTract",
    "multiply": "MULTiply",
}
_MATH_COMPOSITE_OPERATION_READBACKS = {
    "ADD": "add",
    "SUBT": "subtract",
    "SUBTRACT": "subtract",
    "MULT": "multiply",
    "MULTIPLY": "multiply",
}
_MATH_TRANSFORM_TOKENS = {
    "differentiate": "DIFF",
    "integrate": "INTegrate",
    "sqrt": "SQRT",
    "absolute": "ABSolute",
    "square": "SQUare",
    "ln": "LN",
    "log10": "LOG",
    "exp": "EXP",
    "exp10": "TEN",
    "linear": "LINear",
}
_MATH_TRANSFORM_READBACKS = {
    "DIFF": "differentiate",
    "INT": "integrate",
    "INTEGRATE": "integrate",
    "SQRT": "sqrt",
    "ABS": "absolute",
    "ABSOLUTE": "absolute",
    "SQU": "square",
    "SQUARE": "square",
    "LN": "ln",
    "LOG": "log10",
    "EXP": "exp",
    "TEN": "exp10",
    "LIN": "linear",
    "LINEAR": "linear",
}
_MATH_FILTER_TOKENS = {
    "low-pass": "LOWPass",
    "high-pass": "HIGHpass",
    "average": "AVERage",
    "smooth": "SMOoth",
    "envelope": "ENVelope",
}
_MATH_FILTER_READBACKS = {
    "LOWP": "low-pass",
    "LOWPASS": "low-pass",
    "HIGH": "high-pass",
    "HIGHPASS": "high-pass",
    "AVER": "average",
    "AVERAGE": "average",
    "SMO": "smooth",
    "SMOOTH": "smooth",
    "ENV": "envelope",
    "ENVELOPE": "envelope",
}
_MATH_VISUALIZATION_TOKENS = {
    "magnify": "MAGNify",
    "trend": "TRENd",
    "maximum": "MAXimum",
    "minimum": "MINimum",
    "peak": "PEAK",
    "max-hold": "MAXHold",
    "min-hold": "MINHold",
}
_MATH_VISUALIZATION_READBACKS = {
    "MAGN": "magnify",
    "MAGNIFY": "magnify",
    "TREN": "trend",
    "TREND": "trend",
    "MAX": "maximum",
    "MAXIMUM": "maximum",
    "MIN": "minimum",
    "MINIMUM": "minimum",
    "PEAK": "peak",
    "MAXH": "max-hold",
    "MAXHOLD": "max-hold",
    "MINH": "min-hold",
    "MINHOLD": "min-hold",
}
_MATH_TREND_MEASUREMENT_TOKENS = {
    "vavg": "VAVerage",
    "ac_rms": "ACRMs",
    "vratio": "VRATio",
    "period": "PERiod",
    "frequency": "FREQuency",
    "positive_width": "PWIDth",
    "negative_width": "NWIDth",
    "duty_cycle": "DUTYcycle",
    "rise_time": "RISetime",
    "fall_time": "FALLtime",
}
_MATH_TREND_MEASUREMENT_READBACKS = {
    "VAV": "vavg",
    "VAVERAGE": "vavg",
    "ACRM": "ac_rms",
    "ACRMS": "ac_rms",
    "VRAT": "vratio",
    "VRATIO": "vratio",
    "PER": "period",
    "PERIOD": "period",
    "FREQ": "frequency",
    "FREQUENCY": "frequency",
    "PWID": "positive_width",
    "PWIDTH": "positive_width",
    "NWID": "negative_width",
    "NWIDTH": "negative_width",
    "DUTY": "duty_cycle",
    "DUTYCYCLE": "duty_cycle",
    "RIS": "rise_time",
    "RISETIME": "rise_time",
    "FALL": "fall_time",
    "FALLTIME": "fall_time",
}


@dataclass(frozen=True)
class CursorState:
    mode: str
    x1_seconds: float
    x2_seconds: float
    y1_volts: float
    y2_volts: float
    x_delta_seconds: float
    y_delta_volts: float
    dydx: float


@dataclass(frozen=True)
class CursorAutoTimebaseResult:
    enabled: bool
    strategy: str
    changed: bool | None
    original_scale_seconds_per_division: float | None
    original_position_seconds: float | None
    target_scale_seconds_per_division: float | None
    commands: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class CursorAutoVerticalResult:
    enabled: bool
    strategy: str
    changed: bool | None
    offset_changed: bool | None
    original_scale_volts_per_division: float | None
    original_offset_volts: float | None
    target_scale_volts_per_division: float | None
    target_offset_volts: float | None
    commands: tuple[str, ...]
    reason: str


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


@dataclass(frozen=True)
class MathDisplayState:
    function: int
    enabled: bool
    raw: str


@dataclass(frozen=True)
class MathVerticalState:
    function: int
    scale: float
    range: float
    offset: float


@dataclass(frozen=True)
class MathOperatorState:
    function: int
    operation: str
    operation_raw: str
    source1: str
    source1_raw: str
    source2: str
    source2_raw: str


@dataclass(frozen=True)
class MathTransformState:
    function: int
    operation: str
    operation_raw: str
    source: str
    source_raw: str
    input_offset: float | None
    gain: float | None
    linear_offset: float | None


@dataclass(frozen=True)
class MathCompositeSourceState:
    operation: str
    operation_raw: str
    source1: str
    source1_raw: str
    source2: str
    source2_raw: str


@dataclass(frozen=True)
class MathFilterState:
    function: int
    operation: str
    operation_raw: str
    source: str
    source_raw: str
    cutoff_hz: float | None
    average_count: int | None
    smooth_points: int | None


@dataclass(frozen=True)
class MathVisualizationState:
    function: int
    operation: str
    operation_raw: str
    source: str | None
    source_raw: str | None
    source2: str | None
    source2_raw: str | None
    measurement: str | None
    measurement_raw: str | None
    measurement_slot: int | None


class CursorController:
    """Manual marker/cursor controls."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def set_manual(
        self,
        source_channel: int,
        x1_seconds: float,
        x2_seconds: float,
        *,
        y1_volts: float | None = None,
        y2_volts: float | None = None,
        auto_timebase: bool = False,
        auto_vertical: bool = False,
    ) -> None:
        source_channel = validate_analog_channel(source_channel, self.capabilities)
        if auto_timebase:
            scale = self.scpi.query_float(":TIMebase:SCALe?")
            position = self.scpi.query_float(":TIMebase:POSition?")
            auto_result = cursor_auto_timebase_plan(
                scale,
                position,
                x1_seconds,
                x2_seconds,
            )
            if auto_result.changed and auto_result.target_scale_seconds_per_division is not None:
                self.scpi.write(
                    f":TIMebase:SCALe {_format_scpi_number(auto_result.target_scale_seconds_per_division)}"
                )
        if auto_vertical:
            scale = self.scpi.query_float(channel_scale_query(source_channel))
            offset = self.scpi.query_float(channel_offset_query(source_channel))
            auto_vertical_result = cursor_auto_vertical_plan(
                source_channel,
                scale,
                offset,
                y1_volts=y1_volts,
                y2_volts=y2_volts,
                capabilities=self.capabilities,
            )
            if auto_vertical_result.changed:
                assert auto_vertical_result.target_scale_volts_per_division is not None
                assert auto_vertical_result.target_offset_volts is not None
                self.scpi.write(
                    channel_scale_command(
                        source_channel,
                        auto_vertical_result.target_scale_volts_per_division,
                    )
                )
                if auto_vertical_result.offset_changed:
                    self.scpi.write(
                        channel_offset_command(
                            source_channel,
                            auto_vertical_result.target_offset_volts,
                        )
                    )
        for command in cursor_configure_commands(
            source_channel,
            x1_seconds,
            x2_seconds,
            y1_volts=y1_volts,
            y2_volts=y2_volts,
            capabilities=self.capabilities,
        ):
            self.scpi.write(command)

    def off(self) -> None:
        self.scpi.write(":MARKer:MODE OFF")

    def query(self) -> CursorState:
        return CursorState(
            mode=self.scpi.query(":MARKer:MODE?"),
            x1_seconds=self.scpi.query_float(":MARKer:X1Position?"),
            x2_seconds=self.scpi.query_float(":MARKer:X2Position?"),
            y1_volts=self.scpi.query_float(":MARKer:Y1Position?"),
            y2_volts=self.scpi.query_float(":MARKer:Y2Position?"),
            x_delta_seconds=self.scpi.query_float(":MARKer:XDELta?"),
            y_delta_volts=self.scpi.query_float(":MARKer:YDELta?"),
            dydx=self.scpi.query_float(":MARKer:DYDX?"),
        )


class TriggerHoldoffController:
    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def set_seconds(self, seconds: float) -> None:
        for command in trigger_holdoff_commands(seconds):
            self.scpi.write(command)

    def query_seconds(self) -> float:
        return self.scpi.query_float(trigger_holdoff_query())


class SetupController:
    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def autoscale(
        self,
        channels: Sequence[int] | None,
        *,
        acquire_mode: str | None = None,
        channels_mode: str | None = None,
        capabilities: ScopeCapabilities | None = None,
    ) -> None:
        for command in autoscale_commands(
            channels,
            acquire_mode=acquire_mode,
            channels_mode=channels_mode,
            capabilities=capabilities,
        ):
            self.scpi.write(command)

    def save(self, *, slot: int | None = None, file_spec: str | None = None) -> None:
        self.scpi.write(setup_save_command(slot=slot, file_spec=file_spec))

    def recall(self, *, slot: int | None = None, file_spec: str | None = None) -> None:
        self.scpi.write(setup_recall_command(slot=slot, file_spec=file_spec))


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


class MathController:
    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def set_display(self, function: int, enabled: bool) -> None:
        self.scpi.write(
            math_display_command(function, enabled, capabilities=self.capabilities)
        )

    def query_display(self, function: int) -> MathDisplayState:
        raw = self.scpi.query(
            math_display_query(function, capabilities=self.capabilities)
        ).strip()
        return MathDisplayState(
            function=function,
            enabled=parse_math_display(raw),
            raw=raw,
        )

    def configure_vertical(
        self,
        function: int,
        *,
        scale: float | None = None,
        range_value: float | None = None,
        offset: float | None = None,
    ) -> None:
        for command in math_vertical_commands(
            function,
            scale=scale,
            range_value=range_value,
            offset=offset,
            capabilities=self.capabilities,
        ):
            self.scpi.write(command)

    def query_vertical(self, function: int) -> MathVerticalState:
        scale_command, range_command, offset_command = math_vertical_query_commands(
            function, capabilities=self.capabilities
        )
        return MathVerticalState(
            function=function,
            scale=_query_math_finite_number(
                self.scpi, scale_command, "vertical scale"
            ),
            range=_query_math_finite_number(
                self.scpi, range_command, "vertical range"
            ),
            offset=_query_math_finite_number(
                self.scpi, offset_command, "vertical offset"
            ),
        )

    def configure_operator(
        self,
        function: int,
        operation: str,
        source1: str,
        source2: str,
    ) -> None:
        for command in math_operator_commands(
            function,
            operation,
            source1,
            source2,
            capabilities=self.capabilities,
        ):
            self.scpi.write(command)

    def query_operator(self, function: int) -> MathOperatorState:
        operation_command, source1_command, source2_command = (
            math_operator_query_commands(function, capabilities=self.capabilities)
        )
        operation_raw = self.scpi.query(operation_command).strip()
        source1_raw = self.scpi.query(source1_command).strip()
        source2_raw = self.scpi.query(source2_command).strip()
        return MathOperatorState(
            function=function,
            operation=parse_math_operation(operation_raw),
            operation_raw=operation_raw,
            source1=parse_math_source(source1_raw, capabilities=self.capabilities),
            source1_raw=source1_raw,
            source2=parse_math_source(source2_raw, capabilities=self.capabilities),
            source2_raw=source2_raw,
        )

    def configure_composite_source(
        self,
        operation: str,
        source1: str,
        source2: str,
    ) -> None:
        for command in math_composite_source_commands(
            operation,
            source1,
            source2,
            capabilities=self.capabilities,
        ):
            self.scpi.write(command)

    def query_composite_source(self) -> MathCompositeSourceState:
        operation_command, source1_command, source2_command = (
            math_composite_source_query_commands(capabilities=self.capabilities)
        )
        operation_raw = self.scpi.query(operation_command).strip()
        source1_raw = self.scpi.query(source1_command).strip()
        source2_raw = self.scpi.query(source2_command).strip()
        return MathCompositeSourceState(
            operation=parse_math_composite_operation(operation_raw),
            operation_raw=operation_raw,
            source1=parse_math_source(source1_raw, capabilities=self.capabilities),
            source1_raw=source1_raw,
            source2=parse_math_source(source2_raw, capabilities=self.capabilities),
            source2_raw=source2_raw,
        )

    def configure_transform(
        self,
        function: int,
        operation: str,
        source: str,
        *,
        input_offset: float | None = None,
        gain: float | None = None,
        linear_offset: float | None = None,
    ) -> None:
        for command in math_transform_commands(
            function,
            operation,
            source,
            input_offset=input_offset,
            gain=gain,
            linear_offset=linear_offset,
            capabilities=self.capabilities,
        ):
            self.scpi.write(command)

    def query_transform(self, function: int) -> MathTransformState:
        operation_command, source_command = math_transform_query_commands(
            function, capabilities=self.capabilities
        )
        operation_raw = self.scpi.query(operation_command).strip()
        source_raw = self.scpi.query(source_command).strip()
        operation = parse_math_transform(operation_raw)
        prefix = math_function_scpi_prefix(function, self.capabilities)
        input_offset = None
        gain = None
        linear_offset = None
        if operation == "integrate":
            input_offset = _query_math_finite_number(
                self.scpi,
                f"{prefix}:INTegrate:IOFFset?",
                "integrate input offset",
            )
        elif operation == "linear":
            gain = _query_math_finite_number(
                self.scpi, f"{prefix}:LINear:GAIN?", "linear gain"
            )
            linear_offset = _query_math_finite_number(
                self.scpi, f"{prefix}:LINear:OFFSet?", "linear offset"
            )
        return MathTransformState(
            function=function,
            operation=operation,
            operation_raw=operation_raw,
            source=parse_math_source1(
                source_raw,
                function,
                capabilities=self.capabilities,
                allow_composite=True,
            ),
            source_raw=source_raw,
            input_offset=input_offset,
            gain=gain,
            linear_offset=linear_offset,
        )

    def configure_filter(
        self,
        function: int,
        operation: str,
        source: str,
        *,
        cutoff_hz: float | None = None,
        average_count: int | None = None,
        smooth_points: int | None = None,
    ) -> None:
        for command in math_filter_commands(
            function,
            operation,
            source,
            cutoff_hz=cutoff_hz,
            average_count=average_count,
            smooth_points=smooth_points,
            capabilities=self.capabilities,
        ):
            self.scpi.write(command)

    def query_filter(self, function: int) -> MathFilterState:
        operation_command, source_command = math_filter_query_commands(
            function, capabilities=self.capabilities
        )
        operation_raw = self.scpi.query(operation_command).strip()
        source_raw = self.scpi.query(source_command).strip()
        operation = parse_math_filter_operation(operation_raw)
        _validate_math_filter_capability(operation, self.capabilities)
        prefix = math_function_scpi_prefix(function, self.capabilities)
        cutoff_hz = None
        average_count = None
        smooth_points = None
        if operation == "low-pass":
            cutoff_hz = _query_math_finite_number(
                self.scpi,
                f"{prefix}:FREQuency:LOWPass?",
                "low-pass cutoff frequency",
            )
        elif operation == "high-pass":
            cutoff_hz = _query_math_finite_number(
                self.scpi,
                f"{prefix}:FREQuency:HIGHpass?",
                "high-pass cutoff frequency",
            )
        elif operation == "average":
            average_count = _parse_math_filter_integer_response(
                self.scpi.query(f"{prefix}:AVERage:COUNt?"),
                "average count",
                validate_math_average_count,
            )
        elif operation == "smooth":
            smooth_points = _parse_math_filter_integer_response(
                self.scpi.query(f"{prefix}:SMOoth:POINts?"),
                "smooth points",
                validate_math_smooth_points,
            )
        return MathFilterState(
            function=function,
            operation=operation,
            operation_raw=operation_raw,
            source=parse_math_source1(
                source_raw,
                function,
                capabilities=self.capabilities,
                allow_composite=True,
            ),
            source_raw=source_raw,
            cutoff_hz=cutoff_hz,
            average_count=average_count,
            smooth_points=smooth_points,
        )

    def configure_visualization(
        self,
        function: int,
        operation: str,
        *,
        source: str | None = None,
        source2: str | None = None,
        measurement: str | None = None,
        measurement_slot: int | None = None,
    ) -> None:
        for command in math_visualization_commands(
            function,
            operation,
            source=source,
            source2=source2,
            measurement=measurement,
            measurement_slot=measurement_slot,
            capabilities=self.capabilities,
        ):
            self.scpi.write(command)

    def query_visualization(self, function: int) -> MathVisualizationState:
        operation_command = math_visualization_query_commands(
            function, capabilities=self.capabilities
        )[0]
        operation_raw = self.scpi.query(operation_command).strip()
        operation = parse_math_visualization_operation(operation_raw)
        try:
            _validate_math_visualization_capability(
                operation, self.capabilities
            )
        except ParameterValidationError as exc:
            raise ChannelResponseError(
                "Could not parse Math visualization response: "
                f"{operation_raw!r}"
            ) from exc
        prefix = math_function_scpi_prefix(function, self.capabilities)
        source = None
        source_raw = None
        source2 = None
        source2_raw = None
        measurement = None
        measurement_raw = None
        measurement_slot = None
        if operation == "trend" and self.capabilities.series == "4000X":
            measurement_raw = self.scpi.query(
                f"{prefix}:TRENd:NMEasurement?"
            ).strip()
            measurement_slot = parse_math_trend_measurement_slot(measurement_raw)
        else:
            source_raw = self.scpi.query(f"{prefix}:SOURce1?").strip()
            if operation == "trend":
                source = parse_math_source(
                    source_raw, capabilities=self.capabilities
                )
                measurement_raw = self.scpi.query(
                    f"{prefix}:TRENd:MEASurement?"
                ).strip()
                measurement = parse_math_trend_measurement(measurement_raw)
                if measurement == "vratio":
                    source2_raw = self.scpi.query(f"{prefix}:SOURce2?").strip()
                    source2 = parse_math_source(
                        source2_raw, capabilities=self.capabilities
                    )
            else:
                source = parse_math_source1(
                    source_raw,
                    function,
                    capabilities=self.capabilities,
                    allow_composite=True,
                )
        return MathVisualizationState(
            function=function,
            operation=operation,
            operation_raw=operation_raw,
            source=source,
            source_raw=source_raw,
            source2=source2,
            source2_raw=source2_raw,
            measurement=measurement,
            measurement_raw=measurement_raw,
            measurement_slot=measurement_slot,
        )

    def clear(self, function: int) -> None:
        self.scpi.write(math_clear_command(function, capabilities=self.capabilities))


def trigger_holdoff_command(seconds: float) -> str:
    seconds = validate_trigger_holdoff(seconds)
    return f":TRIGger:HOLDoff {_format_scpi_number(seconds)}"


def trigger_holdoff_commands(seconds: float) -> list[str]:
    return [":TRIGger:HOLDoff:RANDom OFF", trigger_holdoff_command(seconds)]


def trigger_holdoff_query() -> str:
    return ":TRIGger:HOLDoff?"


def validate_trigger_holdoff(seconds: float) -> float:
    seconds = validate_finite_number(seconds, "--seconds")
    if seconds < TRIGGER_HOLDOFF_MIN_SECONDS or seconds > TRIGGER_HOLDOFF_MAX_SECONDS:
        raise ParameterValidationError("--seconds must be between 40e-9 and 10.")
    return seconds


def cursor_configure_commands(
    source_channel: int,
    x1_seconds: float,
    x2_seconds: float,
    *,
    y1_volts: float | None = None,
    y2_volts: float | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    channel = (
        validate_analog_channel(source_channel, capabilities)
        if capabilities is not None
        else source_channel
    )
    x1_seconds = validate_finite_number(x1_seconds, "--x1")
    x2_seconds = validate_finite_number(x2_seconds, "--x2")
    commands = [
        ":MARKer:MODE MANual",
        f":MARKer:X1Y1source CHANnel{channel}",
        f":MARKer:X2Y2source CHANnel{channel}",
        f":MARKer:X1Position {_format_scpi_number(x1_seconds)}",
        f":MARKer:X2Position {_format_scpi_number(x2_seconds)}",
    ]
    if y1_volts is not None:
        commands.append(
            f":MARKer:Y1Position {_format_scpi_number(validate_finite_number(y1_volts, '--y1'))}"
        )
    if y2_volts is not None:
        commands.append(
            f":MARKer:Y2Position {_format_scpi_number(validate_finite_number(y2_volts, '--y2'))}"
        )
    return commands


def cursor_auto_timebase_plan(
    current_scale_seconds_per_division: float,
    current_position_seconds: float,
    x1_seconds: float,
    x2_seconds: float,
) -> CursorAutoTimebaseResult:
    current_scale_seconds_per_division = validate_finite_number(
        current_scale_seconds_per_division,
        "timebase scale",
    )
    current_position_seconds = validate_finite_number(
        current_position_seconds,
        "timebase position",
    )
    if current_scale_seconds_per_division <= 0:
        raise ParameterValidationError("timebase scale must be greater than 0 s/div.")
    x1_seconds = validate_finite_number(x1_seconds, "--x1")
    x2_seconds = validate_finite_number(x2_seconds, "--x2")

    visible_half_span_seconds = current_scale_seconds_per_division * 4.5
    max_delta_seconds = max(
        abs(x1_seconds - current_position_seconds),
        abs(x2_seconds - current_position_seconds),
    )
    changed = max_delta_seconds > visible_half_span_seconds
    target_scale = (
        max(current_scale_seconds_per_division, max_delta_seconds / 4.0)
        if changed
        else current_scale_seconds_per_division
    )
    commands = [":TIMebase:SCALe?", ":TIMebase:POSition?"]
    if changed:
        commands.append(f":TIMebase:SCALe {_format_scpi_number(target_scale)}")
    reason = (
        "requested X cursor position is outside the current visible half-span"
        if changed
        else "requested X cursor positions fit within the current visible half-span"
    )
    return CursorAutoTimebaseResult(
        enabled=True,
        strategy="scale_only",
        changed=changed,
        original_scale_seconds_per_division=current_scale_seconds_per_division,
        original_position_seconds=current_position_seconds,
        target_scale_seconds_per_division=target_scale,
        commands=tuple(commands),
        reason=reason,
    )


def cursor_auto_timebase_dry_run_plan() -> CursorAutoTimebaseResult:
    return CursorAutoTimebaseResult(
        enabled=True,
        strategy="scale_only",
        changed=None,
        original_scale_seconds_per_division=None,
        original_position_seconds=None,
        target_scale_seconds_per_division=None,
        commands=(":TIMebase:SCALe?", ":TIMebase:POSition?"),
        reason=(
            "dry-run will query the current timebase and widen scale only if the "
            "requested X cursor positions are outside the visible range"
        ),
    )


def cursor_auto_timebase_json(result: CursorAutoTimebaseResult) -> dict[str, object]:
    return {
        "enabled": result.enabled,
        "strategy": result.strategy,
        "changed": result.changed,
        "original_scale_seconds_per_division": result.original_scale_seconds_per_division,
        "original_position_seconds": result.original_position_seconds,
        "target_scale_seconds_per_division": result.target_scale_seconds_per_division,
        "commands": list(result.commands),
        "reason": result.reason,
    }


def cursor_auto_vertical_plan(
    source_channel: int,
    current_scale_volts_per_division: float,
    current_offset_volts: float,
    *,
    y1_volts: float | None = None,
    y2_volts: float | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> CursorAutoVerticalResult:
    channel = (
        validate_analog_channel(source_channel, capabilities)
        if capabilities is not None
        else source_channel
    )
    current_scale_volts_per_division = validate_finite_number(
        current_scale_volts_per_division,
        "channel scale",
    )
    current_offset_volts = validate_finite_number(
        current_offset_volts,
        "channel offset",
    )
    if current_scale_volts_per_division <= 0:
        raise ParameterValidationError("channel scale must be greater than 0 V/div.")
    targets = _cursor_y_targets(y1_volts=y1_volts, y2_volts=y2_volts)
    min_y = min(targets)
    max_y = max(targets)
    usable_half_span_volts = current_scale_volts_per_division * 3.5
    max_delta_volts = max(abs(value - current_offset_volts) for value in targets)
    changed = max_delta_volts > usable_half_span_volts
    target_scale = current_scale_volts_per_division
    target_offset = current_offset_volts
    offset_changed = False
    commands = [channel_scale_query(channel), channel_offset_query(channel)]
    if changed:
        scale_only = max(current_scale_volts_per_division, max_delta_volts / 3.5)
        midpoint = (min_y + max_y) / 2.0
        midpoint_half_span = max(abs(min_y - midpoint), abs(max_y - midpoint))
        midpoint_scale = max(current_scale_volts_per_division, midpoint_half_span / 3.5)
        if scale_only >= midpoint_scale * 1.5:
            target_scale = midpoint_scale
            target_offset = midpoint
            offset_changed = target_offset != current_offset_volts
        else:
            target_scale = scale_only
        commands.append(channel_scale_command(channel, target_scale))
        if offset_changed:
            commands.append(channel_offset_command(channel, target_offset))
    reason = (
        "requested Y cursor position is outside the current vertical display range"
        if changed
        else "requested Y cursor positions fit within the current vertical display range"
    )
    return CursorAutoVerticalResult(
        enabled=True,
        strategy="scale_then_offset",
        changed=changed,
        offset_changed=offset_changed,
        original_scale_volts_per_division=current_scale_volts_per_division,
        original_offset_volts=current_offset_volts,
        target_scale_volts_per_division=target_scale,
        target_offset_volts=target_offset,
        commands=tuple(commands),
        reason=reason,
    )


def cursor_auto_vertical_dry_run_plan(source_channel: int) -> CursorAutoVerticalResult:
    return CursorAutoVerticalResult(
        enabled=True,
        strategy="scale_then_offset",
        changed=None,
        offset_changed=None,
        original_scale_volts_per_division=None,
        original_offset_volts=None,
        target_scale_volts_per_division=None,
        target_offset_volts=None,
        commands=(channel_scale_query(source_channel), channel_offset_query(source_channel)),
        reason=(
            "dry-run will query the source channel vertical settings and adjust "
            "scale/offset only if requested Y cursor positions are outside the "
            "visible range"
        ),
    )


def cursor_auto_vertical_json(result: CursorAutoVerticalResult) -> dict[str, object]:
    return {
        "enabled": result.enabled,
        "strategy": result.strategy,
        "changed": result.changed,
        "offset_changed": result.offset_changed,
        "original_scale_volts_per_division": result.original_scale_volts_per_division,
        "original_offset_volts": result.original_offset_volts,
        "target_scale_volts_per_division": result.target_scale_volts_per_division,
        "target_offset_volts": result.target_offset_volts,
        "commands": list(result.commands),
        "reason": result.reason,
    }


def _cursor_y_targets(*, y1_volts: float | None, y2_volts: float | None) -> tuple[float, ...]:
    targets = []
    if y1_volts is not None:
        targets.append(validate_finite_number(y1_volts, "--y1"))
    if y2_volts is not None:
        targets.append(validate_finite_number(y2_volts, "--y2"))
    if not targets:
        raise ParameterValidationError("--auto-vertical requires --y1 or --y2.")
    return tuple(targets)


def autoscale_commands(
    channels: Sequence[int] | None,
    *,
    acquire_mode: str | None = None,
    channels_mode: str | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    commands: list[str] = []
    if acquire_mode is not None:
        commands.append(f":AUToscale:AMODe {normalize_autoscale_acquire_mode(acquire_mode)}")
    if channels_mode is not None:
        commands.append(f":AUToscale:CHANnels {normalize_autoscale_channels_mode(channels_mode)}")
    if channels:
        validated = [
            validate_analog_channel(channel, capabilities) if capabilities is not None else channel
            for channel in channels
        ]
        joined = ",".join(f"CHANnel{channel}" for channel in validated)
        commands.append(f":AUToscale {joined}")
    else:
        commands.append(":AUToscale")
    return commands


def normalize_autoscale_acquire_mode(value: str) -> str:
    try:
        return _AUTOSCALE_ACQUIRE_MODES[value.strip().lower()]
    except KeyError as exc:
        raise ParameterValidationError("--acquire-mode must be normal or current.") from exc


def normalize_autoscale_channels_mode(value: str) -> str:
    try:
        return _AUTOSCALE_CHANNEL_MODES[value.strip().lower()]
    except KeyError as exc:
        raise ParameterValidationError("--channels must be all or displayed.") from exc


def setup_save_command(*, slot: int | None = None, file_spec: str | None = None) -> str:
    target = setup_target(slot=slot, file_spec=file_spec)
    return f":SAVE:SETup {target}"


def setup_recall_command(*, slot: int | None = None, file_spec: str | None = None) -> str:
    target = setup_target(slot=slot, file_spec=file_spec)
    return f":RECall:SETup {target}"


def setup_target(*, slot: int | None = None, file_spec: str | None = None) -> str:
    if (slot is None) == (file_spec is None):
        raise ParameterValidationError("setup commands require exactly one of --slot or --file.")
    if slot is not None:
        if slot < 0 or slot > 9:
            raise ParameterValidationError("--slot must be between 0 and 9.")
        return str(slot)
    assert file_spec is not None
    if '"' in file_spec or "'" in file_spec:
        raise ParameterValidationError("--file must not contain quotes.")
    suffix = PureWindowsPath(file_spec).suffix
    if suffix and suffix.lower() != ".scp":
        raise ParameterValidationError("--file extension must be .scp when provided.")
    return f'"{file_spec}"'


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


def math_display_command(
    function: int,
    enabled: bool,
    *,
    capabilities: ScopeCapabilities | None = None,
) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("Math display enabled value must be a boolean.")
    prefix = math_function_scpi_prefix(function, capabilities)
    return f"{prefix}:DISPlay {'ON' if enabled else 'OFF'}"


def math_display_query(
    function: int, *, capabilities: ScopeCapabilities | None = None
) -> str:
    return f"{math_function_scpi_prefix(function, capabilities)}:DISPlay?"


def parse_math_display(raw: str) -> bool:
    normalized = raw.strip().upper()
    if normalized in {"1", "ON"}:
        return True
    if normalized in {"0", "OFF"}:
        return False
    raise ChannelResponseError(f"Could not parse Math display response: {raw!r}")


def math_vertical_commands(
    function: int,
    *,
    scale: float | None = None,
    range_value: float | None = None,
    offset: float | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    if scale is not None and range_value is not None:
        raise ParameterValidationError("--scale and --range are mutually exclusive.")
    if scale is None and range_value is None and offset is None:
        raise ParameterValidationError(
            "Math vertical configure requires --scale, --range, or --offset."
        )
    commands: list[str] = []
    if scale is not None:
        commands.append(
            f"{prefix}:SCALe {_format_number(validate_positive(scale, '--scale'))}"
        )
    if range_value is not None:
        commands.append(
            f"{prefix}:RANGe "
            f"{_format_number(validate_positive(range_value, '--range'))}"
        )
    if offset is not None:
        commands.append(
            f"{prefix}:OFFSet {_format_number(validate_finite_number(offset, '--offset'))}"
        )
    return commands


def math_vertical_query_commands(
    function: int, *, capabilities: ScopeCapabilities | None = None
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    return [
        f"{prefix}:SCALe?",
        f"{prefix}:RANGe?",
        f"{prefix}:OFFSet?",
    ]


def math_operator_commands(
    function: int,
    operation: str,
    source1: str,
    source2: str,
    *,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    operation = normalize_math_operation(operation)
    source1 = normalize_math_source(source1, capabilities=capabilities)
    source2 = normalize_math_source(source2, capabilities=capabilities)
    return [
        f"{prefix}:OPERation {_MATH_OPERATION_TOKENS[operation]}",
        f"{prefix}:SOURce1 CHANnel{source1.removeprefix('channel')}",
        f"{prefix}:SOURce2 CHANnel{source2.removeprefix('channel')}",
    ]


def math_operator_query_commands(
    function: int, *, capabilities: ScopeCapabilities | None = None
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    return [
        f"{prefix}:OPERation?",
        f"{prefix}:SOURce1?",
        f"{prefix}:SOURce2?",
    ]


def math_composite_source_commands(
    operation: str,
    source1: str,
    source2: str,
    *,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    _validate_math_goft_capability(capabilities)
    operation = normalize_math_composite_operation(operation)
    source1 = normalize_math_source(
        source1,
        capabilities=capabilities,
        option_names="--source1 and --source2",
    )
    source2 = normalize_math_source(
        source2,
        capabilities=capabilities,
        option_names="--source1 and --source2",
    )
    return [
        f":FUNCtion:GOFT:OPERation {_MATH_COMPOSITE_OPERATION_TOKENS[operation]}",
        f":FUNCtion:GOFT:SOURce1 CHANnel{source1.removeprefix('channel')}",
        f":FUNCtion:GOFT:SOURce2 CHANnel{source2.removeprefix('channel')}",
    ]


def math_composite_source_query_commands(
    *, capabilities: ScopeCapabilities | None = None
) -> list[str]:
    _validate_math_goft_capability(capabilities)
    return [
        ":FUNCtion:GOFT:OPERation?",
        ":FUNCtion:GOFT:SOURce1?",
        ":FUNCtion:GOFT:SOURce2?",
    ]


def math_transform_commands(
    function: int,
    operation: str,
    source: str,
    *,
    input_offset: float | None = None,
    gain: float | None = None,
    linear_offset: float | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    operation = normalize_math_transform(operation)
    source = normalize_math_source1(
        source,
        function,
        capabilities=capabilities,
        allow_composite=True,
        option_names="--source",
    )
    if operation != "integrate" and input_offset is not None:
        raise ParameterValidationError(
            "--input-offset is only valid with --operation integrate."
        )
    if operation != "linear" and (gain is not None or linear_offset is not None):
        raise ParameterValidationError(
            "--gain and --linear-offset are only valid with --operation linear."
        )
    commands = [
        f"{prefix}:OPERation {_MATH_TRANSFORM_TOKENS[operation]}",
        f"{prefix}:SOURce1 {_math_source_scpi_token(source)}",
    ]
    if input_offset is not None:
        commands.append(
            f"{prefix}:INTegrate:IOFFset "
            f"{_format_number(validate_finite_number(input_offset, '--input-offset'))}"
        )
    if gain is not None:
        commands.append(
            f"{prefix}:LINear:GAIN "
            f"{_format_number(validate_finite_number(gain, '--gain'))}"
        )
    if linear_offset is not None:
        commands.append(
            f"{prefix}:LINear:OFFSet "
            f"{_format_number(validate_finite_number(linear_offset, '--linear-offset'))}"
        )
    return commands


def math_transform_query_commands(
    function: int, *, capabilities: ScopeCapabilities | None = None
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    return [
        f"{prefix}:OPERation?",
        f"{prefix}:SOURce1?",
    ]


def math_filter_commands(
    function: int,
    operation: str,
    source: str,
    *,
    cutoff_hz: float | None = None,
    average_count: int | None = None,
    smooth_points: int | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    operation = normalize_math_filter_operation(operation)
    _validate_math_filter_capability(operation, capabilities)
    source = normalize_math_source1(
        source,
        function,
        capabilities=capabilities,
        allow_composite=True,
        option_names="--source",
    )
    if operation not in {"low-pass", "high-pass"} and cutoff_hz is not None:
        raise ParameterValidationError(
            "--cutoff-hz is only valid with --operation low-pass or high-pass."
        )
    if operation != "average" and average_count is not None:
        raise ParameterValidationError(
            "--average-count is only valid with --operation average."
        )
    if operation != "smooth" and smooth_points is not None:
        raise ParameterValidationError(
            "--smooth-points is only valid with --operation smooth."
        )
    commands = [
        f"{prefix}:OPERation {_MATH_FILTER_TOKENS[operation]}",
        f"{prefix}:SOURce1 {_math_source_scpi_token(source)}",
    ]
    if cutoff_hz is not None:
        cutoff_hz = validate_positive(cutoff_hz, "--cutoff-hz")
        filter_path = "LOWPass" if operation == "low-pass" else "HIGHpass"
        commands.append(
            f"{prefix}:FREQuency:{filter_path} {_format_number(cutoff_hz)}"
        )
    if average_count is not None:
        commands.append(
            f"{prefix}:AVERage:COUNt {validate_math_average_count(average_count)}"
        )
    if smooth_points is not None:
        commands.append(
            f"{prefix}:SMOoth:POINts {validate_math_smooth_points(smooth_points)}"
        )
    return commands


def math_filter_query_commands(
    function: int, *, capabilities: ScopeCapabilities | None = None
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    if capabilities is not None and not capabilities.math_filter_operations:
        raise ParameterValidationError(
            "Math filters are not supported by this capability profile."
        )
    return [
        f"{prefix}:OPERation?",
        f"{prefix}:SOURce1?",
    ]


def math_visualization_commands(
    function: int,
    operation: str,
    *,
    source: str | None = None,
    source2: str | None = None,
    measurement: str | None = None,
    measurement_slot: int | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    operation = normalize_math_visualization_operation(operation)
    _validate_math_visualization_capability(operation, capabilities)
    commands = [
        f"{prefix}:OPERation {_MATH_VISUALIZATION_TOKENS[operation]}"
    ]
    if operation != "trend":
        if source is None:
            raise ParameterValidationError(
                "Math visualization configure requires --source."
            )
        if any(
            value is not None
            for value in (source2, measurement, measurement_slot)
        ):
            raise ParameterValidationError(
                "--source2, --measurement, and --measurement-slot are only "
                "valid with --operation trend."
            )
        normalized_source = normalize_math_source1(
            source,
            function,
            capabilities=capabilities,
            allow_composite=True,
            option_names="--source",
        )
        commands.append(
            f"{prefix}:SOURce1 {_math_source_scpi_token(normalized_source)}"
        )
        return commands

    is_4000x = (
        capabilities.series == "4000X"
        if capabilities is not None
        else measurement_slot is not None
    )
    if is_4000x:
        if any(value is not None for value in (source, source2, measurement)):
            raise ParameterValidationError(
                "4000X Trend accepts --measurement-slot and does not accept "
                "--source, --source2, or --measurement."
            )
        slot = validate_math_trend_measurement_slot(measurement_slot)
        commands.append(f"{prefix}:TRENd:NMEasurement MEAS{slot}")
        return commands

    if measurement_slot is not None:
        raise ParameterValidationError(
            "--measurement-slot is only valid for 4000X Trend."
        )
    if source is None or measurement is None:
        raise ParameterValidationError(
            "2000X/3000X Trend requires --source and --measurement."
        )
    normalized_source = normalize_math_source(
        source,
        capabilities=capabilities,
        option_names="--source",
    )
    normalized_measurement = normalize_math_trend_measurement(measurement)
    commands.append(
        f"{prefix}:SOURce1 {_math_source_scpi_token(normalized_source)}"
    )
    if normalized_measurement == "vratio":
        if source2 is None:
            raise ParameterValidationError(
                "--source2 is required with Trend measurement vratio."
            )
        normalized_source2 = normalize_math_source(
            source2,
            capabilities=capabilities,
            option_names="--source2",
        )
        commands.append(
            f"{prefix}:SOURce2 {_math_source_scpi_token(normalized_source2)}"
        )
    elif source2 is not None:
        raise ParameterValidationError(
            "--source2 is only valid with Trend measurement vratio."
        )
    commands.append(
        f"{prefix}:TRENd:MEASurement "
        f"{_MATH_TREND_MEASUREMENT_TOKENS[normalized_measurement]}"
    )
    return commands


def math_visualization_query_commands(
    function: int, *, capabilities: ScopeCapabilities | None = None
) -> list[str]:
    prefix = math_function_scpi_prefix(function, capabilities)
    if (
        capabilities is not None
        and not capabilities.math_visualization_operations
    ):
        raise ParameterValidationError(
            "Math visualizations are not supported by this capability profile."
        )
    return [f"{prefix}:OPERation?"]


def math_clear_command(
    function: int, *, capabilities: ScopeCapabilities | None = None
) -> str:
    prefix = math_function_scpi_prefix(function, capabilities)
    accumulation_operations = (
        capabilities.math_filter_operations
        | capabilities.math_visualization_operations
        if capabilities is not None
        else frozenset()
    )
    if capabilities is not None and not (
        {"average", "max-hold", "min-hold"} & accumulation_operations
    ):
        raise ParameterValidationError(
            "Math clear is not supported by this capability profile."
        )
    return f"{prefix}:CLEar"


def normalize_math_operation(value: str) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError(
            "--operation must be add, subtract, multiply, or divide."
        )
    normalized = value.strip().lower()
    if normalized not in _MATH_OPERATION_TOKENS:
        raise ParameterValidationError(
            "--operation must be add, subtract, multiply, or divide."
        )
    return normalized


def normalize_math_source(
    value: str,
    *,
    capabilities: ScopeCapabilities | None = None,
    option_names: str = "--source1 and --source2",
) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError(
            f"{option_names} must be channel1, channel2, channel3, or channel4."
        )
    normalized = value.strip().lower()
    if normalized not in MATH_SOURCES:
        raise ParameterValidationError(
            f"{option_names} must be channel1, channel2, channel3, or channel4."
        )
    channel = int(normalized.removeprefix("channel"))
    if capabilities is not None:
        validate_analog_channel(channel, capabilities)
    return normalized


def normalize_math_source1(
    value: str,
    function: int,
    *,
    capabilities: ScopeCapabilities | None = None,
    allow_composite: bool = False,
    option_names: str = "--source1",
) -> str:
    function = validate_function_number(function)
    if not isinstance(value, str):
        raise ParameterValidationError(
            f"{option_names} must be a supported Math source."
        )
    normalized = value.strip().lower()
    if normalized.startswith("channel"):
        return normalize_math_source(
            normalized,
            capabilities=capabilities,
            option_names=option_names,
        )
    if normalized == "composite":
        if not allow_composite:
            raise ParameterValidationError(
                f"{option_names} does not support the composite source."
            )
        if capabilities is not None and not capabilities.supports_math_goft:
            raise ParameterValidationError(
                "The composite Math source is not supported by this capability profile."
            )
        return normalized
    if normalized not in {"math1", "math2", "math3"}:
        raise ParameterValidationError(
            f"{option_names} must be a supported Math source."
        )
    source_function = int(normalized.removeprefix("math"))
    if capabilities is not None:
        if not capabilities.supports_math_cascade:
            raise ParameterValidationError(
                "Math function sources are not supported by this capability profile."
            )
        if source_function > capabilities.math_function_count:
            raise ParameterValidationError(
                "Math source function exceeds this capability profile."
            )
    if source_function >= function:
        raise ParameterValidationError(
            "Math source function must be lower than the destination function."
        )
    return normalized


def parse_math_operation(raw: str) -> str:
    raw_value = raw.strip()
    operation = _MATH_OPERATION_READBACKS.get(raw_value.upper())
    if operation is None:
        raise ChannelResponseError(
            f"Could not parse Math operation response: {raw_value!r}"
        )
    return operation


def normalize_math_composite_operation(value: str) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError(
            "--operation must be add, subtract, or multiply."
        )
    normalized = value.strip().lower()
    if normalized not in _MATH_COMPOSITE_OPERATION_TOKENS:
        raise ParameterValidationError(
            "--operation must be add, subtract, or multiply."
        )
    return normalized


def parse_math_composite_operation(raw: str) -> str:
    raw_value = raw.strip()
    operation = _MATH_COMPOSITE_OPERATION_READBACKS.get(raw_value.upper())
    if operation is None:
        raise ChannelResponseError(
            f"Could not parse Math composite operation response: {raw_value!r}"
        )
    return operation


def normalize_math_transform(value: str) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError(
            "--operation must be a supported single-source Math transform."
        )
    normalized = value.strip().lower()
    if normalized not in _MATH_TRANSFORM_TOKENS:
        raise ParameterValidationError(
            "--operation must be a supported single-source Math transform."
        )
    return normalized


def parse_math_transform(raw: str) -> str:
    raw_value = raw.strip()
    operation = _MATH_TRANSFORM_READBACKS.get(raw_value.upper())
    if operation is None:
        raise ChannelResponseError(
            f"Could not parse Math transform response: {raw_value!r}"
        )
    return operation


def normalize_math_filter_operation(value: str) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError(
            "--operation must be a supported instrument-side Math filter."
        )
    normalized = value.strip().lower()
    if normalized not in _MATH_FILTER_TOKENS:
        raise ParameterValidationError(
            "--operation must be a supported instrument-side Math filter."
        )
    return normalized


def parse_math_filter_operation(raw: str) -> str:
    raw_value = raw.strip()
    operation = _MATH_FILTER_READBACKS.get(raw_value.upper())
    if operation is None:
        raise ChannelResponseError(
            f"Could not parse Math filter response: {raw_value!r}"
        )
    return operation


def normalize_math_visualization_operation(value: str) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError(
            "--operation must be a supported instrument-side Math visualization."
        )
    normalized = value.strip().lower()
    if normalized not in _MATH_VISUALIZATION_TOKENS:
        raise ParameterValidationError(
            "--operation must be a supported instrument-side Math visualization."
        )
    return normalized


def parse_math_visualization_operation(raw: str) -> str:
    raw_value = raw.strip()
    operation = _MATH_VISUALIZATION_READBACKS.get(raw_value.upper())
    if operation is None:
        raise ChannelResponseError(
            f"Could not parse Math visualization response: {raw_value!r}"
        )
    return operation


def normalize_math_trend_measurement(value: str) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError(
            "--measurement must be a supported Trend measurement."
        )
    normalized = value.strip().lower()
    if normalized not in _MATH_TREND_MEASUREMENT_TOKENS:
        raise ParameterValidationError(
            "--measurement must be a supported Trend measurement."
        )
    return normalized


def parse_math_trend_measurement(raw: str) -> str:
    raw_value = raw.strip()
    measurement = _MATH_TREND_MEASUREMENT_READBACKS.get(raw_value.upper())
    if measurement is None:
        raise ChannelResponseError(
            f"Could not parse Math Trend measurement response: {raw_value!r}"
        )
    return measurement


def validate_math_trend_measurement_slot(value: int | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ParameterValidationError(
            "--measurement-slot must be an integer."
        )
    if value < 1 or value > 10:
        raise ParameterValidationError(
            "--measurement-slot must be between 1 and 10."
        )
    return value


def parse_math_trend_measurement_slot(raw: str) -> int | None:
    raw_value = raw.strip()
    normalized = raw_value.upper()
    if normalized == "NONE":
        return None
    if normalized.startswith("MEAS"):
        suffix = normalized.removeprefix("MEAS")
        if suffix.isdigit():
            try:
                return validate_math_trend_measurement_slot(int(suffix))
            except (ValueError, OverflowError, ParameterValidationError):
                pass
    raise ChannelResponseError(
        f"Could not parse Math Trend measurement slot response: {raw_value!r}"
    )


def validate_math_average_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ParameterValidationError("--average-count must be an integer.")
    if value < 2 or value > 65536:
        raise ParameterValidationError(
            "--average-count must be between 2 and 65536."
        )
    if value & (value - 1):
        raise ParameterValidationError("--average-count must be a power of two.")
    return value


def validate_math_smooth_points(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ParameterValidationError("--smooth-points must be an integer.")
    if value.bit_length() > 63:
        raise ParameterValidationError("--smooth-points is too large.")
    if value < 3:
        raise ParameterValidationError("--smooth-points must be at least 3.")
    if value % 2 == 0:
        raise ParameterValidationError("--smooth-points must be odd.")
    return value


def _parse_math_filter_integer_response(
    raw: str,
    setting_name: str,
    validator: Callable[[int], int],
) -> int:
    try:
        numeric_value = float(raw)
        if not math.isfinite(numeric_value) or not numeric_value.is_integer():
            raise ValueError
        return validator(int(numeric_value))
    except (TypeError, ValueError, OverflowError, ParameterValidationError) as exc:
        raise ChannelResponseError(
            f"Could not parse Math {setting_name} response: {raw!r}"
        ) from exc


def _validate_math_filter_capability(
    operation: str, capabilities: ScopeCapabilities | None
) -> None:
    if (
        capabilities is not None
        and operation not in capabilities.math_filter_operations
    ):
        raise ParameterValidationError(
            f"Math filter operation {operation!r} is not supported by this "
            "capability profile."
        )


def _validate_math_visualization_capability(
    operation: str, capabilities: ScopeCapabilities | None
) -> None:
    if (
        capabilities is not None
        and operation not in capabilities.math_visualization_operations
    ):
        raise ParameterValidationError(
            f"Math visualization operation {operation!r} is not supported by "
            "this capability profile."
        )


def parse_math_source(
    raw: str, *, capabilities: ScopeCapabilities | None = None
) -> str:
    raw_value = raw.strip()
    normalized = raw_value.upper()
    if normalized.startswith("CHANNEL"):
        suffix = normalized.removeprefix("CHANNEL")
    elif normalized.startswith("CHAN"):
        suffix = normalized.removeprefix("CHAN")
    else:
        suffix = ""
    if not suffix.isdigit():
        raise ChannelResponseError(
            f"Could not parse Math source response: {raw_value!r}"
        )
    try:
        channel = int(suffix)
        if channel < 1 or channel > 4:
            raise ParameterValidationError("Math source channel is out of range.")
        if capabilities is not None:
            validate_analog_channel(channel, capabilities)
    except (ValueError, OverflowError, ParameterValidationError) as exc:
        raise ChannelResponseError(
            f"Could not parse Math source response: {raw_value!r}"
        ) from exc
    return f"channel{channel}"


def parse_math_source1(
    raw: str,
    function: int,
    *,
    capabilities: ScopeCapabilities | None = None,
    allow_composite: bool = False,
) -> str:
    raw_value = raw.strip()
    normalized = raw_value.upper()
    if normalized.startswith("CHAN"):
        return parse_math_source(raw_value, capabilities=capabilities)
    if normalized == "GOFT":
        candidate = "composite"
    else:
        match = None
        for prefix in ("FUNCTION", "FUNC", "MATH"):
            if normalized.startswith(prefix):
                suffix = normalized.removeprefix(prefix)
                if suffix.isdigit():
                    try:
                        match = f"math{int(suffix)}"
                    except (ValueError, OverflowError):
                        match = None
                break
        candidate = match or ""
    try:
        return normalize_math_source1(
            candidate,
            function,
            capabilities=capabilities,
            allow_composite=allow_composite,
        )
    except ParameterValidationError as exc:
        raise ChannelResponseError(
            f"Could not parse Math source response: {raw_value!r}"
        ) from exc


def _math_source_scpi_token(source: str) -> str:
    if source.startswith("channel"):
        return f"CHANnel{source.removeprefix('channel')}"
    if source == "composite":
        return "GOFT"
    return f"FUNCtion{source.removeprefix('math')}"


def _validate_math_goft_capability(
    capabilities: ScopeCapabilities | None,
) -> None:
    if capabilities is not None and not capabilities.supports_math_goft:
        raise ParameterValidationError(
            "Math composite source is not supported by this capability profile."
        )


def math_function_scpi_prefix(
    function: int, capabilities: ScopeCapabilities | None = None
) -> str:
    function = validate_function_number(function)
    if capabilities is not None and capabilities.math_function_count <= 0:
        raise ParameterValidationError(
            "Math functions are not supported by this capability profile."
        )
    if capabilities is not None and function > capabilities.math_function_count:
        raise ParameterValidationError(
            f"--function must be between 1 and {capabilities.math_function_count}."
        )
    if capabilities is not None and capabilities.math_function_count == 1:
        return ":FUNCtion"
    return f":FUNCtion{function}"


def validate_function_number(function: int) -> int:
    if isinstance(function, bool) or not isinstance(function, int):
        raise ParameterValidationError("--function must be an integer.")
    if function < 1 or function > 4:
        raise ParameterValidationError("--function must be between 1 and 4.")
    return function


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


def _query_math_finite_number(
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
            f"Could not parse Math {setting_name} response: {raw!r}"
        ) from exc


def validate_finite_number(value: float, option: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParameterValidationError(f"{option} must be a finite number.")
    try:
        finite = math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        finite = False
    if not finite:
        raise ParameterValidationError(f"{option} must be a finite number.")
    return value


def validate_nonnegative(value: float, option: str) -> float:
    value = validate_finite_number(value, option)
    if value < 0:
        raise ParameterValidationError(f"{option} must be non-negative.")
    return value


def validate_positive(value: float, option: str) -> float:
    value = validate_finite_number(value, option)
    if value <= 0:
        raise ParameterValidationError(f"{option} must be greater than zero.")
    return value


def _format_number(value: float) -> str:
    return f"{value:.12g}"


def _format_scpi_number(value: float) -> str:
    value = validate_finite_number(value, "SCPI numeric value")
    return f"{value:.12g}".replace("e-0", "e-").replace("e+0", "e+")
