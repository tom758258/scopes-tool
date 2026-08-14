"""Tests for acquisition CLI command."""

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.idn import parse_idn
from scopes_tool_core.status import SystemErrorEntry


class _AcquisitionDummyScope:
    def __init__(self, model="DSOX4024A"):
        self.capabilities = None
        self.calls = []
        self.model = model
        self.backend = type("Backend", (), {"backend": "fake", "timeout": 2000})()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback

    def query_idn(self):
        self.calls.append("query_idn")
        self.capabilities = capabilities_for_model(self.model)
        return parse_idn(f"KEYSIGHT TECHNOLOGIES,{self.model},MY123,07.20")

    def set_acquisition_type(self, acq_type):
        self.calls.append(("set_acquisition_type", acq_type))

    def query_acquisition_type(self):
        self.calls.append("query_acquisition_type")
        return "normal"

    def set_acquisition_count(self, count):
        self.calls.append(("set_acquisition_count", count))

    def query_acquisition_count(self):
        self.calls.append("query_acquisition_count")
        return 16

    def query_acquisition_config(self):
        self.calls.append("query_acquisition_config")
        from scopes_tool_core.acquisition import AcquisitionConfig
        return AcquisitionConfig(type="normal", count=16)

    def query_system_error(self):
        self.calls.append("query_system_error")
        return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')


def _install_acquisition_scope(monkeypatch, model="DSOX4024A"):
    scope = _AcquisitionDummyScope(model=model)
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: scope),
    )
    return scope


def test_acquisition_cli_query_calls_idn_and_config(monkeypatch, capsys):
    scope = _install_acquisition_scope(monkeypatch)

    assert cli.main(["acquisition", "--resource", "USB0::FAKE::INSTR", "--query"]) == 0

    out = capsys.readouterr().out
    assert "query_idn" in str(scope.calls)
    assert "query_acquisition_config" in str(scope.calls)
    assert "query_system_error" in str(scope.calls)
    assert "Planned query: acquisition type and average count" in out
    assert "Acquisition type: normal" in out
    assert "Average count: 16" in out
    assert ":ACQuire:TYPE?" in out
    assert ":ACQuire:COUNt?" in out


def test_acquisition_cli_set_type_sends_type_command(monkeypatch, capsys):
    scope = _install_acquisition_scope(monkeypatch)

    assert cli.main(["acquisition", "--resource", "USB0::FAKE::INSTR", "--type", "average"]) == 0

    assert ("set_acquisition_type", "average") in scope.calls
    out = capsys.readouterr().out
    assert "Planned change: acquisition type average" in out
    assert ":ACQuire:TYPE AVERage" in out


@pytest.mark.parametrize(
    ("alias", "expected_command"),
    [
        ("norm", ":ACQuire:TYPE NORMal"),
        ("avg", ":ACQuire:TYPE AVERage"),
        ("high-resolution", ":ACQuire:TYPE HRESolution"),
        ("hres", ":ACQuire:TYPE HRESolution"),
        ("peak-detect", ":ACQuire:TYPE PEAK"),
    ],
)
def test_acquisition_cli_accepts_type_aliases(monkeypatch, capsys, alias, expected_command):
    scope = _install_acquisition_scope(monkeypatch)

    assert cli.main(["acquisition", "--resource", "USB0::FAKE::INSTR", "--type", alias]) == 0

    assert ("set_acquisition_type", alias) in scope.calls
    out = capsys.readouterr().out
    assert expected_command in out


def test_acquisition_cli_set_average_with_count_sends_type_then_count(monkeypatch, capsys):
    scope = _install_acquisition_scope(monkeypatch)

    assert cli.main([
        "acquisition", "--resource", "USB0::FAKE::INSTR",
        "--type", "average", "--count", "32"
    ]) == 0

    calls = scope.calls
    assert ("set_acquisition_type", "average") in calls
    assert ("set_acquisition_count", 32) in calls
    # Verify order: type before count
    type_idx = next(i for i, c in enumerate(calls) if c[0] == "set_acquisition_type")
    count_idx = next(i for i, c in enumerate(calls) if c[0] == "set_acquisition_count")
    assert type_idx < count_idx

    out = capsys.readouterr().out
    assert ":ACQuire:TYPE AVERage" in out
    assert ":ACQuire:COUNt 32" in out


def test_acquisition_cli_accepts_average_alias_with_count(monkeypatch, capsys):
    scope = _install_acquisition_scope(monkeypatch)

    assert cli.main([
        "acquisition", "--resource", "USB0::FAKE::INSTR",
        "--type", "avg", "--count", "32"
    ]) == 0

    assert ("set_acquisition_type", "avg") in scope.calls
    assert ("set_acquisition_count", 32) in scope.calls
    out = capsys.readouterr().out
    assert ":ACQuire:TYPE AVERage" in out
    assert ":ACQuire:COUNt 32" in out


def test_acquisition_cli_count_without_average_fails(monkeypatch, capsys):
    _install_acquisition_scope(monkeypatch)

    result = cli.main([
        "acquisition", "--resource", "USB0::FAKE::INSTR",
        "--count", "16"
    ])

    assert result == 1
    err = capsys.readouterr().err
    assert "--count can only be used with --type average" in err


def test_acquisition_cli_query_combined_with_type_fails(monkeypatch, capsys):
    _install_acquisition_scope(monkeypatch)

    result = cli.main([
        "acquisition", "--resource", "USB0::FAKE::INSTR",
        "--query", "--type", "normal"
    ])

    assert result == 1
    err = capsys.readouterr().err
    assert "--query cannot be combined with --type or --count" in err


def test_acquisition_cli_query_combined_with_count_fails(monkeypatch, capsys):
    _install_acquisition_scope(monkeypatch)

    result = cli.main([
        "acquisition", "--resource", "USB0::FAKE::INSTR",
        "--query", "--count", "16"
    ])

    assert result == 1
    err = capsys.readouterr().err
    assert "--query cannot be combined with --type or --count" in err


def test_acquisition_cli_requires_resource_or_type(monkeypatch, capsys):
    _install_acquisition_scope(monkeypatch)

    result = cli.main(["acquisition", "--resource", "USB0::FAKE::INSTR"])

    assert result == 1
    err = capsys.readouterr().err
    assert "acquisition command requires --query or --type" in err


def test_acquisition_cli_prints_session_info(monkeypatch, capsys):
    scope = _install_acquisition_scope(monkeypatch)

    assert cli.main(["acquisition", "--resource", "USB0::FAKE::INSTR", "--query"]) == 0

    out = capsys.readouterr().out
    assert "Resource: USB0::FAKE::INSTR" in out
    assert "Model: DSOX4024A" in out
    assert "Series: 4000X" in out


def test_acquisition_cli_invalid_count_fails_before_open_and_type_change(monkeypatch, capsys):
    monkeypatch.setattr(runtime, "_open_scope", lambda *args, **kwargs: pytest.fail("opened scope"))

    result = cli.main([
        "acquisition", "--resource", "USB0::FAKE::INSTR",
        "--type", "average", "--count", "1"
    ])

    assert result != 0
    err = capsys.readouterr().err
    assert "acquisition count must be between 2 and 65536" in err


def test_acquisition_cli_system_error_returns_failure(monkeypatch, capsys):
    scope = _install_acquisition_scope(monkeypatch)
    monkeypatch.setattr(
        scope,
        "query_system_error",
        lambda: SystemErrorEntry(code=-100, message="Command error", raw='-100,"Command error"'),
    )

    result = cli.main([
        "acquisition", "--resource", "USB0::FAKE::INSTR",
        "--type", "normal"
    ])

    assert result == 1
    out = capsys.readouterr().out
    assert 'System error: -100, "Command error"' in out
