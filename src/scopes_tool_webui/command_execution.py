"""WebUI Core-backed command execution and session lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from scopes_tool_core import (
    SequenceRequest,
    SmokeRequest,
    capabilities_for_model_id,
    normalize_sequence_document,
    open_scope_for_run,
    plan_acquisition_check,
    plan_capture,
    plan_capture_monitor,
    plan_capture_until,
    plan_measure,
    plan_measure_sweep,
    plan_measure_until,
    plan_sequence,
    plan_triggered_capture_series,
    plan_triggered_measure_loop,
    query_acquisition_readouts,
    query_instrument_summary,
    run_doctor,
    run_smoke,
)
from scopes_tool_core.discovery import discover_visa_resources
from scopes_tool_core.operation_types import _OperationError
from scopes_tool_core.simulator_backend import SimulatorInstrumentState
from scopes_tool_core.planning import (
    AcquisitionCheckPlanRequest,
    CapturePlanRequest,
    MeasurePlanRequest,
    MeasureSweepPlanRequest,
)
from scopes_tool_core.segmented_capture import plan_segmented_capture

from .command_execution_support import (
    _capture_batch_request,
    _capture_monitor_request,
    _capture_output_paths,
    _capture_until_request,
    _jsonable,
    _measure_log_request,
    _measure_request,
    _measure_sweep_request,
    _measure_until_request,
    _operation_payload,
    _run_config,
    _simple_scope_result,
    _state_scope_result,
    _triggered_capture_series_request,
    _triggered_measure_loop_request,
    _workflow_output_dir,
)
from .command_execution_general import _execute_general_scope_command
from .command_execution_advanced import (
    _execute_trigger_search_serial_segmented_workflow_command,
)

from .command_catalog import _TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMAND_IDS
from .command_validation import (
    WebUIRequestError,
    _segmented_capture_request,
    _single_wait_config,
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
    sample_reporter: Callable[[Mapping[str, object]], None] | None = None,
    progress_reporter: Callable[[Any], None] | None = None,
    simulator_state: SimulatorInstrumentState | None = None,
    simulator_state_reporter: Callable[[SimulatorInstrumentState], None] | None = None,
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

    scope = (
        open_scope_for_run(config, simulator_state=simulator_state)
        if mode == "simulate"
        else open_scope_for_run(config)
    )
    try:
        normalized = dict(parameters)
        if mode == "live":
            idn = scope.idn or scope.query_idn()
            _validate_parameters(command, normalized, mode, idn.model_id)
        execution = _execute_scope_command(
            scope,
            command,
            resource or config.resource or "",
            normalized,
            artifact_dir,
            stop_requested=stop_requested,
            sample_reporter=sample_reporter,
            progress_reporter=progress_reporter,
        )
        if mode == "live":
            scope.post_webui_operation_status(command)
        if mode == "simulate" and simulator_state_reporter is not None:
            simulator_state_reporter(scope.backend.export_instrument_state())
        return execution
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
    if command == "acquisition":
        from scopes_tool_core.drivers import driver_for_physical_model
        from scopes_tool_core.identity import physical_model_for_id

        driver = driver_for_physical_model(physical_model_for_id(model_id))
        driver_plan = driver.plan_webui_acquisition(parameters, capabilities)
        if driver_plan is not None:
            return {
                "exit_code": 0,
                "result": {"status": "planned", "model_id": model_id, "planned_scpi": driver_plan},
                "artifacts": [],
            }
    if command == "sequence":
        save_results = parameters.get("save_results", True)
        plan = plan_sequence(
            SequenceRequest(
                normalize_sequence_document(parameters["document"]),
                output_dir=_workflow_output_dir(command, artifact_dir) if save_results else None,
                save_results=save_results,
            ),
            capabilities,
        )
    elif command == "measure":
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
    elif command == "measure-sweep":
        request = _measure_sweep_request(parameters)
        plan = plan_measure_sweep(
            MeasureSweepPlanRequest(
                channels=request.channels,
                items=request.items,
                pairs=request.pairs,
                pair_items=request.pair_items,
            ),
            capabilities,
        )
    elif command == "capture":
        csv_path, meta_path = _capture_output_paths(artifact_dir)
        plan = plan_capture(
            CapturePlanRequest(
                channels=tuple(parameters["channels"]),
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
            ),
            capabilities,
        )
    elif command == "measure-until":
        save_results = parameters.get("save_results", True)
        request = _measure_until_request(
            parameters,
            _workflow_output_dir(command, artifact_dir) if save_results else None,
        )
        plan = plan_measure_until(request, capabilities)
    elif command == "capture-until":
        request = _capture_until_request(
            parameters, _workflow_output_dir(command, artifact_dir)
        )
        plan = plan_capture_until(request, capabilities)
    elif command == "capture-monitor":
        save_results = parameters.get("save_results", True)
        request = _capture_monitor_request(
            parameters,
            _workflow_output_dir(command, artifact_dir) if save_results else None,
        )
        plan = plan_capture_monitor(request, capabilities)
    elif command == "triggered-measure-loop":
        save_results = parameters.get("save_results", True)
        request = _triggered_measure_loop_request(
            parameters,
            _workflow_output_dir(command, artifact_dir) if save_results else None,
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
    sample_reporter: Callable[[Mapping[str, object]], None] | None = None,
    progress_reporter: Callable[[Any], None] | None = None,
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
            sample_reporter=sample_reporter,
            progress_reporter=progress_reporter,
        )

    if command == "identify":
        idn = scope.idn or scope.query_idn()
        idn_payload = _jsonable(idn)
        idn_payload["model_id"] = idn.model_id
        return {"exit_code": 0, "result": {"idn": idn_payload}, "artifacts": []}

    if command == "live-data-snapshot":
        return _state_scope_result("live_data", query_instrument_summary(scope))

    if command == "system-information-snapshot":
        idn = scope.idn or scope.query_idn()
        idn_payload = _jsonable(idn)
        idn_payload["model_id"] = idn.model_id
        acquisition_readouts = query_acquisition_readouts(scope)
        result = {
            "idn": idn_payload,
            "acquisition": acquisition_readouts,
        }
        return {"exit_code": 0, "result": result, "artifacts": []}

    if command == "doctor":
        return _operation_payload(run_doctor(scope, resource))

    if command == "smoke":
        save_artifacts = parameters.get("save_artifacts", False)
        output_dir = _workflow_output_dir(command, artifact_dir) if save_artifacts else None
        try:
            return _operation_payload(
                run_smoke(
                    scope,
                    resource,
                    SmokeRequest(output_dir=output_dir, save_artifacts=save_artifacts),
                )
            )
        except _OperationError as exc:
            return _operation_payload(exc.result)

    if command == "run":
        scope.run()
        return _simple_scope_result("run")

    if command == "single":
        scope.single()
        return _simple_scope_result("single")

    if command == "single-wait":
        config = _single_wait_config(dict(parameters))
        result = scope.single_wait(config, stop_requested=stop_requested)
        return {
            "exit_code": 0 if result.outcome in {"natural", "forced"} else 1,
            "result": {"operation": "single-wait", **result.to_json(config)},
            "artifacts": [],
        }

    if command == "stop-acquisition":
        scope.stop()
        return _simple_scope_result("stop-acquisition")

    if command == "force-trigger":
        scope.force_trigger()
        return _simple_scope_result("force-trigger")

    if command == "autoscale":
        scope.autoscale(
            parameters.get("channels"),
            acquire_mode=parameters.get("acquire_mode"),
            channels_mode=parameters.get("channels_mode"),
        )
        return _simple_scope_result("autoscale")
    return _execute_general_scope_command(
        scope, command, resource, parameters, artifact_dir,
        stop_requested=stop_requested,
    )
