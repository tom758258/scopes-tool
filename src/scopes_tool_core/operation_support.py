"""Small helpers shared by more than one Core operation module."""

from __future__ import annotations

from typing import Sequence

from .scope import Oscilloscope
from .waveform import MultiChannelWaveformCapture, WaveformCapture


def _capture_waveform(
    scope: Oscilloscope,
    channels: Sequence[int],
    waveform_format: str,
    points: int,
) -> WaveformCapture | MultiChannelWaveformCapture:
    if len(channels) == 1:
        if waveform_format.lower() == "word":
            return scope.capture_waveform_word(channels[0], points=points)
        return scope.capture_waveform_byte(channels[0], points=points)
    if waveform_format.lower() == "word":
        return scope.capture_waveforms_word(channels, points=points)
    return scope.capture_waveforms_byte(channels, points=points)


def _scope_backend_json(scope: Oscilloscope) -> dict[str, object]:
    return {
        "backend": getattr(scope.backend, "backend", None),
        "timeout_ms": getattr(scope.backend, "timeout", None),
    }


def _append_session_header(human: list[str], scope: Oscilloscope, resource: str) -> None:
    human.append(f"Resource: {resource}")
    backend = getattr(scope.backend, "backend", None)
    if backend is not None:
        human.append(f"PyVISA backend: {backend}")
    timeout = getattr(scope.backend, "timeout", None)
    if timeout is not None:
        human.append(f"Timeout ms: {timeout}")


def _format_channel_list(channels: Sequence[int]) -> str:
    return ", ".join(f"CH{channel}" for channel in channels)


def _format_actual_points(capture: WaveformCapture | MultiChannelWaveformCapture) -> str:
    if isinstance(capture, MultiChannelWaveformCapture):
        per_channel = ", ".join(
            f"CH{item.channel}={len(item.raw_samples)}" for item in capture.captures
        )
        return f"Actual points: {per_channel}"
    return f"Actual points: {len(capture.raw_samples)}"


def _waveform_capture_commands(
    channels: Sequence[int],
    waveform_format: str,
    points: int,
) -> list[str]:
    from .planning import planned_waveform_scpi

    return [f"Command: {command}" for command in planned_waveform_scpi(channels, waveform_format, points)]
