import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import queue
from http.server import ThreadingHTTPServer
import subprocess
import sys
import textwrap
import threading
from urllib import error as urlerror
from urllib import request as urlrequest

import pytest

from scopes_tool_cli import cli, runtime as cli_runtime
from scopes_tool_cli import worker, worker_client
from scopes_tool_core.advanced import trigger_holdoff_commands, trigger_holdoff_query
from scopes_tool_core.acquisition import (
    acquisition_points_query,
    record_length_query,
    sample_rate_maximum_query,
    sample_rate_query,
)
from scopes_tool_core.capabilities import (
    capabilities_for_model,
    capabilities_for_model_id,
)
from scopes_tool_core.channel import (
    channel_impedance_command,
    channel_impedance_query,
    channel_invert_command,
    channel_invert_query,
    channel_probe_skew_command,
    channel_probe_skew_query,
    channel_range_command,
    channel_range_query,
    channel_units_command,
    channel_units_query,
    channel_vernier_command,
    channel_vernier_query,
)
from scopes_tool_core.display import (
    display_clear_command,
    display_intensity_command,
    display_intensity_query,
    display_persistence_command,
    display_persistence_query,
    display_vectors_command,
    display_vectors_query,
)
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.idn import parse_idn
from scopes_tool_core.trigger import (
    OPERATION_CONDITION_RUN_MASK,
    force_trigger_command,
    operation_condition_query,
    single_command,
)


def _runtime(
    artifact_root=Path("data/worker"),
    queue_max=32,
    model="keysight-dsox4024a",
):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model=model,
        resource=None,
        artifact_root=Path(artifact_root),
        queue_max=queue_max,
        output_format="jsonl",
    )


def _live_runtime(artifact_root=Path("data/worker")):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="live",
        model="keysight-dsox4024a",
        resource="USB0::FAKE::INSTR",
        artifact_root=Path(artifact_root),
        queue_max=32,
        output_format="jsonl",
    )


def test_live_worker_requires_explicit_resource():
    args = argparse.Namespace(
        simulate=False,
        host="127.0.0.1",
        port=0,
        model="keysight-dsox4024a",
        resource=None,
        artifact_root="data/worker",
        queue_max=32,
        format="jsonl",
    )

    with pytest.raises(OscilloscopeError, match="worker --live requires --resource"):
        worker.run_worker(args)


def test_worker_startup_rejects_unregistered_canonical_model_id():
    args = argparse.Namespace(
        simulate=True,
        host="127.0.0.1",
        port=0,
        model="keysight-dsox4054a",
        resource=None,
        artifact_root="data/worker",
        queue_max=32,
        format="jsonl",
    )

    with pytest.raises(OscilloscopeError, match="model ID"):
        worker.run_worker(args)


@contextmanager
def _worker_server(runtime):
    server = ThreadingHTTPServer(("127.0.0.1", 0), worker._make_handler(runtime))
    runtime.port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield runtime
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _post_command(runtime, body, *, raw=False, add_schema=True):
    if not raw and add_schema and isinstance(body, dict):
        body = {**body, "schema_version": worker.WORKER_SCHEMA_VERSION}
    data = body if raw else json.dumps(body).encode("utf-8")
    req = urlrequest.Request(
        f"http://127.0.0.1:{runtime.port}/command",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlrequest.urlopen(req, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _wait_event_from_queue(events, event_backlog, name, *, predicate=None, timeout=1):
    import time

    deadline = time.monotonic() + timeout
    while True:
        for index, event in enumerate(event_backlog):
            if event.get("event") != name:
                continue
            if predicate is not None and not predicate(event):
                continue
            return event_backlog.pop(index)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(name)

        try:
            event = events.get(timeout=min(0.2, remaining))
        except queue.Empty:
            continue

        if event.get("event") == name and (
            predicate is None or predicate(event)
        ):
            return event

        event_backlog.append(event)


def _run_fake_worker_lifecycle(script, *, ready_timeout=1):
    events = queue.Queue()
    event_backlog = []
    stderr_lines = []
    ready = None
    summary = None
    workflow_error = None
    proc = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def read_stdout():
        assert proc.stdout is not None
        for line in proc.stdout:
            events.put(json.loads(line))

    def read_stderr():
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_lines.append(line.rstrip())

    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    try:
        ready = _wait_event_from_queue(events, event_backlog, "ready", timeout=ready_timeout)
        assert ready["event"] == "ready"
    except Exception as exc:
        workflow_error = exc
    finally:
        if ready is not None:
            try:
                summary = _wait_event_from_queue(
                    events,
                    event_backlog,
                    "summary",
                    timeout=1,
                )
            except TimeoutError:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)

    workflow_failed = (
        workflow_error is not None
        or ready is None
        or summary is None
        or summary.get("event") != "summary"
        or summary.get("run_id") != ready["run_id"]
        or summary.get("ok") is not True
        or summary.get("failed") != 0
        or summary.get("cancelled") != 0
        or proc.returncode != 0
    )
    if workflow_failed:
        raise RuntimeError(
            "worker workflow failed: "
            f"error={workflow_error!r} "
            f"summary={summary} "
            f"worker.returncode={proc.returncode} "
            f"stderr_tail={stderr_lines[-20:]}"
        )
    return ready, summary, stderr_lines


def test_worker_request_rejects_unknown_top_level_field():
    with pytest.raises(OscilloscopeError, match="unknown request field"):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": "identify",
                "arguments": {},
                "extra": True,
            }
        )


def test_worker_request_rejects_unknown_command():
    with pytest.raises(OscilloscopeError, match="unknown command"):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": "list-resources",
                "arguments": {},
            }
        )


@pytest.mark.parametrize(
    "body",
    (
        {"command": "identify", "arguments": {}},
        {"schema_version": 1, "command": "identify", "arguments": {}},
        {"schema_version": "2", "command": "identify", "arguments": {}},
        {"schema_version": 2.0, "command": "identify", "arguments": {}},
        {"schema_version": True, "command": "identify", "arguments": {}},
        {"schema_version": None, "command": "identify", "arguments": {}},
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "identify",
            "arguments": {},
            "context": {},
        },
    ),
)
def test_worker_http_rejects_non_v2_requests_before_side_effects(tmp_path, body):
    runtime = _runtime(tmp_path)
    with _worker_server(runtime):
        status, payload = _post_command(runtime, body, add_schema=False)

    assert status == 400
    assert payload["schema_version"] == worker.WORKER_SCHEMA_VERSION
    assert payload["status"] == "error"
    assert runtime.accepted == 0
    assert runtime.jobs == {}
    assert not any(tmp_path.iterdir())


def test_worker_screenshot_accepts_canonical_format_pack_arguments(tmp_path):
    parsed = worker.parse_domain_command(
        "screenshot",
        {
            "format": "bmp8bit",
            "ink_saver": False,
            "palette": "grayscale",
            "layout": "landscape",
        },
        _runtime(tmp_path),
    )

    assert parsed.format == "bmp8bit"
    assert parsed.ink_saver is False
    assert parsed.palette == "grayscale"
    assert parsed.layout == "landscape"


@pytest.mark.parametrize(
    "arguments",
    [
        {"image_format": "png"},
        {"format": 1},
        {"ink_saver": "false"},
        {"query_hardcopy": False},
        {"query_hardcopy": True, "output": "screen.png"},
    ],
)
def test_worker_screenshot_rejects_noncanonical_arguments_before_artifacts(
    tmp_path, arguments
):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("screenshot", arguments, runtime)

    assert not any(tmp_path.iterdir())


def test_worker_screenshot_query_has_no_artifact_path(tmp_path):
    job_dir = tmp_path / "job"
    parsed = worker.parse_domain_command(
        "screenshot",
        {"query_hardcopy": True},
        _runtime(tmp_path),
        job_dir,
    )

    assert parsed.query_hardcopy is True
    assert worker._planned_artifact_paths(parsed) == []


@pytest.mark.parametrize(
    "command",
    (
        "holdoff",
        "trigger-hold-off",
        "trigger_holdoff",
        "trigger-holdoff-random",
        "trigger-holdoff-minimum",
        "trigger-holdoff-maximum",
    ),
)
def test_worker_request_rejects_trigger_holdoff_command_aliases(command):
    with pytest.raises(OscilloscopeError, match="unknown command"):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": command,
                "arguments": {},
            }
        )


def test_worker_request_rejects_non_object_arguments():
    with pytest.raises(OscilloscopeError, match="arguments"):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": "identify",
                "arguments": [],
            }
        )


@pytest.mark.parametrize(
    "command,arguments",
    (
        ("sample-rate", {"query": True}),
        ("sample-rate", {"query": True, "maximum": True}),
        ("acquisition-points", {"query": True}),
        ("record-length", {"query": True}),
        ("force-trigger", {}),
        ("channel-label", {"channel": 1, "text": "Input A"}),
        ("channel-label", {"channel": 1, "query": True}),
        ("channel-impedance", {"channel": 1, "query": True}),
        (
            "channel-impedance",
            {"channel": 1, "impedance": "fifty", "allow_50_ohm": True},
        ),
        ("channel-invert", {"channel": 1, "off": True}),
        ("channel-range", {"channel": 1, "volts_full_scale": 4}),
        ("channel-units", {"channel": 1, "units": "amp"}),
        ("channel-vernier", {"channel": 1, "on": True}),
        ("channel-probe-skew", {"channel": 1, "seconds": 1e-9}),
        ("display-label", {"off": True}),
        ("display-label", {"query": True}),
        ("display-clear", {}),
        ("display-persistence", {"query": True}),
        ("display-persistence", {"mode": "minimum"}),
        ("display-persistence", {"seconds": 0.5}),
        ("display-intensity", {"query": True}),
        ("display-intensity", {"value": 75}),
        ("display-vectors", {"query": True}),
        ("display-vectors", {"on": True}),
        ("annotation", {"slot": 1, "query": True}),
        ("trigger-edge", {"query": True}),
        ("trigger-delay", {"query": True}),
        ("trigger-setup-hold", {"query": True}),
        ("trigger-edge-burst", {"query": True}),
        ("trigger-tv", {"query": True}),
        ("trigger-sweep", {"query": True}),
        ("trigger-noise-reject", {"query": True}),
        ("trigger-hf-reject", {"query": True}),
    ),
)
def test_worker_request_accepts_trigger_and_acquisition_queries(command, arguments):
    assert worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": command,
            "arguments": arguments,
            "job_id": "job-1",
        }
    ) == (command, arguments, "job-1")


def test_command_acceptance_returns_common_envelope_without_bookkeeping_files(tmp_path):
    runtime = _runtime(tmp_path)
    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {"command": "identify", "arguments": {}, "job_id": "job-1"},
        )

    assert status == 202
    assert payload["schema_version"] == worker.WORKER_SCHEMA_VERSION
    assert payload["status"] == "accepted"
    assert payload["command"] == "identify"
    assert payload["job_id"] == "job-1"
    assert payload["worker_job_id"]
    assert not list(tmp_path.rglob("request.json"))
    assert not list(tmp_path.rglob("result.json"))


def test_worker_normal_terminal_completion_retains_only_latest_job(tmp_path):
    runtime = _runtime(tmp_path)
    worker_thread = threading.Thread(
        target=worker._job_loop, args=(runtime,), daemon=True
    )
    worker_thread.start()

    with _worker_server(runtime):
        _, first = _post_command(
            runtime, {"command": "identify", "arguments": {}, "job_id": "one"},
        )
        runtime.queue.join()
        _, second = _post_command(
            runtime, {"command": "identify", "arguments": {}, "job_id": "two"},
        )
        runtime.queue.join()
        with urlrequest.urlopen(
            f"http://127.0.0.1:{runtime.port}/status", timeout=2
        ) as response:
            status_payload = json.loads(response.read().decode("utf-8"))

    first_id = first["worker_job_id"]
    second_id = second["worker_job_id"]
    assert runtime.last_job_id == second_id
    assert second_id in runtime.jobs
    assert first_id not in runtime.jobs
    last_job = status_payload["last_job"]
    assert last_job["worker_job_id"] == second_id
    assert last_job["state"] == "succeeded"
    assert last_job["ok"] is True
    assert last_job["result"]["idn"]


def test_worker_stop_cancels_multiple_queued_jobs_safely(tmp_path):
    runtime = _runtime(tmp_path)
    emitted = []

    def record_emit(event, **values):
        emitted.append(worker._event_payload(runtime, event, **values))

    runtime.emit = record_emit
    jobs = []
    for name in ("queued-a", "queued-b"):
        job = worker.WorkerJob(
            command="identify",
            arguments={},
            job_id=name,
            worker_job_id=name,
            artifact_path=tmp_path / "run" / name,
            request_time="now",
        )
        runtime.jobs[name] = job
        jobs.append(job)

    try:
        with _worker_server(runtime):
            request = urlrequest.Request(
                f"http://127.0.0.1:{runtime.port}/stop",
                data=b"{}",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urlrequest.urlopen(request, timeout=2) as response:
                assert response.status == 202
                payload = json.loads(response.read().decode("utf-8"))
    except RuntimeError as exc:
        if "dictionary changed size during iteration" not in str(exc):
            raise
        pytest.fail("/stop mutated runtime.jobs during iteration")

    assert [job for job in jobs if job.state == "cancelled"] == jobs
    assert payload["cancelled_jobs"] == ["queued-a", "queued-b"]
    assert runtime.cancelled == 2
    assert runtime.last_job_id == "queued-b"
    assert "queued-b" in runtime.jobs
    assert "queued-a" not in runtime.jobs
    finished_events = [event for event in emitted if event["event"] == "job_finished"]
    assert len(finished_events) == 2
    for job, event in zip(jobs, finished_events):
        assert event["worker_job_id"] == job.worker_job_id
        assert event["state"] == "cancelled"
        assert event["exit_code"] == 3
        assert event["error"] == {"type": "cancelled", "message": "cancelled by stop"}


def test_command_acceptance_validates_sample_rate_maximum_before_enqueue(tmp_path):
    runtime = _runtime(tmp_path)
    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": "sample-rate",
                "arguments": {"query": True, "maximum": True},
                "job_id": "job-maximum",
            },
        )

    assert status == 202
    assert payload["status"] == "accepted"
    assert payload["command"] == "sample-rate"
    assert payload["job_id"] == "job-maximum"
    assert not list(tmp_path.rglob("request.json"))
    assert not list(tmp_path.rglob("result.json"))


def test_command_acceptance_rejects_sample_rate_maximum_without_query_before_artifact(tmp_path):
    runtime = _runtime(tmp_path)
    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": "sample-rate",
                "arguments": {"maximum": True},
                "job_id": "job-bad",
            },
        )

    assert status == 400
    assert payload["status"] == "error"
    assert payload["command"] == "sample-rate"
    assert payload["job_id"] == "job-bad"
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_accepts_capture_batch_and_injects_job_output_dir(tmp_path):
    runtime = _runtime(tmp_path)
    arguments = {
        "channel": [1],
        "points": 1000,
        "format": "byte",
        "count": 3,
        "interval_seconds": 1,
    }

    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": "capture-batch",
                "arguments": arguments,
                "job_id": "periodic-capture",
            },
        )

    assert status == 202
    assert payload["status"] == "accepted"
    job = runtime.jobs[payload["worker_job_id"]]
    parsed = worker.parse_domain_command(
        job.command,
        job.arguments,
        runtime,
        job.artifact_path,
    )
    assert parsed.channel == [1]
    assert parsed.points == 1000
    assert parsed.waveform_format == "byte"
    assert parsed.count == 3
    assert parsed.interval_seconds == 1
    assert Path(parsed.output_dir) == job.artifact_path
    assert parsed.log_scpi is False


@pytest.mark.parametrize(
    "arguments",
    (
        {"channel": [1], "count": 3, "output_dir": "foo"},
        {"channel": [1], "count": 3, "log_scpi": True},
    ),
)
def test_worker_rejects_capture_batch_cli_only_arguments_before_artifact(
    tmp_path, arguments
):
    runtime = _runtime(tmp_path)

    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": "capture-batch",
                "arguments": arguments,
                "job_id": "invalid-periodic-capture",
            },
        )

    assert status == 400
    assert payload["status"] == "error"
    assert payload["command"] == "capture-batch"
    assert payload["job_id"] == "invalid-periodic-capture"
    assert payload["error"] == "validation_error"
    assert runtime.accepted == 0
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


@pytest.mark.parametrize("command", ("acquisition-points", "record-length"))
def test_command_acceptance_validates_points_queries_before_enqueue(tmp_path, command):
    runtime = _runtime(tmp_path)
    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": command,
                "arguments": {"query": True},
                "job_id": "job-query",
            },
        )

    assert status == 202
    assert payload["status"] == "accepted"
    assert payload["command"] == command
    assert payload["job_id"] == "job-query"
    assert not list(tmp_path.rglob("request.json"))
    assert not list(tmp_path.rglob("result.json"))


@pytest.mark.parametrize("command", ("acquisition-points", "record-length"))
def test_command_acceptance_rejects_points_queries_without_query_before_artifact(
    tmp_path, command
):
    runtime = _runtime(tmp_path)
    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": command,
                "arguments": {},
                "job_id": "job-bad",
            },
        )

    assert status == 400
    assert payload["status"] == "error"
    assert payload["command"] == command
    assert payload["job_id"] == "job-bad"
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_command_acceptance_rejects_memory_depth_before_artifact(tmp_path):
    runtime = _runtime(tmp_path)
    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": "memory-depth",
                "arguments": {"query": True},
                "job_id": "job-removed",
            },
        )

    assert status == 400
    assert payload["status"] == "error"
    assert payload["command"] == "memory-depth"
    assert payload["job_id"] == "job-removed"
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_correlation_flows_through_events_and_memory(tmp_path):
    runtime = _runtime(tmp_path)
    client_job_id = "client-job-1"
    with _worker_server(runtime):
        status, accepted = _post_command(
            runtime,
            {"command": "identify", "arguments": {}, "job_id": client_job_id},
        )

    worker_job_id = accepted["worker_job_id"]
    assert status == 202
    assert accepted["schema_version"] == worker.WORKER_SCHEMA_VERSION
    assert accepted["status"] == "accepted"
    assert accepted["command"] == "identify"
    assert accepted["job_id"] == client_job_id
    assert accepted["artifact_path"]
    assert worker_job_id
    assert worker_job_id != client_job_id
    assert runtime.run_id != worker_job_id

    job = runtime.jobs[worker_job_id]
    job.state = "succeeded"
    job.started_time = "started"
    job.finished_time = "finished"
    job.exit_code = 0
    job.result = {"ok": True, "result": {"idn": {}}, "files": []}
    started = worker._event_payload(
        runtime, "job_started", worker_job_id=worker_job_id, command="identify"
    )
    finished = worker._event_payload(
        runtime,
        "job_finished",
        **worker._terminal_job_view(job),
        artifact_path=accepted["artifact_path"],
    )

    assert started["job_id"] == client_job_id
    assert started["worker_job_id"] == worker_job_id
    assert started["command"] == "identify"
    assert finished["job_id"] == client_job_id
    assert finished["worker_job_id"] == worker_job_id
    assert finished["command"] == "identify"
    assert finished["state"] == "succeeded"
    assert finished["ok"] is True
    assert finished["exit_code"] == 0
    assert finished["result"] == {"idn": {}}
    assert finished["files"] == []
    assert finished["error"] is None
    assert finished["run_id"] == runtime.run_id
    assert not list(Path(accepted["artifact_path"]).rglob("request.json"))
    assert not list(Path(accepted["artifact_path"]).rglob("result.json"))


def test_worker_terminal_result_flows_to_job_finished_and_status_last_job(tmp_path):
    runtime = _runtime(tmp_path)
    emitted = []

    def record_emit(event, **values):
        emitted.append(worker._event_payload(runtime, event, **values))

    runtime.emit = record_emit
    client_job_id = "terminal-result"
    worker_thread = threading.Thread(
        target=worker._job_loop, args=(runtime,), daemon=True
    )
    worker_thread.start()

    with _worker_server(runtime):
        status, accepted = _post_command(
            runtime,
            {"command": "identify", "arguments": {}, "job_id": client_job_id},
        )
        assert status == 202
        runtime.queue.join()
        with urlrequest.urlopen(
            f"http://127.0.0.1:{runtime.port}/status", timeout=2
        ) as response:
            status_payload = json.loads(response.read().decode("utf-8"))

    finished = next(
        event
        for event in emitted
        if event["event"] == "job_finished"
        and event["worker_job_id"] == accepted["worker_job_id"]
    )

    assert finished["schema_version"] == worker.WORKER_SCHEMA_VERSION
    assert finished["command"] == "identify"
    assert finished["state"] == "succeeded"
    assert finished["ok"] is True
    assert finished["exit_code"] == 0
    assert isinstance(finished["result"], dict)
    assert finished["result"]["idn"]
    assert finished["result"]["capabilities"]
    assert finished["files"] == []
    assert finished["error"] is None

    last_job = status_payload["last_job"]
    for field in (
        "worker_job_id",
        "job_id",
        "command",
        "state",
        "ok",
        "exit_code",
        "result",
        "files",
        "error",
    ):
        assert last_job[field] == finished[field]

    assert not list(tmp_path.rglob("request.json"))
    assert not list(tmp_path.rglob("result.json"))


def test_worker_failed_job_exposes_terminal_error_in_status_last_job(
    tmp_path, monkeypatch
):
    runtime = _runtime(tmp_path)

    def failing_execute(_parsed, *, stop_requested=None):
        del stop_requested
        raise OscilloscopeError("simulated instrument failure")

    monkeypatch.setattr(worker.scope_cli, "_execute_json_command", failing_execute)
    _, result = _execute_worker_job(runtime, "identify", {}, tmp_path / "failed")

    assert result["state"] == "failed"
    assert result["ok"] is False
    assert result["exit_code"] == 3
    assert result["result"] is None
    assert result["files"] == []

    last_job = runtime.status_payload()["last_job"]
    assert last_job["state"] == "failed"
    assert last_job["ok"] is False
    assert last_job["exit_code"] == 3
    assert last_job["result"] is None
    assert last_job["files"] == []
    assert last_job["error"] == {
        "type": "OscilloscopeError",
        "message": "simulated instrument failure",
    }


@pytest.mark.parametrize(
    ("body", "expected_command", "expected_job_id"),
    (
        (b"{", None, None),
        ([], None, None),
        ({"command": "identify", "arguments": {}, "extra": True}, "identify", None),
        ({"command": "list-resources", "arguments": {}, "job_id": "job-2"}, "list-resources", "job-2"),
        ({"command": "identify", "arguments": {}, "job_id": 7}, "identify", None),
    ),
)
def test_command_validation_errors_use_common_echo_rules(
    tmp_path, body, expected_command, expected_job_id
):
    runtime = _runtime(tmp_path)
    with _worker_server(runtime):
        status, payload = _post_command(runtime, body, raw=isinstance(body, bytes))

    assert status == 400
    assert payload["schema_version"] == worker.WORKER_SCHEMA_VERSION
    assert payload["status"] == "error"
    assert payload["command"] == expected_command
    assert payload["job_id"] == expected_job_id
    assert payload["error"] == "validation_error"
    assert not any(tmp_path.iterdir())


def test_queue_full_rejection_uses_rejected_reason(tmp_path):
    runtime = _runtime(tmp_path, queue_max=1)
    runtime.queue.put_nowait(
        worker.WorkerJob(
            command="identify",
            arguments={},
            job_id=None,
            worker_job_id="queued",
            artifact_path=tmp_path / "queued",
            request_time="now",
        )
    )

    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {"command": "identify", "arguments": {}, "job_id": "job-3"},
        )

    assert status == 429
    assert payload == {
        "schema_version": worker.WORKER_SCHEMA_VERSION,
        "status": "rejected",
        "command": "identify",
        "job_id": "job-3",
        "reason": "queue_full",
    }


def test_worker_http_rejects_invalid_capture_wait_trigger_before_artifacts(tmp_path):
    runtime = _runtime(tmp_path)

    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": "capture",
                "arguments": {"channel": [1], "wait_trigger": True},
                "job_id": "bad-wait",
            },
        )

    assert status == 400
    assert payload["command"] == "capture"
    assert "--trigger-timeout-ms is required" in payload["message"]
    assert not list(tmp_path.rglob("request.json"))


@pytest.mark.parametrize(
    "arguments",
    (
        {"segments": 2},
        {"channel": 1},
        {"channel": True, "segments": 2},
        {"channel": 1, "segments": 2.0},
        {"channel": 1, "segments": 1001},
        {"channel": 5, "segments": 2},
        {"channel": 1, "segments": 2, "points": "1000"},
        {"channel": 1, "segments": 2, "format": "BYTE"},
        {"channel": 1, "segments": 2, "format": 1},
        {"channel": 1, "segments": 2, "timeout_ms": 0},
        {"channel": 1, "segments": 2, "poll_interval_ms": False},
        {"channel": 1, "segments": 2, "output_dir": "out"},
        {"channel": 1, "segments": 2, "resource": "USB0::FAKE::INSTR"},
        {"channel": 1, "segments": 2, "firmware": "07.30"},
    ),
)
def test_worker_http_rejects_invalid_segmented_capture_before_artifacts(
    tmp_path, arguments
):
    runtime = _runtime(tmp_path)

    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": "segmented-capture",
                "arguments": arguments,
                "job_id": "bad-segmented-capture",
            },
        )

    assert status == 400
    assert payload["status"] == "error"
    assert payload["command"] == "segmented-capture"
    assert runtime.accepted == 0
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()
    assert not list(tmp_path.rglob("request.json"))


def test_worker_http_rejects_fifty_ohm_without_allow_before_artifacts(tmp_path):
    runtime = _runtime(tmp_path, model="keysight-dsox3024a")

    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": "channel-impedance",
                "arguments": {"channel": 1, "impedance": "fifty"},
                "job_id": "bad-impedance",
            },
        )

    assert status == 400
    assert payload["status"] == "error"
    assert payload["command"] == "channel-impedance"
    assert payload["job_id"] == "bad-impedance"
    assert "--allow-50-ohm" in payload["message"]
    assert runtime.jobs == {}
    assert not list(tmp_path.rglob("request.json"))


@pytest.mark.parametrize(
    ("command", "arguments", "model", "expected_message"),
    (
        (
            "annotation",
            {"query": True, "text": "bad"},
            "keysight-dsox4024a",
            "--query cannot be combined",
        ),
        (
            "annotation",
            {"text": "Note", "x": 10},
            "keysight-dsox3024a",
            "annotation x is supported only",
        ),
        (
            "annotation",
            {"text": "x" * 255},
            "keysight-dsox4024a",
            "annotation text must be at most 254 characters",
        ),
        (
            "channel-label",
            {"channel": 1, "text": "12345678901"},
            "keysight-dsox3024a",
            "channel label must be at most 10 characters",
        ),
    ),
)
def test_worker_http_rejects_invalid_label_and_annotation_before_artifacts(
    tmp_path, command, arguments, model, expected_message
):
    runtime = _runtime(tmp_path, model=model)

    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {"command": command, "arguments": arguments, "job_id": "bad-label"},
        )

    assert status == 400
    assert payload["status"] == "error"
    assert payload["command"] == command
    assert payload["job_id"] == "bad-label"
    assert expected_message in payload["message"]
    assert runtime.jobs == {}
    assert not list(tmp_path.rglob("request.json"))


def test_worker_http_rejects_invalid_display_common_before_artifacts(tmp_path):
    runtime = _runtime(tmp_path)

    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": "display-vectors",
                "arguments": {"on": False},
                "job_id": "bad-display",
            },
        )

    assert status == 400
    assert payload["status"] == "error"
    assert payload["command"] == "display-vectors"
    assert payload["job_id"] == "bad-display"
    assert "must be exactly true" in payload["message"]
    assert runtime.jobs == {}
    assert not list(tmp_path.rglob("request.json"))


def test_worker_parses_domain_arguments_without_opening_backend():
    parsed = worker.parse_domain_command(
        "channel-scale",
        {"channel": 1, "volts_per_division": 0.5},
        _runtime(),
    )

    assert parsed.command == "channel-scale"
    assert parsed.channel == 1
    assert parsed.scale_value == 0.5
    assert parsed.simulate is True
    assert parsed.json_output is True


def test_worker_segmented_capture_minimal_request_uses_cli_defaults(tmp_path):
    original = {"channel": 1, "segments": 2}
    normalized = worker._normalize_segmented_capture_worker_arguments(
        "segmented-capture", original, _runtime(tmp_path)
    )

    assert normalized == {
        "channel": 1,
        "segments": 2,
        "points": 1000,
        "format": "byte",
        "timeout_ms": 30000,
        "poll_interval_ms": 100,
    }
    assert original == {"channel": 1, "segments": 2}
    assert worker._normalize_segmented_capture_worker_arguments(
        "segmented-capture", normalized, _runtime(tmp_path)
    ) == normalized

    parsed = worker.parse_domain_command(
        "segmented-capture", original, _runtime(tmp_path)
    )
    assert parsed.channel == 1
    assert parsed.segments == 2
    assert parsed.points == 1000
    assert parsed.waveform_format == "byte"
    assert parsed.timeout_ms == 30000
    assert parsed.poll_interval_ms == 100


def test_worker_segmented_capture_full_request_maps_to_cli_namespace(tmp_path):
    parsed = worker.parse_domain_command(
        "segmented-capture",
        {
            "channel": 1,
            "segments": 2,
            "points": 5000,
            "format": "word",
            "timeout_ms": 5000,
            "poll_interval_ms": 50,
        },
        _runtime(tmp_path),
    )

    assert parsed.channel == 1
    assert parsed.segments == 2
    assert parsed.points == 5000
    assert parsed.waveform_format == "word"
    assert parsed.timeout_ms == 5000
    assert parsed.poll_interval_ms == 50
    assert parsed.output_dir is None


def test_worker_parses_sample_rate_query_without_opening_backend():
    parsed = worker.parse_domain_command(
        "sample-rate",
        {"query": True},
        _runtime(),
    )

    assert parsed.command == "sample-rate"
    assert parsed.sample_rate_query is True
    assert parsed.simulate is True
    assert parsed.json_output is True


def test_worker_parses_sample_rate_maximum_query_without_opening_backend():
    parsed = worker.parse_domain_command(
        "sample-rate",
        {"query": True, "maximum": True},
        _runtime(),
    )

    assert parsed.command == "sample-rate"
    assert parsed.sample_rate_query is True
    assert parsed.sample_rate_maximum is True
    assert parsed.simulate is True
    assert parsed.json_output is True


def test_worker_request_rejects_removed_memory_depth_command():
    with pytest.raises(OscilloscopeError, match="unknown command: memory-depth"):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": "memory-depth",
                "arguments": {"query": True},
            }
        )


def test_worker_parses_acquisition_points_query_without_opening_backend():
    parsed = worker.parse_domain_command(
        "acquisition-points",
        {"query": True},
        _runtime(),
    )

    assert parsed.command == "acquisition-points"
    assert parsed.acquisition_points_query_flag is True
    assert parsed.simulate is True
    assert parsed.json_output is True


def test_worker_parses_record_length_query_without_opening_backend():
    parsed = worker.parse_domain_command(
        "record-length",
        {"query": True},
        _runtime(),
    )

    assert parsed.command == "record-length"
    assert parsed.record_length_query_flag is True
    assert parsed.simulate is True
    assert parsed.json_output is True


def test_worker_parses_force_trigger_without_opening_backend():
    parsed = worker.parse_domain_command(
        "force-trigger",
        {},
        _runtime(),
    )

    assert parsed.command == "force-trigger"
    assert parsed.simulate is True
    assert parsed.json_output is True


def test_worker_parses_fifty_ohm_with_allow_without_opening_backend():
    parsed = worker.parse_domain_command(
        "channel-impedance",
        {"channel": 1, "impedance": "fifty", "allow_50_ohm": True},
        _runtime(model="keysight-dsox3024a"),
    )

    assert parsed.command == "channel-impedance"
    assert parsed.channel == 1
    assert parsed.impedance_value == "fifty"
    assert parsed.allow_50_ohm is True
    assert parsed.simulate is True
    assert parsed.json_output is True


@pytest.mark.parametrize(
    ("command", "arguments", "model", "expected_scpi"),
    (
        (
            "channel-label",
            {"channel": 1, "text": "Input A"},
            "keysight-dsox4024a",
            [':CHANnel1:LABel "Input A"', ":SYSTem:ERRor?"],
        ),
        (
            "channel-label",
            {"channel": 1, "query": True},
            "keysight-dsox4024a",
            [":CHANnel1:LABel?", ":SYSTem:ERRor?"],
        ),
        (
            "display-label",
            {"off": True},
            "keysight-dsox4024a",
            [":DISPlay:LABel OFF", ":SYSTem:ERRor?"],
        ),
        (
            "display-label",
            {"query": True},
            "keysight-dsox4024a",
            [":DISPlay:LABel?", ":SYSTem:ERRor?"],
        ),
        (
            "annotation",
            {
                "slot": 2,
                "on": True,
                "text": "Run note",
                "color": "white",
                "background": "opaque",
                "x": 10,
                "y": 20,
            },
            "keysight-dsox4024a",
            [
                ':DISPlay:ANNotation2:TEXT "Run note"',
                ":DISPlay:ANNotation2:COLor WHITE",
                ":DISPlay:ANNotation2:BACKground OPAQ",
                ":DISPlay:ANNotation2:X1Position 10",
                ":DISPlay:ANNotation2:Y1Position 20",
                ":DISPlay:ANNotation2 ON",
                ":SYSTem:ERRor?",
            ],
        ),
        (
            "annotation",
            {"slot": 2, "query": True},
            "keysight-dsox4024a",
            [
                ":DISPlay:ANNotation2?",
                ":DISPlay:ANNotation2:TEXT?",
                ":DISPlay:ANNotation2:COLor?",
                ":DISPlay:ANNotation2:BACKground?",
                ":DISPlay:ANNotation2:X1Position?",
                ":DISPlay:ANNotation2:Y1Position?",
                ":SYSTem:ERRor?",
            ],
        ),
        (
            "annotation",
            {"query": True},
            "keysight-dsox3024a",
            [
                ":DISPlay:ANNotation?",
                ":DISPlay:ANNotation:TEXT?",
                ":DISPlay:ANNotation:COLor?",
                ":DISPlay:ANNotation:BACKground?",
                ":SYSTem:ERRor?",
            ],
        ),
        (
            "channel-impedance",
            {"channel": 1, "query": True},
            "keysight-dsox4024a",
            [channel_impedance_query(1), ":SYSTem:ERRor?"],
        ),
        (
            "channel-impedance",
            {"channel": 1, "impedance": "fifty", "allow_50_ohm": True},
            "keysight-dsox3024a",
            [channel_impedance_command(1, "fifty"), ":SYSTem:ERRor?"],
        ),
        (
            "channel-invert",
            {"channel": 1, "on": True},
            "keysight-dsox4024a",
            [channel_invert_command(1, True), ":SYSTem:ERRor?"],
        ),
        (
            "channel-invert",
            {"channel": 1, "query": True},
            "keysight-dsox4024a",
            [channel_invert_query(1), ":SYSTem:ERRor?"],
        ),
        (
            "channel-range",
            {"channel": 1, "volts_full_scale": 4},
            "keysight-dsox4024a",
            [channel_range_command(1, 4), ":SYSTem:ERRor?"],
        ),
        (
            "channel-range",
            {"channel": 1, "query": True},
            "keysight-dsox4024a",
            [channel_range_query(1), ":SYSTem:ERRor?"],
        ),
        (
            "channel-units",
            {"channel": 1, "units": "amp"},
            "keysight-dsox4024a",
            [channel_units_command(1, "amp"), ":SYSTem:ERRor?"],
        ),
        (
            "channel-units",
            {"channel": 1, "query": True},
            "keysight-dsox4024a",
            [channel_units_query(1), ":SYSTem:ERRor?"],
        ),
        (
            "channel-vernier",
            {"channel": 1, "off": True},
            "keysight-dsox4024a",
            [channel_vernier_command(1, False), ":SYSTem:ERRor?"],
        ),
        (
            "channel-vernier",
            {"channel": 1, "query": True},
            "keysight-dsox4024a",
            [channel_vernier_query(1), ":SYSTem:ERRor?"],
        ),
        (
            "channel-probe-skew",
            {"channel": 1, "seconds": 1e-9},
            "keysight-dsox4024a",
            [channel_probe_skew_command(1, 1e-9), ":SYSTem:ERRor?"],
        ),
        (
            "channel-probe-skew",
            {"channel": 1, "query": True},
            "keysight-dsox4024a",
            [channel_probe_skew_query(1), ":SYSTem:ERRor?"],
        ),
    ),
)
def test_worker_label_and_annotation_dry_run_plans_scpi_without_opening_backend(
    command, arguments, model, expected_scpi
):
    parsed = worker.parse_domain_command(command, arguments, _runtime(model=model))

    payload = cli._dry_run_payload(parsed)

    assert parsed.command == command
    assert parsed.simulate is True
    assert parsed.json_output is True
    assert payload["schema_version"] == cli.CLI_SCHEMA_VERSION
    assert "timestamp_utc" in payload
    assert payload["scpi"]["planned"] == expected_scpi


def test_worker_parses_capture_wait_trigger_without_opening_backend():
    parsed = worker.parse_domain_command(
        "capture",
        {
            "channel": [1],
            "wait_trigger": True,
            "trigger_timeout_ms": 5000,
            "trigger_poll_interval_ms": 100,
            "force_trigger_on_timeout": True,
        },
        _runtime(),
    )

    assert parsed.command == "capture"
    assert parsed.wait_trigger is True
    assert parsed.trigger_timeout_ms == 5000
    assert parsed.trigger_poll_interval_ms == 100
    assert parsed.force_trigger_on_timeout is True
    assert parsed.simulate is True
    assert parsed.json_output is True


def test_worker_parse_rejects_invalid_domain_arguments():
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(
            "channel-scale",
            {"channel": 9, "volts_per_division": 0.5},
            _runtime(),
        )


@pytest.mark.parametrize("command", ("sample-rate", "acquisition-points", "record-length"))
def test_worker_parse_rejects_query_commands_without_query_flag(command):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, {}, _runtime())


def test_worker_parse_rejects_sample_rate_maximum_without_query_flag():
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("sample-rate", {"maximum": True}, _runtime())


@pytest.mark.parametrize(
    ("command", "arguments"),
    (
        ("display-clear", {"query": True}),
        ("display-persistence", {"unknown": True}),
        ("display-persistence", {"query": False}),
        ("display-persistence", {"query": None}),
        ("display-persistence", {}),
        ("display-persistence", {"query": True, "seconds": 1}),
        ("display-persistence", {"seconds": 60.1}),
        ("display-intensity", {"query": False}),
        ("display-intensity", {}),
        ("display-intensity", {"value": 101}),
        ("display-vectors", {"query": False}),
        ("display-vectors", {"on": None}),
        ("display-vectors", {"off": True}),
        ("display-vectors", {}),
    ),
)
def test_worker_parse_rejects_invalid_display_common_arguments(command, arguments):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, _runtime())


@pytest.mark.parametrize(
    ("command", "alias"),
    (
        ("channel-range", "volts"),
        ("channel-range", "range_volts"),
        ("channel-invert", "invert"),
        ("channel-vernier", "vernier"),
    ),
)
def test_worker_parse_rejects_channel_advanced_aliases(command, alias):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(
            command,
            {"channel": 1, alias: 4},
            _runtime(),
        )


@pytest.mark.parametrize(
    ("command", "arguments"),
    (
        ("channel-invert", {"channel": 1, "on": True, "off": True}),
        ("channel-vernier", {"channel": 1, "on": True, "query": True}),
    ),
)
def test_worker_parse_rejects_invalid_channel_boolean_mutual_exclusions(
    command, arguments
):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, _runtime())


@pytest.mark.parametrize(
    ("arguments", "expected_argv"),
    (
        ({"query": True}, ["--query"]),
        ({"seconds": 1e-6}, ["--seconds", "1e-06"]),
    ),
)
def test_worker_parse_accepts_trigger_holdoff_arguments(arguments, expected_argv):
    parsed = worker.parse_domain_command("trigger-holdoff", arguments, _runtime())

    assert parsed.command == "trigger-holdoff"
    normalized = worker._normalize_trigger_holdoff_worker_arguments(
        "trigger-holdoff", arguments
    )
    assert worker.arguments_to_argv(normalized) == expected_argv


@pytest.mark.parametrize(
    "arguments",
    (
        {},
        {"query": False},
        {"query": True, "seconds": 1e-6},
        {"holdoff": 1e-6},
        {"holdoff_seconds": 1e-6},
        {"time_seconds": 1e-6},
        {"random": True},
        {"minimum": True},
        {"maximum": True},
        {"enabled": True},
        {"mode": "fixed"},
        {"seconds": "1e-6"},
        {"seconds": True},
        {"seconds": None},
        {"seconds": 0},
        {"seconds": 1e-9},
        {"seconds": 11.0},
        {"seconds": float("nan")},
    ),
)
def test_worker_parse_rejects_invalid_trigger_holdoff_arguments(arguments):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("trigger-holdoff", arguments, _runtime())


@pytest.mark.parametrize(
    "body",
    (
        {"command": "trigger-holdoff", "arguments": {}},
        {"command": "trigger-holdoff", "arguments": {"query": False}},
        {"command": "trigger-holdoff", "arguments": {"seconds": "1e-6"}},
        {"command": "trigger-holdoff", "arguments": {"seconds": 1e-9}},
        {"command": "trigger-holdoff", "arguments": {"random": True}},
    ),
)
def test_worker_trigger_holdoff_rejects_before_enqueue_or_artifacts(tmp_path, body):
    runtime = _runtime(tmp_path)

    with _worker_server(runtime):
        status, payload = _post_command(runtime, body)

    assert status == 400
    assert payload["status"] == "error"
    assert payload["command"] == "trigger-holdoff"
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


@pytest.mark.parametrize(
    "arguments",
    (
        {"channel": [1], "wait_trigger": True},
        {"channel": [1], "force_trigger_on_timeout": True},
        {
            "channel": [1],
            "wait_trigger": True,
            "trigger_timeout_ms": 10,
            "trigger_poll_interval_ms": 11,
        },
    ),
)
def test_worker_parse_rejects_invalid_capture_wait_trigger_arguments(arguments):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("capture", arguments, _runtime())


def test_send_command_dry_run_does_not_contact_http(capsys):
    args = argparse.Namespace(
        command="send-command",
        host="127.0.0.1",
        port=9,
        worker_command="identify",
        arguments_json="{}",
        job_id="job-1",
        timeout_ms=1,
        format="json",
        client_json=True,
        dry_run=True,
    )

    assert worker.client_send_command(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "dry_run"
    assert payload["schema_version"] == worker.WORKER_SCHEMA_VERSION
    assert "timestamp_utc" in payload
    assert payload["command"] == "identify"
    assert payload["request"] == {
        "schema_version": worker.WORKER_SCHEMA_VERSION,
        "command": "identify",
        "arguments": {},
        "job_id": "job-1",
    }


def test_send_command_sends_v2_request(monkeypatch, capsys):
    args = argparse.Namespace(
        command="send-command",
        host="127.0.0.1",
        port=8765,
        worker_command="identify",
        arguments_json="{}",
        job_id="job-1",
        timeout_ms=1000,
        format="json",
        client_json=True,
        dry_run=False,
    )
    sent = {}

    def fake_http_request(_args, _path, *, method, body=None):
        sent.update(body or {})
        return {"schema_version": worker.WORKER_SCHEMA_VERSION, "status": "accepted"}, 202

    monkeypatch.setattr(worker_client, "_http_request", fake_http_request)

    assert worker.client_send_command(args) == 0
    json.loads(capsys.readouterr().out)
    assert sent["schema_version"] == worker.WORKER_SCHEMA_VERSION


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"schema_version": None},
        {"schema_version": 1},
        {"schema_version": "2"},
        {"schema_version": 2.0},
        {"schema_version": True},
    ),
)
def test_lifecycle_client_response_validator_rejects_invalid_schema(payload):
    with pytest.raises(OscilloscopeError, match="invalid worker response"):
        worker._validate_client_response(payload)


def test_lifecycle_client_fails_closed_on_invalid_worker_response(
    monkeypatch, capsys
):
    args = argparse.Namespace(
        command="status",
        host="127.0.0.1",
        port=8765,
        timeout_ms=1000,
        format="json",
        client_json=True,
    )

    monkeypatch.setattr(
        worker_client,
        "_http_request",
        lambda *_args, **_kwargs: ({"schema_version": 1, "status": "ready"}, 200),
    )

    assert worker.client_get(args, "/status") == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == worker.WORKER_SCHEMA_VERSION
    assert payload["status"] == "error"


def test_stop_is_lifecycle_command_and_stop_acquisition_is_domain(capsys):
    assert cli.main(["stop", "--port", "9", "--timeout-ms", "1", "--json"]) == 3
    assert cli.main(["stop-acquisition", "--simulate", "--json"]) == 0


def test_lifecycle_fallback_error_uses_cli_schema(monkeypatch, capsys):
    def fail_dispatch(_args):
        raise OscilloscopeError("lifecycle dispatch failed")

    monkeypatch.setattr(worker, "dispatch_lifecycle_command", fail_dispatch)

    assert cli.main(["stop", "--port", "9", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema_version"] == cli.CLI_SCHEMA_VERSION
    assert "timestamp_utc" in payload
    assert payload["ok"] is False
    assert payload["status"] == "error"
    assert payload["error"] == {
        "type": "OscilloscopeError",
        "message": "lifecycle dispatch failed",
    }


def test_direct_json_envelope_has_schema_and_timestamp(capsys):
    assert cli.main(["identify", "--simulate", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema_version"] == cli.CLI_SCHEMA_VERSION
    assert "timestamp_utc" in payload
    assert payload["ok"] is True


def test_worker_event_payloads_have_required_fields(tmp_path):
    runtime = _runtime(tmp_path)
    job = worker.WorkerJob(
        command="identify",
        arguments={},
        job_id="client-job",
        worker_job_id="worker-job",
        artifact_path=tmp_path / "worker-job",
        request_time="now",
    )
    runtime.jobs[job.worker_job_id] = job

    ready = worker._event_payload(runtime, "ready", trigger_url="forbidden")
    started = worker._event_payload(
        runtime, "job_started", worker_job_id=job.worker_job_id, command=job.command
    )
    finished = worker._event_payload(
        runtime,
        "job_finished",
        worker_job_id=job.worker_job_id,
        job_id=job.job_id,
        command=job.command,
        state="failed",
        ok=False,
        exit_code=3,
        result=None,
        files=[],
        artifact_path=str(job.artifact_path),
        error={"type": "x", "message": "y"},
    )
    summary = worker._event_payload(runtime, "summary", ok=True, fatal_error=None)

    for payload in (ready, started, finished, summary):
        assert payload["schema_version"] == worker.WORKER_SCHEMA_VERSION
        assert payload["run_id"] == runtime.run_id
        assert "timestamp_utc" in payload
    assert ready["event"] == "ready"
    assert ready["service"] == "scopes-tool"
    assert ready["host"] == "127.0.0.1"
    assert ready["port"] == 0
    assert ready["mode"] == "simulate"
    assert ready["model"] == "keysight-dsox4024a"
    assert ready["resource"] is None
    assert "trigger_url" not in ready
    assert started["job_id"] == "client-job"
    assert started["artifact_path"] == str(job.artifact_path)
    assert finished["state"] == "failed"
    assert finished["ok"] is False
    assert finished["result"] is None
    assert finished["files"] == []
    assert summary["accepted"] == 0


def test_worker_event_payload_rejects_job_finished_without_result_and_files(tmp_path):
    runtime = _runtime(tmp_path)
    job = worker.WorkerJob(
        command="identify",
        arguments={},
        job_id="client-job",
        worker_job_id="worker-job",
        artifact_path=tmp_path / "worker-job",
        request_time="now",
    )
    runtime.jobs[job.worker_job_id] = job

    with pytest.raises(ValueError, match="require result and files"):
        worker._event_payload(
            runtime,
            "job_finished",
            worker_job_id=job.worker_job_id,
            job_id=job.job_id,
            command=job.command,
            state="succeeded",
            ok=True,
            exit_code=0,
            error=None,
        )


def _assert_status_payload_matches_ready(payload, ready):
    assert payload["service"] == "scopes-tool"
    assert payload["run_id"] == ready["run_id"]
    assert payload["mode"] == ready["mode"]
    assert payload["model"] == ready["model"]
    assert payload["resource"] == ready["resource"]
    assert payload["urls"]["command_url"] == ready["command_url"]
    assert payload["urls"]["status_url"] == ready["status_url"]
    assert payload["urls"]["stop_url"] == ready["stop_url"]
    assert "command_url" not in payload
    assert "status_url" not in payload
    assert "stop_url" not in payload
    assert "trigger_url" not in payload
    assert "trigger_url" not in payload["urls"]


def test_status_and_wait_ready_match_ready_session_and_status_urls(tmp_path, capsys):
    runtime = _runtime(tmp_path)
    with _worker_server(runtime):
        ready = worker._event_payload(
            runtime,
            "ready",
            status_url=f"{runtime.base_url()}/status",
            command_url=f"{runtime.base_url()}/command",
            stop_url=f"{runtime.base_url()}/stop",
            trigger_url="forbidden",
        )
        args = argparse.Namespace(
            command="wait-ready",
            host="127.0.0.1",
            port=runtime.port,
            timeout_ms=1000,
            format="json",
            client_json=True,
        )
        assert worker.client_wait_ready(args) == 0
        status_args = argparse.Namespace(
            command="status",
            host="127.0.0.1",
            port=runtime.port,
            timeout_ms=1000,
            format="json",
            client_json=True,
        )
        assert worker.client_get(status_args, "/status") == 0
        stop_args = argparse.Namespace(
            command="stop",
            host="127.0.0.1",
            port=runtime.port,
            timeout_ms=1000,
            format="json",
            client_json=True,
        )
        assert worker.client_post(stop_args, "/stop", {}) == 0

    output_lines = capsys.readouterr().out.strip().splitlines()
    wait_payload = json.loads(output_lines[0])
    status_payload = json.loads(output_lines[1])
    stop_payload = json.loads(output_lines[2])
    assert ready["event"] == "ready"
    assert ready["schema_version"] == worker.WORKER_SCHEMA_VERSION
    assert ready["service"] == "scopes-tool"
    assert ready["run_id"]
    assert ready["host"] == "127.0.0.1"
    assert ready["port"] == runtime.port
    assert ready["mode"] == "simulate"
    assert ready["model"] == "keysight-dsox4024a"
    assert ready["resource"] is None
    assert ready["command_url"].endswith("/command")
    assert ready["status_url"].endswith("/status")
    assert ready["stop_url"].endswith("/stop")
    assert "trigger_url" not in ready
    _assert_status_payload_matches_ready(wait_payload, ready)
    _assert_status_payload_matches_ready(status_payload, ready)
    assert stop_payload["schema_version"] == worker.WORKER_SCHEMA_VERSION
    assert stop_payload["status"] == "accepted"


def test_worker_lifecycle_failure_before_ready_keeps_stderr_diagnostics():
    script = """
        import sys

        print("startup failed: missing dependency", file=sys.stderr, flush=True)
        raise SystemExit(7)
    """

    with pytest.raises(RuntimeError) as exc_info:
        _run_fake_worker_lifecycle(script, ready_timeout=0.2)

    message = str(exc_info.value)
    assert "UnboundLocalError" not in message
    assert "startup failed: missing dependency" in message
    assert "summary=None" in message
    assert "worker.returncode=7" in message


def test_worker_lifecycle_drains_stderr_without_mixing_stdout_jsonl():
    script = """
        import json
        import sys

        ready = {"event": "ready", "run_id": "run-1"}
        print(json.dumps(ready), flush=True)
        for index in range(2000):
            print(f"diagnostic-{index}", file=sys.stderr, flush=True)
        summary = {
            "event": "summary",
            "run_id": "run-1",
            "ok": False,
            "failed": 1,
            "cancelled": 0,
        }
        print(json.dumps(summary), flush=True)
    """

    with pytest.raises(RuntimeError) as exc_info:
        _run_fake_worker_lifecycle(script)

    message = str(exc_info.value)
    assert "diagnostic-1999" in message
    assert "diagnostic-0" not in message
    assert message.count("diagnostic-") <= 20
    assert "summary={'event': 'summary'" in message


@pytest.mark.parametrize(
    ("summary", "return_code", "should_pass", "match"),
    (
        ({"event": "summary", "run_id": "run-1", "ok": True, "failed": 0, "cancelled": 0}, 0, True, None),
        (None, 0, False, "summary=None"),
        ({"event": "summary", "run_id": "run-1", "ok": False, "failed": 0, "cancelled": 0}, 0, False, "'ok': False"),
        ({"event": "summary", "run_id": "other", "ok": True, "failed": 0, "cancelled": 0}, 0, False, "'run_id': 'other'"),
        ({"event": "summary", "run_id": "run-1", "ok": True, "failed": 0, "cancelled": 0}, 9, False, "worker.returncode=9"),
    ),
)
def test_worker_lifecycle_validates_final_summary(summary, return_code, should_pass, match):
    lines = [
        "import json",
        "import sys",
        'print(json.dumps({"event": "ready", "run_id": "run-1"}), flush=True)',
        'print("final diagnostic", file=sys.stderr, flush=True)',
    ]
    if summary is not None:
        lines.append(f"print(json.dumps({summary!r}), flush=True)")
    lines.append(f"raise SystemExit({return_code})")
    script = "\n".join(lines)

    if should_pass:
        ready, final_summary, stderr_lines = _run_fake_worker_lifecycle(script)
        assert ready["run_id"] == "run-1"
        assert final_summary == summary
        assert stderr_lines == ["final diagnostic"]
    else:
        with pytest.raises(RuntimeError, match=match) as exc_info:
            _run_fake_worker_lifecycle(script)
        assert "final diagnostic" in str(exc_info.value)


def test_event_backlog_preserves_non_target_events_and_predicate_selects_job():
    events = queue.Queue()
    event_backlog = []
    events.put({"event": "message", "text": "kept"})
    events.put({"event": "job_started", "worker_job_id": "other"})
    events.put({"event": "summary", "run_id": "run-1"})
    events.put({"event": "job_started", "worker_job_id": "target"})
    events.put({"event": "job_finished", "worker_job_id": "target"})

    started = _wait_event_from_queue(
        events,
        event_backlog,
        "job_started",
        predicate=lambda event: event.get("worker_job_id") == "target",
    )
    summary = _wait_event_from_queue(
        events,
        event_backlog,
        "summary",
        predicate=lambda event: event.get("run_id") == "run-1",
    )
    other_started = _wait_event_from_queue(
        events,
        event_backlog,
        "job_started",
        predicate=lambda event: event.get("worker_job_id") == "other",
    )
    message = _wait_event_from_queue(events, event_backlog, "message")

    assert started["worker_job_id"] == "target"
    assert summary["run_id"] == "run-1"
    assert other_started["worker_job_id"] == "other"
    assert message["text"] == "kept"


def test_worker_job_paths_default_under_job_dir(tmp_path):
    job_dir = tmp_path / "run" / "job"
    parsed = worker.parse_domain_command(
        "capture",
        {"channel": [1], "points": 1000, "plot": "plot.png"},
        _runtime(tmp_path),
        job_dir,
    )

    assert Path(parsed.csv_path) == job_dir / "capture.csv"
    assert Path(parsed.meta_path) == job_dir / "capture_meta.json"
    assert Path(parsed.plot_path) == job_dir / "plot.png"


def test_worker_segmented_capture_uses_child_output_and_overwrite_guard(tmp_path):
    job_dir = tmp_path / "run" / "job"
    job_dir.mkdir(parents=True)

    parsed = worker.parse_domain_command(
        "segmented-capture",
        {"channel": 1, "segments": 2},
        _runtime(tmp_path),
        job_dir,
    )

    assert Path(parsed.output_dir) == job_dir / "segmented_capture"
    worker._guard_no_overwrite(parsed, job_dir)

    Path(parsed.output_dir).mkdir()
    with pytest.raises(OscilloscopeError, match="already exists"):
        worker._guard_no_overwrite(parsed, job_dir)


def test_worker_no_overwrite_guard_rejects_existing_artifact(tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "capture.csv").write_text("existing", encoding="utf-8")
    parsed = worker.parse_domain_command(
        "capture",
        {"channel": [1]},
        _runtime(tmp_path),
        job_dir,
    )

    with pytest.raises(OscilloscopeError, match="already exists"):
        worker._guard_no_overwrite(parsed, job_dir)


def test_stop_cancels_queued_job_without_bookkeeping_artifacts(tmp_path):
    runtime = _runtime(tmp_path)
    job_dir = tmp_path / "run" / "queued"
    job = worker.WorkerJob(
        command="identify",
        arguments={},
        job_id="client-job",
        worker_job_id="queued",
        artifact_path=job_dir,
        request_time="now",
    )
    runtime.jobs[job.worker_job_id] = job

    worker._finish_cancelled_job(runtime, job, started=False)

    assert job.state == "cancelled"
    assert job.exit_code == 3
    assert job.error == {"type": "cancelled", "message": "cancelled by stop"}
    assert runtime.cancelled == 1
    assert not job.artifact_path.exists()
    assert not (job.artifact_path / "result.json").exists()


def test_stop_cooperatively_cancels_running_capture_batch_before_next_capture(
    tmp_path,
):
    import time

    runtime = _runtime(tmp_path)
    worker_thread = threading.Thread(
        target=worker._job_loop,
        args=(runtime,),
        daemon=True,
    )
    worker_thread.start()

    with _worker_server(runtime):
        status, accepted = _post_command(
            runtime,
            {
                "command": "capture-batch",
                "arguments": {
                    "channel": [1],
                    "count": 3,
                    "interval_seconds": 30,
                },
                "job_id": "cancel-running",
            },
        )
        assert status == 202
        artifact_path = Path(accepted["artifact_path"])
        first_capture = artifact_path / "waveform_0001.csv"
        deadline = time.monotonic() + 2
        while not first_capture.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert first_capture.exists()

        request = urlrequest.Request(
            f"http://127.0.0.1:{runtime.port}/stop",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlrequest.urlopen(request, timeout=2) as response:
            assert response.status == 202

        job = runtime.jobs[accepted["worker_job_id"]]
        deadline = time.monotonic() + 2
        while job.state == "running" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert job.state == "cancelled"

    result = worker._terminal_job_view(job)
    manifest = json.loads((artifact_path / "manifest.json").read_text(encoding="utf-8"))
    assert result["state"] == "cancelled"
    assert result["exit_code"] == 3
    assert result["error"]["type"] == "cancelled"
    assert result["result"]["status"] == "cancelled"
    assert result["result"]["error"] is None
    assert result["result"]["completed_count"] == 1
    assert manifest["status"] == "cancelled"
    assert not (artifact_path / "waveform_0002.csv").exists()
    assert not (artifact_path / "result.json").exists()


@pytest.mark.parametrize(
    ("status", "payload_ok", "exit_code", "expected_state"),
    (
        ("completed", True, 0, "succeeded"),
        ("instrument_error", False, 1, "failed"),
    ),
)
def test_worker_preserves_core_workflow_result_after_late_cancellation(
    tmp_path,
    monkeypatch,
    status,
    payload_ok,
    exit_code,
    expected_state,
):
    runtime = _runtime(tmp_path)
    artifact_path = tmp_path / status

    def fake_execute(_parsed, *, stop_requested=None):
        del stop_requested
        job = runtime.jobs[runtime.active_job_id]
        job.cancel_requested = True
        return (
            {
                "ok": payload_ok,
                "result": {"status": status},
                "files": [],
                "error": (
                    None
                    if payload_ok
                    else {"type": "OscilloscopeError", "message": "instrument error"}
                ),
            },
            exit_code,
        )

    monkeypatch.setattr(worker.scope_cli, "_execute_json_command", fake_execute)
    _, result = _execute_worker_job(
        runtime,
        "capture-batch",
        {"channel": [1], "count": 1},
        artifact_path,
    )

    assert result["state"] == expected_state
    assert result["ok"] is (expected_state == "succeeded")
    assert result["exit_code"] == exit_code
    assert result["result"]["status"] == status
    if status == "completed":
        assert result["error"] is None
    else:
        assert result["error"]["type"] == "OscilloscopeError"


def _execute_worker_job(runtime, command, arguments, artifact_path):
    job = worker.WorkerJob(
        command=command,
        arguments=arguments,
        job_id="client-job",
        worker_job_id=command.replace("-", "_"),
        artifact_path=artifact_path,
        request_time="requested",
        accepted_time="accepted",
    )
    runtime.jobs[job.worker_job_id] = job
    thread = threading.Thread(target=worker._job_loop, args=(runtime,), daemon=True)
    thread.start()
    runtime.queue.put(job)
    runtime.queue.join()
    return job, worker._terminal_job_view(job)


def test_worker_measure_results_preserves_statistics_items(tmp_path):
    artifact_path = tmp_path / "measure_results"
    job, result = _execute_worker_job(
        _runtime(tmp_path), "measure-results", {}, artifact_path
    )

    assert result["state"] == "succeeded"
    assert result["result"]["raw"]
    assert result["result"]["items"] == []
    assert result["result"]["statistics_items"]
    assert job.result["scpi"]["sent"] == ["*IDN?", ":MEASure:RESults?"]
    assert not artifact_path.exists()
    assert not (artifact_path / "request.json").exists()
    assert not (artifact_path / "result.json").exists()


def test_worker_executes_capture_wait_trigger_in_simulator(tmp_path):
    runtime = _runtime(tmp_path)
    artifact_path = tmp_path / "capture_wait"

    job, result = _execute_worker_job(
        runtime,
        "capture",
        {
            "channel": [1],
            "wait_trigger": True,
            "trigger_timeout_ms": 1,
            "trigger_poll_interval_ms": 1,
        },
        artifact_path,
    )

    assert result["state"] == "succeeded"
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["result"]["trigger"]["outcome"] == "natural"
    trigger_values = [
        int(value) for value in result["result"]["trigger"]["raw_values"]
    ]
    assert len(trigger_values) == 2
    assert trigger_values[0] & OPERATION_CONDITION_RUN_MASK
    assert not trigger_values[1] & OPERATION_CONDITION_RUN_MASK
    assert result["files"] == [
        {"kind": "csv", "path": str(artifact_path / "capture.csv")},
        {"kind": "metadata", "path": str(artifact_path / "capture_meta.json")},
    ]
    assert (artifact_path / "capture.csv").exists()
    assert not (artifact_path / "request.json").exists()
    assert not (artifact_path / "result.json").exists()
    assert job.result["scpi"]["sent"][:4] == [
        "*IDN?",
        single_command(),
        operation_condition_query(),
        operation_condition_query(),
    ]


def test_worker_executes_segmented_capture_with_domain_child_artifacts(tmp_path):
    runtime = _runtime(tmp_path)
    original_body = {
        "command": "segmented-capture",
        "arguments": {
            "channel": 1,
            "segments": 2,
            "poll_interval_ms": 1,
        },
        "job_id": "segmented-job",
    }

    worker_thread = threading.Thread(
        target=worker._job_loop, args=(runtime,), daemon=True
    )
    worker_thread.start()
    with _worker_server(runtime):
        status, accepted = _post_command(runtime, original_body)
        assert status == 202
        runtime.queue.join()

    artifact_path = Path(accepted["artifact_path"])
    result = worker._terminal_job_view(runtime.jobs[accepted["worker_job_id"]])
    domain_dir = artifact_path / "segmented_capture"
    scpi_log = (domain_dir / "scpi.log").read_text(encoding="utf-8")

    assert not (artifact_path / "request.json").exists()
    assert not (artifact_path / "result.json").exists()
    assert result["state"] == "succeeded"
    assert result["ok"] is True
    assert result["result"]["operation"] == "segmented-capture"
    assert result["result"]["status"] == "completed"
    assert result["result"]["polling"]["command"] == ":OPERegister:CONDition?"
    assert "two consecutive" in result["result"]["polling"]["runtime_behavior"]
    assert (domain_dir / "manifest.json").exists()
    assert (domain_dir / "segment_0001.csv").exists()
    assert (domain_dir / "segment_0002.csv").exists()
    assert result["files"] == [
        {"kind": "manifest", "path": str(domain_dir / "manifest.json")},
        {"kind": "scpi_log", "path": str(domain_dir / "scpi.log")},
        {"kind": "csv", "path": str(domain_dir / "segment_0001.csv")},
        {"kind": "csv", "path": str(domain_dir / "segment_0002.csv")},
    ]
    assert scpi_log.count(":SINGle") == 1
    assert scpi_log.count(":WAVeform:SEGMented:COUNt?") == 1
    assert scpi_log.rindex(":OPERegister:CONDition?") < scpi_log.index(
        ":WAVeform:SEGMented:COUNt?"
    )
    assert ":WAVeform:SEGMented:ALL OFF" not in scpi_log


def test_worker_maps_segmented_capture_partial_result_and_existing_files(
    tmp_path, monkeypatch
):
    runtime = _runtime(tmp_path)
    artifact_path = tmp_path / "partial"

    def fake_execute(parsed, *, stop_requested=None):
        del stop_requested
        csv_path = Path(parsed.output_dir) / "segment_0001.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text("time_s,ch1_v\n0,0\n", encoding="utf-8")
        return (
            {
                "ok": False,
                "result": {
                    "operation": "segmented-capture",
                    "status": "partial",
                },
                "files": [{"kind": "csv", "path": str(csv_path)}],
                "error": {"type": "OscilloscopeError", "message": "partial"},
            },
            1,
        )

    monkeypatch.setattr(worker.scope_cli, "_execute_json_command", fake_execute)
    _, result = _execute_worker_job(
        runtime,
        "segmented-capture",
        {"channel": 1, "segments": 2},
        artifact_path,
    )

    csv_path = artifact_path / "segmented_capture" / "segment_0001.csv"
    assert result["state"] == "failed"
    assert result["ok"] is False
    assert result["result"]["status"] == "partial"
    assert result["files"] == [{"kind": "csv", "path": str(csv_path)}]
    assert result["exit_code"] == 1
    assert csv_path.exists()


@pytest.mark.parametrize(
    ("command", "arguments", "scpi_command", "field", "expected_value"),
    (
        ("sample-rate", {"query": True}, sample_rate_query(), "sample_rate_hz", 5e9),
        (
            "sample-rate",
            {"query": True, "maximum": True},
            sample_rate_maximum_query(),
            "maximum_sample_rate_hz",
            5e9,
        ),
        (
            "acquisition-points",
            {"query": True},
            acquisition_points_query(),
            "acquisition_points",
            1000000,
        ),
        (
            "record-length",
            {"query": True},
            record_length_query(),
            "record_length_points",
            65536,
        ),
        ("force-trigger", {}, force_trigger_command(), "forced", True),
    ),
)
def test_worker_executes_trigger_and_acquisition_queries_in_simulator(
    tmp_path, command, arguments, scpi_command, field, expected_value
):
    runtime = _runtime(tmp_path)

    job, result = _execute_worker_job(runtime, command, arguments, tmp_path / command)

    assert result["state"] == "succeeded"
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["files"] == []
    assert result["result"]["scpi_command"] == scpi_command
    assert result["result"][field] == expected_value
    if arguments.get("maximum"):
        assert result["result"]["query_kind"] == "maximum"
    assert job.result["scpi"]["sent"] == ["*IDN?", scpi_command, ":SYSTem:ERRor?"]


@pytest.mark.parametrize(
    ("arguments", "expected_sent", "expected_result"),
    (
        (
            {"query": True},
            ["*IDN?", trigger_holdoff_query(), ":SYSTem:ERRor?"],
            {"operation": "query", "command": trigger_holdoff_query(), "seconds": 100e-9},
        ),
        (
            {"seconds": 1e-6},
            ["*IDN?", *trigger_holdoff_commands(1e-6), ":SYSTem:ERRor?"],
            {
                "operation": "set",
                "command": trigger_holdoff_commands(1e-6)[-1],
                "commands": trigger_holdoff_commands(1e-6),
                "seconds": 1e-6,
            },
        ),
    ),
)
def test_worker_executes_trigger_holdoff_in_simulator(
    tmp_path, arguments, expected_sent, expected_result
):
    runtime = _runtime(tmp_path)

    job, result = _execute_worker_job(
        runtime, "trigger-holdoff", arguments, tmp_path / "trigger_holdoff"
    )

    assert result["state"] == "succeeded"
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["files"] == []
    for key, value in expected_result.items():
        assert result["result"][key] == value
    assert job.result["scpi"]["sent"] == expected_sent


@pytest.mark.parametrize(
    ("command", "arguments", "scpi_command", "expected_fields"),
    (
        (
            "display-clear",
            {},
            display_clear_command(),
            {"operation": "display-clear", "command": display_clear_command()},
        ),
        (
            "display-persistence",
            {"query": True},
            display_persistence_query(),
            {"operation": "display-persistence", "mode": "minimum", "seconds": None},
        ),
        (
            "display-persistence",
            {"seconds": 0.5},
            display_persistence_command(0.5),
            {"operation": "display-persistence", "mode": None, "seconds": 0.5},
        ),
        (
            "display-intensity",
            {"query": True},
            display_intensity_query(),
            {"operation": "display-intensity", "value": 50},
        ),
        (
            "display-intensity",
            {"value": 75},
            display_intensity_command(75),
            {"operation": "display-intensity", "value": 75},
        ),
        (
            "display-vectors",
            {"query": True},
            display_vectors_query(),
            {"operation": "display-vectors", "value": True},
        ),
        (
            "display-vectors",
            {"on": True},
            display_vectors_command(True),
            {"operation": "display-vectors", "value": True},
        ),
    ),
)
def test_worker_executes_display_common_in_simulator(
    tmp_path, command, arguments, scpi_command, expected_fields
):
    runtime = _runtime(tmp_path)

    job, result = _execute_worker_job(runtime, command, arguments, tmp_path / command)

    assert result["state"] == "succeeded"
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["files"] == []
    assert result["result"]["command"] == scpi_command
    for key, value in expected_fields.items():
        assert result["result"][key] == value
    assert job.result["scpi"]["sent"] == ["*IDN?", scpi_command, ":SYSTem:ERRor?"]


@pytest.mark.parametrize(
    ("command", "arguments", "scpi_command", "field", "expected_value"),
    (
        (
            "channel-impedance",
            {"channel": 1, "impedance": "one-meg"},
            channel_impedance_command(1, "one_meg"),
            "impedance",
            "one_meg",
        ),
        (
            "channel-invert",
            {"channel": 1, "on": True},
            channel_invert_command(1, True),
            "invert",
            True,
        ),
        (
            "channel-range",
            {"channel": 1, "volts_full_scale": 4},
            channel_range_command(1, 4),
            "range_volts",
            4.0,
        ),
        (
            "channel-units",
            {"channel": 1, "units": "amp"},
            channel_units_command(1, "amp"),
            "units",
            "amp",
        ),
        (
            "channel-vernier",
            {"channel": 1, "off": True},
            channel_vernier_command(1, False),
            "vernier",
            False,
        ),
        (
            "channel-probe-skew",
            {"channel": 1, "seconds": 1e-9},
            channel_probe_skew_command(1, 1e-9),
            "probe_skew_seconds",
            1e-9,
        ),
    ),
)
def test_worker_executes_channel_advanced_settings_in_simulator(
    tmp_path, command, arguments, scpi_command, field, expected_value
):
    runtime = _runtime(tmp_path)

    job, result = _execute_worker_job(runtime, command, arguments, tmp_path / command)

    assert result["state"] == "succeeded"
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["files"] == []
    assert result["result"]["operation"] == "set"
    assert result["result"]["command"] == scpi_command
    assert result["result"][field] == expected_value
    assert job.result["scpi"]["sent"] == ["*IDN?", scpi_command, ":SYSTem:ERRor?"]


def test_worker_2000x_rejects_fifty_ohm_with_allow_before_impedance_scpi(tmp_path):
    runtime = _runtime(tmp_path, model="keysight-dsox2004a")

    job, result = _execute_worker_job(
        runtime,
        "channel-impedance",
        {"channel": 1, "impedance": "fifty", "allow_50_ohm": True},
        tmp_path / "channel_impedance_2000x",
    )

    assert result["state"] == "failed"
    assert result["ok"] is False
    assert result["exit_code"] == 3
    assert (
        "DSO-X 2000X only supports one-meg input impedance"
        in result["error"]["message"]
    )
    assert job.result is None


def test_worker_executes_annotation_set_in_simulator(tmp_path):
    runtime = _runtime(tmp_path)

    job, result = _execute_worker_job(
        runtime,
        "annotation",
        {
            "slot": 2,
            "on": True,
            "text": "Run note",
            "color": "white",
            "background": "opaque",
            "x": 10,
            "y": 20,
        },
        tmp_path / "annotation",
    )

    assert result["state"] == "succeeded"
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["files"] == []
    assert result["result"]["operation"] == "set"
    expected_commands = [
        ':DISPlay:ANNotation2:TEXT "Run note"',
        ":DISPlay:ANNotation2:COLor WHITE",
        ":DISPlay:ANNotation2:BACKground OPAQ",
        ":DISPlay:ANNotation2:X1Position 10",
        ":DISPlay:ANNotation2:Y1Position 20",
        ":DISPlay:ANNotation2 ON",
    ]
    assert result["result"]["commands"] == expected_commands
    assert result["result"]["slot"] == 2
    assert result["result"]["enabled"] is True
    assert result["result"]["text"] == "Run note"
    assert result["result"]["clear"] is False
    assert result["result"]["color"] == "WHITE"
    assert result["result"]["background"] == "OPAQ"
    assert result["result"]["x"] == 10
    assert result["result"]["y"] == 20
    sent_commands = job.result["scpi"]["sent"]
    assert sent_commands[0] == "*IDN?"
    assert sent_commands[1:-1] == expected_commands
    assert sent_commands[-1] == ":SYSTem:ERRor?"

    off_runtime = _runtime(tmp_path)
    off_job, off_result = _execute_worker_job(
        off_runtime,
        "annotation",
        {"slot": 2, "off": True, "clear": True, "x": 10, "y": 20},
        tmp_path / "annotation_off",
    )
    expected_off_commands = [
        ':DISPlay:ANNotation2:TEXT ""',
        ":DISPlay:ANNotation2:X1Position 10",
        ":DISPlay:ANNotation2:Y1Position 20",
        ":DISPlay:ANNotation2 OFF",
    ]

    assert off_result["state"] == "succeeded"
    assert off_result["result"]["commands"] == expected_off_commands
    off_sent_commands = off_job.result["scpi"]["sent"]
    assert off_sent_commands[0] == "*IDN?"
    assert off_sent_commands[1:-1] == expected_off_commands
    assert off_sent_commands[-1] == ":SYSTem:ERRor?"


class _FakeBackend:
    backend = "fake VISA"

    def __init__(self, idn: str):
        self.idn = idn
        self.history = []
        self.timeout = None
        self.closed = False

    def query(self, command: str) -> str:
        self.history.append(command)
        if command == "*IDN?":
            return self.idn
        return "+0,\"No error\""

    def write(self, command: str) -> None:
        self.history.append(command)

    def set_timeout(self, timeout_ms: int | None) -> None:
        self.timeout = timeout_ms

    def close(self) -> None:
        self.closed = True


class _FakeScope:
    def __init__(self, idn: str):
        self.backend = _FakeBackend(idn)
        self.scpi = self.backend
        self.capabilities = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def close(self):
        self.backend.close()

    def query_idn(self):
        idn = parse_idn(self.backend.query("*IDN?"))
        self.capabilities = capabilities_for_model_id(idn.model_id)
        return idn


def test_live_worker_identity_mismatch_fails_before_domain_scpi(monkeypatch, tmp_path):
    fake_scope = _FakeScope("KEYSIGHT,DSOX3024A,MY0000,1.0")
    monkeypatch.setattr(cli_runtime.Oscilloscope, "open", lambda *args, **kwargs: fake_scope)
    parsed = worker.parse_domain_command(
        "capture",
        {"channel": [1]},
        _live_runtime(tmp_path),
        tmp_path / "job",
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 3
    assert payload["schema_version"] == cli.CLI_SCHEMA_VERSION
    assert "timestamp_utc" in payload
    assert payload["ok"] is False
    assert payload["error"]["type"] == "identity_mismatch"
    assert payload["error"]["expected_model"] == "keysight-dsox4024a"
    assert payload["error"]["actual_idn"] == "KEYSIGHT,DSOX3024A,MY0000,1.0"
    assert fake_scope.backend.history == ["*IDN?"]
    assert fake_scope.backend.timeout == cli_runtime.WORKER_IDN_TIMEOUT_MS
    assert fake_scope.backend.closed is True


@pytest.mark.parametrize(
    "raw_idn",
    [
        "UNKNOWN,DSOX4024A,MY0000,1.0",
        "KEYSIGHT,DSOX4054A,MY0000,1.0",
    ],
)
def test_live_worker_unknown_identity_fails_before_domain_scpi(
    monkeypatch,
    tmp_path,
    raw_idn,
):
    fake_scope = _FakeScope(raw_idn)
    monkeypatch.setattr(
        cli_runtime.Oscilloscope,
        "open",
        lambda *args, **kwargs: fake_scope,
    )
    parsed = worker.parse_domain_command(
        "capture",
        {"channel": [1]},
        _live_runtime(tmp_path),
        tmp_path / "job",
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 1
    assert payload["ok"] is False
    assert fake_scope.backend.history == ["*IDN?"]


def test_worker_triggered_measure_loop_is_allowlisted_and_uses_job_directory(tmp_path):
    runtime = _runtime(tmp_path)
    job_dir = tmp_path / "triggered-job"
    arguments = {
        "channel": [1, 2],
        "items": "vpp,frequency",
        "pair": ["1:2"],
        "pair_items": "phase",
        "count": 2,
        "trigger_timeout_seconds": 1,
        "interval_seconds": 0,
    }

    assert "triggered-measure-loop" in worker.DOMAIN_COMMANDS
    parsed = worker.parse_domain_command(
        "triggered-measure-loop",
        arguments,
        runtime,
        job_dir,
    )

    assert Path(parsed.output_dir) == job_dir
    assert parsed.count == 2
    assert parsed.trigger_timeout_seconds == 1


def test_worker_triggered_capture_series_is_strict_and_uses_job_directory(tmp_path):
    runtime = _runtime(tmp_path)
    job_dir = tmp_path / "triggered-capture-job"
    arguments = {
        "channel": [1, 2],
        "points": 1000,
        "format": "byte",
        "count": 2,
        "trigger_timeout_seconds": 1,
        "interval_seconds": 0,
    }

    assert "triggered-capture-series" in worker.DOMAIN_COMMANDS
    command, normalized, job_id = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "triggered-capture-series",
            "arguments": arguments,
        }
    )
    assert command == "triggered-capture-series"
    assert normalized == arguments
    assert job_id is None
    parsed = worker.parse_domain_command(
        command,
        normalized,
        runtime,
        job_dir,
    )

    assert parsed.channel == [1, 2]
    assert parsed.points == 1000
    assert parsed.waveform_format == "byte"
    assert parsed.count == 2
    assert parsed.trigger_timeout_seconds == 1
    assert parsed.interval_seconds == 0
    assert Path(parsed.output_dir) == job_dir
    assert parsed.log_scpi is False


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"count": 1, "trigger_timeout_seconds": 1}, "requires argument channel"),
        ({"channel": [1], "trigger_timeout_seconds": 1}, "requires argument count"),
        ({"channel": [1], "count": 1}, "requires argument trigger_timeout_seconds"),
        ({"channel": [1], "count": True, "trigger_timeout_seconds": 1}, "count must be an integer"),
        ({"channel": 1, "count": 1, "trigger_timeout_seconds": 1}, "non-empty array"),
        ({"channel": [1], "count": 1, "trigger_timeout_seconds": "1"}, "must be a finite number"),
        ({"channel": [1], "count": 1, "trigger_timeout_seconds": 0}, "must be greater than zero"),
        ({"channel": [1], "count": 1, "trigger_timeout_seconds": 1, "points": 123}, "points is not supported"),
        ({"channel": [1], "count": 1, "trigger_timeout_seconds": 1, "format": "ascii"}, "format must be exactly byte or word"),
        ({"channel": [1], "count": 1, "trigger_timeout_seconds": 1, "interval_seconds": -1}, "must be non-negative"),
        ({"channel": [1], "count": 1, "trigger_timeout_seconds": 1, "unknown": True}, "unknown argument"),
    ],
)
def test_worker_triggered_capture_series_rejects_invalid_arguments(arguments, message):
    with pytest.raises(OscilloscopeError, match=message):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": "triggered-capture-series",
                "arguments": arguments,
            }
        )


@pytest.mark.parametrize(
    "arguments",
    [
        {
            "channel": [1],
            "count": 1,
            "trigger_timeout_seconds": 1,
            "output_dir": "escape",
        },
        {
            "channel": [1],
            "count": 1,
            "trigger_timeout_seconds": 1,
            "log_scpi": True,
        },
    ],
)
def test_worker_triggered_capture_series_rejects_cli_paths_before_artifacts(
    monkeypatch, tmp_path, arguments
):
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(
        cli_runtime.Oscilloscope,
        "open",
        staticmethod(
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("opened"))
        ),
    )

    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": "triggered-capture-series",
                "arguments": arguments,
                "job_id": "invalid-triggered-capture",
            },
        )

    assert status == 400
    assert payload["status"] == "error"
    assert payload["error"] == "validation_error"
    assert runtime.accepted == 0
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_triggered_capture_series_uses_core_terminal_status_mapping():
    payload = {"result": {"status": "instrument_error"}}

    assert (
        worker._core_workflow_result_status("triggered-capture-series", payload)
        == "instrument_error"
    )


def test_worker_measure_until_is_strict_and_uses_job_directory(tmp_path):
    runtime = _runtime(tmp_path)
    job_dir = tmp_path / "measure-until-job"
    arguments = {
        "channel": 1,
        "item": "vpp",
        "operator": "gt",
        "threshold": 3.3,
        "timeout_seconds": 600,
        "interval_seconds": 1,
    }

    assert "measure-until" in worker.DOMAIN_COMMANDS
    command, normalized, job_id = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "measure-until",
            "arguments": arguments,
        }
    )
    assert command == "measure-until"
    assert normalized == arguments
    assert job_id is None

    parsed = worker.parse_domain_command(command, normalized, runtime, job_dir)

    assert parsed.channel == 1
    assert parsed.item == "vpp"
    assert parsed.operator == "gt"
    assert parsed.threshold == 3.3
    assert parsed.timeout_seconds == 600
    assert parsed.interval_seconds == 1
    assert Path(parsed.output_dir) == job_dir
    assert parsed.log_scpi is False


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"item": "vpp", "operator": "gt", "threshold": 1, "timeout_seconds": 1}, "requires argument channel"),
        ({"channel": 1, "operator": "gt", "threshold": 1, "timeout_seconds": 1}, "requires argument item"),
        ({"channel": 1, "item": "vpp", "threshold": 1, "timeout_seconds": 1}, "requires argument operator"),
        ({"channel": 1, "item": "vpp", "operator": "gt", "timeout_seconds": 1}, "requires argument threshold"),
        ({"channel": 1, "item": "vpp", "operator": "gt", "threshold": 1}, "requires argument timeout_seconds"),
        ({"channel": [1], "item": "vpp", "operator": "gt", "threshold": 1, "timeout_seconds": 1}, "channel must be an integer"),
        ({"channel": 1, "item": "vpp", "operator": "eq", "threshold": 1, "timeout_seconds": 1}, "operator must be exactly"),
        ({"channel": 1, "item": "vpp", "operator": "gt", "threshold": True, "timeout_seconds": 1}, "threshold must be a finite number"),
        ({"channel": 1, "item": "vpp", "operator": "gt", "threshold": float("inf"), "timeout_seconds": 1}, "threshold must be a finite number"),
        ({"channel": 1, "item": "vpp", "operator": "gt", "threshold": 1, "timeout_seconds": 0}, "timeout_seconds must be greater than zero"),
        ({"channel": 1, "item": "vpp", "operator": "gt", "threshold": 1, "timeout_seconds": 1, "interval_seconds": -1}, "interval_seconds must be non-negative"),
        ({"channel": 1, "item": "vpp", "operator": "gt", "threshold": 1, "timeout_seconds": 1, "unknown": True}, "unknown argument"),
    ],
)
def test_worker_measure_until_rejects_invalid_arguments(arguments, message):
    with pytest.raises(OscilloscopeError, match=message):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": "measure-until",
                "arguments": arguments,
            }
        )


@pytest.mark.parametrize(
    "extra_arguments",
    [
        {"output_dir": "escape"},
        {"log_scpi": True},
        {"item": "phase"},
        {"item": "y_at_x"},
        {"channel": 5},
    ],
)
def test_worker_measure_until_rejects_invalid_public_contract_before_artifacts(
    monkeypatch, tmp_path, extra_arguments
):
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(
        cli_runtime.Oscilloscope,
        "open",
        staticmethod(
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("opened"))
        ),
    )
    arguments = {
        "channel": 1,
        "item": "vpp",
        "operator": "gt",
        "threshold": 3.3,
        "timeout_seconds": 10,
        **extra_arguments,
    }

    with _worker_server(runtime):
        status, payload = _post_command(
            runtime,
            {
                "command": "measure-until",
                "arguments": arguments,
                "job_id": "invalid-measure-until",
            },
        )

    assert status == 400
    assert payload["status"] == "error"
    assert payload["error"] == "validation_error"
    assert runtime.accepted == 0
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_executes_measure_until_with_owned_artifacts(tmp_path):
    artifact_path = tmp_path / "measure-until-execution"
    job, result = _execute_worker_job(
        _runtime(tmp_path),
        "measure-until",
        {
            "channel": 1,
            "item": "vpp",
            "operator": "gt",
            "threshold": 0,
            "timeout_seconds": 1,
            "interval_seconds": 0,
        },
        artifact_path,
    )

    assert job.state == "succeeded"
    assert result["state"] == "succeeded"
    assert result["result"]["status"] == "completed"
    assert result["result"]["termination_reason"] == "condition_met"
    assert (artifact_path / "measurements.csv").exists()
    assert (artifact_path / "manifest.json").exists()
    assert (artifact_path / "scpi.log").exists()


@pytest.mark.parametrize(
    "status, expected",
    [
        ("completed", "completed"),
        ("cancelled", "cancelled"),
        ("error", "error"),
        ("instrument_error", "instrument_error"),
    ],
)
def test_worker_measure_until_uses_core_terminal_status_mapping(status, expected):
    payload = {"result": {"status": status}}

    assert worker._core_workflow_result_status("measure-until", payload) == expected


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"count": 1, "trigger_timeout_seconds": 1, "output_dir": "escape"}, "unknown argument"),
        ({"count": True, "trigger_timeout_seconds": 1}, "count must be an integer"),
        ({"count": 1, "trigger_timeout_seconds": "1"}, "must be a finite number"),
        ({"count": 1, "trigger_timeout_seconds": 1, "channel": 1}, "non-empty array"),
        ({"count": 1, "trigger_timeout_seconds": 1, "pair": [1]}, "array of strings"),
        ({"count": 1, "trigger_timeout_seconds": 1, "interval_seconds": -1}, "must be non-negative"),
    ],
)
def test_worker_triggered_measure_loop_rejects_invalid_arguments(arguments, message):
    with pytest.raises(OscilloscopeError, match=message):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": "triggered-measure-loop",
                "arguments": arguments,
            }
        )


def test_worker_executes_triggered_measure_loop_with_domain_artifacts(tmp_path):
    artifact_path = tmp_path / "triggered-execution"
    job, result = _execute_worker_job(
        _runtime(tmp_path),
        "triggered-measure-loop",
        {
            "channel": [1],
            "items": "vpp",
            "count": 2,
            "trigger_timeout_seconds": 1,
            "interval_seconds": 0,
        },
        artifact_path,
    )

    assert job.state == "succeeded"
    assert result["state"] == "succeeded"
    assert result["result"]["status"] == "completed"
    assert result["result"]["completed_count"] == 2
    assert (artifact_path / "measurements.csv").exists()
    assert (artifact_path / "manifest.json").exists()
    assert (artifact_path / "scpi.log").exists()


def test_stop_cooperatively_cancels_running_triggered_measure_loop(tmp_path):
    import time

    runtime = _runtime(tmp_path)
    worker_thread = threading.Thread(target=worker._job_loop, args=(runtime,), daemon=True)
    worker_thread.start()
    job = None

    with _worker_server(runtime):
        try:
            status, accepted = _post_command(
                runtime,
                {
                    "command": "triggered-measure-loop",
                    "arguments": {
                        "channel": [1],
                        "items": "vpp",
                        "count": 3,
                        "trigger_timeout_seconds": 1,
                        "interval_seconds": 30,
                    },
                    "job_id": "cancel-triggered-loop",
                },
            )
            assert status == 202
            job = runtime.jobs[accepted["worker_job_id"]]
            artifact_path = Path(accepted["artifact_path"])
            manifest_path = artifact_path / "manifest.json"
            deadline = time.monotonic() + 2
            completed_count = None
            last_observation = "manifest was not created"
            while time.monotonic() < deadline:
                if manifest_path.exists():
                    try:
                        manifest = json.loads(
                            manifest_path.read_text(encoding="utf-8")
                        )
                    except json.JSONDecodeError as exc:
                        last_observation = f"transient JSON decode error: {exc}"
                    else:
                        assert isinstance(manifest, dict), (
                            "manifest must contain a JSON object"
                        )
                        assert "completed_count" in manifest, (
                            "manifest must contain completed_count"
                        )
                        observed_count = manifest["completed_count"]
                        assert (
                            isinstance(observed_count, int)
                            and not isinstance(observed_count, bool)
                        ), "manifest completed_count must be an integer"
                        assert observed_count in (0, 1), (
                            "manifest completed_count must be 0 or 1 before stop"
                        )
                        completed_count = observed_count
                        last_observation = f"completed_count={observed_count}"
                        if completed_count == 1:
                            break
                time.sleep(0.01)
            assert completed_count == 1, (
                "manifest did not reach completed_count=1 before deadline; "
                f"last observation: {last_observation}"
            )

            request = urlrequest.Request(
                f"http://127.0.0.1:{runtime.port}/stop",
                data=b"{}",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urlrequest.urlopen(request, timeout=2) as response:
                assert response.status == 202

            deadline = time.monotonic() + 2
            while job.state == "running" and time.monotonic() < deadline:
                time.sleep(0.01)
            assert job.state == "cancelled"
        finally:
            runtime.stopping = True
            if job is not None and job.state in {"queued", "running"}:
                job.cancel_requested = True
                deadline = time.monotonic() + 2
                while (
                    job.state in {"queued", "running"}
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
                assert job.state not in {"queued", "running"}, (
                    "worker job did not finish after cleanup cancellation"
                )

    result = worker._terminal_job_view(job)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result["state"] == "cancelled"
    assert result["exit_code"] == 3
    assert result["result"]["status"] == "cancelled"
    assert result["result"]["completed_count"] == 1
    assert manifest["status"] == "cancelled"
    assert not (artifact_path / "result.json").exists()
