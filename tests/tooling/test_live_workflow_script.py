from __future__ import annotations

import json
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


def _workflow_status_run(tmp_path, command, status, *, tektronix=True, valid=True):
    """Run the actual CLI/status dispatch functions with only the process mocked."""
    fixture = {
        "Command": command, "ExitCode": 0 if valid else 1, "Stderr": "",
        "Payload": {"ok": valid, "system_error": None, "result": {
            "valid": valid, "value": 0.75 if valid else None,
            "raw": "0.75" if valid else "9.9E+37", "post_command_status": status,
        }},
    }
    if not valid:
        fixture["Payload"]["error"] = {
            "type": "OscilloscopeError", "message": "Invalid measurement value",
        }
    if command == "measure-until-timeout":
        fixture["ExitCode"] = 1
        fixture["Payload"]["ok"] = False
        fixture["Payload"]["result"].update(
            status="error", termination_reason="condition_timeout",
            error={"type": "condition_timeout"},
        )
    fixture_path = tmp_path / "workflow-status.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    harness = tmp_path / "workflow-status.ps1"
    harness.write_text(r'''param([string]$ScriptPath, [string]$FixturePath, [string]$Target)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $ScriptPath) "_live_tektronix_helpers.ps1")
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref]$tokens, [ref]$errors
)
if ($errors.Count) { throw "Workflow script parse failed: $($errors[0].Message)" }
foreach ($name in @('Get-PayloadErrorText', 'Get-PayloadSystemError',
                   'Get-InvocationFailureDetail', 'Invoke-Cli', 'Invoke-ModeCli',
                   'Get-RequiredResultValue', 'Assert-ResultEquals')) {
    $function = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
    }, $true)
    if ($null -eq $function) { throw "Workflow function missing: $name" }
    Invoke-Expression $function.Extent.Text
}
foreach ($name in @('$script:WorkflowCommands', '$script:LegacyTektronixImmediateMeasurementTargets')) {
    $assignment = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
            $node.Left.Extent.Text -eq $name
    }, $true)
    if ($null -eq $assignment) { throw "Workflow assignment missing: $name" }
    Invoke-Expression $assignment.Extent.Text
}
$script:Target = $Target
$script:IsTektronix = $Target.StartsWith('tektronix-')
$script:Fixture = [IO.File]::ReadAllText($FixturePath) | ConvertFrom-Json
function Invoke-CliRaw {
    param([string]$Stage, [string[]]$Arguments)
    return $script:Fixture
}
try {
    if ($script:Fixture.Command -eq 'measure-until-timeout') {
        $case = $ast.Find({
            param($node)
            $node -is [System.Management.Automation.Language.CommandAst] -and
                $node.Extent.Text.StartsWith('Invoke-WorkflowCase -Name "measure-until-timeout"')
        }, $true)
        if ($null -eq $case) { throw 'Expected-timeout case missing' }
        $action = $case.CommandElements[-1].ScriptBlock.Extent.Text
        $script:LiveConnectionArguments = @('--simulate', '--model', $Target)
        $liveArtifactRoot = Split-Path -Parent $FixturePath
        function Assert-ExpectedFiles { param($OutputDir, $Names, $Stage) }
        & ([scriptblock]::Create($action.Substring(1, $action.Length - 2)))
        $payload = $script:Fixture.Payload
    } else {
        $payload = Invoke-ModeCli -Stage $script:Fixture.Command -Command $script:Fixture.Command `
            -ModeArguments @('--simulate', '--model', $Target)
    }
    $payload | ConvertTo-Json -Depth 20 -Compress
} catch {
    Write-Error $_.Exception.Message -ErrorAction Continue
    exit 1
}
''', encoding="utf-8")
    target = TARGETS[2] if tektronix else "keysight-dsox2004a"
    return run_script(
        "-ScriptPath", str(SCRIPT_PATH), "-FixturePath", str(fixture_path),
        "-Target", target, script=harness,
    ), fixture["Payload"]


def _native_status(code=None):
    events = [] if code is None else [{
        "code": code, "message": "Rise/fall measurement warning; original message",
        "category": "warning",
    }]
    return {
        "source": "tektronix-sesr", "value": 0 if code is None else 16,
        "raw": "0" if code is None else "16\n",
        "event_raw": '0,"No events"' if code is None else f'{code},"{events[0]["message"]}"\n',
        "events": events, "complete": True, "is_error": False, "destructive_read": True,
    }


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("command", ["measure-sweep", "measure-log", "measure-until", "triggered-measure-loop"])
@pytest.mark.parametrize("code", [None, 540, 549])
def test_workflow_measurement_status_dispatch_accepts_and_preserves(tmp_path, command, code):
    result, payload = _workflow_status_run(tmp_path, command, _native_status(code))
    assert result.returncode == 0, result.stdout + result.stderr
    # Includes raw SESR/event strings, codes, messages, and the measured value.
    assert json.loads(result.stdout) == payload


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario", ["execution", "mixed", "other-bit", "incomplete", "malformed", "malformed-event", "missing-events", "invalid-value"])
def test_workflow_measurement_status_dispatch_rejects(tmp_path, scenario):
    status = _native_status(540)
    if scenario in ("execution", "mixed"):
        error = {"code": 221, "message": "Settings conflict", "category": "error"}
        status["events"] = [error] if scenario == "execution" else [*status["events"], error]
        status["event_raw"] += '221,"Settings conflict"'
        # Deliberately retain is_error=False: the validator must inspect the cohort.
    elif scenario == "other-bit":
        status.update(value=48, raw="48")
    elif scenario == "incomplete":
        status["complete"] = False
    elif scenario == "malformed":
        status.update(value=None, raw="unparseable")
    elif scenario == "malformed-event":
        del status["events"][0]["code"]
    elif scenario == "missing-events":
        status["events"] = []
    result, _ = _workflow_status_run(tmp_path, "measure-sweep", status, valid=scenario != "invalid-value")
    assert result.returncode != 0
    assert any(message in result.stderr for message in ("native", "property", "Invalid measurement value"))


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("mixed", [False, True])
def test_workflow_expected_timeout_measurement_warning_dispatch(tmp_path, mixed):
    status = _native_status(540)
    if mixed:
        status["events"].append({"code": 221, "message": "Settings conflict", "category": "error"})
        status["event_raw"] += '221,"Settings conflict"'
    result, payload = _workflow_status_run(tmp_path, "measure-until-timeout", status)
    assert (result.returncode == 0) == (not mixed)
    if not mixed:
        assert json.loads(result.stdout) == payload
    else:
        assert "outside 540-549" in result.stderr


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("command", ["capture-batch", "sequence"])
def test_workflow_nonmeasurement_status_dispatch_remains_strict(tmp_path, command):
    result, _ = _workflow_status_run(tmp_path, command, _native_status(540))
    assert result.returncode != 0
    assert "native command status" in result.stderr


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("valid", [True, False])
def test_workflow_keysight_status_dispatch_is_unchanged(tmp_path, valid):
    # A poisoned Tektronix-only field detects accidental routing through its helper.
    result, payload = _workflow_status_run(
        tmp_path, "measure-sweep", _native_status(221), tektronix=False, valid=valid,
    )
    assert (result.returncode == 0) == valid
    if valid:
        assert json.loads(result.stdout) == payload
    else:
        assert "Invalid measurement value" in result.stderr
