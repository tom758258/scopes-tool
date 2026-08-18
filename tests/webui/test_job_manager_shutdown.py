from __future__ import annotations

import asyncio
import threading
import time

from scopes_tool_webui.jobs import JobManager, JobManagerShuttingDown


MODEL_ID = "keysight-dsox4024a"


def _request(resource: str) -> dict:
    return {
        "command": "identify",
        "mode": "live",
        "resource": resource,
        "model_id": MODEL_ID,
        "parameters": {},
    }


def test_idle_shutdown_succeeds_and_is_repeatable() -> None:
    manager = JobManager()

    asyncio.run(manager.shutdown())
    asyncio.run(manager.shutdown())

    try:
        manager.submit(_request("USB0::NEW::INSTR"))
    except JobManagerShuttingDown:
        pass
    else:
        raise AssertionError("shutdown manager accepted a new job")


def test_cancelled_hardware_lock_waiter_never_executes(monkeypatch) -> None:
    manager = JobManager()
    first_started = threading.Event()
    release_first = threading.Event()
    calls = []

    def blocking_execute(*_args, resource=None, **_kwargs):
        calls.append(resource)
        if resource == "USB0::A::INSTR":
            first_started.set()
            release_first.wait(timeout=2)
        return {"exit_code": 0, "result": {"ok": True}, "artifacts": []}

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", blocking_execute)
    first = manager.submit(_request("USB0::A::INSTR"))
    assert first_started.wait(timeout=2)
    waiting = manager.submit(_request("USB0::B::INSTR"))
    for _ in range(100):
        if manager.get(waiting.job_id).status == "running":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("second job did not start waiting for the hardware lock")

    errors = []

    def shutdown() -> None:
        try:
            asyncio.run(manager.shutdown(timeout_s=2))
        except BaseException as exc:
            errors.append(exc)

    shutdown_thread = threading.Thread(target=shutdown)
    shutdown_thread.start()
    for _ in range(100):
        if manager.get(waiting.job_id).cancel_requested:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("shutdown did not cancel the hardware lock waiter")

    release_first.set()
    shutdown_thread.join(timeout=2)

    assert errors == []
    assert calls == ["USB0::A::INSTR"]
    assert manager.get(first.job_id).status == "cancelled"
    assert manager.get(waiting.job_id).status == "cancelled"
