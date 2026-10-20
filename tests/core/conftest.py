"""Shared checks for finite workflow persistence."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def check_incremental_manifest(monkeypatch):
    writes = []
    dump = json.dump

    def observe(payload, handle, *args, **kwargs):
        if isinstance(payload, dict) and "status" in payload:
            writes.append((Path(handle.name).parent, payload["status"], {
                key: len(value) for key, value in payload.items() if isinstance(value, list)
            }))
        return dump(payload, handle, *args, **kwargs)

    monkeypatch.setattr(json, "dump", observe)

    def check(output_dir, history_key, count):
        snapshots = [(status, sizes) for parent, status, sizes in writes
                     if parent == output_dir and history_key in sizes]
        running = [sizes for status, sizes in snapshots if status == "running"]
        assert running
        assert all(sizes[history_key] == 0 for sizes in running)
        assert all(sizes.get("files", 0) == 0 for sizes in running)
        assert snapshots[-1][0] != "running"
        assert snapshots[-1][1][history_key] == count
        assert not (output_dir / ".manifest-history.jsonl").exists()
        assert not (output_dir / ".manifest.json.tmp").exists()

    return check


@pytest.fixture
def fail_progress_snapshot(monkeypatch):
    dump = json.dump

    def install(count_field="completed_count"):
        def fail(payload, handle, *args, **kwargs):
            if payload.get("status") == "running" and payload.get(count_field) == 2:
                raise OSError("progress snapshot failed")
            return dump(payload, handle, *args, **kwargs)

        monkeypatch.setattr(json, "dump", fail)

    return install
