from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from tests.tooling._live_script_test_support import REPO_ROOT


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
    assert lister_case.count('"serial-data"') == 1
    assert lister_case.count('"serial-enable"') == 1
    assert lister_case.index('"serial-enable"') < lister_case.index(
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
        '-Command "serial-uart-set"',
        '-Command "serial-uart-show"',
        '-Command "serial-i2c-set"',
        '-Command "serial-i2c-show"',
        '-Command "serial-spi-set"',
        '-Command "serial-spi-show"',
        '-Command "serial-can-set"',
        '-Command "serial-can-show"',
        '-Command "serial-search-uart"',
        '-Command "serial-search-i2c"',
        '-Command "serial-search-spi"',
        '-Command "serial-search-can"',
        '-Command "serial-trigger-uart-set"',
        '-Command "serial-trigger-uart-show"',
        '-Command "serial-trigger-i2c-set"',
        '-Command "serial-trigger-i2c-show"',
        '-Command "serial-trigger-spi-set"',
        '-Command "serial-trigger-spi-show"',
        '-Command "serial-trigger-can-set"',
        '-Command "serial-trigger-can-show"',
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
            f'-Command "serial-{protocol}-show"'
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
            f"serial-{protocol}-show",
            "--simulate",
            "--model",
            "keysight-dsox4034a",
            "--json",
            "--bus",
            "1",
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
    if ($Command -eq "serial-lister-status") {
        return [pscustomobject]@{
            result = [pscustomobject]@{
                display = "bus1"
                reference = "trigger"
            }
        }
    }
    if ($Command -in @("serial-enable", "serial-disable")) {
        return [pscustomobject]@{
            result = [pscustomobject]@{ enabled = ($Command -eq "serial-enable") }
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
        Command = "fake-cli serial-data"
    }
}

Invoke-Expression $listerCommands[0].Extent.Text

$exportInvocations = @($script:Invocations | Where-Object {
    $_.command -eq "serial-data"
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
        "serial-lister-status",
        "single",
    ]
    expected_prefix = expected_lister_prefix
    if not serial_display_enabled:
        expected_prefix = ["serial-enable"] + expected_lister_prefix
    assert commands[: len(expected_prefix)] == expected_prefix
    lister_display_index = 0
    if not serial_display_enabled:
        assert result["invocations"][0]["arguments"] == [
            "--bus",
            "1",
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
                "serial-enable",
                "serial-disable",
                "run",
                "stop-acquisition",
                "force-trigger",
                "digitize",
            }
            for entry in result["invocations"]
        )
    else:
        assert commands.count("serial-enable") == 1
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
        assert commands[-1] == "serial-data"
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
    if ($Command -in @("serial-enable", "serial-disable")) {
        $script:DisplayState = $Command -eq "serial-enable"
    } elseif ($Command -eq "serial-status") {
        # Readback only; display state is tracked locally.
    } else {
        throw ("Unexpected cleanup command: " + $Command)
    }
    return [pscustomobject]@{
        result = [pscustomobject]@{
            display = $script:DisplayState
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
        assert result["commands"] == ["serial-disable"]
        assert result["stages"] == ["cleanup-serial-display"]
        assert result["drain_calls"] == [
            {
                "stage": "cleanup-serial-display-error-drain",
                "case_name": "cleanup",
            }
        ]
        assert "Serial display: display restore rejected" in result["restore_error"]
    else:
        expected_restore = "serial-enable" if original_enabled else "serial-disable"
        assert result["final_enabled"] is original_enabled
        assert result["commands"] == [expected_restore, "serial-status"]
        assert result["stages"] == [
            "cleanup-serial-display",
            "cleanup-serial-display-query",
        ]
        assert result["arguments"] == [
            ["--bus", "1"],
            ["--bus", "1"],
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
    if ($Command -eq "serial-trigger-uart-set") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "uart"; bus = 1; selected = $true
            type = "rx-data"; data = 1; qualifier = "equal"
        }}
    }
    if ($Command -eq "serial-trigger-uart-show") {
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
    if ($Command -eq "serial-trigger-i2c-set") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "i2c"; bus = 1; selected = $true
            type = "read7"; address = 80; data = 1
        }}
    }
    if ($Command -eq "serial-trigger-i2c-show") {
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
    if ($Command -eq "serial-trigger-spi-set") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "spi"; bus = 1; selected = $true
            type = "mosi"; width = 8; data = "00000001"
        }}
    }
    if ($Command -eq "serial-trigger-spi-show") {
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
    if ($Command -eq "serial-trigger-can-set") {
        return [pscustomobject]@{ result = [pscustomobject]@{
            protocol = "can"; bus = 1; selected = $true
            type = "id-and-data"; id_mode = "standard"
            id = "00000000000000000000100100011"
            data = "00000001"; data_length = 1
        }}
    }
    if ($Command -eq "serial-trigger-can-show") {
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
        "serial-trigger-uart-set",
        "serial-trigger-uart-show",
        "serial-search-i2c",
        "serial-search-i2c",
        "serial-trigger-i2c-set",
        "serial-trigger-i2c-show",
        "serial-search-spi",
        "serial-search-spi",
        "serial-trigger-spi-set",
        "serial-trigger-spi-show",
        "serial-search-can",
        "serial-search-can",
        "serial-trigger-can-set",
        "serial-trigger-can-show",
    ]
    assert not {
        "single",
        "run",
        "stop-acquisition",
        "force-trigger",
        "digitize",
        "serial-data",
    }.intersection(commands)

    def arguments_for(command: str) -> list[list[str]]:
        return [entry["arguments"] for entry in invocations if entry["command"] == command]

    assert arguments_for("serial-search-spi") == [
        ["--bus", "1", "--mode", "mosi", "--width", "1", "--data", "0x01"],
        ["--bus", "1", "--query"],
    ]
    assert arguments_for("serial-trigger-spi-set") == [
        ["--bus", "1", "--type", "mosi", "--width", "8", "--data", "0x01"],
    ]
    assert arguments_for("serial-trigger-spi-show") == [
        ["--bus", "1"],
    ]
    assert arguments_for("serial-search-can") == [
        [
            "--bus", "1", "--mode", "data", "--id-mode", "standard",
            "--id", "0x123", "--data", "0x01", "--data-length", "1",
        ],
        ["--bus", "1", "--query"],
    ]
    assert arguments_for("serial-trigger-can-set") == [
        [
            "--bus", "1", "--type", "id-and-data", "--id-mode", "standard",
            "--id", "0x123", "--data", "0x01", "--data-length", "1",
        ],
    ]
    assert arguments_for("serial-trigger-can-show") == [
        ["--bus", "1"],
    ]
