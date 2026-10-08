import json

from scopes_tool_cli import cli, runtime
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.trigger import OPERATION_CONDITION_RUN_MASK
from tests.cli._agent_safe_cli_support import _json_stdout


def test_capture_dry_run_json_reports_files_without_writing(monkeypatch, capsys, tmp_path):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))
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

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))
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

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

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
                "1000",
                "--trigger-poll-interval-ms",
                "1",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert csv_path.exists()
    assert payload["result"]["trigger"]["outcome"] == "natural"
    trigger_values = [
        int(value) for value in payload["result"]["trigger"]["raw_values"]
    ]
    assert len(trigger_values) == 2
    assert trigger_values[0] & OPERATION_CONDITION_RUN_MASK
    assert not trigger_values[1] & OPERATION_CONDITION_RUN_MASK
    assert payload["scpi"]["sent"][:5] == [
        "*IDN?",
        ":SYSTem:ERRor?",
        ":SINGle",
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
    ]


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
    assert result["captures"][0]["vertical_unit"] == "V"
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
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

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
        ":SYSTem:ERRor?",
        ":WAVeform:SOURce CHANnel1",
        ":CHANnel1:UNITs?",
        ":WAVeform:FORMat BYTE",
        ":WAVeform:POINts 1000",
        ":WAVeform:PREamble?",
        ":WAVeform:DATA?",
    ]


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
        system_errors=['+0,"No error"', '+0,"No error"', '-113,"Undefined header"']
    )
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

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
