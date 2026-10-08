import json
from pathlib import Path

from scopes_tool_cli import cli, runtime
from scopes_tool_core.identity import physical_model_for_id
from scopes_tool_core.simulator_backend import SimulatorBackend
from tests.cli._agent_safe_cli_support import _json_stdout


def test_acquisition_check_dry_run_json_reports_plan_for_target_models(monkeypatch, capsys, tmp_path):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    for model in (
        "keysight-dsox4024a",
        "keysight-dsox4034a",
        "keysight-dsox3024a",
        "keysight-dsox2004a",
    ):
        output_dir = tmp_path / model
        assert (
            cli.main(
                [
                    "acquisition-check",
                    "--dry-run",
                    "--json",
                    "--model",
                    model,
                    "--output-dir",
                    str(output_dir),
                ]
            )
            == 0
        )

        payload = _json_stdout(capsys)
        planned = payload["scpi"]["planned"]
        assert payload["mode"] == "dry_run"
        assert payload["idn"]["model"] == physical_model_for_id(
            model
        ).canonical_model
        assert payload["files"] == [
            {"kind": "report", "path": str(output_dir / "report.json")},
            {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
        ]
        assert planned == [
            "*IDN?",
            ":ACQuire:TYPE?",
            ":ACQuire:COUNt?",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE NORMal",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE AVERage",
            ":ACQuire:COUNt 16",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE?",
            ":ACQuire:COUNt?",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE HRESolution",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE PEAK",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE?",
            ":ACQuire:COUNt?",
            ":SYSTem:ERRor?",
        ]
        assert not output_dir.exists()


def test_acquisition_check_simulate_json_writes_report_and_scpi_log(capsys, tmp_path):
    output_dir = tmp_path / "acq-check"

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    report_path = output_dir / "report.json"
    scpi_log_path = output_dir / "scpi.log"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["final_acquisition"] == {"type": "peak", "count": 16}
    assert [step["name"] for step in payload["result"]["steps"]] == [
        "initial-query",
        "set-normal",
        "set-average",
        "post-average-query",
        "set-high-resolution",
        "set-peak",
        "final-query",
    ]
    assert report["status"] == "completed"
    assert report["idn"]["model"] == "DSOX4034A"
    assert report["final_acquisition"] == {"type": "peak", "count": 16}
    assert scpi_log_path.exists()
    assert ":ACQuire:TYPE PEAK" in payload["scpi"]["sent"]


def test_acquisition_check_rejects_nonempty_output_dir(capsys, tmp_path):
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    (output_dir / "old.txt").write_text("old", encoding="utf-8")

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "output directory must be empty" in payload["error"]["message"]


def test_acquisition_check_system_error_keeps_report(capsys, tmp_path):
    output_dir = tmp_path / "system-error"

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--simulate-system-error",
                "0",
                "--simulate-system-error",
                "-113",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["result"]["status"] == "instrument_error"
    assert report["status"] == "instrument_error"
    assert report["steps"][0]["system_error"]["code"] == -113


def test_acquisition_check_check_only_json_reports_initial_state_and_no_writes(
    capsys, tmp_path
):
    output_dir = tmp_path / "check-only"

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--check-only",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["result"]["check_only"] is True
    assert payload["result"]["termination_reason"] == "check_only"
    assert payload["result"]["initial_acquisition"] == {"type": "normal", "count": 8}
    assert [step["name"] for step in payload["result"]["steps"]] == [
        "initial-query",
    ]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":SYSTem:ERRor?",
        ":ACQuire:TYPE?",
        ":ACQuire:COUNt?",
        ":SYSTem:ERRor?",
    ]
    assert report["check_only"] is True
    assert report["termination_reason"] == "check_only"
    assert report["initial_acquisition"] == {"type": "normal", "count": 8}


def test_acquisition_check_stop_on_error_stops_after_first_error(monkeypatch, capsys, tmp_path):
    output_dir = tmp_path / "stop-on-error"
    backend = SimulatorBackend(
        system_errors=['+0,"No error"', '+0,"No error"', '-113,"Undefined header"']
    )
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--stop-on-error",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["result"]["stopped_on_error"] is True
    assert payload["result"]["termination_reason"] == "stopped_on_error"
    assert [step["name"] for step in payload["result"]["steps"]] == [
        "initial-query",
        "set-normal",
    ]
    assert report["stopped_on_error"] is True
    assert report["termination_reason"] == "stopped_on_error"


def test_acquisition_check_restore_type_attempts_restore_and_records_result(
    monkeypatch, capsys, tmp_path
):
    output_dir = tmp_path / "restore-type"
    backend = SimulatorBackend()
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--restore-type",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["result"]["restore"]["requested"] is True
    assert payload["result"]["restore"]["attempted"] is True
    assert payload["result"]["restore"]["succeeded"] is True
    assert report["restore"]["requested"] is True
    assert report["restore"]["attempted"] is True
    assert report["restore"]["succeeded"] is True


def test_hardware_report_renders_acquisition_and_smoke_reports(capsys, tmp_path):
    acq_report = tmp_path / "acq.json"
    smoke_report = tmp_path / "smoke.json"
    acq_report.write_text(
        json.dumps(
            {
                "status": "completed",
                "resource": "USB0::FAKE::INSTR",
                "backend": "Keysight simulator",
                "idn": {
                    "model": "DSOX4034A",
                    "firmware": "07.20",
                },
                "average_count": 16,
                "check_only": False,
                "stopped_on_error": False,
                "initial_acquisition": {"type": "normal", "count": 8},
                "restore": {
                    "requested": True,
                    "attempted": True,
                    "succeeded": True,
                    "error": None,
                },
                "termination_reason": "completed",
                "steps": [
                    {
                        "name": "initial-query",
                        "commands": [":ACQuire:TYPE?", ":ACQuire:COUNt?", ":SYSTem:ERRor?"],
                        "system_error": {"is_error": False},
                    }
                ],
                "final_acquisition": {"type": "peak", "count": 16},
                "files": [{"kind": "report", "path": "report.json"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    smoke_report.write_text(
        json.dumps(
            {
                "status": "completed",
                "resource": "USB0::FAKE::INSTR",
                "backend": "Keysight simulator",
                "idn": {
                    "model": "DSOX4034A",
                    "firmware": "07.20",
                },
                "doctor": {},
                "measurements": [],
                "capture": {},
                "screenshot": {},
                "post_check_error": {"code": 0, "message": "No error"},
                "warnings": [],
                "files": [{"kind": "report", "path": "report.json"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    assert cli.main(["hardware-report", str(acq_report), str(smoke_report)]) == 0
    out = capsys.readouterr().out
    assert "Hardware Report" in out
    assert "acquisition-check" in out
    assert "smoke" in out
    assert "Restore Requested: True" in out
    assert "Post Check Error" in out


def test_doctor_dry_run_json_reports_snapshot_plan(capsys):
    assert cli.main(["doctor", "--dry-run", "--json", "--model", "keysight-dsox4034a"]) == 0

    payload = _json_stdout(capsys)
    planned = payload["scpi"]["planned"]
    assert planned[0] == "*IDN?"
    assert ":ACQuire:TYPE?" in planned
    assert ":CHANnel4:BWLimit?" in planned
    assert planned[-1] == ":SYSTem:ERRor?"
    assert payload["result"]["channels"] == []


def test_doctor_simulate_json_reports_four_channels(capsys):
    assert cli.main(["doctor", "--simulate", "--json", "--model", "keysight-dsox4034a"]) == 0

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["backend"] == "Keysight simulator"
    assert result["timeout_ms"] == 2000
    assert result["acquisition"] == {"type": "normal", "count": 8}
    assert len(result["channels"]) == 4
    assert result["channels"][0]["channel"] == 1
    assert result["timebase"]["scale_seconds_per_division"] == 0.001
    assert result["edge_trigger"]["source_channel"] == 1
    assert payload["system_error"]["is_error"] is False


def test_smoke_dry_run_json_reports_files_without_writing(capsys, tmp_path):
    output_dir = tmp_path / "smoke"

    assert (
        cli.main(
            [
                "smoke",
                "--dry-run",
                "--json",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["status"] == "planned"
    assert payload["files"] == [
        {"kind": "report", "path": str(output_dir / "report.json")},
        {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
        {"kind": "csv", "path": str(output_dir / "capture.csv")},
        {"kind": "metadata", "path": str(output_dir / "capture_meta.json")},
        {"kind": "png", "path": str(output_dir / "screen.png")},
    ]
    assert not output_dir.exists()


def test_smoke_dry_run_json_default_output_dir_does_not_crash(capsys):
    assert cli.main(["smoke", "--dry-run", "--json"]) == 0

    payload = _json_stdout(capsys)
    output_dir = Path("data") / "hardware_smoke" / "DRY-RUN"
    assert payload["result"]["status"] == "planned"
    assert payload["result"]["output_dir"] == str(output_dir)
    assert payload["files"][0] == {
        "kind": "report",
        "path": str(output_dir / "report.json"),
    }


def test_smoke_simulate_json_writes_report_and_artifacts(capsys, tmp_path):
    output_dir = tmp_path / "smoke"

    assert (
        cli.main(["smoke", "--simulate", "--json", "--output-dir", str(output_dir)])
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["status"] == "completed"
    for name in ("report.json", "scpi.log", "capture.csv", "capture_meta.json", "screen.png"):
        assert (output_dir / name).exists()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["doctor"]["acquisition"]["type"] == "normal"
    assert report["capture"]["actual_points"] == 1000
    assert report["screenshot"]["byte_count"] > 1000


def test_smoke_simulate_binary_failure_exits_one_and_keeps_report(capsys, tmp_path):
    output_dir = tmp_path / "smoke"

    assert (
        cli.main(
            [
                "smoke",
                "--simulate",
                "--json",
                "--simulate-binary-transfer-failure",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["result"]["status"] == "error"
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "error"
    assert report["error"] == "simulated binary transfer failure"
