from __future__ import annotations

from pathlib import Path

import pytest

from tests.tooling._tektronix_live_test_support import (
    TARGETS, fake_workflow_run, requires_windows,
)

@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario", ["clean", "stale", "nonerror-events"])
def test_workflow_clean_baseline_preserves_history(tmp_path: Path, scenario: str) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[2], f"focused-{scenario}", debug=False)
    assert result.returncode == 0, result.stdout + result.stderr
    cases = {case["name"]: case for case in report["cases"]}
    for name in ("operator-confirmation", "pre-run-clean-baseline", "measure-sweep", "cleanup", "final-standard-event"):
        assert cases[name]["status"] == "PASS", cases[name]
    diagnostic = " ".join(report["diagnostics"]["pre-run-standard-event"])
    initial = 4 if scenario == "stale" else 0
    assert f'"value":{initial}' in diagnostic
    assert f'"raw":"{initial}"' in diagnostic
    stages = [inv["stage"] for inv in report["invocations"]]
    expected = ["identity", "pre-run-standard-event", "pre-run-clear-status", "pre-run-standard-event-verify", "acquisition-precondition-run", "measure-sweep", "cleanup-acquisition-stop-acquisition", "final-standard-event"]
    assert [stage for stage in stages if stage != "preflight-identify"] == expected
    assert result.stdout.index("Press Enter") < result.stdout.index("pre-run-clean-baseline")
    assert all("check-error" != inv["arguments"][0] for inv in report["invocations"])
    assert report["schema_version"] == 1
    counts = report["summary_counts"]
    assert counts["cases"] == len(cases)
    for key, status in (("passed", "PASS"), ("failed", "FAIL"), ("na", "N/A")):
        assert counts[key] == sum(case["status"] == status for case in cases.values())


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario,failed_stage", [
    ("query-io", "pre-run-standard-event"),
    ("clear-io", "pre-run-clear-status"),
    ("verify-io", "pre-run-standard-event-verify"),
    ("post-event", "pre-run-standard-event-verify"),
])
def test_workflow_clean_baseline_failure_blocks_workflows(tmp_path: Path, scenario: str, failed_stage: str) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[2], f"focused-{scenario}", debug=False)
    assert result.returncode != 0
    assert report["status"] == "failed"
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["pre-run-clean-baseline"]["status"] == "FAIL"
    assert "measure-sweep" not in cases
    assert "acquisition-precondition" not in cases
    assert report["invocations"][-1]["stage"] == failed_stage
    if scenario.endswith("io"):
        assert "VisaIOError" in cases["pre-run-clean-baseline"]["detail"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario", ["identify-io", "model-mismatch"])
def test_workflow_clean_baseline_respects_identity_gate(tmp_path: Path, scenario: str) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[2], f"focused-{scenario}", debug=False)
    assert result.returncode != 0
    assert [inv["stage"] for inv in report["invocations"]] == ["preflight-identify", "identity"]


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario,reason", [
    ("n", "explicit empty input"),
    ("no", "explicit empty input"),
    ("text", "explicit empty input"),
    ("space", "explicit empty input"),
    ("null", "explicit empty input"),
    ("unavailable", "Operator console unavailable"),
])
def test_workflow_clean_baseline_respects_confirmation_gate(tmp_path: Path, scenario: str, reason: str) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[2], f"focused-confirmation-{scenario}", debug=False)
    assert result.returncode != 0
    assert report["status"] == "failed"
    cases = {case["name"]: case for case in report["cases"]}
    assert list(cases) == ["preflight", "identity", "target-model-match", "operator-confirmation"]
    assert cases["identity"]["status"] == "PASS"
    assert cases["target-model-match"]["status"] == "PASS"
    assert cases["operator-confirmation"]["status"] == "FAIL"
    assert reason in cases["operator-confirmation"]["detail"]
    assert [inv["stage"] for inv in report["invocations"]] == ["preflight-identify", "identity"]
    assert all(inv["arguments"][0] not in (
        "system-standard-event", "system-clear-status", "run",
        "stop-acquisition", "measure-sweep", "capture-batch",
    ) for inv in report["invocations"])
    counts = report["summary_counts"]
    assert counts["cases"] == len(cases)
    assert counts["invocations"] == len(report["invocations"])
    for key, status in (("passed", "PASS"), ("failed", "FAIL"), ("na", "N/A")):
        assert counts[key] == sum(case["status"] == status for case in cases.values())


@pytest.mark.windows_powershell
@requires_windows
@pytest.mark.parametrize("scenario,final_status", [
    ("clean", "PASS"), ("final-event", "FAIL"), ("final-io", "FAIL"),
    ("final-missing", "FAIL"), ("cleanup-fail", "PASS"),
    ("case-fail", "PASS"), ("case-and-final-fail", "FAIL"),
    ("dirty-case", "PASS"),
])
def test_workflow_final_native_status_after_cleanup(tmp_path: Path, scenario: str, final_status: str) -> None:
    result, report = fake_workflow_run(tmp_path, TARGETS[2], f"focused-{scenario}", debug=False)
    cases = {case["name"]: case for case in report["cases"]}
    assert cases["final-standard-event"]["status"] == final_status
    assert (result.returncode == 0) == (scenario == "clean")
    assert "final-error-queue" not in cases
    stages = [inv["stage"] for inv in report["invocations"]]
    assert stages[-2:] == ["cleanup-acquisition-stop-acquisition", "final-standard-event"]
    if scenario == "cleanup-fail":
        assert cases["cleanup"]["status"] == "FAIL"
        assert "Injected failure at cleanup-acquisition-stop-acquisition" in cases["cleanup"]["detail"]
    if scenario.startswith("case"):
        assert cases["measure-sweep"]["status"] == "FAIL"
        assert "Injected failure at measure-sweep" in cases["measure-sweep"]["detail"]
    if scenario == "final-io":
        assert "VisaIOError" in cases["final-standard-event"]["detail"]
    if scenario == "dirty-case":
        assert cases["measure-sweep"]["status"] == "FAIL"
        assert "error-bearing native measurement status" in cases["measure-sweep"]["detail"]
    counts = report["summary_counts"]
    assert counts["failed"] == sum(case["status"] == "FAIL" for case in cases.values())
