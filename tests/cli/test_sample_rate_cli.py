"""Tests for the sample-rate CLI command."""

import json

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.acquisition import (
    parse_sample_rate,
    sample_rate_maximum_query,
    sample_rate_query,
)
from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.idn import parse_idn
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.status import SystemErrorEntry


class _SampleRateBackend:
    backend = "fake"
    timeout = 2000


class _SampleRateDummyScope:
    backend = _SampleRateBackend()

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
        return SystemErrorEntry(code=0, message="No error", raw=chr(43) + chr(48) + chr(44) + chr(34) + "No error" + chr(34))

    def query(self, command):
        self.calls.append(("query", command))
        if command == sample_rate_query():
            return "5.000000E+09"
        if command == sample_rate_maximum_query():
            return "5.000000E+09"
        raise AssertionError("unexpected SCPI command: " + command)


def _install_sample_rate_scope(monkeypatch):
    scope = _SampleRateDummyScope()
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: scope),
    )
    return scope


def test_sample_rate_cli_requires_query_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["sample-rate", "--resource", "USB0::FAKE::INSTR"])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "the following arguments are required: --query" in captured.err


def test_sample_rate_cli_dry_run_includes_planned_scpi_without_visa(monkeypatch, capsys):
    _install_sample_rate_scope(monkeypatch)

    def fail_open(resource, visa_library=None):
        raise AssertionError("dry-run must not open VISA")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main([
        "sample-rate",
        "--query",
        "--dry-run",
        "--json",
    ]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["command"] == "sample-rate"
    assert payload["mode"] == "dry_run"
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["scpi_command"] == sample_rate_query()
    assert payload["result"]["planned_scpi"] == [
        "*IDN?",
        sample_rate_query(),
        ":SYSTem:ERRor?",
    ]
    assert payload["scpi"]["planned"] == payload["result"]["planned_scpi"]
    assert payload["files"] == []


def test_sample_rate_cli_maximum_dry_run_includes_planned_scpi_without_visa(monkeypatch, capsys):
    _install_sample_rate_scope(monkeypatch)

    def fail_open(resource, visa_library=None):
        raise AssertionError("dry-run must not open VISA")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main([
        "sample-rate",
        "--query",
        "--maximum",
        "--dry-run",
        "--json",
    ]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["command"] == "sample-rate"
    assert payload["mode"] == "dry_run"
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["query_kind"] == "maximum"
    assert payload["result"]["scpi_command"] == sample_rate_maximum_query()
    assert payload["result"]["planned_scpi"] == [
        "*IDN?",
        sample_rate_maximum_query(),
        ":SYSTem:ERRor?",
    ]
    assert payload["scpi"]["planned"] == payload["result"]["planned_scpi"]
    assert payload["files"] == []


def test_sample_rate_cli_simulate_returns_sample_rate_in_hz(monkeypatch, capsys):
    _install_sample_rate_scope(monkeypatch)

    assert cli.main([
        "sample-rate",
        "--query",
        "--simulate",
        "--json",
    ]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["mode"] == "simulate"
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["unit"] == "Hz"
    assert payload["result"]["scpi_command"] == sample_rate_query()
    assert payload["result"]["sample_rate_hz"] == pytest.approx(5e9)
    assert payload["result"]["raw_value"] == "5.000000E+09"
    sent = payload["scpi"]["sent"]
    assert "*IDN?" in sent
    assert sample_rate_query() in sent
    assert ":SYSTem:ERRor?" in sent


def test_sample_rate_cli_simulate_returns_maximum_sample_rate_in_hz(monkeypatch, capsys):
    _install_sample_rate_scope(monkeypatch)

    assert cli.main([
        "sample-rate",
        "--query",
        "--maximum",
        "--simulate",
        "--json",
    ]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["mode"] == "simulate"
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["query_kind"] == "maximum"
    assert payload["result"]["unit"] == "Hz"
    assert payload["result"]["scpi_command"] == sample_rate_maximum_query()
    assert payload["result"]["maximum_sample_rate_hz"] == pytest.approx(5e9)
    assert payload["result"]["raw_value"] == "5.000000E+09"
    sent = payload["scpi"]["sent"]
    assert "*IDN?" in sent
    assert sample_rate_maximum_query() in sent
    assert ":SYSTem:ERRor?" in sent


def test_sample_rate_cli_command_order_with_fake_backend():
    backend = FakeBackend(responses={sample_rate_query(): "5.000000E+09"})
    client = SCPIClient(backend)

    raw = client.query(sample_rate_query())
    value = parse_sample_rate(raw)

    assert value == 5e9
    assert backend.history == [sample_rate_query()]


def test_sample_rate_cli_maximum_command_order_with_fake_backend():
    backend = FakeBackend(responses={sample_rate_maximum_query(): "5.000000E+09"})
    client = SCPIClient(backend)

    raw = client.query(sample_rate_maximum_query())
    value = parse_sample_rate(raw)

    assert value == 5e9
    assert backend.history == [sample_rate_maximum_query()]


def test_sample_rate_cli_simulate_scpi_order(monkeypatch, capsys):
    _install_sample_rate_scope(monkeypatch)

    assert cli.main([
        "sample-rate",
        "--query",
        "--simulate",
        "--json",
    ]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        sample_rate_query(),
        ":SYSTem:ERRor?",
    ]


def test_sample_rate_cli_maximum_simulate_scpi_order(monkeypatch, capsys):
    _install_sample_rate_scope(monkeypatch)

    assert cli.main([
        "sample-rate",
        "--query",
        "--maximum",
        "--simulate",
        "--json",
    ]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        sample_rate_maximum_query(),
        ":SYSTem:ERRor?",
    ]


def test_sample_rate_cli_scpi_log_does_not_break_json_stdout(monkeypatch, capsys):
    _install_sample_rate_scope(monkeypatch)

    assert cli.main([
        "sample-rate",
        "--query",
        "--simulate",
        "--json",
        "--log-scpi",
    ]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["result"]["sample_rate_hz"] == pytest.approx(5e9)

