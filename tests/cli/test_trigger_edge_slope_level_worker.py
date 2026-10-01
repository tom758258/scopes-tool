from contextlib import contextmanager
import json
import threading
from http.server import ThreadingHTTPServer
from urllib import error as urlerror
from urllib import request as urlrequest

import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_cli._worker_commands_trigger import (
    _normalize_trigger_edge_level_worker_arguments,
    _normalize_trigger_edge_slope_worker_arguments,
)
from scopes_tool_cli.worker_commands import arguments_to_argv
from scopes_tool_core.errors import OscilloscopeError
from tests.cli._worker_test_support import make_worker_runtime


def _runtime(model="keysight-dsox4024a"):
    return make_worker_runtime(model=model)


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
    ("arguments", "argv"),
    [
        ({"query": True}, ["--query"]),
        ({"slope": "either"}, ["--slope", "either"]),
    ],
)
def test_worker_trigger_edge_slope_accepts_canonical_json_and_maps_argv(tmp_path, arguments, argv):
    runtime = _runtime()
    parsed = worker.parse_domain_command("trigger-edge-slope", arguments, runtime)

    assert parsed.command == "trigger-edge-slope"
    assert arguments_to_argv(
        _normalize_trigger_edge_slope_worker_arguments("trigger-edge-slope", arguments)
    ) == argv


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("trigger-edge-slope", {}),
        ("trigger-edge-slope", {"query": True, "slope": "positive"}),
        ("trigger-edge-slope", {"slope": "POSITIVE"}),
        ("edge-trigger-slope", {"query": True}),
    ],
)
def test_worker_trigger_edge_slope_rejects_invalid_forms(tmp_path, command, arguments):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, _runtime())


@pytest.mark.parametrize(
    ("arguments", "argv"),
    [
        ({"query": True, "source_channel": 1}, ["--query", "--source-channel", "1"]),
        ({"source_channel": 1, "level_volts": 0.5}, ["--source-channel", "1", "--level-volts", "0.5"]),
    ],
)
def test_worker_trigger_edge_level_accepts_canonical_json_and_maps_argv(tmp_path, arguments, argv):
    runtime = _runtime()
    parsed = worker.parse_domain_command("trigger-edge-level", arguments, runtime)

    assert parsed.command == "trigger-edge-level"
    assert arguments_to_argv(
        _normalize_trigger_edge_level_worker_arguments("trigger-edge-level", arguments, runtime)
    ) == argv


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("trigger-edge-level", {}),
        ("trigger-edge-level", {"query": True}),
        ("trigger-edge-level", {"query": True, "source_channel": 1, "level_volts": 0.5}),
        ("trigger-edge-level", {"source_channel": 5, "level_volts": 0.5}),
        ("trigger-edge-level", {"source_channel": 1, "level_volts": True}),
        ("edge-trigger-level", {"query": True, "source_channel": 1}),
    ],
)
def test_worker_trigger_edge_level_rejects_invalid_forms(tmp_path, command, arguments):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, _runtime("keysight-dsox2004a"))


@pytest.mark.parametrize(
    "body",
    [
        {"command": "trigger-edge-slope", "arguments": {"slope": "POSITIVE"}},
        {"command": "trigger-edge-level", "arguments": {"source_channel": 5, "level_volts": 0.5}},
    ],
)
def test_worker_atomic_trigger_validation_happens_before_enqueue_or_artifacts(tmp_path, body):
    runtime = _runtime("keysight-dsox2004a")
    with _worker_server(runtime):
        status, payload = _post_command(runtime, body)

    assert status == 400
    assert payload["status"] == "error"
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_atomic_trigger_simulator_execution_isolated(tmp_path):
    runtime = _runtime("keysight-dsox4034a")
    parsed = worker.parse_domain_command("trigger-edge-slope", {"slope": "either"}, runtime)
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:SLOPe EITHer", ":SYSTem:ERRor?"
    ]

    parsed = worker.parse_domain_command(
        "trigger-edge-level", {"source_channel": 2, "level_volts": -0.25}, runtime
    )
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert payload["result"]["command"] == ":TRIGger:EDGE:LEVel -0.25,CHANnel2"
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:LEVel -0.25,CHANnel2", ":SYSTem:ERRor?"
    ]


def test_worker_trigger_edge_slope_query_executes_in_simulator(tmp_path):
    runtime = _runtime("keysight-dsox4034a")
    parsed = worker.parse_domain_command("trigger-edge-slope", {"query": True}, runtime)

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert {key: payload["result"][key] for key in (
        "operation", "command", "slope", "raw_slope"
    )} == {
        "operation": "query",
        "command": ":TRIGger:EDGE:SLOPe?",
        "slope": "positive",
        "raw_slope": "POS",
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:SLOPe?", ":SYSTem:ERRor?"
    ]


def test_worker_trigger_edge_level_query_executes_in_simulator(tmp_path):
    runtime = _runtime("keysight-dsox4034a")
    parsed = worker.parse_domain_command(
        "trigger-edge-level", {"query": True, "source_channel": 1}, runtime
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert {key: payload["result"][key] for key in (
        "operation", "command", "source_channel", "level_volts", "raw_level"
    )} == {
        "operation": "query",
        "command": ":TRIGger:EDGE:LEVel? CHANnel1",
        "source_channel": 1,
        "level_volts": 0.0,
        "raw_level": "0",
    }
    assert payload["scpi"]["sent"] == [
        "*IDN?", ":TRIGger:EDGE:LEVel? CHANnel1", ":SYSTem:ERRor?"
    ]
