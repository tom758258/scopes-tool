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
def test_invoke_cli_raw_preserves_native_process_results(
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
if mode in {"nonempty-stderr", "failure-stderr"}:
    print(f"known diagnostic: {mode}", file=sys.stderr)
if mode == "failure-stderr":
    sys.exit(7)
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
$emptyPreference = [string]$ErrorActionPreference

$nonempty = Invoke-CliRaw -Stage "nonempty-stderr" -Arguments @("nonempty-stderr")
$nonemptyPath = Join-Path $RunRoot "cli-002-nonempty-stderr.stderr.txt"
$nonemptyPreference = [string]$ErrorActionPreference

$failure = Invoke-CliRaw -Stage "failure-stderr" -Arguments @("failure-stderr")
$failurePath = Join-Path $RunRoot "cli-003-failure-stderr.stderr.txt"
$failurePreference = [string]$ErrorActionPreference

[ordered]@{
    empty_exit_code = $empty.ExitCode
    empty_ok = $empty.Payload.ok
    empty_stderr = $empty.Stderr
    empty_artifact_exists = Test-Path -LiteralPath $emptyPath
    empty_preference = $emptyPreference
    nonempty_exit_code = $nonempty.ExitCode
    nonempty_ok = $nonempty.Payload.ok
    nonempty_stderr = $nonempty.Stderr
    nonempty_artifact_exists = Test-Path -LiteralPath $nonemptyPath
    nonempty_artifact = [string](Get-Content -LiteralPath $nonemptyPath -Raw)
    nonempty_preference = $nonemptyPreference
    failure_exit_code = $failure.ExitCode
    failure_mode = $failure.Payload.result.mode
    failure_stderr = $failure.Stderr
    failure_artifact_exists = Test-Path -LiteralPath $failurePath
    failure_artifact = [string](Get-Content -LiteralPath $failurePath -Raw)
    failure_preference = $failurePreference
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
    assert result["empty_preference"] == "Stop"
    assert result["nonempty_exit_code"] == 0
    assert result["nonempty_ok"] is True
    assert "known diagnostic: nonempty-stderr" in result["nonempty_stderr"]
    assert result["nonempty_artifact_exists"] is True
    assert "known diagnostic: nonempty-stderr" in result["nonempty_artifact"]
    assert result["nonempty_preference"] == "Stop"
    assert result["failure_exit_code"] == 7
    assert result["failure_mode"] == "failure-stderr"
    assert "known diagnostic: failure-stderr" in result["failure_stderr"]
    assert result["failure_artifact_exists"] is True
    assert "known diagnostic: failure-stderr" in result["failure_artifact"]
    assert result["failure_preference"] == "Stop"


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize("script_path", LIVE_SCRIPTS, ids=lambda path: path.stem)
def test_live_summary_preserves_results_and_diagnostics(
    tmp_path: Path,
    script_path: Path,
) -> None:
    output_root = tmp_path / script_path.stem
    output_root.mkdir()
    harness_path = tmp_path / f"{script_path.stem}-summary-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,

    [Parameter(Mandatory = $true)]
    [string] $OutputRoot
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

foreach ($functionName in @(
    "Add-CaseResult",
    "Add-Diagnostic",
    "Write-DrainErrors",
    "Write-Summary"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$supportsSkip = [System.IO.Path]::GetFileName($ScriptPath) -ne "live-cli-check.ps1"

$script:RunRoot = Join-Path $OutputRoot "pass"
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
if ($supportsSkip) {
    Add-CaseResult -Name "preflight" -Status "PASS"
} else {
    Add-CaseResult -Name "preflight" -Passed $true
}
Write-DrainErrors -Errors @(
    [pscustomobject]@{ code = -350; message = "stale diagnostic" }
) -CaseName "stale-error-drain"
Write-Summary -Result "PASS"

$script:RunRoot = Join-Path $OutputRoot "fail"
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
if ($supportsSkip) {
    Add-CaseResult -Name "functional-case" -Status "FAIL" `
        -Detail "known failure detail"
} else {
    Add-CaseResult -Name "functional-case" -Passed $false `
        -Detail "known failure detail"
}
Write-Summary -Result "FAIL"

$script:RunRoot = Join-Path $OutputRoot "scpi-fail"
New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
if ($supportsSkip) {
    Add-CaseResult -Name "final-error-queue" -Status "FAIL" `
        -Detail "Final error queue contained 1 error(s)."
} else {
    Add-CaseResult -Name "final-error-queue" -Passed $false `
        -Detail "Final error queue contained 1 error(s)."
}
Write-DrainErrors -Errors @(
    [pscustomobject]@{ code = -222; message = "known diagnostic" }
) -CaseName "final-error-queue"
Write-Summary -Result "FAIL"

if ($supportsSkip) {
    $script:RunRoot = Join-Path $OutputRoot "skip"
    New-Item -ItemType Directory -Path $script:RunRoot | Out-Null
    $script:CaseResults = [ordered]@{}
    $script:Diagnostics = [ordered]@{}
    $caseName = if (
        [System.IO.Path]::GetFileName($ScriptPath) -eq "live-dvm-check.ps1"
    ) { "availability" } else { "segmented memory" }
    Add-CaseResult -Name $caseName -Status "SKIP" `
        -Detail "NOT AVAILABLE: required option/license is not installed."
    Write-DrainErrors -Errors @(
        [pscustomobject]@{ code = -241; message = "option not installed" }
    ) -CaseName $caseName
    Write-Summary -Result "SKIP"
}
""",
        encoding="utf-8",
    )

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
            "-OutputRoot",
            str(output_root),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "system error -222: known diagnostic" in completed.stdout

    pass_bytes = (output_root / "pass" / "summary.md").read_bytes()
    pass_summary = pass_bytes.decode("utf-8")
    assert not pass_bytes.startswith(b"\xef\xbb\xbf")
    assert "Result: PASS" in pass_summary
    assert "| preflight | PASS |" in pass_summary
    assert "### stale-error-drain" in pass_summary
    assert "system error -350: stale diagnostic" in pass_summary

    fail_bytes = (output_root / "fail" / "summary.md").read_bytes()
    fail_summary = fail_bytes.decode("utf-8")
    assert not fail_bytes.startswith(b"\xef\xbb\xbf")
    assert "Result: FAIL" in fail_summary
    assert "| functional-case | FAIL | known failure detail |" in fail_summary

    scpi_bytes = (output_root / "scpi-fail" / "summary.md").read_bytes()
    scpi_summary = scpi_bytes.decode("utf-8")
    assert not scpi_bytes.startswith(b"\xef\xbb\xbf")
    assert "Result: FAIL" in scpi_summary
    assert "| final-error-queue | FAIL |" in scpi_summary
    assert "Final error queue contained 1 error(s)." in scpi_summary
    assert "system error -222: known diagnostic" in scpi_summary

    if script_path.name != "live-cli-check.ps1":
        skip_bytes = (output_root / "skip" / "summary.md").read_bytes()
        skip_summary = skip_bytes.decode("utf-8")
        assert not skip_bytes.startswith(b"\xef\xbb\xbf")
        assert "Result: SKIP" in skip_summary
        assert "| SKIP | NOT AVAILABLE:" in skip_summary
        assert "system error -241: option not installed" in skip_summary


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize("script_path", LIVE_SCRIPTS, ids=lambda path: path.stem)
def test_live_preflight_failure_writes_summary_before_hardware_access(
    tmp_path: Path,
    script_path: Path,
) -> None:
    fake_package = tmp_path / "fake_cli" / "scopes_tool_cli"
    fake_package.mkdir(parents=True)
    (fake_package / "__init__.py").write_text("", encoding="utf-8")
    (fake_package / "cli.py").write_text(
        """\
import json
import os
from pathlib import Path
import sys

log_path = Path(os.environ["SCOPES_TOOL_FAKE_CLI_LOG"])
with log_path.open("a", encoding="utf-8") as log_file:
    log_file.write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({"ok": False, "error": {"message": "known preflight failure"}}))
print("known preflight diagnostic", file=sys.stderr)
sys.exit(9)
""",
        encoding="utf-8",
    )

    output_root = tmp_path / "artifacts"
    invocation_log = tmp_path / "fake-cli-invocations.jsonl"
    environment = os.environ.copy()
    python_path = str(fake_package.parent)
    if environment.get("PYTHONPATH"):
        python_path += os.pathsep + environment["PYTHONPATH"]
    environment["PYTHONPATH"] = python_path
    environment["SCOPES_TOOL_FAKE_CLI_LOG"] = str(invocation_log)

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-Resource",
            "TEST::INSTR",
            "-Python",
            sys.executable,
            "-OutputRoot",
            str(output_root),
        ],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1, completed.stderr
    assert "No live hardware was accessed." in completed.stdout
    run_roots = [path for path in output_root.iterdir() if path.is_dir()]
    assert len(run_roots) == 1
    summary_path = run_roots[0] / "summary.md"
    summary_bytes = summary_path.read_bytes()
    summary = summary_bytes.decode("utf-8")
    assert not summary_bytes.startswith(b"\xef\xbb\xbf")
    assert "Result: FAIL" in summary
    assert "| preflight | FAIL |" in summary
    assert "| preflight | FAIL |  |" not in summary

    invocations = [
        json.loads(line)
        for line in invocation_log.read_text(encoding="utf-8").splitlines()
    ]
    assert invocations
    assert all("--live" not in arguments for arguments in invocations)
