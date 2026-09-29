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
        ("demo-output", {"enabled": True}),
        ("demo-function", {"function": "runt"}),
        ("demo-phase", {"degrees": 90}),
    ],
)
def test_worker_demo_accepts_exact_canonical_payloads(tmp_path, command, arguments):
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))
    assert parsed.command == command


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("demo-query", {"query": True}),
        ("demo-output", {"enabled": "true"}),
        ("demo-output", {"output": True}),
        ("demo-function", {"function": "RUNT"}),
        ("demo-function", {"signal": "runt"}),
        ("demo-phase", {"degrees": "90"}),
        ("demo-phase", {"angle": 90}),
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
