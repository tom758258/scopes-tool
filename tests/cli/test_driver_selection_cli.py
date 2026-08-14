from scopes_tool_cli import cli, runtime
import scopes_tool_core.drivers as drivers_module
import scopes_tool_core.identity as identity_module
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.identity import PhysicalModelInfo
from scopes_tool_core.scope import Oscilloscope


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
