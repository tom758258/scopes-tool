param(
    [string]$ScriptPath, [string]$FixturePath, [string]$PythonPath, [string]$OutputRoot,
    [ValidateSet("enter", "decline", "whitespace", "null", "unavailable")]
    [string]$OperatorConfirmation = "enter"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:FixtureJson = [IO.File]::ReadAllText($FixturePath)
$fixture = $script:FixtureJson | ConvertFrom-Json
$script:ModeQueries = 0
$script:VectorsSet = $false
$script:HiddenCaptured = $false
$script:CursorState = $null
$script:ValidatorRoot = Split-Path -Parent $ScriptPath
$script:PositionState = $null

# Test double for the operator confirmation prompt. The fake harness runs
# non-interactively, so the confirmation must be simulated here only. The real
# runner keeps using the Read-Host cmdlet and exposes no bypass option.
function Read-Host {
    param([Parameter(Position = 0)][string]$Prompt)

    switch ($OperatorConfirmation) {
        "enter" { return "" }
        "decline" { return "N" }
        "whitespace" { return " " }
        "null" { return $null }
        "unavailable" { throw "No interactive console is attached." }
    }
    throw "Unsupported operator confirmation mode: $OperatorConfirmation"
}

function Invoke-FakeTransport {
    param([string]$Command, [string[]]$Options, [switch]$Simulate)

    # Fresh values match the independent fake CLI invocations; only explicit state persists.
    $scenario = $script:FixtureJson | ConvertFrom-Json
    $property = $scenario.values.PSObject.Properties[$Command]
    $value = if ($null -eq $property) { [pscustomobject]@{} } else { $property.Value }
    if ($Command -in @("run", "stop-acquisition")) {
        $status = @{ value = 0; raw = "0" }
        if ($scenario.native_status_command -eq $Command) {
            $status.value = [int]$scenario.native_status_value
            $status.raw = [string]$scenario.native_status_raw
        }
        $value | Add-Member -Force -NotePropertyName post_command_status -NotePropertyValue $status
    }
    $idn = if ($Simulate) { $scenario.idn } else { $scenario.live_idn }
    $capabilities = if ($Simulate) { $scenario.capabilities } else { $scenario.live_capabilities }
    $payload = @{ ok = $true; idn = $idn; capabilities = $capabilities; result = $value }
    $fakeError = $null
    if ($Command -eq "math-operator" -and $Options -contains "--query") { $fakeError = $scenario.math_error }
    if ($Command -eq "cursor" -and $Options -contains "--x1") { $fakeError = $scenario.cursor_error }
    if ($null -ne $fakeError) {
        return @{ ExitCode = 1; Payload = @{ ok = $false; error = @{ type = $fakeError[0]; message = $fakeError[1] } } }
    }
    if ($Command -eq "cursor") {
        if ($Options -contains "--off") {
            $script:CursorState = [pscustomobject]@{
                mode = "OFF"; source_channel = $null
                x1_seconds = $null; x2_seconds = $null
                y1_volts = $null; y2_volts = $null
            }
        } elseif ($Options -notcontains "--query") {
            $state = [ordered]@{
                mode = "OFF"; source_channel = $null
                x1_seconds = $null; x2_seconds = $null
                y1_volts = $null; y2_volts = $null
            }
            if ($null -ne $script:CursorState) {
                foreach ($name in @("source_channel", "x1_seconds", "x2_seconds", "y1_volts", "y2_volts")) {
                    $state[$name] = $script:CursorState.$name
                }
            }
            if ($Options -contains "--source-channel") {
                $state.source_channel = [int]$Options[[Array]::IndexOf($Options, "--source-channel") + 1]
            }
            $hasX = $false
            $hasY = $false
            foreach ($mapping in @(
                @("--x1", "x1_seconds", "x"), @("--x2", "x2_seconds", "x"),
                @("--y1", "y1_volts", "y"), @("--y2", "y2_volts", "y")
            )) {
                if ($Options -contains $mapping[0]) {
                    $state[$mapping[1]] = [double]$Options[[Array]::IndexOf($Options, $mapping[0]) + 1]
                    if ($mapping[2] -eq "x") { $hasX = $true } else { $hasY = $true }
                }
            }
            $requested = if ($Options -contains "--function") {
                [string]$Options[[Array]::IndexOf($Options, "--function") + 1]
            } else { $null }
            if ($requested -ceq "off") {
                $state = [ordered]@{
                    mode = "OFF"; source_channel = $null
                    x1_seconds = $null; x2_seconds = $null
                    y1_volts = $null; y2_volts = $null
                }
            } elseif ($null -ne $requested) {
                $state.mode = @{
                    "screen" = "SCREEN"; "waveform" = "WAVEform"
                    "vbars" = "VBArs"; "hbars" = "HBArs"
                }[$requested]
            } else {
                $state.mode = if ($hasX -and $hasY) { "SCREEN" } elseif ($hasX) { "TIME" } elseif ($hasY) { "AMPLITUDE" } else { "OFF" }
            }
            $script:CursorState = [pscustomobject]$state
        } elseif ($null -ne $script:CursorState) {
            $value = $script:CursorState
            $payload.result = $value
        }
    }
    if ($Command -eq "display-vectors") {
        if ($Options -contains "--on") { $script:VectorsSet = $true }
        if ($scenario.vectors_mismatch -and $Options -contains "--query" -and $script:VectorsSet) {
            $value.value = $false
        }
    }
    if ($Command -eq "trigger-mode" -and $Options -contains "--query") {
        $script:ModeQueries += 1
        if ($scenario.mismatch -and $script:ModeQueries -gt 1) { $value.mode = "glitch" }
    }
    $channel = if ($Options -contains "--channel") { $Options[[Array]::IndexOf($Options, "--channel") + 1] } else { $null }
    if ($Command -eq "channel-display" -and $channel -eq "2" -and $scenario.hidden_outcome) {
        $value.display = $scenario.hidden_outcome -eq "display-on" -and $script:HiddenCaptured
    }
    if ($Command -eq "capture") {
        if ($channel -eq "2" -and $scenario.hidden_outcome) {
            $script:HiddenCaptured = $true
            if ($scenario.hidden_outcome -eq "unexpected-success") {
                return @{ ExitCode = 0; Payload = @{ ok = $true; result = @{} } }
            }
            $errorType = if ($scenario.hidden_outcome -eq "wrong-error") { "OscilloscopeError" } else { "WaveformResponseError" }
            return @{ ExitCode = 1; Payload = @{ ok = $false; error = @{
                type = $errorType
                message = "CH2 is not displayed; waveform capture requires a displayed analog channel"
            } } }
        }
        $csv = $Options[[Array]::IndexOf($Options, "--csv") + 1]
        $meta = $Options[[Array]::IndexOf($Options, "--meta") + 1]
        [IO.File]::WriteAllText($csv, $scenario.csv_text)
        [IO.File]::WriteAllText($meta, (@{ actual_points = $scenario.points } | ConvertTo-Json))
        $payload.result = @{ format = "BYTE"; actual_points = $scenario.points }
    }
    if ($Command -eq "screenshot") {
        $path = $Options[[Array]::IndexOf($Options, "--output") + 1]
        [IO.File]::WriteAllBytes($path, [byte[]]$scenario.screenshot_bytes)
        $payload.result = @{ format = $scenario.screenshot_format; byte_count = $scenario.screenshot_bytes.Count; image_path = $path }
    }
    return @{ ExitCode = 0; Payload = $payload }
}

$fixture = $script:FixtureJson | ConvertFrom-Json
$script:RepoRoot = (Resolve-Path -LiteralPath (Join-Path (Split-Path -Parent $ScriptPath) "..")).Path
$RepoRoot = $script:RepoRoot
. (Join-Path $script:RepoRoot "scripts/_validation_helpers.ps1")
. (Join-Path $script:RepoRoot "scripts/_artifact_privacy.ps1")
. (Join-Path $script:RepoRoot "scripts/_live_tektronix_helpers.ps1")

$script:Target = switch ([string]$fixture.idn.model.ToUpperInvariant()) {
    "TBS2074" { "tektronix-tbs2074" }
    "TDS2024B" { "tektronix-tds2024b" }
    "TBS1052B" { "tektronix-tbs1052b" }
    default { throw "Unsupported fake model: $($fixture.idn.model)" }
}
$script:Connection = "usb"
$script:IsTektronix = $true
$script:BackendName = "system_visa"
$script:LiveConnectionArguments = @("--live", "--resource", "USB0::FAKE::INSTR")
$script:CliInvocationIndex = 0
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:ShareableGenerationFailed = $false
$script:HardwareTouched = $false
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:ModeQueries = 0
$script:VectorsSet = $false
$script:HiddenCaptured = $false
$script:CursorState = $null
$script:PositionState = $null
$script:FixtureJson = [IO.File]::ReadAllText($FixturePath)
$script:TargetProfile = Get-ValidationTargetProfile -Target $script:Target -IncludeTektronix
$Resource = "USB0::FAKE::INSTR"
$Python = $PythonPath
$script:Python = $PythonPath
$script:RunLayout = New-ValidationRunDirectory -BaseRoot $OutputRoot -Prefix "run"
$script:RunDirectory = $script:RunLayout.Root
$script:RunRoot = $script:RunLayout.Private
$script:ShareableRoot = $script:RunLayout.Shareable
$script:RunPaths = [pscustomobject]@{ Private = $script:RunRoot }

$tokens = $null
$parseErrors = $null
$cliAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count) { throw "Failed to parse CLI runner: $($parseErrors[0].Message)" }
$summaryAst = $cliAst.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq "Write-Summary"
}, $true)
if ($null -eq $summaryAst) { throw "Write-Summary was not found" }
Invoke-Expression $summaryAst.Extent.Text
$diagnosticAst = $cliAst.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq "Add-Diagnostic"
}, $true)
if ($null -eq $diagnosticAst) { throw "Add-Diagnostic was not found" }
Invoke-Expression $diagnosticAst.Extent.Text

$helperPath = Join-Path (Split-Path -Parent $ScriptPath) "_live_tektronix_helpers.ps1"
$helperAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $helperPath, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count) { throw "Failed to parse Tektronix helper: $($parseErrors[0].Message)" }
$runnerAst = $helperAst.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-TektronixCliValidation"
}, $true)
if ($null -eq $runnerAst) { throw "Invoke-TektronixCliValidation was not found" }
$invokeAst = $runnerAst.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq "Invoke-Cli"
}, $true)
if ($null -eq $invokeAst) { throw "Nested Invoke-Cli was not found" }
$assignments = @($invokeAst.Body.EndBlock.Statements | Where-Object {
    $_ -is [System.Management.Automation.Language.AssignmentStatementAst]
})
$first = @($assignments | Where-Object { $_.Left.Extent.Text -eq '$psi' })
$last = @($assignments | Where-Object { $_.Left.Extent.Text -eq '$stderr' })
if ($first.Count -ne 1 -or $last.Count -ne 1) { throw "Invoke-Cli transport boundary changed" }
$transport = @'
$start = Get-Date
    $fake = Invoke-FakeTransport -Command $Command -Options $Options -Simulate:$Simulate
    $process = [pscustomobject]@{ ExitCode = $fake.ExitCode }
    if (-not $Simulate) { $script:HardwareTouched = $true }
    $timedOut = $false
    $stdout = $fake.Payload | ConvertTo-Json -Depth 20 -Compress
    $stderr = ""
'@
$source = $runnerAst.Extent.Text
$startOffset = $first[0].Extent.StartOffset - $runnerAst.Extent.StartOffset
$endOffset = $last[0].Extent.EndOffset - $runnerAst.Extent.StartOffset
$source = $source.Remove($startOffset, $endOffset - $startOffset).Insert($startOffset, $transport)

$arguments = @($fixture.arguments)
$parameterValues = @{}
$connection = "usb"
$resource = "USB0::FAKE::INSTR"
for ($index = 0; $index -lt $arguments.Count; $index++) {
    $name = $arguments[$index].TrimStart('-')
    if ($name -in @("IncludeAcquisitionActions", "IncludeAutoscale", "IncludeStorageWrites", "IncludeConfigurationActions", "IncludeScreenshot")) {
        $parameterValues[$name] = $true
    } elseif ($name -in @("SetupSlot", "ReferenceSlot", "ImageFilename", "WaveformFilename", "WaveformSourceChannel", "Connection", "Resource")) {
        $index++
        if ($name -eq "Connection") { $connection = $arguments[$index] }
        elseif ($name -eq "Resource") { $resource = $arguments[$index] }
        else { $parameterValues[$name] = $arguments[$index] }
    }
}
$script:Connection = $connection
$script:LiveConnectionArguments = @("--live", "--resource", $resource)
$Resource = $resource
$IncludeAcquisitionActions = [bool]$parameterValues["IncludeAcquisitionActions"]
$IncludeAutoscale = [bool]$parameterValues["IncludeAutoscale"]
$IncludeStorageWrites = [bool]$parameterValues["IncludeStorageWrites"]
$IncludeConfigurationActions = [bool]$parameterValues["IncludeConfigurationActions"]
$IncludeScreenshot = [bool]$parameterValues["IncludeScreenshot"]
$SetupSlot = if ($parameterValues.ContainsKey("SetupSlot")) { [int]$parameterValues["SetupSlot"] } else { 1 }
$ReferenceSlot = if ($parameterValues.ContainsKey("ReferenceSlot")) { [int]$parameterValues["ReferenceSlot"] } else { 1 }
$ImageFilename = [string]$parameterValues["ImageFilename"]
$WaveformFilename = [string]$parameterValues["WaveformFilename"]
$WaveformSourceChannel = if ($parameterValues.ContainsKey("WaveformSourceChannel")) { [int]$parameterValues["WaveformSourceChannel"] } else { 1 }

# Run the real Tektronix branch tail from live-cli-check.ps1 instead of a local
# copy, so the fake harness observes the same Summary, totals, and exit codes as
# the public runner.
$tektronixBranchAst = $null
foreach ($statement in $cliAst.EndBlock.Statements) {
    if ($statement -isnot [System.Management.Automation.Language.IfStatementAst]) { continue }
    if ($statement.Clauses[0].Item2.Extent.Text.Contains("Invoke-TektronixCliValidation")) {
        $tektronixBranchAst = $statement
    }
}
if ($null -eq $tektronixBranchAst) { throw "Tektronix validation branch was not found" }

& ([scriptblock]::Create($source + "`n" + $tektronixBranchAst.Extent.Text))
