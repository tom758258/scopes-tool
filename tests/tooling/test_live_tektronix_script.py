"""Hardware-free checks for Tektronix live validation runners."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "live-cli-check.ps1"
WORKFLOW_SCRIPT = ROOT / "scripts" / "live-workflow-check.ps1"
WORKFLOW_HARNESS = Path(__file__).with_name("tektronix_workflow_harness.ps1")
TEXT = (ROOT / "scripts" / "_live_tektronix_helpers.ps1").read_text(encoding="utf-8")
VALIDATION_HELPERS_TEXT = (ROOT / "scripts" / "_validation_helpers.ps1").read_text(encoding="utf-8")
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
    tmp_path: Path, target: str, scenario: str,
) -> tuple[subprocess.CompletedProcess[str], dict]:
    output_root = (
        ROOT / ".tmp_tests" / "tektronix_workflow_pytest" /
        target / tmp_path.name / uuid.uuid4().hex
    )
    result = run_script(
        "-ScriptPath", str(WORKFLOW_SCRIPT), "-Target", target,
        "-Scenario", scenario, "-PythonPath", r".\.venv\Scripts\python.exe",
        "-OutputRoot", str(output_root), script=WORKFLOW_HARNESS,
    )
    reports = list(output_root.glob("run_*/private/report.json"))
    assert len(reports) == 1, result.stdout + result.stderr
    return result, json.loads(reports[0].read_text(encoding="utf-8"))


@requires_windows
@pytest.mark.parametrize("target", (*TARGETS, "all", "keysight-dsox4034a"))
def test_exact_targets_and_explicit_resource(target: str) -> None:
    args = ["-Target", target, "-Connection", "usb", "-Resource", "TCPIP0::example::INSTR"]
    result = run_script(*args)
    assert result.returncode != 0
    if target in TARGETS:
        assert "does not match resource" in result.stderr
    elif target == "all":
        assert "not supported for live validation" in result.stderr
    else:
        assert "does not match resource" in result.stderr


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
    assert "must stay under repository .tmp_tests" in outside.stderr


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
    result, report = fake_run(
        tmp_path, TARGETS[0], "-IncludeConfigurationActions", "-IncludeScreenshot",
        "-IncludeAcquisitionActions", live_model=TARGETS[1],
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert report["hardware_touched"] is True
    assert [(case["name"], case["status"]) for case in report["cases"]] == [
        ("preflight", "PASS"), ("identify", "FAIL")
    ]
    assert [inv["arguments"][0] for inv in report["invocations"]] == ["identify", "identify"]
    assert "--simulate" in report["invocations"][0]["arguments"]
    assert "--live" in report["invocations"][1]["arguments"]
    assert all(inv["arguments"][0] == "identify" for inv in report["invocations"])


@requires_windows
def test_physical_model_spacing_passes_identity_gate(tmp_path: Path) -> None:
    # Real Tektronix instruments report "TBS 1052B" while the target profile
    # declares "TBS1052B"; the normalized token match must accept it.
    result, report = fake_run(
        tmp_path, TARGETS[2], live_model_name="TBS 1052B",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["preflight"]["status"] == "PASS"
    assert cases["identify"]["status"] == "PASS", cases["identify"]
    assert not [case for case in report["cases"] if case["status"] == "FAIL"]
    assert report["status"] == "passed"
    assert [inv["arguments"][0] for inv in report["invocations"]][:2] == [
        "identify", "identify"
    ]


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
    confirmation: str = "enter",
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
    screenshot_bytes = b"bad" if bad_bmp else (b"\x89PNG\r\n\x1a\nfake" if target == TARGETS[0] else b"BMfake")
    default_supported_operations = {
        TARGETS[0]: (
            "cursor-set", "sample-rate", "channel-label", "channel-probe-skew",
            "trigger-edge-level", "trigger-runt", "save-image-format",
            "save-waveform-format", "screenshot",
        ),
        TARGETS[1]: (
            "cursor-set", "trigger-tv", "save-image-ink-saver",
            "display-vectors", "screenshot", "display-persistence",
        ),
        TARGETS[2]: (
            "cursor-set", "trigger-tv", "save-image-ink-saver", "display-vectors",
            "display-persistence",
        ),
    }[target]
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
        "channel-label": {"text": "CH1"},
        "channel-probe-skew": {"probe_skew_seconds": 0.0},
        "timebase-scale": {"seconds_per_division": 0.001},
        "timebase-position": {"position_seconds": 0.0},
        "acquisition": {"type": "normal", "count": 16},
        "trigger-sweep": {"mode": "auto"},
        "trigger-mode": {"mode": mode, "raw_mode": mode},
        "trigger-runt": {"mode": mode, "channel": 1, "polarity": "positive",
                         "qualifier": "none", "low_level_volts": -0.1,
                         "high_level_volts": 0.1, "time_seconds": 1e-6},
        "trigger-tv": {"mode": mode, "source_channel": 1, "standard": "ntsc",
                       "tv_mode": "field1", "polarity": "positive", "line": None},
        "trigger-edge-source": {"source": "analog-channel", "source_channel": 1},
        "trigger-edge-slope": {"slope": "positive"},
        "trigger-edge-coupling": {"coupling": "dc"},
        "trigger-holdoff": {"seconds": 0.000001},
        "trigger-edge-level": {"level_volts": 0.0},
        "trigger-edge": {"source_channel": 1, "level_volts": 0.0, "slope": "positive"},
        "save-pwd": {"path": "C:/scope"},
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
        "def capabilities_for_model_id(model_id):\n"
        " return SimpleNamespace(supported_operations=frozenset(supported_operations), "
        "cursor_source_selection=cursor_source_selection, fixed_acquisition_memory_mode='realtime', "
        "acquisition_modes=acquisition_modes, average_counts=average_counts)\n",
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
        f" values[command] = {{'format': {'PNG' if target == TARGETS[0] else 'BMP'!r}, 'byte_count': Path(path).stat().st_size, 'image_path': path}}\n"
        f"print(json.dumps({{'ok': True, 'idn': {{'vendor': 'TEKTRONIX', 'model': '{model}'}}, "
        f"'capabilities': {{'analog_channels': {channels}, 'series': '{series}'}}, "
        "'result': values.get(command, {})}))\n",
        encoding="utf-8",
    )
    output_root = ROOT / ".tmp_tests" / "live_tektronix_check" / tmp_path.name
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    arguments = [
        "-Target", target, "-Connection", connection, "-Resource",
        "USB0::FAKE::INSTR" if connection == "usb" else "TCPIP0::example::INSTR",
        "-Python", sys.executable, "-OutputRoot", str(output_root), *extra,
    ]
    previous_runs = set(output_root.glob("run_*/private/report.json"))
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
            "screenshot_format": "PNG" if target == TARGETS[0] else "BMP",
            "arguments": arguments,
        }), encoding="utf-8")
    result = run_script(
        "-ScriptPath", str(SCRIPT), "-FixturePath", str(fixture),
        "-PythonPath", sys.executable, "-OutputRoot", str(output_root),
        "-OperatorConfirmation", confirmation,
        script=Path(__file__).with_name("tektronix_function_harness.ps1"), env=env,
    )
    runs = set(output_root.glob("run_*/private/report.json")) - previous_runs
    assert len(runs) == 1, result.stdout + result.stderr
    report = json.loads(runs.pop().read_text(encoding="utf-8"))
    assert not (tmp_path / "argv.jsonl").exists()
    counts = report["summary_counts"]
    assert counts["cases"] == len(report["cases"])
    assert counts["passed"] == sum(case["status"] == "PASS" for case in report["cases"])
    assert counts["failed"] == sum(case["status"] == "FAIL" for case in report["cases"])
    assert counts["na"] == sum(case["status"] == "N/A" for case in report["cases"])
    assert counts["invocations"] == len(report["invocations"])
    return result, report


CASE_STATUS_PATTERN = re.compile(r"^(PASS|FAIL|N/A)\s+\[live\]\[tektronix\] (\S+)\s*$")


def printed_case_details(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    """Return the console Detail printed for the first status line of each case.

    The trailing Summary reprints every case status without a Detail, so only the
    first occurrence of each case name carries the runner's Add-Case output.
    """
    lines = [line.rstrip() for line in result.stdout.splitlines()]
    printed: dict[str, str] = {}
    for index, line in enumerate(lines):
        match = CASE_STATUS_PATTERN.match(line)
        if match is None or match.group(2) in printed:
            continue
        detail: list[str] = []
        for candidate in lines[index + 1:]:
            if not candidate.strip():
                if detail:
                    break
                continue
            if not candidate.startswith(" "):
                break
            detail.append(candidate.strip())
        printed[match.group(2)] = " ".join(detail)
    return printed


@requires_windows
def test_fail_detail_is_printed_and_carries_cli_error_fields(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], "-IncludeConfigurationActions",
        cursor_error=("OscilloscopeError", "Cursor X setter failed"),
    )
    assert result.returncode != 0
    assert report["status"] == "failed"
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["cursor-set"]["status"] == "FAIL"

    detail = cases["cursor-set"]["detail"]
    # The CLI error type and message must survive instead of being masked by the
    # exit-code and artifact-path summary.
    assert "OscilloscopeError: Cursor X setter failed" in detail
    assert "exit 1" in detail and "timeout=False" in detail

    lines = [line.strip() for line in result.stdout.splitlines()]
    status_index = next(
        index for index, line in enumerate(lines)
        if line.startswith("FAIL") and "[live][tektronix] cursor-set" in line
    )
    assert lines[status_index + 1] == detail


@requires_windows
def test_math_state_outside_public_subset_is_na(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], math_error=("OscilloscopeError", "Unsupported Tek Math expression: 'FFT'"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["math-operator"]["status"] == "N/A"
    assert report["status"] == "passed"
    calls = [inv for inv in report["invocations"] if inv["arguments"][0] == "math-operator"]
    assert len(calls) == 1
    assert "--query" in calls[0]["arguments"]
    assert calls[0]["result"] == "N/A"


@requires_windows
def test_tbs2074_cursor_configuration_actions_cover_x_y_and_screen(tmp_path: Path) -> None:
    result, report = fake_run(tmp_path, TARGETS[0], "-IncludeConfigurationActions")
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["cursor-set"]["status"] == "PASS"
    assert cases["cursor-set-y"]["status"] == "PASS"
    assert cases["cursor-set-screen"]["status"] == "PASS"
    calls = [
        inv["arguments"]
        for inv in report["invocations"]
        if inv["arguments"][0] == "cursor" and "--query" not in inv["arguments"]
    ]
    assert any("--x1" in args and "--y1" not in args for args in calls)
    assert any("--y1" in args and "--x1" not in args for args in calls)
    assert any("--x1" in args and "--y1" in args for args in calls)
    assert any("--off" in args for args in calls)


@requires_windows
def test_tbs2074_cursor_failure_stops_later_cursor_mutations(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path,
        TARGETS[0],
        "-IncludeConfigurationActions",
        cursor_error=("OscilloscopeError", "Cursor X setter failed"),
    )
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["cursor-set"]["status"] == "FAIL"
    assert cases["cursor-set-y"]["status"] == "N/A"
    assert cases["cursor-set-screen"]["status"] == "N/A"
    setters = [
        inv["arguments"]
        for inv in report["invocations"]
        if inv["arguments"][0] == "cursor" and "--query" not in inv["arguments"]
    ]
    assert sum("--x1" in args for args in setters) == 1
    assert not any("--y1" in args for args in setters)


@requires_windows
def test_live_runner_rejects_stale_unsupported_operation_policy(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path,
        TARGETS[1],
        core_supported_operations=("sample-rate",),
    )
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["sample-rate"]["status"] == "FAIL"
    assert "runner drift" in cases["sample-rate"]["detail"].lower()
    assert report["status"] == "failed"


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
    assert report["status"] == "passed"
    calls = [inv for inv in report["invocations"] if inv["arguments"][0] == "cursor"]
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
    result, report = fake_run(
        tmp_path, TARGETS[1], "-IncludeConfigurationActions",
        subprocess_cli=command == "math-operator", **errors,
    )
    assert result.returncode != 0
    assert report["status"] == "failed"
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
    assert report["status"] == ("failed" if mismatch else "passed")
    assert report["summary_counts"]["failed"] == int(mismatch)
    calls = [inv["arguments"] for inv in report["invocations"] if inv["arguments"][0] == "display-vectors"]
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
        assert cases["display-vectors-query"]["status"] == "PASS"
        assert cases["display-vectors-on"]["status"] == "N/A"
    assert cases["timebase-position"]["status"] == "PASS"
    assert cases["trigger-mode"]["status"] == "PASS"
    for name in ("channel-units", "math-display", "math-operator",
                     "cursor-query", "trigger-edge", "trigger-edge-source", "trigger-edge-slope",
                     "trigger-edge-coupling", "acquisition-points", "record-length"):
        assert cases[name]["status"] == "PASS", cases[name]
    assert cases["display-persistence"]["status"] == (
        "N/A" if target == TARGETS[0] else "PASS"
    ), cases["display-persistence"]
    assert cases["autoscale"]["status"] == "N/A"
    assert cases["setup-save"]["status"] == "N/A"
    assert cases["final-standard-event"]["status"] == "PASS"
    assert report["invocations"][-1]["arguments"][0] == "system-standard-event"
    assert not [case for case in report["cases"] if case["status"] == "FAIL"]
    assert report["status"] == "passed"
    assert all(invocation["arguments"][0] not in {
        "autoscale", "setup-save", "run", "screenshot", "measure-install", "measure-clear", "save-image", "measure", "capture", "single-wait"
    }
               for invocation in report["invocations"])
    assert not any(inv["arguments"][0] == "cursor" and "--query" not in inv["arguments"]
                   for inv in report["invocations"])
    unsupported = ({"trigger-tv", "save-image-ink-saver", "display-vectors"}
                   if target == TARGETS[0] else
                   {"sample-rate", "channel-label", "channel-probe-skew",
                    "trigger-edge-level", "trigger-runt", "save-image-format", "save-waveform-format"})
    assert not unsupported.intersection(inv["arguments"][0] for inv in report["invocations"])
    commands = [inv["arguments"][0] for inv in report["invocations"]]
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
        if args[0].startswith("trigger-edge"):
            assert "--query" in args
        if args[0] == "trigger-mode" and "--mode" in args:
            assert args[args.index("--mode") + 1] == mode
        if args[0] == "trigger-runt" and "--query" not in args:
            assert "--time-seconds" not in args  # Unqualified runt preserves dormant width.


@requires_windows
@pytest.mark.parametrize("target", TARGETS)
def test_explicit_action_storage_and_screenshot_gates(tmp_path: Path, target: str) -> None:
    result, report = fake_run(
        tmp_path, target, "-IncludeConfigurationActions", "-IncludeAcquisitionActions",
        "-IncludeAutoscale", "-IncludeStorageWrites", "-SetupSlot", "1", "-ReferenceSlot", "1",
        "-ImageFilename", "acceptance.png", "-IncludeScreenshot",
        "-WaveformFilename", "wave.csv", "-WaveformSourceChannel", "2",
        subprocess_cli=target in TARGETS[:2],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    for name in ("cursor-off", "measure-install", "measure-clear", "run", "single", "force-trigger",
                 "stop-acquisition", "autoscale", "save-image", "save-waveform", "setup-save", "setup-recall",
                 "reference-save", "reference-display", "reference-query", "measure", "capture-byte", "single-wait-natural", "single-wait-force"):
        assert cases[name]["status"] == "PASS", cases[name]
    assert cases["cursor-set"]["status"] == "PASS"
    assert cases["screenshot-bmp"]["status"] == ("PASS" if target == TARGETS[1] else "N/A")
    if target == TARGETS[0]:
        assert cases["cursor-set-y"]["status"] == "PASS"
        assert cases["cursor-set-screen"]["status"] == "PASS"
        assert cases["screenshot-png"]["status"] == "PASS"
    save = next(inv for inv in report["invocations"] if inv["arguments"][0] == "save-waveform")
    assert "--source-channel" in save["arguments"]
    assert "Stop command succeeded; native status clean" in " ".join(report["diagnostics"]["acquisition-final-state"])
    assert cases["capture-hidden-channel"]["status"] == "N/A"


@requires_windows
@pytest.mark.parametrize(("status_command", "expected_failure"), [
    ("run", "run"),
    ("stop-acquisition", "stop-acquisition"),
])
def test_acquisition_rejects_dirty_native_status_and_attempts_stop(
    tmp_path: Path, status_command: str, expected_failure: str,
) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], "-IncludeAcquisitionActions",
        native_status_command=status_command, native_status_value=4, native_status_raw="4",
    )
    assert result.returncode != 0
    assert report["status"] == "failed"
    cases = {case["name"]: case for case in report["cases"]}
    assert cases[expected_failure]["status"] == "FAIL"
    commands = [inv["arguments"][0] for inv in report["invocations"]]
    assert commands.count("run") == 1
    assert commands.count("stop-acquisition") == 1
    assert commands.index("stop-acquisition") > commands.index("run")
    assert cases["stop-acquisition"]["status"] == ("FAIL" if expected_failure == "stop-acquisition" else "PASS")


@requires_windows
def test_private_and_shareable_reports_keep_common_schema(tmp_path: Path) -> None:
    result, private_report = fake_run(tmp_path, TARGETS[0])
    assert result.returncode == 0, result.stdout + result.stderr
    run_dir = ROOT / private_report["run_root"]
    private_path = run_dir / "private" / "report.json"
    shareable_path = run_dir / "shareable" / "report.json"
    assert private_path.is_file()
    assert shareable_path.is_file()
    shared_report = json.loads(shareable_path.read_text(encoding="utf-8"))
    assert private_report["status"] == shared_report["status"] == "passed"
    assert private_report["summary_counts"] == shared_report["summary_counts"]
    assert shared_report["resource"] == "<redacted-resource>"
    assert "USB0::FAKE::INSTR" not in shareable_path.read_text(encoding="utf-8")


@requires_windows
@pytest.mark.parametrize("target", TARGETS)
def test_workflow_simulator_happy_path_uses_core_identity(tmp_path: Path, target: str) -> None:
    result, report = fake_workflow_run(tmp_path, target, "happy")
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["status"] == "passed"
    cases = {case["name"]: case for case in report["cases"]}
    for name in (
        "preflight", "identity", "target-model-match", "acquisition-precondition",
        "measure-sweep", "measure-log", "measure-until", "measure-until-timeout",
        "capture-batch", "capture-until", "capture-monitor", "triggered-measure-loop",
        "triggered-capture-series", "sequence", "cleanup",
    ):
        assert cases[name]["status"] == "PASS", cases[name]
    sweep = next(inv for inv in report["invocations"] if inv["stage"] == "measure-sweep")
    sweep_items = sweep["arguments"][sweep["arguments"].index("--items") + 1].split(",")
    if target == TARGETS[1]:
        assert "vrms" not in sweep_items
    assert all("--live" not in inv["arguments"] for inv in report["invocations"])

    timeout = next(inv for inv in report["invocations"] if inv["stage"] == "measure-until-timeout")
    timeout_payload = json.loads((ROOT / timeout["json"]).read_text(encoding="utf-8"))
    status = timeout_payload["result"]["post_command_status"]
    assert status["source"] == "tektronix-sesr"
    assert status["complete"] is True
    assert status["is_error"] is False
    assert status["destructive_read"] is True
    assert status["value"] == 0
    assert status["raw"]


@requires_windows
def test_workflow_run_failure_still_stops_acquisition(tmp_path: Path) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[0], "dirty-run")
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["acquisition-precondition"]["status"] == "FAIL"
    assert "native command status" in cases["acquisition-precondition"]["detail"]
    assert cases["cleanup"]["status"] == "PASS"
    stages = [inv["stage"] for inv in report["invocations"]]
    assert stages.index("acquisition-precondition-run") < stages.index("cleanup-acquisition-stop-acquisition")


@requires_windows
def test_expected_timeout_still_rejects_dirty_native_status(tmp_path: Path) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[0], "dirty-timeout")
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["measure-until-timeout"]["status"] == "FAIL"
    assert "native command status" in cases["measure-until-timeout"]["detail"]
    assert cases["cleanup"]["status"] == "PASS"


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
    assert invocations[attempted + 1]["arguments"][0] == "channel-display"
    assert "--query" in invocations[attempted + 1]["arguments"]
    for invocation in invocations:
        if invocation["arguments"][0] == "channel-display" and "2" in invocation["arguments"]:
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
    assert not {"screenshot", "save-image"}.intersection(inv["arguments"][0] for inv in report["invocations"])


@requires_windows
@pytest.mark.parametrize("failure", ("mode", "bmp"))
def test_failed_readback_or_artifact_reports_fail(tmp_path: Path, failure: str) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[1], "-IncludeScreenshot",
        mismatch=failure == "mode", bad_bmp=failure == "bmp",
    )
    assert result.returncode != 0
    assert report["status"] == "failed"
    assert report["summary_counts"]["failed"] == 1
    cases = {case["name"]: case for case in report["cases"]}
    failed_case = {"mode": "trigger-mode", "bmp": "screenshot-bmp"}[failure]
    assert cases[failed_case]["status"] == "FAIL"
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
    assert "[string]$Identity.idn.vendor" in VALIDATION_HELPERS_TEXT
    # The physical model is read through the StrictMode-safe accessor and matched
    # by normalized token, so a real "TBS 1052B" still matches the TBS1052B target.
    assert 'PSObject.Properties["model"]' in VALIDATION_HELPERS_TEXT
    assert "Get-NormalizedModelToken -Value $detected" in VALIDATION_HELPERS_TEXT
    assert "[int]$Identity.capabilities.analog_channels" in VALIDATION_HELPERS_TEXT
    assert 'Invoke-Cli -Stage "display-vectors-query"' in TEXT
    assert "if ($isOn -is [bool] -and $isOn)" in TEXT
    assert "no public OFF setter" in TEXT


@requires_windows
def test_pulse_width_roundtrip_preserves_current_glitch_mode(tmp_path):
    result, report = fake_run(tmp_path, TARGETS[0], mode="glitch")
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["trigger-pulse-width"]["status"] == "PASS"
    calls = [inv["arguments"] for inv in report["invocations"] if inv["arguments"][0] == "trigger-pulse-width"]
    assert len(calls) == 3  # Query, same-value set, and readback preserve the current settings.
    assert all("range" not in call for call in calls)


@requires_windows
@pytest.mark.parametrize("arguments", [
    ["-WaveformFilename", "wave.csv", "-WaveformSourceChannel", "1"],
    ["-IncludeStorageWrites", "-SetupSlot", "1", "-ReferenceSlot", "1", "-WaveformFilename", "bad;file.csv", "-WaveformSourceChannel", "1"],
    ["-IncludeStorageWrites", "-SetupSlot", "1", "-ReferenceSlot", "1", "-WaveformFilename", "wave.csv", "-WaveformSourceChannel", "3"],
])
def test_waveform_storage_inputs_rejected_before_identity(arguments):
    result = run_script("-Target", TARGETS[2], "-Connection", "usb", "-Resource", "USB0::FAKE::INSTR", *arguments)
    assert result.returncode != 0
    assert "require" in result.stderr.lower()


@requires_windows
@pytest.mark.parametrize(("target", "mode"), [
    (TARGETS[0], "edge"),
    (TARGETS[0], "runt"),
    (TARGETS[0], "glitch"),
    (TARGETS[1], "tv"),
    (TARGETS[2], "edge"),
])
def test_generated_arguments_match_parser_contract(tmp_path: Path, target: str, mode: str) -> None:
    from scopes_tool_cli.parser import _build_parser

    result, report = fake_run(
        tmp_path, target, "-IncludeConfigurationActions", "-IncludeAcquisitionActions",
        "-IncludeAutoscale", "-IncludeStorageWrites", "-SetupSlot", "1", "-ReferenceSlot", "1",
        "-ImageFilename", "acceptance.png", "-IncludeScreenshot",
        "-WaveformFilename", "wave.csv", "-WaveformSourceChannel", "2",
        mode=mode, vectors_on=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # Build once in pytest, not in every fake child CLI process.
    parser = _build_parser()
    arguments = {tuple(inv["arguments"]) for inv in report["invocations"]}
    assert arguments
    for argv in sorted(arguments):
        parsed = parser.parse_args(argv)
        assert parsed.command == argv[0]
        assert parsed.json_output is True
        if parsed.simulate:
            assert parsed.model == target
            assert parsed.resource is None
            assert parsed.live is False
        else:
            assert parsed.live is True
            assert parsed.resource == "USB0::FAKE::INSTR"
            assert "--model" not in argv


@requires_windows
def test_non_blank_detail_is_printed_for_pass_na_and_fail(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], "-IncludeConfigurationActions",
        cursor_error=("OscilloscopeError", "Cursor X setter failed"),
    )
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    printed = printed_case_details(result)

    # PASS, N/A and FAIL must all surface a non-blank Detail in the console, and
    # the console Detail must stay identical to the reported Detail.
    assert printed["preflight"] == cases["preflight"]["detail"]
    assert printed["preflight"] == "Selected model CLI simulation; no hardware accessed"
    assert printed["channel-units"] == cases["channel-units"]["detail"]
    assert printed["channel-units"] == "query, same-value set, and readback"
    assert printed["autoscale"] == cases["autoscale"]["detail"]
    assert printed["autoscale"] == "Requires -IncludeAutoscale"
    assert cases["autoscale"]["status"] == "N/A"
    assert printed["cursor-set"] == cases["cursor-set"]["detail"]
    assert cases["cursor-set"]["status"] == "FAIL"
    assert "OscilloscopeError: Cursor X setter failed" in printed["cursor-set"]

    # A blank Detail must not produce a stray detail line.
    for name, case in cases.items():
        if case["detail"]:
            assert printed.get(name), name
        else:
            assert name not in printed or printed[name] == "", name


CONFIRMATION_SECTIONS = (
    "PRE-VALIDATION",
    "PHYSICAL PREPARATION",
    "DEFAULT VALIDATION ACTIONS",
    "STATE / CLEANUP LIMITATIONS",
    "OPTIONAL ACTIONS",
)
CONFIRMATION_PROMPT = (
    "Press Enter only after reviewing the information above.",
    "Any other input cancels validation.",
    "Ctrl+C to abort.",
)
NOT_REQUESTED = "Not requested."


@requires_windows
def test_operator_confirmation_enter_runs_every_case_and_reports_pass(tmp_path: Path) -> None:
    # An explicit empty Enter is the only input that may continue.
    result, report = fake_run(tmp_path, TARGETS[2], live_model_name="TBS 1052B")
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["status"] == "passed"

    for banner in (
        "Scopes Tool Tektronix Live Validation",
        "Detected instrument: TBS 1052B",
        "Target: tektronix-tbs1052b",
        "Connection: usb",
        *CONFIRMATION_SECTIONS,
        "Hardware-free preflight passed.",
        "Live instrument identity matches the selected target.",
        "Disconnect unknown or sensitive DUT signals",
        "Default checks use the instrument's current state; a fixed CH1/CH2 Probe Comp fixture is not required.",
        "that read is destructive and clears it.",
        "Perform supported same-value setters",
        "Same-value setters are real instrument writes, not read-only checks.",
        "Not every setting is guaranteed to be fully restored.",
        *CONFIRMATION_PROMPT,
    ):
        assert banner in result.stdout, banner

    # The screen must be printed before the first system command runs.
    assert result.stdout.index("Scopes Tool Tektronix Live Validation") < result.stdout.index(
        "PASS  [live][tektronix] system-status-byte"
    )
    # Sections stay in the documented order.
    positions = [result.stdout.index(section) for section in CONFIRMATION_SECTIONS]
    assert positions == sorted(positions)

    cases = {case["name"]: case for case in report["cases"]}
    assert cases["operator-confirmation"]["status"] == "PASS"
    commands = [inv["arguments"][0] for inv in report["invocations"]]
    assert commands[:2] == ["identify", "identify"]
    assert commands.index("system-status-byte") > 1
    assert commands[-1] == "system-standard-event"
    assert cases["system-status-byte"]["status"] == "PASS"
    assert cases["final-standard-event"]["status"] == "PASS"

    assert "\nSummary\n" in result.stdout
    counts = report["summary_counts"]
    totals = re.search(r"Totals: (\d+) PASS / (\d+) FAIL / (\d+) N/A", result.stdout)
    assert totals is not None, result.stdout[-2000:]
    assert (int(totals.group(1)), int(totals.group(2)), int(totals.group(3))) == (
        counts["passed"], counts["failed"], counts["na"],
    )
    assert result.stdout.rstrip().endswith("PASS  [live][tektronix] baseline live validation")

    # No optional action was requested, so none may be described as planned.
    for action in ("Acquisition", "Autoscale", "Configuration", "Storage Writes", "Screenshot"):
        assert f"- {action}: {NOT_REQUESTED}" in result.stdout, action
    # Without -IncludeConfigurationActions or -IncludeStorageWrites the default
    # screen must not demand a CH1 fixture or writable instrument storage.
    for absent in (
        "Probe Comp / Demo output",
        "Measurement and capture checks require CH1 to be displayed.",
        "Reference Save requires CH1 display ON",
        "Confirm the required instrument storage is available and writable",
    ):
        assert absent not in result.stdout, absent


@requires_windows
def test_operator_confirmation_warnings_follow_enabled_options(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], "-IncludeAcquisitionActions", "-IncludeAutoscale",
        "-IncludeConfigurationActions", "-IncludeStorageWrites",
        "-SetupSlot", "1", "-ReferenceSlot", "2", "-IncludeScreenshot",
        "-ImageFilename", "acceptance.png", "-WaveformFilename", "wave.csv",
        "-WaveformSourceChannel", "2",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for expected in (
        # Physical preparation gains the configuration and storage requirements.
        "Connect a suitable, stable signal to CH1 (for example, the oscilloscope's Probe Comp / Demo output).",
        "Ensure CH1 display is ON and a stable waveform is visible. Measurement and capture checks require CH1 to be displayed.",
        "Reference Save requires CH1 display ON; otherwise the reference-save case is N/A.",
        "Confirm the required instrument storage is available and writable before saving files.",
        # Optional notes are specific to the options actually enabled.
        "Acquisition: Run/Stop state changes",
        "Autoscale: Changes multiple front-panel settings and is not restored.",
        "Configuration: Runs measurement, BYTE waveform capture, and cursor actions. "
        "Cursor mode may end OFF, measurement configuration may end cleared, "
        "and waveform transfer settings are not restored. "
        "TBS2074 cursor source selection may display CH1 or restart acquisition through Core.",
        # Storage slots and filenames come from the arguments, not from constants.
        "Storage Writes: Setup slot 1 and reference slot 2 may be overwritten.",
        "Requested instrument image file 'acceptance.png' may be overwritten.",
        "Requested instrument waveform file 'wave.csv' may be overwritten.",
        # TBS2074 PNG capture is the supported screenshot path.
        "Screenshot: PNG screenshot; Core writes a temporary instrument file and attempts to delete it during cleanup.",
    ):
        assert expected in result.stdout, expected
    assert f"- Storage Writes: {NOT_REQUESTED}" not in result.stdout


@requires_windows
@pytest.mark.parametrize(("target", "expected"), [
    # TBS2074 supports a PNG screenshot written through a temporary instrument
    # file; TDS2024B only over USBTMC; TBS1052B supports no screenshot format at
    # all, so -IncludeScreenshot must not promise a screenshot file.
    (TARGETS[0], "Screenshot: PNG screenshot; Core writes a temporary instrument file and attempts to delete it during cleanup."),
    (TARGETS[1], "Screenshot: BMP screenshot is attempted only with a USBTMC instrument resource; otherwise this case is N/A."),
    (TARGETS[2], "Screenshot: No screenshot format is supported on this model; no screenshot file is written."),
])
def test_operator_confirmation_screenshot_note_matches_model_support(
    tmp_path: Path, target: str, expected: str,
) -> None:
    result, report = fake_run(tmp_path, target, "-IncludeScreenshot")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"- {expected}" in result.stdout, expected


@requires_windows
@pytest.mark.parametrize("confirmation,reason", [
    # Any non-empty input, whitespace-only input, or a null result must fail
    # closed exactly like a declined prompt.
    ("decline", "only an explicit empty Enter continues"),
    ("whitespace", "only an explicit empty Enter continues"),
    ("null", "only an explicit empty Enter continues"),
    ("unavailable", "could not be read"),
])
def test_operator_confirmation_blocks_all_later_commands(
    tmp_path: Path, confirmation: str, reason: str,
) -> None:
    result, report = fake_run(tmp_path, TARGETS[0], confirmation=confirmation)
    assert result.returncode != 0
    assert report["status"] == "failed"
    # Live identify already ran, so hardware access must not be denied.
    assert report["hardware_touched"] is True

    cases = {case["name"]: case for case in report["cases"]}
    assert cases["operator-confirmation"]["status"] == "FAIL"
    assert reason in cases["operator-confirmation"]["detail"]
    assert reason in printed_case_details(result)["operator-confirmation"]
    assert cases["preflight"]["status"] == "PASS"
    assert cases["identify"]["status"] == "PASS"

    commands = [inv["arguments"][0] for inv in report["invocations"]]
    assert commands == ["identify", "identify"]
    assert not {"system-status-byte", "system-standard-event",
                "system-clear-status", "system-opc"} & set(commands)

    counts = report["summary_counts"]
    assert counts["failed"] == 1
    assert counts["passed"] >= 2
    totals = re.search(r"Totals: (\d+) PASS / (\d+) FAIL / (\d+) N/A", result.stdout)
    assert totals is not None, result.stdout[-2000:]
    assert (int(totals.group(1)), int(totals.group(2))) == (counts["passed"], counts["failed"])
    assert "FAIL  [live][tektronix] baseline live validation" in result.stdout
    assert result.stdout.rstrip().endswith("FAIL  [live][tektronix] baseline live validation")
    assert "PASS  [live][tektronix] baseline live validation" not in result.stdout
