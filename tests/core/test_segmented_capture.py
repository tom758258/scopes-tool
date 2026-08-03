import json

import pytest

import scopes_tool_core.segmented_capture as segmented_capture_module
from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.segmented_capture import (
    SegmentedCaptureRequest,
    plan_segmented_capture,
    run_segmented_capture,
)
from scopes_tool_core.segmented import segmented_waveform_all_command
from scopes_tool_core.simulator_backend import SimulatorBackend


def _scope(**kwargs):
    return Oscilloscope(
        SimulatorBackend(
            physical_model_id="keysight-dsox4024a",
            resource_name="SIM::keysight-dsox4024a::INSTR",
            **kwargs,
        )
    )


class _AcquiredCountSequenceBackend(SimulatorBackend):
    def __init__(self, acquired_counts):
        super().__init__(physical_model_id="keysight-dsox4024a")
        self.acquired_counts = list(acquired_counts)
        self.last_acquired_count = 0

    def query(self, command):
        if command == ":WAVeform:SEGMented:COUNt?":
            self._ensure_open()
            self.history.append(command)
            if self.acquired_counts:
                self.last_acquired_count = self.acquired_counts.pop(0)
            return str(self.last_acquired_count)
        return super().query(command)


def test_run_segmented_capture_exports_segments_in_order_and_writes_manifest(tmp_path):
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox4024a",
        resource_name="SIM::keysight-dsox4024a::INSTR",
    )
    with Oscilloscope(backend) as scope:
        scope.scpi.write(segmented_waveform_all_command(True))
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, poll_interval_ms=1, output_dir=tmp_path),
        )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert result.result["initial_mode"] == "realtime"
    assert result.result["final_mode"] == "segmented"
    assert result.result["exported_segments"] == 2
    assert (tmp_path / "segment_0001.csv").exists()
    assert (tmp_path / "segment_0002.csv").exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert [entry["index"] for entry in manifest["segments"]] == [1, 2]
    assert [entry["time_tag_s"] for entry in manifest["segments"]] == [0.0, 0.001]
    assert backend.segmented_waveform_all is False
    assert backend.history.count(segmented_waveform_all_command(False)) == 1
    all_off_index = backend.history.index(segmented_waveform_all_command(False))
    first_index = backend.history.index(":ACQuire:SEGMented:INDex 1")
    assert all_off_index < first_index
    assert backend.history == [
        segmented_waveform_all_command(True),
        "*IDN?",
        ":ACQuire:MODE?",
        ":ACQuire:TYPE?",
        ":ACQuire:MODE SEGMented",
        ":ACQuire:SEGMented:COUNt 2",
        ":SINGle",
        ":WAVeform:SEGMented:COUNt?",
        ":WAVeform:SEGMented:ALL OFF",
        ":ACQuire:SEGMented:INDex 1",
        ":WAVeform:SEGMented:TTAG?",
        ":WAVeform:SOURce CHANnel1",
        ":WAVeform:FORMat BYTE",
        ":WAVeform:POINts 1000",
        ":WAVeform:PREamble?",
        ":WAVeform:DATA?",
        ":ACQuire:SEGMented:INDex 2",
        ":WAVeform:SEGMented:TTAG?",
        ":WAVeform:SOURce CHANnel1",
        ":WAVeform:FORMat BYTE",
        ":WAVeform:POINts 1000",
        ":WAVeform:PREamble?",
        ":WAVeform:DATA?",
        ":ACQuire:MODE?",
        ":SYSTem:ERRor?",
    ]


def test_run_segmented_capture_rejects_average_before_segmented_write(tmp_path):
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox4024a", acquisition_type="AVERage"
    )
    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "failed"
    assert ":ACQuire:MODE SEGMented" not in backend.history
    assert ":SINGle" not in backend.history
    assert backend.history == ["*IDN?", ":ACQuire:MODE?", ":ACQuire:TYPE?"]


def test_run_segmented_capture_zero_acquired_timeout_writes_no_csv(tmp_path):
    backend = _AcquiredCountSequenceBackend([0, 0])
    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(
                1, 2, timeout_ms=1, poll_interval_ms=1, output_dir=tmp_path
            ),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "failed"
    assert result.result["exported_segments"] == 0
    assert not list(tmp_path.glob("segment_*.csv"))
    assert segmented_waveform_all_command(False) not in backend.history
    assert not any(
        command.startswith(":ACQuire:SEGMented:INDex")
        or command in {
            ":WAVeform:SEGMented:TTAG?",
            ":WAVeform:SOURce CHANnel1",
            ":WAVeform:FORMat BYTE",
            ":WAVeform:POINts 1000",
            ":WAVeform:PREamble?",
            ":WAVeform:DATA?",
        }
        for command in backend.history
    )


def test_run_segmented_capture_partial_timeout_keeps_completed_csv(tmp_path):
    backend = _AcquiredCountSequenceBackend([1, 1])
    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(
                1, 2, timeout_ms=1, poll_interval_ms=1, output_dir=tmp_path
            ),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "partial"
    assert result.result["acquired_segments"] == 1
    assert result.result["exported_segments"] == 1
    assert (tmp_path / "segment_0001.csv").exists()
    assert not (tmp_path / "segment_0002.csv").exists()
    assert backend.history.count(segmented_waveform_all_command(False)) == 1
    assert backend.history.index(segmented_waveform_all_command(False)) < backend.history.index(
        ":ACQuire:SEGMented:INDex 1"
    )


@pytest.mark.parametrize(
    ("model", "contains_all_off"),
    [("DSOX2004A", False), ("DSOX3024A", False), ("DSOX4024A", True)],
)
def test_segmented_capture_plan_respects_waveform_all_profile_boundary(
    model, contains_all_off, tmp_path
):
    planned, _, _ = plan_segmented_capture(
        SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        capabilities_for_model(model),
    )

    all_off = segmented_waveform_all_command(False)
    assert (all_off in planned) is contains_all_off
    assert planned.count(all_off) == (1 if contains_all_off else 0)


def test_run_segmented_capture_keeps_csv_file_when_manifest_update_fails(
    monkeypatch, tmp_path
):
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox4024a",
        resource_name="SIM::keysight-dsox4024a::INSTR",
    )
    state = {"failed": False}
    original_write_manifest = segmented_capture_module._write_manifest

    def fail_after_first_csv(manifest, path):
        if (
            manifest["status"] == "running"
            and manifest["exported_segments"] == 1
            and not state["failed"]
        ):
            state["failed"] = True
            raise OSError("simulated manifest failure")
        original_write_manifest(manifest, path)

    monkeypatch.setattr(
        segmented_capture_module, "_write_manifest", fail_after_first_csv
    )
    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        )

    csv_path = tmp_path / "segment_0001.csv"
    assert result.exit_code == 1
    assert result.result["status"] == "partial"
    assert result.result["exported_segments"] == 1
    assert "simulated manifest failure" in result.result["error"]
    assert csv_path.exists()
    assert {"kind": "csv", "path": str(csv_path)} in result.files


def test_run_segmented_capture_malformed_count_returns_failed_manifest(tmp_path):
    backend = _AcquiredCountSequenceBackend(["not-a-count"])
    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "failed"
    assert isinstance(result.result["error"], str)
    assert not list(tmp_path.glob("segment_*.csv"))


def test_run_segmented_capture_rejects_nonempty_output_before_scpi(tmp_path):
    (tmp_path / "existing.txt").write_text("existing", encoding="utf-8")
    backend = SimulatorBackend()
    scope = Oscilloscope(backend)

    with pytest.raises(OscilloscopeError, match="must be empty"):
        run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        )

    assert backend.history == []


@pytest.mark.parametrize("segments", [True, 2.0, "2", 1])
def test_run_segmented_capture_rejects_invalid_static_request(tmp_path, segments):
    with pytest.raises(ParameterValidationError):
        run_segmented_capture(
            _scope(),
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, segments, output_dir=tmp_path),
        )
