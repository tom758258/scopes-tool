"""Commit boundaries shared by incremental workflow histories."""

import json
from pathlib import Path

import pytest

from scopes_tool_core._history import _ManifestHistory
from scopes_tool_core.batch import write_batch_manifest


def test_incremental_records_and_atomic_final_publication(tmp_path):
    path = tmp_path / "manifest.json"
    journal = tmp_path / ".manifest-history.jsonl"
    history = _ManifestHistory(path, "rows")
    manifest = {"status": "running", "completed_rows": 0, "rows": [], "files": []}
    history.write(manifest, write_batch_manifest)
    for index in range(1, 4):
        record = {"index": index, "value": index * 10}
        candidate = dict(manifest, completed_rows=index)
        history.write(candidate, write_batch_manifest, record=record)
        manifest["rows"].append(record)
        manifest["completed_rows"] = index
        assert json.loads(path.read_text()) == dict(candidate, rows=[])
        assert [json.loads(line) for line in journal.read_text().splitlines()] == manifest["rows"]

    manifest["status"] = "completed"

    def fail_final(payload, temporary):
        temporary.write_text("incomplete", encoding="utf-8")
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        history.write(manifest, fail_final)
    assert journal.exists()
    assert len(journal.read_text().splitlines()) == 3
    assert json.loads(path.read_text())["status"] == "running"

    history.write(manifest, write_batch_manifest)
    assert json.loads(path.read_text()) == manifest
    assert not journal.exists()
    assert not (tmp_path / ".manifest.json.tmp").exists()
    manifest["status"] = "error"
    history.write(manifest, write_batch_manifest)
    assert json.loads(path.read_text()) == manifest


@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_failed_snapshot_rolls_back_only_pending_record(tmp_path, failure):
    path = tmp_path / "manifest.json"
    journal = tmp_path / ".manifest-history.jsonl"
    history = _ManifestHistory(path, "rows")
    manifest = {"status": "running", "completed_rows": 1, "rows": []}
    history.write(manifest, write_batch_manifest, record={"index": 1})
    committed = journal.read_bytes()
    snapshot = path.read_bytes()

    def fail_snapshot(payload, temporary):
        raise failure("snapshot failed")

    with pytest.raises(failure):
        history.write(dict(manifest, completed_rows=2), fail_snapshot, record={"index": 2})
    assert journal.read_bytes() == committed
    assert path.read_bytes() == snapshot


def test_partial_journal_write_is_not_committed(tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    journal = tmp_path / ".manifest-history.jsonl"
    history = _ManifestHistory(path, "rows")
    manifest = {"status": "running", "rows": []}
    history.write(manifest, write_batch_manifest, record={"index": 1})
    committed = journal.read_bytes()
    original_open = Path.open

    class PartialAppend:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def tell(self):
            return self.handle.tell()

        def write(self, data):
            self.handle.write(data[:3])
            raise OSError("journal full")

    def open_file(path, mode="r", *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        return PartialAppend(handle) if path == journal and mode == "ab" else handle

    monkeypatch.setattr(Path, "open", open_file)
    with pytest.raises(OSError, match="journal full"):
        history.write(manifest, write_batch_manifest, record={"index": 2})
    assert journal.read_bytes() == committed


def test_failed_atomic_replacement_preserves_snapshot_and_history(tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    journal = tmp_path / ".manifest-history.jsonl"
    history = _ManifestHistory(path, "rows")
    manifest = {"status": "running", "completed_rows": 1, "rows": []}
    history.write(manifest, write_batch_manifest, record={"index": 1})
    snapshot, committed = path.read_bytes(), journal.read_bytes()

    def fail_replace(*args):
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        history.write(dict(manifest, completed_rows=2), write_batch_manifest, record={"index": 2})
    assert path.read_bytes() == snapshot
    assert journal.read_bytes() == committed


def test_no_save_creates_no_files(tmp_path):
    def unexpected_write(*args):
        pytest.fail("no-save must not call a writer")

    history = _ManifestHistory(None, "rows")
    history.write({"status": "running"}, unexpected_write, record={"index": 1})
    history.write({"status": "completed"}, unexpected_write)
    assert list(tmp_path.iterdir()) == []
