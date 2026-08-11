[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $Resource,

    [string] $Python = ".\.venv\Scripts\python.exe",

    [string] $OutputRoot = ".tmp_tests\live_segmented_check"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:CliInvocationIndex = 0
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:SegmentedUnavailable = $false

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

function Assert-PlannedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload,

        [Parameter(Mandatory = $true)]
        [string] $Command,

        [Parameter(Mandatory = $true)]
        [string] $Stage
    )

    $scpiProperty = $Payload.PSObject.Properties["scpi"]
    if ($null -eq $scpiProperty -or $null -eq $scpiProperty.Value) {
        throw "${Stage}: JSON did not contain SCPI plan data."
    }
    $plannedProperty = $scpiProperty.Value.PSObject.Properties["planned"]
    if ($null -eq $plannedProperty -or $Command -notin @($plannedProperty.Value)) {
        throw "${Stage}: planned SCPI did not contain ${Command}."
    }
}

function Invoke-HardwareFreePreflight {
    $model = "keysight-dsox4024a"
    $dryRun = @("--dry-run", "--model", $model)
    $simulate = @("--simulate", "--model", $model)

    $query = Invoke-ModeCli -Stage "preflight-segmented-query" `
        -Command "segmented-memory" -ModeArguments $simulate -Arguments @("--query")
    if ([string](Get-RequiredResultValue -Payload $query -Name "mode" `
        -Stage "Simulator segmented query") -ne "realtime") {
        throw "Simulator segmented-memory query did not report realtime mode."
    }

    $enable = Invoke-ModeCli -Stage "preflight-segmented-enable" `
        -Command "segmented-memory" -ModeArguments $dryRun `
        -Arguments @("--enable", "--segments", "2")
    if ([string](Get-RequiredResultValue -Payload $enable -Name "mode" `
        -Stage "Dry-run segmented enable") -ne "segmented" -or
        [int](Get-RequiredResultValue -Payload $enable -Name "configured_segments" `
            -Stage "Dry-run segmented enable") -ne 2) {
        throw "Dry-run segmented-memory enable did not plan two segments."
    }

    $disable = Invoke-ModeCli -Stage "preflight-segmented-disable" `
        -Command "segmented-memory" -ModeArguments $dryRun -Arguments @("--disable")
    if ([string](Get-RequiredResultValue -Payload $disable -Name "mode" `
        -Stage "Dry-run segmented disable") -ne "realtime") {
        throw "Dry-run segmented-memory disable did not plan realtime mode."
    }

    $capture = Invoke-ModeCli -Stage "preflight-segmented-capture" `
        -Command "segmented-capture" -ModeArguments $dryRun -Arguments @(
            "--channel", "1", "--segments", "2", "--points", "1000",
            "--format", "byte", "--timeout-ms", "30000",
            "--poll-interval-ms", "100"
        )
    if ([string](Get-RequiredResultValue -Payload $capture -Name "status" `
        -Stage "Dry-run segmented capture") -ne "planned" -or
        [int](Get-RequiredResultValue -Payload $capture -Name "configured_segments" `
            -Stage "Dry-run segmented capture") -ne 2 -or
        [string](Get-RequiredResultValue -Payload $capture -Name "format" `
            -Stage "Dry-run segmented capture") -ne "BYTE") {
        throw "Dry-run segmented capture result is malformed."
    }
    foreach ($command in @(
        ":ACQuire:MODE SEGMented",
        ":ACQuire:SEGMented:COUNt 2",
        ":SINGle",
        ":ACQuire:SEGMented:INDex 1",
        ":ACQuire:SEGMented:INDex 2",
        ":WAVeform:DATA?"
    )) {
        Assert-PlannedCommand -Payload $capture -Command $command `
            -Stage "Dry-run segmented capture"
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

function Assert-SegmentedCapture {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload
    )

    $stage = "Segmented capture"
    if ([string](Get-RequiredResultValue -Payload $Payload -Name "operation" `
        -Stage $stage) -ne "segmented-capture") {
        throw "Segmented capture result reported an unexpected operation."
    }
    if ([string](Get-RequiredResultValue -Payload $Payload -Name "status" `
        -Stage $stage) -ne "completed") {
        throw "Segmented capture did not report completed status."
    }
    if ([int](Get-RequiredResultValue -Payload $Payload -Name "channel" `
        -Stage $stage) -ne 1 -or
        [string](Get-RequiredResultValue -Payload $Payload -Name "format" `
            -Stage $stage) -ne "BYTE") {
        throw "Segmented capture did not report CH1 BYTE transfer."
    }
    foreach ($name in @("configured_segments", "acquired_segments", "exported_segments")) {
        if ([int](Get-RequiredResultValue -Payload $Payload -Name $name `
            -Stage $stage) -ne 2) {
            throw "Segmented capture ${name} is not 2."
        }
    }
    $captureError = Get-RequiredResultValue -Payload $Payload -Name "error" -Stage $stage
    if ($null -ne $captureError -and
        -not [string]::IsNullOrWhiteSpace([string]$captureError)) {
        throw "Segmented capture reported an error: ${captureError}"
    }

    $filesProperty = $Payload.PSObject.Properties["files"]
    if ($null -eq $filesProperty -or $null -eq $filesProperty.Value) {
        throw "Segmented capture JSON did not contain reported files."
    }
    $files = @($filesProperty.Value)
    if ($files.Count -eq 0) {
        throw "Segmented capture reported no files."
    }
    foreach ($file in $files) {
        $pathProperty = $file.PSObject.Properties["path"]
        if ($null -eq $pathProperty -or
            [string]::IsNullOrWhiteSpace([string]$pathProperty.Value)) {
            throw "Segmented capture reported a file without a path."
        }
        if (-not (Test-Path -LiteralPath ([string]$pathProperty.Value) -PathType Leaf)) {
            throw "Reported capture file does not exist: $($pathProperty.Value)"
        }
    }

    $manifestPath = [string](Get-RequiredResultValue `
        -Payload $Payload -Name "manifest_path" -Stage $stage)
    Assert-FileNonEmpty -Path $manifestPath -Label "segmented capture manifest"
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw |
            ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "Segmented capture manifest is not valid JSON: ${manifestPath}"
    }
    if ($null -eq $manifest) {
        throw "Segmented capture manifest is empty: ${manifestPath}"
    }

    $csvFiles = @($files | Where-Object { [string]$_.kind -eq "csv" })
    if ($csvFiles.Count -ne 2) {
        throw "Segmented capture reported $($csvFiles.Count) CSV files, expected 2."
    }
    foreach ($csv in $csvFiles) {
        Assert-FileNonEmpty -Path ([string]$csv.path) -Label "segment CSV"
    }
}

function Restore-RealtimeMode {
    $restoreErrors = [System.Collections.Generic.List[string]]::new()

    try {
        Invoke-LiveCli -Stage "cleanup-segmented-disable" `
            -Command "segmented-memory" -Arguments @("--disable") | Out-Null
    } catch {
        $restoreErrors.Add("segmented-memory disable: $($_.Exception.Message)")
        Drain-AfterFailure -Stage "cleanup-segmented-disable-error-drain"
    }

    try {
        $readback = Invoke-LiveCli -Stage "cleanup-segmented-query" `
            -Command "segmented-memory" -Arguments @("--query")
        $mode = [string](Get-RequiredResultValue `
            -Payload $readback -Name "mode" -Stage "Cleanup mode readback")
        if ($mode -ne "realtime") {
            throw "Final acquisition mode is ${mode}, expected realtime."
        }
        Write-Host "Final acquisition mode: realtime"
    } catch {
        $restoreErrors.Add("realtime readback: $($_.Exception.Message)")
        Drain-AfterFailure -Stage "cleanup-segmented-query-error-drain"
    }

    if ($restoreErrors.Count -gt 0) {
        throw ($restoreErrors -join " | ")
    }
}

if ([string]::IsNullOrWhiteSpace($Resource)) {
    throw "Segmented Memory live validation requires an explicit non-empty -Resource."
}
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    throw "Python executable not found: ${Python}"
}

$timestamp = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")
$script:RunRoot = Join-Path $OutputRoot $timestamp
$liveCaptureRoot = Join-Path $script:RunRoot "live\segmented-capture"
New-Item -ItemType Directory -Path $script:RunRoot -Force | Out-Null

Write-Host "Scopes Tool Segmented Memory live validation"
Write-Host "Artifacts: $($script:RunRoot)"
Write-Host ""

try {
    Invoke-HardwareFreePreflight
    Add-CaseResult -Name "preflight" -Status "PASS"
} catch {
    Add-CaseResult -Name "preflight" -Status "FAIL" -Detail $_.Exception.Message
    Write-Host ""
    Write-Host "FAIL  Segmented Memory live validation"
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
    Write-Host "FAIL  Segmented Memory live validation"
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
    Write-Host "FAIL  Segmented Memory live validation"
    Write-Host "No state-changing Segmented Memory cases were run."
    Write-Host "Artifacts: $($script:RunRoot)"
    exit 1
}

Write-Host ""
Write-Host "Detected instrument: $($identity.idn.raw)"
Write-Host "Connection/resource: ${Resource}"

$realtimePreconditionPassed = $false
try {
    $baseline = Invoke-LiveCli -Stage "realtime-precondition" `
        -Command "segmented-memory" -Arguments @("--query")
    $initialMode = [string](Get-RequiredResultValue `
        -Payload $baseline -Name "mode" -Stage "Realtime precondition")
    if ($initialMode -eq "segmented") {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "realtime precondition" -Status "FAIL" -Detail (
            "Current acquisition mode is segmented. " +
            "No state-changing validation was performed."
        )
    } elseif ($initialMode -eq "realtime") {
        $realtimePreconditionPassed = $true
        Add-CaseResult -Name "realtime precondition" -Status "PASS"
    } else {
        throw "Current acquisition mode is not canonical: ${initialMode}"
    }
} catch {
    if (-not $script:FunctionalFailed) {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "realtime precondition" -Status "FAIL" `
            -Detail $_.Exception.Message
        Drain-AfterFailure -Stage "realtime-precondition-error-drain"
    }
}

$stateChangeStarted = $false
$configurationPassed = $false

if ($realtimePreconditionPassed -and -not $script:FunctionalFailed) {
    Write-Host ""
    Write-Host "Segmented Memory live validation"
    Write-Host ""
    Write-Host "Required setup:"
    Write-Host "  - Connect the CH1 probe to the oscilloscope Probe Demo / Probe Comp output."
    Write-Host "  - Confirm a stable waveform is visible on CH1."
    Write-Host "  - Ensure the oscilloscope is able to trigger reliably from the CH1 demo signal."
    Write-Host "  - This validation will enter Segmented Memory mode and perform finite SINGLE"
    Write-Host "    acquisitions."
    Write-Host "  - The runner will return the acquisition mode to realtime during cleanup."
    Write-Host ""
    Write-Host "Press Enter when the environment is ready."
    Write-Host "Ctrl+C to cancel."
    [void](Read-Host)

    $stateChangeStarted = $true
    $enableInvocation = $null
    $enableDrain = $null
    $enableFailure = ""
    try {
        $enableInvocation = Invoke-CliRaw -Stage "configuration-enable" -Arguments @(
            "segmented-memory", "--live", "--resource", $Resource, "--json",
            "--enable", "--segments", "2"
        )
    } catch {
        $enableFailure = $_.Exception.Message
    }

    if ($null -ne $enableInvocation) {
        $okProperty = $enableInvocation.Payload.PSObject.Properties["ok"]
        $enableOk = $null -ne $okProperty -and $okProperty.Value -eq $true
        if ($enableInvocation.ExitCode -ne 0 -or -not $enableOk) {
            try {
                $enableDrain = Get-ErrorDrain -Stage "configuration-enable-error-drain"
                Write-DrainErrors -Errors $enableDrain.Errors
            } catch {
                $enableFailure = "Enable error drain failed: $($_.Exception.Message)"
            }

            if ([string]::IsNullOrWhiteSpace($enableFailure) -and
                $null -ne $enableDrain -and
                (Test-UnavailableProbe `
                    -Invocation $enableInvocation -Drain $enableDrain)) {
                $script:SegmentedUnavailable = $true
                Add-CaseResult -Name "segmented memory" -Status "SKIP" `
                    -Detail "NOT AVAILABLE: required instrument option/license is not installed."
            } elseif ([string]::IsNullOrWhiteSpace($enableFailure)) {
                $enableFailure = Get-InvocationFailureDetail `
                    -Invocation $enableInvocation -Stage "configuration-enable"
            }
        }
    } else {
        try {
            $enableDrain = Get-ErrorDrain -Stage "configuration-enable-diagnostic-drain"
            Write-DrainErrors -Errors $enableDrain.Errors
            if (-not $enableDrain.Terminated) {
                $enableFailure += " Error queue did not reach code 0."
            }
        } catch {
            $enableFailure += " Diagnostic error drain failed: $($_.Exception.Message)"
        }
    }

    if (-not $script:SegmentedUnavailable -and
        -not [string]::IsNullOrWhiteSpace($enableFailure)) {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "segmented configuration roundtrip" -Status "FAIL" `
            -Detail $enableFailure
    }

    if (-not $script:SegmentedUnavailable -and -not $script:FunctionalFailed) {
        try {
            $segmentedReadback = Invoke-LiveCli -Stage "configuration-query-segmented" `
                -Command "segmented-memory" -Arguments @("--query")
            $mode = [string](Get-RequiredResultValue `
                -Payload $segmentedReadback -Name "mode" `
                -Stage "Segmented configuration readback")
            $configuredSegments = [int](Get-RequiredResultValue `
                -Payload $segmentedReadback -Name "configured_segments" `
                -Stage "Segmented configuration readback")
            if ($mode -ne "segmented" -or $configuredSegments -ne 2) {
                throw (
                    "Segmented readback reported mode ${mode} and " +
                    "configured_segments ${configuredSegments}; expected segmented and 2."
                )
            }

            Invoke-LiveCli -Stage "configuration-disable" `
                -Command "segmented-memory" -Arguments @("--disable") | Out-Null
            $realtimeReadback = Invoke-LiveCli -Stage "configuration-query-realtime" `
                -Command "segmented-memory" -Arguments @("--query")
            $mode = [string](Get-RequiredResultValue `
                -Payload $realtimeReadback -Name "mode" `
                -Stage "Realtime configuration readback")
            if ($mode -ne "realtime") {
                throw "Configuration roundtrip ended in ${mode} mode, expected realtime."
            }

            $configurationPassed = $true
            Add-CaseResult -Name "segmented configuration roundtrip" -Status "PASS"
        } catch {
            $script:FunctionalFailed = $true
            Add-CaseResult -Name "segmented configuration roundtrip" -Status "FAIL" `
                -Detail $_.Exception.Message
            Drain-AfterFailure -Stage "configuration-roundtrip-error-drain"
        }
    }
}

if ($configurationPassed -and -not $script:FunctionalFailed) {
    try {
        $capture = Invoke-LiveCli -Stage "segmented-finite-capture" `
            -Command "segmented-capture" -Arguments @(
                "--channel", "1", "--segments", "2", "--points", "1000",
                "--format", "byte", "--timeout-ms", "30000",
                "--poll-interval-ms", "100", "--output-dir", $liveCaptureRoot
            )
        Assert-SegmentedCapture -Payload $capture
        Add-CaseResult -Name "segmented finite capture" -Status "PASS"
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "segmented finite capture" -Status "FAIL" `
            -Detail $_.Exception.Message
        Drain-AfterFailure -Stage "segmented-finite-capture-error-drain"
    }
}

if ($stateChangeStarted) {
    try {
        Restore-RealtimeMode
        Add-CaseResult -Name "cleanup" -Status "PASS"
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "cleanup" -Status "FAIL" -Detail $_.Exception.Message
    }
} else {
    Add-CaseResult -Name "cleanup" -Status "PASS" `
        -Detail "No state-changing Segmented Memory case ran."
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
    Write-Host "FAIL  Segmented Memory live validation"
    exit 1
}

if ($script:SegmentedUnavailable) {
    Write-Host "SKIP  Segmented Memory live validation"
    Write-Host "      NOT AVAILABLE: required instrument option/license is not installed."
    exit 0
}

Write-Host "PASS  Segmented Memory live validation"
exit 0
