"""Read-only oscilloscope measurement queries."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time

from .capabilities import ScopeCapabilities
from typing import Sequence

from .channel import validate_analog_channel
from .errors import MeasurementResponseError, ParameterValidationError
from .scpi import SCPIClient

INVALID_MEASUREMENT_SENTINEL_ABS_MIN = 9.0e37
INVALID_MEASUREMENT_REASON = "invalid measurement sentinel"

_MEASUREMENT_QUERY_TEMPLATES = {
    "vpp": ":MEASure:VPP? CHANnel{channel}",
    "frequency": ":MEASure:FREQuency? CHANnel{channel}",
    "period": ":MEASure:PERiod? CHANnel{channel}",
    "vavg": ":MEASure:VAVerage? DISPlay,CHANnel{channel}",
    "vrms": ":MEASure:VRMS? DISPlay,DC,CHANnel{channel}",
    "ac_rms": ":MEASure:VRMS? DISPlay,AC,CHANnel{channel}",
    "minimum": ":MEASure:VMIN? CHANnel{channel}",
    "maximum": ":MEASure:VMAX? CHANnel{channel}",
    "x_at_max": ":MEASure:XMAX? CHANnel{channel}",
    "x_at_min": ":MEASure:XMIN? CHANnel{channel}",
    "rise_time": ":MEASure:RISetime? CHANnel{channel}",
    "fall_time": ":MEASure:FALLtime? CHANnel{channel}",
    "amplitude": ":MEASure:VAMPlitude? CHANnel{channel}",
    "top": ":MEASure:VTOP? CHANnel{channel}",
    "base": ":MEASure:VBASe? CHANnel{channel}",
    "overshoot": ":MEASure:OVERshoot? CHANnel{channel}",
    "preshoot": ":MEASure:PREShoot? CHANnel{channel}",
    "positive_width": ":MEASure:PWIDth? CHANnel{channel}",
    "negative_width": ":MEASure:NWIDth? CHANnel{channel}",
    "duty_cycle": ":MEASure:DUTYcycle? CHANnel{channel}",
    "negative_duty_cycle": ":MEASure:NDUTy? CHANnel{channel}",
    "area": ":MEASure:AREA? CHANnel{channel}",
    "positive_edges": ":MEASure:PEDGes? CHANnel{channel}",
    "negative_edges": ":MEASure:NEDGes? CHANnel{channel}",
    "positive_pulses": ":MEASure:PPULses? CHANnel{channel}",
    "negative_pulses": ":MEASure:NPULses? CHANnel{channel}",
}

_PAIR_MEASUREMENT_QUERY_TEMPLATES = {
    "phase": ":MEASure:PHASe? CHANnel{source_channel},CHANnel{reference_channel}",
    "delay": ":MEASure:DELay? AUTO,CHANnel{source_channel},CHANnel{reference_channel}",
}

_PARAMETERIZED_MEASUREMENT_ITEMS = (
    "y_at_x",
    "time_at_edge",
    "time_at_value",
)

_MEASUREMENT_ALIASES = {
    "pk-pk": "vpp",
    "pkpk": "vpp",
    "freq": "frequency",
    "acrms": "ac_rms",
    "vrms_ac": "ac_rms",
    "min": "minimum",
    "vmin": "minimum",
    "max": "maximum",
    "vmax": "maximum",
    "xmax": "x_at_max",
    "x-at-max": "x_at_max",
    "xmin": "x_at_min",
    "x-at-min": "x_at_min",
    "risetime": "rise_time",
    "rise-time": "rise_time",
    "falltime": "fall_time",
    "fall-time": "fall_time",
    "vamp": "amplitude",
    "vtop": "top",
    "vbase": "base",
    "pwidth": "positive_width",
    "positive-width": "positive_width",
    "pwid": "positive_width",
    "nwidth": "negative_width",
    "negative-width": "negative_width",
    "nwid": "negative_width",
    "duty": "duty_cycle",
    "dutycycle": "duty_cycle",
    "duty-cycle": "duty_cycle",
    "nduty": "negative_duty_cycle",
    "negative-duty": "negative_duty_cycle",
    "negative-duty-cycle": "negative_duty_cycle",
    "pedges": "positive_edges",
    "positive-edges": "positive_edges",
    "nedges": "negative_edges",
    "negative-edges": "negative_edges",
    "ppulses": "positive_pulses",
    "positive-pulses": "positive_pulses",
    "npulses": "negative_pulses",
    "negative-pulses": "negative_pulses",
    "yatx": "y_at_x",
    "y-at-x": "y_at_x",
    "vtime": "y_at_x",
    "y_at_time": "y_at_x",
    "y-at-time": "y_at_x",
    "tedge": "time_at_edge",
    "time-at-edge": "time_at_edge",
    "tvalue": "time_at_value",
    "time-at-value": "time_at_value",
    "time_at_level": "time_at_value",
    "time-at-level": "time_at_value",
}

_MEASUREMENT_UNITS = {
    "vpp": "V",
    "frequency": "Hz",
    "period": "s",
    "vavg": "V",
    "vrms": "V",
    "ac_rms": "V",
    "minimum": "V",
    "maximum": "V",
    "x_at_max": "s",
    "x_at_min": "s",
    "rise_time": "s",
    "fall_time": "s",
    "amplitude": "V",
    "top": "V",
    "base": "V",
    "overshoot": "%",
    "preshoot": "%",
    "positive_width": "s",
    "negative_width": "s",
    "duty_cycle": "%",
    "negative_duty_cycle": "%",
    "area": "V*s",
    "positive_edges": "count",
    "negative_edges": "count",
    "positive_pulses": "count",
    "negative_pulses": "count",
    "y_at_x": "V",
    "time_at_edge": "s",
    "time_at_value": "s",
    "phase": "deg",
    "delay": "s",
}

SINGLE_CHANNEL_MEASUREMENT_ITEMS = (
    tuple(_MEASUREMENT_QUERY_TEMPLATES) + _PARAMETERIZED_MEASUREMENT_ITEMS
)
PAIR_MEASUREMENT_ITEMS = tuple(_PAIR_MEASUREMENT_QUERY_TEMPLATES)
SUPPORTED_MEASUREMENT_ITEMS = SINGLE_CHANNEL_MEASUREMENT_ITEMS + PAIR_MEASUREMENT_ITEMS
MEASUREMENT_ITEM_CHOICES = SUPPORTED_MEASUREMENT_ITEMS + tuple(_MEASUREMENT_ALIASES)
MEASUREMENT_WINDOW_CHOICES = ("main", "zoom", "auto", "gate")


@dataclass(frozen=True)
class MeasurementResult:
    """Parsed result from one read-only measurement query."""

    item: str
    channel: int
    value: float | None
    raw_value: str
    valid: bool
    unit: str
    reason: str | None = None
    reference_channel: int | None = None


@dataclass(frozen=True)
class MeasurementResultsItem:
    """One conservatively parsed front-panel measurement result."""

    label: str
    value: float | str


@dataclass(frozen=True)
class MeasurementResultsStatisticsItem:
    """One parsed front-panel measurement statistics result."""

    label: str
    current: float | None
    minimum: float | None
    maximum: float | None
    mean: float | None
    stddev: float | None
    count: int | None


@dataclass(frozen=True)
class MeasurementResultsDump:
    """Raw and best-effort parsed front-panel measurement results."""

    raw: str
    items: tuple[MeasurementResultsItem, ...]
    statistics_items: tuple[MeasurementResultsStatisticsItem, ...] = ()


@dataclass(frozen=True)
class MeasurementStatisticsRecord:
    """One front-panel statistics row returned by :MEASure:RESults?."""

    item: str
    current: float | None
    minimum: float | None
    maximum: float | None
    mean: float | None
    stddev: float | None
    count: int | None
    raw_values: tuple[str, ...]


@dataclass(frozen=True)
class MeasurementStatisticsResult:
    """Parsed front-panel measurement statistics."""

    channel: int
    mode: str
    records: tuple[MeasurementStatisticsRecord, ...]
    raw_response: str


@dataclass(frozen=True)
class MeasurementStatisticsState:
    """Instrument-side advanced measurement statistics settings."""

    mode: str
    display_enabled: bool
    max_count: int | None
    relative_stddev_enabled: bool
    raw_mode: str
    raw_display_enabled: str
    raw_max_count: str
    raw_relative_stddev_enabled: str


@dataclass(frozen=True)
class MeasurementShowState:
    enabled: bool
    raw_enabled: str


@dataclass(frozen=True)
class MeasurementSourceState:
    source1: str
    source2: str | None
    source1_channel: int | None
    source2_channel: int | None
    raw: str


@dataclass(frozen=True)
class MeasurementWindowState:
    window: str
    raw_window: str


class MeasurementController:
    """Read-only measurement query controls."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def clear(self) -> None:
        validate_measurements_supported(self.capabilities)
        self.scpi.write(measurement_clear_command())

    def set_show(self, enabled: bool = True) -> None:
        validate_measurements_supported(self.capabilities)
        if not enabled and self.capabilities.series != "4000X":
            raise ParameterValidationError(
                f"measure-show OFF is not supported by {self.capabilities.series} models"
            )
        self.scpi.write(measurement_show_command(enabled))

    def set_show_on(self) -> None:
        self.set_show(True)

    def query_show(self) -> MeasurementShowState:
        validate_measurements_supported(self.capabilities)
        raw = self.scpi.query(measurement_show_query()).strip()
        return MeasurementShowState(parse_measurement_show(raw), raw)

    def set_source(self, source1_channel: int, source2_channel: int | None = None) -> None:
        self.scpi.write(
            measurement_source_command(
                source1_channel, source2_channel, capabilities=self.capabilities
            )
        )

    def query_source(self) -> MeasurementSourceState:
        validate_measurements_supported(self.capabilities)
        raw = self.scpi.query(measurement_source_query()).strip()
        return parse_measurement_source(raw)

    def set_window(self, window: str) -> None:
        validate_measurements_supported(self.capabilities)
        self.scpi.write(measurement_window_command(window))

    def query_window(self) -> MeasurementWindowState:
        validate_measurements_supported(self.capabilities)
        raw = self.scpi.query(measurement_window_query()).strip()
        return MeasurementWindowState(parse_measurement_window(raw), raw)

    def query(
        self,
        channel: int,
        item: str,
        *,
        time_s: float | None = None,
        level: float | None = None,
        slope: str | None = None,
        occurrence: int | None = None,
    ) -> MeasurementResult:
        """Query one measurement without changing acquisition or display state."""

        channel = validate_analog_channel(channel, self.capabilities)
        validate_measurements_supported(self.capabilities)
        item = normalize_measurement_item(item)
        raw = self.scpi.query(
            measurement_query(
                item,
                channel,
                capabilities=self.capabilities,
                time_s=time_s,
                level=level,
                slope=slope,
                occurrence=occurrence,
            )
        )
        return parse_measurement_result(raw, item=item, channel=channel)

    def query_pair(
        self,
        source_channel: int,
        reference_channel: int,
        item: str,
    ) -> MeasurementResult:
        """Query one measurement that compares two analog channels."""

        source_channel, reference_channel = _validate_channel_pair(
            source_channel, reference_channel, self.capabilities
        )
        validate_measurements_supported(self.capabilities)
        item = normalize_measurement_item(item)
        raw = self.scpi.query(
            pair_measurement_query(
                item,
                source_channel,
                reference_channel,
                capabilities=self.capabilities,
            )
        )
        return parse_measurement_result(
            raw,
            item=item,
            channel=source_channel,
            reference_channel=reference_channel,
        )

    def query_results(self) -> MeasurementResultsDump:
        """Query displayed front-panel results without changing measurement state."""

        validate_measure_results_dump_supported(self.capabilities)
        return parse_measurement_results_dump(
            self.scpi.query(measurement_results_query())
        )

    def statistics(
        self,
        channel: int,
        items: Sequence[str],
        *,
        mode: str = "all",
        reset: bool = False,
        max_count: int | None = None,
        settle_seconds: float | None = None,
    ) -> MeasurementStatisticsResult:
        channel = validate_analog_channel(channel, self.capabilities)
        validate_measure_statistics_supported(self.capabilities)
        normalized_items = validate_statistics_items(items)
        mode = normalize_statistics_mode(mode)
        if max_count is not None:
            max_count = validate_statistics_max_count(max_count)
        if settle_seconds is not None:
            settle_seconds = validate_statistics_settle_seconds(settle_seconds)

        self.scpi.write(":MEASure:CLEar")
        self.scpi.write(f":MEASure:SOURce CHANnel{channel}")
        for item in normalized_items:
            self.scpi.write(statistics_install_command(item))
        if reset:
            self.scpi.write(":MEASure:STATistics:RESet")
        if max_count is not None:
            self.scpi.write(measurement_statistics_max_count_command(max_count))
        self.scpi.write(f":MEASure:STATistics {statistics_mode_scpi(mode)}")
        if settle_seconds:
            time.sleep(settle_seconds)
        raw = self.scpi.query(":MEASure:RESults?")
        return parse_statistics_results(
            raw,
            channel=channel,
            items=normalized_items,
            mode=mode,
        )

    def query_statistics_state(self) -> MeasurementStatisticsState:
        validate_measure_statistics_supported(self.capabilities)
        raw_mode = self.scpi.query(measurement_statistics_mode_query()).strip()
        raw_display = self.scpi.query(measurement_statistics_display_query()).strip()
        raw_max_count = self.scpi.query(measurement_statistics_max_count_query()).strip()
        raw_rsd = self.scpi.query(measurement_statistics_relative_stddev_query()).strip()
        return MeasurementStatisticsState(
            mode=parse_statistics_mode(raw_mode),
            display_enabled=parse_statistics_boolean(raw_display, "display"),
            max_count=parse_statistics_max_count(raw_max_count),
            relative_stddev_enabled=parse_statistics_boolean(raw_rsd, "RSDeviation"),
            raw_mode=raw_mode,
            raw_display_enabled=raw_display,
            raw_max_count=raw_max_count,
            raw_relative_stddev_enabled=raw_rsd,
        )

    def set_statistics_mode(self, mode: str) -> None:
        validate_measure_statistics_supported(self.capabilities)
        self.scpi.write(measurement_statistics_mode_command(mode))

    def set_statistics_display(self, enabled: bool) -> None:
        validate_measure_statistics_supported(self.capabilities)
        self.scpi.write(measurement_statistics_display_command(enabled))

    def set_statistics_max_count(self, value: int | None) -> None:
        validate_measure_statistics_supported(self.capabilities)
        self.scpi.write(measurement_statistics_max_count_command(value))

    def set_statistics_relative_stddev(self, enabled: bool) -> None:
        validate_measure_statistics_supported(self.capabilities)
        self.scpi.write(measurement_statistics_relative_stddev_command(enabled))

    def reset_statistics(self) -> None:
        validate_measure_statistics_supported(self.capabilities)
        self.scpi.write(":MEASure:STATistics:RESet")

    def increment_statistics(self) -> None:
        validate_measure_statistics_supported(self.capabilities)
        self.scpi.write(":MEASure:STATistics:INCRement")


def measurement_clear_command() -> str:
    return ":MEASure:CLEar"


def measurement_results_query() -> str:
    return ":MEASure:RESults?"


def measurement_show_command(enabled: bool = True) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("measure-show enabled value must be a boolean.")
    return ":MEASure:SHOW ON" if enabled else ":MEASure:SHOW OFF"


def measurement_show_query() -> str:
    return ":MEASure:SHOW?"


def parse_measurement_show(raw: str) -> bool:
    normalized = raw.strip().upper()
    if normalized in {"1", "+1", "ON"}:
        return True
    if normalized in {"0", "+0", "OFF"}:
        return False
    raise MeasurementResponseError(
        f"Could not parse measurement show response: {raw!r}"
    )


def measurement_source_command(
    source1_channel: int,
    source2_channel: int | None = None,
    *,
    capabilities: ScopeCapabilities,
) -> str:
    validate_measurements_supported(capabilities)
    source1_channel = validate_analog_channel(source1_channel, capabilities)
    token = f"CHANnel{source1_channel}"
    if source2_channel is not None:
        source2_channel = validate_analog_channel(source2_channel, capabilities)
        token += f",CHANnel{source2_channel}"
    return f":MEASure:SOURce {token}"


def measurement_source_query() -> str:
    return ":MEASure:SOURce?"


def parse_measurement_source(raw: str) -> MeasurementSourceState:
    value = raw.strip()
    parts = [part.strip() for part in value.split(",")]
    if len(parts) not in {1, 2} or any(not part for part in parts):
        raise MeasurementResponseError(
            f"Could not parse measurement source response: {raw!r}"
        )
    parsed = [_parse_measurement_source_token(part) for part in parts]
    return MeasurementSourceState(
        source1=parsed[0][0],
        source2=parsed[1][0] if len(parsed) == 2 else None,
        source1_channel=parsed[0][1],
        source2_channel=parsed[1][1] if len(parsed) == 2 else None,
        raw=value,
    )


def _parse_measurement_source_token(value: str) -> tuple[str, int | None]:
    normalized = value.strip().upper()
    for prefix in ("CHANNEL", "CHAN"):
        if normalized.startswith(prefix):
            suffix = normalized[len(prefix) :]
            if suffix.isdigit() and int(suffix) >= 1:
                channel = int(suffix)
                return f"CHANnel{channel}", channel
    return value.strip(), None


def normalize_measurement_window(window: str) -> str:
    normalized = str(window).strip().upper()
    aliases = {"MAI": "MAIN", "ZOO": "ZOOM", "AUT": "AUTO", "GAT": "GATE"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"MAIN", "ZOOM", "AUTO", "GATE"}:
        raise ParameterValidationError(
            "measurement window must be one of: main, zoom, auto, gate."
        )
    return normalized


def measurement_window_command(window: str) -> str:
    return f":MEASure:WINDow {normalize_measurement_window(window)}"


def measurement_window_query() -> str:
    return ":MEASure:WINDow?"


def parse_measurement_window(raw: str) -> str:
    try:
        return normalize_measurement_window(raw)
    except ParameterValidationError as exc:
        raise MeasurementResponseError(
            f"Could not parse measurement window response: {raw!r}"
        ) from exc


def normalize_measurement_item(item: str) -> str:
    """Normalize a user-facing measurement item."""

    normalized = item.strip().lower()
    normalized = _MEASUREMENT_ALIASES.get(normalized, normalized)
    if (
        normalized not in _MEASUREMENT_QUERY_TEMPLATES
        and normalized not in _PARAMETERIZED_MEASUREMENT_ITEMS
        and normalized not in _PAIR_MEASUREMENT_QUERY_TEMPLATES
    ):
        supported = ", ".join(MEASUREMENT_ITEM_CHOICES)
        raise ParameterValidationError(f"measurement item must be one of: {supported}.")
    return normalized


def validate_statistics_items(items: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(normalize_measurement_item(item) for item in items)
    if not normalized:
        raise ParameterValidationError("--items must contain at least one measurement item.")
    unsupported = [
        item
        for item in normalized
        if item in _PARAMETERIZED_MEASUREMENT_ITEMS or item in _PAIR_MEASUREMENT_QUERY_TEMPLATES
    ]
    if unsupported:
        joined = ", ".join(unsupported)
        raise ParameterValidationError(
            f"measure-stats supports only non-parameterized single-channel items; rejected: {joined}."
        )
    return normalized


def normalize_statistics_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in {"all", "current", "min", "max", "mean", "stddev", "count"}:
        raise ParameterValidationError(
            "--mode must be all, current, min, max, mean, stddev, or count."
        )
    return normalized


def statistics_mode_scpi(mode: str) -> str:
    return {
        "all": "ON",
        "current": "CURRent",
        "min": "MINimum",
        "max": "MAXimum",
        "mean": "MEAN",
        "stddev": "STDDev",
        "count": "COUNt",
    }[normalize_statistics_mode(mode)]


def parse_statistics_mode(raw: str) -> str:
    normalized = raw.strip().upper()
    aliases = {
        "ON": "all",
        "ALL": "all",
        "CURRENT": "current",
        "CURR": "current",
        "MINIMUM": "min",
        "MIN": "min",
        "MAXIMUM": "max",
        "MAX": "max",
        "MEAN": "mean",
        "STDDEV": "stddev",
        "STDD": "stddev",
        "SDEV": "stddev",
        "COUNT": "count",
        "COUN": "count",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise MeasurementResponseError(
            f"Could not parse measurement statistics mode response: {raw!r}"
        ) from exc


def measurement_statistics_mode_command(mode: str) -> str:
    return f":MEASure:STATistics {statistics_mode_scpi(mode)}"


def measurement_statistics_mode_query() -> str:
    return ":MEASure:STATistics?"


def measurement_statistics_display_command(enabled: bool) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("statistics display enabled value must be a boolean.")
    return f":MEASure:STATistics:DISPlay {'ON' if enabled else 'OFF'}"


def measurement_statistics_display_query() -> str:
    return ":MEASure:STATistics:DISPlay?"


def measurement_statistics_max_count_command(value: int | None) -> str:
    token = "INFinite" if value is None else str(validate_statistics_max_count(value))
    return f":MEASure:STATistics:MCOUnt {token}"


def measurement_statistics_max_count_query() -> str:
    return ":MEASure:STATistics:MCOUnt?"


def parse_statistics_max_count(raw: str) -> int | None:
    normalized = raw.strip().upper()
    if normalized in {"INF", "INFINITE", "INFINITY"}:
        return None
    try:
        value = int(normalized)
    except ValueError as exc:
        raise MeasurementResponseError(
            f"Could not parse measurement statistics maximum count response: {raw!r}"
        ) from exc
    try:
        return validate_statistics_max_count(value)
    except ParameterValidationError as exc:
        raise MeasurementResponseError(
            f"Could not parse measurement statistics maximum count response: {raw!r}"
        ) from exc


def measurement_statistics_relative_stddev_command(enabled: bool) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("RSDeviation enabled value must be a boolean.")
    return f":MEASure:STATistics:RSDeviation {'ON' if enabled else 'OFF'}"


def measurement_statistics_relative_stddev_query() -> str:
    return ":MEASure:STATistics:RSDeviation?"


def parse_statistics_boolean(raw: str, setting: str) -> bool:
    normalized = raw.strip().upper()
    if normalized in {"1", "+1", "ON"}:
        return True
    if normalized in {"0", "+0", "OFF"}:
        return False
    raise MeasurementResponseError(
        f"Could not parse measurement statistics {setting} response: {raw!r}"
    )


def statistics_install_command(item: str) -> str:
    item = normalize_measurement_item(item)
    if item not in _MEASUREMENT_QUERY_TEMPLATES:
        raise ParameterValidationError(
            f"{item} cannot be installed as a single-channel statistics measurement."
        )
    query = _MEASUREMENT_QUERY_TEMPLATES[item]
    command = query.replace("?", "", 1).split(" ", 1)[0]
    return command


def validate_statistics_max_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ParameterValidationError("maximum statistics count must be an integer.")
    if not 2 <= value <= 2000:
        raise ParameterValidationError("maximum statistics count must be between 2 and 2000.")
    return value


def validate_statistics_settle_seconds(value: float) -> float:
    if not math.isfinite(value) or value < 0:
        raise ParameterValidationError("--settle-seconds must be a non-negative finite number.")
    return value


def measurement_query(
    item: str,
    channel: int,
    *,
    capabilities: ScopeCapabilities | None = None,
    time_s: float | None = None,
    level: float | None = None,
    slope: str | None = None,
    occurrence: int | None = None,
) -> str:
    """Build a read-only measurement query for one analog channel."""

    item = normalize_measurement_item(item)
    if capabilities is not None:
        validate_measurements_supported(capabilities)
    if item == "area":
        _validate_area_measurement_supported(capabilities)
    if item in _PARAMETERIZED_MEASUREMENT_ITEMS:
        return _parameterized_measurement_query(
            item,
            channel,
            capabilities=capabilities,
            time_s=time_s,
            level=level,
            slope=slope,
            occurrence=occurrence,
        )
    if item in _PAIR_MEASUREMENT_QUERY_TEMPLATES:
        raise ParameterValidationError(
            f"{item} measurement requires source and reference channels."
        )
    _reject_parameterized_measurement_args(
        item,
        time_s=time_s,
        level=level,
        slope=slope,
        occurrence=occurrence,
    )
    return _MEASUREMENT_QUERY_TEMPLATES[item].format(channel=channel)


def pair_measurement_query(
    item: str,
    source_channel: int,
    reference_channel: int,
    *,
    capabilities: ScopeCapabilities | None = None,
    time_s: float | None = None,
    level: float | None = None,
    slope: str | None = None,
    occurrence: int | None = None,
) -> str:
    """Build a read-only measurement query for two analog channels."""

    item = normalize_measurement_item(item)
    if capabilities is not None:
        validate_measurements_supported(capabilities)
    if item not in _PAIR_MEASUREMENT_QUERY_TEMPLATES:
        raise ParameterValidationError(
            f"{item} measurement uses a single channel; use measurement_query()."
        )
    _reject_parameterized_measurement_args(
        item,
        time_s=time_s,
        level=level,
        slope=slope,
        occurrence=occurrence,
    )
    source_channel, reference_channel = _validate_channel_pair(
        source_channel, reference_channel, capabilities
    )
    if item == "delay":
        _validate_delay_supported(capabilities)
    return _PAIR_MEASUREMENT_QUERY_TEMPLATES[item].format(
        source_channel=source_channel,
        reference_channel=reference_channel,
    )


def is_pair_measurement_item(item: str) -> bool:
    """Return whether a supported measurement item needs two channels."""

    return normalize_measurement_item(item) in _PAIR_MEASUREMENT_QUERY_TEMPLATES


def measurement_unit(item: str) -> str:
    """Return the display unit for a supported measurement item."""

    return _MEASUREMENT_UNITS[normalize_measurement_item(item)]


def _parameterized_measurement_query(
    item: str,
    channel: int,
    *,
    capabilities: ScopeCapabilities | None,
    time_s: float | None,
    level: float | None,
    slope: str | None,
    occurrence: int | None,
) -> str:
    if item == "y_at_x":
        _reject_parameterized_measurement_args(
            item, time_s=None, level=level, slope=slope, occurrence=occurrence
        )
        if capabilities is None:
            raise ParameterValidationError(
                "y_at_x measurement requires known scope capabilities."
            )
        time_s = _require_finite_float(time_s, "--time", item)
        return f":MEASure:VTIMe? {_format_scpi_number(time_s)},CHANnel{channel}"

    if item == "time_at_edge":
        _reject_parameterized_measurement_args(item, time_s=time_s, level=level)
        signed_occurrence = _signed_occurrence(slope=slope, occurrence=occurrence)
        return f":MEASure:TEDGe? {signed_occurrence:+d},CHANnel{channel}"

    if item == "time_at_value":
        _reject_parameterized_measurement_args(item, time_s=time_s)
        level = _require_finite_float(level, "--level", item)
        signed_occurrence = _signed_occurrence(slope=slope, occurrence=occurrence)
        return (
            f":MEASure:TVALue? {_format_scpi_number(level)},"
            f"{signed_occurrence:+d},CHANnel{channel}"
        )

    raise AssertionError(f"Unhandled parameterized measurement item: {item}")


def _reject_parameterized_measurement_args(
    item: str,
    *,
    time_s: float | None = None,
    level: float | None = None,
    slope: str | None = None,
    occurrence: int | None = None,
) -> None:
    invalid = []
    if time_s is not None:
        invalid.append("--time")
    if level is not None:
        invalid.append("--level")
    if slope is not None:
        invalid.append("--slope")
    if occurrence is not None:
        invalid.append("--occurrence")
    if invalid:
        joined = ", ".join(invalid)
        raise ParameterValidationError(f"{joined} cannot be used with {item} measurement.")


def _require_finite_float(value: float | None, option_name: str, item: str) -> float:
    if value is None:
        raise ParameterValidationError(f"{item} measurement requires {option_name}.")
    if not math.isfinite(value):
        raise ParameterValidationError(f"{option_name} must be a finite number.")
    return value


def _signed_occurrence(*, slope: str | None, occurrence: int | None) -> int:
    if slope is None:
        slope = "positive"
    slope = slope.strip().lower()
    if slope not in {"positive", "negative"}:
        raise ParameterValidationError("--slope must be positive or negative.")
    if occurrence is None:
        occurrence = 1
    if not isinstance(occurrence, int):
        raise ParameterValidationError("--occurrence must be an integer.")
    if occurrence < 1:
        raise ParameterValidationError("--occurrence must be at least 1.")
    return occurrence if slope == "positive" else -occurrence


def _format_scpi_number(value: float) -> str:
    return f"{value:.12g}"


def _validate_channel_pair(
    source_channel: int,
    reference_channel: int,
    capabilities: ScopeCapabilities | None,
) -> tuple[int, int]:
    if capabilities is not None:
        source_channel = validate_analog_channel(source_channel, capabilities)
        reference_channel = validate_analog_channel(reference_channel, capabilities)
    if source_channel == reference_channel:
        raise ParameterValidationError(
            "source channel and reference channel must be different."
        )
    return source_channel, reference_channel


def _validate_delay_supported(capabilities: ScopeCapabilities | None) -> None:
    if capabilities is None:
        raise ParameterValidationError(
            "delay pair measurement requires known scope capabilities."
        )
    if not capabilities.supports_delay_measurement:
        raise ParameterValidationError(
            "delay pair measurement is not supported by this scope capability profile."
        )


def validate_measurements_supported(capabilities: ScopeCapabilities) -> None:
    if not capabilities.supports_measurements:
        raise ParameterValidationError(
            "measurements are not supported by this scope capability profile."
        )


def _validate_area_measurement_supported(
    capabilities: ScopeCapabilities | None,
) -> None:
    if capabilities is None:
        return
    if not capabilities.supports_area_measurement:
        raise ParameterValidationError(
            "area measurement is not supported by this scope capability profile."
        )


def validate_measure_statistics_supported(capabilities: ScopeCapabilities) -> None:
    validate_measurements_supported(capabilities)
    if not capabilities.supports_measure_statistics:
        raise ParameterValidationError(
            "measurement statistics are not supported by this scope capability profile."
        )


def validate_measure_results_dump_supported(capabilities: ScopeCapabilities) -> None:
    if not capabilities.supports_measure_results_dump:
        raise ParameterValidationError(
            "measure-results is not supported by this scope capability profile; "
            "2000X users should use individual measurement queries."
        )


def parse_measurement_results_dump(raw: str) -> MeasurementResultsDump:
    """Parse known result layouts while preserving ambiguous responses."""

    raw_response = raw.strip()
    if not raw_response:
        return MeasurementResultsDump(raw="", items=())

    tokens = [token.strip() for token in raw_response.split(",")]
    statistics_items = _parse_measurement_results_statistics(tokens)
    if statistics_items is not None:
        return MeasurementResultsDump(
            raw=raw_response,
            items=(),
            statistics_items=statistics_items,
        )

    if len(tokens) % 2 or any(
        not tokens[index] or _looks_numeric(tokens[index])
        for index in range(0, len(tokens), 2)
    ):
        return MeasurementResultsDump(raw=raw_response, items=())

    items = []
    for index in range(0, len(tokens), 2):
        raw_value = tokens[index + 1]
        try:
            value: float | str = float(raw_value)
            if not math.isfinite(value):
                value = raw_value
        except ValueError:
            value = raw_value
        items.append(MeasurementResultsItem(label=tokens[index], value=value))
    return MeasurementResultsDump(raw=raw_response, items=tuple(items))


def _parse_measurement_results_statistics(
    tokens: Sequence[str],
) -> tuple[MeasurementResultsStatisticsItem, ...] | None:
    if not tokens or len(tokens) % 7:
        return None

    items = []
    for index in range(0, len(tokens), 7):
        label = tokens[index]
        if not label:
            return None
        try:
            values = tuple(_parse_optional_float(token) for token in tokens[index + 1 : index + 6])
            count_value = _parse_optional_count(tokens[index + 6])
        except (ValueError, MeasurementResponseError):
            return None
        items.append(
            MeasurementResultsStatisticsItem(
                label=label,
                current=values[0],
                minimum=values[1],
                maximum=values[2],
                mean=values[3],
                stddev=values[4],
                count=count_value,
            )
        )
    return tuple(items)


def parse_measurement_result(
    raw: str,
    *,
    item: str,
    channel: int,
    reference_channel: int | None = None,
) -> MeasurementResult:
    """Parse a numeric measurement response, preserving invalid sentinels."""

    item = normalize_measurement_item(item)
    raw_value = raw.strip()
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise MeasurementResponseError(f"Could not parse measurement response: {raw!r}") from exc

    if not math.isfinite(value):
        raise MeasurementResponseError(f"Could not parse measurement response: {raw!r}")

    if abs(value) >= INVALID_MEASUREMENT_SENTINEL_ABS_MIN:
        return MeasurementResult(
            item=item,
            channel=channel,
            value=None,
            raw_value=raw_value,
            valid=False,
            unit=measurement_unit(item),
            reason=INVALID_MEASUREMENT_REASON,
            reference_channel=reference_channel,
        )

    return MeasurementResult(
        item=item,
        channel=channel,
        value=value,
        raw_value=raw_value,
        valid=True,
        unit=measurement_unit(item),
        reference_channel=reference_channel,
    )


def parse_statistics_results(
    raw: str,
    *,
    channel: int,
    items: Sequence[str],
    mode: str,
) -> MeasurementStatisticsResult:
    """Parse :MEASure:RESults? into one row per requested item.

    All mode returns item/current/min/max/mean/stddev/count records. Other
    modes return one value per requested item in requested order.
    """

    normalized_mode = normalize_statistics_mode(mode)
    tokens = tuple(token.strip().strip('"') for token in raw.split(",") if token.strip())
    requested = tuple(items)
    if normalized_mode != "all":
        if not tokens:
            return MeasurementStatisticsResult(
                channel=channel,
                mode=normalized_mode,
                records=(),
                raw_response=raw,
            )
        if len(tokens) != len(requested):
            raise MeasurementResponseError(
                f"Could not parse measurement statistics response: {raw!r}"
            )

        records = []
        for item, value in zip(requested, tokens):
            count = _parse_optional_count(value) if normalized_mode == "count" else None
            statistic = (
                None if normalized_mode == "count" else _parse_optional_float(value)
            )
            records.append(
                MeasurementStatisticsRecord(
                    item=item,
                    current=statistic if normalized_mode == "current" else None,
                    minimum=statistic if normalized_mode == "min" else None,
                    maximum=statistic if normalized_mode == "max" else None,
                    mean=statistic if normalized_mode == "mean" else None,
                    stddev=statistic if normalized_mode == "stddev" else None,
                    count=count,
                    raw_values=(value,),
                )
            )
        return MeasurementStatisticsResult(
            channel=channel,
            mode=normalized_mode,
            records=tuple(records),
            raw_response=raw,
        )

    records: list[MeasurementStatisticsRecord] = []
    index = 0
    while index < len(tokens):
        remaining = len(tokens) - index
        item = requested[len(records)] if len(records) < len(requested) else f"item_{len(records) + 1}"
        if remaining >= 7 and not _looks_numeric(tokens[index]):
            item = _normalize_statistics_result_label(tokens[index])
            values = tokens[index + 1 : index + 7]
            index += 7
        elif remaining >= 6:
            values = tokens[index : index + 6]
            index += 6
        else:
            raise MeasurementResponseError(
                f"Could not parse measurement statistics response: {raw!r}"
            )
        records.append(
            MeasurementStatisticsRecord(
                item=item,
                current=_parse_optional_float(values[0]),
                minimum=_parse_optional_float(values[1]),
                maximum=_parse_optional_float(values[2]),
                mean=_parse_optional_float(values[3]),
                stddev=_parse_optional_float(values[4]),
                count=_parse_optional_count(values[5]),
                raw_values=tuple(values),
            )
        )
    return MeasurementStatisticsResult(
        channel=channel,
        mode=normalized_mode,
        records=tuple(records),
        raw_response=raw,
    )


def _normalize_statistics_result_label(label: str) -> str:
    """Normalize front-panel labels returned by :MEASure:RESults?."""

    normalized = label.strip().lower()
    if normalized.endswith(")") and "(" in normalized:
        normalized = normalized.rsplit("(", 1)[0]
    normalized = normalized.replace(" ", "_")
    return normalize_measurement_item(normalized)


def _looks_numeric(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _parse_optional_float(value: str) -> float | None:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise MeasurementResponseError(f"Could not parse measurement statistics value: {value!r}")
    if abs(parsed) >= INVALID_MEASUREMENT_SENTINEL_ABS_MIN:
        return None
    return parsed


def _parse_optional_count(value: str) -> int | None:
    parsed = _parse_optional_float(value)
    if parsed is None:
        return None
    if not parsed.is_integer():
        raise MeasurementResponseError(
            f"Could not parse measurement statistics count: {value!r}"
        )
    return int(parsed)
