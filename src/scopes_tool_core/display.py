"""Display label and annotation controls."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .capabilities import ScopeCapabilities
from .errors import ChannelResponseError, ParameterValidationError
from .scpi import SCPIClient


@dataclass(frozen=True)
class AnnotationState:
    """Current front-panel annotation state."""

    slot: int
    enabled: bool
    text: str
    color: str
    background: str
    x: int | None
    y: int | None


@dataclass(frozen=True)
class DisplayPersistence:
    """Current display persistence state."""

    mode: str | None
    seconds: float | None
    raw_value: str


class DisplayController:
    """Controls for display labels and annotations."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def set_label(self, enabled: bool) -> None:
        self.scpi.write(display_label_command(enabled))

    def query_label(self) -> bool:
        return parse_display_label(self.scpi.query(display_label_query()))

    def clear_display(self) -> None:
        self.scpi.write(display_clear_command())

    def set_persistence(self, value: str | float) -> None:
        self.scpi.write(display_persistence_command(value))

    def query_persistence(self) -> DisplayPersistence:
        raw = self.scpi.query(display_persistence_query())
        mode, seconds = parse_display_persistence(raw)
        return DisplayPersistence(mode=mode, seconds=seconds, raw_value=raw.strip())

    def set_intensity(self, value: int) -> None:
        self.scpi.write(display_intensity_command(value))

    def query_intensity(self) -> tuple[int, str]:
        raw = self.scpi.query(display_intensity_query())
        return parse_display_intensity(raw), raw.strip()

    def set_vectors_on(self) -> None:
        self.scpi.write(display_vectors_command(True))

    def query_vectors(self) -> tuple[bool, str]:
        raw = self.scpi.query(display_vectors_query())
        return parse_display_vectors(raw), raw.strip()

    def set_annotation_enabled(self, enabled: bool, *, slot: int = 1) -> None:
        slot = validate_annotation_slot(slot, self.capabilities)
        self.scpi.write(annotation_state_command(enabled, slot=slot, capabilities=self.capabilities))

    def clear_annotation(self, *, slot: int = 1) -> None:
        slot = validate_annotation_slot(slot, self.capabilities)
        self.scpi.write(annotation_clear_command(slot=slot, capabilities=self.capabilities))

    def set_annotation_text(self, text: str, *, slot: int = 1) -> None:
        slot = validate_annotation_slot(slot, self.capabilities)
        text = validate_annotation_text(text)
        self.scpi.write(annotation_text_command(text, slot=slot, capabilities=self.capabilities))

    def set_annotation_color(self, color: str, *, slot: int = 1) -> None:
        slot = validate_annotation_slot(slot, self.capabilities)
        color = normalize_annotation_color(color)
        self.scpi.write(annotation_color_command(color, slot=slot, capabilities=self.capabilities))

    def set_annotation_background(self, background: str, *, slot: int = 1) -> None:
        slot = validate_annotation_slot(slot, self.capabilities)
        background = normalize_annotation_background(background)
        self.scpi.write(annotation_background_command(background, slot=slot, capabilities=self.capabilities))

    def set_annotation_position(self, x: int | None = None, y: int | None = None, *, slot: int = 1) -> None:
        slot = validate_annotation_slot(slot, self.capabilities)
        if not self.capabilities.supports_annotation_position:
            raise ParameterValidationError("annotation position is supported only on indexed annotation models.")
        if x is not None:
            self.scpi.write(annotation_x_command(validate_annotation_x(x), slot=slot, capabilities=self.capabilities))
        if y is not None:
            self.scpi.write(annotation_y_command(validate_annotation_y(y), slot=slot, capabilities=self.capabilities))

    def query_annotation(self, *, slot: int = 1) -> AnnotationState:
        slot = validate_annotation_slot(slot, self.capabilities)
        enabled = parse_display_label(
            self.scpi.query(annotation_state_query(slot=slot, capabilities=self.capabilities))
        )
        text = parse_scpi_string(
            self.scpi.query(annotation_text_query(slot=slot, capabilities=self.capabilities))
        )
        color = parse_annotation_color(
            self.scpi.query(annotation_color_query(slot=slot, capabilities=self.capabilities))
        )
        background = parse_annotation_background(
            self.scpi.query(annotation_background_query(slot=slot, capabilities=self.capabilities))
        )
        x = y = None
        if self.capabilities.supports_annotation_position:
            x = parse_annotation_int(
                self.scpi.query(annotation_x_query(slot=slot, capabilities=self.capabilities)),
                "annotation x",
            )
            y = parse_annotation_int(
                self.scpi.query(annotation_y_query(slot=slot, capabilities=self.capabilities)),
                "annotation y",
            )
        return AnnotationState(slot=slot, enabled=enabled, text=text, color=color, background=background, x=x, y=y)


def display_label_command(enabled: bool) -> str:
    return f":DISPlay:LABel {'ON' if enabled else 'OFF'}"


def display_label_query() -> str:
    return ":DISPlay:LABel?"


def display_clear_command() -> str:
    return ":DISPlay:CLEar"


def display_persistence_command(value: str | float) -> str:
    mode, seconds = validate_display_persistence(value)
    if mode == "minimum":
        token = "MINimum"
    elif mode == "infinite":
        token = "INFinite"
    else:
        token = f"{seconds:.12g}"
    return f":DISPlay:PERSistence {token}"


def display_persistence_query() -> str:
    return ":DISPlay:PERSistence?"


def validate_display_persistence(value: str | float) -> tuple[str | None, float | None]:
    if isinstance(value, str):
        normalized = value.strip().lower()
        aliases = {
            "min": "minimum",
            "minimum": "minimum",
            "inf": "infinite",
            "infinite": "infinite",
        }
        if normalized in aliases:
            return aliases[normalized], None
        try:
            numeric = float(value)
        except ValueError as exc:
            raise ParameterValidationError(
                "display persistence must be minimum, infinite, or seconds in range 0.1-60.0."
            ) from exc
    else:
        numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.1 or numeric > 60.0:
        raise ParameterValidationError("display persistence seconds must be in range 0.1-60.0.")
    return None, numeric


def parse_display_persistence(raw: str) -> tuple[str | None, float | None]:
    normalized = raw.strip().upper()
    if normalized in {"MIN", "MINIMUM"}:
        return "minimum", None
    if normalized in {"INF", "INFINITE"}:
        return "infinite", None
    try:
        seconds = float(normalized)
    except ValueError as exc:
        raise ChannelResponseError(f"Could not parse display persistence response: {raw!r}") from exc
    if not math.isfinite(seconds):
        raise ChannelResponseError(f"Could not parse display persistence response: {raw!r}")
    return None, seconds


def display_intensity_command(value: int) -> str:
    return f":DISPlay:INTensity:WAVeform {validate_display_intensity(value)}"


def display_intensity_query() -> str:
    return ":DISPlay:INTensity:WAVeform?"


def validate_display_intensity(value: int) -> int:
    return _validate_int_range(value, "display intensity", 0, 100)


def parse_display_intensity(raw: str) -> int:
    try:
        value = int(float(raw.strip()))
    except ValueError as exc:
        raise ChannelResponseError(f"Could not parse display intensity response: {raw!r}") from exc
    return validate_display_intensity(value)


def display_vectors_command(enabled: bool) -> str:
    if not enabled:
        raise ParameterValidationError("display-vectors set OFF is not supported.")
    return ":DISPlay:VECTors ON"


def display_vectors_query() -> str:
    return ":DISPlay:VECTors?"


def parse_display_vectors(raw: str) -> bool:
    return parse_display_label(raw)


def parse_display_label(raw: str) -> bool:
    """Parse a display label query response."""

    normalized = raw.strip().upper()
    if normalized in {"1", "+1", "ON"}:
        return True
    if normalized in {"0", "+0", "OFF"}:
        return False
    raise ChannelResponseError(f"Could not parse display label response: {raw!r}")


def annotation_commands(
    *,
    capabilities: ScopeCapabilities,
    slot: int = 1,
    enabled: bool | None = None,
    clear: bool = False,
    text: str | None = None,
    color: str | None = None,
    background: str | None = None,
    x: int | None = None,
    y: int | None = None,
) -> list[str]:
    slot = validate_annotation_slot(slot, capabilities)
    commands: list[str] = []
    if clear:
        commands.append(annotation_clear_command(slot=slot, capabilities=capabilities))
    if text is not None:
        commands.append(annotation_text_command(text, slot=slot, capabilities=capabilities))
    if color is not None:
        commands.append(annotation_color_command(color, slot=slot, capabilities=capabilities))
    if background is not None:
        commands.append(annotation_background_command(background, slot=slot, capabilities=capabilities))
    if x is not None:
        commands.append(annotation_x_command(x, slot=slot, capabilities=capabilities))
    if y is not None:
        commands.append(annotation_y_command(y, slot=slot, capabilities=capabilities))
    if enabled is not None:
        commands.append(annotation_state_command(enabled, slot=slot, capabilities=capabilities))
    return commands


def annotation_query_commands(*, slot: int = 1, capabilities: ScopeCapabilities) -> list[str]:
    slot = validate_annotation_slot(slot, capabilities)
    commands = [
        annotation_state_query(slot=slot, capabilities=capabilities),
        annotation_text_query(slot=slot, capabilities=capabilities),
        annotation_color_query(slot=slot, capabilities=capabilities),
        annotation_background_query(slot=slot, capabilities=capabilities),
    ]
    if capabilities.supports_annotation_position:
        commands.extend(
            [
                annotation_x_query(slot=slot, capabilities=capabilities),
                annotation_y_query(slot=slot, capabilities=capabilities),
            ]
        )
    return commands


def annotation_state_command(enabled: bool, *, slot: int, capabilities: ScopeCapabilities) -> str:
    return f"{_annotation_root(slot, capabilities)} {'ON' if enabled else 'OFF'}"


def annotation_state_query(*, slot: int, capabilities: ScopeCapabilities) -> str:
    return f"{_annotation_root(slot, capabilities)}?"


def annotation_clear_command(*, slot: int, capabilities: ScopeCapabilities) -> str:
    return f'{_annotation_root(slot, capabilities)}:TEXT ""'


def annotation_text_command(text: str, *, slot: int, capabilities: ScopeCapabilities) -> str:
    return f'{_annotation_root(slot, capabilities)}:TEXT "{validate_annotation_text(text)}"'


def annotation_text_query(*, slot: int, capabilities: ScopeCapabilities) -> str:
    return f"{_annotation_root(slot, capabilities)}:TEXT?"


def annotation_color_command(color: str, *, slot: int, capabilities: ScopeCapabilities) -> str:
    return f"{_annotation_root(slot, capabilities)}:COLor {normalize_annotation_color(color)}"


def annotation_color_query(*, slot: int, capabilities: ScopeCapabilities) -> str:
    return f"{_annotation_root(slot, capabilities)}:COLor?"


def annotation_background_command(background: str, *, slot: int, capabilities: ScopeCapabilities) -> str:
    return f"{_annotation_root(slot, capabilities)}:BACKground {normalize_annotation_background(background)}"


def annotation_background_query(*, slot: int, capabilities: ScopeCapabilities) -> str:
    return f"{_annotation_root(slot, capabilities)}:BACKground?"


def annotation_x_command(x: int, *, slot: int, capabilities: ScopeCapabilities) -> str:
    if not capabilities.supports_annotation_position:
        raise ParameterValidationError("annotation x is supported only on indexed annotation models.")
    return f"{_annotation_root(slot, capabilities)}:X1Position {validate_annotation_x(x)}"


def annotation_x_query(*, slot: int, capabilities: ScopeCapabilities) -> str:
    if not capabilities.supports_annotation_position:
        raise ParameterValidationError("annotation x is supported only on indexed annotation models.")
    return f"{_annotation_root(slot, capabilities)}:X1Position?"


def annotation_y_command(y: int, *, slot: int, capabilities: ScopeCapabilities) -> str:
    if not capabilities.supports_annotation_position:
        raise ParameterValidationError("annotation y is supported only on indexed annotation models.")
    return f"{_annotation_root(slot, capabilities)}:Y1Position {validate_annotation_y(y)}"


def annotation_y_query(*, slot: int, capabilities: ScopeCapabilities) -> str:
    if not capabilities.supports_annotation_position:
        raise ParameterValidationError("annotation y is supported only on indexed annotation models.")
    return f"{_annotation_root(slot, capabilities)}:Y1Position?"


def validate_annotation_slot(slot: int, capabilities: ScopeCapabilities) -> int:
    if slot < 1 or slot > capabilities.annotation_slots:
        raise ParameterValidationError(
            f"annotation slot must be in range 1-{capabilities.annotation_slots}."
        )
    return slot


def validate_annotation_x(value: int) -> int:
    return _validate_int_range(value, "annotation x", 0, 800)


def validate_annotation_y(value: int) -> int:
    return _validate_int_range(value, "annotation y", 0, 480)


def validate_annotation_text(text: str) -> str:
    return _validate_ascii_text(text, "annotation text", 254)


def normalize_annotation_color(color: str) -> str:
    normalized = str(color).strip().upper()
    aliases = {"DIGITAL": "DIG", "MARKER": "MARK"}
    normalized = aliases.get(normalized, normalized)
    supported = {"CH1", "CH2", "CH3", "CH4", "DIG", "MATH", "REF", "MARK", "WHITE", "RED"}
    if normalized not in supported:
        raise ParameterValidationError(
            "annotation color must be one of: ch1, ch2, ch3, ch4, dig, math, ref, marker, white, red."
        )
    return normalized


def normalize_annotation_background(background: str) -> str:
    normalized = str(background).strip().upper()
    aliases = {"OPAQUE": "OPAQ", "INVERTED": "INV", "TRANSPARENT": "TRAN"}
    normalized = aliases.get(normalized, normalized)
    supported = {"OPAQ", "INV", "TRAN"}
    if normalized not in supported:
        raise ParameterValidationError(
            "annotation background must be one of: opaque, inverted, transparent."
        )
    return normalized


def parse_annotation_color(raw: str) -> str:
    normalized = str(raw).strip().upper()
    aliases = {"WHIT": "WHITE"}
    normalized = aliases.get(normalized, normalized)
    supported = {"CH1", "CH2", "CH3", "CH4", "DIG", "MATH", "REF", "MARK", "WHITE", "RED"}
    if normalized not in supported:
        raise ChannelResponseError(f"Could not parse annotation color response: {raw!r}")
    return normalized


def parse_annotation_background(raw: str) -> str:
    normalized = str(raw).strip().upper()
    supported = {"OPAQ", "INV", "TRAN"}
    if normalized not in supported:
        raise ChannelResponseError(f"Could not parse annotation background response: {raw!r}")
    return normalized


def parse_annotation_int(raw: str, setting_name: str) -> int:
    try:
        value = int(float(raw.strip()))
    except ValueError as exc:
        raise ChannelResponseError(f"Could not parse {setting_name} response: {raw!r}") from exc
    return value


def parse_scpi_string(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


def _annotation_root(slot: int, capabilities: ScopeCapabilities) -> str:
    validate_annotation_slot(slot, capabilities)
    if capabilities.supports_indexed_annotation:
        return f":DISPlay:ANNotation{slot}"
    return ":DISPlay:ANNotation"


def _validate_int_range(value: int, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError(f"{name} must be an integer.") from exc
    if parsed < minimum or parsed > maximum:
        raise ParameterValidationError(f"{name} must be in range {minimum}-{maximum}.")
    return parsed


def _validate_ascii_text(text: str, name: str, max_length: int) -> str:
    if not isinstance(text, str):
        raise ParameterValidationError(f"{name} must be text.")
    if len(text) > max_length:
        raise ParameterValidationError(f"{name} must be at most {max_length} characters.")
    for char in text:
        if char == '"' or ord(char) < 32 or ord(char) > 126:
            raise ParameterValidationError(
                f"{name} must be printable ASCII and must not contain double quotes."
            )
    return text
