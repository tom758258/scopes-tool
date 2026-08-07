import time

from scopes_tool_core.workflow import interruptible_wait


def test_interruptible_wait_completes_normally():
    assert interruptible_wait(0.001) is True


def test_interruptible_wait_stops_early_when_cancelled():
    calls = 0

    def stop_requested():
        nonlocal calls
        calls += 1
        return calls >= 2

    started = time.monotonic()
    assert interruptible_wait(30.0, stop_requested=stop_requested) is False
    assert time.monotonic() - started < 1.0
