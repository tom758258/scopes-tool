from contextlib import contextmanager
import json
from http.server import ThreadingHTTPServer
import threading
from urllib import error as urlerror
from urllib import request as urlrequest

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


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"query": True}, ["--query"]),
        ({"source_channel": 1}, ["--source-channel", "1"]),
        ({"source": "external"}, ["--source", "external"]),
        ({"source": "line"}, ["--source", "line"]),
    ],
)
def test_worker_trigger_edge_source_accepts_canonical_json_and_maps_argv(tmp_path, arguments, expected):
    runtime = _runtime(tmp_path)
    command, accepted, job_id = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "trigger-edge-source",
            "arguments": arguments,
        }
    )
    parsed = worker.parse_domain_command(command, accepted, runtime)

    assert job_id is None
    assert parsed.command == "trigger-edge-source"
    assert worker.arguments_to_argv(
        worker._normalize_trigger_edge_source_worker_arguments(command, accepted, runtime)
    ) == expected


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("trigger-edge-source", {}),
        ("trigger-edge-source", {"query": False}),
        ("trigger-edge-source", {"query": True, "source": "external"}),
        ("trigger-edge-source", {"source": "external", "source_channel": 1}),
        ("trigger-edge-source", {"channel": 1}),
        ("trigger-edge-source", {"sourceChannel": 1}),
        ("trigger-edge-source", {"input_source": "external"}),
        ("trigger-edge-source", {"source": 1}),
        ("trigger-edge-source", {"source": "EXTERNAL"}),
        ("trigger-edge-source", {"source": "Line"}),
        ("trigger-edge-source", {"source": "analog-channel"}),
        ("trigger-edge-source", {"source": "wgen1"}),
        ("trigger-edge-source", {"source_channel": True}),
        ("trigger-edge-source", {"source_channel": 1.0}),
        ("trigger-edge-source", {"source_channel": 0}),
        ("trigger-edge-source", {"source_channel": 5}),
        ("edge-trigger-source", {"query": True}),
        ("trigger-source", {"query": True}),
        ("edge-source", {"query": True}),
        ("trigger-edge-input", {"query": True}),
        ("trigger_edge_source", {"query": True}),
    ],
)
def test_worker_trigger_edge_source_rejects_invalid_forms(tmp_path, command, arguments):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, _runtime(tmp_path, "keysight-dsox2004a"))


@pytest.mark.parametrize(
    "body",
    [
        {"command": "trigger-edge-source", "arguments": {}},
        {"command": "trigger-edge-source", "arguments": {"query": False}},
        {"command": "trigger-edge-source", "arguments": {"query": True, "source": "external"}},
        {"command": "trigger-edge-source", "arguments": {"source": "external", "source_channel": 1}},
        {"command": "trigger-edge-source", "arguments": {"source_channel": True}},
        {"command": "trigger-edge-source", "arguments": {"source_channel": 5}},
        {"command": "trigger-edge-source", "arguments": {"source": "LINE"}},
        {"command": "edge-trigger-source", "arguments": {"query": True}},
    ],
)
def test_worker_trigger_edge_source_rejects_before_enqueue_or_artifacts(tmp_path, body):
    runtime = _runtime(tmp_path, "keysight-dsox2004a")

    with _worker_server(runtime):
        status, payload = _post_command(runtime, body)

    assert status == 400
    assert payload["status"] == "error"
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


@pytest.mark.parametrize(
    ("arguments", "command", "source", "source_channel"),
    [
        ({"source_channel": 4}, ":TRIGger:EDGE:SOURce CHANnel4", "analog-channel", 4),
        ({"source": "external"}, ":TRIGger:EDGE:SOURce EXTernal", "external", None),
        ({"source": "line"}, ":TRIGger:EDGE:SOURce LINE", "line", None),
    ],
)
def test_worker_trigger_edge_source_simulator_configure_execution(tmp_path, arguments, command, source, source_channel):
    runtime = _runtime(tmp_path, "keysight-dsox4034a")
    parsed = worker.parse_domain_command("trigger-edge-source", arguments, runtime)

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert {key: payload["result"][key] for key in (
        "operation", "command", "source", "source_channel"
    )} == {
        "operation": "set",
        "command": command,
        "source": source,
        "source_channel": source_channel,
    }
    assert payload["scpi"]["sent"] == ["*IDN?", command, ":SYSTem:ERRor?"]


def test_worker_trigger_edge_source_simulator_query_execution(tmp_path):
    runtime = _runtime(tmp_path, "keysight-dsox4034a")
    parsed = worker.parse_domain_command("trigger-edge-source", {"query": True}, runtime)

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert {key: payload["result"][key] for key in (
        "operation", "command", "source", "source_channel", "raw_source"
    )} == {
        "operation": "query",
        "command": ":TRIGger:EDGE:SOURce?",
        "source": "analog-channel",
        "source_channel": 1,
        "raw_source": "CHANnel1",
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:SOURce?", ":SYSTem:ERRor?"
    ]
