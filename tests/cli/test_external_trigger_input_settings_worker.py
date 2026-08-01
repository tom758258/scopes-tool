from contextlib import contextmanager
import json
import threading
from http.server import ThreadingHTTPServer
from urllib import error as urlerror
from urllib import request as urlrequest

import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path):
    return worker.WorkerRuntime(
        host="127.0.0.1", port=0, mode="simulate", model="keysight-dsox4034a", resource=None,
        artifact_root=tmp_path, queue_max=1, output_format="jsonl",
    )


@contextmanager
def _worker_server(runtime):
    server = ThreadingHTTPServer(("127.0.0.1", 0), worker._make_handler(runtime))
    runtime.port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
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
        ("external-trigger-probe", {"query": True}, ["--query"]),
        ("external-trigger-probe", {"attenuation": 10}, ["--attenuation", "10"]),
        ("external-trigger-units", {"query": True}, ["--query"]),
        ("external-trigger-units", {"units": "amps"}, ["--units", "amps"]),
        ("external-trigger-settings", {"query": True}, ["--query"]),
    ],
)
def test_worker_external_trigger_input_commands_accept_canonical_json_and_map_argv(tmp_path, command, arguments, argv):
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))
    assert parsed.command == command
    if command == "external-trigger-probe":
        normalized = worker._normalize_external_trigger_probe_worker_arguments(command, arguments)
    elif command == "external-trigger-units":
        normalized = worker._normalize_external_trigger_units_worker_arguments(command, arguments)
    else:
        normalized = worker._normalize_external_trigger_settings_worker_arguments(command, arguments)
    assert worker.arguments_to_argv(normalized) == argv


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("external-trigger-probe", {}), ("external-trigger-probe", {"query": False}),
        ("external-trigger-probe", {"query": True, "attenuation": 10}),
        ("external-trigger-probe", {"attenuation": True}), ("external-trigger-probe", {"attenuation": "10"}),
        ("external-trigger-probe", {"attenuation": None}), ("external-trigger-probe", {"attenuation": 0}),
        ("external-trigger-probe", {"attenuation": -1}), ("external-trigger-probe", {"attenuation": float("nan")}),
        ("external-trigger-probe", {"attenuation": float("inf")}), pytest.param("external-trigger-probe", {"attenuation": 10**10000}, id="probe-huge-integer"),
        ("external-trigger-probe", {"probe": 10}), ("external-trigger-probe", {"ratio": 10}),
        ("external-trigger-probe", {"attenuation": 10, "extra": 1}),
        ("external-trigger-units", {}), ("external-trigger-units", {"query": False}),
        ("external-trigger-units", {"query": True, "units": "volts"}), ("external-trigger-units", {"units": "volt"}),
        ("external-trigger-units", {"units": "AMP"}), ("external-trigger-units", {"units": True}),
        ("external-trigger-units", {"units": None}), ("external-trigger-units", {"unit": "volts"}),
        ("external-trigger-settings", {}), ("external-trigger-settings", {"query": False}),
        ("external-trigger-settings", {"query": 1}), ("external-trigger-settings", {"query": "true"}),
        ("external-trigger-settings", {"units": "volts"}), ("external-trigger-settings", {"extra": 1}),
        ("external-trigger-probe-alias", {"query": True}),
    ],
)
def test_worker_external_trigger_input_commands_reject_invalid_forms_before_execution(tmp_path, command, arguments):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, _runtime(tmp_path))


@pytest.mark.parametrize(
    "body",
    [
        {"command": "external-trigger-probe", "arguments": {"attenuation": 0}},
        {"command": "external-trigger-probe", "arguments": {"attenuation": 10**309}},
        {"command": "external-trigger-units", "arguments": {"units": "AMP"}},
        {"command": "external-trigger-settings", "arguments": {}},
    ],
)
def test_worker_external_trigger_input_validation_happens_before_enqueue_or_artifacts(tmp_path, body):
    runtime = _runtime(tmp_path)
    with _worker_server(runtime):
        status, payload = _post_command(runtime, body)
    assert status == 400
    assert payload["status"] == "error"
    assert payload["error"] == "validation_error"
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


@pytest.mark.parametrize(
    ("command", "arguments", "result", "sent"),
    [
        ("external-trigger-probe", {"attenuation": 10}, {"operation": "set", "command": ":EXTernal:PROBe 10", "attenuation": 10.0}, ["*IDN?", ":EXTernal:PROBe 10", ":SYSTem:ERRor?"]),
        ("external-trigger-probe", {"query": True}, {"operation": "query", "command": ":EXTernal:PROBe?", "attenuation": 1.0, "raw_attenuation": "1"}, ["*IDN?", ":EXTernal:PROBe?", ":SYSTem:ERRor?"]),
        ("external-trigger-units", {"units": "volts"}, {"operation": "set", "command": ":EXTernal:UNITs VOLT", "units": "volts"}, ["*IDN?", ":EXTernal:UNITs VOLT", ":SYSTem:ERRor?"]),
        ("external-trigger-units", {"query": True}, {"operation": "query", "command": ":EXTernal:UNITs?", "units": "volts", "raw_units": "VOLT"}, ["*IDN?", ":EXTernal:UNITs?", ":SYSTem:ERRor?"]),
        ("external-trigger-settings", {"query": True}, {"operation": "query", "command": ":EXTernal?", "probe_attenuation": 1.0, "range_value": 8.0, "units": "volts", "bandwidth_limit_enabled": False}, ["*IDN?", ":EXTernal?", ":SYSTem:ERRor?"]),
    ],
)
def test_worker_external_trigger_input_commands_execute_in_simulator(tmp_path, command, arguments, result, sent):
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert {key: payload["result"][key] for key in result} == result
    assert payload["scpi"]["sent"] == sent
