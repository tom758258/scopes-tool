import json

import pytest

from scopes_tool_core.capabilities import capabilities_for_model
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.operations import (
    AcquisitionCheckRequest,
    CaptureRequest,
    MeasureLogRequest,
    MeasureRequest,
    MeasureSweepRequest,
    SmokeRequest,
    _prepare_output_dir,
    _trigger_wait_classifier_profile,
    run_acquisition_check,
    run_capture,
    run_doctor,
    run_measure_log,
    run_measure,
    run_measure_sweep,
    run_smoke,
)
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.trigger import TriggerWaitConfig


class _StepClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _scope(model_id="keysight-dsox4024a", **kwargs):
    return Oscilloscope(
        SimulatorBackend(
            physical_model_id=model_id,
            resource_name=f"SIM::{model_id}::INSTR",
            **kwargs,
        )
    )


class _ProfileScope:
    def __init__(self, *, backend_name, model):
        self.backend = type("Backend", (), {"backend": backend_name})()
        self.capabilities = capabilities_for_model(model)


def test_run_capture_writes_files_and_checks_system_error(tmp_path):
    with _scope() as scope:
        result = run_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            CaptureRequest((1,), 1000, csv_path=tmp_path / "capture.csv"),
        )

    assert result.exit_code == 0
    assert (tmp_path / "capture.csv").exists()
    assert result.files[1]["kind"] == "metadata"
    assert result.result["captures"][0]["vertical_unit"] == "V"
    assert scope.backend.history[-1] == ":SYSTem:ERRor?"


def test_run_capture_preserves_mixed_channel_units_in_outputs(tmp_path):
    with _scope(channel_units={1: "VOLT", 2: "AMP"}) as scope:
        result = run_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            CaptureRequest((1, 2), 1000, csv_path=tmp_path / "capture.csv"),
        )

    assert [item["vertical_unit"] for item in result.result["captures"]] == ["V", "A"]
    assert (tmp_path / "capture.csv").read_text(encoding="utf-8").splitlines()[0] == (
        "time_s,ch1_v,ch2_a"
    )
    metadata = json.loads((tmp_path / "capture_meta.json").read_text(encoding="utf-8"))
    assert [item["vertical_unit"] for item in metadata["channels"]] == ["V", "A"]
    assert "vertical_unit" not in metadata


def test_run_capture_wait_trigger_natural_path_writes_files(tmp_path):
    clock = _StepClock()
    with _scope(operation_condition_values=[56, 56, 48]) as scope:
        result = run_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            CaptureRequest(
                (1,),
                1000,
                csv_path=tmp_path / "capture.csv",
                trigger_wait=TriggerWaitConfig(
                    10, poll_interval_ms=1, clock=clock, sleep=clock.sleep
                ),
            ),
        )

    assert result.exit_code == 0
    assert (tmp_path / "capture.csv").exists()
    assert result.result["trigger"]["outcome"] == "natural"
    assert result.result["trigger"]["raw_values"] == ["56", "56", "48"]
    assert ":WAVeform:DATA?" in scope.backend.history


def test_run_capture_wait_trigger_timeout_writes_no_artifacts(tmp_path):
    clock = _StepClock()
    with _scope(operation_condition_values=[56]) as scope:
        result = run_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            CaptureRequest(
                (1,),
                1000,
                csv_path=tmp_path / "capture.csv",
                trigger_wait=TriggerWaitConfig(
                    2, poll_interval_ms=1, clock=clock, sleep=clock.sleep
                ),
            ),
        )

    assert result.exit_code == 1
    assert result.files == []
    assert not (tmp_path / "capture.csv").exists()
    assert result.result["trigger"]["outcome"] == "timeout"
    assert ":WAVeform:DATA?" not in scope.backend.history
    assert scope.backend.history[-1] == ":SYSTem:ERRor?"


def test_run_capture_wait_trigger_force_after_timeout_then_captures(tmp_path):
    clock = _StepClock()
    with _scope(operation_condition_values=[56], force_operation_condition_values=[56, 48]) as scope:
        result = run_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            CaptureRequest(
                (1,),
                1000,
                csv_path=tmp_path / "capture.csv",
                trigger_wait=TriggerWaitConfig(
                    2,
                    poll_interval_ms=1,
                    force_on_timeout=True,
                    clock=clock,
                    sleep=clock.sleep,
                ),
            ),
        )

    assert result.exit_code == 0
    assert (tmp_path / "capture.csv").exists()
    assert result.result["trigger"]["outcome"] == "forced"
    assert result.result["trigger"]["forced"] is True
    assert ":TRIGger:FORCe" in scope.backend.history


def test_run_capture_wait_trigger_unknown_writes_no_artifacts(tmp_path):
    clock = _StepClock()
    with _scope(query_failures={":OPERegister:CONDition?": RuntimeError("configured query failure")}) as scope:
        result = run_capture(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            CaptureRequest(
                (1,),
                1000,
                csv_path=tmp_path / "capture.csv",
                trigger_wait=TriggerWaitConfig(
                    10, poll_interval_ms=1, clock=clock, sleep=clock.sleep
                ),
            ),
        )

    assert result.exit_code == 1
    assert result.files == []
    assert not (tmp_path / "capture.csv").exists()
    assert result.result["trigger"]["outcome"] == "unknown"
    assert result.result["trigger"]["condition_values"] == []
    assert "configured query failure" in result.result["trigger"]["error"]
    assert ":WAVeform:DATA?" not in scope.backend.history


def test_trigger_wait_classifier_profile_uses_x_series_run_bit_for_live_models():
    assert _trigger_wait_classifier_profile(
        _ProfileScope(backend_name="fake live", model="DSOX2004A")
    ) == "2000x"
    assert _trigger_wait_classifier_profile(
        _ProfileScope(backend_name="fake live", model="DSOX3024A")
    ) == "3000x"
    assert _trigger_wait_classifier_profile(
        _ProfileScope(backend_name="fake live", model="DSOX4024A")
    ) == "4000x"


def test_run_doctor_returns_channel_snapshot():
    with _scope("keysight-dsox4034a") as scope:
        result = run_doctor(scope, "SIM::keysight-dsox4034a::INSTR")

    assert result.exit_code == 0
    assert len(result.result["channels"]) == 4
    assert result.system_error["is_error"] is False


def test_run_measure_invalid_sentinel_exits_one():
    with _scope(invalid_measurement_channels=(1,)) as scope:
        result = run_measure(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            MeasureRequest(item="vpp", channel=1),
        )

    assert result.exit_code == 1
    assert result.result["valid"] is False


def test_run_measure_sweep_summary_counts_invalid():
    with _scope(invalid_measurement_channels=(2,)) as scope:
        result = run_measure_sweep(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            MeasureSweepRequest(channels=(1, 2), items="vpp"),
        )

    assert result.exit_code == 1
    assert result.result["summary"] == {
        "valid_count": 1,
        "invalid_count": 1,
        "error_count": 0,
    }


def test_run_measure_log_returns_structured_result_without_console_output(tmp_path, capsys):
    with _scope() as scope:
        result = run_measure_log(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            MeasureLogRequest(
                channels=(1,),
                items="vpp",
                pair_items="phase",
                interval_seconds=0,
                requested_count=1,
                output_dir=tmp_path / "measure-log",
            ),
        )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert result.result["completed_rows"] == 1
    assert result.result["csv_path"] == str(tmp_path / "measure-log" / "measurements.csv")
    assert result.files[1]["kind"] == "manifest"
    assert result.system_error["is_error"] is False
    assert result.human_lines
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_run_measure_log_preserves_instrument_error_result(tmp_path):
    with _scope(system_errors=['0,"No error"', '-113,"Undefined header"']) as scope:
        result = run_measure_log(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            MeasureLogRequest(
                channels=(1,),
                items="vpp",
                pair_items="phase",
                interval_seconds=0,
                requested_count=2,
                output_dir=tmp_path / "measure-log-error",
                stop_on_error=True,
            ),
        )

    assert result.exit_code == 1
    assert result.result["status"] == "instrument_error"
    assert result.result["completed_rows"] == 1
    assert result.system_error["code"] == -113


def test_run_measure_log_no_save_failure_preserves_completed_progress(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "not-created"
    with _scope() as scope:
        original_query_system_error = scope.query_system_error
        query_count = 0

        def fail_after_first_completed_row():
            nonlocal query_count
            query_count += 1
            if query_count == 3:
                raise OscilloscopeError("measurement backend failure")
            return original_query_system_error()

        monkeypatch.setattr(scope, "query_system_error", fail_after_first_completed_row)
        with pytest.raises(OscilloscopeError, match="measurement backend failure") as exc_info:
            run_measure_log(
                scope,
                "SIM::keysight-dsox4024a::INSTR",
                MeasureLogRequest(
                    channels=(1,),
                    items="vpp",
                    pair_items="phase",
                    interval_seconds=0,
                    requested_count=3,
                    output_dir=output_dir,
                    save_results=False,
                ),
            )

    result = exc_info.value.result
    assert result.result["completed_rows"] == 1
    assert result.result["last_measurement"]["index"] == 1
    assert result.files == []
    assert not output_dir.exists()


def test_run_measure_log_preserves_invalid_measurement_and_duration_limit(tmp_path):
    with _scope(invalid_measurement_channels=(1,)) as scope:
        result = run_measure_log(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            MeasureLogRequest(
                channels=(1,),
                items="vpp",
                pair_items="phase",
                interval_seconds=0.5,
                requested_duration_seconds=0.01,
                output_dir=tmp_path / "measure-log-duration",
            ),
        )

    assert result.exit_code == 0
    assert result.result["status"] == "completed"
    assert result.result["completed_rows"] == 1
    csv_text = (tmp_path / "measure-log-duration" / "measurements.csv").read_text(
        encoding="utf-8"
    )
    assert "NaN" in csv_text


def test_run_measure_log_preserves_interrupt_result(tmp_path, monkeypatch):
    with _scope() as scope:
        monkeypatch.setattr(
            scope,
            "query_measurement",
            lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
        )
        result = run_measure_log(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            MeasureLogRequest(
                channels=(1,),
                items="vpp",
                pair_items="phase",
                interval_seconds=0,
                requested_count=1,
                output_dir=tmp_path / "measure-log-interrupt",
            ),
        )

    assert result.exit_code == 130
    assert result.result["status"] == "interrupted"
    assert result.result["error"] == "KeyboardInterrupt"
    assert result.files[0]["kind"] == "csv"
    assert result.human_lines


def test_run_smoke_writes_report(tmp_path):
    with _scope() as scope:
        result = run_smoke(
            scope,
            "SIM::keysight-dsox4024a::INSTR",
            SmokeRequest(output_dir=tmp_path / "smoke"),
        )

    report = json.loads((tmp_path / "smoke" / "report.json").read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert report["schema_version"] == 2
    assert report["status"] == "completed"
    assert report["capture"]["captures"][0]["vertical_unit"] == "V"
    assert (tmp_path / "smoke" / "capture.csv").read_text(encoding="utf-8").splitlines()[0] == (
        "time_s,ch1_v"
    )
    metadata = json.loads((tmp_path / "smoke" / "capture_meta.json").read_text(encoding="utf-8"))
    assert metadata["vertical_unit"] == "V"
    assert result.files[0]["kind"] == "report"


def test_run_acquisition_check_check_only_and_restore(tmp_path):
    with _scope("keysight-dsox4034a") as scope:
        check_only = run_acquisition_check(
            scope,
            "SIM::keysight-dsox4034a::INSTR",
            AcquisitionCheckRequest(output_dir=tmp_path / "check", check_only=True),
        )

    assert check_only.result["termination_reason"] == "check_only"
    assert [step["name"] for step in check_only.result["steps"]] == ["initial-query"]

    with _scope("keysight-dsox4034a") as scope:
        restored = run_acquisition_check(
            scope,
            "SIM::keysight-dsox4034a::INSTR",
            AcquisitionCheckRequest(output_dir=tmp_path / "restore", restore_type=True),
        )

    assert restored.result["restore"]["requested"] is True
    assert restored.result["restore"]["attempted"] is True


def test_prepare_output_dir_rejects_request_json_only_directory(tmp_path):
    output_dir = tmp_path / "request-json-output"
    output_dir.mkdir()
    (output_dir / "request.json").write_text("{}", encoding="utf-8")

    with pytest.raises(OscilloscopeError, match="must be empty"):
        _prepare_output_dir(output_dir)
