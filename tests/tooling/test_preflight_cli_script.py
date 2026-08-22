from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "preflight-cli.ps1"
HELPERS = REPO_ROOT / "scripts" / "_validation_helpers.ps1"
PRIVACY = REPO_ROOT / "scripts" / "_artifact_privacy.ps1"
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
CANONICAL_TARGETS = [
    "keysight-dsox2004a",
    "keysight-dsox3024a",
    "keysight-dsox4024a",
    "keysight-dsox4034a",
]

requires_windows = pytest.mark.skipif(
    os.name != "nt", reason="requires Windows PowerShell"
)


def ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_preflight(*args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
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


def run_powershell_command(body: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", body],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def newest_run_dir(output_root: Path) -> Path:
    runs = sorted(output_root.glob("run_*"))
    assert runs, f"no run_* directory under {output_root}"
    return runs[-1]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def shareable_texts(run_dir: Path) -> list[str]:
    texts = []
    for file in sorted((run_dir / "shareable").rglob("*")):
        if file.is_file():
            texts.append(file.read_text(encoding="utf-8", errors="replace"))
    return texts


@pytest.fixture(scope="module")
def successful_single_target_run():
    output_root = REPO_ROOT / ".tmp_tests" / f"preflight_cli_tests_{uuid.uuid4().hex[:8]}"
    try:
        completed = run_preflight(
            "-Target",
            "keysight-dsox3024a",
            "-OutputRoot",
            str(output_root),
        )
        assert completed.returncode == 0, completed.stderr + completed.stdout
        run_dir = newest_run_dir(output_root)
        yield {
            "completed": completed,
            "run_dir": run_dir,
            "private_report": read_json(run_dir / "private" / "report.json"),
            "shareable_report": read_json(run_dir / "shareable" / "report.json"),
        }
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


@requires_windows
def test_resolve_validation_targets_selects_canonical_models() -> None:
    body = (
        f". {ps_quote(HELPERS)}; "
        "$single = @(Resolve-ValidationTargets -Target 'keysight-dsox3024a'); "
        "$all = @(Resolve-ValidationTargets -Target 'all'); "
        "$invalid = ''; "
        "try { Resolve-ValidationTargets -Target 'DSOX3024A' | Out-Null } "
        "catch { $invalid = $_.Exception.Message }; "
        "[ordered]@{ single = $single; all = $all; invalid_error = $invalid } | "
        "ConvertTo-Json -Compress"
    )
    result = run_powershell_command(body)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["single"] == ["keysight-dsox3024a"]
    assert payload["all"] == CANONICAL_TARGETS
    assert "Unsupported target 'DSOX3024A'" in payload["invalid_error"]
    for model_id in CANONICAL_TARGETS:
        assert model_id in payload["invalid_error"]


@requires_windows
def test_script_rejects_noncanonical_target_with_usage_error() -> None:
    completed = run_preflight("-Target", "DSOX3024A")
    assert completed.returncode == 2
    assert "Unsupported target 'DSOX3024A'" in completed.stderr
    for model_id in CANONICAL_TARGETS:
        assert model_id in completed.stderr


@requires_windows
def test_list_targets_prints_registered_models() -> None:
    completed = run_preflight("-ListTargets")
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == CANONICAL_TARGETS


@requires_windows
class TestSuccessfulSingleTargetPreflight:
    def test_exit_code_and_report_contract(
        self, successful_single_target_run
    ) -> None:
        context = successful_single_target_run
        report = context["private_report"]
        assert report["kind"] == "scopes-tool-cli-preflight"
        assert report["status"] == "passed"
        assert report["targets"] == ["keysight-dsox3024a"]
        assert report["validation_mode"] == "no-hardware-cli-preflight"
        assert report["hardware_touched"] is False
        assert report["summary_counts"] == {
            "targets": 1,
            "cases": 3,
            "passed": 3,
            "failed": 0,
        }
        names = [case["name"] for case in report["cases"]]
        assert names == [
            "acquisition-dry-run",
            "acquisition-simulate",
            "hardware-report-render",
        ]
        assert all(case["passed"] is True for case in report["cases"])

    def test_case_records_carry_debugging_evidence(
        self, successful_single_target_run
    ) -> None:
        context = successful_single_target_run
        run_dir: Path = context["run_dir"]
        for case in context["private_report"]["cases"]:
            assert case["target"] == "keysight-dsox3024a"
            assert case["exit_code"] == 0
            assert isinstance(case["duration_ms"], (int, float))
            assert case["failure_reasons"] == []
            assert case["artifacts"], case["name"]
            for relative in case["artifacts"].values():
                assert (REPO_ROOT / relative).is_file(), relative

        dry_run = context["private_report"]["cases"][0]
        arguments = dry_run["arguments"]
        assert "--dry-run" in arguments
        assert arguments[arguments.index("--model") + 1] == "keysight-dsox3024a"

    def test_acquisition_preflight_coverage_is_preserved(
        self, successful_single_target_run
    ) -> None:
        run_dir: Path = successful_single_target_run["run_dir"]
        target_dir = run_dir / "private" / "keysight-dsox3024a"

        dry_payload = read_json(target_dir / "acquisition-dry-run.json")
        assert dry_payload["ok"] is True
        assert dry_payload["mode"] == "dry_run"
        assert dry_payload["result"]["status"] == "planned"
        planned = dry_payload["scpi"]["planned"]
        assert ":ACQuire:TYPE?" in planned
        assert ":ACQuire:COUNt?" in planned

        sim_payload = read_json(target_dir / "acquisition-simulate.json")
        assert sim_payload["ok"] is True
        assert sim_payload["mode"] == "simulate"
        assert sim_payload["result"]["status"] == "completed"

        summary = (target_dir / "hardware-report-render.summary.md").read_text(
            encoding="utf-8"
        )
        assert summary.startswith("# Hardware Report")

    def test_shareable_artifacts_are_generated_and_redacted(
        self, successful_single_target_run
    ) -> None:
        context = successful_single_target_run
        run_dir: Path = context["run_dir"]
        shareable_report = context["shareable_report"]
        assert shareable_report["status"] == "passed"
        assert shareable_report["artifact_visibility"] == "shareable"
        assert shareable_report["redaction_applied"] is True
        assert shareable_report["candidate_evidence_only"] is True
        assert (run_dir / "shareable" / "summary.md").is_file()
        mirrored = (
            run_dir
            / "shareable"
            / "keysight-dsox3024a"
            / "acquisition-dry-run.json"
        )
        assert mirrored.is_file()
        mirrored_payload = read_json(mirrored)
        assert mirrored_payload["resource"] == "<redacted-resource>"
        assert mirrored_payload["idn"] == "<redacted-idn>"

        for text in shareable_texts(run_dir):
            assert str(REPO_ROOT) not in text

    def test_private_summary_lists_cases(self, successful_single_target_run) -> None:
        run_dir: Path = successful_single_target_run["run_dir"]
        summary = (run_dir / "private" / "summary.md").read_text(encoding="utf-8")
        assert "| Target | Case | Exit | Duration (ms) | Result |" in summary
        assert "acquisition-dry-run" in summary
        assert "acquisition-simulate" in summary
        assert "hardware-report-render" in summary

    def test_shareable_report_references_resolve_inside_shareable_tree(
        self, successful_single_target_run
    ) -> None:
        context = successful_single_target_run
        run_dir: Path = context["run_dir"]
        raw = (run_dir / "shareable" / "report.json").read_text(encoding="utf-8")
        assert "/private/" not in raw.replace("\\", "/")

        shareable_report = context["shareable_report"]
        checked_references = 0
        for case in shareable_report["cases"]:
            for reference in case["artifacts"].values():
                assert reference.startswith("shareable/"), reference
                assert (run_dir / reference).is_file(), reference
                checked_references += 1
        assert checked_references >= 3

        artifact_paths = shareable_report["artifact_paths"]
        assert artifact_paths["report"] == "shareable/report.json"
        assert (run_dir / artifact_paths["report"]).is_file()
        assert (run_dir / artifact_paths["summary"]).is_file()


@requires_windows
def test_failed_command_preserves_artifacts_and_fails_preflight(tmp_path: Path) -> None:
    stub = tmp_path / "failing_python.cmd"
    stub.write_text(
        "@echo off\r\n"
        "echo partial stdout sentinel\r\n"
        "echo simulated boom 1>&2\r\n"
        "exit /b 7\r\n",
        encoding="ascii",
    )
    output_root = REPO_ROOT / ".tmp_tests" / f"preflight_cli_tests_{uuid.uuid4().hex[:8]}"
    try:
        completed = run_preflight(
            "-Target",
            "keysight-dsox2004a",
            "-Python",
            str(stub),
            "-OutputRoot",
            str(output_root),
        )
        assert completed.returncode == 1
        run_dir = newest_run_dir(output_root)
        report = read_json(run_dir / "private" / "report.json")
        assert report["status"] == "failed"
        cases = {case["name"]: case for case in report["cases"]}
        dry_run = cases["acquisition-dry-run"]
        assert dry_run["passed"] is False
        assert any("exit code 7" in reason for reason in dry_run["failure_reasons"])
        stdout_artifact = REPO_ROOT / dry_run["artifacts"]["stdout"]
        assert stdout_artifact.read_text(encoding="utf-8").strip().endswith(
            "partial stdout sentinel"
        )
        stderr_artifact = REPO_ROOT / dry_run["artifacts"]["stderr"]
        assert "simulated boom" in stderr_artifact.read_text(encoding="utf-8")

        render = cases["hardware-report-render"]
        assert render["passed"] is False
        assert any("skipped" in reason for reason in render["failure_reasons"])

        shareable_report = read_json(run_dir / "shareable" / "report.json")
        assert shareable_report["status"] == "failed"
        assert (run_dir / "private" / "summary.md").is_file()
        assert (run_dir / "shareable" / "summary.md").is_file()
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


@requires_windows
def test_target_all_runs_every_registered_model() -> None:
    output_root = (
        REPO_ROOT / ".tmp_tests" / f"preflight_cli_tests_{uuid.uuid4().hex[:8]}"
    )
    try:
        completed = run_preflight(
            "-Target",
            "all",
            "-OutputRoot",
            str(output_root),
            timeout=600,
        )
        assert completed.returncode == 0, completed.stderr + completed.stdout
        run_dir = newest_run_dir(output_root)
        report = read_json(run_dir / "private" / "report.json")
        assert report["status"] == "passed"
        assert report["targets"] == CANONICAL_TARGETS
        assert report["summary_counts"]["targets"] == len(CANONICAL_TARGETS)
        assert report["summary_counts"]["failed"] == 0
        covered_targets = {case["target"] for case in report["cases"]}
        assert covered_targets == set(CANONICAL_TARGETS)
        for target in CANONICAL_TARGETS:
            assert (run_dir / "private" / target / "acquisition-simulate.json").is_file()
            assert (
                run_dir / "shareable" / target / "acquisition-simulate.json"
            ).is_file()
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


@requires_windows
def test_shareable_generation_failure_fails_preflight(tmp_path: Path) -> None:
    # Minimal substitution: run a patched copy of the preflight script whose
    # privacy helper re-defines New-ShareableArtifactSet to throw, so all
    # validation cases pass but shareable artifact generation fails.
    harness_dir = tmp_path / "scripts"
    harness_dir.mkdir()
    failing_privacy = harness_dir / "_artifact_privacy.failing.ps1"
    failing_privacy.write_text(
        ". " + ps_quote(PRIVACY) + "\n"
        "function New-ShareableArtifactSet { "
        "throw [System.InvalidOperationException]::new("
        "'simulated shareable artifact generation failure') }\n",
        encoding="utf-8",
    )

    script_text = SCRIPT.read_text(encoding="utf-8")
    replacements = {
        '$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path':
            f"$RepoRoot = {ps_quote(REPO_ROOT)}",
        '. (Join-Path $PSScriptRoot "_validation_helpers.ps1")':
            f". {ps_quote(HELPERS)}",
        '. (Join-Path $PSScriptRoot "_artifact_privacy.ps1")':
            f". {ps_quote(failing_privacy)}",
    }
    for old, new in replacements.items():
        assert script_text.count(old) == 1, old
        script_text = script_text.replace(old, new)
    harness_script = harness_dir / "preflight-cli-failing-shareable.ps1"
    harness_script.write_text(script_text, encoding="utf-8")

    output_root = REPO_ROOT / ".tmp_tests" / f"preflight_cli_tests_{uuid.uuid4().hex[:8]}"
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(harness_script),
                "-Target",
                "keysight-dsox4024a",
                "-OutputRoot",
                str(output_root),
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=300,
        )
        assert completed.returncode == 1
        assert "shareable artifact generation failed" in completed.stdout
        assert (
            "simulated shareable artifact generation failure" in completed.stdout
        )

        run_dir = newest_run_dir(output_root)
        assert (run_dir / "private" / "report.json").is_file()
        assert (run_dir / "private" / "summary.md").is_file()
        report = read_json(run_dir / "private" / "report.json")
        assert all(case["passed"] is True for case in report["cases"])
        assert report["status"] == "failed"
        assert report.get("shareable_generation_error") == (
            "simulated shareable artifact generation failure"
        )
        summary = (run_dir / "private" / "summary.md").read_text(encoding="utf-8")
        assert "Shareable artifact generation failed:" in summary
    finally:
        shutil.rmtree(output_root, ignore_errors=True)


@requires_windows
def test_shareable_artifacts_redact_sensitive_values(tmp_path: Path) -> None:
    resource = "USB0::1::2::SYNTH12345::INSTR"
    idn_raw = "KEYSIGHT TECHNOLOGIES,DSOX4034A,SYNTH12345,0.0"
    secrets = {
        "serial": "SYNTH12345",
        "resource": resource,
        "idn": idn_raw,
        "ip": "192.168.1.50",
        "link_local_ip": "169.254.8.9",
        "user_path": "C:\\Users\\alice\\evidence.txt",
        "repo_path": str(REPO_ROOT),
    }

    private_dir = tmp_path / "run" / "private"
    shareable_dir = tmp_path / "run" / "shareable"
    private_dir.mkdir(parents=True)
    shareable_dir.mkdir(parents=True)

    report_body = (
        "$resource = {resource}; "
        "$idnRaw = {idn}; "
        "$repoRoot = {repo}; "
        "$privateRoot = {private}; "
        "$shareableRoot = {shareable}; "
        "$report = [pscustomobject]@{{ "
        "kind = 'scopes-tool-cli-preflight'; status = 'passed'; "
        "targets = @('keysight-dsox4034a'); resource = $resource; "
        "notes = 'host 192.168.1.50 link 169.254.8.9 user C:\\Users\\alice\\evidence.txt repo ' + $repoRoot; "
        "idn = [pscustomobject]@{{ raw = $idnRaw; serial = 'SYNTH12345' }}; "
        "artifact_paths = [ordered]@{{ report = (Join-Path $privateRoot 'report.json') }} }}; "
        "Write-Utf8NoBomText -LiteralPath (Join-Path $privateRoot 'report.json') "
        "($report | ConvertTo-Json -Depth 12); "
        "Write-Utf8NoBomLines -LiteralPath (Join-Path $privateRoot 'summary.md') "
        "@('# Summary', \"IDN: $idnRaw\", \"Resource: $resource\"); "
        "Write-Utf8NoBomText -LiteralPath (Join-Path $privateRoot 'case-a.stdout.txt') "
        "(\"$resource 192.168.1.50\"); "
        "$null = New-ShareableArtifactSet -PrivateReport $report "
        "-PrivateSummaryPath (Join-Path $privateRoot 'summary.md') "
        "-RunRoot (Split-Path -Parent $privateRoot) -PrivateRoot $privateRoot "
        "-ShareableRoot $shareableRoot -RepoRoot $repoRoot -Resource $resource"
    ).format(
        resource=ps_quote(resource),
        idn=ps_quote(idn_raw),
        repo=ps_quote(REPO_ROOT),
        private=ps_quote(private_dir),
        shareable=ps_quote(shareable_dir),
    )

    result = run_powershell_command(
        f". {ps_quote(HELPERS)}; . {ps_quote(PRIVACY)}; {report_body}"
    )
    assert result.returncode == 0, result.stderr

    # PowerShell 5.1 ConvertTo-Json escapes angle brackets as \u003c/\u003e.
    def normalize(text: str) -> str:
        return text.replace("\\u003c", "<").replace("\\u003e", ">")

    produced = [
        normalize(path.read_text(encoding="utf-8"))
        for path in sorted(shareable_dir.rglob("*"))
        if path.is_file()
    ]
    joined = "\n".join(produced)
    for name, secret in secrets.items():
        assert secret not in joined, f"{name} leaked into shareable artifacts"
    assert "<redacted-resource>" in joined
    assert "<redacted-idn>" in joined
    assert "<redacted-ip>" in joined
    assert "<redacted-path>" in joined
    assert "<repository-root>" in joined

    shareable_report = read_json(shareable_dir / "report.json")
    assert shareable_report["idn"] == "<redacted-idn>"
    assert shareable_report["redaction_applied"] is True
