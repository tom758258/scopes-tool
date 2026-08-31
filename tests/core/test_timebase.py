import pytest

from scopes_tool_core.errors import ParameterValidationError, TimebaseResponseError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.timebase import (
    TimebaseController,
    parse_timebase_float,
    parse_timebase_reference,
    timebase_position_command,
    timebase_position_query,
    timebase_reference_command,
    timebase_reference_query,
    timebase_scale_command,
    timebase_scale_query,
    validate_timebase_position,
    validate_timebase_reference,
    validate_timebase_scale,
)


def test_timebase_scale_and_position_commands_use_keysight_syntax():
    assert timebase_scale_command(0.001) == ":TIMebase:SCALe 0.001"
    assert timebase_scale_query() == ":TIMebase:SCALe?"
    assert timebase_position_command(-0.0005) == ":TIMebase:POSition -0.0005"
    assert timebase_position_query() == ":TIMebase:POSition?"


@pytest.mark.parametrize(
    "reference, token",
    [("left", "LEFT"), ("center", "CENTer"), ("right", "RIGHt")],
)
def test_timebase_reference_commands_use_keysight_syntax(reference, token):
    assert timebase_reference_command(reference) == f":TIMebase:REFerence {token}"
    assert timebase_reference_query() == ":TIMebase:REFerence?"


@pytest.mark.parametrize(
    "raw, expected",
    [("LEFT", "left"), (" CENT ", "center"), ("RIGHt", "right")],
)
def test_parse_timebase_reference_normalizes_instrument_response(raw, expected):
    assert parse_timebase_reference(raw) == expected


def test_timebase_reference_rejects_invalid_values_and_responses():
    with pytest.raises(ParameterValidationError):
        validate_timebase_reference("middle")
    with pytest.raises(TimebaseResponseError):
        parse_timebase_reference("MIDDLE")


@pytest.mark.parametrize("raw, expected", [("1.0E-3", 0.001), (" -5.0E-4 ", -0.0005)])
def test_parse_timebase_float(raw, expected):
    assert parse_timebase_float(raw, "scale") == expected


@pytest.mark.parametrize("raw", ["MAYBE", "NaN", "INF"])
def test_parse_timebase_float_rejects_unexpected_response(raw):
    with pytest.raises(TimebaseResponseError):
        parse_timebase_float(raw, "scale")


@pytest.mark.parametrize("value", [1.0, 0.001, "1e-6"])
def test_validate_timebase_scale_accepts_positive_finite_values(value):
    assert validate_timebase_scale(value) == float(value)


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan"), "abc"])
def test_validate_timebase_scale_rejects_non_positive_or_non_finite_values(value):
    with pytest.raises(ParameterValidationError):
        validate_timebase_scale(value)


@pytest.mark.parametrize("value", [0.0, -0.0005, "1e-3"])
def test_validate_timebase_position_accepts_finite_values(value):
    assert validate_timebase_position(value) == float(value)


@pytest.mark.parametrize("value", [float("inf"), float("nan"), "abc"])
def test_validate_timebase_position_rejects_non_finite_values(value):
    with pytest.raises(ParameterValidationError):
        validate_timebase_position(value)


def test_timebase_controller_sets_scale_and_reads_back_value():
    backend = FakeBackend(responses={":TIMebase:SCALe?": "1.0E-3"})
    controller = TimebaseController(SCPIClient(backend))

    controller.set_scale(0.001)
    scale = controller.query_scale()

    assert scale == 0.001
    assert backend.history == [":TIMebase:SCALe 0.001", ":TIMebase:SCALe?"]


def test_timebase_controller_sets_position_and_reads_back_value():
    backend = FakeBackend(responses={":TIMebase:POSition?": "-5.0E-4"})
    controller = TimebaseController(SCPIClient(backend))

    controller.set_position(-0.0005)
    position = controller.query_position()

    assert position == -0.0005
    assert backend.history == [":TIMebase:POSition -0.0005", ":TIMebase:POSition?"]


def test_timebase_controller_rejects_invalid_scale_before_scpi():
    backend = FakeBackend()
    controller = TimebaseController(SCPIClient(backend))

    with pytest.raises(ParameterValidationError):
        controller.set_scale(0.0)

    assert backend.history == []


def test_timebase_controller_sets_and_queries_reference():
    backend = FakeBackend(responses={":TIMebase:REFerence?": "CENT"})
    controller = TimebaseController(SCPIClient(backend))

    controller.set_reference("center")
    assert controller.query_reference() == "center"
    assert backend.history == [
        ":TIMebase:REFerence CENTer",
        ":TIMebase:REFerence?",
    ]


def test_timebase_controller_rejects_invalid_reference_before_scpi():
    backend = FakeBackend()
    controller = TimebaseController(SCPIClient(backend))

    with pytest.raises(ParameterValidationError):
        controller.set_reference("middle")

    assert backend.history == []
