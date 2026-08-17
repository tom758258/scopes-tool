import sys
from types import SimpleNamespace

import pytest

from scopes_tool_core.errors import VisaBackendError
from scopes_tool_core.visa_backend import (
    ASRL_VERIFY_TIMEOUT_MS,
    BACKEND_CUSTOM_VISA,
    BACKEND_PYVISA_BT,
    BACKEND_PYVISA_PY,
    BACKEND_SYSTEM_VISA,
    VisaBackend,
    is_asrl_resource,
    list_visa_resources,
    normalize_backend,
    normalize_serial_termination,
    verify_asrl_resource_live,
    verify_visa_resource_live,
)


class _FakeResource:
    def __init__(self):
        self.timeout = 2000
        self.closed = False
        self.history = []
        self.binary_kwargs = []

    def write(self, command):
        self.history.append(("write", command))

    def query(self, command):
        self.history.append(("query", command))
        return " response \n"

    def read_raw(self):
        self.history.append(("read_raw",))
        return bytearray(b"raw-bytes")

    def query_binary_values(self, command, **kwargs):
        self.history.append(("query_binary_values", command))
        self.binary_kwargs.append(kwargs)
        return [1, 2, 3]

    def close(self):
        self.closed = True


class _FakeResourceManager:
    def __init__(self, resources=("USB0::FAKE::INSTR",), opened_resource=None):
        self.resources = resources
        self.opened_resource = opened_resource or _FakeResource()
        self.visalib = "fake visa library"
        self.opened_names = []
        self.opened_kwargs = []
        self.closed = False

    def list_resources(self):
        return self.resources

    def open_resource(self, resource_name, **kwargs):
        self.opened_names.append(resource_name)
        self.opened_kwargs.append(kwargs)
        return self.opened_resource

    def close(self):
        self.closed = True


def _install_fake_pyvisa(monkeypatch, factory):
    calls = []

    def resource_manager(*args):
        calls.append(args)
        return factory(*args)

    monkeypatch.setitem(
        sys.modules,
        "pyvisa",
        SimpleNamespace(ResourceManager=resource_manager),
    )
    return calls


@pytest.mark.parametrize(
    ("visa_library", "expected"),
    [
        (None, BACKEND_SYSTEM_VISA),
        ("", BACKEND_SYSTEM_VISA),
        ("   ", BACKEND_SYSTEM_VISA),
        ("@py", BACKEND_PYVISA_PY),
        ("@bt", BACKEND_PYVISA_BT),
        ("@ivi", BACKEND_CUSTOM_VISA),
        ("system_visa", BACKEND_SYSTEM_VISA),
        ("pyvisa_py", BACKEND_PYVISA_PY),
        ("pyvisa_bt", BACKEND_PYVISA_BT),
        ("custom_visa", BACKEND_CUSTOM_VISA),
    ],
)
def test_normalize_backend_returns_canonical_identity(visa_library, expected):
    assert normalize_backend(visa_library) == expected


@pytest.mark.parametrize(
    ("visa_library", "expected_args"),
    [
        (None, ()),
        ("@py", ("@py",)),
        ("@bt", ("@bt",)),
    ],
)
def test_list_visa_resources_preserves_resource_manager_selector(
    monkeypatch, visa_library, expected_args
):
    manager = _FakeResourceManager()
    calls = _install_fake_pyvisa(monkeypatch, lambda *args: manager)

    list_visa_resources(visa_library)

    assert calls == [expected_args]


def test_list_visa_resources_uses_pyvisa_resource_manager_and_closes(monkeypatch):
    manager = _FakeResourceManager(resources=("USB0::FAKE::INSTR", 123))
    calls = _install_fake_pyvisa(monkeypatch, lambda: manager)

    listing = list_visa_resources()

    assert listing.resources == ("USB0::FAKE::INSTR", "123")
    assert listing.backend == "fake visa library"
    assert calls == [()]
    assert manager.closed is True


def test_list_visa_resources_wraps_list_failures_and_closes(monkeypatch):
    class FailingResourceManager(_FakeResourceManager):
        def list_resources(self):
            raise RuntimeError("VISA unavailable")

    manager = FailingResourceManager()
    _install_fake_pyvisa(monkeypatch, lambda visa_library: manager)

    with pytest.raises(VisaBackendError) as excinfo:
        list_visa_resources("@sim")

    assert "Failed to list VISA resources: VISA unavailable" in str(excinfo.value)
    assert manager.closed is True


def test_visa_backend_opens_resource_delegates_io_and_closes(monkeypatch):
    resource = _FakeResource()
    manager = _FakeResourceManager(opened_resource=resource)
    calls = _install_fake_pyvisa(monkeypatch, lambda visa_library: manager)

    backend = VisaBackend("USB0::FAKE::INSTR", visa_library="@sim")

    assert backend.resource_name == "USB0::FAKE::INSTR"
    assert backend.backend == "fake visa library"
    assert backend.timeout == 2000
    assert calls == [("@sim",)]
    assert manager.opened_names == ["USB0::FAKE::INSTR"]

    backend.set_timeout(5000)
    backend.write(":RUN")
    response = backend.query("*IDN?")
    raw = backend.read_raw()
    binary = backend.query_binary_values(":WAVeform:DATA?", datatype="B")
    binary_bytes = backend.query_binary_bytes(":LISTer:DATA?")

    assert resource.timeout == 5000
    assert response == " response \n"
    assert raw == b"raw-bytes"
    assert binary == [1, 2, 3]
    assert binary_bytes == b"raw-bytes"
    assert resource.binary_kwargs == [{"datatype": "B"}]
    assert resource.history == [
        ("write", ":RUN"),
        ("query", "*IDN?"),
        ("read_raw",),
        ("query_binary_values", ":WAVeform:DATA?"),
        ("write", ":LISTer:DATA?"),
        ("read_raw",),
    ]
    assert backend.history == [
        ":RUN", "*IDN?", ":WAVeform:DATA?", ":LISTer:DATA?"
    ]

    backend.close()
    backend.close()

    assert resource.closed is True
    assert manager.closed is True
    with pytest.raises(VisaBackendError) as excinfo:
        backend.query("*IDN?")
    assert "VISA backend is closed" in str(excinfo.value)


def test_visa_backend_wraps_resource_manager_creation_failure(monkeypatch):
    def fail_resource_manager():
        raise RuntimeError("no backend")

    monkeypatch.setitem(
        sys.modules,
        "pyvisa",
        SimpleNamespace(ResourceManager=fail_resource_manager),
    )

    with pytest.raises(VisaBackendError) as excinfo:
        VisaBackend("USB0::FAKE::INSTR")

    assert "Failed to create PyVISA ResourceManager: no backend" in str(excinfo.value)


def test_visa_backend_wraps_open_failure_and_closes_manager(monkeypatch):
    class FailingOpenResourceManager(_FakeResourceManager):
        def open_resource(self, resource_name):
            self.opened_names.append(resource_name)
            raise RuntimeError("device busy")

    manager = FailingOpenResourceManager()
    _install_fake_pyvisa(monkeypatch, lambda: manager)

    with pytest.raises(VisaBackendError) as excinfo:
        VisaBackend("USB0::FAKE::INSTR")

    assert "Failed to open VISA resource USB0::FAKE::INSTR: device busy" in str(
        excinfo.value
    )
    assert manager.opened_names == ["USB0::FAKE::INSTR"]
    assert manager.closed is True


@pytest.mark.parametrize(
    ("operation", "expected_message"),
    [
        (lambda backend: backend.set_timeout(1000), "Failed to set VISA timeout to 1000"),
        (lambda backend: backend.write(":STOP"), "VISA write failed for ':STOP'"),
        (lambda backend: backend.query("*IDN?"), "VISA query failed for '*IDN?'"),
        (lambda backend: backend.read_raw(), "VISA raw read failed"),
        (
            lambda backend: backend.query_binary_values(":WAVeform:DATA?"),
            "VISA binary query failed for ':WAVeform:DATA?'",
        ),
        (
            lambda backend: backend.query_binary_bytes(":LISTer:DATA?"),
            "VISA raw binary query failed for ':LISTer:DATA?'",
        ),
    ],
)
def test_visa_backend_wraps_session_operation_failures(
    monkeypatch, operation, expected_message
):
    class FailingResource(_FakeResource):
        def __init__(self):
            self.closed = False

        @property
        def timeout(self):
            return 2000

        @timeout.setter
        def timeout(self, value):
            raise RuntimeError("timeout failed")

        def write(self, command):
            raise RuntimeError("write failed")

        def query(self, command):
            raise RuntimeError("query failed")

        def read_raw(self):
            raise RuntimeError("read failed")

        def query_binary_values(self, command, **kwargs):
            raise RuntimeError("binary failed")

    manager = _FakeResourceManager(opened_resource=FailingResource())
    _install_fake_pyvisa(monkeypatch, lambda: manager)
    backend = VisaBackend("USB0::FAKE::INSTR")

    with pytest.raises(VisaBackendError) as excinfo:
        operation(backend)

    assert expected_message in str(excinfo.value)


@pytest.mark.parametrize(
    "resource",
    ["ASRL1::INSTR", "asrl2::instr", "  AsRl3::INSTR"],
)
def test_is_asrl_resource_detects_case_insensitively(resource):
    assert is_asrl_resource(resource) is True


@pytest.mark.parametrize(
    "resource",
    ["USB0::FAKE::INSTR", "TCPIP0::192.0.2.1::INSTR", "GPIB0::1::INSTR"],
)
def test_is_asrl_resource_rejects_non_asrl(resource):
    assert is_asrl_resource(resource) is False


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("CRLF", "\r\n"),
        ("LF", "\n"),
        ("CR", "\r"),
        ("NONE", None),
        ("crlf", "\r\n"),
    ],
)
def test_normalize_serial_termination_maps_tokens(token, expected):
    assert normalize_serial_termination(token) == expected


def test_asrl_live_verification_uses_bounded_timeouts_and_serial_settings(monkeypatch):
    resource = _FakeResource()
    manager = _FakeResourceManager(opened_resource=resource)
    calls = _install_fake_pyvisa(monkeypatch, lambda visa_library: manager)

    verification = verify_asrl_resource_live(
        "ASRL1::INSTR",
        visa_library="@sim",
        serial_read_termination="CRLF",
        serial_write_termination="NONE",
    )

    assert verification.live is True
    assert verification.resource == "ASRL1::INSTR"
    assert verification.raw_idn == "response"
    assert verification.detail is None
    assert calls == [("@sim",)]
    assert manager.opened_names == ["ASRL1::INSTR"]
    assert manager.opened_kwargs == [{"open_timeout": ASRL_VERIFY_TIMEOUT_MS}]
    assert resource.timeout == ASRL_VERIFY_TIMEOUT_MS
    assert resource.read_termination == "\r\n"
    assert resource.write_termination is None
    assert resource.history == [("query", "*IDN?")]
    assert resource.closed is True
    assert manager.closed is True


def test_asrl_live_verification_omits_unspecified_serial_settings(monkeypatch):
    resource = _FakeResource()
    manager = _FakeResourceManager(opened_resource=resource)
    _install_fake_pyvisa(monkeypatch, lambda: manager)

    verification = verify_asrl_resource_live("ASRL1::INSTR")

    assert verification.live is True
    assert not hasattr(resource, "read_termination")
    assert not hasattr(resource, "write_termination")


def test_generic_live_verification_uses_bounded_timeout(monkeypatch):
    resource = _FakeResource()
    manager = _FakeResourceManager(opened_resource=resource)
    _install_fake_pyvisa(monkeypatch, lambda: manager)

    verification = verify_visa_resource_live("USB0::INSTR")

    assert verification.live is True
    assert verification.raw_idn == "response"
    assert manager.opened_kwargs == [{"open_timeout": ASRL_VERIFY_TIMEOUT_MS}]
    assert resource.timeout == ASRL_VERIFY_TIMEOUT_MS
    assert resource.history == [("query", "*IDN?")]


def test_asrl_live_verification_returns_stale_detail_and_closes(monkeypatch):
    class FailingResource(_FakeResource):
        def query(self, command):
            self.history.append(("query", command))
            raise RuntimeError("timed out")

    resource = FailingResource()
    manager = _FakeResourceManager(opened_resource=resource)
    _install_fake_pyvisa(monkeypatch, lambda: manager)

    verification = verify_asrl_resource_live("ASRL1::INSTR")

    assert verification.live is False
    assert verification.raw_idn is None
    assert "ASRL verification failed: timed out" in str(verification.detail)
    assert resource.closed is True
    assert manager.closed is True
