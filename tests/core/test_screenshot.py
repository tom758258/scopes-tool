import pytest

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import ParameterValidationError, ScreenshotResponseError
from scopes_tool_core.fake_backend import FakeBackend, FakeBackendError
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.screenshot import (
    BMP_SIGNATURE,
    HardcopyState,
    PNG_SIGNATURE,
    ScreenshotCapture,
    ScreenshotController,
    ScreenshotOptions,
    hardcopy_screen_dump_data_query,
    hardcopy_layout_command,
    hardcopy_palette_command,
    hardcopy_inksaver_command,
    hardcopy_inksaver_for_background,
    hardcopy_inksaver_query,
    normalize_hardcopy_layout,
    normalize_hardcopy_palette,
    normalize_screenshot_format,
    normalize_screenshot_background,
    parse_hardcopy_area,
    parse_hardcopy_layout,
    parse_hardcopy_palette,
    parse_hardcopy_inksaver,
    parse_screenshot_format,
    screenshot_bytes_from_values,
    screenshot_data_query,
    write_screenshot_png,
)


PNG_BYTES = PNG_SIGNATURE + b"\x00\x00\x00\rIHDR"


def test_screenshot_command_uses_keysight_display_data_syntax():
    assert screenshot_data_query() == ":DISPlay:DATA? PNG, COLor"
    assert hardcopy_inksaver_query() == ":HARDcopy:INKSaver?"
    assert hardcopy_inksaver_command(False) == ":HARDcopy:INKSaver OFF"
    assert hardcopy_inksaver_command(True) == ":HARDcopy:INKSaver ON"


def test_screenshot_background_options_map_to_inksaver_state():
    assert normalize_screenshot_background("BLACK") == "black"
    assert normalize_screenshot_background("white") == "white"
    assert hardcopy_inksaver_for_background("black") is False
    assert hardcopy_inksaver_for_background("white") is True


def test_screenshot_background_rejects_unknown_value():
    with pytest.raises(ParameterValidationError):
        normalize_screenshot_background("blue")


def test_parse_hardcopy_inksaver():
    assert parse_hardcopy_inksaver("0") is False
    assert parse_hardcopy_inksaver("1") is True
    with pytest.raises(ScreenshotResponseError):
        parse_hardcopy_inksaver("ON")


@pytest.mark.parametrize(
    ("parser", "response", "expected"),
    [
        (parse_hardcopy_inksaver, "INKS 1", True),
        (parse_hardcopy_inksaver, "0", False),
        (parse_hardcopy_palette, "COL", "color"),
        (parse_hardcopy_palette, "GRAY", "grayscale"),
        (parse_hardcopy_palette, "NONE", "none"),
        (parse_hardcopy_layout, "LAND", "landscape"),
        (parse_hardcopy_layout, "PORT", "portrait"),
        (parse_hardcopy_area, "SCR", "screen"),
        (parse_screenshot_format, "BMP8bit", "bmp8bit"),
    ],
)
def test_hardcopy_parsers_accept_compact_readbacks(parser, response, expected):
    assert parser(response) == expected


@pytest.mark.parametrize(
    ("parser", "response"),
    [
        (parse_hardcopy_inksaver, "ON"),
        (parse_hardcopy_palette, "RAINBOW"),
        (parse_hardcopy_layout, "SQUARE"),
        (parse_hardcopy_area, "PLOT"),
        (parse_screenshot_format, "JPEG"),
    ],
)
def test_hardcopy_parsers_reject_malformed_readbacks(parser, response):
    with pytest.raises(ScreenshotResponseError):
        parser(response)


def test_screenshot_option_normalizers_are_strict():
    assert normalize_screenshot_format("BMP8BIT") == "bmp8bit"
    assert normalize_hardcopy_palette("GRAYScale") == "grayscale"
    assert normalize_hardcopy_layout("LANDSCAPE") == "landscape"
    with pytest.raises(ParameterValidationError):
        normalize_screenshot_format("jpeg")


@pytest.mark.parametrize(
    ("palette", "command"),
    [
        ("color", ":HARDcopy:PALette COLor"),
        ("grayscale", ":HARDcopy:PALette GRAYscale"),
        ("none", ":HARDcopy:PALette NONE"),
    ],
)
def test_hardcopy_palette_commands(palette, command):
    assert hardcopy_palette_command(palette) == command


@pytest.mark.parametrize(
    ("layout", "command"),
    [
        ("landscape", ":HARDcopy:LAYout LANDscape"),
        ("portrait", ":HARDcopy:LAYout PORTrait"),
    ],
)
def test_hardcopy_layout_commands(layout, command):
    assert hardcopy_layout_command(layout) == command


def test_screenshot_bytes_from_values_validates_png_signature():
    assert screenshot_bytes_from_values(PNG_BYTES) == PNG_BYTES


@pytest.mark.parametrize("values", [b"", b"not png"])
def test_screenshot_bytes_from_values_rejects_invalid_png(values):
    with pytest.raises(ScreenshotResponseError):
        screenshot_bytes_from_values(values)


def test_screenshot_bytes_from_values_rejects_out_of_range_byte():
    with pytest.raises(ScreenshotResponseError):
        screenshot_bytes_from_values([256])


def test_screenshot_controller_captures_png_data_with_temporary_timeout():
    backend = FakeBackend(
        responses={":HARDcopy:INKSaver?": "1"},
        binary_responses={":DISPlay:DATA? PNG, COLor": list(PNG_BYTES)},
        timeout=2000,
    )
    controller = ScreenshotController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    capture = controller.capture()

    assert capture.format_name == "PNG"
    assert capture.palette == "COLor"
    assert capture.background == "black"
    assert capture.data == PNG_BYTES
    assert backend.history == [
        ":HARDcopy:INKSaver?",
        ":HARDcopy:INKSaver OFF",
        ":DISPlay:DATA? PNG, COLor",
        ":HARDcopy:INKSaver ON",
    ]
    assert backend.binary_query_kwargs == [{"datatype": "B"}]
    assert backend.timeout_history == [10000, 2000]
    assert backend.timeout == 2000


def test_screenshot_controller_supports_white_background():
    backend = FakeBackend(
        responses={":HARDcopy:INKSaver?": "0"},
        binary_responses={":DISPlay:DATA? PNG, COLor": list(PNG_BYTES)},
    )
    controller = ScreenshotController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))

    capture = controller.capture(background="white")

    assert capture.background == "white"
    assert backend.history == [
        ":HARDcopy:INKSaver?",
        ":HARDcopy:INKSaver ON",
        ":DISPlay:DATA? PNG, COLor",
        ":HARDcopy:INKSaver OFF",
    ]


@pytest.mark.parametrize(
    ("format_name", "payload", "query"),
    [
        ("png", PNG_BYTES, ":HCOPY:SDUMp:DATA? PNG"),
        ("bmp", BMP_SIGNATURE + b"bmp", ":HCOPY:SDUMp:DATA? BMP"),
        ("bmp8bit", BMP_SIGNATURE + b"bmp8", ":HCOPY:SDUMp:DATA? BMP8bit"),
    ],
)
def test_screenshot_controller_uses_explicit_4000x_screen_dump_format(
    format_name, payload, query
):
    backend = FakeBackend(
        responses={":HARDcopy:INKSaver?": "0"},
        binary_responses={query: list(payload)},
    )
    controller = ScreenshotController(
        SCPIClient(backend), capabilities_for_model("DSOX4024A")
    )

    capture = controller.capture(options=ScreenshotOptions(format=format_name))

    assert capture.data == payload
    assert query in backend.history
    assert hardcopy_screen_dump_data_query(format_name) == query


def test_screenshot_controller_applies_hardcopy_appearance_before_capture():
    query = ":HCOPY:SDUMp:DATA? PNG"
    backend = FakeBackend(binary_responses={query: list(PNG_BYTES)})
    controller = ScreenshotController(
        SCPIClient(backend), capabilities_for_model("DSOX4024A")
    )

    controller.capture(
        options=ScreenshotOptions(
            ink_saver=True, palette="grayscale", layout="landscape"
        )
    )

    assert backend.history == [
        ":HARDcopy:INKSaver ON",
        ":HARDcopy:PALette GRAYscale",
        ":HARDcopy:LAYout LANDscape",
        query,
    ]


def test_screenshot_controller_queries_structured_hardcopy_state():
    backend = FakeBackend(
        responses={
            ":HARDcopy:AREA?": "SCR",
            ":HARDcopy:INKSaver?": "INKS 1",
            ":HARDcopy:PALette?": "COL",
            ":HARDcopy:LAYout?": "PORT",
            ":HCOPY:SDUMp:FORMat?": "BMP8bit",
        }
    )
    controller = ScreenshotController(
        SCPIClient(backend), capabilities_for_model("DSOX4024A")
    )

    state = controller.query_hardcopy_state()

    assert state == HardcopyState(
        area="screen",
        ink_saver=True,
        palette="color",
        layout="portrait",
        format="bmp8bit",
        raw_area="SCR",
        raw_ink_saver="INKS 1",
        raw_palette="COL",
        raw_layout="PORT",
        raw_format="BMP8bit",
    )


def test_screenshot_controller_rejects_disabled_capability():
    capabilities = capabilities_for_model("DSOX4024A")
    disabled = capabilities.__class__(
        series=capabilities.series,
        analog_channels=capabilities.analog_channels,
        default_waveform_points=capabilities.default_waveform_points,
        safe_max_waveform_points=capabilities.safe_max_waveform_points,
        supports_word_format=capabilities.supports_word_format,
        supports_raw_points_mode=capabilities.supports_raw_points_mode,
        supports_measurements=capabilities.supports_measurements,
        supports_delay_measurement=capabilities.supports_delay_measurement,
        screenshot_formats=(),
        supports_segmented_memory=capabilities.supports_segmented_memory,
        supports_serial_decode=capabilities.supports_serial_decode,
    )
    backend = FakeBackend()
    controller = ScreenshotController(SCPIClient(backend), disabled)

    with pytest.raises(ParameterValidationError):
        controller.capture()

    assert backend.history == []


def test_screenshot_export_writes_png(tmp_path):
    capture = ScreenshotCapture(
        format_name="PNG",
        palette="COLor",
        data=PNG_BYTES,
        background="black",
    )
    output_path = tmp_path / "screens" / "screen.png"

    written = write_screenshot_png(capture, output_path)

    assert written == output_path
    assert output_path.read_bytes() == PNG_BYTES


@pytest.mark.parametrize("options, query", [
    (ScreenshotOptions(), ":DISPlay:DATA? PNG, COLor"),
    (ScreenshotOptions(format="bmp"), ":HCOPY:SDUMp:DATA? BMP"),
])
def test_screenshot_capture_failure_restores_background_and_timeout(options, query):
    backend = FakeBackend(responses={":HARDcopy:INKSaver?": "0"}, timeout=2345)
    controller = ScreenshotController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))
    with pytest.raises(FakeBackendError):
        controller.capture(options=options, background="white")
    assert backend.history == [
        ":HARDcopy:INKSaver?", ":HARDcopy:INKSaver ON", query, ":HARDcopy:INKSaver OFF",
    ]
    assert backend.timeout_history == [10000, 2345]
    assert backend.timeout == 2345
