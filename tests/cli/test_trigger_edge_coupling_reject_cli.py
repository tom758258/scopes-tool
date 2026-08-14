import json
import pytest
from scopes_tool_cli import cli, runtime

def _json_stdout(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)

def test_trigger_edge_coupling_dry_run_json(capsys):
    # Coupling configure dry-run
    assert cli.main([
        "trigger-edge-coupling",
        "--dry-run",
        "--json",
        "--model", "keysight-dsox4024a",
        "--coupling", "ac"
    ]) == 0
    payload = _json_stdout(capsys)
    assert payload["command"] == "trigger-edge-coupling"
    assert payload["result"] == {
        "operation": "set",
        "command": ":TRIGger:EDGE:COUPling AC",
        "coupling": "ac"
    }
    assert payload["scpi"]["planned"] == [
        ":TRIGger:EDGE:COUPling AC",
        ":SYSTem:ERRor?"
    ]

    # Coupling query dry-run
    assert cli.main([
        "trigger-edge-coupling",
        "--dry-run",
        "--json",
        "--model", "keysight-dsox4024a",
        "--query"
    ]) == 0
    payload = _json_stdout(capsys)
    assert payload["command"] == "trigger-edge-coupling"
    assert payload["result"] == {
        "operation": "query",
        "command": ":TRIGger:EDGE:COUPling?"
    }
    assert payload["scpi"]["planned"] == [
        ":TRIGger:EDGE:COUPling?",
        ":SYSTem:ERRor?"
    ]

def test_trigger_edge_coupling_dry_run_text_uses_result_command(capsys, monkeypatch):
    monkeypatch.setattr(
        runtime,
        "_open_scope",
        lambda *_args, **_kwargs: pytest.fail("dry-run must not open a scope"),
    )

    assert cli.main([
        "trigger-edge-coupling",
        "--dry-run",
        "--model", "keysight-dsox4024a",
        "--coupling", "ac",
    ]) == 0

    output = capsys.readouterr().out
    assert "Command: :TRIGger:EDGE:COUPling AC" in output
    assert "Command: :SYSTem:ERRor?" not in output


def test_trigger_edge_coupling_simulate_json(capsys):
    # Coupling configure simulate
    assert cli.main([
        "trigger-edge-coupling",
        "--simulate",
        "--json",
        "--coupling", "lf-reject"
    ]) == 0
    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["coupling"] == "lf-reject"

    # Coupling query simulate
    assert cli.main([
        "trigger-edge-coupling",
        "--simulate",
        "--json",
        "--query"
    ]) == 0
    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["coupling"] == "dc"
    assert payload["result"]["raw_value"] == "DC"

def test_trigger_edge_reject_dry_run_json(capsys):
    # Reject configure dry-run
    assert cli.main([
        "trigger-edge-reject",
        "--dry-run",
        "--json",
        "--model", "keysight-dsox4024a",
        "--reject", "hf-reject"
    ]) == 0
    payload = _json_stdout(capsys)
    assert payload["command"] == "trigger-edge-reject"
    assert payload["result"] == {
        "operation": "set",
        "command": ":TRIGger:EDGE:REJect HFReject",
        "reject": "hf-reject"
    }
    assert payload["scpi"]["planned"] == [
        ":TRIGger:EDGE:REJect HFReject",
        ":SYSTem:ERRor?"
    ]

    # Reject query dry-run
    assert cli.main([
        "trigger-edge-reject",
        "--dry-run",
        "--json",
        "--model", "keysight-dsox4024a",
        "--query"
    ]) == 0
    payload = _json_stdout(capsys)
    assert payload["command"] == "trigger-edge-reject"
    assert payload["result"] == {
        "operation": "query",
        "command": ":TRIGger:EDGE:REJect?"
    }
    assert payload["scpi"]["planned"] == [
        ":TRIGger:EDGE:REJect?",
        ":SYSTem:ERRor?"
    ]

def test_trigger_edge_reject_query_dry_run_text_uses_result_command(capsys, monkeypatch):
    monkeypatch.setattr(
        runtime,
        "_open_scope",
        lambda *_args, **_kwargs: pytest.fail("dry-run must not open a scope"),
    )

    assert cli.main([
        "trigger-edge-reject",
        "--dry-run",
        "--model", "keysight-dsox4024a",
        "--query",
    ]) == 0

    output = capsys.readouterr().out
    assert "Command: :TRIGger:EDGE:REJect?" in output
    assert "Command: :SYSTem:ERRor?" not in output


def test_trigger_edge_reject_simulate_json(capsys):
    # Reject configure simulate
    assert cli.main([
        "trigger-edge-reject",
        "--simulate",
        "--json",
        "--reject", "lf-reject"
    ]) == 0
    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["reject"] == "lf-reject"

    # Reject query simulate
    assert cli.main([
        "trigger-edge-reject",
        "--simulate",
        "--json",
        "--query"
    ]) == 0
    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["reject"] == "off"
    assert payload["result"]["raw_value"] == "OFF"

def test_trigger_edge_coupling_rejects_combinations(capsys):
    assert cli.main([
        "trigger-edge-coupling",
        "--dry-run",
        "--json",
        "--query",
        "--coupling", "ac"
    ]) == 1
    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "cannot be combined" in payload["error"]["message"]

def test_trigger_edge_coupling_rejects_missing_args(capsys):
    assert cli.main([
        "trigger-edge-coupling",
        "--dry-run",
        "--json"
    ]) == 1
    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "configure requires --coupling" in payload["error"]["message"]

def test_trigger_edge_reject_rejects_combinations(capsys):
    assert cli.main([
        "trigger-edge-reject",
        "--dry-run",
        "--json",
        "--query",
        "--reject", "off"
    ]) == 1
    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "cannot be combined" in payload["error"]["message"]

def test_trigger_edge_reject_rejects_missing_args(capsys):
    assert cli.main([
        "trigger-edge-reject",
        "--dry-run",
        "--json"
    ]) == 1
    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "configure requires --reject" in payload["error"]["message"]

def test_non_canonical_aliases_are_not_accepted(capsys):
    # unknown/alias command
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["edge-trigger-coupling", "--dry-run", "--json", "--query"])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err

    # unknown/alias argument choice
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["trigger-edge-coupling", "--dry-run", "--json", "--coupling", "lfr"])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err
