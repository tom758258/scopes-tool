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


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("trigger-sweep", {"query": True}),
        ("trigger-sweep", {"mode": "auto"}),
        ("trigger-sweep", {"mode": "normal"}),
        ("trigger-noise-reject", {"query": True}),
        ("trigger-noise-reject", {"enabled": True}),
        ("trigger-noise-reject", {"enabled": False}),
        ("trigger-hf-reject", {"query": True}),
        ("trigger-hf-reject", {"enabled": True}),
        ("trigger-hf-reject", {"enabled": False}),
    ],
)
def test_worker_trigger_common_commands_are_accepted(command, arguments):
    parsed_command, parsed_arguments, job_id = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": command,
            "arguments": arguments,
        }
    )

    assert parsed_command == command
    assert parsed_arguments == arguments
    assert job_id is None


@pytest.mark.parametrize(
    "command, arguments, expected_argv",
    [
        ("trigger-sweep", {"query": True}, ["--query"]),
        ("trigger-sweep", {"mode": "auto"}, ["--mode", "auto"]),
        ("trigger-sweep", {"mode": "normal"}, ["--mode", "normal"]),
        ("trigger-noise-reject", {"query": True}, ["--query"]),
        ("trigger-noise-reject", {"enabled": True}, ["--enabled", "true"]),
        ("trigger-noise-reject", {"enabled": False}, ["--enabled", "false"]),
        ("trigger-hf-reject", {"query": True}, ["--query"]),
        ("trigger-hf-reject", {"enabled": True}, ["--enabled", "true"]),
        ("trigger-hf-reject", {"enabled": False}, ["--enabled", "false"]),
    ],
)
def test_worker_trigger_common_arguments_parse(
    tmp_path, command, arguments, expected_argv
):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command(command, arguments, runtime)

    assert parsed.command == command
    normalized = worker._normalize_trigger_common_worker_arguments(command, arguments)
    assert worker.arguments_to_argv(normalized) == expected_argv


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("trigger-sweep", {"query": False}),
        ("trigger-sweep", {"query": "true"}),
        ("trigger-sweep", {"query": 1}),
        ("trigger-sweep", {"query": True, "mode": "auto"}),
        ("trigger-sweep", {}),
        ("trigger-sweep", {"mode": "single"}),
        ("trigger-sweep", {"sweep": "auto"}),
        ("trigger-sweep", {"sweep_mode": "auto"}),
        ("trigger-sweep", {"trigger_sweep": "auto"}),
        ("trigger-noise-reject", {"query": False}),
        ("trigger-noise-reject", {"query": "true"}),
        ("trigger-noise-reject", {"query": 1}),
        ("trigger-noise-reject", {"query": True, "enabled": True}),
        ("trigger-noise-reject", {}),
        ("trigger-noise-reject", {"enabled": "true"}),
        ("trigger-noise-reject", {"enabled": 1}),
        ("trigger-noise-reject", {"noise_reject": True}),
        ("trigger-noise-reject", {"nreject": True}),
        ("trigger-noise-reject", {"nrej": True}),
        ("trigger-noise-reject", {"state": True}),
        ("trigger-noise-reject", {"on": True}),
        ("trigger-noise-reject", {"enable": True}),
        ("trigger-hf-reject", {"query": False}),
        ("trigger-hf-reject", {"query": "true"}),
        ("trigger-hf-reject", {"query": 1}),
        ("trigger-hf-reject", {"query": True, "enabled": True}),
        ("trigger-hf-reject", {}),
        ("trigger-hf-reject", {"enabled": "true"}),
        ("trigger-hf-reject", {"enabled": 1}),
        ("trigger-hf-reject", {"hf_reject": True}),
        ("trigger-hf-reject", {"hfreject": True}),
        ("trigger-hf-reject", {"high_frequency_reject": True}),
        ("trigger-hf-reject", {"state": True}),
        ("trigger-hf-reject", {"on": True}),
        ("trigger-hf-reject", {"enable": True}),
    ],
)
def test_worker_trigger_common_rejects_invalid_arguments(
    tmp_path, command, arguments
):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, runtime)


@pytest.mark.parametrize(
    "body",
    [
        {"command": "trigger-sweep", "arguments": {"query": False}},
        {"command": "trigger-sweep", "arguments": {"sweep": "auto"}},
        {"command": "trigger-noise-reject", "arguments": {"enabled": "true"}},
        {"command": "trigger-noise-reject", "arguments": {"state": True}},
        {"command": "trigger-hf-reject", "arguments": {"enabled": 1}},
        {"command": "trigger-hf-reject", "arguments": {"hf_reject": True}},
    ],
)
def test_worker_trigger_common_rejects_before_enqueue_or_artifacts(tmp_path, body):
    runtime = _runtime(tmp_path)

    with _worker_server(runtime):
        status, payload = _post_command(runtime, body)

    assert status == 400
    assert payload["status"] == "error"
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


@pytest.mark.parametrize(
    "command, arguments, expected_sent",
    [
        (
            "trigger-sweep",
            {"query": True},
            ["*IDN?", ":TRIGger:SWEep?", ":SYSTem:ERRor?"],
        ),
        (
            "trigger-sweep",
            {"mode": "normal"},
            ["*IDN?", ":TRIGger:SWEep NORMal", ":SYSTem:ERRor?"],
        ),
        (
            "trigger-noise-reject",
            {"query": True},
            ["*IDN?", ":TRIGger:NREJect?", ":SYSTem:ERRor?"],
        ),
        (
            "trigger-noise-reject",
            {"enabled": False},
            ["*IDN?", ":TRIGger:NREJect OFF", ":SYSTem:ERRor?"],
        ),
        (
            "trigger-hf-reject",
            {"query": True},
            ["*IDN?", ":TRIGger:HFReject?", ":SYSTem:ERRor?"],
        ),
        (
            "trigger-hf-reject",
            {"enabled": False},
            ["*IDN?", ":TRIGger:HFReject OFF", ":SYSTem:ERRor?"],
        ),
    ],
)
def test_worker_trigger_common_simulator_execution_sends_expected_scpi(
    tmp_path, command, arguments, expected_sent
):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(command, arguments, runtime)

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == expected_sent
