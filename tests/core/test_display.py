import pytest

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.display import (
    DisplayController,
    annotation_commands,
    annotation_query_commands,
    display_clear_command,
    display_intensity_command,
    display_intensity_query,
    display_label_command,
    display_label_query,
    display_persistence_command,
    display_persistence_query,
    display_vectors_command,
    display_vectors_query,
    parse_annotation_background,
    parse_annotation_color,
    parse_display_label,
    parse_display_intensity,
    parse_display_persistence,
    parse_display_vectors,
    validate_annotation_text,
    validate_annotation_slot,
    validate_display_intensity,
    validate_display_persistence,
)
from scopes_tool_core.errors import ChannelResponseError, ParameterValidationError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scpi import SCPIClient


@pytest.mark.parametrize("raw", ["1", "+1", "ON", " on "])
def test_parse_display_label_enabled(raw):
    assert parse_display_label(raw) is True


@pytest.mark.parametrize("raw", ["0", "+0", "OFF", " off "])
def test_parse_display_label_disabled(raw):
    assert parse_display_label(raw) is False


def test_parse_display_label_rejects_unexpected_response():
    with pytest.raises(ChannelResponseError):
        parse_display_label("maybe")


def test_display_label_command_uses_keysight_display_syntax():
    assert display_label_command(True) == ":DISPlay:LABel ON"
    assert display_label_command(False) == ":DISPlay:LABel OFF"
    assert display_label_query() == ":DISPlay:LABel?"


def test_display_common_commands_use_keysight_display_syntax():
    assert display_clear_command() == ":DISPlay:CLEar"
    assert display_persistence_command("minimum") == ":DISPlay:PERSistence MINimum"
    assert display_persistence_command("inf") == ":DISPlay:PERSistence INFinite"
    assert display_persistence_command(0.5) == ":DISPlay:PERSistence 0.5"
    assert display_persistence_query() == ":DISPlay:PERSistence?"
    assert display_intensity_command(75) == ":DISPlay:INTensity:WAVeform 75"
    assert display_intensity_query() == ":DISPlay:INTensity:WAVeform?"
    assert display_vectors_command(True) == ":DISPlay:VECTors ON"
    assert display_vectors_query() == ":DISPlay:VECTors?"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MIN", ("minimum", None)),
        ("MINimum", ("minimum", None)),
        ("INF", ("infinite", None)),
        ("INFinite", ("infinite", None)),
        ("1.250E+0", (None, 1.25)),
    ],
)
def test_parse_display_persistence(raw, expected):
    assert parse_display_persistence(raw) == expected


@pytest.mark.parametrize("value", ["min", "minimum", "inf", "infinite", 0.1, 60.0])
def test_validate_display_persistence_accepts_supported_values(value):
    mode, seconds = validate_display_persistence(value)
    assert mode in {"minimum", "infinite", None}
    if mode is None:
        assert 0.1 <= seconds <= 60.0


@pytest.mark.parametrize("value", [0.099, 60.1, "bad"])
def test_validate_display_persistence_rejects_bad_values(value):
    with pytest.raises(ParameterValidationError):
        validate_display_persistence(value)


@pytest.mark.parametrize("value", [0, 100])
def test_validate_display_intensity_accepts_boundaries(value):
    assert validate_display_intensity(value) == value


@pytest.mark.parametrize("value", [-1, 101])
def test_validate_display_intensity_rejects_out_of_range(value):
    with pytest.raises(ParameterValidationError):
        validate_display_intensity(value)


def test_parse_display_intensity():
    assert parse_display_intensity("75.0") == 75
    with pytest.raises(ParameterValidationError):
        parse_display_intensity("101")


@pytest.mark.parametrize("raw", ["ON", "1"])
def test_parse_display_vectors_enabled(raw):
    assert parse_display_vectors(raw) is True


@pytest.mark.parametrize("raw", ["OFF", "0"])
def test_parse_display_vectors_disabled(raw):
    assert parse_display_vectors(raw) is False


def test_display_vectors_command_rejects_off():
    with pytest.raises(ParameterValidationError):
        display_vectors_command(False)


def test_annotation_unindexed_commands_omit_position_for_3000x_query():
    capabilities = capabilities_for_model("DSOX3024A")

    assert annotation_query_commands(slot=1, capabilities=capabilities) == [
        ":DISPlay:ANNotation?",
        ":DISPlay:ANNotation:TEXT?",
        ":DISPlay:ANNotation:COLor?",
        ":DISPlay:ANNotation:BACKground?",
    ]
    assert annotation_commands(
        capabilities=capabilities,
        slot=1,
        enabled=True,
        text="lower ok",
        color="red",
        background="opaque",
    ) == [
        ':DISPlay:ANNotation:TEXT "lower ok"',
        ":DISPlay:ANNotation:COLor RED",
        ":DISPlay:ANNotation:BACKground OPAQ",
        ":DISPlay:ANNotation ON",
    ]


def test_annotation_indexed_commands_include_position_for_4000x():
    capabilities = capabilities_for_model("DSOX4024A")

    assert annotation_query_commands(slot=2, capabilities=capabilities) == [
        ":DISPlay:ANNotation2?",
        ":DISPlay:ANNotation2:TEXT?",
        ":DISPlay:ANNotation2:COLor?",
        ":DISPlay:ANNotation2:BACKground?",
        ":DISPlay:ANNotation2:X1Position?",
        ":DISPlay:ANNotation2:Y1Position?",
    ]
    assert annotation_commands(
        capabilities=capabilities,
        slot=2,
        enabled=False,
        clear=True,
        x=10,
        y=20,
    ) == [
        ':DISPlay:ANNotation2:TEXT ""',
        ":DISPlay:ANNotation2:X1Position 10",
        ":DISPlay:ANNotation2:Y1Position 20",
        ":DISPlay:ANNotation2 OFF",
    ]


def test_annotation_slot_uses_profile_slot_count():
    with pytest.raises(ParameterValidationError):
        validate_annotation_slot(2, capabilities_for_model("DSOX3024A"))
    assert validate_annotation_slot(10, capabilities_for_model("DSOX4024A")) == 10


def test_validate_annotation_text_accepts_254_printable_ascii_characters():
    text = "x" * 254

    assert validate_annotation_text(text) == text


def test_validate_annotation_text_rejects_255_characters():
    with pytest.raises(ParameterValidationError, match="at most 254"):
        validate_annotation_text("x" * 255)


@pytest.mark.parametrize("text", ['bad"quote', "bad\nline", "non-ascii-\u00e9"])
def test_validate_annotation_text_rejects_invalid_characters(text):
    with pytest.raises(ParameterValidationError):
        validate_annotation_text(text)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" WHIT ", "WHITE"),
        ("whit", "WHITE"),
        ("WHITE", "WHITE"),
        ("MARK", "MARK"),
        ("DIG", "DIG"),
        ("CH1", "CH1"),
    ],
)
def test_parse_annotation_color_accepts_readback_abbreviations(raw, expected):
    assert parse_annotation_color(raw) == expected


def test_parse_annotation_color_rejects_unknown_readback():
    with pytest.raises(ChannelResponseError):
        parse_annotation_color("BLUE")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("opaq", "OPAQ"),
        ("INV", "INV"),
        ("TRAN", "TRAN"),
    ],
)
def test_parse_annotation_background_accepts_canonical_readback(raw, expected):
    assert parse_annotation_background(raw) == expected


def test_parse_annotation_background_rejects_unknown_readback():
    with pytest.raises(ChannelResponseError):
        parse_annotation_background("transparent")


def test_display_controller_sets_and_queries_label_and_annotation():
    backend = FakeBackend(
        responses={
            ":DISPlay:LABel?": "1",
            ":DISPlay:ANNotation1?": "1",
            ":DISPlay:ANNotation1:TEXT?": '"Note"',
            ":DISPlay:ANNotation1:COLor?": " WHIT ",
            ":DISPlay:ANNotation1:BACKground?": "tran",
            ":DISPlay:ANNotation1:X1Position?": "10",
            ":DISPlay:ANNotation1:Y1Position?": "20",
        }
    )
    controller = DisplayController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    controller.set_label(True)
    assert controller.query_label() is True
    controller.set_annotation_enabled(True)
    controller.set_annotation_text("Note")
    controller.set_annotation_position(10, 20)
    state = controller.query_annotation()

    assert state.enabled is True
    assert state.text == "Note"
    assert state.color == "WHITE"
    assert state.background == "TRAN"
    assert state.x == 10
    assert state.y == 20
    assert backend.history == [
        ":DISPlay:LABel ON",
        ":DISPlay:LABel?",
        ":DISPlay:ANNotation1 ON",
        ':DISPlay:ANNotation1:TEXT "Note"',
        ":DISPlay:ANNotation1:X1Position 10",
        ":DISPlay:ANNotation1:Y1Position 20",
        ":DISPlay:ANNotation1?",
        ":DISPlay:ANNotation1:TEXT?",
        ":DISPlay:ANNotation1:COLor?",
        ":DISPlay:ANNotation1:BACKground?",
        ":DISPlay:ANNotation1:X1Position?",
        ":DISPlay:ANNotation1:Y1Position?",
    ]


def test_display_controller_sets_and_queries_common_display_commands():
    backend = FakeBackend(
        responses={
            ":DISPlay:PERSistence?": "1.000E+0",
            ":DISPlay:INTensity:WAVeform?": "75",
            ":DISPlay:VECTors?": "ON",
        }
    )
    controller = DisplayController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    controller.clear_display()
    controller.set_persistence("minimum")
    persistence = controller.query_persistence()
    controller.set_intensity(75)
    intensity, raw_intensity = controller.query_intensity()
    controller.set_vectors_on()
    vectors, raw_vectors = controller.query_vectors()

    assert persistence.mode is None
    assert persistence.seconds == 1.0
    assert persistence.raw_value == "1.000E+0"
    assert intensity == 75
    assert raw_intensity == "75"
    assert vectors is True
    assert raw_vectors == "ON"
    assert backend.history == [
        ":DISPlay:CLEar",
        ":DISPlay:PERSistence MINimum",
        ":DISPlay:PERSistence?",
        ":DISPlay:INTensity:WAVeform 75",
        ":DISPlay:INTensity:WAVeform?",
        ":DISPlay:VECTors ON",
        ":DISPlay:VECTors?",
    ]


def test_set_annotation_position_valid_x_invalid_y_does_no_write():
    backend = FakeBackend()
    controller = DisplayController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    with pytest.raises(ParameterValidationError, match="annotation y must be in range"):
        controller.set_annotation_position(10, -5)

    assert backend.history == []
