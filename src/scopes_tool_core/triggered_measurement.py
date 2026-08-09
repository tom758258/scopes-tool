"""Finite triggered measurement loop workflow."""

from __future__ import annotations

import copy
import csv
from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Callable, Mapping, Sequence

from .batch import (
    batch_iso_timestamp,
    idn_manifest_dict,
    prepare_batch_output_dir,
    relative_manifest_path,
    system_error_manifest_dict,
    write_batch_manifest,
)
from .capabilities import ScopeCapabilities
from .errors import OscilloscopeError, ParameterValidationError
from .measurements import measurement_query, pair_measurement_query
from .operations import OperationResult, _trigger_wait_classifier_profile
from .planning import (
    OperationPlan,
    parse_measurement_item_list,
    parse_pair_specs,
    resolve_sweep_channels,
)
from .scope import Oscilloscope
from .trigger import (
    TriggerWaitConfig,
    operation_condition_query,
    single_command,
    wait_for_current_trigger_completion,
)
from .workflow import (
    ProgressReporter,
    StopRequested,
    WorkflowProgress,
    interruptible_wait,
    workflow_scpi_logging,
)


TRIGGERED_MEASURE_LOOP_SCHEMA_VERSION = 1
TRIGGERED_MEASURE_LOOP_DEFAULT_BASE_DIR = (
    Path("data") / "triggered_measure_loops"
)

SampleReporter = Callable[[Mapping[str, object]], None]


@dataclass(frozen=True)
class TriggeredMeasureLoopRequest:
    """Inputs for one finite triggered measurement loop."""

    count: int
    trigger_timeout_seconds: float
    channels: Sequence[int | str] | None = None
    items: str = "vpp,frequency"
    pairs: Sequence[str] = ()
    pair_items: str = "phase,delay"
    interval_seconds: float = 0.0
    output_dir: str | Path | None = None
    log_scpi: bool = False


def plan_triggered_measure_loop(
    request: TriggeredMeasureLoopRequest,
    capabilities: ScopeCapabilities,
) -> OperationPlan:
    """Validate and plan one representative cycle without hardware or files."""

    normalized = _normalize_request(request, capabilities)
    output_dir = (
        Path(request.output_dir)
        if request.output_dir is not None
        else TRIGGERED_MEASURE_LOOP_DEFAULT_BASE_DIR / "DRY-RUN"
    )
    csv_path, manifest_path, scpi_log_path = _workflow_paths(output_dir)
    files = (
        {"kind": "csv", "path": str(csv_path)},
        {"kind": "manifest", "path": str(manifest_path)},
        {"kind": "scpi_log", "path": str(scpi_log_path)},
    )
    planned = [single_command(), operation_condition_query()]
    planned.extend(_measurement_queries(normalized, capabilities))
    planned.append(":SYSTem:ERRor?")
    result = {
        "status": "planned",
        **_selection_result(normalized),
        "requested_count": request.count,
        "completed_count": 0,
        "trigger_timeout_seconds": float(request.trigger_timeout_seconds),
        "interval_seconds": float(request.interval_seconds),
        "cycles": [],
        "output_dir": str(output_dir),
        "csv_path": str(csv_path),
        "manifest_path": str(manifest_path),
        "scpi_log_path": str(scpi_log_path),
        "error": None,
    }
    return OperationPlan(tuple(planned), files, result)


def run_triggered_measure_loop(
    scope: Oscilloscope,
    resource: str,
    request: TriggeredMeasureLoopRequest,
    *,
    stop_requested: StopRequested | None = None,
    progress_reporter: ProgressReporter | None = None,
    sample_reporter: SampleReporter | None = None,
) -> OperationResult:
    """Run a finite Single, trigger-wait, and measurement cycle loop."""

    _validate_request_fields(request)
    if _stop_requested(stop_requested):
        return _pre_start_cancelled_result(request)

    idn = scope.query_idn()
    if scope.capabilities is None:
        raise OscilloscopeError("Capabilities unavailable for this model")
    normalized = _normalize_request(request, scope.capabilities)

    output_dir = prepare_batch_output_dir(
        request.output_dir,
        base_dir=TRIGGERED_MEASURE_LOOP_DEFAULT_BASE_DIR,
    )
    csv_path, manifest_path, scpi_log_path = _workflow_paths(output_dir)
    files = [
        {"kind": "csv", "path": str(csv_path)},
        {"kind": "manifest", "path": str(manifest_path)},
        {"kind": "scpi_log", "path": str(scpi_log_path)},
    ]
    manifest: dict[str, object] = {
        "schema_version": TRIGGERED_MEASURE_LOOP_SCHEMA_VERSION,
        "start_time": batch_iso_timestamp(),
        "end_time": None,
        "status": "running",
        "resource": resource,
        "backend": getattr(scope.backend, "backend", None),
        "timeout_ms": getattr(scope.backend, "timeout", None),
        "idn": idn_manifest_dict(idn),
        **_selection_result(normalized),
        "requested_count": request.count,
        "completed_count": 0,
        "trigger_timeout_seconds": float(request.trigger_timeout_seconds),
        "interval_seconds": float(request.interval_seconds),
        "cycles": [],
        "files": [
            {"kind": item["kind"], "path": relative_manifest_path(item["path"], output_dir)}
            for item in files
        ],
        "error": None,
    }
    human = [
        f"Triggered measurement loop: {request.count} cycle(s)",
        f"Trigger timeout seconds: {float(request.trigger_timeout_seconds):.12g}",
        f"Interval seconds: {float(request.interval_seconds):.12g}",
        f"Output directory: {output_dir}",
    ]
    headers = _csv_headers(normalized)
    last_system_error: dict[str, object] | None = None
    current_cycle = 0
    reporter_failed = False

    try:
        _write_manifest(manifest, manifest_path)
        with workflow_scpi_logging(
            scpi_log_path,
            echo_to_stderr=request.log_scpi,
        ):
            with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(headers)
                csv_file.flush()
                start_perf = time.perf_counter()

                for index in range(1, request.count + 1):
                    current_cycle = index
                    if _stop_requested(stop_requested):
                        return _finish_result(
                            "cancelled", 130, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=None,
                        )

                    scope.single()
                    trigger_config = _trigger_wait_config(request.trigger_timeout_seconds)
                    trigger = wait_for_current_trigger_completion(
                        scope.scpi,
                        trigger_config,
                        classifier_profile=_trigger_wait_classifier_profile(scope),
                        stop_requested=stop_requested,
                    )
                    if trigger.outcome == "cancelled":
                        return _finish_result(
                            "cancelled", 130, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=None,
                        )
                    if trigger.outcome != "natural":
                        error = _trigger_failure(
                            index,
                            trigger.outcome,
                            trigger.elapsed_ms,
                            trigger.error,
                        )
                        return _finish_result(
                            "error", 1, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=error,
                        )
                    if _stop_requested(stop_requested):
                        return _finish_result(
                            "cancelled", 130, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=None,
                        )

                    timestamp_iso = batch_iso_timestamp()
                    elapsed_seconds = time.perf_counter() - start_perf
                    trigger_elapsed_seconds = trigger.elapsed_ms / 1000.0
                    values: dict[str, str] = {}
                    row_human = [f"Cycle {index}/{request.count}:"]

                    for channel in normalized["channels"]:
                        for item in normalized["items"]:
                            column = f"ch{channel}_{item}"
                            measurement = scope.query_measurement(channel, item)
                            values[column] = _measurement_value(measurement)
                            row_human.append(
                                _measurement_human_line(column, values[column], measurement)
                            )
                            if _stop_requested(stop_requested):
                                return _finish_result(
                                    "cancelled", 130, manifest, manifest_path, csv_path,
                                    scpi_log_path, files, human, idn, last_system_error,
                                    scope, error=None,
                                )

                    for source, reference in normalized["pairs"]:
                        for item in normalized["pair_items"]:
                            column = f"ch{source}_ch{reference}_{item}"
                            measurement = scope.query_pair_measurement(source, reference, item)
                            values[column] = _measurement_value(measurement)
                            row_human.append(
                                _measurement_human_line(column, values[column], measurement)
                            )
                            if _stop_requested(stop_requested):
                                return _finish_result(
                                    "cancelled", 130, manifest, manifest_path, csv_path,
                                    scpi_log_path, files, human, idn, last_system_error,
                                    scope, error=None,
                                )

                    entry = scope.query_system_error()
                    last_system_error = system_error_manifest_dict(entry)
                    if entry.is_error:
                        error = {
                            "type": "instrument_error",
                            "cycle_index": index,
                            "message": entry.format(),
                        }
                        return _finish_result(
                            "instrument_error", 1, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=error,
                        )

                    writer.writerow(
                        [
                            index,
                            timestamp_iso,
                            f"{elapsed_seconds:.6f}",
                            f"{trigger_elapsed_seconds:.6f}",
                            *[values[header] for header in headers[4:]],
                        ]
                    )
                    csv_file.flush()

                    cycle = {
                        "index": index,
                        "timestamp_iso": timestamp_iso,
                        "elapsed_seconds": elapsed_seconds,
                        "trigger_elapsed_seconds": trigger_elapsed_seconds,
                        "system_error": dict(last_system_error),
                    }
                    candidate = copy.deepcopy(manifest)
                    candidate["completed_count"] = index
                    candidate_cycles = candidate["cycles"]
                    assert isinstance(candidate_cycles, list)
                    candidate_cycles.append(cycle)
                    _write_manifest(candidate, manifest_path)
                    manifest = candidate
                    human.extend(row_human)
                    human.append(f"System error: {entry.format()}")

                    sample = {
                        "index": index,
                        "timestamp_iso": timestamp_iso,
                        "elapsed_seconds": elapsed_seconds,
                        "trigger_elapsed_seconds": trigger_elapsed_seconds,
                        "values": dict(values),
                        "system_error": dict(last_system_error),
                    }
                    try:
                        if sample_reporter is not None:
                            sample_reporter(sample)
                        if progress_reporter is not None:
                            progress_reporter(
                                WorkflowProgress(
                                    completed_count=index,
                                    total_count=request.count,
                                    elapsed_seconds=time.perf_counter() - start_perf,
                                )
                            )
                    except Exception:
                        reporter_failed = True
                        raise

                    if index >= request.count:
                        return _finish_result(
                            "completed", 0, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=None,
                        )
                    if _stop_requested(stop_requested):
                        return _finish_result(
                            "cancelled", 130, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=None,
                        )
                    if request.interval_seconds > 0 and not interruptible_wait(
                        request.interval_seconds,
                        stop_requested=stop_requested,
                    ):
                        return _finish_result(
                            "cancelled", 130, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=None,
                        )
    except KeyboardInterrupt:
        return _finish_result(
            "interrupted", 130, manifest, manifest_path, csv_path,
            scpi_log_path, files, human, idn, last_system_error, scope,
            error={
                "type": "KeyboardInterrupt",
                "cycle_index": current_cycle,
                "message": "KeyboardInterrupt",
            },
            best_effort=True,
        )
    except (OSError, OscilloscopeError) as exc:
        if reporter_failed:
            raise
        error = {
            "type": type(exc).__name__,
            "cycle_index": current_cycle or None,
            "message": str(exc),
        }
        return _finish_result(
            "error", 1, manifest, manifest_path, csv_path, scpi_log_path,
            files, human, idn, last_system_error, scope, error=error,
            best_effort=True,
        )

    raise AssertionError("finite triggered measurement loop exited without a result")


def _validate_request_fields(request: TriggeredMeasureLoopRequest) -> None:
    if isinstance(request.count, bool) or not isinstance(request.count, int):
        raise ParameterValidationError("triggered measurement loop count must be an integer")
    if request.count < 1:
        raise ParameterValidationError("triggered measurement loop count must be at least 1")
    _finite_number(
        request.trigger_timeout_seconds,
        "triggered measurement loop trigger timeout seconds",
        positive=True,
    )
    _finite_number(
        request.interval_seconds,
        "triggered measurement loop interval seconds",
        positive=False,
    )
    if not isinstance(request.items, str):
        raise ParameterValidationError("triggered measurement loop items must be a string")
    if not isinstance(request.pair_items, str):
        raise ParameterValidationError("triggered measurement loop pair_items must be a string")
    if isinstance(request.pairs, (str, bytes)) or not isinstance(request.pairs, Sequence):
        raise ParameterValidationError("triggered measurement loop pairs must be a sequence")
    if any(not isinstance(pair, str) for pair in request.pairs):
        raise ParameterValidationError("triggered measurement loop pairs must contain strings")
    if request.channels is not None:
        if isinstance(request.channels, (str, bytes)) or not isinstance(
            request.channels, Sequence
        ):
            raise ParameterValidationError(
                "triggered measurement loop channels must be a sequence"
            )
        for channel in request.channels:
            if isinstance(channel, bool) or not isinstance(channel, (int, str)):
                raise ParameterValidationError(
                    "triggered measurement loop channels must contain integers or all"
                )
    if not isinstance(request.log_scpi, bool):
        raise ParameterValidationError("triggered measurement loop log_scpi must be a boolean")
    if request.output_dir is not None and not isinstance(request.output_dir, (str, Path)):
        raise ParameterValidationError(
            "triggered measurement loop output_dir must be a path or string"
        )


def _finite_number(value: object, label: str, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParameterValidationError(f"{label} must be a finite number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ParameterValidationError(f"{label} must be a finite number")
    if positive and parsed <= 0:
        raise ParameterValidationError(f"{label} must be greater than zero")
    if not positive and parsed < 0:
        raise ParameterValidationError(f"{label} must be non-negative")
    return parsed


def _normalize_request(
    request: TriggeredMeasureLoopRequest,
    capabilities: ScopeCapabilities,
) -> dict[str, object]:
    _validate_request_fields(request)
    channels = resolve_sweep_channels(request.channels, capabilities)
    items = parse_measurement_item_list(request.items, allow_pair=False)
    pairs = parse_pair_specs(request.pairs, capabilities)
    pair_items = parse_measurement_item_list(request.pair_items, allow_pair=True)
    normalized: dict[str, object] = {
        "channels": channels,
        "items": items,
        "pairs": pairs,
        "pair_items": pair_items,
    }
    _measurement_queries(normalized, capabilities)
    return normalized


def _measurement_queries(
    normalized: Mapping[str, object],
    capabilities: ScopeCapabilities,
) -> list[str]:
    planned: list[str] = []
    for channel in normalized["channels"]:
        for item in normalized["items"]:
            planned.append(measurement_query(item, channel, capabilities=capabilities))
    for source, reference in normalized["pairs"]:
        for item in normalized["pair_items"]:
            planned.append(
                pair_measurement_query(
                    item,
                    source,
                    reference,
                    capabilities=capabilities,
                )
            )
    return planned


def _selection_result(normalized: Mapping[str, object]) -> dict[str, object]:
    return {
        "channels": list(normalized["channels"]),
        "items": list(normalized["items"]),
        "pairs": [f"{source}:{reference}" for source, reference in normalized["pairs"]],
        "pair_items": list(normalized["pair_items"]),
    }


def _csv_headers(normalized: Mapping[str, object]) -> list[str]:
    headers = ["index", "timestamp_iso", "elapsed_seconds", "trigger_elapsed_seconds"]
    for channel in normalized["channels"]:
        for item in normalized["items"]:
            headers.append(f"ch{channel}_{item}")
    for source, reference in normalized["pairs"]:
        for item in normalized["pair_items"]:
            headers.append(f"ch{source}_ch{reference}_{item}")
    return headers


def _measurement_value(measurement: object) -> str:
    if not bool(getattr(measurement, "valid", False)):
        return "NaN"
    value = getattr(measurement, "value", None)
    if value is None:
        return "NaN"
    return f"{float(value):.12g}"


def _measurement_human_line(column: str, value: str, measurement: object) -> str:
    if value == "NaN":
        reason = getattr(measurement, "reason", None) or "invalid measurement"
        return f"  {column}: NaN ({reason})"
    return f"  {column}: {value} {getattr(measurement, 'unit', '')}".rstrip()


def _trigger_wait_config(timeout_seconds: float) -> TriggerWaitConfig:
    timeout_ms = max(1, math.ceil(float(timeout_seconds) * 1000.0))
    return TriggerWaitConfig(timeout_ms=timeout_ms, poll_interval_ms=min(100, timeout_ms))


def _trigger_failure(
    cycle_index: int,
    outcome: str,
    elapsed_ms: float,
    detail: str | None,
) -> dict[str, object]:
    if outcome == "timeout":
        message = f"trigger wait timed out in cycle {cycle_index}"
    else:
        message = detail or f"trigger wait ended with outcome {outcome} in cycle {cycle_index}"
    return {
        "type": "trigger_timeout" if outcome == "timeout" else "trigger_wait_error",
        "cycle_index": cycle_index,
        "outcome": outcome,
        "elapsed_seconds": elapsed_ms / 1000.0,
        "message": message,
    }


def _workflow_paths(output_dir: Path) -> tuple[Path, Path, Path]:
    return (
        output_dir / "measurements.csv",
        output_dir / "manifest.json",
        output_dir / "scpi.log",
    )


def _write_manifest(manifest: Mapping[str, object], path: Path) -> None:
    try:
        write_batch_manifest(manifest, path)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise OscilloscopeError(
            f"could not write triggered measurement manifest {path}: {reason}"
        ) from exc


def _finish_result(
    status: str,
    exit_code: int,
    manifest: dict[str, object],
    manifest_path: Path,
    csv_path: Path,
    scpi_log_path: Path,
    files: list[dict[str, str]],
    human: list[str],
    idn: object,
    system_error: dict[str, object] | None,
    scope: Oscilloscope,
    *,
    error: dict[str, object] | None,
    best_effort: bool = False,
) -> OperationResult:
    manifest["status"] = status
    manifest["end_time"] = batch_iso_timestamp()
    manifest["error"] = error
    if best_effort:
        try:
            _write_manifest(manifest, manifest_path)
        except OscilloscopeError:
            pass
    else:
        _write_manifest(manifest, manifest_path)
    human.extend(
        [
            f"Triggered measurement loop status: {status}",
            f"CSV: {csv_path}",
            f"Manifest: {manifest_path}",
            f"SCPI log: {scpi_log_path}",
        ]
    )
    result = {
        "status": status,
        "channels": list(manifest["channels"]),
        "items": list(manifest["items"]),
        "pairs": list(manifest["pairs"]),
        "pair_items": list(manifest["pair_items"]),
        "requested_count": manifest["requested_count"],
        "completed_count": manifest["completed_count"],
        "trigger_timeout_seconds": manifest["trigger_timeout_seconds"],
        "interval_seconds": manifest["interval_seconds"],
        "cycles": list(manifest["cycles"]),
        "output_dir": str(manifest_path.parent),
        "csv_path": str(csv_path),
        "manifest_path": str(manifest_path),
        "scpi_log_path": str(scpi_log_path),
        "error": error,
    }
    return OperationResult(
        exit_code,
        result,
        files,
        system_error,
        human,
        idn=idn,
        backend=getattr(scope.backend, "backend", None),
        timeout_ms=getattr(scope.backend, "timeout", None),
    )


def _pre_start_cancelled_result(
    request: TriggeredMeasureLoopRequest,
) -> OperationResult:
    result = {
        "status": "cancelled",
        "channels": [],
        "items": parse_measurement_item_list(request.items, allow_pair=False),
        "pairs": list(request.pairs),
        "pair_items": parse_measurement_item_list(request.pair_items, allow_pair=True),
        "requested_count": request.count,
        "completed_count": 0,
        "trigger_timeout_seconds": float(request.trigger_timeout_seconds),
        "interval_seconds": float(request.interval_seconds),
        "cycles": [],
        "output_dir": None,
        "csv_path": None,
        "manifest_path": None,
        "scpi_log_path": None,
        "error": None,
    }
    return OperationResult(130, result, human_lines=["Triggered measurement loop cancelled."])


def _stop_requested(callback: StopRequested | None) -> bool:
    return callback is not None and callback()
