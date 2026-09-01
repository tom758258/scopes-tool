import pytest

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.reference import (
    ReferenceWaveformController,
    parse_reference_label,
    reference_save_command,
    validate_reference_label,
)
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend


def test_reference_builders_and_label_parser():
    capabilities = capabilities_for_model("DSOX4024A")
    assert reference_save_command(2, 1, capabilities=capabilities) == ":WMEMory2:SAVE CHANnel1"
    assert parse_reference_label('"BASELINE"') == "BASELINE"
    for value in ("", "TOO-LONG-11", 'BAD"LABEL', "非ASCII"):
        with pytest.raises(ParameterValidationError):
            validate_reference_label(value)


@pytest.mark.parametrize("slot", [0, 3])
def test_reference_slot_validation(slot):
    with pytest.raises(ParameterValidationError):
        reference_save_command(slot, 1, capabilities=capabilities_for_model("DSOX4024A"))


@pytest.mark.parametrize("model", ["DSOX2004A", "DSOX3024A"])
def test_reference_controller_command_order_and_raw_state(model):
    backend = FakeBackend(
        responses={
            "*OPC?": "1",
            ":WMEMory1:DISPlay?": "1",
            ":WMEMory1:LABel?": '"BASELINE"',
        }
    )
    controller = ReferenceWaveformController(SCPIClient(backend), capabilities_for_model(model))
    controller.save(1, 2)
    controller.set_display(1, True)
    controller.set_label(1, "BASELINE")
    state = controller.query(1)
    controller.clear(1)
    assert state.displayed is True
    assert state.raw_displayed == "1"
    assert state.label == "BASELINE"
    assert state.raw_label == '"BASELINE"'
    assert backend.history == [
        ":WMEMory1:SAVE CHANnel2",
        "*OPC?",
        ":WMEMory1:DISPlay ON",
        ':WMEMory1:LABel "BASELINE"',
        ":WMEMory1:DISPlay?",
        ":WMEMory1:LABel?",
        ":WMEMory1:CLEar",
    ]


def test_reference_simulator_roundtrip_and_clear():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()
    scope.save_reference_waveform(1, 2)
    scope.configure_reference_display(1, True)
    scope.configure_reference_label(1, "BASELINE")
    assert backend.reference_saved_source[1] == 2
    assert scope.query_reference_waveform(1).label == "BASELINE"
    scope.clear_reference_waveform(1)
    state = scope.query_reference_waveform(1)
    assert backend.reference_saved_source[1] is None
    assert state.displayed is False
    assert state.label == ""
