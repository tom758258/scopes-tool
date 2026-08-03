"""Segmented-memory query and configuration support."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re

from .acquisition import AcquisitionController
from .capabilities import ScopeCapabilities
from .errors import ParameterValidationError, SegmentedResponseError
from .scpi import SCPIClient


def segmented_mode_query() -> str:
    """Build the segmented-memory acquisition-mode query."""

    return ":ACQuire:MODE?"


def segmented_acquire_count_query() -> str:
    """Build the acquired-segment count query."""

    return ":ACQuire:SEGMented:COUNt?"


def segmented_waveform_count_query() -> str:
    """Build the waveform segmented-count query."""

    return ":WAVeform:SEGMented:COUNt?"


def segmented_index_query() -> str:
    """Build the selected acquired-segment index query."""

    return ":ACQuire:SEGMented:INDex?"


def segmented_index_command(index: int) -> str:
    """Build a validated selected-segment index command."""

    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise ParameterValidationError(
            "segmented-memory index must be an integer of at least 1."
        )
    return f":ACQuire:SEGMented:INDex {index}"


def segmented_time_tag_query() -> str:
    """Build the selected-segment time-tag query."""

    return ":WAVeform:SEGMented:TTAG?"


def segmented_mode_command(mode: str) -> str:
    """Build a validated segmented-memory acquisition-mode command."""

    try:
        token = {"segmented": "SEGMented", "realtime": "RTIMe"}[mode]
    except KeyError as exc:
        raise ParameterValidationError(
            "segmented memory mode must be segmented or realtime."
        ) from exc
    return f":ACQuire:MODE {token}"


def segmented_count_command(count: int) -> str:
    """Build the segmented-memory configured-count command."""

    return f":ACQuire:SEGMented:COUNt {count}"


_REALTIME_READBACKS = {"RTIM", "RTIME", "REALTIME"}
_SEGMENTED_READBACKS = {"SEGM", "SEGMENTED"}
_INTEGER_TOKEN = re.compile(r"^[+-]?\d+$")


def _response_error(label: str, raw: object) -> SegmentedResponseError:
    return SegmentedResponseError(
        f"Could not parse segmented-memory {label} response: {raw!r}"
    )


def parse_segmented_mode(raw: str) -> str:
    """Parse and normalize an acquisition mode readback."""

    value = raw.strip().upper()
    if value in _REALTIME_READBACKS:
        return "realtime"
    if value in _SEGMENTED_READBACKS:
        return "segmented"
    raise _response_error("mode", raw)


def parse_segmented_count(raw: str, *, acquired: bool) -> int:
    """Parse a configured or acquired segment count without range assumptions."""

    value = raw.strip()
    if not _INTEGER_TOKEN.fullmatch(value):
        raise _response_error("acquired count" if acquired else "configured count", raw)
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise _response_error("acquired count" if acquired else "configured count", raw) from exc
    if acquired and parsed < 0:
        raise _response_error("acquired count", raw)
    return parsed


def parse_segmented_configured_count(raw: str) -> int:
    """Parse the configured segment count readback."""

    return parse_segmented_count(raw, acquired=False)


def parse_segmented_acquired_count(raw: str) -> int:
    """Parse the acquired segment count readback."""

    return parse_segmented_count(raw, acquired=True)


def parse_segmented_index(raw: str) -> int:
    """Parse the selected segment index readback."""

    value = raw.strip()
    if not _INTEGER_TOKEN.fullmatch(value):
        raise _response_error("selected index", raw)
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise _response_error("selected index", raw) from exc
    if parsed <= 0:
        raise _response_error("selected index", raw)
    return parsed


def parse_segmented_time_tag(raw: str) -> float:
    """Parse a finite segmented time-tag readback in seconds."""

    value = raw.strip()
    if not value:
        raise _response_error("time tag", raw)
    try:
        parsed = float(value)
    except ValueError as exc:
        raise _response_error("time tag", raw) from exc
    if not math.isfinite(parsed):
        raise _response_error("time tag", raw)
    return parsed


@dataclass(frozen=True)
class SegmentedMemoryQueryResult:
    """Normalized and raw readback from the segmented-memory query path."""

    mode: str
    configured_segments: int | None
    acquired_segments: int | None
    selected_segment: int | None
    time_tag_s: float | None
    raw_mode: str
    raw_configured_segments: str | None
    raw_acquired_segments: str | None
    raw_selected_segment: str | None
    raw_time_tag: str | None

    def to_json(self) -> dict[str, object]:
        """Return the Common v2 result fields."""

        return asdict(self)


def ensure_segmented_memory_supported(
    capabilities: ScopeCapabilities | None,
) -> None:
    """Reject segmented-memory operations when the selected profile is unavailable."""

    if capabilities is None or not capabilities.supports_segmented_memory:
        raise ParameterValidationError(
            "segmented memory requires a registered profile with "
            "supports_segmented_memory enabled."
        )


def validate_segmented_count(
    count: object,
    capabilities: ScopeCapabilities | None,
) -> int:
    """Validate a configured segmented-memory count for a capability profile."""

    ensure_segmented_memory_supported(capabilities)
    if isinstance(count, bool) or not isinstance(count, int):
        raise ParameterValidationError("segmented memory count must be an integer.")
    assert capabilities is not None
    maximum = capabilities.segmented_max_segments
    if maximum < 2:
        raise ParameterValidationError(
            "segmented memory count is unavailable for this capability profile."
        )
    if count < 2 or count > maximum:
        raise ParameterValidationError(
            f"segmented memory count must be between 2 and {maximum}."
        )
    return count


class SegmentedMemoryController:
    """Query and configure segmented-memory acquisition state."""

    def __init__(
        self,
        scpi: SCPIClient,
        capabilities: ScopeCapabilities | None,
    ) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def enable(self, segments: int) -> None:
        """Enable segmented acquisition with an explicit configured count."""

        validated_segments = validate_segmented_count(segments, self.capabilities)
        acquisition_type = AcquisitionController(self.scpi).query_type()
        if acquisition_type == "average":
            raise ParameterValidationError(
                "segmented memory cannot be enabled while acquisition type is "
                "average; configure a non-average acquisition type first."
            )
        self.scpi.write(segmented_mode_command("segmented"))
        self.scpi.write(segmented_count_command(validated_segments))

    def disable(self) -> None:
        """Disable segmented acquisition without changing its configured count."""

        ensure_segmented_memory_supported(self.capabilities)
        self.scpi.write(segmented_mode_command("realtime"))

    def query_mode(self) -> str:
        """Query and normalize only the current acquisition mode."""

        ensure_segmented_memory_supported(self.capabilities)
        raw_mode = self.scpi.query(segmented_mode_query()).strip()
        return parse_segmented_mode(raw_mode)

    def query_acquired_count(self) -> int:
        """Query and parse the number of acquired segments."""

        ensure_segmented_memory_supported(self.capabilities)
        return parse_segmented_acquired_count(
            self.scpi.query(segmented_waveform_count_query())
        )

    def select_segment(self, index: int) -> None:
        """Select one acquired segment for subsequent waveform queries."""

        ensure_segmented_memory_supported(self.capabilities)
        self.scpi.write(segmented_index_command(index))

    def query_time_tag(self) -> float:
        """Query and parse the selected segment time tag in seconds."""

        ensure_segmented_memory_supported(self.capabilities)
        return parse_segmented_time_tag(self.scpi.query(segmented_time_tag_query()))

    def query(self) -> SegmentedMemoryQueryResult:
        """Query mode and conditionally available segmented-memory readbacks."""

        ensure_segmented_memory_supported(self.capabilities)

        raw_mode = self.scpi.query(segmented_mode_query()).strip()
        mode = parse_segmented_mode(raw_mode)
        if mode != "segmented":
            return SegmentedMemoryQueryResult(
                mode=mode,
                configured_segments=None,
                acquired_segments=None,
                selected_segment=None,
                time_tag_s=None,
                raw_mode=raw_mode,
                raw_configured_segments=None,
                raw_acquired_segments=None,
                raw_selected_segment=None,
                raw_time_tag=None,
            )

        raw_configured = self.scpi.query(segmented_acquire_count_query()).strip()
        configured = parse_segmented_configured_count(raw_configured)
        raw_acquired = self.scpi.query(segmented_waveform_count_query()).strip()
        acquired = parse_segmented_acquired_count(raw_acquired)
        if acquired == 0:
            return SegmentedMemoryQueryResult(
                mode=mode,
                configured_segments=configured,
                acquired_segments=acquired,
                selected_segment=None,
                time_tag_s=None,
                raw_mode=raw_mode,
                raw_configured_segments=raw_configured,
                raw_acquired_segments=raw_acquired,
                raw_selected_segment=None,
                raw_time_tag=None,
            )

        raw_selected = self.scpi.query(segmented_index_query()).strip()
        selected = parse_segmented_index(raw_selected)
        raw_time_tag = self.scpi.query(segmented_time_tag_query()).strip()
        time_tag_s = parse_segmented_time_tag(raw_time_tag)
        return SegmentedMemoryQueryResult(
            mode=mode,
            configured_segments=configured,
            acquired_segments=acquired,
            selected_segment=selected,
            time_tag_s=time_tag_s,
            raw_mode=raw_mode,
            raw_configured_segments=raw_configured,
            raw_acquired_segments=raw_acquired,
            raw_selected_segment=raw_selected,
            raw_time_tag=raw_time_tag,
        )
