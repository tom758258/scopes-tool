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
    "command, arguments",
    [
        ("dvm-enable", {"query": True}),
        ("dvm-enable", {"enabled": True}),
        ("dvm-enable", {"enabled": False}),
        ("dvm-source", {"query": True}),
        ("dvm-source", {"channel": 1}),
        ("dvm-mode", {"query": True}),
        ("dvm-mode", {"mode": "dc"}),
        ("dvm-mode", {"mode": "dc-rms"}),
        ("dvm-mode", {"mode": "ac-rms"}),
        ("dvm-auto-range", {"query": True}),
        ("dvm-auto-range", {"enabled": True}),
        ("dvm-auto-range", {"enabled": False}),
        ("dvm-current", {"query": True}),
        ("dvm-query", {"query": True}),
    ],
)
def test_worker_dvm_accepts_canonical_payloads(tmp_path, command, arguments):
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))
    assert parsed.command == command


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("dvm-enable", {}),
        ("dvm-enable", {"query": False}),
        ("dvm-enable", {"query": True, "enabled": True}),
        ("dvm-enable", {"enabled": "true"}),
        ("dvm-enable", {"enabled": 1}),
        ("dvm-source", {"channel": "1"}),
        ("dvm-source", {"channel": 0}),
        ("dvm-source", {"channel": -1}),
        ("dvm-source", {"channel": 5}),
        ("dvm-source", {"source": "CHAN1"}),
        ("dvm-source", {"source_channel": 1}),
        ("dvm-mode", {"mode": "frequency"}),
        ("dvm-mode", {"mode": "freq"}),
        ("dvm-mode", {"mode": "DCRMS"}),
        ("dvm-mode", {"mode": "ACRMS"}),
        ("dvm-mode", {"mode": "dcrms"}),
        ("dvm-mode", {"mode": "acrms"}),
        ("dvm-auto-range", {"auto": True}),
        ("dvm-current", {}),
        ("dvm-current", {"query": False}),
        ("dvm-query", {}),
        ("dvm-query", {"query": True, "enabled": True}),
    ],
)
def test_worker_dvm_rejects_noncanonical_payloads_before_artifacts(tmp_path, command, arguments):
    runtime = _runtime(tmp_path)
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, runtime)
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


@pytest.mark.parametrize("command", ["dvm-frequency", "counter-enable", "counter-query"])
def test_worker_keeps_out_of_scope_commands_unknown(command):
    with pytest.raises(OscilloscopeError, match="unknown command"):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": command,
                "arguments": {},
            }
        )


def test_worker_dvm_query_simulator_execution(tmp_path):
    parsed = worker.parse_domain_command("dvm-query", {"query": True}, _runtime(tmp_path))
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert payload["result"]["mode"] == "dc"
    assert payload["result"]["source_channel"] == 1
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":DVM:ENABle?",
        ":DVM:SOURce?",
        ":DVM:MODE?",
        ":DVM:ARANge?",
        ":DVM:CURRent?",
        ":SYSTem:ERRor?",
    ]
