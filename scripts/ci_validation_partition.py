"""Validate and record the Windows PowerShell case partition without hardware.

Run on Linux Python 3.13 before the expensive Windows jobs.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # direct execution starts with scripts/ on sys.path
EXPECTED_WINDOWS_CASES = 334  # Stage 2: seven redundant parameter variants consolidated.


class ValidationInventory:
    @pytest.hookimpl
    def pytest_collection_finish(self, session):
        from tests.tooling._validation_grouping import GROUPS

        inventory = {group: [] for group in GROUPS}
        all_windows = []
        for item in session.items:
            if item.get_closest_marker("windows_powershell") is None:
                continue
            all_windows.append(item.nodeid)
            owners = [
                group for group in GROUPS
                if item.get_closest_marker(f"validation_{group}") is not None
            ]
            if len(owners) != 1:
                raise pytest.UsageError(
                    f"Windows test {item.nodeid} belongs to {owners}, expected exactly one"
                )
            inventory[owners[0]].append(item.nodeid)

        all_ids = set(all_windows)
        assigned = [node for values in inventory.values() for node in values]
        if len(all_ids) != len(all_windows) or len(set(assigned)) != len(assigned):
            raise pytest.UsageError("Duplicate nodeids in Windows validation partition")
        if set(assigned) != all_ids or len(all_windows) != EXPECTED_WINDOWS_CASES:
            raise pytest.UsageError(
                f"Windows partition changed: {len(all_windows)} collected, "
                f"{len(assigned)} assigned; expected {EXPECTED_WINDOWS_CASES}"
            )
        if any(not values for values in inventory.values()):
            raise pytest.UsageError("Each validation group must contain tests")

        destination = ROOT / ".tmp_tests" / "ci-validation-inventory.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps({group: sorted(items) for group, items in inventory.items()}, indent=2) + "\n",
            encoding="utf-8",
        )
        counts = ", ".join(f"{group}={len(items)}" for group, items in inventory.items())
        print(f"Windows validation partition PASS: {len(all_windows)} unique cases ({counts})")


if __name__ == "__main__":
    raise SystemExit(
        pytest.main(["--collect-only", "-q", "tests/tooling"], plugins=[ValidationInventory()])
    )
