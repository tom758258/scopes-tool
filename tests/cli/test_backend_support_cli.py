"""CLI backend-only Product and contributor policy acceptance tests."""

from __future__ import annotations

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scope import Oscilloscope


@pytest.mark.parametrize("selector", ("@py", "@bt"))
def test_product_live_rejects_backend_without_opening_visa(monkeypatch, capsys, selector):
    def unexpected_open(*_args, **_kwargs):
        pytest.fail("unopened Product backend must be rejected before VISA open")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(unexpected_open))
    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR", "--visa-library", selector]) == 1
    assert "Pending" in capsys.readouterr().err or selector == "@bt"


@pytest.mark.parametrize(
    ("command", "resource", "expected_scpi"),
    [
        ("run", "TCPIP0::FAKE::INSTR", ["*IDN?", ":RUN", ":SYSTem:ERRor?"]),
        ("check-error", "TCPIP::FAKE::INSTR", ["*IDN?", ":SYSTem:ERRor?"]),
    ],
)
def test_registered_pyvisa_py_validation_uses_detected_idn(
    monkeypatch, capsys, command, resource, expected_scpi
):
    backend = FakeBackend(responses={
        "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,SN1,1.0",
        ":SYSTem:ERRor?": '+0,"No error"',
    })
    selectors = []

    def open_fake(resource, visa_library=None):
        selectors.append((resource, visa_library))
        return Oscilloscope(backend)

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(open_fake))
    assert cli.main([
        command, "--resource", resource,
        "--visa-library", "@py", "--validation-allow-pending-live-support",
    ]) == 0
    assert selectors == [(resource, "@py")]
    assert backend.history == expected_scpi
    capsys.readouterr()


def test_pyvisa_py_validation_rejects_unregistered_idn_without_business_scpi(monkeypatch, capsys):
    backend = FakeBackend(responses={"*IDN?": "TEKTRONIX,TBS2074,SN1,1.0"})
    monkeypatch.setattr(
        runtime.Oscilloscope, "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )
    assert cli.main([
        "run", "--resource", "USB0::FAKE::INSTR",
        "--visa-library", "@py", "--validation-allow-pending-live-support",
    ]) == 1
    assert "no registered Pending scope" in capsys.readouterr().err
    assert backend.history == ["*IDN?"]
    assert backend.closed is True


def test_pyvisa_py_unregistered_transport_rejects_before_open(monkeypatch, capsys):
    def unexpected_open(*_args, **_kwargs):
        pytest.fail("unregistered validation transport must not open VISA")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(unexpected_open))
    assert cli.main([
        "run", "--resource", "ASRL1::INSTR",
        "--visa-library", "@py", "--validation-allow-pending-live-support",
    ]) == 1
    assert "no registered transport" in capsys.readouterr().err


def test_system_visa_live_remains_unchanged(monkeypatch, capsys):
    backend = FakeBackend(responses={
        "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,SN1,1.0",
        ":SYSTem:ERRor?": '+0,"No error"',
    })
    monkeypatch.setattr(
        runtime.Oscilloscope, "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )
    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR"]) == 0
    assert backend.history == ["*IDN?", ":RUN", ":SYSTem:ERRor?"]
    capsys.readouterr()


@pytest.mark.parametrize("selector", ("@py", "@bt"))
def test_identity_diagnostic_keeps_optional_backend_selector(monkeypatch, capsys, selector):
    backend = FakeBackend(responses={
        "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,SN1,1.0",
    })
    selectors = []
    def open_fake(resource, visa_library=None):
        selectors.append(visa_library)
        return Oscilloscope(backend)

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(open_fake))
    assert cli.main([
        "identify", "--resource", "USB0::FAKE::INSTR", "--visa-library", selector,
    ]) == 0
    assert selectors == [selector]
    capsys.readouterr()
