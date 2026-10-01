import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError
from tests.cli._worker_test_support import make_worker_runtime


def _runtime(tmp_path):
    return make_worker_runtime(model="keysight-dsox4034a")


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("save-pwd", {"path": r"\usb"}),
        ("save-filename", {"name": "scope_01"}),
        ("save-image-format", {"format": "png"}),
        ("save-image-ink-saver", {"enabled": False}),
        ("save-image", {"filename": r"\usb\screen.png"}),
        ("save-waveform-format", {"format": "ascii-xy"}),
        ("save-waveform-length", {"points": 100}),
        ("save-waveform-length-max", {"query": True}),
        ("save-waveform", {"filename": r"\usb\wave.csv"}),
    ],
)
def test_worker_accepts_canonical_save_export_payloads(tmp_path, command, arguments):
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))
    assert parsed.command == command


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("save-pwd", {"path": 1}),
        ("save-filename", {"filename": "scope"}),
        ("save-image-format", {"format": "PNG"}),
        ("save-image-ink-saver", {"enabled": "false"}),
        ("save-image", {}),
        ("save-waveform-format", {"format": "bin"}),
        ("save-waveform-length", {"points": True}),
        ("save-waveform-length-max", {}),
        ("save-waveform", {"filename": "bad;name"}),
    ],
)
def test_worker_rejects_noncanonical_save_payloads_before_side_effects(
    tmp_path, command, arguments
):
    runtime = _runtime(tmp_path)
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, runtime)
    assert runtime.accepted == 0
    assert runtime.queue.empty()
    assert runtime.jobs == {}
    assert not (tmp_path / runtime.run_id).exists()


def test_worker_save_waveform_simulator_execution_has_no_command_artifacts(tmp_path):
    parsed = worker.parse_domain_command(
        "save-waveform", {"filename": r"\usb\wave.csv"}, _runtime(tmp_path)
    )
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert payload["result"]["operation"] == "save-waveform"
    assert payload["result"]["instrument_side"] is True
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        r':SAVE:WAVeform "\usb\wave.csv"',
        "*OPC?",
        ":OPERegister:CONDition?",
        ":SYSTem:ERRor?",
    ]


def test_worker_tek_waveform_source_forwarded(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.model = "tektronix-tbs1052b"
    parsed = worker.parse_domain_command("save-waveform", {"filename": "wave.csv", "source_channel": 2}, runtime)
    payload, code = cli._execute_json_command(parsed)
    assert code == 0
    assert payload["result"]["command"] == 'SAVe:WAVEform CH2,"wave.csv"'
    for source in (None, 3):
        arguments = {"filename": "wave.csv"}
        if source is not None:
            arguments["source_channel"] = source
        with pytest.raises(OscilloscopeError):
            worker.parse_domain_command("save-waveform", arguments, runtime)
