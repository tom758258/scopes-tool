import json

import pytest

from scopes_tool_cli import cli, runtime


def test_triggered_measure_loop_dry_run_uses_one_representative_cycle(
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
            "triggered-measure-loop",
            "--dry-run",
            "--json",
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
            "100",
            "--trigger-timeout-seconds",
            "5",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["command"] == "triggered-measure-loop"
    assert payload["result"]["requested_count"] == 100
    assert payload["result"]["completed_count"] == 0
    assert payload["scpi"]["planned"] == [
        ":SINGle",
        ":OPERegister:CONDition?",
        ":MEASure:VPP? CHANnel1",
        ":MEASure:FREQuency? CHANnel1",
        ":MEASure:VPP? CHANnel2",
        ":MEASure:FREQuency? CHANnel2",
        ":MEASure:PHASe? CHANnel1,CHANnel2",
        ":SYSTem:ERRor?",
    ]
    assert not output_dir.exists()


def test_triggered_measure_loop_simulator_happy_path(tmp_path, capsys):
    output_dir = tmp_path / "simulated"

    code = cli.main(
        [
            "triggered-measure-loop",
            "--simulate",
            "--json",
            "--channel",
            "1",
            "--items",
            "vpp",
            "--count",
            "2",
            "--trigger-timeout-seconds",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["completed_count"] == 2
    assert payload["scpi"]["sent"].count(":SINGle") == 2
    assert payload["scpi"]["sent"].count(":SYSTem:ERRor?") == 3
    assert (output_dir / "measurements.csv").exists()
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "scpi.log").exists()


def test_triggered_measure_loop_no_save_returns_last_measurement_without_files(
    tmp_path, capsys
):
    output_dir = tmp_path / "not-created"

    code = cli.main(
        [
            "triggered-measure-loop",
            "--simulate",
            "--json",
            "--channel",
            "1",
            "--items",
            "vpp",
            "--count",
            "2",
            "--trigger-timeout-seconds",
            "1",
            "--output-dir",
            str(output_dir),
            "--no-save",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["files"] == []
    assert payload["result"]["completed_count"] == 2
    assert payload["result"]["last_measurement"]["index"] == 2
    assert "cycles" not in payload["result"]
    assert not output_dir.exists()


def test_triggered_measure_loop_requires_count_and_timeout(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["triggered-measure-loop", "--dry-run", "--channel", "1"])

    assert exc_info.value.code == 2
    error = capsys.readouterr().err
    assert "--count" in error
    assert "--trigger-timeout-seconds" in error
