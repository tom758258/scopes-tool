import math

import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path, model="keysight-dsox4024a"):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model=model,
        resource=None,
                queue_max=1,
        output_format="jsonl",
    )


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("demo-query", {}),
        ("demo-output", {"query": True}),
        ("demo-output", {"enabled": True}),
        ("demo-output", {"enabled": False}),
        ("demo-function", {"query": True}),
        ("demo-function", {"function": "runt"}),
        ("demo-phase", {"query": True}),
        ("demo-phase", {"degrees": 90}),
        ("demo-phase", {"degrees": 90.5}),
    ],
)
def test_worker_demo_accepts_exact_canonical_payloads(tmp_path, command, arguments):
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))
    assert parsed.command == command


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("demo-query", {"query": True}),
        ("demo-query", {"enabled": True}),
        ("demo-output", {}),
        ("demo-output", {"query": False}),
        ("demo-output", {"query": True, "enabled": True}),
        ("demo-output", {"enabled": "true"}),
        ("demo-output", {"enabled": None}),
        ("demo-output", {"output": True}),
        ("demo-output", {"on": True}),
        ("demo-output", {"state": True}),
        ("demo-output", {"value": True}),
        ("demo-function", {}),
        ("demo-function", {"query": False}),
        ("demo-function", {"query": True, "function": "runt"}),
        ("demo-function", {"function": 1}),
        ("demo-function", {"function": "RUNT"}),
        ("demo-function", {"function": None}),
        ("demo-function", {"signal": "runt"}),
        ("demo-function", {"type": "runt"}),
        ("demo-function", {"demo": "runt"}),
        ("demo-function", {"mode": "runt"}),
        ("demo-phase", {}),
        ("demo-phase", {"query": False}),
        ("demo-phase", {"query": True, "degrees": 90}),
        ("demo-phase", {"degrees": "90"}),
        ("demo-phase", {"degrees": True}),
        ("demo-phase", {"degrees": None}),
        ("demo-phase", {"degrees": math.nan}),
        ("demo-phase", {"degrees": math.inf}),
        ("demo-phase", {"degrees": -0.1}),
        ("demo-phase", {"degrees": 360.1}),
        ("demo-phase", {"angle": 90}),
        ("demo-phase", {"phase": 90}),
        ("demo-phase", {"degree": 90}),
    ],
)
def test_worker_demo_rejects_noncanonical_payloads_before_artifacts(tmp_path, command, arguments):
    runtime = _runtime(tmp_path)
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, runtime)
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_demo_rejects_profile_unsupported_function_before_artifacts(tmp_path):
    runtime = _runtime(tmp_path, model="keysight-dsox2004a")
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("demo-function", {"function": "i2s"}, runtime)
    assert not (tmp_path / runtime.run_id).exists()


@pytest.mark.parametrize(
    "command, arguments, expected",
    [
        ("demo-query", {}, [":DEMO:FUNCtion?", ":DEMO:OUTPut?", ":DEMO:FUNCtion:PHASe:PHASe?"]),
        ("demo-output", {"enabled": True}, [":DEMO:OUTPut ON"]),
        ("demo-function", {"function": "glitch"}, [":DEMO:FUNCtion GLIT"]),
        ("demo-phase", {"degrees": 90}, [":DEMO:FUNCtion:PHASe:PHASe 90"]),
    ],
)
def test_worker_demo_simulator_routing(tmp_path, command, arguments, expected):
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    sent = payload["scpi"]["sent"]
    for scpi in expected:
        assert scpi in sent
    assert sent[-1] == ":SYSTem:ERRor?"
