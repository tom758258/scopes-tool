"""Small in-memory waveform analysis helpers."""

from __future__ import annotations

from typing import Literal, cast

from .errors import ParameterValidationError
from .waveform import WaveformCapture


WaveformMetric = Literal["max", "min", "peak-to-peak", "abs-max"]
WaveformOperator = Literal["gt", "gte", "lt", "lte"]

WAVEFORM_METRICS = ("max", "min", "peak-to-peak", "abs-max")
WAVEFORM_OPERATORS = ("gt", "gte", "lt", "lte")


def waveform_metric(capture: WaveformCapture, metric: str) -> float:
    """Calculate one supported metric from an existing waveform capture."""

    metric = validate_waveform_metric(metric)
    values = capture.vertical_values
    if not values:
        raise ParameterValidationError("waveform analysis requires at least one sample")
    minimum = min(values)
    maximum = max(values)
    if metric == "max":
        return maximum
    if metric == "min":
        return minimum
    if metric == "peak-to-peak":
        return maximum - minimum
    return max(abs(minimum), abs(maximum))


def waveform_condition_matches(value: float, operator: str, threshold: float) -> bool:
    """Compare one waveform metric value with a threshold."""

    operator = validate_waveform_operator(operator)
    if operator == "gt":
        return value > threshold
    if operator == "gte":
        return value >= threshold
    if operator == "lt":
        return value < threshold
    return value <= threshold


def validate_waveform_metric(value: object) -> WaveformMetric:
    if not isinstance(value, str) or value not in WAVEFORM_METRICS:
        raise ParameterValidationError(
            "waveform metric must be max, min, peak-to-peak, or abs-max"
        )
    return cast(WaveformMetric, value)


def validate_waveform_operator(value: object) -> WaveformOperator:
    if not isinstance(value, str) or value not in WAVEFORM_OPERATORS:
        raise ParameterValidationError("waveform operator must be gt, gte, lt, or lte")
    return cast(WaveformOperator, value)
