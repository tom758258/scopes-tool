"""Worker argument normalization and inventory for Math commands."""

from __future__ import annotations

import math
from typing import Any

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.fft import (
    FFT_DETECTION_TYPES,
    FFT_GATES,
    FFT_OPERATIONS,
    FFT_PHASE_REFERENCES,
    fft_advanced_query_commands,
    fft_configure_commands,
    fft_query_commands,
)
from scopes_tool_core.math import (
    math_clear_command,
    math_composite_source_commands,
    math_composite_source_query_commands,
    math_display_command,
    math_display_query,
    math_filter_commands,
    math_filter_query_commands,
    math_operator_commands,
    math_operator_query_commands,
    math_transform_commands,
    math_transform_query_commands,
    math_visualization_commands,
    math_visualization_query_commands,
    math_vertical_commands,
    math_vertical_query_commands,
)


_MATH_WORKER_ARGUMENTS = {
    "fft": frozenset(
        {
            "function",
            "query",
            "source_channel",
            "units",
            "window",
            "center_hz",
            "span_hz",
            "display",
            "fft_operation",
            "start_hz",
            "stop_hz",
            "gate",
            "phase_reference",
            "detection_type",
            "detection_points",
        }
    ),
    "math-display": frozenset({"function", "on", "off", "query"}),
    "math-vertical": frozenset(
        {"function", "query", "scale", "range", "offset"}
    ),
    "math-operator": frozenset(
        {"function", "query", "operation", "source1", "source2"}
    ),
    "math-composite-source": frozenset(
        {"query", "operation", "source1", "source2"}
    ),
    "math-transform": frozenset(
        {
            "function",
            "query",
            "operation",
            "source",
            "input_offset",
            "gain",
            "linear_offset",
        }
    ),
    "math-filter": frozenset(
        {
            "function",
            "query",
            "operation",
            "source",
            "cutoff_hz",
            "average_count",
            "smooth_points",
        }
    ),
    "math-visualization": frozenset(
        {
            "function",
            "query",
            "operation",
            "source",
            "source2",
            "measurement",
            "measurement_slot",
        }
    ),
    "math-clear": frozenset({"function"}),
}

_MATH_DOMAIN_COMMANDS = frozenset(_MATH_WORKER_ARGUMENTS)


def _normalize_math_worker_arguments(
    command: str, arguments: dict[str, Any], runtime: WorkerRuntime
) -> dict[str, Any]:
    if command not in _MATH_WORKER_ARGUMENTS:
        return arguments

    allowed = _MATH_WORKER_ARGUMENTS[command]
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for {command}: {sorted(unknown)[0]}"
        )
    capabilities = capabilities_for_model_id(runtime.model)

    if command == "fft":
        configure_keys = allowed - {"function", "query"}
        configure_arguments = configure_keys & set(arguments)
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError("fft argument query must be exactly true")
            if configure_arguments:
                raise OscilloscopeError(
                    "fft query cannot be combined with configure arguments"
                )
            fft_query_commands(
                arguments.get("function"), capabilities=capabilities
            )
            if capabilities.supports_advanced_fft:
                fft_advanced_query_commands(
                    arguments.get("function"), capabilities=capabilities
                )
            return dict(arguments)
        if "source_channel" not in arguments:
            raise OscilloscopeError(
                "fft configure requires source_channel unless query is used"
            )
        canonical_values = {
            "fft_operation": FFT_OPERATIONS,
            "gate": FFT_GATES,
            "phase_reference": FFT_PHASE_REFERENCES,
            "detection_type": FFT_DETECTION_TYPES,
            "units": ("decibel", "vrms"),
            "window": (
                "rectangular",
                "hanning",
                "flattop",
                "bharris",
                "bartlett",
            ),
            "display": ("on", "off"),
        }
        for key, choices in canonical_values.items():
            if key in arguments and arguments[key] not in choices:
                raise OscilloscopeError(
                    f"fft argument {key} must be one of: {', '.join(choices)}"
                )
        fft_configure_commands(
            arguments.get("function"),
            arguments["source_channel"],
            units=arguments.get("units"),
            window=arguments.get("window"),
            center_hz=arguments.get("center_hz"),
            span_hz=arguments.get("span_hz"),
            display=(
                None
                if "display" not in arguments
                else arguments["display"] == "on"
            ),
            fft_operation=arguments.get("fft_operation", "fft"),
            start_hz=arguments.get("start_hz"),
            stop_hz=arguments.get("stop_hz"),
            gate=arguments.get("gate"),
            phase_reference=arguments.get("phase_reference"),
            detection_type=arguments.get("detection_type"),
            detection_points=arguments.get("detection_points"),
            capabilities=capabilities,
        )
        return dict(arguments)

    if command == "math-composite-source":
        configure_keys = ("operation", "source1", "source2")
        configure_arguments = {
            key: arguments[key] for key in configure_keys if key in arguments
        }
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(
                    "math-composite-source argument query must be exactly true"
                )
            if configure_arguments:
                raise OscilloscopeError(
                    "math-composite-source query cannot be combined with "
                    "configure arguments"
                )
            math_composite_source_query_commands(capabilities=capabilities)
            return dict(arguments)
        if len(configure_arguments) != len(configure_keys):
            raise OscilloscopeError(
                "math-composite-source configure requires operation, "
                "source1, and source2"
            )
        math_composite_source_commands(
            arguments["operation"],
            arguments["source1"],
            arguments["source2"],
            capabilities=capabilities,
        )
        return dict(arguments)

    function = arguments.get("function")
    if not isinstance(function, int) or isinstance(function, bool):
        raise OscilloscopeError(f"{command} argument function must be an integer")

    if command == "math-display":
        actions = [key for key in ("on", "off", "query") if key in arguments]
        for key in actions:
            if arguments[key] is not True:
                raise OscilloscopeError(
                    f"math-display argument {key} must be exactly true"
                )
        if len(actions) != 1:
            raise OscilloscopeError(
                "math-display requires exactly one of on, off, or query"
            )
        if actions[0] == "query":
            math_display_query(function, capabilities=capabilities)
        else:
            math_display_command(
                function, actions[0] == "on", capabilities=capabilities
            )
        return dict(arguments)

    if command == "math-clear":
        math_clear_command(function, capabilities=capabilities)
        return dict(arguments)

    if command == "math-operator":
        configure_keys = ("operation", "source1", "source2")
        configure_arguments = {
            key: arguments[key] for key in configure_keys if key in arguments
        }
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(
                    "math-operator argument query must be exactly true"
                )
            if configure_arguments:
                raise OscilloscopeError(
                    "math-operator query cannot be combined with configure arguments"
                )
            math_operator_query_commands(function, capabilities=capabilities)
            return dict(arguments)
        if len(configure_arguments) != len(configure_keys):
            raise OscilloscopeError(
                "math-operator configure requires operation, source1, and source2"
            )
        math_operator_commands(
            function,
            arguments["operation"],
            arguments["source1"],
            arguments["source2"],
            capabilities=capabilities,
        )
        return dict(arguments)

    if command == "math-transform":
        configure_keys = (
            "operation",
            "source",
            "input_offset",
            "gain",
            "linear_offset",
        )
        configure_arguments = {
            key: arguments[key] for key in configure_keys if key in arguments
        }
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(
                    "math-transform argument query must be exactly true"
                )
            if configure_arguments:
                raise OscilloscopeError(
                    "math-transform query cannot be combined with configure arguments"
                )
            math_transform_query_commands(function, capabilities=capabilities)
            return dict(arguments)
        if "operation" not in arguments or "source" not in arguments:
            raise OscilloscopeError(
                "math-transform configure requires operation and source"
            )
        math_transform_commands(
            function,
            arguments["operation"],
            arguments["source"],
            input_offset=arguments.get("input_offset"),
            gain=arguments.get("gain"),
            linear_offset=arguments.get("linear_offset"),
            capabilities=capabilities,
        )
        return dict(arguments)

    if command == "math-filter":
        configure_keys = (
            "operation",
            "source",
            "cutoff_hz",
            "average_count",
            "smooth_points",
        )
        configure_arguments = {
            key: arguments[key] for key in configure_keys if key in arguments
        }
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(
                    "math-filter argument query must be exactly true"
                )
            if configure_arguments:
                raise OscilloscopeError(
                    "math-filter query cannot be combined with configure arguments"
                )
            math_filter_query_commands(function, capabilities=capabilities)
            return dict(arguments)
        if "operation" not in arguments or "source" not in arguments:
            raise OscilloscopeError(
                "math-filter configure requires operation and source"
            )
        math_filter_commands(
            function,
            arguments["operation"],
            arguments["source"],
            cutoff_hz=arguments.get("cutoff_hz"),
            average_count=arguments.get("average_count"),
            smooth_points=arguments.get("smooth_points"),
            capabilities=capabilities,
        )
        return dict(arguments)

    if command == "math-visualization":
        configure_keys = (
            "operation",
            "source",
            "source2",
            "measurement",
            "measurement_slot",
        )
        configure_arguments = {
            key: arguments[key] for key in configure_keys if key in arguments
        }
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(
                    "math-visualization argument query must be exactly true"
                )
            if configure_arguments:
                raise OscilloscopeError(
                    "math-visualization query cannot be combined with "
                    "configure arguments"
                )
            math_visualization_query_commands(
                function, capabilities=capabilities
            )
            return dict(arguments)
        if "operation" not in arguments:
            raise OscilloscopeError(
                "math-visualization configure requires operation"
            )
        math_visualization_commands(
            function,
            arguments["operation"],
            source=arguments.get("source"),
            source2=arguments.get("source2"),
            measurement=arguments.get("measurement"),
            measurement_slot=arguments.get("measurement_slot"),
            capabilities=capabilities,
        )
        return dict(arguments)

    setters = {
        key: arguments[key]
        for key in ("scale", "range", "offset")
        if key in arguments
    }
    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                "math-vertical argument query must be exactly true"
            )
        if setters:
            raise OscilloscopeError(
                "math-vertical query cannot be combined with configure arguments"
            )
        math_vertical_query_commands(function, capabilities=capabilities)
        return dict(arguments)
    if not setters:
        raise OscilloscopeError(
            "math-vertical configure requires scale, range, or offset"
        )
    for key, value in setters.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OscilloscopeError(
                f"math-vertical argument {key} must be a finite number"
            )
        try:
            finite = math.isfinite(float(value))
        except (TypeError, ValueError, OverflowError):
            finite = False
        if not finite:
            raise OscilloscopeError(
                f"math-vertical argument {key} must be a finite number"
            )
        if key in {"scale", "range"} and value <= 0:
            raise OscilloscopeError(
                f"math-vertical argument {key} must be greater than zero"
            )
    math_vertical_commands(
        function,
        scale=setters.get("scale"),
        range_value=setters.get("range"),
        offset=setters.get("offset"),
        capabilities=capabilities,
    )
    return dict(arguments)
