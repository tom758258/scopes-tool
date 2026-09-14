import pytest

from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend, SimulatorBackendError


def test_simulator_4000x_legal_6vpp_and_3v_offset_accepted():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_wgen_function("sine")
    scope.configure_wgen_load("one-meg")
    scope.configure_wgen_offset(3.0)
    scope.configure_wgen_voltage(6.0)
    scope.configure_wgen_frequency(1000)

    assert scope.query_wgen().amplitude_volts == 6.0
    assert scope.query_wgen().offset_volts == 3.0


def test_simulator_load_transition_scaling_and_same_load():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    # Establish legal High-Z state
    scope.configure_wgen_function("sine")
    scope.configure_wgen_load("one-meg")
    scope.configure_wgen_offset(3.0)
    scope.configure_wgen_voltage(6.0)

    # one-meg -> fifty: scale down by 2
    scope.configure_wgen_load("fifty")
    assert scope.query_wgen().load == "fifty"
    assert scope.query_wgen().amplitude_volts == 3.0
    assert scope.query_wgen().offset_volts == 1.5

    # same load (fifty -> fifty): no change
    scope.configure_wgen_load("fifty")
    assert scope.query_wgen().amplitude_volts == 3.0
    assert scope.query_wgen().offset_volts == 1.5

    # fifty -> one-meg: scale back up by 2
    scope.configure_wgen_load("one-meg")
    assert scope.query_wgen().load == "one-meg"
    assert scope.query_wgen().amplitude_volts == 6.0
    assert scope.query_wgen().offset_volts == 3.0


def test_simulator_invalid_write_rejected_and_state_preserved():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_wgen_function("sine")
    scope.configure_wgen_load("fifty")
    scope.configure_wgen_voltage(0.5)

    before = backend.wgen_amplitude_volts

    with pytest.raises(SimulatorBackendError):
        backend.write(":WGEN1:VOLTage 6")

    assert backend.wgen_amplitude_volts == before


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
