import json

import pytest

from scopes_tool_cli import cli, runtime
import scopes_tool_core.drivers as drivers_module
import scopes_tool_core.identity as identity_module
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.identity import PhysicalModelInfo
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.visa_backend import VisaResourceListing


def _register_synthetic_model(monkeypatch, *, driver_id):
    physical_model = PhysicalModelInfo(
        model_id="keysight-synthetic1000",
        vendor_id="keysight",
        canonical_model="SYNTH1000",
        display_name="Keysight Synthetic 1000",
        series="SYNTHETIC",
        capability_profile_id="keysight-infiniivision-4000x",
        driver_id=driver_id,
    )
    identity_index = dict(identity_module._PHYSICAL_MODEL_BY_VENDOR_AND_MODEL)
    identity_index[("keysight", "SYNTH1000")] = physical_model
    model_id_index = dict(identity_module._PHYSICAL_MODEL_BY_ID)
    model_id_index[physical_model.model_id] = physical_model
    monkeypatch.setattr(
        identity_module,
        "_PHYSICAL_MODEL_BY_VENDOR_AND_MODEL",
        identity_index,
    )
    monkeypatch.setattr(
        identity_module,
        "_PHYSICAL_MODEL_BY_ID",
        model_id_index,
    )
    return physical_model


def test_one_shot_live_command_uses_detected_driver_subclass(monkeypatch, capsys):
    selected_instances = []

    class SyntheticScope(Oscilloscope):
        def run(self):
            selected_instances.append(self)
            super().run()

    physical_model = _register_synthetic_model(
        monkeypatch,
        driver_id="synthetic-driver",
    )
    driver_registry = dict(drivers_module.DRIVER_REGISTRY)
    driver_registry[physical_model.driver_id] = SyntheticScope
    monkeypatch.setattr(drivers_module, "DRIVER_REGISTRY", driver_registry)
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,SYNTH1000,SN1,1.0",
            ":SYSTem:ERRor?": '+0,"No error"',
        }
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(
            lambda resource, visa_library=None: Oscilloscope(backend)
        ),
    )

    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR"]) == 0

    assert len(selected_instances) == 1
    assert isinstance(selected_instances[0], SyntheticScope)
    assert backend.history == ["*IDN?", ":RUN", ":SYSTem:ERRor?"]
    capsys.readouterr()


def test_one_shot_live_unknown_driver_blocks_state_change(monkeypatch, capsys):
    _register_synthetic_model(
        monkeypatch,
        driver_id="unregistered-driver",
    )
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,SYNTH1000,SN1,1.0",
        }
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(
            lambda resource, visa_library=None: Oscilloscope(backend)
        ),
    )

    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR"]) == 1

    assert backend.history == ["*IDN?"]
    assert backend.closed is True
    assert "unregistered driver ID" in capsys.readouterr().err


def test_one_shot_live_idn_parse_failure_closes_backend(monkeypatch, capsys):
    backend = FakeBackend(responses={"*IDN?": "malformed"})
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(
            lambda resource, visa_library=None: Oscilloscope(backend)
        ),
    )

    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR"]) == 1

    assert backend.history == ["*IDN?"]
    assert backend.closed is True
    capsys.readouterr()


def test_one_shot_identify_rejects_unknown_tek_model(monkeypatch, capsys):
    backend = FakeBackend(responses={"*IDN?": "TEKTRONIX,TBS9999B,SN1,1.0"})
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["identify", "--resource", "USB0::FAKE::INSTR"]) == 1
    assert backend.history == ["*IDN?"]
    assert backend.closed is True
    assert "Unsupported physical oscilloscope model" in capsys.readouterr().err


def test_tek_simulator_uses_tek_driver_and_status_path(monkeypatch, capsys):
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda *args, **kwargs: pytest.fail("opened")))
    assert cli.main(["run", "--simulate", "--model", "tektronix-tbs2074b", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert runtime._backend_history() == ["ACQuire:STOPAfter RUNSTop", "ACQuire:STATE ON", "*ESR?"]
    assert payload["result"]["post_command_status"]["value"] == 0


def test_tek_simulator_unsupported_command_fails_without_business_scpi(capsys):
    assert cli.main(["capture", "--channel", "1", "--simulate", "--model", "tektronix-tbs2074b"]) == 1
    assert runtime._backend_history() == ["*IDN?"]
    assert "unsupported" in capsys.readouterr().err.lower()


def test_tek_live_run_uses_esr_without_system_error_queue(monkeypatch, capsys):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TBS2074B,SN1,1.0",
        "*ESR?": "0",
    })
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR", "--model", "keysight-dsox4024a", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert backend.history == ["*IDN?", "ACQuire:STOPAfter RUNSTop", "ACQuire:STATE ON", "*ESR?"]
    assert payload["system_error"] is None
    assert payload["result"]["post_command_status"]["value"] == 0


def test_tek_esr_error_is_structured_without_system_error_queue(monkeypatch, capsys):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TBS2074B,SN1,1.0",
        "*ESR?": "8",
    })
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert backend.history == ["*IDN?", "ACQuire:STOPAfter RUNSTop", "ACQuire:STATE ON", "*ESR?"]
    assert payload["system_error"] is None
    assert "raw SESR '8'" in payload["error"]["message"]


def test_tek_explicit_standard_event_reads_esr_once(monkeypatch, capsys):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TDS2024B,SN1,1.0",
        "*ESR?": "8",
    })
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["system-standard-event", "--query", "--resource", "USB0::FAKE::INSTR", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert backend.history == ["*IDN?", "*ESR?"]
    assert payload["result"]["value"] == 8
    assert payload["system_error"] is None


def test_tek_invalid_average_count_does_not_change_mode(monkeypatch, capsys):
    backend = FakeBackend(responses={"*IDN?": "TEKTRONIX,TBS2074B,SN1,1.0"})
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["acquisition", "--type", "average", "--count", "3", "--resource", "USB0::FAKE::INSTR"]) == 1
    assert backend.history == ["*IDN?"]
    assert "Unsupported Tek average count" in capsys.readouterr().err


@pytest.mark.parametrize("command,args,expected", [
    ("channel-scale", ["--channel", "1", "--volts-per-division", "0.2"], ["CH1:SCAle 0.2"]),
    ("reference-save", ["--slot", "1", "--source-channel", "1"], ["SAVe:WAVEform CH1,REF1"]),
    ("save-pwd", ["--path", "C:/data"], ['FILESystem:CWD "C:/data"']),
    ("trigger-edge", ["--source-channel", "1", "--level", "0.5", "--slope", "positive"], [
        "TRIGger:A:EDGE:SOUrce CH1", "TRIGger:A:LEVel:CH1 0.5", "TRIGger:A:EDGE:SLOpe RISe",
    ]),
])
def test_tek_live_metadata_matches_sent_business_commands(monkeypatch, capsys, command, args, expected):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TBS2074B,SN1,1.0",
        "*ESR?": "0",
    })
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main([command, *args, "--resource", "USB0::FAKE::INSTR", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert backend.history == ["*IDN?", *expected, "*ESR?"]
    assert payload["result"].get("commands", [payload["result"].get("command")]) == expected


def test_tek_legacy_display_vectors_metadata_matches_sent_command(monkeypatch, capsys):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TDS2024B,SN1,1.0",
        "DISPlay:STYle?": ":DISPLAY:STYLE VECTORS",
        "*ESR?": "0",
    })
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main([
        "display-vectors", "--on",
        "--resource", "USB0::FAKE::INSTR", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert backend.history == [
        "*IDN?", "DISPlay:STYle VECtors", "*ESR?"
    ]
    assert payload["result"]["command"] == "DISPlay:STYle VECtors"


def test_live_resource_discovery_reports_unknown_tek_as_unsupported(monkeypatch, capsys):
    backend = FakeBackend(responses={"*IDN?": "TEKTRONIX,TBS9999B,SN1,1.0"})
    monkeypatch.setattr(
        cli, "list_visa_resources",
        lambda visa_library=None: VisaResourceListing(resources=("USB0::FAKE::INSTR",), backend="test"),
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["list-resources", "--live-only", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert backend.history == ["*IDN?"]
    assert payload["result"]["live_resources"] == []
    assert payload["result"]["verification_failures"][0]["detail"] == "Unsupported physical oscilloscope model"
