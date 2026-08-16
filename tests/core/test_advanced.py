import pytest

from scopes_tool_core.advanced import (
    autoscale_commands,
    cursor_configure_commands,
    setup_recall_command,
    setup_save_command,
    trigger_holdoff_command,
    trigger_holdoff_commands,
)

from scopes_tool_core.capabilities import capabilities_for_model

from scopes_tool_core.scope import Oscilloscope

from scopes_tool_core.simulator_backend import (
    SimulatorBackend,
    SimulatorBackendError,
)

def test_advanced_command_formatting():
    capabilities = capabilities_for_model("DSOX4024A")

    assert trigger_holdoff_command(1e-6) == ":TRIGger:HOLDoff 1e-6"
    assert trigger_holdoff_commands(1e-6) == [
        ":TRIGger:HOLDoff:RANDom OFF",
        ":TRIGger:HOLDoff 1e-6",
    ]
    assert cursor_configure_commands(
        1,
        0.0,
        1e-3,
        y1_volts=0.0,
        y2_volts=0.5,
        capabilities=capabilities,
    ) == [
        ":MARKer:MODE MANual",
        ":MARKer:X1Y1source CHANnel1",
        ":MARKer:X2Y2source CHANnel1",
        ":MARKer:X1Position 0",
        ":MARKer:X2Position 0.001",
        ":MARKer:Y1Position 0",
        ":MARKer:Y2Position 0.5",
    ]
    assert autoscale_commands((1, 2), capabilities=capabilities) == [
        ":AUToscale CHANnel1,CHANnel2"
    ]
    assert setup_save_command(slot=3) == ":SAVE:SETup 3"
    assert setup_recall_command(file_spec="\\usb\\setup.scp") == (
        ':RECall:SETup "\\usb\\setup.scp"'
    )

def test_simulator_advanced_state_round_trip():
    backend = SimulatorBackend()
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.set_trigger_holdoff(2e-6)
    assert scope.query_trigger_holdoff() == pytest.approx(2e-6)
    assert ":TRIGger:HOLDoff:RANDom OFF" in backend.history

    scope.configure_cursor(1, 0.0, 1e-3, y1_volts=0.1, y2_volts=0.6)
    cursor = scope.query_cursor()
    assert cursor.mode == "MANUAL"
    assert cursor.x_delta_seconds == pytest.approx(1e-3)
    assert cursor.y_delta_volts == pytest.approx(0.5)

    scope.configure_fft(1, 2, units="vrms", window="flattop", display=True)
    fft = scope.query_fft(1)
    assert fft.source_channel == 2
    assert fft.display is True

def test_simulator_rejects_unit_suffixes_for_advanced_numeric_writes():
    backend = SimulatorBackend()

    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":TRIGger:HOLDoff 1 us")
    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":MARKer:X2Position 1 ms")
    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":MARKer:Y2Position 0.5 V")
