import json
from pathlib import Path

import pytest

from scopes_tool_cli import cli
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.identity import physical_model_for_id
from scopes_tool_core.simulator_backend import SimulatorBackend


def _json_stdout(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_verify_simulate_json_uses_simulator_without_resource(capsys):
    assert cli.main(["identify", "--simulate", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["command"] == "identify"
    assert payload["mode"] == "simulate"
    assert payload["resource"] == "SIM::keysight-dsox4024a::INSTR"
    assert payload["backend"] == "Keysight simulator"
    assert payload["idn"]["model"] == "DSOX4024A"
    assert payload["capabilities"]["analog_channels"] == 4
    assert payload["scpi"]["sent"] == ["*IDN?"]


@pytest.mark.parametrize("mode", ["--dry-run", "--simulate"])
def test_model_argument_requires_canonical_physical_model_id(capsys, mode):
    assert (
        cli.main(
            [
                "identify",
                mode,
                "--json",
                "--model",
                "DSOX4024A",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["idn"] is None
    assert "model ID" in payload["error"]["message"]


@pytest.mark.parametrize("mode", ["--dry-run", "--simulate"])
def test_unregistered_series_shaped_model_id_is_rejected(capsys, mode):
    assert (
        cli.main(
            [
                "identify",
                mode,
                "--json",
                "--model",
                "keysight-dsox4054a",
            ]
        )
        == 1
    )

    assert "model ID" in _json_stdout(capsys)["error"]["message"]


def test_verify_dry_run_json_does_not_open_scope(monkeypatch, capsys):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(cli.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main(["identify", "--dry-run", "--json", "--model", "keysight-dsox4024a"]) == 0

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["mode"] == "dry_run"
    assert payload["scpi"]["planned"] == ["*IDN?"]
    assert payload["scpi"]["sent"] == []
    assert payload["capabilities"] == {
        "series": "4000X",
        "analog_channels": 4,
        "default_waveform_points": 1000,
        "safe_max_waveform_points": 10000,
        "supports_word_format": True,
        "supports_raw_points_mode": False,
        "supports_measurements": True,
        "supports_delay_measurement": True,
        "supports_measure_results_dump": True,
        "supports_screenshot": True,
        "supports_screenshot_format_pack": True,
        "supports_segmented_memory": False,
        "supports_serial_decode": False,
        "reference_waveforms": 2,
        "supports_channel_label": True,
        "channel_label_max_length": 32,
        "supports_display_label": True,
        "supports_annotation": True,
        "supports_annotation_position": True,
        "annotation_slots": 10,
        "supports_indexed_annotation": True,
        "supports_50_ohm_impedance": True,
        "supports_search_basic": True,
        "search_modes": [
            "serial1",
            "serial2",
            "edge",
            "glitch",
            "runt",
            "transition",
            "peak",
        ],
    }


def test_label_and_annotation_dry_run_json_reports_planned_scpi_without_opening(
    monkeypatch, capsys
):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(cli.Oscilloscope, "open", staticmethod(fail_open))

    assert (
        cli.main(
            [
                "channel-label",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--channel",
                "1",
                "--text",
                "Input a",
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"] == [':CHANnel1:LABel "Input a"', ":SYSTem:ERRor?"]
    assert payload["result"]["text"] == "Input a"

    assert cli.main(["display-label", "--dry-run", "--json", "--off"]) == 0
    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"] == [":DISPlay:LABel OFF", ":SYSTem:ERRor?"]
    assert payload["result"]["display_label"] is False

    assert (
        cli.main(
            [
                "annotation",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--slot",
                "2",
                "--on",
                "--text",
                "Note",
                "--x",
                "10",
                "--y",
                "20",
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"] == [
        ":DISPlay:ANNotation2 ON",
        ':DISPlay:ANNotation2:TEXT "Note"',
        ":DISPlay:ANNotation2:X1Position 10",
        ":DISPlay:ANNotation2:Y1Position 20",
        ":SYSTem:ERRor?",
    ]


def test_annotation_validation_errors_do_not_open_backend(monkeypatch, capsys):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("validation failure must not open a scope")

    monkeypatch.setattr(cli.Oscilloscope, "open", staticmethod(fail_open))

    assert (
        cli.main(
            [
                "annotation",
                "--dry-run",
                "--json",
                "--query",
                "--text",
                "bad",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert "--query cannot be combined" in payload["error"]["message"]

    assert (
        cli.main(
            [
                "annotation",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox3024a",
                "--text",
                "Note",
                "--x",
                "10",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert "annotation x is supported only" in payload["error"]["message"]

    assert (
        cli.main(
            [
                "annotation",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--text",
                "x" * 255,
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert "annotation text must be at most 254 characters" in payload["error"]["message"]


def test_annotation_simulate_json_roundtrip_4000x(capsys):
    assert (
        cli.main(
            [
                "annotation",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--slot",
                "2",
                "--on",
                "--text",
                "Note",
                "--color",
                "red",
                "--background",
                "opaque",
                "--x",
                "10",
                "--y",
                "20",
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":DISPlay:ANNotation2 ON",
        ':DISPlay:ANNotation2:TEXT "Note"',
        ":DISPlay:ANNotation2:COLor RED",
        ":DISPlay:ANNotation2:BACKground OPAQ",
        ":DISPlay:ANNotation2:X1Position 10",
        ":DISPlay:ANNotation2:Y1Position 20",
        ":SYSTem:ERRor?",
    ]


def test_annotation_query_simulate_json_3000x_reports_null_position(capsys):
    assert (
        cli.main(
            [
                "annotation",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox3024a",
                "--query",
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["result"]["x"] is None
    assert payload["result"]["y"] is None
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":DISPlay:ANNotation?",
        ":DISPlay:ANNotation:TEXT?",
        ":DISPlay:ANNotation:COLor?",
        ":DISPlay:ANNotation:BACKground?",
        ":SYSTem:ERRor?",
    ]


def test_annotation_query_json_reports_canonical_readback_enums(monkeypatch, capsys):
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox4034a",
        query_overrides={
            ":DISPlay:ANNotation1:COLor?": "WHIT",
            ":DISPlay:ANNotation1:BACKground?": "tran",
        },
    )
    monkeypatch.setattr(cli, "_make_simulator_backend", lambda args, resource: backend)

    assert (
        cli.main(
            [
                "annotation",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--query",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["color"] == "WHITE"
    assert payload["result"]["background"] == "TRAN"


def test_one_shot_live_flag_conflicts_with_simulate_and_dry_run(capsys):
    for mode in ("--simulate", "--dry-run"):
        assert cli.main(["identify", mode, "--live", "--json"]) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert "--live cannot be combined" in payload["error"]["message"]


def test_capture_dry_run_json_reports_files_without_writing(monkeypatch, capsys, tmp_path):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(cli.Oscilloscope, "open", staticmethod(fail_open))
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--dry-run",
                "--json",
                "--channel",
                "1",
                "--csv",
                str(csv_path),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["mode"] == "dry_run"
    assert payload["files"] == [
        {"kind": "csv", "path": str(csv_path)},
        {"kind": "metadata", "path": str(csv_path.with_name("capture_meta.json"))},
    ]
    assert not csv_path.exists()
    assert payload["scpi"]["planned"][-1] == ":SYSTem:ERRor?"


def test_capture_dry_run_wait_trigger_reports_trigger_plan_without_opening(
    monkeypatch, capsys, tmp_path
):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(cli.Oscilloscope, "open", staticmethod(fail_open))
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--dry-run",
                "--json",
                "--channel",
                "1",
                "--csv",
                str(csv_path),
                "--wait-trigger",
                "--trigger-timeout-ms",
                "10",
                "--trigger-poll-interval-ms",
                "5",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"][:2] == [":SINGle", ":OPERegister:CONDition?"]
    assert payload["result"]["trigger"]["timeout_ms"] == 10
    assert payload["result"]["trigger"]["outcome"] == "unknown"
    assert not csv_path.exists()


def test_capture_wait_trigger_invalid_combinations_reject_before_backend(monkeypatch, capsys):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("invalid wait-trigger arguments must not open a scope")

    monkeypatch.setattr(cli.Oscilloscope, "open", staticmethod(fail_open))

    assert (
        cli.main(
            [
                "capture",
                "--dry-run",
                "--json",
                "--channel",
                "1",
                "--wait-trigger",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert "--trigger-timeout-ms is required" in payload["error"]["message"]

    assert (
        cli.main(
            [
                "capture",
                "--dry-run",
                "--json",
                "--channel",
                "1",
                "--force-trigger-on-timeout",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert "--force-trigger-on-timeout requires --wait-trigger" in payload["error"]["message"]


def test_capture_simulate_wait_trigger_json_reports_trigger_metadata(capsys, tmp_path):
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--simulate",
                "--json",
                "--channel",
                "1",
                "--csv",
                str(csv_path),
                "--wait-trigger",
                "--trigger-timeout-ms",
                "1",
                "--trigger-poll-interval-ms",
                "1",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert csv_path.exists()
    assert payload["result"]["trigger"]["outcome"] == "natural"
    assert payload["result"]["trigger"]["raw_values"] == ["8", "0"]
    assert payload["scpi"]["sent"][:4] == [
        "*IDN?",
        ":SINGle",
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
    ]


def test_acquisition_check_dry_run_json_reports_plan_for_target_models(monkeypatch, capsys, tmp_path):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(cli.Oscilloscope, "open", staticmethod(fail_open))

    for model in (
        "keysight-dsox4024a",
        "keysight-dsox4034a",
        "keysight-dsox3024a",
        "keysight-dsox2004a",
    ):
        output_dir = tmp_path / model
        assert (
            cli.main(
                [
                    "acquisition-check",
                    "--dry-run",
                    "--json",
                    "--model",
                    model,
                    "--output-dir",
                    str(output_dir),
                ]
            )
            == 0
        )

        payload = _json_stdout(capsys)
        planned = payload["scpi"]["planned"]
        assert payload["mode"] == "dry_run"
        assert payload["idn"]["model"] == physical_model_for_id(
            model
        ).canonical_model
        assert payload["files"] == [
            {"kind": "report", "path": str(output_dir / "report.json")},
            {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
        ]
        assert planned == [
            "*IDN?",
            ":ACQuire:TYPE?",
            ":ACQuire:COUNt?",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE NORMal",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE AVERage",
            ":ACQuire:COUNt 16",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE?",
            ":ACQuire:COUNt?",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE HRESolution",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE PEAK",
            ":SYSTem:ERRor?",
            ":ACQuire:TYPE?",
            ":ACQuire:COUNt?",
            ":SYSTem:ERRor?",
        ]
        assert not output_dir.exists()


def test_advanced_autoscale_dry_run_json_accepts_2000x_and_3000x(monkeypatch, capsys):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(cli.Oscilloscope, "open", staticmethod(fail_open))

    for model in ("keysight-dsox2004a", "keysight-dsox3024a"):
        assert cli.main(["autoscale", "--dry-run", "--json", "--model", model]) == 0

        payload = _json_stdout(capsys)
        assert payload["capabilities"]["series"] in {"2000X", "3000X"}
        assert payload["scpi"]["planned"] == [":AUToscale", ":SYSTem:ERRor?"]


def test_acquisition_check_simulate_json_writes_report_and_scpi_log(capsys, tmp_path):
    output_dir = tmp_path / "acq-check"

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    report_path = output_dir / "report.json"
    scpi_log_path = output_dir / "scpi.log"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["final_acquisition"] == {"type": "peak", "count": 16}
    assert [step["name"] for step in payload["result"]["steps"]] == [
        "initial-query",
        "set-normal",
        "set-average",
        "post-average-query",
        "set-high-resolution",
        "set-peak",
        "final-query",
    ]
    assert report["status"] == "completed"
    assert report["idn"]["model"] == "DSOX4034A"
    assert report["final_acquisition"] == {"type": "peak", "count": 16}
    assert scpi_log_path.exists()
    assert ":ACQuire:TYPE PEAK" in payload["scpi"]["sent"]


def test_acquisition_check_rejects_nonempty_output_dir(capsys, tmp_path):
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    (output_dir / "old.txt").write_text("old", encoding="utf-8")

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "output directory must be empty" in payload["error"]["message"]


def test_acquisition_check_system_error_keeps_report(capsys, tmp_path):
    output_dir = tmp_path / "system-error"

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--simulate-system-error",
                "-113",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["result"]["status"] == "instrument_error"
    assert report["status"] == "instrument_error"
    assert report["steps"][0]["system_error"]["code"] == -113


def test_acquisition_check_check_only_json_reports_initial_state_and_no_writes(
    capsys, tmp_path
):
    output_dir = tmp_path / "check-only"

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--check-only",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["result"]["check_only"] is True
    assert payload["result"]["termination_reason"] == "check_only"
    assert payload["result"]["initial_acquisition"] == {"type": "normal", "count": 8}
    assert [step["name"] for step in payload["result"]["steps"]] == [
        "initial-query",
    ]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":ACQuire:TYPE?",
        ":ACQuire:COUNt?",
        ":SYSTem:ERRor?",
    ]
    assert report["check_only"] is True
    assert report["termination_reason"] == "check_only"
    assert report["initial_acquisition"] == {"type": "normal", "count": 8}


def test_acquisition_check_stop_on_error_stops_after_first_error(monkeypatch, capsys, tmp_path):
    output_dir = tmp_path / "stop-on-error"
    backend = SimulatorBackend(
        system_errors=['+0,"No error"', '-113,"Undefined header"']
    )
    monkeypatch.setattr(cli, "_make_simulator_backend", lambda args, resource: backend)

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--stop-on-error",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["result"]["stopped_on_error"] is True
    assert payload["result"]["termination_reason"] == "stopped_on_error"
    assert [step["name"] for step in payload["result"]["steps"]] == [
        "initial-query",
        "set-normal",
    ]
    assert report["stopped_on_error"] is True
    assert report["termination_reason"] == "stopped_on_error"


def test_acquisition_check_restore_type_attempts_restore_and_records_result(
    monkeypatch, capsys, tmp_path
):
    output_dir = tmp_path / "restore-type"
    backend = SimulatorBackend()
    monkeypatch.setattr(cli, "_make_simulator_backend", lambda args, resource: backend)

    assert (
        cli.main(
            [
                "acquisition-check",
                "--simulate",
                "--json",
                "--restore-type",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["result"]["restore"]["requested"] is True
    assert payload["result"]["restore"]["attempted"] is True
    assert payload["result"]["restore"]["succeeded"] is True
    assert report["restore"]["requested"] is True
    assert report["restore"]["attempted"] is True
    assert report["restore"]["succeeded"] is True


def test_hardware_report_renders_acquisition_and_smoke_reports(capsys, tmp_path):
    acq_report = tmp_path / "acq.json"
    smoke_report = tmp_path / "smoke.json"
    acq_report.write_text(
        json.dumps(
            {
                "status": "completed",
                "resource": "USB0::FAKE::INSTR",
                "backend": "Keysight simulator",
                "idn": {
                    "model": "DSOX4034A",
                    "firmware": "07.20",
                },
                "average_count": 16,
                "check_only": False,
                "stopped_on_error": False,
                "initial_acquisition": {"type": "normal", "count": 8},
                "restore": {
                    "requested": True,
                    "attempted": True,
                    "succeeded": True,
                    "error": None,
                },
                "termination_reason": "completed",
                "steps": [
                    {
                        "name": "initial-query",
                        "commands": [":ACQuire:TYPE?", ":ACQuire:COUNt?", ":SYSTem:ERRor?"],
                        "system_error": {"is_error": False},
                    }
                ],
                "final_acquisition": {"type": "peak", "count": 16},
                "files": [{"kind": "report", "path": "report.json"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    smoke_report.write_text(
        json.dumps(
            {
                "status": "completed",
                "resource": "USB0::FAKE::INSTR",
                "backend": "Keysight simulator",
                "idn": {
                    "model": "DSOX4034A",
                    "firmware": "07.20",
                },
                "doctor": {},
                "measurements": [],
                "capture": {},
                "screenshot": {},
                "post_check_error": {"code": 0, "message": "No error"},
                "warnings": [],
                "files": [{"kind": "report", "path": "report.json"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    assert cli.main(["hardware-report", str(acq_report), str(smoke_report)]) == 0
    out = capsys.readouterr().out
    assert "Hardware Report" in out
    assert "acquisition-check" in out
    assert "smoke" in out
    assert "Restore Requested: True" in out
    assert "Post Check Error" in out


def test_simulate_json_error_is_single_json_object(capsys):
    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--channel",
                "5",
                "--item",
                "vpp",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["mode"] == "simulate"
    assert "channel 5 is not available" in payload["error"]["message"]


def test_simulate_json_backend_error_keeps_single_json_object(monkeypatch, capsys):
    backend = SimulatorBackend(
        query_failures={
            ":MEASure:VPP? CHANnel1": OscilloscopeError("configured measurement failure")
        }
    )
    monkeypatch.setattr(cli, "SimulatorBackend", lambda **kwargs: backend)

    assert cli.main(["measure", "--simulate", "--json", "--channel", "1", "--item", "vpp"]) == 1

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["mode"] == "simulate"
    assert payload["error"]["message"] == "configured measurement failure"
    assert payload["scpi"]["sent"] == ["*IDN?", ":MEASure:VPP? CHANnel1"]


def test_check_error_simulate_json_can_report_injected_error_queue(monkeypatch, capsys):
    backend = SimulatorBackend(system_errors=['-113,"Undefined header"'])
    monkeypatch.setattr(cli, "SimulatorBackend", lambda **kwargs: backend)

    assert cli.main(["check-error", "--simulate", "--json", "--all", "--max-reads", "3"]) == 1

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["mode"] == "simulate"
    assert payload["result"]["entries"] == [
        {
            "code": -113,
            "is_error": True,
            "message": "Undefined header",
            "raw": '-113,"Undefined header"',
        },
        {
            "code": 0,
            "is_error": False,
            "message": "No error",
            "raw": '+0,"No error"',
        },
    ]
    assert payload["system_error"]["code"] == 0
    assert payload["scpi"]["sent"] == [":SYSTem:ERRor?", ":SYSTem:ERRor?"]



def test_control_simulate_json_reports_action_and_system_error(capsys):
    assert cli.main(["run", "--simulate", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["action"] == "run"
    assert payload["result"]["command"] == ":RUN"
    assert payload["system_error"]["code"] == 0
    assert payload["result"]["human_output"]


def test_channel_timebase_trigger_json_results(capsys):
    assert cli.main(["channel-scale", "--simulate", "--json", "--channel", "1", "--volts-per-division", "0.5"]) == 0
    channel_payload = _json_stdout(capsys)
    assert channel_payload["result"]["operation"] == "set"
    assert channel_payload["result"]["channel"] == 1
    assert channel_payload["result"]["volts_per_division"] == 0.5

    assert cli.main(["timebase-position", "--simulate", "--json", "--seconds", "0.001"]) == 0
    timebase_payload = _json_stdout(capsys)
    assert timebase_payload["result"]["operation"] == "set"
    assert timebase_payload["result"]["position_seconds"] == 0.001

    assert cli.main(["trigger-edge", "--simulate", "--json", "--source-channel", "1", "--level", "0.2", "--slope", "positive"]) == 0
    trigger_payload = _json_stdout(capsys)
    assert trigger_payload["result"]["source_channel"] == 1
    assert trigger_payload["result"]["level_volts"] == 0.2
    assert trigger_payload["result"]["slope"] == "POSitive"


def test_channel_advanced_simulate_json_results(capsys):
    assert (
        cli.main(
            [
                "channel-impedance",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox3024a",
                "--channel",
                "1",
                "--impedance",
                "fifty",
                "--allow-50-ohm",
            ]
        )
        == 0
    )
    impedance_payload = _json_stdout(capsys)
    assert impedance_payload["result"]["operation"] == "set"
    assert impedance_payload["result"]["impedance"] == "fifty"
    assert impedance_payload["scpi"]["sent"] == [
        "*IDN?",
        ":CHANnel1:IMPedance FIFTy",
        ":SYSTem:ERRor?",
    ]

    assert cli.main(["channel-units", "--simulate", "--json", "--channel", "1", "--query"]) == 0
    units_payload = _json_stdout(capsys)
    assert units_payload["result"]["operation"] == "query"
    assert units_payload["result"]["units"] == "volt"
    assert units_payload["scpi"]["sent"] == ["*IDN?", ":CHANnel1:UNITs?", ":SYSTem:ERRor?"]

    assert (
        cli.main(
            [
                "channel-range",
                "--simulate",
                "--json",
                "--channel",
                "1",
                "--volts-full-scale",
                "4",
            ]
        )
        == 0
    )
    range_payload = _json_stdout(capsys)
    assert range_payload["result"]["operation"] == "set"
    assert range_payload["result"]["range_volts"] == 4.0
    assert range_payload["scpi"]["sent"] == ["*IDN?", ":CHANnel1:RANGe 4", ":SYSTem:ERRor?"]


def test_channel_advanced_dry_run_json_reports_planned_scpi_without_opening(
    monkeypatch, capsys
):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(cli.Oscilloscope, "open", staticmethod(fail_open))

    assert (
        cli.main(
            [
                "channel-probe-skew",
                "--dry-run",
                "--json",
                "--channel",
                "1",
                "--seconds",
                "1e-9",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["probe_skew_seconds"] == 1e-9
    assert payload["scpi"]["planned"] == [
        ":CHANnel1:PROBe:SKEW 1e-09",
        ":SYSTem:ERRor?",
    ]
    assert payload["scpi"]["sent"] == []

    assert (
        cli.main(
            [
                "channel-range",
                "--dry-run",
                "--json",
                "--channel",
                "1",
                "--volts-full-scale",
                "4",
            ]
        )
        == 0
    )
    range_payload = _json_stdout(capsys)
    assert range_payload["result"]["range_volts"] == 4.0
    assert range_payload["scpi"]["planned"] == [
        ":CHANnel1:RANGe 4",
        ":SYSTem:ERRor?",
    ]
    assert range_payload["scpi"]["sent"] == []


def test_channel_impedance_json_rejects_fifty_without_allow_before_open(monkeypatch, capsys):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("validation failure must not open a VISA scope")

    monkeypatch.setattr(cli.Oscilloscope, "open", staticmethod(fail_open))

    assert (
        cli.main(
            [
                "channel-impedance",
                "--json",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--impedance",
                "fifty",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "requires --allow-50-ohm" in payload["error"]["message"]
    assert payload["scpi"]["sent"] == []


def test_channel_impedance_simulate_rejects_2000x_fifty_after_idn(capsys):
    assert (
        cli.main(
            [
                "channel-impedance",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
                "--channel",
                "1",
                "--impedance",
                "fifty",
                "--allow-50-ohm",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert (
        "DSO-X 2000X only supports one-meg input impedance; 50 ohm is not supported "
        "by the 2000X channel impedance spec."
    ) in payload["error"]["message"]
    assert payload["scpi"]["sent"] == ["*IDN?"]


def test_cursor_auto_timebase_dry_run_json_plans_queries(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--dry-run",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.01",
                "--auto-timebase",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"][:2] == [":TIMebase:SCALe?", ":TIMebase:POSition?"]
    assert not any(command.startswith(":TIMebase:SCALe ") for command in payload["scpi"]["planned"])
    assert payload["result"]["auto_timebase"]["enabled"] is True
    assert payload["result"]["auto_timebase"]["strategy"] == "scale_only"
    assert payload["result"]["auto_timebase"]["changed"] is None
    assert payload["result"]["auto_timebase"]["target_scale_seconds_per_division"] is None


def test_cursor_auto_timebase_simulate_widens_before_cursor_setup(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.01",
                "--auto-timebase",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    sent = payload["scpi"]["sent"]
    assert sent[1:4] == [
        ":TIMebase:SCALe?",
        ":TIMebase:POSition?",
        ":TIMebase:SCALe 0.0025",
    ]
    assert sent.index(":TIMebase:SCALe 0.0025") < sent.index(":MARKer:MODE MANual")
    assert payload["result"]["auto_timebase"]["changed"] is True
    assert payload["result"]["auto_timebase"]["original_position_seconds"] == 0.0


def test_cursor_auto_vertical_dry_run_json_plans_queries(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--dry-run",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.001",
                "--y1",
                "10",
                "--auto-vertical",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"][:2] == [":CHANnel1:SCALe?", ":CHANnel1:OFFSet?"]
    assert not any(command.startswith(":CHANnel1:SCALe ") for command in payload["scpi"]["planned"])
    assert payload["result"]["auto_vertical"]["enabled"] is True
    assert payload["result"]["auto_vertical"]["strategy"] == "scale_then_offset"
    assert payload["result"]["auto_vertical"]["changed"] is None
    assert payload["result"]["auto_vertical"]["target_scale_volts_per_division"] is None


def test_cursor_auto_vertical_simulate_adjusts_before_cursor_setup(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.001",
                "--y1",
                "20",
                "--y2",
                "21",
                "--auto-vertical",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    sent = payload["scpi"]["sent"]
    assert sent[1:5] == [
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 1",
        ":CHANnel1:OFFSet 20.5",
    ]
    assert sent.index(":CHANnel1:OFFSet 20.5") < sent.index(":MARKer:MODE MANual")
    assert payload["result"]["auto_vertical"]["changed"] is True
    assert payload["result"]["auto_vertical"]["offset_changed"] is True


def test_cursor_auto_timebase_and_auto_vertical_can_combine(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.01",
                "--y1",
                "20",
                "--auto-timebase",
                "--auto-vertical",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    sent = payload["scpi"]["sent"]
    assert sent[1:4] == [
        ":TIMebase:SCALe?",
        ":TIMebase:POSition?",
        ":TIMebase:SCALe 0.0025",
    ]
    assert sent[4:8] == [
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 1",
        ":CHANnel1:OFFSet 20",
    ]
    assert "auto_timebase" in payload["result"]
    assert "auto_vertical" in payload["result"]


def test_cursor_auto_timebase_rejects_query_and_off(capsys):
    assert cli.main(["cursor", "--dry-run", "--json", "--query", "--auto-timebase"]) == 1
    payload = _json_stdout(capsys)
    assert "--auto-timebase is only valid" in payload["error"]["message"]

    assert cli.main(["cursor", "--dry-run", "--json", "--off", "--auto-timebase"]) == 1
    payload = _json_stdout(capsys)
    assert "--auto-timebase is only valid" in payload["error"]["message"]


def test_cursor_auto_vertical_rejects_query_off_and_missing_y(capsys):
    assert cli.main(["cursor", "--dry-run", "--json", "--query", "--auto-vertical"]) == 1
    payload = _json_stdout(capsys)
    assert "--auto-vertical is only valid" in payload["error"]["message"]

    assert cli.main(["cursor", "--dry-run", "--json", "--off", "--auto-vertical"]) == 1
    payload = _json_stdout(capsys)
    assert "--auto-vertical is only valid" in payload["error"]["message"]

    assert (
        cli.main(
            [
                "cursor",
                "--dry-run",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.001",
                "--auto-vertical",
            ]
        )
        == 1
    )
    payload = _json_stdout(capsys)
    assert "--auto-vertical requires --y1 or --y2" in payload["error"]["message"]


def test_cursor_without_auto_timebase_reports_range_diagnostic(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.01",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["system_error"]["code"] == -222
    assert "cursor --auto-timebase" in payload["result"]["diagnostic"]
    assert "cursor --auto-vertical" in payload["result"]["diagnostic"]
    assert ":TIMebase:SCALe?" not in payload["scpi"]["sent"]
    assert not any(command.startswith(":TIMebase:SCALe ") for command in payload["scpi"]["sent"])


def test_cursor_without_auto_vertical_reports_y_range_diagnostic(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.001",
                "--y1",
                "10",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["system_error"]["code"] == -222
    assert "cursor --auto-vertical" in payload["result"]["diagnostic"]


def test_measure_simulate_json_reports_measurement_fields(capsys):
    assert cli.main(["measure", "--simulate", "--json", "--channel", "1", "--item", "vpp"]) == 0

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["item"] == "vpp"
    assert result["channel"] == 1
    assert result["valid"] is True
    assert result["value"] == 0.5
    assert result["unit"] == "V"
    assert result["raw_value"] == "5.000000E-01"
    assert result["parameters"] == {}
    assert payload["system_error"]["is_error"] is False


def test_measure_pair_phase_simulate_json_uses_signal_model(capsys):
    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "phase",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["item"] == "phase"
    assert result["channel"] == 1
    assert result["reference_channel"] == 2
    assert result["valid"] is True
    assert result["value"] == 45.0
    assert result["unit"] == "deg"


def test_measure_pair_delay_simulate_json_on_4000x_uses_signal_model(capsys):
    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "delay",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["item"] == "delay"
    assert result["reference_channel"] == 2
    assert result["valid"] is True
    assert result["value"] == 45.0 / 360.0 / 1000.0
    assert result["unit"] == "s"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":MEASure:DELay? AUTO,CHANnel1,CHANnel2",
        ":SYSTem:ERRor?",
    ]


def test_measure_pair_delay_simulate_json_rejects_non_4000x_before_measurement(capsys):
    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox3024a",
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "delay",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "capability profile" in payload["error"]["message"]
    assert payload["scpi"]["sent"] == ["*IDN?"]


def test_measure_pair_phase_simulate_json_supported_across_target_models(capsys):
    for model in (
        "keysight-dsox4024a",
        "keysight-dsox4034a",
        "keysight-dsox3024a",
        "keysight-dsox2004a",
    ):
        assert (
            cli.main(
                [
                    "measure",
                    "--simulate",
                    "--json",
                    "--model",
                    model,
                    "--source-channel",
                    "1",
                    "--reference-channel",
                    "2",
                    "--item",
                    "phase",
                ]
            )
            == 0
        )
        payload = _json_stdout(capsys)
        assert payload["idn"]["model"] == physical_model_for_id(
            model
        ).canonical_model
        assert payload["result"]["value"] == 45.0


def test_fft_simulate_2000x_uses_unindexed_commands_for_configure_and_query(capsys):
    common = [
        "fft",
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox2004a",
        "--function",
        "1",
    ]
    assert cli.main([*common, "--source-channel", "1"]) == 0
    configured = _json_stdout(capsys)
    assert configured["scpi"]["sent"] == [
        "*IDN?",
        ":FUNCtion:OPERation FFT",
        ":FUNCtion:SOURce1 CHANnel1",
        ":SYSTem:ERRor?",
    ]

    assert cli.main([*common, "--query"]) == 0
    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["operation"] == "query"
    assert result["fft_operation"] == "FFT"
    assert result["function"] == 1
    assert result["source_channel"] == 1
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":FUNCtion:OPERation?",
        ":FUNCtion:SOURce1?",
        ":FUNCtion:FFT:VTYPe?",
        ":FUNCtion:FFT:WINDow?",
        ":FUNCtion:FFT:CENTer?",
        ":FUNCtion:FFT:SPAN?",
        ":FUNCtion:DISPlay?",
        ":SYSTem:ERRor?",
    ]
    assert payload["system_error"]["is_error"] is False


def test_fft_4000x_advanced_dry_run_and_query_shape(capsys):
    assert (
        cli.main(
            [
                "fft",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--function",
                "2",
                "--source-channel",
                "1",
                "--fft-operation",
                "fft-phase",
                "--start-hz",
                "100",
                "--stop-hz",
                "1000",
                "--gate",
                "zoom",
                "--phase-reference",
                "display",
                "--detection-type",
                "positive-peak",
                "--detection-points",
                "2048",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    commands = configured["result"]["commands"]
    assert configured["result"]["fft_operation_canonical"] == "fft-phase"
    assert "fft_operation" not in configured["result"]
    assert commands == [
        ":FUNCtion2:OPERation FFTPhase",
        ":FUNCtion2:SOURce1 CHANnel1",
        ":FUNCtion2:FREQuency:STARt 100",
        ":FUNCtion2:FREQuency:STOP 1000",
        ":FUNCtion2:GATE ZOOM",
        ":FUNCtion2:PHASe:REFerence DISPlay",
        ":FUNCtion2:DETection:TYPE PPOSitive",
        ":FUNCtion2:DETection:POINts 2048",
    ]
    assert all("<" not in command and ">" not in command for command in commands)

    assert (
        cli.main(
            [
                "fft",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--function",
                "1",
                "--query",
            ]
        )
        == 0
    )
    queried = _json_stdout(capsys)["result"]
    assert queried["fft_operation"] == "FFT"
    assert queried["fft_operation_canonical"] == "fft"
    assert queried["phase_reference"] is None
    assert queried["detection_type"] == "off"
    assert queried["detection_points"] == 640
    assert queried["bin_size_hz"] == pytest.approx(1000)
    assert queried["sample_rate_hz"] == pytest.approx(1e9)
    assert queried["resolution_bandwidth_hz"] == pytest.approx(1500)


@pytest.mark.parametrize(
    ("model", "extra"),
    [
        ("keysight-dsox2004a", ["--fft-operation", "fft-phase"]),
        (
            "keysight-dsox4024a",
            ["--center-hz", "1000", "--start-hz", "100"],
        ),
        (
            "keysight-dsox4024a",
            ["--fft-operation", "fft-phase", "--units", "decibel"],
        ),
    ],
)
def test_fft_invalid_or_unsupported_configuration_fails_before_open(
    monkeypatch, capsys, model, extra
):
    monkeypatch.setattr(cli, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "fft",
                "--simulate",
                "--json",
                "--model",
                model,
                "--function",
                "1",
                "--source-channel",
                "1",
                *extra,
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


def test_math_display_simulate_2000x_uses_unindexed_scpi(capsys):
    assert (
        cli.main(
            [
                "math-display",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
                "--function",
                "1",
                "--on",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["operation"] == "set"
    assert result["function"] == 1
    assert result["enabled"] is True
    assert result["command"] == ":FUNCtion:DISPlay ON"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":FUNCtion:DISPlay ON",
        ":SYSTem:ERRor?",
    ]


def test_math_vertical_simulate_4000x_uses_indexed_scpi(capsys):
    assert (
        cli.main(
            [
                "math-vertical",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--function",
                "2",
                "--scale",
                "2",
                "--offset",
                "0.5",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["operation"] == "set"
    assert result["function"] == 2
    assert result["scale"] == 2.0
    assert result["range"] is None
    assert result["offset"] == 0.5
    assert result["commands"] == [
        ":FUNCtion2:SCALe 2",
        ":FUNCtion2:OFFSet 0.5",
    ]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":FUNCtion2:SCALe 2",
        ":FUNCtion2:OFFSet 0.5",
        ":SYSTem:ERRor?",
    ]


def test_math_vertical_query_with_setter_fails_before_open(
    monkeypatch, capsys
):
    monkeypatch.setattr(cli, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-vertical",
                "--simulate",
                "--json",
                "--function",
                "1",
                "--query",
                "--offset",
                "0",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


@pytest.mark.parametrize(
    ("model", "function", "prefix"),
    [
        ("keysight-dsox2004a", "1", ":FUNCtion"),
        ("keysight-dsox3024a", "1", ":FUNCtion"),
        ("keysight-dsox4024a", "2", ":FUNCtion2"),
    ],
)
def test_math_operator_dry_run_uses_model_function_dialect(
    model, function, prefix, capsys
):
    assert (
        cli.main(
            [
                "math-operator",
                "--dry-run",
                "--json",
                "--model",
                model,
                "--function",
                function,
                "--operation",
                "subtract",
                "--source1",
                "channel1",
                "--source2",
                "channel2",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["operation"] == "set"
    assert result["function"] == int(function)
    assert result["math_operation"] == "subtract"
    assert result["source1"] == "channel1"
    assert result["source2"] == "channel2"
    assert result["commands"] == [
        f"{prefix}:OPERation SUBTract",
        f"{prefix}:SOURce1 CHANnel1",
        f"{prefix}:SOURce2 CHANnel2",
    ]
    if model == "keysight-dsox4024a":
        assert all(
            command.startswith(":FUNCtion2") for command in result["commands"]
        )
    else:
        assert all(":FUNCtion1" not in command for command in result["commands"])
    assert payload["scpi"]["planned"] == [
        *result["commands"],
        ":SYSTem:ERRor?",
    ]


def test_math_operator_missing_source2_fails_before_open(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-operator",
                "--simulate",
                "--json",
                "--function",
                "1",
                "--operation",
                "add",
                "--source1",
                "channel1",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


def test_math_transform_dry_run_configures_integrate(capsys):
    assert (
        cli.main(
            [
                "math-transform",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox2004a",
                "--function",
                "1",
                "--operation",
                "integrate",
                "--source",
                "channel1",
                "--input-offset",
                "0",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result == {
        "operation": "set",
        "function": 1,
        "math_operation": "integrate",
        "source": "channel1",
        "input_offset": 0.0,
        "gain": None,
        "linear_offset": None,
        "commands": [
            ":FUNCtion:OPERation INTegrate",
            ":FUNCtion:SOURce1 CHANnel1",
            ":FUNCtion:INTegrate:IOFFset 0",
        ],
    }
    assert payload["scpi"]["planned"] == [
        *result["commands"],
        ":SYSTem:ERRor?",
    ]


def test_math_transform_simulate_configure_query_round_trip(
    monkeypatch, capsys
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(cli, "SimulatorBackend", simulator_backend)
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox4024a",
        "--function",
        "2",
    ]
    assert (
        cli.main(
            [
                "math-transform",
                *common,
                "--operation",
                "linear",
                "--source",
                "channel1",
                "--gain",
                "2",
                "--linear-offset",
                "-1",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion2:OPERation LINear",
        ":FUNCtion2:SOURce1 CHANnel1",
        ":FUNCtion2:LINear:GAIN 2",
        ":FUNCtion2:LINear:OFFSet -1",
    ]

    assert cli.main(["math-transform", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    result = queried["result"]
    assert result["operation"] == "query"
    assert result["function"] == 2
    assert result["math_operation"] == "linear"
    assert result["operation_raw"] == "LINEAR"
    assert result["source"] == "channel1"
    assert result["source_raw"] == "CHANnel1"
    assert result["input_offset"] is None
    assert result["gain"] == 2.0
    assert result["linear_offset"] == -1.0
    assert queried["scpi"]["sent"][-5:] == [
        ":FUNCtion2:OPERation?",
        ":FUNCtion2:SOURce1?",
        ":FUNCtion2:LINear:GAIN?",
        ":FUNCtion2:LINear:OFFSet?",
        ":SYSTem:ERRor?",
    ]


def test_math_transform_invalid_option_fails_before_open(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-transform",
                "--simulate",
                "--json",
                "--function",
                "1",
                "--operation",
                "absolute",
                "--source",
                "channel1",
                "--gain",
                "2",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


def test_math_composite_source_simulate_configure_query_round_trip(
    monkeypatch, capsys
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox2004a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(cli, "SimulatorBackend", simulator_backend)
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox2004a",
    ]
    assert (
        cli.main(
            [
                "math-composite-source",
                *common,
                "--operation",
                "subtract",
                "--source1",
                "channel1",
                "--source2",
                "channel2",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion:GOFT:OPERation SUBTract",
        ":FUNCtion:GOFT:SOURce1 CHANnel1",
        ":FUNCtion:GOFT:SOURce2 CHANnel2",
    ]

    assert cli.main(["math-composite-source", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    result = queried["result"]
    assert result["operation"] == "query"
    assert result["math_operation"] == "subtract"
    assert result["operation_raw"] == "SUBTRACT"
    assert result["source1"] == "channel1"
    assert result["source1_raw"] == "CHANnel1"
    assert result["source2"] == "channel2"
    assert result["source2_raw"] == "CHANnel2"


def test_math_transform_4000x_cascade_dry_run(capsys):
    assert (
        cli.main(
            [
                "math-transform",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--function",
                "2",
                "--operation",
                "absolute",
                "--source",
                "math1",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["source"] == "math1"
    assert payload["result"]["commands"] == [
        ":FUNCtion2:OPERation ABSolute",
        ":FUNCtion2:SOURce1 FUNCtion1",
    ]


def test_math_transform_unsupported_composite_fails_before_open(
    monkeypatch, capsys
):
    monkeypatch.setattr(cli, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-transform",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--function",
                "1",
                "--operation",
                "absolute",
                "--source",
                "composite",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


def test_math_filter_common_simulate_configure_query_round_trip(
    monkeypatch, capsys
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox2004a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(cli, "SimulatorBackend", simulator_backend)
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox2004a",
        "--function",
        "1",
    ]
    assert (
        cli.main(
            [
                "math-filter",
                *common,
                "--operation",
                "high-pass",
                "--source",
                "composite",
                "--cutoff-hz",
                "1000",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion:OPERation HIGHpass",
        ":FUNCtion:SOURce1 GOFT",
        ":FUNCtion:FREQuency:HIGHpass 1000",
    ]

    assert cli.main(["math-filter", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    assert queried["result"]["math_operation"] == "high-pass"
    assert queried["result"]["source"] == "composite"
    assert queried["result"]["cutoff_hz"] == 1000.0
    assert queried["result"]["average_count"] is None
    assert queried["result"]["smooth_points"] is None
    assert queried["scpi"]["sent"][-4:] == [
        ":FUNCtion:OPERation?",
        ":FUNCtion:SOURce1?",
        ":FUNCtion:FREQuency:HIGHpass?",
        ":SYSTem:ERRor?",
    ]


def test_math_filter_advanced_and_clear_simulate(monkeypatch, capsys):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(cli, "SimulatorBackend", simulator_backend)
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox4024a",
        "--function",
        "2",
    ]
    assert (
        cli.main(
            [
                "math-filter",
                *common,
                "--operation",
                "average",
                "--source",
                "math1",
                "--average-count",
                "64",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion2:OPERation AVERage",
        ":FUNCtion2:SOURce1 FUNCtion1",
        ":FUNCtion2:AVERage:COUNt 64",
    ]

    assert cli.main(["math-filter", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    assert queried["result"]["math_operation"] == "average"
    assert queried["result"]["source"] == "math1"
    assert queried["result"]["average_count"] == 64
    assert queried["scpi"]["sent"][-4:] == [
        ":FUNCtion2:OPERation?",
        ":FUNCtion2:SOURce1?",
        ":FUNCtion2:AVERage:COUNt?",
        ":SYSTem:ERRor?",
    ]

    assert cli.main(["math-clear", *common]) == 0
    cleared = _json_stdout(capsys)
    assert cleared["result"]["operation"] == "clear"
    assert cleared["result"]["function"] == 2
    assert cleared["result"]["cleared"] is True
    assert cleared["result"]["command"] == ":FUNCtion2:CLEar"
    assert cleared["scpi"]["sent"][-2:] == [
        ":FUNCtion2:CLEar",
        ":SYSTem:ERRor?",
    ]


def test_math_filter_irrelevant_parameter_fails_before_open(
    monkeypatch, capsys
):
    monkeypatch.setattr(cli, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-filter",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--function",
                "1",
                "--operation",
                "envelope",
                "--source",
                "channel1",
                "--cutoff-hz",
                "1000",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


def test_math_visualization_common_and_trend_simulate_round_trips(
    monkeypatch, capsys
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox2004a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(cli, "SimulatorBackend", simulator_backend)
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox2004a",
        "--function",
        "1",
    ]
    assert (
        cli.main(
            [
                "math-visualization",
                *common,
                "--operation",
                "magnify",
                "--source",
                "composite",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion:OPERation MAGNify",
        ":FUNCtion:SOURce1 GOFT",
    ]

    assert cli.main(["math-visualization", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    assert queried["result"]["math_operation"] == "magnify"
    assert queried["result"]["source"] == "composite"

    assert (
        cli.main(
            [
                "math-visualization",
                *common,
                "--operation",
                "trend",
                "--source",
                "channel1",
                "--source2",
                "channel2",
                "--measurement",
                "vratio",
            ]
        )
        == 0
    )
    _json_stdout(capsys)

    assert cli.main(["math-visualization", *common, "--query"]) == 0
    trend = _json_stdout(capsys)
    assert trend["result"]["math_operation"] == "trend"
    assert trend["result"]["source"] == "channel1"
    assert trend["result"]["source2"] == "channel2"
    assert trend["result"]["measurement"] == "vratio"
    assert trend["result"]["measurement_slot"] is None


def test_math_visualization_4000x_advanced_and_trend_slot_simulate(
    monkeypatch, capsys
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4024a")

    def simulator_backend(**unused):
        backend.closed = False
        return backend

    monkeypatch.setattr(cli, "SimulatorBackend", simulator_backend)
    common = [
        "--simulate",
        "--json",
        "--model",
        "keysight-dsox4024a",
        "--function",
        "2",
    ]
    assert (
        cli.main(
            [
                "math-visualization",
                *common,
                "--operation",
                "max-hold",
                "--source",
                "math1",
            ]
        )
        == 0
    )
    configured = _json_stdout(capsys)
    assert configured["result"]["commands"] == [
        ":FUNCtion2:OPERation MAXHold",
        ":FUNCtion2:SOURce1 FUNCtion1",
    ]

    assert cli.main(["math-visualization", *common, "--query"]) == 0
    queried = _json_stdout(capsys)
    assert queried["result"]["math_operation"] == "max-hold"
    assert queried["result"]["source"] == "math1"

    assert (
        cli.main(
            [
                "math-visualization",
                *common,
                "--operation",
                "trend",
                "--measurement-slot",
                "3",
            ]
        )
        == 0
    )
    trend_configured = _json_stdout(capsys)
    assert trend_configured["result"]["commands"] == [
        ":FUNCtion2:OPERation TRENd",
        ":FUNCtion2:TRENd:NMEasurement MEAS3",
    ]

    assert cli.main(["math-visualization", *common, "--query"]) == 0
    trend = _json_stdout(capsys)
    assert trend["result"]["math_operation"] == "trend"
    assert trend["result"]["source"] is None
    assert trend["result"]["measurement"] is None
    assert trend["result"]["measurement_raw"] == "MEAS3"
    assert trend["result"]["measurement_slot"] == 3


def test_math_visualization_capability_rejection_fails_before_open(
    monkeypatch, capsys
):
    monkeypatch.setattr(cli, "_open_scope", lambda *unused: pytest.fail("opened scope"))

    assert (
        cli.main(
            [
                "math-visualization",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
                "--function",
                "1",
                "--operation",
                "maximum",
                "--source",
                "channel1",
            ]
        )
        == 1
    )
    assert _json_stdout(capsys)["ok"] is False


def test_measure_simulate_json_reports_invalid_sentinel(monkeypatch, capsys):
    backend = SimulatorBackend(invalid_measurement_channels={1})
    monkeypatch.setattr(cli, "SimulatorBackend", lambda **kwargs: backend)

    assert cli.main(["measure", "--simulate", "--json", "--channel", "1", "--item", "vpp"]) == 1

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert payload["ok"] is False
    assert result["valid"] is False
    assert result["value"] is None
    assert result["raw_value"] == "9.9E+37"
    assert result["reason"] == "invalid measurement sentinel"


def test_measure_pair_simulate_json_reports_reference_channel_invalid_sentinel(
    monkeypatch, capsys
):
    backend = SimulatorBackend(invalid_measurement_channels={2})
    monkeypatch.setattr(cli, "_make_simulator_backend", lambda args, resource: backend)

    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "phase",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert payload["ok"] is False
    assert result["valid"] is False
    assert result["value"] is None
    assert result["raw_value"] == "9.9E+37"
    assert result["reason"] == "invalid measurement sentinel"


def test_capture_simulate_json_reports_files_and_summaries(capsys, tmp_path):
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--simulate",
                "--json",
                "--channel",
                "1",
                "--points",
                "5000",
                "--csv",
                str(csv_path),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert payload["files"] == [
        {"kind": "csv", "path": str(csv_path)},
        {"kind": "metadata", "path": str(csv_path.with_name("capture_meta.json"))},
    ]
    assert result["requested_points"] == 5000
    assert result["actual_points"] == 5000
    assert result["captures"][0]["channel"] == 1
    assert "raw_samples" not in result["captures"][0]
    assert result["captures"][0]["preamble"]["points"] == 5000


def test_capture_simulate_json_accepts_signal_override(capsys, tmp_path):
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--simulate",
                "--json",
                "--simulate-signal",
                "CH1:square:1000:2.0:0.5:0:0.01",
                "--channel",
                "1",
                "--points",
                "1000",
                "--csv",
                str(csv_path),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    rows = csv_path.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "time_s,ch1_v"
    voltages = [float(row.split(",")[1]) for row in rows[1:]]
    assert max(voltages) > 1.3
    assert min(voltages) < -0.3


def test_capture_simulate_json_accepts_each_preset(capsys, tmp_path):
    for preset in (
        "noisy-sine",
        "square-with-offset",
        "phase-shifted-pair",
        "dc-invalid-frequency",
        "trigger-misaligned",
    ):
        csv_path = tmp_path / f"{preset}.csv"

        assert (
            cli.main(
                [
                    "capture",
                    "--simulate",
                    "--json",
                    "--simulate-preset",
                    preset,
                    "--channel",
                    "1",
                    "--csv",
                    str(csv_path),
                ]
            )
            == 0
        )

        payload = _json_stdout(capsys)
        assert payload["ok"] is True
        assert csv_path.exists()


def test_simulate_json_scenario_drives_measurement(capsys, tmp_path):
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(
        json.dumps(
            {
                "preset": "phase-shifted-pair",
                "signals": {"CH1": {"phase_deg": 30.0}, "CH2": {"phase_deg": 120.0}},
            }
        ),
        encoding="utf-8",
    )

    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--simulate-scenario",
                str(scenario_path),
                "--source-channel",
                "1",
                "--reference-channel",
                "2",
                "--item",
                "phase",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["value"] == 90.0


def test_simulate_json_layered_preset_scenario_signal_override(capsys, tmp_path):
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(
        json.dumps({"signals": {"CH1": {"shape": "sine", "vpp_v": 1.0}}}),
        encoding="utf-8",
    )

    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--simulate-preset",
                "noisy-sine",
                "--simulate-scenario",
                str(scenario_path),
                "--simulate-signal",
                "CH1:dc:0:0:2.5:0",
                "--channel",
                "1",
                "--item",
                "vavg",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["value"] == 2.5


def test_measure_simulate_json_accepts_signal_override(capsys):
    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--simulate-signal",
                "1:dc:0:0:1.25:0",
                "--channel",
                "1",
                "--item",
                "vavg",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["value"] == 1.25


def test_simulate_json_public_error_injection_options(capsys, tmp_path):
    assert (
        cli.main(
            [
                "check-error",
                "--simulate",
                "--json",
                "--simulate-system-error",
                "-113",
            ]
        )
        == 1
    )
    payload = _json_stdout(capsys)
    assert payload["system_error"]["code"] == -113

    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--simulate-invalid-measurement",
                "CH1",
                "--channel",
                "1",
                "--item",
                "vpp",
            ]
        )
        == 1
    )
    payload = _json_stdout(capsys)
    assert payload["result"]["raw_value"] == "9.9E+37"

    assert (
        cli.main(
            [
                "capture",
                "--simulate",
                "--json",
                "--simulate-display-off",
                "CH1",
                "--channel",
                "1",
                "--csv",
                str(tmp_path / "display-off.csv"),
            ]
        )
        == 1
    )
    payload = _json_stdout(capsys)
    assert "display is off" in payload["error"]["message"]

    assert (
        cli.main(
            [
                "capture",
                "--simulate",
                "--json",
                "--simulate-binary-transfer-failure",
                "--channel",
                "1",
                "--csv",
                str(tmp_path / "binary-failure.csv"),
            ]
        )
        == 1
    )
    payload = _json_stdout(capsys)
    assert payload["error"]["message"] == "simulated binary transfer failure"


def test_simulate_json_scenario_error_injection_is_single_json_object(capsys, tmp_path):
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(
        json.dumps({"errors": {"binary_transfer_failure": True}}),
        encoding="utf-8",
    )

    assert (
        cli.main(
            [
                "capture",
                "--simulate",
                "--json",
                "--simulate-scenario",
                str(scenario_path),
                "--channel",
                "1",
                "--csv",
                str(tmp_path / "scenario-failure.csv"),
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["error"]["message"] == "simulated binary transfer failure"


def test_simulate_signal_json_errors_are_single_json_objects(capsys, tmp_path):
    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--simulate-signal",
                "CH1:triangle:1000:1:0:0",
                "--channel",
                "1",
                "--item",
                "vpp",
            ]
        )
        == 1
    )
    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "invalid --simulate-signal" in payload["error"]["message"]

    assert (
        cli.main(
            [
                "measure",
                "--simulate",
                "--json",
                "--simulate-signal",
                "CH1:sine:1000:1:0:0",
                "--simulate-signal",
                "1:square:1000:1:0:0",
                "--channel",
                "1",
                "--item",
                "vpp",
            ]
        )
        == 1
    )
    payload = _json_stdout(capsys)
    assert "duplicate --simulate-signal for CH1" in payload["error"]["message"]

    assert (
        cli.main(
            [
                "capture",
                "--dry-run",
                "--json",
                "--simulate-signal",
                "CH1:sine:1000:1:0:0",
                "--channel",
                "1",
                "--csv",
                str(tmp_path / "capture.csv"),
            ]
        )
        == 1
    )
    payload = _json_stdout(capsys)
    assert payload["mode"] == "dry_run"
    assert "--simulate-signal can only be used with --simulate" in payload["error"]["message"]

    assert (
        cli.main(
            [
                "measure",
                "--dry-run",
                "--json",
                "--simulate-preset",
                "noisy-sine",
                "--channel",
                "1",
                "--item",
                "vpp",
            ]
        )
        == 1
    )
    payload = _json_stdout(capsys)
    assert "--simulate-preset can only be used with --simulate" in payload["error"]["message"]


def test_capture_simulate_json_multi_channel_word_reflects_distinct_channels(
    capsys, tmp_path
):
    csv_path = tmp_path / "capture.csv"

    assert (
        cli.main(
            [
                "capture",
                "--simulate",
                "--json",
                "--channel",
                "1",
                "--channel",
                "2",
                "--points",
                "1000",
                "--format",
                "word",
                "--csv",
                str(csv_path),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["actual_points"] == {"CH1": 1000, "CH2": 1000}
    assert [item["channel"] for item in result["captures"]] == [1, 2]
    rows = csv_path.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "time_s,ch1_v,ch2_v"
    _, ch1_v, ch2_v = rows[1].split(",")
    assert float(ch1_v) != float(ch2_v)


def test_capture_simulate_json_binary_failure_reports_single_json_object(
    monkeypatch, capsys, tmp_path
):
    backend = SimulatorBackend(
        binary_failures={":WAVeform:DATA?": OscilloscopeError("configured binary failure")}
    )
    monkeypatch.setattr(cli, "_make_simulator_backend", lambda args, resource: backend)

    assert (
        cli.main(
            [
                "capture",
                "--simulate",
                "--json",
                "--channel",
                "1",
                "--csv",
                str(tmp_path / "capture.csv"),
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["error"]["message"] == "configured binary failure"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":WAVeform:SOURce CHANnel1",
        ":WAVeform:FORMat BYTE",
        ":WAVeform:POINts 1000",
        ":WAVeform:PREamble?",
        ":WAVeform:DATA?",
    ]


def test_screenshot_simulate_json_reports_png_metadata(capsys, tmp_path):
    black_path = tmp_path / "screen-black.png"
    white_path = tmp_path / "screen-white.png"

    assert cli.main(["screenshot", "--simulate", "--json", "--output", str(black_path)]) == 0

    black_payload = _json_stdout(capsys)
    black_result = black_payload["result"]
    assert black_payload["files"] == [{"kind": "png", "path": str(black_path)}]
    assert black_result["format"] == "PNG"
    assert black_result["background"] == "black"
    assert black_result["byte_count"] > 1000
    assert black_result["png_path"] == str(black_path)
    assert black_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    assert (
        cli.main(
            [
                "screenshot",
                "--simulate",
                "--json",
                "--background",
                "white",
                "--output",
                str(white_path),
            ]
        )
        == 0
    )

    white_payload = _json_stdout(capsys)
    white_result = white_payload["result"]
    assert white_payload["files"] == [{"kind": "png", "path": str(white_path)}]
    assert white_result["background"] == "white"
    assert white_result["byte_count"] > 1000
    assert white_result["png_path"] == str(white_path)
    assert white_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert black_path.read_bytes() != white_path.read_bytes()


@pytest.mark.parametrize(
    ("format_name", "extension", "query", "signature"),
    [
        ("png", ".png", ":HCOPY:SDUMp:DATA? PNG", b"\x89PNG\r\n\x1a\n"),
        ("bmp", ".bmp", ":HCOPY:SDUMp:DATA? BMP", b"BM"),
        ("bmp8bit", ".bmp", ":HCOPY:SDUMp:DATA? BMP8bit", b"BM"),
    ],
)
def test_screenshot_format_pack_simulate_uses_explicit_screen_dump_query(
    capsys, tmp_path, format_name, extension, query, signature
):
    output_path = tmp_path / f"screen{extension}"

    assert (
        cli.main(
            [
                "screenshot",
                "--simulate",
                "--json",
                "--format",
                format_name,
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert query in payload["scpi"]["sent"]
    assert output_path.read_bytes().startswith(signature)


def test_screenshot_format_pack_appearance_controls_and_query_state(capsys, tmp_path):
    output_path = tmp_path / "appearance.png"
    assert (
        cli.main(
            [
                "screenshot",
                "--simulate",
                "--json",
                "--format",
                "png",
                "--ink-saver",
                "true",
                "--palette",
                "grayscale",
                "--layout",
                "landscape",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["scpi"]["sent"][1:5] == [
        ":HARDcopy:INKSaver ON",
        ":HARDcopy:PALette GRAYscale",
        ":HARDcopy:LAYout LANDscape",
        ":HCOPY:SDUMp:DATA? PNG",
    ]

    assert cli.main(["screenshot", "--simulate", "--json", "--query-hardcopy"]) == 0
    query_payload = _json_stdout(capsys)
    assert query_payload["files"] == []
    assert query_payload["result"]["hardcopy"] == {
        "area": "screen",
        "ink_saver": False,
        "palette": "none",
        "layout": "portrait",
        "format": "png",
        "raw_area": "SCR",
        "raw_ink_saver": "0",
        "raw_palette": "NONE",
        "raw_layout": "PORT",
        "raw_format": "PNG",
    }


def test_screenshot_format_pack_dry_run_plans_without_backend(capsys, tmp_path):
    output_path = tmp_path / "screen.bmp"
    assert (
        cli.main(
            [
                "screenshot",
                "--dry-run",
                "--json",
                "--format",
                "bmp8bit",
                "--palette",
                "color",
                "--layout",
                "portrait",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["scpi"]["sent"] == []
    assert payload["scpi"]["planned"] == [
        ":HARDcopy:INKSaver?",
        ":HARDcopy:INKSaver OFF",
        ":HARDcopy:PALette COLor",
        ":HARDcopy:LAYout PORTrait",
        ":HCOPY:SDUMp:DATA? BMP8bit",
        ":SYSTem:ERRor?",
    ]
    assert not any(
        "restore queried state" in command
        for command in payload["scpi"]["planned"]
    )
    assert payload["result"]["ink_saver_plan"] == {
        "mode": "temporary_background",
        "target": False,
        "restore": "queried_state_if_changed",
    }
    assert not output_path.exists()


def test_screenshot_format_pack_dry_run_explicit_ink_saver_has_no_restore(capsys):
    assert (
        cli.main(
            [
                "screenshot",
                "--dry-run",
                "--json",
                "--format",
                "bmp",
                "--ink-saver",
                "false",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"] == [
        ":HARDcopy:INKSaver OFF",
        ":HCOPY:SDUMp:DATA? BMP",
        ":SYSTem:ERRor?",
    ]
    assert ":HARDcopy:INKSaver?" not in payload["scpi"]["planned"]
    assert not any(
        "restore queried state" in command
        for command in payload["scpi"]["planned"]
    )
    assert payload["result"]["ink_saver_plan"] == {
        "mode": "explicit",
        "target": False,
        "restore": None,
    }


def test_screenshot_help_describes_general_image_output(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])

    assert excinfo.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "capture the current oscilloscope screen to an image file" in help_text
    assert "capture the current oscilloscope screen to a PNG file" not in help_text


def test_model_help_distinguishes_one_shot_planning_from_worker(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["identify", "--help"])

    assert excinfo.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert (
        "canonical physical model ID used for dry-run and simulation planning"
        in help_text
    )
    assert "live execution uses the identity detected from *IDN?" in help_text
    assert "expected live worker model" not in help_text

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["worker", "--help"])

    assert excinfo.value.code == 0
    worker_help_text = " ".join(capsys.readouterr().out.split())
    assert "--model MODEL" in worker_help_text
    assert "dry-run and simulation planning" not in worker_help_text


def test_screenshot_format_pack_rejects_invalid_values_before_backend(monkeypatch):
    opened = False

    def fail_open(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("backend must not open")

    monkeypatch.setattr(cli, "_open_scope", fail_open)
    with pytest.raises(SystemExit):
        cli.main(["screenshot", "--simulate", "--format", "jpeg"])
    assert opened is False


def test_screenshot_query_hardcopy_rejects_capture_options_before_backend(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        cli, "_open_scope", lambda *args, **kwargs: pytest.fail("backend must not open")
    )
    assert (
        cli.main(
            ["screenshot", "--simulate", "--query-hardcopy", "--format", "png"]
        )
        == 1
    )
    assert "cannot be combined" in capsys.readouterr().err


def test_capture_batch_simulate_json_reports_manifest_and_entries(capsys, tmp_path):
    output_dir = tmp_path / "batch"

    assert (
        cli.main(
            [
                "capture-batch",
                "--simulate",
                "--json",
                "--channel",
                "1",
                "--count",
                "2",
                "--points",
                "10000",
                "--format",
                "word",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["status"] == "completed"
    assert result["requested_count"] == 2
    assert result["completed_count"] == 2
    assert result["manifest_path"] == str(output_dir / "manifest.json")
    assert result["scpi_log_path"] == str(output_dir / "scpi.log")
    assert len(result["captures"]) == 2
    assert result["captures"][0]["actual_points"] == {"CH1": 10000}
    assert {item["kind"] for item in payload["files"]} >= {"manifest", "scpi_log", "csv", "metadata"}


def test_capture_batch_simulate_json_stops_after_injected_system_error(
    monkeypatch, capsys, tmp_path
):
    output_dir = tmp_path / "batch"
    backend = SimulatorBackend(
        system_errors=['+0,"No error"', '-113,"Undefined header"']
    )
    monkeypatch.setattr(cli, "_make_simulator_backend", lambda args, resource: backend)

    assert (
        cli.main(
            [
                "capture-batch",
                "--simulate",
                "--json",
                "--channel",
                "1",
                "--count",
                "3",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert payload["ok"] is False
    assert result["status"] == "instrument_error"
    assert result["completed_count"] == 2
    assert len(result["captures"]) == 2
    assert result["captures"][1]["system_error"]["code"] == -113
    assert (output_dir / "waveform_0001.csv").exists()
    assert (output_dir / "waveform_0002.csv").exists()
    assert not (output_dir / "waveform_0003.csv").exists()
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "instrument_error"
    assert len(manifest["captures"]) == 2
    assert ":WAVeform:DATA?" in (output_dir / "scpi.log").read_text(encoding="utf-8")


def test_acquisition_dry_run_json_reports_structured_plan(capsys):
    assert cli.main(["acquisition", "--dry-run", "--json", "--type", "average", "--count", "16"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["scpi_type"] == "AVERage"
    assert payload["result"]["count"] == 16
    assert payload["scpi"]["planned"] == [":ACQuire:TYPE AVERage", ":ACQuire:COUNt 16", ":SYSTem:ERRor?"]


def test_acquisition_simulate_json_query_reports_readback_and_sent_scpi(capsys):
    assert cli.main(["acquisition", "--simulate", "--json", "--query"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["type"] == "normal"
    assert payload["result"]["count"] == 8
    assert payload["result"]["commands"] == [":ACQuire:TYPE?", ":ACQuire:COUNt?"]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":ACQuire:TYPE?",
        ":ACQuire:COUNt?",
        ":SYSTem:ERRor?",
    ]


def test_acquisition_simulate_json_bad_readback_reports_error(monkeypatch, capsys):
    backend = SimulatorBackend(query_overrides={":ACQuire:TYPE?": "bad-type"})
    monkeypatch.setattr(cli, "_make_simulator_backend", lambda args, resource: backend)

    assert cli.main(["acquisition", "--simulate", "--json", "--query"]) == 1

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "Could not parse acquisition type" in payload["error"]["message"]
    assert payload["scpi"]["sent"] == ["*IDN?", ":ACQuire:TYPE?"]


def test_acquisition_simulate_json_normal_reports_sent_scpi(capsys):
    assert cli.main(["acquisition", "--simulate", "--json", "--type", "normal"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["type"] == "normal"
    assert payload["result"]["scpi_type"] == "NORMal"
    assert payload["result"]["count"] is None
    assert payload["result"]["commands"] == [":ACQuire:TYPE NORMal"]
    assert payload["scpi"]["sent"] == ["*IDN?", ":ACQuire:TYPE NORMal", ":SYSTem:ERRor?"]


def test_acquisition_simulate_json_average_count_reports_sent_scpi(capsys):
    assert (
        cli.main(
            [
                "acquisition",
                "--simulate",
                "--json",
                "--type",
                "average",
                "--count",
                "16",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["type"] == "average"
    assert payload["result"]["scpi_type"] == "AVERage"
    assert payload["result"]["count"] == 16
    assert payload["result"]["commands"] == [":ACQuire:TYPE AVERage", ":ACQuire:COUNt 16"]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":ACQuire:TYPE AVERage",
        ":ACQuire:COUNt 16",
        ":SYSTem:ERRor?",
    ]


def test_acquisition_simulate_json_high_resolution_reports_sent_scpi(capsys):
    assert (
        cli.main(
            ["acquisition", "--simulate", "--json", "--type", "high_resolution"]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["type"] == "high_resolution"
    assert payload["result"]["scpi_type"] == "HRESolution"
    assert payload["result"]["count"] is None
    assert payload["result"]["commands"] == [":ACQuire:TYPE HRESolution"]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":ACQuire:TYPE HRESolution",
        ":SYSTem:ERRor?",
    ]


def test_acquisition_simulate_json_peak_reports_sent_scpi(capsys):
    assert cli.main(["acquisition", "--simulate", "--json", "--type", "peak"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["type"] == "peak"
    assert payload["result"]["scpi_type"] == "PEAK"
    assert payload["result"]["count"] is None
    assert payload["result"]["commands"] == [":ACQuire:TYPE PEAK"]
    assert payload["scpi"]["sent"] == ["*IDN?", ":ACQuire:TYPE PEAK", ":SYSTem:ERRor?"]


def test_doctor_dry_run_json_reports_snapshot_plan(capsys):
    assert cli.main(["doctor", "--dry-run", "--json", "--model", "keysight-dsox4034a"]) == 0

    payload = _json_stdout(capsys)
    planned = payload["scpi"]["planned"]
    assert planned[0] == "*IDN?"
    assert ":ACQuire:TYPE?" in planned
    assert ":CHANnel4:BWLimit?" in planned
    assert planned[-1] == ":SYSTem:ERRor?"
    assert payload["result"]["channels"] == []


def test_doctor_simulate_json_reports_four_channels(capsys):
    assert cli.main(["doctor", "--simulate", "--json", "--model", "keysight-dsox4034a"]) == 0

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["backend"] == "Keysight simulator"
    assert result["timeout_ms"] == 2000
    assert result["acquisition"] == {"type": "normal", "count": 8}
    assert len(result["channels"]) == 4
    assert result["channels"][0]["channel"] == 1
    assert result["timebase"]["scale_seconds_per_division"] == 0.001
    assert result["edge_trigger"]["source_channel"] == 1
    assert payload["system_error"]["is_error"] is False


def test_measure_sweep_simulate_json_all_channels(capsys):
    assert cli.main(["measure-sweep", "--simulate", "--json", "--channel", "all"]) == 0

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert result["channels"] == [1, 2, 3, 4]
    assert result["items"] == ["vpp", "frequency", "period", "vrms"]
    assert len(result["measurements"]) == 16
    assert result["summary"] == {
        "valid_count": 16,
        "invalid_count": 0,
        "error_count": 0,
    }


def test_measure_sweep_simulate_json_pair_items_on_4000x(capsys):
    assert (
        cli.main(
            [
                "measure-sweep",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--channel",
                "1",
                "--items",
                "vpp",
                "--pair",
                "1:2",
                "--pair-items",
                "phase,delay",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    measurements = payload["result"]["measurements"]
    assert [item["item"] for item in measurements] == ["vpp", "phase", "delay"]
    assert measurements[1]["reference_channel"] == 2
    assert measurements[2]["valid"] is True
    assert payload["result"]["summary"]["valid_count"] == 3


def test_measure_sweep_invalid_measurement_continues_and_exits_one(capsys):
    assert (
        cli.main(
            [
                "measure-sweep",
                "--simulate",
                "--json",
                "--simulate-invalid-measurement",
                "CH2",
                "--channel",
                "all",
                "--items",
                "vpp",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    result = payload["result"]
    assert len(result["measurements"]) == 4
    assert result["measurements"][1]["channel"] == 2
    assert result["measurements"][1]["valid"] is False
    assert result["measurements"][1]["reason"] == "invalid measurement sentinel"
    assert result["summary"] == {
        "valid_count": 3,
        "invalid_count": 1,
        "error_count": 0,
    }


def test_smoke_dry_run_json_reports_files_without_writing(capsys, tmp_path):
    output_dir = tmp_path / "smoke"

    assert (
        cli.main(
            [
                "smoke",
                "--dry-run",
                "--json",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["status"] == "planned"
    assert payload["files"] == [
        {"kind": "report", "path": str(output_dir / "report.json")},
        {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
        {"kind": "csv", "path": str(output_dir / "capture.csv")},
        {"kind": "metadata", "path": str(output_dir / "capture_meta.json")},
        {"kind": "png", "path": str(output_dir / "screen.png")},
    ]
    assert not output_dir.exists()


def test_smoke_dry_run_json_default_output_dir_does_not_crash(capsys):
    assert cli.main(["smoke", "--dry-run", "--json"]) == 0

    payload = _json_stdout(capsys)
    output_dir = Path("data") / "hardware_smoke" / "DRY-RUN"
    assert payload["result"]["status"] == "planned"
    assert payload["result"]["output_dir"] == str(output_dir)
    assert payload["files"][0] == {
        "kind": "report",
        "path": str(output_dir / "report.json"),
    }


def test_smoke_simulate_json_writes_report_and_artifacts(capsys, tmp_path):
    output_dir = tmp_path / "smoke"

    assert (
        cli.main(["smoke", "--simulate", "--json", "--output-dir", str(output_dir)])
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["status"] == "completed"
    for name in ("report.json", "scpi.log", "capture.csv", "capture_meta.json", "screen.png"):
        assert (output_dir / name).exists()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["doctor"]["acquisition"]["type"] == "normal"
    assert report["capture"]["actual_points"] == 1000
    assert report["screenshot"]["byte_count"] > 1000


def test_smoke_simulate_binary_failure_exits_one_and_keeps_report(capsys, tmp_path):
    output_dir = tmp_path / "smoke"

    assert (
        cli.main(
            [
                "smoke",
                "--simulate",
                "--json",
                "--simulate-binary-transfer-failure",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["result"]["status"] == "error"
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "error"
    assert report["error"] == "simulated binary transfer failure"
