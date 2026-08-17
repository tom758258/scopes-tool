import json

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_cli.commands import workflows
from scopes_tool_core import operations
from scopes_tool_core import output_files
from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.idn import parse_idn
from scopes_tool_core.status import SystemErrorEntry
from tests.cli.support import (
    byte_waveform_capture,
    install_scope,
    word_waveform_capture,
)
from scopes_tool_core.waveform import (
    MultiChannelWaveformCapture,
)


class _BatchDummyBackend:
    backend = "fake"
    timeout = 2000


class _BatchDummyScope:
    backend = _BatchDummyBackend()

    def __init__(self, *, model="DSOX4024A", system_errors=None):
        self.capabilities = None
        self.calls = []
        self.model = model
        self.system_errors = list(system_errors or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback

    def query_idn(self):
        self.calls.append("query_idn")
        self.capabilities = capabilities_for_model(self.model)
        return parse_idn(f"KEYSIGHT TECHNOLOGIES,{self.model},MY123,07.20")

    def capture_waveform_byte(self, channel, points=1000):
        self.calls.append(("capture_waveform_byte", channel, points))
        return byte_waveform_capture(channel, points=points)

    def capture_waveform_word(self, channel, points=1000):
        self.calls.append(("capture_waveform_word", channel, points))
        return word_waveform_capture(channel, points=points)

    def capture_waveforms_byte(self, channels, points=1000):
        self.calls.append(("capture_waveforms_byte", channels, points))
        return MultiChannelWaveformCapture(
            tuple(byte_waveform_capture(channel, points=points) for channel in channels)
        )

    def capture_waveforms_word(self, channels, points=1000):
        self.calls.append(("capture_waveforms_word", channels, points))
        return MultiChannelWaveformCapture(
            tuple(word_waveform_capture(channel, points=points) for channel in channels)
        )

    def query_system_error(self):
        self.calls.append("query_system_error")
        if self.system_errors:
            return self.system_errors.pop(0)
        return SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')


def test_capture_batch_cli_runs_two_captures_and_writes_outputs(
    monkeypatch, capsys, tmp_path
):
    scope = install_scope(monkeypatch, _BatchDummyScope())
    output_dir = tmp_path / "batch"

    assert (
        cli.main(
            [
                "capture-batch",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--channel",
                "2",
                "--points",
                "1000",
                "--count",
                "2",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("capture_waveforms_byte", (1, 2), 1000),
        "query_system_error",
        ("capture_waveforms_byte", (1, 2), 1000),
        "query_system_error",
    ]
    assert (output_dir / "waveform_0001.csv").exists()
    assert (output_dir / "waveform_0001_meta.json").exists()
    assert (output_dir / "waveform_0002.csv").exists()
    assert (output_dir / "waveform_0002_meta.json").exists()
    assert (output_dir / "scpi.log").exists()
    assert (output_dir / "waveform_0001.csv").read_text(encoding="utf-8").splitlines()[0] == (
        "time_s,ch1_v,ch2_v"
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["resource"] == "USB0::FAKE::INSTR"
    assert manifest["backend"] == "fake"
    assert manifest["timeout_ms"] == 2000
    assert manifest["channels"] == [1, 2]
    assert manifest["requested_count"] == 2
    assert manifest["captures"][0]["csv"] == "waveform_0001.csv"
    assert manifest["captures"][0]["metadata"] == "waveform_0001_meta.json"
    assert manifest["captures"][0]["actual_points"] == {"CH1": 2, "CH2": 2}
    out = capsys.readouterr().out
    assert "Planned batch capture: CH1, CH2, 1000 points, BYTE format, 2 captures" in out
    assert f"Manifest: {output_dir / 'manifest.json'}" in out


def test_capture_batch_cli_maps_arguments_to_core_request(monkeypatch, tmp_path):
    scope = install_scope(monkeypatch, _BatchDummyScope())
    observed = {}

    def fake_run_capture_batch(
        actual_scope,
        resource,
        request,
        *,
        stop_requested=None,
    ):
        observed.update(
            scope=actual_scope,
            resource=resource,
            request=request,
            stop_requested=stop_requested,
        )
        return operations.OperationResult(
            0,
            {
                "status": "completed",
                "completed_count": 0,
            },
        )

    monkeypatch.setattr(workflows, "run_capture_batch", fake_run_capture_batch)
    assert (
        cli.main(
            [
                "capture-batch",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "2",
                "--points",
                "5000",
                "--format",
                "word",
                "--count",
                "3",
                "--interval-seconds",
                "1.5",
                "--output-dir",
                str(tmp_path / "batch"),
            ]
        )
        == 0
    )

    request = observed["request"]
    assert observed["scope"] is scope
    assert observed["resource"] == "USB0::FAKE::INSTR"
    assert observed["stop_requested"] is None
    assert request == operations.CaptureBatchRequest(
        channels=[2],
        points=5000,
        waveform_format="word",
        requested_count=3,
        interval_seconds=1.5,
        output_dir=str(tmp_path / "batch"),
        log_scpi=False,
    )


def test_capture_batch_cli_channel_all_expands_to_detected_model_channels(
    monkeypatch, capsys, tmp_path
):
    scope = install_scope(monkeypatch, _BatchDummyScope(model="DSOX4024A"))

    assert (
        cli.main(
            [
                "capture-batch",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "all",
                "--count",
                "1",
                "--output-dir",
                str(tmp_path / "batch"),
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("capture_waveforms_byte", (1, 2, 3, 4), 1000),
        "query_system_error",
    ]
    assert "Planned batch capture: CH1, CH2, CH3, CH4" in capsys.readouterr().out


def test_capture_batch_cli_word_single_channel_uses_single_word_api_each_time(
    monkeypatch, tmp_path
):
    scope = install_scope(monkeypatch, _BatchDummyScope())

    assert (
        cli.main(
            [
                "capture-batch",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--format",
                "word",
                "--count",
                "2",
                "--output-dir",
                str(tmp_path / "batch"),
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("capture_waveform_word", 1, 1000),
        "query_system_error",
        ("capture_waveform_word", 1, 1000),
        "query_system_error",
    ]


def test_capture_batch_cli_word_multi_channel_uses_plural_word_api(
    monkeypatch, tmp_path
):
    scope = install_scope(monkeypatch, _BatchDummyScope())

    assert (
        cli.main(
            [
                "capture-batch",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "2",
                "--channel",
                "1",
                "--format",
                "word",
                "--count",
                "1",
                "--output-dir",
                str(tmp_path / "batch"),
            ]
        )
        == 0
    )

    assert scope.calls == [
        "query_idn",
        ("capture_waveforms_word", (2, 1), 1000),
        "query_system_error",
    ]


def test_capture_batch_cli_uses_interruptible_wait_between_captures(monkeypatch, tmp_path):
    install_scope(monkeypatch, _BatchDummyScope())
    waits = []
    monkeypatch.setattr(
        operations,
        "interruptible_wait",
        lambda seconds, *, stop_requested=None: waits.append(seconds) or True,
    )

    assert (
        cli.main(
            [
                "capture-batch",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--count",
                "3",
                "--interval-seconds",
                "1.25",
                "--output-dir",
                str(tmp_path / "batch"),
            ]
        )
        == 0
    )

    assert waits == [1.25, 1.25]


def test_capture_batch_cli_stops_after_instrument_error(monkeypatch, tmp_path):
    errors = [
        SystemErrorEntry(code=0, message="No error", raw='+0,"No error"'),
        SystemErrorEntry(code=-113, message="Undefined header", raw='-113,"Undefined header"'),
    ]
    scope = install_scope(monkeypatch, _BatchDummyScope(system_errors=errors))
    output_dir = tmp_path / "batch"

    assert (
        cli.main(
            [
                "capture-batch",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--count",
                "3",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )

    assert scope.calls == [
        "query_idn",
        ("capture_waveform_byte", 1, 1000),
        "query_system_error",
        ("capture_waveform_byte", 1, 1000),
        "query_system_error",
    ]
    assert not (output_dir / "waveform_0003.csv").exists()
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "instrument_error"
    assert len(manifest["captures"]) == 2
    assert manifest["captures"][1]["system_error"]["code"] == -113


def test_capture_batch_cli_reports_output_write_error_without_traceback(
    monkeypatch, capsys, tmp_path
):
    scope = install_scope(monkeypatch, _BatchDummyScope())
    output_dir = tmp_path / "batch"

    def fail_write_waveform_csv(capture, path):
        del capture
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(output_files, "write_waveform_csv", fail_write_waveform_csv)

    assert (
        cli.main(
            [
                "capture-batch",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--count",
                "1",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn", ("capture_waveform_byte", 1, 1000)]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "error"
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "could not write waveform CSV file" in captured.err
    assert "Permission denied" in captured.err


@pytest.mark.parametrize(
    "argv",
    [
        ["--count", "0"],
        ["--count", "1", "--interval-seconds", "-0.1"],
        ["--count", "1", "--interval-seconds", "nan"],
        ["--count", "1", "--interval-seconds", "inf"],
    ],
)
def test_capture_batch_cli_rejects_invalid_count_and_interval_before_open(
    monkeypatch, tmp_path, argv
):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("scope should not be opened")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    with pytest.raises(SystemExit) as excinfo:
        cli.main(
            [
                "capture-batch",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--output-dir",
                str(tmp_path / "batch"),
                *argv,
            ]
        )

    assert excinfo.value.code == 2


def test_capture_batch_cli_rejects_invalid_channel_before_capture(
    monkeypatch, capsys, tmp_path
):
    scope = install_scope(monkeypatch, _BatchDummyScope(model="DSOX4024A"))

    assert (
        cli.main(
            [
                "capture-batch",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "5",
                "--count",
                "1",
                "--output-dir",
                str(tmp_path / "batch"),
            ]
        )
        == 1
    )

    assert scope.calls == ["query_idn"]
    assert "channel 5 is not available" in capsys.readouterr().err


def test_capture_batch_cli_writes_interrupted_manifest(monkeypatch, capsys, tmp_path):
    class InterruptingScope(_BatchDummyScope):
        def capture_waveform_byte(self, channel, points=1000):
            self.calls.append(("capture_waveform_byte", channel, points))
            raise KeyboardInterrupt

    scope = install_scope(monkeypatch, InterruptingScope())
    output_dir = tmp_path / "batch"

    assert (
        cli.main(
            [
                "capture-batch",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--count",
                "2",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 130
    )

    assert scope.calls == ["query_idn", ("capture_waveform_byte", 1, 1000)]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "interrupted"
    assert manifest["captures"] == []
    assert "error: interrupted" in capsys.readouterr().err
