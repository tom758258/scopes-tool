from contextlib import contextmanager
import json
from http.server import ThreadingHTTPServer
import threading
from urllib import error as urlerror
from urllib import request as urlrequest

import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_cli._worker_commands_trigger import (
    _normalize_trigger_common_worker_arguments,
)
from scopes_tool_cli.worker_commands import arguments_to_argv
from scopes_tool_core.errors import OscilloscopeError
from tests.cli._worker_test_support import make_worker_runtime


def _runtime(tmp_path):
    return make_worker_runtime()


@contextmanager
def _worker_server(runtime):
    server = ThreadingHTTPServer(("127.0.0.1", 0), worker._make_handler(runtime))
    runtime.port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield runtime
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _post_command(runtime, body):
    body = {**body, "schema_version": worker.WORKER_SCHEMA_VERSION}
    request = urlrequest.Request(
        f"http://127.0.0.1:{runtime.port}/command",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlrequest.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_worker_trigger_edge_coupling_command_is_accepted():
    command, arguments, job_id = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "trigger-edge-coupling",
            "arguments": {"query": True},
        }
    )
    assert command == "trigger-edge-coupling"
    assert arguments == {"query": True}
    assert job_id is None


def test_worker_trigger_edge_reject_command_is_accepted():
    command, arguments, job_id = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "trigger-edge-reject",
            "arguments": {"query": True},
        }
    )
    assert command == "trigger-edge-reject"
    assert arguments == {"query": True}
    assert job_id is None


@pytest.mark.parametrize(
    "command, arguments, expected",
    [
        ("trigger-edge-coupling", {"query": True}, ["trigger-edge-coupling", "--query"]),
        ("trigger-edge-coupling", {"coupling": "lf-reject"}, ["trigger-edge-coupling", "--coupling", "lf-reject"]),
        ("trigger-edge-reject", {"query": True}, ["trigger-edge-reject", "--query"]),
        ("trigger-edge-reject", {"reject": "hf-reject"}, ["trigger-edge-reject", "--reject", "hf-reject"]),
    ],
)
def test_worker_trigger_edge_coupling_reject_arguments_parse(tmp_path, command, arguments, expected):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(command, arguments, runtime)

    assert parsed.command == command
    assert arguments_to_argv(
        _normalize_trigger_common_worker_arguments(command, arguments)
    ) == expected[1:]


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("trigger-edge-coupling", {}),
        ("trigger-edge-coupling", {"coupling": "AC"}),
        ("trigger-edge-coupling", {"coupling": "ac", "unknown_field": "test"}),
        ("trigger-edge-reject", {}),
        ("trigger-edge-reject", {"reject": True}),
        ("trigger-edge-reject", {"reject": "OFF"}),
        ("edge-trigger-coupling", {"query": True}),
        ("edge-trigger-reject", {"query": True}),
    ],
)
def test_worker_trigger_edge_coupling_reject_rejects_invalid_arguments(tmp_path, command, arguments):
    runtime = _runtime(tmp_path)
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, runtime)


@pytest.mark.parametrize(
    "body",
    [
        {"command": "trigger-edge-coupling", "arguments": {}},
        {"command": "trigger-edge-coupling", "arguments": {"coupling": "AC"}},
        {"command": "trigger-edge-reject", "arguments": {}},
        {"command": "edge-trigger-reject", "arguments": {"query": True}},
    ],
)
def test_worker_trigger_edge_coupling_reject_rejects_before_enqueue_or_artifacts(tmp_path, body):
    runtime = _runtime(tmp_path)

    with _worker_server(runtime):
        status, payload = _post_command(runtime, body)

    assert status == 400
    assert payload["status"] == "error"
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_trigger_edge_coupling_simulator_execution(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-edge-coupling",
        {"coupling": "lf-reject"},
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["result"]["coupling"] == "lf-reject"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:EDGE:COUPling LFReject",
        ":SYSTem:ERRor?",
    ]


def test_worker_trigger_edge_coupling_query_simulator_execution(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command("trigger-edge-coupling", {"query": True}, runtime)

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["coupling"] == "dc"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:EDGE:COUPling?",
        ":SYSTem:ERRor?",
    ]


def test_worker_trigger_edge_reject_simulator_execution(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-edge-reject",
        {"reject": "hf-reject"},
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["result"]["reject"] == "hf-reject"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:EDGE:REJect HFReject",
        ":SYSTem:ERRor?",
    ]


def test_worker_trigger_edge_reject_query_simulator_execution(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command("trigger-edge-reject", {"query": True}, runtime)

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["reject"] == "off"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:EDGE:REJect?",
        ":SYSTem:ERRor?",
    ]
