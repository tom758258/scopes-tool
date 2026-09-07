from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_webui.commands import command_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"


def test_channel_offset_editor_wiring() -> None:
    catalog = {entry["id"]: entry for entry in command_catalog()}
    assert catalog["channel-offset"]["editor"] == "channel-offset"

    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    assert 'import { ChannelOffsetEditor } from "/static/channel-offset-editor.js";' in app
    routing = app.split("const EDITOR_RENDERERS = {", 1)[1].split("};", 1)[0]
    assert '"channel-offset": () => channelOffsetEditor,' in routing
    assert 'elements.channelOffsetEditor.hidden = editorKind !== "channel-offset";' in app

    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="channel-offset-editor"' in html


def test_channel_offset_editor_locale_keys_exist() -> None:
    zh = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    en = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    for key in (
        "channel-offset.editor.title",
        "channel-offset.editor.description",
        "channel-offset.editor.divHeading",
        "channel-offset.editor.divHint",
        "channel-offset.editor.currentSettings",
        "channel-offset.editor.divSelection",
        "channel-offset.editor.divReadIncomplete",
    ):
        assert f'"{key}":' in zh, key
        assert f'"{key}":' in en, key


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_channel_offset_div_quick_fill_behavior(tmp_path: Path) -> None:
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
          setAttribute(k, v) { (this.attributes = this.attributes || {})[k] = String(v); }
          remove() {}
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.queueMicrotask = (fn) => { fn(); };
        // Template shapes mirror the composition contract only, not locale prose.
        const TEMPLATES = {
          "channel-offset.editor.currentSettings": "S={{scale}}|R={{range}}|U={{units}}|O={{offset}}",
          "channel-offset.editor.divSelection": "D={{div}}|V={{value}}",
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
          path.join(process.cwd(), "src/scopes_tool_webui/static/channel-offset-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class ChannelOffsetEditor", "class ChannelOffsetEditor")
          + "\nglobalThis.ChannelOffsetEditor = ChannelOffsetEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const SUMMARY = [
          { channel: 1, display: true, scale: 0.5, range: 4, offset: 0.1, units: "volt" },
          { channel: 2, display: true, scale: 1, range: 8, offset: -0.5, units: "amp" },
          { channel: 3, display: false, scale: 0.2, range: 1.6, offset: 0, units: "volt" },
          { channel: 4, display: false, scale: 0.1, range: 0.8, offset: 0, units: "volt" },
        ];
        const calls = [];
        let currentContext = "simulate||keysight-dsox4024a";
        let deferredResolve = null;
        let partialField = null;
        const hooks = {
          contextKey: () => currentContext,
          selectedCommand: () => ({ id: "channel-offset", editor: "channel-offset" }),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          async executeCommand(id, parameters, options) {
            calls.push([id, parameters, options]);
            if (id === "channel-summary") {
              if (deferredResolve !== null) {
                return new Promise((resolve) => { deferredResolve = resolve; });
              }
              if (partialField !== null) {
                const patched = SUMMARY.map((entry) => entry.channel === 1
                  ? { ...entry, [partialField]: null }
                  : entry);
                return { status: "completed", result: { result: { channels: patched } } };
              }
              return { status: "completed", result: { result: { channels: SUMMARY } } };
            }
            if (id === "channel-offset" && parameters.action === "set") {
              return { status: "completed", result: { result: { volts: parameters.volts } } };
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

        const editor = new globalThis.ChannelOffsetEditor(new FakeNode("div"), catalog, hooks);
        editor.present();

        // 1. Slider is disabled before a successful read.
        assert.deepEqual(editor.channels, [1, 2, 3, 4]);
        assert.equal(editor.divSlider.tagName, "INPUT");
        assert.equal(editor.divSlider.type, "range");
        assert.equal(editor.divSlider.min, "-4");
        assert.equal(editor.divSlider.max, "4");
        assert.equal(editor.divSlider.step, "1");
        assert.equal(editor.divSlider.value, "0");
        assert.equal(editor.divSlider.disabled, true);
        assert.equal(editor.divSlider.attributes["aria-label"], "channel-offset.editor.divHeading");
        assert.equal(editor.divTicks.length, 9);
        assert.deepEqual(
          editor.divTicks.map((tick) => tick.textContent),
          ["-4", "-3", "-2", "-1", "0", "+1", "+2", "+3", "+4"],
        );
        assert.equal(editor.selection.textContent, "");
        assert.equal(editor.divStatus.textContent, "");

        // 2. Reading the selected channel enables Div control and fills the draft.
        editor.channelSelect.value = "1";
        editor.readButton.on_click();
        await drain();
        assert.equal(calls.length, 1);
        assert.deepEqual(calls[0], ["channel-summary", {}, { intent: "readback" }]);
        assert.equal(editor.offsetInput.value, "0.1");
        assert.equal(editor.divSlider.disabled, false);
        assert.equal(
          editor.info.textContent,
          "S=F:0.5:V|R=F:4:V|U=enum.volt|O=F:0.1:V",
        );
        assert.equal(editor.divStatus.textContent, "");

        // 3. Slider +2 on a 0.5 V/div scale fills 1.0 V without executing.
        editor.divSlider.value = "2";
        editor.divSlider.on_input();
        assert.equal(editor.offsetInput.value, "1");
        assert.equal(editor.divSlider.value, "2");
        assert.equal(editor.selection.textContent, "D=+2|V=F:1:V");
        assert.equal(calls.length, 1);

        // 4. Manual numeric edits clear the quick-fill selection and reset the slider.
        editor.offsetInput.value = "0.75";
        editor.offsetInput.on_input();
        assert.equal(editor.selection.textContent, "");
        assert.equal(editor.divSlider.value, "0");
        assert.equal(editor.offsetInput.value, "0.75");
        assert.equal(editor.divSlider.disabled, false);

        // 5. Switching channels invalidates the previous channel scale.
        editor.channelSelect.value = "2";
        editor.channelSelect.on_change();
        assert.equal(editor.offsetInput.value, "");
        assert.equal(editor.divSlider.disabled, true);
        assert.equal(editor.selection.textContent, "");
        assert.equal(editor.divStatus.textContent, "");

        // 6. Reading the new channel enables the slider with its own units.
        editor.readButton.on_click();
        await drain();
        assert.equal(editor.offsetInput.value, "-0.5");
        assert.equal(editor.divSlider.disabled, false);
        assert.equal(
          editor.info.textContent,
          "S=F:1:A|R=F:8:A|U=enum.amp|O=F:-0.5:A",
        );

        // 7. A stale CH1 response must not enable the slider for CH2, nor show feedback.
        editor.channelSelect.value = "1";
        editor.channelSelect.on_change();
        deferredResolve = "armed";
        editor.readButton.on_click();
        editor.channelSelect.value = "2";
        const pendingResolve = deferredResolve;
        assert.equal(typeof pendingResolve, "function");
        deferredResolve = null;
        pendingResolve({ status: "completed", result: { result: { channels: SUMMARY } } });
        await drain();
        assert.equal(editor.divSlider.disabled, true);
        assert.equal(editor.divChannel, null);
        assert.equal(editor.divStatus.textContent, "");

        // 8. Apply writes the draft and clears the selection but keeps Div state.
        editor.channelSelect.value = "1";
        editor.readButton.on_click();
        await drain();
        assert.equal(editor.divSlider.disabled, false);
        editor.divSlider.value = "1";
        editor.divSlider.on_input();
        assert.equal(editor.offsetInput.value, "0.5");
        const callsBeforeApply = calls.length;
        editor.applyButton.on_click();
        await drain();
        assert.equal(calls.length, callsBeforeApply + 1);
        assert.deepEqual(calls[calls.length - 1], [
          "channel-offset",
          { action: "set", channel: 1, volts: 0.5 },
          { intent: "apply" },
        ]);
        assert.equal(editor.offsetInput.value, "0.5");
        assert.equal(editor.selection.textContent, "");
        assert.equal(editor.divSlider.value, "0");
        assert.equal(editor.divSlider.disabled, false);

        // 9. A partial summary never enables the slider and never falls back to volt.
        editor.channelSelect.value = "1";
        editor.channelSelect.on_change();
        editor.offsetInput.value = "0.75";
        partialField = "units";
        editor.readButton.on_click();
        await drain();
        partialField = null;
        assert.equal(editor.divSlider.disabled, true);
        assert.equal(editor.divChannel, null);
        assert.equal(editor.divUnits, null);
        assert.equal(editor.offsetInput.value, "0.75");
        assert.equal(editor.selection.textContent, "");
        assert.equal(editor.divStatus.textContent, "channel-offset.editor.divReadIncomplete");

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)

    harness_path = tmp_path / "channel-offset-editor-harness.mjs"
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
