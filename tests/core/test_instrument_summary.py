from dataclasses import replace

import pytest

from scopes_tool_core import query_instrument_summary
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend


def test_instrument_summary_reads_capability_channels_timebase_and_edge_trigger():
    backend = SimulatorBackend(
        channel_display={1: True, 2: False},
        channel_scale={1: 0.5, 2: 2.0},
        channel_offset={1: 0.0, 2: -0.25},
        channel_units={1: "VOLT", 2: "AMPere"},
        timebase_scale=0.001,
        timebase_position=-0.0024,
        trigger_mode="EDGE",
        trigger_edge_source_raw="CHANnel2",
        trigger_levels={2: 1.2},
        trigger_slope="POSitive",
        trigger_sweep="NORMal",
    )
    scope = Oscilloscope(backend)
    scope.query_idn()
    scope.capabilities = replace(scope.capabilities, analog_channels=2)

    summary = query_instrument_summary(scope)

    assert summary["channels"] == [
        {"channel": 1, "display": True, "units": "volt", "scale": 0.5, "offset": 0.0},
        {"channel": 2, "display": False, "units": "amp", "scale": 2.0, "offset": -0.25},
    ]
    assert summary["timebase"] == {"scale": 0.001, "position": -0.0024}
    assert summary["trigger"] == {
        "type": "edge",
        "source": "analog-channel",
        "source_channel": 2,
        "level": 1.2,
        "units": "amp",
        "slope": "positive",
        "sweep": "normal",
    }


@pytest.mark.parametrize(
    ("trigger_mode", "trigger_source", "expected_type", "expected_source"),
    [
        ("GLITch", "CHANnel1", "glitch", None),
        ("EDGE", "EXTernal", "edge", "external"),
    ],
)
def test_instrument_summary_skips_unsafe_edge_queries(
    trigger_mode, trigger_source, expected_type, expected_source
):
    backend = SimulatorBackend(
        trigger_mode=trigger_mode,
        trigger_edge_source_raw=trigger_source,
    )
    scope = Oscilloscope(backend)
    scope.query_idn()
    backend.history.clear()

    summary = query_instrument_summary(scope)

    assert summary["trigger"]["type"] == expected_type
    assert summary["trigger"]["source"] == expected_source
    assert summary["trigger"]["level"] is None
    if expected_type != "edge":
        assert not any(command.startswith(":TRIGger:EDGE:") for command in backend.history)
    else:
        assert ":TRIGger:EDGE:LEVel? EXTernal" not in backend.history

