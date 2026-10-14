"""Only process/argument/JSON boundaries; functional coverage stays in validation."""
from __future__ import annotations

import json
import sys

import pytest

from tests.tooling._live_script_test_support import (
    REPO_ROOT, extract_live_cli_functions_ps, ps_quote, requires_windows, run_powershell,
)

pytestmark = [pytest.mark.windows_powershell, pytest.mark.windows_boundary_smoke, requires_windows]


@pytest.mark.parametrize("transport", ["native", "captured"])
def test_selected_python_cli_arguments_json_and_failure(tmp_path, transport):
    body = extract_live_cli_functions_ps(("Invoke-CliRaw",)) + f"""
$Python = {ps_quote(sys.executable)}
$RepoRoot = {ps_quote(REPO_ROOT)}
$script:RunRoot = {ps_quote(tmp_path)}
$script:CliInvocationIndex = 0
$script:Invocations = New-Object System.Collections.Generic.List[object]
$DebugArtifacts = $false
$transport = '{transport}'
function Invoke-BoundaryCli {{
    param([string]$Stage, [string[]]$Arguments)
    if ($transport -eq 'native') {{ return Invoke-CliRaw -Stage $Stage -Arguments $Arguments }}
    $record = Invoke-CapturedCommand -Name $Stage -FilePath $Python `
        -Arguments (@('-m', 'scopes_tool_cli.cli') + $Arguments) `
        -StdOutPath (Join-Path $script:RunRoot 'stdout.txt') `
        -StdErrPath (Join-Path $script:RunRoot 'stderr.txt') -CaptureInMemory
    return @{{ ExitCode = $record.exit_code; Payload = ($record.stdout_text | ConvertFrom-Json) }}
}}
$ordinary = Invoke-BoundaryCli ordinary @('identify', '--simulate', '--model', 'tektronix-tbs2074', '--json')
$special = Invoke-BoundaryCli special @('channel-label', '--channel', '1', '--text', 'Lab Signal', '--dry-run', '--json')
$failure = Invoke-BoundaryCli failure @('trigger-edge-coupling', '--coupling', 'ac', '--dry-run', '--model', 'tektronix-tbs2074', '--json')
@{{ version = $PSVersionTable.PSVersion.ToString(); ordinary = $ordinary; special = $special; failure = $failure }} |
    ConvertTo-Json -Depth 20 -Compress
"""
    result = run_powershell(body, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["version"].startswith("5.1.")
    assert payload["ordinary"]["ExitCode"] == 0
    assert payload["ordinary"]["Payload"]["ok"] is True
    assert payload["ordinary"]["Payload"]["idn"]["model"] == "TBS2074"
    assert payload["special"]["ExitCode"] == 0
    assert payload["special"]["Payload"]["result"]["text"] == "Lab Signal"
    assert payload["failure"]["ExitCode"] == 1
    assert payload["failure"]["Payload"]["ok"] is False
    assert payload["failure"]["Payload"]["error"]["type"] == "ParameterValidationError"
    assert "coupling" in payload["failure"]["Payload"]["error"]["message"].lower()
