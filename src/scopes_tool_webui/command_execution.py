"""WebUI Core-backed command execution and session lifecycle."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from scopes_tool_core import (
    CaptureBatchRequest,
    CaptureRequest,
    MeasureLogRequest,
    MeasureRequest,
    MeasureUntilRequest,
    OperationResult,
    ResolvedRunConfig,
    RunModeOptions,
    TriggeredCaptureSeriesRequest,
    TriggeredMeasureLoopRequest,
    capabilities_for_model_id,
    open_scope_for_run,
    plan_acquisition_check,
    plan_capture,
    plan_measure,
    plan_measure_until,
    plan_triggered_capture_series,
    plan_triggered_measure_loop,
    query_instrument_summary,
    run_capture,
    run_capture_batch,
    run_measure,
    run_measure_log,
    run_measure_until,
    run_triggered_capture_series,
    run_triggered_measure_loop,
)
from scopes_tool_core.batch import BATCH_DEFAULT_BASE_DIR, default_batch_output_dir
from scopes_tool_core.discovery import discover_visa_resources
from scopes_tool_core.measure_logger import (
    LOGGER_DEFAULT_BASE_DIR,
    default_measure_log_output_dir,
)
from scopes_tool_core.measure_until import MEASURE_UNTIL_DEFAULT_BASE_DIR
from scopes_tool_core.output_files import (
    default_capture_csv_path,
    write_serial_lister_csv,
    write_screenshot_png_file,
)
from scopes_tool_core.planning import (
    AcquisitionCheckPlanRequest,
    CapturePlanRequest,
    MeasurePlanRequest,
)
from scopes_tool_core.segmented_capture import (
    SEGMENTED_CAPTURE_DEFAULT_BASE_DIR,
    plan_segmented_capture,
    run_segmented_capture,
)
from scopes_tool_core.triggered_capture import TRIGGERED_CAPTURE_SERIES_DEFAULT_BASE_DIR
from scopes_tool_core.triggered_measurement import TRIGGERED_MEASURE_LOOP_DEFAULT_BASE_DIR

from .command_catalog import _TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMAND_IDS
from .command_validation import (
    WebUIRequestError,
    _segmented_capture_request,
    _validate_parameters,
)


class ScopeSessionCloseError(RuntimeError):
    """Raised when a job-owned scope session cannot be closed."""


def execute_command(
    command: str,
    *,
    mode: str,
    resource: str | None,
    model_id: str | None,
    parameters: Mapping[str, Any],
    artifact_dir: Path,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Execute one validated request through the public Core APIs."""

    if command == "list-resources":
        live_only = parameters.get("live_only", False)
        listing = discover_visa_resources(live_only=live_only)
        resources = (
            [resource.to_payload() for resource in listing.resources]
            if live_only
            else list(listing.resources)
        )
        return {
            "exit_code": 0,
            "result": {"resources": resources, "backend": listing.backend},
            "artifacts": [],
        }

    config = _run_config(mode, resource, model_id)
    if mode == "dry-run":
        if model_id is None:
            raise WebUIRequestError("dry-run execution requires a planning model")
        return _execute_dry_run(command, parameters, model_id, artifact_dir)

    scope = open_scope_for_run(config)
    try:
        normalized = dict(parameters)
        if mode == "live":
            idn = scope.idn or scope.query_idn()
            _validate_parameters(command, normalized, mode, idn.model_id)
        return _execute_scope_command(
            scope,
            command,
            resource or config.resource or "",
            normalized,
            artifact_dir,
            stop_requested=stop_requested,
        )
    finally:
        try:
            scope.close()
        except Exception as exc:
            raise ScopeSessionCloseError(f"scope session close failed: {exc}") from exc


def _execute_dry_run(
    command: str,
    parameters: Mapping[str, Any],
    model_id: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    capabilities = capabilities_for_model_id(model_id)
    if command == "measure":
        request = _measure_request(parameters)
        plan = plan_measure(
            MeasurePlanRequest(
                item=request.item,
                channel=request.channel,
                source_channel=request.source_channel,
                reference_channel=request.reference_channel,
                time_s=request.time_s,
                level=request.level,
                slope=request.slope,
                occurrence=request.occurrence,
            ),
            capabilities,
        )
    elif command == "capture":
        csv_path, meta_path = _capture_output_paths(artifact_dir)
        plan = plan_capture(
            CapturePlanRequest(
                channels=(parameters["channel"],),
                points=parameters["points"],
                waveform_format=parameters["format"],
                csv_path=csv_path,
                meta_path=meta_path,
            ),
            capabilities,
        )
    elif command == "acquisition":
        plan = plan_acquisition_check(
            AcquisitionCheckPlanRequest(
                average_count=parameters.get("count", 16),
                check_only=True,
            )
        )
    elif command == "measure-until":
        request = _measure_until_request(
            parameters,
            _workflow_output_dir(command, artifact_dir),
        )
        plan = plan_measure_until(request, capabilities)
    elif command == "triggered-measure-loop":
        request = _triggered_measure_loop_request(
            parameters,
            _workflow_output_dir(command, artifact_dir),
        )
        plan = plan_triggered_measure_loop(request, capabilities)
    elif command == "triggered-capture-series":
        request = _triggered_capture_series_request(
            parameters,
            _workflow_output_dir(command, artifact_dir),
        )
        plan = plan_triggered_capture_series(request, capabilities)
    elif command == "segmented-capture":
        request = _segmented_capture_request(
            parameters,
            _workflow_output_dir(command, artifact_dir),
        )
        planned_scpi, files, result = plan_segmented_capture(request, capabilities)
        return {
            "exit_code": 0,
            "result": {"status": "planned", "model_id": model_id, "planned_scpi": planned_scpi, **_jsonable(result)},
            "artifacts": [{**file, "path": str(file["path"])} for file in files],
        }
    else:
        raise WebUIRequestError(f"dry-run is not supported for {command}")
    return {
        "exit_code": 0,
        "result": {
            "status": "planned",
            "model_id": model_id,
            "planned_scpi": list(plan.planned_scpi),
            "files": [
                {"kind": file["kind"], "path": str(file["path"])}
                for file in plan.files
            ],
            **{
                key: _jsonable(value)
                for key, value in plan.result.items()
                if key != "files"
            },
        },
        "artifacts": [
            {**file, "path": str(file["path"])}
            for file in plan.files
        ],
    }


def _execute_scope_command(
    scope: Any,
    command: str,
    resource: str,
    parameters: Mapping[str, Any],
    artifact_dir: Path,
    *,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if scope.capabilities is None:
        scope.query_idn()
    if command in _TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMAND_IDS:
        return _execute_trigger_search_serial_segmented_workflow_command(
            scope,
            command,
            resource,
            parameters,
            artifact_dir,
            stop_requested=stop_requested,
        )
    if command == "identify":
        idn = scope.idn or scope.query_idn()
        idn_payload = _jsonable(idn)
        idn_payload["model_id"] = idn.model_id
        return {"exit_code": 0, "result": {"idn": idn_payload}, "artifacts": []}
    if command == "live-data-snapshot":
        return _state_scope_result("live_data", query_instrument_summary(scope))
    if command == "run":
        scope.run()
        return _simple_scope_result("run")
    if command == "single":
        scope.single()
        return _simple_scope_result("single")
    if command == "stop-acquisition":
        scope.stop()
        return _simple_scope_result("stop-acquisition")
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
    if command == "measure-results":
        return _state_scope_result("measurements", scope.query_measurement_results())
    if command == "measure-clear":
        scope.clear_measurements()
        return _simple_scope_result("measure-clear")
    if command == "measure-show":
        if parameters["action"] == "set":
            scope.configure_measurement_show(parameters.get("enabled", True))
        return _state_scope_result("show", scope.query_measurement_show())
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
                channels=(parameters["channel"],),
                points=parameters["points"],
                waveform_format=parameters["format"],
                csv_path=csv_path,
                meta_path=meta_path,
            ),
        )
        return _operation_payload(result)
    if command == "screenshot":
        capture = scope.capture_screenshot_png(background=parameters["background"])
        path = write_screenshot_png_file(
            capture,
            _next_output_file(artifact_dir, ".png"),
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
            "save", scope.save_waveform(parameters["filename"]).to_json()
        )
    if command == "check-error":
        entry = scope.query_system_error()
        return {
            "exit_code": 1 if entry.is_error else 0,
            "result": {"system_error": _jsonable(entry)},
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
    if command == "math-composite-source":
        return _execute_math_composite_source(scope, parameters)
    if command == "math-clear":
        scope.clear_math(parameters["function"])
        return _simple_scope_result("math-clear")
    raise WebUIRequestError(f"command is not supported by the Scopes Tool WebUI: {command}")


def _execute_trigger_search_serial_segmented_workflow_command(
    scope: Any,
    command: str,
    resource: str,
    parameters: Mapping[str, Any],
    artifact_dir: Path,
    *,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    action = parameters.get("action", "query")
    if command == "trigger-edge":
        if action == "set":
            scope.configure_trigger_edge(parameters["source_channel"], parameters["level"], parameters["slope"])
        return _state_scope_result("trigger", scope.query_trigger_edge())
    if command == "trigger-edge-source":
        if action == "set":
            scope.configure_trigger_edge_source(source=parameters["source"], source_channel=parameters.get("source_channel"))
        return _state_scope_result("source", scope.query_trigger_edge_source())
    if command == "trigger-edge-slope":
        if action == "set":
            scope.configure_trigger_edge_slope(slope=parameters["slope"])
        return _state_scope_result("slope", scope.query_trigger_edge_slope())
    if command == "trigger-edge-level":
        if action == "set":
            scope.configure_trigger_edge_level(source_channel=parameters["source_channel"], level_volts=parameters["level"])
        return _state_scope_result("level", scope.query_trigger_edge_level(source_channel=parameters["source_channel"]))
    if command == "external-trigger-range":
        if action == "set":
            scope.configure_external_trigger_range(parameters["range_volts"])
        return _state_scope_result("range", scope.query_external_trigger_range())
    if command == "trigger-edge-external-level":
        if action == "set":
            scope.configure_trigger_edge_external_level(level_volts=parameters["level"])
        return _state_scope_result("level", scope.query_trigger_edge_external_level())
    if command == "external-trigger-probe":
        if action == "set":
            scope.configure_external_trigger_probe(parameters["attenuation"])
        return _state_scope_result("probe", scope.query_external_trigger_probe())
    if command == "external-trigger-units":
        if action == "set":
            scope.configure_external_trigger_units(parameters["units"])
        return _state_scope_result("units", scope.query_external_trigger_units())
    if command == "external-trigger-settings":
        return _state_scope_result("settings", scope.query_external_trigger_settings())
    if command == "trigger-edge-coupling":
        if action == "set":
            scope.configure_trigger_edge_coupling(parameters["coupling"])
        return _state_scope_result("coupling", scope.query_trigger_edge_coupling())
    if command == "trigger-edge-reject":
        if action == "set":
            scope.configure_trigger_edge_reject(parameters["reject"])
        return _state_scope_result("reject", scope.query_trigger_edge_reject())
    if command == "trigger-pulse-width":
        if action == "set":
            scope.configure_glitch_trigger(
                channel=parameters["channel"], polarity=parameters["polarity"], qualifier=parameters["qualifier"],
                time_seconds=parameters.get("time_seconds"), min_time_seconds=parameters.get("min_time_seconds"),
                max_time_seconds=parameters.get("max_time_seconds"), level_volts=parameters.get("level"),
            )
        return _state_scope_result("trigger", scope.query_glitch_trigger())
    if command == "trigger-runt":
        if action == "set":
            scope.configure_runt_trigger(
                channel=parameters["channel"], polarity=parameters["polarity"], qualifier=parameters["qualifier"],
                low_level_volts=parameters["low_level"], high_level_volts=parameters["high_level"],
                time_seconds=parameters.get("time_seconds"),
            )
        return _state_scope_result("trigger", scope.query_runt_trigger())
    if command == "trigger-transition":
        if action == "set":
            scope.configure_transition_trigger(
                channel=parameters["channel"], slope=parameters["slope"], qualifier=parameters["qualifier"],
                low_level_volts=parameters["low_level"], high_level_volts=parameters["high_level"],
                time_seconds=parameters["time_seconds"],
            )
        return _state_scope_result("trigger", scope.query_transition_trigger())
    if command == "trigger-delay":
        if action == "set":
            scope.configure_delay_trigger(
                arm_channel=parameters["arm_channel"], arm_slope=parameters["arm_slope"],
                trigger_channel=parameters["trigger_channel"], trigger_slope=parameters["trigger_slope"],
                time_seconds=parameters["time_seconds"], count=parameters["count"],
            )
        return _state_scope_result("trigger", scope.query_delay_trigger())
    if command == "trigger-setup-hold":
        if action == "set":
            scope.configure_setup_hold_trigger(
                clock_channel=parameters["clock_channel"], data_channel=parameters["data_channel"],
                slope=parameters["slope"], setup_time_seconds=parameters["setup_time_seconds"],
                hold_time_seconds=parameters["hold_time_seconds"],
            )
        return _state_scope_result("trigger", scope.query_setup_hold_trigger())
    if command == "trigger-edge-burst":
        if action == "set":
            scope.configure_edge_burst_trigger(
                source_channel=parameters["source_channel"], slope=parameters["slope"], count=parameters["count"],
                idle_time=parameters["idle_time"], level_volts=parameters.get("level"),
            )
        return _state_scope_result("trigger", scope.query_edge_burst_trigger())
    if command == "trigger-tv":
        if action == "set":
            scope.configure_tv_trigger(
                source_channel=parameters["source_channel"], standard=parameters["standard"], mode=parameters["mode"],
                polarity=parameters["polarity"], line=parameters.get("line"),
            )
        return _state_scope_result("trigger", scope.query_tv_trigger())
    if command == "trigger-pattern":
        if action == "set":
            scope.configure_pattern_trigger(parameters["pattern"])
        return _state_scope_result("trigger", scope.query_pattern_trigger())
    if command == "trigger-or":
        if action == "set":
            scope.configure_or_trigger(parameters["pattern"])
        return _state_scope_result("trigger", scope.query_or_trigger())
    if command == "trigger-sweep":
        if action == "set":
            scope.configure_trigger_sweep(parameters["mode"])
        return _state_scope_result("sweep", scope.query_trigger_sweep())
    if command == "trigger-noise-reject":
        if action == "set":
            scope.configure_trigger_noise_reject(parameters["enabled"])
        return _state_scope_result("state", scope.query_trigger_noise_reject())
    if command == "trigger-hf-reject":
        if action == "set":
            scope.configure_trigger_hf_reject(parameters["enabled"])
        return _state_scope_result("state", scope.query_trigger_hf_reject())
    if command == "trigger-holdoff":
        if action == "set":
            scope.set_trigger_holdoff(parameters["seconds"])
        return _state_scope_result("seconds", scope.query_trigger_holdoff())

    if command == "search-state":
        if action == "set":
            scope.configure_search_state(parameters["enabled"])
        return _state_scope_result("state", scope.query_search_state())
    if command == "search-mode":
        if action == "set":
            scope.configure_search_mode(parameters["mode"])
        return _state_scope_result("mode", scope.query_search_mode())
    if command == "search-count":
        return _state_scope_result("count", scope.query_search_count())
    if command == "search-event":
        if action == "set":
            scope.configure_search_event(parameters["event"])
        return _state_scope_result("event", scope.query_search_event())
    if command.startswith("serial-search-"):
        protocol = command.removeprefix("serial-search-")
        bus = parameters["bus"]
        if action == "set":
            if protocol == "uart":
                scope.configure_serial_search_uart(bus, parameters["mode"], parameters.get("data"), parameters.get("qualifier"))
            elif protocol == "i2c":
                scope.configure_serial_search_i2c(bus, parameters["mode"], parameters.get("address"), parameters.get("data"), parameters.get("data2"), parameters.get("qualifier"))
            elif protocol == "spi":
                scope.configure_serial_search_spi(bus, parameters["mode"], parameters.get("data"), parameters.get("width"))
            else:
                scope.configure_serial_search_can(bus, parameters["mode"], parameters.get("data"), parameters.get("data_length"), parameters.get("id"), parameters.get("id_mode"))
        getter = getattr(scope, f"query_serial_search_{protocol}")
        return _state_scope_result("search", getter(bus))

    if command == "serial-query":
        return _state_scope_result("serial", scope.query_serial(parameters["bus"]))
    if command == "serial-mode":
        if action == "set":
            scope.configure_serial_mode(parameters["bus"], parameters["mode"])
        return _state_scope_result("mode", scope.query_serial_mode(parameters["bus"]))
    if command == "serial-display":
        if action == "set":
            scope.configure_serial_display(parameters["bus"], parameters["enabled"])
        return _state_scope_result("display", scope.query_serial_display(parameters["bus"]))
    if command in {"serial-uart", "serial-i2c", "serial-spi", "serial-can"}:
        protocol = command.removeprefix("serial-")
        bus = parameters["bus"]
        if action == "set":
            configure = getattr(scope, f"configure_serial_{protocol}")
            configure(**{key: value for key, value in parameters.items() if key not in {"action", "bus"}}, bus=bus)
        return _state_scope_result(protocol, getattr(scope, f"query_serial_{protocol}")(bus))
    if command in {"serial-trigger-uart", "serial-trigger-i2c", "serial-trigger-spi", "serial-trigger-can"}:
        protocol = command.removeprefix("serial-trigger-")
        bus = parameters["bus"]
        if action == "set":
            configure = getattr(scope, f"configure_serial_{protocol}_trigger")
            configure(**{key: value for key, value in parameters.items() if key not in {"action", "bus"}}, bus=bus)
        return _state_scope_result("trigger", getattr(scope, f"query_serial_{protocol}_trigger")(bus))
    if command == "serial-lister-query":
        return _state_scope_result("lister", scope.query_serial_lister())
    if command == "serial-lister-display":
        if action == "set":
            scope.configure_serial_lister_display(parameters["display"])
        return _state_scope_result("display", scope.query_serial_lister_display())
    if command == "serial-lister-reference":
        if action == "set":
            scope.configure_serial_lister_reference(parameters["reference"])
        return _state_scope_result("reference", scope.query_serial_lister_reference())
    if command == "serial-lister-export":
        target = artifact_dir / parameters["filename"]
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Serial Lister output file already exists: {target}")
        path = write_serial_lister_csv(scope.query_serial_lister_data(), target)
        return {"exit_code": 0, "result": {"output": path.name}, "artifacts": [{"kind": "serial-lister", "path": str(path)}]}

    if command == "segmented-memory":
        if action == "enable":
            scope.enable_segmented_memory(parameters["segments"])
        elif action == "disable":
            scope.disable_segmented_memory()
        return _state_scope_result("segmented", scope.query_segmented_memory())
    if command == "segmented-capture":
        output_dir = _workflow_output_dir(command, artifact_dir)
        return _operation_payload(
            run_segmented_capture(
                scope,
                resource,
                _segmented_capture_request(parameters, output_dir),
            )
        )
    if command == "capture-batch":
        output_dir = _workflow_output_dir(command, artifact_dir)
        return _operation_payload(
            run_capture_batch(
                scope,
                resource,
                _capture_batch_request(parameters, output_dir),
                stop_requested=stop_requested,
            )
        )
    if command == "measure-log":
        output_dir = _workflow_output_dir(command, artifact_dir)
        return _operation_payload(
            run_measure_log(
                scope,
                resource,
                _measure_log_request(parameters, output_dir),
                stop_requested=stop_requested,
            )
        )
    if command == "measure-until":
        output_dir = _workflow_output_dir(command, artifact_dir)
        return _operation_payload(
            run_measure_until(
                scope,
                resource,
                _measure_until_request(parameters, output_dir),
                stop_requested=stop_requested,
            )
        )
    if command == "triggered-measure-loop":
        output_dir = _workflow_output_dir(command, artifact_dir)
        return _operation_payload(
            run_triggered_measure_loop(
                scope,
                resource,
                _triggered_measure_loop_request(parameters, output_dir),
                stop_requested=stop_requested,
            )
        )
    if command == "triggered-capture-series":
        output_dir = _workflow_output_dir(command, artifact_dir)
        return _operation_payload(
            run_triggered_capture_series(
                scope,
                resource,
                _triggered_capture_series_request(parameters, output_dir),
                stop_requested=stop_requested,
            )
        )
    raise WebUIRequestError(f"command is not supported by the Scopes Tool WebUI: {command}")


def _execute_acquisition(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    action = parameters["action"]
    if action == "set":
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
        )
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
    return _state_scope_result("math_operator", scope.query_math_operator(function))


def _execute_math_composite_source(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    if parameters["action"] == "set":
        scope.configure_math_composite_source(
            parameters["operation"],
            parameters["source1"],
            parameters["source2"],
        )
    return _state_scope_result("math_composite_source", scope.query_math_composite_source())


def _state_scope_result(name: str, value: Any) -> dict[str, Any]:
    return {"exit_code": 0, "result": {name: _jsonable(value)}, "artifacts": []}


def _simple_scope_result(action: str) -> dict[str, Any]:
    return {"exit_code": 0, "result": {"action": action}, "artifacts": []}


def _operation_payload(result: OperationResult) -> dict[str, Any]:
    result_payload = _jsonable(result.result)
    if isinstance(result_payload, dict) and isinstance(result_payload.get("files"), list):
        result_payload["files"] = [
            {"kind": item.get("kind"), "name": Path(item["path"]).name}
            if isinstance(item, dict) and isinstance(item.get("path"), str)
            else item
            for item in result_payload["files"]
        ]
    return {
        "exit_code": result.exit_code,
        "result": result_payload,
        "system_error": _jsonable(result.system_error),
        "diagnostics": {"human_lines": list(result.human_lines)},
        "idn": _jsonable(result.idn),
        "backend": result.backend,
        "timeout_ms": result.timeout_ms,
        "artifacts": [dict(item) for item in result.files],
    }


def _run_config(mode: str, resource: str | None, model_id: str | None) -> ResolvedRunConfig:
    if mode != "live" and model_id is None:
        raise WebUIRequestError(f"{mode} execution requires a planning model")
    options = RunModeOptions(
        simulate=mode == "simulate",
        dry_run=mode == "dry-run",
        planning_physical_model_id=model_id if mode != "live" else None,
    )
    resolved_resource = resource
    if mode == "simulate":
        resolved_resource = resource or f"SIM::{model_id}::INSTR"
    elif mode == "dry-run":
        resolved_resource = resource or f"DRY::{model_id}::INSTR"
    return ResolvedRunConfig(
        mode="dry_run" if mode == "dry-run" else mode,
        planning_physical_model_id=model_id if mode != "live" else None,
        expected_physical_model_id=None,
        capabilities=(capabilities_for_model_id(model_id) if mode != "live" else None),
        resource=resolved_resource,
        options=options,
    )


def _measure_request(parameters: Mapping[str, Any]) -> MeasureRequest:
    return MeasureRequest(
        item=parameters["item"],
        channel=parameters.get("channel"),
        reference_channel=parameters.get("reference_channel"),
        time_s=parameters.get("time_s"),
        level=parameters.get("level"),
        slope=parameters.get("slope"),
        occurrence=parameters.get("occurrence"),
    )


def _next_output_file(
    output_root: Path,
    suffix: str,
    *,
    companion_suffixes: tuple[str, ...] = (),
) -> Path:
    stem = default_capture_csv_path().stem
    index = 1
    while True:
        candidate_stem = stem if index == 1 else f"{stem}-{index}"
        candidate = output_root / f"{candidate_stem}{suffix}"
        companions = tuple(
            output_root / f"{candidate_stem}{companion_suffix}"
            for companion_suffix in companion_suffixes
        )
        if not candidate.exists() and not any(path.exists() for path in companions):
            return candidate
        index += 1


def _capture_output_paths(output_root: Path) -> tuple[Path, Path]:
    csv_path = _next_output_file(
        output_root,
        ".csv",
        companion_suffixes=("_meta.json",),
    )
    return csv_path, csv_path.with_name(f"{csv_path.stem}_meta.json")


def _workflow_output_dir(command: str, output_root: Path) -> Path:
    if command == "measure-log":
        return default_measure_log_output_dir(
            base_dir=output_root / LOGGER_DEFAULT_BASE_DIR.name,
        )
    base_dirs = {
        "capture-batch": BATCH_DEFAULT_BASE_DIR,
        "measure-until": MEASURE_UNTIL_DEFAULT_BASE_DIR,
        "triggered-measure-loop": TRIGGERED_MEASURE_LOOP_DEFAULT_BASE_DIR,
        "triggered-capture-series": TRIGGERED_CAPTURE_SERIES_DEFAULT_BASE_DIR,
        "segmented-capture": SEGMENTED_CAPTURE_DEFAULT_BASE_DIR,
    }
    return default_batch_output_dir(
        base_dir=output_root / base_dirs[command].name,
    )


def _capture_batch_request(parameters: Mapping[str, Any], artifact_dir: Path) -> CaptureBatchRequest:
    return CaptureBatchRequest(
        channels=parameters["channels"], points=parameters["points"], waveform_format=parameters["format"],
        requested_count=parameters["count"], interval_seconds=parameters["interval_seconds"], output_dir=artifact_dir,
    )


def _measure_log_request(parameters: Mapping[str, Any], artifact_dir: Path) -> MeasureLogRequest:
    return MeasureLogRequest(
        channels=parameters.get("channels"), items=parameters["items"], pairs=parameters.get("pairs", []),
        pair_items=parameters["pair_items"], interval_seconds=parameters["interval_seconds"],
        requested_count=parameters.get("count"), requested_duration_seconds=parameters.get("duration_seconds"),
        output_dir=artifact_dir, stop_on_error=parameters.get("stop_on_error", False),
    )


def _measure_until_request(parameters: Mapping[str, Any], artifact_dir: Path) -> MeasureUntilRequest:
    return MeasureUntilRequest(
        channel=parameters["channel"], item=parameters["item"], operator=parameters["operator"],
        threshold=parameters["threshold"], timeout_seconds=parameters["timeout_seconds"],
        interval_seconds=parameters["interval_seconds"], output_dir=artifact_dir,
    )


def _triggered_measure_loop_request(parameters: Mapping[str, Any], artifact_dir: Path) -> TriggeredMeasureLoopRequest:
    return TriggeredMeasureLoopRequest(
        count=parameters["count"], trigger_timeout_seconds=parameters["trigger_timeout_seconds"],
        channels=parameters.get("channels"), items=parameters["items"], pairs=parameters.get("pairs", []),
        pair_items=parameters["pair_items"], interval_seconds=parameters["interval_seconds"], output_dir=artifact_dir,
    )


def _triggered_capture_series_request(parameters: Mapping[str, Any], artifact_dir: Path) -> TriggeredCaptureSeriesRequest:
    return TriggeredCaptureSeriesRequest(
        channels=parameters["channels"], count=parameters["count"],
        trigger_timeout_seconds=parameters["trigger_timeout_seconds"], points=parameters["points"],
        waveform_format=parameters["format"], interval_seconds=parameters["interval_seconds"], output_dir=artifact_dir,
    )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"byte_length": len(value)}
    return value
