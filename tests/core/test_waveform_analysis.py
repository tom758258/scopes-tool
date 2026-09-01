import pytest

from scopes_tool_core.waveform_analysis import (
    waveform_condition_matches,
    waveform_metric,
)

from tests.cli.support import byte_waveform_capture


@pytest.mark.parametrize(
    "metric, expected",
    [
        ("max", 3.0),
        ("min", -4.0),
        ("peak-to-peak", 7.0),
        ("abs-max", 4.0),
    ],
)
def test_waveform_metrics(metric, expected):
    capture = byte_waveform_capture(
        1,
        raw_samples=(1, 2, 3),
        vertical_values=(-4.0, 1.0, 3.0),
    )

    assert waveform_metric(capture, metric) == expected


@pytest.mark.parametrize(
    "operator, value, threshold, expected",
    [
        ("gt", 2.0, 1.0, True),
        ("gte", 2.0, 2.0, True),
        ("lt", 1.0, 2.0, True),
        ("lte", 2.0, 2.0, True),
    ],
)
def test_waveform_operators(operator, value, threshold, expected):
    assert waveform_condition_matches(value, operator, threshold) is expected
