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
    [string] $ImageFilename,
    [string] $WaveformFilename,
    [ValidateRange(1, 4)][int] $WaveformSourceChannel,
    [switch] $IncludeConfigurationActions,
    [switch] $IncludeScreenshot,
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
                                    $PSBoundParameters.ContainsKey("ReferenceSlot") -or
                                    $PSBoundParameters.ContainsKey("ImageFilename") -or
                                    $PSBoundParameters.ContainsKey("WaveformFilename") -or
                                    $PSBoundParameters.ContainsKey("WaveformSourceChannel"))) {
    Write-LiveUsageError -Domain "tektronix" "Storage slots and filenames require -IncludeStorageWrites."
}
if ($PSBoundParameters.ContainsKey("WaveformFilename") -or $PSBoundParameters.ContainsKey("WaveformSourceChannel")) {
    if ([string]::IsNullOrWhiteSpace($WaveformFilename) -or
        -not $PSBoundParameters.ContainsKey("WaveformSourceChannel") -or
        $WaveformSourceChannel -gt $targets[$script:Target].channels -or
        $WaveformFilename -match '[^\x20-\x7E]|[";*?%]' -or
        $WaveformFilename.EndsWith("/") -or $WaveformFilename.EndsWith("\")) {
        Write-LiveUsageError -Domain "tektronix" "Waveform save requires a safe explicit filename and a model-valid -WaveformSourceChannel."
    }
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
    param([string]$Stage, [string]$Command, [string[]]$Options = @(), [switch]$AllowCurrentStateNA, [switch]$ExpectHiddenCaptureRejection)
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
        throw "$Stage failed (exit $($record.exit_code), timeout=$timedOut); see $stdoutPath and $stderrPath"
    }
    $payload = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json -ErrorAction Stop
    if ($payload.ok -ne $true) {
        $invocation.result = "FAIL"
        throw "$Stage returned ok=false; see $jsonPath"
    }
    return $payload
}

function Invoke-PositionProbe {
    param([ValidateSet("read", "on", "off", "center", "restore")][string]$Action, [object]$Original = $null)
    # Validation-only raw access; public commands keep all mode handling in Core.
    $probePath = Join-Path $script:RunPaths.Private "position-probe.py"
    $source = @'
import json, math, sys
from scopes_tool_core.visa_backend import VisaBackend

resource, library, action, original_path = sys.argv[1:]
from pathlib import Path
backend = VisaBackend(resource, visa_library=None if library == "system_visa" else library)
try:
    identity = backend.query("*IDN?").strip().upper().split(",")
    if identity[:2] != ["TEKTRONIX", "TBS2074B"]:
        raise ValueError("Position probe requires the expected TBS2074B identity")
    def number(command):
        value = float(backend.query(command).strip().split()[-1])
        if not math.isfinite(value):
            raise ValueError("Non-finite horizontal readback")
        return value
    def snapshot():
        mode = backend.query("HORizontal:MAIn:DELay:MODe?").strip().split()[-1].upper()
        if mode not in {"ON", "OFF", "1", "0"}:
            raise ValueError("Invalid delay mode readback")
        return dict(mode="ON" if mode in {"ON", "1"} else "OFF",
                    delay=number("HORizontal:MAIn:DELay:TIMe?"),
                    position=number("HORizontal:POSition?"),
                    length=number("HORizontal:RECOrdlength?"),
                    rate=number("HORizontal:SAMPLERate?"))
    if action in {"on", "off"}:
        backend.write("HORizontal:MAIn:DELay:MODe " + action.upper())
    elif action == "center":
        backend.write("HORizontal:POSition 50")
    elif action == "restore":
        original = json.loads(Path(original_path).read_text(encoding="utf-8"))
        failures = []
        for command, value in (("HORizontal:POSition", int(original["position"])),
                               ("HORizontal:MAIn:DELay:TIMe", original["delay"]),
                               ("HORizontal:MAIn:DELay:MODe", original["mode"])):
            try:
                backend.write(f"{command} {value}")
            except Exception as exc:
                failures.append(str(exc))
        if failures:
            raise RuntimeError("; ".join(failures))
    print(json.dumps(snapshot()))
finally:
    backend.close()
'@
    Write-Utf8NoBomText -LiteralPath $probePath -Text $source
    $originalJson = if ($null -eq $Original) { "null" } else { $Original | ConvertTo-Json -Compress }
    $originalPath = Join-Path $script:RunPaths.Private "position-original.json"
    Write-Utf8NoBomText -LiteralPath $originalPath -Text $originalJson
    $library = if ($script:LiveArguments -contains "--visa-library") { "@py" } else { "system_visa" }
    $stderrPath = Join-Path $script:RunPaths.Private "position-$Action.stderr.txt"
    $output = & $pythonPath $probePath $Resource $library $Action $originalPath 2> $stderrPath
    if ($LASTEXITCODE -ne 0) { throw "Position probe $Action failed; see $stderrPath" }
    Write-Utf8NoBomText -LiteralPath (Join-Path $script:RunPaths.Private "position-$Action.json") -Text ($output -join "`n")
    return ($output -join "`n" | ConvertFrom-Json)
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
    "fixed_acquisition_memory_mode": capabilities.fixed_acquisition_memory_mode,
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

function Invoke-AcquisitionSummaryProbe {
    # Validation-only Core aggregate probe. This deliberately does not add a
    # public CLI command for the WebUI-only live-data snapshot.
    $probePath = Join-Path $script:RunPaths.Private "acquisition-summary-probe.py"
    $source = @'
import json, sys
from scopes_tool_core.operations import query_acquisition_summary
from scopes_tool_core.run_config import RunModeOptions, ResolvedRunConfig, open_scope_for_run

resource, library, target = sys.argv[1:]
options = RunModeOptions(expected_physical_model_id=target)
config = ResolvedRunConfig(
    mode="live",
    planning_physical_model_id=None,
    expected_physical_model_id=target,
    capabilities=None,
    resource=resource,
    visa_library=None if library == "system_visa" else library,
    options=options,
)
scope = open_scope_for_run(config)
try:
    print(json.dumps(query_acquisition_summary(scope)))
finally:
    scope.close()
'@
    Write-Utf8NoBomText -LiteralPath $probePath -Text $source
    $library = if ($script:LiveArguments -contains "--visa-library") { "@py" } else { "system_visa" }
    $stderrPath = Join-Path $script:RunPaths.Private "acquisition-summary-probe.stderr.txt"
    $output = & $pythonPath $probePath $Resource $library $script:Target 2> $stderrPath
    $script:HardwareTouched = $true
    if ($LASTEXITCODE -ne 0) { throw "Acquisition summary probe failed; see $stderrPath" }
    Write-Utf8NoBomText -LiteralPath (Join-Path $script:RunPaths.Private "acquisition-summary.json") -Text ($output -join "`n")
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
                  ([double]$original -lt $(if ($script:Target -eq "tektronix-tbs2074b") { 4e-8 } else { 5e-7 }) -or
                   [double]$original -gt $(if ($script:Target -eq "tektronix-tbs2074b") { 8 } else { 10 }))) {
            $status = "N/A"
            $detail = "current holdoff is outside the model's supported setter range"
        } elseif ($Name -eq "channel-probe" -and $script:Target -ne "tektronix-tbs2074b" -and
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
        if ($ImageFilename) { $lines += "The explicitly requested instrument image file may have been overwritten." }
    }
    if ($IncludeConfigurationActions) {
        $lines += "Cursor and measurement configurations were not restored; see individual case outcomes."
    }
    Write-Utf8NoBomLines -LiteralPath (Join-Path $script:RunPaths.Private "summary.md") -Lines $lines
    Write-Host "[live][tektronix] private artifacts: $($script:RunPaths.Private)"
}

try {
    try {
        $script:CoreProfile = Invoke-CoreProfileProbe
    } catch {
        Add-Case -Name "core-profile" -Status "FAIL" -Detail $_.Exception.Message
        throw
    }
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
        Invoke-RoundTrip "channel-units" "channel-units" $ch "units" "--units" @("volt", "amp")
        foreach ($name in @("acquisition-points", "record-length")) {
            Invoke-SimpleCase $name $name @("--query")
        }
        Invoke-SimpleCase "channel-summary" "channel-summary"
        if ($script:Target -eq "tektronix-tbs2074b") {
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
        if ($script:Target -eq "tektronix-tbs2074b") {
            if (-not $IncludeConfigurationActions) {
                Add-Case "timebase-position-modes" "N/A" "Requires -IncludeConfigurationActions; temporarily switches Delay Mode"
            } else {
                $originalPosition = $null
                try {
                    $originalPosition = Invoke-PositionProbe "read"
                    foreach ($positionMode in @("on", "off")) {
                        $positionRaw = Invoke-PositionProbe $positionMode
                        if ($positionRaw.mode -ne $positionMode.ToUpperInvariant()) { throw "Delay Mode did not change to $positionMode" }
                        if ($positionRaw.length -le 0 -or $positionRaw.rate -le 0) { throw "Invalid horizontal record geometry" }
                        $positionExpected = if ($positionMode -eq "on") { $positionRaw.delay } else { (50 - $positionRaw.position) / 100 * ($positionRaw.length / $positionRaw.rate) }
                        $positionBefore = Invoke-Cli "position-$positionMode-query" "timebase-position" @("--query")
                        $positionSeconds = Get-Readback $positionBefore "position_seconds"
                        if (-not (Test-ReadbackEqual $positionSeconds $positionExpected)) { throw "Public position differs from raw $positionMode position" }
                        $null = Invoke-Cli "position-$positionMode-set" "timebase-position" @("--seconds", (Format-Setting $positionSeconds))
                        $positionAfter = Invoke-PositionProbe "read"
                        if ($positionAfter.mode -ne $positionRaw.mode) { throw "Public position setter changed Delay Mode" }
                        if ($positionMode -eq "on" -and -not (Test-ReadbackEqual $positionAfter.delay $positionRaw.delay)) { throw "Delay time changed" }
                        if ($positionMode -eq "off" -and $positionAfter.position -ne [math]::Round($positionRaw.position)) { throw "Integer position changed" }
                    }
                    $positionCenter = Invoke-PositionProbe "center"
                    if ($positionCenter.mode -ne "OFF" -or $positionCenter.position -ne 50) { throw "Center setup failed" }
                    $positionPublic = Invoke-Cli "position-center-query" "timebase-position" @("--query")
                    if (-not (Test-ReadbackEqual (Get-Readback $positionPublic "position_seconds") 0)) { throw "Center is not zero seconds" }
                    Add-Case "timebase-position-modes" "PASS" "Delay seconds and record percentage agree with public readback"
                } catch { Add-Case "timebase-position-modes" "FAIL" $_.Exception.Message }
                finally {
                    if ($null -ne $originalPosition) {
                        try {
                            $positionRestored = Invoke-PositionProbe "restore" $originalPosition
                            foreach ($positionField in @("position", "delay", "mode")) {
                                if (-not (Test-ReadbackEqual $positionRestored.$positionField $originalPosition.$positionField)) { throw "Position restore mismatch: $positionField" }
                            }
                            Add-Case "timebase-position-restore" "PASS"
                        } catch { Add-Case "timebase-position-restore" "FAIL" $_.Exception.Message }
                    }
                }
            }
        }
        Invoke-RoundTrip "acquisition" "acquisition" @() "type" "--type" @($script:CoreProfile.acquisition_modes)
        try {
            $nativeAcquisition = Invoke-Cli -Stage "acquisition-summary-native" -Command "acquisition" -Options @("--query")
            $nativeType = [string](Get-Readback $nativeAcquisition "type")
            $summary = Invoke-AcquisitionSummaryProbe
            $expectedMemoryMode = [string]$script:CoreProfile.fixed_acquisition_memory_mode
            if ($expectedMemoryMode -cne "realtime") {
                throw "Registered Tek profile does not declare fixed realtime acquisition mode."
            }
            if ([string]$summary.mode -cne $expectedMemoryMode) {
                throw "Acquisition memory mode differs from the Core profile."
            }
            if ([string]::IsNullOrWhiteSpace([string]$summary.type) -or [string]$summary.type -ceq "unknown") {
                throw "Acquisition type is unavailable."
            }
            if ([string]$summary.type -cne $nativeType) {
                throw "Acquisition summary type differs from acquisition --query."
            }
            Add-Case "acquisition-summary" "PASS" "Fixed realtime memory mode; acquisition type agrees with native query"
        } catch { Add-Case "acquisition-summary" "FAIL" $_.Exception.Message }
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
        if ($script:Target -eq "tektronix-tbs2074b") {
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

        $specialTrigger = if ($script:Target -eq "tektronix-tbs2074b") { "trigger-runt" } else { "trigger-tv" }
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
                if ($state.channel -notin @(1, 2) -or $state.polarity -notin @("positive", "negative") -or
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
        try {
            $before = Invoke-Cli -Stage "display-persistence-before" -Command "display-persistence" -Options @("--query")
            if ($before.result.mode -in @("minimum", "infinite")) {
                Invoke-SameValueCase "display-persistence" "display-persistence" $before @("--mode", $before.result.mode) @("mode")
            } elseif ($null -ne $before.result.seconds) {
                Invoke-SameValueCase "display-persistence" "display-persistence" $before @("--seconds", (Format-Setting $before.result.seconds)) @("seconds")
            } else { throw "Missing persistence mode or seconds readback." }
        } catch { Add-Case "display-persistence" "FAIL" $_.Exception.Message }
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
            Write-Warning "Cursor and measurement configuration actions are not restored; cursors end off and measurements end cleared."
            if ([string]$script:CoreProfile.cursor_source_selection -ceq "selected-waveform") {
                $cursorXPassed = $false
                try {
                    $position = Invoke-Cli -Stage "cursor-timebase-position" -Command "timebase-position" -Options @("--query")
                    $x = Get-Readback $position "position_seconds"
                    $null = Invoke-Cli -Stage "cursor-set" -Command "cursor" -Options @(
                        "--source-channel", "1", "--x1", (Format-Setting $x), "--x2", (Format-Setting $x))
                    $after = Invoke-Cli -Stage "cursor-set-after" -Command "cursor" -Options @("--query")
                    foreach ($field in @("x1_seconds", "x2_seconds")) {
                        if (-not (Test-ReadbackEqual $x (Get-Readback $after $field))) { throw "Cursor X position readback differs." }
                    }
                    $display = Invoke-Cli -Stage "cursor-set-source-display" -Command "channel-display" -Options @("--channel", "1", "--query")
                    if ((Get-Readback $display "display") -ne $true) { throw "Cursor source channel is not displayed." }
                    Add-Case "cursor-set" "PASS" "CH1 X cursors at current timebase position; Core verifies selected-waveform source"
                    $cursorXPassed = $true
                } catch { Add-Case "cursor-set" "FAIL" $_.Exception.Message }

                $voltageChannel = $null
                if (-not $cursorXPassed) {
                    Add-Case "cursor-set-y" "N/A" "Skipped after cursor-set failure"
                    Add-Case "cursor-set-screen" "N/A" "Skipped after cursor-set failure"
                } else {
                try {
                    foreach ($candidate in @(1, 2)) {
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
                if ($null -eq $voltageChannel -and @($script:Cases | Where-Object { $_.name -eq "cursor-set-y" }).Count -eq 0) {
                    Add-Case "cursor-set-y" "N/A" "CH1/CH2 are not currently in physical volt units"
                    Add-Case "cursor-set-screen" "N/A" "CH1/CH2 are not currently in physical volt units"
                } elseif ($null -ne $voltageChannel) {
                    $y = $null
                    $cursorYPassed = $false
                    try {
                        $offset = Invoke-Cli -Stage "cursor-y-offset" -Command "channel-offset" -Options @("--channel", "$voltageChannel", "--query")
                        $y = Get-Readback $offset "volts"
                        $null = Invoke-Cli -Stage "cursor-set-y" -Command "cursor" -Options @(
                            "--source-channel", "$voltageChannel", "--y1", (Format-Setting $y), "--y2", (Format-Setting $y))
                        $after = Invoke-Cli -Stage "cursor-set-y-after" -Command "cursor" -Options @("--query")
                        foreach ($field in @("y1_volts", "y2_volts")) {
                            if (-not (Test-ReadbackEqual $y (Get-Readback $after $field))) { throw "Cursor Y position readback differs." }
                        }
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
                                "--source-channel", "$voltageChannel",
                                "--x1", (Format-Setting $x), "--x2", (Format-Setting $x),
                                "--y1", (Format-Setting $y), "--y2", (Format-Setting $y))
                            $after = Invoke-Cli -Stage "cursor-set-screen-after" -Command "cursor" -Options @("--query")
                            foreach ($field in @("x1_seconds", "x2_seconds")) {
                                if (-not (Test-ReadbackEqual $x (Get-Readback $after $field))) { throw "Cursor SCREEN X readback differs." }
                            }
                            foreach ($field in @("y1_volts", "y2_volts")) {
                                if (-not (Test-ReadbackEqual $y (Get-Readback $after $field))) { throw "Cursor SCREEN Y readback differs." }
                            }
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
            }
            foreach ($name in @("cursor-off", "measure-install", "measure-clear")) {
                Add-Case $name "N/A" "Requires -IncludeConfigurationActions; no public configuration restore path"
            }
        }

        if ($script:Target -eq "tektronix-tbs2074b") {
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

        if ($script:Target -eq "tektronix-tbs2074b") {
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

        if ($script:Target -eq "tektronix-tbs2074b") {
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
            Write-Warning "Acquisition actions change run/stop state; final state is stop."
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
} finally {
    Write-Report
}
if ($script:Failure) { exit 1 }
