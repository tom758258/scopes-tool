import json

import pytest

from scopes_tool_cli import cli, runtime


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


@pytest.mark.parametrize(
    "args, expected",
    [
        (["dvm-enable", "--query"], ":DVM:ENABle?"),
        (["dvm-enable", "--enabled", "true"], ":DVM:ENABle 1"),
        (["dvm-enable", "--enabled", "false"], ":DVM:ENABle 0"),
        (["dvm-source", "--query"], ":DVM:SOURce?"),
        (["dvm-source", "--channel", "1"], ":DVM:SOURce CHANnel1"),
        (["dvm-mode", "--query"], ":DVM:MODE?"),
        (["dvm-mode", "--mode", "dc"], ":DVM:MODE DC"),
        (["dvm-mode", "--mode", "dc-rms"], ":DVM:MODE DCRMs"),
        (["dvm-mode", "--mode", "ac-rms"], ":DVM:MODE ACRMs"),
        (["dvm-auto-range", "--query"], ":DVM:ARANge?"),
        (["dvm-auto-range", "--enabled", "true"], ":DVM:ARANge 1"),
        (["dvm-auto-range", "--enabled", "false"], ":DVM:ARANge 0"),
        (["dvm-current", "--query"], ":DVM:CURRent?"),
    ],
)
def test_dvm_command_dry_run_json(capsys, args, expected):
    assert cli.main([*args, "--dry-run", "--json", "--model", "keysight-dsox4024a"]) == 0
    payload = _payload(capsys)
    assert payload["scpi"]["planned"][0] == expected
    assert payload["scpi"]["planned"][-1] == ":SYSTem:ERRor?"


def test_dvm_query_dry_run_has_only_v1_queries(capsys):
    assert cli.main(["dvm-query", "--query", "--dry-run", "--json"]) == 0
    payload = _payload(capsys)
    assert payload["scpi"]["planned"] == [
        ":DVM:ENABle?",
        ":DVM:SOURce?",
        ":DVM:MODE?",
        ":DVM:ARANge?",
        ":DVM:CURRent?",
        ":SYSTem:ERRor?",
    ]


def test_dvm_query_simulator_json_normalizes_all_fields(capsys):
    assert cli.main(["dvm-query", "--query", "--simulate", "--json"]) == 0
    payload = _payload(capsys)
    result = payload["result"]
    assert result["enabled"] is False
    assert result["source_channel"] == 1
    assert result["mode"] == "dc"
    assert result["auto_range_enabled"] is True
    assert result["value"] == 0.0
    assert result["raw"] == {
        "enabled": "0",
        "source": "CHAN1",
        "mode": "DC",
        "auto_range": "1",
        "current": "+0.00000000E+00",
    }
    assert all("FREQ" not in item.upper() for item in payload["scpi"]["sent"])
    assert all("COUNTER" not in item.upper() for item in payload["scpi"]["sent"])


def test_dvm_text_dry_run_shows_primary_command(capsys):
    assert cli.main(["dvm-mode", "--mode", "dc-rms", "--dry-run"]) == 0
    captured = capsys.readouterr()
    assert "Command: :DVM:MODE DCRMs" in captured.out
    assert ":SYSTem:ERRor?" not in captured.out


@pytest.mark.parametrize(
    "args",
    [
        ["dvm-current"],
        ["dvm-query"],
        ["dvm-mode", "--mode", "frequency"],
        ["dvm-mode", "--mode", "DCRMS"],
        ["dvm-enable", "--enabled", "on"],
        ["dvm-frequency"],
        ["counter-query"],
    ],
)
def test_dvm_invalid_or_out_of_scope_cli_fails_argparse(capsys, args):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(args)
    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "args",
    [
        ["dvm-enable", "--query", "--enabled", "true"],
        ["dvm-source", "--query", "--channel", "1"],
        ["dvm-source", "--channel", "5"],
        ["dvm-mode", "--query", "--mode", "dc"],
        ["dvm-auto-range", "--query", "--enabled", "false"],
    ],
)
def test_dvm_validation_fails_before_open(monkeypatch, capsys, args):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    assert cli.main([*args, "--simulate", "--json", "--model", "keysight-dsox4024a"]) == 1
    payload = _payload(capsys)
    assert payload["ok"] is False
