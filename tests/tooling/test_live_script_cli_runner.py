from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.channel import validate_channel_label


REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_SCRIPTS = (
    REPO_ROOT / "scripts" / "live-cli-check.ps1",
    REPO_ROOT / "scripts" / "live-dvm-check.ps1",
    REPO_ROOT / "scripts" / "live-segmented-check.ps1",
    REPO_ROOT / "scripts" / "live-serial-check.ps1",
    REPO_ROOT / "scripts" / "live-workflow-check.ps1",
)

requires_windows = pytest.mark.skipif(
    os.name != "nt", reason="requires Windows PowerShell"
)


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize("script_path", LIVE_SCRIPTS, ids=lambda path: path.stem)
def test_invoke_cli_raw_preserves_native_process_results(
    tmp_path: Path,
    script_path: Path,
) -> None:
    fake_package = tmp_path / "fake_cli" / "scopes_tool_cli"
    fake_package.mkdir(parents=True)
    (fake_package / "__init__.py").write_text("", encoding="utf-8")
    (fake_package / "cli.py").write_text(
        """\
import json
import sys

mode = sys.argv[1]
print(json.dumps({"ok": True, "result": {"mode": mode}}))
if mode == "invalid-json":
    print("this is not valid json")
    sys.exit(3)
if mode in {"nonempty-stderr", "failure-stderr"}:
    print(f"known diagnostic: {mode}", file=sys.stderr)
if mode == "failure-stderr":
    sys.exit(7)
""",
        encoding="utf-8",
    )

    run_root = tmp_path / script_path.stem
    run_root.mkdir()
    harness_path = tmp_path / f"{script_path.stem}-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [string] $PythonPath,

    [Parameter(Mandatory = $true)]
    [string] $RunRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

$functionAst = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-CliRaw"
    )
}, $true)
if ($null -eq $functionAst) {
    throw "Invoke-CliRaw was not found in ${ScriptPath}."
}

Invoke-Expression $functionAst.Extent.Text

$script:CliInvocationIndex = 0
$script:RunRoot = $RunRoot
$Python = $PythonPath

# Invoke-CliRaw in these migrated validators delegates process capture to the
# shared validation helpers and records invocation metadata.
$migratedCliRawScripts = @(
    "live-cli-check.ps1",
    "live-dvm-check.ps1",
    "live-segmented-check.ps1",
    "live-serial-check.ps1",
    "live-workflow-check.ps1"
)
if ((Split-Path -Leaf $ScriptPath) -in $migratedCliRawScripts) {
    . (Join-Path (Split-Path -Parent $ScriptPath) "_validation_helpers.ps1")
    $RepoRoot = $RunRoot
    $script:RunDirectory = $RunRoot
    $script:Invocations = New-Object System.Collections.Generic.List[object]
}

$empty = Invoke-CliRaw -Stage "empty-stderr" -Arguments @("empty-stderr")
$emptyPath = Join-Path $RunRoot "cli-001-empty-stderr.stderr.txt"
$emptyPreference = [string]$ErrorActionPreference

$nonempty = Invoke-CliRaw -Stage "nonempty-stderr" -Arguments @("nonempty-stderr")
$nonemptyPath = Join-Path $RunRoot "cli-002-nonempty-stderr.stderr.txt"
$nonemptyPreference = [string]$ErrorActionPreference

$failure = Invoke-CliRaw -Stage "failure-stderr" -Arguments @("failure-stderr")
$failurePath = Join-Path $RunRoot "cli-003-failure-stderr.stderr.txt"
$failurePreference = [string]$ErrorActionPreference

$invalidDetail = ""
try {
    Invoke-CliRaw -Stage "invalid-json" -Arguments @("invalid-json") | Out-Null
} catch {
    $invalidDetail = [string]$_.Exception.Message
}
$invalidStdoutPath = Join-Path $RunRoot "cli-004-invalid-json.stdout.txt"

$resultOutput = [ordered]@{
    empty_exit_code = $empty.ExitCode
    empty_ok = $empty.Payload.ok
    empty_stderr = $empty.Stderr
    empty_artifact_exists = Test-Path -LiteralPath $emptyPath
    empty_preference = $emptyPreference
    nonempty_exit_code = $nonempty.ExitCode
    nonempty_ok = $nonempty.Payload.ok
    nonempty_stderr = $nonempty.Stderr
    nonempty_artifact_exists = Test-Path -LiteralPath $nonemptyPath
    nonempty_artifact = [string](Get-Content -LiteralPath $nonemptyPath -Raw)
    nonempty_preference = $nonemptyPreference
    failure_exit_code = $failure.ExitCode
    failure_mode = $failure.Payload.result.mode
    failure_stderr = $failure.Stderr
    failure_artifact_exists = Test-Path -LiteralPath $failurePath
    failure_artifact = [string](Get-Content -LiteralPath $failurePath -Raw)
    failure_preference = $failurePreference
}
if ((Split-Path -Leaf $ScriptPath) -in $migratedCliRawScripts) {
    $firstRecord = $script:Invocations[0]
    $resultOutput["cli_stdout_artifact_exists"] =
        Test-Path -LiteralPath (Join-Path $RunRoot "cli-001-empty-stderr.stdout.txt")
    $resultOutput["cli_json_artifact_exists"] =
        Test-Path -LiteralPath (Join-Path $RunRoot "cli-001-empty-stderr.json")
    $resultOutput["cli_duration_gt_zero"] = ($null -ne $empty.DurationMs -and $empty.DurationMs -gt 0)
    $resultOutput["cli_invocation_count"] = $script:Invocations.Count
    $resultOutput["cli_record_stage0"] = [string]$firstRecord.stage
    $resultOutput["cli_record_index0"] = [int]$firstRecord.index
    $resultOutput["cli_record_exit0"] = [int]$firstRecord.exit_code
    $resultOutput["cli_record_success_last"] = [bool]$script:Invocations[2].success
    $resultOutput["cli_record_relative_stdout"] = [string]$firstRecord.stdout
    $resultOutput["cli_empty_stdout_path_set"] =
        (-not [string]::IsNullOrWhiteSpace([string]$empty.StdOutPath))

    # Evidence ordering regression: an attempted invocation with unparseable
    # stdout must remain recorded even though Invoke-CliRaw threw.
    $fourthRecord = $script:Invocations[3]
    $resultOutput["cli_invalid_threw"] =
        (-not [string]::IsNullOrWhiteSpace($invalidDetail))
    $resultOutput["cli_invalid_threw_invalid_json"] =
        $invalidDetail.Contains("CLI returned invalid JSON")
    $resultOutput["cli_invocation_count_with_invalid"] = $script:Invocations.Count
    $resultOutput["cli_invalid_recorded_stage"] = [string]$fourthRecord.stage
    $resultOutput["cli_invalid_recorded_exit"] = [int]$fourthRecord.exit_code
    $resultOutput["cli_invalid_recorded_success"] = [bool]$fourthRecord.success
    $resultOutput["cli_invalid_recorded_stdout"] = [string]$fourthRecord.stdout
    $resultOutput["cli_invalid_recorded_stderr"] = [string]$fourthRecord.stderr
    $resultOutput["cli_invalid_recorded_json"] = [string]$fourthRecord.json
    $resultOutput["cli_invalid_stdout_artifact_exists"] =
        Test-Path -LiteralPath $invalidStdoutPath
}
$resultOutput | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    environment = os.environ.copy()
    python_path = str(fake_package.parent)
    if environment.get("PYTHONPATH"):
        python_path += os.pathsep + environment["PYTHONPATH"]
    environment["PYTHONPATH"] = python_path

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-PythonPath",
            sys.executable,
            "-RunRoot",
            str(run_root),
        ],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["empty_exit_code"] == 0
    assert result["empty_ok"] is True
    assert result["empty_stderr"] == ""
    assert result["empty_artifact_exists"] is False
    assert result["empty_preference"] == "Stop"
    assert result["nonempty_exit_code"] == 0
    assert result["nonempty_ok"] is True
    assert "known diagnostic: nonempty-stderr" in result["nonempty_stderr"]
    assert result["nonempty_artifact_exists"] is True
    assert "known diagnostic: nonempty-stderr" in result["nonempty_artifact"]
    assert result["nonempty_preference"] == "Stop"
    assert result["failure_exit_code"] == 7
    assert result["failure_mode"] == "failure-stderr"
    assert "known diagnostic: failure-stderr" in result["failure_stderr"]
    assert result["failure_artifact_exists"] is True
    assert "known diagnostic: failure-stderr" in result["failure_artifact"]
    assert result["failure_preference"] == "Stop"
    if script_path.name in {
        "live-cli-check.ps1",
        "live-dvm-check.ps1",
        "live-segmented-check.ps1",
        "live-serial-check.ps1",
        "live-workflow-check.ps1",
    }:
        assert result["cli_stdout_artifact_exists"] is True
        assert result["cli_json_artifact_exists"] is True
        assert result["cli_duration_gt_zero"] is True
        assert result["cli_invocation_count"] == 4
        assert result["cli_record_stage0"] == "empty-stderr"
        assert result["cli_record_index0"] == 1
        assert result["cli_record_exit0"] == 0
        assert result["cli_record_success_last"] is False
        assert result["cli_record_relative_stdout"].replace("\\", "/").endswith(
            "cli-001-empty-stderr.stdout.txt"
        )
        assert result["cli_empty_stdout_path_set"] is True
        assert result["cli_invalid_threw"] is True
        assert result["cli_invalid_threw_invalid_json"] is True
        assert result["cli_invocation_count_with_invalid"] == 4
        assert result["cli_invalid_recorded_stage"] == "invalid-json"
        assert result["cli_invalid_recorded_exit"] == 3
        assert result["cli_invalid_recorded_success"] is False
        assert result["cli_invalid_recorded_stdout"] != ""
        assert result["cli_invalid_recorded_stderr"] == ""
        assert result["cli_invalid_recorded_json"] == ""
        assert result["cli_invalid_stdout_artifact_exists"] is True


@requires_windows
def test_live_cli_check_invoke_cli_raw_uses_native_invocation() -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    invoke_raw_start = script_text.index("function Invoke-CliRaw {")
    invoke_raw_end = script_text.index("\nfunction Invoke-Cli {", invoke_raw_start)
    invoke_raw = script_text[invoke_raw_start:invoke_raw_end]

    # Hardware-proven execution boundary (baseline 239ea52a): launch the CLI
    # through native PowerShell invocation and take the exit code from
    # $LASTEXITCODE; never delegate live-cli-check to the shared
    # ProcessStartInfo capture helper.
    assert "& $Python -m scopes_tool_cli.cli @Arguments" in invoke_raw
    assert "$LASTEXITCODE" in invoke_raw
    assert '$ErrorActionPreference = "Continue"' in invoke_raw
    assert "Invoke-CapturedCommand" not in invoke_raw
    assert "ProcessStartInfo" not in invoke_raw
    assert "System.Diagnostics.Process" not in invoke_raw

    for validator_name in (
        "live-dvm-check.ps1",
        "live-segmented-check.ps1",
        "live-serial-check.ps1",
        "live-workflow-check.ps1",
    ):
        other_script = (REPO_ROOT / "scripts" / validator_name).read_text(
            encoding="utf-8"
        )
        assert "Invoke-CapturedCommand" in other_script


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize("script_path", LIVE_SCRIPTS, ids=lambda path: path.stem)
def test_get_error_drain_normalizes_entries_as_arrays(
    tmp_path: Path,
    script_path: Path,
) -> None:
    harness_path = tmp_path / f"{script_path.stem}-error-drain-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

$functionAst = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Get-ErrorDrain"
    )
}, $true)
if ($null -eq $functionAst) {
    throw "Get-ErrorDrain was not found in ${ScriptPath}."
}
Invoke-Expression $functionAst.Extent.Text

$script:PayloadIndex = 0
$script:Payloads = @(
    [pscustomobject]@{
        result = [pscustomobject]@{
            entries = @(
                [pscustomobject]@{ code = 0; message = "No error" }
            )
        }
    },
    [pscustomobject]@{
        result = [pscustomobject]@{
            entries = @(
                [pscustomobject]@{ code = -222; message = "known diagnostic" }
            )
        }
    },
    [pscustomobject]@{
        result = [pscustomobject]@{
            entries = @(
                [pscustomobject]@{ code = -222; message = "known diagnostic" },
                [pscustomobject]@{ code = 0; message = "No error" }
            )
        }
    }
)

function Invoke-CliRaw {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $payload = $script:Payloads[$script:PayloadIndex]
    $script:PayloadIndex += 1
    return [pscustomobject]@{ Payload = $payload }
}

$script:LiveConnectionArguments = @("--live", "--resource", "TEST::INSTR")
$singletonClean = Get-ErrorDrain -Stage "singleton-clean"
$singletonError = Get-ErrorDrain -Stage "singleton-error"
$multipleEntries = Get-ErrorDrain -Stage "multiple-entries"

[ordered]@{
    clean_entries_count = $singletonClean.Entries.Count
    clean_errors_count = $singletonClean.Errors.Count
    clean_terminated = $singletonClean.Terminated
    error_entries_count = $singletonError.Entries.Count
    error_errors_count = $singletonError.Errors.Count
    error_terminated = $singletonError.Terminated
    error_code = $singletonError.Errors[0].code
    error_message = $singletonError.Errors[0].message
    multiple_entries_count = $multipleEntries.Entries.Count
    multiple_errors_count = $multipleEntries.Errors.Count
    multiple_terminated = $multipleEntries.Terminated
} | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["clean_entries_count"] == 1
    assert result["clean_errors_count"] == 0
    assert result["clean_terminated"] is True
    assert result["error_entries_count"] == 1
    assert result["error_errors_count"] == 1
    assert result["error_terminated"] is False
    assert result["error_code"] == -222
    assert result["error_message"] == "known diagnostic"
    assert result["multiple_entries_count"] == 2
    assert result["multiple_errors_count"] == 1
    assert result["multiple_terminated"] is True


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize(
    "script_path",
    (
        REPO_ROOT / "scripts" / "live-dvm-check.ps1",
        REPO_ROOT / "scripts" / "live-segmented-check.ps1",
        REPO_ROOT / "scripts" / "live-serial-check.ps1",
    ),
    ids=lambda path: path.stem,
)
def test_optional_write_drain_errors_accepts_empty_collection(
    tmp_path: Path,
    script_path: Path,
) -> None:
    harness_path = tmp_path / f"{script_path.stem}-empty-drain-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @("Add-Diagnostic", "Write-DrainErrors")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$script:Diagnostics = [ordered]@{}
Write-DrainErrors -Errors @() -CaseName "dc"

[ordered]@{
    diagnostic_count = $script:Diagnostics.Count
} | ConvertTo-Json -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["diagnostic_count"] == 0


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize(
    "script_path",
    (
        REPO_ROOT / "scripts" / "live-cli-check.ps1",
        REPO_ROOT / "scripts" / "live-dvm-check.ps1",
        REPO_ROOT / "scripts" / "live-serial-check.ps1",
    ),
    ids=lambda path: path.stem,
)
def test_invoke_cli_preserves_nonzero_system_error(
    tmp_path: Path,
    script_path: Path,
) -> None:
    harness_path = tmp_path / f"{script_path.stem}-system-error-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

$functionNames = @("Get-PayloadErrorText")
if ([System.IO.Path]::GetFileName($ScriptPath) -eq "live-cli-check.ps1") {
    $functionNames += "Get-TriggerDiagnosticText"
}
if ([System.IO.Path]::GetFileName($ScriptPath) -eq "live-serial-check.ps1") {
    $functionNames += @("Get-PayloadSystemError", "Get-InvocationFailureDetail")
}
$functionNames += "Invoke-Cli"
foreach ($functionName in $functionNames) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

function Invoke-CliRaw {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $payload = switch ($Stage) {
        "nonzero-system-error" {
            [pscustomobject]@{
                ok = $false
                error = $null
                system_error = [pscustomobject]@{
                    code = -221
                    message = "Settings conflict"
                    raw = '-221,"Settings conflict"'
                }
            }
        }
        "zero-system-error-failure" {
            [pscustomobject]@{
                ok = $false
                error = $null
                system_error = [pscustomobject]@{
                    code = 0
                    message = "No error"
                }
            }
        }
        "zero-system-error-success" {
            [pscustomobject]@{
                ok = $true
                error = $null
                system_error = [pscustomobject]@{
                    code = 0
                    message = "No error"
                }
            }
        }
        default {
            throw "Unexpected stage: ${Stage}"
        }
    }
    $exitCode = if ($Stage -eq "zero-system-error-success") { 0 } else { 1 }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Payload = $payload
        Stderr = ""
        Command = "fake-cli dvm-auto-range --enabled true"
    }
}

$nonzeroDetail = ""
try {
    Invoke-Cli -Stage "nonzero-system-error" -Arguments @("dvm-auto-range")
} catch {
    $nonzeroDetail = $_.Exception.Message
}

$zeroFailureDetail = ""
try {
    Invoke-Cli -Stage "zero-system-error-failure" -Arguments @("dvm-auto-range")
} catch {
    $zeroFailureDetail = $_.Exception.Message
}

$success = Invoke-Cli -Stage "zero-system-error-success" `
    -Arguments @("dvm-auto-range")

[ordered]@{
    nonzero_detail = $nonzeroDetail
    zero_failure_detail = $zeroFailureDetail
    success_ok = $success.ok
} | ConvertTo-Json -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert "exited 1" in result["nonzero_detail"]
    assert "-221" in result["nonzero_detail"]
    assert "Settings conflict" in result["nonzero_detail"]
    assert "exited 1" in result["zero_failure_detail"]
    if script_path.name == "live-cli-check.ps1":
        assert '-221,"Settings conflict"' in result["nonzero_detail"]
        assert "system error 0" in result["zero_failure_detail"]
        assert "No error" in result["zero_failure_detail"]
    else:
        assert "system error 0" not in result["zero_failure_detail"]
        assert "No error" not in result["zero_failure_detail"]
    assert result["success_ok"] is True


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize(
    ("source_channel", "expected_status", "expected_gate_open"),
    [(1, "FAIL", False), (2, "PASS", True)],
)
def test_dvm_auto_range_trigger_precondition(
    tmp_path: Path,
    source_channel: int,
    expected_status: str,
    expected_gate_open: bool,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-dvm-check.ps1"
    harness_path = tmp_path / f"dvm-trigger-precondition-{source_channel}.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [int] $SourceChannel
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse DVM live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @(
    "Add-CaseResult",
    "Add-Diagnostic",
    "Get-RequiredResultValue",
    "Get-ErrorDrain",
    "Write-DrainErrors",
    "Drain-AfterFailure",
    "Invoke-DvmCase"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$preconditionCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.Extent.Text.Contains('Invoke-DvmCase -Name "auto-range-precondition"')
    )
}, $true))
if ($preconditionCommands.Count -ne 1) {
    throw "Expected one production auto-range-precondition command."
}

$stateChangeBlocks = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.Contains('Invoke-DvmCase -Name "dc"') -and
        $node.Extent.Text.Contains('dc-source-set')
    )
}, $true))
if ($stateChangeBlocks.Count -ne 1) {
    throw "Expected one production DVM state-change block."
}

$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations = New-Object System.Collections.Generic.List[object]
$Resource = "TEST::INSTR"

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $Command,

        [string[]] $Arguments = @()
    )

    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    if ($Command -ne "trigger-edge-source") {
        throw "Unexpected live command: ${Command}"
    }
    return [pscustomobject]@{
        result = [pscustomobject]@{
            source = "analog-channel"
            source_channel = $SourceChannel
        }
    }
}

function Invoke-CliRaw {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Arguments[0]
        arguments = @($Arguments[1..($Arguments.Count - 1)])
    })
    return [pscustomobject]@{
        ExitCode = 0
        Payload = [pscustomobject]@{
            result = [pscustomobject]@{
                entries = @(
                    [pscustomobject]@{ code = 0; message = "No error" }
                )
            }
        }
        Stderr = ""
        Command = "fake-cli check-error"
    }
}

Invoke-Expression $preconditionCommands[0].Extent.Text

$snapshot = [pscustomobject]@{}
$stateGateExpression = $stateChangeBlocks[0].Clauses[0].Item1.Extent.Text
$stateGateOpen = [bool](Invoke-Expression $stateGateExpression)
if (-not $stateGateOpen) {
    Invoke-Expression $stateChangeBlocks[0].Extent.Text
}

[ordered]@{
    status = $script:CaseResults["auto-range-precondition"].Status
    detail = $script:CaseResults["auto-range-precondition"].Detail
    functional_failed = $script:FunctionalFailed
    state_gate_open = $stateGateOpen
    invocations = @($script:Invocations | ForEach-Object { $_ })
} | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-SourceChannel",
            str(source_channel),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["status"] == expected_status
    assert result["functional_failed"] is (expected_status == "FAIL")
    assert result["state_gate_open"] is expected_gate_open

    commands = [invocation["command"] for invocation in result["invocations"]]
    assert commands[0] == "trigger-edge-source"
    if source_channel == 1:
        assert "CH1" in result["detail"]
        assert "Edge trigger source" in result["detail"]
        assert "another trigger source" in result["detail"]
        assert not {
            "dvm-source",
            "dvm-auto-range",
            "dvm-mode",
            "dvm-enable",
        }.intersection(commands)
    else:
        assert result["detail"] == ""


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize(
    (
        "scenario",
        "expected_status",
        "expected_stages",
        "expected_sleeps",
    ),
    [
        (
            "normal",
            "PASS",
            "configuration-enable,configuration-query-segmented,"
            "configuration-disable,configuration-query-realtime",
            "500",
        ),
        (
            "transient-allowed",
            "PASS",
            "configuration-enable,configuration-query-segmented,"
            "configuration-query-segmented-recovery-drain,"
            "configuration-query-segmented-retry,configuration-disable,"
            "configuration-query-realtime",
            "500,500,500",
        ),
        (
            "transient-clean",
            "PASS",
            "configuration-enable,configuration-query-segmented,"
            "configuration-query-segmented-recovery-drain,"
            "configuration-query-segmented-retry,configuration-disable,"
            "configuration-query-realtime",
            "500,500,500",
        ),
        (
            "unexpected-recovery-error",
            "FAIL",
            "configuration-enable,configuration-query-segmented,"
            "configuration-query-segmented-recovery-drain,"
            "configuration-roundtrip-error-drain",
            "500,500",
        ),
        (
            "non-idn-timeout",
            "FAIL",
            "configuration-enable,configuration-query-segmented,"
            "configuration-roundtrip-error-drain",
            "500",
        ),
        (
            "retry-failure",
            "FAIL",
            "configuration-enable,configuration-query-segmented,"
            "configuration-query-segmented-recovery-drain,"
            "configuration-query-segmented-retry,"
            "configuration-roundtrip-error-drain",
            "500,500,500",
        ),
    ],
)
def test_segmented_configuration_readback_recovery(
    tmp_path: Path,
    scenario: str,
    expected_status: str,
    expected_stages: str,
    expected_sleeps: str,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-segmented-check.ps1"
    harness_path = tmp_path / f"segmented-readback-{scenario}.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [string] $Scenario
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse Segmented live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @(
    "Get-PayloadErrorText",
    "Add-CaseResult",
    "Add-Diagnostic",
    "Get-InvocationFailureDetail",
    "Get-RequiredResultValue",
    "Get-ErrorDrain",
    "Write-DrainErrors",
    "Drain-AfterFailure",
    "Invoke-SegmentedConfigurationReadback"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$enableAssignments = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Extent.Text.Contains('Invoke-CliRaw -Stage "configuration-enable"')
    )
}, $true))
if ($enableAssignments.Count -ne 1) {
    throw "Expected one production configuration-enable assignment."
}

$configurationBlocks = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.TryStatementAst] -and
        $node.Extent.Text.Contains("Invoke-SegmentedConfigurationReadback") -and
        $node.Extent.Text.Contains('Invoke-LiveCli -Stage "configuration-disable"')
    )
}, $true))
if ($configurationBlocks.Count -ne 1) {
    throw "Expected one production configuration roundtrip try block."
}

$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:Sleeps = New-Object System.Collections.Generic.List[int]
$configurationPassed = $false
$enableInvocation = $null
$Resource = "TEST::INSTR"
$script:LiveConnectionArguments = @("--live", "--resource", $Resource)

Write-DrainErrors -Errors @() -CaseName "empty-drain"
$emptyDrainDiagnosticCount = $script:Diagnostics.Count

function Start-Sleep {
    param(
        [Parameter(Mandatory = $true)]
        [int] $Milliseconds
    )

    $script:Sleeps.Add($Milliseconds)
}

function Invoke-CliRaw {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Arguments[0]
        arguments = @($Arguments)
    })

    $exitCode = 0
    $payload = $null
    switch ($Stage) {
        "configuration-enable" {
            $payload = [pscustomobject]@{ ok = $true; error = $null }
        }
        "configuration-query-segmented" {
            if ($Scenario -eq "normal") {
                $payload = [pscustomobject]@{
                    ok = $true
                    error = $null
                    result = [pscustomobject]@{
                        mode = "segmented"
                        configured_segments = 2
                    }
                }
            } else {
                $exitCode = if ($Scenario -eq "non-idn-timeout") { 0 } else { 1 }
                $message = if ($Scenario -eq "non-idn-timeout") {
                    "VISA query failed for ':WAVeform:DATA?': VI_ERROR_TMO"
                } else {
                    "VISA query failed for '*IDN?': VI_ERROR_TMO"
                }
                $payload = [pscustomobject]@{
                    ok = $false
                    error = [pscustomobject]@{
                        type = "VisaBackendError"
                        message = $message
                    }
                }
            }
        }
        "configuration-query-segmented-recovery-drain" {
            $entries = switch ($Scenario) {
                "transient-allowed" {
                    @(
                        [pscustomobject]@{ code = -221; message = "Settings conflict" },
                        [pscustomobject]@{ code = -420; message = "Query UNTERMINATED" },
                        [pscustomobject]@{ code = 0; message = "No error" }
                    )
                }
                "transient-clean" {
                    @([pscustomobject]@{ code = 0; message = "No error" })
                }
                "unexpected-recovery-error" {
                    @(
                        [pscustomobject]@{ code = -222; message = "Data out of range" },
                        [pscustomobject]@{ code = 0; message = "No error" }
                    )
                }
                "retry-failure" {
                    @(
                        [pscustomobject]@{ code = -221; message = "Settings conflict" },
                        [pscustomobject]@{ code = 0; message = "No error" }
                    )
                }
                default {
                    throw "Unexpected recovery drain scenario: ${Scenario}"
                }
            }
            $payload = [pscustomobject]@{
                ok = $true
                result = [pscustomobject]@{ entries = @($entries) }
            }
        }
        "configuration-query-segmented-retry" {
            if ($Scenario -eq "retry-failure") {
                $payload = [pscustomobject]@{
                    ok = $false
                    error = [pscustomobject]@{
                        type = "VisaBackendError"
                        message = "retry rejected"
                    }
                }
            } else {
                $payload = [pscustomobject]@{
                    ok = $true
                    error = $null
                    result = [pscustomobject]@{
                        mode = "segmented"
                        configured_segments = 2
                    }
                }
            }
        }
        "configuration-roundtrip-error-drain" {
            $payload = [pscustomobject]@{
                ok = $true
                result = [pscustomobject]@{
                    entries = @(
                        [pscustomobject]@{ code = 0; message = "No error" }
                    )
                }
            }
        }
        default {
            throw "Unexpected raw CLI stage: ${Stage}"
        }
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Payload = $payload
        Stderr = ""
        Command = "fake-cli $($Arguments -join ' ')"
    }
}

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $Command,

        [string[]] $Arguments = @()
    )

    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    switch ($Stage) {
        "configuration-disable" {
            return [pscustomobject]@{ ok = $true }
        }
        "configuration-query-realtime" {
            return [pscustomobject]@{
                ok = $true
                result = [pscustomobject]@{ mode = "realtime" }
            }
        }
        default {
            throw "Unexpected live CLI stage: ${Stage}"
        }
    }
}

Invoke-Expression $enableAssignments[0].Extent.Text
Invoke-Expression $configurationBlocks[0].Extent.Text

$diagnosticMessages = @()
if ($script:Diagnostics.Contains("segmented configuration roundtrip")) {
    $diagnosticMessages = @(
        $script:Diagnostics["segmented configuration roundtrip"] |
            ForEach-Object { $_ }
    )
}

[ordered]@{
    status = $script:CaseResults["segmented configuration roundtrip"].Status
    detail = $script:CaseResults["segmented configuration roundtrip"].Detail
    functional_failed = $script:FunctionalFailed
    configuration_passed = $configurationPassed
    empty_drain_diagnostic_count = $emptyDrainDiagnosticCount
    invocation_stages = (($script:Invocations | ForEach-Object { $_.stage }) -join ",")
    sleeps = (($script:Sleeps | ForEach-Object { $_ }) -join ",")
    diagnostics = ($diagnosticMessages -join " | ")
} | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-Scenario",
            scenario,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["status"] == expected_status
    assert result["functional_failed"] is (expected_status == "FAIL")
    assert result["configuration_passed"] is (expected_status == "PASS")
    assert result["empty_drain_diagnostic_count"] == 0
    assert result["invocation_stages"] == expected_stages
    assert result["sleeps"] == expected_sleeps
    assert result["invocation_stages"].split(",").count("configuration-enable") == 1
    assert (
        result["invocation_stages"].split(",").count(
            "configuration-query-segmented"
        )
        == 1
    )
    assert (
        result["invocation_stages"].split(",").count(
            "configuration-query-segmented-retry"
        )
        <= 1
    )
    assert "diagnostic error drain failed" not in result["diagnostics"]

    if scenario == "transient-allowed":
        assert "system error -221: Settings conflict" in result["diagnostics"]
        assert "system error -420: Query UNTERMINATED" in result["diagnostics"]
    elif scenario == "unexpected-recovery-error":
        assert "system error -222: Data out of range" in result["diagnostics"]
        assert "unexpected system error code(s): -222" in result["detail"]
    elif scenario == "retry-failure":
        assert "configuration-query-segmented-retry" in result["detail"]
        assert "retry rejected" in result["detail"]
    elif scenario in {"normal", "transient-clean", "non-idn-timeout"}:
        assert result["diagnostics"] == ""


@requires_windows
def test_segmented_finite_capture_uses_run_root_output_dir(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-segmented-check.ps1"
    harness_path = tmp_path / "segmented-finite-capture-harness.ps1"
    run_root = tmp_path / "run-root"
    run_root.mkdir()
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [string] $RunRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse Segmented live script: $($parseErrors[0].Message)"
}

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:RunRoot = $RunRoot
$configurationPassed = $true

function Add-CaseResult {
    param([string] $Name, [string] $Status, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Status = $Status
        Detail = $Detail
    }
}

function Assert-SegmentedCapture {
    param([object] $Payload)
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
}

function Invoke-LiveCli {
    param(
        [string] $Stage,
        [string] $Command,
        [string[]] $Arguments = @()
    )
    $script:CaptureInvocation = [pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    }
    return [pscustomobject]@{ ok = $true }
}

$finiteBlocks = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.TryStatementAst] -and
        $node.Extent.Text.Contains('Stage "segmented-finite-capture"')
    )
}, $true))
if ($finiteBlocks.Count -ne 1) {
    throw "Expected one production finite capture try block."
}
Invoke-Expression $finiteBlocks[0].Extent.Text

if ($null -eq $script:CaptureInvocation) {
    throw "segmented-finite-capture was not invoked."
}
$outputDirIndex = [array]::IndexOf(
    $script:CaptureInvocation.arguments,
    "--output-dir"
)
if ($outputDirIndex -lt 0 -or
    $outputDirIndex + 1 -ge $script:CaptureInvocation.arguments.Count) {
    throw "--output-dir is missing or has no value."
}
$outputDir = $script:CaptureInvocation.arguments[$outputDirIndex + 1]

[ordered]@{
    status = $script:CaseResults["segmented finite capture"].Status
    detail = $script:CaseResults["segmented finite capture"].Detail
    functional_failed = $script:FunctionalFailed
    stage = $script:CaptureInvocation.stage
    command = $script:CaptureInvocation.command
    arguments = @($script:CaptureInvocation.arguments)
    output_dir = $outputDir
} | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-RunRoot",
            str(run_root),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["status"] == "PASS", result["detail"]
    assert result["functional_failed"] is False
    assert result["stage"] == "segmented-finite-capture"
    assert result["command"] == "segmented-capture"
    assert "--output-dir" in result["arguments"]
    assert result["output_dir"]
    assert Path(result["output_dir"]).resolve() == (
        run_root / "segmented-capture"
    ).resolve()

def test_serial_lister_acquisition_safety_structure() -> None:
    script = (REPO_ROOT / "scripts" / "live-serial-check.ps1").read_text(
        encoding="utf-8"
    )

    assert "$script:ListerAcquisitionTimeoutMilliseconds = 5000" in script
    assert "$script:ListerAcquisitionPollIntervalMilliseconds = 100" in script
    assert "$script:OperationConditionRunMask = 8" in script
    assert '-Command "system-operation-status" -ModeArguments $simulate' in script
    assert 'foreach ($command in @("single", "run", "stop-acquisition"))' in script

    snapshot = script.index('-Stage "snapshot-operation-status"')
    snapshot_display = script.index('-Stage "snapshot-serial-display"')
    was_running = script.index("WasRunning = (", snapshot)
    assert snapshot < was_running
    assert snapshot_display < script.index('-Stage "uart-configure"')

    restore = script.index("function Restore-SerialState")
    search = script.index("if ($DisableSearch)", restore)
    lister = script.index("if ($RestoreLister)", search)
    serial_display_restore = script.index("if ($RestoreSerialDisplay)", lister)
    trigger = script.index("if ($RestoreTrigger)", serial_display_restore)
    acquisition = script.index("if ($RestoreAcquisition)", trigger)
    final_drain = script.index('$finalDrain = Get-ErrorDrain -Stage "final-error-queue"')
    assert (
        restore
        < search
        < lister
        < serial_display_restore
        < trigger
        < acquisition
        < final_drain
    )

    lister_case_start = script.index(
        'Invoke-SerialCase -Name "UART Lister export"'
    )
    search_case_start = script.index(
        'Invoke-SerialCase -Name "UART Serial Search"', lister_case_start
    )
    lister_case = script[lister_case_start:search_case_start]
    assert lister_case.count('"serial-lister-export"') == 1
    assert lister_case.count('"serial-display"') == 1
    assert lister_case.index('"serial-display"') < lister_case.index(
        '"serial-lister-display"'
    )
    assert ":SAVE:LISTer" not in script
    assert "DIGITIZE" not in lister_case.upper()
    assert '"force-trigger"' not in lister_case


def test_serial_protocol_coverage_structure() -> None:
    script = (REPO_ROOT / "scripts" / "live-serial-check.ps1").read_text(
        encoding="utf-8"
    )

    expected_preflight = [
        '-Command "serial-uart"',
        '-Command "serial-i2c"',
        '-Command "serial-spi"',
        '-Command "serial-can"',
        '-Command "serial-search-uart"',
        '-Command "serial-search-i2c"',
        '-Command "serial-search-spi"',
        '-Command "serial-search-can"',
        '-Command "serial-trigger-uart"',
        '-Command "serial-trigger-i2c"',
        '-Command "serial-trigger-spi"',
        '-Command "serial-trigger-can"',
    ]
    for marker in expected_preflight:
        assert marker in script

    case_names = [
        'Invoke-SerialCase -Name "UART configuration roundtrip"',
        'Invoke-SerialCase -Name "UART Lister export"',
        'Invoke-SerialCase -Name "UART Serial Search"',
        'Invoke-SerialCase -Name "UART Serial Trigger"',
        'Invoke-SerialCase -Name "I2C configuration roundtrip"',
        'Invoke-SerialCase -Name "I2C Serial Search"',
        'Invoke-SerialCase -Name "I2C Serial Trigger"',
        'Invoke-SerialCase -Name "SPI configuration roundtrip"',
        'Invoke-SerialCase -Name "SPI Serial Search"',
        'Invoke-SerialCase -Name "SPI Serial Trigger"',
        'Invoke-SerialCase -Name "CAN configuration roundtrip"',
        'Invoke-SerialCase -Name "CAN Serial Search"',
        'Invoke-SerialCase -Name "CAN Serial Trigger"',
    ]
    indices = [script.index(name) for name in case_names]
    assert indices == sorted(indices)

    assert '"--framing", "timeout"' in script
    assert '"--clock-timeout", "1e-5"' in script
    assert '"--id", "0x123"' in script

    for case_name in [
        "I2C configuration roundtrip",
        "I2C Serial Search",
        "I2C Serial Trigger",
        "SPI configuration roundtrip",
        "SPI Serial Search",
        "SPI Serial Trigger",
        "CAN configuration roundtrip",
        "CAN Serial Search",
        "CAN Serial Trigger",
    ]:
        start = script.index(f'Invoke-SerialCase -Name "{case_name}"')
        next_pos = script.find('Invoke-SerialCase -Name "', start + 1)
        if next_pos == -1:
            next_pos = script.find('if ($stateChangeStarted)', start)
        block = script[start:next_pos]
        assert '"single"' not in block
        assert '"run"' not in block
        assert '"digitize"' not in block
        assert '"force-trigger"' not in block

    can_trigger = script.index('Invoke-SerialCase -Name "CAN Serial Trigger"')
    cleanup = script.index("Restore-SerialState -Snapshot $snapshot", can_trigger)
    final_drain = script.index(
        '$finalDrain = Get-ErrorDrain -Stage "final-error-queue"', cleanup
    )

    assert can_trigger < cleanup < final_drain
    assert "-RestoreUartBaseline $true" in script[cleanup:final_drain]

    restore_def = script.index("function Restore-SerialState")
    uart_rebaseline = script.index('-Stage "cleanup-uart-configure"', restore_def)
    uart_rebaseline_query = script.index('-Stage "cleanup-uart-query"', uart_rebaseline)
    assert restore_def < uart_rebaseline < uart_rebaseline_query
    assert "Assert-UartReadback -Payload $uart" in script[uart_rebaseline:cleanup]


def test_serial_protocol_query_preflights_preserve_simulator_contract() -> None:
    script = (REPO_ROOT / "scripts" / "live-serial-check.ps1").read_text(
        encoding="utf-8"
    )
    preflight_start = script.index("function Invoke-HardwareFreePreflight {")
    preflight_end = script.index("\nfunction Restore-SerialState {", preflight_start)
    preflight = script[preflight_start:preflight_end]

    for protocol in ("i2c", "spi", "can"):
        stage_start = preflight.index(
            f'Invoke-ModeCli -Stage "preflight-{protocol}-query" '
            f'-Command "serial-{protocol}"'
        )
        stage_end = preflight.find("\n    Invoke-ModeCli", stage_start + 1)
        if stage_end == -1:
            stage_end = len(preflight)
        stage = preflight[stage_start:stage_end]
        assert "-ModeArguments $dryRun" in stage
        assert "-ModeArguments $simulate" not in stage

        command = [
            sys.executable,
            "-m",
            "scopes_tool_cli.cli",
            f"serial-{protocol}",
            "--simulate",
            "--model",
            "keysight-dsox4034a",
            "--json",
            "--bus",
            "1",
            "--query",
        ]
        simulated = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert simulated.returncode != 0
        simulated_payload = json.loads(simulated.stdout)
        assert simulated_payload["ok"] is False
        assert simulated_payload["error"]["message"] == (
            f"Serial bus 1 is in mode 'uart'; expected '{protocol}'."
        )

        command[command.index("--simulate")] = "--dry-run"
        dry_run = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert dry_run.returncode == 0, dry_run.stderr
        dry_run_payload = json.loads(dry_run.stdout)
        assert dry_run_payload["ok"] is True
        assert dry_run_payload["mode"] == "dry_run"
        assert dry_run_payload["result"]["operation"] == "query"


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize("scenario", ["completed", "timeout", "single-failure"])
@pytest.mark.parametrize(
    "serial_display_enabled", [True, False], ids=["display-on", "display-off"]
)
def test_serial_lister_export_waits_for_fresh_acquisition(
    tmp_path: Path, scenario: str, serial_display_enabled: bool
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-serial-check.ps1"
    output_path = tmp_path / "uart-lister.csv"
    harness_path = tmp_path / "serial-lister-export-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [string] $OutputPath,

    [Parameter(Mandatory = $true)]
    [ValidateSet("completed", "timeout", "single-failure")]
    [string] $Scenario,

    [Parameter(Mandatory = $true)]
    [ValidateSet(0, 1)]
    [int] $SerialDisplayEnabledValue
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse Serial live script: $($parseErrors[0].Message)"
}

$requiredValueFunction = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Get-RequiredResultValue"
    )
}, $true)
if ($null -eq $requiredValueFunction) {
    throw "Get-RequiredResultValue was not found in ${ScriptPath}."
}
Invoke-Expression $requiredValueFunction.Extent.Text

$listerCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.Extent.Text.Contains('Invoke-SerialCase -Name "UART Lister export"')
    )
}, $true))
if ($listerCommands.Count -ne 1) {
    throw "Expected one production UART Lister export command."
}

$script:CaseStatus = ""
$script:CaseDetail = ""
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:Sleeps = New-Object System.Collections.Generic.List[int]
$script:StatusIndex = 0
$script:ListerAcquisitionStarted = $false
$script:ListerAcquisitionTimeoutMilliseconds = 500
$script:ListerAcquisitionPollIntervalMilliseconds = 1
$script:OperationConditionRunMask = 8
$Resource = "TEST::INSTR"
$script:LiveConnectionArguments = @("--live", "--resource", $Resource)
$script:RunRoot = Split-Path -Parent $OutputPath
$snapshot = [pscustomobject]@{
    SerialDisplayEnabled = $SerialDisplayEnabledValue -eq 1
    WasRunning = $true
    OperationStatus = [pscustomobject]@{
        ok = $true
        command = "system-operation-status"
        result = [pscustomobject]@{
            operation = "query"
            command = ":OPERegister:CONDition?"
            value = 56
            raw = "+56"
            set_bits = @(3, 4, 5)
        }
    }
}

function Invoke-SerialCase {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [scriptblock] $Action
    )

    try {
        & $Action
        $script:CaseStatus = "PASS"
    } catch {
        $script:CaseStatus = "FAIL"
        $script:CaseDetail = $_.Exception.Message
    }
}

function Start-Sleep {
    param(
        [Parameter(Mandatory = $true)]
        [int] $Milliseconds
    )

    $script:Sleeps.Add($Milliseconds)
    $script:Invocations.Add([pscustomobject]@{
        stage = "sleep"
        command = "Start-Sleep"
        arguments = @([string]$Milliseconds)
    })
    [System.Threading.Thread]::Sleep($Milliseconds)
}

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $Command,

        [string[]] $Arguments = @()
    )

    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    if ($Command -eq "single" -and $Scenario -eq "single-failure") {
        throw "single rejected"
    }
    if ($Command -eq "serial-lister-query") {
        return [pscustomobject]@{
            result = [pscustomobject]@{
                display = "bus1"
                reference = "trigger"
            }
        }
    }
    if ($Command -eq "serial-display") {
        return [pscustomobject]@{
            result = [pscustomobject]@{ enabled = $true }
        }
    }
    if ($Command -eq "system-operation-status") {
        $value = if ($Scenario -eq "completed" -and $script:StatusIndex -gt 0) {
            48
        } else {
            56
        }
        $script:StatusIndex += 1
        return [pscustomobject]@{
            ok = $true
            command = "system-operation-status"
            result = [pscustomobject]@{
                operation = "query"
                command = ":OPERegister:CONDition?"
                value = $value
                raw = "+${value}"
                set_bits = if ($value -eq 56) { @(3, 4, 5) } else { @(4, 5) }
            }
        }
    }
    return [pscustomobject]@{ result = [pscustomobject]@{} }
}

function Invoke-CliRaw {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Arguments[0]
        arguments = @($Arguments)
    })
    if ($Stage -ne "lister-export") {
        throw "Unexpected raw invocation stage: ${Stage}"
    }

    $bytes = [System.Text.Encoding]::UTF8.GetBytes(
        "bus,time,value`r`nSBUS1,0,1`r`n"
    )
    $outputIndex = [array]::IndexOf($Arguments, "--output")
    $actualOutputPath = $Arguments[$outputIndex + 1]
    [System.IO.File]::WriteAllBytes($actualOutputPath, $bytes)
    $reportedPath = (Get-Item -LiteralPath $actualOutputPath).FullName.ToUpperInvariant()
    return [pscustomobject]@{
        ExitCode = 0
        Payload = [pscustomobject]@{
            ok = $true
            result = [pscustomobject]@{
                bytes_written = $bytes.Length
                command = ":LISTer:DATA?"
            }
            files = @(
                [pscustomobject]@{ kind = "csv"; path = $reportedPath }
            )
        }
        Stderr = ""
        Command = "fake-cli serial-lister-export"
    }
}

Invoke-Expression $listerCommands[0].Extent.Text

$exportInvocations = @($script:Invocations | Where-Object {
    $_.command -eq "serial-lister-export"
})
$outputExists = Test-Path -LiteralPath $OutputPath -PathType Leaf
$outputBytes = if ($outputExists) {
    (Get-Item -LiteralPath $OutputPath).Length
} else {
    0
}
$operationStatusPath = Join-Path $script:RunRoot "system-operation-status.json"
$operationStatusExists = Test-Path -LiteralPath $operationStatusPath -PathType Leaf
$operationStatusArtifact = if ($operationStatusExists) {
    Get-Content -LiteralPath $operationStatusPath -Raw | ConvertFrom-Json
} else {
    $null
}
$acquisitionStatusPath = Join-Path $script:RunRoot "lister-acquisition-status.json"
$acquisitionStatusArtifact = Get-Content -LiteralPath $acquisitionStatusPath -Raw |
    ConvertFrom-Json
[ordered]@{
    status = $script:CaseStatus
    detail = $script:CaseDetail
    export_count = $exportInvocations.Count
    invocations = @($script:Invocations | ForEach-Object {
        [ordered]@{
            stage = $_.stage
            command = $_.command
            arguments = @($_.arguments)
        }
    })
    sleep_values = @($script:Sleeps | ForEach-Object { $_ })
    acquisition_started = $script:ListerAcquisitionStarted
    operation_status_exists = $operationStatusExists
    operation_status = $operationStatusArtifact
    acquisition_status = $acquisitionStatusArtifact
    output_exists = $outputExists
    output_bytes = $outputBytes
} | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-OutputPath",
            str(output_path),
            "-Scenario",
            scenario,
            "-SerialDisplayEnabledValue",
            "1" if serial_display_enabled else "0",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    commands = [entry["command"] for entry in result["invocations"]]
    expected_lister_prefix = [
        "serial-lister-display",
        "serial-lister-reference",
        "serial-lister-query",
        "single",
    ]
    expected_prefix = expected_lister_prefix
    if not serial_display_enabled:
        expected_prefix = ["serial-display"] + expected_lister_prefix
    assert commands[: len(expected_prefix)] == expected_prefix
    lister_display_index = 0
    if not serial_display_enabled:
        assert result["invocations"][0]["arguments"] == [
            "--bus",
            "1",
            "--enabled",
            "true",
        ]
        lister_display_index = 1
    assert result["invocations"][lister_display_index]["arguments"] == [
        "--selection",
        "bus1",
    ]
    lister_query_index = lister_display_index + 2
    assert commands.count("single") == 1
    if serial_display_enabled:
        assert all(
            entry["command"]
            not in {
                "serial-display",
                "run",
                "stop-acquisition",
                "force-trigger",
                "digitize",
            }
            for entry in result["invocations"]
        )
    else:
        assert commands.count("serial-display") == 1
        assert all(
            entry["command"]
            not in {"run", "stop-acquisition", "force-trigger", "digitize"}
            for entry in result["invocations"]
        )
    assert result["acquisition_status"]["was_running"] is True
    if scenario == "single-failure":
        assert result["status"] == "FAIL"
        assert "single rejected" in result["detail"]
        assert result["acquisition_started"] is False
        assert commands == expected_prefix
        assert result["export_count"] == 0
        assert result["operation_status_exists"] is False
        assert result["acquisition_status"]["outcome"] == "not-started"
        assert result["output_exists"] is False
        assert result["output_bytes"] == 0
    elif scenario == "completed":
        assert result["acquisition_started"] is True
        assert result["invocations"][lister_query_index + 2]["arguments"] == [
            "--query"
        ]
        assert result["sleep_values"]
        assert result["operation_status_exists"] is True
        assert result["acquisition_status"]["poll_samples"][0]["result"]["value"] == 56
        assert result["status"] == "PASS", result["detail"]
        assert result["detail"] == ""
        assert result["export_count"] == 1
        assert commands[-1] == "serial-lister-export"
        assert result["invocations"][-1]["arguments"][-2:] == [
            "--output",
            str(output_path),
        ]
        assert result["operation_status"]["result"] == {
            "operation": "query",
            "command": ":OPERegister:CONDition?",
            "value": 48,
            "raw": "+48",
            "set_bits": [4, 5],
        }
        assert result["acquisition_status"]["outcome"] == "completed"
        assert result["acquisition_status"]["poll_count"] == 2
        assert result["output_exists"] is True
        assert result["output_bytes"] > 0
    else:
        assert result["acquisition_started"] is True
        assert result["invocations"][lister_query_index + 2]["arguments"] == [
            "--query"
        ]
        assert result["sleep_values"]
        assert result["operation_status_exists"] is True
        assert result["acquisition_status"]["poll_samples"][0]["result"]["value"] == 56
        assert result["status"] == "FAIL"
        assert "did not complete within 500 ms" in result["detail"]
        assert result["export_count"] == 0
        assert result["acquisition_status"]["outcome"] == "timeout"
        assert result["output_exists"] is False
        assert result["output_bytes"] == 0


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize(
    "was_running", [True, False], ids=["original-run", "original-stop"]
)
@pytest.mark.parametrize("outcome", ["completed", "timeout", "not-started"])
def test_serial_cleanup_deterministically_restores_acquisition_state(
    tmp_path: Path, was_running: bool, outcome: str
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-serial-check.ps1"
    harness_path = tmp_path / f"serial-cleanup-{was_running}-{outcome}.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [ValidateSet(0, 1)]
    [int] $WasRunningValue,

    [Parameter(Mandatory = $true)]
    [string] $Outcome
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse Serial live script: $($parseErrors[0].Message)"
}
foreach ($name in @("Get-RequiredResultValue", "Restore-SerialState")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${name} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$script:OperationConditionRunMask = 8
$script:Invocations = New-Object System.Collections.Generic.List[object]
$Resource = "TEST::INSTR"
$WasRunning = $WasRunningValue -eq 1
$snapshot = [pscustomobject]@{ WasRunning = $WasRunning }

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,
        [Parameter(Mandatory = $true)]
        [string] $Command,
        [string[]] $Arguments = @()
    )
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    if ($Command -eq "system-operation-status") {
        $value = if ($WasRunning) { 56 } else { 48 }
        return [pscustomobject]@{
            result = [pscustomobject]@{
                value = $value
                raw = "+${value}"
                set_bits = if ($WasRunning) { @(3, 4, 5) } else { @(4, 5) }
            }
        }
    }
    return [pscustomobject]@{ result = [pscustomobject]@{} }
}

function Drain-AfterFailure { throw "Unexpected cleanup failure drain." }

$restoreAcquisition = $Outcome -ne "not-started"
Restore-SerialState -Snapshot $snapshot -DisableSearch $false `
    -RestoreLister $false -RestoreSerialDisplay $false -RestoreTrigger $false `
    -RestoreAcquisition $restoreAcquisition

[ordered]@{
    outcome = $Outcome
    commands = @($script:Invocations | ForEach-Object { $_.command })
    stages = @($script:Invocations | ForEach-Object { $_.stage })
} | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-WasRunningValue",
            "1" if was_running else "0",
            "-Outcome",
            outcome,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    expected_command = "run" if was_running else "stop-acquisition"
    assert result["outcome"] == outcome
    if outcome == "not-started":
        assert result["commands"] == []
        assert result["stages"] == []
    else:
        assert result["commands"] == [expected_command, "system-operation-status"]
        assert result["stages"] == [
            f"cleanup-acquisition-{expected_command}",
            "cleanup-acquisition-status",
        ]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize(
    "scenario, original_enabled",
    [
        ("original-on", True),
        ("original-off", False),
        ("restore-failure", False),
    ],
    ids=["original-on", "original-off", "restore-failure"],
)
def test_serial_cleanup_restores_serial_display_state(
    tmp_path: Path, scenario: str, original_enabled: bool
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-serial-check.ps1"
    harness_path = tmp_path / f"serial-display-cleanup-{scenario}.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [ValidateSet("original-on", "original-off", "restore-failure")]
    [string] $Scenario,

    [Parameter(Mandatory = $true)]
    [ValidateSet(0, 1)]
    [int] $OriginalEnabledValue
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw ("Failed to parse Serial live script: " + $parseErrors[0].Message)
}
foreach ($name in @("Get-RequiredResultValue", "Restore-SerialState")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw ("Missing function: " + $name)
    }
    Invoke-Expression $functionAst.Extent.Text
}

$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:DrainCalls = New-Object System.Collections.Generic.List[object]
$script:DisplayState = $OriginalEnabledValue -eq 1
$snapshot = [pscustomobject]@{
    SerialDisplayEnabled = $script:DisplayState
}

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $Command,

        [string[]] $Arguments = @()
    )

    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    if ($Scenario -eq "restore-failure" -and
        $Stage -eq "cleanup-serial-display") {
        throw "display restore rejected"
    }
    if ($Command -ne "serial-display") {
        throw ("Unexpected cleanup command: " + $Command)
    }
    if ($Arguments -contains "--enabled") {
        $script:DisplayState = $Arguments[3] -eq "true"
    }
    return [pscustomobject]@{
        result = [pscustomobject]@{
            enabled = $script:DisplayState
        }
    }
}

function Drain-AfterFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $CaseName
    )
    $script:DrainCalls.Add([pscustomobject]@{
        stage = $Stage
        case_name = $CaseName
    })
}

$restoreError = ""
try {
    Restore-SerialState -Snapshot $snapshot -DisableSearch $false -RestoreLister $false -RestoreSerialDisplay $true -RestoreTrigger $false -RestoreAcquisition $false
} catch {
    $restoreError = $_.Exception.Message
}

[ordered]@{
    scenario = $Scenario
    initial_enabled = $OriginalEnabledValue -eq 1
    final_enabled = $script:DisplayState
    commands = @($script:Invocations | ForEach-Object { $_.command })
    arguments = @($script:Invocations | ForEach-Object { ,@($_.arguments) })
    stages = @($script:Invocations | ForEach-Object { $_.stage })
    drain_calls = @($script:DrainCalls | ForEach-Object {
        [ordered]@{ stage = $_.stage; case_name = $_.case_name }
    })
    restore_error = $restoreError
} | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-Scenario",
            scenario,
            "-OriginalEnabledValue",
            "1" if original_enabled else "0",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["scenario"] == scenario
    assert result["initial_enabled"] is original_enabled
    if scenario == "restore-failure":
        assert result["final_enabled"] is False
        assert result["commands"] == ["serial-display"]
        assert result["stages"] == ["cleanup-serial-display"]
        assert result["drain_calls"] == [
            {
                "stage": "cleanup-serial-display-error-drain",
                "case_name": "cleanup",
            }
        ]
        assert "Serial display: display restore rejected" in result["restore_error"]
    else:
        expected_text = "true" if original_enabled else "false"
        assert result["final_enabled"] is original_enabled
        assert result["commands"] == ["serial-display", "serial-display"]
        assert result["stages"] == [
            "cleanup-serial-display",
            "cleanup-serial-display-query",
        ]
        assert result["arguments"] == [
            ["--bus", "1", "--enabled", expected_text],
            ["--bus", "1", "--query"],
        ]
        assert result["drain_calls"] == []
        assert result["restore_error"] == ""


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_serial_search_and_trigger_cases_do_not_acquire(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-serial-check.ps1"
    harness_path = tmp_path / "serial-search-trigger-no-acquire.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse Serial live script: $($parseErrors[0].Message)"
}
$functionNames = @(
    "Get-RequiredResultValue",
    "Assert-SerialCriteriaReadback",
    "Assert-I2cCriteriaReadback",
    "Assert-SpiCriteriaReadback",
    "Assert-CanCriteriaReadback"
)
foreach ($name in $functionNames) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
        )
    }, $true)
    Invoke-Expression $functionAst.Extent.Text
}

$expectedCaseNames = @(
    'Invoke-SerialCase -Name "UART Serial Search"',
    'Invoke-SerialCase -Name "UART Serial Trigger"',
    'Invoke-SerialCase -Name "I2C Serial Search"',
    'Invoke-SerialCase -Name "I2C Serial Trigger"',
    'Invoke-SerialCase -Name "SPI Serial Search"',
    'Invoke-SerialCase -Name "SPI Serial Trigger"',
    'Invoke-SerialCase -Name "CAN Serial Search"',
    'Invoke-SerialCase -Name "CAN Serial Trigger"'
)
$caseCommands = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.CommandAst]) {
        return $false
    }
    foreach ($caseName in $expectedCaseNames) {
        if ($node.Extent.Text.Contains($caseName)) {
            return $true
        }
    }
    return $false
}, $true))
if ($caseCommands.Count -ne 8) {
    throw "Expected 8 Serial Search and Trigger cases, found $($caseCommands.Count)."
}

$script:Invocations = New-Object System.Collections.Generic.List[object]
function Invoke-SerialCase {
    param([string] $Name, [scriptblock] $Action)
    & $Action
}
function Start-Sleep { param([int] $Milliseconds) }
function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    if ($Command -eq "serial-search-uart") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "uart"; bus = 1; selected = $true
            mode = "rx-data"; data = 1; qualifier = "equal"
        }}
    }
    if ($Command -eq "serial-trigger-uart") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "uart"; bus = 1; selected = $true
            type = "rx-data"; data = 1; qualifier = "equal"
        }}
    }
    if ($Command -eq "serial-search-i2c") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "i2c"; bus = 1; selected = $true
            mode = "read7"; address = 80; data = 1; qualifier = "equal"
        }}
    }
    if ($Command -eq "serial-trigger-i2c") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "i2c"; bus = 1; selected = $true
            type = "read7"; address = 80; data = 1
        }}
    }
    if ($Command -eq "serial-search-spi") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "spi"; bus = 1; selected = $true
            mode = "mosi"; width = 1; data = "0x01"
        }}
    }
    if ($Command -eq "serial-trigger-spi") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "spi"; bus = 1; selected = $true
            type = "mosi"; width = 8; data = "00000001"
        }}
    }
    if ($Command -eq "serial-search-can") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "can"; bus = 1; selected = $true
            mode = "data"; id_mode = "standard"; id = "0x123"
            data = "0x01"; data_length = 1
        }}
    }
    if ($Command -eq "serial-trigger-can") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "can"; bus = 1; selected = $true
            type = "id-and-data"; id_mode = "standard"
            id = "00000000000000000000100100011"
            data = "00000001"; data_length = 1
        }}
    }
    throw "Unexpected live command: ${Command}"
}

foreach ($caseCommand in $caseCommands) {
    Invoke-Expression $caseCommand.Extent.Text
}
@($script:Invocations | ForEach-Object { $_ }) |
    ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    invocations = json.loads(completed.stdout)
    commands = [entry["command"] for entry in invocations]
    assert commands == [
        "serial-search-uart",
        "serial-search-uart",
        "serial-trigger-uart",
        "serial-trigger-uart",
        "serial-search-i2c",
        "serial-search-i2c",
        "serial-trigger-i2c",
        "serial-trigger-i2c",
        "serial-search-spi",
        "serial-search-spi",
        "serial-trigger-spi",
        "serial-trigger-spi",
        "serial-search-can",
        "serial-search-can",
        "serial-trigger-can",
        "serial-trigger-can",
    ]
    assert not {
        "single",
        "run",
        "stop-acquisition",
        "force-trigger",
        "digitize",
        "serial-lister-export",
    }.intersection(commands)

    def arguments_for(command: str) -> list[list[str]]:
        return [entry["arguments"] for entry in invocations if entry["command"] == command]

    assert arguments_for("serial-search-spi") == [
        ["--bus", "1", "--mode", "mosi", "--width", "1", "--data", "0x01"],
        ["--bus", "1", "--query"],
    ]
    assert arguments_for("serial-trigger-spi") == [
        ["--bus", "1", "--type", "mosi", "--width", "8", "--data", "0x01"],
        ["--bus", "1", "--query"],
    ]
    assert arguments_for("serial-search-can") == [
        [
            "--bus", "1", "--mode", "data", "--id-mode", "standard",
            "--id", "0x123", "--data", "0x01", "--data-length", "1",
        ],
        ["--bus", "1", "--query"],
    ]
    assert arguments_for("serial-trigger-can") == [
        [
            "--bus", "1", "--type", "id-and-data", "--id-mode", "standard",
            "--id", "0x123", "--data", "0x01", "--data-length", "1",
        ],
        ["--bus", "1", "--query"],
    ]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize("script_path", LIVE_SCRIPTS, ids=lambda path: path.stem)
def test_live_summary_preserves_results_and_diagnostics(
    tmp_path: Path,
    script_path: Path,
) -> None:
    output_root = tmp_path / script_path.stem
    output_root.mkdir()
    harness_path = tmp_path / f"{script_path.stem}-summary-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [string] $OutputRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Shared finalize (invoked by extracted production failure paths) lives in the
# validation helpers/privacy helpers.
. (Join-Path (Split-Path -Parent $ScriptPath) "_validation_helpers.ps1")
. (Join-Path (Split-Path -Parent $ScriptPath) "_artifact_privacy.ps1")

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @(
    "Add-CaseResult",
    "Add-Diagnostic",
    "Write-DrainErrors",
    "Write-Summary"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

foreach ($drainBlock in @(
    [pscustomobject]@{
        VariableName = "StaleDrainBlock"
        Stage = "stale-error-drain"
    },
    [pscustomobject]@{
        VariableName = "FinalDrainBlock"
        Stage = "final-error-queue"
    }
)) {
    $expectedText = "Get-ErrorDrain -Stage `"$($drainBlock.Stage)`""
    $matchingBlocks = @($ast.FindAll({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.TryStatementAst] -and
            $node.Extent.Text.Contains($expectedText)
        )
    }, $true))
    if ($matchingBlocks.Count -ne 1) {
        throw "Expected one $($drainBlock.Stage) try block in ${ScriptPath}."
    }
    Set-Variable -Name $drainBlock.VariableName -Value $matchingBlocks[0].Extent.Text
}

$scriptName = [System.IO.Path]::GetFileName($ScriptPath)
$usesBooleanCaseResult = $scriptName -eq "live-cli-check.ps1"
$supportsSkip = $scriptName -in @(
    "live-dvm-check.ps1",
    "live-segmented-check.ps1",
    "live-serial-check.ps1"
)
# Migrated validators' Write-Summary reports target/connection metadata.
$script:Target = "keysight-dsox4034a"
$script:Connection = "usb"
$script:BackendName = "system_visa"
# Extracted production drain blocks may invoke the shared finalize on their
# failure paths; provide a disposable run layout for those calls.
$Resource = "TEST::INSTR"
$RepoRoot = Split-Path -Parent $ScriptPath
$RepoRoot = Split-Path -Parent $RepoRoot
$scratchLayout = New-ValidationRunDirectory -BaseRoot $OutputRoot -Prefix "scratch"
$script:RunDirectory = $scratchLayout.Root
$script:RunRoot = $scratchLayout.Private
$script:ShareableRoot = $scratchLayout.Shareable
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:HardwareTouched = $false
$script:ShareableGenerationFailed = $false

$script:RunRoot = Join-Path $OutputRoot "pass"
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
if ($usesBooleanCaseResult) {
    Add-CaseResult -Name "preflight" -Passed $true
} else {
    Add-CaseResult -Name "preflight" -Status "PASS"
}
Write-DrainErrors -Errors @(
    [pscustomobject]@{ code = -350; message = "stale diagnostic" }
) -CaseName "stale-error-drain"
Write-Summary -Result "PASS"

$script:RunRoot = Join-Path $OutputRoot "fail"
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
if ($usesBooleanCaseResult) {
    Add-CaseResult -Name "functional-case" -Passed $false `
        -Detail "known failure detail"
} else {
    Add-CaseResult -Name "functional-case" -Status "FAIL" `
        -Detail "known failure detail"
}
Write-Summary -Result "FAIL"

$script:RunRoot = Join-Path $OutputRoot "scpi-fail"
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
if ($usesBooleanCaseResult) {
    Add-CaseResult -Name "final-error-queue" -Passed $false `
        -Detail "Final error queue contained 1 error(s)."
} else {
    Add-CaseResult -Name "final-error-queue" -Status "FAIL" `
        -Detail "Final error queue contained 1 error(s)."
}
Write-DrainErrors -Errors @(
    [pscustomobject]@{ code = -222; message = "known diagnostic" }
) -CaseName "final-error-queue"
Write-Summary -Result "FAIL"

function Get-ErrorDrain {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage
    )

    $errorEntry = switch ($Stage) {
        "stale-error-drain" {
            [pscustomobject]@{ code = -350; message = "unterminated stale diagnostic" }
        }
        "final-error-queue" {
            [pscustomobject]@{ code = -222; message = "unterminated final diagnostic" }
        }
        default {
            throw "Unexpected drain stage: ${Stage}"
        }
    }
    return [pscustomobject]@{
        Errors = @($errorEntry)
        Terminated = $false
    }
}

$script:RunRoot = Join-Path $OutputRoot "final-unterminated"
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
Invoke-Expression $FinalDrainBlock
Write-Summary -Result "FAIL"

if ($supportsSkip) {
    $script:RunRoot = Join-Path $OutputRoot "skip"
    New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
    $script:CaseResults = [ordered]@{}
    $script:Diagnostics = [ordered]@{}
    $scriptName = [System.IO.Path]::GetFileName($ScriptPath)
    $caseName = if ($scriptName -eq "live-dvm-check.ps1") {
        "availability"
    } elseif ($scriptName -eq "live-serial-check.ps1") {
        "availability"
    } else {
        "segmented memory"
    }
    Add-CaseResult -Name $caseName -Status "SKIP" `
        -Detail "NOT AVAILABLE: required option/license is not installed."
    Write-DrainErrors -Errors @(
        [pscustomobject]@{ code = -241; message = "option not installed" }
    ) -CaseName $caseName
    Write-Summary -Result "SKIP"
}

$script:RunRoot = Join-Path $OutputRoot "stale-unterminated"
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$initialDrainPassed = $false
Invoke-Expression $StaleDrainBlock
Write-Summary -Result "FAIL"
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-OutputRoot",
            str(output_root),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    expected_returncode = 0 if script_path.name == "live-cli-check.ps1" else 1
    assert completed.returncode == expected_returncode, completed.stderr
    assert "system error -222: known diagnostic" in completed.stdout

    pass_bytes = (output_root / "pass" / "summary.md").read_bytes()
    pass_summary = pass_bytes.decode("utf-8")
    assert not pass_bytes.startswith(b"\xef\xbb\xbf")
    assert "Result: PASS" in pass_summary
    assert "Backend: system_visa" in pass_summary
    assert "| preflight | PASS |" in pass_summary
    assert "### stale-error-drain" in pass_summary
    assert "system error -350: stale diagnostic" in pass_summary

    fail_bytes = (output_root / "fail" / "summary.md").read_bytes()
    fail_summary = fail_bytes.decode("utf-8")
    assert not fail_bytes.startswith(b"\xef\xbb\xbf")
    assert "Result: FAIL" in fail_summary
    assert "| functional-case | FAIL | known failure detail |" in fail_summary

    scpi_bytes = (output_root / "scpi-fail" / "summary.md").read_bytes()
    scpi_summary = scpi_bytes.decode("utf-8")
    assert not scpi_bytes.startswith(b"\xef\xbb\xbf")
    assert "Result: FAIL" in scpi_summary
    assert "| final-error-queue | FAIL |" in scpi_summary
    assert "Final error queue contained 1 error(s)." in scpi_summary
    assert "system error -222: known diagnostic" in scpi_summary

    stale_unterminated_bytes = (
        output_root / "stale-unterminated" / "summary.md"
    ).read_bytes()
    stale_unterminated_summary = stale_unterminated_bytes.decode("utf-8")
    assert not stale_unterminated_bytes.startswith(b"\xef\xbb\xbf")
    assert "Result: FAIL" in stale_unterminated_summary
    assert "| stale-error-drain | FAIL |" in stale_unterminated_summary
    assert (
        "Initial error queue did not reach code 0 within 30 reads."
        in stale_unterminated_summary
    )
    assert "system error -350: unterminated stale diagnostic" in (
        stale_unterminated_summary
    )

    final_unterminated_bytes = (
        output_root / "final-unterminated" / "summary.md"
    ).read_bytes()
    final_unterminated_summary = final_unterminated_bytes.decode("utf-8")
    assert not final_unterminated_bytes.startswith(b"\xef\xbb\xbf")
    assert "Result: FAIL" in final_unterminated_summary
    assert "| final-error-queue | FAIL |" in final_unterminated_summary
    assert (
        "Final error queue did not reach code 0 within 30 reads."
        in final_unterminated_summary
    )
    assert "system error -222: unterminated final diagnostic" in (
        final_unterminated_summary
    )

    if script_path.name in {
        "live-dvm-check.ps1",
        "live-segmented-check.ps1",
        "live-serial-check.ps1",
    }:
        skip_bytes = (output_root / "skip" / "summary.md").read_bytes()
        skip_summary = skip_bytes.decode("utf-8")
        assert not skip_bytes.startswith(b"\xef\xbb\xbf")
        assert "Result: SKIP" in skip_summary
        assert "| SKIP | NOT AVAILABLE:" in skip_summary
        assert "system error -241: option not installed" in skip_summary


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize("script_path", LIVE_SCRIPTS, ids=lambda path: path.stem)
def test_live_preflight_failure_writes_summary_before_hardware_access(
    tmp_path: Path,
    script_path: Path,
) -> None:
    fake_package = tmp_path / "fake_cli" / "scopes_tool_cli"
    fake_package.mkdir(parents=True)
    (fake_package / "__init__.py").write_text("", encoding="utf-8")
    (fake_package / "cli.py").write_text(
        """\
import json
import os
from pathlib import Path
import sys

log_path = Path(os.environ["SCOPES_TOOL_FAKE_CLI_LOG"])
with log_path.open("a", encoding="utf-8") as log_file:
    log_file.write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({"ok": False, "error": {"message": "known preflight failure"}}))
print("known preflight diagnostic", file=sys.stderr)
sys.exit(9)
""",
        encoding="utf-8",
    )

    output_root = tmp_path / "artifacts"
    invocation_log = tmp_path / "fake-cli-invocations.jsonl"
    # All migrated validators take the canonical Target/Connection contract,
    # validate Connection against the resource transport, and write
    # private/report.json + private/summary.md before any live access.
    script_args = [
        "-Resource",
        "USB0::1::2::SYNTH12345::INSTR",
        "-Target",
        "keysight-dsox4034a",
        "-Connection",
        "usb",
        "-Python",
        sys.executable,
    ]
    script_args += ["-OutputRoot", str(output_root)]
    environment = os.environ.copy()
    python_path = str(fake_package.parent)
    if environment.get("PYTHONPATH"):
        python_path += os.pathsep + environment["PYTHONPATH"]
    environment["PYTHONPATH"] = python_path
    environment["SCOPES_TOOL_FAKE_CLI_LOG"] = str(invocation_log)

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            *script_args,
        ],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1, completed.stderr
    assert "No live hardware was accessed." in completed.stdout
    run_roots = [path for path in output_root.iterdir() if path.is_dir()]
    assert len(run_roots) == 1
    summary_path = run_roots[0] / "private" / "summary.md"
    summary_bytes = summary_path.read_bytes()
    summary = summary_bytes.decode("utf-8")
    assert not summary_bytes.startswith(b"\xef\xbb\xbf")
    assert "Result: FAIL" in summary
    assert "| preflight | FAIL |" in summary
    assert "| preflight | FAIL |  |" not in summary
    report_path = run_roots[0] / "private" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["hardware_touched"] is False
    assert report["backend"] == "system_visa"

    invocations = [
        json.loads(line)
        for line in invocation_log.read_text(encoding="utf-8").splitlines()
    ]
    assert invocations
    assert all("--live" not in arguments for arguments in invocations)


@requires_windows
@pytest.mark.parametrize("script_path", LIVE_SCRIPTS, ids=lambda path: path.stem)
@pytest.mark.parametrize(
    ("backend", "expected_arguments"),
    (
        pytest.param(
            "",
            ["--live", "--resource", "TEST::INSTR"],
            id="system-visa",
        ),
        pytest.param(
            "@py",
            [
                "--live",
                "--resource",
                "TEST::INSTR",
                "--visa-library",
                "@py",
            ],
            id="pyvisa-py",
        ),
    ),
)
def test_live_backend_arguments_reach_commands_and_error_drains(
    tmp_path: Path,
    script_path: Path,
    backend: str,
    expected_arguments: list[str],
) -> None:
    harness_path = tmp_path / f"{script_path.stem}-backend-harness.ps1"
    harness_path.write_text(
        r'''param(
    [Parameter(Mandatory = $true)][string] $ScriptPath,
    [AllowEmptyString()][string] $Backend
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $ScriptPath) "_validation_helpers.ps1")

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Invoke-LiveCli", "Get-ErrorDrain")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "${functionName} was not found." }
    Invoke-Expression $functionAst.Extent.Text
}

function Invoke-ModeCli {
    param(
        [string] $Stage,
        [string] $Command,
        [string[]] $ModeArguments,
        [string[]] $Arguments = @()
    )
    $script:CommandArguments = @($ModeArguments)
    return [pscustomobject]@{ Payload = [pscustomobject]@{} }
}

function Invoke-CliRaw {
    param([string] $Stage, [string[]] $Arguments)
    $script:DrainArguments = @($Arguments)
    return [pscustomobject]@{
        Payload = [pscustomobject]@{
            result = [pscustomobject]@{
                entries = @([pscustomobject]@{ code = 0; message = "No error" })
            }
        }
    }
}

$script:LiveConnectionArguments = @(
    Get-LiveConnectionArguments -Resource "TEST::INSTR" -Backend $Backend
)
$script:HardwareTouched = $false
[void](Invoke-LiveCli -Stage "identity" -Command "identify")
[void](Get-ErrorDrain -Stage "final-error-queue")

[ordered]@{
    command_arguments = @($script:CommandArguments)
    drain_arguments = @($script:DrainArguments)
    hardware_touched = $script:HardwareTouched
} | ConvertTo-Json -Depth 5 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-Backend",
            backend,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["command_arguments"] == expected_arguments
    assert payload["drain_arguments"] == [
        "check-error",
        *expected_arguments,
        "--json",
        "--all",
        "--max-reads",
        "30",
    ]
    assert payload["hardware_touched"] is True


def test_live_scripts_use_shared_backend_arguments_for_live_invocations() -> None:
    for script_path in LIVE_SCRIPTS:
        script = script_path.read_text(encoding="utf-8")
        assert '[Alias("VisaLibrary")]' in script
        assert script.count("Get-LiveConnectionArguments -Resource $Resource") == 1
        assert '"--live"' not in script


def test_baseline_live_script_contains_acquisition_measurement_and_status_wiring() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    for case_name in (
        "run",
        "stop-acquisition",
        "single",
        "force-trigger",
        "capture-wait-trigger",
        "trigger-holdoff",
        "acquisition-average",
        "acquisition-high-resolution",
        "acquisition-peak",
        "acquisition-queries",
        "system-status",
        "measurements",
        "measure-phase",
        "measure-delay",
        "measure-stats",
        "measure-controls",
        "cursor-lifecycle",
        "measure-results",
        "channel-summary",
    ):
        assert f'Invoke-BaselineCase -Name "{case_name}"' in script

    for command in (
        'Command "sample-rate"',
        'Command "acquisition-points"',
        'Command "record-length"',
        'Command "system-opc"',
        'Command "system-status-byte"',
        'Command "system-operation-status"',
        'Command "system-standard-event"',
        'Command "system-options"',
        'Command "run"',
        'Command "stop-acquisition"',
        'Command "single"',
        'Command "force-trigger"',
        'Command "capture"',
        'Command "trigger-holdoff"',
        'Command "measure"',
        'Command "measure-stats"',
        'Command "measure-clear"',
        'Command "measure-show"',
        'Command "measure-source"',
        'Command "measure-window"',
        'Command "cursor"',
        'Command "measure-results"',
        'Command "channel-summary"',
    ):
        assert command in script

    assert "$identity.capabilities.supports_measure_results_dump" in script
    assert '@("--type", "average", "--count", "16")' in script
    assert '@("--type", "high_resolution")' in script
    assert '@("--type", "peak")' in script
    assert '@("--type", "normal")' in script

    system_status_start = script.index(
        'Invoke-BaselineCase -Name "system-status"'
    )
    system_status_end = script.index(
        "\n    if (-not $script:FunctionalFailed -and", system_status_start
    )
    system_status_case = script[system_status_start:system_status_end]
    assert '"system-standard-event"' in system_status_case
    assert "*ESR?" in system_status_case

    screenshot_start = script.index('Invoke-BaselineCase -Name "screenshot-bmp"')
    screenshot_end = script.index(
        "\n    if (-not $script:FunctionalFailed", screenshot_start + 1
    )
    screenshot_case = script[screenshot_start:screenshot_end]
    assert 'Add-NotApplicableCase -Name "screenshot-bmp"' in screenshot_case

    for case_name in (
        "run",
        "single",
        "force-trigger",
        "capture-wait-trigger",
    ):
        case_start = script.index(f'Invoke-BaselineCase -Name "{case_name}"')
        case_end = script.index(
            "\n    if (-not $script:FunctionalFailed", case_start + 1
        )
        case_block = script[case_start:case_end]
        assert 'Command "stop-acquisition"' in case_block

    force_start = script.index('Invoke-BaselineCase -Name "force-trigger"')
    force_end = script.index(
        "\n    if (-not $script:FunctionalFailed", force_start + 1
    )
    force_case = script[force_start:force_end]
    assert force_case.index('Stage "force-trigger-run"') < force_case.index(
        'Stage "force-trigger"'
    )
    assert force_case.index('Command "run"') < force_case.index(
        'Command "force-trigger"'
    )
    assert force_case.index('Command "force-trigger"') < force_case.index(
        'Command "stop-acquisition"'
    )
    assert 'Command "single"' not in force_case

    cursor_start = script.index('Invoke-BaselineCase -Name "cursor-lifecycle"')
    cursor_end = script.index(
        "\n    if (-not $script:FunctionalFailed", cursor_start + 1
    )
    cursor_case = script[cursor_start:cursor_end]
    assert cursor_case.index('Stage "cursor-off"') < cursor_case.index(
        'Stage "cursor-off-query"'
    )
    assert 'Arguments @("--off")' in cursor_case
    assert ':MARKer:MODE MANual' in cursor_case
    assert ':MARKer:MODE TIME' not in cursor_case

    lifecycle_markers = [
        script.index('Invoke-BaselineCase -Name "fixture-baseline"'),
        script.index('Invoke-BaselineCase -Name "save-pwd-fixture"'),
        script.index('Invoke-BaselineCase -Name "save-pwd"'),
        script.index('Invoke-BaselineCase -Name "save-settings"'),
        script.index('Invoke-BaselineCase -Name "save-export"'),
        script.index('Invoke-BaselineCase -Name "acquisition"'),
        script.index('Invoke-BaselineCase -Name "single"'),
        script.index('Invoke-BaselineCase -Name "capture-wait-trigger"'),
    ]
    assert lifecycle_markers == sorted(lifecycle_markers)
    for case_name in (
        "save-pwd-fixture",
        "save-pwd",
        "save-settings",
        "save-export",
    ):
        assert (
            script.count(f'Invoke-BaselineCase -Name "{case_name}"') == 1
        )
    assert script.index("Invoke-FixtureBaseline") < lifecycle_markers[0]

    pair_start = script.index("$pairMeasurementSnapshot = $null")
    pair_end = script.index(
        'Invoke-BaselineCase -Name "measure-stats"', pair_start
    )
    pair_lifecycle = script[pair_start:pair_end]
    for stage in (
        'Stage "pair-ch2-snapshot-display"',
        'Stage "pair-ch2-snapshot-coupling"',
        'Stage "pair-ch2-snapshot-scale"',
        'Stage "pair-ch2-snapshot-offset"',
        'Stage "pair-ch2-snapshot-probe"',
        'Stage "pair-ch2-prepare-display"',
        'Stage "pair-ch2-prepare-coupling"',
        'Stage "pair-ch2-prepare-scale"',
        'Stage "pair-ch2-prepare-offset"',
        'Stage "measure-ch2-readiness"',
    ):
        assert stage in script
    assert "Prepare-PairMeasurementChannel" in pair_lifecycle
    assert "Invoke-StrictPairMeasurement" in pair_lifecycle
    assert "Invoke-PairMeasurementReadiness" in pair_lifecycle
    assert "Restore-PairMeasurementChannel" in pair_lifecycle
    assert pair_lifecycle.index("Prepare-PairMeasurementChannel") < pair_lifecycle.index(
        'Stage "pair-measurement-run"'
    )
    assert pair_lifecycle.index('Stage "pair-measurement-run"') < pair_lifecycle.index(
        "Invoke-PairMeasurementReadiness"
    )
    assert pair_lifecycle.index("Invoke-PairMeasurementReadiness") < pair_lifecycle.index(
        'Invoke-BaselineCase -Name "measure-phase"'
    )
    assert pair_lifecycle.index('Invoke-BaselineCase -Name "measure-phase"') < pair_lifecycle.index(
        'Invoke-BaselineCase -Name "measure-delay"'
    )
    assert pair_lifecycle.index('Invoke-BaselineCase -Name "measure-delay"') < pair_lifecycle.index(
        'Stage "pair-measurement-stop"'
    )
    assert pair_lifecycle.index('Stage "pair-measurement-stop"') < pair_lifecycle.index(
        "Restore-PairMeasurementChannel"
    )
    assert 'Command "run"' in pair_lifecycle
    assert 'ExpectedCommands @(":RUN")' in pair_lifecycle
    assert 'Command "stop-acquisition"' in pair_lifecycle
    assert 'ExpectedCommands @(":STOP")' in pair_lifecycle
    assert "pair-ch2-restore-$($step.Kind)-query" in script
    assert "invalid measurement sentinels are not accepted" in script
    prompt_start = script.index('Write-Host "PHYSICAL SETUP  operator must prepare"')
    prompt_fixture_start = script.index('Write-Host "FIXTURE POLICY"', prompt_start)
    prompt_cleanup_start = script.index(
        'Write-Host "Press Enter only after the PHYSICAL SETUP above is ready."',
        prompt_fixture_start,
    )
    prompt = script[prompt_start : prompt_cleanup_start + 1000]
    assert prompt.index("PHYSICAL SETUP") < prompt.index("THE VALIDATOR WILL CONFIGURE")
    assert prompt.index("THE VALIDATOR WILL CONFIGURE") < prompt.index("FIXTURE POLICY")
    for required_prompt_text in (
        "CH1 probe -> Probe Demo / Probe Comp",
        "CH2 probe -> same Probe Demo / Probe Comp",
        "stable Probe Comp waveforms are visible",
        "physical attenuation must match",
        "Insert writable USB storage",
        "CH1 vertical scale = 2 V/div",
        "trigger = Edge / CH1 / Positive / 1 V",
        "fixed laboratory validation fixture",
        "does not adapt an incorrect physical fixture",
        "Timebase mode = MAIN / normal horizontal timebase",
        "Press Enter only after the PHYSICAL SETUP above is ready",
    ):
        assert required_prompt_text in prompt
    assert "measure minimum" not in script
    assert "measure maximum" not in script
    assert "midpoint" not in script.lower()
    assert "autoscale fallback" not in script.lower()
    assert "--force-trigger-on-timeout" not in script[
        script.index('Invoke-BaselineCase -Name "capture-wait-trigger"'):
        script.index('Invoke-BaselineCase -Name "trigger-holdoff"')
    ]
    readiness_start = script.index("function Invoke-PairMeasurementReadiness")
    readiness_end = script.index("function Get-PairMeasurementChannelSnapshot", readiness_start)
    readiness = script[readiness_start:readiness_end]
    assert "while ($elapsedMilliseconds -le $TimeoutMilliseconds)" in readiness
    assert "Start-Sleep -Milliseconds $sleepMilliseconds" in readiness
    assert "CH2 pair-measurement precondition did not become measurement-ready" in readiness
    assert "if ($systemErrorCode -ne 0)" in readiness
    assert "Invoke-StrictPairMeasurement" not in readiness

    for case_name, expected_query in (
        ("measure-phase", ":MEASure:PHASe? CHANnel1,CHANnel2"),
        ("measure-delay", ":MEASure:DELay? AUTO,CHANnel1,CHANnel2"),
    ):
        case_start = script.index(f'Invoke-BaselineCase -Name "{case_name}"')
        case_end = script.index(
            "\n    if (-not $script:FunctionalFailed", case_start + 1
        )
        case_block = script[case_start:case_end]
        assert expected_query in case_block
        assert ".result.valid" in case_block
        assert "Assert-FiniteNumber" in case_block
        assert "Invoke-StrictPairMeasurement" in case_block
        assert 'Command "channel-display"' not in case_block

    invoke_live_cli_start = script.index("function Invoke-LiveCli {")
    invoke_live_cli_end = script.index(
        "\nfunction Get-ErrorDrain {", invoke_live_cli_start
    )
    invoke_live_cli = script[invoke_live_cli_start:invoke_live_cli_end]
    assert '"--log-scpi"' not in invoke_live_cli


def test_baseline_live_script_contains_channel_display_search_and_restore_wiring() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    for case_name in (
        "channel-vertical",
        "channel-probe",
        "channel-advanced",
        "display-settings",
        "display-annotation",
        "search-basic",
        "search-event",
        "screenshot-bmp",
        "waveform-amp",
    ):
        assert f'Invoke-BaselineCase -Name "{case_name}"' in script

    for command in (
        "channel-label",
        "channel-scale",
        "channel-offset",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
        "display-label",
        "display-persistence",
        "display-intensity",
        "display-vectors",
        "annotation",
        "search-state",
        "search-mode",
        "search-count",
        "search-event",
    ):
        assert f'Command = "{command}"' in script or f'Command "{command}"' in script

    preflight_start = script.index("function Invoke-HardwareFreePreflight {")
    preflight_end = script.index("\nfunction Restore-InstrumentState {", preflight_start)
    preflight = script[preflight_start:preflight_end]
    for command in (
        "channel-label",
        "channel-scale",
        "channel-offset",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
        "display-label",
        "display-persistence",
        "display-intensity",
        "display-vectors",
        "annotation",
        "search-state",
        "search-mode",
        "search-count",
        "search-event",
    ):
        assert f'Command = "{command}"' in preflight
    assert '"--format", "bmp"' in preflight

    channel_vertical_start = script.index(
        'Invoke-BaselineCase -Name "channel-vertical"'
    )
    channel_vertical_end = script.index(
        '\n    if (-not $script:FunctionalFailed)', channel_vertical_start + 1
    )
    channel_vertical = script[channel_vertical_start:channel_vertical_end]
    assert channel_vertical.index('Stage "channel-vertical-scale-set"') < (
        channel_vertical.index('Stage "channel-vertical-scale-query"')
    )
    assert channel_vertical.index('Stage "channel-vertical-scale-query"') < (
        channel_vertical.index('Stage "channel-range-set"')
    )
    assert channel_vertical.index('Stage "channel-range-set"') < (
        channel_vertical.index('Stage "channel-range-query"')
    )
    assert '"--volts-per-division", "2"' in channel_vertical
    assert "-Expected 2.0" in channel_vertical
    assert "$snapshot.ChannelScale" not in channel_vertical

    assert '$identity.capabilities.supports_screenshot_hardcopy_controls' in script
    assert '$identity.capabilities.supports_search_event_navigation' in script
    assert '"edge" -in @($identity.capabilities.search_modes)' in script
    assert 'Stage "waveform-amp-unit-restore"' in script
    assert 'Stage "waveform-amp-unit-restore-query"' in script

    for case_name in (
        "channel-vertical",
        "channel-probe",
        "channel-advanced",
        "display-settings",
        "search-basic",
    ):
        case_start = script.index(f'Invoke-BaselineCase -Name "{case_name}"')
        case_end = script.index(
            "\n    if (-not $script:FunctionalFailed", case_start + 1
        )
        case_block = script[case_start:case_end]
        assert ".result.command" not in case_block
        assert ".result.commands" not in case_block

    restore_start = script.index("function Restore-InstrumentState {")
    restore_end = script.index("\nif ([string]::IsNullOrWhiteSpace", restore_start)
    restore = script[restore_start:restore_end]
    for command in (
        "channel-label",
        "channel-scale",
        "channel-offset",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
        "display-label",
        "display-persistence",
        "display-intensity",
        "annotation",
        "search-state",
    ):
        assert f'Command = "{command}"' in restore


def test_baseline_live_script_contains_trigger_math_generator_save_and_safety_wiring() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    for case_name in (
        "trigger-edge-settings",
        "trigger-common",
        "trigger-external",
        "trigger-pulse-width",
        "trigger-runt",
        "trigger-transition",
        "trigger-delay",
        "trigger-setup-hold",
        "trigger-edge-burst",
        "trigger-tv",
        "trigger-pattern",
        "trigger-or",
        "math-operator",
        "math-transform",
        "math-display",
        "math-vertical",
        "math-composite-source",
        "math-filter",
        "math-visualization",
        "math-clear",
        "fft",
        "fft-advanced",
        "wgen-basic",
        "demo-basic",
        "demo-phase",
        "autoscale",
        "setup-lifecycle",
        "setup-slot-lifecycle",
        "reference-lifecycle",
        "save-settings",
        "save-export",
        "safe-cleanup",
    ):
        assert f'Invoke-BaselineCase -Name "{case_name}"' in script

    preflight_start = script.index("function Invoke-HardwareFreePreflight {")
    preflight_end = script.index("\nfunction Restore-InstrumentState {", preflight_start)
    preflight = script[preflight_start:preflight_end]
    for command in (
        "trigger-pulse-width",
        "trigger-runt",
        "trigger-transition",
        "trigger-delay",
        "trigger-setup-hold",
        "trigger-edge-burst",
        "trigger-tv",
        "trigger-pattern",
        "trigger-or",
        "trigger-edge-external-level",
        "math-operator",
        "math-transform",
        "fft",
        "wgen-output",
        "demo-output",
        "autoscale",
        "setup-save",
        "setup-recall",
        "save-image",
        "save-waveform",
        "cleanup",
    ):
        assert f'Command = "{command}"' in preflight

    assert '$snapshot.Is4000XSeries' in script
    assert '$snapshot.InstalledOptions = @($options.result.options)' in script
    assert '$snapshot.WgenApplicable = "WAVEGEN" -in @($snapshot.InstalledOptions)' in script
    assert '$snapshot.WgenApplicable' in script
    assert 'Waveform Generator option is not installed' in script
    system_status_start = script.index('Invoke-BaselineCase -Name "system-status"')
    system_status_end = script.index(
        '\n    if (-not $script:FunctionalFailed', system_status_start
    )
    system_status = script[system_status_start:system_status_end]
    assert system_status.count('-Command "system-options"') == 1
    assert 'ExpectedCommands @("*OPT?")' in system_status
    assert script.count('-Command "system-options"') == 1
    assert 'Stage "wgen-output-off"' in script
    assert 'Stage "demo-output-off"' in script
    assert 'Command = "wgen-output"' in script
    assert 'Command = "demo-output"' in script
    assert 'Command = "math-display"' in script
    assert '"--pattern", "XXX1"' in script
    assert '"--pattern", "XXXR"' in script
    assert '"disable_dvm"' in script
    assert '"disable_demo_output"' in script
    assert '":DVM:ENABle 0"' in script
    assert '":DEMO:OUTPut OFF"' in script
    assert '"disable_wgen"' in script
    assert '"wgen_not_implemented"' in script
    assert "Original save format context is not restorable." not in script
    assert "SaveFixtureEstablished" in script
    assert 'Stage "preflight-cli-save-waveform-length-max-query"' in preflight
    assert '-Command "save-waveform-length-max"' in preflight
    assert '-Arguments @("--query")' in preflight
    assert '-Stage "snapshot-save-waveform-length-max"' in script
    assert '-Command "save-waveform-length-max" -Arguments @("--query")' in script
    assert "SaveWaveformLengthMax = [bool]$saveWaveformLengthMax.result.enabled" in script
    assert '@("--format", "none")' not in script
    assert '"\\usb\\scopes-tool-live-${timestamp}.scp"' in script
    setup_slot_start = script.index('Invoke-BaselineCase -Name "setup-slot-lifecycle"')
    setup_slot_end = script.index(
        'Invoke-BaselineCase -Name "safe-cleanup"', setup_slot_start
    )
    setup_slot_case = script[setup_slot_start:setup_slot_end]
    assert 'Command "setup-save"' in setup_slot_case
    assert 'Command "setup-recall"' in setup_slot_case
    assert '"--slot", "1"' in setup_slot_case
    reference_start = script.index('Invoke-BaselineCase -Name "reference-lifecycle"')
    reference_end = script.index(
        'Invoke-BaselineCase -Name "setup-slot-lifecycle"', reference_start
    )
    reference_case = script[reference_start:reference_end]
    for stage in (
        'Stage "reference-run"',
        'Stage "reference-save"',
        'Stage "reference-display-query"',
        'Stage "reference-label-query"',
        'Stage "reference-clear"',
        'Stage "reference-stop"',
    ):
        assert stage in reference_case
    for command in (
        "run",
        "reference-save",
        "reference-query",
        "reference-display",
        "reference-label",
        "reference-clear",
        "stop-acquisition",
    ):
        assert f'Command "{command}"' in reference_case
    assert 'ExpectedCommands @(\":RUN\")' in reference_case
    assert 'ExpectedCommands @(\":STOP\")' in reference_case
    assert ':WMEMory1:SAVE CHANnel1' in reference_case
    assert '*OPC?' not in reference_case
    assert 'Start-Sleep' not in reference_case
    assert '$referenceFailure = $null' in reference_case
    assert 'Add-Diagnostic -Name "reference-lifecycle" -Message $stopMessage' in reference_case
    assert 'if ($null -eq $referenceFailure)' in reference_case
    assert 'Command "autoscale"' not in reference_case
    assert 'Command "channel-scale"' not in reference_case
    assert reference_case.index('Stage "reference-run"') < reference_case.index(
        "Invoke-ReferenceWaveformReadiness"
    )
    assert reference_case.index("Invoke-ReferenceWaveformReadiness") < reference_case.index(
        'Stage "reference-save"'
    )
    assert reference_case.index('Stage "reference-save"') < reference_case.index(
        'Stage "reference-display-on"'
    )
    assert reference_case.index('Stage "reference-display-query"') < reference_case.index(
        'Stage "reference-label-set"'
    )
    assert reference_case.index('Stage "reference-label-query"') < reference_case.index(
        'Stage "reference-clear"'
    )
    assert reference_case.index('Stage "reference-clear"') < reference_case.index(
        'Stage "reference-stop"'
    )

    reference_readiness_start = script.index("function Invoke-ReferenceWaveformReadiness")
    reference_readiness_end = script.index(
        "function Invoke-PairMeasurementReadiness", reference_readiness_start
    )
    reference_readiness = script[reference_readiness_start:reference_readiness_end]
    assert 'Stage "reference-ch1-readiness"' in reference_readiness
    assert '"--source-channel", "1"' in reference_readiness
    assert '"--item", "vpp"' in reference_readiness
    assert ':MEASure:VPP? CHANnel1' in reference_readiness
    assert "while ($elapsedMilliseconds -le $TimeoutMilliseconds)" in reference_readiness
    assert "Start-Sleep -Milliseconds $sleepMilliseconds" in reference_readiness
    assert "CH1 reference-waveform precondition did not become measurement-ready" in reference_readiness
    assert "if ($systemErrorCode -ne 0)" in reference_readiness
    save_pwd_start = script.index('Invoke-BaselineCase -Name "save-pwd"')
    save_settings_start = script.index('Invoke-BaselineCase -Name "save-settings"')
    save_settings_end = script.index(
        'Invoke-BaselineCase -Name "save-export"', save_settings_start
    )
    save_pwd_case = script[save_pwd_start:save_settings_start]
    save_settings_case = script[save_settings_start:save_settings_end]
    fixture_case_start = script.index('Invoke-BaselineCase -Name "save-pwd-fixture"')
    assert fixture_case_start < save_pwd_start
    assert 'Stage "save-pwd-fixture-query"' in script[fixture_case_start:save_pwd_start]
    assert 'Test-SavePathEquivalent' in script[fixture_case_start:save_pwd_start]
    assert '"\\usb"' in script[fixture_case_start:save_pwd_start]
    assert 'Stage "save-pwd-set"' in save_pwd_case
    assert 'Stage "save-pwd-query"' in save_pwd_case
    assert "save-pwd-restore" not in save_pwd_case
    for command in (
        "save-image-format",
        "save-filename",
        "save-image-palette",
        "save-image-ink-saver",
        "save-image-factors",
    ):
        assert f'Command "{command}"' in save_settings_case
    assert "finally" in save_settings_case
    configure_order = [
        save_settings_case.index('Stage "save-image-format-png"'),
        save_settings_case.index('Stage "save-filename-set"'),
        save_settings_case.index('Stage "save-image-palette-set"'),
        save_settings_case.index('Stage "save-image-ink-saver-set"'),
        save_settings_case.index('Stage "save-image-factors-set"'),
    ]
    assert configure_order == sorted(configure_order)
    restore_order = [
        save_settings_case.index('Stage = "save-image-factors-restore"'),
        save_settings_case.index('Stage = "save-image-ink-saver-restore"'),
        save_settings_case.index('Stage = "save-image-palette-restore"'),
        save_settings_case.index('Stage = "save-filename-restore"'),
    ]
    assert restore_order == sorted(restore_order)
    for stage in (
        "save-filename-restore-query",
        "save-image-palette-restore-query",
        "save-image-ink-saver-restore-query",
        "save-image-factors-restore-query",
    ):
        assert f'Stage "{stage}"' in save_settings_case
    assert "$identity.capabilities.supports_advanced_fft" in script
    assert "$identity.capabilities.supports_math_goft" in script
    assert "$identity.capabilities.demo_functions" in script
    assert "WGEN output OFF and disconnected from unknown DUT" in script
    assert "DEMO output OFF" in script
    assert "External trigger input" in script
    assert "Math Function 1 is disposable" in script

    save_export_start = script.index('Invoke-BaselineCase -Name "save-export"')
    save_export_end = script.index(
        'Invoke-BaselineCase -Name "acquisition"', save_export_start
    )
    save_export = script[save_export_start:save_export_end]
    image_format_set = save_export.index('Stage "save-image-format-png"')
    image_save = save_export.index('$image = Invoke-LiveCli -Stage "save-image"')
    waveform_format_set = save_export.index('Stage "save-waveform-format-csv"')
    waveform_length_set = save_export.index('Stage "save-waveform-length-1000"')
    waveform_stage = save_export.index('$waveform = Invoke-LiveCli -Stage "save-waveform"')
    waveform_validation = save_export.index(
        "if (-not [bool]$waveform.result.instrument_side", waveform_stage
    )
    handoff_sleep = save_export.index("Start-Sleep -Seconds 3", waveform_validation)
    length_restore = save_export.index(
        'Invoke-LiveCli -Stage "save-waveform-length-restore"'
    )
    assert "Start-Sleep -Milliseconds 500" not in save_export
    assert (
        image_format_set
        < image_save
        < waveform_format_set
        < waveform_length_set
        < waveform_stage
        < waveform_validation
        < handoff_sleep
        < length_restore
    )
    assert 'Stage "save-image-format-restore"' not in save_export
    assert 'Stage "save-waveform-format-restore"' not in save_export

    restore_start = script.index("function Restore-InstrumentState {")
    restore_end = script.index(
        "\nif ([string]::IsNullOrWhiteSpace($Resource))", restore_start
    )
    restore = script[restore_start:restore_end]
    assert 'Name = "save directory fixture"' in restore
    assert 'Name = "waveform save format fixture"' in restore
    assert "SaveFixtureEstablished" in restore
    assert 'Command = "save-image-format"' in restore
    assert 'Command = "save-waveform-format"' in restore
    assert 'Name = "waveform save length"' in restore
    assert 'Command = "save-waveform-length"' in restore


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_wgen_applicability_and_runtime_failure(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-wgen-applicability-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @(
    "Add-CaseResult", "Add-NotApplicableCase", "Assert-NearlyEqual",
    "Assert-FiniteNumber", "Assert-ScpiSent", "Invoke-BaselineCase"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$fixtureFunctionAst = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-FixtureBaseline"
    )
}, $true)
if ($null -eq $fixtureFunctionAst) { throw "Missing Invoke-FixtureBaseline." }
Invoke-Expression $fixtureFunctionAst.Extent.Text

$snapshotAssignment = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Extent.Text.TrimStart().StartsWith('$snapshot = [pscustomobject]@{')
    )
}, $true)
if ($null -eq $snapshotAssignment) { throw "Missing production snapshot construction." }

$systemStatusCommand = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "system-status"') -and
        $node.Extent.Text.Contains('$snapshot.InstalledOptions = @($options.result.options)')
    )
}, $true)
if ($null -eq $systemStatusCommand) { throw "Missing production system-status command." }

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
}

$wgenIf = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.TrimStart().StartsWith('if (-not $script:FunctionalFailed -and $snapshot.WgenApplicable -eq $true)')
    )
}, $true)
if ($null -eq $wgenIf) { throw "Missing wgen-basic applicability gate." }
$wgenCode = $wgenIf.Extent.Text

$demoIf = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.TrimStart().StartsWith('if (-not $script:FunctionalFailed -and [bool]$identity.capabilities.supports_demo)')
    )
}, $true)
if ($null -eq $demoIf) { throw "Missing demo-basic continuation gate." }
$demoCode = $demoIf.Extent.Text

$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:Scenario = ""
$script:InstalledOptions = @()

function New-QueryPayload {
    param([hashtable] $Values)
    return [pscustomobject]@{
        result = [pscustomobject]$Values
    }
}

function New-ProductionIdentity {
    return [pscustomobject]@{
        capabilities = [pscustomobject]@{
            series = "4000X"
            analog_channels = 4
            default_waveform_points = 1000
            safe_max_waveform_points = 4000000
            supports_word_format = $true
            supports_raw_points_mode = $true
            supports_measurements = $true
            supports_delay_measurement = $true
            supports_measure_results_dump = $true
            supports_demo = $true
            demo_functions = @("sine")
            math_function_count = 4
            supports_math_goft = $true
            math_filter_operations = @()
            math_visualization_operations = @()
            supports_advanced_fft = $true
            supports_screenshot = $true
            supports_screenshot_hardcopy_controls = $true
            supports_segmented_memory = $true
            segmented_max_segments = 1000
            supports_serial_decode = $true
            serial_bus_count = 2
            serial_modes = @("uart", "i2c", "spi", "can")
            reference_waveforms = 4
            supports_channel_label = $true
            channel_label_max_length = 10
            supports_display_label = $true
            supports_annotation = $false
            supports_annotation_position = $false
            annotation_slots = 0
            supports_indexed_annotation = $false
            supports_50_ohm_impedance = $true
            supports_search_basic = $true
            supports_search_event_navigation = $true
            search_modes = @("edge")
        }
    }
}

function Initialize-ProductionSnapshot {
    param([Parameter(Mandatory = $true)] $Identity)

    $acquisition = New-QueryPayload @{ type = "normal"; count = 1 }
    $channelDisplay = New-QueryPayload @{ display = $true }
    $channelCoupling = New-QueryPayload @{ coupling = "dc" }
    $channelLabel = New-QueryPayload @{ text = "Original" }
    $channelScale = New-QueryPayload @{ volts_per_division = 1.0 }
    $channelOffset = New-QueryPayload @{ volts = 0.0 }
    $channelProbe = New-QueryPayload @{ probe_ratio = 10.0 }
    $channelBandwidth = New-QueryPayload @{ bandwidth_limit = $false }
    $channelImpedance = New-QueryPayload @{ impedance = "one_meg" }
    $channelInvert = New-QueryPayload @{ invert = $false }
    $channelRange = New-QueryPayload @{ range_volts = 8.0 }
    $channelUnits = New-QueryPayload @{ units = "volt" }
    $channelVernier = New-QueryPayload @{ vernier = $false }
    $channelProbeSkew = New-QueryPayload @{ probe_skew_seconds = 0.0 }
    $displayLabels = New-QueryPayload @{ display_label = $true }
    $displayPersistence = New-QueryPayload @{ mode = "minimum"; seconds = $null }
    $displayIntensity = New-QueryPayload @{ value = 50 }
    $displayVectors = New-QueryPayload @{ value = $true }
    $annotationState = $null
    $annotationRestorable = $false
    $timebaseScale = New-QueryPayload @{ seconds_per_division = 0.001 }
    $timebasePosition = New-QueryPayload @{ position_seconds = 0.0 }
    $timebaseReference = New-QueryPayload @{ reference = "center" }
    $triggerSource = New-QueryPayload @{ source = "analog-channel"; source_channel = 1 }
    $triggerSlope = New-QueryPayload @{ slope = "negative" }
    $triggerLevel = New-QueryPayload @{ level_volts = 0.0 }
    $triggerHoldoff = New-QueryPayload @{ seconds = 0.000001 }
    $is2000XSeries = $false
    $is3000XSeries = $false
    $is4000XSeries = $false
    $triggerEdgeCoupling = $null
    $triggerEdgeReject = $null
    $triggerSweep = $null
    $triggerNoiseReject = $null
    $triggerHfReject = $null
    $externalTrigger = $null
    $externalTriggerLevel = $null
    $searchSupported = $true
    $identity = $Identity
    $savePwd = New-QueryPayload @{ path = "\\usb" }
    $saveFilename = New-QueryPayload @{ name = "scope" }
    $saveImageFormat = New-QueryPayload @{ format = "none" }
    $saveImagePalette = New-QueryPayload @{ palette = "color" }
    $saveImageInkSaver = New-QueryPayload @{ enabled = $true }
    $saveImageFactors = New-QueryPayload @{ enabled = $false }
    $saveWaveformFormat = New-QueryPayload @{ format = "csv" }
    $saveWaveformLength = New-QueryPayload @{ points = 1000 }
    $saveWaveformLengthMax = New-QueryPayload @{ enabled = $false }
    $snapshot = $null
    Invoke-Expression $snapshotAssignment.Extent.Text | Out-Null
    return $snapshot
}

function Invoke-ProductionSystemStatus {
    $is2000XSeries = $false
    $is3000XSeries = $false
    $is4000XSeries = $false
    Invoke-Expression $systemStatusCommand.Extent.Text | Out-Null
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    if ($script:Scenario -eq "runtime-failure" -and $Command -eq "wgen-function") {
        throw "-241,Hardware missing"
    }
    switch ($Command) {
        "channel-display" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:DISPlay ON") }
                result = [pscustomobject]@{ command = ":CHANnel1:DISPlay ON" }
            }
        }
        "channel-scale" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:SCALe 2") }
                result = [pscustomobject]@{ command = ":CHANnel1:SCALe 2" }
            }
        }
        "acquisition" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":ACQuire:TYPE NORMal") }
                result = [pscustomobject]@{ command = ":ACQuire:TYPE NORMal" }
            }
        }
        "trigger-edge" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(
                    ":TRIGger:MODE EDGE",
                    ":TRIGger:EDGE:SOURce CHANnel1",
                    ":TRIGger:EDGE:SLOPe POSitive"
                ) }
                result = [pscustomobject]@{ command = ":TRIGger:EDGE:SLOPe POSitive" }
            }
        }
        "system-opc" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*OPC?") }
                result = [pscustomobject]@{ complete = $true; raw = "1" }
            }
        }
        "system-status-byte" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*STB?") }
                result = [pscustomobject]@{ value = 0; set_bits = @() }
            }
        }
        "system-operation-status" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":OPERegister:CONDition?") }
                result = [pscustomobject]@{ value = 0; set_bits = @() }
            }
        }
        "system-standard-event" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*ESR?") }
                result = [pscustomobject]@{ value = 0; set_bits = @() }
            }
        }
        "system-options" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*OPT?") }
                result = [pscustomobject]@{
                    raw = ($script:InstalledOptions -join ",")
                    options = @($script:InstalledOptions)
                }
            }
        }
        "wgen-output" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(
                    if ($Arguments -contains "true") { ":WGEN1:OUTPut ON" } else { ":WGEN1:OUTPut OFF" }
                ) }
                result = [pscustomobject]@{}
            }
        }
        "wgen-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{
                enabled = $true
                function = "sine"
                load = "one-meg"
                frequency_hz = 1000
                amplitude_volts = 0.5
            } }
        }
        "demo-function" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":DEMO:FUNCtion SIN") }
                result = [pscustomobject]@{}
            }
        }
        "demo-output" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(
                    if ($Arguments -contains "true") { ":DEMO:OUTPut ON" } else { ":DEMO:OUTPut OFF" }
                ) }
                result = [pscustomobject]@{}
            }
        }
        "demo-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{
                enabled = $true
                function = "sine"
            } }
        }
        default {
            return [pscustomobject]@{ result = [pscustomobject]@{} }
        }
    }
}

function Invoke-Scenario {
    param(
        [ValidateSet("installed", "absent", "runtime-failure")]
        [string] $Name
    )
    $script:Scenario = $Name
    $script:Invocations.Clear()
    $script:CaseResults = [ordered]@{}
    $script:FunctionalFailed = $false
    $identity = New-ProductionIdentity
    $script:InstalledOptions = if ($Name -eq "installed" -or $Name -eq "runtime-failure") {
        @("WAVEGEN")
    } else {
        @("BASIC")
    }
    $snapshot = Initialize-ProductionSnapshot -Identity $identity
    $initialInstalledOptions = @($snapshot.InstalledOptions)
    $unknownBeforeSystemStatus = $null -eq $snapshot.WgenApplicable
    Invoke-ProductionSystemStatus
    $applicability = [pscustomobject]@{
        Applicable = $snapshot.WgenApplicable
        Detail = $snapshot.WgenApplicabilityDetail
    }
    Invoke-Expression $wgenCode
    $wgenCommands = @($script:Invocations |
        Where-Object { $_.command -like "wgen-*" } |
        ForEach-Object { $_.command })
    if ($Name -eq "absent") {
        Invoke-Expression $demoCode
    }
    return [pscustomobject]@{
        applicability = $applicability
        initial_installed_options = $initialInstalledOptions
        installed_options = @($snapshot.InstalledOptions)
        wgen_applicable = $snapshot.WgenApplicable
        unknown_before_system_status = $unknownBeforeSystemStatus
        supports_wgen_absent = $null -eq $identity.capabilities.PSObject.Properties["supports_wgen"]
        system_status = [string]$script:CaseResults["system-status"].Status
        system_options_queries = @($script:Invocations |
            Where-Object { $_.command -eq "system-options" }).Count
        wgen_status = [string]$script:CaseResults["wgen-basic"].Status
        wgen_commands = $wgenCommands
        demo_status = if ($script:CaseResults.Contains("demo-basic")) {
            [string]$script:CaseResults["demo-basic"].Status
        } else { "" }
        functional_failed = [bool]$script:FunctionalFailed
    }
}

[ordered]@{
    installed = Invoke-Scenario -Name "installed"
    absent = Invoke-Scenario -Name "absent"
    runtime_failure = Invoke-Scenario -Name "runtime-failure"
} | ConvertTo-Json -Depth 10 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    installed = result["installed"]
    assert installed["applicability"]["Applicable"] is True
    assert installed["initial_installed_options"] == []
    assert installed["unknown_before_system_status"] is True
    assert installed["supports_wgen_absent"] is True
    assert installed["system_status"] == "PASS"
    assert installed["system_options_queries"] == 1
    assert installed["installed_options"] == ["WAVEGEN"]
    assert installed["wgen_applicable"] is True
    assert installed["wgen_status"] == "PASS"
    assert installed["wgen_commands"] == [
        "wgen-function",
        "wgen-frequency",
        "wgen-voltage",
        "wgen-offset",
        "wgen-load",
        "wgen-output",
        "wgen-query",
        "wgen-output",
    ]
    assert installed["functional_failed"] is False

    absent = result["absent"]
    assert absent["applicability"]["Applicable"] is False
    assert "option is not installed" in absent["applicability"]["Detail"]
    assert absent["initial_installed_options"] == []
    assert absent["unknown_before_system_status"] is True
    assert absent["supports_wgen_absent"] is True
    assert absent["system_status"] == "PASS"
    assert absent["system_options_queries"] == 1
    assert absent["installed_options"] == ["BASIC"]
    assert absent["wgen_applicable"] is False
    assert absent["wgen_status"] == "N/A"
    assert absent["wgen_commands"] == []
    assert absent["demo_status"] == "PASS"
    assert absent["functional_failed"] is False

    runtime_failure = result["runtime_failure"]
    assert runtime_failure["applicability"]["Applicable"] is True
    assert runtime_failure["supports_wgen_absent"] is True
    assert runtime_failure["system_status"] == "PASS"
    assert runtime_failure["system_options_queries"] == 1
    assert runtime_failure["installed_options"] == ["WAVEGEN"]
    assert runtime_failure["wgen_applicable"] is True
    assert runtime_failure["wgen_status"] == "FAIL"
    assert runtime_failure["functional_failed"] is True


def test_save_pwd_validation_uses_fixed_usb_fixture_without_obsolete_logic() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    for obsolete in (
        "Get-SavePathSetterArgument",
        "save-pwd-prerequisite-set",
        "save-pwd-prerequisite-query",
        "save-pwd-restore",
        "queryable but not setter-restorable",
    ):
        assert obsolete not in script
    assert '"--path", [string]$snapshot.SavePwd' not in script
    assert '"--path", $savePwdSetterPath' not in script

    fixture_start = script.index('Invoke-BaselineCase -Name "save-pwd-fixture"')
    assert fixture_start < script.index('Invoke-BaselineCase -Name "save-pwd"')
    fixture_case = script[
        fixture_start:script.index(
            'Invoke-BaselineCase -Name "save-pwd"', fixture_start
        )
    ]
    assert 'Command "save-pwd"' in fixture_case
    assert 'Arguments @("--query")' in fixture_case
    assert "Test-SavePathEquivalent" in fixture_case
    assert '"\\usb"' in fixture_case

    save_pwd_start = script.index('Invoke-BaselineCase -Name "save-pwd"')
    save_pwd_end = script.index('Invoke-BaselineCase -Name "save-settings"')
    save_pwd_case = script[save_pwd_start:save_pwd_end]
    setter_index = save_pwd_case.index('Stage "save-pwd-set"')
    query_index = save_pwd_case.index('Stage "save-pwd-query"')
    assert setter_index < query_index
    assert save_pwd_case.index("-Arguments @(\"--path\", \"\\usb\")") < query_index
    assert save_pwd_case.count('Command "save-pwd"') == 2
    assert ':SAVE:PWD "\\usb"' in save_pwd_case
    assert "Test-SavePathEquivalent" in save_pwd_case

    assert "[10] Set the instrument Save directory" not in script
    assert "Save PWD and active Save image/waveform format context are validator-owned" in script
    assert "Cleanup leaves Save PWD at \\usb and waveform save format CSV after the" in script

@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_save_pwd_fixture_establishes_usb_and_csv(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "save-pwd-fixture-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @(
    "Test-SavePathEquivalent", "Assert-ScpiSent", "Invoke-BaselineCase"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$fixtureCase = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "save-pwd-fixture"')
    )
}, $true).Extent.Text

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Status = if ($Passed) { "PASS" } else { "FAIL" }
        Detail = $Detail
    }
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:Drains.Add($Stage)
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Stages.Add($Stage)
    switch ($Stage) {
        "save-pwd-fixture-set" {
            if ($script:SetFails) { throw '-310,"System error"' }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(':SAVE:PWD "\usb"') }
                result = [pscustomobject]@{}
            }
        }
        "save-pwd-fixture-query" {
            return [pscustomobject]@{
                result = [pscustomobject]@{ path = $script:QueryPath }
            }
        }
        "save-waveform-format-fixture-set" {
            if ($script:FormatFails) { throw '-310,"Format error"' }
            return [pscustomobject]@{ result = [pscustomobject]@{} }
        }
        "save-waveform-format-fixture-query" {
            return [pscustomobject]@{
                result = [pscustomobject]@{ format = $script:WaveformFormat }
            }
        }
        default { throw "Unexpected stage ${Stage}." }
    }
}

function Invoke-Scenario {
    param(
        [ValidateSet("success", "pwd-mismatch", "csv-mismatch")]
        [string] $Name
    )
    $script:SetFails = $false
    $script:FormatFails = $false
    $script:QueryPath = "\usb"
    $script:WaveformFormat = "csv"
    if ($Name -eq "pwd-mismatch") { $script:QueryPath = "\Temp" }
    if ($Name -eq "csv-mismatch") { $script:WaveformFormat = "binary" }
    $script:SaveFixtureEstablished = $false
    $script:DownstreamRan = $false
    $script:CaseResults = [ordered]@{}
    $script:FunctionalFailed = $false
    $script:Stages = New-Object System.Collections.Generic.List[string]
    $script:Drains = New-Object System.Collections.Generic.List[string]

    Invoke-Expression $fixtureCase
    if (-not $script:FunctionalFailed) {
        $script:DownstreamRan = $true
    }

    return [pscustomobject]@{
        fixture_status = if ($script:CaseResults.Contains("save-pwd-fixture")) {
            [string]$script:CaseResults["save-pwd-fixture"].Status
        } else { "" }
        functional_failed = $script:FunctionalFailed
        established = $script:SaveFixtureEstablished
        downstream_ran = $script:DownstreamRan
        stages = @($script:Stages | ForEach-Object { $_ })
        drains = @($script:Drains | ForEach-Object { $_ })
    }
}

[ordered]@{
    success = Invoke-Scenario -Name "success"
    pwd_mismatch = Invoke-Scenario -Name "pwd-mismatch"
    csv_mismatch = Invoke-Scenario -Name "csv-mismatch"
} | ConvertTo-Json -Depth 8 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    success = result["success"]
    assert success["fixture_status"] == "PASS"
    assert success["functional_failed"] is False
    assert success["established"] is True
    assert success["downstream_ran"] is True
    assert success["stages"] == [
        "save-pwd-fixture-set",
        "save-pwd-fixture-query",
        "save-waveform-format-fixture-set",
        "save-waveform-format-fixture-query",
    ]
    assert success["drains"] == []

    pwd_mismatch = result["pwd_mismatch"]
    assert pwd_mismatch["fixture_status"] == "FAIL"
    assert pwd_mismatch["functional_failed"] is True
    assert pwd_mismatch["established"] is False
    assert pwd_mismatch["downstream_ran"] is False
    assert pwd_mismatch["stages"] == [
        "save-pwd-fixture-set",
        "save-pwd-fixture-query",
    ]

    csv_mismatch = result["csv_mismatch"]
    assert csv_mismatch["fixture_status"] == "FAIL"
    assert csv_mismatch["functional_failed"] is True
    assert csv_mismatch["established"] is False
    assert csv_mismatch["downstream_ran"] is False
    assert csv_mismatch["stages"] == [
        "save-pwd-fixture-set",
        "save-pwd-fixture-query",
        "save-waveform-format-fixture-set",
        "save-waveform-format-fixture-query",
    ]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_workflow_acquisition_run_precondition(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-workflow-check.ps1"
    harness_path = tmp_path / "workflow-acquisition-precondition-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse workflow live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @("Get-RequiredResultValue", "Ensure-WorkflowAcquisitionRunning")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$script:OperationConditionRunMask = 8
$script:Invocations = New-Object System.Collections.Generic.List[object]

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,
        [Parameter(Mandatory = $true)]
        [string] $Command,
        [string[]] $Arguments = @()
    )

    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    if ($Command -eq "run") {
        return [pscustomobject]@{ ok = $true }
    }
    if ($Command -eq "system-operation-status") {
        return [pscustomobject]@{
            result = [pscustomobject]@{ value = 8 }
        }
    }
    throw "Unexpected live command: ${Command}"
}

# Case 1 - originally running: helper should return without invoking CLI
$script:Invocations.Clear()
$runningError = ""
try {
    Ensure-WorkflowAcquisitionRunning -WasRunning $true
} catch {
    $runningError = $_.Exception.Message
}
$runningCalls = @($script:Invocations | ForEach-Object {
    [ordered]@{ command = $_.command; arguments = @($_.arguments) }
})

# Case 2 - originally stopped: helper should issue run + status query
$script:Invocations.Clear()
$stoppedError = ""
try {
    Ensure-WorkflowAcquisitionRunning -WasRunning $false
} catch {
    $stoppedError = $_.Exception.Message
}
$stoppedCalls = @($script:Invocations | ForEach-Object {
    [ordered]@{ command = $_.command; arguments = @($_.arguments) }
})

[ordered]@{
    running_error = $runningError
    running_calls = @($runningCalls)
    running_count = $runningCalls.Count
    stopped_error = $stoppedError
    stopped_calls = @($stoppedCalls)
    stopped_count = $stoppedCalls.Count
} | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    # Case 1 - originally running: no CLI invocation
    assert result["running_error"] == ""
    assert result["running_count"] == 0
    assert result["running_calls"] == []

    # Case 2 - originally stopped: exactly run + status query
    assert result["stopped_error"] == ""
    assert result["stopped_count"] == 2
    assert result["stopped_calls"][0]["command"] == "run"
    assert result["stopped_calls"][0]["arguments"] == []
    assert result["stopped_calls"][1]["command"] == "system-operation-status"
    assert result["stopped_calls"][1]["arguments"] == ["--query"]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")


def test_baseline_save_settings_owns_mutations_and_partial_rollback(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-save-settings-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Assert-ScpiSent", "Invoke-BaselineCase")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"save-settings`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) { throw "Expected one save-settings case." }
$caseBlock = $matchingCommands[0].Extent.Text

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Add-Diagnostic {
    param([string] $Name, [string] $Message)
    if (-not $script:Diagnostics.Contains($Name)) {
        $script:Diagnostics[$Name] = New-Object System.Collections.Generic.List[string]
    }
    $script:Diagnostics[$Name].Add($Message)
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })

    if ($script:Scenario -eq "filename-query-failure" -and
        $Stage -eq "save-filename-query") {
        throw "filename readback failure"
    }

    $sent = @()
    $result = [ordered]@{}
    switch ($Stage) {
        "save-image-format-png" { $sent = @(':SAVE:IMAGe:FORMat PNG') }
        "save-filename-set" { $sent = @(':SAVE:FILename "live_validation"') }
        "save-filename-query" { $result.name = "live_validation" }
        "save-filename-restore" { $sent = @(':SAVE:FILename "scope"') }
        "save-filename-restore-query" { $result.name = "scope" }
        "save-image-palette-set" { $sent = @(':SAVE:IMAGe:PALette COLOR') }
        "save-image-palette-query" { $result.palette = "color" }
        "save-image-palette-restore" { $sent = @(':SAVE:IMAGe:PALette COLOR') }
        "save-image-palette-restore-query" { $result.palette = "color" }
        "save-image-ink-saver-set" { $sent = @(':SAVE:IMAGe:INKSaver 0') }
        "save-image-ink-saver-query" { $result.enabled = $false }
        "save-image-ink-saver-restore" { $sent = @(':SAVE:IMAGe:INKSaver 1') }
        "save-image-ink-saver-restore-query" { $result.enabled = $true }
        "save-image-factors-set" { $sent = @(':SAVE:IMAGe:FACTors 1') }
        "save-image-factors-query" { $result.enabled = $true }
        "save-image-factors-restore" { $sent = @(':SAVE:IMAGe:FACTors 0') }
        "save-image-factors-restore-query" { $result.enabled = $false }
    }
    return [pscustomobject]@{
        scpi = [pscustomobject]@{ sent = $sent }
        result = [pscustomobject]$result
    }
}

function Invoke-Scenario {
    param([ValidateSet("pass", "filename-query-failure", "empty-filename")][string] $Name)
    $script:Scenario = $Name
    $script:CaseResults = [ordered]@{}
    $script:Diagnostics = [ordered]@{}
    $script:FunctionalFailed = $false
    $script:DrainCalls = 0
    $script:Invocations = New-Object System.Collections.Generic.List[object]
    $snapshot = [pscustomobject]@{
        SaveImageFormat = "none"
        SavePwd = "\usb"
        SaveFilename = if ($Name -eq "empty-filename") { "" } else { "scope" }
        SaveImagePalette = "color"
        SaveImageInkSaver = $true
        SaveImageFactors = $false
        SaveWaveformFormat = "csv"
    }
    Invoke-Expression $caseBlock
    return [pscustomobject]@{
        passed = $script:CaseResults["save-settings"].Passed
        detail = $script:CaseResults["save-settings"].Detail
        stages = @($script:Invocations | ForEach-Object { $_.stage })
        commands = @($script:Invocations | ForEach-Object { $_.command })
        invocations = @(
            $script:Invocations | ForEach-Object {
                [pscustomobject]@{
                    stage = $_.stage
                    command = $_.command
                    arguments = @($_.arguments)
                }
            }
        )
        drain_calls = $script:DrainCalls
    }
}

[ordered]@{
    pass = Invoke-Scenario -Name "pass"
    empty_filename = Invoke-Scenario -Name "empty-filename"
    filename_query_failure = Invoke-Scenario -Name "filename-query-failure"
} | ConvertTo-Json -Depth 10 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    passing = result["pass"]
    assert passing["passed"] is True, passing["detail"]
    assert passing["stages"][:9] == [
        "save-image-format-png",
        "save-filename-set",
        "save-filename-query",
        "save-image-palette-set",
        "save-image-palette-query",
        "save-image-ink-saver-set",
        "save-image-ink-saver-query",
        "save-image-factors-set",
        "save-image-factors-query",
    ]
    restore_start = passing["stages"].index("save-image-factors-restore")
    assert passing["stages"][restore_start : restore_start + 4] == [
        "save-image-factors-restore",
        "save-image-ink-saver-restore",
        "save-image-palette-restore",
        "save-filename-restore",
    ]
    assert [
        stage for stage in passing["stages"]
        if stage.endswith("-restore")
    ] == [
        "save-image-factors-restore",
        "save-image-ink-saver-restore",
        "save-image-palette-restore",
        "save-filename-restore",
    ]
    assert passing["stages"][-1] == "save-image-factors-restore-query"
    assert [
        stage for stage in passing["stages"]
        if stage.endswith("-restore-query")
    ] == [
        "save-filename-restore-query",
        "save-image-palette-restore-query",
        "save-image-ink-saver-restore-query",
        "save-image-factors-restore-query",
    ]

    empty = result["empty_filename"]
    assert empty["passed"] is True, empty["detail"]
    assert empty["stages"][0:3] == [
        "save-image-format-png",
        "save-filename-set",
        "save-filename-query",
    ]
    assert "save-filename-restore" not in empty["stages"]
    assert "save-filename-restore-query" not in empty["stages"]
    image_restores = [
        stage for stage in empty["stages"] if stage.endswith("-restore")
    ]
    assert image_restores == [
        "save-image-factors-restore",
        "save-image-ink-saver-restore",
        "save-image-palette-restore",
    ]

    filename_set = next(
        entry for entry in empty["invocations"]
        if entry["stage"] == "save-filename-set"
    )
    assert filename_set["arguments"] == ["--name", "live_validation"]

    assert not any(
        arg == ""
        for entry in empty["invocations"]
        for arg in entry["arguments"]
    )

    failure = result["filename_query_failure"]
    assert failure["passed"] is False
    assert "filename readback failure" in failure["detail"]
    assert failure["stages"] == [
        "save-image-format-png",
        "save-filename-set",
        "save-filename-query",
        "save-filename-restore",
        "save-filename-restore-query",
    ]
    assert not any(command == "save-pwd" for command in passing["commands"])
    assert not any(command == "save-pwd" for command in failure["commands"])
    assert not any(
        stage.startswith("save-image-palette")
        or stage.startswith("save-image-ink-saver")
        or stage.startswith("save-image-factors")
        for stage in failure["stages"]
    )


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_timebase_reference_restore_preserves_primary_failure(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "timebase-reference-restore-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Assert-NearlyEqual", "Invoke-BaselineCase")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"timebase`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) { throw "Expected one timebase case." }
$caseBlock = $matchingCommands[0].Extent.Text

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Add-Diagnostic {
    param([string] $Name, [string] $Message)
    if (-not $script:Diagnostics.Contains($Name)) {
        $script:Diagnostics[$Name] = New-Object System.Collections.Generic.List[string]
    }
    $script:Diagnostics[$Name].Add($Message)
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:Drains.Add($Stage)
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Stages.Add($Stage)
    $result = [ordered]@{}
    switch ($Stage) {
        "timebase-scale-query" { $result.seconds_per_division = 0.001 }
        "timebase-position-query" { $result.position_seconds = 0.0 }
        "timebase-reference-set" {
            if ($script:Scenario -eq "set-failure") {
                throw "reference set failure"
            }
        }
        "timebase-reference-query" {
            $result.reference = if ($script:Scenario -eq "primary-and-restore-failure") {
                "right"
            } else {
                "left"
            }
        }
        "timebase-reference-restore" {
            if ($script:Scenario -eq "primary-and-restore-failure") {
                throw "reference restore failure"
            }
        }
        "timebase-reference-restore-query" { $result.reference = "center" }
    }
    return [pscustomobject]@{ result = [pscustomobject]$result }
}

function Invoke-Scenario {
    param(
        [ValidateSet("success", "set-failure", "primary-and-restore-failure")]
        [string] $Name
    )
    $script:Scenario = $Name
    $script:CaseResults = [ordered]@{}
    $script:Diagnostics = [ordered]@{}
    $script:FunctionalFailed = $false
    $script:Stages = New-Object System.Collections.Generic.List[string]
    $script:Drains = New-Object System.Collections.Generic.List[string]
    $snapshot = [pscustomobject]@{ TimebaseReference = "center" }
    Invoke-Expression $caseBlock
    $diagnostics = @(
        if ($script:Diagnostics.Contains("timebase")) {
            $script:Diagnostics["timebase"] | ForEach-Object { $_ }
        }
    )
    return [pscustomobject]@{
        passed = $script:CaseResults["timebase"].Passed
        detail = $script:CaseResults["timebase"].Detail
        stages = @($script:Stages | ForEach-Object { $_ })
        drains = @($script:Drains | ForEach-Object { $_ })
        diagnostics = $diagnostics
    }
}

[ordered]@{
    success = Invoke-Scenario -Name "success"
    set_failure = Invoke-Scenario -Name "set-failure"
    primary_and_restore_failure = Invoke-Scenario -Name "primary-and-restore-failure"
} | ConvertTo-Json -Depth 8 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    success = result["success"]
    assert success["passed"] is True, success["detail"]
    assert success["stages"][-2:] == [
        "timebase-reference-restore",
        "timebase-reference-restore-query",
    ]
    assert success["drains"] == []
    assert success["diagnostics"] == []

    set_failure = result["set_failure"]
    assert set_failure["passed"] is False
    assert "reference set failure" in set_failure["detail"]
    assert "timebase-reference-restore" not in set_failure["stages"]
    assert set_failure["drains"] == ["timebase-error-drain"]

    combined_failure = result["primary_and_restore_failure"]
    assert combined_failure["passed"] is False
    assert "Timebase reference readback does not match left" in combined_failure["detail"]
    assert "reference restore failure" not in combined_failure["detail"]
    assert combined_failure["stages"][-1] == "timebase-reference-restore"
    assert "timebase-reference-restore-query" not in combined_failure["stages"]
    assert combined_failure["drains"] == [
        "timebase-reference-restore-error-drain",
        "timebase-error-drain",
    ]
    assert combined_failure["diagnostics"] == [
        "timebase reference restore failed: reference restore failure"
    ]


def test_baseline_part1_capability_gates_and_cleanup_wiring() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    gated_cases = {
        "measure-delay": "$identity.capabilities.supports_delay_measurement",
        "math-composite-source": "$identity.capabilities.supports_math_goft",
        "fft-advanced": "$identity.capabilities.supports_advanced_fft",
        "demo-phase": "$identity.capabilities.demo_functions",
        "reference-lifecycle": "reference_waveforms",
        "math-filter": "math_filter_operations",
        "math-visualization": "math_visualization_operations",
        "math-clear": "mathClearSupported",
    }
    for case_name, capability in gated_cases.items():
        case_start = script.index(f'Invoke-BaselineCase -Name "{case_name}"')
        gate_start = script.rfind("\n    if (-not $script:FunctionalFailed", 0, case_start)
        assert gate_start >= 0
        case_end = script.index(
            "\n    if (-not $script:FunctionalFailed", case_start + 1
        )
        case_block = script[gate_start:case_end]
        assert capability in case_block
        assert f'Add-NotApplicableCase -Name "{case_name}"' in case_block

    fft_advanced_start = script.index('Invoke-BaselineCase -Name "fft-advanced"')
    fft_advanced_end = script.index(
        'Invoke-BaselineCase -Name "wgen-basic"', fft_advanced_start
    )
    fft_advanced_case = script[fft_advanced_start:fft_advanced_end]
    assert "$identity.capabilities.math_function_count" in script[
        script.rfind("\n    if (-not $script:FunctionalFailed", 0, fft_advanced_start):
    ]
    assert '"--function", "4"' in fft_advanced_case
    assert '"--start-hz", "0"' in fft_advanced_case
    assert '"--gate", "none"' in fft_advanced_case
    assert '"--phase-reference", "trigger"' in fft_advanced_case
    assert '"--detection-type", "sample"' in fft_advanced_case
    assert '"--detection-points", "640"' in fft_advanced_case
    assert '"--gate", "zoom"' not in fft_advanced_case
    for command in (
        ":FUNCtion4:OPERation FFTPhase",
        ":FUNCtion4:FREQuency:STARt 0",
        ":FUNCtion4:FREQuency:STOP 1000000",
        ":FUNCtion4:GATE NONE",
        ":FUNCtion4:PHASe:REFerence TRIGger",
        ":FUNCtion4:DETection:TYPE SAMPle",
        ":FUNCtion4:DETection:POINts 640",
    ):
        assert command in fft_advanced_case
    assert 'Stage "fft-advanced-query"' in fft_advanced_case
    assert '"--function", "4", "--query"' in fft_advanced_case
    assert 'Stage "fft-advanced-display-off"' in fft_advanced_case
    assert '"--function", "4", "--off"' in fft_advanced_case

    demo_phase_start = script.index('Invoke-BaselineCase -Name "demo-phase"')
    demo_phase_end = script.index(
        'Invoke-BaselineCase -Name "autoscale"', demo_phase_start
    )
    demo_phase_case = script[demo_phase_start:demo_phase_end]
    assert 'Command "demo-phase"' in demo_phase_case
    assert 'Arguments @("--degrees", "90")' in demo_phase_case
    assert ':DEMO:FUNCtion:PHASe:PHASe 90' in demo_phase_case
    assert 'Stage "demo-phase-query"' in demo_phase_case
    assert 'Arguments @("--query")' in demo_phase_case
    assert ':DEMO:FUNCtion:PHASe:PHASe?' in demo_phase_case
    assert '$query.result.phase_degrees' in demo_phase_case
    assert '$query.result.degrees' not in demo_phase_case
    assert 'Properties["phase_raw"]' in demo_phase_case
    assert '-Expected 90' in demo_phase_case

    composite_start = script.index(
        'Invoke-BaselineCase -Name "math-composite-source"'
    )
    composite_end = script.index(
        'Invoke-BaselineCase -Name "math-filter"', composite_start
    )
    composite_gate_start = script.rfind(
        "\n    if (-not $script:FunctionalFailed", 0, composite_start
    )
    composite_case = script[composite_gate_start:composite_end]
    assert "$identity.capabilities.supports_math_goft" in composite_case
    assert 'Add-NotApplicableCase -Name "math-composite-source"' in composite_case

    natural_start = script.index('Invoke-BaselineCase -Name "capture-wait-trigger"')
    natural_end = script.index(
        'Invoke-BaselineCase -Name "trigger-holdoff"', natural_start
    )
    natural_case = script[natural_start:natural_end]
    assert '"--wait-trigger", "--trigger-timeout-ms", "5000"' in natural_case
    assert '"--trigger-poll-interval-ms", "100"' in natural_case
    assert "trigger-edge" not in natural_case
    assert '"--item", "minimum"' not in natural_case
    assert '"--item", "maximum"' not in natural_case
    assert "--force-trigger-on-timeout" not in natural_case
    assert 'Invoke-BaselineCase -Name "capture-wait-trigger-fallback"' not in script
    assert "--force-trigger-on-timeout" not in script

    assert 'Command "measure-sweep"' not in script
    assert 'Command "reference-clear"' in script
    assert 'Command "setup-save"' in script
    assert 'Command "setup-recall"' in script
    assert 'Command "math-visualization"' in script
    assert 'Stage "fft-display-off"' in script
    assert 'Stage "fft-advanced-display-off"' in script
    measure_start = script.index('Invoke-BaselineCase -Name "measure-controls"')
    measure_end = script.index(
        'Invoke-BaselineCase -Name "cursor-lifecycle"', measure_start
    )
    measure_case = script[measure_start:measure_end]
    for stage in (
        'Stage "measure-show-before"',
        'Stage "measure-source-before"',
        'Stage "measure-window-before"',
        'Stage "measure-source-restore"',
        'Stage "measure-source-restore-query"',
        'Stage "measure-window-restore"',
        'Stage "measure-window-restore-query"',
    ):
        assert stage in measure_case
    assert "finally" in measure_case
    assert 'throw "Measurement control restoration failed:' in measure_case
    assert "Measure Show may remain ON because the current public CLI exposes" in script
    assert 'Get-ErrorDrain -Stage "final-error-queue"' in script
    assert 'Command "cleanup"' in script


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_cursor_lifecycle_preserves_primary_failure_during_cleanup(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "cursor-lifecycle-cleanup-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

$functionAst = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-BaselineCase"
    )
}, $true)
if ($null -eq $functionAst) { throw "Missing Invoke-BaselineCase." }
Invoke-Expression $functionAst.Extent.Text

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"cursor-lifecycle`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) { throw "Expected one cursor-lifecycle case." }
$caseBlock = $matchingCommands[0].Extent.Text

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Add-Diagnostic {
    param([string] $Name, [string] $Message)
    if (-not $script:Diagnostics.Contains($Name)) {
        $script:Diagnostics[$Name] = New-Object System.Collections.Generic.List[string]
    }
    $script:Diagnostics[$Name].Add($Message)
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:Events.Add("drain:${Stage}")
}

function Assert-ScpiSent {
    param([object] $Payload, [string[]] $ExpectedCommands, [string] $Label)
    if ($script:Scenario -eq "configure-assert-and-cleanup-fail" -and
        $Label -eq "Cursor configure") {
        throw "cursor configure assertion failure"
    }
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Events.Add($Stage)
    if ($script:Scenario -eq "configure-fail" -and $Stage -eq "cursor-set") {
        throw "cursor configure primary failure"
    }
    if ($script:Scenario -eq "query-and-cleanup-fail" -and
        $Stage -eq "cursor-query") {
        throw "cursor query primary failure"
    }
    if ($script:Scenario -in @(
            "query-and-cleanup-fail",
            "cleanup-only-fail",
            "configure-assert-and-cleanup-fail"
        ) -and
        $Stage -eq "cursor-off") {
        throw "cursor cleanup failure"
    }
    $mode = if ($Stage -eq "cursor-off-query") { "off" } else { "manual" }
    return [pscustomobject]@{
        result = [pscustomobject]@{ mode = $mode }
    }
}

function Invoke-Scenario {
    param([string] $Name)
    $script:Scenario = $Name
    $script:CaseResults = [ordered]@{}
    $script:Diagnostics = [ordered]@{}
    $script:FunctionalFailed = $false
    $script:Events = New-Object System.Collections.Generic.List[string]
    Invoke-Expression $caseBlock
    return [pscustomobject]@{
        passed = $script:CaseResults["cursor-lifecycle"].Passed
        detail = $script:CaseResults["cursor-lifecycle"].Detail
        diagnostics = @(
            if ($script:Diagnostics.Contains("cursor-lifecycle")) {
                $script:Diagnostics["cursor-lifecycle"] | ForEach-Object { [string]$_ }
            }
        )
        events = @($script:Events | ForEach-Object { $_ })
    }
}

[ordered]@{
    query_and_cleanup_fail = Invoke-Scenario -Name "query-and-cleanup-fail"
    cleanup_only_fail = Invoke-Scenario -Name "cleanup-only-fail"
    configure_fail = Invoke-Scenario -Name "configure-fail"
    configure_assert_and_cleanup_fail = Invoke-Scenario `
        -Name "configure-assert-and-cleanup-fail"
} | ConvertTo-Json -Depth 10 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    combined = result["query_and_cleanup_fail"]
    assert combined["passed"] is False
    assert "cursor query primary failure" in combined["detail"]
    assert "cursor cleanup failure" not in combined["detail"]
    assert any("cursor cleanup failure" in item for item in combined["diagnostics"])
    assert combined["events"] == [
        "cursor-set",
        "cursor-query",
        "drain:cursor-primary-error-drain",
        "cursor-off",
        "cursor-off-query",
        "drain:cursor-lifecycle-error-drain",
    ]

    cleanup_only = result["cleanup_only_fail"]
    assert cleanup_only["passed"] is False
    assert "cursor cleanup failure" in cleanup_only["detail"]
    assert cleanup_only["events"] == [
        "cursor-set",
        "cursor-query",
        "cursor-off",
        "cursor-off-query",
        "drain:cursor-lifecycle-error-drain",
    ]

    configure = result["configure_fail"]
    assert configure["passed"] is False
    assert "cursor configure primary failure" in configure["detail"]
    assert configure["events"] == [
        "cursor-set",
        "drain:cursor-lifecycle-error-drain",
    ]

    configure_assert = result["configure_assert_and_cleanup_fail"]
    assert configure_assert["passed"] is False
    assert "cursor configure assertion failure" in configure_assert["detail"]
    assert "cursor cleanup failure" not in configure_assert["detail"]
    assert any(
        "cursor cleanup failure" in item
        for item in configure_assert["diagnostics"]
    )
    assert configure_assert["events"] == [
        "cursor-set",
        "drain:cursor-primary-error-drain",
        "cursor-off",
        "cursor-off-query",
        "drain:cursor-lifecycle-error-drain",
    ]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_save_export_preserves_primary_error_and_enforces_prerequisite(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-save-export-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

$functionAst = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-BaselineCase"
    )
}, $true)
if ($null -eq $functionAst) { throw "Missing Invoke-BaselineCase." }
Invoke-Expression $functionAst.Extent.Text

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"save-export`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) { throw "Expected one save-export case." }
$caseBlock = $matchingCommands[0].Extent.Text

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Add-Diagnostic {
    param([string] $Name, [string] $Message)
    if (-not $script:Diagnostics.Contains($Name)) {
        $script:Diagnostics[$Name] = New-Object System.Collections.Generic.List[string]
    }
    $script:Diagnostics[$Name].Add($Message)
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

function Assert-ScpiSentPrefix {
    param([object] $Payload, [string] $ExpectedPrefix, [string] $Label)
}

function Start-Sleep {
    param([int] $Seconds = 0, [int] $Milliseconds = 0)
    $script:SleepCalls.Add([pscustomobject]@{
        Seconds = $Seconds
        Milliseconds = $Milliseconds
        InvocationsCount = $script:Invocations.Count
    })
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add($Stage)
    if ($script:Scenario -eq "body-and-restore-fail" -and
        $Stage -eq "save-image-format-png") {
        throw "body primary failure"
    }
    if ($script:Scenario -in @("body-and-restore-fail", "restore-only-fail") -and
        $Stage -eq "save-waveform-length-restore") {
        throw "waveform length restore failure"
    }
    if ($Stage -eq "save-image") {
        $script:Filenames["save-image"] = [string]$Arguments[1]
        return [pscustomobject]@{ result = [pscustomobject]@{
            instrument_side = $true
            operation_complete = $true
            filename = $Arguments[1]
        } }
    }
    if ($Stage -eq "save-waveform") {
        $script:Filenames["save-waveform"] = [string]$Arguments[1]
        return [pscustomobject]@{ result = [pscustomobject]@{
            instrument_side = $true
            operation_complete = $true
            filename = $Arguments[1]
        } }
    }
    return [pscustomobject]@{ result = [pscustomobject]@{} }
}

function Invoke-Scenario {
    param([string] $Name, [bool] $LengthMax)
    $script:Scenario = $Name
    $script:CaseResults = [ordered]@{}
    $script:Diagnostics = [ordered]@{}
    $script:FunctionalFailed = $false
    $script:DrainCalls = 0
    $script:Invocations = New-Object System.Collections.Generic.List[string]
    $script:SleepCalls = New-Object System.Collections.Generic.List[object]
    $script:Filenames = [ordered]@{ "save-image" = ""; "save-waveform" = "" }
    $snapshot = [pscustomobject]@{
        SaveImageFormat = "png"
        SaveWaveformFormat = "csv"
        SaveWaveformLength = 2000
        SaveWaveformLengthMax = $LengthMax
    }
    Invoke-Expression $caseBlock
    return [pscustomobject]@{
        passed = $script:CaseResults["save-export"].Passed
        detail = $script:CaseResults["save-export"].Detail
        diagnostics = @(
            if ($script:Diagnostics.Contains("save-export")) {
                $script:Diagnostics["save-export"] | ForEach-Object { [string]$_ }
            }
        )
        invocations = @($script:Invocations | ForEach-Object { $_ })
        sleep_calls = @($script:SleepCalls | ForEach-Object { $_ })
        functional_failed = $script:FunctionalFailed
        drain_calls = $script:DrainCalls
        image_filename = [string]$script:Filenames["save-image"]
        waveform_filename = [string]$script:Filenames["save-waveform"]
    }
}

[ordered]@{
    pass = Invoke-Scenario -Name "pass" -LengthMax $false
    body_and_restore_fail = Invoke-Scenario `
        -Name "body-and-restore-fail" -LengthMax $false
    restore_only_fail = Invoke-Scenario `
        -Name "restore-only-fail" -LengthMax $false
    max_enabled = Invoke-Scenario -Name "max-enabled" -LengthMax $true
} | ConvertTo-Json -Depth 10 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    # Regression: save-export must define its own run timestamp instead of
    # depending on an undefined $timestamp under Set-StrictMode.
    passing = result["pass"]
    assert passing["passed"] is True
    assert passing["detail"] == ""
    assert passing["invocations"] == [
        "save-image-format-png",
        "save-image",
        "save-waveform-format-csv",
        "save-waveform-length-1000",
        "save-waveform",
        "save-waveform-length-restore",
    ]
    assert passing["drain_calls"] == 0
    assert len(passing["sleep_calls"]) == 1
    assert passing["sleep_calls"][0]["Seconds"] == 3
    filename_pattern = re.compile(
        r"^\\usb\\scopes-tool-live-(\d{8}-\d{6})\.(png|csv)$"
    )
    image_match = filename_pattern.match(passing["image_filename"])
    waveform_match = filename_pattern.match(passing["waveform_filename"])
    assert image_match is not None
    assert waveform_match is not None
    assert image_match.group(1) == waveform_match.group(1)

    combined = result["body_and_restore_fail"]
    assert combined["passed"] is False
    assert "body primary failure" in combined["detail"]
    assert "waveform length restore failure" not in combined["detail"]
    assert any(
        "waveform length restore failure" in item
        for item in combined["diagnostics"]
    )
    assert combined["invocations"][-1] == "save-waveform-length-restore"

    restore_only = result["restore_only_fail"]
    assert restore_only["passed"] is False
    assert "waveform length restore failure" in restore_only["detail"]
    assert restore_only["functional_failed"] is True
    assert restore_only["drain_calls"] == 1
    assert len(restore_only["sleep_calls"]) == 1
    assert restore_only["sleep_calls"][0]["Seconds"] == 3
    # Verify sleep occurred after save-waveform and before restore
    save_waveform_idx = restore_only["invocations"].index("save-waveform")
    assert restore_only["sleep_calls"][0]["InvocationsCount"] == save_waveform_idx + 1
    assert (
        restore_only["invocations"].index("save-image-format-png")
        < restore_only["invocations"].index("save-image")
    )
    assert restore_only["invocations"] == [
        "save-image-format-png",
        "save-image",
        "save-waveform-format-csv",
        "save-waveform-length-1000",
        "save-waveform",
        "save-waveform-length-restore",
    ]
    assert len(combined["sleep_calls"]) == 0

    max_enabled = result["max_enabled"]
    assert len(max_enabled["sleep_calls"]) == 0
    assert max_enabled["passed"] is False
    assert "acceptance prerequisite failed" in max_enabled["detail"]
    assert not any(
        stage
        in {
            "save-image-format-png",
            "save-image",
            "save-waveform-format-csv",
            "save-waveform-length-1000",
            "save-waveform",
            "save-image-format-restore",
            "save-waveform-format-restore",
            "save-waveform-length-restore",
        }
        for stage in max_enabled["invocations"]
    )


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_setup_lifecycle_uses_concrete_timestamped_setup_file(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-setup-lifecycle-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

$functionAst = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-BaselineCase"
    )
}, $true)
if ($null -eq $functionAst) { throw "Missing Invoke-BaselineCase." }
Invoke-Expression $functionAst.Extent.Text

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"setup-lifecycle`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) { throw "Expected one setup-lifecycle case." }
$caseBlock = $matchingCommands[0].Extent.Text

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

function Assert-ScpiSentPrefix {
    param([object] $Payload, [string] $ExpectedPrefix, [string] $Label)
}

$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:Filenames = [ordered]@{}
$script:ChannelLabel = "Original"

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    if ($Stage -in @("setup-save", "setup-recall")) {
        $script:Filenames[$Stage] = [string]$Arguments[1]
    }
    switch ($Stage) {
        "setup-label-change-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ text = "live edit" } }
        }
        "setup-label-restore-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ text = $script:ChannelLabel } }
        }
        default {
            return [pscustomobject]@{ result = [pscustomobject]@{} }
        }
    }
}

$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$snapshot = [pscustomobject]@{ ChannelLabel = $script:ChannelLabel }

Invoke-Expression $caseBlock

[ordered]@{
    passed = $script:CaseResults["setup-lifecycle"].Passed
    detail = $script:CaseResults["setup-lifecycle"].Detail
    invocations = @($script:Invocations | ForEach-Object { $_ })
    save_file = [string]$script:Filenames["setup-save"]
    recall_file = [string]$script:Filenames["setup-recall"]
    functional_failed = $script:FunctionalFailed
} | ConvertTo-Json -Depth 8 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    # Regression: setup-lifecycle must define its own run timestamp instead of
    # depending on an undefined $timestamp under Set-StrictMode.
    assert result["passed"] is True
    assert result["detail"] == ""
    assert result["functional_failed"] is False
    assert [entry["stage"] for entry in result["invocations"]] == [
        "setup-save",
        "setup-label-change",
        "setup-label-change-query",
        "setup-recall",
        "setup-label-restore-query",
    ]
    filename_pattern = re.compile(
        r"^\\usb\\scopes-tool-live-(\d{8}-\d{6})\.scp$"
    )
    assert filename_pattern.match(result["save_file"]) is not None
    assert result["recall_file"] == result["save_file"]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_setup_lifecycle_channel_label_fixtures_fit_3000x_profile(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "setup-lifecycle-channel-label-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

$functionAst = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-BaselineCase"
    )
}, $true)
if ($null -eq $functionAst) { throw "Missing Invoke-BaselineCase." }
Invoke-Expression $functionAst.Extent.Text

$setupCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"setup-lifecycle`"")
    )
}, $true))
if ($setupCommands.Count -ne 1) { throw "Expected one setup-lifecycle case." }
$setupCaseBlock = $setupCommands[0].Extent.Text

$slotCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"setup-slot-lifecycle`"")
    )
}, $true))
if ($slotCommands.Count -ne 1) { throw "Expected one setup-slot-lifecycle case." }
$slotCaseBlock = $slotCommands[0].Extent.Text

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

function Assert-ScpiSentPrefix {
    param([object] $Payload, [string] $ExpectedPrefix, [string] $Label)
}

function Assert-ScpiSent {
    param([object] $Payload, [string[]] $ExpectedCommands, [string] $Label)
}

$script:CapturedLabels = New-Object System.Collections.Generic.List[string]
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:CurrentLabel = "Original"

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })

    if ($Command -eq "channel-label" -and $Arguments -contains "--text") {
        $textIndex = [Array]::IndexOf($Arguments, "--text")
        if ($textIndex -lt 0 -or $textIndex + 1 -ge $Arguments.Count) {
            throw "channel-label mutation is missing its text argument."
        }
        $script:CurrentLabel = [string]$Arguments[$textIndex + 1]
        $script:CapturedLabels.Add($script:CurrentLabel)
    }

    switch ($Stage) {
        "setup-label-change-query" {
            return [pscustomobject]@{
                result = [pscustomobject]@{ text = $script:CurrentLabel }
            }
        }
        "setup-label-restore-query" {
            return [pscustomobject]@{
                result = [pscustomobject]@{ text = [string]$snapshot.ChannelLabel }
            }
        }
        "setup-slot-label-query" {
            return [pscustomobject]@{
                result = [pscustomobject]@{ text = [string]$snapshot.ChannelLabel }
            }
        }
        default {
            return [pscustomobject]@{}
        }
    }
}

$snapshot = [pscustomobject]@{ ChannelLabel = "Original" }
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0

Invoke-Expression $setupCaseBlock
$setupResult = $script:CaseResults["setup-lifecycle"]
$setupFunctionalFailed = $script:FunctionalFailed
$setupInvocations = @($script:Invocations | ForEach-Object { $_ })

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:Invocations.Clear()
$script:CurrentLabel = [string]$snapshot.ChannelLabel

Invoke-Expression $slotCaseBlock
$slotResult = $script:CaseResults["setup-slot-lifecycle"]
$slotInvocations = @($script:Invocations | ForEach-Object { $_ })

[ordered]@{
    captured_labels = @($script:CapturedLabels)
    setup_passed = [bool]$setupResult.Passed
    setup_detail = [string]$setupResult.Detail
    setup_functional_failed = $setupFunctionalFailed
    setup_invocations = $setupInvocations
    slot_passed = [bool]$slotResult.Passed
    slot_detail = [string]$slotResult.Detail
    slot_functional_failed = $script:FunctionalFailed
    slot_invocations = $slotInvocations
} | ConvertTo-Json -Depth 8 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["setup_passed"] is True
    assert result["setup_detail"] == ""
    assert result["setup_functional_failed"] is False
    assert [entry["stage"] for entry in result["setup_invocations"]] == [
        "setup-save",
        "setup-label-change",
        "setup-label-change-query",
        "setup-recall",
        "setup-label-restore-query",
    ]
    assert result["slot_passed"] is True
    assert result["slot_detail"] == ""
    assert result["slot_functional_failed"] is False
    assert [entry["stage"] for entry in result["slot_invocations"]] == [
        "setup-slot-save",
        "setup-slot-label-change",
        "setup-slot-recall",
        "setup-slot-label-query",
    ]

    captured_labels = result["captured_labels"]
    assert captured_labels == ["live edit", "slot edit"]
    capabilities = capabilities_for_model_id("keysight-dsox3024a")
    assert [validate_channel_label(value, capabilities) for value in captured_labels] == (
        captured_labels
    )


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_fft_accepts_documented_hann_readback_and_rejects_other_window(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-fft-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Add-CaseResult", "Assert-ScpiSent", "Invoke-BaselineCase")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"fft`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) { throw "Expected one fft case." }
$caseBlock = $matchingCommands[0].Extent.Text

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{ Passed = $Passed; Detail = $Detail }
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    if ($Stage -eq "fft-set") {
        return [pscustomobject]@{
            scpi = [pscustomobject]@{ sent = @(
                ":FUNCtion1:OPERation FFT",
                ":FUNCtion1:SOURce1 CHANnel1",
                ":FUNCtion1:FFT:WINDow HANNing"
            ) }
            result = [pscustomobject]@{}
        }
    }
    if ($Stage -eq "fft-query") {
        return [pscustomobject]@{
            scpi = [pscustomobject]@{ sent = @(
                ":FUNCtion1:OPERation?",
                ":FUNCtion1:SOURce1?",
                ":FUNCtion1:FFT:WINDow?"
            ) }
            result = [pscustomobject]@{
                fft_operation_canonical = "fft"
                source_channel = 1
                window = $script:FftWindow
            }
        }
    }
    if ($Stage -eq "fft-display-off") {
        $script:FftCleanupCalls += 1
        return [pscustomobject]@{
            scpi = [pscustomobject]@{ sent = @(":FUNCtion1:DISPlay OFF") }
            result = [pscustomobject]@{}
        }
    }
    throw "Unexpected stage: ${Stage}"
}

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:FftCleanupCalls = 0
$script:FftWindow = "HANN"
$identity = [pscustomobject]@{
    capabilities = [pscustomobject]@{
        math_function_count = 4
    }
}
Invoke-Expression $caseBlock
$pass = $script:CaseResults["fft"].Passed
$passFailed = $script:FunctionalFailed
$pass_cleanup_calls = $script:FftCleanupCalls

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:FftCleanupCalls = 0
$script:FftWindow = "FLAT"
Invoke-Expression $caseBlock

[ordered]@{
    pass = $pass
    pass_failed = $passFailed
    pass_cleanup_calls = $pass_cleanup_calls
    failure_passed = $script:CaseResults["fft"].Passed
    failure_detail = $script:CaseResults["fft"].Detail
    failure_functional_failed = $script:FunctionalFailed
    failure_drain_calls = $script:DrainCalls
} | ConvertTo-Json -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["pass"] is True
    assert result["pass_failed"] is False
    assert result["pass_cleanup_calls"] == 1
    assert result["failure_passed"] is False
    assert "FFT readback is invalid" in result["failure_detail"]
    assert result["failure_functional_failed"] is True
    assert result["failure_drain_calls"] == 1



@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_live_validator_holdoff_series_gating(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "holdoff-series-gating-harness.ps1"
    harness_path.write_text(
        r'''
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @(
    "ConvertTo-InvariantString",
    "Assert-ScpiSent",
    "Assert-NearlyEqual",
    "Invoke-BaselineCase"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"trigger-holdoff`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) {
    throw "Expected one trigger-holdoff case in ${ScriptPath}."
}
$caseBlock = $matchingCommands[0].Extent.Text

$snapshot = [pscustomobject]@{ TriggerHoldoffSeconds = 0.000002 }
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:ConfigureScpi = @(
    ":TRIGger:HOLDoff:RANDom OFF",
    ":TRIGger:HOLDoff 1e-6"
)
$is4000XSeries = $true

function Add-CaseResult {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [bool] $Passed,

        [string] $Detail = ""
    )

    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Drain-AfterFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $CaseName
    )

    $script:DrainCalls += 1
}

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $Command,

        [string[]] $Arguments = @()
    )

    switch ($Stage) {
        "trigger-holdoff-set" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = $script:ConfigureScpi }
            }
        }
        "trigger-holdoff-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":TRIGger:HOLDoff?") }
                result = [pscustomobject]@{ seconds = 0.000001 }
            }
        }
        "trigger-holdoff-restore" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":TRIGger:HOLDoff 2e-6") }
            }
        }
        default {
            throw "Unexpected stage: ${Stage}"
        }
    }
}

Invoke-Expression $caseBlock
$series4000XResult = $script:CaseResults["trigger-holdoff"].Passed
$series4000XFunctionalFailed = $script:FunctionalFailed
$series4000XDrainCalls = $script:DrainCalls

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:ConfigureScpi = @(":TRIGger:HOLDoff 1e-6")
$is4000XSeries = $false
Invoke-Expression $caseBlock

[ordered]@{
    series_4000x_result = $series4000XResult
    series_4000x_functional_failed = $series4000XFunctionalFailed
    series_4000x_drain_calls = $series4000XDrainCalls
    non_4000x_result = $script:CaseResults["trigger-holdoff"].Passed
    non_4000x_functional_failed = $script:FunctionalFailed
    non_4000x_drain_calls = $script:DrainCalls
} | ConvertTo-Json -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["series_4000x_result"] is True
    assert result["series_4000x_functional_failed"] is False
    assert result["series_4000x_drain_calls"] == 0
    assert result["non_4000x_result"] is True
    assert result["non_4000x_functional_failed"] is False
    assert result["non_4000x_drain_calls"] == 0

@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_channel_vertical_rejects_payload_self_oracle(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-channel-vertical-harness.ps1"
    harness_path.write_text(
        r'''
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @(
    "ConvertTo-InvariantString",
    "Assert-ScpiSent",
    "Assert-NearlyEqual",
    "Invoke-BaselineCase"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"channel-vertical`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) {
    throw "Expected one channel-vertical case in ${ScriptPath}."
}
$caseBlock = $matchingCommands[0].Extent.Text

$script:snapshot = [pscustomobject]@{
    ChannelLabel = "Input a"
    ChannelScale = 0.5
    ChannelRange = 4.0
    ChannelOffset = 0.0
}
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:WrongScalePath = $false

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    switch ($Stage) {
        "channel-label-set" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(':CHANnel1:LABel "Input a"') }
                result = [pscustomobject]@{ command = ':CHANnel1:LABel "Input a"' }
            }
        }
        "channel-label-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:LABel?") }
                result = [pscustomobject]@{ text = "Input a" }
            }
        }
        "channel-vertical-scale-set" {
            $commandText = if ($script:WrongScalePath) {
                ":CHANnel1:OFFSet 2"
            } else {
                ":CHANnel1:SCALe 2"
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @($commandText) }
                result = [pscustomobject]@{ command = $commandText }
            }
        }
        "channel-vertical-scale-query" {
            $scale = if ($script:WrongScalePath) { 0.5 } else { 2.0 }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:SCALe?") }
                result = [pscustomobject]@{ volts_per_division = $scale }
            }
        }
        "channel-range-set" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:RANGe 4") }
                result = [pscustomobject]@{ command = ":CHANnel1:RANGe 4" }
            }
        }
        "channel-range-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:RANGe?") }
                result = [pscustomobject]@{ range_volts = 4.0 }
            }
        }
        "channel-vertical-offset-set" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:OFFSet 0") }
                result = [pscustomobject]@{ command = ":CHANnel1:OFFSet 0" }
            }
        }
        "channel-vertical-offset-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:OFFSet?") }
                result = [pscustomobject]@{ volts = 0.0 }
            }
        }
        default {
            throw "Unexpected stage: ${Stage}"
        }
    }
}

Invoke-Expression $caseBlock
$passResult = $script:CaseResults["channel-vertical"].Passed
$passFunctionalFailed = $script:FunctionalFailed
$passDrainCalls = $script:DrainCalls

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:Invocations.Clear()
$script:WrongScalePath = $true
Invoke-Expression $caseBlock

[ordered]@{
    pass_result = $passResult
    pass_functional_failed = $passFunctionalFailed
    pass_drain_calls = $passDrainCalls
    failure_passed = $script:CaseResults["channel-vertical"].Passed
    failure_detail = $script:CaseResults["channel-vertical"].Detail
    failure_functional_failed = $script:FunctionalFailed
    failure_drain_calls = $script:DrainCalls
    failure_stages = @($script:Invocations | ForEach-Object { $_.stage })
} | ConvertTo-Json -Depth 10 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["pass_result"] is True
    assert result["pass_functional_failed"] is False
    assert result["pass_drain_calls"] == 0
    assert result["failure_passed"] is False
    assert "CH1 scale SCPI path" in result["failure_detail"]
    assert result["failure_functional_failed"] is True
    assert result["failure_drain_calls"] == 1
    assert "channel-vertical-scale-query" in result["failure_stages"]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_acquisition_queries_validate_payloads_and_scpi_history(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-acquisition-harness.ps1"
    harness_path.write_text(
        r'''
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @("Assert-FiniteNumber", "Assert-ScpiSent", "Invoke-BaselineCase")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"acquisition-queries`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) {
    throw "Expected one acquisition-queries case in ${ScriptPath}."
}
$caseBlock = $matchingCommands[0].Extent.Text

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:EmptySampleRateHistory = $false
$is4000XSeries = $true

function Add-CaseResult {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [bool] $Passed,

        [string] $Detail = ""
    )

    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Drain-AfterFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $CaseName
    )

    $script:DrainCalls += 1
}

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $Command,

        [string[]] $Arguments = @()
    )

    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })

    switch ($Stage) {
        "sample-rate-query" {
            if ($script:EmptySampleRateHistory) {
                return [pscustomobject]@{
                    scpi = [pscustomobject]@{ sent = @() }
                    result = [pscustomobject]@{ sample_rate_hz = 5000000000.0 }
                }
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*IDN?", ":ACQuire:SRATe?") }
                result = [pscustomobject]@{ sample_rate_hz = 5000000000.0 }
            }
        }
        "acquisition-points-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*IDN?", ":ACQuire:POINts?") }
                result = [pscustomobject]@{ acquisition_points = 1000000 }
            }
        }
        "record-length-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*IDN?", ":ACQuire:RLENgth?") }
                result = [pscustomobject]@{ record_length_points = 65536 }
            }
        }
        default {
            throw "Unexpected stage: ${Stage}"
        }
    }
}

Invoke-Expression $caseBlock
$passResult = $script:CaseResults["acquisition-queries"].Passed
$passInvocations = @($script:Invocations | ForEach-Object { $_ })
$passFunctionalFailed = $script:FunctionalFailed

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:EmptySampleRateHistory = $true
$is4000XSeries = $true
Invoke-Expression $caseBlock
$failurePassed = $script:CaseResults["acquisition-queries"].Passed
$failureDetail = $script:CaseResults["acquisition-queries"].Detail
$failureFunctionalFailed = $script:FunctionalFailed
$failureDrainCalls = $script:DrainCalls

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:EmptySampleRateHistory = $false
$is4000XSeries = $false
Invoke-Expression $caseBlock

[ordered]@{
    pass_result = $passResult
    pass_functional_failed = $passFunctionalFailed
    pass_invocations = $passInvocations
    failure_passed = $failurePassed
    failure_detail = $failureDetail
    failure_functional_failed = $failureFunctionalFailed
    failure_drain_calls = $failureDrainCalls
    non_4000x_result = $script:CaseResults["acquisition-queries"].Passed
    non_4000x_functional_failed = $script:FunctionalFailed
    non_4000x_invocations = @($script:Invocations | ForEach-Object { $_ })
} | ConvertTo-Json -Depth 12 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["pass_result"] is True
    assert result["pass_functional_failed"] is False
    invocations = result["pass_invocations"]
    assert [entry["command"] for entry in invocations] == [
        "sample-rate",
        "acquisition-points",
        "record-length",
    ]
    assert all(entry["arguments"] == ["--query"] for entry in invocations)
    assert result["failure_passed"] is False
    assert "empty SCPI history" in result["failure_detail"]
    assert result["failure_functional_failed"] is True
    assert result["failure_drain_calls"] == 1
    assert result["non_4000x_result"] is True
    assert result["non_4000x_functional_failed"] is False
    non_4000x_invocations = result["non_4000x_invocations"]
    assert [entry["command"] for entry in non_4000x_invocations] == [
        "sample-rate",
        "acquisition-points",
    ]
    assert all(
        entry["arguments"] == ["--query"] for entry in non_4000x_invocations
    )
    assert "record-length" not in {
        entry["command"] for entry in non_4000x_invocations
    }


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_waveform_amp_case_validates_artifacts_and_restores_unit(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    harness_path = tmp_path / "baseline-waveform-amp-harness.ps1"
    harness_path.write_text(
        r'''
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [string] $ArtifactRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @(
    "Assert-FileNonEmpty",
    "Assert-Capture",
    "Assert-ScpiSent",
    "Invoke-BaselineCase"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"waveform-amp`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) {
    throw "Expected one waveform-amp case in ${ScriptPath}."
}
$caseBlock = $matchingCommands[0].Extent.Text

$script:liveArtifactRoot = $ArtifactRoot
$script:snapshot = [pscustomobject]@{ ChannelUnits = "volt" }
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:EmptyCaptureHistory = $false

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    switch ($Stage) {
        "fixture-baseline-display" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:DISPlay ON") }
                result = [pscustomobject]@{ command = ":CHANnel1:DISPlay ON" }
            }
        }
        "fixture-baseline-scale" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:SCALe 2") }
                result = [pscustomobject]@{ command = ":CHANnel1:SCALe 2" }
            }
        }
        "fixture-baseline-acquisition" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":ACQuire:TYPE NORMal") }
                result = [pscustomobject]@{ command = ":ACQuire:TYPE NORMal" }
            }
        }
        "fixture-baseline-trigger" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(
                    ":TRIGger:MODE EDGE",
                    ":TRIGger:EDGE:SOURce CHANnel1",
                    ":TRIGger:EDGE:SLOPe POSitive"
                ) }
                result = [pscustomobject]@{ command = ":TRIGger:EDGE:SLOPe POSitive" }
            }
        }
        "waveform-amp-unit-set" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:UNITs AMP") }
                result = [pscustomobject]@{ command = ":CHANnel1:UNITs AMP"; units = "amp" }
            }
        }
        "waveform-amp-unit-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:UNITs?") }
                result = [pscustomobject]@{ units = "amp" }
            }
        }
        "waveform-amp-capture" {
            $csvPath = Join-Path $ArtifactRoot "waveform-amp.csv"
            $metadataPath = Join-Path $ArtifactRoot "waveform-amp-meta.json"
            [System.IO.File]::WriteAllText($csvPath, "time_s,ch1_a`n0,1`n")
            [System.IO.File]::WriteAllText(
                $metadataPath,
                '{"format":"BYTE","actual_points":1,"vertical_unit":"A"}'
            )
            $sent = if ($script:EmptyCaptureHistory) {
                @()
            } else {
                @(":CHANnel1:UNITs?", ":WAVeform:FORMat BYTE", ":WAVeform:DATA?")
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = $sent }
                result = [pscustomobject]@{
                    format = "BYTE"
                    actual_points = 1
                    captures = @([pscustomobject]@{ vertical_unit = "A" })
                }
            }
        }
        "waveform-amp-unit-restore" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:UNITs VOLT") }
                result = [pscustomobject]@{ command = ":CHANnel1:UNITs VOLT" }
            }
        }
        "waveform-amp-unit-restore-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:UNITs?") }
                result = [pscustomobject]@{ units = "volt" }
            }
        }
        default { throw "Unexpected stage: ${Stage}" }
    }
}

Invoke-Expression $caseBlock
$passResult = $script:CaseResults["waveform-amp"].Passed
$passInvocations = @($script:Invocations | ForEach-Object { $_ })

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:EmptyCaptureHistory = $true
Invoke-Expression $caseBlock

[ordered]@{
    pass_result = $passResult
    pass_invocations = $passInvocations
    failure_passed = $script:CaseResults["waveform-amp"].Passed
    failure_detail = $script:CaseResults["waveform-amp"].Detail
    failure_functional_failed = $script:FunctionalFailed
    failure_drain_calls = $script:DrainCalls
    failure_invocations = @($script:Invocations | ForEach-Object { $_ })
} | ConvertTo-Json -Depth 12 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-ArtifactRoot",
            str(artifact_root),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["pass_result"] is True
    assert [entry["stage"] for entry in result["pass_invocations"]][-2:] == [
        "waveform-amp-unit-restore",
        "waveform-amp-unit-restore-query",
    ]
    assert result["failure_passed"] is False
    assert "empty SCPI history" in result["failure_detail"]
    assert result["failure_functional_failed"] is True
    assert result["failure_drain_calls"] == 1
    assert [entry["stage"] for entry in result["failure_invocations"]][-2:] == [
        "waveform-amp-unit-restore",
        "waveform-amp-unit-restore-query",
    ]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_restore_carries_proven_save_context_with_fixed_usb_pwd(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-restore-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @(
    "ConvertTo-InvariantString", "Assert-NearlyEqual", "Assert-ScpiSent",
    "Invoke-BaselineCase", "Restore-InstrumentState"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$autoscaleCommand = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "autoscale"')
    )
}, $true)
if ($null -eq $autoscaleCommand) { throw "Missing autoscale case." }
$autoscaleBlock = $autoscaleCommand.Extent.Text

$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:DrainCalls = 0

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Status = if ($Passed) { "PASS" } else { "FAIL" }
        Detail = $Detail
    }
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    switch ($Stage) {
        "fixture-baseline-display" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:DISPlay ON") }
                result = [pscustomobject]@{ command = ":CHANnel1:DISPlay ON" }
            }
        }
        "fixture-baseline-scale" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:SCALe 2") }
                result = [pscustomobject]@{ command = ":CHANnel1:SCALe 2" }
            }
        }
        "fixture-baseline-acquisition" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":ACQuire:TYPE NORMal") }
                result = [pscustomobject]@{ command = ":ACQuire:TYPE NORMal" }
            }
        }
        "fixture-baseline-trigger" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(
                    ":TRIGger:MODE EDGE",
                    ":TRIGger:EDGE:SOURce CHANnel1",
                    ":TRIGger:EDGE:SLOPe POSitive"
                ) }
                result = [pscustomobject]@{ command = ":TRIGger:EDGE:SLOPe POSitive" }
            }
        }
        "autoscale-ch1" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(':AUToscale CHANnel1') }
                result = [pscustomobject]@{}
            }
        }
        "restore-channel-summary-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ channels = @(
                [pscustomobject]@{
                    label = "Original"
                    scale = 1.0
                    range = 8.0
                    offset = 0.0
                    bandwidth_limit = $false
                    impedance = "one_meg"
                    invert = $false
                    units = "volt"
                    vernier = $false
                    probe_ratio = 10.0
                    probe_skew = 0.0
                }
            ) } }
        }
        "restore-display-label-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ display_label = $true } }
        }
        "restore-display-persistence-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ mode = "minimum"; seconds = $null } }
        }
        "restore-display-intensity-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ value = 50 } }
        }
        "restore-display-vectors-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ value = $true } }
        }
        "restore-timebase-reference-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ reference = "center" } }
        }
        "restore-annotation-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{
                enabled = $false
                text = ""
                color = "WHITE"
                background = "OPAQ"
                x = 20
                y = 30
            } }
        }
        "restore-search-state-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ enabled = $false } }
        }
        "restore-wgen-output-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ enabled = $false } }
        }
        "restore-demo-output-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ enabled = $false } }
        }
        "restore-math-display-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ enabled = $false } }
        }
        default { return [pscustomobject]@{ result = [pscustomobject]@{} } }
    }
}

$snapshot = [pscustomobject]@{
    ChannelProbeSkew = 0.0
    ChannelVernier = $false
    ChannelUnits = "volt"
    ChannelInvert = $false
    ChannelImpedance = "one_meg"
    ChannelBandwidthLimit = $false
    ChannelProbeRatio = 10.0
    ChannelRange = 8.0
    ChannelScale = 1.0
    ChannelOffset = 0.0
    ChannelLabel = "Original"
    DisplayIntensity = 50
    DisplayPersistenceSeconds = $null
    DisplayPersistenceMode = "minimum"
    DisplayLabels = $true
    TriggerLevel = 0.0
    TriggerSlope = "negative"
    TriggerSource = "analog-channel"
    TriggerSourceChannel = 2
    TimebasePosition = -4E-05
    TimebaseScale = 0.001
    TimebaseReference = "center"
    ChannelCoupling = "dc"
    ChannelDisplay = $true
    AcquisitionType = "normal"
    AcquisitionCount = 1
        DisplayVectors = $true
        TriggerHoldoffSeconds = 0.000001
        AnnotationRestorable = $true
    AnnotationEnabled = $false
    AnnotationText = ""
    AnnotationColor = "WHITE"
    AnnotationBackground = "OPAQ"
    AnnotationX = 20
    AnnotationY = 30
        SearchSupported = $true
        Is4000XSeries = $true
        WgenApplicable = $true
        MathFunctionCount = 4
        DemoSupported = $true
        TriggerEdgeCoupling = "dc"
    TriggerEdgeReject = "off"
    TriggerSweep = "auto"
    TriggerNoiseReject = $false
    TriggerHfReject = $false
    ExternalTriggerRange = 8.0
    ExternalTriggerProbe = 1.0
    ExternalTriggerUnits = "volts"
    ExternalTriggerLevel = -0.25
        SaveImageFormat = "none"
        SavePwd = "\\Temp\\"
        SaveFilename = "scope"
        SaveImagePalette = "color"
        SaveImageInkSaver = $true
        SaveImageFactors = $false
        SaveWaveformFormat = "csv"
    SaveWaveformLength = 1000
}

$script:SaveFixtureEstablished = $true
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
Invoke-Expression $autoscaleBlock
$autoscaleInvocations = @($script:Invocations | ForEach-Object { $_ })
$autoscaleStatus = [string]$script:CaseResults["autoscale"].Status
$autoscaleFunctionalFailed = $script:FunctionalFailed
$script:Invocations.Clear()
Restore-InstrumentState -Snapshot $snapshot
$installedInvocations = @($script:Invocations | ForEach-Object { $_ })
$snapshot.WgenApplicable = $false
$script:Invocations.Clear()
Restore-InstrumentState -Snapshot $snapshot
$absentInvocations = @($script:Invocations | ForEach-Object { $_ })

$emptySnapshot = $snapshot.PSObject.Copy()
$emptySnapshot.SaveFilename = ""
$script:Invocations.Clear()
$script:SaveFixtureEstablished = $true
Restore-InstrumentState -Snapshot $emptySnapshot
$emptyFilenameInvocations = @($script:Invocations | ForEach-Object { $_ })

$snapshot.WgenApplicable = $null
$script:Invocations.Clear()
Restore-InstrumentState -Snapshot $snapshot
$unknownInvocations = @($script:Invocations | ForEach-Object { $_ })
[ordered]@{
    autoscale_invocations = $autoscaleInvocations
    autoscale_status = $autoscaleStatus
    autoscale_functional_failed = $autoscaleFunctionalFailed
    invocations = $installedInvocations
    absent_invocations = $absentInvocations
    unknown_invocations = $unknownInvocations
    drain_calls = $script:DrainCalls
    empty_filename_invocations = $emptyFilenameInvocations
} | ConvertTo-Json -Depth 10 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    script_text = script_path.read_text(encoding="utf-8")
    assert script_text.index('"image save format context"') < script_text.index(
        'Invoke-BaselineCase -Name "setup-lifecycle"'
    )

    proven_save_context = [
        "save-image-format",
        "save-image-factors",
        "save-image-ink-saver",
        "save-image-palette",
        "save-filename",
        "save-pwd",
        "save-waveform-format",
        "save-waveform-length",
    ]

    assert result["autoscale_status"] == "PASS"
    assert result["autoscale_functional_failed"] is False
    autoscale_commands = [
        entry["command"] for entry in result["autoscale_invocations"]
    ]
    assert autoscale_commands[0] == "autoscale"
    assert "channel-scale" in autoscale_commands
    assert [c for c in autoscale_commands if c.startswith("save-")] == (
        proven_save_context
    )
    commands = [entry["command"] for entry in result["invocations"]]
    for command in (
        "channel-label",
        "channel-scale",
        "channel-offset",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
        "display-label",
        "display-persistence",
        "display-intensity",
        "display-vectors",
        "annotation",
        "search-state",
        "trigger-holdoff",
        "math-display",
        "wgen-output",
        "demo-output",
        "trigger-sweep",
        "trigger-noise-reject",
        "trigger-hf-reject",
        "trigger-edge-coupling",
        "trigger-edge-reject",
        "external-trigger-range",
        "external-trigger-probe",
        "external-trigger-units",
        "trigger-edge-external-level",
    ):
        assert command in commands
    annotation_restore = next(
        entry for entry in result["invocations"] if entry["stage"] == "restore-annotation"
    )
    assert "--clear" in annotation_restore["arguments"]
    assert "--text" not in annotation_restore["arguments"]
    assert "" not in annotation_restore["arguments"]
    assert any(
        entry["stage"] == "restore-annotation-query"
        for entry in result["invocations"]
    )
    save_entries = [
        entry for entry in result["invocations"]
        if entry["command"].startswith("save-")
    ]
    assert [entry["command"] for entry in save_entries] == proven_save_context
    assert save_entries[0]["arguments"] == ["--format", "png"]
    assert save_entries[1]["arguments"] == ["--enabled", "false"]
    assert save_entries[2]["arguments"] == ["--enabled", "true"]
    assert save_entries[3]["arguments"] == ["--palette", "color"]
    assert save_entries[4]["arguments"] == ["--name", "scope"]
    assert save_entries[5]["arguments"] == ["--path", "\\usb"]
    assert save_entries[6]["arguments"] == ["--format", "csv"]
    assert save_entries[7]["arguments"] == ["--points", "1000"]
    pwd_entries = [
        entry for entry in result["invocations"]
        if entry["command"] == "save-pwd"
    ]
    assert len(pwd_entries) == 1
    assert pwd_entries[0]["stage"] == "restore-save-pwd"
    assert pwd_entries[0]["arguments"] == ["--path", "\\usb"]
    restore_start = script_text.index("function Restore-InstrumentState {")
    restore_end = script_text.index(
        "\nif ([string]::IsNullOrWhiteSpace($Resource))", restore_start
    )
    restore_body = script_text[restore_start:restore_end]
    assert 'Command = "save-pwd"' in restore_body
    assert '@("--path", "\\usb")' in restore_body
    assert "SavePwd" not in restore_body
    assert any(
        entry["command"] == "trigger-edge-source"
        and entry["arguments"] == ["--source-channel", "2"]
        for entry in result["invocations"]
    )
    assert any(
        entry["command"] == "trigger-edge-slope"
        and entry["arguments"] == ["--slope", "negative"]
        for entry in result["invocations"]
    )
    assert any(
        entry["command"] == "trigger-edge-external-level"
        and entry["arguments"] == ["--level-volts", "-0.25"]
        for entry in result["invocations"]
    )
    assert not any(
        entry["command"] == "trigger-edge"
        and entry["arguments"][:2] == ["--source-channel", "1"]
        and "positive" in entry["arguments"]
        for entry in result["invocations"]
    )
    assert result["drain_calls"] == 0
    scale_restore = next(
        entry for entry in result["invocations"] if entry["stage"] == "restore-channel-scale"
    )
    assert float(scale_restore["arguments"][-1]) == 1.0
    trigger_level_restore = next(
        entry for entry in result["invocations"] if entry["stage"] == "restore-trigger-edge-level"
    )
    assert float(trigger_level_restore["arguments"][-1]) == 0.0
    timebase_position_restore = next(
        entry
        for entry in result["invocations"]
        if entry["stage"] == "restore-timebase-position"
    )
    assert timebase_position_restore["arguments"] == ["--seconds=-4E-05"]
    timebase_reference_restore = next(
        entry
        for entry in result["invocations"]
        if entry["stage"] == "restore-timebase-reference"
    )
    assert timebase_reference_restore["arguments"] == ["--reference", "center"]
    absent_commands = [entry["command"] for entry in result["absent_invocations"]]
    assert "wgen-output" not in absent_commands
    for command in (
        "trigger-sweep",
        "trigger-noise-reject",
        "trigger-hf-reject",
        "trigger-edge-coupling",
        "trigger-edge-reject",
        "external-trigger-range",
        "external-trigger-probe",
        "external-trigger-units",
        "trigger-edge-external-level",
    ):
        assert command in absent_commands
    assert not any(command.startswith("wgen-") for command in absent_commands)
    unknown_commands = [entry["command"] for entry in result["unknown_invocations"]]
    assert not any(command.startswith("wgen-") for command in unknown_commands)

    save_filename_entries = [
        entry for entry in result["invocations"]
        if entry["command"] == "save-filename"
    ]
    assert len(save_filename_entries) == 1
    assert save_filename_entries[0]["arguments"] == ["--name", "scope"]
    assert not any(
        "--name" in entry["arguments"] and "" in entry["arguments"]
        for entry in result["invocations"]
    )


    empty_save_entries = [
        entry for entry in result["empty_filename_invocations"]
        if entry["command"] == "save-filename"
    ]
    assert len(empty_save_entries) == 0

    empty_save_commands = [
        entry["command"] for entry in result["empty_filename_invocations"]
        if entry["command"].startswith("save-")
    ]
    assert empty_save_commands == [
        "save-image-format",
        "save-image-factors",
        "save-image-ink-saver",
        "save-image-palette",
        "save-pwd",
        "save-waveform-format",
        "save-waveform-length",
    ]

    empty_save_lookup = {
        entry["command"]: entry["arguments"]
        for entry in result["empty_filename_invocations"]
        if entry["command"] in (
            "save-image-format", "save-pwd", "save-waveform-format",
        )
    }
    assert empty_save_lookup["save-image-format"] == ["--format", "png"]
    assert empty_save_lookup["save-pwd"] == ["--path", "\\usb"]
    assert empty_save_lookup["save-waveform-format"] == ["--format", "csv"]

    assert not any(
        arg == ""
        for entry in result["empty_filename_invocations"]
        for arg in entry["arguments"]
    )

@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_diagnostic_drain_ignores_empty_error_collection(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-empty-diagnostic-drain-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Add-Diagnostic", "Drain-AfterFailure")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$script:Diagnostics = [ordered]@{}

function Get-ErrorDrain {
    param([string] $Stage)
    return [pscustomobject]@{
        Errors = @()
        Terminated = $true
    }
}

function Write-DrainErrors {
    throw "Write-DrainErrors must not be called for an empty error collection."
}

Drain-AfterFailure -Stage "empty-error-drain" -CaseName "cleanup"

[ordered]@{
    diagnostic_count = $script:Diagnostics.Count
    diagnostics = @(
        $script:Diagnostics.Values |
            ForEach-Object { $_ } |
            ForEach-Object { [string]$_ }
    )
} | ConvertTo-Json -Depth 6 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["diagnostic_count"] == 0
    assert result["diagnostics"] == []
@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_search_basic_and_event_execution(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-search-harness.ps1"
    harness_path.write_text(
        r"""
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Add-CaseResult", "Assert-ScpiSent", "Invoke-BaselineCase")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$searchBasicCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "search-basic"')
    )
}, $true))
if ($searchBasicCommands.Count -ne 1) {
    throw "Expected one search-basic case in ${ScriptPath}."
}
$searchBasicCode = $searchBasicCommands[0].Extent.Text

$searchEventCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "search-event"')
    )
}, $true))
if ($searchEventCommands.Count -ne 1) {
    throw "Expected one search-event case in ${ScriptPath}."
}
$searchEventCode = $searchEventCommands[0].Extent.Text

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:DrainCalls = 0
$script:SearchCount = 3
$script:SimulateFailure = $false

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    switch -Regex ($Stage) {
        "^search-state-enable$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe 1") }
                result = [pscustomobject]@{ enabled = $true }
            }
        }
        "^search-state-query$" {
            if ($script:SimulateFailure) {
                return [pscustomobject]@{
                    scpi = [pscustomobject]@{ sent = @(":SEARch:STATe?") }
                    result = [pscustomobject]@{ enabled = $false }
                }
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe?") }
                result = [pscustomobject]@{ enabled = $true }
            }
        }
        "^search-mode-(.*)-set$" {
            $mode = $Matches[1]
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe 1", ":SEARch:MODE $($mode.ToUpperInvariant())") }
                result = [pscustomobject]@{ mode = $mode; enabled = $true }
            }
        }
        "^search-mode-(.*)-query$" {
            $mode = $Matches[1]
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:MODE?") }
                result = [pscustomobject]@{ mode = $mode; enabled = $true }
            }
        }
        "^search-count-query$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:COUNt?") }
                result = [pscustomobject]@{ count = [int64]$script:SearchCount }
            }
        }
        "^search-state-disable$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe 0") }
                result = [pscustomobject]@{ enabled = $false }
            }
        }
        "^search-state-disable-query$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe?") }
                result = [pscustomobject]@{ enabled = $false }
            }
        }
        "^search-event-enable$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe 1") }
                result = [pscustomobject]@{ enabled = $true }
            }
        }
        "^search-event-mode-edge$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:MODE EDGE") }
                result = [pscustomobject]@{ mode = "edge"; enabled = $true }
            }
        }
        "^search-event-query$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:EVENt?") }
                result = [pscustomobject]@{ event = [int64]1 }
            }
        }
        "^search-event-count-query$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:COUNt?") }
                result = [pscustomobject]@{ count = [int64]$script:SearchCount }
            }
        }
        "^search-event-set$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:EVENt 1") }
                result = [pscustomobject]@{ event = [int64]1 }
            }
        }
        "^search-event-readback$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:EVENt?") }
                result = [pscustomobject]@{ event = [int64]1 }
            }
        }
        "^search-event-cleanup$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe 0") }
                result = [pscustomobject]@{ enabled = $false }
            }
        }
        "^search-event-cleanup-query$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe?") }
                result = [pscustomobject]@{ enabled = $false }
            }
        }
        default {
            throw "Unexpected stage in test harness: $Stage"
        }
    }
}

function Run-SearchSection {
    param($Identity)
    $supportsEdgeSearch = "edge" -in @($Identity.capabilities.search_modes)
    if (-not $script:FunctionalFailed -and [bool]$Identity.capabilities.supports_search_basic -and $supportsEdgeSearch) {
        Invoke-Expression $searchBasicCode
    }
    if (-not $script:FunctionalFailed -and [bool]$Identity.capabilities.supports_search_event_navigation) {
        Invoke-Expression $searchEventCode
    }
}

# Run 1: 4000X capabilities, count > 0 (normal pass)
$identity4000x = [pscustomobject]@{
    capabilities = [pscustomobject]@{
        supports_search_basic = $true
        supports_search_event_navigation = $true
        search_modes = @("edge", "glitch", "runt", "transition", "serial1", "serial2", "peak")
    }
}
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()
$script:SearchCount = 3
Run-SearchSection -Identity $identity4000x
$pass4000xResults = [ordered]@{}
foreach ($k in $script:CaseResults.Keys) {
    $pass4000xResults[$k] = $script:CaseResults[$k].Passed
}
$pass4000xInvocations = @($script:Invocations | ForEach-Object { $_ })

# Run 2: 4000X capabilities, count == 0 (query only, skips event-set)
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()
$script:SearchCount = 0
Run-SearchSection -Identity $identity4000x
$zeroHit4000xResults = [ordered]@{}
foreach ($k in $script:CaseResults.Keys) {
    $zeroHit4000xResults[$k] = $script:CaseResults[$k].Passed
}
$zeroHit4000xInvocations = @($script:Invocations | ForEach-Object { $_ })

# Run 3: 2000X capabilities (search_modes only serial1, no edge)
$identity2000x = [pscustomobject]@{
    capabilities = [pscustomobject]@{
        supports_search_basic = $true
        supports_search_event_navigation = $false
        search_modes = @("serial1")
    }
}
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()
Run-SearchSection -Identity $identity2000x
$pass2000xResults = [ordered]@{}
foreach ($k in $script:CaseResults.Keys) {
    $pass2000xResults[$k] = $script:CaseResults[$k].Passed
}
$pass2000xInvocations = @($script:Invocations | ForEach-Object { $_ })

# Run 4: Failure path
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()
$script:SimulateFailure = $true
Run-SearchSection -Identity $identity4000x

[ordered]@{
    pass4000x_results = $pass4000xResults
    pass4000x_invocations = $pass4000xInvocations
    zero_hit_results = $zeroHit4000xResults
    zero_hit_invocations = $zeroHit4000xInvocations
    pass2000x_results = $pass2000xResults
    pass2000x_invocations = $pass2000xInvocations
    fail_passed = $script:CaseResults["search-basic"].Passed
    fail_functional_failed = $script:FunctionalFailed
} | ConvertTo-Json -Depth 10 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    data = json.loads(completed.stdout.strip().splitlines()[-1])

    # 4000X normal pass
    assert data["pass4000x_results"]["search-basic"] is True
    assert data["pass4000x_results"]["search-event"] is True
    stages_4000x = [entry["stage"] for entry in data["pass4000x_invocations"]]
    assert "search-state-enable" in stages_4000x
    assert "search-mode-edge-set" in stages_4000x
    assert "search-mode-glitch-set" in stages_4000x
    assert "search-mode-runt-set" in stages_4000x
    assert "search-mode-transition-set" in stages_4000x
    assert "search-mode-peak-set" in stages_4000x
    assert "search-count-query" in stages_4000x
    assert "search-state-disable" in stages_4000x
    assert "search-event-set" in stages_4000x
    assert "search-event-cleanup" in stages_4000x
    assert "search-event-cleanup-query" in stages_4000x

    # 4000X count == 0 skips search-event-set
    assert data["zero_hit_results"]["search-basic"] is True
    assert data["zero_hit_results"]["search-event"] is True
    stages_zero = [entry["stage"] for entry in data["zero_hit_invocations"]]
    assert "search-event-query" in stages_zero
    assert "search-event-count-query" in stages_zero
    assert "search-event-set" not in stages_zero
    assert "search-event-cleanup" in stages_zero
    assert "search-event-cleanup-query" in stages_zero

    # 2000X N/A: neither case runs
    assert "search-basic" not in data["pass2000x_results"]
    assert "search-event" not in data["pass2000x_results"]
    assert len(data["pass2000x_invocations"]) == 0

    # Failure simulation
    assert data["fail_passed"] is False
    assert data["fail_functional_failed"] is True

@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_annotation_execution_and_cleanup(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-annotation-harness.ps1"
    harness_path.write_text(
        r"""
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Add-CaseResult", "Assert-ScpiSent", "Invoke-BaselineCase", "Restore-InstrumentState", "ConvertTo-InvariantString", "Assert-NearlyEqual")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$annotationCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "display-annotation"')
    )
}, $true))
if ($annotationCommands.Count -ne 1) {
    throw "Expected one display-annotation case in ${ScriptPath}."
}
$annotationCode = $annotationCommands[0].Extent.Text

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

$script:SaveFixtureEstablished = $false
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:DrainCalls = 0
$script:SimulateFailure = $false

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    switch -Regex ($Stage) {
        "^annotation-set$" {
            $cmds = @(':DISPlay:ANNotation1:TEXT "Live note"', ":DISPlay:ANNotation1 ON")
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = $cmds }
                result = [pscustomobject]@{ commands = $cmds }
            }
        }
        "^annotation-query$" {
            $cmds = @(
                ":DISPlay:ANNotation1?",
                ":DISPlay:ANNotation1:TEXT?",
                ":DISPlay:ANNotation1:COLor?",
                ":DISPlay:ANNotation1:BACKground?",
                ":DISPlay:ANNotation1:X1Position?",
                ":DISPlay:ANNotation1:Y1Position?"
            )
            if ($script:SimulateFailure) {
                return [pscustomobject]@{
                    scpi = [pscustomobject]@{ sent = $cmds }
                    result = [pscustomobject]@{ commands = $cmds; enabled = $false; text = "wrong"; slot = 1; color = "WHITE"; background = "OPAQ"; x = 20; y = 30 }
                }
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = $cmds }
                result = [pscustomobject]@{ commands = $cmds; enabled = $true; text = "Live note"; slot = 1; color = "WHITE"; background = "OPAQ"; x = 20; y = 30 }
            }
        }
        "^restore-channel-summary-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ channels = @(
                [pscustomobject]@{
                    label = "Original"
                    scale = 1.0
                    range = 8.0
                    offset = 0.0
                    bandwidth_limit = $false
                    impedance = "one_meg"
                    invert = $false
                    units = "volt"
                    vernier = $false
                    probe_ratio = 10.0
                    probe_skew = 0.0
                }
            ) } }
        }
        "^restore-display-label-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ display_label = $true } }
        }
        "^restore-display-persistence-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ mode = "minimum"; seconds = $null } }
        }
        "^restore-display-intensity-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ value = 50 } }
        }
        "^restore-display-vectors-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ value = $true } }
        }
        "^restore-timebase-reference-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ reference = "center" } }
        }
        "^restore-annotation-query$" {
            return [pscustomobject]@{
                result = [pscustomobject]@{ enabled = $false; text = ""; color = "WHITE"; background = "OPAQ"; x = 20; y = 30 }
            }
        }
        default {
            return [pscustomobject]@{ result = [pscustomobject]@{} }
        }
    }
}

# Run 1: Annotation supported, executes display-annotation
$identity = [pscustomobject]@{
    capabilities = [pscustomobject]@{
        supports_annotation = $true
    }
}
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()

if (-not $script:FunctionalFailed -and [bool]$identity.capabilities.supports_annotation) {
    Invoke-Expression $annotationCode
}
$passResult = $script:CaseResults["display-annotation"].Passed
$passInvocations = @($script:Invocations | ForEach-Object { $_ })

# Run 2: Annotation failure
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()
$script:SimulateFailure = $true
if (-not $script:FunctionalFailed -and [bool]$identity.capabilities.supports_annotation) {
    Invoke-Expression $annotationCode
}
$failResult = $script:CaseResults["display-annotation"].Passed
$failFunctionalFailed = $script:FunctionalFailed

# Run 3: Restore when not restorable but supported (safe baseline --slot 1 --off --clear)
$script:Invocations.Clear()
$nonRestorableSnapshot = [pscustomobject]@{
    ChannelProbeSkew = 0.0
    ChannelVernier = $false
    ChannelUnits = "volt"
    ChannelInvert = $false
    ChannelImpedance = "one_meg"
    ChannelBandwidthLimit = $false
    ChannelProbeRatio = 10.0
    ChannelRange = 8.0
    ChannelScale = 1.0
    ChannelOffset = 0.0
    ChannelLabel = "Original"
    DisplayIntensity = 50
    DisplayPersistenceSeconds = $null
    DisplayPersistenceMode = "minimum"
    DisplayLabels = $true
    TriggerLevel = 0.0
    TriggerSlope = "negative"
    TriggerSource = "analog-channel"
    TriggerSourceChannel = 2
    TimebasePosition = 0.0
    TimebaseScale = 0.001
    TimebaseReference = "center"
    ChannelCoupling = "dc"
    ChannelDisplay = $true
    AcquisitionType = "normal"
    AcquisitionCount = 1
    DisplayVectors = $true
    AnnotationRestorable = $false
    AnnotationSupported = $true
}
Restore-InstrumentState -Snapshot $nonRestorableSnapshot
$nonRestorableRestoreInvocations = @($script:Invocations | ForEach-Object { $_ })

[ordered]@{
    pass_result = $passResult
    pass_invocations = $passInvocations
    fail_result = $failResult
    fail_functional_failed = $failFunctionalFailed
    non_restorable_restore_invocations = $nonRestorableRestoreInvocations
} | ConvertTo-Json -Depth 10 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    data = json.loads(completed.stdout.strip().splitlines()[-1])
    assert data["pass_result"] is True
    stages = [entry["stage"] for entry in data["pass_invocations"]]
    assert "annotation-set" in stages
    assert "annotation-query" in stages

    assert data["fail_result"] is False
    assert data["fail_functional_failed"] is True

    restore_commands = [entry for entry in data["non_restorable_restore_invocations"] if entry["command"] == "annotation"]
    assert len(restore_commands) >= 1
    assert restore_commands[0]["arguments"] == ["--slot", "1", "--off", "--clear"]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_capture_wait_trigger_uses_fixed_fixture_and_preserves_timeout_detail(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    artifact_root = tmp_path / "natural-trigger-artifacts"
    artifact_root.mkdir()
    harness_path = tmp_path / "natural-trigger-harness.ps1"
    harness_path.write_text(
        r"""
param(
    [Parameter(Mandatory = $true)][string] $ScriptPath,
    [Parameter(Mandatory = $true)][string] $ArtifactRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @(
        "Get-PayloadErrorText",
        "Get-TriggerDiagnosticText",
        "Invoke-FixtureBaseline",
        "Add-CaseResult",
        "Add-Diagnostic",
        "Invoke-Cli",
        "Invoke-ModeCli",
        "Invoke-LiveCli",
        "Assert-ScpiSent",
        "Assert-NearlyEqual",
        "Assert-FileNonEmpty",
        "Assert-Capture",
        "Invoke-BaselineCase"
    )) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing production function ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$caseCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "capture-wait-trigger"')
    )
}, $true))
if ($caseCommands.Count -ne 1) {
    throw "Expected one production capture-wait-trigger case."
}
$caseCode = $caseCommands[0].Extent.Text

$fixtureCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "fixture-baseline"')
    )
}, $true))
if ($fixtureCommands.Count -ne 1) {
    throw "Expected one production fixture-baseline case."
}
function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainStages.Add($Stage)
}

function Get-ArgumentValue {
    param([string[]] $Arguments, [string] $Name)
    $index = [Array]::IndexOf($Arguments, $Name)
    if ($index -lt 0 -or $index + 1 -ge $Arguments.Count) {
        throw "Missing fake CLI argument ${Name}."
    }
    return [string]$Arguments[$index + 1]
}

function New-SystemError {
    param([int] $Code = 0, [string] $Message = "No error")
    return [pscustomobject]@{
        code = $Code
        message = $Message
        raw = if ($Code -eq 0) { '+0,"No error"' } else { '-310,"System error"' }
    }
}

function New-SuccessPayload {
    param([object] $Result, [string[]] $Sent = @())
    return [pscustomobject]@{
        schema_version = 2
        ok = $true
        command = "fake"
        result = $Result
        error = $null
        system_error = (New-SystemError)
        scpi = [pscustomobject]@{ sent = $Sent }
    }
}

function New-FakeInvocation {
    param(
        [int] $ExitCode,
        [object] $Payload,
        [string] $Stage,
        [string[]] $Arguments
    )
    return [pscustomobject]@{
        ExitCode = $ExitCode
        Payload = $Payload
        Stderr = ""
        Command = "fake-cli $($Arguments -join ' ')"
    }
}

function Invoke-CliRaw {
    param([string] $Stage, [string[]] $Arguments)

    $command = [string]$Arguments[0]
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $command
        arguments = @($Arguments)
    })

    if ($command -eq "measure") {
        throw "Adaptive measurements are forbidden in the fixed trigger fixture."
    }

    switch ($Stage) {
        "capture-wait-trigger-natural" {
            $script:CaptureCount += 1
            if ($script:CaptureCount -ne 1) {
                throw "Natural trigger capture may only be attempted once."
            }
            if ($script:Scenario.Timeout) {
                $trigger = [pscustomobject]@{
                    wait_enabled = $true
                    arm_command = ":SINGle"
                    poll_source = "operation_condition"
                    poll_command = ":OPERegister:CONDition?"
                    timeout_ms = 5000
                    poll_interval_ms = 100
                    force_on_timeout = $false
                    force_command = $null
                    outcome = "timeout"
                    forced = $false
                    timed_out = $true
                    poll_count = 50
                    elapsed_ms = 5000
                    condition_values = @(4152, 4152, 4152)
                    raw_values = @("+4152", "+4152", "+4152")
                    capture_allowed = $false
                    capture_block_reason = "trigger wait did not complete naturally"
                    error = "trigger timeout"
                }
                $payload = [pscustomobject]@{
                    schema_version = 2
                    ok = $false
                    command = "capture"
                    result = [pscustomobject]@{ trigger = $trigger }
                    error = [pscustomobject]@{
                        type = "operation_error"
                        message = "trigger wait timed out"
                    }
                    system_error = (New-SystemError)
                    scpi = [pscustomobject]@{
                        sent = @(":SINGle", ":OPERegister:CONDition?")
                    }
                }
                return New-FakeInvocation 1 $payload $Stage $Arguments
            }

            $csvPath = Get-ArgumentValue -Arguments $Arguments -Name "--csv"
            $metadataPath = Get-ArgumentValue -Arguments $Arguments -Name "--meta"
            [System.IO.File]::WriteAllText($csvPath, "time,channel_1`n0,0`n")
            [System.IO.File]::WriteAllText(
                $metadataPath,
                ([ordered]@{ format = "BYTE"; actual_points = 2 } | ConvertTo-Json -Compress)
            )
            $trigger = [pscustomobject]@{
                wait_enabled = $true
                arm_command = ":SINGle"
                poll_source = "operation_condition"
                poll_command = ":OPERegister:CONDition?"
                timeout_ms = 5000
                poll_interval_ms = 100
                force_on_timeout = $false
                force_command = $null
                outcome = "natural"
                forced = $false
                timed_out = $false
                poll_count = 2
                elapsed_ms = 100
                condition_values = @(4152, 0)
                raw_values = @("+4152", "+0")
                capture_allowed = $true
                capture_block_reason = $null
                error = $null
            }
            $result = [pscustomobject]@{
                channel = 1
                requested_points = 1000
                actual_points = 2
                format = "BYTE"
                captures = @()
                trigger = $trigger
            }
            return New-FakeInvocation 0 (New-SuccessPayload $result @(
                ":SINGle", ":OPERegister:CONDition?", ":WAVeform:DATA?"
            )) $Stage $Arguments
        }
        "capture-wait-trigger-natural-stop" {
            if ($script:Scenario.StopFailure) {
                $payload = [pscustomobject]@{
                    schema_version = 2
                    ok = $false
                    command = "stop-acquisition"
                    result = [pscustomobject]@{}
                    error = [pscustomobject]@{
                        type = "instrument_error"
                        message = "secondary stop failure"
                    }
                    system_error = (New-SystemError -Code -310 -Message "System error")
                    scpi = [pscustomobject]@{ sent = @(":STOP") }
                }
                return New-FakeInvocation 1 $payload $Stage $Arguments
            }
            return New-FakeInvocation 0 (New-SuccessPayload ([pscustomobject]@{
                operation = "stop"
            }) @(":STOP")) $Stage $Arguments
        }
        default {
            throw "Unexpected fake CLI stage: ${Stage}."
        }
    }
}

function Run-Scenario {
    param([object] $Scenario)

    $script:Scenario = $Scenario
    $script:CaptureCount = 0
    $script:Invocations = [System.Collections.Generic.List[object]]::new()
    $script:DrainStages = [System.Collections.Generic.List[string]]::new()
    $script:CaseResults = [ordered]@{}
    $script:Diagnostics = [ordered]@{}
    $script:FunctionalFailed = $false
    $Resource = "TEST::INSTR"
    $script:LiveConnectionArguments = @("--live", "--resource", $Resource)
    $liveArtifactRoot = Join-Path $ArtifactRoot $Scenario.Name
    [void](New-Item -ItemType Directory -Path $liveArtifactRoot -Force)

    Invoke-Expression $caseCode

    $diagnostics = if ($script:Diagnostics.Contains("capture-wait-trigger")) {
        @($script:Diagnostics["capture-wait-trigger"])
    } else {
        @()
    }
    return [pscustomobject]@{
        name = $Scenario.Name
        result = $script:CaseResults["capture-wait-trigger"]
        invocations = @($script:Invocations | ForEach-Object { $_ })
        diagnostics = $diagnostics
        drains = @($script:DrainStages)
        capture_count = $script:CaptureCount
    }
}

$scenarios = @(
    [pscustomobject]@{
        Name = "timeout"
        ReadbackMismatch = ""
        Timeout = $true
        StopFailure = $false
    },
    [pscustomobject]@{
        Name = "timeout-stop-failure"
        ReadbackMismatch = ""
        Timeout = $true
        StopFailure = $true
    },
    [pscustomobject]@{
        Name = "success-stop-failure"
        ReadbackMismatch = ""
        Timeout = $false
        StopFailure = $true
    }
)

@($scenarios | ForEach-Object { Run-Scenario $_ }) |
    ConvertTo-Json -Depth 20 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-ArtifactRoot",
            str(artifact_root),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    scenarios = {
        scenario["name"]: scenario
        for scenario in json.loads(completed.stdout.strip().splitlines()[-1])
    }

    def stages(name: str) -> list[str]:
        return [entry["stage"] for entry in scenarios[name]["invocations"]]

    def invocation(name: str, stage: str) -> dict[str, object]:
        return next(
            entry
            for entry in scenarios[name]["invocations"]
            if entry["stage"] == stage
        )

    expected_success_order = [
        "capture-wait-trigger-natural",
        "capture-wait-trigger-natural-stop",
    ]
    capture_invocation = invocation("timeout", "capture-wait-trigger-natural")
    capture_arguments = capture_invocation["arguments"]
    assert "--wait-trigger" in capture_arguments
    assert capture_arguments[
        capture_arguments.index("--trigger-timeout-ms") + 1
    ] == "5000"
    assert capture_arguments[
        capture_arguments.index("--trigger-poll-interval-ms") + 1
    ] == "100"
    assert "--force-trigger-on-timeout" not in capture_arguments
    assert invocation(
        "timeout", "capture-wait-trigger-natural-stop"
    )["command"] == "stop-acquisition"

    timeout = scenarios["timeout"]
    timeout_detail = timeout["result"]["Detail"]
    assert timeout["result"]["Passed"] is False
    assert timeout["result"]["Status"] == "FAIL"
    assert stages("timeout") == expected_success_order
    assert timeout["capture_count"] == 1
    assert "Fixed natural-trigger fixture capture failed" in timeout_detail
    assert "CH1 Probe Comp connection" in timeout_detail
    assert "exited 1" in timeout_detail
    assert "system error 0: No error" in timeout_detail
    assert "outcome=timeout" in timeout_detail
    assert "timed_out=true" in timeout_detail
    assert "forced=false" in timeout_detail
    assert "capture_allowed=false" in timeout_detail
    assert "poll_count=50" in timeout_detail
    assert "elapsed_ms=5000" in timeout_detail
    assert "raw_values=" in timeout_detail
    assert all(
        "--force-trigger-on-timeout" not in entry["arguments"]
        for entry in timeout["invocations"]
    )
    assert all(
        entry["command"] != "measure"
        for scenario in scenarios.values()
        for entry in scenario["invocations"]
    )

    timeout_cleanup = scenarios["timeout-stop-failure"]
    timeout_cleanup_detail = timeout_cleanup["result"]["Detail"]
    assert "outcome=timeout" in timeout_cleanup_detail
    assert "secondary stop failure" not in timeout_cleanup_detail
    assert "secondary stop failure" in json.dumps(
        timeout_cleanup["diagnostics"]
    )
    assert stages("timeout-stop-failure") == expected_success_order

@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_fixture_baseline_executes_fixed_commands_and_gates_readback_failures(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "fixture-baseline-harness.ps1"
    harness_path.write_text(
        r"""
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @(
    "Assert-ScpiSent", "Assert-NearlyEqual", "Invoke-BaselineCase",
    "Add-CaseResult",
    "Invoke-FixtureBaseline"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing production function ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$fixtureCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "fixture-baseline"')
    )
}, $true))
if ($fixtureCommands.Count -ne 1) { throw "Expected one fixture-baseline case." }
$fixtureCode = $fixtureCommands[0].Extent.Text

$script:snapshot = [pscustomobject]@{
    ChannelScale = 5.0
    TriggerLevel = 100.0
    TriggerSlope = "negative"
    TriggerSource = "analog-channel"
    TriggerSourceChannel = 2
    AcquisitionType = "average"
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    if ($Stage -eq $script:FailureStage) {
        throw "Injected ${Stage} failure"
    }
    switch ($Stage) {
        "fixture-baseline-display-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ display = $true } }
        }
        "fixture-baseline-scale-query" {
            return [pscustomobject]@{
                result = [pscustomobject]@{ volts_per_division = $script:ScaleReadback }
            }
        }
        "fixture-baseline-acquisition-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{ type = "normal" } }
        }
        "fixture-baseline-source-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{
                source = $script:TriggerReadback.Source
                source_channel = $script:TriggerReadback.SourceChannel
            } }
        }
        "fixture-baseline-slope-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{
                slope = $script:TriggerReadback.Slope
            } }
        }
        "fixture-baseline-level-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{
                level_volts = $script:TriggerReadback.Level
            } }
        }
        default {
            $sent = switch ($Stage) {
                "fixture-baseline-display" { @(":CHANnel1:DISPlay ON") }
                "fixture-baseline-scale" { @(":CHANnel1:SCALe 2") }
                "fixture-baseline-acquisition" { @(":ACQuire:TYPE NORMal") }
                "fixture-baseline-trigger" {
                    @(
                        ":TRIGger:MODE EDGE",
                        ":TRIGger:EDGE:SOURce CHANnel1",
                        ":TRIGger:EDGE:SLOPe POSitive"
                    )
                }
                default { @("fixture-${Stage}") }
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = $sent }
                result = [pscustomobject]@{}
            }
        }
    }
}

function Run-Fixture {
    param(
        [string] $Name,
        [object] $TriggerReadback,
        [double] $ScaleReadback = 2.0
    )
    $script:FailureStage = ""
    $script:ScaleReadback = $ScaleReadback
    $script:TriggerReadback = $TriggerReadback
    $script:Invocations = New-Object System.Collections.Generic.List[object]
    $script:DrainCalls = 0
    $script:CaseResults = [ordered]@{}
    $script:FunctionalFailed = $false
    Invoke-Expression $fixtureCode
    return [pscustomobject]@{
        name = $Name
        result = $script:CaseResults["fixture-baseline"]
        functional_failed = $script:FunctionalFailed
        drain_calls = $script:DrainCalls
        invocations = @($script:Invocations | ForEach-Object { $_ })
    }
}

$results = @(
    Run-Fixture "pass" (
        [pscustomobject]@{
            Source = "analog-channel"; SourceChannel = 1; Slope = "positive"; Level = 1.0
        }
    )
    Run-Fixture "scale-mismatch" (
        [pscustomobject]@{
            Source = "analog-channel"; SourceChannel = 1; Slope = "positive"; Level = 1.0
        }
    ) 5.0
    Run-Fixture "trigger-source-mismatch" (
        [pscustomobject]@{
            Source = "analog-channel"; SourceChannel = 2; Slope = "positive"; Level = 1.0
        }
    )
    Run-Fixture "trigger-slope-mismatch" (
        [pscustomobject]@{
            Source = "analog-channel"; SourceChannel = 1; Slope = "negative"; Level = 1.0
        }
    )
    Run-Fixture "trigger-level-mismatch" (
        [pscustomobject]@{
            Source = "analog-channel"; SourceChannel = 1; Slope = "positive"; Level = 2.0
        }
    )
)
$script:ScaleReadback = 2.0
$script:TriggerReadback = [pscustomobject]@{
    Source = "analog-channel"; SourceChannel = 1; Slope = "positive"; Level = 1.0
}
$script:FailureStage = "fixture-baseline-scale"
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:DrainCalls = 0
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
Invoke-Expression $fixtureCode
$results += [pscustomobject]@{
    name = "setter-failure"
    result = $script:CaseResults["fixture-baseline"]
    functional_failed = $script:FunctionalFailed
    drain_calls = $script:DrainCalls
    invocations = @($script:Invocations | ForEach-Object { $_ })
}

@($results) | ConvertTo-Json -Depth 12 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    scenarios = {
        scenario["name"]: scenario
        for scenario in json.loads(completed.stdout.strip().splitlines()[-1])
    }

    pass_stages = [
        entry["stage"] for entry in scenarios["pass"]["invocations"]
    ]
    assert pass_stages == [
        "fixture-baseline-display",
        "fixture-baseline-scale",
        "fixture-baseline-acquisition",
        "fixture-baseline-trigger",
        "fixture-baseline-display-query",
        "fixture-baseline-scale-query",
        "fixture-baseline-acquisition-query",
        "fixture-baseline-source-query",
        "fixture-baseline-slope-query",
        "fixture-baseline-level-query",
    ]
    assert scenarios["pass"]["result"]["Passed"] is True
    assert scenarios["pass"]["functional_failed"] is False

    scale_set = scenarios["pass"]["invocations"][1]
    assert scale_set["command"] == "channel-scale"
    assert scale_set["arguments"][-2:] == ["--volts-per-division", "2"]
    trigger_set = scenarios["pass"]["invocations"][3]
    assert trigger_set["command"] == "trigger-edge"
    assert trigger_set["arguments"][-6:] == [
        "--source-channel", "1", "--level", "1", "--slope", "positive"
    ]

    for name in (
        "scale-mismatch",
        "trigger-source-mismatch",
        "trigger-slope-mismatch",
        "trigger-level-mismatch",
        "setter-failure",
    ):
        scenario = scenarios[name]
        assert scenario["result"]["Passed"] is False
        assert scenario["functional_failed"] is True
        assert scenario["drain_calls"] == 1
        if name == "scale-mismatch":
            assert "Fixture CH1 scale" in scenario["result"]["Detail"]


def test_live_cli_check_recommends_restart_before_validation() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    recommended_start = script.index('Write-Host "RECOMMENDED BEFORE VALIDATION"')
    physical_setup = script.index(
        'Write-Host "PHYSICAL SETUP  operator must prepare"'
    )
    prompt = script.index(
        'Write-Host "Press Enter only after the PHYSICAL SETUP above is ready."'
    )

    assert recommended_start < physical_setup < prompt

    block = script[recommended_start:physical_setup].lower()
    assert "restart" in block
    assert "recommended" in block
    assert "not required" in block
    assert "transient instrument-side state" in block

    checklist = script[physical_setup:prompt]
    assert "restart" not in checklist.lower()
    assert 'Write-Host "  [11]' not in script


def _extract_brace_block(script: str, start: int) -> str:
    depth = 0
    for index in range(start, len(script)):
        if script[index] == "{":
            depth += 1
        elif script[index] == "}":
            depth -= 1
            if depth == 0:
                return script[start : index + 1]
    raise AssertionError("unbalanced braces starting at offset %d" % start)


def test_live_cli_check_warns_4034a_about_autoscale_save_destination() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    gate = 'if ([string]$script:Target -eq "keysight-dsox4034a") {'
    gate_positions = []
    search_from = 0
    while True:
        position = script.find(gate, search_from)
        if position < 0:
            break
        gate_positions.append(position)
        search_from = position + 1
    assert len(gate_positions) == 2, (
        "expected exactly two 4034A gates, found %d" % len(gate_positions)
    )

    recommended_start = script.index(
        'Write-Host "RECOMMENDED BEFORE VALIDATION"'
    )
    physical_setup = script.index(
        'Write-Host "PHYSICAL SETUP  operator must prepare"'
    )
    pass_line = script.index('Write-Host "PASS  baseline live validation"')
    exit_zero = script.index("exit 0", pass_line)

    first_gate, second_gate = gate_positions
    pre_block = _extract_brace_block(script, first_gate)
    post_block = _extract_brace_block(script, second_gate)

    assert recommended_start < first_gate < physical_setup
    assert "KNOWN DSO-X 4034A FRONT-PANEL BEHAVIOR" in pre_block
    assert '`"Please Select`"' in pre_block
    assert "not a Scopes Tool SAVE" in pre_block
    assert "reselect the USB destination under Save To" in pre_block

    assert pass_line < second_gate < exit_zero
    assert "NOTE  DSO-X 4034A Autoscale" in post_block
    assert '`"Please Select`"' in post_block
    assert "Reselect the USB destination" in post_block


VALIDATION_HELPERS_SCRIPT = REPO_ROOT / "scripts" / "_validation_helpers.ps1"
ARTIFACT_PRIVACY_SCRIPT = REPO_ROOT / "scripts" / "_artifact_privacy.ps1"
LIVE_CLI_SCRIPT = REPO_ROOT / "scripts" / "live-cli-check.ps1"
CANONICAL_TARGETS = (
    "keysight-dsox2004a",
    "keysight-dsox3024a",
    "keysight-dsox4024a",
    "keysight-dsox4034a",
)


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_live_cli_script(*args, timeout=180):
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LIVE_CLI_SCRIPT),
            *args,
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def run_live_cli_harness(body, timeout=180):
    command = (
        ". "
        + ps_quote(VALIDATION_HELPERS_SCRIPT)
        + "; . "
        + ps_quote(ARTIFACT_PRIVACY_SCRIPT)
        + "; "
        + body
    )
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def extract_live_cli_functions_ps(names):
    name_list = ", ".join(ps_quote(name) for name in names)
    return """
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    '@SCRIPT@',
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}
$functionSources = New-Object System.Collections.Generic.List[string]
foreach ($functionName in @(@FUNCS@)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in the live script."
    }
    $functionSources.Add($functionAst.Extent.Text)
}
# Define through a temporary file so function bodies are file-backed, matching
# how production loads them. Invoke-Expression compilation trips a PowerShell
# 5.1 DLR array-binding bug for some bodies.
$functionsFile = Join-Path $env:TEMP (
    'live_cli_extracted_' + [guid]::NewGuid().ToString('N') + '.ps1'
)
[System.IO.File]::WriteAllLines(
    $functionsFile,
    $functionSources.ToArray(),
    [System.Text.UTF8Encoding]::new($false)
)
. $functionsFile
Remove-Item -LiteralPath $functionsFile -Force
""".replace("@SCRIPT@", str(LIVE_CLI_SCRIPT)).replace("@FUNCS@", name_list)


@requires_windows
@pytest.mark.parametrize(
    ("args", "expected_error"),
    (
        pytest.param(
            ("-Target", "all", "-Connection", "usb", "-Resource", "TEST::INSTR"),
            "'all' is not supported for live validation",
            id="target-all-rejected",
        ),
        pytest.param(
            (
                "-Target",
                "keysight-dsox9999a",
                "-Connection",
                "usb",
                "-Resource",
                "TEST::INSTR",
            ),
            "Unsupported target 'keysight-dsox9999a'",
            id="invalid-target-rejected",
        ),
        pytest.param(
            (
                "-Target",
                "keysight-dsox4034a",
                "-Connection",
                "rs232",
                "-Resource",
                "TEST::INSTR",
            ),
            "Unsupported connection 'rs232'",
            id="invalid-connection-rejected",
        ),
        pytest.param(
            (
                "-Target",
                "keysight-dsox4034a",
                "-Connection",
                "usb",
                "-Resource",
                "TCPIP0::198.51.100.7::inst0::INSTR",
            ),
            "does not match resource 'TCPIP0::198.51.100.7::inst0::INSTR'",
            id="usb-label-with-tcpip-resource-rejected",
        ),
        pytest.param(
            (
                "-Target",
                "keysight-dsox4034a",
                "-Connection",
                "tcpip",
                "-Resource",
                "USB0::1::2::SYNTH12345::INSTR",
            ),
            "does not match resource 'USB0::1::2::SYNTH12345::INSTR'",
            id="tcpip-label-with-usb-resource-rejected",
        ),
        pytest.param(
            (
                "-Target",
                "keysight-dsox4034a",
                "-Connection",
                "usb",
                "-Resource",
                "USB0::1::2::SYNTH12345::INSTR",
                "-Backend",
                "@unsupported",
            ),
            "Unsupported backend '@unsupported'",
            id="unsupported-backend-rejected",
        ),
    ),
)
def test_live_cli_check_usage_errors(args, expected_error):
    completed = run_live_cli_script(*args)
    assert completed.returncode == 2, completed.stderr + completed.stdout
    assert "[live][cli]" in completed.stderr
    assert expected_error in completed.stderr


@requires_windows
def test_live_cli_check_requires_target_and_connection():
    completed = run_live_cli_script("-Resource", "TEST::INSTR")
    assert completed.returncode != 0
    assert "Target" in completed.stderr

    completed = run_live_cli_script("-Target", "keysight-dsox4034a")
    assert completed.returncode != 0
    assert "Connection" in completed.stderr


@requires_windows
def test_live_cli_check_target_model_match_gate():
    body = """
$results = @{}
$matching = [pscustomobject]@{
    idn = [pscustomobject]@{
        model = "DSOX4034A"
        raw = "KEYSIGHT TECHNOLOGIES,DSOX4034A,SYNTH12345,07.20"
    }
}
try {
    Assert-TargetModelMatch -Identity $matching -ResolvedTarget "keysight-dsox4034a"
    $results.match_canonical = ""
} catch {
    $results.match_canonical = $_.Exception.Message
}
$aliased = [pscustomobject]@{ idn = [pscustomobject]@{ model = "DSO-X 3024A" } }
try {
    Assert-TargetModelMatch -Identity $aliased -ResolvedTarget "keysight-dsox3024a"
    $results.match_alias = ""
} catch {
    $results.match_alias = $_.Exception.Message
}
$mismatched = [pscustomobject]@{ idn = [pscustomobject]@{ model = "DSOX2004A" } }
try {
    Assert-TargetModelMatch -Identity $mismatched -ResolvedTarget "keysight-dsox3024a"
    $results.mismatch = ""
} catch {
    $results.mismatch = $_.Exception.Message
}
$missing = [pscustomobject]@{ idn = $null }
try {
    Assert-TargetModelMatch -Identity $missing -ResolvedTarget "keysight-dsox4034a"
    $results.missing = ""
} catch {
    $results.missing = $_.Exception.Message
}
[ordered]@{
    match_canonical = [string]$results.match_canonical
    match_alias = [string]$results.match_alias
    mismatch = [string]$results.mismatch
    missing = [string]$results.missing
} | ConvertTo-Json -Depth 4 -Compress
"""
    result = run_live_cli_harness(body)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.splitlines()[-1])
    assert payload["match_canonical"] == ""
    assert payload["match_alias"] == ""
    assert "DSOX2004A" in payload["mismatch"]
    assert "does not match" in payload["mismatch"]
    assert "keysight-dsox3024a" in payload["mismatch"]
    assert "unavailable" in payload["missing"]


LIVE_VALIDATOR_SCRIPTS = (
    ("live-dvm-check.ps1", "dvm"),
    ("live-segmented-check.ps1", "segmented"),
    ("live-serial-check.ps1", "serial"),
    ("live-workflow-check.ps1", "workflow"),
)


@requires_windows
@pytest.mark.parametrize(("script_name", "domain"), LIVE_VALIDATOR_SCRIPTS)
def test_live_validators_enforce_canonical_target_contract(tmp_path, script_name, domain):
    script = REPO_ROOT / "scripts" / script_name
    usb = "USB0::1::2::SYNTH12345::INSTR"
    tcpip = "TCPIP0::198.51.100.7::inst0::INSTR"

    def run(*extra: str) -> subprocess.CompletedProcess[str]:
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
                *extra,
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=120,
        )

    completed = run("-Target", "all", "-Connection", "usb", "-Resource", usb)
    assert completed.returncode == 2
    assert "[live][%s]" % domain in completed.stderr
    assert "'all' is not supported for live validation" in completed.stderr

    completed = run(
        "-Target", "keysight-dsox9999a", "-Connection", "usb", "-Resource", usb
    )
    assert completed.returncode == 2
    assert "Unsupported target 'keysight-dsox9999a'" in completed.stderr

    completed = run(
        "-Target", "keysight-dsox4034a", "-Connection", "rs232", "-Resource", usb
    )
    assert completed.returncode == 2
    assert "Unsupported connection 'rs232'" in completed.stderr

    completed = run(
        "-Target", "keysight-dsox4034a", "-Connection", "usb", "-Resource", tcpip
    )
    assert completed.returncode == 2
    assert f"does not match resource '{tcpip}'" in completed.stderr

    completed = run(
        "-Target", "keysight-dsox4034a", "-Connection", "usb",
        "-Resource", usb, "-Backend", "@unsupported"
    )
    assert completed.returncode == 2
    assert "Unsupported backend '@unsupported'" in completed.stderr


@pytest.mark.parametrize(("script_name", "domain"), LIVE_VALIDATOR_SCRIPTS)
def test_live_validators_wire_shared_framework(script_name, domain):
    text = (REPO_ROOT / "scripts" / script_name).read_text(encoding="utf-8")
    for marker in (
        "_validation_helpers.ps1",
        "_artifact_privacy.ps1",
        "Invoke-CapturedCommand ",
        "New-ValidationRunDirectory -BaseRoot $outputBase",
        "Assert-TargetModelMatch -Identity $identity -ResolvedTarget $script:Target",
        f"Complete-LiveValidationRun -Kind 'scopes-tool-live-{domain}-check'",
        "$script:HardwareTouched = $true",
        "$script:Invocations.Add($invocationRecord) | Out-Null",
    ):
        assert marker in text, (script_name, marker)


def _normalize_json_text(text):
    return (
        text.replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\/", "/")
        .replace("\\\\", "\\")
    )


@requires_windows
def test_live_cli_check_complete_run_builds_private_and_shareable_evidence(tmp_path):
    runs_root = tmp_path / "runs"
    resource = "USB0::1::2::SYNTH12345::INSTR"
    body = extract_live_cli_functions_ps(("Write-Summary",)) + """
$Resource = '@RESOURCE@'
$RepoRoot = '@REPO@'
$RunsRoot = '@RUNS@'

# --- scenario 1: FAIL run carrying sensitive evidence ---
$layout = New-ValidationRunDirectory -BaseRoot $RunsRoot -Prefix 'run'
$script:RunDirectory = $layout.Root
$script:RunRoot = $layout.Private
$script:ShareableRoot = $layout.Shareable
$script:Target = 'keysight-dsox4034a'
$script:Connection = 'usb'
$script:BackendName = 'system_visa'
$script:FunctionalFailed = $true
$script:ShareableGenerationFailed = $false
$script:HardwareTouched = $true
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:CliInvocationIndex = 0
$stdoutPath = Join-Path $script:RunRoot 'cli-001-identity.stdout.txt'
$jsonPath = Join-Path $script:RunRoot 'cli-001-identity.json'
Write-Utf8NoBomText -LiteralPath $stdoutPath `
    -Text ('{"ok":true,"resource":"' + $Resource + '"}')
Write-Utf8NoBomText -LiteralPath $jsonPath `
    -Text '{"ok":true,"idn":{"raw":"KEYSIGHT TECHNOLOGIES,DSOX4034A,SYNTH12345,07.20"}}'
$script:Invocations.Add([pscustomobject]@{
    index = 1
    stage = 'identity'
    command = 'python -m scopes_tool_cli.cli identify'
    arguments = @('identify', '--resource', $Resource)
    exit_code = 0
    duration_ms = 123.4
    success = $true
    stdout = (Get-ArtifactRelativePath -Path $stdoutPath -BaseRoot $RepoRoot)
    stderr = ''
    json = (Get-ArtifactRelativePath -Path $jsonPath -BaseRoot $RepoRoot)
}) | Out-Null
$script:CaseResults['identity'] = [pscustomobject]@{
    Passed = $true; Status = 'PASS'; Detail = '' }
$script:CaseResults['pair-measurement'] = [pscustomobject]@{
    Passed = $false; Status = 'FAIL';
    Detail = ('VISA query failed for ' + $Resource +
        ' at host 192.168.1.50 under repo ' + $RepoRoot) }
$script:CaseResults['math-composite-source'] = [pscustomobject]@{
    Passed = $false; Status = 'N/A'; Detail = 'unsupported on detected model' }

Complete-LiveValidationRun -Kind 'scopes-tool-live-cli-check' -Domain 'cli' -Result 'FAIL'

$privateReportRaw =
    [System.IO.File]::ReadAllText((Join-Path $script:RunRoot 'report.json'))
$privateSummaryText =
    [System.IO.File]::ReadAllText((Join-Path $script:RunRoot 'summary.md'))
$shareableDir = Join-Path $script:RunDirectory 'shareable'
$shareableReportRaw =
    [System.IO.File]::ReadAllText((Join-Path $shareableDir 'report.json'))
$shareableSummaryRaw =
    [System.IO.File]::ReadAllText((Join-Path $shareableDir 'summary.md'))
$shareableReport = $shareableReportRaw | ConvertFrom-Json
$privateReport = $privateReportRaw | ConvertFrom-Json
$firstInvocation = @($shareableReport.invocations)[0]
$mirrorReference = [string]$firstInvocation.json
$mirrorPath = Join-Path $shareableDir $mirrorReference.Substring('shareable/'.Length)
$mirrorText = [System.IO.File]::ReadAllText($mirrorPath)

# --- scenario 2: passing cases but shareable generation fails ---
function New-ShareableArtifactSet {
    throw [System.InvalidOperationException]::new(
        'simulated shareable artifact generation failure')
}
$layout2 = New-ValidationRunDirectory -BaseRoot $RunsRoot -Prefix 'run'
$script:RunDirectory = $layout2.Root
$script:RunRoot = $layout2.Private
$script:ShareableRoot = $layout2.Shareable
$script:BackendName = 'pyvisa_py'
$script:FunctionalFailed = $false
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:CaseResults['identity'] = [pscustomobject]@{
    Passed = $true; Status = 'PASS'; Detail = '' }
Complete-LiveValidationRun -Kind 'scopes-tool-live-cli-check' -Domain 'cli' -Result 'PASS'

$s2ReportRaw =
    [System.IO.File]::ReadAllText((Join-Path $script:RunRoot 'report.json'))
$s2SummaryText =
    [System.IO.File]::ReadAllText((Join-Path $script:RunRoot 'summary.md'))
$s2Report = $s2ReportRaw | ConvertFrom-Json

[ordered]@{
    s1_status = [string]$privateReport.status
    s1_target = [string]$privateReport.target
    s1_connection = [string]$privateReport.connection
    s1_backend = [string]$privateReport.backend
    s1_counts_cases = [int]$privateReport.summary_counts.cases
    s1_counts_passed = [int]$privateReport.summary_counts.passed
    s1_counts_failed = [int]$privateReport.summary_counts.failed
    s1_counts_na = [int]$privateReport.summary_counts.na
    s1_counts_invocations = [int]$privateReport.summary_counts.invocations
    s1_hardware_touched = [bool]$privateReport.hardware_touched
    s1_private_report_raw = $privateReportRaw
    s1_private_summary_has_target =
        $privateSummaryText.Contains('Target: keysight-dsox4034a')
    s1_private_summary_has_backend =
        $privateSummaryText.Contains('Backend: system_visa')
    s1_shareable_report_raw = $shareableReportRaw
    s1_shareable_summary_raw = $shareableSummaryRaw
    s1_mirror_reference = $mirrorReference
    s1_mirror_exists = (Test-Path -LiteralPath $mirrorPath -PathType Leaf)
    s1_mirror_text = $mirrorText
    s1_case_statuses = @(@($shareableReport.cases) |
        ForEach-Object { [string]$_.status })
    s1_shareable_status = [string]$shareableReport.status
    s2_flag = $script:ShareableGenerationFailed
    s2_status = [string]$s2Report.status
    s2_backend = [string]$s2Report.backend
    s2_summary_has_backend = $s2SummaryText.Contains('Backend: pyvisa_py')
    s2_error = [string]$s2Report.shareable_generation_error
    s2_summary_reason = $s2SummaryText.Contains(
        'Shareable artifact generation failed:')
} | ConvertTo-Json -Depth 8 -Compress
""".replace("@RESOURCE@", resource).replace("@REPO@", str(REPO_ROOT)).replace(
        "@RUNS@", str(runs_root)
    )

    result = run_live_cli_harness(body, timeout=300)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.splitlines()[-1])

    assert payload["s1_status"] == "failed"
    assert payload["s1_target"] == "keysight-dsox4034a"
    assert payload["s1_connection"] == "usb"
    assert payload["s1_backend"] == "system_visa"
    assert payload["s1_counts_cases"] == 3
    assert payload["s1_counts_passed"] == 1
    assert payload["s1_counts_failed"] == 1
    assert payload["s1_counts_na"] == 1
    assert payload["s1_counts_invocations"] == 1
    assert payload["s1_hardware_touched"] is True
    assert payload["s1_case_statuses"] == ["PASS", "FAIL", "N/A"]
    assert payload["s1_private_summary_has_target"] is True
    assert payload["s1_private_summary_has_backend"] is True
    assert payload["s1_shareable_status"] == "failed"

    # Private evidence retains raw sensitive values.
    normalized_private = _normalize_json_text(payload["s1_private_report_raw"])
    assert resource in normalized_private
    assert "SYNTH12345" in normalized_private

    # Shareable artifacts are redacted everywhere.
    joined_shareable = _normalize_json_text(
        "\n".join(
            (
                payload["s1_shareable_report_raw"],
                payload["s1_shareable_summary_raw"],
                payload["s1_mirror_text"],
            )
        )
    )
    for secret in (resource, "SYNTH12345", "192.168.1.50", str(REPO_ROOT)):
        assert secret not in joined_shareable, secret
    assert "<redacted-resource>" in joined_shareable
    assert "<redacted-idn>" in joined_shareable
    assert "<redacted-ip>" in joined_shareable

    # Invocation references point into the existing shareable tree.
    reference = payload["s1_mirror_reference"]
    assert reference.startswith("shareable/")
    assert payload["s1_mirror_exists"] is True

    # Scenario 2: all cases passed, but shareable generation failed.
    assert payload["s2_flag"] is True
    assert payload["s2_status"] == "failed"
    assert payload["s2_backend"] == "pyvisa_py"
    assert payload["s2_summary_has_backend"] is True
    assert payload["s2_error"] == "simulated shareable artifact generation failure"
    assert payload["s2_summary_reason"] is True


LIVE_VALIDATOR_FINALIZATION_CASES = (
    (
        "live-dvm-check.ps1",
        "scopes-tool-live-dvm-check",
        "dvm",
        "FAIL  DVM live validation",
        "PASS  DVM live validation",
    ),
    (
        "live-segmented-check.ps1",
        "scopes-tool-live-segmented-check",
        "segmented",
        "FAIL  Segmented Memory live validation",
        "PASS  Segmented Memory live validation",
    ),
    (
        "live-serial-check.ps1",
        "scopes-tool-live-serial-check",
        "serial",
        "FAIL  Serial live validation",
        "PASS  Serial live validation",
    ),
    (
        "live-workflow-check.ps1",
        "scopes-tool-live-workflow-check",
        "workflow",
        "FAIL  Workflow live validation",
        "PASS  Workflow live validation",
    ),
)


def _extract_balanced_block(text: str, start_marker: str) -> str:
    start = text.index(start_marker)
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError("unbalanced braces")


@pytest.mark.parametrize(
    ("script_name", "kind", "domain", "fail_label", "pass_label"),
    LIVE_VALIDATOR_FINALIZATION_CASES,
)
def test_live_validator_finalization_control_flow(
    script_name, kind, domain, fail_label, pass_label
):
    text = (REPO_ROOT / "scripts" / script_name).read_text(encoding="utf-8")

    # Migration template placeholders must never reach production output.
    assert "@DOMAIN@" not in text
    assert "@OUTPUTROOT@" not in text

    fail_block = _extract_balanced_block(text, "if ($script:FunctionalFailed) {")
    fail_finalize = (
        "Complete-LiveValidationRun -Kind '{kind}' "
        "-Domain '{domain}' -Result \"FAIL\""
    ).format(kind=kind, domain=domain)
    assert fail_block.count(fail_finalize) == 1
    # The FAIL path always terminates: no fall-through into SKIP/PASS
    # finalization regardless of shareable generation outcome.
    assert fail_block.rstrip().endswith("exit 1\n}")

    block_end = text.index(fail_block) + len(fail_block)
    tail_after_fail = text[block_end:]

    # Exactly one PASS finalization follows, and no stray FAIL finalize.
    pass_finalize = (
        "Complete-LiveValidationRun -Kind '{kind}' "
        "-Domain '{domain}' -Result \"PASS\""
    ).format(kind=kind, domain=domain)
    assert tail_after_fail.count(pass_finalize) == 1
    assert '-Result "FAIL"' not in tail_after_fail

    # Success contract: PASS finalization, then console PASS, then exit 0;
    # a shareable failure downgrades it to FAIL with exit 1.
    pass_tail = tail_after_fail[tail_after_fail.index(pass_finalize) :]
    assert "$script:ShareableGenerationFailed) {" in pass_tail
    assert pass_tail.index('Write-Host "%s"' % pass_label) > pass_tail.index(
        "if ($script:ShareableGenerationFailed)"
    )
    assert pass_tail.rstrip().endswith('Write-Host "%s"\nexit 0' % pass_label)


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize(
    ("series", "installed_options", "expected_transform_status", "expected_transform_operation", "expected_filter_status", "expected_visualization_status"),
    [
        (
            "2000X",
            "BW20",
            "N/A",
            "",
            "N/A",
            "N/A",
        ),
        (
            "3000X",
            "BW20",
            "PASS",
            "differentiate",
            "N/A",
            "N/A",
        ),
    ],
    ids=["2000X_no_plus", "3000X_no_advmath"],
)
def test_live_cli_math_option_applicability_runtime(
    tmp_path: Path,
    series: str,
    installed_options: str,
    expected_transform_status: str,
    expected_transform_operation: str,
    expected_filter_status: str,
    expected_visualization_status: str,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / f"math-option-{series}.ps1"
    harness_path.write_text(
        r'''
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,
    [Parameter(Mandatory = $true)]
    [string] $Series,
    [Parameter(Mandatory = $true)]
    [string] $InstalledOptionsCsv
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($fn in @("Add-CaseResult", "Add-NotApplicableCase", "Add-Diagnostic", "Assert-ScpiSent", "Assert-ScpiSentPrefix", "Invoke-BaselineCase", "Assert-FiniteNumber", "ConvertTo-InvariantString", "Assert-NearlyEqual")) {
    $fa = $ast.Find({
        param($node)
        return ($node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $fn)
    }, $true)
    if ($null -ne $fa) { Invoke-Expression $fa.Extent.Text }
}

# Provide lightweight stubs where production helpers are not needed to load.
if (-not (Get-Command Assert-ScpiSent -ErrorAction SilentlyContinue)) {
    function Assert-ScpiSent { param($Payload,$Label,$ExpectedCommands) }
}
if (-not (Get-Command Assert-ScpiSentPrefix -ErrorAction SilentlyContinue)) {
    function Assert-ScpiSentPrefix { param($Payload,$Label,$ExpectedPrefix) }
}
if (-not (Get-Command Assert-FiniteNumber -ErrorAction SilentlyContinue)) {
    function Assert-FiniteNumber { param($Value,$Label) return [double]$Value }
}
if (-not (Get-Command Add-Diagnostic -ErrorAction SilentlyContinue)) {
    function Add-Diagnostic { param($Name,$Message) }
}
if (-not (Get-Command ConvertTo-InvariantString -ErrorAction SilentlyContinue)) {
    function ConvertTo-InvariantString { param([double]$Value) return $Value.ToString("R", [System.Globalization.CultureInfo]::InvariantCulture) }
}
if (-not (Get-Command Assert-NearlyEqual -ErrorAction SilentlyContinue)) {
    function Assert-NearlyEqual { param([double]$Actual,[double]$Expected,[string]$Label) }
}
function Drain-AfterFailure { param($Stage,$CaseName) }

$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:LastTransformOperation = $null
$script:LastFilterOperation = $null
$script:LastVisualizationOperation = $null
$script:LastVerticalScale = $null
$script:LastVerticalOffset = $null
$script:BaselineVerticalScale = 250000
$script:BaselineVerticalOffset = 0

$installedOptions = @()
if (-not [string]::IsNullOrWhiteSpace($InstalledOptionsCsv)) {
    $installedOptions = @($InstalledOptionsCsv -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })
}

$identity = [pscustomobject]@{
    idn = [pscustomobject]@{ series = $Series }
    capabilities = [pscustomobject]@{
        series = $Series
        math_function_count = 1
        math_filter_operations = @("low-pass", "high-pass")
        math_visualization_operations = @("magnify", "trend")
        supports_math_goft = $true
        supports_measurements = $true
        supports_demo = $false
    }
}
$is2000XSeries = [string]$identity.idn.series -eq "2000X"
$is3000XSeries = [string]$identity.idn.series -eq "3000X"
$is4000XSeries = [string]$identity.idn.series -eq "4000X"
$snapshot = [pscustomobject]@{
    Is4000XSeries = $is4000XSeries
    MathEnhancementsInstalled = $false
    AdvancedMathInstalled = $false
    InstalledOptions = @($installedOptions)
    WgenApplicable = $null
    WgenApplicabilityDetail = ""
    MathFunctionCount = 1
}
# Use production option applicability assignments instead of duplicating logic
$plusAssignmentNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if ($is2000XSeries)') -and $txt.Contains('$snapshot.MathEnhancementsInstalled = "PLUS"')
}, $true))
$advmAssignmentNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if ($is3000XSeries)') -and $txt.Contains('$snapshot.AdvancedMathInstalled = "ADVMATH"')
}, $true))
if ($plusAssignmentNodes.Count -ne 1) { throw "Expected 1 PLUS assignment, found $($plusAssignmentNodes.Count)" }
if ($advmAssignmentNodes.Count -ne 1) { throw "Expected 1 ADVMATH assignment, found $($advmAssignmentNodes.Count)" }
Invoke-Expression $plusAssignmentNodes[0].Extent.Text
Invoke-Expression $advmAssignmentNodes[0].Extent.Text

# Override baseline helpers to capture runtime behavior without real hardware.
function Add-CaseResult {
    param([string]$Name,[bool]$Passed,[string]$Detail="")
    $s = if ($Passed) { "PASS" } else { "FAIL" }
    $script:CaseResults[$Name] = [pscustomobject]@{ Status = $s; Detail = $Detail; Passed = $Passed }
}
function Add-NotApplicableCase {
    param([string]$Name,[string]$Detail)
    $script:CaseResults[$Name] = [pscustomobject]@{ Status = "N/A"; Detail = $Detail; Passed = $false }
    $script:Invocations.Add([pscustomobject]@{ stage = "N/A"; command = "Add-NotApplicableCase"; arguments = @($Name, $Detail) })
}
function Invoke-BaselineCase {
    param([string]$Name,[scriptblock]$Action)
    try {
        & $Action
        if (-not $script:CaseResults.Contains($Name)) {
            $script:CaseResults[$Name] = [pscustomobject]@{ Status = "PASS"; Detail = ""; Passed = $true }
        }
    } catch {
        $script:CaseResults[$Name] = [pscustomobject]@{ Status = "FAIL"; Detail = $_.Exception.Message; Passed = $false }
        $script:FunctionalFailed = $true
    }
}
function Invoke-LiveCli {
    param([string]$Stage,[string]$Command,[string[]]$Arguments=@())
    $script:Invocations.Add([pscustomobject]@{ stage = $Stage; command = $Command; arguments = @($Arguments) })
    switch -Wildcard ($Stage) {
        "math-transform-set" {
            $idx = [array]::IndexOf($Arguments, "--operation")
            if ($idx -ge 0) { $script:LastTransformOperation = $Arguments[$idx+1] }
            $tok = if ($script:LastTransformOperation -eq "differentiate") { "DIFF" } else { "ABSolute" }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":FUNCtion:OPERation $tok", ":FUNCtion:SOURce1 CHANnel1") }
                result = [pscustomobject]@{}
            }
        }
        "math-transform-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @() }
                result = [pscustomobject]@{ math_operation = $script:LastTransformOperation; source = "channel1" }
            }
        }
        "math-filter-set" {
            $idx = [array]::IndexOf($Arguments, "--operation")
            if ($idx -ge 0) { $script:LastFilterOperation = $Arguments[$idx+1] }
            return [pscustomobject]@{ scpi = [pscustomobject]@{ sent = @() }; result = [pscustomobject]@{} }
        }
        "math-filter-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @() }
                result = [pscustomobject]@{ math_operation = $script:LastFilterOperation; source = "channel1" }
            }
        }
        "math-visualization-set" {
            $idx = [array]::IndexOf($Arguments, "--operation")
            if ($idx -ge 0) { $script:LastVisualizationOperation = $Arguments[$idx+1] }
            return [pscustomobject]@{ scpi = [pscustomobject]@{ sent = @() }; result = [pscustomobject]@{} }
        }
        "math-visualization-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @() }
                result = [pscustomobject]@{ math_operation = $script:LastVisualizationOperation }
            }
        }
        "math-vertical-baseline-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":FUNCtion:SCALe?", ":FUNCtion:RANGe?", ":FUNCtion:OFFSet?") }
                result = [pscustomobject]@{ scale = $script:BaselineVerticalScale; range = 2000000; offset = $script:BaselineVerticalOffset }
            }
        }
        "math-vertical-set" {
            $idxScale = [array]::IndexOf($Arguments, "--scale")
            $idxOffset = [array]::IndexOf($Arguments, "--offset")
            if ($idxScale -ge 0) { $script:LastVerticalScale = $Arguments[$idxScale+1] }
            if ($idxOffset -ge 0) { $script:LastVerticalOffset = $Arguments[$idxOffset+1] }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":FUNCtion:SCALe $($Arguments[$idxScale+1])", ":FUNCtion:OFFSet $($Arguments[$idxOffset+1])") }
                result = [pscustomobject]@{}
            }
        }
        "math-vertical-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":FUNCtion:SCALe?", ":FUNCtion:RANGe?", ":FUNCtion:OFFSet?") }
                result = [pscustomobject]@{ scale = [double]$script:LastVerticalScale; range = 2000000; offset = [double]$script:LastVerticalOffset }
            }
        }
        default {
            return [pscustomobject]@{ scpi = [pscustomobject]@{ sent = @() }; result = [pscustomobject]@{} }
        }
    }
}

# Locate the three production Math blocks that now contain option gating.
# Use TrimStart prefix to avoid matching ancestor `if ($snapshotComplete)` blocks.
$transformNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if ($is2000XSeries -and -not $snapshot.MathEnhancementsInstalled') -and $txt.Contains('Add-NotApplicableCase -Name "math-transform"')
}, $true))
$filterNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if (-not $script:FunctionalFailed -and @($identity.capabilities.math_filter_operations).Count -gt 0)') -and $txt.Contains('Add-NotApplicableCase -Name "math-filter"')
}, $true))
$visualNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if (-not $script:FunctionalFailed -and @($identity.capabilities.math_visualization_operations).Count -gt 0)') -and $txt.Contains('Add-NotApplicableCase -Name "math-visualization"')
}, $true))

if ($transformNodes.Count -ne 1) { throw "Expected 1 math-transform conditional, found $($transformNodes.Count)" }
if ($filterNodes.Count -ne 1) { throw "Expected 1 math-filter conditional, found $($filterNodes.Count)" }
if ($visualNodes.Count -ne 1) { throw "Expected 1 math-visualization conditional, found $($visualNodes.Count)" }

# Execute the production conditionals exactly as they appear in the script.
Invoke-Expression $transformNodes[0].Extent.Text
Invoke-Expression $filterNodes[0].Extent.Text
Invoke-Expression $visualNodes[0].Extent.Text

# Also execute math-vertical to verify dynamic fixture (must run after transform which sets DIFF)
$verticalNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if (-not $script:FunctionalFailed -and [int]$identity.capabilities.math_function_count -gt 0)') -and $txt.Contains('Invoke-BaselineCase -Name "math-vertical"')
}, $true))
if ($verticalNodes.Count -ne 1) { throw "Expected 1 math-vertical conditional, found $($verticalNodes.Count)" }
Invoke-Expression $verticalNodes[0].Extent.Text
$verticalResult = if ($script:CaseResults.Contains("math-vertical")) { $script:CaseResults["math-vertical"] } else { $null }

$transformResult = if ($script:CaseResults.Contains("math-transform")) { $script:CaseResults["math-transform"] } else { $null }
$filterResult = if ($script:CaseResults.Contains("math-filter")) { $script:CaseResults["math-filter"] } else { $null }
$visualResult = if ($script:CaseResults.Contains("math-visualization")) { $script:CaseResults["math-visualization"] } else { $null }

# Collect invoked SCPI-like operation names for negative checks.
$allArgs = @($script:Invocations | ForEach-Object { ($_.arguments -join " ") })
$joinedArgs = $allArgs -join " | "

[ordered]@{
    series = $Series
    installed = @($installedOptions)
    math_enhancements = [bool]$snapshot.MathEnhancementsInstalled
    advanced_math = [bool]$snapshot.AdvancedMathInstalled
    transform_status = if ($null -ne $transformResult) { [string]$transformResult.Status } else { "" }
    transform_detail = if ($null -ne $transformResult) { [string]$transformResult.Detail } else { "" }
    transform_operation = [string]$script:LastTransformOperation
    filter_status = if ($null -ne $filterResult) { [string]$filterResult.Status } else { "" }
    filter_detail = if ($null -ne $filterResult) { [string]$filterResult.Detail } else { "" }
    visualization_status = if ($null -ne $visualResult) { [string]$visualResult.Status } else { "" }
    visualization_detail = if ($null -ne $visualResult) { [string]$visualResult.Detail } else { "" }
    vertical_status = if ($null -ne $verticalResult) { [string]$verticalResult.Status } else { "" }
    vertical_detail = if ($null -ne $verticalResult) { [string]$verticalResult.Detail } else { "" }
    vertical_scale = [string]$script:LastVerticalScale
    vertical_offset = [string]$script:LastVerticalOffset
    joined_args = $joinedArgs
    invocations = @($script:Invocations | ForEach-Object { [ordered]@{ stage = $_.stage; command = $_.command; arguments = @($_.arguments) } })
} | ConvertTo-Json -Depth 10 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-Series",
            series,
            "-InstalledOptionsCsv",
            installed_options,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    assert result["series"] == series
    if series == "2000X":
        assert result["math_enhancements"] is False
        assert result["transform_status"] == expected_transform_status
        assert result["filter_status"] == expected_filter_status
        assert result["visualization_status"] == expected_visualization_status
        assert result["transform_operation"] == ""
        assert "PLUS" in result["transform_detail"]
        assert "PLUS" in result["filter_detail"]
        assert "PLUS" in result["visualization_detail"]
        # Must not have executed any PLUS-only SCPI.
        assert "absolute" not in result["joined_args"].lower()
        assert "low-pass" not in result["joined_args"].lower()
        assert "magnify" not in result["joined_args"].lower()
        assert "ABSolute" not in result["joined_args"]
        assert "LOWPass" not in result["joined_args"]
        assert "MAGNify" not in result["joined_args"]
        # Verify math-vertical also uses dynamic baseline (same as 3000X)
        assert result["vertical_status"] == "PASS"
        vertical_invocations = [inv for inv in result["invocations"] if inv["stage"] == "math-vertical-set"]
        assert len(vertical_invocations) == 1
        v_args = vertical_invocations[0]["arguments"]
        assert v_args[v_args.index("--scale") + 1] == "250000"
        assert v_args[v_args.index("--offset") + 1] == "0"
    else:
        assert result["advanced_math"] is False
        assert result["transform_status"] == expected_transform_status
        assert result["transform_operation"] == expected_transform_operation
        assert result["filter_status"] == expected_filter_status
        assert result["visualization_status"] == expected_visualization_status
        assert "ADVMATH" in result["filter_detail"]
        assert "ADVMATH" in result["visualization_detail"]
        # 3000X without ADVMATH must use DIFF, not ABSolute/LOWPass/MAGNify.
        assert result["transform_operation"] == "differentiate"
        assert "differentiate" in result["joined_args"]
        assert "absolute" not in result["joined_args"].lower()
        assert "low-pass" not in result["joined_args"].lower()
        assert "magnify" not in result["joined_args"].lower()
        assert "ABSolute" not in result["joined_args"]
        assert "LOWPass" not in result["joined_args"]
        assert "MAGNify" not in result["joined_args"]
        # Verify math-vertical dynamic fixture: baseline query used and set uses baseline values, not hardcoded 1
        assert result["vertical_status"] == "PASS"
        vertical_invocations = [inv for inv in result["invocations"] if inv["stage"] == "math-vertical-set"]
        assert len(vertical_invocations) == 1
        v_args = vertical_invocations[0]["arguments"]
        scale_idx = v_args.index("--scale") if "--scale" in v_args else -1
        offset_idx = v_args.index("--offset") if "--offset" in v_args else -1
        assert scale_idx != -1 and offset_idx != -1
        assert v_args[scale_idx + 1] == "250000"
        assert v_args[offset_idx + 1] == "0"
        # Ensure baseline query was executed
        baseline_stages = [inv["stage"] for inv in result["invocations"]]
        assert "math-vertical-baseline-query" in baseline_stages
        assert "math-vertical-query" in baseline_stages

@requires_windows
def test_workflow_post_case_error_queue_regression(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-workflow-check.ps1"
    harness_path = tmp_path / "workflow-post-case-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

$functionAst = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-WorkflowCase"
    )
}, $true)
if ($null -eq $functionAst) {
    throw "Invoke-WorkflowCase was not found in ${ScriptPath}."
}
Invoke-Expression $functionAst.Extent.Text

$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:WriteDrainErrorsCalls = New-Object System.Collections.Generic.List[object]
$script:DrainAfterFailureCalls = New-Object System.Collections.Generic.List[object]
$script:AddCaseResultCalls = New-Object System.Collections.Generic.List[object]

function Add-CaseResult {
    param([string] $Name, [string] $Status, [string] $Detail = "")
    $script:AddCaseResultCalls.Add([pscustomobject]@{ Name = $Name; Status = $Status; Detail = $Detail })
    $script:CaseResults[$Name] = [pscustomobject]@{ Status = $Status; Detail = $Detail }
}
function Write-DrainErrors {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]] $Errors,
        [string] $CaseName = ""
    )
    $script:WriteDrainErrorsCalls.Add([pscustomobject]@{ Errors = @($Errors); CaseName = $CaseName })
}
function Drain-AfterFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,
        [Parameter(Mandatory = $true)]
        [string] $CaseName
    )
    $script:DrainAfterFailureCalls.Add([pscustomobject]@{ Stage = $Stage; CaseName = $CaseName })
}
$script:Scenario = "pass"
function Get-ErrorDrain {
    param([Parameter(Mandatory = $true)][string] $Stage)
    if ($script:Scenario -eq "pass") {
        return [pscustomobject]@{
            Invocation = $null
            Entries = @([pscustomobject]@{ code = 0; message = "No error"; raw = '+0,"No error"' })
            Errors = @()
            Terminated = $true
        }
    } else {
        $err = [pscustomobject]@{ code = -221; message = "Settings conflict"; raw = '-221,"Settings conflict"' }
        return [pscustomobject]@{
            Invocation = $null
            Entries = @($err, [pscustomobject]@{ code = 0; message = "No error"; raw = '+0,"No error"' })
            Errors = @($err)
            Terminated = $true
        }
    }
}

# PASS case
$script:Scenario = "pass"
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:WriteDrainErrorsCalls.Clear()
$script:DrainAfterFailureCalls.Clear()
$script:AddCaseResultCalls.Clear()
Invoke-WorkflowCase -Name "demo-pass" -Action { }
$passStatus = $script:CaseResults["demo-pass"].Status
$passFunctional = $script:FunctionalFailed
$passWriteCount = $script:WriteDrainErrorsCalls.Count
$passDrainCount = $script:DrainAfterFailureCalls.Count

# FAIL case
$script:Scenario = "fail"
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:WriteDrainErrorsCalls.Clear()
$script:DrainAfterFailureCalls.Clear()
$script:AddCaseResultCalls.Clear()
Invoke-WorkflowCase -Name "demo-fail" -Action { }
$failStatus = $script:CaseResults["demo-fail"].Status
$failFunctional = $script:FunctionalFailed
$failWriteCount = $script:WriteDrainErrorsCalls.Count
$failDrainCount = $script:DrainAfterFailureCalls.Count
$failDrainStage = if ($failDrainCount -gt 0) { $script:DrainAfterFailureCalls[0].Stage } else { "" }
$failDrainCase = if ($failDrainCount -gt 0) { $script:DrainAfterFailureCalls[0].CaseName } else { "" }
$failDetail = $script:CaseResults["demo-fail"].Detail

[ordered]@{
    pass_status = $passStatus
    pass_functional_failed = $passFunctional
    pass_write_count = $passWriteCount
    pass_drain_count = $passDrainCount
    fail_status = $failStatus
    fail_functional_failed = $failFunctional
    fail_write_count = $failWriteCount
    fail_drain_count = $failDrainCount
    fail_drain_stage = $failDrainStage
    fail_drain_case = $failDrainCase
    fail_detail = $failDetail
} | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["pass_status"] == "PASS"
    assert result["pass_functional_failed"] is False
    assert result["pass_drain_count"] == 0
    assert result["pass_write_count"] == 0
    assert result["fail_status"] == "FAIL"
    assert result["fail_functional_failed"] is True
    assert result["fail_write_count"] == 1
    assert result["fail_drain_count"] == 1
    assert result["fail_drain_stage"] == "demo-fail-error-drain"
    assert result["fail_drain_case"] == "demo-fail"
    assert "Post-case error queue contained" in result["fail_detail"]
