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
    ("arguments", "expected_result", "expected_history"),
    [
        (
            {"enable": True, "segments": 25},
            {"operation": "enable", "mode": "segmented", "configured_segments": 25},
            [
                "*IDN?",
                ":ACQuire:TYPE?",
                ":ACQuire:MODE SEGMented",
                ":ACQuire:SEGMented:COUNt 25",
                ":SYSTem:ERRor?",
            ],
        ),
        (
            {"disable": True},
            {"operation": "disable", "mode": "realtime", "configured_segments": None},
            ["*IDN?", ":ACQuire:MODE RTIMe", ":SYSTem:ERRor?"],
        ),
    ],
)
def test_segmented_memory_worker_routes_canonical_configuration_payloads(
    tmp_path, arguments, expected_result, expected_history
):
    command, normalized, job_id = worker.validate_command_request(
        {
            "schema_version": 2,
            "command": "segmented-memory",
            "arguments": arguments,
        }
    )
    parsed = worker.parse_domain_command(command, normalized, _runtime(tmp_path))
    payload, exit_code = cli._execute_json_command(parsed)

    assert (command, job_id) == ("segmented-memory", None)
    assert exit_code == 0
    assert {
        key: payload["result"][key] for key in expected_result
    } == expected_result
    assert payload["scpi"]["sent"] == expected_history


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": False},
        {"query": True, "model": "keysight-dsox4034a"},
        {"enable": True},
        {"enable": True, "segments": True},
        {"enable": True, "segments": 2.0},
        {"enable": True, "segments": "2"},
        {"disable": True, "segments": 2},
        {"query": True, "disable": True},
    ],
)
def test_segmented_memory_worker_rejects_noncanonical_arguments(tmp_path, arguments):
    with pytest.raises(OscilloscopeError, match="segmented-memory"):
        worker.validate_command_request(
            {
                "schema_version": 2,
                "command": "segmented-memory",
                "arguments": arguments,
            }
        )


def test_segmented_memory_worker_rejects_out_of_range_before_enqueue(tmp_path):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError, match="between 2 and 1000"):
        worker.parse_domain_command(
            "segmented-memory", {"enable": True, "segments": 1001}, runtime
        )

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()
