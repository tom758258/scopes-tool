from contextlib import contextmanager
import json
from http.server import ThreadingHTTPServer
import threading
from urllib import error as urlerror
from urllib import request as urlrequest

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


def test_worker_trigger_edge_command_is_accepted():
    command, arguments, job_id = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "trigger-edge",
            "arguments": {"query": True},
        }
    )

    assert command == "trigger-edge"
    assert arguments == {"query": True}
    assert job_id is None


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"query": True}, ["trigger-edge", "--query"]),
        (
            {"source_channel": 1, "level": 0.5, "slope": "positive"},
            [
                "trigger-edge",
                "--source-channel",
                "1",
                "--level",
                "0.5",
                "--slope",
                "positive",
            ],
        ),
        (
            {"source_channel": 1, "level": 0.5, "slope": "negative"},
            [
                "trigger-edge",
                "--source-channel",
                "1",
                "--level",
                "0.5",
                "--slope",
                "negative",
            ],
        ),
    ],
)
def test_worker_trigger_edge_arguments_parse(tmp_path, arguments, expected):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command("trigger-edge", arguments, runtime)

    assert parsed.command == "trigger-edge"
    assert worker.arguments_to_argv(
        worker._normalize_trigger_edge_worker_arguments("trigger-edge", arguments)
    ) == expected[1:]


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("edge-trigger", {"query": True}),
        ("trigger-edge", {"query": False}),
        ("trigger-edge", {"query": "true"}),
        ("trigger-edge", {"query": 1}),
        ("trigger-edge", {"query": True, "source_channel": 1}),
        ("trigger-edge", {"query": True, "level": 0.5}),
        ("trigger-edge", {"query": True, "slope": "positive"}),
        ("trigger-edge", {"source_channel": 1, "level": 0.5}),
        ("trigger-edge", {"source_channel": 1, "slope": "positive"}),
        ("trigger-edge", {"level": 0.5, "slope": "positive"}),
        ("trigger-edge", {"channel": 1, "level": 0.5, "slope": "positive"}),
        ("trigger-edge", {"source": 1, "level": 0.5, "slope": "positive"}),
        (
            "trigger-edge",
            {"source_channel": 1, "level_volts": 0.5, "slope": "positive"},
        ),
        (
            "trigger-edge",
            {"source_channel": 1, "level": 0.5, "edge_slope": "positive"},
        ),
        (
            "trigger-edge",
            {"source_channel": 1, "level": 0.5, "slope": "positive", "mode": "edge"},
        ),
        (
            "trigger-edge",
            {"source_ch": 1, "level": 0.5, "slope": "positive"},
        ),
        (
            "trigger-edge",
            {"trigger_source": 1, "level": 0.5, "slope": "positive"},
        ),
        (
            "trigger-edge",
            {"source_channel": 1, "trigger_level": 0.5, "slope": "positive"},
        ),
    ],
)
def test_worker_trigger_edge_rejects_invalid_arguments(tmp_path, command, arguments):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, runtime)


@pytest.mark.parametrize(
    "body",
    [
        {"command": "edge-trigger", "arguments": {"query": True}},
        {"command": "trigger-edge", "arguments": {"query": False}},
        {
            "command": "trigger-edge",
            "arguments": {"query": True, "source_channel": 1},
        },
        {
            "command": "trigger-edge",
            "arguments": {"channel": 1, "level": 0.5, "slope": "positive"},
        },
        {
            "command": "trigger-edge",
            "arguments": {"source": 1, "level": 0.5, "slope": "positive"},
        },
        {
            "command": "trigger-edge",
            "arguments": {"source_channel": 1, "level_volts": 0.5, "slope": "positive"},
        },
        {
            "command": "trigger-edge",
            "arguments": {"source_channel": 1, "level": 0.5, "edge_slope": "positive"},
        },
        {
            "command": "trigger-edge",
            "arguments": {
                "source_channel": 1,
                "level": 0.5,
                "slope": "positive",
                "mode": "edge",
            },
        },
    ],
)
def test_worker_trigger_edge_rejects_before_enqueue_or_artifacts(tmp_path, body):
    runtime = _runtime(tmp_path)

    with _worker_server(runtime):
        status, payload = _post_command(runtime, body)

    assert status == 400
    assert payload["status"] == "error"
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_trigger_edge_simulator_execution_sends_expected_scpi(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-edge",
        {"source_channel": 1, "level": 0.5, "slope": "positive"},
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["files"] == []
    assert payload["result"]["source_channel"] == 1
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE EDGE",
        ":TRIGger:EDGE:SOURce CHANnel1",
        ":TRIGger:EDGE:LEVel 0.5",
        ":TRIGger:EDGE:SLOPe POSitive",
        ":SYSTem:ERRor?",
    ]


def test_worker_trigger_edge_query_simulator_execution(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command("trigger-edge", {"query": True}, runtime)

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["source_channel"] == 1
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:EDGE:SOURce?",
        ":TRIGger:EDGE:LEVel?",
        ":TRIGger:EDGE:SLOPe?",
        ":SYSTem:ERRor?",
    ]
