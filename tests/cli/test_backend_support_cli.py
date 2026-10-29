"""CLI Product and contributor connection policy acceptance tests."""

from __future__ import annotations

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scope import Oscilloscope


@pytest.mark.parametrize("selector", ("@py", "@bt", "@ivi"))
def test_product_live_rejects_backend_without_opening_visa(monkeypatch, capsys, selector):
    def unexpected_open(*_args, **_kwargs):
        pytest.fail("unopened Product backend must be rejected before VISA open")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(unexpected_open))
    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR", "--visa-library", selector]) == 1
    assert "not open" in capsys.readouterr().err or selector == "@py"


@pytest.mark.parametrize(
    ("command", "resource", "idn_model", "expected_scpi"),
    [
        ("run", "USB0::FAKE::INSTR", "KEYSIGHT TECHNOLOGIES,DSOX4024A",
         ["*IDN?", ":RUN", ":SYSTem:ERRor?"]),
        ("run", "USB0::FAKE::INSTR", "KEYSIGHT TECHNOLOGIES,DSOX4034A",
         ["*IDN?", ":RUN", ":SYSTem:ERRor?"]),
        ("run", "USB0::FAKE::INSTR", "TEKTRONIX,TBS2074",
         ["*IDN?", "ACQuire:STOPAfter RUNSTop", "ACQuire:STATE ON", "*ESR?"]),
        ("run", "TCPIP0::FAKE::INSTR", "KEYSIGHT TECHNOLOGIES,DSOX4024A",
         ["*IDN?", ":RUN", ":SYSTem:ERRor?"]),
        ("check-error", "TCPIP::FAKE::INSTR", "KEYSIGHT TECHNOLOGIES,DSOX4024A",
         ["*IDN?", ":SYSTem:ERRor?"]),
    ],
)
def test_registered_pyvisa_py_validation_uses_detected_idn(
    monkeypatch, capsys, command, resource, idn_model, expected_scpi
):
    backend = FakeBackend(responses={
        "*IDN?": f"{idn_model},SN1,1.0",
        ":SYSTem:ERRor?": '+0,"No error"',
        "*ESR?": "0",
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
    assert backend.closed is True
    capsys.readouterr()


@pytest.mark.parametrize("command, selector, resource, idn_model, error", [
    ("run", "@py", "USB0::FAKE::INSTR", "KEYSIGHT TECHNOLOGIES,DSOX2004A",
     "no registered scope"),
    ("run", "@py", "USB0::FAKE::INSTR", "KEYSIGHT TECHNOLOGIES,DSOX3024A",
     "no registered scope"),
    ("run", "@py", "USB0::FAKE::INSTR", "TEKTRONIX,TBS1052B", "no registered scope"),
    ("run", "@py", "USB0::FAKE::INSTR", "TEKTRONIX,TDS2024B", "no registered scope"),
    ("run", "system_visa", "TCPIP0::FAKE::INSTR", "KEYSIGHT TECHNOLOGIES,DSOX2004A",
     "no registered scope"),
    ("measure-results", "@py", "USB0::FAKE::INSTR", "TEKTRONIX,TBS2074", "unsupported"),
])
def test_validation_rejects_unsupported_scope_or_operation_without_business_scpi(
    monkeypatch, capsys, command, selector, resource, idn_model, error
):
    backend = FakeBackend(responses={"*IDN?": f"{idn_model},SN1,1.0"})
    monkeypatch.setattr(
        runtime.Oscilloscope, "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )
    assert cli.main([
        command, "--resource", resource, "--model", "keysight-dsox4024a",
        "--visa-library", selector, "--validation-allow-pending-live-support",
    ]) == 1
    assert error in capsys.readouterr().err
    assert backend.history == ["*IDN?"]
    assert backend.closed is True


@pytest.mark.parametrize("selector, resource", [
    ("@py", "ASRL1::INSTR"),
    ("system_visa", "ASRL1::INSTR"),
    ("@bt", "USB0::FAKE::INSTR"),
    ("@ivi", "USB0::FAKE::INSTR"),
    ("custom", "USB0::FAKE::INSTR"),
])
def test_validation_unregistered_backend_or_transport_rejects_before_open(
    monkeypatch, capsys, selector, resource
):
    def unexpected_open(*_args, **_kwargs):
        pytest.fail("unregistered validation transport must not open VISA")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(unexpected_open))
    assert cli.main([
        "run", "--resource", resource,
        "--visa-library", selector, "--validation-allow-pending-live-support",
    ]) == 1
    assert "no registered" in capsys.readouterr().err


@pytest.mark.parametrize("validation_args", ([], ["--validation-allow-pending-live-support"]))
def test_system_visa_live_remains_unchanged(monkeypatch, capsys, validation_args):
    backend = FakeBackend(responses={
        "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,SN1,1.0",
        ":SYSTem:ERRor?": '+0,"No error"',
    })
    monkeypatch.setattr(
        runtime.Oscilloscope, "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )
    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR", *validation_args]) == 0
    assert backend.history == ["*IDN?", ":RUN", ":SYSTem:ERRor?"]
    assert backend.closed is True
    capsys.readouterr()


@pytest.mark.parametrize("selector", ("@py", "@bt"))
@pytest.mark.parametrize("validation_args", ([], ["--validation-allow-pending-live-support"]))
def test_identity_diagnostic_keeps_optional_backend_selector(
    monkeypatch, capsys, selector, validation_args
):
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
        *validation_args,
    ]) == 0
    assert selectors == [selector]
    assert backend.history == ["*IDN?"]
    assert backend.closed is True
    capsys.readouterr()


def test_product_py_tcpip_cli_runs_without_contributor_override(monkeypatch, capsys):
    backend = FakeBackend(responses={
        "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,SN1,1.0",
        ":SYSTem:ERRor?": '+0,"No error"',
    })
    monkeypatch.setattr(
        runtime.Oscilloscope, "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )
    assert cli.main([
        "run", "--resource", "TCPIP0::FAKE::INSTR", "--visa-library", "@py",
    ]) == 0
    assert backend.history == ["*IDN?", ":RUN", ":SYSTem:ERRor?"]
    capsys.readouterr()


def test_product_py_tcpip_rejects_other_detected_model_before_run(monkeypatch, capsys):
    backend = FakeBackend(responses={"*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX2004A,SN1,1.0"})
    monkeypatch.setattr(
        runtime.Oscilloscope, "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )
    assert cli.main([
        "run", "--resource", "TCPIP0::FAKE::INSTR", "--visa-library", "@py",
    ]) == 1
    assert "No Product Live support" in capsys.readouterr().err
    assert backend.history == ["*IDN?"]
    assert backend.closed is True
