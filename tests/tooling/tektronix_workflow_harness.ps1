param(
    [string]$ScriptPath,
    [string]$Target = 'tektronix-tbs2074',
    [string]$Scenario,
    [string]$PythonPath,
    [string]$OutputRoot
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
    default { '' }
}
if ($runMutation) {
    $replacements.Add(@{
        Start = $payloadAssignment.Extent.EndOffset
        Length = 0
        Text = $runMutation
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

foreach ($replacement in @($replacements | Sort-Object Start -Descending)) {
    $source = $source.Remove($replacement.Start, $replacement.Length).Insert(
        $replacement.Start, $replacement.Text
    )
}
$source = $source.Replace('$PSScriptRoot', "'$scriptDirectory'")

function Read-Host { return '' }
$workflow = [scriptblock]::Create($source)
& $workflow `
    -Target $Target `
    -Connection 'usb' `
    -Resource 'USB0::FAKE::INSTR' `
    -Python $PythonPath `
    -OutputRoot $OutputRoot
