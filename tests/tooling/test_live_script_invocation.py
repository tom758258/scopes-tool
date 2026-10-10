from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from tests.tooling._live_script_test_support import REPO_ROOT, requires_windows


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize("script_path", (REPO_ROOT / "scripts" / "live-cli-check.ps1",), ids=lambda path: path.stem)
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
@pytest.mark.parametrize("script_path", (REPO_ROOT / "scripts" / "live-cli-check.ps1",), ids=lambda path: path.stem)
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

$script:LiveConnectionArguments = @("--resource", "TEST::INSTR")
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
@pytest.mark.parametrize("script_path", (REPO_ROOT / "scripts" / "live-cli-check.ps1",), ids=lambda path: path.stem)
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
@pytest.mark.parametrize("script_path", (REPO_ROOT / "scripts" / "live-cli-check.ps1",), ids=lambda path: path.stem)
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

    output_root = tmp_path / "preflight_cli_check"
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
@pytest.mark.parametrize("script_path", (REPO_ROOT / "scripts" / "live-cli-check.ps1",), ids=lambda path: path.stem)
@pytest.mark.parametrize(
    ("backend", "expected_arguments"),
    (
        pytest.param(
            "",
            ["--resource", "TEST::INSTR"],
            id="system-visa",
        ),
        pytest.param(
            "@py",
            [
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
