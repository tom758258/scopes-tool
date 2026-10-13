[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string] $Target,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string] $Connection,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string] $Resource,
    [Alias("VisaLibrary")][string] $Backend,
    [string] $Python = ".\.venv\Scripts\python.exe",
    [string] $OutputRoot = ".tmp_tests\live_autoscale_check",
    [switch] $DebugArtifacts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot "_validation_helpers.ps1")
. (Join-Path $PSScriptRoot "_artifact_privacy.ps1")
. (Join-Path $PSScriptRoot "_live_tektronix_helpers.ps1")

$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:Invocations = [System.Collections.Generic.List[object]]::new()
$script:HardwareTouched = $false
$script:ShareableGenerationFailed = $false
$script:FunctionalFailed = $false

try {
    $resolved = @(Resolve-ValidationTargets -Target $Target -IncludeTektronix)
    if ($resolved.Count -ne 1) { throw "Live validation requires one exact registered target; 'all' is not supported." }
    $script:Target = $resolved[0]
    $script:Connection = $Connection.Trim().ToLowerInvariant()
    if ($script:Connection -notin @("usb", "tcpip")) { throw "Unsupported connection. Use usb or tcpip." }
    if (($script:Connection -eq "usb" -and $Resource -notmatch "^(?i)USB\d*::") -or
        ($script:Connection -eq "tcpip" -and $Resource -notmatch "^(?i)TCPIP\d*::")) {
        throw "Connection does not match resource; supply an explicit USB or TCPIP VISA resource of the selected type."
    }
    $script:LiveConnectionArguments = @(Get-LiveConnectionArguments -Resource $Resource -Backend $Backend)
    $script:BackendName = if ($script:LiveConnectionArguments -contains "--visa-library") { "pyvisa_py" } else { "system_visa" }
    $script:IsTektronix = $script:Target -in @($script:TektronixValidationTargetProfiles.model_id)
    $Python = Get-FullPath -Path $Python -BaseRoot $RepoRoot
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python executable not found: $Python" }
    $outputBase = Get-FullPath -Path $OutputRoot -BaseRoot $RepoRoot
    Assert-PathUnderRoot -RootPath (Join-Path $RepoRoot ".tmp_tests") -Path $outputBase `
        -Message "Live validation artifacts must stay under repository .tmp_tests: {0}"
} catch {
    Write-LiveUsageError -Domain autoscale -Message $_.Exception.Message
}
$layout = New-ValidationRunDirectory -BaseRoot $outputBase
$script:RunDirectory = $layout.Root
$script:RunRoot = $layout.Private
$script:ShareableRoot = $layout.Shareable

function Add-AutoCase {
    param([string] $Name, [ValidateSet("PASS", "FAIL", "N/A")][string] $Status, [string] $Detail)
    $script:CaseResults[$Name] = [pscustomobject]@{ Status = $Status; Detail = $Detail; Passed = ($Status -eq "PASS") }
    if ($Status -eq "FAIL") { $script:FunctionalFailed = $true }
    Write-CaseStatus -Status $Status -Name $Name -Context "[live][autoscale]"
    Write-Host "      $Detail"
}

function Add-Diagnostic {
    param([string] $Name, [string] $Message)
    if (-not $script:Diagnostics.Contains($Name)) { $script:Diagnostics[$Name] = [System.Collections.Generic.List[string]]::new() }
    $script:Diagnostics[$Name].Add($Message)
}

function Write-Summary {
    param([string] $Result)
    $lines = [System.Collections.Generic.List[string]]@(
        "# Scopes Tool Auto Scale / AutoSet Validation", "", "Result: $Result",
        "Target: $($script:Target)", "Connection: $($script:Connection)", "Backend: $($script:BackendName)", "",
        "| Case | Status | Detail |", "|---|---|---|"
    )
    foreach ($entry in $script:CaseResults.GetEnumerator()) {
        $detail = ([string]$entry.Value.Detail).Replace("|", "\|").Replace("`r", "").Replace("`n", "<br>")
        $lines.Add("| $($entry.Key) | $($entry.Value.Status) | $detail |")
    }
    foreach ($entry in $script:Diagnostics.GetEnumerator()) {
        $lines.Add("")
        $lines.Add("## $($entry.Key)")
        foreach ($message in $entry.Value) { $lines.Add("- " + $message.Replace("`r", "").Replace("`n", "<br>")) }
    }
    Write-Utf8NoBomLines -LiteralPath (Join-Path $script:RunRoot "summary.md") -Lines $lines.ToArray()
}

function Invoke-AutoCli {
    param([string] $Stage, [string] $Command, [string[]] $Options = @(),
        [ValidateSet("live", "simulate", "dry-run")][string] $Mode = "live", [switch] $AllowFailure)
    $modeArguments = if ($Mode -eq "live") {
        $script:HardwareTouched = $true
        $script:LiveConnectionArguments
    } else { @("--$Mode", "--model", $script:Target) }
    $arguments = @($Command) + @($modeArguments) + @("--json", "--log-scpi") + $Options
    $base = Join-Path $script:RunRoot ("cli-{0:D3}-{1}" -f ($script:Invocations.Count + 1), $Stage)
    $record = Invoke-CapturedCommand -Name $Stage -FilePath $Python `
        -Arguments (@("-m", "scopes_tool_cli.cli") + $arguments) `
        -StdOutPath "$base.stdout.txt" -StdErrPath "$base.stderr.txt" -JsonPath "$base.json" `
        -WorkingDirectory $RepoRoot -CaptureInMemory:(-not $DebugArtifacts)
    $payload = $record.payload
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage; command = "$Python -m scopes_tool_cli.cli"; arguments = $arguments
        exit_code = $record.exit_code; success = $record.success; duration_ms = $record.duration_ms
        stdout = $record.stdout; stderr = $record.stderr; json = $record.json
        scpi = if ($null -ne $payload) { $payload.scpi } else { $null }
        system_error = if ($null -ne $payload) { $payload.system_error } else { $null }
        result = if ($null -ne $payload -and $Command -eq "autoscale") { $payload.result } else { $null }
    })
    if (-not $AllowFailure) { Assert-AutoCliSuccess -Record $record }
    return $record
}

function Assert-AutoCliSuccess {
    param([object] $Record)
    if ($Record.exit_code -ne 0 -or $null -eq $Record.payload -or $Record.payload.ok -ne $true) {
        $errorDetail = Get-CliErrorDetail -Payload $Record.payload
        throw "$($Record.name) failed (exit $($Record.exit_code)): $errorDetail $($Record.stderr_text)"
    }
}

function Assert-AutoScpi {
    param([object] $Payload, [string] $Expected, [switch] $Planned)
    $commands = if ($Planned) { @($Payload.scpi.planned) } else { @($Payload.scpi.sent) }
    if ($commands -cnotcontains $Expected) { throw "Expected SCPI was not recorded: $Expected" }
}

function Convert-AutoStatusInteger {
    param([object] $Status)
    # PowerShell 7 parses JSON integers as Int64; the existing Tektronix
    # status validators use the Int32 values produced by Windows PowerShell.
    # Normalize only valid integer register values, preserving fail-closed checks.
    if ($null -ne $Status) {
        $property = $Status.PSObject.Properties["value"]
        if ($null -ne $property -and $property.Value -is [long] -and
            $property.Value -ge 0 -and $property.Value -le 255) { $Status.value = [int]$property.Value }
    }
}

function Test-AutoPreflight {
    # PyVISA's resource parser does not create a ResourceManager or open hardware.
    $source = @'
import sys
from pyvisa.rname import ResourceName
r = ResourceName.from_string(sys.argv[1])
assert r.interface_type == sys.argv[2].upper()
assert r.resource_class in (('INSTR',) if sys.argv[2] == 'usb' else ('INSTR', 'SOCKET'))
'@
    $parsed = Invoke-CapturedCommand -Name "resource-parse" -FilePath $Python `
        -Arguments @("-c", $source, $Resource, $script:Connection) `
        -StdOutPath (Join-Path $script:RunRoot "resource-parse.stdout.txt") `
        -StdErrPath (Join-Path $script:RunRoot "resource-parse.stderr.txt") `
        -WorkingDirectory $RepoRoot -CaptureInMemory:(-not $DebugArtifacts)
    if (-not $parsed.success) { throw "Invalid VISA resource: $($parsed.stderr_text)" }
    $sim = Invoke-AutoCli -Stage "preflight-identify" -Command identify -Mode simulate
    Assert-TargetModelMatch -Identity $sim.payload -ResolvedTarget $script:Target
    $script:ExpectedChannels = [int]$sim.payload.capabilities.analog_channels
    $script:ExpectedSeries = [string]$sim.payload.capabilities.series
    $options = @()
    if (-not $script:IsTektronix) { $options = @("--source-channel", "1") }
    foreach ($mode in @("dry-run", "simulate")) {
        $auto = Invoke-AutoCli -Stage "preflight-auto-$mode" -Command autoscale -Options $options -Mode $mode
        Assert-AutoScpi -Payload $auto.payload -Expected $script:ExpectedAuto -Planned:($mode -eq "dry-run")
        if ($mode -eq "dry-run" -and @($auto.payload.scpi.sent).Count -ne 0) { throw "Dry-run unexpectedly sent SCPI." }
    }
}

function Confirm-AutoOperator {
    param([object] $Identity)
    Write-Host ""
    Write-Host "Scopes Tool Auto Scale / AutoSet Live Validation"
    Write-Host "Detected instrument: $($Identity.idn.vendor) $($Identity.idn.model)"
    Write-Host "Target: $($script:Target)"
    Write-Host "Connection: $($script:Connection); backend: $($script:BackendName)"
    Write-Host "Auto operation: $(if ($script:IsTektronix) { 'autoscale (no optional controls)' } else { 'autoscale --source-channel 1' })"
    Write-Host "Expected command: $($script:ExpectedAuto)"
    Write-Host "A PASS result confirms Auto command execution and status checks; it does not prove optimal waveform scaling or signal recognition."
    Write-Host ""
    Write-Host "PHYSICAL SETUP"
    Write-Host "Connect a suitable, stable test signal to CH1 and confirm the probe attenuation matches the instrument setting."
    Write-Host "Remove unknown or sensitive DUT signals from all inputs."
    Write-Host "Auto may not correctly detect low-frequency, weak, narrow-pulse, or unstable signals."
    Write-Host ""
    Write-Host "POSSIBLE EFFECTS"
    Write-Host "Auto may enable/disable channels and change vertical scale/offset, timebase/delay, trigger, and acquisition settings."
    if ($script:IsTektronix) {
        Write-Host "On $($Identity.idn.model), AutoSet may also affect cursor, measurement, and Math state; these states are not restored."
        Write-Host "Reference and horizontal display state, where available, are outside this validator's restore coverage."
        Write-Host "RESTORE: Tektronix automatic restore is NOT attempted. Manually restore your required settings after the test."
    } else {
        Write-Host "On this Keysight model, cursor, measurement, Math, Reference, and Zoom state may be affected where those features apply."
        Write-Host "RESTORE: Keysight attempts only the supported local snapshot settings; full restoration is NOT guaranteed."
        Write-Host "Coverage: all analog channels' display, coupling, probe ratio, scale/offset; timebase scale/reference/position; acquisition type/active average count; trigger mode, holdoff, and current Edge source/slope/channel levels."
        Write-Host "Other channel settings, inactive average count, non-Edge trigger parameters, trigger filtering/sweep, cursor, measurement, Math, Reference, Zoom, Save To, and Run/Stop state are not restored."
        Write-Host "The CH1 command may fall back to bare :AUToscale. A successful fallback proves basic Auto only, not CH1 selection."
    }
    Write-Host "Error/event status reads can consume pending entries; baseline draining/clearing after confirmation discards existing diagnostic state."
    Write-Host "Errors and events cannot be restored. Restore failures are reported as FAIL. Review the report and manually recover any uncovered settings."
    if ($script:Target -eq "keysight-dsox4034a") {
        Write-Host 'DSO-X 4034A Auto may leave front-panel Save To at "Please Select". Reselect the USB destination if front-panel saving is needed.'
        Write-Host "This can also occur when Auto Scale is run directly from the front panel; it is not a Scopes Tool SAVE failure."
    }
    Write-Host ""
    Write-Host "Press Enter only after reviewing these warnings and preparing the physical setup. Any other input cancels."
    $response = Read-Host
    if ($response -isnot [string] -or $response.Length -ne 0) { throw "Operator confirmation was not given; only an explicit empty Enter continues." }
}

function Read-AutoStatus {
    param([string] $Stage, [switch] $Baseline)
    if ($script:IsTektronix) {
        if ($Baseline) {
            $before = Invoke-AutoCli -Stage "$Stage-before" -Command system-standard-event -Options @("--query")
            Add-Diagnostic -Name $Stage -Message ($before.payload.result | ConvertTo-Json -Compress)
            $null = Invoke-AutoCli -Stage "$Stage-clear" -Command system-clear-status
        }
        $event = Invoke-AutoCli -Stage $Stage -Command system-standard-event -Options @("--query")
        Convert-AutoStatusInteger -Status $event.payload.result
        $bits = Get-TektronixStandardEventValue -Payload $event.payload
        Add-Diagnostic -Name $Stage -Message "Native SESR value: $bits"
        if (($bits -band 60) -ne 0) { throw "Native SESR error bits CME/EXE/DDE/QYE set: $bits" }
    } else {
        $drain = Invoke-AutoCli -Stage $Stage -Command check-error -Options @("--all", "--max-reads", "30")
        $entries = @($drain.payload.result.entries)
        Add-Diagnostic -Name $Stage -Message ($entries | ConvertTo-Json -Depth 8 -Compress)
        if ($entries.Count -lt 1 -or [int]$entries[-1].code -ne 0) { throw "Error queue did not terminate with code 0." }
        if (-not $Baseline -and @($entries | Where-Object { [int]$_.code -ne 0 }).Count -gt 0) { throw "Instrument error queue contains Auto/restore errors; see diagnostics." }
    }
}

function Get-AutoSnapshot {
    param([int] $ChannelCount)
    # Local query/set/readback records follow the existing live CLI restore design.
    # No setup recall, fixture setup, or unrelated cleanup is used here.
    $steps = [System.Collections.Generic.List[object]]::new()
    function Save-Setting {
        param([string] $Name, [string] $Command, [string[]] $Base, [string[]] $Fields, [string[]] $SetOptions)
        $query = Invoke-AutoCli -Stage "snapshot-$Name" -Command $Command -Options ($Base + @("--query"))
        $values = @()
        foreach ($field in $Fields) {
            $property = $query.payload.result.PSObject.Properties[$field]
            if ($null -eq $property -or $null -eq $property.Value) { throw "Missing snapshot value: $Name.$field" }
            $value = $property.Value
            if ($value -is [double] -and ([double]::IsNaN($value) -or [double]::IsInfinity($value))) { throw "Non-finite snapshot value: $Name.$field" }
            $values += $value
        }
        $set = @($Base)
        switch ($Command) {
            "channel-display" { $set += $(if ($values[0]) { "--on" } else { "--off" }) }
            "acquisition" {
                $set += @("--type", [string]$values[0])
                if ($values[0] -eq "average") { $set += @("--count", [string]$values[1]) }
                else { $Fields = @("type"); $values = @($values[0]) }
            }
            "trigger-edge-source" {
                if ($values[0] -eq "analog-channel") {
                    $channel = $query.payload.result.source_channel
                    if ($null -eq $channel -or [int]$channel -lt 1 -or [int]$channel -gt $ChannelCount) { throw "Invalid Edge source channel snapshot." }
                    $set += @("--source-channel", [string]$channel)
                    $Fields += "source_channel"; $values += $channel
                } else { $set += @("--source", [string]$values[0]) }
            }
            default {
                $text = if ($values[0] -is [double]) { $values[0].ToString("R", [Globalization.CultureInfo]::InvariantCulture) } else { [string]$values[0] }
                # Equals form handles negative offset/delay/trigger values in argparse.
                $set += "$($SetOptions[0])=$text"
            }
        }
        $steps.Add([pscustomobject]@{ Name = $Name; Command = $Command; Base = $Base; Fields = $Fields; Values = $values; Set = $set })
        return $query.payload.result
    }
    for ($channel = 1; $channel -le $ChannelCount; $channel++) {
        $base = @("--channel", [string]$channel)
        foreach ($item in @(
            @("channel-probe", "probe_ratio", "--ratio"), @("channel-coupling", "coupling", "--coupling"),
            @("channel-scale", "volts_per_division", "--volts-per-division"), @("channel-offset", "volts", "--volts"),
            @("channel-display", "display", "--on")
        )) { $null = Save-Setting "ch$channel-$($item[0])" $item[0] $base @($item[1]) @($item[2]) }
    }
    foreach ($item in @(
        @("timebase-scale", "seconds_per_division", "--seconds-per-division"),
        @("timebase-reference", "reference", "--reference"), @("timebase-position", "position_seconds", "--seconds"),
        @("trigger-holdoff", "seconds", "--seconds")
    )) { $null = Save-Setting $item[0] $item[0] @() @($item[1]) @($item[2]) }
    $null = Save-Setting "acquisition" "acquisition" @() @("type", "count") @("--type")
    $mode = Save-Setting "trigger-mode" "trigger-mode" @() @("mode") @("--mode")
    # Restore original mode last, after any saved Edge parameters.
    $modeStep = $steps[$steps.Count - 1]; $steps.RemoveAt($steps.Count - 1)
    if ($mode.mode -eq "edge") {
        $null = Save-Setting "edge-source" "trigger-edge-source" @() @("source") @("--source")
        $null = Save-Setting "edge-slope" "trigger-edge-slope" @() @("slope") @("--slope")
        for ($channel = 1; $channel -le $ChannelCount; $channel++) {
            $null = Save-Setting "edge-level-ch$channel" "trigger-edge-level" @("--source-channel", [string]$channel) @("level_volts") @("--level-volts")
        }
    } else { Add-Diagnostic -Name "restore-limitations" -Message "Original trigger mode is $($mode.mode); its non-Edge parameters are not snapshotted or restored." }
    $steps.Add($modeStep)
    return $steps.ToArray()
}

function Restore-AutoSnapshot {
    param([object[]] $Snapshot)
    $failures = [System.Collections.Generic.List[string]]::new()
    foreach ($step in $Snapshot) {
        try {
            $null = Invoke-AutoCli -Stage "restore-$($step.Name)" -Command $step.Command -Options $step.Set
            $query = Invoke-AutoCli -Stage "readback-$($step.Name)" -Command $step.Command -Options ($step.Base + @("--query"))
            for ($index = 0; $index -lt $step.Fields.Count; $index++) {
                $actualProperty = $query.payload.result.PSObject.Properties[$step.Fields[$index]]
                if ($null -eq $actualProperty -or $null -eq $actualProperty.Value) { throw "Missing restore readback: $($step.Fields[$index])" }
                $actual = $actualProperty.Value; $expected = $step.Values[$index]
                $matches = if ($expected -is [double]) {
                    $number = [double]$actual
                    -not [double]::IsNaN($number) -and -not [double]::IsInfinity($number) -and
                    [math]::Abs($number - $expected) -le [math]::Max(1e-12, [math]::Abs($expected) * 1e-6)
                } else { $actual -ceq $expected }
                if (-not $matches) { throw "Restore readback differs from snapshot: $($step.Fields[$index])" }
            }
            Add-Diagnostic -Name "restore-steps" -Message "PASS $($step.Name): set and readback matched snapshot."
        } catch {
            $detail = "$($step.Name): $($_.Exception.Message)"
            $failures.Add($detail)
            Add-Diagnostic -Name "restore-steps" -Message "FAIL $detail"
        }
    }
    if ($failures.Count -gt 0) { throw ($failures -join " | ") }
}

function Invoke-AutoCheck {
    $options = @()
    if (-not $script:IsTektronix) { $options = @("--source-channel", "1") }
    $auto = Invoke-AutoCli -Stage "auto" -Command autoscale -Options $options -AllowFailure
    $payload = $auto.payload
    if ($null -eq $payload) {
        Add-Diagnostic -Name "auto" -Message "Actual commands and fallback are unavailable: Auto returned no valid CLI JSON; CLI exit: $($auto.exit_code)."
        Write-Host "Actual commands/fallback: unavailable (invalid CLI JSON); CLI exit: $($auto.exit_code)"
        throw "Auto returned no valid CLI JSON."
    }
    $fallbackProperty = $payload.result.PSObject.Properties["fallback"]
    $fallback = if ($null -ne $fallbackProperty) { [string]$fallbackProperty.Value } else { "none" }
    $commands = @($payload.result.commands)
    if ($fallback -eq "none" -and ($commands -ccontains ":AUToscale" -or @($payload.scpi.sent) -ccontains ":AUToscale")) {
        $fallback = "bare_autoscale_observed_without_marker"
    }
    Add-Diagnostic -Name "auto" -Message "Actual commands: $($commands -join '; '); fallback: $fallback; CLI exit: $($auto.exit_code)"
    Write-Host "Actual commands: $($commands -join '; '); fallback: $fallback; CLI exit: $($auto.exit_code)"
    Assert-AutoCliSuccess -Record $auto
    Assert-AutoScpi -Payload $payload -Expected $script:ExpectedAuto
    if ($script:IsTektronix) {
        Convert-AutoStatusInteger -Status $payload.result.post_command_status
        Assert-TektronixCommandStatus -Payload $payload
        if ($commands.Count -ne 1 -or $commands[0] -cne $script:ExpectedAuto) { throw "Unexpected Tektronix AutoSet commands or optional controls." }
    } else {
        if ($null -eq $payload.system_error -or ($payload.system_error.code -isnot [int] -and $payload.system_error.code -isnot [long]) -or
            $payload.system_error.code -ne 0 -or $payload.system_error.is_error -ne $false -or
            [string]::IsNullOrWhiteSpace($payload.system_error.raw)) { throw "Missing or error-bearing Keysight Auto status." }
        if ($fallback -ne "none" -or $commands -ccontains ":AUToscale" -or @($payload.scpi.sent) -ccontains ":AUToscale") {
            Assert-AutoScpi -Payload $payload -Expected ":AUToscale"
            Add-AutoCase "auto-ch1" "N/A" "CH1 selection was rejected or bypassed; fallback: $fallback. Basic Auto result is separate."
        } else {
            if ($commands.Count -ne 1 -or $commands[0] -cne $script:ExpectedAuto -or @($payload.result.source_channels).Count -ne 1 -or $payload.result.source_channels[0] -ne 1) { throw "CH1 Auto command/result does not match the request." }
        }
    }
    Read-AutoStatus -Stage "post-auto-status"
    Add-AutoCase "auto-basic" "PASS" "Auto command, CLI result, and post-Auto instrument error/event state are clean."
    if (-not $script:IsTektronix -and -not $script:CaseResults.Contains("auto-ch1")) {
        Add-AutoCase "auto-ch1" "PASS" "Requested CH1 command and clean CLI instrument status confirmed; no fallback."
    }
}

$script:ExpectedAuto = if ($script:IsTektronix) { "AUTOSet EXECute" } else { ":AUToscale CHANnel1" }
$snapshot = @()
$autoStarted = $false
$stage = "preflight"
try {
    Test-AutoPreflight
    Add-AutoCase "preflight" "PASS" "Resource syntax, simulated identity, and basic Auto dry-run/simulation passed; no hardware accessed."
    $stage = "identify"
    $identity = Invoke-AutoCli -Stage identify -Command identify
    Assert-TargetModelMatch -Identity $identity.payload -ResolvedTarget $script:Target
    if (-not $script:IsTektronix -and $identity.payload.idn.vendor -notmatch '^(?i)(Keysight|Agilent)( Technologies)?$') { throw "Detected vendor does not match the Keysight target." }
    if ([int]$identity.payload.capabilities.analog_channels -ne $script:ExpectedChannels -or
        [string]$identity.payload.capabilities.series -cne $script:ExpectedSeries) { throw "Detected channel count or series differs from the registered target." }
    Add-AutoCase "identify" "PASS" "$($identity.payload.idn.vendor) $($identity.payload.idn.model) matched target."
    $stage = "operator-confirmation"
    Confirm-AutoOperator -Identity $identity.payload
    Add-AutoCase "operator-confirmation" "PASS" "Operator explicitly pressed Enter after reviewing the warnings."
    Add-Diagnostic -Name "restore-limitations" -Message $(if ($script:IsTektronix) { "Tektronix automatic restore is not attempted; manually recover all required settings." } else { "Only the listed Channel/Timebase/Trigger/Acquisition snapshot settings are restored. Other channel settings, inactive average count, non-Edge parameters, trigger filtering/sweep, cursor, measurement, Math, Reference, Zoom, Save To, and Run/Stop state are not restored; errors/events cannot be restored." })
    $stage = "status-baseline"
    Read-AutoStatus -Stage $stage -Baseline
    Add-AutoCase $stage "PASS" "Pre-existing error/event state recorded and drained/cleared after confirmation."
    if (-not $script:IsTektronix) {
        $stage = "snapshot"
        $snapshot = @(Get-AutoSnapshot -ChannelCount ([int]$identity.payload.capabilities.analog_channels))
        Add-AutoCase $stage "PASS" "Supported local settings saved for all analog channels; $($snapshot.Count) restore steps."
    }
    $stage = "auto-basic"
    $autoStarted = $true
    Invoke-AutoCheck
} catch {
    Add-AutoCase $stage "FAIL" $_.Exception.Message
    if ($stage -eq "auto-basic" -and -not $script:IsTektronix -and -not $script:CaseResults.Contains("auto-ch1")) {
        Add-AutoCase "auto-ch1" "FAIL" "Requested CH1 Auto was not verified; see Auto failure."
    }
} finally {
    if ($autoStarted -and -not $script:IsTektronix) {
        $restoreErrors = [System.Collections.Generic.List[string]]::new()
        try {
            Restore-AutoSnapshot -Snapshot $snapshot
        } catch { $restoreErrors.Add($_.Exception.Message) }
        try { Read-AutoStatus -Stage "post-restore-status" }
        catch { $restoreErrors.Add($_.Exception.Message) }
        if ($restoreErrors.Count -eq 0) {
            Add-AutoCase "restore" "PASS" "All $($snapshot.Count) supported snapshot steps matched readback; partial coverage only, not full instrument restoration."
        } else { Add-AutoCase "restore" "FAIL" ($restoreErrors -join " | ") }
    } else { Add-AutoCase "restore" "N/A" $(if ($script:IsTektronix) { "Not attempted: Tektronix automatic restore is not supported by this validator." } else { "Not attempted: Auto was not executed." }) }
    if ($autoStarted -and $script:Target -eq "keysight-dsox4034a") {
        $note = 'DSO-X 4034A Auto may leave Save To at "Please Select", including after front-panel Auto Scale; this is not a Scopes Tool SAVE failure. Manually reselect the USB destination if needed.'
        Add-Diagnostic -Name "manual-action" -Message $note
        Write-Host $note
    }
    Write-Host ""
    Write-Host "Summary"
    $counts = @{ PASS = 0; FAIL = 0; 'N/A' = 0 }
    foreach ($entry in $script:CaseResults.GetEnumerator()) {
        $counts[$entry.Value.Status]++
        Write-CaseStatus -Status $entry.Value.Status -Name $entry.Key -Context "[live][autoscale]"
        Write-Host "      $($entry.Value.Detail)"
    }
    Write-Host "Totals: $($counts.PASS) PASS / $($counts.FAIL) FAIL / $($counts['N/A']) N/A"
    foreach ($message in @($script:Diagnostics['restore-limitations'])) { Write-Host "Manual review: $message" }
    $result = if ($script:FunctionalFailed) { "FAIL" } else { "PASS" }
    Complete-LiveValidationRun -Kind "scopes-tool-live-autoscale-check" -Domain autoscale -Result $result -DebugArtifacts:$DebugArtifacts
}
if ($script:FunctionalFailed -or $script:ShareableGenerationFailed) { exit 1 }
exit 0
