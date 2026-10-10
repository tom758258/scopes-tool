"""Shared request, result, and error types for Core operations."""

from __future__ import annotations

from .status import status_fields

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .errors import OscilloscopeError
from .trigger import TriggerWaitConfig


@dataclass(frozen=True)
class OperationResult:
    exit_code: int
    result: dict[str, object]
    files: list[dict[str, str]] = field(default_factory=list)
    system_error: dict[str, object] | None = None
    human_lines: list[str] = field(default_factory=list)
    idn: object | None = None
    backend: str | None = None
    timeout_ms: int | None = None

    @classmethod
    def from_status(cls, exit_code, result, files=None, system_error=None,
                    human_lines=None, idn=None, backend=None, timeout_ms=None):
        fields = status_fields(system_error)
        if "post_command_status" in fields:
            result = {**result, "post_command_status": fields["post_command_status"]}
        return cls(exit_code, result, [] if files is None else files,
                   fields["system_error"], [] if human_lines is None else human_lines,
                   idn, backend, timeout_ms)


@dataclass(frozen=True)
class CaptureRequest:
    channels: Sequence[int | str]
    points: int
    waveform_format: str = "byte"
    csv_path: str | Path | None = None
    meta_path: str | Path | None = None
    plot_path: str | Path | None = None
    allow_time_axis_tolerance: bool = False
    trigger_wait: TriggerWaitConfig | None = None


@dataclass(frozen=True)
class CaptureBatchRequest:
    """Normalized request for one finite waveform capture batch."""

    channels: Sequence[int | str]
    points: int = 1000
    waveform_format: str = "byte"
    requested_count: int = 1
    interval_seconds: float = 0.0
    output_dir: str | Path | None = None
    log_scpi: bool = False


@dataclass(frozen=True)
class MeasureRequest:
    item: str
    channel: int | None = None
    reference_channel: int | None = None
    time_s: float | None = None
    level: float | None = None
    slope: str | None = None
    occurrence: int | None = None


@dataclass(frozen=True)
class MeasureSweepRequest:
    channels: Sequence[int | str] | None = None
    items: str = "vpp,frequency,period,vrms"
    pairs: Sequence[str] = ()
    pair_items: str = "phase,delay"


@dataclass(frozen=True)
class MeasureLogRequest:
    """Normalized request for one finite measurement logging run."""

    channels: Sequence[int | str] | None = None
    items: str = "vpp,frequency"
    pairs: Sequence[str] = ()
    pair_items: str = "phase,delay"
    interval_seconds: float = 1.0
    requested_count: int | None = None
    requested_duration_seconds: float | None = None
    output_dir: str | Path | None = None
    save_results: bool = True
    stop_on_error: bool = False
    log_scpi: bool = False


@dataclass(frozen=True)
class SmokeRequest:
    output_dir: str | Path | None = None
    log_scpi: bool = False
    save_artifacts: bool = True


@dataclass(frozen=True)
class AcquisitionCheckRequest:
    output_dir: str | Path | None = None
    average_count: int = 16
    check_only: bool = False
    stop_on_error: bool = False
    restore_type: bool = False
    log_scpi: bool = False


class _OperationError(OscilloscopeError):
    def __init__(self, original: OscilloscopeError, result: OperationResult) -> None:
        super().__init__(str(original))
        self.result = result
