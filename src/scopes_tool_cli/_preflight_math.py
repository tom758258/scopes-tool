"""CLI pre-open validation for Math commands."""

from __future__ import annotations

import argparse

from scopes_tool_core.math import (
    math_display_command,
    math_display_query,
    math_clear_command,
    math_composite_source_commands,
    math_composite_source_query_commands,
    math_operator_commands,
    math_operator_query_commands,
    math_filter_commands,
    math_filter_query_commands,
    math_transform_commands,
    math_transform_query_commands,
    math_visualization_commands,
    math_visualization_query_commands,
    math_vertical_commands,
    math_vertical_query_commands,
)
from scopes_tool_core.errors import ParameterValidationError

from ._preflight_common import _pre_open_capabilities


def _validate_math_args(args: argparse.Namespace) -> None:
    capabilities = _pre_open_capabilities(args)
    if args.command == "math-composite-source":
        configure_values = (
            args.math_composite_operation,
            args.source1,
            args.source2,
        )
        if args.math_composite_query:
            if any(value is not None for value in configure_values):
                raise ParameterValidationError(
                    "math-composite-source --query cannot be combined with "
                    "configure options."
                )
            math_composite_source_query_commands(capabilities=capabilities)
            return
        if any(value is None for value in configure_values):
            raise ParameterValidationError(
                "math-composite-source configure requires --operation, "
                "--source1, and --source2."
            )
        math_composite_source_commands(
            args.math_composite_operation,
            args.source1,
            args.source2,
            capabilities=capabilities,
        )
        return

    if args.command == "math-display":
        if args.math_display_action == "query":
            math_display_query(args.function, capabilities=capabilities)
        else:
            math_display_command(
                args.function,
                args.math_display_action == "on",
                capabilities=capabilities,
            )
        return

    if args.command == "math-vertical":
        if args.math_vertical_query:
            if any(
                value is not None
                for value in (args.scale, args.range_value, args.offset)
            ):
                raise ParameterValidationError(
                    "math-vertical --query cannot be combined with configure options."
                )
            math_vertical_query_commands(args.function, capabilities=capabilities)
            return
        math_vertical_commands(
            args.function,
            scale=args.scale,
            range_value=args.range_value,
            offset=args.offset,
            capabilities=capabilities,
        )
        return

    if args.command == "math-transform":
        configure_values = (
            args.math_transform_operation,
            args.source,
            args.input_offset,
            args.gain,
            args.linear_offset,
        )
        if args.math_transform_query:
            if any(value is not None for value in configure_values):
                raise ParameterValidationError(
                    "math-transform --query cannot be combined with configure options."
                )
            math_transform_query_commands(
                args.function, capabilities=capabilities
            )
            return
        if args.math_transform_operation is None or args.source is None:
            raise ParameterValidationError(
                "math-transform configure requires --operation and --source."
            )
        math_transform_commands(
            args.function,
            args.math_transform_operation,
            args.source,
            input_offset=args.input_offset,
            gain=args.gain,
            linear_offset=args.linear_offset,
            capabilities=capabilities,
        )
        return

    if args.command == "math-filter":
        configure_values = (
            args.math_filter_operation,
            args.source,
            args.cutoff_hz,
            args.average_count,
            args.smooth_points,
        )
        if args.math_filter_query:
            if any(value is not None for value in configure_values):
                raise ParameterValidationError(
                    "math-filter --query cannot be combined with configure options."
                )
            math_filter_query_commands(args.function, capabilities=capabilities)
            return
        if args.math_filter_operation is None or args.source is None:
            raise ParameterValidationError(
                "math-filter configure requires --operation and --source."
            )
        math_filter_commands(
            args.function,
            args.math_filter_operation,
            args.source,
            cutoff_hz=args.cutoff_hz,
            average_count=args.average_count,
            smooth_points=args.smooth_points,
            capabilities=capabilities,
        )
        return

    if args.command == "math-visualization":
        configure_values = (
            args.math_visualization_operation,
            args.source,
            args.source2,
            args.measurement,
            args.measurement_slot,
        )
        if args.math_visualization_query:
            if any(value is not None for value in configure_values):
                raise ParameterValidationError(
                    "math-visualization --query cannot be combined with "
                    "configure options."
                )
            math_visualization_query_commands(
                args.function, capabilities=capabilities
            )
            return
        if args.math_visualization_operation is None:
            raise ParameterValidationError(
                "math-visualization configure requires --operation."
            )
        math_visualization_commands(
            args.function,
            args.math_visualization_operation,
            source=args.source,
            source2=args.source2,
            measurement=args.measurement,
            measurement_slot=args.measurement_slot,
            capabilities=capabilities,
        )
        return

    if args.command == "math-clear":
        math_clear_command(args.function, capabilities=capabilities)
        return

    configure_values = (args.math_operation, args.source1, args.source2)
    if args.math_operator_query:
        if any(value is not None for value in configure_values):
            raise ParameterValidationError(
                "math-operator --query cannot be combined with configure options."
            )
        math_operator_query_commands(args.function, capabilities=capabilities)
        return
    if any(value is None for value in configure_values):
        raise ParameterValidationError(
            "math-operator configure requires --operation, --source1, and --source2."
        )
    math_operator_commands(
        args.function,
        args.math_operation,
        args.source1,
        args.source2,
        capabilities=capabilities,
    )
