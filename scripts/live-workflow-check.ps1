[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $Resource,

    [string] $Python = ".\.venv\Scripts\python.exe",

    [string] $OutputRoot = ".tmp_tests\live_workflow_check"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:CliInvocationIndex = 0
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:OperationConditionRunMask = 8

function Get-PayloadErrorText {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload
    )

    $errorProperty = $Payload.PSObject.Properties["error"]
    if ($null -eq $errorProperty -or $null -eq $errorProperty.Value) {
        return ""
    }
    return ($errorProperty.Value | ConvertTo-Json -Depth 8 -Compress)
}

function Get-PayloadSystemError {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload
    )

    $systemErrorProperty = $Payload.PSObject.Properties["system_error"]
    if ($null -eq $systemErrorProperty -or $null -eq $systemErrorProperty.Value) {
        return $null
    }
    return $systemErrorProperty.Value
}

function Add-CaseResult {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [ValidateSet("PASS", "FAIL", "N/A")]
        [string] $Status,

        [string] $Detail = ""
    )

    $script:CaseResults[$Name] = [pscustomobject]@{
        Status = $Status
        Detail = $Detail
    }
    Write-Host ("{0,-5} {1}" -f $Status, $Name)
    if (-not [string]::IsNullOrWhiteSpace($Detail)) {
        Write-Host "      ${Detail}"
    }
}

function Add-Diagnostic {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [string] $Message
    )

    if (-not $script:Diagnostics.Contains($Name)) {
        $script:Diagnostics[$Name] = New-Object System.Collections.Generic.List[string]
    }
    $script:Diagnostics[$Name].Add($Message)
}

function Write-Summary {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("PASS", "FAIL", "N/A")]
        [string] $Result
    )

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# Scopes Tool Workflow Live Validation Summary")
    $lines.Add("")
    $lines.Add("Result: ${Result}")
    $lines.Add("")
    $lines.Add("| Case | Status | Detail |")
    $lines.Add("|---|---|---|")
    foreach ($entry in $script:CaseResults.GetEnumerator()) {
        $detail = [System.Convert]::ToString($entry.Value.Detail)
        $detail = $detail.Replace("|", "\|").Replace("`r`n", "<br>")
        $detail = $detail.Replace("`n", "<br>").Replace("`r", "<br>")
        $lines.Add("| $($entry.Key) | $($entry.Value.Status) | ${detail} |")
    }

    if ($script:Diagnostics.Count -gt 0) {
        $lines.Add("")
        $lines.Add("## Diagnostics")
        foreach ($entry in $script:Diagnostics.GetEnumerator()) {
            $lines.Add("")
            $lines.Add("### $($entry.Key)")
            foreach ($message in $entry.Value) {
                $safeMessage = $message.Replace("`r`n", "<br>")
                $safeMessage = $safeMessage.Replace("`n", "<br>").Replace("`r", "<br>")
                $lines.Add("- ${safeMessage}")
            }
        }
    }

    $summaryPath = Join-Path $script:RunRoot "summary.md"
    $content = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
    [System.IO.File]::WriteAllText(
        $summaryPath,
        $content,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Summary: ${summaryPath}"
}

function Invoke-CliRaw {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $script:CliInvocationIndex += 1
    $safeStage = $Stage -replace "[^A-Za-z0-9_-]", "-"
    $stderrPath = Join-Path $script:RunRoot (
        "cli-{0:D3}-{1}.stderr.txt" -f $script:CliInvocationIndex, $safeStage
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $stdoutLines = @(& $Python -m scopes_tool_cli.cli @Arguments 2> $stderrPath)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $stderrText = ""
    if (Test-Path -LiteralPath $stderrPath) {
        $stderrText = [System.Convert]::ToString(
            (Get-Content -LiteralPath $stderrPath -Raw)
        ).Trim()
        if ([string]::IsNullOrWhiteSpace($stderrText)) {
            Remove-Item -LiteralPath $stderrPath -Force
        }
    }

    $stdoutText = ($stdoutLines -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($stdoutText)) {
        throw "${Stage}: CLI returned no JSON (exit ${exitCode}). ${stderrText}"
    }

    try {
        $payload = $stdoutText | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "${Stage}: CLI returned invalid JSON (exit ${exitCode}). ${stderrText}"
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Payload = $payload
        Stderr = $stderrText
        Command = "$Python -m scopes_tool_cli.cli $($Arguments -join ' ')"
    }
}

function Get-InvocationFailureDetail {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Invocation,

        [Parameter(Mandatory = $true)]
        [string] $Stage
    )

    $detail = "${Stage}: $($Invocation.Command) exited $($Invocation.ExitCode)"
    $payloadError = Get-PayloadErrorText -Payload $Invocation.Payload
    if (-not [string]::IsNullOrWhiteSpace($payloadError)) {
        $detail += "; error=${payloadError}"
    }

    $systemError = Get-PayloadSystemError -Payload $Invocation.Payload
    if ($null -ne $systemError) {
        $codeProperty = $systemError.PSObject.Properties["code"]
        $messageProperty = $systemError.PSObject.Properties["message"]
        if ($null -ne $codeProperty -and [int]$codeProperty.Value -ne 0) {
            $systemErrorDetail = "system error $([int]$codeProperty.Value)"
            if ($null -ne $messageProperty -and
                -not [string]::IsNullOrWhiteSpace([string]$messageProperty.Value)) {
                $systemErrorDetail += ": $($messageProperty.Value)"
            }
            $detail += "; ${systemErrorDetail}"
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($Invocation.Stderr)) {
        $detail += "; stderr=$($Invocation.Stderr)"
    }
    return $detail
}

function Invoke-Cli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $invocation = Invoke-CliRaw -Stage $Stage -Arguments $Arguments
    $okProperty = $invocation.Payload.PSObject.Properties["ok"]
    $ok = $null -ne $okProperty -and $okProperty.Value -eq $true
    if ($invocation.ExitCode -ne 0 -or -not $ok) {
        throw (Get-InvocationFailureDetail -Invocation $invocation -Stage $Stage)
    }
    return $invocation.Payload
}

function Invoke-ModeCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $Command,

        [Parameter(Mandatory = $true)]
        [string[]] $ModeArguments,

        [string[]] $Arguments = @()
    )

    $allArguments = @($Command) + $ModeArguments + @("--json") + $Arguments
    return Invoke-Cli -Stage $Stage -Arguments $allArguments
}

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $Command,

        [string[]] $Arguments = @()
    )

    return Invoke-ModeCli -Stage $Stage -Command $Command -ModeArguments @(
        "--live", "--resource", $Resource
    ) -Arguments $Arguments
}

function Get-RequiredResultValue {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload,

        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [string] $Stage
    )

    $resultProperty = $Payload.PSObject.Properties["result"]
    if ($null -eq $resultProperty -or $null -eq $resultProperty.Value) {
        throw "${Stage}: JSON did not contain result data."
    }
    $valueProperty = $resultProperty.Value.PSObject.Properties[$Name]
    if ($null -eq $valueProperty) {
        throw "${Stage}: result did not contain ${Name}."
    }
    return $valueProperty.Value
}

function Get-ErrorDrain {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage
    )

    $arguments = @(
        "check-error", "--live", "--resource", $Resource, "--json",
        "--all", "--max-reads", "30"
    )
    $invocation = Invoke-CliRaw -Stage $Stage -Arguments $arguments
    $resultProperty = $invocation.Payload.PSObject.Properties["result"]
    if ($null -eq $resultProperty -or $null -eq $resultProperty.Value) {
        throw "${Stage}: check-error JSON did not contain result data."
    }
    $entriesProperty = $resultProperty.Value.PSObject.Properties["entries"]
    $entries = @(
        if ($null -ne $entriesProperty) {
            $entriesProperty.Value
        }
    )
    $terminated = $entries.Count -gt 0 -and [int]$entries[-1].code -eq 0
    $errors = @($entries | Where-Object { [int]$_.code -ne 0 })

    return [pscustomobject]@{
        Invocation = $invocation
        Entries = $entries
        Errors = $errors
        Terminated = $terminated
    }
}

function Write-DrainErrors {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]] $Errors,

        [string] $CaseName = ""
    )

    foreach ($entry in $Errors) {
        $message = "system error $($entry.code): $($entry.message)"
        Write-Host "      ${message}"
        if (-not [string]::IsNullOrWhiteSpace($CaseName)) {
            Add-Diagnostic -Name $CaseName -Message $message
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

    try {
        $drain = Get-ErrorDrain -Stage $Stage
        Write-DrainErrors -Errors $drain.Errors -CaseName $CaseName
        if (-not $drain.Terminated) {
            $message = "error queue did not reach code 0 within 30 reads"
            Write-Host "      ${message}"
            Add-Diagnostic -Name $CaseName -Message $message
        }
    } catch {
        $message = "diagnostic error drain failed: $($_.Exception.Message)"
        Write-Host "      ${message}"
        Add-Diagnostic -Name $CaseName -Message $message
    }
}

function Assert-ResultEquals {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload,

        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [object] $Expected,

        [Parameter(Mandatory = $true)]
        [string] $Stage
    )

    $actual = Get-RequiredResultValue -Payload $Payload -Name $Name -Stage $Stage
    if ([string]$actual -ne [string]$Expected) {
        throw "${Stage}: ${Name} is ${actual}, expected ${Expected}."
    }
}

function Assert-ExpectedFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string] $OutputDir,

        [Parameter(Mandatory = $true)]
        [string[]] $Names,

        [Parameter(Mandatory = $true)]
        [string] $Stage
    )

    foreach ($name in $Names) {
        $path = Join-Path $OutputDir $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "${Stage}: expected artifact was not written: ${path}"
        }
    }
}

function Invoke-WorkflowCase {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [scriptblock] $Action
    )

    try {
        & $Action
        Add-CaseResult -Name $Name -Status "PASS"
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name $Name -Status "FAIL" -Detail $_.Exception.Message
        Drain-AfterFailure -Stage "${Name}-error-drain" -CaseName $Name
    }
}

function Invoke-HardwareFreePreflight {
    $model = "keysight-dsox4024a"
    $simulate = @("--simulate", "--model", $model)
    $dryRun = @("--dry-run", "--model", $model)
    $preflightRoot = Join-Path $script:RunRoot "preflight"
    New-Item -ItemType Directory -Path $preflightRoot -Force | Out-Null

    Invoke-ModeCli -Stage "preflight-measure-sweep" -Command "measure-sweep" `
        -ModeArguments $simulate -Arguments @(
            "--channel", "1", "--items", "vpp,frequency"
        ) | Out-Null

    $measureLogDir = Join-Path $preflightRoot "measure-log"
    $measureLog = Invoke-ModeCli -Stage "preflight-measure-log" `
        -Command "measure-log" -ModeArguments $simulate -Arguments @(
            "--channel", "1", "--items", "vpp", "--count", "1",
            "--interval-seconds", "0", "--output-dir", $measureLogDir
        )
    Assert-ResultEquals -Payload $measureLog -Name "status" -Expected "completed" `
        -Stage "Preflight measure-log"
    Assert-ExpectedFiles -OutputDir $measureLogDir `
        -Names @("measurements.csv", "manifest.json", "scpi.log") `
        -Stage "Preflight measure-log"

    $measureUntilDir = Join-Path $preflightRoot "measure-until"
    $measureUntil = Invoke-ModeCli -Stage "preflight-measure-until" `
        -Command "measure-until" -ModeArguments $simulate -Arguments @(
            "--channel", "1", "--item", "vpp", "--operator", "gt",
            "--threshold", "0", "--timeout-seconds", "1",
            "--interval-seconds", "0", "--output-dir", $measureUntilDir
        )
    Assert-ResultEquals -Payload $measureUntil -Name "termination_reason" `
        -Expected "condition_met" -Stage "Preflight measure-until"

    $captureBatchDir = Join-Path $preflightRoot "capture-batch"
    $captureBatch = Invoke-ModeCli -Stage "preflight-capture-batch" `
        -Command "capture-batch" -ModeArguments $simulate -Arguments @(
            "--channel", "1", "--points", "1000", "--format", "byte",
            "--count", "1", "--interval-seconds", "0",
            "--output-dir", $captureBatchDir
        )
    Assert-ResultEquals -Payload $captureBatch -Name "status" -Expected "completed" `
        -Stage "Preflight capture-batch"

    $triggeredMeasureDir = Join-Path $preflightRoot "triggered-measure-loop"
    $triggeredMeasure = Invoke-ModeCli -Stage "preflight-triggered-measure-loop" `
        -Command "triggered-measure-loop" -ModeArguments $simulate -Arguments @(
            "--channel", "1", "--items", "vpp", "--count", "1",
            "--trigger-timeout-seconds", "1", "--interval-seconds", "0",
            "--output-dir", $triggeredMeasureDir
        )
    Assert-ResultEquals -Payload $triggeredMeasure -Name "status" -Expected "completed" `
        -Stage "Preflight triggered-measure-loop"

    $triggeredCaptureDir = Join-Path $preflightRoot "triggered-capture-series"
    $triggeredCapture = Invoke-ModeCli -Stage "preflight-triggered-capture-series" `
        -Command "triggered-capture-series" -ModeArguments $simulate -Arguments @(
            "--channel", "1", "--points", "1000", "--format", "byte",
            "--count", "1", "--trigger-timeout-seconds", "1",
            "--interval-seconds", "0", "--output-dir", $triggeredCaptureDir
        )
    Assert-ResultEquals -Payload $triggeredCapture -Name "status" -Expected "completed" `
        -Stage "Preflight triggered-capture-series"

    Invoke-ModeCli -Stage "preflight-operation-status" `
        -Command "system-operation-status" -ModeArguments $simulate `
        -Arguments @("--query") | Out-Null
    foreach ($command in @("run", "stop-acquisition")) {
        Invoke-ModeCli -Stage "preflight-${command}" -Command $command `
            -ModeArguments $dryRun | Out-Null
    }
}

function Restore-AcquisitionState {
    param(
        [Parameter(Mandatory = $true)]
        [bool] $WasRunning
    )

    $restoreCommand = if ($WasRunning) { "run" } else { "stop-acquisition" }
    Invoke-LiveCli -Stage "cleanup-acquisition-${restoreCommand}" `
        -Command $restoreCommand | Out-Null

    $operationStatus = Invoke-LiveCli -Stage "cleanup-acquisition-status" `
        -Command "system-operation-status" -Arguments @("--query")
    $operationValue = [int](Get-RequiredResultValue -Payload $operationStatus `
        -Name "value" -Stage "Acquisition cleanup")
    $isRunning = ($operationValue -band $script:OperationConditionRunMask) -ne 0
    if ($isRunning -ne $WasRunning) {
        throw "Acquisition cleanup readback does not match the original run state."
    }
}

if ([string]::IsNullOrWhiteSpace($Resource)) {
    throw "Workflow live validation requires an explicit non-empty -Resource."
}
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    throw "Python executable not found: ${Python}"
}

$timestamp = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")
$script:RunRoot = Join-Path $OutputRoot $timestamp
New-Item -ItemType Directory -Path $script:RunRoot -Force | Out-Null

Write-Host "Scopes Tool Workflow live validation"
Write-Host "Artifacts: $($script:RunRoot)"
Write-Host ""

try {
    Invoke-HardwareFreePreflight
    Add-CaseResult -Name "preflight" -Status "PASS"
} catch {
    Add-CaseResult -Name "preflight" -Status "FAIL" -Detail $_.Exception.Message
    Write-Host ""
    Write-Host "FAIL  Workflow live validation"
    Write-Host "No live hardware was accessed."
    Write-Host "Artifacts: $($script:RunRoot)"
    Write-Summary -Result "FAIL"
    exit 1
}

$identity = $null
try {
    $identity = Invoke-LiveCli -Stage "identity" -Command "identify"
    if ([string]::IsNullOrWhiteSpace([string]$identity.idn.raw) -or
        [string]::IsNullOrWhiteSpace([string]$identity.idn.model)) {
        throw "Live identify did not return detected IDN/model information."
    }
    Add-CaseResult -Name "identity" -Status "PASS"
} catch {
    Add-CaseResult -Name "identity" -Status "FAIL" -Detail $_.Exception.Message
    Write-Host ""
    Write-Host "FAIL  Workflow live validation"
    Write-Host "Artifacts: $($script:RunRoot)"
    Write-Summary -Result "FAIL"
    exit 1
}

try {
    $initialDrain = Get-ErrorDrain -Stage "stale-error-drain"
    if ($initialDrain.Errors.Count -gt 0) {
        Write-Host "      drained $($initialDrain.Errors.Count) stale system error(s)"
        Write-DrainErrors -Errors $initialDrain.Errors -CaseName "stale-error-drain"
    }
    if (-not $initialDrain.Terminated) {
        throw "Initial error queue did not reach code 0 within 30 reads."
    }
    Add-CaseResult -Name "stale-error-drain" -Status "PASS"
} catch {
    Add-CaseResult -Name "stale-error-drain" -Status "FAIL" `
        -Detail $_.Exception.Message
    Write-Host ""
    Write-Host "FAIL  Workflow live validation"
    Write-Host "No workflow cases were run."
    Write-Host "Artifacts: $($script:RunRoot)"
    Write-Summary -Result "FAIL"
    exit 1
}

Write-Host ""
Write-Host "Workflow live validation"
Write-Host ""
Write-Host "Detected instrument: $($identity.idn.raw)"
Write-Host "Connection/resource: ${Resource}"
Write-Host ""
Write-Host "Required setup:"
Write-Host "  - Disconnect unknown or sensitive DUT connections from the oscilloscope."
Write-Host "  - Connect the CH1 probe to the oscilloscope Probe Demo / Probe Comp output."
Write-Host "  - Confirm a stable waveform is present on CH1."
Write-Host "  - Confirm the existing trigger setup reliably triggers from that CH1 waveform;"
Write-Host "    an Edge trigger on CH1 with a level inside the waveform is recommended."
Write-Host "  - The script does not reset, preset, autoscale, or reconfigure the trigger mode."
Write-Host "  - Workflow artifacts are written under the run directory shown above."
Write-Host "  - Triggered workflow cases use Single acquisition and the original Running/Stopped"
Write-Host "    acquisition state is restored at cleanup."
Write-Host ""
Write-Host "Press Enter when ready."
Write-Host "Ctrl+C to cancel."
[void](Read-Host)

$wasRunning = $false
$snapshotTaken = $false
try {
    $operationStatus = Invoke-LiveCli -Stage "snapshot-operation-status" `
        -Command "system-operation-status" -Arguments @("--query")
    $operationValue = [int](Get-RequiredResultValue -Payload $operationStatus `
        -Name "value" -Stage "Acquisition state snapshot")
    $wasRunning = ($operationValue -band $script:OperationConditionRunMask) -ne 0
    $snapshotTaken = $true
    $snapshotDetail = if ($wasRunning) { "Acquisition was running." } else { "Acquisition was stopped." }
    Add-CaseResult -Name "state-snapshot" -Status "PASS" -Detail $snapshotDetail
} catch {
    $script:FunctionalFailed = $true
    Add-CaseResult -Name "state-snapshot" -Status "FAIL" -Detail $_.Exception.Message
    Drain-AfterFailure -Stage "state-snapshot-error-drain" -CaseName "state-snapshot"
}

$liveArtifactRoot = Join-Path $script:RunRoot "workflows"
New-Item -ItemType Directory -Path $liveArtifactRoot -Force | Out-Null

if (-not $script:FunctionalFailed) {
    Invoke-WorkflowCase -Name "measure-sweep" -Action {
        $payload = Invoke-LiveCli -Stage "measure-sweep" -Command "measure-sweep" `
            -Arguments @("--channel", "1", "--items", "vpp,frequency,period,vrms")
        $summary = Get-RequiredResultValue -Payload $payload -Name "summary" `
            -Stage "measure-sweep"
        if ([int]$summary.error_count -ne 0) {
            throw "measure-sweep reported $($summary.error_count) error result(s)."
        }
        if ([int]$summary.valid_count -lt 1) {
            throw "measure-sweep did not return any valid measurement."
        }
    }
}

if (-not $script:FunctionalFailed) {
    Invoke-WorkflowCase -Name "measure-log" -Action {
        $outputDir = Join-Path $liveArtifactRoot "measure-log"
        $payload = Invoke-LiveCli -Stage "measure-log" -Command "measure-log" `
            -Arguments @(
                "--channel", "1", "--items", "vpp,frequency",
                "--count", "2", "--interval-seconds", "0",
                "--output-dir", $outputDir
            )
        Assert-ResultEquals -Payload $payload -Name "status" -Expected "completed" `
            -Stage "measure-log"
        Assert-ResultEquals -Payload $payload -Name "completed_rows" -Expected 2 `
            -Stage "measure-log"
        Assert-ExpectedFiles -OutputDir $outputDir `
            -Names @("measurements.csv", "manifest.json", "scpi.log") `
            -Stage "measure-log"
    }
}

if (-not $script:FunctionalFailed) {
    Invoke-WorkflowCase -Name "measure-until" -Action {
        $outputDir = Join-Path $liveArtifactRoot "measure-until"
        $payload = Invoke-LiveCli -Stage "measure-until" -Command "measure-until" `
            -Arguments @(
                "--channel", "1", "--item", "vpp", "--operator", "gt",
                "--threshold", "0", "--timeout-seconds", "5",
                "--interval-seconds", "0", "--output-dir", $outputDir
            )
        Assert-ResultEquals -Payload $payload -Name "status" -Expected "completed" `
            -Stage "measure-until"
        Assert-ResultEquals -Payload $payload -Name "termination_reason" `
            -Expected "condition_met" -Stage "measure-until"
        Assert-ExpectedFiles -OutputDir $outputDir `
            -Names @("measurements.csv", "manifest.json", "scpi.log") `
            -Stage "measure-until"
    }
}

if (-not $script:FunctionalFailed) {
    Invoke-WorkflowCase -Name "measure-until-timeout" -Action {
        $outputDir = Join-Path $liveArtifactRoot "measure-until-timeout"
        $arguments = @(
            "measure-until", "--live", "--resource", $Resource, "--json",
            "--channel", "1", "--item", "vpp", "--operator", "lt",
            "--threshold", "-1", "--timeout-seconds", "1",
            "--interval-seconds", "0.1", "--output-dir", $outputDir
        )
        $invocation = Invoke-CliRaw -Stage "measure-until-timeout" -Arguments $arguments
        if ($invocation.ExitCode -eq 0) {
            throw "measure-until timeout case unexpectedly exited 0."
        }
        $okProperty = $invocation.Payload.PSObject.Properties["ok"]
        if ($null -eq $okProperty -or $okProperty.Value -ne $false) {
            throw "measure-until timeout case did not report ok=false."
        }
        Assert-ResultEquals -Payload $invocation.Payload -Name "status" -Expected "error" `
            -Stage "measure-until timeout"
        Assert-ResultEquals -Payload $invocation.Payload -Name "termination_reason" `
            -Expected "condition_timeout" -Stage "measure-until timeout"
        $errorValue = Get-RequiredResultValue -Payload $invocation.Payload -Name "error" `
            -Stage "measure-until timeout"
        if ([string]$errorValue.type -ne "condition_timeout") {
            throw "measure-until timeout case returned unexpected error type: $($errorValue.type)"
        }
        Assert-ExpectedFiles -OutputDir $outputDir `
            -Names @("measurements.csv", "manifest.json", "scpi.log") `
            -Stage "measure-until timeout"
    }
}

if (-not $script:FunctionalFailed) {
    Invoke-WorkflowCase -Name "capture-batch" -Action {
        $outputDir = Join-Path $liveArtifactRoot "capture-batch"
        $payload = Invoke-LiveCli -Stage "capture-batch" -Command "capture-batch" `
            -Arguments @(
                "--channel", "1", "--points", "1000", "--format", "byte",
                "--count", "2", "--interval-seconds", "0",
                "--output-dir", $outputDir
            )
        Assert-ResultEquals -Payload $payload -Name "status" -Expected "completed" `
            -Stage "capture-batch"
        $captures = @(Get-RequiredResultValue -Payload $payload -Name "captures" `
            -Stage "capture-batch")
        if ($captures.Count -ne 2) {
            throw "capture-batch returned $($captures.Count) capture(s), expected 2."
        }
        Assert-ExpectedFiles -OutputDir $outputDir `
            -Names @(
                "manifest.json", "scpi.log", "waveform_0001.csv",
                "waveform_0001_meta.json", "waveform_0002.csv",
                "waveform_0002_meta.json"
            ) -Stage "capture-batch"
    }
}

if (-not $script:FunctionalFailed) {
    Invoke-WorkflowCase -Name "triggered-measure-loop" -Action {
        $outputDir = Join-Path $liveArtifactRoot "triggered-measure-loop"
        $payload = Invoke-LiveCli -Stage "triggered-measure-loop" `
            -Command "triggered-measure-loop" -Arguments @(
                "--channel", "1", "--items", "vpp,frequency",
                "--count", "2", "--trigger-timeout-seconds", "5",
                "--interval-seconds", "0", "--output-dir", $outputDir
            )
        Assert-ResultEquals -Payload $payload -Name "status" -Expected "completed" `
            -Stage "triggered-measure-loop"
        Assert-ResultEquals -Payload $payload -Name "completed_count" -Expected 2 `
            -Stage "triggered-measure-loop"
        Assert-ExpectedFiles -OutputDir $outputDir `
            -Names @("measurements.csv", "manifest.json", "scpi.log") `
            -Stage "triggered-measure-loop"
    }
}

if (-not $script:FunctionalFailed) {
    Invoke-WorkflowCase -Name "triggered-capture-series" -Action {
        $outputDir = Join-Path $liveArtifactRoot "triggered-capture-series"
        $payload = Invoke-LiveCli -Stage "triggered-capture-series" `
            -Command "triggered-capture-series" -Arguments @(
                "--channel", "1", "--points", "1000", "--format", "byte",
                "--count", "2", "--trigger-timeout-seconds", "5",
                "--interval-seconds", "0", "--output-dir", $outputDir
            )
        Assert-ResultEquals -Payload $payload -Name "status" -Expected "completed" `
            -Stage "triggered-capture-series"
        Assert-ResultEquals -Payload $payload -Name "completed_count" -Expected 2 `
            -Stage "triggered-capture-series"
        Assert-ExpectedFiles -OutputDir $outputDir `
            -Names @(
                "manifest.json", "scpi.log", "waveform_0001.csv",
                "waveform_0001_meta.json", "waveform_0002.csv",
                "waveform_0002_meta.json"
            ) -Stage "triggered-capture-series"
    }
}

if ($snapshotTaken) {
    try {
        Restore-AcquisitionState -WasRunning $wasRunning
        Add-CaseResult -Name "cleanup" -Status "PASS"
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "cleanup" -Status "FAIL" -Detail $_.Exception.Message
        Drain-AfterFailure -Stage "cleanup-error-drain" -CaseName "cleanup"
    }
} else {
    Add-CaseResult -Name "cleanup" -Status "PASS" `
        -Detail "No workflow case ran because acquisition state snapshot failed."
}

try {
    $finalDrain = Get-ErrorDrain -Stage "final-error-queue"
    if ($finalDrain.Errors.Count -gt 0) {
        Write-DrainErrors -Errors $finalDrain.Errors -CaseName "final-error-queue"
    }
    if (-not $finalDrain.Terminated) {
        throw "Final error queue did not reach code 0 within 30 reads."
    }
    if ($finalDrain.Errors.Count -gt 0) {
        throw "Final error queue contained $($finalDrain.Errors.Count) error(s)."
    }
    Add-CaseResult -Name "final-error-queue" -Status "PASS"
} catch {
    $script:FunctionalFailed = $true
    Add-CaseResult -Name "final-error-queue" -Status "FAIL" `
        -Detail $_.Exception.Message
}

Write-Host ""
Write-Host "Summary"
foreach ($entry in $script:CaseResults.GetEnumerator()) {
    Write-Host ("{0,-5} {1}" -f $entry.Value.Status, $entry.Key)
}
Write-Host "Artifacts: $($script:RunRoot)"
Write-Host ""

if ($script:FunctionalFailed) {
    Write-Summary -Result "FAIL"
    Write-Host "FAIL  Workflow live validation"
    exit 1
}

Write-Summary -Result "PASS"
Write-Host "PASS  Workflow live validation"
exit 0
