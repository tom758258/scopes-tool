"""WebUI parameter validation for acquisition, timebase, channel, display,
reference, cursor, annotation, WGEN, demo, save, setup, capture, screenshot,
and autoscale commands."""

from __future__ import annotations

from typing import Any

from scopes_tool_core.acquisition import (
    normalize_acquisition_type,
    validate_acquisition_count,
)
from scopes_tool_core.channel import (
    normalize_channel_coupling,
    normalize_channel_impedance,
    normalize_channel_units,
    validate_analog_channel,
    validate_channel_impedance_supported,
    validate_channel_label,
    validate_channel_offset,
    validate_channel_range,
    validate_channel_scale,
    validate_probe_ratio,
    validate_probe_skew,
)
from scopes_tool_core.cursor import resolve_cursor_function, validate_cursor_request
from scopes_tool_core.display import (
    normalize_annotation_background,
    normalize_annotation_color,
    validate_annotation_slot,
    validate_annotation_text,
    validate_annotation_x,
    validate_annotation_y,
    validate_display_intensity,
    validate_display_persistence,
)
from scopes_tool_core.demo import validate_demo_function, validate_demo_phase
from scopes_tool_core.planning import resolve_capture_channels
from scopes_tool_core.reference import validate_reference_label, validate_reference_slot
from scopes_tool_core.save_export import (
    SAVE_IMAGE_FORMATS,
    SAVE_IMAGE_PALETTES,
    SAVE_WAVEFORM_FORMATS,
    validate_save_filename_base,
    validate_save_quoted_string,
    validate_save_waveform_length,
)
from scopes_tool_core.timebase import (
    validate_timebase_position,
    validate_timebase_reference,
    validate_timebase_scale,
)
from scopes_tool_core.wgen import (
    validate_wgen_amplitude,
    validate_wgen_frequency,
    validate_wgen_function,
    validate_wgen_load,
    validate_wgen_offset,
)

from ._validation_shared import (
    WebUIRequestError,
    _action,
    _csv_values,
    _finite_number,
    _integer,
    _reject_query_parameters,
    _require_boolean,
    _require_parameter,
)


def _autoscale_channels(value: Any, capabilities: Any) -> list[int] | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    tokens = _csv_values(value)
    if not tokens:
        return None
    channels = []
    for token in tokens:
        if token.lower() == "all":
            raise WebUIRequestError(
                "autoscale channels must contain analog channel numbers, not all"
            )
        if not token.isdigit():
            raise WebUIRequestError(f"invalid autoscale channel: {token}")
        channels.append(int(token))
    try:
        return [validate_analog_channel(channel, capabilities) for channel in channels]
    except WebUIRequestError:
        raise
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc


def _capture_channels(value: Any, capabilities: Any) -> list[int]:
    if isinstance(value, str):
        raw_values = [item.strip() for item in value.split(",") if item.strip()]
        if not raw_values:
            raise WebUIRequestError("channels are required")
        raw = [int(item) if item.isdigit() else item for item in raw_values]
    elif isinstance(value, (list, tuple)):
        if not value:
            raise WebUIRequestError("channels are required")
        raw_values = [str(item).strip() for item in value if str(item).strip()]
        if not raw_values:
            raise WebUIRequestError("channels are required")
        raw = [int(item) if item.isdigit() else item for item in raw_values]
    elif value is None:
        raise WebUIRequestError("channels are required")
    else:
        raise WebUIRequestError("channels must be a comma-separated string or list")
    try:
        return list(resolve_capture_channels(raw, capabilities))
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc


def _normalize_acquisition_type(value: Any) -> str:
    normalized = normalize_acquisition_type(value)
    return {
        "NORMal": "normal",
        "AVERage": "average",
        "HRESolution": "high_resolution",
        "PEAK": "peak",
    }[normalized]


def _cursor_function(parameters: dict[str, Any], capabilities: Any) -> str | None:
    """Normalize the optional explicit cursor function before position checks."""

    if "function" not in parameters:
        return None
    try:
        resolved = resolve_cursor_function(
            capabilities,
            parameters.get("function"),
            x_axis=any(parameters.get(name) is not None for name in ("x1", "x2")),
            y_axis=any(parameters.get(name) is not None for name in ("y1", "y2")),
        )
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc
    parameters["function"] = resolved
    return resolved


def _validate_cursor_set_parameters(
    parameters: dict[str, Any], command: str, capabilities: Any, function: str | None
) -> None:
    positions = ("x1", "x2", "y1", "y2")
    if function in ("off", "waveform"):
        for name in positions:
            parameters.pop(name, None)
        parameters.pop("source_channel", None)
        return
    has_position = any(parameters.get(name) is not None for name in positions)
    if not has_position and function is None:
        raise WebUIRequestError(
            "cursor set requires at least one of x1, x2, y1, or y2"
        )
    if has_position:
        _require_parameter(parameters, "source_channel", command)
    try:
        if parameters.get("source_channel") is not None:
            parameters["source_channel"] = validate_analog_channel(
                _integer(parameters["source_channel"], "source_channel"),
                capabilities,
            )
        for name in positions:
            if parameters.get(name) is not None:
                parameters[name] = _finite_number(parameters[name], name)
        validate_cursor_request(
            capabilities,
            x1_seconds=parameters.get("x1"),
            x2_seconds=parameters.get("x2"),
            y1_volts=parameters.get("y1"),
            y2_volts=parameters.get("y2"),
            function=function,
        )
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc


def _validate_control_parameters(
    command: str, parameters: dict[str, Any], capabilities: Any, mode: str
) -> bool:
    """Validate control-surface parameters; return True when the command is handled."""

    if command == "acquisition":
        action = parameters.setdefault("action", "query")
        if action not in {"query", "set"}:
            raise WebUIRequestError("acquisition action must be query or set")
        if action == "set" and "type" not in parameters and "count" not in parameters:
            raise WebUIRequestError("acquisition set requires type or count")
        if "type" in parameters:
            try:
                parameters["type"] = _normalize_acquisition_type(parameters["type"])
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
            if capabilities.acquisition_modes is not None and parameters["type"] not in capabilities.acquisition_modes:
                raise WebUIRequestError("acquisition type is unsupported for this model")
        if "count" in parameters:
            try:
                parameters["count"] = validate_acquisition_count(
                    _integer(parameters["count"], "count")
                )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
            if capabilities.average_counts is not None and parameters["count"] not in capabilities.average_counts:
                raise WebUIRequestError("average count is unsupported for this model")
        if mode == "dry-run" and action != "query":
            raise WebUIRequestError("dry-run acquisition supports query only")
    elif command == "timebase-scale":
        action = _action(parameters, command)
        if action == "set":
            _require_parameter(parameters, "seconds_per_division", command)
            try:
                parameters["seconds_per_division"] = validate_timebase_scale(
                    _finite_number(
                        parameters["seconds_per_division"], "seconds_per_division"
                    )
                )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, ("seconds_per_division",), command)
    elif command == "timebase-position":
        action = _action(parameters, command)
        if action == "set":
            _require_parameter(parameters, "position_seconds", command)
            try:
                parameters["position_seconds"] = validate_timebase_position(
                    _finite_number(parameters["position_seconds"], "position_seconds")
                )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, ("position_seconds",), command)
    elif command == "timebase-reference":
        action = _action(parameters, command)
        if action == "set":
            _require_parameter(parameters, "reference", command)
            try:
                parameters["reference"] = validate_timebase_reference(
                    parameters["reference"]
                )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, ("reference",), command)
    elif command in {"channel-display", "channel-scale"}:
        action = parameters.setdefault("action", "query")
        if action not in {"query", "set"}:
            raise WebUIRequestError(f"{command} action must be query or set")
        channel = _integer(parameters.get("channel", 1), "channel")
        parameters["channel"] = validate_analog_channel(channel, capabilities)
        if action == "set":
            if command == "channel-display":
                if not isinstance(parameters.get("enabled"), bool):
                    raise WebUIRequestError("enabled must be a boolean for channel-display set")
            else:
                if "volts_per_division" not in parameters:
                    raise WebUIRequestError("channel-scale set requires volts_per_division")
                try:
                    parameters["volts_per_division"] = validate_channel_scale(
                        _finite_number(parameters["volts_per_division"], "volts_per_division")
                    )
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
    elif command in {
        "channel-label",
        "channel-offset",
        "channel-coupling",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
    }:
        action = _action(parameters, command)
        parameters["channel"] = validate_analog_channel(
            _integer(parameters.get("channel", 1), "channel"), capabilities
        )
        if (command == "channel-units" and capabilities.channel_units_channels is not None
                and parameters["channel"] not in capabilities.channel_units_channels):
            raise WebUIRequestError("channel units are unsupported for this channel")
        value_name = {
            "channel-label": "text",
            "channel-offset": "volts",
            "channel-coupling": "coupling",
            "channel-probe": "ratio",
            "channel-bandwidth-limit": "enabled",
            "channel-impedance": "impedance",
            "channel-invert": "enabled",
            "channel-range": "volts",
            "channel-units": "units",
            "channel-vernier": "enabled",
            "channel-probe-skew": "seconds",
        }[command]
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if command == "channel-label":
                    parameters[value_name] = validate_channel_label(parameters[value_name], capabilities)
                elif command == "channel-offset":
                    parameters[value_name] = validate_channel_offset(
                        _finite_number(parameters[value_name], value_name)
                    )
                elif command == "channel-coupling":
                    parameters[value_name] = normalize_channel_coupling(
                        parameters[value_name]
                    )
                elif command == "channel-probe":
                    parameters[value_name] = validate_probe_ratio(
                        _finite_number(parameters[value_name], value_name)
                    )
                elif command in {
                    "channel-bandwidth-limit",
                    "channel-invert",
                    "channel-vernier",
                }:
                    _require_boolean(parameters[value_name], value_name)
                elif command == "channel-impedance":
                    normalized_impedance = normalize_channel_impedance(
                        parameters[value_name]
                    )
                    validate_channel_impedance_supported(
                        normalized_impedance, capabilities
                    )
                    parameters[value_name] = normalized_impedance
                elif command == "channel-range":
                    parameters[value_name] = validate_channel_range(
                        _finite_number(parameters[value_name], value_name)
                    )
                elif command == "channel-units":
                    parameters[value_name] = normalize_channel_units(
                        parameters[value_name]
                    )
                else:
                    parameters[value_name] = validate_probe_skew(
                        _finite_number(parameters[value_name], value_name)
                    )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command in {
        "display-label",
        "display-persistence",
        "display-intensity",
        "display-vectors",
    }:
        action = _action(parameters, command)
        value_name = {
            "display-label": "enabled",
            "display-persistence": "mode",
            "display-intensity": "value",
            "display-vectors": None,
        }[command]
        if action == "set":
            if value_name is not None:
                _require_parameter(parameters, value_name, command)
            try:
                if command == "display-label":
                    _require_boolean(parameters[value_name], value_name)
                elif command == "display-persistence":
                    mode = parameters["mode"]
                    if mode not in {"minimum", "infinite", "timed"}:
                        raise WebUIRequestError(
                            "display-persistence mode must be minimum, infinite, or timed"
                        )
                    value = mode
                    if mode == "timed":
                        _require_parameter(parameters, "seconds", command)
                        parameters["seconds"] = _finite_number(
                            parameters["seconds"], "seconds"
                        )
                        value = parameters["seconds"]
                    validate_display_persistence(value, capabilities)
                elif command == "display-intensity":
                    parameters[value_name] = validate_display_intensity(
                        _integer(parameters[value_name], value_name)
                    )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            query_names = (
                ("mode", "seconds")
                if command == "display-persistence"
                else ((value_name,) if value_name else ())
            )
            _reject_query_parameters(parameters, query_names, command)
    elif command == "reference-save":
        _require_parameter(parameters, "slot", command)
        _require_parameter(parameters, "source_channel", command)
        try:
            parameters["slot"] = validate_reference_slot(
                _integer(parameters["slot"], "slot"), capabilities
            )
            parameters["source_channel"] = validate_analog_channel(
                _integer(parameters["source_channel"], "source_channel"), capabilities
            )
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
    elif command in {"reference-display", "reference-label"}:
        action = _action(parameters, command)
        try:
            parameters["slot"] = validate_reference_slot(
                _integer(parameters.get("slot", 1), "slot"), capabilities
            )
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        value_name = "enabled" if command == "reference-display" else "label"
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if command == "reference-display":
                    _require_boolean(parameters[value_name], value_name)
                else:
                    parameters[value_name] = validate_reference_label(parameters[value_name])
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command in {"reference-clear", "reference-query"}:
        try:
            parameters["slot"] = validate_reference_slot(
                _integer(parameters.get("slot", 1), "slot"), capabilities
            )
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
    elif command == "cursor-set":
        function = _cursor_function(parameters, capabilities)
        _validate_cursor_set_parameters(parameters, command, capabilities, function)
    elif command in {
        "annotation-query",
        "annotation-set",
        "annotation-on",
        "annotation-off",
        "annotation-clear",
    }:
        try:
            parameters["slot"] = validate_annotation_slot(
                _integer(parameters.get("slot", 1), "slot"), capabilities
            )
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        if command == "annotation-set":
            setter_names = ("text", "color", "background", "x", "y")
            if (
                parameters.get("x") is not None
                or parameters.get("y") is not None
            ) and not capabilities.supports_annotation_position:
                raise WebUIRequestError(
                    "annotation position is not supported by this model"
                )
            provided = [
                name for name in setter_names if parameters.get(name) is not None
            ]
            if not provided:
                raise WebUIRequestError(
                    "annotation set requires at least one of text, color, background, x, or y"
                )
            try:
                if parameters.get("text") is not None:
                    parameters["text"] = validate_annotation_text(parameters["text"])
                if parameters.get("color") is not None:
                    parameters["color"] = normalize_annotation_color(parameters["color"])
                if parameters.get("background") is not None:
                    parameters["background"] = normalize_annotation_background(
                        parameters["background"]
                    )
                if parameters.get("x") is not None:
                    parameters["x"] = validate_annotation_x(
                        _integer(parameters["x"], "x")
                    )
                if parameters.get("y") is not None:
                    parameters["y"] = validate_annotation_y(
                        _integer(parameters["y"], "y")
                    )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
    elif command in {
        "wgen-output",
        "wgen-function",
        "wgen-frequency",
        "wgen-voltage",
        "wgen-offset",
        "wgen-load",
    }:
        action = _action(parameters, command)
        value_name = {
            "wgen-output": "enabled",
            "wgen-function": "function",
            "wgen-frequency": "frequency_hz",
            "wgen-voltage": "amplitude",
            "wgen-offset": "offset_volts",
            "wgen-load": "load",
        }[command]
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if command == "wgen-output":
                    _require_boolean(parameters[value_name], value_name)
                elif command == "wgen-function":
                    parameters[value_name] = validate_wgen_function(
                        parameters[value_name]
                    )
                elif command == "wgen-frequency":
                    parameters[value_name] = validate_wgen_frequency(
                        _finite_number(parameters[value_name], value_name),
                        series=capabilities.series,
                    )
                elif command == "wgen-voltage":
                    parameters[value_name] = validate_wgen_amplitude(
                        _finite_number(parameters[value_name], value_name),
                        series=capabilities.series,
                    )
                elif command == "wgen-offset":
                    parameters[value_name] = validate_wgen_offset(
                        _finite_number(parameters[value_name], value_name),
                        series=capabilities.series,
                    )
                else:
                    parameters[value_name] = validate_wgen_load(parameters[value_name])
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command in {
        "demo-output",
        "demo-function",
        "demo-phase",
    }:
        action = _action(parameters, command)
        value_name = {
            "demo-output": "enabled",
            "demo-function": "function",
            "demo-phase": "degrees",
        }[command]
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if command == "demo-output":
                    _require_boolean(parameters[value_name], value_name)
                elif command == "demo-function":
                    validate_demo_function(parameters[value_name], capabilities)
                else:
                    parameters[value_name] = validate_demo_phase(
                        _finite_number(parameters[value_name], value_name)
                    )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command in {
        "save-pwd",
        "save-filename",
        "save-image-format",
        "save-image-palette",
        "save-image-ink-saver",
        "save-image-factors",
        "save-waveform-format",
        "save-waveform-length",
    }:
        action = _action(parameters, command)
        value_name = {
            "save-pwd": "path",
            "save-filename": "name",
            "save-image-format": "format",
            "save-image-palette": "palette",
            "save-image-ink-saver": "enabled",
            "save-image-factors": "enabled",
            "save-waveform-format": "format",
            "save-waveform-length": "points",
        }[command]
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if command == "save-pwd":
                    parameters[value_name] = validate_save_quoted_string(
                        parameters[value_name], label="Save path"
                    )
                elif command == "save-filename":
                    parameters[value_name] = validate_save_filename_base(parameters[value_name])
                elif command == "save-image-format":
                    if parameters[value_name] not in (capabilities.save_image_formats or SAVE_IMAGE_FORMATS):
                        raise ValueError(
                            f"image format must be one of: {', '.join(SAVE_IMAGE_FORMATS)}"
                        )
                elif command == "save-image-palette":
                    if parameters[value_name] not in SAVE_IMAGE_PALETTES:
                        raise ValueError(
                            f"image palette must be one of: {', '.join(SAVE_IMAGE_PALETTES)}"
                        )
                elif command in {"save-image-ink-saver", "save-image-factors"}:
                    _require_boolean(parameters[value_name], value_name)
                elif command == "save-waveform-format":
                    if parameters[value_name] not in (capabilities.save_waveform_formats or SAVE_WAVEFORM_FORMATS):
                        raise ValueError(
                            f"waveform format must be one of: {', '.join(SAVE_WAVEFORM_FORMATS)}"
                        )
                else:
                    parameters[value_name] = validate_save_waveform_length(
                        _integer(parameters[value_name], value_name)
                    )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command in {"save-image", "save-waveform"}:
        if command == "save-waveform":
            if capabilities.save_waveform_requires_source:
                _require_parameter(parameters, "source_channel", command)
            if "source_channel" in parameters:
                if not capabilities.save_waveform_requires_source:
                    raise WebUIRequestError("source_channel is unsupported for this model save-waveform")
                try:
                    parameters["source_channel"] = validate_analog_channel(
                        _integer(parameters["source_channel"], "source_channel"), capabilities)
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
        _require_parameter(parameters, "filename", command)
        try:
            parameters["filename"] = validate_save_quoted_string(
                parameters["filename"],
                label="Save image filename" if command == "save-image" else "Save waveform filename",
            )
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
    elif command == "capture":
        if "channels" not in parameters:
            parameters["channels"] = [1]
        parameters["channels"] = _capture_channels(parameters.get("channels"), capabilities)
        parameters["points"] = _integer(parameters.get("points", 1000), "points")
        if parameters["points"] not in {1000, 5000, 10000}:
            raise WebUIRequestError("points must be one of: 1000, 5000, 10000")
        parameters["format"] = str(parameters.get("format", "byte")).lower()
        if parameters["format"] not in {"byte", "word"}:
            raise WebUIRequestError("format must be byte or word")
        if parameters["format"] == "word" and not capabilities.supports_word_format:
            raise WebUIRequestError("word waveform format is not supported by this model")
    elif command == "screenshot":
        if not capabilities.supports_any_screenshot:
            raise WebUIRequestError("screenshot is unsupported for this model")
        parameters["background"] = str(parameters.get("background", "black")).lower()
        allowed_backgrounds = capabilities.screenshot_backgrounds
        if allowed_backgrounds is not None:
            if parameters["background"] not in allowed_backgrounds:
                raise WebUIRequestError("background is unsupported for this model")
        elif parameters["background"] not in {"black", "white"}:
            raise WebUIRequestError("background must be black or white")
    elif command == "autoscale":
        if not capabilities.autoscale_supports_optional_controls:
            supplied = [
                name for name in ("channels", "acquire_mode", "channels_mode")
                if name in parameters and parameters[name] not in (None, "", [], ())
            ]
            if supplied:
                raise WebUIRequestError("autoscale optional controls are unsupported for this model")
        parameters["channels"] = _autoscale_channels(
            parameters.get("channels"), capabilities
        )
        if "acquire_mode" in parameters and parameters["acquire_mode"] not in {
            "normal",
            "current",
        }:
            raise WebUIRequestError("acquire_mode must be normal or current")
        if "channels_mode" in parameters and parameters["channels_mode"] not in {
            "all",
            "displayed",
        }:
            raise WebUIRequestError("channels_mode must be all or displayed")
    elif command in {"setup-save", "setup-recall"}:
        target = parameters.get("target")
        if target == "slot":
            parameters["slot"] = _integer(parameters.get("slot"), "slot")
            if capabilities.setup_slots is not None and parameters["slot"] not in capabilities.setup_slots:
                raise WebUIRequestError("setup slot is unsupported for this model")
            parameters.pop("file", None)
        elif target == "file":
            if not capabilities.supports_setup_file_target:
                raise WebUIRequestError("setup file target is unsupported for this model")
            file_spec = parameters.get("file")
            if not isinstance(file_spec, str) or not file_spec.strip():
                raise WebUIRequestError(f"{command} file target requires a file path")
            parameters.pop("slot", None)
        else:
            raise WebUIRequestError(f"{command} target must be slot or file")
    else:
        return False
    return True
