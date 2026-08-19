import pytest

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import ParameterValidationError, TriggerResponseError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.trigger import (
    EdgeTriggerController,
    GlitchTriggerController,
    OPERATION_CONDITION_RUI_ENAB_MASK,
    OPERATION_CONDITION_RUN_MASK,
    OPERATION_CONDITION_WAIT_TRIG_MASK,
    RuntTriggerController,
    TriggerHfRejectController,
    TriggerNoiseRejectController,
    TriggerSweepController,
    TriggerWaitConfig,
    classify_operation_condition,
    edge_trigger_level_command,
    edge_trigger_level_query,
    edge_trigger_slope_command,
    edge_trigger_slope_query,
    edge_trigger_source_command,
    force_trigger_command,
    edge_trigger_source_query,
    glitch_trigger_configure_commands,
    glitch_trigger_query_commands,
    normalize_edge_slope,
    normalize_glitch_polarity,
    normalize_glitch_qualifier,
    normalize_runt_polarity,
    normalize_runt_qualifier,
    parse_edge_slope,
    parse_edge_trigger_source,
    parse_glitch_level,
    parse_glitch_range,
    parse_glitch_source,
    parse_operation_condition,
    parse_trigger_reject_bool,
    parse_trigger_sweep,
    parse_runt_source,
    parse_trigger_float,
    runt_trigger_configure_commands,
    runt_trigger_query_commands,
    wait_for_trigger_completion,
    wait_for_current_trigger_completion,
    trigger_mode_edge_command,
    trigger_mode_glitch_command,
    trigger_mode_runt_command,
    trigger_hf_reject_command,
    trigger_hf_reject_query,
    trigger_noise_reject_command,
    trigger_noise_reject_query,
    trigger_sweep_command,
    trigger_sweep_query,
    normalize_trigger_sweep,
    parse_trigger_mode,
    trigger_mode_serial_command,
    validate_trigger_level,
)


class _StepClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class _SequenceBackend:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0
        self.history = []

    def write(self, command):
        self.history.append(command)

    def query(self, command):
        self.history.append(command)
        index = min(self.index, len(self.values) - 1)
        value = self.values[index]
        if self.index < len(self.values) - 1:
            self.index += 1
        if isinstance(value, Exception):
            raise value
        return value

def test_edge_trigger_commands_use_keysight_syntax():
    assert trigger_mode_edge_command() == ":TRIGger:MODE EDGE"
    assert edge_trigger_source_command(1) == ":TRIGger:EDGE:SOURce CHANnel1"
    assert edge_trigger_source_query() == ":TRIGger:EDGE:SOURce?"
    assert edge_trigger_level_command(0.25) == ":TRIGger:EDGE:LEVel 0.25"
    assert edge_trigger_level_query() == ":TRIGger:EDGE:LEVel?"
    assert edge_trigger_slope_command("POSitive") == ":TRIGger:EDGE:SLOPe POSitive"
    assert edge_trigger_slope_query() == ":TRIGger:EDGE:SLOPe?"


def test_serial_trigger_mode_uses_shared_trigger_mode_parser():
    assert trigger_mode_serial_command(2) == ":TRIGger:MODE SBUS2"
    assert parse_trigger_mode("SBUS1") == "serial1"
    assert parse_trigger_mode("SBUS2") == "serial2"

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("CHAN1", 1),
        ("CHANnel2", 2),
        (" channel4 ", 4),
    ],
)


def test_parse_edge_trigger_source(raw, expected):
    assert parse_edge_trigger_source(raw) == expected

@pytest.mark.parametrize("raw", ["NONE", "EXT", "CHANX", "CHAN0"])


def test_parse_edge_trigger_source_rejects_non_analog_channel(raw):
    with pytest.raises(TriggerResponseError):
        parse_edge_trigger_source(raw)

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("POS", "positive"),
        ("POSitive", "positive"),
        ("NEG", "negative"),
        ("EITH", "either"),
        ("ALT", "alternate"),
    ],
)


def test_parse_edge_slope(raw, expected):
    assert parse_edge_slope(raw) == expected

def test_parse_edge_slope_rejects_unexpected_response():
    with pytest.raises(TriggerResponseError):
        parse_edge_slope("MAYBE")

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("positive", "POSitive"),
        ("rising", "POSitive"),
        ("negative", "NEGative"),
        ("falling", "NEGative"),
        ("either", "EITHer"),
        ("alternate", "ALTernate"),
    ],
)


def test_normalize_edge_slope(raw, expected):
    assert normalize_edge_slope(raw) == expected

def test_normalize_edge_slope_rejects_unknown_slope():
    with pytest.raises(ParameterValidationError):
        normalize_edge_slope("sideways")

@pytest.mark.parametrize("raw, expected", [("2.5E-1", 0.25), (" -1.0 ", -1.0)])


def test_parse_trigger_float(raw, expected):
    assert parse_trigger_float(raw, "level") == expected

@pytest.mark.parametrize("raw", ["MAYBE", "NaN", "INF"])


def test_parse_trigger_float_rejects_unexpected_response(raw):
    with pytest.raises(TriggerResponseError):
        parse_trigger_float(raw, "level")

@pytest.mark.parametrize("value", [0.0, -1.0, "0.25"])


def test_validate_trigger_level_accepts_finite_values(value):
    assert validate_trigger_level(value) == float(value)

@pytest.mark.parametrize("value", [float("inf"), float("nan"), "abc"])


def test_validate_trigger_level_rejects_non_finite_values(value):
    with pytest.raises(ParameterValidationError):
        validate_trigger_level(value)

def test_edge_trigger_controller_configures_and_reads_back_state():
    backend = FakeBackend(
        responses={
            ":TRIGger:EDGE:SOURce?": "CHAN1",
            ":TRIGger:EDGE:LEVel?": "2.5E-1",
            ":TRIGger:EDGE:SLOPe?": "POS",
        }
    )
    controller = EdgeTriggerController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    controller.configure(source_channel=1, level_volts=0.25, slope="positive")
    state = controller.query()

    assert state.source_channel == 1
    assert state.level_volts == 0.25
    assert state.slope == "positive"
    assert backend.history == [
        ":TRIGger:MODE EDGE",
        ":TRIGger:EDGE:SOURce CHANnel1",
        ":TRIGger:EDGE:LEVel 0.25",
        ":TRIGger:EDGE:SLOPe POSitive",
        ":TRIGger:EDGE:SOURce?",
        ":TRIGger:EDGE:LEVel?",
        ":TRIGger:EDGE:SLOPe?",
    ]

def test_edge_trigger_controller_rejects_invalid_channel_before_scpi():
    backend = FakeBackend()
    controller = EdgeTriggerController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    with pytest.raises(ParameterValidationError):
        controller.configure(source_channel=5, level_volts=0.0, slope="positive")

    assert backend.history == []


def test_trigger_sweep_commands_use_keysight_syntax():
    assert trigger_sweep_command("auto") == ":TRIGger:SWEep AUTO"
    assert trigger_sweep_command("normal") == ":TRIGger:SWEep NORMal"
    assert trigger_sweep_query() == ":TRIGger:SWEep?"


def test_normalize_trigger_sweep_accepts_public_values():
    assert normalize_trigger_sweep("auto") == "AUTO"
    assert normalize_trigger_sweep("normal") == "NORMal"


@pytest.mark.parametrize(
    "raw, expected",
    [("AUTO", "auto"), ("NORM", "normal"), ("NORMal", "normal")],
)
def test_parse_trigger_sweep(raw, expected):
    assert parse_trigger_sweep(raw) == expected


def test_trigger_sweep_rejects_invalid_mode_before_scpi():
    backend = FakeBackend()
    controller = TriggerSweepController(SCPIClient(backend))

    with pytest.raises(ParameterValidationError):
        controller.configure("single")

    assert backend.history == []


def test_trigger_sweep_controller_configures_and_queries_state():
    backend = FakeBackend(responses={":TRIGger:SWEep?": "NORM"})
    controller = TriggerSweepController(SCPIClient(backend))

    controller.configure("normal")
    state = controller.query()

    assert state.mode == "normal"
    assert state.raw_value == "NORM"
    assert state.to_json() == {"mode": "normal", "raw_value": "NORM"}
    assert backend.history == [":TRIGger:SWEep NORMal", ":TRIGger:SWEep?"]


def test_trigger_reject_commands_use_keysight_syntax():
    assert trigger_noise_reject_command(True) == ":TRIGger:NREJect ON"
    assert trigger_noise_reject_command(False) == ":TRIGger:NREJect OFF"
    assert trigger_noise_reject_query() == ":TRIGger:NREJect?"
    assert trigger_hf_reject_command(True) == ":TRIGger:HFReject ON"
    assert trigger_hf_reject_command(False) == ":TRIGger:HFReject OFF"
    assert trigger_hf_reject_query() == ":TRIGger:HFReject?"


@pytest.mark.parametrize("raw, expected", [("1", True), ("0", False)])
def test_parse_trigger_reject_bool(raw, expected):
    assert parse_trigger_reject_bool(raw) is expected


@pytest.mark.parametrize("raw", ["ON", "OFF", "true", ""])
def test_parse_trigger_reject_bool_rejects_unexpected_readback(raw):
    with pytest.raises(TriggerResponseError):
        parse_trigger_reject_bool(raw)


@pytest.mark.parametrize(
    "controller_class, command, query",
    [
        (TriggerNoiseRejectController, ":TRIGger:NREJect ON", ":TRIGger:NREJect?"),
        (TriggerHfRejectController, ":TRIGger:HFReject ON", ":TRIGger:HFReject?"),
    ],
)
def test_trigger_reject_controllers_configure_and_query_state(
    controller_class, command, query
):
    backend = FakeBackend(responses={query: "1"})
    controller = controller_class(SCPIClient(backend))

    controller.configure(True)
    state = controller.query()

    assert state.enabled is True
    assert state.raw_value == "1"
    assert state.to_json() == {"enabled": True, "raw_value": "1"}
    assert backend.history == [command, query]


@pytest.mark.parametrize(
    "controller_class",
    [TriggerNoiseRejectController, TriggerHfRejectController],
)
def test_trigger_reject_controllers_reject_non_bool_before_scpi(controller_class):
    backend = FakeBackend()
    controller = controller_class(SCPIClient(backend))

    with pytest.raises(ParameterValidationError):
        controller.configure("true")

    assert backend.history == []


def test_glitch_trigger_less_than_sequence_uses_keysight_pulse_width_syntax():
    commands = glitch_trigger_configure_commands(
        channel=1,
        polarity="positive",
        qualifier="less-than",
        time_seconds=1e-6,
        capabilities=capabilities_for_model("DSOX4024A"),
    )

    assert commands == [
        ":TRIGger:MODE GLITch",
        ":TRIGger:GLITch:SOURce CHANnel1",
        ":TRIGger:GLITch:POLarity POSitive",
        ":TRIGger:GLITch:LESSthan 1e-06",
        ":TRIGger:GLITch:QUALifier LESSthan",
    ]


def test_glitch_trigger_greater_than_sequence_includes_optional_level_before_polarity():
    commands = glitch_trigger_configure_commands(
        channel=1,
        polarity="negative",
        qualifier="greater-than",
        time_seconds=5e-6,
        level_volts=0.5,
        capabilities=capabilities_for_model("DSOX4024A"),
    )

    assert commands == [
        ":TRIGger:MODE GLITch",
        ":TRIGger:GLITch:SOURce CHANnel1",
        ":TRIGger:GLITch:LEVel 0.5,CHANnel1",
        ":TRIGger:GLITch:POLarity NEGative",
        ":TRIGger:GLITch:GREaterthan 5e-06",
        ":TRIGger:GLITch:QUALifier GREaterthan",
    ]


def test_glitch_trigger_range_sequence_maps_cli_max_then_min_to_scpi_range():
    commands = glitch_trigger_configure_commands(
        channel=1,
        polarity="positive",
        qualifier="range",
        min_time_seconds=1e-6,
        max_time_seconds=10e-6,
        capabilities=capabilities_for_model("DSOX4024A"),
    )

    assert commands == [
        ":TRIGger:MODE GLITch",
        ":TRIGger:GLITch:SOURce CHANnel1",
        ":TRIGger:GLITch:POLarity POSitive",
        ":TRIGger:GLITch:RANGe 1e-05,1e-06",
        ":TRIGger:GLITch:QUALifier RANGe",
    ]


def test_glitch_trigger_query_sequence_is_explicit_and_non_acquisition():
    assert trigger_mode_glitch_command() == ":TRIGger:MODE GLITch"
    assert glitch_trigger_query_commands() == [
        ":TRIGger:MODE?",
        ":TRIGger:GLITch:SOURce?",
        ":TRIGger:GLITch:POLarity?",
        ":TRIGger:GLITch:QUALifier?",
        ":TRIGger:GLITch:GREaterthan?",
        ":TRIGger:GLITch:LESSthan?",
        ":TRIGger:GLITch:RANGe?",
        ":TRIGger:GLITch:LEVel?",
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"qualifier": "less-than"},
        {"qualifier": "greater-than"},
        {"qualifier": "range", "min_time_seconds": 1e-6},
        {"qualifier": "range", "max_time_seconds": 10e-6},
        {"qualifier": "range", "time_seconds": 1e-6},
        {"qualifier": "range", "min_time_seconds": 2e-6, "max_time_seconds": 1e-6},
        {"qualifier": "less-than", "time_seconds": 1e-6, "min_time_seconds": 5e-7},
    ],
)
def test_glitch_trigger_rejects_invalid_timing_combinations(kwargs):
    with pytest.raises(ParameterValidationError):
        glitch_trigger_configure_commands(
            channel=1,
            polarity="positive",
            capabilities=capabilities_for_model("DSOX4024A"),
            **kwargs,
        )


def test_glitch_trigger_rejects_invalid_channel_before_scpi():
    backend = FakeBackend()
    controller = GlitchTriggerController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    with pytest.raises(ParameterValidationError):
        controller.configure(
            channel=5,
            polarity="positive",
            qualifier="less-than",
            time_seconds=1e-6,
        )

    assert backend.history == []


@pytest.mark.parametrize("value", ["positive", "negative"])
def test_normalize_glitch_polarity_accepts_public_values(value):
    assert normalize_glitch_polarity(value) in {"POSitive", "NEGative"}


@pytest.mark.parametrize("value", ["greater-than", "less-than", "range"])
def test_normalize_glitch_qualifier_accepts_public_values(value):
    assert normalize_glitch_qualifier(value) in {"GREaterthan", "LESSthan", "RANGe"}


@pytest.mark.parametrize("value", ["sideways", ""])
def test_normalize_glitch_polarity_rejects_invalid_values(value):
    with pytest.raises(ParameterValidationError):
        normalize_glitch_polarity(value)


@pytest.mark.parametrize("value", ["between", ""])
def test_normalize_glitch_qualifier_rejects_invalid_values(value):
    with pytest.raises(ParameterValidationError):
        normalize_glitch_qualifier(value)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("CHAN1", ("channel", 1, None)),
        ("CHANnel2", ("channel", 2, None)),
        ("DIGital7", ("digital", None, 7)),
        ("EXT", ("external", None, None)),
        ("NONE", ("none", None, None)),
    ],
)
def test_parse_glitch_source_is_tolerant_of_current_instrument_state(raw, expected):
    assert parse_glitch_source(raw) == expected


def test_parse_glitch_level_treats_none_as_absent():
    assert parse_glitch_level("NONE") is None


def test_parse_glitch_range_maps_scpi_max_min_to_cli_min_max():
    assert parse_glitch_range("+1.00000000E-05,+1.00000000E-06") == (1e-6, 1e-5)


def test_glitch_trigger_controller_configures_and_queries_state():
    backend = FakeBackend(
        responses={
            ":TRIGger:MODE?": "GLIT",
            ":TRIGger:GLITch:SOURce?": "CHAN1",
            ":TRIGger:GLITch:POLarity?": "POS",
            ":TRIGger:GLITch:QUALifier?": "LESS",
            ":TRIGger:GLITch:GREaterthan?": "+1.00000000E-06",
            ":TRIGger:GLITch:LESSthan?": "+1.00000000E-06",
            ":TRIGger:GLITch:RANGe?": "+1.00000000E-05,+1.00000000E-06",
            ":TRIGger:GLITch:LEVel?": "NONE",
        }
    )
    controller = GlitchTriggerController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    controller.configure(
        channel=1,
        polarity="positive",
        qualifier="less-than",
        time_seconds=1e-6,
    )
    state = controller.query()

    assert state.mode == "glitch"
    assert state.source_kind == "channel"
    assert state.channel == 1
    assert state.polarity == "positive"
    assert state.qualifier == "less-than"
    assert state.level_volts is None
    assert state.range_min_seconds == pytest.approx(1e-6)
    assert state.range_max_seconds == pytest.approx(1e-5)
    assert backend.history == [
        ":TRIGger:MODE GLITch",
        ":TRIGger:GLITch:SOURce CHANnel1",
        ":TRIGger:GLITch:POLarity POSitive",
        ":TRIGger:GLITch:LESSthan 1e-06",
        ":TRIGger:GLITch:QUALifier LESSthan",
        *glitch_trigger_query_commands(),
    ]


def test_runt_trigger_none_sequence_skips_time_command():
    commands = runt_trigger_configure_commands(
        channel=1,
        polarity="either",
        qualifier="none",
        low_level_volts=-0.5,
        high_level_volts=0.5,
        capabilities=capabilities_for_model("DSOX4024A"),
    )

    assert commands == [
        ":TRIGger:MODE RUNT",
        ":TRIGger:RUNT:SOURce CHANnel1",
        ":TRIGger:LEVel:LOW -0.5,CHANnel1",
        ":TRIGger:LEVel:HIGH 0.5,CHANnel1",
        ":TRIGger:RUNT:POLarity EITHer",
        ":TRIGger:RUNT:QUALifier NONE",
    ]


@pytest.mark.parametrize(
    "qualifier, expected_time_command, expected_qualifier_command",
    [
        ("greater-than", ":TRIGger:RUNT:TIME 5e-06", ":TRIGger:RUNT:QUALifier GREaterthan"),
        ("less-than", ":TRIGger:RUNT:TIME 5e-06", ":TRIGger:RUNT:QUALifier LESSthan"),
    ],
)
def test_runt_trigger_timed_sequences(qualifier, expected_time_command, expected_qualifier_command):
    commands = runt_trigger_configure_commands(
        channel=1,
        polarity="positive",
        qualifier=qualifier,
        time_seconds=5e-6,
        low_level_volts=-0.25,
        high_level_volts=0.75,
        capabilities=capabilities_for_model("DSOX4024A"),
    )

    assert commands == [
        ":TRIGger:MODE RUNT",
        ":TRIGger:RUNT:SOURce CHANnel1",
        ":TRIGger:LEVel:LOW -0.25,CHANnel1",
        ":TRIGger:LEVel:HIGH 0.75,CHANnel1",
        ":TRIGger:RUNT:POLarity POSitive",
        expected_time_command,
        expected_qualifier_command,
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"qualifier": "greater-than", "low_level_volts": -0.5, "high_level_volts": 0.5},
        {
            "qualifier": "less-than",
            "time_seconds": 1e-6,
            "low_level_volts": 0.5,
            "high_level_volts": 0.5,
        },
        {
            "qualifier": "none",
            "time_seconds": 1e-6,
            "low_level_volts": -0.5,
            "high_level_volts": 0.5,
        },
        {
            "qualifier": "none",
            "low_level_volts": float("nan"),
            "high_level_volts": 0.5,
        },
    ],
)
def test_runt_trigger_rejects_invalid_timing_and_levels(kwargs):
    with pytest.raises(ParameterValidationError):
        runt_trigger_configure_commands(
            channel=1,
            polarity="positive",
            capabilities=capabilities_for_model("DSOX4024A"),
            **kwargs,
        )


def test_runt_trigger_rejects_invalid_channel_before_scpi():
    backend = FakeBackend()
    controller = RuntTriggerController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    with pytest.raises(ParameterValidationError):
        controller.configure(
            channel=5,
            polarity="positive",
            qualifier="none",
            low_level_volts=-0.5,
            high_level_volts=0.5,
        )

    assert backend.history == []


@pytest.mark.parametrize("value", ["positive", "negative", "either"])
def test_normalize_runt_polarity_accepts_public_values(value):
    assert normalize_runt_polarity(value) in {"POSitive", "NEGative", "EITHer"}


@pytest.mark.parametrize("value", ["greater-than", "less-than", "none"])
def test_normalize_runt_qualifier_accepts_public_values(value):
    assert normalize_runt_qualifier(value) in {"GREaterthan", "LESSthan", "NONE"}


@pytest.mark.parametrize("value", ["sideways", ""])
def test_normalize_runt_polarity_rejects_invalid_values(value):
    with pytest.raises(ParameterValidationError):
        normalize_runt_polarity(value)


@pytest.mark.parametrize("value", ["range", "greater_than", ""])
def test_normalize_runt_qualifier_rejects_invalid_values(value):
    with pytest.raises(ParameterValidationError):
        normalize_runt_qualifier(value)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("CHAN1", ("channel", 1)),
        ("CHANnel2", ("channel", 2)),
        ("DIGital7", (None, None)),
        ("EXT", (None, None)),
    ],
)
def test_parse_runt_source_preserves_only_safe_analog_channels(raw, expected):
    assert parse_runt_source(raw) == expected


def test_runt_trigger_query_sequence_is_explicit_and_non_acquisition():
    assert trigger_mode_runt_command() == ":TRIGger:MODE RUNT"
    assert runt_trigger_query_commands() == [
        ":TRIGger:MODE?",
        ":TRIGger:RUNT:SOURce?",
        ":TRIGger:RUNT:POLarity?",
        ":TRIGger:RUNT:QUALifier?",
        ":TRIGger:RUNT:TIME?",
    ]


def test_runt_trigger_controller_configures_and_queries_analog_state():
    backend = FakeBackend(
        responses={
            ":TRIGger:MODE?": "RUNT",
            ":TRIGger:RUNT:SOURce?": "CHAN1",
            ":TRIGger:RUNT:POLarity?": "EITH",
            ":TRIGger:RUNT:QUALifier?": "NONE",
            ":TRIGger:RUNT:TIME?": "+1.00000000E-06",
            ":TRIGger:LEVel:LOW? CHANnel1": "-5.00000000E-01",
            ":TRIGger:LEVel:HIGH? CHANnel1": "+5.00000000E-01",
        }
    )
    controller = RuntTriggerController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    controller.configure(
        channel=1,
        polarity="either",
        qualifier="none",
        low_level_volts=-0.5,
        high_level_volts=0.5,
    )
    state = controller.query()

    assert state.mode == "runt"
    assert state.source_kind == "channel"
    assert state.channel == 1
    assert state.polarity == "either"
    assert state.qualifier == "none"
    assert state.time_seconds == pytest.approx(1e-6)
    assert state.low_level_volts == pytest.approx(-0.5)
    assert state.high_level_volts == pytest.approx(0.5)
    assert backend.history == [
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


def test_runt_trigger_query_skips_levels_for_unsafe_source():
    backend = FakeBackend(
        responses={
            ":TRIGger:MODE?": "RUNT",
            ":TRIGger:RUNT:SOURce?": "DIGital7",
            ":TRIGger:RUNT:POLarity?": "POS",
            ":TRIGger:RUNT:QUALifier?": "GRE",
            ":TRIGger:RUNT:TIME?": "+1.00000000E-06",
        }
    )
    controller = RuntTriggerController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    state = controller.query()

    assert state.source == "DIGital7"
    assert state.source_kind is None
    assert state.channel is None
    assert state.low_level_volts is None
    assert state.high_level_volts is None
    assert backend.history == [
        ":TRIGger:MODE?",
        ":TRIGger:RUNT:SOURce?",
        ":TRIGger:RUNT:POLarity?",
        ":TRIGger:RUNT:QUALifier?",
        ":TRIGger:RUNT:TIME?",
    ]


def test_force_trigger_command_returns_expected_scpi():
    assert force_trigger_command() == ":TRIGger:FORCe"


def test_force_trigger_command_writes_only_force_trigger_scpi():
    backend = FakeBackend()
    client = SCPIClient(backend)

    client.write(force_trigger_command())

    assert backend.history == [":TRIGger:FORCe"]


def test_operation_condition_classifier_is_conservative_for_live_values():
    assert parse_operation_condition("+1") == 1
    assert classify_operation_condition(0, profile="live") == "unknown"
    assert classify_operation_condition(1, profile="live") == "unknown"
    assert classify_operation_condition(24, profile="live") == "unknown"


def test_operation_condition_masks_match_x_series_register_bits():
    assert OPERATION_CONDITION_RUN_MASK == 8
    assert OPERATION_CONDITION_RUI_ENAB_MASK == 16
    assert OPERATION_CONDITION_WAIT_TRIG_MASK == 32


@pytest.mark.parametrize("profile", ["2000x", "3000x", "4000x", "simulator"])
@pytest.mark.parametrize("value", [8, 24, 40, 56])
def test_operation_condition_classifier_x_series_run_bit_set_is_pending(profile, value):
    assert classify_operation_condition(value, profile=profile) == "pending"


@pytest.mark.parametrize("profile", ["2000x", "3000x", "4000x", "simulator"])
@pytest.mark.parametrize("value", [0, 16, 32, 48])
def test_operation_condition_classifier_x_series_run_bit_clear_is_complete(profile, value):
    assert classify_operation_condition(value, profile=profile) == "complete"


@pytest.mark.parametrize("value", [56, 40, 32, 24, 48, 16, 8, 0])
def test_operation_condition_classifier_unsupported_live_values_remain_unknown(value):
    assert classify_operation_condition(value, profile="live") == "unknown"


def test_wait_for_trigger_completion_natural_path_uses_single_and_poll():
    clock = _StepClock()
    backend = FakeBackend(responses={":OPERegister:CONDition?": "48"})

    result = wait_for_trigger_completion(
        SCPIClient(backend),
        TriggerWaitConfig(100, clock=clock, sleep=clock.sleep),
        classifier_profile="simulator",
    )

    assert result.outcome == "natural"
    assert result.capture_allowed is True
    assert result.condition_values == (48,)
    assert backend.history == [":SINGle", ":OPERegister:CONDition?"]


def test_wait_for_current_trigger_completion_cancels_without_arming_single():
    clock = _StepClock()
    backend = FakeBackend(responses={":OPERegister:CONDition?": "56"})

    result = wait_for_current_trigger_completion(
        SCPIClient(backend),
        TriggerWaitConfig(100, clock=clock, sleep=clock.sleep),
        classifier_profile="simulator",
        stop_requested=lambda: True,
    )

    assert result.outcome == "cancelled"
    assert result.capture_allowed is False
    assert backend.history == [":OPERegister:CONDition?"]


def test_wait_for_trigger_completion_timeout_without_real_sleep():
    clock = _StepClock()
    backend = FakeBackend(responses={":OPERegister:CONDition?": "56"})

    result = wait_for_trigger_completion(
        SCPIClient(backend),
        TriggerWaitConfig(2, poll_interval_ms=1, clock=clock, sleep=clock.sleep),
        classifier_profile="simulator",
    )

    assert result.outcome == "timeout"
    assert result.capture_allowed is False
    assert result.timed_out is True
    assert result.poll_count == 3


@pytest.mark.parametrize("profile", ["2000x", "3000x", "4000x"])
def test_wait_for_trigger_completion_x_series_polls_until_run_bit_clears(profile):
    clock = _StepClock()
    backend = _SequenceBackend(["40", "40", "32"])

    result = wait_for_trigger_completion(
        SCPIClient(backend),
        TriggerWaitConfig(10, poll_interval_ms=1, clock=clock, sleep=clock.sleep),
        classifier_profile=profile,
    )

    assert result.outcome == "natural"
    assert result.capture_allowed is True
    assert result.raw_values == ("40", "40", "32")
    assert result.condition_values == (40, 40, 32)
    assert backend.history == [
        ":SINGle",
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
    ]


def test_wait_for_trigger_completion_4000x_force_after_timeout_then_completes():
    clock = _StepClock()
    backend = _SequenceBackend(["56", "56", "56", "56", "48"])

    result = wait_for_trigger_completion(
        SCPIClient(backend),
        TriggerWaitConfig(
            2,
            poll_interval_ms=1,
            force_on_timeout=True,
            clock=clock,
            sleep=clock.sleep,
        ),
        classifier_profile="4000x",
    )

    assert result.outcome == "forced"
    assert result.forced is True
    assert result.timed_out is False
    assert result.capture_allowed is True
    assert result.raw_values == ("56", "56", "56", "56", "48")
    assert backend.history == [
        ":SINGle",
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
        ":TRIGger:FORCe",
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
    ]


def test_wait_for_trigger_completion_4000x_force_after_timeout_then_times_out():
    clock = _StepClock()
    backend = _SequenceBackend(["56"])

    result = wait_for_trigger_completion(
        SCPIClient(backend),
        TriggerWaitConfig(
            2,
            poll_interval_ms=1,
            force_on_timeout=True,
            clock=clock,
            sleep=clock.sleep,
        ),
        classifier_profile="4000x",
    )

    assert result.outcome == "timeout"
    assert result.forced is True
    assert result.timed_out is True
    assert result.capture_allowed is False
    assert ":TRIGger:FORCe" in backend.history


def test_wait_for_trigger_completion_unknown_blocks_capture():
    clock = _StepClock()
    backend = FakeBackend(responses={":OPERegister:CONDition?": "+24"})

    result = wait_for_trigger_completion(
        SCPIClient(backend),
        TriggerWaitConfig(100, clock=clock, sleep=clock.sleep),
        classifier_profile="live",
    )

    assert result.outcome == "unknown"
    assert result.capture_allowed is False
    assert result.raw_values == ("+24",)
    assert result.condition_values == (24,)


def test_wait_for_trigger_completion_query_failure_is_unknown_without_force():
    clock = _StepClock()
    backend = _SequenceBackend([RuntimeError("configured query failure")])

    result = wait_for_trigger_completion(
        SCPIClient(backend),
        TriggerWaitConfig(
            100,
            force_on_timeout=True,
            clock=clock,
            sleep=clock.sleep,
        ),
        classifier_profile="4000x",
    )

    assert result.outcome == "unknown"
    assert result.forced is False
    assert result.capture_allowed is False
    assert result.raw_values == ()
    assert result.condition_values == ()
    assert "configured query failure" in result.error
    assert backend.history == [":SINGle", ":OPERegister:CONDition?"]
