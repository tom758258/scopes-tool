import json

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.tektronix import TektronixOscilloscope
from scopes_tool_core.trigger import TRIGGER_MODES


def _json_stdout(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


@pytest.mark.parametrize(
    "command, query_arg, expected_query",
    [
        ("trigger-mode", "--query", ":TRIGger:MODE?"),
        ("trigger-sweep", "--query", ":TRIGger:SWEep?"),
        ("trigger-noise-reject", "--query", ":TRIGger:NREJect?"),
        ("trigger-hf-reject", "--query", ":TRIGger:HFReject?"),
    ],
)
def test_trigger_common_query_dry_run_json(capsys, command, query_arg, expected_query):
    assert cli.main([command, "--dry-run", "--json", "--model", "keysight-dsox4024a", query_arg]) == 0

    payload = _json_stdout(capsys)
    assert payload["command"] == command
    assert payload["result"] == {"operation": "query", "command": expected_query}
    assert payload["scpi"]["planned"] == [expected_query, ":SYSTem:ERRor?"]


@pytest.mark.parametrize(
    "args, expected_command, expected_result",
    [
        (
            ["trigger-mode", "--mode", "runt"],
            ":TRIGger:MODE RUNT",
            {"mode": "runt"},
        ),
        (
            ["trigger-sweep", "--mode", "auto"],
            ":TRIGger:SWEep AUTO",
            {"mode": "auto"},
        ),
        (
            ["trigger-sweep", "--mode", "normal"],
            ":TRIGger:SWEep NORMal",
            {"mode": "normal"},
        ),
        (
            ["trigger-noise-reject", "--enabled", "true"],
            ":TRIGger:NREJect ON",
            {"enabled": True},
        ),
        (
            ["trigger-noise-reject", "--enabled", "false"],
            ":TRIGger:NREJect OFF",
            {"enabled": False},
        ),
        (
            ["trigger-hf-reject", "--enabled", "true"],
            ":TRIGger:HFReject ON",
            {"enabled": True},
        ),
        (
            ["trigger-hf-reject", "--enabled", "false"],
            ":TRIGger:HFReject OFF",
            {"enabled": False},
        ),
    ],
)
def test_trigger_common_configure_dry_run_json(
    capsys, args, expected_command, expected_result
):
    assert cli.main([*args, "--dry-run", "--json", "--model", "keysight-dsox4024a"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "configure"
    assert payload["result"]["command"] == expected_command
    assert payload["result"]["state_changing"] is True
    for key, value in expected_result.items():
        assert payload["result"][key] == value
    assert payload["scpi"]["planned"] == [expected_command, ":SYSTem:ERRor?"]


@pytest.mark.parametrize(
    "command, expected_result, expected_sent",
    [
        (
            "trigger-mode",
            {"mode": "edge", "raw_mode": "EDGE"},
            ["*IDN?", ":TRIGger:MODE?", ":SYSTem:ERRor?"],
        ),
        (
            "trigger-sweep",
            {"mode": "auto", "raw_value": "AUTO"},
            ["*IDN?", ":TRIGger:SWEep?", ":SYSTem:ERRor?"],
        ),
        (
            "trigger-noise-reject",
            {"enabled": False, "raw_value": "0"},
            ["*IDN?", ":TRIGger:NREJect?", ":SYSTem:ERRor?"],
        ),
        (
            "trigger-hf-reject",
            {"enabled": False, "raw_value": "0"},
            ["*IDN?", ":TRIGger:HFReject?", ":SYSTem:ERRor?"],
        ),
    ],
)
def test_trigger_common_query_simulate_json(
    capsys, command, expected_result, expected_sent
):
    assert cli.main([command, "--simulate", "--json", "--model", "keysight-dsox4024a", "--query"]) == 0

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "query"
    for key, value in expected_result.items():
        assert payload["result"][key] == value
    assert payload["scpi"]["sent"] == expected_sent


@pytest.mark.parametrize(
    "args, expected_sent",
    [
        (
            ["trigger-mode", "--mode", "runt"],
            ["*IDN?", ":TRIGger:MODE RUNT", ":SYSTem:ERRor?"],
        ),
        (
            ["trigger-sweep", "--mode", "normal"],
            ["*IDN?", ":TRIGger:SWEep NORMal", ":SYSTem:ERRor?"],
        ),
        (
            ["trigger-noise-reject", "--enabled", "true"],
            ["*IDN?", ":TRIGger:NREJect ON", ":SYSTem:ERRor?"],
        ),
        (
            ["trigger-noise-reject", "--enabled", "false"],
            ["*IDN?", ":TRIGger:NREJect OFF", ":SYSTem:ERRor?"],
        ),
        (
            ["trigger-hf-reject", "--enabled", "true"],
            ["*IDN?", ":TRIGger:HFReject ON", ":SYSTem:ERRor?"],
        ),
        (
            ["trigger-hf-reject", "--enabled", "false"],
            ["*IDN?", ":TRIGger:HFReject OFF", ":SYSTem:ERRor?"],
        ),
    ],
)
def test_trigger_common_configure_simulate_json(capsys, args, expected_sent):
    assert cli.main([*args, "--simulate", "--json", "--model", "keysight-dsox4024a"]) == 0

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "configure"
    assert payload["scpi"]["sent"] == expected_sent


@pytest.mark.parametrize(
    "args, expected_message",
    [
        (["trigger-mode", "--query", "--mode", "edge"], "cannot be combined"),
        (["trigger-mode"], "configure requires --mode"),
        (
            ["trigger-sweep", "--query", "--mode", "auto"],
            "cannot be combined",
        ),
        (
            ["trigger-noise-reject", "--query", "--enabled", "true"],
            "cannot be combined",
        ),
        (
            ["trigger-hf-reject", "--query", "--enabled", "false"],
            "cannot be combined",
        ),
        (["trigger-sweep"], "configure requires --mode"),
        (["trigger-noise-reject"], "configure requires --enabled"),
        (["trigger-hf-reject"], "configure requires --enabled"),
    ],
)
def test_trigger_common_validation_errors_are_json(capsys, args, expected_message):
    assert cli.main([*args, "--dry-run", "--json", "--model", "keysight-dsox4024a"]) == 1

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert expected_message in payload["error"]["message"]


@pytest.mark.parametrize(
    "args",
    [
        ["trigger-mode", "--mode", "pulse-width", "--dry-run", "--json"],
        ["trigger-sweep", "--mode", "single", "--dry-run", "--json"],
        ["trigger-noise-reject", "--enabled", "yes", "--dry-run", "--json"],
        ["trigger-hf-reject", "--enabled", "1", "--dry-run", "--json"],
    ],
)
def test_trigger_common_invalid_values_fail_argparse(capsys, args):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(args)

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "invalid choice" in captured.err or "must be true or false" in captured.err


@pytest.mark.parametrize(
    "model_id, command",
    [
        ("tektronix-tbs2074b", "TRIGger:A:TYPe?"),
        ("tektronix-tds2024b", "TRIGger:MAIn:TYPe?"),
        ("tektronix-tbs1052b", "TRIGger:MAIn:TYPe?"),
    ],
)
@pytest.mark.parametrize("run_mode", ["--dry-run", "--simulate"])
def test_trigger_mode_tektronix_query_uses_core(monkeypatch, capsys, model_id, command, run_mode):
    calls = []
    original = TektronixOscilloscope.query_trigger_mode

    def query(scope):
        calls.append(scope)
        return original(scope)

    monkeypatch.setattr(TektronixOscilloscope, "query_trigger_mode", query)
    assert cli.main([
        "trigger-mode", "--query", run_mode, "--model", model_id, "--json",
    ]) == 0
    payload = _json_stdout(capsys)
    assert calls
    assert payload["ok"] is True
    if run_mode == "--dry-run":
        assert payload["result"] == {"operation": "trigger-mode", "commands": [command]}
        assert payload["scpi"]["planned"] == [command, "*ESR?"]
        assert payload["scpi"]["sent"] == []
    else:
        assert payload["result"]["operation"] == "query"
        assert payload["result"]["command"] == command
        assert payload["result"]["mode"] == "edge"
        assert payload["result"]["raw_mode"] == "EDGE"
        assert payload["scpi"]["sent"] == ["*IDN?", command, "*ESR?"]


_TEK_TRIGGER_MODE_CASES = [
    ("tektronix-tbs2074b", "edge", ["TRIGger:A:TYPe EDGE"]),
    ("tektronix-tbs2074b", "glitch", ["TRIGger:A:TYPe PULSE", "TRIGger:A:PULSe:CLAss WIDth"]),
    ("tektronix-tbs2074b", "runt", ["TRIGger:A:TYPe PULSE", "TRIGger:A:PULSe:CLAss RUNT"]),
    ("tektronix-tds2024b", "edge", ["TRIGger:MAIn:TYPe EDGE"]),
    ("tektronix-tds2024b", "glitch", ["TRIGger:MAIn:TYPe PULSE"]),
    ("tektronix-tds2024b", "tv", ["TRIGger:MAIn:TYPe VIDeo"]),
    ("tektronix-tbs1052b", "edge", ["TRIGger:MAIn:TYPe EDGE"]),
    ("tektronix-tbs1052b", "glitch", ["TRIGger:MAIn:TYPe PULSE"]),
    ("tektronix-tbs1052b", "tv", ["TRIGger:MAIn:TYPe VIDeo"]),
]


@pytest.mark.parametrize("model_id, mode, commands", _TEK_TRIGGER_MODE_CASES)
@pytest.mark.parametrize("run_mode", ["--dry-run", "--simulate"])
def test_trigger_mode_tektronix_configure_uses_core(
    monkeypatch, capsys, model_id, mode, commands, run_mode
):
    calls = []
    original = TektronixOscilloscope.configure_trigger_mode

    def configure(scope, selected_mode):
        calls.append(selected_mode)
        return original(scope, selected_mode)

    monkeypatch.setattr(TektronixOscilloscope, "configure_trigger_mode", configure)
    assert cli.main([
        "trigger-mode", "--mode", mode, run_mode, "--model", model_id, "--json",
    ]) == 0
    payload = _json_stdout(capsys)
    assert calls and all(selected == mode for selected in calls)
    assert payload["ok"] is True
    if run_mode == "--dry-run":
        assert payload["result"] == {"operation": "trigger-mode", "commands": commands}
        assert payload["scpi"]["planned"] == [*commands, "*ESR?"]
        assert payload["scpi"]["sent"] == []
    else:
        assert payload["result"]["operation"] == "configure"
        assert payload["result"]["command"] == commands[0]
        assert payload["result"]["mode"] == mode
        assert payload["result"]["state_changing"] is True
        assert payload["scpi"]["sent"] == ["*IDN?", *commands, "*ESR?"]


@pytest.mark.parametrize(
    "model_id, supported",
    [
        ("tektronix-tbs2074b", ("edge", "glitch", "runt")),
        ("tektronix-tds2024b", ("edge", "glitch", "tv")),
        ("tektronix-tbs1052b", ("edge", "glitch", "tv")),
    ],
)
@pytest.mark.parametrize("run_mode", ["--dry-run", "--simulate"])
def test_trigger_mode_subset_rejected_before_open(monkeypatch, capsys, model_id, supported, run_mode):
    monkeypatch.setattr(
        runtime, "_open_scope", lambda *args, **kwargs: pytest.fail("opened scope"),
    )
    for mode in TRIGGER_MODES:
        if mode in supported:
            continue
        assert cli.main([
            "trigger-mode", "--mode", mode, run_mode, "--model", model_id, "--json",
        ]) == 1
        payload = _json_stdout(capsys)
        assert payload["ok"] is False
        assert payload["error"]["type"] == "ParameterValidationError"
        assert "unsupported" in payload["error"]["message"]
        assert payload["scpi"] == {"planned": [], "sent": []}
