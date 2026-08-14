import json

import pytest

from scopes_tool_cli import cli, runtime


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


@pytest.mark.parametrize(
    ("slope", "command"),
    [
        ("positive", "POSitive"),
        ("negative", "NEGative"),
        ("either", "EITHer"),
        ("alternate", "ALTernate"),
    ],
)
def test_trigger_edge_slope_dry_run_json(capsys, slope, command):
    assert cli.main([
        "trigger-edge-slope", "--dry-run", "--json", "--model", "keysight-dsox2004a",
        "--slope", slope,
    ]) == 0

    payload = _payload(capsys)
    assert payload["result"] == {
        "operation": "set",
        "command": f":TRIGger:EDGE:SLOPe {command}",
        "slope": slope,
    }
    assert payload["scpi"]["planned"] == [
        f":TRIGger:EDGE:SLOPe {command}", ":SYSTem:ERRor?"
    ]


def test_trigger_edge_slope_query_dry_run_and_text_does_not_open_scope(capsys, monkeypatch):
    monkeypatch.setattr(runtime, "_open_scope", lambda *_a, **_kw: pytest.fail("opened scope"))
    assert cli.main([
        "trigger-edge-slope", "--dry-run", "--json", "--model", "keysight-dsox3024a", "--query",
    ]) == 0
    assert _payload(capsys)["result"] == {
        "operation": "query", "command": ":TRIGger:EDGE:SLOPe?"
    }

    assert cli.main([
        "trigger-edge-slope", "--dry-run", "--model", "keysight-dsox3024a", "--slope", "either",
    ]) == 0
    output = capsys.readouterr().out
    assert "Command: :TRIGger:EDGE:SLOPe EITHer" in output
    assert "Command: :SYSTem:ERRor?" not in output


def test_trigger_edge_slope_simulate_configure_and_query(capsys):
    assert cli.main([
        "trigger-edge-slope", "--simulate", "--json", "--model", "keysight-dsox4034a",
        "--slope", "alternate",
    ]) == 0
    payload = _payload(capsys)
    assert {key: payload["result"][key] for key in ("operation", "command", "slope")} == {
        "operation": "set", "command": ":TRIGger:EDGE:SLOPe ALTernate", "slope": "alternate"
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:SLOPe ALTernate", ":SYSTem:ERRor?"
    ]

    assert cli.main([
        "trigger-edge-slope", "--simulate", "--json", "--model", "keysight-dsox4034a", "--query",
    ]) == 0
    payload = _payload(capsys)
    assert {key: payload["result"][key] for key in ("operation", "command", "slope", "raw_slope")} == {
        "operation": "query", "command": ":TRIGger:EDGE:SLOPe?", "slope": "positive", "raw_slope": "POS"
    }
    assert payload["scpi"]["sent"] == ["*IDN?", ":TRIGger:EDGE:SLOPe?", ":SYSTem:ERRor?"]


@pytest.mark.parametrize("arguments", [[], ["--query", "--slope", "positive"]])
def test_trigger_edge_slope_rejects_invalid_operation(capsys, arguments):
    assert cli.main(["trigger-edge-slope", "--dry-run", "--json", *arguments]) == 1
    assert _payload(capsys)["ok"] is False


@pytest.mark.parametrize("value", ["POSITIVE", "rising", "both"])
def test_trigger_edge_slope_rejects_invalid_choice(capsys, value):
    with pytest.raises(SystemExit):
        cli.main(["trigger-edge-slope", "--dry-run", "--slope", value])
    assert "invalid choice" in capsys.readouterr().err


def test_trigger_edge_level_dry_run_json_and_text(capsys, monkeypatch):
    monkeypatch.setattr(runtime, "_open_scope", lambda *_a, **_kw: pytest.fail("opened scope"))
    assert cli.main([
        "trigger-edge-level", "--dry-run", "--json", "--model", "keysight-dsox2004a",
        "--source-channel", "1", "--level-volts", "-0.25",
    ]) == 0
    payload = _payload(capsys)
    assert payload["result"] == {
        "operation": "set",
        "command": ":TRIGger:EDGE:LEVel -0.25,CHANnel1",
        "source_channel": 1,
        "level_volts": -0.25,
    }

    assert cli.main([
        "trigger-edge-level", "--dry-run", "--model", "keysight-dsox3024a",
        "--source-channel", "4", "--query",
    ]) == 0
    output = capsys.readouterr().out
    assert "Command: :TRIGger:EDGE:LEVel? CHANnel4" in output
    assert "Command: :SYSTem:ERRor?" not in output


def test_trigger_edge_level_simulate_configure_and_query(capsys):
    assert cli.main([
        "trigger-edge-level", "--simulate", "--json", "--model", "keysight-dsox4034a",
        "--source-channel", "2", "--level-volts", "0",
    ]) == 0
    payload = _payload(capsys)
    assert {key: payload["result"][key] for key in (
        "operation", "command", "source_channel", "level_volts"
    )} == {
        "operation": "set", "command": ":TRIGger:EDGE:LEVel 0,CHANnel2",
        "source_channel": 2, "level_volts": 0.0,
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:LEVel 0,CHANnel2", ":SYSTem:ERRor?"
    ]

    assert cli.main([
        "trigger-edge-level", "--simulate", "--json", "--model", "keysight-dsox4034a",
        "--source-channel", "2", "--query",
    ]) == 0
    payload = _payload(capsys)
    assert {key: payload["result"][key] for key in (
        "operation", "command", "source_channel", "level_volts", "raw_level"
    )} == {
        "operation": "query", "command": ":TRIGger:EDGE:LEVel? CHANnel2",
        "source_channel": 2, "level_volts": 0.0, "raw_level": "0",
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:LEVel? CHANnel2", ":SYSTem:ERRor?"
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        [], ["--query"], ["--source-channel", "1"], ["--level-volts", "0.5"],
        ["--source-channel", "1", "--query", "--level-volts", "0.5"],
        ["--source-channel", "5", "--level-volts", "0.5"],
        ["--source-channel", "1", "--level-volts", "nan"],
    ],
)
def test_trigger_edge_level_rejects_invalid_operation(capsys, arguments):
    assert cli.main([
        "trigger-edge-level", "--dry-run", "--json", "--model", "keysight-dsox2004a", *arguments
    ]) == 1
    assert _payload(capsys)["ok"] is False


def test_existing_atomic_trigger_commands_remain_available(capsys):
    assert cli.main([
        "trigger-edge", "--dry-run", "--json", "--model", "keysight-dsox4024a",
        "--source-channel", "1", "--level", "0.5", "--slope", "positive",
    ]) == 0
    assert _payload(capsys)["result"]["commands"][0] == ":TRIGger:MODE EDGE"
    assert cli.main([
        "trigger-edge-source", "--dry-run", "--json", "--model", "keysight-dsox4024a", "--source", "line"
    ]) == 0
    assert _payload(capsys)["result"]["command"] == ":TRIGger:EDGE:SOURce LINE"
