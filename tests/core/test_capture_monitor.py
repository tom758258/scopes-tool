from __future__ import annotations

import csv
import json

import pytest

from scopes_tool_core import capture_monitor
from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.waveform import MultiChannelWaveformCapture, WaveformCapture, WaveformPreamble


RESOURCE = "SIM::keysight-dsox4024a::INSTR"


def _scope():
    return Oscilloscope(SimulatorBackend(physical_model_id="keysight-dsox4024a"))


def _capture(channel, value, *, points=1000):
    time_s = tuple(index * 1e-6 for index in range(points))
    values = (value,) + tuple(0.0 for _ in range(points - 1))
    preamble = WaveformPreamble(
        raw=f"0,0,{points},1,1e-6,0,0,1,0,0",
        format_code=0,
        type_code=0,
        points=points,
        count=1,
        x_increment=1e-6,
        x_origin=0.0,
        x_reference=0,
        y_increment=1.0,
        y_origin=0.0,
        y_reference=0,
    )
    return WaveformCapture(
        channel=channel,
        requested_points=points,
        format_name="BYTE",
        preamble=preamble,
        raw_samples=tuple(0 for _ in range(points)),
        time_s=time_s,
        vertical_values=values,
        vertical_unit="V",
    )


def _request(output_dir, **values):
    defaults = {"channels": [1], "count": 2, "output_dir": output_dir}
    defaults.update(values)
    return capture_monitor.CaptureMonitorRequest(**defaults)


@pytest.mark.parametrize(
    "values, message",
    [
        ({"retention_points": 999}, "at least points per capture"),
        ({"retention_points": 1500}, "multiple of points per capture"),
    ],
)
def test_retention_default_and_validation(tmp_path, values, message):
    assert capture_monitor.CaptureMonitorRequest(channels=[1], count=1).retention_points == 250000
    with pytest.raises(ParameterValidationError, match=message):
        capture_monitor.plan_capture_monitor(
            _request(tmp_path / "never", **values), _scope().backend._capabilities
        )


def test_retention_drops_oldest_complete_chunk_but_preserves_overall_max(
    monkeypatch, tmp_path
):
    captures = iter((_capture(1, 9.0), _capture(1, 2.0), _capture(1, 3.0)))
    monkeypatch.setattr(capture_monitor, "_capture_waveform", lambda *args: next(captures))
    updates = []
    output_dir = tmp_path / "retained"

    result = capture_monitor.run_capture_monitor(
        _scope(),
        RESOURCE,
        _request(output_dir, count=3, retention_points=2000),
        sample_reporter=updates.append,
    )

    assert result.exit_code == 0
    assert result.result["completed_count"] == 3
    assert result.result["total_observed_points"] == 3000
    assert result.result["retained_points"] == 2000
    assert result.result["dropped_points"] == 1000
    assert result.result["first_retained_capture_index"] == 2
    assert result.result["metrics"]["CH1"]["maximum"] == 9.0
    assert updates[-1]["dropped_capture_count"] == 1
    assert len(updates[-1]["channels"]["CH1"]["values"]) == 1000
    with (output_dir / "retained_waveforms.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2000
    assert rows[0]["capture_index"] == "2"
    assert rows[0]["global_sample_index"] == "1000"
    assert rows[0]["sample_index"] == "0"


def test_multichannel_retention_is_per_channel(monkeypatch, tmp_path):
    captures = iter(
        (
            MultiChannelWaveformCapture((_capture(1, 1.0), _capture(2, 4.0))),
            MultiChannelWaveformCapture((_capture(1, 2.0), _capture(2, 5.0))),
        )
    )
    monkeypatch.setattr(capture_monitor, "_capture_waveform", lambda *args: next(captures))

    result = capture_monitor.run_capture_monitor(
        _scope(),
        RESOURCE,
        _request(tmp_path / "multi", channels=[1, 2], retention_points=1000),
    )

    assert result.result["retained_points"] == 1000
    assert result.result["dropped_points"] == 1000
    assert set(result.result["metrics"]) == {"CH1", "CH2"}
    header = (tmp_path / "multi" / "retained_waveforms.csv").read_text(
        encoding="utf-8"
    ).splitlines()[0]
    assert header == "capture_index,global_sample_index,sample_index,time_s,ch1_v,ch2_v"


def test_no_save_keeps_compact_result_without_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(capture_monitor, "_capture_waveform", lambda *args: _capture(1, 2.0))
    output_dir = tmp_path / "not-created"

    result = capture_monitor.run_capture_monitor(
        _scope(), RESOURCE, _request(output_dir, count=1, save_results=False)
    )

    assert result.exit_code == 0
    assert result.files == []
    assert result.result["total_observed_points"] == 1000
    assert result.result["retained_points"] == 1000
    assert result.result["dropped_points"] == 0
    assert "samples" not in result.result
    assert "channels" in result.result
    assert not output_dir.exists()


def test_cancellation_c1_saves_retained_window_and_remains_cancelled(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(capture_monitor, "_capture_waveform", lambda *args: _capture(1, 2.0))
    stop = [False]

    def report(_update):
        stop[0] = True

    output_dir = tmp_path / "cancelled"
    result = capture_monitor.run_capture_monitor(
        _scope(),
        RESOURCE,
        _request(output_dir, count=2),
        stop_requested=lambda: stop[0],
        sample_reporter=report,
    )

    assert result.exit_code == 130
    assert result.result["status"] == "cancelled"
    assert result.result["completed_count"] == 1
    assert (output_dir / "retained_waveforms.csv").exists()
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "cancelled"


def test_cancellation_before_first_capture_creates_no_empty_waveform(tmp_path):
    output_dir = tmp_path / "never"

    result = capture_monitor.run_capture_monitor(
        _scope(),
        RESOURCE,
        _request(output_dir),
        stop_requested=lambda: True,
    )

    assert result.exit_code == 130
    assert result.result["completed_count"] == 0
    assert not output_dir.exists()
