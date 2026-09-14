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
    ("validator", "kwargs", "value"),
    [
        (validate_wgen_function, {}, "sinc"),
        (validate_wgen_amplitude, {"series": "2000X"}, 5.1),
        (validate_wgen_offset, {"series": "3000X"}, -2.6),
        (validate_wgen_frequency, {"series": "2000X"}, 0),
    ],
)
def test_wgen_validation_rejects_unsupported_or_unsafe_values(validator, kwargs, value):
    with pytest.raises(ParameterValidationError):
        validator(value, **kwargs)


def test_wgen_frequency_limits_follow_series_and_function():
    assert validate_wgen_frequency(100.0e3, series="2000X", function="ramp") == 100.0e3
    with pytest.raises(ParameterValidationError):
        validate_wgen_frequency(100.0e3 + 1.0, series="2000X", function="ramp")
    assert validate_wgen_frequency(200.0e3, series="3000X", function="ramp") == 200.0e3
    assert validate_wgen_frequency(20.0e6, series="4000X", function="sine") == 20.0e6
    with pytest.raises(ParameterValidationError, match="not applicable"):
        validate_wgen_frequency(1000.0, series="3000X", function="noise")
    with pytest.raises(ParameterValidationError, match="not applicable"):
        validate_wgen_frequency(1000.0, series="3000X", function="dc")


def test_wgen_amplitude_limits_follow_series_and_load():
    assert validate_wgen_amplitude(0.02, series="3000X") == 0.02
    assert validate_wgen_amplitude(0.01, series="3000X", load="fifty") == 0.01
    with pytest.raises(ParameterValidationError):
        validate_wgen_amplitude(0.005, series="3000X", load="fifty")
    assert validate_wgen_amplitude(10.0, series="4000X") == 10.0
    with pytest.raises(ParameterValidationError):
        validate_wgen_amplitude(10.0, series="4000X", load="fifty")
    with pytest.raises(ParameterValidationError, match="not applicable"):
        validate_wgen_amplitude(1.0, series="4000X", function="dc")


def test_wgen_offset_limits_follow_series_function_and_load():
    assert validate_wgen_offset(2.5, series="3000X") == 2.5
    with pytest.raises(ParameterValidationError):
        validate_wgen_offset(2.6, series="3000X")
    assert validate_wgen_offset(3.0, series="4000X", function="sine") == 3.0
    with pytest.raises(ParameterValidationError):
        validate_wgen_offset(4.1, series="4000X", function="sine")
    assert validate_wgen_offset(10.0, series="4000X", function="dc") == 10.0
    with pytest.raises(ParameterValidationError):
        validate_wgen_offset(10.0, series="4000X", function="dc", load="fifty")


def test_series_only_amplitude_planning_envelope():
    # Unspecified load (load=None) must use union envelope: lower bound
    # from 50-ohm halved minimum, upper bound from High-Z exact maximum.
    assert validate_wgen_amplitude(0.01, series="3000X", load=None) == 0.01
    assert validate_wgen_amplitude(5.0, series="3000X", load=None) == 5.0
    assert validate_wgen_amplitude(0.01, series="4000X", load=None) == 0.01
    assert validate_wgen_amplitude(10.0, series="4000X", load=None) == 10.0
    # Below 50-ohm minimum should be rejected.
    with pytest.raises(ParameterValidationError):
        validate_wgen_amplitude(0.005, series="3000X", load=None)


def test_4000x_interaction_not_applied_for_fifty_or_unspecified():
    # Software interaction guard is only applied for explicit High-Z
    # (one-meg) evidence; 50-ohm interaction is not inferred.
    # A low amplitude with a large (but within 50-ohm bound) offset
    # should succeed without interaction rejection.
    assert validate_wgen_offset(
        2.0, series="4000X", function="sine", load="fifty", amplitude=0.02
    ) == 2.0
    assert validate_wgen_offset(
        2.0, series="4000X", function="sine", load=None, amplitude=0.02
    ) == 2.0


def test_dc_amplitude_rejected_without_extra_queries():
    controller, backend = _wgen_live_controller({
        ":WGEN1:FUNCtion?": "DC",
    })
    with pytest.raises(ParameterValidationError, match="not applicable"):
        controller.configure_voltage(1.0)
    # Should not query load or offset for DC.
    assert ":WGEN1:OUTPut:LOAD?" not in backend.history
    assert ":WGEN1:VOLTage:OFFSet?" not in backend.history


def test_dc_offset_does_not_query_amplitude():
    controller, backend = _wgen_live_controller({
        ":WGEN1:FUNCtion?": "DC",
        ":WGEN1:OUTPut:LOAD?": "ONEM",
    })
    # DC offset does not need current amplitude.
    controller.configure_offset(3.0)
    assert ":WGEN1:VOLTage?" not in backend.history


def test_wgen_4000x_amplitude_offset_interaction():
    # Interaction guard applies only for explicit High-Z (one-meg)
    # evidence; 50-ohm interaction is not inferred by software.
    assert (
        validate_wgen_offset(
            0.6, series="4000X", function="sine", amplitude=0.04,
            load="one-meg",
        )
        == 0.6
    )
    with pytest.raises(ParameterValidationError, match="500 mV"):
        validate_wgen_offset(
            0.6, series="4000X", function="sine", amplitude=0.02,
            load="one-meg",
        )
    assert (
        validate_wgen_amplitude(
            0.04, series="4000X", function="sine", load="one-meg",
            offset=0.6,
        )
        == 0.04
    )
    with pytest.raises(ParameterValidationError, match="500 mV"):
        validate_wgen_amplitude(
            0.02, series="4000X", function="sine", load="one-meg",
            offset=0.6,
        )


def _wgen_live_controller(responses, model="DSOX4024A"):
    capabilities = capabilities_for_model(model)
    backend = FakeBackend(responses=dict(responses))
    return WgenController(SCPIClient(backend), capabilities), backend


def test_wgen_frequency_set_queries_function_and_skips_write_when_invalid():
    controller, backend = _wgen_live_controller({
        ":WGEN1:FUNCtion?": "RAMP",
    })

    with pytest.raises(ParameterValidationError):
        controller.configure_frequency(1.0e6)

    assert backend.history == [":WGEN1:FUNCtion?"]


def test_wgen_4000x_amplitude_set_queries_state_and_skips_write_on_interaction():
    controller, backend = _wgen_live_controller({
        ":WGEN1:FUNCtion?": "SIN",
        ":WGEN1:OUTPut:LOAD?": "ONEM",
        ":WGEN1:VOLTage:OFFSet?": "1.0",
    })

    with pytest.raises(ParameterValidationError, match="500 mV"):
        controller.configure_voltage(0.02)

    assert backend.history == [
        ":WGEN1:FUNCtion?",
        ":WGEN1:OUTPut:LOAD?",
        ":WGEN1:VOLTage:OFFSet?",
    ]


def test_wgen_4000x_offset_set_queries_state_and_skips_write_on_interaction():
    controller, backend = _wgen_live_controller({
        ":WGEN1:FUNCtion?": "SIN",
        ":WGEN1:OUTPut:LOAD?": "ONEM",
        ":WGEN1:VOLTage?": "0.02",
    })

    with pytest.raises(ParameterValidationError, match="500 mV"):
        controller.configure_offset(1.0)

    assert backend.history == [
        ":WGEN1:FUNCtion?",
        ":WGEN1:OUTPut:LOAD?",
        ":WGEN1:VOLTage?",
    ]
