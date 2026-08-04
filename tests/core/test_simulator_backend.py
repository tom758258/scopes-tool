import pytest

from scopes_tool_core.errors import OscilloscopeError, UnsupportedModelError
from scopes_tool_core.simulator_backend import (
    SimulatedSignal,
    SimulatorBackend,
    SimulatorBackendError,
)
from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.trigger import (
    OPERATION_CONDITION_RUI_ENAB_MASK,
    OPERATION_CONDITION_RUN_MASK,
)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_dimensions(data):
    assert data.startswith(PNG_SIGNATURE)
    assert data[12:16] == b"IHDR"
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def test_simulator_system_error_queue_drains_to_no_error():
    backend = SimulatorBackend(
        system_errors=['-113,"Undefined header"', '-222,"Data out of range"']
    )

    assert backend.query(":SYSTem:ERRor?") == '-113,"Undefined header"'
    assert backend.query(":SYSTem:ERRor?") == '-222,"Data out of range"'
    assert backend.query(":SYSTem:ERRor?") == '+0,"No error"'
    assert backend.history == [
        ":SYSTem:ERRor?",
        ":SYSTem:ERRor?",
        ":SYSTem:ERRor?",
    ]


def test_simulator_rejects_unknown_scpi_in_strict_mode():
    backend = SimulatorBackend()

    with pytest.raises(SimulatorBackendError, match="Unsupported simulator query"):
        backend.query(":FOO:BAR?")

    with pytest.raises(SimulatorBackendError, match="Unsupported simulator write"):
        backend.write(":FOO:BAR 1")

    with pytest.raises(SimulatorBackendError, match="Unsupported simulator binary query"):
        backend.query_binary_values(":FOO:DATA?")


def test_simulator_allows_supported_control_and_word_waveform_commands():
    backend = SimulatorBackend()

    backend.write(":RUN")
    backend.write(":STOP")
    backend.write(":SINGle")
    backend.write(":WAVeform:SOURce CHANnel2")
    backend.write(":WAVeform:FORMat WORD")
    backend.write(":WAVeform:BYTeorder MSBFirst")
    backend.write(":WAVeform:UNSigned ON")
    backend.write(":WAVeform:POINts 1000")

    assert backend.run_state == "single"
    assert backend.waveform_source == 2
    assert backend.waveform_format == "WORD"
    assert backend.waveform_byte_order == "MSBFirst"
    assert backend.waveform_unsigned is True
    assert backend.query(":WAVeform:PREamble?").startswith("1,0,1000,")
    assert len(backend.query_binary_values(":WAVeform:DATA?", datatype="H")) == 1000


def test_simulator_default_operation_condition_sequence_preserves_remote_readiness():
    backend = SimulatorBackend()

    backend.write(":SINGle")

    assert backend.query(":OPERegister:CONDition?") == str(
        OPERATION_CONDITION_RUN_MASK | OPERATION_CONDITION_RUI_ENAB_MASK
    )
    assert backend.query(":OPERegister:CONDition?") == str(
        OPERATION_CONDITION_RUI_ENAB_MASK
    )
    assert backend.run_state == "stopped"


def test_simulator_state_queries_reflect_channel_timebase_and_trigger_writes():
    backend = SimulatorBackend()

    backend.write(":CHANnel1:SCALe 0.5")
    backend.write(":CHANnel1:OFFSet 0.25")
    backend.write(":CHANnel1:COUPling AC")
    backend.write(":CHANnel1:PROBe 10")
    backend.write(":CHANnel1:BWLimit ON")
    backend.write(":TIMebase:SCALe 0.002")
    backend.write(":TIMebase:POSition 0.001")
    backend.write(":TRIGger:MODE EDGE")
    backend.write(":TRIGger:EDGE:SOURce CHANnel2")
    backend.write(":TRIGger:EDGE:LEVel 0.15")
    backend.write(":TRIGger:EDGE:SLOPe NEGative")

    assert backend.query(":CHANnel1:SCALe?") == "0.5"
    assert backend.query(":CHANnel1:OFFSet?") == "0.25"
    assert backend.query(":CHANnel1:COUPling?") == "AC"
    assert backend.query(":CHANnel1:PROBe?") == "10"
    assert backend.query(":CHANnel1:BWLimit?") == "1"
    assert backend.query(":TIMebase:SCALe?") == "0.002"
    assert backend.query(":TIMebase:POSition?") == "0.001"
    assert backend.query(":TRIGger:EDGE:SOURce?") == "CHANnel2"
    assert backend.query(":TRIGger:EDGE:LEVel?") == "0.15"
    assert backend.query(":TRIGger:EDGE:SLOPe?") == "NEG"


def test_simulator_trigger_common_roundtrip():
    backend = SimulatorBackend()

    backend.write(":TRIGger:SWEep AUTO")
    assert backend.query(":TRIGger:SWEep?") == "AUTO"

    backend.write(":TRIGger:SWEep NORMal")
    assert backend.query(":TRIGger:SWEep?") == "NORM"

    backend.write(":TRIGger:NREJect ON")
    assert backend.query(":TRIGger:NREJect?") == "1"
    backend.write(":TRIGger:NREJect OFF")
    assert backend.query(":TRIGger:NREJect?") == "0"

    backend.write(":TRIGger:HFReject ON")
    assert backend.query(":TRIGger:HFReject?") == "1"
    backend.write(":TRIGger:HFReject OFF")
    assert backend.query(":TRIGger:HFReject?") == "0"


@pytest.mark.parametrize(
    "command",
    [
        ":TRIGger:SWEep SINGle",
        ":TRIGger:NREJect TRUE",
        ":TRIGger:HFReject TRUE",
    ],
)
def test_simulator_trigger_common_rejects_invalid_writes(command):
    backend = SimulatorBackend()

    with pytest.raises(SimulatorBackendError):
        backend.write(command)


def test_simulator_glitch_less_than_roundtrip():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE GLITch")
    backend.write(":TRIGger:GLITch:SOURce CHANnel1")
    backend.write(":TRIGger:GLITch:POLarity POSitive")
    backend.write(":TRIGger:GLITch:LESSthan 1e-6")
    backend.write(":TRIGger:GLITch:QUALifier LESSthan")

    assert backend.query(":TRIGger:MODE?") == "GLIT"
    assert backend.query(":TRIGger:GLITch:SOURce?") == "CHAN1"
    assert backend.query(":TRIGger:GLITch:POLarity?") == "POS"
    assert backend.query(":TRIGger:GLITch:LESSthan?") == "1.00000000E-06"
    assert backend.query(":TRIGger:GLITch:QUALifier?") == "LESS"


def test_simulator_pattern_trigger_roundtrip():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE PATTern")
    backend.write(":TRIGger:PATTern:FORMat ASCii")
    backend.write(':TRIGger:PATTern "XXX1"')
    backend.write(":TRIGger:PATTern:QUALifier ENTered")

    assert backend.query(":TRIGger:MODE?") == "PATT"
    assert backend.query(":TRIGger:PATTern:FORMat?") == "ASC"
    assert backend.query(":TRIGger:PATTern?") == '"XXX1",NONE,POS'
    assert backend.query(":TRIGger:PATTern:QUALifier?") == "ENT"


def test_simulator_or_trigger_roundtrip():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE OR")
    backend.write(':TRIGger:OR "XXXR"')

    assert backend.query(":TRIGger:MODE?") == "OR"
    assert backend.query(":TRIGger:OR?") == '"XXXR"'


def test_simulator_or_trigger_accepts_unquoted_write():
    backend = SimulatorBackend()

    backend.write(":TRIGger:OR XXFR")

    assert backend.query(":TRIGger:OR?") == '"XXFR"'


@pytest.mark.parametrize(
    "standard, readback",
    [
        ("NTSC", "NTSC"),
        ("PAL", "PAL"),
        ("PALM", "PALM"),
        ("SECam", "SEC"),
    ],
)
def test_simulator_tv_standard_roundtrip(standard, readback):
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE TV")
    backend.write(":TRIGger:TV:SOURce CHANnel2")
    backend.write(f":TRIGger:TV:STANdard {standard}")
    backend.write(":TRIGger:TV:MODE LFIeld1")
    backend.write(":TRIGger:TV:LINE 20")
    backend.write(":TRIGger:TV:POLarity NEGative")

    assert backend.query(":TRIGger:MODE?") == "TV"
    assert backend.query(":TRIGger:TV:SOURce?") == "CHAN2"
    assert backend.query(":TRIGger:TV:STANdard?") == readback
    assert backend.query(":TRIGger:TV:MODE?") == "LFI1"
    assert backend.query(":TRIGger:TV:LINE?") == "20"
    assert backend.query(":TRIGger:TV:POLarity?") == "NEG"


@pytest.mark.parametrize(
    "mode, readback",
    [
        ("FIEld1", "FIE1"),
        ("FIEld2", "FIE2"),
        ("AFIelds", "AFI"),
        ("ALINes", "ALIN"),
        ("LFIeld1", "LFI1"),
        ("LFIeld2", "LFI2"),
        ("LALTernate", "LALT"),
    ],
)
def test_simulator_tv_mode_short_readbacks(mode, readback):
    backend = SimulatorBackend()

    backend.write(f":TRIGger:TV:MODE {mode}")

    assert backend.query(":TRIGger:TV:MODE?") == readback


@pytest.mark.parametrize(
    "command",
    [
        ":TRIGger:TV:SOURce DIGital0",
        ":TRIGger:TV:STANdard GEN",
        ":TRIGger:TV:MODE LINE",
        ":TRIGger:TV:LINE 0",
        ":TRIGger:TV:POLarity EITHer",
    ],
)
def test_simulator_tv_rejects_invalid_writes(command):
    backend = SimulatorBackend()

    with pytest.raises(SimulatorBackendError):
        backend.write(command)


def test_simulator_glitch_greater_than_with_level_roundtrip():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE GLITch")
    backend.write(":TRIGger:GLITch:SOURce CHANnel1")
    backend.write(":TRIGger:GLITch:LEVel 0.5,CHANnel1")
    backend.write(":TRIGger:GLITch:POLarity NEGative")
    backend.write(":TRIGger:GLITch:GREaterthan 5e-6")
    backend.write(":TRIGger:GLITch:QUALifier GREaterthan")

    assert backend.query(":TRIGger:GLITch:LEVel?") == "5.00000000E-01"
    assert backend.query(":TRIGger:GLITch:POLarity?") == "NEG"
    assert backend.query(":TRIGger:GLITch:GREaterthan?") == "5.00000000E-06"
    assert backend.query(":TRIGger:GLITch:QUALifier?") == "GRE"


def test_simulator_glitch_range_query_returns_canonical_max_min():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE GLITch")
    backend.write(":TRIGger:GLITch:SOURce CHANnel1")
    backend.write(":TRIGger:GLITch:POLarity POSitive")
    backend.write(":TRIGger:GLITch:RANGe 1e-5,1e-6")
    backend.write(":TRIGger:GLITch:QUALifier RANGe")

    assert backend.query(":TRIGger:GLITch:RANGe?") == "1.00000000E-05,1.00000000E-06"
    assert backend.query(":TRIGger:GLITch:QUALifier?") == "RANG"


def test_simulator_glitch_level_none_query_is_explicit():
    backend = SimulatorBackend(glitch_level=None)

    assert backend.query(":TRIGger:GLITch:LEVel?") == "NONE"


def test_simulator_runt_none_roundtrip():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE RUNT")
    backend.write(":TRIGger:RUNT:SOURce CHANnel1")
    backend.write(":TRIGger:LEVel:LOW -0.5,CHANnel1")
    backend.write(":TRIGger:LEVel:HIGH 0.5,CHANnel1")
    backend.write(":TRIGger:RUNT:POLarity EITHer")
    backend.write(":TRIGger:RUNT:QUALifier NONE")

    assert backend.query(":TRIGger:MODE?") == "RUNT"
    assert backend.query(":TRIGger:RUNT:SOURce?") == "CHAN1"
    assert backend.query(":TRIGger:LEVel:LOW? CHANnel1") == "-5.00000000E-01"
    assert backend.query(":TRIGger:LEVel:HIGH? CHANnel1") == "5.00000000E-01"
    assert backend.query(":TRIGger:RUNT:POLarity?") == "EITH"
    assert backend.query(":TRIGger:RUNT:QUALifier?") == "NONE"


def test_simulator_runt_greater_than_roundtrip():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE RUNT")
    backend.write(":TRIGger:RUNT:SOURce CHANnel1")
    backend.write(":TRIGger:LEVel:LOW -0.25,CHANnel1")
    backend.write(":TRIGger:LEVel:HIGH 0.75,CHANnel1")
    backend.write(":TRIGger:RUNT:POLarity POSitive")
    backend.write(":TRIGger:RUNT:TIME 5e-6")
    backend.write(":TRIGger:RUNT:QUALifier GREaterthan")

    assert backend.query(":TRIGger:RUNT:TIME?") == "5.00000000E-06"
    assert backend.query(":TRIGger:RUNT:POLarity?") == "POS"
    assert backend.query(":TRIGger:RUNT:QUALifier?") == "GRE"


def test_simulator_runt_less_than_roundtrip():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE RUNT")
    backend.write(":TRIGger:RUNT:SOURce CHANnel1")
    backend.write(":TRIGger:LEVel:LOW -0.25,CHANnel1")
    backend.write(":TRIGger:LEVel:HIGH 0.75,CHANnel1")
    backend.write(":TRIGger:RUNT:POLarity NEGative")
    backend.write(":TRIGger:RUNT:TIME 2e-6")
    backend.write(":TRIGger:RUNT:QUALifier LESSthan")

    assert backend.query(":TRIGger:RUNT:TIME?") == "2.00000000E-06"
    assert backend.query(":TRIGger:RUNT:POLarity?") == "NEG"
    assert backend.query(":TRIGger:RUNT:QUALifier?") == "LESS"


def test_simulator_transition_greater_than_roundtrip():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE TRANsition")
    backend.write(":TRIGger:TRANsition:SOURce CHANnel1")
    backend.write(":TRIGger:LEVel:LOW -0.5,CHANnel1")
    backend.write(":TRIGger:LEVel:HIGH 0.5,CHANnel1")
    backend.write(":TRIGger:TRANsition:SLOPe POSitive")
    backend.write(":TRIGger:TRANsition:TIME 5e-6")
    backend.write(":TRIGger:TRANsition:QUALifier GREaterthan")

    assert backend.query(":TRIGger:MODE?") == "TRAN"
    assert backend.query(":TRIGger:TRANsition:SOURce?") == "CHAN1"
    assert backend.query(":TRIGger:LEVel:LOW? CHANnel1") == "-5.00000000E-01"
    assert backend.query(":TRIGger:LEVel:HIGH? CHANnel1") == "5.00000000E-01"
    assert backend.query(":TRIGger:TRANsition:SLOPe?") == "POS"
    assert backend.query(":TRIGger:TRANsition:TIME?") == "5.00000000E-06"
    assert backend.query(":TRIGger:TRANsition:QUALifier?") == "GRE"


def test_simulator_transition_less_than_roundtrip():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE TRANsition")
    backend.write(":TRIGger:TRANsition:SOURce CHANnel1")
    backend.write(":TRIGger:LEVel:LOW -0.25,CHANnel1")
    backend.write(":TRIGger:LEVel:HIGH 0.75,CHANnel1")
    backend.write(":TRIGger:TRANsition:SLOPe NEGative")
    backend.write(":TRIGger:TRANsition:TIME 2e-6")
    backend.write(":TRIGger:TRANsition:QUALifier LESSthan")

    assert backend.query(":TRIGger:TRANsition:SLOPe?") == "NEG"
    assert backend.query(":TRIGger:TRANsition:TIME?") == "2.00000000E-06"
    assert backend.query(":TRIGger:TRANsition:QUALifier?") == "LESS"
    assert backend.query(":TRIGger:LEVel:LOW? CHANnel1") == "-2.50000000E-01"
    assert backend.query(":TRIGger:LEVel:HIGH? CHANnel1") == "7.50000000E-01"


def test_simulator_delay_trigger_roundtrip():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE DELay")
    backend.write(":TRIGger:DELay:ARM:SOURce CHANnel1")
    backend.write(":TRIGger:DELay:ARM:SLOPe POSitive")
    backend.write(":TRIGger:DELay:TDELay:TIME 1e-6")
    backend.write(":TRIGger:DELay:TRIGger:COUNt 2")
    backend.write(":TRIGger:DELay:TRIGger:SOURce CHANnel2")
    backend.write(":TRIGger:DELay:TRIGger:SLOPe NEGative")

    assert backend.query(":TRIGger:MODE?") == "DEL"
    assert backend.query(":TRIGger:DELay:ARM:SOURce?") == "CHAN1"
    assert backend.query(":TRIGger:DELay:ARM:SLOPe?") == "POS"
    assert backend.query(":TRIGger:DELay:TDELay:TIME?") == "1.00000000E-06"
    assert backend.query(":TRIGger:DELay:TRIGger:COUNt?") == "2"
    assert backend.query(":TRIGger:DELay:TRIGger:SOURce?") == "CHAN2"
    assert backend.query(":TRIGger:DELay:TRIGger:SLOPe?") == "NEG"


def test_simulator_edge_burst_trigger_roundtrip_with_level():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE EBURst")
    backend.write(":TRIGger:EBURst:SOURce CHANnel1")
    backend.write(":TRIGger:EBURst:SLOPe POSitive")
    backend.write(":TRIGger:EBURst:COUNt 3")
    backend.write(":TRIGger:EBURst:IDLE 1e-6")
    backend.write(":TRIGger:EDGE:LEVel 0.5, CHANnel1")

    assert backend.query(":TRIGger:MODE?") == "EBUR"
    assert backend.query(":TRIGger:EBURst:SOURce?") == "CHAN1"
    assert backend.query(":TRIGger:EBURst:SLOPe?") == "POS"
    assert backend.query(":TRIGger:EBURst:COUNt?") == "3"
    assert backend.query(":TRIGger:EBURst:IDLE?") == "1.00000000E-06"
    assert backend.query(":TRIGger:EDGE:LEVel? CHANnel1") == "0.5"


def test_simulator_edge_burst_trigger_roundtrip_without_level():
    backend = SimulatorBackend()

    backend.write(":TRIGger:MODE EBURst")
    backend.write(":TRIGger:EBURst:SOURce CHANnel2")
    backend.write(":TRIGger:EBURst:SLOPe NEGative")
    backend.write(":TRIGger:EBURst:COUNt 5")
    backend.write(":TRIGger:EBURst:IDLE 1e-5")

    assert backend.query(":TRIGger:EBURst:SOURce?") == "CHAN2"
    assert backend.query(":TRIGger:EBURst:SLOPe?") == "NEG"
    assert backend.query(":TRIGger:EBURst:COUNt?") == "5"
    assert backend.query(":TRIGger:EBURst:IDLE?") == "1.00000000E-05"
    assert backend.query(":TRIGger:EDGE:LEVel? CHANnel2") == "0"


def test_simulator_channel_advanced_settings_round_trip():
    backend = SimulatorBackend()

    backend.write(":CHANnel1:IMPedance FIFTy")
    backend.write(":CHANnel1:INVert ON")
    backend.write(":CHANnel1:RANGe 4")
    backend.write(":CHANnel1:UNITs AMP")
    backend.write(":CHANnel1:VERNier ON")
    backend.write(":CHANnel1:PROBe:SKEW 1e-09")

    assert backend.query(":CHANnel1:IMPedance?") == "FIFTy"
    assert backend.query(":CHANnel1:INVert?") == "1"
    assert backend.query(":CHANnel1:RANGe?") == "4"
    assert backend.query(":CHANnel1:UNITs?") == "AMP"
    assert backend.query(":CHANnel1:VERNier?") == "1"
    assert backend.query(":CHANnel1:PROBe:SKEW?") == "1e-09"


def test_simulator_label_and_display_annotation_roundtrip_4000x():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")

    backend.write(':CHANnel1:LABel "Input a"')
    backend.write(":DISPlay:LABel OFF")
    backend.write(":DISPlay:ANNotation2 ON")
    backend.write(':DISPlay:ANNotation2:TEXT "Note"')
    backend.write(":DISPlay:ANNotation2:COLor RED")
    backend.write(":DISPlay:ANNotation2:BACKground OPAQ")
    backend.write(":DISPlay:ANNotation2:X1Position 10")
    backend.write(":DISPlay:ANNotation2:Y1Position 20")

    assert backend.query(":CHANnel1:LABel?") == '"Input a"'
    assert backend.query(":DISPlay:LABel?") == "0"
    assert backend.query(":DISPlay:ANNotation2?") == "1"
    assert backend.query(":DISPlay:ANNotation2:TEXT?") == '"Note"'
    assert backend.query(":DISPlay:ANNotation2:COLor?") == "RED"
    assert backend.query(":DISPlay:ANNotation2:BACKground?") == "OPAQ"
    assert backend.query(":DISPlay:ANNotation2:X1Position?") == "10"
    assert backend.query(":DISPlay:ANNotation2:Y1Position?") == "20"


def test_simulator_common_display_roundtrip():
    backend = SimulatorBackend()

    backend.measurement_statistics_items = ["VPP"]
    backend.write(":DISPlay:CLEar")
    backend.write(":DISPlay:PERSistence 0.5")
    backend.write(":DISPlay:INTensity:WAVeform 75")
    backend.write(":DISPlay:VECTors ON")

    assert backend.measurement_statistics_items == []
    assert backend.query(":DISPlay:PERSistence?") == "0.5"
    assert backend.query(":DISPlay:INTensity:WAVeform?") == "75"
    assert backend.query(":DISPlay:VECTors?") == "ON"
    assert backend.history == [
        ":DISPlay:CLEar",
        ":DISPlay:PERSistence 0.5",
        ":DISPlay:INTensity:WAVeform 75",
        ":DISPlay:VECTors ON",
        ":DISPlay:PERSistence?",
        ":DISPlay:INTensity:WAVeform?",
        ":DISPlay:VECTors?",
    ]


def test_simulator_rejects_old_display_intensity_path():
    backend = SimulatorBackend()

    with pytest.raises(SimulatorBackendError, match="Unsupported simulator write"):
        backend.write(":DISPlay:INTensity 75")

    with pytest.raises(SimulatorBackendError, match="Unsupported simulator query"):
        backend.query(":DISPlay:INTensity?")


def test_simulator_unindexed_annotation_roundtrip_3000x():
    backend = SimulatorBackend(physical_model_id="keysight-dsox3024a")

    backend.write(":DISPlay:ANNotation ON")
    backend.write(':DISPlay:ANNotation:TEXT "Note"')

    assert backend.query(":DISPlay:ANNotation?") == "1"
    assert backend.query(":DISPlay:ANNotation:TEXT?") == '"Note"'


def test_simulator_waveform_model_reflects_scale_offset_timebase_and_channel_phase():
    backend = SimulatorBackend()

    backend.write(":TIMebase:SCALe 0.002")
    backend.write(":TIMebase:POSition 0.001")
    backend.write(":CHANnel1:SCALe 0.5")
    backend.write(":CHANnel1:OFFSet 0.25")
    backend.write(":WAVeform:SOURce CHANnel1")
    backend.write(":WAVeform:FORMat BYTE")
    backend.write(":WAVeform:POINts 1000")
    ch1_preamble = backend.query(":WAVeform:PREamble?").split(",")
    ch1_samples = backend.query_binary_values(":WAVeform:DATA?", datatype="B")

    backend.write(":WAVeform:SOURce CHANnel2")
    ch2_samples = backend.query_binary_values(":WAVeform:DATA?", datatype="B")

    assert float(ch1_preamble[4]) == pytest.approx(2.0e-5)
    assert float(ch1_preamble[5]) == pytest.approx(-0.009)
    assert float(ch1_preamble[7]) == pytest.approx(0.01)
    assert float(ch1_preamble[8]) == pytest.approx(0.25)
    assert len(ch1_samples) == 1000
    assert ch1_samples != ch2_samples


def test_simulator_respects_model_channel_capabilities():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")

    with pytest.raises(SimulatorBackendError, match="CH5 is not available"):
        backend.write(":WAVeform:SOURce CHANnel5")

    with pytest.raises(SimulatorBackendError, match="CH5 is not available"):
        backend.query(":MEASure:VPP? CHANnel5")

    with pytest.raises(SimulatorBackendError, match="CH5 is not available"):
        backend.write(":TRIGger:EDGE:SOURce CHANnel5")


def test_simulator_byte_waveform_uses_requested_5000_points():
    backend = SimulatorBackend()

    backend.write(":WAVeform:SOURce CHANnel1")
    backend.write(":WAVeform:FORMat BYTE")
    backend.write(":WAVeform:POINts 5000")

    preamble = backend.query(":WAVeform:PREamble?")
    samples = backend.query_binary_values(":WAVeform:DATA?", datatype="B")

    assert preamble.split(",")[2] == "5000"
    assert len(samples) == 5000
    assert min(samples) >= 0
    assert max(samples) <= 255


def test_simulator_word_waveform_uses_requested_10000_points():
    backend = SimulatorBackend()

    backend.write(":WAVeform:SOURce CHANnel2")
    backend.write(":WAVeform:FORMat WORD")
    backend.write(":WAVeform:BYTeorder MSBFirst")
    backend.write(":WAVeform:UNSigned ON")
    backend.write(":WAVeform:POINts 10000")

    preamble = backend.query(":WAVeform:PREamble?")
    samples = backend.query_binary_values(":WAVeform:DATA?", datatype="H")

    assert preamble.split(",")[2] == "10000"
    assert len(samples) == 10000
    assert min(samples) >= 0
    assert max(samples) <= 65535


def test_simulator_rejects_unsupported_waveform_points_in_strict_mode():
    backend = SimulatorBackend()

    with pytest.raises(SimulatorBackendError, match="waveform point count"):
        backend.write(":WAVeform:POINts 2000")


def test_simulator_measurements_use_channel_and_pair_signal_model():
    backend = SimulatorBackend()

    assert float(backend.query(":MEASure:VPP? CHANnel1")) == pytest.approx(0.5)
    assert float(backend.query(":MEASure:VPP? CHANnel2")) == pytest.approx(1.0)
    assert float(backend.query(":MEASure:PHASe? CHANnel1,CHANnel2")) == pytest.approx(45.0)
    assert float(backend.query(":MEASure:DELay? AUTO,CHANnel1,CHANnel2")) == pytest.approx(
        45.0 / 360.0 / 1000.0
    )


def test_simulator_parameterized_measurements_are_deterministic():
    backend = SimulatorBackend()

    assert float(backend.query(":MEASure:VTIMe? 0,CHANnel1")) == pytest.approx(0.0)
    assert float(backend.query(":MEASure:TEDGe? +1,CHANnel1")) == pytest.approx(0.0)
    assert float(backend.query(":MEASure:TVALue? 0,+1,CHANnel1")) == pytest.approx(0.0)


def test_simulator_measurement_invalid_sentinel_hooks():
    backend = SimulatorBackend(invalid_measurement_channels={2})

    assert backend.query(":MEASure:VPP? CHANnel2") == "9.9E+37"
    assert backend.query(":MEASure:TVALue? 99,+1,CHANnel1") == "9.9E+37"


def test_simulator_failure_and_override_hooks_record_attempted_command():
    query_error = OscilloscopeError("configured query failure")
    binary_error = OscilloscopeError("configured binary failure")
    backend = SimulatorBackend(
        query_failures={":MEASure:VPP? CHANnel1": query_error},
        binary_failures={":WAVeform:DATA?": binary_error},
        query_overrides={":ACQuire:TYPE?": "bad-type"},
        binary_overrides={":DISPlay:DATA? PNG, COLor": []},
    )

    with pytest.raises(OscilloscopeError, match="configured query failure"):
        backend.query(":MEASure:VPP? CHANnel1")
    assert backend.history[-1] == ":MEASure:VPP? CHANnel1"

    with pytest.raises(OscilloscopeError, match="configured binary failure"):
        backend.query_binary_values(":WAVeform:DATA?")
    assert backend.history[-1] == ":WAVeform:DATA?"

    assert backend.query(":ACQuire:TYPE?") == "bad-type"
    assert backend.query_binary_values(":DISPlay:DATA? PNG, COLor") == []


def test_simulator_screenshot_png_reflects_inksaver_background():
    backend = SimulatorBackend()

    black = bytes(backend.query_binary_values(":DISPlay:DATA? PNG, COLor"))
    backend.write(":HARDcopy:INKSaver ON")
    white = bytes(backend.query_binary_values(":DISPlay:DATA? PNG, COLor"))

    assert black.startswith(PNG_SIGNATURE)
    assert white.startswith(PNG_SIGNATURE)
    assert black != white
    assert _png_dimensions(black) == (480, 272)
    assert _png_dimensions(white) == (480, 272)
    assert len(black) > 1000
    assert len(white) > 1000


def test_simulator_screenshot_png_reflects_model_label_deterministically():
    first = bytes(
        SimulatorBackend(physical_model_id="keysight-dsox4024a").query_binary_values(
            ":DISPlay:DATA? PNG, COLor"
        )
    )
    second = bytes(
        SimulatorBackend(physical_model_id="keysight-dsox4024a").query_binary_values(
            ":DISPlay:DATA? PNG, COLor"
        )
    )
    different_model = bytes(
        SimulatorBackend(physical_model_id="keysight-dsox3024a").query_binary_values(
            ":DISPlay:DATA? PNG, COLor"
        )
    )

    assert first == second
    assert first != different_model
    assert _png_dimensions(different_model) == (480, 272)


def test_simulator_hardcopy_format_pack_state_and_binary_payloads():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")

    assert backend.query(":HARDcopy:AREA?") == "SCR"
    assert backend.query(":HARDcopy:INKSaver?") == "0"
    assert backend.query(":HARDcopy:PALette?") == "NONE"
    assert backend.query(":HARDcopy:LAYout?") == "PORT"
    assert backend.query(":HCOPY:SDUMp:FORMat?") == "PNG"

    backend.write(":HARDcopy:INKSaver ON")
    backend.write(":HARDcopy:PALette GRAYscale")
    backend.write(":HARDcopy:LAYout LANDscape")
    assert backend.query(":HARDcopy:PALette?") == "GRAY"
    assert backend.query(":HARDcopy:LAYout?") == "LAND"
    assert bytes(backend.query_binary_values(":HCOPY:SDUMp:DATA? PNG")).startswith(
        PNG_SIGNATURE
    )
    assert bytes(backend.query_binary_values(":HCOPY:SDUMp:DATA? BMP")).startswith(b"BM")
    assert bytes(
        backend.query_binary_values(":HCOPY:SDUMp:DATA? BMP8bit")
    ).startswith(b"BM")


def test_simulator_supports_configured_signal_shapes_and_measurements():
    backend = SimulatorBackend(
        signals={
            1: SimulatedSignal("square", 2000.0, 2.0, 0.1, 0.0),
            2: SimulatedSignal("ramp", 500.0, 3.0, -0.2, 90.0),
            3: SimulatedSignal("dc", 0.0, 0.0, 1.25, 0.0),
            4: SimulatedSignal("noise", 0.0, 0.0, -0.1, 0.0, 0.05),
        }
    )

    assert float(backend.query(":MEASure:VPP? CHANnel1")) == pytest.approx(2.0)
    assert float(backend.query(":MEASure:VRMS? DISPlay,AC,CHANnel1")) == pytest.approx(1.0)
    assert float(backend.query(":MEASure:VAVerage? DISPlay,CHANnel2")) == pytest.approx(-0.2)
    assert float(backend.query(":MEASure:VAVerage? DISPlay,CHANnel3")) == pytest.approx(1.25)
    assert backend.query(":MEASure:FREQuency? CHANnel3") == "9.9E+37"
    assert backend.query(":MEASure:PERiod? CHANnel4") == "9.9E+37"


def test_simulator_signal_offset_adds_channel_offset_and_affects_y_at_x():
    backend = SimulatorBackend(
        signals={1: SimulatedSignal("sine", 1000.0, 2.0, 0.4, 0.0)}
    )
    backend.write(":CHANnel1:OFFSet 0.25")

    assert float(backend.query(":MEASure:VAVerage? DISPlay,CHANnel1")) == pytest.approx(
        0.65
    )
    assert float(backend.query(":MEASure:VTIMe? 0,CHANnel1")) == pytest.approx(0.65)


def test_simulator_trigger_alignment_respects_level_and_slope():
    backend = SimulatorBackend(
        signals={1: SimulatedSignal("sine", 1000.0, 2.0, 0.0, 0.0)}
    )
    backend.write(":TRIGger:EDGE:SOURce CHANnel1")
    backend.write(":TRIGger:EDGE:LEVel 0.5")
    backend.write(":TRIGger:EDGE:SLOPe POSitive")
    backend.write(":WAVeform:SOURce CHANnel1")

    assert backend._raw_waveform_voltage_at_index(500) == pytest.approx(0.5, abs=0.01)

    backend.write(":TRIGger:EDGE:SLOPe NEGative")

    assert backend._raw_waveform_voltage_at_index(500) == pytest.approx(0.5, abs=0.01)
    assert backend._raw_waveform_voltage_at_index(501) < backend._raw_waveform_voltage_at_index(
        500
    )


def test_simulator_channel_display_off_blocks_capture_and_invalidates_measurements():
    backend = SimulatorBackend()
    backend.write(":CHANnel1:DISPlay OFF")
    backend.write(":WAVeform:SOURce CHANnel1")

    with pytest.raises(SimulatorBackendError, match="display is off"):
        backend.query_binary_values(":WAVeform:DATA?", datatype="B")

    assert backend.query(":MEASure:VPP? CHANnel1") == "9.9E+37"
    assert backend.query(":MEASure:PHASe? CHANnel2,CHANnel1") == "9.9E+37"


def test_simulator_acquisition_modes_are_distinct_and_deterministic():
    backend = SimulatorBackend(
        signals={1: SimulatedSignal("sine", 1000.0, 1.0, 0.0, 0.0, 0.1)}
    )
    backend.write(":WAVeform:SOURce CHANnel1")

    normal = tuple(backend._waveform_voltage_at_index(index) for index in range(20))
    backend.write(":ACQuire:TYPE AVERage")
    backend.write(":ACQuire:COUNt 16")
    average = tuple(backend._waveform_voltage_at_index(index) for index in range(20))
    backend.write(":ACQuire:TYPE HRESolution")
    high_resolution = tuple(backend._waveform_voltage_at_index(index) for index in range(20))
    backend.write(":ACQuire:TYPE PEAK")
    peak = tuple(backend._waveform_voltage_at_index(index) for index in range(20))

    assert normal == tuple(backend._raw_waveform_voltage_at_index(index) for index in range(20))
    assert average != normal
    assert high_resolution != normal
    assert peak != normal
    assert peak == tuple(backend._waveform_voltage_at_index(index) for index in range(20))


def test_simulator_average_count_scales_deterministic_noise():
    backend = SimulatorBackend(
        signals={1: SimulatedSignal("dc", 0.0, 0.0, 0.0, 0.0, 0.16)}
    )
    backend.write(":WAVeform:SOURce CHANnel1")
    normal = backend._waveform_voltage_at_index(17)

    backend.write(":ACQuire:TYPE AVERage")
    backend.write(":ACQuire:COUNt 16")
    averaged = backend._waveform_voltage_at_index(17)

    assert averaged == pytest.approx(normal / 4.0)


def test_simulator_high_resolution_smooths_neighbors_and_reduces_noise():
    backend = SimulatorBackend(
        signals={1: SimulatedSignal("sine", 1000.0, 1.0, 0.0, 0.0, 0.12)}
    )
    backend.write(":WAVeform:SOURce CHANnel1")
    raw_neighbors = [
        backend._raw_waveform_voltage_at_index(index, noise_scale=0.5)
        for index in (99, 100, 101)
    ]

    backend.write(":ACQuire:TYPE HRESolution")

    assert backend._waveform_voltage_at_index(100) == pytest.approx(
        sum(raw_neighbors) / 3.0
    )


def test_simulator_peak_envelope_affects_measurement_extrema():
    backend = SimulatorBackend(
        signals={1: SimulatedSignal("sine", 1000.0, 2.0, 0.0, 0.0, 0.2)}
    )
    backend.write(":ACQuire:TYPE PEAK")

    assert float(backend.query(":MEASure:VPP? CHANnel1")) == pytest.approx(2.8)
    assert float(backend.query(":MEASure:VAMPLitude? CHANnel1")) == pytest.approx(1.4)
    assert float(backend.query(":MEASure:VMIN? CHANnel1")) == pytest.approx(-1.4)
    assert float(backend.query(":MEASure:VMAX? CHANnel1")) == pytest.approx(1.4)


def test_simulator_invalid_measurement_conditions_return_sentinel():
    backend = SimulatorBackend(
        signals={
            1: SimulatedSignal("sine", 10.0, 1.0, 0.0, 0.0),
            2: SimulatedSignal("sine", 1000.0, 0.0, 0.0, 0.0),
        }
    )

    assert backend.query(":MEASure:FREQuency? CHANnel1") == "9.9E+37"
    assert backend.query(":MEASure:TEDGe? +99,CHANnel1") == "9.9E+37"
    assert backend.query(":MEASure:TVALue? 2,+1,CHANnel1") == "9.9E+37"
    assert backend.query(":MEASure:RISetime? CHANnel2") == "9.9E+37"
    assert float(backend.query(":MEASure:VPP? CHANnel2")) == pytest.approx(0.0)


def test_simulator_trigger_alignment_handles_all_public_slopes():
    backend = SimulatorBackend(
        signals={1: SimulatedSignal("sine", 1000.0, 2.0, 0.0, 0.0)}
    )
    backend.write(":TRIGger:EDGE:SOURce CHANnel1")
    backend.write(":TRIGger:EDGE:LEVel 0")
    backend.write(":WAVeform:SOURce CHANnel1")

    backend.write(":TRIGger:EDGE:SLOPe POSitive")
    assert backend._raw_waveform_voltage_at_index(500) == pytest.approx(0.0, abs=0.01)
    assert backend._raw_waveform_voltage_at_index(501) > backend._raw_waveform_voltage_at_index(500)

    backend.write(":TRIGger:EDGE:SLOPe NEGative")
    assert backend._raw_waveform_voltage_at_index(500) == pytest.approx(0.0, abs=0.01)
    assert backend._raw_waveform_voltage_at_index(501) < backend._raw_waveform_voltage_at_index(500)

    backend.write(":TRIGger:EDGE:SLOPe EITHer")
    assert backend._trigger_time_offset_s() == pytest.approx(0.0)

    backend.write(":TRIGger:EDGE:SLOPe ALTernate")
    first = tuple(backend.query_binary_values(":WAVeform:DATA?", datatype="B")[:3])
    second = tuple(backend.query_binary_values(":WAVeform:DATA?", datatype="B")[:3])
    assert first != second


def test_simulator_trigger_out_of_range_level_does_not_align():
    backend = SimulatorBackend(
        signals={1: SimulatedSignal("sine", 1000.0, 2.0, 0.0, 90.0)}
    )
    backend.write(":TRIGger:EDGE:SOURce CHANnel1")
    backend.write(":TRIGger:EDGE:LEVel 5")

    assert backend._trigger_time_offset_s() == 0.0


def test_simulator_identity_and_capabilities_come_from_physical_model_registry():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4034a")

    assert backend.query("*IDN?") == (
        "KEYSIGHT TECHNOLOGIES,DSOX4034A,SIM000000,07.20"
    )
    assert backend._capabilities is capabilities_for_model_id(
        "keysight-dsox4034a"
    )


def test_simulator_waveform_all_uses_instance_firmware_and_strict_support():
    old_firmware = SimulatorBackend(
        physical_model_id="keysight-dsox4034a", firmware="07.20"
    )
    assert old_firmware.query("*IDN?").endswith(",07.20")
    assert old_firmware.segmented_waveform_all is False
    with pytest.raises(SimulatorBackendError, match="Unsupported simulator write"):
        old_firmware.write(":WAVeform:SEGMented:ALL ON")
    assert old_firmware.segmented_waveform_all is False

    non_strict = SimulatorBackend(
        physical_model_id="keysight-dsox4034a",
        firmware="07.20",
        strict_unknown_commands=False,
    )
    assert non_strict.segmented_waveform_all is False
    non_strict.write(":WAVeform:SEGMented:ALL ON")
    assert non_strict.segmented_waveform_all is False

    new_firmware = SimulatorBackend(
        physical_model_id="keysight-dsox4034a", firmware="07.30"
    )
    assert new_firmware.query("*IDN?").endswith(",07.30")
    new_firmware.write(":WAVeform:SEGMented:ALL ON")
    assert new_firmware.segmented_waveform_all is True


def test_simulator_rejects_raw_or_unknown_physical_model_identity():
    with pytest.raises(UnsupportedModelError):
        SimulatorBackend(physical_model_id="DSOX4024A")
    with pytest.raises(UnsupportedModelError):
        SimulatorBackend(physical_model_id="keysight-dsox4054a")
