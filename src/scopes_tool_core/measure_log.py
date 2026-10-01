"""Finite measurement logging operation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .errors import OscilloscopeError
from .measure_logger import (
    MeasureLogManifest,
    log_measurements_workflow,
    measure_log_paths,
    prepare_measure_log_output_dir,
)
from .measurements import measurement_query
from .operation_support import _append_session_header, _scope_backend_json
from .operation_types import (
    MeasureLogRequest,
    OperationResult,
    _OperationError,
)
from .planning import (
    parse_measurement_item_list,
    parse_pair_specs,
    resolve_capture_channels,
)
from .scope import Oscilloscope
from .workflow import (
    ProgressReporter,
    StopRequested,
    WorkflowProgress,
    drain_preexisting_system_errors,
    workflow_scpi_logging,
)


def run_measure_log(
    scope: Oscilloscope,
    resource: str,
    request: MeasureLogRequest,
    *,
    stop_requested: StopRequested | None = None,
    progress_reporter: ProgressReporter | None = None,
    sample_reporter: Callable[[Mapping[str, object]], None] | None = None,
) -> OperationResult:
    """Run a finite measurement logger and return its structured outcome."""

    if request.requested_count is None and request.requested_duration_seconds is None:
        raise OscilloscopeError(
            "measure-log requires --count or --duration-seconds so the run is finite"
        )
    if not isinstance(request.save_results, bool):
        raise OscilloscopeError("measure-log save_results must be a boolean")
    output_dir = (
        prepare_measure_log_output_dir(request.output_dir)
        if request.save_results
        else None
    )
    csv_path, manifest_path, scpi_log_path = (
        measure_log_paths(output_dir)
        if output_dir is not None
        else (None, None, None)
    )
    files = [
        {"kind": kind, "path": str(path)}
        for kind, path in (("csv", csv_path), ("manifest", manifest_path), ("scpi_log", scpi_log_path))
        if path is not None
    ]
    human: list[str] = []
    idn = None
    channels: tuple[int, ...] = ()
    items: tuple[str, ...] = ()
    pairs: tuple[tuple[int, int], ...] = ()
    pair_items: tuple[str, ...] = ()
    reporter_failed = False
    completed_rows = 0
    last_measurement: dict[str, object] | None = None

    def report_progress(progress: WorkflowProgress) -> None:
        nonlocal reporter_failed
        if progress_reporter is None:
            return
        try:
            progress_reporter(progress)
        except Exception:
            reporter_failed = True
            raise

    def report_sample(sample: Mapping[str, object]) -> None:
        nonlocal completed_rows, last_measurement, reporter_failed
        completed_rows = int(sample["index"])
        last_measurement = dict(sample)
        if sample_reporter is None:
            return
        try:
            sample_reporter(sample)
        except Exception:
            reporter_failed = True
            raise

    try:
        with workflow_scpi_logging(scpi_log_path, echo_to_stderr=request.log_scpi):
            idn = scope.query_idn()
            _append_session_header(human, scope, resource)
            human.extend([f"Model: {idn.model}", f"Series: {idn.series or 'unknown'}"])
            if scope.capabilities is None:
                raise OscilloscopeError("Capabilities unavailable for this model")
            channels = resolve_capture_channels(
                request.channels or ("all",),
                scope.capabilities,
            )
            items = parse_measurement_item_list(request.items, allow_pair=False)
            pairs = parse_pair_specs(request.pairs, scope.capabilities)
            pair_items = parse_measurement_item_list(request.pair_items, allow_pair=True)
            for channel in channels:
                for item in items:
                    measurement_query(item, channel, capabilities=scope.capabilities)
            for _entry in drain_preexisting_system_errors(scope):
                human.append(f"Pre-operation stale system error drained: {_entry.format()}")
            workflow = log_measurements_workflow(
                scope=scope,
                resource=resource,
                output_dir=output_dir,
                csv_path=csv_path,
                manifest_path=manifest_path,
                scpi_log_path=scpi_log_path,
                channels=list(channels),
                items=list(items),
                pairs=list(pairs),
                pair_items=list(pair_items),
                interval_seconds=request.interval_seconds,
                requested_count=request.requested_count,
                requested_duration_seconds=request.requested_duration_seconds,
                stop_on_error=request.stop_on_error,
                stop_requested=stop_requested,
                progress_reporter=report_progress if progress_reporter is not None else None,
                sample_reporter=report_sample,
            )
        human.extend(workflow.human_lines)
        if scpi_log_path is not None:
            human.append(f"SCPI log: {scpi_log_path}")
        return OperationResult.from_status(
            workflow.exit_code,
            _measure_log_result_json(
                workflow.manifest,
                csv_path,
                manifest_path,
                scpi_log_path,
            ),
            files,
            workflow.system_error,
            human,
            idn=idn,
            **_scope_backend_json(scope),
        )
    except OscilloscopeError as exc:
        if reporter_failed:
            raise
        result, system_error = _measure_log_failure_result(
            manifest_path=manifest_path,
            csv_path=csv_path,
            scpi_log_path=scpi_log_path,
            channels=channels,
            items=items,
            pairs=pairs,
            pair_items=pair_items,
            request=request,
            error=str(exc),
            completed_rows=completed_rows,
            last_measurement=last_measurement,
        )
        raise _OperationError(
            exc,
            OperationResult.from_status(
                1,
                result,
                files,
                system_error,
                human,
                idn=idn,
                **_scope_backend_json(scope),
            ),
        ) from exc
    except OSError as exc:
        if reporter_failed:
            raise
        error = OscilloscopeError(
            f"could not write SCPI log file {scpi_log_path}: {exc}"
        )
        result, system_error = _measure_log_failure_result(
            manifest_path=manifest_path,
            csv_path=csv_path,
            scpi_log_path=scpi_log_path,
            channels=channels,
            items=items,
            pairs=pairs,
            pair_items=pair_items,
            request=request,
            error=str(error),
            completed_rows=completed_rows,
            last_measurement=last_measurement,
        )
        raise _OperationError(
            error,
            OperationResult.from_status(
                1,
                result,
                files,
                system_error,
                human,
                idn=idn,
                **_scope_backend_json(scope),
            ),
        ) from exc


def _measure_log_result_json(
    manifest: MeasureLogManifest,
    csv_path: Path | None,
    manifest_path: Path | None,
    scpi_log_path: Path | None,
) -> dict[str, object]:
    data = manifest.to_json_dict()
    return {
        "status": data["status"],
        "channels": data["channels"],
        "items": data["items"],
        "pairs": data["pairs"],
        "pair_items": data["pair_items"],
        "interval_seconds": data["interval_seconds"],
        "requested_count": data["requested_count"],
        "requested_duration_seconds": data["requested_duration_seconds"],
        "completed_rows": data["completed_rows"],
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
        "scpi_log_path": str(scpi_log_path) if scpi_log_path is not None else None,
        "csv_path": str(csv_path) if csv_path is not None else None,
        "error": data["error"],
        "last_measurement": data["last_measurement"],
    }


def _measure_log_failure_result(
    *,
    manifest_path: Path | None,
    csv_path: Path | None,
    scpi_log_path: Path | None,
    channels: Sequence[int],
    items: Sequence[str],
    pairs: Sequence[tuple[int, int]],
    pair_items: Sequence[str],
    request: MeasureLogRequest,
    error: str,
    completed_rows: int,
    last_measurement: Mapping[str, object] | None,
) -> tuple[dict[str, object], dict[str, object] | None]:
    data: dict[str, object] = {}
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path is not None else {}
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, json.JSONDecodeError):
        pass
    rows = data.get("rows")
    if not isinstance(rows, list):
        rows = []
    system_error = None
    if rows and isinstance(rows[-1], dict):
        candidate = rows[-1].get("system_error")
        if isinstance(candidate, dict):
            system_error = candidate
    elif last_measurement is not None:
        candidate = last_measurement.get("system_error")
        if isinstance(candidate, dict):
            system_error = candidate
    result = {
        "status": data.get("status", "error"),
        "channels": data.get("channels", list(channels)),
        "items": data.get("items", list(items)),
        "pairs": data.get(
            "pairs",
            [f"{source}:{reference}" for source, reference in pairs],
        ),
        "pair_items": data.get("pair_items", list(pair_items)),
        "interval_seconds": data.get("interval_seconds", request.interval_seconds),
        "requested_count": data.get("requested_count", request.requested_count),
        "requested_duration_seconds": data.get(
            "requested_duration_seconds",
            request.requested_duration_seconds,
        ),
        "completed_rows": data.get("completed_rows", completed_rows),
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
        "scpi_log_path": str(scpi_log_path) if scpi_log_path is not None else None,
        "csv_path": str(csv_path) if csv_path is not None else None,
        "error": data.get("error", error),
        "last_measurement": data.get("last_measurement", last_measurement),
    }
    return result, system_error
