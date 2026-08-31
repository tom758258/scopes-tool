from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.errors import ParameterValidationError


def test_scope_queries_idn_and_loads_capabilities():
    backend = FakeBackend(responses={"*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4034A,MY1,02.50"})
    scope = Oscilloscope(backend)

    idn = scope.query_idn()

    assert idn.model == "DSOX4034A"
    assert scope.capabilities is not None
    assert scope.capabilities.series == "4000X"
    assert backend.history == ["*IDN?"]


def test_scope_keeps_unknown_capabilities_none():
    backend = FakeBackend(responses={"*IDN?": "ACME,MODEL1,SN1,FW1"})
    scope = Oscilloscope(backend)

    idn = scope.query_idn()

    assert idn.model == "MODEL1"
    assert idn.series is None
    assert scope.capabilities is None


def test_scope_live_capabilities_require_manufacturer_and_model_identity():
    backend = FakeBackend(
        responses={"*IDN?": "ACME,DSOX4024A,SN1,FW1"}
    )
    scope = Oscilloscope(backend)

    idn = scope.query_idn()

    assert idn.model == "DSOX4024A"
    assert scope.capabilities is None


def test_scope_context_manager_closes_backend():
    backend = FakeBackend()

    with Oscilloscope(backend):
        pass

    assert backend.closed is True


def test_scope_queries_system_error():
    backend = FakeBackend(responses={":SYSTem:ERRor?": '-113,"Undefined header"'})
    scope = Oscilloscope(backend)

    entry = scope.query_system_error()

    assert entry.code == -113
    assert entry.message == "Undefined header"
    assert backend.history == [":SYSTem:ERRor?"]


def test_scope_system_status_methods_delegate_without_identity_query():
    backend = FakeBackend(
        responses={
            "*OPC?": "1",
            "*STB?": "0",
            "*ESR?": "0",
            ":OPERegister:CONDition?": "0",
            "*OPT?": "0",
        }
    )
    scope = Oscilloscope(backend)

    scope.clear_status()
    assert scope.query_operation_complete().complete is True
    assert scope.query_status_byte().value == 0
    assert scope.query_standard_event_status().value == 0
    assert scope.query_operation_status().value == 0
    assert scope.query_system_options().options == ("0",)
    assert backend.history == [
        "*CLS",
        "*OPC?",
        "*STB?",
        "*ESR?",
        ":OPERegister:CONDition?",
        "*OPT?",
    ]


def test_scope_control_methods_send_one_command_each():
    backend = FakeBackend()
    scope = Oscilloscope(backend)

    scope.stop()
    scope.run()
    scope.single()

    assert backend.history == [":STOP", ":RUN", ":SINGle"]


def test_scope_drains_system_errors_until_no_error():
    class SequencedBackend(FakeBackend):
        def __init__(self):
            super().__init__()
            self.sequence = [
                '-113,"Undefined header"',
                '-222,"Data out of range"',
                '+0,"No error"',
            ]

        def query(self, command: str) -> str:
            self._ensure_open()
            self.history.append(command)
            if command == ":SYSTem:ERRor?":
                return self.sequence.pop(0)
            return super().query(command)

    backend = SequencedBackend()
    scope = Oscilloscope(backend)

    entries = scope.drain_system_errors()

    assert [entry.code for entry in entries] == [-113, -222, 0]
    assert backend.history == [
        ":SYSTem:ERRor?",
        ":SYSTem:ERRor?",
        ":SYSTem:ERRor?",
    ]


def test_scope_rejects_invalid_error_drain_limit():
    scope = Oscilloscope(FakeBackend())

    try:
        scope.drain_system_errors(max_reads=0)
    except ValueError as exc:
        assert "max_reads" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_scope_channel_display_requires_known_capabilities():
    scope = Oscilloscope(FakeBackend())

    try:
        scope.set_channel_display(1, True)
    except ParameterValidationError as exc:
        assert "query_idn" in str(exc)
    else:
        raise AssertionError("Expected ParameterValidationError")


def test_scope_channel_display_uses_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":CHANnel4:DISPlay?": "0",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    scope.set_channel_display(4, True)
    display = scope.query_channel_display(4)

    assert display is False
    assert backend.history == ["*IDN?", ":CHANnel4:DISPlay ON", ":CHANnel4:DISPlay?"]


def test_scope_rejects_channel_above_capability_before_display_scpi():
    backend = FakeBackend(responses={"*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20"})
    scope = Oscilloscope(backend)

    scope.query_idn()
    try:
        scope.set_channel_display(5, True)
    except ParameterValidationError:
        pass
    else:
        raise AssertionError("Expected ParameterValidationError")

    assert backend.history == ["*IDN?"]


def test_scope_channel_scale_and_offset_use_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":CHANnel1:SCALe?": "5.0E-1",
            ":CHANnel1:OFFSet?": "-1.25E-1",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    scope.set_channel_scale(1, 0.5)
    scale = scope.query_channel_scale(1)
    scope.set_channel_offset(1, -0.125)
    offset = scope.query_channel_offset(1)

    assert scale == 0.5
    assert offset == -0.125
    assert backend.history == [
        "*IDN?",
        ":CHANnel1:SCALe 0.5",
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet -0.125",
        ":CHANnel1:OFFSet?",
    ]


def test_scope_channel_parameters_use_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":CHANnel1:COUPling?": "DC",
            ":CHANnel1:PROBe?": "1.0E+1",
            ":CHANnel1:BWLimit?": "0",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    scope.set_channel_coupling(1, "ac")
    coupling = scope.query_channel_coupling(1)
    scope.set_channel_probe_ratio(1, 10)
    ratio = scope.query_channel_probe_ratio(1)
    scope.set_channel_bandwidth_limit(1, True)
    bandwidth_limit = scope.query_channel_bandwidth_limit(1)

    assert coupling == "dc"
    assert ratio == 10
    assert bandwidth_limit is False
    assert backend.history == [
        "*IDN?",
        ":CHANnel1:COUPling AC",
        ":CHANnel1:COUPling?",
        ":CHANnel1:PROBe 10",
        ":CHANnel1:PROBe?",
        ":CHANnel1:BWLimit ON",
        ":CHANnel1:BWLimit?",
    ]


def test_scope_channel_advanced_settings_use_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":CHANnel1:IMPedance?": "ONEMeg",
            ":CHANnel1:INVert?": "1",
            ":CHANnel1:RANGe?": "4.0",
            ":CHANnel1:UNITs?": "VOLT",
            ":CHANnel1:VERNier?": "0",
            ":CHANnel1:PROBe:SKEW?": "1.0E-9",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    scope.set_channel_impedance(1, "one-meg")
    impedance = scope.query_channel_impedance(1)
    scope.set_channel_invert(1, True)
    invert = scope.query_channel_invert(1)
    scope.set_channel_range(1, 4)
    channel_range = scope.query_channel_range(1)
    scope.set_channel_units(1, "volt")
    units = scope.query_channel_units(1)
    scope.set_channel_vernier(1, False)
    vernier = scope.query_channel_vernier(1)
    scope.set_channel_probe_skew(1, 1e-9)
    skew = scope.query_channel_probe_skew(1)

    assert impedance == "one_meg"
    assert invert is True
    assert channel_range == 4.0
    assert units == "volt"
    assert vernier is False
    assert skew == 1e-9
    assert backend.history == [
        "*IDN?",
        ":CHANnel1:IMPedance ONEMeg",
        ":CHANnel1:IMPedance?",
        ":CHANnel1:INVert ON",
        ":CHANnel1:INVert?",
        ":CHANnel1:RANGe 4",
        ":CHANnel1:RANGe?",
        ":CHANnel1:UNITs VOLT",
        ":CHANnel1:UNITs?",
        ":CHANnel1:VERNier OFF",
        ":CHANnel1:VERNier?",
        ":CHANnel1:PROBe:SKEW 1e-09",
        ":CHANnel1:PROBe:SKEW?",
    ]


def test_scope_rejects_channel_above_capability_before_scale_scpi():
    backend = FakeBackend(responses={"*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20"})
    scope = Oscilloscope(backend)

    scope.query_idn()
    try:
        scope.set_channel_scale(5, 0.5)
    except ParameterValidationError:
        pass
    else:
        raise AssertionError("Expected ParameterValidationError")

    assert backend.history == ["*IDN?"]


def test_scope_timebase_requires_known_capabilities():
    scope = Oscilloscope(FakeBackend())

    try:
        scope.set_timebase_scale(0.001)
    except ParameterValidationError as exc:
        assert "query_idn" in str(exc)
    else:
        raise AssertionError("Expected ParameterValidationError")


def test_scope_timebase_controls_use_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":TIMebase:SCALe?": "1.0E-3",
            ":TIMebase:POSition?": "-5.0E-4",
            ":TIMebase:REFerence?": "RIGH",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    scope.set_timebase_scale(0.001)
    scale = scope.query_timebase_scale()
    scope.set_timebase_position(-0.0005)
    position = scope.query_timebase_position()
    scope.set_timebase_reference("right")
    reference = scope.query_timebase_reference()

    assert scale == 0.001
    assert position == -0.0005
    assert reference == "right"
    assert backend.history == [
        "*IDN?",
        ":TIMebase:SCALe 0.001",
        ":TIMebase:SCALe?",
        ":TIMebase:POSition -0.0005",
        ":TIMebase:POSition?",
        ":TIMebase:REFerence RIGHt",
        ":TIMebase:REFerence?",
    ]


def test_scope_edge_trigger_requires_known_capabilities():
    scope = Oscilloscope(FakeBackend())

    try:
        scope.configure_trigger_edge(source_channel=1, level_volts=0.0, slope="positive")
    except ParameterValidationError as exc:
        assert "query_idn" in str(exc)
    else:
        raise AssertionError("Expected ParameterValidationError")


def test_scope_edge_trigger_uses_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":TRIGger:EDGE:SOURce?": "CHAN1",
            ":TRIGger:EDGE:LEVel?": "2.5E-1",
            ":TRIGger:EDGE:SLOPe?": "POS",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    scope.configure_trigger_edge(source_channel=1, level_volts=0.25, slope="positive")
    state = scope.query_trigger_edge()

    assert state.source_channel == 1
    assert state.level_volts == 0.25
    assert state.slope == "positive"
    assert backend.history == [
        "*IDN?",
        ":TRIGger:MODE EDGE",
        ":TRIGger:EDGE:SOURce CHANnel1",
        ":TRIGger:EDGE:LEVel 0.25",
        ":TRIGger:EDGE:SLOPe POSitive",
        ":TRIGger:EDGE:SOURce?",
        ":TRIGger:EDGE:LEVel?",
        ":TRIGger:EDGE:SLOPe?",
    ]


def test_scope_edge_trigger_old_methods_are_removed():
    scope = Oscilloscope(FakeBackend())

    assert not hasattr(scope, "configure_edge_trigger")
    assert not hasattr(scope, "query_edge_trigger")


def test_scope_runt_trigger_uses_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":TRIGger:MODE?": "RUNT",
            ":TRIGger:RUNT:SOURce?": "CHAN1",
            ":TRIGger:RUNT:POLarity?": "EITH",
            ":TRIGger:RUNT:QUALifier?": "NONE",
            ":TRIGger:RUNT:TIME?": "1.0E-6",
            ":TRIGger:LEVel:LOW? CHANnel1": "-5.0E-1",
            ":TRIGger:LEVel:HIGH? CHANnel1": "5.0E-1",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    scope.configure_runt_trigger(
        channel=1,
        polarity="either",
        qualifier="none",
        low_level_volts=-0.5,
        high_level_volts=0.5,
    )
    state = scope.query_runt_trigger()

    assert state.mode == "runt"
    assert state.channel == 1
    assert state.low_level_volts == -0.5
    assert state.high_level_volts == 0.5
    assert backend.history == [
        "*IDN?",
        ":TRIGger:MODE RUNT",
        ":TRIGger:RUNT:SOURce CHANnel1",
        ":TRIGger:LEVel:LOW -0.5,CHANnel1",
        ":TRIGger:LEVel:HIGH 0.5,CHANnel1",
        ":TRIGger:RUNT:POLarity EITHer",
        ":TRIGger:RUNT:QUALifier NONE",
        ":TRIGger:MODE?",
        ":TRIGger:RUNT:SOURce?",
        ":TRIGger:RUNT:POLarity?",
        ":TRIGger:RUNT:QUALifier?",
        ":TRIGger:RUNT:TIME?",
        ":TRIGger:LEVel:LOW? CHANnel1",
        ":TRIGger:LEVel:HIGH? CHANnel1",
    ]


def test_scope_transition_trigger_uses_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":TRIGger:MODE?": "TRAN",
            ":TRIGger:TRANsition:SOURce?": "CHAN1",
            ":TRIGger:TRANsition:SLOPe?": "NEG",
            ":TRIGger:TRANsition:QUALifier?": "LESS",
            ":TRIGger:TRANsition:TIME?": "2.0E-6",
            ":TRIGger:LEVel:LOW? CHANnel1": "-2.5E-1",
            ":TRIGger:LEVel:HIGH? CHANnel1": "7.5E-1",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    scope.configure_transition_trigger(
        channel=1,
        slope="negative",
        qualifier="less-than",
        time_seconds=2e-6,
        low_level_volts=-0.25,
        high_level_volts=0.75,
    )
    state = scope.query_transition_trigger()

    assert state.mode == "transition"
    assert state.channel == 1
    assert state.slope == "negative"
    assert state.qualifier == "less-than"
    assert state.low_level_volts == -0.25
    assert state.high_level_volts == 0.75
    assert backend.history == [
        "*IDN?",
        ":TRIGger:MODE TRANsition",
        ":TRIGger:TRANsition:SOURce CHANnel1",
        ":TRIGger:LEVel:LOW -0.25,CHANnel1",
        ":TRIGger:LEVel:HIGH 0.75,CHANnel1",
        ":TRIGger:TRANsition:SLOPe NEGative",
        ":TRIGger:TRANsition:TIME 2e-06",
        ":TRIGger:TRANsition:QUALifier LESSthan",
        ":TRIGger:MODE?",
        ":TRIGger:TRANsition:SOURce?",
        ":TRIGger:TRANsition:SLOPe?",
        ":TRIGger:TRANsition:QUALifier?",
        ":TRIGger:TRANsition:TIME?",
        ":TRIGger:LEVel:LOW? CHANnel1",
        ":TRIGger:LEVel:HIGH? CHANnel1",
    ]


def test_scope_pattern_trigger_uses_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":TRIGger:MODE?": "PATT",
            ":TRIGger:PATTern:FORMat?": "ASC",
            ":TRIGger:PATTern?": '"XXX1",NONE,POS',
            ":TRIGger:PATTern:QUALifier?": "ENT",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    configured = scope.configure_pattern_trigger("xxx1")
    state = scope.query_pattern_trigger()

    assert configured.pattern == "XXX1"
    assert state.mode == "pattern"
    assert state.format == "ascii"
    assert state.pattern == "XXX1"
    assert state.qualifier == "entered"
    assert state.edge_source_raw == "NONE"
    assert state.edge_raw == "POS"
    assert backend.history == [
        "*IDN?",
        ":TRIGger:MODE PATTern",
        ":TRIGger:PATTern:FORMat ASCii",
        ':TRIGger:PATTern "XXX1"',
        ":TRIGger:PATTern:QUALifier ENTered",
        ":TRIGger:MODE?",
        ":TRIGger:PATTern:FORMat?",
        ":TRIGger:PATTern?",
        ":TRIGger:PATTern:QUALifier?",
    ]


def test_scope_waveform_requires_known_capabilities():
    scope = Oscilloscope(FakeBackend())

    try:
        scope.capture_waveform_byte(1, points=1000)
    except ParameterValidationError as exc:
        assert "query_idn" in str(exc)
    else:
        raise AssertionError("Expected ParameterValidationError")


def test_scope_measurement_requires_known_capabilities():
    scope = Oscilloscope(FakeBackend())

    try:
        scope.query_measurement(1, "vpp")
    except ParameterValidationError as exc:
        assert "query_idn" in str(exc)
    else:
        raise AssertionError("Expected ParameterValidationError")


def test_scope_screenshot_requires_known_capabilities():
    scope = Oscilloscope(FakeBackend())

    try:
        scope.capture_screenshot_png()
    except ParameterValidationError as exc:
        assert "query_idn" in str(exc)
    else:
        raise AssertionError("Expected ParameterValidationError")


def test_scope_measurement_uses_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":MEASure:VPP? CHANnel1": "5.0E-1",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    result = scope.query_measurement(1, "vpp")

    assert result.valid is True
    assert result.value == 0.5
    assert backend.history == ["*IDN?", ":MEASure:VPP? CHANnel1"]


def test_scope_parameterized_measurement_uses_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":MEASure:VTIMe? 0,CHANnel1": "2.5E-1",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    result = scope.query_measurement(1, "y_at_x", time_s=0.0)

    assert result.valid is True
    assert result.value == 0.25
    assert backend.history == ["*IDN?", ":MEASure:VTIMe? 0,CHANnel1"]


def test_scope_pair_measurement_uses_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":MEASure:PHASe? CHANnel1,CHANnel2": "9.0E+1",
        }
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    result = scope.query_pair_measurement(1, 2, "phase")

    assert result.valid is True
    assert result.value == 90.0
    assert result.reference_channel == 2
    assert backend.history == ["*IDN?", ":MEASure:PHASe? CHANnel1,CHANnel2"]


def test_scope_rejects_delay_pair_on_non_4000x_before_scpi():
    backend = FakeBackend(
        responses={"*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX3024A,MY1,07.20"}
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    try:
        scope.query_pair_measurement(1, 2, "delay")
    except ParameterValidationError:
        pass
    else:
        raise AssertionError("Expected ParameterValidationError")

    assert backend.history == ["*IDN?"]


def test_scope_waveform_capture_uses_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":CHANnel1:UNITs?": "VOLT",
            ":WAVeform:PREamble?": "0,0,2,1,1.0E-6,0,0,2.0E-2,-2.56,128",
        },
        binary_responses={":WAVeform:DATA?": [128, 129]},
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    capture = scope.capture_waveform_byte(1, points=1000)

    assert capture.raw_samples == (128, 129)
    assert capture.vertical_unit == "V"
    assert backend.history == [
        "*IDN?",
        ":WAVeform:SOURce CHANnel1",
        ":CHANnel1:UNITs?",
        ":WAVeform:FORMat BYTE",
        ":WAVeform:POINts 1000",
        ":WAVeform:PREamble?",
        ":WAVeform:DATA?",
    ]


def test_scope_word_waveform_capture_uses_capabilities_from_idn():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":CHANnel1:UNITs?": "VOLT",
            ":WAVeform:PREamble?": "1,0,2,1,1.0E-6,0,0,1.0E-4,0,32768",
        },
        binary_responses={":WAVeform:DATA?": [32768, 32769]},
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    capture = scope.capture_waveform_word(1, points=1000)

    assert capture.raw_samples == (32768, 32769)
    assert capture.format_name == "WORD"
    assert capture.vertical_unit == "V"
    assert backend.history == [
        "*IDN?",
        ":WAVeform:SOURce CHANnel1",
        ":CHANnel1:UNITs?",
        ":WAVeform:FORMat WORD",
        ":WAVeform:BYTeorder MSBFirst",
        ":WAVeform:UNSigned ON",
        ":WAVeform:POINts 1000",
        ":WAVeform:PREamble?",
        ":WAVeform:DATA?",
    ]


def test_scope_screenshot_uses_capabilities_from_idn():
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY1,07.20",
            ":HARDcopy:INKSaver?": "1",
        },
        binary_responses={":DISPlay:DATA? PNG, COLor": list(png_bytes)},
        timeout=2000,
    )
    scope = Oscilloscope(backend)

    scope.query_idn()
    capture = scope.capture_screenshot_png()

    assert capture.data == png_bytes
    assert capture.background == "black"
    assert backend.history == [
        "*IDN?",
        ":HARDcopy:INKSaver?",
        ":HARDcopy:INKSaver OFF",
        ":DISPlay:DATA? PNG, COLor",
        ":HARDcopy:INKSaver ON",
    ]
    assert backend.timeout_history == [10000, 2000]
    assert backend.timeout == 2000
