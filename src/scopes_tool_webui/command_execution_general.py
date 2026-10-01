"""WebUI execution for general scope commands and their helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from scopes_tool_core import CaptureRequest, run_capture, run_measure, run_measure_sweep
from scopes_tool_core.screenshot import ScreenshotOptions, write_screenshot
from scopes_tool_core.output_files import write_screenshot_png_file

from .command_execution_support import (
    _capture_output_paths,
    _jsonable,
    _measure_request,
    _measure_sweep_request,
    _next_output_file,
    _operation_payload,
    _simple_scope_result,
    _state_scope_result,
)

from .command_validation import WebUIRequestError


def _execute_acquisition(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    action = parameters["action"]
    if action == "set":
        if "count" in parameters:
            scope.validate_acquisition_count(parameters["count"])
        if "type" in parameters:
            scope.set_acquisition_type(parameters["type"])
        if "count" in parameters:
            scope.set_acquisition_count(parameters["count"])
    config = scope.query_acquisition_config()
    return {
        "exit_code": 0,
        "result": {"action": action, "acquisition": _jsonable(config)},
        "artifacts": [],
    }


def _execute_channel_display(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    channel = parameters["channel"]
    if parameters["action"] == "set":
        scope.set_channel_display(channel, parameters["enabled"])
    enabled = scope.query_channel_display(channel)
    return {
        "exit_code": 0,
        "result": {"channel": channel, "enabled": enabled},
        "artifacts": [],
    }


def _execute_channel_scale(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    channel = parameters["channel"]
    if parameters["action"] == "set":
        scope.set_channel_scale(channel, parameters["volts_per_division"])
    scale = scope.query_channel_scale(channel)
    return {
        "exit_code": 0,
        "result": {"channel": channel, "volts_per_division": scale},
        "artifacts": [],
    }


def _execute_channel_setting(
    scope: Any,
    parameters: Mapping[str, Any],
    *,
    setter: Any,
    getter: Any,
    value_name: str,
    result_name: str,
) -> dict[str, Any]:
    channel = parameters["channel"]
    if parameters["action"] == "set":
        setter(channel, parameters[value_name])
    return {
        "exit_code": 0,
        "result": {
            "channel": channel,
            result_name: _jsonable(getter(channel)),
        },
        "artifacts": [],
    }


def _execute_display_setting(
    parameters: Mapping[str, Any],
    setter: Any,
    getter: Any,
    value_name: str,
) -> dict[str, Any]:
    if parameters["action"] == "set":
        setter(parameters[value_name])
    return _state_scope_result("state", getter())


def _execute_state_setting(
    parameters: Mapping[str, Any],
    setter: Any,
    getter: Any,
    value_name: str = "enabled",
) -> dict[str, Any]:
    if parameters["action"] == "set":
        setter(parameters[value_name])
    return _state_scope_result("state", getter())


def _execute_fft(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_fft(
            function,
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
        )
    else:
        mismatch = _math_family_mismatch_result(
            scope, function, expected_family="fft", result_name="fft"
        )
        if mismatch is not None:
            return mismatch
    return _state_scope_result("fft", scope.query_fft(function))


def _execute_math_display(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_display(function, parameters["enabled"])
    return _state_scope_result("math_display", scope.query_math_display(function))


def _execute_math_vertical(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_vertical(
            function,
            scale=parameters.get("scale"),
            range_value=parameters.get("range_value"),
            offset=parameters.get("offset"),
        )
    return _state_scope_result("math_vertical", scope.query_math_vertical(function))


def _execute_math_operator(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_operator(
            function,
            parameters["operation"],
            parameters["source1"],
            parameters["source2"],
        )
    else:
        mismatch = _math_family_mismatch_result(
            scope, function, expected_family="operator", result_name="math_operator"
        )
        if mismatch is not None:
            return mismatch
    return _state_scope_result("math_operator", scope.query_math_operator(function))


def _execute_math_transform(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_transform(
            function,
            parameters["operation"],
            parameters["source"],
            input_offset=parameters.get("input_offset"),
            gain=parameters.get("gain"),
            linear_offset=parameters.get("linear_offset"),
        )
    else:
        mismatch = _math_family_mismatch_result(
            scope, function, expected_family="transform", result_name="math_transform"
        )
        if mismatch is not None:
            return mismatch
    return _state_scope_result("math_transform", scope.query_math_transform(function))


def _execute_math_filter(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_filter(
            function,
            parameters["operation"],
            parameters["source"],
            cutoff_hz=parameters.get("cutoff_hz"),
            average_count=parameters.get("average_count"),
            smooth_points=parameters.get("smooth_points"),
        )
    else:
        mismatch = _math_family_mismatch_result(
            scope, function, expected_family="filter", result_name="math_filter"
        )
        if mismatch is not None:
            return mismatch
    return _state_scope_result("math_filter", scope.query_math_filter(function))


def _execute_math_visualization(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_visualization(
            function,
            parameters["operation"],
            source=parameters.get("source"),
            source2=parameters.get("source2"),
            measurement=parameters.get("measurement"),
            measurement_slot=parameters.get("measurement_slot"),
        )
    else:
        mismatch = _math_family_mismatch_result(
            scope,
            function,
            expected_family="visualization",
            result_name="math_visualization",
        )
        if mismatch is not None:
            return mismatch
    return _state_scope_result(
        "math_visualization", scope.query_math_visualization(function)
    )


def _math_family_mismatch_result(
    scope: Any,
    function: int,
    *,
    expected_family: str,
    result_name: str,
) -> dict[str, Any] | None:
    state = scope.query_math_operation(function)
    if state.family == expected_family:
        return None
    return _state_scope_result(
        result_name,
        {
            "function": function,
            "active": False,
            "active_family": state.family,
            "active_operation": state.operation,
            "operation_raw": state.operation_raw,
        },
    )


def _execute_math_composite_source(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    if parameters["action"] == "set":
        scope.configure_math_composite_source(
            parameters["operation"],
            parameters["source1"],
            parameters["source2"],
        )
    return _state_scope_result("math_composite_source", scope.query_math_composite_source())


def _execute_general_scope_command(
    scope: Any,
    command: str,
    resource: str,
    parameters: Mapping[str, Any],
    artifact_dir: Path,
    *,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if command == "acquisition":
        return _execute_acquisition(scope, parameters)

    if command == "timebase-scale":
        if parameters["action"] == "set":
            scope.set_timebase_scale(parameters["seconds_per_division"])
        return _state_scope_result(
            "timebase",
            {"seconds_per_division": scope.query_timebase_scale()},
        )

    if command == "timebase-position":
        if parameters["action"] == "set":
            scope.set_timebase_position(parameters["position_seconds"])
        return _state_scope_result(
            "timebase",
            {"position_seconds": scope.query_timebase_position()},
        )

    if command == "timebase-reference":
        if parameters["action"] == "set":
            scope.set_timebase_reference(parameters["reference"])
        return _state_scope_result(
            "timebase",
            {"reference": scope.query_timebase_reference()},
        )

    if command == "channel-display":
        return _execute_channel_display(scope, parameters)

    if command == "channel-scale":
        return _execute_channel_scale(scope, parameters)

    if command == "channel-summary":
        return _state_scope_result("channels", scope.query_channel_summary())

    if command == "channel-label":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_label,
            getter=scope.query_channel_label,
            value_name="text",
            result_name="text",
        )

    if command == "channel-offset":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_offset,
            getter=scope.query_channel_offset,
            value_name="volts",
            result_name="volts",
        )

    if command == "channel-coupling":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_coupling,
            getter=scope.query_channel_coupling,
            value_name="coupling",
            result_name="coupling",
        )

    if command == "channel-probe":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_probe_ratio,
            getter=scope.query_channel_probe_ratio,
            value_name="ratio",
            result_name="ratio",
        )

    if command == "channel-bandwidth-limit":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_bandwidth_limit,
            getter=scope.query_channel_bandwidth_limit,
            value_name="enabled",
            result_name="enabled",
        )

    if command == "channel-impedance":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_impedance,
            getter=scope.query_channel_impedance,
            value_name="impedance",
            result_name="impedance",
        )

    if command == "channel-invert":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_invert,
            getter=scope.query_channel_invert,
            value_name="enabled",
            result_name="enabled",
        )

    if command == "channel-range":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_range,
            getter=scope.query_channel_range,
            value_name="volts",
            result_name="volts",
        )

    if command == "channel-units":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_units,
            getter=scope.query_channel_units,
            value_name="units",
            result_name="units",
        )

    if command == "channel-vernier":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_vernier,
            getter=scope.query_channel_vernier,
            value_name="enabled",
            result_name="enabled",
        )

    if command == "channel-probe-skew":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_probe_skew,
            getter=scope.query_channel_probe_skew,
            value_name="seconds",
            result_name="seconds",
        )

    if command == "display-label":
        return _execute_display_setting(parameters, scope.set_display_label, scope.query_display_label, "enabled")

    if command == "display-clear":
        scope.clear_display()
        return _simple_scope_result("display-clear")

    if command == "display-persistence":
        if parameters["action"] == "set":
            value = (
                parameters["seconds"]
                if parameters["mode"] == "timed"
                else parameters["mode"]
            )
            scope.set_display_persistence(value)
        persistence = scope.query_display_persistence()
        return _state_scope_result(
            "persistence",
            {
                "mode": persistence.mode or "timed",
                "seconds": persistence.seconds,
                "raw_value": persistence.raw_value,
            },
        )

    if command == "display-intensity":
        if parameters["action"] == "set":
            scope.set_display_intensity(parameters["value"])
        intensity, raw = scope.query_display_intensity()
        return _state_scope_result("intensity", {"value": intensity, "raw": raw})

    if command == "display-vectors":
        if parameters["action"] == "set":
            scope.set_display_vectors_on()
        enabled, raw = scope.query_display_vectors()
        return _state_scope_result("vectors", {"enabled": enabled, "raw": raw})

    if command == "measure":
        result = run_measure(scope, resource, _measure_request(parameters))
        return _operation_payload(result)

    if command == "measure-sweep":
        result = run_measure_sweep(
            scope, resource, _measure_sweep_request(parameters), stop_requested=stop_requested
        )
        return _operation_payload(result)

    if command == "measure-install":
        scope.install_measurement(parameters["source_channel"], parameters["item"])
        return _simple_scope_result("measure-install")

    if command == "measure-results":
        return _state_scope_result("measurements", scope.query_measurement_results())

    if command == "measure-clear":
        scope.clear_measurements()
        return _simple_scope_result("measure-clear")

    if command == "measure-menu":
        scope.open_measurement_menu()
        return _simple_scope_result("measure-menu")

    if command == "measure-show":
        if parameters["action"] == "set":
            scope.configure_measurement_show(parameters.get("enabled", True))
        return _state_scope_result("show", scope.query_measurement_show())

    if command == "measurement-statistics":
        action = parameters["action"]
        if action == "set":
            scope.configure_measurement_statistics_mode(parameters["mode"])
            scope.configure_measurement_statistics_display(parameters["display_enabled"])
            scope.configure_measurement_statistics_max_count(
                parameters.get("max_count")
                if parameters["max_count_mode"] == "numeric"
                else None
            )
            scope.configure_measurement_statistics_relative_stddev(
                parameters["relative_stddev_enabled"]
            )
        elif action == "reset":
            scope.reset_measurement_statistics()
        return _state_scope_result(
            "statistics",
            {
                "settings": scope.query_measurement_statistics_state(),
                "results": scope.query_measurement_results(),
            },
        )

    if command == "measure-source":
        if parameters["action"] == "set":
            scope.configure_measurement_source(
                parameters["source_channel"], parameters.get("source2_channel")
            )
        return _state_scope_result("source", scope.query_measurement_source())

    if command == "measure-window":
        if parameters["action"] == "set":
            scope.configure_measurement_window(parameters["window"])
        return _state_scope_result("window", scope.query_measurement_window())

    if command == "capture":
        csv_path, meta_path = _capture_output_paths(artifact_dir)
        result = run_capture(
            scope,
            resource,
            CaptureRequest(
                channels=tuple(parameters["channels"]),
                points=parameters["points"],
                waveform_format=parameters["format"],
                csv_path=csv_path,
                meta_path=meta_path,
            ),
        )
        return _operation_payload(result)

    if command == "screenshot":
        format_name = scope.capabilities.supported_screenshot_formats[0]
        capture = (scope.capture_screenshot_png(background=parameters["background"]) if format_name == "png" else
            scope.capture_screenshot(options=ScreenshotOptions(format=format_name), background=parameters["background"]))
        writer = write_screenshot_png_file if capture.format_name == "PNG" else write_screenshot
        path = writer(
            capture,
            _next_output_file(artifact_dir, "." + capture.format_name.lower()),
        )
        return {
            "exit_code": 0,
            "result": {
                "format": capture.format_name,
                "background": capture.background,
                "artifact": path.name,
            },
            "artifacts": [{"kind": "screenshot", "path": str(path)}],
        }

    if command == "reference-save":
        scope.save_reference_waveform(parameters["slot"], parameters["source_channel"])
        return _simple_scope_result("reference-save")

    if command == "reference-display":
        if parameters["action"] == "set":
            scope.configure_reference_display(parameters["slot"], parameters["enabled"])
        enabled, raw = scope.query_reference_display(parameters["slot"])
        return _state_scope_result(
            "display",
            {"slot": parameters["slot"], "enabled": enabled, "raw": raw},
        )

    if command == "reference-label":
        if parameters["action"] == "set":
            scope.configure_reference_label(parameters["slot"], parameters["label"])
        label, raw = scope.query_reference_label(parameters["slot"])
        return _state_scope_result(
            "label",
            {"slot": parameters["slot"], "label": label, "raw": raw},
        )

    if command == "reference-clear":
        scope.clear_reference_waveform(parameters["slot"])
        return _simple_scope_result("reference-clear")

    if command == "reference-query":
        return _state_scope_result(
            "reference", scope.query_reference_waveform(parameters["slot"])
        )

    if command == "cursor":
        action = parameters["action"]
        if action == "set":
            cursor_kwargs = {
                "x1_seconds": parameters.get("x1"),
                "x2_seconds": parameters.get("x2"),
                "y1_volts": parameters.get("y1"),
                "y2_volts": parameters.get("y2"),
            }
            if parameters.get("function") is not None:
                cursor_kwargs["function"] = parameters["function"]
            scope.configure_cursor(parameters.get("source_channel"), **cursor_kwargs)
        elif action == "off":
            scope.cursor_off()
        return _state_scope_result("cursor", scope.query_cursor())

    if command == "cursor-query":
        return _state_scope_result("cursor", scope.query_cursor())

    if command == "cursor-set":
        cursor_kwargs = {
            "x1_seconds": parameters.get("x1"),
            "x2_seconds": parameters.get("x2"),
            "y1_volts": parameters.get("y1"),
            "y2_volts": parameters.get("y2"),
        }
        if parameters.get("function") is not None:
            cursor_kwargs["function"] = parameters["function"]
        scope.configure_cursor(parameters.get("source_channel"), **cursor_kwargs)
        return _state_scope_result("cursor", scope.query_cursor())

    if command == "cursor-off":
        scope.cursor_off()
        return _state_scope_result("cursor", scope.query_cursor())

    if command == "annotation":
        action = parameters["action"]
        slot = parameters["slot"]
        if action == "set":
            if parameters.get("text") is not None:
                scope.set_annotation_text(parameters["text"], slot=slot)
            if parameters.get("color") is not None:
                scope.set_annotation_color(parameters["color"], slot=slot)
            if parameters.get("background") is not None:
                scope.set_annotation_background(parameters["background"], slot=slot)
            if parameters.get("x") is not None or parameters.get("y") is not None:
                scope.set_annotation_position(
                    parameters.get("x"), parameters.get("y"), slot=slot
                )
        elif action == "on":
            scope.set_annotation_enabled(True, slot=slot)
        elif action == "off":
            scope.set_annotation_enabled(False, slot=slot)
        elif action == "clear":
            scope.clear_annotation(slot=slot)
        return _state_scope_result("annotation", scope.query_annotation(slot=slot))

    if command == "annotation-query":
        slot = parameters.get("slot", 1)
        return _state_scope_result("annotation", scope.query_annotation(slot=slot))

    if command == "annotation-set":
        slot = parameters.get("slot", 1)
        if parameters.get("text") is not None:
            scope.set_annotation_text(parameters["text"], slot=slot)
        if parameters.get("color") is not None:
            scope.set_annotation_color(parameters["color"], slot=slot)
        if parameters.get("background") is not None:
            scope.set_annotation_background(parameters["background"], slot=slot)
        if parameters.get("x") is not None or parameters.get("y") is not None:
            scope.set_annotation_position(
                parameters.get("x"), parameters.get("y"), slot=slot
            )
        return _state_scope_result("annotation", scope.query_annotation(slot=slot))

    if command == "annotation-on":
        slot = parameters.get("slot", 1)
        scope.set_annotation_enabled(True, slot=slot)
        return _state_scope_result("annotation", scope.query_annotation(slot=slot))

    if command == "annotation-off":
        slot = parameters.get("slot", 1)
        scope.set_annotation_enabled(False, slot=slot)
        return _state_scope_result("annotation", scope.query_annotation(slot=slot))

    if command == "annotation-clear":
        slot = parameters.get("slot", 1)
        scope.clear_annotation(slot=slot)
        return _state_scope_result("annotation", scope.query_annotation(slot=slot))

    if command == "wgen-query":
        return _state_scope_result("wgen", scope.query_wgen())

    if command == "wgen-output":
        if parameters["action"] == "set":
            scope.configure_wgen_output(parameters["enabled"])
        return _state_scope_result("output", scope.query_wgen_output())

    if command == "wgen-function":
        if parameters["action"] == "set":
            scope.configure_wgen_function(parameters["function"])
        return _state_scope_result("function", scope.query_wgen_function())

    if command == "wgen-frequency":
        if parameters["action"] == "set":
            scope.configure_wgen_frequency(parameters["frequency_hz"])
        return _state_scope_result("frequency", scope.query_wgen_frequency())

    if command == "wgen-voltage":
        if parameters["action"] == "set":
            scope.configure_wgen_voltage(parameters["amplitude"])
        return _state_scope_result("voltage", scope.query_wgen_voltage())

    if command == "wgen-offset":
        if parameters["action"] == "set":
            scope.configure_wgen_offset(parameters["offset_volts"])
        return _state_scope_result("offset", scope.query_wgen_offset())

    if command == "wgen-load":
        if parameters["action"] == "set":
            scope.configure_wgen_load(parameters["load"])
        return _state_scope_result("load", scope.query_wgen_load())

    if command == "demo-query":
        return _state_scope_result("demo", scope.query_demo())

    if command == "demo-output":
        if parameters["action"] == "set":
            scope.configure_demo_output(parameters["enabled"])
        return _state_scope_result("output", scope.query_demo_output())

    if command == "demo-function":
        if parameters["action"] == "set":
            scope.configure_demo_function(parameters["function"])
        return _state_scope_result("function", scope.query_demo_function())

    if command == "demo-phase":
        if parameters["action"] == "set":
            scope.configure_demo_phase(parameters["degrees"])
        return _state_scope_result("phase", scope.query_demo_phase())

    if command == "save-pwd":
        return _execute_state_setting(
            parameters, scope.configure_save_pwd, scope.query_save_pwd, "path"
        )

    if command == "save-filename":
        return _execute_state_setting(
            parameters, scope.configure_save_filename, scope.query_save_filename, "name"
        )

    if command == "save-image-format":
        return _execute_state_setting(
            parameters,
            scope.configure_save_image_format,
            scope.query_save_image_format,
            "format",
        )

    if command == "save-image-palette":
        return _execute_state_setting(
            parameters,
            scope.configure_save_image_palette,
            scope.query_save_image_palette,
            "palette",
        )

    if command == "save-image-ink-saver":
        return _execute_state_setting(
            parameters,
            scope.configure_save_image_ink_saver,
            scope.query_save_image_ink_saver,
        )

    if command == "save-image-factors":
        return _execute_state_setting(
            parameters,
            scope.configure_save_image_factors,
            scope.query_save_image_factors,
        )

    if command == "save-image":
        return _state_scope_result("save", scope.save_image(parameters["filename"]).to_json())

    if command == "save-waveform-format":
        return _execute_state_setting(
            parameters,
            scope.configure_save_waveform_format,
            scope.query_save_waveform_format,
            "format",
        )

    if command == "save-waveform-length":
        return _execute_state_setting(
            parameters,
            scope.configure_save_waveform_length,
            scope.query_save_waveform_length,
            "points",
        )

    if command == "save-waveform-length-max":
        return _state_scope_result("state", scope.query_save_waveform_length_max())

    if command == "save-waveform":
        return _state_scope_result(
            "save", scope.save_waveform(parameters["filename"], source_channel=parameters.get("source_channel")).to_json()
        )

    if command == "setup-save":
        scope.save_setup(slot=parameters.get("slot"), file_spec=parameters.get("file"))
        return _simple_scope_result("setup-save")

    if command == "setup-recall":
        scope.recall_setup(slot=parameters.get("slot"), file_spec=parameters.get("file"))
        return _simple_scope_result("setup-recall")

    if command == "check-error":
        max_reads = int(parameters.get("max_reads", 20))
        entries = scope.drain_system_errors(max_reads=max_reads)
        entry_json = [_jsonable(entry) for entry in entries]
        return {
            "exit_code": 1 if any(entry.is_error for entry in entries) else 0,
            "result": {
                "drain": True,
                "max_reads": max_reads,
                "entries": entry_json,
                "system_error": entry_json[-1] if entry_json else None,
            },
            "artifacts": [],
        }

    if command == "system-status-byte":
        return {"exit_code": 0, "result": scope.query_status_byte().to_json(), "artifacts": []}

    if command == "system-operation-status":
        return {"exit_code": 0, "result": scope.query_operation_status().to_json(), "artifacts": []}

    if command == "system-clear-status":
        scope.clear_status()
        return _simple_scope_result("system-clear-status")

    if command == "system-opc":
        return _state_scope_result("operation_complete", scope.query_operation_complete())

    if command == "system-standard-event":
        return {"exit_code": 0, "result": scope.query_standard_event_status().to_json(), "artifacts": []}

    if command == "system-options":
        return {"exit_code": 0, "result": scope.query_system_options().to_json(), "artifacts": []}

    if command == "dvm-enable":
        return _execute_state_setting(parameters, scope.configure_dvm_enable, scope.query_dvm_enable)

    if command == "dvm-source":
        return _execute_state_setting(parameters, scope.configure_dvm_source, scope.query_dvm_source, "channel")

    if command == "dvm-mode":
        return _execute_state_setting(parameters, scope.configure_dvm_mode, scope.query_dvm_mode, "mode")

    if command == "dvm-auto-range":
        return _execute_state_setting(parameters, scope.configure_dvm_auto_range, scope.query_dvm_auto_range)

    if command == "dvm-current":
        return _state_scope_result("reading", scope.query_dvm_current())

    if command == "dvm-query":
        return _state_scope_result("dvm", scope.query_dvm())

    if command == "fft":
        return _execute_fft(scope, parameters)

    if command == "math-display":
        return _execute_math_display(scope, parameters)

    if command == "math-vertical":
        return _execute_math_vertical(scope, parameters)

    if command == "math-operator":
        return _execute_math_operator(scope, parameters)

    if command == "math-transform":
        return _execute_math_transform(scope, parameters)

    if command == "math-filter":
        return _execute_math_filter(scope, parameters)

    if command == "math-visualization":
        return _execute_math_visualization(scope, parameters)

    if command == "math-composite-source":
        return _execute_math_composite_source(scope, parameters)

    if command == "math-clear":
        scope.clear_math(parameters["function"])
        return _simple_scope_result("math-clear")
    raise WebUIRequestError(f"command is not supported by the Scopes Tool WebUI: {command}")
