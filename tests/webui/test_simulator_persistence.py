from __future__ import annotations

import asyncio
import threading
import time

import pytest

from scopes_tool_webui.commands import validate_job_request
from scopes_tool_webui.jobs import JobManager


MODEL_4024 = "keysight-dsox4024a"
MODEL_4034 = "keysight-dsox4034a"


def _wait(manager: JobManager, job_id: str):
    for _ in range(300):
        job = manager.get(job_id)
        assert job is not None
        if job.status not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError("WebUI simulation job did not reach a terminal state")


def _run(manager: JobManager, tmp_path, command: str, parameters: dict, *, model_id=MODEL_4024):
    request = validate_job_request(
        {
            "command": command,
            "mode": "simulate",
            "model_id": model_id,
            "pc_output_dir": str(tmp_path),
            "parameters": parameters,
        }
    )
    return _wait(manager, manager.submit(request).job_id)


def test_simulate_math_state_persists_across_jobs_and_cross_family_reads_are_informational(
    tmp_path,
):
    manager = JobManager()
    try:
        initial = _run(
            manager,
            tmp_path,
            "math-visualization",
            {"action": "query", "function": 1},
        )
        assert initial.status == "completed"
        initial_state = initial.result["result"]["math_visualization"]
        assert initial_state == {
            "function": 1,
            "active": False,
            "active_family": "fft",
            "active_operation": "fft",
            "operation_raw": "FFT",
        }

        applied = _run(
            manager,
            tmp_path,
            "math-visualization",
            {
                "action": "set",
                "function": 1,
                "operation": "magnify",
                "source": "channel2",
            },
        )
        assert applied.status == "completed"
        assert applied.result["result"]["math_visualization"]["operation"] == "magnify"
        assert applied.result["result"]["math_visualization"]["source"] == "channel2"

        reread = _run(
            manager,
            tmp_path,
            "math-visualization",
            {"action": "query", "function": 1},
        )
        assert reread.status == "completed"
        assert reread.result["result"]["math_visualization"]["operation"] == "magnify"
        assert reread.result["result"]["math_visualization"]["source"] == "channel2"

        filter_read = _run(
            manager,
            tmp_path,
            "math-filter",
            {"action": "query", "function": 1},
        )
        assert filter_read.status == "completed"
        assert filter_read.result["result"]["math_filter"]["active"] is False
        assert filter_read.result["result"]["math_filter"]["active_family"] == "visualization"
        assert filter_read.result["result"]["math_filter"]["active_operation"] == "magnify"

        filter_set = _run(
            manager,
            tmp_path,
            "math-filter",
            {
                "action": "set",
                "function": 1,
                "operation": "low-pass",
                "source": "channel2",
                "cutoff_hz": 1000.0,
            },
        )
        assert filter_set.status == "completed"
        assert filter_set.result["result"]["math_filter"]["operation"] == "low-pass"
        assert filter_set.result["result"]["math_filter"]["cutoff_hz"] == pytest.approx(1000.0)

        fft_read = _run(
            manager,
            tmp_path,
            "fft",
            {"action": "query", "function": 1},
        )
        assert fft_read.status == "completed"
        assert fft_read.result["result"]["fft"]["active"] is False
        assert fft_read.result["result"]["fft"]["active_family"] == "filter"
        assert fft_read.result["result"]["fft"]["active_operation"] == "low-pass"
    finally:
        asyncio.run(manager.shutdown())


def test_simulate_persists_general_state_and_isolates_planning_models(tmp_path):
    manager = JobManager()
    try:
        set_scale = _run(
            manager,
            tmp_path,
            "channel-scale",
            {"action": "set", "channel": 1, "volts_per_division": 2.0},
        )
        assert set_scale.status == "completed"

        same_model = _run(
            manager,
            tmp_path,
            "channel-scale",
            {"action": "query", "channel": 1},
        )
        assert same_model.result["result"]["volts_per_division"] == pytest.approx(2.0)

        other_model = _run(
            manager,
            tmp_path,
            "channel-scale",
            {"action": "query", "channel": 1},
            model_id=MODEL_4034,
        )
        assert other_model.result["result"]["volts_per_division"] != pytest.approx(2.0)

        enabled = _run(
            manager,
            tmp_path,
            "segmented-memory",
            {"action": "enable", "segments": 4},
        )
        assert enabled.status == "completed"

        segmented = _run(
            manager,
            tmp_path,
            "segmented-memory",
            {"action": "query"},
        )
        state = segmented.result["result"]["segmented"]
        assert state["mode"] == "segmented"
        assert state["configured_segments"] == 4
    finally:
        asyncio.run(manager.shutdown())


def test_simulate_jobs_for_one_model_are_serialized(monkeypatch, tmp_path):
    manager = JobManager()
    first_started = threading.Event()
    release_first = threading.Event()
    calls: list[str] = []

    def fake_execute(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            first_started.set()
            release_first.wait(timeout=2)
        return {"exit_code": 0, "result": {"ok": True}, "artifacts": []}

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", fake_execute)
    request = validate_job_request(
        {
            "command": "identify",
            "mode": "simulate",
            "model_id": MODEL_4024,
            "pc_output_dir": str(tmp_path),
            "parameters": {},
        }
    )

    first = manager.submit(request)
    assert first_started.wait(timeout=2)
    second = manager.submit(request)
    time.sleep(0.05)
    assert calls == ["identify"]

    release_first.set()
    try:
        assert _wait(manager, first.job_id).status == "completed"
        assert _wait(manager, second.job_id).status == "completed"
        assert calls == ["identify", "identify"]
    finally:
        asyncio.run(manager.shutdown())
