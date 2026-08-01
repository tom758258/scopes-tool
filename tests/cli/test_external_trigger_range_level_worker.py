from contextlib import contextmanager
import json
import threading
from http.server import ThreadingHTTPServer
from urllib import error as urlerror
from urllib import request as urlrequest

import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path, model="keysight-dsox4034a"):
    return worker.WorkerRuntime(
        host="127.0.0.1", port=0, mode="simulate", model=model, resource=None,
        artifact_root=tmp_path, queue_max=1, output_format="jsonl",
    )


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
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlrequest.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


@pytest.mark.parametrize(
    ("command", "arguments", "argv"),
    [
        ("external-trigger-range", {"query": True}, ["--query"]),
        ("external-trigger-range", {"range_volts": 8.0}, ["--range-volts", "8.0"]),
        ("trigger-edge-external-level", {"query": True}, ["--query"]),
        ("trigger-edge-external-level", {"level_volts": -0.5}, ["--level-volts", "-0.5"]),
    ],
)
def test_worker_external_commands_accept_canonical_json_and_map_argv(tmp_path, command, arguments, argv):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(command, arguments, runtime)

    assert parsed.command == command
    if command == "external-trigger-range":
        normalized = worker._normalize_external_trigger_range_worker_arguments(command, arguments)
    else:
        normalized = worker._normalize_trigger_edge_external_level_worker_arguments(command, arguments)
    assert worker.arguments_to_argv(normalized) == argv


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("external-trigger-range", {}),
        ("external-trigger-range", {"query": False}),
        ("external-trigger-range", {"query": True, "range_volts": 8.0}),
        ("external-trigger-range", {"range_volts": 0}),
        ("external-trigger-range", {"range_volts": -8.0}),
        ("external-trigger-range", {"range_volts": True}),
        ("external-trigger-range", {"range_volts": "8.0"}),
        ("external-trigger-range", {"range_volts": float("nan")}),
        ("external-trigger-range", {"range_volts": float("inf")}),
        ("external-trigger-range", {"range_volts": 10**309}),
        ("external-trigger-range", {"range": 8.0}),
        ("external-trigger-range", {"volts": 8.0}),
        ("external-trigger-range", {"value": 8.0}),
        ("external-trigger-range", {"external_range": 8.0}),
        ("external-trigger-range", {"range_volts": 8.0, "extra": 1}),
        ("external-range", {"query": True}),
        ("trigger-edge-external-level", {}),
        ("trigger-edge-external-level", {"query": False}),
        ("trigger-edge-external-level", {"query": True, "level_volts": 0.5}),
        ("trigger-edge-external-level", {"level_volts": True}),
        ("trigger-edge-external-level", {"level_volts": "0.5"}),
        ("trigger-edge-external-level", {"level_volts": float("nan")}),
        ("trigger-edge-external-level", {"level_volts": float("-inf")}),
        ("trigger-edge-external-level", {"level_volts": 10**309}),
        ("trigger-edge-external-level", {"level_volts": -(10**309)}),
        ("trigger-edge-external-level", {"level": 0.5}),
        ("trigger-edge-external-level", {"volts": 0.5}),
        ("trigger-edge-external-level", {"trigger_level": 0.5}),
        ("trigger-edge-external-level", {"source": "external", "level_volts": 0.5}),
        ("trigger-edge-external-level", {"source_channel": 1, "level_volts": 0.5}),
        ("trigger-edge-external-level", {"level_volts": 0.5, "extra": 1}),
        ("edge-trigger-external-level", {"query": True}),
        ("trigger_external_level", {"query": True}),
    ],
)
def test_worker_external_commands_reject_invalid_forms_before_execution(tmp_path, command, arguments):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, _runtime(tmp_path))


@pytest.mark.parametrize(
    "body",
    [
        {"command": "external-trigger-range", "arguments": {"range": 8.0}},
        {"command": "external-trigger-range", "arguments": {"range_volts": 0}},
        {"command": "external-trigger-range", "arguments": {"range_volts": 10**309}},
        {"command": "trigger-edge-external-level", "arguments": {"level_volts": True}},
        {"command": "trigger-edge-external-level", "arguments": {"level_volts": -(10**309)}},
        {"command": "trigger-edge-external-level", "arguments": {"source": "external", "level_volts": 0.5}},
    ],
)
def test_worker_external_command_validation_happens_before_enqueue_or_artifacts(tmp_path, body):
    runtime = _runtime(tmp_path)
    with _worker_server(runtime):
        status, payload = _post_command(runtime, body)

    assert status == 400
    assert payload["status"] == "error"
    assert payload["command"] == body["command"]
    assert payload["error"] == "validation_error"
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_external_commands_execute_configure_and_query_in_simulator(tmp_path):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command("external-trigger-range", {"range_volts": 1.6}, runtime)
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert {key: payload["result"][key] for key in (
        "operation", "command", "range_volts"
    )} == {
        "operation": "set", "command": ":EXTernal:RANGe 1.6", "range_volts": 1.6,
    }
    assert payload["scpi"]["sent"] == ["*IDN?", ":EXTernal:RANGe 1.6", ":SYSTem:ERRor?"]

    parsed = worker.parse_domain_command("external-trigger-range", {"query": True}, runtime)
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert {key: payload["result"][key] for key in (
        "operation", "command", "range_volts", "raw_range"
    )} == {
        "operation": "query", "command": ":EXTernal:RANGe?", "range_volts": 8.0, "raw_range": "8"
    }
    assert payload["scpi"]["sent"] == ["*IDN?", ":EXTernal:RANGe?", ":SYSTem:ERRor?"]

    parsed = worker.parse_domain_command(
        "trigger-edge-external-level", {"level_volts": -0.5}, runtime
    )
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert {key: payload["result"][key] for key in (
        "operation", "command", "level_volts"
    )} == {
        "operation": "set",
        "command": ":TRIGger:EDGE:LEVel -0.5,EXTernal",
        "level_volts": -0.5,
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:LEVel -0.5,EXTernal", ":SYSTem:ERRor?"
    ]

    parsed = worker.parse_domain_command("trigger-edge-external-level", {"query": True}, runtime)
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert {key: payload["result"][key] for key in (
        "operation", "command", "level_volts", "raw_level"
    )} == {
        "operation": "query",
        "command": ":TRIGger:EDGE:LEVel? EXTernal",
        "level_volts": 0.0,
        "raw_level": "0",
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:LEVel? EXTernal", ":SYSTem:ERRor?"
    ]
