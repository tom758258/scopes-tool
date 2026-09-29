param([string]$ScriptPath, [string]$FixturePath)

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

function Invoke-FakePositionProbe {
    param([string]$Action, [object]$Original = $null)
    if ($null -eq $script:PositionState) {
        $script:PositionState = @{ mode = "OFF"; delay = 0.003; position = 40; length = 1000; rate = 1000 }
    }
    if ($Action -in @("on", "off")) { $script:PositionState.mode = $Action.ToUpperInvariant() }
    if ($Action -eq "center") { $script:PositionState.position = 50 }
    if ($Action -eq "restore") { $script:PositionState = $Original.Clone() }
    [IO.File]::WriteAllText((Join-Path (Split-Path $FixturePath) "position-state.json"), ($script:PositionState | ConvertTo-Json))
    return $script:PositionState.Clone()
}

function Invoke-FakeTransport {
    param([string]$Command, [string[]]$Options)

    # Fresh values match the independent fake CLI invocations; only explicit state persists.
    $scenario = $script:FixtureJson | ConvertFrom-Json
    $property = $scenario.values.PSObject.Properties[$Command]
    $value = if ($null -eq $property) { [pscustomobject]@{} } else { $property.Value }
    if ($Command -eq "timebase-position" -and $null -ne $script:PositionState) {
        $value.position_seconds = if ($script:PositionState.mode -eq "ON") { $script:PositionState.delay } else {
            (50 - $script:PositionState.position) / 100 * ($script:PositionState.length / $script:PositionState.rate)
        }
        if ($scenario.position_mismatch) { $value.position_seconds += 1 }
    }
    $payload = @{ ok = $true; idn = $scenario.idn; capabilities = $scenario.capabilities; result = $value }
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
            $state.mode = if ($hasX -and $hasY) { "SCREEN" } elseif ($hasX) { "TIME" } elseif ($hasY) { "AMPLITUDE" } else { "OFF" }
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

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw "Failed to parse validator: $($parseErrors[0].Message)" }
$invoke = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq "Invoke-Cli"
}, $true)
if ($null -eq $invoke) { throw "Invoke-Cli was not found" }
# Replace only transport, retaining the real argv, error classification, readback and report code.
$assignments = @($invoke.Body.EndBlock.Statements | Where-Object {
    $_ -is [System.Management.Automation.Language.AssignmentStatementAst]
})
$first = @($assignments | Where-Object { $_.Left.Extent.Text -eq '$psi' })
$last = @($assignments | Where-Object { $_.Left.Extent.Text -eq '$stderr' })
if ($first.Count -ne 1 -or $last.Count -ne 1) { throw "Invoke-Cli transport boundary changed" }
$transport = @'
$start = Get-Date
    $fake = Invoke-FakeTransport -Command $Command -Options $Options
    $process = [pscustomobject]@{ ExitCode = $fake.ExitCode }
    $script:HardwareTouched = $true
    $timedOut = $false
    $stdout = $fake.Payload | ConvertTo-Json -Depth 20 -Compress
    $stderr = ""
'@
$source = $ast.Extent.Text
$probe = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq "Invoke-PositionProbe"
}, $true)
$source = $source.Remove($probe.Extent.StartOffset, $probe.Extent.EndOffset - $probe.Extent.StartOffset).Insert(
    $probe.Extent.StartOffset, 'function Invoke-PositionProbe { param($Action, $Original) Invoke-FakePositionProbe $Action $Original }')
$offset = $first[0].Extent.StartOffset
$source = $source.Remove($offset, $last[0].Extent.EndOffset - $offset).Insert($offset, $transport)
# The in-memory script retains the validator's helper and repository locations.
$source = $source.Replace('$PSScriptRoot', '$script:ValidatorRoot')
$switches = @($ast.ParamBlock.Parameters | Where-Object { $_.StaticType -eq [switch] } |
    ForEach-Object { $_.Name.VariablePath.UserPath })
$parameters = @{}
for ($index = 0; $index -lt $fixture.arguments.Count; $index++) {
    $name = $fixture.arguments[$index].TrimStart('-')
    if ($name -in $switches) { $parameters[$name] = $true }
    else { $index++; $parameters[$name] = $fixture.arguments[$index] }
}
& ([scriptblock]::Create($source)) @parameters
if ($script:Failure) { exit 1 }
