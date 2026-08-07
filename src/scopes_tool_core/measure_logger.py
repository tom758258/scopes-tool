"""Finite batch measurement logging helpers."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import time
from typing import Callable, Mapping

from .batch import idn_manifest_dict, relative_manifest_path, system_error_manifest_dict
from .errors import OscilloscopeError
from .scope import Oscilloscope
from .workflow import (
    ProgressReporter,
    StopRequested,
    WorkflowProgress,
    interruptible_wait,
)

LOGGER_SCHEMA_VERSION = 1
LOGGER_DEFAULT_TIMEZONE = timezone(timedelta(hours=8), name="UTC+8")
LOGGER_DEFAULT_BASE_DIR = Path("data") / "measure_logs"
LOGGER = logging.getLogger(__name__)


@dataclass
class MeasureLogManifest:
    """Serializable manifest for one finite measurement log run."""

    start_time: str
    status: str
    resource: str
    backend: str | None
    timeout_ms: int | None
    idn: dict[str, object] | None
    channels: list[int]
    items: list[str]
    pairs: list[str]
    pair_items: list[str]
    interval_seconds: float
    requested_count: int | None
    requested_duration_seconds: float | None
    completed_rows: int = 0
    end_time: str | None = None
    error: str | None = None
    rows: list[dict[str, object]] = field(default_factory=list)
    schema_version: int = LOGGER_SCHEMA_VERSION
    files: list[dict[str, str]] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping with stable key order."""
        data = asdict(self)
        return {
            "schema_version": data["schema_version"],
            "start_time": data["start_time"],
            "end_time": data["end_time"],
            "status": data["status"],
            "resource": data["resource"],
            "backend": data["backend"],
            "timeout_ms": data["timeout_ms"],
            "idn": data["idn"],
            "channels": data["channels"],
            "items": data["items"],
            "pairs": data["pairs"],
            "pair_items": data["pair_items"],
            "interval_seconds": data["interval_seconds"],
            "requested_count": data["requested_count"],
            "requested_duration_seconds": data["requested_duration_seconds"],
            "completed_rows": data["completed_rows"],
            "error": data["error"],
            "rows": data["rows"],
            "files": data["files"],
        }


@dataclass(frozen=True)
class MeasureLogWorkflowResult:
    """Structured outcome from the finite measurement logging loop."""

    exit_code: int
    manifest: MeasureLogManifest
    human_lines: list[str]
    system_error: dict[str, object] | None = None


def logger_timestamp(now: datetime | None = None) -> datetime:
    """Return a timezone-aware UTC+8 timestamp for logger paths and metadata."""
    if now is None:
        return datetime.now(LOGGER_DEFAULT_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=LOGGER_DEFAULT_TIMEZONE)
    return now.astimezone(LOGGER_DEFAULT_TIMEZONE)


def logger_timestamp_text(now: datetime | None = None) -> str:
    """Return the timestamp text used in default output directory names."""
    return logger_timestamp(now).strftime("%Y-%m-%d-%H-%M-%S")


def logger_iso_timestamp(now: datetime | None = None) -> str:
    """Return an ISO timestamp using the default UTC+8 timezone."""
    return logger_timestamp(now).isoformat(timespec="seconds")


def default_measure_log_output_dir(
    now: datetime | None = None,
    *,
    base_dir: str | Path = LOGGER_DEFAULT_BASE_DIR,
) -> Path:
    """Return the next non-colliding default logger output directory path."""
    base_path = Path(base_dir)
    stem = logger_timestamp_text(now)
    candidate = base_path / stem
    suffix = 2
    while candidate.exists():
        candidate = base_path / f"{stem}-{suffix}"
        suffix += 1
    return candidate


def prepare_measure_log_output_dir(
    output_dir: str | Path | None,
    *,
    now: datetime | None = None,
    base_dir: str | Path = LOGGER_DEFAULT_BASE_DIR,
) -> Path:
    """Create and return a safe output directory for a measurement log run."""

    if output_dir is None:
        path = default_measure_log_output_dir(now, base_dir=base_dir)
        try:
            path.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise OscilloscopeError(
                _format_directory_error("could not create output directory", path, exc)
            ) from exc
        return path

    path = Path(output_dir)
    if path.exists():
        if not path.is_dir():
            raise OscilloscopeError(f"output directory path is not a directory: {path}")
        try:
            has_existing_files = any(path.iterdir())
        except OSError as exc:
            raise OscilloscopeError(
                _format_directory_error("could not inspect output directory", path, exc)
            ) from exc
        if has_existing_files and {item.name for item in path.iterdir()} != {"request.json"}:
            raise OscilloscopeError(f"output directory must be empty: {path}")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OscilloscopeError(
            _format_directory_error("could not create output directory", path, exc)
        ) from exc
    return path


def _format_directory_error(action: str, path: Path, exc: OSError) -> str:
    reason = exc.strerror or str(exc)
    return f"{action} {path}: {reason}"


def measure_log_paths(output_dir: str | Path) -> tuple[Path, Path, Path]:
    """Return CSV, manifest JSON, and SCPI log paths."""
    output_path = Path(output_dir)
    return (
        output_path / "measurements.csv",
        output_path / "manifest.json",
        output_path / "scpi.log",
    )


def write_measure_log_manifest(
    manifest: MeasureLogManifest | Mapping[str, object],
    path: str | Path,
) -> Path:
    """Write the manifest JSON file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        manifest.to_json_dict()
        if isinstance(manifest, MeasureLogManifest)
        else dict(manifest)
    )
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return output_path


def log_measurements_workflow(
    scope: Oscilloscope,
    resource: str,
    output_dir: Path,
    csv_path: Path,
    manifest_path: Path,
    scpi_log_path: Path,
    channels: list[int],
    items: list[str],
    pairs: list[tuple[int, int]],
    pair_items: list[str],
    interval_seconds: float,
    requested_count: int | None,
    requested_duration_seconds: float | None,
    stop_on_error: bool,
    *,
    stop_requested: StopRequested | None = None,
    progress_reporter: ProgressReporter | None = None,
    sample_reporter: Callable[[Mapping[str, object]], None] | None = None,
) -> MeasureLogWorkflowResult:
    """Run a finite measurement logging loop and write CSV plus manifest files."""

    human: list[str] = []
    last_system_error: dict[str, object] | None = None
    reporter_failed = False
    manifest = MeasureLogManifest(
        start_time=logger_iso_timestamp(),
        status="running",
        resource=resource,
        backend=getattr(scope.backend, "backend", None),
        timeout_ms=getattr(scope.backend, "timeout", None),
        idn=idn_manifest_dict(scope.idn) if scope.idn else None,
        channels=list(channels),
        items=list(items),
        pairs=[f"{src}:{ref}" for src, ref in pairs],
        pair_items=list(pair_items),
        interval_seconds=interval_seconds,
        requested_count=requested_count,
        requested_duration_seconds=requested_duration_seconds,
        files=[
            {"kind": "csv", "path": relative_manifest_path(csv_path, output_dir)},
            {"kind": "manifest", "path": relative_manifest_path(manifest_path, output_dir)},
            {"kind": "scpi_log", "path": relative_manifest_path(scpi_log_path, output_dir)},
        ],
    )

    _touch_measure_log_file(scpi_log_path, "SCPI log")
    write_measure_log_manifest(manifest, manifest_path)

    headers = ["timestamp_iso", "elapsed_seconds"]
    for ch in channels:
        for item in items:
            headers.append(f"ch{ch}_{item}")
    for src, ref in pairs:
        for item in pair_items:
            headers.append(f"ch{src}_ch{ref}_{item}")

    human.append(
        f"Planned measurement logger: {len(channels)} channels, "
        f"{len(pairs)} channel-pairs"
    )
    human.append(f"Interval seconds: {interval_seconds}")
    if requested_count is not None:
        human.append(f"Requested count: {requested_count}")
    if requested_duration_seconds is not None:
        human.append(f"Requested duration: {requested_duration_seconds}s")
    human.append(f"CSV path: {csv_path}")
    human.append(f"Manifest path: {manifest_path}")

    try:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)
            csv_file.flush()

            start_perf = time.perf_counter()
            row_index = 0

            while True:
                if requested_count is not None and row_index >= requested_count:
                    break
                elapsed = time.perf_counter() - start_perf
                if requested_duration_seconds is not None and elapsed >= requested_duration_seconds:
                    break
                if stop_requested is not None and stop_requested():
                    return _cancel_measurement_log(
                        manifest,
                        manifest_path,
                        human,
                        last_system_error,
                    )

                row_index += 1
                loop_start = time.perf_counter()
                iso_now = logger_iso_timestamp()
                elapsed_now = time.perf_counter() - start_perf

                row_human = [
                    f"Row {row_index}"
                    + (f"/{requested_count}" if requested_count else "")
                    + f" (elapsed {elapsed_now:.2f}s):"
                ]

                row_data: dict[str, str] = {
                    "timestamp_iso": iso_now,
                    "elapsed_seconds": f"{elapsed_now:.4f}",
                }

                # Single channel queries
                for ch in channels:
                    for item in items:
                        col = f"ch{ch}_{item}"
                        val = "NaN"
                        try:
                            res = scope.query_measurement(ch, item)
                            if res.valid and res.value is not None:
                                val = f"{res.value:.12g}"
                                row_human.append(f"  {col}: {val} {res.unit}")
                            else:
                                row_human.append(
                                    f"  {col}: NaN ({res.reason or 'invalid sentinel'})"
                                )
                        except OscilloscopeError as exc:
                            LOGGER.warning("%s: NaN (query failed: %s)", col, exc)
                        row_data[col] = val
                        if stop_requested is not None and stop_requested():
                            return _cancel_measurement_log(
                                manifest,
                                manifest_path,
                                human,
                                last_system_error,
                            )

                for src, ref in pairs:
                    for item in pair_items:
                        col = f"ch{src}_ch{ref}_{item}"
                        val = "NaN"
                        try:
                            res = scope.query_pair_measurement(src, ref, item)
                            if res.valid and res.value is not None:
                                val = f"{res.value:.12g}"
                                row_human.append(f"  {col}: {val} {res.unit}")
                            else:
                                row_human.append(
                                    f"  {col}: NaN ({res.reason or 'invalid sentinel'})"
                                )
                        except OscilloscopeError as exc:
                            LOGGER.warning("%s: NaN (query failed: %s)", col, exc)
                        row_data[col] = val
                        if stop_requested is not None and stop_requested():
                            return _cancel_measurement_log(
                                manifest,
                                manifest_path,
                                human,
                                last_system_error,
                            )

                system_err = scope.query_system_error()

                row_vals = [row_data[h] for h in headers]
                writer.writerow(row_vals)
                csv_file.flush()

                manifest.completed_rows = row_index
                manifest.rows.append(
                    {
                        "index": row_index,
                        "timestamp_iso": iso_now,
                        "elapsed_seconds": elapsed_now,
                        "system_error": system_error_manifest_dict(system_err),
                    }
                )
                last_system_error = system_error_manifest_dict(system_err)
                write_measure_log_manifest(manifest, manifest_path)
                human.extend(row_human)
                human.append(f"System error: {system_err.format()}")

                sample = {
                    "index": row_index,
                    "timestamp_iso": iso_now,
                    "elapsed_seconds": elapsed_now,
                    "values": {header: row_data[header] for header in headers[2:]},
                    "system_error": dict(last_system_error),
                }
                try:
                    if sample_reporter is not None:
                        sample_reporter(sample)
                    if progress_reporter is not None:
                        progress_reporter(
                            WorkflowProgress(
                                completed_count=row_index,
                                total_count=requested_count,
                                elapsed_seconds=time.perf_counter() - start_perf,
                            )
                        )
                except Exception:
                    reporter_failed = True
                    raise

                if stop_on_error and system_err.is_error:
                    LOGGER.error(
                        "stop-on-error triggered by system error: %s",
                        system_err.format(),
                    )
                    manifest.status = "instrument_error"
                    manifest.error = f"SystemError: {system_err.format()}"
                    manifest.end_time = logger_iso_timestamp()
                    write_measure_log_manifest(manifest, manifest_path)
                    return MeasureLogWorkflowResult(
                        1,
                        manifest,
                        human,
                        last_system_error,
                    )

                if requested_count is not None and row_index >= requested_count:
                    break
                elapsed_after = time.perf_counter() - start_perf
                if requested_duration_seconds is not None and elapsed_after >= requested_duration_seconds:
                    break

                if stop_requested is not None and stop_requested():
                    return _cancel_measurement_log(
                        manifest,
                        manifest_path,
                        human,
                        last_system_error,
                    )

                loop_duration = time.perf_counter() - loop_start
                sleep_time = max(0.0, interval_seconds - loop_duration)
                if sleep_time > 0 and not interruptible_wait(
                    sleep_time,
                    stop_requested=stop_requested,
                ):
                    return _cancel_measurement_log(
                        manifest,
                        manifest_path,
                        human,
                        last_system_error,
                    )

            manifest.status = "completed"
            manifest.end_time = logger_iso_timestamp()
            write_measure_log_manifest(manifest, manifest_path)
            human.append("Measurement logging completed successfully.")
            return MeasureLogWorkflowResult(
                0,
                manifest,
                human,
                last_system_error,
            )

    except KeyboardInterrupt:
        manifest.status = "interrupted"
        manifest.error = "KeyboardInterrupt"
        manifest.end_time = logger_iso_timestamp()
        try:
            write_measure_log_manifest(manifest, manifest_path)
        except OSError:
            pass
        LOGGER.warning("measurement logging interrupted")
        return MeasureLogWorkflowResult(
            130,
            manifest,
            human,
            last_system_error,
        )
    except OSError as exc:
        if reporter_failed:
            raise
        manifest.status = "error"
        manifest.error = str(exc)
        manifest.end_time = logger_iso_timestamp()
        try:
            write_measure_log_manifest(manifest, manifest_path)
        except OSError:
            pass
        raise OscilloscopeError(
            _format_measure_log_file_error("measurement log output", csv_path, exc)
        ) from exc
    except OscilloscopeError as exc:
        if reporter_failed:
            raise
        manifest.status = "error"
        manifest.error = str(exc)
        manifest.end_time = logger_iso_timestamp()
        try:
            write_measure_log_manifest(manifest, manifest_path)
        except OSError:
            pass
        raise


def _cancel_measurement_log(
    manifest: MeasureLogManifest,
    manifest_path: Path,
    human: list[str],
    last_system_error: dict[str, object] | None,
) -> MeasureLogWorkflowResult:
    manifest.status = "cancelled"
    manifest.error = None
    manifest.end_time = logger_iso_timestamp()
    write_measure_log_manifest(manifest, manifest_path)
    human.append("Measurement logging cancelled.")
    return MeasureLogWorkflowResult(
        130,
        manifest,
        human,
        last_system_error,
    )


def _touch_measure_log_file(path: Path, file_kind: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
    except OSError as exc:
        raise OscilloscopeError(
            _format_measure_log_file_error(file_kind, path, exc)
        ) from exc


def _format_measure_log_file_error(file_kind: str, path: Path, exc: OSError) -> str:
    reason = exc.strerror or str(exc)
    message = f"could not write {file_kind} file {path}: {reason}"
    if isinstance(exc, PermissionError):
        message += ". The file may be open in another program, or the folder may not be writable."
    return message
