import pytest

from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.operations import (
    CaptureRequest,
    MeasureRequest,
    run_capture,
    run_measure,
)
from scopes_tool_core.measure_until import MeasureUntilRequest, run_measure_until
from scopes_tool_core.triggered_measurement import (
    TriggeredMeasureLoopRequest,
    run_triggered_measure_loop,
)
from scopes_tool_core.operations import CaptureBatchRequest, run_capture_batch
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.workflow import drain_preexisting_system_errors
from scopes_tool_core.sequence import (
    SequenceDocument,
    SequenceStep,
    SequenceRequest,
    run_sequence,
)


def _scope(**kwargs):
    return Oscilloscope(
        SimulatorBackend(
            physical_model_id="keysight-dsox4024a",
            resource_name="SIM::keysight-dsox4024a::INSTR",
            **kwargs,
        )
    )


def test_drain_returns_stale_and_terminates():
    # queue: -420, -221, 0  -> should return 2 stale entries
    with _scope(system_errors=['-420,"Query UNTERMINATED"', '-221,"Settings conflict"', '0,"No error"']) as scope:
        drained = drain_preexisting_system_errors(scope)
        assert len(drained) == 2
        assert drained[0].code == -420
        assert drained[1].code == -221
        # queue now clean, next read should be 0
        assert scope.query_system_error().code == 0


def test_drain_exceeds_max_reads_raises():
    # 30 non-zero without terminating 0 -> should raise
    errors = ['-420,"Query UNTERMINATED"'] * 31
    with _scope(system_errors=errors) as scope:
        with pytest.raises(OscilloscopeError, match="did not reach code 0"):
            drain_preexisting_system_errors(scope, max_reads=30)


def test_capture_batch_stale_drained_then_completed(tmp_path):
    # stale -420 before batch, per-capture should be clean
    with _scope(system_errors=['-420,"Query UNTERMINATED"', '0,"No error"']) as scope:
        result = run_capture_batch(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            CaptureBatchRequest(channels=(1,), points=1000, requested_count=1, interval_seconds=0, output_dir=tmp_path / "batch"),
        )
    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert any("Pre-operation stale system error drained" in line for line in result.human_lines)


def test_measure_stale_drained(tmp_path):
    with _scope(system_errors=['-420,"Query UNTERMINATED"', '0,"No error"']) as scope:
        result = run_measure(scope, "SIM::keysight-dsox4024a::INSTR", MeasureRequest(item="vpp", channel=1))
    assert result.exit_code == 0
    assert any("Pre-operation stale" in line for line in result.human_lines)


def test_capture_stale_drained(tmp_path):
    with _scope(system_errors=['-420,"Query UNTERMINATED"', '0,"No error"']) as scope:
        result = run_capture(scope, "SIM::keysight-dsox4024a::INSTR", CaptureRequest((1,), 1000, csv_path=tmp_path / "c.csv"))
    assert result.exit_code == 0
    assert any("Pre-operation stale" in line for line in result.human_lines)


def test_measure_until_stale_drained(tmp_path):
    with _scope(system_errors=['-420,"Query UNTERMINATED"', '0,"No error"']) as scope:
        result = run_measure_until(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            MeasureUntilRequest(channel=1, item="vpp", operator="gt", threshold=0, timeout_seconds=2, interval_seconds=0, output_dir=tmp_path / "until"),
        )
    # should complete (simulator vpp >0)
    assert result.exit_code in (0, 1)  # may be completed or error but not instrument_error from stale
    # ensure stale was drained human line exists
    assert any("Pre-operation stale" in line for line in result.human_lines)


def test_triggered_measure_loop_stale_drained(tmp_path):
    with _scope(system_errors=['-420,"Query UNTERMINATED"', '0,"No error"']) as scope:
        result = run_triggered_measure_loop(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            TriggeredMeasureLoopRequest(count=1, trigger_timeout_seconds=5, channels=(1,), items="vpp", interval_seconds=0, output_dir=tmp_path / "tloop"),
        )
    assert result.exit_code == 0
    assert any("Pre-operation stale" in line for line in result.human_lines)


def test_operation_true_error_still_fails(tmp_path):
    # No stale, but operation generates error via system_errors after capture
    # For capture, system error after capture is determined by simulator system_errors queue
    # We inject error that will be seen as post-operation error (not drained)
    # drain will consume 0 (clean), then capture's post SYST:ERR? will be -221
    with _scope(system_errors=['0,"No error"', '-221,"Settings conflict"']) as scope:
        result = run_capture(scope, "SIM::keysight-dsox4024a::INSTR", CaptureRequest((1,), 1000, csv_path=tmp_path / "c2.csv"))
    # post-operation error should cause exit_code 1
    assert result.exit_code == 1
    assert result.system_error["code"] == -221


def test_sequence_top_level_only_drains_once(tmp_path):
    # stale before sequence: -420, then step1 measure succeeds with 0, step2 capture's post error would be -221 if not swallowed
    # If nested drain existed, -221 would be drained before step2 and be lost. We verify sequence correctly reports instrument_error for step2
    # Setup: stale -420,0 then sequence steps: measure then capture. We make capture post error -221 by having system_errors queue: -420,0 (stale drain), then 0 for measure step, then -221 for capture step, then 0
    # Simulator system_errors are sequential reads of SYST:ERR? - drain reads 2, measure reads 0, capture reads -221
    with _scope(system_errors=['-420,"Query UNTERMINATED"', '0,"No error"', '0,"No error"', '-221,"Settings conflict"', '0,"No error"']) as scope:
        doc = SequenceDocument(version=1, loop_count=1, steps=(
            SequenceStep(action="measure", parameters={"item": "vpp", "channel": 1}),
            SequenceStep(action="capture", parameters={"channels": [1], "points": 1000}),
        ))
        result = run_sequence(scope, "SIM::keysight-dsox4024a::INSTR", SequenceRequest(document=doc, output_dir=tmp_path / "seq"))
    # capture step should have caused instrument_error status, drain should not have swallowed it
    assert result.result["status"] == "instrument_error"
    assert result.exit_code == 1
