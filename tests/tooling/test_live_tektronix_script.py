"""Hardware-free checks for Tektronix live validation runners."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.tooling._tektronix_live_test_support import (
    ROOT, TARGETS, VISA_FAILURE, fake_run, fake_workflow_run,
    requires_windows, run_script,
)


@pytest.fixture(scope="module", params=TARGETS)
def baseline_tektronix_run(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory):
    """Reuse identical, immutable happy-path reports across independent contract assertions."""
    target = request.param
    root = tmp_path_factory.mktemp(f"tektronix-baseline-{target.removeprefix('tektronix-')}")
    result, report = fake_run(root, target)
    return target, result, report



@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("waveform_format,expected_status", [("internal", "N/A"), ("csv", "PASS")])
def test_empty_label_and_waveform_format_roundtrip(
    tmp_path: Path, waveform_format: str, expected_status: str,
) -> None:
    # Run only these two round trips, using the production process transport
    # and a fake CLI that rejects missing empty arguments or unsupported setters.
    package = tmp_path / "scopes_tool_cli"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(
        "import json, sys\n"
        "command = sys.argv[1]\n"
        "if command == 'channel-label':\n"
        " if '--query' not in sys.argv:\n"
        "  assert sys.argv[sys.argv.index('--text') + 1] == ''\n"
        " result = {'text': ''}\n"
        "elif command == 'save-waveform-format':\n"
        " if '--query' not in sys.argv:\n"
        "  assert sys.argv[sys.argv.index('--format') + 1] == 'csv'\n"
        f" result = {{'format': {waveform_format!r}}}\n"
        "else:\n"
        " raise AssertionError(command)\n"
        "print(json.dumps({'ok': True, 'result': result}))\n",
        encoding="utf-8",
    )
    harness = tmp_path / "roundtrip.ps1"
    harness.write_text(
        r'''param([string]$RepoRoot, [string]$PythonPath, [string]$RunRoot)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $RepoRoot "scripts/_validation_helpers.ps1")
. (Join-Path $RepoRoot "scripts/_live_tektronix_helpers.ps1")
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $RepoRoot "scripts/_live_tektronix_helpers.ps1"), [ref]$tokens, [ref]$errors
)
if ($errors.Count) { throw $errors[0].Message }
foreach ($name in @("Invoke-Cli", "Get-Readback", "Test-ReadbackEqual", "Assert-ReadbackEqual", "Invoke-RoundTrip")) {
    $function = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
    }, $true)
    if ($null -eq $function) { throw "Missing function $name" }
    Invoke-Expression $function.Extent.Text
}
$pythonPath = $PythonPath
$DebugArtifacts = $false
$script:RunPaths = [pscustomobject]@{ Private = $RunRoot }
$script:LiveConnectionArguments = @()
$script:CliInvocationIndex = 0
$script:HardwareTouched = $false
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:Cases = New-Object System.Collections.Generic.List[object]
function Add-Case {
    param([string]$Name, [string]$Status, [string]$Detail)
    $script:Cases.Add([pscustomobject]@{ name = $Name; status = $Status; detail = $Detail })
}
Invoke-RoundTrip "channel-label" "channel-label" @("--channel", "1") "text" "--text"
Invoke-RoundTrip "save-waveform-format" "save-waveform-format" @() "format" "--format" @("csv")
@{ cases = $script:Cases.ToArray(); invocations = $script:Invocations.ToArray() } | ConvertTo-Json -Depth 20 -Compress
''', encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    result = run_script(
        "-RepoRoot", str(ROOT), "-PythonPath", sys.executable, "-RunRoot", str(tmp_path),
        script=harness, env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    label, waveform = report["cases"]
    assert label["status"] == "PASS", label
    assert waveform["status"] == expected_status, waveform
    invocations = report["invocations"]
    label_sets = [inv for inv in invocations if inv["stage"] in {"channel-label-same-value", "channel-label-restore"}]
    assert len(label_sets) == 2
    for invocation in label_sets:
        arguments = invocation["arguments"]
        assert arguments[arguments.index("--text") + 1] == ""
        assert invocation["exit_code"] == 0
    waveform_invocations = [inv for inv in invocations if inv["arguments"][0] == "save-waveform-format"]
    if waveform_format == "internal":
        assert "outside supported acceptance precondition" in waveform["detail"]
        assert [inv["stage"] for inv in waveform_invocations] == ["save-waveform-format-before"]
        assert all("--format" not in inv["arguments"] for inv in waveform_invocations)
    else:
        assert len(waveform_invocations) == 5



@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("target", (*TARGETS, "all", "keysight-dsox4034a"))
def test_exact_targets_and_explicit_resource(target: str) -> None:
    args = ["-Target", target, "-Connection", "usb", "-Resource", "TCPIP0::example::INSTR"]
    result = run_script(*args)
    assert result.returncode != 0
    if target in TARGETS:
        assert "does not match resource" in result.stderr
    elif target == "all":
        assert "not supported for live validation" in result.stderr
    else:
        assert "does not match resource" in result.stderr


@pytest.mark.windows_powershell
@requires_windows
def test_missing_resource_rejected_before_any_live_invocation() -> None:
    result = run_script("-Target", TARGETS[0], "-Connection", "usb")
    assert result.returncode != 0
    assert "Resource" in result.stderr


@pytest.mark.windows_powershell
@requires_windows
def test_backend_and_output_root_are_bounded() -> None:
    base = ["-Target", TARGETS[0], "-Connection", "usb", "-Resource", "USB0::FAKE::INSTR"]
    backend = run_script(*base, "-Backend", "@other")
    assert backend.returncode != 0
    assert "Unsupported backend" in backend.stderr
    outside = run_script(*base, "-OutputRoot", str(ROOT / "docs"))
    assert outside.returncode != 0
    assert "must stay under repository .tmp_tests" in outside.stderr


@pytest.mark.windows_powershell
@requires_windows
def test_identity_mismatch_stops_before_other_cases(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], live_model=TARGETS[1],
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert report["hardware_touched"] is True
    assert [(case["name"], case["status"]) for case in report["cases"]] == [
        ("preflight", "PASS"), ("identify", "FAIL")
    ]
    assert [inv["arguments"][0] for inv in report["invocations"]] == ["identify", "identify"]
    assert "--simulate" in report["invocations"][0]["arguments"]
    assert "--resource" in report["invocations"][1]["arguments"]
    assert all(inv["arguments"][0] == "identify" for inv in report["invocations"])


@pytest.mark.windows_powershell
@requires_windows
def test_physical_model_spacing_passes_identity_gate(tmp_path: Path) -> None:
    # Real Tektronix instruments report "TBS 1052B" while the target profile
    # declares "TBS1052B"; the normalized token match must accept it.
    result, report = fake_run(
        tmp_path, TARGETS[2], live_model_name="TBS 1052B",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["preflight"]["status"] == "PASS"
    assert cases["identify"]["status"] == "PASS", cases["identify"]
    assert not [case for case in report["cases"] if case["status"] == "FAIL"]
    assert report["status"] == "passed"
    assert [inv["arguments"][0] for inv in report["invocations"]][:2] == [
        "identify", "identify"
    ]



CASE_STATUS_PATTERN = re.compile(r"^(PASS|FAIL|N/A|NOT TESTED)\s+\[live\]\[tektronix\] (\S+)\s*$")


def printed_case_details(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    """Return the console Detail printed for the first status line of each case.

    The trailing Summary reprints every case status without a Detail, so only the
    first occurrence of each case name carries the runner's Add-Case output.
    """
    lines = [line.rstrip() for line in result.stdout.splitlines()]
    printed: dict[str, str] = {}
    for index, line in enumerate(lines):
        match = CASE_STATUS_PATTERN.match(line)
        if match is None or match.group(2) in printed:
            continue
        detail: list[str] = []
        for candidate in lines[index + 1:]:
            if not candidate.strip():
                if detail:
                    break
                continue
            if not candidate.startswith(" "):
                break
            detail.append(candidate.strip())
        printed[match.group(2)] = " ".join(detail)
    return printed


@pytest.mark.windows_powershell
@requires_windows
def test_fail_detail_is_printed_and_carries_cli_error_fields(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], cursor_error=("OscilloscopeError", "Cursor X setter failed"),
    )
    assert result.returncode != 0
    assert report["status"] == "failed"
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["cursor-set"]["status"] == "FAIL"

    detail = cases["cursor-set"]["detail"]
    # The CLI error type and message must survive instead of being masked by the
    # exit-code and artifact-path summary.
    assert "OscilloscopeError: Cursor X setter failed" in detail
    assert "exit 1" in detail and "timeout=False" in detail

    lines = [line.strip() for line in result.stdout.splitlines()]
    status_index = next(
        index for index, line in enumerate(lines)
        if line.startswith("FAIL") and "[live][tektronix] cursor-set" in line
    )
    assert lines[status_index + 1] == detail


@pytest.mark.windows_powershell
@requires_windows
def test_math_state_outside_public_subset_is_na(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], math_error=("OscilloscopeError", "Unsupported Tek Math expression: 'FFT'"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["math-operator"]["status"] == "N/A"
    assert report["status"] == "passed"
    calls = [inv for inv in report["invocations"] if inv["arguments"][0] == "math-operator"]
    assert len(calls) == 1
    assert "--query" in calls[0]["arguments"]
    assert calls[0]["result"] == "N/A"


@pytest.mark.windows_powershell
@requires_windows
def test_tbs2074_cursor_configuration_actions_cover_x_y_and_screen(tmp_path: Path) -> None:
    result, report = fake_run(tmp_path, TARGETS[0])
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["cursor-set"]["status"] == "PASS"
    assert cases["cursor-set-y"]["status"] == "PASS"
    assert cases["cursor-set-screen"]["status"] == "PASS"
    calls = [
        inv["arguments"]
        for inv in report["invocations"]
        if inv["arguments"][0] == "cursor" and "--query" not in inv["arguments"]
    ]
    assert any("--x1" in args and "--y1" not in args for args in calls)
    assert any("--y1" in args and "--x1" not in args for args in calls)
    assert any("--x1" in args and "--y1" in args for args in calls)
    assert any("--off" in args for args in calls)


@pytest.mark.windows_powershell
@requires_windows
def test_tbs2074_cursor_failure_stops_later_cursor_mutations(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path,
        TARGETS[0],
        cursor_error=("OscilloscopeError", "Cursor X setter failed"),
    )
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["cursor-set"]["status"] == "FAIL"
    assert cases["cursor-set-y"]["status"] == "NOT TESTED"
    assert cases["cursor-set-screen"]["status"] == "NOT TESTED"
    setters = [
        inv["arguments"]
        for inv in report["invocations"]
        if inv["arguments"][0] == "cursor" and "--query" not in inv["arguments"]
    ]
    assert sum("--x1" in args for args in setters) == 1
    assert not any("--y1" in args for args in setters)


@pytest.mark.windows_powershell
@requires_windows
def test_live_runner_rejects_stale_unsupported_operation_policy(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path,
        TARGETS[1],
        core_supported_operations=("sample-rate",),
    )
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["sample-rate"]["status"] == "FAIL"
    assert "runner drift" in cases["sample-rate"]["detail"].lower()
    assert report["status"] == "failed"


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("target", TARGETS[1:2])
def test_cursor_seconds_prerequisite_is_na(tmp_path: Path, target: str) -> None:
    result, report = fake_run(
        tmp_path, target, cursor_error=("ParameterValidationError", "X cursors require existing seconds units"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["cursor-set"]["status"] == "N/A"
    assert cases["cursor-off"]["status"] == "PASS"
    assert report["status"] == "passed"
    calls = [inv for inv in report["invocations"] if inv["arguments"][0] == "cursor"]
    setters = [inv for inv in calls if "--query" not in inv["arguments"]]
    assert len(setters) == 3  # Rejected X, independent Y, then standard OFF.
    assert "--x1" in setters[0]["arguments"]
    assert setters[0]["result"] == "N/A"
    assert "--y1" in setters[1]["arguments"]
    assert "--off" in setters[2]["arguments"]
    assert cases["cursor-set-y"]["status"] == "PASS"
    assert "--auto-timebase" not in setters[0]["arguments"]
    assert "not restored" in result.stdout


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize(("command", "error"), [
    ("math-operator", ("OscilloscopeError", "Math query failed")),
    ("cursor", ("ParameterValidationError", "X cursor position is outside the graticule")),
])
def test_unrelated_math_or_cursor_errors_remain_fail(
    tmp_path: Path, command: str, error: tuple[str, str],
) -> None:
    errors = {"math_error" if command == "math-operator" else "cursor_error": error}
    result, report = fake_run(
        tmp_path, TARGETS[1], subprocess_cli=command == "math-operator", **errors,
    )
    assert result.returncode != 0
    assert report["status"] == "failed"
    assert report["summary_counts"]["failed"] == 1
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["math-operator" if command == "math-operator" else "cursor-set"]["status"] == "FAIL"


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("target", TARGETS[1:2])
@pytest.mark.parametrize("mismatch", (False, True))
def test_vectors_on_requires_readback(tmp_path: Path, target: str, mismatch: bool) -> None:
    result, report = fake_run(tmp_path, target, vectors_on=True, vectors_mismatch=mismatch)
    assert (result.returncode != 0) == mismatch, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["display-vectors-query"]["status"] == "PASS"
    assert cases["display-vectors-on"]["status"] == ("FAIL" if mismatch else "PASS")
    assert report["status"] == ("failed" if mismatch else "passed")
    assert report["summary_counts"]["failed"] == int(mismatch)
    calls = [inv["arguments"] for inv in report["invocations"] if inv["arguments"][0] == "display-vectors"]
    assert len(calls) == 3
    assert "--query" in calls[0]
    assert "--on" in calls[1]
    assert "--query" in calls[2]


@pytest.mark.windows_powershell
@requires_windows
def test_default_case_flow_with_fake_cli(baseline_tektronix_run) -> None:
    target, result, report = baseline_tektronix_run
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["identify"]["status"] == "PASS"
    assert cases["channel-display"]["status"] == "PASS"
    if target == TARGETS[0]:
        assert cases["channel-probe-skew"]["status"] == "PASS"
        assert cases["display-vectors"]["status"] == "N/A"
    else:
        assert cases["display-vectors-query"]["status"] == "PASS"
        assert cases["display-vectors-on"]["status"] == "N/A"
    assert cases["timebase-position"]["status"] == "PASS"
    assert cases["trigger-mode"]["status"] == "PASS"
    for name in ("channel-units", "math-display", "math-operator",
                     "cursor-query", "trigger-edge", "trigger-edge-source", "trigger-edge-slope",
                     "trigger-edge-coupling", "acquisition-points", "record-length"):
        assert cases[name]["status"] == "PASS", cases[name]
    assert cases["display-persistence"]["status"] == (
        "N/A" if target == TARGETS[0] else "PASS"
    ), cases["display-persistence"]
    assert "autoscale" not in cases
    assert cases["setup-save"]["status"] == ("PASS" if target == TARGETS[0] else "N/A")
    assert cases["final-standard-event"]["status"] == "PASS"
    assert report["invocations"][-1]["arguments"][0] == "system-standard-event"
    assert not [case for case in report["cases"] if case["status"] == "FAIL"]
    assert report["status"] == "passed"
    assert all(inv["arguments"][0] != "autoscale" for inv in report["invocations"])
    unsupported = ({"trigger-tv", "save-image-ink-saver", "display-vectors"}
                   if target == TARGETS[0] else
                   {"sample-rate", "channel-label", "channel-probe-skew",
                    "trigger-edge-level", "trigger-runt", "save-image-format", "save-waveform-format", "save-image-ink-saver"})
    assert not unsupported.intersection(inv["arguments"][0] for inv in report["invocations"])
    commands = [inv["arguments"][0] for inv in report["invocations"]]
    assert commands.index("trigger-mode") < commands.index("trigger-edge-source")
    for name in ("sample-rate", "save-image-format", "save-waveform-format", "save-image-ink-saver"):
        assert cases[name]["status"] == ("N/A" if name in unsupported else "PASS")


@pytest.mark.windows_powershell
@requires_windows
def test_standard_execution_list_uses_core_capabilities(baseline_tektronix_run) -> None:
    from scopes_tool_core.capabilities import capabilities_for_model_id
    target, result, report = baseline_tektronix_run
    caps = capabilities_for_model_id(target)
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    calls = [inv["arguments"] for inv in report["invocations"] if "--simulate" not in inv["arguments"]]
    for name in ("cursor-set", "cursor-set-y", "cursor-off", "measure-install", "measure-clear", "run", "single",
                 "force-trigger", "stop-acquisition", "capture-byte", "single-wait-natural", "single-wait-force"):
        assert cases[name]["status"] == "PASS", cases[name]
    commands = [call[0] for call in calls]
    assert {"run", "stop-acquisition", "single", "force-trigger", "capture", "screenshot"} <= set(commands)
    waits = [call for call in calls if call[0] == "single-wait"]
    assert len(waits) == 2
    assert sum("--force-trigger-on-timeout" in call for call in waits) == 1
    measurements = [call for call in calls if call[0] == "measure"]
    assert [call[call.index("--item") + 1] for call in measurements] == list(caps.measurement_items)
    for item in caps.measurement_items:
        assert cases[f"measure-{item}"]["status"] == "PASS"
    capture = next(call for call in calls if call[0] == "capture")
    assert capture[capture.index("--format") + 1] == "byte"
    assert capture[capture.index("--points") + 1] == "1000"
    assert "--csv" in capture and "--meta" in capture
    assert any(call[0] == "cursor" and "--x1" in call for call in calls)
    image_format = caps.screenshot_formats[0]
    assert cases[f"screenshot-{image_format}"]["status"] == "PASS"
    image = next(call for call in calls if call[0] == "screenshot")
    if image_format != "png":
        assert image[image.index("--format") + 1] == image_format
    storage = {"setup-save", "setup-recall", "reference-save", "reference-display", "reference-query",
               "save-image", "save-waveform", "save-pwd", "save-image-ink-saver"}
    if target == TARGETS[0]:
        assert storage - {"save-image-ink-saver"} <= set(commands)
        for call in calls:
            if call[0] in {"setup-save", "setup-recall", "reference-save", "reference-display", "reference-query"}:
                assert call[call.index("--slot") + 1] == "1"
            if call[0] in {"save-image", "save-waveform"}:
                filename = call[call.index("--filename") + 1]
                assert re.fullmatch(r"st[0-9a-f]{6}\.(png|csv)", filename)
                assert filename.endswith(".png" if call[0] == "save-image" else ".csv")
        for name in ("cursor-set-y", "cursor-set-screen"):
            assert cases[name]["status"] == "PASS"
        stages = [inv["stage"] for inv in report["invocations"]]
        setup_stages = [stage for stage in stages if stage.startswith("setup-")]
        assert setup_stages == [
            "setup-slot-label-before", "setup-save", "setup-slot-label-change",
            "setup-slot-label-changed", "setup-recall", "setup-slot-label-restored",
        ]
        assert cases["setup-slot-lifecycle"]["status"] == "PASS"
        assert cases["reference-lifecycle"]["status"] == "PASS"
        assert stages.index("reference-save") < stages.index("reference-display") < stages.index("reference-display-after") < stages.index("reference-query-after-save") < stages.index("reference-display-cleanup")
        assert not {"reference-label", "reference-clear"}.intersection(commands)
        functions = {call[call.index("--function") + 1] for call in calls if call[0] == "cursor" and "--function" in call}
        assert functions == set(caps.cursor_functions)
    else:
        assert not storage.intersection(commands)
        assert cases["cursor-set-screen"]["status"] == "N/A"
        for name in storage:
            assert cases[name]["status"] == "N/A"
    assert "Stop command succeeded; native status clean" in " ".join(report["diagnostics"]["acquisition-final-state"])
    assert cases["capture-hidden-channel"]["status"] == "N/A"


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize(("status_command", "expected_failure"), [
    ("run", "run"),
    ("stop-acquisition", "stop-acquisition"),
])
def test_acquisition_rejects_dirty_native_status_and_attempts_stop(
    tmp_path: Path, status_command: str, expected_failure: str,
) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], native_status_command=status_command, native_status_value=4, native_status_raw="4",
    )
    assert result.returncode != 0
    assert report["status"] == "failed"
    cases = {case["name"]: case for case in report["cases"]}
    assert cases[expected_failure]["status"] == "FAIL"
    commands = [inv["arguments"][0] for inv in report["invocations"]]
    assert commands.count("run") == 1
    assert commands.count("stop-acquisition") == 1
    assert commands.index("stop-acquisition") > commands.index("run")
    assert cases["stop-acquisition"]["status"] == ("FAIL" if expected_failure == "stop-acquisition" else "PASS")


@pytest.mark.windows_powershell
@requires_windows
def test_private_and_shareable_reports_keep_common_schema(tmp_path: Path) -> None:
    result, private_report = fake_run(tmp_path, TARGETS[0])
    assert result.returncode == 0, result.stdout + result.stderr
    run_dir = ROOT / private_report["run_root"]
    private_path = run_dir / "private" / "report.json"
    shareable_path = run_dir / "shareable" / "report.json"
    assert private_path.is_file()
    assert shareable_path.is_file()
    shared_report = json.loads(shareable_path.read_text(encoding="utf-8"))
    assert private_report["status"] == shared_report["status"] == "passed"
    assert private_report["summary_counts"] == shared_report["summary_counts"]
    assert shared_report["resource"] == "<redacted-resource>"
    assert shared_report["artifact_paths"]["report"] == "shareable/report.json"
    assert shared_report["artifact_paths"]["summary"] == "shareable/summary.md"
    assert "USB0::FAKE::INSTR" not in shareable_path.read_text(encoding="utf-8")


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("debug", (False, True), ids=("minimal", "debug"))
@pytest.mark.parametrize("failed", (False, True), ids=("pass", "fail"))
def test_tektronix_cli_artifact_retention(tmp_path: Path, debug: bool, failed: bool) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], debug=debug, live_model=TARGETS[1] if failed else None,
    )
    assert result.returncode == (1 if failed else 0), result.stdout + result.stderr
    assert report["status"] == ("failed" if failed else "passed")
    root = ROOT / report["run_root"]
    files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    raw = (root / "shareable/report.json").read_text(encoding="utf-8")
    shared = json.loads(raw)
    assert shared["artifact_mode"] == ("debug" if debug else "minimal")
    assert shared["debug_artifacts_retained"] is debug
    assert shared["private_raw_artifacts_retained"] is debug
    assert shared["summary_counts"] == report["summary_counts"]
    assert "USB0::FAKE::INSTR" not in raw
    if debug:
        assert "private/report.json" in files and "private/summary.md" in files
        assert len(files) > 4
    else:
        assert files == {"shareable/report.json", "shareable/summary.md"}
        assert all(inv[field] is None for inv in shared["invocations"] for field in ("stdout", "stderr", "json"))


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("target", TARGETS)
def test_workflow_simulator_happy_path_uses_core_identity(tmp_path: Path, target: str) -> None:
    result, report = fake_workflow_run(tmp_path, target, "happy")
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["status"] == "passed"
    cases = {case["name"]: case for case in report["cases"]}
    for name in (
        "preflight", "identity", "target-model-match", "acquisition-precondition",
        "measure-sweep", "measure-log", "measure-until", "measure-until-timeout",
        "capture-batch", "capture-until", "capture-monitor", "triggered-measure-loop",
        "triggered-capture-series", "sequence", "cleanup",
    ):
        assert cases[name]["status"] == "PASS", cases[name]
    sweep = next(inv for inv in report["invocations"] if inv["stage"] == "measure-sweep")
    sweep_items = sweep["arguments"][sweep["arguments"].index("--items") + 1].split(",")
    if target == TARGETS[1]:
        assert "vrms" not in sweep_items
    assert all("--live" not in inv["arguments"] for inv in report["invocations"])

    timeout = next(inv for inv in report["invocations"] if inv["stage"] == "measure-until-timeout")
    timeout_payload = json.loads((ROOT / timeout["json"]).read_text(encoding="utf-8"))
    status = timeout_payload["result"]["post_command_status"]
    assert status["source"] == "tektronix-sesr"
    assert status["complete"] is True
    assert status["is_error"] is False
    assert status["destructive_read"] is True
    assert status["value"] == 0
    assert status["raw"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("target", TARGETS[1:2])
def test_workflow_measurement_settings_conflict_is_actionable(
    tmp_path: Path, target: str,
) -> None:
    result, report = fake_workflow_run(tmp_path, target, "measurement-settings-conflict")
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["measure-sweep"]["status"] == "FAIL"
    detail = cases["measure-sweep"]["detail"]
    assert "Tektronix native status 16" in detail
    assert "event 221: Settings conflict" in detail
    assert "Trigger View is OFF" in detail
    assert "display format is YT" in detail
    assert "not in Scan mode" in detail
    assert cases["cleanup"]["status"] == "PASS"
    stages = [inv["stage"] for inv in report["invocations"]]
    assert stages.index("measure-sweep") < stages.index("cleanup-acquisition-stop-acquisition")


@pytest.mark.windows_powershell
@requires_windows
def test_workflow_run_failure_still_stops_acquisition(tmp_path: Path) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[0], "dirty-run")
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["acquisition-precondition"]["status"] == "FAIL"
    assert "native command status" in cases["acquisition-precondition"]["detail"]
    assert cases["cleanup"]["status"] == "PASS"
    stages = [inv["stage"] for inv in report["invocations"]]
    assert stages.index("acquisition-precondition-run") < stages.index("cleanup-acquisition-stop-acquisition")


@pytest.mark.windows_powershell
@requires_windows
def test_expected_timeout_still_rejects_dirty_native_status(tmp_path: Path) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[0], "dirty-timeout")
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["measure-until-timeout"]["status"] == "FAIL"
    assert "error-bearing native measurement status" in cases["measure-until-timeout"]["detail"]
    assert cases["cleanup"]["status"] == "PASS"


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("rows,points,status", [(("0,0.5",), None, "PASS"), (("0,0.5",), 2, "FAIL"), (("NaN,0.5",), None, "FAIL")])
def test_capture_artifact_validity(tmp_path: Path, rows, points, status) -> None:
    result, report = fake_run(tmp_path, TARGETS[0], waveform_rows=rows, actual_points=points)
    cases = {case["name"]: case for case in report["cases"]}
    if status == "PASS":
        assert result.returncode == 0, result.stdout + result.stderr
        assert cases["capture-byte"]["status"] == "PASS"
    else:
        assert result.returncode != 0
        assert cases["capture-byte"]["status"] == "FAIL"


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("outcome,status", [
    ("rejected", "PASS"), ("unexpected-success", "FAIL"),
    ("wrong-error", "FAIL"), ("display-on", "FAIL"),
])
def test_hidden_capture_rejection_and_display_readback(tmp_path: Path, outcome, status) -> None:
    result, report = fake_run(tmp_path, TARGETS[0], hidden_outcome=outcome)
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["capture-hidden-channel"]["status"] == status
    assert (result.returncode == 0) == (status == "PASS")
    invocations = report["invocations"]
    attempted = next(index for index, invocation in enumerate(invocations)
        if "capture-hidden-channel" in invocation["stdout"])
    assert invocations[attempted + 1]["arguments"][0] == "channel-display"
    assert "--query" in invocations[attempted + 1]["arguments"]
    for invocation in invocations:
        if invocation["arguments"][0] == "channel-display" and "2" in invocation["arguments"]:
            assert "--query" in invocation["arguments"]


@pytest.mark.windows_powershell
@requires_windows
def test_screenshot_transport_and_storage_filename_preconditions(tmp_path: Path) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[1], connection="tcpip",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["screenshot-bmp"]["status"] == "N/A"
    assert cases["save-image"]["status"] == "N/A"
    assert not {"screenshot", "save-image"}.intersection(inv["arguments"][0] for inv in report["invocations"])


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("failure", ("mode", "bmp"))
def test_failed_readback_or_artifact_reports_fail(tmp_path: Path, failure: str) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[1], bad_bmp=failure == "bmp",
        stage_responses={"trigger-mode-after": {"ResultOverrides": {"mode": "glitch"}}}
        if failure == "mode" else {},
    )
    assert result.returncode != 0
    assert report["status"] == "failed"
    assert report["summary_counts"]["failed"] == 1
    cases = {case["name"]: case for case in report["cases"]}
    failed_case = {"mode": "trigger-mode", "bmp": "screenshot-bmp"}[failure]
    assert cases[failed_case]["status"] == "FAIL"
    if failure == "mode":
        assert cases["trigger-edge"]["status"] == "NOT TESTED"


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("stage,response", [("fixture-display", {"ExitCode": 1, "Payload": {"ok": False}}), ("fixture-trigger-query", {"ExitCode": 0, "Payload": {"ok": True, "result": {"source_channel": 1, "level_volts": 2.48, "slope": "positive"}}})])
def test_fixed_fixture_failure_stops_functional_cases(tmp_path, target, stage, response):
    result, report = fake_run(tmp_path, target, focused=True, stage_responses={stage: response})
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["fixture-baseline"]["status"] == "FAIL"
    assert "channel-scale" not in cases and "trigger-edge" not in cases
    assert report["invocations"][-1]["stage"] == stage


@pytest.mark.windows_powershell
@requires_windows
def test_measurement_warning_is_retained_in_cli_report(tmp_path):
    status = {"source": "tektronix-sesr", "raw": "16", "value": 16,
              "event_raw": '540,"Measurement warning"', "complete": True,
              "destructive_read": True, "is_error": False,
              "events": [{"code": 540, "message": "Measurement warning", "category": "warning"}]}
    response = {"ExitCode": 0, "Payload": {"ok": True, "result": {
        "valid": True, "value": 0.75, "unit": "s", "post_command_status": status,
    }}}
    result, report = fake_run(tmp_path, TARGETS[2], stage_responses={"measure-rise_time": response})
    assert result.returncode == 0, result.stdout + result.stderr
    case = next(case for case in report["cases"] if case["name"] == "measure-rise_time")
    assert case["status"] == "PASS" and '"code":540' in case["detail"]
    assert '"value":16' in case["detail"] and "Measurement warning" in case["detail"]


@pytest.mark.windows_powershell
@requires_windows
# Representative parser boundary checks; other modes/models remain covered by
# baseline execution, special-trigger and Core/CLI parser contract tests.
@pytest.mark.parametrize(("target", "mode"), [
    (TARGETS[0], "glitch"),
    (TARGETS[1], "tv"),
])
def test_generated_arguments_match_parser_contract(tmp_path: Path, target: str, mode: str) -> None:
    from scopes_tool_cli.parser import _build_parser

    result, report = fake_run(
        tmp_path, target, mode=mode, vectors_on=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # Build once in pytest, not in every fake child CLI process.
    parser = _build_parser()
    arguments = {tuple(inv["arguments"]) for inv in report["invocations"]}
    assert arguments
    for argv in sorted(arguments):
        parsed = parser.parse_args(argv)
        assert parsed.command == argv[0]
        assert parsed.json_output is True
        assert "--live" not in argv
        if parsed.simulate:
            assert parsed.model == target
            assert parsed.resource is None
        else:
            assert parsed.simulate is False
            assert parsed.resource == "USB0::FAKE::INSTR"
            assert "--model" not in argv


CONFIRMATION_SECTIONS = (
    "PRE-VALIDATION",
    "PHYSICAL PREPARATION",
    "DEFAULT VALIDATION ACTIONS",
    "STATE / CLEANUP LIMITATIONS",
    "STANDARD ACTIONS",
)
CONFIRMATION_PROMPT = (
    "Press Enter only after reviewing the information above.",
    "Any other input cancels validation.",
    "Ctrl+C to abort.",
)
NOT_REQUESTED = "Not requested."


@pytest.mark.windows_powershell
@requires_windows
def test_operator_confirmation_enter_runs_every_case_and_reports_pass(tmp_path: Path) -> None:
    # An explicit empty Enter is the only input that may continue.
    result, report = fake_run(tmp_path, TARGETS[2], live_model_name="TBS 1052B")
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["status"] == "passed"

    for banner in (
        "Scopes Tool Tektronix Live Validation",
        "Detected instrument: TBS 1052B",
        "Target: tektronix-tbs1052b",
        "Connection: usb",
        *CONFIRMATION_SECTIONS,
        "Hardware-free preflight passed.",
        "Live instrument identity matches the selected target.",
        "Disconnect unknown or sensitive DUT signals",
        "The runner actively establishes a fixed CH1 fixture before functional checks.",
        "that read is destructive and clears it.",
        "Perform supported same-value setters",
        "Same-value setters are real instrument writes, not read-only checks.",
        "Not every setting is guaranteed to be fully restored.",
        *CONFIRMATION_PROMPT,
    ):
        assert banner in result.stdout, banner

    # The screen must be printed before the first system command runs.
    assert result.stdout.index("Scopes Tool Tektronix Live Validation") < result.stdout.index(
        "PASS  [live][tektronix] system-status-byte"
    )
    # Sections stay in the documented order.
    positions = [result.stdout.index(section) for section in CONFIRMATION_SECTIONS]
    assert positions == sorted(positions)

    cases = {case["name"]: case for case in report["cases"]}
    assert cases["operator-confirmation"]["status"] == "PASS"
    commands = [inv["arguments"][0] for inv in report["invocations"]]
    assert commands[:2] == ["identify", "identify"]
    assert commands.index("system-status-byte") > 1
    assert commands[-1] == "system-standard-event"
    assert cases["system-status-byte"]["status"] == "PASS"
    assert cases["final-standard-event"]["status"] == "PASS"

    assert "\nSummary\n" in result.stdout
    counts = report["summary_counts"]
    totals = re.search(r"Totals: (\d+) PASS / (\d+) FAIL / (\d+) N/A", result.stdout)
    assert totals is not None, result.stdout[-2000:]
    assert (int(totals.group(1)), int(totals.group(2)), int(totals.group(3))) == (
        counts["passed"], counts["failed"], counts["na"],
    )
    assert result.stdout.rstrip().endswith("PASS  [live][tektronix] baseline live validation")

    assert "Fixture: CH1 display ON, CH1 scale 2 V/div" in result.stdout
    assert "Acquisition: Run/Stop state changes" in result.stdout
    assert "Storage Writes: Not requested." not in result.stdout
    assert "autoscale" not in cases


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("confirmation,reason", [
    # Any non-empty input, whitespace-only input, or a null result must fail
    # closed exactly like a declined prompt.
    ("decline", "only an explicit empty Enter continues"),
    ("whitespace", "only an explicit empty Enter continues"),
    ("null", "only an explicit empty Enter continues"),
    ("unavailable", "could not be read"),
])
def test_operator_confirmation_blocks_all_later_commands(
    tmp_path: Path, confirmation: str, reason: str,
) -> None:
    result, report = fake_run(tmp_path, TARGETS[0], confirmation=confirmation)
    assert result.returncode != 0
    assert report["status"] == "failed"
    # Live identify already ran, so hardware access must not be denied.
    assert report["hardware_touched"] is True

    cases = {case["name"]: case for case in report["cases"]}
    assert cases["operator-confirmation"]["status"] == "FAIL"
    assert reason in cases["operator-confirmation"]["detail"]
    assert reason in printed_case_details(result)["operator-confirmation"]
    assert cases["preflight"]["status"] == "PASS"
    assert cases["identify"]["status"] == "PASS"

    commands = [inv["arguments"][0] for inv in report["invocations"]]
    assert commands == ["identify", "identify"]
    assert not {"system-status-byte", "system-standard-event",
                "system-clear-status", "system-opc"} & set(commands)

    counts = report["summary_counts"]
    assert counts["failed"] == 1
    assert counts["passed"] >= 2
    totals = re.search(r"Totals: (\d+) PASS / (\d+) FAIL / (\d+) N/A", result.stdout)
    assert totals is not None, result.stdout[-2000:]
    assert (int(totals.group(1)), int(totals.group(2))) == (counts["passed"], counts["failed"])
    assert "FAIL  [live][tektronix] baseline live validation" in result.stdout
    assert result.stdout.rstrip().endswith("FAIL  [live][tektronix] baseline live validation")
    assert "PASS  [live][tektronix] baseline live validation" not in result.stdout



@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("initial,verified", [(0, 0), (4, 0), (65, 65)])
def test_cli_clean_baseline_preserves_history(tmp_path: Path, initial: int, verified: int) -> None:
    responses = {
        stage: {"ExitCode": 0, "Payload": {"ok": True, "result": {"value": value, "raw": str(value)}}}
        for stage, value in (("pre-run-standard-event", initial), ("pre-run-standard-event-verify", verified))
    }
    result, report = fake_run(tmp_path, TARGETS[0], focused=True, stage_responses=responses)
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["pre-run-clean-baseline"]["status"] == "PASS"
    assert cases["save-pwd"]["status"] == "PASS"
    diagnostic = " ".join(report["diagnostics"]["pre-run-standard-event"])
    assert f'"value":{initial}' in diagnostic
    assert f'"raw":"{initial}"' in diagnostic
    stages = [inv["stage"] for inv in report["invocations"]]
    assert stages.index("identify") < stages.index("pre-run-standard-event")
    assert stages.index("pre-run-standard-event") < stages.index("pre-run-clear-status")
    assert stages.index("pre-run-clear-status") < stages.index("pre-run-standard-event-verify")
    assert stages.index("pre-run-standard-event-verify") < stages.index("save-pwd-same-value")
    assert result.stdout.index("operator-confirmation") < result.stdout.index("pre-run-clean-baseline")
    assert sum(inv["arguments"][0] == "system-clear-status" for inv in report["invocations"]) == 1


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("stage,response", [("pre-run-standard-event", VISA_FAILURE), ("pre-run-standard-event-verify", {"ExitCode": 0, "Payload": {"ok": True, "result": {"value": 4}}})])
def test_cli_clean_baseline_failure_blocks_setters(tmp_path: Path, stage: str, response: dict) -> None:
    result, report = fake_run(tmp_path, TARGETS[0], focused=True, stage_responses={stage: response})
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["pre-run-clean-baseline"]["status"] == "FAIL"
    assert "save-pwd" not in cases
    assert "channel-scale" not in cases
    stages = [inv["stage"] for inv in report["invocations"]]
    assert stages[-1] == stage
    if response["ExitCode"]:
        assert "VisaIOError: Injected I/O failure" in cases["pre-run-clean-baseline"]["detail"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("gate", ["identify", "model", "confirmation"])
def test_cli_clean_baseline_respects_safety_gates(tmp_path: Path, gate: str) -> None:
    result, report = fake_run(
        tmp_path, TARGETS[0], focused=True,
        stage_responses={"identify": VISA_FAILURE} if gate == "identify" else {},
        live_model=TARGETS[1] if gate == "model" else None,
        confirmation="decline" if gate == "confirmation" else "enter",
    )
    assert result.returncode != 0
    assert [inv["arguments"][0] for inv in report["invocations"]] == ["identify", "identify"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("failure", ["none", "setter", "readback", "restore"])
def test_save_pwd_restores_only_after_failure(tmp_path: Path, failure: str) -> None:
    responses = {}
    if failure in ("setter", "restore"):
        responses["save-pwd-same-value"] = VISA_FAILURE
    if failure == "readback":
        responses["save-pwd-after"] = {"ExitCode": 0, "Payload": {"ok": True, "result": {"path": "/other/"}}}
    if failure == "restore":
        responses["save-pwd-restore"] = {
            "ExitCode": 1, "Payload": {"ok": False, "error": {"type": "VisaIOError", "message": "Restore I/O failure"}},
        }
    result, report = fake_run(tmp_path, TARGETS[0], focused=True, stage_responses=responses, save_pwd_path="/usb0/")
    case = next(case for case in report["cases"] if case["name"] == "save-pwd")
    assert case["status"] == ("PASS" if failure == "none" else "FAIL")
    assert (result.returncode == 0) == (failure == "none")
    calls = [inv for inv in report["invocations"] if inv["arguments"][0] == "save-pwd"]
    stages = [inv["stage"] for inv in calls]
    if failure == "none":
        assert stages == ["save-pwd-before", "save-pwd-same-value", "save-pwd-after"]
        assert sum("--path" in inv["arguments"] for inv in calls) == 1
    else:
        assert "save-pwd-restore" in stages
        if failure == "readback":
            assert "readback differs" in case["detail"]
        else:
            assert "save-pwd-same-value failed" in case["detail"]
            assert "Injected I/O failure" in case["detail"]
        if failure == "restore":
            assert "restore failed" in case["detail"]
            assert "Restore I/O failure" in case["detail"]
        else:
            assert stages[-1] == "save-pwd-restored"
    # Other round trips still restore and verify even after successful readback.
    scale_stages = [inv["stage"] for inv in report["invocations"]
                    if inv["stage"].startswith("channel-scale-")]
    assert scale_stages == ["channel-scale-before", "channel-scale-same-value", "channel-scale-after", "channel-scale-restore", "channel-scale-restored"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("path", ["", "bad;path"])
def test_save_pwd_unsafe_original_does_not_write(tmp_path: Path, path: str) -> None:
    result, report = fake_run(tmp_path, TARGETS[0], focused=True, save_pwd_path=path)
    assert result.returncode == 0, result.stdout + result.stderr
    case = next(case for case in report["cases"] if case["name"] == "save-pwd")
    assert case["status"] == "N/A"
    assert [inv["stage"] for inv in report["invocations"] if inv["arguments"][0] == "save-pwd"] == ["save-pwd-before"]


@pytest.mark.windows_powershell
@requires_windows
def test_save_pwd_failed_query_does_not_restore(tmp_path: Path) -> None:
    result, report = fake_run(tmp_path, TARGETS[0], focused=True, stage_responses={"save-pwd-before": VISA_FAILURE})
    assert result.returncode != 0
    case = next(case for case in report["cases"] if case["name"] == "save-pwd")
    assert case["status"] == "FAIL"
    assert "Injected I/O failure" in case["detail"]
    assert [inv["stage"] for inv in report["invocations"] if inv["arguments"][0] == "save-pwd"] == ["save-pwd-before"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("value", [0, 65, 4, None])
def test_cli_final_native_status(tmp_path: Path, value: int | None) -> None:
    response = {"ExitCode": 0, "Payload": {"ok": True, "result": {"value": value}}}
    result, report = fake_run(tmp_path, TARGETS[0], focused=True, stage_responses={"final-standard-event": response})
    case = next(case for case in report["cases"] if case["name"] == "final-standard-event")
    clean = value in (0, 65)
    assert case["status"] == ("PASS" if clean else "FAIL")
    assert (result.returncode == 0) == clean
    assert report["invocations"][-1]["stage"] == "final-standard-event"


@pytest.mark.windows_powershell
@requires_windows
def test_cli_final_io_failure_preserves_case_failure(tmp_path: Path) -> None:
    result, report = fake_run(tmp_path, TARGETS[0], focused=True, stage_responses={
        "save-pwd-same-value": VISA_FAILURE, "final-standard-event": VISA_FAILURE,
    })
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["save-pwd"]["status"] == "FAIL"
    assert "save-pwd-same-value failed" in cases["save-pwd"]["detail"]
    assert cases["final-standard-event"]["status"] == "FAIL"
    assert "VisaIOError" in cases["final-standard-event"]["detail"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("target,command,expected,actual,passed", [(TARGETS[1], "trigger-edge", 1.0, 1.05, True), (TARGETS[1], "trigger-edge", 1.0, 0.95, True), (TARGETS[2], "trigger-edge", 1.0, 1.06, False), (TARGETS[0], "trigger-edge-level", 0.0, 5e-13, True), (TARGETS[0], "trigger-edge-level", 1.0, 1.002, False)])
def test_edge_readback_tolerance(tmp_path, target, command, expected, actual, passed):
    def response(value):
        return {"ExitCode": 0, "Payload": {"ok": True, "result": {
            "source_channel": 1, "level_volts": value, "slope": "positive",
        }}}
    result, report = fake_run(tmp_path, target, focused_case=("trigger-edge-level" if command == "trigger-edge-level" else "trigger-edge"), stage_responses={
        f"{command}-before": response(expected), f"{command}-after": response(actual),
        f"{command}-restored": response(expected),
    })
    case = next(case for case in report["cases"] if case["name"] == command)
    assert case["status"] == ("PASS" if passed else "FAIL")
    assert (result.returncode == 0) == passed
    setter_called = any(inv["stage"] == f"{command}-same-value" for inv in report["invocations"])
    assert setter_called == (command != "trigger-edge" or expected != 1.06)
    if not passed:
        for field in ("Before=", "After=", "Difference=", "Tolerance="):
            assert field in case["detail"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("target", TARGETS[1:2])
@pytest.mark.parametrize("actual,passed", [(1.04, True), (1.06, False)])
def test_fixture_trigger_level_readback_tolerance(tmp_path, target, actual, passed):
    result, report = fake_run(tmp_path, target, focused=True, stage_responses={
        "fixture-trigger-query": {"ResultOverrides": {"level_volts": actual}},
    })
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["fixture-baseline"]["status"] == ("PASS" if passed else "FAIL")
    assert (result.returncode == 0) == passed, result.stdout + result.stderr
    trigger = next(inv["arguments"] for inv in report["invocations"]
                   if inv["stage"] == "fixture-trigger")
    assert trigger[trigger.index("--level") + 1] == "1"
    if not passed:
        assert "level_volts readback differs" in cases["fixture-baseline"]["detail"]
        assert report["invocations"][-1]["stage"] == "fixture-trigger-query"


@pytest.mark.windows_powershell
@requires_windows
# TDS2024B represents the legacy pulse-width readback tolerance contract.
# TBS1052B still has independent identity, mode and two-channel capability tests.
@pytest.mark.parametrize("target", TARGETS[1:2])
@pytest.mark.parametrize("field,actual,passed", [
    ("level_volts", 1.04, True), ("level_volts", 1.06, False),
    ("greater_than_seconds", 1.0065e-6, True),
    ("greater_than_seconds", 1.011e-6, False),
])
def test_pulse_width_level_readback_tolerance(tmp_path, target, field, actual, passed):
    result, report = fake_run(tmp_path, target, mode="glitch", focused_case="trigger-pulse-width", stage_responses={
        "trigger-pulse-width-query": {"ResultOverrides": {field: actual}},
    })
    case = next(case for case in report["cases"] if case["name"] == "trigger-pulse-width")
    assert case["status"] == ("PASS" if passed else "FAIL"), case["detail"]
    assert (result.returncode == 0) == passed, result.stdout + result.stderr
    setter = next(inv["arguments"] for inv in report["invocations"]
                  if inv["stage"] == "trigger-pulse-width-set")
    assert float(setter[setter.index("--level-volts") + 1]) == 1.0
    if not passed:
        assert f"{field} readback differs" in case["detail"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("target", TARGETS[1:2])
@pytest.mark.parametrize("command,field,actual", [
    ("channel-scale", "volts_per_division", 2.001),
    ("trigger-edge", "source_channel", 1.01),
    ("trigger-edge", "slope", "negative"),
])
def test_unrelated_readback_retains_strict_tolerance(tmp_path, target, command, field, actual):
    result, report = fake_run(tmp_path, target, focused_case="strict-readback", stage_responses={
        f"{command}-after": {"ResultOverrides": {field: actual}},
    })
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases[command]["status"] == "FAIL"
    assert f"{field} readback differs" in cases[command]["detail"]
    if command != "trigger-edge":
        assert cases["trigger-edge"]["status"] == "PASS"


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("response", [
    {"ExitCode": 1, "Payload": {"ok": False, "result": {"valid": False, "reason": "No suitable edges"}}},
    {"ExitCode": 0, "Payload": {"ok": True, "result": {"valid": False, "value": 1.0, "unit": "V"}}},
    {"ExitCode": 0, "Payload": {"ok": True, "result": {"valid": True, "value": "NaN", "unit": "V"}}},
    {"ExitCode": 0, "Payload": {"ok": True, "result": {"valid": "true", "value": 1.0, "unit": "V"}}},
])
def test_invalid_measurement_fails_and_remaining_items_execute(tmp_path, response):
    from scopes_tool_core.capabilities import capabilities_for_model_id
    items = capabilities_for_model_id(TARGETS[2]).measurement_items
    result, report = fake_run(tmp_path, TARGETS[2], stage_responses={f"measure-{items[0]}": response})
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases[f"measure-{items[0]}"]["status"] == "FAIL"
    if response["ExitCode"]:
        assert "No suitable edges" in cases[f"measure-{items[0]}"]["detail"]
    for item in items[1:]:
        assert cases[f"measure-{item}"]["status"] == "PASS"
    assert cases["capture-byte"]["status"] == "PASS"
    calls = [inv["arguments"] for inv in report["invocations"] if inv["arguments"][0] == "measure"]
    assert [call[call.index("--item") + 1] for call in calls] == list(items)


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("stage,dependent", [
    ("single", "force-trigger"), ("setup-save", "setup-recall"),
    ("reference-save", "reference-display"), ("cursor-set", "cursor-set-screen"),
    ("primitive-source-display", "capture-byte"), ("trigger-mode-before", "trigger-edge"),
])
def test_failed_prerequisite_is_fail_and_unexecuted_case_not_tested(tmp_path, stage, dependent):
    result, report = fake_run(tmp_path, TARGETS[0], stage_responses={stage: VISA_FAILURE})
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["trigger-mode" if stage == "trigger-mode-before" else stage]["status"] == "FAIL"
    assert cases[dependent]["status"] == "NOT TESTED"
    assert dependent not in [inv["stage"] for inv in report["invocations"]]
    assert report["summary_counts"]["not_tested"] > 0
    assert f"{report['summary_counts']['not_tested']} NOT TESTED" in result.stdout
    assert printed_case_details(result)[dependent] == cases[dependent]["detail"]
    assert cases["stop-acquisition"]["status"] == "PASS"


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("option", ["-IncludeAcquisitionActions"])
def test_removed_optional_switches_are_rejected_before_invocation(option):
    result = run_script("-Target", TARGETS[0], "-Connection", "usb", "-Resource", "USB0::FAKE::INSTR", option)
    assert result.returncode != 0
    assert "NamedParameterNotFound" in result.stderr


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("format_name", ["csv", "internal"])
def test_tbs2074_waveform_save_uses_supported_current_format(tmp_path, format_name):
    result, report = fake_run(tmp_path, TARGETS[0], stage_responses={
        "save-waveform-format-for-file": {"ExitCode": 0, "Payload": {"ok": True, "result": {"format": format_name}}},
        "save-image-format-for-file": {"ExitCode": 0, "Payload": {"ok": True, "result": {"format": "bmp"}}},
    })
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["save-waveform"]["status"] == ("PASS" if format_name == "csv" else "N/A")
    commands = [inv["arguments"] for inv in report["invocations"]]
    waveform_saves = [call for call in commands if call[0] == "save-waveform"]
    assert len(waveform_saves) == (1 if format_name == "csv" else 0)
    image = next(call for call in commands if call[0] == "save-image")
    assert re.fullmatch(r"st[0-9a-f]{6}\.bmp", image[image.index("--filename") + 1])
    assert cases["capture-byte"]["status"] == "PASS"
    if format_name == "internal":
        assert "no public setter can restore INTERNAL" in cases["save-waveform"]["detail"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("target", TARGETS[1:2])
@pytest.mark.parametrize("mismatch", [False, True])
def test_legacy_cursor_y_executes_setter_and_checks_readback(tmp_path, target, mismatch):
    responses = {"cursor-y-offset": {"ResultOverrides": {"volts": 0.25}}}
    if mismatch:
        responses["cursor-set-y-after"] = {"ResultOverrides": {"y2_volts": 0.5}}
    result, report = fake_run(tmp_path, target, stage_responses=responses)
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["cursor-set-y"]["status"] == ("FAIL" if mismatch else "PASS")
    assert (result.returncode != 0) is mismatch
    stages = [inv["stage"] for inv in report["invocations"]]
    assert stages.index("cursor-y-units") < stages.index("cursor-y-offset") < stages.index("cursor-set-y") < stages.index("cursor-set-y-after") < stages.index("cursor-off")
    setter = next(inv["arguments"] for inv in report["invocations"] if inv["stage"] == "cursor-set-y")
    assert setter[setter.index("--source-channel") + 1] == "1"
    assert setter[setter.index("--y1") + 1] == setter[setter.index("--y2") + 1] == "0.25"
    assert "--x1" not in setter and "--auto-vertical" not in setter
    assert cases["cursor-set-screen"]["status"] == "N/A"


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario,status,executed", [
    ("channel-units", "N/A", False), ("cursor-units", "N/A", True),
    ("query-error", "FAIL", False), ("setter-error", "FAIL", True),
])
def test_legacy_cursor_y_preconditions_are_precise(tmp_path, scenario, status, executed):
    if scenario == "channel-units":
        responses = {"cursor-y-units": {"ResultOverrides": {"units": "ampere"}}}
    elif scenario == "cursor-units":
        responses = {"cursor-set-y": {"ExitCode": 1, "Payload": {"ok": False, "error": {
            "type": "ParameterValidationError", "message": "Y cursors require existing volts units",
        }}}}
    else:
        responses = {"cursor-y-units" if scenario == "query-error" else "cursor-set-y": VISA_FAILURE}
    result, report = fake_run(tmp_path, TARGETS[1], stage_responses=responses)
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["cursor-set-y"]["status"] == status
    stages = [inv["stage"] for inv in report["invocations"]]
    assert ("cursor-set-y" in stages) is executed
    assert "cursor-set-y-after" not in stages
    assert cases["cursor-off"]["status"] == "PASS"
    assert (result.returncode != 0) is (status == "FAIL")


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("label", ["", "slot edit"])
def test_setup_lifecycle_restores_empty_or_matching_marker_label(tmp_path, label):
    result, report = fake_run(tmp_path, TARGETS[0], channel_label=label)
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["setup-slot-lifecycle"]["status"] == "PASS"
    change = next(inv["arguments"] for inv in report["invocations"] if inv["stage"] == "setup-slot-label-change")
    assert change[change.index("--text") + 1] != label
    assert "setup-slot-label-cleanup" not in [inv["stage"] for inv in report["invocations"]]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario", ["recall-error", "cleanup-readback"])
def test_setup_lifecycle_failure_retains_error_and_checks_cleanup(tmp_path, scenario):
    responses = {"setup-slot-label-restored": {"ResultOverrides": {"text": "not restored"}}}
    if scenario == "change-readback":
        responses = {"setup-slot-label-changed": {"ResultOverrides": {"text": "CH1"}}}
    elif scenario == "recall-error":
        responses = {"setup-recall": VISA_FAILURE}
    elif scenario == "cleanup-error":
        responses["setup-slot-label-cleanup"] = VISA_FAILURE
    elif scenario == "cleanup-readback":
        responses["setup-slot-label-cleanup-query"] = {"ResultOverrides": {"text": "not restored"}}
    result, report = fake_run(tmp_path, TARGETS[0], stage_responses=responses)
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["setup-save"]["status"] == "PASS"
    assert cases["setup-slot-lifecycle"]["status"] == "FAIL"
    assert cases["setup-recall"]["status"] == ("NOT TESTED" if scenario == "change-readback" else "FAIL")
    assert cases["setup-slot-cleanup"]["status"] == ("FAIL" if scenario.startswith("cleanup-") else "PASS")
    assert ("VisaIOError: Injected I/O failure" if scenario == "recall-error" else "readback differs") in cases["setup-slot-lifecycle"]["detail"]
    cleanup = next(inv["arguments"] for inv in report["invocations"] if inv["stage"] == "setup-slot-label-cleanup")
    assert cleanup[cleanup.index("--text") + 1] == "CH1"
    assert cases["reference-lifecycle"]["status"] == "PASS"


@pytest.mark.windows_powershell
@requires_windows
def test_reference_lifecycle_restores_original_display_off(tmp_path):
    result, report = fake_run(tmp_path, TARGETS[0], stage_responses={
        "reference-display-before": {"ResultOverrides": {"displayed": False}},
    })
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["reference-lifecycle"]["status"] == "PASS"
    assert cases["reference-display-cleanup"]["status"] == "PASS"
    calls = {inv["stage"]: inv["arguments"] for inv in report["invocations"]}
    assert calls["reference-save"][calls["reference-save"].index("--source-channel") + 1] == "1"
    for stage, expected in (("reference-display", "on"), ("reference-display-cleanup", "off")):
        assert calls[stage][calls[stage].index("--state") + 1] == expected


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario", ["display-readback", "cleanup-readback"])
def test_reference_lifecycle_rejects_inconsistent_readback_or_cleanup(tmp_path, scenario):
    stage = {"display-readback": "reference-display-after", "post-save-query": "reference-query-after-save",
             "cleanup-error": "reference-display-cleanup", "cleanup-readback": "reference-display-cleanup-query"}[scenario]
    response = VISA_FAILURE if scenario == "cleanup-error" else {"ResultOverrides": {"displayed": False}}
    result, report = fake_run(tmp_path, TARGETS[0], stage_responses={stage: response})
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["reference-query"]["status"] == "PASS"  # Independent earlier query cannot prove the lifecycle.
    assert cases["reference-save"]["status"] == "PASS"
    assert cases["reference-lifecycle"]["status"] == "FAIL"
    assert cases["reference-display-cleanup"]["status"] == ("FAIL" if scenario.startswith("cleanup-") else "PASS")
    assert "reference-display-cleanup" in [inv["stage"] for inv in report["invocations"]]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("command", ["save-image"])
@pytest.mark.parametrize("fault", ["instrument_side", "opc-scpi"])
def test_instrument_save_rejects_inconsistent_result_or_scpi(tmp_path, command, fault):
    if fault.endswith("scpi"):
        response = {"SentOverrides": ["*OPC?"]} if fault == "save-scpi" else {"OmitSent": ["*OPC?"]}
    else:
        value = False if fault in {"instrument_side", "operation_complete"} else "0" if fault == "raw_operation_complete" else "wrong.bmp"
        response = {"ResultOverrides": {fault: value}}
    result, report = fake_run(tmp_path, TARGETS[0], stage_responses={command: response})
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases[command]["status"] == "FAIL"
    assert cases["save-waveform" if command == "save-image" else "save-image"]["status"] == "PASS"
    assert cases["setup-slot-lifecycle"]["status"] == "PASS"


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("stage,response", [("single", {"SentOverrides": ["ACQuire:STATE ON"]}), ("force-trigger", {"ResultOverrides": {"forced": False}})])
def test_acquisition_checks_sent_commands_and_results(tmp_path, stage, response):
    result, report = fake_run(tmp_path, TARGETS[0], stage_responses={stage: response})
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    assert cases[stage]["status"] == "FAIL"
    stages = [inv["stage"] for inv in report["invocations"]]
    if stage != "stop-acquisition":
        assert stages.index("stop-acquisition") > stages.index(stage)
    if stage == "single":
        assert cases["force-trigger"]["status"] == "NOT TESTED"
        assert "force-trigger" not in stages


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("stage,outcome,status,detail", [
    ("single-wait-natural", "forced", "FAIL", "Invalid bounded BUSY"),
    ("single-wait-force", "natural", "PASS", "timeout-force branch NOT TESTED"),
    ("single-wait-force", "forced", "PASS", "timeout-force branch executed"),
])
def test_single_wait_reports_actual_natural_or_force_outcome(tmp_path, stage, outcome, status, detail):
    result, report = fake_run(tmp_path, TARGETS[0], stage_responses={
        stage: {"ResultOverrides": {"outcome": outcome}},
    })
    cases = {case["name"]: case for case in report["cases"]}
    assert cases[stage]["status"] == status
    assert detail in cases[stage]["detail"]
    assert (result.returncode != 0) is (status == "FAIL")
    call = next(inv["arguments"] for inv in report["invocations"] if inv["stage"] == stage)
    assert ("--force-trigger-on-timeout" in call) is (stage == "single-wait-force")
    assert cases["force-trigger"]["status"] == "PASS"


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize("exit_code", [0, 1])
def test_failure_hints_reference_only_retained_artifacts(tmp_path, debug, exit_code):
    response = {"ExitCode": exit_code, "Payload": {"ok": False, "error": {
        "type": "OscilloscopeError", "message": "Cursor Y setter failed",
    }}}
    result, report = fake_run(tmp_path, TARGETS[1], debug=debug, stage_responses={"cursor-set-y": response})
    assert result.returncode != 0
    cases = {case["name"]: case for case in report["cases"]}
    detail = printed_case_details(result)["cursor-set-y"]
    assert cases["cursor-set-y"]["status"] == "FAIL"
    assert "OscilloscopeError: Cursor Y setter failed" in detail
    invocation = next(inv for inv in report["invocations"] if inv["stage"] == "cursor-set-y")
    if debug:
        for field in ("stdout", "stderr", "json"):
            assert (ROOT / invocation[field]).is_file()
        assert invocation["json" if exit_code == 0 else "stdout"].split("/")[-1].split("\\")[-1] in detail
    else:
        assert "see shareable/report.json and shareable/summary.md" in detail
        assert ".stdout.txt" not in detail and ".stderr.txt" not in detail
        assert all(invocation[field] is None for field in ("stdout", "stderr", "json"))


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("display,status", [(False, "N/A"), ("invalid", "FAIL")])
def test_reference_lifecycle_source_precondition_blocks_writes(tmp_path, display, status):
    result, report = fake_run(tmp_path, TARGETS[0], stage_responses={
        "reference-source-display": {"ResultOverrides": {"display": display}},
    })
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["reference-lifecycle"]["status"] == status
    assert cases["reference-save"]["status"] == ("N/A" if status == "N/A" else "NOT TESTED")
    assert (result.returncode != 0) is (status == "FAIL")
    stages = [inv["stage"] for inv in report["invocations"]]
    assert not {"reference-save", "reference-display", "reference-query-after-save", "reference-display-cleanup"}.intersection(stages)
