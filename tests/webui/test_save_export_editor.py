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
          "save-export.editor.destinationPreviewLabel": "Destination preview",
          "save-export.editor.advancedSettings": "Advanced settings",
          "save-export.editor.baseFilenameHelp": "This is the instrument SAVE default base filename.",
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
            this.container._fieldNodes = [];
          }
          render(command, options = {}) {
            this.command = command;
            this.onDirty = options.onDirty || (() => {});
          }
          values() { return this.valuesResult; }
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
          const hooks = {
              executeCommand: async (command, parameters, options) => {
              const job = execute
                ? await execute(command, parameters, options)
                : { status: "completed", job_id: command };
              submitted.push({ command, parameters, intent: options?.intent, job });
              return job;
            },
            isAvailable: () => true,
            isExecutionBusy: () => false,
            contextKey: () => context.value,
            selectedCommand: () => catalog.commands.find((command) => command.id === "save-export"),
          };
          return { editor: new globalThis.saveExportApi.SaveExportEditor(new FakeNode("div"), catalog, hooks), submitted, hooks, catalog, context };
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
        assert.equal(editor.lengthMaxEntry.id, "save-waveform-length-max");
        assert.ok(!editor.entries.some((entry) => entry.id.startsWith("save-image")));
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
          result: command === "save-waveform-length-max"
            ? { result: { state: { enabled: true } } }
            : { result: {} },
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
        assert.deepEqual(submitted.slice(-5).map((entry) => entry.command), [
          "save-pwd",
          "save-filename",
          "save-waveform-format",
          "save-waveform-length",
          "save-waveform-length-max",
        ]);
        assert.deepEqual(submitted.slice(-1)[0].parameters, {});
        assert.equal(editor.lengthMaxEntry.value.textContent, "Enabled");
        assert.ok(!editor.entries.some((entry) => entry.id === "save-waveform-length-max"));
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

        for (const [format, suffix] of [["PNG", ".png"], ["BMP24", ".bmp"]]) {
          imageFormat.form.valuesResult = { format };
          editor.updateDestinationPreview();
          assert.equal(editor.destinationPreview.textContent, `\\usb\\screen${suffix}`);
        }

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
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout
