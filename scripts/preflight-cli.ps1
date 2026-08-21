[CmdletBinding()]
param(
    [string]$Target = "all",

    [switch]$ListTargets,

    [string]$Python = ".\.venv\Scripts\python.exe",

    [string]$OutputRoot = ".tmp_tests\cli_preflight"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$TmpRoot = Join-Path $RepoRoot ".tmp_tests"
. (Join-Path $PSScriptRoot "_validation_helpers.ps1")
. (Join-Path $PSScriptRoot "_artifact_privacy.ps1")

function Write-UsageError {
    param([Parameter(Mandatory = $true)][string]$Message)
    [Console]::Error.WriteLine("[preflight][cli] ${Message}")
    exit 2
}

function ConvertTo-RepoRelativePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $root = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd('\', '/')
    $full = [System.IO.Path]::GetFullPath($Path)
    if ($full.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $full.Substring($root.Length + 1)
    }
    return $full
}

function Get-JsonField {
    param(
        [AllowNull()]$Object,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $value = $Object
    foreach ($part in $Path.Split('.')) {
        if ($null -eq $value) { return $null }
        $property = $value.PSObject.Properties[$part]
        if ($null -eq $property) { return $null }
        $value = $property.Value
    }
    return $value
}

$script:PreflightCases = New-Object System.Collections.Generic.List[object]
$script:RunLayout = $null
$script:PythonExecutable = ""

function Add-PreflightCaseRecord {
    param([Parameter(Mandatory = $true)]$Record)

    $script:PreflightCases.Add($Record) | Out-Null
    $status = if ($Record.passed) { "PASS" } else { "FAIL" }
    Write-CaseStatus -Status $status -Context "[preflight][cli]" `
        -Name "$($Record.target)/$($Record.name)" `
        -FailureReasons @($Record.failure_reasons)
}

function New-PreflightCaseRecord {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Target,
        [AllowNull()]$Invocation,
        [AllowEmptyCollection()][string[]]$FailureReasons = @(),
        [hashtable]$ExtraArtifacts = @{}
    )

    $artifacts = [ordered]@{}
    if ($null -ne $Invocation) {
        foreach ($pair in @(
                @("stdout", [string]$Invocation["stdout"]),
                @("stderr", [string]$Invocation["stderr"]),
                @("json", [string]$Invocation["json"])
            )) {
            if (-not [string]::IsNullOrWhiteSpace($pair[1]) -and (Test-Path -LiteralPath $pair[1] -PathType Leaf)) {
                $artifacts[$pair[0]] = ConvertTo-RepoRelativePath -Path $pair[1]
            }
        }
    }
    foreach ($key in $ExtraArtifacts.Keys) {
        $value = [string]$ExtraArtifacts[$key]
        if (-not [string]::IsNullOrWhiteSpace($value) -and (Test-Path -LiteralPath $value -PathType Leaf)) {
            $artifacts[$key] = ConvertTo-RepoRelativePath -Path $value
        }
    }

    $exitCode = $null
    $durationMs = $null
    $commandText = $null
    $arguments = @()
    if ($null -ne $Invocation) {
        $exitCode = $Invocation["exit_code"]
        $durationMs = $Invocation["duration_ms"]
        $commandText = $Invocation["command"]
        $arguments = @($Invocation["arguments"])
    }

    return [pscustomobject]@{
        name = $Name
        target = $Target
        command = $commandText
        arguments = $arguments
        exit_code = $exitCode
        duration_ms = $durationMs
        passed = (@($FailureReasons).Count -eq 0)
        failure_reasons = @($FailureReasons)
        artifacts = $artifacts
    }
}

function Invoke-PreflightCliCase {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$StdOutPath,
        [Parameter(Mandatory = $true)][string]$StdErrPath,
        [string]$JsonPath = "",
        [scriptblock]$Validate,
        [scriptblock]$PostCheck
    )

    $invocation = Invoke-CapturedCommand `
        -Name $Name `
        -FilePath $script:PythonExecutable `
        -Arguments $Arguments `
        -StdOutPath $StdOutPath `
        -StdErrPath $StdErrPath `
        -JsonPath $JsonPath `
        -WorkingDirectory $RepoRoot

    $failures = [System.Collections.Generic.List[string]]::new()
    if (-not $invocation["success"]) {
        $failures.Add("exit code $($invocation['exit_code'])") | Out-Null
    }

    $payload = $null
    if (-not [string]::IsNullOrWhiteSpace($JsonPath)) {
        $jsonArtifact = [string]$invocation["json"]
        if (-not [string]::IsNullOrWhiteSpace($jsonArtifact) -and
            (Test-Path -LiteralPath $jsonArtifact -PathType Leaf)) {
            $payload = Get-Content -LiteralPath $jsonArtifact -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
        }
        if ($null -eq $payload) {
            $failures.Add("stdout did not contain valid CLI JSON") | Out-Null
        } elseif ((Get-JsonField -Object $payload -Path "ok") -ne $true) {
            $failures.Add("CLI envelope ok was not true") | Out-Null
        }
    }

    if ($null -ne $Validate -and $null -ne $payload) {
        & $Validate $payload $failures
    }
    if ($null -ne $PostCheck) {
        & $PostCheck $invocation $failures
    }

    Add-PreflightCaseRecord -Record (New-PreflightCaseRecord `
        -Name $Name -Target $Target -Invocation $invocation `
        -FailureReasons @($failures.ToArray()))
    return $invocation
}

if ($ListTargets) {
    Get-SupportedTargetModelIds | ForEach-Object { Write-Host $_ }
    exit 0
}

$pythonPath = Get-FullPath -Path $Python -BaseRoot $RepoRoot
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    Write-UsageError "Python executable not found: ${pythonPath}"
}

try {
    $targets = @(Resolve-ValidationTargets -Target $Target)
} catch {
    Write-UsageError $_.Exception.Message
}

$outputBase = Get-FullPath -Path $OutputRoot -BaseRoot $RepoRoot
try {
    Assert-PathUnderRoot `
        -RootPath $TmpRoot `
        -Path $outputBase `
        -Message "Preflight output must stay under repository .tmp_tests: {0}"
} catch {
    Write-UsageError $_.Exception.Message
}

$script:RunLayout = New-ValidationRunDirectory -BaseRoot $outputBase
$runRoot = $script:RunLayout.Root
$privateRoot = $script:RunLayout.Private
$shareableRoot = $script:RunLayout.Shareable
$script:PythonExecutable = $pythonPath

Write-Host "[preflight][cli] target(s): $($targets -join ', ')"
Write-Host "[preflight][cli] artifacts: $(ConvertTo-RepoRelativePath -Path $runRoot)"

foreach ($target in $targets) {
    $targetDir = Join-Path $privateRoot $target
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

    # Case 1: acquisition dry-run plans the full acquisition-check sequence
    # without opening a VISA backend (existing preflight-acquisition coverage).
    $dryOutDir = Join-Path $targetDir "acquisition-dry-run"
    $dryArgs = @(
        "-m", "scopes_tool_cli.cli", "acquisition-check",
        "--dry-run", "--json", "--model", $target, "--output-dir", $dryOutDir
    )
    $dryInvocation = Invoke-PreflightCliCase `
        -Name "acquisition-dry-run" `
        -Target $target `
        -Arguments $dryArgs `
        -StdOutPath (Join-Path $targetDir "acquisition-dry-run.stdout.txt") `
        -StdErrPath (Join-Path $targetDir "acquisition-dry-run.stderr.txt") `
        -JsonPath (Join-Path $targetDir "acquisition-dry-run.json") `
        -Validate {
            param($Payload, [System.Collections.Generic.List[string]]$Failures)
            $mode = Get-JsonField -Object $Payload -Path "mode"
            if ([string]$mode -ne "dry_run") {
                $Failures.Add("expected mode dry_run, got '${mode}'") | Out-Null
            }
            $status = Get-JsonField -Object $Payload -Path "result.status"
            if ([string]$status -ne "planned") {
                $Failures.Add("expected planned dry-run status, got '${status}'") | Out-Null
            }
            $planned = @(Get-JsonField -Object $Payload -Path "scpi.planned")
            if ($planned.Count -eq 0) {
                $Failures.Add("dry-run planned SCPI sequence is empty") | Out-Null
            }
        }

    # Case 2: acquisition simulate executes the same sequence against the
    # built-in simulator and writes the hardware report artifacts.
    $simOutDir = Join-Path $targetDir "acquisition-simulate"
    $simArgs = @(
        "-m", "scopes_tool_cli.cli", "acquisition-check",
        "--simulate", "--json", "--model", $target, "--output-dir", $simOutDir
    )
    $simInvocation = Invoke-PreflightCliCase `
        -Name "acquisition-simulate" `
        -Target $target `
        -Arguments $simArgs `
        -StdOutPath (Join-Path $targetDir "acquisition-simulate.stdout.txt") `
        -StdErrPath (Join-Path $targetDir "acquisition-simulate.stderr.txt") `
        -JsonPath (Join-Path $targetDir "acquisition-simulate.json") `
        -Validate {
            param($Payload, [System.Collections.Generic.List[string]]$Failures)
            $mode = Get-JsonField -Object $Payload -Path "mode"
            if ([string]$mode -ne "simulate") {
                $Failures.Add("expected mode simulate, got '${mode}'") | Out-Null
            }
            $status = Get-JsonField -Object $Payload -Path "result.status"
            if ([string]$status -ne "completed") {
                $Failures.Add("expected completed acquisition-check status, got '${status}'") | Out-Null
            }
            $reportPath = Get-JsonField -Object $Payload -Path "result.report_path"
            if ([string]::IsNullOrWhiteSpace([string]$reportPath)) {
                $Failures.Add("acquisition-check did not report a report_path") | Out-Null
            } elseif (-not (Test-Path -LiteralPath ([string]$reportPath) -PathType Leaf)) {
                $Failures.Add("reported report_path does not exist: ${reportPath}") | Out-Null
            }
        }

    # Case 3: hardware-report renders the simulated acquisition report to a
    # markdown summary (existing preflight-acquisition summary coverage).
    $simReportPath = ""
    $simJsonArtifact = [string]$simInvocation["json"]
    if (-not [string]::IsNullOrWhiteSpace($simJsonArtifact) -and
        (Test-Path -LiteralPath $simJsonArtifact -PathType Leaf)) {
        $simPayload = Get-Content -LiteralPath $simJsonArtifact -Raw | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($null -ne $simPayload) {
            $simReportPath = [string](Get-JsonField -Object $simPayload -Path "result.report_path")
        }
    }
    if ([string]::IsNullOrWhiteSpace($simReportPath) -or -not (Test-Path -LiteralPath $simReportPath -PathType Leaf)) {
        $record = New-PreflightCaseRecord `
            -Name "hardware-report-render" -Target $target -Invocation $null `
            -FailureReasons @("skipped: acquisition-simulate did not produce a report") `
            -ExtraArtifacts @{}
        Add-PreflightCaseRecord -Record $record
    } else {
        $renderSummaryPath = Join-Path $targetDir "hardware-report-render.summary.md"
        $renderArgs = @(
            "-m", "scopes_tool_cli.cli", "hardware-report", $simReportPath
        )
        $null = Invoke-PreflightCliCase `
            -Name "hardware-report-render" `
            -Target $target `
            -Arguments $renderArgs `
            -StdOutPath $renderSummaryPath `
            -StdErrPath (Join-Path $targetDir "hardware-report-render.stderr.txt") `
            -PostCheck {
                param($Invocation, [System.Collections.Generic.List[string]]$Failures)
                # hardware-report writes markdown to stdout (not JSON).
                $summaryPath = [string]$Invocation["stdout"]
                if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf) -or
                    (Get-Item -LiteralPath $summaryPath).Length -le 0) {
                    $Failures.Add("rendered markdown summary is missing or empty") | Out-Null
                }
            }
    }
}

$cases = @($script:PreflightCases.ToArray())
$failed = @($cases | Where-Object { -not $_.passed })
$report = [ordered]@{
    schema_version = 1
    kind = "scopes-tool-cli-preflight"
    status = if ($failed.Count -eq 0) { "passed" } else { "failed" }
    target = $Target
    targets = @($targets)
    package_version = Get-PackageVersion -ProjectRoot $RepoRoot
    git_head = Get-GitHead -ProjectRoot $RepoRoot
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    validation_mode = "no-hardware-cli-preflight"
    hardware_touched = $false
    run_root = ConvertTo-RepoRelativePath -Path $runRoot
    artifact_paths = [ordered]@{
        output_dir = ConvertTo-RepoRelativePath -Path $runRoot
        report = ConvertTo-RepoRelativePath -Path (Join-Path $privateRoot "report.json")
        summary = ConvertTo-RepoRelativePath -Path (Join-Path $privateRoot "summary.md")
    }
    summary_counts = [ordered]@{
        targets = @($targets).Count
        cases = $cases.Count
        passed = $cases.Count - $failed.Count
        failed = $failed.Count
    }
    cases = $cases
}
$privateReportPath = Join-Path $privateRoot "report.json"
Write-JsonReport -LiteralPath $privateReportPath -Report $report

$summaryLines = @(
    "# Scopes Tool CLI Preflight Summary",
    "",
    "- Status: $($report.status)",
    "- Targets: $($targets -join ', ')",
    "- Package version: $($report.package_version)",
    "- Git HEAD: $($report.git_head)",
    "- Generated at: $($report.generated_at)",
    "- Validation mode: no-hardware-cli-preflight",
    "- Hardware touched: false",
    "- Artifacts: $($report.run_root)",
    "",
    "| Target | Case | Exit | Duration (ms) | Result |",
    "|---|---|---:|---:|---|"
)
foreach ($case in $cases) {
    $status = if ($case.passed) { "PASS" } else { "FAIL" }
    $summaryLines += "| $($case.target) | ``$($case.name)`` | $($case.exit_code) | $($case.duration_ms) | ${status} |"
    foreach ($reason in @($case.failure_reasons)) {
        $summaryLines += "  - Failure: ${reason}"
    }
}
$privateSummaryPath = Join-Path $privateRoot "summary.md"
Write-Utf8NoBomLines -LiteralPath $privateSummaryPath -Lines $summaryLines

try {
    $null = New-ShareableArtifactSet `
        -PrivateReport $report `
        -PrivateSummaryPath $privateSummaryPath `
        -RunRoot $runRoot `
        -PrivateRoot $privateRoot `
        -ShareableRoot $shareableRoot `
        -RepoRoot $RepoRoot
} catch {
    Write-Host "[preflight][cli] shareable artifact generation failed: $($_.Exception.Message)"
    Write-Host "[preflight][cli] private artifacts retained: $(ConvertTo-RepoRelativePath -Path $privateRoot)"
}

Write-Host "[preflight][cli] $($report.status): $($failed.Count) of $($cases.Count) cases failed"
Write-Host "[preflight][cli] report: $($report.artifact_paths.report)"
if ($failed.Count -gt 0) {
    exit 1
}
exit 0
