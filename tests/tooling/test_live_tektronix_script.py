"""Hardware-free checks for the dedicated Tektronix live acceptance runner."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "live-tektronix-check.ps1"
TEXT = SCRIPT.read_text(encoding="utf-8")
TARGETS = (
    "tektronix-tbs2074b",
    "tektronix-tds2024b",
    "tektronix-tbs1052b",
)
requires_windows = pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")


def run_script(*arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            *arguments,
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@requires_windows
@pytest.mark.parametrize("target", (*TARGETS, "all", "keysight-dsox4034a"))
def test_exact_targets_and_explicit_resource(target: str) -> None:
    args = ["-Target", target, "-Connection", "usb", "-Resource", "TCPIP0::example::INSTR"]
    result = run_script(*args)
    assert result.returncode != 0
    if target in TARGETS:
        assert "resource type must match" in result.stderr
    else:
        assert "Unsupported target" in result.stderr


@requires_windows
def test_missing_resource_rejected_before_any_live_invocation() -> None:
    result = run_script("-Target", TARGETS[0], "-Connection", "usb")
    assert result.returncode != 0
    assert "Resource" in result.stderr


@requires_windows
def test_backend_and_output_root_are_bounded() -> None:
    base = ["-Target", TARGETS[0], "-Connection", "usb", "-Resource", "USB0::FAKE::INSTR"]
    backend = run_script(*base, "-Backend", "@other")
    assert backend.returncode != 0
    assert "Unsupported backend" in backend.stderr
    outside = run_script(*base, "-OutputRoot", str(ROOT / "docs"))
    assert outside.returncode != 0
    assert "OutputRoot must be under .tmp_tests" in outside.stderr


@requires_windows
@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ([], "explicit -SetupSlot"),
        (["-SetupSlot", "0", "-ReferenceSlot", "1"], "SetupSlot"),
        (["-SetupSlot", "1", "-ReferenceSlot", "3"], "ReferenceSlot"),
    ],
)
def test_storage_write_requires_explicit_slots_in_range(extra: list[str], message: str) -> None:
    result = run_script(
        "-Target", TARGETS[0], "-Connection", "usb", "-Resource", "USB0::FAKE::INSTR",
        "-IncludeStorageWrites", *extra,
    )
    assert result.returncode != 0
    assert message in result.stderr


@requires_windows
def test_identity_mismatch_stops_before_other_cases(tmp_path: Path) -> None:
    stub = tmp_path / "scopes_tool_cli"
    stub.mkdir()
    (stub / "__init__.py").write_text("", encoding="utf-8")
    (stub / "cli.py").write_text(
        "import json\n"
        "print(json.dumps({'ok': True, 'idn': {'vendor': 'Tektronix', 'model': 'TDS2024B'}, "
        "'capabilities': {'analog_channels': 4, 'series': 'TDS2000B'}, 'result': {}}))\n",
        encoding="utf-8",
    )
    output_root = ROOT / ".tmp_tests" / "live_tektronix_check" / "tooling_identity_gate"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    result = run_script(
        "-Target", TARGETS[0], "-Connection", "usb", "-Resource", "USB0::FAKE::INSTR",
        "-Python", sys.executable, "-OutputRoot", str(output_root),
        "-IncludeConfigurationActions", "-IncludeScreenshot", "-IncludeAcquisitionActions",
        env=env,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    runs = sorted(output_root.glob("run_*/private/report.json"), key=lambda path: path.stat().st_mtime)
    assert runs
    report = json.loads(runs[-1].read_text(encoding="utf-8"))
    assert report["hardware_touched"] is True  # Stub process attempted; no instrument opened.
    assert [(case["name"], case["status"]) for case in report["cases"]] == [("identify", "FAIL")]
    assert len(report["invocations"]) == 1
    assert report["invocations"][0]["arguments"][2] == "identify"


def fake_run(
    tmp_path: Path, target: str, *extra: str, mode: str = "edge", mismatch: bool = False,
    connection: str = "usb", bad_bmp: bool = False,
    math_error: tuple[str, str] | None = None, cursor_error: tuple[str, str] | None = None,
    vectors_on: bool = False, vectors_mismatch: bool = False,
    waveform_rows: tuple[str, ...] = ("0,0.5", "0.001,0.6"),
    actual_points: int | None = None, hidden_outcome: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict]:
    model, channels, series = {
        TARGETS[0]: ("TBS2074B", 4, "TBS2000B"),
        TARGETS[1]: ("TDS2024B", 4, "TDS2000B"),
        TARGETS[2]: ("TBS1052B", 2, "TBS1000B"),
    }[target]
    stub = tmp_path / "scopes_tool_cli"
    stub.mkdir()
    (stub / "__init__.py").write_text(
        f"__path__.append({str(ROOT / 'src' / 'scopes_tool_cli')!r})\n", encoding="utf-8"
    )
    (stub / "cli.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "from scopes_tool_cli.parser import _build_parser\n"
        "_build_parser().parse_args()\n"
        "command = sys.argv[1]\n"
        "values = {\n"
        " 'system-standard-event': {'value': 0},\n"
        " 'channel-display': {'display': True},\n"
        " 'channel-scale': {'volts_per_division': 1.0},\n"
        " 'channel-coupling': {'coupling': 'dc'},\n"
        " 'channel-probe': {'probe_ratio': 10.0},\n"
        " 'channel-bandwidth-limit': {'bandwidth_limit': False},\n"
        " 'channel-invert': {'invert': False},\n"
        " 'channel-units': {'units': 'volt'},\n"
        " 'channel-offset': {'volts': 0.0},\n"
        " 'channel-label': {'text': 'CH1'},\n"
        " 'channel-probe-skew': {'probe_skew_seconds': 0.0},\n"
        " 'timebase-scale': {'seconds_per_division': 0.001},\n"
        " 'timebase-position': {'position_seconds': 0.0},\n"
        " 'acquisition': {'type': 'normal', 'count': 16},\n"
        " 'trigger-sweep': {'mode': 'auto'},\n"
        f" 'trigger-mode': {{'mode': {mode!r}, 'raw_mode': {mode!r}}},\n"
        f" 'trigger-runt': {{'mode': {mode!r}, 'channel': 1, 'polarity': 'positive', "
        "'qualifier': 'none', 'low_level_volts': -0.1, 'high_level_volts': 0.1, 'time_seconds': 1e-6},\n"
        f" 'trigger-tv': {{'mode': {mode!r}, 'source_channel': 1, 'standard': 'ntsc', "
        "'tv_mode': 'field1', 'polarity': 'positive', 'line': None},\n"
        " 'trigger-edge-source': {'source': 'analog-channel', 'source_channel': 1},\n"
        " 'trigger-edge-slope': {'slope': 'positive'},\n"
        " 'trigger-edge-coupling': {'coupling': 'dc'},\n"
        " 'trigger-holdoff': {'seconds': 0.000001},\n"
        " 'trigger-edge-level': {'level_volts': 0.0},\n"
        " 'trigger-edge': {'source_channel': 1, 'level_volts': 0.0, 'slope': 'positive'},\n"
        " 'save-pwd': {'path': 'C:/scope'},\n"
        f" 'display-vectors': {{'value': {vectors_on!r}}},\n"
        " 'display-persistence': {'mode': 'minimum', 'seconds': None},\n"
        " 'math-display': {'enabled': False},\n"
        " 'math-operator': {'math_operation': 'add', 'source1': 'channel1', 'source2': 'channel2'},\n"
        " 'cursor': {'mode': 'OFF', 'x1_seconds': 0.0, 'x2_seconds': 0.0},\n"
        " 'save-image-format': {'format': 'png'},\n"
        " 'save-waveform-format': {'format': 'csv'},\n"
        " 'save-image-ink-saver': {'enabled': False},\n"
        " 'save-image': {'operation_complete': True, 'raw_operation_complete': '1'},\n"
        " 'reference-display': {'displayed': True},\n"
        " 'reference-query': {'displayed': True, 'label': None, 'raw_label': None},\n"
        " 'measure': {'valid': True, 'value': 0.5, 'unit': 'V'},\n"
        " 'single-wait': {'poll_source': 'busy', 'poll_command': 'BUSY?', 'outcome': 'natural'},\n"
        f" 'trigger-pulse-width': {{'mode': {mode!r}, 'channel': 1, 'polarity': 'positive', "
        "'qualifier': 'less-than', 'less_than_seconds': 1e-6, 'greater_than_seconds': None, 'level_volts': 0.0},\n"
        "}\n"
        f"math_error, cursor_error = {math_error!r}, {cursor_error!r}\n"
        "error = (math_error if command == 'math-operator' and '--query' in sys.argv else\n"
        "         cursor_error if command == 'cursor' and '--x1' in sys.argv else None)\n"
        "if error:\n"
        " print(json.dumps({'ok': False, 'error': {'type': error[0], 'message': error[1]}}))\n"
        " sys.exit(1)\n"
        f"vectors_path = Path({str(tmp_path / 'vectors_set.txt')!r})\n"
        "if command == 'display-vectors':\n"
        " if '--on' in sys.argv: vectors_path.write_text('on')\n"
        f" if {vectors_mismatch!r} and '--query' in sys.argv and vectors_path.exists():\n"
        "  values[command]['value'] = False\n"
        f"counter_path = Path({str(tmp_path / 'mode_queries.txt')!r})\n"
        "if command == 'trigger-mode' and '--query' in sys.argv:\n"
        " count = int(counter_path.read_text()) + 1 if counter_path.exists() else 1\n"
        " counter_path.write_text(str(count))\n"
        f" if {mismatch!r} and count > 1: values[command]['mode'] = 'glitch'\n"
        f"hidden_outcome = {hidden_outcome!r}\n"
        f"hidden_capture = Path({str(tmp_path / 'hidden_capture.txt')!r})\n"
        "channel = sys.argv[sys.argv.index('--channel') + 1] if '--channel' in sys.argv else None\n"
        "if command == 'channel-display' and channel == '2' and hidden_outcome:\n"
        " values[command]['display'] = hidden_outcome == 'display-on' and hidden_capture.exists()\n"
        "if command == 'capture':\n"
        " if channel == '2' and hidden_outcome:\n"
        "  hidden_capture.write_text('attempted')\n"
        "  if hidden_outcome == 'unexpected-success':\n"
        "   print(json.dumps({'ok': True, 'result': {}})); sys.exit(0)\n"
        "  error_type = 'OscilloscopeError' if hidden_outcome == 'wrong-error' else 'WaveformResponseError'\n"
        "  print(json.dumps({'ok': False, 'error': {'type': error_type, 'message': 'CH2 is not displayed; waveform capture requires a displayed analog channel'}}))\n"
        "  sys.exit(1)\n"
        f" points = {len(waveform_rows) if actual_points is None else actual_points!r}\n"
        f" csv_text = {'time_s,ch1_v' + chr(10) + chr(10).join(waveform_rows) + chr(10)!r}\n"
        " Path(sys.argv[sys.argv.index('--csv') + 1]).write_text(csv_text)\n"
        " Path(sys.argv[sys.argv.index('--meta') + 1]).write_text(json.dumps({'actual_points': points}))\n"
        " values[command] = {'format': 'BYTE', 'actual_points': points}\n"
        "if command == 'screenshot':\n"
        " path = sys.argv[sys.argv.index('--output') + 1]\n"
        f" Path(path).write_bytes({'bad' if bad_bmp else 'BMfake'!r}.encode())\n"
        " values[command] = {'format': 'BMP', 'byte_count': Path(path).stat().st_size, 'image_path': path}\n"
        f"print(json.dumps({{'ok': True, 'idn': {{'vendor': 'TEKTRONIX', 'model': '{model}'}}, "
        f"'capabilities': {{'analog_channels': {channels}, 'series': '{series}'}}, "
        "'result': values.get(command, {})}))\n",
        encoding="utf-8",
    )
    output_root = ROOT / ".tmp_tests" / "live_tektronix_check" / tmp_path.name
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    result = run_script(
        "-Target", target, "-Connection", connection, "-Resource",
        "USB0::FAKE::INSTR" if connection == "usb" else "TCPIP0::example::INSTR",
        "-Python", sys.executable, "-OutputRoot", str(output_root), *extra, env=env,
    )
    runs = sorted(output_root.glob("run_*/private/report.json"), key=lambda path: path.stat().st_mtime)
    assert runs
    report = json.loads(runs[-1].read_text(encoding="utf-8"))
    counts = report["summary_counts"]
    assert counts == {
        "passed": sum(case["status"] == "PASS" for case in report["cases"]),
        "failed": sum(case["status"] == "FAIL" for case in report["cases"]),
        "na": sum(case["status"] == "N/A" for case in report["cases"]),
    }
    return result, report


@requires_windows
def test_math_state_outside_public_subset_is_na(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], math_error=("OscilloscopeError", "Unsupported Tek Math expression: 'FFT'"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["math-operator"]["status"] == "N/A"
    assert report["status"] == "pass"
    calls = [inv for inv in report["invocations"] if inv["arguments"][2] == "math-operator"]
    assert len(calls) == 1
    assert "--query" in calls[0]["arguments"]
    assert calls[0]["result"] == "N/A"


@requires_windows
@pytest.mark.parametrize("target", TARGETS[1:])
def test_cursor_seconds_prerequisite_is_na(tmp_path: Path, target: str) -> None:
    result, report = fake_run(
        tmp_path, target, "-IncludeConfigurationActions",
        cursor_error=("ParameterValidationError", "X cursors require existing seconds units"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["cursor-set"]["status"] == "N/A"
    assert cases["cursor-off"]["status"] == "PASS"
    assert report["status"] == "pass"
    calls = [inv for inv in report["invocations"] if inv["arguments"][2] == "cursor"]
    setters = [inv for inv in calls if "--query" not in inv["arguments"]]
    assert len(setters) == 2  # Rejected X setter and the existing opt-in OFF action.
    assert "--x1" in setters[0]["arguments"]
    assert setters[0]["result"] == "N/A"
    assert "--off" in setters[1]["arguments"]
    assert "--auto-timebase" not in setters[0]["arguments"]
    assert "not restored" in result.stdout


@requires_windows
@pytest.mark.parametrize(("command", "error"), [
    ("math-operator", ("OscilloscopeError", "Math query failed")),
    ("cursor", ("ParameterValidationError", "X cursor position is outside the graticule")),
])
def test_unrelated_math_or_cursor_errors_remain_fail(
    tmp_path: Path, command: str, error: tuple[str, str],
) -> None:
    errors = {"math_error" if command == "math-operator" else "cursor_error": error}
    result, report = fake_run(tmp_path, TARGETS[1], "-IncludeConfigurationActions", **errors)
    assert result.returncode != 0
    assert report["status"] == "fail"
    assert report["summary_counts"]["failed"] == 1
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["math-operator" if command == "math-operator" else "cursor-set"]["status"] == "FAIL"


@requires_windows
@pytest.mark.parametrize("target", TARGETS[1:])
@pytest.mark.parametrize("mismatch", (False, True))
def test_vectors_on_requires_readback(tmp_path: Path, target: str, mismatch: bool) -> None:
    result, report = fake_run(tmp_path, target, vectors_on=True, vectors_mismatch=mismatch)
    assert (result.returncode != 0) == mismatch, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["display-vectors-query"]["status"] == "PASS"
    assert cases["display-vectors-on"]["status"] == ("FAIL" if mismatch else "PASS")
    assert report["status"] == ("fail" if mismatch else "pass")
    assert report["summary_counts"]["failed"] == int(mismatch)
    calls = [inv["arguments"] for inv in report["invocations"] if inv["arguments"][2] == "display-vectors"]
    assert len(calls) == 3
    assert "--query" in calls[0]
    assert "--on" in calls[1]
    assert "--query" in calls[2]


@requires_windows
@pytest.mark.parametrize("target", TARGETS)
def test_default_case_flow_with_fake_cli(tmp_path: Path, target: str) -> None:
    result, report = fake_run(tmp_path, target)
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["identify"]["status"] == "PASS"
    assert cases["channel-display"]["status"] == "PASS"
    if target == TARGETS[0]:
        assert cases["channel-probe-skew"]["status"] == "PASS"
        assert cases["display-vectors"]["status"] == "N/A"
    else:
        assert cases["timebase-position"]["status"] == "PASS"
        assert cases["display-vectors-query"]["status"] == "PASS"
        assert cases["display-vectors-on"]["status"] == "N/A"
    assert cases["trigger-mode"]["status"] == "PASS"
    for name in ("channel-units", "math-display", "math-operator", "display-persistence",
                 "cursor-query", "trigger-edge", "trigger-edge-source", "trigger-edge-slope",
                 "trigger-edge-coupling", "acquisition-points", "record-length"):
        assert cases[name]["status"] == "PASS", cases[name]
    assert cases["autoscale"]["status"] == "N/A"
    assert cases["setup-save"]["status"] == "N/A"
    assert not [case for case in report["cases"] if case["status"] == "FAIL"]
    assert report["status"] == "pass"
    assert all(invocation["arguments"][2] not in {
        "autoscale", "setup-save", "run", "screenshot", "measure-install", "measure-clear", "save-image", "measure", "capture", "single-wait"
    }
               for invocation in report["invocations"])
    assert not any(inv["arguments"][2] == "cursor" and "--query" not in inv["arguments"]
                   for inv in report["invocations"])
    unsupported = ({"timebase-position", "trigger-tv", "save-image-ink-saver", "display-vectors"}
                   if target == TARGETS[0] else
                   {"sample-rate", "channel-offset", "channel-label", "channel-probe-skew",
                    "trigger-edge-level", "trigger-runt", "save-image-format", "save-waveform-format"})
    assert not unsupported.intersection(inv["arguments"][2] for inv in report["invocations"])
    commands = [inv["arguments"][2] for inv in report["invocations"]]
    assert commands.index("trigger-mode") < commands.index("trigger-edge-source")
    for name in ("sample-rate", "save-image-format", "save-waveform-format", "save-image-ink-saver"):
        assert cases[name]["status"] == ("N/A" if name in unsupported else "PASS")


@requires_windows
@pytest.mark.parametrize(("target", "mode"), [(TARGETS[0], "runt"), (TARGETS[1], "tv"), (TARGETS[2], "tv")])
def test_non_edge_mode_preserves_trigger_configuration(tmp_path: Path, target: str, mode: str) -> None:
    result, report = fake_run(tmp_path, target, mode=mode)
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    special = "trigger-runt" if mode == "runt" else "trigger-tv"
    assert cases[special]["status"] == "PASS", cases[special]
    for name in ("trigger-edge", "trigger-edge-source", "trigger-edge-slope", "trigger-edge-coupling"):
        assert cases[name]["status"] == "N/A"
    for inv in report["invocations"]:
        args = inv["arguments"]
        if args[2].startswith("trigger-edge"):
            assert "--query" in args
        if args[2] == "trigger-mode" and "--mode" in args:
            assert args[args.index("--mode") + 1] == mode
        if args[2] == "trigger-runt" and "--query" not in args:
            assert "--time-seconds" not in args  # Unqualified runt preserves dormant width.


@requires_windows
@pytest.mark.parametrize("target", TARGETS)
def test_explicit_action_storage_and_screenshot_gates(tmp_path: Path, target: str) -> None:
    result, report = fake_run(
        tmp_path, target, "-IncludeConfigurationActions", "-IncludeAcquisitionActions",
        "-IncludeAutoscale", "-IncludeStorageWrites", "-SetupSlot", "1", "-ReferenceSlot", "1",
        "-ImageFilename", "acceptance.png", "-IncludeScreenshot",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    for name in ("cursor-off", "measure-install", "measure-clear", "run", "single", "force-trigger",
                 "stop-acquisition", "autoscale", "save-image", "setup-save", "setup-recall",
                 "reference-save", "reference-display", "reference-query", "measure", "capture-byte", "single-wait-natural", "single-wait-force"):
        assert cases[name]["status"] == "PASS", cases[name]
    assert cases["cursor-set"]["status"] == ("N/A" if target == TARGETS[0] else "PASS")
    assert cases["screenshot-bmp"]["status"] == ("PASS" if target == TARGETS[1] else "N/A")
    assert report["acquisition_final_state"] == "stopped"
    assert cases["capture-hidden-channel"]["status"] == "N/A"


@requires_windows
@pytest.mark.parametrize("rows,points,status", [
    (("0,0.5",), None, "PASS"),
    ((), 0, "FAIL"),
    (("0,0.5",), 2, "FAIL"),
    (("NaN,0.5",), None, "FAIL"),
    (("0,Infinity",), None, "FAIL"),
    (("0.001,0.5", "0,0.6"), None, "FAIL"),
    (("0,0.5", "0,0.6"), None, "FAIL"),
])
def test_capture_artifact_validity(tmp_path: Path, rows, points, status) -> None:
    result, report = fake_run(tmp_path, TARGETS[0], "-IncludeConfigurationActions",
        waveform_rows=rows, actual_points=points)
    cases = {case["name"]: case for case in report["cases"]}
    if status == "PASS":
        assert result.returncode == 0, result.stdout + result.stderr
        assert cases["capture-byte"]["status"] == "PASS"
    else:
        assert result.returncode != 0
        assert cases["measure-capture"]["status"] == "FAIL"
        assert "capture-byte" not in cases


@requires_windows
@pytest.mark.parametrize("outcome,status", [
    ("rejected", "PASS"), ("unexpected-success", "FAIL"),
    ("wrong-error", "FAIL"), ("display-on", "FAIL"),
])
def test_hidden_capture_rejection_and_display_readback(tmp_path: Path, outcome, status) -> None:
    result, report = fake_run(tmp_path, TARGETS[0], "-IncludeConfigurationActions",
        hidden_outcome=outcome)
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["capture-hidden-channel"]["status"] == status
    assert (result.returncode == 0) == (status == "PASS")
    invocations = report["invocations"]
    attempted = next(index for index, invocation in enumerate(invocations)
        if "capture-hidden-channel" in invocation["stdout"])
    assert invocations[attempted + 1]["arguments"][2] == "channel-display"
    assert "--query" in invocations[attempted + 1]["arguments"]
    for invocation in invocations:
        if invocation["arguments"][2] == "channel-display" and "2" in invocation["arguments"]:
            assert "--query" in invocation["arguments"]


@requires_windows
def test_screenshot_transport_and_storage_filename_preconditions(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[1], "-IncludeScreenshot", "-IncludeStorageWrites",
        "-SetupSlot", "1", "-ReferenceSlot", "1", connection="tcpip",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["screenshot-bmp"]["status"] == "N/A"
    assert cases["save-image"]["status"] == "N/A"
    assert not {"screenshot", "save-image"}.intersection(inv["arguments"][2] for inv in report["invocations"])


@requires_windows
@pytest.mark.parametrize("failure", ("mode", "bmp"))
def test_failed_readback_or_artifact_reports_fail(tmp_path: Path, failure: str) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[1], "-IncludeScreenshot", mismatch=failure == "mode", bad_bmp=failure == "bmp",
    )
    assert result.returncode != 0
    assert report["status"] == "fail"
    assert report["summary_counts"]["failed"] == 1
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["trigger-mode" if failure == "mode" else "screenshot-bmp"]["status"] == "FAIL"
    if failure == "mode":
        assert cases["trigger-edge"]["status"] == "N/A"


@requires_windows
def test_image_filename_requires_storage_opt_in() -> None:
    result = run_script(
        "-Target", TARGETS[0], "-Connection", "usb", "-Resource", "USB0::FAKE::INSTR",
        "-ImageFilename", "acceptance.png",
    )
    assert result.returncode != 0
    assert "require -IncludeStorageWrites" in result.stderr


def test_runner_uses_only_public_cli_and_default_options_are_off() -> None:
    commands = re.findall(r'-Command\s+"([a-z][a-z0-9-]+)"', TEXT)
    assert commands
    assert not set(commands) & {
        "check-error",
        "doctor", "smoke", "list-resources",
    }
    assert "ProcessStartInfo" in TEXT
    assert '"-m", "scopes_tool_cli.cli"' in TEXT
    assert not re.search(r"(?i)(?:\bACQuire:|\bTRIGger:|\bCH\d+:|\*ESR\?|\*IDN\?)", TEXT)
    assert not re.search(r"(?i)(?:EVENT\?|EVMsg\?|ALLEv\?|EVQty\?|DISPLAY:STYLE\s+DOTS)", TEXT)
    assert "-IncludeAcquisitionActions" in TEXT
    assert "-IncludeAutoscale" in TEXT
    assert "-IncludeStorageWrites" in TEXT
    assert 'Add-Case "autoscale" "N/A"' in TEXT
    assert 'Add-Case $name "N/A" "Requires -IncludeAcquisitionActions"' in TEXT
    assert 'Add-Case $name "N/A" "Requires -IncludeStorageWrites' in TEXT


def test_identity_gate_and_vectors_safety_are_explicit() -> None:
    assert TEXT.index('Invoke-Cli -Stage "identify"') < TEXT.index("if (-not $script:StopAfterIdentity)")
    assert "[string]$identity.idn.vendor" in TEXT
    assert "[string]$identity.idn.model" in TEXT
    assert "[int]$identity.capabilities.analog_channels" in TEXT
    assert 'Invoke-Cli -Stage "display-vectors-query"' in TEXT
    assert "if ($isOn -is [bool] -and $isOn)" in TEXT
    assert "no public OFF setter" in TEXT


@requires_windows
def test_pulse_width_roundtrip_preserves_current_glitch_mode(tmp_path):
    result, report = fake_run(tmp_path, TARGETS[0], mode="glitch")
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["trigger-pulse-width"]["status"] == "PASS"
    calls = [inv["arguments"] for inv in report["invocations"] if inv["arguments"][2] == "trigger-pulse-width"]
    assert len(calls) == 3  # Query, same-value set, and readback preserve the current settings.
    assert all("range" not in call for call in calls)
