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
          "save-export.editor.reloadSettings": "Reload instrument settings",
          "save-export.editor.storageNote": "Instrument-side storage",
          "save-export.editor.pathHelper": "Example: \\usb\\",
          "save-export.editor.pathUnavailable": "Could not read the current save location.",
          "save-export.editor.currentValueUnavailable": "Current value unavailable.",
          "save-export.editor.destinationPreviewLabel": "Destination preview",
          "save-export.editor.advancedSettings": "Advanced settings",
          "save-export.editor.baseFilenameHelp": "This is the instrument SAVE default base filename.",
          "save-export.editor.waveformLengthMaxNote": "Maximum waveform length mode cannot be configured by this tool. If the mode is enabled on the instrument, the manual waveform save length setting has no effect.",
          "save-export.editor.readingCurrent": "reading:{{group}}:{{current}}/{{total}}",
          "save-export.editor.currentLoaded": "loaded:{{group}}",
          "save-export.editor.currentReadFailed": "failed:{{group}}:{{failed}}/{{total}}",
          "actions.apply": "Apply",
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
def test_save_export_editor_shows_only_the_selected_mode() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor } = buildEditor();
        editor.mode = "image";
        editor.rebuildSections("ctx|save-export:image");
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "save-image-format",
          "save-image-palette",
          "save-image-ink-saver",
          "save-image-factors",
        ]);
        assert.ok(!editor.entries.some((entry) => entry.id.startsWith("save-waveform")));

        editor.mode = "waveform";
        editor.rebuildSections("ctx|save-export:waveform");
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "save-waveform-format",
          "save-waveform-length",
        ]);
        assert.ok(!editor.entries.some((entry) => entry.id.startsWith("save-image")));
        assert.ok(editor.sectionsHost.textContent.includes("Maximum waveform length mode"));
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_same_mode_click_preserves_state_and_mode_change_reads_once() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor();
        await editor.refresh(false, true);
        const imagePathEntry = editor.pathEntry;
        const imageReadCount = submitted.length;

        editor.modeButtons[0].dispatch("click");
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(editor.pathEntry, imagePathEntry);
        assert.equal(submitted.length, imageReadCount);

        editor.modeButtons[1].dispatch("click");
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(editor.mode, "waveform");
        assert.notEqual(editor.pathEntry, imagePathEntry);
        assert.deepEqual(submitted.slice(-4).map((entry) => entry.command), [
          "save-pwd",
          "save-filename",
          "save-waveform-format",
          "save-waveform-length",
        ]);
        assert.equal(submitted.length, imageReadCount + 4);
        assert.ok(!submitted.some((entry) => entry.command === "save-waveform-length-max"));
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_reads_and_displays_the_current_save_path() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor } = buildEditor();
        editor.mode = "image";
        editor.rebuildSections("ctx|save-export:image");

        editor.pathEntry.form.queryValuesResult = { path: "\\usb\\" };
        editor.filenameEntry.form.valuesResult = { filename: "scope" };
        editor.entries.find((entry) => entry.id === "save-image-format").form.valuesResult = { format: "PNG" };
        editor.updateDestinationPreview();
        assert.equal(editor.destinationPreview.textContent, "\\usb\\scope.png");

        editor.pathEntry.form.queryValuesResult = null;
        editor.pathStatus.textContent = "";
        await editor.readWorkspace();
        assert.equal(editor.pathStatus.textContent, "Could not read the current save location.");
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_read_progress_is_one_based() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor } = buildEditor();
        const readingProgress = [];
        const setReadStatus = editor.setReadStatus.bind(editor);
        editor.setReadStatus = (kind, values) => {
          if (kind === "reading") readingProgress.push(values.current);
          setReadStatus(kind, values);
        };

        await editor.refresh(false, true);
        assert.deepEqual(readingProgress, [1, 2, 3, 4, 5, 6]);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_does_not_validate_clean_path_before_save() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        let pathValuesCalls = 0;
        const { editor, submitted } = buildEditor((command) => {
          if (command === "save-image") assert.equal(pathValuesCalls, 0);
          return { status: "completed", job_id: command };
        });
        editor.rebuildSections("ctx|save-export:image");
        editor.pathEntry.form.values = () => {
          pathValuesCalls += 1;
          return { action: "set", path: "\\usb\\" };
        };
        editor.filenameEntry.form.valuesResult = { filename: "screen" };

        await editor.submitCurrentMode("save-image");
        assert.deepEqual(submitted.map((entry) => entry.command), ["save-image"]);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_submits_image_settings_then_final_image_save() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor();
        editor.mode = "image";
        editor.rebuildSections("ctx|save-export:image");

        editor.pathEntry.form.valuesResult = { action: "set", path: "\\usb\\" };
        editor.pathEntry.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        editor.filenameEntry.form.valuesResult = { filename: "scope" };
        editor.filenameEntry.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        const imageFormat = editor.entries.find((entry) => entry.id === "save-image-format");
        imageFormat.form.valuesResult = { action: "set", format: "PNG" };
        imageFormat.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        editor.advancedEntry.form.valuesResult = { action: "set", name: "instrument_default" };
        editor.advancedEntry.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];

        await editor.submitCurrentMode("save-image");
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd",
          "save-image-format",
          "save-image",
        ]);
        assert.deepEqual(submitted.map((entry) => entry.parameters), [
          { action: "set", path: "\\usb\\" },
          { action: "set", format: "PNG" },
          { filename: "scope" },
        ]);
        assert.ok(!submitted.some((entry) => entry.command.startsWith("save-waveform")));
        assert.ok(!submitted.some((entry) => entry.command === "save-filename"));
        assert.ok(!submitted.some((entry) => entry.parameters.action === "query"));
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_submits_waveform_settings_then_final_waveform_save() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor();
        editor.mode = "waveform";
        editor.rebuildSections("ctx|save-export:waveform");

        editor.pathEntry.form.valuesResult = { action: "set", path: "\\usb\\" };
        editor.pathEntry.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        editor.filenameEntry.form.valuesResult = { filename: "trace" };
        editor.filenameEntry.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        const waveformFormat = editor.entries.find((entry) => entry.id === "save-waveform-format");
        waveformFormat.form.valuesResult = { action: "set", format: "CSV" };
        waveformFormat.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        const waveformLength = editor.entries.find((entry) => entry.id === "save-waveform-length");
        waveformLength.form.valuesResult = { action: "set", points: 1000 };
        waveformLength.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        editor.advancedEntry.form.valuesResult = { action: "set", name: "instrument_default" };
        editor.advancedEntry.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];

        await editor.submitCurrentMode("save-waveform");
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd",
          "save-waveform-format",
          "save-waveform-length",
          "save-waveform",
        ]);
        assert.deepEqual(submitted.map((entry) => entry.parameters), [
          { action: "set", path: "\\usb\\" },
          { action: "set", format: "CSV" },
          { action: "set", points: 1000 },
          { filename: "trace" },
        ]);
        assert.ok(!submitted.some((entry) => entry.command.startsWith("save-image")));
        assert.ok(!submitted.some((entry) => entry.command === "save-filename"));
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_keeps_default_base_filename_in_advanced_settings() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor } = buildEditor();
        editor.mode = "image";
        editor.rebuildSections("ctx|save-export:image");
        const mainText = editor.sectionsHost.textContent || "";
        assert.ok(!mainText.includes("Default base filename"));
        const advanced = [...editor.sectionsHost.children].find((node) => node.tagName === "DETAILS");
        assert.ok(advanced);
        assert.ok(advanced.textContent.includes("Advanced settings"));
        assert.ok(advanced.textContent.includes("This is the instrument SAVE default base filename."));
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_reads_each_workspace_state_once_on_entry_and_context_change() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted, context } = buildEditor((command) => ({
          status: "completed",
          job_id: command,
          result: { result: {} },
        }));

        await editor.refresh(false, true);
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd",
          "save-filename",
          "save-image-format",
          "save-image-palette",
          "save-image-ink-saver",
          "save-image-factors",
        ]);
        assert.ok(submitted.every((entry) => entry.parameters.action === "query"));
        assert.ok(editor.entries.every((entry) => entry.form.command.fields.some((field) => field.name === "action")));

        const firstReadCount = submitted.length;
        await editor.refresh(false, true);
        assert.equal(submitted.length, firstReadCount);

        context.value = "changed-context";
        await editor.refresh(false, true);
        assert.equal(submitted.length, firstReadCount * 2);

        editor.mode = "waveform";
        await editor.refresh(false, true);
        assert.deepEqual(submitted.slice(-4).map((entry) => entry.command), [
          "save-pwd",
          "save-filename",
          "save-waveform-format",
          "save-waveform-length",
        ]);
        assert.ok(!submitted.some((entry) => entry.command === "save-waveform-length-max"));
        assert.ok(editor.sectionsHost.textContent.includes("Maximum waveform length mode"));
        assert.ok(!editor.entries.some((entry) => entry.id === "save-waveform-length-max"));
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_retries_an_interrupted_read_without_premarking_loaded() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        let built;
        let interrupt = true;
        built = buildEditor(async (command) => {
          if (interrupt && command === "save-image-format") {
            interrupt = false;
            built.hooks.selectedCommand = () => null;
          }
          return { status: "completed", job_id: command, result: { result: {} } };
        });
        const { editor, submitted, hooks, catalog } = built;

        await editor.refresh(false, false);
        assert.equal(submitted.length, 0);
        assert.equal(editor.renderedKey, "ctx|save-export:image");
        assert.equal(editor.stateKey, null);

        await editor.refresh(false, true);
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd",
          "save-filename",
          "save-image-format",
        ]);
        assert.equal(editor.stateKey, null);

        hooks.selectedCommand = () => catalog.commands.find((command) => command.id === "save-export");
        const interruptedCount = submitted.length;
        await editor.refresh(false, true);
        assert.equal(submitted.length, interruptedCount + 6);
        assert.deepEqual(submitted.slice(interruptedCount).map((entry) => entry.command), [
          "save-pwd",
          "save-filename",
          "save-image-format",
          "save-image-palette",
          "save-image-ink-saver",
          "save-image-factors",
        ]);
        assert.equal(editor.stateKey, "ctx|save-export:image");
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_invalidates_loaded_state_before_interrupted_forced_read() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        let built;
        let interruptForcedRead = false;
        built = buildEditor(async (command) => {
          if (interruptForcedRead && command === "save-image-format") {
            interruptForcedRead = false;
            built.hooks.selectedCommand = () => null;
          }
          return { status: "completed", job_id: command, result: { result: {} } };
        });
        const { editor, submitted, hooks, catalog } = built;

        await editor.refresh(false, true);
        assert.equal(editor.stateKey, "ctx|save-export:image");
        assert.equal(submitted.length, 6);

        interruptForcedRead = true;
        const forcedStart = submitted.length;
        await editor.refresh(true, true);
        assert.deepEqual(submitted.slice(forcedStart).map((entry) => entry.command), [
          "save-pwd",
          "save-filename",
          "save-image-format",
        ]);
        assert.equal(editor.stateKey, null);

        hooks.selectedCommand = () => catalog.commands.find((command) => command.id === "save-export");
        const retryStart = submitted.length;
        await editor.refresh(false, true);
        assert.deepEqual(submitted.slice(retryStart).map((entry) => entry.command), [
          "save-pwd",
          "save-filename",
          "save-image-format",
          "save-image-palette",
          "save-image-ink-saver",
          "save-image-factors",
        ]);
        assert.equal(editor.stateKey, "ctx|save-export:image");
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_resyncs_format_after_explicit_image_and_waveform_extensions() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const imageReads = { count: 0 };
        const imageBuilt = buildEditor((command, parameters) => {
          if (command === "save-image-format" && parameters.action === "query") {
            imageReads.count += 1;
            const format = imageReads.count === 1 ? "PNG" : "BMP";
            return { status: "completed", job_id: `image-format-${imageReads.count}`, result: { result: { state: { format } } } };
          }
          return { status: "completed", job_id: command, result: { result: {} } };
        });
        const imageEditor = imageBuilt.editor;
        imageEditor.rebuildSections("ctx|save-export:image");
        const imageFormat = imageEditor.entries.find((entry) => entry.id === "save-image-format");
        imageFormat.form.syncResult = function (job, preserveDirty) {
          this.syncCalls.push([job.job_id, preserveDirty]);
          const format = job?.result?.result?.state?.format;
          if (format) this.valuesResult = { format };
        };
        await imageEditor.refresh(false, true);
        assert.equal(imageFormat.form.valuesResult.format, "PNG");
        const imageStart = imageBuilt.submitted.length;
        imageEditor.filenameEntry.form.valuesResult = { filename: "screen.bmp" };
        await imageEditor.submitCurrentMode("save-image");
        const imageCommands = imageBuilt.submitted.slice(imageStart);
        assert.deepEqual(imageCommands.map((entry) => entry.command), [
          "save-image",
          "save-image-format",
        ]);
        assert.deepEqual(imageCommands[0].parameters, { filename: "screen.bmp" });
        assert.deepEqual(imageCommands[1].parameters, { action: "query" });
        assert.equal(imageCommands[1].intent, "readback");
        assert.ok(!imageCommands.some((entry) => entry.parameters.action === "set"));
        assert.ok(!imageCommands.some((entry) => entry.command === "save-filename"));
        assert.equal(imageFormat.form.valuesResult.format, "BMP");
        imageEditor.filenameEntry.form.valuesResult = { filename: "screen2" };
        imageEditor.updateDestinationPreview();
        assert.equal(imageEditor.destinationPreview.textContent, "screen2.bmp");

        const waveformReads = { count: 0 };
        const waveformBuilt = buildEditor((command, parameters) => {
          if (command === "save-waveform-format" && parameters.action === "query") {
            waveformReads.count += 1;
            const format = waveformReads.count === 1 ? "BINARY" : "CSV";
            return { status: "completed", job_id: `waveform-format-${waveformReads.count}`, result: { result: { state: { format } } } };
          }
          return { status: "completed", job_id: command, result: { result: {} } };
        });
        const waveformEditor = waveformBuilt.editor;
        waveformEditor.mode = "waveform";
        waveformEditor.rebuildSections("ctx|save-export:waveform");
        const waveformFormat = waveformEditor.entries.find((entry) => entry.id === "save-waveform-format");
        waveformFormat.form.syncResult = function (job, preserveDirty) {
          this.syncCalls.push([job.job_id, preserveDirty]);
          const format = job?.result?.result?.state?.format;
          if (format) this.valuesResult = { format };
        };
        await waveformEditor.refresh(false, true);
        assert.equal(waveformFormat.form.valuesResult.format, "BINARY");
        const waveformStart = waveformBuilt.submitted.length;
        waveformEditor.filenameEntry.form.valuesResult = { filename: "trace.csv" };
        await waveformEditor.submitCurrentMode("save-waveform");
        const waveformCommands = waveformBuilt.submitted.slice(waveformStart);
        assert.deepEqual(waveformCommands.map((entry) => entry.command), [
          "save-waveform",
          "save-waveform-format",
        ]);
        assert.deepEqual(waveformCommands[0].parameters, { filename: "trace.csv" });
        assert.deepEqual(waveformCommands[1].parameters, { action: "query" });
        assert.ok(!waveformCommands.some((entry) => entry.parameters.action === "set"));
        assert.ok(!waveformCommands.some((entry) => entry.command === "save-filename"));
        assert.equal(waveformFormat.form.valuesResult.format, "CSV");
        waveformEditor.filenameEntry.form.valuesResult = { filename: "trace2" };
        waveformEditor.updateDestinationPreview();
        assert.equal(waveformEditor.destinationPreview.textContent, "trace2.csv");
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_invalidates_loaded_state_when_format_resync_becomes_stale() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        let built;
        let formatReads = 0;
        built = buildEditor((command, parameters) => {
          if (command === "save-image-format" && parameters.action === "query") {
            formatReads += 1;
            const format = formatReads === 1 ? "PNG" : "BMP";
            return { status: "completed", job_id: `format-${formatReads}`, result: { result: { state: { format } } } };
          }
          if (command === "save-image") built.hooks.selectedCommand = () => null;
          return { status: "completed", job_id: command, result: { result: {} } };
        });
        const { editor, submitted, hooks, catalog } = built;
        editor.rebuildSections("ctx|save-export:image");
        const format = editor.entries.find((entry) => entry.id === "save-image-format");
        format.form.syncResult = function (job, preserveDirty) {
          this.syncCalls.push([job.job_id, preserveDirty]);
          const value = job?.result?.result?.state?.format;
          if (value) this.valuesResult = { format: value };
        };

        await editor.refresh(false, true);
        assert.equal(editor.stateKey, "ctx|save-export:image");
        assert.equal(format.form.valuesResult.format, "PNG");

        const saveStart = submitted.length;
        editor.filenameEntry.form.valuesResult = { filename: "screen.bmp" };
        await editor.submitCurrentMode("save-image");
        const saveCommands = submitted.slice(saveStart);
        assert.deepEqual(saveCommands.map((entry) => entry.command), ["save-image"]);
        assert.equal(saveCommands[0].job.status, "completed");
        assert.equal(submitted.filter((entry) => entry.command === "save-image").length, 1);
        assert.equal(editor.stateKey, null);
        assert.ok(!editor.readStatus.textContent.startsWith("failed:"));

        hooks.selectedCommand = () => catalog.commands.find((command) => command.id === "save-export");
        const retryStart = submitted.length;
        await editor.refresh(false, true);
        assert.deepEqual(submitted.slice(retryStart).map((entry) => entry.command), [
          "save-pwd",
          "save-filename",
          "save-image-format",
          "save-image-palette",
          "save-image-ink-saver",
          "save-image-factors",
        ]);
        assert.equal(editor.stateKey, "ctx|save-export:image");
        assert.equal(format.form.valuesResult.format, "BMP");
        editor.filenameEntry.form.valuesResult = { filename: "screen2" };
        editor.updateDestinationPreview();
        assert.equal(editor.destinationPreview.textContent, "screen2.bmp");
        assert.equal(submitted.filter((entry) => entry.command === "save-image").length, 1);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_keeps_successful_save_when_format_resync_fails() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        let formatReads = 0;
        const { editor, submitted } = buildEditor((command, parameters) => {
          if (command === "save-image-format" && parameters.action === "query") {
            formatReads += 1;
            if (formatReads === 2) return { status: "failed", job_id: "format-resync" };
            const format = formatReads === 1 ? "PNG" : "BMP";
            return { status: "completed", job_id: `format-${formatReads}`, result: { result: { state: { format } } } };
          }
          return { status: "completed", job_id: command, result: { result: {} } };
        });
        editor.rebuildSections("ctx|save-export:image");
        const format = editor.entries.find((entry) => entry.id === "save-image-format");
        format.form.syncResult = function (job, preserveDirty) {
          this.syncCalls.push([job.job_id, preserveDirty]);
          const value = job?.result?.result?.state?.format;
          if (value) this.valuesResult = { format: value };
        };
        await editor.refresh(false, true);
        assert.equal(editor.stateKey, "ctx|save-export:image");
        assert.equal(format.form.valuesResult.format, "PNG");
        const advancedDirty = { dataset: { dirty: "true" } };
        editor.advancedEntry.form.valuesResult = { action: "set", name: "keep_me" };
        editor.advancedEntry.form.container._fieldNodes = [advancedDirty];

        const saveStart = submitted.length;
        editor.filenameEntry.form.valuesResult = { filename: "screen.bmp" };
        await editor.submitCurrentMode("save-image");
        const saveCommands = submitted.slice(saveStart);
        assert.deepEqual(saveCommands.map((entry) => entry.command), [
          "save-image",
          "save-image-format",
        ]);
        assert.equal(saveCommands[0].job.status, "completed");
        assert.equal(saveCommands[1].job.status, "failed");
        assert.equal(submitted.filter((entry) => entry.command === "save-image").length, 1);
        assert.equal(format.form.renderCalls, 2);
        assert.deepEqual(format.form.valuesResult, {});
        assert.equal(editor.stateKey, null);
        assert.ok(editor.readStatus.textContent.startsWith("failed:Image"));
        assert.equal(editor.advancedEntry.form.container._fieldNodes[0], advancedDirty);

        await editor.refresh(true, true);
        assert.equal(submitted.filter((entry) => entry.command === "save-image").length, 1);
        assert.equal(editor.stateKey, "ctx|save-export:image");
        assert.equal(format.form.valuesResult.format, "BMP");
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_resumes_initial_and_forced_reads_after_global_busy() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted, context, executionState } = buildEditor();
        executionState.busy = true;
        editor.schedulePresentation();
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(submitted.length, 0);
        assert.equal(editor.pendingRefresh, true);
        assert.equal(editor.pendingRefreshForce, false);

        context.value = "changed-context";
        executionState.busy = false;
        editor.applyBusyState();
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd",
          "save-filename",
          "save-image-format",
          "save-image-palette",
          "save-image-ink-saver",
          "save-image-factors",
        ]);
        assert.equal(editor.stateKey, "changed-context|save-export:image");
        const firstReadCount = submitted.length;

        editor.applyBusyState();
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(submitted.length, firstReadCount);

        executionState.busy = true;
        editor.scheduleRefresh(true);
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(submitted.length, firstReadCount);
        assert.equal(editor.pendingRefresh, true);
        assert.equal(editor.pendingRefreshForce, true);

        executionState.busy = false;
        executionState.available = false;
        editor.applyBusyState();
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(submitted.length, firstReadCount);
        assert.equal(editor.pendingRefresh, true);
        assert.equal(editor.pendingRefreshForce, true);

        executionState.available = true;
        editor.applyBusyState();
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(submitted.length, firstReadCount * 2);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_applies_advanced_filename_only_when_requested() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor();
        editor.mode = "image";
        editor.rebuildSections("ctx|save-export:image");
        const advanced = editor.advancedEntry;
        assert.ok(advanced.form.command.fields.some((field) => field.name === "action"));
        advanced.form.valuesResult = { action: "set", name: "instrument_default" };
        advanced.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];

        await editor.submitCurrentMode("save-image");
        assert.deepEqual(submitted.map((entry) => entry.command), ["save-image"]);

        await advanced.form.onDirty();
        await editor.applyAdvancedFilename(advanced);
        assert.deepEqual(submitted.map((entry) => entry.command), ["save-image", "save-filename"]);
        assert.deepEqual(submitted[1].parameters, { action: "set", name: "instrument_default" });
        assert.equal(submitted[1].intent, "apply");
        assert.equal(advanced.form.clearedDirty, 1);
        assert.deepEqual(advanced.form.syncCalls, [["save-filename", false]]);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_preserves_advanced_filename_after_failed_apply() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor((command) => ({
          status: command === "save-filename" ? "failed" : "completed",
          job_id: command,
        }));
        editor.mode = "image";
        editor.rebuildSections("ctx|save-export:image");
        const advanced = editor.advancedEntry;
        const dirtyField = { dataset: { dirty: "true" } };
        advanced.form.valuesResult = { action: "set", name: "keep_me" };
        advanced.form.container._fieldNodes = [dirtyField];

        const job = await editor.applyAdvancedFilename(advanced);
        assert.equal(job.status, "failed");
        assert.deepEqual(submitted.map((entry) => entry.command), ["save-filename"]);
        assert.equal(advanced.form.clearedDirty, 0);
        assert.equal(advanced.form.container._fieldNodes[0], dirtyField);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_primary_save_button_tracks_busy_and_availability() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, executionState } = buildEditor();
        editor.rebuildSections("ctx|save-export:image");
        assert.equal(editor.saveButton.disabled, false);

        editor.busy = true;
        editor.applyBusyState();
        assert.equal(editor.saveButton.disabled, true);

        editor.busy = false;
        executionState.busy = true;
        editor.applyBusyState();
        assert.equal(editor.saveButton.disabled, true);

        executionState.busy = false;
        executionState.available = false;
        editor.applyBusyState();
        assert.equal(editor.saveButton.disabled, true);

        executionState.available = true;
        editor.applyBusyState();
        assert.equal(editor.saveButton.disabled, false);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_blocks_final_save_after_prerequisite_failure() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor((command) => ({
          status: command === "save-image-format" ? "failed" : "completed",
          job_id: command,
        }));
        editor.mode = "image";
        editor.rebuildSections("ctx|save-export:image");
        editor.pathEntry.form.valuesResult = { action: "set", path: "\\usb\\" };
        editor.pathEntry.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        const format = editor.entries.find((entry) => entry.id === "save-image-format");
        format.form.valuesResult = { action: "set", format: "png" };
        format.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        editor.filenameEntry.form.valuesResult = { filename: "screen" };

        await editor.submitCurrentMode("save-image");
        assert.deepEqual(submitted.map((entry) => entry.command), ["save-pwd", "save-image-format"]);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_updates_preview_for_formats_and_empty_filename() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor } = buildEditor();
        editor.mode = "image";
        editor.rebuildSections("ctx|save-export:image");
        editor.pathEntry.form.valuesResult = { path: "\\usb\\" };
        editor.filenameEntry.form.valuesResult = { filename: "screen" };
        const imageFormat = editor.entries.find((entry) => entry.id === "save-image-format");

        for (const [format, suffix] of [["PNG", ".png"], ["BMP", ".bmp"], ["BMP8", ".bmp"], ["BMP24", ".bmp"]]) {
          imageFormat.form.valuesResult = { format };
          editor.updateDestinationPreview();
          assert.equal(editor.destinationPreview.textContent, `\\usb\\screen${suffix}`);
        }

        imageFormat.form.valuesResult = { format: "none" };
        editor.updateDestinationPreview();
        assert.equal(editor.destinationPreview.textContent, "\\usb\\screen");
        imageFormat.form.valuesResult = { format: "future-format" };
        editor.updateDestinationPreview();
        assert.equal(editor.destinationPreview.textContent, "\\usb\\screen");
        imageFormat.form.valuesResult = { format: "" };
        editor.updateDestinationPreview();
        assert.equal(editor.destinationPreview.textContent, "\\usb\\screen");
        imageFormat.form.valuesResult = { format: "PNG" };
        editor.filenameEntry.form.valuesResult = { filename: "screen.bmp" };
        editor.filenameEntry.form.notifyDirty();
        assert.equal(editor.destinationPreview.textContent, "\\usb\\screen.bmp");
        editor.filenameEntry.form.valuesResult = { filename: "captures/screen" };
        editor.filenameEntry.form.notifyDirty();
        assert.equal(editor.destinationPreview.textContent, "captures/screen");

        editor.filenameEntry.form.valuesResult = {};
        editor.pathEntry.form.notifyDirty();
        assert.equal(editor.destinationPreview.textContent, "\\usb\\");
        assert.ok(!editor.destinationPreview.textContent.includes("scope"));

        editor.mode = "waveform";
        editor.rebuildSections("ctx|save-export:waveform");
        editor.pathEntry.form.valuesResult = { path: "\\usb\\" };
        editor.filenameEntry.form.valuesResult = { filename: "trace" };
        const waveformFormat = editor.entries.find((entry) => entry.id === "save-waveform-format");
        for (const [format, suffix] of [["CSV", ".csv"], ["ascii-xy", ".csv"], ["BINARY", ".bin"]]) {
          waveformFormat.form.valuesResult = { format };
          editor.updateDestinationPreview();
          assert.equal(editor.destinationPreview.textContent, `\\usb\\trace${suffix}`);
        }
        waveformFormat.form.valuesResult = { format: "none" };
        editor.updateDestinationPreview();
        assert.equal(editor.destinationPreview.textContent, "\\usb\\trace");
        waveformFormat.form.valuesResult = { format: "unknown" };
        editor.updateDestinationPreview();
        assert.equal(editor.destinationPreview.textContent, "\\usb\\trace");
        waveformFormat.form.valuesResult = { format: "" };
        editor.updateDestinationPreview();
        assert.equal(editor.destinationPreview.textContent, "\\usb\\trace");
        editor.filenameEntry.form.valuesResult = { filename: "D:\\captures\\trace.csv" };
        editor.filenameEntry.form.notifyDirty();
        assert.equal(editor.destinationPreview.textContent, "D:\\captures\\trace.csv");
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_setup_mode_has_no_readback_io() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor();
        editor.modeButtons[2].dispatch("click");
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(editor.mode, "setup");
        await editor.refresh(false, true);
        assert.equal(submitted.length, 0);
        assert.equal(editor.refreshButton.hidden, true);
        assert.deepEqual(editor.entries, []);
        assert.equal(editor.pathEntry, null);
        assert.equal(editor.filenameEntry, null);
        assert.ok(editor.setupEntry);
        assert.ok(editor.setupSaveButton);
        assert.ok(editor.setupRecallButton);
        assert.ok(editor.sectionsHost.textContent.includes("Setup storage note"));
        assert.ok(!editor.sectionsHost.textContent.includes("Maximum waveform length mode"));
        editor.modeButtons[0].dispatch("click");
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(editor.mode, "image");
        assert.equal(editor.refreshButton.hidden, false);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_setup_save_submits_target_parameters() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const { editor, submitted } = buildEditor();
        editor.mode = "setup";
        editor.rebuildSections("ctx|save-export:setup");
        editor.setupEntry.form.valuesResult = { target: "slot", slot: 1 };
        editor.setupSaveButton.dispatch("click");
        await new Promise((resolve) => setTimeout(resolve, 0));
        editor.setupEntry.form.valuesResult = { target: "file", file: "\\usb\\baseline.scp" };
        editor.setupSaveButton.dispatch("click");
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.deepEqual(submitted.map((entry) => entry.command), ["setup-save", "setup-save"]);
        assert.deepEqual(submitted[0].parameters, { target: "slot", slot: 1 });
        assert.deepEqual(submitted[1].parameters, { target: "file", file: "\\usb\\baseline.scp" });
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_setup_recall_confirms_before_executing() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const confirmMessages = [];
        globalThis.window = { confirm: (message) => { confirmMessages.push(message); return true; } };
        const { editor, submitted } = buildEditor();
        editor.mode = "setup";
        editor.rebuildSections("ctx|save-export:setup");
        editor.setupEntry.form.valuesResult = { target: "slot", slot: 1 };
        editor.setupRecallButton.dispatch("click");
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(submitted.length, 1);
        assert.equal(submitted[0].command, "setup-recall");
        assert.deepEqual(submitted[0].parameters, { target: "slot", slot: 1 });
        assert.ok(confirmMessages[0].includes("slot 1"));
        editor.setupEntry.form.valuesResult = { target: "file", file: "\\usb\\baseline.scp" };
        editor.setupRecallButton.dispatch("click");
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(submitted.length, 2);
        assert.ok(confirmMessages[1].includes("\\usb\\baseline.scp"));
        globalThis.window = { confirm: (message) => { confirmMessages.push(message); return false; } };
        editor.setupRecallButton.dispatch("click");
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.equal(submitted.length, 2);
        assert.equal(confirmMessages.length, 3);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout
