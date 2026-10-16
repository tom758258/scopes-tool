"""Verify that expensive Windows CI jobs are selected by meaningful changes.

Model the positive/exclusion matching contract of dorny/paths-filter configured
with predicate-quantifier=some-with-excludes, without binding tests to YAML layout.
"""

from fnmatch import fnmatchcase
from pathlib import Path

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


def test_manual_build_only_offers_non_release_outputs():
    workflow = BUILD_WORKFLOW.read_text(encoding="utf-8")
    assert "  workflow_dispatch:\n" in workflow
    assert "  pull_request:" not in workflow
    assert "  push:" not in workflow
    assert "          - bundle\n" in workflow
    assert "          - desktop\n" in workflow
    assert "          - release\n" not in workflow
    assert "build_windows_bundle.ps1" in workflow
    assert "build_desktop.ps1" in workflow
    assert "scripts/ci_packaging_smoke.py" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "gh release" not in workflow
