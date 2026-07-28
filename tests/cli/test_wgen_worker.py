import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model="keysight-dsox4024a",
        resource=None,
        artifact_root=tmp_path,
        queue_max=1,
        output_format="jsonl",
    )


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("wgen-query", {"query": True}),
        ("wgen-output", {"enabled": True}),
        ("wgen-function", {"function": "sine"}),
        ("wgen-frequency", {"hz": 1000}),
        ("wgen-voltage", {"amplitude": 0.5}),
        ("wgen-offset", {"volts": 0}),
        ("wgen-load", {"load": "one-meg"}),
    ],
)
def test_worker_wgen_accepts_explicit_valid_arguments(tmp_path, command, arguments):
    assert worker.parse_domain_command(command, arguments, _runtime(tmp_path)).command == command


@pytest.mark.parametrize("command", ["wgen-query", "wgen-output", "wgen-frequency"])
def test_worker_wgen_rejects_empty_or_missing_arguments(tmp_path, command):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, {}, _runtime(tmp_path))


def test_worker_wgen_routes_to_simulator(tmp_path):
    parsed = worker.parse_domain_command(
        "wgen-output", {"enabled": True}, _runtime(tmp_path)
    )
    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert ":WGEN1:OUTPut ON" in payload["scpi"]["sent"]
