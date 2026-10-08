import json

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.simulator_backend import SimulatorBackend
from tests.cli._agent_safe_cli_support import _json_stdout


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

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

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
        "supports_area_measurement": True,
        "supports_measure_statistics": True,
        "supports_demo": True,
        "demo_functions": [
            "am",
            "arinc",
            "burst",
            "can",
            "can-lin",
            "clock",
            "coupling",
            "edge-then-edge",
            "flexray",
            "fm-burst",
            "glitch",
            "harmonics",
            "i2c",
            "i2s",
            "lf-sine",
            "lin",
            "mil",
            "mil2",
            "mso",
            "noisy",
            "phase",
            "rf-burst",
            "ringing",
            "runt",
            "setup-hold",
            "sine",
            "single",
            "spi",
            "transition",
            "uart",
        ],
        "math_function_count": 4,
        "supports_math_goft": False,
        "supports_math_cascade": True,
        "math_filter_operations": [
            "average",
            "envelope",
            "high-pass",
            "low-pass",
            "smooth",
        ],
        "math_visualization_operations": [
            "magnify",
            "max-hold",
            "maximum",
            "min-hold",
            "minimum",
            "peak",
            "trend",
        ],
        "supports_advanced_fft": True,
        "supports_wgen": True,
        "wgen_scpi_root": ":WGEN1",
        "supports_screenshot": True,
        "screenshot_formats": ["png", "bmp", "bmp8bit"],
        "supports_screenshot_hardcopy_controls": True,
        "supports_segmented_memory": True,
        "segmented_max_segments": 1000,
        "supports_segmented_waveform_all": True,
        "supports_serial_decode": True,
        "serial_bus_count": 2,
        "serial_modes": [
            "a429",
            "can",
            "cxpi",
            "flexray",
            "i2s",
            "i2c",
            "lin",
            "m1553",
            "manchester",
            "nrz",
            "sent",
            "spi",
            "uart",
            "usb",
            "usb-pd",
        ],
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
        "supports_search_event_navigation": True,
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


def test_one_shot_live_flag_conflicts_with_simulate_and_dry_run(capsys):
    for mode in ("--simulate", "--dry-run"):
        assert cli.main(["identify", mode, "--live", "--json"]) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert "--live cannot be combined" in payload["error"]["message"]


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
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

    assert cli.main(["measure", "--simulate", "--json", "--channel", "1", "--item", "vpp"]) == 1

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert payload["mode"] == "simulate"
    assert payload["error"]["message"] == "configured measurement failure"
    assert payload["scpi"]["sent"] == ["*IDN?", ":SYSTem:ERRor?", ":MEASure:VPP? CHANnel1"]


def test_check_error_simulate_json_can_report_injected_error_queue(monkeypatch, capsys):
    backend = SimulatorBackend(system_errors=['-113,"Undefined header"'])
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

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
