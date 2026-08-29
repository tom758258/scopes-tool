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
        const editor = Object.create(globalThis.MeasurementEditor.prototype);
        Object.assign(editor, {
          hooks: {
            contextKey: () => activeContext,
            mode: () => mode,
            isCommandAvailable: () => true,
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
          renderFrontPanelReadback: () => {},
          present: () => {},
          controls: {},
        });

        activeContext = "simulate||keysight-dsox2004a";
        assert.equal(editor.syncContext(), true);
        assert.equal(editor.windowCurrent, "");
        assert.equal(editor.windowReadback, "");
        assert.equal(editor.windowDirty, false);
        assert.deepEqual(editor.frontPanelState, { kind: "empty", payload: null });

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
        await editor.showFrontPanel();
        assert.deepEqual(calls[1], ["measure-show", { action: "set" }]);
        await editor.clearFrontPanel();
        assert.deepEqual(calls[2], ["measure-clear", {}]);
        assert.equal(editor.frontPanelState.kind, "cleared");
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
