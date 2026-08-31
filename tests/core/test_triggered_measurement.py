import csv
import json

import pytest

from scopes_tool_core import triggered_measurement
from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.trigger import TriggerWaitResult


RESOURCE = "SIM::keysight-dsox4024a::INSTR"


def _scope(*, invalid_channels=None, system_errors=None):
    return Oscilloscope(
        SimulatorBackend(
            physical_model_id="keysight-dsox4024a",
            invalid_measurement_channels=set(invalid_channels or ()),
            system_errors=list(system_errors or ()),
        )
    )


def _request(output_dir, **values):
    defaults = {
        "count": 2,
        "trigger_timeout_seconds": 1,
        "channels": [1],
        "items": "vpp",
        "pair_items": "phase",
        "output_dir": output_dir,
    }
    defaults.update(values)
    return triggered_measurement.TriggeredMeasureLoopRequest(**defaults)


@pytest.mark.parametrize(
    "values, message",
    [
        ({"count": 0}, "count must be at least 1"),
        ({"count": True}, "count must be an integer"),
        ({"trigger_timeout_seconds": 0}, "must be greater than zero"),
        ({"trigger_timeout_seconds": float("inf")}, "must be a finite number"),
        ({"interval_seconds": -1}, "must be non-negative"),
    ],
)
def test_request_validation_rejects_invalid_finite_loop_values(tmp_path, values, message):
    scope = _scope()
    request = _request(tmp_path / "never", **values)

    with pytest.raises(ParameterValidationError, match=message):
        triggered_measurement.plan_triggered_measure_loop(request, scope.backend._capabilities)


def test_planner_reuses_measurement_channel_and_pair_validation(tmp_path):
    scope = _scope()
    request = _request(
        tmp_path / "planned",
        channels=[1, 2],
        items="vpp,frequency",
        pairs=["1:2"],
        pair_items="phase",
    )

    plan = triggered_measurement.plan_triggered_measure_loop(
        request,
        scope.backend._capabilities,
    )

    assert plan.planned_scpi == (
        ":SINGle",
        ":OPERegister:CONDition?",
        ":MEASure:VPP? CHANnel1",
        ":MEASure:FREQuency? CHANnel1",
        ":MEASure:VPP? CHANnel2",
        ":MEASure:FREQuency? CHANnel2",
        ":MEASure:PHASe? CHANnel1,CHANnel2",
        ":SYSTem:ERRor?",
    )
    assert not (tmp_path / "planned").exists()

    with pytest.raises(ParameterValidationError, match="duplicate waveform channels"):
        triggered_measurement.plan_triggered_measure_loop(
            _request(tmp_path / "duplicate", channels=[1, 1]),
            scope.backend._capabilities,
        )


def test_happy_path_persists_two_completed_cycles_and_reports(tmp_path):
    scope = _scope()
    output_dir = tmp_path / "run"
    samples = []
    progress = []

    result = triggered_measurement.run_triggered_measure_loop(
        scope,
        RESOURCE,
        _request(
            output_dir,
            channels=[1, 2],
            pairs=["1:2"],
            pair_items="phase",
        ),
        sample_reporter=samples.append,
        progress_reporter=progress.append,
    )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert result.result["completed_count"] == 2
    assert scope.backend.history.count(":SINGle") == 2
    assert scope.backend.history.count(":SYSTem:ERRor?") == 3
    assert [item.completed_count for item in progress] == [1, 2]
    assert all(item.total_count == 2 for item in progress)
    assert len(samples) == 2

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["completed_count"] == 2
    assert len(manifest["cycles"]) == 2
    with (output_dir / "measurements.csv").open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == [
        "index",
        "timestamp_iso",
        "elapsed_seconds",
        "trigger_elapsed_seconds",
        "ch1_vpp",
        "ch2_vpp",
        "ch1_ch2_phase",
    ]
    assert len(rows) == 3
    assert (output_dir / "scpi.log").exists()


def test_invalid_measurement_sentinel_is_nan_and_cycle_continues(tmp_path):
    scope = _scope(invalid_channels={2})
    output_dir = tmp_path / "invalid"

    result = triggered_measurement.run_triggered_measure_loop(
        scope,
        RESOURCE,
        _request(output_dir, channels=[1, 2]),
    )

    assert result.exit_code == 0
    assert result.result["completed_count"] == 2
    with (output_dir / "measurements.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["ch2_vpp"] == "NaN"
    assert rows[1]["ch2_vpp"] == "NaN"


def test_trigger_timeout_preserves_previous_cycle_and_stops(monkeypatch, tmp_path):
    outcomes = iter(
        [
            TriggerWaitResult("natural", False, False, 1, 10.0),
            TriggerWaitResult("timeout", False, True, 2, 1000.0),
        ]
    )
    monkeypatch.setattr(
        triggered_measurement,
        "wait_for_current_trigger_completion",
        lambda *args, **kwargs: next(outcomes),
    )
    scope = _scope()
    output_dir = tmp_path / "timeout"

    result = triggered_measurement.run_triggered_measure_loop(
        scope,
        RESOURCE,
        _request(output_dir, count=3),
    )

    assert result.exit_code == 1
    assert result.result["status"] == "error"
    assert result.result["completed_count"] == 1
    assert result.result["error"] == {
        "type": "trigger_timeout",
        "cycle_index": 2,
        "outcome": "timeout",
        "elapsed_seconds": 1.0,
        "message": "trigger wait timed out in cycle 2",
    }
    assert scope.backend.history.count(":SINGle") == 2
    with (output_dir / "measurements.csv").open(encoding="utf-8") as handle:
        assert len(list(csv.reader(handle))) == 2


def test_system_error_fails_before_cycle_persistence(tmp_path):
    scope = _scope(system_errors=['0,"No error"', '-113,"Undefined header"'])
    output_dir = tmp_path / "system-error"

    result = triggered_measurement.run_triggered_measure_loop(
        scope,
        RESOURCE,
        _request(output_dir),
    )

    assert result.exit_code == 1
    assert result.result["status"] == "instrument_error"
    assert result.result["completed_count"] == 0
    assert result.system_error["code"] == -113
    with (output_dir / "measurements.csv").open(encoding="utf-8") as handle:
        assert len(list(csv.reader(handle))) == 1


def test_trigger_wait_cancellation_preserves_empty_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        triggered_measurement,
        "wait_for_current_trigger_completion",
        lambda *args, **kwargs: TriggerWaitResult(
            "cancelled", False, False, 1, 10.0
        ),
    )
    scope = _scope()
    output_dir = tmp_path / "trigger-cancel"

    result = triggered_measurement.run_triggered_measure_loop(
        scope,
        RESOURCE,
        _request(output_dir),
    )

    assert result.exit_code == 130
    assert result.result["status"] == "cancelled"
    assert result.result["completed_count"] == 0
    assert ":MEASure:VPP? CHANnel1" not in scope.backend.history


def test_interval_cancellation_keeps_first_persisted_cycle(monkeypatch, tmp_path):
    monkeypatch.setattr(
        triggered_measurement,
        "interruptible_wait",
        lambda seconds, *, stop_requested=None: False,
    )
    scope = _scope()
    output_dir = tmp_path / "interval-cancel"

    result = triggered_measurement.run_triggered_measure_loop(
        scope,
        RESOURCE,
        _request(output_dir, interval_seconds=10),
    )

    assert result.exit_code == 130
    assert result.result["status"] == "cancelled"
    assert result.result["completed_count"] == 1
    assert scope.backend.history.count(":SINGle") == 1


def test_reporters_run_after_csv_and_manifest_persist(tmp_path):
    scope = _scope()
    output_dir = tmp_path / "reporting"
    observed = []

    def sample_reporter(sample):
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        with (output_dir / "measurements.csv").open(encoding="utf-8") as handle:
            row_count = len(list(csv.reader(handle)))
        observed.append((sample["index"], manifest["completed_count"], row_count))

    result = triggered_measurement.run_triggered_measure_loop(
        scope,
        RESOURCE,
        _request(output_dir, count=1),
        sample_reporter=sample_reporter,
    )

    assert result.exit_code == 0
    assert observed == [(1, 1, 2)]


def test_keyboard_interrupt_uses_shared_interrupted_contract(monkeypatch, tmp_path):
    def _raise_keyboard_interrupt(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        triggered_measurement,
        "wait_for_current_trigger_completion",
        _raise_keyboard_interrupt,
    )
    scope = _scope()
    output_dir = tmp_path / "interrupted"

    result = triggered_measurement.run_triggered_measure_loop(
        scope,
        RESOURCE,
        _request(output_dir),
    )

    assert result.exit_code == 130
    assert result.result["status"] == "interrupted"
    assert result.result["error"] == "KeyboardInterrupt"
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "interrupted"
    assert manifest["error"] == "KeyboardInterrupt"


def test_measurement_query_exception_fails_fast_without_writing_csv_row(monkeypatch, tmp_path):
    scope = _scope()
    output_dir = tmp_path / "query-exception"

    def _failing_query_measurement(channel, item):
        raise triggered_measurement.OscilloscopeError("measurement transport error")

    monkeypatch.setattr(scope, "query_measurement", _failing_query_measurement)

    result = triggered_measurement.run_triggered_measure_loop(
        scope,
        RESOURCE,
        _request(output_dir, count=2),
    )

    assert result.exit_code == 1
    assert result.result["status"] == "error"
    assert result.result["completed_count"] == 0
    assert result.result["error"]["type"] == "OscilloscopeError"
    assert scope.backend.history.count(":SINGle") == 1
    with (output_dir / "measurements.csv").open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 1
    assert rows[0] == [
        "index",
        "timestamp_iso",
        "elapsed_seconds",
        "trigger_elapsed_seconds",
        "ch1_vpp",
    ]

