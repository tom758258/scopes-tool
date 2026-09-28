"""CLI and Worker acceptance for model-aware Tek workflows."""

import json
import pytest
from scopes_tool_cli import cli
from tests.cli.test_worker_cli import _runtime, _execute_worker_job

MODELS = ("tektronix-tbs2074b", "tektronix-tds2024b", "tektronix-tbs1052b")


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
def test_cli_workflows_simulate_and_plan(model, command, arguments, tmp_path, capsys):
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
def test_worker_native_workflows(model, command, arguments):
    job, result = _execute_worker_job(_runtime(model=model), command, arguments)
    assert job.state == "succeeded", result
    assert job.result["system_error"] is None
    assert result["result"]["post_command_status"]["complete"] is True
    assert "ALLEv?" in job.result["scpi"]["sent"]
