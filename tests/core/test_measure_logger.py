import csv
from datetime import datetime
import json

import pytest

from scopes_tool_core import measure_logger
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend

def test_prepare_default_measure_log_output_dir_uses_timestamp_and_collision_suffix(tmp_path, monkeypatch):
    now = datetime(2026, 5, 16, 12, 34, 56)

    first = measure_logger.prepare_measure_log_output_dir(None, now=now, base_dir=tmp_path)
    second = measure_logger.prepare_measure_log_output_dir(None, now=now, base_dir=tmp_path)
    third = measure_logger.prepare_measure_log_output_dir(None, now=now, base_dir=tmp_path)

    assert first == tmp_path / "2026-05-16-12-34-56"
    assert second == tmp_path / "2026-05-16-12-34-56-2"
    assert third == tmp_path / "2026-05-16-12-34-56-3"
    assert first.is_dir()
    assert second.is_dir()
    assert third.is_dir()


def test_prepare_specified_measure_log_output_dir_accepts_missing_directory(tmp_path):
    output_dir = tmp_path / "new-measure-log"
    assert measure_logger.prepare_measure_log_output_dir(output_dir) == output_dir
    assert output_dir.is_dir()


def test_prepare_specified_measure_log_output_dir_accepts_empty_directory(tmp_path):
    output_dir = tmp_path / "empty-measure-log"
    output_dir.mkdir()
    assert measure_logger.prepare_measure_log_output_dir(output_dir) == output_dir


def test_prepare_specified_measure_log_output_dir_rejects_non_empty_directory(tmp_path):
    output_dir = tmp_path / "existing-measure-log"
    output_dir.mkdir()
    (output_dir / "old.csv").write_text("old\n", encoding="utf-8")

    with pytest.raises(OscilloscopeError, match="must be empty"):
        measure_logger.prepare_measure_log_output_dir(output_dir)


def test_prepare_specified_measure_log_output_dir_rejects_request_json_only_directory(
    tmp_path,
):
    output_dir = tmp_path / "request-json-measure-log"
    output_dir.mkdir()
    (output_dir / "request.json").write_text("{}", encoding="utf-8")

    with pytest.raises(OscilloscopeError, match="must be empty"):
        measure_logger.prepare_measure_log_output_dir(output_dir)


def test_write_measure_log_manifest_json(tmp_path):
    manifest = measure_logger.MeasureLogManifest(
        start_time="2026-05-16T12:00:00+08:00",
        end_time="2026-05-16T12:00:05+08:00",
        status="completed",
        resource="USB0::FAKE::INSTR",
        backend="fake",
        timeout_ms=2000,
        idn={"vendor": "KEYSIGHT", "model": "DSOX4024A", "serial": "MY123", "firmware": "07.20"},
        channels=[1, 2],
        items=["vpp", "frequency"],
        pairs=["1:2"],
        pair_items=["phase"],
        interval_seconds=1.0,
        requested_count=5,
        requested_duration_seconds=None,
        completed_rows=5,
        files=[
            {"kind": "csv", "path": "measurements.csv"},
            {"kind": "manifest", "path": "manifest.json"},
        ],
        rows=[
            {
                "index": 1,
                "timestamp_iso": "2026-05-16T12:00:01+08:00",
                "elapsed_seconds": 0.1,
                "system_error": {
                    "code": 0,
                    "message": "No error",
                    "raw": '+0,"No error"',
                    "is_error": False,
                },
            }
        ],
    )

    manifest_path = tmp_path / "manifest.json"
    written_path = measure_logger.write_measure_log_manifest(manifest, manifest_path)

    assert written_path == manifest_path
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["status"] == "completed"
    assert payload["idn"]["model"] == "DSOX4024A"
    assert payload["channels"] == [1, 2]
    assert payload["items"] == ["vpp", "frequency"]
    assert payload["pairs"] == ["1:2"]
    assert payload["pair_items"] == ["phase"]
    assert payload["completed_rows"] == 5
    assert len(payload["files"]) == 2
    assert payload["rows"][0]["system_error"]["code"] == 0


def test_log_measurements_workflow_runs_successfully_and_writes_files(tmp_path, capsys):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    csv_path, manifest_path, scpi_log_path = measure_logger.measure_log_paths(tmp_path)

    result = measure_logger.log_measurements_workflow(
        scope=scope,
        resource="SIM::keysight-dsox4024a::INSTR",
        output_dir=tmp_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        scpi_log_path=scpi_log_path,
        channels=[1, 2],
        items=["vpp", "frequency"],
        pairs=[(1, 2)],
        pair_items=["phase"],
        interval_seconds=0.1,
        requested_count=3,
        requested_duration_seconds=None,
        stop_on_error=False,
    )

    assert result.exit_code == 0
    assert result.manifest.status == "completed"
    assert result.human_lines
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert csv_path.exists()
    assert manifest_path.exists()
    assert scpi_log_path.exists()

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["status"] == "completed"
    assert manifest_data["completed_rows"] == 3
    assert len(manifest_data["rows"]) == 3
    assert manifest_data["rows"][0]["system_error"]["raw"] == '+0,"No error"'

    with csv_path.open("r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    assert len(reader) == 4
    assert reader[0] == ["timestamp_iso", "elapsed_seconds", "ch1_vpp", "ch1_frequency", "ch2_vpp", "ch2_frequency", "ch1_ch2_phase"]
    for i in range(1, 4):
        assert float(reader[i][1]) >= 0.0
        assert float(reader[i][2]) > 0.0
        assert float(reader[i][3]) > 0.0
        assert float(reader[i][4]) > 0.0
        assert float(reader[i][5]) > 0.0
        assert float(reader[i][6]) is not None


def test_log_measurements_workflow_no_save_keeps_only_compact_state(tmp_path):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    result = measure_logger.log_measurements_workflow(
        scope=scope,
        resource="SIM::keysight-dsox4024a::INSTR",
        output_dir=None,
        csv_path=None,
        manifest_path=None,
        scpi_log_path=None,
        channels=[1],
        items=["vpp"],
        pairs=[],
        pair_items=[],
        interval_seconds=0,
        requested_count=3,
        requested_duration_seconds=None,
        stop_on_error=False,
    )

    assert result.exit_code == 0
    assert result.manifest.completed_rows == 3
    assert result.manifest.last_measurement["index"] == 3
    assert result.manifest.rows == []
    assert result.manifest.files == []
    assert list(tmp_path.iterdir()) == []


def test_log_measurements_workflow_respects_duration_limit(tmp_path):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    csv_path, manifest_path, scpi_log_path = measure_logger.measure_log_paths(tmp_path)

    result = measure_logger.log_measurements_workflow(
        scope=scope,
        resource="SIM::keysight-dsox4024a::INSTR",
        output_dir=tmp_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        scpi_log_path=scpi_log_path,
        channels=[1],
        items=["vpp"],
        pairs=[],
        pair_items=[],
        interval_seconds=0.5,
        requested_count=None,
        requested_duration_seconds=0.1,
        stop_on_error=False,
    )

    assert result.exit_code == 0
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["status"] == "completed"
    assert manifest_data["completed_rows"] == 1


def test_log_measurements_workflow_handles_invalid_sentinels_and_errors(tmp_path):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a", invalid_measurement_channels={2})
    scope = Oscilloscope(backend)
    scope.query_idn()

    csv_path, manifest_path, scpi_log_path = measure_logger.measure_log_paths(tmp_path)

    result = measure_logger.log_measurements_workflow(
        scope=scope,
        resource="SIM::keysight-dsox4024a::INSTR",
        output_dir=tmp_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        scpi_log_path=scpi_log_path,
        channels=[1, 2],
        items=["vpp"],
        pairs=[],
        pair_items=[],
        interval_seconds=0.01,
        requested_count=2,
        requested_duration_seconds=None,
        stop_on_error=False,
    )

    assert result.exit_code == 0
    with csv_path.open("r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    assert reader[0] == ["timestamp_iso", "elapsed_seconds", "ch1_vpp", "ch2_vpp"]
    assert reader[1][3] == "NaN"
    assert float(reader[1][2]) > 0.0


def test_log_measurements_workflow_stops_on_error(tmp_path):
    # Setup simulator with system error triggered on queries
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a", system_errors=['-113,"Undefined header"'])
    scope = Oscilloscope(backend)
    scope.query_idn()

    csv_path, manifest_path, scpi_log_path = measure_logger.measure_log_paths(tmp_path)

    result = measure_logger.log_measurements_workflow(
        scope=scope,
        resource="SIM::keysight-dsox4024a::INSTR",
        output_dir=tmp_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        scpi_log_path=scpi_log_path,
        channels=[1],
        items=["vpp"],
        pairs=[],
        pair_items=[],
        interval_seconds=0.01,
        requested_count=3,
        requested_duration_seconds=None,
        stop_on_error=True,
    )

    assert result.exit_code == 1
    assert result.system_error["code"] == -113
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["status"] == "instrument_error"
    assert "Undefined header" in manifest_data["error"]
    assert manifest_data["completed_rows"] == 1
    assert manifest_data["rows"][0]["system_error"]["code"] == -113


def test_log_measurements_workflow_records_interrupt(tmp_path, monkeypatch):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(scope, "query_measurement", interrupt)
    csv_path, manifest_path, scpi_log_path = measure_logger.measure_log_paths(tmp_path)

    result = measure_logger.log_measurements_workflow(
        scope=scope,
        resource="SIM::keysight-dsox4024a::INSTR",
        output_dir=tmp_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        scpi_log_path=scpi_log_path,
        channels=[1],
        items=["vpp"],
        pairs=[],
        pair_items=[],
        interval_seconds=0,
        requested_count=1,
        requested_duration_seconds=None,
        stop_on_error=False,
    )

    assert result.exit_code == 130
    assert result.manifest.status == "interrupted"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["status"] == "interrupted"
    assert manifest_data["error"] == "KeyboardInterrupt"


def test_log_measurements_workflow_discards_partial_row_on_cancellation(tmp_path):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()
    csv_path, manifest_path, scpi_log_path = measure_logger.measure_log_paths(tmp_path)
    stop_checks = 0

    def stop_requested():
        nonlocal stop_checks
        stop_checks += 1
        return stop_checks >= 2

    result = measure_logger.log_measurements_workflow(
        scope=scope,
        resource="SIM::keysight-dsox4024a::INSTR",
        output_dir=tmp_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        scpi_log_path=scpi_log_path,
        channels=[1, 2],
        items=["vpp"],
        pairs=[],
        pair_items=[],
        interval_seconds=0,
        requested_count=3,
        requested_duration_seconds=None,
        stop_on_error=False,
        stop_requested=stop_requested,
    )

    assert result.exit_code == 130
    assert result.manifest.status == "cancelled"
    assert result.manifest.error is None
    assert result.manifest.completed_rows == 0
    with csv_path.open("r", encoding="utf-8") as handle:
        assert len(list(csv.reader(handle))) == 1
    assert backend.history.count(":MEASure:VPP? CHANnel1") == 1
    assert ":MEASure:VPP? CHANnel2" not in backend.history


def test_log_measurements_workflow_reports_only_persisted_rows_before_cancel(tmp_path):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()
    csv_path, manifest_path, scpi_log_path = measure_logger.measure_log_paths(tmp_path)
    stop_checks = 0
    samples = []
    progress = []

    def stop_requested():
        nonlocal stop_checks
        stop_checks += 1
        return stop_checks >= 3

    result = measure_logger.log_measurements_workflow(
        scope=scope,
        resource="SIM::keysight-dsox4024a::INSTR",
        output_dir=tmp_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        scpi_log_path=scpi_log_path,
        channels=[1],
        items=["vpp"],
        pairs=[],
        pair_items=[],
        interval_seconds=0,
        requested_count=3,
        requested_duration_seconds=None,
        stop_on_error=False,
        stop_requested=stop_requested,
        sample_reporter=samples.append,
        progress_reporter=progress.append,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result.manifest.status == "cancelled"
    assert manifest["status"] == "cancelled"
    assert manifest["error"] is None
    assert manifest["completed_rows"] == 1
    assert len(samples) == 1
    assert float(samples[0]["values"]["ch1_vpp"]) > 0
    assert progress[0].completed_count == 1
    assert progress[0].total_count == 3


def test_log_measurements_workflow_completion_precedes_late_cancellation(tmp_path):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")
    scope = Oscilloscope(backend)
    scope.query_idn()
    csv_path, manifest_path, scpi_log_path = measure_logger.measure_log_paths(tmp_path)
    cancelled = False

    def stop_requested():
        return cancelled

    def report_sample(_sample):
        nonlocal cancelled
        cancelled = True

    result = measure_logger.log_measurements_workflow(
        scope=scope,
        resource="SIM::keysight-dsox4024a::INSTR",
        output_dir=tmp_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        scpi_log_path=scpi_log_path,
        channels=[1],
        items=["vpp"],
        pairs=[],
        pair_items=[],
        interval_seconds=0,
        requested_count=1,
        requested_duration_seconds=None,
        stop_on_error=False,
        stop_requested=stop_requested,
        sample_reporter=report_sample,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert result.manifest.status == "completed"
    assert result.manifest.error is None
    assert result.manifest.completed_rows == 1
    assert manifest["status"] == "completed"
    assert manifest["error"] is None
    assert manifest["completed_rows"] == 1
    with csv_path.open("r", encoding="utf-8") as handle:
        assert len(list(csv.reader(handle))) == 2
    assert scpi_log_path.exists()
