import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model="keysight-dsox4034a",
        resource=None,
        artifact_root=tmp_path,
        queue_max=1,
        output_format="jsonl",
    )


def test_segmented_memory_worker_routes_exact_query_payload(tmp_path):
    command, arguments, job_id = worker.validate_command_request(
        {
            "schema_version": 2,
            "command": "segmented-memory",
            "arguments": {"query": True},
        }
    )

    assert (command, arguments, job_id) == ("segmented-memory", {"query": True}, None)
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))
    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["result"]["mode"] == "realtime"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":ACQuire:MODE?",
        ":SYSTem:ERRor?",
    ]


@pytest.mark.parametrize(
    "arguments",
    [{}, {"query": False}, {"query": True, "model": "keysight-dsox4034a"}],
)
def test_segmented_memory_worker_rejects_noncanonical_arguments(tmp_path, arguments):
    with pytest.raises(OscilloscopeError, match="segmented-memory requires exactly query=true"):
        worker.validate_command_request(
            {
                "schema_version": 2,
                "command": "segmented-memory",
                "arguments": arguments,
            }
        )
