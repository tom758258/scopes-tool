from dataclasses import replace

import pytest

from scopes_tool_core.math import (
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
)

from scopes_tool_core.capabilities import capabilities_for_model

from scopes_tool_core.errors import (
    ChannelResponseError,
    ParameterValidationError,
)

from scopes_tool_core.scope import Oscilloscope

from scopes_tool_core.simulator_backend import (
    SimulatorBackend,
    SimulatorBackendError,
)

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
