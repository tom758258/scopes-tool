import pytest

from scopes_tool_cli import worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path, model="keysight-dsox4024a"):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model=model,
        resource=None,
        artifact_root=tmp_path,
        queue_max=1,
        output_format="jsonl",
    )


def test_worker_accepts_math_display_request(tmp_path):
    assert "math-display" in worker.DOMAIN_COMMANDS

    parsed = worker.parse_domain_command(
        "math-display",
        {"function": 1, "on": True},
        _runtime(tmp_path, "keysight-dsox2004a"),
    )

    assert parsed.command == "math-display"
    assert parsed.function == 1
    assert parsed.math_display_action == "on"


def test_worker_accepts_math_vertical_request(tmp_path):
    assert "math-vertical" in worker.DOMAIN_COMMANDS

    parsed = worker.parse_domain_command(
        "math-vertical",
        {"function": 2, "scale": 2.0, "offset": 0.5},
        _runtime(tmp_path),
    )

    assert parsed.command == "math-vertical"
    assert parsed.function == 2
    assert parsed.scale == 2.0
    assert parsed.offset == 0.5


def test_worker_rejects_unsupported_math_function_before_enqueue(tmp_path):
    runtime = _runtime(tmp_path, "keysight-dsox2004a")

    with pytest.raises(OscilloscopeError, match="between 1 and 1"):
        worker.parse_domain_command(
            "math-display",
            {"function": 2, "query": True},
            runtime,
        )

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()
