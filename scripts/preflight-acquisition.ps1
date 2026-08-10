[CmdletBinding()]
param(
    [ValidateSet("DSOX4024A", "DSOX4034A", "DSOX3024A", "DSOX2004A")]
    [string[]] $Model = @("DSOX4024A", "DSOX4034A", "DSOX3024A", "DSOX2004A"),

    [string] $Python = ".\.venv\Scripts\python.exe",

    [string] $OutputRoot = ".tmp_tests\acquisition_preflight"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$modelIds = @{
    "DSOX4024A" = "keysight-dsox4024a"
    "DSOX4034A" = "keysight-dsox4034a"
    "DSOX3024A" = "keysight-dsox3024a"
    "DSOX2004A" = "keysight-dsox2004a"
}

function Invoke-Cli {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $output = & $Python -m scopes_tool_cli.cli @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Python -m scopes_tool_cli.cli $($Arguments -join ' ')"
    }
    try {
        $payload = $output | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "Command did not return JSON: $Python -m scopes_tool_cli.cli $($Arguments -join ' ')"
    }
    if (-not $payload.ok) {
        throw "Command JSON reported ok=false: $Python -m scopes_tool_cli.cli $($Arguments -join ' ')"
    }
    return $payload
}

function Remove-ModelOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Root,

        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    New-Item -ItemType Directory -Path $Root -Force | Out-Null
    $rootPath = (Resolve-Path -LiteralPath $Root).Path

    if (Test-Path -LiteralPath $Path) {
        $targetPath = (Resolve-Path -LiteralPath $Path).Path
        if (-not $targetPath.StartsWith($rootPath + [System.IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to remove output outside ${rootPath}: ${targetPath}"
        }
        Remove-Item -LiteralPath $targetPath -Recurse -Force
    }
}

if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    throw "Python executable not found: ${Python}"
}

foreach ($targetModel in $Model) {
    $modelId = $modelIds[$targetModel]
    $outputDir = Join-Path $OutputRoot $targetModel
    $reportPath = Join-Path $outputDir "report.json"
    $summaryPath = Join-Path $outputDir "summary.md"

    Write-Host "== Acquisition preflight: ${targetModel} =="
    Write-Host "Dry-run: no VISA backend will be opened."
    $dry = Invoke-Cli -Arguments @(
        "acquisition-check",
        "--dry-run",
        "--json",
        "--model",
        $modelId,
        "--output-dir",
        $outputDir
    )
    if ($dry.mode -ne "dry_run") {
        throw "Expected dry_run mode for ${targetModel}."
    }

    Remove-ModelOutput -Root $OutputRoot -Path $outputDir

    Write-Host "Simulate: writing ${outputDir}"
    $sim = Invoke-Cli -Arguments @(
        "acquisition-check",
        "--simulate",
        "--json",
        "--model",
        $modelId,
        "--output-dir",
        $outputDir
    )
    if ($sim.result.status -ne "completed") {
        throw "Simulated acquisition-check did not complete for ${targetModel}: $($sim.result.status)"
    }

    if (-not (Test-Path -LiteralPath $reportPath)) {
        throw "Expected report was not created: ${reportPath}"
    }
    if ($sim.result.report_path -and -not (Test-Path -LiteralPath $sim.result.report_path)) {
        throw "Reported report_path does not exist: $($sim.result.report_path)"
    }

    Write-Host "Rendering summary: ${summaryPath}"
    $summary = & $Python -m scopes_tool_cli.cli hardware-report $reportPath
    if ($LASTEXITCODE -ne 0) {
        throw "hardware-report failed for ${reportPath}"
    }
    $summary | Set-Content -LiteralPath $summaryPath -Encoding UTF8

    Write-Host "Preflight passed: ${targetModel}"
}
