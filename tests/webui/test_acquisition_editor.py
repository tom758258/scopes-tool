from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

import scopes_tool_webui.commands as commands_module


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_acquisition_control_composite_dispatch_and_wiring(tmp_path: Path) -> None:
    catalog_json = json.dumps(commands_module.command_catalog())
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    app_source = read_static("app.js")
    index_source = read_static("index.html")

    assert "acquisition: () => acquisitionEditor," in app_source
    assert 'id="acquisition-editor"' in index_source
    for key in (
        '"command.acquisition-control": "Acquisition Control"',
        '"command.acquisition": "Acquisition Settings"',
        '"description.acquisition-control":',
    ):
        assert key in english, key
    for key in (
        '"command.acquisition-control": "擷取控制"',
        '"command.acquisition": "擷取設定"',
        '"description.acquisition-control":',
    ):
        assert key in chinese, key
    for key in (
        '"acquisition.editor.title":',
        '"acquisition.editor.description":',
    ):
        assert key in english, key
        assert key in chinese, key

    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

        class FakeNode {
          constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.className = ""; this.textContent = ""; this.disabled = false; }
          append(...nodes) { this.children.push(...nodes); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          addEventListener(_name, handler) { this.handler = handler; }
          setAttribute() {}
          remove() {}
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.queueMicrotask = (fn) => { fn(); };
        globalThis.translate = (key) => key;
        globalThis.CommandForm = class CommandForm {
          constructor(container, _catalog) {
            this.container = container;
            this.command = null;
            this.formDisabled = false;
            this.nextValues = {
              trigger_timeout_seconds: 5.0,
              force_trigger_on_timeout: false,
              trigger_poll_interval_ms: 100,
            };
          }
          render(command) { this.command = command; }
          values() { return this.nextValues; }
          setDisabled(disabled) { this.formDisabled = disabled; }
        };

        const calls = [];
        let executionBusy = false;
        const hooks = {
          contextKey: () => "simulate||keysight-dsox4024a",
          selectedCommand: () => ({ id: "acquisition-control", editor: "acquisition" }),
          isAvailable: () => true,
          isCommandAvailable: () => true,
          isExecutionBusy: () => executionBusy,
          async executeCommand(id, parameters, options) {
            calls.push([id, parameters, options]);
            return { status: "completed", job_id: "job-1" };
          },
        };
        const catalog = {
          commands: __CATALOG__,
          commandLabel: (command) => command.id,
          fieldsFor: (command) => command.fields,
          optionsFor: (field) => field.options || [],
        };

        let editorSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/acquisition-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class AcquisitionEditor", "class AcquisitionEditor")
          + "\nglobalThis.AcquisitionEditor = AcquisitionEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const editor = new globalThis.AcquisitionEditor(new FakeNode("div"), catalog, hooks);
        editor.present();
        assert.deepEqual(
          editor.controlButtons.map((entry) => entry.id),
          ["run", "single", "stop-acquisition", "force-trigger"],
        );
        assert.equal(editor.singleWaitForm.command.id, "single-wait");
        assert.equal(editor.singleWaitForm.container.className, "command-form");

        await editor.controlButtons[0].button.handler();
        assert.deepEqual(calls[0], ["run", {}, undefined]);

        await editor.submitSingleWait();
        assert.deepEqual(calls[1], ["single-wait", {
          trigger_timeout_seconds: 5.0,
          force_trigger_on_timeout: false,
          trigger_poll_interval_ms: 100,
        }, { intent: "command" }]);

        editor.singleWaitForm.nextValues = null;
        await editor.submitSingleWait();
        assert.equal(calls.length, 2);

        executionBusy = true;
        editor.applyBusyState();
        assert.ok(editor.controlButtons.every((entry) => entry.button.disabled));
        assert.equal(editor.singleWaitButton.disabled, true);
        assert.equal(editor.singleWaitForm.formDisabled, true);

        // Single-wait button should be primary; control buttons stay secondary.
        assert.ok(editor.singleWaitButton.className.includes("primary"));
        assert.ok(!editor.singleWaitButton.className.includes("secondary"));
        for (const entry of editor.controlButtons) {
          assert.ok(entry.button.className.includes("secondary"));
          assert.ok(!entry.button.className.includes("primary"));
        }

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)
    harness_path = tmp_path / "acquisition-editor-harness.mjs"
    harness_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"ok": True}
