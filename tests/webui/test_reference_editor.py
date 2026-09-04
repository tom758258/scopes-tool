from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
EDITOR_SOURCE = STATIC_ROOT / "reference-editor.js"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_reference_editor_wiring_and_localization() -> None:
    app = read_static("app.js")
    html = read_static("index.html")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert 'import { ReferenceEditor } from "/static/reference-editor.js";' in app
    assert 'id="reference-editor" class="reference-editor trigger-editor" hidden' in html
    assert 'reference: () => referenceEditor,' in app
    assert 'elements.referenceEditor.hidden = editorKind !== "reference";' in app
    assert 'referenceEditor?.schedulePresentation();' in app
    for key in (
        "command.reference-waveform",
        "description.reference-waveform",
        "reference.editor.title",
        "reference.editor.saveAndDisplay",
        "reference.editor.currentLoaded",
        "reference.editor.readFailed",
        "command.save-export",
        "description.save-export",
    ):
        assert f'"{key}":' in english
        assert f'"{key}":' in chinese
    assert '"reference.editor.title": "Reference waveform"' in english
    assert '"save-export.editor.title": "Save / Export"' in english
    assert '"reference.editor.title": "參考波形"' in chinese
    assert '"save-export.editor.title": "儲存 / 匯出"' in chinese
    english_reference_help = next(
        line for line in english.splitlines()
        if '"help.reference-label.label":' in line
    )
    chinese_reference_help = next(
        line for line in chinese.splitlines()
        if '"help.reference-label.label":' in line
    )
    assert "Set the reference waveform label" in english_reference_help
    assert (
        "does not control whether the label text is shown on the instrument display"
        in english_reference_help
    )
    assert "設定參考波形的標籤名稱" in chinese_reference_help
    assert "不控制標籤文字是否顯示在儀器畫面上" in chinese_reference_help


REFERENCE_EDITOR_HARNESS = r'''
    import assert from "node:assert/strict";
    import fs from "node:fs";

    class FakeNode {
      constructor(tag = "div") {
        this.tagName = tag.toUpperCase();
        this.children = [];
        this.listeners = {};
        this.dataset = {};
        this.hidden = false;
        this.disabled = false;
        this.className = "";
        this.textContent = "";
      }
      addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
      dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
      append(...nodes) { this.children.push(...nodes); }
      replaceChildren(...nodes) { this.children = [...nodes]; }
      remove() {}
      querySelector(selector) {
        const field = selector.match(/^\[data-field="([^"]+)"\]$/)?.[1];
        const visit = (node) => {
          if (field && node.dataset?.field === field) return node;
          for (const child of node.children || []) {
            const found = visit(child);
            if (found) return found;
          }
          return null;
        };
        return visit(this);
      }
    }
    globalThis.document = { createElement: (tag) => new FakeNode(tag) };
    globalThis.translate = (key) => key;

    globalThis.CommandForm = class CommandForm {
      constructor(container) {
        this.container = container;
        this.command = null;
        this.disabled = false;
        this.syncCalls = [];
        this.clearCalls = 0;
        this.valuesResult = {};
      }
      render(command) {
        this.command = command;
        if (command.id === "reference-query") {
          this.valuesResult = { slot: 1 };
          const select = new FakeNode("select");
          select.dataset.field = "slot";
          this.container.append(select);
        } else if (command.id === "reference-save") {
          this.valuesResult = { source_channel: 1 };
        } else if (command.id === "reference-display") {
          this.valuesResult = { action: "set", enabled: true };
        } else if (command.id === "reference-label") {
          this.valuesResult = { action: "set", label: "BASE" };
        }
      }
      values() { return this.valuesResult; }
      setDisabled(value) { this.disabled = value; }
      syncResult(job, preserveDirty) { this.syncCalls.push([job.job_id, preserveDirty]); }
      clearDirty() { this.clearCalls += 1; }
    };

    const source = fs.readFileSync(process.argv[1], "utf8")
      .replace(/^import[^\n]*\r?\n/gm, "")
      .replace(/^export /gm, "")
      + "\nglobalThis.referenceApi = { ReferenceEditor };";
    await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

    const setting = {
      kind: "setting", action: "apply", action_field: "action",
      apply_value: "set", query_value: "query", query_fields: ["slot"],
    };
    const def = (id, presentation, fields) => ({
      id, editor: "reference", category: "Reference", label: id,
      modes: ["live", "simulate"], presentation, fields,
    });
    const commands = [
      def("reference-save", { kind: "command", action: "save" }, [
        { name: "slot", type: "integer", options: [1, 2], default: 1 },
        { name: "source_channel", type: "integer", options: [1, 2, 3, 4] },
      ]),
      def("reference-display", setting, [
        { name: "action", type: "enum" }, { name: "slot", type: "integer" },
        { name: "enabled", type: "boolean" },
      ]),
      def("reference-label", setting, [
        { name: "action", type: "enum" }, { name: "slot", type: "integer" },
        { name: "label", type: "string" },
      ]),
      def("reference-clear", { kind: "command", action: "clear" }, [
        { name: "slot", type: "integer" },
      ]),
      def("reference-query", { kind: "command", action: "read" }, [
        { name: "slot", type: "integer", options: [1, 2], default: 1 },
      ]),
      def("reference-waveform", { kind: "command", action: "run" }, []),
    ];
    commands.at(-1).presentation_only = true;
    const catalog = {
      commands,
      fieldsFor: (command) => command.fields,
      supported: () => true,
      commandLabel: (command) => command.label,
      description: (command) => `description.${command.id}`,
    };
    const env = { available: false, executionBusy: false, contextKey: "live||" };
    const submitted = [];
    const commandStatuses = [];
    const hooks = {
      executeCommand: async (command, parameters, options) => {
        submitted.push({ command, parameters, intent: options?.intent });
        return {
          job_id: `job-${submitted.length}`,
          status: commandStatuses.shift() || "completed",
          result: { result: { reference: { displayed: true, label: "BASE" } } },
        };
      },
      headerActions: new FakeNode(),
      isAvailable: () => env.available,
      isExecutionBusy: () => env.executionBusy,
      contextKey: () => env.contextKey,
      selectedCommand: () => commands.find((command) => command.id === "reference-waveform"),
    };
    const editor = new globalThis.referenceApi.ReferenceEditor(
      new FakeNode(), catalog, hooks,
    );
    const settle = async () => {
      await Promise.resolve();
      await Promise.resolve();
    };
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_reference_workspace_stays_visible_when_unavailable_and_routes_existing_commands() -> None:
    script = textwrap.dedent(REFERENCE_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        editor.schedulePresentation();
        await settle();
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "reference-save", "reference-display", "reference-label", "reference-clear",
        ]);
        assert.equal(editor.refreshButton.disabled, true);
        assert.equal(editor.slotForm.disabled, true);
        assert.ok(editor.entries.every((entry) => entry.button.disabled));
        assert.deepEqual(submitted, []);
        await editor.refresh();
        assert.deepEqual(submitted, []);

        env.available = true;
        editor.present();
        assert.equal(editor.refreshButton.disabled, false);
        assert.equal(editor.slotForm.disabled, false);
        await editor.refresh();
        assert.deepEqual(submitted, [{
          command: "reference-query", parameters: { slot: 1 }, intent: "readback",
        }]);
        assert.equal(editor.readStatus.textContent, "reference.editor.currentLoaded");
        assert.equal(
          editor.entries.find((entry) => entry.id === "reference-save").form.syncCalls.length,
          0,
        );
        assert.equal(
          editor.entries.find((entry) => entry.id === "reference-display").form.syncCalls.length,
          1,
        );
        assert.equal(
          editor.entries.find((entry) => entry.id === "reference-label").form.syncCalls.length,
          1,
        );

        submitted.length = 0;
        const save = editor.entries.find((entry) => entry.id === "reference-save");
        await editor.saveAndDisplay(save);
        assert.deepEqual(submitted, [
          {
            command: "reference-save",
            parameters: { source_channel: 1, slot: 1 },
            intent: "command",
          },
          {
            command: "reference-display",
            parameters: { action: "set", slot: 1, enabled: true },
            intent: "apply",
          },
          {
            command: "reference-query",
            parameters: { slot: 1 },
            intent: "readback",
          },
        ]);

        for (const id of ["reference-display", "reference-label", "reference-clear"]) {
          submitted.length = 0;
          const entry = editor.entries.find((item) => item.id === id);
          await editor.submit(entry);
          assert.equal(submitted[0].command, id);
          assert.equal(submitted[0].parameters.slot, 1);
          assert.equal(submitted[1].command, "reference-query");
          assert.equal(submitted[1].intent, "readback");
        }
        assert.deepEqual(
          editor.entries.find((entry) => entry.id === "reference-save").form.valuesResult,
          { source_channel: 1 },
        );
        assert.equal(
          editor.entries.find((entry) => entry.id === "reference-display").form
            .command.presentation.readback_fields.enabled,
          "displayed",
        );
        ''')
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_reference_editor_does_not_submit_invalid_form_and_clear_needs_no_form() -> None:
    script = textwrap.dedent(REFERENCE_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.available = true;
        editor.schedulePresentation();
        await settle();

        const save = editor.entries.find((entry) => entry.id === "reference-save");
        save.form.valuesResult = null;
        assert.equal(await editor.saveAndDisplay(save), null);
        assert.equal(submitted.length, 0);

        const clear = editor.entries.find((entry) => entry.id === "reference-clear");
        assert.equal(clear.form, null);
        const job = await editor.submit(clear);
        assert.equal(job.status, "completed");
        assert.equal(submitted[0].command, "reference-clear");
        assert.deepEqual(submitted[0].parameters, { slot: 1 });
        ''')
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_reference_save_failure_short_circuits_save_and_display() -> None:
    script = textwrap.dedent(REFERENCE_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.available = true;
        editor.schedulePresentation();
        await settle();

        commandStatuses.push("failed");
        const save = editor.entries.find((entry) => entry.id === "reference-save");
        const job = await editor.saveAndDisplay(save);
        assert.equal(job.status, "failed");
        assert.deepEqual(submitted, [{
          command: "reference-save",
          parameters: { source_channel: 1, slot: 1 },
          intent: "command",
        }]);
        assert.equal(save.form.clearCalls, 0);
        ''')
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_reference_display_failure_stops_before_readback() -> None:
    script = textwrap.dedent(REFERENCE_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.available = true;
        editor.schedulePresentation();
        await settle();

        commandStatuses.push("completed", "failed");
        const save = editor.entries.find((entry) => entry.id === "reference-save");
        const job = await editor.saveAndDisplay(save);
        assert.equal(job.status, "failed");
        assert.deepEqual(submitted, [
          {
            command: "reference-save",
            parameters: { source_channel: 1, slot: 1 },
            intent: "command",
          },
          {
            command: "reference-display",
            parameters: { action: "set", slot: 1, enabled: true },
            intent: "apply",
          },
        ]);
        ''')
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_reference_action_forms_use_command_form_layout() -> None:
    script = textwrap.dedent(REFERENCE_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.available = true;
        editor.schedulePresentation();
        await settle();

        const selectorSection = editor.container.children[0];
        const selectorHost = selectorSection.children[0];
        assert.equal(selectorHost.className.includes("command-form"), false);

        const saveSection = editor.actionsHost.children[0];
        const saveFormHost = saveSection.children[1];
        assert.ok(saveFormHost);
        assert.equal(saveFormHost.className, "command-form");

        const management = editor.actionsHost.children[1];
        const displayControl = management.children[0];
        const displayFormHost = displayControl.children[1];
        assert.ok(displayFormHost);
        assert.equal(displayFormHost.className, "command-form");
        ''')
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
