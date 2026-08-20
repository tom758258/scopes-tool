import pytest

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import ParameterValidationError, SearchResponseError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.search import (
    SearchController,
    parse_can_data_length_query,
    parse_can_id_mode,
    parse_can_search_mode,
    parse_i2c_pattern_query,
    parse_search_count,
    parse_search_event,
    parse_search_mode,
    parse_search_qualifier,
    parse_search_state,
    parse_pattern_query,
    parse_spi_search_mode,
    parse_spi_width_query,
    parse_uart_data_query,
    parse_uart_search_mode,
    parse_i2c_search_mode,
    search_count_query,
    search_event_command,
    search_event_query,
    search_mode_command,
    search_mode_query,
    search_state_command,
    search_state_query,
    validate_search_event,
)
from scopes_tool_core.scpi import SCPIClient


def test_search_basic_scpi_builders():
    assert search_state_command(True) == ":SEARch:STATe 1"
    assert search_state_command(False) == ":SEARch:STATe 0"
    assert search_state_query() == ":SEARch:STATe?"
    assert search_mode_query() == ":SEARch:MODE?"
    assert search_count_query() == ":SEARch:COUNt?"
    assert search_mode_command("serial1") == ":SEARch:MODE SERial1"
    assert search_mode_command("serial2") == ":SEARch:MODE SERial2"
    assert search_mode_command("edge") == ":SEARch:MODE EDGE"
    assert search_mode_command("glitch") == ":SEARch:MODE GLITch"
    assert search_mode_command("runt") == ":SEARch:MODE RUNT"
    assert search_mode_command("transition") == ":SEARch:MODE TRANsition"
    assert search_mode_command("peak") == ":SEARch:MODE PEAK"


@pytest.mark.parametrize(
    "raw, expected", [("ON", True), ("1", True), ("+1", True), ("OFF", False), ("0", False)]
)
def test_parse_search_state(raw, expected):
    assert parse_search_state(raw) is expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("OFF", (None, False)),
        ("SER1", ("serial1", True)),
        ("SERial1", ("serial1", True)),
        ("SER2", ("serial2", True)),
        ("SERial2", ("serial2", True)),
        ("EDGE", ("edge", True)),
        ("GLIT", ("glitch", True)),
        ("GLITch", ("glitch", True)),
        ("RUNT", ("runt", True)),
        ("TRAN", ("transition", True)),
        ("TRANsition", ("transition", True)),
        ("PEAK", ("peak", True)),
    ],
)
def test_parse_search_mode_long_and_short_forms(raw, expected):
    assert parse_search_mode(raw) == expected


@pytest.mark.parametrize("raw", ["", "1.0", "abc", "1E+1", "-1"])
def test_parse_search_count_rejects_malformed_or_negative_readback(raw):
    with pytest.raises(SearchResponseError, match="Could not parse search count response"):
        parse_search_count(raw)


@pytest.mark.parametrize(
    "raw, expected_count, expected_raw",
    [("0", 0, "0"), ("+0", 0, "+0"), ("7", 7, "7"), (" +12 \n", 12, "+12")],
)
def test_parse_search_count_preserves_raw_non_negative_integer_readback(
    raw, expected_count, expected_raw
):
    state = parse_search_count(raw)
    assert state.count == expected_count
    assert state.raw_count == expected_raw


@pytest.mark.parametrize(
    "model, accepted, rejected",
    [
        ("DSOX2004A", {"serial1"}, {"serial2", "edge", "glitch", "runt", "transition", "peak"}),
        ("DSOX3024A", {"serial1", "serial2", "edge", "glitch", "runt", "transition"}, {"peak"}),
        ("DSOX4034A", {"serial1", "serial2", "edge", "glitch", "runt", "transition", "peak"}, set()),
    ],
)
def test_search_mode_profile_gating(model, accepted, rejected):
    for mode in accepted:
        backend = FakeBackend()
        controller = SearchController(SCPIClient(backend), capabilities_for_model(model))
        state = controller.configure_mode(mode)
        assert state.mode == mode
        assert backend.history == [":SEARch:STATe 1", search_mode_command(mode)]
    for mode in rejected:
        backend = FakeBackend()
        controller = SearchController(SCPIClient(backend), capabilities_for_model(model))
        with pytest.raises(ParameterValidationError, match="not supported by the selected"):
            controller.configure_mode(mode)
        assert backend.history == []


def test_oscilloscope_search_queries_preserve_raw_readbacks():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4034A,MY00000000,02.50",
            ":SEARch:STATe?": "ON",
            ":SEARch:MODE?": "TRAN",
            ":SEARch:COUNt?": "7",
        }
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    assert scope.query_search_state().to_json() == {"enabled": True, "raw_state": "ON"}
    assert scope.query_search_mode().to_json() == {
        "mode": "transition",
        "enabled": True,
        "raw_mode": "TRAN",
    }
    assert scope.query_search_count().to_json() == {"count": 7, "raw_count": "7"}


def test_query_search_mode_off_preserves_raw_readback():
    backend = FakeBackend(responses={":SEARch:MODE?": "OFF"})
    controller = SearchController(SCPIClient(backend), capabilities_for_model("DSOX2004A"))
    assert controller.query_mode().to_json() == {
        "mode": None,
        "enabled": False,
        "raw_mode": "OFF",
    }


def test_search_event_scpi_builders_and_validation():
    assert search_event_command(2) == ":SEARch:EVENt 2"
    assert search_event_query() == ":SEARch:EVENt?"
    for invalid in [0, -1, "1", True, False, 1.5]:
        with pytest.raises(ParameterValidationError, match="positive integer"):
            validate_search_event(invalid)


@pytest.mark.parametrize(
    "raw, expected_event, expected_raw",
    [("1", 1, "1"), ("+1", 1, "+1"), ("+0", 0, "+0"), (" 2 \n", 2, "2")],
)
def test_parse_search_event_success(raw, expected_event, expected_raw):
    state = parse_search_event(raw)
    assert state.event == expected_event
    assert state.raw == expected_raw


@pytest.mark.parametrize("raw", ["", "-1", "1.0", "abc"])
def test_parse_search_event_rejects_invalid(raw):
    with pytest.raises(SearchResponseError, match="Could not parse search event response"):
        parse_search_event(raw)


def test_search_event_query_and_set_on_4000x():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4034A,MY00000000,02.50",
            ":SEARch:EVENt?": "+3",
        }
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    query_res = scope.query_search_event()
    assert query_res.event == 3
    assert query_res.raw == "+3"
    assert query_res.to_json() == {"event": 3, "raw": "+3"}

    set_res = scope.configure_search_event(2)
    assert set_res.event == 2
    assert set_res.to_json() == {"event": 2}
    assert backend.history == ["*IDN?", ":SEARch:EVENt?", ":SEARch:EVENt 2"]


@pytest.mark.parametrize("model", ["DSOX2004A", "DSOX3024A"])
def test_search_event_unsupported_profiles_reject(model):
    backend = FakeBackend()
    controller = SearchController(SCPIClient(backend), capabilities_for_model(model))
    with pytest.raises(ParameterValidationError, match="not supported by the selected"):
        controller.query_event()
    with pytest.raises(ParameterValidationError, match="not supported by the selected"):
        controller.set_event(1)
    assert backend.history == []


@pytest.mark.parametrize(
    "protocol, configure_fn, args, expected_scpi",
    [
        (
            "uart",
            "configure_serial_search_uart",
            {"bus": 1, "mode": "rx-data", "data": 85, "qualifier": "equal"},
            [
                ":SEARch:STATe 1",
                ":SEARch:MODE SERial1",
                ":SEARch:SERial:UART:MODE RDATa",
                ":SEARch:SERial:UART:DATA 85",
                ":SEARch:SERial:UART:QUALifier EQUal",
            ],
        ),
        (
            "i2c",
            "configure_serial_search_i2c",
            {"bus": 1, "mode": "read7", "address": 80, "data": 255, "qualifier": "not-equal"},
            [
                ":SEARch:STATe 1",
                ":SEARch:MODE SERial1",
                ":SEARch:SERial:IIC:MODE READ7",
                ":SEARch:SERial:IIC:PATTern:ADDRess 80",
                ":SEARch:SERial:IIC:PATTern:DATA 255",
                ":SEARch:SERial:IIC:QUALifier NOTequal",
            ],
        ),
        (
            "spi",
            "configure_serial_search_spi",
            {"bus": 1, "mode": "mosi", "data": "0xA5XX", "width": 2},
            [
                ":SEARch:STATe 1",
                ":SEARch:MODE SERial1",
                ":SEARch:SERial:SPI:MODE MOSI",
                ":SEARch:SERial:SPI:PATTern:WIDTh 2",
                ':SEARch:SERial:SPI:PATTern:DATA "0xA5XX"',
            ],
        ),
        (
            "can",
            "configure_serial_search_can",
            {"bus": 1, "mode": "data", "data": "0x12XX", "data_length": 2, "id_val": "0x123", "id_mode": "standard"},
            [
                ":SEARch:STATe 1",
                ":SEARch:MODE SERial1",
                ":SEARch:SERial:CAN:MODE DATA",
                ":SEARch:SERial:CAN:PATTern:DATA:LENGth 2",
                ':SEARch:SERial:CAN:PATTern:DATA "0x12XX"',
                ":SEARch:SERial:CAN:PATTern:ID:MODE STANdard",
                ':SEARch:SERial:CAN:PATTern:ID "0x123"',
            ],
        ),
    ],
)
def test_core_serial_search_configure_commands(protocol, configure_fn, args, expected_scpi):
    backend = FakeBackend()
    scope = Oscilloscope(backend)
    scope.query_idn()
    getattr(scope, configure_fn)(**args)
    assert backend.history == ["*IDN?", *expected_scpi]


def test_core_serial_search_can_data_length_precedes_data_when_length_changes():
    class LengthSensitiveCanBackend(FakeBackend):
        def __init__(self):
            super().__init__()
            self.data = "0x12XX"
            self.data_length = 2

        def write(self, command: str) -> None:
            super().write(command)
            if command.endswith(":DATA:LENGth 1"):
                self.data_length = 1
                self.data = "0xXX"
            elif command.endswith(':DATA "0x01"'):
                self.data = "0x01"

        def query(self, command: str) -> str:
            if command == "*IDN?":
                return super().query(command)
            self._ensure_open()
            self.history.append(command)
            return {
                ":SEARch:STATe?": "1",
                ":SEARch:MODE?": "SER1",
                ":SEARch:SERial:CAN:MODE?": "DATA",
                ":SEARch:SERial:CAN:PATTern:DATA?": f'"{self.data}"',
                ":SEARch:SERial:CAN:PATTern:DATA:LENGth?": str(self.data_length),
                ":SEARch:SERial:CAN:PATTern:ID?": '"0x123"',
                ":SEARch:SERial:CAN:PATTern:ID:MODE?": "STAN",
            }[command]

    backend = LengthSensitiveCanBackend()
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_serial_search_can(
        bus=1,
        mode="data",
        data="0x01",
        data_length=1,
        id_val="0x123",
        id_mode="standard",
    )
    state = scope.query_serial_search_can(bus=1)

    assert state.data_length == 1
    assert state.data == "0x01"
    assert backend.history.index(":SEARch:SERial:CAN:PATTern:DATA:LENGth 1") < backend.history.index(
        ':SEARch:SERial:CAN:PATTern:DATA "0x01"'
    )


@pytest.mark.parametrize(
    "protocol, query_fn, responses, check_dict",
    [
        (
            "uart",
            "query_serial_search_uart",
            {
                "*IDN?": "KEYSIGHT,DSOX3024A,MY12345678,02.41",
                ":SEARch:STATe?": "1",
                ":SEARch:MODE?": "SER1",
                ":SEARch:SERial:UART:MODE?": "RDAT",
                ":SEARch:SERial:UART:DATA?": "85",
                ":SEARch:SERial:UART:QUALifier?": "EQU",
            },
            {"search_enabled": True, "raw_search_state": "1", "search_mode": "serial1", "raw_search_mode": "SER1", "selected": True, "mode": "rx-data", "raw_mode": "RDAT", "data": 85, "qualifier": "equal"},
        ),
        (
            "i2c",
            "query_serial_search_i2c",
            {
                "*IDN?": "KEYSIGHT,DSOX3024A,MY12345678,02.41",
                ":SEARch:STATe?": "1",
                ":SEARch:MODE?": "SER1",
                ":SEARch:SERial:IIC:MODE?": "READ7",
                ":SEARch:SERial:IIC:PATTern:ADDRess?": "80",
                ":SEARch:SERial:IIC:PATTern:DATA?": "255",
                ":SEARch:SERial:IIC:PATTern:DATA2?": "-1",
                ":SEARch:SERial:IIC:QUALifier?": "EQU",
            },
            {"search_enabled": True, "raw_search_state": "1", "search_mode": "serial1", "raw_search_mode": "SER1", "selected": True, "mode": "read7", "raw_mode": "READ7", "address": 80, "data": 255, "data2": -1, "qualifier": "equal"},
        ),
        (
            "spi",
            "query_serial_search_spi",
            {
                "*IDN?": "KEYSIGHT,DSOX3024A,MY12345678,02.41",
                ":SEARch:STATe?": "1",
                ":SEARch:MODE?": "SER1",
                ":SEARch:SERial:SPI:MODE?": "MOSI",
                ":SEARch:SERial:SPI:PATTern:DATA?": '"0xA5XX"',
                ":SEARch:SERial:SPI:PATTern:WIDTh?": "2",
            },
            {"search_enabled": True, "raw_search_state": "1", "search_mode": "serial1", "raw_search_mode": "SER1", "selected": True, "mode": "mosi", "raw_mode": "MOSI", "data": "0xA5XX", "raw_data": '"0xA5XX"', "width": 2},
        ),
        (
            "can",
            "query_serial_search_can",
            {
                "*IDN?": "KEYSIGHT,DSOX3024A,MY12345678,02.41",
                ":SEARch:STATe?": "1",
                ":SEARch:MODE?": "SER1",
                ":SEARch:SERial:CAN:MODE?": "DATA",
                ":SEARch:SERial:CAN:PATTern:DATA?": '"0x12XX"',
                ":SEARch:SERial:CAN:PATTern:DATA:LENGth?": "2",
                ":SEARch:SERial:CAN:PATTern:ID?": '"0x123"',
                ":SEARch:SERial:CAN:PATTern:ID:MODE?": "STAN",
            },
            {"search_enabled": True, "raw_search_state": "1", "search_mode": "serial1", "raw_search_mode": "SER1", "selected": True, "mode": "data", "raw_mode": "DATA", "data": "0x12XX", "data_length": 2, "id": "0x123", "id_mode": "standard"},
        ),
    ],
)
def test_core_serial_search_query_short_readbacks(protocol, query_fn, responses, check_dict):
    backend = FakeBackend(responses=responses)
    scope = Oscilloscope(backend)
    scope.query_idn()
    state = getattr(scope, query_fn)(bus=1)
    res_dict = state.to_json()
    for k, v in check_dict.items():
        assert res_dict[k] == v


@pytest.mark.parametrize(
    "parser, raw",
    [
        (parse_i2c_search_mode, "ADDR"),
        (parse_i2c_search_mode, "ADDRESS"),
        (parse_can_search_mode, "ACK"),
        (parse_can_search_mode, "STUFFERROR"),
    ],
)
def test_core_serial_search_preserves_unsupported_4000x_modes(parser, raw):
    assert parser(raw) == (None, raw)


def test_serial_search_query_preserves_raw_search_values_and_unselected_mode():
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT,DSOX3024A,MY12345678,02.41",
            ":SEARch:STATe?": " 1 ",
            ":SEARch:MODE?": " EDGE ",
            ":SEARch:SERial:UART:MODE?": "RDAT",
            ":SEARch:SERial:UART:DATA?": "85",
            ":SEARch:SERial:UART:QUALifier?": "EQU",
        }
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    result = scope.query_serial_search_uart(1).to_json()

    assert result["raw_search_state"] == "1"
    assert result["raw_search_mode"] == "EDGE"
    assert result["search_mode"] == "edge"
    assert result["selected"] is False


@pytest.mark.parametrize(
    "parser, raw",
    [
        (parse_uart_search_mode, "GARBAGE"),
        (parse_i2c_search_mode, ""),
        (parse_spi_search_mode, "GARBAGE"),
        (parse_can_search_mode, "GARBAGE"),
        (parse_search_qualifier, "BAD"),
        (parse_can_id_mode, "BAD"),
    ],
)
def test_serial_search_rejects_unknown_readbacks(parser, raw):
    with pytest.raises(SearchResponseError):
        parser(raw)


def test_serial_search_unknown_mode_error_identifies_field_and_response():
    with pytest.raises(
        SearchResponseError,
        match=r"Could not parse UART serial search mode response: 'GARBAGE'",
    ):
        parse_uart_search_mode("GARBAGE")


@pytest.mark.parametrize(
    "parser, raw",
    [
        (parse_uart_data_query, "256"),
        (parse_spi_width_query, "11"),
        (parse_can_data_length_query, "abc"),
        (parse_i2c_pattern_query, "1.0"),
    ],
)
def test_serial_search_rejects_malformed_numeric_readbacks(parser, raw):
    with pytest.raises(SearchResponseError):
        if parser is parse_i2c_pattern_query:
            parser(raw, "I2C address")
        else:
            parser(raw)


@pytest.mark.parametrize("raw", ['"0xA5XX', "0x", "0xGG", "garbage"])
def test_serial_search_rejects_malformed_pattern_readbacks(raw):
    with pytest.raises(SearchResponseError):
        parse_pattern_query(raw)


@pytest.mark.parametrize("raw", ['"0xA5XX"', "'0xA5XX'", "0xA5XX"])
def test_serial_search_pattern_readbacks_are_canonicalized(raw):
    assert parse_pattern_query(raw) == ("0xA5XX", raw)


def test_serial_search_rejects_bus2_for_2000x():
    backend = FakeBackend(responses={"*IDN?": "KEYSIGHT,DSOX2004A,MY12345678,02.41"})
    scope = Oscilloscope(backend)
    scope.query_idn()
    backend.history.clear()
    with pytest.raises(ParameterValidationError, match="bus"):
        scope.configure_serial_search_uart(bus=2, mode="rx-data")
    assert backend.history == []


def test_serial_search_validates_numeric_range_and_patterns():
    backend = FakeBackend()
    scope = Oscilloscope(backend)
    scope.query_idn()
    backend.history.clear()
    with pytest.raises(ParameterValidationError, match="data"):
        scope.configure_serial_search_uart(bus=1, mode="rx-data", data=256)
    with pytest.raises(ParameterValidationError, match="pattern"):
        scope.configure_serial_search_spi(bus=1, mode="mosi", data="0xGG")
    with pytest.raises(ParameterValidationError, match="width"):
        scope.configure_serial_search_spi(bus=1, mode="mosi", width=11)
    with pytest.raises(ParameterValidationError, match="pattern"):
        scope.configure_serial_search_spi(bus=1, mode="mosi", data="0xA5XX", width=8)
    with pytest.raises(ParameterValidationError, match="id-data"):
        scope.configure_serial_search_can(
            bus=1,
            mode="id-data",
            data="0x12XX",
            data_length=2,
            id_val="0x123",
            id_mode="standard",
        )
    assert backend.history == []


@pytest.mark.parametrize(
    "id_mode, id_val, valid",
    [
        ("standard", "0x7FF", True),
        ("standard", "0x800", False),
        ("standard", "0xABC", False),
        ("extended", "0xABC", True),
        ("extended", "0x20000000", False),
    ],
)
def test_serial_search_can_validates_id_range(id_mode, id_val, valid):
    backend = FakeBackend()
    scope = Oscilloscope(backend)
    scope.query_idn()
    backend.history.clear()

    if valid:
        state = scope.configure_serial_search_can(
            bus=1, mode="data", id_val=id_val, id_mode=id_mode
        )
        assert state.id == id_val.upper().replace("0X", "0x")
        assert backend.history
    else:
        with pytest.raises(ParameterValidationError, match="ID"):
            scope.configure_serial_search_can(
                bus=1, mode="data", id_val=id_val, id_mode=id_mode
            )
        assert backend.history == []
