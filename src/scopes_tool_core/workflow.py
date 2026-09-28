"""Small synchronous helpers for finite Core workflows."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import logging
from pathlib import Path
import sys
import time
from typing import Callable, Iterator

from .errors import OscilloscopeError
from .log import LOGGER_NAME


StopRequested = Callable[[], bool]


@dataclass(frozen=True)
class WorkflowProgress:
    """Progress reported after one workflow item is completed."""

    completed_count: int
    total_count: int | None
    elapsed_seconds: float


ProgressReporter = Callable[[WorkflowProgress], None]


@contextmanager
def workflow_scpi_logging(
    log_path: str | Path | None,
    *,
    echo_to_stderr: bool = False,
) -> Iterator[None]:
    """Log Core workflow SCPI activity to one file for the context lifetime."""

    logger = logging.getLogger(LOGGER_NAME)
    old_level = logger.level
    old_propagate = logger.propagate
    formatter = logging.Formatter("%(name)s %(levelname)s: %(message)s")
    handlers: list[logging.Handler] = []

    if log_path is not None:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    if echo_to_stderr:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    try:
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        for handler in handlers:
            logger.addHandler(handler)
        yield
    finally:
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(old_level)
        logger.propagate = old_propagate


def establish_instrument_status_boundary(scope, *, max_reads: int = 30) -> tuple:
    """Clear stale status using the active driver's native status model."""

    return tuple(scope.establish_status_boundary(max_reads=max_reads))


def instrument_status_fields(entry) -> dict[str, object]:
    """Serialize one driver status sample without conflating SESR with an error queue."""

    if getattr(entry, "is_system_error_queue", True):
        return {
            "system_error": {
                "code": entry.code,
                "message": entry.message,
                "raw": entry.raw,
                "is_error": entry.is_error,
            }
        }
    payload = dict(entry.to_json())
    payload.setdefault("is_error", entry.is_error)
    return {
        "system_error": None,
        "post_command_status": payload,
    }


def system_error_from_status(entry) -> dict[str, object] | None:
    """Return legacy system-error JSON only for queue-based status models."""

    return instrument_status_fields(entry)["system_error"]


def status_human_label(entry) -> str:
    """Return a human-facing label for one native status sample."""

    return str(getattr(entry, "status_label", "Instrument status"))


def drain_preexisting_system_errors(scope, *, max_reads: int = 30) -> tuple:
    """Compatibility alias for the driver-owned pre-operation status boundary."""

    return establish_instrument_status_boundary(scope, max_reads=max_reads)


def interruptible_wait(
    seconds: float,
    *,
    stop_requested: StopRequested | None = None,
) -> bool:
    """Wait for ``seconds`` or return ``False`` when cancellation is requested."""

    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        if stop_requested is not None and stop_requested():
            return False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(0.1, remaining))
