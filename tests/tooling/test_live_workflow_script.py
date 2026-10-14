from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from tests.tooling.test_live_tektronix_script import (
    TARGETS, fake_workflow_run, requires_windows, run_script,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "live-workflow-check.ps1"


def _script_text() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_live_workflow_script_covers_public_workflows() -> None:
    text = _script_text()

    for case in (
        "measure-sweep",
        "measure-log",
        "measure-until",
        "measure-until-timeout",
        "capture-batch",
        "triggered-measure-loop",
        "triggered-capture-series",
        "capture-until",
        "capture-monitor",
        "sequence",
    ):
        assert f'-Name "{case}"' in text

    for command in (
        "measure-sweep",
        "measure-log",
        "measure-until",
        "capture-batch",
        "triggered-measure-loop",
        "triggered-capture-series",
        "capture-until",
        "capture-monitor",
        "sequence",
    ):
        assert f'-Command "{command}"' in text


def test_live_workflow_script_preserves_fixture_and_trigger_boundary() -> None:
    text = _script_text()

    assert "Probe Demo / Probe Comp" in text
    assert "stable waveform is present on CH1" in text
    assert "Disconnect unknown or sensitive DUT" in text
    assert "existing trigger setup reliably triggers" in text
    assert "does not reset, preset, autoscale, or reconfigure the trigger mode" in text
    assert "If acquisition is initially stopped, the validator starts it for workflow validation and restores the original Running/Stopped state during cleanup." in text
    legacy_targets = text[
        text.index("$script:LegacyTektronixImmediateMeasurementTargets"):
        text.index("$script:WorkflowCommands")
    ]
    assert '"tektronix-tbs1052b"' in legacy_targets
    assert '"tektronix-tds2024b"' in legacy_targets
    assert "tektronix-tbs2074" not in legacy_targets
    assert "Trigger View must be OFF." in text
    assert "Display format must be YT, not XY." in text
    assert "must not be in Scan mode." in text
    assert "faster than 100 ms/div." in text
    assert "Press Enter only after the required setup above is ready." in text
    assert '-Command "trigger-edge"' not in text
    assert '-Command "trigger-sweep"' not in text


def test_live_workflow_script_surfaces_legacy_tek_measurement_settings_conflict() -> None:
    text = _script_text()

    assert 'PSObject.Properties["post_command_status"]' in text
    assert 'PSObject.Properties["is_error"]' in text
    assert "Tektronix native status" in text
    assert '"event $($eventCodeProperty.Value)"' in text
    assert "[int]$eventCodeProperty.Value -eq 221" in text
    assert "verify Trigger View is OFF, display format is YT" in text
    assert "is not in Scan mode, then rerun validation" in text


def test_live_workflow_script_validates_artifacts_and_expected_timeout() -> None:
    text = _script_text()

    assert '"measurements.csv", "manifest.json", "scpi.log"' in text
    assert '"waveform_0001.csv"' in text
    assert '"waveform_0002_meta.json"' in text
    assert 'Invoke-CliRaw -Stage "measure-until-timeout"' in text
    assert '"condition_timeout"' in text
    assert '"--threshold", "-1"' in text


def test_live_workflow_script_restores_acquisition_and_requires_clean_queue() -> None:
    text = _script_text()

    assert '"system-operation-status"' in text
    assert '$script:OperationConditionRunMask = 8' in text
    assert 'Restore-AcquisitionState -WasRunning $wasRunning' in text
    assert 'if ($snapshotTaken)' in text
    assert '"run"' in text
    assert '"stop-acquisition"' in text
    assert 'Get-ErrorDrain -Stage "final-error-queue"' in text
    assert '-Name "final-error-queue" -Status "PASS"' in text
    assert 'function Ensure-WorkflowAcquisitionRunning' in text
    assert 'Ensure-WorkflowAcquisitionRunning -WasRunning $wasRunning' in text
    assert 'Acquisition was stopped; started for workflow validation.' in text
    assert 'Acquisition was running.' in text
    assert '"acquisition-precondition-run"' in text
    assert '"acquisition-precondition-status"' in text
    call = "Ensure-WorkflowAcquisitionRunning -WasRunning $wasRunning"
    snapshot_index = text.index('Invoke-LiveCli -Stage "snapshot-operation-status"')
    call_index = text.index(call, snapshot_index)
    workflow_index = text.index(
        'Invoke-WorkflowCase -Name "measure-sweep"', call_index
    )
    assert snapshot_index < call_index < workflow_index


def test_live_workflow_script_orders_waveform_before_triggered() -> None:
    text = _script_text()

    monitor_index = text.index('Invoke-WorkflowCase -Name "capture-monitor"')
    triggered_index = text.index('Invoke-WorkflowCase -Name "triggered-measure-loop"')
    until_index = text.index('Invoke-WorkflowCase -Name "capture-until"')

    assert monitor_index < triggered_index
    assert until_index < triggered_index


def test_live_workflow_script_preflight_covers_workflows() -> None:
    text = _script_text()

    assert 'preflight-capture-until' in text
    assert 'preflight-capture-monitor' in text
    assert 'preflight-sequence' in text


def test_live_workflow_script_uses_qualification_status_vocabulary() -> None:
    text = _script_text()

    assert '[ValidateSet("PASS", "FAIL", "N/A")]' in text
    assert '"SKIP"' not in text


@pytest.mark.windows_powershell
@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_live_workflow_script_parses_in_windows_powershell() -> None:
    command = """
$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    $args[0],
    [ref]$tokens,
    [ref]$errors
)
if ($errors.Count -ne 0) {
    $errors | ForEach-Object { Write-Error $_.Message }
    exit 1
}
"""
    environment = os.environ.copy()
    environment["SCOPES_WORKFLOW_SCRIPT_PATH"] = str(SCRIPT_PATH)
    command = command.replace("$args[0]", "$env:SCOPES_WORKFLOW_SCRIPT_PATH")
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_live_workflow_script_uses_unambiguous_negative_threshold_argument() -> None:
    text = _script_text()

    assert text.count('"--threshold=-1e9"') == 2
    assert '"--threshold", "-1e9"' not in text


def _live_capture_monitor_block(text: str) -> str:
    start = text.index('Invoke-WorkflowCase -Name "capture-monitor"')
    end = text.index('Invoke-WorkflowCase -Name "triggered-measure-loop"', start)
    return text[start:end]


def test_live_workflow_script_capture_monitor_live_uses_actual_point_invariants() -> None:
    text = _script_text()
    block = _live_capture_monitor_block(text)

    # A. Forbidden exact hardware assumptions must not reappear in live block.
    assert 'total_observed_points" -Expected 5000' not in block
    assert 'retained_points" -Expected 2000' not in block
    assert 'dropped_points" -Expected 3000' not in block
    assert 'first_retained_capture_index" -Expected 4' not in block
    assert '$rows.Count -ne 2000' not in block
    assert '($indices -join ",") -ne "4,5"' not in block

    # B. Live rollover workload stays
    assert '"--points", "1000"' in block
    assert '"--count", "5"' in block
    assert '"--retention-points", "2000"' in block

    # C. Actual-point accounting invariant
    assert '$retainedPoints + $droppedPoints' in block

    # D. CSV rows == retained_points
    assert '$rows.Count -ne $retainedPoints' in block

    # E. Retained capture indices
    assert '$indices[0] -ne $firstRetainedCaptureIndex' in block
    assert '$indices[-1] -ne $lastRetainedCaptureIndex' in block
    assert '+ 1' in block


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario", ["clean", "stale", "nonerror-events"])
def test_workflow_clean_baseline_preserves_history(tmp_path: Path, scenario: str) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[2], f"focused-{scenario}")
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    for name in ("operator-confirmation", "pre-run-clean-baseline", "measure-sweep", "cleanup", "final-standard-event"):
        assert cases[name]["status"] == "PASS", cases[name]
    diagnostic = " ".join(report["diagnostics"]["pre-run-standard-event"])
    initial = 4 if scenario == "stale" else 0
    assert f'"value":{initial}' in diagnostic
    assert f'"raw":"{initial}"' in diagnostic
    stages = [inv["stage"] for inv in report["invocations"]]
    expected = ["identity", "pre-run-standard-event", "pre-run-clear-status", "pre-run-standard-event-verify", "acquisition-precondition-run", "measure-sweep", "cleanup-acquisition-stop-acquisition", "final-standard-event"]
    assert [stage for stage in stages if stage != "preflight-identify"] == expected
    assert result.stdout.index("Press Enter") < result.stdout.index("pre-run-clean-baseline")
    assert all("check-error" != inv["arguments"][0] for inv in report["invocations"])
    assert report["schema_version"] == 1
    counts = report["summary_counts"]
    assert counts["cases"] == len(cases)
    for key, status in (("passed", "PASS"), ("failed", "FAIL"), ("na", "N/A")):
        assert counts[key] == sum(case["status"] == status for case in cases.values())


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario,failed_stage", [
    ("query-io", "pre-run-standard-event"),
    ("clear-io", "pre-run-clear-status"),
    ("verify-io", "pre-run-standard-event-verify"),
    ("post-event", "pre-run-standard-event-verify"),
])
def test_workflow_clean_baseline_failure_blocks_workflows(tmp_path: Path, scenario: str, failed_stage: str) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[2], f"focused-{scenario}")
    assert result.returncode != 0
    assert report["status"] == "failed"
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["pre-run-clean-baseline"]["status"] == "FAIL"
    assert "measure-sweep" not in cases
    assert "acquisition-precondition" not in cases
    assert report["invocations"][-1]["stage"] == failed_stage
    if scenario.endswith("io"):
        assert "VisaIOError" in cases["pre-run-clean-baseline"]["detail"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario", ["identify-io", "model-mismatch"])
def test_workflow_clean_baseline_respects_identity_gate(tmp_path: Path, scenario: str) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[2], f"focused-{scenario}")
    assert result.returncode != 0
    assert [inv["stage"] for inv in report["invocations"]] == ["preflight-identify", "identity"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario,reason", [
    ("n", "explicit empty input"),
    ("no", "explicit empty input"),
    ("text", "explicit empty input"),
    ("space", "explicit empty input"),
    ("null", "explicit empty input"),
    ("unavailable", "Operator console unavailable"),
])
def test_workflow_clean_baseline_respects_confirmation_gate(tmp_path: Path, scenario: str, reason: str) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[2], f"focused-confirmation-{scenario}")
    assert result.returncode != 0
    assert report["status"] == "failed"
    cases = {case["name"]: case for case in report["cases"]}
    assert list(cases) == ["preflight", "identity", "target-model-match", "operator-confirmation"]
    assert cases["identity"]["status"] == "PASS"
    assert cases["target-model-match"]["status"] == "PASS"
    assert cases["operator-confirmation"]["status"] == "FAIL"
    assert reason in cases["operator-confirmation"]["detail"]
    assert [inv["stage"] for inv in report["invocations"]] == ["preflight-identify", "identity"]
    assert all(inv["arguments"][0] not in (
        "system-standard-event", "system-clear-status", "run",
        "stop-acquisition", "measure-sweep", "capture-batch",
    ) for inv in report["invocations"])
    counts = report["summary_counts"]
    assert counts["cases"] == len(cases)
    assert counts["invocations"] == len(report["invocations"])
    for key, status in (("passed", "PASS"), ("failed", "FAIL"), ("na", "N/A")):
        assert counts[key] == sum(case["status"] == status for case in cases.values())


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario,final_status", [
    ("clean", "PASS"), ("final-event", "FAIL"), ("final-io", "FAIL"),
    ("final-missing", "FAIL"), ("cleanup-fail", "PASS"),
    ("case-fail", "PASS"), ("case-and-final-fail", "FAIL"),
    ("dirty-case", "PASS"),
])
def test_workflow_final_native_status_after_cleanup(tmp_path: Path, scenario: str, final_status: str) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[2], f"focused-{scenario}")
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["final-standard-event"]["status"] == final_status
    assert (result.returncode == 0) == (scenario == "clean")
    assert "final-error-queue" not in cases
    stages = [inv["stage"] for inv in report["invocations"]]
    assert stages[-2:] == ["cleanup-acquisition-stop-acquisition", "final-standard-event"]
    if scenario == "cleanup-fail":
        assert cases["cleanup"]["status"] == "FAIL"
        assert "Injected failure at cleanup-acquisition-stop-acquisition" in cases["cleanup"]["detail"]
    if scenario.startswith("case"):
        assert cases["measure-sweep"]["status"] == "FAIL"
        assert "Injected failure at measure-sweep" in cases["measure-sweep"]["detail"]
    if scenario == "final-io":
        assert "VisaIOError" in cases["final-standard-event"]["detail"]
    if scenario == "dirty-case":
        assert cases["measure-sweep"]["status"] == "FAIL"
        assert "native command status" in cases["measure-sweep"]["detail"]
    counts = report["summary_counts"]
    assert counts["failed"] == sum(case["status"] == "FAIL" for case in cases.values())
