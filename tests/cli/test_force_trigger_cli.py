"""Tests for the force-trigger CLI command."""

import json

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.simulator_backend import SimulatorBackend, SimulatorBackendError
from scopes_tool_core.trigger import force_trigger_command


_FORBIDDEN_COMMANDS = (
    ":RUN",
    ":STOP",
    ":SINGle",
    ":DIGitize",
    ":AUToscale",
    "*RST",
    "*CLS",
    ":TRIGger:EDGE:SOURce",
    ":TRIGger:EDGE:LEVel",
    ":TRIGger:EDGE:SLOPe",
    ":ACQuire:TYPE",
    ":ACQuire:COUNt",
    ":ACQuire:SRATe",
    ":ACQuire:POINts",
    ":WAVeform:POINts",
    ":WAVeform:FORMat",
)


def test_force_trigger_cli_requires_resource(capsys, monkeypatch):
    monkeypatch.delenv("SCOPES_TOOL_RESOURCE", raising=False)

    assert cli.main(["force-trigger"]) == 2
    assert "--resource is required" in capsys.readouterr().err


def test_force_trigger_cli_dry_run_includes_planned_scpi_without_visa(monkeypatch, capsys):
    def fail_open(resource, visa_library=None):
        raise AssertionError("dry-run must not open VISA")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main(["force-trigger", "--dry-run", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["command"] == "force-trigger"
    assert payload["mode"] == "dry_run"
    assert payload["result"]["operation"] == "force-trigger"
    assert payload["result"]["scpi_command"] == force_trigger_command()
    assert payload["result"]["planned_scpi"] == [
        "*IDN?",
        force_trigger_command(),
        ":SYSTem:ERRor?",
    ]
    assert payload["result"]["state_changing"] is True
    assert payload["scpi"]["planned"] == payload["result"]["planned_scpi"]
    assert payload["scpi"]["sent"] == []
    assert payload["files"] == []


def test_force_trigger_cli_simulate_runs_expected_scpi_order(capsys):
    assert cli.main(["force-trigger", "--simulate", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["mode"] == "simulate"
    assert payload["result"]["operation"] == "force-trigger"
    assert payload["result"]["scpi_command"] == force_trigger_command()
    assert payload["result"]["forced"] is True
    sent = payload["scpi"]["sent"]
    assert sent == [
        "*IDN?",
        force_trigger_command(),
        ":SYSTem:ERRor?",
    ]
    assert payload["system_error"]["code"] == 0


def test_force_trigger_cli_simulate_returns_failure_on_system_error(monkeypatch, capsys):
    backend = SimulatorBackend(system_errors=['-113,"Undefined header"'])
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

    assert cli.main(["force-trigger", "--simulate", "--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["system_error"]["code"] == -113
    assert force_trigger_command() in payload["scpi"]["sent"]


def test_force_trigger_cli_does_not_send_unrelated_state_changing_commands(monkeypatch, capsys):
    backend = SimulatorBackend()
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

    assert cli.main(["force-trigger", "--simulate", "--json"]) == 0
    json.loads(capsys.readouterr().out)

    for forbidden in _FORBIDDEN_COMMANDS:
        for command in backend.history:
            assert not command.upper().startswith(forbidden.upper()), (
                f"force-trigger should not send {forbidden}; got {command!r}"
            )


def test_force_trigger_cli_scpi_log_does_not_break_json_stdout(capsys):
    assert cli.main(["force-trigger", "--simulate", "--json", "--log-scpi"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["result"]["forced"] is True


def test_force_trigger_command_order_with_fake_backend():
    backend = FakeBackend()
    client = SCPIClient(backend)

    client.write(force_trigger_command())

    assert backend.history == [force_trigger_command()]


def test_force_trigger_simulator_does_not_change_simulated_state():
    backend = SimulatorBackend()
    baseline_run_state = backend.run_state
    baseline_trigger_source = backend.trigger_source
    baseline_trigger_level = backend.trigger_level
    baseline_trigger_slope = backend.trigger_slope
    baseline_acquisition_type = backend.acquisition_type
    baseline_acquisition_count = backend.acquisition_count
    baseline_sample_rate = backend.sample_rate_hz
    baseline_acquisition_points = backend.acquisition_points
    baseline_timebase_scale = backend.timebase_scale
    baseline_timebase_position = backend.timebase_position

    backend.write(force_trigger_command())

    assert backend.history[-1] == force_trigger_command()
    assert backend.run_state == baseline_run_state
    assert backend.trigger_source == baseline_trigger_source
    assert backend.trigger_level == baseline_trigger_level
    assert backend.trigger_slope == baseline_trigger_slope
    assert backend.acquisition_type == baseline_acquisition_type
    assert backend.acquisition_count == baseline_acquisition_count
    assert backend.sample_rate_hz == baseline_sample_rate
    assert backend.acquisition_points == baseline_acquisition_points
    assert backend.timebase_scale == baseline_timebase_scale
    assert backend.timebase_position == baseline_timebase_position


def test_force_trigger_simulator_rejects_old_short_form():
    backend = SimulatorBackend()

    with pytest.raises(SimulatorBackendError, match="Unsupported simulator write"):
        backend.write(":TFORce")
