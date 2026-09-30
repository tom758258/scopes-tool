"""Acceptance tests for Tek workflows using the native driver boundaries."""

import pytest

from scopes_tool_core.operations import run_doctor
from scopes_tool_core.tektronix import TektronixOscilloscope
from scopes_tool_core.tektronix_simulator import TektronixSimulatorBackend
from scopes_tool_core.trigger import TriggerWaitConfig


MODELS = ("tektronix-tbs2074", "tektronix-tds2024b", "tektronix-tbs1052b")


def scope_for(model):
    scope = TektronixOscilloscope(TektronixSimulatorBackend(physical_model_id=model))
    scope.query_idn()
    return scope


@pytest.mark.parametrize("model", MODELS)
def test_doctor_uses_native_status_without_writes(model):
    with scope_for(model) as scope:
        result = run_doctor(scope, "SIM::INSTR")
        assert result.exit_code == 0
        assert result.system_error is None
        assert result.result["post_command_status"]["complete"] is True
        assert not any(":SYST" in cmd.upper() for cmd in scope.backend.history)
        assert all(cmd.endswith("?") for cmd in scope.backend.history)


@pytest.mark.parametrize("model", MODELS)
def test_wait_current_does_not_rearm(model):
    with scope_for(model) as scope:
        scope.single()
        scope.backend.history.clear()
        result = scope.wait_for_current_trigger_completion(TriggerWaitConfig(1000, 1, False))
        assert result.outcome == "natural"
        assert result.arm_command is None
        assert scope.backend.history == ["BUSY?", "BUSY?"]


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("workflow", ("batch", "until", "monitor", "sweep", "log", "measure-until", "triggered-capture", "triggered-measure", "acquisition", "sequence", "cleanup"))
def test_workflow_matrix(model, workflow, tmp_path):
    from scopes_tool_core import operations as op, capture_until, capture_monitor, measure_until, triggered_capture, triggered_measurement, sequence
    from scopes_tool_core.cleanup import execute_cleanup
    with scope_for(model) as scope:
        if workflow == "batch":
            result = op.run_capture_batch(scope, "SIM::INSTR", op.CaptureBatchRequest([1], requested_count=1, output_dir=tmp_path))
        elif workflow == "until":
            result = capture_until.run_capture_until(scope, "SIM::INSTR", capture_until.CaptureUntilRequest([1], 1, "max", "gt", -100, 1, interval_seconds=0, output_dir=tmp_path))
        elif workflow == "monitor":
            result = capture_monitor.run_capture_monitor(scope, "SIM::INSTR", capture_monitor.CaptureMonitorRequest([1], count=1, output_dir=tmp_path))
        elif workflow == "sweep":
            result = op.run_measure_sweep(scope, "SIM::INSTR", op.MeasureSweepRequest([1], items="vpp,frequency"))
        elif workflow == "log":
            result = op.run_measure_log(scope, "SIM::INSTR", op.MeasureLogRequest([1], requested_count=1, interval_seconds=0, output_dir=tmp_path))
        elif workflow == "measure-until":
            result = measure_until.run_measure_until(scope, "SIM::INSTR", measure_until.MeasureUntilRequest(1, "vpp", "gt", -100, 1, interval_seconds=0, output_dir=tmp_path))
        elif workflow == "triggered-capture":
            result = triggered_capture.run_triggered_capture_series(scope, "SIM::INSTR", triggered_capture.TriggeredCaptureSeriesRequest([1], 1, 1, output_dir=tmp_path))
        elif workflow == "triggered-measure":
            result = triggered_measurement.run_triggered_measure_loop(scope, "SIM::INSTR", triggered_measurement.TriggeredMeasureLoopRequest(1, 1, channels=[1], output_dir=tmp_path))
        elif workflow == "acquisition":
            result = op.run_acquisition_check(scope, "SIM::INSTR", op.AcquisitionCheckRequest(output_dir=tmp_path))
            skipped = [step for step in result.result["steps"] if step["status"] == "skipped"]
            assert bool(skipped)
            # No registered Tektronix profile declares high-resolution acquisition.
            assert any(step["type"] == "high_resolution" for step in skipped)
        elif workflow == "sequence":
            doc = sequence.normalize_sequence_document({"version": 1, "steps": [
                {"action": "single", "parameters": {}}, {"action": "wait-trigger", "parameters": {"timeout_seconds": 1}},
                {"action": "measure", "parameters": {"item": "vpp", "channel": 1}},
                {"action": "capture", "parameters": {"channels": [1]}},
                {"action": "cleanup", "parameters": {}}]})
            result = sequence.run_sequence(scope, "SIM::INSTR", sequence.SequenceRequest(doc, output_dir=tmp_path))
            assert scope.backend.history.count("ACQuire:STATE ON") == 1
        else:
            result = execute_cleanup(scope, "safe")
            assert result.final_error_queue_clean is None
            assert not result.final_error.is_error
            assert "clear_display" not in result.actions
            return
        assert result.exit_code == 0, result.result
        assert result.system_error is None
        assert not any(cmd.upper().startswith((":SYST", ":OPER", ":SING", ":ACQ", ":WAV", ":MEAS")) for cmd in scope.backend.history)
        if workflow != "sweep":
            assert result.result["post_command_status"]["complete"] is True
        else:
            assert all(m["system_error"] is None and m["post_command_status"]["complete"] for m in result.result["measurements"])


@pytest.mark.parametrize("code,category,is_error", [(401,"event",False),(402,"event",False),(403,"event",False),(468,"event",False),(100,"error",True),(200,"error",True),(300,"error",True),(410,"error",True),(528,"warning",True),(350,"error",True)])
def test_native_event_categories(code, category, is_error):
    with scope_for(MODELS[0]) as scope:
        scope.backend.inject_event(code, 'A message, with "quotes"')
        status = scope.workflow_status()
        assert status.is_error is is_error
        assert status.events == ({"code": code, "message": 'A message, with "quotes"', "category": category},)
        assert status.complete is (code != 350)
        assert scope.backend.history[-3:] == ["DESE?", "*ESR?", "ALLEv?"]
        assert scope.workflow_status().events == ()


def test_status_mask_fails_without_consuming_or_writing():
    from scopes_tool_core.errors import OscilloscopeError
    with scope_for(MODELS[0]) as scope:
        scope.backend.device_event_enable = 0
        scope.backend.history.clear()
        with pytest.raises(OscilloscopeError, match="DESE"):
            run_doctor(scope, "SIM::INSTR")
        assert scope.backend.history == ["*IDN?", "DESE?"]


def test_doctor_stops_on_preexisting_error():
    with scope_for(MODELS[0]) as scope:
        scope.backend.inject_event(100, "Command error")
        scope.backend.history.clear()
        result = run_doctor(scope, "SIM::INSTR")
        assert result.exit_code == 1
        assert result.system_error is None
        assert result.result["post_command_status"]["events"][0]["code"] == 100
        assert scope.backend.history == ["*IDN?", "DESE?", "*ESR?", "ALLEv?"]


@pytest.mark.parametrize("response", ["", '100', '100,"unterminated', '-1,"invalid"'])
def test_bad_event_response_stops_without_retry(response):
    from scopes_tool_core.errors import OscilloscopeError
    from scopes_tool_core.fake_backend import FakeBackend
    backend = FakeBackend(responses={"DESE?": "255", "*ESR?": "32", "ALLEv?": response})
    with TektronixOscilloscope(backend) as scope:
        with pytest.raises(OscilloscopeError, match="event response"):
            scope.workflow_status()
        assert backend.history == ["DESE?", "*ESR?", "ALLEv?"]


@pytest.mark.parametrize("response", ["invalid", "-1", "256", "1.5"])
def test_bad_sesr_stops_before_events(response):
    from scopes_tool_core.errors import OscilloscopeError
    from scopes_tool_core.fake_backend import FakeBackend
    backend = FakeBackend(responses={"DESE?": "255", "*ESR?": response})
    with TektronixOscilloscope(backend) as scope:
        with pytest.raises(OscilloscopeError):
            scope.workflow_status()
        assert backend.history == ["DESE?", "*ESR?"]


def test_event_cohorts_and_overflow_are_not_reported_clean():
    with scope_for(MODELS[0]) as scope:
        backend = scope.backend
        backend.inject_event(100, "old")
        assert backend.query("*ESR?") == "32"
        backend.inject_event(200, "new")
        assert "old" in backend.query("ALLEv?")
        assert [event["message"] for event in scope.workflow_status().events] == ["new"]
        for _ in range(21):
            backend.inject_event(100, "overflow")
        status = scope.workflow_status()
        assert len(status.events) == 20
        assert not status.complete and status.is_error
        assert status.events[-1]["code"] == 350


@pytest.mark.parametrize("value,events", [(32, '0,"No events"'), (0, '100,"command error"')])
def test_inconsistent_status_cannot_pass(value, events):
    from scopes_tool_core.fake_backend import FakeBackend
    backend = FakeBackend(responses={"DESE?": "255", "*ESR?": str(value), "ALLEv?": events})
    with TektronixOscilloscope(backend) as scope:
        assert scope.workflow_status().is_error


def test_stale_events_are_reported_then_measurement_proceeds():
    from scopes_tool_core.operations import run_measure_sweep, MeasureSweepRequest
    with scope_for(MODELS[0]) as scope:
        scope.backend.inject_event(100, "stale command failure")
        result = run_measure_sweep(scope, "SIM::INSTR", MeasureSweepRequest([1], items="vpp"))
        assert result.exit_code == 0
        assert result.result["post_command_status"]["events"] == []
        assert any("stale command failure" in line for line in result.human_lines)


@pytest.mark.parametrize("workflow", ["sweep", "log"])
def test_unsupported_measurement_request_fails_before_mutation(workflow, tmp_path):
    from scopes_tool_core.operations import run_measure_sweep, run_measure_log, MeasureSweepRequest, MeasureLogRequest
    from scopes_tool_core.errors import OscilloscopeError
    with scope_for(MODELS[1]) as scope:
        scope.backend.history.clear()
        with pytest.raises(OscilloscopeError):
            if workflow == "sweep":
                run_measure_sweep(scope, "SIM::INSTR", MeasureSweepRequest([1], items="vpp", pairs=["1:2"]))
            else:
                run_measure_log(scope, "SIM::INSTR", MeasureLogRequest([1], items="vrms", requested_count=1, output_dir=tmp_path))
        assert scope.backend.history == ["*IDN?"]


def test_bad_checkpoint_does_not_retry_or_continue_sweep(monkeypatch):
    from scopes_tool_core.operations import run_measure_sweep, MeasureSweepRequest
    with scope_for(MODELS[0]) as scope:
        original = scope.backend.query
        reads = 0

        def query(command):
            nonlocal reads
            value = original(command)
            if command == "ALLEv?":
                reads += 1
                if reads == 2:
                    return '100,"unterminated'
            return value

        monkeypatch.setattr(scope.backend, "query", query)
        result = run_measure_sweep(scope, "SIM::INSTR", MeasureSweepRequest([1], items="vpp,frequency"))
        assert result.exit_code == 1
        assert len(result.result["measurements"]) == 1
        assert reads == 2
        assert scope.backend.history[-1] == "ALLEv?"


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("outcome", ["timeout", "cancelled", "forced"])
def test_wait_current_terminal_paths_never_rearm(model, outcome):
    with scope_for(model) as scope:
        scope.single()
        scope.backend.busy_values = (1,)
        scope.backend.history.clear()
        now = [0.0]
        config = TriggerWaitConfig(10, 5, outcome == "forced", clock=lambda: now[0],
                                   sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        result = scope.wait_for_current_trigger_completion(config, stop_requested=lambda: outcome == "cancelled")
        assert result.outcome == outcome
        assert "ACQuire:STATE ON" not in scope.backend.history
        assert ("TRIGger FORCe" in scope.backend.history) is (outcome == "forced")


@pytest.mark.parametrize("model", MODELS[1:])
def test_sequence_validates_later_screenshot_before_single(model, tmp_path):
    from scopes_tool_core.sequence import normalize_sequence_document, run_sequence, SequenceRequest
    from scopes_tool_core.errors import OscilloscopeError
    with scope_for(model) as scope:
        scope.backend.history.clear()
        document = normalize_sequence_document({"version": 1, "steps": [
            {"action": "single", "parameters": {}},
            {"action": "screenshot", "parameters": {}},
        ]})
        with pytest.raises(OscilloscopeError, match="not supported"):
            run_sequence(scope, "SIM::INSTR", SequenceRequest(document, output_dir=tmp_path))
        assert scope.backend.history == ["*IDN?"]


def test_planning_keeps_new_registered_identity(monkeypatch):
    from dataclasses import replace
    from scopes_tool_core import identity
    from scopes_tool_core.capabilities import capabilities_for_model_id
    from scopes_tool_core.tektronix import _PlanningBackend
    original = identity.physical_model_for_id(MODELS[2])
    added = replace(original, model_id="tektronix-test-model", canonical_model="TESTMODEL")
    monkeypatch.setitem(identity._PHYSICAL_MODEL_BY_ID, added.model_id, added)
    backend = _PlanningBackend(capabilities_for_model_id(added.model_id))
    assert backend.physical_model_id == added.model_id
    assert backend.query("*IDN?").split(",")[1] == "TESTMODEL"


def test_planning_rejects_mismatched_profile():
    from dataclasses import replace
    from scopes_tool_core.capabilities import capabilities_for_model_id
    from scopes_tool_core.errors import OscilloscopeError
    from scopes_tool_core.tektronix import _PlanningBackend
    caps = capabilities_for_model_id(MODELS[0])
    with pytest.raises(OscilloscopeError):
        _PlanningBackend(replace(caps, physical_model_id=MODELS[1]))


@pytest.mark.parametrize("checkpoint", [2, 3, 5])
def test_acquisition_incomplete_checkpoint_stops_remaining_steps(checkpoint, monkeypatch, tmp_path):
    from scopes_tool_core.operations import run_acquisition_check, AcquisitionCheckRequest
    with scope_for(MODELS[0]) as scope:
        original = scope.backend.query
        reads = 0

        def query(command):
            nonlocal reads
            value = original(command)
            if command == "ALLEv?":
                reads += 1
                if reads == checkpoint:
                    return '350,"Queue overflow"'
            return value

        monkeypatch.setattr(scope.backend, "query", query)
        result = run_acquisition_check(scope, "SIM::INSTR", AcquisitionCheckRequest(output_dir=tmp_path))
        assert result.exit_code == 1
        assert result.result["stopped_on_error"] is True
        assert result.result["post_command_status"]["complete"] is False
        assert reads == checkpoint
        assert scope.backend.history[-1] == "ALLEv?"


def test_acquisition_restore_checks_native_status(monkeypatch, tmp_path):
    from scopes_tool_core.operations import run_acquisition_check, AcquisitionCheckRequest
    from scopes_tool_core.errors import OscilloscopeError
    with scope_for(MODELS[0]) as scope:
        original = scope.set_acquisition_type
        normal_writes = 0

        def set_type(value):
            nonlocal normal_writes
            original(value)
            if value == "normal":
                normal_writes += 1
                if normal_writes == 2:
                    scope.backend.inject_event(200, "Restore rejected")

        monkeypatch.setattr(scope, "set_acquisition_type", set_type)
        with pytest.raises(OscilloscopeError) as caught:
            run_acquisition_check(scope, "SIM::INSTR", AcquisitionCheckRequest(output_dir=tmp_path, restore_type=True))
        result = caught.value.result
        assert result.exit_code == 1
        assert result.result["restore"]["succeeded"] is False
        assert result.result["restore"]["post_command_status"]["events"][0]["code"] == 200


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("trigger_state", ["non-edge", "line"])
def test_doctor_unavailable_trigger_details_are_read_only(model, trigger_state, monkeypatch):
    with scope_for(model) as scope:
        original = scope.backend.query

        def query(command):
            value = original(command)
            if trigger_state == "non-edge" and command.endswith(":TYPe?"):
                return "PULSE"
            if trigger_state == "line" and command.endswith(":EDGE:SOUrce?"):
                return "LINE" if model == MODELS[0] else "ACLINE"
            return value

        monkeypatch.setattr(scope.backend, "query", query)
        scope.backend.history.clear()
        result = run_doctor(scope, "SIM::INSTR")
        assert result.exit_code == 0
        trigger = result.result["edge_trigger"]
        assert trigger["level_volts"] is None
        assert trigger["unavailable_reason"] == (
            "current_trigger_is_not_edge" if trigger_state == "non-edge"
            else "current_source_is_not_an_analog_channel"
        )
        assert all(command.endswith("?") for command in scope.backend.history)
        assert not any(":LEVel" in command for command in scope.backend.history)
