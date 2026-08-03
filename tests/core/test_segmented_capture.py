import json

import pytest

import scopes_tool_core.segmented_capture as segmented_capture_module
from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError, VisaBackendError
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
    def __init__(
        self,
        acquired_counts,
        *,
        firmware="07.20",
        operation_conditions=(8, 0),
    ):
        super().__init__(physical_model_id="keysight-dsox4024a", firmware=firmware)
        self.acquired_counts = list(acquired_counts)
        self.last_acquired_count = 0
        self.operation_conditions = list(operation_conditions)
        self.last_operation_condition = 0

    def query(self, command):
        if command == ":WAVeform:SEGMented:COUNt?":
            self._ensure_open()
            self.history.append(command)
            if self.acquired_counts:
                self.last_acquired_count = self.acquired_counts.pop(0)
            return str(self.last_acquired_count)
        if command == ":OPERegister:CONDition?":
            self._ensure_open()
            self.history.append(command)
            if self.operation_conditions:
                self.last_operation_condition = self.operation_conditions.pop(0)
            return str(self.last_operation_condition)
        return super().query(command)


class _TimeoutTrackingBackend(_AcquiredCountSequenceBackend):
    def __init__(
        self,
        acquired_counts,
        *,
        firmware="07.20",
        operation_conditions=(8, 0),
    ):
        super().__init__(
            acquired_counts,
            firmware=firmware,
            operation_conditions=operation_conditions,
        )
        self.events = []

    def set_timeout(self, timeout_ms):
        self.events.append(("set_timeout", timeout_ms))
        super().set_timeout(timeout_ms)

    def write(self, command):
        self.events.append(("write", command))
        super().write(command)

    def query(self, command):
        self.events.append(("query", command))
        return super().query(command)

    def query_binary_values(self, command, **kwargs):
        self.events.append(("query_binary_values", command))
        return super().query_binary_values(command, **kwargs)


class _VisaTimeoutCause(Exception):
    error_code = -1073807339


class _PollingVisaTimeoutBackend(_TimeoutTrackingBackend):
    def __init__(self):
        super().__init__([1])
        self.count_queries = 0

    def query(self, command):
        if command == ":WAVeform:SEGMented:COUNt?":
            self.count_queries += 1
            if self.count_queries == 2:
                self._ensure_open()
                self.events.append(("query", command))
                self.history.append(command)
                raise VisaBackendError(
                    f"VISA query failed for {command!r}: VI_ERROR_TMO"
                ) from _VisaTimeoutCause()
        return super().query(command)


class _ExportVisaTimeoutBackend(_TimeoutTrackingBackend):
    def __init__(self, failure_command, *, fail_segment=1):
        super().__init__([2], operation_conditions=[0])
        self.failure_command = failure_command
        self.fail_segment = fail_segment

    def _should_fail(self, command):
        return (
            command == self.failure_command
            and self.segmented_selected_segment == self.fail_segment
        )

    def query(self, command):
        if self._should_fail(command):
            self._ensure_open()
            self.events.append(("query", command))
            self.history.append(command)
            raise VisaBackendError(
                f"VISA query failed for {command!r}: VI_ERROR_TMO"
            ) from _VisaTimeoutCause()
        return super().query(command)

    def query_binary_values(self, command, **kwargs):
        if self._should_fail(command):
            self._ensure_open()
            self.events.append(("query_binary_values", command))
            self.history.append(command)
            raise VisaBackendError(
                f"VISA binary query failed for {command!r}: VI_ERROR_TMO"
            ) from _VisaTimeoutCause()
        return super().query_binary_values(command, **kwargs)


class _FinalModeVisaTimeoutBackend(_TimeoutTrackingBackend):
    def __init__(self):
        super().__init__([2], operation_conditions=[0])
        self.mode_queries = 0

    def query(self, command):
        if command == ":ACQuire:MODE?":
            self.mode_queries += 1
            if self.mode_queries == 2:
                self._ensure_open()
                self.events.append(("query", command))
                self.history.append(command)
                raise VisaBackendError(
                    f"VISA query failed for {command!r}: VI_ERROR_TMO"
                ) from _VisaTimeoutCause()
        return super().query(command)


def test_run_segmented_capture_exports_segments_in_order_and_writes_manifest(tmp_path):
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox4024a",
        resource_name="SIM::keysight-dsox4024a::INSTR",
        firmware="07.30",
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
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
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


def test_run_segmented_capture_restores_timeout_before_waveform_export(monkeypatch, tmp_path):
    backend = _TimeoutTrackingBackend([0, 2])
    clock = iter([100.0, 100.1, 100.5, 100.6, 100.7])
    monkeypatch.setattr(segmented_capture_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(segmented_capture_module.time, "sleep", lambda _: None)

    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, poll_interval_ms=1, output_dir=tmp_path),
        )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    timeout_events = [value for kind, value in backend.events if kind == "set_timeout"]
    assert timeout_events[0] > 2000
    assert timeout_events[1] < timeout_events[0]
    assert timeout_events[-1] == 2000
    restore_index = backend.events.index(("set_timeout", 2000))
    first_index = backend.events.index(("write", ":ACQuire:SEGMented:INDex 1"))
    assert restore_index < first_index
    assert backend.timeout == 2000


def test_run_segmented_capture_polling_visa_timeout_stops_scpi(tmp_path):
    backend = _PollingVisaTimeoutBackend()
    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, poll_interval_ms=1, output_dir=tmp_path),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "failed"
    assert result.result["acquired_segments"] == 1
    assert result.result["exported_segments"] == 0
    assert "acquired-count read timed out" in result.result["error"]
    assert "30000 ms" in result.result["error"]
    assert "1 of 2" in result.result["error"]
    assert backend.timeout == 2000
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["final_mode"] is None
    assert manifest["system_error"] is None
    assert (tmp_path / "scpi.log").exists()
    assert not list(tmp_path.glob("segment_*.csv"))
    timeout_query_index = max(
        index
        for index, command in enumerate(backend.history)
        if command == ":WAVeform:SEGMented:COUNt?"
    )
    assert backend.history[timeout_query_index + 1 :] == []


def test_run_segmented_capture_waits_for_ready_after_count_reaches_target(
    monkeypatch, tmp_path
):
    backend = _TimeoutTrackingBackend(
        [0, 2], operation_conditions=[8, 8, 0]
    )
    clock = iter([0.0, 0.001, 0.002, 0.003, 0.004, 0.005])
    monkeypatch.setattr(segmented_capture_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(segmented_capture_module.time, "sleep", lambda _: None)

    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, poll_interval_ms=1, output_dir=tmp_path),
        )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert result.result["exported_segments"] == 2
    assert backend.history.count(":SINGle") == 1
    last_count = max(
        index
        for index, command in enumerate(backend.history)
        if command == ":WAVeform:SEGMented:COUNt?"
    )
    first_index = backend.history.index(":ACQuire:SEGMented:INDex 1")
    condition_indexes = [
        index
        for index, command in enumerate(backend.history)
        if command == ":OPERegister:CONDition?"
    ]
    assert condition_indexes
    assert last_count < condition_indexes[0] < first_index
    assert (tmp_path / "segment_0001.csv").exists()
    assert (tmp_path / "segment_0002.csv").exists()

    timeout_events = [value for kind, value in backend.events if kind == "set_timeout"]
    assert timeout_events[-1] == 2000
    polling_timeouts = timeout_events[:-1]
    assert polling_timeouts == sorted(polling_timeouts, reverse=True)
    assert len(polling_timeouts) == 5


def test_run_segmented_capture_ready_deadline_does_not_export(
    monkeypatch, tmp_path
):
    backend = _TimeoutTrackingBackend([2], operation_conditions=[8, 8])
    clock = iter([0.0, 0.005, 0.01, 0.03])
    monkeypatch.setattr(segmented_capture_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(segmented_capture_module.time, "sleep", lambda _: None)

    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(
                1,
                2,
                timeout_ms=20,
                poll_interval_ms=1,
                output_dir=tmp_path,
            ),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "failed"
    assert result.result["acquired_segments"] == 2
    assert result.result["exported_segments"] == 0
    assert "20 ms" in result.result["error"]
    assert "2 of 2" in result.result["error"]
    assert "not ready" in result.result["error"]
    assert backend.timeout == 2000
    assert backend.history[-2:] == [":ACQuire:MODE?", ":SYSTem:ERRor?"]
    assert not list(tmp_path.glob("segment_*.csv"))
    assert not any(
        command.startswith(":ACQuire:SEGMented:INDex")
        or command in {
            ":WAVeform:SEGMented:TTAG?",
            ":WAVeform:PREamble?",
            ":WAVeform:DATA?",
        }
        for command in backend.history
    )


def test_run_segmented_capture_acquisition_type_timeout_stops_before_writes(tmp_path):
    backend = _ExportVisaTimeoutBackend(":ACQuire:TYPE?")

    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "failed"
    assert "acquisition-type read timed out" in result.result["error"]
    assert backend.history[-1] == ":ACQuire:TYPE?"
    assert ":ACQuire:MODE SEGMented" not in backend.history
    assert ":ACQuire:SEGMented:COUNt 2" not in backend.history
    assert ":ACQuire:MODE?" not in backend.history[backend.history.index(":ACQuire:TYPE?") + 1 :]
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["final_mode"] is None


def test_run_segmented_capture_idn_timeout_stops_scpi(tmp_path):
    backend = _ExportVisaTimeoutBackend("*IDN?")

    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "failed"
    assert "IDN read timed out" in result.result["error"]
    assert backend.history == ["*IDN?"]
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["final_mode"] is None
    assert manifest["system_error"] is None


def test_run_segmented_capture_operation_condition_timeout_stops_scpi(tmp_path):
    backend = _ExportVisaTimeoutBackend(":OPERegister:CONDition?")

    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "failed"
    assert result.result["acquired_segments"] == 2
    assert result.result["exported_segments"] == 0
    assert "operation-condition read timed out" in result.result["error"]
    assert backend.timeout == 2000
    timeout_index = backend.history.index(":OPERegister:CONDition?")
    assert backend.history[timeout_index + 1 :] == []
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["final_mode"] is None
    assert manifest["system_error"] is None
    assert (tmp_path / "scpi.log").exists()


@pytest.mark.parametrize(
    "failure_command",
    [
        ":WAVeform:SEGMented:TTAG?",
        ":WAVeform:PREamble?",
        ":WAVeform:DATA?",
    ],
)
def test_run_segmented_capture_export_read_timeout_stops_scpi(
    failure_command, tmp_path
):
    backend = _ExportVisaTimeoutBackend(failure_command)

    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "failed"
    assert result.result["exported_segments"] == 0
    assert "segment 1" in result.result["error"]
    assert not list(tmp_path.glob("segment_*.csv"))
    timeout_index = backend.history.index(failure_command)
    assert backend.history[timeout_index + 1 :] == []
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["final_mode"] is None
    assert manifest["system_error"] is None
    assert (tmp_path / "scpi.log").exists()


def test_run_segmented_capture_segment_two_timeout_keeps_segment_one(
    tmp_path,
):
    backend = _ExportVisaTimeoutBackend(
        ":WAVeform:SEGMented:TTAG?", fail_segment=2
    )

    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "partial"
    assert result.result["exported_segments"] == 1
    assert (tmp_path / "segment_0001.csv").exists()
    assert not (tmp_path / "segment_0002.csv").exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert [entry["index"] for entry in manifest["segments"]] == [1]
    assert manifest["final_mode"] is None
    assert manifest["system_error"] is None
    timeout_index = max(
        index
        for index, command in enumerate(backend.history)
        if command == ":WAVeform:SEGMented:TTAG?"
    )
    assert backend.history[timeout_index + 1 :] == []


def test_run_segmented_capture_final_mode_timeout_skips_system_error(tmp_path):
    backend = _FinalModeVisaTimeoutBackend()

    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "partial"
    assert result.result["exported_segments"] == 2
    assert "final mode read timed out" in result.result["error"]
    final_mode_index = max(
        index
        for index, command in enumerate(backend.history)
        if command == ":ACQuire:MODE?"
    )
    assert backend.history[final_mode_index + 1 :] == []
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["system_error"] is None


def test_run_segmented_capture_normal_deadline_keeps_final_state_queries(
    monkeypatch, tmp_path
):
    backend = _AcquiredCountSequenceBackend([0])
    clock = iter([100.0, 100.01, 100.11])
    monkeypatch.setattr(segmented_capture_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(segmented_capture_module.time, "sleep", lambda _: None)

    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SegmentedCaptureRequest(
                1, 2, timeout_ms=100, poll_interval_ms=1, output_dir=tmp_path
            ),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "failed"
    assert result.result["final_mode"] == "segmented"
    assert backend.history[-2:] == [":ACQuire:MODE?", ":SYSTem:ERRor?"]


def test_run_segmented_capture_07_20_omits_waveform_all_command(tmp_path):
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox4034a",
        resource_name="SIM::keysight-dsox4034a::INSTR",
        firmware="07.20.2017102615",
    )

    with Oscilloscope(backend) as scope:
        result = run_segmented_capture(
            scope,
            "SIM::keysight-dsox4034a::INSTR",
            SegmentedCaptureRequest(1, 2, poll_interval_ms=1, output_dir=tmp_path),
        )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert segmented_waveform_all_command(False) not in backend.history
    assert ":ACQuire:SEGMented:INDex 1" in backend.history
    assert ":WAVeform:SEGMented:TTAG?" in backend.history
    assert (tmp_path / "segment_0001.csv").exists()
    assert (tmp_path / "segment_0002.csv").exists()


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
    backend = _AcquiredCountSequenceBackend([1, 1], firmware="07.30")
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
    ("model", "firmware", "contains_all_off"),
    [
        ("DSOX2004A", "07.30", False),
        ("DSOX3024A", "07.30", False),
        ("DSOX4024A", None, False),
        ("DSOX4024A", "07.20", False),
        ("DSOX4024A", "07.30", True),
    ],
)
def test_segmented_capture_plan_respects_waveform_all_profile_boundary(
    model, firmware, contains_all_off, tmp_path
):
    planned, _, _ = plan_segmented_capture(
        SegmentedCaptureRequest(1, 2, output_dir=tmp_path),
        capabilities_for_model(model),
        firmware=firmware,
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
    assert backend.history[-2:] == [":ACQuire:MODE?", ":SYSTem:ERRor?"]


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
