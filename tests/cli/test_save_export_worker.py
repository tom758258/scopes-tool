import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model="keysight-dsox4034a",
        resource=None,
                queue_max=1,
        output_format="jsonl",
    )


@pytest.mark.parametrize(
    "command, arguments",
    [
        ("save-pwd", {"query": True}),
        ("save-pwd", {"path": r"\usb"}),
        ("save-filename", {"query": True}),
        ("save-filename", {"name": "scope_01"}),
        ("save-image-format", {"format": "png"}),
        ("save-image-format", {"format": "bmp24"}),
        ("save-image-palette", {"palette": "color"}),
        ("save-image-ink-saver", {"enabled": False}),
        ("save-image-factors", {"enabled": True}),
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
        ("save-pwd", {}),
        ("save-pwd", {"query": False}),
        ("save-pwd", {"query": True, "path": "USB:/"}),
        ("save-pwd", {"path": 1}),
        ("save-pwd", {"path": "bad;path"}),
        ("save-filename", {"name": "folder/name"}),
        ("save-filename", {"filename": "scope"}),
        ("save-image-format", {"format": "PNG"}),
        ("save-image-format", {"format": "none"}),
        ("save-image-palette", {"palette": "gray"}),
        ("save-image-ink-saver", {"enabled": "false"}),
        ("save-image-ink-saver", {"enabled": 0}),
        ("save-image", {}),
        ("save-image", {"filename": 1}),
        ("save-image", {"filename": "bad\nname"}),
        ("save-image", {"query": True, "filename": "screen.png"}),
        ("save-waveform-format", {"format": "bin"}),
        ("save-waveform-format", {"format": "none"}),
        ("save-waveform-length", {"points": True}),
        ("save-waveform-length", {"points": "100"}),
        ("save-waveform-length", {"points": 99}),
        ("save-waveform-length-max", {}),
        ("save-waveform-length-max", {"query": False}),
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
