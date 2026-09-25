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
        "-Python", sys.executable, "-OutputRoot", str(output_root), env=env,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    runs = sorted(output_root.glob("run_*/private/report.json"), key=lambda path: path.stat().st_mtime)
    assert runs
    report = json.loads(runs[-1].read_text(encoding="utf-8"))
    assert report["hardware_touched"] is True  # Stub process attempted; no instrument opened.
    assert [(case["name"], case["status"]) for case in report["cases"]] == [("identify", "FAIL")]
    assert len(report["invocations"]) == 1
    assert report["invocations"][0]["arguments"][2] == "identify"


@requires_windows
@pytest.mark.parametrize(
    ("target", "model", "channels", "series", "vectors"),
    [
        (TARGETS[0], "TBS2074B", 4, "TBS2000B", True),
        (TARGETS[1], "TDS2024B", 4, "TDS2000B", False),
        (TARGETS[2], "TBS1052B", 2, "TBS1000B", False),
    ],
)
def test_default_case_flow_with_fake_cli(
    tmp_path: Path, target: str, model: str, channels: int, series: str, vectors: bool
) -> None:
    stub = tmp_path / "scopes_tool_cli"
    stub.mkdir()
    (stub / "__init__.py").write_text("", encoding="utf-8")
    (stub / "cli.py").write_text(
        "import json, sys\n"
        "command = sys.argv[1]\n"
        "values = {\n"
        " 'system-standard-event': {'value': 0},\n"
        " 'channel-display': {'display': True},\n"
        " 'channel-scale': {'volts_per_division': 1.0},\n"
        " 'channel-coupling': {'coupling': 'dc'},\n"
        " 'channel-probe': {'probe_ratio': 10.0},\n"
        " 'channel-bandwidth-limit': {'bandwidth_limit': False},\n"
        " 'channel-invert': {'invert': False},\n"
        " 'channel-offset': {'volts': 0.0},\n"
        " 'channel-label': {'text': 'CH1'},\n"
        " 'channel-probe-skew': {'probe_skew_seconds': 0.0},\n"
        " 'timebase-scale': {'seconds_per_division': 0.001},\n"
        " 'timebase-position': {'position_seconds': 0.0},\n"
        " 'acquisition': {'type': 'normal', 'count': 16},\n"
        " 'trigger-sweep': {'mode': 'auto'},\n"
        " 'trigger-edge-source': {'source': 'analog-channel', 'source_channel': 1},\n"
        " 'trigger-edge-slope': {'slope': 'positive'},\n"
        " 'trigger-edge-coupling': {'coupling': 'dc'},\n"
        " 'trigger-holdoff': {'seconds': 0.000001},\n"
        " 'trigger-edge-level': {'level_volts': 0.0},\n"
        " 'trigger-edge': {'source_channel': 1, 'level_volts': 0.0, 'slope': 'positive'},\n"
        " 'save-pwd': {'path': 'C:/scope'},\n"
        f" 'display-vectors': {{'value': {vectors}}},\n"
        "}\n"
        f"print(json.dumps({{'ok': True, 'idn': {{'vendor': 'TEKTRONIX', 'model': '{model}'}}, "
        f"'capabilities': {{'analog_channels': {channels}, 'series': '{series}'}}, "
        "'result': values.get(command, {})}))\n",
        encoding="utf-8",
    )
    output_root = ROOT / ".tmp_tests" / "live_tektronix_check" / f"tooling_default_{model.lower()}"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    result = run_script(
        "-Target", target, "-Connection", "usb", "-Resource", "USB0::FAKE::INSTR",
        "-Python", sys.executable, "-OutputRoot", str(output_root), env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    runs = sorted(output_root.glob("run_*/private/report.json"), key=lambda path: path.stat().st_mtime)
    assert runs
    report = json.loads(runs[-1].read_text(encoding="utf-8"))
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
    assert cases["trigger-mode"]["status"] == "N/A"
    assert cases["autoscale"]["status"] == "N/A"
    assert cases["setup-save"]["status"] == "N/A"
    assert not [case for case in report["cases"] if case["status"] == "FAIL"]
    assert report["status"] == "pass"
    assert all(invocation["arguments"][2] not in {"autoscale", "setup-save", "run"}
               for invocation in report["invocations"])


def test_runner_uses_only_public_cli_and_default_options_are_off() -> None:
    commands = re.findall(r'-Command\s+"([a-z][a-z0-9-]+)"', TEXT)
    assert commands
    assert not set(commands) & {
        "check-error", "capture", "measure", "screenshot", "single-wait",
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
