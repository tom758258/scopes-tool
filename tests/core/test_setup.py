import pytest

from scopes_tool_core.setup import (
    SetupController,
    setup_save_command,
)

from scopes_tool_core.errors import ParameterValidationError

from scopes_tool_core.fake_backend import (
    FakeBackend,
    FakeBackendError,
)

from scopes_tool_core.scpi import SCPIClient

def test_setup_file_rejects_quotes_and_wrong_extension():
    with pytest.raises(ParameterValidationError):
        setup_save_command(file_spec='"bad.scp"')
    with pytest.raises(ParameterValidationError):
        setup_save_command(file_spec="bad.txt")

@pytest.mark.parametrize(
    ("method", "arguments", "command"),
    [
        ("save", {"file_spec": "\\usb\\setup.scp"}, ':SAVE:SETup "\\usb\\setup.scp"'),
        ("recall", {"slot": 3}, ":RECall:SETup 3"),
    ],
)
def test_setup_operations_wait_for_completion_with_temporary_timeout(
    monkeypatch, method, arguments, command
):
    backend = FakeBackend(responses={"*OPC?": "1"}, timeout=2000)
    opc_query_timeouts = []
    query = backend.query

    def record_query_timeout(scpi_command):
        opc_query_timeouts.append(backend.timeout)
        return query(scpi_command)

    monkeypatch.setattr(backend, "query", record_query_timeout)
    controller = SetupController(SCPIClient(backend))

    getattr(controller, method)(**arguments)

    assert backend.history == [command, "*OPC?"]
    assert opc_query_timeouts == [15000]
    assert backend.timeout_history == [15000, 2000]
    assert backend.timeout == 2000

@pytest.mark.parametrize(
    ("method", "arguments"),
    [
        ("save", {"slot": 2}),
        ("recall", {"file_spec": "\\usb\\setup.scp"}),
    ],
)
def test_setup_operations_restore_timeout_when_completion_query_raises(
    method, arguments
):
    backend = FakeBackend(responses={}, timeout=2000)
    controller = SetupController(SCPIClient(backend))

    with pytest.raises(FakeBackendError):
        getattr(controller, method)(**arguments)

    assert backend.timeout_history == [15000, 2000]
    assert backend.timeout == 2000
