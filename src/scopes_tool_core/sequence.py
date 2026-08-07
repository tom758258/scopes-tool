"""Finite ordered Generic Sequence v1 workflow support."""

from __future__ import annotations
import copy

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import time
from typing import Mapping

from .capabilities import ScopeCapabilities
from .cleanup import CLEANUP_PROFILES, execute_cleanup, plan_cleanup
from .errors import OscilloscopeError, ParameterValidationError
from .measurements import is_pair_measurement_item, normalize_measurement_item
from .operations import (
    CaptureRequest,
    MeasureRequest,
    OperationResult,
    _OperationError,
    run_capture,
    run_measure,
)
from .output_files import write_json_file, write_json_file_best_effort, write_screenshot_png_file
from .planning import (
    CapturePlanRequest,
    MeasurePlanRequest,
    OperationPlan,
    measurement_query_kwargs,
    plan_capture,
    plan_measure,
)
from .screenshot import (
    DEFAULT_SCREENSHOT_BACKGROUND,
    hardcopy_inksaver_command,
    hardcopy_inksaver_for_background,
    hardcopy_inksaver_query,
    normalize_screenshot_background,
    screenshot_data_query,
)
from .scope import Oscilloscope
from .trigger import (
    TriggerWaitConfig,
    operation_condition_query,
    wait_for_current_trigger_completion,
)
from .waveform import SUPPORTED_WAVEFORM_POINTS
from .workflow import (
    ProgressReporter,
    StopRequested,
    WorkflowProgress,
    interruptible_wait,
    workflow_scpi_logging,
)


SEQUENCE_VERSION = 1
SEQUENCE_MANIFEST_SCHEMA_VERSION = 1
SEQUENCE_ACTIONS = (
    "wait",
    "single",
    "wait-trigger",
    "measure",
    "capture",
    "screenshot",
    "cleanup",
)
_SEQUENCE_TIMEZONE = timezone(timedelta(hours=8), name="UTC+8")
_SEQUENCE_DEFAULT_BASE_DIR = Path("data") / "sequences"


@dataclass(frozen=True)
class SequenceStep:
    """One normalized Generic Sequence v1 step."""

    action: str
    parameters: dict[str, object]

    def to_json(self) -> dict[str, object]:
        """Return the normalized JSON representation."""

        return {"action": self.action, "parameters": dict(self.parameters)}


@dataclass(frozen=True)
class SequenceDocument:
    """One normalized finite Generic Sequence v1 document."""

    version: int
    loop_count: int
    steps: tuple[SequenceStep, ...]

    def to_json(self) -> dict[str, object]:
        """Return the normalized JSON representation."""

        return {
            "version": self.version,
            "loop_count": self.loop_count,
            "steps": [step.to_json() for step in self.steps],
        }


@dataclass(frozen=True)
class SequenceRequest:
    """Normalized request for one Generic Sequence v1 execution."""

    document: SequenceDocument
    output_dir: str | Path | None = None
    log_scpi: bool = False


@dataclass(frozen=True)
class _StepOutcome:
    result: dict[str, object]
    files: tuple[dict[str, str], ...] = ()
    system_error: dict[str, object] | None = None
    status: str = "completed"


class _SequenceStepCancelled(Exception):
    pass


def load_sequence_document(path: str | Path) -> SequenceDocument:
    """Load and strictly normalize one JSON Sequence v1 document."""

    input_path = Path(path)
    try:
        text = input_path.read_text(encoding="utf-8")
        payload = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise OscilloscopeError(f"could not read sequence file {input_path}: {reason}") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise ParameterValidationError(
            f"invalid sequence JSON in {input_path}: {exc}"
        ) from exc
    return normalize_sequence_document(payload)


def normalize_sequence_document(payload: Mapping[str, object]) -> SequenceDocument:
    """Validate and normalize a Generic Sequence v1 document without hardware."""

    if not isinstance(payload, Mapping):
        raise ParameterValidationError("sequence document must be a JSON object")
    _require_exact_fields(payload, required={"version", "steps"}, optional={"loop_count"}, label="sequence document")
    version = _strict_integer(payload["version"], "sequence version")
    if version != SEQUENCE_VERSION:
        raise ParameterValidationError("sequence version must be 1")
    loop_count = _strict_integer(payload.get("loop_count", 1), "sequence loop_count")
    if loop_count < 1:
        raise ParameterValidationError("sequence loop_count must be at least 1")
    raw_steps = payload["steps"]
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ParameterValidationError("sequence steps must be a non-empty JSON array")

    steps: list[SequenceStep] = []
    for index, raw_step in enumerate(raw_steps, start=1):
        label = f"sequence step {index}"
        if not isinstance(raw_step, Mapping):
            raise ParameterValidationError(f"{label} must be a JSON object")
        _require_exact_fields(raw_step, required={"action", "parameters"}, optional=set(), label=label)
        action = raw_step["action"]
        if not isinstance(action, str) or action not in SEQUENCE_ACTIONS:
            supported = ", ".join(SEQUENCE_ACTIONS)
            raise ParameterValidationError(f"{label} action must be one of: {supported}")
        parameters = raw_step["parameters"]
        if not isinstance(parameters, Mapping):
            raise ParameterValidationError(f"{label} parameters must be a JSON object")
        steps.append(
            SequenceStep(
                action=action,
                parameters=_normalize_step_parameters(action, parameters, label),
            )
        )
    return SequenceDocument(version=version, loop_count=loop_count, steps=tuple(steps))


def plan_sequence(
    request: SequenceRequest,
    capabilities: ScopeCapabilities,
) -> OperationPlan:
    """Validate and plan one Sequence v1 without opening hardware or writing files."""

    document = _validate_and_normalize_request(request)
    output_dir = (
        Path(request.output_dir)
        if request.output_dir is not None
        else _SEQUENCE_DEFAULT_BASE_DIR / "DRY-RUN"
    )
    step_plans, planned_scpi = _plan_steps(document, capabilities, output_dir)
    files = (
        {"kind": "manifest", "path": str(output_dir / "manifest.json")},
        {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
    )
    result = {
        "status": "planned",
        "version": document.version,
        "loop_count": document.loop_count,
        "step_count": len(document.steps),
        "total_step_executions": document.loop_count * len(document.steps),
        "completed_loops": 0,
        "completed_step_executions": 0,
        "failed_step": None,
        "steps": step_plans,
        "files": list(files),
        "output_dir": str(output_dir),
        "manifest_path": str(output_dir / "manifest.json"),
        "scpi_log_path": str(output_dir / "scpi.log"),
        "error": None,
    }
    return OperationPlan(tuple(planned_scpi), files, result)


def run_sequence(
    scope: Oscilloscope,
    resource: str,
    request: SequenceRequest,
    *,
    stop_requested: StopRequested | None = None,
    progress_reporter: ProgressReporter | None = None,
) -> OperationResult:
    """Execute one finite ordered Generic Sequence v1 workflow."""

    document = _validate_and_normalize_request(request)
    if _stop_requested(stop_requested):
        return _pre_start_cancelled_result(document)

    idn = scope.query_idn()
    if scope.capabilities is None:
        raise OscilloscopeError("Capabilities unavailable for this model")

    output_dir = _sequence_output_path(request.output_dir)
    _plan_steps(document, scope.capabilities, output_dir)
    output_dir = _prepare_sequence_output_dir(output_dir)
    manifest_path = output_dir / "manifest.json"
    scpi_log_path = output_dir / "scpi.log"
    files: list[dict[str, str]] = [
        {"kind": "manifest", "path": str(manifest_path)},
        {"kind": "scpi_log", "path": str(scpi_log_path)},
    ]
    summaries = [
        {
            "step_index": index,
            "action": step.action,
            "parameters": dict(step.parameters),
            "completed_executions": 0,
            "last_result": None,
        }
        for index, step in enumerate(document.steps, start=1)
    ]
    total = document.loop_count * len(document.steps)
    manifest: dict[str, object] = {
        "schema_version": SEQUENCE_MANIFEST_SCHEMA_VERSION,
        "start_time": _sequence_timestamp(),
        "end_time": None,
        "status": "running",
        "resource": resource,
        "backend": getattr(scope.backend, "backend", None),
        "timeout_ms": getattr(scope.backend, "timeout", None),
        "idn": _idn_json(idn),
        "document": document.to_json(),
        "total_step_executions": total,
        "completed_loops": 0,
        "completed_step_executions": 0,
        "executions": [],
        "failed_step": None,
        "files": [_relative_file(item, output_dir) for item in files],
        "error": None,
    }
    human = [
        f"Sequence: {document.loop_count} loop(s), "
        f"{len(document.steps)} step(s), {total} execution(s)",
        f"Output directory: {output_dir}",
    ]
    last_system_error: dict[str, object] | None = None
    start_perf = time.perf_counter()
    _write_sequence_manifest(manifest, manifest_path)

    try:
        with workflow_scpi_logging(scpi_log_path, echo_to_stderr=request.log_scpi):
            for loop_index in range(1, document.loop_count + 1):
                if _stop_requested(stop_requested):
                    return _finish_sequence(
                        "cancelled", 130, manifest, manifest_path, scpi_log_path,
                        files, summaries, human, idn, last_system_error, scope,
                        output_dir, error=None,
                    )
                for step_index, step in enumerate(document.steps, start=1):
                    if _stop_requested(stop_requested):
                        return _finish_sequence(
                            "cancelled", 130, manifest, manifest_path, scpi_log_path,
                            files, summaries, human, idn, last_system_error, scope,
                            output_dir, error=None,
                        )
                    try:
                        outcome = _execute_step(
                            scope,
                            resource,
                            document,
                            output_dir,
                            loop_index,
                            step_index,
                            step,
                            stop_requested=stop_requested,
                        )
                    except _SequenceStepCancelled:
                        return _finish_sequence(
                            "cancelled", 130, manifest, manifest_path, scpi_log_path,
                            files, summaries, human, idn, last_system_error, scope,
                            output_dir, error=None,
                        )
                    except OscilloscopeError as exc:
                        _collect_existing_step_artifacts(
                            files, output_dir, document, loop_index, step_index, step, exc
                        )
                        failed = _failed_step(loop_index, step_index, step.action, exc)
                        manifest["failed_step"] = failed
                        return _finish_sequence(
                            "error", 1, manifest, manifest_path, scpi_log_path,
                            files, summaries, human, idn, last_system_error, scope,
                            output_dir, error=str(exc), failed_step=failed,
                        )

                    last_system_error = outcome.system_error or last_system_error
                    for item in outcome.files:
                        if item not in files:
                            files.append(dict(item))
                    if outcome.status != "completed":
                        message = _outcome_error_message(outcome)
                        failed = {
                            "loop_index": loop_index,
                            "step_index": step_index,
                            "action": step.action,
                            "error": {
                                "type": "instrument_error" if outcome.status == "instrument_error" else "step_error",
                                "message": message,
                            },
                        }
                        manifest["failed_step"] = failed
                        return _finish_sequence(
                            outcome.status, 1, manifest, manifest_path, scpi_log_path,
                            files, summaries, human, idn, last_system_error, scope,
                            output_dir, error=message, failed_step=failed,
                        )

                    completed = int(manifest["completed_step_executions"]) + 1
                    candidate_manifest = copy.deepcopy(manifest)
                    candidate_manifest["completed_step_executions"] = completed
                    if step_index == len(document.steps):
                        candidate_manifest["completed_loops"] = loop_index
                    record = {
                        "loop_index": loop_index,
                        "step_index": step_index,
                        "action": step.action,
                        "status": "completed",
                        "result": outcome.result,
                        "files": [_relative_file(item, output_dir) for item in outcome.files],
                    }
                    executions = candidate_manifest["executions"]
                    assert isinstance(executions, list)
                    executions.append(record)
                    candidate_manifest["files"] = [_relative_file(item, output_dir) for item in files]
                    try:
                        _write_sequence_manifest(candidate_manifest, manifest_path)
                    except OscilloscopeError as exc:
                        failed = _failed_step(loop_index, step_index, step.action, exc)
                        manifest["failed_step"] = failed
                        return _finish_sequence(
                            "error", 1, manifest, manifest_path, scpi_log_path,
                            files, summaries, human, idn, last_system_error, scope,
                            output_dir, error=str(exc), failed_step=failed,
                        )

                    manifest = candidate_manifest
                    summary = summaries[step_index - 1]
                    summary["completed_executions"] = int(summary["completed_executions"]) + 1
                    summary["last_result"] = outcome.result
                    human.append(
                        f"Loop {loop_index}/{document.loop_count}, "
                        f"step {step_index}/{len(document.steps)}: {step.action} completed"
                    )
                    if progress_reporter is not None:
                        progress_reporter(
                            WorkflowProgress(
                                completed_count=completed,
                                total_count=total,
                                elapsed_seconds=time.perf_counter() - start_perf,
                            )
                        )

                    if completed >= total:
                        return _finish_sequence(
                            "completed", 0, manifest, manifest_path, scpi_log_path,
                            files, summaries, human, idn, last_system_error, scope,
                            output_dir, error=None,
                        )
                    if _stop_requested(stop_requested):
                        return _finish_sequence(
                            "cancelled", 130, manifest, manifest_path, scpi_log_path,
                            files, summaries, human, idn, last_system_error, scope,
                            output_dir, error=None,
                        )
    except KeyboardInterrupt:
        return _finish_sequence(
            "interrupted", 130, manifest, manifest_path, scpi_log_path,
            files, summaries, human, idn, last_system_error, scope,
            output_dir, error="KeyboardInterrupt",
        )
    except OSError as exc:
        manifest["status"] = "error"
        manifest["end_time"] = _sequence_timestamp()
        manifest["error"] = str(exc)
        return _finish_sequence(
            "error", 1, manifest, manifest_path, scpi_log_path,
            files, summaries, human, idn, last_system_error, scope,
            output_dir, error=str(exc),
        )

    raise AssertionError("finite sequence exited without a terminal result")


def _normalize_step_parameters(
    action: str,
    parameters: Mapping[str, object],
    label: str,
) -> dict[str, object]:
    if action == "wait":
        _require_exact_fields(parameters, required={"seconds"}, optional=set(), label=f"{label} parameters")
        return {"seconds": _finite_number(parameters["seconds"], f"{label} seconds", minimum=0.0)}
    if action == "single":
        _require_exact_fields(parameters, required=set(), optional=set(), label=f"{label} parameters")
        return {}
    if action == "wait-trigger":
        _require_exact_fields(parameters, required={"timeout_seconds"}, optional=set(), label=f"{label} parameters")
        timeout = _finite_number(parameters["timeout_seconds"], f"{label} timeout_seconds", exclusive_minimum=0.0)
        return {"timeout_seconds": timeout}
    if action == "measure":
        allowed = {
            "item", "channel", "source_channel", "reference_channel",
            "time_s", "level", "slope", "occurrence",
        }
        _require_exact_fields(parameters, required={"item"}, optional=allowed - {"item"}, label=f"{label} parameters")
        item_value = parameters["item"]
        if not isinstance(item_value, str):
            raise ParameterValidationError(f"{label} measure item must be a string")
        item = normalize_measurement_item(item_value)
        normalized: dict[str, object] = {"item": item}
        for name in ("channel", "source_channel", "reference_channel", "occurrence"):
            if name in parameters:
                value = _strict_integer(parameters[name], f"{label} {name}")
                if value < 1:
                    raise ParameterValidationError(f"{label} {name} must be at least 1")
                normalized[name] = value
        for name in ("time_s", "level"):
            if name in parameters:
                normalized[name] = _finite_number(parameters[name], f"{label} {name}")
        if "slope" in parameters:
            slope = parameters["slope"]
            if not isinstance(slope, str) or slope not in {"positive", "negative"}:
                raise ParameterValidationError(f"{label} slope must be positive or negative")
            normalized["slope"] = slope
        request = _measure_plan_request(normalized)
        measurement_query_kwargs(request, item)
        if request.channel is not None and request.source_channel is not None:
            raise ParameterValidationError(f"{label} channel cannot be combined with source_channel")
        source = request.source_channel if request.source_channel is not None else request.channel
        if is_pair_measurement_item(item):
            if source is None or request.reference_channel is None:
                raise ParameterValidationError(f"{label} {item} requires source/channel and reference_channel")
            if source == request.reference_channel:
                raise ParameterValidationError(f"{label} source and reference channels must differ")
        else:
            if source is None:
                raise ParameterValidationError(f"{label} measure requires channel or source_channel")
            if request.reference_channel is not None:
                raise ParameterValidationError(f"{label} reference_channel is only valid for phase or delay")
        return normalized
    if action == "capture":
        allowed = {"channels", "points", "waveform_format", "allow_time_axis_tolerance"}
        _require_exact_fields(parameters, required={"channels"}, optional=allowed - {"channels"}, label=f"{label} parameters")
        raw_channels = parameters["channels"]
        if not isinstance(raw_channels, list) or not raw_channels:
            raise ParameterValidationError(f"{label} channels must be a non-empty JSON array")
        channels: list[int | str] = []
        for channel in raw_channels:
            if channel == "all" and isinstance(channel, str):
                channels.append(channel)
                continue
            value = _strict_integer(channel, f"{label} channel")
            if value < 1:
                raise ParameterValidationError(f"{label} channel must be at least 1")
            channels.append(value)
        if "all" in channels and channels != ["all"]:
            raise ParameterValidationError(f"{label} channels all cannot be combined with channel numbers")
        if len(set(channels)) != len(channels):
            raise ParameterValidationError(f"{label} duplicate channels are not allowed")
        points = _strict_integer(parameters.get("points", 1000), f"{label} points")
        if points not in SUPPORTED_WAVEFORM_POINTS:
            supported = ", ".join(str(value) for value in SUPPORTED_WAVEFORM_POINTS)
            raise ParameterValidationError(f"{label} points must be one of: {supported}")
        waveform_format = parameters.get("waveform_format", "byte")
        if not isinstance(waveform_format, str) or waveform_format not in {"byte", "word"}:
            raise ParameterValidationError(f"{label} waveform_format must be byte or word")
        tolerance = parameters.get("allow_time_axis_tolerance", False)
        if not isinstance(tolerance, bool):
            raise ParameterValidationError(f"{label} allow_time_axis_tolerance must be a boolean")
        return {
            "channels": channels,
            "points": points,
            "waveform_format": waveform_format,
            "allow_time_axis_tolerance": tolerance,
        }
    if action == "screenshot":
        _require_exact_fields(parameters, required=set(), optional={"background"}, label=f"{label} parameters")
        background = parameters.get("background", DEFAULT_SCREENSHOT_BACKGROUND)
        if not isinstance(background, str):
            raise ParameterValidationError(f"{label} background must be a string")
        return {"background": normalize_screenshot_background(background)}
    if action == "cleanup":
        _require_exact_fields(parameters, required=set(), optional={"profile"}, label=f"{label} parameters")
        profile = parameters.get("profile", "minimal")
        if not isinstance(profile, str) or profile not in CLEANUP_PROFILES:
            raise ParameterValidationError(
                f"{label} cleanup profile must be one of: {', '.join(CLEANUP_PROFILES)}"
            )
        return {"profile": profile}
    raise AssertionError(f"unsupported normalized sequence action: {action}")


def _plan_steps(
    document: SequenceDocument,
    capabilities: ScopeCapabilities,
    output_dir: Path,
) -> tuple[list[dict[str, object]], list[str]]:
    step_plans: list[dict[str, object]] = []
    planned_scpi: list[str] = []
    for index, step in enumerate(document.steps, start=1):
        step_scpi: list[str] = []
        artifact_template: str | None = None
        if step.action == "single":
            step_scpi = [":SINGle", ":SYSTem:ERRor?"]
        elif step.action == "wait-trigger":
            _trigger_wait_config(step)
            step_scpi = [operation_condition_query(), ":SYSTem:ERRor?"]
        elif step.action == "measure":
            plan = plan_measure(_measure_plan_request(step.parameters), capabilities)
            step_scpi = list(plan.planned_scpi)
        elif step.action == "capture":
            csv_path, meta_path = _capture_paths(output_dir, document, 1, index)
            plan = plan_capture(
                CapturePlanRequest(
                    channels=step.parameters["channels"],
                    points=int(step.parameters["points"]),
                    waveform_format=str(step.parameters["waveform_format"]),
                    csv_path=csv_path,
                    meta_path=meta_path,
                ),
                capabilities,
            )
            step_scpi = list(plan.planned_scpi)
            artifact_template = _artifact_template(document, index, "capture")
        elif step.action == "screenshot":
            if not capabilities.supports_screenshot:
                raise ParameterValidationError(
                    f"sequence step {index} screenshot is not supported by this model"
                )
            step_scpi = [
                hardcopy_inksaver_query(),
                screenshot_data_query(),
                ":SYSTem:ERRor?",
            ]
            artifact_template = _artifact_template(document, index, "screenshot")
        elif step.action == "cleanup":
            plan = plan_cleanup(str(step.parameters["profile"]), capabilities)
            step_scpi = list(plan.commands)
        plan_entry: dict[str, object] = {
            "step_index": index,
            "action": step.action,
            "parameters": dict(step.parameters),
            "planned_scpi": step_scpi,
        }
        if artifact_template is not None:
            plan_entry["artifact_path_template"] = artifact_template
        step_plans.append(plan_entry)
        planned_scpi.extend(step_scpi)
    return step_plans, planned_scpi


def _execute_step(
    scope: Oscilloscope,
    resource: str,
    document: SequenceDocument,
    output_dir: Path,
    loop_index: int,
    step_index: int,
    step: SequenceStep,
    *,
    stop_requested: StopRequested | None,
) -> _StepOutcome:
    if step.action == "wait":
        seconds = float(step.parameters["seconds"])
        if not interruptible_wait(seconds, stop_requested=stop_requested):
            raise _SequenceStepCancelled
        return _StepOutcome({"seconds": seconds})
    if step.action == "single":
        scope.single()
        entry = scope.query_system_error()
        system_error = _system_error_json(entry)
        return _StepOutcome(
            {"action": "single", "command": ":SINGle", "system_error": system_error},
            system_error=system_error,
            status="instrument_error" if entry.is_error else "completed",
        )
    if step.action == "wait-trigger":
        config = _trigger_wait_config(step)
        result = wait_for_current_trigger_completion(
            scope.scpi,
            config,
            classifier_profile=_trigger_classifier_profile(scope),
            stop_requested=stop_requested,
        )
        if result.outcome == "cancelled":
            raise _SequenceStepCancelled

        trigger_result = result.to_json(config)
        trigger_result["arm_command"] = None
        entry = scope.query_system_error()
        system_error = _system_error_json(entry)
        if entry.is_error:
            return _StepOutcome(
                {"trigger": trigger_result, "system_error": system_error},
                system_error=system_error,
                status="instrument_error",
            )
        status = "completed" if result.outcome in {"natural", "forced"} else "error"
        return _StepOutcome(
            {"trigger": trigger_result, "system_error": system_error},
            system_error=system_error,
            status=status,
        )
    if step.action == "measure":
        operation = run_measure(
            scope,
            resource,
            _measure_request(step.parameters),
        )
        status = _operation_status(operation)
        return _StepOutcome(
            dict(operation.result),
            tuple(operation.files),
            operation.system_error,
            status,
        )
    if step.action == "capture":
        csv_path, meta_path = _capture_paths(output_dir, document, loop_index, step_index)
        operation = run_capture(
            scope,
            resource,
            CaptureRequest(
                channels=step.parameters["channels"],
                points=int(step.parameters["points"]),
                waveform_format=str(step.parameters["waveform_format"]),
                csv_path=csv_path,
                meta_path=meta_path,
                allow_time_axis_tolerance=bool(step.parameters["allow_time_axis_tolerance"]),
            ),
        )
        return _StepOutcome(
            dict(operation.result),
            tuple(operation.files),
            operation.system_error,
            _operation_status(operation),
        )
    if step.action == "screenshot":
        output_path = _screenshot_path(output_dir, document, loop_index, step_index)
        capture = scope.capture_screenshot_png(background=str(step.parameters["background"]))
        written = write_screenshot_png_file(capture, output_path)
        entry = scope.query_system_error()
        system_error = _system_error_json(entry)
        file_info = {"kind": "png", "path": str(written)}
        return _StepOutcome(
            {
                "format": capture.format_name,
                "palette": capture.palette,
                "background": capture.background,
                "byte_count": len(capture.data),
                "image_path": str(written),
                "files": [file_info],
                "system_error": system_error,
            },
            (file_info,),
            system_error,
            "instrument_error" if entry.is_error else "completed",
        )
    if step.action == "cleanup":
        result = execute_cleanup(scope, str(step.parameters["profile"]))
        system_error = _system_error_json(result.final_error)
        return _StepOutcome(
            {**result.to_json(), "system_error": system_error},
            system_error=system_error,
            status="instrument_error" if result.final_error.is_error else "completed",
        )
    raise AssertionError(f"unsupported normalized sequence action: {step.action}")


def _finish_sequence(
    status: str,
    exit_code: int,
    manifest: dict[str, object],
    manifest_path: Path,
    scpi_log_path: Path,
    files: list[dict[str, str]],
    summaries: list[dict[str, object]],
    human: list[str],
    idn: object,
    system_error: dict[str, object] | None,
    scope: Oscilloscope,
    output_dir: Path,
    *,
    error: str | None,
    failed_step: dict[str, object] | None = None,
) -> OperationResult:
    document = manifest["document"]
    assert isinstance(document, dict)
    document_steps = document["steps"]
    assert isinstance(document_steps, list)
    manifest["status"] = status
    manifest["end_time"] = _sequence_timestamp()
    manifest["error"] = error
    manifest["failed_step"] = failed_step
    manifest["files"] = [_relative_file(item, output_dir) for item in files]
    write_json_file_best_effort(manifest, manifest_path)
    human.extend(
        [
            f"Sequence status: {status}",
            f"Completed step executions: {manifest['completed_step_executions']}/{manifest['total_step_executions']}",
            f"Manifest: {manifest_path}",
            f"SCPI log: {scpi_log_path}",
        ]
    )
    result = {
        "status": status,
        "version": SEQUENCE_VERSION,
        "loop_count": document["loop_count"],
        "step_count": len(document_steps),
        "total_step_executions": manifest["total_step_executions"],
        "completed_loops": manifest["completed_loops"],
        "completed_step_executions": manifest["completed_step_executions"],
        "failed_step": failed_step,
        "steps": summaries,
        "files": list(files),
        "output_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "scpi_log_path": str(scpi_log_path),
        "error": error,
    }
    return OperationResult(
        exit_code,
        result,
        list(files),
        system_error,
        list(human),
        idn=idn,
        backend=getattr(scope.backend, "backend", None),
        timeout_ms=getattr(scope.backend, "timeout", None),
    )


def _measure_plan_request(parameters: Mapping[str, object]) -> MeasurePlanRequest:
    return MeasurePlanRequest(
        item=str(parameters["item"]),
        channel=_optional_int(parameters.get("channel")),
        source_channel=_optional_int(parameters.get("source_channel")),
        reference_channel=_optional_int(parameters.get("reference_channel")),
        time_s=_optional_float(parameters.get("time_s")),
        level=_optional_float(parameters.get("level")),
        slope=_optional_str(parameters.get("slope")),
        occurrence=_optional_int(parameters.get("occurrence")),
    )


def _measure_request(parameters: Mapping[str, object]) -> MeasureRequest:
    plan = _measure_plan_request(parameters)
    return MeasureRequest(
        item=plan.item,
        channel=plan.channel,
        source_channel=plan.source_channel,
        reference_channel=plan.reference_channel,
        time_s=plan.time_s,
        level=plan.level,
        slope=plan.slope,
        occurrence=plan.occurrence,
    )


def _trigger_wait_config(step: SequenceStep) -> TriggerWaitConfig:
    timeout_ms = max(1, math.ceil(float(step.parameters["timeout_seconds"]) * 1000.0))
    return TriggerWaitConfig(timeout_ms=timeout_ms, poll_interval_ms=min(100, timeout_ms))


def _operation_status(operation: OperationResult) -> str:
    if operation.exit_code == 0:
        return "completed"
    if isinstance(operation.system_error, dict) and operation.system_error.get("is_error") is True:
        return "instrument_error"
    return "error"


def _outcome_error_message(outcome: _StepOutcome) -> str:
    if outcome.status == "instrument_error" and outcome.system_error is not None:
        return str(outcome.system_error.get("message") or "instrument error")
    trigger = outcome.result.get("trigger")
    if isinstance(trigger, dict):
        return f"trigger wait ended with outcome {trigger.get('outcome')}"
    error = outcome.result.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return str(error["message"])
    reason = outcome.result.get("reason")
    if isinstance(reason, str):
        return reason
    return "sequence step failed"


def _failed_step(loop_index: int, step_index: int, action: str, exc: Exception) -> dict[str, object]:
    return {
        "loop_index": loop_index,
        "step_index": step_index,
        "action": action,
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }


def _sequence_output_path(output_dir: str | Path | None) -> Path:
    if output_dir is not None:
        return Path(output_dir)
    stem = datetime.now(_SEQUENCE_TIMEZONE).strftime("%Y-%m-%d-%H-%M-%S")
    candidate = _SEQUENCE_DEFAULT_BASE_DIR / stem
    suffix = 2
    while candidate.exists():
        candidate = _SEQUENCE_DEFAULT_BASE_DIR / f"{stem}-{suffix}"
        suffix += 1
    return candidate


def _prepare_sequence_output_dir(path: Path) -> Path:
    if path.exists():
        if not path.is_dir():
            raise OscilloscopeError(f"output directory path is not a directory: {path}")
        try:
            if any(path.iterdir()):
                raise OscilloscopeError(f"output directory must be empty: {path}")
        except OSError as exc:
            raise OscilloscopeError(f"could not inspect output directory {path}: {exc}") from exc
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OscilloscopeError(f"could not create output directory {path}: {exc}") from exc
    return path


def _capture_paths(
    output_dir: Path,
    document: SequenceDocument,
    loop_index: int,
    step_index: int,
) -> tuple[Path, Path]:
    directory = output_dir / _loop_name(loop_index, document.loop_count) / f"{_step_name(step_index, len(document.steps))}_capture"
    return directory / "waveform.csv", directory / "waveform_meta.json"


def _screenshot_path(
    output_dir: Path,
    document: SequenceDocument,
    loop_index: int,
    step_index: int,
) -> Path:
    return output_dir / _loop_name(loop_index, document.loop_count) / f"{_step_name(step_index, len(document.steps))}_screenshot.png"


def _artifact_template(document: SequenceDocument, step_index: int, action: str) -> str:
    loop_width = max(4, len(str(document.loop_count)))
    step_width = max(4, len(str(len(document.steps))))
    if action == "capture":
        return f"loop_{{loop_index:0{loop_width}d}}/step_{step_index:0{step_width}d}_capture/"
    return f"loop_{{loop_index:0{loop_width}d}}/step_{step_index:0{step_width}d}_screenshot.png"


def _loop_name(index: int, count: int) -> str:
    return f"loop_{index:0{max(4, len(str(count)))}d}"


def _step_name(index: int, count: int) -> str:
    return f"step_{index:0{max(4, len(str(count)))}d}"


def _write_sequence_manifest(manifest: dict[str, object], path: Path) -> None:
    write_json_file(manifest, path, file_kind="sequence manifest JSON")


def _relative_file(item: Mapping[str, str], output_dir: Path) -> dict[str, str]:
    path = Path(item["path"])
    try:
        relative = path.relative_to(output_dir).as_posix()
    except ValueError:
        relative = path.as_posix()
    return {"kind": item["kind"], "path": relative}


def _idn_json(idn: object) -> dict[str, object]:
    return {
        "raw": getattr(idn, "raw", None),
        "vendor": getattr(idn, "vendor", None),
        "model": getattr(idn, "model", None),
        "series": getattr(idn, "series", None),
        "serial": getattr(idn, "serial", None),
        "firmware": getattr(idn, "firmware", None),
    }


def _system_error_json(entry: object) -> dict[str, object]:
    return {
        "code": getattr(entry, "code"),
        "message": getattr(entry, "message"),
        "raw": getattr(entry, "raw"),
        "is_error": bool(getattr(entry, "is_error")),
    }


def _trigger_classifier_profile(scope: Oscilloscope) -> str:
    if getattr(scope.backend, "backend", None) == "Keysight simulator":
        return "simulator"
    if scope.capabilities is not None and scope.capabilities.series in {"2000X", "3000X", "4000X"}:
        return scope.capabilities.series.lower()
    return "live"


def _sequence_timestamp() -> str:
    return datetime.now(_SEQUENCE_TIMEZONE).isoformat(timespec="seconds")


def _stop_requested(callback: StopRequested | None) -> bool:
    return callback is not None and callback()


def _strict_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ParameterValidationError(f"{label} must be an integer")
    return value


def _finite_number(
    value: object,
    label: str,
    *,
    minimum: float | None = None,
    exclusive_minimum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParameterValidationError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ParameterValidationError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise ParameterValidationError(f"{label} must be at least {minimum:g}")
    if exclusive_minimum is not None and result <= exclusive_minimum:
        raise ParameterValidationError(f"{label} must be greater than {exclusive_minimum:g}")
    return result


def _require_exact_fields(
    value: Mapping[str, object],
    *,
    required: set[str],
    optional: set[str],
    label: str,
) -> None:
    keys = set(value)
    missing = required - keys
    if missing:
        raise ParameterValidationError(f"{label} is missing field: {sorted(missing)[0]}")
    unknown = keys - required - optional
    if unknown:
        raise ParameterValidationError(f"{label} has unknown field: {sorted(unknown)[0]}")


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object field: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON number is not allowed: {value}")


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _validate_and_normalize_request(request: SequenceRequest) -> SequenceDocument:
    if not isinstance(request, SequenceRequest):
        raise ParameterValidationError("sequence request must be a SequenceRequest")
    if not isinstance(request.document, SequenceDocument):
        raise ParameterValidationError("sequence document must be a SequenceDocument")
    try:
        payload = request.document.to_json()
    except (AttributeError, TypeError, ValueError) as exc:
        raise ParameterValidationError(f"invalid sequence document: {exc}") from exc
    return normalize_sequence_document(payload)


def _pre_start_cancelled_result(document: SequenceDocument) -> OperationResult:
    total = document.loop_count * len(document.steps)
    summaries = [
        {
            "step_index": index,
            "action": step.action,
            "parameters": dict(step.parameters),
            "completed_executions": 0,
            "last_result": None,
        }
        for index, step in enumerate(document.steps, start=1)
    ]
    result = {
        "status": "cancelled",
        "version": SEQUENCE_VERSION,
        "loop_count": document.loop_count,
        "step_count": len(document.steps),
        "total_step_executions": total,
        "completed_loops": 0,
        "completed_step_executions": 0,
        "failed_step": None,
        "steps": summaries,
        "files": [],
        "output_dir": None,
        "manifest_path": None,
        "scpi_log_path": None,
        "error": None,
    }
    return OperationResult(
        130,
        result,
        [],
        None,
        ["Sequence execution cancelled before start"],
        idn=None,
        backend=None,
        timeout_ms=None,
    )


def _collect_existing_step_artifacts(
    files: list[dict[str, str]],
    output_dir: Path,
    document: SequenceDocument,
    loop_index: int,
    step_index: int,
    step: SequenceStep,
    exc: OscilloscopeError,
) -> None:
    if isinstance(exc, _OperationError):
        for item in exc.result.files:
            p = Path(item["path"])
            if p.exists() and item not in files:
                files.append(dict(item))
        return

    if step.action == "capture":
        csv_path, meta_path = _capture_paths(output_dir, document, loop_index, step_index)
        for path, kind in ((csv_path, "csv"), (meta_path, "json")):
            if path.exists():
                file_entry = {"kind": kind, "path": str(path)}
                if file_entry not in files:
                    files.append(file_entry)
    elif step.action == "screenshot":
        output_path = _screenshot_path(output_dir, document, loop_index, step_index)
        if output_path.exists():
            file_entry = {"kind": "png", "path": str(output_path)}
            if file_entry not in files:
                files.append(file_entry)
