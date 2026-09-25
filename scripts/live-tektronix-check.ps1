[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string] $Target,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string] $Connection,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string] $Resource,
    [Alias("VisaLibrary")][string] $Backend,
    [string] $Python = ".\.venv\Scripts\python.exe",
    [string] $OutputRoot = ".tmp_tests\live_tektronix_check",
    [switch] $IncludeAcquisitionActions,
    [switch] $IncludeAutoscale,
    [switch] $IncludeStorageWrites,
    [ValidateRange(1, 9)][int] $SetupSlot,
    [ValidateRange(1, 2)][int] $ReferenceSlot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot "_validation_helpers.ps1")

$targets = [ordered]@{
    "tektronix-tbs2074b" = @{ model = "TBS2074B"; channels = 4 }
    "tektronix-tds2024b" = @{ model = "TDS2024B"; channels = 4 }
    "tektronix-tbs1052b" = @{ model = "TBS1052B"; channels = 2 }
}
$script:Target = $Target.Trim().ToLowerInvariant()
$script:Connection = $Connection.Trim().ToLowerInvariant()
if (-not $targets.Contains($script:Target)) {
    Write-LiveUsageError -Domain "tektronix" "Unsupported target. Choose one of: $($targets.Keys -join ', ')."
}
if ($script:Connection -notin @("usb", "tcpip")) {
    Write-LiveUsageError -Domain "tektronix" "Connection must be usb or tcpip."
}
if (-not (($script:Connection -eq "usb" -and $Resource -match "^(?i)USB\d*::") -or
          ($script:Connection -eq "tcpip" -and $Resource -match "^(?i)TCPIP\d*::"))) {
    Write-LiveUsageError -Domain "tektronix" "The explicit VISA resource type must match -Connection."
}
if ($IncludeStorageWrites -and (-not $PSBoundParameters.ContainsKey("SetupSlot") -or
                                -not $PSBoundParameters.ContainsKey("ReferenceSlot"))) {
    Write-LiveUsageError -Domain "tektronix" "Storage writes require explicit -SetupSlot (1..9) and -ReferenceSlot (1..2)."
}
if (-not $IncludeStorageWrites -and ($PSBoundParameters.ContainsKey("SetupSlot") -or
                                    $PSBoundParameters.ContainsKey("ReferenceSlot"))) {
    Write-LiveUsageError -Domain "tektronix" "Storage slots require -IncludeStorageWrites."
}
try {
    $script:LiveArguments = @(Get-LiveConnectionArguments -Resource $Resource -Backend $Backend)
    $outputBase = Get-FullPath -Path $OutputRoot -BaseRoot $RepoRoot
    Assert-PathUnderRoot -RootPath (Join-Path $RepoRoot ".tmp_tests") -Path $outputBase `
        -Message "OutputRoot must be under .tmp_tests: {0}"
    $pythonPath = Get-FullPath -Path $Python -BaseRoot $RepoRoot
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "Python executable not found: $pythonPath"
    }
} catch {
    Write-LiveUsageError -Domain "tektronix" $_.Exception.Message
}
$script:BackendName = if ($script:LiveArguments -contains "--visa-library") { "pyvisa_py" } else { "system_visa" }
$script:RunPaths = New-ValidationRunDirectory -BaseRoot $outputBase
$script:Cases = New-Object System.Collections.Generic.List[object]
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:HardwareTouched = $false
$script:CliIndex = 0
$script:Failure = $false
$script:StopAfterIdentity = $false
$script:AcquisitionFinalState = "unchanged by runner"

function Add-Case {
    param([string]$Name, [ValidateSet("PASS", "FAIL", "N/A")][string]$Status, [string]$Detail = "")
    $script:Cases.Add([ordered]@{ name = $Name; status = $Status; detail = $Detail })
    Write-CaseStatus -Status $Status -Name $Name -Context "[live][tektronix]"
    if ($Status -eq "FAIL") { $script:Failure = $true }
}

function Invoke-Cli {
    param([string]$Stage, [string]$Command, [string[]]$Options = @())
    $script:CliIndex += 1
    $stem = "cli-{0:D3}-{1}" -f $script:CliIndex, (New-SafeCaseName -Name $Stage)
    $stdoutPath = Join-Path $script:RunPaths.Private "$stem.stdout.txt"
    $stderrPath = Join-Path $script:RunPaths.Private "$stem.stderr.txt"
    $jsonPath = Join-Path $script:RunPaths.Private "$stem.json"
    $args = @("-m", "scopes_tool_cli.cli", $Command, "--json") + @($Options) + @($script:LiveArguments)
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $pythonPath
    $psi.Arguments = Join-ProcessArguments -Arguments $args
    $psi.WorkingDirectory = $RepoRoot
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $start = Get-Date
    $process = [System.Diagnostics.Process]::Start($psi)
    $script:HardwareTouched = $true
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
    $invocation = [ordered]@{
        command = "$pythonPath -m scopes_tool_cli.cli"
        arguments = @($args)
        exit_code = $record.exit_code
        duration_ms = $record.duration_ms
        result = if ($record.success) { "PASS" } else { "FAIL" }
        stdout = Get-ArtifactRelativePath -Path $stdoutPath -BaseRoot $RepoRoot
        stderr = Get-ArtifactRelativePath -Path ([string]$record.stderr) -BaseRoot $RepoRoot
        json = Get-ArtifactRelativePath -Path ([string]$record.json) -BaseRoot $RepoRoot
    }
    $script:Invocations.Add($invocation)
    if (-not $record.success -or -not $record.json) {
        $invocation.result = "FAIL"
        throw "$Stage failed (exit $($record.exit_code), timeout=$timedOut); see $stdoutPath and $stderrPath"
    }
    $payload = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ($payload.ok -ne $true) {
        $invocation.result = "FAIL"
        throw "$Stage returned ok=false; see $jsonPath"
    }
    return $payload
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
                  ([double]$original -lt $(if ($script:Target -eq "tektronix-tbs2074b") { 4e-8 } else { 5e-7 }) -or
                   [double]$original -gt $(if ($script:Target -eq "tektronix-tbs2074b") { 8 } else { 10 }))) {
            $status = "N/A"
            $detail = "current holdoff is outside the model's supported setter range"
        } elseif ($Name -eq "channel-probe" -and $script:Target -ne "tektronix-tbs2074b" -and
                  [double]$original -notin @(1, 10, 20, 50, 100, 500, 1000)) {
            $status = "N/A"
            $detail = "current probe ratio is outside the legacy supported subset"
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

function Write-Report {
    $pass = @($script:Cases | Where-Object { $_.status -eq "PASS" }).Count
    $fail = @($script:Cases | Where-Object { $_.status -eq "FAIL" }).Count
    $na = @($script:Cases | Where-Object { $_.status -eq "N/A" }).Count
    $runStatus = if ($fail -gt 0) { "FAIL" } elseif ($script:Failure) { "BLOCKED" } else { "PASS" }
    $report = [ordered]@{
        status = $runStatus.ToLowerInvariant()
        target = $script:Target
        connection = $script:Connection
        backend = $script:BackendName
        git_head = Get-GitHead -ProjectRoot $RepoRoot
        package_version = Get-PackageVersion -ProjectRoot $RepoRoot
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        hardware_touched = $script:HardwareTouched
        resource = $Resource
        acquisition_final_state = $script:AcquisitionFinalState
        cases = @($script:Cases.ToArray())
        summary_counts = [ordered]@{ passed = $pass; failed = $fail; na = $na }
        invocations = @($script:Invocations.ToArray())
    }
    Write-JsonReport -LiteralPath (Join-Path $script:RunPaths.Private "report.json") -Report $report
    $lines = @(
        "# Tektronix Live Acceptance", "",
        "Result: $runStatus",
        "Target: $($script:Target)", "Connection: $($script:Connection)",
        "Backend: $($script:BackendName)", "Hardware touched: $($script:HardwareTouched)",
        "Acquisition final state: $($script:AcquisitionFinalState)", "",
        "| Case | Status | Detail |", "|---|---|---|"
    )
    foreach ($case in $script:Cases) {
        $safe = ([string]$case.detail).Replace("|", "\|").Replace("`r", " ").Replace("`n", " ")
        $lines += "| $($case.name) | $($case.status) | $safe |"
    }
    if ($IncludeStorageWrites) {
        $lines += ""
        $lines += "Requested setup slot $SetupSlot and reference slot $ReferenceSlot may have been overwritten."
    }
    Write-Utf8NoBomLines -LiteralPath (Join-Path $script:RunPaths.Private "summary.md") -Lines $lines
    Write-Host "[live][tektronix] private artifacts: $($script:RunPaths.Private)"
}

try {
    # The first live invocation is identify. No state-changing case may precede this gate.
    try {
        $identity = Invoke-Cli -Stage "identify" -Command "identify"
        $expected = $targets[$script:Target]
        if ([string]$identity.idn.vendor -ine "Tektronix" -or
            [string]$identity.idn.model -cne [string]$expected.model -or
            [int]$identity.capabilities.analog_channels -ne [int]$expected.channels -or
            [string]$identity.capabilities.series -cne $(if ($script:Target -eq "tektronix-tbs2074b") { "TBS2000B" } elseif ($script:Target -eq "tektronix-tds2024b") { "TDS2000B" } else { "TBS1000B" })) {
            throw "Detected vendor, physical model, channel count, or profile differs from -Target."
        }
        Add-Case -Name "identify" -Status "PASS" -Detail "Tektronix $($expected.model), $($expected.channels) channels"
    } catch {
        Add-Case -Name "identify" -Status "FAIL" -Detail $_.Exception.Message
        $script:StopAfterIdentity = $true
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
        if ($script:Target -eq "tektronix-tbs2074b") {
            Invoke-RoundTrip "channel-offset" "channel-offset" $ch "volts" "--volts"
            Invoke-RoundTrip "channel-label" "channel-label" $ch "text" "--text"
            Invoke-RoundTrip "channel-probe-skew" "channel-probe-skew" $ch "probe_skew_seconds" "--seconds"
        } else {
            foreach ($name in @("channel-offset", "channel-label", "channel-probe-skew")) {
                Add-Case $name "N/A" "Unsupported on this model"
            }
        }
        Invoke-RoundTrip "timebase-scale" "timebase-scale" @() "seconds_per_division" "--seconds-per-division"
        if ($script:Target -eq "tektronix-tbs2074b") {
            Add-Case "timebase-position" "N/A" "Unsupported on this model"
        } else {
            Invoke-RoundTrip "timebase-position" "timebase-position" @() "position_seconds" "--seconds"
        }
        Invoke-RoundTrip "acquisition" "acquisition" @() "type" "--type" `
            $(if ($script:Target -eq "tektronix-tbs2074b") { @("normal", "average", "peak", "high_resolution") } else { @("normal", "average", "peak") })
        try {
            $average = Invoke-Cli -Stage "acquisition-average-before" -Command "acquisition" -Options @("--query")
            $acqType = [string](Get-Readback $average "type")
            $count = [int](Get-Readback $average "count")
            if ($acqType -ne "average") {
                Add-Case "acquisition-average-count" "N/A" "Current acquisition mode is not average"
            } else {
                $validCounts = if ($script:Target -eq "tektronix-tbs2074b") {
                    @(2, 4, 8, 16, 32, 64, 128, 256, 512)
                } else { @(4, 16, 64, 128) }
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

        Add-Case "trigger-mode" "N/A" "No standalone one-shot CLI surface; direct CLI acceptance is not applicable"
        Invoke-RoundTrip "trigger-sweep" "trigger-sweep" @() "mode" "--mode" @("auto", "normal")
        foreach ($name in @("trigger-edge-source", "trigger-edge-slope", "trigger-edge-coupling")) {
            try {
                $null = Invoke-Cli -Stage "$name-query" -Command $name -Options @("--query")
                Add-Case $name "N/A" "query passed; setter requires a public current trigger-type readback"
            } catch { Add-Case $name "FAIL" $_.Exception.Message }
        }
        Invoke-RoundTrip "trigger-holdoff" "trigger-holdoff" @() "seconds" "--seconds"
        if ($script:Target -eq "tektronix-tbs2074b") {
            Invoke-RoundTrip "trigger-edge-level" "trigger-edge-level" @("--source-channel", "1") "level_volts" "--level-volts"
        } else {
            Add-Case "trigger-edge-level" "N/A" "Unsupported standalone on this model"
        }
        try {
            $null = Invoke-Cli -Stage "trigger-edge-query" -Command "trigger-edge" -Options @("--query")
            Add-Case "trigger-edge" "N/A" "query passed; setter requires a public current trigger-type readback"
        } catch { Add-Case "trigger-edge" "FAIL" $_.Exception.Message }

        if ($script:Target -eq "tektronix-tbs2074b") {
            Add-Case "display-vectors" "N/A" "Unsupported on this model"
        } else {
            try {
                $vectors = Invoke-Cli -Stage "display-vectors-query" -Command "display-vectors" -Options @("--query")
                $isOn = Get-Readback $vectors "value"
                Add-Case "display-vectors-query" "PASS"
                if ($isOn -is [bool] -and $isOn) {
                    Invoke-SimpleCase "display-vectors-on" "display-vectors" @("--on")
                } else {
                    Add-Case "display-vectors-on" "N/A" "Current style is dots; no public OFF setter for restore"
                }
            } catch { Add-Case "display-vectors-query" "FAIL" $_.Exception.Message }
        }
        Invoke-RoundTrip "save-pwd" "save-pwd" @() "path" "--path"

        if ($IncludeAcquisitionActions) {
            Write-Warning "Acquisition actions change run/stop state; final state is stop."
            $script:AcquisitionFinalState = "stop requested"
            try {
                Invoke-SimpleCase "run" "run"
                Invoke-SimpleCase "single" "single"
                if (@($script:Cases | Where-Object { $_.name -eq "single" -and $_.status -eq "PASS" }).Count -eq 1) {
                    Invoke-SimpleCase "force-trigger" "force-trigger"
                } else { Add-Case "force-trigger" "N/A" "Single acquisition did not arm successfully" }
            } finally {
                Invoke-SimpleCase "stop-acquisition" "stop-acquisition"
                if (@($script:Cases | Where-Object { $_.name -eq "stop-acquisition" -and $_.status -eq "PASS" }).Count -eq 1) {
                    $script:AcquisitionFinalState = "stopped"
                } else { $script:AcquisitionFinalState = "stop failed or unconfirmed" }
            }
        } else {
            foreach ($name in @("run", "single", "force-trigger", "stop-acquisition")) {
                Add-Case $name "N/A" "Requires -IncludeAcquisitionActions"
            }
        }
        if ($IncludeAutoscale) {
            Write-Warning "Autoscale changes multiple front-panel settings and is not restored."
            Invoke-SimpleCase "autoscale" "autoscale"
        } else { Add-Case "autoscale" "N/A" "Requires -IncludeAutoscale" }
        if ($IncludeStorageWrites) {
            Write-Warning "Setup slot $SetupSlot and reference slot $ReferenceSlot may be overwritten."
            Invoke-SimpleCase "setup-save" "setup-save" @("--slot", "$SetupSlot")
            if (@($script:Cases | Where-Object { $_.name -eq "setup-save" -and $_.status -eq "PASS" }).Count -eq 1) {
                Invoke-SimpleCase "setup-recall" "setup-recall" @("--slot", "$SetupSlot")
            } else { Add-Case "setup-recall" "N/A" "Setup save did not succeed" }
            try {
                $display = Invoke-Cli -Stage "reference-source-display" -Command "channel-display" `
                    -Options @("--channel", "1", "--query")
                if ((Get-Readback $display "display") -eq $true) {
                    Invoke-SimpleCase "reference-save" "reference-save" @("--slot", "$ReferenceSlot", "--source-channel", "1")
                    if (@($script:Cases | Where-Object { $_.name -eq "reference-save" -and $_.status -eq "PASS" }).Count -eq 1) {
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
            foreach ($name in @("setup-save", "setup-recall", "reference-save", "reference-display")) {
                Add-Case $name "N/A" "Requires -IncludeStorageWrites and explicit slots"
            }
        }
    }
} finally {
    Write-Report
}
if ($script:Failure) { exit 1 }
