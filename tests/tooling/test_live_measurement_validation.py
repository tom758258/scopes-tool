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


def test_single_measurement_breadth_uses_raw_acceptance_path() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    block = _case_block(script, "measurements", "measure-phase")

    assert '"--level", "0.5", "--slope", "positive", "--occurrence", "1"' in block
    assert "Invoke-CliRaw" in block
    assert "Assert-SingleMeasurementInvocation" in block
    assert 'Invoke-LiveCli -Stage "measure-${item}"' not in block


def test_pair_measurements_remain_strict() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    phase = _case_block(script, "measure-phase", "measure-delay")
    delay = _case_block(script, "measure-delay", "measure-stats")
    for block in (phase, delay):
        assert "Invoke-LiveCli" in block
        assert ".result.valid" in block
        assert "Assert-FiniteNumber" in block
        assert "Assert-SingleMeasurementInvocation" not in block


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
