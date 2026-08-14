import json

import pytest

from scopes_tool_cli import cli, runtime


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


@pytest.mark.parametrize(
    "model",
    [
        "keysight-dsox2004a",
        "keysight-dsox3024a",
        "keysight-dsox4024a",
        "keysight-dsox4034a",
    ],
)
def test_external_trigger_range_dry_run_json_for_all_target_models(capsys, model):
    assert cli.main([
        "external-trigger-range", "--dry-run", "--json", "--model", model,
        "--range-volts", "1.6",
    ]) == 0

    payload = _payload(capsys)
    assert payload["result"] == {
        "operation": "set", "command": ":EXTernal:RANGe 1.6", "range_volts": 1.6,
    }
    assert payload["scpi"]["planned"] == [":EXTernal:RANGe 1.6", ":SYSTem:ERRor?"]


def test_external_trigger_range_query_dry_run_text_and_simulate_query(capsys, monkeypatch):
    monkeypatch.setattr(runtime, "_open_scope", lambda *_a, **_kw: pytest.fail("opened scope"))
    assert cli.main([
        "external-trigger-range", "--dry-run", "--json", "--model", "keysight-dsox2004a", "--query",
    ]) == 0
    assert _payload(capsys)["result"] == {
        "operation": "query", "command": ":EXTernal:RANGe?"
    }

    assert cli.main([
        "external-trigger-range", "--dry-run", "--model", "keysight-dsox4034a", "--range-volts", "8",
    ]) == 0
    output = capsys.readouterr().out
    assert "Command: :EXTernal:RANGe 8" in output
    assert "Command: :SYSTem:ERRor?" not in output

    monkeypatch.undo()
    assert cli.main([
        "external-trigger-range", "--simulate", "--json", "--model", "keysight-dsox4034a", "--query",
    ]) == 0
    payload = _payload(capsys)
    assert {key: payload["result"][key] for key in (
        "operation", "command", "range_volts", "raw_range"
    )} == {
        "operation": "query", "command": ":EXTernal:RANGe?", "range_volts": 8.0, "raw_range": "8"
    }
    assert payload["scpi"]["sent"] == ["*IDN?", ":EXTernal:RANGe?", ":SYSTem:ERRor?"]


def test_external_trigger_range_simulate_configure_has_no_unrelated_scpi(capsys):
    assert cli.main([
        "external-trigger-range", "--simulate", "--json", "--model", "keysight-dsox3024a", "--range-volts", "12.5",
    ]) == 0
    payload = _payload(capsys)
    assert {key: payload["result"][key] for key in (
        "operation", "command", "range_volts"
    )} == {
        "operation": "set", "command": ":EXTernal:RANGe 12.5", "range_volts": 12.5,
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":EXTernal:RANGe 12.5", ":SYSTem:ERRor?"
    ]


@pytest.mark.parametrize(
    "arguments",
    [[], ["--query", "--range-volts", "8"], ["--range-volts", "0"], ["--range-volts", "-1"], ["--range-volts", "nan"]],
)
def test_external_trigger_range_rejects_invalid_operations_before_open(capsys, monkeypatch, arguments):
    monkeypatch.setattr(runtime, "_open_scope", lambda *_a, **_kw: pytest.fail("opened scope"))
    assert cli.main(["external-trigger-range", "--dry-run", "--json", *arguments]) == 1
    assert _payload(capsys)["ok"] is False


@pytest.mark.parametrize("alias", ["--range", "--volts", "--external-range", "--value"])
def test_external_trigger_range_rejects_aliases(capsys, alias):
    with pytest.raises(SystemExit):
        cli.main(["external-trigger-range", "--dry-run", alias, "8"])
    assert "unrecognized arguments" in capsys.readouterr().err


@pytest.mark.parametrize(
    "model",
    [
        "keysight-dsox2004a",
        "keysight-dsox3024a",
        "keysight-dsox4024a",
        "keysight-dsox4034a",
    ],
)
def test_external_edge_level_dry_run_json_for_all_target_models(capsys, model):
    assert cli.main([
        "trigger-edge-external-level", "--dry-run", "--json", "--model", model,
        "--level-volts", "-0.5",
    ]) == 0

    payload = _payload(capsys)
    assert payload["result"] == {
        "operation": "set",
        "command": ":TRIGger:EDGE:LEVel -0.5,EXTernal",
        "level_volts": -0.5,
    }
    assert payload["scpi"]["planned"] == [
        ":TRIGger:EDGE:LEVel -0.5,EXTernal", ":SYSTem:ERRor?"
    ]


def test_external_edge_level_dry_run_text_and_simulate_paths(capsys, monkeypatch):
    monkeypatch.setattr(runtime, "_open_scope", lambda *_a, **_kw: pytest.fail("opened scope"))
    assert cli.main([
        "trigger-edge-external-level", "--dry-run", "--model", "keysight-dsox4034a", "--level-volts", "0.5",
    ]) == 0
    output = capsys.readouterr().out
    assert "Command: :TRIGger:EDGE:LEVel 0.5,EXTernal" in output
    assert "Command: :SYSTem:ERRor?" not in output

    monkeypatch.undo()
    assert cli.main([
        "trigger-edge-external-level", "--simulate", "--json", "--model", "keysight-dsox4034a", "--level-volts", "-0.5",
    ]) == 0
    payload = _payload(capsys)
    assert {key: payload["result"][key] for key in (
        "operation", "command", "level_volts"
    )} == {
        "operation": "set",
        "command": ":TRIGger:EDGE:LEVel -0.5,EXTernal",
        "level_volts": -0.5,
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:LEVel -0.5,EXTernal", ":SYSTem:ERRor?"
    ]

    assert cli.main([
        "trigger-edge-external-level", "--simulate", "--json", "--model", "keysight-dsox4034a", "--query",
    ]) == 0
    payload = _payload(capsys)
    assert {key: payload["result"][key] for key in (
        "operation", "command", "level_volts", "raw_level"
    )} == {
        "operation": "query",
        "command": ":TRIGger:EDGE:LEVel? EXTernal",
        "level_volts": 0.0,
        "raw_level": "0",
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:LEVel? EXTernal", ":SYSTem:ERRor?"
    ]


@pytest.mark.parametrize(
    "arguments",
    [[], ["--query", "--level-volts", "0.5"], ["--level-volts", "nan"]],
)
def test_external_edge_level_rejects_invalid_operations_before_open(capsys, monkeypatch, arguments):
    monkeypatch.setattr(runtime, "_open_scope", lambda *_a, **_kw: pytest.fail("opened scope"))
    assert cli.main(["trigger-edge-external-level", "--dry-run", "--json", *arguments]) == 1
    assert _payload(capsys)["ok"] is False


@pytest.mark.parametrize("alias", ["--source", "--source-channel", "--channel", "--level", "--trigger-level", "--volts"])
def test_external_edge_level_rejects_aliases(capsys, alias):
    with pytest.raises(SystemExit):
        cli.main(["trigger-edge-external-level", "--dry-run", alias, "1"])
    assert "unrecognized arguments" in capsys.readouterr().err
