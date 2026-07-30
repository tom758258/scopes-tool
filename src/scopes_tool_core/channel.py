"""Analog channel controls."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Literal

from .capabilities import ScopeCapabilities
from .errors import ChannelResponseError, ParameterValidationError
from .scpi import SCPIClient

ChannelImpedance = Literal["one_meg", "fifty"]
ChannelUnits = Literal["volt", "amp"]
_IMPEDANCE_NOT_SUPPORTED_2000X = (
    "DSO-X 2000X only supports one-meg input impedance; 50 ohm is not supported "
    "by the 2000X channel impedance spec."
)


@dataclass(frozen=True)
class ChannelSummaryEntry:
    """Read-only setup summary for one analog channel."""

    channel: int
    display: bool | None
    label: str | None
    scale: float | None
    range: float | None
    offset: float | None
    coupling: str | None
    impedance: ChannelImpedance | None
    invert: bool | None
    bandwidth_limit: bool | None
    units: ChannelUnits | None
    vernier: bool | None
    probe_ratio: float | None
    probe_skew: float | None

    def to_json(self) -> dict[str, object]:
        return {
            "channel": self.channel,
            "display": self.display,
            "label": self.label,
            "scale": self.scale,
            "range": self.range,
            "offset": self.offset,
            "coupling": self.coupling,
            "impedance": self.impedance,
            "invert": self.invert,
            "bandwidth_limit": self.bandwidth_limit,
            "units": self.units,
            "vernier": self.vernier,
            "probe_ratio": self.probe_ratio,
            "probe_skew": self.probe_skew,
        }


class ChannelController:
    """Controls for analog oscilloscope channels."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def set_display(self, channel: int, enabled: bool) -> None:
        """Turn one analog channel display on or off."""

        channel = validate_analog_channel(channel, self.capabilities)
        self.scpi.write(channel_display_command(channel, enabled))

    def query_display(self, channel: int) -> bool:
        """Query whether one analog channel display is enabled."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_display(self.scpi.query(channel_display_query(channel)))

    def set_scale(self, channel: int, volts_per_division: float) -> None:
        """Set one analog channel vertical scale in volts per division."""

        channel = validate_analog_channel(channel, self.capabilities)
        volts_per_division = validate_channel_scale(volts_per_division)
        self.scpi.write(channel_scale_command(channel, volts_per_division))

    def query_scale(self, channel: int) -> float:
        """Query one analog channel vertical scale in volts per division."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_float(self.scpi.query(channel_scale_query(channel)), "scale")

    def set_offset(self, channel: int, volts: float) -> None:
        """Set one analog channel vertical offset in volts."""

        channel = validate_analog_channel(channel, self.capabilities)
        volts = validate_channel_offset(volts)
        self.scpi.write(channel_offset_command(channel, volts))

    def query_offset(self, channel: int) -> float:
        """Query one analog channel vertical offset in volts."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_float(self.scpi.query(channel_offset_query(channel)), "offset")

    def set_coupling(self, channel: int, coupling: str) -> None:
        """Set one analog channel input coupling."""

        channel = validate_analog_channel(channel, self.capabilities)
        coupling = normalize_channel_coupling(coupling)
        self.scpi.write(channel_coupling_command(channel, coupling))

    def query_coupling(self, channel: int) -> str:
        """Query one analog channel input coupling."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_coupling(self.scpi.query(channel_coupling_query(channel)))

    def set_probe_ratio(self, channel: int, ratio: float) -> None:
        """Set one analog channel probe attenuation ratio."""

        channel = validate_analog_channel(channel, self.capabilities)
        ratio = validate_probe_ratio(ratio)
        self.scpi.write(channel_probe_ratio_command(channel, ratio))

    def query_probe_ratio(self, channel: int) -> float:
        """Query one analog channel probe attenuation ratio."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_float(
            self.scpi.query(channel_probe_ratio_query(channel)),
            "probe ratio",
        )

    def set_bandwidth_limit(self, channel: int, enabled: bool) -> None:
        """Turn one analog channel bandwidth limit on or off."""

        channel = validate_analog_channel(channel, self.capabilities)
        self.scpi.write(channel_bandwidth_limit_command(channel, enabled))

    def query_bandwidth_limit(self, channel: int) -> bool:
        """Query whether one analog channel bandwidth limit is enabled."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_bool(
            self.scpi.query(channel_bandwidth_limit_query(channel)),
            "bandwidth limit",
        )

    def set_impedance(self, channel: int, impedance: str) -> None:
        """Set one analog channel input impedance."""

        channel = validate_analog_channel(channel, self.capabilities)
        impedance = normalize_channel_impedance(impedance)
        validate_channel_impedance_supported(impedance, self.capabilities)
        self.scpi.write(channel_impedance_command(channel, impedance))

    def query_impedance(self, channel: int) -> ChannelImpedance:
        """Query one analog channel input impedance."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_impedance(self.scpi.query(channel_impedance_query(channel)))

    def set_invert(self, channel: int, enabled: bool) -> None:
        """Turn one analog channel inversion on or off."""

        channel = validate_analog_channel(channel, self.capabilities)
        self.scpi.write(channel_invert_command(channel, enabled))

    def query_invert(self, channel: int) -> bool:
        """Query whether one analog channel inversion is enabled."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_bool(self.scpi.query(channel_invert_query(channel)), "invert")

    def set_range(self, channel: int, volts: float) -> None:
        """Set one analog channel full-scale range in volts."""

        channel = validate_analog_channel(channel, self.capabilities)
        volts = validate_channel_range(volts)
        self.scpi.write(channel_range_command(channel, volts))

    def query_range(self, channel: int) -> float:
        """Query one analog channel full-scale range in volts."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_float(self.scpi.query(channel_range_query(channel)), "range")

    def set_units(self, channel: int, units: str) -> None:
        """Set one analog channel units."""

        channel = validate_analog_channel(channel, self.capabilities)
        units = normalize_channel_units(units)
        self.scpi.write(channel_units_command(channel, units))

    def query_units(self, channel: int) -> ChannelUnits:
        """Query one analog channel units."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_units(self.scpi.query(channel_units_query(channel)))

    def set_vernier(self, channel: int, enabled: bool) -> None:
        """Turn one analog channel vernier scaling on or off."""

        channel = validate_analog_channel(channel, self.capabilities)
        self.scpi.write(channel_vernier_command(channel, enabled))

    def query_vernier(self, channel: int) -> bool:
        """Query whether one analog channel vernier scaling is enabled."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_bool(self.scpi.query(channel_vernier_query(channel)), "vernier")

    def set_probe_skew(self, channel: int, seconds: float) -> None:
        """Set one analog channel probe skew in seconds."""

        channel = validate_analog_channel(channel, self.capabilities)
        seconds = validate_probe_skew(seconds)
        self.scpi.write(channel_probe_skew_command(channel, seconds))

    def query_probe_skew(self, channel: int) -> float:
        """Query one analog channel probe skew in seconds."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_float(
            self.scpi.query(channel_probe_skew_query(channel)),
            "probe skew",
        )

    def set_label(self, channel: int, text: str) -> None:
        """Set one analog channel label."""

        channel = validate_analog_channel(channel, self.capabilities)
        text = validate_channel_label(text, self.capabilities)
        self.scpi.write(channel_label_command(channel, text, self.capabilities))

    def query_label(self, channel: int) -> str:
        """Query one analog channel label."""

        channel = validate_analog_channel(channel, self.capabilities)
        return parse_channel_label(self.scpi.query(channel_label_query(channel)))

    def query_summary(self) -> tuple[ChannelSummaryEntry, ...]:
        """Query common setup fields for every analog channel."""

        entries = []
        for channel in range(1, self.capabilities.analog_channels + 1):
            entries.append(
                ChannelSummaryEntry(
                    channel=channel,
                    display=self._query_optional(lambda: self.query_display(channel)),
                    label=self._query_optional(lambda: self.query_label(channel)),
                    scale=self._query_optional(lambda: self.query_scale(channel)),
                    range=self._query_optional(lambda: self.query_range(channel)),
                    offset=self._query_optional(lambda: self.query_offset(channel)),
                    coupling=self._query_optional(lambda: self.query_coupling(channel)),
                    impedance=self._query_optional(lambda: self.query_impedance(channel)),
                    invert=self._query_optional(lambda: self.query_invert(channel)),
                    bandwidth_limit=self._query_optional(
                        lambda: self.query_bandwidth_limit(channel)
                    ),
                    units=self._query_optional(lambda: self.query_units(channel)),
                    vernier=self._query_optional(lambda: self.query_vernier(channel)),
                    probe_ratio=self._query_optional(
                        lambda: self.query_probe_ratio(channel)
                    ),
                    probe_skew=self._query_optional(lambda: self.query_probe_skew(channel)),
                )
            )
        return tuple(entries)

    @staticmethod
    def _query_optional(query: Callable[[], object]) -> object | None:
        try:
            return query()
        except ChannelResponseError:
            return None


def validate_analog_channel(channel: int, capabilities: ScopeCapabilities) -> int:
    """Validate an analog channel number against a capability profile."""

    if channel < 1:
        raise ParameterValidationError("channel must be at least 1.")

    max_channel = capabilities.analog_channels
    if channel > max_channel:
        raise ParameterValidationError(
            f"channel {channel} is not available on this scope; valid range is 1-{max_channel}."
        )
    return channel


def validate_channel_scale(volts_per_division: float) -> float:
    """Validate a vertical scale value before sending it to the instrument."""

    try:
        value = float(volts_per_division)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError("channel scale must be a number.") from exc
    if not math.isfinite(value):
        raise ParameterValidationError("channel scale must be a finite number.")
    if value <= 0:
        raise ParameterValidationError("channel scale must be greater than 0 V/div.")
    return value


def validate_channel_offset(volts: float) -> float:
    """Validate a vertical offset value before sending it to the instrument."""

    try:
        value = float(volts)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError("channel offset must be a number.") from exc
    if not math.isfinite(value):
        raise ParameterValidationError("channel offset must be a finite number.")
    return value


def validate_channel_range(volts: float) -> float:
    """Validate a full-scale range value before sending it to the instrument."""

    try:
        value = float(volts)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError("channel range must be a number.") from exc
    if not math.isfinite(value):
        raise ParameterValidationError("channel range must be a finite number.")
    if value <= 0:
        raise ParameterValidationError("channel range must be greater than 0 V.")
    return value


def validate_probe_ratio(ratio: float) -> float:
    """Validate a probe attenuation ratio before sending it to the instrument."""

    try:
        value = float(ratio)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError("probe ratio must be a number.") from exc
    if not math.isfinite(value):
        raise ParameterValidationError("probe ratio must be a finite number.")
    if value <= 0:
        raise ParameterValidationError("probe ratio must be greater than 0.")
    return value


def validate_probe_skew(seconds: float) -> float:
    """Validate a probe skew value before sending it to the instrument."""

    try:
        value = float(seconds)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError("probe skew must be a number.") from exc
    if not math.isfinite(value):
        raise ParameterValidationError("probe skew must be a finite number.")
    if value < -100e-9 or value > 100e-9:
        raise ParameterValidationError("probe skew must be between -100e-9 and 100e-9 seconds.")
    return value


def normalize_channel_coupling(coupling: str) -> str:
    """Normalize a supported analog channel input coupling."""

    normalized = str(coupling).strip().lower()
    if normalized in {"ac", "dc"}:
        return normalized
    raise ParameterValidationError("channel coupling must be 'ac' or 'dc'.")


def normalize_channel_impedance(impedance: str) -> ChannelImpedance:
    """Normalize a supported analog channel input impedance."""

    normalized = str(impedance).strip().lower().replace("-", "_")
    if normalized in {"one_meg", "onemeg", "1meg", "1m", "1_mohm"}:
        return "one_meg"
    if normalized in {"fifty", "50", "50ohm", "50_ohm"}:
        return "fifty"
    raise ParameterValidationError("channel impedance must be 'one-meg' or 'fifty'.")


def validate_channel_impedance_supported(
    impedance: ChannelImpedance, capabilities: ScopeCapabilities
) -> None:
    """Validate channel impedance against the detected capability profile."""

    if impedance == "fifty" and not capabilities.supports_50_ohm_impedance:
        if capabilities.series == "2000X":
            raise ParameterValidationError(_IMPEDANCE_NOT_SUPPORTED_2000X)
        raise ParameterValidationError(
            f"{capabilities.series} does not support 50 ohm input impedance."
        )


def normalize_channel_units(units: str) -> ChannelUnits:
    """Normalize supported analog channel units."""

    normalized = str(units).strip().lower()
    if normalized in {"volt", "volts", "v"}:
        return "volt"
    if normalized in {"amp", "amps", "ampere", "amperes", "a"}:
        return "amp"
    raise ParameterValidationError("channel units must be 'volt' or 'amp'.")


def channel_display_command(channel: int, enabled: bool) -> str:
    """Build the SCPI command for analog channel display control."""

    state = "ON" if enabled else "OFF"
    return f":CHANnel{channel}:DISPlay {state}"


def channel_display_query(channel: int) -> str:
    """Build the SCPI query for analog channel display state."""

    return f":CHANnel{channel}:DISPlay?"


def channel_scale_command(channel: int, volts_per_division: float) -> str:
    """Build the SCPI command for analog channel vertical scale."""

    return f":CHANnel{channel}:SCALe {_format_scpi_float(volts_per_division)}"


def channel_scale_query(channel: int) -> str:
    """Build the SCPI query for analog channel vertical scale."""

    return f":CHANnel{channel}:SCALe?"


def channel_offset_command(channel: int, volts: float) -> str:
    """Build the SCPI command for analog channel vertical offset."""

    return f":CHANnel{channel}:OFFSet {_format_scpi_float(volts)}"


def channel_offset_query(channel: int) -> str:
    """Build the SCPI query for analog channel vertical offset."""

    return f":CHANnel{channel}:OFFSet?"


def channel_coupling_command(channel: int, coupling: str) -> str:
    """Build the SCPI command for analog channel input coupling."""

    normalized = normalize_channel_coupling(coupling)
    return f":CHANnel{channel}:COUPling {normalized.upper()}"


def channel_coupling_query(channel: int) -> str:
    """Build the SCPI query for analog channel input coupling."""

    return f":CHANnel{channel}:COUPling?"


def channel_probe_ratio_command(channel: int, ratio: float) -> str:
    """Build the SCPI command for analog channel probe attenuation ratio."""

    ratio = validate_probe_ratio(ratio)
    return f":CHANnel{channel}:PROBe {_format_scpi_float(ratio)}"


def channel_probe_ratio_query(channel: int) -> str:
    """Build the SCPI query for analog channel probe attenuation ratio."""

    return f":CHANnel{channel}:PROBe?"


def channel_bandwidth_limit_command(channel: int, enabled: bool) -> str:
    """Build the SCPI command for analog channel bandwidth limit control."""

    state = "ON" if enabled else "OFF"
    return f":CHANnel{channel}:BWLimit {state}"


def channel_bandwidth_limit_query(channel: int) -> str:
    """Build the SCPI query for analog channel bandwidth limit state."""

    return f":CHANnel{channel}:BWLimit?"


def channel_impedance_command(channel: int, impedance: str) -> str:
    """Build the SCPI command for analog channel input impedance."""

    normalized = normalize_channel_impedance(impedance)
    scpi_value = "ONEMeg" if normalized == "one_meg" else "FIFTy"
    return f":CHANnel{channel}:IMPedance {scpi_value}"


def channel_impedance_query(channel: int) -> str:
    """Build the SCPI query for analog channel input impedance."""

    return f":CHANnel{channel}:IMPedance?"


def channel_invert_command(channel: int, enabled: bool) -> str:
    """Build the SCPI command for analog channel inversion."""

    state = "ON" if enabled else "OFF"
    return f":CHANnel{channel}:INVert {state}"


def channel_invert_query(channel: int) -> str:
    """Build the SCPI query for analog channel inversion."""

    return f":CHANnel{channel}:INVert?"


def channel_range_command(channel: int, volts: float) -> str:
    """Build the SCPI command for analog channel full-scale range."""

    volts = validate_channel_range(volts)
    return f":CHANnel{channel}:RANGe {_format_scpi_float(volts)}"


def channel_range_query(channel: int) -> str:
    """Build the SCPI query for analog channel full-scale range."""

    return f":CHANnel{channel}:RANGe?"


def channel_units_command(channel: int, units: str) -> str:
    """Build the SCPI command for analog channel units."""

    normalized = normalize_channel_units(units)
    scpi_value = "VOLT" if normalized == "volt" else "AMP"
    return f":CHANnel{channel}:UNITs {scpi_value}"


def channel_units_query(channel: int) -> str:
    """Build the SCPI query for analog channel units."""

    return f":CHANnel{channel}:UNITs?"


def channel_vernier_command(channel: int, enabled: bool) -> str:
    """Build the SCPI command for analog channel vernier scaling."""

    state = "ON" if enabled else "OFF"
    return f":CHANnel{channel}:VERNier {state}"


def channel_vernier_query(channel: int) -> str:
    """Build the SCPI query for analog channel vernier scaling."""

    return f":CHANnel{channel}:VERNier?"


def channel_probe_skew_command(channel: int, seconds: float) -> str:
    """Build the SCPI command for analog channel probe skew."""

    seconds = validate_probe_skew(seconds)
    return f":CHANnel{channel}:PROBe:SKEW {_format_scpi_float(seconds)}"


def channel_probe_skew_query(channel: int) -> str:
    """Build the SCPI query for analog channel probe skew."""

    return f":CHANnel{channel}:PROBe:SKEW?"


def channel_label_command(channel: int, text: str, capabilities: ScopeCapabilities) -> str:
    """Build the SCPI command for analog channel label text."""

    return f':CHANnel{channel}:LABel "{validate_channel_label(text, capabilities)}"'


def channel_label_query(channel: int) -> str:
    """Build the SCPI query for analog channel label text."""

    return f":CHANnel{channel}:LABel?"


def channel_summary_queries(capabilities: ScopeCapabilities) -> list[str]:
    """Build the ordered read-only query list for all analog channels."""

    queries = []
    for channel in range(1, capabilities.analog_channels + 1):
        queries.extend(
            [
                channel_display_query(channel),
                channel_label_query(channel),
                channel_scale_query(channel),
                channel_range_query(channel),
                channel_offset_query(channel),
                channel_coupling_query(channel),
                channel_impedance_query(channel),
                channel_invert_query(channel),
                channel_bandwidth_limit_query(channel),
                channel_units_query(channel),
                channel_vernier_query(channel),
                channel_probe_ratio_query(channel),
                channel_probe_skew_query(channel),
            ]
        )
    return queries


def parse_channel_display(raw: str) -> bool:
    """Parse a channel display query response."""

    return parse_channel_bool(raw, "display")


def parse_channel_bool(raw: str, setting_name: str) -> bool:
    """Parse a channel boolean query response."""

    normalized = raw.strip().upper()
    if normalized in {"1", "+1", "ON"}:
        return True
    if normalized in {"0", "+0", "OFF"}:
        return False
    raise ChannelResponseError(
        f"Could not parse channel {setting_name} response: {raw!r}"
    )


def parse_channel_coupling(raw: str) -> str:
    """Parse a channel coupling query response."""

    normalized = raw.strip().lower()
    if normalized in {"ac", "dc"}:
        return normalized
    raise ChannelResponseError(f"Could not parse channel coupling response: {raw!r}")


def parse_channel_impedance(raw: str) -> ChannelImpedance:
    """Parse a channel impedance query response."""

    normalized = raw.strip().upper()
    if normalized.startswith("ONEM"):
        return "one_meg"
    if normalized.startswith("FIFT"):
        return "fifty"
    raise ChannelResponseError(f"Could not parse channel impedance response: {raw!r}")


def parse_channel_units(raw: str) -> ChannelUnits:
    """Parse a channel units query response."""

    normalized = raw.strip().upper()
    if normalized == "VOLT":
        return "volt"
    if normalized.startswith("AMP"):
        return "amp"
    raise ChannelResponseError(f"Could not parse channel units response: {raw!r}")


def parse_channel_float(raw: str, setting_name: str) -> float:
    """Parse a numeric channel query response."""

    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise ChannelResponseError(
            f"Could not parse channel {setting_name} response: {raw!r}"
        ) from exc
    if not math.isfinite(value):
        raise ChannelResponseError(
            f"Could not parse channel {setting_name} response: {raw!r}"
        )
    return value


def validate_channel_label(text: str, capabilities: ScopeCapabilities) -> str:
    """Validate an analog channel label before sending it to the instrument."""

    if not isinstance(text, str):
        raise ParameterValidationError("channel label must be text.")
    max_length = capabilities.channel_label_max_length
    if len(text) > max_length:
        raise ParameterValidationError(
            f"channel label must be at most {max_length} characters for this model."
        )
    for char in text:
        if char == '"' or ord(char) < 32 or ord(char) > 126:
            raise ParameterValidationError(
                "channel label must be printable ASCII and must not contain double quotes."
            )
    return text


def parse_channel_label(raw: str) -> str:
    """Parse an analog channel label query response."""

    text = raw.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


def _format_scpi_float(value: float) -> str:
    return f"{value:.12g}"
