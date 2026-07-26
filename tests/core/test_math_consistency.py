import argparse

import pytest

from scopes_tool_cli import cli
from scopes_tool_cli import worker
from scopes_tool_core.advanced import (
    FFT_OPERATIONS,
    MATH_COMPOSITE_OPERATIONS,
    MATH_FILTER_OPERATIONS,
    MATH_OPERATIONS,
    MATH_TRANSFORMS,
    MATH_VISUALIZATION_OPERATIONS,
    fft_configure_commands,
    math_filter_commands,
    math_function_scpi_prefix,
    math_operator_commands,
    math_transform_commands,
    math_visualization_commands,
    parse_math_source,
    parse_math_source1,
    parse_math_trend_measurement_slot,
    validate_math_smooth_points,
)
from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.errors import ChannelResponseError, ParameterValidationError
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend


_PROFILE_MATRIX = {
    "keysight-dsox2004a": {
        "series": "2000X",
        "count": 1,
        "goft": True,
        "cascade": False,
        "advanced_fft": False,
        "filters": {"low-pass", "high-pass"},
        "visualizations": {"magnify", "trend"},
    },
    "keysight-dsox3024a": {
        "series": "3000X",
        "count": 1,
        "goft": True,
        "cascade": False,
        "advanced_fft": False,
        "filters": {"low-pass", "high-pass"},
        "visualizations": {"magnify", "trend"},
    },
    "keysight-dsox4024a": {
        "series": "4000X",
        "count": 4,
        "goft": False,
        "cascade": True,
        "advanced_fft": True,
        "filters": set(MATH_FILTER_OPERATIONS),
        "visualizations": set(MATH_VISUALIZATION_OPERATIONS),
    },
}


def _subcommand_parsers() -> dict[str, argparse.ArgumentParser]:
    parser = cli._build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return subparsers.choices


def _long_option_names(parser: argparse.ArgumentParser) -> set[str]:
    return {
        option.removeprefix("--").replace("-", "_")
        for action in parser._actions
        for option in action.option_strings
        if option.startswith("--") and option != "--help"
    }


def _option_choices(
    parser: argparse.ArgumentParser, option: str
) -> tuple[str, ...]:
    action = next(
        action for action in parser._actions if option in action.option_strings
    )
    return tuple(action.choices or ())


def test_math_profile_operation_and_dialect_consistency_gate():
    for model, expected in _PROFILE_MATRIX.items():
        capabilities = capabilities_for_model_id(model)
        assert capabilities.series == expected["series"]
        assert capabilities.math_function_count == expected["count"]
        assert capabilities.supports_math_goft is expected["goft"]
        assert capabilities.supports_math_cascade is expected["cascade"]
        assert capabilities.supports_advanced_fft is expected["advanced_fft"]
        assert capabilities.math_filter_operations == frozenset(
            expected["filters"]
        )
        assert capabilities.math_visualization_operations == frozenset(
            expected["visualizations"]
        )
        assert capabilities.math_filter_operations <= set(
            MATH_FILTER_OPERATIONS
        )
        assert capabilities.math_visualization_operations <= set(
            MATH_VISUALIZATION_OPERATIONS
        )

        prefix = math_function_scpi_prefix(1, capabilities)
        assert prefix == (
            ":FUNCtion1" if capabilities.series == "4000X" else ":FUNCtion"
        )
        for operation in MATH_OPERATIONS:
            assert math_operator_commands(
                1,
                operation,
                "channel1",
                "channel2",
                capabilities=capabilities,
            )[0].startswith(f"{prefix}:OPERation ")
        for operation in MATH_TRANSFORMS:
            assert math_transform_commands(
                1,
                operation,
                "channel1",
                capabilities=capabilities,
            )[0].startswith(f"{prefix}:OPERation ")
        for operation in capabilities.math_filter_operations:
            assert math_filter_commands(
                1,
                operation,
                "channel1",
                capabilities=capabilities,
            )[0].startswith(f"{prefix}:OPERation ")
        for operation in capabilities.math_visualization_operations:
            arguments = (
                {"measurement_slot": 1}
                if operation == "trend" and capabilities.series == "4000X"
                else (
                    {"source": "channel1", "measurement": "vavg"}
                    if operation == "trend"
                    else {"source": "channel1"}
                )
            )
            assert math_visualization_commands(
                1,
                operation,
                capabilities=capabilities,
                **arguments,
            )[0].startswith(f"{prefix}:OPERation ")
        assert fft_configure_commands(
            1, 1, capabilities=capabilities
        )[0] == f"{prefix}:OPERation FFT"
        if capabilities.supports_advanced_fft:
            assert fft_configure_commands(
                1,
                1,
                fft_operation="fft-phase",
                capabilities=capabilities,
            )[0] == f"{prefix}:OPERation FFTPhase"


def test_math_cli_worker_schema_and_p8_absence_consistency_gate():
    command_parsers = _subcommand_parsers()
    connection_parser = argparse.ArgumentParser(add_help=False)
    cli._add_scope_connection_args(connection_parser)
    connection_arguments = _long_option_names(connection_parser)

    assert set(worker._MATH_WORKER_ARGUMENTS) <= worker.DOMAIN_COMMANDS
    for command, worker_arguments in worker._MATH_WORKER_ARGUMENTS.items():
        cli_arguments = (
            _long_option_names(command_parsers[command]) - connection_arguments
        )
        assert cli_arguments == set(worker_arguments)

    assert _option_choices(
        command_parsers["fft"], "--fft-operation"
    ) == FFT_OPERATIONS
    assert _option_choices(
        command_parsers["math-operator"], "--operation"
    ) == MATH_OPERATIONS
    assert _option_choices(
        command_parsers["math-composite-source"], "--operation"
    ) == MATH_COMPOSITE_OPERATIONS
    assert _option_choices(
        command_parsers["math-transform"], "--operation"
    ) == MATH_TRANSFORMS
    assert _option_choices(
        command_parsers["math-filter"], "--operation"
    ) == MATH_FILTER_OPERATIONS
    assert _option_choices(
        command_parsers["math-visualization"], "--operation"
    ) == MATH_VISUALIZATION_OPERATIONS

    enabled_names = {
        *command_parsers,
        *worker.DOMAIN_COMMANDS,
        *FFT_OPERATIONS,
        *MATH_OPERATIONS,
        *MATH_TRANSFORMS,
        *MATH_FILTER_OPERATIONS,
        *MATH_VISUALIZATION_OPERATIONS,
    }
    assert "bus-timing" not in enabled_names
    assert "bus-state" not in enabled_names


@pytest.mark.parametrize("model", _PROFILE_MATRIX)
def test_math_enabled_operations_have_simulator_round_trip(model):
    backend = SimulatorBackend(physical_model_id=model)
    scope = Oscilloscope(backend)
    scope.query_idn()
    capabilities = scope.capabilities

    scope.configure_math_display(1, True)
    scope.configure_math_vertical(1, scale=2.0, offset=0.25)
    assert scope.query_math_display(1).enabled is True
    vertical = scope.query_math_vertical(1)
    assert vertical.scale == pytest.approx(2.0)
    assert vertical.offset == pytest.approx(0.25)

    for operation in MATH_OPERATIONS:
        scope.configure_math_operator(
            1, operation, "channel1", "channel2"
        )
        assert scope.query_math_operator(1).operation == operation

    for operation in MATH_TRANSFORMS:
        settings = (
            {"input_offset": 0.5}
            if operation == "integrate"
            else (
                {"gain": 2.0, "linear_offset": -1.0}
                if operation == "linear"
                else {}
            )
        )
        scope.configure_math_transform(
            1, operation, "channel1", **settings
        )
        state = scope.query_math_transform(1)
        assert state.operation == operation
        if operation == "integrate":
            assert state.input_offset == pytest.approx(0.5)
        else:
            assert state.input_offset is None
        if operation == "linear":
            assert state.gain == pytest.approx(2.0)
            assert state.linear_offset == pytest.approx(-1.0)
        else:
            assert state.gain is None
            assert state.linear_offset is None

    for operation in capabilities.math_filter_operations:
        settings = {
            "low-pass": {"cutoff_hz": 1e6},
            "high-pass": {"cutoff_hz": 1e3},
            "average": {"average_count": 64},
            "smooth": {"smooth_points": 9},
            "envelope": {},
        }[operation]
        scope.configure_math_filter(
            1, operation, "channel1", **settings
        )
        state = scope.query_math_filter(1)
        assert state.operation == operation
        assert (state.cutoff_hz is not None) is (
            operation in {"low-pass", "high-pass"}
        )
        assert (state.average_count is not None) is (operation == "average")
        assert (state.smooth_points is not None) is (operation == "smooth")

    for operation in capabilities.math_visualization_operations:
        settings = (
            {"measurement_slot": 1}
            if operation == "trend" and capabilities.series == "4000X"
            else (
                {"source": "channel1", "measurement": "vavg"}
                if operation == "trend"
                else {"source": "channel1"}
            )
        )
        scope.configure_math_visualization(1, operation, **settings)
        state = scope.query_math_visualization(1)
        assert state.operation == operation
        assert state.measurement_slot == (
            1
            if operation == "trend" and capabilities.series == "4000X"
            else None
        )

    if capabilities.supports_math_goft:
        scope.configure_math_composite_source(
            "subtract", "channel1", "channel2"
        )
        assert scope.query_math_composite_source().operation == "subtract"
    if capabilities.supports_math_cascade:
        scope.configure_math_transform(2, "absolute", "math1")
        assert scope.query_math_transform(2).source == "math1"
        scope.configure_math_filter(1, "average", "channel1", average_count=64)
        scope.clear_math(1)

    scope.configure_fft(1, 1, units="decibel")
    assert scope.query_fft(1).operation_canonical == "fft"
    if capabilities.supports_advanced_fft:
        scope.configure_fft(1, 1, fft_operation="fft-phase")
        assert scope.query_fft(1).operation_canonical == "fft-phase"


@pytest.mark.parametrize(
    ("query_kind", "overrides"),
    [
        (
            "vertical",
            {":FUNCtion1:SCALe?": "NaN"},
        ),
        (
            "transform",
            {
                ":FUNCtion1:OPERation?": "LIN",
                ":FUNCtion1:SOURce1?": "CHAN1",
                ":FUNCtion1:LINear:GAIN?": "1e9999",
            },
        ),
        (
            "filter",
            {
                ":FUNCtion1:OPERation?": "LOWP",
                ":FUNCtion1:SOURce1?": "CHAN1",
                ":FUNCtion1:FREQuency:LOWPass?": "not-a-number",
            },
        ),
    ],
)
def test_math_numeric_query_errors_use_domain_error(query_kind, overrides):
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox4024a",
        query_overrides=overrides,
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    with pytest.raises(ChannelResponseError, match="Could not parse Math"):
        {
            "vertical": scope.query_math_vertical,
            "transform": scope.query_math_transform,
            "filter": scope.query_math_filter,
        }[query_kind](1)


def test_math_oversized_integer_readbacks_use_domain_errors():
    oversized = "9" * 5000

    with pytest.raises(ChannelResponseError, match="Math source"):
        parse_math_source(f"CHAN{oversized}")
    with pytest.raises(ChannelResponseError, match="Math source"):
        parse_math_source1(f"FUNC{oversized}", 2)
    with pytest.raises(ChannelResponseError, match="Trend measurement slot"):
        parse_math_trend_measurement_slot(f"MEAS{oversized}")


def test_math_oversized_smooth_points_use_domain_error():
    with pytest.raises(ParameterValidationError, match="too large"):
        validate_math_smooth_points(10**10000)


@pytest.mark.parametrize(
    ("command", "response"),
    [
        (":FUNCtion1:SOURce1?", "BUS1"),
        (":FUNCtion1:DISPlay?", "MAYBE"),
    ],
)
def test_fft_unknown_source_and_display_readbacks_use_domain_errors(
    command, response
):
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox4024a",
        query_overrides={command: response},
    )
    scope = Oscilloscope(backend)
    scope.query_idn()

    with pytest.raises(ChannelResponseError):
        scope.query_fft(1)
