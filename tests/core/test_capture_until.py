from __future__ import annotations

import json

import pytest

from scopes_tool_core import capture_until
from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.waveform import MultiChannelWaveformCapture
from tests.cli.support import byte_waveform_capture


RESOURCE = "SIM::keysight-dsox4024a::INSTR"


def _scope():
    return Oscilloscope(SimulatorBackend(physical_model_id="keysight-dsox4024a"))


def _request(output_dir, **values):
    defaults = {
        "channels": [1],
        "condition_channel": 1,
        "metric": "max",
        "operator": "gt",
        "threshold": 1.0,
        "timeout_seconds": 10.0,
        "interval_seconds": 0.0,
        "output_dir": output_dir,
    }
    defaults.update(values)
    return capture_until.CaptureUntilRequest(**defaults)


def _single(channel, values):
    raw = tuple(range(len(values)))
    capture = byte_waveform_capture(
        channel, raw_samples=raw, vertical_values=tuple(values)
    )
    return capture


@pytest.mark.parametrize("count", [0, 256])
def test_count_range_rejects_product_boundary(tmp_path, count):
    with pytest.raises(ParameterValidationError, match="between 1 and 255"):
        capture_until.plan_capture_until(
            _request(tmp_path / "never", count=count), _scope().backend._capabilities
        )


def test_condition_channel_must_be_selected(tmp_path):
    with pytest.raises(ParameterValidationError, match="included in selected"):
        capture_until.plan_capture_until(
            _request(tmp_path / "never", channels=[2]),
            _scope().backend._capabilities,
        )


def test_unmatched_capture_is_discarded_and_exact_matching_capture_is_saved(
    monkeypatch, tmp_path
):
    captures = iter((_single(1, (0.0, 0.5)), _single(1, (2.0, 3.0))))
    monkeypatch.setattr(capture_until, "_capture_waveform", lambda *args: next(captures))
    output_dir = tmp_path / "run"

    result = capture_until.run_capture_until(
        _scope(), RESOURCE, _request(output_dir)
    )

    assert result.exit_code == 0
    assert result.result["completed_count"] == 1
    assert result.result["capture_count"] == 2
    assert not (output_dir / "match_000.csv").exists()
    csv_text = (output_dir / "match_001.csv").read_text(encoding="utf-8")
    assert "3.0" in csv_text
    assert "0.5" not in csv_text
    assert len(list(output_dir.glob("match_*_meta.json"))) == 1


def test_multi_channel_match_saves_all_selected_channels(monkeypatch, tmp_path):
    capture = MultiChannelWaveformCapture(
        (_single(1, (2.0, 3.0)), _single(2, (7.0, 8.0)))
    )
    monkeypatch.setattr(capture_until, "_capture_waveform", lambda *args: capture)
    output_dir = tmp_path / "multi"

    result = capture_until.run_capture_until(
        _scope(),
        RESOURCE,
        _request(output_dir, channels=[1, 2], condition_channel=1),
    )

    assert result.exit_code == 0
    header = (output_dir / "match_001.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == "time_s,ch1_v,ch2_v"


def test_count_accumulates_matches_and_timeout_is_not_reset(monkeypatch, tmp_path):
    clock = [0.0]
    captures = iter(
        (
            _single(1, (2.0, 3.0)),
            _single(1, (0.0, 0.5)),
        )
    )

    def capture(*args):
        item = next(captures)
        clock[0] += 0.6
        return item

    monkeypatch.setattr(capture_until, "_capture_waveform", capture)
    monkeypatch.setattr(capture_until.time, "perf_counter", lambda: clock[0])
    output_dir = tmp_path / "timeout"

    result = capture_until.run_capture_until(
        _scope(),
        RESOURCE,
        _request(output_dir, count=2, timeout_seconds=1.0),
    )

    assert result.exit_code == 1
    assert result.result["termination_reason"] == "condition_timeout"
    assert result.result["requested_count"] == 2
    assert result.result["completed_count"] == 1
    assert result.result["capture_count"] == 2
    assert (output_dir / "match_001.csv").exists()
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["termination_reason"] == "condition_timeout"
    assert len(manifest["matches"]) == 1


def test_multiple_matches_complete_and_cancellation_does_not_rollback(
    monkeypatch, tmp_path
):
    capture = _single(1, (2.0, 3.0))
    monkeypatch.setattr(capture_until, "_capture_waveform", lambda *args: capture)
    stop = [False]

    def report(update):
        if update["completed_count"] == 1:
            stop[0] = True

    cancelled_dir = tmp_path / "cancelled"
    cancelled = capture_until.run_capture_until(
        _scope(),
        RESOURCE,
        _request(cancelled_dir, count=2),
        stop_requested=lambda: stop[0],
        sample_reporter=report,
    )
    completed_dir = tmp_path / "completed"
    completed = capture_until.run_capture_until(
        _scope(), RESOURCE, _request(completed_dir, count=2)
    )

    assert cancelled.exit_code == 130
    assert cancelled.result["completed_count"] == 1
    assert (cancelled_dir / "match_001.csv").exists()
    assert completed.exit_code == 0
    assert completed.result["completed_count"] == 2
    assert len(list(completed_dir.glob("match_*.csv"))) == 2
