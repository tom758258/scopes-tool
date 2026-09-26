"""Hardware-free coverage for the registered Tektronix command dialect."""

import json

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id, operation_supported
from scopes_tool_core.drivers import driver_for_physical_model
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError, UnsupportedModelError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.identity import physical_model_for_id, resolve_physical_model_identity
from scopes_tool_core.tektronix import TektronixOscilloscope
from scopes_tool_core.run_config import ResolvedRunConfig, RunModeOptions, open_scope_for_run
from scopes_tool_core.simulator_backend import SimulatorBackendError
from scopes_tool_core.operations import query_acquisition_readouts, query_instrument_summary
from scopes_tool_core.screenshot import ScreenshotOptions
from scopes_tool_core.errors import ScreenshotResponseError


MODELS = (
    ("tektronix-tbs2074b", "TBS2074B", 4),
    ("tektronix-tds2024b", "TDS2024B", 4),
    ("tektronix-tbs1052b", "TBS1052B", 2),
)


def simulated_scope(model_id):
    options = RunModeOptions(simulate=True, planning_physical_model_id=model_id)
    scope = open_scope_for_run(ResolvedRunConfig(
        mode="simulate", planning_physical_model_id=model_id,
        expected_physical_model_id=None, capabilities=None,
        resource=f"SIM::{model_id}::INSTR", options=options,
    ))
    scope.query_idn()
    return scope


def test_tek_simulator_representative_roundtrips():
    with simulated_scope("tektronix-tbs2074b") as scope:
        scope.set_channel_label(1, "Input")
        assert scope.query_channel_label(1) == "Input"
        scope.configure_trigger_edge_level(source_channel=1, level_volts=0.25)
        assert scope.query_trigger_edge_level(source_channel=1).level_volts == pytest.approx(0.25)
    with simulated_scope("tektronix-tds2024b") as scope:
        scope.set_timebase_position(0.002)
        assert scope.query_timebase_position() == pytest.approx(0.002)
    with simulated_scope("tektronix-tbs1052b") as scope:
        scope.set_channel_scale(2, 0.5)
        assert scope.query_channel_scale(2) == pytest.approx(0.5)
        with pytest.raises((ParameterValidationError, SimulatorBackendError)):
            scope.set_channel_scale(3, 1.0)
        assert 3 not in scope.backend.channel_scale


def test_tbs2074b_scenario_trigger_level_readback(tmp_path):
    scenario = tmp_path / "trigger.json"
    scenario.write_text(json.dumps({"trigger": {"source_channel": "CH1", "level_v": 0.5}}), encoding="utf-8")
    model_id = "tektronix-tbs2074b"
    options = RunModeOptions(simulate=True, planning_physical_model_id=model_id, simulate_scenario=str(scenario))
    with open_scope_for_run(ResolvedRunConfig(
        mode="simulate", planning_physical_model_id=model_id,
        expected_physical_model_id=None, capabilities=None,
        resource=f"SIM::{model_id}::INSTR", options=options,
    )) as scope:
        assert scope.query_trigger_edge_level(source_channel=1).level_volts == pytest.approx(0.5)


def make_scope(model_id="tektronix-tbs2074b", responses=None):
    model = physical_model_for_id(model_id)
    backend = FakeBackend(responses={"*IDN?": f"TEKTRONIX,{model.canonical_model},SN,1.0", "*ESR?": "0", "*OPC?": "1", **(responses or {})})
    scope = TektronixOscilloscope(backend)
    scope.query_idn()
    return scope, backend


@pytest.mark.parametrize("model_id,model,channels", MODELS)
def test_registered_identity_driver_and_channels(model_id, model, channels):
    physical = resolve_physical_model_identity("TEKTRONIX", model)
    assert physical.model_id == model_id
    assert driver_for_physical_model(physical) is TektronixOscilloscope
    assert capabilities_for_model_id(model_id).analog_channels == channels
    scope, _ = make_scope(model_id)
    assert scope.idn.model_id == model_id


def test_unknown_tek_model_fails_closed():
    with pytest.raises(UnsupportedModelError):
        resolve_physical_model_identity("TEKTRONIX", "TBS9999B")


@pytest.mark.parametrize("model_id,_,__", MODELS)
def test_capability_subset_and_unsupported_leaks(model_id, _, __):
    capabilities = capabilities_for_model_id(model_id)
    for operation in ("run", "channel-scale", "setup-save", "trigger-edge", "list-resources"):
        assert operation_supported(capabilities, operation)
    for operation in ("measure", "measure-sweep", "measure-results", "capture", "check-error", "single-wait", "trigger-pulse-width",
                      "reference-query", "save-waveform", "doctor", "smoke", "cleanup", "acquisition-check",
                      "capture-batch", "capture-until", "capture-monitor", "measure-log", "measure-until",
                      "triggered-measure-loop", "triggered-capture-series", "sequence"):
        assert not operation_supported(capabilities, operation)
    for operation in ("channel-units", "display-persistence", "cursor-query", "cursor-off", "math-display",
                      "math-operator", "measure-install", "measure-clear", "save-image", "acquisition-points",
                      "record-length", "channel-summary", "live-data-snapshot", "system-information-snapshot"):
        assert operation_supported(capabilities, operation)
    b2 = model_id == "tektronix-tbs2074b"
    assert capabilities.trigger_modes == (("edge", "glitch", "runt") if b2 else ("edge", "glitch", "tv"))
    assert capabilities.trigger_edge_sources == (("analog-channel", "line") if b2 else ("analog-channel", "line", "external"))
    for operation in (("sample-rate", "trigger-runt", "save-image-format", "save-waveform-format") if b2
                      else ("cursor-set", "trigger-tv", "save-image-ink-saver")):
        assert operation_supported(capabilities, operation)
    assert not capabilities.supports_measure_results_dump
    assert not capabilities.supports_screenshot
    assert operation_supported(capabilities, "screenshot") is (model_id == "tektronix-tds2024b")
    assert operation_supported(capabilities, "display-vectors") is (
        model_id in {"tektronix-tds2024b", "tektronix-tbs1052b"}
    )


@pytest.mark.parametrize("model_id,_,__", MODELS)
def test_run_single_stop_and_force_use_tek_commands(model_id, _, __):
    scope, backend = make_scope(model_id)
    scope.run()
    scope.single()
    scope.stop()
    scope.force_trigger()
    assert backend.history[1:] == [
        "ACQuire:STOPAfter RUNSTop", "ACQuire:STATE ON",
        "ACQuire:STATE OFF", "ACQuire:STOPAfter SEQuence", "ACQuire:STATE ON",
        "ACQuire:STATE OFF", "TRIGger FORCe",
    ]


@pytest.mark.parametrize("model_id,count,mode", [
    ("tektronix-tbs2074b", 512, "high_resolution"),
    ("tektronix-tds2024b", 64, "peak"),
    ("tektronix-tbs1052b", 16, "normal"),
])
def test_acquisition_values_and_count_reject_before_scpi(model_id, count, mode):
    scope, backend = make_scope(model_id)
    scope.set_acquisition_type(mode)
    scope.set_acquisition_count(count)
    expected_mode = {"high_resolution": "HIRes", "peak": "PEAKdetect", "normal": "SAMple"}[mode]
    assert backend.history[-2:] == [f"ACQuire:MODe {expected_mode}", f"ACQuire:NUMAVg {count}"]
    history = list(backend.history)
    with pytest.raises(ParameterValidationError):
        scope.set_acquisition_count(3)
    with pytest.raises(ParameterValidationError):
        scope.set_acquisition_type("invalid")
    assert backend.history == history


@pytest.mark.parametrize("model_id,reference", [
    ("tektronix-tbs2074b", "REF1"),
    ("tektronix-tds2024b", "REFA"),
    ("tektronix-tbs1052b", "REFA"),
])
def test_reference_setup_and_autoscale_boundaries(model_id, reference):
    scope, backend = make_scope(model_id)
    scope.save_reference_waveform(1, 1)
    scope.configure_reference_display(1, True)
    scope.save_setup(slot=9)
    scope.recall_setup(slot=1)
    scope.autoscale(None)
    assert backend.history[1:] == [
        f"SAVe:WAVEform CH1,{reference}", "*OPC?", f"SELect:{reference} ON",
        "SAVe:SETUp 9", "RECAll:SETUp 1", "AUTOSet EXECute",
    ]
    history = list(backend.history)
    for action in (
        lambda: scope.save_reference_waveform(3, 1),
        lambda: scope.save_setup(slot=0),
        lambda: scope.recall_setup(file_spec="x.scp"),
        lambda: scope.autoscale((1,)),
    ):
        with pytest.raises(ParameterValidationError):
            action()
    assert backend.history == history


def test_b2_channel_and_trigger_mappings():
    scope, backend = make_scope()
    scope.set_channel_probe_ratio(1, 10)
    scope.set_channel_bandwidth_limit(1, True)
    scope.set_channel_bandwidth_limit(1, False)
    scope.set_channel_label(1, "A")
    scope.set_channel_probe_skew(1, 100e-9)
    scope.configure_trigger_mode("edge")
    scope.configure_trigger_sweep("normal")
    scope.configure_trigger_edge_coupling("lf-reject")
    scope.configure_trigger_edge_level(source_channel=1, level_volts=0.5)
    scope.set_trigger_holdoff(40e-9)
    assert backend.history[1:] == [
        "CH1:PRObe:GAIN 0.1", "CH1:BANdwidth TWEnty", "CH1:BANdwidth FULl",
        'CH1:LABel "A"', "CH1:DESKew 1e-07", "TRIGger:A:TYPe EDGE",
        "TRIGger:A:MODe NORMal", "TRIGger:A:EDGE:COUPling LFRej",
        "TRIGger:A:LEVel:CH1 0.5", "TRIGger:A:HOLDOff:TIMe 4e-08",
    ]


@pytest.mark.parametrize("model_id,_,__", MODELS)
def test_common_timebase_channel_trigger_and_directory_commands(model_id, _, __):
    scope, backend = make_scope(model_id)
    scope.set_timebase_scale(1e-3)
    scope.set_channel_display(1, True)
    scope.set_channel_scale(1, 0.2)
    scope.set_channel_coupling(1, "ac")
    scope.set_channel_invert(1, True)
    scope.configure_trigger_edge_source(source="analog-channel", source_channel=1)
    scope.configure_trigger_edge_slope(slope="positive")
    scope.configure_trigger_sweep("auto")
    scope.configure_save_pwd("C:/data")
    assert backend.history[1:] == [
        "HORizontal:MAIn:SCAle 0.001", "SELect:CH1 ON", "CH1:SCAle 0.2",
        "CH1:COUPling AC", "CH1:INVert ON",
        f"{scope._trigger_root}:EDGE:SOUrce CH1",
        f"{scope._trigger_root}:EDGE:SLOpe RISe",
        f"{scope._trigger_root}:MODe AUTO", 'FILESystem:CWD "C:/data"',
    ]


@pytest.mark.parametrize("model_id", ["tektronix-tds2024b", "tektronix-tbs1052b"])
def test_legacy_display_vectors_query_and_on(model_id):
    scope, backend = make_scope(
        model_id,
        {"DISPlay:STYle?": ":DISPLAY:STYLE DOTS"},
    )
    enabled, raw = scope.query_display_vectors()
    assert enabled is False
    assert raw == ":DISPLAY:STYLE DOTS"
    scope.set_display_vectors_on()
    assert backend.history[1:] == ["DISPlay:STYle?", "DISPlay:STYle VECtors"]


def test_b2_display_vectors_rejects_before_scpi():
    scope, backend = make_scope()
    with pytest.raises(ParameterValidationError):
        scope.query_display_vectors()
    with pytest.raises(ParameterValidationError):
        scope.set_display_vectors_on()
    assert backend.history == ["*IDN?"]


@pytest.mark.parametrize("model_id", ["tektronix-tds2024b", "tektronix-tbs1052b"])
def test_legacy_timebase_probe_reference_and_holdoff(model_id):
    scope, backend = make_scope(model_id)
    scope.set_timebase_position(0.25)
    scope.set_channel_probe_ratio(1, 20)
    scope.set_channel_bandwidth_limit(1, True)
    scope.set_trigger_holdoff(500e-9)
    scope.save_reference_waveform(2, 1)
    scope.configure_reference_display(2, False)
    assert backend.history[1:] == [
        "HORizontal:MAIn:POSition 0.25", "CH1:PRObe 20",
        "CH1:BANdwidth ON", "TRIGger:MAIn:HOLDOff:VALue 5e-07",
        "SAVe:WAVEform CH1,REFB", "*OPC?", "SELect:REFB OFF",
    ]


def test_b2_only_channel_limits_reject_before_scpi():
    scope, backend = make_scope()
    scope.set_channel_offset(1, 0.25)
    scope.set_channel_label(1, "x" * 30)
    history = list(backend.history)
    for action in (
        lambda: scope.set_channel_label(1, "x" * 31),
        lambda: scope.set_channel_label(1, "é"),
        lambda: scope.set_channel_probe_skew(1, 101e-9),
        lambda: scope.set_channel_coupling(1, "gnd"),
        lambda: scope.configure_trigger_mode("pulse-width"),
        lambda: scope.configure_save_pwd("C:/bad;path"),
    ):
        with pytest.raises(ParameterValidationError):
            action()
    assert backend.history == history


def test_standard_status_commands_and_optional_headers():
    scope, backend = make_scope(responses={"*OPC?": "*OPC 1", "*STB?": "*STB 4", "*ESR?": "*ESR 8"})
    scope.clear_status()
    assert scope.query_operation_complete().complete
    assert scope.query_status_byte().value == 4
    assert scope.query_standard_event_status().value == 8
    assert backend.history[1:] == ["*CLS", "*OPC?", "*STB?", "*ESR?"]


@pytest.mark.parametrize("model_id", ["tektronix-tds2024b", "tektronix-tbs1052b"])
def test_legacy_standalone_level_rejected_but_combined_edge_supported(model_id):
    scope, backend = make_scope(model_id)
    with pytest.raises(ParameterValidationError):
        scope.configure_trigger_edge_level(source_channel=1, level_volts=0.5)
    assert backend.history == ["*IDN?"]
    scope.configure_trigger_edge(1, 0.5, "negative")
    assert backend.history[1:] == [
        "TRIGger:MAIn:EDGE:SOUrce CH1", "TRIGger:MAIn:LEVel 0.5",
        "TRIGger:MAIn:EDGE:SLOpe FALL",
    ]


@pytest.mark.parametrize("value,fails", [(0, False), (128, False), (64, False), (2, False), (1, False), (32, True), (16, True), (8, True), (4, True)])
def test_post_command_esr_bits(value, fails):
    scope, backend = make_scope(responses={"*ESR?": str(value)})
    if fails:
        with pytest.raises(OscilloscopeError, match=f"raw SESR '{value}'"):
            scope.post_command_status()
    else:
        assert scope.post_command_status().value == value
    assert backend.history == ["*IDN?", "*ESR?"]


def test_explicit_status_does_not_read_hidden_esr():
    scope, backend = make_scope(responses={"*ESR?": "*ESR 8"})
    state = scope.query_standard_event_status()
    assert state.value == 8
    scope.post_command_status("system-standard-event")
    assert backend.history == ["*IDN?", "*ESR?"]


@pytest.mark.parametrize("model_id,command,response,method,args,expected", [
    ("tektronix-tbs2074b", "CH1:SCAle?", ":CH1:SCALE 0.2", "query_channel_scale", (1,), 0.2),
    ("tektronix-tbs2074b", "CH1:COUPling?", ":CH1:COUPLING DC", "query_channel_coupling", (1,), "dc"),
    ("tektronix-tbs2074b", "CH1:PRObe:GAIN?", ":CH1:PROBE:GAIN 0.1", "query_channel_probe_ratio", (1,), 10),
    ("tektronix-tbs2074b", "CH1:BANdwidth?", ":CH1:BANDWIDTH TWENTY", "query_channel_bandwidth_limit", (1,), True),
    ("tektronix-tbs2074b", "CH1:INVert?", ":CH1:INVERT ON", "query_channel_invert", (1,), True),
    ("tektronix-tbs2074b", "CH1:LABel?", ':CH1:LABEL "A"', "query_channel_label", (1,), "A"),
    ("tektronix-tbs2074b", "CH1:DESKew?", ":CH1:DESKEW 1e-8", "query_channel_probe_skew", (1,), 1e-8),
    ("tektronix-tds2024b", "HORizontal:MAIn:POSition?", ":HORIZONTAL:MAIN:POSITION 0.1", "query_timebase_position", (), 0.1),
    ("tektronix-tbs2074b", "HORizontal:MAIn:SCAle?", ":HORIZONTAL:SCALE 0.1", "query_timebase_scale", (), 0.1),
    ("tektronix-tbs2074b", "ACQuire:MODe?", ":ACQUIRE:MODE SAMPLE", "query_acquisition_type", (), "normal"),
    ("tektronix-tbs2074b", "ACQuire:NUMAVg?", ":ACQUIRE:NUMAVG 16", "query_acquisition_count", (), 16),
    ("tektronix-tbs2074b", "TRIGger:A:EDGE:SOUrce?", ":TRIGGER:A:EDGE:SOURCE CH1", "query_trigger_edge_source", (), "analog-channel"),
    ("tektronix-tds2024b", "TRIGger:MAIn:EDGE:SOUrce?", ":TRIGGER:EDGE:SOURCE CH1", "query_trigger_edge_source", (), "analog-channel"),
    ("tektronix-tbs2074b", "TRIGger:A:EDGE:SLOpe?", ":TRIGGER:A:EDGE:SLOPE RISE", "query_trigger_edge_slope", (), "positive"),
    ("tektronix-tbs2074b", "TRIGger:A:EDGE:COUPling?", ":TRIGGER:A:EDGE:COUPLING DC", "query_trigger_edge_coupling", (), "dc"),
    ("tektronix-tbs2074b", "TRIGger:A:LEVel:CH1?", ":TRIGGER:A:LEVEL:CH1 0.5", "query_trigger_edge_level", (), 0.5),
    ("tektronix-tbs2074b", "TRIGger:A:TYPe?", ":TRIGGER:A:TYPE EDGE", "query_trigger_mode", (), "edge"),
    ("tektronix-tbs2074b", "TRIGger:A:MODe?", ":TRIGGER:A:MODE NORMAL", "query_trigger_sweep", (), "normal"),
    ("tektronix-tbs2074b", "TRIGger:A:HOLDOff:TIMe?", ":TRIGGER:A:HOLDOFF:TIME 0.1", "query_trigger_holdoff", (), 0.1),
    ("tektronix-tbs2074b", "SELect:REF1?", ":SELECT:REF1 1", "query_reference_display", (1,), True),
    ("tektronix-tbs2074b", "FILESystem:CWD?", ':FILESYSTEM:CWD "C:/"', "query_save_pwd", (), "C:/"),
    ("tektronix-tds2024b", "DISPlay:STYle?", ":DISPLAY:STYLE VECTORS", "query_display_vectors", (), True),
    ("tektronix-tbs2074b", "*STB?", "*STB 4", "query_status_byte", (), 4),
])
def test_header_on_query_normalization(model_id, command, response, method, args, expected):
    scope, backend = make_scope(model_id, {command: response})
    if method == "query_trigger_edge_level":
        result = scope.query_trigger_edge_level(source_channel=1)
    else:
        result = getattr(scope, method)(*args)
    if method == "query_trigger_edge_source":
        result = result.source
    elif method == "query_trigger_edge_slope":
        result = result.slope
    elif method == "query_trigger_edge_coupling":
        result = result.coupling
    elif method == "query_trigger_edge_level":
        result = result.level_volts
    elif method == "query_trigger_mode" or method == "query_trigger_sweep":
        result = result.mode
    elif method == "query_reference_display":
        result = result[0]
    elif method == "query_save_pwd":
        result = result.path
    elif method == "query_display_vectors":
        result = result[0]
    elif method == "query_status_byte":
        result = result.value
    assert result == expected
    assert backend.history == ["*IDN?", command]


def test_phase2_high_risk_subsets_reject_before_scpi():
    scope, backend = make_scope(responses={"CH1:YUNit?": "V", "CH2:YUNit?": "A"})
    for channel, units in ((1, "volt"), (2, "amp")):
        scope.set_channel_units(channel, units)
        assert scope.query_channel_units(channel) == units
    for action in (
        lambda: scope.set_channel_units(3, "volt"), lambda: scope.query_channel_units(4),
        lambda: scope.configure_save_image_format("bmp8"), lambda: scope.configure_save_image_format("jpg"),
        lambda: scope.configure_save_waveform_format("binary"), lambda: scope.configure_save_waveform_format("ascii-xy"),
        lambda: scope.configure_runt_trigger(channel=3, polarity="positive", qualifier="none", low_level_volts=0, high_level_volts=1),
        lambda: scope.configure_runt_trigger(channel=1, polarity="either", qualifier="none", low_level_volts=0, high_level_volts=1),
        lambda: scope.configure_cursor(1, x1_seconds=0),
        lambda: scope.configure_math_operator(1, "add", "channel1", "channel3"),
        lambda: scope.configure_math_operator(1, "add", "channel1", "channel1"),
        lambda: scope.configure_math_operator(1, "divide", "channel1", "channel2"),
        lambda: scope.configure_math_display(2, True),
    ):
        before = list(backend.history)
        with pytest.raises(ParameterValidationError): action()
        assert backend.history == before


@pytest.mark.parametrize("model_id", ["tektronix-tds2024b", "tektronix-tbs1052b"])
def test_phase2_legacy_subsets(model_id):
    scope, backend = make_scope(model_id)
    for value in ("minimum", "infinite", 1, 2, 5):
        scope.set_display_persistence(value)
    for action in (
        *(lambda value=value: scope.set_display_persistence(value) for value in (0.1, 3, 60)),
        lambda: scope.configure_cursor(1, x1_seconds=0, y1_volts=0),
        lambda: scope.configure_cursor(1, y1_volts=0, auto_vertical=True),
        lambda: scope.configure_tv_trigger(source_channel=1, standard="secam", mode="field1", polarity="positive"),
        lambda: scope.configure_tv_trigger(source_channel=1, standard="ntsc", mode="line-field1", polarity="positive", line=1),
        lambda: scope.configure_save_image_format("bmp"),
    ):
        before = list(backend.history)
        with pytest.raises(ParameterValidationError): action()
        assert backend.history == before


@pytest.mark.parametrize("model_id,_,__", MODELS)
def test_phase2_measurement_results_and_png_stay_fail_closed(model_id, _, __):
    scope, backend = make_scope(model_id)
    for action in (scope.query_measurement_results, scope.capture_screenshot_png, scope.query_hardcopy_state,
                   lambda: scope.capture_screenshot(options=ScreenshotOptions()),
                   lambda: scope.capture_screenshot(options=ScreenshotOptions(format="png"))):
        with pytest.raises(ParameterValidationError): action()
    assert backend.history == ["*IDN?"]


@pytest.mark.parametrize("failure", [None, "signature", "transfer", "setup"])
def test_phase2_tds_bmp_restores_state_and_timeout(monkeypatch, failure):
    scope, backend = make_scope("tektronix-tds2024b", {
        "HARDCopy:FORMat?": "RLE", "HARDCopy:PORT?": "FILE",
        "HARDCopy:INKSaver?": "OFF", "HARDCopy:LAYout?": "PORTRAIT",
    })
    backend.timeout = 2345
    backend.raw_response = b"BMbitmap" if failure != "signature" else b"not a bitmap"
    def read():
        assert backend.timeout == 10000
        if failure == "transfer": raise OscilloscopeError("transfer failed")
        return backend.raw_response
    monkeypatch.setattr(backend, "read_raw", read)
    original_write = backend.write
    def write(command):
        original_write(command)
        if failure == "setup" and command == "HARDCopy:LAYout LANdscape":
            raise OscilloscopeError("setup failed")
    monkeypatch.setattr(backend, "write", write)
    options = ScreenshotOptions(format="bmp", ink_saver=True, layout="landscape")
    if failure:
        with pytest.raises(OscilloscopeError): scope.capture_screenshot(options=options)
    else:
        capture = scope.capture_screenshot(options=options)
        assert capture.format_name == "BMP" and capture.data.startswith(b"BM")
        assert capture.palette is None
    assert backend.timeout_history == [10000, 2345]
    assert backend.timeout == 2345
    assert backend.history[-4:] == ["HARDCopy:LAYout PORTRAIT", "HARDCopy:INKSaver OFF", "HARDCopy:PORT FILE", "HARDCopy:FORMat RLE"]


def test_phase2_save_uses_actual_readback_completion_and_restores_timeout():
    scope, backend = make_scope(responses={"SAVe:IMAge:FILEFormat?": "BMP", "SAVe:WAVEform:FILEFormat?": "SPREADSHEET"})
    scope.configure_save_image_format("png")
    assert scope.query_save_image_format().format == "bmp"
    scope.configure_save_waveform_format("csv")
    assert scope.query_save_waveform_format().format == "csv"
    backend.timeout = 3210
    result = scope.save_image("caller.bmp")
    assert result.command == 'SAVe:IMAge "caller.bmp"'
    assert result.operation == "save-image"
    assert backend.history[-2:] == ['SAVe:IMAge "caller.bmp"', "*OPC?"]
    assert backend.timeout_history == [15000, 3210]
    del backend.responses["*OPC?"]
    with pytest.raises(OscilloscopeError): scope.save_image("failed.bmp")
    assert backend.timeout == 3210


@pytest.mark.parametrize("model_id,_,__", MODELS)
def test_phase2_simulator_roundtrips_and_slot_safety(model_id, _, __):
    with simulated_scope(model_id) as scope:
        scope.set_channel_units(1, "amp")
        assert scope.query_channel_units(1) == "amp"
        scope.set_display_persistence(2)
        assert scope.query_display_persistence().seconds == 2
        scope.configure_math_operator(1, "subtract", "channel2", "channel1")
        assert scope.query_math_operator(1).source1 == "channel2"
        assert scope.query_math_operation(1).operation == "subtract"
        scope.configure_math_display(1, True)
        assert scope.query_math_display(1).enabled
        scope.install_measurement(1, "vpp")
        assert scope.backend.tek_measurements[1]["TYPE"] == "PK2Pk"
        start = len(scope.backend.history)
        scope.install_measurement(1, "vpp")
        assert all(command.endswith("?") for command in scope.backend.history[start:])
        for slot in scope.backend.tek_measurements.values():
            slot.update(TYPE="MEAN", SOURCE="CH2", SOURCE1="CH2", STATE="ON")
        start = len(scope.backend.history)
        with pytest.raises(ParameterValidationError, match="full"): scope.install_measurement(1, "vpp")
        assert all(command.endswith("?") for command in scope.backend.history[start:])
        scope.clear_measurements()
        scope.install_measurement(1, "vpp")
        if model_id == "tektronix-tbs2074b":
            scope.configure_runt_trigger(channel=2, polarity="negative", qualifier="less-than", time_seconds=1e-6, low_level_volts=-0.1, high_level_volts=0.1)
            state = scope.query_runt_trigger()
            assert (state.channel, state.polarity, state.qualifier) == (2, "negative", "less-than")
            scope.configure_save_image_format("bmp")
            assert scope.query_save_image_format().format == "bmp"
            scope.configure_save_waveform_format("csv")
            assert scope.query_save_waveform_format().format == "csv"
        else:
            state = scope.configure_tv_trigger(source_channel=2, standard="PAL", mode="all-fields", polarity="POSITIVE")
            assert (state.standard, state.tv_mode, state.polarity) == ("pal", "all-fields", "positive")
            scope.configure_save_image_ink_saver(True)
            assert scope.query_save_image_ink_saver().enabled
            scope.configure_cursor(1, x1_seconds=0, x2_seconds=0.001)
            cursor = scope.query_cursor()
            assert cursor.x2_seconds == 0.001 and cursor.y1_volts is None
        scope.save_image("simulated.bmp")


@pytest.mark.parametrize("model_id,_,__", MODELS)
def test_phase2_partial_aggregates_zero_unsupported_scpi(model_id, _, __):
    with simulated_scope(model_id) as scope:
        scope.backend.history.clear()
        channels = scope.query_channel_summary()
        readouts = query_acquisition_readouts(scope)
        snapshot = query_instrument_summary(scope)
        assert snapshot["acquisition"]["mode"] == "unknown"
        assert readouts["record_length"] == readouts["acquisition_points"]
        history = [command.upper() for command in scope.backend.history]
        assert not any(":RANGE?" in command or ":IMPEDANCE?" in command or ":VERNIER?" in command for command in history)
        assert "ACQUIRE:MODE?" not in history
        if model_id == "tektronix-tbs2074b":
            assert channels[2].units is None and channels[3].units is None
            assert "CH3:YUNIT?" not in history and "CH4:YUNIT?" not in history
            assert snapshot["timebase"]["position"] is None
            assert not any(command in history for command in ("HORIZONTAL:MAIN:POSITION?", "HORIZONTAL:DELAY:TIME?"))
            scope.backend.tek_settings["HORIZONTAL:DELAY:MODE"] = "ON"
            scope.backend.tek_settings["HORIZONTAL:DELAY:TIME"] = "0.25"
            assert query_instrument_summary(scope)["timebase"]["position"] == 0.25
        else:
            assert readouts["sample_rate"] is None
            assert not any("SAMPLERATE" in command for command in history)
            for channel in channels:
                assert all(getattr(channel, name) is None for name in ("offset", "label", "probe_skew", "range", "impedance", "vernier"))
            assert not any(":OFFSET?" in command or ":LABEL?" in command or ":DESKEW?" in command for command in history)
        scope.configure_trigger_mode("glitch")
        scope.backend.history.clear()
        assert query_instrument_summary(scope)["trigger"]["level"] is None
        assert not any(":EDGE:" in command or ":LEVel" in command for command in scope.backend.history)


@pytest.mark.parametrize("model_id,_,__", MODELS)
def test_phase2_cursor_projection_skips_inactive_and_non_voltage_axes(model_id, _, __):
    with simulated_scope(model_id) as scope:
        b2 = model_id == "tektronix-tbs2074b"
        scope.backend.tek_settings["CURSOR:FUNCTION"] = "TIME" if b2 else "VBARS"
        scope.backend.history.clear()
        state = scope.query_cursor()
        assert state.x1_seconds is not None and state.y1_volts is None
        assert not any("HBARS" in command.upper() for command in scope.backend.history)
        scope.backend.tek_settings["CURSOR:FUNCTION"] = "AMPLITUDE" if b2 else "HBARS"
        scope.set_channel_units(1, "amp")
        scope.backend.history.clear()
        state = scope.query_cursor()
        assert state.x1_seconds is None and state.y1_volts is None
        assert not any("POSITION" in command.upper() or "DELTA" in command.upper() or "VBARS" in command.upper()
                       for command in scope.backend.history)
        if not b2:
            with pytest.raises(ParameterValidationError, match="volt"):
                scope.configure_cursor(1, y1_volts=0)
            assert all(command.endswith("?") for command in scope.backend.history)


def test_phase2_measurement_item_subset_rejects_before_scpi():
    scope, backend = make_scope("tektronix-tds2024b")
    with pytest.raises(ParameterValidationError):
        scope.install_measurement(1, "vrms")
    assert backend.history == ["*IDN?"]
