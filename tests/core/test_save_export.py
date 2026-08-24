import pytest

from scopes_tool_core import save_export
from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.errors import ParameterValidationError, SaveExportResponseError
from scopes_tool_core.fake_backend import FakeBackend, FakeBackendError
from scopes_tool_core.save_export import (
    SaveExportController,
    parse_save_image_format,
    parse_save_waveform_format,
    save_filename_command,
    save_image_command,
    save_image_factors_command,
    save_image_format_command,
    save_image_ink_saver_command,
    save_image_palette_command,
    save_pwd_command,
    save_waveform_command,
    save_waveform_format_command,
    save_waveform_length_command,
    save_waveform_length_max_query,
    validate_save_filename_base,
    validate_save_quoted_string,
)
from scopes_tool_core.scpi import SCPIClient


def test_save_export_v1_scpi_builders_use_common_commands():
    assert save_pwd_command(r"\usb") == ':SAVE:PWD "\\usb"'
    assert save_filename_command("capture_01") == ':SAVE:FILename "capture_01"'
    assert save_image_format_command("png") == ":SAVE:IMAGe:FORMat PNG"
    assert save_image_format_command("bmp") == ":SAVE:IMAGe:FORMat BMP"
    assert save_image_format_command("bmp8") == ":SAVE:IMAGe:FORMat BMP8bit"
    assert save_image_format_command("bmp24") == ":SAVE:IMAGe:FORMat BMP24bit"
    assert save_image_palette_command("color") == ":SAVE:IMAGe:PALette COLor"
    assert save_image_palette_command("grayscale") == ":SAVE:IMAGe:PALette GRAYscale"
    assert save_image_ink_saver_command(True) == ":SAVE:IMAGe:INKSaver 1"
    assert save_image_factors_command(False) == ":SAVE:IMAGe:FACTors 0"
    assert save_waveform_format_command("ascii-xy") == ":SAVE:WAVeform:FORMat ASCiixy"
    assert save_waveform_format_command("csv") == ":SAVE:WAVeform:FORMat CSV"
    assert save_waveform_format_command("binary") == ":SAVE:WAVeform:FORMat BINary"
    assert save_waveform_length_command(100) == ":SAVE:WAVeform:LENGth 100"
    assert save_waveform_length_max_query() == ":SAVE:WAVeform:LENGth:MAX?"


def test_save_format_builders_reject_none_readback_sentinel():
    with pytest.raises(ParameterValidationError):
        save_image_format_command("none")
    with pytest.raises(ParameterValidationError):
        save_waveform_format_command("none")


def test_save_format_parsers_accept_none_readback_sentinel():
    assert parse_save_image_format("NONE") == "none"
    assert parse_save_waveform_format("NONE") == "none"


@pytest.mark.parametrize(
    "value",
    ["", "   ", 'bad"name', "bad;name", "bad\nname", "bad\rname", "bad\x00name", "café"],
)
def test_quoted_save_strings_reject_unsafe_values(value):
    with pytest.raises(ParameterValidationError):
        validate_save_quoted_string(value, label="Save value")


def test_path_like_start_values_are_allowed_but_base_name_rejects_separators():
    file_spec = r"\usb\folder\screen.png"
    assert save_image_command(file_spec) == f':SAVE:IMAGe "{file_spec}"'
    assert save_waveform_command(r"\usb\wave.csv") == r':SAVE:WAVeform "\usb\wave.csv"'
    for value in ("folder/name", r"folder\name", "USB:name"):
        with pytest.raises(ParameterValidationError):
            validate_save_filename_base(value)


def test_query_states_are_canonical_and_preserve_raw_readbacks():
    backend = FakeBackend(
        responses={
            ":SAVE:PWD?": '"\\usb"',
            ":SAVE:FILename?": '"scope_01"',
            ":SAVE:IMAGe:FORMat?": "BMP8bit",
            ":SAVE:IMAGe:PALette?": "GRAYscale",
            ":SAVE:IMAGe:INKSaver?": "ON",
            ":SAVE:IMAGe:FACTors?": "0",
            ":SAVE:WAVeform:FORMat?": "BINary",
            ":SAVE:WAVeform:LENGth?": "+1000",
            ":SAVE:WAVeform:LENGth:MAX?": "1",
        }
    )
    controller = SaveExportController(SCPIClient(backend))
    assert controller.query_pwd().to_json() == {
        "path": r"\usb",
        "raw_response": '"\\usb"',
    }
    assert controller.query_filename().name == "scope_01"
    assert controller.query_image_format().format == "bmp8"
    assert controller.query_image_palette().palette == "grayscale"
    assert controller.query_image_ink_saver().enabled is True
    assert controller.query_image_factors().enabled is False
    assert controller.query_waveform_format().format == "binary"
    assert controller.query_waveform_length().to_json() == {
        "points": 1000,
        "raw_response": "+1000",
    }
    assert controller.query_waveform_length_max().enabled is True


@pytest.mark.parametrize(
    "operation, command",
    [
        ("save-image", r':SAVE:IMAGe "\usb\screen.png"'),
        ("save-waveform", r':SAVE:WAVeform "\usb\wave.csv"'),
    ],
)
def test_start_operations_wait_for_opc(operation, command):
    backend = FakeBackend(responses={"*OPC?": "1"})
    controller = SaveExportController(SCPIClient(backend))
    filename = command.split('"', 1)[1][:-1]
    result = (
        controller.save_image(filename)
        if operation == "save-image"
        else controller.save_waveform(filename)
    )
    assert result.to_json()["instrument_side"] is True
    assert result.to_json()["operation"] == operation
    assert result.to_json()["command"] == command
    assert backend.history == [command, "*OPC?"]


def test_save_image_temporarily_uses_bounded_opc_timeout_and_restores_original(
    monkeypatch,
):
    backend = FakeBackend(responses={"*OPC?": "1"}, timeout=2000)
    opc_query_timeouts = []
    query = backend.query

    def record_query_timeout(command):
        opc_query_timeouts.append(backend.timeout)
        return query(command)

    monkeypatch.setattr(backend, "query", record_query_timeout)
    result = SaveExportController(SCPIClient(backend)).save_image(r"\usb\screen.png")

    assert result.raw_operation_complete == "1"
    assert opc_query_timeouts == [15000]
    assert backend.timeout_history == [15000, 2000]
    assert backend.timeout == 2000


def test_save_image_restores_original_timeout_when_opc_query_raises():
    backend = FakeBackend(responses={}, timeout=2000)

    with pytest.raises(FakeBackendError):
        SaveExportController(SCPIClient(backend)).save_image(r"\usb\screen.png")

    assert backend.timeout_history == [15000, 2000]
    assert backend.timeout == 2000


def test_4000x_configure_image_format_waits_for_context_transition(monkeypatch):
    backend = FakeBackend(responses={"*OPC?": "1"}, timeout=2000)
    opc_query_timeouts = []
    query = backend.query

    def record_query_timeout(command):
        opc_query_timeouts.append(backend.timeout)
        return query(command)

    monkeypatch.setattr(backend, "query", record_query_timeout)
    SaveExportController(
        SCPIClient(backend), capabilities_for_model_id("keysight-dsox4034a")
    ).configure_image_format("png")

    assert backend.history == [":SAVE:IMAGe:FORMat PNG", "*OPC?"]
    assert opc_query_timeouts == [5000]
    assert backend.timeout_history == [5000, 2000]
    assert backend.timeout == 2000


def test_4000x_configure_image_format_restores_timeout_when_opc_query_raises():
    backend = FakeBackend(responses={}, timeout=2000)

    with pytest.raises(FakeBackendError):
        SaveExportController(
            SCPIClient(backend), capabilities_for_model_id("keysight-dsox4034a")
        ).configure_image_format("png")

    assert backend.history == [":SAVE:IMAGe:FORMat PNG", "*OPC?"]
    assert backend.timeout_history == [5000, 2000]
    assert backend.timeout == 2000


def test_non_4000x_configure_image_format_does_not_add_opc_barrier():
    backend = FakeBackend(timeout=2000)
    SaveExportController(
        SCPIClient(backend), capabilities_for_model_id("keysight-dsox3024a")
    ).configure_image_format("png")

    assert backend.history == [":SAVE:IMAGe:FORMat PNG"]
    assert backend.timeout_history == []
    assert backend.timeout == 2000


def test_save_waveform_temporarily_uses_bounded_opc_timeout_and_restores_original(
    monkeypatch,
):
    backend = FakeBackend(responses={"*OPC?": "1"}, timeout=2000)
    opc_query_timeouts = []
    query = backend.query

    def record_query_timeout(command):
        opc_query_timeouts.append(backend.timeout)
        return query(command)

    monkeypatch.setattr(backend, "query", record_query_timeout)
    result = SaveExportController(
        SCPIClient(backend), capabilities_for_model_id("keysight-dsox3024a")
    ).save_waveform(r"\usb\wave.csv")

    assert result.raw_operation_complete == "1"
    assert opc_query_timeouts == [15000]
    assert backend.timeout_history == [15000, 2000]
    assert backend.timeout == 2000
    assert backend.history == [r':SAVE:WAVeform "\usb\wave.csv"', "*OPC?"]


def test_4000x_save_waveform_waits_for_remote_interface_readiness(monkeypatch):
    backend = FakeBackend(timeout=2000)
    condition_responses = iter(("4136", "4136", "4152"))
    query_timeouts = []

    def query(command):
        backend.history.append(command)
        query_timeouts.append((command, backend.timeout))
        if command == "*OPC?":
            return "1"
        return next(condition_responses)

    monkeypatch.setattr(backend, "query", query)
    monkeypatch.setattr(save_export.time, "sleep", lambda unused: None)

    result = SaveExportController(
        SCPIClient(backend), capabilities_for_model_id("keysight-dsox4034a")
    ).save_waveform(r"\usb\wave.csv")

    assert result.raw_operation_complete == "1"
    assert backend.history == [
        r':SAVE:WAVeform "\usb\wave.csv"',
        "*OPC?",
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
    ]
    assert query_timeouts[0] == ("*OPC?", 15000)
    assert all(1 <= timeout <= 15000 for _, timeout in query_timeouts[1:])
    assert backend.timeout == 2000
    assert backend.timeout_history[-1] == 2000


def test_4000x_save_waveform_times_out_waiting_for_remote_interface(monkeypatch):
    backend = FakeBackend(
        responses={"*OPC?": "1", ":OPERegister:CONDition?": "4136"},
        timeout=2000,
    )
    monotonic_values = iter((0.0, 0.0, 15.0))
    monkeypatch.setattr(save_export.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(save_export.time, "sleep", lambda unused: None)

    with pytest.raises(
        SaveExportResponseError,
        match="4000X waveform save timed out waiting for remote-interface readiness",
    ):
        SaveExportController(
            SCPIClient(backend), capabilities_for_model_id("keysight-dsox4034a")
        ).save_waveform(r"\usb\wave.csv")

    assert backend.history == [
        r':SAVE:WAVeform "\usb\wave.csv"',
        "*OPC?",
        ":OPERegister:CONDition?",
    ]
    assert backend.timeout_history == [15000, 2000, 15000, 2000]
    assert backend.timeout == 2000


def test_save_waveform_restores_original_timeout_when_opc_query_raises():
    backend = FakeBackend(responses={}, timeout=2000)

    with pytest.raises(FakeBackendError):
        SaveExportController(SCPIClient(backend)).save_waveform(r"\usb\wave.csv")

    assert backend.timeout_history == [15000, 2000]
    assert backend.timeout == 2000
    assert backend.history == [r':SAVE:WAVeform "\usb\wave.csv"', "*OPC?"]


@pytest.mark.parametrize("points", [True, 99, 1.5, "100"])
def test_waveform_length_rejects_non_integer_or_too_small_values(points):
    with pytest.raises(ParameterValidationError):
        save_waveform_length_command(points)
