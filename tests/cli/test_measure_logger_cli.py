import json

from scopes_tool_cli import cli


def test_measure_log_cli_dry_run_json(capsys):
    args = [
        "measure-log",
        "--dry-run",
        "--json",
        "--model",
        "keysight-dsox4024a",
        "--channel",
        "1",
        "--channel",
        "2",
        "--items",
        "vpp,frequency",
        "--pair",
        "1:2",
        "--pair-items",
        "phase",
        "--count",
        "5",
        "--interval-seconds",
        "0.5",
        "--output-dir",
        "data/measure_logs/DRY-RUN",
    ]

    code = cli.main(args)
    assert code == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["ok"] is True
    assert payload["command"] == "measure-log"
    assert payload["mode"] == "dry_run"
    assert payload["result"]["status"] == "planned"
    assert payload["result"]["channels"] == [1, 2]
    assert payload["result"]["items"] == ["vpp", "frequency"]
    assert payload["result"]["pairs"] == ["1:2"]
    assert payload["result"]["pair_items"] == ["phase"]
    assert payload["result"]["interval_seconds"] == 0.5
    assert payload["result"]["requested_count"] == 5
    assert payload["scpi"]["planned"] == [
        ":MEASure:VPP? CHANnel1",
        ":MEASure:FREQuency? CHANnel1",
        ":MEASure:VPP? CHANnel2",
        ":MEASure:FREQuency? CHANnel2",
        ":MEASure:PHASe? CHANnel1,CHANnel2",
        ":SYSTem:ERRor?",
    ]
    assert len(payload["files"]) == 3
    assert payload["files"][0]["kind"] == "csv"
    assert payload["files"][1]["kind"] == "manifest"
    assert payload["files"][2]["kind"] == "scpi_log"


def test_measure_log_cli_dry_run_json_rejects_unbounded_run(capsys):
    code = cli.main(
        [
            "measure-log",
            "--dry-run",
            "--json",
            "--model",
            "keysight-dsox4024a",
            "--channel",
            "1",
        ]
    )

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "requires --count or --duration-seconds" in payload["error"]["message"]


def test_measure_log_cli_simulate_json(capsys, tmp_path):
    output_dir = tmp_path / "simulated_log"
    args = [
        "measure-log",
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox4024a",
        "--channel",
        "1",
        "--channel",
        "2",
        "--items",
        "vpp,frequency",
        "--pair",
        "1:2",
        "--pair-items",
        "phase",
        "--count",
        "2",
        "--interval-seconds",
        "0.01",
        "--output-dir",
        str(output_dir),
    ]

    code = cli.main(args)
    assert code == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["ok"] is True
    assert payload["command"] == "measure-log"
    assert payload["mode"] == "simulate"
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["completed_rows"] == 2
    assert payload["result"]["channels"] == [1, 2]
    assert payload["result"]["items"] == ["vpp", "frequency"]
    assert payload["result"]["pairs"] == ["1:2"]
    assert payload["result"]["pair_items"] == ["phase"]
    assert payload["result"]["last_measurement"]["index"] == 2
    assert "rows" not in payload["result"]
    assert payload["system_error"]["raw"] == '+0,"No error"'

    csv_file = output_dir / "measurements.csv"
    manifest_file = output_dir / "manifest.json"
    scpi_log_file = output_dir / "scpi.log"

    assert csv_file.exists()
    assert manifest_file.exists()
    assert scpi_log_file.exists()

    with manifest_file.open("r", encoding="utf-8") as handle:
        manifest_data = json.load(handle)
    assert manifest_data["status"] == "completed"
    assert manifest_data["completed_rows"] == 2
    assert len(manifest_data["rows"]) == 2
    assert manifest_data["channels"] == [1, 2]
    assert manifest_data["items"] == ["vpp", "frequency"]
    assert manifest_data["pairs"] == ["1:2"]
    assert manifest_data["pair_items"] == ["phase"]


def test_measure_log_cli_no_save_returns_last_measurement_without_files(capsys, tmp_path):
    output_dir = tmp_path / "not-created"

    code = cli.main(
        [
            "measure-log",
            "--simulate",
            "--json",
            "--channel",
            "1",
            "--items",
            "vpp",
            "--count",
            "2",
            "--interval-seconds",
            "0",
            "--output-dir",
            str(output_dir),
            "--no-save",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["files"] == []
    assert payload["result"]["completed_rows"] == 2
    assert payload["result"]["last_measurement"]["index"] == 2
    assert not output_dir.exists()


def test_measure_log_cli_simulate_fails_on_duplicate_channel(capsys):
    args = [
        "measure-log",
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox4024a",
        "--pair",
        "1:1",
        "--count",
        "1",
        "--interval-seconds",
        "0.01",
    ]

    code = cli.main(args)
    assert code == 1

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["ok"] is False
    assert "error" in payload
    assert "source and reference channels must differ" in payload["error"]["message"]


def test_measure_log_cli_simulate_json_stops_on_injected_system_error(
    capsys, tmp_path
):
    output_dir = tmp_path / "simulated_error_log"

    code = cli.main(
        [
            "measure-log",
            "--simulate",
            "--json",
            "--model",
            "keysight-dsox4024a",
            "--simulate-system-error",
            "0",
            "--simulate-system-error",
            "-113",
            "--channel",
            "1",
            "--items",
            "vpp",
            "--count",
            "3",
            "--interval-seconds",
            "0",
            "--output-dir",
            str(output_dir),
            "--stop-on-error",
        ]
    )

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["result"]["status"] == "instrument_error"
    assert payload["result"]["completed_rows"] == 1
    assert payload["result"]["last_measurement"]["system_error"]["code"] == -113
    assert payload["system_error"]["code"] == -113

    manifest_data = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "instrument_error"
    assert manifest_data["completed_rows"] == 1
