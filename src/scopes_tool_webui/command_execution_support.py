"""Shared WebUI command execution results, requests, and output paths."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from scopes_tool_core import (
    CaptureBatchRequest,
    CaptureMonitorRequest,
    CaptureUntilRequest,
    MeasureLogRequest,
    MeasureRequest,
    MeasureSweepRequest,
    MeasureUntilRequest,
    OperationResult,
    ResolvedRunConfig,
    RunModeOptions,
    TriggeredCaptureSeriesRequest,
    TriggeredMeasureLoopRequest,
    capabilities_for_model_id,
)
from scopes_tool_core.batch import BATCH_DEFAULT_BASE_DIR, default_batch_output_dir
from scopes_tool_core.measure_logger import (
    LOGGER_DEFAULT_BASE_DIR,
    default_measure_log_output_dir,
)
from scopes_tool_core.measure_until import MEASURE_UNTIL_DEFAULT_BASE_DIR
from scopes_tool_core.capture_until import CAPTURE_UNTIL_DEFAULT_BASE_DIR
from scopes_tool_core.capture_monitor import CAPTURE_MONITOR_DEFAULT_BASE_DIR
from scopes_tool_core.output_files import default_capture_csv_path
from scopes_tool_core.segmented_capture import SEGMENTED_CAPTURE_DEFAULT_BASE_DIR
from scopes_tool_core.triggered_capture import TRIGGERED_CAPTURE_SERIES_DEFAULT_BASE_DIR
from scopes_tool_core.triggered_measurement import (
    TRIGGERED_MEASURE_LOOP_DEFAULT_BASE_DIR,
)

from .command_validation import WebUIRequestError


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


def _measure_sweep_request(parameters: Mapping[str, Any]) -> MeasureSweepRequest:
    return MeasureSweepRequest(
        channels=parameters.get("channels"),
        items=parameters.get("items", "vpp,frequency,period,vrms"),
        pairs=parameters.get("pairs", ()),
        pair_items=parameters.get("pair_items", "phase,delay"),
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
        "capture-until": CAPTURE_UNTIL_DEFAULT_BASE_DIR,
        "capture-monitor": CAPTURE_MONITOR_DEFAULT_BASE_DIR,
        "measure-until": MEASURE_UNTIL_DEFAULT_BASE_DIR,
        "triggered-measure-loop": TRIGGERED_MEASURE_LOOP_DEFAULT_BASE_DIR,
        "triggered-capture-series": TRIGGERED_CAPTURE_SERIES_DEFAULT_BASE_DIR,
        "segmented-capture": SEGMENTED_CAPTURE_DEFAULT_BASE_DIR,
        "sequence": Path("sequences"),
        "smoke": Path("hardware_smoke"),
    }
    return default_batch_output_dir(
        base_dir=output_root / base_dirs[command].name,
    )


def _capture_batch_request(parameters: Mapping[str, Any], artifact_dir: Path) -> CaptureBatchRequest:
    return CaptureBatchRequest(
        channels=parameters["channels"], points=parameters["points"], waveform_format=parameters["format"],
        requested_count=parameters["count"], interval_seconds=parameters["interval_seconds"], output_dir=artifact_dir,
    )


def _capture_until_request(
    parameters: Mapping[str, Any], artifact_dir: Path
) -> CaptureUntilRequest:
    return CaptureUntilRequest(
        channels=parameters["channels"],
        condition_channel=parameters["condition_channel"],
        points=parameters["points"],
        waveform_format=parameters["format"],
        metric=parameters["metric"],
        operator=parameters["operator"],
        threshold=parameters["threshold"],
        count=parameters["count"],
        timeout_seconds=parameters["timeout_seconds"],
        interval_seconds=parameters["interval_seconds"],
        output_dir=artifact_dir,
    )


def _capture_monitor_request(
    parameters: Mapping[str, Any], artifact_dir: Path | None
) -> CaptureMonitorRequest:
    return CaptureMonitorRequest(
        channels=parameters["channels"],
        points=parameters["points"],
        waveform_format=parameters["format"],
        count=parameters["count"],
        interval_seconds=parameters["interval_seconds"],
        retention_points=parameters["retention_points"],
        save_results=parameters.get("save_results", True),
        output_dir=artifact_dir,
    )


def _measure_log_request(parameters: Mapping[str, Any], artifact_dir: Path | None) -> MeasureLogRequest:
    return MeasureLogRequest(
        channels=parameters.get("channels"), items=parameters["items"], pairs=parameters.get("pairs", []),
        pair_items=parameters["pair_items"], interval_seconds=parameters["interval_seconds"],
        requested_count=parameters.get("count"), requested_duration_seconds=parameters.get("duration_seconds"),
        output_dir=artifact_dir, save_results=parameters.get("save_results", True),
        stop_on_error=parameters.get("stop_on_error", False),
    )


def _measure_until_request(parameters: Mapping[str, Any], artifact_dir: Path | None) -> MeasureUntilRequest:
    return MeasureUntilRequest(
        channel=parameters["channel"], item=parameters["item"], operator=parameters["operator"],
        threshold=parameters["threshold"], timeout_seconds=parameters["timeout_seconds"],
        interval_seconds=parameters["interval_seconds"], output_dir=artifact_dir,
        save_results=parameters.get("save_results", True),
    )


def _triggered_measure_loop_request(parameters: Mapping[str, Any], artifact_dir: Path | None) -> TriggeredMeasureLoopRequest:
    return TriggeredMeasureLoopRequest(
        count=parameters["count"], trigger_timeout_seconds=parameters["trigger_timeout_seconds"],
        channels=parameters.get("channels"), items=parameters["items"], pairs=parameters.get("pairs", []),
        pair_items=parameters["pair_items"], interval_seconds=parameters["interval_seconds"], output_dir=artifact_dir,
        save_results=parameters.get("save_results", True),
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
