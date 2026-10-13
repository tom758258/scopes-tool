"""Focused hardware-free validation of the standalone Auto runner."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

import pytest

from scopes_tool_cli.parser import _build_parser
from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.identity import physical_model_for_id
from tests.tooling._live_script_test_support import REPO_ROOT


SCRIPT = REPO_ROOT / "scripts/live-autoscale-check.ps1"
HARNESS = Path(__file__).with_name("autoscale_function_harness.ps1")
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")
requires_powershell = pytest.mark.skipif(not POWERSHELL, reason="requires PowerShell")
TARGETS = (
    "keysight-dsox2004a", "keysight-dsox3024a", "keysight-dsox4024a", "keysight-dsox4034a",
    "tektronix-tbs2074", "tektronix-tds2024b", "tektronix-tbs1052b",
)
PAIRS = [(target, "usb") for target in TARGETS] + [(target, "tcpip") for target in TARGETS[2:4]]


def ps_run(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # PowerShell on Unix must not create its cache/config in the user's home.
    if os.name != "nt":
        for key, leaf in (("XDG_CACHE_HOME", "cache"), ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data")):
            env[key] = str(REPO_ROOT / ".tmp_tests/autoscale_powershell" / leaf)
    return subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(path), *args],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False, timeout=90,
    )


def fake_run(tmp_path: Path, target: str = TARGETS[3], *, connection: str = "usb", scenario: str = "success",
             confirmation: str = "enter", mismatch: bool = False, debug: bool = False,
             real_preflight: bool = False, real_settings: bool = False, real_auto: bool = False,
             trigger_mode: str = "edge", acquisition_type: str = "average", backend: str = ""):
    caps = capabilities_for_model_id(target)
    tek = target.startswith("tektronix-")
    vendor = "TEKTRONIX" if tek else "KEYSIGHT TECHNOLOGIES"
    model = physical_model_for_id(target).canonical_model
    serial = "PRIVATE-SERIAL-123456"
    idn = {"vendor": vendor, "model": model, "serial": serial, "raw": f"{vendor},{model},{serial},1.0"}
    state = {}
    for channel in range(1, caps.analog_channels + 1):
        for command, field, value in (
            ("channel-display", "display", channel % 2 == 1), ("channel-scale", "volts_per_division", channel * 0.2),
            ("channel-offset", "volts", channel * -0.1), ("channel-probe", "probe_ratio", 10.0),
            ("channel-coupling", "coupling", "dc"), ("trigger-edge-level", "level_volts", channel * -0.01),
        ):
            state[f"{command}:{channel}"] = {field: value}
    state.update({
        "timebase-scale:": {"seconds_per_division": 0.001}, "timebase-reference:": {"reference": "center"},
        "timebase-position:": {"position_seconds": -0.001}, "trigger-holdoff:": {"seconds": 0.000001},
        "trigger-mode:": {"mode": trigger_mode}, "trigger-edge-source:": {"source": "analog-channel", "source_channel": 2},
        "trigger-edge-slope:": {"slope": "negative"}, "acquisition:": {"type": acquisition_type, "count": 16},
    })
    resource = "USB0::0x0957::0x1234::PRIVATE-SERIAL-123456::INSTR" if connection == "usb" else "TCPIP0::private-scope.example::inst0::INSTR"
    fixture = {
        "target": target, "connection": connection, "resource": resource, "tektronix": tek,
        "idn": idn, "live_idn": {**idn, "model": "TBS1052B" if not tek else "DSOX2004A"} if mismatch else idn,
        "capabilities": {"analog_channels": caps.analog_channels, "series": caps.series},
        "state": state, "scenario": scenario, "confirmation": confirmation, "debug": debug, "backend": backend,
    }
    fixture_path = tmp_path / "auto-fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    output = REPO_ROOT / ".tmp_tests/autoscale_pytest" / uuid.uuid4().hex
    result = ps_run(HARNESS, "-ScriptPath", str(SCRIPT), "-FixturePath", str(fixture_path), "-PythonPath", sys.executable,
                    "-OutputRoot", str(output), *(["-RealPreflight"] if real_preflight else []),
                    *(["-RealSettings"] if real_settings else []), *(["-RealAuto"] if real_auto else []))
    runs = list(output.glob("run_*"))
    assert len(runs) == 1, result.stdout + result.stderr
    report_path = runs[0] / ("private" if debug else "shareable") / "report.json"
    assert report_path.exists(), result.stdout + result.stderr
    return result, json.loads(report_path.read_text(encoding="utf-8")), runs[0]


def cases(report):
    return {case["name"]: case for case in report["cases"]}


@requires_powershell
@pytest.mark.parametrize(("target", "connection"), PAIRS)
def test_registered_model_transport_flow_and_restore(tmp_path: Path, target: str, connection: str) -> None:
    result, report, _ = fake_run(tmp_path, target, connection=connection)
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["kind"] == "scopes-tool-live-autoscale-check"
    assert report["status"] == "passed"
    c = cases(report)
    auto = next(inv for inv in report["invocations"] if inv["stage"] == "auto")
    before = report["invocations"][:report["invocations"].index(auto)]
    assert all("--resource" not in inv["arguments"] for inv in before[:3])
    assert before[3]["stage"] == "identify"
    assert c["auto-basic"]["status"] == "PASS"
    if target.startswith("tektronix-"):
        assert auto["result"]["commands"] == ["AUTOSet EXECute"]
        assert "--source-channel" not in auto["arguments"]
        assert "auto-ch1" not in c
        assert c["restore"]["status"] == "N/A"
        assert not any(inv["stage"].startswith(("restore-", "snapshot-")) for inv in report["invocations"])
        assert "automatic restore is NOT attempted" in result.stdout
    else:
        assert auto["result"]["commands"] == [":AUToscale CHANnel1"]
        assert c["auto-ch1"]["status"] == "PASS"
        assert c["restore"]["status"] == "PASS"
        for channel in range(1, 5):
            for kind in ("display", "coupling", "probe", "scale", "offset"):
                assert any(inv["stage"] == f"readback-ch{channel}-channel-{kind}" for inv in report["invocations"])
        assert "partial coverage only" in c["restore"]["detail"]
    assert ("Please Select" in result.stdout) == (target == TARGETS[3])
    for note in ("Auto Scale is run directly from the front panel", "not a Scopes Tool SAVE failure",
                 "Reselect the USB destination"):
        assert (note in result.stdout) == (target == TARGETS[3])
    totals = report["summary_counts"]
    assert totals["cases"] == len(c)
    for status, key in (("PASS", "passed"), ("FAIL", "failed"), ("N/A", "na")):
        assert totals[key] == sum(case["status"] == status for case in c.values())
    assert f"Totals: {totals['passed']} PASS / {totals['failed']} FAIL / {totals['na']} N/A" in result.stdout
    parser = _build_parser()
    for inv in report["invocations"]:
        # Parse original option values without relying on redacted resource text.
        parser.parse_args(inv["arguments"])
    assert all("--acquire-mode" not in inv["arguments"] and "--channels" not in inv["arguments"] for inv in report["invocations"])
    for token in ("Detected instrument", "Target:", "Connection:", "CH1", "attenuation", "sensitive DUT",
                  "low-frequency", "weak", "narrow-pulse", "unstable", "enable/disable", "scale/offset",
                  "timebase/delay", "trigger", "acquisition", "cursor", "measurement", "Math", "Reference",
                  "Error/event", "Enter", "cancels"):
        assert token in result.stdout
    assert "A PASS result confirms Auto command execution and status checks" in result.stdout
    assert "does not prove optimal waveform scaling or signal recognition" in result.stdout


@requires_powershell
@pytest.mark.parametrize("target", TARGETS)
def test_real_preflight_and_simulated_auto_never_open_hardware(tmp_path: Path, target: str) -> None:
    result, report, _ = fake_run(tmp_path, target, real_preflight=True, real_auto=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert cases(report)["preflight"]["status"] == "PASS"
    assert cases(report)["auto-basic"]["status"] == "PASS"
    assert [inv["stage"] for inv in report["invocations"]][:4] == [
        "preflight-identify", "preflight-auto-dry-run", "preflight-auto-simulate", "identify",
    ]
    for inv in report["invocations"][:3]:
        assert "--resource" not in inv["arguments"]
        assert "--dry-run" in inv["arguments"] or "--simulate" in inv["arguments"]
    assert report["invocations"][1]["scpi"]["sent"] == []


@requires_powershell
@pytest.mark.parametrize("confirmation", ["decline", "whitespace", "null", "unavailable"])
def test_confirmation_fails_closed_before_status_or_state_changes(tmp_path: Path, confirmation: str) -> None:
    result, report, _ = fake_run(tmp_path, confirmation=confirmation)
    assert result.returncode == 1
    assert cases(report)["operator-confirmation"]["status"] == "FAIL"
    assert [inv["stage"] for inv in report["invocations"]][-1] == "identify"
    assert cases(report)["restore"]["status"] == "N/A"


@requires_powershell
@pytest.mark.parametrize("target", [TARGETS[0], TARGETS[4]])
def test_identity_mismatch_blocks_auto_and_prompt(tmp_path: Path, target: str) -> None:
    result, report, _ = fake_run(tmp_path, target, mismatch=True)
    assert result.returncode == 1
    assert cases(report)["identify"]["status"] == "FAIL"
    assert "operator-confirmation" not in cases(report)
    assert "PHYSICAL SETUP" not in result.stdout
    assert len(report["invocations"]) == 4


@requires_powershell
@pytest.mark.parametrize("scenario", ["fallback", "unmarked-fallback", "fallback-failure"])
def test_fallback_cannot_pass_ch1(tmp_path: Path, scenario: str) -> None:
    result, report, _ = fake_run(tmp_path, scenario=scenario)
    assert cases(report)["auto-ch1"]["status"] != "PASS"
    assert cases(report)["restore"]["status"] == "PASS"
    expected = "FAIL" if scenario == "fallback-failure" else "PASS"
    assert cases(report)["auto-basic"]["status"] == expected
    assert result.returncode == (1 if expected == "FAIL" else 0)
    assert ":AUToscale" in " ".join(report["diagnostics"]["auto"])


@requires_powershell
@pytest.mark.parametrize("scenario", ["auto-failure", "missing-scpi", "invalid-json", "dirty-status", "unterminated-queue"])
def test_auto_failures_attempt_restore_and_remain_failed(tmp_path: Path, scenario: str) -> None:
    result, report, _ = fake_run(tmp_path, scenario=scenario)
    assert result.returncode == 1
    assert cases(report)["auto-basic"]["status"] == "FAIL"
    assert cases(report)["auto-ch1"]["status"] == "FAIL"
    assert cases(report)["restore"]["status"] == "PASS"
    assert any(inv["stage"] == "readback-ch4-channel-display" for inv in report["invocations"])


@requires_powershell
@pytest.mark.parametrize("scenario", ["restore-failure", "readback-failure", "restore-status-failure"])
def test_restore_failure_is_visible_and_other_steps_continue(tmp_path: Path, scenario: str) -> None:
    result, report, _ = fake_run(tmp_path, scenario=scenario)
    assert result.returncode == 1
    assert cases(report)["auto-basic"]["status"] == "PASS"
    assert cases(report)["restore"]["status"] == "FAIL"
    assert report["status"] == "failed"
    assert any(inv["stage"] == "readback-trigger-mode" for inv in report["invocations"])
    assert "FAIL" in result.stdout
    assert any(inv["stage"] == "post-restore-status" for inv in report["invocations"])


@requires_powershell
def test_auto_and_restore_failures_are_both_preserved(tmp_path: Path) -> None:
    result, report, _ = fake_run(tmp_path, scenario="auto-and-restore-failure")
    assert result.returncode == 1
    assert cases(report)["auto-basic"]["status"] == "FAIL"
    assert "Auto command rejected" in cases(report)["auto-basic"]["detail"]
    assert cases(report)["restore"]["status"] == "FAIL"
    assert "ch2-channel-scale" in cases(report)["restore"]["detail"]


@requires_powershell
def test_pyvisa_backend_uses_shared_connection_arguments(tmp_path: Path) -> None:
    result, report, _ = fake_run(tmp_path, backend="@py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["backend"] == "pyvisa_py"
    for inv in report["invocations"]:
        if "--resource" in inv["arguments"]:
            index = inv["arguments"].index("--visa-library")
            assert inv["arguments"][index + 1] == "@py"


@requires_powershell
def test_failed_snapshot_prevents_auto(tmp_path: Path) -> None:
    result, report, _ = fake_run(tmp_path, scenario="snapshot-failure")
    assert result.returncode == 1
    assert cases(report)["snapshot"]["status"] == "FAIL"
    assert not any(inv["stage"] == "auto" for inv in report["invocations"])
    assert cases(report)["restore"]["status"] == "N/A"


@requires_powershell
def test_snapshot_restore_uses_real_public_simulated_cli(tmp_path: Path) -> None:
    result, report, _ = fake_run(tmp_path, TARGETS[0], real_settings=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert cases(report)["snapshot"]["status"] == "PASS"
    assert cases(report)["restore"]["status"] == "PASS"
    for inv in report["invocations"]:
        if inv["stage"].startswith(("snapshot-", "restore-", "readback-")):
            assert inv["scpi"]["sent"]


@requires_powershell
def test_non_edge_and_inactive_average_are_explicit_limits(tmp_path: Path) -> None:
    result, report, _ = fake_run(tmp_path, trigger_mode="glitch", acquisition_type="normal")
    assert result.returncode == 0, result.stdout + result.stderr
    assert cases(report)["restore"]["status"] == "PASS"
    assert not any(inv["arguments"][0].startswith("trigger-edge") for inv in report["invocations"])
    assert "non-Edge parameters" in " ".join(report["diagnostics"]["restore-limitations"])
    assert "inactive average count" in result.stdout
    restore_mode = next(inv for inv in report["invocations"] if inv["stage"] == "restore-trigger-mode")
    assert "--mode=glitch" in restore_mode["arguments"]
    assert _build_parser().parse_args(restore_mode["arguments"]).mode == "glitch"
    assert any("Original trigger mode is glitch" in note for note in report["diagnostics"]["restore-limitations"])


@requires_powershell
@pytest.mark.parametrize("target", TARGETS[4:])
def test_tektronix_native_error_is_failure_without_restore(tmp_path: Path, target: str) -> None:
    result, report, _ = fake_run(tmp_path, target, scenario="dirty-status")
    assert result.returncode == 1
    assert cases(report)["auto-basic"]["status"] == "FAIL"
    assert cases(report)["restore"]["status"] == "N/A"
    assert not any(inv["stage"].startswith("restore-") for inv in report["invocations"])


@requires_powershell
@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize("scenario", ["success", "auto-failure"])
def test_private_shareable_privacy_and_retention(tmp_path: Path, debug: bool, scenario: str) -> None:
    result, _, run = fake_run(tmp_path, debug=debug, scenario=scenario)
    assert result.returncode == (0 if scenario == "success" else 1), result.stdout + result.stderr
    shareable = list((run / "shareable").rglob("*"))
    for path in shareable:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "PRIVATE-SERIAL-123456" not in text
            assert "USB0::0x0957" not in text
            assert str(REPO_ROOT) not in text
    if debug:
        private = (run / "private/report.json").read_text(encoding="utf-8")
        assert "PRIVATE-SERIAL-123456" in private
        assert (run / "private/summary.md").exists()
    else:
        assert not (run / "private").exists()
        assert {path.name for path in shareable} == {"report.json", "summary.md"}


@requires_powershell
@pytest.mark.parametrize("changes", [
    ["-Target", "all"], ["-Target", "unknown"], ["-Connection", "serial"],
    ["-Connection", "tcpip"], ["-Resource", "TCPIP0::example::INSTR"],
    ["-Resource", "USB0::"], ["-Backend", "@other"], ["-OutputRoot", "docs"],
])
def test_invalid_inputs_are_rejected_before_hardware(tmp_path: Path, changes: list[str]) -> None:
    args = {"-Target": TARGETS[0], "-Connection": "usb", "-Resource": "USB0::0x0957::0x1234::FAKE1234::INSTR",
            "-Python": sys.executable, "-OutputRoot": str(REPO_ROOT / ".tmp_tests/autoscale_invalid" / uuid.uuid4().hex)}
    args[changes[0]] = changes[1]
    result = ps_run(SCRIPT, *(item for pair in args.items() for item in pair))
    assert result.returncode != 0
    assert "Detected instrument:" not in result.stdout
    assert "Actual commands:" not in result.stdout


@requires_powershell
def test_original_cli_rejects_removed_autoscale_option() -> None:
    result = ps_run(REPO_ROOT / "scripts/live-cli-check.ps1", "-Target", TARGETS[4], "-Connection", "usb",
                    "-Resource", "USB0::FAKE::INSTR", "-IncludeAutoscale")
    assert result.returncode != 0
    assert "IncludeAutoscale" in re.sub(r"\s+", "", result.stderr)
    assert "Detected instrument:" not in result.stdout


def test_original_cli_and_tektronix_have_no_auto_cases_or_warnings() -> None:
    for name in ("live-cli-check.ps1", "_live_tektronix_helpers.ps1"):
        text = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "IncludeAutoscale" not in text
        assert not re.search(r'(?i)(?:Command|Name)\s*(?:=\s*)?"autoscale"', text)
        assert "Please Select" not in text


def test_auto_script_reuses_existing_cli_and_privacy_without_bypass() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Get-LiveConnectionArguments" in text
    assert "Assert-TargetModelMatch" in text
    assert "Complete-LiveValidationRun" in text
    assert "New-ShareableArtifactSet" not in text  # Shared finalizer owns privacy.
    assert "Restore-InstrumentState" not in text
    assert "ResourceManager" in text  # Comment describes the hardware-free parser.
    assert not re.search(r"(?i)(?:\*RST|:SYSTem:PRESet|Command setup-recall|SkipConfirmation|ForceAuto)", text)
