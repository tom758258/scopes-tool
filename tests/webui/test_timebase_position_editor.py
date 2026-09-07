from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_webui.commands import command_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"


def test_timebase_position_editor_wiring() -> None:
    catalog = {entry["id"]: entry for entry in command_catalog()}
    assert catalog["timebase-position"]["editor"] == "timebase-position"

    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    assert 'import { TimebasePositionEditor } from "/static/timebase-position-editor.js";' in app
    routing = app.split("const EDITOR_RENDERERS = {", 1)[1].split("};", 1)[0]
    assert '"timebase-position": () => timebasePositionEditor,' in routing
    assert 'elements.timebasePositionEditor.hidden = editorKind !== "timebase-position";' in app

    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="timebase-position-editor"' in html


def test_timebase_position_editor_locale_keys_exist() -> None:
    zh = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    en = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    for key in (
        "timebase-position.editor.title",
        "timebase-position.editor.description",
        "timebase-position.editor.divHeading",
        "timebase-position.editor.divHint",
        "timebase-position.editor.referenceNote",
        "timebase-position.editor.currentSettings",
        "timebase-position.editor.divSelection",
    ):
        assert f'"{key}":' in zh, key
        assert f'"{key}":' in en, key


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_timebase_position_div_quick_fill_behavior(tmp_path: Path) -> None:
    catalog_json = json.dumps(command_catalog())
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
            this.className = "";
            this.textContent = "";
            this.hidden = false;
            this.disabled = false;
            this.checked = false;
            this.type = "";
            this.value = "";
            this.style = {};
          }
          append(...nodes) { this.children.push(...nodes); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          addEventListener(event, handler) { this[`on_${event}`] = handler; }
          remove() {}
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.queueMicrotask = (fn) => { fn(); };
        // Template shapes mirror the composition contract only, not locale prose.
        const TEMPLATES = {
          "timebase-position.editor.currentSettings":
            "S={{scale}}|R={{reference}}|P={{position}}|SPAN={{span}}",
          "timebase-position.editor.divSelection": "D={{div}}|V={{value}}",
        };
        globalThis.translate = (key, values = {}) => {
          let text = TEMPLATES[key] || key;
          for (const [name, value] of Object.entries(values)) {
            text = text.replaceAll(`{{${name}}}`, String(value));
          }
          return text;
        };
        globalThis.hasTranslation = () => false;
        globalThis.formatEngineering = (value, unit) => `F:${String(value)}:${unit}`;

        let editorSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/timebase-position-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class TimebasePositionEditor", "class TimebasePositionEditor")
          + "\nglobalThis.TimebasePositionEditor = TimebasePositionEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const calls = [];
        let currentContext = "simulate||keysight-dsox4024a";
        let failId = null;
        const hooks = {
          contextKey: () => currentContext,
          selectedCommand: () => ({ id: "timebase-position", editor: "timebase-position" }),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          async executeCommand(id, parameters, options) {
            calls.push([id, parameters, options]);
            if (id === failId) return { status: "failed" };
            if (id === "timebase-scale") {
              return { status: "completed", result: { result: { timebase: { seconds_per_division: 0.0002 } } } };
            }
            if (id === "timebase-position") {
              if (parameters.action === "query") {
                return { status: "completed", result: { result: { timebase: { position_seconds: 0.0001 } } } };
              }
              return { status: "completed", result: { result: { timebase: { position_seconds: parameters.position_seconds } } } };
            }
            if (id === "timebase-reference") {
              return { status: "completed", result: { result: { timebase: { reference: "center" } } } };
            }
            return { status: "completed" };
          },
        };

        const catalog = {
          commands: __CATALOG__,
          fieldsFor: (command) => command.fields || [],
          optionsFor: (field) => field.options || [],
        };

        const drain = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
        };

        const editor = new globalThis.TimebasePositionEditor(new FakeNode("div"), catalog, hooks);
        editor.present();

        // 1. Div control is disabled before a successful read.
        assert.equal(editor.divButtons.length, 11);
        assert.deepEqual(
          editor.divButtons.map((button) => button.textContent),
          ["-5", "-4", "-3", "-2", "-1", "0", "+1", "+2", "+3", "+4", "+5"],
        );
        editor.divButtons.forEach((button) => assert.equal(button.type, "button"));
        editor.divButtons.forEach((button) => assert.equal(button.disabled, true));
        assert.equal(editor.selection.textContent, "");

        // 2. A successful read enables Div control and fills the draft.
        currentContext = "simulate||keysight-dsox4024a";
        editor.readButton.on_click();
        await drain();
        assert.equal(calls.length, 3);
        assert.deepEqual(calls[0][0], "timebase-scale");
        assert.deepEqual(calls[1][0], "timebase-position");
        assert.deepEqual(calls[2][0], "timebase-reference");
        assert.equal(editor.positionInput.value, "0.0001");
        editor.divButtons.forEach((button) => assert.equal(button.disabled, false));
        assert.equal(
          editor.info.textContent,
          "S=F:0.0002:s|R=enum.center|P=F:0.0001:s|SPAN=F:0.002:s",
        );

        // 3. +3 div fills the numeric draft without executing a new command.
        const plusThree = editor.divButtons.find((button) => button.textContent === "+3");
        plusThree.on_click();
        assert.equal(editor.positionInput.value, "0.0006");
        assert.equal(editor.selection.textContent, "D=+3|V=F:0.0006:s");
        assert.equal(calls.length, 3);

        // 4. Manual numeric edits clear the quick-fill selection.
        editor.positionInput.value = "0.00045";
        editor.positionInput.on_input();
        assert.equal(editor.selection.textContent, "");
        assert.equal(editor.positionInput.value, "0.00045");
        editor.divButtons.forEach((button) => assert.equal(button.disabled, false));

        // 5. A failed read keeps Div control disabled without touching the draft.
        failId = "timebase-scale";
        editor.readButton.on_click();
        await drain();
        editor.divButtons.forEach((button) => assert.equal(button.disabled, true));
        assert.equal(editor.positionInput.value, "0.00045");
        assert.equal(editor.selection.textContent, "");
        failId = null;

        // 6. A context change invalidates the read-derived Div state.
        editor.readButton.on_click();
        await drain();
        editor.divButtons.forEach((button) => assert.equal(button.disabled, false));
        currentContext = "simulate|RESOURCE-B|keysight-dsox4024a";
        editor.present();
        editor.divButtons.forEach((button) => assert.equal(button.disabled, true));
        assert.equal(editor.positionInput.value, "");
        assert.equal(editor.selection.textContent, "");

        // 7. Apply writes the draft and clears the selection but keeps Div state.
        currentContext = "simulate||keysight-dsox4024a";
        editor.readButton.on_click();
        await drain();
        const plusTwo = editor.divButtons.find((button) => button.textContent === "+2");
        plusTwo.on_click();
        assert.equal(editor.positionInput.value, "0.0004");
        const callsBeforeApply = calls.length;
        editor.applyButton.on_click();
        await drain();
        assert.equal(calls.length, callsBeforeApply + 1);
        assert.deepEqual(calls[calls.length - 1], [
          "timebase-position",
          { action: "set", position_seconds: 0.0004 },
          { intent: "apply" },
        ]);
        assert.equal(editor.positionInput.value, "0.0004");
        assert.equal(editor.selection.textContent, "");
        editor.divButtons.forEach((button) => assert.equal(button.disabled, false));

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)

    harness_path = tmp_path / "timebase-position-editor-harness.mjs"
    harness_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout
    assert json.loads(completed.stdout) == {"ok": True}
