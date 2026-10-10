from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest
from tests.tooling._live_script_test_support import REPO_ROOT, requires_windows


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
    ("result_fields", "expected_passed", "expected_unit"),
    [
        ({"unit": "volt"}, True, "volt"),
        ({"unit": "amp"}, True, "amp"),
        ({}, False, None),
        ({"unit": "volts"}, False, None),
    ],
)
def test_dvm_snapshot_unit_contract(
    tmp_path: Path, result_fields: dict, expected_passed: bool, expected_unit
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-dvm-check.ps1"
    harness_path = tmp_path / "dvm-snapshot-unit.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [string] $ResultJson
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
    "Get-RequiredResultValue",
    "Get-DvmSnapshot"
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

$payload = [pscustomobject]@{
    result = ($ResultJson | ConvertFrom-Json)
}

$outcome = [ordered]@{
    passed = $false
    unit = $null
    error = ""
}
try {
    $snapshot = Get-DvmSnapshot -Payload $payload -Stage "unit contract"
    $outcome.passed = $true
    $outcome.unit = $snapshot.DvmUnit
} catch {
    $outcome.error = [string]$_.Exception.Message
}
$outcome | ConvertTo-Json -Compress
""",
        encoding="utf-8",
    )
    result = {
        "enabled": True,
        "source_channel": 1,
        "mode": "dc",
        "auto_range_enabled": False,
        **result_fields,
    }

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
            "-ResultJson",
            json.dumps(result),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    outcome = json.loads(completed.stdout.splitlines()[-1])
    assert outcome["passed"] is expected_passed
    assert outcome["unit"] == expected_unit


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
$script:LiveConnectionArguments = @("--resource", $Resource)

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
