param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$ScenarioPath,
    [Parameter(Mandatory = $true)][string]$ScratchRoot
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Keysight-style contract harness: one PowerShell host, many independently
# reset fake scenarios. Actual production nested functions own the comparisons
# and restoration semantics; no hardware or Python CLI process is launched.
$helper = Join-Path $RepoRoot "scripts/_live_tektronix_helpers.ps1"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $helper, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }
$names = @(
    "Get-Readback", "Test-ReadbackEqual", "Assert-ReadbackEqual",
    "Invoke-RoundTrip", "Invoke-SameValueCase", "Invoke-SpecialTriggerCase"
)
$sources = New-Object System.Collections.Generic.List[string]
foreach ($name in $names) {
    $matches = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -ceq $name
    }, $true))
    if ($matches.Count -ne 1) { throw "Missing or ambiguous production function: $name" }
    $sources.Add($matches[0].Extent.Text)
}
$extracted = Join-Path $ScratchRoot "tektronix-extracted.ps1"
[IO.File]::WriteAllLines($extracted, $sources.ToArray(), [Text.UTF8Encoding]::new($false))
. $extracted
. $helper

$triggerLevelTolerances = @{
    "tektronix-tbs1052b" = 0.05
    "tektronix-tds2024b" = 0.05
}
$pulseWidthTimeTolerances = @{
    "tektronix-tbs1052b" = 1e-8
    "tektronix-tds2024b" = 1e-8
}

function Add-Case {
    param([string]$Name, [string]$Status, [string]$Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Status = $Status
        Detail = $Detail
    }
}
function Invoke-Cli {
    param(
        [string]$Stage,
        [string]$Command,
        [string[]]$Options = @(),
        [switch]$AllowCurrentStateNA,
        [switch]$ExpectHiddenCaptureRejection,
        [switch]$Simulate
    )
    $script:Stages.Add($Stage)
    $script:Calls.Add([pscustomobject]@{ stage = $Stage; command = $Command; options = @($Options) })
    $scenario = $script:Scenario
    if ($scenario.kind -eq "pulse") {
        switch ($Command) {
            "trigger-pulse-width" {
                $value = @{
                    mode = "glitch"; channel = 1; polarity = "positive"
                    qualifier = "greater-than"; greater_than_seconds = 1e-6
                    level_volts = 1.0
                }
                if ($Stage -eq "trigger-pulse-width-query") {
                    $value[$scenario.field] = $scenario.actual
                }
            }
            "trigger-mode" {
                $mode = if ($Stage -like "*edge-mode-query") { "edge" } else { "glitch" }
                $value = @{ mode = $mode }
            }
            "system-standard-event" { $value = @{ value = 0 } }
            "trigger-edge" {
                $value = @{ source_channel = 1; level_volts = 1.0; slope = "positive" }
            }
            default { throw "Unexpected pulse-width command: $Command at $Stage" }
        }
    } else {
        switch ($Command) {
            "trigger-edge" {
                $value = @{
                    source_channel = 1
                    level_volts = 1.0
                    slope = "positive"
                }
                if ($Stage -eq "trigger-edge-after") {
                    $value[$scenario.field] = $scenario.actual
                }
            }
            "trigger-edge-level" {
                $number = if ($Stage -eq "trigger-edge-level-after") {
                    $scenario.actual
                } else { $scenario.expected }
                $value = @{ level_volts = $number }
            }
            "channel-scale" {
                $value = @{ volts_per_division = 2.0 }
                if ($Stage -eq "channel-scale-after") {
                    $value.volts_per_division = $scenario.actual
                }
            }
            default { throw "Unexpected readback command: $Command at $Stage" }
        }
    }
    return [pscustomobject]@{ result = [pscustomobject]$value }
}

$scenarios = @(Get-Content -LiteralPath $ScenarioPath -Raw | ConvertFrom-Json)
$results = New-Object System.Collections.Generic.List[object]
foreach ($scenario in $scenarios) {
    # Important: reset all mutable fake state between scenarios, even though
    # the production functions and PowerShell interpreter are reused.
    $script:Scenario = $scenario
    $script:Target = [string]$scenario.target
    $script:Stages = New-Object System.Collections.Generic.List[string]
    $script:Calls = New-Object System.Collections.Generic.List[object]
    $script:CaseResults = [ordered]@{}
    $name = [string]$scenario.command
    try {
        switch ([string]$scenario.kind) {
            "edge" {
                if ($name -eq "trigger-edge-level") {
                    Invoke-RoundTrip "trigger-edge-level" "trigger-edge-level" @("--source-channel", "1") "level_volts" "--level-volts"
                } else {
                    $before = Invoke-Cli -Stage "trigger-edge-before" -Command "trigger-edge" -Options @("--query")
                    try {
                        Assert-ReadbackEqual 1 (Get-Readback $before "source_channel") "trigger-edge" "source_channel"
                        Assert-ReadbackEqual 1.0 (Get-Readback $before "level_volts") "trigger-edge" "level_volts"
                        Assert-ReadbackEqual "positive" (Get-Readback $before "slope") "trigger-edge" "slope"
                        Invoke-SameValueCase "trigger-edge" "trigger-edge" $before @(
                            "--source-channel", "1", "--level", "1", "--slope", "positive"
                        ) @("source_channel", "level_volts", "slope")
                    } catch { Add-Case "trigger-edge" "FAIL" $_.Exception.Message }
                }
            }
            "strict" {
                if ($name -eq "channel-scale") {
                    Invoke-RoundTrip "channel-scale" "channel-scale" @("--channel", "1") "volts_per_division" "--volts-per-division"
                } else {
                    $before = Invoke-Cli -Stage "trigger-edge-before" -Command "trigger-edge" -Options @("--query")
                    try {
                        Invoke-SameValueCase "trigger-edge" "trigger-edge" $before @(
                            "--source-channel", "1", "--level", "1", "--slope", "positive"
                        ) @("source_channel", "level_volts", "slope")
                    } catch { Add-Case "trigger-edge" "FAIL" $_.Exception.Message }
                }
            }
            "pulse" {
                Invoke-SpecialTriggerCase "trigger-pulse-width" @(
                    "--channel", "1", "--polarity", "positive", "--qualifier", "greater-than",
                    "--time-seconds", "0.000001", "--level-volts", "1"
                ) @{ mode = "glitch"; channel = 1; polarity = "positive"; qualifier = "greater-than";
                     greater_than_seconds = 1e-6; level_volts = 1.0 }
            }
            default { throw "Unsupported contract kind: $($scenario.kind)" }
        }
    } catch {
        Add-Case $name "FAIL" $_.Exception.Message
    }
    if (-not $script:CaseResults.Contains($name)) {
        throw "Scenario did not execute its contract: $($scenario.id)"
    }
    $case = $script:CaseResults[$name]
    $results.Add([pscustomobject]@{
        id = [string]$scenario.id
        status = [string]$case.Status
        detail = [string]$case.Detail
        stages = @($script:Stages.ToArray())
        calls = @($script:Calls.ToArray())
    })
}
# Output exactly one structured JSON document; diagnostics are exceptions.
ConvertTo-Json -InputObject @($results.ToArray()) -Depth 20 -Compress
