Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$DistRoot = Join-Path $RepoRoot "dist"
$BundlePath = [System.IO.Path]::GetFullPath((Join-Path $DistRoot "scopes-tool"))
$WorkPath = Join-Path $RepoRoot "build\pyinstaller-windows"
$SpecPath = Join-Path $PSScriptRoot "scopes-tool-windows.spec"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project Python executable not found: $Python"
}
& $Python -c "import sys, platform, struct; sys.exit(0 if sys.platform == 'win32' and platform.machine().lower() in ('amd64', 'x86_64') and struct.calcsize('P') == 8 else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Windows onedir build requires Windows x64 Python."
}
& $Python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is required; run uv sync --all-extras --locked --link-mode=copy."
}
$TkProbe = @'
import tkinter as tk
root = tk.Tk()
root.withdraw()
root.update()
root.destroy()
'@
& $Python -c $TkProbe
if ($LASTEXITCODE -ne 0) {
    throw "The WebUI Launcher requires a working Tkinter / Tcl/Tk runtime."
}

$RepoPrefix = $RepoRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not $BundlePath.StartsWith($RepoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Bundle path must stay under the repository: $BundlePath"
}
if (Test-Path -LiteralPath $BundlePath) {
    Remove-Item -LiteralPath $BundlePath -Recurse -Force
}
& $Python -m PyInstaller --noconfirm --clean --distpath $DistRoot --workpath $WorkPath $SpecPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
Write-Host "Windows onedir bundle: $BundlePath"
