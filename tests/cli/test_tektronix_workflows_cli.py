"""CLI and Worker acceptance for model-aware Tek workflows."""

import json
import pytest
from scopes_tool_cli import cli
from tests.cli.test_worker_cli import _runtime, _execute_worker_job

MODELS = ("tektronix-tbs2074", "tektronix-tds2024b", "tektronix-tbs1052b")


def _set_tbs2074_delay_mode_on(monkeypatch):
    from scopes_tool_core.tektronix_simulator import TektronixSimulatorBackend

    initialize = TektronixSimulatorBackend.__post_init__

    def initialize_with_delay_mode_on(backend):
        initialize(backend)
        backend.tek_settings["HORIZONTAL:DELAY:MODE"] = "ON"

    monkeypatch.setattr(
        TektronixSimulatorBackend, "__post_init__", initialize_with_delay_mode_on
    )


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("command,arguments", [
    ("doctor", []),
    ("cleanup", []),
    ("acquisition-check", []),
    ("measure-sweep", ["--channel", "1", "--items", "vpp,frequency"]),
    ("measure-log", ["--channel", "1", "--count", "1", "--interval-seconds", "0"]),
    ("measure-until", ["--channel", "1", "--item", "vpp", "--operator", "gt", "--threshold", "0", "--timeout-seconds", "1"]),
    ("capture-batch", ["--channel", "1", "--count", "1"]),
    ("capture-until", ["--channel", "1", "--condition-channel", "1", "--metric", "max", "--operator", "gt", "--threshold", "0", "--timeout-seconds", "1"]),
    ("capture-monitor", ["--channel", "1", "--count", "1"]),
    ("triggered-capture-series", ["--channel", "1", "--count", "1", "--trigger-timeout-seconds", "1"]),
    ("triggered-measure-loop", ["--channel", "1", "--count", "1", "--trigger-timeout-seconds", "1"]),
])
def test_cli_workflows_simulate_and_plan(model, command, arguments, tmp_path, capsys, monkeypatch):
    if model == "tektronix-tbs2074" and command == "doctor":
        _set_tbs2074_delay_mode_on(monkeypatch)
    for mode in ("--dry-run", "--simulate"):
        output = [] if command in {"doctor", "cleanup", "measure-sweep"} else ["--output-dir", str(tmp_path / mode)]
        code = cli.main([command, *arguments, *output, mode, "--model", model, "--json"])
        captured = capsys.readouterr()
        assert code == 0, captured.out + captured.err
        payload = json.loads(captured.out)
        commands = payload["scpi"]["planned" if mode == "--dry-run" else "sent"]
        assert commands
        assert not any(c.upper().startswith((":SYST", ":WAV", ":ACQ", ":OPER", ":MEAS", ":SING")) for c in commands)
        assert "ALLEv?" in commands
        if mode == "--simulate":
            assert payload["system_error"] is None


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("command,arguments", [
    ("doctor", {}),
    ("measure-log", {"channel": [1], "count": 1, "save_results": False}),
    ("triggered-measure-loop", {"channel": [1], "count": 1, "trigger_timeout_seconds": 1, "save_results": False}),
])
def test_worker_native_workflows(model, command, arguments, monkeypatch):
    if model == "tektronix-tbs2074" and command == "doctor":
        _set_tbs2074_delay_mode_on(monkeypatch)
    job, result = _execute_worker_job(_runtime(model=model), command, arguments)
    assert job.state == "succeeded", result
    assert job.result["system_error"] is None
    assert result["result"]["post_command_status"]["complete"] is True
    assert "ALLEv?" in job.result["scpi"]["sent"]


def test_cli_tbs2074_cursor_set_uses_core_tektronix_commands(capsys, monkeypatch):
    _set_tbs2074_delay_mode_on(monkeypatch)
    assert cli.main(
        [
            "cursor",
            "--simulate",
            "--json",
            "--model",
            "tektronix-tbs2074",
            "--source-channel",
            "2",
            "--x1",
            "0",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    commands = payload["scpi"]["sent"]
    assert "SELect:CONTROl CH2" in commands
    assert "CURSor:FUNCtion VBArs" in commands
    assert not any(":MARKer:" in command for command in commands)


def test_worker_tbs2074_cursor_set_uses_core_tektronix_commands(monkeypatch):
    _set_tbs2074_delay_mode_on(monkeypatch)
    job, result = _execute_worker_job(
        _runtime(model="tektronix-tbs2074"),
        "cursor",
        {"source_channel": 2, "x1": 0.0},
    )

    assert result["state"] == "succeeded"
    commands = job.result["scpi"]["sent"]
    assert "SELect:CONTROl CH2" in commands
    assert "CURSor:FUNCtion VBArs" in commands
    assert not any(":MARKer:" in command for command in commands)


@pytest.mark.parametrize("function,expected", [
    ("off", "CURSor:FUNCtion OFF"),
    ("screen", "CURSor:FUNCtion SCREEN"),
    ("waveform", "CURSor:FUNCtion WAVEform"),
    ("vbars", "CURSor:FUNCtion VBArs"),
    ("hbars", "CURSor:FUNCtion HBArs"),
])
def test_worker_tbs2074_cursor_function_passes_through(function, expected):
    job, result = _execute_worker_job(
        _runtime(model="tektronix-tbs2074"),
        "cursor",
        {"function": function},
    )

    assert result["state"] == "succeeded"
    assert expected in job.result["scpi"]["sent"]
    assert job.result["result"]["function"] == function


def test_worker_tbs2074_rejects_invalid_cursor_function():
    _job, result = _execute_worker_job(
        _runtime(model="tektronix-tbs2074"),
        "cursor",
        {"source_channel": 1, "function": "vbars", "y1": 0.0},
    )

    assert result["state"] == "failed"
    assert "does not accept Y positions" in result["error"]["message"]


@pytest.mark.parametrize("mode", ["--dry-run", "--simulate"])
def test_tbs2074_trigger_holdoff_accepts_20ns(mode, capsys):
    assert cli.main([
        "trigger-holdoff", mode, "--json", "--model", "tektronix-tbs2074",
        "--seconds", "2e-8",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    commands = payload["scpi"]["planned" if mode == "--dry-run" else "sent"]
    assert "TRIGger:A:HOLDOff:TIMe 2e-08" in commands


def test_keysight_trigger_holdoff_keeps_40ns_minimum(capsys):
    assert cli.main([
        "trigger-holdoff", "--dry-run", "--json", "--model", "keysight-dsox4024a",
        "--seconds", "2e-8",
    ]) == 1
    assert "between 40e-9 and 10" in json.loads(capsys.readouterr().out)["error"]["message"]


def test_worker_tbs2074_trigger_holdoff_accepts_20ns():
    job, result = _execute_worker_job(
        _runtime(model="tektronix-tbs2074"),
        "trigger-holdoff",
        {"seconds": 20e-9},
    )
    assert result["state"] == "succeeded"
    assert "TRIGger:A:HOLDOff:TIMe 2e-08" in job.result["scpi"]["sent"]
