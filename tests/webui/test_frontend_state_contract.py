from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_identity_is_bound_to_the_current_execution_context() -> None:
    source = read_static("device-resource.js")

    assert "this.identityContext = null;" in source
    assert "function sameContext(left, right)" in source
    assert "this.clearIdentity();" in source
    assert "changed(true);" in source
    assert "setIdentity(identity, associatedContext = this.context())" in source
    assert "sameContext(this.context(), associatedContext)" in source


def test_scan_failure_is_included_in_the_compact_device_presentation() -> None:
    source = read_static("device-resource.js")

    assert 'this.scanStatus = "failed";' in source
    assert '"device.detection.scanFailed"' in source
    assert "this.elements.summary.title = summary;" in source


def test_workspace_and_live_command_states_have_separate_owners() -> None:
    source = read_static("app.js")

    assert "let workspaceExecutionState = { key: \"device.ready\" };" in source
    assert "let liveCommandState = { key: \"device.ready\" };" in source
    assert "workspaceExecutionState = { ...state };" in source
    assert "liveCommandState = { ...state };" in source
    command_state_handler = source.split("function setCommandState(state) {", 1)[1].split("\n}", 1)[0]
    assert "liveCommandState = { ...state };" in command_state_handler
    assert "workspaceExecutionState =" not in command_state_handler
    assert "renderExecutionStatus();" in source
    assert "const commandStatus = liveCommandState.status;" in source


def test_live_mode_badge_is_neutral_and_utility_glyphs_are_centered() -> None:
    styles = read_static("styles.css")

    assert "display: inline-flex;" in styles
    assert "align-items: center;" in styles
    assert "justify-content: center;" in styles
    assert "width: 32px;" in styles
    assert ".execution-mode-badge.mode-live { border-color: var(--line-strong); background: transparent; color: var(--muted); }" in styles


def test_summary_uses_only_scopes_supported_states() -> None:
    english = read_static("locale_en.js")

    assert '"device.summary.live": "{{mode}} / VISA resource: {{resource}} / {{detection}}"' in english
    assert '"device.detection.notScanned": "Detection status: not scanned"' in english
    assert '"device.detection.scanFailed": "Detection status: scan failed: {{error}}"' in english
    assert '"device.summary.planning": "{{mode}} / Planning model: {{model}} / Real VISA resource: not used"' in english
    assert "Expected Model guard" not in english
    assert "Connection scope" not in english
