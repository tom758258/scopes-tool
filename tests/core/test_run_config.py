import pytest
import scopes_tool_core.run_config as run_config_module

import scopes_tool_core.drivers as drivers_module
from scopes_tool_core.errors import OscilloscopeError, UnsupportedModelError
from scopes_tool_core.run_config import (
    ResolvedRunConfig,
    RunModeOptions,
    open_scope_for_run,
    resolve_resource,
    resolve_run_mode,
)
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.tektronix import TektronixOscilloscope
from scopes_tool_core.tektronix_simulator import TektronixSimulatorBackend


def test_resolve_run_mode_rejects_simulate_and_dry_run():
    with pytest.raises(OscilloscopeError, match="cannot be combined"):
        resolve_run_mode(RunModeOptions(simulate=True, dry_run=True))


def test_resolve_run_mode_defaults_to_live():
    assert resolve_run_mode(RunModeOptions()) == "live"


@pytest.mark.parametrize(
    "options",
    [
        RunModeOptions(live=True, simulate=True),
        RunModeOptions(live=True, dry_run=True),
    ],
)
def test_resolve_run_mode_rejects_live_with_non_live_mode(options):
    with pytest.raises(OscilloscopeError, match="--live cannot be combined"):
        resolve_run_mode(options)


def test_simulator_options_require_simulate():
    with pytest.raises(OscilloscopeError, match="--simulate-preset"):
        resolve_run_mode(RunModeOptions(dry_run=True, simulate_preset="noisy-sine"))


@pytest.mark.parametrize(
    "model_id",
    [
        "keysight-dsox2004a",
        "keysight-dsox3024a",
        "keysight-dsox4024a",
        "keysight-dsox4034a",
    ],
)
@pytest.mark.parametrize(
    ("flag", "expected_mode"),
    [("dry_run", "dry_run"), ("simulate", "simulate")],
)
def test_registered_models_keep_dry_run_and_simulator_lookup(
    model_id, flag, expected_mode
):
    assert (
        resolve_run_mode(
            RunModeOptions(
                planning_physical_model_id=model_id,
                **{flag: True},
            )
        )
        == expected_mode
    )


@pytest.mark.parametrize("flag", ["dry_run", "simulate"])
def test_unregistered_series_shaped_model_is_rejected(flag):
    with pytest.raises(OscilloscopeError):
        resolve_run_mode(
            RunModeOptions(
                planning_physical_model_id="DSOX4054A",
                **{flag: True},
            )
        )


def test_resource_fallbacks():
    model_id = "keysight-dsox4024a"
    assert resolve_resource("simulate", None, model_id, {}) == f"SIM::{model_id}::INSTR"
    assert resolve_resource("dry_run", None, model_id, {}) == f"DRY::{model_id}::INSTR"
    assert resolve_resource(
        "live",
        None,
        model_id,
        {"SCOPES_TOOL_RESOURCE": "USB"},
    ) == "USB"


def test_dry_run_open_scope_is_blocked():
    config = ResolvedRunConfig(
        mode="dry_run",
        planning_physical_model_id="keysight-dsox4024a",
        expected_physical_model_id=None,
        capabilities=None,
        resource="DRY::keysight-dsox4024a::INSTR",
    )
    with pytest.raises(OscilloscopeError, match="dry-run"):
        open_scope_for_run(config)


@pytest.mark.parametrize("model_id, backend_type, scope_type", [
    ("keysight-dsox4024a", SimulatorBackend, Oscilloscope),
    ("tektronix-tbs2074b", TektronixSimulatorBackend, TektronixOscilloscope),
    ("tektronix-tds2024b", TektronixSimulatorBackend, TektronixOscilloscope),
    ("tektronix-tbs1052b", TektronixSimulatorBackend, TektronixOscilloscope),
])
def test_simulate_open_scope_uses_model_driver_and_dialect(model_id, backend_type, scope_type):
    options = RunModeOptions(
        simulate=True,
        planning_physical_model_id=model_id,
    )
    config = ResolvedRunConfig(
        mode="simulate",
        planning_physical_model_id=model_id,
        expected_physical_model_id=None,
        capabilities=None,
        resource=f"SIM::{model_id}::INSTR",
        options=options,
    )

    with open_scope_for_run(config) as scope:
        assert type(scope.backend) is backend_type
        assert type(scope) is scope_type
        assert scope.backend.physical_model_id == model_id
        assert scope.query_idn().model_id == model_id


def test_live_detected_identity_sets_actual_capabilities(monkeypatch):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4034a")
    monkeypatch.setattr(
        "scopes_tool_core.run_config.Oscilloscope.open",
        lambda *args, **kwargs: Oscilloscope(backend),
    )
    config = ResolvedRunConfig(
        mode="live",
        planning_physical_model_id=None,
        expected_physical_model_id="keysight-dsox4034a",
        capabilities=None,
        resource="USB0::FAKE::INSTR",
    )

    with open_scope_for_run(config) as scope:
        assert scope.idn.model_id == "keysight-dsox4034a"
        assert scope.capabilities is not None
        assert scope.capabilities.series == "4000X"


def test_live_expected_identity_cannot_override_detected_identity(monkeypatch):
    backend = SimulatorBackend(physical_model_id="keysight-dsox3024a")
    selected_model_ids = []
    real_scope_for_physical_model = run_config_module.scope_for_physical_model

    def select_detected_driver(physical_model, selected_backend, **kwargs):
        selected_model_ids.append(physical_model.model_id)
        return real_scope_for_physical_model(
            physical_model,
            selected_backend,
            **kwargs,
        )

    monkeypatch.setattr(
        "scopes_tool_core.run_config.Oscilloscope.open",
        lambda *args, **kwargs: Oscilloscope(backend),
    )
    monkeypatch.setattr(
        "scopes_tool_core.run_config.scope_for_physical_model",
        select_detected_driver,
    )
    config = ResolvedRunConfig(
        mode="live",
        planning_physical_model_id="keysight-dsox4034a",
        expected_physical_model_id="keysight-dsox4024a",
        capabilities=None,
        resource="USB0::FAKE::INSTR",
    )

    with pytest.raises(OscilloscopeError, match="does not match"):
        open_scope_for_run(config)

    assert selected_model_ids == ["keysight-dsox3024a"]
    assert backend.history == ["*IDN?"]


def test_live_unknown_driver_fails_before_command_execution(monkeypatch):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    monkeypatch.setattr(
        "scopes_tool_core.run_config.Oscilloscope.open",
        lambda *args, **kwargs: Oscilloscope(backend),
    )
    monkeypatch.setattr(drivers_module, "DRIVER_REGISTRY", {})
    config = ResolvedRunConfig(
        mode="live",
        planning_physical_model_id=None,
        expected_physical_model_id=None,
        capabilities=None,
        resource="USB0::FAKE::INSTR",
    )

    with pytest.raises(UnsupportedModelError, match="driver ID"):
        open_scope_for_run(config)

    assert backend.history == ["*IDN?"]
