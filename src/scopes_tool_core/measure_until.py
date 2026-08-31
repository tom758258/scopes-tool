"""Finite measurement-until-condition workflow."""

from __future__ import annotations

import copy
import csv
from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Callable, Mapping

from .batch import (
    batch_iso_timestamp,
    idn_manifest_dict,
    prepare_batch_output_dir,
    relative_manifest_path,
    system_error_manifest_dict,
    write_batch_manifest,
)
from .capabilities import ScopeCapabilities
from .channel import validate_analog_channel
from .errors import OscilloscopeError, ParameterValidationError
from .measurements import measurement_query, validate_statistics_items
from .operations import OperationResult
from .planning import OperationPlan
from .scope import Oscilloscope
from .workflow import (
    ProgressReporter,
    StopRequested,
    WorkflowProgress,
    drain_preexisting_system_errors,
    interruptible_wait,
    workflow_scpi_logging,
)


MEASURE_UNTIL_SCHEMA_VERSION = 1
MEASURE_UNTIL_DEFAULT_BASE_DIR = Path("data") / "measure_until"
MEASURE_UNTIL_OPERATORS = ("gt", "gte", "lt", "lte")

SampleReporter = Callable[[Mapping[str, object]], None]


@dataclass(frozen=True)
class MeasureUntilRequest:
    """Inputs for one finite measurement-until-condition workflow."""

    channel: int
    item: str
    operator: str
    threshold: float
    timeout_seconds: float
    interval_seconds: float = 1.0
    output_dir: str | Path | None = None
    log_scpi: bool = False


def plan_measure_until(
    request: MeasureUntilRequest,
    capabilities: ScopeCapabilities,
) -> OperationPlan:
    """Validate and plan one representative polling iteration."""

    normalized = _normalize_request(request, capabilities)
    output_dir = (
        Path(request.output_dir)
        if request.output_dir is not None
        else MEASURE_UNTIL_DEFAULT_BASE_DIR / "DRY-RUN"
    )
    csv_path, manifest_path, scpi_log_path = _workflow_paths(output_dir)
    files = (
        {"kind": "csv", "path": str(csv_path)},
        {"kind": "manifest", "path": str(manifest_path)},
        {"kind": "scpi_log", "path": str(scpi_log_path)},
    )
    planned = (
        measurement_query(
            normalized["item"],
            normalized["channel"],
            capabilities=capabilities,
        ),
        ":SYSTem:ERRor?",
    )
    result = {
        "status": "planned",
        "channel": normalized["channel"],
        "item": normalized["item"],
        "operator": request.operator,
        "threshold": float(request.threshold),
        "timeout_seconds": float(request.timeout_seconds),
        "interval_seconds": float(request.interval_seconds),
        "completed_count": 0,
        "matched": False,
        "matched_sample": None,
        "termination_reason": None,
        "output_dir": str(output_dir),
        "csv_path": str(csv_path),
        "manifest_path": str(manifest_path),
        "scpi_log_path": str(scpi_log_path),
        "error": None,
    }
    return OperationPlan(planned, files, result)


def run_measure_until(
    scope: Oscilloscope,
    resource: str,
    request: MeasureUntilRequest,
    *,
    stop_requested: StopRequested | None = None,
    progress_reporter: ProgressReporter | None = None,
    sample_reporter: SampleReporter | None = None,
) -> OperationResult:
    """Query one measurement until its condition matches or timeout expires."""

    _validate_request_fields(request)
    if _stop_requested(stop_requested):
        return _pre_start_cancelled_result(request)

    idn = scope.query_idn()
    if scope.capabilities is None:
        raise OscilloscopeError("Capabilities unavailable for this model")
    normalized = _normalize_request(request, scope.capabilities)
    channel = int(normalized["channel"])
    item = str(normalized["item"])

    output_dir = prepare_batch_output_dir(
        request.output_dir,
        base_dir=MEASURE_UNTIL_DEFAULT_BASE_DIR,
    )
    csv_path, manifest_path, scpi_log_path = _workflow_paths(output_dir)
    files = [
        {"kind": "csv", "path": str(csv_path)},
        {"kind": "manifest", "path": str(manifest_path)},
        {"kind": "scpi_log", "path": str(scpi_log_path)},
    ]
    manifest: dict[str, object] = {
        "schema_version": MEASURE_UNTIL_SCHEMA_VERSION,
        "start_time": batch_iso_timestamp(),
        "end_time": None,
        "status": "running",
        "resource": resource,
        "backend": getattr(scope.backend, "backend", None),
        "timeout_ms": getattr(scope.backend, "timeout", None),
        "idn": idn_manifest_dict(idn),
        "channel": channel,
        "item": item,
        "operator": request.operator,
        "threshold": float(request.threshold),
        "timeout_seconds": float(request.timeout_seconds),
        "interval_seconds": float(request.interval_seconds),
        "completed_count": 0,
        "matched": False,
        "matched_sample": None,
        "termination_reason": None,
        "files": _relative_files(files, output_dir),
        "error": None,
    }
    human = [
        f"Measure until: CH{channel} {item} {request.operator} "
        f"{float(request.threshold):.12g}",
        f"Timeout seconds: {float(request.timeout_seconds):.12g}",
        f"Interval seconds: {float(request.interval_seconds):.12g}",
        f"Output directory: {output_dir}",
    ]
    last_system_error: dict[str, object] | None = None
    current_sample = 0
    reporter_failed = False

    try:
        _write_manifest(manifest, manifest_path)
        with workflow_scpi_logging(
            scpi_log_path,
            echo_to_stderr=request.log_scpi,
        ):
            for _entry in drain_preexisting_system_errors(scope):
                human.append(f"Pre-operation stale system error drained: {_entry.format()}")
            with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(
                    ["index", "timestamp_iso", "elapsed_seconds", "value", "matched"]
                )
                csv_file.flush()
                start_perf = time.perf_counter()

                while True:
                    if _stop_requested(stop_requested):
                        return _finish_result(
                            "cancelled", 130, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=None, termination_reason=None,
                        )

                    elapsed_before = time.perf_counter() - start_perf
                    if elapsed_before >= float(request.timeout_seconds):
                        error = _condition_timeout_error(request.timeout_seconds)
                        return _finish_result(
                            "error", 1, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=error,
                            termination_reason="condition_timeout",
                        )

                    current_sample = int(manifest["completed_count"]) + 1
                    measurement = scope.query_measurement(channel, item)
                    entry = scope.query_system_error()
                    last_system_error = system_error_manifest_dict(entry)
                    if entry.is_error:
                        error = {
                            "type": "instrument_error",
                            "sample_index": current_sample,
                            "message": entry.format(),
                        }
                        return _finish_result(
                            "instrument_error", 1, manifest, manifest_path,
                            csv_path, scpi_log_path, files, human, idn,
                            last_system_error, scope, error=error,
                            termination_reason=None,
                        )

                    timestamp_iso = batch_iso_timestamp()
                    elapsed_seconds = time.perf_counter() - start_perf
                    value = _measurement_value(measurement)
                    matched = value is not None and _condition_matches(
                        value,
                        request.operator,
                        float(request.threshold),
                    )
                    value_text = "NaN" if value is None else f"{value:.12g}"
                    writer.writerow(
                        [
                            current_sample,
                            timestamp_iso,
                            f"{elapsed_seconds:.6f}",
                            value_text,
                            "true" if matched else "false",
                        ]
                    )
                    csv_file.flush()

                    matched_sample = (
                        {
                            "index": current_sample,
                            "value": value,
                            "elapsed_seconds": elapsed_seconds,
                        }
                        if matched
                        else None
                    )
                    candidate = copy.deepcopy(manifest)
                    candidate["completed_count"] = current_sample
                    candidate["matched"] = matched
                    candidate["matched_sample"] = matched_sample
                    _write_manifest(candidate, manifest_path)
                    manifest = candidate

                    sample = {
                        "index": current_sample,
                        "timestamp_iso": timestamp_iso,
                        "elapsed_seconds": elapsed_seconds,
                        "value": value_text,
                        "matched": matched,
                        "system_error": dict(last_system_error),
                    }
                    try:
                        if sample_reporter is not None:
                            sample_reporter(sample)
                        if progress_reporter is not None:
                            progress_reporter(
                                WorkflowProgress(
                                    completed_count=current_sample,
                                    total_count=None,
                                    elapsed_seconds=time.perf_counter() - start_perf,
                                )
                            )
                    except Exception:
                        reporter_failed = True
                        raise

                    human.append(
                        f"Sample {current_sample}: {value_text}, "
                        f"matched={'true' if matched else 'false'}"
                    )
                    human.append(f"System error: {entry.format()}")

                    if matched:
                        return _finish_result(
                            "completed", 0, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=None,
                            termination_reason="condition_met",
                        )
                    if _stop_requested(stop_requested):
                        return _finish_result(
                            "cancelled", 130, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=None, termination_reason=None,
                        )

                    remaining = float(request.timeout_seconds) - (
                        time.perf_counter() - start_perf
                    )
                    wait_seconds = min(float(request.interval_seconds), max(0.0, remaining))
                    if wait_seconds > 0 and not interruptible_wait(
                        wait_seconds,
                        stop_requested=stop_requested,
                    ):
                        return _finish_result(
                            "cancelled", 130, manifest, manifest_path, csv_path,
                            scpi_log_path, files, human, idn, last_system_error,
                            scope, error=None, termination_reason=None,
                        )
    except KeyboardInterrupt:
        return _finish_result(
            "interrupted", 130, manifest, manifest_path, csv_path,
            scpi_log_path, files, human, idn, last_system_error, scope,
            error="KeyboardInterrupt", termination_reason=None,
            best_effort=True,
        )
    except (OSError, OscilloscopeError) as exc:
        if reporter_failed:
            raise
        error = {
            "type": type(exc).__name__,
            "sample_index": current_sample or None,
            "message": str(exc),
        }
        return _finish_result(
            "error", 1, manifest, manifest_path, csv_path, scpi_log_path,
            files, human, idn, last_system_error, scope, error=error,
            termination_reason=None, best_effort=True,
        )


def _validate_request_fields(request: MeasureUntilRequest) -> None:
    if isinstance(request.channel, bool) or not isinstance(request.channel, int):
        raise ParameterValidationError("measure until channel must be an integer")
    if request.channel < 1:
        raise ParameterValidationError("measure until channel must be at least 1")
    _normalize_item(request.item)
    if not isinstance(request.operator, str) or request.operator not in MEASURE_UNTIL_OPERATORS:
        raise ParameterValidationError(
            "measure until operator must be gt, gte, lt, or lte"
        )
    _finite_number(request.threshold, "measure until threshold", positive=False)
    _finite_number(
        request.timeout_seconds,
        "measure until timeout seconds",
        positive=True,
    )
    _finite_number(
        request.interval_seconds,
        "measure until interval seconds",
        positive=False,
        nonnegative=True,
    )
    if not isinstance(request.log_scpi, bool):
        raise ParameterValidationError("measure until log_scpi must be a boolean")
    if request.output_dir is not None and not isinstance(request.output_dir, (str, Path)):
        raise ParameterValidationError("measure until output_dir must be a path or string")


def _normalize_request(
    request: MeasureUntilRequest,
    capabilities: ScopeCapabilities,
) -> dict[str, object]:
    _validate_request_fields(request)
    channel = validate_analog_channel(request.channel, capabilities)
    item = _normalize_item(request.item)
    measurement_query(item, channel, capabilities=capabilities)
    return {"channel": channel, "item": item}


def _normalize_item(value: object) -> str:
    if not isinstance(value, str):
        raise ParameterValidationError("measure until item must be a string")
    try:
        return validate_statistics_items((value,))[0]
    except ParameterValidationError as exc:
        raise ParameterValidationError(
            "measure until item must be a non-parameterized single-channel measurement"
        ) from exc


def _finite_number(
    value: object,
    label: str,
    *,
    positive: bool,
    nonnegative: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParameterValidationError(f"{label} must be a finite number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ParameterValidationError(f"{label} must be a finite number")
    if positive and parsed <= 0:
        raise ParameterValidationError(f"{label} must be greater than zero")
    if nonnegative and parsed < 0:
        raise ParameterValidationError(f"{label} must be non-negative")
    return parsed


def _measurement_value(measurement: object) -> float | None:
    if not bool(getattr(measurement, "valid", False)):
        return None
    value = getattr(measurement, "value", None)
    if value is None:
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _condition_matches(value: float, operator: str, threshold: float) -> bool:
    if operator == "gt":
        return value > threshold
    if operator == "gte":
        return value >= threshold
    if operator == "lt":
        return value < threshold
    if operator == "lte":
        return value <= threshold
    raise AssertionError(f"unsupported measure until operator: {operator}")


def _condition_timeout_error(timeout_seconds: float) -> dict[str, object]:
    return {
        "type": "condition_timeout",
        "message": (
            "measurement condition was not met within "
            f"{float(timeout_seconds):.12g} seconds"
        ),
    }


def _workflow_paths(output_dir: Path) -> tuple[Path, Path, Path]:
    return (
        output_dir / "measurements.csv",
        output_dir / "manifest.json",
        output_dir / "scpi.log",
    )


def _relative_files(
    files: list[dict[str, str]],
    output_dir: Path,
) -> list[dict[str, str]]:
    return [
        {
            "kind": item["kind"],
            "path": relative_manifest_path(item["path"], output_dir),
        }
        for item in files
    ]


def _write_manifest(manifest: Mapping[str, object], path: Path) -> None:
    try:
        write_batch_manifest(manifest, path)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise OscilloscopeError(
            f"could not write measure until manifest {path}: {reason}"
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
    error: dict[str, object] | str | None,
    termination_reason: str | None,
    best_effort: bool = False,
) -> OperationResult:
    manifest["status"] = status
    manifest["end_time"] = batch_iso_timestamp()
    manifest["termination_reason"] = termination_reason
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
            f"Measure until status: {status}",
            f"CSV: {csv_path}",
            f"Manifest: {manifest_path}",
            f"SCPI log: {scpi_log_path}",
        ]
    )
    result = {
        "status": status,
        "channel": manifest["channel"],
        "item": manifest["item"],
        "operator": manifest["operator"],
        "threshold": manifest["threshold"],
        "timeout_seconds": manifest["timeout_seconds"],
        "interval_seconds": manifest["interval_seconds"],
        "completed_count": manifest["completed_count"],
        "matched": manifest["matched"],
        "matched_sample": manifest["matched_sample"],
        "termination_reason": termination_reason,
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


def _pre_start_cancelled_result(request: MeasureUntilRequest) -> OperationResult:
    result = {
        "status": "cancelled",
        "channel": request.channel,
        "item": _normalize_item(request.item),
        "operator": request.operator,
        "threshold": float(request.threshold),
        "timeout_seconds": float(request.timeout_seconds),
        "interval_seconds": float(request.interval_seconds),
        "completed_count": 0,
        "matched": False,
        "matched_sample": None,
        "termination_reason": None,
        "output_dir": None,
        "csv_path": None,
        "manifest_path": None,
        "scpi_log_path": None,
        "error": None,
    }
    return OperationResult(130, result, human_lines=["Measure until cancelled."])


def _stop_requested(callback: StopRequested | None) -> bool:
    return callback is not None and callback()
