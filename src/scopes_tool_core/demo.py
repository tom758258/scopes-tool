"""Built-in DEMO output controls for supported InfiniiVision X-Series scopes."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .capabilities import ScopeCapabilities
from .errors import DemoResponseError, ParameterValidationError
from .scpi import SCPIClient


DEMO_FUNCTION_TOKENS = {
    "sine": "SIN",
    "noisy": "NOIS",
    "phase": "PHAS",
    "lf-sine": "LFS",
    "am": "AM",
    "rf-burst": "RFB",
    "fm-burst": "FMB",
    "harmonics": "HARM",
    "coupling": "COUP",
    "ringing": "RING",
    "single": "SING",
    "clock": "CLK",
    "runt": "RUNT",
    "transition": "TRAN",
    "setup-hold": "SHOL",
    "mso": "MSO",
    "burst": "BURS",
    "glitch": "GLIT",
    "edge-then-edge": "ETE",
    "i2c": "I2C",
    "uart": "UART",
    "spi": "SPI",
    "can": "CAN",
    "lin": "LIN",
    "i2s": "I2S",
    "can-lin": "CANL",
    "flexray": "FLEX",
    "arinc": "ARIN",
    "mil": "MIL",
    "mil2": "MIL2",
}
DEMO_FUNCTIONS = tuple(DEMO_FUNCTION_TOKENS)
_DEMO_TOKEN_FUNCTIONS = {token: name for name, token in DEMO_FUNCTION_TOKENS.items()}
_DEMO_FUNCTION_READBACK_ALIASES = {
    "SINGL": "single",
    "CANLIN": "can-lin",
    "ARINC": "arinc",
    "FLEXRAY": "flexray",
    "TRANSITION": "transition",
    "RFBURST": "rf-burst",
    "FMBURST": "fm-burst",
    "HARMONICS": "harmonics",
    "COUPLING": "coupling",
    "RINGING": "ringing",
    "BURST": "burst",
    "GLITCH": "glitch",
    "LFSINE": "lf-sine",
    "SINUSOID": "sine",
    "NOISY": "noisy",
    "PHASE": "phase",
    "SHOLD": "setup-hold",
}


@dataclass(frozen=True)
class DemoOutputState:
    enabled: bool
    output_raw: str

    def to_json(self) -> dict[str, object]:
        return {"enabled": self.enabled, "output_raw": self.output_raw}


@dataclass(frozen=True)
class DemoFunctionState:
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
class DemoPhaseState:
    phase_degrees: float
    phase_raw: str

    def to_json(self) -> dict[str, object]:
        return {"phase_degrees": self.phase_degrees, "phase_raw": self.phase_raw}


@dataclass(frozen=True)
class DemoState:
    function: str | None
    function_scpi: str | None
    function_raw: str
    enabled: bool
    output_raw: str
    phase_degrees: float
    phase_raw: str

    def to_json(self) -> dict[str, object]:
        return {
            "function": self.function,
            "function_scpi": self.function_scpi,
            "function_raw": self.function_raw,
            "enabled": self.enabled,
            "output_raw": self.output_raw,
            "phase_degrees": self.phase_degrees,
            "phase_raw": self.phase_raw,
        }


class DemoController:
    """Controller for DEMO output controls."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        if not capabilities.supports_demo:
            raise ParameterValidationError(
                "DEMO output is not supported by this model profile."
            )
        self.scpi = scpi
        self.capabilities = capabilities

    def configure_output(self, enabled: bool) -> None:
        self.scpi.write(demo_output_command(enabled))

    def query_output(self) -> DemoOutputState:
        raw = self.scpi.query(demo_output_query()).strip()
        return DemoOutputState(parse_demo_bool(raw), raw)

    def configure_function(self, function: str) -> None:
        self.scpi.write(demo_function_command(function, capabilities=self.capabilities))

    def query_function(self) -> DemoFunctionState:
        raw = self.scpi.query(demo_function_query()).strip()
        function, token = parse_demo_function(raw)
        return DemoFunctionState(function, token, raw)

    def configure_phase(self, degrees: float) -> None:
        self.scpi.write(demo_phase_command(degrees))

    def query_phase(self) -> DemoPhaseState:
        raw = self.scpi.query(demo_phase_query()).strip()
        return DemoPhaseState(parse_demo_phase(raw), raw)

    def query(self) -> DemoState:
        function = self.query_function()
        output = self.query_output()
        phase = self.query_phase()
        return DemoState(
            function=function.function,
            function_scpi=function.function_scpi,
            function_raw=function.function_raw,
            enabled=output.enabled,
            output_raw=output.output_raw,
            phase_degrees=phase.phase_degrees,
            phase_raw=phase.phase_raw,
        )


def demo_output_command(enabled: bool) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("DEMO output enabled value must be a boolean.")
    return f":DEMO:OUTPut {'ON' if enabled else 'OFF'}"


def demo_output_query() -> str:
    return ":DEMO:OUTPut?"


def demo_function_command(function: str, *, capabilities: ScopeCapabilities) -> str:
    token = validate_demo_function(function, capabilities)
    return f":DEMO:FUNCtion {token}"


def demo_function_query() -> str:
    return ":DEMO:FUNCtion?"


def demo_phase_command(degrees: float) -> str:
    value = validate_demo_phase(degrees)
    return f":DEMO:FUNCtion:PHASe:PHASe {value:g}"


def demo_phase_query() -> str:
    return ":DEMO:FUNCtion:PHASe:PHASe?"


def demo_query_commands() -> list[str]:
    return [demo_function_query(), demo_output_query(), demo_phase_query()]


def validate_demo_function(function: str, capabilities: ScopeCapabilities) -> str:
    if not isinstance(function, str) or function not in DEMO_FUNCTION_TOKENS:
        raise ParameterValidationError(
            "DEMO function must be one of: " + ", ".join(DEMO_FUNCTIONS) + "."
        )
    if not capabilities.supports_demo or function not in capabilities.demo_functions:
        raise ParameterValidationError(
            f"DEMO function {function!r} is not supported by the selected "
            f"{capabilities.series} model profile."
        )
    return DEMO_FUNCTION_TOKENS[function]


def validate_demo_phase(degrees: float) -> float:
    if isinstance(degrees, bool) or not isinstance(degrees, (int, float)):
        raise ParameterValidationError("DEMO phase must be a number.")
    value = float(degrees)
    if not math.isfinite(value):
        raise ParameterValidationError("DEMO phase must be finite.")
    if not 0.0 <= value <= 360.0:
        raise ParameterValidationError("DEMO phase must be between 0 and 360 degrees.")
    return value


def parse_demo_bool(raw: str) -> bool:
    normalized = raw.strip().upper()
    if normalized in {"1", "+1", "ON"}:
        return True
    if normalized in {"0", "+0", "OFF"}:
        return False
    raise DemoResponseError(f"Could not parse DEMO output response: {raw!r}")


def parse_demo_function(raw: str) -> tuple[str | None, str | None]:
    token = raw.strip().upper()
    function = _DEMO_TOKEN_FUNCTIONS.get(token)
    if function is not None:
        return function, token
    function = _DEMO_FUNCTION_READBACK_ALIASES.get(token)
    if function is None:
        return None, None
    return function, DEMO_FUNCTION_TOKENS[function]


def parse_demo_phase(raw: str) -> float:
    raw_value = raw.strip()
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise DemoResponseError(f"Could not parse DEMO phase response: {raw!r}") from exc
    if not math.isfinite(value):
        raise DemoResponseError(f"Could not parse DEMO phase response: {raw!r}")
    return value
