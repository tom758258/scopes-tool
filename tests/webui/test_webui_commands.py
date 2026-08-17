from __future__ import annotations

import time
import threading

import pytest
from fastapi.testclient import TestClient

from scopes_tool_core.dvm import DVM_MODES
from scopes_tool_core.math import MATH_COMPOSITE_OPERATIONS, MATH_OPERATIONS, MATH_SOURCES
from scopes_tool_core.measurements import MEASUREMENT_WINDOW_CHOICES, SUPPORTED_MEASUREMENT_ITEMS
import scopes_tool_webui.app as app_module
from scopes_tool_webui.app import app
from scopes_tool_webui.commands import ScopeSessionCloseError
from scopes_tool_webui.jobs import JobManager, JobManagerShuttingDown


MODEL_ID = "keysight-dsox4024a"


def wait_for_job(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.02)
    raise AssertionError("WebUI job did not reach a terminal state")


def submit(client: TestClient, command: str, mode: str, parameters: dict) -> dict:
    response = client.post(
        "/api/jobs",
        json={
            "command": command,
            "mode": mode,
            "model_id": MODEL_ID,
            "parameters": parameters,
        },
    )
    assert response.status_code == 202
    return wait_for_job(client, response.json()["job_id"])


def test_commands_expose_the_p2_subset() -> None:
    client = TestClient(app)

    response = client.get("/api/commands")

    assert response.status_code == 200
    command_ids = {entry["id"] for entry in response.json()}
    assert {
        "identify",
        "acquisition",
        "channel-display",
        "channel-scale",
        "measure",
        "screenshot",
        "capture",
        "check-error",
        "system-status-byte",
        "system-operation-status",
    } <= command_ids
    assert "trigger" not in command_ids
    acquisition = next(entry for entry in response.json() if entry["id"] == "acquisition")
    action = next(field for field in acquisition["fields"] if field["name"] == "action")
    assert action["mode_options"]["dry-run"] == ["query"]
    measure = next(entry for entry in response.json() if entry["id"] == "measure")
    item = next(field for field in measure["fields"] if field["name"] == "item")
    assert item["options"] == list(SUPPORTED_MEASUREMENT_ITEMS)


def test_commands_expose_the_p3a_flat_subset() -> None:
    client = TestClient(app)

    response = client.get("/api/commands")

    assert response.status_code == 200
    command_ids = {entry["id"] for entry in response.json()}
    assert {
        "channel-summary",
        "channel-label",
        "channel-offset",
        "channel-coupling",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
        "display-label",
        "display-clear",
        "display-persistence",
        "display-intensity",
        "display-vectors",
        "measure-results",
        "measure-clear",
        "measure-show",
        "measure-source",
        "measure-window",
        "system-clear-status",
        "system-opc",
        "system-standard-event",
        "system-options",
        "dvm-enable",
        "dvm-source",
        "dvm-mode",
        "dvm-auto-range",
        "dvm-current",
        "dvm-query",
        "fft",
        "math-display",
        "math-vertical",
        "math-operator",
        "math-composite-source",
        "math-clear",
    } <= command_ids
    assert {"trigger", "math-transform", "math-filter", "math-visualization"}.isdisjoint(command_ids)

    dvm_mode = next(entry for entry in response.json() if entry["id"] == "dvm-mode")
    assert next(field for field in dvm_mode["fields"] if field["name"] == "mode")["options"] == list(DVM_MODES)
    measure_window = next(entry for entry in response.json() if entry["id"] == "measure-window")
    assert next(field for field in measure_window["fields"] if field["name"] == "window")["options"] == list(
        MEASUREMENT_WINDOW_CHOICES
    )
    math_operator = next(entry for entry in response.json() if entry["id"] == "math-operator")
    assert next(field for field in math_operator["fields"] if field["name"] == "operation")["options"] == list(
        MATH_OPERATIONS
    )
    assert next(field for field in math_operator["fields"] if field["name"] == "source1")["options"] == list(
        MATH_SOURCES
    )
    math_composite = next(entry for entry in response.json() if entry["id"] == "math-composite-source")
    assert next(field for field in math_composite["fields"] if field["name"] == "operation")["options"] == list(
        MATH_COMPOSITE_OPERATIONS
    )


def test_representative_p3a_simulated_commands_complete() -> None:
    client = TestClient(app)

    for command, parameters in (
        ("channel-offset", {"action": "set", "channel": 1, "volts": 0.25}),
        ("display-intensity", {"action": "set", "value": 75}),
        ("measure-window", {"action": "set", "window": "zoom"}),
        ("dvm-mode", {"action": "set", "mode": "dc-rms"}),
        (
            "fft",
            {
                "action": "set",
                "function": 1,
                "source_channel": 1,
                "units": "vrms",
                "window": "hanning",
                "display": True,
            },
        ),
        (
            "math-operator",
            {
                "action": "set",
                "function": 1,
                "operation": "add",
                "source1": "channel1",
                "source2": "channel2",
            },
        ),
    ):
        job = submit(client, command, "simulate", parameters)
        assert job["status"] == "completed", (command, job)


def test_p3a_invalid_and_unsupported_requests_are_rejected() -> None:
    client = TestClient(app)

    invalid = client.post(
        "/api/jobs",
        json={
            "command": "channel-coupling",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "set", "channel": 1, "coupling": "invalid"},
        },
    )
    assert invalid.status_code == 400

    fft_query = client.post(
        "/api/jobs",
        json={
            "command": "fft",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "query", "function": 1, "source_channel": 1},
        },
    )
    assert fft_query.status_code == 400
    assert "cannot include" in fft_query.json()["detail"]

    deferred = client.post(
        "/api/jobs",
        json={
            "command": "math-transform",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"function": 1},
        },
    )
    assert deferred.status_code == 400


def test_p3a_capability_rejection_remains_core_owned() -> None:
    client = TestClient(app)

    job = submit(
        client,
        "math-composite-source",
        "simulate",
        {"action": "set", "operation": "add", "source1": "channel1", "source2": "channel2"},
    )

    assert job["status"] == "failed"
    assert "not supported by this capability profile" in job["error"]


def test_simulated_measure_and_dry_run_capture_complete() -> None:
    client = TestClient(app)

    simulated = submit(client, "measure", "simulate", {"item": "vpp", "channel": 1})
    assert simulated["status"] == "completed"
    assert simulated["result"]["result"]["valid"] is True

    dry_run = submit(
        client,
        "capture",
        "dry-run",
        {"channel": 1, "points": 1000, "format": "byte"},
    )
    assert dry_run["status"] == "completed"
    assert dry_run["result"]["result"]["status"] == "planned"
    assert dry_run["result"]["result"]["planned_scpi"]


def test_dry_run_acquisition_query_is_planned() -> None:
    client = TestClient(app)

    job = submit(client, "acquisition", "dry-run", {"action": "query"})

    assert job["status"] == "completed"
    assert job["result"]["result"]["status"] == "planned"
    assert job["result"]["result"]["planned_scpi"]


def test_dry_run_acquisition_set_is_rejected_before_queueing(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(
        app_module.job_manager,
        "submit",
        lambda _request: pytest.fail("unsupported dry-run acquisition was queued"),
    )

    response = client.post(
        "/api/jobs",
        json={
            "command": "acquisition",
            "mode": "dry-run",
            "model_id": MODEL_ID,
            "parameters": {"action": "set", "type": "normal"},
        },
    )

    assert response.status_code == 400
    assert "query only" in response.json()["detail"]


def test_job_submission_returns_503_during_manager_shutdown(monkeypatch) -> None:
    manager = JobManager()
    manager.shutdown()
    monkeypatch.setattr(app_module, "job_manager", manager)
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        json={
            "command": "measure",
            "mode": "dry-run",
            "model_id": MODEL_ID,
            "parameters": {"item": "vpp", "channel": 1},
        },
    )

    assert response.status_code == 503
    assert "not accepted" in response.json()["detail"]


def test_simulated_capture_artifact_is_registered_and_downloadable() -> None:
    client = TestClient(app)

    job = submit(
        client,
        "capture",
        "simulate",
        {"channel": 1, "points": 1000, "format": "byte"},
    )

    assert job["status"] == "completed"
    artifact = next(item for item in job["artifacts"] if item["name"] == "capture.csv")
    response = client.get(artifact["url"])
    assert response.status_code == 200
    assert response.content


def test_invalid_request_is_rejected_before_queueing() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        json={
            "command": "capture",
            "mode": "live",
            "parameters": {"channel": 1, "points": 1000, "format": "byte"},
        },
    )

    assert response.status_code == 400
    assert "resource" in response.json()["detail"]


def test_only_queued_jobs_are_cancelled(monkeypatch) -> None:
    manager = JobManager()
    started = threading.Event()
    release = threading.Event()
    started_count = 0
    count_lock = threading.Lock()

    def blocking_execute(*_args, **_kwargs):
        nonlocal started_count
        with count_lock:
            started_count += 1
            if started_count == 4:
                started.set()
        release.wait(timeout=2)
        return {"exit_code": 0, "result": {"ok": True}, "artifacts": []}

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", blocking_execute)
    request = {
        "command": "identify",
        "mode": "simulate",
        "resource": None,
        "model_id": MODEL_ID,
        "parameters": {},
    }
    jobs = [manager.submit(request) for _ in range(4)]
    try:
        assert started.wait(timeout=2)
        running_state, running_message = manager.cancel(jobs[0].job_id)
        assert running_state == "running"
        assert "not cancellable" in running_message
        assert manager.get(jobs[0].job_id).status == "running"

        queued = manager.submit(request)
        queued_state, _queued_message = manager.cancel(queued.job_id)
        assert queued_state == "cancelled"
        assert manager.get(queued.job_id).status == "cancelled"
    finally:
        release.set()
        manager.shutdown(timeout_s=2)


def test_shutdown_rejects_new_jobs_and_waits_for_running_jobs(monkeypatch) -> None:
    manager = JobManager()
    started = threading.Event()
    release = threading.Event()
    started_count = 0
    count_lock = threading.Lock()

    def blocking_execute(*_args, **_kwargs):
        nonlocal started_count
        with count_lock:
            started_count += 1
            if started_count == 4:
                started.set()
        release.wait(timeout=2)
        return {"exit_code": 0, "result": {"ok": True}, "artifacts": []}

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", blocking_execute)
    request = {
        "command": "identify",
        "mode": "simulate",
        "resource": None,
        "model_id": MODEL_ID,
        "parameters": {},
    }
    jobs = [manager.submit(request) for _ in range(5)]
    shutdown_errors = []
    shutdown_thread = threading.Thread(
        target=lambda: _capture_exception(
            shutdown_errors, manager.shutdown, timeout_s=2
        )
    )
    try:
        assert started.wait(timeout=2)
        shutdown_thread.start()
        time.sleep(0.05)
        assert all(manager.get(job.job_id).status == "running" for job in jobs[:4])
        assert manager.get(jobs[4].job_id).status == "cancelled"
        with pytest.raises(JobManagerShuttingDown):
            manager.submit(request)
        assert shutdown_thread.is_alive()
        release.set()
        shutdown_thread.join(timeout=2)
        assert shutdown_errors == []
        assert all(manager.get(job.job_id).status == "completed" for job in jobs[:4])
    finally:
        release.set()
        shutdown_thread.join(timeout=2)
        if not manager._executor_shutdown:
            manager._executor.shutdown(wait=True)


def test_shutdown_timeout_leaves_executor_for_retry(monkeypatch) -> None:
    manager = JobManager()
    started = threading.Event()
    release = threading.Event()
    shutdown_calls = []
    original_shutdown = manager._executor.shutdown

    def blocking_execute(*_args, **_kwargs):
        started.set()
        release.wait(timeout=2)
        return {"exit_code": 0, "result": {"ok": True}, "artifacts": []}

    def recording_shutdown(*args, **kwargs):
        shutdown_calls.append((args, kwargs))
        return original_shutdown(*args, **kwargs)

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", blocking_execute)
    monkeypatch.setattr(manager._executor, "shutdown", recording_shutdown)
    request = {
        "command": "identify",
        "mode": "simulate",
        "resource": None,
        "model_id": MODEL_ID,
        "parameters": {},
    }
    job = manager.submit(request)
    try:
        assert started.wait(timeout=2)
        with pytest.raises(TimeoutError):
            manager.shutdown(timeout_s=0.05)
        assert shutdown_calls == []
        release.set()
        manager.shutdown(timeout_s=2)
        assert shutdown_calls == [((), {"wait": True})]
        assert manager.get(job.job_id).status == "completed"
    finally:
        release.set()
        if not manager._executor_shutdown:
            manager._executor.shutdown(wait=True)


def test_scope_close_failure_is_preserved_and_blocks_shutdown(monkeypatch) -> None:
    manager = JobManager()
    started = threading.Event()
    release = threading.Event()

    def close_failure(*_args, **_kwargs):
        started.set()
        release.wait(timeout=2)
        raise ScopeSessionCloseError("close failed")

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", close_failure)
    request = {
        "command": "identify",
        "mode": "simulate",
        "resource": None,
        "model_id": MODEL_ID,
        "parameters": {},
    }
    job = manager.submit(request)
    shutdown_errors = []
    shutdown_thread = threading.Thread(
        target=lambda: _capture_exception(
            shutdown_errors, manager.shutdown, timeout_s=2
        )
    )
    try:
        assert started.wait(timeout=2)
        shutdown_thread.start()
        release.set()
        shutdown_thread.join(timeout=2)
        assert len(shutdown_errors) == 1
        assert isinstance(shutdown_errors[0], RuntimeError)
        assert "cleanup failed" in str(shutdown_errors[0])
        completed = _wait_for_manager_job(manager, job.job_id)
        assert completed.status == "failed"
        assert "close failed" in completed.error
    finally:
        release.set()
        shutdown_thread.join(timeout=2)
        if not manager._executor_shutdown:
            manager._executor.shutdown(wait=True)


def _capture_exception(target, function, **kwargs):
    try:
        function(**kwargs)
    except BaseException as exc:
        target.append(exc)


def _wait_for_manager_job(manager, job_id):
    for _ in range(100):
        job = manager.get(job_id)
        if job.status not in {"queued", "running"}:
            return job
        time.sleep(0.02)
    raise AssertionError("manager job did not reach a terminal state")
