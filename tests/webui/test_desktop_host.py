"""Focused no-hardware coverage for the private Desktop Host lifecycle."""

from __future__ import annotations

import asyncio
import json
import os
from io import StringIO
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from scopes_tool_webui import _desktop_host as desktop_host


class RecordingStream(StringIO):
    def __init__(self, events):
        super().__init__()
        self.events = events

    def flush(self):
        self.events.append("flush")


class FakeSocket:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def getsockname(self):
        return ("127.0.0.1", 43123)

    def close(self):
        self.events.append("socket.close")
        self.closed = True


class FakeServer:
    def __init__(self, events):
        self.events = events
        self._should_exit = False

    @property
    def should_exit(self):
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value):
        self._should_exit = value
        if value:
            self.events.append("server.exit")


@pytest.fixture
def rig(monkeypatch):
    events = []
    output = RecordingStream(events)
    server_socket = FakeSocket(events)
    server = FakeServer(events)
    loop = SimpleNamespace(is_running=lambda: True)

    class FakeManager:
        error = None

        async def shutdown(self, *, timeout_s):
            assert timeout_s == desktop_host.JOB_SHUTDOWN_TIMEOUT_S
            assert not server.should_exit
            events.append("jobs.shutdown")
            if self.error:
                raise self.error
            events.append("jobs.cleaned")

    manager = FakeManager()

    def check_ready(url):
        assert url == "http://127.0.0.1:43123/api/health"
        events.append("health.ready")
        return True

    host = desktop_host.DesktopHost(
        socket_binder=lambda: server_socket,
        server_factory=lambda port: server if port == 43123 else None,
        readiness_checker=check_ready,
        job_manager_instance=manager,
        input_stream=StringIO('{"command":"shutdown"}\n'),
        output_stream=output,
        startup_timeout_s=0.01,
        readiness_poll_interval_s=0.001,
        server_join_timeout_s=0.01,
    )

    class FakeThread:
        alive = False
        stuck = False
        stopped_at_start = False
        start_error = None
        loop_ready = True

        def __init__(self, *, target, name, daemon):
            self.target = target
            assert daemon is True

        def start(self):
            events.append("thread.start")
            if self.start_error:
                raise self.start_error
            self.alive = not self.stopped_at_start
            host._server_loop = loop
            if self.loop_ready:
                host._server_loop_ready.set()

        def is_alive(self):
            return self.alive

        def join(self, *, timeout):
            assert timeout == 0.01
            events.append("thread.join")
            self.alive = self.stuck

    class FakeFuture:
        wait_error = None

        def __init__(self, coroutine):
            self.coroutine = coroutine

        def result(self, *, timeout):
            assert timeout == (
                desktop_host.JOB_SHUTDOWN_TIMEOUT_S + desktop_host.SHUTDOWN_WAIT_GRACE_S
            )
            if self.wait_error:
                raise self.wait_error
            asyncio.run(self.coroutine)

        def cancel(self):
            events.append("future.cancel")
            self.coroutine.close()

    def submit(coroutine, submitted_loop):
        assert submitted_loop is loop
        return FakeFuture(coroutine)

    monkeypatch.setattr(desktop_host.threading, "Thread", FakeThread)
    monkeypatch.setattr(desktop_host.asyncio, "run_coroutine_threadsafe", submit)
    return SimpleNamespace(
        host=host, events=events, output=output, socket=server_socket, server=server,
        manager=manager, thread_type=FakeThread, future_type=FakeFuture, loop=loop,
    )


def events_from(output):
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_ready_and_shutdown_preserve_cleanup_order_and_flush(rig):
    rig.host._input_stream = StringIO(
        'invalid\n[]\n{"command":1}\n{"command":"unknown"}\n'
        '{"command":"shutdown"}\n'
    )
    assert rig.host.run() == 0
    assert rig.host.port == 43123
    assert events_from(rig.output) == [
        {"event": "ready", "url": "http://127.0.0.1:43123"}
    ]
    assert rig.output.getvalue().endswith("\n")
    assert rig.events == [
        "thread.start", "health.ready", "flush", "jobs.shutdown", "jobs.cleaned",
        "server.exit", "thread.join", "socket.close",
    ]
    assert not rig.host.server_thread.is_alive()
    assert rig.socket.closed


@pytest.mark.parametrize("failure", ["cleanup", "job_timeout", "wait_timeout"])
def test_shutdown_incomplete_keeps_server_thread_and_socket(rig, failure):
    rig.host.start()
    if failure == "wait_timeout":
        rig.future_type.wait_error = TimeoutError("shutdown wait timed out")
    else:
        rig.manager.error = (
            RuntimeError("cleanup failed") if failure == "cleanup"
            else TimeoutError("jobs still cleaning up")
        )
    assert rig.host.shutdown() is False
    assert events_from(rig.output)[-1]["event"] == "shutdown_incomplete"
    assert rig.events[-1] == "flush"
    assert not rig.server.should_exit
    assert rig.host.server_thread.is_alive()
    assert not rig.socket.closed
    assert not rig.host._shutdown_in_progress
    assert "thread.join" not in rig.events


def test_incomplete_shutdown_accepts_later_formal_shutdown(rig):
    rig.manager.error = TimeoutError("jobs still cleaning up")

    class RetryInput:
        def __iter__(self):
            yield '{"command":"shutdown"}\n'
            assert not rig.server.should_exit
            assert not rig.socket.closed
            rig.manager.error = None
            yield '{"command":"shutdown"}\n'

    rig.host._input_stream = RetryInput()
    assert rig.host.run() == 0
    assert [event["event"] for event in events_from(rig.output)] == [
        "ready", "shutdown_incomplete"
    ]
    assert rig.socket.closed


def test_server_join_timeout_does_not_close_socket(rig):
    rig.host.start()
    rig.thread_type.stuck = True
    assert rig.host.shutdown() is False
    assert events_from(rig.output)[-1]["event"] == "shutdown_incomplete"
    assert rig.server.should_exit
    assert not rig.socket.closed
    assert rig.host.server_thread.is_alive()


def test_stdin_eof_matches_powers_without_extra_shutdown(rig):
    rig.host._input_stream = StringIO('invalid\n{"command":"unknown"}\n')
    assert rig.host.run() == 0
    assert rig.events == ["thread.start", "health.ready", "flush"]
    assert not rig.server.should_exit
    assert not rig.socket.closed


@pytest.mark.parametrize("failure", [
    "bind", "factory", "thread_start", "loop_start", "stopped", "server_error",
    "health_timeout", "stopped_during_health",
])
def test_startup_failure_emits_error_without_ready_and_releases_resources(rig, failure):
    def fail():
        raise RuntimeError("startup failed")

    if failure == "bind":
        rig.host._socket_binder = fail
    elif failure == "factory":
        rig.host._server_factory = lambda _port: fail()
    elif failure == "thread_start":
        rig.thread_type.start_error = RuntimeError("thread failed")
    elif failure == "loop_start":
        rig.thread_type.loop_ready = False
    elif failure in {"stopped", "server_error"}:
        rig.thread_type.stopped_at_start = True
        if failure == "server_error":
            def start():
                rig.host._server_loop_ready.set()
                rig.host._server_error = RuntimeError("server failed")
            rig.thread_type.start = lambda self: start()
    elif failure == "health_timeout":
        rig.host._readiness_checker = lambda _url: False
    else:
        def stopped_health(_url):
            rig.host.server_thread.alive = False
            return True
        rig.host._readiness_checker = stopped_health

    assert rig.host.run() == 1
    events = events_from(rig.output)
    assert len(events) == 1 and events[0]["event"] == "error"
    assert events[0]["message"]
    assert rig.events.count("flush") == 1
    assert rig.socket.closed is (failure != "bind")
    assert rig.host.server_thread is None or not rig.host.server_thread.is_alive()


@pytest.mark.parametrize("payload,status,expected", [
    ({"status": "ok", "package": "scopes-tool-webui"}, 200, True),
    ({"status": "ok", "package": "other-service"}, 200, False),
    ({"status": "error", "package": "scopes-tool-webui"}, 200, False),
    ({"status": "ok", "package": "scopes-tool-webui"}, 503, False),
    ({}, 200, False), ([], 200, False), (None, 200, False),
    ("invalid JSON", 200, False),
])
def test_health_readiness_requires_status_and_package(monkeypatch, payload, status, expected):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self):
            return b"invalid JSON" if payload == "invalid JSON" else json.dumps(payload).encode()

    response = Response()
    response.status = status

    def open_health(url, *, timeout):
        assert url == "http://127.0.0.1:43123/api/health"
        assert timeout == 0.5
        return response

    monkeypatch.setattr(desktop_host, "urlopen", open_health)
    assert desktop_host._server_is_ready("http://127.0.0.1:43123/api/health") is expected


def test_health_connection_failure_is_not_ready(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise URLError("connection refused")
    monkeypatch.setattr(desktop_host, "urlopen", unavailable)
    assert not desktop_host._server_is_ready("http://127.0.0.1:43123/api/health")


def test_socket_binds_only_loopback_with_os_selected_port(monkeypatch):
    calls = []
    sentinel = object()
    monkeypatch.setattr(
        desktop_host.socket, "create_server",
        lambda address: calls.append(address) or sentinel,
    )
    assert desktop_host.bind_local_socket() is sentinel
    assert calls == [("127.0.0.1", 0)]


def test_server_factory_uses_existing_app_and_keeps_logs_off_stdout():
    from scopes_tool_webui.app import app

    server = desktop_host.create_uvicorn_server(43123)
    assert server.config.app is app
    assert server.config.host == "127.0.0.1"
    assert server.config.port == 43123
    assert server.config.log_config is None
    assert server.config.access_log is False


def test_serve_uses_owned_socket_and_records_server_event_loop():
    host = desktop_host.DesktopHost()
    server_socket = object()

    class Server:
        async def serve(self, *, sockets):
            assert sockets == [server_socket]
            assert host._server_loop is asyncio.get_running_loop()
            assert host._server_loop_ready.is_set()

    host._server = Server()
    asyncio.run(host._serve_server(server_socket))


def test_module_http_smoke_ready_then_formal_shutdown():
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    process = subprocess.Popen(
        [sys.executable, "-m", "scopes_tool_webui._desktop_host"],
        cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    try:
        # communicate is bounded and keeps the formal shutdown input open until read.
        stdout, stderr = process.communicate('{"command":"shutdown"}\n', timeout=15)
        assert process.returncode == 0, stderr
        events = [json.loads(line) for line in stdout.splitlines()]
        assert len(events) == 1 and events[0]["event"] == "ready"
        url = events[0]["url"]
        assert url.startswith("http://127.0.0.1:")
        assert 0 < int(url.rsplit(":", 1)[1]) <= 65535
        with pytest.raises(URLError):
            urlopen(f"{url}/api/health", timeout=0.5)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=3)
