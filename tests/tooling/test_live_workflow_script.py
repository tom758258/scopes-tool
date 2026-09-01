from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


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
    assert '-Command "trigger-edge"' not in text
    assert '-Command "trigger-sweep"' not in text


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


def test_live_workflow_script_preflight_covers_new_waveform_workflows() -> None:
    text = _script_text()

    assert 'preflight-capture-until' in text
    assert 'preflight-capture-monitor' in text


def test_live_workflow_script_uses_qualification_status_vocabulary() -> None:
    text = _script_text()

    assert '[ValidateSet("PASS", "FAIL", "N/A")]' in text
    assert '"SKIP"' not in text


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
