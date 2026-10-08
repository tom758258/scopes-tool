from __future__ import annotations

import re
import shutil
import subprocess
import textwrap

import pytest

from tests.webui._frontend_state_test_support import (
    STATIC_ROOT,
    NUMERIC_INPUT_PATH,
    read_static,
    extract_function,
    extract_function_declaration,
)

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_editor_routing_is_callable_before_editor_bootstrap_completes() -> None:
    app_source = read_static("app.js")
    bootstrap_source = read_static("editor-bootstrap.js")

    # initialize() awaits health and command loading before it builds the editors, so the
    # document-level localechange handler can run while routing is not wired up yet.
    declaration = re.search(r"^let editorKindFor(?: = (.+))?;$", app_source, re.M)
    assert declaration, "app.js must declare a module-level editorKindFor binding"
    fallback = declaration.group(1) or "undefined"
    renderer_map = (
        "{"
        + bootstrap_source.split("const editorRenderers = {", 1)[1].split("};", 1)[0]
        + "}"
    )
    routing_body = extract_function(bootstrap_source, "function editorKindFor(command)")

    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";

        const editorRenderers = RENDERER_MAP;

        function bootstrappedEditorKindFor(command) ROUTING_BODY

        let editorKindFor = FALLBACK;

        assert.equal(typeof editorKindFor, "function", "routing must be callable before bootstrap");
        assert.equal(editorKindFor(), null);
        assert.equal(editorKindFor(undefined), null);
        assert.equal(editorKindFor(null), null);
        assert.equal(editorKindFor({}), null);
        assert.equal(editorKindFor({ editor: "not-a-editor" }), null);
        assert.equal(editorKindFor({ editor: "trigger" }), null);

        editorKindFor = bootstrappedEditorKindFor;

        assert.equal(editorKindFor({ editor: "trigger" }), "trigger");
        assert.equal(editorKindFor({ editor: "serial-lister" }), "serial-lister");
        assert.equal(editorKindFor({ editor: "not-a-editor" }), null);
        assert.equal(editorKindFor(), null);
        '''
    ).replace("FALLBACK", fallback).replace("RENDERER_MAP", renderer_map).replace(
        "ROUTING_BODY", routing_body
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    # The fallback must not permanently shadow the real routing after bootstrap.
    assert "editorKindFor = editors.editorKindFor;" in app_source

def test_channel_display_editor_uses_workflow_editor_layout() -> None:
    html = read_static("index.html")
    assert (
        'id="channel-display-editor" '
        'class="channel-display-editor workflow-editor" hidden'
    ) in html

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_diagnostics_editor_defaults_and_submits_selected_mode() -> None:
    editor_path = STATIC_ROOT / "diagnostics-editor.js"
    bootstrap_source = read_static("editor-bootstrap.js")
    html = read_static("index.html")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    assert 'import { DiagnosticsEditor } from "/static/diagnostics-editor.js";' in bootstrap_source
    assert 'id="diagnostics-editor" class="diagnostics-editor" hidden' in html
    assert '"diagnostics.saveArtifacts": "Save diagnostic artifacts"' in english
    assert '"diagnostics.saveArtifacts": "儲存診斷檔案"' in chinese

    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.value = "";
            this.checked = false;
            this.className = "";
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) { this.children.push(...nodes); }
          setAttribute() {}
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.Option = function Option(text, value) {
          return { textContent: text, value: String(value) };
        };
        globalThis.translate = (key) => key;
        globalThis.hasTranslation = () => false;

        const doctorSnapshot = {
          backend: "system_visa",
          timeout_ms: 2000,
          acquisition: { type: "normal", count: 16 },
          channels: [
            { channel: 1, display: true, scale_volts_per_division: 2.0 },
            { channel: 2, display: false, scale_volts_per_division: 1.0 },
          ],
          timebase: { scale_seconds_per_division: 0.001, position_seconds: 0.0 },
          edge_trigger: { source_channel: 1, level_volts: 1.0, slope: "positive" },
        };
        const smokeSnapshot = {
          status: "completed",
          doctor: doctorSnapshot,
          measurements: [
            { command: ":MEASure:VPP? CHANnel1", item: "vpp", channel: 1, value: 2.0, unit: "V", valid: true },
          ],
          capture: { actual_points: 1000 },
          screenshot: { byte_count: 1234 },
          warnings: [],
          error: null,
        };
        let failMode = null;
        const doctorPayload = (extra = {}) => ({
          exit_code: 0,
          result: doctorSnapshot,
          system_error: { code: 0, message: "No error", raw: "0", is_error: false },
          ...extra,
        });

        const stripModule = (text) => text
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "");
        const resultsSource = stripModule(fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/results.js"), "utf8"));
        const editorSource = stripModule(fs.readFileSync(process.argv[1], "utf8"));
        const source = resultsSource + "\n" + editorSource
          + "\nglobalThis.diagnosticsApi = { DiagnosticsEditor };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { DiagnosticsEditor } = globalThis.diagnosticsApi;
        const container = new FakeNode();
        const headerActions = new FakeNode();
        const submitted = [];
        const selected = { id: "diagnostics", editor: "diagnostics" };
        let contextKey = "simulate|";
        const editor = new DiagnosticsEditor(container, {}, {
          headerActions,
          selectedCommand: () => selected,
          contextKey: () => contextKey,
          isExecutionBusy: () => false,
          isAvailable: () => true,
          executeCommand: async (command, parameters) => {
            submitted.push({ command, parameters });
            if (failMode) {
              const mode = failMode;
              failMode = null;
              if (mode === "noresult") {
                return { status: "failed", command, result: null, error: "boom-no-result", artifacts: [] };
              }
              if (mode === "cancelled-partial") {
                return {
                  status: "cancelled",
                  command,
                  result: {
                    exit_code: 1,
                    result: {
                      status: "error",
                      error: "Smoke measurement query timed out",
                      doctor: doctorSnapshot,
                      measurements: [],
                      capture: null,
                      screenshot: null,
                    },
                    system_error: null,
                  },
                  error: null,
                  artifacts: [],
                };
              }
              return {
                status: "failed",
                command,
                result: {
                  exit_code: 1,
                  result: {
                    status: "error",
                    error: "Smoke measurement query timed out",
                    doctor: doctorSnapshot,
                    measurements: [],
                  },
                  system_error: null,
                },
                error: "Core command returned a non-zero exit code.",
                artifacts: [],
              };
            }
            const payload = command === "smoke"
              ? {
                exit_code: 0,
                result: smokeSnapshot,
                system_error: { code: 0, message: "No error", raw: "0", is_error: false },
              }
              : doctorPayload();
            return { status: "completed", command, result: payload, error: null, artifacts: [] };
          },
        });
        const panelText = () => {
          const texts = [];
          const visit = (node) => {
            if (typeof node.textContent === "string" && node.textContent) texts.push(node.textContent);
            for (const child of node.children || []) visit(child);
          };
          visit(editor.resultPanel);
          return texts.join(" ");
        };

        editor.present();
        assert.equal(headerActions.children.length, 1);
        assert.equal(editor.modeSelect.value, "doctor");
        assert.equal(editor.saveArtifactsInput.checked, false);
        assert.equal(editor.saveArtifactsField.hidden, true);
        await editor.submit();
        assert.deepEqual(submitted[0], { command: "doctor", parameters: {} });

        editor.modeSelect.value = "smoke";
        editor.modeSelect.dispatch("change");
        assert.equal(editor.saveArtifactsField.hidden, false);
        await editor.submit();
        assert.deepEqual(submitted[1], { command: "smoke", parameters: { save_artifacts: false } });

        editor.saveArtifactsInput.checked = true;
        editor.saveArtifactsInput.dispatch("change");
        await editor.submit();
        assert.deepEqual(submitted[2], { command: "smoke", parameters: { save_artifacts: true } });

        selected.editor = "other";
        editor.present();
        selected.editor = "diagnostics";
        editor.present();
        assert.equal(editor.modeSelect.value, "smoke");
        assert.equal(editor.saveArtifactsInput.checked, true);

        contextKey = "live|RESOURCE|MODEL";
        editor.present();
        assert.equal(editor.modeSelect.value, "doctor");
        assert.equal(editor.saveArtifactsInput.checked, false);
        assert.equal(editor.saveArtifactsField.hidden, true);

        await editor.submit();
        assert.ok(panelText().includes("normal"));
        assert.ok(panelText().includes("Channel 1"));

        editor.modeSelect.value = "smoke";
        editor.modeSelect.dispatch("change");
        assert.equal(panelText(), "");
        await editor.submit();
        assert.ok(panelText().includes("vpp"));
        assert.ok(panelText().includes("Channel 1"));

        editor.modeSelect.value = "doctor";
        editor.modeSelect.dispatch("change");
        assert.ok(panelText().includes("Channel 1"));

        failMode = "partial";
        editor.modeSelect.value = "smoke";
        editor.modeSelect.dispatch("change");
        await editor.submit();
        assert.ok(panelText().includes("Smoke measurement query timed out"));
        assert.ok(panelText().includes("Channel 1"));

        failMode = "noresult";
        await editor.submit();
        assert.ok(panelText().includes("boom-no-result"));

        failMode = "cancelled-partial";
        await editor.submit();
        const cancelledText = panelText();
        assert.ok(cancelledText.includes("Smoke measurement query timed out"));
        assert.equal(cancelledText.split("Smoke measurement query timed out").length - 1, 1);

        contextKey = "simulate|OTHER";
        editor.present();
        assert.equal(panelText(), "");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(editor_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_fft_frequency_readback_dirty_only_submission() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.testTranslate = (key) => key;
        globalThis.testHasTranslation = () => false;
        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          fs.readFileSync(process.argv[2], "utf8"),
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export function /gm, "function ")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.formApi = { CommandForm };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const makeField = (name, type, value) => ({
          value: value ?? "",
          type: type === "boolean" ? "checkbox" : "text",
          checked: false,
          dataset: { field: name, type },
          validity: { badInput: false },
          closest: () => null,
          setCustomValidity() {},
          checkValidity() { return true; },
          reportValidity() {},
        });

        const action = makeField("action", "enum", "set");
        action.type = "hidden";
        const func = makeField("function", "integer", "1");
        const sourceChannel = makeField("source_channel", "integer", "1");
        const center = makeField("center_hz", "number", "1000000");
        const span = makeField("span_hz", "number", "100000");
        const start = makeField("start_hz", "number", "500000");
        const stop = makeField("stop_hz", "number", "1500000");
        const gate = makeField("gate", "enum", "none");

        const fields = [action, func, sourceChannel, center, span, start, stop, gate];
        const container = {
          querySelectorAll(selector) {
            if (selector === "[data-field]") return fields;
            if (selector === "[data-visible-if]") return [];
            if (selector === "[data-help-by-value]") return [];
            return [];
          },
          querySelector(selector) {
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return fields.find((f) => f.dataset.field === match?.[1]) ?? null;
          },
          replaceChildren() {},
        };

        const form = new globalThis.formApi.CommandForm(container, { optionsFor: () => [] });
        form.command = { id: "fft" };
        form.presentation = { kind: "setting", action_field: "action", apply_value: "set", query_value: "query" };

        // Readback state: four frequency fields have values but are pristine
        // Only gate is dirty (user edited unrelated field)
        gate.dataset.dirty = "true";
        let values = form.values();
        assert.deepEqual(values, { action: "set", function: 1, source_channel: 1, gate: "none" });
        assert.equal("center_hz" in values, false);
        assert.equal("span_hz" in values, false);
        assert.equal("start_hz" in values, false);
        assert.equal("stop_hz" in values, false);

        // Center dirty only -> should send only center
        delete gate.dataset.dirty;
        center.dataset.dirty = "true";
        values = form.values();
        assert.equal(values.center_hz, 1000000);
        assert.equal("span_hz" in values, false);
        assert.equal("start_hz" in values, false);
        assert.equal("stop_hz" in values, false);

        // Start+Stop dirty -> should send both, no center/span
        delete center.dataset.dirty;
        start.dataset.dirty = "true";
        stop.dataset.dirty = "true";
        values = form.values();
        assert.equal(values.start_hz, 500000);
        assert.equal(values.stop_hz, 1500000);
        assert.equal("center_hz" in values, false);
        assert.equal("span_hz" in values, false);

        // User explicitly dirties both ranges -> both sent, Core authoritative validation will reject
        center.dataset.dirty = "true";
        span.dataset.dirty = "true";
        values = form.values();
        assert.equal(values.center_hz, 1000000);
        assert.equal(values.span_hz, 100000);
        assert.equal(values.start_hz, 500000);
        assert.equal(values.stop_hz, 1500000);

        // Non-FFT synthetic command: dirty-only filter must not apply globally
        form.command = { id: "synthetic-setting" };
        delete center.dataset.dirty;
        delete span.dataset.dirty;
        delete start.dataset.dirty;
        delete stop.dataset.dirty;
        values = form.values();
        assert.equal(values.center_hz, 1000000);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(command_form_path), str(NUMERIC_INPUT_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_fft_phase_units_visibility_and_submission() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.testTranslate = (key) => key;
        globalThis.testHasTranslation = () => false;
        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          fs.readFileSync(process.argv[2], "utf8"),
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export function /gm, "function ")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.formApi = { CommandForm };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const makeField = (name, type, value) => ({
          value: value ?? "",
          type: type === "boolean" ? "checkbox" : "text",
          checked: false,
          dataset: { field: name, type },
          validity: { badInput: false },
          closest: () => null,
          setCustomValidity() {},
          checkValidity() { return true; },
          reportValidity() {},
        });

        const action = makeField("action", "enum", "set");
        action.type = "hidden";
        const func = makeField("function", "integer", "1");
        const sourceChannel = makeField("source_channel", "integer", "1");
        const fftOp = makeField("fft_operation", "enum", "fft-phase");
        const units = makeField("units", "string", "vrms");
        const gate = makeField("gate", "enum", "zoom");
        const phaseRef = makeField("phase_reference", "enum", "display");
        const detectionType = makeField("detection_type", "enum", "average");
        const detectionPoints = makeField("detection_points", "integer", "4096");

        // Units hidden when fft-phase
        units.closest = (selector) => {
          if (selector === "[data-visible-if-hidden=\"true\"]" && fftOp.value === "fft-phase") return {};
          return null;
        };

        const fields = [action, func, sourceChannel, fftOp, units, gate, phaseRef, detectionType, detectionPoints];
        const container = {
          querySelectorAll(selector) {
            if (selector === "[data-field]") return fields;
            if (selector === "[data-visible-if]") return [];
            if (selector === "[data-help-by-value]") return [];
            return [];
          },
          querySelector(selector) {
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return fields.find((f) => f.dataset.field === match?.[1]) ?? null;
          },
          replaceChildren() {},
        };

        const form = new globalThis.formApi.CommandForm(container, { optionsFor: () => [] });
        form.command = { id: "fft" };
        form.presentation = { kind: "setting", action_field: "action", apply_value: "set", query_value: "query" };

        // Phase: units hidden -> not submitted, phase controls still submitted
        gate.dataset.dirty = "true";
        phaseRef.dataset.dirty = "true";
        let values = form.values();
        assert.equal("units" in values, false);
        assert.equal(values.phase_reference, "display");
        assert.equal(values.gate, "zoom");

        // Switch to magnitude -> units visible
        fftOp.value = "fft";
        units.value = "vrms";
        values = form.values();
        assert.equal(values.units, "vrms");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(command_form_path), str(NUMERIC_INPUT_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_fft_abbreviated_readback_syncs_canonical_values_for_apply() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.testTranslate = (key) => key;
        globalThis.testHasTranslation = () => false;
        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          fs.readFileSync(process.argv[2], "utf8"),
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export function /gm, "function ")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.formApi = { CommandForm };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const makeField = (name, type, value) => ({
          value: value ?? "",
          type: type === "boolean" ? "checkbox" : "text",
          checked: false,
          dataset: { field: name, type },
          validity: { badInput: false },
          closest: () => null,
          setCustomValidity() {},
          checkValidity() { return true; },
          reportValidity() {},
        });

        const units = makeField("units", "string", "");
        const window = makeField("window", "string", "");
        const fields = [units, window];
        const container = {
          querySelectorAll(selector) {
            if (selector === "[data-field]") return fields;
            if (selector === "[data-visible-if]") return [];
            if (selector === "[data-help-by-value]") return [];
            return [];
          },
          querySelector(selector) {
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return fields.find((f) => f.dataset.field === match?.[1]) ?? null;
          },
          replaceChildren() {},
        };

        const form = new globalThis.formApi.CommandForm(container, { optionsFor: () => [] });
        form.command = { id: "fft" };
        form.presentation = {
          kind: "setting",
          action_field: "action",
          apply_value: "set",
          query_value: "query",
          readback_fields: { units: "units_canonical", window: "window_canonical" },
        };

        // Core already canonicalized the SCPI tokens; the form only follows the alias.
        form.syncResult({ result: { result: {
          units: "DEC",
          units_canonical: "decibel",
          window: "HANN",
          window_canonical: "hanning",
        } } }, true);
        assert.equal(units.value, "decibel");
        assert.equal(window.value, "hanning");
        assert.deepEqual(form.values(), { units: "decibel", window: "hanning" });
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(command_form_path), str(NUMERIC_INPUT_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_save_export_refresh_stays_hidden_in_setup_mode_on_header_resync() -> None:
    app_source = read_static("app.js")
    sync_header = extract_function_declaration(app_source, "function syncWorkspaceHeaderActions(editorKind)")
    script = textwrap.dedent(
        f'''
        import assert from "node:assert/strict";
        let selectedId = "setup-save";
        const presentations = {{
          "external-trigger-settings": {{ kind: "command", action: "read" }},
          "trigger-edge-slope": {{ kind: "setting", action: "apply" }},
        }};
        const catalog = {{
          selected: () => ({{ id: selectedId, presentation: presentations[selectedId] }}),
        }};
        const elements = {{
          refresh: {{ hidden: false }},
          execute: {{ hidden: false }},
        }};
        const commandForm = null;
            const referenceEditor = {{}};
            const referenceDisplayEditor = {{ refreshButton: {{}}, runButton: {{}} }};
            const referenceLabelsEditor = {{}};
        const saveExportEditor = {{
          mode: "setup",
          refreshButton: {{ hidden: false }},
        }};
        const selectSaveCommand = (id) => {{
          selectedId = id;
          if (id === "save-waveform") saveExportEditor.mode = "waveform";
          else if (id === "setup-save") saveExportEditor.mode = "setup";
          else if (id === "save-image") saveExportEditor.mode = "image";
        }};
        const serialDecodeEditor = {{}};
        const serialTriggerEditor = {{}};
        const serialListerEditor = {{}};
        const triggerEditor = {{ refreshButton: {{}}, entry: {{ button: {{}} }} }};
        const searchEditor = {{}};
        const segmentedEditor = {{}};
        const workflowEditor = {{}};
        const sequenceEditor = {{}};
        const cursorEditor = {{ refreshButton: {{}}, entry: {{ button: {{}} }} }};
        const annotationEditor = {{ refreshButton: {{}}, entry: {{ button: {{}} }} }};
        const wgenEditor = {{ refreshButton: {{}}, entry: {{ button: {{}} }} }};
        const demoEditor = {{ refreshButton: {{}}, entry: {{ button: {{}} }} }};
        const channelDisplayEditor = {{}};
        const channelScaleRangeEditor = {{}};
        const externalTriggerEditor = {{ readButton: {{}}, applyButton: {{}} }};
        const timebasePositionEditor = {{ readButton: {{}}, applyButton: {{}} }};
        const channelOffsetEditor = {{ readButton: {{}}, applyButton: {{}} }};
        const translate = (key) => key;
        {sync_header}

            const actionPairs = [
              ["timebase-position", timebasePositionEditor.readButton, timebasePositionEditor.applyButton],
              ["channel-offset", channelOffsetEditor.readButton, channelOffsetEditor.applyButton],
              ["external-trigger", externalTriggerEditor.readButton, externalTriggerEditor.applyButton],
          ["cursor", cursorEditor.refreshButton, cursorEditor.entry.button],
          ["annotation", annotationEditor.refreshButton, annotationEditor.entry.button],
        ];
        for (const kind of [...actionPairs.map(([kind]) => kind), "save-export"]) {{
          syncWorkspaceHeaderActions(kind);
          for (const [owner, read, apply] of actionPairs) {{
            assert.equal(read.hidden, owner !== kind);
            assert.equal(apply.hidden, owner !== kind);
          }}
        }}

        syncWorkspaceHeaderActions("save-export");
        assert.equal(saveExportEditor.refreshButton.hidden, true);
        selectSaveCommand("save-image");
        syncWorkspaceHeaderActions("save-export");
        assert.equal(saveExportEditor.refreshButton.hidden, false);
        selectSaveCommand("setup-save");
        syncWorkspaceHeaderActions("save-export");
        syncWorkspaceHeaderActions("serial");
        syncWorkspaceHeaderActions("save-export");
        assert.equal(saveExportEditor.refreshButton.hidden, true);

        selectedId = "cursor-query";
        syncWorkspaceHeaderActions("cursor");
        assert.equal(cursorEditor.refreshButton.hidden, false);
        assert.equal(cursorEditor.entry.button.hidden, true);
        syncWorkspaceHeaderActions("cursor");
        assert.equal(cursorEditor.entry.button.hidden, true);

        selectedId = "cursor-set";
        syncWorkspaceHeaderActions("cursor");
        assert.equal(cursorEditor.refreshButton.hidden, false);
        assert.equal(cursorEditor.entry.button.hidden, false);

        selectedId = "cursor-off";
        syncWorkspaceHeaderActions("cursor");
        assert.equal(cursorEditor.refreshButton.hidden, false);
        assert.equal(cursorEditor.entry.button.hidden, false);

        selectedId = "annotation-query";
        syncWorkspaceHeaderActions("annotation");
        assert.equal(annotationEditor.refreshButton.hidden, false);
        assert.equal(annotationEditor.entry.button.hidden, true);
        syncWorkspaceHeaderActions("annotation");
        assert.equal(annotationEditor.entry.button.hidden, true);

        for (const id of ["annotation-set", "annotation-on", "annotation-off", "annotation-clear"]) {{
          selectedId = id;
          syncWorkspaceHeaderActions("annotation");
          assert.equal(annotationEditor.refreshButton.hidden, false);
          assert.equal(annotationEditor.entry.button.hidden, false);
        }}

        selectedId = "wgen-query";
        syncWorkspaceHeaderActions("wgen");
        assert.equal(wgenEditor.refreshButton.hidden, false);
        assert.equal(wgenEditor.entry.button.hidden, true);

        selectedId = "wgen-frequency";
        syncWorkspaceHeaderActions("wgen");
        assert.equal(wgenEditor.refreshButton.hidden, false);
        assert.equal(wgenEditor.entry.button.hidden, false);

        selectedId = "demo-query";
        syncWorkspaceHeaderActions("demo");
        assert.equal(demoEditor.refreshButton.hidden, false);
        assert.equal(demoEditor.entry.button.hidden, true);

        selectedId = "demo-function";
        syncWorkspaceHeaderActions("demo");
        assert.equal(demoEditor.refreshButton.hidden, false);
        assert.equal(demoEditor.entry.button.hidden, false);

        selectedId = "external-trigger-settings";
        syncWorkspaceHeaderActions("trigger");
        assert.equal(triggerEditor.refreshButton.hidden, false);
        assert.equal(triggerEditor.entry.button.hidden, true);

        selectedId = "trigger-edge-slope";
        syncWorkspaceHeaderActions("trigger");
        assert.equal(triggerEditor.refreshButton.hidden, false);
        assert.equal(triggerEditor.entry.button.hidden, false);

        syncWorkspaceHeaderActions("serial");
        assert.equal(triggerEditor.refreshButton.hidden, true);
        assert.equal(triggerEditor.entry.button.hidden, true);

        syncWorkspaceHeaderActions("serial");
        assert.equal(annotationEditor.refreshButton.hidden, true);
        assert.equal(annotationEditor.entry.button.hidden, true);

        syncWorkspaceHeaderActions("serial");
        assert.equal(cursorEditor.refreshButton.hidden, true);
        assert.equal(cursorEditor.entry.button.hidden, true);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
