# Private helpers for the public CLI and workflow live validators.

function Get-CliErrorDetail {
    param([AllowNull()][object]$Payload)

    if ($null -eq $Payload) { return "" }
    $errorProperty = $Payload.PSObject.Properties["error"]
    if ($null -eq $errorProperty -or $null -eq $errorProperty.Value) { return "" }
    $cliError = $errorProperty.Value
    $errorType = ""
    $errorMessage = ""
    if ($null -ne $cliError.PSObject.Properties["type"]) { $errorType = [string]$cliError.type }
    if ($null -ne $cliError.PSObject.Properties["message"]) { $errorMessage = [string]$cliError.message }
    if ([string]::IsNullOrWhiteSpace($errorType) -and [string]::IsNullOrWhiteSpace($errorMessage)) { return "" }
    return @($errorType, $errorMessage | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ": "
}

function Assert-TektronixCommandStatus {
    param([Parameter(Mandatory = $true)][object]$Payload)

    $status = $Payload.result.post_command_status
    if ($null -eq $status -or $status.value -isnot [int] -or
        $status.value -lt 0 -or $status.value -gt 255 -or
        ($status.value -band 60) -ne 0 -or [string]::IsNullOrWhiteSpace($status.raw)) {
        throw "Missing, invalid, or error-bearing native command status."
    }
}

function Assert-TektronixWorkflowStatus {
    param([Parameter(Mandatory = $true)][object]$Payload)

    Assert-TektronixCommandStatus -Payload $Payload
    $status = $Payload.result.post_command_status
    if ($null -ne $Payload.system_error -or $status.source -cne "tektronix-sesr" -or
        $status.complete -cne $true -or $status.is_error -cne $false -or
        $status.destructive_read -cne $true -or
        [string]::IsNullOrWhiteSpace($status.event_raw) -or $null -eq $status.events) {
        throw "Native workflow status must contain a complete, clean SESR/event cohort."
    }
}

function Assert-TektronixCliOptions {
    param([System.Collections.IDictionary]$BoundParameters)

    $profile = Get-ValidationTargetProfile -Target $script:Target -IncludeTektronix
    if ($IncludeStorageWrites -and (-not $BoundParameters.ContainsKey("SetupSlot") -or
                                    -not $BoundParameters.ContainsKey("ReferenceSlot"))) {
        Write-LiveUsageError -Domain "tektronix" "Storage writes require explicit -SetupSlot (1..9) and -ReferenceSlot (1..2)."
    }
    if (-not $IncludeStorageWrites -and ($BoundParameters.ContainsKey("SetupSlot") -or
                                        $BoundParameters.ContainsKey("ReferenceSlot") -or
                                        $BoundParameters.ContainsKey("ImageFilename") -or
                                        $BoundParameters.ContainsKey("WaveformFilename") -or
                                        $BoundParameters.ContainsKey("WaveformSourceChannel"))) {
        Write-LiveUsageError -Domain "tektronix" "Storage slots and filenames require -IncludeStorageWrites."
    }
    if ($BoundParameters.ContainsKey("WaveformFilename") -or $BoundParameters.ContainsKey("WaveformSourceChannel")) {
        if ([string]::IsNullOrWhiteSpace($WaveformFilename) -or
            -not $BoundParameters.ContainsKey("WaveformSourceChannel") -or
            $WaveformSourceChannel -gt $profile.channels -or
            $WaveformFilename -match '[^\x20-\x7E]|[";*?%]' -or
            $WaveformFilename.EndsWith("/") -or $WaveformFilename.EndsWith("\")) {
            Write-LiveUsageError -Domain "tektronix" "Waveform save requires a safe explicit filename and a model-valid -WaveformSourceChannel."
        }
    }
}

function Invoke-TektronixCliValidation {
    $profile = Get-ValidationTargetProfile -Target $script:Target -IncludeTektronix
    $pythonPath = Get-FullPath -Path $Python -BaseRoot $RepoRoot
    $script:RunPaths = [pscustomobject]@{ Private = $script:RunRoot }
    $script:Failure = $false
    $script:StopAfterIdentity = $false
    $script:AcquisitionFinalState = "Acquisition actions not requested; configuration side effects are reported separately"

    function Add-Case {
        param([string]$Name, [ValidateSet("PASS", "FAIL", "N/A")][string]$Status, [string]$Detail = "")
        $script:CaseResults[$Name] = [pscustomobject]@{
            Passed = ($Status -eq "PASS"); Status = $Status; Detail = $Detail
        }
        Write-CaseStatus -Status $Status -Name $Name -Context "[live][tektronix]"
        if (-not [string]::IsNullOrWhiteSpace($Detail)) {
            Write-Host "      ${Detail}"
        }
        if ($Status -eq "FAIL") { $script:Failure = $true }
    }

    function Invoke-Cli {
        param([string]$Stage, [string]$Command, [string[]]$Options = @(), [switch]$AllowCurrentStateNA, [switch]$ExpectHiddenCaptureRejection, [switch]$Simulate)
        $script:CliInvocationIndex += 1
        $stem = "cli-{0:D3}-{1}" -f $script:CliInvocationIndex, (New-SafeCaseName -Name $Stage)
        $stdoutPath = Join-Path $script:RunPaths.Private "$stem.stdout.txt"
        $stderrPath = Join-Path $script:RunPaths.Private "$stem.stderr.txt"
        $jsonPath = Join-Path $script:RunPaths.Private "$stem.json"
        $modeArguments = if ($Simulate) { @("--simulate", "--model", $script:Target) } else { $script:LiveConnectionArguments }
        $args = @("-m", "scopes_tool_cli.cli", $Command, "--json") + @($Options) + @($modeArguments)
        $psi = [System.Diagnostics.ProcessStartInfo]::new()
        $psi.FileName = $pythonPath
        $psi.Arguments = Join-ProcessArguments -Arguments $args
        $psi.WorkingDirectory = $RepoRoot
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $start = Get-Date
        $process = [System.Diagnostics.Process]::Start($psi)
        if (-not $Simulate) { $script:HardwareTouched = $true }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(30000)) {
            $process.Kill()
            $process.WaitForExit()
            $timedOut = $true
        } else { $timedOut = $false }
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        Write-Utf8NoBomText -LiteralPath $stdoutPath -Text $stdout
        Write-Utf8NoBomText -LiteralPath $stderrPath -Text $stderr
        $record = [ordered]@{
            exit_code = $process.ExitCode
            duration_ms = [math]::Round(((Get-Date) - $start).TotalMilliseconds, 3)
            success = (-not $timedOut -and $process.ExitCode -eq 0)
            stderr = $stderrPath
            json = ""
        }
        if (-not [string]::IsNullOrWhiteSpace($stdout)) {
            try {
                $parsed = $stdout | ConvertFrom-Json -ErrorAction Stop
                Write-JsonReport -LiteralPath $jsonPath -Report $parsed
                $record.json = $jsonPath
            } catch { }
        }
        $cliErrorDetail = ""
        if ($record.json) { $cliErrorDetail = Get-CliErrorDetail -Payload $parsed }
        if (-not [string]::IsNullOrWhiteSpace($cliErrorDetail)) { $cliErrorDetail = "; $cliErrorDetail" }
        $invocation = [ordered]@{
            index = $script:CliInvocationIndex
            command = "$pythonPath -m scopes_tool_cli.cli"
            stage = $Stage
            arguments = @($args | Select-Object -Skip 2)
            exit_code = $record.exit_code
            duration_ms = $record.duration_ms
            success = $record.success
            result = if ($record.success) { "PASS" } else { "FAIL" }
            stdout = Get-ArtifactRelativePath -Path $stdoutPath -BaseRoot $RepoRoot
            stderr = Get-ArtifactRelativePath -Path ([string]$record.stderr) -BaseRoot $RepoRoot
            json = Get-ArtifactRelativePath -Path ([string]$record.json) -BaseRoot $RepoRoot
        }
        $script:Invocations.Add($invocation)
        if ($AllowCurrentStateNA -and -not $timedOut -and $record.exit_code -eq 1 -and $record.json -and
            $parsed.ok -eq $false -and $null -ne $parsed.PSObject.Properties["error"]) {
            $cliError = $parsed.error
            # Only these Core preconditions indicate an inapplicable current state.
            if (($Stage -ceq "math-operator-before" -and $Command -ceq "math-operator" -and
                 $cliError.type -ceq "OscilloscopeError" -and
                 ([string]$cliError.message).StartsWith("Unsupported Tek Math expression: ", [StringComparison]::Ordinal)) -or
                ($Stage -ceq "cursor-set" -and $Command -ceq "cursor" -and
                 $cliError.type -ceq "ParameterValidationError" -and
                 $cliError.message -ceq "X cursors require existing seconds units")) {
                $invocation.result = "N/A"
                return $null
            }
        }
        if ($ExpectHiddenCaptureRejection) {
            if (-not $timedOut -and $record.exit_code -eq 1 -and $record.json -and
                $parsed.ok -eq $false -and $null -ne $parsed.PSObject.Properties["error"] -and
                $parsed.error.type -ceq "WaveformResponseError" -and
                $parsed.error.message -ceq "CH$($Options[1]) is not displayed; waveform capture requires a displayed analog channel") {
                $invocation.result = "PASS"
                return $parsed
            }
            $invocation.result = "FAIL"
            throw "$Stage did not return the expected hidden-channel capture rejection."
        }
        if (-not $record.success -or -not $record.json) {
            $invocation.result = "FAIL"
            throw "$Stage failed (exit $($record.exit_code), timeout=$timedOut)$cliErrorDetail; see $stdoutPath and $stderrPath"
        }
        $payload = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json -ErrorAction Stop
        if ($payload.ok -ne $true) {
            $invocation.result = "FAIL"
            throw "$Stage returned ok=false$cliErrorDetail; see $jsonPath"
        }
        if ($Command -in @("run", "stop-acquisition")) {
            Assert-TektronixCommandStatus -Payload $payload
        }
        return $payload
    }

    function Invoke-CoreProfileProbe {
        # Validation tooling consumes Core support metadata instead of maintaining
        # a second operation-support matrix.
        $probePath = Join-Path $script:RunPaths.Private "core-profile-probe.py"
        $source = @'
import json, sys
from scopes_tool_core.capabilities import capabilities_for_model_id

capabilities = capabilities_for_model_id(sys.argv[1])
print(json.dumps({
    "supported_operations": sorted(capabilities.supported_operations or ()),
    "cursor_source_selection": capabilities.cursor_source_selection,
    "acquisition_modes": list(capabilities.acquisition_modes or ()),
    "average_counts": list(capabilities.average_counts or ()),
}))
'@
        Write-Utf8NoBomText -LiteralPath $probePath -Text $source
        $stderrPath = Join-Path $script:RunPaths.Private "core-profile-probe.stderr.txt"
        $output = & $pythonPath $probePath $script:Target 2> $stderrPath
        if ($LASTEXITCODE -ne 0) { throw "Core profile probe failed; see $stderrPath" }
        Write-Utf8NoBomText -LiteralPath (Join-Path $script:RunPaths.Private "core-profile.json") -Text ($output -join "`n")
        return ($output -join "`n" | ConvertFrom-Json)
    }

    function Add-UnsupportedOperationCase {
        param([string]$Name, [string]$Operation = "", [string]$Detail = "Unsupported on this model")
        if ([string]::IsNullOrWhiteSpace($Operation)) { $Operation = $Name }
        if (@($script:CoreProfile.supported_operations) -contains $Operation) {
            Add-Case $Name "FAIL" "Validation runner drift: Core declares '$Operation' supported for $($script:Target)."
        } else {
            Add-Case $Name "N/A" $Detail
        }
    }

    function Get-Readback {
        param([object]$Payload, [string]$Field)
        if ($null -eq $Payload.result) { throw "Missing result object." }
        $property = $Payload.result.PSObject.Properties[$Field]
        if ($null -eq $property -or $null -eq $property.Value) { throw "Missing $Field readback." }
        return $property.Value
    }

    function Test-ReadbackEqual {
        param($Expected, $Actual)
        if ($Expected -is [bool]) { return $Actual -is [bool] -and $Expected -eq $Actual }
        if ($Expected -is [ValueType] -and $Actual -is [ValueType]) {
            $a = [double]$Expected
            $b = [double]$Actual
            return [math]::Abs($a - $b) -le (1e-6 * [math]::Max(1e-12, [math]::Abs($a)))
        }
        return [string]$Expected -ceq [string]$Actual
    }

    function Invoke-RoundTrip {
        param([string]$Name, [string]$Command, [string[]]$Base = @(), [string]$Field,
              [string]$SetOption, [string[]]$Allowed = @())
        $original = $null
        $setAttempted = $false
        $status = "PASS"
        $detail = "query, same-value set, and readback"
        try {
            $before = Invoke-Cli -Stage "$Name-before" -Command $Command -Options (@($Base) + "--query")
            $original = Get-Readback -Payload $before -Field $Field
            $value = [string]$original
            if ($Allowed.Count -gt 0 -and $value -notin $Allowed) {
                $status = "N/A"
                $detail = "current instrument state outside supported acceptance precondition"
            } elseif ($Command -eq "save-pwd" -and [string]::IsNullOrWhiteSpace($value)) {
                $status = "N/A"
                $detail = "current readback cannot be safely written through the public setter"
            } elseif ($Command -eq "save-pwd" -and
                      ($value -match '[^\x20-\x7E]' -or $value.Contains('"') -or $value.Contains(';'))) {
                $status = "N/A"
                $detail = "current path is outside the public setter's accepted characters"
            } elseif ($Command -eq "channel-label" -and $value -match '[^\x20-\x7E]|"') {
                $status = "N/A"
                $detail = "current label is outside the public setter's accepted characters"
            } elseif ($Name -eq "trigger-holdoff" -and
                      ([double]$original -lt $(if ($script:Target -eq "tektronix-tbs2074") { 2e-8 } else { 5e-7 }) -or
                       [double]$original -gt $(if ($script:Target -eq "tektronix-tbs2074") { 8 } else { 10 }))) {
                $status = "N/A"
                $detail = "current holdoff is outside the model's supported setter range"
            } elseif ($Name -eq "channel-probe" -and $script:Target -ne "tektronix-tbs2074" -and
                      [double]$original -notin @(1, 10, 20, 50, 100, 500, 1000)) {
                $status = "N/A"
                $detail = "current probe ratio is outside the TDS2000B/TBS1000B supported subset"
            } else {
                if ($original -is [bool]) {
                    $setValue = if ($original) { "--on" } else { "--off" }
                    if ($SetOption -eq "--state") { $setValue = if ($original) { "on" } else { "off" } }
                }
                elseif ($original -is [ValueType]) { $setValue = ([double]$original).ToString("R", [Globalization.CultureInfo]::InvariantCulture) }
                else { $setValue = $value }
                $setAttempted = $true
                $setArgs = if ($original -is [bool] -and $SetOption -ne "--state") {
                    @($Base) + $setValue
                } else { @($Base) + $SetOption + $setValue }
                $null = Invoke-Cli -Stage "$Name-same-value" -Command $Command -Options $setArgs
                $after = Invoke-Cli -Stage "$Name-after" -Command $Command -Options (@($Base) + "--query")
                $actual = Get-Readback -Payload $after -Field $Field
                if (-not (Test-ReadbackEqual -Expected $original -Actual $actual)) {
                    throw "Readback differs after same-value setter."
                }
            }
        } catch {
            $status = "FAIL"
            $detail = $_.Exception.Message
        } finally {
            if ($setAttempted) {
                try {
                    $null = Invoke-Cli -Stage "$Name-restore" -Command $Command -Options $setArgs
                    $restored = Invoke-Cli -Stage "$Name-restored" -Command $Command `
                        -Options (@($Base) + "--query")
                    if (-not (Test-ReadbackEqual -Expected $original `
                        -Actual (Get-Readback -Payload $restored -Field $Field))) {
                        throw "Restore readback differs from original."
                    }
                } catch {
                    $status = "FAIL"
                    $detail += "; restore failed: $($_.Exception.Message)"
                }
            }
        }
        Add-Case -Name $Name -Status $status -Detail $detail
    }

    function Invoke-SimpleCase {
        param([string]$Name, [string]$Command, [string[]]$Options = @())
        try {
            $null = Invoke-Cli -Stage $Name -Command $Command -Options $Options
            Add-Case -Name $Name -Status "PASS"
        } catch {
            Add-Case -Name $Name -Status "FAIL" -Detail $_.Exception.Message
        }
    }

    function Invoke-SameValueCase {
        param([string]$Name, [string]$Command, [object]$Before,
              [string[]]$Options, [string[]]$Fields, [string[]]$Base = @())
        # Callers supply only settings already read from the current instrument state.
        $null = Invoke-Cli -Stage "$Name-same-value" -Command $Command -Options (@($Base) + $Options)
        $after = Invoke-Cli -Stage "$Name-after" -Command $Command -Options (@($Base) + "--query")
        foreach ($field in $Fields) {
            if (-not (Test-ReadbackEqual (Get-Readback $Before $field) (Get-Readback $after $field))) {
                throw "$field readback differs after same-value setter."
            }
        }
        Add-Case $Name "PASS" "query, same-value set, and readback"
    }

    function Format-Setting {
        param($Value)
        if ($Value -is [bool]) { return $Value.ToString().ToLowerInvariant() }
        if ($Value -is [ValueType]) {
            return ([double]$Value).ToString("R", [Globalization.CultureInfo]::InvariantCulture)
        }
        return [string]$Value
    }

    function Write-OperatorSection {
        param([string]$Title, [System.Collections.Generic.List[string]]$Lines)

        Write-Host ""
        Write-Host $Title
        foreach ($line in $Lines) { Write-Host "  - ${line}" }
    }

    function Confirm-OperatorContinuation {
        # Only an explicit empty Enter continues. Whitespace-only input, any other
        # text, a null result, an unreadable prompt, or a non-interactive host all
        # stop the run before any further functional command touches the
        # instrument. The wording below describes what this runner really does;
        # it deliberately avoids raw SCPI so the runner stays CLI-only.
        param([object]$DetectedModel)

        $physicalPreparation = [System.Collections.Generic.List[string]]@(
            "Confirm the correct oscilloscope is connected.",
            "Disconnect unknown or sensitive DUT signals, and any signal the test must not disturb.",
            "Default checks use the instrument's current state; a fixed CH1/CH2 Probe Comp fixture is not required."
        )
        if ($IncludeConfigurationActions) {
            $physicalPreparation.Add(
                "Connect a suitable, stable signal to CH1 (for example, the oscilloscope's Probe Comp / Demo output).")
            $physicalPreparation.Add(
                "Ensure CH1 display is ON and a stable waveform is visible. Measurement and capture checks require CH1 to be displayed.")
        }
        if ($IncludeStorageWrites) {
            $physicalPreparation.Add(
                "Reference Save requires CH1 display ON; otherwise the reference-save case is N/A.")
        }
        if ($IncludeStorageWrites -and
            (-not [string]::IsNullOrWhiteSpace($ImageFilename) -or
             -not [string]::IsNullOrWhiteSpace($WaveformFilename))) {
            $physicalPreparation.Add(
                "Confirm the required instrument storage is available and writable before saving files.")
        }

        $defaultActions = [System.Collections.Generic.List[string]]@(
            "Read the instrument status byte.",
            "Read the Standard Event Status register; that read is destructive and clears it.",
            "Send a status clear, which discards the current status and event state.",
            "Query the current channel, timebase, acquisition, and trigger settings.",
            "Perform supported same-value setters, read each value back, then attempt to restore the original value.",
            "Report a case as N/A when the model or the current instrument state is outside the supported subset, instead of changing state to force a result."
        )

        $cleanupLimitations = [System.Collections.Generic.List[string]]@(
            "Same-value setters are real instrument writes, not read-only checks.",
            "Not every setting is guaranteed to be fully restored.",
            "Status reads and the status clear may consume or discard existing error and event state that was pending before validation.",
            "Waveform transfer settings have no public restore path and may remain changed."
        )

        $acquisitionNote = if ($IncludeAcquisitionActions) {
            "Run/Stop state changes; cleanup sends stop without an independent Running/Stopped readback, and the original state is not restored."
        } else { "Not requested." }
        $autoscaleNote = if ($IncludeAutoscale) {
            "Changes multiple front-panel settings and is not restored."
        } else { "Not requested." }
        $configurationNote = if ($IncludeConfigurationActions) {
            $text = "Runs measurement, BYTE waveform capture, and cursor actions. Cursor mode may end OFF, measurement configuration may end cleared, and waveform transfer settings are not restored."
            if ($script:Target -eq "tektronix-tbs2074") {
                $text += " TBS2074 cursor source selection may display CH1 or restart acquisition through Core."
            }
            $text
        } else { "Not requested." }
        $storageNote = if ($IncludeStorageWrites) {
            $text = "Setup slot $SetupSlot and reference slot $ReferenceSlot may be overwritten."
            if (-not [string]::IsNullOrWhiteSpace($ImageFilename)) {
                $text += " Requested instrument image file '$ImageFilename' may be overwritten."
            }
            if (-not [string]::IsNullOrWhiteSpace($WaveformFilename)) {
                $text += " Requested instrument waveform file '$WaveformFilename' may be overwritten."
            }
            $text
        } else { "Not requested." }
        $screenshotNote = if (-not $IncludeScreenshot) {
            "Not requested."
        } elseif ($script:Target -eq "tektronix-tbs2074") {
            "PNG screenshot; Core writes a temporary instrument file and attempts to delete it during cleanup."
        } elseif ($script:Target -eq "tektronix-tds2024b") {
            "BMP screenshot is attempted only with a USBTMC instrument resource; otherwise this case is N/A."
        } else {
            "No screenshot format is supported on this model; no screenshot file is written."
        }

        $optionalActions = [System.Collections.Generic.List[string]]@(
            "Acquisition: ${acquisitionNote}",
            "Autoscale: ${autoscaleNote}",
            "Configuration: ${configurationNote}",
            "Storage Writes: ${storageNote}",
            "Screenshot: ${screenshotNote}"
        )

        Write-Host ""
        Write-Host "--------------------------------------------------"
        Write-Host "Scopes Tool Tektronix Live Validation"
        Write-Host ""
        Write-Host "Detected instrument: $DetectedModel"
        Write-Host "Target: $($script:Target)"
        Write-Host "Connection: $($script:Connection)"

        Write-OperatorSection -Title "PRE-VALIDATION" -Lines ([System.Collections.Generic.List[string]]@(
            "Hardware-free preflight passed.",
            "Live instrument identity matches the selected target."
        ))
        Write-OperatorSection -Title "PHYSICAL PREPARATION" -Lines $physicalPreparation
        Write-OperatorSection -Title "DEFAULT VALIDATION ACTIONS" -Lines $defaultActions
        Write-OperatorSection -Title "STATE / CLEANUP LIMITATIONS" -Lines $cleanupLimitations
        Write-OperatorSection -Title "OPTIONAL ACTIONS" -Lines $optionalActions
        Write-Host ""
        Write-Host "Press Enter only after reviewing the information above."
        Write-Host "Any other input cancels validation."
        Write-Host "Ctrl+C to abort."
        Write-Host ""

        $response = $null
        $reason = ""
        try {
            $response = Read-Host
        } catch {
            $reason = "Operator confirmation could not be read: $($_.Exception.Message)"
        }
        if ([string]::IsNullOrWhiteSpace($reason)) {
            # Fail closed: only an actual empty string counts as an explicit Enter.
            if ($response -is [string] -and $response.Length -eq 0) {
                Add-Case -Name "operator-confirmation" -Status "PASS" `
                    -Detail "Operator confirmed after live identity and target match"
                return $true
            }
            $reason = "Operator confirmation was not given; only an explicit empty Enter continues."
        }
        Add-Case -Name "operator-confirmation" -Status "FAIL" -Detail $reason
        # Reuse the identity gate so no later functional command runs.
        $script:StopAfterIdentity = $true
        return $false
    }

    try {
        $script:CoreProfile = Invoke-CoreProfileProbe
        $preflight = Invoke-Cli -Stage "preflight-identify" -Command "identify" -Simulate
        Assert-TargetModelMatch -Identity $preflight -ResolvedTarget $script:Target
        Add-Case "preflight" "PASS" "Selected model CLI simulation; no hardware accessed"
    } catch {
        Add-Case "preflight" "FAIL" $_.Exception.Message
        $script:FunctionalFailed = $true
        Complete-LiveValidationRun -Kind 'scopes-tool-live-cli-check' -Domain 'cli' -Result "FAIL"
        return
    }

    try {
        # The first live invocation is identify. No state-changing case may precede this gate.
        $detectedModel = ""
        try {
            $identity = Invoke-Cli -Stage "identify" -Command "identify"
            Assert-TargetModelMatch -Identity $identity -ResolvedTarget $script:Target
            $expected = $profile
            $modelProperty = $identity.PSObject.Properties["idn"]
            if ($null -ne $modelProperty -and $null -ne $modelProperty.Value) {
                $detectedModelName = $modelProperty.Value.PSObject.Properties["model"]
                if ($null -ne $detectedModelName) { $detectedModel = [string]$detectedModelName.Value }
            }
            if ([string]::IsNullOrWhiteSpace($detectedModel)) { $detectedModel = [string]$profile.model }
            Add-Case -Name "identify" -Status "PASS" -Detail "Tektronix $($expected.model), $($expected.channels) channels"
        } catch {
            Add-Case -Name "identify" -Status "FAIL" -Detail $_.Exception.Message
            $script:StopAfterIdentity = $true
        }
        if (-not $script:StopAfterIdentity) {
            [void](Confirm-OperatorContinuation -DetectedModel $detectedModel)
        }
        if (-not $script:StopAfterIdentity) {
            Invoke-SimpleCase -Name "system-status-byte" -Command "system-status-byte" -Options @("--query")
            try {
                $event = Invoke-Cli -Stage "system-standard-event" -Command "system-standard-event" -Options @("--query")
                $bits = [int](Get-Readback -Payload $event -Field "value")
                if (($bits -band 60) -ne 0) { throw "SESR error bits CME/EXE/DDE/QYE set: $bits" }
                Add-Case -Name "system-standard-event" -Status "PASS" -Detail "No SESR error bits; raw value $bits"
            } catch { Add-Case -Name "system-standard-event" -Status "FAIL" -Detail $_.Exception.Message }
            Invoke-SimpleCase -Name "system-clear-status" -Command "system-clear-status"
            Invoke-SimpleCase -Name "system-opc" -Command "system-opc" -Options @("--query")

            $ch = @("--channel", "1")
            Invoke-RoundTrip "channel-display" "channel-display" $ch "display" "--on"
            Invoke-RoundTrip "channel-scale" "channel-scale" $ch "volts_per_division" "--volts-per-division"
            Invoke-RoundTrip "channel-coupling" "channel-coupling" $ch "coupling" "--coupling" @("ac", "dc")
            Invoke-RoundTrip "channel-probe" "channel-probe" $ch "probe_ratio" "--ratio"
            Invoke-RoundTrip "channel-bandwidth-limit" "channel-bandwidth-limit" $ch "bandwidth_limit" "--on"
            Invoke-RoundTrip "channel-invert" "channel-invert" $ch "invert" "--on"
            Invoke-RoundTrip "channel-units" "channel-units" $ch "units" "--units" @("volt", "amp")
            foreach ($name in @("acquisition-points", "record-length")) {
                Invoke-SimpleCase $name $name @("--query")
            }
            Invoke-SimpleCase "channel-summary" "channel-summary"
            if ($script:Target -eq "tektronix-tbs2074") {
                Invoke-SimpleCase "sample-rate" "sample-rate" @("--query")
                Invoke-SimpleCase "sample-rate-maximum" "sample-rate" @("--query", "--maximum")
                Invoke-RoundTrip "channel-label" "channel-label" $ch "text" "--text"
                Invoke-RoundTrip "channel-probe-skew" "channel-probe-skew" $ch "probe_skew_seconds" "--seconds"
            } else {
                Add-UnsupportedOperationCase "sample-rate"
                foreach ($name in @("channel-label", "channel-probe-skew")) {
                    Add-UnsupportedOperationCase $name
                }
            }
            Invoke-RoundTrip "channel-offset" "channel-offset" $ch "volts" "--volts"
            Invoke-RoundTrip "timebase-scale" "timebase-scale" @() "seconds_per_division" "--seconds-per-division"
            Invoke-RoundTrip "timebase-position" "timebase-position" @() "position_seconds" "--seconds"
            Invoke-RoundTrip "acquisition" "acquisition" @() "type" "--type" @($script:CoreProfile.acquisition_modes)
            try {
                $average = Invoke-Cli -Stage "acquisition-average-before" -Command "acquisition" -Options @("--query")
                $acqType = [string](Get-Readback $average "type")
                $count = [int](Get-Readback $average "count")
                if ($acqType -ne "average") {
                    Add-Case "acquisition-average-count" "N/A" "Current acquisition mode is not average"
                } else {
                    $validCounts = @($script:CoreProfile.average_counts)
                    if ($count -notin $validCounts) {
                        Add-Case "acquisition-average-count" "N/A" "Current count is outside the model's supported subset"
                    } else {
                        $countStatus = "PASS"
                        $countDetail = "query, same-value set, and readback"
                        try {
                            $null = Invoke-Cli -Stage "acquisition-average-same-value" -Command "acquisition" `
                                -Options @("--type", "average", "--count", "$count")
                            $readback = Invoke-Cli -Stage "acquisition-average-after" -Command "acquisition" -Options @("--query")
                            if ([string](Get-Readback $readback "type") -ne "average" -or
                                [int](Get-Readback $readback "count") -ne $count) {
                                throw "Average count readback differs."
                            }
                        } catch { $countStatus = "FAIL"; $countDetail = $_.Exception.Message }
                        finally {
                            try {
                                $null = Invoke-Cli -Stage "acquisition-average-restore" -Command "acquisition" `
                                    -Options @("--type", "average", "--count", "$count")
                                $restored = Invoke-Cli -Stage "acquisition-average-restored" -Command "acquisition" -Options @("--query")
                                if ([string](Get-Readback $restored "type") -ne "average" -or
                                    [int](Get-Readback $restored "count") -ne $count) { throw "Restore readback differs." }
                            } catch { $countStatus = "FAIL"; $countDetail += "; restore failed: $($_.Exception.Message)" }
                        }
                        Add-Case "acquisition-average-count" $countStatus $countDetail
                    }
                }
            } catch { Add-Case "acquisition-average-count" "FAIL" $_.Exception.Message }

            $triggerMode = $null
            try {
                $trigger = Invoke-Cli -Stage "trigger-mode-before" -Command "trigger-mode" -Options @("--query")
                $triggerMode = [string](Get-Readback $trigger "mode")
                Invoke-SameValueCase "trigger-mode" "trigger-mode" $trigger @("--mode", $triggerMode) @("mode")
            } catch {
                $triggerMode = $null
                Add-Case "trigger-mode" "FAIL" $_.Exception.Message
            }
            Invoke-RoundTrip "trigger-sweep" "trigger-sweep" @() "mode" "--mode" @("auto", "normal")
            foreach ($name in @("trigger-edge-source", "trigger-edge-slope", "trigger-edge-coupling")) {
                try {
                    $before = Invoke-Cli -Stage "$name-query" -Command $name -Options @("--query")
                    Add-Case "$name-query" "PASS"
                    if ($triggerMode -ne "edge") {
                        Add-Case $name "N/A" "Current trigger type is not edge or could not be verified; no setter executed"
                    } elseif ($name -eq "trigger-edge-source") {
                        $source = $before.result.source
                        if ($source -eq "analog-channel") {
                            $channel = Get-Readback $before "source_channel"
                            Invoke-SameValueCase $name $name $before @("--source-channel", "$channel") @("source", "source_channel")
                        } elseif ($source -in @("line", "external")) {
                            Invoke-SameValueCase $name $name $before @("--source", $source) @("source")
                        } else { Add-Case $name "N/A" "Current source is outside the supported subset" }
                    } elseif ($name -eq "trigger-edge-slope") {
                        Invoke-SameValueCase $name $name $before @("--slope", (Get-Readback $before "slope")) @("slope")
                    } else {
                        Invoke-SameValueCase $name $name $before @("--coupling", (Get-Readback $before "coupling")) @("coupling")
                    }
                } catch { Add-Case $name "FAIL" $_.Exception.Message }
            }
            Invoke-RoundTrip "trigger-holdoff" "trigger-holdoff" @() "seconds" "--seconds"
            if ($script:Target -eq "tektronix-tbs2074") {
                Invoke-SimpleCase "trigger-edge-level-query" "trigger-edge-level" @("--source-channel", "1", "--query")
                if ($triggerMode -eq "edge") {
                    Invoke-RoundTrip "trigger-edge-level" "trigger-edge-level" @("--source-channel", "1") "level_volts" "--level-volts"
                } else { Add-Case "trigger-edge-level" "N/A" "Current trigger type is not edge or could not be verified; no setter executed" }
            } else {
                Add-UnsupportedOperationCase "trigger-edge-level" "trigger-edge-level" "Unsupported standalone on this model"
            }
            try {
                if ($triggerMode -ne "edge") {
                    Add-Case "trigger-edge" "N/A" "Current trigger type is not edge or could not be verified; no setter executed"
                } else {
                    $source = Invoke-Cli -Stage "trigger-edge-source-precondition" -Command "trigger-edge-source" -Options @("--query")
                    if ($source.result.source -ne "analog-channel") {
                        Add-Case "trigger-edge" "N/A" "Combined edge requires a current analog source; source is not changed"
                    } else {
                        $before = Invoke-Cli -Stage "trigger-edge-before" -Command "trigger-edge" -Options @("--query")
                        Invoke-SameValueCase "trigger-edge" "trigger-edge" $before @(
                            "--source-channel", (Format-Setting (Get-Readback $before "source_channel")),
                            "--level", (Format-Setting (Get-Readback $before "level_volts")),
                            "--slope", (Get-Readback $before "slope")
                        ) @("source_channel", "level_volts", "slope")
                    }
                }
            } catch { Add-Case "trigger-edge" "FAIL" $_.Exception.Message }

            $specialTrigger = if ($script:Target -eq "tektronix-tbs2074") { "trigger-runt" } else { "trigger-tv" }
            $specialMode = if ($specialTrigger -eq "trigger-runt") { "runt" } else { "tv" }
            $unsupportedSpecialTrigger = if ($specialTrigger -eq "trigger-runt") { "trigger-tv" } else { "trigger-runt" }
            Add-UnsupportedOperationCase $unsupportedSpecialTrigger
            try {
                $before = Invoke-Cli -Stage "$specialTrigger-query" -Command $specialTrigger -Options @("--query")
                Add-Case "$specialTrigger-query" "PASS"
                if ($triggerMode -ne $specialMode -or $before.result.mode -ne $specialMode) {
                    Add-Case $specialTrigger "N/A" "Current trigger type is not $specialMode; no setter executed"
                } elseif ($specialMode -eq "runt") {
                    $state = $before.result
                    if ($state.channel -notin @(1, 2, 3, 4) -or $state.polarity -notin @("positive", "negative") -or
                        $state.qualifier -notin @("none", "less-than", "greater-than") -or
                        $null -eq $state.low_level_volts -or $null -eq $state.high_level_volts -or
                        $state.low_level_volts -ge $state.high_level_volts -or
                        ($state.qualifier -ne "none" -and ($null -eq $state.time_seconds -or $state.time_seconds -le 0))) {
                        Add-Case $specialTrigger "N/A" "Current runt settings are outside the public setter subset"
                    } else {
                        $fields = @("channel", "polarity", "qualifier", "low_level_volts", "high_level_volts", "mode")
                        if ($null -ne $state.time_seconds) { $fields += "time_seconds" }
                        $options = @("--channel", "$($state.channel)", "--polarity", $state.polarity,
                            "--qualifier", $state.qualifier, "--low-level-volts", (Format-Setting $state.low_level_volts),
                            "--high-level-volts", (Format-Setting $state.high_level_volts))
                        if ($state.qualifier -ne "none") { $options += @("--time-seconds", (Format-Setting $state.time_seconds)) }
                        Invoke-SameValueCase $specialTrigger $specialTrigger $before $options $fields
                    }
                } else {
                    $state = $before.result
                    if ($null -eq $state.source_channel -or $state.standard -notin @("ntsc", "pal") -or
                        $state.tv_mode -notin @("field1", "field2", "all-fields", "all-lines") -or
                        $state.polarity -notin @("positive", "negative")) {
                        Add-Case $specialTrigger "N/A" "Current TV settings are outside the public setter subset"
                    } else {
                        Invoke-SameValueCase $specialTrigger $specialTrigger $before @(
                            "--source-channel", "$($state.source_channel)", "--standard", $state.standard,
                            "--mode", $state.tv_mode, "--polarity", $state.polarity
                        ) @("source_channel", "standard", "tv_mode", "polarity", "mode")
                    }
                }
            } catch { Add-Case $specialTrigger "FAIL" $_.Exception.Message }

            Invoke-RoundTrip "math-display" "math-display" @("--function", "1") "enabled" "--on"
            try {
                $before = Invoke-Cli -Stage "math-operator-before" -Command "math-operator" `
                    -Options @("--function", "1", "--query") -AllowCurrentStateNA
                if ($null -eq $before) {
                    Add-Case "math-operator" "N/A" "Current Math expression is outside the public operator subset; no setter executed"
                } else {
                    Invoke-SameValueCase "math-operator" "math-operator" $before @(
                        "--operation", (Get-Readback $before "math_operation"),
                        "--source1", (Get-Readback $before "source1"), "--source2", (Get-Readback $before "source2")
                    ) @("math_operation", "source1", "source2") @("--function", "1")
                }
            } catch { Add-Case "math-operator" "FAIL" $_.Exception.Message }
            if (@($script:CoreProfile.supported_operations) -contains "display-persistence") {
                try {
                    $before = Invoke-Cli -Stage "display-persistence-before" -Command "display-persistence" -Options @("--query")
                    if ($before.result.mode -in @("minimum", "infinite")) {
                        Invoke-SameValueCase "display-persistence" "display-persistence" $before @("--mode", $before.result.mode) @("mode")
                    } elseif ($null -ne $before.result.seconds) {
                        Invoke-SameValueCase "display-persistence" "display-persistence" $before @("--seconds", (Format-Setting $before.result.seconds)) @("seconds")
                    } else { throw "Missing persistence mode or seconds readback." }
                } catch { Add-Case "display-persistence" "FAIL" $_.Exception.Message }
            } else {
                Add-UnsupportedOperationCase "display-persistence"
            }
            try {
                $reference = Invoke-Cli -Stage "reference-query" -Command "reference-query" -Options @("--slot", "1")
                if ($reference.result.displayed -isnot [bool] -or
                    $null -eq $reference.result.PSObject.Properties["label"] -or
                    $null -eq $reference.result.PSObject.Properties["raw_label"] -or
                    $null -ne $reference.result.label -or $null -ne $reference.result.raw_label) {
                    throw "Reference display or unavailable-label projection is invalid."
                }
                Add-Case "reference-query" "PASS"
            } catch { Add-Case "reference-query" "FAIL" $_.Exception.Message }
            if ($triggerMode -eq "glitch") {
                try {
                    $before = Invoke-Cli -Stage "trigger-pulse-width-before" -Command "trigger-pulse-width" -Options @("--query")
                    $state = $before.result
                    $field = if ($state.qualifier -eq "less-than") { "less_than_seconds" } else { "greater_than_seconds" }
                    if ($state.qualifier -notin @("less-than", "greater-than") -or $null -eq $state.channel -or
                        $state.polarity -notin @("positive", "negative") -or $null -eq $state.$field -or $state.$field -le 0) {
                        Add-Case "trigger-pulse-width" "N/A" "Current pulse settings are outside the public subset; no setter executed"
                    } else {
                        Invoke-SameValueCase "trigger-pulse-width" "trigger-pulse-width" $before @(
                            "--channel", "$($state.channel)", "--polarity", $state.polarity,
                            "--qualifier", $state.qualifier, "--time-seconds", (Format-Setting $state.$field),
                            "--level-volts", (Format-Setting $state.level_volts)
                        ) @("channel", "polarity", "qualifier", $field, "level_volts", "mode")
                    }
                } catch { Add-Case "trigger-pulse-width" "FAIL" $_.Exception.Message }
            } else { Add-Case "trigger-pulse-width" "N/A" "Current trigger type is not glitch; no setter executed" }
            if ($IncludeConfigurationActions) {
                try {
                    $display = Invoke-Cli -Stage "primitive-source-display" -Command "channel-display" -Options @("--channel", "1", "--query")
                    if ((Get-Readback $display "display") -eq $true) {
                        $measurement = Invoke-Cli -Stage "measure" -Command "measure" -Options @("--channel", "1", "--item", "vpp")
                        if ((Get-Readback $measurement "valid") -ne $true) { throw "Immediate measurement is invalid." }
                        Add-Case "measure" "PASS" "Immediate measurement completed; Core TYPE/SOURCE restore is covered by hardware-free regression tests"
                        $csv = Join-Path $script:RunPaths.Private "waveform.csv"
                        $meta = Join-Path $script:RunPaths.Private "waveform.json"
                        $capture = Invoke-Cli -Stage "capture-byte" -Command "capture" -Options @(
                            "--channel", "1", "--format", "byte", "--points", "1000", "--csv", $csv, "--meta", $meta)
                        if ((Get-Readback $capture "format") -cne "BYTE" -or
                            -not (Test-Path -LiteralPath $csv) -or -not (Test-Path -LiteralPath $meta)) {
                            throw "Missing BYTE waveform artifacts."
                        }
                        $actualPoints = [int](Get-Readback $capture "actual_points")
                        $metadata = Get-Content -LiteralPath $meta -Raw | ConvertFrom-Json
                        $rows = @(Import-Csv -LiteralPath $csv)
                        if ($actualPoints -le 0 -or $rows.Count -ne $actualPoints -or
                            $metadata.actual_points -ne $actualPoints) {
                            throw "Waveform point count is empty or inconsistent with artifacts."
                        }
                        $previousTime = $null
                        foreach ($row in $rows) {
                            $columns = @($row.PSObject.Properties)
                            if ($columns.Count -ne 2 -or $columns[0].Name -cne "time_s") {
                                throw "Unexpected waveform CSV columns."
                            }
                            $time = [double]::Parse($columns[0].Value, [Globalization.CultureInfo]::InvariantCulture)
                            $vertical = [double]::Parse($columns[1].Value, [Globalization.CultureInfo]::InvariantCulture)
                            if ([double]::IsNaN($time) -or [double]::IsInfinity($time) -or
                                [double]::IsNaN($vertical) -or [double]::IsInfinity($vertical)) {
                                throw "Waveform time or vertical value is not finite."
                            }
                            if ($null -ne $previousTime -and $time -le $previousTime) {
                                throw "Waveform time axis is not strictly increasing."
                            }
                            $previousTime = $time
                        }
                        Add-Case "capture-byte" "PASS" "Displayed CH1; positive point count, finite values, increasing time axis; transfer settings may change"
                    } else {
                        Add-Case "measure" "N/A" "CH1 is hidden; display state is not changed"
                        Add-Case "capture-byte" "N/A" "CH1 is hidden; display state is not changed"
                    }
                } catch { Add-Case "measure-capture" "FAIL" $_.Exception.Message }
                try {
                    $hiddenChannel = $null
                    for ($channel = 1; $channel -le $expected.channels; $channel++) {
                        $display = Invoke-Cli -Stage "hidden-source-display-$channel" -Command "channel-display" `
                            -Options @("--channel", "$channel", "--query")
                        $displayed = Get-Readback $display "display"
                        if ($displayed -isnot [bool]) { throw "Invalid channel display readback." }
                        if (-not $displayed) { $hiddenChannel = $channel; break }
                    }
                    if ($null -eq $hiddenChannel) {
                        Add-Case "capture-hidden-channel" "N/A" "All analog channels are displayed; display state is not changed"
                    } else {
                        try {
                            $null = Invoke-Cli -Stage "capture-hidden-channel" -Command "capture" `
                                -Options @("--channel", "$hiddenChannel", "--format", "byte", "--points", "1000") `
                                -ExpectHiddenCaptureRejection
                        } finally {
                            $after = Invoke-Cli -Stage "hidden-source-display-after" -Command "channel-display" `
                                -Options @("--channel", "$hiddenChannel", "--query")
                            if ((Get-Readback $after "display") -cne $false) {
                                throw "Hidden channel display did not remain OFF."
                            }
                        }
                        Add-Case "capture-hidden-channel" "PASS" "Capture rejected; channel display remains OFF"
                    }
                } catch { Add-Case "capture-hidden-channel" "FAIL" $_.Exception.Message }
            } else {
                foreach ($name in @("measure", "capture-byte", "capture-hidden-channel")) {
                    Add-Case $name "N/A" "Requires -IncludeConfigurationActions; capture transfer settings are not restored"
                }
            }
            Invoke-SimpleCase "cursor-query" "cursor" @("--query")
            if ($IncludeConfigurationActions) {
                Write-Warning "Cursor and measurement configuration actions are not restored; cursors end off and measurements end cleared. TBS2074 cursor setting selects CH1 and may display it or restart acquisition through Core."
                if ([string]$script:CoreProfile.cursor_source_selection -ceq "selected-waveform") {
                    $cursorXPassed = $false
                    try {
                        $position = Invoke-Cli -Stage "cursor-timebase-position" -Command "timebase-position" -Options @("--query")
                        $x = Get-Readback $position "position_seconds"
                        $null = Invoke-Cli -Stage "cursor-set" -Command "cursor" -Options @(
                            "--function", "vbars", "--source-channel", "1",
                            "--x1", (Format-Setting $x), "--x2", (Format-Setting $x))
                        $after = Invoke-Cli -Stage "cursor-set-after" -Command "cursor" -Options @("--query")
                        foreach ($field in @("x1_seconds", "x2_seconds")) {
                            if (-not (Test-ReadbackEqual $x (Get-Readback $after $field))) { throw "Cursor X position readback differs." }
                        }
                        if ([string](Get-Readback $after "mode") -ine "VBArs") { throw "Cursor function readback is not VBArs." }
                        $display = Invoke-Cli -Stage "cursor-set-source-display" -Command "channel-display" -Options @("--channel", "1", "--query")
                        if ((Get-Readback $display "display") -ne $true) { throw "Cursor source channel is not displayed." }
                        Add-Case "cursor-set" "PASS" "CH1 X cursors at current timebase position using the VBArs function; Core verifies selected-waveform source"
                        $cursorXPassed = $true
                    } catch { Add-Case "cursor-set" "FAIL" $_.Exception.Message }

                    foreach ($function in @("screen", "waveform", "vbars", "hbars")) {
                        $caseName = "cursor-function-$function"
                        try {
                            $null = Invoke-Cli -Stage $caseName -Command "cursor" -Options @("--function", $function)
                            $after = Invoke-Cli -Stage "$caseName-after" -Command "cursor" -Options @("--query")
                            $expectedMode = switch ($function) {
                                "screen" { "SCREEN" }
                                "waveform" { "WAVEform" }
                                "vbars" { "VBArs" }
                                "hbars" { "HBArs" }
                            }
                            if ([string](Get-Readback $after "mode") -ine $expectedMode) {
                                throw "Cursor function readback is $((Get-Readback $after 'mode')) instead of $expectedMode."
                            }
                            Add-Case $caseName "PASS" "Function-only cursor switch to $function and query readback"
                        } catch { Add-Case $caseName "FAIL" $_.Exception.Message }
                    }
                    try {
                        $null = Invoke-Cli -Stage "cursor-function-off" -Command "cursor" -Options @("--function", "off")
                        $after = Invoke-Cli -Stage "cursor-function-off-after" -Command "cursor" -Options @("--query")
                        if ([string](Get-Readback $after "mode") -ine "off") { throw "Cursors are not off." }
                        Add-Case "cursor-function-off" "PASS" "Function-only cursor switch to OFF without a source channel"
                    } catch { Add-Case "cursor-function-off" "FAIL" $_.Exception.Message }

                    $voltageChannel = $null
                    if (-not $cursorXPassed) {
                        Add-Case "cursor-set-y" "N/A" "Skipped after cursor-set failure"
                        Add-Case "cursor-set-screen" "N/A" "Skipped after cursor-set failure"
                    } else {
                    try {
                        foreach ($candidate in @(1, 2, 3, 4)) {
                            $units = Invoke-Cli -Stage "cursor-voltage-units-$candidate" -Command "channel-units" -Options @("--channel", "$candidate", "--query")
                            if ([string](Get-Readback $units "units") -ceq "volt") {
                                $voltageChannel = $candidate
                                break
                            }
                        }
                    } catch {
                        Add-Case "cursor-set-y" "FAIL" $_.Exception.Message
                        Add-Case "cursor-set-screen" "N/A" "Skipped because the voltage-source precondition could not be checked"
                    }
                    if ($null -eq $voltageChannel -and -not $script:CaseResults.Contains("cursor-set-y")) {
                        Add-Case "cursor-set-y" "N/A" "CH1-CH4 are not currently in physical volt units"
                        Add-Case "cursor-set-screen" "N/A" "CH1-CH4 are not currently in physical volt units"
                    } elseif ($null -ne $voltageChannel) {
                        $y = $null
                        $cursorYPassed = $false
                        try {
                            $offset = Invoke-Cli -Stage "cursor-y-offset" -Command "channel-offset" -Options @("--channel", "$voltageChannel", "--query")
                            $y = Get-Readback $offset "volts"
                            $null = Invoke-Cli -Stage "cursor-set-y" -Command "cursor" -Options @(
                                "--function", "hbars", "--source-channel", "$voltageChannel",
                                "--y1", (Format-Setting $y), "--y2", (Format-Setting $y))
                            $after = Invoke-Cli -Stage "cursor-set-y-after" -Command "cursor" -Options @("--query")
                            foreach ($field in @("y1_volts", "y2_volts")) {
                                if (-not (Test-ReadbackEqual $y (Get-Readback $after $field))) { throw "Cursor Y position readback differs." }
                            }
                            if ([string](Get-Readback $after "mode") -ine "HBArs") { throw "Cursor function readback is not HBArs." }
                            $display = Invoke-Cli -Stage "cursor-set-y-source-display" -Command "channel-display" -Options @("--channel", "$voltageChannel", "--query")
                            if ((Get-Readback $display "display") -ne $true) { throw "Cursor source channel is not displayed." }
                            Add-Case "cursor-set-y" "PASS" "Physical-volts Y cursor round-trip on CH$voltageChannel"
                            $cursorYPassed = $true
                        } catch { Add-Case "cursor-set-y" "FAIL" $_.Exception.Message }

                        if ($cursorYPassed) {
                            try {
                                $position = Invoke-Cli -Stage "cursor-screen-position" -Command "timebase-position" -Options @("--query")
                                $x = Get-Readback $position "position_seconds"
                                $null = Invoke-Cli -Stage "cursor-set-screen" -Command "cursor" -Options @(
                                    "--function", "screen", "--source-channel", "$voltageChannel",
                                    "--x1", (Format-Setting $x), "--x2", (Format-Setting $x),
                                    "--y1", (Format-Setting $y), "--y2", (Format-Setting $y))
                                $after = Invoke-Cli -Stage "cursor-set-screen-after" -Command "cursor" -Options @("--query")
                                foreach ($field in @("x1_seconds", "x2_seconds")) {
                                    if (-not (Test-ReadbackEqual $x (Get-Readback $after $field))) { throw "Cursor SCREEN X readback differs." }
                                }
                                foreach ($field in @("y1_volts", "y2_volts")) {
                                    if (-not (Test-ReadbackEqual $y (Get-Readback $after $field))) { throw "Cursor SCREEN Y readback differs." }
                                }
                                if ([string](Get-Readback $after "mode") -ine "SCREEN") { throw "Cursor function readback is not SCREEN." }
                                $display = Invoke-Cli -Stage "cursor-set-screen-source-display" -Command "channel-display" -Options @("--channel", "$voltageChannel", "--query")
                                if ((Get-Readback $display "display") -ne $true) { throw "Cursor source channel is not displayed." }
                                Add-Case "cursor-set-screen" "PASS" "Combined X/Y cursor round-trip on CH$voltageChannel"
                            } catch { Add-Case "cursor-set-screen" "FAIL" $_.Exception.Message }
                        } else {
                            Add-Case "cursor-set-screen" "N/A" "Skipped after cursor-set-y failure"
                        }
                    }
                    }
                } else {
                    try {
                        $position = Invoke-Cli -Stage "cursor-timebase-position" -Command "timebase-position" -Options @("--query")
                        $x = Get-Readback $position "position_seconds"
                        $configured = Invoke-Cli -Stage "cursor-set" -Command "cursor" -Options @(
                            "--source-channel", "1", "--x1", (Format-Setting $x), "--x2", (Format-Setting $x)) -AllowCurrentStateNA
                        if ($null -eq $configured) {
                            Add-Case "cursor-set" "N/A" "X cursors require existing seconds units; units were not changed"
                        } else {
                            $after = Invoke-Cli -Stage "cursor-set-after" -Command "cursor" -Options @("--query")
                            foreach ($field in @("x1_seconds", "x2_seconds")) {
                                if (-not (Test-ReadbackEqual $x (Get-Readback $after $field))) { throw "Cursor position readback differs." }
                            }
                            Add-Case "cursor-set" "PASS" "CH1 X cursors at current timebase position; no auto-range changes"
                        }
                    } catch { Add-Case "cursor-set" "FAIL" $_.Exception.Message }
                }
                try {
                    $null = Invoke-Cli -Stage "cursor-off" -Command "cursor" -Options @("--off")
                    $after = Invoke-Cli -Stage "cursor-off-after" -Command "cursor" -Options @("--query")
                    if ([string](Get-Readback $after "mode") -ine "off") { throw "Cursors are not off." }
                    Add-Case "cursor-off" "PASS"
                } catch { Add-Case "cursor-off" "FAIL" $_.Exception.Message }
                Invoke-SimpleCase "measure-install" "measure-install" @("--source-channel", "1", "--item", "vpp")
                Invoke-SimpleCase "measure-clear" "measure-clear"
            } else {
                Add-Case "cursor-set" "N/A" "Requires -IncludeConfigurationActions; cursor source/mode changes are not restored"
                if ([string]$script:CoreProfile.cursor_source_selection -ceq "selected-waveform") {
                    Add-Case "cursor-set-y" "N/A" "Requires -IncludeConfigurationActions; cursor source/mode changes are not restored"
                    Add-Case "cursor-set-screen" "N/A" "Requires -IncludeConfigurationActions; cursor source/mode changes are not restored"
                    foreach ($function in @("screen", "waveform", "vbars", "hbars", "off")) {
                        Add-Case "cursor-function-$function" "N/A" "Requires -IncludeConfigurationActions; cursor function changes are not restored"
                    }
                }
                foreach ($name in @("cursor-off", "measure-install", "measure-clear")) {
                    Add-Case $name "N/A" "Requires -IncludeConfigurationActions; no public configuration restore path"
                }
            }

            if ($script:Target -eq "tektronix-tbs2074") {
                Invoke-RoundTrip "save-image-format" "save-image-format" @() "format" "--format" @("png", "bmp")
                Invoke-RoundTrip "save-waveform-format" "save-waveform-format" @() "format" "--format" @("csv")
                Add-UnsupportedOperationCase "save-image-ink-saver"
            } else {
                Add-UnsupportedOperationCase "save-image-format"
                Add-UnsupportedOperationCase "save-waveform-format"
                try {
                    $before = Invoke-Cli -Stage "save-image-ink-saver-before" -Command "save-image-ink-saver" -Options @("--query")
                    Invoke-SameValueCase "save-image-ink-saver" "save-image-ink-saver" $before @(
                        "--enabled", (Format-Setting (Get-Readback $before "enabled"))) @("enabled")
                } catch { Add-Case "save-image-ink-saver" "FAIL" $_.Exception.Message }
            }

            if ($script:Target -eq "tektronix-tbs2074") {
                Add-UnsupportedOperationCase "display-vectors"
            } else {
                try {
                    $vectors = Invoke-Cli -Stage "display-vectors-query" -Command "display-vectors" -Options @("--query")
                    $isOn = Get-Readback $vectors "value"
                    Add-Case "display-vectors-query" "PASS"
                    if ($isOn -is [bool] -and $isOn) {
                        try {
                            Invoke-SameValueCase "display-vectors-on" "display-vectors" $vectors @("--on") @("value")
                        } catch { Add-Case "display-vectors-on" "FAIL" $_.Exception.Message }
                    } else {
                        Add-Case "display-vectors-on" "N/A" "Current style is dots; no public OFF setter for restore"
                    }
                } catch { Add-Case "display-vectors-query" "FAIL" $_.Exception.Message }
            }
            Invoke-RoundTrip "save-pwd" "save-pwd" @() "path" "--path"

            if ($script:Target -eq "tektronix-tbs2074") {
                if (-not $IncludeScreenshot) {
                    Add-Case "screenshot-png" "N/A" "Requires -IncludeScreenshot; writes a temporary instrument file"
                } else {
                    try {
                        $path = Join-Path $script:RunPaths.Private "screenshot.png"
                        $capture = Invoke-Cli -Stage "screenshot-png" -Command "screenshot" -Options @("--output", $path)
                        if ((Get-Readback $capture "format") -cne "PNG" -or
                            [int](Get-Readback $capture "byte_count") -le 0 -or
                            [string](Get-Readback $capture "image_path") -cne $path) { throw "Invalid PNG artifact metadata." }
                        $bytes = [IO.File]::ReadAllBytes($path)
                        if ($bytes.Length -lt 8 -or
                            [BitConverter]::ToString($bytes, 0, 8) -cne "89-50-4E-47-0D-0A-1A-0A") { throw "Missing PNG signature." }
                        Add-Case "screenshot-png" "PASS" "Native PNG host artifact; temporary file and settings cleaned by Core"
                    } catch { Add-Case "screenshot-png" "FAIL" $_.Exception.Message }
                }
            }
            if ($script:Target -ne "tektronix-tds2024b") {
                Add-Case "screenshot-bmp" "N/A" "BMP screenshot format is unsupported on this model"
            } elseif (-not $IncludeScreenshot) {
                Add-Case "screenshot-bmp" "N/A" "Requires -IncludeScreenshot"
            } elseif ($script:Connection -ne "usb" -or $Resource -notmatch '(?i)::INSTR$') {
                Add-Case "screenshot-bmp" "N/A" "Public BMP capture requires USBTMC"
            } else {
                try {
                    $path = Join-Path $script:RunPaths.Private "screenshot.bmp"
                    $capture = Invoke-Cli -Stage "screenshot-bmp" -Command "screenshot" -Options @("--format", "bmp", "--output", $path)
                    if ((Get-Readback $capture "format") -cne "BMP" -or
                        [int](Get-Readback $capture "byte_count") -le 0 -or
                        [string](Get-Readback $capture "image_path") -cne $path) { throw "Invalid BMP artifact metadata." }
                    $bytes = [IO.File]::ReadAllBytes($path)
                    if ($bytes.Length -lt 2 -or $bytes[0] -ne 66 -or $bytes[1] -ne 77) { throw "Missing BMP signature." }
                    Add-Case "screenshot-bmp" "PASS" "Explicit BMP host artifact; temporary settings restored by Core"
                } catch { Add-Case "screenshot-bmp" "FAIL" $_.Exception.Message }
            }

            if ($IncludeAcquisitionActions) {
                Write-Warning "Acquisition actions change run/stop state; cleanup sends stop without independent state readback."
                $script:AcquisitionFinalState = "stop requested"
                try {
                    foreach ($force in @($false, $true)) {
                        $name = if ($force) { "single-wait-force" } else { "single-wait-natural" }
                        try {
                            $options = @("--trigger-timeout-ms", "1000", "--trigger-poll-interval-ms", "50")
                            if ($force) { $options += "--force-trigger-on-timeout" }
                            $wait = Invoke-Cli -Stage $name -Command "single-wait" -Options $options
                            if ($wait.result.poll_source -cne "busy" -or $wait.result.poll_command -cne "BUSY?" -or
                                $wait.result.outcome -notin @("natural", "forced") -or
                                (-not $force -and $wait.result.outcome -ne "natural")) {
                                throw "Invalid bounded BUSY completion result."
                            }
                            Add-Case $name "PASS" "Outcome: $($wait.result.outcome); force only on timeout"
                        } catch { Add-Case $name "FAIL" $_.Exception.Message }
                    }
                    Invoke-SimpleCase "run" "run"
                    Invoke-SimpleCase "single" "single"
                    if ($script:CaseResults["single"].Status -eq "PASS") {
                        Invoke-SimpleCase "force-trigger" "force-trigger"
                    } else { Add-Case "force-trigger" "N/A" "Single acquisition did not arm successfully" }
                } finally {
                    Invoke-SimpleCase "stop-acquisition" "stop-acquisition"
                    if ($script:CaseResults["stop-acquisition"].Status -eq "PASS") {
                        $script:AcquisitionFinalState = "Stop command succeeded; native status clean; Running/Stopped not read back"
                    } else { $script:AcquisitionFinalState = "stop failed or unconfirmed" }
                }
            } else {
                foreach ($name in @("run", "single", "force-trigger", "stop-acquisition", "single-wait-natural", "single-wait-force")) {
                    Add-Case $name "N/A" "Requires -IncludeAcquisitionActions"
                }
            }
            if ($IncludeAutoscale) {
                Write-Warning "Autoscale changes multiple front-panel settings and is not restored."
                Invoke-SimpleCase "autoscale" "autoscale"
            } else { Add-Case "autoscale" "N/A" "Requires -IncludeAutoscale" }
            if ($IncludeStorageWrites) {
                Write-Warning "Setup slot $SetupSlot and reference slot $ReferenceSlot may be overwritten."
                if ([string]::IsNullOrWhiteSpace($ImageFilename)) {
                    Add-Case "save-image" "N/A" "Requires explicit -ImageFilename on available instrument storage"
                } else {
                    Write-Warning "The requested instrument image filename may be overwritten."
                    try {
                        $saved = Invoke-Cli -Stage "save-image" -Command "save-image" -Options @("--filename", $ImageFilename)
                        if ((Get-Readback $saved "operation_complete") -ne $true) { throw "Image save completion was not confirmed." }
                        Add-Case "save-image" "PASS" "Caller-selected instrument file; operation complete"
                    } catch { Add-Case "save-image" "FAIL" $_.Exception.Message }
                }
                if ([string]::IsNullOrWhiteSpace($WaveformFilename)) {
                    Add-Case "save-waveform" "N/A" "Requires explicit -WaveformFilename and -WaveformSourceChannel"
                } else {
                    Write-Warning "The requested instrument waveform filename may be overwritten."
                    try {
                        $saved = Invoke-Cli -Stage "save-waveform" -Command "save-waveform" `
                            -Options @("--filename", $WaveformFilename, "--source-channel", "$WaveformSourceChannel")
                        if ((Get-Readback $saved "operation_complete") -ne $true) { throw "Waveform save completion was not confirmed." }
                        Add-Case "save-waveform" "PASS" "Caller-selected channel and instrument file; operation complete"
                    } catch { Add-Case "save-waveform" "FAIL" $_.Exception.Message }
                }
                Invoke-SimpleCase "setup-save" "setup-save" @("--slot", "$SetupSlot")
                if ($script:CaseResults["setup-save"].Status -eq "PASS") {
                    Invoke-SimpleCase "setup-recall" "setup-recall" @("--slot", "$SetupSlot")
                } else { Add-Case "setup-recall" "N/A" "Setup save did not succeed" }
                try {
                    $display = Invoke-Cli -Stage "reference-source-display" -Command "channel-display" `
                        -Options @("--channel", "1", "--query")
                    if ((Get-Readback $display "display") -eq $true) {
                        Invoke-SimpleCase "reference-save" "reference-save" @("--slot", "$ReferenceSlot", "--source-channel", "1")
                        if ($script:CaseResults["reference-save"].Status -eq "PASS") {
                            Invoke-RoundTrip "reference-display" "reference-display" @("--slot", "$ReferenceSlot") "displayed" "--state"
                        } else { Add-Case "reference-display" "N/A" "Reference save did not succeed" }
                    } else {
                        Add-Case "reference-save" "N/A" "CH1 is not displayed; source is not changed"
                        Add-Case "reference-display" "N/A" "Reference save precondition not met"
                    }
                } catch {
                    Add-Case "reference-save" "FAIL" $_.Exception.Message
                    Add-Case "reference-display" "N/A" "Reference source precondition could not be checked"
                }
            } else {
                foreach ($name in @("setup-save", "setup-recall", "reference-save", "reference-display", "save-image", "save-waveform")) {
                    Add-Case $name "N/A" "Requires -IncludeStorageWrites and explicit slots"
                }
            }

            try {
                $event = Invoke-Cli -Stage "final-standard-event" -Command "system-standard-event" -Options @("--query")
                $bits = [int](Get-Readback -Payload $event -Field "value")
                if (($bits -band 60) -ne 0) { throw "Final SESR error bits CME/EXE/DDE/QYE set: $bits" }
                Add-Case -Name "final-standard-event" -Status "PASS" -Detail "No final SESR error bits; raw value $bits"
            } catch { Add-Case -Name "final-standard-event" -Status "FAIL" -Detail $_.Exception.Message }
        }
    } catch {
        Add-Case "runner" "FAIL" $_.Exception.Message
    } finally {
        Add-Diagnostic -Name "acquisition-final-state" -Message $script:AcquisitionFinalState
        if ($IncludeStorageWrites) {
            Add-Diagnostic -Name "storage" -Message "Requested setup/reference slots and instrument files may have been overwritten."
        }
        if ($IncludeConfigurationActions) {
            Add-Diagnostic -Name "configuration" -Message "Cursor and measurement configuration actions are not restored. TBS2074 cursor source selection may change channel display or restart acquisition."
        }
        $result = if ($script:Failure) { "FAIL" } else { "PASS" }
        Complete-LiveValidationRun -Kind 'scopes-tool-live-cli-check' -Domain 'cli' -Result $result
    }
    $script:FunctionalFailed = $script:Failure

}
