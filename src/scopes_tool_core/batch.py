"""Finite waveform batch capture helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Mapping

from .errors import OscilloscopeError
from .idn import IDN
from .status import SystemErrorEntry
from .waveform import MultiChannelWaveformCapture, WaveformCapture

BATCH_SCHEMA_VERSION = 1
BATCH_DEFAULT_TIMEZONE = timezone(timedelta(hours=8), name="UTC+8")
BATCH_DEFAULT_BASE_DIR = Path("data") / "captures"


@dataclass
class BatchManifest:
    """Serializable manifest for one finite batch capture run."""

    start_time: str
    status: str
    resource: str
    backend: str | None
    timeout_ms: int | None
    idn: dict[str, object] | None
    channels: list[int]
    points: int
    format: str
    requested_count: int
    interval_seconds: float
    captures: list[dict[str, object]] = field(default_factory=list)
    end_time: str | None = None
    error: str | None = None
    schema_version: int = BATCH_SCHEMA_VERSION

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
            "points": data["points"],
            "format": data["format"],
            "requested_count": data["requested_count"],
            "interval_seconds": data["interval_seconds"],
            "captures": data["captures"],
            "error": data["error"],
        }


def batch_timestamp(now: datetime | None = None) -> datetime:
    """Return a timezone-aware UTC+8 timestamp for batch paths and metadata."""

    if now is None:
        return datetime.now(BATCH_DEFAULT_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=BATCH_DEFAULT_TIMEZONE)
    return now.astimezone(BATCH_DEFAULT_TIMEZONE)


def batch_timestamp_text(now: datetime | None = None) -> str:
    """Return the timestamp text used in default batch directory names."""

    return batch_timestamp(now).strftime("%Y-%m-%d-%H-%M-%S")


def batch_iso_timestamp(now: datetime | None = None) -> str:
    """Return an ISO timestamp using the batch default UTC+8 timezone."""

    return batch_timestamp(now).isoformat(timespec="seconds")


def default_batch_output_dir(
    now: datetime | None = None,
    *,
    base_dir: str | Path = BATCH_DEFAULT_BASE_DIR,
) -> Path:
    """Return the next non-colliding default batch output directory path."""

    base_path = Path(base_dir)
    stem = batch_timestamp_text(now)
    candidate = base_path / stem
    suffix = 2
    while candidate.exists():
        candidate = base_path / f"{stem}-{suffix}"
        suffix += 1
    return candidate


def prepare_batch_output_dir(
    output_dir: str | Path | None,
    *,
    now: datetime | None = None,
    base_dir: str | Path = BATCH_DEFAULT_BASE_DIR,
) -> Path:
    """Create and return a safe output directory for a batch run."""

    if output_dir is None:
        path = default_batch_output_dir(now, base_dir=base_dir)
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


def batch_capture_stem(index: int, requested_count: int) -> str:
    """Return the stable per-capture file stem for one batch index."""

    if index < 1:
        raise ValueError("batch capture index must be at least 1")
    if requested_count < 1:
        raise ValueError("requested count must be at least 1")
    width = max(4, len(str(requested_count)))
    return f"waveform_{index:0{width}d}"


def _format_directory_error(action: str, path: Path, exc: OSError) -> str:
    reason = exc.strerror or str(exc)
    return f"{action} {path}: {reason}"


def batch_capture_paths(
    output_dir: str | Path,
    index: int,
    requested_count: int,
) -> tuple[Path, Path]:
    """Return the CSV and metadata paths for one batch index."""

    output_path = Path(output_dir)
    stem = batch_capture_stem(index, requested_count)
    return output_path / f"{stem}.csv", output_path / f"{stem}_meta.json"


def relative_manifest_path(path: str | Path, base_dir: str | Path) -> str:
    """Return a portable path relative to the manifest directory when possible."""

    path_obj = Path(path)
    base_path = Path(base_dir)
    try:
        return path_obj.relative_to(base_path).as_posix()
    except ValueError:
        try:
            return path_obj.resolve().relative_to(base_path.resolve()).as_posix()
        except ValueError:
            return path_obj.as_posix()


def idn_manifest_dict(idn: IDN) -> dict[str, object]:
    """Return parsed IDN fields for manifest JSON."""

    return {
        "raw": idn.raw,
        "vendor": idn.vendor,
        "model": idn.model,
        "series": idn.series,
        "serial": idn.serial,
        "firmware": idn.firmware,
    }


def system_error_manifest_dict(entry: SystemErrorEntry) -> dict[str, object]:
    """Return one system error entry for manifest JSON."""

    return {
        "code": entry.code,
        "message": entry.message,
        "raw": entry.raw,
        "is_error": entry.is_error,
    }


def capture_actual_points(
    capture: WaveformCapture | MultiChannelWaveformCapture,
) -> int | dict[str, int]:
    """Return actual point counts in a compact manifest-friendly shape."""

    if isinstance(capture, MultiChannelWaveformCapture):
        return {f"CH{item.channel}": len(item.raw_samples) for item in capture.captures}
    return len(capture.raw_samples)


def write_batch_manifest(
    manifest: BatchManifest | Mapping[str, object],
    path: str | Path,
) -> Path:
    """Write a batch manifest JSON file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest.to_json_dict() if isinstance(manifest, BatchManifest) else dict(manifest)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return output_path
