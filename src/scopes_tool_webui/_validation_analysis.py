"""WebUI parameter validation for measurement, statistics, DVM, FFT, and Math commands."""

from __future__ import annotations

from typing import Any

from scopes_tool_core.channel import validate_analog_channel
from scopes_tool_core.dvm import normalize_dvm_mode
from scopes_tool_core.fft import fft_configure_commands
from scopes_tool_core.math import (
    math_operator_commands,
    math_filter_commands,
    math_filter_query_commands,
    math_transform_commands,
    math_transform_query_commands,
    math_visualization_commands,
    math_visualization_query_commands,
    normalize_math_composite_operation,
    normalize_math_operation,
    normalize_math_source,
    validate_finite_number,
    validate_positive,
)
from scopes_tool_core.measurements import (
    measurement_install_command,
    normalize_measurement_item,
    normalize_statistics_mode,
    normalize_measurement_window,
    validate_measure_statistics_supported,
    validate_statistics_max_count,
)

from ._validation_shared import (
    WebUIRequestError,
    _action,
    _finite_number,
    _integer,
    _reject_query_parameters,
    _require_boolean,
    _require_parameter,
)


def _validate_analysis_parameters(
    command: str, parameters: dict[str, Any], capabilities: Any
) -> bool:
    """Validate analysis-surface parameters; return True when the command is handled."""

    if command == "measure-install":
        _require_parameter(parameters, "source_channel", command)
        _require_parameter(parameters, "item", command)
        try:
            parameters["source_channel"] = validate_analog_channel(
                _integer(parameters["source_channel"], "source_channel"), capabilities
            )
            parameters["item"] = normalize_measurement_item(parameters["item"])
            measurement_install_command(parameters["item"], capabilities=capabilities)
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
    elif command == "measurement-statistics":
        try:
            validate_measure_statistics_supported(capabilities)
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        action = parameters.setdefault("action", "query")
        if action not in {"query", "set", "reset"}:
            raise WebUIRequestError(
                "measurement-statistics action must be query, set, or reset"
            )
        setting_names = (
            "mode",
            "display_enabled",
            "max_count_mode",
            "max_count",
            "relative_stddev_enabled",
        )
        if action == "set":
            for name in (
                "mode",
                "display_enabled",
                "max_count_mode",
                "relative_stddev_enabled",
            ):
                _require_parameter(parameters, name, command)
            try:
                parameters["mode"] = normalize_statistics_mode(parameters["mode"])
                if parameters["mode"] != "all":
                    raise WebUIRequestError(
                        "measurement-statistics mode must be all"
                    )
                _require_boolean(parameters["display_enabled"], "display_enabled")
                _require_boolean(
                    parameters["relative_stddev_enabled"],
                    "relative_stddev_enabled",
                )
                if parameters["max_count_mode"] not in {"infinite", "numeric"}:
                    raise WebUIRequestError(
                        "max_count_mode must be infinite or numeric"
                    )
                if parameters["max_count_mode"] == "numeric":
                    _require_parameter(parameters, "max_count", command)
                    parameters["max_count"] = validate_statistics_max_count(
                        _integer(parameters["max_count"], "max_count")
                    )
                else:
                    parameters.pop("max_count", None)
            except WebUIRequestError:
                raise
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, setting_names, command)
    elif command in {"measure-show", "measure-source", "measure-window"}:
        action = _action(parameters, command)
        if command == "measure-show":
            if action == "set":
                if "enabled" in parameters:
                    _require_boolean(parameters["enabled"], "enabled")
                    if not parameters["enabled"] and capabilities.series != "4000X":
                        raise WebUIRequestError(
                            f"measure-show OFF is not supported by {capabilities.series} models"
                        )
            else:
                _reject_query_parameters(parameters, ("enabled",), command)
        elif command == "measure-source":
            if action == "set":
                _require_parameter(parameters, "source_channel", command)
                parameters["source_channel"] = validate_analog_channel(
                    _integer(parameters["source_channel"], "source_channel"), capabilities
                )
                if "source2_channel" in parameters:
                    parameters["source2_channel"] = validate_analog_channel(
                        _integer(parameters["source2_channel"], "source2_channel"), capabilities
                    )
            else:
                _reject_query_parameters(parameters, ("source_channel", "source2_channel"), command)
        else:
            if action == "set":
                _require_parameter(parameters, "window", command)
                try:
                    parameters["window"] = normalize_measurement_window(parameters["window"])
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
                if parameters["window"] == "GATE" and capabilities.series != "4000X":
                    raise WebUIRequestError(
                        f"measurement window gate is not supported by {capabilities.series} models"
                    )
            else:
                _reject_query_parameters(parameters, ("window",), command)
    elif command in {"dvm-enable", "dvm-source", "dvm-mode", "dvm-auto-range"}:
        action = _action(parameters, command)
        value_name = {
            "dvm-enable": "enabled",
            "dvm-source": "channel",
            "dvm-mode": "mode",
            "dvm-auto-range": "enabled",
        }[command]
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if value_name == "enabled":
                    _require_boolean(parameters[value_name], value_name)
                elif command == "dvm-source":
                    parameters[value_name] = validate_analog_channel(
                        _integer(parameters[value_name], value_name), capabilities
                    )
                else:
                    normalize_dvm_mode(parameters[value_name])
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command == "fft":
        action = _action(parameters, command)
        parameters["function"] = _integer(parameters.get("function", 1), "function")
        if action == "set":
            _require_parameter(parameters, "source_channel", command)
            try:
                parameters["source_channel"] = validate_analog_channel(
                    _integer(parameters["source_channel"], "source_channel"), capabilities
                )
                for name in ("center_hz", "span_hz", "start_hz", "stop_hz"):
                    if name in parameters:
                        parameters[name] = _finite_number(parameters[name], name)
                if "detection_points" in parameters:
                    parameters["detection_points"] = _integer(
                        parameters["detection_points"], "detection_points"
                    )
                if "display" in parameters:
                    _require_boolean(parameters["display"], "display")
                fft_configure_commands(
                    parameters["function"],
                    parameters["source_channel"],
                    units=parameters.get("units"),
                    window=parameters.get("window"),
                    center_hz=parameters.get("center_hz"),
                    span_hz=parameters.get("span_hz"),
                    display=parameters.get("display"),
                    fft_operation=parameters.get("fft_operation", "fft"),
                    start_hz=parameters.get("start_hz"),
                    stop_hz=parameters.get("stop_hz"),
                    gate=parameters.get("gate"),
                    phase_reference=parameters.get("phase_reference"),
                    detection_type=parameters.get("detection_type"),
                    detection_points=parameters.get("detection_points"),
                    capabilities=capabilities,
                )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(
                parameters,
                (
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
                ),
                command,
            )
    elif command in {
        "math-display",
        "math-vertical",
        "math-operator",
        "math-transform",
        "math-filter",
        "math-visualization",
        "math-composite-source",
    }:
        action = _action(parameters, command)
        if command != "math-composite-source":
            parameters["function"] = _integer(parameters.get("function", 1), "function")
        if command == "math-display":
            if action == "set":
                _require_parameter(parameters, "enabled", command)
                _require_boolean(parameters["enabled"], "enabled")
            else:
                _reject_query_parameters(parameters, ("enabled",), command)
        elif command == "math-vertical":
            names = ("scale", "range_value", "offset")
            if action == "set":
                if not any(name in parameters for name in names):
                    raise WebUIRequestError("math-vertical set requires scale, range_value, or offset")
                try:
                    for name in ("scale", "range_value"):
                        if name in parameters:
                            parameters[name] = validate_positive(
                                _finite_number(parameters[name], name), name
                            )
                    if "offset" in parameters:
                        parameters["offset"] = validate_finite_number(
                            _finite_number(parameters["offset"], "offset"), "offset"
                        )
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, names, command)
        elif command == "math-operator":
            names = ("operation", "source1", "source2")
            if action == "set":
                for name in names:
                    _require_parameter(parameters, name, command)
                try:
                    parameters["operation"] = normalize_math_operation(parameters["operation"])
                    parameters["source1"] = normalize_math_source(
                        parameters["source1"], capabilities=capabilities
                    )
                    parameters["source2"] = normalize_math_source(
                        parameters["source2"], capabilities=capabilities
                    )
                    math_operator_commands(parameters["function"], parameters["operation"],
                        parameters["source1"], parameters["source2"], capabilities=capabilities)
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, names, command)
        elif command == "math-composite-source":
            names = ("operation", "source1", "source2")
            if action == "set":
                for name in names:
                    _require_parameter(parameters, name, command)
                try:
                    parameters["operation"] = normalize_math_composite_operation(parameters["operation"])
                    parameters["source1"] = normalize_math_source(
                        parameters["source1"], capabilities=capabilities
                    )
                    parameters["source2"] = normalize_math_source(
                        parameters["source2"], capabilities=capabilities
                    )
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, names, command)
        else:
            names = {
                "math-transform": (
                    "operation", "source", "input_offset", "gain", "linear_offset"
                ),
                "math-filter": (
                    "operation", "source", "cutoff_hz", "average_count", "smooth_points"
                ),
                "math-visualization": (
                    "operation", "source", "source2", "measurement", "measurement_slot"
                ),
            }[command]
            try:
                if action == "query":
                    _reject_query_parameters(parameters, names, command)
                    query = {
                        "math-transform": math_transform_query_commands,
                        "math-filter": math_filter_query_commands,
                        "math-visualization": math_visualization_query_commands,
                    }[command]
                    query(parameters["function"], capabilities=capabilities)
                else:
                    _require_parameter(parameters, "operation", command)
                    if command in {"math-transform", "math-filter"}:
                        _require_parameter(parameters, "source", command)
                    for name in (
                        "input_offset", "gain", "linear_offset", "cutoff_hz"
                    ):
                        if name in parameters:
                            parameters[name] = _finite_number(parameters[name], name)
                    for name in ("average_count", "smooth_points", "measurement_slot"):
                        if name in parameters:
                            parameters[name] = _integer(parameters[name], name)
                    if command == "math-transform":
                        math_transform_commands(
                            parameters["function"],
                            parameters["operation"],
                            parameters["source"],
                            input_offset=parameters.get("input_offset"),
                            gain=parameters.get("gain"),
                            linear_offset=parameters.get("linear_offset"),
                            capabilities=capabilities,
                        )
                    elif command == "math-filter":
                        math_filter_commands(
                            parameters["function"],
                            parameters["operation"],
                            parameters["source"],
                            cutoff_hz=parameters.get("cutoff_hz"),
                            average_count=parameters.get("average_count"),
                            smooth_points=parameters.get("smooth_points"),
                            capabilities=capabilities,
                        )
                    else:
                        math_visualization_commands(
                            parameters["function"],
                            parameters["operation"],
                            source=parameters.get("source"),
                            source2=parameters.get("source2"),
                            measurement=parameters.get("measurement"),
                            measurement_slot=parameters.get("measurement_slot"),
                            capabilities=capabilities,
                        )
            except WebUIRequestError:
                raise
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
    elif command == "math-clear":
        parameters["function"] = _integer(parameters.get("function", 1), "function")
    elif command == "check-error":
        max_reads = _integer(parameters.get("max_reads", 20), "max_reads")
        if max_reads < 1:
            raise WebUIRequestError("max_reads must be at least 1")
        parameters["max_reads"] = max_reads
    elif command == "measure":
        try:
            parameters["item"] = normalize_measurement_item(parameters.get("item", "vpp"))
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        parameters["channel"] = validate_analog_channel(
            _integer(parameters.get("channel", 1), "channel"), capabilities
        )
        if "reference_channel" in parameters:
            parameters["reference_channel"] = validate_analog_channel(
                _integer(parameters["reference_channel"], "reference_channel"), capabilities
            )
        for name in ("time_s", "level"):
            if name in parameters:
                parameters[name] = _finite_number(parameters[name], name)
        if "occurrence" in parameters:
            parameters["occurrence"] = _integer(parameters["occurrence"], "occurrence")
        if "slope" in parameters and parameters["slope"] not in {"positive", "negative"}:
            raise WebUIRequestError("slope must be positive or negative")
    else:
        return False
    return True
