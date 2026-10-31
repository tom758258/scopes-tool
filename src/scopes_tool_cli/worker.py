"""Worker server, runtime, and lifecycle implementation."""

from __future__ import annotations

import argparse
from copy import deepcopy
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
from scopes_tool_core.simulator_backend import SimulatorInstrumentState

from . import cli as scope_cli
from . import runtime as cli_runtime
from scopes_tool_core.measure_stream import (
    MeasureStreamOptions, run_measure_stream, validate_measure_stream_options,
)

from .worker_client import (
    client_get,
    client_post,
    client_send_command,
    client_wait_ready,
)
from .worker_commands import (
    DOMAIN_COMMANDS,
    WORKER_FEATURES,
    WORKER_SCHEMA_VERSION,
    _CORE_WORKFLOW_COMMANDS,
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
    request_time: str
    state: str = "queued"
    accepted_time: str | None = None
    started_time: str | None = None
    finished_time: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    exit_code: int | None = None
    cancel_requested: bool = False
    terminal_snapshot: dict[str, Any] | None = field(default=None, init=False)


@dataclass
class WorkerRuntime:
    host: str
    port: int
    mode: str
    model: str
    resource: str | None
    queue_max: int
    output_format: str
    streaming: bool = False
    visa_library: str | None = None
    run_id: str = field(default_factory=lambda: uuid4().hex)
    queue: Queue[WorkerJob] = field(init=False)
    jobs: dict[str, WorkerJob] = field(default_factory=dict)
    simulator_state: SimulatorInstrumentState | None = field(default=None, init=False)
    active_job_id: str | None = None
    last_job_id: str | None = None
    fatal_error: dict[str, Any] | None = None
    stopping: bool = False
    accepted: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    emit_lock: threading.Lock = field(default_factory=threading.Lock)
    stream_state: str | None = None
    stream_started: bool = False
    stream_thread: threading.Thread | None = None
    stream_stop: threading.Event = field(default_factory=threading.Event)
    stream_options: MeasureStreamOptions | None = None
    stream_completed: int = 0
    stream_invalid: int = 0
    stream_reason: str | None = None
    server: ThreadingHTTPServer | None = None

    def __post_init__(self) -> None:
        self.queue = Queue(maxsize=self.queue_max)
        if self.streaming:
            self.stream_state = "waiting"

    def runtime_features(self) -> dict[str, Any]:
        features = deepcopy(WORKER_FEATURES)
        if self.streaming:
            features["common.streaming"] = {
                "contract_version": 1, "lifecycles": ["deferred_start"],
            }
        return features

    def emit(self, event: str, **values: Any) -> None:
        payload = _event_payload(self, event, **values)
        with self.emit_lock:
            if self.output_format == "jsonl":
                print(json.dumps(payload, sort_keys=True, allow_nan=not self.streaming), flush=True)
            else:
                print(f"{event}: {payload}", flush=True)

    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def control_urls(self) -> dict[str, str]:
        return {f"{name}_url": f"{self.base_url()}/{name}"
                for name in ("status", "command", "stop")}

    def status_payload(self) -> dict[str, Any]:
        with self.lock:
            active = self.jobs.get(self.active_job_id) if self.active_job_id else None
            last = self.jobs.get(self.last_job_id) if self.last_job_id else None
            active_snapshot = _job_summary(active, terminal=False)
            last_snapshot = _job_summary(last)
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
        stream = (
            {"stream": {"lifecycle": "deferred_start", "state": self.stream_state}}
            if self.streaming else {}
        )
        return {
            "schema_version": WORKER_SCHEMA_VERSION,
            "service": "scopes-tool",
            "status": "stopping" if self.stopping else "ready",
            "worker_state": "failed" if self.fatal_error is not None else (
                "stopping" if self.stopping else "running"
            ),
            "run_id": self.run_id,
            "mode": self.mode,
            "model": self.model,
            "resource": self.resource,
            "queue": {
                "max": self.queue_max,
                "size": self.queue.qsize(),
                "jobs": queued,
            },
            "active_job": active_snapshot,
            "last_job": last_snapshot,
            **self.control_urls(),
            "urls": self.control_urls(),
            "features": self.runtime_features(),
            "fatal_error": self.fatal_error,
            "timestamp_utc": _now(),
            **stream,
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
    streaming = bool(getattr(args, "streaming", False))
    if streaming and args.format != "jsonl":
        raise OscilloscopeError("streaming worker requires --format jsonl")
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
        queue_max=args.queue_max,
        output_format=args.format,
        visa_library=args.visa_library,
        streaming=streaming,
    )
    handler = _make_handler(runtime)
    try:
        server = ThreadingHTTPServer((args.host, args.port), handler)
    except Exception as exc:
        runtime.fatal_error = _common_error("worker", "startup_failed", str(exc), exc)
        runtime.emit("error", scope="worker", fatal=True, error=runtime.fatal_error)
        runtime.emit("summary", ok=False, fatal_error=runtime.fatal_error, exit_code=3)
        return 3
    summary_emitted = False
    try:
        runtime.port = server.server_port
        runtime.server = server
        worker_thread = threading.Thread(target=_job_loop, args=(runtime,), daemon=True)
        worker_thread.start()
        runtime.emit("ready")
        if runtime.streaming:
            runtime.emit("status")
        server.serve_forever()
    except KeyboardInterrupt:
        runtime.stopping = True
        runtime.fatal_error = _common_error("worker", "interrupted", "interrupted")
        runtime.emit("summary", ok=False, fatal_error=runtime.fatal_error, exit_code=130)
        summary_emitted = True
        return 130
    except Exception as exc:
        runtime.fatal_error = _common_error("worker", "worker_failed", str(exc), exc)
        runtime.emit("error", scope="worker", fatal=True, error=runtime.fatal_error)
        runtime.emit("summary", ok=False, fatal_error=runtime.fatal_error, exit_code=3)
        summary_emitted = True
        return 3
    finally:
        try:
            server.server_close()
        except Exception as exc:
            runtime.fatal_error = _common_error("worker", "cleanup_failed", str(exc), exc)
            runtime.emit("error", scope="worker", fatal=True, error=runtime.fatal_error)
            if not summary_emitted:
                runtime.emit("summary", ok=False, fatal_error=runtime.fatal_error, exit_code=3)
            return 3
    runtime.queue.join()
    if runtime.streaming:
        runtime.stream_stop.set()
        if runtime.stream_thread is not None:
            runtime.stream_thread.join(timeout=30)
            if runtime.stream_thread.is_alive():
                runtime.fatal_error = _common_error(
                    "worker", "stream_stop_timeout",
                    "stream query did not stop within the bounded shutdown window",
                )
                runtime.emit("error", scope="worker", fatal=True, error=runtime.fatal_error)
        elif runtime.stream_state != "ended":
            _mark_stream_ended(runtime, "stopped_before_start")
    runtime.emit(
        "summary",
        ok=runtime.fatal_error is None,
        fatal_error=runtime.fatal_error,
        exit_code=0 if runtime.fatal_error is None else 3,
        **({
            "stream_summary": {
                "completed_cycles": runtime.stream_completed,
                "expected_cycles": (
                    runtime.stream_options.count if runtime.stream_options else None
                ),
                "invalid_measurements": runtime.stream_invalid,
                "stop_reason": runtime.stream_reason,
                "data_integrity": (
                    "unknown" if runtime.stream_options is None
                    else "incomplete" if runtime.fatal_error is not None or (
                        runtime.stream_options is not None
                        and runtime.stream_options.count is not None
                        and runtime.stream_completed < runtime.stream_options.count
                    ) else "no_loss_detected"
                ),
            },
        } if runtime.streaming else {}),
    )
    return 0 if runtime.fatal_error is None else 3


def _make_handler(runtime: WorkerRuntime):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            print(fmt % args, file=sys.stderr, flush=True)

        def do_GET(self) -> None:
            if self.path != "/status":
                self._send(404, {"status": "error", "error": _common_error(
                    "validation", "not_found", "not found"
                )})
                return
            try:
                self._send(200, runtime.status_payload())
            except Exception as exc:
                self._send(500, {"status": "error", "error": _common_error(
                    "worker", "status_failed", str(exc), exc
                )})
                return

        def do_POST(self) -> None:
            if self.path == "/command":
                self._handle_command()
                return
            if self.path == "/stop":
                self._handle_stop()
                return
            self._send(404, {"status": "error", "error": _common_error(
                "validation", "not_found", "not found"
            )})

        def _handle_command(self) -> None:
            command_echo: str | None = None
            job_id_echo: str | None = None
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                body = json.loads(raw.decode("utf-8") if raw else "{}")
                command_echo, job_id_echo = _command_identity(body)
                command, arguments, job_id = validate_command_request(body)
                if command == "measure-stream-start":
                    if not runtime.streaming:
                        raise OscilloscopeError("measure-stream-start requires --streaming")
                    stream_options = validate_measure_stream_options(
                        arguments, capabilities_for_model_id(runtime.model),
                    )
                else:
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
            except (OscilloscopeError, UnicodeError, ValueError) as exc:
                self._send(
                    400,
                    _command_error_envelope(str(exc), command_echo, job_id_echo, exc),
                )
                return
            except Exception as exc:
                self._send(500, _command_error_envelope(
                    str(exc), command_echo, job_id_echo, exc,
                    category="worker", code="command_failed",
                ))
                return
            try:
                if command == "measure-stream-start":
                    self._admit_stream_start(command, job_id, stream_options)
                else:
                    self._admit_command(command, arguments, job_id)
            except Exception as exc:
                self._send(500, _command_error_envelope(
                    str(exc), command_echo, job_id_echo, exc,
                    category="worker", code="command_failed",
                ))

        def _admit_stream_start(
            self, command: str, job_id: str | None, options: MeasureStreamOptions,
        ) -> None:
            with runtime.lock:
                if runtime.stopping:
                    reason = "worker_stopping"
                elif runtime.stream_started or runtime.stream_state != "waiting":
                    reason = "stream_already_started"
                elif (
                    runtime.active_job_id is not None
                    or not runtime.queue.empty()
                    or any(job.state in {"queued", "running"} for job in runtime.jobs.values())
                ):
                    reason = "worker_busy"
                else:
                    reason = None
                    runtime.stream_started = True
                    runtime.stream_options = options
            if reason is not None:
                self._send(409, _command_rejected_envelope(
                    reason, command, job_id, kind="control",
                ))
                return
            runtime.stream_thread = threading.Thread(
                target=_stream_loop, args=(runtime,), daemon=True,
            )
            runtime.stream_thread.start()
            self._send(202, {
                "status": "accepted", "command": command, "job_id": job_id,
                "kind": "control", "worker_job_id": None, "error": None,
            })

        def _admit_command(
            self, command: str, arguments: dict[str, Any], job_id: str | None
        ) -> None:
            with runtime.lock:
                if runtime.stopping:
                    reason = "worker_stopping"
                elif runtime.streaming and runtime.stream_started:
                    reason = "stream_owns_session"
                elif runtime.queue.full():
                    reason = "queue_full"
                else:
                    reason = None
                if reason is None:
                    worker_job_id = uuid4().hex
                    job = WorkerJob(
                        command=command, arguments=arguments, job_id=job_id,
                        worker_job_id=worker_job_id, request_time=_now(),
                        accepted_time=_now(),
                    )
                    runtime.jobs[worker_job_id] = job
                    try:
                        runtime.queue.put_nowait(job)
                        runtime.accepted += 1
                    except Full:
                        runtime.jobs.pop(worker_job_id, None)
                        reason = "queue_full"
            if reason is not None:
                self._send(
                    429 if reason == "queue_full" else 409,
                    _command_rejected_envelope(reason, command, job_id),
                )
                return
            self._send(202, {
                "status": "accepted", "command": command, "job_id": job_id,
                "worker_job_id": worker_job_id, "kind": "async_job", "error": None,
            })

        def _handle_stop(self) -> None:
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                body = json.loads(raw.decode("utf-8") if raw else "{}")
                if not isinstance(body, dict):
                    raise OscilloscopeError("stop body must be a JSON object")
                if set(body) - {"schema_version", "reason"}:
                    raise OscilloscopeError("unknown stop request field")
                if "schema_version" in body and (
                    type(body["schema_version"]) is not int
                    or body["schema_version"] != WORKER_SCHEMA_VERSION
                ):
                    raise OscilloscopeError("schema_version must be exactly 3")
                if "reason" in body and not isinstance(body["reason"], str):
                    raise OscilloscopeError("reason must be a string")
            except (OscilloscopeError, UnicodeError, ValueError) as exc:
                self._send(400, {"status": "error", "error": _common_error(
                    "validation", "invalid_stop", str(exc), exc
                )})
                return
            except Exception as exc:
                self._send(500, {"status": "error", "error": _common_error(
                    "worker", "stop_failed", str(exc), exc
                )})
                return
            try:
                cancelled = []
                with runtime.lock:
                    first_stop = not runtime.stopping
                    runtime.stopping = True
                    runtime.stream_stop.set()
                    if first_stop:
                        for job in list(runtime.jobs.values()):
                            if job.state == "queued":
                                _finish_cancelled_job(runtime, job, started=False)
                                cancelled.append(job.worker_job_id)
                            elif job.state == "running":
                                job.cancel_requested = True
            except Exception as exc:
                self._send(500, {"status": "error", "error": _common_error(
                    "worker", "stop_failed", str(exc), exc
                )})
                return
            self._send(
                202,
                {
                    "status": "accepted",
                    "run_id": runtime.run_id,
                    "cancelled_jobs": cancelled,
                    "active_job": runtime.active_job_id,
                    "error": None,
                },
            )
            if runtime.streaming and not runtime.stream_started:
                _mark_stream_ended(runtime, "stopped_before_start")
            if first_stop:
                threading.Thread(target=self.server.shutdown, daemon=True).start()

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            payload = {**payload, "schema_version": WORKER_SCHEMA_VERSION,
                       "run_id": runtime.run_id}
            data = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _mark_stream_ended(runtime: WorkerRuntime, reason: str) -> None:
    with runtime.lock:
        if runtime.stream_state == "ended":
            return
        runtime.stream_state = "ended"
        runtime.stream_reason = reason
    runtime.emit("status")


def _stream_loop(runtime: WorkerRuntime) -> None:
    options = runtime.stream_options
    if options is None:
        return
    if runtime.stream_stop.is_set():
        _mark_stream_ended(runtime, "stopped_before_start")
        return
    args = argparse.Namespace(
        command="measure", simulate=runtime.mode == "simulate",
        live=runtime.mode == "live", model=runtime.model,
        resource=runtime.resource, visa_library=runtime.visa_library,
        _worker_live_validation=runtime.mode == "live",
        _simulator_state=runtime.simulator_state,
        _simulator_state_reporter=lambda state: None,
    )
    resource = runtime.resource or f"SIM::{runtime.model}::INSTR"
    try:
        with cli_runtime._open_scope(args, resource) as scope:
            scope.query_idn()
            with runtime.lock:
                can_activate = not runtime.stopping and not runtime.stream_stop.is_set()
                if can_activate:
                    runtime.stream_state = "active"
            if not can_activate:
                _mark_stream_ended(runtime, "stop_requested")
                return
            runtime.emit("status")

            def report_sample(sample: dict[str, Any]) -> None:
                runtime.emit("sample", **sample)
                with runtime.lock:
                    runtime.stream_completed = int(sample["index"])
                    runtime.stream_invalid += sum(
                        not value["valid"] for value in sample["values"].values()
                    )

            _count, _invalid, reason = run_measure_stream(
                scope, options, stop_requested=runtime.stream_stop.is_set,
                wait_or_stop=runtime.stream_stop.wait,
                sample_reporter=report_sample,
            )
        _mark_stream_ended(runtime, reason)
    except Exception as exc:
        runtime.fatal_error = _common_error("worker", "stream_failed", str(exc), exc)
        runtime.emit("error", scope="worker", fatal=True, error=runtime.fatal_error)
        _mark_stream_ended(runtime, "error")
        if runtime.server is not None:
            threading.Thread(target=runtime.server.shutdown, daemon=True).start()


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
            parsed = parse_domain_command(job.command, job.arguments, runtime)
            _guard_no_overwrite(parsed)
            simulator_states: list[SimulatorInstrumentState] = []
            if runtime.mode == "simulate":
                def report_simulator_state(state: SimulatorInstrumentState) -> None:
                    if state.physical_model_id != runtime.model:
                        raise OscilloscopeError(
                            "Simulator state model does not match the Worker model: "
                            f"{state.physical_model_id!r} != {runtime.model!r}."
                        )
                    simulator_states.append(state)

                parsed._simulator_state = runtime.simulator_state
                parsed._simulator_state_reporter = report_simulator_state
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
            if job.state == "succeeded" and simulator_states:
                runtime.simulator_state = simulator_states[-1]
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
                if job.state == "succeeded":
                    runtime.succeeded += 1
                elif job.state == "cancelled":
                    runtime.cancelled += 1
                else:
                    runtime.failed += 1
                _retain_terminal_job(runtime, job)
            runtime.emit(
                "job_finished",
                **_terminal_job_view(job),
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
    if command == "segmented-capture" and status in {"partial", "failed"}:
        return str(status)
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
                **runtime.control_urls(),
                "features": runtime.runtime_features(),
                **({"stream": {"lifecycle": "deferred_start"}} if runtime.streaming else {}),
            }
        )
        payload.pop("trigger_url", None)
    elif event == "status":
        payload.update(runtime.status_payload())
    elif event == "job_started":
        job = runtime.jobs.get(str(payload.get("worker_job_id")))
        payload.setdefault("job_id", None if job is None else job.job_id)
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


def _retain_terminal_job(runtime: WorkerRuntime, job: WorkerJob) -> None:
    _terminal_job_view(job)
    previous_id = runtime.last_job_id
    if previous_id is not None and previous_id != job.worker_job_id:
        previous = runtime.jobs.get(previous_id)
        if (
            previous is not None
            and previous.state in {"succeeded", "failed", "cancelled"}
            and previous_id != runtime.active_job_id
        ):
            del runtime.jobs[previous_id]
    runtime.last_job_id = job.worker_job_id


def _finish_cancelled_job(
    runtime: WorkerRuntime, job: WorkerJob, *, started: bool
) -> None:
    job.state = "cancelled"
    job.started_time = job.started_time if started else None
    job.finished_time = _now()
    job.exit_code = 3
    job.error = {"type": "cancelled", "message": "cancelled by stop"}
    runtime.cancelled += 1
    _retain_terminal_job(runtime, job)
    runtime.emit(
        "job_finished",
        **_terminal_job_view(job),
    )


def _guard_no_overwrite(args: argparse.Namespace) -> None:
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
    if command == "capture-until":
        output_dir = Path(args.output_dir)
        return [output_dir / "manifest.json", output_dir / "scpi.log"]
    if command == "capture-monitor":
        if getattr(args, "no_save", False):
            return []
        output_dir = Path(args.output_dir)
        return [
            output_dir / "retained_waveforms.csv",
            output_dir / "manifest.json",
            output_dir / "scpi.log",
        ]
    if command == "measure-log":
        if getattr(args, "no_save", False):
            return []
        output_dir = Path(args.output_dir)
        return [
            output_dir / "measurements.csv",
            output_dir / "manifest.json",
            output_dir / "scpi.log",
        ]
    if command == "measure-until":
        if getattr(args, "no_save", False):
            return []
        output_dir = Path(args.output_dir)
        return [
            output_dir / "measurements.csv",
            output_dir / "manifest.json",
            output_dir / "scpi.log",
        ]
    if command == "triggered-measure-loop":
        if getattr(args, "no_save", False):
            return []
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
    if command == "serial-data":
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
    if job.terminal_snapshot is not None:
        return deepcopy(job.terminal_snapshot)
    payload = job.result if isinstance(job.result, dict) else {}
    files = payload.get("files")
    domain_error = job.error if job.error is not None else payload.get("error")
    error = None
    if job.state != "succeeded":
        message = domain_error.get("message") if isinstance(domain_error, dict) else None
        error = _common_error(
            "execution", "job_cancelled" if job.state == "cancelled" else "job_failed",
            message or f"job {job.state}", domain_error=domain_error,
        )
        if payload.get("error") is not None and payload["error"] != domain_error:
            error["details"]["domain_error"] = deepcopy(payload["error"])
            error["details"]["cancellation_error"] = deepcopy(domain_error)
    snapshot = {
        "worker_job_id": job.worker_job_id,
        "job_id": job.job_id,
        "command": job.command,
        "state": job.state,
        "timestamp_utc": job.finished_time or _now(),
        "ok": job.state == "succeeded",
        "exit_code": job.exit_code,
        "result": payload.get("result"),
        "files": _existing_files(files) if isinstance(files, list) else [],
        "error": error,
    }
    if job.state == "succeeded" and domain_error is not None:
        snapshot["domain_error"] = deepcopy(domain_error)
    job.terminal_snapshot = deepcopy(snapshot)
    return snapshot


def _job_summary(job: WorkerJob | None, *, terminal: bool = True) -> dict[str, Any] | None:
    if job is None:
        return None
    state = job.state
    if not terminal and state not in {"queued", "running"}:
        return None
    summary: dict[str, Any] = {
        "worker_job_id": job.worker_job_id,
        "job_id": job.job_id,
        "command": job.command,
        "state": state,
        "timestamp_utc": job.started_time or job.accepted_time or job.request_time,
        "exit_code": job.exit_code,
    }
    if terminal and state in {"succeeded", "failed", "cancelled"}:
        return deepcopy(job.terminal_snapshot)
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
    *, category: str = "validation", code: str = "validation_error",
) -> dict[str, Any]:
    return {
        "status": "error",
        "command": command,
        "job_id": job_id,
        "kind": (
            "control" if command == "measure-stream-start"
            else "async_job" if command in DOMAIN_COMMANDS else None
        ),
        "worker_job_id": None,
        "error": _common_error(category, code, message, exc),
        "message": message,
        "error_detail": {
            "type": type(exc).__name__ if exc is not None else "ValidationError",
            "message": message,
        },
    }


def _command_rejected_envelope(
    reason: str, command: str | None, job_id: str | None,
    *, kind: str = "async_job",
) -> dict[str, Any]:
    return {
        "status": "rejected",
        "command": command,
        "job_id": job_id,
        "reason": reason,
        "kind": kind,
        "worker_job_id": None,
        "error": _common_error("admission", reason, reason),
    }


def _common_error(
    category: str, code: str, message: str, exc: Exception | None = None,
    *, domain_error: Any = None,
) -> dict[str, Any]:
    details = {}
    if domain_error is not None:
        details["domain_error"] = deepcopy(domain_error)
    elif exc is not None:
        details["domain_error"] = {"type": type(exc).__name__, "message": str(exc)}
    return {"category": category, "code": code,
            "message": message or code, "details": details}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
