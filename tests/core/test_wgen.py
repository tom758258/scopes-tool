import pytest

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scpi import SCPIClient
from scopes_tool_core.wgen import (
    WgenController,
    parse_wgen_function,
    validate_wgen_amplitude,
    validate_wgen_frequency,
    validate_wgen_function,
    validate_wgen_offset,
    wgen_offset_query,
    wgen_output_command,
)


def test_wgen_scpi_builder_uses_profile_dialect():
    plain = capabilities_for_model("DSOX3024A")
    indexed = capabilities_for_model("DSOX4024A")

    assert wgen_output_command(True, plain) == ":WGEN:OUTPut ON"
    assert wgen_output_command(True, indexed) == ":WGEN1:OUTPut ON"
    assert wgen_offset_query(plain) == ":WGEN:VOLTage:OFFSet?"
    assert wgen_offset_query(indexed) == ":WGEN1:VOLTage:OFFSet?"


def test_wgen_function_normalization_and_unknown_aggregate_preservation():
    assert parse_wgen_function("SIN") == "sine"
    assert parse_wgen_function("SQU") == "square"

    capabilities = capabilities_for_model("DSOX4024A")
    backend = FakeBackend(
        responses={
            ":WGEN1:OUTPut?": "OFF",
            ":WGEN1:FUNCtion?": "SINC",
            ":WGEN1:FREQuency?": "1.0E+3",
            ":WGEN1:VOLTage?": "0.5",
            ":WGEN1:VOLTage:OFFSet?": "0",
            ":WGEN1:OUTPut:LOAD?": "ONEM",
        }
    )
    state = WgenController(SCPIClient(backend), capabilities).query()

    assert state.function is None
    assert state.function_raw == "SINC"
    assert state.frequency_hz == 1000.0
    assert state.load == "one-meg"


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        (validate_wgen_function, "sinc"),
        (validate_wgen_amplitude, 5.1),
        (validate_wgen_offset, -2.6),
        (validate_wgen_frequency, 0),
    ],
)
def test_wgen_validation_rejects_unsupported_or_unsafe_values(validator, value):
    with pytest.raises(ParameterValidationError):
        validator(value)
