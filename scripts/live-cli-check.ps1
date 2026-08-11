[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $Resource,

    [string] $Python = ".\.venv\Scripts\python.exe",

    [string] $OutputRoot = ".tmp_tests\live_cli_check"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:CliInvocationIndex = 0
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false

function ConvertTo-InvariantString {
    param(
        [Parameter(Mandatory = $true)]
        [double] $Value
    )

    return $Value.ToString("R", [System.Globalization.CultureInfo]::InvariantCulture)
}

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

function Add-CaseResult {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [bool] $Passed,

        [string] $Detail = ""
    )

    $status = if ($Passed) { "PASS" } else { "FAIL" }
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
    Write-Host ("{0,-5} {1}" -f $status, $Name)
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
        [ValidateSet("PASS", "FAIL", "SKIP")]
        [string] $Result
    )

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# Scopes Tool Live Validation Summary")
    $lines.Add("")
    $lines.Add("Result: ${Result}")
    $lines.Add("")
    $lines.Add("| Case | Status | Detail |")
    $lines.Add("|---|---|---|")
    foreach ($entry in $script:CaseResults.GetEnumerator()) {
        $status = if ($entry.Value.Passed) { "PASS" } else { "FAIL" }
        $detail = [System.Convert]::ToString($entry.Value.Detail)
        $detail = $detail.Replace("|", "\|").Replace("`r`n", "<br>")
        $detail = $detail.Replace("`n", "<br>").Replace("`r", "<br>")
        $lines.Add("| $($entry.Key) | ${status} | ${detail} |")
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
        $stderrText = [System.Convert]::ToString((Get-Content -LiteralPath $stderrPath -Raw)).Trim()
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
        $payloadError = Get-PayloadErrorText -Payload $invocation.Payload
        $detail = "${Stage}: $($invocation.Command) exited $($invocation.ExitCode)"
        if (-not [string]::IsNullOrWhiteSpace($payloadError)) {
            $detail += "; error=${payloadError}"
        }
        if (-not [string]::IsNullOrWhiteSpace($invocation.Stderr)) {
            $detail += "; stderr=$($invocation.Stderr)"
        }
        throw $detail
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
    $entriesProperty = $invocation.Payload.result.PSObject.Properties["entries"]
    $entries = if ($null -eq $entriesProperty) { @() } else { @($entriesProperty.Value) }
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

function Assert-FiniteNumber {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Value,

        [Parameter(Mandatory = $true)]
        [string] $Label
    )

    $number = [double]$Value
    if ([double]::IsNaN($number) -or [double]::IsInfinity($number)) {
        throw "${Label} is not finite: ${Value}"
    }
    return $number
}

function Assert-NearlyEqual {
    param(
        [Parameter(Mandatory = $true)]
        [double] $Actual,

        [Parameter(Mandatory = $true)]
        [double] $Expected,

        [Parameter(Mandatory = $true)]
        [string] $Label
    )

    $tolerance = [Math]::Max(1e-12, [Math]::Abs($Expected) * 1e-3)
    if ([Math]::Abs($Actual - $Expected) -gt $tolerance) {
        throw "${Label} readback ${Actual} does not match ${Expected}."
    }
}

function Assert-FileNonEmpty {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,

        [Parameter(Mandatory = $true)]
        [string] $Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "${Label} was not created: ${Path}"
    }
    if ((Get-Item -LiteralPath $Path).Length -le 0) {
        throw "${Label} is empty: ${Path}"
    }
}

function Assert-Capture {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload,

        [Parameter(Mandatory = $true)]
        [ValidateSet("BYTE", "WORD")]
        [string] $ExpectedFormat,

        [Parameter(Mandatory = $true)]
        [string] $CsvPath,

        [Parameter(Mandatory = $true)]
        [string] $MetadataPath
    )

    if ([string]$Payload.result.format -ne $ExpectedFormat) {
        throw "Expected ${ExpectedFormat} capture, got $($Payload.result.format)."
    }
    if ([int]$Payload.result.actual_points -le 0) {
        throw "${ExpectedFormat} capture returned no samples."
    }
    Assert-FileNonEmpty -Path $CsvPath -Label "${ExpectedFormat} waveform CSV"
    Assert-FileNonEmpty -Path $MetadataPath -Label "${ExpectedFormat} waveform metadata"

    $metadata = Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json
    if ([string]$metadata.format -ne $ExpectedFormat) {
        throw "${ExpectedFormat} metadata reports format $($metadata.format)."
    }
    if ([int]$metadata.actual_points -le 0) {
        throw "${ExpectedFormat} metadata reports no samples."
    }
}

function Invoke-BaselineCase {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [scriptblock] $Action
    )

    try {
        & $Action
        Add-CaseResult -Name $Name -Passed $true
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name $Name -Passed $false -Detail $_.Exception.Message
        Drain-AfterFailure -Stage "${Name}-error-drain" -CaseName $Name
    }
}

function Invoke-HardwareFreePreflight {
    param(
        [Parameter(Mandatory = $true)]
        [string] $PreflightRoot
    )

    $acquisitionPreflight = Join-Path $PSScriptRoot "preflight-acquisition.ps1"
    if (-not (Test-Path -LiteralPath $acquisitionPreflight -PathType Leaf)) {
        throw "Missing acquisition preflight script: ${acquisitionPreflight}"
    }

    Write-Host "Running existing acquisition preflight before live access."
    & $acquisitionPreflight -Python $Python -OutputRoot (Join-Path $PreflightRoot "acquisition")

    $model = "keysight-dsox4024a"
    $dryRun = @("--dry-run", "--model", $model)
    $simulate = @("--simulate", "--model", $model)

    Invoke-ModeCli -Stage "preflight-channel-display" -Command "channel-display" `
        -ModeArguments $dryRun -Arguments @("--channel", "1", "--on") | Out-Null
    Invoke-ModeCli -Stage "preflight-channel-coupling" -Command "channel-coupling" `
        -ModeArguments $dryRun -Arguments @("--channel", "1", "--coupling", "dc") | Out-Null
    Invoke-ModeCli -Stage "preflight-timebase-scale" -Command "timebase-scale" `
        -ModeArguments $dryRun -Arguments @("--seconds-per-division", "0.001") | Out-Null
    Invoke-ModeCli -Stage "preflight-timebase-position" -Command "timebase-position" `
        -ModeArguments $dryRun -Arguments @("--seconds", "0") | Out-Null
    Invoke-ModeCli -Stage "preflight-trigger-edge" -Command "trigger-edge" `
        -ModeArguments $dryRun -Arguments @(
            "--source-channel", "1", "--level", "0", "--slope", "positive"
        ) | Out-Null

    Invoke-ModeCli -Stage "preflight-identify" -Command "identify" `
        -ModeArguments $simulate | Out-Null
    $preflightDrain = Invoke-ModeCli -Stage "preflight-error-drain" -Command "check-error" `
        -ModeArguments $simulate -Arguments @("--all", "--max-reads", "30")
    if (@($preflightDrain.result.entries).Count -lt 1 -or
        [int]@($preflightDrain.result.entries)[-1].code -ne 0) {
        throw "Simulator error queue did not terminate with code 0."
    }
    Invoke-ModeCli -Stage "preflight-acquisition-query" -Command "acquisition" `
        -ModeArguments $simulate -Arguments @("--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-channel-display-query" -Command "channel-display" `
        -ModeArguments $simulate -Arguments @("--channel", "1", "--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-channel-coupling-query" -Command "channel-coupling" `
        -ModeArguments $simulate -Arguments @("--channel", "1", "--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-timebase-scale-query" -Command "timebase-scale" `
        -ModeArguments $simulate -Arguments @("--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-timebase-position-query" -Command "timebase-position" `
        -ModeArguments $simulate -Arguments @("--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-trigger-source-query" -Command "trigger-edge-source" `
        -ModeArguments $simulate -Arguments @("--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-trigger-slope-query" -Command "trigger-edge-slope" `
        -ModeArguments $simulate -Arguments @("--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-trigger-level-query" -Command "trigger-edge-level" `
        -ModeArguments $simulate -Arguments @("--source-channel", "1", "--query") | Out-Null

    $measurements = @{}
    foreach ($item in @("vpp", "frequency", "period")) {
        $payload = Invoke-ModeCli -Stage "preflight-measure-${item}" -Command "measure" `
            -ModeArguments $simulate -Arguments @("--channel", "1", "--item", $item)
        if (-not $payload.result.valid) {
            throw "Simulator ${item} measurement is invalid."
        }
        $measurements[$item] = Assert-FiniteNumber -Value $payload.result.value -Label $item
    }
    if ($measurements.vpp -le 0 -or $measurements.frequency -le 0 -or $measurements.period -le 0) {
        throw "Simulator baseline measurements must be positive."
    }

    $artifactRoot = Join-Path $PreflightRoot "artifacts"
    New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
    foreach ($format in @("byte", "word")) {
        $csvPath = Join-Path $artifactRoot "waveform-${format}.csv"
        $metadataPath = Join-Path $artifactRoot "waveform-${format}-meta.json"
        $payload = Invoke-ModeCli -Stage "preflight-waveform-${format}" -Command "capture" `
            -ModeArguments $simulate -Arguments @(
                "--channel", "1", "--points", "1000", "--format", $format,
                "--csv", $csvPath, "--meta", $metadataPath
            )
        Assert-Capture -Payload $payload -ExpectedFormat $format.ToUpperInvariant() `
            -CsvPath $csvPath -MetadataPath $metadataPath
    }

    $screenshotPath = Join-Path $artifactRoot "screenshot-4000x.png"
    $screenshot = Invoke-ModeCli -Stage "preflight-screenshot-4000x" -Command "screenshot" `
        -ModeArguments $simulate -Arguments @(
            "--output", $screenshotPath, "--background", "black"
        )
    if ([int]$screenshot.result.byte_count -le 0) {
        throw "Simulator screenshot returned no bytes."
    }
    Assert-FileNonEmpty -Path $screenshotPath -Label "4000X simulator screenshot"

    $legacyScreenshotPath = Join-Path $artifactRoot "screenshot-2000x.png"
    $legacyScreenshot = Invoke-ModeCli -Stage "preflight-screenshot-2000x" -Command "screenshot" `
        -ModeArguments @("--simulate", "--model", "keysight-dsox2004a") -Arguments @(
            "--output", $legacyScreenshotPath, "--background", "black"
        )
    if ([int]$legacyScreenshot.result.byte_count -le 0) {
        throw "2000X simulator screenshot returned no bytes."
    }
    Assert-FileNonEmpty -Path $legacyScreenshotPath -Label "2000X simulator screenshot"
}

function Restore-InstrumentState {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Snapshot
    )

    $restoreErrors = [System.Collections.Generic.List[string]]::new()

    $restoreSteps = @(
        [pscustomobject]@{
            Name = "CH1 Edge level"
            Command = "trigger-edge-level"
            Arguments = @(
                "--source-channel", "1", "--level-volts",
                (ConvertTo-InvariantString -Value ([double]$Snapshot.TriggerLevel))
            )
        },
        [pscustomobject]@{
            Name = "Edge slope"
            Command = "trigger-edge-slope"
            Arguments = @("--slope", [string]$Snapshot.TriggerSlope)
        },
        [pscustomobject]@{
            Name = "Edge source"
            Command = "trigger-edge-source"
            Arguments = if ($Snapshot.TriggerSource -eq "analog-channel") {
                @("--source-channel", [string]$Snapshot.TriggerSourceChannel)
            } else {
                @("--source", [string]$Snapshot.TriggerSource)
            }
        },
        [pscustomobject]@{
            Name = "timebase position"
            Command = "timebase-position"
            Arguments = @(
                "--seconds", (ConvertTo-InvariantString -Value ([double]$Snapshot.TimebasePosition))
            )
        },
        [pscustomobject]@{
            Name = "timebase scale"
            Command = "timebase-scale"
            Arguments = @(
                "--seconds-per-division",
                (ConvertTo-InvariantString -Value ([double]$Snapshot.TimebaseScale))
            )
        },
        [pscustomobject]@{
            Name = "CH1 coupling"
            Command = "channel-coupling"
            Arguments = @("--channel", "1", "--coupling", [string]$Snapshot.ChannelCoupling)
        },
        [pscustomobject]@{
            Name = "CH1 display"
            Command = "channel-display"
            Arguments = if ($Snapshot.ChannelDisplay) {
                @("--channel", "1", "--on")
            } else {
                @("--channel", "1", "--off")
            }
        }
    )

    $acquisitionArguments = @("--type", [string]$Snapshot.AcquisitionType)
    if ($Snapshot.AcquisitionType -eq "average") {
        $acquisitionArguments += @("--count", [string]$Snapshot.AcquisitionCount)
    }
    $restoreSteps += [pscustomobject]@{
        Name = "acquisition"
        Command = "acquisition"
        Arguments = $acquisitionArguments
    }

    foreach ($step in $restoreSteps) {
        try {
            Invoke-LiveCli -Stage "restore-$($step.Command)" -Command $step.Command `
                -Arguments $step.Arguments | Out-Null
        } catch {
            $restoreErrors.Add("$($step.Name): $($_.Exception.Message)")
            Drain-AfterFailure -Stage "restore-$($step.Command)-error-drain" `
                -CaseName "cleanup"
        }
    }

    if ($restoreErrors.Count -gt 0) {
        throw ($restoreErrors -join " | ")
    }
}

if ([string]::IsNullOrWhiteSpace($Resource)) {
    throw "Baseline live validation requires an explicit non-empty -Resource."
}
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    throw "Python executable not found: ${Python}"
}

$timestamp = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")
$script:RunRoot = Join-Path $OutputRoot $timestamp
$preflightRoot = Join-Path $script:RunRoot "preflight"
$liveArtifactRoot = Join-Path $script:RunRoot "live"
New-Item -ItemType Directory -Path $preflightRoot -Force | Out-Null
New-Item -ItemType Directory -Path $liveArtifactRoot -Force | Out-Null

Write-Host "Scopes Tool baseline live validation"
Write-Host "Artifacts: $($script:RunRoot)"
Write-Host ""

try {
    Invoke-HardwareFreePreflight -PreflightRoot $preflightRoot
    Add-CaseResult -Name "preflight" -Passed $true
} catch {
    Add-CaseResult -Name "preflight" -Passed $false -Detail $_.Exception.Message
    Write-Host ""
    Write-Host "FAIL  baseline live validation"
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
    Add-CaseResult -Name "identity" -Passed $true
} catch {
    Add-CaseResult -Name "identity" -Passed $false -Detail $_.Exception.Message
    Write-Host ""
    Write-Host "FAIL  baseline live validation"
    Write-Host "Artifacts: $($script:RunRoot)"
    Write-Summary -Result "FAIL"
    exit 1
}

$initialDrainPassed = $false
try {
    $initialDrain = Get-ErrorDrain -Stage "stale-error-drain"
    if (-not $initialDrain.Terminated) {
        throw "Initial error queue did not reach code 0 within 30 reads."
    }
    if ($initialDrain.Errors.Count -gt 0) {
        Write-Host "      drained $($initialDrain.Errors.Count) stale system error(s)"
        Write-DrainErrors -Errors $initialDrain.Errors -CaseName "stale-error-drain"
    }
    Add-CaseResult -Name "stale-error-drain" -Passed $true
    $initialDrainPassed = $true
} catch {
    Add-CaseResult -Name "stale-error-drain" -Passed $false -Detail $_.Exception.Message
}

if (-not $initialDrainPassed) {
    Write-Host ""
    Write-Host "FAIL  baseline live validation"
    Write-Host "No state-changing baseline cases were run."
    Write-Host "Artifacts: $($script:RunRoot)"
    Write-Summary -Result "FAIL"
    exit 1
}

Write-Host ""
Write-Host "Baseline live validation target"
Write-Host ""
Write-Host "Detected instrument: $($identity.idn.raw)"
Write-Host "Connection/resource: ${Resource}"
Write-Host ""
Write-Host "Required setup:"
Write-Host "  - Connect the CH1 probe to the oscilloscope Probe Demo / Probe Comp output."
Write-Host "  - Confirm a stable waveform is visible on CH1."
Write-Host "  - Disconnect unknown DUT signals."
Write-Host "  - This test temporarily changes CH1, acquisition, timebase, trigger,"
Write-Host "    and waveform transfer settings."
Write-Host "  - Acquisition, CH1, timebase, Edge source/slope, and CH1 Edge level"
Write-Host "    will be restored where practical."
Write-Host "  - The generic trigger mode cannot be restored and will remain Edge after"
Write-Host "    the trigger case runs. Waveform transfer format may remain WORD."
Write-Host ""
Write-Host "Press Enter when the environment is ready."
Write-Host "Ctrl+C to cancel."
[void](Read-Host)

$snapshot = $null
$snapshotComplete = $false
$stateChangeStarted = $false

try {
    $acquisition = Invoke-LiveCli -Stage "snapshot-acquisition" -Command "acquisition" `
        -Arguments @("--query")
    $channelDisplay = Invoke-LiveCli -Stage "snapshot-channel-display" `
        -Command "channel-display" -Arguments @("--channel", "1", "--query")
    $channelCoupling = Invoke-LiveCli -Stage "snapshot-channel-coupling" `
        -Command "channel-coupling" -Arguments @("--channel", "1", "--query")
    $timebaseScale = Invoke-LiveCli -Stage "snapshot-timebase-scale" `
        -Command "timebase-scale" -Arguments @("--query")
    $timebasePosition = Invoke-LiveCli -Stage "snapshot-timebase-position" `
        -Command "timebase-position" -Arguments @("--query")
    $triggerSource = Invoke-LiveCli -Stage "snapshot-trigger-source" `
        -Command "trigger-edge-source" -Arguments @("--query")
    $triggerSlope = Invoke-LiveCli -Stage "snapshot-trigger-slope" `
        -Command "trigger-edge-slope" -Arguments @("--query")
    $triggerLevel = Invoke-LiveCli -Stage "snapshot-trigger-level" `
        -Command "trigger-edge-level" -Arguments @("--source-channel", "1", "--query")

    if ($triggerSource.result.source -notin @("analog-channel", "external", "line")) {
        throw "Unsupported Edge source readback: $($triggerSource.result.source)"
    }
    if ($triggerSource.result.source -eq "analog-channel" -and
        [int]$triggerSource.result.source_channel -le 0) {
        throw "Edge source query did not return a valid analog channel."
    }
    if ($triggerSlope.result.slope -notin @("positive", "negative", "either", "alternate")) {
        throw "Unsupported Edge slope readback: $($triggerSlope.result.slope)"
    }

    $snapshot = [pscustomobject]@{
        AcquisitionType = [string]$acquisition.result.type
        AcquisitionCount = [int]$acquisition.result.count
        ChannelDisplay = [bool]$channelDisplay.result.display
        ChannelCoupling = [string]$channelCoupling.result.coupling
        TimebaseScale = Assert-FiniteNumber `
            -Value $timebaseScale.result.seconds_per_division -Label "timebase scale"
        TimebasePosition = Assert-FiniteNumber `
            -Value $timebasePosition.result.position_seconds -Label "timebase position"
        TriggerSource = [string]$triggerSource.result.source
        TriggerSourceChannel = $triggerSource.result.source_channel
        TriggerSlope = [string]$triggerSlope.result.slope
        TriggerLevel = Assert-FiniteNumber `
            -Value $triggerLevel.result.level_volts -Label "CH1 Edge level"
    }
    $snapshotComplete = $true
} catch {
    $script:FunctionalFailed = $true
    Add-CaseResult -Name "state-snapshot" -Passed $false -Detail $_.Exception.Message
    Drain-AfterFailure -Stage "state-snapshot-error-drain" -CaseName "state-snapshot"
}

if ($snapshotComplete) {
    $stateChangeStarted = $true

    Invoke-BaselineCase -Name "acquisition" -Action {
        Invoke-LiveCli -Stage "acquisition-set" -Command "acquisition" `
            -Arguments @("--type", "normal") | Out-Null
        $readback = Invoke-LiveCli -Stage "acquisition-query" -Command "acquisition" `
            -Arguments @("--query")
        if ($readback.result.type -ne "normal") {
            throw "Acquisition type readback is $($readback.result.type), expected normal."
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "channel" -Action {
            Invoke-LiveCli -Stage "channel-display-set" -Command "channel-display" `
                -Arguments @("--channel", "1", "--on") | Out-Null
            Invoke-LiveCli -Stage "channel-coupling-set" -Command "channel-coupling" `
                -Arguments @("--channel", "1", "--coupling", "dc") | Out-Null
            $display = Invoke-LiveCli -Stage "channel-display-query" `
                -Command "channel-display" -Arguments @("--channel", "1", "--query")
            $coupling = Invoke-LiveCli -Stage "channel-coupling-query" `
                -Command "channel-coupling" -Arguments @("--channel", "1", "--query")
            if (-not $display.result.display -or $coupling.result.coupling -ne "dc") {
                throw "CH1 readback did not report display ON and DC coupling."
            }
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "timebase" -Action {
            Invoke-LiveCli -Stage "timebase-scale-set" -Command "timebase-scale" `
                -Arguments @("--seconds-per-division", "0.001") | Out-Null
            Invoke-LiveCli -Stage "timebase-position-set" -Command "timebase-position" `
                -Arguments @("--seconds", "0") | Out-Null
            $scale = Invoke-LiveCli -Stage "timebase-scale-query" `
                -Command "timebase-scale" -Arguments @("--query")
            $position = Invoke-LiveCli -Stage "timebase-position-query" `
                -Command "timebase-position" -Arguments @("--query")
            Assert-NearlyEqual -Actual ([double]$scale.result.seconds_per_division) `
                -Expected 0.001 -Label "Timebase scale"
            Assert-NearlyEqual -Actual ([double]$position.result.position_seconds) `
                -Expected 0 -Label "Timebase position"
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "edge-trigger" -Action {
            $level = ConvertTo-InvariantString -Value ([double]$snapshot.TriggerLevel)
            Invoke-LiveCli -Stage "edge-trigger-set" -Command "trigger-edge" -Arguments @(
                "--source-channel", "1", "--level", $level, "--slope", "positive"
            ) | Out-Null
            $source = Invoke-LiveCli -Stage "edge-trigger-source-query" `
                -Command "trigger-edge-source" -Arguments @("--query")
            $slope = Invoke-LiveCli -Stage "edge-trigger-slope-query" `
                -Command "trigger-edge-slope" -Arguments @("--query")
            $levelReadback = Invoke-LiveCli -Stage "edge-trigger-level-query" `
                -Command "trigger-edge-level" -Arguments @("--source-channel", "1", "--query")
            if ($source.result.source -ne "analog-channel" -or
                [int]$source.result.source_channel -ne 1 -or
                $slope.result.slope -ne "positive") {
                throw "Edge trigger readback did not report CH1 with positive slope."
            }
            Assert-NearlyEqual -Actual ([double]$levelReadback.result.level_volts) `
                -Expected ([double]$snapshot.TriggerLevel) -Label "CH1 Edge level"
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "measurements" -Action {
            $values = @{}
            foreach ($item in @("vpp", "frequency", "period")) {
                $measurement = Invoke-LiveCli -Stage "measure-${item}" -Command "measure" `
                    -Arguments @("--channel", "1", "--item", $item)
                if (-not $measurement.result.valid) {
                    throw "${item} measurement is invalid: $($measurement.result.reason)"
                }
                $values[$item] = Assert-FiniteNumber `
                    -Value $measurement.result.value -Label $item
            }
            if ($values.vpp -le 0) {
                throw "Vpp does not indicate a usable signal: $($values.vpp) V."
            }
            if ($values.frequency -le 0 -or $values.period -le 0) {
                throw "Frequency and Period must be positive."
            }
            $consistency = $values.frequency * $values.period
            if ($consistency -lt 0.8 -or $consistency -gt 1.2) {
                throw "Frequency/Period consistency is ${consistency}, expected 0.8 through 1.2."
            }
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "waveform-byte" -Action {
            $csvPath = Join-Path $liveArtifactRoot "waveform-byte.csv"
            $metadataPath = Join-Path $liveArtifactRoot "waveform-byte-meta.json"
            $capture = Invoke-LiveCli -Stage "waveform-byte" -Command "capture" -Arguments @(
                "--channel", "1", "--points", "1000", "--format", "byte",
                "--csv", $csvPath, "--meta", $metadataPath
            )
            Assert-Capture -Payload $capture -ExpectedFormat "BYTE" `
                -CsvPath $csvPath -MetadataPath $metadataPath
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "waveform-word" -Action {
            $csvPath = Join-Path $liveArtifactRoot "waveform-word.csv"
            $metadataPath = Join-Path $liveArtifactRoot "waveform-word-meta.json"
            $capture = Invoke-LiveCli -Stage "waveform-word" -Command "capture" -Arguments @(
                "--channel", "1", "--points", "1000", "--format", "word",
                "--csv", $csvPath, "--meta", $metadataPath
            )
            Assert-Capture -Payload $capture -ExpectedFormat "WORD" `
                -CsvPath $csvPath -MetadataPath $metadataPath
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "screenshot" -Action {
            $screenshotPath = Join-Path $liveArtifactRoot "screenshot.png"
            $screenshot = Invoke-LiveCli -Stage "screenshot" -Command "screenshot" `
                -Arguments @("--output", $screenshotPath, "--background", "black")
            if ([int]$screenshot.result.byte_count -le 0) {
                throw "Screenshot returned no bytes."
            }
            Assert-FileNonEmpty -Path $screenshotPath -Label "screenshot"
        }
    }
}

if ($snapshotComplete -and $stateChangeStarted) {
    try {
        Restore-InstrumentState -Snapshot $snapshot
        Add-CaseResult -Name "cleanup" -Passed $true
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "cleanup" -Passed $false -Detail $_.Exception.Message
    }
} else {
    Add-CaseResult -Name "cleanup" -Passed $true -Detail "No state-changing case ran."
}

try {
    $finalDrain = Get-ErrorDrain -Stage "final-error-queue"
    if (-not $finalDrain.Terminated) {
        throw "Final error queue did not reach code 0 within 30 reads."
    }
    if ($finalDrain.Errors.Count -gt 0) {
        Write-DrainErrors -Errors $finalDrain.Errors -CaseName "final-error-queue"
        throw "Final error queue contained $($finalDrain.Errors.Count) error(s)."
    }
    Add-CaseResult -Name "final-error-queue" -Passed $true
} catch {
    $script:FunctionalFailed = $true
    Add-CaseResult -Name "final-error-queue" -Passed $false -Detail $_.Exception.Message
}

Write-Host ""
Write-Host "Known restore limitations:"
Write-Host "  - The original generic trigger mode is not queryable through the existing"
Write-Host "    public CLI. If the trigger case ran, the mode remains Edge."
Write-Host "  - Waveform source, format, and points are transfer-session settings without"
Write-Host "    an existing public restore path. The transfer format may remain WORD."
Write-Host ""
Write-Host "Summary"
foreach ($entry in $script:CaseResults.GetEnumerator()) {
    $status = if ($entry.Value.Passed) { "PASS" } else { "FAIL" }
    Write-Host ("{0,-5} {1}" -f $status, $entry.Key)
}
Write-Host "Artifacts: $($script:RunRoot)"

if ($script:FunctionalFailed) {
    Write-Summary -Result "FAIL"
    Write-Host "FAIL  baseline live validation"
    exit 1
}

Write-Summary -Result "PASS"
Write-Host "PASS  baseline live validation"
exit 0
