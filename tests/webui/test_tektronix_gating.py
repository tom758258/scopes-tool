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
    assert supported("display-vectors", b1)
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

    autoscale = catalog["autoscale"]["presentation"]["models"]
    for model in (b2, b1):
        for field in ("channels", "acquire_mode", "channels_mode"):
            assert autoscale[model]["fields"][field]["hidden"] is True

    setup = catalog["setup-save"]["presentation"]["models"]
    assert setup[b2]["fields"]["target"]["options"] == ["slot"]
    assert setup[b2]["fields"]["slot"]["options"] == list(range(1, 10))
    assert setup[b2]["fields"]["file"]["hidden"] is True

    trigger_mode = catalog["trigger-mode"]["presentation"]["models"]
    assert trigger_mode[b2]["fields"]["mode"]["options"] == ["edge"]
    assert trigger_mode[b1]["fields"]["mode"]["options"] == ["edge"]

    trigger_source = catalog["trigger-edge-source"]["presentation"]["models"]
    assert trigger_source[b2]["fields"]["source"]["options"] == ["analog-channel"]
    assert trigger_source[b1]["fields"]["source"]["options"] == ["analog-channel"]

    trigger_slope = catalog["trigger-edge-slope"]["presentation"]["models"]
    assert trigger_slope[b2]["fields"]["slope"]["options"] == ["positive", "negative"]
    assert trigger_slope[b1]["fields"]["slope"]["options"] == ["positive", "negative"]

    trigger_coupling = catalog["trigger-edge-coupling"]["presentation"]["models"]
    assert trigger_coupling[b2]["fields"]["coupling"]["options"] == ["dc", "lf-reject"]
    assert trigger_coupling[b1]["fields"]["coupling"]["options"] == ["ac", "dc", "lf-reject"]

    holdoff = catalog["trigger-holdoff"]["presentation"]["models"]
    assert holdoff[b2]["fields"]["seconds"]["minimum"] == pytest.approx(40e-9)
    assert holdoff[b2]["fields"]["seconds"]["maximum"] == pytest.approx(8.0)
    assert holdoff[b1]["fields"]["seconds"]["minimum"] == pytest.approx(500e-9)
    assert holdoff[b1]["fields"]["seconds"]["maximum"] == pytest.approx(10.0)


def test_webui_legacy_display_vectors_uses_b1_style_command(monkeypatch, tmp_path):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TDS2024B,SN1,1.0",
        "DISPlay:STYle?": ":DISPLAY:STYLE VECTORS",
        "*ESR?": "0",
    })
    scope = TektronixOscilloscope(backend)
    scope.query_idn()
    monkeypatch.setattr(command_execution, "open_scope_for_run", lambda *args, **kwargs: scope)

    result = command_execution.execute_command(
        "display-vectors", mode="live", resource="USB0::FAKE::INSTR", model_id=None,
        parameters={"action": "set"}, artifact_dir=tmp_path,
    )

    assert result["exit_code"] == 0
    assert backend.history == [
        "*IDN?", "DISPlay:STYle VECtors", "DISPlay:STYle?", "*ESR?"
    ]


@pytest.mark.parametrize(
    "command,parameters,message",
    [
        ("autoscale", {"channels": [1]}, "optional controls"),
        ("setup-save", {"target": "file", "file": "x.scp"}, "file target"),
        (
            "trigger-edge-source",
            {"action": "set", "source": "external"},
            "source is unsupported",
        ),
        (
            "trigger-edge-coupling",
            {"action": "set", "coupling": "ac"},
            "coupling is unsupported",
        ),
        (
            "trigger-holdoff",
            {"action": "set", "seconds": 20e-9},
            "at least",
        ),
    ],
)
def test_webui_tek_option_constraints_reject_before_business_scpi(
    monkeypatch, tmp_path, command, parameters, message
):
    backend = FakeBackend(responses={"*IDN?": "TEKTRONIX,TBS2074B,SN1,1.0"})
    scope = TektronixOscilloscope(backend)
    scope.query_idn()
    monkeypatch.setattr(command_execution, "open_scope_for_run", lambda *args, **kwargs: scope)

    with pytest.raises(WebUIRequestError, match=message):
        command_execution.execute_command(
            command, mode="live", resource="USB0::FAKE::INSTR", model_id=None,
            parameters=parameters, artifact_dir=tmp_path,
        )
    assert backend.history == ["*IDN?"]


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
