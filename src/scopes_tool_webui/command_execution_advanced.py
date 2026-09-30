"""WebUI execution for Trigger, Search, Serial, segmented, and workflow commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from scopes_tool_core import (
    SequenceRequest,
    normalize_sequence_document,
    run_capture_batch,
    run_capture_monitor,
    run_capture_until,
    run_measure_log,
    run_measure_until,
    run_sequence,
    run_triggered_capture_series,
    run_triggered_measure_loop,
)
from scopes_tool_core.output_files import write_serial_lister_csv
from scopes_tool_core.segmented_capture import run_segmented_capture

from .command_execution_support import (
    _capture_batch_request,
    _capture_monitor_request,
    _capture_until_request,
    _measure_log_request,
    _measure_until_request,
    _operation_payload,
    _state_scope_result,
    _triggered_capture_series_request,
    _triggered_measure_loop_request,
    _workflow_output_dir,
)

from .command_validation import WebUIRequestError, _segmented_capture_request


def _execute_trigger_search_serial_segmented_workflow_command(
    scope: Any,
    command: str,
    resource: str,
    parameters: Mapping[str, Any],
    artifact_dir: Path,
    *,
    stop_requested: Callable[[], bool] | None = None,
    sample_reporter: Callable[[Mapping[str, object]], None] | None = None,
    progress_reporter: Callable[[Any], None] | None = None,
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
    if command == "trigger-mode":
        if action == "set":
            scope.configure_trigger_mode(parameters["mode"])
        return _state_scope_result("trigger", scope.query_trigger_mode())
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
        elif action == "select":
            scope.select_segmented_memory(parameters["index"])
        return _state_scope_result("segmented", scope.query_segmented_memory())
    if command == "segmented-capture":
        output_dir = _workflow_output_dir(command, artifact_dir)
        return _operation_payload(
            run_segmented_capture(
                scope,
                resource,
                _segmented_capture_request(parameters, output_dir),
                stop_requested=stop_requested,
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
                progress_reporter=progress_reporter,
            )
        )
    if command == "capture-until":
        output_dir = _workflow_output_dir(command, artifact_dir)
        return _operation_payload(
            run_capture_until(
                scope,
                resource,
                _capture_until_request(parameters, output_dir),
                stop_requested=stop_requested,
                progress_reporter=progress_reporter,
            )
        )
    if command == "capture-monitor":
        output_dir = (
            _workflow_output_dir(command, artifact_dir)
            if parameters.get("save_results", True)
            else None
        )
        return _operation_payload(
            run_capture_monitor(
                scope,
                resource,
                _capture_monitor_request(parameters, output_dir),
                stop_requested=stop_requested,
                sample_reporter=sample_reporter,
            )
        )
    if command == "measure-log":
        output_dir = _workflow_output_dir(command, artifact_dir) if parameters.get("save_results", True) else None
        return _operation_payload(
            run_measure_log(
                scope,
                resource,
                _measure_log_request(parameters, output_dir),
                stop_requested=stop_requested,
                progress_reporter=progress_reporter,
            )
        )
    if command == "measure-until":
        output_dir = _workflow_output_dir(command, artifact_dir) if parameters.get("save_results", True) else None
        return _operation_payload(
            run_measure_until(
                scope,
                resource,
                _measure_until_request(parameters, output_dir),
                stop_requested=stop_requested,
                progress_reporter=progress_reporter,
            )
        )
    if command == "triggered-measure-loop":
        output_dir = _workflow_output_dir(command, artifact_dir) if parameters.get("save_results", True) else None
        return _operation_payload(
            run_triggered_measure_loop(
                scope,
                resource,
                _triggered_measure_loop_request(parameters, output_dir),
                stop_requested=stop_requested,
                progress_reporter=progress_reporter,
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
                progress_reporter=progress_reporter,
            )
        )
    if command == "sequence":
        save_results = parameters.get("save_results", True)
        return _operation_payload(
            run_sequence(
                scope,
                resource,
                SequenceRequest(
                    normalize_sequence_document(parameters["document"]),
                    output_dir=_workflow_output_dir(command, artifact_dir) if save_results else None,
                    save_results=save_results,
                ),
                stop_requested=stop_requested,
                progress_reporter=progress_reporter,
            )
        )
    raise WebUIRequestError(f"command is not supported by the Scopes Tool WebUI: {command}")
