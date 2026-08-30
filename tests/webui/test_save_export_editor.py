from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_webui.commands import COMMANDS, command_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
SAVE_EXPORT_EDITOR_SOURCE = STATIC_ROOT / "save-export-editor.js"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


EXPECTED_SAVE_EXPORT_GROUPS = {
    "save-pwd": "path-filename",
    "save-filename": "path-filename",
    "save-image-format": "image",
    "save-image-palette": "image",
    "save-image-ink-saver": "image",
    "save-image-factors": "image",
    "save-image": "image",
    "save-waveform-format": "waveform",
    "save-waveform-length": "waveform",
    "save-waveform-length-max": "waveform",
    "save-waveform": "waveform",
}


def test_save_export_commands_keep_groups_and_route_to_the_dedicated_editor() -> None:
    save_commands = [entry for entry in COMMANDS if entry["category"] == "Save / Export"]

    assert {entry["id"] for entry in save_commands} == set(EXPECTED_SAVE_EXPORT_GROUPS)
    for entry in save_commands:
        assert entry.get("editor") == "save-export", entry["id"]
        assert entry["group"] == EXPECTED_SAVE_EXPORT_GROUPS[entry["id"]]

    catalog = {entry["id"]: entry for entry in command_catalog()}
    assert catalog["save-image-format"]["presentation"]["kind"] == "setting"
    assert catalog["save-waveform-length-max"]["presentation"]["kind"] == "command"
    assert catalog["save-waveform-length-max"]["presentation"]["action"] == "read"
    assert catalog["save-waveform-length-max"]["fields"] == []
    assert catalog["save-image"]["presentation"]["action"] == "save"
    assert catalog["save-waveform"]["presentation"]["action"] == "save"
    expected_help = {
        "save-image-palette": ("palette", "save-image-palette.palette"),
        "save-image-ink-saver": ("enabled", "save-image-ink-saver.enabled"),
        "save-image-factors": ("enabled", "save-image-factors.enabled"),
        "save-waveform-length": ("points", "save-waveform-length.points"),
        "save-image": ("filename", "save-image.filename"),
        "save-waveform": ("filename", "save-waveform.filename"),
    }
    for command_id, (field_name, help_key) in expected_help.items():
        field = next(
            field for field in catalog[command_id]["fields"] if field["name"] == field_name
        )
        assert field["help_key"] == help_key


def test_save_export_editor_frontend_wiring_and_localization() -> None:
    app_source = read_static("app.js")
    html = read_static("index.html")
    editor_source = read_static("save-export-editor.js")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert 'import { SaveExportEditor } from "/static/save-export-editor.js";' in app_source
    assert 'id="save-export-editor" class="save-export-editor trigger-editor" hidden' in html
    assert '"save-export": () => saveExportEditor,' in app_source
    assert "saveExportEditor = new SaveExportEditor(elements.saveExportEditor, catalog, {" in app_source
    assert 'elements.saveExportEditor.hidden = editorKind !== "save-export";' in app_source
    assert "elements.form.hidden = editorOwned;" in app_source
    assert "headerActions: elements.workspaceHeaderActions," in app_source
    assert "headerActions" in editor_source
    assert "saveExportEditor?.schedulePresentation();" in app_source
    assert "saveExportEditor?.rerender();" in app_source
    assert '["measurement", "save-export"].includes(editorKind)' in app_source
    assert "this.catalog.description?.(command)" in editor_source
    assert "applyAll" not in editor_source
    assert "Apply All" not in editor_source
    for key in (
        "save-export.editor.title",
        "save-export.editor.description",
        "save-export.editor.storageNote",
        "save-export.editor.readingCurrent",
        "save-export.editor.currentLoaded",
        "save-export.editor.currentReadFailed",
        "save-export.editor.currentValueUnavailable",
        "save-export.editor.workspaceLabel",
        "save-export.editor.workspaceName",
        "description.save-waveform-length-max",
        "help.save-image-palette.palette",
        "help.save-image-ink-saver.enabled",
        "help.save-image-factors.enabled",
        "help.save-waveform-length.points",
        "help.save-image.filename",
        "help.save-waveform.filename",
    ):
        assert f'"{key}":' in english
        assert f'"{key}":' in chinese
    assert "instrument-side storage" in english
    assert "儀器端儲存裝置" in chinese
    assert '"command.save-waveform-length-max": "Use maximum waveform length"' in english
    assert '"command.save-waveform-length-max": "使用最大波形長度"' in chinese


SAVE_EXPORT_EDITOR_HARNESS = r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.className = "";
            this.textContent = "";
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) { this.children.push(...nodes); }
          insertBefore(node, reference) {
            const index = this.children.indexOf(reference);
            if (index < 0) this.children.push(node);
            else this.children.splice(index, 0, node);
          }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        const translations = {
          "save-export.editor.readingCurrent": "reading:{{group}}:{{current}}/{{total}}",
          "save-export.editor.currentLoaded": "loaded:{{group}}",
          "save-export.editor.currentReadFailed": "failed:{{group}}:{{failed}}/{{total}}",
          "save-export.editor.currentValueUnavailable": "current-value-unavailable",
          "save-export.editor.workspaceLabel": "workspace",
          "save-export.editor.workspaceName": "workspace",
        };
        globalThis.translate = (key, values = {}) => {
          let text = translations[key] || key;
          for (const [name, value] of Object.entries(values)) {
            text = text.replaceAll(`{{${name}}}`, String(value));
          }
          return text;
        };
        globalThis.CommandForm = class CommandForm {
          constructor(container) {
            this.container = container;
            this.renderedCommand = null;
            this.queryValuesResult = { action: "query" };
            this.valuesResult = {};
            this.syncCalls = [];
            this.clearedDirty = 0;
            this.disableCalls = [];
          }
          render(command) { this.renderedCommand = command; }
          values() { return this.valuesResult; }
          queryValues() { return this.queryValuesResult; }
          setDisabled(value) { this.disableCalls.push(value); }
          clearDirty() { this.clearedDirty += 1; }
          syncResult(job, preserveDirty) { this.syncCalls.push([job.job_id, preserveDirty]); }
        };

        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.saveExportApi = { SaveExportEditor };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const settle = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
          await new Promise((resolve) => setTimeout(resolve, 0));
        };
        const settingPresentation = {
          kind: "setting", action: "apply", action_field: "action",
          apply_value: "set", query_value: "query", query_fields: [],
        };
        const def = (id, group, presentation, fields = []) => ({
          id,
          editor: "save-export",
          category: "Save / Export",
          label: id,
          modes: ["live", "simulate"],
          group,
          presentation,
          fields,
        });
        const setting = (id, group) => def(id, group, settingPresentation, [
          { name: "action", type: "enum", options: ["query", "set"] },
        ]);
        const save = (id, group) => def(id, group, { kind: "command", action: "save" }, [
          { name: "filename", type: "string", required: true },
        ]);
        const commands = [
          setting("save-pwd", "path-filename"),
          setting("save-filename", "path-filename"),
          setting("save-image-format", "image"),
          setting("save-image-palette", "image"),
          setting("save-image-ink-saver", "image"),
          setting("save-image-factors", "image"),
          save("save-image", "image"),
          setting("save-waveform-format", "waveform"),
          setting("save-waveform-length", "waveform"),
          def("save-waveform-length-max", "waveform", { kind: "command", action: "read" }),
          save("save-waveform", "waveform"),
        ];
        const catalog = {
          commands,
          supported: () => true,
          groupLabel: (group) => group,
          commandLabel: (command) => command.label,
        };
        const env = {
          available: true, executionBusy: false, contextKey: "ctx", selectedId: "save-pwd",
        };
        const submitted = [];
        const recordingExecute = async (command, parameters, options) => {
          const payload = command === "save-waveform-length-max" ? { enabled: true } : {};
          const job = {
            job_id: `${command}-${submitted.length}`,
            status: "completed",
            result: { result: payload },
          };
          submitted.push({ command, parameters, intent: options?.intent, job });
          return job;
        };
        const hooks = {
          executeCommand: recordingExecute,
          isAvailable: () => env.available,
          isExecutionBusy: () => env.executionBusy,
          contextKey: () => env.contextKey,
          selectedCommand: () => commands.find((command) => command.id === env.selectedId),
        };
        const buildEditor = () => new globalThis.saveExportApi.SaveExportEditor(
          new FakeNode(), catalog, hooks,
        );
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_actions_follow_global_execution_admission_and_recover() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.selectedId = "save-image-format";
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        const entry = editor.entries.find((item) => item.id === "save-image-format");
        const saveEntry = editor.entries.find((item) => item.id === "save-image");

        env.executionBusy = true;
        editor.applyBusyState();
        assert.equal(editor.refreshButton.disabled, true);
        assert.equal(entry.button.disabled, true);
        assert.equal(saveEntry.button.disabled, true);
        await editor.submit(entry);
        await editor.submit(saveEntry);
        assert.deepEqual(submitted, []);

        env.executionBusy = false;
        editor.applyBusyState();
        assert.equal(entry.button.disabled, false);
        await editor.submit(entry);
        await settle();
        assert.equal(submitted[0].command, "save-image-format");
        assert.equal(submitted[0].intent, "apply");
        assert.equal(submitted.slice(1).some((item) => item.intent === "readback"), true);
        ''')
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


def run_node(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SAVE_EXPORT_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_always_shows_and_refreshes_the_complete_workspace() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        assert.deepEqual(submitted, []);
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "save-pwd", "save-filename",
          "save-image-format", "save-image-palette", "save-image-ink-saver",
          "save-image-factors", "save-image",
          "save-waveform-format", "save-waveform-length",
          "save-waveform-length-max", "save-waveform",
        ]);

        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd", "save-filename",
          "save-image-format", "save-image-palette", "save-image-ink-saver",
          "save-image-factors", "save-waveform-format", "save-waveform-length",
          "save-waveform-length-max",
        ]);
        assert.ok(submitted.every((entry) => entry.intent === "readback"));
        assert.ok(editor.entries.filter((entry) => entry.kind === "setting").every(
          (entry) => entry.form.syncCalls.at(-1)[1] === true,
        ));
        assert.equal(editor.readStatus.textContent, "loaded:workspace");

        submitted.length = 0;
        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd", "save-filename",
          "save-image-format", "save-image-palette", "save-image-ink-saver",
          "save-image-factors", "save-waveform-format", "save-waveform-length",
          "save-waveform-length-max",
        ]);

        submitted.length = 0;
        env.selectedId = "save-image";
        editor.schedulePresentation();
        await settle();
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "save-pwd", "save-filename",
          "save-image-format", "save-image-palette", "save-image-ink-saver",
          "save-image-factors", "save-image",
          "save-waveform-format", "save-waveform-length",
          "save-waveform-length-max", "save-waveform",
        ]);
        assert.deepEqual(submitted, []);

        submitted.length = 0;
        env.selectedId = "save-waveform";
        editor.schedulePresentation();
        await settle();
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "save-pwd", "save-filename",
          "save-image-format", "save-image-palette", "save-image-ink-saver",
          "save-image-factors", "save-image",
          "save-waveform-format", "save-waveform-length",
          "save-waveform-length-max", "save-waveform",
        ]);
        assert.deepEqual(submitted, []);
        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd", "save-filename",
          "save-image-format", "save-image-palette", "save-image-ink-saver",
          "save-image-factors", "save-waveform-format", "save-waveform-length",
          "save-waveform-length-max",
        ]);
        const maximum = editor.entries.find((entry) => entry.id === "save-waveform-length-max");
        assert.equal(maximum.kind, "readonly");
        assert.equal(maximum.button, undefined);
        assert.equal(maximum.output.textContent, "status.enabled");
        assert.equal(editor.readStatus.textContent, "loaded:workspace");

        submitted.length = 0;
        env.contextKey = "ctx-2";
        editor.schedulePresentation();
        await settle();
        assert.deepEqual(submitted, []);
        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd", "save-filename",
          "save-image-format", "save-image-palette", "save-image-ink-saver",
          "save-image-factors", "save-waveform-format", "save-waveform-length",
          "save-waveform-length-max",
        ]);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_reports_sequential_readback_progress_without_recursion() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.selectedId = "save-image-format";
        const editor = buildEditor();
        const pending = [];
        hooks.executeCommand = (command, parameters, options) => {
          submitted.push({ command, parameters, intent: options?.intent });
          editor.scheduleRefresh();
          return new Promise((resolve) => pending.push({ command, resolve }));
        };

        editor.scheduleRefresh();
        await settle();
        assert.equal(editor.busy, true);
        assert.equal(editor.readStatus.textContent, "reading:workspace:1/9");
        assert.equal(pending.length, 1);
        assert.equal(editor.refreshButton.disabled, true);
        assert.ok(editor.entries.filter((entry) => entry.button).every(
          (entry) => entry.button.disabled,
        ));
        assert.ok(editor.entries.filter((entry) => entry.form).every(
          (entry) => entry.form.disableCalls.at(-1) === true,
        ));

        for (let index = 0; index < 9; index += 1) {
          pending[index].resolve({
            job_id: `read-${index}`,
            status: "completed",
            result: {
              result: pending[index].command === "save-waveform-length-max"
                ? { enabled: true }
                : {},
            },
          });
          await settle();
          if (index < 8) {
            assert.equal(editor.readStatus.textContent, `reading:workspace:${index + 2}/9`);
          }
        }
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd", "save-filename",
          "save-image-format", "save-image-palette", "save-image-ink-saver",
          "save-image-factors", "save-waveform-format", "save-waveform-length",
          "save-waveform-length-max",
        ]);
        assert.equal(editor.readStatus.textContent, "loaded:workspace");
        assert.equal(editor.busy, false);
        assert.equal(editor.refreshButton.disabled, false);
        assert.equal(editor.pendingRefresh, false);
        assert.ok(editor.entries.filter((entry) => entry.button).every(
          (entry) => !entry.button.disabled,
        ));
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_editor_surfaces_partial_failure_and_allows_retry_and_apply() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.selectedId = "save-image-format";
        let paletteFailures = 1;
        hooks.executeCommand = async (command, parameters, options) => {
          submitted.push({ command, parameters, intent: options?.intent });
          if (
            options?.intent === "readback"
            && command === "save-image-palette"
            && paletteFailures > 0
          ) {
            paletteFailures -= 1;
            return null;
          }
          return {
            job_id: `${command}-${submitted.length}`,
            status: "completed",
            result: {
              result: command === "save-waveform-length-max" ? { enabled: true } : {},
            },
          };
        };
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();

        const palette = editor.entries.find((entry) => entry.id === "save-image-palette");
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd", "save-filename",
          "save-image-format", "save-image-palette", "save-image-ink-saver",
          "save-image-factors", "save-waveform-format", "save-waveform-length",
          "save-waveform-length-max",
        ]);
        assert.equal(palette.readError.hidden, false);
        assert.equal(palette.readError.textContent, "current-value-unavailable");
        assert.equal(editor.readStatus.textContent, "failed:workspace:1/9");
        assert.equal(editor.busy, false);
        assert.equal(palette.button.disabled, false);

        submitted.length = 0;
        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "save-pwd", "save-filename",
          "save-image-format", "save-image-palette", "save-image-ink-saver",
          "save-image-factors", "save-waveform-format", "save-waveform-length",
          "save-waveform-length-max",
        ]);
        assert.equal(submitted.some((entry) => entry.command === "save-image"), false);
        assert.equal(palette.readError.hidden, true);
        assert.equal(editor.readStatus.textContent, "loaded:workspace");
        assert.ok(editor.entries.filter((entry) => entry.kind === "setting").every(
          (entry) => entry.form.syncCalls.at(-1)[1] === true,
        ));

        paletteFailures = 1;
        editor.refreshButton.dispatch("click");
        await settle();
        assert.equal(palette.readError.hidden, false);
        palette.form.valuesResult = { action: "set", palette: "grayscale" };
        submitted.length = 0;
        palette.button.dispatch("click");
        await settle();
        assert.equal(submitted[0].command, "save-image-palette");
        assert.equal(submitted[0].intent, "apply");
        assert.deepEqual(submitted[0].parameters, {
          action: "set", palette: "grayscale",
        });
        assert.equal(palette.form.clearedDirty, 1);
        assert.equal(palette.readError.hidden, true);
        assert.equal(editor.readStatus.textContent, "loaded:image");
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_setting_apply_is_independent_and_reconciles_the_group() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.selectedId = "save-image-format";
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        submitted.length = 0;

        const formatEntry = editor.entries.find((entry) => entry.id === "save-image-format");
        const paletteEntry = editor.entries.find((entry) => entry.id === "save-image-palette");
        const paletteSyncCount = paletteEntry.form.syncCalls.length;
        formatEntry.form.valuesResult = { action: "set", format: "png" };
        formatEntry.button.dispatch("click");
        await settle();

        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.intent}`), [
          "save-image-format:apply",
          "save-image-format:readback",
          "save-image-palette:readback",
          "save-image-ink-saver:readback",
          "save-image-factors:readback",
        ]);
        assert.deepEqual(submitted[0].parameters, { action: "set", format: "png" });
        assert.equal(formatEntry.form.clearedDirty, 1);
        assert.deepEqual(formatEntry.form.syncCalls.slice(-2).map((call) => call[1]), [
          false, true,
        ]);
        assert.equal(paletteEntry.form.syncCalls.length, paletteSyncCount + 1);
        assert.equal(paletteEntry.form.syncCalls.at(-1)[1], true);
        assert.equal(submitted.some((entry) => entry.command === "save-image"), false);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_actions_submit_once_without_group_refresh_and_busy_gates_controls() -> None:
    script = textwrap.dedent(SAVE_EXPORT_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.selectedId = "save-image";
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        const imageEntry = editor.entries.find((entry) => entry.id === "save-image");
        imageEntry.form.valuesResult = { filename: "scope-screen" };

        submitted.length = 0;
        let releaseSave;
        hooks.executeCommand = (command, parameters, options) => new Promise((resolve) => {
          submitted.push({ command, parameters, intent: options?.intent });
          releaseSave = () => resolve({ job_id: "saved", status: "completed", result: {} });
        });
        imageEntry.button.dispatch("click");
        await settle();
        assert.equal(editor.busy, true);
        assert.equal(editor.refreshButton.disabled, true);
        assert.ok(editor.entries.filter((entry) => entry.button).every((entry) => entry.button.disabled));
        assert.ok(editor.entries.filter((entry) => entry.form).every(
          (entry) => entry.form.disableCalls.at(-1) === true,
        ));
        releaseSave();
        await settle();
        assert.deepEqual(submitted, [{
          command: "save-image",
          parameters: { filename: "scope-screen" },
          intent: "command",
        }]);
        assert.equal(imageEntry.form.clearedDirty, 0);
        assert.equal(editor.pendingRefresh, false);

        hooks.executeCommand = recordingExecute;
        env.selectedId = "save-waveform";
        editor.scheduleRefresh();
        await settle();
        const waveformEntry = editor.entries.find((entry) => entry.id === "save-waveform");
        waveformEntry.form.valuesResult = { filename: "wave-data" };
        submitted.length = 0;
        waveformEntry.button.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => ({
          command: entry.command, parameters: entry.parameters, intent: entry.intent,
        })), [{
          command: "save-waveform",
          parameters: { filename: "wave-data" },
          intent: "command",
        }]);
        assert.equal(submitted.some((entry) => entry.command === "save-filename"), false);
        assert.equal(editor.pendingRefresh, false);
        '''
    )
    completed = run_node(script)
    assert completed.returncode == 0, completed.stderr or completed.stdout
