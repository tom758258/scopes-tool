import json

import pytest

from scopes_tool_cli import cli, runtime
import scopes_tool_core.drivers as drivers_module
import scopes_tool_core.identity as identity_module
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.identity import PhysicalModelInfo
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.tektronix_simulator import TektronixSimulatorBackend
from scopes_tool_core.visa_backend import VisaResourceListing


@pytest.mark.parametrize("command,options,query,response,field,expected", [
    ("channel-bandwidth-limit", ["--channel", "1"], "CH1:BANdwidth?", "20.0000E+6", "bandwidth_limit", True),
    ("channel-bandwidth-limit", ["--channel", "1"], "CH1:BANdwidth?", "70.0000E+6", "bandwidth_limit", False),
    ("save-waveform-format", [], "SAVe:WAVEform:FILEFormat?", "INTERNAL", "format", "internal"),
    ("save-waveform-format", [], "SAVe:WAVEform:FILEFormat?", "INTERN", "format", "internal"),
    ("save-waveform-format", [], "SAVe:WAVEform:FILEFormat?", "SPREADSheet", "format", "csv"),
])
def test_tbs2074_cli_readbacks(monkeypatch, capsys, command, options, query, response, field, expected):
    original_query = TektronixSimulatorBackend.query

    def readback(backend, scpi):
        if scpi == query:
            backend.history.append(scpi)
            return response
        return original_query(backend, scpi)

    monkeypatch.setattr(TektronixSimulatorBackend, "query", readback)
    assert cli.main([command, *options, "--query", "--simulate", "--model", "tektronix-tbs2074", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["result"][field] == expected
    assert payload["scpi"]["sent"] == ["*IDN?", query, "*ESR?"]


def test_tbs2074_cli_channel_summary_numeric_bandwidth(monkeypatch, capsys):
    original_query = TektronixSimulatorBackend.query

    def readback(backend, scpi):
        if scpi in {f"CH{channel}:BANdwidth?" for channel in range(1, 5)}:
            backend.history.append(scpi)
            return "20.0000E+6" if scpi.startswith("CH1:") else "70.0000E+6"
        return original_query(backend, scpi)

    monkeypatch.setattr(TektronixSimulatorBackend, "query", readback)
    assert cli.main(["channel-summary", "--simulate", "--model", "tektronix-tbs2074", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert [channel["bandwidth_limit"] for channel in payload["result"]["channels"]] == [True, False, False, False]
    assert all(command.endswith("?") for command in payload["scpi"]["sent"])


def test_tbs2074_cli_save_waveform_format_rejects_internal(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["save-waveform-format", "--format", "internal", "--simulate", "--model", "tektronix-tbs2074", "--json"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "internal" in captured.err


def _register_synthetic_model(monkeypatch, *, driver_id):
    physical_model = PhysicalModelInfo(
        model_id="keysight-synthetic1000",
        vendor_id="keysight",
        canonical_model="SYNTH1000",
        display_name="Keysight Synthetic 1000",
        series="SYNTHETIC",
        capability_profile_id="keysight-infiniivision-4000x",
        driver_id=driver_id,
    )
    identity_index = dict(identity_module._PHYSICAL_MODEL_BY_VENDOR_AND_MODEL)
    identity_index[("keysight", "SYNTH1000")] = physical_model
    model_id_index = dict(identity_module._PHYSICAL_MODEL_BY_ID)
    model_id_index[physical_model.model_id] = physical_model
    monkeypatch.setattr(
        identity_module,
        "_PHYSICAL_MODEL_BY_VENDOR_AND_MODEL",
        identity_index,
    )
    monkeypatch.setattr(
        identity_module,
        "_PHYSICAL_MODEL_BY_ID",
        model_id_index,
    )
    return physical_model


def test_one_shot_live_command_uses_detected_driver_subclass(monkeypatch, capsys):
    selected_instances = []

    class SyntheticScope(Oscilloscope):
        def run(self):
            selected_instances.append(self)
            super().run()

    physical_model = _register_synthetic_model(
        monkeypatch,
        driver_id="synthetic-driver",
    )
    driver_registry = dict(drivers_module.DRIVER_REGISTRY)
    driver_registry[physical_model.driver_id] = SyntheticScope
    monkeypatch.setattr(drivers_module, "DRIVER_REGISTRY", driver_registry)
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,SYNTH1000,SN1,1.0",
            ":SYSTem:ERRor?": '+0,"No error"',
        }
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(
            lambda resource, visa_library=None: Oscilloscope(backend)
        ),
    )

    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR"]) == 0

    assert len(selected_instances) == 1
    assert isinstance(selected_instances[0], SyntheticScope)
    assert backend.history == ["*IDN?", ":RUN", ":SYSTem:ERRor?"]
    capsys.readouterr()


def test_one_shot_live_unknown_driver_blocks_state_change(monkeypatch, capsys):
    _register_synthetic_model(
        monkeypatch,
        driver_id="unregistered-driver",
    )
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,SYNTH1000,SN1,1.0",
        }
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(
            lambda resource, visa_library=None: Oscilloscope(backend)
        ),
    )

    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR"]) == 1

    assert backend.history == ["*IDN?"]
    assert backend.closed is True
    assert "unregistered driver ID" in capsys.readouterr().err


def test_one_shot_live_idn_parse_failure_closes_backend(monkeypatch, capsys):
    backend = FakeBackend(responses={"*IDN?": "malformed"})
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(
            lambda resource, visa_library=None: Oscilloscope(backend)
        ),
    )

    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR"]) == 1

    assert backend.history == ["*IDN?"]
    assert backend.closed is True
    capsys.readouterr()


@pytest.mark.parametrize("json_args", [[], ["--json"]])
def test_one_shot_identify_rejects_unknown_tek_model(monkeypatch, capsys, json_args):
    backend = FakeBackend(responses={"*IDN?": "TEKTRONIX,TBS9999B,SN1,1.0"})
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["identify", "--resource", "USB0::FAKE::INSTR", *json_args]) == 1
    assert backend.history == ["*IDN?"]
    assert backend.closed is True
    captured = capsys.readouterr()
    if json_args:
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert "Unsupported physical oscilloscope model" in payload["error"]["message"]
    else:
        assert "Unsupported physical oscilloscope model" in captured.err


@pytest.mark.parametrize("vendor,model,series,model_id", [
    ("KEYSIGHT TECHNOLOGIES", "DSOX4024A", "4000X", "keysight-dsox4024a"),
    ("TEKTRONIX", "TBS2074", "TBS2000", "tektronix-tbs2074"),
    ("KEYSIGHT TECHNOLOGIES", "DSOX4999A", "4000X", None),
    ("UNKNOWN VENDOR", "UNKNOWN1000", None, None),
    ("UNKNOWN VENDOR", "DSOX4024A", "4000X", None),
])
def test_one_shot_identify_json_model_id(monkeypatch, capsys, vendor, model, series, model_id):
    raw_idn = f"{vendor},{model},SN1,FW1"
    backend = FakeBackend(responses={"*IDN?": raw_idn})
    opened = []

    def fake_open(resource, visa_library=None):
        opened.append((resource, visa_library))
        return Oscilloscope(backend)

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fake_open))

    assert cli.main(["identify", "--resource", "USB0::FAKE::INSTR", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    idn = payload["idn"]
    assert payload["schema_version"] == 2
    assert payload["ok"] is True
    assert idn == payload["result"]["idn"]
    assert idn == {
        "raw": raw_idn,
        "vendor": vendor,
        "model": model,
        "serial": "SN1",
        "firmware": "FW1",
        "series": series,
        "model_id": model_id,
    }
    assert payload["capabilities"] == payload["result"]["capabilities"]
    if model_id is None:
        assert payload["capabilities"] is None
    else:
        assert payload["capabilities"]["analog_channels"] == 4
    assert opened == [("USB0::FAKE::INSTR", None)]
    assert backend.history == ["*IDN?"]
    assert backend.closed is True


def test_tek_simulator_uses_tek_driver_and_status_path(monkeypatch, capsys):
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda *args, **kwargs: pytest.fail("opened")))
    assert cli.main(["run", "--simulate", "--model", "tektronix-tbs2074", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert runtime._backend_history() == ["ACQuire:STOPAfter RUNSTop", "ACQuire:STATE ON", "*ESR?"]
    assert payload["backend"] == "Tektronix simulator"
    assert payload["result"]["commands"] == ["ACQuire:STOPAfter RUNSTop", "ACQuire:STATE ON"]
    assert payload["result"]["command"] == "ACQuire:STATE ON"
    assert payload["result"]["post_command_status"]["value"] == 0


def test_tek_simulator_unsupported_command_fails_without_business_scpi(capsys):
    assert cli.main(["measure-results", "--simulate", "--model", "tektronix-tbs2074"]) == 1
    assert runtime._backend_history() == []
    assert runtime._LAST_BACKEND is None
    assert "unsupported" in capsys.readouterr().err.lower()


@pytest.mark.parametrize("entry", ["main", "json_executor"])
def test_unsupported_command_clears_previous_backend_history(monkeypatch, capsys, entry):
    assert cli.main(["run", "--simulate", "--model", "tektronix-tbs2074", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["scpi"]["sent"]
    previous = runtime._LAST_BACKEND
    previous_history = list(previous.history)

    def unexpected_open(*args, **kwargs):
        pytest.fail("Unsupported operation must not create a backend")

    monkeypatch.setattr(runtime, "_make_simulator_backend", unexpected_open)
    monkeypatch.setattr(runtime.Oscilloscope, "open", unexpected_open)
    argv = ["measure-results", "--simulate", "--model", "tektronix-tbs2074", "--json"]
    if entry == "main":
        code = cli.main(argv)
        payload = json.loads(capsys.readouterr().out)
    else:
        args = cli.cli_parser._build_parser().parse_args(argv)
        payload, code = cli._execute_json_command(args)
    assert code == 1 and payload["ok"] is False
    assert "unsupported" in payload["error"]["message"]
    assert payload["scpi"]["sent"] == []
    assert runtime._LAST_BACKEND is None
    assert previous.history == previous_history


def test_tek_live_run_uses_esr_without_system_error_queue(monkeypatch, capsys):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TBS2074,SN1,1.0",
        "*ESR?": "0", "*OPC?": "1",
    })
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR", "--model", "keysight-dsox4024a", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert backend.history == ["*IDN?", "ACQuire:STOPAfter RUNSTop", "ACQuire:STATE ON", "*ESR?"]
    assert payload["system_error"] is None
    assert payload["result"]["post_command_status"]["value"] == 0


def test_tek_esr_error_is_structured_without_system_error_queue(monkeypatch, capsys):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TBS2074,SN1,1.0",
        "*ESR?": "8",
    })
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["run", "--resource", "USB0::FAKE::INSTR", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert backend.history == ["*IDN?", "ACQuire:STOPAfter RUNSTop", "ACQuire:STATE ON", "*ESR?"]
    assert payload["system_error"] is None
    assert "raw SESR '8'" in payload["error"]["message"]


def test_tek_explicit_standard_event_reads_esr_once(monkeypatch, capsys):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TDS2024B,SN1,1.0",
        "*ESR?": "8",
    })
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["system-standard-event", "--query", "--resource", "USB0::FAKE::INSTR", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert backend.history == ["*IDN?", "*ESR?"]
    assert payload["result"]["value"] == 8
    assert payload["system_error"] is None


def test_tek_invalid_average_count_does_not_change_mode(monkeypatch, capsys):
    backend = FakeBackend(responses={"*IDN?": "TEKTRONIX,TBS2074,SN1,1.0"})
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["acquisition", "--type", "average", "--count", "3", "--resource", "USB0::FAKE::INSTR"]) == 1
    assert backend.history == ["*IDN?"]
    assert "Unsupported Tek average count" in capsys.readouterr().err


@pytest.mark.parametrize("command,args,expected", [
    ("channel-scale", ["--channel", "1", "--volts-per-division", "0.2"], ["CH1:SCAle 0.2"]),
    ("reference-save", ["--slot", "1", "--source-channel", "1"], ["SAVe:WAVEform CH1,REF1", "*OPC?"]),
    ("save-pwd", ["--path", "C:/data"], ['FILESystem:CWD "C:/data"']),
    ("trigger-edge", ["--source-channel", "1", "--level", "0.5", "--slope", "positive"], [
        "TRIGger:A:EDGE:SOUrce CH1", "TRIGger:A:LEVel:CH1 0.5", "TRIGger:A:EDGE:SLOpe RISe",
    ]),
])
def test_tek_live_metadata_matches_sent_business_commands(monkeypatch, capsys, command, args, expected):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TBS2074,SN1,1.0",
        "*ESR?": "0", "*OPC?": "1",
    })
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main([command, *args, "--resource", "USB0::FAKE::INSTR", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert backend.history == ["*IDN?", *expected, "*ESR?"]
    assert payload["result"].get("commands", [payload["result"].get("command")]) == expected


def test_tds2000b_display_vectors_metadata_matches_sent_command(monkeypatch, capsys):
    backend = FakeBackend(responses={
        "*IDN?": "TEKTRONIX,TDS2024B,SN1,1.0",
        "DISPlay:STYle?": ":DISPLAY:STYLE VECTORS",
        "*ESR?": "0", "*OPC?": "1",
    })
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main([
        "display-vectors", "--on",
        "--resource", "USB0::FAKE::INSTR", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert backend.history == [
        "*IDN?", "DISPlay:STYle VECtors", "*ESR?"
    ]
    assert payload["result"]["command"] == "DISPlay:STYle VECtors"


@pytest.mark.parametrize("vendor,model,series,model_id", [
    ("KEYSIGHT TECHNOLOGIES", "DSOX4024A", "4000X", "keysight-dsox4024a"),
    ("TEKTRONIX", "TBS2074", "TBS2000", "tektronix-tbs2074"),
    ("TEKTRONIX", "TBS2072", None, None),
    ("UNKNOWN VENDOR", "UNKNOWN1000", None, None),
])
def test_live_resource_discovery_model_id(monkeypatch, capsys, vendor, model, series, model_id):
    raw_idn = f"{vendor},{model},FAKE_SERIAL,FW1"
    backend = FakeBackend(responses={"*IDN?": raw_idn})
    monkeypatch.setattr(
        cli, "list_visa_resources",
        lambda visa_library=None: VisaResourceListing(resources=("USB0::FAKE::INSTR",), backend="test"),
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main(["list-resources", "--live-only", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert backend.history == ["*IDN?"]
    assert payload["result"]["live_resources"] == [
        {
            "resource": "USB0::FAKE::INSTR",
            "idn": {
                "raw": raw_idn,
                "vendor": vendor,
                "model": model,
                "series": series,
                "serial": "FAKE_SERIAL",
                "firmware": "FW1",
            },
            "model_id": model_id,
        }
    ]
    assert payload["schema_version"] == 2
    assert payload["backend"] == payload["result"]["backend"] == "test"
    assert payload["result"]["resources"] == ["USB0::FAKE::INSTR"]
    assert payload["result"]["live_only"] is True
    assert backend.closed is True
    assert "verification_failures" not in payload["result"]


@pytest.mark.parametrize("model,format_name,signature", [
    ("tektronix-tbs2074", "png", b"\x89PNG"),
    ("tektronix-tds2024b", "bmp", b"BM"),
    ("tektronix-tbs1052b", "jpeg", b"\xff\xd8"),
])
def test_screenshot_text_reports_native_format(tmp_path, capsys, model, format_name, signature):
    output = tmp_path / f"screen.{format_name}"
    assert cli.main([
        "screenshot", "--simulate", "--model", model,
        "--format", format_name, "--output", str(output),
    ]) == 0
    text = capsys.readouterr().out
    assert f"{format_name.upper()}: {output}" in text
    assert output.read_bytes().startswith(signature)
    if format_name == "jpeg":
        assert "BMP:" not in text and "PNG:" not in text


@pytest.mark.parametrize("mode", ["--simulate", "--dry-run"])
def test_cli_tds_explicit_bmp_only(mode, tmp_path, capsys):
    output = tmp_path / "screen.bmp"
    common = [mode, "--model", "tektronix-tds2024b", "--json"]
    assert cli.main(["screenshot", "--format", "bmp", "--output", str(output), *common]) == 0
    payload = json.loads(capsys.readouterr().out)
    if mode == "--simulate":
        assert output.read_bytes().startswith(b"BM")
        assert payload["result"]["format"] == "BMP"
        assert payload["result"]["files"][0]["kind"] == "bmp"
    else:
        assert not output.exists()
        assert "HARDCopy STARt" in payload["scpi"]["planned"]
    for options in ([], ["--format", "png"], ["--query-hardcopy"]):
        assert cli.main(["screenshot", *options, *common]) != 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False


def test_worker_tbs1052b_screenshot_uses_core_jpeg_support(tmp_path):
    from scopes_tool_cli import worker
    from tests.cli._worker_test_support import make_worker_runtime
    from scopes_tool_core.errors import OscilloscopeError

    worker_runtime = make_worker_runtime(model="tektronix-tbs1052b")
    output = tmp_path / "screen.jpeg"
    args = worker.parse_domain_command("screenshot", {"output": str(output), "format": "jpeg"}, worker_runtime)
    payload, code = cli._execute_json_command(args)
    assert code == 0 and payload["ok"] is True
    assert payload["capabilities"]["screenshot_formats"] == ["jpeg"]
    assert payload["result"]["format"] == "JPEG"
    assert output.read_bytes().startswith(b"\xff\xd8") and output.read_bytes().endswith(b"\xff\xd9")
    with pytest.raises(OscilloscopeError, match="unsupported"):
        worker.parse_domain_command("screenshot", {"output": str(tmp_path / "screen.bmp"), "format": "bmp"}, worker_runtime)


def test_cli_keysight_tcpip_bmp_reaches_detected_driver(monkeypatch, tmp_path, capsys):
    output = tmp_path / "screen.bmp"
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,SN1,1.0",
            ":HARDcopy:INKSaver?": "0",
            ":SYSTem:ERRor?": '+0,"No error"',
        },
        binary_responses={":HCOPY:SDUMp:DATA? BMP": list(b"BMbitmap")},
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main([
        "screenshot", "--format", "bmp", "--output", str(output),
        "--resource", "TCPIP0::192.0.2.1::INSTR",
    ]) == 0
    assert output.read_bytes().startswith(b"BM")
    assert backend.history[0] == "*IDN?"
    assert ":HCOPY:SDUMp:DATA? BMP" in backend.history
    capsys.readouterr()


def test_cli_tds_bmp_allows_usbtmc_after_detected_driver(monkeypatch, tmp_path, capsys):
    from scopes_tool_core.visa_backend import VisaBackend
    class VisaStub(FakeBackend, VisaBackend):
        pass
    output = tmp_path / "screen.bmp"
    backend = VisaStub(
        resource_name="USB0::FAKE::INSTR",
        responses={
            "*IDN?": "TEKTRONIX,TDS2024B,SN1,1.0",
            "HARDCopy:FORMat?": "RLE",
            "HARDCopy:PORT?": "FILE",
            "HARDCopy:INKSaver?": "OFF",
            "*ESR?": "0",
        },
        raw_response=b"BMbitmap",
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main([
        "screenshot", "--format", "bmp", "--output", str(output),
        "--resource", "USB0::FAKE::INSTR",
    ]) == 0
    assert output.read_bytes().startswith(b"BM")
    assert backend.history[0] == "*IDN?"
    assert "HARDCopy STARt" in backend.history
    capsys.readouterr()


@pytest.mark.parametrize("resource", ["TCPIP0::192.0.2.1::INSTR", "ASRL1::INSTR", "USB0::FAKE::RAW"])
def test_cli_tds_bmp_rejects_other_transports_after_detected_driver(monkeypatch, tmp_path, capsys, resource):
    from scopes_tool_core.visa_backend import VisaBackend
    class VisaStub(FakeBackend, VisaBackend):
        pass
    backend = VisaStub(
        resource_name=resource,
        responses={"*IDN?": "TEKTRONIX,TDS2024B,SN1,1.0"}
    )
    monkeypatch.setattr(
        runtime.Oscilloscope,
        "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )

    assert cli.main([
        "screenshot", "--format", "bmp", "--output", str(tmp_path / "screen.bmp"),
        "--resource", resource, "--model", "keysight-dsox4024a",
    ]) == 1
    assert backend.history == ["*IDN?"]
    assert "requires a USBTMC resource" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["--simulate", "--dry-run"])
def test_cli_periodic_measurement_admission(mode, capsys):
    common = [mode, "--model", "tektronix-tbs2074", "--json"]
    assert cli.main(["measure-install", "--source-channel", "1", "--item", "vpp", *common]) == 0
    payload = json.loads(capsys.readouterr().out)
    commands = payload["scpi"]["sent" if mode == "--simulate" else "planned"]
    assert "MEASUrement:MEAS1:TYPe PK2Pk" in commands
    assert not any(command.startswith(":MEAS") for command in commands)
    assert cli.main(["measure-clear", *common]) == 0
    capsys.readouterr()
    assert cli.main(["measure-results", *common]) != 0
    capsys.readouterr()


@pytest.mark.parametrize("mode", ["--simulate", "--dry-run"])
def test_cli_tds2000b_cursor_and_timed_persistence(mode, capsys):
    common = [mode, "--model", "tektronix-tds2024b", "--json"]
    for args in (["cursor", "--source-channel", "1", "--x1", "0.02", "--auto-timebase"],
                 ["cursor", "--source-channel", "1", "--y1", "0.2"],
                 ["display-persistence", "--seconds", "2"]):
        assert cli.main([*args, *common]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        commands = payload["scpi"]["sent" if mode == "--simulate" else "planned"]
        assert not any(command.startswith(":MARKer") or "YUNit " in command for command in commands)


def test_cli_metadata_uses_driver_commands(capsys):
    cases = [
        ("tbs2074", ["channel-units", "--channel", "1", "--units", "amp"]),
        ("tbs2074", ["math-display", "--function", "1", "--on"]),
        ("tbs2074", ["math-operator", "--function", "1", "--operation", "add", "--source1", "channel1", "--source2", "channel2"]),
        ("tbs2074", ["trigger-runt", "--query"]),
        ("tds2024b", ["trigger-tv", "--source-channel", "1", "--standard", "pal", "--mode", "all-lines", "--polarity", "negative"]),
        ("tbs2074", ["save-image-format", "--format", "bmp"]),
        ("tbs2074", ["save-waveform-format", "--format", "csv"]),
    ]
    for model, args in cases:
        assert cli.main([*args, "--simulate", "--model", "tektronix-" + model, "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        result = payload["result"]
        commands = result.get("commands", [result.get("command")])
        sent = payload["scpi"]["sent"][1:-1]
        assert commands == (sent if "commands" in result else sent[:1])
