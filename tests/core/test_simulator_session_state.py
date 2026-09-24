import pytest

from scopes_tool_core.errors import ChannelResponseError
from scopes_tool_core.math import parse_math_function_operation
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import (
    SimulatorBackend,
    SimulatorBackendError,
)


@pytest.mark.parametrize(
    ("raw", "family", "operation"),
    [
        ("FFT", "fft", "fft"),
        ("FFTPhase", "fft", "fft-phase"),
        ("ADD", "operator", "add"),
        ("DIFF", "transform", "differentiate"),
        ("LOWPass", "filter", "low-pass"),
        ("MAGNify", "visualization", "magnify"),
        ("BTIM", "other", "bus-timing"),
        ("BSTate", "other", "bus-state"),
    ],
)
def test_parse_math_function_operation_classifies_shared_operation_domain(
    raw, family, operation
):
    assert parse_math_function_operation(raw) == (family, operation)


def test_parse_math_function_operation_rejects_unknown_readback():
    with pytest.raises(ChannelResponseError, match="Math operation"):
        parse_math_function_operation("GARBAGE")


def test_scope_queries_math_operation_family_without_assuming_an_editor():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    initial = scope.query_math_operation(1)
    assert initial.family == "fft"
    assert initial.operation == "fft"

    scope.configure_math_visualization(1, "magnify", source="channel2")
    visualization = scope.query_math_operation(1)
    assert visualization.family == "visualization"
    assert visualization.operation == "magnify"

    scope.configure_math_filter(
        1,
        "low-pass",
        "channel2",
        cutoff_hz=1000.0,
    )
    filtered = scope.query_math_operation(1)
    assert filtered.family == "filter"
    assert filtered.operation == "low-pass"

    backend.write(":FUNCtion1:OPERation BTIMing")
    bus_timing = scope.query_math_operation(1)
    assert bus_timing.family == "other"
    assert bus_timing.operation == "bus-timing"


def test_simulator_instrument_state_round_trips_without_session_state():
    first = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    first.channel_scale[1] = 2.0
    first.segmented_mode = "SEGM"
    first.segmented_configured_segments = 4
    first.fft_functions[1] = {
        "operation": "MAGNify",
        "source": "CHANnel2",
        "source2": "CHANnel1",
    }
    first.history.extend([":CHANnel1:SCALe 2", ":FUNCtion1:OPERation MAGNify"])
    first.timeout = 15000

    state = first.export_instrument_state()
    first.channel_scale[1] = 5.0
    first.close()

    second = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    second.restore_instrument_state(state)

    assert second.channel_scale[1] == pytest.approx(2.0)
    assert second.segmented_mode == "SEGM"
    assert second.segmented_configured_segments == 4
    assert second.fft_functions[1]["operation"] == "MAGNify"
    assert second.history == []
    assert second.timeout == 2000
    assert second.closed is False


def test_simulator_instrument_state_rejects_different_model():
    source = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    state = source.export_instrument_state()
    target = SimulatorBackend(physical_model_id="keysight-dsox4034a")

    with pytest.raises(SimulatorBackendError, match="model does not match"):
        target.restore_instrument_state(state)
