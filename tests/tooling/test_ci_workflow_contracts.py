"""Protect expensive Windows CI selection without freezing implementation details."""

from fnmatch import fnmatchcase
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TESTS_WORKFLOW = ROOT / ".github/workflows/tests.yml"
BUILD_WORKFLOW = ROOT / ".github/workflows/build-windows.yml"


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


def _affected(path: str) -> tuple[bool, bool]:
    filters = _change_filters()
    return tuple(
        any(fnmatchcase(path, pattern) for pattern in filters[name])
        for name in ("validation", "packaging")
    )


def test_windows_change_detection_limits_expensive_jobs() -> None:
    assert set(_change_filters()) == {"validation", "packaging"}
    assert _affected("README.md") == (False, False)
    assert _affected("docs/core/integration.md") == (False, False)
    assert _affected("src/scopes_tool_core/drivers/keysight.py") == (True, True)
    assert _affected("src/scopes_tool_cli/cli.py") == (True, True)
    assert _affected("src/scopes_tool_webui/static/app.js") == (False, True)
    assert _affected("desktop/main.cjs") == (False, True)
    assert _affected("scripts/live-autoscale-check.ps1") == (True, False)
    assert _affected("scripts/build_desktop.ps1") == (False, True)
    assert _affected("scripts/scopes-tool-windows.spec") == (False, True)
    assert _affected("scripts/ci_packaging_smoke.py") == (False, True)
    assert _affected("pyproject.toml") == (True, True)
    assert _affected("uv.lock") == (True, True)


def test_ci_keeps_pr_and_main_checks_while_selecting_windows_jobs() -> None:
    workflow = TESTS_WORKFLOW.read_text(encoding="utf-8")
    assert "  pull_request:\n" in workflow
    assert "  push:\n" in workflow
    assert "  workflow_dispatch:" not in workflow
    assert "base: ${{ github.event.repository.default_branch }}" in workflow
    assert "needs.detect-windows-validation-changes.outputs.validation == 'true'" in workflow
    assert "needs.detect-windows-validation-changes.outputs.packaging == 'true'" in workflow
    assert "scripts/ci_packaging_smoke.py --mode desktop" in workflow


def test_manual_build_only_offers_non_release_outputs() -> None:
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
