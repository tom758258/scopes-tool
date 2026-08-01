import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError


COMMAND_ARGUMENTS = {
    "system-clear-status": {},
    "system-opc": {"query": True},
    "system-status-byte": {"query": True},
    "system-standard-event": {"query": True},
    "system-operation-status": {"query": True},
    "system-options": {"query": True},
}
QUERY_COMMANDS = tuple(
    command for command in COMMAND_ARGUMENTS if command != "system-clear-status"
)


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


@pytest.mark.parametrize("command, arguments", COMMAND_ARGUMENTS.items())
def test_worker_accepts_canonical_system_status_payloads(tmp_path, command, arguments):
    assert command in worker.DOMAIN_COMMANDS
    accepted = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": command,
            "arguments": arguments,
        }
    )
    parsed = worker.parse_domain_command(accepted[0], accepted[1], _runtime(tmp_path))

    assert parsed.command == command


@pytest.mark.parametrize("command", QUERY_COMMANDS)
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": False},
        {"query": None},
        {"query": 1},
        {"query": "true"},
        {"query": True, "extra": 1},
        {"q": True},
    ],
)
def test_worker_rejects_noncanonical_system_query_payloads_before_side_effects(
    tmp_path, command, arguments
):
    runtime = _runtime(tmp_path)
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, runtime)

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


@pytest.mark.parametrize("arguments", [{"query": True}, {"extra": 1}, {"clear": True}])
def test_worker_clear_status_rejects_nonempty_arguments_before_side_effects(
    tmp_path, arguments
):
    runtime = _runtime(tmp_path)
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("system-clear-status", arguments, runtime)

    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


@pytest.mark.parametrize("arguments", [None, [], "", 0, 1])
def test_worker_request_rejects_non_object_system_arguments(arguments):
    with pytest.raises(OscilloscopeError, match="arguments must be a JSON object"):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": "system-opc",
                "arguments": arguments,
            }
        )


@pytest.mark.parametrize(
    "alias",
    ["system-cls", "system-stb", "system-esr", "system-operation", "system-opt"],
)
def test_worker_rejects_system_status_aliases(alias):
    with pytest.raises(OscilloscopeError, match="unknown command"):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": alias,
                "arguments": {"query": True},
            }
        )


@pytest.mark.parametrize("command, arguments", COMMAND_ARGUMENTS.items())
def test_worker_system_status_simulator_routing_is_structured(
    tmp_path, command, arguments
):
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["files"] == []
    assert payload["result"]["command"] in payload["scpi"]["sent"]
