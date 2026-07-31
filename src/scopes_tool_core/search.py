"""Model-guarded basic waveform event search controls."""

from __future__ import annotations

from dataclasses import dataclass

from .capabilities import ScopeCapabilities
from .errors import ParameterValidationError, SearchResponseError
from .scpi import SCPIClient


SEARCH_MODES = (
    "serial1",
    "serial2",
    "edge",
    "glitch",
    "runt",
    "transition",
    "peak",
)

_SEARCH_MODE_COMMANDS = {
    "serial1": "SERial1",
    "serial2": "SERial2",
    "edge": "EDGE",
    "glitch": "GLITch",
    "runt": "RUNT",
    "transition": "TRANsition",
    "peak": "PEAK",
}

_SEARCH_MODE_READBACKS = {
    "SER1": "serial1",
    "SERIAL1": "serial1",
    "SER2": "serial2",
    "SERIAL2": "serial2",
    "EDGE": "edge",
    "GLIT": "glitch",
    "GLITCH": "glitch",
    "RUNT": "runt",
    "TRAN": "transition",
    "TRANSITION": "transition",
    "PEAK": "peak",
}


@dataclass(frozen=True)
class SearchState:
    enabled: bool
    raw_state: str | None = None

    def to_json(self) -> dict[str, object]:
        return {"enabled": self.enabled, "raw_state": self.raw_state}


@dataclass(frozen=True)
class SearchModeState:
    mode: str | None
    enabled: bool | None
    raw_mode: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "raw_mode": self.raw_mode,
        }


@dataclass(frozen=True)
class SearchCountState:
    count: int
    raw_count: str

    def to_json(self) -> dict[str, object]:
        return {"count": self.count, "raw_count": self.raw_count}


@dataclass(frozen=True)
class SearchEventState:
    event: int
    raw: str | None = None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {"event": self.event}
        if self.raw is not None:
            payload["raw"] = self.raw
        return payload


class SearchController:
    """Controller for Search Basic Pack v1."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure_state(self, enabled: bool) -> SearchState:
        require_search_basic(self.capabilities)
        self.scpi.write(search_state_command(enabled))
        return SearchState(enabled=enabled)

    def query_state(self) -> SearchState:
        require_search_basic(self.capabilities)
        raw = self.scpi.query(search_state_query()).strip()
        return SearchState(enabled=parse_search_state(raw), raw_state=raw)

    def configure_mode(self, mode: str) -> SearchModeState:
        canonical = validate_search_mode(mode, self.capabilities)
        self.scpi.write(search_state_command(True))
        self.scpi.write(search_mode_command(canonical))
        return SearchModeState(mode=canonical, enabled=True)

    def query_mode(self) -> SearchModeState:
        require_search_basic(self.capabilities)
        raw = self.scpi.query(search_mode_query()).strip()
        mode, enabled = parse_search_mode(raw)
        return SearchModeState(mode=mode, enabled=enabled, raw_mode=raw)

    def query_count(self) -> SearchCountState:
        require_search_basic(self.capabilities)
        return parse_search_count(self.scpi.query(search_count_query()))

    def set_event(self, event: int) -> SearchEventState:
        require_search_event_navigation(self.capabilities)
        canonical_event = validate_search_event(event)
        self.scpi.write(search_event_command(canonical_event))
        return SearchEventState(event=canonical_event)

    def query_event(self) -> SearchEventState:
        require_search_event_navigation(self.capabilities)
        raw = self.scpi.query(search_event_query()).strip()
        return parse_search_event(raw)


def search_state_command(enabled: bool) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("Search enabled value must be a boolean.")
    return f":SEARch:STATe {1 if enabled else 0}"


def search_state_query() -> str:
    return ":SEARch:STATe?"


def search_mode_command(mode: str) -> str:
    canonical = normalize_search_mode(mode)
    return f":SEARch:MODE {_SEARCH_MODE_COMMANDS[canonical]}"


def search_mode_query() -> str:
    return ":SEARch:MODE?"


def search_count_query() -> str:
    return ":SEARch:COUNt?"


def search_event_command(event: int) -> str:
    canonical_event = validate_search_event(event)
    return f":SEARch:EVENt {canonical_event}"


def search_event_query() -> str:
    return ":SEARch:EVENt?"


def validate_search_event(event: int) -> int:
    if isinstance(event, bool) or not isinstance(event, int) or event <= 0:
        raise ParameterValidationError("Search event must be a positive integer.")
    return event


def require_search_event_navigation(capabilities: ScopeCapabilities) -> None:
    if not capabilities.supports_search_event_navigation:
        raise ParameterValidationError(
            "Search event navigation is not supported by the selected model profile."
        )


def normalize_search_mode(mode: str) -> str:
    if not isinstance(mode, str) or mode not in _SEARCH_MODE_COMMANDS:
        raise ParameterValidationError(
            "Search mode must be one of: " + ", ".join(SEARCH_MODES) + "."
        )
    return mode


def validate_search_mode(mode: str, capabilities: ScopeCapabilities) -> str:
    require_search_basic(capabilities)
    canonical = normalize_search_mode(mode)
    if canonical not in capabilities.search_modes:
        raise ParameterValidationError(
            f"Search mode {canonical!r} is not supported by the selected "
            f"{capabilities.series} model profile."
        )
    return canonical


def require_search_basic(capabilities: ScopeCapabilities) -> None:
    if not capabilities.supports_search_basic:
        raise ParameterValidationError(
            "Search Basic Pack v1 is not supported by the selected model profile."
        )


def parse_search_state(raw: str) -> bool:
    normalized = raw.strip().upper()
    if normalized in {"1", "+1", "ON"}:
        return True
    if normalized in {"0", "+0", "OFF"}:
        return False
    raise SearchResponseError(f"Could not parse search state response: {raw!r}")


def parse_search_mode(raw: str) -> tuple[str | None, bool]:
    normalized = raw.strip().upper()
    if normalized == "OFF":
        return None, False
    try:
        return _SEARCH_MODE_READBACKS[normalized], True
    except KeyError as exc:
        raise SearchResponseError(f"Could not parse search mode response: {raw!r}") from exc


def parse_search_count(raw: str) -> SearchCountState:
    raw_count = raw.strip()
    try:
        count = int(raw_count)
    except ValueError as exc:
        raise SearchResponseError(
            f"Could not parse search count response: {raw!r}"
        ) from exc
    if count < 0:
        raise SearchResponseError(f"Could not parse search count response: {raw!r}")
    return SearchCountState(count=count, raw_count=raw_count)


def parse_search_event(raw: str) -> SearchEventState:
    raw_event = raw.strip()
    try:
        event = int(raw_event)
    except ValueError as exc:
        raise SearchResponseError(
            f"Could not parse search event response: {raw!r}"
        ) from exc
    if event <= 0:
        raise SearchResponseError(f"Could not parse search event response: {raw!r}")
    return SearchEventState(event=event, raw=raw_event)
