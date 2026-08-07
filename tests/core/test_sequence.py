import json

import pytest

from scopes_tool_core import sequence
from scopes_tool_core.cleanup import CleanupResult
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.status import SystemErrorEntry


RESOURCE = "SIM::keysight-dsox4024a::INSTR"


def _document(*steps, loop_count=1):
    return sequence.normalize_sequence_document(
        {"version": 1, "loop_count": loop_count, "steps": list(steps)}
    )


def _step(action, **parameters):
    return {"action": action, "parameters": parameters}


def _scope(model="keysight-dsox4024a"):
    return Oscilloscope(SimulatorBackend(physical_model_id=model))


def test_normalize_sequence_document_applies_defaults_and_normalizes_steps():
    document = sequence.normalize_sequence_document(
        {
            "version": 1,
            "steps": [
                _step("wait", seconds=0),
                _step("capture", channels=[1]),
                _step("cleanup"),
            ],
        }
    )

    assert document.version == 1
    assert document.loop_count == 1
    assert document.steps[0].parameters == {"seconds": 0.0}
    assert document.steps[1].parameters == {
        "channels": [1],
        "points": 1000,
        "waveform_format": "byte",
        "allow_time_axis_tolerance": False,
    }
    assert document.steps[2].parameters == {"profile": "minimal"}


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"version": True, "steps": [_step("single")]}, "version must be an integer"),
        ({"version": 1, "loop_count": False, "steps": [_step("single")]}, "loop_count must be an integer"),
        ({"version": 1, "steps": [{"action": "single", "parameters": {}, "extra": 1}]}, "unknown field"),
        ({"version": 1, "steps": [_step("unknown")]}, "action must be one of"),
        ({"version": 1, "steps": [_step("capture", channels=[True])]}, "channel must be an integer"),
        ({"version": 1, "steps": [_step("wait", seconds=1, extra=True)]}, "unknown field"),
    ],
)
def test_sequence_document_rejects_unknown_fields_actions_and_boolean_integers(
    payload, message
):
    with pytest.raises(ParameterValidationError, match=message):
        sequence.normalize_sequence_document(payload)


def test_sequence_loader_rejects_non_standard_json_numbers(tmp_path):
    path = tmp_path / "sequence.json"
    path.write_text(
        '{"version":1,"steps":[{"action":"wait","parameters":{"seconds":NaN}}]}',
        encoding="utf-8",
    )

    with pytest.raises(ParameterValidationError, match="non-standard JSON number"):
        sequence.load_sequence_document(path)


def test_sequence_executes_steps_in_loop_order_and_reports_progress(
    monkeypatch, tmp_path
):
    waits = []
    progress = []
    monkeypatch.setattr(
        sequence,
        "interruptible_wait",
        lambda seconds, *, stop_requested=None: waits.append(seconds) or True,
    )
    document = _document(
        _step("wait", seconds=1),
        _step("wait", seconds=2),
        loop_count=2,
    )

    result = sequence.run_sequence(
        _scope(),
        RESOURCE,
        sequence.SequenceRequest(document, output_dir=tmp_path / "run"),
        progress_reporter=progress.append,
    )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert waits == [1.0, 2.0, 1.0, 2.0]
    assert [item.completed_count for item in progress] == [1, 2, 3, 4]
    assert all(item.total_count == 4 for item in progress)
    assert result.result["completed_loops"] == 2
    assert result.result["completed_step_executions"] == 4


def test_sequence_wait_cancellation_does_not_execute_next_step(monkeypatch, tmp_path):
    calls = []

    def fake_wait(seconds, *, stop_requested=None):
        calls.append(("wait", seconds))
        return False

    monkeypatch.setattr(sequence, "interruptible_wait", fake_wait)
    document = _document(_step("wait", seconds=30), _step("single"))

    result = sequence.run_sequence(
        _scope(),
        RESOURCE,
        sequence.SequenceRequest(document, output_dir=tmp_path / "cancelled"),
    )

    assert result.exit_code == 130
    assert result.result["status"] == "cancelled"
    assert result.result["completed_step_executions"] == 0
    assert calls == [("wait", 30.0)]
    manifest = json.loads((tmp_path / "cancelled" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "cancelled"
    assert manifest["executions"] == []


def test_sequence_single_then_wait_trigger_arms_only_once(tmp_path):
    scope = _scope()
    result = sequence.run_sequence(
        scope,
        RESOURCE,
        sequence.SequenceRequest(
            _document(
                _step("single"),
                _step("wait-trigger", timeout_seconds=1),
            ),
            output_dir=tmp_path / "trigger",
        ),
    )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert scope.backend.history.count(":SINGle") == 1
    assert result.result["steps"][1]["last_result"]["trigger"]["arm_command"] is None


def test_sequence_failure_is_fail_fast_and_reports_failed_step(monkeypatch, tmp_path):
    actions = []

    def fake_execute(*args, **kwargs):
        step = args[6]
        actions.append(step.action)
        if step.action == "single":
            raise OscilloscopeError("single failed")
        return sequence._StepOutcome({"seconds": 0.0})

    monkeypatch.setattr(sequence, "_execute_step", fake_execute)
    document = _document(
        _step("wait", seconds=0),
        _step("single"),
        _step("cleanup"),
    )

    result = sequence.run_sequence(
        _scope(),
        RESOURCE,
        sequence.SequenceRequest(document, output_dir=tmp_path / "failed"),
    )

    assert result.exit_code == 1
    assert result.result["status"] == "error"
    assert actions == ["wait", "single"]
    assert result.result["failed_step"] == {
        "loop_index": 1,
        "step_index": 2,
        "action": "single",
        "error": {"type": "OscilloscopeError", "message": "single failed"},
    }


def test_sequence_completion_precedes_late_cancellation(tmp_path):
    cancelled = False

    def stop_requested():
        return cancelled

    def progress_reporter(_progress):
        nonlocal cancelled
        cancelled = True

    result = sequence.run_sequence(
        _scope(),
        RESOURCE,
        sequence.SequenceRequest(
            _document(_step("wait", seconds=0)),
            output_dir=tmp_path / "completed",
        ),
        stop_requested=stop_requested,
        progress_reporter=progress_reporter,
    )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert result.result["error"] is None


def test_sequence_capture_reuses_core_capture_without_overwriting_across_loops(tmp_path):
    output_dir = tmp_path / "captures"
    result = sequence.run_sequence(
        _scope(),
        RESOURCE,
        sequence.SequenceRequest(
            _document(_step("capture", channels=[1]), loop_count=2),
            output_dir=output_dir,
        ),
    )

    assert result.exit_code == 0
    first = output_dir / "loop_0001" / "step_0001_capture"
    second = output_dir / "loop_0002" / "step_0001_capture"
    for directory in (first, second):
        assert (directory / "waveform.csv").exists()
        assert (directory / "waveform_meta.json").exists()
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert len(manifest["executions"]) == 2


def test_sequence_cleanup_calls_existing_execute_cleanup(monkeypatch, tmp_path):
    calls = []
    final_error = SystemErrorEntry(0, "No error", '+0,"No error"')

    def fake_cleanup(scope, profile):
        calls.append((scope, profile))
        return CleanupResult(profile, ("existing",), (), final_error)

    monkeypatch.setattr(sequence, "execute_cleanup", fake_cleanup)
    scope = _scope()
    result = sequence.run_sequence(
        scope,
        RESOURCE,
        sequence.SequenceRequest(
            _document(_step("cleanup", profile="safe")),
            output_dir=tmp_path / "cleanup",
        ),
    )

    assert result.exit_code == 0
    assert calls == [(scope, "safe")]


def test_detected_capability_validation_happens_before_output_creation(tmp_path):
    output_dir = tmp_path / "unsupported"
    document = _document(
        _step(
            "measure",
            item="delay",
            source_channel=1,
            reference_channel=2,
        )
    )

    with pytest.raises(ParameterValidationError):
        sequence.run_sequence(
            _scope("keysight-dsox2004a"),
            "SIM::keysight-dsox2004a::INSTR",
            sequence.SequenceRequest(document, output_dir=output_dir),
        )

    assert not output_dir.exists()


def test_direct_core_construction_validation_fails_closed_before_hardware_or_files(tmp_path):
    scope = _scope()
    output_dir = tmp_path / "never_created"

    doc_zero_loop = sequence.SequenceDocument(
        version=1,
        loop_count=0,
        steps=(sequence.SequenceStep("single", {}),),
    )
    with pytest.raises(ParameterValidationError, match="loop_count must be at least 1"):
        sequence.plan_sequence(sequence.SequenceRequest(doc_zero_loop), scope.capabilities)

    with pytest.raises(ParameterValidationError, match="loop_count must be at least 1"):
        sequence.run_sequence(
            scope,
            RESOURCE,
            sequence.SequenceRequest(doc_zero_loop, output_dir=output_dir),
        )

    doc_bad_action = sequence.SequenceDocument(
        version=1,
        loop_count=1,
        steps=(sequence.SequenceStep("invalid-action", {}),),
    )
    with pytest.raises(ParameterValidationError, match="action must be one of"):
        sequence.plan_sequence(sequence.SequenceRequest(doc_bad_action), scope.capabilities)

    with pytest.raises(ParameterValidationError, match="action must be one of"):
        sequence.run_sequence(
            scope,
            RESOURCE,
            sequence.SequenceRequest(doc_bad_action, output_dir=output_dir),
        )

    assert not output_dir.exists()
    assert scope.backend.history.count("*IDN?") == 0


def test_screenshot_dry_run_planned_scpi_does_not_include_conditional_inksaver_write():
    scope = _scope()
    scope.query_idn()
    doc = _document(_step("screenshot", background="white"))
    plan = sequence.plan_sequence(sequence.SequenceRequest(doc), scope.capabilities)

    assert plan.planned_scpi == (
        ":HARDcopy:INKSaver?",
        ":DISPlay:DATA? PNG, COLor",
        ":SYSTem:ERRor?",
    )
    assert ":HARDcopy:INKSaver ON" not in plan.planned_scpi
    assert ":HARDcopy:INKSaver OFF" not in plan.planned_scpi


def test_pre_start_cancellation_performs_zero_hardware_io_and_creates_no_directory(tmp_path):
    scope = _scope()
    output_dir = tmp_path / "cancelled_pre_start"
    doc = _document(_step("single"))

    result = sequence.run_sequence(
        scope,
        RESOURCE,
        sequence.SequenceRequest(doc, output_dir=output_dir),
        stop_requested=lambda: True,
    )

    assert result.exit_code == 130
    assert result.result["status"] == "cancelled"
    assert result.result["output_dir"] is None
    assert result.result["manifest_path"] is None
    assert result.result["scpi_log_path"] is None
    assert result.result["files"] == []
    assert not output_dir.exists()
    assert scope.backend.history == []


def test_wait_trigger_cancellation_does_not_query_system_error_or_execute_next_step(
    monkeypatch, tmp_path
):
    scope = _scope()
    calls = []

    def fake_wait(*args, **kwargs):
        calls.append("wait_for_trigger")
        from scopes_tool_core.trigger import TriggerWaitResult
        return TriggerWaitResult("cancelled", False, False, 1, 100.0)

    monkeypatch.setattr(sequence, "wait_for_current_trigger_completion", fake_wait)

    doc = _document(
        _step("wait-trigger", timeout_seconds=1),
        _step("single"),
    )

    result = sequence.run_sequence(
        scope,
        RESOURCE,
        sequence.SequenceRequest(doc, output_dir=tmp_path / "trigger_cancelled"),
    )

    assert result.exit_code == 130
    assert result.result["status"] == "cancelled"
    assert calls == ["wait_for_trigger"]
    assert "query::SYSTem:ERRor?" not in calls
    assert scope.backend.history.count(":SINGle") == 0


def test_capture_artifact_failure_preserves_existing_csv_partial_result(
    monkeypatch, tmp_path
):
    scope = _scope()
    output_dir = tmp_path / "partial_artifact"
    progress = []

    doc = _document(
        _step("capture", channels=[1]),
        _step("single"),
    )

    def failing_run_capture(scp, res, req):
        req.csv_path.parent.mkdir(parents=True, exist_ok=True)
        req.csv_path.write_text("time,ch1\n0,1\n", encoding="utf-8")
        raise OscilloscopeError("mock metadata write error")

    monkeypatch.setattr(sequence, "run_capture", failing_run_capture)

    result = sequence.run_sequence(
        scope,
        RESOURCE,
        sequence.SequenceRequest(doc, output_dir=output_dir),
        progress_reporter=progress.append,
    )

    assert result.exit_code == 1
    assert result.result["status"] == "error"
    assert result.result["completed_step_executions"] == 0
    assert progress == []

    file_paths = [item["path"] for item in result.files]
    assert any("waveform.csv" in p for p in file_paths)
    assert not any("waveform_meta.json" in p for p in file_paths)
    assert scope.backend.history.count(":SINGle") == 0
