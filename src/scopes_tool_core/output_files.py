"""Shared output-file helpers for CLI and core operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from .errors import OscilloscopeError
from .screenshot import write_screenshot_png
from .waveform import (
    MultiChannelWaveformCapture,
    WaveformCapture,
    write_waveform_csv,
    write_waveform_metadata,
    write_waveform_plot_png,
    write_waveforms_csv,
    write_waveforms_metadata,
)

_CAPTURE_DEFAULT_TIMEZONE = timezone(timedelta(hours=8), name="UTC+8")


@dataclass(frozen=True)
class FileRecord:
    kind: str
    path: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "path": self.path}


def default_capture_csv_path(now: datetime | None = None) -> Path:
    if now is None:
        capture_time = datetime.now(_CAPTURE_DEFAULT_TIMEZONE)
    elif now.tzinfo is None:
        capture_time = now.replace(tzinfo=_CAPTURE_DEFAULT_TIMEZONE)
    else:
        capture_time = now.astimezone(_CAPTURE_DEFAULT_TIMEZONE)

    return Path("data") / capture_time.strftime("%Y-%m-%d-%H-%M-%S.csv")


def capture_output_paths(
    csv_path: str | Path | None,
    meta_path: str | Path | None,
    plot_path: str | Path | None,
) -> tuple[Path, Path, Path | None]:
    resolved_csv = Path(csv_path) if csv_path is not None else default_capture_csv_path()
    resolved_meta = (
        Path(meta_path)
        if meta_path is not None
        else resolved_csv.with_name(f"{resolved_csv.stem}_meta.json")
    )
    resolved_plot = Path(plot_path) if plot_path is not None else None
    return resolved_csv, resolved_meta, resolved_plot


def write_capture_csv_file(
    capture: WaveformCapture | MultiChannelWaveformCapture,
    csv_path: Path,
    *,
    allow_time_axis_tolerance: bool = False,
) -> Path:
    try:
        if isinstance(capture, MultiChannelWaveformCapture):
            return write_waveforms_csv(
                capture,
                csv_path,
                allow_time_axis_tolerance=allow_time_axis_tolerance,
            )
        return write_waveform_csv(capture, csv_path)
    except OSError as exc:
        raise OscilloscopeError(_format_output_file_error("CSV", csv_path, exc)) from exc


def write_capture_metadata_file(
    capture: WaveformCapture | MultiChannelWaveformCapture,
    meta_path: Path,
    *,
    idn,
    resource: str,
    time_axis_tolerance: dict[str, object] | None = None,
) -> Path:
    try:
        if isinstance(capture, MultiChannelWaveformCapture):
            if time_axis_tolerance is None:
                return write_waveforms_metadata(
                    capture,
                    meta_path,
                    idn=idn,
                    resource=resource,
                )
            return write_waveforms_metadata(
                capture,
                meta_path,
                idn=idn,
                resource=resource,
                time_axis_tolerance=time_axis_tolerance,
            )
        return write_waveform_metadata(capture, meta_path, idn=idn, resource=resource)
    except OSError as exc:
        raise OscilloscopeError(
            _format_output_file_error("metadata JSON", meta_path, exc)
        ) from exc


def write_capture_plot_file(
    capture: WaveformCapture | MultiChannelWaveformCapture,
    plot_path: Path,
) -> Path:
    try:
        return write_waveform_plot_png(capture, plot_path)
    except OSError as exc:
        raise OscilloscopeError(
            _format_plain_output_file_error("waveform plot PNG", plot_path, exc)
        ) from exc


def write_screenshot_png_file(capture, output_path: Path) -> Path:
    try:
        return write_screenshot_png(capture, output_path)
    except OSError as exc:
        raise OscilloscopeError(
            _format_output_file_error("screenshot PNG", output_path, exc)
        ) from exc


def write_json_file(
    payload: dict[str, object],
    path: Path,
    *,
    file_kind: str,
) -> Path:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        return path
    except OSError as exc:
        raise OscilloscopeError(_format_plain_output_file_error(file_kind, path, exc)) from exc


def write_json_file_best_effort(payload: dict[str, object], path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError:
        pass


def write_serial_lister_csv(payload: bytes, path: Path) -> Path:
    """Write an instrument Lister CSV payload without parsing or rewriting it."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path
    except OSError as exc:
        raise OscilloscopeError(
            _format_plain_output_file_error("Serial Lister CSV", path, exc)
        ) from exc


def _format_output_file_error(file_kind: str, path: Path, exc: OSError) -> str:
    reason = exc.strerror or str(exc)
    if file_kind.startswith("screenshot"):
        message = f"could not write {file_kind} file {path}: {reason}"
    else:
        message = f"could not write waveform {file_kind} file {path}: {reason}"
    if isinstance(exc, PermissionError):
        if file_kind.startswith("screenshot"):
            message += (
                ". The file may be open in another program, "
                "or the folder may not be writable."
            )
        else:
            message += (
                ". The file may be open in another program, such as Excel, "
                "or the folder may not be writable."
            )
    return message


def _format_plain_output_file_error(file_kind: str, path: Path, exc: OSError) -> str:
    reason = exc.strerror or str(exc)
    message = f"could not write {file_kind} file {path}: {reason}"
    if isinstance(exc, PermissionError):
        message += ". The file may be open in another program, or the folder may not be writable."
    return message
