[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $Target,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $Connection,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string] $Resource,

    [string] $Python = ".\.venv\Scripts\python.exe",

    [string] $OutputRoot = ".tmp_tests\live_segmented_check"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$script:RepoRoot = $RepoRoot
. (Join-Path $PSScriptRoot "_validation_helpers.ps1")
. (Join-Path $PSScriptRoot "_artifact_privacy.ps1")

$script:CliInvocationIndex = 0
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:SegmentedUnavailable = $false
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:ShareableGenerationFailed = $false
$script:HardwareTouched = $false

$normalizedConnection = $Connection.Trim().ToLowerInvariant()
if ($normalizedConnection -notin @("usb", "tcpip")) {
    Write-LiveUsageError -Domain "segmented" `
        "Unsupported connection '${Connection}'. Use usb or tcpip."
}

$normalizedTarget = $Target.Trim().ToLowerInvariant()
if ($normalizedTarget -eq "all") {
    Write-LiveUsageError -Domain "segmented" (
        "Target 'all' is not supported for live validation. " +
        "Specify one of: $(@(Get-SupportedTargetModelIds) -join ', ')."
    )
}
try {
    $resolvedTargets = @(Resolve-ValidationTargets -Target $normalizedTarget)
} catch {
    Write-LiveUsageError -Domain "segmented" $_.Exception.Message
}
if ($resolvedTargets.Count -ne 1) {
    Write-LiveUsageError -Domain "segmented" (
        "Live validation requires a single canonical target. " +
        "Supported targets: $(@(Get-SupportedTargetModelIds) -join ', ')."
    )
}
$script:Target = $resolvedTargets[0]
$script:Connection = $normalizedConnection

$resourceMatchesConnection =
    ($normalizedConnection -eq "usb" -and $Resource -match "^(?i)USB\d*::") -or
    ($normalizedConnection -eq "tcpip" -and $Resource -match "^(?i)TCPIP\d*::")
if (-not $resourceMatchesConnection) {
    $mismatchMessage =
        "Connection '{0}' does not match resource '{1}'. usb requires a " +
        "USB0::-style resource; tcpip requires a TCPIP0::-style resource."
    Write-LiveUsageError -Domain "segmented" (
        $mismatchMessage -f $normalizedConnection, $Resource
    )
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
    Write-Host ("{0,-5} [live][segmented] {1}" -f $Status, $Name)
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
    $lines.Add("Target: $($script:Target)")
    $lines.Add("Connection: $($script:Connection)")
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
    $baseName = "cli-{0:D3}-{1}" -f $script:CliInvocationIndex, $safeStage
    $stdoutPath = Join-Path $script:RunRoot "${baseName}.stdout.txt"
    $stderrPath = Join-Path $script:RunRoot "${baseName}.stderr.txt"
    $jsonPath = Join-Path $script:RunRoot "${baseName}.json"

    $record = Invoke-CapturedCommand `
        -Name $Stage `
        -FilePath $Python `
        -Arguments (@("-m", "scopes_tool_cli.cli") + @($Arguments)) `
        -StdOutPath $stdoutPath `
        -StdErrPath $stderrPath `
        -JsonPath $jsonPath `
        -WorkingDirectory $RepoRoot

    $exitCode = [int]$record["exit_code"]
    $invocationRecord = [pscustomobject]@{
        index = $script:CliInvocationIndex
        stage = $Stage
        command = "$Python -m scopes_tool_cli.cli $($Arguments -join ' ')"
        arguments = @($Arguments)
        exit_code = $exitCode
        duration_ms = $record["duration_ms"]
        success = ($exitCode -eq 0)
        stdout = Get-ArtifactRelativePath `
            -Path ([string]$record["stdout"]) `
            -BaseRoot $RepoRoot
        stderr = Get-ArtifactRelativePath `
            -Path ([string]$record["stderr"]) `
            -BaseRoot $RepoRoot
        json = Get-ArtifactRelativePath `
            -Path ([string]$record["json"]) `
            -BaseRoot $RepoRoot
    }
    $script:Invocations.Add($invocationRecord) | Out-Null

    $stdoutText = ""
    if (Test-Path -LiteralPath $stdoutPath -PathType Leaf) {
        $stdoutText = [System.Convert]::ToString((Get-Content -LiteralPath $stdoutPath -Raw)).Trim()
    }
    $stderrText = ""
    if (-not [string]::IsNullOrWhiteSpace([string]$record["stderr"]) -and
        (Test-Path -LiteralPath ([string]$record["stderr"]) -PathType Leaf)) {
        $stderrText = [System.Convert]::ToString((Get-Content -LiteralPath ([string]$record["stderr"]) -Raw)).Trim()
    }
    $artifactHint = "stdout=${stdoutPath}"
    if (-not [string]::IsNullOrWhiteSpace([string]$record["stderr"])) {
        $artifactHint += "; stderr=$($record['stderr'])"
    } else {
        $artifactHint += "; stderr=(empty)"
    }

    if ([string]::IsNullOrWhiteSpace($stdoutText)) {
        throw "${Stage}: CLI returned no JSON (exit ${exitCode}). ${stderrText} [artifacts: ${artifactHint}]"
    }

    try {
        $payload = $stdoutText | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "${Stage}: CLI returned invalid JSON (exit ${exitCode}). ${stderrText} [artifacts: ${artifactHint}]"
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Payload = $payload
        Stderr = $stderrText
        Command = "$Python -m scopes_tool_cli.cli $($Arguments -join ' ')"
        DurationMs = $record["duration_ms"]
        StdOutPath = $stdoutPath
        StdErrPath = [string]$record["stderr"]
        JsonPath = [string]$record["json"]
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

    $script:HardwareTouched = $true

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

    $script:HardwareTouched = $true

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

function Invoke-SegmentedConfigurationReadback {
    $arguments = @(
        "segmented-memory", "--live", "--resource", $Resource, "--json", "--query"
    )

    Start-Sleep -Milliseconds 500
    $invocation = Invoke-CliRaw -Stage "configuration-query-segmented" `
        -Arguments $arguments
    $okProperty = $invocation.Payload.PSObject.Properties["ok"]
    $ok = $null -ne $okProperty -and $okProperty.Value -eq $true
    if ($invocation.ExitCode -eq 0 -and $ok) {
        return $invocation.Payload
    }

    $isTransientTimeout = $false
    $errorProperty = $invocation.Payload.PSObject.Properties["error"]
    if ($null -ne $errorProperty -and $null -ne $errorProperty.Value) {
        $typeProperty = $errorProperty.Value.PSObject.Properties["type"]
        $messageProperty = $errorProperty.Value.PSObject.Properties["message"]
        if ($null -ne $typeProperty -and $null -ne $messageProperty) {
            $errorType = [string]$typeProperty.Value
            $errorMessage = [string]$messageProperty.Value
            $isTransientTimeout = (
                $errorType -eq "VisaBackendError" -and
                $errorMessage.Contains("*IDN?") -and
                $errorMessage.Contains("VI_ERROR_TMO")
            )
        }
    }
    if (-not $isTransientTimeout) {
        throw (Get-InvocationFailureDetail `
            -Invocation $invocation -Stage "configuration-query-segmented")
    }

    Start-Sleep -Milliseconds 500
    $recoveryDrain = Get-ErrorDrain `
        -Stage "configuration-query-segmented-recovery-drain"
    if ($recoveryDrain.Errors.Count -gt 0) {
        Write-DrainErrors -Errors $recoveryDrain.Errors `
            -CaseName "segmented configuration roundtrip"
    }
    if (-not $recoveryDrain.Terminated) {
        throw "Configuration readback recovery error queue did not reach code 0."
    }
    $unexpectedErrors = @($recoveryDrain.Errors | Where-Object {
        ([int]$_.code) -notin @(-221, -420)
    })
    if ($unexpectedErrors.Count -gt 0) {
        $unexpectedCodes = @($unexpectedErrors | ForEach-Object { [int]$_.code })
        throw (
            "Configuration readback recovery encountered unexpected system " +
            "error code(s): $($unexpectedCodes -join ', ')."
        )
    }

    Start-Sleep -Milliseconds 500
    $retryInvocation = Invoke-CliRaw `
        -Stage "configuration-query-segmented-retry" -Arguments $arguments
    $retryOkProperty = $retryInvocation.Payload.PSObject.Properties["ok"]
    $retryOk = $null -ne $retryOkProperty -and $retryOkProperty.Value -eq $true
    if ($retryInvocation.ExitCode -ne 0 -or -not $retryOk) {
        throw (Get-InvocationFailureDetail `
            -Invocation $retryInvocation -Stage "configuration-query-segmented-retry")
    }
    return $retryInvocation.Payload
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
        Drain-AfterFailure -Stage "cleanup-segmented-disable-error-drain" `
            -CaseName "cleanup"
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
        Drain-AfterFailure -Stage "cleanup-segmented-query-error-drain" `
            -CaseName "cleanup"
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

$outputBase = Get-FullPath -Path $OutputRoot -BaseRoot $RepoRoot
try {
    Assert-PathUnderRoot `
        -RootPath (Join-Path $RepoRoot ".tmp_tests") `
        -Path $outputBase `
        -Message "Live validation artifacts must stay under repository .tmp_tests: {0}"
} catch {
    Write-LiveUsageError -Domain "segmented" $_.Exception.Message
}

$runLayout = New-ValidationRunDirectory -BaseRoot $outputBase -Prefix "run"
$script:RunDirectory = $runLayout.Root
$script:RunRoot = $runLayout.Private
$script:ShareableRoot = $runLayout.Shareable

Write-Host "Scopes Tool Segmented Memory live validation"
Write-Host "[live][segmented] target: $($script:Target)"
Write-Host "[live][segmented] connection: $($script:Connection)"
Write-Host "[live][segmented] artifacts: $($script:RunDirectory)"
Write-Host ""
Write-Host ""

try {
    Invoke-HardwareFreePreflight
    Add-CaseResult -Name "preflight" -Status "PASS"
} catch {
    Add-CaseResult -Name "preflight" -Status "FAIL" -Detail $_.Exception.Message
    Write-Host ""
    Write-Host "FAIL  Segmented Memory live validation"
    Write-Host "No live hardware was accessed."
    Write-Host "[live][segmented] artifacts: $($script:RunDirectory)"
    Complete-LiveValidationRun -Kind 'scopes-tool-live-segmented-check' -Domain 'segmented' -Result "FAIL"
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
    Write-Host "[live][segmented] artifacts: $($script:RunDirectory)"
    Complete-LiveValidationRun -Kind 'scopes-tool-live-segmented-check' -Domain 'segmented' -Result "FAIL"
    exit 1
}

try {
    Assert-TargetModelMatch -Identity $identity -ResolvedTarget $script:Target
    Add-CaseResult -Name "target-model-match" -Status "PASS"
} catch {
    Add-CaseResult -Name "target-model-match" -Status "FAIL" `
        -Detail $_.Exception.Message
    Write-Host ""
    Write-Host "FAIL  Segmented Memory live validation"
    Write-Host "Functional cases were not run because the detected model does not match the requested target."
    Write-Host "[live][segmented] artifacts: $($script:RunDirectory)"
    Complete-LiveValidationRun -Kind 'scopes-tool-live-segmented-check' -Domain 'segmented' -Result "FAIL"
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
    Write-Host "FAIL  Segmented Memory live validation"
    Write-Host "No state-changing Segmented Memory cases were run."
    Write-Host "[live][segmented] artifacts: $($script:RunDirectory)"
    Complete-LiveValidationRun -Kind 'scopes-tool-live-segmented-check' -Domain 'segmented' -Result "FAIL"
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
        Drain-AfterFailure -Stage "realtime-precondition-error-drain" `
            -CaseName "realtime precondition"
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
                Write-DrainErrors -Errors $enableDrain.Errors -CaseName "segmented memory"
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
            Write-DrainErrors -Errors $enableDrain.Errors -CaseName "segmented memory"
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
            $segmentedReadback = Invoke-SegmentedConfigurationReadback
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
            Drain-AfterFailure -Stage "configuration-roundtrip-error-drain" `
                -CaseName "segmented configuration roundtrip"
        }
    }
}

if ($configurationPassed -and -not $script:FunctionalFailed) {
    try {
        $liveCaptureRoot = Join-Path $script:RunRoot "segmented-capture"
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
        Drain-AfterFailure -Stage "segmented-finite-capture-error-drain" `
            -CaseName "segmented finite capture"
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
    Write-Host ("{0,-5} [live][segmented] {1}" -f $entry.Value.Status, $entry.Key)
}
Write-Host "[live][segmented] artifacts: $($script:RunDirectory)"
Write-Host ""

if ($script:FunctionalFailed) {
    Complete-LiveValidationRun -Kind 'scopes-tool-live-segmented-check' -Domain 'segmented' -Result "FAIL"
    Write-Host "FAIL  Segmented Memory live validation"
    if ($script:ShareableGenerationFailed) {
        Write-Host "[live][segmented] run failed; see private report for the shareable generation error"
    }
    exit 1
}

if ($script:SegmentedUnavailable) {
    Complete-LiveValidationRun -Kind 'scopes-tool-live-segmented-check' -Domain 'segmented' -Result "SKIP"
    Write-Host "SKIP  Segmented Memory live validation"
    Write-Host "      NOT AVAILABLE: required instrument option/license is not installed."
    if ($script:ShareableGenerationFailed) {
        Write-Host "[live][segmented] skipped run failed; see private report for the shareable generation error"
        exit 1
    }
    exit 0
}

    Complete-LiveValidationRun -Kind 'scopes-tool-live-segmented-check' -Domain 'segmented' -Result "PASS"
if ($script:ShareableGenerationFailed) {
    Write-Host "FAIL  Segmented Memory live validation (shareable artifact generation failed)"
    exit 1
}
Write-Host "PASS  Segmented Memory live validation"
exit 0
