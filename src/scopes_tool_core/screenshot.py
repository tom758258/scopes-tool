"""Oscilloscope screen image capture helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .capabilities import ScopeCapabilities
from .errors import ParameterValidationError, ScreenshotResponseError
from .scpi import SCPIClient

SCREENSHOT_FORMAT = "PNG"
SCREENSHOT_PALETTE = "COLor"
SCREENSHOT_TIMEOUT_MS = 10000
DEFAULT_SCREENSHOT_BACKGROUND = "black"
SCREENSHOT_BACKGROUND_CHOICES = ("black", "white")
SCREENSHOT_FORMAT_CHOICES = ("png", "bmp", "bmp8bit")
HARDCOPY_PALETTE_CHOICES = ("color", "grayscale", "none")
HARDCOPY_LAYOUT_CHOICES = ("landscape", "portrait")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BMP_SIGNATURE = b"BM"


@dataclass(frozen=True)
class ScreenshotOptions:
    """Optional hardcopy controls for one screenshot capture."""

    format: str | None = None
    ink_saver: bool | None = None
    palette: str | None = None
    layout: str | None = None


@dataclass(frozen=True)
class HardcopyState:
    """Normalized hardcopy state with original instrument readbacks."""

    area: str
    ink_saver: bool
    palette: str
    layout: str
    format: str
    raw_area: str
    raw_ink_saver: str
    raw_palette: str
    raw_layout: str
    raw_format: str


@dataclass(frozen=True)
class ScreenshotCapture:
    """Captured oscilloscope screen image bytes."""

    format_name: str
    palette: str | None
    data: bytes
    background: str


class ScreenshotController:
    """Controls for current screen image capture."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def capture_png(
        self,
        *,
        background: str = DEFAULT_SCREENSHOT_BACKGROUND,
        timeout_ms: int = SCREENSHOT_TIMEOUT_MS,
    ) -> ScreenshotCapture:
        """Capture the current screen as a color PNG image."""

        if not self.capabilities.supports_screenshot:
            raise ParameterValidationError(
                f"screenshot capture is not enabled for {self.capabilities.series} capabilities."
            )

        background = normalize_screenshot_background(background)
        raw_values = self._capture_png_values(background, timeout_ms)
        data = screenshot_bytes_from_values(raw_values)
        return ScreenshotCapture(
            format_name=SCREENSHOT_FORMAT,
            palette=SCREENSHOT_PALETTE,
            data=data,
            background=background,
        )

    def capture(
        self,
        *,
        options: ScreenshotOptions,
        background: str = DEFAULT_SCREENSHOT_BACKGROUND,
        timeout_ms: int = SCREENSHOT_TIMEOUT_MS,
    ) -> ScreenshotCapture:
        """Capture a screen image with optional 4000X hardcopy controls."""

        if not self.capabilities.supports_screenshot:
            raise ParameterValidationError(
                f"screenshot capture is not enabled for {self.capabilities.series} capabilities."
            )
        normalized = normalize_screenshot_options(options)
        background = normalize_screenshot_background(background)
        if not self.capabilities.supports_screenshot_hardcopy_controls:
            raise ParameterValidationError(
                "Screenshot hardcopy controls require a 4000X capability profile."
            )

        if normalized.ink_saver is not None:
            self.scpi.write(hardcopy_inksaver_command(normalized.ink_saver))
        if normalized.palette is not None:
            self.scpi.write(hardcopy_palette_command(normalized.palette))
        if normalized.layout is not None:
            self.scpi.write(hardcopy_layout_command(normalized.layout))

        format_name = normalized.format or "png"
        if normalized.ink_saver is None:
            values = self._capture_values_with_temporary_background(
                background, timeout_ms, format_name
            )
            capture_background = background
        else:
            values = self._query_screenshot_data(timeout_ms, format_name)
            capture_background = "white" if normalized.ink_saver else "black"
        data = screenshot_bytes_from_values_for_format(values, format_name)
        return ScreenshotCapture(
            format_name=screenshot_format_scpi(format_name),
            palette=(
                hardcopy_palette_scpi(normalized.palette)
                if normalized.palette is not None
                else None
            ),
            data=data,
            background=capture_background,
        )

    def query_hardcopy_state(self) -> HardcopyState:
        """Query the 4000X hardcopy and screen-dump settings."""

        if not self.capabilities.supports_screenshot_hardcopy_controls:
            raise ParameterValidationError(
                "Screenshot hardcopy controls require a 4000X capability profile."
            )
        raw_area = self.scpi.query(hardcopy_area_query()).strip()
        raw_ink_saver = self.scpi.query(hardcopy_inksaver_query()).strip()
        raw_palette = self.scpi.query(hardcopy_palette_query()).strip()
        raw_layout = self.scpi.query(hardcopy_layout_query()).strip()
        raw_format = self.scpi.query(hardcopy_format_query()).strip()
        return HardcopyState(
            area=parse_hardcopy_area(raw_area),
            ink_saver=parse_hardcopy_inksaver(raw_ink_saver),
            palette=parse_hardcopy_palette(raw_palette),
            layout=parse_hardcopy_layout(raw_layout),
            format=parse_screenshot_format(raw_format),
            raw_area=raw_area,
            raw_ink_saver=raw_ink_saver,
            raw_palette=raw_palette,
            raw_layout=raw_layout,
            raw_format=raw_format,
        )

    def _capture_png_values(self, background: str, timeout_ms: int) -> Sequence[int]:
        original_inksaver = parse_hardcopy_inksaver(self.scpi.query(hardcopy_inksaver_query()))
        desired_inksaver = hardcopy_inksaver_for_background(background)
        if original_inksaver != desired_inksaver:
            self.scpi.write(hardcopy_inksaver_command(desired_inksaver))
        try:
            return self._query_screenshot_data(timeout_ms)
        finally:
            if original_inksaver != desired_inksaver:
                self.scpi.write(hardcopy_inksaver_command(original_inksaver))

    def _capture_values_with_temporary_background(
        self, background: str, timeout_ms: int, format_name: str
    ) -> Sequence[int]:
        original_inksaver = parse_hardcopy_inksaver(self.scpi.query(hardcopy_inksaver_query()))
        desired_inksaver = hardcopy_inksaver_for_background(background)
        if original_inksaver != desired_inksaver:
            self.scpi.write(hardcopy_inksaver_command(desired_inksaver))
        try:
            return self._query_screenshot_data(timeout_ms, format_name)
        finally:
            if original_inksaver != desired_inksaver:
                self.scpi.write(hardcopy_inksaver_command(original_inksaver))

    def _query_screenshot_data(
        self, timeout_ms: int, format_name: str | None = None
    ) -> Sequence[int]:
        original_timeout = self.scpi.timeout
        self.scpi.set_timeout(timeout_ms)
        try:
            command = (
                hardcopy_screen_dump_data_query(format_name)
                if format_name is not None
                else screenshot_data_query()
            )
            return self.scpi.query_binary_values(command, datatype="B")
        finally:
            self.scpi.set_timeout(original_timeout)


def normalize_screenshot_background(background: str) -> str:
    """Normalize a screenshot background option."""

    normalized = background.strip().lower()
    if normalized not in SCREENSHOT_BACKGROUND_CHOICES:
        supported = ", ".join(SCREENSHOT_BACKGROUND_CHOICES)
        raise ParameterValidationError(f"screenshot background must be one of: {supported}.")
    return normalized


def normalize_screenshot_options(options: ScreenshotOptions) -> ScreenshotOptions:
    """Validate and normalize screenshot hardcopy options without instrument access."""

    if options.ink_saver is not None and not isinstance(options.ink_saver, bool):
        raise ParameterValidationError("screenshot ink_saver must be a boolean.")
    return ScreenshotOptions(
        format=(normalize_screenshot_format(options.format) if options.format is not None else None),
        ink_saver=options.ink_saver,
        palette=(normalize_hardcopy_palette(options.palette) if options.palette is not None else None),
        layout=(normalize_hardcopy_layout(options.layout) if options.layout is not None else None),
    )


def normalize_screenshot_format(format_name: str) -> str:
    return _normalize_choice(format_name, SCREENSHOT_FORMAT_CHOICES, "screenshot format")


def normalize_hardcopy_palette(palette: str) -> str:
    return _normalize_choice(palette, HARDCOPY_PALETTE_CHOICES, "hardcopy palette")


def normalize_hardcopy_layout(layout: str) -> str:
    return _normalize_choice(layout, HARDCOPY_LAYOUT_CHOICES, "hardcopy layout")


def hardcopy_inksaver_for_background(background: str) -> bool:
    """Return the `:HARDcopy:INKSaver` state needed for a background option."""

    background = normalize_screenshot_background(background)
    return background == "white"


def hardcopy_inksaver_query() -> str:
    """Build the SCPI query for hardcopy ink saver state."""

    return ":HARDcopy:INKSaver?"


def hardcopy_inksaver_command(enabled: bool) -> str:
    """Build the SCPI command for hardcopy ink saver state."""

    return f":HARDcopy:INKSaver {'ON' if enabled else 'OFF'}"


def parse_hardcopy_inksaver(response: str) -> bool:
    """Parse a hardcopy ink saver query response."""

    value = _readback_value(response, ("INKS", "INKSAVER"))
    if value == "0":
        return False
    if value == "1":
        return True
    raise ScreenshotResponseError(f"Could not parse hardcopy ink saver response: {response!r}")


def hardcopy_area_query() -> str:
    return ":HARDcopy:AREA?"


def hardcopy_palette_query() -> str:
    return ":HARDcopy:PALette?"


def hardcopy_layout_query() -> str:
    return ":HARDcopy:LAYout?"


def hardcopy_format_query() -> str:
    return ":HCOPY:SDUMp:FORMat?"


def hardcopy_palette_command(palette: str) -> str:
    return f":HARDcopy:PALette {hardcopy_palette_scpi(palette)}"


def hardcopy_layout_command(layout: str) -> str:
    return f":HARDcopy:LAYout {hardcopy_layout_scpi(layout)}"


def hardcopy_screen_dump_data_query(format_name: str) -> str:
    return f":HCOPY:SDUMp:DATA? {screenshot_format_scpi(format_name)}"


def screenshot_format_scpi(format_name: str) -> str:
    return {"png": "PNG", "bmp": "BMP", "bmp8bit": "BMP8bit"}[
        normalize_screenshot_format(format_name)
    ]


def hardcopy_palette_scpi(palette: str) -> str:
    return {"color": "COLor", "grayscale": "GRAYscale", "none": "NONE"}[
        normalize_hardcopy_palette(palette)
    ]


def hardcopy_layout_scpi(layout: str) -> str:
    return {"landscape": "LANDscape", "portrait": "PORTrait"}[
        normalize_hardcopy_layout(layout)
    ]


def parse_screenshot_format(response: str) -> str:
    value = _readback_value(response, ("FORM", "FORMAT")).upper()
    mapping = {"PNG": "png", "BMP": "bmp", "BMP8BIT": "bmp8bit"}
    try:
        return mapping[value]
    except KeyError as exc:
        raise ScreenshotResponseError(
            f"Could not parse hardcopy format response: {response!r}"
        ) from exc


def parse_hardcopy_palette(response: str) -> str:
    value = _readback_value(response, ("PAL", "PALETTE")).upper()
    mapping = {"COL": "color", "COLOR": "color", "GRAY": "grayscale", "GRAYSCALE": "grayscale", "NONE": "none"}
    try:
        return mapping[value]
    except KeyError as exc:
        raise ScreenshotResponseError(
            f"Could not parse hardcopy palette response: {response!r}"
        ) from exc


def parse_hardcopy_layout(response: str) -> str:
    value = _readback_value(response, ("LAY", "LAYOUT")).upper()
    mapping = {"LAND": "landscape", "LANDSCAPE": "landscape", "PORT": "portrait", "PORTRAIT": "portrait"}
    try:
        return mapping[value]
    except KeyError as exc:
        raise ScreenshotResponseError(
            f"Could not parse hardcopy layout response: {response!r}"
        ) from exc


def parse_hardcopy_area(response: str) -> str:
    value = _readback_value(response, ("AREA",)).upper()
    if value in {"SCR", "SCREEN"}:
        return "screen"
    raise ScreenshotResponseError(f"Could not parse hardcopy area response: {response!r}")


def screenshot_data_query() -> str:
    """Build the SCPI query for a color PNG screenshot."""

    return f":DISPlay:DATA? {SCREENSHOT_FORMAT}, {SCREENSHOT_PALETTE}"


def screenshot_bytes_from_values(values: Sequence[int]) -> bytes:
    """Convert binary query values to PNG bytes and validate the response."""

    data = bytes(_validate_byte_value(value) for value in values)
    if not data:
        raise ScreenshotResponseError("Screenshot data query returned no bytes.")
    if not data.startswith(PNG_SIGNATURE):
        raise ScreenshotResponseError("Screenshot data is not a PNG image.")
    return data


def screenshot_bytes_from_values_for_format(
    values: Sequence[int], format_name: str
) -> bytes:
    """Convert binary values and validate the requested image signature."""

    format_name = normalize_screenshot_format(format_name)
    data = bytes(_validate_byte_value(value) for value in values)
    if not data:
        raise ScreenshotResponseError("Screenshot data query returned no bytes.")
    signature = PNG_SIGNATURE if format_name == "png" else BMP_SIGNATURE
    if not data.startswith(signature):
        raise ScreenshotResponseError(
            f"Screenshot data is not a {screenshot_format_scpi(format_name)} image."
        )
    return data


def write_screenshot_png(capture: ScreenshotCapture, path: str | Path) -> Path:
    """Write captured screenshot bytes to a PNG file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(capture.data)
    return output_path


def write_screenshot(capture: ScreenshotCapture, path: str | Path) -> Path:
    """Write captured screenshot bytes without changing their format."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(capture.data)
    return output_path


def _normalize_choice(value: str, choices: tuple[str, ...], label: str) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError(f"{label} must be a string.")
    normalized = value.strip().lower()
    if normalized not in choices:
        raise ParameterValidationError(f"{label} must be one of: {', '.join(choices)}.")
    return normalized


def _readback_value(response: str, prefixes: tuple[str, ...]) -> str:
    value = response.strip()
    if not value:
        return value
    parts = value.split()
    if len(parts) == 2 and parts[0].upper() in prefixes:
        return parts[1]
    return value


def _validate_byte_value(value: int) -> int:
    byte_value = int(value)
    if byte_value < 0 or byte_value > 255:
        raise ScreenshotResponseError(f"Screenshot byte out of range: {value!r}")
    return byte_value
