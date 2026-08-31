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
    """Progress reported after one workflow item is safely persisted."""

    completed_count: int
    total_count: int | None
    elapsed_seconds: float


ProgressReporter = Callable[[WorkflowProgress], None]


@contextmanager
def workflow_scpi_logging(
    log_path: str | Path,
    *,
    echo_to_stderr: bool = False,
) -> Iterator[None]:
    """Log Core workflow SCPI activity to one file for the context lifetime."""

    logger = logging.getLogger(LOGGER_NAME)
    old_level = logger.level
    old_propagate = logger.propagate
    formatter = logging.Formatter("%(name)s %(levelname)s: %(message)s")
    handlers: list[logging.Handler] = []

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


def drain_preexisting_system_errors(scope, *, max_reads: int = 30) -> tuple:
    """Drain stale system errors before a top-level operation.

    Uses the existing ``scope.drain_system_errors`` bounded drain.
    Returns non-zero entries for human diagnostics. Raises if the queue
    does not reach code 0 within ``max_reads``.
    """

    entries = scope.drain_system_errors(max_reads=max_reads)
    if not entries or entries[-1].is_error:
        raise OscilloscopeError(
            f"System error queue did not reach code 0 within {max_reads} reads."
        )
    return tuple(entry for entry in entries if entry.is_error)


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
