import json

import pytest

from scopes_tool_cli import cli, runtime


@pytest.mark.parametrize(
    ("argv", "target"),
    [
        (["measure-clear"], ":MEASure:CLEar"),
        (["measure-show", "--on"], ":MEASure:SHOW ON"),
        (["measure-show", "--query"], ":MEASure:SHOW?"),
        (["measure-source", "--source-channel", "1"], ":MEASure:SOURce CHANnel1"),
        (["measure-source", "--source-channel", "1", "--source2-channel", "2"], ":MEASure:SOURce CHANnel1,CHANnel2"),
        (["measure-source", "--query"], ":MEASure:SOURce?"),
        (["measure-window", "--window", "gate"], ":MEASure:WINDow GATE"),
        (["measure-window", "--query"], ":MEASure:WINDow?"),
    ],
)
@pytest.mark.parametrize("mode", ["--dry-run", "--simulate"])
def test_measurement_control_json_modes(argv, target, mode, capsys):
    assert cli.main([*argv, mode, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    scpi_key = "planned" if mode == "--dry-run" else "sent"
    assert payload["ok"] is True
    assert target in payload["scpi"][scpi_key]
    assert payload["result"]["command"] == target


@pytest.mark.parametrize(
    "argv",
    [
        ["measure-show", "--off", "--dry-run", "--json"],
        ["measure-source", "--dry-run", "--json"],
        ["measure-source", "--query", "--source-channel", "1", "--dry-run", "--json"],
        ["measure-source", "--source-channel", "5", "--model", "keysight-dsox2004a", "--dry-run", "--json"],
    ],
)
def test_measurement_control_validation_before_open(argv, monkeypatch, capsys):
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda *args, **kwargs: pytest.fail("opened VISA")))
    assert cli.main(argv) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


@pytest.mark.parametrize("argv", [["measure-show"], ["measure-window"]])
def test_measurement_control_missing_action_rejected(argv):
    with pytest.raises(SystemExit):
        cli.main(argv)


def test_measurement_window_invalid_value_rejected():
    with pytest.raises(SystemExit):
        cli.main(["measure-window", "--window", "screen", "--dry-run"])


def test_measurement_control_text_output_smoke(capsys):
    assert cli.main(["measure-show", "--query", "--simulate"]) == 0
    assert "Command: :MEASure:SHOW?" in capsys.readouterr().out


def test_measure_stats_dry_run_rejects_unsupported_2000x(capsys, monkeypatch):
    monkeypatch.setattr(
        runtime.Oscilloscope, "open", staticmethod(lambda *args, **kwargs: pytest.fail("opened VISA"))
    )
    argv = [
        "measure-stats",
        "--dry-run",
        "--json",
        "--model",
        "keysight-dsox2004a",
        "--channel",
        "1",
        "--items",
        "vpp,frequency",
    ]
    assert cli.main(argv) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "capability profile" in payload["error"]["message"].lower()
    assert "statistics" in payload["error"]["message"].lower()
    planned = payload["scpi"]["planned"]
    assert not any("STATistics" in cmd for cmd in planned)
    assert not any("RESults" in cmd for cmd in planned)


def test_measure_stats_dry_run_generates_planned_scpi_on_supported_model(capsys):
    argv = [
        "measure-stats",
        "--dry-run",
        "--json",
        "--model",
        "keysight-dsox4024a",
        "--channel",
        "1",
        "--items",
        "vpp,frequency",
    ]
    assert cli.main(argv) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    planned = payload["scpi"]["planned"]
    assert any("CLEar" in cmd for cmd in planned)
    assert any("RESults" in cmd for cmd in planned)
