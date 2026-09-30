"""WebUI parameter validation for Trigger, Search, Serial, segmented, and finite workflow commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from scopes_tool_core import capabilities_for_model_id
from scopes_tool_core.channel import validate_analog_channel
from scopes_tool_core.measurements import (
    measurement_query,
    normalize_measurement_item,
    pair_measurement_query,
    validate_statistics_items,
)
from scopes_tool_core.planning import (
    parse_measurement_item_list,
    parse_pair_specs,
    resolve_sweep_channels,
)
from scopes_tool_core.save_export import validate_save_filename_base
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
from scopes_tool_core.trigger import (
    runt_trigger_configure_commands,
    tv_trigger_configure_commands,
    normalize_delay_slope,
    normalize_edge_burst_slope,
    normalize_edge_slope,
    glitch_trigger_configure_commands,
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
    trigger_mode_command,
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

from ._validation_shared import (
    WebUIRequestError,
    _action,
    _csv_values,
    _finite_number,
    _integer,
    _reject_query_parameters,
    _require_boolean,
    _require_parameter,
    _validate_action_fields,
)


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


def _validate_measure_sweep_parameters(
    parameters: dict[str, Any], capabilities: Any
) -> None:
    parameters["channels"] = _workflow_channels(
        parameters.get("channels"), capabilities, required=False
    )
    parameters["items"] = _validated_direct_measurement_items(
        parameters.get("items", "vpp,frequency,period,vrms")
    )
    parameters["pairs"] = _workflow_pairs(parameters.get("pairs"), capabilities)
    try:
        pair_items = parse_measurement_item_list(
            ",".join(_csv_values(parameters.get("pair_items", "phase,delay"))),
            allow_pair=True,
        )
        for item in parameters["items"].split(","):
            measurement_query(item, 1, capabilities=capabilities)
        if parameters["pairs"] or capabilities.measurement_items is None:
            for item in pair_items:
                pair_measurement_query(item, 1, 2, capabilities=capabilities)
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc
    parameters["pair_items"] = ",".join(pair_items)


def _segmented_capture_request(parameters: Mapping[str, Any], artifact_dir: Path) -> SegmentedCaptureRequest:
    return SegmentedCaptureRequest(
        channel=parameters["channel"], segments=parameters["segments"], points=parameters["points"],
        waveform_format=parameters["format"], timeout_ms=parameters["timeout_ms"],
        poll_interval_ms=parameters["poll_interval_ms"], output_dir=artifact_dir,
    )


def _validate_trigger_search_serial_segmented_workflow_parameters(command: str, parameters: dict[str, Any], mode: str, model_id: str) -> None:
    capabilities = capabilities_for_model_id(model_id)
    if command == "segmented-memory":
        action = parameters.setdefault("action", "query")
        if action not in {"query", "enable", "disable", "select"}:
            raise WebUIRequestError(
                "segmented-memory action must be query, enable, disable, or select"
            )
        if action == "enable":
            parameters["segments"] = _integer(parameters.get("segments"), "segments")
            _reject_query_parameters(parameters, ("index",), command)
        elif action == "select":
            parameters["index"] = _integer(parameters.get("index"), "index")
            _reject_query_parameters(parameters, ("segments",), command)
        else:
            _reject_query_parameters(parameters, ("segments", "index"), command)
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
    if command in {"capture-batch", "capture-until", "capture-monitor", "measure-log", "measure-until", "triggered-measure-loop", "triggered-capture-series"}:
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
        elif command == "capture-until":
            parameters["channels"] = _workflow_channels(
                parameters.get("channels"), capabilities, required=True
            )
            parameters["condition_channel"] = validate_analog_channel(
                _integer(parameters.get("condition_channel"), "condition_channel"),
                capabilities,
            )
            if parameters["condition_channel"] not in parameters["channels"]:
                raise WebUIRequestError(
                    "condition_channel must be included in selected channels"
                )
            parameters["points"] = _integer(parameters.get("points", 1000), "points")
            if parameters["points"] not in {1000, 5000, 10000}:
                raise WebUIRequestError("points must be one of: 1000, 5000, 10000")
            parameters["format"] = str(parameters.get("format", "byte")).lower()
            if parameters["format"] not in {"byte", "word"}:
                raise WebUIRequestError("format must be byte or word")
            if parameters.get("metric") not in {
                "max", "min", "peak-to-peak", "abs-max"
            }:
                raise WebUIRequestError("metric is not supported")
            if parameters.get("operator") not in {"gt", "gte", "lt", "lte"}:
                raise WebUIRequestError("operator must be gt, gte, lt, or lte")
            parameters["threshold"] = _finite_number(
                parameters.get("threshold"), "threshold"
            )
            parameters["count"] = _integer(parameters.get("count", 1), "count")
            if not 1 <= parameters["count"] <= 255:
                raise WebUIRequestError("count must be between 1 and 255")
            parameters["timeout_seconds"] = _finite_number(
                parameters.get("timeout_seconds"), "timeout_seconds"
            )
            if parameters["timeout_seconds"] <= 0:
                raise WebUIRequestError("timeout_seconds must be greater than zero")
            parameters["interval_seconds"] = _finite_number(
                parameters.get("interval_seconds", 0), "interval_seconds"
            )
            if parameters["interval_seconds"] < 0:
                raise WebUIRequestError("interval_seconds must be non-negative")
        elif command == "capture-monitor":
            parameters["channels"] = _workflow_channels(
                parameters.get("channels"), capabilities, required=True
            )
            parameters["points"] = _integer(parameters.get("points", 1000), "points")
            if parameters["points"] not in {1000, 5000, 10000}:
                raise WebUIRequestError("points must be one of: 1000, 5000, 10000")
            parameters["format"] = str(parameters.get("format", "byte")).lower()
            if parameters["format"] not in {"byte", "word"}:
                raise WebUIRequestError("format must be byte or word")
            parameters["count"] = _integer(parameters.get("count"), "count")
            if parameters["count"] < 1:
                raise WebUIRequestError("count must be at least 1")
            parameters["interval_seconds"] = _finite_number(
                parameters.get("interval_seconds", 0), "interval_seconds"
            )
            if parameters["interval_seconds"] < 0:
                raise WebUIRequestError("interval_seconds must be non-negative")
            parameters["retention_points"] = _integer(
                parameters.get("retention_points", 250000), "retention_points"
            )
            if parameters["retention_points"] < parameters["points"]:
                raise WebUIRequestError(
                    "retention_points must be at least points per capture"
                )
            if parameters["retention_points"] % parameters["points"] != 0:
                raise WebUIRequestError(
                    "retention_points must be a multiple of points per capture"
                )
            _require_boolean(parameters.setdefault("save_results", True), "save_results")
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
            _require_boolean(parameters.setdefault("save_results", True), "save_results")
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
            _require_boolean(parameters.setdefault("save_results", True), "save_results")
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
            _require_boolean(parameters.setdefault("save_results", True), "save_results")
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
        _validate_trigger_parameters(command, parameters, capabilities)
        return
    if command.startswith("serial-"):
        _validate_serial_parameters(command, parameters, capabilities)
        return


def _validate_trigger_parameters(command: str, parameters: dict[str, Any], capabilities: Any) -> None:
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
        "trigger-mode": ("mode",),
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
        if capabilities.trigger_edge_slopes is not None and parameters["slope"] not in capabilities.trigger_edge_slopes:
            raise WebUIRequestError("trigger edge slope is unsupported for this model")
    elif command == "trigger-edge-source":
        if capabilities.trigger_edge_sources is not None and parameters["source"] not in capabilities.trigger_edge_sources:
            raise WebUIRequestError("trigger edge source is unsupported for this model")
        if parameters["source"] == "analog-channel":
            _require_parameter(parameters, "source_channel", command)
            parameters["source_channel"] = validate_analog_channel(_integer(parameters["source_channel"], "source_channel"), capabilities)
    elif command == "trigger-edge-slope":
        parameters["slope"] = normalize_edge_slope(parameters["slope"])
        if capabilities.trigger_edge_slopes is not None and parameters["slope"] not in capabilities.trigger_edge_slopes:
            raise WebUIRequestError("trigger edge slope is unsupported for this model")
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
        if capabilities.trigger_edge_couplings is not None and parameters["coupling"] not in capabilities.trigger_edge_couplings:
            raise WebUIRequestError("trigger edge coupling is unsupported for this model")
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
        glitch_trigger_configure_commands(channel=parameters["channel"], polarity=parameters["polarity"],
            qualifier=parameters["qualifier"], time_seconds=parameters.get("time_seconds"),
            min_time_seconds=parameters.get("min_time_seconds"), max_time_seconds=parameters.get("max_time_seconds"),
            level_volts=parameters.get("level"), capabilities=capabilities)
    elif command == "trigger-runt":
        runt_trigger_configure_commands(channel=_integer(parameters["channel"], "channel"),
            polarity=parameters["polarity"], qualifier=parameters["qualifier"],
            low_level_volts=_finite_number(parameters["low_level"], "low_level"),
            high_level_volts=_finite_number(parameters["high_level"], "high_level"),
            time_seconds=parameters.get("time_seconds"), capabilities=capabilities)
        parameters["channel"] = validate_analog_channel(_integer(parameters["channel"], "channel"), capabilities)
        normalize_runt_polarity(parameters["polarity"])
        qualifier = parameters["qualifier"]
        normalize_runt_qualifier(qualifier)
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
        tv_trigger_configure_commands(source_channel=_integer(parameters["source_channel"], "source_channel"),
            standard=parameters["standard"], mode=parameters["mode"], polarity=parameters["polarity"],
            line=parameters.get("line"), capabilities=capabilities)
        parameters["source_channel"] = validate_tv_source_channel(_integer(parameters["source_channel"], "source_channel"), capabilities)
        normalize_tv_standard(parameters["standard"])
        normalize_tv_mode(parameters["mode"])
        normalize_tv_polarity(parameters["polarity"])
        parameters["line"] = validate_tv_line(parameters["standard"], parameters["mode"], parameters.get("line"))
    elif command == "trigger-mode":
        if capabilities.trigger_modes is not None and parameters["mode"] not in capabilities.trigger_modes:
            raise WebUIRequestError("trigger mode is unsupported for this model")
        trigger_mode_command(parameters["mode"])
    elif command == "trigger-pattern":
        parameters["pattern"] = validate_pattern_trigger_pattern(parameters["pattern"], capabilities)
    elif command == "trigger-or":
        parameters["pattern"] = validate_or_trigger_pattern(parameters["pattern"], capabilities)
    elif command == "trigger-sweep":
        parameters["mode"] = normalize_trigger_sweep(parameters["mode"])
        if capabilities.trigger_sweep_modes is not None and parameters["mode"] not in capabilities.trigger_sweep_modes:
            raise WebUIRequestError("trigger sweep is unsupported for this model")
    elif command in {"trigger-noise-reject", "trigger-hf-reject"}:
        _require_boolean(parameters["enabled"], "enabled")
    elif command == "trigger-holdoff":
        parameters["seconds"] = _finite_number(parameters["seconds"], "seconds")
        minimum = capabilities.trigger_holdoff_min_seconds
        maximum = capabilities.trigger_holdoff_max_seconds
        if minimum is not None and parameters["seconds"] < minimum:
            raise WebUIRequestError(f"trigger holdoff must be at least {minimum} seconds for this model")
        if maximum is not None and parameters["seconds"] > maximum:
            raise WebUIRequestError(f"trigger holdoff must be at most {maximum} seconds for this model")


def _validate_serial_parameters(command: str, parameters: dict[str, Any], capabilities: Any) -> None:
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
