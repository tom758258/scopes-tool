from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest
from tests.tooling._live_script_test_support import REPO_ROOT, requires_windows


VALIDATION_HELPERS_SCRIPT = REPO_ROOT / "scripts" / "_validation_helpers.ps1"


ARTIFACT_PRIVACY_SCRIPT = REPO_ROOT / "scripts" / "_artifact_privacy.ps1"


LIVE_CLI_SCRIPT = REPO_ROOT / "scripts" / "live-cli-check.ps1"


CANONICAL_TARGETS = (
    "keysight-dsox2004a",
    "keysight-dsox3024a",
    "keysight-dsox4024a",
    "keysight-dsox4034a",
)


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_live_cli_script(*args, timeout=180):
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LIVE_CLI_SCRIPT),
            *args,
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def run_live_cli_harness(body, timeout=180):
    command = (
        ". "
        + ps_quote(VALIDATION_HELPERS_SCRIPT)
        + "; . "
        + ps_quote(ARTIFACT_PRIVACY_SCRIPT)
        + "; "
        + body
    )
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def extract_live_cli_functions_ps(names):
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
""".replace("@SCRIPT@", str(LIVE_CLI_SCRIPT)).replace("@FUNCS@", name_list)


@requires_windows
@pytest.mark.parametrize(
    ("args", "expected_error"),
    (
        pytest.param(
            ("-Target", "all", "-Connection", "usb", "-Resource", "TEST::INSTR"),
            "'all' is not supported for live validation",
            id="target-all-rejected",
        ),
        pytest.param(
            (
                "-Target",
                "keysight-dsox9999a",
                "-Connection",
                "usb",
                "-Resource",
                "TEST::INSTR",
            ),
            "Unsupported target 'keysight-dsox9999a'",
            id="invalid-target-rejected",
        ),
        pytest.param(
            (
                "-Target",
                "keysight-dsox4034a",
                "-Connection",
                "rs232",
                "-Resource",
                "TEST::INSTR",
            ),
            "Unsupported connection 'rs232'",
            id="invalid-connection-rejected",
        ),
        pytest.param(
            (
                "-Target",
                "keysight-dsox4034a",
                "-Connection",
                "usb",
                "-Resource",
                "TCPIP0::198.51.100.7::inst0::INSTR",
            ),
            "does not match resource 'TCPIP0::198.51.100.7::inst0::INSTR'",
            id="usb-label-with-tcpip-resource-rejected",
        ),
        pytest.param(
            (
                "-Target",
                "keysight-dsox4034a",
                "-Connection",
                "tcpip",
                "-Resource",
                "USB0::1::2::SYNTH12345::INSTR",
            ),
            "does not match resource 'USB0::1::2::SYNTH12345::INSTR'",
            id="tcpip-label-with-usb-resource-rejected",
        ),
        pytest.param(
            (
                "-Target",
                "keysight-dsox4034a",
                "-Connection",
                "usb",
                "-Resource",
                "USB0::1::2::SYNTH12345::INSTR",
                "-Backend",
                "@unsupported",
            ),
            "Unsupported backend '@unsupported'",
            id="unsupported-backend-rejected",
        ),
    ),
)
def test_live_cli_check_usage_errors(args, expected_error):
    completed = run_live_cli_script(*args)
    assert completed.returncode == 2, completed.stderr + completed.stdout
    assert "[live][cli]" in completed.stderr
    assert expected_error in completed.stderr


@requires_windows
def test_live_cli_check_requires_target_and_connection():
    completed = run_live_cli_script("-Resource", "TEST::INSTR")
    assert completed.returncode != 0
    assert "Target" in completed.stderr

    completed = run_live_cli_script("-Target", "keysight-dsox4034a")
    assert completed.returncode != 0
    assert "Connection" in completed.stderr


@requires_windows
def test_live_cli_check_accepts_tektronix_target_before_resource_validation():
    completed = run_live_cli_script(
        "-Target", "tektronix-tbs2074", "-Connection", "usb",
        "-Resource", "TCPIP0::198.51.100.7::inst0::INSTR",
    )
    assert completed.returncode == 2
    assert "does not match resource" in completed.stderr
    assert "Unsupported target" not in completed.stderr


@requires_windows
def test_live_cli_check_target_model_match_gate():
    body = """
$results = @{}
$matching = [pscustomobject]@{
    idn = [pscustomobject]@{
        model = "DSOX4034A"
        raw = "KEYSIGHT TECHNOLOGIES,DSOX4034A,SYNTH12345,07.20"
    }
}
try {
    Assert-TargetModelMatch -Identity $matching -ResolvedTarget "keysight-dsox4034a"
    $results.match_canonical = ""
} catch {
    $results.match_canonical = $_.Exception.Message
}
$aliased = [pscustomobject]@{ idn = [pscustomobject]@{ model = "DSO-X 3024A" } }
try {
    Assert-TargetModelMatch -Identity $aliased -ResolvedTarget "keysight-dsox3024a"
    $results.match_alias = ""
} catch {
    $results.match_alias = $_.Exception.Message
}
$mismatched = [pscustomobject]@{ idn = [pscustomobject]@{ model = "DSOX2004A" } }
try {
    Assert-TargetModelMatch -Identity $mismatched -ResolvedTarget "keysight-dsox3024a"
    $results.mismatch = ""
} catch {
    $results.mismatch = $_.Exception.Message
}
$missing = [pscustomobject]@{ idn = $null }
try {
    Assert-TargetModelMatch -Identity $missing -ResolvedTarget "keysight-dsox4034a"
    $results.missing = ""
} catch {
    $results.missing = $_.Exception.Message
}
$tek = [pscustomobject]@{
    idn = [pscustomobject]@{ vendor = "Tektronix"; model = "TBS2074" }
    capabilities = [pscustomobject]@{ series = "TBS2000"; analog_channels = 4 }
}
try {
    Assert-TargetModelMatch -Identity $tek -ResolvedTarget "tektronix-tbs2074"
    $results.tek_match = ""
} catch {
    $results.tek_match = $_.Exception.Message
}
$tekWrongVendor = [pscustomobject]@{
    idn = [pscustomobject]@{ vendor = "Keysight"; model = "TBS2074" }
    capabilities = [pscustomobject]@{ series = "TBS2000"; analog_channels = 4 }
}
try {
    Assert-TargetModelMatch -Identity $tekWrongVendor -ResolvedTarget "tektronix-tbs2074"
    $results.tek_wrong_vendor = ""
} catch {
    $results.tek_wrong_vendor = $_.Exception.Message
}
$tekWrongModel = [pscustomobject]@{
    idn = [pscustomobject]@{ vendor = "Tektronix"; model = "TDS2024B" }
    capabilities = [pscustomobject]@{ series = "TBS2000"; analog_channels = 4 }
}
try {
    Assert-TargetModelMatch -Identity $tekWrongModel -ResolvedTarget "tektronix-tbs2074"
    $results.tek_wrong_model = ""
} catch {
    $results.tek_wrong_model = $_.Exception.Message
}
$tekWrongSeries = [pscustomobject]@{
    idn = [pscustomobject]@{ vendor = "Tektronix"; model = "TBS2074" }
    capabilities = [pscustomobject]@{ series = "TDS2000B"; analog_channels = 4 }
}
try {
    Assert-TargetModelMatch -Identity $tekWrongSeries -ResolvedTarget "tektronix-tbs2074"
    $results.tek_wrong_series = ""
} catch {
    $results.tek_wrong_series = $_.Exception.Message
}
$tekWrongChannels = [pscustomobject]@{
    idn = [pscustomobject]@{ vendor = "Tektronix"; model = "TBS2074" }
    capabilities = [pscustomobject]@{ series = "TBS2000"; analog_channels = 2 }
}
try {
    Assert-TargetModelMatch -Identity $tekWrongChannels -ResolvedTarget "tektronix-tbs2074"
    $results.tek_wrong_channels = ""
} catch {
    $results.tek_wrong_channels = $_.Exception.Message
}
[ordered]@{
    match_canonical = [string]$results.match_canonical
    match_alias = [string]$results.match_alias
    mismatch = [string]$results.mismatch
    missing = [string]$results.missing
    tek_match = [string]$results.tek_match
    tek_wrong_vendor = [string]$results.tek_wrong_vendor
    tek_wrong_model = [string]$results.tek_wrong_model
    tek_wrong_series = [string]$results.tek_wrong_series
    tek_wrong_channels = [string]$results.tek_wrong_channels
} | ConvertTo-Json -Depth 4 -Compress
"""
    result = run_live_cli_harness(body)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.splitlines()[-1])
    assert payload["match_canonical"] == ""
    assert payload["match_alias"] == ""
    assert "DSOX2004A" in payload["mismatch"]
    assert "does not match" in payload["mismatch"]
    assert "keysight-dsox3024a" in payload["mismatch"]
    assert "unavailable" in payload["missing"]
    assert payload["tek_match"] == ""
    assert payload["tek_wrong_vendor"]
    assert payload["tek_wrong_model"]
    assert payload["tek_wrong_series"]
    assert payload["tek_wrong_channels"]


@requires_windows
def test_shared_target_resolution_keeps_tektronix_opt_in() -> None:
    body = """
$defaultAll = @(Resolve-ValidationTargets -Target "all")
$tekAll = @(Resolve-ValidationTargets -Target "all" -IncludeTektronix)
$withoutOptIn = ""
try {
    Resolve-ValidationTargets -Target "tektronix-tbs2074" | Out-Null
} catch {
    $withoutOptIn = $_.Exception.Message
}
$withOptIn = @(Resolve-ValidationTargets -Target "tektronix-tbs2074" -IncludeTektronix)
[ordered]@{
    default_all = $defaultAll
    tek_all = $tekAll
    without_opt_in = $withoutOptIn
    with_opt_in = $withOptIn
} | ConvertTo-Json -Depth 4 -Compress
"""
    result = run_live_cli_harness(body)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.splitlines()[-1])
    assert payload["default_all"] == list(CANONICAL_TARGETS)
    assert payload["tek_all"] == [
        *CANONICAL_TARGETS,
        "tektronix-tbs2074",
        "tektronix-tds2024b",
        "tektronix-tbs1052b",
    ]
    assert "Unsupported target 'tektronix-tbs2074'" in payload["without_opt_in"]
    assert payload["with_opt_in"] == ["tektronix-tbs2074"]


LIVE_VALIDATOR_SCRIPTS = (
    ("live-dvm-check.ps1", "dvm"),
    ("live-segmented-check.ps1", "segmented"),
    ("live-serial-check.ps1", "serial"),
    ("live-workflow-check.ps1", "workflow"),
)


@requires_windows
@pytest.mark.parametrize(("script_name", "domain"), LIVE_VALIDATOR_SCRIPTS)
def test_live_validators_enforce_canonical_target_contract(tmp_path, script_name, domain):
    script = REPO_ROOT / "scripts" / script_name
    usb = "USB0::1::2::SYNTH12345::INSTR"
    tcpip = "TCPIP0::198.51.100.7::inst0::INSTR"

    def run(*extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                *extra,
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=120,
        )

    completed = run("-Target", "all", "-Connection", "usb", "-Resource", usb)
    assert completed.returncode == 2
    assert "[live][%s]" % domain in completed.stderr
    assert "'all' is not supported for live validation" in completed.stderr

    completed = run(
        "-Target", "keysight-dsox9999a", "-Connection", "usb", "-Resource", usb
    )
    assert completed.returncode == 2
    assert "Unsupported target 'keysight-dsox9999a'" in completed.stderr

    completed = run(
        "-Target", "keysight-dsox4034a", "-Connection", "rs232", "-Resource", usb
    )
    assert completed.returncode == 2
    assert "Unsupported connection 'rs232'" in completed.stderr

    completed = run(
        "-Target", "keysight-dsox4034a", "-Connection", "usb", "-Resource", tcpip
    )
    assert completed.returncode == 2
    assert f"does not match resource '{tcpip}'" in completed.stderr

    tek_target = "tektronix-tbs2074"
    completed = run("-Target", tek_target, "-Connection", "usb", "-Resource", tcpip)
    if domain in {"cli", "workflow"}:
        assert completed.returncode == 2
        assert f"does not match resource '{tcpip}'" in completed.stderr
        assert "Unsupported target" not in completed.stderr
    else:
        assert completed.returncode == 2
        assert f"Unsupported target '{tek_target}'" in completed.stderr

    completed = run(
        "-Target", "keysight-dsox4034a", "-Connection", "usb",
        "-Resource", usb, "-Backend", "@unsupported"
    )
    assert completed.returncode == 2
    assert "Unsupported backend '@unsupported'" in completed.stderr


@pytest.mark.parametrize(("script_name", "domain"), LIVE_VALIDATOR_SCRIPTS)
def test_live_validators_wire_shared_framework(script_name, domain):
    text = (REPO_ROOT / "scripts" / script_name).read_text(encoding="utf-8")
    for marker in (
        "_validation_helpers.ps1",
        "_artifact_privacy.ps1",
        "Invoke-CapturedCommand ",
        "New-ValidationRunDirectory -BaseRoot $outputBase",
        "Assert-TargetModelMatch -Identity $identity -ResolvedTarget $script:Target",
        f"Complete-LiveValidationRun -Kind 'scopes-tool-live-{domain}-check'",
        "-DebugArtifacts:$DebugArtifacts",
        "$script:HardwareTouched = $true",
        "$script:Invocations.Add($invocationRecord) | Out-Null",
    ):
        assert marker in text, (script_name, marker)


def _normalize_json_text(text):
    return (
        text.replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\/", "/")
        .replace("\\\\", "\\")
    )


@requires_windows
def test_live_cli_check_complete_run_builds_private_and_shareable_evidence(tmp_path):
    runs_root = tmp_path / "runs"
    resource = "USB0::1::2::SYNTH12345::INSTR"
    body = extract_live_cli_functions_ps(("Write-Summary",)) + """
$Resource = '@RESOURCE@'
$RepoRoot = '@REPO@'
$RunsRoot = '@RUNS@'

# --- scenario 1: FAIL run carrying sensitive evidence ---
$layout = New-ValidationRunDirectory -BaseRoot $RunsRoot -Prefix 'run'
$script:RunDirectory = $layout.Root
$script:RunRoot = $layout.Private
$script:ShareableRoot = $layout.Shareable
$script:Target = 'keysight-dsox4034a'
$script:Connection = 'usb'
$script:BackendName = 'system_visa'
$script:FunctionalFailed = $true
$script:ShareableGenerationFailed = $false
$script:HardwareTouched = $true
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:CliInvocationIndex = 0
$stdoutPath = Join-Path $script:RunRoot 'cli-001-identity.stdout.txt'
$jsonPath = Join-Path $script:RunRoot 'cli-001-identity.json'
Write-Utf8NoBomText -LiteralPath $stdoutPath `
    -Text ('{"ok":true,"resource":"' + $Resource + '"}')
Write-Utf8NoBomText -LiteralPath $jsonPath `
    -Text '{"ok":true,"idn":{"raw":"KEYSIGHT TECHNOLOGIES,DSOX4034A,SYNTH12345,07.20"}}'
$script:Invocations.Add([pscustomobject]@{
    index = 1
    stage = 'identity'
    command = 'python -m scopes_tool_cli.cli identify'
    arguments = @('identify', '--resource', $Resource)
    exit_code = 0
    duration_ms = 123.4
    success = $true
    stdout = (Get-ArtifactRelativePath -Path $stdoutPath -BaseRoot $RepoRoot)
    stderr = ''
    json = (Get-ArtifactRelativePath -Path $jsonPath -BaseRoot $RepoRoot)
}) | Out-Null
$script:CaseResults['identity'] = [pscustomobject]@{
    Passed = $true; Status = 'PASS'; Detail = '' }
$script:CaseResults['pair-measurement'] = [pscustomobject]@{
    Passed = $false; Status = 'FAIL';
    Detail = ('VISA query failed for ' + $Resource +
        ' at host 192.168.1.50 under repo ' + $RepoRoot) }
$script:CaseResults['math-composite-source'] = [pscustomobject]@{
    Passed = $false; Status = 'N/A'; Detail = 'unsupported on detected model' }

Complete-LiveValidationRun -Kind 'scopes-tool-live-cli-check' -Domain 'cli' -Result 'FAIL' -DebugArtifacts

$privateReportRaw =
    [System.IO.File]::ReadAllText((Join-Path $script:RunRoot 'report.json'))
$privateSummaryText =
    [System.IO.File]::ReadAllText((Join-Path $script:RunRoot 'summary.md'))
$shareableDir = Join-Path $script:RunDirectory 'shareable'
$shareableReportRaw =
    [System.IO.File]::ReadAllText((Join-Path $shareableDir 'report.json'))
$shareableSummaryRaw =
    [System.IO.File]::ReadAllText((Join-Path $shareableDir 'summary.md'))
$shareableReport = $shareableReportRaw | ConvertFrom-Json
$privateReport = $privateReportRaw | ConvertFrom-Json
$firstInvocation = @($shareableReport.invocations)[0]
$mirrorReference = [string]$firstInvocation.json
$mirrorPath = Join-Path $shareableDir $mirrorReference.Substring('shareable/'.Length)
$mirrorText = [System.IO.File]::ReadAllText($mirrorPath)

# --- scenario 2: passing cases but shareable generation fails ---
function New-ShareableArtifactSet {
    throw [System.InvalidOperationException]::new(
        'simulated shareable artifact generation failure')
}
$layout2 = New-ValidationRunDirectory -BaseRoot $RunsRoot -Prefix 'run'
$script:RunDirectory = $layout2.Root
$script:RunRoot = $layout2.Private
$script:ShareableRoot = $layout2.Shareable
$script:BackendName = 'pyvisa_py'
$script:FunctionalFailed = $false
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:CaseResults['identity'] = [pscustomobject]@{
    Passed = $true; Status = 'PASS'; Detail = '' }
Complete-LiveValidationRun -Kind 'scopes-tool-live-cli-check' -Domain 'cli' -Result 'PASS'

$s2ReportRaw =
    [System.IO.File]::ReadAllText((Join-Path $script:RunRoot 'report.json'))
$s2SummaryText =
    [System.IO.File]::ReadAllText((Join-Path $script:RunRoot 'summary.md'))
$s2Report = $s2ReportRaw | ConvertFrom-Json

[ordered]@{
    s1_status = [string]$privateReport.status
    s1_target = [string]$privateReport.target
    s1_connection = [string]$privateReport.connection
    s1_backend = [string]$privateReport.backend
    s1_counts_cases = [int]$privateReport.summary_counts.cases
    s1_counts_passed = [int]$privateReport.summary_counts.passed
    s1_counts_failed = [int]$privateReport.summary_counts.failed
    s1_counts_na = [int]$privateReport.summary_counts.na
    s1_counts_invocations = [int]$privateReport.summary_counts.invocations
    s1_hardware_touched = [bool]$privateReport.hardware_touched
    s1_private_report_raw = $privateReportRaw
    s1_private_summary_has_target =
        $privateSummaryText.Contains('Target: keysight-dsox4034a')
    s1_private_summary_has_backend =
        $privateSummaryText.Contains('Backend: system_visa')
    s1_shareable_report_raw = $shareableReportRaw
    s1_shareable_summary_raw = $shareableSummaryRaw
    s1_mirror_reference = $mirrorReference
    s1_mirror_exists = (Test-Path -LiteralPath $mirrorPath -PathType Leaf)
    s1_mirror_text = $mirrorText
    s1_case_statuses = @(@($shareableReport.cases) |
        ForEach-Object { [string]$_.status })
    s1_shareable_status = [string]$shareableReport.status
    s2_flag = $script:ShareableGenerationFailed
    s2_status = [string]$s2Report.status
    s2_backend = [string]$s2Report.backend
    s2_summary_has_backend = $s2SummaryText.Contains('Backend: pyvisa_py')
    s2_error = [string]$s2Report.shareable_generation_error
    s2_summary_reason = $s2SummaryText.Contains(
        'Shareable artifact generation failed:')
} | ConvertTo-Json -Depth 8 -Compress
""".replace("@RESOURCE@", resource).replace("@REPO@", str(REPO_ROOT)).replace(
        "@RUNS@", str(runs_root)
    )

    result = run_live_cli_harness(body, timeout=300)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.splitlines()[-1])

    assert payload["s1_status"] == "failed"
    assert payload["s1_target"] == "keysight-dsox4034a"
    assert payload["s1_connection"] == "usb"
    assert payload["s1_backend"] == "system_visa"
    assert payload["s1_counts_cases"] == 3
    assert payload["s1_counts_passed"] == 1
    assert payload["s1_counts_failed"] == 1
    assert payload["s1_counts_na"] == 1
    assert payload["s1_counts_invocations"] == 1
    assert payload["s1_hardware_touched"] is True
    assert payload["s1_case_statuses"] == ["PASS", "FAIL", "N/A"]
    assert payload["s1_private_summary_has_target"] is True
    assert payload["s1_private_summary_has_backend"] is True
    assert payload["s1_shareable_status"] == "failed"

    # Private evidence retains raw sensitive values.
    normalized_private = _normalize_json_text(payload["s1_private_report_raw"])
    assert resource in normalized_private
    assert "SYNTH12345" in normalized_private

    # Shareable artifacts are redacted everywhere.
    joined_shareable = _normalize_json_text(
        "\n".join(
            (
                payload["s1_shareable_report_raw"],
                payload["s1_shareable_summary_raw"],
                payload["s1_mirror_text"],
            )
        )
    )
    for secret in (resource, "SYNTH12345", "192.168.1.50", str(REPO_ROOT)):
        assert secret not in joined_shareable, secret
    assert "<redacted-resource>" in joined_shareable
    assert "<redacted-idn>" in joined_shareable
    assert "<redacted-ip>" in joined_shareable

    # Invocation references point into the existing shareable tree.
    reference = payload["s1_mirror_reference"]
    assert reference.startswith("shareable/")
    assert payload["s1_mirror_exists"] is True

    # Scenario 2: all cases passed, but shareable generation failed.
    assert payload["s2_flag"] is True
    assert payload["s2_status"] == "failed"
    assert payload["s2_backend"] == "pyvisa_py"
    assert payload["s2_summary_has_backend"] is True
    assert payload["s2_error"] == "simulated shareable artifact generation failure"
    assert payload["s2_summary_reason"] is True


@requires_windows
@pytest.mark.parametrize(("script_name", "domain"), (("live-cli-check.ps1", "cli"), *LIVE_VALIDATOR_SCRIPTS))
@pytest.mark.parametrize("debug", (False, True), ids=("minimal", "debug"))
@pytest.mark.parametrize("result_status", ("PASS", "FAIL"))
def test_live_artifact_retention_modes(tmp_path, script_name, domain, debug, result_status):
    outside = tmp_path / "outside.txt"
    outside.write_text("outside evidence", encoding="utf-8")
    sibling = tmp_path / "run_previous" / "private" / "raw.txt"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("previous run evidence", encoding="utf-8")
    script_path = REPO_ROOT / "scripts" / script_name
    body = extract_live_cli_functions_ps(("Write-Summary",)).replace(
        str(LIVE_CLI_SCRIPT), str(script_path)
    ) + """
$paramScript = [scriptblock]::Create($ast.ParamBlock.Extent.Text + '; [bool]$DebugArtifacts')
$defaultDebug = & $paramScript -Target 'keysight-dsox4034a' -Connection 'usb' -Resource 'TEST::INSTR'
$explicitDebug = & $paramScript -Target 'keysight-dsox4034a' -Connection 'usb' -Resource 'TEST::INSTR' -DebugArtifacts
$Resource = 'USB0::1::2::SYNTH12345::INSTR'
$RepoRoot = '@REPO@'
$layout = New-ValidationRunDirectory -BaseRoot '@RUNS@'
$script:RunDirectory = $layout.Root
$script:RunRoot = $layout.Private
$script:ShareableRoot = $layout.Shareable
$script:Target = 'keysight-dsox4034a'
$script:Connection = 'usb'
$script:BackendName = 'system_visa'
$script:ShareableGenerationFailed = $false
$script:HardwareTouched = $false
$script:CaseResults = [ordered]@{
    identity = [pscustomobject]@{ Passed = $true; Status = 'PASS'; Detail = '' }
    validation = [pscustomobject]@{
        Passed = ('@RESULT@' -eq 'PASS'); Status = '@RESULT@'
        Detail = 'known validation diagnostic for USB0::1::2::SYNTH12345::INSTR at 192.168.1.50'
    }
    optional = [pscustomobject]@{ Passed = $false; Status = 'N/A'; Detail = 'unsupported feature' }
    cleanup = [pscustomobject]@{ Passed = $true; Status = 'PASS'; Detail = 'original state restored' }
    final_error = [pscustomobject]@{ Passed = $true; Status = 'PASS'; Detail = 'error queue clean' }
}
$script:Diagnostics = [ordered]@{
    validation = @('known failure diagnostic; Native status and errors are retained in the CLI artifacts; no extra destructive status read was issued.')
}
$script:Invocations = New-Object System.Collections.Generic.List[object]
$rawNames = @('identity.stdout.txt', 'identity.stderr.txt', 'identity.json',
    'raw/native.log', 'workflow/sequence.json', 'preflight/report.json', 'capture.bin', 'lister.csv')
foreach ($name in $rawNames) {
    $path = Join-Path $script:RunRoot $name
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
    Write-Utf8NoBomText -LiteralPath $path -Text '{"resource":"USB0::1::2::SYNTH12345::INSTR","serial":"SYNTH12345","host":"192.168.1.50"}'
}
Write-Utf8NoBomText -LiteralPath (Join-Path $layout.Root '.intermediate') -Text 'temporary'
$artifactRelative = Get-ArtifactRelativePath -BaseRoot $RepoRoot -Path (Join-Path $script:RunRoot 'workflow/sequence.json')
$script:Diagnostics['artifact-reference'] = @("historical artifact: ${artifactRelative}; shareable/workflow/sequence.json")
$script:Invocations.Add([pscustomobject]@{
    index = 1; stage = 'identity'; command = 'fake-cli'; arguments = @(
        'identify', '--resource', $Resource, '--output', (Join-Path $script:RunRoot 'workflow/sequence.json'))
    exit_code = 0; duration_ms = 123.4; success = $true
    stdout = Get-ArtifactRelativePath -BaseRoot $RepoRoot -Path (Join-Path $script:RunRoot 'identity.stdout.txt')
    stderr = Get-ArtifactRelativePath -BaseRoot $RepoRoot -Path (Join-Path $script:RunRoot 'identity.stderr.txt')
    json = Get-ArtifactRelativePath -BaseRoot $RepoRoot -Path (Join-Path $script:RunRoot 'identity.json')
}) | Out-Null
Complete-LiveValidationRun -Kind 'scopes-tool-live-@DOMAIN@-check' -Domain '@DOMAIN@' -Result '@RESULT@' @DEBUG@
[ordered]@{
    run_root = $layout.Root
    failed = $script:ShareableGenerationFailed
    default_debug = $defaultDebug
    explicit_debug = $explicitDebug
} | ConvertTo-Json -Compress
""".replace("@REPO@", str(REPO_ROOT)).replace("@RUNS@", str(tmp_path)).replace(
        "@RESULT@", result_status
    ).replace("@DOMAIN@", domain).replace("@DEBUG@", "-DebugArtifacts" if debug else "")
    completed = run_live_cli_harness(body)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout.splitlines()[-1])
    assert payload["default_debug"] is False
    assert payload["explicit_debug"] is True
    assert payload["failed"] is False
    run_root = Path(payload["run_root"])
    files = {p.relative_to(run_root).as_posix() for p in run_root.rglob("*") if p.is_file()}
    report_raw = (run_root / "shareable/report.json").read_text(encoding="utf-8")
    summary = (run_root / "shareable/summary.md").read_text(encoding="utf-8")
    report = json.loads(report_raw)
    assert report["status"] == ("passed" if result_status == "PASS" else "failed")
    assert report["artifact_mode"] == ("debug" if debug else "minimal")
    assert report["debug_artifacts_retained"] is debug
    assert report["private_raw_artifacts_retained"] is debug
    assert report["summary_counts"] == {
        "cases": 5, "passed": 4 if result_status == "PASS" else 3,
        "failed": 0 if result_status == "PASS" else 1, "na": 1, "invocations": 1,
    }
    assert report["hardware_touched"] is False
    assert report["target"] == "keysight-dsox4034a"
    assert report["connection"] == "usb"
    assert report["backend"] == "system_visa"
    assert report["git_head"] and report["package_version"] and report["generated_at"]
    assert report["candidate_evidence_only"] is True
    assert report["promotes_live_support"] is False
    for field, filename in (("report", "report.json"), ("summary", "summary.md")):
        assert report["artifact_paths"][field] == f"shareable/{filename}"
        assert (run_root / report["artifact_paths"][field]).is_file()
    invocation = report["invocations"][0]
    assert invocation["exit_code"] == 0 and invocation["success"] is True
    assert invocation["index"] == 1 and invocation["stage"] == "identity"
    assert invocation["duration_ms"] == 123.4
    for marker in (f"Result: {result_status}", "known validation diagnostic", "known failure diagnostic",
                   "original state restored", "error queue clean", "unsupported feature"):
        assert marker in summary
    for secret in ("USB0::1::2::SYNTH12345::INSTR", "SYNTH12345", "192.168.1.50", str(REPO_ROOT)):
        assert secret not in _normalize_json_text(report_raw + summary)
    if debug:
        for name in ("identity.stdout.txt", "identity.stderr.txt", "identity.json", "raw/native.log",
                     "workflow/sequence.json", "preflight/report.json", "capture.bin", "lister.csv"):
            assert f"private/{name}" in files
            assert "SYNTH12345" in (run_root / "private" / name).read_text(encoding="utf-8")
        assert "private/report.json" in files and "private/summary.md" in files
        assert ".intermediate" in files
        for field in ("stdout", "stderr", "json"):
            assert (run_root / invocation[field]).is_file()
        assert "shareable/workflow/sequence.json" in files
        assert "shareable/preflight/report.json" in files
    else:
        assert files == {"shareable/report.json", "shareable/summary.md"}
        assert {p.relative_to(run_root).as_posix() for p in run_root.rglob("*") if p.is_dir()} == {"shareable"}
        assert all(invocation[field] is None for field in ("stdout", "stderr", "json"))
        assert invocation["arguments"][-1] == "<artifact-not-retained>"
        assert "shareable/workflow/sequence.json" not in report_raw + summary
        assert "retained in the CLI artifacts" not in report_raw + summary
    assert outside.read_text(encoding="utf-8") == "outside evidence"
    assert sibling.read_text(encoding="utf-8") == "previous run evidence"


@requires_windows
@pytest.mark.parametrize("failure", ("throw", "missing-report", "missing-summary", "empty-summary", "invalid-report", "private-report", "private-summary"))
def test_live_artifact_generation_failure_retains_raw_evidence(tmp_path, failure):
    body = extract_live_cli_functions_ps(("Write-Summary",)) + """
$Resource = 'USB0::1::2::SYNTH12345::INSTR'
$RepoRoot = '@REPO@'
$layout = New-ValidationRunDirectory -BaseRoot '@RUNS@'
$script:RunDirectory = $layout.Root
$script:RunRoot = $layout.Private
$script:ShareableRoot = $layout.Shareable
$script:Target = 'keysight-dsox4034a'
$script:Connection = 'usb'
$script:BackendName = 'system_visa'
$script:HardwareTouched = $false
$script:ShareableGenerationFailed = $false
$script:CaseResults = [ordered]@{ identity = [pscustomobject]@{ Passed = $true; Status = 'PASS'; Detail = '' } }
$script:Diagnostics = [ordered]@{}
$script:Invocations = New-Object System.Collections.Generic.List[object]
Write-Utf8NoBomText -LiteralPath (Join-Path $script:RunRoot 'raw.stdout.txt') -Text 'unique raw evidence SYNTH12345'
function New-ShareableArtifactSet {
    if ('@FAILURE@' -eq 'throw') { throw 'injected generation failure' }
    if ('@FAILURE@' -ne 'missing-report') {
        $text = if ('@FAILURE@' -eq 'invalid-report') { 'invalid json' } else { '{"status":"passed"}' }
        Write-Utf8NoBomText -LiteralPath (Join-Path $script:ShareableRoot 'report.json') -Text $text
    }
    if ('@FAILURE@' -ne 'missing-summary') {
        $text = if ('@FAILURE@' -eq 'empty-summary') { '' } else { 'Result: PASS' }
        Write-Utf8NoBomText -LiteralPath (Join-Path $script:ShareableRoot 'summary.md') -Text $text
    }
}
if ('@FAILURE@' -eq 'private-summary') {
    function Write-Summary { throw 'injected private summary failure' }
}
if ('@FAILURE@' -eq 'private-report') {
    $script:ReportWriteAttempt = 0
    function Write-JsonReport {
        param([string]$LiteralPath, $Report)
        $script:ReportWriteAttempt += 1
        if ($script:ReportWriteAttempt -eq 1) { throw 'injected private report failure' }
        Write-Utf8NoBomText -LiteralPath $LiteralPath -Text ($Report | ConvertTo-Json -Depth 20)
    }
}
Complete-LiveValidationRun -Kind 'scopes-tool-live-cli-check' -Domain 'cli' -Result 'PASS'
[ordered]@{ run_root = $layout.Root; failed = $script:ShareableGenerationFailed } | ConvertTo-Json -Compress
""".replace("@REPO@", str(REPO_ROOT)).replace("@RUNS@", str(tmp_path)).replace("@FAILURE@", failure)
    completed = run_live_cli_harness(body)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout.splitlines()[-1])
    assert payload["failed"] is True
    assert "Artifact Generation Failure" in completed.stdout
    root = Path(payload["run_root"])
    assert (root / "private/raw.stdout.txt").read_text(encoding="utf-8") == "unique raw evidence SYNTH12345"
    report = json.loads((root / "private/report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["shareable_generation_error"]
    summary = (root / "private/summary.md").read_text(encoding="utf-8")
    assert "Shareable artifact generation failed:" in summary
    assert "Result: PASS" not in summary
    assert not (root / "shareable/report.json").exists()
    assert not (root / "shareable/summary.md").exists()


LIVE_VALIDATOR_FINALIZATION_CASES = (
    (
        "live-dvm-check.ps1",
        "scopes-tool-live-dvm-check",
        "dvm",
        "FAIL  DVM live validation",
        "PASS  DVM live validation",
    ),
    (
        "live-segmented-check.ps1",
        "scopes-tool-live-segmented-check",
        "segmented",
        "FAIL  Segmented Memory live validation",
        "PASS  Segmented Memory live validation",
    ),
    (
        "live-serial-check.ps1",
        "scopes-tool-live-serial-check",
        "serial",
        "FAIL  Serial live validation",
        "PASS  Serial live validation",
    ),
    (
        "live-workflow-check.ps1",
        "scopes-tool-live-workflow-check",
        "workflow",
        "FAIL  Workflow live validation",
        "PASS  Workflow live validation",
    ),
)


def _extract_balanced_block(text: str, start_marker: str) -> str:
    start = text.index(start_marker)
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError("unbalanced braces")


@pytest.mark.parametrize(
    ("script_name", "kind", "domain", "fail_label", "pass_label"),
    LIVE_VALIDATOR_FINALIZATION_CASES,
)
def test_live_validator_finalization_control_flow(
    script_name, kind, domain, fail_label, pass_label
):
    text = (REPO_ROOT / "scripts" / script_name).read_text(encoding="utf-8")

    # Migration template placeholders must never reach production output.
    assert "@DOMAIN@" not in text
    assert "@OUTPUTROOT@" not in text

    fail_block = _extract_balanced_block(text, "if ($script:FunctionalFailed) {")
    fail_finalize = (
        "Complete-LiveValidationRun -Kind '{kind}' "
        "-Domain '{domain}' -Result \"FAIL\""
    ).format(kind=kind, domain=domain)
    assert fail_block.count(fail_finalize) == 1
    # The FAIL path always terminates: no fall-through into SKIP/PASS
    # finalization regardless of shareable generation outcome.
    assert fail_block.rstrip().endswith("exit 1\n}")

    block_end = text.index(fail_block) + len(fail_block)
    tail_after_fail = text[block_end:]

    # Exactly one PASS finalization follows, and no stray FAIL finalize.
    pass_finalize = (
        "Complete-LiveValidationRun -Kind '{kind}' "
        "-Domain '{domain}' -Result \"PASS\""
    ).format(kind=kind, domain=domain)
    assert tail_after_fail.count(pass_finalize) == 1
    assert '-Result "FAIL"' not in tail_after_fail

    # Success contract: PASS finalization, then console PASS, then exit 0;
    # a shareable failure downgrades it to FAIL with exit 1.
    pass_tail = tail_after_fail[tail_after_fail.index(pass_finalize) :]
    assert "$script:ShareableGenerationFailed) {" in pass_tail
    assert pass_tail.index('Write-Host "%s"' % pass_label) > pass_tail.index(
        "if ($script:ShareableGenerationFailed)"
    )
    assert pass_tail.rstrip().endswith('Write-Host "%s"\nexit 0' % pass_label)


@requires_windows
def test_workflow_post_case_error_queue_regression(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-workflow-check.ps1"
    harness_path = tmp_path / "workflow-post-case-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
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
        $node.Name -eq "Invoke-WorkflowCase"
    )
}, $true)
if ($null -eq $functionAst) {
    throw "Invoke-WorkflowCase was not found in ${ScriptPath}."
}
Invoke-Expression $functionAst.Extent.Text

$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:IsTektronix = $false
$script:WriteDrainErrorsCalls = New-Object System.Collections.Generic.List[object]
$script:DrainAfterFailureCalls = New-Object System.Collections.Generic.List[object]
$script:AddCaseResultCalls = New-Object System.Collections.Generic.List[object]

function Add-CaseResult {
    param([string] $Name, [string] $Status, [string] $Detail = "")
    $script:AddCaseResultCalls.Add([pscustomobject]@{ Name = $Name; Status = $Status; Detail = $Detail })
    $script:CaseResults[$Name] = [pscustomobject]@{ Status = $Status; Detail = $Detail }
}
function Write-DrainErrors {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]] $Errors,
        [string] $CaseName = ""
    )
    $script:WriteDrainErrorsCalls.Add([pscustomobject]@{ Errors = @($Errors); CaseName = $CaseName })
}
function Drain-AfterFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,
        [Parameter(Mandatory = $true)]
        [string] $CaseName
    )
    $script:DrainAfterFailureCalls.Add([pscustomobject]@{ Stage = $Stage; CaseName = $CaseName })
}
$script:Scenario = "pass"
function Get-ErrorDrain {
    param([Parameter(Mandatory = $true)][string] $Stage)
    if ($script:Scenario -eq "pass") {
        return [pscustomobject]@{
            Invocation = $null
            Entries = @([pscustomobject]@{ code = 0; message = "No error"; raw = '+0,"No error"' })
            Errors = @()
            Terminated = $true
        }
    } else {
        $err = [pscustomobject]@{ code = -221; message = "Settings conflict"; raw = '-221,"Settings conflict"' }
        return [pscustomobject]@{
            Invocation = $null
            Entries = @($err, [pscustomobject]@{ code = 0; message = "No error"; raw = '+0,"No error"' })
            Errors = @($err)
            Terminated = $true
        }
    }
}

# PASS case
$script:Scenario = "pass"
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:WriteDrainErrorsCalls.Clear()
$script:DrainAfterFailureCalls.Clear()
$script:AddCaseResultCalls.Clear()
Invoke-WorkflowCase -Name "demo-pass" -Action { }
$passStatus = $script:CaseResults["demo-pass"].Status
$passFunctional = $script:FunctionalFailed
$passWriteCount = $script:WriteDrainErrorsCalls.Count
$passDrainCount = $script:DrainAfterFailureCalls.Count

# FAIL case
$script:Scenario = "fail"
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:WriteDrainErrorsCalls.Clear()
$script:DrainAfterFailureCalls.Clear()
$script:AddCaseResultCalls.Clear()
Invoke-WorkflowCase -Name "demo-fail" -Action { }
$failStatus = $script:CaseResults["demo-fail"].Status
$failFunctional = $script:FunctionalFailed
$failWriteCount = $script:WriteDrainErrorsCalls.Count
$failDrainCount = $script:DrainAfterFailureCalls.Count
$failDrainStage = if ($failDrainCount -gt 0) { $script:DrainAfterFailureCalls[0].Stage } else { "" }
$failDrainCase = if ($failDrainCount -gt 0) { $script:DrainAfterFailureCalls[0].CaseName } else { "" }
$failDetail = $script:CaseResults["demo-fail"].Detail

[ordered]@{
    pass_status = $passStatus
    pass_functional_failed = $passFunctional
    pass_write_count = $passWriteCount
    pass_drain_count = $passDrainCount
    fail_status = $failStatus
    fail_functional_failed = $failFunctional
    fail_write_count = $failWriteCount
    fail_drain_count = $failDrainCount
    fail_drain_stage = $failDrainStage
    fail_drain_case = $failDrainCase
    fail_detail = $failDetail
} | ConvertTo-Json -Depth 8 -Compress
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
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["pass_status"] == "PASS"
    assert result["pass_functional_failed"] is False
    assert result["pass_drain_count"] == 0
    assert result["pass_write_count"] == 0
    assert result["fail_status"] == "FAIL"
    assert result["fail_functional_failed"] is True
    assert result["fail_write_count"] == 1
    assert result["fail_drain_count"] == 1
    assert result["fail_drain_stage"] == "demo-fail-error-drain"
    assert result["fail_drain_case"] == "demo-fail"
    assert "Post-case error queue contained" in result["fail_detail"]


@requires_windows
def test_shareable_large_numeric_arrays_keep_values_and_redact_strings(tmp_path):
    """Regression: live invocation capability ranges must not stall redaction."""
    private_root = tmp_path / "private"
    shareable_root = tmp_path / "shareable"
    private_root.mkdir()
    resource = "USB0::1::2::SYNTH12345::INSTR"
    body = r"""
$privateRoot = @PRIVATE@
$shareableRoot = @SHAREABLE@
$resource = @RESOURCE@
$repoRoot = @REPO@
$values = @(2..65536)
$raw = [ordered]@{
    ok = $true
    capabilities = [ordered]@{ average_counts = $values }
    resource = $resource
    mixed = @('safe', $resource, 42)
}
Write-Utf8NoBomText -LiteralPath (Join-Path $privateRoot 'cli-001.json') -Text (
    $raw | ConvertTo-Json -Depth 20 -Compress
)
Write-Utf8NoBomText -LiteralPath (Join-Path $privateRoot 'summary.md') -Text (
    '# Summary' + [Environment]::NewLine
)
$report = [ordered]@{
    status = 'passed'
    resource = $resource
    invocations = @()
}
$null = New-ShareableArtifactSet -PrivateReport $report `
    -PrivateSummaryPath (Join-Path $privateRoot 'summary.md') `
    -RunRoot (Split-Path -Parent $privateRoot) `
    -PrivateRoot $privateRoot -ShareableRoot $shareableRoot `
    -RepoRoot $repoRoot -Resource $resource
$mirror = Get-Content -LiteralPath (
    Join-Path $shareableRoot 'cli-001.json'
) -Raw | ConvertFrom-Json
$sharedReport = Get-Content -LiteralPath (
    Join-Path $shareableRoot 'report.json'
) -Raw | ConvertFrom-Json
[ordered]@{
    count = @($mirror.capabilities.average_counts).Count
    first = $mirror.capabilities.average_counts[0]
    last = $mirror.capabilities.average_counts[-1]
    resource = $mirror.resource
    mixed_resource = $mirror.mixed[1]
    report_resource = $sharedReport.resource
    summary_exists = Test-Path (Join-Path $shareableRoot 'summary.md')
} | ConvertTo-Json -Compress
"""
    replacements = {
        "@PRIVATE@": ps_quote(private_root),
        "@SHAREABLE@": ps_quote(shareable_root),
        "@RESOURCE@": ps_quote(resource),
        "@REPO@": ps_quote(REPO_ROOT),
    }
    for marker, value in replacements.items():
        body = body.replace(marker, value)
    result = run_live_cli_harness(body, timeout=120)
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout.strip().splitlines()[-1])
    assert values["count"] == 65535
    assert values["first"] == 2
    assert values["last"] == 65536
    assert values["resource"] == "<redacted-resource>"
    assert resource not in values["mixed_resource"]
    assert values["report_resource"] == "<redacted-resource>"
    assert values["summary_exists"] is True
