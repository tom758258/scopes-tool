[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $Resource,

    [string] $Python = ".\.venv\Scripts\python.exe",

    [string] $OutputRoot = ".tmp_tests\live_dvm_check"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:CliInvocationIndex = 0
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DvmUnavailable = $false

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
        [ValidateSet("PASS", "FAIL", "SKIP")]
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

    $stdoutLines = @(& $Python -m scopes_tool_cli.cli @Arguments 2> $stderrPath)
    $exitCode = $LASTEXITCODE
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
    $resultProperty = $invocation.Payload.PSObject.Properties["result"]
    if ($null -eq $resultProperty -or $null -eq $resultProperty.Value) {
        throw "${Stage}: check-error JSON did not contain result data."
    }
    $entriesProperty = $resultProperty.Value.PSObject.Properties["entries"]
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
        [object[]] $Errors
    )

    foreach ($entry in $Errors) {
        Write-Host "      system error $($entry.code): $($entry.message)"
    }
}

function Drain-AfterFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage
    )

    try {
        $drain = Get-ErrorDrain -Stage $Stage
        Write-DrainErrors -Errors $drain.Errors
        if (-not $drain.Terminated) {
            Write-Host "      error queue did not reach code 0 within 30 reads"
        }
    } catch {
        Write-Host "      diagnostic error drain failed: $($_.Exception.Message)"
    }
}

function Assert-FiniteNumber {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Value,

        [Parameter(Mandatory = $true)]
        [string] $Label
    )

    if ($null -eq $Value) {
        throw "${Label} is null."
    }
    $number = [double]$Value
    if ([double]::IsNaN($number) -or [double]::IsInfinity($number)) {
        throw "${Label} is not finite: ${Value}"
    }
    return $number
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

function Get-DvmSnapshot {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload,

        [string] $Stage = "DVM snapshot"
    )

    $enabled = Get-RequiredResultValue -Payload $Payload -Name "enabled" -Stage $Stage
    $sourceChannel = Get-RequiredResultValue `
        -Payload $Payload -Name "source_channel" -Stage $Stage
    $mode = [string](Get-RequiredResultValue -Payload $Payload -Name "mode" -Stage $Stage)
    $autoRange = Get-RequiredResultValue `
        -Payload $Payload -Name "auto_range_enabled" -Stage $Stage

    if ($enabled -isnot [bool]) {
        throw "${Stage}: enabled is not a boolean."
    }
    if ($autoRange -isnot [bool]) {
        throw "${Stage}: auto_range_enabled is not a boolean."
    }
    $sourceChannel = [int]$sourceChannel
    if ($sourceChannel -lt 1) {
        throw "${Stage}: source_channel is invalid: ${sourceChannel}"
    }
    if ($mode -notin @("dc", "dc-rms", "ac-rms")) {
        throw "${Stage}: mode is not canonical: ${mode}"
    }

    return [pscustomobject]@{
        DvmEnabled = [bool]$enabled
        DvmSourceChannel = $sourceChannel
        DvmMode = $mode
        DvmAutoRange = [bool]$autoRange
    }
}

function Test-UnavailableProbe {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Invocation,

        [Parameter(Mandatory = $true)]
        [object] $Drain
    )

    if ($Invocation.ExitCode -eq 0) {
        return $false
    }
    $errorProperty = $Invocation.Payload.PSObject.Properties["error"]
    if ($null -ne $errorProperty -and $null -ne $errorProperty.Value) {
        return $false
    }

    $systemErrorProperty = $Invocation.Payload.PSObject.Properties["system_error"]
    if ($null -eq $systemErrorProperty -or $null -eq $systemErrorProperty.Value) {
        return $false
    }
    $codeProperty = $systemErrorProperty.Value.PSObject.Properties["code"]
    if ($null -eq $codeProperty -or [int]$codeProperty.Value -ne -241) {
        return $false
    }
    if (-not $Drain.Terminated) {
        return $false
    }
    if (@($Drain.Errors | Where-Object { [int]$_.code -ne -241 }).Count -gt 0) {
        return $false
    }
    return $true
}

function Invoke-HardwareFreePreflight {
    $model = "keysight-dsox4024a"
    $dryRun = @("--dry-run", "--model", $model)
    $simulate = @("--simulate", "--model", $model)

    Invoke-ModeCli -Stage "preflight-dvm-enable" -Command "dvm-enable" `
        -ModeArguments $dryRun -Arguments @("--enabled", "true") | Out-Null
    Invoke-ModeCli -Stage "preflight-dvm-source" -Command "dvm-source" `
        -ModeArguments $dryRun -Arguments @("--channel", "1") | Out-Null
    Invoke-ModeCli -Stage "preflight-dvm-auto-range" -Command "dvm-auto-range" `
        -ModeArguments $dryRun -Arguments @("--enabled", "true") | Out-Null
    foreach ($mode in @("dc", "dc-rms", "ac-rms")) {
        Invoke-ModeCli -Stage "preflight-dvm-mode-${mode}" -Command "dvm-mode" `
            -ModeArguments $dryRun -Arguments @("--mode", $mode) | Out-Null
    }

    $aggregate = Invoke-ModeCli -Stage "preflight-dvm-query" -Command "dvm-query" `
        -ModeArguments $simulate -Arguments @("--query")
    [void](Get-DvmSnapshot -Payload $aggregate -Stage "Simulator DVM snapshot")
    $aggregateValid = Get-RequiredResultValue `
        -Payload $aggregate -Name "valid" -Stage "Simulator DVM snapshot"
    if ($aggregateValid -ne $true) {
        throw "Simulator aggregate DVM reading is invalid."
    }
    [void](Assert-FiniteNumber `
        -Value (Get-RequiredResultValue -Payload $aggregate -Name "value" `
            -Stage "Simulator DVM snapshot") `
        -Label "simulator aggregate DVM value")

    $current = Invoke-ModeCli -Stage "preflight-dvm-current" -Command "dvm-current" `
        -ModeArguments $simulate -Arguments @("--query")
    if ((Get-RequiredResultValue -Payload $current -Name "valid" `
        -Stage "Simulator DVM current") -ne $true) {
        throw "Simulator current DVM reading is invalid."
    }
    [void](Assert-FiniteNumber `
        -Value (Get-RequiredResultValue -Payload $current -Name "value" `
            -Stage "Simulator DVM current") `
        -Label "simulator current DVM value")

    Invoke-ModeCli -Stage "preflight-channel-scale-set" -Command "channel-scale" `
        -ModeArguments $dryRun -Arguments @(
            "--channel", "1", "--volts-per-division", "1"
        ) | Out-Null
    Invoke-ModeCli -Stage "preflight-channel-offset-set" -Command "channel-offset" `
        -ModeArguments $dryRun -Arguments @("--channel", "1", "--volts", "0") | Out-Null

    $scale = Invoke-ModeCli -Stage "preflight-channel-scale-query" `
        -Command "channel-scale" -ModeArguments $simulate `
        -Arguments @("--channel", "1", "--query")
    $scaleValue = Assert-FiniteNumber `
        -Value (Get-RequiredResultValue -Payload $scale -Name "volts_per_division" `
            -Stage "Simulator CH1 scale") `
        -Label "simulator CH1 scale"
    if ($scaleValue -le 0) {
        throw "Simulator CH1 scale must be positive."
    }

    $offset = Invoke-ModeCli -Stage "preflight-channel-offset-query" `
        -Command "channel-offset" -ModeArguments $simulate `
        -Arguments @("--channel", "1", "--query")
    [void](Assert-FiniteNumber `
        -Value (Get-RequiredResultValue -Payload $offset -Name "volts" `
            -Stage "Simulator CH1 offset") `
        -Label "simulator CH1 offset")
}

function Wait-DvmCurrentValue {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Mode
    )

    $lastReason = "invalid reading"
    for ($attempt = 1; $attempt -le 10; $attempt += 1) {
        $reading = Invoke-LiveCli -Stage "${Mode}-current-${attempt}" `
            -Command "dvm-current" -Arguments @("--query")
        $valid = Get-RequiredResultValue `
            -Payload $reading -Name "valid" -Stage "${Mode} DVM current"
        if ($valid -eq $true) {
            return Assert-FiniteNumber `
                -Value (Get-RequiredResultValue -Payload $reading -Name "value" `
                    -Stage "${Mode} DVM current") `
                -Label "${Mode} DVM current"
        }

        $reason = Get-RequiredResultValue `
            -Payload $reading -Name "reason" -Stage "${Mode} DVM current"
        if ($null -ne $reason -and -not [string]::IsNullOrWhiteSpace([string]$reason)) {
            $lastReason = [string]$reason
        }
        if ($attempt -lt 10) {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "${Mode} DVM current did not become valid after 10 attempts: ${lastReason}"
}

function Assert-DvmModeAndCurrent {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("dc", "dc-rms", "ac-rms")]
        [string] $Mode
    )

    $modeReadback = Invoke-LiveCli -Stage "${Mode}-mode-query" `
        -Command "dvm-mode" -Arguments @("--query")
    $actualMode = [string](Get-RequiredResultValue `
        -Payload $modeReadback -Name "mode" -Stage "${Mode} mode readback")
    if ($actualMode -ne $Mode) {
        throw "DVM mode readback is ${actualMode}, expected ${Mode}."
    }
    [void](Wait-DvmCurrentValue -Mode $Mode)
}

function Invoke-DvmCase {
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
        Drain-AfterFailure -Stage "${Name}-error-drain"
    }
}

function Restore-InstrumentState {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Snapshot
    )

    $restoreErrors = [System.Collections.Generic.List[string]]::new()
    $originalAutoRange = if ($Snapshot.DvmAutoRange) { "true" } else { "false" }
    $originalEnabled = if ($Snapshot.DvmEnabled) { "true" } else { "false" }
    $restoreSteps = @(
        [pscustomobject]@{
            Name = "temporary DVM auto range disable"
            Command = "dvm-auto-range"
            Arguments = @("--enabled", "false")
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
            Name = "temporary DVM disable"
            Command = "dvm-enable"
            Arguments = @("--enabled", "false")
        },
        [pscustomobject]@{
            Name = "DVM source"
            Command = "dvm-source"
            Arguments = @("--channel", [string]$Snapshot.DvmSourceChannel)
        },
        [pscustomobject]@{
            Name = "DVM mode"
            Command = "dvm-mode"
            Arguments = @("--mode", [string]$Snapshot.DvmMode)
        },
        [pscustomobject]@{
            Name = "DVM auto range"
            Command = "dvm-auto-range"
            Arguments = @("--enabled", $originalAutoRange)
        },
        [pscustomobject]@{
            Name = "DVM enabled state"
            Command = "dvm-enable"
            Arguments = @("--enabled", $originalEnabled)
        }
    )

    foreach ($step in $restoreSteps) {
        try {
            Invoke-LiveCli -Stage "restore-$($step.Command)" -Command $step.Command `
                -Arguments $step.Arguments | Out-Null
        } catch {
            $restoreErrors.Add("$($step.Name): $($_.Exception.Message)")
            Drain-AfterFailure -Stage "restore-$($step.Command)-error-drain"
        }
    }

    if ($restoreErrors.Count -gt 0) {
        throw ($restoreErrors -join " | ")
    }
}

if ([string]::IsNullOrWhiteSpace($Resource)) {
    throw "DVM live validation requires an explicit non-empty -Resource."
}
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    throw "Python executable not found: ${Python}"
}

$timestamp = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")
$script:RunRoot = Join-Path $OutputRoot $timestamp
New-Item -ItemType Directory -Path $script:RunRoot -Force | Out-Null

Write-Host "Scopes Tool DVM live validation"
Write-Host "Artifacts: $($script:RunRoot)"
Write-Host ""

try {
    Invoke-HardwareFreePreflight
    Add-CaseResult -Name "preflight" -Status "PASS"
} catch {
    Add-CaseResult -Name "preflight" -Status "FAIL" -Detail $_.Exception.Message
    Write-Host ""
    Write-Host "FAIL  DVM live validation"
    Write-Host "No live hardware was accessed."
    Write-Host "Artifacts: $($script:RunRoot)"
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
    Write-Host "FAIL  DVM live validation"
    Write-Host "Artifacts: $($script:RunRoot)"
    exit 1
}

try {
    $initialDrain = Get-ErrorDrain -Stage "stale-error-drain"
    if (-not $initialDrain.Terminated) {
        throw "Initial error queue did not reach code 0 within 30 reads."
    }
    if ($initialDrain.Errors.Count -gt 0) {
        Write-Host "      drained $($initialDrain.Errors.Count) stale system error(s)"
        Write-DrainErrors -Errors $initialDrain.Errors
    }
    Add-CaseResult -Name "stale-error-drain" -Status "PASS"
} catch {
    Add-CaseResult -Name "stale-error-drain" -Status "FAIL" `
        -Detail $_.Exception.Message
    Write-Host ""
    Write-Host "FAIL  DVM live validation"
    Write-Host "No state-changing DVM cases were run."
    Write-Host "Artifacts: $($script:RunRoot)"
    exit 1
}

$dvmSnapshot = $null
$availabilityInvocation = $null
$availabilityDrain = $null
$availabilityError = ""
try {
    $availabilityInvocation = Invoke-CliRaw -Stage "availability" -Arguments @(
        "dvm-query", "--live", "--resource", $Resource, "--json", "--query"
    )
} catch {
    $availabilityError = $_.Exception.Message
}

if ($null -ne $availabilityInvocation) {
    $okProperty = $availabilityInvocation.Payload.PSObject.Properties["ok"]
    $ok = $null -ne $okProperty -and $okProperty.Value -eq $true
    if ($availabilityInvocation.ExitCode -eq 0 -and $ok) {
        try {
            $systemErrorProperty = `
                $availabilityInvocation.Payload.PSObject.Properties["system_error"]
            if ($null -eq $systemErrorProperty -or
                $null -eq $systemErrorProperty.Value -or
                [int]$systemErrorProperty.Value.code -ne 0) {
                throw "Availability probe did not report a clean system error."
            }
            $dvmSnapshot = Get-DvmSnapshot `
                -Payload $availabilityInvocation.Payload -Stage "Live DVM snapshot"
            Add-CaseResult -Name "availability" -Status "PASS"
        } catch {
            $availabilityError = $_.Exception.Message
        }
    } else {
        try {
            $availabilityDrain = Get-ErrorDrain -Stage "availability-error-drain"
            Write-DrainErrors -Errors $availabilityDrain.Errors
        } catch {
            $availabilityError = "Availability error drain failed: $($_.Exception.Message)"
        }

        if ([string]::IsNullOrWhiteSpace($availabilityError) -and
            $null -ne $availabilityDrain -and
            (Test-UnavailableProbe `
                -Invocation $availabilityInvocation -Drain $availabilityDrain)) {
            $script:DvmUnavailable = $true
            Add-CaseResult -Name "availability" -Status "SKIP" `
                -Detail "DVM option/license is not available on this instrument."
        } elseif ([string]::IsNullOrWhiteSpace($availabilityError)) {
            $payloadError = Get-PayloadErrorText -Payload $availabilityInvocation.Payload
            $availabilityError = "DVM availability probe failed with an unknown error."
            if (-not [string]::IsNullOrWhiteSpace($payloadError)) {
                $availabilityError += " error=${payloadError}"
            }
        }
    }
} else {
    try {
        $availabilityDrain = Get-ErrorDrain -Stage "availability-diagnostic-drain"
        Write-DrainErrors -Errors $availabilityDrain.Errors
        if (-not $availabilityDrain.Terminated) {
            $availabilityError += " Error queue did not reach code 0."
        }
    } catch {
        $availabilityError += " Diagnostic error drain failed: $($_.Exception.Message)"
    }
}

if (-not $script:DvmUnavailable -and $null -eq $dvmSnapshot) {
    $script:FunctionalFailed = $true
    Add-CaseResult -Name "availability" -Status "FAIL" -Detail $availabilityError
}

$snapshot = $null
$stateChangeStarted = $false

if ($null -ne $dvmSnapshot -and -not $script:FunctionalFailed) {
    Write-Host ""
    Write-Host "DVM live validation"
    Write-Host ""
    Write-Host "Detected instrument: $($identity.idn.raw)"
    Write-Host "Connection/resource: ${Resource}"
    Write-Host ""
    Write-Host "Required setup:"
    Write-Host "  - Connect the CH1 probe to the oscilloscope Probe Demo / Probe Comp output."
    Write-Host "  - Confirm a stable waveform is present on CH1."
    Write-Host "  - Ensure CH1 is not currently used as the oscilloscope trigger source while"
    Write-Host "    validating DVM Auto Range."
    Write-Host "  - This test will temporarily change DVM settings and may adjust CH1 scale"
    Write-Host "    and offset while DVM Auto Range is enabled."
    Write-Host "  - The original DVM settings and CH1 scale/offset will be restored where"
    Write-Host "    supported by the existing public CLI."
    Write-Host ""
    Write-Host "Press Enter when ready."
    Write-Host "Ctrl+C to cancel."
    [void](Read-Host)

    try {
        $channelScale = Invoke-LiveCli -Stage "snapshot-channel-scale" `
            -Command "channel-scale" -Arguments @("--channel", "1", "--query")
        $channelOffset = Invoke-LiveCli -Stage "snapshot-channel-offset" `
            -Command "channel-offset" -Arguments @("--channel", "1", "--query")
        $scaleValue = Assert-FiniteNumber `
            -Value (Get-RequiredResultValue -Payload $channelScale `
                -Name "volts_per_division" -Stage "CH1 scale snapshot") `
            -Label "CH1 scale"
        if ($scaleValue -le 0) {
            throw "CH1 scale must be positive."
        }
        $offsetValue = Assert-FiniteNumber `
            -Value (Get-RequiredResultValue -Payload $channelOffset `
                -Name "volts" -Stage "CH1 offset snapshot") `
            -Label "CH1 offset"

        $snapshot = [pscustomobject]@{
            DvmEnabled = $dvmSnapshot.DvmEnabled
            DvmSourceChannel = $dvmSnapshot.DvmSourceChannel
            DvmMode = $dvmSnapshot.DvmMode
            DvmAutoRange = $dvmSnapshot.DvmAutoRange
            ChannelScale = $scaleValue
            ChannelOffset = $offsetValue
        }
        Add-CaseResult -Name "state-snapshot" -Status "PASS"
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "state-snapshot" -Status "FAIL" `
            -Detail $_.Exception.Message
        Drain-AfterFailure -Stage "state-snapshot-error-drain"
    }
}

if ($null -ne $snapshot -and -not $script:FunctionalFailed) {
    $stateChangeStarted = $true
    Invoke-DvmCase -Name "dc" -Action {
        Invoke-LiveCli -Stage "dc-source-set" -Command "dvm-source" `
            -Arguments @("--channel", "1") | Out-Null
        Invoke-LiveCli -Stage "dc-auto-range-set" -Command "dvm-auto-range" `
            -Arguments @("--enabled", "true") | Out-Null
        Invoke-LiveCli -Stage "dc-mode-set" -Command "dvm-mode" `
            -Arguments @("--mode", "dc") | Out-Null
        Invoke-LiveCli -Stage "dc-enable-set" -Command "dvm-enable" `
            -Arguments @("--enabled", "true") | Out-Null
        Assert-DvmModeAndCurrent -Mode "dc"
    }

    if (-not $script:FunctionalFailed) {
        Invoke-DvmCase -Name "dc-rms" -Action {
            Invoke-LiveCli -Stage "dc-rms-mode-set" -Command "dvm-mode" `
                -Arguments @("--mode", "dc-rms") | Out-Null
            Assert-DvmModeAndCurrent -Mode "dc-rms"
        }
    }

    if (-not $script:FunctionalFailed) {
        Invoke-DvmCase -Name "ac-rms" -Action {
            Invoke-LiveCli -Stage "ac-rms-mode-set" -Command "dvm-mode" `
                -Arguments @("--mode", "ac-rms") | Out-Null
            Assert-DvmModeAndCurrent -Mode "ac-rms"
        }
    }
}

if ($stateChangeStarted) {
    try {
        Restore-InstrumentState -Snapshot $snapshot
        Add-CaseResult -Name "cleanup" -Status "PASS"
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "cleanup" -Status "FAIL" -Detail $_.Exception.Message
    }
} else {
    Add-CaseResult -Name "cleanup" -Status "PASS" `
        -Detail "No state-changing DVM case ran."
}

try {
    $finalDrain = Get-ErrorDrain -Stage "final-error-queue"
    if (-not $finalDrain.Terminated) {
        throw "Final error queue did not reach code 0 within 30 reads."
    }
    if ($finalDrain.Errors.Count -gt 0) {
        Write-DrainErrors -Errors $finalDrain.Errors
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
    Write-Host "FAIL  DVM live validation"
    exit 1
}

if ($script:DvmUnavailable) {
    Write-Host "SKIP  DVM live validation"
    Write-Host "      DVM option/license is not available on this instrument."
    exit 0
}

Write-Host "PASS  DVM live validation"
exit 0
