"""Tests for acquisition-points and record-length CLI commands."""

import json

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.acquisition import (
    acquisition_points_query,
    parse_acquisition_points,
    parse_record_length,
    record_length_query,
)
from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.idn import parse_idn
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.status import SystemErrorEntry


class _QueryBackend:
    backend = "fake"
    timeout = 2000


class _QueryDummyScope:
    backend = _QueryBackend()

    def __init__(self):
        self.capabilities = None
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback

    def query_idn(self):
        self.calls.append("query_idn")
        self.capabilities = capabilities_for_model("DSOX4024A")
        return parse_idn("KEYSIGHT TECHNOLOGIES,DSOX4024A,MY123,07.20")

    def query_system_error(self):
        self.calls.append("query_system_error")
        return SystemErrorEntry(
            code=0,
            message="No error",
            raw=chr(43) + chr(48) + chr(44) + chr(34) + "No error" + chr(34),
        )

    @property
    def scpi(self):
        return self

    def query(self, command):
        self.calls.append(("query", command))
        if command == acquisition_points_query():
            return "1000000"
        if command == record_length_query():
            return "65536"
        raise AssertionError("unexpected SCPI command: " + command)


def _install_query_scope(monkeypatch):
    scope = _QueryDummyScope()
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: scope),
    )
    return scope


@pytest.mark.parametrize("command", ("acquisition-points", "record-length"))
def test_query_commands_require_query_flag(command, capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main([command, "--resource", "USB0::FAKE::INSTR"])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "the following arguments are required: --query" in captured.err


def test_memory_depth_cli_is_not_accepted(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["memory-depth", "--query", "--simulate", "--json"])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "invalid choice: 'memory-depth'" in captured.err


@pytest.mark.parametrize(
    ("command", "scpi_command"),
    (
        ("acquisition-points", acquisition_points_query()),
        ("record-length", record_length_query()),
    ),
)
def test_query_command_dry_run_includes_planned_scpi_without_visa(
    command, scpi_command, monkeypatch, capsys
):
    _install_query_scope(monkeypatch)

    def fail_open(resource, visa_library=None):
        raise AssertionError("dry-run must not open VISA")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main([command, "--query", "--dry-run", "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["command"] == command
    assert payload["mode"] == "dry_run"
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["scpi_command"] == scpi_command
    assert payload["result"]["planned_scpi"] == [
        "*IDN?",
        scpi_command,
        ":SYSTem:ERRor?",
    ]
    assert payload["scpi"]["planned"] == payload["result"]["planned_scpi"]
    assert payload["result"]["unit"] == "points"
    assert "acquisition_points" not in payload["result"]
    assert "record_length_points" not in payload["result"]
    assert "memory_depth_points" not in payload["result"]
    assert payload["scpi"]["sent"] == []
    assert payload["files"] == []


def test_acquisition_points_cli_simulate_returns_points(capsys):
    assert cli.main(["acquisition-points", "--query", "--simulate", "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["mode"] == "simulate"
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["unit"] == "points"
    assert payload["result"]["scpi_command"] == acquisition_points_query()
    assert payload["result"]["acquisition_points"] == 1000000
    assert "memory_depth_points" not in payload["result"]
    assert isinstance(payload["result"]["acquisition_points"], int)
    assert payload["result"]["raw_value"] == "1000000"


def test_record_length_cli_simulate_returns_points(capsys):
    assert cli.main(["record-length", "--query", "--simulate", "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["mode"] == "simulate"
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["unit"] == "points"
    assert payload["result"]["scpi_command"] == record_length_query()
    assert payload["result"]["record_length_points"] == 65536
    assert "memory_depth_points" not in payload["result"]
    assert isinstance(payload["result"]["record_length_points"], int)
    assert payload["result"]["raw_value"] == "65536"


@pytest.mark.parametrize(
    ("command", "scpi_command"),
    (
        ("acquisition-points", acquisition_points_query()),
        ("record-length", record_length_query()),
    ),
)
def test_query_command_simulate_scpi_order(command, scpi_command, capsys):
    assert cli.main([command, "--query", "--simulate", "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        scpi_command,
        ":SYSTem:ERRor?",
    ]


def test_acquisition_points_command_order_with_fake_backend():
    backend = FakeBackend(responses={":ACQuire:POINts?": "1000000"})
    client = SCPIClient(backend)

    raw = client.query(acquisition_points_query())
    value = parse_acquisition_points(raw)

    assert value == 1000000
    assert backend.history == [acquisition_points_query()]



@pytest.mark.parametrize("model", ("keysight-dsox2004a", "keysight-dsox3024a"))
def test_record_length_unsupported_on_non_4000x_series(model, capsys):
    exit_code = cli.main(
        ["record-length", "--query", "--simulate", "--json", "--model", model]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["scpi"]["sent"] == ["*IDN?"]


def test_record_length_command_order_with_fake_backend():
    backend = FakeBackend(responses={":ACQuire:RLENgth?": "65536"})
    client = SCPIClient(backend)

    raw = client.query(record_length_query())
    value = parse_record_length(raw)

    assert value == 65536
    assert backend.history == [record_length_query()]


@pytest.mark.parametrize(
    "command",
    ("acquisition-points", "record-length"),
)
def test_query_command_scpi_log_does_not_break_json_stdout(command, capsys):
    assert cli.main([command, "--query", "--simulate", "--json", "--log-scpi"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["result"]["human_output"]
