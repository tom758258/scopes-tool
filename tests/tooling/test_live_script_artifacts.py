from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

import pytest
from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.channel import validate_channel_label
from tests.tooling._live_script_test_support import REPO_ROOT


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
    $script:LiveConnectionArguments = @("--resource", $Resource)
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
