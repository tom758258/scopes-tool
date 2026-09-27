param([string]$ScriptPath, [string]$FixturePath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:FixtureJson = [IO.File]::ReadAllText($FixturePath)
$fixture = $script:FixtureJson | ConvertFrom-Json
$script:ModeQueries = 0
$script:VectorsSet = $false
$script:HiddenCaptured = $false
$script:ValidatorRoot = Split-Path -Parent $ScriptPath

function Invoke-FakeTransport {
    param([string]$Command, [string[]]$Options)

    # Fresh values match the independent fake CLI invocations; only explicit state persists.
    $scenario = $script:FixtureJson | ConvertFrom-Json
    $property = $scenario.values.PSObject.Properties[$Command]
    $value = if ($null -eq $property) { [pscustomobject]@{} } else { $property.Value }
    $payload = @{ ok = $true; idn = $scenario.idn; capabilities = $scenario.capabilities; result = $value }
    $fakeError = $null
    if ($Command -eq "math-operator" -and $Options -contains "--query") { $fakeError = $scenario.math_error }
    if ($Command -eq "cursor" -and $Options -contains "--x1") { $fakeError = $scenario.cursor_error }
    if ($null -ne $fakeError) {
        return @{ ExitCode = 1; Payload = @{ ok = $false; error = @{ type = $fakeError[0]; message = $fakeError[1] } } }
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
