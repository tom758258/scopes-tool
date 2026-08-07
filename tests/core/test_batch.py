import json
import logging
from datetime import datetime

import pytest

from scopes_tool_core import batch
from scopes_tool_core import operations, workflow
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


def test_run_capture_batch_completes_and_writes_representative_artifacts(tmp_path):
    scope = Oscilloscope(
        SimulatorBackend(physical_model_id="keysight-dsox4024a")
    )
    output_dir = tmp_path / "batch"

    result = operations.run_capture_batch(
        scope,
        "SIM::keysight-dsox4024a::INSTR",
        operations.CaptureBatchRequest(
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

    result = operations.run_capture_batch(
        scope,
        "SIM::keysight-dsox4024a::INSTR",
        operations.CaptureBatchRequest(
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

    result = operations.run_capture_batch(
        scope,
        "SIM::keysight-dsox4024a::INSTR",
        operations.CaptureBatchRequest(
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

    monkeypatch.setattr(operations, "interruptible_wait", fake_wait)
    result = operations.run_capture_batch(
        scope,
        "SIM::keysight-dsox4024a::INSTR",
        operations.CaptureBatchRequest(
            channels=[1],
            requested_count=2,
            interval_seconds=1.25,
            output_dir=tmp_path / "wait",
        ),
    )

    assert result.exit_code == 0
    assert waits == [(1.25, None)]
