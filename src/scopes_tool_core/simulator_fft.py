"""Simulated Math and FFT function SCPI write and query handling."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .simulator_support import SimulatorBackendError

if TYPE_CHECKING:
    from .simulator_backend import SimulatorBackend


def _default_fft_function_state() -> dict[str, object]:
    return {
        "operation": "FFT",
        "source": "CHANnel1",
        "source2": "CHANnel2",
        "units": "DECibel",
        "window": "HANNing",
        "center": 0.0,
        "span": 1.0e6,
        "start": 0.0,
        "stop": 1.0e6,
        "gate": "NONE",
        "phase_reference": "TRIGger",
        "detection_type": "OFF",
        "detection_points": 640,
        "bin_size": 1000.0,
        "fft_sample_rate": 1.0e9,
        "resolution_bandwidth": 1500.0,
        "display": False,
        "scale": 1.0,
        "range": 8.0,
        "offset": 0.0,
        "integrate_input_offset": 0.0,
        "linear_gain": 1.0,
        "linear_offset": 0.0,
        "low_pass_cutoff": 1.0e6,
        "high_pass_cutoff": 1.0e3,
        "average_count": 64,
        "smooth_points": 9,
        "trend_measurement": "VAVerage",
        "trend_measurement_slot": "NONE",
    }


def _normalize_math_source_token(backend: SimulatorBackend, value: str) -> str:
    normalized = value.strip().upper()
    if normalized.startswith("CHANNEL"):
        channel = backend._validate_channel(
            int(normalized.removeprefix("CHANNEL"))
        )
        return f"CHANnel{channel}"
    if normalized == "GOFT":
        return "GOFT"
    if normalized.startswith("FUNCTION"):
        function = int(normalized.removeprefix("FUNCTION"))
        return f"FUNCtion{function}"
    raise SimulatorBackendError(f"Unsupported Math source: {value}")


def apply_fft_write(backend: SimulatorBackend, command: str) -> bool:
    """Apply one simulated Math/FFT write, reporting whether it was recognized."""

    clear_match = re.fullmatch(
        r":FUNCtion(\d+):CLEar",
        command,
        flags=re.IGNORECASE,
    )
    if clear_match is not None:
        function = int(clear_match.group(1))
        accumulation_operations = (
            backend._capabilities.math_filter_operations
            | backend._capabilities.math_visualization_operations
        )
        if (
            not (
                {"average", "max-hold", "min-hold"}
                & accumulation_operations
            )
            or function > backend._capabilities.math_function_count
        ):
            raise SimulatorBackendError(
                "Math clear is not supported by this simulator profile."
            )
        return True
    match = re.fullmatch(
        r":FUNCtion(\d*):([A-Za-z0-9]+)(?::([A-Za-z0-9]+))?\s+(.+)",
        command,
        flags=re.IGNORECASE,
    )
    if not match:
        return False
    function = int(match.group(1) or "1")
    key = backend.fft_functions.setdefault(function, _default_fft_function_state())
    primary, secondary, value = match.group(2).upper(), (match.group(3) or "").upper(), match.group(4)
    advanced_fft_setting = (
        (primary == "FREQUENCY" and secondary in {"START", "STOP"})
        or primary == "GATE"
        or (primary == "PHASE" and secondary == "REFERENCE")
        or (primary == "DETECTION" and secondary in {"TYPE", "POINTS"})
    )
    if advanced_fft_setting and not backend._capabilities.supports_advanced_fft:
        raise SimulatorBackendError(
            "Advanced FFT controls are not supported by this simulator profile."
        )
    if primary == "GOFT" and secondary == "OPERATION":
        backend.math_goft_operation = value.upper()
    elif primary == "GOFT" and secondary == "SOURCE1":
        backend.math_goft_source1 = backend._validate_channel(
            int(value.upper().rsplit("CHANNEL", 1)[1])
        )
    elif primary == "GOFT" and secondary == "SOURCE2":
        backend.math_goft_source2 = backend._validate_channel(
            int(value.upper().rsplit("CHANNEL", 1)[1])
        )
    elif primary == "OPERATION":
        operation = value.upper()
        if (
            operation == "FFTPHASE"
            and not backend._capabilities.supports_advanced_fft
        ):
            raise SimulatorBackendError(
                "FFT Phase is not supported by this simulator profile."
            )
        key["operation"] = (
            "FFTPhase" if operation == "FFTPHASE" else operation
        )
    elif primary == "SOURCE1":
        source = _normalize_math_source_token(backend, value)
        if (
            source.upper().startswith("FUNCTION")
            and str(key["operation"]).upper()
            in {"ADD", "SUBTRACT", "MULTIPLY", "DIVIDE"}
        ):
            raise SimulatorBackendError(
                "Arithmetic Math operators require an analog source1."
            )
        if (
            str(key["operation"]).upper() == "TREND"
            and backend._capabilities.series == "4000X"
        ):
            raise SimulatorBackendError(
                "4000X Trend does not accept a Math source write."
            )
        key["source"] = source
    elif primary == "SOURCE2":
        if (
            str(key["operation"]).upper() == "TREND"
            and backend._capabilities.series == "4000X"
        ):
            raise SimulatorBackendError(
                "4000X Trend does not accept a Math source write."
            )
        key["source2"] = _normalize_math_source_token(backend, value)
    elif primary == "DISPLAY":
        key["display"] = value.upper() == "ON"
    elif primary == "SCALE":
        key["scale"] = float(value)
    elif primary == "RANGE":
        key["range"] = float(value)
    elif primary == "OFFSET":
        key["offset"] = float(value)
    elif primary == "INTEGRATE" and secondary == "IOFFSET":
        key["integrate_input_offset"] = float(value)
    elif primary == "LINEAR" and secondary == "GAIN":
        key["linear_gain"] = float(value)
    elif primary == "LINEAR" and secondary == "OFFSET":
        key["linear_offset"] = float(value)
    elif primary == "FREQUENCY" and secondary == "LOWPASS":
        key["low_pass_cutoff"] = float(value)
    elif primary == "FREQUENCY" and secondary == "HIGHPASS":
        key["high_pass_cutoff"] = float(value)
    elif primary == "AVERAGE" and secondary == "COUNT":
        key["average_count"] = int(value)
    elif primary == "SMOOTH" and secondary == "POINTS":
        key["smooth_points"] = int(value)
    elif primary == "TREND" and secondary == "MEASUREMENT":
        key["trend_measurement"] = value
    elif primary == "TREND" and secondary == "NMEASUREMENT":
        key["trend_measurement_slot"] = value.upper()
    elif primary == "FFT" and secondary == "VTYPE":
        key["units"] = value
    elif primary == "FFT" and secondary == "WINDOW":
        key["window"] = value
    elif primary == "FFT" and secondary == "CENTER":
        key["center"] = float(value)
    elif primary == "FFT" and secondary == "SPAN":
        key["span"] = float(value)
    elif primary == "FREQUENCY" and secondary == "START":
        key["start"] = float(value)
    elif primary == "FREQUENCY" and secondary == "STOP":
        key["stop"] = float(value)
    elif primary == "GATE":
        key["gate"] = value
    elif primary == "PHASE" and secondary == "REFERENCE":
        key["phase_reference"] = value
    elif primary == "DETECTION" and secondary == "TYPE":
        key["detection_type"] = value
    elif primary == "DETECTION" and secondary == "POINTS":
        points = int(value)
        if points < 640 or points > 65536:
            raise SimulatorBackendError(
                "FFT detection points must be between 640 and 65536."
            )
        key["detection_points"] = points
    else:
        return False
    return True


def query_fft(backend: SimulatorBackend, command: str) -> str | None:
    """Return the simulated Math/FFT response, or None for other commands."""

    match = re.fullmatch(
        r":FUNCtion(\d*):([A-Za-z0-9]+)(?::([A-Za-z0-9]+))?\?",
        command,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    function = int(match.group(1) or "1")
    state = backend.fft_functions.setdefault(function, _default_fft_function_state())
    primary, secondary = match.group(2).upper(), (match.group(3) or "").upper()
    advanced_fft_query = (
        (primary == "FREQUENCY" and secondary in {"START", "STOP"})
        or primary in {"GATE", "BSIZE", "SRATE", "RBWIDTH"}
        or (primary == "PHASE" and secondary == "REFERENCE")
        or (primary == "DETECTION" and secondary in {"TYPE", "POINTS"})
    )
    if advanced_fft_query and not backend._capabilities.supports_advanced_fft:
        raise SimulatorBackendError(
            "Advanced FFT queries are not supported by this simulator profile."
        )
    if primary == "GOFT" and secondary == "OPERATION":
        return backend.math_goft_operation
    if primary == "GOFT" and secondary == "SOURCE1":
        return f"CHANnel{backend.math_goft_source1}"
    if primary == "GOFT" and secondary == "SOURCE2":
        return f"CHANnel{backend.math_goft_source2}"
    if primary == "OPERATION":
        return str(state["operation"])
    if primary == "SOURCE1":
        return str(state["source"])
    if primary == "SOURCE2":
        return str(state["source2"])
    if primary == "DISPLAY":
        return "1" if state["display"] else "0"
    if primary == "SCALE":
        return f"{float(state['scale']):.12g}"
    if primary == "RANGE":
        return f"{float(state['range']):.12g}"
    if primary == "OFFSET":
        return f"{float(state['offset']):.12g}"
    if primary == "INTEGRATE" and secondary == "IOFFSET":
        return f"{float(state['integrate_input_offset']):.12g}"
    if primary == "LINEAR" and secondary == "GAIN":
        return f"{float(state['linear_gain']):.12g}"
    if primary == "LINEAR" and secondary == "OFFSET":
        return f"{float(state['linear_offset']):.12g}"
    if primary == "FREQUENCY" and secondary == "LOWPASS":
        return f"{float(state['low_pass_cutoff']):.12g}"
    if primary == "FREQUENCY" and secondary == "HIGHPASS":
        return f"{float(state['high_pass_cutoff']):.12g}"
    if primary == "AVERAGE" and secondary == "COUNT":
        return str(int(state["average_count"]))
    if primary == "SMOOTH" and secondary == "POINTS":
        return str(int(state["smooth_points"]))
    if primary == "TREND" and secondary == "MEASUREMENT":
        return str(state["trend_measurement"])
    if primary == "TREND" and secondary == "NMEASUREMENT":
        return str(state["trend_measurement_slot"])
    if primary == "FFT" and secondary == "VTYPE":
        return str(state["units"])
    if primary == "FFT" and secondary == "WINDOW":
        return str(state["window"])
    if primary == "FFT" and secondary == "CENTER":
        return f"{float(state['center']):.12g}"
    if primary == "FFT" and secondary == "SPAN":
        return f"{float(state['span']):.12g}"
    if primary == "FREQUENCY" and secondary == "START":
        return f"{float(state['start']):.12g}"
    if primary == "FREQUENCY" and secondary == "STOP":
        return f"{float(state['stop']):.12g}"
    if primary == "GATE":
        return str(state["gate"])
    if primary == "PHASE" and secondary == "REFERENCE":
        return str(state["phase_reference"])
    if primary == "DETECTION" and secondary == "TYPE":
        return str(state["detection_type"])
    if primary == "DETECTION" and secondary == "POINTS":
        return str(int(state["detection_points"]))
    if primary == "BSIZE":
        return f"{float(state['bin_size']):.12g}"
    if primary == "SRATE":
        return f"{float(state['fft_sample_rate']):.12g}"
    if primary == "RBWIDTH":
        return f"{float(state['resolution_bandwidth']):.12g}"
    return None
