"""Small polling job runtime for WebUI command execution."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Mapping
import uuid

from .commands import ScopeSessionCloseError, execute_command


JOB_STATUSES = frozenset({"queued", "running", "completed", "failed", "cancelled"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


class JobManagerShuttingDown(RuntimeError):
    """Raised when a job is submitted after shutdown has started."""


@dataclass
class Job:
    job_id: str
    command: str
    mode: str
    resource: str | None
    model_id: str | None
    parameters: dict[str, Any]
    artifact_dir: Path
    status: str = "queued"
    created_at: str = field(default_factory=lambda: _timestamp())
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    cancel_requested: bool = field(default=False, repr=False)
    cleanup_failed: bool = field(default=False, repr=False)
    future: Future[Any] | None = field(default=None, repr=False)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def to_payload(self) -> dict[str, Any]:
        with self.lock:
            artifacts = [dict(item) for item in self.artifacts]
            for artifact in artifacts:
                artifact["url"] = f"/api/jobs/{self.job_id}/artifacts/{artifact['name']}"
            return {
                "job_id": self.job_id,
                "command": self.command,
                "mode": self.mode,
                "resource": self.resource,
                "model_id": self.model_id,
                "parameters": dict(self.parameters),
                "status": self.status,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "result": self.result,
                "error": self.error,
                "artifacts": artifacts,
            }


class JobManager:
    """Own WebUI jobs and serialize live instrument sessions."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._hardware_lock = threading.Lock()
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
            job = Job(
                job_id=uuid.uuid4().hex,
                command=request["command"],
                mode=request["mode"],
                resource=request.get("resource"),
                model_id=request["model_id"],
                parameters=dict(request["parameters"]),
                artifact_dir=Path(tempfile.mkdtemp(prefix="scopes-tool-webui-")),
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
            lock = self._hardware_lock if job.mode == "live" and job.command != "list-resources" else _NullLock()
            with lock:
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
                    artifact_dir=job.artifact_dir,
                    stop_requested=lambda: job.cancel_requested,
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
        root = job.artifact_dir.resolve()
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
            registered.append(
                {
                    "name": path.name,
                    "kind": item.get("kind", "file"),
                    "size": path.stat().st_size,
                }
            )
        return registered

    def artifact_path(self, job_id: str, name: str) -> tuple[Job, Path] | None:
        job = self.get(job_id)
        if job is None:
            return None
        with job.lock:
            registered = next(
                (item for item in job.artifacts if item.get("name") == name),
                None,
            )
        if registered is None:
            return None
        path = (job.artifact_dir / name).resolve()
        try:
            path.relative_to(job.artifact_dir.resolve())
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
