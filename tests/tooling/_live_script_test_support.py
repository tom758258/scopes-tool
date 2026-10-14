from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


requires_windows = pytest.mark.skipif(
    os.name != "nt", reason="requires Windows PowerShell"
)


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_powershell(body, tmp_path, timeout=180):
    harness = tmp_path / "harness.ps1"
    harness.write_text(
        'Set-StrictMode -Version Latest\n$ErrorActionPreference = "Stop"\n'
        + f". {ps_quote(REPO_ROOT / 'scripts/_validation_helpers.ps1')}\n"
        + body,
        encoding="utf-8",
    )
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=REPO_ROOT, text=True, capture_output=True, check=False, timeout=timeout,
    )


def extract_live_cli_functions_ps(names, script_path=None):
    name_list = ", ".join(ps_quote(name) for name in names)
    return """
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    '@SCRIPT@',
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}
$functionSources = New-Object System.Collections.Generic.List[string]
foreach ($functionName in @(@FUNCS@)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in the live script."
    }
    $functionSources.Add($functionAst.Extent.Text)
}
# Define through a temporary file so function bodies are file-backed, matching
# how production loads them. Invoke-Expression compilation trips a PowerShell
# 5.1 DLR array-binding bug for some bodies.
$functionsFile = Join-Path $env:TEMP (
    'live_cli_extracted_' + [guid]::NewGuid().ToString('N') + '.ps1'
)
[System.IO.File]::WriteAllLines(
    $functionsFile,
    $functionSources.ToArray(),
    [System.Text.UTF8Encoding]::new($false)
)
. $functionsFile
Remove-Item -LiteralPath $functionsFile -Force
""".replace("@SCRIPT@", str(script_path or REPO_ROOT / "scripts/live-cli-check.ps1")).replace("@FUNCS@", name_list)
