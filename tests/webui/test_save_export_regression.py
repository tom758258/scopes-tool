from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
SAVE_EXPORT_EDITOR_SOURCE = STATIC_ROOT / "save-export-editor.js"


def run_node(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SAVE_EXPORT_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )


SAVE_EXPORT_EDITOR_HARNESS = r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = (tag || "div").toUpperCase();
            this.children = [];
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.className = "";
            this.dataset = {};
            this._textContent = "";
            this.classList = {
              add: (...names) => {
                const tokens = new Set((this.className || "").split(/\s+/).filter(Boolean));
                for (const name of names) tokens.add(name);
                this.className = [...tokens].join(" ");
              },
              remove: (...names) => {
                const tokens = new Set((this.className || "").split(/\s+/).filter(Boolean));
                for (const name of names) tokens.delete(name);
                this.className = [...tokens].join(" ");
              },
              contains: (name) => (this.className || "").split(/\s+/).includes(name),
            };
            Object.defineProperty(this, "textContent", {
              get: () => {
                if (this._textContent !== "") return this._textContent;
                return this.children.map((child) => child && typeof child.textContent === "string" ? child.textContent : "").join("");
              },
              set: (value) => {
                this._textContent = value ?? "";
              },
            });
          }
          addEventListener(name, handler) {
            (this.listeners[name] ||= []).push(handler);
          }
          dispatch(name) {
            for (const handler of this.listeners[name] || []) handler({ type: name });
          }
          replaceChildren(...nodes) {
            this.children = [...nodes];
          }
          append(...nodes) {
            this.children.push(...nodes);
          }
          insertBefore(node, reference) {
            const index = this.children.indexOf(reference);
            if (index < 0) this.children.push(node);
            else this.children.splice(index, 0, node);
          }
          querySelectorAll(selector = "[data-field]") {
            return this._fieldNodes || [];
          }
        }

        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        const translations = {
          "save-export.editor.title": "Save / Export",
          "save-export.editor.mode.image": "Image",
          "save-export.editor.mode.waveform": "Waveform data",
          "actions.readSettings": "Read current settings",
          "actions.apply": "Apply",
          "save-export.editor.storageNote": "Instrument-side storage",
          "save-export.editor.pathHelper": "Example: \\\\usb\\\\.",
          "save-export.editor.pathUnavailable": "Could not read the current save location.",
          "save-export.editor.currentValueUnavailable": "Current value unavailable.",
          "save-export.editor.destinationPreviewLabel": "Destination preview",
          "save-export.editor.advancedSettings": "Advanced settings",
          "save-export.editor.baseFilenameHelp": "This is the instrument SAVE default base filename.",
          "save-export.editor.waveformLengthMaxNote": "Maximum waveform length mode cannot be configured by this tool. If the mode is enabled on the instrument, the manual waveform save length setting has no effect.",
          "save-export.editor.readingCurrent": "reading:{{group}}:{{current}}/{{total}}",
          "save-export.editor.currentLoaded": "loaded:{{group}}",
          "save-export.editor.currentReadFailed": "failed:{{group}}:{{failed}}/{{total}}",
          "save-export.editor.readSettingsPrompt": "Read the instrument settings before using this function.",
          "status.enabled": "Enabled",
          "status.disabled": "Disabled",
          "field.save-pwd.path": "Save location",
          "field.save-image.filename": "Image file name",
          "field.save-waveform.filename": "Waveform file name",
          "save-export.editor.saveImage": "Save image",
          "save-export.editor.saveWaveform": "Save waveform",
          "save-export.editor.mode.setup": "Setup",
          "save-export.editor.setupNote": "Setup storage note",
          "save-export.editor.saveSetup": "Save Setup",
          "save-export.editor.recallSetup": "Recall Setup",
          "save-export.editor.setupSlotTarget": "slot {{slot}}",
          "save-export.editor.recallSetupConfirm": "Recall setup from {{target}}? Confirm.",
        };
        globalThis.translate = (key, values = {}) => {
          let text = translations[key] || key;
          for (const [name, value] of Object.entries(values)) {
            text = text.replaceAll(`{{${name}}}`, String(value));
          }
          return text;
        };

        globalThis.CommandForm = class CommandForm {
          constructor(container, catalog) {
            this.container = container;
            this.catalog = catalog;
            this.valuesResult = {};
            this.queryValuesResult = undefined;
            this.onDirty = () => {};
            this.disabled = false;
            this.clearedDirty = 0;
            this.syncCalls = [];
            this.disableCalls = [];
            this.valueCalls = 0;
            this.renderCalls = 0;
            this.container._fieldNodes = [];
          }
          render(command, options = {}) {
            this.renderCalls += 1;
            this.command = command;
            this.valuesResult = {};
            this.onDirty = options.onDirty || (() => {});
          }
          values() {
            this.valueCalls += 1;
            return this.valuesResult;
          }
          queryValues() {
            if (this.queryValuesResult !== undefined) return this.queryValuesResult;
            return this.command?.presentation?.kind === "setting" ? { action: "query" } : null;
          }
          notifyDirty() { this.onDirty(); }
          setDisabled(value) {
            this.disabled = value;
            this.disableCalls.push(value);
          }
          clearDirty() { this.clearedDirty += 1; }
          syncResult(job, preserveDirty) { this.syncCalls.push([job.job_id, preserveDirty]); }
        };

        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.saveExportApi = { SaveExportEditor };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const makeCatalog = () => {
          const commands = [
            { id: "save-pwd", editor: "save-export", category: "Save / Export", label: "Save location", group: "path-filename", presentation: { kind: "setting", action: "apply", action_field: "action", query_value: "query", apply_value: "set" }, fields: [{ name: "action", type: "enum" }, { name: "path", type: "string" }] },
            { id: "save-filename", editor: "save-export", category: "Save / Export", label: "Default base filename", group: "path-filename", presentation: { kind: "setting", action: "apply", action_field: "action", query_value: "query", apply_value: "set" }, fields: [{ name: "action", type: "enum" }, { name: "name", type: "string" }] },
            { id: "save-image-format", editor: "save-export", category: "Save / Export", label: "Image format", group: "image", presentation: { kind: "setting", action: "apply", action_field: "action", query_value: "query", apply_value: "set" }, fields: [{ name: "action", type: "enum" }, { name: "format", type: "string" }] },
            { id: "save-image-palette", editor: "save-export", category: "Save / Export", label: "Image palette", group: "image", presentation: { kind: "setting", action: "apply", action_field: "action", query_value: "query", apply_value: "set" }, fields: [{ name: "action", type: "enum" }, { name: "palette", type: "string" }] },
            { id: "save-image-ink-saver", editor: "save-export", category: "Save / Export", label: "Ink saver", group: "image", presentation: { kind: "setting", action: "apply", action_field: "action", query_value: "query", apply_value: "set" }, fields: [{ name: "action", type: "enum" }, { name: "enabled", type: "boolean" }] },
            { id: "save-image-factors", editor: "save-export", category: "Save / Export", label: "Image factors", group: "image", presentation: { kind: "setting", action: "apply", action_field: "action", query_value: "query", apply_value: "set" }, fields: [{ name: "action", type: "enum" }, { name: "enabled", type: "boolean" }] },
            { id: "save-image", editor: "save-export", category: "Save / Export", label: "Save image", group: "image", presentation: { kind: "command", action: "save" }, fields: [{ name: "filename", type: "string" }] },
            { id: "save-waveform-format", editor: "save-export", category: "Save / Export", label: "Waveform format", group: "waveform", presentation: { kind: "setting", action: "apply", action_field: "action", query_value: "query", apply_value: "set" }, fields: [{ name: "action", type: "enum" }, { name: "format", type: "string" }] },
            { id: "save-waveform-length", editor: "save-export", category: "Save / Export", label: "Waveform length", group: "waveform", presentation: { kind: "setting", action: "apply", action_field: "action", query_value: "query", apply_value: "set" }, fields: [{ name: "action", type: "enum" }, { name: "points", type: "integer" }] },
            { id: "save-waveform-length-max", editor: "save-export", category: "Save / Export", label: "Max waveform length", group: "waveform", presentation: { kind: "command", action: "read" }, fields: [] },
            { id: "save-waveform", editor: "save-export", category: "Save / Export", label: "Save waveform", group: "waveform", presentation: { kind: "command", action: "save" }, fields: [{ name: "filename", type: "string" }] },
            { id: "setup-save", editor: "save-export", category: "Save / Export", label: "Save setup", presentation: { kind: "command", action: "run" }, fields: [{ name: "target", type: "enum" }, { name: "slot", type: "integer" }, { name: "file", type: "string" }] },
            { id: "setup-recall", editor: "save-export", category: "Save / Export", label: "Recall setup", presentation: { kind: "command", action: "run" }, fields: [{ name: "target", type: "enum" }, { name: "slot", type: "integer" }, { name: "file", type: "string" }] },
            { id: "save-export", editor: "save-export", category: "Save / Export", label: "Save / Export", presentation_only: true, presentation: { kind: "command", action: "run" }, fields: [] },
          ];
          return {
            commands,
            supported: () => true,
            groupLabel: (group) => group,
            commandLabel: (command) => command.label,
            description: () => "",
            fieldsFor: (command) => command.fields || [],
          };
        };

        const buildEditor = (execute = null) => {
          const catalog = makeCatalog();
          const submitted = [];
          const context = { value: "ctx" };
          const executionState = { busy: false, available: true };
          const hooks = {
              executeCommand: async (command, parameters, options) => {
              const job = execute
                ? await execute(command, parameters, options)
                : { status: "completed", job_id: command };
              submitted.push({ command, parameters, intent: options?.intent, job });
              return job;
            },
            isAvailable: () => executionState.available,
            isExecutionBusy: () => executionState.busy,
            contextKey: () => context.value,
            selectedCommand: () => catalog.commands.find((command) => command.id === "save-export"),
          };
          return { editor: new globalThis.saveExportApi.SaveExportEditor(new FakeNode("div"), catalog, hooks), submitted, hooks, catalog, context, executionState };
        };
        '''


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_regression_save_export_explicit_read_and_mode_change() -> None:
    """Regression coverage for A-D requirements."""
    # A: entry does not auto-read
    script_a = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor();
        editor.rebuildSections("ctx|save-export:image");
        editor.schedulePresentation();
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(submitted.length, 0);
        assert.equal(editor.stateKey, null);
        assert.ok(!editor.hasCurrentSettings());
        '''
    )
    completed = run_node(script_a)
    assert completed.returncode == 0, f"A failed: {completed.stderr or completed.stdout}"

    # B: active read after clicking Read Settings
    script_b = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor();
        editor.rebuildSections("ctx|save-export:image");
        editor.scheduleRefresh(true);
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.ok(submitted.some((s) => s.command === "save-pwd"));
        assert.ok(submitted.some((s) => s.command === "save-image-format"));
        assert.ok(editor.hasCurrentSettings());
        '''
    )
    completed = run_node(script_b)
    assert completed.returncode == 0, f"B failed: {completed.stderr or completed.stdout}"

    # C: mode change does not auto-read; old state invalidated; read required before save/apply
    script_c = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor();
        // First complete image read
        await editor.refresh(false, true);
        const imageState = editor.stateKey;
        assert.ok(editor.hasCurrentSettings());

        // Mode change to waveform: presentation only, no auto-query
        editor.modeButtons[1].dispatch("click");
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(editor.mode, "waveform");
        assert.ok(!editor.hasCurrentSettings());
        assert.equal(submitted.filter((s) => s.command === "save-waveform-format").length, 0);

        // Save blocked before read
        await editor.submitCurrentMode("save-waveform");
        assert.equal(submitted.filter((s) => s.command === "save-waveform").length, 0);

        // Read waveform settings explicitly
        editor.scheduleRefresh(true);
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.ok(editor.hasCurrentSettings());

        // After read, save can proceed
        await editor.submitCurrentMode("save-waveform");
        assert.ok(submitted.some((s) => s.command === "save-waveform"));
        '''
    )
    completed = run_node(script_c)
    assert completed.returncode == 0, f"C failed: {completed.stderr or completed.stdout}"

    # D: Setup bypass (no read required, save/recall works, refresh hidden)
    script_d = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor();
        editor.modeButtons[2].dispatch("click");
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(editor.mode, "setup");
        assert.equal(editor.refreshButton.hidden, true);
        assert.ok(editor.hasCurrentSettings());
        // Setup submit should not require prior read
        await editor.submitSetup("setup-save", false);
        assert.ok(submitted.some((s) => s.command === "setup-save"));
        '''
    )
    completed = run_node(script_d)
    assert completed.returncode == 0, f"D failed: {completed.stderr or completed.stdout}"
