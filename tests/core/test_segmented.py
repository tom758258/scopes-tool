from dataclasses import replace

import pytest

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import ParameterValidationError, SegmentedResponseError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.segmented import (
    parse_segmented_mode,
)
from scopes_tool_core.simulator_backend import SimulatorBackend


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(" RTIM\n", "realtime"), (" SEGM ", "segmented")],
)
def test_segmented_mode_parser_accepts_abbreviated_readbacks(raw, expected):
    assert parse_segmented_mode(raw) == expected


def test_segmented_mode_parser_rejects_unknown_readback():
    with pytest.raises(SegmentedResponseError):
        parse_segmented_mode("UNKNOWN")


def test_segmented_realtime_query_only_reads_mode():
    backend = FakeBackend(responses={":ACQuire:MODE?": "RTIM\n"})
    scope = Oscilloscope(backend)
    scope.capabilities = capabilities_for_model("DSOX4024A")

    result = scope.query_segmented_memory()

    assert result.mode == "realtime"
    assert result.configured_segments is None
    assert result.acquired_segments is None
    assert result.selected_segment is None
    assert result.time_tag_s is None
    assert result.raw_mode == "RTIM"
    assert backend.history == [":ACQuire:MODE?"]


def test_segmented_query_parses_values_preserves_raw_and_orders_queries():
    backend = FakeBackend(
        responses={
            ":ACQuire:MODE?": "SEGM",
            ":ACQuire:SEGMented:COUNt?": "+25\n",
            ":WAVeform:SEGMented:COUNt?": "+10",
            ":ACQuire:SEGMented:INDex?": "+3",
            ":WAVeform:SEGMented:TTAG?": "+125.0E-03\n",
        }
    )
    scope = Oscilloscope(backend)
    scope.capabilities = capabilities_for_model("DSOX4024A")

    result = scope.query_segmented_memory()

    assert result.to_json() == {
        "mode": "segmented",
        "configured_segments": 25,
        "acquired_segments": 10,
        "selected_segment": 3,
        "time_tag_s": 0.125,
        "raw_mode": "SEGM",
        "raw_configured_segments": "+25",
        "raw_acquired_segments": "+10",
        "raw_selected_segment": "+3",
        "raw_time_tag": "+125.0E-03",
    }
    assert backend.history == [
        ":ACQuire:MODE?",
        ":ACQuire:SEGMented:COUNt?",
        ":WAVeform:SEGMented:COUNt?",
        ":ACQuire:SEGMented:INDex?",
        ":WAVeform:SEGMented:TTAG?",
    ]


def test_segmented_zero_acquired_count_skips_index_and_time_tag():
    backend = FakeBackend(
        responses={
            ":ACQuire:MODE?": "SEGMENTED",
            ":ACQuire:SEGMented:COUNt?": "25",
            ":WAVeform:SEGMented:COUNt?": "0",
        }
    )
    scope = Oscilloscope(backend)
    scope.capabilities = capabilities_for_model("DSOX4024A")

    result = scope.query_segmented_memory()

    assert result.selected_segment is None
    assert result.time_tag_s is None
    assert result.raw_selected_segment is None
    assert result.raw_time_tag is None
    assert backend.history == [
        ":ACQuire:MODE?",
        ":ACQuire:SEGMented:COUNt?",
        ":WAVeform:SEGMented:COUNt?",
    ]


def test_segmented_capability_guard_precedes_mode_query():
    backend = FakeBackend(responses={":ACQuire:MODE?": "SEGM"})
    scope = Oscilloscope(backend)
    scope.capabilities = replace(
        capabilities_for_model("DSOX4024A"), supports_segmented_memory=False
    )

    with pytest.raises(ParameterValidationError):
        scope.query_segmented_memory()
    assert backend.history == []


def test_segmented_malformed_numeric_response_uses_feature_error():
    backend = FakeBackend(
        responses={
            ":ACQuire:MODE?": "SEGM",
            ":ACQuire:SEGMented:COUNt?": "not-an-integer",
        }
    )
    scope = Oscilloscope(backend)
    scope.capabilities = capabilities_for_model("DSOX4024A")

    with pytest.raises(SegmentedResponseError):
        scope.query_segmented_memory()


def test_simulator_segmented_state_uses_query_history():
    backend = SimulatorBackend(
        segmented_mode="SEGM",
        segmented_configured_segments=25,
        segmented_acquired_segments=10,
        segmented_selected_segment=3,
        segmented_time_tag_s=0.125,
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    result = scope.query_segmented_memory()

    assert result.configured_segments == 25
    assert result.acquired_segments == 10
    assert result.selected_segment == 3
    assert result.time_tag_s == 0.125
    assert backend.history == [
        "*IDN?",
        ":ACQuire:MODE?",
        ":ACQuire:SEGMented:COUNt?",
        ":WAVeform:SEGMented:COUNt?",
        ":ACQuire:SEGMented:INDex?",
        ":WAVeform:SEGMented:TTAG?",
    ]
