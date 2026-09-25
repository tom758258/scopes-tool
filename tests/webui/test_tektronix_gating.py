"""Focused Tektronix WebUI capability and live status checks."""

import pytest

from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.tektronix import TektronixOscilloscope
from scopes_tool_webui import command_execution
from scopes_tool_webui.command_catalog import command_catalog
from scopes_tool_webui.command_validation import WebUIRequestError


def test_catalog_admits_only_registered_tek_operations():
    catalog = {entry["id"]: entry for entry in command_catalog()}
    b2 = "tektronix-tbs2074b"
    b1 = "tektronix-tds2024b"
    keysight = "keysight-dsox4024a"

    def supported(command, model):
        return catalog[command]["presentation"]["models"][model]["supported"]

    assert supported("run", b2)
    assert supported("channel-offset", b2)
    assert not supported("channel-offset", b1)
    assert supported("timebase-position", b1)
    assert not supported("timebase-position", b2)
    assert not supported("display-vectors", b1)
    assert not supported("trigger-edge-level", b1)
    assert supported("trigger-edge-level", b2)
    for command in ("measure", "capture", "screenshot", "check-error", "single-wait", "trigger-pulse-width"):
        assert not supported(command, b2)
        assert not supported(command, b1)
    assert supported("capture", keysight)
    acquisition = catalog["acquisition"]["presentation"]["models"]
    assert acquisition[b2]["fields"]["type"]["options"] == ["normal", "peak", "average", "high_resolution"]
    assert acquisition[b1]["fields"]["type"]["options"] == ["normal", "peak", "average"]
    assert acquisition[b1]["fields"]["count"]["options"] == [4, 16, 64, 128]


def test_webui_live_tek_run_checks_esr_after_business_command(monkeypatch, tmp_path):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TBS2074B,SN1,1.0",
        "*ESR?": "0",
    })
    scope = TektronixOscilloscope(backend)
    scope.query_idn()
    monkeypatch.setattr(command_execution, "open_scope_for_run", lambda *args, **kwargs: scope)

    result = command_execution.execute_command(
        "run", mode="live", resource="USB0::FAKE::INSTR", model_id=None,
        parameters={}, artifact_dir=tmp_path,
    )

    assert result["exit_code"] == 0
    assert backend.history == ["*IDN?", "ACQuire:STOPAfter RUNSTop", "ACQuire:STATE ON", "*ESR?"]


def test_webui_unsupported_tek_command_rejected_before_business_scpi(monkeypatch, tmp_path):
    backend = FakeBackend(responses={"*IDN?": "TEKTRONIX,TDS2024B,SN1,1.0"})
    scope = TektronixOscilloscope(backend)
    scope.query_idn()
    monkeypatch.setattr(command_execution, "open_scope_for_run", lambda *args, **kwargs: scope)

    with pytest.raises(WebUIRequestError, match="unsupported"):
        command_execution.execute_command(
            "capture", mode="live", resource="USB0::FAKE::INSTR", model_id=None,
            parameters={}, artifact_dir=tmp_path,
        )
    assert backend.history == ["*IDN?"]


@pytest.mark.parametrize("parameters,message", [
    ({"action": "set", "type": "average", "count": 8}, "average count is unsupported"),
    ({"action": "set", "type": "high_resolution"}, "acquisition type is unsupported"),
])
def test_webui_invalid_acquisition_values_do_not_change_mode(monkeypatch, tmp_path, parameters, message):
    backend = FakeBackend(responses={"*IDN?": "TEKTRONIX,TDS2024B,SN1,1.0"})
    scope = TektronixOscilloscope(backend)
    scope.query_idn()
    monkeypatch.setattr(command_execution, "open_scope_for_run", lambda *args, **kwargs: scope)

    with pytest.raises(WebUIRequestError, match=message):
        command_execution.execute_command(
            "acquisition", mode="live", resource="USB0::FAKE::INSTR", model_id=None,
            parameters=parameters, artifact_dir=tmp_path,
        )
    assert backend.history == ["*IDN?"]
