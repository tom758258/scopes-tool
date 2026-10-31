"""Real no-hardware Worker subprocess contracts for numeric native streaming."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from urllib import error as urlerror
from urllib import request as urlrequest


MEASUREMENTS = [
    {"id": "ch1_frequency", "channel": 1, "item": "frequency"},
    {"id": "ch2_vpp", "channel": 2, "item": "vpp"},
]


def _post(url, command=None, arguments=None):
    body = {"schema_version": 3}
    if command is not None:
        body.update({"command": command, "arguments": arguments or {}})
    request = urlrequest.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlrequest.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except urlerror.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def _status(url):
    with urlrequest.urlopen(url, timeout=5) as response:
        return json.load(response)


@contextmanager
def _streaming_worker(model="keysight-dsox4024a"):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "scopes_tool_cli", "worker", "--simulate",
         "--model", model, "--port", "0",
         "--format", "jsonl", "--streaming"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    events = queue.Queue()
    records = []
    def consume():
        for line in proc.stdout:
            event = json.loads(line)
            records.append(event)
            events.put(event)
    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    try:
        ready = events.get(timeout=12)
        assert ready["event"] == "ready"
        assert ready["features"]["common.streaming"] == {
            "contract_version": 1, "lifecycles": ["deferred_start"],
        }
        assert ready["stream"] == {"lifecycle": "deferred_start"}
        assert "state" not in ready["stream"]
        yield ready, events, records, proc
    finally:
        if proc.poll() is None:
            try:
                ready_url = next(
                    (item["stop_url"] for item in records if item["event"] == "ready"), None
                )
                if ready_url is not None:
                    _post(ready_url)
            except OSError:
                pass
        try:
            proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            raise
        thread.join(timeout=2)
        proc.stderr.close()
        proc.stdout.close()


def _event(events, name, timeout=8):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        item = events.get(timeout=max(0.01, until - time.monotonic()))
        if item["event"] == name:
            return item
    raise AssertionError(f"missing event: {name}")


def test_real_scopes_sim_worker_finite_multi_item_and_control_admission():
    with _streaming_worker() as (ready, events, records, proc):
        status = _status(ready["status_url"])
        assert status["stream"] == {"lifecycle": "deferred_start", "state": "waiting"}
        # Existing Setup/other ordinary jobs remain available before source start.
        accepted, job = _post(ready["command_url"], "identify")
        assert accepted == 202 and job["kind"] == "async_job"
        _event(events, "job_finished")
        code, result = _post(ready["command_url"], "measure-stream-start", {
            "measurements": MEASUREMENTS, "count": 3, "interval_seconds": 0.01,
        })
        assert code == 202 and result["kind"] == "control"
        assert result["worker_job_id"] is None
        assert result["run_id"] == ready["run_id"]
        assert _post(ready["command_url"], "measure-stream-start", {
            "measurements": MEASUREMENTS,
        })[0] == 409
        assert _post(ready["command_url"], "measure", {
            "item": "vpp", "channel": 1,
        })[0] == 409
        active = _event(events, "status")
        while active["stream"]["state"] != "active":
            active = _event(events, "status")
        samples = [_event(events, "sample") for _ in range(3)]
        assert [s["index"] for s in samples] == [1, 2, 3]
        for sample in samples:
            assert list(sample["values"]) == ["ch1_frequency", "ch2_vpp"]
            assert sample["run_id"] == ready["run_id"]
            assert sample["values"]["ch1_frequency"]["unit"] == "Hz"
            assert sample["values"]["ch2_vpp"]["unit"] == "V"
        ended = _event(events, "status")
        assert ended["stream"]["state"] == "ended"
        assert _status(ready["status_url"])["stream"]["state"] == "ended"
        assert proc.poll() is None
        assert _post(ready["stop_url"])[0] == 202
        summary = _event(events, "summary")
        assert summary["ok"] is True
        assert summary["stream_summary"]["completed_cycles"] == 3
        assert summary["stream_summary"]["stop_reason"] == "count_reached"
        proc.wait(timeout=8)
        assert proc.returncode == 0
        assert records.index(ended) > records.index(samples[-1])


def test_real_scopes_sim_worker_native_infinite_stop_and_waiting_stop():
    with _streaming_worker() as (ready, events, records, proc):
        assert _post(ready["command_url"], "measure-stream-start", {
            "measurements": MEASUREMENTS, "interval_seconds": 0.01,
        })[0] == 202
        while True:
            status = _event(events, "status")
            if status["stream"]["state"] == "active":
                break
        assert _event(events, "sample")["index"] == 1
        assert _event(events, "sample")["index"] == 2
        assert _post(ready["stop_url"])[0] == 202
        while True:
            status = _event(events, "status")
            if status["stream"]["state"] == "ended":
                break
        summary = _event(events, "summary")
        assert summary["ok"] is True
        assert summary["stream_summary"]["expected_cycles"] is None
        assert summary["stream_summary"]["completed_cycles"] >= 2
        assert summary["stream_summary"]["stop_reason"] == "stop_requested"
        proc.wait(timeout=8)
        assert proc.returncode == 0
        assert not [r for r in records[records.index(status) + 1:] if r["event"] == "sample"]

    with _streaming_worker() as (ready, events, records, proc):
        assert _post(ready["stop_url"])[0] == 202
        while True:
            status = _event(events, "status")
            if status["stream"]["state"] == "ended":
                break
        summary = _event(events, "summary")
        assert summary["stream_summary"]["completed_cycles"] == 0
        assert summary["stream_summary"]["stop_reason"] == "stopped_before_start"
        assert not any(r["event"] == "sample" for r in records)
        proc.wait(timeout=8)
        assert proc.returncode == 0


def test_deferred_source_start_is_rejected_while_setup_job_is_queued():
    from http.server import ThreadingHTTPServer
    from scopes_tool_cli import worker

    runtime = worker.WorkerRuntime(
        host="127.0.0.1", port=0, mode="simulate",
        model="keysight-dsox4024a", resource=None,
        queue_max=32, output_format="jsonl", streaming=True,
    )
    queued = worker.WorkerJob(
        command="identify", arguments={}, job_id="pending",
        worker_job_id="pending", request_time="now",
    )
    runtime.queue.put_nowait(queued)
    server = ThreadingHTTPServer(("127.0.0.1", 0), worker._make_handler(runtime))
    runtime.port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, result = _post(
            runtime.control_urls()["command_url"],
            "measure-stream-start", {"measurements": MEASUREMENTS},
        )
        assert status == 409
        assert result["kind"] == "control"
        assert result["reason"] == "worker_busy"
        assert not runtime.stream_started
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        runtime.queue.get_nowait()
        runtime.queue.task_done()


def test_worker_client_understands_streaming_status_and_control_reply(monkeypatch):
    import argparse
    import pytest
    from scopes_tool_cli import worker, worker_client
    from scopes_tool_core.errors import OscilloscopeError

    runtime = worker.WorkerRuntime(
        host="127.0.0.1", port=8765, mode="simulate",
        model="keysight-dsox4024a", resource=None,
        queue_max=32, output_format="jsonl", streaming=True,
    )
    args = argparse.Namespace(
        host="127.0.0.1", port=8765, timeout_ms=5000,
        command="send-command", worker_command="measure-stream-start",
        client_json=False,
    )
    worker_client._validate_status(runtime.status_payload(), args)
    invalid_status = runtime.status_payload()
    invalid_status["stream"] = {"lifecycle": "run_bound", "state": "active"}
    with pytest.raises(OscilloscopeError):
        worker_client._validate_status(invalid_status, args)

    response = {
        "schema_version": 3, "run_id": "r1", "status": "accepted",
        "command": "measure-stream-start", "job_id": None,
        "kind": "control", "worker_job_id": None, "error": None,
    }
    monkeypatch.setattr(
        worker_client, "_http_request",
        lambda *_args, **_kwargs: (response, 202),
    )
    assert worker_client.client_post(
        args, "/command", {
            "schema_version": 3, "command": "measure-stream-start",
            "arguments": {"measurements": MEASUREMENTS},
        },
    ) == 0

def test_stream_start_is_control_only_without_changing_domain_command_inventory():
    from scopes_tool_cli.worker_commands import (
        DOMAIN_COMMANDS, STREAM_CONTROL_COMMANDS, validate_command_request,
    )

    assert STREAM_CONTROL_COMMANDS == frozenset({"measure-stream-start"})
    assert not STREAM_CONTROL_COMMANDS.intersection(DOMAIN_COMMANDS)
    command, arguments, job_id = validate_command_request({
        "schema_version": 3,
        "command": "measure-stream-start",
        "arguments": {"measurements": MEASUREMENTS},
        "job_id": "control-one",
    })
    assert command == "measure-stream-start"
    assert arguments == {"measurements": MEASUREMENTS}
    assert job_id == "control-one"


def test_tektronix_worker_setup_is_reused_by_finite_multi_measure_stream():
    with _streaming_worker("tektronix-tbs2074") as (ready, events, records, proc):
        code, job = _post(ready["command_url"], "channel-display", {
            "channel": 2, "off": True,
        })
        assert code == 202 and job["kind"] == "async_job"
        setup = _event(events, "job_finished")
        assert setup["state"] == "succeeded"
        code, response = _post(ready["command_url"], "measure-stream-start", {
            "measurements": MEASUREMENTS, "count": 2, "interval_seconds": 0,
        })
        assert code == 202 and response["kind"] == "control"
        while True:
            status = _event(events, "status")
            if status["stream"]["state"] == "active":
                break
        samples = [_event(events, "sample") for _ in range(2)]
        assert [sample["index"] for sample in samples] == [1, 2]
        for sample in samples:
            assert sample["values"]["ch1_frequency"]["valid"] is True
            missing = sample["values"]["ch2_vpp"]
            assert missing["valid"] is False and missing["value"] is None
            assert missing["reason"]
        ended = _event(events, "status")
        assert ended["stream"]["state"] == "ended"
        assert _post(ready["stop_url"])[0] == 202
        summary = _event(events, "summary")
        assert summary["ok"] is True
        assert summary["stream_summary"]["completed_cycles"] == 2
        assert summary["stream_summary"]["invalid_measurements"] == 2
        assert summary["stream_summary"]["stop_reason"] == "count_reached"
        proc.wait(timeout=8)
        assert proc.returncode == 0
        assert not [e for e in records[records.index(ended) + 1:]
                    if e["event"] == "sample"]


def test_start_stop_interleaving_never_exposes_unstarted_stream_thread(monkeypatch):
    from http.server import ThreadingHTTPServer
    from scopes_tool_cli import worker

    runtime = worker.WorkerRuntime(
        host="127.0.0.1", port=0, mode="simulate",
        model="keysight-dsox4024a", resource=None,
        queue_max=32, output_format="jsonl", streaming=True,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), worker._make_handler(runtime))
    runtime.port = server.server_port
    runtime.server = server
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    reached_start = threading.Event()
    release_start = threading.Event()
    original_start = threading.Thread.start

    def controlled_start(thread):
        if getattr(thread, "_target", None) is worker._stream_loop:
            reached_start.set()
            assert release_start.wait(timeout=5)
        return original_start(thread)

    monkeypatch.setattr(threading.Thread, "start", controlled_start)
    start_response = []
    stop_response = []
    stop_done = threading.Event()

    def request_start():
        start_response.append(_post(runtime.control_urls()["command_url"],
                                    "measure-stream-start", {
                                        "measurements": MEASUREMENTS, "count": 1,
                                    }))

    def request_stop():
        try:
            stop_response.append(_post(runtime.control_urls()["stop_url"]))
        finally:
            stop_done.set()

    first = threading.Thread(target=request_start)
    second = threading.Thread(target=request_stop)
    try:
        first.start()
        assert reached_start.wait(timeout=5)
        second.start()
        assert not stop_done.wait(timeout=0.2)
        release_start.set()
        first.join(timeout=6)
        second.join(timeout=6)
        assert not first.is_alive() and not second.is_alive()
        assert start_response[0][0] == 202
        assert stop_response[0][0] == 202
        assert runtime.stream_thread is not None
        runtime.stream_thread.join(timeout=5)
        assert not runtime.stream_thread.is_alive()
        assert runtime.stream_state == "ended"
    finally:
        release_start.set()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
