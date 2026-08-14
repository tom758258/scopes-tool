import json

import pytest

from scopes_tool_cli import cli, runtime


def _json_stdout(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            ["--source-channel", "1"],
            {
                "operation": "set",
                "command": ":TRIGger:EDGE:SOURce CHANnel1",
                "source": "analog-channel",
                "source_channel": 1,
            },
        ),
        (
            ["--source", "external"],
            {
                "operation": "set",
                "command": ":TRIGger:EDGE:SOURce EXTernal",
                "source": "external",
                "source_channel": None,
            },
        ),
        (
            ["--source", "line"],
            {
                "operation": "set",
                "command": ":TRIGger:EDGE:SOURce LINE",
                "source": "line",
                "source_channel": None,
            },
        ),
        (
            ["--query"],
            {"operation": "query", "command": ":TRIGger:EDGE:SOURce?"},
        ),
    ],
)
def test_trigger_edge_source_dry_run_json(capsys, arguments, expected):
    assert cli.main([
        "trigger-edge-source", "--dry-run", "--json", "--model", "keysight-dsox4024a", *arguments
    ]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"] == expected
    assert payload["scpi"]["planned"] == [expected["command"], ":SYSTem:ERRor?"]


def test_trigger_edge_source_dry_run_text_does_not_open_scope(capsys, monkeypatch):
    monkeypatch.setattr(
        runtime,
        "_open_scope",
        lambda *_args, **_kwargs: pytest.fail("dry-run must not open a scope"),
    )

    assert cli.main([
        "trigger-edge-source", "--dry-run", "--model", "keysight-dsox4024a", "--source", "external"
    ]) == 0

    output = capsys.readouterr().out
    assert "Command: :TRIGger:EDGE:SOURce EXTernal" in output
    assert "Command: :SYSTem:ERRor?" not in output


@pytest.mark.parametrize(
    ("arguments", "expected_command", "expected_source", "expected_channel"),
    [
        (["--source-channel", "4"], ":TRIGger:EDGE:SOURce CHANnel4", "analog-channel", 4),
        (["--source", "external"], ":TRIGger:EDGE:SOURce EXTernal", "external", None),
        (["--source", "line"], ":TRIGger:EDGE:SOURce LINE", "line", None),
    ],
)
def test_trigger_edge_source_simulate_configure(capsys, arguments, expected_command, expected_source, expected_channel):
    assert cli.main([
        "trigger-edge-source", "--simulate", "--json", "--model", "keysight-dsox4034a", *arguments
    ]) == 0

    payload = _json_stdout(capsys)
    assert {key: payload["result"][key] for key in (
        "operation", "command", "source", "source_channel"
    )} == {
        "operation": "set",
        "command": expected_command,
        "source": expected_source,
        "source_channel": expected_channel,
    }
    assert payload["scpi"]["sent"] == ["*IDN?", expected_command, ":SYSTem:ERRor?"]
    assert ":TRIGger:MODE EDGE" not in payload["scpi"]["sent"]


def test_trigger_edge_source_simulate_query(capsys):
    assert cli.main([
        "trigger-edge-source", "--simulate", "--json", "--model", "keysight-dsox4034a", "--query"
    ]) == 0

    payload = _json_stdout(capsys)
    assert {key: payload["result"][key] for key in (
        "operation", "command", "source", "source_channel", "raw_source"
    )} == {
        "operation": "query",
        "command": ":TRIGger:EDGE:SOURce?",
        "source": "analog-channel",
        "source_channel": 1,
        "raw_source": "CHANnel1",
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:SOURce?", ":SYSTem:ERRor?"
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--query", "--source", "external"],
        ["--source", "external", "--source-channel", "1"],
        ["--source-channel", "5"],
    ],
)
def test_trigger_edge_source_rejects_invalid_operation(capsys, arguments):
    assert cli.main(["trigger-edge-source", "--dry-run", "--json", "--model", "keysight-dsox2004a", *arguments]) == 1
    payload = _json_stdout(capsys)
    assert payload["ok"] is False


@pytest.mark.parametrize("value", ["channel1", "analog", "wgen", "digital0"])
def test_trigger_edge_source_rejects_invalid_source_choice(capsys, value):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["trigger-edge-source", "--dry-run", "--json", "--source", value])
    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_existing_trigger_edge_behavior_is_unchanged(capsys):
    assert cli.main([
        "trigger-edge", "--dry-run", "--json", "--model", "keysight-dsox4024a",
        "--source-channel", "1", "--level", "0.5", "--slope", "positive",
    ]) == 0
    payload = _json_stdout(capsys)
    assert payload["result"]["commands"] == [
        ":TRIGger:MODE EDGE",
        ":TRIGger:EDGE:SOURce CHANnel1",
        ":TRIGger:EDGE:LEVel 0.5",
        ":TRIGger:EDGE:SLOPe POSitive",
    ]
