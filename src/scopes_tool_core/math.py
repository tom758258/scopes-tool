"""Math function controls and command/readback helpers."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from .capabilities import ScopeCapabilities
from .channel import validate_analog_channel
from .errors import ChannelResponseError, ParameterValidationError
from .scpi import SCPIClient


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
