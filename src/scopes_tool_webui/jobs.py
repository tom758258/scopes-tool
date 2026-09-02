"""Small polling job runtime for WebUI command execution."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import threading
import time
from typing import Any, Mapping
import uuid

from .command_catalog import PC_OUTPUT_COMMAND_IDS
from .commands import ScopeSessionCloseError, execute_command


JOB_STATUSES = frozenset({"queued", "running", "completed", "failed", "cancelled"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

_RESULT_PROGRESS_COMMANDS = frozenset(
    {
        "sequence",
        "measure-log",
        "measure-until",
        "triggered-measure-loop",
        "capture-batch",
        "capture-until",
        "triggered-capture-series",
    }
)


class JobManagerShuttingDown(RuntimeError):
    """Raised when a job is submitted after shutdown has started."""


@dataclass
class Job:
    job_id: str
    command: str
    mode: str
    resource: str | None
    model_id: str | None
    pc_output_dir: str
    parameters: dict[str, Any]
    pc_output_root: Path
    status: str = "queued"
    created_at: str = field(default_factory=lambda: _timestamp())
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    artifact_paths: dict[str, Path] = field(default_factory=dict, repr=False)
    cancel_requested: bool = field(default=False, repr=False)
    cleanup_failed: bool = field(default=False, repr=False)
    monitor_updates: list[dict[str, Any]] = field(default_factory=list, repr=False)
    monitor_update_sequence: int = field(default=0, repr=False)
    monitor_summary: dict[str, Any] | None = field(default=None, repr=False)
    progress: dict[str, Any] | None = field(default=None, repr=False)
    future: Future[Any] | None = field(default=None, repr=False)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def to_payload(self, *, after_sequence: int = 0) -> dict[str, Any]:
        with self.lock:
            artifacts = [dict(item) for item in self.artifacts]
            for artifact in artifacts:
                artifact["url"] = f"/api/jobs/{self.job_id}/artifacts/{artifact['name']}"
            payload = {
                "job_id": self.job_id,
                "command": self.command,
                "mode": self.mode,
                "resource": self.resource,
                "model_id": self.model_id,
                "pc_output_dir": self.pc_output_dir,
                "parameters": dict(self.parameters),
                "status": self.status,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "result": self.result,
                "error": self.error,
                "artifacts": artifacts,
            }
            if self.progress is not None:
                payload["progress"] = dict(self.progress)
            if self.command == "capture-monitor":
                first_sequence = (
                    self.monitor_updates[0]["sequence"]
                    if self.monitor_updates
                    else self.monitor_update_sequence + 1
                )
                reset = bool(
                    self.monitor_updates
                    and after_sequence < first_sequence - 1
                )
                updates = (
                    list(self.monitor_updates)
                    if reset
                    else [
                        item
                        for item in self.monitor_updates
                        if item["sequence"] > after_sequence
                    ]
                )
                payload["monitor_runtime"] = {
                    "sequence": self.monitor_update_sequence,
                    "reset": reset,
                    "updates": updates,
                    "summary": dict(self.monitor_summary or {}),
                }
                if self.status in TERMINAL_STATUSES:
                    self.monitor_updates.clear()
            return payload


class JobManager:
    """Own WebUI jobs and serialize live instrument sessions."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._hardware_lock = threading.Lock()
        self._pc_output_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="scopes-tool-webui-job",
        )
        self._shutdown_started = False
        self._executor_shutdown = False
        self._shutdown_job_ids: set[str] = set()

    def submit(self, request: Mapping[str, Any]) -> Job:
        with self._lock:
            if self._shutdown_started or self._executor_shutdown:
                raise JobManagerShuttingDown(
                    "WebUI job manager is shutting down; new jobs are not accepted."
                )
            job_id = uuid.uuid4().hex
            output_root = Path(request.get("pc_output_dir", "data")).resolve()
            job = Job(
                job_id=job_id,
                command=request["command"],
                mode=request["mode"],
                resource=request.get("resource"),
                model_id=request["model_id"],
                pc_output_dir=request.get("pc_output_dir", "data"),
                parameters=dict(request["parameters"]),
                pc_output_root=output_root,
            )
            self._jobs[job.job_id] = job
            job.future = self._executor.submit(self._run, job.job_id)
        return job

    async def shutdown(self, timeout_s: float = 10.0) -> None:
        """Stop admission and wait for owned jobs without interrupting I/O."""
        if timeout_s < 0:
            raise ValueError("shutdown timeout must not be negative")

        with self._lock:
            if self._executor_shutdown:
                return
            self._shutdown_started = True
            self._shutdown_job_ids.update(
                job_id
                for job_id, job in self._jobs.items()
                if job.status not in TERMINAL_STATUSES
            )
            target_job_ids = set(self._shutdown_job_ids)

        for job_id in target_job_ids:
            self.cancel(job_id)

        deadline = time.monotonic() + timeout_s
        while True:
            with self._lock:
                pending_job_ids = set()
                cleanup_failures = set()
                for job_id in target_job_ids:
                    job = self._jobs.get(job_id)
                    if job is None:
                        continue
                    with job.lock:
                        if job.status not in TERMINAL_STATUSES:
                            pending_job_ids.add(job_id)
                        if job.cleanup_failed:
                            cleanup_failures.add(job_id)

            if cleanup_failures:
                failed = ", ".join(sorted(cleanup_failures))
                raise RuntimeError(f"WebUI job cleanup failed during shutdown: {failed}")
            if not pending_job_ids:
                self._executor.shutdown(wait=True)
                with self._lock:
                    self._executor_shutdown = True
                return
            if time.monotonic() >= deadline:
                details = ", ".join(sorted(pending_job_ids))
                raise TimeoutError(f"WebUI job shutdown timed out (pending jobs: {details})")
            await asyncio.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> tuple[str, str, bool] | None:
        job = self.get(job_id)
        if job is None:
            return None
        with job.lock:
            if job.status == "queued":
                job.cancel_requested = True
                if job.future is not None:
                    job.future.cancel()
                job.status = "cancelled"
                job.finished_at = _timestamp()
                return "cancelled", "Queued job cancelled.", True
            if job.status == "running":
                job.cancel_requested = True
                return "running", "Cancellation requested; waiting for cleanup.", True
            return job.status, f"Job is already {job.status}.", False

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        with job.lock:
            if job.status != "queued":
                return
            job.status = "running"
            job.started_at = _timestamp()

        try:
            output_lock = (
                self._pc_output_lock
                if job.mode != "dry-run" and job.command in PC_OUTPUT_COMMAND_IDS
                else _NullLock()
            )
            hardware_lock = (
                self._hardware_lock
                if job.mode == "live" and job.command != "list-resources"
                else _NullLock()
            )
            with output_lock:
                with hardware_lock:
                    with job.lock:
                        if job.cancel_requested:
                            job.status = "cancelled"
                            job.finished_at = _timestamp()
                            return
                    execution = execute_command(
                        job.command,
                        mode=job.mode,
                        resource=job.resource,
                        model_id=job.model_id,
                        parameters=job.parameters,
                        artifact_dir=job.pc_output_root,
                        stop_requested=lambda: job.cancel_requested,
                        sample_reporter=(
                            (lambda update: self._append_monitor_update(job, update))
                            if job.command == "capture-monitor"
                            else None
                        ),
                        progress_reporter=(
                            (lambda progress: self._set_progress(job, progress))
                            if job.command in _RESULT_PROGRESS_COMMANDS
                            else None
                        ),
                    )
                artifacts = self._register_artifacts(job, execution.get("artifacts", []))
            exit_code = execution.get("exit_code", 1)
            public_execution = dict(execution)
            public_execution["artifacts"] = [
                {
                    "kind": item.get("kind", "file"),
                    "name": Path(item["path"]).name,
                }
                for item in execution.get("artifacts", [])
                if isinstance(item, Mapping) and isinstance(item.get("path"), str)
            ]
            with job.lock:
                job.result = public_execution
                job.artifacts = artifacts
                if job.cancel_requested:
                    job.status = "cancelled"
                else:
                    job.status = "completed" if exit_code == 0 else "failed"
                if exit_code != 0 and not job.cancel_requested:
                    job.error = "Core command returned a non-zero exit code."
                job.finished_at = _timestamp()
        except Exception as exc:
            with job.lock:
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                job.cleanup_failed = isinstance(exc, ScopeSessionCloseError)
                job.finished_at = _timestamp()

    def _register_artifacts(
        self,
        job: Job,
        artifacts: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(artifacts, list):
            return []
        registered: list[dict[str, Any]] = []
        registered_paths: dict[str, Path] = {}
        root = job.pc_output_root
        for item in artifacts:
            if not isinstance(item, Mapping):
                continue
            raw_path = item.get("path")
            if not isinstance(raw_path, str):
                continue
            path = Path(raw_path).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                continue
            if not path.is_file():
                continue
            name = path.name
            if name in registered_paths:
                suffix = 2
                while True:
                    candidate = f"{path.stem}-{suffix}{path.suffix}"
                    if candidate not in registered_paths:
                        name = candidate
                        break
                    suffix += 1
            registered.append(
                {
                    "name": name,
                    "kind": item.get("kind", "file"),
                    "size": path.stat().st_size,
                }
            )
            registered_paths[name] = path
        with job.lock:
            job.artifact_paths = registered_paths
        return registered

    def _append_monitor_update(
        self,
        job: Job,
        update: Mapping[str, object],
    ) -> None:
        with job.lock:
            job.monitor_update_sequence += 1
            record = {"sequence": job.monitor_update_sequence, **dict(update)}
            job.monitor_updates.append(record)
            dropped = update.get("dropped_capture_count", 0)
            if isinstance(dropped, int) and dropped > 0:
                del job.monitor_updates[: min(dropped, len(job.monitor_updates))]
            points = job.parameters.get("points", 1000)
            retention = job.parameters.get("retention_points", 250000)
            if isinstance(points, int) and points > 0 and isinstance(retention, int):
                maximum_chunks = max(1, retention // points)
                if len(job.monitor_updates) > maximum_chunks:
                    del job.monitor_updates[:-maximum_chunks]
            job.monitor_summary = {
                key: value
                for key, value in update.items()
                if key not in {"time_s", "channels"}
            }

    def _set_progress(self, job: Job, progress: Any) -> None:
        with job.lock:
            total_count = getattr(progress, "total_count")
            job.progress = {
                "completed_count": int(getattr(progress, "completed_count")),
                "total_count": None if total_count is None else int(total_count),
                "elapsed_seconds": float(getattr(progress, "elapsed_seconds")),
            }

    def artifact_path(self, job_id: str, name: str) -> tuple[Job, Path] | None:
        job = self.get(job_id)
        if job is None:
            return None
        with job.lock:
            registered_path = job.artifact_paths.get(name)
        if registered_path is None:
            return None
        path = registered_path.resolve()
        try:
            path.relative_to(job.pc_output_root)
        except ValueError:
            return None
        if not path.is_file():
            return None
        return job, path


class _NullLock:
    def __enter__(self) -> "_NullLock":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


job_manager = JobManager()
