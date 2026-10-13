import pytest
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.errors import ParameterValidationError, TriggerResponseError
from scopes_tool_core.trigger import (
    trigger_edge_coupling_command,
    trigger_edge_coupling_query,
    trigger_edge_reject_command,
    trigger_edge_reject_query,
    normalize_trigger_edge_coupling,
    normalize_trigger_edge_reject,
)

def test_trigger_edge_coupling_builders():
    assert trigger_edge_coupling_command("ac") == ":TRIGger:EDGE:COUPling AC"
    assert trigger_edge_coupling_command("dc") == ":TRIGger:EDGE:COUPling DC"
    assert trigger_edge_coupling_command("lf-reject") == ":TRIGger:EDGE:COUPling LFReject"

    assert trigger_edge_coupling_query() == ":TRIGger:EDGE:COUPling?"

    with pytest.raises(ParameterValidationError) as exc:
        trigger_edge_coupling_command("gnd")
    assert "Invalid Edge Trigger coupling" in str(exc.value)

def test_trigger_edge_coupling_normalization_parsers():
    assert normalize_trigger_edge_coupling("AC") == "ac"
    assert normalize_trigger_edge_coupling("DC") == "dc"
    assert normalize_trigger_edge_coupling("LFR") == "lf-reject"
    assert normalize_trigger_edge_coupling("LFREJECT") == "lf-reject"
    assert normalize_trigger_edge_coupling(" lfreject \n") == "lf-reject"

    with pytest.raises(TriggerResponseError) as exc:
        normalize_trigger_edge_coupling("INVALID")
    assert "Could not parse Edge Trigger coupling response" in str(exc.value)

def test_trigger_edge_reject_builders():
    assert trigger_edge_reject_command("off") == ":TRIGger:EDGE:REJect OFF"
    assert trigger_edge_reject_command("lf-reject") == ":TRIGger:EDGE:REJect LFReject"
    assert trigger_edge_reject_command("hf-reject") == ":TRIGger:EDGE:REJect HFReject"

    assert trigger_edge_reject_query() == ":TRIGger:EDGE:REJect?"

    with pytest.raises(ParameterValidationError) as exc:
        trigger_edge_reject_command("invalid_reject")
    assert "Invalid Edge Trigger reject" in str(exc.value)

def test_trigger_edge_reject_normalization_parsers():
    assert normalize_trigger_edge_reject("OFF") == "off"
    assert normalize_trigger_edge_reject("LFR") == "lf-reject"
    assert normalize_trigger_edge_reject("LFREJECT") == "lf-reject"
    assert normalize_trigger_edge_reject("HFR") == "hf-reject"
    assert normalize_trigger_edge_reject("HFREJECT") == "hf-reject"
    assert normalize_trigger_edge_reject(" hfreject \n") == "hf-reject"

    with pytest.raises(TriggerResponseError) as exc:
        normalize_trigger_edge_reject("INVALID")
    assert "Could not parse Edge Trigger reject response" in str(exc.value)

def test_controllers_and_scope_routing():
    backend = FakeBackend(responses={
        "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4034A,SIM000000,07.20",
        ":TRIGger:EDGE:COUPling?": "LFREJECT",
        ":TRIGger:EDGE:REJect?": "HFREJECT",
    })
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_trigger_edge_coupling("ac")
    assert backend.history[-1] == ":TRIGger:EDGE:COUPling AC"

    coupling_state = scope.query_trigger_edge_coupling()
    assert coupling_state.coupling == "lf-reject"
    assert coupling_state.raw_value == "LFREJECT"
    assert coupling_state.to_json() == {"coupling": "lf-reject", "raw_value": "LFREJECT"}
    assert backend.history[-1] == ":TRIGger:EDGE:COUPling?"

    scope.configure_trigger_edge_reject("lf-reject")
    assert backend.history[-1] == ":TRIGger:EDGE:REJect LFReject"

    reject_state = scope.query_trigger_edge_reject()
    assert reject_state.reject == "hf-reject"
    assert reject_state.raw_value == "HFREJECT"
    assert reject_state.to_json() == {"reject": "hf-reject", "raw_value": "HFREJECT"}
    assert backend.history[-1] == ":TRIGger:EDGE:REJect?"
