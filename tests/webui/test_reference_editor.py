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
    assert 'import { ReferenceDisplayEditor } from "/static/reference-display-editor.js";' in app
    assert 'import { ReferenceLabelsEditor } from "/static/reference-labels-editor.js";' in app
    assert 'id="reference-editor" class="reference-editor trigger-editor" hidden' in html
    assert 'id="reference-display-editor" class="reference-display-editor workflow-editor" hidden' in html
    assert 'id="reference-labels-editor" class="reference-editor trigger-editor" hidden' in html
    assert 'reference: () => referenceEditor,' in app
    assert '"reference-display": () => referenceDisplayEditor,' in app
    assert '"reference-labels": () => referenceLabelsEditor,' in app
    assert 'elements.referenceEditor.hidden = editorKind !== "reference";' in app
    assert 'elements.referenceDisplayEditor.hidden = editorKind !== "reference-display";' in app
    assert 'elements.referenceLabelsEditor.hidden = editorKind !== "reference-labels";' in app
    assert 'referenceEditor?.schedulePresentation();' in app
    assert 'referenceDisplayEditor?.schedulePresentation();' in app
    assert 'referenceLabelsEditor?.schedulePresentation();' in app
    for key in (
        "command.reference-waveform",
        "command.reference-labels",
        "description.reference-waveform",
        "description.reference-labels",
        "reference.editor.title",
        "reference.editor.saveAndDisplay",
        "reference.editor.currentLoaded",
        "reference.editor.readFailed",
        "reference-display.editor.displayedReferences",
        "reference-display.editor.displayHelper",
        "reference-display.editor.runIncomplete",
        "reference-display.editor.readFailed",
        "reference-labels.editor.title",
        "reference-labels.editor.description",
        "reference-labels.editor.read",
        "reference-labels.editor.currentLoaded",
        "reference-labels.editor.readFailed",
        "labels.visibility",
        "labels.shared",
        "labels.readFailed",
        "command.save-export",
        "description.save-export",
    ):
        assert f'"{key}":' in english
        assert f'"{key}":' in chinese
    assert '"reference.editor.title": "Reference waveform"' in english
    assert '"reference-labels.editor.title": "Reference Labels"' in english
    assert '"save-export.editor.title": "Save / Export"' in english
    assert '"reference.editor.title": "參考波形"' in chinese
    assert '"reference-labels.editor.title": "參考標籤"' in chinese
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
    assert '"labels.visibility": "Label visibility"' in english
    assert '"labels.visibility": "標籤顯示"' in chinese
    display_label_description = next(
        line for line in english.splitlines()
        if '"description.display-label":' in line
    )
    assert "single shared display setting" in display_label_description
    channel_label_description = next(
        line for line in english.splitlines()
        if '"description.channel-label":' in line
    )
    assert "Label visibility" in channel_label_description


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
        } else if (command.id === "display-label") {
          this.valuesResult = { action: "set", enabled: false };
        }
      }
      values() { return this.valuesResult; }
      queryValues() { return { action: "query" }; }
      setDisabled(value) { this.disabled = value; }
      syncResult(job, preserveDirty) { this.syncCalls.push([job.job_id, preserveDirty]); }
      clearDirty() { this.clearCalls += 1; }
    };

    const visibilitySource = fs.readFileSync(
      new URL("label-visibility.js", `file:///${process.argv[1].replaceAll("\\", "/")}`), "utf8",
    ).replace(/^import[^\n]*\r?\n/gm, "").replace(/^export /gm, "")
      + "\nglobalThis.LabelVisibility = LabelVisibility;";
    await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(visibilitySource)}`);

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
    commands.push({
      id: "display-label", category: "Display", label: "Display label",
      modes: ["live", "simulate"], presentation: setting,
      fields: [{ name: "action", type: "enum" }, { name: "enabled", type: "boolean" }],
    });
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
    let displayLabelState = false;
    const hooks = {
      executeCommand: async (command, parameters, options) => {
        submitted.push({ command, parameters, intent: options?.intent });
        const status = commandStatuses.shift() || "completed";
        const result = command === "display-label"
          ? { result: { state: displayLabelState } }
          : { result: { reference: { displayed: true, label: "BASE" } } };
        return { job_id: `job-${submitted.length}`, status, result };
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
              "reference-save", "reference-clear",
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
        assert.deepEqual(submitted, [
          {
            command: "reference-query",
            parameters: { slot: 1 },
            intent: "readback",
          },
        ]);
        assert.equal(editor.readStatus.textContent, "reference.editor.currentLoaded");
            assert.equal(
              editor.entries.find((entry) => entry.id === "reference-save").form.syncCalls.length,
              0,
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

            for (const id of ["reference-clear"]) {
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
def test_reference_labels_editor_reads_and_applies_label_state() -> None:
    script = textwrap.dedent(REFERENCE_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const labelsSource = fs.readFileSync(
          new URL("reference-labels-editor.js", `file:///${process.argv[1].replaceAll("\\", "/")}`), "utf8",
        ).replace(/^import[^\n]*\r?\n/gm, "").replace(/^export /gm, "")
          + "\nglobalThis.ReferenceLabelsEditor = ReferenceLabelsEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(labelsSource)}`);

        const labelsSelected = {
          id: "reference-labels", editor: "reference-labels", category: "Reference",
          label: "reference-labels", modes: ["live", "simulate"],
          presentation: { kind: "command", action: "run" }, fields: [],
        };
        hooks.selectedCommand = () => labelsSelected;
        const labelsEditor = new globalThis.ReferenceLabelsEditor(
          new FakeNode(), catalog, hooks,
        );
        env.available = true;
        labelsEditor.schedulePresentation();
        await settle();

            assert.equal(labelsEditor.entry.id, "reference-label");
            assert.ok(labelsEditor.entry.button.className.includes("primary"));
            assert.equal(labelsEditor.entry.button.className.includes("secondary"), false);
            // Slot selector (left) and label text (right) share one two-column row.
            const topRow = labelsEditor.container.children[0];
            assert.equal(topRow.className, "command-form");
            assert.deepEqual(topRow.children, [
              labelsEditor.slotForm.container,
              labelsEditor.labelFieldHost,
            ]);
            assert.equal(labelsEditor.entry.form.container, labelsEditor.labelFieldHost);
        assert.ok(labelsEditor.labelVisibility);
        assert.equal(labelsEditor.labelVisibility.form.command.id, "display-label");

        await labelsEditor.refresh();
        assert.deepEqual(submitted, [
          { command: "reference-query", parameters: { slot: 1 }, intent: "readback" },
          { command: "display-label", parameters: { action: "query" }, intent: "readback" },
        ]);
        assert.equal(labelsEditor.readStatus.textContent, "reference-labels.editor.currentLoaded");

        submitted.length = 0;
        await labelsEditor.submit(labelsEditor.entry);
        assert.deepEqual(submitted[0], {
          command: "reference-label",
          parameters: { action: "set", label: "BASE", slot: 1 },
          intent: "apply",
        });
        assert.equal(submitted[1].command, "reference-query");
        assert.equal(submitted[1].intent, "readback");
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
        assert.equal(selectorHost.className.includes("command-form"), true);

        const saveSection = editor.actionsHost.children[0];
        const saveFormHost = saveSection.children.find((node) => node.className === "command-form");
        assert.ok(saveFormHost);
        assert.equal(saveFormHost.className, "command-form");

            const management = editor.actionsHost.children[1];
            assert.equal(management.children.length, 1);
            const clearControl = management.children[0];
            assert.equal(
              clearControl.children.find((node) => node.className === "command-form"),
              undefined,
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
def test_composite_workspace_results_render_underlying_command_jobs(tmp_path: Path) -> None:
    app_source = read_static("app.js")
    render_source = "function renderWorkspace() {" + (
        app_source.split("function renderWorkspace() {", 1)[1].split(
            "\nasync function updateHealth()", 1
        )[0]
    )
    context_source = "function currentWorkspaceContext(" + (
        app_source.split("function currentWorkspaceContext(", 1)[1].split(
            "\nfunction captureWorkspaceResult(", 1
        )[0]
    )
    for selected_id in ("reference-waveform", "reference-labels", "save-export"):
        assert f'"{selected_id}"' in render_source
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = String(tag).toUpperCase();
            this.children = [];
            this.hidden = false;
            this.className = "";
            this.textContent = "";
          }
          append(...nodes) { this.children.push(...nodes); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.translate = (key) => key;

        const strip = (text) => text
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "");
        const execSource = strip(fs.readFileSync(process.argv[3], "utf8"))
          + "\nglobalThis.execCtx = {"
          + " buildWorkspaceContext, workspaceContextKey,"
          + " sameWorkspaceContext, findWorkspaceResult };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(execSource)}`);
        const {
          buildWorkspaceContext, workspaceContextKey,
          sameWorkspaceContext, findWorkspaceResult,
        } = globalThis.execCtx;
        globalThis.sameWorkspaceContext = sameWorkspaceContext;
        globalThis.findWorkspaceResult = findWorkspaceResult;

        let selected = null;
        globalThis.catalog = { selected: () => selected };
        globalThis.state = { workspaceResults: new Map() };
        globalThis.elements = {
          systemInformationWorkspace: new FakeNode("section"),
          identityWorkspace: new FakeNode("section"),
          identityWorkspaceContent: new FakeNode("div"),
        };
        globalThis.context = { mode: "simulate", resource: null, model_id: "keysight-dsox4024a" };
        globalThis.currentModelId = () => "keysight-dsox4024a";
        const rendered = [];
        globalThis.renderWorkspaceResult = (container, job) => {
          rendered.push({ container, job });
        };
        globalThis.renderSystemInformation = () => {};

        __RENDER_SOURCE__
        __CONTEXT_SOURCE__

        const execContext = { mode: "simulate", resource: null, model_id: "keysight-dsox4024a" };
        const seed = (command) => {
          const jobContext = buildWorkspaceContext(command, execContext, "keysight-dsox4024a");
          const job = {
            job_id: `job-${command}`, command, status: "completed",
            result: { result: { ok: true } },
          };
          globalThis.state.workspaceResults = new Map([
            [workspaceContextKey(jobContext), { context: jobContext, job }],
          ]);
          return job;
        };
        const show = (id, command) => {
          selected = { id, presentation_only: true };
          const job = seed(command);
          rendered.length = 0;
          globalThis.elements.identityWorkspaceContent.replaceChildren();
          renderWorkspace();
          assert.equal(globalThis.elements.identityWorkspace.hidden, false);
          assert.equal(rendered.length, 1);
          assert.equal(rendered[0].job, job);
        };

        show("reference-waveform", "reference-query");
        show("reference-labels", "display-label");
        show("save-export", "save-pwd");

        selected = { id: "reference-waveform", presentation_only: true };
        globalThis.state.workspaceResults = new Map();
        rendered.length = 0;
        globalThis.elements.identityWorkspaceContent.replaceChildren();
        renderWorkspace();
        assert.equal(globalThis.elements.identityWorkspace.hidden, false);
        assert.equal(rendered.length, 0);
        assert.equal(globalThis.elements.identityWorkspaceContent.children.length, 1);

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__RENDER_SOURCE__", render_source).replace("__CONTEXT_SOURCE__", context_source)
    harness_path = tmp_path / "composite-workspace-result-harness.mjs"
    harness_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path), str(EDITOR_SOURCE), str(STATIC_ROOT / "execution-context.js")],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout
