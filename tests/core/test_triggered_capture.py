import json

import pytest

from scopes_tool_core import triggered_capture
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.trigger import TriggerWaitResult


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
        "channels": [1],
        "count": 2,
        "trigger_timeout_seconds": 1,
        "output_dir": output_dir,
    }
    defaults.update(values)
    return triggered_capture.TriggeredCaptureSeriesRequest(**defaults)


@pytest.mark.parametrize(
    "values, message",
    [
        ({"count": 0}, "count must be at least 1"),
        ({"count": True}, "count must be an integer"),
        ({"trigger_timeout_seconds": 0}, "must be greater than zero"),
        ({"trigger_timeout_seconds": float("inf")}, "must be a finite number"),
        ({"interval_seconds": -1}, "must be non-negative"),
        ({"waveform_format": "ascii"}, "format must be byte or word"),
        ({"channels": [1, 1]}, "duplicate waveform channels"),
        ({"points": 123}, "supports only these point counts"),
    ],
)
def test_request_validation_rejects_invalid_values(tmp_path, values, message):
    scope = _scope()

    with pytest.raises(ParameterValidationError, match=message):
        triggered_capture.plan_triggered_capture_series(
            _request(tmp_path / "never", **values),
            scope.backend._capabilities,
        )


def test_planner_uses_one_representative_cycle_without_writing_files(tmp_path):
    scope = _scope()
    output_dir = tmp_path / "planned"

    plan = triggered_capture.plan_triggered_capture_series(
        _request(output_dir, channels=[1, 2], count=10),
        scope.backend._capabilities,
    )

    assert plan.planned_scpi.count(":SINGle") == 1
    assert plan.planned_scpi.count(":OPERegister:CONDition?") == 1
    assert plan.planned_scpi.count(":SYSTem:ERRor?") == 1
    assert plan.planned_scpi.count(":WAVeform:DATA?") == 2
    assert plan.result["requested_count"] == 10
    assert plan.result["completed_count"] == 0
    assert not output_dir.exists()


def test_happy_path_commits_two_cycles_before_reporting_and_preserves_completion(
    tmp_path,
):
    scope = _scope()
    output_dir = tmp_path / "run"
    observed = []
    progress = []
    late_stop = [False]

    def sample_reporter(sample):
        manifest = json.loads(
            (output_dir / "manifest.json").read_text(encoding="utf-8")
        )
        csv_path = output_dir / sample["csv"]
        metadata_path = output_dir / sample["metadata"]
        observed.append(
            (
                sample["index"],
                manifest["completed_count"],
                csv_path.exists(),
                metadata_path.exists(),
            )
        )
        if sample["index"] == 2:
            late_stop[0] = True

    result = triggered_capture.run_triggered_capture_series(
        scope,
        RESOURCE,
        _request(output_dir, channels=[1, 2]),
        stop_requested=lambda: late_stop[0],
        sample_reporter=sample_reporter,
        progress_reporter=progress.append,
    )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert result.result["completed_count"] == 2
    assert scope.backend.history.count(":SINGle") == 2
    assert scope.backend.history.count(":SYSTem:ERRor?") == 2
    assert observed == [(1, 1, True, True), (2, 2, True, True)]
    assert [item.completed_count for item in progress] == [1, 2]
    assert all(item.total_count == 2 for item in progress)
    assert (output_dir / "waveform_0001.csv").exists()
    assert (output_dir / "waveform_0001_meta.json").exists()
    assert (output_dir / "waveform_0002.csv").exists()
    assert (output_dir / "waveform_0002_meta.json").exists()
    assert (output_dir / "scpi.log").exists()
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["completed_count"] == 2
    assert len(manifest["cycles"]) == 2


def test_later_trigger_timeout_preserves_previous_cycle_and_stops(monkeypatch, tmp_path):
    outcomes = iter(
        [
            TriggerWaitResult("natural", False, False, 1, 10.0),
            TriggerWaitResult("timeout", False, True, 2, 1000.0),
        ]
    )
    monkeypatch.setattr(
        triggered_capture,
        "wait_for_current_trigger_completion",
        lambda *args, **kwargs: next(outcomes),
    )
    scope = _scope()
    output_dir = tmp_path / "timeout"

    result = triggered_capture.run_triggered_capture_series(
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
    assert ":TRIGger:FORCe" not in scope.backend.history
    assert not (output_dir / "waveform_0002.csv").exists()


def test_trigger_wait_cancellation_does_not_capture_cycle(monkeypatch, tmp_path):
    monkeypatch.setattr(
        triggered_capture,
        "wait_for_current_trigger_completion",
        lambda *args, **kwargs: TriggerWaitResult(
            "cancelled", False, False, 1, 10.0
        ),
    )
    scope = _scope()
    output_dir = tmp_path / "trigger-cancel"

    result = triggered_capture.run_triggered_capture_series(
        scope,
        RESOURCE,
        _request(output_dir),
    )

    assert result.exit_code == 130
    assert result.result["status"] == "cancelled"
    assert result.result["completed_count"] == 0
    assert not (output_dir / "waveform_0001.csv").exists()


def test_interval_cancellation_keeps_committed_cycle(monkeypatch, tmp_path):
    monkeypatch.setattr(
        triggered_capture,
        "interruptible_wait",
        lambda seconds, *, stop_requested=None: False,
    )
    scope = _scope()
    output_dir = tmp_path / "interval-cancel"

    result = triggered_capture.run_triggered_capture_series(
        scope,
        RESOURCE,
        _request(output_dir, interval_seconds=10),
    )

    assert result.exit_code == 130
    assert result.result["status"] == "cancelled"
    assert result.result["completed_count"] == 1
    assert scope.backend.history.count(":SINGle") == 1


def test_post_capture_system_error_keeps_diagnostics_without_committing_cycle(tmp_path):
    scope = _scope(system_errors=['-113,"Undefined header"'])
    output_dir = tmp_path / "system-error"
    samples = []

    result = triggered_capture.run_triggered_capture_series(
        scope,
        RESOURCE,
        _request(output_dir),
        sample_reporter=samples.append,
    )

    assert result.exit_code == 1
    assert result.result["status"] == "instrument_error"
    assert result.result["completed_count"] == 0
    assert result.system_error["code"] == -113
    assert samples == []
    assert (output_dir / "waveform_0001.csv").exists()
    assert (output_dir / "waveform_0001_meta.json").exists()
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["completed_count"] == 0
    assert manifest["cycles"] == []


def test_waveform_failure_does_not_commit_cycle(monkeypatch, tmp_path):
    monkeypatch.setattr(
        triggered_capture,
        "_capture_waveform",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OscilloscopeError("waveform transport error")
        ),
    )
    scope = _scope()

    result = triggered_capture.run_triggered_capture_series(
        scope,
        RESOURCE,
        _request(tmp_path / "waveform-error"),
    )

    assert result.exit_code == 1
    assert result.result["status"] == "error"
    assert result.result["completed_count"] == 0
    assert result.result["error"]["type"] == "OscilloscopeError"


def test_keyboard_interrupt_uses_interrupted_terminal_status(monkeypatch, tmp_path):
    monkeypatch.setattr(
        triggered_capture,
        "wait_for_current_trigger_completion",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    scope = _scope()
    output_dir = tmp_path / "interrupted"

    result = triggered_capture.run_triggered_capture_series(
        scope,
        RESOURCE,
        _request(output_dir),
    )

    assert result.exit_code == 130
    assert result.result["status"] == "interrupted"
    assert result.result["error"] == "KeyboardInterrupt"
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "interrupted"

