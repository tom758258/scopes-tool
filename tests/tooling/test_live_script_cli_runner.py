from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_SCRIPTS = (
    REPO_ROOT / "scripts" / "live-cli-check.ps1",
    REPO_ROOT / "scripts" / "live-dvm-check.ps1",
    REPO_ROOT / "scripts" / "live-segmented-check.ps1",
    REPO_ROOT / "scripts" / "live-serial-check.ps1",
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

$empty = Invoke-CliRaw -Stage "empty-stderr" -Arguments @("empty-stderr")
$emptyPath = Join-Path $RunRoot "cli-001-empty-stderr.stderr.txt"
$emptyPreference = [string]$ErrorActionPreference

$nonempty = Invoke-CliRaw -Stage "nonempty-stderr" -Arguments @("nonempty-stderr")
$nonemptyPath = Join-Path $RunRoot "cli-002-nonempty-stderr.stderr.txt"
$nonemptyPreference = [string]$ErrorActionPreference

$failure = Invoke-CliRaw -Stage "failure-stderr" -Arguments @("failure-stderr")
$failurePath = Join-Path $RunRoot "cli-003-failure-stderr.stderr.txt"
$failurePreference = [string]$ErrorActionPreference

[ordered]@{
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
} | ConvertTo-Json -Depth 8 -Compress
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

$Resource = "TEST::INSTR"
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
    was_running = script.index("WasRunning = (", snapshot)
    assert snapshot < was_running

    restore = script.index("function Restore-SerialState")
    search = script.index("if ($DisableSearch)", restore)
    lister = script.index("if ($RestoreLister)", search)
    trigger = script.index("if ($RestoreTrigger)", lister)
    acquisition = script.index("if ($RestoreAcquisition)", trigger)
    final_drain = script.index('$finalDrain = Get-ErrorDrain -Stage "final-error-queue"')
    assert restore < search < lister < trigger < acquisition < final_drain

    lister_case_start = script.index(
        'Invoke-SerialCase -Name "UART Lister export"'
    )
    search_case_start = script.index(
        'Invoke-SerialCase -Name "UART Serial Search"', lister_case_start
    )
    lister_case = script[lister_case_start:search_case_start]
    assert lister_case.count('"serial-lister-export"') == 1
    assert '"serial-display"' not in lister_case
    assert ":SAVE:LISTer" not in script
    assert "DIGITIZE" not in lister_case.upper()
    assert '"force-trigger"' not in lister_case


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize("scenario", ["completed", "timeout", "single-failure"])
def test_serial_lister_export_waits_for_fresh_acquisition(
    tmp_path: Path, scenario: str
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
$listerCsvPath = $OutputPath
$script:RunRoot = Split-Path -Parent $OutputPath
$snapshot = [pscustomobject]@{
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
    [System.IO.File]::WriteAllBytes($listerCsvPath, $bytes)
    $reportedPath = (Get-Item -LiteralPath $listerCsvPath).FullName.ToUpperInvariant()
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
$outputExists = Test-Path -LiteralPath $listerCsvPath -PathType Leaf
$outputBytes = if ($outputExists) {
    (Get-Item -LiteralPath $listerCsvPath).Length
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
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    commands = [entry["command"] for entry in result["invocations"]]
    expected_prefix = [
        "serial-lister-display",
        "serial-lister-reference",
        "serial-lister-query",
        "single",
    ]
    assert commands[:4] == expected_prefix
    assert result["invocations"][0]["arguments"] == ["--selection", "bus1"]
    assert commands.count("single") == 1
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
        assert result["invocations"][4]["arguments"] == ["--query"]
        assert result["sleep_values"]
        assert result["operation_status_exists"] is True
        assert result["acquisition_status"]["poll_samples"][0]["result"]["value"] == 56
        assert result["status"] == "PASS", result["detail"]
        assert result["detail"] == ""
        assert result["export_count"] == 1
        assert commands[-1] == "serial-lister-export"
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
        assert result["invocations"][4]["arguments"] == ["--query"]
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
    -RestoreLister $false -RestoreTrigger $false `
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
foreach ($name in @("Get-RequiredResultValue", "Assert-SerialCriteriaReadback")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
        )
    }, $true)
    Invoke-Expression $functionAst.Extent.Text
}

$caseCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        ($node.Extent.Text.Contains('Invoke-SerialCase -Name "UART Serial Search"') -or
         $node.Extent.Text.Contains('Invoke-SerialCase -Name "UART Serial Trigger"'))
    )
}, $true))
if ($caseCommands.Count -ne 2) {
    throw "Expected production Serial Search and Trigger cases."
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
    ]
    assert not {
        "single",
        "run",
        "stop-acquisition",
        "force-trigger",
        "digitize",
        "serial-lister-export",
    }.intersection(commands)


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

$supportsSkip = [System.IO.Path]::GetFileName($ScriptPath) -ne "live-cli-check.ps1"

$script:RunRoot = Join-Path $OutputRoot "pass"
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
if ($supportsSkip) {
    Add-CaseResult -Name "preflight" -Status "PASS"
} else {
    Add-CaseResult -Name "preflight" -Passed $true
}
Write-DrainErrors -Errors @(
    [pscustomobject]@{ code = -350; message = "stale diagnostic" }
) -CaseName "stale-error-drain"
Write-Summary -Result "PASS"

$script:RunRoot = Join-Path $OutputRoot "fail"
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
if ($supportsSkip) {
    Add-CaseResult -Name "functional-case" -Status "FAIL" `
        -Detail "known failure detail"
} else {
    Add-CaseResult -Name "functional-case" -Passed $false `
        -Detail "known failure detail"
}
Write-Summary -Result "FAIL"

$script:RunRoot = Join-Path $OutputRoot "scpi-fail"
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
if ($supportsSkip) {
    Add-CaseResult -Name "final-error-queue" -Status "FAIL" `
        -Detail "Final error queue contained 1 error(s)."
} else {
    Add-CaseResult -Name "final-error-queue" -Passed $false `
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

    if script_path.name != "live-cli-check.ps1":
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
            "-Resource",
            "TEST::INSTR",
            "-Python",
            sys.executable,
            "-OutputRoot",
            str(output_root),
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
    summary_path = run_roots[0] / "summary.md"
    summary_bytes = summary_path.read_bytes()
    summary = summary_bytes.decode("utf-8")
    assert not summary_bytes.startswith(b"\xef\xbb\xbf")
    assert "Result: FAIL" in summary
    assert "| preflight | FAIL |" in summary
    assert "| preflight | FAIL |  |" not in summary

    invocations = [
        json.loads(line)
        for line in invocation_log.read_text(encoding="utf-8").splitlines()
    ]
    assert invocations
    assert all("--live" not in arguments for arguments in invocations)


def test_baseline_live_script_contains_p1_case_wiring() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    for case_name in (
        "acquisition-average",
        "acquisition-queries",
        "system-status",
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
        'Command "system-options"',
        'Command "measure-results"',
        'Command "channel-summary"',
    ):
        assert command in script

    assert "$identity.capabilities.supports_measure_results_dump" in script
    assert '@("--type", "average", "--count", "16")' in script
    assert '@("--type", "normal")' in script

    system_status_start = script.index(
        'Invoke-BaselineCase -Name "system-status"'
    )
    system_status_end = script.index(
        "\n    if (-not $script:FunctionalFailed -and", system_status_start
    )
    system_status_case = script[system_status_start:system_status_end]
    assert '"system-standard-event"' not in system_status_case
    assert "*ESR?" not in system_status_case

    invoke_live_cli_start = script.index("function Invoke-LiveCli {")
    invoke_live_cli_end = script.index(
        "\nfunction Get-ErrorDrain {", invoke_live_cli_start
    )
    invoke_live_cli = script[invoke_live_cli_start:invoke_live_cli_end]
    assert '"--log-scpi"' not in invoke_live_cli


def test_baseline_live_script_contains_p2_case_and_restore_wiring() -> None:
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
    assert channel_vertical.index('Stage "channel-scale-set-p2"') < (
        channel_vertical.index('Stage "channel-scale-query-p2"')
    )
    assert channel_vertical.index('Stage "channel-scale-query-p2"') < (
        channel_vertical.index('Stage "channel-range-set"')
    )
    assert channel_vertical.index('Stage "channel-range-set"') < (
        channel_vertical.index('Stage "channel-range-query"')
    )

    assert '$identity.capabilities.supports_screenshot_format_pack' in script
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
        "search-mode",
    ):
        assert f'Command = "{command}"' in restore


def test_baseline_live_script_contains_p3_case_and_safety_wiring() -> None:
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
        "fft",
        "wgen-basic",
        "demo-basic",
        "autoscale",
        "setup-lifecycle",
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

    assert '$snapshot.P3Enabled' in script
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
    assert 'SaveImageFormat -in @("png", "bmp", "bmp8", "bmp24")' in script
    assert 'Stage "preflight-p3-save-waveform-length-max-query"' in preflight
    assert '-Command "save-waveform-length-max"' in preflight
    assert '-Arguments @("--query")' in preflight
    assert '-Stage "snapshot-save-waveform-length-max"' in script
    assert '-Command "save-waveform-length-max" -Arguments @("--query")' in script
    assert "SaveWaveformLengthMax = if" in script
    assert '@("--format", "none")' not in script
    assert '"\\usb\\scopes-tool-live-${timestamp}.scp"' in script
    assert '"--slot"' not in script[script.index('Invoke-BaselineCase -Name "setup-lifecycle"'):]
    assert "Leave WGEN output OFF" in script
    assert "Leave DEMO output OFF" in script
    assert "External trigger input" in script
    assert "Math Function 1 is disposable" in script

    save_export_start = script.index('Invoke-BaselineCase -Name "save-export"')
    save_export_end = script.index(
        'Invoke-BaselineCase -Name "safe-cleanup"', save_export_start
    )
    save_export = script[save_export_start:save_export_end]
    waveform_stage = save_export.index('$waveform = Invoke-LiveCli -Stage "save-waveform"')
    waveform_validation = save_export.index(
        "if (-not [bool]$waveform.result.instrument_side", waveform_stage
    )
    handoff_delay = save_export.index("Start-Sleep -Milliseconds 500")
    first_restore = save_export.index(
        'Invoke-LiveCli -Stage "save-image-format-restore"'
    )
    assert save_export.count("Start-Sleep -Milliseconds 500") == 1
    assert waveform_stage < waveform_validation < handoff_delay < first_restore
    assert (
        'throw "Instrument waveform save result is invalid."\n'
        "                }\n"
        "                Start-Sleep -Milliseconds 500"
        in save_export
    )


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

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add($Stage)
    if ($script:Scenario -eq "body-and-restore-fail" -and
        $Stage -eq "save-image-format-png") {
        throw "body primary failure"
    }
    if ($script:Scenario -in @("body-and-restore-fail", "restore-only-fail") -and
        $Stage -eq "save-image-format-restore") {
        throw "image restore failure"
    }
    if ($Stage -eq "save-image") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            instrument_side = $true
            operation_complete = $true
            filename = $Arguments[1]
        } }
    }
    if ($Stage -eq "save-waveform") {
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
    $snapshot = [pscustomobject]@{
        SaveImageFormat = "png"
        SaveWaveformFormat = "csv"
        SaveWaveformLength = 2000
        SaveWaveformLengthMax = $LengthMax
    }
    $timestamp = "test"
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
        functional_failed = $script:FunctionalFailed
        drain_calls = $script:DrainCalls
    }
}

[ordered]@{
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

    combined = result["body_and_restore_fail"]
    assert combined["passed"] is False
    assert "body primary failure" in combined["detail"]
    assert "image restore failure" not in combined["detail"]
    assert any("image restore failure" in item for item in combined["diagnostics"])
    assert combined["invocations"][-3:] == [
        "save-image-format-restore",
        "save-waveform-format-restore",
        "save-waveform-length-restore",
    ]

    restore_only = result["restore_only_fail"]
    assert restore_only["passed"] is False
    assert "image restore failure" in restore_only["detail"]
    assert restore_only["functional_failed"] is True
    assert restore_only["drain_calls"] == 1

    max_enabled = result["max_enabled"]
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
def test_baseline_p3_fft_accepts_documented_hann_readback_and_rejects_other_window(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-p3-fft-harness.ps1"
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
    throw "Unexpected stage: ${Stage}"
}

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:FftWindow = "HANN"
Invoke-Expression $caseBlock
$pass = $script:CaseResults["fft"].Passed
$passFailed = $script:FunctionalFailed

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:FftWindow = "FLAT"
Invoke-Expression $caseBlock

[ordered]@{
    pass = $pass
    pass_failed = $passFailed
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
    assert result["failure_passed"] is False
    assert "FFT readback is invalid" in result["failure_detail"]
    assert result["failure_functional_failed"] is True
    assert result["failure_drain_calls"] == 1


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_p2_channel_vertical_rejects_payload_self_oracle(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-p2-channel-vertical-harness.ps1"
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
        "channel-scale-set-p2" {
            $commandText = if ($script:WrongScalePath) {
                ":CHANnel1:OFFSet 0.5"
            } else {
                ":CHANnel1:SCALe 0.5"
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @($commandText) }
                result = [pscustomobject]@{ command = $commandText }
            }
        }
        "channel-scale-query-p2" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:SCALe?") }
                result = [pscustomobject]@{ volts_per_division = 0.5 }
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
        "channel-offset-set-p2" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:OFFSet 0") }
                result = [pscustomobject]@{ command = ":CHANnel1:OFFSet 0" }
            }
        }
        "channel-offset-query-p2" {
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
    assert "channel-scale-query-p2" in result["failure_stages"]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_p1_cases_validate_payloads_and_scpi_history(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-p1-harness.ps1"
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
Invoke-Expression $caseBlock

[ordered]@{
    pass_result = $passResult
    pass_functional_failed = $passFunctionalFailed
    pass_invocations = $passInvocations
    failure_passed = $script:CaseResults["acquisition-queries"].Passed
    failure_detail = $script:CaseResults["acquisition-queries"].Detail
    failure_functional_failed = $script:FunctionalFailed
    failure_drain_calls = $script:DrainCalls
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


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_p2_amp_case_validates_artifacts_and_restores_unit(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    harness_path = tmp_path / "baseline-p2-amp-harness.ps1"
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
def test_baseline_p2_restore_executes_public_cli_steps(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-p2-restore-harness.ps1"
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
    "ConvertTo-InvariantString", "Assert-NearlyEqual", "Restore-InstrumentState"
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

$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:DrainCalls = 0

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
    TimebasePosition = 0.0
    TimebaseScale = 0.001
    ChannelCoupling = "dc"
    ChannelDisplay = $true
    AcquisitionType = "normal"
    AcquisitionCount = 1
    DisplayVectors = $true
    AnnotationRestorable = $true
    AnnotationEnabled = $false
    AnnotationText = ""
    AnnotationColor = "WHITE"
    AnnotationBackground = "OPAQ"
    AnnotationX = 20
    AnnotationY = 30
    SearchRestorable = $true
    SearchMode = "edge"
    SearchEnabled = $false
    P3Enabled = $true
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
    SaveWaveformFormat = "csv"
    SaveWaveformLength = 1000
}

Restore-InstrumentState -Snapshot $snapshot
[ordered]@{
    invocations = @($script:Invocations | ForEach-Object { $_ })
    drain_calls = $script:DrainCalls
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
        "search-mode",
        "search-state",
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
        "save-waveform-format",
        "save-waveform-length",
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
    assert not any(
        entry["command"] == "save-image-format"
        and entry["arguments"] == ["--format", "none"]
        for entry in result["invocations"]
    )
    assert any(
        entry["command"] == "save-waveform-format"
        and entry["arguments"] == ["--format", "csv"]
        for entry in result["invocations"]
    )
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
