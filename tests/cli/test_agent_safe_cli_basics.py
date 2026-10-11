import json

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.simulator_backend import SimulatorBackend
from tests.cli._agent_safe_cli_support import _json_stdout


def test_verify_simulate_json_uses_simulator_without_resource(capsys):
    assert cli.main(["identify", "--simulate", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "identify"
    assert payload["mode"] == "simulate"
    assert payload["resource"] == "SIM::keysight-dsox4024a::INSTR"
    assert payload["backend"] == "Keysight simulator"
    assert payload["idn"]["model"] == "DSOX4024A"
    assert payload["capabilities"]["analog_channels"] == 4
    assert payload["scpi"]["sent"] == ["*IDN?"]


@pytest.mark.parametrize("mode", ["--dry-run", "--simulate"])
def test_model_argument_requires_canonical_physical_model_id(capsys, mode):
    assert (
        cli.main(
            [
                "identify",
                mode,
                "--json",
                "--model",
                "DSOX4024A",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["idn"] is None
    assert "model ID" in payload["error"]["message"]


@pytest.mark.parametrize("mode", ["--dry-run", "--simulate"])
def test_unregistered_series_shaped_model_id_is_rejected(capsys, mode):
    assert (
        cli.main(
            [
                "identify",
                mode,
                "--json",
                "--model",
                "keysight-dsox4054a",
            ]
        )
        == 1
    )

    assert "model ID" in _json_stdout(capsys)["error"]["message"]


def test_verify_dry_run_json_does_not_open_scope(monkeypatch, capsys):
    import pyvisa

    def fail_open(*args, **kwargs):
        raise AssertionError("dry-run must not access VISA")

    monkeypatch.setattr(pyvisa, "ResourceManager", fail_open)
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main(["identify", "--dry-run", "--json", "--model", "keysight-dsox4024a"]) == 0

    payload = _json_stdout(capsys)
    assert isinstance(payload, dict)
    assert type(payload["schema_version"]) is int
    assert payload["schema_version"] == 2
    assert payload["ok"] is True
    assert payload["command"] == "identify"
    assert payload["mode"] == "dry_run"
    assert payload["scpi"]["planned"] == ["*IDN?"]
    assert payload["scpi"]["sent"] == []
    assert payload["files"] == []
    assert payload["system_error"] is None
    assert payload["error"] is None
    assert isinstance(payload["idn"], dict)
    assert payload["idn"]["model"] == "DSOX4024A"
    assert payload["backend"] is None
    # Capability details are covered by test_introspection_cli.py.
    assert isinstance(payload["capabilities"], dict)
    assert isinstance(payload["result"], dict)
    assert isinstance(payload["result"]["idn"], dict)
    assert payload["result"]["idn"]["model"] == "DSOX4024A"
    assert isinstance(payload["result"]["capabilities"], dict)
    assert payload["result"]["backend"] is None
    assert payload["result"]["timeout_ms"] is None


def test_one_shot_live_flag_is_rejected_before_backend_open(monkeypatch, capsys):
    import pytest

    def unexpected_open(*args, **kwargs):
        raise AssertionError("parser rejection must precede backend open")

    monkeypatch.setattr(runtime, "_open_scope", unexpected_open)
    for mode in ([], ["--simulate"], ["--dry-run"]):
        with pytest.raises(SystemExit) as exc:
            cli.main(["identify", *mode, "--live", "--json"])
        assert exc.value.code == 2
        assert "unrecognized arguments: --live" in capsys.readouterr().err


def test_simulate_json_error_is_single_json_object(capsys):
    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--channel",
                "5",
                "--item",
                "vpp",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["mode"] == "simulate"
    assert "channel 5 is not available" in payload["error"]["message"]


def test_simulate_json_backend_error_keeps_single_json_object(monkeypatch, capsys):
    backend = SimulatorBackend(
        query_failures={
            ":MEASure:VPP? CHANnel1": OscilloscopeError("configured measurement failure")
        }
    )
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

    assert cli.main(["measure", "--simulate", "--json", "--channel", "1", "--item", "vpp"]) == 1

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["mode"] == "simulate"
    assert payload["error"]["message"] == "configured measurement failure"
    assert payload["scpi"]["sent"] == ["*IDN?", ":SYSTem:ERRor?", ":MEASure:VPP? CHANnel1"]


def test_check_error_simulate_json_can_report_injected_error_queue(monkeypatch, capsys):
    backend = SimulatorBackend(system_errors=['-113,"Undefined header"'])
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

    assert cli.main(["check-error", "--simulate", "--json", "--all", "--max-reads", "3"]) == 1

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["mode"] == "simulate"
    assert payload["result"]["entries"] == [
        {
            "code": -113,
            "is_error": True,
            "message": "Undefined header",
            "raw": '-113,"Undefined header"',
        },
        {
            "code": 0,
            "is_error": False,
            "message": "No error",
            "raw": '+0,"No error"',
        },
    ]
    assert payload["system_error"]["code"] == 0
    assert payload["scpi"]["sent"] == [":SYSTem:ERRor?", ":SYSTem:ERRor?"]



def test_control_simulate_json_reports_action_and_system_error(capsys):
    assert cli.main(["run", "--simulate", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["action"] == "run"
    assert payload["result"]["command"] == ":RUN"
    assert payload["system_error"]["code"] == 0
    assert payload["result"]["human_output"]


def test_model_help_distinguishes_one_shot_planning_from_worker(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["identify", "--help"])

    assert excinfo.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "--model MODEL" in help_text
    assert "dry-run and simulation planning" in help_text
    assert "live execution uses the identity detected from *IDN?" in help_text
    assert "expected live worker model" not in help_text

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["worker", "--help"])

    assert excinfo.value.code == 0
    worker_help_text = " ".join(capsys.readouterr().out.split())
    assert "--model MODEL" in worker_help_text
    assert "dry-run and simulation planning" not in worker_help_text
