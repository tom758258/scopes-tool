import json
import logging
from datetime import datetime

import pytest

from scopes_tool_core import batch
from scopes_tool_core import capture_batch, workflow
from scopes_tool_core.operation_types import CaptureBatchRequest, _OperationError
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.idn import parse_idn
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.status import SystemErrorEntry


def test_prepare_default_batch_output_dir_uses_timestamp_and_collision_suffix(tmp_path):
    now = datetime(2026, 5, 16, 12, 34, 56)

    first = batch.prepare_batch_output_dir(None, now=now, base_dir=tmp_path)
    second = batch.prepare_batch_output_dir(None, now=now, base_dir=tmp_path)
    third = batch.prepare_batch_output_dir(None, now=now, base_dir=tmp_path)

    assert first == tmp_path / "2026-05-16-12-34-56"
    assert second == tmp_path / "2026-05-16-12-34-56-2"
    assert third == tmp_path / "2026-05-16-12-34-56-3"
    assert first.is_dir()
    assert second.is_dir()
    assert third.is_dir()


def test_prepare_specified_batch_output_dir_accepts_missing_directory(tmp_path):
    output_dir = tmp_path / "new-batch"

    assert batch.prepare_batch_output_dir(output_dir) == output_dir

    assert output_dir.is_dir()


def test_prepare_specified_batch_output_dir_accepts_empty_directory(tmp_path):
    output_dir = tmp_path / "empty-batch"
    output_dir.mkdir()

    assert batch.prepare_batch_output_dir(output_dir) == output_dir


def test_prepare_specified_batch_output_dir_rejects_non_empty_directory(tmp_path):
    output_dir = tmp_path / "existing-batch"
    output_dir.mkdir()
    (output_dir / "old.csv").write_text("old\n", encoding="utf-8")

    with pytest.raises(OscilloscopeError, match="must be empty"):
        batch.prepare_batch_output_dir(output_dir)


def test_prepare_specified_batch_output_dir_rejects_request_json_only_directory(
    tmp_path,
):
    output_dir = tmp_path / "request-json-batch"
    output_dir.mkdir()
    (output_dir / "request.json").write_text("{}", encoding="utf-8")

    with pytest.raises(OscilloscopeError, match="must be empty"):
        batch.prepare_batch_output_dir(output_dir)


def test_batch_capture_paths_use_minimum_four_digit_width(tmp_path):
    csv_path, meta_path = batch.batch_capture_paths(tmp_path, 3, 12)

    assert csv_path == tmp_path / "waveform_0003.csv"
    assert meta_path == tmp_path / "waveform_0003_meta.json"


def test_batch_capture_paths_expand_width_for_large_count(tmp_path):
    csv_path, meta_path = batch.batch_capture_paths(tmp_path, 12345, 12345)

    assert csv_path.name == "waveform_12345.csv"
    assert meta_path.name == "waveform_12345_meta.json"


def test_write_batch_manifest_json_fields_and_capture_list(tmp_path):
    idn = parse_idn("KEYSIGHT TECHNOLOGIES,DSOX4024A,MY123,07.20")
    entry = SystemErrorEntry(code=0, message="No error", raw='+0,"No error"')
    manifest = batch.BatchManifest(
        schema_version=batch.BATCH_SCHEMA_VERSION,
        start_time="2026-05-16T12:00:00+08:00",
        end_time="2026-05-16T12:00:01+08:00",
        status="completed",
        resource="USB0::FAKE::INSTR",
        backend="fake",
        timeout_ms=2000,
        idn=batch.idn_manifest_dict(idn),
        channels=[1, 2],
        points=1000,
        format="BYTE",
        requested_count=1,
        interval_seconds=0.0,
        captures=[
            {
                "index": 1,
                "csv": "waveform_0001.csv",
                "metadata": "waveform_0001_meta.json",
                "actual_points": {"CH1": 2, "CH2": 2},
                "system_error": batch.system_error_manifest_dict(entry),
            }
        ],
    )

    manifest_path = batch.write_batch_manifest(manifest, tmp_path / "manifest.json")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["status"] == "completed"
    assert payload["idn"]["model"] == "DSOX4024A"
    assert payload["channels"] == [1, 2]
    assert payload["captures"] == [
        {
            "index": 1,
            "csv": "waveform_0001.csv",
            "metadata": "waveform_0001_meta.json",
            "actual_points": {"CH1": 2, "CH2": 2},
            "system_error": {
                "code": 0,
                "message": "No error",
                "raw": '+0,"No error"',
                "is_error": False,
            },
        }
    ]


def test_workflow_scpi_logging_writes_package_debug_to_file(tmp_path):
    log_path = tmp_path / "scpi.log"
    logger = logging.getLogger("scopes_tool_core.scpi")

    with workflow.workflow_scpi_logging(log_path):
        logger.debug("SCPI >> *IDN?")
        logger.debug("SCPI << IDN")

    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "scopes_tool_core.scpi DEBUG: SCPI >> *IDN?",
        "scopes_tool_core.scpi DEBUG: SCPI << IDN",
    ]


def test_run_capture_batch_completes_and_writes_representative_artifacts(tmp_path, check_incremental_manifest):
    scope = Oscilloscope(
        SimulatorBackend(physical_model_id="keysight-dsox4024a")
    )
    output_dir = tmp_path / "batch"

    result = capture_batch.run_capture_batch(
        scope,
        "SIM::keysight-dsox4024a::INSTR",
        CaptureBatchRequest(
            channels=[1, 2],
            requested_count=2,
            output_dir=output_dir,
        ),
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert result.result["completed_count"] == 2
    assert manifest["status"] == "completed"
    assert len(manifest["captures"]) == 2
    assert manifest["captures"][0]["csv"] == "waveform_0001.csv"
    assert (output_dir / "waveform_0001.csv").exists()
    assert (output_dir / "waveform_0001_meta.json").exists()
    assert (output_dir / "scpi.log").exists()
    check_incremental_manifest(output_dir, "captures", 2)



def test_snapshot_failure_preserves_only_committed_captures(tmp_path, fail_progress_snapshot):
    fail_progress_snapshot()
    output_dir = tmp_path / "failed"
    samples, progress = [], []
    with pytest.raises(OscilloscopeError) as caught:
        capture_batch.run_capture_batch(
            Oscilloscope(SimulatorBackend(physical_model_id="keysight-dsox4024a")),
            "SIM::keysight-dsox4024a::INSTR",
            CaptureBatchRequest(channels=[1], requested_count=3, output_dir=output_dir),
            sample_reporter=samples.append, progress_reporter=progress.append,
        )
    result = caught.value.result
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result.exit_code == 1
    assert result.result["status"] == "error"
    assert result.result["completed_count"] == 1
    assert [capture["index"] for capture in manifest["captures"]] == [1]
    assert [sample["index"] for sample in samples] == [1]
    assert [item.completed_count for item in progress] == [1]
    assert (output_dir / "waveform_0002.csv").exists()


def test_run_capture_batch_cancels_before_next_capture_and_reports_sample(tmp_path):
    scope = Oscilloscope(
        SimulatorBackend(physical_model_id="keysight-dsox4024a")
    )
    stop_checks = 0
    samples = []
    progress = []

    def stop_requested():
        nonlocal stop_checks
        stop_checks += 1
        return stop_checks >= 2

    result = capture_batch.run_capture_batch(
        scope,
        "SIM::keysight-dsox4024a::INSTR",
        CaptureBatchRequest(
            channels=[1],
            requested_count=3,
            output_dir=tmp_path / "cancelled",
        ),
        stop_requested=stop_requested,
        sample_reporter=samples.append,
        progress_reporter=progress.append,
    )

    manifest = json.loads(
        (tmp_path / "cancelled" / "manifest.json").read_text(encoding="utf-8")
    )
    assert result.exit_code == 130
    assert result.result["status"] == "cancelled"
    assert result.result["error"] is None
    assert result.result["completed_count"] == 1
    assert manifest["status"] == "cancelled"
    assert manifest["error"] is None
    assert len(samples) == 1
    assert progress[0].completed_count == 1
    assert not (tmp_path / "cancelled" / "waveform_0002.csv").exists()


def test_run_capture_batch_completion_precedes_late_cancellation(tmp_path):
    scope = Oscilloscope(
        SimulatorBackend(physical_model_id="keysight-dsox4024a")
    )
    output_dir = tmp_path / "completed"
    cancelled = False

    def stop_requested():
        return cancelled

    def report_sample(_sample):
        nonlocal cancelled
        cancelled = True

    result = capture_batch.run_capture_batch(
        scope,
        "SIM::keysight-dsox4024a::INSTR",
        CaptureBatchRequest(
            channels=[1],
            requested_count=1,
            output_dir=output_dir,
        ),
        stop_requested=stop_requested,
        sample_reporter=report_sample,
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert result.result["error"] is None
    assert result.result["completed_count"] == 1
    assert manifest["status"] == "completed"
    assert manifest["error"] is None
    assert len(manifest["captures"]) == 1
    assert (output_dir / "waveform_0001.csv").exists()
    assert (output_dir / "waveform_0001_meta.json").exists()


def test_run_capture_batch_uses_interruptible_wait_between_captures(
    tmp_path, monkeypatch
):
    scope = Oscilloscope(
        SimulatorBackend(physical_model_id="keysight-dsox4024a")
    )
    waits = []

    def fake_wait(seconds, *, stop_requested=None):
        waits.append((seconds, stop_requested))
        return True

    monkeypatch.setattr(capture_batch, "interruptible_wait", fake_wait)
    result = capture_batch.run_capture_batch(
        scope,
        "SIM::keysight-dsox4024a::INSTR",
        CaptureBatchRequest(
            channels=[1],
            requested_count=2,
            interval_seconds=1.25,
            output_dir=tmp_path / "wait",
        ),
    )

    assert result.exit_code == 0
    assert waits == [(1.25, None)]


@pytest.mark.parametrize("terminal_status", ["instrument_error", "cancelled", "completed"])
@pytest.mark.parametrize("persistent_failure", [False, True], ids=["retry", "persistent"])
def test_final_manifest_failure_preserves_capture_batch_error_state(
    tmp_path, monkeypatch, terminal_status, persistent_failure
):
    scope = Oscilloscope(SimulatorBackend(physical_model_id="keysight-dsox4024a"))
    output_dir = tmp_path / "final-failure"
    samples, progress, failed_snapshots = [], [], []
    write_manifest = capture_batch.write_batch_manifest
    instrument_error = terminal_status == "instrument_error"
    status = SystemErrorEntry(
        code=-222 if instrument_error else 0,
        message="Data out of range" if instrument_error else "No error",
        raw='-222,"Data out of range"' if instrument_error else '+0,"No error"',
    )
    monkeypatch.setattr(scope, "workflow_status", lambda: status)

    def fail_final_manifest(payload, path):
        if payload["status"] != "running":
            if persistent_failure or not failed_snapshots:
                failed_snapshots.append(dict(payload))
                raise OSError("final manifest publication failed")
        return write_manifest(payload, path)

    monkeypatch.setattr(capture_batch, "write_batch_manifest", fail_final_manifest)
    with pytest.raises(_OperationError, match="final manifest publication failed") as caught:
        capture_batch.run_capture_batch(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            CaptureBatchRequest(
                channels=[1],
                requested_count=1 if terminal_status == "completed" else 3,
                output_dir=output_dir,
            ),
            stop_requested=lambda: terminal_status == "cancelled" and bool(samples),
            sample_reporter=samples.append,
            progress_reporter=progress.append,
        )

    result = caught.value.result
    expected_status = "error" if terminal_status == "completed" else terminal_status
    assert result.exit_code == 1
    assert result.result["status"] == expected_status
    if terminal_status == "completed":
        assert "final manifest publication failed" in result.result["error"]
    else:
        assert result.result["error"] is None
    assert isinstance(caught.value.__cause__, OscilloscopeError)
    assert isinstance(caught.value.__cause__.__cause__, OSError)
    assert result.result["completed_count"] == 1
    assert result.system_error["code"] == status.code
    assert [entry["index"] for entry in result.result["captures"]] == [1]
    assert samples == [dict(failed_snapshots[0]["captures"][0])]
    assert [item.completed_count for item in progress] == [1]
    assert not (output_dir / "waveform_0002.csv").exists()
    for artifact in result.files:
        assert (output_dir / artifact["path"]).is_file()

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    journal = output_dir / ".manifest-history.jsonl"
    if persistent_failure:
        assert manifest["status"] == "running"
        assert manifest["completed_count"] == 1
        assert manifest["captures"] == []
        assert [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()] == samples
        assert len(failed_snapshots) == 2
        assert failed_snapshots[1]["status"] == expected_status
        assert failed_snapshots[1]["captures"] == failed_snapshots[0]["captures"]
        if terminal_status != "completed":
            assert failed_snapshots[1]["end_time"] == failed_snapshots[0]["end_time"]
    else:
        assert manifest["status"] == expected_status
        assert manifest["error"] == result.result["error"]
        assert manifest["captures"] == samples
        assert not journal.exists()


@pytest.mark.parametrize("error_type", [OscilloscopeError, OSError, RuntimeError])
@pytest.mark.parametrize("reporter", ["sample_reporter", "progress_reporter"])
def test_capture_batch_reporter_exception_propagates_unchanged(
    tmp_path, error_type, reporter
):
    output_dir = tmp_path / "reporter-failure"
    error = error_type("reporter failed")

    def fail_reporter(_event):
        raise error

    with pytest.raises(error_type) as caught:
        capture_batch.run_capture_batch(
            Oscilloscope(SimulatorBackend(physical_model_id="keysight-dsox4024a")),
            "SIM::keysight-dsox4024a::INSTR",
            CaptureBatchRequest(channels=[1], requested_count=3, output_dir=output_dir),
            **{reporter: fail_reporter},
        )

    assert caught.value is error
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "error"
    assert manifest["error"] == "reporter failed"
    assert [entry["index"] for entry in manifest["captures"]] == [1]
    assert not (output_dir / "waveform_0002.csv").exists()
