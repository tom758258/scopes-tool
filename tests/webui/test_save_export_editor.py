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
            this.queryValuesResult = {};
            this.disabled = false;
            this.clearedDirty = 0;
            this.syncCalls = [];
            this.disableCalls = [];
            this.container._fieldNodes = [];
          }
          render(command) {
            this.command = command;
          }
          values() { return this.valuesResult; }
          queryValues() { return this.queryValuesResult; }
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
            { id: "save-pwd", editor: "save-export", category: "Save / Export", label: "Save location", group: "path-filename", presentation: { kind: "setting", action: "apply" }, fields: [{ name: "path", type: "string" }] },
            { id: "save-filename", editor: "save-export", category: "Save / Export", label: "Default base filename", group: "path-filename", presentation: { kind: "setting", action: "apply" }, fields: [{ name: "name", type: "string" }] },
            { id: "save-image-format", editor: "save-export", category: "Save / Export", label: "Image format", group: "image", presentation: { kind: "setting", action: "apply" }, fields: [{ name: "format", type: "string" }] },
            { id: "save-image-palette", editor: "save-export", category: "Save / Export", label: "Image palette", group: "image", presentation: { kind: "setting", action: "apply" }, fields: [{ name: "palette", type: "string" }] },
            { id: "save-image-ink-saver", editor: "save-export", category: "Save / Export", label: "Ink saver", group: "image", presentation: { kind: "setting", action: "apply" }, fields: [{ name: "enabled", type: "boolean" }] },
            { id: "save-image-factors", editor: "save-export", category: "Save / Export", label: "Image factors", group: "image", presentation: { kind: "setting", action: "apply" }, fields: [{ name: "enabled", type: "boolean" }] },
            { id: "save-image", editor: "save-export", category: "Save / Export", label: "Save image", group: "image", presentation: { kind: "command", action: "save" }, fields: [{ name: "filename", type: "string" }] },
            { id: "save-waveform-format", editor: "save-export", category: "Save / Export", label: "Waveform format", group: "waveform", presentation: { kind: "setting", action: "apply" }, fields: [{ name: "format", type: "string" }] },
            { id: "save-waveform-length", editor: "save-export", category: "Save / Export", label: "Waveform length", group: "waveform", presentation: { kind: "setting", action: "apply" }, fields: [{ name: "points", type: "integer" }] },
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

        const buildEditor = () => {
          const catalog = makeCatalog();
          const submitted = [];
          const hooks = {
            executeCommand: async (command, parameters, options) => {
              submitted.push({ command, parameters, intent: options?.intent, job: { status: "completed" } });
              return { status: "completed", job_id: command };
            },
            isAvailable: () => true,
            isExecutionBusy: () => false,
            contextKey: () => "ctx",
            selectedCommand: () => catalog.commands.find((command) => command.id === "save-export"),
          };
          return { editor: new globalThis.saveExportApi.SaveExportEditor(new FakeNode("div"), catalog, hooks), submitted, hooks, catalog };
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
          "save-waveform-length-max",
        ]);
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

        editor.pathEntry.form.valuesResult = { path: "\\usb\\" };
        editor.pathEntry.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        editor.filenameEntry.form.valuesResult = { filename: "scope" };
        editor.filenameEntry.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        const imageFormat = editor.entries.find((entry) => entry.id === "save-image-format");
        imageFormat.form.valuesResult = { format: "PNG" };
        imageFormat.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];

        await editor.submitCurrentMode("save-image");
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd",
          "save-image-format",
          "save-image",
        ]);
        assert.ok(!submitted.some((entry) => entry.command.startsWith("save-waveform")));
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

        editor.pathEntry.form.valuesResult = { path: "\\usb\\" };
        editor.pathEntry.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        editor.filenameEntry.form.valuesResult = { filename: "trace" };
        editor.filenameEntry.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];
        const waveformFormat = editor.entries.find((entry) => entry.id === "save-waveform-format");
        waveformFormat.form.valuesResult = { format: "CSV" };
        waveformFormat.form.container._fieldNodes = [{ dataset: { dirty: "true" } }];

        await editor.submitCurrentMode("save-waveform");
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd",
          "save-waveform-format",
          "save-waveform",
        ]);
        assert.ok(!submitted.some((entry) => entry.command.startsWith("save-image")));
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
