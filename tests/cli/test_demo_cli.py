import json
import math

import pytest

from scopes_tool_cli import cli, runtime


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


@pytest.mark.parametrize(
    "args, expected",
    [
        (["demo-output", "--query"], ":DEMO:OUTPut?"),
        (["demo-output", "--enabled", "true"], ":DEMO:OUTPut ON"),
        (["demo-output", "--enabled", "false"], ":DEMO:OUTPut OFF"),
        (["demo-function", "--query"], ":DEMO:FUNCtion?"),
        (["demo-function", "--function", "runt"], ":DEMO:FUNCtion RUNT"),
        (["demo-function", "--function", "glitch"], ":DEMO:FUNCtion GLIT"),
        (["demo-phase", "--query"], ":DEMO:FUNCtion:PHASe:PHASe?"),
        (["demo-phase", "--degrees", "90"], ":DEMO:FUNCtion:PHASe:PHASe 90"),
    ],
)
def test_demo_commands_dry_run_json(capsys, args, expected):
    assert cli.main([*args, "--dry-run", "--json", "--model", "keysight-dsox4024a"]) == 0
    payload = _payload(capsys)
    assert payload["scpi"]["planned"][0] == expected
    assert payload["scpi"]["planned"][-1] == ":SYSTem:ERRor?"


def test_demo_query_dry_run_and_simulator_json(capsys):
    assert cli.main(["demo-query", "--dry-run", "--json"]) == 0
    payload = _payload(capsys)
    assert payload["scpi"]["planned"] == [
        ":DEMO:FUNCtion?",
        ":DEMO:OUTPut?",
        ":DEMO:FUNCtion:PHASe:PHASe?",
        ":SYSTem:ERRor?",
    ]

    assert cli.main(["demo-query", "--simulate", "--json"]) == 0
    result = _payload(capsys)["result"]
    assert result["operation"] == "query"
    assert result["commands"] == [
        ":DEMO:FUNCtion?",
        ":DEMO:OUTPut?",
        ":DEMO:FUNCtion:PHASe:PHASe?",
    ]
    assert result["function"] == "sine"
    assert result["function_scpi"] == "SIN"
    assert result["function_raw"] == "SIN"
    assert result["enabled"] is False
    assert result["output_raw"] == "0"
    assert result["phase_degrees"] == 0.0
    assert result["phase_raw"] == "0"


@pytest.mark.parametrize(
    "args",
    [
        ["demo-output"],
        ["demo-function"],
        ["demo-phase"],
        ["demo-output", "--query", "--enabled", "true"],
        ["demo-function", "--query", "--function", "runt"],
        ["demo-phase", "--query", "--degrees", "90"],
        ["demo-function", "--function", "RUNT"],
        ["demo-function", "--function", "usb"],
    ],
)
def test_demo_cli_rejects_missing_conflicting_or_invalid_actions(capsys, args):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(args)
    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("degrees", ["-0.1", "360.1", "nan", "inf", "-inf"])
def test_demo_phase_validation_fails_before_open(monkeypatch, capsys, degrees):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    degree_args = [f"--degrees={degrees}"] if degrees == "-inf" else ["--degrees", degrees]
    assert cli.main([
        "demo-phase", *degree_args, "--simulate", "--json", "--model", "keysight-dsox4024a"
    ]) == 1
    assert _payload(capsys)["ok"] is False


def test_demo_function_profile_gating_fails_before_open(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    assert cli.main([
        "demo-function", "--function", "i2s", "--simulate", "--json", "--model", "keysight-dsox2004a"
    ]) == 1
    assert _payload(capsys)["ok"] is False


def test_demo_dry_run_never_opens_scope(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    assert cli.main(["demo-query", "--dry-run", "--json"]) == 0
    _payload(capsys)
