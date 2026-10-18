"""Reusable hardware-free Tektronix runner test fixtures.

Helpers live outside test modules so vendor-specific tests never import another
test module just to access a fake runner.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "live-cli-check.ps1"
WORKFLOW_SCRIPT = ROOT / "scripts" / "live-workflow-check.ps1"
WORKFLOW_HARNESS = Path(__file__).with_name("tektronix_workflow_harness.ps1")
TARGETS = (
    "tektronix-tbs2074",
    "tektronix-tds2024b",
    "tektronix-tbs1052b",
)
requires_windows = pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")


def run_script(*arguments: str, env: dict[str, str] | None = None, script: Path = SCRIPT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *arguments,
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def fake_workflow_run(
    tmp_path: Path, target: str, scenario: str, *, debug: bool = True,
) -> tuple[subprocess.CompletedProcess[str], dict]:
    output_root = (
        ROOT / ".tmp_tests" / "tektronix_workflow_pytest" /
        target / tmp_path.name / uuid.uuid4().hex
    )
    result = run_script(
        "-ScriptPath", str(WORKFLOW_SCRIPT), "-Target", target,
        "-Scenario", scenario, "-PythonPath", r".\.venv\Scripts\python.exe",
        "-OutputRoot", str(output_root), *(["-MinimalArtifacts"] if not debug else []),
        script=WORKFLOW_HARNESS,
    )
    report_dir = "private" if debug else "shareable"
    reports = list(output_root.glob(f"run_*/{report_dir}/report.json"))
    assert len(reports) == 1, result.stdout + result.stderr
    return result, json.loads(reports[0].read_text(encoding="utf-8"))


def fake_run(
    tmp_path: Path, target: str, *extra: str, mode: str = "edge", mismatch: bool = False,
    connection: str = "usb", bad_bmp: bool = False,
    math_error: tuple[str, str] | None = None, cursor_error: tuple[str, str] | None = None,
    vectors_on: bool = False, vectors_mismatch: bool = False,
    waveform_rows: tuple[str, ...] = ("0,0.5", "0.001,0.6"),
    actual_points: int | None = None, hidden_outcome: str | None = None,
    subprocess_cli: bool = False, live_model: str | None = None,
    live_model_name: str | None = None,
    native_status_command: str | None = None, native_status_value: int = 0,
    native_status_raw: str = "0",
    core_supported_operations: tuple[str, ...] | None = None,
    confirmation: str = "enter", runt_channel: int = 1,
    holdoff_seconds: float = 0.000001, debug: bool = True,
    focused: bool = False, stage_responses: dict | None = None,
    save_pwd_path: str = "C:/scope", channel_label: str = "CH1",
) -> tuple[subprocess.CompletedProcess[str], dict]:
    model, channels, series = {
        TARGETS[0]: ("TBS2074", 4, "TBS2000"),
        TARGETS[1]: ("TDS2024B", 4, "TDS2000B"),
        TARGETS[2]: ("TBS1052B", 2, "TBS1000B"),
    }[target]
    live_detected_model, live_channels, live_series = {
        TARGETS[0]: ("TBS2074", 4, "TBS2000"),
        TARGETS[1]: ("TDS2024B", 4, "TDS2000B"),
        TARGETS[2]: ("TBS1052B", 2, "TBS1000B"),
    }[live_model or target]
    if live_model_name is not None:
        live_detected_model = live_model_name
    screenshot_bytes = b"bad" if bad_bmp else (b"\x89PNG\r\n\x1a\nfake" if target == TARGETS[0] else b"BMfake" if target == TARGETS[1] else b"\xff\xd8fake\xff\xd9")
    from scopes_tool_core.capabilities import capabilities_for_model_id
    actual_capabilities = capabilities_for_model_id(target)
    default_supported_operations = tuple(actual_capabilities.supported_operations)
    measurement_items = tuple(actual_capabilities.measurement_items)
    supported_operations = (
        tuple(core_supported_operations)
        if core_supported_operations is not None
        else default_supported_operations
    )
    acquisition_modes = ("normal", "average", "peak")
    average_counts = (
        (2, 4, 8, 16, 32, 64, 128, 256, 512)
        if target == TARGETS[0]
        else (4, 16, 64, 128)
    )
    cursor_source_selection = (
        "selected-waveform" if target == TARGETS[0] else "independent"
    )
    values = {
        "system-standard-event": {"value": 0},
        "channel-display": {"display": True},
        "channel-scale": {"volts_per_division": 1.0},
        "channel-coupling": {"coupling": "dc"},
        "channel-probe": {"probe_ratio": 10.0},
        "channel-bandwidth-limit": {"bandwidth_limit": False},
        "channel-invert": {"invert": False},
        "channel-units": {"units": "volt"},
        "channel-offset": {"volts": 0.0},
        "channel-label": {"text": channel_label},
        "channel-probe-skew": {"probe_skew_seconds": 0.0},
        "timebase-scale": {"seconds_per_division": 0.001},
        "timebase-position": {"position_seconds": 0.0},
        "acquisition": {"type": "normal", "count": 16},
        "trigger-sweep": {"mode": "auto"},
        "trigger-mode": {"mode": mode, "raw_mode": mode},
        "trigger-runt": {"mode": mode, "channel": runt_channel, "polarity": "positive",
                         "qualifier": "none", "low_level_volts": -0.1,
                         "high_level_volts": 0.1, "time_seconds": 1e-6},
        "trigger-tv": {"mode": mode, "source_channel": 1, "standard": "ntsc",
                       "tv_mode": "field1", "polarity": "positive", "line": None},
        "trigger-edge-source": {"source": "analog-channel", "source_channel": 1},
        "trigger-edge-slope": {"slope": "positive"},
        "trigger-edge-coupling": {"coupling": "dc"},
        "trigger-holdoff": {"seconds": holdoff_seconds},
        "trigger-edge-level": {"level_volts": 0.0},
        "trigger-edge": {"source_channel": 1, "level_volts": 0.0, "slope": "positive"},
        "save-pwd": {"path": save_pwd_path},
        "save-waveform": {"operation_complete": True},
        "display-vectors": {"value": vectors_on},
        "display-persistence": {"mode": "minimum", "seconds": None},
        "math-display": {"enabled": False},
        "math-operator": {"math_operation": "add", "source1": "channel1", "source2": "channel2"},
        "cursor": {
            "mode": "OFF", "source_channel": None,
            "x1_seconds": 0.0, "x2_seconds": 0.0,
            "y1_volts": 0.0, "y2_volts": 0.0,
        },
        "save-image-format": {"format": "png"},
        "save-waveform-format": {"format": "csv"},
        "save-image-ink-saver": {"enabled": False},
        "save-image": {"operation_complete": True, "raw_operation_complete": "1"},
        "reference-display": {"displayed": True},
        "reference-query": {"displayed": True, "label": None, "raw_label": None},
        "measure": {"valid": True, "value": 0.5, "unit": "V"},
        "single-wait": {"poll_source": "busy", "poll_command": "BUSY?", "outcome": "natural"},
        "trigger-pulse-width": {"mode": mode, "channel": 1, "polarity": "positive",
                                "qualifier": "less-than", "less_than_seconds": 1e-6,
                                "greater_than_seconds": None, "level_volts": 0.0},
    }
    raw_state = tmp_path / "position-state.json"
    cursor_state = tmp_path / "cursor-state.json"
    core_stub = tmp_path / "scopes_tool_core"
    core_stub.mkdir()
    (core_stub / "__init__.py").write_text("", encoding="utf-8")
    (core_stub / "capabilities.py").write_text(
        "from types import SimpleNamespace\n"
        f"supported_operations = {supported_operations!r}\n"
        f"acquisition_modes = {acquisition_modes!r}\n"
        f"average_counts = {average_counts!r}\n"
        f"cursor_source_selection = {cursor_source_selection!r}\n"
        f"measurement_items = {measurement_items!r}\n"
        "def capabilities_for_model_id(model_id):\n"
        " return SimpleNamespace(supported_operations=frozenset(supported_operations), "
        "cursor_source_selection=cursor_source_selection, fixed_acquisition_memory_mode='realtime', "
        "acquisition_modes=acquisition_modes, average_counts=average_counts, measurement_items=measurement_items)\n",
        encoding="utf-8",
    )
    stub = tmp_path / "scopes_tool_cli"
    stub.mkdir()
    (stub / "__init__.py").write_text("", encoding="utf-8")
    (stub / "cli.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        f"with Path({str(tmp_path / 'argv.jsonl')!r}).open('a', encoding='utf-8') as log:\n"
        " log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "command = sys.argv[1]\n"
        f"values = {values!r}\n"
        f"raw_state = Path({str(raw_state)!r})\n"
        "if command == 'timebase-position' and raw_state.exists():\n"
        " state = json.loads(raw_state.read_text())\n"
        " values[command]['position_seconds'] = (state['delay'] if state['mode'] == 'ON' else "
        "(50 - state['position']) / 100 * state['length'] / state['rate'])\n"
        f"math_error, cursor_error = {math_error!r}, {cursor_error!r}\n"
        "error = (math_error if command == 'math-operator' and '--query' in sys.argv else\n"
        "         cursor_error if command == 'cursor' and '--x1' in sys.argv else None)\n"
        "if error:\n"
        " print(json.dumps({'ok': False, 'error': {'type': error[0], 'message': error[1]}}))\n"
        " sys.exit(1)\n"
        f"cursor_state = Path({str(cursor_state)!r})\n"
        "if command == 'cursor':\n"
        " if '--off' in sys.argv:\n"
        "  cursor_state.write_text(json.dumps({'mode': 'OFF', 'source_channel': None, 'x1_seconds': None, 'x2_seconds': None, 'y1_volts': None, 'y2_volts': None}))\n"
        " elif '--query' not in sys.argv:\n"
        "  state = json.loads(cursor_state.read_text()) if cursor_state.exists() else {'mode': 'OFF', 'source_channel': None, 'x1_seconds': None, 'x2_seconds': None, 'y1_volts': None, 'y2_volts': None}\n"
        "  if '--source-channel' in sys.argv: state['source_channel'] = int(sys.argv[sys.argv.index('--source-channel') + 1])\n"
        "  has_x = has_y = False\n"
        "  for option, field, axis in (('--x1', 'x1_seconds', 'x'), ('--x2', 'x2_seconds', 'x'), ('--y1', 'y1_volts', 'y'), ('--y2', 'y2_volts', 'y')):\n"
        "   if option in sys.argv:\n"
        "    state[field] = float(sys.argv[sys.argv.index(option) + 1])\n"
        "    has_x = has_x or axis == 'x'; has_y = has_y or axis == 'y'\n"
        "  requested = sys.argv[sys.argv.index('--function') + 1] if '--function' in sys.argv else None\n"
        "  if requested == 'off':\n"
        "   state = {'mode': 'OFF', 'source_channel': None, 'x1_seconds': None, 'x2_seconds': None, 'y1_volts': None, 'y2_volts': None}\n"
        "  elif requested is not None:\n"
        "   state['mode'] = {'screen': 'SCREEN', 'waveform': 'WAVEform', 'vbars': 'VBArs', 'hbars': 'HBArs'}[requested]\n"
        "  else:\n"
        "   state['mode'] = 'SCREEN' if has_x and has_y else 'TIME' if has_x else 'AMPLITUDE' if has_y else 'OFF'\n"
        "  cursor_state.write_text(json.dumps(state))\n"
        " elif cursor_state.exists(): values[command] = json.loads(cursor_state.read_text())\n"
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
        f" Path(path).write_bytes({screenshot_bytes!r})\n"
        f" values[command] = {{'format': {'PNG' if target == TARGETS[0] else 'BMP' if target == TARGETS[1] else 'JPEG'!r}, 'byte_count': Path(path).stat().st_size, 'image_path': path}}\n"
        f"print(json.dumps({{'ok': True, 'idn': {{'vendor': 'TEKTRONIX', 'model': '{model}'}}, "
        f"'capabilities': {{'analog_channels': {channels}, 'series': '{series}'}}, "
        "'result': values.get(command, {})}))\n",
        encoding="utf-8",
    )
    output_root = ROOT / ".tmp_tests" / "live_tektronix_check" / tmp_path.parent.name / tmp_path.name
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    arguments = [
        "-Target", target, "-Connection", connection, "-Resource",
        "USB0::FAKE::INSTR" if connection == "usb" else "TCPIP0::example::INSTR",
        "-Python", sys.executable, "-OutputRoot", str(output_root),
        *(["-DebugArtifacts"] if debug else []), *extra,
    ]
    report_dir = "private" if debug else "shareable"
    previous_runs = set(output_root.glob(f"run_*/{report_dir}/report.json"))
    fixture = tmp_path / "scenario.json"
    fixture.write_text(json.dumps({
            "values": values,
            "idn": {"vendor": "TEKTRONIX", "model": model},
            "capabilities": {"analog_channels": channels, "series": series},
            "live_idn": {"vendor": "TEKTRONIX", "model": live_detected_model},
            "live_capabilities": {"analog_channels": live_channels, "series": live_series},
            "native_status_command": native_status_command,
            "native_status_value": native_status_value,
            "native_status_raw": native_status_raw,
            "math_error": math_error, "cursor_error": cursor_error,
            "mismatch": mismatch, "vectors_mismatch": vectors_mismatch,
            "hidden_outcome": hidden_outcome,
            "points": len(waveform_rows) if actual_points is None else actual_points,
            "csv_text": "time_s,ch1_v\n" + "\n".join(waveform_rows) + "\n",
            "screenshot_bytes": list(screenshot_bytes),
            "screenshot_format": "PNG" if target == TARGETS[0] else "BMP" if target == TARGETS[1] else "JPEG",
            "arguments": arguments,
            "focused": focused, "stage_responses": stage_responses or {},
        }), encoding="utf-8")
    result = run_script(
        "-ScriptPath", str(SCRIPT), "-FixturePath", str(fixture),
        "-PythonPath", sys.executable, "-OutputRoot", str(output_root),
        "-OperatorConfirmation", confirmation,
        script=Path(__file__).with_name("tektronix_function_harness.ps1"), env=env,
    )
    runs = set(output_root.glob(f"run_*/{report_dir}/report.json")) - previous_runs
    assert len(runs) == 1, result.stdout + result.stderr
    report = json.loads(runs.pop().read_text(encoding="utf-8"))
    assert not (tmp_path / "argv.jsonl").exists()
    counts = report["summary_counts"]
    assert counts["cases"] == len(report["cases"])
    assert counts["passed"] == sum(case["status"] == "PASS" for case in report["cases"])
    assert counts["failed"] == sum(case["status"] == "FAIL" for case in report["cases"])
    assert counts["na"] == sum(case["status"] == "N/A" for case in report["cases"])
    assert counts["not_tested"] == sum(case["status"] == "NOT TESTED" for case in report["cases"])
    assert counts["invocations"] == len(report["invocations"])
    return result, report


VISA_FAILURE = {
    "ExitCode": 1,
    "Payload": {"ok": False, "error": {"type": "VisaIOError", "message": "Injected I/O failure"}},
}
