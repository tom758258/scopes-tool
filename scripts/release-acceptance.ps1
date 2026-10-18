param(
    [string]$OutputRoot = ".tmp_tests\release_acceptance"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
. (Join-Path $PSScriptRoot "_validation_helpers.ps1")

$outputFull = Get-FullPath -Path $OutputRoot -BaseRoot $RepoRoot
Assert-PathUnderRoot -RootPath (Join-Path $RepoRoot ".tmp_tests") -Path $outputFull `
    -Message "OutputRoot must stay under the repository .tmp_tests directory: {0}"
$ancestor = $outputFull
while ($ancestor) {
    if (Test-Path -LiteralPath $ancestor) {
        if ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Acceptance output cannot traverse links: $ancestor"
        }
    }
    $ancestor = Split-Path -Parent $ancestor
}
$runDir = Join-Path $outputFull ("run-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$steps = @(
    "git-source", "required-tools", "versions", "build-release", "release-layout",
    "wheel-install", "sdist-install", "preflight", "source-unchanged"
) | ForEach-Object {
    [pscustomobject]@{ name = $_; result = "NOT RUN"; exit_code = $null; duration_ms = 0; error = $null }
}
$commands = New-Object System.Collections.Generic.List[object]
$sourceCommit = $null
$Version = $null
$ok = $false
$started = Get-Date
$environmentNames = @("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE", "VIRTUAL_ENV",
    "UV_INTERNAL__PYTHONHOME", "UV_PROJECT_ENVIRONMENT", "UV_CACHE_DIR", "TEMP", "TMP")
$savedEnvironment = @{}
foreach ($name in $environmentNames) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

function Invoke-ReleaseCommand {
    param([string]$Name, [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory = $RepoRoot)
    $result = [pscustomobject](Invoke-CapturedCommand -Name $Name -FilePath $FilePath -Arguments $Arguments `
        -WorkingDirectory $WorkingDirectory -StdOutPath (Join-Path $runDir "$Name.stdout.txt") `
        -StdErrPath (Join-Path $runDir "$Name.stderr.txt"))
    $commands.Add($result)
    $script:stepExitCode = $result.exit_code
    if (-not $result.success) { throw "$Name failed with exit code $($result.exit_code); see captured output." }
    return $result.stdout_text
}

function Invoke-AcceptanceStep {
    param([string]$Name, [scriptblock]$Action)
    $step = $steps | Where-Object { $_.name -eq $Name }
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $script:stepExitCode = $null
    Write-Host "[start] $Name"
    try {
        & $Action
        $step.result = "PASS"
        $step.exit_code = 0
    } catch {
        $step.result = "FAIL"
        $step.exit_code = if ($script:stepExitCode) { $script:stepExitCode } else { 1 }
        $step.error = $_.Exception.Message
        throw
    } finally {
        $timer.Stop()
        $step.duration_ms = $timer.ElapsedMilliseconds
        Write-Host "[$($step.result)] $Name duration=$($step.duration_ms)ms"
    }
}

try {
    Invoke-AcceptanceStep "git-source" {
        $script:sourceCommit = (Invoke-ReleaseCommand "git-head" "git" @("-C", $RepoRoot, "rev-parse", "HEAD")).Trim()
        $status = Invoke-ReleaseCommand "git-clean" "git" @("-C", $RepoRoot, "status", "--porcelain", "--untracked-files=all")
        if (-not $sourceCommit -or -not [string]::IsNullOrWhiteSpace($status)) {
            throw "Release acceptance requires a clean committed HEAD."
        }
    }
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $null, "Process")
    }
    $env:PYTHONNOUSERSITE = "1"
    $env:UV_CACHE_DIR = Join-Path $runDir "uv-cache"
    $env:TEMP = Join-Path $runDir "temp"
    $env:TMP = $env:TEMP
    New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null

    Invoke-AcceptanceStep "required-tools" {
        foreach ($tool in @("git", "uv", "node", "npm.cmd", "powershell.exe")) {
            $null = Get-Command $tool -CommandType Application -ErrorAction Stop
        }
        $probe = @'
import platform, struct, sys
import build, PyInstaller, tkinter
assert sys.platform == 'win32' and platform.machine().lower() in ('amd64', 'x86_64') and struct.calcsize('P') == 8
assert sys.version_info >= (3, 10)
root = tkinter.Tk(); root.withdraw(); root.update(); root.destroy()
print(sys.version)
'@
        $null = Invoke-ReleaseCommand "python-tools" $Python @("-I", "-c", $probe)
        $null = Invoke-ReleaseCommand "node-version" "node" @("-e", "const [a,b]=process.versions.node.split('.').map(Number); if(a<22||(a===22&&b<12))process.exit(1); console.log(process.version)")
        $null = Invoke-ReleaseCommand "npm-version" "cmd.exe" @("/d", "/c", "npm.cmd", "--version")
        $null = Invoke-ReleaseCommand "uv-version" "uv" @("--version")
        $null = Invoke-ReleaseCommand "lock-check" "uv" @("lock", "--check")
    }
    Invoke-AcceptanceStep "versions" {
        $script:Version = Get-PackageVersion -ProjectRoot $RepoRoot
        $desktopPackage = Get-Content -LiteralPath (Join-Path $RepoRoot "desktop\package.json") -Raw | ConvertFrom-Json
        if ([string]::IsNullOrWhiteSpace($Version) -or $desktopPackage.version -cne $Version) {
            throw "Python and Electron versions must match."
        }
    }
    $releaseRoot = Join-Path $runDir "release"
    $versionDir = Join-Path $releaseRoot $Version
    $smoke = Join-Path $PSScriptRoot "ci_packaging_smoke.py"
    Invoke-AcceptanceStep "build-release" {
        $null = Invoke-ReleaseCommand "build" "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "build_release.ps1"), "-ReleaseRoot", $releaseRoot)
    }
    Invoke-AcceptanceStep "release-layout" {
        $null = Invoke-ReleaseCommand "release-smoke" $Python @($smoke, "--release-dir", $versionDir,
            "--expected-version", $Version, "--extract-dir", (Join-Path $runDir "windows"))
    }
    foreach ($kind in @("wheel", "sdist")) {
        Invoke-AcceptanceStep "$kind-install" {
            $venv = Join-Path $runDir "$kind-venv"
            $venvPython = Join-Path $venv "Scripts\python.exe"
            $artifact = if ($kind -eq "wheel") { "scopes_tool-$Version-py3-none-any.whl" } else { "scopes_tool-$Version.tar.gz" }
            $null = Invoke-ReleaseCommand "$kind-venv" $Python @("-m", "venv", $venv)
            $null = Invoke-ReleaseCommand "$kind-install" "uv" @("pip", "install", "--python", $venvPython,
                "--link-mode", "copy", ((Join-Path $versionDir $artifact) + "[webui]")) $runDir
            $null = Invoke-ReleaseCommand "$kind-smoke" $Python @($smoke, "--installed-python", $venvPython,
                "--expected-version", $Version) $runDir
        }
    }
    Invoke-AcceptanceStep "preflight" {
        $null = Invoke-ReleaseCommand "preflight" "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "preflight-cli.ps1"), "-Target", "all", "-Python", $Python,
            "-OutputRoot", (Join-Path $runDir "preflight"))
    }
    Invoke-AcceptanceStep "source-unchanged" {
        $head = (Invoke-ReleaseCommand "final-head" "git" @("-C", $RepoRoot, "rev-parse", "HEAD")).Trim()
        $status = Invoke-ReleaseCommand "final-clean" "git" @("-C", $RepoRoot, "status", "--porcelain", "--untracked-files=all")
        if ($head -cne $sourceCommit -or -not [string]::IsNullOrWhiteSpace($status)) {
            throw "HEAD or source worktree changed during acceptance."
        }
    }
    $ok = $true
} catch {
    Write-Warning $_.Exception.Message
} finally {
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
    }
    $commandRecords = @($commands.ToArray() | Select-Object name, command, arguments, exit_code, duration_ms, success, stdout, stderr)
    $report = [ordered]@{
        schema_version = 1
        kind = "scopes-tool-release-acceptance"
        ok = $ok
        acceptance_mode = "committed-clean-head"
        source_commit = $sourceCommit
        project_version = $Version
        hardware_touched = $false
        duration_ms = [math]::Round(((Get-Date) - $started).TotalMilliseconds)
        steps = @($steps)
        commands = $commandRecords
    }
    Write-JsonReport -LiteralPath (Join-Path $runDir "report.json") -Report $report
    $summary = @("# Scopes Tool Release Acceptance", "", "Result: $(if ($ok) { 'PASS' } else { 'FAIL' })",
        "Source commit: $sourceCommit", "Version: $Version", "Hardware touched: false", "",
        "| Step | Result | Exit code | Duration ms | Failure |", "| --- | --- | --- | --- | --- |")
    foreach ($step in $steps) {
        $summary += "| $($step.name) | $($step.result) | $($step.exit_code) | $($step.duration_ms) | $($step.error) |"
    }
    Write-Utf8NoBomLines -LiteralPath (Join-Path $runDir "summary.md") -Lines $summary
    Write-Host "Acceptance report: $(Join-Path $runDir 'report.json')"
}
if (-not $ok) { exit 1 }
