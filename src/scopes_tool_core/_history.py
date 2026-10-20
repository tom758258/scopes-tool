"""Incremental history and atomic manifest snapshots for finite workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Mapping


class _ManifestHistory:
    def __init__(self, path: Path | None, key: str) -> None:
        self.path = path
        self.key = key
        self._committed_bytes = 0

    def write(
        self,
        manifest: Mapping[str, object],
        writer: Callable,
        *,
        record: Mapping[str, object] | None = None,
    ) -> None:
        if self.path is None:
            return
        path = self.path
        journal = path.with_name(".manifest-history.jsonl")
        temporary = path.with_name(f".{path.name}.tmp")
        final = manifest["status"] != "running"
        payload = dict(manifest)
        if not final:
            payload[self.key] = []
            if "files" in payload:
                payload["files"] = []
        elif self._committed_bytes:
            with journal.open("rb") as handle:
                payload[self.key] = [
                    json.loads(line)
                    for line in handle.read(self._committed_bytes).splitlines()
                ]

        offset = None
        try:
            if record is not None:
                data = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
                path.parent.mkdir(parents=True, exist_ok=True)
                with journal.open("ab") as handle:
                    offset = handle.tell()
                    handle.write(data)
                    handle.flush()
                    pending_bytes = handle.tell()
            writer(payload, temporary)
            temporary.replace(path)
            if record is not None:
                self._committed_bytes = pending_bytes
        except BaseException:
            # A failed snapshot must not commit its pending history record.
            if offset is not None:
                try:
                    with journal.open("r+b") as handle:
                        handle.truncate(offset)
                except OSError:
                    pass
            raise

        if final:
            # Keep the journal if final publication fails; cleanup is optional.
            try:
                journal.unlink(missing_ok=True)
                self._committed_bytes = 0
            except OSError:
                pass
