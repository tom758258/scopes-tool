"""Worker server, runtime, and lifecycle implementation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from queue import Full, Queue
import sys
import threading
from typing import Any
from uuid import uuid4

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.identity import physical_model_for_id

from . import cli as scope_cli

from .worker_client import (
    _http_request,
    _validate_client_response,
    client_get,
    client_post,
    client_send_command,
    client_wait_ready,
)
from .worker_commands import (
    DOMAIN_COMMANDS,
    WORKER_SCHEMA_VERSION,
    _CORE_WORKFLOW_COMMANDS,
    _MATH_DOMAIN_COMMANDS,
    _MATH_WORKER_ARGUMENTS,
    _NON_MATH_DOMAIN_COMMANDS,
    _normalize_external_trigger_probe_worker_arguments,
    _normalize_external_trigger_range_worker_arguments,
    _normalize_external_trigger_settings_worker_arguments,
    _normalize_external_trigger_units_worker_arguments,
    _normalize_segmented_capture_worker_arguments,
    _normalize_trigger_common_worker_arguments,
    _normalize_trigger_delay_worker_arguments,
    _normalize_trigger_edge_burst_worker_arguments,
    _normalize_trigger_edge_external_level_worker_arguments,
    _normalize_trigger_edge_level_worker_arguments,
    _normalize_trigger_edge_slope_worker_arguments,
    _normalize_trigger_edge_source_worker_arguments,
    _normalize_trigger_edge_worker_arguments,
    _normalize_trigger_glitch_worker_arguments,
    _normalize_trigger_holdoff_worker_arguments,
    _normalize_trigger_or_worker_arguments,
    _normalize_trigger_pattern_worker_arguments,
    _normalize_trigger_runt_worker_arguments,
    _normalize_trigger_setup_hold_worker_arguments,
    _normalize_trigger_transition_worker_arguments,
    _normalize_trigger_tv_worker_arguments,
    arguments_to_argv,
    parse_domain_command,
    validate_command_request,
)


_CORE_WORKFLOW_TERMINAL_STATUSES = {
    "completed",
    "cancelled",
    "instrument_error",
    "error",
    "interrupted",
}


@dataclass
class WorkerJob:
    command: str
    arguments: dict[str, Any]
    job_id: str | None
    worker_job_id: str
    artifact_path: Path
    request_time: str
    state: str = "queued"
    accepted_time: str | None = None
    started_time: str | None = None
    finished_time: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    exit_code: int | None = None
    cancel_requested: bool = False


@dataclass
class WorkerRuntime:
    host: str
    port: int
    mode: str
    model: str
    resource: str | None
    artifact_root: Path
    queue_max: int
    output_format: str
    run_id: str = field(default_factory=lambda: uuid4().hex)
    queue: Queue[WorkerJob] = field(init=False)
    jobs: dict[str, WorkerJob] = field(default_factory=dict)
    active_job_id: str | None = None
    last_job_id: str | None = None
    fatal_error: str | None = None
    stopping: bool = False
    accepted: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.queue = Queue(maxsize=self.queue_max)

    def emit(self, event: str, **values: Any) -> None:
        payload = _event_payload(self, event, **values)
        if self.output_format == "jsonl":
            print(json.dumps(payload, sort_keys=True), flush=True)
        else:
            print(f"{event}: {payload}", flush=True)

    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def status_payload(self) -> dict[str, Any]:
        with self.lock:
            active = self.jobs.get(self.active_job_id) if self.active_job_id else None
            last = self.jobs.get(self.last_job_id) if self.last_job_id else None
            queued = [
                {
                    "worker_job_id": job.worker_job_id,
                    "job_id": job.job_id,
                    "command": job.command,
                    "state": job.state,
                }
                for job in self.jobs.values()
                if job.state == "queued"
            ]
        return {
            "schema_version": WORKER_SCHEMA_VERSION,
            "service": "scopes-tool",
            "status": "stopping" if self.stopping else "ready",
            "run_id": self.run_id,
            "mode": self.mode,
            "model": self.model,
            "resource": self.resource,
            "queue": {
                "max": self.queue_max,
                "size": self.queue.qsize(),
                "jobs": queued,
            },
            "active_job": _job_summary(active),
            "last_job": _job_summary(last),
            "urls": {
                "command_url": f"{self.base_url()}/command",
                "status_url": f"{self.base_url()}/status",
                "stop_url": f"{self.base_url()}/stop",
            },
            "fatal_error": self.fatal_error,
            "timestamp_utc": _now(),
        }


def dispatch_lifecycle_command(args: argparse.Namespace) -> int:
    if args.command == "worker":
        return run_worker(args)
    if args.command == "send-command":
        return client_send_command(args)
    if args.command == "status":
        return client_get(args, "/status")
    if args.command == "stop":
        return client_post(args, "/stop", {})
    if args.command == "wait-ready":
        return client_wait_ready(args)
    raise OscilloscopeError("unknown lifecycle command")


def run_worker(args: argparse.Namespace) -> int:
    mode = "simulate" if args.simulate else "live"
    if mode == "live" and not args.resource:
        raise OscilloscopeError("worker --live requires --resource")
    physical_model_for_id(args.model)
    capabilities_for_model_id(args.model)
    runtime = WorkerRuntime(
        host=args.host,
        port=args.port,
        mode=mode,
        model=args.model,
        resource=args.resource,
        artifact_root=Path(args.artifact_root),
        queue_max=args.queue_max,
        output_format=args.format,
    )
    handler = _make_handler(runtime)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    runtime.port = server.server_port
    worker_thread = threading.Thread(target=_job_loop, args=(runtime,), daemon=True)
    worker_thread.start()
    runtime.emit(
        "ready",
        status_url=f"{runtime.base_url()}/status",
        command_url=f"{runtime.base_url()}/command",
        stop_url=f"{runtime.base_url()}/stop",
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        runtime.stopping = True
        runtime.emit("summary", ok=False, fatal_error="interrupted", exit_code=130)
        return 130
    except Exception as exc:
        runtime.fatal_error = str(exc)
        runtime.emit("summary", ok=False, fatal_error=runtime.fatal_error, exit_code=3)
        return 3
    finally:
        server.server_close()
    runtime.queue.join()
    runtime.emit(
        "summary",
        ok=runtime.fatal_error is None,
        fatal_error=runtime.fatal_error,
        exit_code=0 if runtime.fatal_error is None else 3,
    )
    return 0 if runtime.fatal_error is None else 3


def _make_handler(runtime: WorkerRuntime):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            print(fmt % args, file=sys.stderr, flush=True)

        def do_GET(self) -> None:
            if self.path != "/status":
                self._send(404, {"status": "error", "error": {"message": "not found"}})
                return
            self._send(200, runtime.status_payload())

        def do_POST(self) -> None:
            if self.path == "/command":
                self._handle_command()
                return
            if self.path == "/stop":
                self._handle_stop()
                return
            self._send(404, {"status": "error", "error": {"message": "not found"}})

        def _handle_command(self) -> None:
            command_echo: str | None = None
            job_id_echo: str | None = None
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                body = json.loads(raw.decode("utf-8") if raw else "{}")
                command_echo, job_id_echo = _command_identity(body)
                command, arguments, job_id = validate_command_request(body)
                parse_domain_command(command, arguments, runtime)
            except json.JSONDecodeError as exc:
                self._send(
                    400,
                    _command_error_envelope(
                        "malformed JSON",
                        command_echo,
                        job_id_echo,
                        exc,
                    ),
                )
                return
            except OscilloscopeError as exc:
                self._send(
                    400,
                    _command_error_envelope(str(exc), command_echo, job_id_echo, exc),
                )
                return
            if runtime.stopping:
                self._send(
                    409,
                    _command_rejected_envelope(
                        "worker_stopping", command_echo, job_id_echo
                    ),
                )
                return
            if runtime.queue.full():
                self._send(
                    429,
                    _command_rejected_envelope("queue_full", command_echo, job_id_echo),
                )
                return
            worker_job_id = uuid4().hex
            artifact_path = runtime.artifact_root / runtime.run_id / worker_job_id
            job = WorkerJob(
                command=command,
                arguments=arguments,
                job_id=job_id,
                worker_job_id=worker_job_id,
                artifact_path=artifact_path,
                request_time=_now(),
                accepted_time=_now(),
            )
            try:
                with runtime.lock:
                    runtime.jobs[worker_job_id] = job
                runtime.queue.put_nowait(job)
                with runtime.lock:
                    runtime.accepted += 1
            except Full:
                with runtime.lock:
                    runtime.jobs.pop(worker_job_id, None)
                self._send(
                    429,
                    _command_rejected_envelope("queue_full", command_echo, job_id_echo),
                )
                return
            response = {
                "status": "accepted",
                "command": command,
                "job_id": job_id,
                "worker_job_id": worker_job_id,
                "artifact_path": str(artifact_path),
            }
            self._send(202, response)

        def _handle_stop(self) -> None:
            runtime.stopping = True
            cancelled = []
            with runtime.lock:
                for job in runtime.jobs.values():
                    if job.state == "queued":
                        _finish_cancelled_job(runtime, job, started=False)
                        cancelled.append(job.worker_job_id)
                    elif job.state == "running":
                        job.cancel_requested = True
            self._send(
                202,
                {
                    "status": "accepted",
                    "run_id": runtime.run_id,
                    "cancelled_jobs": cancelled,
                    "active_job": runtime.active_job_id,
                },
            )
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            payload = {**payload, "schema_version": WORKER_SCHEMA_VERSION}
            data = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _job_loop(runtime: WorkerRuntime) -> None:
    while True:
        job = runtime.queue.get()
        with runtime.lock:
            if job.state == "cancelled":
                runtime.queue.task_done()
                continue
            job.state = "running"
            job.started_time = _now()
            runtime.active_job_id = job.worker_job_id
        runtime.emit("job_started", worker_job_id=job.worker_job_id, command=job.command)
        try:
            parsed = parse_domain_command(
                job.command, job.arguments, runtime, job.artifact_path
            )
            _guard_no_overwrite(parsed, job.artifact_path)
            if any(
                path.is_relative_to(job.artifact_path)
                for path in _planned_artifact_paths(parsed)
            ):
                job.artifact_path.mkdir(parents=True, exist_ok=True)
            payload, exit_code = scope_cli._execute_json_command(
                parsed,
                stop_requested=lambda: job.cancel_requested or runtime.stopping,
            )
            job.result = payload
            job.exit_code = exit_code
            workflow_status = _core_workflow_result_status(job.command, payload)
            if workflow_status == "completed":
                job.state = "succeeded"
            elif workflow_status == "cancelled":
                job.state = "cancelled"
            elif workflow_status is not None:
                job.state = "failed"
            else:
                job.state = (
                    "cancelled"
                    if job.cancel_requested or runtime.stopping
                    else "succeeded" if exit_code == 0 else "failed"
                )
            if job.state == "cancelled":
                job.exit_code = 3
                job.error = {"type": "cancelled", "message": "cancelled by stop"}
            elif not payload.get("ok", False):
                err = payload.get("error")
                job.error = err if isinstance(err, dict) else None
        except Exception as exc:
            job.exit_code = 3
            job.state = "failed"
            job.error = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            job.finished_time = _now()
            with runtime.lock:
                runtime.active_job_id = None
                runtime.last_job_id = job.worker_job_id
                if job.state == "succeeded":
                    runtime.succeeded += 1
                elif job.state == "cancelled":
                    runtime.cancelled += 1
                else:
                    runtime.failed += 1
            runtime.emit(
                "job_finished",
                **_terminal_job_view(job),
                artifact_path=str(job.artifact_path),
            )
            runtime.queue.task_done()


def _core_workflow_result_status(
    command: str,
    payload: dict[str, object],
) -> str | None:
    if command not in _CORE_WORKFLOW_COMMANDS:
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    status = result.get("status")
    if status in _CORE_WORKFLOW_TERMINAL_STATUSES:
        return str(status)
    return None


def _event_payload(runtime: WorkerRuntime, event: str, **values: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": WORKER_SCHEMA_VERSION,
        "event": event,
        "run_id": runtime.run_id,
        "timestamp_utc": _now(),
        **values,
    }
    if event == "ready":
        payload.update(
            {
                "service": "scopes-tool",
                "host": runtime.host,
                "port": runtime.port,
                "mode": runtime.mode,
                "model": runtime.model,
                "resource": runtime.resource,
            }
        )
        payload.pop("trigger_url", None)
    elif event == "job_started":
        job = runtime.jobs.get(str(payload.get("worker_job_id")))
        payload.setdefault("job_id", None if job is None else job.job_id)
        payload.setdefault(
            "artifact_path", None if job is None else str(job.artifact_path)
        )
    elif event == "job_finished":
        state = payload.get("state")
        if state not in {"succeeded", "failed", "cancelled"}:
            raise ValueError(f"invalid job_finished state: {state}")
        if payload.get("ok") is True and state != "succeeded":
            raise ValueError("only succeeded job_finished events may use ok=true")
        if "result" not in payload or "files" not in payload:
            raise ValueError("job_finished events require result and files")
        payload.setdefault("error", None)
    elif event == "summary":
        payload.setdefault("ok", runtime.fatal_error is None)
        payload.setdefault("fatal_error", runtime.fatal_error)
        payload.update(
            {
                "accepted": runtime.accepted,
                "succeeded": runtime.succeeded,
                "failed": runtime.failed,
                "cancelled": runtime.cancelled,
            }
        )
    return payload


def _finish_cancelled_job(
    runtime: WorkerRuntime, job: WorkerJob, *, started: bool
) -> None:
    job.state = "cancelled"
    job.started_time = job.started_time if started else None
    job.finished_time = _now()
    job.exit_code = 3
    job.error = {"type": "cancelled", "message": "cancelled by stop"}
    runtime.cancelled += 1
    runtime.last_job_id = job.worker_job_id
    runtime.emit(
        "job_finished",
        **_terminal_job_view(job),
        artifact_path=str(job.artifact_path),
    )


def _guard_no_overwrite(args: argparse.Namespace, job_dir: Path) -> None:
    for path in _planned_artifact_paths(args):
        if path.exists():
            raise OscilloscopeError(f"output path already exists: {path}")


def _planned_artifact_paths(args: argparse.Namespace) -> list[Path]:
    command = args.command
    if command == "capture":
        paths = [Path(args.csv_path), Path(args.meta_path)]
        if args.plot_path is not None:
            paths.append(Path(args.plot_path))
        return paths
    if command == "screenshot":
        if getattr(args, "query_hardcopy", False):
            return []
        return [Path(args.output_path)]
    if command == "capture-batch":
        output_dir = Path(args.output_dir)
        return [output_dir / "manifest.json", output_dir / "scpi.log"]
    if command == "segmented-capture":
        return [Path(args.output_dir)]
    if command == "measure-log":
        output_dir = Path(args.output_dir)
        return [
            output_dir / "measurements.csv",
            output_dir / "manifest.json",
            output_dir / "scpi.log",
        ]
    if command == "measure-until":
        output_dir = Path(args.output_dir)
        return [
            output_dir / "measurements.csv",
            output_dir / "manifest.json",
            output_dir / "scpi.log",
        ]
    if command == "triggered-measure-loop":
        output_dir = Path(args.output_dir)
        return [
            output_dir / "measurements.csv",
            output_dir / "manifest.json",
            output_dir / "scpi.log",
        ]
    if command == "triggered-capture-series":
        output_dir = Path(args.output_dir)
        return [output_dir / "manifest.json", output_dir / "scpi.log"]
    if command == "smoke":
        output_dir = Path(args.output_dir)
        return [
            output_dir / "report.json",
            output_dir / "scpi.log",
            output_dir / "capture.csv",
            output_dir / "capture_meta.json",
            output_dir / "screen.png",
        ]
    if command == "acquisition-check":
        output_dir = Path(args.output_dir)
        return [output_dir / "report.json", output_dir / "scpi.log"]
    if command == "serial-lister-export":
        return [Path(args.output_path)]
    return []


def _existing_files(files: list[Any]) -> list[Any]:
    existing = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if isinstance(path, str) and Path(path).exists():
            existing.append(entry)
    return existing


def _terminal_job_view(job: WorkerJob) -> dict[str, Any]:
    payload = job.result if isinstance(job.result, dict) else {}
    files = payload.get("files")
    return {
        "worker_job_id": job.worker_job_id,
        "job_id": job.job_id,
        "command": job.command,
        "state": job.state,
        "ok": job.state == "succeeded",
        "exit_code": job.exit_code,
        "result": payload.get("result"),
        "files": _existing_files(files) if isinstance(files, list) else [],
        "error": job.error if job.error is not None else payload.get("error"),
    }


def _job_summary(job: WorkerJob | None) -> dict[str, Any] | None:
    if job is None:
        return None
    summary: dict[str, Any] = {
        "worker_job_id": job.worker_job_id,
        "job_id": job.job_id,
        "command": job.command,
        "state": job.state,
        "artifact_path": str(job.artifact_path),
        "exit_code": job.exit_code,
    }
    if job.state in {"succeeded", "failed", "cancelled"}:
        summary.update(_terminal_job_view(job))
    return summary


def _command_identity(body: Any) -> tuple[str | None, str | None]:
    if not isinstance(body, dict):
        return None, None
    command = body.get("command")
    job_id = body.get("job_id")
    return (
        command if isinstance(command, str) else None,
        job_id if isinstance(job_id, str) else None,
    )


def _command_error_envelope(
    message: str,
    command: str | None,
    job_id: str | None,
    exc: Exception | None = None,
) -> dict[str, Any]:
    return {
        "status": "error",
        "command": command,
        "job_id": job_id,
        "error": "validation_error",
        "message": message,
        "error_detail": {
            "type": type(exc).__name__ if exc is not None else "ValidationError",
            "message": message,
        },
    }


def _command_rejected_envelope(
    reason: str, command: str | None, job_id: str | None
) -> dict[str, Any]:
    return {
        "status": "rejected",
        "command": command,
        "job_id": job_id,
        "reason": reason,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
