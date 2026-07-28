from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend


def test_simulator_wgen_conservative_roundtrip():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_wgen_output(False)
    scope.configure_wgen_function("sine")
    scope.configure_wgen_frequency(1000)
    scope.configure_wgen_voltage(0.5)
    scope.configure_wgen_offset(0)
    scope.configure_wgen_load("one-meg")
    scope.configure_wgen_output(True)
    state = scope.query_wgen()

    assert state.enabled is True
    assert state.function == "sine"
    assert state.frequency_hz == 1000.0
    assert state.amplitude_volts == 0.5
    assert state.offset_volts == 0.0
    assert state.load == "one-meg"
    assert ":WGEN1:OUTPut ON" in backend.history
