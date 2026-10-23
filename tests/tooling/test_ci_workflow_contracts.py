"""Verify that expensive Windows CI jobs are selected by meaningful changes.

Model the positive/exclusion matching contract of dorny/paths-filter configured
with predicate-quantifier=some-with-excludes, without binding tests to YAML layout.
"""

from fnmatch import fnmatchcase
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from textwrap import dedent

import pytest


ROOT = Path(__file__).resolve().parents[2]
TESTS_WORKFLOW = ROOT / ".github/workflows/tests.yml"
BUILD_WORKFLOW = ROOT / ".github/workflows/build-windows.yml"
FILTERS = (
    "validation_shared",
    "validation_keysight",
    "validation_tektronix",
    "validation_cross_vendor",
    "packaging",
    "release_layout",
    "release_contracts",
)


def _change_filters() -> dict[str, list[str]]:
    lines = TESTS_WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "filters: |")
    indent = len(lines[start]) - len(lines[start].lstrip())
    patterns: dict[str, list[str]] = {}
    category = ""
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        part = line.strip()
        if part.endswith(":"):
            category = part[:-1]
            patterns[category] = []
        elif part.startswith("- '") and part.endswith("'"):
            patterns[category].append(part[3:-1])
    return patterns


def _changed_categories(*paths: str) -> set[str]:
    filters = _change_filters()
    affected = set()
    for category, patterns in filters.items():
        included = [pattern for pattern in patterns if not pattern.startswith("!")]
        excluded = [pattern[1:] for pattern in patterns if pattern.startswith("!")]
        for path in paths:
            if any(fnmatchcase(path, pattern) for pattern in included) and not any(
                fnmatchcase(path, pattern) for pattern in excluded
            ):
                affected.add(category)
    return affected


def _jobs(*paths: str) -> set[str]:
    changed = _changed_categories(*paths)
    result = set()
    if "validation_cross_vendor" in changed:
        result.update(("shared", "keysight", "tektronix"))
    else:
        result.update(
            category.removeprefix("validation_")
            for category in changed if category.startswith("validation_")
        )
    if "packaging" in changed:
        result.add("packaging")
    return result


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        (("README.md",), set()),
        (("docs/core/integration.md",), set()),
        (("docs/testing-guidelines.md",), set()),
        (("scripts/check_text_hygiene.py",), set()),
        (("tests/tooling/test_ci_workflow_contracts.py",), set()),
        (("src/scopes_tool_webui/static/app.js",), {"packaging"}),
        (("desktop/main.cjs",), {"packaging"}),
        (("scripts/build_desktop.ps1",), {"packaging"}),
        (("scripts/build_release.ps1",), {"packaging"}),
        (("scripts/release-acceptance.ps1",), set()),
        (("tests/packaging/test_release_acceptance.py",), set()),
        (("scripts/ci_packaging_smoke.py",), {"packaging"}),
        (("tests/packaging/test_windows_bundle.py",), {"packaging"}),
        ((".github/workflows/build-windows.yml",), {"packaging"}),
        (("tests/tooling/test_live_script_invocation.py",), {"shared"}),
        (("tests/tooling/test_live_script_validators.py",), {"shared"}),
        (("tests/tooling/test_windows_python_boundary.py",), {"shared"}),
        (("tests/tooling/test_live_script_controls.py",), {"keysight"}),
        (("tests/tooling/test_live_script_artifacts.py",), {"keysight"}),
        (("tests/tooling/test_live_script_dvm_segmented.py",), {"keysight"}),
        (("tests/tooling/test_live_script_serial.py",), {"keysight"}),
        (("tests/tooling/test_preflight_cli_script.py",), {"keysight"}),
        (("tests/tooling/test_live_tektronix_script.py",), {"tektronix"}),
        (("tests/tooling/test_live_workflow_script.py",), {"tektronix"}),
        (("tests/tooling/_tektronix_live_test_support.py",), {"tektronix"}),
        (("src/scopes_tool_core/tektronix.py",), {"tektronix", "packaging"}),
        (("src/scopes_tool_core/tektronix_simulator.py",), {"tektronix", "packaging"}),
        (("scripts/_live_tektronix_helpers.ps1",), {"shared", "tektronix"}),
        (("scripts/live-dvm-check.ps1",), {"shared", "keysight"}),
        (("scripts/live-segmented-check.ps1",), {"shared", "keysight"}),
        (("scripts/live-serial-check.ps1",), {"shared", "keysight"}),
        (("scripts/preflight-cli.ps1",), {"shared", "keysight"}),
        (("scripts/live-cli-check.ps1",), {"shared", "keysight", "tektronix"}),
        (("scripts/live-workflow-check.ps1",), {"shared", "keysight", "tektronix"}),
        (("scripts/live-autoscale-check.ps1",), {"shared", "keysight", "tektronix"}),
        (("tests/tooling/test_live_autoscale_script.py",), {"shared", "keysight", "tektronix"}),
        (("tests/tooling/test_live_trigger_validation.py",), {"shared", "keysight", "tektronix"}),
        (("tests/conftest.py",), {"shared", "keysight", "tektronix"}),
        (("tests/tooling/_validation_grouping.py",), {"shared", "keysight", "tektronix"}),
        (("src/scopes_tool_core/scpi.py",), {"shared", "keysight", "tektronix", "packaging"}),
        (("src/scopes_tool_core/drivers.py",), {"shared", "keysight", "tektronix", "packaging"}),
        (("src/scopes_tool_cli/cli.py",), {"shared", "keysight", "tektronix", "packaging"}),
        (("pyproject.toml",), {"shared", "keysight", "tektronix", "packaging"}),
        (("uv.lock",), {"shared", "keysight", "tektronix", "packaging"}),
        ((".github/workflows/tests.yml",), {"shared", "keysight", "tektronix", "packaging"}),
        (("README.md", "src/scopes_tool_core/tektronix.py"), {"tektronix", "packaging"}),
        (("src/scopes_tool_core/tektronix.py", "scripts/live-dvm-check.ps1"), {"shared", "keysight", "tektronix", "packaging"}),
    ],
)
def test_windows_change_detection_is_precise(changed, expected):
    assert _jobs(*changed) == expected


def test_filters_and_conditional_gate_remain_safe():
    workflow = TESTS_WORKFLOW.read_text(encoding="utf-8")
    assert set(_change_filters()) == set(FILTERS)
    assert "predicate-quantifier: some-with-excludes" in workflow
    assert "base: ${{ github.event.repository.default_branch }}" in workflow
    assert "  pull_request:\n" in workflow
    assert "  push:\n" in workflow
    assert "      - main\n" in workflow
    assert "  workflow_dispatch:" not in workflow
    for group in ("shared", "keysight", "tektronix"):
        assert f"  windows-validation-{group}:" in workflow
        if group == "tektronix":
            # Its marker selection now lives in the single-Job shard launcher.
            assert "scripts/ci_tektronix_validation.py" in workflow
            launcher = (ROOT / "scripts/ci_tektronix_validation.py").read_text(
                encoding="utf-8"
            )
            assert f"windows_powershell and validation_{group}" in launcher
        else:
            assert f"windows_powershell and validation_{group}" in workflow
        assert f"outputs.validation_{group} == 'true'" in workflow
    assert "needs.detect-windows-validation-changes.outputs.validation_cross_vendor" in workflow
    assert "  windows-validation-gate:" in workflow
    assert "    if: always()" in workflow
    assert "DETECT_RESULT" in workflow
    assert "scripts/ci_validation_partition.py" in workflow
    assert "scripts/ci_packaging_smoke.py --mode desktop" in workflow


def test_release_changes_select_contracts_and_a_single_packaging_build():
    assert _changed_categories("scripts/release-acceptance.ps1") == {"release_contracts"}
    assert "release_contracts" in _changed_categories(".github/workflows/build-windows.yml")
    assert _changed_categories("tests/tooling/test_ci_workflow_contracts.py") == {"release_contracts"}
    assert _changed_categories("scripts/build_release.ps1") == {
        "packaging", "release_layout", "release_contracts",
    }
    workflow = TESTS_WORKFLOW.read_text(encoding="utf-8")
    assert "tests/packaging/test_release_acceptance.py" in workflow
    assert "outputs.release_layout == 'true'" in workflow
    assert "outputs.release_layout != 'true'" in workflow
    assert "--release-dir" in workflow


def test_manual_build_routes_outputs_and_gates_draft_releases():
    workflow = BUILD_WORKFLOW.read_text(encoding="utf-8")
    lines = workflow.splitlines()
    assert "workflow_dispatch:" in [line.strip() for line in lines]
    assert not {"pull_request:", "push:"}.intersection(line.strip() for line in lines)

    # Select a YAML section by indentation, not a particular formatting layout.
    def section(key: str) -> str:
        starts = [i for i, line in enumerate(lines) if line.strip() == f"{key}:"]
        assert len(starts) == 1
        start = starts[0]
        indent = len(lines[start]) - len(lines[start].lstrip())
        body = []
        for line in lines[start + 1:]:
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            body.append(line.strip())
        return "\n".join(body)

    mode = section("build_mode").splitlines()
    draft_input = section("create_draft").splitlines()
    assert "type: choice" in mode
    assert "default: release" in mode
    assert {line[2:] for line in mode if line.startswith("- ")} == {
        "bundle", "desktop", "release", "release-acceptance",
    }
    assert {"type: boolean", "default: false"}.issubset(draft_input)

    build, draft = section("build"), section("draft-release")
    for mode, script in (
        ("bundle", "build_windows_bundle.ps1"),
        ("desktop", "build_desktop.ps1"),
        ("release", "build_release.ps1"),
    ):
        assert re.search(rf"'{mode}'\s*{{[^}}]*scripts[\\/]{script}", build)
    assert "powershell.exe" in build and "-File $script" in build
    assert re.search(r"if\s*\(\$LASTEXITCODE -ne 0\)\s*{\s*throw", build)
    assert "scripts/ci_packaging_smoke.py --mode" in build
    assert "scripts/ci_packaging_smoke.py --release-dir" in build
    assert {"--expected-version", "--extract-dir"}.issubset(build.split())
    assert "--layout-only" not in build
    assert "dist/scopes-tool" in build
    assert "dist/desktop/win-unpacked" in build
    assert "scopes-tool-$mode-windows-x64.zip" in build
    assert "git rev-parse --short=7 HEAD" in build
    assert re.search(r"artifact_name=scopes-tool-windows-\$\{\{\s*inputs\.build_mode\s*\}\}-\$\w+", build)
    assert "github.run_id" not in build
    for artifact in (
        "scopes-tool-$version-windows-x64.zip",
        "scopes_tool-$version-py3-none-any.whl",
        "scopes_tool-$version.tar.gz",
        "checksums.txt",
    ):
        assert artifact in build
    assert "release/$version/$name" in build
    assert "actions/upload-artifact@v4" in build
    assert "path: .tmp_tests/actions-artifacts/*" in build
    assert "if-no-files-found: error" in build
    assert "continue-on-error:" not in workflow

    assert "'${{ inputs.create_draft }}' -eq 'true'" in build
    assert "'${{ inputs.build_mode }}' -ne 'release-acceptance'" in build
    assert "'${{ github.ref }}' -ne 'refs/heads/main'" in build
    gate = next(line.strip() for line in draft.splitlines() if line.strip().startswith("if:"))
    assert "inputs.build_mode == 'release-acceptance'" in gate
    assert "inputs.create_draft" in gate
    assert "github.ref == 'refs/heads/main'" in gate
    assert "needs.build.result == 'success'" in gate
    assert "needs.build.outputs.acceptance_passed == 'true'" in gate
    assert "needs.build.outputs.source_commit == github.sha" in gate
    assert "needs: build" in draft
    assert "ref: ${{ github.sha }}" in draft
    assert "actions/download-artifact@v4" in draft
    assert "name: ${{ steps.meta.outputs.artifact_name }}" in build
    assert "name: ${{ needs.build.outputs.artifact_name }}" in draft
    assert "contents: read" in workflow and "contents: write" not in build
    assert "contents: write" in draft
    # Verify both duplicate guards precede creation without freezing CLI spelling.
    checks, separator, creation = draft.partition("gh release create")
    assert separator
    assert "/releases" in checks or "gh release view" in checks
    assert "refs/tags/" in checks
    assert "set -euo pipefail" in checks
    assert "exit 1" in checks
    assert '"v${VERSION}" release-assets/*' in creation
    assert '--target "$GITHUB_SHA"' in creation
    assert "--draft" in creation.split()
    assert "gh release edit" not in workflow
    assert "gh release upload" not in workflow
    assert "--clobber" not in workflow


def _build_step(name):
    workflow = BUILD_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        rf"^      - name: {re.escape(name)}\n(.*?)(?=^      - |\n  [\w-]+:|\Z)",
        workflow, re.MULTILINE | re.DOTALL,
    )
    assert match, name
    return match[1]


def _run_block(step):
    return dedent(step.split("        run: |\n", 1)[1])


def _powershell(tmp_path, script, **environment):
    path = tmp_path / "workflow-step.ps1"
    path.write_text(script, encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"}
    env.update(environment)
    return subprocess.run(
        ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell required")
@pytest.mark.parametrize("mode", ["bundle", "desktop", "release", "release-acceptance"])
@pytest.mark.parametrize("main", [False, True])
@pytest.mark.parametrize("create_draft", [False, True])
def test_manual_build_draft_input_validation(tmp_path, mode, main, create_draft):
    script = _run_block(_build_step("Validate options"))
    for key, value in {
        "inputs.build_mode": mode,
        "inputs.create_draft": str(create_draft).lower(),
        "github.ref": "refs/heads/main" if main else "refs/heads/topic",
    }.items():
        script = script.replace("${{ " + key + " }}", value)
    result = _powershell(tmp_path, script)
    allowed = not create_draft or (mode == "release-acceptance" and main)
    assert (result.returncode == 0) is allowed, result.stdout + result.stderr


def test_acceptance_is_the_only_build_and_smoke_in_its_mode():
    for name in ("Build Windows output", "Smoke actual packaged executables (no hardware)"):
        assert "if: inputs.build_mode != 'release-acceptance'" in _build_step(name)
    acceptance = _build_step("Run and verify formal release acceptance (no hardware)")
    assert "if: inputs.build_mode == 'release-acceptance'" in acceptance
    assert acceptance.count("& powershell.exe") == 1
    assert "./scripts/release-acceptance.ps1 -OutputRoot $outputRoot" in acceptance
    assert "build_release.ps1" not in acceptance
    assert "ci_packaging_smoke.py" not in acceptance
    assert "Join-Path $runDirectory" in acceptance
    assert "Copy-Item -LiteralPath $artifact" in acceptance
    assert "if: inputs.build_mode == 'bundle' || inputs.build_mode == 'desktop'" in _build_step(
        "Stage downloadable ZIP"
    )
    assert "if: inputs.build_mode == 'release'" in _build_step("Stage release artifacts")
    evidence = _build_step("Upload acceptance evidence")
    assert "if: always() && inputs.build_mode == 'release-acceptance'" in evidence
    assert "run-*/report.json" in evidence and "run-*/summary.md" in evidence
    assert "actions-artifacts" not in evidence
    workflow = BUILD_WORKFLOW.read_text(encoding="utf-8")
    assert "acceptance_passed: ${{ steps.acceptance.outputs.passed }}" in workflow
    assert "source_commit: ${{ steps.acceptance.outputs.source_commit }}" in workflow


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell required")
@pytest.mark.parametrize("fault", [
    "success", "exit", "missing-report", "invalid-json", "ok", "ok-string", "mode",
    "commit", "version", "hardware", "hardware-string", "FAIL", "NOT RUN", "missing-step",
    "duplicate-step", "unknown-step", "step-exit", "missing-asset", "multiple-runs", "stale",
])
def test_action_acceptance_report_gate_and_same_run_assets(tmp_path, fault):
    version, commit = "1.0.0", "a" * 40
    names = ["git-source", "required-tools", "versions", "build-release", "release-layout",
             "wheel-install", "sdist-install", "preflight", "source-unchanged"]
    report = {
        "ok": True, "acceptance_mode": "committed-clean-head", "source_commit": commit,
        "project_version": version, "hardware_touched": False,
        "steps": [{"name": name, "result": "PASS", "exit_code": 0} for name in names],
    }
    fields = {
        "ok": ("ok", False), "ok-string": ("ok", "true"),
        "mode": ("acceptance_mode", "working-tree"), "commit": ("source_commit", "b" * 40),
        "version": ("project_version", "9.9.9"), "hardware": ("hardware_touched", True),
        "hardware-string": ("hardware_touched", "false"),
    }
    if fault in fields:
        key, value = fields[fault]
        report[key] = value
    elif fault in ("FAIL", "NOT RUN"):
        report["steps"][-1]["result"] = fault
    elif fault == "missing-step":
        report["steps"].pop()
    elif fault == "duplicate-step":
        report["steps"][-1] = report["steps"][0]
    elif fault == "unknown-step":
        report["steps"][-1]["name"] = "other"
    elif fault == "step-exit":
        report["steps"][-1]["exit_code"] = 7
    fixture = tmp_path / "fixture"
    run = fixture / "run-current"
    artifacts = run / "release" / version
    artifacts.mkdir(parents=True)
    expected = [f"scopes-tool-{version}-windows-x64.zip", f"scopes_tool-{version}-py3-none-any.whl",
                f"scopes_tool-{version}.tar.gz", "checksums.txt"]
    for name in expected:
        (artifacts / name).write_text("current acceptance: " + name, encoding="utf-8")
    if fault == "missing-asset":
        (artifacts / expected[0]).unlink()
    if fault != "missing-report":
        (run / "report.json").write_text(
            "invalid{" if fault == "invalid-json" else json.dumps(report), encoding="utf-8",
        )
    (run / "summary.md").write_text("fixture evidence", encoding="utf-8")
    if fault == "multiple-runs":
        (fixture / "run-old").mkdir()
    if fault == "stale":
        (tmp_path / ".tmp_tests/actions-release-acceptance").mkdir(parents=True)
    # A subprocess stub produces one synthetic run; no acceptance build is executed.
    stub = r'''
function powershell.exe {
    Add-Content -LiteralPath calls.txt -Value ($args -join '|')
    New-Item -ItemType Directory -Force -Path .tmp_tests | Out-Null
    Copy-Item -LiteralPath $env:TEST_ACCEPTANCE_FIXTURE -Destination $args[-1] -Recurse
    $global:LASTEXITCODE = [int]$env:TEST_ACCEPTANCE_EXIT
}
'''
    script = _run_block(_build_step("Run and verify formal release acceptance (no hardware)"))
    script = script.replace("${{ steps.meta.outputs.version }}", version)
    script = script.replace("${{ github.sha }}", commit)
    output = tmp_path / "outputs.txt"
    result = _powershell(
        tmp_path, stub + script, TEST_ACCEPTANCE_FIXTURE=str(fixture),
        TEST_ACCEPTANCE_EXIT="7" if fault == "exit" else "0", GITHUB_OUTPUT=str(output),
    )
    if fault == "stale":
        assert not (tmp_path / "calls.txt").exists()
    else:
        calls = (tmp_path / "calls.txt").read_text().splitlines()
        assert len(calls) == 1
        assert "./scripts/release-acceptance.ps1|-OutputRoot|" in calls[0]
    if fault == "success":
        assert result.returncode == 0, result.stdout + result.stderr
        assert output.read_text(encoding="utf-8").splitlines() == [
            f"source_commit={commit}", "passed=true",
        ]
        staged = tmp_path / ".tmp_tests/actions-artifacts"
        assert {path.name for path in staged.iterdir()} == set(expected)
        assert all((staged / name).read_bytes() == (artifacts / name).read_bytes()
                   for name in expected)
    else:
        assert result.returncode != 0, result.stdout + result.stderr
        assert not output.exists()


@pytest.mark.parametrize("mode, create_draft, ref, result, passed, same_commit, allowed", [
    ("bundle", True, "main", "success", "true", True, False),
    ("desktop", True, "main", "success", "true", True, False),
    ("release", True, "main", "success", "true", True, False),
    ("release-acceptance", False, "main", "success", "true", True, False),
    ("release-acceptance", True, "topic", "success", "true", True, False),
    ("release-acceptance", True, "main", "failure", "true", True, False),
    ("release-acceptance", True, "main", "success", "", True, False),
    ("release-acceptance", True, "main", "success", "false", True, False),
    ("release-acceptance", True, "main", "success", "true", False, False),
    ("release-acceptance", True, "main", "success", "true", True, True),
])
def test_draft_job_requires_verified_acceptance(mode, create_draft, ref, result, passed,
                                               same_commit, allowed):
    draft = BUILD_WORKFLOW.read_text(encoding="utf-8").split("  draft-release:", 1)[1]
    expression = re.search(r"if: \$\{\{ (.+) \}\}", draft)[1]
    values = {
        "inputs.build_mode": mode, "inputs.create_draft": create_draft,
        "github.ref": "refs/heads/" + ref, "needs.build.result": result,
        "needs.build.outputs.acceptance_passed": passed,
        "needs.build.outputs.source_commit": "a" if same_commit else "b", "github.sha": "a",
    }
    for key, value in values.items():
        expression = expression.replace(key, repr(value))
    assert eval(expression.replace("&&", "and"), {"__builtins__": {}}) is allowed
