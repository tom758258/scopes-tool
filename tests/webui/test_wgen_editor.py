from __future__ import annotations

import dataclasses
import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.wgen import WGEN_FUNCTIONS, WGEN_LOADS, wgen_frequency_limits
import scopes_tool_webui.command_execution as command_execution_module
import scopes_tool_webui.commands as commands_module
from scopes_tool_webui.command_catalog import _command_supported_by_capabilities
from scopes_tool_webui.command_validation import WebUIRequestError, validate_job_request


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
MODEL_ID = "keysight-dsox4024a"

WGEN_COMMAND_IDS = [
    "wgen-query",
    "wgen-output",
    "wgen-function",
    "wgen-frequency",
    "wgen-voltage",
    "wgen-offset",
    "wgen-load",
]


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_wgen_command_family_routes_to_one_editor() -> None:
    entries = [entry for entry in commands_module.COMMANDS if entry["id"] in WGEN_COMMAND_IDS]

    assert [entry["id"] for entry in entries] == WGEN_COMMAND_IDS
    for entry in entries:
        assert entry["category"] == "WGEN", entry["id"]
        assert "group" not in entry, entry["id"]
        assert entry["editor"] == "wgen", entry["id"]
        assert entry.get("browser_hidden") is not True, entry["id"]
        assert entry.get("hidden") is not True, entry["id"]


def test_wgen_options_come_from_core_constants() -> None:
    entries = {entry["id"]: entry for entry in commands_module.COMMANDS}

    function = next(
        field for field in entries["wgen-function"]["fields"] if field["name"] == "function"
    )
    load = next(
        field for field in entries["wgen-load"]["fields"] if field["name"] == "load"
    )

    assert tuple(function["options"]) == WGEN_FUNCTIONS
    assert tuple(load["options"]) == WGEN_LOADS


def test_wgen_frequency_model_presentation_projects_core_limits() -> None:
    catalog = {entry["id"]: entry for entry in commands_module.command_catalog()}
    models = catalog["wgen-frequency"]["presentation"]["models"]

    projected = models["keysight-dsox4024a"]["fields"]["frequency_hz"]["frequency_limits"]
    assert projected == wgen_frequency_limits("4000X")
    assert projected["sine"] == {
        "min_hz": 0.1,
        "max_hz": 20.0e6,
        "min_label": "100 mHz",
        "max_label": "20 MHz",
    }
    older = models["keysight-dsox2004a"]["fields"]["frequency_hz"]["frequency_limits"]
    assert older == wgen_frequency_limits("2000X")
    assert older["ramp"]["max_hz"] == 100.0e3
    assert "noise" not in projected
    assert "dc" not in projected


def test_wgen_commands_follow_model_support_flag() -> None:
    entries = {entry["id"]: entry for entry in commands_module.COMMANDS}
    supported = capabilities_for_model_id(MODEL_ID)
    unsupported = dataclasses.replace(supported, supports_wgen=False)

    for command_id in WGEN_COMMAND_IDS:
        assert _command_supported_by_capabilities(entries[command_id], supported) is True
        assert _command_supported_by_capabilities(entries[command_id], unsupported) is False


def test_wgen_set_validation_uses_core_rules() -> None:
    request = validate_job_request({
        "command": "wgen-frequency",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {"action": "set", "frequency_hz": 1000.0},
    })

    assert request["parameters"]["frequency_hz"] == 1000.0
    with pytest.raises(WebUIRequestError, match="frequency"):
        validate_job_request({
            "command": "wgen-frequency",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "set", "frequency_hz": 30.0e6},
        })
    with pytest.raises(WebUIRequestError, match="frequency"):
        validate_job_request({
            "command": "wgen-frequency",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "set"},
        })
    with pytest.raises(WebUIRequestError, match="function"):
        validate_job_request({
            "command": "wgen-function",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "set", "function": "triangle"},
        })


def test_wgen_frequency_set_does_not_touch_output(tmp_path: Path) -> None:
    calls: list[tuple] = []

    class FakeScope:
        capabilities = object()

        def configure_wgen_output(self, enabled):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_output", enabled))

        def query_wgen_output(self):  # type: ignore[no-untyped-def]
            return {"enabled": False, "output_raw": "0"}

        def configure_wgen_function(self, function):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_function", function))

        def query_wgen_function(self):  # type: ignore[no-untyped-def]
            return {"function": "sine", "function_scpi": "SINusoid", "function_raw": "SIN"}

        def configure_wgen_frequency(self, frequency_hz):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_frequency", frequency_hz))

        def query_wgen_frequency(self):  # type: ignore[no-untyped-def]
            calls.append(("query_wgen_frequency",))
            return {"frequency_hz": 1000.0, "frequency_raw": "1.0E+3"}

        def configure_wgen_voltage(self, amplitude_volts):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_voltage", amplitude_volts))

        def query_wgen_voltage(self):  # type: ignore[no-untyped-def]
            return {"amplitude_volts": 1.0, "voltage_raw": "1.0E+0"}

        def configure_wgen_offset(self, offset_volts):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_offset", offset_volts))

        def query_wgen_offset(self):  # type: ignore[no-untyped-def]
            return {"offset_volts": 0.0, "offset_raw": "0.0E+0"}

        def configure_wgen_load(self, load):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_load", load))

        def query_wgen_load(self):  # type: ignore[no-untyped-def]
            return {"load": "fifty", "load_scpi": "FIFTy", "load_raw": "FIFT"}

        def query_wgen(self):  # type: ignore[no-untyped-def]
            return {
                "enabled": False,
                "output_raw": "0",
                "function": "sine",
                "function_scpi": "SINusoid",
                "function_raw": "SIN",
                "frequency_hz": 1000.0,
                "frequency_raw": "1.0E+3",
                "amplitude_volts": 1.0,
                "voltage_raw": "1.0E+0",
                "offset_volts": 0.0,
                "offset_raw": "0.0E+0",
                "load": "fifty",
                "load_scpi": "FIFTy",
                "load_raw": "FIFT",
            }

    scope = FakeScope()
    result = command_execution_module._execute_scope_command(
        scope,
        "wgen-frequency",
        "SIM::INSTR",
        {"action": "set", "frequency_hz": 1000.0},
        tmp_path,
    )

    assert ("configure_wgen_frequency", 1000.0) in calls
    assert all(name != "configure_wgen_output" for name, *_ in calls)
    assert result["result"]["frequency"]["frequency_hz"] == 1000.0

    aggregate = command_execution_module._execute_scope_command(
        scope, "wgen-query", "SIM::INSTR", {}, tmp_path
    )

    assert aggregate["result"]["wgen"]["load"] == "fifty"
    assert aggregate["result"]["wgen"]["enabled"] is False


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_wgen_editor_aggregate_refresh_and_setter(tmp_path: Path) -> None:
    catalog_json = json.dumps(commands_module.command_catalog())
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    app_source = read_static("app.js")
    index_source = read_static("index.html")

    assert "wgen: () => wgenEditor," in app_source
    assert "elements.wgenEditor.hidden = editorKind !== " in app_source
    assert 'if (editorKind === "wgen") wgenEditor?.schedulePresentation();' in app_source
    assert 'wgenEditor.refreshButton.hidden = editorKind !== "wgen";' in app_source
    assert "wgenEditor?.rerender();" in app_source
    # WGEN uses the existing command-specific header path, so each selected
    # WGEN command shows its own label/description.
    assert '["annotation", "cursor", "measurement", "reference-display", "save-export", "wgen", "demo", "trigger", "search", "segmented"].includes(editorKind)' in app_source
    assert '["annotation", "cursor", "measurement", "reference", "reference-display", "save-export", "wgen", "demo", "trigger", "search", "segmented"].includes(editorKind)' in app_source
    assert 'id="wgen-editor"' in index_source
    for key in (
        '"command.wgen-query": "Waveform generator state"',
        '"command.wgen-load": "Generator load"',
        '"description.wgen-query":',
        '"wgen.editor.title": "Waveform generator"',
        '"wgen.editor.description":',
        '"wgen.frequency.rangeWarning": "The allowed frequency range for the current waveform is {{min}} to {{max}}.',
        '"wgen.state.amplitude":',
        '"enum.wgen-function.sine":',
        '"enum.wgen-load.fifty":',
    ):
        assert key in english, key
    for key in (
        '"command.wgen-query": "波形產生器狀態"',
        '"command.wgen-load": "產生器負載"',
        '"description.wgen-query":',
        '"wgen.editor.title": "波形產生器"',
        '"wgen.editor.description":',
        '"wgen.frequency.rangeWarning": "目前波形允許的頻率範圍為 {{min}} ～ {{max}}，',
        '"wgen.state.amplitude":',
        '"enum.wgen-function.sine":',
        '"enum.wgen-load.fifty":',
    ):
        assert key in chinese, key

    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

        class FakeNode {
          constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.hidden = false; this.textContent = ""; this.className = ""; this.disabled = false; }
          append(...nodes) { for (const node of nodes) { node.remove(); node.parent = this; this.children.push(node); } }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          addEventListener(_name, handler) { this.handler = handler; }
          setAttribute() {}
          remove() { if (this.parent) this.parent.children = this.parent.children.filter((node) => node !== this); this.parent = null; }
          querySelector() { return null; }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.queueMicrotask = (fn) => { fn(); };

        globalThis.translate = (key) => key;
        let selectedId = "wgen-query";
        let currentMode = "live";
        let submittedLoad = "one-meg";
        globalThis.CommandForm = class CommandForm {
          constructor(container, _catalog) { this.container = container; this.command = null; this.disabled = false; }
          render(command) { this.command = command; }
          values() {
            if (selectedId === "wgen-frequency") return { action: "set", frequency_hz: 1000 };
            if (selectedId === "wgen-offset") return { action: "set", offset_volts: 0 };
            if (selectedId === "wgen-load") return { action: "set", load: submittedLoad };
            return {};
          }
          setDisabled(disabled) { this.disabled = disabled; }
          clearDirty() {}
        };

        const calls = [];
        const aggregate = {
          enabled: false, output_raw: "0", function: "sine",
          function_scpi: "SINusoid", function_raw: "SIN",
          frequency_hz: 1000, frequency_raw: "1.0E+3",
          amplitude_volts: 1.0, voltage_raw: "1.0E+0",
          offset_volts: 0.0, offset_raw: "0.0E+0",
          load: "fifty", load_scpi: "FIFTy", load_raw: "FIFT",
        };
        const hooks = {
          calls,
          contextKey: () => `${currentMode}||keysight-dsox4024a`,
          mode: () => currentMode,
          selectedCommand: () => catalog.commands.find((command) => command.id === selectedId),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          headerActions: new FakeNode("div"),
          async executeCommand(id, parameters, _options) {
            calls.push([id, parameters]);
            if (id === "wgen-query") {
              return { status: "completed", result: { result: { wgen: { ...aggregate } } } };
            }
            if (id === "wgen-load") {
              aggregate.load = parameters.load;
              return { status: "completed", result: { result: { load: { load: parameters.load } } } };
            }
            return { status: "completed", result: { result: { frequency: { frequency_hz: 1000 } } } };
          },
        };
        const catalog = {
          commands: __CATALOG__,
          groupLabel: (group) => group,
          commandLabel: (command) => command.id,
          supported: () => true,
        };

        let editorSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/wgen-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class WgenEditor", "class WgenEditor")
          + "\nglobalThis.WgenEditor = WgenEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const editor = new globalThis.WgenEditor(new FakeNode("div"), catalog, hooks);
        await editor.refresh(true, true);
        assert.deepEqual(calls, [["wgen-query", {}]]);
        assert.ok(hooks.headerActions.children.includes(editor.refreshButton));
        assert.ok(hooks.headerActions.children.includes(editor.entry.button));
        assert.equal(editor.entry.form.container.className, "command-form");
        assert.ok(!editor.sectionsHost.children[0].children.includes(editor.entry.button));
        // Only the selected command is rendered; wgen-query has no fields.
        assert.equal(editor.sectionsHost.children.length, 1);
        assert.equal(editor.sectionsHost.children[0].hidden, true);
        assert.equal(editor.entry.form.container.hidden, true);
        // wgen-query reuses the header Read action; no second query button.
        assert.equal(editor.entry.button.hidden, true);

        selectedId = "wgen-frequency";
        const queryButton = editor.entry.button;
        const beforeFrequencyRead = calls.length;
        await editor.refresh(true, true);
        assert.deepEqual(calls.slice(beforeFrequencyRead), [["wgen-query", {}]]);
        // Switching commands rebuilds: one section, no leftover header action.
        assert.equal(editor.sectionsHost.children.length, 1);
        assert.equal(hooks.headerActions.children.length, 2);
        assert.ok(!hooks.headerActions.children.includes(queryButton));
        assert.ok(hooks.headerActions.children.includes(editor.entry.button));
        assert.equal(editor.entry.button.hidden, false);
        assert.equal(editor.entry.button.textContent, "actions.apply");
        assert.ok(editor.entry.button.className.split(" ").includes("primary"));
        assert.equal(editor.sectionsHost.children[0].hidden, false);

        const beforeSubmit = calls.length;
        await editor.submit();
        const setterCalls = calls.slice(beforeSubmit);
        assert.equal(setterCalls.length, 1);
        assert.deepEqual(setterCalls[0], ["wgen-frequency", { action: "set", frequency_hz: 1000 }]);
        assert.ok(!calls.slice(beforeSubmit).some((call) => call[0] === "wgen-output"));
        assert.ok(!calls.slice(beforeSubmit).some((call) => call[0] === "wgen-query"));

        // Numeric 0 is a valid submission and must reach its own command.
        selectedId = "wgen-offset";
        await editor.refresh(true, true);
        const beforeOffset = calls.length;
        await editor.submit();
        const offsetCalls = calls.slice(beforeOffset);
        assert.equal(offsetCalls.length, 1);
        assert.deepEqual(offsetCalls[0], ["wgen-offset", { action: "set", offset_volts: 0 }]);
        assert.ok(!offsetCalls.some((call) => call[0] === "wgen-output"));

        // Live load set is followed by one aggregate refresh; simulate is not.
        selectedId = "wgen-load";
        await editor.refresh(true, true);
        const beforeLoad = calls.length;
        await editor.submit();
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.deepEqual(calls.slice(beforeLoad), [
          ["wgen-load", { action: "set", load: "one-meg" }],
          ["wgen-query", {}],
        ]);

        currentMode = "simulate";
        submittedLoad = "fifty";
        const beforeSimulateLoad = calls.length;
        await editor.submit();
        await new Promise((resolve) => setTimeout(resolve, 0));
        assert.deepEqual(calls.slice(beforeSimulateLoad), [
          ["wgen-load", { action: "set", load: "fifty" }],
        ]);

        // Switching back to wgen-query hides the section button again.
        selectedId = "wgen-query";
        const callsBeforeBack = calls.length;
        await editor.refresh(true, false);
        assert.equal(calls.length, callsBeforeBack);
        assert.equal(editor.entry.button.hidden, true);
        assert.equal(editor.sectionsHost.children.length, 1);

        const headerCount = hooks.headerActions.children.length;
        const oldApply = editor.entry.button;
        const callsBeforeLayout = calls.length;
        editor.rerender();
        assert.equal(hooks.headerActions.children.length, headerCount);
        assert.ok(!hooks.headerActions.children.includes(oldApply));
        assert.ok(hooks.headerActions.children.includes(editor.entry.button));
        const local = new globalThis.WgenEditor(new FakeNode("div"), catalog, {
          ...hooks, headerActions: null,
        });
        await local.refresh(false, false);
        assert.ok(local.sectionsHost.children[0].children.includes(local.entry.button));
        assert.equal(calls.length, callsBeforeLayout);
        editor.clearSections();
        assert.equal(hooks.headerActions.children.length, headerCount - 1);

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)
    harness_path = tmp_path / "wgen-editor-harness.mjs"
    harness_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"ok": True}


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_wgen_frequency_range_warning(tmp_path: Path) -> None:
    catalog_json = json.dumps(commands_module.command_catalog())
    english = read_static("locale_en.js")

    assert '"wgen.frequency.rangeWarning"' in english

    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

        class FakeNode {
          constructor(tag) {
            this.tagName = (tag || "").toUpperCase();
            this.children = [];
            this.options = [];
            this.hidden = false;
            this.textContent = "";
            this.className = "";
            this.disabled = false;
            this.value = "";
            this.checked = false;
            this.multiple = false;
            this.listeners = {};
            this.parent = null;
          }
          append(...nodes) {
            for (const node of nodes) {
              if (!node) continue;
              node.remove();
              node.parent = this;
              this.children.push(node);
              if (node.tagName === "OPTION") this.options.push(node);
            }
          }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatchEvent(event) {
            for (const handler of this.listeners[event.type] || []) handler(event);
            return true;
          }
          setAttribute() {}
          remove() {
            if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this);
            this.parent = null;
          }
          get classList() {
            return { add: (...names) => { this.className = [this.className, ...names].filter(Boolean).join(" "); } };
          }
          querySelector(sel) {
            const match = /^\[data-field="([^"]+)"\]$/.exec(sel || "");
            if (!match) return null;
            const find = (list) => {
              for (const child of list || []) {
                if (child.dataset && child.dataset.field === match[1]) return child;
                const found = find(child.children);
                if (found) return found;
              }
              return null;
            };
            return find(this.children);
          }
          querySelectorAll(sel) {
            const out = [];
            const collect = (list) => {
              for (const child of list || []) {
                if (child.dataset && child.dataset.field) out.push(child);
                collect(child.children);
              }
            };
            collect(this.children);
            if (sel === "[data-field]") return out;
            const match = /^\[data-field="([^"]+)"\]$/.exec(sel || "");
            if (match) return out.filter((child) => child.dataset.field === match[1]);
            return [];
          }
          get closest() { return () => null; }
          get validity() { return { badInput: false }; }
          setCustomValidity() {}
          reportValidity() {}
          checkValidity() { return true; }
          get dataset() { if (!this._dataset) this._dataset = {}; return this._dataset; }
          set dataset(v) { this._dataset = v; }
        }
        globalThis.Option = class {
          constructor(text, value) {
            this.tagName = "OPTION";
            this.textContent = text;
            this.value = value;
            this.selected = false;
            this.children = [];
          }
          remove() {}
        };
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.queueMicrotask = (fn) => { fn(); };

        const localeSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/locale_en.js"), "utf8",
        ).replace("export const en =", "globalThis.en =");
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(localeSource)}`);
        globalThis.translate = (key, values = {}) => {
          let text = (globalThis.en && globalThis.en[key]) || key;
          for (const [name, value] of Object.entries(values || {})) {
            text = text.replaceAll(`{{${name}}}`, String(value));
          }
          return text;
        };
        globalThis.hasTranslation = (key) => Boolean(globalThis.en && globalThis.en[key]);

        const load = (name) => fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static", name), "utf8",
        ).replace(/^import[^\n]*\r?\n/gm, "").replace(/^export /gm, "");
        const source = [
          load("numeric-input.js"),
          load("command-form.js"),
          load("command-support.js"),
          load("wgen-editor.js"),
        ].join("\n") + [
          "globalThis.CommandForm = CommandForm;",
          "globalThis.fieldsForModel = fieldsForModel;",
          "globalThis.WgenEditor = WgenEditor;",
        ].join("\n");
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const commands = __CATALOG__;
        const catalog = {
          commands,
          activeModelId: "keysight-dsox4024a",
          supported: () => true,
          fieldsFor: (command) => globalThis.fieldsForModel(command, "keysight-dsox4024a"),
          optionsFor: (field) => field.options || [],
          commandLabel: (command) => command.id,
        };

        let selectedId = "wgen-frequency";
        let currentFunction = "sine";
        let contextKeyValue = "simulate||keysight-dsox4024a";
        const calls = [];
        const hooks = {
          contextKey: () => contextKeyValue,
          mode: () => "simulate",
          selectedCommand: () => commands.find((command) => command.id === selectedId),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          headerActions: new FakeNode("div"),
          executeCommand: async (id, parameters) => {
            calls.push([id, parameters]);
            if (id === "wgen-query") {
              return { status: "completed", result: { result: { wgen: { function: currentFunction } } } };
            }
            if (id === "wgen-function") {
              currentFunction = parameters.function;
              return { status: "completed", result: { result: { function: { function: parameters.function } } } };
            }
            return { status: "completed", result: { result: {} } };
          },
        };

        const editor = new globalThis.WgenEditor(new FakeNode("div"), catalog, hooks);
        await editor.refresh(true, true);
        const frequencyInput = () => editor.entry.form.container.querySelector('[data-field="frequency_hz"]');
        const warningNote = () => editor.entry.form.container.children.find((child) => child.tagName === "P");
        const setFrequency = (value) => {
          frequencyInput().value = value;
          frequencyInput().dispatchEvent({ type: "input" });
        };

        // Empty input shows no range warning.
        assert.equal(warningNote().className, "muted compact-note");
        assert.equal(warningNote().hidden, true);
        // A representative in-range value shows no range warning.
        setFrequency("1000");
        assert.equal(warningNote().hidden, true);
        // An out-of-range value warns with the Core-projected 4000X sine limits.
        setFrequency("30000000");
        assert.equal(warningNote().hidden, false);
        assert.ok(warningNote().textContent.includes("100 mHz"));
        assert.ok(warningNote().textContent.includes("20 MHz"));
        setFrequency("1000");
        assert.equal(warningNote().hidden, true);

        // A verified wgen-function result updates the cached waveform, so the
        // warning follows the new function.
        selectedId = "wgen-function";
        await editor.refresh(true, true);
        editor.entry.form.container.querySelector('[data-field="function"]').value = "square";
        await editor.submit();
        assert.equal(editor.frequencyFunction, "square");
        // Command navigation keeps the cached waveform through the
        // presentation-only path without another wgen-query.
        selectedId = "wgen-frequency";
        const callsBeforeNavigate = calls.length;
        await editor.refresh(false, false);
        assert.deepEqual(
          calls.slice(callsBeforeNavigate).filter((call) => call[0] === "wgen-query"),
          [],
        );
        assert.equal(editor.frequencyFunction, "square");
        // 15 MHz is legal for sine but out of range for square on 4000X.
        setFrequency("15000000");
        assert.equal(warningNote().hidden, false);
        assert.ok(warningNote().textContent.includes("10 MHz"));
        // An execution context change drops the cached waveform instead of
        // reusing the previous resource's state.
        contextKeyValue = "simulate|OTHER::RESOURCE|keysight-dsox4024a";
        await editor.refresh(false, false);
        assert.equal(editor.frequencyFunction, null);
        assert.equal(warningNote().hidden, true);

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)
    harness_path = tmp_path / "wgen-frequency-warning-harness.mjs"
    harness_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"ok": True}
