"""WebUI request admission, parameter validation, and normalization."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

from scopes_tool_core import capabilities_for_model_id
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
from scopes_tool_core.display import validate_display_intensity, validate_display_persistence
from scopes_tool_core.dvm import normalize_dvm_mode
from scopes_tool_core.fft import normalize_fft_units, normalize_fft_window
from scopes_tool_core.identity import physical_model_for_id
from scopes_tool_core.math import (
    normalize_math_composite_operation,
    normalize_math_operation,
    normalize_math_source,
    validate_finite_number,
    validate_positive,
)
from scopes_tool_core.measurements import (
    normalize_measurement_item,
    normalize_measurement_window,
    validate_statistics_items,
)
from scopes_tool_core.planning import (
    parse_measurement_item_list,
    parse_pair_specs,
    resolve_sweep_channels,
)
from scopes_tool_core.reference import validate_reference_label, validate_reference_slot
from scopes_tool_core.save_export import (
    SAVE_IMAGE_FORMATS,
    SAVE_IMAGE_PALETTES,
    SAVE_WAVEFORM_FORMATS,
    validate_save_filename_base,
    validate_save_quoted_string,
    validate_save_waveform_length,
)
from scopes_tool_core.search import (
    validate_can_search_criteria,
    validate_can_search_mode,
    validate_i2c_pattern_value,
    validate_i2c_search_mode,
    validate_search_event,
    validate_search_mode,
    validate_search_qualifier,
    validate_serial_search_bus,
    validate_spi_search_mode,
    validate_spi_search_pattern_width,
    validate_uart_data,
    validate_uart_search_mode,
)
from scopes_tool_core.segmented_capture import (
    SegmentedCaptureRequest,
    validate_segmented_capture_request,
)
from scopes_tool_core.serial import (
    normalize_can_signal_definition,
    normalize_i2c_address_size,
    normalize_serial_bit_order,
    normalize_serial_mode,
    normalize_serial_source,
    normalize_spi_clock_slope,
    normalize_spi_framing,
    normalize_uart_parity,
    normalize_uart_polarity,
    validate_can_baud_rate,
    validate_can_sample_point,
    validate_serial_bus,
    validate_serial_can_trigger_request,
    validate_serial_i2c_trigger_request,
    validate_serial_mode,
    validate_serial_spi_trigger_request,
    validate_serial_uart_trigger_request,
    validate_serial_lister_display,
    validate_serial_lister_reference,
    validate_spi_framing_clock_timeout,
    validate_uart_baud_rate,
)
from scopes_tool_core.timebase import (
    validate_timebase_position,
    validate_timebase_scale,
)
from scopes_tool_core.trigger import (
    normalize_delay_slope,
    normalize_edge_burst_slope,
    normalize_edge_slope,
    normalize_glitch_polarity,
    normalize_glitch_qualifier,
    normalize_runt_polarity,
    normalize_runt_qualifier,
    normalize_setup_hold_slope,
    normalize_transition_qualifier,
    normalize_transition_slope,
    normalize_trigger_edge_coupling,
    normalize_trigger_edge_reject,
    normalize_trigger_sweep,
    normalize_tv_mode,
    normalize_tv_polarity,
    normalize_tv_standard,
    validate_delay_trigger_count,
    validate_delay_trigger_time,
    validate_edge_burst_count,
    validate_edge_burst_idle_time,
    validate_edge_burst_source_channel,
    validate_external_trigger_probe_attenuation,
    validate_external_trigger_range,
    validate_external_trigger_units,
    validate_or_trigger_pattern,
    validate_pattern_trigger_pattern,
    validate_setup_hold_trigger_channel,
    validate_setup_hold_trigger_time,
    validate_trigger_level,
    validate_trigger_time,
    validate_tv_line,
    validate_tv_source_channel,
)

from .command_catalog import (
    _COMMAND_BY_ID,
    _COMMAND_FIELDS,
    _P3C_COMMAND_IDS,
)

DEFAULT_MODEL_ID = "keysight-dsox4024a"
DEFAULT_PC_OUTPUT_DIR = "data"


class WebUIRequestError(ValueError):
    """Raised when a WebUI command request is invalid before queueing."""


def validate_job_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise WebUIRequestError("request body must be an object")
    command = payload.get("command")
    if not isinstance(command, str) or command not in _COMMAND_BY_ID:
        raise WebUIRequestError("command is not supported by the Scopes Tool WebUI")
    mode = payload.get("mode", "live")
    if mode not in {"live", "simulate", "dry-run"}:
        raise WebUIRequestError("mode must be live, simulate, or dry-run")
    if mode not in _COMMAND_BY_ID[command]["modes"]:
        raise WebUIRequestError(f"command {command!r} is not available in {mode} mode")
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise WebUIRequestError("parameters must be an object")
    unknown = sorted(set(parameters) - _COMMAND_FIELDS[command])
    if unknown:
        raise WebUIRequestError(f"unknown parameter for {command}: {unknown[0]}")

    resource = payload.get("resource")
    if resource is not None and (not isinstance(resource, str) or not resource.strip()):
        raise WebUIRequestError("resource must be a non-empty string when provided")
    pc_output_dir = payload.get("pc_output_dir", DEFAULT_PC_OUTPUT_DIR)
    if not isinstance(pc_output_dir, str) or not pc_output_dir.strip():
        raise WebUIRequestError("pc_output_dir must be a non-empty string")
    model_id = None if mode == "live" else payload.get("model_id", DEFAULT_MODEL_ID)
    if mode != "live":
        if not isinstance(model_id, str) or not model_id.strip():
            raise WebUIRequestError("model_id must be a non-empty registered model ID")
        try:
            physical_model_for_id(model_id)
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
    if mode == "live" and command != "list-resources" and resource is None:
        raise WebUIRequestError("live execution requires an explicit VISA resource")

    normalized = dict(parameters)
    _validate_exclusive_minimum_fields(command, normalized)
    if mode == "live" and command != "list-resources":
        _validate_parameter_shapes(command, normalized, mode)
    else:
        _validate_parameters(command, normalized, mode, model_id)
    return {
        "command": command,
        "mode": mode,
        "resource": resource.strip() if isinstance(resource, str) else None,
        "model_id": model_id,
        "pc_output_dir": pc_output_dir.strip(),
        "parameters": normalized,
    }


def _csv_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    raise WebUIRequestError("workflow list fields must be comma-separated strings")


def _validated_direct_measurement_items(value: Any) -> str:
    value = ",".join(_csv_values(value))
    items = parse_measurement_item_list(value, allow_pair=False)
    return ",".join(validate_statistics_items(items))


def _workflow_channels(value: Any, capabilities: Any, *, required: bool) -> list[int] | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise WebUIRequestError("channels are required")
        return None
    try:
        raw = [int(item) if item.isdigit() else item for item in _csv_values(value)]
        return list(resolve_sweep_channels(raw, capabilities))
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc


def _workflow_pairs(value: Any, capabilities: Any) -> list[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return []
    values = _csv_values(value)
    try:
        parse_pair_specs(values, capabilities)
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc
    return values


def _segmented_capture_request(parameters: Mapping[str, Any], artifact_dir: Path) -> SegmentedCaptureRequest:
    return SegmentedCaptureRequest(
        channel=parameters["channel"], segments=parameters["segments"], points=parameters["points"],
        waveform_format=parameters["format"], timeout_ms=parameters["timeout_ms"],
        poll_interval_ms=parameters["poll_interval_ms"], output_dir=artifact_dir,
    )


def _validate_action_fields(parameters: dict[str, Any], command: str, names: tuple[str, ...]) -> str:
    action = _action(parameters, command)
    if action == "query":
        _reject_query_parameters(parameters, names, command)
    return action


def _validate_p3c_parameters(command: str, parameters: dict[str, Any], mode: str, model_id: str) -> None:
    capabilities = capabilities_for_model_id(model_id)
    if command == "segmented-memory":
        action = parameters.setdefault("action", "query")
        if action not in {"query", "enable", "disable"}:
            raise WebUIRequestError("segmented-memory action must be query, enable, or disable")
        if action == "enable":
            parameters["segments"] = _integer(parameters.get("segments"), "segments")
        elif action == "query":
            _reject_query_parameters(parameters, ("segments",), command)
        else:
            _reject_query_parameters(parameters, ("segments",), command)
        return
    if command == "segmented-capture":
        parameters["channel"] = validate_analog_channel(_integer(parameters.get("channel", 1), "channel"), capabilities)
        parameters["segments"] = _integer(parameters.get("segments"), "segments")
        parameters["points"] = _integer(parameters.get("points", 1000), "points")
        parameters["timeout_ms"] = _integer(parameters.get("timeout_ms", 30000), "timeout_ms")
        parameters["poll_interval_ms"] = _integer(parameters.get("poll_interval_ms", 100), "poll_interval_ms")
        parameters["format"] = str(parameters.get("format", "byte")).lower()
        if parameters["format"] not in {"byte", "word"}:
            raise WebUIRequestError("format must be byte or word")
        if mode == "dry-run" and not capabilities.supports_segmented_memory:
            raise WebUIRequestError("segmented capture is not supported by this model")
        try:
            validate_segmented_capture_request(_segmented_capture_request(parameters, Path(".")), capabilities)
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        return
    if command in {"capture-batch", "measure-log", "measure-until", "triggered-measure-loop", "triggered-capture-series"}:
        if command == "capture-batch":
            parameters["channels"] = _workflow_channels(parameters.get("channels"), capabilities, required=True)
            parameters["points"] = _integer(parameters.get("points", 1000), "points")
            parameters["count"] = _integer(parameters.get("count", 1), "count")
            parameters["interval_seconds"] = _finite_number(parameters.get("interval_seconds", 0), "interval_seconds")
            if parameters["interval_seconds"] < 0:
                raise WebUIRequestError("interval_seconds must be non-negative")
            parameters["format"] = str(parameters.get("format", "byte")).lower()
            if parameters["format"] not in {"byte", "word"}:
                raise WebUIRequestError("format must be byte or word")
        elif command == "measure-log":
            parameters["channels"] = _workflow_channels(parameters.get("channels"), capabilities, required=False)
            parameters["items"] = parameters.get("items", "vpp,frequency")
            parameters["pairs"] = _workflow_pairs(parameters.get("pairs"), capabilities)
            parameters["pair_items"] = str(parameters.get("pair_items", "phase,delay"))
            try:
                parameters["items"] = _validated_direct_measurement_items(parameters["items"])
                parse_measurement_item_list(parameters["pair_items"], allow_pair=True)
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
            if "count" not in parameters and "duration_seconds" not in parameters:
                raise WebUIRequestError("measure-log requires count or duration_seconds")
            if "count" in parameters:
                parameters["count"] = _integer(parameters["count"], "count")
            if "duration_seconds" in parameters:
                parameters["duration_seconds"] = _finite_number(parameters["duration_seconds"], "duration_seconds")
            parameters["interval_seconds"] = _finite_number(parameters.get("interval_seconds", 1), "interval_seconds")
            if "stop_on_error" in parameters:
                _require_boolean(parameters["stop_on_error"], "stop_on_error")
            else:
                parameters["stop_on_error"] = False
        elif command == "measure-until":
            parameters["channel"] = validate_analog_channel(_integer(parameters.get("channel", 1), "channel"), capabilities)
            try:
                parameters["item"] = validate_statistics_items(
                    (normalize_measurement_item(parameters.get("item", "vpp")),)
                )[0]
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
            if parameters.get("operator") not in {"gt", "gte", "lt", "lte"}:
                raise WebUIRequestError("operator must be gt, gte, lt, or lte")
            parameters["threshold"] = _finite_number(parameters.get("threshold"), "threshold")
            parameters["timeout_seconds"] = _finite_number(parameters.get("timeout_seconds"), "timeout_seconds")
            parameters["interval_seconds"] = _finite_number(parameters.get("interval_seconds", 1), "interval_seconds")
        elif command == "triggered-measure-loop":
            parameters["channels"] = _workflow_channels(parameters.get("channels"), capabilities, required=False)
            parameters["items"] = parameters.get("items", "vpp,frequency")
            parameters["pairs"] = _workflow_pairs(parameters.get("pairs"), capabilities)
            parameters["pair_items"] = str(parameters.get("pair_items", "phase,delay"))
            parameters["count"] = _integer(parameters.get("count"), "count")
            parameters["trigger_timeout_seconds"] = _finite_number(parameters.get("trigger_timeout_seconds"), "trigger_timeout_seconds")
            parameters["interval_seconds"] = _finite_number(parameters.get("interval_seconds", 0), "interval_seconds")
            try:
                parameters["items"] = _validated_direct_measurement_items(parameters["items"])
                parse_measurement_item_list(parameters["pair_items"], allow_pair=True)
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            parameters["channels"] = _workflow_channels(parameters.get("channels"), capabilities, required=True)
            parameters["count"] = _integer(parameters.get("count"), "count")
            parameters["trigger_timeout_seconds"] = _finite_number(parameters.get("trigger_timeout_seconds"), "trigger_timeout_seconds")
            parameters["points"] = _integer(parameters.get("points", 1000), "points")
            parameters["interval_seconds"] = _finite_number(parameters.get("interval_seconds", 0), "interval_seconds")
            parameters["format"] = str(parameters.get("format", "byte")).lower()
            if parameters["format"] not in {"byte", "word"}:
                raise WebUIRequestError("format must be byte or word")
        if mode == "dry-run" and command in {"capture-batch", "measure-log"}:
            raise WebUIRequestError(f"dry-run is not supported for {command}")
        return
    if command.startswith("serial-search-"):
        protocol = command.removeprefix("serial-search-")
        action = _validate_action_fields(parameters, command, tuple(key for key in parameters if key not in {"action", "bus"}))
        parameters["bus"] = validate_serial_search_bus(_integer(parameters.get("bus", 1), "bus"), capabilities)
        if action == "set":
            if protocol == "uart":
                parameters["mode"] = validate_uart_search_mode(parameters["mode"])
                if "data" in parameters: parameters["data"] = validate_uart_data(parameters["data"])
                if "qualifier" in parameters: parameters["qualifier"] = validate_search_qualifier(parameters["qualifier"])
            elif protocol == "i2c":
                parameters["mode"] = validate_i2c_search_mode(parameters["mode"])
                for name in ("address", "data", "data2"):
                    if name in parameters: parameters[name] = validate_i2c_pattern_value(_integer(parameters[name], name), name)
                if "qualifier" in parameters: parameters["qualifier"] = validate_search_qualifier(parameters["qualifier"])
            elif protocol == "spi":
                parameters["mode"] = validate_spi_search_mode(parameters["mode"])
                if "width" in parameters: parameters["width"] = _integer(parameters["width"], "width")
                validate_spi_search_pattern_width(parameters.get("data"), parameters.get("width"))
            else:
                parameters["mode"] = validate_can_search_mode(parameters["mode"])
                validate_can_search_criteria(parameters["mode"], data=parameters.get("data"), data_length=parameters.get("data_length"), id_val=parameters.get("id"), id_mode=parameters.get("id_mode"))
        return
    if command in {"search-state", "search-mode", "search-event"}:
        names = {"search-state": ("enabled",), "search-mode": ("mode",), "search-event": ("event",)}[command]
        action = _validate_action_fields(parameters, command, names)
        if action == "set":
            if command == "search-state": _require_boolean(parameters["enabled"], "enabled")
            elif command == "search-mode": parameters["mode"] = validate_search_mode(parameters["mode"], capabilities)
            else: parameters["event"] = validate_search_event(_integer(parameters["event"], "event"))
        return
    if command == "search-count":
        return
    if command.startswith("trigger-") or command.startswith("external-trigger-"):
        _validate_p3c_trigger(command, parameters, capabilities)
        return
    if command.startswith("serial-"):
        _validate_p3c_serial(command, parameters, capabilities)
        return


def _validate_p3c_trigger(command: str, parameters: dict[str, Any], capabilities: Any) -> None:
    if command == "external-trigger-settings":
        return
    action = _action(parameters, command)
    names_by_command = {
        "trigger-edge": ("source_channel", "level", "slope"),
        "trigger-edge-source": ("source", "source_channel"),
        "trigger-edge-slope": ("slope",),
        "trigger-edge-level": ("level",),
        "external-trigger-range": ("range_volts",),
        "trigger-edge-external-level": ("level",),
        "external-trigger-probe": ("attenuation",),
        "external-trigger-units": ("units",),
        "trigger-edge-coupling": ("coupling",),
        "trigger-edge-reject": ("reject",),
        "trigger-pulse-width": ("channel", "polarity", "qualifier", "time_seconds", "min_time_seconds", "max_time_seconds", "level"),
        "trigger-runt": ("channel", "polarity", "qualifier", "low_level", "high_level", "time_seconds"),
        "trigger-transition": ("channel", "slope", "qualifier", "low_level", "high_level", "time_seconds"),
        "trigger-delay": ("arm_channel", "arm_slope", "trigger_channel", "trigger_slope", "time_seconds", "count"),
        "trigger-setup-hold": ("clock_channel", "data_channel", "slope", "setup_time_seconds", "hold_time_seconds"),
        "trigger-edge-burst": ("source_channel", "slope", "count", "idle_time", "level"),
        "trigger-tv": ("source_channel", "standard", "mode", "polarity", "line"),
        "trigger-pattern": ("pattern",),
        "trigger-or": ("pattern",),
        "trigger-sweep": ("mode",),
        "trigger-noise-reject": ("enabled",),
        "trigger-hf-reject": ("enabled",),
        "trigger-holdoff": ("seconds",),
    }
    names = names_by_command[command]
    if command == "trigger-edge-level":
        parameters["source_channel"] = validate_analog_channel(_integer(parameters.get("source_channel", 1), "source_channel"), capabilities)
    if action == "query":
        _reject_query_parameters(parameters, names, command)
        return
    optional_names = {
        "trigger-pulse-width": {"time_seconds", "min_time_seconds", "max_time_seconds", "level"},
        "trigger-runt": {"time_seconds"},
        "trigger-edge-burst": {"level"},
        "trigger-tv": {"line"},
    }.get(command, set())
    for name in names:
        if name in optional_names:
            continue
        if command == "trigger-edge-source" and name == "source_channel":
            continue
        _require_parameter(parameters, name, command)
    if command == "trigger-edge":
        parameters["source_channel"] = validate_analog_channel(_integer(parameters["source_channel"], "source_channel"), capabilities)
        parameters["level"] = validate_trigger_level(_finite_number(parameters["level"], "level"))
        parameters["slope"] = normalize_edge_slope(parameters["slope"])
    elif command == "trigger-edge-source":
        if parameters["source"] == "analog-channel":
            _require_parameter(parameters, "source_channel", command)
            parameters["source_channel"] = validate_analog_channel(_integer(parameters["source_channel"], "source_channel"), capabilities)
    elif command == "trigger-edge-slope":
        parameters["slope"] = normalize_edge_slope(parameters["slope"])
    elif command == "trigger-edge-level":
        parameters["level"] = validate_trigger_level(_finite_number(parameters["level"], "level"))
    elif command == "external-trigger-range":
        parameters["range_volts"] = validate_external_trigger_range(_finite_number(parameters["range_volts"], "range_volts"))
    elif command == "trigger-edge-external-level":
        parameters["level"] = validate_trigger_level(_finite_number(parameters["level"], "level"))
    elif command == "external-trigger-probe":
        parameters["attenuation"] = validate_external_trigger_probe_attenuation(_finite_number(parameters["attenuation"], "attenuation"))
    elif command == "external-trigger-units":
        parameters["units"] = validate_external_trigger_units(parameters["units"])
    elif command == "trigger-edge-coupling":
        parameters["coupling"] = normalize_trigger_edge_coupling(parameters["coupling"])
    elif command == "trigger-edge-reject":
        parameters["reject"] = normalize_trigger_edge_reject(parameters["reject"])
    elif command == "trigger-pulse-width":
        parameters["channel"] = validate_analog_channel(_integer(parameters["channel"], "channel"), capabilities)
        parameters["polarity"] = normalize_glitch_polarity(parameters["polarity"])
        qualifier = parameters["qualifier"]
        parameters["qualifier"] = normalize_glitch_qualifier(qualifier)
        if qualifier == "range":
            _require_parameter(parameters, "min_time_seconds", command)
            _require_parameter(parameters, "max_time_seconds", command)
            parameters["min_time_seconds"] = validate_trigger_time(_finite_number(parameters["min_time_seconds"], "min_time_seconds"))
            parameters["max_time_seconds"] = validate_trigger_time(_finite_number(parameters["max_time_seconds"], "max_time_seconds"))
        else:
            _require_parameter(parameters, "time_seconds", command)
            parameters["time_seconds"] = validate_trigger_time(_finite_number(parameters["time_seconds"], "time_seconds"))
        if "level" in parameters: parameters["level"] = validate_trigger_level(_finite_number(parameters["level"], "level"))
    elif command == "trigger-runt":
        parameters["channel"] = validate_analog_channel(_integer(parameters["channel"], "channel"), capabilities)
        parameters["polarity"] = normalize_runt_polarity(parameters["polarity"])
        qualifier = parameters["qualifier"]
        parameters["qualifier"] = normalize_runt_qualifier(qualifier)
        parameters["low_level"] = validate_trigger_level(_finite_number(parameters["low_level"], "low_level"))
        parameters["high_level"] = validate_trigger_level(_finite_number(parameters["high_level"], "high_level"))
        if qualifier != "none":
            _require_parameter(parameters, "time_seconds", command)
            parameters["time_seconds"] = validate_trigger_time(_finite_number(parameters["time_seconds"], "time_seconds"))
    elif command == "trigger-transition":
        parameters["channel"] = validate_analog_channel(_integer(parameters["channel"], "channel"), capabilities)
        parameters["slope"] = normalize_transition_slope(parameters["slope"])
        parameters["qualifier"] = normalize_transition_qualifier(parameters["qualifier"])
        for name in ("low_level", "high_level"):
            parameters[name] = validate_trigger_level(_finite_number(parameters[name], name))
        parameters["time_seconds"] = validate_trigger_time(_finite_number(parameters["time_seconds"], "time_seconds"))
    elif command == "trigger-delay":
        for name in ("arm_channel", "trigger_channel"):
            parameters[name] = validate_analog_channel(_integer(parameters[name], name), capabilities)
        parameters["arm_slope"] = normalize_delay_slope(parameters["arm_slope"])
        parameters["trigger_slope"] = normalize_delay_slope(parameters["trigger_slope"])
        parameters["time_seconds"] = validate_delay_trigger_time(_finite_number(parameters["time_seconds"], "time_seconds"))
        parameters["count"] = validate_delay_trigger_count(_integer(parameters["count"], "count"))
    elif command == "trigger-setup-hold":
        parameters["clock_channel"] = validate_setup_hold_trigger_channel(_integer(parameters["clock_channel"], "clock_channel"), capabilities, "clock_channel")
        parameters["data_channel"] = validate_setup_hold_trigger_channel(_integer(parameters["data_channel"], "data_channel"), capabilities, "data_channel")
        parameters["slope"] = normalize_setup_hold_slope(parameters["slope"])
        parameters["setup_time_seconds"] = validate_setup_hold_trigger_time(_finite_number(parameters["setup_time_seconds"], "setup_time_seconds"), "setup_time_seconds")
        parameters["hold_time_seconds"] = validate_setup_hold_trigger_time(_finite_number(parameters["hold_time_seconds"], "hold_time_seconds"), "hold_time_seconds")
    elif command == "trigger-edge-burst":
        parameters["source_channel"] = validate_edge_burst_source_channel(_integer(parameters["source_channel"], "source_channel"), capabilities)
        parameters["slope"] = normalize_edge_burst_slope(parameters["slope"])
        parameters["count"] = validate_edge_burst_count(_integer(parameters["count"], "count"))
        parameters["idle_time"] = validate_edge_burst_idle_time(_finite_number(parameters["idle_time"], "idle_time"))
        if "level" in parameters: parameters["level"] = validate_trigger_level(_finite_number(parameters["level"], "level"))
    elif command == "trigger-tv":
        parameters["source_channel"] = validate_tv_source_channel(_integer(parameters["source_channel"], "source_channel"), capabilities)
        parameters["standard"] = normalize_tv_standard(parameters["standard"])
        parameters["mode"] = normalize_tv_mode(parameters["mode"])
        parameters["polarity"] = normalize_tv_polarity(parameters["polarity"])
        parameters["line"] = validate_tv_line(parameters["standard"], parameters["mode"], parameters.get("line"))
    elif command == "trigger-pattern":
        parameters["pattern"] = validate_pattern_trigger_pattern(parameters["pattern"], capabilities)
    elif command == "trigger-or":
        parameters["pattern"] = validate_or_trigger_pattern(parameters["pattern"], capabilities)
    elif command == "trigger-sweep":
        parameters["mode"] = normalize_trigger_sweep(parameters["mode"])
    elif command in {"trigger-noise-reject", "trigger-hf-reject"}:
        _require_boolean(parameters["enabled"], "enabled")
    elif command == "trigger-holdoff":
        parameters["seconds"] = _finite_number(parameters["seconds"], "seconds")


def _validate_p3c_serial(command: str, parameters: dict[str, Any], capabilities: Any) -> None:
    if command == "serial-lister-export":
        _require_parameter(parameters, "filename", command)
        try:
            filename = validate_save_filename_base(parameters["filename"])
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        if filename in {".", ".."}:
            raise WebUIRequestError("serial-lister-export filename must not be . or ..")
        parameters["filename"] = filename
        return
    if command == "serial-lister-query":
        return
    if command in {"serial-lister-display", "serial-lister-reference"}:
        action = _action(parameters, command)
        name = "display" if command.endswith("display") else "reference"
        if action == "set":
            _require_parameter(parameters, name, command)
            try:
                parameters[name] = validate_serial_lister_display(parameters[name], capabilities) if name == "display" else validate_serial_lister_reference(parameters[name], capabilities)
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (name,), command)
        return
    parameters["bus"] = validate_serial_bus(_integer(parameters.get("bus", 1), "bus"), capabilities)
    if command == "serial-query":
        return
    if command == "serial-mode":
        action = _validate_action_fields(parameters, command, ("mode",))
        if action == "set": parameters["mode"] = validate_serial_mode(parameters["mode"], capabilities)
        return
    if command == "serial-display":
        action = _validate_action_fields(parameters, command, ("enabled",))
        if action == "set": _require_boolean(parameters["enabled"], "enabled")
        return
    if command.startswith("serial-trigger-"):
        protocol = command.removeprefix("serial-trigger-")
        names = ("type", "data", "qualifier", "address", "data2", "width", "id", "id_mode", "data_length")
        action = _validate_action_fields(parameters, command, names)
        if action != "set": return
        try:
            if protocol == "uart":
                validate_serial_uart_trigger_request(parameters["bus"], type=parameters.get("type"), data=parameters.get("data"), qualifier=parameters.get("qualifier"), capabilities=capabilities)
            elif protocol == "i2c":
                validate_serial_i2c_trigger_request(parameters["bus"], type=parameters.get("type"), address=parameters.get("address"), data=parameters.get("data"), data2=parameters.get("data2"), qualifier=parameters.get("qualifier"), capabilities=capabilities)
            elif protocol == "spi":
                validate_serial_spi_trigger_request(parameters["bus"], type=parameters.get("type"), width=parameters.get("width"), data=parameters.get("data"), capabilities=capabilities)
            else:
                validate_serial_can_trigger_request(parameters["bus"], type=parameters.get("type"), id=parameters.get("id"), id_mode=parameters.get("id_mode"), data=parameters.get("data"), data_length=parameters.get("data_length"), capabilities=capabilities)
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        return
    protocol = command.removeprefix("serial-")
    action = _validate_action_fields(parameters, command, tuple(key for key in parameters if key not in {"action", "bus"}))
    if action != "set": return
    values = {key: value for key, value in parameters.items() if key not in {"action", "bus"}}
    if not values:
        raise WebUIRequestError(f"{command} set requires at least one setting")
    try:
        if protocol == "uart":
            if "rx_source" in values: values["rx_source"] = normalize_serial_source(values["rx_source"], capabilities)
            if "tx_source" in values: values["tx_source"] = normalize_serial_source(values["tx_source"], capabilities)
            if "baud_rate" in values: values["baud_rate"] = validate_uart_baud_rate(values["baud_rate"], capabilities)
            if "parity" in values: values["parity"] = normalize_uart_parity(values["parity"])
            if "polarity" in values: values["polarity"] = normalize_uart_polarity(values["polarity"])
            if "bit_order" in values: values["bit_order"] = normalize_serial_bit_order(values["bit_order"])
        elif protocol == "i2c":
            for name in ("clock_source", "data_source"):
                if name in values: values[name] = normalize_serial_source(values[name], capabilities)
            if "address_size" in values: values["address_size"] = normalize_i2c_address_size(values["address_size"])
        elif protocol == "spi":
            for name in ("clock_source", "mosi_source", "miso_source", "frame_source"):
                if name in values: values[name] = normalize_serial_source(values[name], capabilities)
            if "clock_slope" in values: values["clock_slope"] = normalize_spi_clock_slope(values["clock_slope"])
            if "bit_order" in values: values["bit_order"] = normalize_serial_bit_order(values["bit_order"])
            if "framing" in values: values["framing"] = normalize_spi_framing(values["framing"])
            if "clock_timeout" in values: validate_spi_framing_clock_timeout(values.get("framing"), values.get("clock_timeout"))
        else:
            if "source" in values: values["source"] = normalize_serial_source(values["source"], capabilities)
            if "baud_rate" in values: values["baud_rate"] = validate_can_baud_rate(values["baud_rate"])
            if "sample_point" in values: values["sample_point"] = validate_can_sample_point(values["sample_point"], capabilities)
            if "signal_definition" in values: values["signal_definition"] = normalize_can_signal_definition(values["signal_definition"])
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc
    parameters.update(values)


def _validate_parameter_shapes(
    command: str,
    parameters: Mapping[str, Any],
    mode: str,
) -> None:
    fields = {field["name"]: field for field in _COMMAND_BY_ID[command]["fields"]}
    for name, field in fields.items():
        if name not in parameters:
            if field.get("required") is True:
                raise WebUIRequestError(f"{name} is required")
            continue
        value = parameters[name]
        field_type = field["type"]
        if field_type == "integer":
            parsed = _integer(value, name)
        elif field_type == "number":
            parsed = _finite_number(value, name)
        elif field_type == "boolean":
            _require_boolean(value, name)
            continue
        elif field_type == "string":
            if not isinstance(value, str):
                raise WebUIRequestError(f"{name} must be a string")
            continue
        elif field_type == "enum":
            options = field.get("mode_options", {}).get(mode, field.get("options", ()))
            if value not in options:
                raise WebUIRequestError(f"{name} must be one of: {', '.join(map(str, options))}")
            continue
        elif field_type == "multi-enum":
            if isinstance(value, str):
                continue
            if isinstance(value, (list, tuple)) and all(
                isinstance(item, (str, int, float)) and not isinstance(item, bool)
                for item in value
            ):
                continue
            raise WebUIRequestError(f"{name} must be a comma-separated string or list")
        else:
            continue
        if "minimum" in field and parsed < field["minimum"]:
            raise WebUIRequestError(f"{name} must be at least {field['minimum']}")
        if "maximum" in field and parsed > field["maximum"]:
            raise WebUIRequestError(f"{name} must be at most {field['maximum']}")


def _validate_exclusive_minimum_fields(
    command: str,
    parameters: Mapping[str, Any],
) -> None:
    fields = {field["name"]: field for field in _COMMAND_BY_ID[command]["fields"]}
    for name, value in parameters.items():
        exclusive_minimum = fields[name].get("exclusive_minimum")
        if exclusive_minimum is None:
            continue
        if _finite_number(value, name) <= exclusive_minimum:
            raise WebUIRequestError(
                f"{name} must be greater than {exclusive_minimum}"
            )


def _validate_parameters(
    command: str,
    parameters: dict[str, Any],
    mode: str,
    model_id: str | None,
) -> None:
    if command == "list-resources":
        parameters.setdefault("live_only", False)
        _require_boolean(parameters["live_only"], "live_only")
        return
    if model_id is None:
        raise WebUIRequestError("detected model identity is required for live validation")
    capabilities = capabilities_for_model_id(model_id)
    if command in _P3C_COMMAND_IDS:
        _validate_p3c_parameters(command, parameters, mode, model_id)
        return
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
        if "count" in parameters:
            try:
                parameters["count"] = validate_acquisition_count(
                    _integer(parameters["count"], "count")
                )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
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
                    validate_display_persistence(value)
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
    elif command in {"measure-show", "measure-source", "measure-window"}:
        action = _action(parameters, command)
        if command == "measure-show":
            if action == "set":
                pass
            else:
                _reject_query_parameters(parameters, (), command)
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
            else:
                _reject_query_parameters(parameters, ("window",), command)
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
                    if parameters[value_name] not in SAVE_IMAGE_FORMATS:
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
                    if parameters[value_name] not in SAVE_WAVEFORM_FORMATS:
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
        _require_parameter(parameters, "filename", command)
        try:
            parameters["filename"] = validate_save_quoted_string(
                parameters["filename"],
                label="Save image filename" if command == "save-image" else "Save waveform filename",
            )
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
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
            parameters["source_channel"] = validate_analog_channel(
                _integer(parameters["source_channel"], "source_channel"), capabilities
            )
            for name in ("center_hz", "span_hz"):
                if name in parameters:
                    parameters[name] = _finite_number(parameters[name], name)
            if "center_hz" in parameters and parameters["center_hz"] < 0:
                raise WebUIRequestError("center_hz must be non-negative")
            if "span_hz" in parameters and parameters["span_hz"] <= 0:
                raise WebUIRequestError("span_hz must be greater than zero")
            if "units" in parameters:
                try:
                    normalize_fft_units(parameters["units"])
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            if "window" in parameters:
                try:
                    normalize_fft_window(parameters["window"])
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            if "display" in parameters:
                _require_boolean(parameters["display"], "display")
        else:
            _reject_query_parameters(
                parameters,
                ("source_channel", "units", "window", "center_hz", "span_hz", "display"),
                command,
            )
    elif command in {"math-display", "math-vertical", "math-operator", "math-composite-source"}:
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
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, names, command)
        else:
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
    elif command == "math-clear":
        parameters["function"] = _integer(parameters.get("function", 1), "function")
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
    elif command == "capture":
        parameters["channel"] = validate_analog_channel(
            _integer(parameters.get("channel", 1), "channel"), capabilities
        )
        parameters["points"] = _integer(parameters.get("points", 1000), "points")
        if parameters["points"] not in {1000, 5000, 10000}:
            raise WebUIRequestError("points must be one of: 1000, 5000, 10000")
        parameters["format"] = str(parameters.get("format", "byte")).lower()
        if parameters["format"] not in {"byte", "word"}:
            raise WebUIRequestError("format must be byte or word")
        if parameters["format"] == "word" and not capabilities.supports_word_format:
            raise WebUIRequestError("word waveform format is not supported by this model")
    elif command == "screenshot":
        parameters["background"] = str(parameters.get("background", "black")).lower()
        if parameters["background"] not in {"black", "white"}:
            raise WebUIRequestError("background must be black or white")


def _normalize_acquisition_type(value: Any) -> str:
    normalized = normalize_acquisition_type(value)
    return {
        "NORMal": "normal",
        "AVERage": "average",
        "HRESolution": "high_resolution",
        "PEAK": "peak",
    }[normalized]


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WebUIRequestError(f"{name} must be an integer")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WebUIRequestError(f"{name} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise WebUIRequestError(f"{name} must be finite")
    return parsed


def _action(parameters: dict[str, Any], command: str) -> str:
    action = parameters.setdefault("action", "query")
    if action not in {"query", "set"}:
        raise WebUIRequestError(f"{command} action must be query or set")
    return action


def _require_parameter(parameters: Mapping[str, Any], name: str, command: str) -> None:
    if name not in parameters:
        raise WebUIRequestError(f"{command} set requires {name}")


def _reject_query_parameters(
    parameters: Mapping[str, Any], names: tuple[str, ...], command: str
) -> None:
    for name in names:
        if name in parameters:
            raise WebUIRequestError(f"{command} query cannot include {name}")


def _require_boolean(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise WebUIRequestError(f"{name} must be a boolean")
