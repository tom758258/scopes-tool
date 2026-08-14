import json

from scopes_tool_cli import cli, runtime
from scopes_tool_core.operations import OperationResult


def test_measure_until_dry_run_plans_one_iteration_without_hardware_or_files(
    monkeypatch, tmp_path, capsys
):
    output_dir = tmp_path / "planned"
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("opened"))
        ),
    )

    code = cli.main(
        [
            "measure-until",
            "--dry-run",
            "--json",
            "--channel",
            "1",
            "--item",
            "vpp",
            "--operator",
            "gt",
            "--threshold",
            "3.3",
            "--timeout-seconds",
            "600",
            "--interval-seconds",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["command"] == "measure-until"
    assert payload["result"]["channel"] == 1
    assert payload["result"]["item"] == "vpp"
    assert payload["result"]["operator"] == "gt"
    assert payload["result"]["threshold"] == 3.3
    assert payload["result"]["timeout_seconds"] == 600
    assert payload["result"]["interval_seconds"] == 1
    assert payload["scpi"]["planned"] == [
        ":MEASure:VPP? CHANnel1",
        ":SYSTem:ERRor?",
    ]
    assert not output_dir.exists()


def test_measure_until_simulator_smoke(tmp_path, capsys):
    output_dir = tmp_path / "simulated"

    code = cli.main(
        [
            "measure-until",
            "--simulate",
            "--json",
            "--channel",
            "1",
            "--item",
            "vpp",
            "--operator",
            "gt",
            "--threshold",
            "0",
            "--timeout-seconds",
            "1",
            "--interval-seconds",
            "0",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["termination_reason"] == "condition_met"
    assert payload["result"]["completed_count"] == 1
    assert (output_dir / "measurements.csv").exists()
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "scpi.log").exists()


def test_measure_until_cli_preserves_timeout_exit_and_result(monkeypatch, tmp_path, capsys):
    timeout_result = {
        "status": "error",
        "channel": 1,
        "item": "vpp",
        "operator": "gt",
        "threshold": 3.3,
        "timeout_seconds": 1.0,
        "interval_seconds": 0.0,
        "completed_count": 1,
        "matched": False,
        "matched_sample": None,
        "termination_reason": "condition_timeout",
        "output_dir": str(tmp_path),
        "csv_path": str(tmp_path / "measurements.csv"),
        "manifest_path": str(tmp_path / "manifest.json"),
        "scpi_log_path": str(tmp_path / "scpi.log"),
        "error": {"type": "condition_timeout", "message": "timed out"},
    }
    monkeypatch.setattr(
        cli,
        "run_measure_until",
        lambda *args, **kwargs: OperationResult(1, timeout_result),
    )

    code = cli.main(
        [
            "measure-until",
            "--simulate",
            "--json",
            "--channel",
            "1",
            "--item",
            "vpp",
            "--operator",
            "gt",
            "--threshold",
            "3.3",
            "--timeout-seconds",
            "1",
            "--interval-seconds",
            "0",
            "--output-dir",
            str(tmp_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["ok"] is False
    assert payload["result"]["status"] == "error"
    assert payload["result"]["termination_reason"] == "condition_timeout"
    assert payload["result"]["error"]["type"] == "condition_timeout"
