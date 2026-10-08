"""Simulated Channel SCPI write and query handling."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .simulator_support import _parse_scpi_string_arg

if TYPE_CHECKING:
    from .simulator_backend import SimulatorBackend


def apply_channel_write(backend: SimulatorBackend, command: str) -> bool:
    channel = _extract_channel(command)
    if channel is None:
        return False
    channel = backend._validate_channel(channel)
    upper = command.upper()
    value = command.rsplit(" ", 1)[1] if " " in command else ""
    if ":DISPLAY " in upper:
        backend.channel_display[channel] = upper.endswith(" ON")
    elif ":SCALE " in upper:
        backend.channel_scale[channel] = float(value)
    elif ":OFFSET " in upper:
        backend.channel_offset[channel] = float(value)
    elif ":COUPLING " in upper:
        backend.channel_coupling[channel] = value.upper()
    elif ":PROBE " in upper:
        backend.channel_probe[channel] = float(value)
    elif ":BWLIMIT " in upper:
        backend.channel_bandwidth_limit[channel] = upper.endswith(" ON")
    elif ":IMPEDANCE " in upper:
        backend.channel_impedance[channel] = "FIFTy" if value.upper().startswith("FIFT") else "ONEMeg"
    elif ":INVERT " in upper:
        backend.channel_invert[channel] = upper.endswith(" ON")
    elif ":RANGE " in upper:
        backend.channel_range[channel] = float(value)
    elif ":UNITS " in upper:
        backend.channel_units[channel] = "AMP" if value.upper().startswith("AMP") else "VOLT"
    elif ":VERNIER " in upper:
        backend.channel_vernier[channel] = upper.endswith(" ON")
    elif ":PROBE:SKEW " in upper:
        backend.channel_probe_skew[channel] = float(value)
    elif ":LABEL " in upper:
        backend.channel_label[channel] = _parse_scpi_string_arg(command.split(" ", 1)[1])
    else:
        return False
    return True


def query_channel(backend: SimulatorBackend, command: str) -> str | None:
    channel = _extract_channel(command)
    if channel is None:
        return None
    channel = backend._validate_channel(channel)
    upper = command.upper()
    if ":DISPLAY?" in upper:
        return "1" if backend.channel_display.get(channel, True) else "0"
    if ":SCALE?" in upper:
        return f"{backend.channel_scale.get(channel, 1.0):.12g}"
    if ":OFFSET?" in upper:
        return f"{backend.channel_offset.get(channel, 0.0):.12g}"
    if ":COUPLING?" in upper:
        return backend.channel_coupling.get(channel, "DC")
    if ":PROBE?" in upper:
        return f"{backend.channel_probe.get(channel, 10.0):.12g}"
    if ":BWLIMIT?" in upper:
        return "1" if backend.channel_bandwidth_limit.get(channel, False) else "0"
    if ":IMPEDANCE?" in upper:
        return backend.channel_impedance.get(channel, "ONEMeg")
    if ":INVERT?" in upper:
        return "1" if backend.channel_invert.get(channel, False) else "0"
    if ":RANGE?" in upper:
        return f"{backend.channel_range.get(channel, backend.channel_scale.get(channel, 1.0) * 8.0):.12g}"
    if ":UNITS?" in upper:
        return backend.channel_units.get(channel, "VOLT")
    if ":VERNIER?" in upper:
        return "1" if backend.channel_vernier.get(channel, False) else "0"
    if ":PROBE:SKEW?" in upper:
        return f"{backend.channel_probe_skew.get(channel, 0.0):.12g}"
    if ":LABEL?" in upper:
        return f'"{backend.channel_label.get(channel, "")}"'
    return None


def _extract_channel(command: str) -> int | None:
    marker = ":CHANnel"
    if marker not in command:
        return None
    remainder = command.split(marker, 1)[1]
    digits = []
    for char in remainder:
        if char.isdigit():
            digits.append(char)
        else:
            break
    return int("".join(digits)) if digits else None
