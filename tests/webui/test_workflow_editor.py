from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_webui.commands import command_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
EDITOR_SOURCE = STATIC_ROOT / "workflow-editor.js"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_only_e1_workflows_use_the_dedicated_editor() -> None:
    commands = {entry["id"]: entry for entry in command_catalog()}

    assert commands["measure-log"]["editor"] == "workflow"
    assert commands["triggered-measure-loop"]["editor"] == "workflow"
    for command_id in (
        "capture-batch",
        "measure-until",
        "triggered-capture-series",
    ):
        assert "editor" not in commands[command_id]


def test_workflow_choices_reuse_catalog_and_model_capability_projection() -> None:
    commands = {entry["id"]: entry for entry in command_catalog()}
    for command_id in ("measure-log", "triggered-measure-loop"):
        command = commands[command_id]
        fields = {field["name"]: field for field in command["fields"]}
        assert fields["pair_items"]["options"] == ["phase", "delay"]
        for model_id, presentation in command["presentation"]["models"].items():
            capabilities = capabilities_for_model_id(model_id)
            assert presentation["fields"]["channels"]["options"] == list(
                range(1, capabilities.analog_channels + 1)
            )
            expected_pair_items = (
                ["phase", "delay"]
                if capabilities.supports_delay_measurement
                else ["phase"]
            )
            projected_pair_items = presentation["fields"].get(
                "pair_items", fields["pair_items"]
            )["options"]
            assert projected_pair_items == expected_pair_items


def test_app_routes_workflow_editor_without_generic_header_actions() -> None:
    app = read_static("app.js")
    html = read_static("index.html")
    editor = read_static("workflow-editor.js")

    assert 'import { WorkflowEditor } from "/static/workflow-editor.js";' in app
    assert 'workflow: () => workflowEditor,' in app
    assert 'id="workflow-editor" class="workflow-editor" hidden' in html
    assert 'elements.workflowEditor.hidden = editorKind !== "workflow";' in app
    assert 'workflowEditor?.schedulePresentation();' in app
    assert 'workflowEditor?.runButton' in app
    assert "refreshButton" not in editor
    assert 'executeCommand(\n        definition.id,' in editor
    assert '{ intent: "command" }' in editor
    assert "formRevision" not in editor


WORKFLOW_EDITOR_HARNESS = r'''
    import assert from "node:assert/strict";
    import fs from "node:fs";

    class FakeNode {
      constructor(tag = "div") {
        this.tagName = tag.toUpperCase();
        this.children = [];
        this.parentNode = null;
        this.dataset = {};
        this.listeners = {};
        this.hidden = false;
        this.disabled = false;
        this.checked = false;
        this.required = false;
        this.value = "";
        this.className = "";
        this.textContent = "";
        this.customValidity = "";
      }
      addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
      dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
      append(...nodes) {
        for (const node of nodes) {
          node.parentNode = this;
          this.children.push(node);
        }
      }
      replaceChildren(...nodes) {
        for (const child of this.children) child.parentNode = null;
        this.children = [];
        this.append(...nodes);
      }
      remove() {
        if (!this.parentNode) return;
        this.parentNode.children = this.parentNode.children.filter((node) => node !== this);
        this.parentNode = null;
      }
      setAttribute(name, value) { this[name] = String(value); }
      setCustomValidity(value) { this.customValidity = value; }
      checkValidity() {
        if (this.customValidity) return false;
        if (this.required && this.value === "") return false;
        if (this.value !== "" && this.type === "number") {
          const value = Number(this.value);
          if (!Number.isFinite(value)) return false;
          if (this.min !== undefined && value < Number(this.min)) return false;
          if (this.max !== undefined && value > Number(this.max)) return false;
          if (this.step === "1" && !Number.isInteger(value)) return false;
        }
        return true;
      }
      reportValidity() {}
      querySelectorAll(selector) {
        const tags = new Set(selector.split(",").map((value) => value.trim().toUpperCase()));
        const found = [];
        const visit = (node) => {
          for (const child of node.children) {
            if (tags.has(child.tagName)) found.push(child);
            visit(child);
          }
        };
        visit(this);
        return found;
      }
    }
    globalThis.document = { createElement: (tag) => new FakeNode(tag) };
    globalThis.Option = class Option extends FakeNode {
      constructor(label, value) {
        super("option");
        this.textContent = label;
        this.value = String(value);
      }
    };
    globalThis.translate = (key) => key;
    globalThis.hasTranslation = () => false;

    const source = fs.readFileSync(process.argv[1], "utf8")
      .replace(/^import[^\n]*\r?\n/gm, "")
      .replace(/^export /gm, "")
      + "\nglobalThis.workflowApi = { WorkflowEditor };";
    await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

    const settle = async () => {
      await Promise.resolve();
      await Promise.resolve();
    };
    const fields = [
      { name: "channels", type: "multi-enum", options: [1, 2, 3, 4], serialize: "csv" },
      { name: "items", type: "multi-enum", options: ["vpp", "frequency"], default: ["vpp", "frequency"], serialize: "csv" },
      { name: "pairs", type: "string" },
      { name: "pair_items", type: "string", options: ["phase", "delay"], default: "phase,delay" },
      { name: "interval_seconds", type: "number", minimum: 0, default: 1 },
      { name: "count", type: "integer", minimum: 1 },
      { name: "duration_seconds", type: "number", minimum: 0 },
      { name: "stop_on_error", type: "boolean", default: false },
    ];
    const triggeredFields = fields.filter((field) => !["duration_seconds", "stop_on_error"].includes(field.name)).map(
      (field) => field.name === "interval_seconds" ? { ...field, default: 0 } : field,
    ).concat([
      { name: "trigger_timeout_seconds", type: "number", minimum: 0, required: true },
    ]).map((field) => field.name === "count" ? { ...field, required: true } : field);
    const definitions = [
      { id: "measure-log", editor: "workflow", fields },
      { id: "triggered-measure-loop", editor: "workflow", fields: triggeredFields },
    ];
    const env = { selectedId: "measure-log", contextKey: "simulate||model", executionBusy: false };
    const submissions = [];
    const catalog = { fieldsFor: (definition) => definition.fields };
    const hooks = {
      executeCommand: async (command, parameters, options) => {
        submissions.push({ command, parameters, options });
        return { job_id: `job-${submissions.length}`, command, status: "completed" };
      },
      headerActions: new FakeNode(),
      isExecutionBusy: () => env.executionBusy,
      isAvailable: () => true,
      contextKey: () => env.contextKey,
      selectedCommand: () => definitions.find((item) => item.id === env.selectedId),
    };
    const buildEditor = () => new globalThis.workflowApi.WorkflowEditor(
      new FakeNode(), catalog, hooks,
    );
'''


def run_editor_behavior(script: str) -> None:
    completed = subprocess.run(
        [
            "node",
            "--input-type=module",
            "--eval",
            textwrap.dedent(WORKFLOW_EDITOR_HARNESS) + textwrap.dedent(script),
            str(EDITOR_SOURCE),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_workflow_selection_is_passive_and_run_serializes_structured_inputs_once() -> None:
    run_editor_behavior(
        r'''
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        assert.deepEqual(submissions, []);
        assert.equal(editor.runButton.textContent, "actions.run");

        editor.controls.channels.find((input) => input.value === "1").checked = true;
        editor.controls.channels.find((input) => input.value === "3").checked = true;
        editor.addPairButton.dispatch("click");
        editor.addPairButton.dispatch("click");
        editor.pairRows[1].source.value = "3";
        editor.pairRows[1].reference.value = "4";
        editor.controls.count.value = "5";
        editor.controls.duration_seconds.value = "12";
        editor.controls.interval_seconds.value = "0.25";
        editor.controls.stop_on_error.checked = true;

        await editor.submit();
        assert.equal(submissions.length, 1);
        assert.equal(submissions[0].command, "measure-log");
        assert.deepEqual(submissions[0].parameters, {
          channels: "1,3",
          items: "vpp,frequency",
          pairs: ["1:2", "3:4"],
          pair_items: "phase,delay",
          interval_seconds: 0.25,
          count: 5,
          duration_seconds: 12,
          stop_on_error: true,
        });
        assert.deepEqual(submissions[0].options, { intent: "command" });
        assert.equal(Object.hasOwn(submissions[0].options, "formRevision"), false);

        env.executionBusy = true;
        await editor.submit();
        assert.equal(submissions.length, 1);

        env.executionBusy = false;
        env.selectedId = "triggered-measure-loop";
        editor.schedulePresentation();
        await settle();
        assert.equal(submissions.length, 1);
        editor.controls.count.value = "3";
        editor.controls.trigger_timeout_seconds.value = "4.5";
        editor.addPairButton.dispatch("click");
        await editor.submit();
        assert.equal(submissions.length, 2);
        assert.equal(submissions[1].command, "triggered-measure-loop");
        assert.deepEqual(submissions[1].parameters, {
          items: "vpp,frequency",
          pairs: ["1:2"],
          pair_items: "phase,delay",
          interval_seconds: 0,
          count: 3,
          trigger_timeout_seconds: 4.5,
        });
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_workflow_drafts_survive_locale_rerender_but_not_context_switch_or_stale_completion() -> None:
    run_editor_behavior(
        r'''
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        editor.controls.count.value = "7";
        editor.controls.count.dispatch("input");
        editor.rerender();
        await settle();
        assert.equal(editor.controls.count.value, "7");
        assert.deepEqual(submissions, []);

        env.contextKey = "simulate||other-model";
        editor.schedulePresentation();
        await settle();
        assert.equal(editor.controls.count.value, "");
        editor.controls.count.value = "2";
        editor.controls.count.dispatch("input");

        let complete;
        hooks.executeCommand = (command, parameters, options) => {
          submissions.push({ command, parameters, options });
          return new Promise((resolve) => { complete = resolve; });
        };
        const pending = editor.submit();
        await settle();
        assert.equal(submissions.length, 1);

        env.selectedId = "triggered-measure-loop";
        editor.schedulePresentation();
        await settle();
        editor.controls.count.value = "9";
        editor.controls.count.dispatch("input");
        complete({ job_id: "old-job", command: "measure-log", status: "completed" });
        await pending;
        assert.equal(env.selectedId, "triggered-measure-loop");
        assert.equal(editor.controls.count.value, "9");
        assert.equal(editor.drafts.get(editor.currentKey()).count, "9");
        ''',
    )
