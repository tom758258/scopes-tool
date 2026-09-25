"""Run-mode resolution and backend opening helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Literal, Mapping, Sequence

from .capabilities import ScopeCapabilities, capabilities_for_model_id
from .drivers import scope_for_physical_model
from .errors import OscilloscopeError
from .identity import physical_model_for_id
from .scope import Oscilloscope
from .simulator_backend import SimulatorBackend, SimulatorInstrumentState
from .simulator_config import simulator_backend_kwargs, validate_simulator_args
from .tektronix_simulator import TektronixSimulatorBackend

RunMode = Literal["dry_run", "simulate", "live"]


@dataclass(frozen=True)
class RunModeOptions:
    simulate: bool = False
    dry_run: bool = False
    live: bool = False
    planning_physical_model_id: str | None = None
    expected_physical_model_id: str | None = None
    simulate_signals: Sequence[str] = field(default_factory=tuple)
    simulate_preset: str | None = None
    simulate_scenario: str | None = None
    simulate_system_errors: Sequence[str] = field(default_factory=tuple)
    simulate_binary_transfer_failure: bool = False
    simulate_invalid_measurement_channels: Sequence[str] = field(default_factory=tuple)
    simulate_display_off_channels: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResolvedRunConfig:
    mode: RunMode
    planning_physical_model_id: str | None
    expected_physical_model_id: str | None
    capabilities: ScopeCapabilities | None
    resource: str | None
    visa_library: str | None = None
    options: RunModeOptions = field(default_factory=RunModeOptions)


def resolve_run_mode(options: RunModeOptions) -> RunMode:
    """Resolve compatible run-mode flags into one effective mode."""

    if options.simulate and options.dry_run:
        raise OscilloscopeError("--simulate cannot be combined with --dry-run")
    if options.live and options.simulate:
        raise OscilloscopeError("--live cannot be combined with --simulate")
    if options.live and options.dry_run:
        raise OscilloscopeError("--live cannot be combined with --dry-run")
    if options.simulate_signals and not options.simulate:
        raise OscilloscopeError("--simulate-signal can only be used with --simulate")
    for value, option in (
        (options.simulate_preset, "--simulate-preset"),
        (options.simulate_scenario, "--simulate-scenario"),
        (options.simulate_system_errors, "--simulate-system-error"),
        (
            options.simulate_binary_transfer_failure,
            "--simulate-binary-transfer-failure",
        ),
        (options.simulate_invalid_measurement_channels, "--simulate-invalid-measurement"),
        (options.simulate_display_off_channels, "--simulate-display-off"),
    ):
        if value and not options.simulate:
            raise OscilloscopeError(f"{option} can only be used with --simulate")
    if options.simulate:
        if options.planning_physical_model_id is None:
            raise OscilloscopeError(
                "simulate mode requires a planning physical model ID"
            )
        physical_model_for_id(options.planning_physical_model_id)
        capabilities = capabilities_for_model_id(options.planning_physical_model_id)
        if not capabilities.supports_simulator:
            raise OscilloscopeError("Simulator is unavailable for this physical model")
        validate_simulator_args(options, capabilities)
        return "simulate"
    if options.dry_run:
        if options.planning_physical_model_id is None:
            raise OscilloscopeError(
                "dry-run mode requires a planning physical model ID"
            )
        physical_model_for_id(options.planning_physical_model_id)
        capabilities_for_model_id(options.planning_physical_model_id)
        return "dry_run"
    if options.expected_physical_model_id is not None:
        physical_model_for_id(options.expected_physical_model_id)
        capabilities_for_model_id(options.expected_physical_model_id)
    return "live"


def resolve_resource(
    mode: RunMode,
    explicit_resource: str | None,
    model: str,
    environ: Mapping[str, str] = os.environ,
) -> str | None:
    """Resolve the resource string for a selected run mode."""

    if mode == "simulate":
        return explicit_resource or f"SIM::{model}::INSTR"
    if mode == "dry_run":
        return explicit_resource or f"DRY::{model}::INSTR"
    return explicit_resource or environ.get("SCOPES_TOOL_RESOURCE")


def require_resource(
    mode: RunMode,
    explicit_resource: str | None,
    model: str,
    environ: Mapping[str, str] = os.environ,
) -> str:
    """Return the resolved resource or raise when live selection is missing."""

    resource = resolve_resource(mode, explicit_resource, model, environ)
    if resource is None:
        raise OscilloscopeError("--resource is required unless SCOPES_TOOL_RESOURCE is set")
    return resource


def make_simulator_backend(
    options: RunModeOptions,
    resource: str,
    *,
    instrument_state: SimulatorInstrumentState | None = None,
) -> SimulatorBackend:
    """Create a simulator backend from resolved run options."""

    if options.planning_physical_model_id is None:
        raise OscilloscopeError(
            "simulate mode requires a planning physical model ID"
        )
    capabilities = capabilities_for_model_id(options.planning_physical_model_id)
    if not capabilities.supports_simulator:
        raise OscilloscopeError("Simulator is unavailable for this physical model")
    kwargs = simulator_backend_kwargs(
        options,
        resource,
        capabilities,
    )
    physical_model = physical_model_for_id(options.planning_physical_model_id)
    backend_type = TektronixSimulatorBackend if physical_model.vendor_id == "tektronix" else SimulatorBackend
    backend = backend_type(**kwargs)
    if instrument_state is not None:
        backend.restore_instrument_state(instrument_state)
    return backend


def open_scope_for_run(
    config: ResolvedRunConfig,
    *,
    simulator_state: SimulatorInstrumentState | None = None,
) -> Oscilloscope:
    """Open a scope for a resolved simulated or live run."""

    if config.mode == "dry_run":
        raise OscilloscopeError("dry-run does not open a backend")
    if config.resource is None:
        raise OscilloscopeError("--resource is required unless SCOPES_TOOL_RESOURCE is set")
    if config.mode == "simulate":
        backend = make_simulator_backend(
            config.options, config.resource, instrument_state=simulator_state
        )
        physical_model = physical_model_for_id(config.options.planning_physical_model_id)
        scope = scope_for_physical_model(physical_model, backend)
        scope.capabilities = capabilities_for_model_id(physical_model.model_id)
        return scope
    opened_scope = Oscilloscope.open(
        config.resource,
        visa_library=config.visa_library,
    )
    try:
        idn = opened_scope.query_idn()
        scope = scope_for_physical_model(
            idn.physical_model,
            opened_scope.backend,
            existing_scope=opened_scope,
        )
        if (
            config.expected_physical_model_id is not None
            and idn.model_id != config.expected_physical_model_id
        ):
            raise OscilloscopeError(
                "Live physical model identity does not match the expected "
                f"canonical ID {config.expected_physical_model_id}: {idn.raw}"
            )
        return scope
    except Exception:
        opened_scope.close()
        raise
