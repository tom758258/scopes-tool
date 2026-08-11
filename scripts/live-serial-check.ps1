[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $Resource,

    [string] $Python = ".\.venv\Scripts\python.exe",

    [string] $OutputRoot = ".tmp_tests\live_serial_check"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:CliInvocationIndex = 0
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:SerialUnavailable = $false

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
            $code = [int]$codeProperty.Value
            $systemErrorDetail = "system error ${code}"
            if ($null -ne $messageProperty -and
                -not [string]::IsNullOrWhiteSpace([string]$messageProperty.Value)) {
                $systemErrorDetail += ": $($messageProperty.Value)"
            }
            $detail += "; ${systemErrorDetail}"
            if ($code -eq -221) {
                $detail += (
                    "; Requested Serial settings conflict with current instrument state. " +
                    "Check the other Serial bus and release CH1/CH2 or conflicting " +
                    "protocol resources."
                )
            }
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
    $systemError = Get-PayloadSystemError -Payload $Invocation.Payload
    if ($null -eq $systemError) {
        return $false
    }
    $codeProperty = $systemError.PSObject.Properties["code"]
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

function Assert-UartReadback {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload
    )

    $expected = [ordered]@{
        mode = "uart"
        rx_source = "channel1"
        tx_source = "channel2"
        baud_rate = 115200
        data_bits = 8
        parity = "none"
        polarity = "high"
        bit_order = "lsb-first"
    }
    foreach ($entry in $expected.GetEnumerator()) {
        $actual = Get-RequiredResultValue -Payload $Payload -Name $entry.Key `
            -Stage "UART configuration readback"
        if ([string]$actual -ne [string]$entry.Value) {
            throw (
                "UART $($entry.Key) readback is ${actual}, expected " +
                "$($entry.Value)."
            )
        }
    }
}

function Assert-SerialCriteriaReadback {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Payload,

        [Parameter(Mandatory = $true)]
        [ValidateSet("Search", "Trigger")]
        [string] $Kind
    )

    $typeField = if ($Kind -eq "Search") { "mode" } else { "type" }
    $expected = [ordered]@{
        protocol = "uart"
        bus = 1
        selected = $true
        $typeField = "rx-data"
        data = 1
        qualifier = "equal"
    }
    foreach ($entry in $expected.GetEnumerator()) {
        $actual = Get-RequiredResultValue -Payload $Payload -Name $entry.Key `
            -Stage "UART Serial ${Kind} readback"
        if ([string]$actual -ne [string]$entry.Value) {
            throw (
                "UART Serial ${Kind} $($entry.Key) readback is ${actual}, " +
                "expected $($entry.Value)."
            )
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
        Add-CaseResult -Name $Name -Status "PASS"
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name $Name -Status "FAIL" -Detail $_.Exception.Message
        Drain-AfterFailure -Stage "${Name}-error-drain" -CaseName $Name
    }
}

function Invoke-HardwareFreePreflight {
    $model = "keysight-dsox4034a"
    $dryRun = @("--dry-run", "--model", $model)
    $simulate = @("--simulate", "--model", $model)

    Invoke-ModeCli -Stage "preflight-serial-query" -Command "serial-query" `
        -ModeArguments $simulate -Arguments @("--bus", "1") | Out-Null
    Invoke-ModeCli -Stage "preflight-uart-configure" -Command "serial-uart" `
        -ModeArguments $dryRun -Arguments @(
            "--bus", "1", "--rx-source", "channel1", "--tx-source", "channel2",
            "--baud-rate", "115200", "--data-bits", "8", "--parity", "none",
            "--polarity", "high", "--bit-order", "lsb-first"
        ) | Out-Null
    Invoke-ModeCli -Stage "preflight-uart-query" -Command "serial-uart" `
        -ModeArguments $simulate -Arguments @("--bus", "1", "--query") | Out-Null

    Invoke-ModeCli -Stage "preflight-lister-query" -Command "serial-lister-query" `
        -ModeArguments $simulate | Out-Null
    Invoke-ModeCli -Stage "preflight-lister-display" `
        -Command "serial-lister-display" -ModeArguments $dryRun `
        -Arguments @("--selection", "all") | Out-Null
    Invoke-ModeCli -Stage "preflight-lister-display-query" `
        -Command "serial-lister-display" -ModeArguments $simulate `
        -Arguments @("--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-lister-reference" `
        -Command "serial-lister-reference" -ModeArguments $dryRun `
        -Arguments @("--reference", "trigger") | Out-Null
    Invoke-ModeCli -Stage "preflight-lister-reference-query" `
        -Command "serial-lister-reference" -ModeArguments $simulate `
        -Arguments @("--query") | Out-Null
    $preflightExport = Join-Path $script:RunRoot "preflight-uart-lister.csv"
    Invoke-ModeCli -Stage "preflight-lister-export" `
        -Command "serial-lister-export" -ModeArguments $dryRun `
        -Arguments @("--output", $preflightExport) | Out-Null
    if (Test-Path -LiteralPath $preflightExport) {
        throw "Dry-run Serial Lister export unexpectedly created ${preflightExport}."
    }

    Invoke-ModeCli -Stage "preflight-search-configure" `
        -Command "serial-search-uart" -ModeArguments $dryRun -Arguments @(
            "--bus", "1", "--mode", "rx-data", "--data", "1",
            "--qualifier", "equal"
        ) | Out-Null
    Invoke-ModeCli -Stage "preflight-search-query" `
        -Command "serial-search-uart" -ModeArguments $simulate `
        -Arguments @("--bus", "1", "--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-trigger-configure" `
        -Command "serial-trigger-uart" -ModeArguments $dryRun -Arguments @(
            "--bus", "1", "--type", "rx-data", "--data", "1",
            "--qualifier", "equal"
        ) | Out-Null
    Invoke-ModeCli -Stage "preflight-trigger-query" `
        -Command "serial-trigger-uart" -ModeArguments $simulate `
        -Arguments @("--bus", "1", "--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-search-disable" -Command "search-state" `
        -ModeArguments $dryRun -Arguments @("--enabled", "false") | Out-Null
    Invoke-ModeCli -Stage "preflight-search-state-query" -Command "search-state" `
        -ModeArguments $simulate -Arguments @("--query") | Out-Null

    Invoke-ModeCli -Stage "preflight-edge-configure" -Command "trigger-edge" `
        -ModeArguments $dryRun -Arguments @(
            "--source-channel", "1", "--level", "0", "--slope", "positive"
        ) | Out-Null
    Invoke-ModeCli -Stage "preflight-edge-source-query" `
        -Command "trigger-edge-source" -ModeArguments $simulate `
        -Arguments @("--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-edge-source-restore" `
        -Command "trigger-edge-source" -ModeArguments $dryRun `
        -Arguments @("--source", "external") | Out-Null
    Invoke-ModeCli -Stage "preflight-edge-slope-query" `
        -Command "trigger-edge-slope" -ModeArguments $simulate `
        -Arguments @("--query") | Out-Null
    Invoke-ModeCli -Stage "preflight-edge-level-query" `
        -Command "trigger-edge-level" -ModeArguments $simulate `
        -Arguments @("--source-channel", "1", "--query") | Out-Null
}

function Restore-SerialState {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Snapshot,

        [Parameter(Mandatory = $true)]
        [bool] $DisableSearch,

        [Parameter(Mandatory = $true)]
        [bool] $RestoreLister,

        [Parameter(Mandatory = $true)]
        [bool] $RestoreTrigger
    )

    $restoreErrors = [System.Collections.Generic.List[string]]::new()

    if ($DisableSearch) {
        try {
            Invoke-LiveCli -Stage "cleanup-search-disable" -Command "search-state" `
                -Arguments @("--enabled", "false") | Out-Null
            $searchState = Invoke-LiveCli -Stage "cleanup-search-query" `
                -Command "search-state" -Arguments @("--query")
            if ([bool](Get-RequiredResultValue -Payload $searchState -Name "enabled" `
                -Stage "Search cleanup") -ne $false) {
                throw "Search cleanup readback did not report OFF."
            }
        } catch {
            $restoreErrors.Add("Search: $($_.Exception.Message)")
            Drain-AfterFailure -Stage "cleanup-search-error-drain" -CaseName "cleanup"
        }
    }

    if ($RestoreLister) {
        $listerRestoreErrors = [System.Collections.Generic.List[string]]::new()
        try {
            Invoke-LiveCli -Stage "cleanup-lister-display" `
                -Command "serial-lister-display" `
                -Arguments @("--selection", [string]$Snapshot.ListerDisplay) | Out-Null
        } catch {
            $listerRestoreErrors.Add("display: $($_.Exception.Message)")
            Drain-AfterFailure -Stage "cleanup-lister-display-error-drain" `
                -CaseName "cleanup"
        }
        try {
            Invoke-LiveCli -Stage "cleanup-lister-reference" `
                -Command "serial-lister-reference" `
                -Arguments @("--reference", [string]$Snapshot.ListerReference) | Out-Null
        } catch {
            $listerRestoreErrors.Add("reference: $($_.Exception.Message)")
            Drain-AfterFailure -Stage "cleanup-lister-reference-error-drain" `
                -CaseName "cleanup"
        }
        try {
            $lister = Invoke-LiveCli -Stage "cleanup-lister-query" `
                -Command "serial-lister-query"
            if ([string](Get-RequiredResultValue -Payload $lister -Name "display" `
                -Stage "Lister cleanup") -ne [string]$Snapshot.ListerDisplay -or
                [string](Get-RequiredResultValue -Payload $lister -Name "reference" `
                -Stage "Lister cleanup") -ne [string]$Snapshot.ListerReference) {
                throw "Lister cleanup readback did not match the saved display/reference."
            }
        } catch {
            $listerRestoreErrors.Add("readback: $($_.Exception.Message)")
            Drain-AfterFailure -Stage "cleanup-lister-query-error-drain" `
                -CaseName "cleanup"
        }
        if ($listerRestoreErrors.Count -gt 0) {
            $restoreErrors.Add("Lister: $($listerRestoreErrors -join '; ')")
        }
    }

    if ($RestoreTrigger) {
        try {
            $levelText = ConvertTo-InvariantString -Value ([double]$Snapshot.EdgeLevel)
            Invoke-LiveCli -Stage "cleanup-trigger-edge" -Command "trigger-edge" `
                -Arguments @(
                    "--source-channel", [string]$Snapshot.EdgeLevelChannel,
                    "--level", $levelText, "--slope", [string]$Snapshot.EdgeSlope
                ) | Out-Null
            if ($Snapshot.EdgeSource -in @("external", "line")) {
                Invoke-LiveCli -Stage "cleanup-trigger-edge-source" `
                    -Command "trigger-edge-source" `
                    -Arguments @("--source", [string]$Snapshot.EdgeSource) | Out-Null
            }

            $source = Invoke-LiveCli -Stage "cleanup-trigger-source-query" `
                -Command "trigger-edge-source" -Arguments @("--query")
            $slope = Invoke-LiveCli -Stage "cleanup-trigger-slope-query" `
                -Command "trigger-edge-slope" -Arguments @("--query")
            $level = Invoke-LiveCli -Stage "cleanup-trigger-level-query" `
                -Command "trigger-edge-level" -Arguments @(
                    "--source-channel", [string]$Snapshot.EdgeLevelChannel, "--query"
                )

            $sourceValue = [string](Get-RequiredResultValue `
                -Payload $source -Name "source" -Stage "Edge cleanup")
            $sourceChannel = Get-RequiredResultValue `
                -Payload $source -Name "source_channel" -Stage "Edge cleanup"
            if ($sourceValue -ne [string]$Snapshot.EdgeSource) {
                throw "Edge source cleanup readback is ${sourceValue}."
            }
            if ($sourceValue -eq "analog-channel") {
                if ([int]$sourceChannel -ne [int]$Snapshot.EdgeSourceChannel) {
                    throw "Edge source channel cleanup readback is ${sourceChannel}."
                }
            } elseif ($null -ne $sourceChannel) {
                throw "Edge ${sourceValue} cleanup returned a non-null source_channel."
            }
            $slopeValue = [string](Get-RequiredResultValue `
                -Payload $slope -Name "slope" -Stage "Edge cleanup")
            if ($slopeValue -ne [string]$Snapshot.EdgeSlope) {
                throw "Edge slope cleanup readback is ${slopeValue}."
            }
            Assert-NearlyEqual -Actual ([double](Get-RequiredResultValue `
                -Payload $level -Name "level_volts" -Stage "Edge cleanup")) `
                -Expected ([double]$Snapshot.EdgeLevel) -Label "Edge level cleanup"
        } catch {
            $restoreErrors.Add("Edge Trigger: $($_.Exception.Message)")
            Drain-AfterFailure -Stage "cleanup-trigger-error-drain" -CaseName "cleanup"
        }
    }

    if ($restoreErrors.Count -gt 0) {
        throw ($restoreErrors -join " | ")
    }
}

if ([string]::IsNullOrWhiteSpace($Resource)) {
    throw "Serial live validation requires an explicit non-empty -Resource."
}
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    throw "Python executable not found: ${Python}"
}

$timestamp = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")
$script:RunRoot = Join-Path $OutputRoot $timestamp
$listerCsvPath = Join-Path $script:RunRoot "uart-lister.csv"
New-Item -ItemType Directory -Path $script:RunRoot -Force | Out-Null

Write-Host "Scopes Tool Serial live validation"
Write-Host "Artifacts: $($script:RunRoot)"
Write-Host ""

try {
    Invoke-HardwareFreePreflight
    Add-CaseResult -Name "preflight" -Status "PASS"
} catch {
    Add-CaseResult -Name "preflight" -Status "FAIL" -Detail $_.Exception.Message
    Write-Host ""
    Write-Host "FAIL  Serial live validation"
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
    Write-Host "FAIL  Serial live validation"
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
    Write-Host "FAIL  Serial live validation"
    Write-Host "No state-changing Serial cases were run."
    Write-Host "Artifacts: $($script:RunRoot)"
    Write-Summary -Result "FAIL"
    exit 1
}

Write-Host ""
Write-Host "Detected instrument: $($identity.idn.raw)"
Write-Host "Connection/resource: ${Resource}"

$availabilityPassed = $false
$availabilityInvocation = $null
$availabilityDrain = $null
$availabilityFailure = ""
try {
    $availabilityInvocation = Invoke-CliRaw -Stage "availability" -Arguments @(
        "serial-query", "--live", "--resource", $Resource, "--json", "--bus", "1"
    )
} catch {
    $availabilityFailure = $_.Exception.Message
}

if ($null -ne $availabilityInvocation) {
    $okProperty = $availabilityInvocation.Payload.PSObject.Properties["ok"]
    $availabilityOk = $null -ne $okProperty -and $okProperty.Value -eq $true
    if ($availabilityInvocation.ExitCode -eq 0 -and $availabilityOk) {
        $availabilityPassed = $true
        Add-CaseResult -Name "availability" -Status "PASS"
    } else {
        try {
            $availabilityDrain = Get-ErrorDrain -Stage "availability-error-drain"
            Write-DrainErrors -Errors $availabilityDrain.Errors -CaseName "availability"
            if (-not $availabilityDrain.Terminated) {
                $availabilityFailure = (
                    "Availability error queue did not reach code 0 within 30 reads."
                )
            }
        } catch {
            $availabilityFailure = "Availability error drain failed: $($_.Exception.Message)"
        }

        if ([string]::IsNullOrWhiteSpace($availabilityFailure) -and
            $null -ne $availabilityDrain -and
            (Test-UnavailableProbe -Invocation $availabilityInvocation `
                -Drain $availabilityDrain)) {
            $script:SerialUnavailable = $true
            $systemError = Get-PayloadSystemError -Payload $availabilityInvocation.Payload
            Add-CaseResult -Name "availability" -Status "SKIP" -Detail (
                "NOT AVAILABLE: isolated system error $($systemError.code): " +
                "$($systemError.message)."
            )
        } elseif ([string]::IsNullOrWhiteSpace($availabilityFailure)) {
            $availabilityFailure = Get-InvocationFailureDetail `
                -Invocation $availabilityInvocation -Stage "availability"
        }
    }
} else {
    try {
        $availabilityDrain = Get-ErrorDrain -Stage "availability-diagnostic-drain"
        Write-DrainErrors -Errors $availabilityDrain.Errors -CaseName "availability"
        if (-not $availabilityDrain.Terminated) {
            $availabilityFailure += " Error queue did not reach code 0."
        }
    } catch {
        $availabilityFailure += " Diagnostic error drain failed: $($_.Exception.Message)"
    }
}

if (-not $availabilityPassed -and -not $script:SerialUnavailable) {
    $script:FunctionalFailed = $true
    Add-CaseResult -Name "availability" -Status "FAIL" -Detail $availabilityFailure
}

$searchPreconditionPassed = $false
if ($availabilityPassed -and -not $script:FunctionalFailed) {
    try {
        $searchState = Invoke-LiveCli -Stage "search-disabled-precondition" `
            -Command "search-state" -Arguments @("--query")
        $searchEnabled = Get-RequiredResultValue -Payload $searchState `
            -Name "enabled" -Stage "Search precondition"
        if ($searchEnabled -ne $false) {
            throw (
                "Search is currently enabled. No state-changing Serial validation " +
                "was performed. Disable Search and run the validation again."
            )
        }
        $searchPreconditionPassed = $true
        Add-CaseResult -Name "search-disabled precondition" -Status "PASS"
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "search-disabled precondition" -Status "FAIL" `
            -Detail $_.Exception.Message
        Drain-AfterFailure -Stage "search-disabled-precondition-error-drain" `
            -CaseName "search-disabled precondition"
    }
}

$snapshot = $null
if ($searchPreconditionPassed -and -not $script:FunctionalFailed) {
    try {
        $lister = Invoke-LiveCli -Stage "snapshot-lister" `
            -Command "serial-lister-query"
        $edgeSource = Invoke-LiveCli -Stage "snapshot-edge-source" `
            -Command "trigger-edge-source" -Arguments @("--query")
        $edgeSlope = Invoke-LiveCli -Stage "snapshot-edge-slope" `
            -Command "trigger-edge-slope" -Arguments @("--query")

        $source = [string](Get-RequiredResultValue -Payload $edgeSource `
            -Name "source" -Stage "Edge snapshot")
        $sourceChannel = Get-RequiredResultValue -Payload $edgeSource `
            -Name "source_channel" -Stage "Edge snapshot"
        if ($source -eq "analog-channel") {
            $levelChannel = 0
            if ($null -eq $sourceChannel -or
                -not [int]::TryParse([string]$sourceChannel, [ref]$levelChannel) -or
                $levelChannel -lt 1) {
                throw "Edge snapshot returned an invalid analog source_channel."
            }
        } elseif ($source -in @("external", "line")) {
            if ($null -ne $sourceChannel) {
                throw "Edge ${source} snapshot must return a null source_channel."
            }
            $levelChannel = 1
        } else {
            throw "Unsupported Edge source readback: ${source}"
        }

        $slope = [string](Get-RequiredResultValue -Payload $edgeSlope `
            -Name "slope" -Stage "Edge snapshot")
        if ($slope -notin @("positive", "negative", "either", "alternate")) {
            throw "Unsupported Edge slope readback: ${slope}"
        }
        $edgeLevel = Invoke-LiveCli -Stage "snapshot-edge-level" `
            -Command "trigger-edge-level" -Arguments @(
                "--source-channel", [string]$levelChannel, "--query"
            )
        $level = [double](Get-RequiredResultValue -Payload $edgeLevel `
            -Name "level_volts" -Stage "Edge snapshot")
        if ([double]::IsNaN($level) -or [double]::IsInfinity($level)) {
            throw "Edge snapshot level is not finite."
        }

        $snapshot = [pscustomobject]@{
            ListerDisplay = [string](Get-RequiredResultValue -Payload $lister `
                -Name "display" -Stage "Lister snapshot")
            ListerReference = [string](Get-RequiredResultValue -Payload $lister `
                -Name "reference" -Stage "Lister snapshot")
            EdgeSource = $source
            EdgeSourceChannel = $sourceChannel
            EdgeSlope = $slope
            EdgeLevelChannel = $levelChannel
            EdgeLevel = $level
        }
        Add-CaseResult -Name "state-snapshot" -Status "PASS"
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "state-snapshot" -Status "FAIL" `
            -Detail $_.Exception.Message
        Drain-AfterFailure -Stage "state-snapshot-error-drain" `
            -CaseName "state-snapshot"
    }
}

$stateChangeStarted = $false
$listerChangeStarted = $false
$searchChangeStarted = $false
$triggerChangeStarted = $false

if ($null -ne $snapshot -and -not $script:FunctionalFailed) {
    Write-Host ""
    Write-Host "Serial UART live validation"
    Write-Host ""
    Write-Host "Required setup:"
    Write-Host "  - Use Serial bus 1."
    Write-Host "  - Connect an external UART TX signal to CH1."
    Write-Host "  - UART traffic must be continuously active."
    Write-Host "  - Baud rate: 115200."
    Write-Host "  - 8 data bits."
    Write-Host "  - No parity."
    Write-Host "  - Idle high."
    Write-Host "  - LSB first."
    Write-Host "  - Repeated data value: 0x01."
    Write-Host "  - CH2 will be selected as the UART TX decode source; live traffic on CH2 is not"
    Write-Host "    required for the representative RX/Lister case."
    Write-Host "  - Ensure another Serial bus is not reserving CH1/CH2 or conflicting protocol"
    Write-Host "    resources."
    Write-Host "  - This validation will temporarily configure Serial1, Lister, Serial Search,"
    Write-Host "    and Serial Trigger."
    Write-Host "  - Serial1 is intentionally not restored. After successful UART configuration"
    Write-Host "    it remains at the documented UART test baseline. If UART configuration"
    Write-Host "    fails after partial instrument changes, Serial1 may retain partial test"
    Write-Host "    settings."
    Write-Host "  - Search will be disabled during cleanup."
    Write-Host "  - Serial Trigger validation does not arm, run, single, force, or acquire."
    Write-Host "  - Cleanup returns the global trigger mode to Edge; an arbitrary original"
    Write-Host "    trigger mode cannot be restored through the current public CLI."
    Write-Host ""
    Write-Host "Press Enter when UART traffic is active."
    Write-Host "Ctrl+C to cancel."
    [void](Read-Host)

    $stateChangeStarted = $true
    Invoke-SerialCase -Name "UART configuration roundtrip" -Action {
        Invoke-LiveCli -Stage "uart-configure" -Command "serial-uart" -Arguments @(
            "--bus", "1", "--rx-source", "channel1", "--tx-source", "channel2",
            "--baud-rate", "115200", "--data-bits", "8", "--parity", "none",
            "--polarity", "high", "--bit-order", "lsb-first"
        ) | Out-Null
        Start-Sleep -Milliseconds 500
        $uart = Invoke-LiveCli -Stage "uart-query" -Command "serial-uart" `
            -Arguments @("--bus", "1", "--query")
        Assert-UartReadback -Payload $uart
    }

    if (-not $script:FunctionalFailed) {
        $listerChangeStarted = $true
        Invoke-SerialCase -Name "UART Lister export" -Action {
            Invoke-LiveCli -Stage "lister-display" -Command "serial-lister-display" `
                -Arguments @("--selection", "all") | Out-Null
            Invoke-LiveCli -Stage "lister-reference" `
                -Command "serial-lister-reference" `
                -Arguments @("--reference", "trigger") | Out-Null
            $lister = Invoke-LiveCli -Stage "lister-query" `
                -Command "serial-lister-query"
            if ([string](Get-RequiredResultValue -Payload $lister -Name "display" `
                -Stage "Lister readback") -ne "all" -or
                [string](Get-RequiredResultValue -Payload $lister -Name "reference" `
                -Stage "Lister readback") -ne "trigger") {
                throw "Lister readback did not report display all and reference trigger."
            }

            Start-Sleep -Milliseconds 1000
            $exportInvocation = Invoke-CliRaw -Stage "lister-export" -Arguments @(
                "serial-lister-export", "--live", "--resource", $Resource, "--json",
                "--output", $listerCsvPath
            )
            $exportOkProperty = $exportInvocation.Payload.PSObject.Properties["ok"]
            $exportOk = $null -ne $exportOkProperty -and
                $exportOkProperty.Value -eq $true
            if ($exportInvocation.ExitCode -ne 0 -or -not $exportOk) {
                $detail = Get-InvocationFailureDetail `
                    -Invocation $exportInvocation -Stage "lister-export"
                $systemError = Get-PayloadSystemError -Payload $exportInvocation.Payload
                if ($null -ne $systemError -and [int]$systemError.code -eq 109) {
                    $detail = (
                        "UART traffic was not successfully decoded by the Lister. " +
                        "${detail}"
                    )
                }
                throw $detail
            }

            $reportedBytes = [long](Get-RequiredResultValue `
                -Payload $exportInvocation.Payload -Name "bytes_written" `
                -Stage "Lister export")
            if ($reportedBytes -le 0) {
                throw "Lister export reported no bytes."
            }
            if (-not (Test-Path -LiteralPath $listerCsvPath -PathType Leaf)) {
                throw "Lister export did not create ${listerCsvPath}."
            }

            $filesProperty = $exportInvocation.Payload.PSObject.Properties["files"]
            $reportedCsvFiles = @()
            if ($null -ne $filesProperty) {
                $reportedCsvFiles = @($filesProperty.Value | Where-Object {
                    $null -ne $_ -and
                        $null -ne $_.PSObject.Properties["kind"] -and
                        [string]$_.PSObject.Properties["kind"].Value -eq "csv"
                })
            }
            if ($reportedCsvFiles.Count -ne 1) {
                throw "Lister export did not report exactly one CSV artifact."
            }
            $reportedPathProperty = $reportedCsvFiles[0].PSObject.Properties["path"]
            if ($null -eq $reportedPathProperty -or
                [string]::IsNullOrWhiteSpace([string]$reportedPathProperty.Value)) {
                throw "Lister export CSV artifact did not report a path."
            }
            $reportedCsvPath = [string]$reportedPathProperty.Value
            if (-not (Test-Path -LiteralPath $reportedCsvPath -PathType Leaf)) {
                throw "Lister export reported a missing path: ${reportedCsvPath}."
            }

            $requestedItem = Get-Item -LiteralPath $listerCsvPath
            $reportedItem = Get-Item -LiteralPath $reportedCsvPath
            if (-not [string]::Equals(
                $requestedItem.FullName,
                $reportedItem.FullName,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                throw "Lister export reported a different CSV path."
            }

            $actualBytes = $requestedItem.Length
            if ($actualBytes -le 0) {
                throw "Lister export file is empty: ${listerCsvPath}."
            }
            if ($reportedBytes -ne $actualBytes) {
                throw (
                    "Lister export reported ${reportedBytes} bytes, but the file " +
                    "contains ${actualBytes} bytes."
                )
            }
        }
    }

    if (-not $script:FunctionalFailed) {
        $searchChangeStarted = $true
        Invoke-SerialCase -Name "UART Serial Search" -Action {
            Invoke-LiveCli -Stage "serial-search-configure" `
                -Command "serial-search-uart" -Arguments @(
                    "--bus", "1", "--mode", "rx-data", "--data", "1",
                    "--qualifier", "equal"
                ) | Out-Null
            Start-Sleep -Milliseconds 500
            $search = Invoke-LiveCli -Stage "serial-search-query" `
                -Command "serial-search-uart" `
                -Arguments @("--bus", "1", "--query")
            Assert-SerialCriteriaReadback -Payload $search -Kind "Search"
        }
    }

    if (-not $script:FunctionalFailed) {
        $triggerChangeStarted = $true
        Invoke-SerialCase -Name "UART Serial Trigger" -Action {
            Invoke-LiveCli -Stage "serial-trigger-configure" `
                -Command "serial-trigger-uart" -Arguments @(
                    "--bus", "1", "--type", "rx-data", "--data", "1",
                    "--qualifier", "equal"
                ) | Out-Null
            Start-Sleep -Milliseconds 500
            $trigger = Invoke-LiveCli -Stage "serial-trigger-query" `
                -Command "serial-trigger-uart" `
                -Arguments @("--bus", "1", "--query")
            Assert-SerialCriteriaReadback -Payload $trigger -Kind "Trigger"
        }
    }
}

if ($stateChangeStarted) {
    try {
        Restore-SerialState -Snapshot $snapshot `
            -DisableSearch $searchChangeStarted `
            -RestoreLister $listerChangeStarted `
            -RestoreTrigger $triggerChangeStarted
        Add-CaseResult -Name "cleanup" -Status "PASS"
    } catch {
        $script:FunctionalFailed = $true
        Add-CaseResult -Name "cleanup" -Status "FAIL" -Detail $_.Exception.Message
    }
} else {
    Add-CaseResult -Name "cleanup" -Status "PASS" `
        -Detail "No state-changing Serial case ran."
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
    Write-Host "FAIL  Serial live validation"
    exit 1
}

if ($script:SerialUnavailable) {
    Write-Summary -Result "SKIP"
    Write-Host "SKIP  Serial live validation"
    Write-Host "      Serial option/license is not available on this instrument."
    exit 0
}

Write-Summary -Result "PASS"
Write-Host "PASS  Serial live validation"
exit 0
