param(
    [string]$ReleaseRoot = "release"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
. (Join-Path $PSScriptRoot "_validation_helpers.ps1")

$Version = Get-PackageVersion -ProjectRoot $RepoRoot
if ([string]::IsNullOrWhiteSpace($Version) -or $Version -notmatch '^[0-9][A-Za-z0-9.!+_-]*$') {
    throw "Invalid project version."
}
$desktopPackage = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "desktop\package.json") | ConvertFrom-Json
if ($desktopPackage.version -cne $Version) {
    throw "Desktop version must match project version $Version."
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project Python executable not found: $Python"
}

$releaseRootFull = Get-FullPath -Path $ReleaseRoot -BaseRoot $RepoRoot
Assert-PathUnderRoot -RootPath $RepoRoot -Path $releaseRootFull `
    -Message "ReleaseRoot must stay under the repository: {0}"
# Reject linked ancestors before creating or copying any output.
$staging = Join-Path (Join-Path $RepoRoot ".tmp_tests") ("release-build-" + [guid]::NewGuid().ToString("N"))
foreach ($path in @($releaseRootFull, $staging)) {
    $ancestor = $path
    while ($ancestor) {
        if (Test-Path -LiteralPath $ancestor) {
            if ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Release output cannot traverse links: $ancestor"
            }
        }
        $ancestor = Split-Path -Parent $ancestor
    }
}
$versionDir = Join-Path $releaseRootFull $Version
if (Test-Path -LiteralPath $versionDir) {
    throw "Release directory already exists; choose a fresh ReleaseRoot: $versionDir"
}
New-Item -ItemType Directory -Path $versionDir -Force | Out-Null

try {
    Push-Location $RepoRoot
    try {
        & $Python -m build --outdir $versionDir
        if ($LASTEXITCODE -ne 0) { throw "Python build failed ($LASTEXITCODE)." }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build_desktop.ps1")
        if ($LASTEXITCODE -ne 0) { throw "Desktop build failed ($LASTEXITCODE)." }
    } finally {
        Pop-Location
    }

    $desktopDirectory = Join-Path $RepoRoot "dist\desktop\win-unpacked"
    & $Python (Join-Path $PSScriptRoot "ci_packaging_smoke.py") --mode desktop --layout-only
    if ($LASTEXITCODE -ne 0) { throw "Desktop layout validation failed ($LASTEXITCODE)." }
    $bundleRoot = Join-Path $staging "scopes-tool-$Version"
    New-Item -ItemType Directory -Path $bundleRoot -Force | Out-Null
    foreach ($entry in Get-ChildItem -LiteralPath $desktopDirectory -Force) {
        Copy-Item -LiteralPath $entry.FullName -Destination $bundleRoot -Recurse -Force
    }
    $zipName = "scopes-tool-$Version-windows-x64.zip"
    Compress-Archive -LiteralPath $bundleRoot -DestinationPath (Join-Path $versionDir $zipName) -CompressionLevel Optimal

    $expectedNames = @($zipName, "scopes_tool-$Version-py3-none-any.whl", "scopes_tool-$Version.tar.gz")
    $entries = @(Get-ChildItem -LiteralPath $versionDir -Force)
    if ($entries.Count -ne 3 -or @($entries | Where-Object { $_.PSIsContainer -or $_.Name -cnotin $expectedNames }).Count) {
        throw "Release build must produce exactly the ZIP, wheel, and sdist."
    }
    $checksums = foreach ($name in ($expectedNames | Sort-Object)) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $versionDir $name)).Hash.ToLowerInvariant()
        "$hash  $name"
    }
    Write-Utf8NoBomLines -LiteralPath (Join-Path $versionDir "checksums.txt") -Lines $checksums
    Write-Host "Release artifacts: $versionDir"
} finally {
    Remove-TemporaryValidationPath -Path $staging -AllowedRoot (Join-Path $RepoRoot ".tmp_tests")
}
