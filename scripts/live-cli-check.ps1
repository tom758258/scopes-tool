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
        if ($drain.Errors.Count -gt 0) {
            Write-DrainErrors -Errors $drain.Errors -CaseName $CaseName
        }
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

function Assert-ScpiSent {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload,

        [Parameter(Mandatory = $true)]
        [string[]] $ExpectedCommands,

        [Parameter(Mandatory = $true)]
        [string] $Label
    )

    $scpiProperty = $Payload.PSObject.Properties["scpi"]
    if ($null -eq $scpiProperty -or $null -eq $scpiProperty.Value) {
        throw "${Label} did not return SCPI history."
    }
    $sentProperty = $scpiProperty.Value.PSObject.Properties["sent"]
    $sent = @(
        if ($null -ne $sentProperty) {
            $sentProperty.Value
        }
    )
    if ($sent.Count -eq 0) {
        throw "${Label} returned empty SCPI history."
    }
    foreach ($command in $ExpectedCommands) {
        if ($command -notin $sent) {
            throw "${Label} SCPI history does not contain ${command}."
        }
    }
}

function Assert-ScpiSentPrefix {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload,

        [Parameter(Mandatory = $true)]
        [string] $ExpectedPrefix,

        [Parameter(Mandatory = $true)]
        [string] $Label
    )

    $sent = @($Payload.scpi.sent)
    if ($sent.Count -eq 0 -or
        @($sent | Where-Object { [string]$_ -like "${ExpectedPrefix}*" }).Count -eq 0) {
        throw "${Label} SCPI history does not contain prefix ${ExpectedPrefix}."
    }
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
        [string] $MetadataPath,

        [ValidateSet("", "V", "A")]
        [string] $ExpectedVerticalUnit = ""
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
    if (-not [string]::IsNullOrWhiteSpace($ExpectedVerticalUnit)) {
        $captures = @($Payload.result.captures)
        if ($captures.Count -ne 1 -or
            [string]$captures[0].vertical_unit -ne $ExpectedVerticalUnit) {
            throw "${ExpectedFormat} capture did not report vertical unit ${ExpectedVerticalUnit}."
        }
        if ([string]$metadata.vertical_unit -ne $ExpectedVerticalUnit) {
            throw "${ExpectedFormat} metadata did not report vertical unit ${ExpectedVerticalUnit}."
        }
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

function Restore-EdgeTriggerBaseline {
    param(
        [Parameter(Mandatory = $true)]
        [double] $LevelVolts,

        [Parameter(Mandatory = $true)]
        [string] $Stage
    )

    $configured = Invoke-LiveCli -Stage $Stage -Command "trigger-edge" -Arguments @(
        "--source-channel", "1", "--level",
        (ConvertTo-InvariantString -Value $LevelVolts), "--slope", "positive"
    )
    Assert-ScpiSent -Payload $configured -Label "Edge trigger reset" -ExpectedCommands @(
        ":TRIGger:MODE EDGE",
        ":TRIGger:EDGE:SOURce CHANnel1",
        ":TRIGger:EDGE:SLOPe POSitive"
    )
    $source = Invoke-LiveCli -Stage "${Stage}-source-query" `
        -Command "trigger-edge-source" -Arguments @("--query")
    $slope = Invoke-LiveCli -Stage "${Stage}-slope-query" `
        -Command "trigger-edge-slope" -Arguments @("--query")
    if ([string]$source.result.source -ne "analog-channel" -or
        [int]$source.result.source_channel -ne 1 -or
        [string]$slope.result.slope -ne "positive") {
        throw "Edge trigger reset readback is not CH1 positive slope."
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
    foreach ($item in @(
        [pscustomobject]@{ Command = "channel-label"; Arguments = @("--channel", "1", "--text", "P2") },
        [pscustomobject]@{ Command = "channel-scale"; Arguments = @("--channel", "1", "--volts-per-division", "0.5") },
        [pscustomobject]@{ Command = "channel-offset"; Arguments = @("--channel", "1", "--volts", "0") },
        [pscustomobject]@{ Command = "channel-probe"; Arguments = @("--channel", "1", "--ratio", "10") },
        [pscustomobject]@{ Command = "channel-bandwidth-limit"; Arguments = @("--channel", "1", "--off") },
        [pscustomobject]@{ Command = "channel-impedance"; Arguments = @("--channel", "1", "--impedance", "one-meg") },
        [pscustomobject]@{ Command = "channel-invert"; Arguments = @("--channel", "1", "--off") },
        [pscustomobject]@{ Command = "channel-range"; Arguments = @("--channel", "1", "--volts-full-scale", "4") },
        [pscustomobject]@{ Command = "channel-units"; Arguments = @("--channel", "1", "--units", "amp") },
        [pscustomobject]@{ Command = "channel-vernier"; Arguments = @("--channel", "1", "--off") },
        [pscustomobject]@{ Command = "channel-probe-skew"; Arguments = @("--channel", "1", "--seconds", "0") },
        [pscustomobject]@{ Command = "display-label"; Arguments = @("--on") },
        [pscustomobject]@{ Command = "display-persistence"; Arguments = @("--mode", "minimum") },
        [pscustomobject]@{ Command = "display-intensity"; Arguments = @("--value", "75") },
        [pscustomobject]@{ Command = "display-vectors"; Arguments = @("--on") },
        [pscustomobject]@{ Command = "annotation"; Arguments = @("--slot", "1", "--on", "--text", "P2") },
        [pscustomobject]@{ Command = "search-state"; Arguments = @("--enabled", "true") },
        [pscustomobject]@{ Command = "search-mode"; Arguments = @("--mode", "edge") }
    )) {
        Invoke-ModeCli -Stage "preflight-$($item.Command)-set" -Command $item.Command `
            -ModeArguments $dryRun -Arguments $item.Arguments | Out-Null
    }

    foreach ($item in @(
        [pscustomobject]@{ Command = "trigger-edge-coupling"; Arguments = @("--coupling", "dc") },
        [pscustomobject]@{ Command = "trigger-edge-reject"; Arguments = @("--reject", "off") },
        [pscustomobject]@{ Command = "trigger-sweep"; Arguments = @("--mode", "auto") },
        [pscustomobject]@{ Command = "trigger-noise-reject"; Arguments = @("--enabled", "false") },
        [pscustomobject]@{ Command = "trigger-hf-reject"; Arguments = @("--enabled", "false") },
        [pscustomobject]@{ Command = "external-trigger-range"; Arguments = @("--range-volts", "8") },
        [pscustomobject]@{ Command = "trigger-edge-external-level"; Arguments = @("--level-volts", "0") },
        [pscustomobject]@{ Command = "external-trigger-probe"; Arguments = @("--attenuation", "1") },
        [pscustomobject]@{ Command = "external-trigger-units"; Arguments = @("--units", "volts") },
        [pscustomobject]@{ Command = "trigger-pulse-width"; Arguments = @("--channel", "1", "--polarity", "positive", "--qualifier", "greater-than", "--time-seconds", "0.000001", "--level-volts", "0") },
        [pscustomobject]@{ Command = "trigger-runt"; Arguments = @("--channel", "1", "--polarity", "positive", "--qualifier", "none", "--low-level-volts", "-0.5", "--high-level-volts", "0.5") },
        [pscustomobject]@{ Command = "trigger-transition"; Arguments = @("--channel", "1", "--slope", "positive", "--qualifier", "greater-than", "--time-seconds", "0.000001", "--low-level-volts", "-0.5", "--high-level-volts", "0.5") },
        [pscustomobject]@{ Command = "trigger-delay"; Arguments = @("--arm-channel", "1", "--arm-slope", "positive", "--trigger-channel", "2", "--trigger-slope", "positive", "--time-seconds", "0.000001", "--count", "2") },
        [pscustomobject]@{ Command = "trigger-setup-hold"; Arguments = @("--clock-channel", "1", "--data-channel", "2", "--slope", "positive", "--setup-time", "0.000000001", "--hold-time", "0.000000001") },
        [pscustomobject]@{ Command = "trigger-edge-burst"; Arguments = @("--source-channel", "1", "--slope", "positive", "--count", "2", "--idle-time", "0.000001", "--level-volts", "0") },
        [pscustomobject]@{ Command = "trigger-tv"; Arguments = @("--source-channel", "1", "--standard", "ntsc", "--mode", "all-lines", "--polarity", "positive") },
        [pscustomobject]@{ Command = "trigger-pattern"; Arguments = @("--pattern", "XXX1") },
        [pscustomobject]@{ Command = "trigger-or"; Arguments = @("--pattern", "XXXR") },
        [pscustomobject]@{ Command = "math-operator"; Arguments = @("--function", "1", "--operation", "add", "--source1", "channel1", "--source2", "channel2") },
        [pscustomobject]@{ Command = "math-transform"; Arguments = @("--function", "1", "--operation", "absolute", "--source", "channel1") },
        [pscustomobject]@{ Command = "fft"; Arguments = @("--function", "1", "--source-channel", "1", "--units", "decibel", "--window", "hanning", "--display", "on") },
        [pscustomobject]@{ Command = "wgen-function"; Arguments = @("--function", "sine") },
        [pscustomobject]@{ Command = "wgen-frequency"; Arguments = @("--hz", "1000") },
        [pscustomobject]@{ Command = "wgen-voltage"; Arguments = @("--amplitude", "0.5") },
        [pscustomobject]@{ Command = "wgen-offset"; Arguments = @("--volts", "0") },
        [pscustomobject]@{ Command = "wgen-load"; Arguments = @("--load", "one-meg") },
        [pscustomobject]@{ Command = "wgen-output"; Arguments = @("--enabled", "true") },
        [pscustomobject]@{ Command = "demo-function"; Arguments = @("--function", "sine") },
        [pscustomobject]@{ Command = "demo-output"; Arguments = @("--enabled", "true") },
        [pscustomobject]@{ Command = "autoscale"; Arguments = @("--source-channel", "1") },
        [pscustomobject]@{ Command = "setup-save"; Arguments = @("--file", "\usb\scopes-tool-p3-preflight.scp") },
        [pscustomobject]@{ Command = "setup-recall"; Arguments = @("--file", "\usb\scopes-tool-p3-preflight.scp") },
        [pscustomobject]@{ Command = "save-image-format"; Arguments = @("--format", "png") },
        [pscustomobject]@{ Command = "save-image"; Arguments = @("--filename", "\usb\scopes-tool-p3-preflight.png") },
        [pscustomobject]@{ Command = "save-waveform-format"; Arguments = @("--format", "csv") },
        [pscustomobject]@{ Command = "save-waveform-length"; Arguments = @("--points", "1000") },
        [pscustomobject]@{ Command = "save-waveform"; Arguments = @("--filename", "\usb\scopes-tool-p3-preflight.csv") },
        [pscustomobject]@{ Command = "cleanup"; Arguments = @("--profile", "safe") }
    )) {
        Invoke-ModeCli -Stage "preflight-p3-$($item.Command)" -Command $item.Command `
            -ModeArguments $dryRun -Arguments $item.Arguments | Out-Null
    }
    Invoke-ModeCli -Stage "preflight-p3-trigger-edge-external-level-query" `
        -Command "trigger-edge-external-level" -ModeArguments $simulate `
        -Arguments @("--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-p3-save-waveform-length-max-query" `
        -Command "save-waveform-length-max" -ModeArguments $simulate `
        -Arguments @("--query") | Out-Null

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
    Invoke-ModeCli -Stage "preflight-sample-rate-query" -Command "sample-rate" `
        -ModeArguments $simulate -Arguments @("--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-acquisition-points-query" `
        -Command "acquisition-points" -ModeArguments $simulate `
        -Arguments @("--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-record-length-query" -Command "record-length" `
        -ModeArguments $simulate -Arguments @("--query") | Out-Null
    foreach ($command in @(
        "system-opc",
        "system-status-byte",
        "system-operation-status",
        "system-options"
    )) {
        Invoke-ModeCli -Stage "preflight-${command}" -Command $command `
            -ModeArguments $simulate -Arguments @("--query") | Out-Null
    }
    Invoke-ModeCli -Stage "preflight-measure-results" -Command "measure-results" `
        -ModeArguments $simulate | Out-Null
    $channelSummary = Invoke-ModeCli -Stage "preflight-channel-summary" `
        -Command "channel-summary" `
        -ModeArguments @("--simulate", "--model", "keysight-dsox4034a")
    if (@($channelSummary.result.channels).Count -ne 4) {
        throw "4034A simulator channel summary did not return four analog channels."
    }
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
    foreach ($item in @(
        [pscustomobject]@{ Command = "channel-label"; Arguments = @("--channel", "1", "--query") },
        [pscustomobject]@{ Command = "channel-scale"; Arguments = @("--channel", "1", "--query") },
        [pscustomobject]@{ Command = "channel-offset"; Arguments = @("--channel", "1", "--query") },
        [pscustomobject]@{ Command = "channel-probe"; Arguments = @("--channel", "1", "--query") },
        [pscustomobject]@{ Command = "channel-bandwidth-limit"; Arguments = @("--channel", "1", "--query") },
        [pscustomobject]@{ Command = "channel-impedance"; Arguments = @("--channel", "1", "--query") },
        [pscustomobject]@{ Command = "channel-invert"; Arguments = @("--channel", "1", "--query") },
        [pscustomobject]@{ Command = "channel-range"; Arguments = @("--channel", "1", "--query") },
        [pscustomobject]@{ Command = "channel-units"; Arguments = @("--channel", "1", "--query") },
        [pscustomobject]@{ Command = "channel-vernier"; Arguments = @("--channel", "1", "--query") },
        [pscustomobject]@{ Command = "channel-probe-skew"; Arguments = @("--channel", "1", "--query") },
        [pscustomobject]@{ Command = "display-label"; Arguments = @("--query") },
        [pscustomobject]@{ Command = "display-persistence"; Arguments = @("--query") },
        [pscustomobject]@{ Command = "display-intensity"; Arguments = @("--query") },
        [pscustomobject]@{ Command = "display-vectors"; Arguments = @("--query") },
        [pscustomobject]@{ Command = "annotation"; Arguments = @("--slot", "1", "--query") },
        [pscustomobject]@{ Command = "search-state"; Arguments = @("--query") },
        [pscustomobject]@{ Command = "search-mode"; Arguments = @("--query") },
        [pscustomobject]@{ Command = "search-count"; Arguments = @("--query") },
        [pscustomobject]@{ Command = "search-event"; Arguments = @("--query") }
    )) {
        Invoke-ModeCli -Stage "preflight-$($item.Command)-query" -Command $item.Command `
            -ModeArguments $simulate -Arguments $item.Arguments | Out-Null
    }

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

    $bmpPath = Join-Path $artifactRoot "screenshot-4000x.bmp"
    $bmp = Invoke-ModeCli -Stage "preflight-screenshot-bmp" -Command "screenshot" `
        -ModeArguments $simulate -Arguments @("--format", "bmp", "--output", $bmpPath)
    if ([string]$bmp.result.format -ne "BMP" -or [int]$bmp.result.byte_count -le 0) {
        throw "4000X simulator BMP screenshot result is invalid."
    }
    Assert-FileNonEmpty -Path $bmpPath -Label "4000X simulator BMP screenshot"

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
            Name = "CH1 probe skew"
            Command = "channel-probe-skew"
            Arguments = @(
                "--channel", "1", "--seconds",
                (ConvertTo-InvariantString -Value ([double]$Snapshot.ChannelProbeSkew))
            )
        },
        [pscustomobject]@{
            Name = "CH1 vernier"
            Command = "channel-vernier"
            Arguments = @("--channel", "1", $(if ($Snapshot.ChannelVernier) { "--on" } else { "--off" }))
        },
        [pscustomobject]@{
            Name = "CH1 units"
            Command = "channel-units"
            Arguments = @("--channel", "1", "--units", [string]$Snapshot.ChannelUnits)
        },
        [pscustomobject]@{
            Name = "CH1 invert"
            Command = "channel-invert"
            Arguments = @("--channel", "1", $(if ($Snapshot.ChannelInvert) { "--on" } else { "--off" }))
        },
        [pscustomobject]@{
            Name = "CH1 impedance"
            Command = "channel-impedance"
            Arguments = @(
                "--channel", "1", "--impedance",
                $(if ($Snapshot.ChannelImpedance -eq "one_meg") { "one-meg" } else { "fifty" })
            ) + $(if ($Snapshot.ChannelImpedance -eq "fifty") { @("--allow-50-ohm") } else { @() })
        },
        [pscustomobject]@{
            Name = "CH1 bandwidth limit"
            Command = "channel-bandwidth-limit"
            Arguments = @("--channel", "1", $(if ($Snapshot.ChannelBandwidthLimit) { "--on" } else { "--off" }))
        },
        [pscustomobject]@{
            Name = "CH1 probe ratio"
            Command = "channel-probe"
            Arguments = @(
                "--channel", "1", "--ratio",
                (ConvertTo-InvariantString -Value ([double]$Snapshot.ChannelProbeRatio)
                )
            )
        },
        [pscustomobject]@{
            Name = "CH1 range"
            Command = "channel-range"
            Arguments = @(
                "--channel", "1", "--volts-full-scale",
                (ConvertTo-InvariantString -Value ([double]$Snapshot.ChannelRange))
            )
        },
        [pscustomobject]@{
            Name = "CH1 scale"
            Command = "channel-scale"
            Arguments = @(
                "--channel", "1", "--volts-per-division",
                (ConvertTo-InvariantString -Value ([double]$Snapshot.ChannelScale))
            )
        },
        [pscustomobject]@{
            Name = "CH1 offset"
            Command = "channel-offset"
            Arguments = @(
                "--channel", "1", "--volts",
                (ConvertTo-InvariantString -Value ([double]$Snapshot.ChannelOffset))
            )
        },
        [pscustomobject]@{
            Name = "CH1 label"
            Command = "channel-label"
            Arguments = @("--channel", "1", "--text", [string]$Snapshot.ChannelLabel)
        },
        [pscustomobject]@{
            Name = "display intensity"
            Command = "display-intensity"
            Arguments = @("--value", [string]$Snapshot.DisplayIntensity)
        },
        [pscustomobject]@{
            Name = "display persistence"
            Command = "display-persistence"
            Arguments = if ($null -ne $Snapshot.DisplayPersistenceSeconds) {
                @(
                    "--seconds",
                    (ConvertTo-InvariantString -Value ([double]$Snapshot.DisplayPersistenceSeconds))
                )
            } else {
                @("--mode", [string]$Snapshot.DisplayPersistenceMode)
            }
        },
        [pscustomobject]@{
            Name = "display labels"
            Command = "display-label"
            Arguments = @($(if ($Snapshot.DisplayLabels) { "--on" } else { "--off" }))
        },
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

    if ($Snapshot.DisplayVectors) {
        $restoreSteps += [pscustomobject]@{
            Name = "display vectors"
            Command = "display-vectors"
            Arguments = @("--on")
        }
    }
    if ($Snapshot.AnnotationRestorable) {
        $annotationArguments = @(
            "--slot", "1",
            $(if ($Snapshot.AnnotationEnabled) { "--on" } else { "--off" }),
            "--color", [string]$Snapshot.AnnotationColor,
            "--background", [string]$Snapshot.AnnotationBackground
        )
        if ([string]::IsNullOrEmpty([string]$Snapshot.AnnotationText)) {
            $annotationArguments += "--clear"
        } else {
            $annotationArguments += @("--text", [string]$Snapshot.AnnotationText)
        }
        if ($null -ne $Snapshot.AnnotationX -and $null -ne $Snapshot.AnnotationY) {
            $annotationArguments += @(
                "--x", [string]$Snapshot.AnnotationX,
                "--y", [string]$Snapshot.AnnotationY
            )
        }
        $restoreSteps += [pscustomobject]@{
            Name = "annotation slot 1"
            Command = "annotation"
            Arguments = $annotationArguments
        }
    }
    if ($Snapshot.SearchRestorable) {
        $restoreSteps += [pscustomobject]@{
            Name = "search mode"
            Command = "search-mode"
            Arguments = @("--mode", [string]$Snapshot.SearchMode)
        }
        $restoreSteps += [pscustomobject]@{
            Name = "search state"
            Command = "search-state"
            Arguments = @("--enabled", ([string][bool]$Snapshot.SearchEnabled).ToLowerInvariant())
        }
    }
    $p3Property = $Snapshot.PSObject.Properties["P3Enabled"]
    if ($null -ne $p3Property -and [bool]$p3Property.Value) {
        $restoreSteps += @(
            [pscustomobject]@{
                Name = "Math Function 1 display"
                Command = "math-display"
                Arguments = @("--function", "1", "--off")
            },
            [pscustomobject]@{
                Name = "WGEN output"
                Command = "wgen-output"
                Arguments = @("--enabled", "false")
            },
            [pscustomobject]@{
                Name = "DEMO output"
                Command = "demo-output"
                Arguments = @("--enabled", "false")
            },
            [pscustomobject]@{
                Name = "trigger sweep"
                Command = "trigger-sweep"
                Arguments = @("--mode", [string]$Snapshot.TriggerSweep)
            },
            [pscustomobject]@{
                Name = "trigger noise reject"
                Command = "trigger-noise-reject"
                Arguments = @("--enabled", ([string][bool]$Snapshot.TriggerNoiseReject).ToLowerInvariant())
            },
            [pscustomobject]@{
                Name = "trigger HF reject"
                Command = "trigger-hf-reject"
                Arguments = @("--enabled", ([string][bool]$Snapshot.TriggerHfReject).ToLowerInvariant())
            },
            [pscustomobject]@{
                Name = "Edge coupling"
                Command = "trigger-edge-coupling"
                Arguments = @("--coupling", [string]$Snapshot.TriggerEdgeCoupling)
            },
            [pscustomobject]@{
                Name = "Edge reject"
                Command = "trigger-edge-reject"
                Arguments = @("--reject", [string]$Snapshot.TriggerEdgeReject)
            },
            [pscustomobject]@{
                Name = "External trigger range"
                Command = "external-trigger-range"
                Arguments = @(
                    "--range-volts",
                    (ConvertTo-InvariantString -Value ([double]$Snapshot.ExternalTriggerRange))
                )
            },
            [pscustomobject]@{
                Name = "External trigger probe"
                Command = "external-trigger-probe"
                Arguments = @(
                    "--attenuation",
                    (ConvertTo-InvariantString -Value ([double]$Snapshot.ExternalTriggerProbe))
                )
            },
            [pscustomobject]@{
                Name = "External trigger units"
                Command = "external-trigger-units"
                Arguments = @("--units", [string]$Snapshot.ExternalTriggerUnits)
            },
            [pscustomobject]@{
                Name = "External Edge level"
                Command = "trigger-edge-external-level"
                Arguments = @(
                    "--level-volts",
                    (ConvertTo-InvariantString -Value ([double]$Snapshot.ExternalTriggerLevel))
                )
            }
        )
        if ([string]$Snapshot.SaveImageFormat -in @("png", "bmp", "bmp8", "bmp24")) {
            $restoreSteps += [pscustomobject]@{
                Name = "image save format"
                Command = "save-image-format"
                Arguments = @("--format", [string]$Snapshot.SaveImageFormat)
            }
        } elseif ([string]$Snapshot.SaveWaveformFormat -in @("ascii-xy", "csv", "binary")) {
            $restoreSteps += [pscustomobject]@{
                Name = "waveform save format"
                Command = "save-waveform-format"
                Arguments = @("--format", [string]$Snapshot.SaveWaveformFormat)
            }
        }
        if ([int]$Snapshot.SaveWaveformLength -gt 0) {
            $restoreSteps += [pscustomobject]@{
                Name = "waveform save length"
                Command = "save-waveform-length"
                Arguments = @("--points", [string]$Snapshot.SaveWaveformLength)
            }
        }
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

    if ($restoreErrors.Count -eq 0) {
        try {
            $summary = Invoke-LiveCli -Stage "restore-channel-summary-query" `
                -Command "channel-summary"
            $channel = @($summary.result.channels)[0]
            if ([string]$channel.label -ne [string]$Snapshot.ChannelLabel -or
                [bool]$channel.bandwidth_limit -ne [bool]$Snapshot.ChannelBandwidthLimit -or
                [string]$channel.impedance -ne [string]$Snapshot.ChannelImpedance -or
                [bool]$channel.invert -ne [bool]$Snapshot.ChannelInvert -or
                [string]$channel.units -ne [string]$Snapshot.ChannelUnits -or
                [bool]$channel.vernier -ne [bool]$Snapshot.ChannelVernier) {
                throw "CH1 restored state does not match the snapshot."
            }
            Assert-NearlyEqual -Actual ([double]$channel.scale) `
                -Expected ([double]$Snapshot.ChannelScale) -Label "Restored CH1 scale"
            Assert-NearlyEqual -Actual ([double]$channel.range) `
                -Expected ([double]$Snapshot.ChannelRange) -Label "Restored CH1 range"
            Assert-NearlyEqual -Actual ([double]$channel.offset) `
                -Expected ([double]$Snapshot.ChannelOffset) -Label "Restored CH1 offset"
            Assert-NearlyEqual -Actual ([double]$channel.probe_ratio) `
                -Expected ([double]$Snapshot.ChannelProbeRatio) -Label "Restored CH1 probe ratio"
            Assert-NearlyEqual -Actual ([double]$channel.probe_skew) `
                -Expected ([double]$Snapshot.ChannelProbeSkew) -Label "Restored CH1 probe skew"

            $labels = Invoke-LiveCli -Stage "restore-display-label-query" `
                -Command "display-label" -Arguments @("--query")
            $persistence = Invoke-LiveCli -Stage "restore-display-persistence-query" `
                -Command "display-persistence" -Arguments @("--query")
            $intensity = Invoke-LiveCli -Stage "restore-display-intensity-query" `
                -Command "display-intensity" -Arguments @("--query")
            $vectors = Invoke-LiveCli -Stage "restore-display-vectors-query" `
                -Command "display-vectors" -Arguments @("--query")
            if ([bool]$labels.result.display_label -ne [bool]$Snapshot.DisplayLabels -or
                [int]$intensity.result.value -ne [int]$Snapshot.DisplayIntensity -or
                [bool]$vectors.result.value -ne [bool]$Snapshot.DisplayVectors) {
                throw "Restored display state does not match the snapshot."
            }
            if ($null -ne $Snapshot.DisplayPersistenceSeconds) {
                Assert-NearlyEqual -Actual ([double]$persistence.result.seconds) `
                    -Expected ([double]$Snapshot.DisplayPersistenceSeconds) `
                    -Label "Restored display persistence"
            } elseif ([string]$persistence.result.mode -ne [string]$Snapshot.DisplayPersistenceMode) {
                throw "Restored display-persistence mode does not match the snapshot."
            }

            if ($Snapshot.AnnotationRestorable) {
                $annotation = Invoke-LiveCli -Stage "restore-annotation-query" `
                    -Command "annotation" -Arguments @("--slot", "1", "--query")
                if ([bool]$annotation.result.enabled -ne [bool]$Snapshot.AnnotationEnabled -or
                    [string]$annotation.result.text -ne [string]$Snapshot.AnnotationText -or
                    [string]$annotation.result.color -ne [string]$Snapshot.AnnotationColor -or
                    [string]$annotation.result.background -ne [string]$Snapshot.AnnotationBackground -or
                    $annotation.result.x -ne $Snapshot.AnnotationX -or
                    $annotation.result.y -ne $Snapshot.AnnotationY) {
                    throw "Restored annotation state does not match the snapshot."
                }
            }
            if ($Snapshot.SearchRestorable) {
                $search = Invoke-LiveCli -Stage "restore-search-state-query" `
                    -Command "search-state" -Arguments @("--query")
                if ([bool]$search.result.enabled -ne [bool]$Snapshot.SearchEnabled) {
                    throw "Restored Search state does not match the snapshot."
                }
                if ($Snapshot.SearchEnabled) {
                    $mode = Invoke-LiveCli -Stage "restore-search-mode-query" `
                        -Command "search-mode" -Arguments @("--query")
                    if ([string]$mode.result.mode -ne [string]$Snapshot.SearchMode) {
                        throw "Restored Search mode does not match the snapshot."
                    }
                }
            }
            if ($null -ne $p3Property -and [bool]$p3Property.Value) {
                $wgen = Invoke-LiveCli -Stage "restore-wgen-output-query" `
                    -Command "wgen-output" -Arguments @("--query")
                $demo = Invoke-LiveCli -Stage "restore-demo-output-query" `
                    -Command "demo-output" -Arguments @("--query")
                $math = Invoke-LiveCli -Stage "restore-math-display-query" `
                    -Command "math-display" -Arguments @("--function", "1", "--query")
                if ([bool]$wgen.result.enabled -or [bool]$demo.result.enabled -or
                    [bool]$math.result.enabled) {
                    throw "P3 output cleanup did not leave WGEN, DEMO, and Math OFF."
                }
            }
        } catch {
            $restoreErrors.Add("restore readback: $($_.Exception.Message)")
            Drain-AfterFailure -Stage "restore-readback-error-drain" -CaseName "cleanup"
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
    if ($initialDrain.Errors.Count -gt 0) {
        Write-Host "      drained $($initialDrain.Errors.Count) stale system error(s)"
        Write-DrainErrors -Errors $initialDrain.Errors -CaseName "stale-error-drain"
    }
    if (-not $initialDrain.Terminated) {
        throw "Initial error queue did not reach code 0 within 30 reads."
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
Write-Host "  - Leave WGEN output OFF and disconnected from any unknown DUT."
Write-Host "  - Leave DEMO output OFF."
Write-Host "  - Do not connect the External trigger input to an unknown or sensitive DUT."
Write-Host "  - Insert writable USB storage for setup and Save/Export test files."
Write-Host "  - This test temporarily changes CH1, acquisition, display, Search,"
Write-Host "    annotation, timebase, trigger, Math, WGEN, DEMO, and save settings."
Write-Host "  - Modified public settings will be restored where practical."
Write-Host "  - Math Function 1 is disposable acceptance state and will finish OFF."
Write-Host "  - Safe Cleanup clears the display; DVM and DEMO may finish OFF rather"
Write-Host "    than return to a pre-test ON state."
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
    $channelLabel = Invoke-LiveCli -Stage "snapshot-channel-label" `
        -Command "channel-label" -Arguments @("--channel", "1", "--query")
    $channelScale = Invoke-LiveCli -Stage "snapshot-channel-scale" `
        -Command "channel-scale" -Arguments @("--channel", "1", "--query")
    $channelOffset = Invoke-LiveCli -Stage "snapshot-channel-offset" `
        -Command "channel-offset" -Arguments @("--channel", "1", "--query")
    $channelProbe = Invoke-LiveCli -Stage "snapshot-channel-probe" `
        -Command "channel-probe" -Arguments @("--channel", "1", "--query")
    $channelBandwidth = Invoke-LiveCli -Stage "snapshot-channel-bandwidth" `
        -Command "channel-bandwidth-limit" -Arguments @("--channel", "1", "--query")
    $channelImpedance = Invoke-LiveCli -Stage "snapshot-channel-impedance" `
        -Command "channel-impedance" -Arguments @("--channel", "1", "--query")
    $channelInvert = Invoke-LiveCli -Stage "snapshot-channel-invert" `
        -Command "channel-invert" -Arguments @("--channel", "1", "--query")
    $channelRange = Invoke-LiveCli -Stage "snapshot-channel-range" `
        -Command "channel-range" -Arguments @("--channel", "1", "--query")
    $channelUnits = Invoke-LiveCli -Stage "snapshot-channel-units" `
        -Command "channel-units" -Arguments @("--channel", "1", "--query")
    $channelVernier = Invoke-LiveCli -Stage "snapshot-channel-vernier" `
        -Command "channel-vernier" -Arguments @("--channel", "1", "--query")
    $channelProbeSkew = Invoke-LiveCli -Stage "snapshot-channel-probe-skew" `
        -Command "channel-probe-skew" -Arguments @("--channel", "1", "--query")
    $displayLabels = Invoke-LiveCli -Stage "snapshot-display-labels" `
        -Command "display-label" -Arguments @("--query")
    $displayPersistence = Invoke-LiveCli -Stage "snapshot-display-persistence" `
        -Command "display-persistence" -Arguments @("--query")
    $displayIntensity = Invoke-LiveCli -Stage "snapshot-display-intensity" `
        -Command "display-intensity" -Arguments @("--query")
    $displayVectors = Invoke-LiveCli -Stage "snapshot-display-vectors" `
        -Command "display-vectors" -Arguments @("--query")
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

    $p3Enabled = [string]$identity.idn.series -eq "4000X"
    $triggerEdgeCoupling = $null
    $triggerEdgeReject = $null
    $triggerSweep = $null
    $triggerNoiseReject = $null
    $triggerHfReject = $null
    $externalTrigger = $null
    $externalTriggerLevel = $null
    $saveImageFormat = $null
    $saveWaveformFormat = $null
    $saveWaveformLength = $null
    $saveWaveformLengthMax = $null
    if ($p3Enabled) {
        $triggerEdgeCoupling = Invoke-LiveCli -Stage "snapshot-trigger-edge-coupling" `
            -Command "trigger-edge-coupling" -Arguments @("--query")
        $triggerEdgeReject = Invoke-LiveCli -Stage "snapshot-trigger-edge-reject" `
            -Command "trigger-edge-reject" -Arguments @("--query")
        $triggerSweep = Invoke-LiveCli -Stage "snapshot-trigger-sweep" `
            -Command "trigger-sweep" -Arguments @("--query")
        $triggerNoiseReject = Invoke-LiveCli -Stage "snapshot-trigger-noise-reject" `
            -Command "trigger-noise-reject" -Arguments @("--query")
        $triggerHfReject = Invoke-LiveCli -Stage "snapshot-trigger-hf-reject" `
            -Command "trigger-hf-reject" -Arguments @("--query")
        $externalTrigger = Invoke-LiveCli -Stage "snapshot-external-trigger" `
            -Command "external-trigger-settings" -Arguments @("--query")
        $externalTriggerLevel = Invoke-LiveCli -Stage "snapshot-external-trigger-level" `
            -Command "trigger-edge-external-level" -Arguments @("--query")
        $saveImageFormat = Invoke-LiveCli -Stage "snapshot-save-image-format" `
            -Command "save-image-format" -Arguments @("--query")
        $saveWaveformFormat = Invoke-LiveCli -Stage "snapshot-save-waveform-format" `
            -Command "save-waveform-format" -Arguments @("--query")
        $saveWaveformLength = Invoke-LiveCli -Stage "snapshot-save-waveform-length" `
            -Command "save-waveform-length" -Arguments @("--query")
        $saveWaveformLengthMax = Invoke-LiveCli `
            -Stage "snapshot-save-waveform-length-max" `
            -Command "save-waveform-length-max" -Arguments @("--query")
    }

    $annotationState = $null
    $annotationRestorable = $false
    if ([bool]$identity.capabilities.supports_annotation) {
        $annotationState = Invoke-LiveCli -Stage "snapshot-annotation" `
            -Command "annotation" -Arguments @("--slot", "1", "--query")
        $annotationText = [string]$annotationState.result.text
        $annotationRestorable = $annotationText -notmatch '["]|[^ -~]'
    }

    $searchState = $null
    $searchMode = $null
    $searchRestorable = $false
    if ([bool]$identity.capabilities.supports_search_basic) {
        $searchState = Invoke-LiveCli -Stage "snapshot-search-state" `
            -Command "search-state" -Arguments @("--query")
        $searchMode = Invoke-LiveCli -Stage "snapshot-search-mode" `
            -Command "search-mode" -Arguments @("--query")
        $searchRestorable = (
            "edge" -in @($identity.capabilities.search_modes) -and
            -not [string]::IsNullOrWhiteSpace([string]$searchMode.result.mode)
        )
    }

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
        ChannelLabel = [string]$channelLabel.result.text
        ChannelScale = Assert-FiniteNumber -Value $channelScale.result.volts_per_division `
            -Label "CH1 scale"
        ChannelOffset = Assert-FiniteNumber -Value $channelOffset.result.volts `
            -Label "CH1 offset"
        ChannelProbeRatio = Assert-FiniteNumber -Value $channelProbe.result.probe_ratio `
            -Label "CH1 probe ratio"
        ChannelBandwidthLimit = [bool]$channelBandwidth.result.bandwidth_limit
        ChannelImpedance = [string]$channelImpedance.result.impedance
        ChannelInvert = [bool]$channelInvert.result.invert
        ChannelRange = Assert-FiniteNumber -Value $channelRange.result.range_volts `
            -Label "CH1 range"
        ChannelUnits = [string]$channelUnits.result.units
        ChannelVernier = [bool]$channelVernier.result.vernier
        ChannelProbeSkew = Assert-FiniteNumber `
            -Value $channelProbeSkew.result.probe_skew_seconds -Label "CH1 probe skew"
        DisplayLabels = [bool]$displayLabels.result.display_label
        DisplayPersistenceMode = $displayPersistence.result.mode
        DisplayPersistenceSeconds = $displayPersistence.result.seconds
        DisplayIntensity = [int]$displayIntensity.result.value
        DisplayVectors = [bool]$displayVectors.result.value
        AnnotationRestorable = $annotationRestorable
        AnnotationEnabled = if ($null -ne $annotationState) { [bool]$annotationState.result.enabled } else { $false }
        AnnotationText = if ($null -ne $annotationState) { [string]$annotationState.result.text } else { "" }
        AnnotationColor = if ($null -ne $annotationState) { [string]$annotationState.result.color } else { "" }
        AnnotationBackground = if ($null -ne $annotationState) { [string]$annotationState.result.background } else { "" }
        AnnotationX = if ($null -ne $annotationState) { $annotationState.result.x } else { $null }
        AnnotationY = if ($null -ne $annotationState) { $annotationState.result.y } else { $null }
        SearchRestorable = $searchRestorable
        SearchEnabled = if ($null -ne $searchState) { [bool]$searchState.result.enabled } else { $false }
        SearchMode = if ($null -ne $searchMode) { [string]$searchMode.result.mode } else { "" }
        TimebaseScale = Assert-FiniteNumber `
            -Value $timebaseScale.result.seconds_per_division -Label "timebase scale"
        TimebasePosition = Assert-FiniteNumber `
            -Value $timebasePosition.result.position_seconds -Label "timebase position"
        TriggerSource = [string]$triggerSource.result.source
        TriggerSourceChannel = $triggerSource.result.source_channel
        TriggerSlope = [string]$triggerSlope.result.slope
        TriggerLevel = Assert-FiniteNumber `
            -Value $triggerLevel.result.level_volts -Label "CH1 Edge level"
        P3Enabled = $p3Enabled
        TriggerEdgeCoupling = if ($null -ne $triggerEdgeCoupling) { [string]$triggerEdgeCoupling.result.coupling } else { "" }
        TriggerEdgeReject = if ($null -ne $triggerEdgeReject) { [string]$triggerEdgeReject.result.reject } else { "" }
        TriggerSweep = if ($null -ne $triggerSweep) { [string]$triggerSweep.result.mode } else { "" }
        TriggerNoiseReject = if ($null -ne $triggerNoiseReject) { [bool]$triggerNoiseReject.result.enabled } else { $false }
        TriggerHfReject = if ($null -ne $triggerHfReject) { [bool]$triggerHfReject.result.enabled } else { $false }
        ExternalTriggerRange = if ($null -ne $externalTrigger) { [double]$externalTrigger.result.range_value } else { 0.0 }
        ExternalTriggerProbe = if ($null -ne $externalTrigger) { [double]$externalTrigger.result.probe_attenuation } else { 0.0 }
        ExternalTriggerUnits = if ($null -ne $externalTrigger) { [string]$externalTrigger.result.units } else { "" }
        ExternalTriggerLevel = if ($null -ne $externalTriggerLevel) { [double]$externalTriggerLevel.result.level_volts } else { 0.0 }
        SaveImageFormat = if ($null -ne $saveImageFormat) { [string]$saveImageFormat.result.format } else { "none" }
        SaveWaveformFormat = if ($null -ne $saveWaveformFormat) { [string]$saveWaveformFormat.result.format } else { "none" }
        SaveWaveformLength = if ($null -ne $saveWaveformLength) { [int]$saveWaveformLength.result.points } else { 0 }
        SaveWaveformLengthMax = if ($null -ne $saveWaveformLengthMax) { [bool]$saveWaveformLengthMax.result.enabled } else { $false }
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
        Invoke-BaselineCase -Name "acquisition-average" -Action {
            $configured = Invoke-LiveCli -Stage "acquisition-average-set" `
                -Command "acquisition" `
                -Arguments @("--type", "average", "--count", "16")
            Assert-ScpiSent -Payload $configured -Label "Average acquisition configure" `
                -ExpectedCommands @(
                    ":ACQuire:TYPE AVERage",
                    ":ACQuire:COUNt 16"
                )
            $readback = Invoke-LiveCli -Stage "acquisition-average-query" `
                -Command "acquisition" -Arguments @("--query")
            Assert-ScpiSent -Payload $readback -Label "Average acquisition query" `
                -ExpectedCommands @(
                    ":ACQuire:TYPE?",
                    ":ACQuire:COUNt?"
                )
            if ($readback.result.type -ne "average" -or
                [int]$readback.result.count -ne 16) {
                throw (
                    "Average acquisition readback is type=$($readback.result.type), " +
                    "count=$($readback.result.count); expected average, 16."
                )
            }
            $normal = Invoke-LiveCli -Stage "acquisition-average-reset-normal" `
                -Command "acquisition" -Arguments @("--type", "normal")
            Assert-ScpiSent -Payload $normal -Label "Acquisition reset to normal" `
                -ExpectedCommands @(
                    ":ACQuire:TYPE NORMal"
                )
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "acquisition-queries" -Action {
            $sampleRate = Invoke-LiveCli -Stage "sample-rate-query" `
                -Command "sample-rate" -Arguments @("--query")
            Assert-ScpiSent -Payload $sampleRate -Label "Sample rate query" `
                -ExpectedCommands @(
                    ":ACQuire:SRATe?"
                )
            $sampleRateHz = Assert-FiniteNumber `
                -Value $sampleRate.result.sample_rate_hz -Label "Sample rate"
            if ($sampleRateHz -le 0) {
                throw "Sample rate must be positive."
            }

            $acquisitionPoints = Invoke-LiveCli -Stage "acquisition-points-query" `
                -Command "acquisition-points" -Arguments @("--query")
            Assert-ScpiSent -Payload $acquisitionPoints -Label "Acquisition points query" `
                -ExpectedCommands @(
                    ":ACQuire:POINts?"
                )
            if ([int64]$acquisitionPoints.result.acquisition_points -le 0) {
                throw "Acquisition points must be positive."
            }

            $recordLength = Invoke-LiveCli -Stage "record-length-query" `
                -Command "record-length" -Arguments @("--query")
            Assert-ScpiSent -Payload $recordLength -Label "Record length query" `
                -ExpectedCommands @(
                    ":ACQuire:RLENgth?"
                )
            if ([int64]$recordLength.result.record_length_points -le 0) {
                throw "Record length must be positive."
            }
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "system-status" -Action {
            $opc = Invoke-LiveCli -Stage "system-opc-query" `
                -Command "system-opc" -Arguments @("--query")
            Assert-ScpiSent -Payload $opc -Label "Operation Complete query" `
                -ExpectedCommands @("*OPC?")
            if (-not $opc.result.complete -or [string]$opc.result.raw -ne "1") {
                throw "Operation Complete query did not report complete=true and raw=1."
            }

            $statusByte = Invoke-LiveCli -Stage "system-status-byte-query" `
                -Command "system-status-byte" -Arguments @("--query")
            Assert-ScpiSent -Payload $statusByte -Label "Status Byte query" `
                -ExpectedCommands @("*STB?")
            $statusByteValue = [int]$statusByte.result.value
            if ($statusByteValue -lt 0 -or $statusByteValue -gt 255) {
                throw "Status Byte is outside 0..255: ${statusByteValue}."
            }
            [void]@($statusByte.result.set_bits)

            $operationStatus = Invoke-LiveCli -Stage "system-operation-status-query" `
                -Command "system-operation-status" -Arguments @("--query")
            Assert-ScpiSent -Payload $operationStatus `
                -Label "Operation Status Condition query" `
                -ExpectedCommands @(
                    ":OPERegister:CONDition?"
                )
            $operationStatusValue = [int]$operationStatus.result.value
            if ($operationStatusValue -lt 0 -or $operationStatusValue -gt 65535) {
                throw (
                    "Operation Status Condition is outside 0..65535: " +
                    "${operationStatusValue}."
                )
            }
            [void]@($operationStatus.result.set_bits)

            $options = Invoke-LiveCli -Stage "system-options-query" `
                -Command "system-options" -Arguments @("--query")
            Assert-ScpiSent -Payload $options -Label "Installed Options query" `
                -ExpectedCommands @("*OPT?")
            if ([string]::IsNullOrWhiteSpace([string]$options.result.raw) -or
                @($options.result.options).Count -eq 0) {
                throw "Installed Options query returned no option data."
            }
        }
    }

    if (-not $script:FunctionalFailed -and
        [bool]$identity.capabilities.supports_measure_results_dump) {
        Invoke-BaselineCase -Name "measure-results" -Action {
            $results = Invoke-LiveCli -Stage "measure-results" `
                -Command "measure-results"
            Assert-ScpiSent -Payload $results -Label "Measure Results query" `
                -ExpectedCommands @(
                    ":MEASure:RESults?"
                )
            if ($results.result.operation -ne "query" -or
                $results.result.command -ne ":MEASure:RESults?") {
                throw "Measure Results did not report the expected query operation."
            }
            [void][string]$results.result.raw
            [void]@($results.result.items)
            [void]@($results.result.statistics_items)
        }
    } elseif (-not $script:FunctionalFailed) {
        Write-Host "SKIP  measure-results (not supported by the detected instrument)"
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "channel-summary" -Action {
            $summary = Invoke-LiveCli -Stage "channel-summary" `
                -Command "channel-summary"
            $channelCount = [int]$identity.capabilities.analog_channels
            $channels = @($summary.result.channels)
            if ($channelCount -le 0 -or $channels.Count -ne $channelCount) {
                throw (
                    "Channel Summary returned $($channels.Count) analog channels; " +
                    "expected ${channelCount}."
                )
            }
            for ($index = 0; $index -lt $channels.Count; $index += 1) {
                $channel = $channels[$index]
                $expectedChannel = $index + 1
                if ([int]$channel.channel -ne $expectedChannel) {
                    throw (
                        "Channel Summary entry $($index + 1) reports " +
                        "channel $($channel.channel)."
                    )
                }
                foreach ($field in @("display", "scale", "offset", "coupling")) {
                    if ($null -eq $channel.PSObject.Properties[$field]) {
                        throw "CH${expectedChannel} summary is missing ${field}."
                    }
                }
            }
            $expectedDisplayQueries = @(
                foreach ($channel in 1..$channelCount) {
                    ":CHANnel${channel}:DISPlay?"
                }
            )
            Assert-ScpiSent -Payload $summary -Label "Channel Summary query" `
                -ExpectedCommands $expectedDisplayQueries
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
        Invoke-BaselineCase -Name "channel-vertical" -Action {
            $labelSet = Invoke-LiveCli -Stage "channel-label-set" -Command "channel-label" `
                -Arguments @("--channel", "1", "--text", [string]$snapshot.ChannelLabel)
            if (-not @($labelSet.scpi.sent | Where-Object {
                ([string]$_).StartsWith(':CHANnel1:LABel "')
            })) {
                throw "CH1 label configure did not use the CH1 label SCPI path."
            }
            $label = Invoke-LiveCli -Stage "channel-label-query" -Command "channel-label" `
                -Arguments @("--channel", "1", "--query")
            Assert-ScpiSent -Payload $label -Label "CH1 label query" `
                -ExpectedCommands @(":CHANnel1:LABel?")
            if ([string]$label.result.text -ne [string]$snapshot.ChannelLabel) {
                throw "CH1 label readback does not match the snapshot."
            }

            $scaleValue = ConvertTo-InvariantString -Value ([double]$snapshot.ChannelScale)
            $scaleSet = Invoke-LiveCli -Stage "channel-scale-set-p2" -Command "channel-scale" `
                -Arguments @("--channel", "1", "--volts-per-division", $scaleValue)
            $scale = Invoke-LiveCli -Stage "channel-scale-query-p2" -Command "channel-scale" `
                -Arguments @("--channel", "1", "--query")
            Assert-ScpiSent -Payload $scale -Label "CH1 scale query" `
                -ExpectedCommands @(":CHANnel1:SCALe?")
            Assert-NearlyEqual -Actual ([double]$scale.result.volts_per_division) `
                -Expected ([double]$snapshot.ChannelScale) -Label "CH1 scale"
            if (-not @($scaleSet.scpi.sent | Where-Object {
                ([string]$_).StartsWith(":CHANnel1:SCALe ")
            })) {
                throw "CH1 scale configure did not use the CH1 scale SCPI path."
            }

            $rangeValue = ConvertTo-InvariantString -Value ([double]$snapshot.ChannelRange)
            $rangeSet = Invoke-LiveCli -Stage "channel-range-set" -Command "channel-range" `
                -Arguments @("--channel", "1", "--volts-full-scale", $rangeValue)
            $range = Invoke-LiveCli -Stage "channel-range-query" -Command "channel-range" `
                -Arguments @("--channel", "1", "--query")
            Assert-ScpiSent -Payload $range -Label "CH1 range query" `
                -ExpectedCommands @(":CHANnel1:RANGe?")
            Assert-NearlyEqual -Actual ([double]$range.result.range_volts) `
                -Expected ([double]$snapshot.ChannelRange) -Label "CH1 range"
            if (-not @($rangeSet.scpi.sent | Where-Object {
                ([string]$_).StartsWith(":CHANnel1:RANGe ")
            })) {
                throw "CH1 range configure did not use the CH1 range SCPI path."
            }

            $offsetValue = ConvertTo-InvariantString -Value ([double]$snapshot.ChannelOffset)
            $offsetSet = Invoke-LiveCli -Stage "channel-offset-set-p2" -Command "channel-offset" `
                -Arguments @("--channel", "1", "--volts", $offsetValue)
            $offset = Invoke-LiveCli -Stage "channel-offset-query-p2" -Command "channel-offset" `
                -Arguments @("--channel", "1", "--query")
            Assert-NearlyEqual -Actual ([double]$offset.result.volts) `
                -Expected ([double]$snapshot.ChannelOffset) -Label "CH1 offset"
            if (-not @($offsetSet.scpi.sent | Where-Object {
                ([string]$_).StartsWith(":CHANnel1:OFFSet ")
            })) {
                throw "CH1 offset configure did not use the CH1 offset SCPI path."
            }
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "channel-probe" -Action {
            $ratioValue = ConvertTo-InvariantString -Value ([double]$snapshot.ChannelProbeRatio)
            $ratioSet = Invoke-LiveCli -Stage "channel-probe-set" -Command "channel-probe" `
                -Arguments @("--channel", "1", "--ratio", $ratioValue)
            $ratio = Invoke-LiveCli -Stage "channel-probe-query" -Command "channel-probe" `
                -Arguments @("--channel", "1", "--query")
            Assert-NearlyEqual -Actual ([double]$ratio.result.probe_ratio) `
                -Expected ([double]$snapshot.ChannelProbeRatio) -Label "CH1 probe ratio"
            if (-not @($ratioSet.scpi.sent | Where-Object {
                ([string]$_).StartsWith(":CHANnel1:PROBe ")
            })) {
                throw "CH1 probe ratio configure did not use the CH1 probe SCPI path."
            }

            $bandwidthAction = if ($snapshot.ChannelBandwidthLimit) { "--on" } else { "--off" }
            $bandwidthSet = Invoke-LiveCli -Stage "channel-bandwidth-set" `
                -Command "channel-bandwidth-limit" `
                -Arguments @("--channel", "1", $bandwidthAction)
            Assert-ScpiSent -Payload $bandwidthSet -Label "CH1 bandwidth configure" `
                -ExpectedCommands @(
                    ":CHANnel1:BWLimit $(if ($snapshot.ChannelBandwidthLimit) { 'ON' } else { 'OFF' })"
                )
            $bandwidth = Invoke-LiveCli -Stage "channel-bandwidth-query" `
                -Command "channel-bandwidth-limit" -Arguments @("--channel", "1", "--query")
            if ([bool]$bandwidth.result.bandwidth_limit -ne $snapshot.ChannelBandwidthLimit) {
                throw "CH1 bandwidth-limit readback does not match the snapshot."
            }

            $impedanceValue = if ($snapshot.ChannelImpedance -eq "one_meg") {
                "one-meg"
            } else {
                "fifty"
            }
            $impedanceArguments = @("--channel", "1", "--impedance", $impedanceValue)
            if ($impedanceValue -eq "fifty") {
                $impedanceArguments += "--allow-50-ohm"
            }
            $impedanceSet = Invoke-LiveCli -Stage "channel-impedance-set" `
                -Command "channel-impedance" -Arguments $impedanceArguments
            $impedanceScpiValue = if ($impedanceValue -eq "one-meg") { "ONEMeg" } else { "FIFTy" }
            Assert-ScpiSent -Payload $impedanceSet -Label "CH1 impedance configure" `
                -ExpectedCommands @(":CHANnel1:IMPedance ${impedanceScpiValue}")
            $impedance = Invoke-LiveCli -Stage "channel-impedance-query" `
                -Command "channel-impedance" -Arguments @("--channel", "1", "--query")
            if ([string]$impedance.result.impedance -ne [string]$snapshot.ChannelImpedance) {
                throw "CH1 impedance readback does not match the snapshot."
            }
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "channel-advanced" -Action {
            foreach ($item in @(
                [pscustomobject]@{
                    Name = "invert"
                    Command = "channel-invert"
                    Action = if ($snapshot.ChannelInvert) { "--on" } else { "--off" }
                    Field = "invert"
                    Expected = [bool]$snapshot.ChannelInvert
                },
                [pscustomobject]@{
                    Name = "vernier"
                    Command = "channel-vernier"
                    Action = if ($snapshot.ChannelVernier) { "--on" } else { "--off" }
                    Field = "vernier"
                    Expected = [bool]$snapshot.ChannelVernier
                }
            )) {
                $configured = Invoke-LiveCli -Stage "channel-$($item.Name)-set" `
                    -Command $item.Command -Arguments @("--channel", "1", $item.Action)
                $state = if ($item.Expected) { "ON" } else { "OFF" }
                $scpiPath = if ($item.Name -eq "invert") { "INVert" } else { "VERNier" }
                Assert-ScpiSent -Payload $configured -Label "CH1 $($item.Name) configure" `
                    -ExpectedCommands @(":CHANnel1:${scpiPath} ${state}")
                $readback = Invoke-LiveCli -Stage "channel-$($item.Name)-query" `
                    -Command $item.Command -Arguments @("--channel", "1", "--query")
                if ([bool]$readback.result.($item.Field) -ne $item.Expected) {
                    throw "CH1 $($item.Name) readback does not match the snapshot."
                }
            }

            $skewValue = ConvertTo-InvariantString -Value ([double]$snapshot.ChannelProbeSkew)
            $skewSet = Invoke-LiveCli -Stage "channel-probe-skew-set" `
                -Command "channel-probe-skew" `
                -Arguments @("--channel", "1", "--seconds", $skewValue)
            $skew = Invoke-LiveCli -Stage "channel-probe-skew-query" `
                -Command "channel-probe-skew" -Arguments @("--channel", "1", "--query")
            Assert-NearlyEqual -Actual ([double]$skew.result.probe_skew_seconds) `
                -Expected ([double]$snapshot.ChannelProbeSkew) -Label "CH1 probe skew"
            if (-not @($skewSet.scpi.sent | Where-Object {
                ([string]$_).StartsWith(":CHANnel1:PROBe:SKEW ")
            })) {
                throw "CH1 probe skew configure did not use the CH1 probe-skew SCPI path."
            }
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "display-settings" -Action {
            $labelAction = if ($snapshot.DisplayLabels) { "--on" } else { "--off" }
            $labelSet = Invoke-LiveCli -Stage "display-label-set" -Command "display-label" `
                -Arguments @($labelAction)
            Assert-ScpiSent -Payload $labelSet -Label "Display labels configure" `
                -ExpectedCommands @(
                    ":DISPlay:LABel $(if ($snapshot.DisplayLabels) { 'ON' } else { 'OFF' })"
                )
            $labels = Invoke-LiveCli -Stage "display-label-query" -Command "display-label" `
                -Arguments @("--query")
            if ([bool]$labels.result.display_label -ne $snapshot.DisplayLabels) {
                throw "Display-label readback does not match the snapshot."
            }

            $persistenceArguments = if ($null -ne $snapshot.DisplayPersistenceSeconds) {
                @(
                    "--seconds",
                    (ConvertTo-InvariantString -Value ([double]$snapshot.DisplayPersistenceSeconds))
                )
            } else {
                @("--mode", [string]$snapshot.DisplayPersistenceMode)
            }
            $persistenceSet = Invoke-LiveCli -Stage "display-persistence-set" `
                -Command "display-persistence" -Arguments $persistenceArguments
            $persistence = Invoke-LiveCli -Stage "display-persistence-query" `
                -Command "display-persistence" -Arguments @("--query")
            if ($null -ne $snapshot.DisplayPersistenceSeconds) {
                Assert-NearlyEqual -Actual ([double]$persistence.result.seconds) `
                    -Expected ([double]$snapshot.DisplayPersistenceSeconds) `
                    -Label "Display persistence"
            } elseif ([string]$persistence.result.mode -ne [string]$snapshot.DisplayPersistenceMode) {
                throw "Display-persistence mode does not match the snapshot."
            }
            if ($null -ne $snapshot.DisplayPersistenceSeconds) {
                if (-not @($persistenceSet.scpi.sent | Where-Object {
                    ([string]$_).StartsWith(":DISPlay:PERSistence ")
                })) {
                    throw "Display persistence configure did not use the persistence SCPI path."
                }
            } else {
                $persistenceToken = if ($snapshot.DisplayPersistenceMode -eq "minimum") {
                    "MINimum"
                } else {
                    "INFinite"
                }
                Assert-ScpiSent -Payload $persistenceSet -Label "Display persistence configure" `
                    -ExpectedCommands @(":DISPlay:PERSistence ${persistenceToken}")
            }

            $intensitySet = Invoke-LiveCli -Stage "display-intensity-set" `
                -Command "display-intensity" -Arguments @("--value", [string]$snapshot.DisplayIntensity)
            Assert-ScpiSent -Payload $intensitySet -Label "Display intensity configure" `
                -ExpectedCommands @(
                    ":DISPlay:INTensity:WAVeform $($snapshot.DisplayIntensity)"
                )
            $intensity = Invoke-LiveCli -Stage "display-intensity-query" `
                -Command "display-intensity" -Arguments @("--query")
            if ([int]$intensity.result.value -ne [int]$snapshot.DisplayIntensity) {
                throw "Display-intensity readback does not match the snapshot."
            }

            if ($snapshot.DisplayVectors) {
                $vectorsSet = Invoke-LiveCli -Stage "display-vectors-set" `
                    -Command "display-vectors" -Arguments @("--on")
                Assert-ScpiSent -Payload $vectorsSet -Label "Display vectors configure" `
                    -ExpectedCommands @(":DISPlay:VECTors ON")
            }
            $vectors = Invoke-LiveCli -Stage "display-vectors-query" `
                -Command "display-vectors" -Arguments @("--query")
            Assert-ScpiSent -Payload $vectors -Label "Display vectors query" `
                -ExpectedCommands @(":DISPlay:VECTors?")
            if ([bool]$vectors.result.value -ne [bool]$snapshot.DisplayVectors) {
                throw "Display-vectors readback does not match the snapshot."
            }
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.AnnotationRestorable) {
        Invoke-BaselineCase -Name "display-annotation" -Action {
            $annotation = Invoke-LiveCli -Stage "annotation-set" -Command "annotation" `
                -Arguments @("--slot", "1", "--on", "--text", "P2 live")
            Assert-ScpiSent -Payload $annotation -Label "Annotation configure" `
                -ExpectedCommands @($annotation.result.commands)
            $readback = Invoke-LiveCli -Stage "annotation-query" -Command "annotation" `
                -Arguments @("--slot", "1", "--query")
            Assert-ScpiSent -Payload $readback -Label "Annotation query" `
                -ExpectedCommands @($readback.result.commands)
            if (-not [bool]$readback.result.enabled -or
                [string]$readback.result.text -ne "P2 live" -or
                [int]$readback.result.slot -ne 1) {
                throw "Annotation slot 1 readback does not match the representative state."
            }
        }
    } elseif (-not $script:FunctionalFailed) {
        Write-Host "SKIP  display-annotation (slot 1 cannot be safely restored)"
    }

    $supportsEdgeSearch = "edge" -in @($identity.capabilities.search_modes)
    if (-not $script:FunctionalFailed -and $supportsEdgeSearch -and $snapshot.SearchRestorable) {
        Invoke-BaselineCase -Name "search-basic" -Action {
            $enabled = Invoke-LiveCli -Stage "search-state-enable" -Command "search-state" `
                -Arguments @("--enabled", "true")
            Assert-ScpiSent -Payload $enabled -Label "Search state configure" `
                -ExpectedCommands @(":SEARch:STATe 1")
            $modeSet = Invoke-LiveCli -Stage "search-mode-edge-set" -Command "search-mode" `
                -Arguments @("--mode", "edge")
            Assert-ScpiSent -Payload $modeSet -Label "Search mode configure" `
                -ExpectedCommands @(":SEARch:STATe 1", ":SEARch:MODE EDGE")

            $state = Invoke-LiveCli -Stage "search-state-query" -Command "search-state" `
                -Arguments @("--query")
            $mode = Invoke-LiveCli -Stage "search-mode-query" -Command "search-mode" `
                -Arguments @("--query")
            if (-not [bool]$state.result.enabled -or
                -not [bool]$mode.result.enabled -or
                [string]$mode.result.mode -ne "edge") {
                throw "Search readback did not report enabled Edge mode."
            }
            $count = Invoke-LiveCli -Stage "search-count-query" -Command "search-count" `
                -Arguments @("--query")
            Assert-ScpiSent -Payload $count -Label "Search count query" `
                -ExpectedCommands @(":SEARch:COUNt?")
            if ([int64]$count.result.count -lt 0) {
                throw "Search count must be zero or greater."
            }

            if ([bool]$identity.capabilities.supports_search_event_navigation) {
                $event = Invoke-LiveCli -Stage "search-event-query" -Command "search-event" `
                    -Arguments @("--query")
                Assert-ScpiSent -Payload $event -Label "Search event query" `
                    -ExpectedCommands @(":SEARch:EVENt?")
                if ([int64]$event.result.event -lt 0) {
                    throw "Search event must be zero or greater."
                }
            }
        }
    } elseif (-not $script:FunctionalFailed) {
        Write-Host "SKIP  search-basic (non-Serial mode cannot be safely restored)"
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

    if (-not $script:FunctionalFailed -and
        [bool]$identity.capabilities.supports_screenshot_format_pack) {
        Invoke-BaselineCase -Name "screenshot-bmp" -Action {
            $screenshotPath = Join-Path $liveArtifactRoot "screenshot.bmp"
            $screenshot = Invoke-LiveCli -Stage "screenshot-bmp" -Command "screenshot" `
                -Arguments @("--format", "bmp", "--output", $screenshotPath)
            Assert-ScpiSent -Payload $screenshot -Label "BMP screenshot" `
                -ExpectedCommands @(":HCOPY:SDUMp:DATA? BMP")
            if ([string]$screenshot.result.format -ne "BMP" -or
                [int]$screenshot.result.byte_count -le 0 -or
                [string]$screenshot.result.image_path -ne $screenshotPath) {
                throw "BMP screenshot result metadata is invalid."
            }
            Assert-FileNonEmpty -Path $screenshotPath -Label "BMP screenshot"
        }
    } elseif (-not $script:FunctionalFailed) {
        Write-Host "SKIP  screenshot-bmp (format pack not supported)"
    }

    if (-not $script:FunctionalFailed) {
        Invoke-BaselineCase -Name "waveform-amp" -Action {
            $originalUnits = [string]$snapshot.ChannelUnits
            try {
                $unitSet = Invoke-LiveCli -Stage "waveform-amp-unit-set" `
                    -Command "channel-units" -Arguments @("--channel", "1", "--units", "amp")
                Assert-ScpiSent -Payload $unitSet -Label "CH1 AMP unit configure" `
                    -ExpectedCommands @(":CHANnel1:UNITs AMP")
                $unit = Invoke-LiveCli -Stage "waveform-amp-unit-query" `
                    -Command "channel-units" -Arguments @("--channel", "1", "--query")
                Assert-ScpiSent -Payload $unit -Label "CH1 AMP unit query" `
                    -ExpectedCommands @(":CHANnel1:UNITs?")
                if ([string]$unit.result.units -ne "amp") {
                    throw "CH1 unit readback did not report amp."
                }

                $csvPath = Join-Path $liveArtifactRoot "waveform-amp.csv"
                $metadataPath = Join-Path $liveArtifactRoot "waveform-amp-meta.json"
                $capture = Invoke-LiveCli -Stage "waveform-amp-capture" -Command "capture" `
                    -Arguments @(
                        "--channel", "1", "--points", "1000", "--format", "byte",
                        "--csv", $csvPath, "--meta", $metadataPath
                    )
                Assert-ScpiSent -Payload $capture -Label "AMP waveform capture" `
                    -ExpectedCommands @(
                        ":CHANnel1:UNITs?",
                        ":WAVeform:FORMat BYTE",
                        ":WAVeform:DATA?"
                    )
                Assert-Capture -Payload $capture -ExpectedFormat "BYTE" `
                    -CsvPath $csvPath -MetadataPath $metadataPath -ExpectedVerticalUnit "A"
                $csvHeader = [string](Get-Content -LiteralPath $csvPath -TotalCount 1)
                if ($csvHeader -ne "time_s,ch1_a") {
                    throw "AMP waveform CSV header is ${csvHeader}; expected time_s,ch1_a."
                }
            } finally {
                $restore = Invoke-LiveCli -Stage "waveform-amp-unit-restore" `
                    -Command "channel-units" `
                    -Arguments @("--channel", "1", "--units", $originalUnits)
                Assert-ScpiSent -Payload $restore -Label "CH1 unit restore" `
                    -ExpectedCommands @([string]$restore.result.command)
                $restored = Invoke-LiveCli -Stage "waveform-amp-unit-restore-query" `
                    -Command "channel-units" -Arguments @("--channel", "1", "--query")
                if ([string]$restored.result.units -ne $originalUnits) {
                    throw "CH1 unit restore readback does not match ${originalUnits}."
                }
            }
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-edge-settings" -Action {
            $couplingSet = Invoke-LiveCli -Stage "trigger-edge-coupling-set" `
                -Command "trigger-edge-coupling" `
                -Arguments @("--coupling", [string]$snapshot.TriggerEdgeCoupling)
            Assert-ScpiSentPrefix -Payload $couplingSet `
                -ExpectedPrefix ":TRIGger:EDGE:COUPling " -Label "Edge coupling"
            $coupling = Invoke-LiveCli -Stage "trigger-edge-coupling-query" `
                -Command "trigger-edge-coupling" -Arguments @("--query")
            $rejectSet = Invoke-LiveCli -Stage "trigger-edge-reject-set" `
                -Command "trigger-edge-reject" `
                -Arguments @("--reject", [string]$snapshot.TriggerEdgeReject)
            Assert-ScpiSentPrefix -Payload $rejectSet `
                -ExpectedPrefix ":TRIGger:EDGE:REJect " -Label "Edge reject"
            $reject = Invoke-LiveCli -Stage "trigger-edge-reject-query" `
                -Command "trigger-edge-reject" -Arguments @("--query")
            if ([string]$coupling.result.coupling -ne [string]$snapshot.TriggerEdgeCoupling -or
                [string]$reject.result.reject -ne [string]$snapshot.TriggerEdgeReject) {
                throw "Edge coupling/reject readback does not match the snapshot."
            }
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-common" -Action {
            $sweepSet = Invoke-LiveCli -Stage "trigger-sweep-set" -Command "trigger-sweep" `
                -Arguments @("--mode", [string]$snapshot.TriggerSweep)
            Assert-ScpiSentPrefix -Payload $sweepSet -ExpectedPrefix ":TRIGger:SWEep " `
                -Label "Trigger sweep"
            $noiseSet = Invoke-LiveCli -Stage "trigger-noise-set" `
                -Command "trigger-noise-reject" -Arguments @(
                    "--enabled", ([string][bool]$snapshot.TriggerNoiseReject).ToLowerInvariant()
                )
            Assert-ScpiSentPrefix -Payload $noiseSet -ExpectedPrefix ":TRIGger:NREJect " `
                -Label "Trigger noise reject"
            $hfSet = Invoke-LiveCli -Stage "trigger-hf-set" -Command "trigger-hf-reject" `
                -Arguments @(
                    "--enabled", ([string][bool]$snapshot.TriggerHfReject).ToLowerInvariant()
                )
            Assert-ScpiSentPrefix -Payload $hfSet -ExpectedPrefix ":TRIGger:HFReject " `
                -Label "Trigger HF reject"
            $sweep = Invoke-LiveCli -Stage "trigger-sweep-query" `
                -Command "trigger-sweep" -Arguments @("--query")
            $noise = Invoke-LiveCli -Stage "trigger-noise-query" `
                -Command "trigger-noise-reject" -Arguments @("--query")
            $hf = Invoke-LiveCli -Stage "trigger-hf-query" `
                -Command "trigger-hf-reject" -Arguments @("--query")
            if ([string]$sweep.result.mode -ne [string]$snapshot.TriggerSweep -or
                [bool]$noise.result.enabled -ne [bool]$snapshot.TriggerNoiseReject -or
                [bool]$hf.result.enabled -ne [bool]$snapshot.TriggerHfReject) {
                throw "Common trigger settings readback does not match the snapshot."
            }
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-external" -Action {
            $rangeSet = Invoke-LiveCli -Stage "external-trigger-range-set" `
                -Command "external-trigger-range" -Arguments @(
                    "--range-volts",
                    (ConvertTo-InvariantString -Value ([double]$snapshot.ExternalTriggerRange))
                )
            Assert-ScpiSentPrefix -Payload $rangeSet -ExpectedPrefix ":EXTernal:RANGe " `
                -Label "External trigger range"
            $probeSet = Invoke-LiveCli -Stage "external-trigger-probe-set" `
                -Command "external-trigger-probe" -Arguments @(
                    "--attenuation",
                    (ConvertTo-InvariantString -Value ([double]$snapshot.ExternalTriggerProbe))
                )
            Assert-ScpiSentPrefix -Payload $probeSet -ExpectedPrefix ":EXTernal:PROBe " `
                -Label "External trigger probe"
            $unitsSet = Invoke-LiveCli -Stage "external-trigger-units-set" `
                -Command "external-trigger-units" `
                -Arguments @("--units", [string]$snapshot.ExternalTriggerUnits)
            Assert-ScpiSentPrefix -Payload $unitsSet -ExpectedPrefix ":EXTernal:UNITs " `
                -Label "External trigger units"
            $levelSet = Invoke-LiveCli -Stage "external-trigger-level-set" `
                -Command "trigger-edge-external-level" -Arguments @(
                    "--level-volts",
                    (ConvertTo-InvariantString -Value ([double]$snapshot.ExternalTriggerLevel))
                )
            Assert-ScpiSentPrefix -Payload $levelSet `
                -ExpectedPrefix ":TRIGger:EDGE:LEVel " `
                -Label "External Edge level"
            if (-not (@($levelSet.scpi.sent) | Where-Object {
                [string]$_ -like ":TRIGger:EDGE:LEVel *,EXTernal"
            })) {
                throw "External Edge level setter did not use External-qualified SCPI."
            }
            $readback = Invoke-LiveCli -Stage "external-trigger-query" `
                -Command "external-trigger-settings" -Arguments @("--query")
            $levelReadback = Invoke-LiveCli -Stage "external-trigger-level-query" `
                -Command "trigger-edge-external-level" -Arguments @("--query")
            Assert-ScpiSent -Payload $levelReadback -Label "External Edge level query" `
                -ExpectedCommands @(":TRIGger:EDGE:LEVel? EXTernal")
            Assert-NearlyEqual -Actual ([double]$readback.result.range_value) `
                -Expected ([double]$snapshot.ExternalTriggerRange) `
                -Label "External trigger range"
            Assert-NearlyEqual -Actual ([double]$readback.result.probe_attenuation) `
                -Expected ([double]$snapshot.ExternalTriggerProbe) `
                -Label "External trigger probe"
            if ([string]$readback.result.units -ne [string]$snapshot.ExternalTriggerUnits) {
                throw "External trigger units readback does not match the snapshot."
            }
            Assert-NearlyEqual -Actual ([double]$levelReadback.result.level_volts) `
                -Expected ([double]$snapshot.ExternalTriggerLevel) `
                -Label "External Edge level"
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-pulse-width" -Action {
            $configured = Invoke-LiveCli -Stage "trigger-pulse-width-set" `
                -Command "trigger-pulse-width" -Arguments @(
                    "--channel", "1", "--polarity", "positive", "--qualifier", "greater-than",
                    "--time-seconds", "0.000001", "--level-volts", "0"
                )
            Assert-ScpiSent -Payload $configured -Label "Pulse-width trigger mode" `
                -ExpectedCommands @(":TRIGger:MODE GLITch")
            Assert-ScpiSentPrefix -Payload $configured -ExpectedPrefix ":TRIGger:GLITch:" `
                -Label "Pulse-width trigger subtree"
            $readback = Invoke-LiveCli -Stage "trigger-pulse-width-query" `
                -Command "trigger-pulse-width" -Arguments @("--query")
            if ([string]$readback.result.mode -ne "glitch" -or
                [int]$readback.result.channel -ne 1 -or
                [string]$readback.result.qualifier -ne "greater-than") {
                throw "Pulse-width trigger readback is invalid."
            }
            Restore-EdgeTriggerBaseline -LevelVolts $snapshot.TriggerLevel `
                -Stage "trigger-pulse-width-edge-reset"
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-runt" -Action {
            $configured = Invoke-LiveCli -Stage "trigger-runt-set" -Command "trigger-runt" `
                -Arguments @(
                    "--channel", "1", "--polarity", "positive", "--qualifier", "none",
                    "--low-level-volts", "-0.5", "--high-level-volts", "0.5"
                )
            Assert-ScpiSent -Payload $configured -Label "Runt trigger mode" `
                -ExpectedCommands @(":TRIGger:MODE RUNT")
            Assert-ScpiSentPrefix -Payload $configured -ExpectedPrefix ":TRIGger:RUNT:" `
                -Label "Runt trigger subtree"
            $readback = Invoke-LiveCli -Stage "trigger-runt-query" `
                -Command "trigger-runt" -Arguments @("--query")
            if ([string]$readback.result.mode -ne "runt" -or
                [int]$readback.result.channel -ne 1 -or
                [string]$readback.result.polarity -ne "positive") {
                throw "Runt trigger readback is invalid."
            }
            Restore-EdgeTriggerBaseline -LevelVolts $snapshot.TriggerLevel `
                -Stage "trigger-runt-edge-reset"
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-transition" -Action {
            $configured = Invoke-LiveCli -Stage "trigger-transition-set" `
                -Command "trigger-transition" -Arguments @(
                    "--channel", "1", "--slope", "positive", "--qualifier", "greater-than",
                    "--time-seconds", "0.000001", "--low-level-volts", "-0.5",
                    "--high-level-volts", "0.5"
                )
            Assert-ScpiSent -Payload $configured -Label "Transition trigger mode" `
                -ExpectedCommands @(":TRIGger:MODE TRANsition")
            Assert-ScpiSentPrefix -Payload $configured -ExpectedPrefix ":TRIGger:TRANsition:" `
                -Label "Transition trigger subtree"
            $readback = Invoke-LiveCli -Stage "trigger-transition-query" `
                -Command "trigger-transition" -Arguments @("--query")
            if ([string]$readback.result.mode -ne "transition" -or
                [int]$readback.result.channel -ne 1 -or
                [string]$readback.result.slope -ne "positive") {
                throw "Transition trigger readback is invalid."
            }
            Restore-EdgeTriggerBaseline -LevelVolts $snapshot.TriggerLevel `
                -Stage "trigger-transition-edge-reset"
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-delay" -Action {
            $configured = Invoke-LiveCli -Stage "trigger-delay-set" -Command "trigger-delay" `
                -Arguments @(
                    "--arm-channel", "1", "--arm-slope", "positive",
                    "--trigger-channel", "2", "--trigger-slope", "positive",
                    "--time-seconds", "0.000001", "--count", "2"
                )
            Assert-ScpiSent -Payload $configured -Label "Delay trigger mode" `
                -ExpectedCommands @(":TRIGger:MODE DELay")
            Assert-ScpiSentPrefix -Payload $configured -ExpectedPrefix ":TRIGger:DELay:" `
                -Label "Delay trigger subtree"
            $readback = Invoke-LiveCli -Stage "trigger-delay-query" `
                -Command "trigger-delay" -Arguments @("--query")
            if ([string]$readback.result.mode -ne "delay" -or
                [int]$readback.result.arm_channel -ne 1 -or
                [int]$readback.result.trigger_channel -ne 2 -or
                [int]$readback.result.count -ne 2) {
                throw "Delay trigger readback is invalid."
            }
            Restore-EdgeTriggerBaseline -LevelVolts $snapshot.TriggerLevel `
                -Stage "trigger-delay-edge-reset"
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-setup-hold" -Action {
            $configured = Invoke-LiveCli -Stage "trigger-setup-hold-set" `
                -Command "trigger-setup-hold" -Arguments @(
                    "--clock-channel", "1", "--data-channel", "2", "--slope", "positive",
                    "--setup-time", "0.000000001", "--hold-time", "0.000000001"
                )
            Assert-ScpiSent -Payload $configured -Label "Setup/hold trigger mode" `
                -ExpectedCommands @(":TRIGger:MODE SHOLd")
            Assert-ScpiSentPrefix -Payload $configured -ExpectedPrefix ":TRIGger:SHOLd:" `
                -Label "Setup/hold trigger subtree"
            $readback = Invoke-LiveCli -Stage "trigger-setup-hold-query" `
                -Command "trigger-setup-hold" -Arguments @("--query")
            if ([string]$readback.result.mode -ne "setup-hold" -or
                [int]$readback.result.clock_channel -ne 1 -or
                [int]$readback.result.data_channel -ne 2) {
                throw "Setup/hold trigger readback is invalid."
            }
            Restore-EdgeTriggerBaseline -LevelVolts $snapshot.TriggerLevel `
                -Stage "trigger-setup-hold-edge-reset"
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-edge-burst" -Action {
            $configured = Invoke-LiveCli -Stage "trigger-edge-burst-set" `
                -Command "trigger-edge-burst" -Arguments @(
                    "--source-channel", "1", "--slope", "positive", "--count", "2",
                    "--idle-time", "0.000001", "--level-volts", "0"
                )
            Assert-ScpiSent -Payload $configured -Label "Nth Edge Burst mode" `
                -ExpectedCommands @(":TRIGger:MODE EBURst")
            Assert-ScpiSentPrefix -Payload $configured -ExpectedPrefix ":TRIGger:EBURst:" `
                -Label "Nth Edge Burst subtree"
            $readback = Invoke-LiveCli -Stage "trigger-edge-burst-query" `
                -Command "trigger-edge-burst" -Arguments @("--query")
            if ([string]$readback.result.mode -ne "edge-burst" -or
                [int]$readback.result.source_channel -ne 1 -or
                [int]$readback.result.count -ne 2) {
                throw "Nth Edge Burst trigger readback is invalid."
            }
            Restore-EdgeTriggerBaseline -LevelVolts $snapshot.TriggerLevel `
                -Stage "trigger-edge-burst-edge-reset"
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-tv" -Action {
            $configured = Invoke-LiveCli -Stage "trigger-tv-set" -Command "trigger-tv" `
                -Arguments @(
                    "--source-channel", "1", "--standard", "ntsc",
                    "--mode", "all-lines", "--polarity", "positive"
                )
            Assert-ScpiSent -Payload $configured -Label "TV trigger mode" `
                -ExpectedCommands @(":TRIGger:MODE TV")
            Assert-ScpiSentPrefix -Payload $configured -ExpectedPrefix ":TRIGger:TV:" `
                -Label "TV trigger subtree"
            $readback = Invoke-LiveCli -Stage "trigger-tv-query" `
                -Command "trigger-tv" -Arguments @("--query")
            if ([string]$readback.result.mode -ne "tv" -or
                [int]$readback.result.source_channel -ne 1 -or
                [string]$readback.result.standard -ne "ntsc" -or
                [string]$readback.result.tv_mode -ne "all-lines") {
                throw "TV trigger readback is invalid."
            }
            Restore-EdgeTriggerBaseline -LevelVolts $snapshot.TriggerLevel `
                -Stage "trigger-tv-edge-reset"
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-pattern" -Action {
            $configured = Invoke-LiveCli -Stage "trigger-pattern-set" `
                -Command "trigger-pattern" -Arguments @("--pattern", "XXX1")
            Assert-ScpiSent -Payload $configured -Label "Pattern trigger mode" `
                -ExpectedCommands @(":TRIGger:MODE PATTern")
            Assert-ScpiSentPrefix -Payload $configured -ExpectedPrefix ":TRIGger:PATTern" `
                -Label "Pattern trigger subtree"
            $readback = Invoke-LiveCli -Stage "trigger-pattern-query" `
                -Command "trigger-pattern" -Arguments @("--query")
            if ([string]$readback.result.mode -ne "pattern" -or
                [string]$readback.result.pattern -ne "XXX1") {
                throw "Pattern trigger readback is invalid."
            }
            Restore-EdgeTriggerBaseline -LevelVolts $snapshot.TriggerLevel `
                -Stage "trigger-pattern-edge-reset"
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "trigger-or" -Action {
            $configured = Invoke-LiveCli -Stage "trigger-or-set" `
                -Command "trigger-or" -Arguments @("--pattern", "XXXR")
            Assert-ScpiSent -Payload $configured -Label "OR trigger mode" `
                -ExpectedCommands @(":TRIGger:MODE OR")
            Assert-ScpiSentPrefix -Payload $configured -ExpectedPrefix ":TRIGger:OR " `
                -Label "OR trigger subtree"
            $readback = Invoke-LiveCli -Stage "trigger-or-query" `
                -Command "trigger-or" -Arguments @("--query")
            if ([string]$readback.result.mode -ne "or" -or
                [string]$readback.result.pattern -ne "XXXR") {
                throw "OR trigger readback is invalid."
            }
            Restore-EdgeTriggerBaseline -LevelVolts $snapshot.TriggerLevel `
                -Stage "trigger-or-edge-reset"
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "math-operator" -Action {
            $configured = Invoke-LiveCli -Stage "math-operator-set" `
                -Command "math-operator" -Arguments @(
                    "--function", "1", "--operation", "add",
                    "--source1", "channel1", "--source2", "channel2"
                )
            Assert-ScpiSent -Payload $configured -Label "Math operator" `
                -ExpectedCommands @(
                    ":FUNCtion1:OPERation ADD",
                    ":FUNCtion1:SOURce1 CHANnel1",
                    ":FUNCtion1:SOURce2 CHANnel2"
                )
            $readback = Invoke-LiveCli -Stage "math-operator-query" `
                -Command "math-operator" -Arguments @("--function", "1", "--query")
            if ([string]$readback.result.math_operation -ne "add" -or
                [string]$readback.result.source1 -ne "channel1" -or
                [string]$readback.result.source2 -ne "channel2") {
                throw "Math operator readback is invalid."
            }
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "math-transform" -Action {
            $configured = Invoke-LiveCli -Stage "math-transform-set" `
                -Command "math-transform" -Arguments @(
                    "--function", "1", "--operation", "absolute", "--source", "channel1"
                )
            Assert-ScpiSent -Payload $configured -Label "Math transform" `
                -ExpectedCommands @(
                    ":FUNCtion1:OPERation ABSolute",
                    ":FUNCtion1:SOURce1 CHANnel1"
                )
            $readback = Invoke-LiveCli -Stage "math-transform-query" `
                -Command "math-transform" -Arguments @("--function", "1", "--query")
            if ([string]$readback.result.math_operation -ne "absolute" -or
                [string]$readback.result.source -ne "channel1") {
                throw "Math transform readback is invalid."
            }
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "fft" -Action {
            $configured = Invoke-LiveCli -Stage "fft-set" -Command "fft" -Arguments @(
                "--function", "1", "--source-channel", "1", "--units", "decibel",
                "--window", "hanning", "--display", "on"
            )
            Assert-ScpiSent -Payload $configured -Label "FFT configure" -ExpectedCommands @(
                ":FUNCtion1:OPERation FFT",
                ":FUNCtion1:SOURce1 CHANnel1",
                ":FUNCtion1:FFT:WINDow HANNing"
            )
            $readback = Invoke-LiveCli -Stage "fft-query" `
                -Command "fft" -Arguments @("--function", "1", "--query")
            Assert-ScpiSent -Payload $readback -Label "FFT query" -ExpectedCommands @(
                ":FUNCtion1:OPERation?",
                ":FUNCtion1:SOURce1?",
                ":FUNCtion1:FFT:WINDow?"
            )
            $window = ([string]$readback.result.window).Trim().ToUpperInvariant()
            if ([string]$readback.result.fft_operation_canonical -ne "fft" -or
                [int]$readback.result.source_channel -ne 1 -or
                $window -ne "HANN") {
                throw "FFT readback is invalid."
            }
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "wgen-basic" -Action {
            try {
                Invoke-LiveCli -Stage "wgen-function-set" -Command "wgen-function" `
                    -Arguments @("--function", "sine") | Out-Null
                Invoke-LiveCli -Stage "wgen-frequency-set" -Command "wgen-frequency" `
                    -Arguments @("--hz", "1000") | Out-Null
                Invoke-LiveCli -Stage "wgen-voltage-set" -Command "wgen-voltage" `
                    -Arguments @("--amplitude", "0.5") | Out-Null
                Invoke-LiveCli -Stage "wgen-offset-set" -Command "wgen-offset" `
                    -Arguments @("--volts", "0") | Out-Null
                Invoke-LiveCli -Stage "wgen-load-set" -Command "wgen-load" `
                    -Arguments @("--load", "one-meg") | Out-Null
                $enabled = Invoke-LiveCli -Stage "wgen-output-on" -Command "wgen-output" `
                    -Arguments @("--enabled", "true")
                Assert-ScpiSent -Payload $enabled -Label "WGEN output enable" `
                    -ExpectedCommands @(":WGEN1:OUTPut ON")
                $readback = Invoke-LiveCli -Stage "wgen-query" -Command "wgen-query"
                if (-not [bool]$readback.result.enabled -or
                    [string]$readback.result.function -ne "sine" -or
                    [string]$readback.result.load -ne "one-meg") {
                    throw "WGEN readback is invalid."
                }
                Assert-NearlyEqual -Actual ([double]$readback.result.frequency_hz) `
                    -Expected 1000 -Label "WGEN frequency"
                Assert-NearlyEqual -Actual ([double]$readback.result.amplitude_volts) `
                    -Expected 0.5 -Label "WGEN amplitude"
            } finally {
                $off = Invoke-LiveCli -Stage "wgen-output-off" -Command "wgen-output" `
                    -Arguments @("--enabled", "false")
                Assert-ScpiSent -Payload $off -Label "WGEN output disable" `
                    -ExpectedCommands @(":WGEN1:OUTPut OFF")
            }
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "demo-basic" -Action {
            try {
                $function = Invoke-LiveCli -Stage "demo-function-set" `
                    -Command "demo-function" -Arguments @("--function", "sine")
                Assert-ScpiSent -Payload $function -Label "DEMO function" `
                    -ExpectedCommands @(":DEMO:FUNCtion SIN")
                Invoke-LiveCli -Stage "demo-output-on" -Command "demo-output" `
                    -Arguments @("--enabled", "true") | Out-Null
                $readback = Invoke-LiveCli -Stage "demo-query" -Command "demo-query"
                if (-not [bool]$readback.result.enabled -or
                    [string]$readback.result.function -ne "sine") {
                    throw "DEMO readback is invalid."
                }
            } finally {
                $off = Invoke-LiveCli -Stage "demo-output-off" -Command "demo-output" `
                    -Arguments @("--enabled", "false")
                Assert-ScpiSent -Payload $off -Label "DEMO output disable" `
                    -ExpectedCommands @(":DEMO:OUTPut OFF")
            }
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "autoscale" -Action {
            $autoscale = Invoke-LiveCli -Stage "autoscale-ch1" -Command "autoscale" `
                -Arguments @("--source-channel", "1")
            Assert-ScpiSent -Payload $autoscale -Label "CH1 autoscale" `
                -ExpectedCommands @(":AUToscale CHANnel1")
            Restore-InstrumentState -Snapshot $snapshot
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "setup-lifecycle" -Action {
            $setupFile = "\usb\scopes-tool-live-${timestamp}.scp"
            $saved = Invoke-LiveCli -Stage "setup-save" -Command "setup-save" `
                -Arguments @("--file", $setupFile)
            Assert-ScpiSentPrefix -Payload $saved -ExpectedPrefix ':SAVE:SETup "\usb\scopes-tool-live-' `
                -Label "Setup save"
            Invoke-LiveCli -Stage "setup-label-change" -Command "channel-label" `
                -Arguments @("--channel", "1", "--text", "P3 recall") | Out-Null
            $changed = Invoke-LiveCli -Stage "setup-label-change-query" `
                -Command "channel-label" -Arguments @("--channel", "1", "--query")
            if ([string]$changed.result.text -ne "P3 recall") {
                throw "Setup lifecycle change was not applied."
            }
            $recalled = Invoke-LiveCli -Stage "setup-recall" -Command "setup-recall" `
                -Arguments @("--file", $setupFile)
            Assert-ScpiSentPrefix -Payload $recalled -ExpectedPrefix ':RECall:SETup "\usb\scopes-tool-live-' `
                -Label "Setup recall"
            $restored = Invoke-LiveCli -Stage "setup-label-restore-query" `
                -Command "channel-label" -Arguments @("--channel", "1", "--query")
            if ([string]$restored.result.text -ne [string]$snapshot.ChannelLabel) {
                throw "Setup recall did not restore the CH1 label."
            }
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "save-export" -Action {
            $primaryException = $null
            $firstRestoreException = $null
            try {
                if ([bool]$snapshot.SaveWaveformLengthMax) {
                    throw (
                        "Save/export acceptance prerequisite failed: " +
                        "maximum waveform save length is enabled; " +
                        "the 1000-point CSV path was not executed."
                    )
                }
                $imageFile = "\usb\scopes-tool-live-${timestamp}.png"
                $waveformFile = "\usb\scopes-tool-live-${timestamp}.csv"
                Invoke-LiveCli -Stage "save-image-format-png" -Command "save-image-format" `
                    -Arguments @("--format", "png") | Out-Null
                $image = Invoke-LiveCli -Stage "save-image" -Command "save-image" `
                    -Arguments @("--filename", $imageFile)
                Assert-ScpiSentPrefix -Payload $image -ExpectedPrefix ':SAVE:IMAGe "\usb\scopes-tool-live-' `
                    -Label "Instrument image save"
                if (-not [bool]$image.result.instrument_side -or
                    -not [bool]$image.result.operation_complete -or
                    [string]$image.result.filename -ne $imageFile) {
                    throw "Instrument image save result is invalid."
                }
                Invoke-LiveCli -Stage "save-waveform-format-csv" `
                    -Command "save-waveform-format" -Arguments @("--format", "csv") | Out-Null
                Invoke-LiveCli -Stage "save-waveform-length-1000" `
                    -Command "save-waveform-length" -Arguments @("--points", "1000") | Out-Null
                $waveform = Invoke-LiveCli -Stage "save-waveform" -Command "save-waveform" `
                    -Arguments @("--filename", $waveformFile)
                Assert-ScpiSentPrefix -Payload $waveform `
                    -ExpectedPrefix ':SAVE:WAVeform "\usb\scopes-tool-live-' `
                    -Label "Instrument waveform save"
                if (-not [bool]$waveform.result.instrument_side -or
                    -not [bool]$waveform.result.operation_complete -or
                    [string]$waveform.result.filename -ne $waveformFile) {
                    throw "Instrument waveform save result is invalid."
                }
            } catch {
                $primaryException = $_.Exception
            } finally {
                if ([string]$snapshot.SaveImageFormat -in @("png", "bmp", "bmp8", "bmp24")) {
                    try {
                        Invoke-LiveCli -Stage "save-image-format-restore" `
                            -Command "save-image-format" `
                            -Arguments @("--format", [string]$snapshot.SaveImageFormat) | Out-Null
                    } catch {
                        if ($null -eq $firstRestoreException) {
                            $firstRestoreException = $_.Exception
                        }
                        Add-Diagnostic -Name "save-export" -Message (
                            "image format restore failed: $($_.Exception.Message)"
                        )
                    }
                }
                if ([string]$snapshot.SaveWaveformFormat -in @("ascii-xy", "csv", "binary")) {
                    try {
                        Invoke-LiveCli -Stage "save-waveform-format-restore" `
                            -Command "save-waveform-format" `
                            -Arguments @("--format", [string]$snapshot.SaveWaveformFormat) | Out-Null
                    } catch {
                        if ($null -eq $firstRestoreException) {
                            $firstRestoreException = $_.Exception
                        }
                        Add-Diagnostic -Name "save-export" -Message (
                            "waveform format restore failed: $($_.Exception.Message)"
                        )
                    }
                }
                if ([int]$snapshot.SaveWaveformLength -gt 0) {
                    try {
                        Invoke-LiveCli -Stage "save-waveform-length-restore" `
                            -Command "save-waveform-length" `
                            -Arguments @("--points", [string]$snapshot.SaveWaveformLength) | Out-Null
                    } catch {
                        if ($null -eq $firstRestoreException) {
                            $firstRestoreException = $_.Exception
                        }
                        Add-Diagnostic -Name "save-export" -Message (
                            "waveform length restore failed: $($_.Exception.Message)"
                        )
                    }
                }
            }
            if ($null -ne $primaryException) {
                throw $primaryException
            }
            if ($null -ne $firstRestoreException) {
                throw $firstRestoreException
            }
        }
    }

    if (-not $script:FunctionalFailed -and $snapshot.P3Enabled) {
        Invoke-BaselineCase -Name "safe-cleanup" -Action {
            $cleanup = Invoke-LiveCli -Stage "safe-cleanup" -Command "cleanup" `
                -Arguments @("--profile", "safe")
            if ([string]$cleanup.result.profile -ne "safe" -or
                -not [bool]$cleanup.result.final_error_queue_clean -or
                "final_error_check" -notin @($cleanup.result.actions) -or
                "disable_dvm" -notin @($cleanup.result.actions) -or
                "disable_demo_output" -notin @($cleanup.result.actions)) {
                throw "Safe cleanup result is invalid."
            }
            $wgenSkip = @($cleanup.result.skipped | Where-Object {
                [string]$_.action -eq "disable_wgen" -and
                [string]$_.reason -eq "wgen_not_implemented"
            })
            if ($wgenSkip.Count -ne 1) {
                throw "Safe cleanup did not report the expected WGEN skip."
            }
            Assert-ScpiSent -Payload $cleanup -Label "Safe cleanup" `
                -ExpectedCommands @(
                    "*CLS", ":DISPlay:CLEar", ":DVM:ENABle 0",
                    ":DEMO:OUTPut OFF", "*OPC?", ":SYSTem:ERRor?"
                )
        }
    } elseif (-not $script:FunctionalFailed) {
        Write-Host "SKIP  P3 coverage (representative cases require detected 4000X capabilities)"
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
    if ($finalDrain.Errors.Count -gt 0) {
        Write-DrainErrors -Errors $finalDrain.Errors -CaseName "final-error-queue"
    }
    if (-not $finalDrain.Terminated) {
        throw "Final error queue did not reach code 0 within 30 reads."
    }
    if ($finalDrain.Errors.Count -gt 0) {
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
Write-Host "  - Cursor and trigger holdoff are not changed because their current public"
Write-Host "    query surfaces do not expose all state required for safe restoration."
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
