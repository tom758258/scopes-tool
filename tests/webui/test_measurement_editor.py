from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_webui.commands import command_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_measurement_browser_visibility_and_composite_editor_contract() -> None:
    catalog_json = json.dumps(command_catalog())
    app_source = (REPO_ROOT / "src/scopes_tool_webui/static/app.js").read_text(encoding="utf-8")
    editor_source = (REPO_ROOT / "src/scopes_tool_webui/static/measurement-editor.js").read_text(
        encoding="utf-8"
    )
    styles = (REPO_ROOT / "src/scopes_tool_webui/static/styles.css").read_text(encoding="utf-8")
    execute_handler = app_source.split('elements.execute.addEventListener("click"', 1)[1].split(
        'elements.cancel.addEventListener("click"', 1
    )[0]
    header_actions = app_source.split("function syncWorkspaceHeaderActions(editorKind)", 1)[1].split(
        "function syncEditorPresentation(editorKind)", 1
    )[0]
    assert 'selected?.id === "measure"' in execute_handler
    assert "measurementEditor?.runMeasurement()" in execute_handler
    assert 'selected?.id === "measure" && editorKind === "measurement"' in header_actions
    assert "measurement-editor-action" not in editor_source
    assert 'button.className = className;' in editor_source
    assert '["frontPanelHide", "measure-show"]' in editor_source
    assert '"measurement.frontPanel.markersAlwaysOn"' in editor_source
    assert '"measurement.frontPanel.readFailedEmpty"' in editor_source
    assert '"measurement.frontPanel.readFailedCleared"' in editor_source
    assert '"danger"' in editor_source
    assert ".danger {" in styles
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

        globalThis.hasTranslation = () => false;
        globalThis.translate = (key) => key;
        globalThis.commandSupported = () => true;
        globalThis.commandSupportReason = () => "";
        globalThis.fieldsForModel = (command) => command.fields || [];
        globalThis.CommandForm = class CommandForm {};

        let catalogSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/command-catalog.js"),
          "utf8",
        );
        catalogSource = catalogSource
          .replace(/import \{[\s\S]*?\} from "\/static\/i18n\.js";\r?\n/, "")
          .replace(/import \{[\s\S]*?\} from "\/static\/command-support\.js";\r?\n/, "")
          .replace("export class CommandCatalog", "class CommandCatalog")
          + "\nglobalThis.CommandCatalog = CommandCatalog;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(catalogSource)}`);

        const catalog = Object.create(globalThis.CommandCatalog.prototype);
        catalog.commands = __CATALOG__;
        catalog.activeMode = "simulate";
        assert.deepEqual(
          catalog.availableCommands()
            .filter((command) => command.category === "Measurement")
            .map((command) => command.id),
          ["measure", "front-panel-measurements"],
        );
        catalog.activeMode = "live";
        assert.deepEqual(
          catalog.availableCommands()
            .filter((command) => command.category === "Measurement")
            .map((command) => command.id),
          ["measure", "front-panel-measurements"],
        );
        catalog.activeMode = "dry-run";
        assert.deepEqual(
          catalog.availableCommands()
            .filter((command) => command.category === "Measurement")
            .map((command) => command.id),
          ["measure"],
        );

        let editorSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/measurement-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class MeasurementEditor", "class MeasurementEditor")
          + "\nglobalThis.MeasurementEditor = MeasurementEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);
        const freshEditor = new globalThis.MeasurementEditor(null, null, {});
        assert.deepEqual(freshEditor.frontPanelState, { kind: "unread", payload: null });
        assert.equal(freshEditor.frontPanelReadError, null);

        let activeContext = "simulate||keysight-dsox4024a";
        let mode = "simulate";
        const calls = [];
        const jobs = {
          "measure-window": { status: "completed", result: { result: { window: { window: "AUTO" } } } },
          "measure": { status: "completed" },
          "measure-results": {
            status: "completed",
            result: { result: { measurements: { items: [{ label: "VPP CH1", value: "3.28" }] } } },
          },
          "measure-show": { status: "completed" },
          "measure-clear": { status: "completed" },
        };
        const unavailable = new Set();
        const editor = Object.create(globalThis.MeasurementEditor.prototype);
        Object.assign(editor, {
          hooks: {
            contextKey: () => activeContext,
            mode: () => mode,
            isCommandAvailable: (command) => !unavailable.has(command),
            executeCommand: async (command, parameters) => {
              calls.push([command, parameters]);
              return jobs[command];
            },
          },
          contextKey: activeContext,
          windowCurrent: "gate",
          windowReadback: "auto",
          windowDirty: true,
          frontPanelState: { kind: "results", payload: { items: [{ label: "old" }] } },
          frontPanelReadError: "old-error",
          renderFrontPanelReadback: () => {},
          present: () => {},
          controls: {},
        });

        activeContext = "simulate||keysight-dsox2004a";
        assert.equal(editor.syncContext(), true);
        assert.equal(editor.windowCurrent, "");
        assert.equal(editor.windowReadback, "");
        assert.equal(editor.windowDirty, false);
        assert.deepEqual(editor.frontPanelState, { kind: "unread", payload: null });
        assert.equal(editor.frontPanelReadError, null);

        editor.contextKey = activeContext;
        editor.windowDirty = true;
        editor.measureForm = { values: () => ({ item: "period", channel: 1 }) };
        editor.windowForm = {
          values: () => ({ action: "set", window: "auto" }),
          clearDirty: () => {},
        };
        calls.length = 0;
        await editor.runMeasurement();
        assert.deepEqual(calls.map(([command]) => command), ["measure-window", "measure"]);
        assert.equal(editor.windowDirty, false);

        mode = "dry-run";
        editor.windowDirty = true;
        calls.length = 0;
        await editor.runMeasurement();
        assert.deepEqual(calls.map(([command]) => command), ["measure"]);

        mode = "simulate";
        calls.length = 0;
        await editor.refreshFrontPanel();
        assert.deepEqual(calls[0], ["measure-results", {}]);
        assert.equal(editor.frontPanelState.kind, "results");
        assert.equal(editor.frontPanelState.payload.items[0].label, "VPP CH1");
        assert.equal(editor.frontPanelReadError, null);

        jobs["measure-results"] = {
          status: "completed",
          result: { result: { measurements: { items: [] } } },
        };
        await editor.refreshFrontPanel();
        assert.equal(editor.frontPanelState.kind, "empty");

        jobs["measure-results"] = { status: "failed" };
        await editor.refreshFrontPanel();
        assert.equal(editor.frontPanelState.kind, "empty");
        assert.equal(editor.frontPanelReadError, "measurement.frontPanel.readFailed");

        jobs["measure-results"] = {
          status: "completed",
          result: { result: { measurements: { items: [{ label: "Period CH1", value: "1e-3" }] } } },
        };
        await editor.refreshFrontPanel();
        const previousPayload = editor.frontPanelState.payload;
        jobs["measure-results"] = { status: "failed" };
        await editor.refreshFrontPanel();
        assert.equal(editor.frontPanelState.kind, "results");
        assert.equal(editor.frontPanelState.payload, previousPayload);
        assert.equal(editor.frontPanelReadError, "measurement.frontPanel.readFailed");

        jobs["measure-results"] = {
          status: "completed",
          result: { result: { measurements: { items: [{ label: "Frequency CH1", value: "1000" }] } } },
        };
        await editor.refreshFrontPanel();
        assert.equal(editor.frontPanelState.payload.items[0].label, "Frequency CH1");
        assert.equal(editor.frontPanelReadError, null);

        unavailable.add("measure-results");
        const callCount = calls.length;
        await editor.refreshFrontPanel();
        assert.equal(calls.length, callCount);
        await editor.showFrontPanel(true);
        assert.deepEqual(calls.at(-1), ["measure-show", { action: "set", enabled: true }]);
        await editor.showFrontPanel(false);
        assert.deepEqual(calls.at(-1), ["measure-show", { action: "set", enabled: false }]);
        await editor.clearFrontPanel();
        assert.deepEqual(calls.at(-1), ["measure-clear", {}]);
        assert.equal(editor.frontPanelState.kind, "cleared");
        assert.equal(editor.frontPanelReadError, null);
        '''
    ).replace("__CATALOG__", catalog_json)
    completed = subprocess.run(
        ["node", "--input-type=module"],
        cwd=REPO_ROOT,
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_measurement_marker_actions_follow_projected_model_fields() -> None:
    editor_source = (REPO_ROOT / "src/scopes_tool_webui/static/measurement-editor.js").read_text(
        encoding="utf-8"
    )
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.hidden = false; this.textContent = ""; this.className = ""; }
          append(...nodes) { this.children.push(...nodes); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          addEventListener(_name, handler) { this.handler = handler; }
          setAttribute() {}
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.translate = (key) => key;
        globalThis.CommandForm = class CommandForm {};
        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import.*$/gm, "")
          .replace("export class MeasurementEditor", "class MeasurementEditor")
          + "\nglobalThis.MeasurementEditor = MeasurementEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const makeEditor = (modelId) => {
          const catalog = {
            activeModelId: modelId,
            commands: [{ id: "measure-show" }],
            fieldsFor: () => modelId === "keysight-dsox4024a"
              ? [{ name: "action" }, { name: "enabled" }]
              : [{ name: "action" }],
            supportReason: () => "",
          };
          const editor = new globalThis.MeasurementEditor(new FakeNode("div"), catalog, {
            isExecutionBusy: () => false,
            isCommandAvailable: () => true,
            executeCommand: async () => ({ status: "completed" }),
          });
          editor.renderFrontPanel();
          return editor;
        };

        const fixed = makeEditor("keysight-dsox3024a");
        assert.equal(fixed.controls.frontPanelShow, undefined);
        assert.equal(fixed.controls.frontPanelHide, undefined);
        assert(fixed.container.children[0].children.some((node) => node.textContent === "measurement.frontPanel.markersAlwaysOn"));

        const toggle = makeEditor("keysight-dsox4024a");
        assert.equal(toggle.controls.frontPanelShow.className, "secondary");
        assert.equal(toggle.controls.frontPanelHide.className, "secondary");
        assert.equal(toggle.controls.frontPanelClear.className, "danger");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(REPO_ROOT / "src/scopes_tool_webui/static/measurement-editor.js")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout
