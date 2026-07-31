import pytest

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import ParameterValidationError, SerialResponseError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.serial import (
    SerialController,
    normalize_serial_source,
    parse_can_signal_definition,
    parse_serial_source,
    parse_serial_mode,
    serial_bus_query,
    serial_display_command,
    serial_display_query,
    serial_mode_command,
    serial_mode_query,
    validate_serial_bus,
)
from dataclasses import replace


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


def test_serial_uart_configure_order_and_scpi_mapping():
    backend = FakeBackend()
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX2004A"))
    state = controller.configure_uart(
        1, rx_source="channel1", baud_rate=115200, parity="none"
    )
    assert state.rx_source == "channel1"
    assert backend.history == [
        ":SBUS1:MODE UART",
        ":SBUS1:UART:SOURce:RX CHANnel1",
        ":SBUS1:UART:BAUDrate 115200",
        ":SBUS1:UART:PARity NONE",
    ]


def test_serial_i2c_configure_order_and_scpi_mapping():
    backend = FakeBackend()
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX2004A"))
    controller.configure_i2c(1, clock_source="external", address_size="bit8")
    assert backend.history == [
        ":SBUS1:MODE IIC",
        ":SBUS1:IIC:SOURce:CLOCk EXTernal",
        ":SBUS1:IIC:ASIZe BIT8",
    ]


def test_serial_spi_configure_order_and_scpi_mapping():
    backend = FakeBackend()
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX4034A"))
    controller.configure_spi(2, clock_source="channel1", framing="chip-select")
    assert backend.history == [
        ":SBUS2:MODE SPI",
        ":SBUS2:SPI:SOURce:CLOCk CHANnel1",
        ":SBUS2:SPI:FRAMing CHIPselect",
    ]


def test_serial_spi_timeout_framing_configure_order_and_scpi_mapping():
    backend = FakeBackend()
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX4034A"))
    controller.configure_spi(2, framing="timeout", clock_timeout=1e-6)

    assert backend.history == [
        ":SBUS2:MODE SPI",
        ":SBUS2:SPI:FRAMing TIMeout",
        ":SBUS2:SPI:CLOCk:TIMeout 1e-06",
    ]


@pytest.mark.parametrize("framing", ["chip-select", "no-chip-select"])
def test_serial_spi_clock_timeout_rejects_non_timeout_framing(framing):
    backend = FakeBackend()
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX4034A"))

    with pytest.raises(
        ParameterValidationError,
        match="framing is explicitly set to timeout",
    ):
        controller.configure_spi(2, framing=framing, clock_timeout=1e-6)

    assert backend.history == []


def test_serial_spi_clock_timeout_requires_explicit_framing():
    backend = FakeBackend()
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX4034A"))

    with pytest.raises(
        ParameterValidationError,
        match="framing is explicitly set to timeout",
    ):
        controller.configure_spi(2, clock_timeout=1e-6)

    assert backend.history == []


def test_serial_spi_timeout_framing_without_clock_timeout_is_allowed():
    backend = FakeBackend()
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX4034A"))

    controller.configure_spi(2, framing="timeout")

    assert backend.history == [
        ":SBUS2:MODE SPI",
        ":SBUS2:SPI:FRAMing TIMeout",
    ]


def test_serial_can_configure_order_and_scpi_mapping():
    backend = FakeBackend()
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX2004A"))
    controller.configure_can(1, source="external", signal_definition="difl", sample_point=75)
    assert backend.history == [
        ":SBUS1:MODE CAN",
        ":SBUS1:CAN:SOURce EXTernal",
        ":SBUS1:CAN:SIGNal:DEFinition DIFL",
        ":SBUS1:CAN:SAMPlepoint 75",
    ]


def test_serial_protocol_query_order_and_canonical_readbacks():
    backend = FakeBackend(
        responses={
            ":SBUS1:MODE?": "UART",
            ":SBUS1:UART:SOURce:RX?": "CHAN1",
            ":SBUS1:UART:SOURce:TX?": "EXT",
            ":SBUS1:UART:BAUDrate?": "115200",
            ":SBUS1:UART:WIDTh?": "8",
            ":SBUS1:UART:PARity?": "NONE",
            ":SBUS1:UART:POLarity?": "HIGH",
            ":SBUS1:UART:BITorder?": "MSBF",
        }
    )
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX2004A"))
    state = controller.query_uart(1)
    assert state.rx_source == "channel1"
    assert state.tx_source == "external"
    assert state.raw_rx_source == "CHAN1"
    assert backend.history == [
        ":SBUS1:MODE?",
        ":SBUS1:UART:SOURce:RX?",
        ":SBUS1:UART:SOURce:TX?",
        ":SBUS1:UART:BAUDrate?",
        ":SBUS1:UART:WIDTh?",
        ":SBUS1:UART:PARity?",
        ":SBUS1:UART:POLarity?",
        ":SBUS1:UART:BITorder?",
    ]


def test_serial_protocol_query_mode_mismatch_stops_before_fields():
    backend = FakeBackend(responses={":SBUS1:MODE?": "SPI"})
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX2004A"))
    with pytest.raises(SerialResponseError, match="expected 'uart'"):
        controller.query_uart(1)
    assert backend.history == [":SBUS1:MODE?"]


def test_serial_protocol_malformed_readback_uses_serial_response_error():
    backend = FakeBackend(
        responses={
            ":SBUS1:MODE?": "UART",
            ":SBUS1:UART:SOURce:RX?": "MAYBE",
        }
    )
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX2004A"))
    with pytest.raises(SerialResponseError, match="serial source"):
        controller.query_uart(1)
    assert backend.history == [":SBUS1:MODE?", ":SBUS1:UART:SOURce:RX?"]


def test_serial_source_uses_analog_channel_capability_and_can_normalize_difl():
    backend = FakeBackend()
    capabilities = replace(capabilities_for_model("DSOX2004A"), analog_channels=2)
    controller = SerialController(SCPIClient(backend), capabilities)
    with pytest.raises(ParameterValidationError, match="channel3"):
        controller.configure_uart(1, rx_source="channel3")
    assert backend.history == []
    assert parse_can_signal_definition("DIFFERENTIAL") == "difl"


@pytest.mark.parametrize("value, expected", [("channel1", "channel1"), ("external", "external")])
def test_serial_source_configure_accepts_only_canonical_values(value, expected):
    backend = FakeBackend()
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX2004A"))

    assert normalize_serial_source(value, controller.capabilities) == expected
    controller.configure_uart(1, rx_source=value)
    assert backend.history == [
        ":SBUS1:MODE UART",
        f":SBUS1:UART:SOURce:RX {'EXTernal' if value == 'external' else 'CHANnel1'}",
    ]


@pytest.mark.parametrize(
    "value",
    [
        "CHANnel1",
        "CHANNEL1",
        "External",
        "EXTernal",
        " channel1",
        "channel1 ",
        "channel01",
    ],
)
def test_serial_source_configure_rejects_noncanonical_values_before_scpi(value):
    backend = FakeBackend()
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX2004A"))

    with pytest.raises(ParameterValidationError):
        controller.configure_uart(1, rx_source=value)
    assert backend.history == []


@pytest.mark.parametrize(
    "raw, expected",
    [("CHAN1", "channel1"), ("CHANNEL1", "channel1"), ("EXT", "external"), ("EXTERNAL", "external")],
)
def test_serial_source_readback_accepts_instrument_aliases(raw, expected):
    assert parse_serial_source(raw, capabilities_for_model("DSOX2004A")) == expected


def test_serial_i2c_query_order_and_raw_readbacks():
    backend = FakeBackend(
        responses={
            ":SBUS1:MODE?": "IIC",
            ":SBUS1:IIC:SOURce:CLOCk?": "CHAN1",
            ":SBUS1:IIC:SOURce:DATA?": "EXTERNAL",
            ":SBUS1:IIC:ASIZe?": "BIT8",
        }
    )
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX2004A"))

    state = controller.query_i2c(1)

    assert state.clock_source == "channel1"
    assert state.data_source == "external"
    assert state.raw_address_size == "BIT8"
    assert backend.history == [
        ":SBUS1:MODE?",
        ":SBUS1:IIC:SOURce:CLOCk?",
        ":SBUS1:IIC:SOURce:DATA?",
        ":SBUS1:IIC:ASIZe?",
    ]


def test_serial_spi_query_order_and_raw_readbacks():
    backend = FakeBackend(
        responses={
            ":SBUS2:MODE?": "SPI",
            ":SBUS2:SPI:SOURce:CLOCk?": "CHAN1",
            ":SBUS2:SPI:SOURce:FRAMe?": "CHAN2",
            ":SBUS2:SPI:SOURce:MOSI?": "CHAN3",
            ":SBUS2:SPI:SOURce:MISO?": "CHAN4",
            ":SBUS2:SPI:CLOCk:SLOPe?": "NEG",
            ":SBUS2:SPI:BITorder?": "LSBF",
            ":SBUS2:SPI:WIDTh?": "8",
            ":SBUS2:SPI:FRAMing?": "TIM",
            ":SBUS2:SPI:CLOCk:TIMeout?": "1e-6",
        }
    )
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX4034A"))

    state = controller.query_spi(2)

    assert state.clock_source == "channel1"
    assert state.framing == "timeout"
    assert state.raw_word_width == "8"
    assert backend.history == [
        ":SBUS2:MODE?",
        ":SBUS2:SPI:SOURce:CLOCk?",
        ":SBUS2:SPI:SOURce:FRAMe?",
        ":SBUS2:SPI:SOURce:MOSI?",
        ":SBUS2:SPI:SOURce:MISO?",
        ":SBUS2:SPI:CLOCk:SLOPe?",
        ":SBUS2:SPI:BITorder?",
        ":SBUS2:SPI:WIDTh?",
        ":SBUS2:SPI:FRAMing?",
        ":SBUS2:SPI:CLOCk:TIMeout?",
    ]


def test_serial_can_query_order_and_raw_readbacks():
    backend = FakeBackend(
        responses={
            ":SBUS1:MODE?": "CAN",
            ":SBUS1:CAN:SOURce?": "CHAN1",
            ":SBUS1:CAN:SIGNal:BAUDrate?": "500000",
            ":SBUS1:CAN:SIGNal:DEFinition?": "DIFL",
            ":SBUS1:CAN:SAMPlepoint?": "75",
        }
    )
    controller = SerialController(SCPIClient(backend), capabilities_for_model("DSOX2004A"))

    state = controller.query_can(1)

    assert state.source == "channel1"
    assert state.signal_definition == "difl"
    assert state.raw_sample_point == "75"
    assert backend.history == [
        ":SBUS1:MODE?",
        ":SBUS1:CAN:SOURce?",
        ":SBUS1:CAN:SIGNal:BAUDrate?",
        ":SBUS1:CAN:SIGNal:DEFinition?",
        ":SBUS1:CAN:SAMPlepoint?",
    ]


@pytest.mark.parametrize(
    "method, model, responses, expected_history, field",
    [
        (
            "query_uart",
            "DSOX2004A",
            {
                ":SBUS1:MODE?": "UART",
                ":SBUS1:UART:SOURce:RX?": "CHAN1",
                ":SBUS1:UART:SOURce:TX?": "CHAN1",
                ":SBUS1:UART:BAUDrate?": "115200",
                ":SBUS1:UART:WIDTh?": "10",
            },
            [
                ":SBUS1:MODE?",
                ":SBUS1:UART:SOURce:RX?",
                ":SBUS1:UART:SOURce:TX?",
                ":SBUS1:UART:BAUDrate?",
                ":SBUS1:UART:WIDTh?",
            ],
            "UART data bits",
        ),
        (
            "query_spi",
            "DSOX4034A",
            {
                ":SBUS1:MODE?": "SPI",
                ":SBUS1:SPI:SOURce:CLOCk?": "CHAN1",
                ":SBUS1:SPI:SOURce:FRAMe?": "CHAN2",
                ":SBUS1:SPI:SOURce:MOSI?": "CHAN3",
                ":SBUS1:SPI:SOURce:MISO?": "CHAN4",
                ":SBUS1:SPI:CLOCk:SLOPe?": "POS",
                ":SBUS1:SPI:BITorder?": "MSBF",
                ":SBUS1:SPI:WIDTh?": "17",
            },
            [
                ":SBUS1:MODE?",
                ":SBUS1:SPI:SOURce:CLOCk?",
                ":SBUS1:SPI:SOURce:FRAMe?",
                ":SBUS1:SPI:SOURce:MOSI?",
                ":SBUS1:SPI:SOURce:MISO?",
                ":SBUS1:SPI:CLOCk:SLOPe?",
                ":SBUS1:SPI:BITorder?",
                ":SBUS1:SPI:WIDTh?",
            ],
            "SPI word width",
        ),
        (
            "query_can",
            "DSOX2004A",
            {
                ":SBUS1:MODE?": "CAN",
                ":SBUS1:CAN:SOURce?": "CHAN1",
                ":SBUS1:CAN:SIGNal:BAUDrate?": "500000",
                ":SBUS1:CAN:SIGNal:DEFinition?": "CANH",
                ":SBUS1:CAN:SAMPlepoint?": "61",
            },
            [
                ":SBUS1:MODE?",
                ":SBUS1:CAN:SOURce?",
                ":SBUS1:CAN:SIGNal:BAUDrate?",
                ":SBUS1:CAN:SIGNal:DEFinition?",
                ":SBUS1:CAN:SAMPlepoint?",
            ],
            "CAN sample point",
        ),
    ],
)
def test_serial_numeric_query_readback_validation_stops_at_invalid_field(
    method, model, responses, expected_history, field
):
    backend = FakeBackend(responses=responses)
    controller = SerialController(SCPIClient(backend), capabilities_for_model(model))

    with pytest.raises(SerialResponseError, match=field):
        getattr(controller, method)(1)
    assert backend.history == expected_history


@pytest.mark.parametrize(
    "configure, query, settings, field, expected",
    [
        ("configure_serial_uart", "query_serial_uart", {"rx_source": "channel2"}, "rx_source", "channel2"),
        ("configure_serial_i2c", "query_serial_i2c", {"clock_source": "external"}, "clock_source", "external"),
        ("configure_serial_spi", "query_serial_spi", {"framing": "timeout"}, "framing", "timeout"),
        ("configure_serial_can", "query_serial_can", {"signal_definition": "difl"}, "signal_definition", "difl"),
    ],
)
def test_serial_protocol_simulator_query_round_trip(configure, query, settings, field, expected):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4034a")
    scope = Oscilloscope(backend)
    scope.query_idn()
    getattr(scope, configure)(2, **settings)
    state = getattr(scope, query)(2)
    assert getattr(state, field) == expected
