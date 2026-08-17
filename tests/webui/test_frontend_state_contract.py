from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    body_start = source.index("{", start)
    depth = 0
    for index in range(body_start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[body_start:index + 1]
    raise AssertionError(f"Unclosed function: {signature}")


def extract_css_rule(source: str, selector: str) -> str:
    start = source.index(selector)
    body_start = source.index("{", start)
    end = source.index("}", body_start)
    return source[body_start:end + 1]


def test_identity_is_bound_to_the_current_execution_context() -> None:
    source = read_static("device-resource.js")

    assert "this.identityContext = null;" in source
    assert "function sameContext(left, right)" in source
    context_snapshot = extract_function(source, "function contextSnapshot(context)")
    assert 'mode: context?.mode || null' in context_snapshot
    assert 'resource: context?.resource || null' in context_snapshot
    assert 'model_id: context?.model_id || null' in context_snapshot
    assert "this.clearIdentity();" in source
    assert "changed(true);" in source
    assert "setIdentity(identity, associatedContext = this.context())" in source
    assert "sameContext(this.context(), associatedContext)" in source
    changed = extract_function(source, "changed(forceIdentityClear = false)")
    assert "if (forceIdentityClear || contextChanged)" in changed
    assert "this.clearIdentity();" in changed
    assert "this.clearIdentity();" in extract_function(source, "async scan()")


def test_empty_scan_has_a_distinct_compact_detection_presentation() -> None:
    source = read_static("device-resource.js")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    detection_summary = extract_function(source, "  detectionSummary(context)")
    empty_branch = 'this.scanStatus === "empty"'
    assert empty_branch in detection_summary
    assert 'translate("device.detection.noResources")' in detection_summary
    assert detection_summary.index(empty_branch) < detection_summary.index("hasCurrentIdentity")
    assert 'this.scanStatus = resources.length ? "scanned" : "empty";' in source
    assert '"device.detection.noResources": "Detection status: no resources found"' in english
    assert '"device.detection.noResources": "偵測狀態：未找到資源"' in chinese
    assert '"device.detection.notIdentified"' in detection_summary


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
    icon_button = extract_css_rule(styles, ".icon-button")
    utility_button = extract_css_rule(styles, ".utility-icon-button")

    assert "display: inline-flex;" in icon_button
    assert "align-items: center;" in icon_button
    assert "justify-content: center;" in icon_button
    assert "width: 32px;" in icon_button
    assert "min-width: 32px;" in icon_button
    assert "height: 32px;" in icon_button
    assert "min-height: 32px;" in icon_button
    assert "padding: 0;" in icon_button
    assert "font-size:" not in icon_button
    assert "line-height:" not in icon_button
    assert "border-radius: 50%;" in utility_button
    assert ".execution-mode-badge.mode-live { border-color: var(--line-strong); background: transparent; color: var(--muted); }" in styles


def test_summary_uses_only_scopes_supported_states() -> None:
    english = read_static("locale_en.js")

    assert '"device.summary.live": "{{mode}} / VISA resource: {{resource}} / {{detection}}"' in english
    assert '"device.detection.notScanned": "Detection status: not scanned"' in english
    assert '"device.detection.scanFailed": "Detection status: scan failed: {{error}}"' in english
    assert '"device.summary.planning": "{{mode}} / Planning model: {{model}} / Real VISA resource: not used"' in english
    assert "Expected Model guard" not in english
    assert "Connection scope" not in english
