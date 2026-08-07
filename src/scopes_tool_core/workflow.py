"""Small synchronous helpers for finite Core workflows."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable


StopRequested = Callable[[], bool]


@dataclass(frozen=True)
class WorkflowProgress:
    """Progress reported after one workflow item is safely persisted."""

    completed_count: int
    total_count: int | None
    elapsed_seconds: float


ProgressReporter = Callable[[WorkflowProgress], None]


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
