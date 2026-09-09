from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
EDITOR_SOURCE = STATIC_ROOT / "reference-display-editor.js"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


DISPLAY_EDITOR_HARNESS = r'''
    import assert from "node:assert/strict";
    import fs from "node:fs";

    class FakeNode {
      constructor(tag = "div") {
        this.tagName = tag.toUpperCase();
        this.children = [];
        this.listeners = {};
        this.dataset = {};
        this.attributes = {};
        this.hidden = false;
        this.disabled = false;
        this.className = "";
        this.textContent = "";
        this.value = "";
        this.checked = false;
        this.type = "";
      }
      addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
      append(...nodes) { this.children.push(...nodes); }
      replaceChildren(...nodes) { this.children = [...nodes]; }
      remove() {}
      setAttribute(name, value) { this.attributes[name] = String(value); }
    }
    globalThis.document = { createElement: (tag) => new FakeNode(tag) };
    globalThis.queueMicrotask = (fn) => { fn(); };
    const TEMPLATES = {
      "enum.reference-waveform": "Reference waveform {{value}}",
    };
    globalThis.translate = (key, values = {}) => {
      let text = TEMPLATES[key] || key;
      for (const [name, value] of Object.entries(values)) {
        text = text.replaceAll(`{{${name}}}`, String(value));
      }
      return text;
    };
    globalThis.hasTranslation = (key) => key in TEMPLATES;

    const source = fs.readFileSync(process.argv[1], "utf8")
      .replace(/^import[^\n]*\r?\n/gm, "")
      .replace(/^export /gm, "")
      + "\nglobalThis.displayApi = { ReferenceDisplayEditor };";
    await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

    const { ReferenceDisplayEditor } = globalThis.displayApi;
    const submitted = [];
    const env = { available: true, busy: false, context: "simulate||model" };
    let handler = async () => ({ status: "completed" });
    const headerActions = new FakeNode("div");
    const hooks = {
      contextKey: () => env.context,
      selectedCommand: () => ({ id: "reference-display", editor: "reference-display" }),
      isAvailable: () => env.available,
      isExecutionBusy: () => env.busy,
      headerActions,
      async executeCommand(id, parameters, options) {
        submitted.push({ command: id, parameters, intent: options?.intent });
        return handler(id, parameters, options);
      },
    };
    const catalog = { commands: [], fieldsFor: () => [], optionsFor: () => [] };
    const editor = new ReferenceDisplayEditor(new FakeNode(), catalog, hooks);
    const settle = async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
    };
    const displayJob = (slot, enabled, status = "completed") => ({
      status,
      result: { result: { display: { slot, enabled } } },
    });
    '''


def run_harness(body: str) -> None:
    script = textwrap.dedent(DISPLAY_EDITOR_HARNESS) + textwrap.dedent(body)
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_reference_display_editor_shows_two_slots_with_shared_actions() -> None:
    run_harness(
        r'''
        editor.schedulePresentation();
        await settle();

        assert.deepEqual(editor.entries.map((entry) => entry.slot), [1, 2]);
        assert.ok(editor.entries.every((entry) => entry.box.type === "checkbox"));
        assert.deepEqual(
          editor.entries.map((entry) => entry.text.textContent),
          ["Reference waveform 1", "Reference waveform 2"],
        );
        assert.deepEqual(headerActions.children, [editor.refreshButton, editor.runButton]);
        assert.ok(editor.refreshButton.className.includes("secondary"));
        assert.ok(editor.runButton.className.includes("primary"));
        assert.equal(editor.heading.textContent, "reference-display.editor.displayedReferences");
        assert.equal(editor.helper.textContent, "reference-display.editor.displayHelper");
        assert.ok(editor.container.children.includes(editor.section));
        assert.equal(editor.container.children.includes(editor.refreshButton), false);
        assert.equal(editor.container.children.includes(editor.runButton), false);
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_reference_display_read_syncs_both_checkboxes() -> None:
    run_harness(
        r'''
        const states = new Map([[1, false], [2, true]]);
        handler = async (id, parameters) => displayJob(parameters.slot, states.get(parameters.slot));
        editor.schedulePresentation();
        await settle();

        await editor.read();
        assert.deepEqual(submitted, [
          { command: "reference-display", parameters: { action: "query", slot: 1 }, intent: "readback" },
          { command: "reference-display", parameters: { action: "query", slot: 2 }, intent: "readback" },
        ]);
        assert.equal(editor.boxFor(1).checked, false);
        assert.equal(editor.boxFor(2).checked, true);
        assert.equal(editor.status.textContent, "");
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_reference_display_partial_read_keeps_existing_checkboxes() -> None:
    run_harness(
        r'''
        handler = async (id, parameters) => (
          parameters.slot === 1 ? displayJob(1, true) : displayJob(2, false, "failed")
        );
        editor.schedulePresentation();
        await settle();
        editor.boxFor(1).checked = false;
        editor.boxFor(2).checked = false;

        await editor.read();
        assert.equal(editor.status.textContent, "reference-display.editor.readFailed");
        assert.equal(editor.boxFor(1).checked, false);
        assert.equal(editor.boxFor(2).checked, false);
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_reference_display_run_applies_then_shows_final_readback() -> None:
    run_harness(
        r'''
        const instrument = new Map([[1, false], [2, false]]);
        handler = async (id, parameters) => {
          if (parameters.action === "set") {
            instrument.set(parameters.slot, parameters.enabled);
            if (parameters.slot === 2 && parameters.enabled) instrument.set(1, false);
            return displayJob(parameters.slot, instrument.get(parameters.slot));
          }
          return displayJob(parameters.slot, instrument.get(parameters.slot));
        };
        editor.schedulePresentation();
        await settle();
        editor.boxFor(1).checked = true;
        editor.boxFor(2).checked = true;

        await editor.run();
        assert.deepEqual(submitted.map((entry) => entry.parameters), [
          { action: "set", slot: 1, enabled: true },
          { action: "set", slot: 2, enabled: true },
          { action: "query", slot: 1 },
          { action: "query", slot: 2 },
        ]);
        // The instrument turned slot 1 back off; the UI shows the final state.
        assert.equal(editor.boxFor(1).checked, false);
        assert.equal(editor.boxFor(2).checked, true);
        assert.equal(editor.status.textContent, "");
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_reference_display_run_failure_stops_before_remaining_slots() -> None:
    run_harness(
        r'''
        handler = async () => displayJob(1, false, "failed");
        editor.schedulePresentation();
        await settle();

        await editor.run();
        assert.equal(submitted.length, 1);
        assert.equal(submitted[0].command, "reference-display");
        assert.equal(editor.status.textContent, "reference-display.editor.runIncomplete");
        ''',
    )
