"""Representative trigger runner contracts, without instrument access."""
from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO

import pytest

from tests.tooling.test_live_tektronix_script import TARGETS, VISA_FAILURE, fake_run
from tests.tooling._live_script_test_support import (
    extract_live_cli_functions_ps, ps_quote, requires_windows, run_powershell,
)

pytestmark = [pytest.mark.windows_powershell, requires_windows]


@pytest.mark.parametrize("target", TARGETS)
def test_tektronix_special_triggers_execute_from_edge_and_restore(tmp_path, target):
    result, report = fake_run(tmp_path, target)
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    special = "trigger-runt" if target == TARGETS[0] else "trigger-tv"
    unsupported = "trigger-tv" if target == TARGETS[0] else "trigger-runt"
    assert cases[unsupported]["status"] == "N/A"
    for name in ("trigger-pulse-width", special):
        assert cases[name]["status"] == "PASS", cases[name]
        stages = [inv["stage"] for inv in report["invocations"]
                  if inv["stage"].startswith(name + "-")]
        assert stages == [name + suffix for suffix in (
            "-set", "-query", "-mode-query", "-status", "-edge-reset",
            "-edge-query", "-edge-mode-query", "-edge-status",
        )]
    assert not any(inv["arguments"][0] == "check-error" for inv in report["invocations"])


@pytest.mark.parametrize("responses,details", [
    ({"trigger-runt-set": VISA_FAILURE}, ("trigger-runt-set failed",)),
    ({"trigger-runt-query": {"ResultOverrides": {"high_level_volts": 2}}},
     ("high_level_volts readback differs",)),
    ({"trigger-runt-status": {"ResultOverrides": {"value": 4}}}, ("Native SESR",)),
    ({"trigger-runt-edge-query": {"ResultOverrides": {"slope": "negative"}}},
     ("Edge fixture restoration failed",)),
    ({"trigger-runt-query": VISA_FAILURE, "trigger-runt-edge-reset": VISA_FAILURE},
     ("trigger-runt-query failed", "Edge fixture restoration failed")),
])
def test_tektronix_failure_preserves_errors_and_resets_edge(tmp_path, responses, details):
    result, report = fake_run(tmp_path, TARGETS[0], stage_responses=responses)
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    case = cases["trigger-runt"]
    assert case["status"] == "FAIL"
    for detail in details:
        assert detail in case["detail"]
    assert any(inv["stage"] == "trigger-runt-edge-reset" for inv in report["invocations"])
    stages = [inv["stage"] for inv in report["invocations"]]
    assert stages.index("trigger-runt-status") < stages.index("trigger-runt-edge-reset")
    if "Edge fixture restoration failed" in details:
        assert not any(inv["stage"] == "trigger-pulse-width-set" for inv in report["invocations"])


KEYSIGHT_TRIGGERS = (
    "trigger-edge-settings", "trigger-common", "trigger-external", "trigger-pulse-width",
    "trigger-runt", "trigger-transition", "trigger-delay", "trigger-setup-hold",
    "trigger-edge-burst", "trigger-tv", "trigger-pattern", "trigger-or",
)
PLUS_TRIGGERS = {
    "trigger-runt", "trigger-transition", "trigger-delay", "trigger-setup-hold",
    "trigger-edge-burst", "trigger-tv", "trigger-or",
}


def keysight_fixture(model):
    from scopes_tool_cli.cli import main
    from scopes_tool_core.capabilities import capabilities_for_model_id

    sets = {
        "trigger-edge": ["--source-channel", "1", "--level", "1", "--slope", "positive"],
        "trigger-pulse-width": ["--channel", "1", "--polarity", "positive", "--qualifier", "greater-than", "--time-seconds", "0.000001", "--level-volts", "0"],
        "trigger-runt": ["--channel", "1", "--polarity", "positive", "--qualifier", "none", "--low-level-volts", "-0.5", "--high-level-volts", "0.5"],
        "trigger-transition": ["--channel", "1", "--slope", "positive", "--qualifier", "greater-than", "--time-seconds", "0.000001", "--low-level-volts", "-0.5", "--high-level-volts", "0.5"],
        "trigger-delay": ["--arm-channel", "1", "--arm-slope", "positive", "--trigger-channel", "2", "--trigger-slope", "positive", "--time-seconds", "0.000001", "--count", "2"],
        "trigger-setup-hold": ["--clock-channel", "1", "--data-channel", "2", "--slope", "positive", "--setup-time", "0.000000001", "--hold-time", "0.000000001"],
        "trigger-edge-burst": ["--source-channel", "1", "--slope", "positive", "--count", "2", "--idle-time", "0.000001", "--level-volts", "0"],
        "trigger-tv": ["--source-channel", "1", "--standard", "ntsc", "--mode", "all-lines", "--polarity", "positive"],
        "trigger-pattern": ["--pattern", "XXX1"], "trigger-or": ["--pattern", "XXXR"],
        "trigger-edge-coupling": ["--coupling", "dc"], "trigger-edge-reject": ["--reject", "off"],
        "trigger-sweep": ["--mode", "auto"], "trigger-noise-reject": ["--enabled", "true"],
        "trigger-hf-reject": ["--enabled", "false"], "external-trigger-range": ["--range-volts", "8"],
        "external-trigger-probe": ["--attenuation", "1"], "external-trigger-units": ["--units", "volts"],
        "trigger-edge-external-level": ["--level-volts", "0.25"],
    }
    payloads = {}
    for command, args in sets.items():
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main([command, *args, "--model", model, "--dry-run", "--json"])
        assert exit_code == 0, output.getvalue()[:500]
        payloads[command] = json.loads(output.getvalue())
        # The runner checks sent history; Core supplies the command dialect.
        payloads[command]["scpi"]["sent"] = payloads[command]["scpi"]["planned"]
    queries = {
        "trigger-pulse-width": {"mode": "glitch", "channel": 1, "polarity": "positive", "qualifier": "greater-than", "greater_than_seconds": 1e-6, "level_volts": 0},
        "trigger-runt": {"mode": "runt", "channel": 1, "polarity": "positive", "qualifier": "none", "low_level_volts": -0.5, "high_level_volts": 0.5},
        "trigger-transition": {"mode": "transition", "channel": 1, "slope": "positive", "qualifier": "greater-than", "time_seconds": 1e-6, "low_level_volts": -0.5, "high_level_volts": 0.5},
        "trigger-delay": {"mode": "delay", "arm_channel": 1, "trigger_channel": 2, "arm_slope": "positive", "trigger_slope": "positive", "count": 2, "time_seconds": 1e-6},
        "trigger-setup-hold": {"mode": "setup-hold", "clock_channel": 1, "data_channel": 2, "slope": "positive", "setup_time_seconds": 1e-9, "hold_time_seconds": 1e-9},
        "trigger-edge-burst": {"mode": "edge-burst", "source_channel": 1, "slope": "positive", "count": 2, "idle_time": 1e-6, "level_volts": 0},
        "trigger-tv": {"mode": "tv", "source_channel": 1, "standard": "ntsc", "tv_mode": "all-lines", "polarity": "positive"},
        "trigger-pattern": {"mode": "pattern", "pattern": "XXX1"}, "trigger-or": {"mode": "or", "pattern": "XXXR"},
        "trigger-mode": {"mode": "edge"}, "trigger-edge-source": {"source": "analog-channel", "source_channel": 1},
        "trigger-edge-slope": {"slope": "positive"}, "trigger-edge-level": {"level_volts": 1},
        "trigger-edge-coupling": {"coupling": "dc"}, "trigger-edge-reject": {"reject": "off"},
        "trigger-sweep": {"mode": "auto"}, "trigger-noise-reject": {"enabled": True}, "trigger-hf-reject": {"enabled": False},
        "external-trigger-settings": {"range_value": 8, "probe_attenuation": 1, "units": "volts"},
        "trigger-edge-external-level": {"level_volts": 0.25},
        "channel-summary": {"channels": [{"label": "", "bandwidth_limit": False, "impedance": "one_meg", "invert": False, "units": "volt", "vernier": False, "scale": 2, "range": 16, "offset": 0, "probe_ratio": 10, "probe_skew": 0}]},
        "display-label": {"display_label": False}, "display-persistence": {"mode": "minimum"},
        "display-intensity": {"value": 50}, "display-vectors": {"value": True}, "timebase-reference": {"reference": "center"},
    }
    return {"series": capabilities_for_model_id(model).series, "sets": payloads, "queries": queries}


def run_keysight_triggers(tmp_path, model, *, plus=True, failures=None, patches=None, edge_faults=()):
    fixture = keysight_fixture(model)
    fixture.update(plus=plus, failures=failures or [], patches=patches or {}, edge_faults=list(edge_faults))
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    body = extract_live_cli_functions_ps((
        "Invoke-BaselineCase", "Restore-EdgeTriggerBaseline", "Restore-InstrumentState",
        "Assert-ScpiSent", "Assert-ScpiSentPrefix", "Assert-NearlyEqual",
        "Assert-FiniteNumber", "ConvertTo-InvariantString",
    )) + f"$fixture = [IO.File]::ReadAllText({ps_quote(path)}) | ConvertFrom-Json\n" + r'''
$script:FunctionalFailed = $false
$script:SaveFixtureEstablished = $false
$script:Calls = New-Object System.Collections.Generic.List[object]
$script:Cases = [ordered]@{}
$script:Edge = @{ coupling = 'dc'; reject = 'off' }
$identity = [pscustomobject]@{ idn = @{ series = $fixture.series }; capabilities = @{ series = $fixture.series } }
$snapshot = [pscustomobject]@{
    ChannelDisplay = $true; ChannelCoupling = 'dc'; ChannelScale = 2; ChannelOffset = 0
    ChannelLabel = ''; ChannelProbeRatio = 10; ChannelBandwidthLimit = $false; ChannelImpedance = 'one_meg'
    ChannelInvert = $false; ChannelRange = 16; ChannelUnits = 'volt'; ChannelVernier = $false; ChannelProbeSkew = 0
    DisplayLabels = $false; DisplayIntensity = 50; DisplayVectors = $true; DisplayPersistenceSeconds = $null
    DisplayPersistenceMode = 'minimum'; TimebaseScale = 0.001; TimebasePosition = 0; TimebaseReference = 'center'
    TriggerSource = 'analog-channel'; TriggerSourceChannel = 1; TriggerSlope = 'positive'; TriggerLevel = 1
    TriggerHoldoffSeconds = 1e-6; AcquisitionType = 'normal'; AcquisitionCount = 16
    Is4000XSeries = ($fixture.series -eq '4000X'); MathEnhancementsInstalled = $fixture.plus
}
function Add-CaseResult {
    param($Name, $Passed, $Detail = '')
    $script:Cases[$Name] = @{ status = $(if ($Passed) { 'PASS' } else { 'FAIL' }); detail = $Detail }
}
function Add-NotApplicableCase {
    param($Name, $Detail)
    $script:Cases[$Name] = @{ status = 'N/A'; detail = $Detail }
}
function Add-Diagnostic { param($Name, $Message) }
function Drain-AfterFailure { param($Stage, $CaseName) }
function Invoke-LiveCli {
    param($Stage, $Command, $Arguments = @())
    $call = @{ stage = $Stage; command = $Command; arguments = @($Arguments)
        edge_before = @{ coupling = $script:Edge.coupling; reject = $script:Edge.reject } }
    $script:Calls.Add($call)
    if ($Stage -in $fixture.failures) { throw "$Stage failure" }
    $query = $Arguments -contains '--query' -or $Command -eq 'channel-summary'
    if ($query) {
        $result = $fixture.queries.PSObject.Properties[$Command].Value
        if ($Command -eq 'trigger-edge-coupling') { $result = @{ coupling = $script:Edge.coupling } }
        if ($Command -eq 'trigger-edge-reject') { $result = @{ reject = $script:Edge.reject } }
        $payload = [pscustomobject]@{ ok = $true; result = $result; scpi = [pscustomobject]@{ sent = @(':TRIGger:EDGE:LEVel? EXTernal') } }
    } else {
        if ($Command -eq 'trigger-edge-coupling' -and
            -not ($Stage -eq 'restore-trigger-edge-coupling' -and 'restore-coupling' -in $fixture.edge_faults)) {
            $script:Edge.coupling = $Arguments[1]
        }
        if ($Command -eq 'trigger-edge-reject') {
            $script:Edge.reject = $Arguments[1]
            if ($Stage -eq 'trigger-edge-reject-set' -and 'reject-coupling' -in $fixture.edge_faults) {
                $script:Edge.coupling = 'ac'
            }
        }
        $set = $fixture.sets.PSObject.Properties[$Command]
        $payload = if ($null -ne $set) { $set.Value } else { @{ ok = $true } }
    }
    $patch = $fixture.patches.PSObject.Properties[$Stage]
    if ($null -ne $patch) {
        $payload = ($payload | ConvertTo-Json -Depth 20 | ConvertFrom-Json)
        foreach ($field in $patch.Value.PSObject.Properties) {
            $payload.result | Add-Member -Force -NotePropertyName $field.Name -NotePropertyValue $field.Value
        }
    }
    $call.edge_after = @{ coupling = $script:Edge.coupling; reject = $script:Edge.reject }
    return $payload
}
# Execute the real trigger snapshot gate and its actual field projections.
$setup = @($ast.FindAll({ param($n)
    $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $n.Left.Extent.Text -in @('$is2000XSeries', '$is3000XSeries', '$is4000XSeries', '$triggerSettingsApplicable')
}, $true) | ForEach-Object { $_.Extent.Text }) -join "`n"
$capture = $ast.Find({ param($n)
    $n -is [System.Management.Automation.Language.IfStatementAst] -and
    $n.Extent.Text.Contains('snapshot-trigger-edge-coupling')
}, $true)
$fields = $ast.Find({ param($n)
    $n -is [System.Management.Automation.Language.HashtableAst] -and
    $n.Extent.Text.Contains('TriggerSettingsCaptured =')
}, $true)
$projections = @($fields.KeyValuePairs | Where-Object {
    $_.Item1.Extent.Text -match '^(TriggerSettingsCaptured|TriggerEdgeCoupling|TriggerEdgeReject|TriggerSweep|TriggerNoiseReject|TriggerHfReject|ExternalTrigger.*)$'
} | ForEach-Object { $_.Item1.Extent.Text + ' = ' + $_.Item2.Extent.Text }) -join "`n"
$snapshotFile = Join-Path $PSScriptRoot 'snapshot.ps1'
[IO.File]::WriteAllText($snapshotFile, ($setup + "`n" + $capture.Extent.Text + "`n" +
    '$captured = [pscustomobject]@{' + "`n" + $projections + "`n}"))
try {
    . $snapshotFile
    foreach ($field in $captured.PSObject.Properties) {
        $snapshot | Add-Member -NotePropertyName $field.Name -NotePropertyValue $field.Value
    }
} catch {
    $script:FunctionalFailed = $true
    Add-CaseResult snapshot $false $_.Exception.Message
}
if (-not $script:FunctionalFailed) {
    $names = @('trigger-edge-settings', 'trigger-common', 'trigger-external', 'trigger-pulse-width',
        'trigger-runt', 'trigger-transition', 'trigger-delay', 'trigger-setup-hold',
        'trigger-edge-burst', 'trigger-tv', 'trigger-pattern', 'trigger-or')
    $blocks = New-Object System.Collections.Generic.List[string]
    foreach ($name in $names) {
        $call = $ast.Find({ param($n)
            $n -is [System.Management.Automation.Language.CommandAst] -and
            $n.GetCommandName() -eq 'Invoke-BaselineCase' -and $n.Extent.Text.Contains('-Name "' + $name + '"')
        }, $true)
        $gate = $call.Parent
        while ($gate -isnot [System.Management.Automation.Language.IfStatementAst]) { $gate = $gate.Parent }
        $blocks.Add($gate.Extent.Text)
    }
    $casesFile = Join-Path $PSScriptRoot 'cases.ps1'
    [IO.File]::WriteAllLines($casesFile, $blocks.ToArray())
    # Start away from the snapshot so setters must change the fake instrument.
    $script:Edge.coupling = 'ac'; $script:Edge.reject = 'hf'
    . $casesFile
    $script:Edge.coupling = 'ac'; $script:Edge.reject = 'hf'
    try { Restore-InstrumentState -Snapshot $snapshot; Add-CaseResult restore $true }
    catch { Add-CaseResult restore $false $_.Exception.Message }
}
@{ cases = $script:Cases; calls = $script:Calls.ToArray(); snapshot = $snapshot } | ConvertTo-Json -Depth 20 -Compress
'''
    result = run_powershell(body, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("model", ["keysight-dsox2004a", "keysight-dsox3024a", "keysight-dsox4024a"])
def test_keysight_trigger_groups_snapshot_readback_and_restore(tmp_path, model):
    report = run_keysight_triggers(tmp_path, model)
    assert set(report["cases"]) == {*KEYSIGHT_TRIGGERS, "restore"}
    assert all(case["status"] == "PASS" for case in report["cases"].values()), report["cases"]
    snapshot = report["snapshot"]
    assert snapshot["TriggerSettingsCaptured"] is True
    assert snapshot["ExternalTriggerLevel"] == 0.25
    calls = report["calls"]
    for name in ("trigger-pulse-width", *PLUS_TRIGGERS, "trigger-pattern"):
        assert any(c["stage"] == name + "-set" for c in calls)
        assert any(c["stage"] == name + "-query" for c in calls)
        assert any(c["stage"] == name + "-edge-reset-mode-query" for c in calls)
    for command in ("trigger-edge-coupling", "trigger-edge-reject", "trigger-sweep", "trigger-noise-reject", "trigger-hf-reject",
                    "external-trigger-range", "external-trigger-probe", "external-trigger-units", "trigger-edge-external-level"):
        assert any(c["stage"] == "restore-" + command for c in calls)
    external = next(c for c in calls if c["stage"] == "external-trigger-level-set")
    assert external["arguments"] == ["--level-volts", "0.25"]


def test_keysight_missing_plus_is_explicit_na(tmp_path):
    report = run_keysight_triggers(tmp_path, "keysight-dsox2004a", plus=False)
    for name, case in report["cases"].items():
        assert case["status"] == ("N/A" if name in PLUS_TRIGGERS else "PASS"), case
    assert not PLUS_TRIGGERS.intersection(c["command"] for c in report["calls"])


@pytest.mark.parametrize("failures,patches,details", [
    (["trigger-pulse-width-set"], {}, ["trigger-pulse-width-set failure"]),
    ([], {"trigger-pulse-width-query": {"greater_than_seconds": 2e-6}}, ["readback"]),
    (["trigger-pulse-width-query", "trigger-pulse-width-edge-reset"], {},
     ["trigger-pulse-width-query failure", "Edge fixture restoration failed"]),
])
def test_keysight_trigger_failure_resets_edge_and_stops_cases(tmp_path, failures, patches, details):
    report = run_keysight_triggers(tmp_path, "keysight-dsox3024a", failures=failures, patches=patches)
    case = report["cases"]["trigger-pulse-width"]
    assert case["status"] == "FAIL"
    for detail in details:
        assert detail in case["detail"]
    assert any(c["stage"] == "trigger-pulse-width-edge-reset" for c in report["calls"])
    assert "trigger-runt" not in report["cases"]
    assert report["cases"]["restore"]["status"] == "PASS"


def test_keysight_snapshot_failure_prevents_setters(tmp_path):
    report = run_keysight_triggers(tmp_path, "keysight-dsox2004a", failures=["snapshot-external-trigger"])
    assert report["cases"]["snapshot"]["status"] == "FAIL"
    assert all("--query" in c["arguments"] for c in report["calls"])


def test_keysight_restore_readback_failure_cannot_pass(tmp_path):
    report = run_keysight_triggers(tmp_path, "keysight-dsox2004a", patches={
        "restore-external-trigger-level-query": {"level_volts": 0.5},
    })
    assert report["cases"]["restore"]["status"] == "FAIL"
    assert "Restored external level" in report["cases"]["restore"]["detail"]


@pytest.mark.parametrize("edge_faults,edge_status,restore_status", [
    ((), "PASS", "PASS"),
    (("reject-coupling",), "FAIL", "PASS"),
    (("restore-coupling",), "PASS", "FAIL"),
    (("reject-coupling", "restore-coupling"), "FAIL", "FAIL"),
])
def test_keysight_edge_final_state_and_restore(tmp_path, edge_faults, edge_status, restore_status):
    report = run_keysight_triggers(tmp_path, "keysight-dsox3024a", edge_faults=edge_faults)
    edge = report["cases"]["trigger-edge-settings"]
    restore = report["cases"]["restore"]
    assert edge["status"] == edge_status, edge
    assert restore["status"] == restore_status, restore
    calls = {call["stage"]: call for call in report["calls"]}
    for prefix in ("", "restore-"):
        coupling_set = calls[prefix + "trigger-edge-coupling" + ("-set" if not prefix else "")]
        reject_set = calls[prefix + "trigger-edge-reject" + ("-set" if not prefix else "")]
        assert coupling_set["edge_before"] == {"coupling": "ac", "reject": "hf"}
        assert reject_set["edge_after"]["reject"] == "off"
        expected = "ac" if ("restore-coupling" if prefix else "reject-coupling") in edge_faults else "dc"
        query = calls[prefix + "trigger-edge-coupling-query"]
        assert query["edge_after"] == {"coupling": expected, "reject": "off"}
    if edge_status == "FAIL":
        assert "Edge coupling/reject readback" in edge["detail"]
        assert "trigger-common" not in report["cases"]
    if restore_status == "FAIL":
        assert "Restored common trigger settings" in restore["detail"]
