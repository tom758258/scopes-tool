from dataclasses import replace

import pytest

from scopes_tool_core.advanced import (
    SetupController,
    autoscale_commands,
    cursor_auto_vertical_plan,
    cursor_auto_timebase_plan,
    cursor_configure_commands,
    fft_configure_commands,
    fft_query_commands,
    math_display_command,
    math_display_query,
    math_clear_command,
    math_composite_source_commands,
    math_composite_source_query_commands,
    math_operator_commands,
    math_operator_query_commands,
    math_filter_commands,
    math_filter_query_commands,
    math_transform_commands,
    math_transform_query_commands,
    math_visualization_commands,
    math_visualization_query_commands,
    math_vertical_commands,
    math_vertical_query_commands,
    parse_math_display,
    parse_math_composite_operation,
    parse_math_filter_operation,
    parse_math_operation,
    parse_math_source,
    parse_math_source1,
    parse_math_transform,
    parse_math_trend_measurement,
    parse_math_visualization_operation,
    setup_recall_command,
    setup_save_command,
    trigger_holdoff_command,
    trigger_holdoff_commands,
)
from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import ChannelResponseError, ParameterValidationError
from scopes_tool_core.fake_backend import FakeBackend, FakeBackendError
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend, SimulatorBackendError


def test_advanced_command_formatting():
    capabilities = capabilities_for_model("DSOX4024A")

    assert trigger_holdoff_command(1e-6) == ":TRIGger:HOLDoff 1e-6"
    assert trigger_holdoff_commands(1e-6) == [
        ":TRIGger:HOLDoff:RANDom OFF",
        ":TRIGger:HOLDoff 1e-6",
    ]
    assert cursor_configure_commands(
        1,
        0.0,
        1e-3,
        y1_volts=0.0,
        y2_volts=0.5,
        capabilities=capabilities,
    ) == [
        ":MARKer:MODE MANual",
        ":MARKer:X1Y1source CHANnel1",
        ":MARKer:X2Y2source CHANnel1",
        ":MARKer:X1Position 0",
        ":MARKer:X2Position 0.001",
        ":MARKer:Y1Position 0",
        ":MARKer:Y2Position 0.5",
    ]
    assert autoscale_commands((1, 2), capabilities=capabilities) == [
        ":AUToscale CHANnel1,CHANnel2"
    ]
    assert setup_save_command(slot=3) == ":SAVE:SETup 3"
    assert setup_recall_command(file_spec="\\usb\\setup.scp") == (
        ':RECall:SETup "\\usb\\setup.scp"'
    )


@pytest.mark.parametrize(
    ("model", "prefix"),
    [
        ("DSOX2004A", ":FUNCtion"),
        ("DSOX3024A", ":FUNCtion"),
        ("DSOX4024A", ":FUNCtion1"),
    ],
)
def test_fft_commands_use_series_appropriate_function_prefix(model, prefix):
    capabilities = capabilities_for_model(model)

    assert fft_configure_commands(
        1,
        1,
        units="decibel",
        window="hanning",
        center_hz=1000,
        span_hz=10000,
        display=True,
        capabilities=capabilities,
    ) == [
        f"{prefix}:OPERation FFT",
        f"{prefix}:SOURce1 CHANnel1",
        f"{prefix}:FFT:VTYPe DECibel",
        f"{prefix}:FFT:WINDow HANNing",
        f"{prefix}:FFT:CENTer 1000",
        f"{prefix}:FFT:SPAN 10000",
        f"{prefix}:DISPlay ON",
    ]
    assert fft_query_commands(1, capabilities=capabilities) == [
        f"{prefix}:OPERation?",
        f"{prefix}:SOURce1?",
        f"{prefix}:FFT:VTYPe?",
        f"{prefix}:FFT:WINDow?",
        f"{prefix}:FFT:CENTer?",
        f"{prefix}:FFT:SPAN?",
        f"{prefix}:DISPlay?",
    ]


def test_fft_function_validation_uses_profile_function_count():
    single_function = capabilities_for_model("DSOX2004A")
    four_functions = capabilities_for_model("DSOX4024A")
    unsupported = replace(four_functions, math_function_count=0)

    with pytest.raises(
        ParameterValidationError,
        match="Math functions are not supported by this capability profile",
    ):
        fft_configure_commands(1, 1, capabilities=unsupported)

    with pytest.raises(ParameterValidationError, match="between 1 and 1"):
        fft_configure_commands(2, 1, capabilities=single_function)

    assert fft_configure_commands(4, 1, capabilities=four_functions)[:2] == [
        ":FUNCtion4:OPERation FFT",
        ":FUNCtion4:SOURce1 CHANnel1",
    ]


def test_fft_phase_and_advanced_4000x_commands():
    capabilities = capabilities_for_model("DSOX4024A")

    assert fft_configure_commands(
        2,
        3,
        fft_operation="fft-phase",
        phase_reference="display",
        capabilities=capabilities,
    ) == [
        ":FUNCtion2:OPERation FFTPhase",
        ":FUNCtion2:SOURce1 CHANnel3",
        ":FUNCtion2:PHASe:REFerence DISPlay",
    ]
    assert fft_configure_commands(
        1,
        1,
        start_hz=100,
        stop_hz=1000,
        gate="zoom",
        detection_type="positive-peak",
        detection_points=2048,
        capabilities=capabilities,
    ) == [
        ":FUNCtion1:OPERation FFT",
        ":FUNCtion1:SOURce1 CHANnel1",
        ":FUNCtion1:FREQuency:STARt 100",
        ":FUNCtion1:FREQuency:STOP 1000",
        ":FUNCtion1:GATE ZOOM",
        ":FUNCtion1:DETection:TYPE PPOSitive",
        ":FUNCtion1:DETection:POINts 2048",
    ]


def test_fft_phase_rejects_magnitude_units():
    with pytest.raises(
        ParameterValidationError,
        match="units.*fft-phase",
    ):
        fft_configure_commands(
            1,
            1,
            fft_operation="fft-phase",
            units="decibel",
            capabilities=capabilities_for_model("DSOX4024A"),
        )


def test_fft_advanced_validation_uses_profile_and_range_mode():
    basic = capabilities_for_model("DSOX3024A")
    advanced = capabilities_for_model("DSOX4024A")

    with pytest.raises(ParameterValidationError, match="4000X"):
        fft_configure_commands(
            1,
            1,
            gate="zoom",
            capabilities=basic,
        )
    with pytest.raises(ParameterValidationError, match="cannot be combined"):
        fft_configure_commands(
            1,
            1,
            center_hz=1000,
            start_hz=100,
            capabilities=advanced,
        )


def test_fft_4000x_aggregate_query_parses_advanced_state():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()
    scope.configure_fft(
        2,
        1,
        fft_operation="fft-phase",
        start_hz=100,
        stop_hz=1000,
        gate="zoom",
        phase_reference="trigger",
        detection_type="average",
        detection_points=4096,
    )
    backend.fft_functions[2]["operation"] = "fFtP"
    backend.fft_functions[2]["gate"] = "zOoM"
    backend.fft_functions[2]["phase_reference"] = "dIsP"
    backend.fft_functions[2]["detection_type"] = "pNeG"

    state = scope.query_fft(2)

    assert state.operation == "fFtP"
    assert state.operation_canonical == "fft-phase"
    assert state.start_hz == pytest.approx(100)
    assert state.stop_hz == pytest.approx(1000)
    assert state.gate == "zoom"
    assert state.phase_reference == "display"
    assert state.detection_type == "negative-peak"
    assert state.detection_points == 4096
    assert state.bin_size_hz == pytest.approx(1000)
    assert state.sample_rate_hz == pytest.approx(1e9)
    assert state.resolution_bandwidth_hz == pytest.approx(1500)
    assert backend.history[-1] == ":FUNCtion2:PHASe:REFerence?"


def test_fft_fractional_detection_points_readback_is_rejected():
    class FractionalDetectionPointsBackend(SimulatorBackend):
        def query(self, command):
            if command == ":FUNCtion1:DETection:POINts?":
                self.history.append(command)
                return "640.5"
            return super().query(command)

    backend = FractionalDetectionPointsBackend(
        physical_model_id="keysight-dsox4024a"
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    with pytest.raises(ChannelResponseError, match="detection points"):
        scope.query_fft(1)


@pytest.mark.parametrize(
    ("model", "prefix"),
    [
        ("DSOX2004A", ":FUNCtion"),
        ("DSOX3024A", ":FUNCtion"),
        ("DSOX4024A", ":FUNCtion1"),
    ],
)
def test_math_p1_commands_use_series_appropriate_function_prefix(model, prefix):
    capabilities = capabilities_for_model(model)

    assert math_display_command(1, True, capabilities=capabilities) == (
        f"{prefix}:DISPlay ON"
    )
    assert math_display_query(1, capabilities=capabilities) == f"{prefix}:DISPlay?"
    assert math_vertical_commands(
        1, scale=2, offset=0.5, capabilities=capabilities
    ) == [
        f"{prefix}:SCALe 2",
        f"{prefix}:OFFSet 0.5",
    ]
    assert math_vertical_commands(
        1, range_value=8, capabilities=capabilities
    ) == [f"{prefix}:RANGe 8"]
    assert math_vertical_query_commands(1, capabilities=capabilities) == [
        f"{prefix}:SCALe?",
        f"{prefix}:RANGe?",
        f"{prefix}:OFFSet?",
    ]


def test_math_p1_validation_rejects_invalid_functions_and_vertical_values():
    single_function = capabilities_for_model("DSOX2004A")
    unsupported = replace(single_function, math_function_count=0)

    with pytest.raises(ParameterValidationError, match="must be an integer"):
        math_display_query(True, capabilities=single_function)
    with pytest.raises(ParameterValidationError, match="must be an integer"):
        math_display_query(1.5, capabilities=single_function)
    with pytest.raises(ParameterValidationError, match="between 1 and 1"):
        math_display_query(2, capabilities=single_function)
    with pytest.raises(ParameterValidationError, match="Math functions are not supported"):
        math_display_query(1, capabilities=unsupported)
    with pytest.raises(ParameterValidationError, match="finite number"):
        math_vertical_commands(1, offset=True, capabilities=single_function)
    with pytest.raises(ParameterValidationError, match="finite number"):
        math_vertical_commands(1, scale=10**10000, capabilities=single_function)
    with pytest.raises(ParameterValidationError, match="greater than zero"):
        math_vertical_commands(1, scale=0, capabilities=single_function)
    with pytest.raises(ParameterValidationError, match="greater than zero"):
        math_vertical_commands(1, range_value=-1, capabilities=single_function)
    with pytest.raises(ParameterValidationError, match="finite number"):
        math_vertical_commands(
            1, offset=float("inf"), capabilities=single_function
        )
    with pytest.raises(ParameterValidationError, match="mutually exclusive"):
        math_vertical_commands(
            1, scale=2, range_value=8, capabilities=single_function
        )
    with pytest.raises(ChannelResponseError, match="Math display"):
        parse_math_display("UNKNOWN")


def test_math_p1_simulator_round_trip_in_one_session():
    backend = SimulatorBackend(physical_model_id="keysight-dsox2004a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_math_display(1, True)
    display = scope.query_math_display(1)
    scope.configure_math_vertical(1, scale=2, offset=0.5)
    vertical = scope.query_math_vertical(1)

    assert display.enabled is True
    assert display.raw == "1"
    assert vertical.scale == pytest.approx(2.0)
    assert vertical.range == pytest.approx(8.0)
    assert vertical.offset == pytest.approx(0.5)
    assert backend.history[1:] == [
        ":FUNCtion:DISPlay ON",
        ":FUNCtion:DISPlay?",
        ":FUNCtion:SCALe 2",
        ":FUNCtion:OFFSet 0.5",
        ":FUNCtion:SCALe?",
        ":FUNCtion:RANGe?",
        ":FUNCtion:OFFSet?",
    ]


@pytest.mark.parametrize(
    ("operation", "token"),
    [
        ("add", "ADD"),
        ("subtract", "SUBTract"),
        ("multiply", "MULTiply"),
        ("divide", "DIVide"),
    ],
)
def test_math_p2_operation_mapping(operation, token):
    capabilities = capabilities_for_model("DSOX4024A")

    assert math_operator_commands(
        1,
        operation,
        "channel1",
        "channel2",
        capabilities=capabilities,
    )[0] == f":FUNCtion1:OPERation {token}"


@pytest.mark.parametrize(
    ("model", "function", "prefix"),
    [
        ("DSOX2004A", 1, ":FUNCtion"),
        ("DSOX3024A", 1, ":FUNCtion"),
        ("DSOX4024A", 2, ":FUNCtion2"),
    ],
)
def test_math_p2_operator_commands_use_series_dialect(model, function, prefix):
    capabilities = capabilities_for_model(model)

    assert math_operator_commands(
        function,
        "subtract",
        "channel1",
        "channel2",
        capabilities=capabilities,
    ) == [
        f"{prefix}:OPERation SUBTract",
        f"{prefix}:SOURce1 CHANnel1",
        f"{prefix}:SOURce2 CHANnel2",
    ]
    assert math_operator_query_commands(
        function, capabilities=capabilities
    ) == [
        f"{prefix}:OPERation?",
        f"{prefix}:SOURce1?",
        f"{prefix}:SOURce2?",
    ]


def test_math_p2_operator_validation_and_readback_parsing():
    single_function = capabilities_for_model("DSOX2004A")
    four_functions = capabilities_for_model("DSOX4024A")

    with pytest.raises(ParameterValidationError, match="between 1 and 1"):
        math_operator_commands(
            2,
            "add",
            "channel1",
            "channel2",
            capabilities=single_function,
        )
    with pytest.raises(ParameterValidationError, match="channel1"):
        math_operator_commands(
            1,
            "add",
            "channel1",
            "channel5",
            capabilities=four_functions,
        )
    assert parse_math_operation(" sUbT ") == "subtract"
    assert parse_math_source(" cHaN1 ", capabilities=four_functions) == "channel1"
    with pytest.raises(ChannelResponseError, match="UNKNOWN"):
        parse_math_operation(" UNKNOWN ")


def test_math_p2_simulator_operator_round_trip():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_math_operator(2, "subtract", "channel1", "channel2")
    state = scope.query_math_operator(2)

    assert state.function == 2
    assert state.operation == "subtract"
    assert state.operation_raw == "SUBTRACT"
    assert state.source1 == "channel1"
    assert state.source1_raw == "CHANnel1"
    assert state.source2 == "channel2"
    assert state.source2_raw == "CHANnel2"
    assert backend.history[1:] == [
        ":FUNCtion2:OPERation SUBTract",
        ":FUNCtion2:SOURce1 CHANnel1",
        ":FUNCtion2:SOURce2 CHANnel2",
        ":FUNCtion2:OPERation?",
        ":FUNCtion2:SOURce1?",
        ":FUNCtion2:SOURce2?",
    ]


@pytest.mark.parametrize(
    ("operation", "token", "readbacks"),
    [
        ("differentiate", "DIFF", ("DIFF",)),
        ("integrate", "INTegrate", ("INT", "INTEGRATE")),
        ("sqrt", "SQRT", ("SQRT",)),
        ("absolute", "ABSolute", ("ABS", "ABSOLUTE")),
        ("square", "SQUare", ("SQU", "SQUARE")),
        ("ln", "LN", ("LN",)),
        ("log10", "LOG", ("LOG",)),
        ("exp", "EXP", ("EXP",)),
        ("exp10", "TEN", ("TEN",)),
        ("linear", "LINear", ("LIN", "LINEAR")),
    ],
)
def test_math_p3_transform_mapping_and_readback(operation, token, readbacks):
    capabilities = capabilities_for_model("DSOX4024A")

    assert math_transform_commands(
        1,
        operation,
        "channel1",
        capabilities=capabilities,
    )[0] == f":FUNCtion1:OPERation {token}"
    for readback in readbacks:
        assert parse_math_transform(f" {readback.swapcase()} ") == operation


@pytest.mark.parametrize(
    ("model", "function", "prefix"),
    [
        ("DSOX2004A", 1, ":FUNCtion"),
        ("DSOX3024A", 1, ":FUNCtion"),
        ("DSOX4024A", 2, ":FUNCtion2"),
    ],
)
def test_math_p3_transform_commands_use_series_dialect(model, function, prefix):
    capabilities = capabilities_for_model(model)

    assert math_transform_commands(
        function,
        "absolute",
        "channel1",
        capabilities=capabilities,
    ) == [
        f"{prefix}:OPERation ABSolute",
        f"{prefix}:SOURce1 CHANnel1",
    ]
    assert math_transform_query_commands(
        function, capabilities=capabilities
    ) == [
        f"{prefix}:OPERation?",
        f"{prefix}:SOURce1?",
    ]


def test_math_p3_integrate_command_order_and_input_offset():
    capabilities = capabilities_for_model("DSOX2004A")

    assert math_transform_commands(
        1,
        "integrate",
        "channel1",
        input_offset=0,
        capabilities=capabilities,
    ) == [
        ":FUNCtion:OPERation INTegrate",
        ":FUNCtion:SOURce1 CHANnel1",
        ":FUNCtion:INTegrate:IOFFset 0",
    ]


def test_math_p3_linear_command_order_gain_and_offset():
    capabilities = capabilities_for_model("DSOX4024A")

    assert math_transform_commands(
        2,
        "linear",
        "channel1",
        gain=2,
        linear_offset=-1,
        capabilities=capabilities,
    ) == [
        ":FUNCtion2:OPERation LINear",
        ":FUNCtion2:SOURce1 CHANnel1",
        ":FUNCtion2:LINear:GAIN 2",
        ":FUNCtion2:LINear:OFFSet -1",
    ]


def test_math_p3_transform_validation():
    single_function = capabilities_for_model("DSOX2004A")
    four_functions = capabilities_for_model("DSOX4024A")

    with pytest.raises(ParameterValidationError, match="only valid.*integrate"):
        math_transform_commands(
            1,
            "absolute",
            "channel1",
            input_offset=0,
            capabilities=single_function,
        )
    with pytest.raises(ParameterValidationError, match="only valid.*linear"):
        math_transform_commands(
            1,
            "integrate",
            "channel1",
            gain=2,
            capabilities=single_function,
        )
    with pytest.raises(ParameterValidationError, match="finite number"):
        math_transform_commands(
            1,
            "linear",
            "channel1",
            gain=float("inf"),
            capabilities=single_function,
        )
    with pytest.raises(ParameterValidationError, match="finite number"):
        math_transform_commands(
            1,
            "integrate",
            "channel1",
            input_offset=10**10000,
            capabilities=single_function,
        )
    with pytest.raises(ParameterValidationError, match="between 1 and 1"):
        math_transform_commands(
            2,
            "absolute",
            "channel1",
            capabilities=single_function,
        )
    with pytest.raises(ParameterValidationError, match="channel1"):
        math_transform_commands(
            1,
            "absolute",
            "channel5",
            capabilities=four_functions,
        )
    with pytest.raises(ChannelResponseError, match="ADD"):
        parse_math_transform(" ADD ")


def test_math_p3_simulator_integrate_and_linear_round_trip():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_math_transform(
        2,
        "integrate",
        "channel1",
        input_offset=0.25,
    )
    integrate_state = scope.query_math_transform(2)
    scope.configure_math_transform(
        2,
        "linear",
        "channel2",
        gain=2,
        linear_offset=-1,
    )
    linear_state = scope.query_math_transform(2)

    assert integrate_state.operation == "integrate"
    assert integrate_state.operation_raw == "INTEGRATE"
    assert integrate_state.source == "channel1"
    assert integrate_state.source_raw == "CHANnel1"
    assert integrate_state.input_offset == pytest.approx(0.25)
    assert integrate_state.gain is None
    assert integrate_state.linear_offset is None
    assert linear_state.operation == "linear"
    assert linear_state.source == "channel2"
    assert linear_state.input_offset is None
    assert linear_state.gain == pytest.approx(2.0)
    assert linear_state.linear_offset == pytest.approx(-1.0)
    assert backend.history[1:] == [
        ":FUNCtion2:OPERation INTegrate",
        ":FUNCtion2:SOURce1 CHANnel1",
        ":FUNCtion2:INTegrate:IOFFset 0.25",
        ":FUNCtion2:OPERation?",
        ":FUNCtion2:SOURce1?",
        ":FUNCtion2:INTegrate:IOFFset?",
        ":FUNCtion2:OPERation LINear",
        ":FUNCtion2:SOURce1 CHANnel2",
        ":FUNCtion2:LINear:GAIN 2",
        ":FUNCtion2:LINear:OFFSet -1",
        ":FUNCtion2:OPERation?",
        ":FUNCtion2:SOURce1?",
        ":FUNCtion2:LINear:GAIN?",
        ":FUNCtion2:LINear:OFFSet?",
    ]


@pytest.mark.parametrize(
    ("operation", "token"),
    [
        ("add", "ADD"),
        ("subtract", "SUBTract"),
        ("multiply", "MULTiply"),
    ],
)
def test_math_p4_goft_operation_mapping(operation, token):
    capabilities = capabilities_for_model("DSOX2004A")

    assert math_composite_source_commands(
        operation,
        "channel1",
        "channel2",
        capabilities=capabilities,
    )[0] == f":FUNCtion:GOFT:OPERation {token}"


def test_math_p4_goft_simulator_configure_query_state():
    backend = SimulatorBackend(physical_model_id="keysight-dsox2004a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_math_composite_source("subtract", "channel1", "channel2")
    state = scope.query_math_composite_source()

    assert state.operation == "subtract"
    assert state.operation_raw == "SUBTRACT"
    assert state.source1 == "channel1"
    assert state.source1_raw == "CHANnel1"
    assert state.source2 == "channel2"
    assert state.source2_raw == "CHANnel2"
    assert backend.history[1:] == [
        ":FUNCtion:GOFT:OPERation SUBTract",
        ":FUNCtion:GOFT:SOURce1 CHANnel1",
        ":FUNCtion:GOFT:SOURce2 CHANnel2",
        ":FUNCtion:GOFT:OPERation?",
        ":FUNCtion:GOFT:SOURce1?",
        ":FUNCtion:GOFT:SOURce2?",
    ]
    assert parse_math_composite_operation(" mUlT ") == "multiply"


def test_math_p4_transform_composite_source_commands_and_query_parse():
    capabilities = capabilities_for_model("DSOX3024A")

    assert math_transform_commands(
        1,
        "absolute",
        "composite",
        capabilities=capabilities,
    ) == [
        ":FUNCtion:OPERation ABSolute",
        ":FUNCtion:SOURce1 GOFT",
    ]
    assert parse_math_source1(
        " GOFT ",
        1,
        capabilities=capabilities,
        allow_composite=True,
    ) == "composite"
    backend = SimulatorBackend(physical_model_id="keysight-dsox3024a")
    scope = Oscilloscope(backend)
    scope.query_idn()
    scope.configure_math_transform(1, "absolute", "composite")

    state = scope.query_math_transform(1)

    assert state.source == "composite"
    assert state.source_raw == "GOFT"


def test_math_p4_4000x_lower_function_cascade_source():
    capabilities = capabilities_for_model("DSOX4034A")

    assert math_transform_commands(
        2,
        "absolute",
        "math1",
        capabilities=capabilities,
    ) == [
        ":FUNCtion2:OPERation ABSolute",
        ":FUNCtion2:SOURce1 FUNCtion1",
    ]
    assert parse_math_source1(
        "FUNC1", 2, capabilities=capabilities
    ) == "math1"
    assert parse_math_source1(
        "FUNCtion1", 2, capabilities=capabilities
    ) == "math1"
    assert parse_math_source1(
        "MATH1", 2, capabilities=capabilities
    ) == "math1"
    backend = SimulatorBackend(physical_model_id="keysight-dsox4034a")
    scope = Oscilloscope(backend)
    scope.query_idn()
    scope.configure_math_transform(2, "absolute", "math1")

    state = scope.query_math_transform(2)

    assert state.source == "math1"
    assert state.source_raw == "FUNCtion1"


def test_math_p4_operator_rejects_math_function_source():
    capabilities = capabilities_for_model("DSOX4034A")

    with pytest.raises(ParameterValidationError, match="channel1"):
        math_operator_commands(
            2,
            "add",
            "math1",
            "channel2",
            capabilities=capabilities,
        )


def test_math_p4_simulator_rejects_arithmetic_cascade_source():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4034a")

    backend.write(":FUNCtion2:OPERation ADD")
    with pytest.raises(SimulatorBackendError, match="analog source1"):
        backend.write(":FUNCtion2:SOURce1 FUNCtion1")


@pytest.mark.parametrize("source", ["math2", "math3"])
def test_math_p4_rejects_self_and_forward_cascade_sources(source):
    capabilities = capabilities_for_model("DSOX4034A")

    with pytest.raises(ParameterValidationError, match="lower than"):
        math_transform_commands(
            2,
            "absolute",
            source,
            capabilities=capabilities,
        )


def test_math_p4_source_capabilities_fail_closed():
    single_function = capabilities_for_model("DSOX2004A")
    four_functions = capabilities_for_model("DSOX4034A")

    assert capabilities_for_model("DSOX3024A").supports_math_goft is True
    assert four_functions.supports_math_cascade is True
    with pytest.raises(ParameterValidationError, match="composite.*not supported"):
        math_transform_commands(
            1,
            "absolute",
            "composite",
            capabilities=four_functions,
        )
    with pytest.raises(ParameterValidationError, match="function sources.*not supported"):
        math_transform_commands(
            1,
            "absolute",
            "math1",
            capabilities=single_function,
        )
    with pytest.raises(ParameterValidationError, match="add, subtract, or multiply"):
        math_composite_source_commands(
            "divide",
            "channel1",
            "channel2",
            capabilities=single_function,
        )
    with pytest.raises(ParameterValidationError, match="not supported"):
        math_composite_source_query_commands(capabilities=four_functions)


@pytest.mark.parametrize(
    ("operation", "token", "readbacks"),
    [
        ("low-pass", "LOWPass", ("LOWP", "LOWPASS")),
        ("high-pass", "HIGHpass", ("HIGH", "HIGHPASS")),
        ("average", "AVERage", ("AVER", "AVERAGE")),
        ("smooth", "SMOoth", ("SMO", "SMOOTH")),
        ("envelope", "ENVelope", ("ENV", "ENVELOPE")),
    ],
)
def test_math_p5_filter_mapping_and_readback(operation, token, readbacks):
    capabilities = capabilities_for_model("DSOX4024A")

    assert math_filter_commands(
        1,
        operation,
        "channel1",
        capabilities=capabilities,
    )[0] == f":FUNCtion1:OPERation {token}"
    for readback in readbacks:
        assert parse_math_filter_operation(f" {readback.swapcase()} ") == operation


@pytest.mark.parametrize(
    ("model", "function", "prefix"),
    [
        ("DSOX2004A", 1, ":FUNCtion"),
        ("DSOX3024A", 1, ":FUNCtion"),
        ("DSOX4024A", 2, ":FUNCtion2"),
    ],
)
def test_math_p5_filter_commands_use_series_dialect(model, function, prefix):
    capabilities = capabilities_for_model(model)

    assert math_filter_commands(
        function,
        "low-pass",
        "channel1",
        cutoff_hz=1e6,
        capabilities=capabilities,
    ) == [
        f"{prefix}:OPERation LOWPass",
        f"{prefix}:SOURce1 CHANnel1",
        f"{prefix}:FREQuency:LOWPass 1000000",
    ]
    assert math_filter_query_commands(
        function, capabilities=capabilities
    ) == [
        f"{prefix}:OPERation?",
        f"{prefix}:SOURce1?",
    ]


def test_math_p5_filter_reuses_composite_and_cascade_sources():
    single_function = capabilities_for_model("DSOX2004A")
    four_functions = capabilities_for_model("DSOX4034A")

    assert math_filter_commands(
        1,
        "high-pass",
        "composite",
        cutoff_hz=1000,
        capabilities=single_function,
    )[1] == ":FUNCtion:SOURce1 GOFT"
    assert math_filter_commands(
        2,
        "average",
        "math1",
        average_count=64,
        capabilities=four_functions,
    )[1] == ":FUNCtion2:SOURce1 FUNCtion1"


def test_math_p5_filter_validation():
    single_function = capabilities_for_model("DSOX2004A")
    four_functions = capabilities_for_model("DSOX4024A")

    with pytest.raises(ParameterValidationError, match="not supported"):
        math_filter_commands(
            1, "average", "channel1", capabilities=single_function
        )
    with pytest.raises(ParameterValidationError, match="greater than zero"):
        math_filter_commands(
            1,
            "low-pass",
            "channel1",
            cutoff_hz=0,
            capabilities=single_function,
        )
    with pytest.raises(ParameterValidationError, match="finite number"):
        math_filter_commands(
            1,
            "high-pass",
            "channel1",
            cutoff_hz=float("inf"),
            capabilities=single_function,
        )
    with pytest.raises(ParameterValidationError, match="power of two"):
        math_filter_commands(
            1,
            "average",
            "channel1",
            average_count=3,
            capabilities=four_functions,
        )
    with pytest.raises(ParameterValidationError, match="integer"):
        math_filter_commands(
            1,
            "average",
            "channel1",
            average_count=True,
            capabilities=four_functions,
        )
    with pytest.raises(ParameterValidationError, match="odd"):
        math_filter_commands(
            1,
            "smooth",
            "channel1",
            smooth_points=8,
            capabilities=four_functions,
        )
    with pytest.raises(ParameterValidationError, match="only valid.*average"):
        math_filter_commands(
            1,
            "envelope",
            "channel1",
            average_count=64,
            capabilities=four_functions,
        )
    assert math_filter_commands(
        1,
        "smooth",
        "channel1",
        smooth_points=9,
        capabilities=four_functions,
    )[-1] == ":FUNCtion1:SMOoth:POINts 9"


def test_math_p5_simulator_round_trips_filters_and_clear():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_math_filter(
        2, "low-pass", "channel1", cutoff_hz=1e6
    )
    low_pass = scope.query_math_filter(2)
    scope.configure_math_filter(
        2, "high-pass", "channel2", cutoff_hz=1000
    )
    high_pass = scope.query_math_filter(2)
    scope.configure_math_filter(
        2, "average", "math1", average_count=64
    )
    average = scope.query_math_filter(2)
    scope.clear_math(2)

    assert low_pass.operation == "low-pass"
    assert low_pass.source == "channel1"
    assert low_pass.cutoff_hz == pytest.approx(1e6)
    assert low_pass.average_count is None
    assert low_pass.smooth_points is None
    assert high_pass.operation == "high-pass"
    assert high_pass.source == "channel2"
    assert high_pass.cutoff_hz == pytest.approx(1000)
    assert average.operation == "average"
    assert average.source == "math1"
    assert average.cutoff_hz is None
    assert average.average_count == 64
    assert average.smooth_points is None
    assert backend.history[-4:] == [
        ":FUNCtion2:OPERation?",
        ":FUNCtion2:SOURce1?",
        ":FUNCtion2:AVERage:COUNt?",
        ":FUNCtion2:CLEar",
    ]
    assert math_clear_command(2, capabilities=scope.capabilities) == (
        ":FUNCtion2:CLEar"
    )
    with pytest.raises(ParameterValidationError, match="not supported"):
        math_clear_command(
            1, capabilities=capabilities_for_model("DSOX2004A")
        )


@pytest.mark.parametrize(
    ("operation", "query_command", "response", "message"),
    [
        (
            "AVERage",
            ":FUNCtion1:AVERage:COUNt?",
            "63.5",
            "Math average count response",
        ),
        (
            "SMOoth",
            ":FUNCtion1:SMOoth:POINts?",
            "8",
            "Math smooth points response",
        ),
    ],
)
def test_math_p5_filter_rejects_invalid_integer_readbacks(
    operation, query_command, response, message
):
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox4024a",
        query_overrides={
            ":FUNCtion1:OPERation?": operation,
            ":FUNCtion1:SOURce1?": "CHAN1",
            query_command: response,
        },
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    with pytest.raises(ChannelResponseError, match=message):
        scope.query_math_filter(1)


@pytest.mark.parametrize(
    ("operation", "token", "readback"),
    [
        ("magnify", "MAGNify", "MAGN"),
        ("trend", "TRENd", "TREN"),
        ("maximum", "MAXimum", "MAX"),
        ("minimum", "MINimum", "MIN"),
        ("peak", "PEAK", "PEAK"),
        ("max-hold", "MAXHold", "MAXH"),
        ("min-hold", "MINHold", "MINH"),
    ],
)
def test_math_p6_visualization_mapping(operation, token, readback):
    capabilities = capabilities_for_model("DSOX4024A")
    options = (
        {"measurement_slot": 1}
        if operation == "trend"
        else {"source": "channel1"}
    )

    assert math_visualization_commands(
        1,
        operation,
        capabilities=capabilities,
        **options,
    )[0] == f":FUNCtion1:OPERation {token}"
    assert parse_math_visualization_operation(
        f" {readback.swapcase()} "
    ) == operation


@pytest.mark.parametrize(
    ("model", "prefix"),
    [
        ("DSOX2004A", ":FUNCtion"),
        ("DSOX3024A", ":FUNCtion"),
    ],
)
def test_math_p6_common_magnify_uses_unindexed_composite_source(model, prefix):
    capabilities = capabilities_for_model(model)

    assert math_visualization_commands(
        1,
        "magnify",
        source="composite",
        capabilities=capabilities,
    ) == [
        f"{prefix}:OPERation MAGNify",
        f"{prefix}:SOURce1 GOFT",
    ]


def test_math_p6_4000x_visualization_cascade_and_capability_rejection():
    four_functions = capabilities_for_model("DSOX4034A")
    single_function = capabilities_for_model("DSOX2004A")
    hold_only = replace(
        four_functions,
        math_filter_operations=frozenset(),
        math_visualization_operations=frozenset({"max-hold"}),
    )

    assert math_visualization_commands(
        2,
        "max-hold",
        source="math1",
        capabilities=four_functions,
    ) == [
        ":FUNCtion2:OPERation MAXHold",
        ":FUNCtion2:SOURce1 FUNCtion1",
    ]
    with pytest.raises(ParameterValidationError, match="not supported"):
        math_visualization_commands(
            1,
            "max-hold",
            source="channel1",
            capabilities=single_function,
        )
    assert math_clear_command(2, capabilities=hold_only) == ":FUNCtion2:CLEar"


def test_math_p6_trend_commands_keep_series_paths_explicit():
    single_function = capabilities_for_model("DSOX3024A")
    four_functions = capabilities_for_model("DSOX4024A")

    assert math_visualization_commands(
        1,
        "trend",
        source="channel1",
        source2="channel2",
        measurement="vratio",
        capabilities=single_function,
    ) == [
        ":FUNCtion:OPERation TRENd",
        ":FUNCtion:SOURce1 CHANnel1",
        ":FUNCtion:SOURce2 CHANnel2",
        ":FUNCtion:TRENd:MEASurement VRATio",
    ]
    assert math_visualization_commands(
        2,
        "trend",
        measurement_slot=3,
        capabilities=four_functions,
    ) == [
        ":FUNCtion2:OPERation TRENd",
        ":FUNCtion2:TRENd:NMEasurement MEAS3",
    ]
    assert parse_math_trend_measurement(" vRaT ") == "vratio"


def test_math_p6_visualization_query_parses_trend_variants():
    single_backend = SimulatorBackend(
        physical_model_id="keysight-dsox2004a",
        query_overrides={
            ":FUNCtion:OPERation?": "TREN",
            ":FUNCtion:SOURce1?": "CHAN1",
            ":FUNCtion:TRENd:MEASurement?": "VRAT",
            ":FUNCtion:SOURce2?": "CHAN2",
        },
    )
    single_scope = Oscilloscope(single_backend)
    single_scope.query_idn()

    single_state = single_scope.query_math_visualization(1)

    assert single_state.operation == "trend"
    assert single_state.source == "channel1"
    assert single_state.source2 == "channel2"
    assert single_state.measurement == "vratio"
    assert single_backend.history[1:] == [
        ":FUNCtion:OPERation?",
        ":FUNCtion:SOURce1?",
        ":FUNCtion:TRENd:MEASurement?",
        ":FUNCtion:SOURce2?",
    ]

    four_backend = SimulatorBackend(
        physical_model_id="keysight-dsox4024a",
        query_overrides={
            ":FUNCtion2:OPERation?": "TREN",
            ":FUNCtion2:TRENd:NMEasurement?": "NONE",
        },
    )
    four_scope = Oscilloscope(four_backend)
    four_scope.query_idn()

    four_state = four_scope.query_math_visualization(2)

    assert four_state.operation == "trend"
    assert four_state.source is None
    assert four_state.measurement is None
    assert four_state.measurement_raw == "NONE"
    assert four_state.measurement_slot is None
    assert four_backend.history[1:] == [
        ":FUNCtion2:OPERation?",
        ":FUNCtion2:TRENd:NMEasurement?",
    ]

    inappropriate_backend = SimulatorBackend(
        physical_model_id="keysight-dsox2004a",
        query_overrides={":FUNCtion:OPERation?": "MAX"},
    )
    inappropriate_scope = Oscilloscope(inappropriate_backend)
    inappropriate_scope.query_idn()

    with pytest.raises(ChannelResponseError, match="'MAX'"):
        inappropriate_scope.query_math_visualization(1)


def test_math_p6_visualization_rejects_inapplicable_arguments():
    single_function = capabilities_for_model("DSOX2004A")
    four_functions = capabilities_for_model("DSOX4024A")

    with pytest.raises(ParameterValidationError, match="source2.*vratio"):
        math_visualization_commands(
            1,
            "trend",
            source="channel1",
            source2="channel2",
            measurement="vavg",
            capabilities=single_function,
        )
    with pytest.raises(ParameterValidationError, match="does not accept"):
        math_visualization_commands(
            2,
            "trend",
            source="channel1",
            measurement_slot=1,
            capabilities=four_functions,
        )
    with pytest.raises(ParameterValidationError, match="only valid.*trend"):
        math_visualization_commands(
            1,
            "magnify",
            source="channel1",
            measurement="vavg",
            capabilities=single_function,
        )
    with pytest.raises(ChannelResponseError, match="UNKNOWN"):
        parse_math_visualization_operation("UNKNOWN")
    assert math_visualization_query_commands(
        2, capabilities=four_functions
    ) == [":FUNCtion2:OPERation?"]


def test_cursor_auto_timebase_plan_keeps_visible_positions():
    result = cursor_auto_timebase_plan(1e-3, 0.0, 0.0, 1e-3)

    assert result.changed is False
    assert result.target_scale_seconds_per_division == pytest.approx(1e-3)
    assert result.commands == (":TIMebase:SCALe?", ":TIMebase:POSition?")


def test_cursor_auto_timebase_plan_widens_for_out_of_range_x2():
    result = cursor_auto_timebase_plan(1e-3, 0.0, 0.0, 0.01)

    assert result.changed is True
    assert result.target_scale_seconds_per_division == pytest.approx(0.0025)
    assert result.commands == (
        ":TIMebase:SCALe?",
        ":TIMebase:POSition?",
        ":TIMebase:SCALe 0.0025",
    )


def test_cursor_auto_timebase_plan_uses_current_position():
    result = cursor_auto_timebase_plan(1e-3, 0.01, 0.009, 0.011)

    assert result.changed is False
    assert result.target_scale_seconds_per_division == pytest.approx(1e-3)


def test_cursor_auto_vertical_plan_keeps_visible_positions():
    result = cursor_auto_vertical_plan(1, 1.0, 0.0, y1_volts=-1.0, y2_volts=1.0)

    assert result.changed is False
    assert result.offset_changed is False
    assert result.target_scale_volts_per_division == pytest.approx(1.0)
    assert result.target_offset_volts == pytest.approx(0.0)
    assert result.commands == (":CHANnel1:SCALe?", ":CHANnel1:OFFSet?")


def test_cursor_auto_vertical_plan_uses_scale_only_when_reasonable():
    result = cursor_auto_vertical_plan(1, 1.0, 0.0, y1_volts=0.0, y2_volts=5.0)

    assert result.changed is True
    assert result.offset_changed is False
    assert result.target_scale_volts_per_division == pytest.approx(5.0 / 3.5)
    assert result.target_offset_volts == pytest.approx(0.0)
    assert result.commands == (
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 1.42857142857",
    )


def test_cursor_auto_vertical_plan_centers_common_positive_waveform_range():
    result = cursor_auto_vertical_plan(1, 0.2, 0.0, y1_volts=0.0, y2_volts=2.5)

    assert result.changed is True
    assert result.offset_changed is True
    assert result.target_scale_volts_per_division == pytest.approx(2.5 / 2.0 / 3.5)
    assert result.target_offset_volts == pytest.approx(1.25)
    assert result.commands == (
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 0.357142857143",
        ":CHANnel1:OFFSet 1.25",
    )


def test_cursor_auto_vertical_plan_moves_offset_to_avoid_coarse_scale():
    result = cursor_auto_vertical_plan(1, 1.0, 0.0, y1_volts=20.0, y2_volts=21.0)

    assert result.changed is True
    assert result.offset_changed is True
    assert result.target_scale_volts_per_division == pytest.approx(1.0)
    assert result.target_offset_volts == pytest.approx(20.5)
    assert result.commands == (
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 1",
        ":CHANnel1:OFFSet 20.5",
    )


def test_cursor_auto_vertical_plan_handles_single_negative_y():
    result = cursor_auto_vertical_plan(1, 0.5, 0.0, y1_volts=-20.0)

    assert result.changed is True
    assert result.offset_changed is True
    assert result.target_scale_volts_per_division == pytest.approx(0.5)
    assert result.target_offset_volts == pytest.approx(-20.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"y1_volts": float("nan")},
        {"y2_volts": float("inf")},
    ],
)
def test_cursor_auto_vertical_plan_rejects_missing_or_nonfinite_y(kwargs):
    with pytest.raises(ParameterValidationError):
        cursor_auto_vertical_plan(1, 1.0, 0.0, **kwargs)


def test_configure_cursor_auto_timebase_sends_scale_before_cursor_commands():
    backend = SimulatorBackend(timebase_scale=1e-3, timebase_position=0.0)
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_cursor(1, 0.0, 0.01, auto_timebase=True)

    assert backend.history[1:4] == [
        ":TIMebase:SCALe?",
        ":TIMebase:POSition?",
        ":TIMebase:SCALe 0.0025",
    ]
    assert backend.history[4:9] == [
        ":MARKer:MODE MANual",
        ":MARKer:X1Y1source CHANnel1",
        ":MARKer:X2Y2source CHANnel1",
        ":MARKer:X1Position 0",
        ":MARKer:X2Position 0.01",
    ]


def test_configure_cursor_auto_vertical_sends_scale_offset_before_cursor_commands():
    backend = SimulatorBackend(channel_scale={1: 1.0}, channel_offset={1: 0.0})
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_cursor(1, 0.0, 1e-3, y1_volts=20.0, y2_volts=21.0, auto_vertical=True)

    assert backend.history[1:5] == [
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 1",
        ":CHANnel1:OFFSet 20.5",
    ]
    assert backend.history[5:10] == [
        ":MARKer:MODE MANual",
        ":MARKer:X1Y1source CHANnel1",
        ":MARKer:X2Y2source CHANnel1",
        ":MARKer:X1Position 0",
        ":MARKer:X2Position 0.001",
    ]


@pytest.mark.parametrize("seconds", [39e-9, 10.1])
def test_trigger_holdoff_rejects_out_of_range(seconds):
    with pytest.raises(ParameterValidationError):
        trigger_holdoff_command(seconds)


def test_setup_file_rejects_quotes_and_wrong_extension():
    with pytest.raises(ParameterValidationError):
        setup_save_command(file_spec='"bad.scp"')
    with pytest.raises(ParameterValidationError):
        setup_save_command(file_spec="bad.txt")


@pytest.mark.parametrize(
    ("method", "arguments", "command"),
    [
        ("save", {"file_spec": "\\usb\\setup.scp"}, ':SAVE:SETup "\\usb\\setup.scp"'),
        ("recall", {"slot": 3}, ":RECall:SETup 3"),
    ],
)
def test_setup_operations_wait_for_completion_with_temporary_timeout(
    monkeypatch, method, arguments, command
):
    backend = FakeBackend(responses={"*OPC?": "1"}, timeout=2000)
    opc_query_timeouts = []
    query = backend.query

    def record_query_timeout(scpi_command):
        opc_query_timeouts.append(backend.timeout)
        return query(scpi_command)

    monkeypatch.setattr(backend, "query", record_query_timeout)
    controller = SetupController(SCPIClient(backend))

    getattr(controller, method)(**arguments)

    assert backend.history == [command, "*OPC?"]
    assert opc_query_timeouts == [15000]
    assert backend.timeout_history == [15000, 2000]
    assert backend.timeout == 2000


@pytest.mark.parametrize(
    ("method", "arguments"),
    [
        ("save", {"slot": 2}),
        ("recall", {"file_spec": "\\usb\\setup.scp"}),
    ],
)
def test_setup_operations_restore_timeout_when_completion_query_raises(
    method, arguments
):
    backend = FakeBackend(responses={}, timeout=2000)
    controller = SetupController(SCPIClient(backend))

    with pytest.raises(FakeBackendError):
        getattr(controller, method)(**arguments)

    assert backend.timeout_history == [15000, 2000]
    assert backend.timeout == 2000


def test_simulator_advanced_state_round_trip():
    backend = SimulatorBackend()
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.set_trigger_holdoff(2e-6)
    assert scope.query_trigger_holdoff() == pytest.approx(2e-6)
    assert ":TRIGger:HOLDoff:RANDom OFF" in backend.history

    scope.configure_cursor(1, 0.0, 1e-3, y1_volts=0.1, y2_volts=0.6)
    cursor = scope.query_cursor()
    assert cursor.mode == "MANUAL"
    assert cursor.x_delta_seconds == pytest.approx(1e-3)
    assert cursor.y_delta_volts == pytest.approx(0.5)

    scope.configure_fft(1, 2, units="vrms", window="flattop", display=True)
    fft = scope.query_fft(1)
    assert fft.source_channel == 2
    assert fft.display is True


def test_simulator_rejects_unit_suffixes_for_advanced_numeric_writes():
    backend = SimulatorBackend()

    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":TRIGger:HOLDoff 1 us")
    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":MARKer:X2Position 1 ms")
    with pytest.raises(SimulatorBackendError, match="must not include unit suffixes"):
        backend.write(":MARKer:Y2Position 0.5 V")


def test_configure_cursor_invalid_x_fails_before_auto_timebase_or_vertical_write():
    backend = SimulatorBackend(timebase_scale=1e-3, channel_scale={1: 1.0})
    scope = Oscilloscope(backend)
    scope.query_idn()

    with pytest.raises(ParameterValidationError, match="--x1 must be a finite number"):
        scope.configure_cursor(1, float("nan"), 0.01, auto_timebase=True, auto_vertical=True, y1_volts=1.0)

    assert not any(":TIMebase:SCALe" in cmd for cmd in backend.history)
    assert not any(":CHANnel1:SCALe" in cmd for cmd in backend.history)
