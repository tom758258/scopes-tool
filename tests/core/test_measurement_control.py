import pytest

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.measurements import (
    MeasurementController,
    measurement_menu_command,
    measurement_show_command,
    measurement_source_command,
    measurement_window_command,
    parse_measurement_show,
    parse_measurement_source,
    parse_measurement_window,
)
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend


@pytest.mark.parametrize(("raw", "expected"), [("1", True), ("0", False), ("ON", True), ("OFF", False)])
def test_parse_measurement_show(raw, expected):
    assert parse_measurement_show(raw) is expected


@pytest.mark.parametrize(
    ("raw", "channels"),
    [("CHAN1", (1, None)), ("CHANnel1", (1, None)), ("CHANNEL1", (1, None)), ("CHAN1,CHAN2", (1, 2))],
)
def test_parse_measurement_source_preserves_raw(raw, channels):
    state = parse_measurement_source(raw)
    assert (state.source1_channel, state.source2_channel) == channels
    assert state.raw == raw


@pytest.mark.parametrize(("raw", "expected"), [("MAIN", "MAIN"), ("ZOO", "ZOOM"), ("AUTO", "AUTO"), ("GAT", "GATE")])
def test_parse_measurement_window(raw, expected):
    assert parse_measurement_window(raw) == expected


def test_measurement_control_builders_validate_channels_and_values():
    capabilities = capabilities_for_model("DSOX2004A")
    assert measurement_source_command(1, 2, capabilities=capabilities) == ":MEASure:SOURce CHANnel1,CHANnel2"
    assert measurement_window_command("gate") == ":MEASure:WINDow GATE"
    with pytest.raises(ParameterValidationError):
        measurement_source_command(5, capabilities=capabilities)


def test_measurement_show_command_supports_on_and_off():
    assert measurement_show_command() == ":MEASure:SHOW ON"
    assert measurement_show_command(True) == ":MEASure:SHOW ON"
    assert measurement_show_command(False) == ":MEASure:SHOW OFF"


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("DSOX2004A", ":SYSTem:MENU MEASure"),
        ("DSOX3024A", ":SYSTem:MENU MEASure"),
        ("DSOX4024A", ":DISPlay:SIDebar MEASurements"),
    ],
)
def test_measurement_menu_command_series(model_id, expected):
    capabilities = capabilities_for_model(model_id)
    assert measurement_menu_command(capabilities) == expected
    backend = FakeBackend()
    controller = MeasurementController(SCPIClient(backend), capabilities)
    controller.open_menu()
    assert backend.history == [expected]
    scope = Oscilloscope(SimulatorBackend(physical_model_id=f"keysight-{model_id.lower()}"))
    scope.query_idn()
    scope.open_measurement_menu()
    assert scope.backend.history[-1] == expected


@pytest.mark.parametrize("model_id", ("DSOX2004A", "DSOX3024A"))
def test_measurement_controller_rejects_marker_off_on_2000x_and_3000x(model_id):
    backend = FakeBackend()
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model(model_id))
    with pytest.raises(ParameterValidationError, match="OFF"):
        controller.set_show(False)
    assert backend.history == []


def test_measurement_controller_accepts_marker_off_on_4000x():
    backend = FakeBackend(responses={":MEASure:SHOW?": "0"})
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))
    controller.set_show(False)
    assert controller.query_show().enabled is False
    assert backend.history == [":MEASure:SHOW OFF", ":MEASure:SHOW?"]


def test_measurement_controller_command_order_and_raw_state():
    backend = FakeBackend(
        responses={
            ":MEASure:SHOW?": " ON ",
            ":MEASure:SOURce?": "CHAN1,CHAN2",
            ":MEASure:WINDow?": "ZOOM",
        }
    )
    controller = MeasurementController(SCPIClient(backend), capabilities_for_model("DSOX4024A"))
    controller.clear()
    controller.set_show_on()
    controller.set_source(1, 2)
    controller.set_window("zoom")
    assert controller.query_show().raw_enabled == "ON"
    assert controller.query_source().raw == "CHAN1,CHAN2"
    assert controller.query_window().raw_window == "ZOOM"
    assert backend.history == [
        ":MEASure:CLEar",
        ":MEASure:SHOW ON",
        ":MEASure:SOURce CHANnel1,CHANnel2",
        ":MEASure:WINDow ZOOM",
        ":MEASure:SHOW?",
        ":MEASure:SOURce?",
        ":MEASure:WINDow?",
    ]


def test_measurement_control_simulator_roundtrip():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()
    scope.configure_measurement_show()
    scope.configure_measurement_source(1, 2)
    scope.configure_measurement_window("gate")
    assert scope.query_measurement_show().enabled is True
    scope.configure_measurement_show(False)
    assert scope.query_measurement_show().enabled is False
    assert scope.query_measurement_source().source2_channel == 2
    assert scope.query_measurement_window().window == "GATE"
