from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_webui.commands import command_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"


def test_workbench_header_text_sets_matching_title() -> None:
    app_source = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    selection_source = app_source.split("function syncCommandSelection(", 1)[1].split(
        "\nfunction invalidateGenericFormOwnership()", 1
    )[0]
    assert "elements.selectedCommand.textContent = selectedTitle;" in selection_source
    assert "elements.selectedCommand.title = selectedTitle;" in selection_source
    assert "elements.commandDescription.textContent = selectedDescription;" in selection_source
    assert "elements.commandDescription.title = selectedDescription;" in selection_source
    assert "elements.commandSupportReason.title = supportReason;" in selection_source


def test_workbench_field_helper_texts_exist() -> None:
    zh = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    en = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    for key in (
        "timebase-position.editor.positionHelp",
        "channel-scale-range.editor.channelHelp",
        "channel-offset.editor.channelHelp",
        "channel-offset.editor.valueHelp",
        "help.measure-install.source_channel",
        "help.measure-install.item",
    ):
        assert f'"{key}":' in zh, key
        assert f'"{key}":' in en, key

    timebase = (STATIC_ROOT / "timebase-position-editor.js").read_text(encoding="utf-8")
    assert 'translate("timebase-position.editor.positionHelp")' in timebase
    scale_range = (STATIC_ROOT / "channel-scale-range-editor.js").read_text(encoding="utf-8")
    assert 'translate("channel-scale-range.editor.channelHelp")' in scale_range
    offset = (STATIC_ROOT / "channel-offset-editor.js").read_text(encoding="utf-8")
    assert 'translate("channel-offset.editor.channelHelp")' in offset
    assert 'translate("channel-offset.editor.valueHelp")' in offset

    catalog = {entry["id"]: entry for entry in command_catalog()}
    install_fields = {field["name"]: field for field in catalog["measure-install"]["fields"]}
    assert install_fields["source_channel"].get("help_key") == "measure-install.source_channel"
    assert install_fields["item"].get("help_key") == "measure-install.item"


def test_single_command_actions_use_workspace_header() -> None:
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    for editor in (
        "timebasePositionEditor",
        "channelScaleRangeEditor",
        "channelOffsetEditor",
    ):
        assert f"if ({editor}?.readButton)" in app
        assert f"if ({editor}?.applyButton)" in app
    for editor_file in (
        "timebase-position-editor.js",
        "channel-scale-range-editor.js",
        "channel-offset-editor.js",
    ):
        source = (STATIC_ROOT / editor_file).read_text(encoding="utf-8")
        assert "this.hooks.headerActions.append(this.readButton, this.applyButton)" in source


def test_channel_label_actions_live_in_first_section() -> None:
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    workspace = html.split('<div class="workspace-content">', 1)[1]
    form_pos = workspace.index('id="command-form"')
    actions_pos = workspace.index('id="channel-label-actions"')
    visibility_pos = workspace.index('id="channel-label-visibility"')
    assert form_pos < actions_pos < visibility_pos

    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    assert 'selected?.id === "channel-label"' in app
    assert "channelLabelReadButton" in app
    assert "channelLabelApplyButton" in app
    # Header buttons stay hidden for channel-label so they cannot read as whole-card actions.
    assert "|| channelLabelSelected" in app

    visibility = (STATIC_ROOT / "label-visibility.js").read_text(encoding="utf-8")
    assert 'this.applyButton.className = "primary trigger-editor-action"' in visibility


def test_pc_output_note_lives_in_parameters_area() -> None:
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    workspace = html.split('<div class="workspace-content">', 1)[1]
    heading_pos = workspace.index('id="form-heading"')
    note_pos = workspace.index('id="pc-output-command-note"')
    form_pos = workspace.index('id="command-form"')
    assert heading_pos < note_pos < form_pos
    assert "pc-output-note-box" in html

    css = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
    assert ".pc-output-note-box" in css
    assert ".channel-label-actions" in css

    note = (STATIC_ROOT / "pc-output.js").read_text(encoding="utf-8")
    assert 'translate("pcOutput.commandNote"' in note


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_channel_scale_range_header_actions_behavior(tmp_path: Path) -> None:
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

        class FakeNode {
          constructor(tag) {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.attributes = {};
            this.className = "";
            this.textContent = "";
            this.disabled = false;
            this.hidden = false;
            this.style = {};
            this.value = "";
            this.type = "";
            const classSet = () => new Set(this.className.split(" ").filter(Boolean));
            const writeBack = (set) => { this.className = [...set].join(" "); };
            this.classList = {
              add: (...names) => { const s = classSet(); names.forEach((n) => s.add(n)); writeBack(s); },
              remove: (...names) => { const s = classSet(); names.forEach((n) => s.delete(n)); writeBack(s); },
              toggle: (name, force) => {
                const s = classSet();
                const want = force === undefined ? !s.has(name) : Boolean(force);
                if (want) s.add(name); else s.delete(name);
                writeBack(s);
                return want;
              },
              contains: (name) => classSet().has(name),
            };
          }
          append(...nodes) { this.children.push(...nodes); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          addEventListener(event, handler) { this[`on_${event}`] = handler; }
          setAttribute(k, v) { this.attributes[k] = String(v); }
          getAttribute(k) { return this.attributes[k]; }
          remove() {}
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.queueMicrotask = (fn) => { fn(); };
        globalThis.translate = (key) => key;
        globalThis.hasTranslation = () => false;
        globalThis.formatEngineering = (value) => String(value);

        let editorSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/channel-scale-range-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class ChannelScaleRangeEditor", "class ChannelScaleRangeEditor")
          + "\nglobalThis.ChannelScaleRangeEditor = ChannelScaleRangeEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const catalog = {
          commands: [{ id: "channel-scale-range" }, { id: "channel-scale" }],
          fieldsFor: () => [],
          optionsFor: () => [],
        };
        const baseHooks = {
          contextKey: () => "simulate||keysight-dsox4024a",
          selectedCommand: () => ({ id: "channel-scale-range", editor: "channel-scale-range" }),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          executeCommand: async () => ({ status: "completed" }),
        };
        const headerActions = new FakeNode("div");
        const editor = new globalThis.ChannelScaleRangeEditor(
          new FakeNode("div"), catalog, { ...baseHooks, headerActions },
        );
        assert.deepEqual(headerActions.children, [editor.readButton, editor.applyButton]);
        assert.equal(editor.container.children.includes(editor.actions), false);

        const local = new globalThis.ChannelScaleRangeEditor(
          new FakeNode("div"), catalog, { ...baseHooks, headerActions: null },
        );
        assert.deepEqual(local.actions.children, [local.readButton, local.applyButton]);
        assert.ok(local.container.children.includes(local.actions));
        console.log(JSON.stringify({ ok: true }));
        '''
    )
    harness_path = tmp_path / "scale-range-header-harness.mjs"
    harness_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_channel_label_inline_actions_delegate_to_generic_buttons(tmp_path: Path) -> None:
    app_source = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    build_source = "function buildChannelLabelActions() {" + (
        app_source.split("function buildChannelLabelActions() {", 1)[1].split(
            "\nfunction renderChannelLabelActions()", 1
        )[0]
    )
    render_source = "function renderChannelLabelActions() {" + (
        app_source.split("function renderChannelLabelActions() {", 1)[1].split(
            "\nfunction syncWorkspaceHeaderActions(", 1
        )[0]
    )
    # Static contract: inline handlers only delegate via .click(), no second payload path.
    assert "elements.refresh.click()" in build_source
    assert "elements.execute.click()" in build_source
    assert "executeCommand(" not in build_source
    assert "executeCommand(" not in render_source
    # Static contract: disabled state mirrors the generic header buttons.
    assert "channelLabelReadButton.disabled = elements.refresh.disabled" in app_source
    assert "channelLabelApplyButton.disabled = elements.execute.disabled" in app_source

    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";

        class FakeNode {
          constructor(tag) {
            this.tagName = String(tag).toUpperCase();
            this.children = [];
            this.dataset = {};
            this.className = "";
            this.textContent = "";
            this.hidden = false;
            this.disabled = false;
            this.type = "";
            this.style = {};
            this.listeners = {};
          }
          append(...nodes) { this.children.push(...nodes); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          addEventListener(event, handler) { (this.listeners[event] ||= []).push(handler); }
          click() {
            for (const handler of this.listeners.click || []) handler({ type: "click" });
          }
          setAttribute() {}
          remove() {}
        }

        let prefix = "zh";
        globalThis.translate = (key) => `${prefix}:${key}`;
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        let refreshClicks = 0;
        let executeClicks = 0;
        globalThis.elements = {
          channelLabelActions: new FakeNode("div"),
          refresh: { click() { refreshClicks += 1; } },
          execute: { click() { executeClicks += 1; } },
        };
        let channelLabelReadButton = null;
        let channelLabelApplyButton = null;

        __BUILD_SOURCE__
        __RENDER_SOURCE__
        globalThis.buildChannelLabelActions = buildChannelLabelActions;
        globalThis.renderChannelLabelActions = renderChannelLabelActions;

        globalThis.buildChannelLabelActions();
        assert.deepEqual(
          globalThis.elements.channelLabelActions.children,
          [channelLabelReadButton, channelLabelApplyButton],
        );
        assert.equal(channelLabelReadButton.textContent, "zh:actions.readSettings");
        assert.equal(channelLabelApplyButton.textContent, "zh:actions.apply");

        channelLabelReadButton.click();
        assert.equal(refreshClicks, 1);
        assert.equal(executeClicks, 0);
        channelLabelApplyButton.click();
        assert.equal(refreshClicks, 1);
        assert.equal(executeClicks, 1);

        prefix = "en";
        globalThis.renderChannelLabelActions();
        assert.equal(channelLabelReadButton.textContent, "en:actions.readSettings");
        assert.equal(channelLabelApplyButton.textContent, "en:actions.apply");

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__BUILD_SOURCE__", build_source).replace("__RENDER_SOURCE__", render_source)
    harness_path = tmp_path / "channel-label-delegation-harness.mjs"
    harness_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout
