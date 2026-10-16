"""Partition Tektronix tests inside a single Windows CI runner.

Use only in the Tektronix CI wrapper; ordinary pytest invocation is unchanged.
The existing tests/conftest.py still assigns vendor ownership and enforces
unknown modules fail closed before this plugin selects a deterministic shard.
"""

from __future__ import annotations

import hashlib
import os

import pytest


def shard_for_nodeid(nodeid: str, count: int) -> int:
    return int.from_bytes(hashlib.sha256(nodeid.encode("utf-8")).digest()[:8], "big") % count


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    index = int(os.environ["SCOPES_TEKTRONIX_SHARD_INDEX"])
    count = int(os.environ["SCOPES_TEKTRONIX_SHARD_COUNT"])
    if count < 2 or not (0 <= index < count):
        raise pytest.UsageError(f"Invalid Tektronix shard {index} of {count}")

    # Fail closed if -m selection/marker ownership changes upstream.
    if any(
        item.get_closest_marker("hardware") is not None or
        item.get_closest_marker("windows_powershell") is None or
        item.get_closest_marker("validation_tektronix") is None
        for item in items
    ):
        raise pytest.UsageError("Unexpected case reached Tektronix-only shard")

    kept = [item for item in items if shard_for_nodeid(item.nodeid, count) == index]
    removed = [item for item in items if shard_for_nodeid(item.nodeid, count) != index]
    config.hook.pytest_deselected(items=removed)
    items[:] = kept
    if not kept:
        raise pytest.UsageError(f"Tektronix shard {index}/{count} is unexpectedly empty")
