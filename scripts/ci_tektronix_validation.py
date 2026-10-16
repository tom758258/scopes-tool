"""Run isolated Tektronix pytest shards concurrently on one Windows CI job.

No new dependency or CI job is needed; all selected nodeids execute exactly
once, while each child pytest process keeps independent module fixtures and
temporary paths. Only hardware-free validation is selected.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
import os
from pathlib import Path
import re
import subprocess
import sys
import time

# Direct script invocation puts scripts/ first on sys.path; use repository root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
shard_for_nodeid = import_module("tests.tooling._tektronix_shard").shard_for_nodeid

COUNT = 2
MARKERS = "not hardware and windows_powershell and validation_tektronix"
TEMPROOT = Path(".tmp_tests")


def _collect_nodeids() -> list[str]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", MARKERS],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError("Tektronix collection failed:\n" + completed.stdout + completed.stderr)
    nodes = [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    ]
    if not nodes or len(nodes) != len(set(nodes)):
        raise RuntimeError(f"Invalid Tektronix nodeid inventory: {len(nodes)} collected")
    return nodes


def _run_shard(index: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SCOPES_TEKTRONIX_SHARD_INDEX"] = str(index)
    env["SCOPES_TEKTRONIX_SHARD_COUNT"] = str(COUNT)
    cmd = [
        sys.executable, "-m", "pytest", "-q", "-m", MARKERS,
        "-p", "tests.tooling._tektronix_shard", "--durations=30",
        "--basetemp", str(TEMPROOT / f"ci-windows-validation-tektronix-shard-{index}"),
    ]
    return subprocess.run(cmd, env=env, text=True, capture_output=True, check=False)


def main() -> int:
    selected = _collect_nodeids()
    sizes = [sum(shard_for_nodeid(node, COUNT) == idx for node in selected)
             for idx in range(COUNT)]
    if any(size == 0 for size in sizes) or sum(sizes) != len(selected):
        raise RuntimeError(f"Incomplete Tektronix partition: {sizes} of {len(selected)}")
    print(f"Tektronix CI: {len(selected)} collected, shard sizes {sizes}; "
          "independent test processes, no hardware", flush=True)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=COUNT) as pool:
        futures = [pool.submit(_run_shard, idx) for idx in range(COUNT)]
        results = [future.result() for future in futures]
    passed_total = 0
    success = True
    for idx, result in enumerate(results):
        print(f"\n=== Tektronix shard {idx + 1}/{COUNT}: exit {result.returncode} ===",
              flush=True)
        print(result.stdout, flush=True)
        if result.stderr:
            print(result.stderr, file=sys.stderr, flush=True)
        found = re.search(r"(?m)^(\d+) passed(?:,\s*\d+ deselected)? in [\d.]+s", result.stdout)
        if result.returncode or not found or int(found.group(1)) != sizes[idx]:
            success = False
        if found:
            passed_total += int(found.group(1))
    duration = time.perf_counter() - started
    print(f"Tektronix shards: {passed_total}/{len(selected)} passed; "
          f"wall {duration:.2f}s (concurrent, not summed pytest duration)",
          flush=True)
    return 0 if success and passed_total == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
