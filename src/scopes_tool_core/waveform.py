"""Waveform capture helpers."""

from __future__ import annotations

import csv
import binascii
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import struct
from typing import Literal, Sequence, cast
import zlib

from .capabilities import ScopeCapabilities
from .channel import ChannelController, ChannelUnits, validate_analog_channel
from .errors import ParameterValidationError, WaveformResponseError
from .idn import IDN
from .scpi import SCPIClient

SUPPORTED_WAVEFORM_POINTS = (1000, 5000, 10000)
SUPPORTED_BYTE_POINTS = SUPPORTED_WAVEFORM_POINTS
SUPPORTED_WORD_POINTS = SUPPORTED_WAVEFORM_POINTS
WORD_BYTE_ORDER = "MSBFirst"
WORD_UNSIGNED = True
WaveformVerticalUnit = Literal["V", "A"]


@dataclass(frozen=True)
class WaveformPreamble:
    """Parsed `:WAVeform:PREamble?` response."""

    raw: str
    format_code: int
    type_code: int
    points: int
    count: int
    x_increment: float
    x_origin: float
    x_reference: int
    y_increment: float
    y_origin: float
    y_reference: int


@dataclass(frozen=True)
class WaveformCapture:
    """Converted single-channel waveform data."""

    channel: int
    requested_points: int
    format_name: str
    preamble: WaveformPreamble
    raw_samples: tuple[int, ...]
    time_s: tuple[float, ...]
    vertical_values: tuple[float, ...]
    vertical_unit: WaveformVerticalUnit
    byte_order: str | None = None
    unsigned: bool | None = None


@dataclass(frozen=True)
class MultiChannelWaveformCapture:
    """Converted waveform data for multiple analog channels."""

    captures: tuple[WaveformCapture, ...]

    def __post_init__(self) -> None:
        captures = tuple(self.captures)
        if not captures:
            raise WaveformResponseError(
                "Multi-channel waveform capture requires at least one channel."
            )

        channels = tuple(capture.channel for capture in captures)
        if len(set(channels)) != len(channels):
            raise WaveformResponseError(
                "Multi-channel waveform capture contains duplicate channels."
            )

        formats = {capture.format_name for capture in captures}
        if len(formats) != 1:
            raise WaveformResponseError(
                "Multi-channel waveform capture contains mixed formats."
            )

        requested_points = {capture.requested_points for capture in captures}
        if len(requested_points) != 1:
            raise WaveformResponseError(
                "Multi-channel waveform capture contains mixed point counts."
            )

        object.__setattr__(self, "captures", captures)

    @property
    def channels(self) -> tuple[int, ...]:
        """Ordered analog channel numbers."""

        return tuple(capture.channel for capture in self.captures)

    @property
    def requested_points(self) -> int:
        """Requested point count shared by all channel captures."""

        return self.captures[0].requested_points

    @property
    def format_name(self) -> str:
        """Waveform transfer format shared by all channel captures."""

        return self.captures[0].format_name


def query_waveform_vertical_unit(
    scpi: SCPIClient,
    capabilities: ScopeCapabilities,
    channel: int,
) -> WaveformVerticalUnit:
    """Query and map one channel's unit to the waveform vertical unit."""

    channel_units: ChannelUnits = ChannelController(scpi, capabilities).query_units(channel)
    if channel_units == "volt":
        return "V"
    if channel_units == "amp":
        return "A"
    raise WaveformResponseError(
        f"Unsupported normalized channel units: {channel_units!r}."
    )


class WaveformController:
    """Controls for waveform capture."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def capture_byte(self, channel: int, points: int = 1000) -> WaveformCapture:
        """Capture one analog channel using BYTE waveform format."""

        channel = validate_analog_channel(channel, self.capabilities)
        points = validate_waveform_points(points, self.capabilities)
        self.scpi.write(waveform_source_command(channel))
        vertical_unit = query_waveform_vertical_unit(
            self.scpi, self.capabilities, channel
        )
        self.scpi.write(waveform_format_byte_command())
        self.scpi.write(waveform_points_command(points))
        preamble = parse_waveform_preamble(self.scpi.query(waveform_preamble_query()))
        if preamble.format_code != 0:
            raise WaveformResponseError(
                f"Expected BYTE waveform preamble format 0, got {preamble.format_code}."
            )
        raw_samples = tuple(int(value) for value in self.scpi.query_binary_values(waveform_data_query(), datatype="B"))
        if not raw_samples:
            raise WaveformResponseError("Waveform data query returned no samples.")
        return convert_byte_waveform(
            channel, points, preamble, raw_samples, vertical_unit=vertical_unit
        )

    def capture_word(self, channel: int, points: int = 1000) -> WaveformCapture:
        """Capture one analog channel using WORD waveform format."""

        channel = validate_analog_channel(channel, self.capabilities)
        points = validate_waveform_points(points, self.capabilities)
        validate_word_format_supported(self.capabilities)
        self.scpi.write(waveform_source_command(channel))
        vertical_unit = query_waveform_vertical_unit(
            self.scpi, self.capabilities, channel
        )
        self.scpi.write(waveform_format_word_command())
        self.scpi.write(waveform_byte_order_command(WORD_BYTE_ORDER))
        self.scpi.write(waveform_unsigned_command(WORD_UNSIGNED))
        self.scpi.write(waveform_points_command(points))
        preamble = parse_waveform_preamble(self.scpi.query(waveform_preamble_query()))
        if preamble.format_code != 1:
            raise WaveformResponseError(
                f"Expected WORD waveform preamble format 1, got {preamble.format_code}."
            )
        raw_samples = tuple(
            int(value)
            for value in self.scpi.query_binary_values(
                waveform_data_query(),
                datatype="H",
                is_big_endian=True,
            )
        )
        if not raw_samples:
            raise WaveformResponseError("Waveform data query returned no samples.")
        return convert_word_waveform(
            channel, points, preamble, raw_samples, vertical_unit=vertical_unit
        )

    def capture_channels_byte(
        self, channels: Sequence[int], points: int = 1000
    ) -> MultiChannelWaveformCapture:
        """Capture multiple analog channels using BYTE waveform format."""

        channels = validate_waveform_channels(channels, self.capabilities)
        points = validate_waveform_points(points, self.capabilities)
        captures = tuple(self.capture_byte(channel, points=points) for channel in channels)
        return MultiChannelWaveformCapture(captures)

    def capture_channels_word(
        self, channels: Sequence[int], points: int = 1000
    ) -> MultiChannelWaveformCapture:
        """Capture multiple analog channels using WORD waveform format."""

        channels = validate_waveform_channels(channels, self.capabilities)
        points = validate_waveform_points(points, self.capabilities)
        validate_word_format_supported(self.capabilities)
        captures = tuple(self.capture_word(channel, points=points) for channel in channels)
        return MultiChannelWaveformCapture(captures)


def validate_waveform_channels(
    channels: Sequence[int], capabilities: ScopeCapabilities
) -> tuple[int, ...]:
    """Validate ordered waveform channel selection and reject duplicates."""

    if isinstance(channels, (str, bytes)):
        raise ParameterValidationError(
            "waveform channels must be a sequence of integers."
        )
    try:
        normalized = tuple(
            validate_analog_channel(channel, capabilities) for channel in channels
        )
    except TypeError as exc:
        raise ParameterValidationError(
            "waveform channels must be a sequence of integers."
        ) from exc
    if not normalized:
        raise ParameterValidationError("waveform capture requires at least one channel.")
    if len(set(normalized)) != len(normalized):
        seen: set[int] = set()
        duplicates = []
        for channel in normalized:
            if channel in seen and channel not in duplicates:
                duplicates.append(channel)
            seen.add(channel)
        duplicate_text = ", ".join(f"CH{channel}" for channel in duplicates)
        raise ParameterValidationError(
            f"duplicate waveform channels are not allowed: {duplicate_text}."
        )
    return normalized


def validate_waveform_points(points: int, capabilities: ScopeCapabilities) -> int:
    """Validate supported waveform point count."""

    try:
        value = int(points)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError("waveform points must be an integer.") from exc
    if value not in SUPPORTED_WAVEFORM_POINTS:
        supported = ", ".join(str(point_count) for point_count in SUPPORTED_WAVEFORM_POINTS)
        raise ParameterValidationError(
            f"waveform capture supports only these point counts: {supported}."
        )
    if value > capabilities.safe_max_waveform_points:
        raise ParameterValidationError(
            f"waveform points {value} exceed safe maximum {capabilities.safe_max_waveform_points}."
        )
    return value


def validate_word_format_supported(capabilities: ScopeCapabilities) -> None:
    """Reject WORD waveform capture when the runtime profile does not allow it."""

    if not capabilities.supports_word_format:
        raise ParameterValidationError(
            "WORD waveform format is not supported by this scope capability profile."
        )


def waveform_source_command(channel: int) -> str:
    """Build the SCPI command for waveform source."""

    return f":WAVeform:SOURce CHANnel{channel}"


def waveform_format_byte_command() -> str:
    """Build the SCPI command for BYTE waveform format."""

    return ":WAVeform:FORMat BYTE"


def waveform_format_word_command() -> str:
    """Build the SCPI command for WORD waveform format."""

    return ":WAVeform:FORMat WORD"


def waveform_byte_order_command(byte_order: str = WORD_BYTE_ORDER) -> str:
    """Build the SCPI command for WORD byte order."""

    return f":WAVeform:BYTeorder {byte_order}"


def waveform_unsigned_command(unsigned: bool = WORD_UNSIGNED) -> str:
    """Build the SCPI command for waveform unsigned mode."""

    return f":WAVeform:UNSigned {'ON' if unsigned else 'OFF'}"


def waveform_points_command(points: int) -> str:
    """Build the SCPI command for waveform point count."""

    return f":WAVeform:POINts {points}"


def waveform_preamble_query() -> str:
    """Build the SCPI query for waveform preamble."""

    return ":WAVeform:PREamble?"


def waveform_data_query() -> str:
    """Build the SCPI query for waveform data."""

    return ":WAVeform:DATA?"


def parse_waveform_preamble(raw: str) -> WaveformPreamble:
    """Parse a Keysight waveform preamble."""

    parts = [part.strip() for part in raw.strip().split(",")]
    if len(parts) != 10:
        raise WaveformResponseError(f"Expected 10 waveform preamble fields, got {len(parts)}: {raw!r}")
    try:
        format_code = int(parts[0])
        type_code = int(parts[1])
        points = int(parts[2])
        count = int(parts[3])
        x_increment = float(parts[4])
        x_origin = float(parts[5])
        x_reference = int(parts[6])
        y_increment = float(parts[7])
        y_origin = float(parts[8])
        y_reference = int(parts[9])
    except ValueError as exc:
        raise WaveformResponseError(f"Could not parse waveform preamble: {raw!r}") from exc
    numeric_values = (x_increment, x_origin, y_increment, y_origin)
    if not all(math.isfinite(value) for value in numeric_values):
        raise WaveformResponseError(f"Could not parse waveform preamble: {raw!r}")
    if points < 1:
        raise WaveformResponseError(f"Waveform preamble points must be positive: {raw!r}")
    return WaveformPreamble(
        raw=raw.strip(),
        format_code=format_code,
        type_code=type_code,
        points=points,
        count=count,
        x_increment=x_increment,
        x_origin=x_origin,
        x_reference=x_reference,
        y_increment=y_increment,
        y_origin=y_origin,
        y_reference=y_reference,
    )


def validate_waveform_vertical_unit(unit: str) -> WaveformVerticalUnit:
    """Validate the supported analog waveform vertical units."""

    if unit not in {"V", "A"}:
        raise ParameterValidationError("waveform vertical unit must be V or A.")
    return cast(WaveformVerticalUnit, unit)


def convert_byte_waveform(
    channel: int,
    requested_points: int,
    preamble: WaveformPreamble,
    raw_samples: Sequence[int],
    *,
    vertical_unit: WaveformVerticalUnit,
) -> WaveformCapture:
    """Convert BYTE waveform samples to time and vertical-value tuples."""

    samples = tuple(_validate_byte_sample(value) for value in raw_samples)
    vertical_unit = validate_waveform_vertical_unit(vertical_unit)
    time_s = tuple(
        (index - preamble.x_reference) * preamble.x_increment + preamble.x_origin
        for index in range(len(samples))
    )
    vertical_values = tuple(
        (sample - preamble.y_reference) * preamble.y_increment + preamble.y_origin
        for sample in samples
    )
    return WaveformCapture(
        channel=channel,
        requested_points=requested_points,
        format_name="BYTE",
        preamble=preamble,
        raw_samples=samples,
        time_s=time_s,
        vertical_values=vertical_values,
        vertical_unit=vertical_unit,
    )


def convert_word_waveform(
    channel: int,
    requested_points: int,
    preamble: WaveformPreamble,
    raw_samples: Sequence[int],
    *,
    vertical_unit: WaveformVerticalUnit,
) -> WaveformCapture:
    """Convert unsigned WORD waveform samples to time and vertical-value tuples."""

    samples = tuple(_validate_word_sample(value) for value in raw_samples)
    vertical_unit = validate_waveform_vertical_unit(vertical_unit)
    time_s = tuple(
        (index - preamble.x_reference) * preamble.x_increment + preamble.x_origin
        for index in range(len(samples))
    )
    vertical_values = tuple(
        (sample - preamble.y_reference) * preamble.y_increment + preamble.y_origin
        for sample in samples
    )
    return WaveformCapture(
        channel=channel,
        requested_points=requested_points,
        format_name="WORD",
        preamble=preamble,
        raw_samples=samples,
        time_s=time_s,
        vertical_values=vertical_values,
        vertical_unit=vertical_unit,
        byte_order=WORD_BYTE_ORDER,
        unsigned=WORD_UNSIGNED,
    )


def write_waveform_csv(capture: WaveformCapture, path: str | Path) -> Path:
    """Write converted waveform data to CSV."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("time_s", f"ch{capture.channel}_v"))
        writer.writerows(zip(capture.time_s, capture.vertical_values))
    return output_path


def write_waveform_metadata(
    capture: WaveformCapture,
    path: str | Path,
    *,
    idn: IDN,
    resource: str,
) -> Path:
    """Write capture metadata to JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "idn": idn.raw,
        "vendor": idn.vendor,
        "model": idn.model,
        "series": idn.series,
        "serial": idn.serial,
        "firmware": idn.firmware,
        "resource": resource,
        "channel": capture.channel,
        "requested_points": capture.requested_points,
        "actual_points": len(capture.raw_samples),
        "format": capture.format_name,
        "preamble": asdict(capture.preamble),
    }
    if capture.byte_order is not None:
        metadata["byte_order"] = capture.byte_order
    if capture.unsigned is not None:
        metadata["unsigned"] = capture.unsigned
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return output_path


def write_waveforms_csv(
    capture: MultiChannelWaveformCapture,
    path: str | Path,
    *,
    allow_time_axis_tolerance: bool = False,
) -> Path:
    """Write aligned multi-channel waveform data to CSV."""

    _validate_aligned_waveforms(
        capture, allow_time_axis_tolerance=allow_time_axis_tolerance
    )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reference = _time_axis_reference(
        capture,
        allow_time_axis_tolerance=allow_time_axis_tolerance,
    )
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("time_s", *(f"ch{item.channel}_v" for item in capture.captures))
        )
        for index, time_value in enumerate(reference.time_s):
            writer.writerow(
                (time_value, *(item.vertical_values[index] for item in capture.captures))
            )
    return output_path


def write_waveforms_metadata(
    capture: MultiChannelWaveformCapture,
    path: str | Path,
    *,
    idn: IDN,
    resource: str,
    time_axis_tolerance: dict[str, object] | None = None,
) -> Path:
    """Write multi-channel capture metadata to JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "idn": idn.raw,
        "vendor": idn.vendor,
        "model": idn.model,
        "series": idn.series,
        "serial": idn.serial,
        "firmware": idn.firmware,
        "resource": resource,
        "requested_points": capture.requested_points,
        "format": capture.format_name,
        "channels": [_waveform_channel_metadata(item) for item in capture.captures],
    }
    if time_axis_tolerance is not None:
        metadata["time_axis_tolerance"] = time_axis_tolerance
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return output_path


def waveform_time_axis_tolerance_summary(
    capture: MultiChannelWaveformCapture,
) -> dict[str, object]:
    """Return compact time-axis tolerance details for a multi-channel capture."""

    reference = _time_axis_reference(capture, allow_time_axis_tolerance=True)
    reference_count = _validate_capture_sample_lengths(reference)
    max_allowed_delta = _time_axis_max_allowed_delta(reference)
    channels: list[dict[str, object]] = []
    for item in capture.captures:
        item_count = _validate_capture_sample_lengths(item)
        max_delta = 0.0
        if item_count == reference_count:
            max_delta = _time_axis_max_delta(item.time_s, reference.time_s)
        channels.append(
            {
                "channel": item.channel,
                "max_observed_delta_s": max_delta,
            }
        )
    return {
        "enabled": True,
        "canonical_channel": reference.channel,
        "max_allowed_delta_s": max_allowed_delta,
        "channels": channels,
    }


def write_waveform_plot_png(
    capture: WaveformCapture | MultiChannelWaveformCapture,
    path: str | Path,
    *,
    width: int = 1000,
    height: int = 600,
) -> Path:
    """Write a simple waveform line plot PNG without third-party dependencies."""

    if width < 100 or height < 100:
        raise ValueError("plot dimensions must be at least 100x100 pixels.")
    captures = capture.captures if isinstance(capture, MultiChannelWaveformCapture) else (capture,)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(_plot_png_bytes(captures, width=width, height=height))
    return output_path


def _waveform_channel_metadata(capture: WaveformCapture) -> dict[str, object]:
    metadata: dict[str, object] = {
        "channel": capture.channel,
        "actual_points": len(capture.raw_samples),
        "preamble": asdict(capture.preamble),
    }
    if capture.byte_order is not None:
        metadata["byte_order"] = capture.byte_order
    if capture.unsigned is not None:
        metadata["unsigned"] = capture.unsigned
    return metadata


def _validate_aligned_waveforms(
    capture: MultiChannelWaveformCapture,
    *,
    allow_time_axis_tolerance: bool,
) -> None:
    reference = _time_axis_reference(
        capture,
        allow_time_axis_tolerance=allow_time_axis_tolerance,
    )
    reference_count = _validate_capture_sample_lengths(reference)
    max_allowed_delta = _time_axis_max_allowed_delta(reference)
    for item in capture.captures:
        if item is reference:
            continue
        item_count = _validate_capture_sample_lengths(item)
        if item_count != reference_count:
            raise WaveformResponseError(
                "Cannot write multi-channel waveform CSV: "
                f"CH{item.channel} has {item_count} samples, "
                f"CH{reference.channel} has {reference_count}."
            )
        if item.time_s != reference.time_s:
            max_delta = _time_axis_max_delta(item.time_s, reference.time_s)
            if allow_time_axis_tolerance and max_delta <= max_allowed_delta:
                continue
            raise WaveformResponseError(
                "Cannot write multi-channel waveform CSV: "
                f"CH{item.channel} time axis does not match CH{reference.channel}."
            )


def _validate_capture_sample_lengths(capture: WaveformCapture) -> int:
    sample_count = len(capture.raw_samples)
    if len(capture.time_s) != sample_count:
        raise WaveformResponseError(
            f"CH{capture.channel} has {sample_count} samples "
            f"but {len(capture.time_s)} time values."
        )
    if len(capture.vertical_values) != sample_count:
        raise WaveformResponseError(
            f"CH{capture.channel} has {sample_count} samples "
            f"but {len(capture.vertical_values)} vertical values."
        )
    return sample_count


def _time_axis_reference(
    capture: MultiChannelWaveformCapture,
    *,
    allow_time_axis_tolerance: bool,
) -> WaveformCapture:
    if allow_time_axis_tolerance:
        for item in capture.captures:
            if item.channel == 1:
                return item
    return capture.captures[0]


def _time_axis_max_allowed_delta(capture: WaveformCapture) -> float:
    return 0.5 * abs(capture.preamble.x_increment)


def _time_axis_max_delta(
    time_s: Sequence[float],
    reference_time_s: Sequence[float],
) -> float:
    if not time_s:
        return 0.0
    return max(
        abs(time_value - reference_value)
        for time_value, reference_value in zip(time_s, reference_time_s)
    )


def _plot_png_bytes(
    captures: Sequence[WaveformCapture],
    *,
    width: int,
    height: int,
) -> bytes:
    margin_left = 64
    margin_right = 20
    margin_top = 20
    margin_bottom = 48
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    xs = [value for capture in captures for value in capture.time_s]
    ys = [value for capture in captures for value in capture.vertical_values]
    if not xs or not ys:
        raise ValueError("cannot plot an empty waveform capture.")
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmin == xmax:
        xmin -= 0.5
        xmax += 0.5
    if ymin == ymax:
        ymin -= 0.5
        ymax += 0.5
    ypad = (ymax - ymin) * 0.08
    ymin -= ypad
    ymax += ypad

    pixels = bytearray([255, 255, 255] * width * height)
    axis_color = (70, 70, 70)
    grid_color = (225, 225, 225)
    colors = ((31, 119, 180), (214, 39, 40), (44, 160, 44), (148, 103, 189))

    def point(time_s: float, vertical_value: float) -> tuple[int, int]:
        x = margin_left + round((time_s - xmin) / (xmax - xmin) * (plot_width - 1))
        y = margin_top + round((ymax - vertical_value) / (ymax - ymin) * (plot_height - 1))
        return x, y

    for index in range(6):
        x = margin_left + round(index * (plot_width - 1) / 5)
        _draw_line(pixels, width, height, x, margin_top, x, margin_top + plot_height, grid_color)
    for index in range(5):
        y = margin_top + round(index * (plot_height - 1) / 4)
        _draw_line(pixels, width, height, margin_left, y, margin_left + plot_width, y, grid_color)
    _draw_line(pixels, width, height, margin_left, margin_top, margin_left, margin_top + plot_height, axis_color)
    _draw_line(pixels, width, height, margin_left, margin_top + plot_height, margin_left + plot_width, margin_top + plot_height, axis_color)

    for capture_index, capture in enumerate(captures):
        color = colors[capture_index % len(colors)]
        points = [
            point(time_s, vertical_value)
            for time_s, vertical_value in zip(capture.time_s, capture.vertical_values)
        ]
        for first, second in zip(points, points[1:]):
            _draw_line(pixels, width, height, first[0], first[1], second[0], second[1], color)

    rows = []
    stride = width * 3
    for y in range(height):
        rows.append(b"\x00" + bytes(pixels[y * stride : (y + 1) * stride]))
    raw = b"".join(rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def _draw_line(
    pixels: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
) -> None:
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        if 0 <= x0 < width and 0 <= y0 < height:
            offset = (y0 * width + x0) * 3
            pixels[offset : offset + 3] = bytes(color)
        if x0 == x1 and y0 == y1:
            break
        twice_error = 2 * error
        if twice_error >= dy:
            error += dy
            x0 += sx
        if twice_error <= dx:
            error += dx
            y0 += sy


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def _validate_byte_sample(value: int) -> int:
    sample = int(value)
    if sample < 0 or sample > 255:
        raise WaveformResponseError(f"BYTE waveform sample out of range: {value!r}")
    return sample


def _validate_word_sample(value: int) -> int:
    sample = int(value)
    if sample < 0 or sample > 65535:
        raise WaveformResponseError(f"WORD waveform sample out of range: {value!r}")
    return sample
