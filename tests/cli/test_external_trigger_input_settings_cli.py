import json

import pytest

from scopes_tool_cli import cli, runtime


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


@pytest.mark.parametrize("command", ["external-trigger-probe", "external-trigger-units", "external-trigger-settings"])
def test_external_trigger_input_commands_publish_help(capsys, command):
    with pytest.raises(SystemExit) as exc_info:
        cli.main([command, "--help"])
    assert exc_info.value.code == 0
    assert command in capsys.readouterr().out


@pytest.mark.parametrize(
    "model",
    [
        "keysight-dsox2004a",
        "keysight-dsox3024a",
        "keysight-dsox4024a",
        "keysight-dsox4034a",
    ],
)
def test_external_trigger_probe_dry_run_and_simulate_paths(capsys, model):
    assert cli.main([
        "external-trigger-probe", "--dry-run", "--json", "--model", model, "--attenuation", "10"
    ]) == 0
    assert _payload(capsys)["result"] == {
        "operation": "set", "command": ":EXTernal:PROBe 10", "attenuation": 10.0
    }

    assert cli.main([
        "external-trigger-probe", "--simulate", "--json", "--model", model, "--query"
    ]) == 0
    payload = _payload(capsys)
    assert {key: payload["result"][key] for key in (
        "operation", "command", "attenuation", "raw_attenuation"
    )} == {
        "operation": "query", "command": ":EXTernal:PROBe?", "attenuation": 1.0, "raw_attenuation": "1"
    }
    assert payload["scpi"]["sent"] == ["*IDN?", ":EXTernal:PROBe?", ":SYSTem:ERRor?"]


@pytest.mark.parametrize(
    ("command", "args", "result", "sent"),
    [
        ("external-trigger-units", ["--units", "volts"], {"operation": "set", "command": ":EXTernal:UNITs VOLT", "units": "volts"}, ["*IDN?", ":EXTernal:UNITs VOLT", ":SYSTem:ERRor?"]),
        ("external-trigger-units", ["--query"], {"operation": "query", "command": ":EXTernal:UNITs?", "units": "volts", "raw_units": "VOLT"}, ["*IDN?", ":EXTernal:UNITs?", ":SYSTem:ERRor?"]),
        ("external-trigger-settings", ["--query"], {"operation": "query", "command": ":EXTernal?", "probe_attenuation": 1.0, "range_value": 8.0, "units": "volts", "bandwidth_limit_enabled": False, "raw_response": ":EXT:BWL 0;RANG +8.00000000E+00;UNIT VOLT;PROB +1.00000000E+00"}, ["*IDN?", ":EXTernal?", ":SYSTem:ERRor?"]),
    ],
)
def test_external_trigger_units_and_settings_simulate_paths(capsys, command, args, result, sent):
    assert cli.main([command, "--simulate", "--json", "--model", "keysight-dsox4034a", *args]) == 0
    payload = _payload(capsys)
    assert {key: payload["result"][key] for key in result} == result
    assert payload["scpi"]["sent"] == sent


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("external-trigger-probe", []),
        ("external-trigger-probe", ["--query", "--attenuation", "10"]),
        ("external-trigger-probe", ["--attenuation", "0"]),
        ("external-trigger-probe", ["--attenuation", "nan"]),
        ("external-trigger-units", []),
        ("external-trigger-units", ["--query", "--units", "volts"]),
    ],
)
def test_external_trigger_input_commands_reject_invalid_operations_before_open(capsys, monkeypatch, command, arguments):
    monkeypatch.setattr(runtime, "_open_scope", lambda *_a, **_kw: pytest.fail("opened scope"))
    assert cli.main([command, "--dry-run", "--json", *arguments]) == 1
    assert _payload(capsys)["ok"] is False


def test_external_trigger_settings_requires_query_at_argparse_level(capsys, monkeypatch):
    monkeypatch.setattr(runtime, "_open_scope", lambda *_a, **_kw: pytest.fail("opened scope"))

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["external-trigger-settings", "--dry-run", "--json"])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "usage:" in captured.err
    assert "the following arguments are required: --query" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize(
    ("command", "alias", "value"),
    [
        ("external-trigger-probe", "--probe", "10"),
        ("external-trigger-probe", "--atten", "10"),
        ("external-trigger-units", "--unit", "volts"),
        ("external-trigger-units", "--units", "amp"),
        ("external-trigger-settings", "--probe", "true"),
    ],
)
def test_external_trigger_input_commands_reject_aliases_or_noncanonical_choices(capsys, command, alias, value):
    arguments = [command, "--dry-run"]
    if command == "external-trigger-settings":
        arguments.append("--query")
    arguments.extend([alias, value])
    with pytest.raises(SystemExit):
        cli.main(arguments)
    error_output = capsys.readouterr().err
    assert "unrecognized arguments" in error_output or "invalid choice" in error_output


@pytest.mark.parametrize(
    ("command", "arguments", "expected"),
    [
        ("external-trigger-probe", ["--query"], ":EXTernal:PROBe?"),
        ("external-trigger-probe", ["--attenuation", "10"], ":EXTernal:PROBe 10"),
        ("external-trigger-units", ["--units", "amps"], ":EXTernal:UNITs AMPere"),
        ("external-trigger-settings", ["--query"], ":EXTernal?"),
    ],
)
def test_external_trigger_input_dry_run_text_shows_specific_command(capsys, command, arguments, expected):
    assert cli.main([command, "--dry-run", "--model", "keysight-dsox4034a", *arguments]) == 0
    output = capsys.readouterr().out
    assert f"Command: {expected}" in output
    assert "Command: :SYSTem:ERRor?" not in output
