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
NUMERIC_INPUT_SOURCE = STATIC_ROOT / "numeric-input.js"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_expected_commands_use_the_dedicated_workflow_editor() -> None:
    commands = {entry["id"]: entry for entry in command_catalog()}

    assert commands["measure-log"]["editor"] == "workflow"
    assert commands["triggered-measure-loop"]["editor"] == "workflow"
    assert commands["capture-batch"]["editor"] == "workflow"
    assert commands["measure-until"]["editor"] == "workflow"
    assert commands["triggered-capture-series"]["editor"] == "workflow"


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
        const classes = new Set();
        this.classList = {
          add: (...names) => names.forEach((name) => classes.add(name)),
          contains: (name) => classes.has(name),
        };
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

    const source = [
      fs.readFileSync(process.argv[2], "utf8"),
      fs.readFileSync(process.argv[1], "utf8"),
    ].join("\n")
      .replace(/^import[^\n]*\r?\n/gm, "")
      .replace(/^export function /gm, "function ")
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
      { name: "trigger_timeout_seconds", type: "number", exclusive_minimum: 0, required: true },
    ]).map((field) => field.name === "count" ? { ...field, required: true } : field);
    const definitions = [
      { id: "measure-log", editor: "workflow", fields },
      { id: "triggered-measure-loop", editor: "workflow", fields: triggeredFields },
    ];
    const env = {
      selectedId: "measure-log", contextKey: "simulate||model",
      executionBusy: false, available: true,
    };
    const submissions = [];
    const catalog = { fieldsFor: (definition) => definition.fields };
    const hooks = {
      executeCommand: async (command, parameters, options) => {
        submissions.push({ command, parameters, options });
        return { job_id: `job-${submissions.length}`, command, status: "completed" };
      },
      headerActions: new FakeNode(),
      isExecutionBusy: () => env.executionBusy,
      isAvailable: () => env.available,
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
            str(NUMERIC_INPUT_SOURCE),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_workflow_runtime_unavailable_content_stays_visible_and_recovers() -> None:
    run_editor_behavior(
        r'''
        env.available = false;
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        assert.ok(editor.controls.count);
        assert.equal(editor.runButton.disabled, true);
        assert.ok(editor.container.querySelectorAll("input, select, button").every(
          (control) => control.disabled,
        ));
        await editor.submit();
        assert.deepEqual(submissions, []);

        env.available = true;
        editor.schedulePresentation();
        await settle();
        assert.equal(editor.runButton.disabled, false);
        assert.equal(editor.controls.count.disabled, false);
        editor.controls.count.value = "1";
        await editor.submit();
        assert.equal(submissions.length, 1);
        assert.equal(submissions[0].command, "measure-log");
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_workflow_number_fields_share_numeric_constraints() -> None:
    run_editor_behavior(
        r'''
        const editor = buildEditor();
        const interval = editor.buildNumberField({
          name: "interval_seconds", type: "number", minimum: 0,
        }, "").input;
        assert.equal(interval.type, "number");
        assert.equal(interval.step, "any");
        assert.equal(interval.min, "0");
        assert.equal(interval.classList.contains("no-number-spinner"), true);

        const timeout = editor.buildNumberField({
          name: "trigger_timeout_seconds", type: "number", exclusive_minimum: 0,
        }, "").input;
        assert.equal(timeout.min, "0");
        assert.equal(timeout.dataset.exclusiveMinimum, "0");
        assert.equal(timeout.classList.contains("no-number-spinner"), true);
        '''
    )


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
        for (const input of editor.controls.pair_items) {
          input.checked = true;
          input.dispatch("change");
        }
        editor.addPairButton.dispatch("click");
        editor.addPairButton.dispatch("click");
        editor.pairRows[1].source.value = "3";
        editor.pairRows[1].reference.value = "4";
        editor.controls.count.value = "5";
        editor.controls.duration_seconds.value = "12";
        editor.controls.interval_seconds.value = "0.25";
        editor.controls.stop_on_error.checked = true;
        editor.controls.save_results.checked = false;

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
          save_results: false,
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
        editor.controls.trigger_timeout_seconds.value = "0";
        editor.addPairButton.dispatch("click");
        await editor.submit();
        assert.equal(submissions.length, 1);
        assert.equal(
          editor.controls.trigger_timeout_seconds.customValidity,
          "form.greaterThan",
        );

        editor.controls.trigger_timeout_seconds.value = "4.5";
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
          save_results: true,
        });
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_workflow_pair_measurements_are_required_only_with_pair_rows() -> None:
    run_editor_behavior(
        r'''
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        editor.controls.count.value = "1";
        assert.equal(editor.pairRows.length, 0);
        assert.deepEqual(editor.checkedValues("pair_items"), []);
        assert.equal(editor.pairItemsSection.hidden, false);
        assert.equal(editor.addPairButton.disabled, true);
        assert.deepEqual(editor.container.children.map((section) => section.children[0].textContent), [
          "workflow.editor.channels", "workflow.editor.measurements",
          "workflow.editor.pairMeasurements", "workflow.editor.pairs", "workflow.editor.runLimits",
        ]);
        assert.equal(editor.checkedValues("items").length > 0, true);
        editor.controls.channels[0].checked = true;

        await editor.submit();
        assert.equal(submissions.length, 1);
        assert.equal(submissions[0].parameters.pair_items, "phase");
        assert.equal(submissions[0].parameters.channels, "1");
        assert.equal(submissions[0].parameters.items, "vpp,frequency");
        assert.equal(editor.addPairButton.disabled, true);

        editor.controls.pair_items[0].checked = true;
        editor.controls.pair_items[0].dispatch("change");
        assert.equal(editor.addPairButton.disabled, false);
        assert.equal(editor.pairRows.length, 0);
        editor.addPairButton.dispatch("click");
        assert.equal(editor.pairRows.length, 1);
        assert.equal(editor.pairItemsSection.hidden, false);
        editor.controls.pair_items[0].checked = false;
        editor.controls.pair_items[0].dispatch("change");
        assert.equal(editor.addPairButton.disabled, true);
        assert.equal(editor.pairRows.length, 1);
        await editor.submit();
        assert.equal(submissions.length, 1);
        assert.equal(
          editor.controls.pair_items[0].customValidity,
          "workflow.editor.pairMeasurementRequired",
        );

        editor.controls.pair_items[0].checked = true;
        editor.pairRows[0].reference.value = editor.pairRows[0].source.value;
        await editor.submit();
        assert.equal(submissions.length, 1);
        assert.equal(
          editor.pairRows[0].reference.customValidity,
          "workflow.editor.distinctPair",
        );

        editor.pairRows[0].remove.dispatch("click");
        assert.equal(editor.pairRows.length, 0);
        assert.equal(editor.pairItemsSection.hidden, false);
        await editor.submit();
        assert.equal(submissions.length, 2);
        assert.equal(submissions[1].parameters.pair_items, "phase");

        env.selectedId = "triggered-measure-loop";
        editor.schedulePresentation();
        await settle();
        editor.controls.count.value = "1";
        editor.controls.trigger_timeout_seconds.value = "1";
        for (const input of editor.controls.pair_items) input.checked = false;
        assert.equal(editor.pairRows.length, 0);
        assert.equal(editor.checkedValues("items").length > 0, true);

        await editor.submit();
        assert.equal(submissions.length, 3);
        assert.equal(submissions[2].parameters.pair_items, "phase");
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


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_workflow_editor_renders_capture_batch_and_serializes() -> None:
    run_editor_behavior(
        r'''
        const captureBatchFields = [
          { name: "channels", type: "multi-enum", options: [1, 2, 3, 4], serialize: "csv", required: true },
          { name: "points", type: "integer", options: [1000, 5000, 10000], default: 1000 },
          { name: "format", type: "enum", options: ["byte", "word"], default: "byte" },
          { name: "count", type: "integer", minimum: 1, default: 1 },
          { name: "interval_seconds", type: "number", minimum: 0, default: 0 },
        ];
        definitions.push({ id: "capture-batch", editor: "workflow", fields: captureBatchFields });
        env.selectedId = "capture-batch";
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        assert.ok(editor.controls.channels, "channels should render");
        assert.ok(editor.controls.points, "points should render");
        assert.ok(editor.controls.format, "format should render");
        assert.ok(editor.controls.count, "count should render");
        assert.ok(editor.controls.interval_seconds, "interval_seconds should render");
        assert.equal(editor.controls.points.value, "1000");
        assert.equal(editor.controls.format.value, "byte");
        assert.equal(editor.controls.count.value, "1");
        assert.equal(editor.controls.interval_seconds.value, "0");
        editor.controls.channels.find((input) => input.value === "1").checked = true;
        editor.controls.channels.find((input) => input.value === "2").checked = true;
        editor.controls.points.value = "5000";
        editor.controls.format.value = "word";
        editor.controls.count.value = "3";
        editor.controls.interval_seconds.value = "0.5";
        await editor.submit();
        assert.equal(submissions.length, 1);
        assert.equal(submissions[0].command, "capture-batch");
        assert.deepEqual(submissions[0].parameters, {
          channels: "1,2",
          points: 5000,
          format: "word",
          count: 3,
          interval_seconds: 0.5,
        });
        assert.deepEqual(submissions[0].options, { intent: "command" });
        env.executionBusy = true;
        await editor.submit();
        assert.equal(submissions.length, 1);
        env.executionBusy = false;
        editor.controls.count.value = "4";
        await editor.submit();
        assert.equal(submissions.length, 2);
        assert.equal(submissions[1].parameters.count, 4);
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_workflow_editor_renders_measure_until_and_serializes() -> None:
    run_editor_behavior(
        r'''
        const measureUntilFields = [
          { name: "channel", type: "integer", minimum: 1, maximum: 4, default: 1, options: [1, 2, 3, 4] },
          { name: "item", type: "enum", options: ["vpp", "frequency"], default: "vpp" },
          { name: "operator", type: "enum", options: ["gt", "gte", "lt", "lte"], required: true },
          { name: "threshold", type: "number", required: true },
          { name: "timeout_seconds", type: "number", exclusive_minimum: 0, required: true },
          { name: "interval_seconds", type: "number", minimum: 0, default: 1 },
          { name: "save_results", type: "boolean", default: true },
        ];
        definitions.push({ id: "measure-until", editor: "workflow", fields: measureUntilFields });
        env.selectedId = "measure-until";
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        assert.ok(editor.controls.channel, "channel should render");
        assert.ok(editor.controls.item, "item should render");
        assert.ok(editor.controls.operator, "operator should render");
        assert.ok(editor.controls.threshold, "threshold should render");
        assert.ok(editor.controls.timeout_seconds, "timeout_seconds should render");
        assert.ok(editor.controls.interval_seconds, "interval_seconds should render");
        assert.ok(editor.controls.save_results, "save_results should render");
        assert.equal(editor.controls.channel.value, "1");
        assert.equal(editor.controls.item.value, "vpp");
        assert.equal(editor.controls.interval_seconds.value, "1");
        editor.controls.channel.value = "2";
        editor.controls.item.value = "frequency";
        editor.controls.operator.value = "gte";
        editor.controls.threshold.value = "1000";
        editor.controls.timeout_seconds.value = "10";
        editor.controls.interval_seconds.value = "0.25";
        editor.controls.save_results.checked = true;
        editor.rerender();
        await settle();
        assert.equal(editor.controls.channel.value, "2");
        assert.equal(editor.controls.item.value, "frequency");
        assert.equal(editor.controls.operator.value, "gte");
        assert.equal(editor.controls.threshold.value, "1000");
        assert.equal(editor.controls.timeout_seconds.value, "10");
        assert.equal(editor.controls.interval_seconds.value, "0.25");
        assert.equal(editor.controls.operator.required, true);
        editor.controls.operator.value = "";
        assert.equal(editor.controls.operator.checkValidity(), false);
        await editor.submit();
        assert.equal(submissions.length, 0);
        editor.controls.operator.value = "gte";
        assert.equal(editor.controls.operator.checkValidity(), true);
        editor.controls.timeout_seconds.value = "0";
        await editor.submit();
        assert.equal(submissions.length, 0);
        assert.equal(editor.controls.timeout_seconds.customValidity, "form.greaterThan");
        editor.controls.timeout_seconds.value = "10";
        await editor.submit();
        assert.equal(submissions.length, 1);
        assert.equal(submissions[0].command, "measure-until");
        assert.deepEqual(submissions[0].parameters, {
          channel: 2,
          item: "frequency",
          operator: "gte",
          threshold: 1000,
          timeout_seconds: 10,
          interval_seconds: 0.25,
          save_results: true,
        });
        assert.deepEqual(submissions[0].options, { intent: "command" });
        ''',
    )


def test_workflow_editor_condition_locale_exists() -> None:
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert '"workflow.editor.condition": "Condition"' in english
    assert '"workflow.editor.condition": "條件"' in chinese


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_workflow_editor_renders_triggered_capture_series_and_serializes() -> None:
    run_editor_behavior(
        r'''
        const tcsFields = [
          { name: "channels", type: "multi-enum", options: [1, 2, 3, 4], serialize: "csv", required: true },
          { name: "count", type: "integer", minimum: 1, required: true },
          { name: "trigger_timeout_seconds", type: "number", exclusive_minimum: 0, required: true },
          { name: "points", type: "integer", options: [1000, 5000, 10000], default: 1000 },
          { name: "format", type: "enum", options: ["byte", "word"], default: "byte" },
          { name: "interval_seconds", type: "number", minimum: 0, default: 0 },
        ];
        definitions.push({ id: "triggered-capture-series", editor: "workflow", fields: tcsFields });
        env.selectedId = "triggered-capture-series";
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        assert.ok(editor.controls.channels, "channels should render");
        assert.ok(editor.controls.points, "points should render");
        assert.ok(editor.controls.format, "format should render");
        assert.ok(editor.controls.count, "count should render");
        assert.ok(editor.controls.trigger_timeout_seconds, "trigger_timeout_seconds should render");
        assert.ok(editor.controls.interval_seconds, "interval_seconds should render");
        assert.equal(editor.controls.points.value, "1000");
        assert.equal(editor.controls.format.value, "byte");
        assert.equal(editor.controls.interval_seconds.value, "0");
        assert.equal(editor.controls.count.required, true);
        assert.equal(editor.controls.trigger_timeout_seconds.required, true);
        editor.controls.channels.find((input) => input.value === "1").checked = true;
        editor.controls.count.value = "";
        await editor.submit();
        assert.equal(submissions.length, 0);
        editor.controls.count.value = "3";
        editor.controls.trigger_timeout_seconds.value = "";
        await editor.submit();
        assert.equal(submissions.length, 0);
        editor.controls.trigger_timeout_seconds.value = "0";
        await editor.submit();
        assert.equal(submissions.length, 0);
        assert.equal(editor.controls.trigger_timeout_seconds.customValidity, "form.greaterThan");
        editor.controls.channels.find((input) => input.value === "2").checked = true;
        editor.controls.points.value = "5000";
        editor.controls.format.value = "word";
        editor.controls.count.value = "3";
        editor.controls.trigger_timeout_seconds.value = "4.5";
        editor.controls.interval_seconds.value = "0.25";
        editor.rerender();
        await settle();
        assert.equal(editor.controls.channels.find((input) => input.value === "1").checked, true);
        assert.equal(editor.controls.channels.find((input) => input.value === "2").checked, true);
        assert.equal(editor.controls.points.value, "5000");
        assert.equal(editor.controls.format.value, "word");
        assert.equal(editor.controls.count.value, "3");
        assert.equal(editor.controls.trigger_timeout_seconds.value, "4.5");
        assert.equal(editor.controls.interval_seconds.value, "0.25");
        await editor.submit();
        assert.equal(submissions.length, 1);
        assert.equal(submissions[0].command, "triggered-capture-series");
        assert.deepEqual(submissions[0].parameters, {
          channels: "1,2",
          points: 5000,
          format: "word",
          count: 3,
          trigger_timeout_seconds: 4.5,
          interval_seconds: 0.25,
        });
        assert.deepEqual(submissions[0].options, { intent: "command" });
        assert.equal(Object.hasOwn(submissions[0].options, "formRevision"), false);
        assert.equal(submissions[0].parameters.save_results, undefined);
        editor.controls.channels.find((input) => input.value === "1").checked = false;
        editor.controls.channels.find((input) => input.value === "2").checked = false;
        await editor.submit();
        assert.equal(submissions.length, 1);
        ''',
    )
