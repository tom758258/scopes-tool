from __future__ import annotations

import errno
import json
import threading

from scopes_tool_webui import launcher


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, *_args):
        pass


class FakeWidget:
    def __init__(self):
        self.state = "normal"
        self.visible = True

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]

    def grid(self, **_kwargs):
        self.visible = True

    def grid_remove(self):
        self.visible = False

    def columnconfigure(self, *_args, **_kwargs):
        pass

    def rowconfigure(self, *_args, **_kwargs):
        pass


class FakeRoot:
    def __init__(self):
        self.destroyed = False
        self.deiconified = False

    def destroy(self):
        self.destroyed = True

    def update_idletasks(self):
        pass

    def deiconify(self):
        self.deiconified = True

    def lift(self):
        pass

    def after(self, _delay, _callback):
        pass

    def title(self, _value):
        pass

    def protocol(self, _name, _callback):
        pass

    def columnconfigure(self, *_args, **_kwargs):
        pass

    def rowconfigure(self, *_args, **_kwargs):
        pass


class FakeSocket:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeServer:
    def __init__(self):
        self.should_exit = False
        self.served_sockets = []

    async def serve(self, *, sockets):
        self.served_sockets = list(sockets)


class OrderedServer(FakeServer):
    def __init__(self, events):
        super().__init__()
        self.events = events

    @property
    def should_exit(self):
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value):
        self._should_exit = value
        if value:
            self.events.append("server")


class ImmediateThread:
    def __init__(self, *, target, name, daemon, args=()):
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon
        self.alive = False

    def start(self):
        self.alive = True
        self.target(*self.args)
        self.alive = False

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.alive = False


class LiveThread:
    def __init__(self):
        self.alive = True
        self.joined = False

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.joined = True
        self.alive = False


class FakeJobManager:
    def __init__(self, events=None, error=None):
        self.events = events if events is not None else []
        self.error = error

    def shutdown(self, *, timeout_s):
        self.events.append(("jobs", timeout_s))
        if self.error is not None:
            raise self.error


def make_app(
    *,
    initial_port=launcher.DEFAULT_PORT,
    socket_binder=None,
    server_factory=None,
    readiness_checker=None,
    browser_open=None,
    job_manager_instance=None,
):
    app = launcher.LauncherApp.__new__(launcher.LauncherApp)
    app._root = FakeRoot()
    app._server_factory = server_factory or (lambda _port: FakeServer())
    app._socket_binder = socket_binder or (lambda _port: FakeSocket())
    app._browser_open = browser_open or (lambda _url: True)
    app._readiness_checker = readiness_checker or (lambda _url: True)
    app._job_manager = job_manager_instance or FakeJobManager()
    app._server = None
    app._server_socket = None
    app._server_thread = None
    app._server_loop = None
    app._startup_thread = None
    app._shutdown_thread = None
    app._shutdown_in_progress = False
    app._jobs_shutdown_complete = False
    app._ui_queue = launcher.Queue()
    app._startup_success = threading.Event()
    app._server_error = None
    app._manual_port_fallback = False
    app._startup_attempt = 0
    app._startup_result_handled = False
    app._exit_code = 0
    app._use_default_port = FakeVar(initial_port == launcher.DEFAULT_PORT)
    app._port_value = FakeVar(str(initial_port))
    app._url_value = FakeVar(launcher.build_local_url(initial_port))
    app._status_value = FakeVar("Ready")
    app._config_frame = FakeWidget()
    app._default_checkbox = FakeWidget()
    app._port_entry = FakeWidget()
    app._start_button = FakeWidget()
    app._quit_button = FakeWidget()
    return app


def drain_ui(app) -> None:
    app._process_ui_queue()


def test_launcher_constructor_initializes_shutdown_state(monkeypatch):
    for widget_name in ("Frame", "Checkbutton", "Label", "Entry", "Button"):
        monkeypatch.setattr(
            launcher.tk,
            widget_name,
            lambda *_args, **_kwargs: FakeWidget(),
        )
    monkeypatch.setattr(
        launcher.tk,
        "BooleanVar",
        lambda *_args, **kwargs: FakeVar(kwargs.get("value")),
    )
    monkeypatch.setattr(
        launcher.tk,
        "StringVar",
        lambda *_args, **kwargs: FakeVar(kwargs.get("value")),
    )

    job_manager = FakeJobManager()
    app = launcher.LauncherApp(FakeRoot(), job_manager_instance=job_manager)

    assert app._job_manager is job_manager
    assert app._shutdown_thread is None
    assert app._shutdown_in_progress is False
    assert app._jobs_shutdown_complete is False


def test_default_port_and_auto_fallback(monkeypatch):
    assert launcher.DEFAULT_HOST == "127.0.0.1"
    assert launcher.DEFAULT_PORT == 8025
    assert launcher._candidate_ports(8025, auto_port=True) == tuple(range(8025, 8125))

    events = []
    attempted_ports = []
    sockets = {}
    server = FakeServer()

    def socket_binder(port):
        events.append(("bind", port))
        attempted_ports.append(port)
        if port < 8027:
            raise OSError(errno.EADDRINUSE, "in use")
        sockets[port] = FakeSocket()
        return sockets[port]

    def server_factory(port):
        events.append(("factory", port))
        return server

    def readiness_checker(url):
        events.append(("ready", url))
        return url.endswith(":8027/api/health")

    browser_urls = []
    app = make_app(
        socket_binder=socket_binder,
        server_factory=server_factory,
        readiness_checker=readiness_checker,
        browser_open=lambda url: events.append(("browser", url)) or browser_urls.append(url),
    )
    monkeypatch.setattr(launcher.threading, "Thread", ImmediateThread)

    app.start(auto_port=True)
    drain_ui(app)

    assert attempted_ports == [8025, 8026, 8027]
    assert server.served_sockets == [sockets[8027]]
    assert browser_urls == ["http://127.0.0.1:8027"]
    assert events.index(("ready", "http://127.0.0.1:8027/api/health")) < events.index(
        ("browser", "http://127.0.0.1:8027")
    )


def test_readiness_requires_scopes_service_identity(monkeypatch):
    class FakeResponse:
        status = 200

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    monkeypatch.setattr(
        launcher,
        "urlopen",
        lambda _url, timeout: FakeResponse(
            {"status": "ok", "package": "scopes-tool-webui"}
        ),
    )
    assert launcher._server_is_ready("http://127.0.0.1:8025/api/health") is True

    monkeypatch.setattr(
        launcher,
        "urlopen",
        lambda _url, timeout: FakeResponse(
            {"status": "ok", "package": "other-service"}
        ),
    )
    assert launcher._server_is_ready("http://127.0.0.1:8025/api/health") is False


def test_fixed_port_conflict_fails_and_does_not_fallback(monkeypatch):
    errors = []
    attempted_ports = []

    def socket_binder(port):
        attempted_ports.append(port)
        raise OSError(errno.EADDRINUSE, "in use")

    app = make_app(initial_port=9000, socket_binder=socket_binder)
    monkeypatch.setattr(
        launcher.messagebox,
        "showerror",
        lambda title, message: errors.append((title, message)),
    )

    app.start()

    assert attempted_ports == [9000]
    assert app._root.destroyed is True
    assert app.exit_code == 1
    assert errors[0][0] == "Start failed"


def test_startup_failure_closes_owned_socket(monkeypatch):
    server_socket = FakeSocket()
    errors = []

    app = make_app(
        socket_binder=lambda _port: server_socket,
        server_factory=lambda _port: (_ for _ in ()).throw(
            RuntimeError("server creation failed")
        ),
    )
    monkeypatch.setattr(
        launcher.messagebox,
        "showerror",
        lambda _title, message: errors.append(message),
    )

    app.start()

    assert server_socket.closed is True
    assert app._root.destroyed is True
    assert app.exit_code == 1
    assert errors == ["RuntimeError: server creation failed"]


def test_auto_port_exhaustion_exposes_manual_fallback(monkeypatch):
    attempted_ports = []
    errors = []

    def socket_binder(port):
        attempted_ports.append(port)
        raise OSError(errno.EADDRINUSE, "in use")

    app = make_app(socket_binder=socket_binder)
    monkeypatch.setattr(
        launcher.messagebox,
        "showerror",
        lambda title, message: errors.append((title, message)),
    )

    app.start(auto_port=True)

    assert attempted_ports == list(range(8025, 8125))
    assert app._manual_port_fallback is True
    assert app._root.destroyed is False
    assert app._start_button.state == "normal"
    assert errors[0][0] == "No available port"


def test_clean_shutdown_runs_off_the_ui_thread():
    events = []
    job_manager = FakeJobManager(events)
    app = make_app()
    app._job_manager = job_manager
    app._server = OrderedServer(events)
    app._server_thread = LiveThread()
    original_server_thread = app._server_thread

    app._server.should_exit = False

    app.quit()
    app._shutdown_thread.join(timeout=1)
    drain_ui(app)

    assert app._server.should_exit is True
    assert original_server_thread.joined is True
    assert events == [("jobs", launcher.JOB_SHUTDOWN_TIMEOUT_S), "server"]
    assert app._root.destroyed is True


def test_shutdown_failure_keeps_launcher_operable(monkeypatch):
    errors = []
    events = []
    app = make_app(
        job_manager_instance=FakeJobManager(events, TimeoutError("job timeout")),
    )
    app._server = FakeServer()
    app._server_thread = LiveThread()
    monkeypatch.setattr(
        launcher.messagebox,
        "showerror",
        lambda title, message: errors.append((title, message)),
    )

    app.quit()
    app._shutdown_thread.join(timeout=1)
    drain_ui(app)

    assert events == [("jobs", launcher.JOB_SHUTDOWN_TIMEOUT_S)]
    assert app._server.should_exit is False
    assert app._root.destroyed is False
    assert app._shutdown_in_progress is False
    assert app._quit_button.state == "normal"
    assert errors[0][0] == "Shutdown incomplete"


def test_shutdown_timeout_can_be_retried_successfully(monkeypatch):
    errors = []
    events = []
    job_manager = FakeJobManager(events, TimeoutError("job timeout"))
    app = make_app(job_manager_instance=job_manager)
    app._server = OrderedServer(events)
    app._server_thread = LiveThread()
    monkeypatch.setattr(
        launcher.messagebox,
        "showerror",
        lambda title, message: errors.append((title, message)),
    )

    app.quit()
    app._shutdown_thread.join(timeout=1)
    drain_ui(app)

    assert events == [("jobs", launcher.JOB_SHUTDOWN_TIMEOUT_S)]
    assert app._server.should_exit is False
    assert app._root.destroyed is False
    assert app._shutdown_in_progress is False
    assert app._jobs_shutdown_complete is False
    assert app._quit_button.state == "normal"
    assert errors[0][0] == "Shutdown incomplete"

    job_manager.error = None
    app.quit()
    app._shutdown_thread.join(timeout=1)
    drain_ui(app)

    assert events == [
        ("jobs", launcher.JOB_SHUTDOWN_TIMEOUT_S),
        ("jobs", launcher.JOB_SHUTDOWN_TIMEOUT_S),
        "server",
    ]
    assert app._server.should_exit is True
    assert app._root.destroyed is True
