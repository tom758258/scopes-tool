"""Deterministic simulated screenshot and hardcopy image rendering."""

from __future__ import annotations

import binascii
import math
import struct
import zlib


_SCREENSHOT_WIDTH = 480
_SCREENSHOT_HEIGHT = 272
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_FONT_5X7 = {
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
}


def _simulated_screenshot_bmp(eight_bit: bool) -> bytes:
    """Return a deterministic valid 1x1 BMP payload."""

    if eight_bit:
        palette = b"".join(bytes((value, value, value, 0)) for value in range(256))
        pixel_offset = 14 + 40 + len(palette)
        pixels = b"\x7f\x00\x00\x00"
        dib = struct.pack("<IIIHHIIIIII", 40, 1, 1, 1, 8, 0, len(pixels), 0, 0, 256, 0)
        size = pixel_offset + len(pixels)
        return struct.pack("<2sIHHI", b"BM", size, 0, 0, pixel_offset) + dib + palette + pixels
    pixels = b"\x00\xd6\xff\x00"
    pixel_offset = 14 + 40
    dib = struct.pack("<IIIHHIIIIII", 40, 1, 1, 1, 24, 0, len(pixels), 0, 0, 0, 0)
    size = pixel_offset + len(pixels)
    return struct.pack("<2sIHHI", b"BM", size, 0, 0, pixel_offset) + dib + pixels


def _simulated_screenshot_png(model: str, *, white_background: bool) -> bytes:
    background = (255, 255, 255) if white_background else (0, 0, 0)
    grid = (210, 210, 210) if white_background else (42, 42, 42)
    axis = (160, 160, 160) if white_background else (72, 72, 72)
    text = (28, 32, 38) if white_background else (244, 244, 244)
    ch1 = (156, 112, 0) if white_background else (255, 214, 0)
    ch2 = (0, 120, 132) if white_background else (0, 220, 235)

    pixels = bytearray(background * (_SCREENSHOT_WIDTH * _SCREENSHOT_HEIGHT))

    for x in range(40, _SCREENSHOT_WIDTH, 40):
        _draw_vertical_line(pixels, x, grid if x != _SCREENSHOT_WIDTH // 2 else axis)
    for y in range(34, _SCREENSHOT_HEIGHT, 34):
        _draw_horizontal_line(pixels, y, grid if y != _SCREENSHOT_HEIGHT // 2 else axis)

    _draw_waveform(pixels, ch1, center_y=116, amplitude=42, phase=0.0)
    _draw_waveform(pixels, ch2, center_y=158, amplitude=36, phase=math.pi / 4.0)
    _draw_text(pixels, 12, 10, f"SIM {model.upper()}", text, scale=2)
    _draw_text(pixels, 12, 244, "CH1", ch1, scale=2)
    _draw_text(pixels, 66, 244, "CH2", ch2, scale=2)
    return _encode_rgb_png(_SCREENSHOT_WIDTH, _SCREENSHOT_HEIGHT, pixels)


def _encode_rgb_png(width: int, height: int, pixels: bytearray) -> bytes:
    stride = width * 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        start = y * stride
        raw.extend(pixels[start : start + stride])
    return b"".join(
        (
            _PNG_SIGNATURE,
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            _png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9)),
            _png_chunk(b"IEND", b""),
        )
    )


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = binascii.crc32(chunk_type)
    checksum = binascii.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def _draw_vertical_line(pixels: bytearray, x: int, color: tuple[int, int, int]) -> None:
    for y in range(_SCREENSHOT_HEIGHT):
        _set_pixel(pixels, x, y, color)


def _draw_horizontal_line(pixels: bytearray, y: int, color: tuple[int, int, int]) -> None:
    for x in range(_SCREENSHOT_WIDTH):
        _set_pixel(pixels, x, y, color)


def _draw_waveform(
    pixels: bytearray,
    color: tuple[int, int, int],
    *,
    center_y: int,
    amplitude: int,
    phase: float,
) -> None:
    previous: tuple[int, int] | None = None
    for x in range(24, _SCREENSHOT_WIDTH - 16):
        angle = (x - 24) / (_SCREENSHOT_WIDTH - 40) * 2.0 * math.pi * 2.4 + phase
        y = round(center_y - amplitude * math.sin(angle))
        if previous is not None:
            _draw_line(pixels, previous[0], previous[1], x, y, color)
            _draw_line(pixels, previous[0], previous[1] + 1, x, y + 1, color)
        previous = (x, y)


def _draw_line(
    pixels: bytearray,
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
        _set_pixel(pixels, x0, y0, color)
        if x0 == x1 and y0 == y1:
            return
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x0 += sx
        if doubled <= dx:
            error += dx
            y0 += sy


def _draw_text(
    pixels: bytearray,
    x: int,
    y: int,
    text: str,
    color: tuple[int, int, int],
    *,
    scale: int,
) -> None:
    cursor = x
    for char in text:
        glyph = _FONT_5X7.get(char, _FONT_5X7["-"])
        for row_index, row in enumerate(glyph):
            for column_index, value in enumerate(row):
                if value == "1":
                    _fill_rect(
                        pixels,
                        cursor + column_index * scale,
                        y + row_index * scale,
                        scale,
                        scale,
                        color,
                    )
        cursor += 6 * scale


def _fill_rect(
    pixels: bytearray,
    x: int,
    y: int,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    for row in range(y, y + height):
        for column in range(x, x + width):
            _set_pixel(pixels, column, row, color)


def _set_pixel(pixels: bytearray, x: int, y: int, color: tuple[int, int, int]) -> None:
    if x < 0 or x >= _SCREENSHOT_WIDTH or y < 0 or y >= _SCREENSHOT_HEIGHT:
        return
    offset = (y * _SCREENSHOT_WIDTH + x) * 3
    pixels[offset : offset + 3] = bytes(color)
