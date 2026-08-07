"""Trigger controls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import math
import time

from .capabilities import ScopeCapabilities
from .channel import validate_analog_channel
from .errors import ParameterValidationError, TriggerResponseError
from .scpi import SCPIClient
from .workflow import StopRequested, interruptible_wait


_SLOPE_COMMANDS = {
    "positive": "POSitive",
    "pos": "POSitive",
    "rising": "POSitive",
    "negative": "NEGative",
    "neg": "NEGative",
    "falling": "NEGative",
    "either": "EITHer",
    "eith": "EITHer",
    "alternate": "ALTernate",
    "alt": "ALTernate",
}

_SLOPE_READBACKS = {
    "POS": "positive",
    "POSITIVE": "positive",
    "NEG": "negative",
    "NEGATIVE": "negative",
    "EITH": "either",
    "EITHER": "either",
    "ALT": "alternate",
    "ALTERNATE": "alternate",
}

_GLITCH_POLARITY_COMMANDS = {
    "positive": "POSitive",
    "pos": "POSitive",
    "negative": "NEGative",
    "neg": "NEGative",
}

_GLITCH_POLARITY_READBACKS = {
    "POS": "positive",
    "POSITIVE": "positive",
    "NEG": "negative",
    "NEGATIVE": "negative",
}

_GLITCH_QUALIFIER_COMMANDS = {
    "greater-than": "GREaterthan",
    "greater_than": "GREaterthan",
    "greaterthan": "GREaterthan",
    "gre": "GREaterthan",
    "less-than": "LESSthan",
    "less_than": "LESSthan",
    "lessthan": "LESSthan",
    "less": "LESSthan",
    "range": "RANGe",
    "rang": "RANGe",
}

_GLITCH_QUALIFIER_READBACKS = {
    "GRE": "greater-than",
    "GREATERTHAN": "greater-than",
    "LESS": "less-than",
    "LESSTHAN": "less-than",
    "RANG": "range",
    "RANGE": "range",
}

_RUNT_POLARITY_COMMANDS = {
    "positive": "POSitive",
    "negative": "NEGative",
    "either": "EITHer",
}

_RUNT_POLARITY_READBACKS = {
    "POS": "positive",
    "POSITIVE": "positive",
    "NEG": "negative",
    "NEGATIVE": "negative",
    "EITH": "either",
    "EITHER": "either",
}

_RUNT_QUALIFIER_COMMANDS = {
    "greater-than": "GREaterthan",
    "less-than": "LESSthan",
    "none": "NONE",
}

_RUNT_QUALIFIER_READBACKS = {
    "GRE": "greater-than",
    "GREATERTHAN": "greater-than",
    "LESS": "less-than",
    "LESSTHAN": "less-than",
    "NONE": "none",
}


_EDGE_COUPLING_COMMANDS = {
    'ac': 'AC',
    'dc': 'DC',
    'lf-reject': 'LFReject',
}

_EDGE_COUPLING_READBACKS = {
    'AC': 'ac',
    'DC': 'dc',
    'LFREJECT': 'lf-reject',
    'LFR': 'lf-reject',
}

_EDGE_REJECT_COMMANDS = {
    'off': 'OFF',
    'lf-reject': 'LFReject',
    'hf-reject': 'HFReject',
}

_EDGE_REJECT_READBACKS = {
    'OFF': 'off',
    'LFREJECT': 'lf-reject',
    'LFR': 'lf-reject',
    'HFREJECT': 'hf-reject',
    'HFR': 'hf-reject',
}

_EDGE_TRIGGER_SOURCE_COMMANDS = {
    "external": "EXTernal",
    "line": "LINE",
}

_EXTERNAL_TRIGGER_UNITS_COMMANDS = {
    "volts": "VOLT",
    "amps": "AMPere",
}

_EXTERNAL_TRIGGER_UNITS_READBACKS = {
    "VOLT": "volts",
    "AMP": "amps",
    "AMPERE": "amps",
}


def _validate_edge_coupling(coupling: str) -> None:
    if coupling not in _EDGE_COUPLING_COMMANDS:
        raise ParameterValidationError(
            f'Invalid Edge Trigger coupling {coupling!r}. '
            'Valid values are: ac, dc, lf-reject.'
        )


def _edge_coupling_token(coupling: str) -> str:
    return _EDGE_COUPLING_COMMANDS[coupling]


def _validate_edge_reject(reject: str) -> None:
    if reject not in _EDGE_REJECT_COMMANDS:
        raise ParameterValidationError(
            f'Invalid Edge Trigger reject {reject!r}. '
            'Valid values are: off, lf-reject, hf-reject.'
        )


def _edge_reject_token(reject: str) -> str:
    return _EDGE_REJECT_COMMANDS[reject]

_TRANSITION_SLOPE_COMMANDS = {
    "positive": "POSitive",
    "negative": "NEGative",
}

_TRANSITION_SLOPE_READBACKS = {
    "POS": "positive",
    "POSITIVE": "positive",
    "NEG": "negative",
    "NEGATIVE": "negative",
}

_TRANSITION_QUALIFIER_COMMANDS = {
    "greater-than": "GREaterthan",
    "less-than": "LESSthan",
}

_TRANSITION_QUALIFIER_READBACKS = {
    "GRE": "greater-than",
    "GREATERTHAN": "greater-than",
    "LESS": "less-than",
    "LESSTHAN": "less-than",
}

_DELAY_SLOPE_COMMANDS = {
    "positive": "POSitive",
    "negative": "NEGative",
}

_DELAY_SLOPE_READBACKS = {
    "POS": "positive",
    "POSITIVE": "positive",
    "NEG": "negative",
    "NEGATIVE": "negative",
}

_SETUP_HOLD_SLOPE_COMMANDS = {
    "positive": "POSitive",
    "negative": "NEGative",
}

_SETUP_HOLD_SLOPE_READBACKS = {
    "POS": "positive",
    "POSITIVE": "positive",
    "NEG": "negative",
    "NEGATIVE": "negative",
}

_EDGE_BURST_SLOPE_COMMANDS = {
    "positive": "POSitive",
    "negative": "NEGative",
}

_EDGE_BURST_SLOPE_READBACKS = {
    "POS": "positive",
    "POSITIVE": "positive",
    "NEG": "negative",
    "NEGATIVE": "negative",
}

_TV_STANDARD_COMMANDS = {
    "ntsc": "NTSC",
    "pal": "PAL",
    "palm": "PALM",
    "secam": "SECam",
}

_TV_STANDARD_READBACKS = {
    "NTSC": "ntsc",
    "PAL": "pal",
    "PALM": "palm",
    "SEC": "secam",
    "SECAM": "secam",
}

_TV_EXTENDED_STANDARDS = {
    "generic",
    "gen",
    "p480",
    "p720",
    "p1080",
    "i1080",
    "p480l60hz",
    "p720l60hz",
    "p1080l24hz",
    "p1080l25hz",
    "p1080l50hz",
    "p1080l60hz",
    "i1080l50hz",
    "i1080l60hz",
}

_TV_MODE_COMMANDS = {
    "field1": "FIEld1",
    "field2": "FIEld2",
    "all-fields": "AFIelds",
    "all-lines": "ALINes",
    "line-field1": "LFIeld1",
    "line-field2": "LFIeld2",
    "line-alternate": "LALTernate",
}

_TV_MODE_READBACKS = {
    "FIE1": "field1",
    "FIELD1": "field1",
    "FIE2": "field2",
    "FIELD2": "field2",
    "AFI": "all-fields",
    "AFIELDS": "all-fields",
    "ALIN": "all-lines",
    "ALINES": "all-lines",
    "LFI1": "line-field1",
    "LFIELD1": "line-field1",
    "LFI2": "line-field2",
    "LFIELD2": "line-field2",
    "LALT": "line-alternate",
    "LALTERNATE": "line-alternate",
}

_TV_LINE_MODES = frozenset(("line-field1", "line-field2", "line-alternate"))

_TV_LINE_RANGES = {
    ("ntsc", "line-field1"): (1, 263),
    ("ntsc", "line-field2"): (1, 262),
    ("ntsc", "line-alternate"): (1, 262),
    ("pal", "line-field1"): (1, 313),
    ("pal", "line-field2"): (314, 625),
    ("pal", "line-alternate"): (1, 312),
    ("palm", "line-field1"): (1, 263),
    ("palm", "line-field2"): (264, 525),
    ("palm", "line-alternate"): (1, 262),
    ("secam", "line-field1"): (1, 313),
    ("secam", "line-field2"): (314, 625),
    ("secam", "line-alternate"): (1, 312),
}

_TV_POLARITY_COMMANDS = {
    "positive": "POSitive",
    "negative": "NEGative",
}

_TV_POLARITY_READBACKS = {
    "POS": "positive",
    "POSITIVE": "positive",
    "NEG": "negative",
    "NEGATIVE": "negative",
}

_TRIGGER_SWEEP_COMMANDS = {
    "auto": "AUTO",
    "normal": "NORMal",
}

_TRIGGER_SWEEP_READBACKS = {
    "AUTO": "auto",
    "NORM": "normal",
    "NORMAL": "normal",
}

_PATTERN_FORMAT_READBACKS = {
    "ASC": "ascii",
    "ASCII": "ascii",
    "HEX": "hex",
}

_PATTERN_QUALIFIER_READBACKS = {
    "ENT": "entered",
    "ENTERED": "entered",
}

OPERATION_CONDITION_RUN_MASK = 1 << 3
OPERATION_CONDITION_RUI_ENAB_MASK = 1 << 4
OPERATION_CONDITION_WAIT_TRIG_MASK = 1 << 5


@dataclass(frozen=True)
class EdgeTriggerState:
    """Readback state for analog edge trigger settings."""

    source_channel: int
    level_volts: float
    slope: str


@dataclass(frozen=True)
class EdgeTriggerSourceState:
    """Readback state for the Edge Trigger source only."""

    source: str | None
    source_channel: int | None
    raw_source: str

    def to_json(self) -> dict[str, object]:
        return {
            "source": self.source,
            "source_channel": self.source_channel,
            "raw_source": self.raw_source,
        }


@dataclass(frozen=True)
class EdgeTriggerSlopeState:
    """Readback state for the Edge Trigger slope only."""

    slope: str | None
    raw_slope: str

    def to_json(self) -> dict[str, object]:
        return {"slope": self.slope, "raw_slope": self.raw_slope}


@dataclass(frozen=True)
class EdgeTriggerLevelState:
    """Readback state for one analog Edge Trigger level."""

    source_channel: int
    level_volts: float
    raw_level: str

    def to_json(self) -> dict[str, object]:
        return {
            "source_channel": self.source_channel,
            "level_volts": self.level_volts,
            "raw_level": self.raw_level,
        }


@dataclass(frozen=True)
class ExternalTriggerRangeState:
    """Readback state for the External trigger input range."""

    range_volts: float
    raw_range: str

    def to_json(self) -> dict[str, object]:
        return {"range_volts": self.range_volts, "raw_range": self.raw_range}


@dataclass(frozen=True)
class ExternalTriggerProbeState:
    """Readback state for the External trigger probe attenuation."""

    attenuation: float
    raw_attenuation: str

    def to_json(self) -> dict[str, object]:
        return {
            "attenuation": self.attenuation,
            "raw_attenuation": self.raw_attenuation,
        }


@dataclass(frozen=True)
class ExternalTriggerUnitsState:
    """Readback state for the External trigger input units."""

    units: str | None
    raw_units: str

    def to_json(self) -> dict[str, object]:
        return {"units": self.units, "raw_units": self.raw_units}


@dataclass(frozen=True)
class ExternalTriggerSettingsState:
    """Readback state parsed from the aggregate External input query."""

    probe_attenuation: float | None
    range_value: float | None
    units: str | None
    bandwidth_limit_enabled: bool | None
    raw_response: str

    def to_json(self) -> dict[str, object]:
        return {
            "probe_attenuation": self.probe_attenuation,
            "range_value": self.range_value,
            "units": self.units,
            "bandwidth_limit_enabled": self.bandwidth_limit_enabled,
            "raw_response": self.raw_response,
        }


@dataclass(frozen=True)
class EdgeTriggerExternalLevelState:
    """Readback state for the External-qualified Edge Trigger level."""

    level_volts: float
    raw_level: str

    def to_json(self) -> dict[str, object]:
        return {"level_volts": self.level_volts, "raw_level": self.raw_level}


@dataclass(frozen=True)
class TriggerSweepState:
    """Readback state for trigger sweep mode."""

    mode: str
    raw_value: str

    def to_json(self) -> dict[str, object]:
        return {"mode": self.mode, "raw_value": self.raw_value}


@dataclass(frozen=True)
class TriggerRejectState:
    """Readback state for trigger reject filters."""

    enabled: bool
    raw_value: str

    def to_json(self) -> dict[str, object]:
        return {"enabled": self.enabled, "raw_value": self.raw_value}




@dataclass(frozen=True)
class EdgeTriggerCouplingState:
    """Readback state for Edge Trigger coupling."""

    coupling: str
    raw_value: str

    def to_json(self) -> dict[str, object]:
        return {"coupling": self.coupling, "raw_value": self.raw_value}


@dataclass(frozen=True)
class EdgeTriggerRejectState:
    """Readback state for Edge Trigger reject filter."""

    reject: str
    raw_value: str

    def to_json(self) -> dict[str, object]:
        return {"reject": self.reject, "raw_value": self.raw_value}


@dataclass(frozen=True)
class GlitchTriggerState:
    """Readback state for pulse-width trigger settings."""

    mode: str | None
    source: str
    source_kind: str | None
    channel: int | None
    digital: int | None
    polarity: str | None
    qualifier: str | None
    greater_than_seconds: float | None
    less_than_seconds: float | None
    range_min_seconds: float | None
    range_max_seconds: float | None
    level_volts: float | None
    raw: dict[str, str]

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "source": self.source,
            "source_kind": self.source_kind,
            "channel": self.channel,
            "digital": self.digital,
            "polarity": self.polarity,
            "qualifier": self.qualifier,
            "greater_than_seconds": self.greater_than_seconds,
            "less_than_seconds": self.less_than_seconds,
            "range_min_seconds": self.range_min_seconds,
            "range_max_seconds": self.range_max_seconds,
            "level_volts": self.level_volts,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class RuntTriggerState:
    """Readback state for runt trigger settings."""

    mode: str | None
    source: str
    source_kind: str | None
    channel: int | None
    polarity: str | None
    qualifier: str | None
    time_seconds: float | None
    low_level_volts: float | None
    high_level_volts: float | None
    raw: dict[str, str]

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "source": self.source,
            "source_kind": self.source_kind,
            "channel": self.channel,
            "polarity": self.polarity,
            "qualifier": self.qualifier,
            "time_seconds": self.time_seconds,
            "low_level_volts": self.low_level_volts,
            "high_level_volts": self.high_level_volts,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class TransitionTriggerState:
    """Readback state for transition trigger settings."""

    mode: str | None
    source: str
    source_kind: str | None
    channel: int | None
    slope: str | None
    qualifier: str | None
    time_seconds: float | None
    low_level_volts: float | None
    high_level_volts: float | None
    raw: dict[str, str]

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "source": self.source,
            "source_kind": self.source_kind,
            "channel": self.channel,
            "slope": self.slope,
            "qualifier": self.qualifier,
            "time_seconds": self.time_seconds,
            "low_level_volts": self.low_level_volts,
            "high_level_volts": self.high_level_volts,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class DelayTriggerState:
    """Readback state for Edge Then Edge / Delay trigger settings."""

    mode: str | None
    arm_source: str
    arm_source_kind: str | None
    arm_channel: int | None
    arm_digital: int | None
    arm_slope: str | None
    trigger_source: str
    trigger_source_kind: str | None
    trigger_channel: int | None
    trigger_digital: int | None
    trigger_slope: str | None
    time_seconds: float | None
    count: int | None
    raw: dict[str, str]

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "arm_source": self.arm_source,
            "arm_source_kind": self.arm_source_kind,
            "arm_channel": self.arm_channel,
            "arm_digital": self.arm_digital,
            "arm_slope": self.arm_slope,
            "trigger_source": self.trigger_source,
            "trigger_source_kind": self.trigger_source_kind,
            "trigger_channel": self.trigger_channel,
            "trigger_digital": self.trigger_digital,
            "trigger_slope": self.trigger_slope,
            "time_seconds": self.time_seconds,
            "count": self.count,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class SetupHoldTriggerState:
    """Readback state for setup-hold trigger settings."""

    mode: str | None
    raw_mode: str
    clock_source: str
    clock_source_kind: str | None
    clock_channel: int | None
    clock_digital: int | None
    data_source: str
    data_source_kind: str | None
    data_channel: int | None
    data_digital: int | None
    slope: str | None
    setup_time_seconds: float | None
    hold_time_seconds: float | None
    raw: dict[str, str]

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "raw_mode": self.raw_mode,
            "clock_source": self.clock_source,
            "clock_source_kind": self.clock_source_kind,
            "clock_channel": self.clock_channel,
            "clock_digital": self.clock_digital,
            "data_source": self.data_source,
            "data_source_kind": self.data_source_kind,
            "data_channel": self.data_channel,
            "data_digital": self.data_digital,
            "slope": self.slope,
            "setup_time_seconds": self.setup_time_seconds,
            "hold_time_seconds": self.hold_time_seconds,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class EdgeBurstTriggerState:
    """Readback state for Nth Edge Burst trigger settings."""

    mode: str | None
    source_channel: int | None
    slope: str | None
    count: int | None
    idle_time: float | None
    level_volts: float | None
    raw_mode: str | None
    raw_source: str | None
    raw_slope: str | None
    raw_count: str | None
    raw_idle_time: str | None
    raw_level: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "source_channel": self.source_channel,
            "slope": self.slope,
            "count": self.count,
            "idle_time": self.idle_time,
            "level_volts": self.level_volts,
            "raw_mode": self.raw_mode,
            "raw_source": self.raw_source,
            "raw_slope": self.raw_slope,
            "raw_count": self.raw_count,
            "raw_idle_time": self.raw_idle_time,
            "raw_level": self.raw_level,
        }


@dataclass(frozen=True)
class TvTriggerState:
    """Readback state for basic TV / video trigger settings."""

    mode: str | None
    source_raw: str
    source_channel: int | None
    standard_raw: str
    standard: str | None
    tv_mode_raw: str
    tv_mode: str | None
    line_raw: str
    line: int | None
    polarity_raw: str
    polarity: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "source_raw": self.source_raw,
            "source_channel": self.source_channel,
            "standard_raw": self.standard_raw,
            "standard": self.standard,
            "tv_mode_raw": self.tv_mode_raw,
            "tv_mode": self.tv_mode,
            "line_raw": self.line_raw,
            "line": self.line,
            "polarity_raw": self.polarity_raw,
            "polarity": self.polarity,
        }


@dataclass(frozen=True)
class PatternTriggerState:
    """Readback state for pattern trigger settings."""

    mode: str | None
    format: str | None
    pattern: str | None
    qualifier: str | None
    edge_source_raw: str | None
    edge_raw: str | None
    raw_pattern_response: str | None
    raw: dict[str, str]

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "format": self.format,
            "pattern": self.pattern,
            "qualifier": self.qualifier,
            "edge_source_raw": self.edge_source_raw,
            "edge_raw": self.edge_raw,
            "raw_pattern_response": self.raw_pattern_response,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class OrTriggerState:
    """Readback state for DSO analog OR trigger settings."""

    mode: str | None
    raw_mode: str
    pattern: str | None
    raw_pattern: str
    raw: dict[str, str]

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "raw_mode": self.raw_mode,
            "pattern": self.pattern,
            "raw_pattern": self.raw_pattern,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class TriggerWaitConfig:
    """Controls for explicit triggered capture waiting."""

    timeout_ms: int
    poll_interval_ms: int = 100
    force_on_timeout: bool = False
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep


@dataclass(frozen=True)
class TriggerWaitResult:
    """Structured result from a finite trigger wait."""

    outcome: str
    forced: bool
    timed_out: bool
    poll_count: int
    elapsed_ms: float
    condition_values: tuple[int, ...] = field(default_factory=tuple)
    raw_values: tuple[str, ...] = field(default_factory=tuple)
    capture_allowed: bool = False
    capture_block_reason: str | None = None
    error: str | None = None

    def to_json(self, config: TriggerWaitConfig) -> dict[str, object]:
        return {
            "wait_enabled": True,
            "arm_command": single_command(),
            "poll_source": "operation_condition",
            "poll_command": operation_condition_query(),
            "timeout_ms": config.timeout_ms,
            "poll_interval_ms": config.poll_interval_ms,
            "force_on_timeout": config.force_on_timeout,
            "force_command": force_trigger_command(),
            "outcome": self.outcome,
            "forced": self.forced,
            "timed_out": self.timed_out,
            "poll_count": self.poll_count,
            "elapsed_ms": self.elapsed_ms,
            "condition_values": list(self.condition_values),
            "raw_values": list(self.raw_values),
            "capture_allowed": self.capture_allowed,
            "capture_block_reason": self.capture_block_reason,
            "error": self.error,
        }


class EdgeTriggerController:
    """Controls for analog edge trigger settings."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(self, source_channel: int, level_volts: float, slope: str) -> None:
        """Configure analog edge trigger source, level, and slope."""

        source_channel = validate_analog_channel(source_channel, self.capabilities)
        level_volts = validate_trigger_level(level_volts)
        slope_command = normalize_edge_slope(slope)
        self.scpi.write(trigger_mode_edge_command())
        self.scpi.write(edge_trigger_source_command(source_channel))
        self.scpi.write(edge_trigger_level_command(level_volts))
        self.scpi.write(edge_trigger_slope_command(slope_command))

    def query(self) -> EdgeTriggerState:
        """Query analog edge trigger source, level, and slope."""

        source_channel = parse_edge_trigger_source(self.scpi.query(edge_trigger_source_query()))
        validate_analog_channel(source_channel, self.capabilities)
        level_volts = parse_trigger_float(self.scpi.query(edge_trigger_level_query()), "level")
        slope = parse_edge_slope(self.scpi.query(edge_trigger_slope_query()))
        return EdgeTriggerState(source_channel=source_channel, level_volts=level_volts, slope=slope)


class EdgeTriggerSourceController:
    """Controls for the Edge Trigger source only."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(
        self,
        *,
        source: str,
        source_channel: int | None = None,
    ) -> None:
        self.scpi.write(
            trigger_edge_source_command(
                source,
                source_channel=source_channel,
                capabilities=self.capabilities,
            )
        )

    def query(self) -> EdgeTriggerSourceState:
        return parse_trigger_edge_source(self.scpi.query(trigger_edge_source_query()))


class EdgeTriggerSlopeController:
    """Controls for the Edge Trigger slope only."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def configure(self, *, slope: str) -> None:
        self.scpi.write(edge_trigger_slope_command(_normalize_edge_trigger_slope(slope)))

    def query(self) -> EdgeTriggerSlopeState:
        return parse_trigger_edge_slope(self.scpi.query(edge_trigger_slope_query()))


class EdgeTriggerLevelController:
    """Controls for one named analog Edge Trigger level only."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(self, *, source_channel: int, level_volts: float) -> None:
        source_channel = _validate_edge_trigger_level_channel(
            source_channel, self.capabilities
        )
        level_volts = _validate_edge_trigger_level_value(level_volts)
        self.scpi.write(edge_trigger_level_channel_command(source_channel, level_volts))

    def query(self, *, source_channel: int) -> EdgeTriggerLevelState:
        source_channel = _validate_edge_trigger_level_channel(
            source_channel, self.capabilities
        )
        raw_level = self.scpi.query(edge_trigger_level_channel_query(source_channel)).strip()
        return EdgeTriggerLevelState(
            source_channel=source_channel,
            level_volts=parse_trigger_float(raw_level, "Edge Trigger level"),
            raw_level=raw_level,
        )


class ExternalTriggerRangeController:
    """Controls for the dedicated External trigger input range."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def configure(self, *, range_volts: float) -> None:
        self.scpi.write(external_trigger_range_command(range_volts))

    def query(self) -> ExternalTriggerRangeState:
        return parse_external_trigger_range(
            self.scpi.query(external_trigger_range_query())
        )


class ExternalTriggerProbeController:
    """Controls for the External trigger probe attenuation only."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def configure(self, *, attenuation: float) -> None:
        self.scpi.write(external_trigger_probe_command(attenuation))

    def query(self) -> ExternalTriggerProbeState:
        return parse_external_trigger_probe(self.scpi.query(external_trigger_probe_query()))


class ExternalTriggerUnitsController:
    """Controls for the External trigger input units only."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def configure(self, *, units: str) -> None:
        self.scpi.write(external_trigger_units_command(units))

    def query(self) -> ExternalTriggerUnitsState:
        return parse_external_trigger_units(self.scpi.query(external_trigger_units_query()))


class ExternalTriggerSettingsController:
    """Read-only aggregate External trigger input settings query."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def query(self) -> ExternalTriggerSettingsState:
        return parse_external_trigger_settings(self.scpi.query(external_trigger_settings_query()))


class EdgeTriggerExternalLevelController:
    """Controls for the External-qualified Edge Trigger level only."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def configure(self, *, level_volts: float) -> None:
        self.scpi.write(edge_trigger_external_level_command(level_volts))

    def query(self) -> EdgeTriggerExternalLevelState:
        return parse_edge_trigger_external_level(
            self.scpi.query(edge_trigger_external_level_query())
        )


class TriggerSweepController:
    """Controls for common trigger sweep mode."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def configure(self, mode: str) -> None:
        self.scpi.write(trigger_sweep_command(mode))

    def query(self) -> TriggerSweepState:
        raw = self.scpi.query(trigger_sweep_query())
        return TriggerSweepState(mode=parse_trigger_sweep(raw), raw_value=raw.strip())


class TriggerNoiseRejectController:
    """Controls for common trigger noise reject."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def configure(self, enabled: bool) -> None:
        self.scpi.write(trigger_noise_reject_command(enabled))

    def query(self) -> TriggerRejectState:
        raw = self.scpi.query(trigger_noise_reject_query())
        return TriggerRejectState(
            enabled=parse_trigger_reject_bool(raw),
            raw_value=raw.strip(),
        )


class TriggerHfRejectController:
    """Controls for common trigger high-frequency reject."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def configure(self, enabled: bool) -> None:
        self.scpi.write(trigger_hf_reject_command(enabled))

    def query(self) -> TriggerRejectState:
        raw = self.scpi.query(trigger_hf_reject_query())
        return TriggerRejectState(
            enabled=parse_trigger_reject_bool(raw),
            raw_value=raw.strip(),
        )



class EdgeTriggerCouplingController:
    """Controls for Edge Trigger coupling."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def configure(self, coupling: str) -> None:
        self.scpi.write(trigger_edge_coupling_command(coupling))

    def query(self) -> EdgeTriggerCouplingState:
        raw = self.scpi.query(trigger_edge_coupling_query())
        return EdgeTriggerCouplingState(
            coupling=normalize_trigger_edge_coupling(raw),
            raw_value=raw.strip(),
        )


class EdgeTriggerRejectController:
    """Controls for Edge Trigger reject filter."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def configure(self, reject: str) -> None:
        self.scpi.write(trigger_edge_reject_command(reject))

    def query(self) -> EdgeTriggerRejectState:
        raw = self.scpi.query(trigger_edge_reject_query())
        return EdgeTriggerRejectState(
            reject=normalize_trigger_edge_reject(raw),
            raw_value=raw.strip(),
        )


class GlitchTriggerController:
    """Controls for analog pulse-width trigger settings."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(
        self,
        *,
        channel: int,
        polarity: str,
        qualifier: str,
        time_seconds: float | None = None,
        min_time_seconds: float | None = None,
        max_time_seconds: float | None = None,
        level_volts: float | None = None,
    ) -> None:
        """Configure analog-channel pulse-width trigger settings."""

        commands = glitch_trigger_configure_commands(
            channel=channel,
            polarity=polarity,
            qualifier=qualifier,
            capabilities=self.capabilities,
            time_seconds=time_seconds,
            min_time_seconds=min_time_seconds,
            max_time_seconds=max_time_seconds,
            level_volts=level_volts,
        )
        for command in commands:
            self.scpi.write(command)

    def query(self) -> GlitchTriggerState:
        """Query pulse-width trigger state without changing acquisition state."""

        raw = {
            "mode": self.scpi.query(trigger_mode_query()),
            "source": self.scpi.query(glitch_trigger_source_query()),
            "polarity": self.scpi.query(glitch_trigger_polarity_query()),
            "qualifier": self.scpi.query(glitch_trigger_qualifier_query()),
            "greater_than": self.scpi.query(glitch_trigger_greater_than_query()),
            "less_than": self.scpi.query(glitch_trigger_less_than_query()),
            "range": self.scpi.query(glitch_trigger_range_query()),
            "level": self.scpi.query(glitch_trigger_level_query()),
        }
        source_kind, channel, digital = parse_glitch_source(raw["source"])
        range_min, range_max = parse_glitch_range(raw["range"])
        return GlitchTriggerState(
            mode=parse_trigger_mode(raw["mode"]),
            source=raw["source"].strip(),
            source_kind=source_kind,
            channel=channel,
            digital=digital,
            polarity=parse_glitch_polarity_readback(raw["polarity"]),
            qualifier=parse_glitch_qualifier_readback(raw["qualifier"]),
            greater_than_seconds=parse_optional_trigger_float(
                raw["greater_than"], "glitch greater-than"
            ),
            less_than_seconds=parse_optional_trigger_float(raw["less_than"], "glitch less-than"),
            range_min_seconds=range_min,
            range_max_seconds=range_max,
            level_volts=parse_glitch_level(raw["level"]),
            raw=raw,
        )


class RuntTriggerController:
    """Controls for analog runt trigger settings."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(
        self,
        *,
        channel: int,
        polarity: str,
        qualifier: str,
        low_level_volts: float,
        high_level_volts: float,
        time_seconds: float | None = None,
    ) -> None:
        """Configure analog-channel runt trigger settings."""

        commands = runt_trigger_configure_commands(
            channel=channel,
            polarity=polarity,
            qualifier=qualifier,
            low_level_volts=low_level_volts,
            high_level_volts=high_level_volts,
            capabilities=self.capabilities,
            time_seconds=time_seconds,
        )
        for command in commands:
            self.scpi.write(command)

    def query(self) -> RuntTriggerState:
        """Query runt trigger state without changing acquisition state."""

        raw = {
            "mode": self.scpi.query(trigger_mode_query()),
            "source": self.scpi.query(runt_trigger_source_query()),
            "polarity": self.scpi.query(runt_trigger_polarity_query()),
            "qualifier": self.scpi.query(runt_trigger_qualifier_query()),
            "time": self.scpi.query(runt_trigger_time_query()),
        }
        source_kind, channel = parse_runt_source(raw["source"])
        low_level = None
        high_level = None
        if channel is not None:
            raw["low_level"] = self.scpi.query(runt_trigger_low_level_query(channel))
            raw["high_level"] = self.scpi.query(runt_trigger_high_level_query(channel))
            low_level = parse_trigger_float(raw["low_level"], "runt low level")
            high_level = parse_trigger_float(raw["high_level"], "runt high level")
        return RuntTriggerState(
            mode=parse_trigger_mode(raw["mode"]),
            source=raw["source"].strip(),
            source_kind=source_kind,
            channel=channel,
            polarity=parse_runt_polarity_readback(raw["polarity"]),
            qualifier=parse_runt_qualifier_readback(raw["qualifier"]),
            time_seconds=parse_optional_trigger_float(raw["time"], "runt time"),
            low_level_volts=low_level,
            high_level_volts=high_level,
            raw=raw,
        )


class TransitionTriggerController:
    """Controls for analog transition trigger settings."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(
        self,
        *,
        channel: int,
        slope: str,
        qualifier: str,
        low_level_volts: float,
        high_level_volts: float,
        time_seconds: float,
    ) -> None:
        """Configure analog-channel transition trigger settings."""

        commands = transition_trigger_configure_commands(
            channel=channel,
            slope=slope,
            qualifier=qualifier,
            low_level_volts=low_level_volts,
            high_level_volts=high_level_volts,
            capabilities=self.capabilities,
            time_seconds=time_seconds,
        )
        for command in commands:
            self.scpi.write(command)

    def query(self) -> TransitionTriggerState:
        """Query transition trigger state without changing acquisition state."""

        raw = {
            "mode": self.scpi.query(trigger_mode_query()),
            "source": self.scpi.query(transition_trigger_source_query()),
            "slope": self.scpi.query(transition_trigger_slope_query()),
            "qualifier": self.scpi.query(transition_trigger_qualifier_query()),
            "time": self.scpi.query(transition_trigger_time_query()),
        }
        source_kind, channel = parse_transition_source(raw["source"])
        low_level = None
        high_level = None
        if channel is not None:
            raw["low_level"] = self.scpi.query(trigger_low_level_query(channel))
            raw["high_level"] = self.scpi.query(trigger_high_level_query(channel))
            low_level = parse_trigger_float(raw["low_level"], "transition low level")
            high_level = parse_trigger_float(raw["high_level"], "transition high level")
        return TransitionTriggerState(
            mode=parse_trigger_mode(raw["mode"]),
            source=raw["source"].strip(),
            source_kind=source_kind,
            channel=channel,
            slope=parse_transition_slope_readback(raw["slope"]),
            qualifier=parse_transition_qualifier_readback(raw["qualifier"]),
            time_seconds=parse_optional_trigger_float(raw["time"], "transition time"),
            low_level_volts=low_level,
            high_level_volts=high_level,
            raw=raw,
        )


class DelayTriggerController:
    """Controls for analog Edge Then Edge / Delay trigger settings."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(
        self,
        *,
        arm_channel: int,
        arm_slope: str,
        trigger_channel: int,
        trigger_slope: str,
        time_seconds: float,
        count: int,
    ) -> None:
        """Configure analog-channel delay trigger settings."""

        commands = delay_trigger_configure_commands(
            arm_channel=arm_channel,
            arm_slope=arm_slope,
            trigger_channel=trigger_channel,
            trigger_slope=trigger_slope,
            time_seconds=time_seconds,
            count=count,
            capabilities=self.capabilities,
        )
        for command in commands:
            self.scpi.write(command)

    def query(self) -> DelayTriggerState:
        """Query delay trigger state without changing acquisition state."""

        raw = {
            "mode": self.scpi.query(trigger_mode_query()),
            "arm_source": self.scpi.query(delay_trigger_arm_source_query()),
            "arm_slope": self.scpi.query(delay_trigger_arm_slope_query()),
            "time": self.scpi.query(delay_trigger_time_query()),
            "count": self.scpi.query(delay_trigger_count_query()),
            "trigger_source": self.scpi.query(delay_trigger_trigger_source_query()),
            "trigger_slope": self.scpi.query(delay_trigger_trigger_slope_query()),
        }
        arm_source_kind, arm_channel, arm_digital = parse_delay_source(raw["arm_source"])
        trigger_source_kind, trigger_channel, trigger_digital = parse_delay_source(
            raw["trigger_source"]
        )
        return DelayTriggerState(
            mode=parse_trigger_mode(raw["mode"]),
            arm_source=raw["arm_source"].strip(),
            arm_source_kind=arm_source_kind,
            arm_channel=arm_channel,
            arm_digital=arm_digital,
            arm_slope=parse_delay_slope_readback(raw["arm_slope"]),
            trigger_source=raw["trigger_source"].strip(),
            trigger_source_kind=trigger_source_kind,
            trigger_channel=trigger_channel,
            trigger_digital=trigger_digital,
            trigger_slope=parse_delay_slope_readback(raw["trigger_slope"]),
            time_seconds=parse_optional_trigger_float(raw["time"], "delay time"),
            count=parse_delay_count_readback(raw["count"]),
            raw=raw,
        )


class SetupHoldTriggerController:
    """Controls for DSO analog setup-hold trigger settings."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(
        self,
        *,
        clock_channel: int,
        data_channel: int,
        slope: str,
        setup_time_seconds: float,
        hold_time_seconds: float,
    ) -> SetupHoldTriggerState:
        """Configure DSO analog setup-hold trigger settings."""

        commands = setup_hold_trigger_configure_commands(
            clock_channel=clock_channel,
            data_channel=data_channel,
            slope=slope,
            setup_time_seconds=setup_time_seconds,
            hold_time_seconds=hold_time_seconds,
            capabilities=self.capabilities,
        )
        for command in commands:
            self.scpi.write(command)
        return SetupHoldTriggerState(
            mode="setup-hold",
            raw_mode="SHOLd",
            clock_source=f"CHANnel{clock_channel}",
            clock_source_kind="channel",
            clock_channel=clock_channel,
            clock_digital=None,
            data_source=f"CHANnel{data_channel}",
            data_source_kind="channel",
            data_channel=data_channel,
            data_digital=None,
            slope=slope,
            setup_time_seconds=setup_time_seconds,
            hold_time_seconds=hold_time_seconds,
            raw={
                "mode": "SHOLd",
                "clock_source": f"CHANnel{clock_channel}",
                "data_source": f"CHANnel{data_channel}",
                "slope": normalize_setup_hold_slope(slope),
                "setup_time": _format_scpi_float(setup_time_seconds),
                "hold_time": _format_scpi_float(hold_time_seconds),
            },
        )

    def query(self) -> SetupHoldTriggerState:
        """Query setup-hold trigger state without changing acquisition state."""

        raw = {
            "mode": self.scpi.query(trigger_mode_query()),
            "clock_source": self.scpi.query(setup_hold_trigger_clock_source_query()),
            "data_source": self.scpi.query(setup_hold_trigger_data_source_query()),
            "slope": self.scpi.query(setup_hold_trigger_slope_query()),
            "setup_time": self.scpi.query(setup_hold_trigger_setup_time_query()),
            "hold_time": self.scpi.query(setup_hold_trigger_hold_time_query()),
        }
        clock_kind, clock_channel, clock_digital = parse_setup_hold_source(raw["clock_source"])
        data_kind, data_channel, data_digital = parse_setup_hold_source(raw["data_source"])
        return SetupHoldTriggerState(
            mode=parse_trigger_mode(raw["mode"]) or raw["mode"].strip(),
            raw_mode=raw["mode"],
            clock_source=raw["clock_source"].strip(),
            clock_source_kind=clock_kind,
            clock_channel=clock_channel,
            clock_digital=clock_digital,
            data_source=raw["data_source"].strip(),
            data_source_kind=data_kind,
            data_channel=data_channel,
            data_digital=data_digital,
            slope=parse_setup_hold_slope_readback(raw["slope"]),
            setup_time_seconds=parse_optional_trigger_float(raw["setup_time"], "setup-hold setup time"),
            hold_time_seconds=parse_optional_trigger_float(raw["hold_time"], "setup-hold hold time"),
            raw=raw,
        )


class EdgeBurstTriggerController:
    """Controls for DSO analog Nth Edge Burst trigger settings."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(
        self,
        *,
        source_channel: int,
        slope: str,
        count: int,
        idle_time: float,
        level_volts: float | None = None,
    ) -> EdgeBurstTriggerState:
        """Configure DSO analog Nth Edge Burst trigger settings."""

        commands = edge_burst_trigger_configure_commands(
            source_channel=source_channel,
            slope=slope,
            count=count,
            idle_time=idle_time,
            capabilities=self.capabilities,
            level_volts=level_volts,
        )
        for command in commands:
            self.scpi.write(command)
        normalized_channel = validate_analog_channel(source_channel, self.capabilities)
        normalized_slope = parse_edge_burst_slope_readback(normalize_edge_burst_slope(slope))
        normalized_count = validate_edge_burst_count(count)
        normalized_idle = validate_edge_burst_idle_time(idle_time)
        normalized_level = (
            validate_trigger_level(level_volts) if level_volts is not None else None
        )
        return EdgeBurstTriggerState(
            mode="edge-burst",
            source_channel=normalized_channel,
            slope=normalized_slope,
            count=normalized_count,
            idle_time=normalized_idle,
            level_volts=normalized_level,
            raw_mode="EBURst",
            raw_source=f"CHANnel{normalized_channel}",
            raw_slope=normalize_edge_burst_slope(slope),
            raw_count=str(normalized_count),
            raw_idle_time=_format_scpi_float(normalized_idle),
            raw_level=_format_scpi_float(normalized_level)
            if normalized_level is not None
            else None,
        )

    def query(self) -> EdgeBurstTriggerState:
        """Query Nth Edge Burst trigger state without changing acquisition state."""

        raw_mode = self.scpi.query(trigger_mode_query())
        raw_source = self.scpi.query(edge_burst_source_query())
        raw_slope = self.scpi.query(edge_burst_slope_query())
        raw_count = self.scpi.query(edge_burst_count_query())
        raw_idle = self.scpi.query(edge_burst_idle_query())
        source_kind, source_channel, _digital = parse_edge_burst_source(raw_source)
        raw_level = None
        level_volts = None
        if source_kind == "channel" and source_channel is not None:
            raw_level = self.scpi.query(edge_trigger_level_for_source_query(source_channel))
            level_volts = parse_trigger_float(raw_level, "edge-burst level")
        return EdgeBurstTriggerState(
            mode=parse_trigger_mode(raw_mode),
            source_channel=source_channel if source_kind == "channel" else None,
            slope=parse_edge_burst_slope_readback(raw_slope),
            count=parse_edge_burst_count_readback(raw_count),
            idle_time=parse_optional_trigger_float(raw_idle, "edge-burst idle time"),
            level_volts=level_volts,
            raw_mode=raw_mode,
            raw_source=raw_source,
            raw_slope=raw_slope,
            raw_count=raw_count,
            raw_idle_time=raw_idle,
            raw_level=raw_level,
        )


class TvTriggerController:
    """Controls for DSO analog basic TV / video trigger settings."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(
        self,
        *,
        source_channel: int,
        standard: str,
        mode: str,
        polarity: str,
        line: int | None = None,
    ) -> TvTriggerState:
        """Configure DSO analog basic TV trigger settings."""

        commands = tv_trigger_configure_commands(
            source_channel=source_channel,
            standard=standard,
            mode=mode,
            polarity=polarity,
            capabilities=self.capabilities,
            line=line,
        )
        for command in commands:
            self.scpi.write(command)
        channel = validate_tv_source_channel(source_channel, self.capabilities)
        standard_value = validate_tv_standard(standard)
        mode_value = validate_tv_mode(mode)
        polarity_value = parse_tv_polarity_readback(normalize_tv_polarity(polarity))
        line_value = validate_tv_line(standard_value, mode_value, line)
        return TvTriggerState(
            mode="tv",
            source_raw=f"CHANnel{channel}",
            source_channel=channel,
            standard_raw=normalize_tv_standard(standard),
            standard=standard_value,
            tv_mode_raw=normalize_tv_mode(mode),
            tv_mode=mode_value,
            line_raw=str(line_value) if line_value is not None else "",
            line=line_value,
            polarity_raw=normalize_tv_polarity(polarity),
            polarity=polarity_value,
        )

    def query(self) -> TvTriggerState:
        """Query basic TV trigger state without changing acquisition state."""

        raw_mode = self.scpi.query(trigger_mode_query())
        raw_source = self.scpi.query(tv_trigger_source_query())
        raw_standard = self.scpi.query(tv_trigger_standard_query())
        raw_tv_mode = self.scpi.query(tv_trigger_mode_query())
        raw_line = self.scpi.query(tv_trigger_line_query())
        raw_polarity = self.scpi.query(tv_trigger_polarity_query())
        return TvTriggerState(
            mode=parse_trigger_mode(raw_mode),
            source_raw=raw_source.strip(),
            source_channel=parse_tv_source(raw_source),
            standard_raw=raw_standard.strip(),
            standard=parse_tv_standard_readback(raw_standard),
            tv_mode_raw=raw_tv_mode.strip(),
            tv_mode=parse_tv_mode_readback(raw_tv_mode),
            line_raw=raw_line.strip(),
            line=parse_tv_line_readback(raw_line),
            polarity_raw=raw_polarity.strip(),
            polarity=parse_tv_polarity_readback(raw_polarity),
        )


class PatternTriggerController:
    """Controls for DSO ASCII pattern trigger settings."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(self, pattern: str) -> PatternTriggerState:
        """Configure DSO ASCII entered-pattern trigger settings."""

        commands = pattern_trigger_configure_commands(
            pattern=pattern,
            capabilities=self.capabilities,
        )
        for command in commands:
            self.scpi.write(command)
        normalized = validate_pattern_trigger_pattern(pattern, self.capabilities)
        return PatternTriggerState(
            mode="pattern",
            format="ascii",
            pattern=normalized,
            qualifier="entered",
            edge_source_raw=None,
            edge_raw=None,
            raw_pattern_response=None,
            raw={
                "mode": "PATTern",
                "format": "ASCii",
                "pattern": normalized,
                "qualifier": "ENTered",
            },
        )

    def query(self) -> PatternTriggerState:
        """Query pattern trigger state without changing acquisition state."""

        raw = {
            "mode": self.scpi.query(trigger_mode_query()),
            "format": self.scpi.query(pattern_trigger_format_query()),
            "pattern": self.scpi.query(pattern_trigger_pattern_query()),
            "qualifier": self.scpi.query(pattern_trigger_qualifier_query()),
        }
        pattern, edge_source, edge = parse_pattern_trigger_response(raw["pattern"])
        return PatternTriggerState(
            mode=parse_trigger_mode(raw["mode"]),
            format=parse_pattern_format_readback(raw["format"]),
            pattern=pattern,
            qualifier=parse_pattern_qualifier_readback(raw["qualifier"]),
            edge_source_raw=edge_source,
            edge_raw=edge,
            raw_pattern_response=raw["pattern"],
            raw=raw,
        )


class OrTriggerController:
    """Controls for DSO analog OR trigger settings."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure(self, pattern: str) -> OrTriggerState:
        """Configure DSO analog OR trigger settings."""

        commands = or_trigger_configure_commands(
            pattern=pattern,
            capabilities=self.capabilities,
        )
        for command in commands:
            self.scpi.write(command)
        normalized = validate_or_trigger_pattern(pattern, self.capabilities)
        return OrTriggerState(
            mode="or",
            raw_mode="OR",
            pattern=normalized,
            raw_pattern=normalized,
            raw={"mode": "OR", "pattern": normalized},
        )

    def query(self) -> OrTriggerState:
        """Query OR trigger state without changing acquisition state."""

        raw = {
            "mode": self.scpi.query(trigger_mode_query()),
            "pattern": self.scpi.query(or_trigger_pattern_query()),
        }
        return OrTriggerState(
            mode=parse_trigger_mode(raw["mode"]),
            raw_mode=raw["mode"],
            pattern=parse_or_trigger_pattern_response(raw["pattern"]),
            raw_pattern=raw["pattern"],
            raw=raw,
        )


def validate_trigger_level(level_volts: float) -> float:
    """Validate a trigger level before sending it to the instrument."""

    try:
        value = float(level_volts)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ParameterValidationError("trigger level must be a number.") from exc
    if not math.isfinite(value):
        raise ParameterValidationError("trigger level must be a finite number.")
    return value


def _validate_edge_trigger_level_value(level_volts: float) -> float:
    """Validate an atomic Edge Trigger analog level value."""

    if isinstance(level_volts, bool) or not isinstance(level_volts, (int, float)):
        raise ParameterValidationError("Edge Trigger level must be a real number.")
    return validate_trigger_level(level_volts)


def validate_external_trigger_range(range_volts: float) -> float:
    """Validate an External trigger range without probing attenuation state."""

    if isinstance(range_volts, bool) or not isinstance(range_volts, (int, float)):
        raise ParameterValidationError("External trigger range must be a real number.")
    try:
        value = float(range_volts)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ParameterValidationError(
            "External trigger range must be a real number."
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise ParameterValidationError(
            "External trigger range must be a positive finite number."
        )
    return value


def validate_external_trigger_probe_attenuation(attenuation: float) -> float:
    """Validate External probe attenuation without probing probe type or limits."""

    if isinstance(attenuation, bool) or not isinstance(attenuation, (int, float)):
        raise ParameterValidationError("External trigger probe attenuation must be a real number.")
    try:
        value = float(attenuation)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ParameterValidationError(
            "External trigger probe attenuation must be a real number."
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise ParameterValidationError(
            "External trigger probe attenuation must be a positive finite number."
        )
    return value


def validate_external_trigger_units(units: str) -> str:
    """Validate canonical External trigger input units."""

    if not isinstance(units, str) or units not in _EXTERNAL_TRIGGER_UNITS_COMMANDS:
        raise ParameterValidationError(
            "External trigger units must be one of: volts, amps."
        )
    return units


def _validate_edge_trigger_level_channel(
    source_channel: int, capabilities: ScopeCapabilities
) -> int:
    if isinstance(source_channel, bool):
        raise ParameterValidationError("Edge Trigger source_channel must be an integer.")
    return validate_analog_channel(source_channel, capabilities)


def _normalize_edge_trigger_slope(slope: str) -> str:
    if not isinstance(slope, str):
        raise ParameterValidationError(
            "edge trigger slope must be one of: positive, negative, either, alternate."
        )
    if slope not in {"positive", "negative", "either", "alternate"}:
        raise ParameterValidationError(
            "edge trigger slope must be one of: positive, negative, either, alternate."
        )
    return _SLOPE_COMMANDS[slope]


def normalize_edge_slope(slope: str) -> str:
    """Normalize a user-facing edge slope into a SCPI argument."""

    normalized = slope.strip().lower()
    try:
        return _SLOPE_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "edge trigger slope must be one of: positive, negative, either, alternate."
        ) from exc


def normalize_glitch_polarity(polarity: str) -> str:
    """Normalize a user-facing glitch polarity into a SCPI argument."""

    normalized = polarity.strip().lower()
    try:
        return _GLITCH_POLARITY_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "pulse-width trigger polarity must be one of: positive, negative."
        ) from exc


def normalize_glitch_qualifier(qualifier: str) -> str:
    """Normalize a user-facing glitch qualifier into a SCPI argument."""

    normalized = qualifier.strip().lower()
    try:
        return _GLITCH_QUALIFIER_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "pulse-width trigger qualifier must be one of: greater-than, less-than, range."
        ) from exc


def normalize_runt_polarity(polarity: str) -> str:
    """Normalize a user-facing runt polarity into a SCPI argument."""

    normalized = polarity.strip().lower()
    try:
        return _RUNT_POLARITY_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "runt trigger polarity must be one of: positive, negative, either."
        ) from exc


def normalize_runt_qualifier(qualifier: str) -> str:
    """Normalize a user-facing runt qualifier into a SCPI argument."""

    normalized = qualifier.strip().lower()
    try:
        return _RUNT_QUALIFIER_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "runt trigger qualifier must be one of: greater-than, less-than, none."
        ) from exc


def normalize_transition_slope(slope: str) -> str:
    """Normalize a user-facing transition slope into a SCPI argument."""

    normalized = slope.strip().lower()
    try:
        return _TRANSITION_SLOPE_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "transition trigger slope must be one of: positive, negative."
        ) from exc


def normalize_transition_qualifier(qualifier: str) -> str:
    """Normalize a user-facing transition qualifier into a SCPI argument."""

    normalized = qualifier.strip().lower()
    try:
        return _TRANSITION_QUALIFIER_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "transition trigger qualifier must be one of: greater-than, less-than."
        ) from exc


def normalize_delay_slope(slope: str) -> str:
    """Normalize a public delay slope value into a SCPI argument."""

    normalized = slope.strip().lower()
    try:
        return _DELAY_SLOPE_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "delay trigger slope must be one of: positive, negative."
        ) from exc


def normalize_setup_hold_slope(slope: str) -> str:
    """Normalize a public setup-hold slope value into a SCPI argument."""

    normalized = slope.strip().lower()
    try:
        return _SETUP_HOLD_SLOPE_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "setup-hold trigger slope must be one of: positive, negative."
        ) from exc


def normalize_edge_burst_slope(slope: str) -> str:
    """Normalize a public edge-burst slope value into a SCPI argument."""

    normalized = slope.strip().lower()
    try:
        return _EDGE_BURST_SLOPE_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "edge-burst trigger slope must be one of: positive, negative."
        ) from exc


def normalize_tv_standard(standard: str) -> str:
    """Normalize a public TV standard value into a SCPI argument."""

    normalized = standard.strip().lower()
    if normalized in _TV_EXTENDED_STANDARDS:
        raise ParameterValidationError(
            "TV trigger standard is out of v1 scope; use one of: ntsc, pal, palm, secam."
        )
    try:
        return _TV_STANDARD_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "TV trigger standard must be one of: ntsc, pal, palm, secam."
        ) from exc


def normalize_tv_mode(mode: str) -> str:
    """Normalize a public TV mode value into a SCPI argument."""

    normalized = mode.strip().lower()
    if normalized == "line":
        raise ParameterValidationError("TV trigger mode line is out of v1 scope.")
    try:
        return _TV_MODE_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "TV trigger mode must be one of: field1, field2, all-fields, all-lines, "
            "line-field1, line-field2, line-alternate."
        ) from exc


def normalize_tv_polarity(polarity: str) -> str:
    """Normalize a public TV polarity value into a SCPI argument."""

    normalized = polarity.strip().lower()
    try:
        return _TV_POLARITY_COMMANDS[normalized]
    except KeyError as exc:
        raise ParameterValidationError(
            "TV trigger polarity must be one of: positive, negative."
        ) from exc


def trigger_mode_edge_command() -> str:
    """Build the SCPI command that selects edge trigger mode."""

    return ":TRIGger:MODE EDGE"


def trigger_mode_glitch_command() -> str:
    """Build the SCPI command that selects glitch trigger mode."""

    return ":TRIGger:MODE GLITch"


def trigger_mode_runt_command() -> str:
    """Build the SCPI command that selects runt trigger mode."""

    return ":TRIGger:MODE RUNT"


def trigger_mode_transition_command() -> str:
    """Build the SCPI command that selects transition trigger mode."""

    return ":TRIGger:MODE TRANsition"


def trigger_mode_delay_command() -> str:
    """Build the SCPI command that selects delay trigger mode."""

    return ":TRIGger:MODE DELay"


def trigger_mode_setup_hold_command() -> str:
    """Build the SCPI command that selects setup-hold trigger mode."""

    return ":TRIGger:MODE SHOLd"


def trigger_mode_edge_burst_command() -> str:
    """Build the SCPI command that selects Nth Edge Burst trigger mode."""

    return ":TRIGger:MODE EBURst"


def trigger_mode_tv_command() -> str:
    """Build the SCPI command that selects TV trigger mode."""

    return ":TRIGger:MODE TV"


def trigger_mode_pattern_command() -> str:
    """Build the SCPI command that selects pattern trigger mode."""

    return ":TRIGger:MODE PATTern"


def trigger_mode_or_command() -> str:
    """Build the SCPI command that selects OR trigger mode."""

    return ":TRIGger:MODE OR"


def trigger_mode_serial_command(bus: int) -> str:
    """Build the SCPI command that selects a serial bus trigger mode."""

    return f":TRIGger:MODE SBUS{bus}"


def trigger_mode_query() -> str:
    """Build the SCPI query for trigger mode."""

    return ":TRIGger:MODE?"


def trigger_sweep_command(mode: str) -> str:
    """Build the SCPI command for trigger sweep mode."""

    return f":TRIGger:SWEep {normalize_trigger_sweep(mode)}"


def trigger_sweep_query() -> str:
    """Build the SCPI query for trigger sweep mode."""

    return ":TRIGger:SWEep?"


def trigger_noise_reject_command(enabled: bool) -> str:
    """Build the SCPI command for trigger noise reject."""

    return f":TRIGger:NREJect {_trigger_bool_token(enabled)}"


def trigger_noise_reject_query() -> str:
    """Build the SCPI query for trigger noise reject."""

    return ":TRIGger:NREJect?"


def trigger_hf_reject_command(enabled: bool) -> str:
    """Build the SCPI command for trigger high-frequency reject."""

    return f":TRIGger:HFReject {_trigger_bool_token(enabled)}"


def trigger_hf_reject_query() -> str:
    """Build the SCPI query for trigger high-frequency reject."""

    return ":TRIGger:HFReject?"



def trigger_edge_coupling_command(coupling: str) -> str:
    """Build the SCPI command for Edge Trigger coupling."""

    _validate_edge_coupling(coupling)
    return f":TRIGger:EDGE:COUPling {_edge_coupling_token(coupling)}"


def trigger_edge_coupling_query() -> str:
    """Build the SCPI query for Edge Trigger coupling."""

    return ":TRIGger:EDGE:COUPling?"


def trigger_edge_reject_command(reject: str) -> str:
    """Build the SCPI command for Edge Trigger reject filter."""

    _validate_edge_reject(reject)
    return f":TRIGger:EDGE:REJect {_edge_reject_token(reject)}"


def trigger_edge_reject_query() -> str:
    """Build the SCPI query for Edge Trigger reject filter."""

    return ":TRIGger:EDGE:REJect?"


def normalize_trigger_edge_coupling(raw: str) -> str:
    """Normalize an Edge Trigger coupling readback to canonical form."""

    text = raw.strip().upper()
    if text in _EDGE_COUPLING_READBACKS:
        return _EDGE_COUPLING_READBACKS[text]
    raise TriggerResponseError(f"Could not parse Edge Trigger coupling response: {raw!r}")


def normalize_trigger_edge_reject(raw: str) -> str:
    """Normalize an Edge Trigger reject filter readback to canonical form."""

    text = raw.strip().upper()
    if text in _EDGE_REJECT_READBACKS:
        return _EDGE_REJECT_READBACKS[text]
    raise TriggerResponseError(f"Could not parse Edge Trigger reject response: {raw!r}")


def single_command() -> str:
    """Return the SCPI command that arms one single acquisition."""

    return ":SINGle"


def operation_condition_query() -> str:
    """Return the operation condition status query used by trigger waits."""

    return ":OPERegister:CONDition?"


def edge_trigger_source_command(channel: int) -> str:
    """Build the SCPI command for analog edge trigger source."""

    return f":TRIGger:EDGE:SOURce CHANnel{channel}"


def edge_trigger_source_query() -> str:
    """Build the SCPI query for edge trigger source."""

    return ":TRIGger:EDGE:SOURce?"


def trigger_edge_source_channel_command(channel: int) -> str:
    """Build the SCPI command for an analog Edge Trigger source."""

    return f":TRIGger:EDGE:SOURce CHANnel{channel}"


def trigger_edge_source_external_command() -> str:
    """Build the SCPI command for the external Edge Trigger source."""

    return ":TRIGger:EDGE:SOURce EXTernal"


def trigger_edge_source_line_command() -> str:
    """Build the SCPI command for the line Edge Trigger source."""

    return ":TRIGger:EDGE:SOURce LINE"


def trigger_edge_source_query() -> str:
    """Build the SCPI query for the Edge Trigger source."""

    return ":TRIGger:EDGE:SOURce?"


def trigger_edge_source_command(
    source: str,
    *,
    source_channel: int | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> str:
    """Build one validated source-only Edge Trigger command."""

    if source == "analog-channel":
        if source_channel is None:
            raise ParameterValidationError(
                "Edge Trigger analog-channel source requires source_channel."
            )
        if isinstance(source_channel, bool) or not isinstance(source_channel, int):
            raise ParameterValidationError("Edge Trigger source_channel must be an integer.")
        if capabilities is not None:
            source_channel = validate_analog_channel(source_channel, capabilities)
        elif source_channel < 1:
            raise ParameterValidationError("Edge Trigger source_channel must be positive.")
        return trigger_edge_source_channel_command(source_channel)
    if source in _EDGE_TRIGGER_SOURCE_COMMANDS:
        if source_channel is not None:
            raise ParameterValidationError(
                f"Edge Trigger {source} source does not accept source_channel."
            )
        return {
            "external": trigger_edge_source_external_command,
            "line": trigger_edge_source_line_command,
        }[source]()
    raise ParameterValidationError(
        "Invalid Edge Trigger source. Valid values are: analog-channel, external, line."
    )


def edge_trigger_level_command(level_volts: float) -> str:
    """Build the SCPI command for edge trigger level."""

    return f":TRIGger:EDGE:LEVel {_format_scpi_float(level_volts)}"


def edge_trigger_level_query() -> str:
    """Build the SCPI query for edge trigger level."""

    return ":TRIGger:EDGE:LEVel?"


def edge_trigger_level_for_source_command(level_volts: float, channel: int) -> str:
    """Build the SCPI command for an analog-source edge trigger level."""

    return f":TRIGger:EDGE:LEVel {_format_scpi_float(level_volts)}, CHANnel{channel}"


def edge_trigger_level_for_source_query(channel: int) -> str:
    """Build the SCPI query for an analog-source edge trigger level."""

    return f":TRIGger:EDGE:LEVel? CHANnel{channel}"


def edge_trigger_level_channel_command(source_channel: int, level_volts: float) -> str:
    """Build a source-qualified analog Edge Trigger level command."""

    level = _format_scpi_float(_validate_edge_trigger_level_value(level_volts))
    return f":TRIGger:EDGE:LEVel {level},CHANnel{source_channel}"


def edge_trigger_level_channel_query(source_channel: int) -> str:
    """Build a source-qualified analog Edge Trigger level query."""

    return f":TRIGger:EDGE:LEVel? CHANnel{source_channel}"


def external_trigger_range_command(range_volts: float) -> str:
    """Build the SCPI command for the dedicated External trigger input range."""

    value = validate_external_trigger_range(range_volts)
    return f":EXTernal:RANGe {_format_scpi_float(value)}"


def external_trigger_range_query() -> str:
    """Build the SCPI query for the dedicated External trigger input range."""

    return ":EXTernal:RANGe?"


def external_trigger_probe_command(attenuation: float) -> str:
    """Build the SCPI command for External trigger probe attenuation."""

    value = validate_external_trigger_probe_attenuation(attenuation)
    return f":EXTernal:PROBe {_format_scpi_float(value)}"


def external_trigger_probe_query() -> str:
    """Build the SCPI query for External trigger probe attenuation."""

    return ":EXTernal:PROBe?"


def external_trigger_units_command(units: str) -> str:
    """Build the SCPI command for canonical External trigger input units."""

    return f":EXTernal:UNITs {_EXTERNAL_TRIGGER_UNITS_COMMANDS[validate_external_trigger_units(units)]}"


def external_trigger_units_query() -> str:
    """Build the SCPI query for External trigger input units."""

    return ":EXTernal:UNITs?"


def external_trigger_settings_query() -> str:
    """Build the aggregate External trigger input settings query."""

    return ":EXTernal?"


def edge_trigger_external_level_command(level_volts: float) -> str:
    """Build a source-qualified External Edge Trigger level command."""

    level = _format_scpi_float(_validate_edge_trigger_level_value(level_volts))
    return f":TRIGger:EDGE:LEVel {level},EXTernal"


def edge_trigger_external_level_query() -> str:
    """Build a source-qualified External Edge Trigger level query."""

    return ":TRIGger:EDGE:LEVel? EXTernal"


def edge_trigger_slope_command(slope_command: str) -> str:
    """Build the SCPI command for edge trigger slope."""

    return f":TRIGger:EDGE:SLOPe {slope_command}"


def edge_trigger_slope_query() -> str:
    """Build the SCPI query for edge trigger slope."""

    return ":TRIGger:EDGE:SLOPe?"


def glitch_trigger_source_command(channel: int) -> str:
    """Build the SCPI command for analog GLITch source."""

    return f":TRIGger:GLITch:SOURce CHANnel{channel}"


def glitch_trigger_source_query() -> str:
    """Build the SCPI query for GLITch source."""

    return ":TRIGger:GLITch:SOURce?"


def glitch_trigger_level_command(level_volts: float, channel: int) -> str:
    """Build the SCPI command for analog glitch trigger level."""

    return f":TRIGger:GLITch:LEVel {_format_scpi_float(level_volts)},CHANnel{channel}"


def glitch_trigger_level_query() -> str:
    """Build the SCPI query for glitch trigger level."""

    return ":TRIGger:GLITch:LEVel?"


def glitch_trigger_polarity_command(polarity_command: str) -> str:
    """Build the SCPI command for glitch trigger polarity."""

    return f":TRIGger:GLITch:POLarity {polarity_command}"


def glitch_trigger_polarity_query() -> str:
    """Build the SCPI query for glitch trigger polarity."""

    return ":TRIGger:GLITch:POLarity?"


def glitch_trigger_qualifier_command(qualifier_command: str) -> str:
    """Build the SCPI command for glitch trigger qualifier."""

    return f":TRIGger:GLITch:QUALifier {qualifier_command}"


def glitch_trigger_qualifier_query() -> str:
    """Build the SCPI query for glitch trigger qualifier."""

    return ":TRIGger:GLITch:QUALifier?"


def glitch_trigger_greater_than_command(time_seconds: float) -> str:
    """Build the SCPI command for glitch greater-than timing."""

    return f":TRIGger:GLITch:GREaterthan {_format_scpi_float(time_seconds)}"


def glitch_trigger_greater_than_query() -> str:
    """Build the SCPI query for glitch greater-than timing."""

    return ":TRIGger:GLITch:GREaterthan?"


def glitch_trigger_less_than_command(time_seconds: float) -> str:
    """Build the SCPI command for glitch less-than timing."""

    return f":TRIGger:GLITch:LESSthan {_format_scpi_float(time_seconds)}"


def glitch_trigger_less_than_query() -> str:
    """Build the SCPI query for glitch less-than timing."""

    return ":TRIGger:GLITch:LESSthan?"


def glitch_trigger_range_command(max_time_seconds: float, min_time_seconds: float) -> str:
    """Build the SCPI command for glitch range timing."""

    return (
        ":TRIGger:GLITch:RANGe "
        f"{_format_scpi_float(max_time_seconds)},{_format_scpi_float(min_time_seconds)}"
    )


def glitch_trigger_range_query() -> str:
    """Build the SCPI query for glitch range timing."""

    return ":TRIGger:GLITch:RANGe?"


def glitch_trigger_query_commands() -> list[str]:
    """Return the glitch trigger query SCPI sequence."""

    return [
        trigger_mode_query(),
        glitch_trigger_source_query(),
        glitch_trigger_polarity_query(),
        glitch_trigger_qualifier_query(),
        glitch_trigger_greater_than_query(),
        glitch_trigger_less_than_query(),
        glitch_trigger_range_query(),
        glitch_trigger_level_query(),
    ]


def glitch_trigger_configure_commands(
    *,
    channel: int,
    polarity: str,
    qualifier: str,
    capabilities: ScopeCapabilities,
    time_seconds: float | None = None,
    min_time_seconds: float | None = None,
    max_time_seconds: float | None = None,
    level_volts: float | None = None,
) -> list[str]:
    """Return the analog glitch trigger configure SCPI sequence."""

    channel = validate_analog_channel(channel, capabilities)
    polarity_command = normalize_glitch_polarity(polarity)
    qualifier_command = normalize_glitch_qualifier(qualifier)
    level = validate_trigger_level(level_volts) if level_volts is not None else None

    commands = [
        trigger_mode_glitch_command(),
        glitch_trigger_source_command(channel),
    ]
    if level is not None:
        commands.append(glitch_trigger_level_command(level, channel))
    commands.append(glitch_trigger_polarity_command(polarity_command))

    if qualifier_command == "GREaterthan":
        if time_seconds is None:
            raise ParameterValidationError(
                "pulse-width trigger greater-than requires time_seconds."
            )
        if min_time_seconds is not None or max_time_seconds is not None:
            raise ParameterValidationError(
                "pulse-width trigger greater-than does not accept range timing."
            )
        commands.append(glitch_trigger_greater_than_command(validate_trigger_time(time_seconds)))
    elif qualifier_command == "LESSthan":
        if time_seconds is None:
            raise ParameterValidationError("pulse-width trigger less-than requires time_seconds.")
        if min_time_seconds is not None or max_time_seconds is not None:
            raise ParameterValidationError("pulse-width trigger less-than does not accept range timing.")
        commands.append(glitch_trigger_less_than_command(validate_trigger_time(time_seconds)))
    else:
        if time_seconds is not None:
            raise ParameterValidationError("pulse-width trigger range does not accept time_seconds.")
        if min_time_seconds is None or max_time_seconds is None:
            raise ParameterValidationError(
                "pulse-width trigger range requires min_time_seconds and max_time_seconds."
            )
        min_time = validate_trigger_time(min_time_seconds)
        max_time = validate_trigger_time(max_time_seconds)
        if min_time >= max_time:
            raise ParameterValidationError(
                "pulse-width trigger min_time_seconds must be less than max_time_seconds."
            )
        commands.append(glitch_trigger_range_command(max_time, min_time))

    commands.append(glitch_trigger_qualifier_command(qualifier_command))
    return commands


def runt_trigger_source_command(channel: int) -> str:
    """Build the SCPI command for analog RUNT source."""

    return f":TRIGger:RUNT:SOURce CHANnel{channel}"


def runt_trigger_source_query() -> str:
    """Build the SCPI query for RUNT source."""

    return ":TRIGger:RUNT:SOURce?"


def trigger_low_level_command(level_volts: float, channel: int) -> str:
    """Build the SCPI command for analog trigger low threshold."""

    return f":TRIGger:LEVel:LOW {_format_scpi_float(level_volts)},CHANnel{channel}"


def trigger_low_level_query(channel: int) -> str:
    """Build the SCPI query for analog trigger low threshold."""

    return f":TRIGger:LEVel:LOW? CHANnel{channel}"


def trigger_high_level_command(level_volts: float, channel: int) -> str:
    """Build the SCPI command for analog trigger high threshold."""

    return f":TRIGger:LEVel:HIGH {_format_scpi_float(level_volts)},CHANnel{channel}"


def trigger_high_level_query(channel: int) -> str:
    """Build the SCPI query for analog trigger high threshold."""

    return f":TRIGger:LEVel:HIGH? CHANnel{channel}"


def runt_trigger_low_level_command(level_volts: float, channel: int) -> str:
    """Build the SCPI command for analog runt low level."""

    return trigger_low_level_command(level_volts, channel)


def runt_trigger_low_level_query(channel: int) -> str:
    """Build the SCPI query for analog runt low level."""

    return trigger_low_level_query(channel)


def runt_trigger_high_level_command(level_volts: float, channel: int) -> str:
    """Build the SCPI command for analog runt high level."""

    return trigger_high_level_command(level_volts, channel)


def runt_trigger_high_level_query(channel: int) -> str:
    """Build the SCPI query for analog runt high level."""

    return trigger_high_level_query(channel)


def runt_trigger_polarity_command(polarity_command: str) -> str:
    """Build the SCPI command for runt trigger polarity."""

    return f":TRIGger:RUNT:POLarity {polarity_command}"


def runt_trigger_polarity_query() -> str:
    """Build the SCPI query for runt trigger polarity."""

    return ":TRIGger:RUNT:POLarity?"


def runt_trigger_time_command(time_seconds: float) -> str:
    """Build the SCPI command for runt timing."""

    return f":TRIGger:RUNT:TIME {_format_scpi_float(time_seconds)}"


def runt_trigger_time_query() -> str:
    """Build the SCPI query for runt timing."""

    return ":TRIGger:RUNT:TIME?"


def runt_trigger_qualifier_command(qualifier_command: str) -> str:
    """Build the SCPI command for runt trigger qualifier."""

    return f":TRIGger:RUNT:QUALifier {qualifier_command}"


def runt_trigger_qualifier_query() -> str:
    """Build the SCPI query for runt trigger qualifier."""

    return ":TRIGger:RUNT:QUALifier?"


def runt_trigger_query_commands() -> list[str]:
    """Return the unconditional runt trigger query SCPI sequence."""

    return [
        trigger_mode_query(),
        runt_trigger_source_query(),
        runt_trigger_polarity_query(),
        runt_trigger_qualifier_query(),
        runt_trigger_time_query(),
    ]


def runt_trigger_configure_commands(
    *,
    channel: int,
    polarity: str,
    qualifier: str,
    low_level_volts: float,
    high_level_volts: float,
    capabilities: ScopeCapabilities,
    time_seconds: float | None = None,
) -> list[str]:
    """Return the analog runt trigger configure SCPI sequence."""

    channel = validate_analog_channel(channel, capabilities)
    polarity_command = normalize_runt_polarity(polarity)
    qualifier_command = normalize_runt_qualifier(qualifier)
    low_level = validate_trigger_level(low_level_volts)
    high_level = validate_trigger_level(high_level_volts)
    if low_level >= high_level:
        raise ParameterValidationError(
            "runt trigger low_level_volts must be less than high_level_volts."
        )

    commands = [
        trigger_mode_runt_command(),
        runt_trigger_source_command(channel),
        runt_trigger_low_level_command(low_level, channel),
        runt_trigger_high_level_command(high_level, channel),
        runt_trigger_polarity_command(polarity_command),
    ]

    if qualifier_command in {"GREaterthan", "LESSthan"}:
        if time_seconds is None:
            raise ParameterValidationError(
                "runt trigger greater-than and less-than require time_seconds."
            )
        commands.append(runt_trigger_time_command(validate_trigger_time(time_seconds)))
    elif time_seconds is not None:
        raise ParameterValidationError("runt trigger qualifier none rejects time_seconds.")

    commands.append(runt_trigger_qualifier_command(qualifier_command))
    return commands


def transition_trigger_source_command(channel: int) -> str:
    """Build the SCPI command for analog TRANsition source."""

    return f":TRIGger:TRANsition:SOURce CHANnel{channel}"


def transition_trigger_source_query() -> str:
    """Build the SCPI query for TRANsition source."""

    return ":TRIGger:TRANsition:SOURce?"


def transition_trigger_slope_command(slope_command: str) -> str:
    """Build the SCPI command for transition trigger slope."""

    return f":TRIGger:TRANsition:SLOPe {slope_command}"


def transition_trigger_slope_query() -> str:
    """Build the SCPI query for transition trigger slope."""

    return ":TRIGger:TRANsition:SLOPe?"


def transition_trigger_time_command(time_seconds: float) -> str:
    """Build the SCPI command for transition timing."""

    return f":TRIGger:TRANsition:TIME {_format_scpi_float(time_seconds)}"


def transition_trigger_time_query() -> str:
    """Build the SCPI query for transition timing."""

    return ":TRIGger:TRANsition:TIME?"


def transition_trigger_qualifier_command(qualifier_command: str) -> str:
    """Build the SCPI command for transition trigger qualifier."""

    return f":TRIGger:TRANsition:QUALifier {qualifier_command}"


def transition_trigger_qualifier_query() -> str:
    """Build the SCPI query for transition trigger qualifier."""

    return ":TRIGger:TRANsition:QUALifier?"


def transition_trigger_query_commands() -> list[str]:
    """Return the unconditional transition trigger query SCPI sequence."""

    return [
        trigger_mode_query(),
        transition_trigger_source_query(),
        transition_trigger_slope_query(),
        transition_trigger_qualifier_query(),
        transition_trigger_time_query(),
    ]


def transition_trigger_configure_commands(
    *,
    channel: int,
    slope: str,
    qualifier: str,
    low_level_volts: float,
    high_level_volts: float,
    capabilities: ScopeCapabilities,
    time_seconds: float,
) -> list[str]:
    """Return the analog transition trigger configure SCPI sequence."""

    channel = validate_analog_channel(channel, capabilities)
    slope_command = normalize_transition_slope(slope)
    qualifier_command = normalize_transition_qualifier(qualifier)
    low_level = validate_trigger_level(low_level_volts)
    high_level = validate_trigger_level(high_level_volts)
    trigger_time = validate_trigger_time(time_seconds)
    if low_level >= high_level:
        raise ParameterValidationError(
            "transition trigger low_level_volts must be less than high_level_volts."
        )

    return [
        trigger_mode_transition_command(),
        transition_trigger_source_command(channel),
        trigger_low_level_command(low_level, channel),
        trigger_high_level_command(high_level, channel),
        transition_trigger_slope_command(slope_command),
        transition_trigger_time_command(trigger_time),
        transition_trigger_qualifier_command(qualifier_command),
    ]


def delay_trigger_arm_source_command(channel: int) -> str:
    """Build the SCPI command for delay trigger arm source."""

    return f":TRIGger:DELay:ARM:SOURce CHANnel{channel}"


def delay_trigger_arm_source_query() -> str:
    """Build the SCPI query for delay trigger arm source."""

    return ":TRIGger:DELay:ARM:SOURce?"


def delay_trigger_arm_slope_command(slope_command: str) -> str:
    """Build the SCPI command for delay trigger arm slope."""

    return f":TRIGger:DELay:ARM:SLOPe {slope_command}"


def delay_trigger_arm_slope_query() -> str:
    """Build the SCPI query for delay trigger arm slope."""

    return ":TRIGger:DELay:ARM:SLOPe?"


def delay_trigger_time_command(time_seconds: float) -> str:
    """Build the SCPI command for delay trigger time."""

    return f":TRIGger:DELay:TDELay:TIME {_format_scpi_float(time_seconds)}"


def delay_trigger_time_query() -> str:
    """Build the SCPI query for delay trigger time."""

    return ":TRIGger:DELay:TDELay:TIME?"


def delay_trigger_count_command(count: int) -> str:
    """Build the SCPI command for delay trigger count."""

    return f":TRIGger:DELay:TRIGger:COUNt {count}"


def delay_trigger_count_query() -> str:
    """Build the SCPI query for delay trigger count."""

    return ":TRIGger:DELay:TRIGger:COUNt?"


def delay_trigger_trigger_source_command(channel: int) -> str:
    """Build the SCPI command for delay trigger source."""

    return f":TRIGger:DELay:TRIGger:SOURce CHANnel{channel}"


def delay_trigger_trigger_source_query() -> str:
    """Build the SCPI query for delay trigger source."""

    return ":TRIGger:DELay:TRIGger:SOURce?"


def delay_trigger_trigger_slope_command(slope_command: str) -> str:
    """Build the SCPI command for delay trigger slope."""

    return f":TRIGger:DELay:TRIGger:SLOPe {slope_command}"


def delay_trigger_trigger_slope_query() -> str:
    """Build the SCPI query for delay trigger slope."""

    return ":TRIGger:DELay:TRIGger:SLOPe?"


def delay_trigger_query_commands() -> list[str]:
    """Return the delay trigger query SCPI sequence."""

    return [
        trigger_mode_query(),
        delay_trigger_arm_source_query(),
        delay_trigger_arm_slope_query(),
        delay_trigger_time_query(),
        delay_trigger_count_query(),
        delay_trigger_trigger_source_query(),
        delay_trigger_trigger_slope_query(),
    ]


def delay_trigger_configure_commands(
    *,
    arm_channel: int,
    arm_slope: str,
    trigger_channel: int,
    trigger_slope: str,
    time_seconds: float,
    count: int,
    capabilities: ScopeCapabilities,
) -> list[str]:
    """Return the analog delay trigger configure SCPI sequence."""

    arm_channel = validate_analog_channel(arm_channel, capabilities)
    trigger_channel = validate_analog_channel(trigger_channel, capabilities)
    arm_slope_command = normalize_delay_slope(arm_slope)
    trigger_slope_command = normalize_delay_slope(trigger_slope)
    delay_time = validate_delay_trigger_time(time_seconds)
    delay_count = validate_delay_trigger_count(count)

    return [
        trigger_mode_delay_command(),
        delay_trigger_arm_source_command(arm_channel),
        delay_trigger_arm_slope_command(arm_slope_command),
        delay_trigger_time_command(delay_time),
        delay_trigger_count_command(delay_count),
        delay_trigger_trigger_source_command(trigger_channel),
        delay_trigger_trigger_slope_command(trigger_slope_command),
    ]


def validate_delay_trigger_time(seconds: float) -> float:
    """Validate the delay trigger time range from the manual."""

    try:
        value = float(seconds)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError(
            "delay trigger time must be a number of seconds."
        ) from exc
    if not math.isfinite(value):
        raise ParameterValidationError(
            "delay trigger time must be a finite number of seconds."
        )
    if value < 4e-9 or value > 10.0:
        raise ParameterValidationError(
            "delay trigger time_seconds must be between 4e-9 and 10.0 seconds."
        )
    return value


def validate_delay_trigger_count(count: int) -> int:
    """Validate the delay trigger Nth edge count."""

    if isinstance(count, bool) or not isinstance(count, int):
        raise ParameterValidationError("delay trigger count must be an integer.")
    if count < 1:
        raise ParameterValidationError("delay trigger count must be at least 1.")
    return count


def setup_hold_trigger_clock_source_command(channel: int) -> str:
    """Build the SCPI command for setup-hold clock source."""

    return f":TRIGger:SHOLd:SOURce:CLOCk CHANnel{channel}"


def setup_hold_trigger_clock_source_query() -> str:
    """Build the SCPI query for setup-hold clock source."""

    return ":TRIGger:SHOLd:SOURce:CLOCk?"


def setup_hold_trigger_data_source_command(channel: int) -> str:
    """Build the SCPI command for setup-hold data source."""

    return f":TRIGger:SHOLd:SOURce:DATA CHANnel{channel}"


def setup_hold_trigger_data_source_query() -> str:
    """Build the SCPI query for setup-hold data source."""

    return ":TRIGger:SHOLd:SOURce:DATA?"


def setup_hold_trigger_slope_command(slope_command: str) -> str:
    """Build the SCPI command for setup-hold clock slope."""

    return f":TRIGger:SHOLd:SLOPe {slope_command}"


def setup_hold_trigger_slope_query() -> str:
    """Build the SCPI query for setup-hold clock slope."""

    return ":TRIGger:SHOLd:SLOPe?"


def setup_hold_trigger_setup_time_command(time_seconds: float) -> str:
    """Build the SCPI command for setup time."""

    return f":TRIGger:SHOLd:TIME:SETup {_format_scpi_float(time_seconds)}"


def setup_hold_trigger_setup_time_query() -> str:
    """Build the SCPI query for setup time."""

    return ":TRIGger:SHOLd:TIME:SETup?"


def setup_hold_trigger_hold_time_command(time_seconds: float) -> str:
    """Build the SCPI command for hold time."""

    return f":TRIGger:SHOLd:TIME:HOLD {_format_scpi_float(time_seconds)}"


def setup_hold_trigger_hold_time_query() -> str:
    """Build the SCPI query for hold time."""

    return ":TRIGger:SHOLd:TIME:HOLD?"


def setup_hold_trigger_query_commands() -> list[str]:
    """Return the setup-hold trigger query SCPI sequence."""

    return [
        trigger_mode_query(),
        setup_hold_trigger_clock_source_query(),
        setup_hold_trigger_data_source_query(),
        setup_hold_trigger_slope_query(),
        setup_hold_trigger_setup_time_query(),
        setup_hold_trigger_hold_time_query(),
    ]


def setup_hold_trigger_configure_commands(
    *,
    clock_channel: int,
    data_channel: int,
    slope: str,
    setup_time_seconds: float,
    hold_time_seconds: float,
    capabilities: ScopeCapabilities,
) -> list[str]:
    """Return the DSO analog setup-hold trigger configure SCPI sequence."""

    clock_channel = validate_setup_hold_trigger_channel(clock_channel, capabilities, "clock")
    data_channel = validate_setup_hold_trigger_channel(data_channel, capabilities, "data")
    slope_command = normalize_setup_hold_slope(slope)
    setup_time = validate_setup_hold_trigger_time(setup_time_seconds, "setup")
    hold_time = validate_setup_hold_trigger_time(hold_time_seconds, "hold")

    return [
        trigger_mode_setup_hold_command(),
        setup_hold_trigger_clock_source_command(clock_channel),
        setup_hold_trigger_data_source_command(data_channel),
        setup_hold_trigger_slope_command(slope_command),
        setup_hold_trigger_setup_time_command(setup_time),
        setup_hold_trigger_hold_time_command(hold_time),
    ]


def validate_setup_hold_trigger_time(seconds: float, field_name: str = "time") -> float:
    """Validate setup-hold timing in seconds."""

    try:
        value = float(seconds)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError(
            f"setup-hold trigger {field_name} time must be a number of seconds."
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise ParameterValidationError(
            f"setup-hold trigger {field_name} time must be a positive finite number of seconds."
        )
    return value


def validate_setup_hold_trigger_channel(
    channel: int, capabilities: ScopeCapabilities, field_name: str = "source"
) -> int:
    """Validate setup-hold DSO analog channel input."""

    if isinstance(channel, bool) or not isinstance(channel, int):
        raise ParameterValidationError(
            f"setup-hold trigger {field_name} channel must be an integer analog channel."
        )
    return validate_analog_channel(channel, capabilities)


def edge_burst_source_command(channel: int) -> str:
    """Build the SCPI command for Nth Edge Burst trigger source."""

    return f":TRIGger:EBURst:SOURce CHANnel{channel}"


def edge_burst_source_query() -> str:
    """Build the SCPI query for Nth Edge Burst trigger source."""

    return ":TRIGger:EBURst:SOURce?"


def edge_burst_slope_command(slope_scpi: str) -> str:
    """Build the SCPI command for Nth Edge Burst trigger slope."""

    return f":TRIGger:EBURst:SLOPe {slope_scpi}"


def edge_burst_slope_query() -> str:
    """Build the SCPI query for Nth Edge Burst trigger slope."""

    return ":TRIGger:EBURst:SLOPe?"


def edge_burst_count_command(count: int) -> str:
    """Build the SCPI command for Nth Edge Burst trigger count."""

    return f":TRIGger:EBURst:COUNt {count}"


def edge_burst_count_query() -> str:
    """Build the SCPI query for Nth Edge Burst trigger count."""

    return ":TRIGger:EBURst:COUNt?"


def edge_burst_idle_command(seconds: float) -> str:
    """Build the SCPI command for Nth Edge Burst trigger idle time."""

    return f":TRIGger:EBURst:IDLE {_format_scpi_float(seconds)}"


def edge_burst_idle_query() -> str:
    """Build the SCPI query for Nth Edge Burst trigger idle time."""

    return ":TRIGger:EBURst:IDLE?"


def edge_burst_trigger_query_commands(*, include_level_for_channel: int | None = None) -> list[str]:
    """Return the Nth Edge Burst trigger query SCPI sequence."""

    commands = [
        trigger_mode_query(),
        edge_burst_source_query(),
        edge_burst_slope_query(),
        edge_burst_count_query(),
        edge_burst_idle_query(),
    ]
    if include_level_for_channel is not None:
        commands.append(edge_trigger_level_for_source_query(include_level_for_channel))
    return commands


def edge_burst_trigger_configure_commands(
    *,
    source_channel: int,
    slope: str,
    count: int,
    idle_time: float,
    capabilities: ScopeCapabilities,
    level_volts: float | None = None,
) -> list[str]:
    """Return the DSO analog Nth Edge Burst trigger configure SCPI sequence."""

    channel = validate_edge_burst_source_channel(source_channel, capabilities)
    slope_command = normalize_edge_burst_slope(slope)
    count_value = validate_edge_burst_count(count)
    idle_value = validate_edge_burst_idle_time(idle_time)
    level = validate_trigger_level(level_volts) if level_volts is not None else None
    commands = [
        trigger_mode_edge_burst_command(),
        edge_burst_source_command(channel),
        edge_burst_slope_command(slope_command),
        edge_burst_count_command(count_value),
        edge_burst_idle_command(idle_value),
    ]
    if level is not None:
        commands.append(edge_trigger_level_for_source_command(level, channel))
    return commands


def validate_edge_burst_count(count: int) -> int:
    """Validate the Nth Edge Burst edge count."""

    if isinstance(count, bool) or not isinstance(count, int):
        raise ParameterValidationError("edge-burst trigger count must be an integer.")
    if count < 1:
        raise ParameterValidationError("edge-burst trigger count must be at least 1.")
    return count


def validate_edge_burst_idle_time(seconds: float) -> float:
    """Validate the documented Nth Edge Burst idle time range."""

    try:
        value = float(seconds)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError(
            "edge-burst trigger idle_time must be a number of seconds."
        ) from exc
    if not math.isfinite(value):
        raise ParameterValidationError(
            "edge-burst trigger idle_time must be a finite number of seconds."
        )
    if value < 1e-8 or value > 10.0:
        raise ParameterValidationError(
            "edge-burst trigger idle_time must be between 1e-8 and 10.0 seconds."
        )
    return value


def validate_edge_burst_source_channel(
    channel: int, capabilities: ScopeCapabilities
) -> int:
    """Validate edge-burst DSO analog channel input."""

    if isinstance(channel, bool) or not isinstance(channel, int):
        raise ParameterValidationError(
            "edge-burst trigger source_channel must be an integer analog channel."
        )
    return validate_analog_channel(channel, capabilities)


def tv_trigger_source_command(channel: int) -> str:
    """Build the SCPI command for TV trigger source."""

    return f":TRIGger:TV:SOURce CHANnel{channel}"


def tv_trigger_source_query() -> str:
    """Build the SCPI query for TV trigger source."""

    return ":TRIGger:TV:SOURce?"


def tv_trigger_standard_command(standard_scpi: str) -> str:
    """Build the SCPI command for TV trigger standard."""

    return f":TRIGger:TV:STANdard {standard_scpi}"


def tv_trigger_standard_query() -> str:
    """Build the SCPI query for TV trigger standard."""

    return ":TRIGger:TV:STANdard?"


def tv_trigger_mode_command(mode_scpi: str) -> str:
    """Build the SCPI command for TV trigger mode."""

    return f":TRIGger:TV:MODE {mode_scpi}"


def tv_trigger_mode_query() -> str:
    """Build the SCPI query for TV trigger mode."""

    return ":TRIGger:TV:MODE?"


def tv_trigger_line_command(line: int) -> str:
    """Build the SCPI command for TV trigger line."""

    return f":TRIGger:TV:LINE {line}"


def tv_trigger_line_query() -> str:
    """Build the SCPI query for TV trigger line."""

    return ":TRIGger:TV:LINE?"


def tv_trigger_polarity_command(polarity_scpi: str) -> str:
    """Build the SCPI command for TV trigger polarity."""

    return f":TRIGger:TV:POLarity {polarity_scpi}"


def tv_trigger_polarity_query() -> str:
    """Build the SCPI query for TV trigger polarity."""

    return ":TRIGger:TV:POLarity?"


def tv_trigger_query_commands() -> list[str]:
    """Return the basic TV trigger query SCPI sequence."""

    return [
        trigger_mode_query(),
        tv_trigger_source_query(),
        tv_trigger_standard_query(),
        tv_trigger_mode_query(),
        tv_trigger_line_query(),
        tv_trigger_polarity_query(),
    ]


def tv_trigger_configure_commands(
    *,
    source_channel: int,
    standard: str,
    mode: str,
    polarity: str,
    capabilities: ScopeCapabilities,
    line: int | None = None,
) -> list[str]:
    """Return the DSO analog basic TV trigger configure SCPI sequence."""

    channel = validate_tv_source_channel(source_channel, capabilities)
    standard_value = validate_tv_standard(standard)
    standard_command = normalize_tv_standard(standard)
    mode_value = validate_tv_mode(mode)
    mode_command = normalize_tv_mode(mode)
    line_value = validate_tv_line(standard_value, mode_value, line)
    polarity_command = normalize_tv_polarity(polarity)
    commands = [
        trigger_mode_tv_command(),
        tv_trigger_source_command(channel),
        tv_trigger_standard_command(standard_command),
        tv_trigger_mode_command(mode_command),
    ]
    if line_value is not None:
        commands.append(tv_trigger_line_command(line_value))
    commands.append(tv_trigger_polarity_command(polarity_command))
    return commands


def validate_tv_source_channel(channel: int, capabilities: ScopeCapabilities) -> int:
    """Validate TV trigger DSO analog channel input."""

    if isinstance(channel, bool) or not isinstance(channel, int):
        raise ParameterValidationError(
            "TV trigger source_channel must be an integer analog channel."
        )
    return validate_analog_channel(channel, capabilities)


def validate_tv_standard(standard: str) -> str:
    """Validate and normalize a public TV standard value."""

    normalize_tv_standard(standard)
    return standard.strip().lower()


def validate_tv_mode(mode: str) -> str:
    """Validate and normalize a public TV mode value."""

    normalize_tv_mode(mode)
    return mode.strip().lower()


def validate_tv_line(standard: str, mode: str, line: int | None) -> int | None:
    """Validate TV line presence and documented v1 line ranges."""

    if mode in _TV_LINE_MODES:
        if line is None:
            raise ParameterValidationError(f"TV trigger mode {mode} requires line.")
        if isinstance(line, bool) or not isinstance(line, int):
            raise ParameterValidationError("TV trigger line must be a positive integer.")
        low, high = _TV_LINE_RANGES[(standard, mode)]
        if line < low or line > high:
            raise ParameterValidationError(
                f"TV trigger line for {standard} {mode} must be from {low} through {high}."
            )
        return line
    if line is not None:
        raise ParameterValidationError(f"TV trigger mode {mode} does not accept line.")
    return None


def pattern_trigger_format_command() -> str:
    """Build the SCPI command for ASCII pattern format."""

    return ":TRIGger:PATTern:FORMat ASCii"


def pattern_trigger_format_query() -> str:
    """Build the SCPI query for pattern format."""

    return ":TRIGger:PATTern:FORMat?"


def pattern_trigger_pattern_command(pattern: str) -> str:
    """Build the SCPI command for the raw ASCII pattern string."""

    return f':TRIGger:PATTern "{pattern}"'


def pattern_trigger_pattern_query() -> str:
    """Build the SCPI query for pattern state."""

    return ":TRIGger:PATTern?"


def pattern_trigger_qualifier_command() -> str:
    """Build the SCPI command for entered pattern qualifier."""

    return ":TRIGger:PATTern:QUALifier ENTered"


def pattern_trigger_qualifier_query() -> str:
    """Build the SCPI query for pattern qualifier."""

    return ":TRIGger:PATTern:QUALifier?"


def pattern_trigger_query_commands() -> list[str]:
    """Return the pattern trigger query SCPI sequence."""

    return [
        trigger_mode_query(),
        pattern_trigger_format_query(),
        pattern_trigger_pattern_query(),
        pattern_trigger_qualifier_query(),
    ]


def pattern_trigger_configure_commands(
    *,
    pattern: str,
    capabilities: ScopeCapabilities,
) -> list[str]:
    """Return the DSO ASCII pattern trigger configure SCPI sequence."""

    normalized = validate_pattern_trigger_pattern(pattern, capabilities)
    return [
        trigger_mode_pattern_command(),
        pattern_trigger_format_command(),
        pattern_trigger_pattern_command(normalized),
        pattern_trigger_qualifier_command(),
    ]


def validate_pattern_trigger_pattern(pattern: str, capabilities: ScopeCapabilities) -> str:
    """Validate and normalize a v1 DSO ASCII pattern string."""

    if not isinstance(pattern, str):
        raise ParameterValidationError("pattern trigger pattern must be a string.")
    if pattern.lower().startswith("0x"):
        raise ParameterValidationError("pattern trigger pattern does not accept hex strings.")
    normalized = pattern.upper()
    if not normalized:
        raise ParameterValidationError("pattern trigger pattern must not be empty.")
    if any(char not in {"0", "1", "X"} for char in normalized):
        raise ParameterValidationError("pattern trigger pattern may contain only 0, 1, and X.")
    if len(normalized) != capabilities.analog_channels:
        raise ParameterValidationError(
            "pattern trigger pattern length must match the model analog channel count "
            f"({capabilities.analog_channels})."
        )
    return normalized


def or_trigger_pattern_command(pattern: str) -> str:
    """Build the SCPI command for the raw OR trigger edge mask."""

    return f':TRIGger:OR "{pattern}"'


def or_trigger_pattern_query() -> str:
    """Build the SCPI query for OR trigger state."""

    return ":TRIGger:OR?"


def or_trigger_query_commands() -> list[str]:
    """Return the OR trigger query SCPI sequence."""

    return [
        trigger_mode_query(),
        or_trigger_pattern_query(),
    ]


def or_trigger_configure_commands(
    *,
    pattern: str,
    capabilities: ScopeCapabilities,
) -> list[str]:
    """Return the DSO analog OR trigger configure SCPI sequence."""

    normalized = validate_or_trigger_pattern(pattern, capabilities)
    return [
        trigger_mode_or_command(),
        or_trigger_pattern_command(normalized),
    ]


def validate_or_trigger_pattern(pattern: str, capabilities: ScopeCapabilities) -> str:
    """Validate and normalize a v1 DSO analog OR trigger edge mask."""

    if not isinstance(pattern, str):
        raise ParameterValidationError("OR trigger pattern must be a string.")
    if pattern.lower().startswith("0x"):
        raise ParameterValidationError("OR trigger pattern does not accept hex strings.")
    normalized = pattern.upper()
    if not normalized:
        raise ParameterValidationError("OR trigger pattern must not be empty.")
    if any(char not in {"R", "F", "E", "X"} for char in normalized):
        raise ParameterValidationError("OR trigger pattern may contain only R, F, E, and X.")
    if len(normalized) != capabilities.analog_channels:
        raise ParameterValidationError(
            "OR trigger pattern length must match the model analog channel count "
            f"({capabilities.analog_channels})."
        )
    return normalized


def normalize_trigger_sweep(mode: str) -> str:
    """Normalize a public trigger sweep value into a SCPI argument."""

    try:
        return _TRIGGER_SWEEP_COMMANDS[mode.strip().lower()]
    except (AttributeError, KeyError) as exc:
        raise ParameterValidationError(
            "trigger sweep mode must be one of: auto, normal."
        ) from exc


def parse_trigger_sweep(raw: str) -> str:
    """Parse a trigger sweep readback."""

    try:
        return _TRIGGER_SWEEP_READBACKS[raw.strip().upper()]
    except KeyError as exc:
        raise TriggerResponseError(
            f"Could not parse trigger sweep response: {raw!r}"
        ) from exc


def parse_trigger_reject_bool(raw: str) -> bool:
    """Parse a trigger reject query readback."""

    text = raw.strip()
    if text == "1":
        return True
    if text == "0":
        return False
    raise TriggerResponseError(f"Could not parse trigger reject response: {raw!r}")


def parse_edge_trigger_source(raw: str) -> int:
    """Parse an edge trigger source readback into an analog channel number."""

    normalized = raw.strip().upper()
    if normalized.startswith("CHANNEL"):
        suffix = normalized.removeprefix("CHANNEL")
    elif normalized.startswith("CHAN"):
        suffix = normalized.removeprefix("CHAN")
    else:
        raise TriggerResponseError(f"Could not parse edge trigger source response: {raw!r}")

    try:
        channel = int(suffix)
    except ValueError as exc:
        raise TriggerResponseError(f"Could not parse edge trigger source response: {raw!r}") from exc
    if channel < 1:
        raise TriggerResponseError(f"Could not parse edge trigger source response: {raw!r}")
    return channel


def parse_trigger_edge_source(raw: str) -> EdgeTriggerSourceState:
    """Parse an Edge Trigger source readback without rejecting unknown states."""

    raw_source = raw.strip()
    normalized = raw_source.upper()
    if normalized.startswith("CHANNEL"):
        suffix = normalized.removeprefix("CHANNEL")
    elif normalized.startswith("CHAN"):
        suffix = normalized.removeprefix("CHAN")
    else:
        suffix = None
    if suffix is not None:
        try:
            channel = int(suffix)
        except ValueError:
            channel = None
        if channel is not None and channel >= 1:
            return EdgeTriggerSourceState(
                source="analog-channel",
                source_channel=channel,
                raw_source=raw_source,
            )
    if normalized in {"EXT", "EXTERNAL"}:
        return EdgeTriggerSourceState(
            source="external",
            source_channel=None,
            raw_source=raw_source,
        )
    if normalized == "LINE":
        return EdgeTriggerSourceState(
            source="line",
            source_channel=None,
            raw_source=raw_source,
        )
    return EdgeTriggerSourceState(
        source=None,
        source_channel=None,
        raw_source=raw_source,
    )


def parse_trigger_mode(raw: str) -> str | None:
    """Parse a trigger mode readback when recognized."""

    normalized = raw.strip().upper()
    if normalized in {"GLIT", "GLITCH"}:
        return "glitch"
    if normalized in {"RUNT"}:
        return "runt"
    if normalized in {"TRAN", "TRANSITION"}:
        return "transition"
    if normalized in {"DEL", "DELAY"}:
        return "delay"
    if normalized in {"SHOL", "SHOLD"}:
        return "setup-hold"
    if normalized in {"EBUR", "EBURST"}:
        return "edge-burst"
    if normalized in {"TV"}:
        return "tv"
    if normalized in {"PATT", "PATTERN"}:
        return "pattern"
    if normalized in {"OR"}:
        return "or"
    if normalized in {"EDGE"}:
        return "edge"
    if normalized == "SBUS1":
        return "serial1"
    if normalized == "SBUS2":
        return "serial2"
    return None


def parse_glitch_source(raw: str) -> tuple[str | None, int | None, int | None]:
    """Parse a glitch source readback without assuming analog-only state."""

    normalized = raw.strip().upper()
    if normalized in {"", "NONE"}:
        return "none", None, None
    if normalized.startswith("CHANNEL"):
        suffix = normalized.removeprefix("CHANNEL")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix), None
    if normalized.startswith("CHAN"):
        suffix = normalized.removeprefix("CHAN")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix), None
    if normalized.startswith("DIGITAL"):
        suffix = normalized.removeprefix("DIGITAL")
        return _parse_digital_source(suffix), None, _parse_digital_suffix(suffix)
    if normalized.startswith("DIG"):
        suffix = normalized.removeprefix("DIG")
        return _parse_digital_source(suffix), None, _parse_digital_suffix(suffix)
    if normalized.startswith("EXT"):
        return "external", None, None
    return None, None, None


def parse_glitch_polarity_readback(raw: str) -> str | None:
    """Parse a glitch polarity readback when recognized."""

    return _GLITCH_POLARITY_READBACKS.get(raw.strip().upper())


def parse_glitch_qualifier_readback(raw: str) -> str | None:
    """Parse a glitch qualifier readback when recognized."""

    return _GLITCH_QUALIFIER_READBACKS.get(raw.strip().upper())


def parse_runt_source(raw: str) -> tuple[str | None, int | None]:
    """Parse a runt source readback, preserving unsafe non-analog sources."""

    normalized = raw.strip().upper()
    if normalized.startswith("CHANNEL"):
        suffix = normalized.removeprefix("CHANNEL")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix)
    if normalized.startswith("CHAN"):
        suffix = normalized.removeprefix("CHAN")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix)
    return None, None


def parse_runt_polarity_readback(raw: str) -> str | None:
    """Parse a runt polarity readback when recognized."""

    return _RUNT_POLARITY_READBACKS.get(raw.strip().upper())


def parse_runt_qualifier_readback(raw: str) -> str | None:
    """Parse a runt qualifier readback when recognized."""

    return _RUNT_QUALIFIER_READBACKS.get(raw.strip().upper())


def parse_transition_source(raw: str) -> tuple[str | None, int | None]:
    """Parse a transition source readback, preserving unsafe non-analog sources."""

    normalized = raw.strip().upper()
    if normalized.startswith("CHANNEL"):
        suffix = normalized.removeprefix("CHANNEL")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix)
    if normalized.startswith("CHAN"):
        suffix = normalized.removeprefix("CHAN")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix)
    return None, None


def parse_transition_slope_readback(raw: str) -> str | None:
    """Parse a transition slope readback when recognized."""

    return _TRANSITION_SLOPE_READBACKS.get(raw.strip().upper())


def parse_transition_qualifier_readback(raw: str) -> str | None:
    """Parse a transition qualifier readback when recognized."""

    return _TRANSITION_QUALIFIER_READBACKS.get(raw.strip().upper())


def parse_delay_source(raw: str) -> tuple[str | None, int | None, int | None]:
    """Parse a delay trigger source while preserving unsupported raw states."""

    normalized = raw.strip().upper()
    if normalized.startswith("CHANNEL"):
        suffix = normalized.removeprefix("CHANNEL")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix), None
    if normalized.startswith("CHAN"):
        suffix = normalized.removeprefix("CHAN")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix), None
    if normalized.startswith("DIGITAL"):
        suffix = normalized.removeprefix("DIGITAL")
        return _parse_digital_source(suffix), None, _parse_digital_suffix(suffix)
    if normalized.startswith("DIG"):
        suffix = normalized.removeprefix("DIG")
        return _parse_digital_source(suffix), None, _parse_digital_suffix(suffix)
    return None, None, None


def parse_delay_slope_readback(raw: str) -> str | None:
    """Parse a delay trigger slope readback when recognized."""

    return _DELAY_SLOPE_READBACKS.get(raw.strip().upper())


def parse_setup_hold_source(raw: str) -> tuple[str | None, int | None, int | None]:
    """Parse a setup-hold source while preserving unsupported raw states."""

    normalized = raw.strip().upper()
    if normalized.startswith("CHANNEL"):
        suffix = normalized.removeprefix("CHANNEL")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix), None
    if normalized.startswith("CHAN"):
        suffix = normalized.removeprefix("CHAN")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix), None
    if normalized.startswith("DIGITAL"):
        suffix = normalized.removeprefix("DIGITAL")
        return _parse_digital_source(suffix), None, _parse_digital_suffix(suffix)
    if normalized.startswith("DIG"):
        suffix = normalized.removeprefix("DIG")
        return _parse_digital_source(suffix), None, _parse_digital_suffix(suffix)
    return None, None, None


def parse_setup_hold_slope_readback(raw: str) -> str | None:
    """Parse a setup-hold trigger slope readback when recognized."""

    return _SETUP_HOLD_SLOPE_READBACKS.get(raw.strip().upper())


def parse_edge_burst_source(raw: str) -> tuple[str | None, int | None, int | None]:
    """Parse an edge-burst source while preserving unsupported raw states."""

    normalized = raw.strip().upper()
    if normalized in {"", "NONE"}:
        return "none", None, None
    if normalized.startswith("CHANNEL"):
        suffix = normalized.removeprefix("CHANNEL")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix), None
    if normalized.startswith("CHAN"):
        suffix = normalized.removeprefix("CHAN")
        return _parse_channel_source(suffix), _parse_channel_suffix(suffix), None
    if normalized.startswith("DIGITAL"):
        suffix = normalized.removeprefix("DIGITAL")
        return _parse_digital_source(suffix), None, _parse_digital_suffix(suffix)
    if normalized.startswith("DIG"):
        suffix = normalized.removeprefix("DIG")
        return _parse_digital_source(suffix), None, _parse_digital_suffix(suffix)
    return None, None, None


def parse_edge_burst_slope_readback(raw: str) -> str | None:
    """Parse an edge-burst trigger slope readback when recognized."""

    return _EDGE_BURST_SLOPE_READBACKS.get(raw.strip().upper())


def parse_tv_source(raw: str) -> int | None:
    """Parse a TV source readback as analog channel when safe."""

    normalized = raw.strip().upper()
    if normalized.startswith("CHANNEL"):
        return _parse_channel_suffix(normalized.removeprefix("CHANNEL"))
    if normalized.startswith("CHAN"):
        return _parse_channel_suffix(normalized.removeprefix("CHAN"))
    return None


def parse_tv_standard_readback(raw: str) -> str | None:
    """Parse a TV standard readback when it is in the basic v1 set."""

    return _TV_STANDARD_READBACKS.get(raw.strip().upper())


def parse_tv_mode_readback(raw: str) -> str | None:
    """Parse a TV mode readback when it is in the basic v1 set."""

    return _TV_MODE_READBACKS.get(raw.strip().upper())


def parse_tv_line_readback(raw: str) -> int | None:
    """Parse a TV line readback, preserving non-integer states as absent."""

    try:
        return int(raw.strip())
    except ValueError:
        return None


def parse_tv_polarity_readback(raw: str) -> str | None:
    """Parse a TV polarity readback when recognized."""

    return _TV_POLARITY_READBACKS.get(raw.strip().upper())


def parse_edge_burst_count_readback(raw: str) -> int | None:
    """Parse an edge-burst trigger count readback."""

    text = raw.strip()
    if not text or text.upper() == "NONE":
        return None
    try:
        value = int(text)
    except ValueError as exc:
        raise TriggerResponseError(
            f"Could not parse edge-burst trigger count response: {raw!r}"
        ) from exc
    if value < 1:
        raise TriggerResponseError(
            f"Could not parse edge-burst trigger count response: {raw!r}"
        )
    return value


def parse_delay_count_readback(raw: str) -> int | None:
    """Parse a delay trigger count readback."""

    text = raw.strip()
    if not text or text.upper() == "NONE":
        return None
    try:
        value = int(text)
    except ValueError as exc:
        raise TriggerResponseError(
            f"Could not parse trigger delay count response: {raw!r}"
        ) from exc
    if value < 1:
        raise TriggerResponseError(f"Could not parse trigger delay count response: {raw!r}")
    return value


def parse_pattern_format_readback(raw: str) -> str | None:
    """Parse a pattern format readback when recognized."""

    return _PATTERN_FORMAT_READBACKS.get(raw.strip().upper())


def parse_pattern_qualifier_readback(raw: str) -> str | None:
    """Parse a pattern qualifier readback when recognized."""

    return _PATTERN_QUALIFIER_READBACKS.get(raw.strip().upper())


def parse_pattern_trigger_response(raw: str) -> tuple[str | None, str | None, str | None]:
    """Parse :TRIGger:PATTern? as string plus optional edge fields."""

    parts = _split_pattern_response(raw)
    if not parts:
        return None, None, None
    pattern = _strip_optional_quotes(parts[0])
    edge_source = parts[1].strip() if len(parts) > 1 else None
    edge = parts[2].strip() if len(parts) > 2 else None
    return pattern, edge_source, edge


def parse_or_trigger_pattern_response(raw: str) -> str | None:
    """Parse common OR trigger pattern readbacks without destroying unusual values."""

    pattern = _strip_optional_quotes(raw.strip()).upper()
    if pattern and all(char in {"R", "F", "E", "X"} for char in pattern):
        return pattern
    return None


def parse_edge_slope(raw: str) -> str:
    """Parse an edge trigger slope readback."""

    normalized = raw.strip().upper()
    try:
        return _SLOPE_READBACKS[normalized]
    except KeyError as exc:
        raise TriggerResponseError(f"Could not parse edge trigger slope response: {raw!r}") from exc


def parse_trigger_edge_slope(raw: str) -> EdgeTriggerSlopeState:
    """Parse an Edge Trigger slope readback without rejecting unknown values."""

    raw_slope = raw.strip()
    return EdgeTriggerSlopeState(
        slope=_SLOPE_READBACKS.get(raw_slope.upper()),
        raw_slope=raw_slope,
    )


def parse_trigger_float(raw: str, setting_name: str) -> float:
    """Parse a numeric trigger query response."""

    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise TriggerResponseError(
            f"Could not parse trigger {setting_name} response: {raw!r}"
        ) from exc
    if not math.isfinite(value):
        raise TriggerResponseError(f"Could not parse trigger {setting_name} response: {raw!r}")
    return value


def parse_external_trigger_range(raw: str) -> ExternalTriggerRangeState:
    """Parse an External trigger range response while preserving raw SCPI."""

    raw_range = raw.strip()
    return ExternalTriggerRangeState(
        range_volts=parse_trigger_float(raw_range, "External trigger range"),
        raw_range=raw_range,
    )


def parse_external_trigger_probe(raw: str) -> ExternalTriggerProbeState:
    """Parse an External trigger probe response while preserving raw SCPI."""

    raw_attenuation = raw.strip()
    return ExternalTriggerProbeState(
        attenuation=parse_trigger_float(raw_attenuation, "External trigger probe attenuation"),
        raw_attenuation=raw_attenuation,
    )


def normalize_external_trigger_units(raw: str) -> str | None:
    """Normalize an External units readback without claiming future values."""

    return _EXTERNAL_TRIGGER_UNITS_READBACKS.get(raw.strip().upper())


def parse_external_trigger_units(raw: str) -> ExternalTriggerUnitsState:
    """Parse an External trigger units response while preserving raw SCPI."""

    raw_units = raw.strip()
    return ExternalTriggerUnitsState(
        units=normalize_external_trigger_units(raw_units),
        raw_units=raw_units,
    )


def parse_external_trigger_settings(raw: str) -> ExternalTriggerSettingsState:
    """Parse an aggregate External trigger settings response in any field order."""

    raw_response = raw.strip()
    if not raw_response:
        raise TriggerResponseError("Could not parse External trigger settings response: empty response")

    values: dict[str, object] = {}
    saw_field = False
    for segment in raw_response.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        saw_field = True
        parts = segment.split(None, 1)
        header = parts[0].lstrip(":")
        value = parts[1].strip() if len(parts) == 2 else None
        final_header = header.split(":")[-1].upper()
        if final_header not in {
            "BWL",
            "BWLIMIT",
            "RANG",
            "RANGE",
            "UNIT",
            "UNITS",
            "PROB",
            "PROBE",
        }:
            continue
        if value is None:
            raise TriggerResponseError(
                f"Could not parse External trigger settings response: {raw!r}"
            )
        if final_header in {"BWL", "BWLIMIT"}:
            normalized = value.upper()
            if normalized in {"0", "OFF"}:
                values["bandwidth_limit_enabled"] = False
            elif normalized in {"1", "ON"}:
                values["bandwidth_limit_enabled"] = True
            else:
                raise TriggerResponseError(
                    f"Could not parse External trigger bandwidth limit response: {value!r}"
                )
        elif final_header in {"RANG", "RANGE"}:
            values["range_value"] = parse_trigger_float(value, "External trigger range")
        elif final_header in {"UNIT", "UNITS"}:
            values["units"] = normalize_external_trigger_units(value)
        elif final_header in {"PROB", "PROBE"}:
            values["probe_attenuation"] = parse_trigger_float(
                value, "External trigger probe attenuation"
            )

    if not saw_field:
        raise TriggerResponseError(
            f"Could not parse External trigger settings response: {raw!r}"
        )

    return ExternalTriggerSettingsState(
        probe_attenuation=values.get("probe_attenuation"),
        range_value=values.get("range_value"),
        units=values.get("units"),
        bandwidth_limit_enabled=values.get("bandwidth_limit_enabled"),
        raw_response=raw_response,
    )


def parse_edge_trigger_external_level(raw: str) -> EdgeTriggerExternalLevelState:
    """Parse an External-qualified Edge Trigger level response."""

    raw_level = raw.strip()
    return EdgeTriggerExternalLevelState(
        level_volts=parse_trigger_float(raw_level, "External Edge Trigger level"),
        raw_level=raw_level,
    )


def parse_optional_trigger_float(raw: str, setting_name: str) -> float | None:
    """Parse a numeric trigger response, preserving explicit NONE as absent."""

    if raw.strip().upper() == "NONE":
        return None
    return parse_trigger_float(raw, setting_name)


def parse_glitch_level(raw: str) -> float | None:
    """Parse a glitch trigger level readback."""

    text = raw.strip()
    if text.upper() == "NONE":
        return None
    return parse_trigger_float(text.split(",", 1)[0], "glitch level")


def parse_glitch_range(raw: str) -> tuple[float | None, float | None]:
    """Parse glitch range as CLI min/max from SCPI max,min readback."""

    text = raw.strip()
    if text.upper() == "NONE":
        return None, None
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2:
        raise TriggerResponseError(f"Could not parse trigger glitch range response: {raw!r}")
    max_time = parse_trigger_float(parts[0], "glitch range max")
    min_time = parse_trigger_float(parts[1], "glitch range min")
    return min_time, max_time


def validate_trigger_time(seconds: float) -> float:
    """Validate a positive trigger timing value in seconds."""

    try:
        value = float(seconds)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError("trigger time must be a number of seconds.") from exc
    if not math.isfinite(value) or value <= 0:
        raise ParameterValidationError("trigger time must be a positive finite number of seconds.")
    return value


def _format_scpi_float(value: float) -> str:
    return f"{value:.12g}"


def _parse_channel_suffix(suffix: str) -> int | None:
    try:
        value = int(suffix)
    except ValueError:
        return None
    return value if value >= 1 else None


def _parse_digital_suffix(suffix: str) -> int | None:
    try:
        value = int(suffix)
    except ValueError:
        return None
    return value if value >= 0 else None


def _parse_channel_source(suffix: str) -> str | None:
    return "channel" if _parse_channel_suffix(suffix) is not None else None


def _parse_digital_source(suffix: str) -> str | None:
    return "digital" if _parse_digital_suffix(suffix) is not None else None


def _trigger_bool_token(enabled: bool) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("trigger reject enabled value must be a boolean.")
    return "ON" if enabled else "OFF"


def _split_pattern_response(raw: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    for char in raw.strip():
        if char == '"':
            in_quotes = not in_quotes
            current.append(char)
        elif char == "," and not in_quotes:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current or raw.strip():
        parts.append("".join(current).strip())
    return parts


def _strip_optional_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


def force_trigger_command() -> str:
    """Return the SCPI command that forces one trigger event.

    The command is a state-changing write. High-level workflows must keep force
    behavior explicit and opt-in.
    """

    return ":TRIGger:FORCe"


def classify_operation_condition(value: int, *, profile: str = "live") -> str:
    """Classify one operation-condition value for trigger waiting.

    DSO-X 2000X/3000X/4000X and simulator waits use the Operation Status
    Condition Run bit: set means acquisition is still pending, clear means the
    wait completed. Other live profiles remain conservative until separately
    validated.
    """

    if profile in {"2000x", "3000x", "4000x", "simulator"}:
        if value & OPERATION_CONDITION_RUN_MASK:
            return "pending"
        return "complete"
    return "unknown"


def parse_operation_condition(raw: str) -> int:
    """Parse an operation-condition response into an integer value."""

    text = raw.strip()
    try:
        return int(text, 0)
    except ValueError:
        try:
            value = float(text)
        except ValueError as exc:
            raise TriggerResponseError(
                f"Could not parse operation condition response: {raw!r}"
            ) from exc
    if not math.isfinite(value) or not value.is_integer():
        raise TriggerResponseError(f"Could not parse operation condition response: {raw!r}")
    return int(value)


def validate_trigger_wait_config(config: TriggerWaitConfig) -> TriggerWaitConfig:
    """Validate finite trigger wait settings."""

    if config.timeout_ms < 1:
        raise ParameterValidationError("trigger timeout must be at least 1 ms.")
    if config.poll_interval_ms < 1:
        raise ParameterValidationError("trigger poll interval must be at least 1 ms.")
    if config.poll_interval_ms > config.timeout_ms:
        raise ParameterValidationError(
            "trigger poll interval must be less than or equal to trigger timeout."
        )
    return config


def wait_for_trigger_completion(
    scpi: SCPIClient,
    config: TriggerWaitConfig,
    *,
    classifier_profile: str = "live",
    stop_requested: StopRequested | None = None,
) -> TriggerWaitResult:
    """Arm a single acquisition and wait finitely for trigger completion."""

    config = validate_trigger_wait_config(config)
    scpi.write(single_command())
    return wait_for_current_trigger_completion(
        scpi,
        config,
        classifier_profile=classifier_profile,
        stop_requested=stop_requested,
    )


def wait_for_current_trigger_completion(
    scpi: SCPIClient,
    config: TriggerWaitConfig,
    *,
    classifier_profile: str = "live",
    stop_requested: StopRequested | None = None,
) -> TriggerWaitResult:
    """Wait finitely for an acquisition that has already been armed."""

    config = validate_trigger_wait_config(config)
    raw_values: list[str] = []
    condition_values: list[int] = []
    start = config.clock()

    outcome, error = _poll_operation_condition(
        scpi,
        config,
        deadline=start + config.timeout_ms / 1000.0,
        raw_values=raw_values,
        condition_values=condition_values,
        classifier_profile=classifier_profile,
        stop_requested=stop_requested,
    )
    if outcome == "complete":
        return _trigger_wait_result(
            "natural", False, False, start, config, raw_values, condition_values
        )
    if outcome == "unknown":
        return _trigger_wait_result(
            "unknown", False, False, start, config, raw_values, condition_values, error=error
        )
    if outcome == "cancelled":
        return _trigger_wait_result(
            "cancelled", False, False, start, config, raw_values, condition_values
        )
    if not config.force_on_timeout:
        return _trigger_wait_result(
            "timeout", False, True, start, config, raw_values, condition_values
        )

    scpi.write(force_trigger_command())
    force_start = config.clock()
    outcome, error = _poll_operation_condition(
        scpi,
        config,
        deadline=force_start + config.timeout_ms / 1000.0,
        raw_values=raw_values,
        condition_values=condition_values,
        classifier_profile=classifier_profile,
        stop_requested=stop_requested,
    )
    if outcome == "complete":
        return _trigger_wait_result(
            "forced", True, False, start, config, raw_values, condition_values
        )
    if outcome == "unknown":
        return _trigger_wait_result(
            "unknown", True, False, start, config, raw_values, condition_values, error=error
        )
    if outcome == "cancelled":
        return _trigger_wait_result(
            "cancelled", True, False, start, config, raw_values, condition_values
        )
    return _trigger_wait_result(
        "timeout", True, True, start, config, raw_values, condition_values
    )


def _poll_operation_condition(
    scpi: SCPIClient,
    config: TriggerWaitConfig,
    *,
    deadline: float,
    raw_values: list[str],
    condition_values: list[int],
    classifier_profile: str,
    stop_requested: StopRequested | None,
) -> tuple[str, str | None]:
    while True:
        try:
            raw = scpi.query(operation_condition_query())
            value = parse_operation_condition(raw)
        except Exception as exc:
            return "unknown", str(exc)
        raw_values.append(raw)
        condition_values.append(value)
        classification = classify_operation_condition(value, profile=classifier_profile)
        if classification == "complete":
            return "complete", None
        if classification == "unknown":
            return "unknown", f"unclassified operation condition value: {value}"
        if stop_requested is not None and stop_requested():
            return "cancelled", None
        now = config.clock()
        if now >= deadline:
            return "timeout", None
        sleep_s = min(config.poll_interval_ms / 1000.0, max(0.0, deadline - now))
        if sleep_s > 0 and not _wait_for_trigger_poll(
            config,
            sleep_s,
            stop_requested=stop_requested,
        ):
            return "cancelled", None


def _wait_for_trigger_poll(
    config: TriggerWaitConfig,
    seconds: float,
    *,
    stop_requested: StopRequested | None,
) -> bool:
    if stop_requested is None:
        config.sleep(seconds)
        return True
    if config.sleep is time.sleep and config.clock is time.monotonic:
        return interruptible_wait(seconds, stop_requested=stop_requested)
    if stop_requested():
        return False
    config.sleep(seconds)
    return not stop_requested()


def _trigger_wait_result(
    outcome: str,
    forced: bool,
    timed_out: bool,
    start: float,
    config: TriggerWaitConfig,
    raw_values: list[str],
    condition_values: list[int],
    *,
    error: str | None = None,
) -> TriggerWaitResult:
    capture_allowed = outcome in {"natural", "forced"}
    block_reason = None if capture_allowed else outcome
    return TriggerWaitResult(
        outcome=outcome,
        forced=forced,
        timed_out=timed_out,
        poll_count=len(raw_values),
        elapsed_ms=max(0.0, (config.clock() - start) * 1000.0),
        condition_values=tuple(condition_values),
        raw_values=tuple(raw_values),
        capture_allowed=capture_allowed,
        capture_block_reason=block_reason,
        error=error,
    )
