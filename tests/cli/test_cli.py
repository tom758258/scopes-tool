import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from scopes_tool_cli import cli, runtime
import scopes_tool_core.output_files as core_output_files
from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import OscilloscopeError, VisaBackendError
from scopes_tool_core.idn import parse_idn
from scopes_tool_core.measurements import (
    MeasurementResult,
    parse_measurement_results_dump,
)
from scopes_tool_core.screenshot import ScreenshotCapture
from scopes_tool_core.status import SystemErrorEntry
from scopes_tool_core.visa_backend import VisaLiveVerification, VisaResourceListing
from scopes_tool_core.waveform import (
    MultiChannelWaveformCapture,
    WaveformCapture,
    WaveformPreamble,
)


def _byte_waveform_capture(
    channel, points=1000, raw_samples=(128, 129), vertical_values=(-2.56, -2.54)
):
    preamble = WaveformPreamble(
        raw="0,0,2,1,1.0E-6,0,0,2.0E-2,-2.56,128",
        format_code=0,
        type_code=0,
        points=2,
        count=1,
        x_increment=1e-6,
        x_origin=0.0,
        x_reference=0,
        y_increment=0.02,
        y_origin=-2.56,
        y_reference=128,
    )
    return WaveformCapture(
        channel=channel,
        requested_points=points,
        format_name="BYTE",
        preamble=preamble,
        raw_samples=raw_samples,
        time_s=(0.0, 1e-6),
        vertical_values=vertical_values,
        vertical_unit="V",
    )


def _word_waveform_capture(channel, points=1000):
    preamble = WaveformPreamble(
        raw="1,0,2,1,1.0E-6,0,0,1.0E-4,0,32768",
        format_code=1,
        type_code=0,
        points=2,
        count=1,
        x_increment=1e-6,
        x_origin=0.0,
        x_reference=0,
        y_increment=0.0001,
        y_origin=0.0,
        y_reference=32768,
    )
    return WaveformCapture(
        channel=channel,
        requested_points=points,
        format_name="WORD",
        preamble=preamble,
        raw_samples=(32768, 32769),
        time_s=(0.0, 1e-6),
        vertical_values=(0.0, 0.0001),
        vertical_unit="V",
        byte_order="MSBFirst",
        unsigned=True,
    )


class _ChannelParameterDummyBackend:
    backend = "backend"
    timeout = 2000


class _ChannelParameterDummyScope:
    backend = _ChannelParameterDummyBackend()

    def __init__(self, model="DSOX4024A"):
        self.model = model
        self.capabilities = None
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback

    def query_idn(self):
        self.calls.append("query_idn")
        self.capabilities = capabilities_for_model(self.model)
        return parse_idn(f"KEYSIGHT TECHNOLOGIES,{self.model},MY123,07.20")

    def set_channel_coupling(self, channel, coupling):
        self.calls.append(("set_channel_coupling", channel, coupling))

    def query_channel_coupling(self, channel):
        self.calls.append(("query_channel_coupling", channel))
        return "dc"

    def set_channel_probe_ratio(self, channel, ratio):
        self.calls.append(("set_channel_probe_ratio", channel, ratio))

    def query_channel_probe_ratio(self, channel):
        self.calls.append(("query_channel_probe_ratio", channel))
        return 10

    def set_channel_bandwidth_limit(self, channel, enabled):
        self.calls.append(("set_channel_bandwidth_limit", channel, enabled))

    def query_channel_bandwidth_limit(self, channel):
        self.calls.append(("query_channel_bandwidth_limit", channel))
        return True

    def set_channel_impedance(self, channel, impedance):
        self.calls.append(("set_channel_impedance", channel, impedance))

    def query_channel_impedance(self, channel):
        self.calls.append(("query_channel_impedance", channel))
        return "one_meg"

    def set_channel_invert(self, channel, enabled):
        self.calls.append(("set_channel_invert", channel, enabled))

    def query_channel_invert(self, channel):
        self.calls.append(("query_channel_invert", channel))
        return True

    def set_channel_range(self, channel, volts):
        self.calls.append(("set_channel_range", channel, volts))

    def query_channel_range(self, channel):
        self.calls.append(("query_channel_range", channel))
        return 4.0

    def set_channel_units(self, channel, units):
        self.calls.append(("set_channel_units", channel, units))

    def query_channel_units(self, channel):
        self.calls.append(("query_channel_units", channel))
        return "volt"

    def set_channel_vernier(self, channel, enabled):
        self.calls.append(("set_channel_vernier", channel, enabled))

    def query_channel_vernier(self, channel):
        self.calls.append(("query_channel_vernier", channel))
        return False

    def set_channel_probe_skew(self, channel, seconds):
        self.calls.append(("set_channel_probe_skew", channel, seconds))

    def query_channel_probe_skew(self, channel):
        self.calls.append(("query_channel_probe_skew", channel))
        return 1e-9

    def query_system_error(self):
        self.calls.append("query_system_error")
        return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')


def _install_channel_parameter_scope(monkeypatch, model="DSOX4024A"):
    scope = _ChannelParameterDummyScope(model=model)
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: scope),
    )
    return scope


class _MeasurementDummyBackend:
    backend = "backend"
    timeout = None


class _MeasurementDummyScope:
    backend = _MeasurementDummyBackend()

    def __init__(
        self,
        result_value,
        raw_value,
        unit,
        valid=True,
        reason=None,
        model="DSOX4024A",
    ):
        self.capabilities = None
        self.calls = []
        self.result_value = result_value
        self.raw_value = raw_value
        self.unit = unit
        self.valid = valid
        self.reason = reason
        self.model = model

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback

    def query_idn(self):
        self.calls.append("query_idn")
        self.capabilities = capabilities_for_model(self.model)
        return parse_idn(f"KEYSIGHT TECHNOLOGIES,{self.model},MY123,07.20")

    def query_measurement(self, channel, item, **kwargs):
        if kwargs:
            self.calls.append(("query_measurement", channel, item, kwargs))
        else:
            self.calls.append(("query_measurement", channel, item))
        return MeasurementResult(
            item=item,
            channel=channel,
            value=self.result_value,
            raw_value=self.raw_value,
            valid=self.valid,
            unit=self.unit,
            reason=self.reason,
        )

    def query_pair_measurement(self, source_channel, reference_channel, item):
        self.calls.append(
            ("query_pair_measurement", source_channel, reference_channel, item)
        )
        return MeasurementResult(
            item=item,
            channel=source_channel,
            value=self.result_value,
            raw_value=self.raw_value,
            valid=self.valid,
            unit=self.unit,
            reason=self.reason,
            reference_channel=reference_channel,
        )

    def query_system_error(self):
        self.calls.append("query_system_error")
        return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')


def _install_measurement_scope(
    monkeypatch, result_value, raw_value, unit, valid=True, reason=None, model="DSOX4024A"
):
    scope = _MeasurementDummyScope(
        result_value, raw_value, unit, valid=valid, reason=reason, model=model
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: scope),
    )
    return scope


def test_list_resources_cli_prints_backend_and_resources(monkeypatch, capsys):
    def fake_list_visa_resources(visa_library=None):
        assert visa_library is None
        return VisaResourceListing(
            resources=("USB0::0x2A8D::FAKE::INSTR",),
            backend="Test VISA backend",
        )

    monkeypatch.setattr(cli, "list_visa_resources", fake_list_visa_resources)

    assert cli.main(["list-resources"]) == 0

    out = capsys.readouterr().out
    assert "PyVISA backend: Test VISA backend" in out
    assert "USB0::0x2A8D::FAKE::INSTR" in out


def test_list_resources_cli_passes_visa_library_selector_unchanged(monkeypatch):
    selectors = []

    def fake_list_visa_resources(visa_library=None):
        selectors.append(visa_library)
        return VisaResourceListing(resources=(), backend="Test VISA backend")

    monkeypatch.setattr(cli, "list_visa_resources", fake_list_visa_resources)

    assert cli.main(["list-resources", "--visa-library", "@bt"]) == 0
    assert selectors == ["@bt"]


def test_list_resources_cli_is_passive_and_lists_all_resource_types(monkeypatch, capsys):
    def fake_list_visa_resources(visa_library=None):
        assert visa_library is None
        return VisaResourceListing(
            resources=(
                "ASRL1::INSTR",
                "USB0::0x2A8D::FAKE::INSTR",
                "TCPIP0::192.0.2.1::inst0::INSTR",
            ),
            backend="Test VISA backend",
        )

    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("plain list-resources must not open resources")

    def fail_verify(*args, **kwargs):
        del args, kwargs
        raise AssertionError("plain list-resources must not verify ASRL resources")

    monkeypatch.setattr(cli, "list_visa_resources", fake_list_visa_resources)
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))
    monkeypatch.setattr(cli, "verify_asrl_resource_live", fail_verify)

    assert cli.main(["list-resources"]) == 0

    out = capsys.readouterr().out
    assert "ASRL1::INSTR" in out
    assert "USB0::0x2A8D::FAKE::INSTR" in out
    assert "TCPIP0::192.0.2.1::inst0::INSTR" in out


def test_list_resources_cli_prints_empty_resources(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "list_visa_resources",
        lambda visa_library=None: VisaResourceListing(resources=(), backend="backend"),
    )

    assert cli.main(["list-resources"]) == 0

    assert "<none>" in capsys.readouterr().out


def test_list_resources_cli_reports_backend_failure_without_traceback(monkeypatch, capsys):
    def fail_list_visa_resources(visa_library=None):
        raise VisaBackendError("VISA backend is unavailable")

    monkeypatch.setattr(cli, "list_visa_resources", fail_list_visa_resources)

    assert cli.main(["list-resources"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert "error: VISA backend is unavailable" in captured.err


def test_list_resources_live_only_prints_only_idn_responsive_resources(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

        def __init__(self, resource):
            self.resource = resource

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def query_idn(self):
            return parse_idn(f"KEYSIGHT TECHNOLOGIES,{self.resource},SN1,FW1")

    def fake_list_visa_resources(visa_library=None):
        assert visa_library == "@sim"
        return VisaResourceListing(
            resources=("DSOX4024A", "STALE::RESOURCE", "DSOX4034A"),
            backend="Test VISA backend",
        )

    def fake_open(resource, visa_library=None):
        assert visa_library == "@sim"
        if resource == "STALE::RESOURCE":
            raise OscilloscopeError("not reachable")
        return DummyScope(resource)

    monkeypatch.setattr(cli, "list_visa_resources", fake_list_visa_resources)
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fake_open))

    assert cli.main(["list-resources", "--live-only", "--visa-library", "@sim"]) == 0

    out = capsys.readouterr().out
    assert "PyVISA backend: Test VISA backend" in out
    assert "Live resources:" in out
    assert "DSOX4024A" in out
    assert "DSOX4034A" in out
    assert "STALE::RESOURCE" not in out


def test_list_resources_live_only_prints_none_when_no_resources_respond(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "list_visa_resources",
        lambda visa_library=None: VisaResourceListing(
            resources=("STALE::RESOURCE",),
            backend="backend",
        ),
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(
            lambda resource, visa_library=None: (_ for _ in ()).throw(
                OscilloscopeError("not reachable")
            )
        ),
    )

    assert cli.main(["list-resources", "--live-only"]) == 0

    out = capsys.readouterr().out
    assert "Live resources:" in out
    assert "<none>" in out
    assert "STALE::RESOURCE" not in out


def test_list_resources_live_only_continues_after_stale_asrl(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def query_idn(self):
            return parse_idn("KEYSIGHT TECHNOLOGIES,DSOX4024A,SN1,FW1")

    def fake_list_visa_resources(visa_library=None):
        assert visa_library is None
        return VisaResourceListing(
            resources=("ASRL1::INSTR", "USB0::LIVE::INSTR"),
            backend="Test VISA backend",
        )

    def fake_verify(resource, **kwargs):
        assert resource == "ASRL1::INSTR"
        assert kwargs == {
            "visa_library": None,
            "serial_read_termination": None,
            "serial_write_termination": None,
        }
        return VisaLiveVerification(resource, False, None, "timed out")

    opened = []

    def fake_open(resource, visa_library=None):
        opened.append((resource, visa_library))
        return DummyScope()

    monkeypatch.setattr(cli, "list_visa_resources", fake_list_visa_resources)
    monkeypatch.setattr(cli, "verify_asrl_resource_live", fake_verify)
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fake_open))

    assert cli.main(["list-resources", "--live-only"]) == 0

    out = capsys.readouterr().out
    assert "USB0::LIVE::INSTR" in out
    assert "ASRL1::INSTR" not in out
    assert opened == [("USB0::LIVE::INSTR", None)]


def test_list_resources_live_only_json_reports_asrl_verification_failures(
    monkeypatch, capsys
):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def query_idn(self):
            return parse_idn("KEYSIGHT TECHNOLOGIES,DSOX4034A,SN2,FW2")

    monkeypatch.setattr(
        cli,
        "list_visa_resources",
        lambda visa_library=None: VisaResourceListing(
            resources=("ASRL1::INSTR", "TCPIP0::LIVE::INSTR"),
            backend="backend",
        ),
    )
    monkeypatch.setattr(
        cli,
        "verify_asrl_resource_live",
        lambda resource, **kwargs: VisaLiveVerification(
            resource, False, None, "timed out"
        ),
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: DummyScope()),
    )

    assert cli.main(["list-resources", "--live-only", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    result = payload["result"]
    assert result["live_resources"] == [
        {
            "resource": "TCPIP0::LIVE::INSTR",
            "idn": {
                "raw": "KEYSIGHT TECHNOLOGIES,DSOX4034A,SN2,FW2",
                "vendor": "KEYSIGHT TECHNOLOGIES",
                "model": "DSOX4034A",
                "serial": "SN2",
                "firmware": "FW2",
                "series": "4000X",
            },
        }
    ]
    assert result["verification_failures"] == [
        {
            "resource": "ASRL1::INSTR",
            "live": False,
            "raw_idn": None,
            "detail": "timed out",
        }
    ]


def test_list_resources_serial_termination_options_are_asrl_only(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def query_idn(self):
            return parse_idn("KEYSIGHT TECHNOLOGIES,DSOX4024A,SN1,FW1")

    verify_calls = []

    def fake_verify(resource, **kwargs):
        verify_calls.append((resource, kwargs))
        return VisaLiveVerification(
            resource,
            True,
            "KEYSIGHT TECHNOLOGIES,DSOX2002A,SN0,FW0",
            None,
        )

    open_calls = []

    def fake_open(resource, visa_library=None):
        open_calls.append((resource, visa_library))
        return DummyScope()

    monkeypatch.setattr(
        cli,
        "list_visa_resources",
        lambda visa_library=None: VisaResourceListing(
            resources=("ASRL1::INSTR", "USB0::LIVE::INSTR"),
            backend="backend",
        ),
    )
    monkeypatch.setattr(cli, "verify_asrl_resource_live", fake_verify)
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fake_open))

    assert (
        cli.main(
            [
                "list-resources",
                "--live-only",
                "--serial-read-termination",
                "CRLF",
                "--serial-write-termination",
                "NONE",
            ]
        )
        == 0
    )

    assert verify_calls == [
        (
            "ASRL1::INSTR",
            {
                "visa_library": None,
                "serial_read_termination": "CRLF",
                "serial_write_termination": "NONE",
            },
        )
    ]
    assert open_calls == [("USB0::LIVE::INSTR", None)]
    out = capsys.readouterr().out
    assert "ASRL1::INSTR" in out
    assert "USB0::LIVE::INSTR" in out


def test_serial_termination_options_are_rejected_by_other_commands(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["identify", "--serial-read-termination", "CRLF"])

    assert excinfo.value.code == 2
    assert (
        "unrecognized arguments: --serial-read-termination CRLF"
        in capsys.readouterr().err
    )


def test_verify_cli_queries_scope(monkeypatch, capsys):
    class DummyBackend:
        backend = "Test VISA backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()
        capabilities = capabilities_for_model("DSOX4024A")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def query_idn(self):
            return parse_idn("KEYSIGHT TECHNOLOGIES,DSOX4024A,MY12345678,02.50")

    def fake_open(resource, visa_library=None):
        assert resource == "USB0::FAKE::INSTR"
        assert visa_library is None
        return DummyScope()

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fake_open))

    assert cli.main(["identify", "--resource", "USB0::FAKE::INSTR"]) == 0

    out = capsys.readouterr().out
    assert "Model: DSOX4024A" in out
    assert "Series: 4000X" in out
    assert "Analog channels: 4" in out


def test_verify_cli_uses_environment_resource(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()
        capabilities = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def query_idn(self):
            return parse_idn("ACME,MODEL1,SN1,FW1")

    monkeypatch.setenv("SCOPES_TOOL_RESOURCE", "USB0::ENV::INSTR")
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: DummyScope()))

    assert cli.main(["identify"]) == 0

    out = capsys.readouterr().out
    assert "Resource: USB0::ENV::INSTR" in out
    assert "Series: unknown" in out


def test_verify_cli_requires_resource(monkeypatch, capsys):
    monkeypatch.delenv("SCOPES_TOOL_RESOURCE", raising=False)

    assert cli.main(["identify"]) == 2

    err = capsys.readouterr().err
    assert "--resource is required" in err


def test_verify_cli_reports_backend_open_failure_without_traceback(monkeypatch, capsys):
    def fail_open(resource, visa_library=None):
        raise VisaBackendError(f"Failed to open VISA resource {resource}: device busy")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main(["identify", "--resource", "USB0::FAKE::INSTR"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert "error: Failed to open VISA resource USB0::FAKE::INSTR: device busy" in captured.err


def test_old_list_command_is_not_registered():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["list"])

    assert excinfo.value.code == 2


def test_old_idn_command_is_not_registered():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["idn"])

    assert excinfo.value.code == 2


def test_state_command_is_not_registered():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["state"])

    assert excinfo.value.code == 2


def test_check_error_cli_reads_one_entry(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def query_system_error(self):
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: DummyScope()))

    assert cli.main(["check-error", "--resource", "USB0::FAKE::INSTR"]) == 0

    assert 'System error: +0, "No error"' in capsys.readouterr().out


def test_check_error_cli_drain_returns_failure_when_errors_found(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def drain_system_errors(self, max_reads=30):
            assert max_reads == 5
            return (
                SystemErrorEntry(code=-113, message="Undefined header", raw='-113,"Undefined header"'),
                SystemErrorEntry(code=0, message="No error", raw='+0,"No error"'),
            )

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: DummyScope()))

    assert cli.main(["check-error", "--resource", "USB0::FAKE::INSTR", "--all", "--max-reads", "5"]) == 1

    out = capsys.readouterr().out
    assert 'System error 1: -113, "Undefined header"' in out
    assert 'System error 2: +0, "No error"' in out


def test_control_cli_sends_command_then_error_post_check(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def stop(self):
            self.calls.append("stop")

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scopes = []

    def fake_open(resource, visa_library=None):
        assert resource == "USB0::FAKE::INSTR"
        assert visa_library is None
        scope = DummyScope()
        scopes.append(scope)
        return scope

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fake_open))

    assert cli.main(["stop-acquisition", "--resource", "USB0::FAKE::INSTR"]) == 0

    assert scopes[0].calls == ["stop", "query_system_error"]
    out = capsys.readouterr().out
    assert "Command: :STOP" in out
    assert 'System error: +0, "No error"' in out


def test_control_cli_returns_failure_when_post_check_reports_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def run(self):
            pass

        def query_system_error(self):
            return SystemErrorEntry(code=-113, message="Undefined header", raw='-113,"Undefined header"')

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: DummyScope()))

    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR"]) == 1

    assert 'System error: -113, "Undefined header"' in capsys.readouterr().out


def test_channel_display_cli_turns_channel_on_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def set_channel_display(self, channel, enabled):
            self.calls.append(("set_channel_display", channel, enabled))

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scopes = []

    def fake_open(resource, visa_library=None):
        assert resource == "USB0::FAKE::INSTR"
        assert visa_library is None
        scope = DummyScope()
        scopes.append(scope)
        return scope

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fake_open))

    assert (
        cli.main(
            [
                "channel-display",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--on",
            ]
        )
        == 0
    )

    assert scopes[0].calls == [
        "query_idn",
        ("set_channel_display", 1, True),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert "Resource: USB0::FAKE::INSTR" in out
    assert "Timeout ms: 2000" in out
    assert "Planned change: CH1 display ON" in out
    assert "Command: :CHANnel1:DISPlay ON" in out
    assert 'System error: +0, "No error"' in out


def test_channel_display_cli_queries_display_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def query_channel_display(self, channel):
            self.calls.append(("query_channel_display", channel))
            return False

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "channel-display",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "2",
                "--query",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("query_channel_display", 2), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned query: CH2 display state" in out
    assert "Command: :CHANnel2:DISPlay?" in out
    assert "Display: OFF" in out


def test_channel_display_cli_rejects_channel_above_detected_capabilities(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def set_channel_display(self, channel, enabled):
            self.calls.append(("set_channel_display", channel, enabled))

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "channel-display",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "5",
                "--on",
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn"]
    err = capsys.readouterr().err
    assert "channel 5 is not available" in err


def test_channel_scale_cli_sets_scale_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def set_channel_scale(self, channel, volts_per_division):
            self.calls.append(("set_channel_scale", channel, volts_per_division))

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "channel-scale",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--volts-per-division",
                "0.5",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("set_channel_scale", 1, 0.5), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned change: CH1 scale 0.5 V/div" in out
    assert "Command: :CHANnel1:SCALe 0.5" in out
    assert 'System error: +0, "No error"' in out


def test_channel_scale_cli_queries_scale_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def query_channel_scale(self, channel):
            self.calls.append(("query_channel_scale", channel))
            return 0.5

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "channel-scale",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "2",
                "--query",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("query_channel_scale", 2), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned query: CH2 scale" in out
    assert "Command: :CHANnel2:SCALe?" in out
    assert "Scale V/div: 0.5" in out


def test_channel_offset_cli_sets_offset_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def set_channel_offset(self, channel, volts):
            self.calls.append(("set_channel_offset", channel, volts))

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "channel-offset",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--volts",
                "-0.125",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("set_channel_offset", 1, -0.125), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned change: CH1 offset -0.125 V" in out
    assert "Command: :CHANnel1:OFFSet -0.125" in out
    assert 'System error: +0, "No error"' in out


def test_channel_offset_cli_queries_offset_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def query_channel_offset(self, channel):
            self.calls.append(("query_channel_offset", channel))
            return -0.125

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "channel-offset",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "2",
                "--query",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("query_channel_offset", 2), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned query: CH2 offset" in out
    assert "Command: :CHANnel2:OFFSet?" in out
    assert "Offset V: -0.125" in out


def test_channel_scale_cli_rejects_channel_above_detected_capabilities(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def set_channel_scale(self, channel, volts_per_division):
            self.calls.append(("set_channel_scale", channel, volts_per_division))

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "channel-scale",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "5",
                "--volts-per-division",
                "0.5",
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn"]
    err = capsys.readouterr().err
    assert "channel 5 is not available" in err


def test_channel_coupling_cli_sets_coupling_then_checks_error(monkeypatch, capsys):
    scope = _install_channel_parameter_scope(monkeypatch)

    assert (
        cli.main(
            [
                "channel-coupling",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--coupling",
                "ac",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("set_channel_coupling", 1, "ac"), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned change: CH1 coupling AC" in out
    assert "Command: :CHANnel1:COUPling AC" in out
    assert 'System error: +0, "No error"' in out


def test_channel_coupling_cli_queries_coupling_then_checks_error(monkeypatch, capsys):
    scope = _install_channel_parameter_scope(monkeypatch)

    assert (
        cli.main(
            [
                "channel-coupling",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "2",
                "--query",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("query_channel_coupling", 2), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned query: CH2 coupling" in out
    assert "Command: :CHANnel2:COUPling?" in out
    assert "Coupling: DC" in out


def test_channel_probe_cli_sets_ratio_then_checks_error(monkeypatch, capsys):
    scope = _install_channel_parameter_scope(monkeypatch)

    assert (
        cli.main(
            [
                "channel-probe",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--ratio",
                "10",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("set_channel_probe_ratio", 1, 10.0), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned change: CH1 probe ratio 10" in out
    assert "Command: :CHANnel1:PROBe 10" in out
    assert 'System error: +0, "No error"' in out


def test_channel_probe_cli_queries_ratio_then_checks_error(monkeypatch, capsys):
    scope = _install_channel_parameter_scope(monkeypatch)

    assert (
        cli.main(
            [
                "channel-probe",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "2",
                "--query",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("query_channel_probe_ratio", 2), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned query: CH2 probe ratio" in out
    assert "Command: :CHANnel2:PROBe?" in out
    assert "Probe ratio: 10" in out


def test_channel_bandwidth_limit_cli_turns_limit_on_then_checks_error(monkeypatch, capsys):
    scope = _install_channel_parameter_scope(monkeypatch)

    assert (
        cli.main(
            [
                "channel-bandwidth-limit",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--on",
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("set_channel_bandwidth_limit", 1, True),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert "Planned change: CH1 bandwidth limit ON" in out
    assert "Command: :CHANnel1:BWLimit ON" in out
    assert 'System error: +0, "No error"' in out


def test_channel_bandwidth_limit_cli_queries_limit_then_checks_error(monkeypatch, capsys):
    scope = _install_channel_parameter_scope(monkeypatch)

    assert (
        cli.main(
            [
                "channel-bandwidth-limit",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "2",
                "--query",
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("query_channel_bandwidth_limit", 2),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert "Planned query: CH2 bandwidth limit" in out
    assert "Command: :CHANnel2:BWLimit?" in out
    assert "Bandwidth limit: ON" in out


def test_channel_impedance_cli_sets_one_meg_then_checks_error(monkeypatch, capsys):
    scope = _install_channel_parameter_scope(monkeypatch)

    assert (
        cli.main(
            [
                "channel-impedance",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--impedance",
                "one-meg",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("set_channel_impedance", 1, "one_meg"), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned change: CH1 impedance one-meg" in out
    assert "Command: :CHANnel1:IMPedance ONEMeg" in out


def test_channel_impedance_cli_queries_impedance_then_checks_error(monkeypatch, capsys):
    scope = _install_channel_parameter_scope(monkeypatch)

    assert (
        cli.main(
            [
                "channel-impedance",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "2",
                "--query",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("query_channel_impedance", 2), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned query: CH2 impedance" in out
    assert "Command: :CHANnel2:IMPedance?" in out
    assert "Impedance: one-meg" in out


def test_channel_impedance_cli_rejects_fifty_without_allow_before_open(monkeypatch, capsys):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("validation failure must not open a scope")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert (
        cli.main(
            [
                "channel-impedance",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--impedance",
                "fifty",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "requires --allow-50-ohm" in captured.err


def test_channel_impedance_cli_rejects_2000x_fifty_after_idn_without_impedance_scpi(
    monkeypatch, capsys
):
    scope = _install_channel_parameter_scope(monkeypatch, model="DSOX2004A")

    assert (
        cli.main(
            [
                "channel-impedance",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--impedance",
                "fifty",
                "--allow-50-ohm",
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn"]
    captured = capsys.readouterr()
    assert (
        "DSO-X 2000X only supports one-meg input impedance; 50 ohm is not supported "
        "by the 2000X channel impedance spec."
    ) in captured.err


def test_channel_impedance_cli_allows_3000x_fifty_with_allow(monkeypatch, capsys):
    scope = _install_channel_parameter_scope(monkeypatch, model="DSOX3024A")

    assert (
        cli.main(
            [
                "channel-impedance",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--impedance",
                "fifty",
                "--allow-50-ohm",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("set_channel_impedance", 1, "fifty"), "query_system_error"]
    assert "Command: :CHANnel1:IMPedance FIFTy" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("command_args", "expected_call", "expected_text"),
    [
        (
            ["channel-invert", "--channel", "1", "--on"],
            ("set_channel_invert", 1, True),
            "Command: :CHANnel1:INVert ON",
        ),
        (
            ["channel-range", "--channel", "1", "--volts-full-scale", "4"],
            ("set_channel_range", 1, 4.0),
            "Command: :CHANnel1:RANGe 4",
        ),
        (
            ["channel-units", "--channel", "1", "--units", "amp"],
            ("set_channel_units", 1, "amp"),
            "Command: :CHANnel1:UNITs AMP",
        ),
        (
            ["channel-vernier", "--channel", "1", "--off"],
            ("set_channel_vernier", 1, False),
            "Command: :CHANnel1:VERNier OFF",
        ),
        (
            ["channel-probe-skew", "--channel", "1", "--seconds", "1e-9"],
            ("set_channel_probe_skew", 1, 1e-09),
            "Command: :CHANnel1:PROBe:SKEW 1e-09",
        ),
    ],
)
def test_channel_advanced_cli_sets_values_then_checks_error(
    monkeypatch, capsys, command_args, expected_call, expected_text
):
    scope = _install_channel_parameter_scope(monkeypatch)

    assert cli.main([command_args[0], "--resource", "USB0::FAKE::INSTR", *command_args[1:]]) == 0

    assert scope.calls == ["query_idn", expected_call, "query_system_error"]
    assert expected_text in capsys.readouterr().out


@pytest.mark.parametrize(
    ("command_args", "expected_call", "expected_text"),
    [
        (
            ["channel-invert", "--channel", "2", "--query"],
            ("query_channel_invert", 2),
            "Invert: ON",
        ),
        (
            ["channel-range", "--channel", "2", "--query"],
            ("query_channel_range", 2),
            "Range V: 4",
        ),
        (
            ["channel-units", "--channel", "2", "--query"],
            ("query_channel_units", 2),
            "Units: volt",
        ),
        (
            ["channel-vernier", "--channel", "2", "--query"],
            ("query_channel_vernier", 2),
            "Vernier: OFF",
        ),
        (
            ["channel-probe-skew", "--channel", "2", "--query"],
            ("query_channel_probe_skew", 2),
            "Probe skew s: 1e-09",
        ),
    ],
)
def test_channel_advanced_cli_queries_values_then_checks_error(
    monkeypatch, capsys, command_args, expected_call, expected_text
):
    scope = _install_channel_parameter_scope(monkeypatch)

    assert cli.main([command_args[0], "--resource", "USB0::FAKE::INSTR", *command_args[1:]]) == 0

    assert scope.calls == ["query_idn", expected_call, "query_system_error"]
    assert expected_text in capsys.readouterr().out


def test_channel_range_cli_rejects_volts_alias(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["channel-range", "--channel", "1", "--volts", "4"])

    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "one of the arguments --volts-full-scale --query is required" in err


def test_timebase_scale_cli_sets_scale_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def set_timebase_scale(self, seconds_per_division):
            self.calls.append(("set_timebase_scale", seconds_per_division))

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "timebase-scale",
                "--resource",
                "USB0::FAKE::INSTR",
                "--seconds-per-division",
                "0.001",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("set_timebase_scale", 0.001), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned change: timebase scale 0.001 s/div" in out
    assert "Command: :TIMebase:SCALe 0.001" in out
    assert 'System error: +0, "No error"' in out


def test_timebase_scale_cli_queries_scale_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def query_timebase_scale(self):
            self.calls.append("query_timebase_scale")
            return 0.001

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "timebase-scale",
                "--resource",
                "USB0::FAKE::INSTR",
                "--query",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", "query_timebase_scale", "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned query: timebase scale" in out
    assert "Command: :TIMebase:SCALe?" in out
    assert "Timebase scale s/div: 0.001" in out


def test_timebase_position_cli_sets_position_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def set_timebase_position(self, seconds):
            self.calls.append(("set_timebase_position", seconds))

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "timebase-position",
                "--resource",
                "USB0::FAKE::INSTR",
                "--seconds",
                "-0.0005",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("set_timebase_position", -0.0005), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned change: timebase position -0.0005 s" in out
    assert "Command: :TIMebase:POSition -0.0005" in out
    assert 'System error: +0, "No error"' in out


def test_timebase_position_cli_queries_position_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def query_timebase_position(self):
            self.calls.append("query_timebase_position")
            return -0.0005

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "timebase-position",
                "--resource",
                "USB0::FAKE::INSTR",
                "--query",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", "query_timebase_position", "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned query: timebase position" in out
    assert "Command: :TIMebase:POSition?" in out
    assert "Timebase position s: -0.0005" in out


def test_trigger_edge_cli_configures_edge_trigger_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def configure_trigger_edge(self, source_channel, level_volts, slope):
            self.calls.append(("configure_trigger_edge", source_channel, level_volts, slope))

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "trigger-edge",
                "--resource",
                "USB0::FAKE::INSTR",
                "--source-channel",
                "1",
                "--level",
                "0.25",
                "--slope",
                "positive",
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("configure_trigger_edge", 1, 0.25, "POSitive"),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert "Planned change: edge trigger CH1, level 0.25 V, slope positive" in out
    assert "Command: :TRIGger:MODE EDGE" in out
    assert "Command: :TRIGger:EDGE:SOURce CHANnel1" in out
    assert "Command: :TRIGger:EDGE:LEVel 0.25" in out
    assert "Command: :TRIGger:EDGE:SLOPe POSitive" in out
    assert 'System error: +0, "No error"' in out


def test_trigger_edge_cli_queries_edge_trigger_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyState:
        source_channel = 1
        level_volts = 0.25
        slope = "positive"

    class DummyScope:
        backend = DummyBackend()

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

        def query_trigger_edge(self):
            self.calls.append("query_trigger_edge")
            return DummyState()

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert cli.main(["trigger-edge", "--resource", "USB0::FAKE::INSTR", "--query"]) == 0

    assert scope.calls == ["query_idn", "query_trigger_edge", "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned query: edge trigger source, level, and slope" in out
    assert "Command: :TRIGger:EDGE:SOURce?" in out
    assert "Source: CH1" in out
    assert "Command: :TRIGger:EDGE:LEVel?" in out
    assert "Level V: 0.25" in out
    assert "Command: :TRIGger:EDGE:SLOPe?" in out
    assert "Slope: positive" in out


def test_trigger_edge_cli_rejects_missing_configuration_args(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert cli.main(["trigger-edge", "--resource", "USB0::FAKE::INSTR", "--source-channel", "1"]) == 1

    assert scope.calls == []
    err = capsys.readouterr().err
    assert "requires --source-channel, --level, and --slope" in err


def test_capture_cli_writes_csv_and_metadata_then_checks_error(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveform_byte(self, channel, points=1000):
            self.calls.append(("capture_waveform_byte", channel, points))
            preamble = WaveformPreamble(
                raw="0,0,2,1,1.0E-6,0,0,2.0E-2,-2.56,128",
                format_code=0,
                type_code=0,
                points=2,
                count=1,
                x_increment=1e-6,
                x_origin=0.0,
                x_reference=0,
                y_increment=0.02,
                y_origin=-2.56,
                y_reference=128,
            )
            return WaveformCapture(
                channel=channel,
                requested_points=points,
                format_name="BYTE",
                preamble=preamble,
                raw_samples=(128, 129),
                time_s=(0.0, 1e-6),
                vertical_values=(-2.56, -2.54),
                vertical_unit="V",
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--points",
                "10000",
                "--csv",
                str(csv_path),
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("capture_waveform_byte", 1, 10000), "query_system_error"]
    assert (tmp_path / "capture_meta.json").exists()
    assert csv_path.read_text(encoding="utf-8").splitlines()[0] == "time_s,ch1_v"
    out = capsys.readouterr().out
    assert "Planned capture: CH1, 10000 points, BYTE format" in out
    assert "Command: :WAVeform:SOURce CHANnel1" in out
    assert "Command: :WAVeform:FORMat BYTE" in out
    assert "Command: :WAVeform:POINts 10000" in out
    assert "Command: :WAVeform:PREamble?" in out
    assert "Command: :WAVeform:DATA?" in out
    assert "Actual points: 2" in out
    assert 'System error: +0, "No error"' in out


def test_capture_cli_supports_word_format(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveform_word(self, channel, points=1000):
            self.calls.append(("capture_waveform_word", channel, points))
            preamble = WaveformPreamble(
                raw="1,0,2,1,1.0E-6,0,0,1.0E-4,0,32768",
                format_code=1,
                type_code=0,
                points=2,
                count=1,
                x_increment=1e-6,
                x_origin=0.0,
                x_reference=0,
                y_increment=0.0001,
                y_origin=0.0,
                y_reference=32768,
            )
            return WaveformCapture(
                channel=channel,
                requested_points=points,
                format_name="WORD",
                preamble=preamble,
                raw_samples=(32768, 32769),
                time_s=(0.0, 1e-6),
                vertical_values=(0.0, 0.0001),
                vertical_unit="V",
                byte_order="MSBFirst",
                unsigned=True,
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--points",
                "5000",
                "--format",
                "word",
                "--csv",
                str(csv_path),
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("capture_waveform_word", 1, 5000), "query_system_error"]
    metadata = (tmp_path / "capture_meta.json").read_text(encoding="utf-8")
    assert '"format": "WORD"' in metadata
    assert '"byte_order": "MSBFirst"' in metadata
    assert '"unsigned": true' in metadata
    out = capsys.readouterr().out
    assert "Planned capture: CH1, 5000 points, WORD format" in out
    assert "Command: :WAVeform:SOURce CHANnel1" in out
    assert "Command: :WAVeform:FORMat WORD" in out
    assert "Command: :WAVeform:BYTeorder MSBFirst" in out
    assert "Command: :WAVeform:UNSigned ON" in out
    assert "Command: :WAVeform:POINts 5000" in out
    assert "Command: :WAVeform:PREamble?" in out
    assert "Command: :WAVeform:DATA?" in out
    assert "Actual points: 2" in out
    assert 'System error: +0, "No error"' in out


def test_capture_cli_writes_multi_channel_csv_and_metadata(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveforms_byte(self, channels, points=1000):
            self.calls.append(("capture_waveforms_byte", channels, points))
            return MultiChannelWaveformCapture(
                (
                    _byte_waveform_capture(1, points=points),
                    _byte_waveform_capture(2, points=points, vertical_values=(-2.52, -2.58)),
                )
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--channel",
                "2",
                "--csv",
                str(csv_path),
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("capture_waveforms_byte", (1, 2), 1000),
        "query_system_error",
    ]
    assert csv_path.read_text(encoding="utf-8").splitlines()[0] == "time_s,ch1_v,ch2_v"
    metadata = json.loads((tmp_path / "capture_meta.json").read_text(encoding="utf-8"))
    assert metadata["format"] == "BYTE"
    assert [item["channel"] for item in metadata["channels"]] == [1, 2]
    out = capsys.readouterr().out
    assert "Planned capture: CH1, CH2, 1000 points, BYTE format" in out
    assert out.count("Command: :WAVeform:SOURce CHANnel1") == 1
    assert out.count("Command: :WAVeform:SOURce CHANnel2") == 1
    assert "Actual points: CH1=2, CH2=2" in out
    assert 'System error: +0, "No error"' in out


def test_capture_cli_allows_opt_in_time_axis_tolerance(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveforms_byte(self, channels, points=1000):
            self.calls.append(("capture_waveforms_byte", channels, points))
            return MultiChannelWaveformCapture(
                (
                    _byte_waveform_capture(1, points=points),
                    replace(
                        _byte_waveform_capture(
                            2,
                            points=points,
                            vertical_values=(-2.52, -2.58),
                        ),
                        time_s=(0.0000004, 0.0000014),
                    ),
                )
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--channel",
                "2",
                "--csv",
                str(csv_path),
                "--allow-time-axis-tolerance",
                "--json",
            ]
        )
        == 0
    )

    assert csv_path.read_text(encoding="utf-8").splitlines() == [
        "time_s,ch1_v,ch2_v",
        "0.0,-2.56,-2.52",
        "1e-06,-2.54,-2.58",
    ]
    metadata = json.loads((tmp_path / "capture_meta.json").read_text(encoding="utf-8"))
    assert metadata["time_axis_tolerance"]["canonical_channel"] == 1
    assert metadata["time_axis_tolerance"]["max_allowed_delta_s"] == pytest.approx(
        0.5e-6
    )
    assert metadata["time_axis_tolerance"]["channels"][1]["channel"] == 2
    assert metadata["time_axis_tolerance"]["channels"][1][
        "max_observed_delta_s"
    ] == pytest.approx(0.4e-6)
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["time_axis_tolerance"] == metadata["time_axis_tolerance"]


def test_capture_cli_channel_all_expands_to_detected_model_channels(
    monkeypatch, capsys, tmp_path
):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveforms_byte(self, channels, points=1000):
            self.calls.append(("capture_waveforms_byte", channels, points))
            return MultiChannelWaveformCapture(
                tuple(_byte_waveform_capture(channel, points=points) for channel in channels)
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "all",
                "--csv",
                str(csv_path),
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("capture_waveforms_byte", (1, 2, 3, 4), 1000),
        "query_system_error",
    ]
    assert csv_path.read_text(encoding="utf-8").splitlines()[0] == (
        "time_s,ch1_v,ch2_v,ch3_v,ch4_v"
    )
    out = capsys.readouterr().out
    assert "Planned capture: CH1, CH2, CH3, CH4, 1000 points, BYTE format" in out
    assert "Actual points: CH1=2, CH2=2, CH3=2, CH4=2" in out


def test_capture_cli_channel_all_is_case_insensitive_and_supports_word(
    monkeypatch, capsys, tmp_path
):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveforms_word(self, channels, points=1000):
            self.calls.append(("capture_waveforms_word", channels, points))
            return MultiChannelWaveformCapture(
                tuple(_word_waveform_capture(channel, points=points) for channel in channels)
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "ALL",
                "--format",
                "word",
                "--csv",
                str(csv_path),
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("capture_waveforms_word", (1, 2, 3, 4), 1000),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert "Planned capture: CH1, CH2, CH3, CH4, 1000 points, WORD format" in out
    assert out.count("Command: :WAVeform:FORMat WORD") == 4


def test_capture_cli_multi_channel_word_uses_plural_api(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveforms_word(self, channels, points=1000):
            self.calls.append(("capture_waveforms_word", channels, points))
            return MultiChannelWaveformCapture(
                (
                    _word_waveform_capture(2, points=points),
                    _word_waveform_capture(1, points=points),
                )
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "2",
                "--channel",
                "1",
                "--points",
                "5000",
                "--format",
                "word",
                "--csv",
                str(csv_path),
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("capture_waveforms_word", (2, 1), 5000),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert "Planned capture: CH2, CH1, 5000 points, WORD format" in out
    assert "Command: :WAVeform:SOURce CHANnel2" in out
    assert "Command: :WAVeform:SOURce CHANnel1" in out
    assert out.count("Command: :WAVeform:FORMat WORD") == 2
    assert out.count("Command: :WAVeform:BYTeorder MSBFirst") == 2
    assert out.count("Command: :WAVeform:UNSigned ON") == 2
    assert csv_path.read_text(encoding="utf-8").splitlines()[0] == "time_s,ch2_v,ch1_v"


def test_capture_cli_reports_multi_channel_metadata_permission_error_without_traceback(
    monkeypatch, capsys, tmp_path
):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveforms_byte(self, channels, points=1000):
            self.calls.append(("capture_waveforms_byte", channels, points))
            return MultiChannelWaveformCapture(
                (
                    _byte_waveform_capture(1, points=points),
                    _byte_waveform_capture(2, points=points),
                )
            )

    scope = DummyScope()
    csv_path = tmp_path / "capture.csv"
    meta_path = tmp_path / "capture_meta.json"

    def fake_write_waveforms_metadata(capture, path, *, idn, resource):
        del capture, idn, resource
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    monkeypatch.setattr(
        core_output_files,
        "write_waveforms_metadata",
        fake_write_waveforms_metadata,
    )

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--channel",
                "2",
                "--csv",
                str(csv_path),
                "--meta",
                str(meta_path),
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn", ("capture_waveforms_byte", (1, 2), 1000)]
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "could not write waveform metadata JSON file" in captured.err
    assert str(meta_path) in captured.err
    assert "Permission denied" in captured.err


def test_capture_cli_rejects_duplicate_multi_channel_before_capture(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveforms_byte(self, channels, points=1000):
            self.calls.append(("capture_waveforms_byte", channels, points))
            raise AssertionError("capture should not be called")

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--channel",
                "1",
                "--csv",
                str(tmp_path / "capture.csv"),
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn"]
    err = capsys.readouterr().err
    assert "duplicate waveform channels are not allowed" in err


def test_capture_cli_rejects_channel_all_combined_with_explicit_channel(
    monkeypatch, capsys, tmp_path
):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveforms_byte(self, channels, points=1000):
            self.calls.append(("capture_waveforms_byte", channels, points))
            raise AssertionError("capture should not be called")

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "all",
                "--channel",
                "1",
                "--csv",
                str(tmp_path / "capture.csv"),
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn"]
    err = capsys.readouterr().err
    assert "--channel all cannot be combined with explicit channel numbers" in err


def test_capture_cli_rejects_unknown_channel_token():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["capture", "--resource", "USB0::FAKE::INSTR", "--channel", "abc"])

    assert excinfo.value.code == 2


def test_capture_cli_rejects_invalid_multi_channel_before_capture(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveforms_byte(self, channels, points=1000):
            self.calls.append(("capture_waveforms_byte", channels, points))
            raise AssertionError("capture should not be called")

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--channel",
                "5",
                "--csv",
                str(tmp_path / "capture.csv"),
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn"]
    err = capsys.readouterr().err
    assert "channel 5 is not available" in err


def test_capture_cli_uses_timestamped_default_csv_when_omitted(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveform_byte(self, channel, points=1000):
            self.calls.append(("capture_waveform_byte", channel, points))
            preamble = WaveformPreamble(
                raw="0,0,2,1,1.0E-6,0,0,2.0E-2,-2.56,128",
                format_code=0,
                type_code=0,
                points=2,
                count=1,
                x_increment=1e-6,
                x_origin=0.0,
                x_reference=0,
                y_increment=0.02,
                y_origin=-2.56,
                y_reference=128,
            )
            return WaveformCapture(
                channel=channel,
                requested_points=points,
                format_name="BYTE",
                preamble=preamble,
                raw_samples=(128, 129),
                time_s=(0.0, 1e-6),
                vertical_values=(-2.56, -2.54),
                vertical_unit="V",
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    default_csv_path = tmp_path / "data" / "2026-05-12-14-30-05.csv"
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    monkeypatch.setattr(cli, "_default_capture_csv_path", lambda: default_csv_path)

    assert cli.main(["capture", "--resource", "USB0::FAKE::INSTR", "--channel", "1"]) == 0

    assert scope.calls == ["query_idn", ("capture_waveform_byte", 1, 1000), "query_system_error"]
    assert default_csv_path.exists()
    assert (tmp_path / "data" / "2026-05-12-14-30-05_meta.json").exists()
    assert default_csv_path.read_text(encoding="utf-8").splitlines()[0] == "time_s,ch1_v"
    out = capsys.readouterr().out
    assert f"CSV: {default_csv_path}" in out
    assert f"Metadata: {tmp_path / 'data' / '2026-05-12-14-30-05_meta.json'}" in out
    assert 'System error: +0, "No error"' in out


def test_capture_cli_reports_csv_permission_error_without_traceback(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def capture_waveform_byte(self, channel, points=1000):
            self.calls.append(("capture_waveform_byte", channel, points))
            preamble = WaveformPreamble(
                raw="0,0,2,1,1.0E-6,0,0,2.0E-2,-2.56,128",
                format_code=0,
                type_code=0,
                points=2,
                count=1,
                x_increment=1e-6,
                x_origin=0.0,
                x_reference=0,
                y_increment=0.02,
                y_origin=-2.56,
                y_reference=128,
            )
            return WaveformCapture(
                channel=channel,
                requested_points=points,
                format_name="BYTE",
                preamble=preamble,
                raw_samples=(128, 129),
                time_s=(0.0, 1e-6),
                vertical_values=(-2.56, -2.54),
                vertical_unit="V",
            )

    scope = DummyScope()
    csv_path = tmp_path / "capture.csv"

    def fake_write_waveform_csv(capture, path):
        del capture
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    monkeypatch.setattr(core_output_files, "write_waveform_csv", fake_write_waveform_csv)

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--csv",
                str(csv_path),
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn", ("capture_waveform_byte", 1, 1000)]
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "could not write waveform CSV file" in captured.err
    assert str(csv_path) in captured.err
    assert "Permission denied" in captured.err
    assert "file may be open in another program" in captured.err
    assert "Excel" in captured.err


def test_capture_cli_rejects_channel_above_detected_capabilities(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "capture",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "5",
                "--csv",
                str(tmp_path / "capture.csv"),
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn"]
    err = capsys.readouterr().err
    assert "channel 5 is not available" in err


def test_screenshot_cli_writes_png_then_checks_error(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def capture_screenshot_png(self, *, background="black"):
            self.calls.append(("capture_screenshot_png", background))
            return ScreenshotCapture(
                format_name="PNG",
                palette="COLor",
                data=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
                background=background,
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    output_path = tmp_path / "screen.png"
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "screenshot",
                "--resource",
                "USB0::FAKE::INSTR",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("capture_screenshot_png", "black"), "query_system_error"]
    assert output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    out = capsys.readouterr().out
    assert "Resource: USB0::FAKE::INSTR" in out
    assert "Timeout ms: 2000" in out
    assert "Planned capture: current screen PNG image with black background" in out
    assert "Screenshot timeout ms: 10000 (temporary)" in out
    assert "Command: :HARDcopy:INKSaver OFF" in out
    assert "Command: :DISPlay:DATA? PNG, COLor" in out
    assert "Format: PNG" in out
    assert "Palette: COLor" in out
    assert "Background: black" in out
    assert "Bytes: 16" in out
    assert f"PNG: {output_path}" in out
    assert 'System error: +0, "No error"' in out


def test_screenshot_cli_uses_timestamped_default_output_when_omitted(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def capture_screenshot_png(self, *, background="black"):
            self.calls.append(("capture_screenshot_png", background))
            return ScreenshotCapture(
                format_name="PNG",
                palette="COLor",
                data=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
                background=background,
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    default_output_path = tmp_path / "data" / "2026-05-13-10-20-30.png"
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    monkeypatch.setattr(cli, "_default_screenshot_path", lambda: default_output_path)

    assert cli.main(["screenshot", "--resource", "USB0::FAKE::INSTR"]) == 0

    assert scope.calls == ["query_idn", ("capture_screenshot_png", "black"), "query_system_error"]
    assert default_output_path.exists()
    out = capsys.readouterr().out
    assert f"PNG: {default_output_path}" in out


def test_screenshot_cli_supports_white_background(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def capture_screenshot_png(self, *, background="black"):
            self.calls.append(("capture_screenshot_png", background))
            return ScreenshotCapture(
                format_name="PNG",
                palette="COLor",
                data=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
                background=background,
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    output_path = tmp_path / "screen.png"
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "screenshot",
                "--resource",
                "USB0::FAKE::INSTR",
                "--output",
                str(output_path),
                "--background",
                "white",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("capture_screenshot_png", "white"), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned capture: current screen PNG image with white background" in out
    assert "Command: :HARDcopy:INKSaver ON" in out
    assert "Background: white" in out


def test_default_screenshot_path_matches_capture_timestamp_format():
    assert cli._default_screenshot_path(datetime(2026, 5, 13, 10, 20, 30)) == (
        Path("data") / "2026-05-13-10-20-30.png"
    )


def test_screenshot_cli_reports_png_permission_error_without_traceback(monkeypatch, capsys, tmp_path):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def capture_screenshot_png(self, *, background="black"):
            self.calls.append(("capture_screenshot_png", background))
            return ScreenshotCapture(
                format_name="PNG",
                palette="COLor",
                data=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
                background=background,
            )

    scope = DummyScope()
    output_path = tmp_path / "screen.png"

    def fake_write_screenshot_png(capture, path):
        del capture
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))
    monkeypatch.setattr(cli, "write_screenshot_png", fake_write_screenshot_png)

    assert (
        cli.main(
            [
                "screenshot",
                "--resource",
                "USB0::FAKE::INSTR",
                "--output",
                str(output_path),
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn", ("capture_screenshot_png", "black")]
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "could not write screenshot PNG file" in captured.err
    assert str(output_path) in captured.err
    assert "Permission denied" in captured.err
    assert "file may be open in another program" in captured.err


@pytest.mark.parametrize(
    (
        "requested_item",
        "normalized_item",
        "value",
        "raw_value",
        "unit",
        "expected_command",
        "expected_value_line",
    ),
    [
        (
            "amplitude",
            "amplitude",
            1.2,
            "1.20E+0",
            "V",
            ":MEASure:VAMPlitude? CHANnel1",
            "Value V: 1.2",
        ),
        (
            "pwidth",
            "positive_width",
            0.000002,
            "2.00E-6",
            "s",
            ":MEASure:PWIDth? CHANnel1",
            "Value s: 2e-06",
        ),
        (
            "duty-cycle",
            "duty_cycle",
            48.0,
            "4.80E+1",
            "%",
            ":MEASure:DUTYcycle? CHANnel1",
            "Value %: 48",
        ),
        (
            "area",
            "area",
            0.0000012,
            "1.20E-6",
            "V*s",
            ":MEASure:AREA? CHANnel1",
            "Value V*s: 1.2e-06",
        ),
        (
            "acrms",
            "ac_rms",
            0.6,
            "6.00E-1",
            "V",
            ":MEASure:VRMS? DISPlay,AC,CHANnel1",
            "Value V: 0.6",
        ),
        (
            "x-at-max",
            "x_at_max",
            0.00000125,
            "1.25E-6",
            "s",
            ":MEASure:XMAX? CHANnel1",
            "Value s: 1.25e-06",
        ),
        (
            "pedges",
            "positive_edges",
            4.0,
            "4.0E+0",
            "count",
            ":MEASure:PEDGes? CHANnel1",
            "Value count: 4",
        ),
    ],
)
def test_measure_cli_queries_new_items_then_checks_error(
    monkeypatch,
    capsys,
    requested_item,
    normalized_item,
    value,
    raw_value,
    unit,
    expected_command,
    expected_value_line,
):
    scope = _install_measurement_scope(monkeypatch, value, raw_value, unit)

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--item",
                requested_item,
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("query_measurement", 1, normalized_item),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert f"Planned query: CH1 {normalized_item} measurement" in out
    assert f"Command: {expected_command}" in out
    assert f"Measurement: {normalized_item}" in out
    assert expected_value_line in out
    assert f"Raw response: {raw_value}" in out
    assert 'System error: +0, "No error"' in out


def test_measure_results_cli_dry_run_plans_only_read_only_query(capsys):
    assert (
        cli.main(
            [
                "measure-results",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox3024a",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["scpi"]["planned"] == [":MEASure:RESults?"]
    assert payload["result"] == {
        "operation": "query",
        "command": ":MEASure:RESults?",
        "raw": "",
        "items": [],
        "statistics_items": [],
    }


def test_measure_results_cli_json_includes_statistics_items(monkeypatch, capsys):
    raw = (
        "Amplitude(2),+2.48E+00,+2.48E+00,+2.48E+00,"
        "+2.48000000000000E+00,+0.0E+00,386"
    )

    class DummyScope:
        backend = _MeasurementDummyBackend()

        def __init__(self):
            self.capabilities = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def query_idn(self):
            self.capabilities = capabilities_for_model("DSOX4034A")
            return parse_idn("KEYSIGHT TECHNOLOGIES,DSOX4034A,MY123,07.20")

        def query_measurement_results(self):
            return parse_measurement_results_dump(raw)

    scope = DummyScope()
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: scope),
    )

    assert (
        cli.main(
            [
                "measure-results",
                "--resource",
                "USB0::FAKE::INSTR",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["raw"] == raw
    assert payload["result"]["items"] == []
    assert payload["result"]["statistics_items"] == [
        {
            "label": "Amplitude(2)",
            "current": 2.48,
            "minimum": 2.48,
            "maximum": 2.48,
            "mean": 2.48,
            "stddev": 0.0,
            "count": 386,
        }
    ]


@pytest.mark.parametrize(
    (
        "argv",
        "normalized_item",
        "kwargs",
        "unit",
        "expected_command",
        "expected_plan_fragment",
    ),
    [
        (
            ["--item", "y_at_x", "--time", "0"],
            "y_at_x",
            {"time_s": 0.0},
            "V",
            ":MEASure:VTIMe? 0,CHANnel1",
            "time=0.0",
        ),
        (
            ["--item", "tedge", "--slope", "negative", "--occurrence", "2"],
            "time_at_edge",
            {"slope": "negative", "occurrence": 2},
            "s",
            ":MEASure:TEDGe? -2,CHANnel1",
            "slope=negative, occurrence=2",
        ),
        (
            ["--item", "time-at-value", "--level", "0.5"],
            "time_at_value",
            {"level": 0.5, "slope": "positive", "occurrence": 1},
            "s",
            ":MEASure:TVALue? 0.5,+1,CHANnel1",
            "level=0.5, slope=positive, occurrence=1",
        ),
    ],
)
def test_measure_cli_queries_parameterized_items_then_checks_error(
    monkeypatch,
    capsys,
    argv,
    normalized_item,
    kwargs,
    unit,
    expected_command,
    expected_plan_fragment,
):
    scope = _install_measurement_scope(monkeypatch, 0.25, "2.5E-1", unit)

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                *argv,
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("query_measurement", 1, normalized_item, kwargs),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert f"Planned query: CH1 {normalized_item} measurement" in out
    assert expected_plan_fragment in out
    assert f"Command: {expected_command}" in out
    assert f"Measurement: {normalized_item}" in out
    assert f"Value {unit}: 0.25" in out
    assert 'System error: +0, "No error"' in out


@pytest.mark.parametrize(
    (
        "item",
        "value",
        "raw_value",
        "unit",
        "expected_command",
        "expected_value_line",
    ),
    [
        (
            "phase",
            90.0,
            "9.0E+1",
            "deg",
            ":MEASure:PHASe? CHANnel1,CHANnel2",
            "Value deg: 90",
        ),
        (
            "delay",
            0.00000125,
            "1.25E-6",
            "s",
            ":MEASure:DELay? AUTO,CHANnel1,CHANnel2",
            "Value s: 1.25e-06",
        ),
    ],
)
def test_measure_cli_queries_pair_items_then_checks_error(
    monkeypatch,
    capsys,
    item,
    value,
    raw_value,
    unit,
    expected_command,
    expected_value_line,
):
    scope = _install_measurement_scope(monkeypatch, value, raw_value, unit)

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                item,
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("query_pair_measurement", 1, 2, item),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert f"Planned query: CH1 to CH2 {item} measurement" in out
    assert f"Command: {expected_command}" in out
    assert f"Measurement: {item}" in out
    assert "Channel: 1" in out
    assert "Reference channel: 2" in out
    assert expected_value_line in out
    assert f"Raw response: {raw_value}" in out
    assert 'System error: +0, "No error"' in out


def test_measure_cli_treats_channel_as_source_alias_for_pair_item(monkeypatch, capsys):
    scope = _install_measurement_scope(monkeypatch, 90.0, "9.0E+1", "deg")

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "phase",
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("query_pair_measurement", 1, 2, "phase"),
        "query_system_error",
    ]
    assert "Command: :MEASure:PHASe? CHANnel1,CHANnel2" in capsys.readouterr().out


def test_measure_cli_accepts_source_channel_for_single_item(monkeypatch, capsys):
    scope = _install_measurement_scope(monkeypatch, 0.5, "5.0E-1", "V")

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--source-channel",
                "1",
                "--item",
                "vpp",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("query_measurement", 1, "vpp"), "query_system_error"]
    assert "Command: :MEASure:VPP? CHANnel1" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "expected_error"),
    [
        (["--item", "y_at_x"], "requires --time"),
        (["--item", "vpp", "--time", "0"], "can only be used"),
        (["--item", "time_at_edge", "--level", "0.5"], "cannot be used"),
        (["--item", "time_at_value"], "requires --level"),
    ],
)
def test_measure_cli_rejects_invalid_parameterized_args_without_query(
    monkeypatch, capsys, argv, expected_error
):
    scope = _install_measurement_scope(monkeypatch, 0.25, "2.5E-1", "V")

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                *argv,
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn"]
    captured = capsys.readouterr()
    assert expected_error in captured.err


@pytest.mark.parametrize(
    ("argv", "expected_error"),
    [
        (
            ["--channel", "1", "--source-channel", "2", "--item", "vpp"],
            "cannot be combined",
        ),
        (
            ["--source-channel", "1", "--item", "phase"],
            "requires --source-channel",
        ),
        (
            ["--source-channel", "1", "--reference-channel", "1", "--item", "phase"],
            "must be different",
        ),
        (
            ["--source-channel", "5", "--reference-channel", "1", "--item", "phase"],
            "channel 5 is not available",
        ),
        (
            ["--source-channel", "1", "--reference-channel", "2", "--item", "phase", "--time", "0"],
            "cannot be used with phase or delay",
        ),
        (
            ["--source-channel", "1", "--reference-channel", "2", "--item", "vpp"],
            "can only be used with phase or delay",
        ),
    ],
)
def test_measure_cli_rejects_invalid_pair_channel_args_without_query(
    monkeypatch, capsys, argv, expected_error
):
    scope = _install_measurement_scope(monkeypatch, 0.25, "2.5E-1", "V", model="DSOX4024A")

    assert cli.main(["measure", "--resource", "USB0::FAKE::INSTR", *argv]) == 1

    assert scope.calls == ["query_idn"]
    assert expected_error in capsys.readouterr().err


def test_measure_cli_rejects_delay_pair_when_capability_is_unsupported(monkeypatch, capsys):
    scope = _install_measurement_scope(
        monkeypatch,
        0.00000125,
        "1.25E-6",
        "s",
        model="DSOX3024A",
    )

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "delay",
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn"]
    assert "capability profile" in capsys.readouterr().err


def test_measure_cli_reports_invalid_sentinel_for_pair_item(monkeypatch, capsys):
    scope = _install_measurement_scope(
        monkeypatch,
        None,
        "9.9E+37",
        "deg",
        valid=False,
        reason="invalid measurement sentinel",
    )

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "phase",
            ]
        )
        == 1
    )

    assert scope.calls == [
        "query_idn",
        ("query_pair_measurement", 1, 2, "phase"),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert "Command: :MEASure:PHASe? CHANnel1,CHANnel2" in out
    assert "Reference channel: 2" in out
    assert "Valid: false" in out
    assert "Value: unavailable" in out
    assert "Raw response: 9.9E+37" in out
    assert "Reason: invalid measurement sentinel" in out


@pytest.mark.parametrize(
    ("requested_item", "normalized_item", "unit", "expected_command"),
    [
        ("overshoot", "overshoot", "%", ":MEASure:OVERshoot? CHANnel1"),
        ("positive_width", "positive_width", "s", ":MEASure:PWIDth? CHANnel1"),
        ("area", "area", "V*s", ":MEASure:AREA? CHANnel1"),
        ("x_at_min", "x_at_min", "s", ":MEASure:XMIN? CHANnel1"),
        ("negative-edges", "negative_edges", "count", ":MEASure:NEDGes? CHANnel1"),
    ],
)
def test_measure_cli_reports_invalid_sentinel_for_new_items(
    monkeypatch, capsys, requested_item, normalized_item, unit, expected_command
):
    scope = _install_measurement_scope(
        monkeypatch,
        None,
        "9.9E+37",
        unit,
        valid=False,
        reason="invalid measurement sentinel",
    )

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--item",
                requested_item,
            ]
        )
        == 1
    )

    assert scope.calls == [
        "query_idn",
        ("query_measurement", 1, normalized_item),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert f"Command: {expected_command}" in out
    assert f"Measurement: {normalized_item}" in out
    assert "Valid: false" in out
    assert "Value: unavailable" in out
    assert "Raw response: 9.9E+37" in out
    assert "Reason: invalid measurement sentinel" in out
    assert 'System error: +0, "No error"' in out


def test_measure_cli_queries_vpp_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def query_measurement(self, channel, item):
            self.calls.append(("query_measurement", channel, item))
            return MeasurementResult(
                item=item,
                channel=channel,
                value=0.5,
                raw_value="5.0E-1",
                valid=True,
                unit="V",
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--item",
                "vpp",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("query_measurement", 1, "vpp"), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned query: CH1 vpp measurement" in out
    assert "Command: :MEASure:VPP? CHANnel1" in out
    assert "Measurement: vpp" in out
    assert "Channel: 1" in out
    assert "Valid: true" in out
    assert "Value V: 0.5" in out
    assert "Raw response: 5.0E-1" in out
    assert 'System error: +0, "No error"' in out


def test_measure_cli_queries_vrms_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def query_measurement(self, channel, item):
            self.calls.append(("query_measurement", channel, item))
            return MeasurementResult(
                item=item,
                channel=channel,
                value=0.707,
                raw_value="7.07E-1",
                valid=True,
                unit="V",
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--item",
                "vrms",
            ]
        )
        == 0
    )

    assert scope.calls == ["query_idn", ("query_measurement", 1, "vrms"), "query_system_error"]
    out = capsys.readouterr().out
    assert "Planned query: CH1 vrms measurement" in out
    assert "Command: :MEASure:VRMS? DISPlay,DC,CHANnel1" in out
    assert "Measurement: vrms" in out
    assert "Value V: 0.707" in out
    assert "Raw response: 7.07E-1" in out
    assert 'System error: +0, "No error"' in out


def test_measure_cli_accepts_risetime_alias_then_checks_error(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = 2000

    class DummyScope:
        backend = DummyBackend()

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

        def query_measurement(self, channel, item):
            self.calls.append(("query_measurement", channel, item))
            return MeasurementResult(
                item=item,
                channel=channel,
                value=0.000001,
                raw_value="1.00E-6",
                valid=True,
                unit="s",
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--item",
                "risetime",
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("query_measurement", 1, "rise_time"),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert "Planned query: CH1 rise_time measurement" in out
    assert "Command: :MEASure:RISetime? CHANnel1" in out
    assert "Measurement: rise_time" in out
    assert "Value s: 1e-06" in out
    assert "Raw response: 1.00E-6" in out
    assert 'System error: +0, "No error"' in out


def test_measure_cli_accepts_freq_alias(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def query_measurement(self, channel, item):
            self.calls.append(("query_measurement", channel, item))
            return MeasurementResult(
                item=item,
                channel=channel,
                value=1000.0,
                raw_value="1.0E+3",
                valid=True,
                unit="Hz",
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--item",
                "freq",
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("query_measurement", 1, "frequency"),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert "Planned query: CH1 frequency measurement" in out
    assert "Command: :MEASure:FREQuency? CHANnel1" in out
    assert "Measurement: frequency" in out


def test_measure_cli_reports_invalid_sentinel_without_losing_raw(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def query_measurement(self, channel, item):
            self.calls.append(("query_measurement", channel, item))
            return MeasurementResult(
                item=item,
                channel=channel,
                value=None,
                raw_value="9.9E+37",
                valid=False,
                unit="Hz",
                reason="invalid measurement sentinel",
            )

        def query_system_error(self):
            self.calls.append("query_system_error")
            return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--item",
                "frequency",
            ]
        )
        == 1
    )

    assert scope.calls == [
        "query_idn",
        ("query_measurement", 1, "frequency"),
        "query_system_error",
    ]
    out = capsys.readouterr().out
    assert "Command: :MEASure:FREQuency? CHANnel1" in out
    assert "Measurement: frequency" in out
    assert "Valid: false" in out
    assert "Value: unavailable" in out
    assert "Raw response: 9.9E+37" in out
    assert "Reason: invalid measurement sentinel" in out
    assert 'System error: +0, "No error"' in out


def test_measure_cli_rejects_channel_above_detected_capabilities(monkeypatch, capsys):
    class DummyBackend:
        backend = "backend"
        timeout = None

    class DummyScope:
        backend = DummyBackend()

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

        def query_measurement(self, channel, item):
            self.calls.append(("query_measurement", channel, item))
            raise AssertionError("measurement query should not be sent")

    scope = DummyScope()
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda resource, visa_library=None: scope))

    assert (
        cli.main(
            [
                "measure",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "5",
                "--item",
                "vpp",
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn"]
    err = capsys.readouterr().err
    assert "channel 5 is not available" in err
