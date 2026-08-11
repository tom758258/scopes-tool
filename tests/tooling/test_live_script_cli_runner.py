from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_SCRIPTS = (
    REPO_ROOT / "scripts" / "live-cli-check.ps1",
    REPO_ROOT / "scripts" / "live-dvm-check.ps1",
    REPO_ROOT / "scripts" / "live-segmented-check.ps1",
)


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize("script_path", LIVE_SCRIPTS, ids=lambda path: path.stem)
def test_invoke_cli_raw_handles_empty_and_nonempty_stderr(
    tmp_path: Path,
    script_path: Path,
) -> None:
    fake_package = tmp_path / "fake_cli" / "scopes_tool_cli"
    fake_package.mkdir(parents=True)
    (fake_package / "__init__.py").write_text("", encoding="utf-8")
    (fake_package / "cli.py").write_text(
        """\
import json
import sys

mode = sys.argv[1]
print(json.dumps({"ok": True, "result": {"mode": mode}}))
if mode == "nonempty-stderr":
    print("known diagnostic", file=sys.stderr)
""",
        encoding="utf-8",
    )

    run_root = tmp_path / script_path.stem
    run_root.mkdir()
    harness_path = tmp_path / f"{script_path.stem}-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [string] $PythonPath,

    [Parameter(Mandatory = $true)]
    [string] $RunRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

$functionAst = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-CliRaw"
    )
}, $true)
if ($null -eq $functionAst) {
    throw "Invoke-CliRaw was not found in ${ScriptPath}."
}

Invoke-Expression $functionAst.Extent.Text

$script:CliInvocationIndex = 0
$script:RunRoot = $RunRoot
$Python = $PythonPath

$empty = Invoke-CliRaw -Stage "empty-stderr" -Arguments @("empty-stderr")
$emptyPath = Join-Path $RunRoot "cli-001-empty-stderr.stderr.txt"

$previousErrorActionPreference = $ErrorActionPreference
# Windows PowerShell promotes native stderr to an error record under Stop.
$ErrorActionPreference = "Continue"
try {
    $nonempty = Invoke-CliRaw -Stage "nonempty-stderr" -Arguments @("nonempty-stderr")
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
$nonemptyPath = Join-Path $RunRoot "cli-002-nonempty-stderr.stderr.txt"

[ordered]@{
    empty_exit_code = $empty.ExitCode
    empty_ok = $empty.Payload.ok
    empty_stderr = $empty.Stderr
    empty_artifact_exists = Test-Path -LiteralPath $emptyPath
    nonempty_exit_code = $nonempty.ExitCode
    nonempty_ok = $nonempty.Payload.ok
    nonempty_stderr = $nonempty.Stderr
    nonempty_artifact_exists = Test-Path -LiteralPath $nonemptyPath
    nonempty_artifact = [string](Get-Content -LiteralPath $nonemptyPath -Raw)
} | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    environment = os.environ.copy()
    python_path = str(fake_package.parent)
    if environment.get("PYTHONPATH"):
        python_path += os.pathsep + environment["PYTHONPATH"]
    environment["PYTHONPATH"] = python_path

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-PythonPath",
            sys.executable,
            "-RunRoot",
            str(run_root),
        ],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["empty_exit_code"] == 0
    assert result["empty_ok"] is True
    assert result["empty_stderr"] == ""
    assert result["empty_artifact_exists"] is False
    assert result["nonempty_exit_code"] == 0
    assert result["nonempty_ok"] is True
    assert "known diagnostic" in result["nonempty_stderr"]
    assert result["nonempty_artifact_exists"] is True
    assert "known diagnostic" in result["nonempty_artifact"]
