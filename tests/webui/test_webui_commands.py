from __future__ import annotations

import asyncio
import time
import threading

import pytest
from fastapi.testclient import TestClient

from scopes_tool_core.dvm import DVM_MODES
from scopes_tool_core.math import MATH_COMPOSITE_OPERATIONS, MATH_OPERATIONS, MATH_SOURCES
from scopes_tool_core.measurements import (
    MEASUREMENT_WINDOW_CHOICES,
    SINGLE_CHANNEL_MEASUREMENT_ITEMS,
    SUPPORTED_MEASUREMENT_ITEMS,
)
import scopes_tool_webui.app as app_module
import scopes_tool_webui.commands as commands_module
from scopes_tool_webui.app import app
from scopes_tool_webui.commands import ScopeSessionCloseError, validate_job_request
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


def test_command_catalog_projects_setting_and_model_presentation() -> None:
    commands = {
        entry["id"]: entry
        for entry in TestClient(app).get("/api/commands").json()
    }

    channel_scale = commands["channel-scale"]
    assert channel_scale["presentation"]["kind"] == "setting"
    assert channel_scale["presentation"]["action"] == "apply"
    assert channel_scale["presentation"]["query_fields"] == ["channel"]
    for command_id, value_name in (
        ("timebase-scale", "seconds_per_division"),
        ("timebase-position", "position_seconds"),
    ):
        timebase = commands[command_id]
        assert timebase["presentation"]["kind"] == "setting"
        assert timebase["presentation"]["action"] == "apply"
        assert timebase["presentation"]["query_fields"] == []
        assert next(
            field for field in timebase["fields"] if field["name"] == value_name
        )["required_if"] == [{"field": "action", "equals": "set"}]

    model_2000x = "keysight-dsox2004a"
    impedance = commands["channel-impedance"]["presentation"]["models"][model_2000x]
    assert impedance["fields"]["impedance"]["options"] == ["one_meg"]
    math_display = commands["math-display"]["presentation"]["models"][model_2000x]
    assert math_display["fields"]["function"]["maximum"] == 1
    assert commands["measure-results"]["presentation"]["models"][model_2000x]["supported"] is False
    serial_mode = commands["serial-mode"]["presentation"]["models"][model_2000x]
    assert serial_mode["fields"]["mode"]["options"] == ["can", "i2c", "lin", "spi", "uart"]
    search_mode = commands["search-mode"]["presentation"]["models"][model_2000x]
    assert search_mode["fields"]["mode"]["options"] == ["serial1"]
    assert commands["segmented-capture"]["presentation"]["models"][model_2000x]["fields"]["segments"]["maximum"] == 250
    assert "delay" not in commands["measure"]["presentation"]["models"][model_2000x]["fields"]["item"]["options"]
    segmented = commands["segmented-memory"]["presentation"]
    assert segmented["kind"] == "setting"
    assert segmented["query_value"] == "query"
    assert segmented["action_choices"] == ["enable", "disable"]
    assert commands["measure-source"]["presentation"]["readback_fields"] == {
        "source_channel": "source1_channel"
    }
    assert commands["math-vertical"]["presentation"]["readback_fields"] == {
        "range_value": "range"
    }
    assert commands["trigger-pulse-width"]["presentation"]["readback_fields"] == {
        "time_seconds": {
            "selector_field": "qualifier",
            "fields": {
                "greater-than": "greater_than_seconds",
                "less-than": "less_than_seconds",
            },
        },
        "min_time_seconds": "range_min_seconds",
        "max_time_seconds": "range_max_seconds",
        "level": "level_volts",
    }
    assert commands["trigger-tv"]["presentation"]["readback_fields"] == {
        "mode": "tv_mode"
    }
    vectors = commands["display-vectors"]["presentation"]
    assert {key: value for key, value in vectors.items() if key != "models"} == {
        "kind": "one-way",
        "action": "enable",
        "action_field": "action",
        "apply_value": "set",
    }
    assert commands["measure-show"]["presentation"]["kind"] == "one-way"
    assert commands["measure-show"]["presentation"]["action"] == "show"

    persistence_fields = {
        field["name"]: field for field in commands["display-persistence"]["fields"]
    }
    assert persistence_fields["mode"]["options"] == ["minimum", "infinite", "timed"]
    assert persistence_fields["seconds"]["visible_if"][-1] == {
        "field": "mode",
        "equals": "timed",
    }

    workflow_fields = {
        field["name"]: field for field in commands["measure-log"]["fields"]
    }
    assert workflow_fields["channels"]["type"] == "multi-enum"
    assert workflow_fields["channels"]["serialize"] == "csv"
    assert workflow_fields["items"]["options"] == list(SINGLE_CHANNEL_MEASUREMENT_ITEMS)
    assert workflow_fields["pairs"]["help"]
    workflow_model = commands["measure-log"]["presentation"]["models"][MODEL_ID]
    assert workflow_model["fields"]["channels"]["options"] == [1, 2, 3, 4]


def test_simulated_timebase_and_display_persistence_use_setting_readback() -> None:
    client = TestClient(app)

    scale = submit(
        client,
        "timebase-scale",
        "simulate",
        {"action": "set", "seconds_per_division": 0.002},
    )
    assert scale["status"] == "completed"
    assert scale["result"]["result"]["timebase"] == {
        "seconds_per_division": 0.002
    }

    position = submit(
        client,
        "timebase-position",
        "simulate",
        {"action": "set", "position_seconds": -0.0005},
    )
    assert position["status"] == "completed"
    assert position["result"]["result"]["timebase"] == {
        "position_seconds": -0.0005
    }

    persistence = submit(
        client,
        "display-persistence",
        "simulate",
        {"action": "set", "mode": "timed", "seconds": 2.5},
    )
    assert persistence["status"] == "completed"
    assert persistence["result"]["result"]["persistence"]["mode"] == "timed"
    assert persistence["result"]["result"]["persistence"]["seconds"] == 2.5


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


def test_commands_expose_the_p3b_reference_and_save_subset() -> None:
    client = TestClient(app)

    response = client.get("/api/commands")

    assert response.status_code == 200
    commands = {entry["id"]: entry for entry in response.json()}
    expected = {
        "reference-save",
        "reference-display",
        "reference-label",
        "reference-clear",
        "reference-query",
        "save-pwd",
        "save-filename",
        "save-image-format",
        "save-image-palette",
        "save-image-ink-saver",
        "save-image-factors",
        "save-image",
        "save-waveform-format",
        "save-waveform-length",
        "save-waveform-length-max",
        "save-waveform",
    }

    assert expected <= commands.keys()
    for command in expected:
        assert commands[command]["modes"] == ["live", "simulate"]


def test_representative_p3b_simulated_commands_complete_without_artifacts() -> None:
    client = TestClient(app)

    reference = submit(
        client,
        "reference-label",
        "simulate",
        {"action": "set", "slot": 1, "label": "BASELINE"},
    )
    assert reference["status"] == "completed"
    assert reference["result"]["result"]["label"]["label"] == "BASELINE"

    save_setting = submit(
        client,
        "save-image-format",
        "simulate",
        {"action": "set", "format": "bmp24"},
    )
    assert save_setting["status"] == "completed"
    assert save_setting["result"]["result"]["state"]["format"] == "bmp24"

    save = submit(client, "save-image", "simulate", {"filename": "screen.png"})
    assert save["status"] == "completed"
    assert save["artifacts"] == []
    assert save["result"]["result"]["save"]["instrument_side"] is True


def test_p3b_save_filename_validation_is_preserved() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        json={
            "command": "save-image",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"filename": "screen;bad.png"},
        },
    )

    assert response.status_code == 400
    assert "filename" in response.json()["detail"].lower()


def test_query_only_commands_do_not_default_set_only_channels() -> None:
    client = TestClient(app)

    response = client.get("/api/commands")

    assert response.status_code == 200
    commands = {entry["id"]: entry for entry in response.json()}
    measure_source = next(field for field in commands["measure-source"]["fields"] if field["name"] == "source_channel")
    dvm_source = next(field for field in commands["dvm-source"]["fields"] if field["name"] == "channel")
    assert "default" not in measure_source
    assert "default" not in dvm_source


def test_measure_and_dvm_query_requests_complete_without_set_only_channels() -> None:
    client = TestClient(app)

    for command in ("measure-source", "dvm-source"):
        job = submit(client, command, "simulate", {"action": "query"})
        assert job["status"] == "completed", (command, job)


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
    asyncio.run(manager.shutdown())
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


def test_running_cancel_api_stays_running_until_cleanup(monkeypatch) -> None:
    manager = JobManager()
    started = threading.Event()
    release = threading.Event()

    def blocking_execute(*_args, **_kwargs):
        started.set()
        release.wait(timeout=2)
        return {"exit_code": 0, "result": {"ok": True}, "artifacts": []}

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", blocking_execute)
    monkeypatch.setattr(app_module, "job_manager", manager)
    client = TestClient(app)
    response = client.post(
        "/api/jobs",
        json={
            "command": "identify",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {},
        },
    )
    job_id = response.json()["job_id"]
    try:
        assert started.wait(timeout=2)
        cancelled = client.post(f"/api/jobs/{job_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "running"
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "running"

        release.set()
        terminal = wait_for_job(client, job_id)
        assert terminal["status"] == "cancelled"
    finally:
        release.set()
        asyncio.run(manager.shutdown(timeout_s=2))


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


def test_queued_and_running_job_cancellation_requests_are_accepted(monkeypatch) -> None:
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
        running_state, running_message, running_accepted = manager.cancel(jobs[0].job_id)
        assert running_state == "running"
        assert "waiting for cleanup" in running_message
        assert running_accepted is True
        assert manager.get(jobs[0].job_id).status == "running"
        assert manager.get(jobs[0].job_id).cancel_requested is True

        queued = manager.submit(request)
        queued_state, _queued_message, queued_accepted = manager.cancel(queued.job_id)
        assert queued_state == "cancelled"
        assert queued_accepted is True
        assert manager.get(queued.job_id).status == "cancelled"
    finally:
        release.set()
        asyncio.run(manager.shutdown(timeout_s=2))


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
            shutdown_errors, _run_manager_shutdown, manager=manager, timeout_s=2
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
        assert all(manager.get(job.job_id).status == "cancelled" for job in jobs[:4])
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
            asyncio.run(manager.shutdown(timeout_s=0.05))
        assert shutdown_calls == []
        release.set()
        asyncio.run(manager.shutdown(timeout_s=2))
        assert shutdown_calls == [((), {"wait": True})]
        assert manager.get(job.job_id).status == "cancelled"
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
            shutdown_errors, _run_manager_shutdown, manager=manager, timeout_s=2
        )
    )
    try:
        assert started.wait(timeout=2)
        shutdown_thread.start()
        for _ in range(100):
            if manager.get(job.job_id).cancel_requested:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("shutdown did not request cancellation")
        release.set()
        shutdown_thread.join(timeout=2)
        assert len(shutdown_errors) == 1
        assert isinstance(shutdown_errors[0], RuntimeError)
        assert "cleanup failed" in str(shutdown_errors[0])
        completed = _wait_for_manager_job(manager, job.job_id)
        assert completed.status == "failed"
        assert "close failed" in completed.error
        with pytest.raises(RuntimeError, match="cleanup failed"):
            asyncio.run(manager.shutdown(timeout_s=2))
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


def _run_manager_shutdown(manager, timeout_s):
    asyncio.run(manager.shutdown(timeout_s=timeout_s))


def _wait_for_manager_job(manager, job_id):
    for _ in range(100):
        job = manager.get(job_id)
        if job.status not in {"queued", "running"}:
            return job
        time.sleep(0.02)
    raise AssertionError("manager job did not reach a terminal state")


@pytest.mark.parametrize(
    ("command", "runner_name", "parameters"),
    (
        ("capture-batch", "run_capture_batch", {"channels": (1,), "points": 1000, "format": "byte", "count": 2, "interval_seconds": 0}),
        ("measure-log", "run_measure_log", {"channels": (1,), "items": ("vpp",), "pairs": (), "pair_items": (), "interval_seconds": 0, "count": 2}),
        ("measure-until", "run_measure_until", {"channel": 1, "item": "vpp", "operator": "gt", "threshold": 0.1, "timeout_seconds": 1, "interval_seconds": 0}),
        ("triggered-measure-loop", "run_triggered_measure_loop", {"count": 2, "trigger_timeout_seconds": 1, "channels": (1,), "items": ("vpp",), "pairs": (), "pair_items": (), "interval_seconds": 0}),
        ("triggered-capture-series", "run_triggered_capture_series", {"channels": (1,), "count": 2, "trigger_timeout_seconds": 1, "points": 1000, "format": "byte", "interval_seconds": 0}),
    ),
)
def test_long_workflows_receive_existing_core_stop_callback(
    monkeypatch,
    tmp_path,
    command,
    runner_name,
    parameters,
) -> None:
    stop_requested = lambda: True
    received = []

    def fake_runner(_scope, _resource, _request, *, stop_requested=None):
        received.append(stop_requested)
        return commands_module.OperationResult(exit_code=0, result={"status": "cancelled"})

    monkeypatch.setattr(commands_module, runner_name, fake_runner)

    commands_module._execute_p3c_scope_command(
        object(),
        command,
        "USB0::TEST::INSTR",
        parameters,
        tmp_path,
        stop_requested=stop_requested,
    )

    assert received == [stop_requested]


def test_commands_expose_p3c_families_and_conditional_fields() -> None:
    client = TestClient(app)
    response = client.get("/api/commands")
    assert response.status_code == 200
    commands = {entry["id"]: entry for entry in response.json()}
    expected = {
        "trigger-edge",
        "trigger-pulse-width",
        "trigger-delay",
        "trigger-tv",
        "search-mode",
        "serial-search-uart",
        "serial-uart",
        "serial-trigger-can",
        "serial-lister-export",
        "segmented-memory",
        "segmented-capture",
        "capture-batch",
        "measure-log",
        "measure-until",
        "triggered-measure-loop",
        "triggered-capture-series",
    }
    assert expected <= commands.keys()
    assert commands["segmented-capture"]["modes"] == ["live", "simulate", "dry-run"]
    assert commands["capture-batch"]["modes"] == ["live", "simulate"]
    pulse_fields = {field["name"]: field for field in commands["trigger-pulse-width"]["fields"]}
    assert pulse_fields["time_seconds"]["visible_if"] == [
        {"field": "action", "equals": "set"},
        {"field": "qualifier", "in": ["greater-than", "less-than"]},
    ]


def test_command_catalog_exposes_required_field_contracts() -> None:
    client = TestClient(app)
    commands = {entry["id"]: entry for entry in client.get("/api/commands").json()}

    reference_fields = {
        field["name"]: field for field in commands["reference-save"]["fields"]
    }
    assert reference_fields["slot"]["required"] is True
    assert reference_fields["source_channel"]["required"] is True

    scale_fields = {
        field["name"]: field for field in commands["channel-scale"]["fields"]
    }
    assert scale_fields["volts_per_division"]["required_if"] == [
        {"field": "action", "equals": "set"}
    ]
    assert "required" not in scale_fields["volts_per_division"]


def test_p3c_request_validation_regressions() -> None:
    client = TestClient(app)
    commands = {entry["id"]: entry for entry in client.get("/api/commands").json()}
    assert [field["name"] for field in commands["serial-query"]["fields"]] == ["bus"]

    serial_query = client.post(
        "/api/jobs",
        json={
            "command": "serial-query",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"bus": 1, "action": "query"},
        },
    )
    assert serial_query.status_code == 400
    assert "unknown parameter" in serial_query.json()["detail"]

    for parameters in (
        {"action": "query", "bus": 1, "mode": "async"},
        {"action": "query", "bus": 1, "data": 1},
    ):
        serial_search = client.post(
            "/api/jobs",
            json={
                "command": "serial-search-uart",
                "mode": "simulate",
                "model_id": MODEL_ID,
                "parameters": parameters,
            },
        )
        assert serial_search.status_code == 400
        assert "query cannot include" in serial_search.json()["detail"]

    invalid_measure_log = client.post(
        "/api/jobs",
        json={
            "command": "measure-log",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"count": 1, "stop_on_error": "false"},
        },
    )
    assert invalid_measure_log.status_code == 400
    assert "stop_on_error must be a boolean" in invalid_measure_log.json()["detail"]

    accepted = validate_job_request(
        {
            "command": "measure-log",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"count": 1, "stop_on_error": True},
        }
    )
    assert accepted["parameters"]["stop_on_error"] is True

    defaulted = validate_job_request(
        {
            "command": "measure-log",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"count": 1},
        }
    )
    assert defaulted["parameters"]["stop_on_error"] is False


def test_representative_p3c_simulated_commands_complete() -> None:
    client = TestClient(app)
    for command, parameters in (
        ("trigger-edge", {"action": "set", "source_channel": 1, "level": 0.1, "slope": "positive"}),
        ("search-mode", {"action": "set", "mode": "edge"}),
        ("serial-mode", {"action": "set", "bus": 1, "mode": "uart"}),
        ("serial-uart", {"action": "set", "bus": 1, "baud_rate": 9600, "data_bits": 8, "parity": "none"}),
        ("segmented-memory", {"action": "enable", "segments": 2}),
        ("capture-batch", {"channels": "1", "points": 1000, "format": "byte", "count": 1, "interval_seconds": 0}),
    ):
        job = submit(client, command, "simulate", parameters)
        assert job["status"] == "completed", (command, job)


def test_p3c_dry_run_planners_and_conditional_validation() -> None:
    client = TestClient(app)
    job = submit(
        client,
        "measure-until",
        "dry-run",
        {"channel": 1, "item": "vpp", "operator": "gt", "threshold": 0.1, "timeout_seconds": 1, "interval_seconds": 0},
    )
    assert job["status"] == "completed"
    assert job["result"]["result"]["status"] == "planned"

    rejected = client.post(
        "/api/jobs",
        json={
            "command": "trigger-pulse-width",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "query", "time_seconds": 1},
        },
    )
    assert rejected.status_code == 400
    assert "query" in rejected.json()["detail"].lower()


def test_p3c_serial_lister_export_registers_only_its_host_artifact() -> None:
    client = TestClient(app)
    job = submit(client, "serial-lister-export", "simulate", {"output": "lister.csv"})
    assert job["status"] == "completed"
    assert [artifact["name"] for artifact in job["artifacts"]] == ["lister.csv"]
    artifact = client.get(job["artifacts"][0]["url"])
    assert artifact.status_code == 200
    assert artifact.content
