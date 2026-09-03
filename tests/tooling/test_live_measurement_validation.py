from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "live-cli-check.ps1"


def _case_block(script: str, case_name: str, next_case_name: str) -> str:
    start = script.index(f'Invoke-BaselineCase -Name "{case_name}"')
    end = script.index(f'Invoke-BaselineCase -Name "{next_case_name}"', start)
    return script[start:end]


def _pair_lifecycle_block(script: str) -> str:
    start = script.index("$pairMeasurementSnapshot = $null")
    end = script.index('Invoke-BaselineCase -Name "measure-stats"', start)
    return script[start:end]


def test_single_measurement_breadth_uses_raw_acceptance_path() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    common = _case_block(script, "measurements", "measure-area")
    area = _case_block(script, "measure-area", "measure-phase")

    assert '"area"' not in common
    assert '"--level", "0.5", "--slope", "positive", "--occurrence", "1"' in common
    assert "Invoke-CliRaw" in common
    assert "Assert-SingleMeasurementInvocation" in common
    assert 'Invoke-LiveCli -Stage "measure-${item}"' not in common

    # measure-area must be capability-gated and retain raw acceptance semantics
    assert 'if (-not $script:FunctionalFailed -and [bool]$identity.capabilities.supports_area_measurement)' in script
    assert "Invoke-CliRaw" in area
    assert "Assert-SingleMeasurementInvocation" in area
    assert "Add-NotApplicableCase" in script
    assert 'Add-NotApplicableCase -Name "measure-area"' in script
    assert '"--item", "area"' in area


def test_measure_statistics_uses_capability_gate() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    # outer gate must be on statistics capability, not just general measurements
    assert 'if (-not $script:FunctionalFailed -and [bool]$identity.capabilities.supports_measure_statistics)' in script
    stats = _case_block(script, "measure-stats", "measure-controls")
    assert "Add-NotApplicableCase" in script
    assert 'Add-NotApplicableCase -Name "measure-stats"' in script
    assert "Measurement statistics are unsupported by the detected instrument." in script
    assert "query_measurement_statistics_state" in stats
    assert '-Command "measure-stats"' in stats
    assert '"--mode", "all", "--reset"' in stats
    assert '"--max-count", "2000"' in stats
    assert '":MEASure:STATistics:MCOUnt 2000"' in stats
    assert 'configure_measurement_statistics_mode("stddev")' in stats
    assert 'raw_mode.upper() == "STDD"' in stats
    assert "configure_measurement_statistics_display" in stats
    assert "configure_measurement_statistics_max_count(2000)" in stats
    assert "configure_measurement_statistics_max_count(None)" in stats
    assert "configure_measurement_statistics_relative_stddev" in stats
    assert "reset_measurement_statistics" in stats
    assert "increment_measurement_statistics" not in stats
    assert "finally:" in stats
    assert "snapshot_mode" in stats
    assert "$statisticsRestoreProgram" in stats
    assert "Statistics state restore readback failed." in stats
    # Embedded statistics programs must run via stdin, not `python -c`,
    # so multiline source avoids Windows native argv quote marshalling.
    assert "& $Python -c $statisticsProgram" not in stats
    assert "& $Python -c $statisticsRestoreProgram" not in stats
    assert "$statisticsProgram |" in stats
    assert "& $Python - $Resource $statisticsBackend $script:Target 2>&1" in stats
    assert "$statisticsRestoreProgram |" in stats
    assert "& $Python - $Resource $statisticsBackend" in stats
    assert "$snapshotMaxCount $snapshotRsd 2>&1" in stats


def test_measure_controls_validates_public_install_without_auto_clear() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    controls = _case_block(script, "measure-controls", "cursor-lifecycle")

    assert '-Command "measure-install"' in controls
    assert '"--source-channel", "1", "--item", "ac_rms"' in controls
    assert '":MEASure:SOURce CHANnel1"' in controls
    assert '":MEASure:VRMS DISPlay,AC"' in controls
    # The no-clear assertion must be scoped to the install invocation because
    # the same case intentionally runs measure-clear afterwards.
    assert "@($install.scpi.sent) -contains" in controls
    assert "measure-install unexpectedly cleared existing measurements." in controls
    assert controls.index('-Command "measure-install"') < controls.index(
        '-Command "measure-clear"'
    )


def test_pair_measurements_remain_strict() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    lifecycle = _pair_lifecycle_block(script)
    phase = _case_block(script, "measure-phase", "measure-delay")
    delay = _case_block(script, "measure-delay", "measure-stats")

    for field in ("Display", "Coupling", "Scale", "Offset", "ProbeRatio"):
        assert f"{field} =" in script[script.index("function Get-PairMeasurementChannelSnapshot") :]
    for stage in (
        'Stage "pair-ch2-snapshot-display"',
        'Stage "pair-ch2-snapshot-coupling"',
        'Stage "pair-ch2-snapshot-scale"',
        'Stage "pair-ch2-snapshot-offset"',
        'Stage "pair-ch2-snapshot-probe"',
    ):
        assert stage in script
    assert lifecycle.index("Get-PairMeasurementChannelSnapshot") < lifecycle.index(
        "Prepare-PairMeasurementChannel"
    )
    assert lifecycle.index("Prepare-PairMeasurementChannel") < lifecycle.index(
        'Stage "pair-measurement-run"'
    )
    assert lifecycle.index("Invoke-PairMeasurementReadiness") < lifecycle.index(
        'Invoke-BaselineCase -Name "measure-phase"'
    )
    assert lifecycle.index('Stage "pair-measurement-run"') < lifecycle.index(
        "Invoke-PairMeasurementReadiness"
    )
    assert lifecycle.index('Invoke-BaselineCase -Name "measure-phase"') < lifecycle.index(
        'Invoke-BaselineCase -Name "measure-delay"'
    )
    assert lifecycle.index('Invoke-BaselineCase -Name "measure-delay"') < lifecycle.index(
        'Stage "pair-measurement-stop"'
    )
    assert lifecycle.index('Stage "pair-measurement-stop"') < lifecycle.index(
        "Restore-PairMeasurementChannel"
    )
    assert 'Command "run"' in lifecycle
    assert 'ExpectedCommands @(":RUN")' in lifecycle
    assert 'Command "stop-acquisition"' in lifecycle
    assert 'ExpectedCommands @(":STOP")' in lifecycle
    assert 'Stage "measure-ch2-readiness"' in script
    assert "CH2 pair-measurement precondition is invalid" in lifecycle
    readiness_start = script.index("function Invoke-PairMeasurementReadiness")
    readiness_end = script.index("function Get-PairMeasurementChannelSnapshot", readiness_start)
    readiness = script[readiness_start:readiness_end]
    assert '"--source-channel", "2"' in readiness
    assert '"--item", "vpp"' in readiness
    assert ':MEASure:VPP? CHANnel2' in readiness
    assert "while ($elapsedMilliseconds -le $TimeoutMilliseconds)" in readiness
    assert "if ([bool]$validProperty.Value)" in readiness
    assert "Start-Sleep -Milliseconds $sleepMilliseconds" in readiness
    assert "CH2 pair-measurement precondition did not become measurement-ready" in readiness
    assert "if ($systemErrorCode -ne 0)" in readiness
    assert "Invoke-StrictPairMeasurement" not in readiness
    assert "function Assert-StrictMeasurementInvocation" in script
    assert "invalid measurement sentinels are not accepted" in script
    assert "systemErrorCode -ne 0" in script
    assert "function Restore-PairMeasurementChannel" in script
    assert "pair-ch2-restore-$($step.Kind)-query" in script
    prepare_start = script.index("function Prepare-PairMeasurementChannel")
    prepare_end = script.index("function Restore-PairMeasurementChannel", prepare_start)
    prepare = script[prepare_start:prepare_end]
    assert '"--channel", "2", "--on"' in prepare
    assert '"--channel", "2", "--coupling", "dc"' in prepare
    assert "$Ch1Snapshot.ChannelScale" in prepare
    assert "$Ch1Snapshot.ChannelOffset" in prepare
    assert "$Ch1Snapshot.ChannelProbeRatio" in prepare
    restore_start = script.index("function Restore-PairMeasurementChannel")
    restore_end = script.index("function Assert-ScpiSent", restore_start)
    restore = script[restore_start:restore_end]
    for previous, following in (
        ('Kind = "offset"', 'Kind = "scale"'),
        ('Kind = "scale"', 'Kind = "probe"'),
        ('Kind = "probe"', 'Kind = "coupling"'),
        ('Kind = "coupling"', 'Kind = "display"'),
    ):
        assert restore.index(previous) < restore.index(following)
    assert '"--query"' in restore
    assert "pairMeasurementSnapshot = $null" in lifecycle
    assert "finally" in lifecycle
    assert "Start-Sleep" not in prepare
    assert "measure-phase-ch2-display-before" not in script
    assert "measure-delay-ch2-display-before" not in script

    for block in (phase, delay):
        assert ".result.valid" in block
        assert "Assert-FiniteNumber" in block
        assert "Assert-SingleMeasurementInvocation" not in block
        assert "Invoke-StrictPairMeasurement" in block


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_pair_readiness_polling_retries_sentinels_and_fails_fast_on_system_error(
    tmp_path: Path,
) -> None:
    harness_path = tmp_path / "pair-readiness-harness.ps1"
    harness_path.write_text(
        """\
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Assert-FiniteNumber", "Invoke-PairMeasurementReadiness")) {
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

$Resource = "SIMULATED"
$script:LiveConnectionArguments = @("--live", "--resource", $Resource)
$script:Scenario = ""
$script:ReadinessCalls = 0
$script:SleepCalls = 0

function Assert-ScpiSent {
    param([object] $Payload, [string] $Label, [string[]] $ExpectedCommands)
}

function Start-Sleep {
    param([int] $Milliseconds = 0)
    $script:SleepCalls += 1
}

function New-ReadinessInvocation {
    param(
        [bool] $Valid,
        [object] $Value,
        [int] $SystemErrorCode,
        [int] $ExitCode,
        [bool] $Ok,
        [string] $Reason
    )
    return [pscustomobject]@{
        ExitCode = $ExitCode
        Payload = [pscustomobject]@{
            ok = $Ok
            result = [pscustomobject]@{ valid = $Valid; value = $Value; reason = $Reason }
            system_error = [pscustomobject]@{
                code = $SystemErrorCode
                message = if ($SystemErrorCode -eq 0) { "No error" } else { "Parameter error" }
            }
            scpi = [pscustomobject]@{
                sent = @("*IDN?", ":MEASure:VPP? CHANnel2", ":SYSTem:ERRor?")
            }
        }
    }
}

function Invoke-CliRaw {
    param([string] $Stage, [string[]] $Arguments)
    $script:ReadinessCalls += 1
    if ($script:Scenario -eq "retry" -and $script:ReadinessCalls -eq 1) {
        return New-ReadinessInvocation `
            -Valid:$false -Value $null -SystemErrorCode 0 -ExitCode 1 -Ok:$false `
            -Reason "invalid measurement sentinel"
    }
    if ($script:Scenario -eq "timeout") {
        return New-ReadinessInvocation `
            -Valid:$false -Value $null -SystemErrorCode 0 -ExitCode 1 -Ok:$false `
            -Reason "invalid measurement sentinel"
    }
    if ($script:Scenario -eq "system-error") {
        return New-ReadinessInvocation `
            -Valid:$false -Value $null -SystemErrorCode -222 -ExitCode 1 -Ok:$false `
            -Reason "invalid measurement sentinel"
    }
    return New-ReadinessInvocation `
        -Valid:$true -Value 2.74 -SystemErrorCode 0 -ExitCode 0 -Ok:$true -Reason ""
}

$script:Scenario = "retry"
$script:ReadinessCalls = 0
$script:SleepCalls = 0
$retry = Invoke-PairMeasurementReadiness -TimeoutMilliseconds 300 -PollIntervalMilliseconds 100
$retryCalls = $script:ReadinessCalls
$retrySleeps = $script:SleepCalls

$script:Scenario = "timeout"
$script:ReadinessCalls = 0
$script:SleepCalls = 0
$timeoutMessage = ""
try { [void](Invoke-PairMeasurementReadiness -TimeoutMilliseconds 250 -PollIntervalMilliseconds 100) }
catch { $timeoutMessage = $_.Exception.Message }
$timeoutCalls = $script:ReadinessCalls
$timeoutSleeps = $script:SleepCalls

$script:Scenario = "system-error"
$script:ReadinessCalls = 0
$script:SleepCalls = 0
$systemErrorMessage = ""
try { [void](Invoke-PairMeasurementReadiness -TimeoutMilliseconds 2500 -PollIntervalMilliseconds 100) }
catch { $systemErrorMessage = $_.Exception.Message }
$systemErrorCalls = $script:ReadinessCalls
$systemErrorSleeps = $script:SleepCalls

[ordered]@{
    retry_value = $retry.result.value
    retry_calls = $retryCalls
    retry_sleeps = $retrySleeps
    timeout_message = $timeoutMessage
    timeout_calls = $timeoutCalls
    timeout_sleeps = $timeoutSleeps
    system_error_message = $systemErrorMessage
    system_error_calls = $systemErrorCalls
    system_error_sleeps = $systemErrorSleeps
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
            str(SCRIPT_PATH),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["retry_value"] == 2.74
    assert result["retry_calls"] == 2
    assert result["retry_sleeps"] == 1
    assert "did not become measurement-ready" in result["timeout_message"]
    assert result["timeout_calls"] > 2
    assert result["timeout_sleeps"] > 0
    assert "system error -222" in result["system_error_message"]
    assert result["system_error_calls"] == 1
    assert result["system_error_sleeps"] == 0


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_single_measurement_invocation_acceptance_semantics(tmp_path: Path) -> None:
    harness_path = tmp_path / "measurement-acceptance-harness.ps1"
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

foreach ($functionName in @("Assert-FiniteNumber", "Assert-SingleMeasurementInvocation")) {
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

function New-MeasurementInvocation {
    param(
        [int] $ExitCode,
        [bool] $Ok,
        [bool] $Valid,
        [object] $Value,
        [string] $Reason,
        [int] $SystemErrorCode,
        [string[]] $Sent
    )

    $systemMessage = if ($SystemErrorCode -eq 0) { "No error" } else { "Data out of range" }
    return [pscustomobject]@{
        ExitCode = $ExitCode
        Command = "python -m scopes_tool_cli.cli measure ..."
        Stderr = ""
        Payload = [pscustomobject]@{
            ok = $Ok
            result = [pscustomobject]@{
                valid = $Valid
                value = $Value
                reason = $Reason
            }
            system_error = [pscustomobject]@{
                code = $SystemErrorCode
                message = $systemMessage
                raw = [string]$SystemErrorCode
            }
            scpi = [pscustomobject]@{
                sent = $Sent
            }
        }
    }
}

$valid = New-MeasurementInvocation `
    -ExitCode 0 -Ok $true -Valid $true -Value 1.25 -Reason "" -SystemErrorCode 0 `
    -Sent @("*IDN?", ":MEASure:VPP? CHANnel1", ":SYSTem:ERRor?")
[void](Assert-SingleMeasurementInvocation -Invocation $valid -Item "vpp")

$sentinel = New-MeasurementInvocation `
    -ExitCode 1 -Ok $false -Valid $false -Value $null `
    -Reason "invalid measurement sentinel" -SystemErrorCode 0 `
    -Sent @("*IDN?", ":MEASure:TVALue? 0.5,+1,CHANnel1", ":SYSTem:ERRor?")
[void](Assert-SingleMeasurementInvocation -Invocation $sentinel -Item "time_at_value")

$instrumentErrorRejected = $false
try {
    $instrumentError = New-MeasurementInvocation `
        -ExitCode 1 -Ok $false -Valid $false -Value $null `
        -Reason "invalid measurement sentinel" -SystemErrorCode -222 `
        -Sent @("*IDN?", ":MEASure:VPP? CHANnel1", ":SYSTem:ERRor?")
    [void](Assert-SingleMeasurementInvocation -Invocation $instrumentError -Item "vpp")
} catch {
    $instrumentErrorRejected = $_.Exception.Message -like "*system error -222*"
}

$unexpectedFailureRejected = $false
try {
    $unexpectedFailure = New-MeasurementInvocation `
        -ExitCode 1 -Ok $false -Valid $false -Value $null `
        -Reason "unexpected failure" -SystemErrorCode 0 `
        -Sent @("*IDN?", ":MEASure:VPP? CHANnel1", ":SYSTem:ERRor?")
    [void](Assert-SingleMeasurementInvocation -Invocation $unexpectedFailure -Item "vpp")
} catch {
    $unexpectedFailureRejected = $true
}

[ordered]@{
    valid_accepted = $true
    sentinel_accepted = $true
    instrument_error_rejected = $instrumentErrorRejected
    unexpected_failure_rejected = $unexpectedFailureRejected
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
            str(SCRIPT_PATH),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "valid_accepted": True,
        "sentinel_accepted": True,
        "instrument_error_rejected": True,
        "unexpected_failure_rejected": True,
    }
