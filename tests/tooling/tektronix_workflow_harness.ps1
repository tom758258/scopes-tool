param(
    [string]$ScriptPath,
    [string]$Target = 'tektronix-tbs2074',
    [string]$Scenario,
    [string]$PythonPath,
    [string]$OutputRoot,
    [switch]$MinimalArtifacts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $ScriptPath
$source = [IO.File]::ReadAllText($ScriptPath)
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput(
    $source, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count) { throw "Failed to parse workflow live script: $($parseErrors[0].Message)" }

$liveArguments = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left.Extent.Text -eq '$script:LiveConnectionArguments'
}, $true)
if ($null -eq $liveArguments) { throw "Live connection argument assignment was not found" }
$replacements = New-Object System.Collections.Generic.List[object]
$replacements.Add(@{
    Start = $liveArguments.Right.Extent.StartOffset
    Length = $liveArguments.Right.Extent.EndOffset - $liveArguments.Right.Extent.StartOffset
    Text = '@("--simulate", "--model", $script:Target)'
})

$modeCli = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Invoke-ModeCli'
}, $true)
if ($null -eq $modeCli) { throw "Invoke-ModeCli was not found" }
$payloadAssignment = $modeCli.Find({
    param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left.Extent.Text -eq '$payload' -and
        $node.Right.Extent.Text -like 'Invoke-Cli*'
}, $true)
if ($null -eq $payloadAssignment) { throw "Invoke-ModeCli payload assignment was not found" }
$runMutation = switch ($Scenario) {
    'dirty-run' {
        "`n    if (`$Command -eq 'run' -and `$ModeArguments -notcontains '--dry-run') { `$payload.result.post_command_status.value = 4; `$payload.result.post_command_status.raw = '4' }"
    }
    'focused-dirty-case' {
        "`n    if (`$Stage -eq 'measure-sweep') { `$payload.result.post_command_status.value = 4; `$payload.result.post_command_status.raw = '4' }"
    }
    default { '' }
}
if ($runMutation) {
    $replacements.Add(@{
        Start = $payloadAssignment.Extent.EndOffset
        Length = 0
        Text = $runMutation
    })
}

if ($Scenario.StartsWith('focused-')) {
    # Limit these checks to one workflow while retaining the runner's gates,
    # native checkpoints, cleanup, final check, and report generation.
    $preflight = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq 'Invoke-HardwareFreePreflight'
    }, $true)
    $cases = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.IfStatementAst] -and
            $node.Clauses[0].Item1.Extent.Text -eq '-not $script:FunctionalFailed'
    }, $true))
    if ($null -eq $preflight -or $cases.Count -eq 0 -or
        -not $cases[0].Extent.Text.Contains('Invoke-WorkflowCase -Name "measure-sweep"')) {
        throw 'Focused workflow boundary was not found'
    }
    $replacements.Add(@{
        Start = $preflight.Extent.StartOffset
        Length = $preflight.Extent.EndOffset - $preflight.Extent.StartOffset
        Text = @'
function Invoke-HardwareFreePreflight {
    Invoke-ModeCli -Stage 'preflight-identify' -Command 'identify' -ModeArguments @('--simulate', '--model', $script:Target) | Out-Null
}
'@
    })
    foreach ($case in @($cases | Select-Object -Skip 1)) {
        $replacements.Add(@{
            Start = $case.Extent.StartOffset
            Length = $case.Extent.EndOffset - $case.Extent.StartOffset
            Text = ''
        })
    }
    $invokeCli = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-Cli'
    }, $true)
    $invocationAssignment = $invokeCli.Find({
        param($node)
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
            $node.Left.Extent.Text -eq '$invocation' -and $node.Right.Extent.Text -like 'Invoke-CliRaw*'
    }, $true)
    if ($null -eq $invocationAssignment) { throw 'Focused invocation boundary was not found' }
    $mutation = @'
    if ($Stage -eq 'identity' -and $Scenario -eq 'focused-model-mismatch') {
        $invocation.Payload.idn.model = 'TDS2024B'
    }
    if ($Stage -eq 'pre-run-standard-event' -and $Scenario -eq 'focused-stale') {
        $invocation.Payload.result.value = 4
        $invocation.Payload.result.raw = '4'
    }
    if (($Stage -eq 'pre-run-standard-event-verify' -and $Scenario -eq 'focused-post-event') -or
        ($Stage -eq 'final-standard-event' -and $Scenario -in @('focused-final-event', 'focused-case-and-final-fail'))) {
        $invocation.Payload.result.value = 4
        $invocation.Payload.result.raw = '4'
    }
    if ($Stage -in @('pre-run-standard-event-verify', 'final-standard-event') -and $Scenario -eq 'focused-nonerror-events') {
        $invocation.Payload.result.value = 65
        $invocation.Payload.result.raw = '65'
    }
    if ($Stage -eq 'final-standard-event' -and $Scenario -eq 'focused-final-missing') {
        $invocation.Payload.result.PSObject.Properties.Remove('value')
    }
    $failedStage = switch ($Scenario) {
        'focused-identify-io' { 'identity' }
        'focused-query-io' { 'pre-run-standard-event' }
        'focused-clear-io' { 'pre-run-clear-status' }
        'focused-verify-io' { 'pre-run-standard-event-verify' }
        'focused-final-io' { 'final-standard-event' }
        'focused-cleanup-fail' { 'cleanup-acquisition-stop-acquisition' }
        'focused-case-fail' { 'measure-sweep' }
        'focused-case-and-final-fail' { 'measure-sweep' }
        default { '' }
    }
    if ($Stage -eq $failedStage) {
        $invocation.ExitCode = 1
        $invocation.Payload.ok = $false
        $invocation.Payload | Add-Member -Force -NotePropertyName error -NotePropertyValue ([pscustomobject]@{
            type = 'VisaIOError'; message = "Injected failure at $Stage"
        })
        $lastInvocation = $script:Invocations[$script:Invocations.Count - 1]
        $lastInvocation.exit_code = 1
        $lastInvocation.success = $false
    }
'@
    $replacements.Add(@{
        Start = $invocationAssignment.Extent.EndOffset
        Length = 0
        Text = "`n$mutation"
    })
}

if ($Scenario -eq 'measurement-settings-conflict') {
    $invokeCli = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq 'Invoke-Cli'
    }, $true)
    if ($null -eq $invokeCli) { throw "Invoke-Cli was not found" }
    $invocationAssignment = $invokeCli.Find({
        param($node)
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
            $node.Left.Extent.Text -eq '$invocation' -and
            $node.Right.Extent.Text -like 'Invoke-CliRaw*'
    }, $true)
    if ($null -eq $invocationAssignment) { throw "Invoke-Cli invocation assignment was not found" }
    $measurementMutation = @'
    if ($Stage -eq 'measure-sweep') {
        $invocation.ExitCode = 1
        $invocation.Payload.ok = $false
        $status = $invocation.Payload.result.post_command_status
        $status.value = 16
        $status.raw = '16'
        $status.event_raw = '221,"Settings conflict; "'
        $status.events = @([pscustomobject]@{
            code = 221
            message = 'Settings conflict; '
            category = 'error'
        })
        $status.is_error = $true
        $lastInvocation = $script:Invocations[$script:Invocations.Count - 1]
        $lastInvocation.exit_code = 1
        $lastInvocation.success = $false
    }
'@
    $replacements.Add(@{
        Start = $invocationAssignment.Extent.EndOffset
        Length = 0
        Text = "`n$measurementMutation"
    })
}

if ($Scenario -eq 'dirty-timeout') {
    $timeoutAssignment = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
            $node.Left.Extent.Text -eq '$invocation' -and
            $node.Extent.Text -match 'measure-until-timeout'
    }, $true)
    if ($null -eq $timeoutAssignment) { throw "Expected-timeout invocation was not found" }
    $replacements.Add(@{
        Start = $timeoutAssignment.Extent.EndOffset
        Length = 0
        Text = "`n        `$invocation.Payload.result.post_command_status.value = 4; `$invocation.Payload.result.post_command_status.raw = '4'"
    })
}

foreach ($replacement in @($replacements | Sort-Object { [int]$_.Start } -Descending)) {
    $source = $source.Remove($replacement.Start, $replacement.Length).Insert(
        $replacement.Start, $replacement.Text
    )
}
$source = $source.Replace('$PSScriptRoot', "'$scriptDirectory'")

function Read-Host {
    switch ($Scenario) {
        'focused-confirmation-unavailable' { throw 'Operator console unavailable.' }
        'focused-confirmation-n' { return 'N' }
        'focused-confirmation-no' { return 'No' }
        'focused-confirmation-text' { return 'ready' }
        'focused-confirmation-space' { return ' ' }
        'focused-confirmation-null' { return $null }
        default { return '' }
    }
}
$workflow = [scriptblock]::Create($source)
& $workflow `
    -Target $Target `
    -Connection 'usb' `
    -Resource 'USB0::FAKE::INSTR' `
    -Python $PythonPath `
    -OutputRoot $OutputRoot -DebugArtifacts:(-not $MinimalArtifacts)
