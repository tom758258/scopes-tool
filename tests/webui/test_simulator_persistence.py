from __future__ import annotations

import asyncio
import threading
import time

import pytest

import scopes_tool_webui.command_execution as command_execution
from scopes_tool_webui.commands import validate_job_request
from scopes_tool_webui.jobs import JobManager


MODEL_4024 = "keysight-dsox4024a"
MODEL_4034 = "keysight-dsox4034a"
MODEL_TEK = "tektronix-tbs2074b"
MODEL_TEK_OTHER = "tektronix-tds2024b"


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

        second_slot = _run(
            manager,
            tmp_path,
            "math-visualization",
            {
                "action": "set",
                "function": 2,
                "operation": "magnify",
                "source": "channel1",
            },
        )
        assert second_slot.status == "completed"
        assert second_slot.result["result"]["math_visualization"]["function"] == 2

        first_slot = _run(
            manager,
            tmp_path,
            "math-filter",
            {"action": "query", "function": 1},
        )
        assert first_slot.status == "completed"
        assert first_slot.result["result"]["math_filter"]["operation"] == "low-pass"
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

        back_to_first_model = _run(
            manager,
            tmp_path,
            "channel-scale",
            {"action": "query", "channel": 1},
        )
        assert back_to_first_model.result["result"]["volts_per_division"] == pytest.approx(2.0)

        timebase_set = _run(
            manager,
            tmp_path,
            "timebase-scale",
            {"action": "set", "seconds_per_division": 0.002},
        )
        assert timebase_set.status == "completed"
        timebase_read = _run(
            manager,
            tmp_path,
            "timebase-scale",
            {"action": "query"},
        )
        assert timebase_read.result["result"]["timebase"]["seconds_per_division"] == pytest.approx(0.002)

        wgen_set = _run(
            manager,
            tmp_path,
            "wgen-frequency",
            {"action": "set", "frequency_hz": 2500.0},
        )
        assert wgen_set.status == "completed"
        wgen_read = _run(
            manager,
            tmp_path,
            "wgen-frequency",
            {"action": "query"},
        )
        assert wgen_read.result["result"]["frequency"]["frequency_hz"] == pytest.approx(2500.0)

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


def test_tek_simulate_state_persists_and_isolates_planning_models(tmp_path):
    manager = JobManager()
    try:
        applied = _run(manager, tmp_path, "channel-scale", {
            "action": "set", "channel": 1, "volts_per_division": 2.0,
        }, model_id=MODEL_TEK)
        assert applied.status == "completed", applied.error
        same = _run(manager, tmp_path, "channel-scale", {
            "action": "query", "channel": 1,
        }, model_id=MODEL_TEK)
        assert same.status == "completed", same.error
        assert same.result["result"]["volts_per_division"] == pytest.approx(2.0)
        other = _run(manager, tmp_path, "channel-scale", {
            "action": "query", "channel": 1,
        }, model_id=MODEL_TEK_OTHER)
        assert other.status == "completed", other.error
        assert other.result["result"]["volts_per_division"] != pytest.approx(2.0)
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


def test_known_unmodeled_math_operation_is_informational_not_parse_failure():
    class OperationState:
        family = "other"
        operation = "bus-timing"
        operation_raw = "BTIM"

    class FakeScope:
        def query_math_operation(self, function):
            assert function == 1
            return OperationState()

        def query_math_visualization(self, _function):
            raise AssertionError("typed visualization query must not run for another family")

    result = command_execution._execute_math_visualization(
        FakeScope(),
        {"action": "query", "function": 1},
    )

    assert result == {
        "exit_code": 0,
        "result": {
            "math_visualization": {
                "function": 1,
                "active": False,
                "active_family": "other",
                "active_operation": "bus-timing",
                "operation_raw": "BTIM",
            }
        },
        "artifacts": [],
    }
