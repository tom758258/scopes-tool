import json

from scopes_tool_cli import cli, runtime


def test_triggered_capture_series_dry_run_uses_one_representative_cycle(
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
            "triggered-capture-series",
            "--dry-run",
            "--json",
            "--channel",
            "1",
            "--channel",
            "2",
            "--points",
            "1000",
            "--format",
            "byte",
            "--count",
            "100",
            "--trigger-timeout-seconds",
            "5",
            "--interval-seconds",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["command"] == "triggered-capture-series"
    assert payload["result"]["channels"] == [1, 2]
    assert payload["result"]["requested_count"] == 100
    assert payload["result"]["trigger_timeout_seconds"] == 5
    assert payload["result"]["interval_seconds"] == 1
    assert payload["scpi"]["planned"].count(":SINGle") == 1
    assert payload["scpi"]["planned"].count(":OPERegister:CONDition?") == 1
    assert payload["scpi"]["planned"].count(":SYSTem:ERRor?") == 1
    assert payload["scpi"]["planned"].count(":WAVeform:DATA?") == 2
    assert not output_dir.exists()


def test_triggered_capture_series_simulator_smoke(tmp_path, capsys):
    output_dir = tmp_path / "simulated"

    code = cli.main(
        [
            "triggered-capture-series",
            "--simulate",
            "--json",
            "--channel",
            "1",
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
    assert (output_dir / "waveform_0001.csv").exists()
    assert (output_dir / "waveform_0002_meta.json").exists()
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "scpi.log").exists()

