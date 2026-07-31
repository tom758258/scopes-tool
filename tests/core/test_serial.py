import pytest

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import ParameterValidationError, SerialResponseError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.serial import (
    SerialController,
    parse_serial_mode,
    serial_bus_query,
    serial_display_command,
    serial_display_query,
    serial_mode_command,
    serial_mode_query,
    validate_serial_bus,
)


def test_serial_bus_one_command_generation():
    assert serial_bus_query(1) == ":SBUS1?"
    assert serial_mode_command(1, "uart") == ":SBUS1:MODE UART"
    assert serial_mode_query(1) == ":SBUS1:MODE?"
    assert serial_display_command(1, True) == ":SBUS1:DISPlay 1"
    assert serial_display_command(1, False) == ":SBUS1:DISPlay 0"
    assert serial_display_query(1) == ":SBUS1:DISPlay?"


@pytest.mark.parametrize("bus", [True, False, 0, -1, 1.0, "1"])
def test_serial_bus_rejects_bool_and_non_positive_integer_values(bus):
    with pytest.raises(ParameterValidationError, match="positive integer"):
        validate_serial_bus(bus, capabilities_for_model("DSOX2004A"))


def test_2000x_rejects_bus_two_before_scpi():
    backend = FakeBackend()
    controller = SerialController(
        SCPIClient(backend), capabilities_for_model("DSOX2004A")
    )
    with pytest.raises(ParameterValidationError, match="Serial bus 2"):
        controller.query(2)
    assert backend.history == []


def test_uart_configure_and_query_normalization():
    backend = FakeBackend(responses={":SBUS1:MODE?": "UART"})
    controller = SerialController(
        SCPIClient(backend), capabilities_for_model("DSOX2004A")
    )

    configured = controller.configure_mode(1, "uart")
    queried = controller.query_mode(1)

    assert configured.to_json() == {"bus": 1, "mode": "uart", "raw_mode": None}
    assert queried.to_json() == {
        "bus": 1,
        "mode": "uart",
        "raw_mode": "UART",
    }
    assert backend.history == [":SBUS1:MODE UART", ":SBUS1:MODE?"]


def test_4000x_accepts_usb_pd_and_2000x_rejects_it():
    controller_4000x = SerialController(
        SCPIClient(FakeBackend()), capabilities_for_model("DSOX4034A")
    )
    state = controller_4000x.configure_mode(2, "usb-pd")
    assert state.mode == "usb-pd"
    assert controller_4000x.scpi.backend.history == [":SBUS2:MODE USBPd"]

    backend_2000x = FakeBackend()
    controller_2000x = SerialController(
        SCPIClient(backend_2000x), capabilities_for_model("DSOX2004A")
    )
    with pytest.raises(ParameterValidationError, match="not supported"):
        controller_2000x.configure_mode(1, "usb-pd")
    assert backend_2000x.history == []


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("FLEX", "flexray"),
        ("FLEXRAY", "flexray"),
        ("MANC", "manchester"),
        ("MANCHESTER", "manchester"),
        ("USBP", "usb-pd"),
        ("USBPD", "usb-pd"),
    ],
)
def test_serial_mode_readback_short_forms(raw, expected):
    assert parse_serial_mode(raw) == expected


def test_serial_mode_none_query_preserves_raw_readback():
    backend = FakeBackend(responses={":SBUS1:MODE?": "NONE"})
    controller = SerialController(
        SCPIClient(backend), capabilities_for_model("DSOX2004A")
    )
    assert controller.query_mode(1).to_json() == {
        "bus": 1,
        "mode": None,
        "raw_mode": "NONE",
    }


@pytest.mark.parametrize(
    "raw, expected",
    [("1", True), ("ON", True), ("0", False), ("OFF", False)],
)
def test_serial_display_query_reuses_boolean_readback_parser(raw, expected):
    backend = FakeBackend(responses={":SBUS1:DISPlay?": raw})
    controller = SerialController(
        SCPIClient(backend), capabilities_for_model("DSOX2004A")
    )
    assert controller.query_display(1).to_json() == {
        "bus": 1,
        "enabled": expected,
        "raw_state": raw,
    }


def test_serial_display_malformed_readback_uses_serial_response_error():
    backend = FakeBackend(responses={":SBUS1:DISPlay?": "MAYBE"})
    controller = SerialController(
        SCPIClient(backend), capabilities_for_model("DSOX2004A")
    )

    with pytest.raises(SerialResponseError, match="serial display"):
        controller.query_display(1)

    assert backend.history == [":SBUS1:DISPlay?"]


def test_serial_aggregate_query_preserves_trimmed_raw_response():
    raw = "  :SBUS1:DISP 0;MODE IIC;... \n"
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX2004A,MY00000000,02.50",
            ":SBUS1?": raw,
        }
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    assert scope.query_serial(1).to_json() == {
        "bus": 1,
        "raw": ":SBUS1:DISP 0;MODE IIC;...",
    }
