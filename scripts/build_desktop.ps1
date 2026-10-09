Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$DesktopRoot = Join-Path $RepoRoot "desktop"
$SharedBundle = Join-Path $RepoRoot "dist\scopes-tool"
$DesktopDist = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "dist\desktop"))
$DesktopDirectory = Join-Path $DesktopDist "win-unpacked"

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build_windows_bundle.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$RepoPrefix = $RepoRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not $DesktopDist.StartsWith($RepoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Desktop build path must stay under the repository: $DesktopDist"
}
if (Test-Path -LiteralPath $DesktopDist) {
    Remove-Item -LiteralPath $DesktopDist -Recurse -Force
}
$Npm = (Get-Command "npm.cmd" -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
Push-Location $DesktopRoot
try {
    & $Npm ci
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Npm run check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Npm run dist:win
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $DesktopDirectory -PathType Container)) {
    throw "Electron directory build did not produce: $DesktopDirectory"
}
foreach ($entry in Get-ChildItem -LiteralPath $SharedBundle -Force) {
    Copy-Item -LiteralPath $entry.FullName -Destination $DesktopDirectory -Recurse -Force
}
foreach ($name in @("Scopes Tool.exe", "scopes-tool.exe", "scopes-tool-webui-launcher.exe", "scopes-tool-webui-host.exe", "resources\app.asar")) {
    if (-not (Test-Path -LiteralPath (Join-Path $DesktopDirectory $name) -PathType Leaf)) {
        throw "Desktop directory is missing required file: $name"
    }
}
$InternalRoot = Join-Path $DesktopDirectory "_internal"
$InternalDirectories = @(Get-ChildItem -LiteralPath $DesktopDirectory -Directory -Recurse -Force | Where-Object { $_.Name -eq "_internal" })
if ($InternalDirectories.Count -ne 1 -or -not $InternalDirectories[0].FullName.Equals($InternalRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Desktop must share exactly one _internal at the application root."
}
if (Test-Path -LiteralPath (Join-Path $DesktopDirectory "resources\backend")) {
    throw "Desktop must not contain resources\backend."
}
$PythonLibraries = @(Get-ChildItem -LiteralPath $DesktopDirectory -Filter "python*.dll" -File -Recurse)
if ($PythonLibraries.Count -eq 0 -or @($PythonLibraries | Where-Object { $_.DirectoryName -ne $InternalRoot }).Count -ne 0) {
    throw "Python runtime libraries must exist only in the shared _internal."
}
if (@(Get-ChildItem -LiteralPath $DesktopDist -Filter "*portable*.exe" -File -Recurse).Count -ne 0) {
    throw "Desktop directory build must not produce a portable executable."
}
foreach ($asset in Get-ChildItem -LiteralPath (Join-Path $RepoRoot "src\scopes_tool_webui\static") -File) {
    if (-not (Test-Path -LiteralPath (Join-Path $InternalRoot "scopes_tool_webui\static\$($asset.Name)") -PathType Leaf)) {
        throw "Missing WebUI static asset: $($asset.Name)"
    }
}
foreach ($distribution in @("scopes_tool", "pyvisa", "fastapi", "uvicorn", "starlette", "pydantic", "anyio")) {
    $MetadataDirectories = @(Get-ChildItem -LiteralPath $InternalRoot -Directory -Filter "$distribution-*.dist-info")
    if ($MetadataDirectories.Count -ne 1 -or -not (Test-Path -LiteralPath (Join-Path $MetadataDirectories[0].FullName "METADATA") -PathType Leaf)) {
        throw "Missing or duplicate package metadata: $distribution"
    }
}
Write-Host "Desktop directory validated: $DesktopDirectory"
