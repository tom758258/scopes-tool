import json

import pytest

from scopes_tool_cli import cli, runtime


COMMANDS = {
    "system-clear-status": "*CLS",
    "system-opc": "*OPC?",
    "system-status-byte": "*STB?",
    "system-standard-event": "*ESR?",
    "system-operation-status": ":OPERegister:CONDition?",
    "system-options": "*OPT?",
}
QUERY_COMMANDS = tuple(command for command in COMMANDS if command != "system-clear-status")


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


@pytest.mark.parametrize("command, scpi", COMMANDS.items())
def test_system_status_dry_run_json_does_not_open_scope(
    monkeypatch, capsys, command, scpi
):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    query = ["--query"] if command in QUERY_COMMANDS else []

    assert cli.main([command, *query, "--dry-run", "--json"]) == 0

    payload = _payload(capsys)
    assert payload["scpi"] == {"planned": [scpi, ":SYSTem:ERRor?"], "sent": []}
    assert payload["files"] == []


@pytest.mark.parametrize(
    "command, expected",
    [
        ("system-clear-status", {"cleared": True}),
        ("system-opc", {"complete": True, "raw": "1"}),
        ("system-status-byte", {"value": 0, "raw": "0", "set_bits": []}),
        ("system-standard-event", {"value": 0, "raw": "0", "set_bits": []}),
        ("system-operation-status", {"value": 0, "raw": "0", "set_bits": []}),
        ("system-options", {"raw": "0", "options": ["0"]}),
    ],
)
def test_system_status_simulator_json_is_structured(capsys, command, expected):
    query = ["--query"] if command in QUERY_COMMANDS else []

    assert cli.main([command, *query, "--simulate", "--json"]) == 0

    payload = _payload(capsys)
    for key, value in expected.items():
        assert payload["result"][key] == value
    assert payload["result"]["command"] == COMMANDS[command]
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == [COMMANDS[command], ":SYSTem:ERRor?"]


@pytest.mark.parametrize("command", QUERY_COMMANDS)
def test_system_query_commands_require_query_before_open(monkeypatch, capsys, command):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    with pytest.raises(SystemExit) as excinfo:
        cli.main([command, "--simulate", "--json"])

    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""


def test_system_clear_status_does_not_accept_query(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["system-clear-status", "--query", "--simulate", "--json"])

    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("command", COMMANDS)
def test_system_status_commands_reject_extra_user_arguments(capsys, command):
    query = ["--query"] if command in QUERY_COMMANDS else []
    with pytest.raises(SystemExit) as excinfo:
        cli.main([command, *query, "--unexpected", "value", "--simulate", "--json"])

    assert excinfo.value.code == 2
    assert capsys.readouterr().out == ""
