from __future__ import annotations

import csv
import json

import pytest

from scopes_tool_core import measure_until
from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.measurements import MeasurementResult
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend


RESOURCE = "SIM::keysight-dsox4024a::INSTR"


def _scope(*, system_errors=None):
    return Oscilloscope(
        SimulatorBackend(
            physical_model_id="keysight-dsox4024a",
            system_errors=list(system_errors or ()),
        )
    )


def _request(output_dir, **values):
    defaults = {
        "channel": 1,
        "item": "vpp",
        "operator": "gt",
        "threshold": 3.3,
        "timeout_seconds": 10,
        "interval_seconds": 0,
        "output_dir": output_dir,
    }
    defaults.update(values)
    return measure_until.MeasureUntilRequest(**defaults)


def _measurement(value, *, valid=True):
    return MeasurementResult(
        item="vpp",
        channel=1,
        value=value if valid else None,
        raw_value=str(value) if valid else "9.9E+37",
        valid=valid,
        unit="V",
        reason=None if valid else "invalid measurement sentinel",
    )


@pytest.mark.parametrize(
    "values, message",
    [
        ({"channel": [1]}, "channel must be an integer"),
        ({"channel": 5}, "not available on this scope"),
        ({"item": "phase"}, "non-parameterized single-channel"),
        ({"item": "y_at_x"}, "non-parameterized single-channel"),
        ({"operator": "eq"}, "operator must be gt, gte, lt, or lte"),
        ({"threshold": float("inf")}, "threshold must be a finite number"),
        ({"timeout_seconds": 0}, "timeout seconds must be greater than zero"),
        ({"interval_seconds": -1}, "interval seconds must be non-negative"),
    ],
)
def test_request_validation_rejects_invalid_values(tmp_path, values, message):
    scope = _scope()

    with pytest.raises(ParameterValidationError, match=message):
        measure_until.plan_measure_until(
            _request(tmp_path / "never", **values),
            scope.backend._capabilities,
        )


def test_first_sample_match_is_committed_before_reporters_and_beats_late_stop(
    monkeypatch, tmp_path
):
    perf_values = iter((0.0, 0.5, 1.1, 1.2))
    monkeypatch.setattr(measure_until.time, "perf_counter", lambda: next(perf_values))
    scope = _scope()
    output_dir = tmp_path / "first-match"
    stopped = False
    observed = []
    progress = []

    monkeypatch.setattr(scope, "query_measurement", lambda channel, item: _measurement(4.0))

    def report_sample(sample):
        nonlocal stopped
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        with (output_dir / "measurements.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        observed.append((sample, manifest, rows))
        stopped = True

    result = measure_until.run_measure_until(
        scope,
        RESOURCE,
        _request(output_dir, timeout_seconds=1),
        stop_requested=lambda: stopped,
        sample_reporter=report_sample,
        progress_reporter=progress.append,
    )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert result.result["termination_reason"] == "condition_met"
    assert result.result["matched"] is True
    assert result.result["matched_sample"]["index"] == 1
    assert result.result["matched_sample"]["value"] == 4.0
    assert result.result["matched_sample"]["elapsed_seconds"] > 1.0
    assert observed[0][1]["completed_count"] == 1
    assert observed[0][1]["matched"] is True
    assert observed[0][2][0]["matched"] == "true"
    assert progress[0].completed_count == 1
    assert progress[0].total_count is None
    assert (output_dir / "scpi.log").exists()


def test_non_match_then_match_updates_compact_summary(monkeypatch, tmp_path):
    readings = iter((_measurement(3.0), _measurement(3.3)))
    scope = _scope()
    monkeypatch.setattr(scope, "query_measurement", lambda channel, item: next(readings))
    output_dir = tmp_path / "later-match"

    result = measure_until.run_measure_until(
        scope,
        RESOURCE,
        _request(output_dir, operator="gte"),
    )

    assert result.exit_code == 0
    assert result.result["completed_count"] == 2
    assert result.result["matched_sample"]["index"] == 2
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["completed_count"] == 2
    assert "samples" not in manifest
    with (output_dir / "measurements.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["matched"] for row in rows] == ["false", "true"]


def test_invalid_measurement_is_nan_non_match_and_continues(monkeypatch, tmp_path):
    readings = iter((_measurement(None, valid=False), _measurement(4.0)))
    scope = _scope()
    monkeypatch.setattr(scope, "query_measurement", lambda channel, item: next(readings))
    output_dir = tmp_path / "invalid"

    result = measure_until.run_measure_until(
        scope,
        RESOURCE,
        _request(output_dir),
    )

    assert result.exit_code == 0
    assert result.result["completed_count"] == 2
    with (output_dir / "measurements.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["value"] == "NaN"
    assert rows[0]["matched"] == "false"
    assert rows[1]["matched"] == "true"


def test_timeout_is_failure_and_preserves_committed_samples(monkeypatch, tmp_path):
    perf_values = iter((0.0, 0.9, 1.1, 1.1, 1.1))
    monkeypatch.setattr(measure_until.time, "perf_counter", lambda: next(perf_values))
    scope = _scope()
    monkeypatch.setattr(scope, "query_measurement", lambda channel, item: _measurement(1.0))
    output_dir = tmp_path / "timeout"

    result = measure_until.run_measure_until(
        scope,
        RESOURCE,
        _request(output_dir, timeout_seconds=1),
    )

    assert result.exit_code == 1
    assert result.result["status"] == "error"
    assert result.result["termination_reason"] == "condition_timeout"
    assert result.result["error"]["type"] == "condition_timeout"
    assert result.result["completed_count"] == 1
    assert result.result["matched"] is False
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["completed_count"] == 1
    assert manifest["termination_reason"] == "condition_timeout"


def test_system_error_stops_before_sample_commit(tmp_path):
    scope = _scope(system_errors=['-113,"Undefined header"'])
    output_dir = tmp_path / "system-error"

    result = measure_until.run_measure_until(
        scope,
        RESOURCE,
        _request(output_dir, threshold=0),
    )

    assert result.exit_code == 1
    assert result.result["status"] == "instrument_error"
    assert result.result["termination_reason"] is None
    assert result.result["completed_count"] == 0
    with (output_dir / "measurements.csv").open(encoding="utf-8") as handle:
        assert len(list(csv.reader(handle))) == 1


def test_interval_cancellation_preserves_committed_sample(monkeypatch, tmp_path):
    monkeypatch.setattr(
        measure_until,
        "interruptible_wait",
        lambda seconds, *, stop_requested=None: False,
    )
    scope = _scope()
    monkeypatch.setattr(scope, "query_measurement", lambda channel, item: _measurement(1.0))
    output_dir = tmp_path / "cancelled"

    result = measure_until.run_measure_until(
        scope,
        RESOURCE,
        _request(output_dir, interval_seconds=10),
    )

    assert result.exit_code == 130
    assert result.result["status"] == "cancelled"
    assert result.result["termination_reason"] is None
    assert result.result["completed_count"] == 1


def test_planner_uses_one_iteration_without_hardware_or_files(monkeypatch, tmp_path):
    scope = _scope()
    output_dir = tmp_path / "planned"
    monkeypatch.setattr(
        Oscilloscope,
        "open",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("opened"))),
    )

    plan = measure_until.plan_measure_until(
        _request(output_dir, timeout_seconds=600, interval_seconds=1),
        scope.backend._capabilities,
    )

    assert plan.planned_scpi == (
        ":MEASure:VPP? CHANnel1",
        ":SYSTem:ERRor?",
    )
    assert plan.result["timeout_seconds"] == 600
    assert plan.result["interval_seconds"] == 1
    assert plan.result["completed_count"] == 0
    assert not output_dir.exists()
