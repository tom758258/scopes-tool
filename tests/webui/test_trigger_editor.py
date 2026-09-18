from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_webui.commands import COMMANDS, command_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
TRIGGER_EDITOR_SOURCE = STATIC_ROOT / "trigger-editor.js"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    body_start = source.index("{", start)
    depth = 0
    for index in range(body_start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[body_start:index + 1]
    raise AssertionError(f"Unclosed function: {signature}")


EXPECTED_TRIGGER_GROUPS = {
    "trigger-edge": "edge",
    "trigger-edge-source": "edge",
    "trigger-edge-slope": "edge",
    "trigger-edge-level": "edge",
    "trigger-edge-coupling": "edge",
    "trigger-edge-reject": "edge",
    "external-trigger-settings": "external",
    "external-trigger-range": "external",
    "trigger-edge-external-level": "external",
    "external-trigger-probe": "external",
    "external-trigger-units": "external",
    "trigger-pulse-width": "pulse-width",
    "trigger-runt": "runt",
    "trigger-transition": "transition",
    "trigger-delay": "delay",
    "trigger-setup-hold": "setup-hold",
    "trigger-edge-burst": "edge-burst",
    "trigger-tv": "tv",
    "trigger-pattern": "pattern-or",
    "trigger-or": "pattern-or",
    "trigger-sweep": "common",
    "trigger-noise-reject": "common",
    "trigger-hf-reject": "common",
    "trigger-holdoff": "common",
}


def test_trigger_commands_keep_groups_and_carry_trigger_editor_metadata() -> None:
    trigger_commands = [entry for entry in COMMANDS if entry["category"] == "Trigger"]

    assert {entry["id"] for entry in trigger_commands} == set(EXPECTED_TRIGGER_GROUPS)
    for entry in trigger_commands:
        if entry["id"] in {"external-trigger-range", "trigger-edge-external-level"}:
            assert entry.get("editor") == "external-trigger", entry["id"]
        else:
            assert entry.get("editor") == "trigger", entry["id"]
        assert entry["group"] == EXPECTED_TRIGGER_GROUPS[entry["id"]], entry["id"]
    assert [entry["id"] for entry in COMMANDS if entry.get("editor") == "serial"] == [
        "serial-mode",
        "serial-display",
        "serial-uart",
        "serial-i2c",
        "serial-spi",
        "serial-can",
        "serial-trigger-uart",
        "serial-trigger-i2c",
        "serial-trigger-spi",
        "serial-trigger-can",
        "serial-lister-query",
        "serial-lister-display",
        "serial-lister-reference",
        "serial-lister-export",
    ]


def test_command_catalog_exposes_editor_metadata_for_browser_routing() -> None:
    catalog = {entry["id"]: entry for entry in command_catalog()}

    assert catalog["trigger-edge-slope"]["editor"] == "trigger"
    assert catalog["trigger-edge-slope"]["group"] == "edge"
    assert catalog["external-trigger-settings"]["editor"] == "trigger"
    assert catalog["serial-mode"]["editor"] == "serial"
    assert "editor" not in catalog["channel-scale"]


def test_trigger_channel_fields_follow_the_existing_model_projection() -> None:
    catalog = {entry["id"]: entry for entry in command_catalog()}
    expected_fields = {
        "trigger-runt": ("channel",),
        "trigger-edge-source": ("source_channel",),
        "trigger-edge-level": ("source_channel",),
        "trigger-delay": ("arm_channel", "trigger_channel"),
    }

    for command_id, field_names in expected_fields.items():
        models = catalog[command_id]["presentation"]["models"]
        for model_id, presentation in models.items():
            expected = capabilities_for_model_id(model_id).analog_channels
            assert presentation["supported"] is True
            for name in field_names:
                assert presentation["fields"][name]["maximum"] == expected
                assert presentation["fields"][name]["options"] == list(range(1, expected + 1))


def test_app_routes_editors_by_command_metadata() -> None:
    app_source = read_static("app.js")
    html = read_static("index.html")

    assert 'import { TriggerEditor } from "/static/trigger-editor.js";' in app_source
    assert 'id="trigger-editor" class="trigger-editor" hidden' in html
    assert (
        "triggerEditor = new TriggerEditor(elements.triggerEditor, catalog, {"
        in app_source
    )
    routing_map = app_source.split("const EDITOR_RENDERERS = {", 1)[1].split("};", 1)[0]
    assert 'serial: () => serialEditor,' in routing_map
    assert 'trigger: () => triggerEditor,' in routing_map
    routing = extract_function(app_source, "function editorKindFor(command)")
    assert "EDITOR_RENDERERS[kind]" in routing
    assert 'elements.triggerEditor.hidden = editorKind !== "trigger";' in app_source
    assert 'translate(`${editorKind}.editor.title`)' in app_source
    assert 'translate(`${editorKind}.editor.description`)' in app_source


def test_trigger_editor_locale_keys_are_localized() -> None:
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert '"trigger.editor.title": "Trigger editor"' in english
    assert '"trigger.editor.description"' in english
    assert '"trigger.editor.title": "觸發編輯器"' in chinese
    assert '"trigger.editor.description"' in chinese
    for key, value in (
        ("enum.ntsc", "NTSC"),
        ("enum.pal", "PAL"),
        ("enum.palm", "PAL-M"),
        ("enum.secam", "SECAM"),
    ):
        assert f'"{key}": "{value}"' in english
        assert f'"{key}": "{value}"' in chinese
    for key in (
        "trigger.editor.divHeading",
        "trigger.editor.divHint",
        "trigger.editor.divCurrent",
        "trigger.editor.divSelection",
        "trigger.editor.divReadIncomplete",
    ):
        assert f'"{key}":' in english, key
        assert f'"{key}":' in chinese, key


TRIGGER_EDITOR_HARNESS = r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.className = "";
            this.textContent = "";
            this.type = "";
            this.value = "";
            this.min = "";
            this.max = "";
            this.customValidity = "";
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) { for (const node of nodes) { node.remove(); node.parent = this; this.children.push(node); } }
          remove() { if (this.parent) this.parent.children = this.parent.children.filter((node) => node !== this); this.parent = null; }
          get validity() {
            const value = Number(this.value);
            return {
              badInput: false,
              rangeOverflow: this.max !== "" && Number.isFinite(value) && value > Number(this.max),
              rangeUnderflow: this.min !== "" && Number.isFinite(value) && value < Number(this.min),
            };
          }
          setCustomValidity(message) { this.customValidity = message; }
          reportValidity() {
            if (this.customValidity || !this.checkValidity()) {
              globalThis.__reportedValidity.push(this.customValidity || `range:${this.value}`);
              return false;
            }
            return true;
          }
          checkValidity() {
            if (this.disabled || this.type !== "number") return true;
            const { validity } = this;
            return !this.customValidity && !validity.badInput
              && !validity.rangeOverflow && !validity.rangeUnderflow;
          }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.__reportedValidity = [];
        globalThis.translate = (key) => key;
        globalThis.hasTranslation = () => true;
        globalThis.CommandForm = class CommandForm {
          constructor(container) {
            this.container = container;
            this.renderedCommand = null;
            this.renderOptions = {};
            this.queryValuesResult = {};
            this.valuesResult = {};
            this.syncCalls = [];
            this.clearedDirty = 0;
            this.disableCalls = [];
          }
          render(command, options = {}) {
            this.renderedCommand = command;
            this.renderOptions = options;
          }
          values() { return this.valuesResult; }
          queryValues() { return this.queryValuesResult; }
          setDisabled(value) { this.disableCalls.push(value); }
          clearDirty() { this.clearedDirty += 1; }
          syncResult(job, preserveDirty) { this.syncCalls.push([job.job_id, preserveDirty]); }
          isDirty() { return false; }
        };

        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.triggerApi = { TriggerEditor };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const settle = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
          await new Promise((resolve) => setTimeout(resolve, 0));
        };

        const settingPresentation = {
          kind: "setting", action_field: "action", apply_value: "set",
          query_value: "query", query_fields: [],
        };
        const def = (id, group, presentation = settingPresentation) => ({
          id,
          editor: "trigger",
          category: "Trigger",
          label: id,
          modes: ["live"],
          group,
          presentation,
          fields: [],
        });

        const commands = [
          def("trigger-edge-slope", "edge"),
          def("trigger-edge-coupling", "edge"),
          def("trigger-runt", "runt"),
          def("trigger-tv", "tv"),
          def("external-trigger-settings", "external", { kind: "command", action: "read" }),
        ];
        const catalog = {
          commands,
          supported: () => true,
          groupLabel: (group) => group,
          commandLabel: (command) => command.label,
          description: (command) => `catalog-description:${command.id}`,
          fieldsFor: (command) => command.fields,
        };
        const env = {
          available: true,
          executionBusy: false,
          contextKey: "ctx",
          selectedId: "trigger-edge-slope",
        };
        const submitted = [];
        const hooks = {
          headerActions: new FakeNode("div"),
          executeCommand: async (command, parameters, options) => {
            const job = {
              job_id: `${command}-${submitted.length}`,
              status: "completed",
              result: { result: {} },
            };
            submitted.push({ command, parameters, intent: options?.intent, job });
            return job;
          },
          isAvailable: () => env.available,
          isExecutionBusy: () => env.executionBusy,
          contextKey: () => env.contextKey,
          selectedCommand: () => catalog.commands.find((command) => command.id === env.selectedId),
        };
        const buildEditor = () =>
          new globalThis.triggerApi.TriggerEditor(new FakeNode(), catalog, hooks);
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_external_trigger_editor_routing() -> None:
    app_source = read_static("app.js")
    html = read_static("index.html")

    assert 'import { ExternalTriggerEditor } from "/static/external-trigger-editor.js";' in app_source
    assert 'id="external-trigger-editor" class="external-trigger-editor" hidden' in html
    assert (
        "externalTriggerEditor = new ExternalTriggerEditor(elements.externalTriggerEditor, catalog, {"
        in app_source
    )
    routing_map = app_source.split("const EDITOR_RENDERERS = {", 1)[1].split("};", 1)[0]
    assert '"external-trigger": () => externalTriggerEditor,' in routing_map
    assert 'elements.externalTriggerEditor.hidden = editorKind !== "external-trigger";' in app_source
    assert 'if (editorKind === "external-trigger") externalTriggerEditor?.schedulePresentation();' in app_source
    assert 'externalTriggerEditor.readButton.hidden = editorKind !== "external-trigger";' in app_source
    assert 'externalTriggerEditor.applyButton.hidden = editorKind !== "external-trigger";' in app_source
    assert "modelSeries" not in app_source
    assert '"external-trigger-range-level": [' in app_source
    assert '"external-trigger-range",' in app_source
    assert '"trigger-edge-external-level",' in app_source
    assert "externalTriggerEditor?.deactivate();" in app_source


def test_external_trigger_range_level_composite_workspace() -> None:
    catalog = {entry["id"]: entry for entry in command_catalog()}
    composite = catalog["external-trigger-range-level"]
    assert composite["category"] == "Trigger"
    assert composite["group"] == "external"
    assert composite["editor"] == "external-trigger"
    assert composite["presentation_only"] is True
    assert composite["modes"] == ["live", "simulate"]
    assert composite["fields"] == []

    assert catalog["external-trigger-range"]["browser_hidden"] is True
    assert catalog["trigger-edge-external-level"]["browser_hidden"] is True

    models = catalog["external-trigger-range"]["presentation"]["models"]
    assert models["keysight-dsox4034a"]["fields"]["range_volts"]["quick_fill_probe_1x_values"] == [1.6, 8.0]
    assert models["keysight-dsox3024a"]["fields"]["range_volts"]["quick_fill_probe_1x_values"] == [8.0]

    ids = [entry["id"] for entry in command_catalog()]
    assert ids.index("external-trigger-range-level") + 1 == ids.index("external-trigger-range")

    visible = [entry["id"] for entry in command_catalog() if not entry.get("browser_hidden")]
    assert "external-trigger-range-level" in visible
    assert "external-trigger-range" not in visible
    assert "trigger-edge-external-level" not in visible

    range_fields = {field["name"]: field for field in catalog["external-trigger-range"]["fields"]}
    assert "range_volts" in range_fields
    level_fields = {field["name"]: field for field in catalog["trigger-edge-external-level"]["fields"]}
    assert "level" in level_fields

    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    assert '"command.external-trigger-range-level": "External Trigger Range / Level"' in english
    assert '"command.external-trigger-range-level": "外部觸發範圍 / 位準"' in chinese
    assert '"description.external-trigger-range-level":' in english
    assert '"description.external-trigger-range-level":' in chinese


def test_external_trigger_level_uses_current_range() -> None:
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.className = "";
            this.textContent = "";
            this.type = "";
            this.value = "";
            this.inputMode = "";
            this.style = {};
            this.attributes = {};
            this.customValidity = "";
            this.reported = [];
            const classList = { toggled: {} };
            classList.toggle = (name, force) => { classList.toggled[name] = force; };
            this.classList = classList;
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) {
            for (const node of nodes) {
              node.remove();
              node.parent = this;
              this.children.push(node);
            }
          }
          remove() { if (this.parent) this.parent.children = this.parent.children.filter((n) => n !== this); this.parent = null; }
          setAttribute(k, v) { this.attributes[k] = String(v); }
          setCustomValidity(value) { this.customValidity = String(value); }
          reportValidity() { this.reported.push(this.customValidity); }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        // Template shapes mirror the composition contract only, not locale prose.
        const TEMPLATES = {
          "external-trigger.editor.modeRange": "Range",
          "external-trigger.editor.modeLevel": "Level",
          "external-trigger.editor.readFirstHelp": "READFIRST",
          "external-trigger.editor.levelDescription": "LEVELDESC",
          "external-trigger.editor.levelOutOfRange": "OUT {{min}} {{max}}",
          "field.channel-range.value": "Range value",
          "field.level": "Level",
          "help.external-trigger-range.range_volts": "RANGEHELP",
          "help.trigger-edge-external-level.level": "LEVELHELP",
          "actions.readSettings": "Read",
          "actions.apply": "Apply",
          "system.readFailed": "READFAILED",
        };
        globalThis.translate = (key, values = {}) => {
          let text = TEMPLATES[key] || key;
          for (const [name, value] of Object.entries(values)) {
            text = text.replaceAll(`{{${name}}}`, String(value));
          }
          return text;
        };

        const strip = (filename) => fs.readFileSync(filename, "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "").replace(/^export /gm, "");
        const liveDataSource = strip(process.argv[2])
          + "\nglobalThis.formatEngineering = formatEngineering;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(liveDataSource)}`);
        const editorSource = strip(process.argv[1])
          + "\nglobalThis.ExternalTriggerEditor = ExternalTriggerEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const commands = __CATALOG__;
        const catalog = {
          commands,
          supported: () => true,
          fieldsFor: (command) => {
            const overrides = command.presentation?.models?.[env.modelId]?.fields || {};
            return (command.fields || []).filter((field) => !overrides[field.name]?.hidden).map((field) => ({
              ...field,
              ...(overrides[field.name] || {}),
            }));
          },
        };
        const env = { selectedId: "external-trigger-range-level", contextKey: "ctx", modelId: "keysight-dsox4024a" };
        const calls = [];
        let range = 8;
        let levelVal = 0.5;
        let probeAttenuation = 1;
        let units = "volts";
        let rangeStatus = "completed";
        let levelStatus = "completed";
        let settingsStatus = "completed";
        let deferRange = false;
        let releaseRange = null;
        const hooks = {
          headerActions: new FakeNode("div"),
          contextKey: () => env.contextKey,
          mode: () => "live",
          selectedCommand: () => commands.find((command) => command.id === env.selectedId),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          executeCommand: async (id, parameters, options) => {
            calls.push([id, parameters, options?.intent]);
            if (id === "external-trigger-settings") {
              if (settingsStatus !== "completed") return { status: settingsStatus, result: { result: {} } };
              return { status: "completed", result: { result: { settings: {
                probe_attenuation: probeAttenuation,
                range_value: range,
                units,
                bandwidth_limit_enabled: false,
                raw_response: "EXT",
              } } } };
            }
            if (id === "external-trigger-range" && parameters.action === "query") {
              if (deferRange) await new Promise((resolve) => { releaseRange = resolve; });
              if (rangeStatus !== "completed") return { status: rangeStatus, result: { result: {} } };
              return { status: "completed", result: { result: { range: { range_volts: range } } } };
            }
            if (id === "external-trigger-range") {
              range = parameters.range_volts;
              return { status: "completed", result: { result: { range: { range_volts: range } } } };
            }
            if (id === "trigger-edge-external-level" && parameters.action === "query") {
              if (levelStatus !== "completed") return { status: levelStatus, result: { result: {} } };
              return { status: "completed", result: { result: { level_volts: levelVal } } };
            }
            levelVal = parameters.level;
            return { status: "completed", result: { result: { level_volts: levelVal } } };
          },
        };

        const settle = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
        };
        const findAll = (node, pred, out = []) => {
          for (const child of node.children || []) {
            if (pred(child)) out.push(child);
            findAll(child, pred, out);
          }
          return out;
        };

        const editor = new globalThis.ExternalTriggerEditor(new FakeNode("div"), catalog, hooks);
        await settle();
        const rangeInput = () => findAll(editor.container, (node) => node.dataset.field === "range_volts")[0];
        const levelInput = () => findAll(editor.container, (node) => node.dataset.field === "level")[0];
        const modeButton = (mode) => findAll(
          editor.container, (node) => node.tagName === "BUTTON" && node.dataset.mode === mode,
        )[0];

        // 1. The presentation entry opens in Range; mode switches stay in the
        // workspace without changing the selected command.
        assert.equal(editor.mode, "range");
        assert.equal(editor.rangeSection.hidden, false);
        assert.equal(editor.levelSection.hidden, true);
        assert.equal(modeButton("range").classList.toggled.selected, true);
        modeButton("level").dispatch("click");
        assert.equal(editor.mode, "level");
        assert.equal(editor.rangeSection.hidden, true);
        assert.equal(editor.levelSection.hidden, false);
        assert.equal(env.selectedId, "external-trigger-range-level");
        // Leaving the workspace resets trusted state; re-entering returns to Range.
        editor.deactivate();
        assert.equal(editor.mode, "range");
        assert.equal(rangeInput().value, "");
        assert.equal(levelInput().value, "");
        editor.present();
        assert.equal(editor.mode, "range");
        // A direct underlying selection still resolves to its mode.
        env.selectedId = "trigger-edge-external-level";
        editor.present();
        assert.equal(editor.mode, "level");
        env.selectedId = "external-trigger-range-level";
        editor.present();
        assert.equal(editor.mode, "range");

        // The header owns a single Read / Apply pair.
        assert.deepEqual(hooks.headerActions.children, [editor.readButton, editor.applyButton]);

        // 2. Range mode reads and applies; a successful apply clears the level side.
        await editor.readCurrent();
        assert.deepEqual(calls, [
          ["external-trigger-range", { action: "query" }, "readback"],
          ["external-trigger-settings", {}, "readback"],
        ]);
        assert.equal(rangeInput().value, "8");
        assert.equal(editor.rangeRead, 8);

        env.selectedId = "trigger-edge-external-level";
        editor.present();
        await editor.readCurrent();
        assert.deepEqual(calls.slice(2), [
          ["trigger-edge-external-level", { action: "query" }, "readback"],
          ["external-trigger-settings", {}, "readback"],
        ]);
        assert.equal(levelInput().value, "0.5");
        assert.equal(editor.levelRead, 0.5);
        modeButton("range").dispatch("click");
        assert.equal(editor.mode, "range");
        assert.equal(levelInput().value, "0.5");
        rangeInput().value = "1.6";
        calls.length = 0;
        await editor.applyCurrent();
        assert.deepEqual(calls, [
          ["external-trigger-range", { action: "set", range_volts: 1.6 }, "apply"],
        ]);
        assert.equal(rangeInput().value, "1.6");
        assert.equal(editor.rangeValue, 1.6);
        assert.equal(levelInput().value, "");
        assert.equal(editor.levelRead, null);

        // 3. Level entries are validated against the current range.
        modeButton("level").dispatch("click");
        assert.equal(editor.mode, "level");
        await editor.readCurrent();
        assert.equal(levelInput().value, "0.5");
        for (const bad of ["2", "-2"]) {
          calls.length = 0;
          levelInput().value = bad;
          await editor.applyCurrent();
          assert.deepEqual(calls, [["external-trigger-range", { action: "query" }, "readback"]]);
          assert.equal(levelInput().customValidity, "OUT -1.6 1.6");
          assert.equal(editor.busy, false);
        }
        for (const good of ["1", "-1"]) {
          calls.length = 0;
          levelInput().value = good;
          await editor.applyCurrent();
          assert.deepEqual(calls, [
            ["external-trigger-range", { action: "query" }, "readback"],
            ["trigger-edge-external-level", { action: "set", level: Number(good) }, "apply"],
          ]);
          assert.equal(levelInput().value, good);
          assert.equal(editor.levelRead, Number(good));
        }

        // 4. A failed range blocks the level set without guessing.
        rangeStatus = "failed";
        calls.length = 0;
        levelInput().value = "0.5";
        await editor.applyCurrent();
        assert.deepEqual(calls, [["external-trigger-range", { action: "query" }, "readback"]]);
        assert.equal(levelInput().customValidity, "READFAILED");
        assert.equal(editor.busy, false);
        rangeStatus = "completed";

        // 5. A failed level query drops trust but keeps the draft.
        levelStatus = "failed";
        calls.length = 0;
        await editor.readCurrent();
        assert.deepEqual(calls, [["trigger-edge-external-level", { action: "query" }, "readback"]]);
        assert.equal(editor.levelRead, null);
        assert.equal(levelInput().value, "0.5");
        levelStatus = "completed";

        // 6. A stale range response never leads to a set.
        deferRange = true;
        calls.length = 0;
        const pending = editor.applyCurrent();
        await settle();
        env.contextKey = "new-context";
        releaseRange();
        await pending;
        assert.deepEqual(calls, [["external-trigger-range", { action: "query" }, "readback"]]);
        assert.equal(editor.busy, false);

        // 7. A blank level never reaches the instrument (Number("") === 0 guard).
        modeButton("level").dispatch("click");
        assert.equal(editor.mode, "level");
        for (const blank of ["", "   "]) {
          calls.length = 0;
          levelInput().value = blank;
          levelInput().setCustomValidity("OUT -1.6 1.6");
          await editor.applyCurrent();
          assert.deepEqual(calls, []);
          assert.equal(levelInput().customValidity, "");
          assert.equal(editor.busy, false);
        }

        // 8. A mode switch during a pending Level apply invalidates the Level set.
        levelInput().value = "0.5";
        deferRange = true;
        calls.length = 0;
        const racing = editor.applyCurrent();
        await settle();
        assert.deepEqual(calls, [["external-trigger-range", { action: "query" }, "readback"]]);
        modeButton("range").dispatch("click");
        assert.equal(editor.mode, "range");
        assert.equal(modeButton("range").disabled, true);
        assert.equal(modeButton("level").disabled, true);
        releaseRange();
        await racing;
        assert.deepEqual(calls, [["external-trigger-range", { action: "query" }, "readback"]]);
        assert.equal(editor.busy, false);
        assert.equal(modeButton("range").disabled, false);
        assert.equal(modeButton("level").disabled, false);
        deferRange = false;

        // 9. deactivate/re-enter during a pending Level apply invalidates the Level set.
        modeButton("level").dispatch("click");
        assert.equal(editor.mode, "level");
        levelInput().value = "0.5";
        deferRange = true;
        calls.length = 0;
        const stale = editor.applyCurrent();
        await settle();
            assert.deepEqual(calls, [["external-trigger-range", { action: "query" }, "readback"]]);
            editor.deactivate();
            env.selectedId = "external-trigger-range-level";
            editor.present();
            assert.equal(editor.mode, "range");
        releaseRange();
        await stale;
        assert.deepEqual(calls, [["external-trigger-range", { action: "query" }, "readback"]]);
        assert.equal(editor.busy, false);
        assert.equal(editor.mode, "range");
        deferRange = false;

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", json.dumps([
        entry for entry in command_catalog() if entry["id"] in {
            "external-trigger-range",
            "external-trigger-range-level",
            "trigger-edge-external-level",
        }
    ]))
    completed = subprocess.run(
        [
            "node", "--input-type=module", "--eval", script,
            str(STATIC_ROOT / "external-trigger-editor.js"),
            str(STATIC_ROOT / "live-data.js"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == {"ok": True}


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_external_trigger_quick_fill() -> None:
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.className = "";
            this.textContent = "";
            this.type = "";
            this.value = "";
            this.inputMode = "";
            this.style = {};
            this.attributes = {};
            this.customValidity = "";
            this.reported = [];
            const classList = { toggled: {} };
            classList.toggle = (name, force) => { classList.toggled[name] = force; };
            this.classList = classList;
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) {
            for (const node of nodes) {
              node.remove();
              node.parent = this;
              this.children.push(node);
            }
          }
          remove() { if (this.parent) this.parent.children = this.parent.children.filter((n) => n !== this); this.parent = null; }
          setAttribute(k, v) { this.attributes[k] = String(v); }
          setCustomValidity(value) { this.customValidity = String(value); }
          reportValidity() { this.reported.push(this.customValidity); }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.translate = (key) => key;

        const strip = (filename) => fs.readFileSync(filename, "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "").replace(/^export /gm, "");
        const liveDataSource = strip(process.argv[2])
          + "\nglobalThis.formatEngineering = formatEngineering;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(liveDataSource)}`);
        const editorSource = strip(process.argv[1])
          + "\nglobalThis.ExternalTriggerEditor = ExternalTriggerEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const commands = __CATALOG__;
        const catalog = {
          commands,
          supported: () => true,
          fieldsFor: (command) => {
            const overrides = command.presentation?.models?.[env.modelId]?.fields || {};
            return (command.fields || []).filter((field) => !overrides[field.name]?.hidden).map((field) => ({
              ...field,
              ...(overrides[field.name] || {}),
            }));
          },
        };
        const env = { selectedId: "external-trigger-range-level", contextKey: "ctx", modelId: "keysight-dsox4024a" };
        const calls = [];
        let range = 8;
        let levelVal = 0.5;
        let probeAttenuation = 1;
        let units = "volts";
        const hooks = {
          headerActions: new FakeNode("div"),
          contextKey: () => env.contextKey,
          mode: () => "live",
          selectedCommand: () => commands.find((command) => command.id === env.selectedId),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          executeCommand: async (id, parameters, options) => {
            calls.push([id, parameters, options?.intent]);
            if (id === "external-trigger-settings") {
              return { status: "completed", result: { result: { settings: {
                probe_attenuation: probeAttenuation,
                range_value: range,
                units,
                bandwidth_limit_enabled: false,
                raw_response: "EXT",
              } } } };
            }
            if (id === "external-trigger-range" && parameters.action === "query") {
              return { status: "completed", result: { result: { range: { range_volts: range } } } };
            }
            if (id === "external-trigger-range") {
              range = parameters.range_volts;
              return { status: "completed", result: { result: { range: { range_volts: range } } } };
            }
            if (id === "trigger-edge-external-level" && parameters.action === "query") {
              return { status: "completed", result: { result: { level_volts: levelVal } } };
            }
            levelVal = parameters.level;
            return { status: "completed", result: { result: { level_volts: levelVal } } };
          },
        };

        const settle = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
        };
        const findAll = (node, pred, out = []) => {
          for (const child of node.children || []) {
            if (pred(child)) out.push(child);
            findAll(child, pred, out);
          }
          return out;
        };

        const editor = new globalThis.ExternalTriggerEditor(new FakeNode("div"), catalog, hooks);
        await settle();
        const rangeInput = () => findAll(editor.container, (node) => node.dataset.field === "range_volts")[0];
        const levelInput = () => findAll(editor.container, (node) => node.dataset.field === "level")[0];
        const modeButton = (mode) => findAll(
          editor.container, (node) => node.tagName === "BUTTON" && node.dataset.mode === mode,
        )[0];
        const rangePresets = () => findAll(editor.rangeSection, (node) => node.tagName === "BUTTON");
        const levelPresets = () => findAll(editor.levelSection, (node) => node.tagName === "BUTTON");
        const labels = (nodes) => nodes.map((node) => node.textContent);

        // A. Presets exist before any read: 4000X shows its two base values,
        // Level shows its five symbolic presets, all visible but disabled.
        assert.equal(editor.modeSelector.className, "trigger-editor-segmented channel-scale-range-mode");
        assert.equal(editor.rangeField.className, "field channel-scale-range-value");
        assert.equal(editor.levelField.className, "field channel-scale-range-value");
        assert.equal(editor.rangePresets.className, "channel-scale-range-presets");
        assert.equal(editor.levelPresets.className, "channel-scale-range-presets");
        assert.equal(rangePresets().length, 2);
        assert.deepEqual(labels(rangePresets()), ["1.6", "8"]);
        assert.ok(rangePresets().every((button) => button.disabled === true));
        assert.equal(levelPresets().length, 5);
        assert.deepEqual(labels(levelPresets()), ["−R", "−R/2", "0", "R/2", "R"]);
        assert.ok(levelPresets().every((button) => button.disabled === true));
        const firstRangeButton = rangePresets()[0];
        const firstLevelButton = levelPresets()[0];

        // B. 4000X range presets follow the probe attenuation.
        calls.length = 0;
        await editor.readCurrent();
        assert.deepEqual(calls, [
          ["external-trigger-range", { action: "query" }, "readback"],
          ["external-trigger-settings", {}, "readback"],
        ]);
        assert.deepEqual(labels(rangePresets()), ["1.60 V", "8.00 V"]);
        assert.equal(rangePresets()[0], firstRangeButton);
        assert.ok(rangePresets().every((button) => button.disabled === false));
        calls.length = 0;
        rangePresets()[0].dispatch("click");
        assert.equal(rangeInput().value, "1.6");
        assert.deepEqual(calls, []);

        probeAttenuation = 10;
        calls.length = 0;
        await editor.readCurrent();
        assert.deepEqual(labels(rangePresets()), ["16.0 V", "80.0 V"]);

        // C. 3000X only offers 8 V at 1:1 attenuation. A model switch is a
        // context change in the real app, so the structure is rebuilt on the
        // next present, before any read.
        env.modelId = "keysight-dsox3024a";
        env.contextKey = "ctx-3000x";
        probeAttenuation = 1;
        editor.present();
        assert.equal(rangePresets().length, 1);
        assert.deepEqual(labels(rangePresets()), ["8"]);
        assert.ok(rangePresets().every((button) => button.disabled === true));
        calls.length = 0;
        await editor.readCurrent();
        assert.deepEqual(labels(rangePresets()), ["8.00 V"]);

        // D. Level presets follow the current range; a Range apply invalidates them.
        range = 8;
        modeButton("level").dispatch("click");
        calls.length = 0;
        await editor.readCurrent();
        assert.deepEqual(calls, [
          ["trigger-edge-external-level", { action: "query" }, "readback"],
          ["external-trigger-settings", {}, "readback"],
        ]);
        assert.deepEqual(labels(levelPresets()), ["-8.00 V", "-4.00 V", "0.00 V", "4.00 V", "8.00 V"]);
        assert.equal(levelPresets()[0], firstLevelButton);
        calls.length = 0;
        levelPresets()[3].dispatch("click");
        assert.equal(levelInput().value, "4");
        assert.deepEqual(calls, []);

        modeButton("range").dispatch("click");
        rangeInput().value = "1.6";
        calls.length = 0;
        await editor.applyCurrent();
        assert.equal(calls.length, 1);
        assert.equal(levelPresets().length, 5);
        assert.ok(levelPresets().every((button) => button.disabled === true));
        calls.length = 0;
        levelInput().value = "";
        levelPresets()[0].dispatch("click");
        assert.equal(levelInput().value, "");
        assert.deepEqual(calls, []);

        // E. Amps units change the preset labels.
        env.modelId = "keysight-dsox4024a";
        env.contextKey = "ctx";
        units = "amps";
        probeAttenuation = 1;
        editor.present();
        calls.length = 0;
        await editor.readCurrent();
        assert.deepEqual(labels(rangePresets()), ["1.60 A", "8.00 A"]);

        // F. Range partial settings: a null probe keeps the primary readback.
        probeAttenuation = null;
        units = "volts";
        calls.length = 0;
        await editor.readCurrent();
        assert.equal(rangeInput().value, "1.6");
        assert.equal(editor.rangeRead, 1.6);
        assert.ok(rangePresets().length > 0);
        assert.ok(rangePresets().every((button) => button.disabled === true));

        // G. Level tolerates a null probe attenuation.
        probeAttenuation = null;
        range = 8;
        units = "volts";
        modeButton("level").dispatch("click");
        calls.length = 0;
        await editor.readCurrent();
        assert.deepEqual(calls, [
          ["trigger-edge-external-level", { action: "query" }, "readback"],
          ["external-trigger-settings", {}, "readback"],
        ]);
        assert.equal(levelInput().value, "0.5");
        assert.equal(editor.levelRead, 0.5);
        assert.equal(editor.rangeValue, 8);
        assert.deepEqual(labels(levelPresets()), ["-8.00 V", "-4.00 V", "0.00 V", "4.00 V", "8.00 V"]);
        assert.ok(levelPresets().every((button) => button.disabled === false));

        // H. Level tolerates missing units for the primary read; only quick-fill stops.
        units = null;
        calls.length = 0;
        await editor.readCurrent();
        assert.equal(levelInput().value, "0.5");
        assert.equal(editor.levelRead, 0.5);
        assert.equal(editor.rangeValue, 8);
        assert.equal(levelInput().customValidity, "");
        assert.deepEqual(levelInput().reported, []);
        assert.ok(levelPresets().every((button) => button.disabled === true));

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", json.dumps([
        entry for entry in command_catalog() if entry["id"] in {
            "external-trigger-range",
            "external-trigger-range-level",
            "trigger-edge-external-level",
        }
    ]))
    completed = subprocess.run(
        [
            "node", "--input-type=module", "--eval", script,
            str(STATIC_ROOT / "external-trigger-editor.js"),
            str(STATIC_ROOT / "live-data.js"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == {"ok": True}


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_actions_follow_global_execution_admission_and_recover() -> None:
    script = textwrap.dedent(TRIGGER_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        const entry = editor.entry;
        assert.equal(entry.id, "trigger-edge-slope");
        assert.equal(entry.form.container.className, "command-form");
        assert.ok(hooks.headerActions.children.includes(editor.refreshButton));
        assert.ok(hooks.headerActions.children.includes(entry.button));
        assert.ok(!editor.sectionsHost.children[0].children.includes(entry.button));
        assert.equal(editor.sectionsHost.children.length, 1);

        env.executionBusy = true;
        editor.applyBusyState();
        assert.equal(editor.refreshButton.disabled, true);
        assert.equal(entry.button.disabled, true);
        await editor.submit();
        assert.deepEqual(submitted, []);

        env.executionBusy = false;
        editor.applyBusyState();
        assert.equal(editor.refreshButton.disabled, false);
        assert.equal(entry.button.disabled, false);
        await editor.submit();
        await settle();
        assert.equal(submitted[0].command, entry.id);
        assert.equal(submitted[0].intent, "apply");
        assert.equal(submitted.length, 1);
        ''')
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(TRIGGER_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_editor_renders_only_selected_command_and_scopes_readback_to_it() -> None:
    script = textwrap.dedent(TRIGGER_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        // Selecting an Edge command renders only that command without reading it.
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();

        assert.equal(editor.sectionsHost.children.length, 1);
        assert.equal(editor.entry.id, "trigger-edge-slope");
        assert.ok(editor.entry.button.className.split(" ").includes("primary"));
        assert.ok(hooks.headerActions.children.includes(editor.entry.button));
        assert.deepEqual(submitted, []);

        // Explicit Refresh reads only the selected command.
        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "trigger-edge-slope",
        ]);
        assert.ok(submitted.every((entry) => entry.intent === "readback"));
        assert.equal(editor.entry.form.renderedCommand, commands.find((c) => c.id === "trigger-edge-slope"));
        assert.deepEqual(editor.entry.form.syncCalls.at(-1), [submitted[0].job.job_id, true]);

        // Manual refresh re-reads the same command without rebuilding forms.
        submitted.length = 0;
        const epochBeforeRefresh = editor.epoch;
        const formBeforeRefresh = editor.entry.form;
        editor.refreshButton.dispatch("click");
        await settle();
        assert.equal(editor.epoch, epochBeforeRefresh);
        assert.equal(editor.entry.form, formBeforeRefresh);
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "trigger-edge-slope",
        ]);

        // Switching within the group replaces the section without reading it.
        // A dirty draft on the old form must not leak into the new one.
        submitted.length = 0;
        editor.entry.form.valuesResult = { action: "set", slope: "positive" };
        env.selectedId = "trigger-edge-coupling";
        editor.schedulePresentation();
        await settle();
        assert.equal(editor.sectionsHost.children.length, 1);
        assert.equal(editor.entry.id, "trigger-edge-coupling");
        assert.equal(editor.entry.form.renderedCommand, commands.find((c) => c.id === "trigger-edge-coupling"));
        assert.equal(hooks.headerActions.children.length, 2);
        assert.ok(hooks.headerActions.children.includes(editor.entry.button));
        assert.deepEqual(submitted, []);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(TRIGGER_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_editor_applies_each_command_individually() -> None:
    script = textwrap.dedent(TRIGGER_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.selectedId = "trigger-runt";
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        const runtEntry = editor.entry;

        // A rejected form submit executes nothing.
        submitted.length = 0;
        runtEntry.form.valuesResult = null;
        runtEntry.button.dispatch("click");
        await settle();
        assert.deepEqual(submitted, []);

        // Apply submits exactly this one existing command with action=set;
        // the setter readback reconciles the form without a second query.
        submitted.length = 0;
        runtEntry.form.valuesResult = { action: "set", channel: 1 };
        runtEntry.button.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "trigger-runt",
        ]);
        assert.equal(submitted[0].intent, "apply");
        assert.deepEqual(submitted[0].parameters, { action: "set", channel: 1 });
        assert.equal(runtEntry.form.clearedDirty, 1);
        assert.deepEqual(runtEntry.form.syncCalls.at(-1), [submitted[0].job.job_id, false]);

        // No aggregate transaction: a second Apply still runs only this command.
        submitted.length = 0;
        runtEntry.button.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "trigger-runt",
        ]);
        assert.equal(submitted[0].intent, "apply");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(TRIGGER_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_editor_gates_busy_state_and_keeps_read_commands_explicit() -> None:
    script = textwrap.dedent(TRIGGER_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.selectedId = "trigger-runt";
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        const runtEntry = editor.entry;

        let releaseApply;
        const recordingExecute = hooks.executeCommand;
        hooks.executeCommand = () => new Promise((resolve) => {
          releaseApply = () => resolve({
            job_id: "pending-job",
            status: "completed",
            result: { result: {} },
          });
        });
        runtEntry.button.dispatch("click");
        await settle();
        assert.equal(editor.busy, true);
        assert.equal(runtEntry.button.disabled, true);
        assert.equal(editor.refreshButton.disabled, true);
        releaseApply();
        hooks.executeCommand = recordingExecute;
        await settle();
        assert.equal(editor.busy, false);
        assert.equal(runtEntry.button.disabled, false);
        assert.equal(editor.refreshButton.disabled, false);

        // Informational commands keep explicit Read semantics: selecting one
        // reads it, the header Read re-runs it, and no second inline Read
        // button is shown.
        submitted.length = 0;
        env.selectedId = "external-trigger-settings";
        editor.scheduleRefresh();
        await settle();
        const readEntry = editor.entry;
        assert.equal(readEntry.id, "external-trigger-settings");
        assert.equal(readEntry.kind, "command");
        assert.equal(readEntry.button.textContent, "actions.read");
        assert.equal(readEntry.button.hidden, true);
        assert.equal(editor.sectionsHost.children.length, 1);
        assert.equal(hooks.headerActions.children.length, 2);
        assert.ok(hooks.headerActions.children.includes(readEntry.button));
        assert.deepEqual(submitted.map((item) => [item.command, item.intent]), [
          ["external-trigger-settings", undefined],
        ]);
        assert.deepEqual(submitted[0].parameters, {});
        assert.equal(readEntry.form.clearedDirty, 0);

        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((item) => [item.command, item.intent]), [
          ["external-trigger-settings", undefined],
          ["external-trigger-settings", undefined],
        ]);

        // Setter commands still show their Apply after switching back.
        submitted.length = 0;
        env.selectedId = "trigger-runt";
        editor.schedulePresentation();
        await settle();
        assert.equal(editor.entry.id, "trigger-runt");
        assert.equal(editor.entry.button.hidden, false);
        assert.equal(editor.entry.button.textContent, "actions.apply");
        assert.ok(editor.entry.button.className.split(" ").includes("primary"));

        // Runtime unavailability keeps the editor visible and disabled without I/O.
        submitted.length = 0;
        env.selectedId = "external-trigger-settings";
        env.available = false;
        editor.scheduleRefresh();
        await settle();
        assert.equal(editor.entry.id, "external-trigger-settings");
        assert.equal(editor.refreshButton.disabled, true);
        assert.equal(editor.entry.button.disabled, true);
        assert.equal(editor.entry.form.disableCalls.at(-1), true);
        assert.deepEqual(submitted, []);
        env.available = true;
        editor.scheduleRefresh();
        await settle();
        assert.equal(editor.entry.id, "external-trigger-settings");
        assert.equal(editor.entry.button.disabled, false);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(TRIGGER_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_editor_skips_unsupported_group_commands_and_keeps_projection_in_command_form() -> None:
    script = textwrap.dedent(TRIGGER_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.selectedId = "trigger-edge-slope";
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        assert.equal(editor.entry.id, "trigger-edge-slope");
        assert.equal(
          editor.entry.form.renderedCommand,
          commands.find((command) => command.id === "trigger-edge-slope"),
        );

        catalog.supported = (command) => command.id !== "trigger-edge-slope";
        env.contextKey = "ctx-2";
        editor.scheduleRefresh();
        await settle();
        assert.equal(editor.entry, null);
        assert.equal(editor.sectionsHost.children.length, 0);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(TRIGGER_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_editor_query_field_change_is_passive_until_refresh() -> None:
    script = textwrap.dedent(TRIGGER_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        // trigger-edge-level defines source_channel as its query field.
        catalog.commands = [
          def("trigger-edge-level", "edge", {
            kind: "setting", action_field: "action", apply_value: "set",
            query_value: "query", query_fields: ["source_channel"],
          }),
          def("trigger-edge-slope", "edge"),
        ];
        env.selectedId = "trigger-edge-level";
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        assert.equal(editor.entry.id, "trigger-edge-level");
        const levelEntry = editor.entry;
        assert.equal(levelEntry.form.renderOptions.onQueryFieldChange, undefined);

        submitted.length = 0;
        levelEntry.form.queryValuesResult = { action: "query", source_channel: 2 };
        await settle();

        assert.deepEqual(submitted, []);

        // Explicit Refresh reads the selected command using the changed query selector.
        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "trigger-edge-level",
        ]);
        assert.equal(submitted[0].intent, "readback");
        assert.deepEqual(submitted[0].parameters, { action: "query", source_channel: 2 });
        assert.deepEqual(levelEntry.form.syncCalls.at(-1), [submitted[0].job.job_id, true]);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(TRIGGER_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_editor_serializes_readback_and_disables_actions_while_busy() -> None:
    script = textwrap.dedent(TRIGGER_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.selectedId = "trigger-runt";
        const editor = buildEditor();
        let queries = 0;
        let releaseQuery;
        hooks.executeCommand = (command) => {
          queries += 1;
          return new Promise((resolve) => {
            releaseQuery = () => resolve({
              job_id: `${command}-deferred-${queries}`,
              status: "completed",
              result: { result: {} },
            });
          });
        };
        editor.scheduleRefresh();
        await settle();

        // The selected-command readback itself holds the busy gate.
        const runtEntry = editor.entry;
        assert.equal(queries, 1);
        assert.equal(editor.busy, true);
        assert.equal(runtEntry.button.disabled, true);
        assert.equal(runtEntry.form.disableCalls.at(-1), true);
        assert.equal(editor.refreshButton.disabled, true);

        // Same-state auto notifications during the readback are ignored.
        editor.scheduleRefresh();
        await settle();
        assert.equal(queries, 1);

        // Forced refresh requests are queued exactly once.
        editor.scheduleRefresh(true);
        editor.scheduleRefresh(true);
        await settle();
        assert.equal(queries, 1);

        releaseQuery();
        hooks.executeCommand = async (command, parameters, options) => {
          const job = {
            job_id: `${command}-${submitted.length}`,
            status: "completed",
            result: { result: {} },
          };
          submitted.push({ command, parameters, intent: options?.intent });
          return job;
        };
        await settle();
        assert.equal(queries, 1);
        assert.equal(editor.busy, false);
        assert.equal(runtEntry.button.disabled, false);
        assert.equal(editor.refreshButton.disabled, false);
        assert.deepEqual(submitted.map((entry) => entry.command), ["trigger-runt"]);
        assert.ok(submitted.every((entry) => entry.intent === "readback"));
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(TRIGGER_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_editor_same_state_notifications_do_not_restart_group_readback() -> None:
    script = textwrap.dedent(TRIGGER_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        // Simulate the real app contract: every completed executeCommand ends
        // with a plain unforced refresh notification (app-level
        // scheduleEditorRead). The selected-command readback must not restart.
        env.selectedId = "trigger-edge-slope";
        let editor;
        hooks.executeCommand = async (command, parameters, options) => {
          if (submitted.length > 4) {
            throw new Error("Trigger readback refresh loop detected");
          }
          const job = {
            job_id: `${command}-${submitted.length}`,
            status: "completed",
            result: { result: {} },
          };
          submitted.push({ command, parameters, intent: options?.intent });
          editor.scheduleRefresh();
          return job;
        };
        editor = buildEditor();
        editor.scheduleRefresh();
        await settle();

        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.intent}`), [
          "trigger-edge-slope:readback",
        ]);
        assert.equal(editor.busy, false);
        assert.equal(editor.pendingRefresh, false);

        // A later genuine state change still triggers a fresh pass.
        submitted.length = 0;
        env.selectedId = "trigger-runt";
        editor.scheduleRefresh();
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), ["trigger-runt"]);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(TRIGGER_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_editor_apply_uses_setter_readback_without_extra_query() -> None:
    script = textwrap.dedent(TRIGGER_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        catalog.commands = [
          def("trigger-edge", "edge"),
          def("trigger-edge-source", "edge"),
        ];
        env.selectedId = "trigger-edge-source";
        let deferApply = true;
        let releaseApply;
        hooks.executeCommand = async (command, parameters, options) => {
          const job = {
            job_id: `${command}-${submitted.length}`,
            status: "completed",
            result: { result: {} },
          };
          submitted.push({ command, parameters, intent: options?.intent });
          if (options?.intent === "apply" && deferApply) {
            deferApply = false;
            return new Promise((resolve) => { releaseApply = () => resolve(job); });
          }
          return job;
        };
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        assert.equal(editor.entry.id, "trigger-edge-source");
        const sourceEntry = editor.entry;
        sourceEntry.form.valuesResult = { action: "set", source_channel: 2 };

        submitted.length = 0;
        sourceEntry.button.dispatch("click");
        await settle();
        assert.equal(editor.busy, true);
        releaseApply();
        await settle();

        // Exactly one write; the setter readback reconciles the form with
        // no extra query.
        assert.equal(editor.busy, false);
        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.intent}`), [
          "trigger-edge-source:apply",
        ]);
        assert.deepEqual(sourceEntry.form.syncCalls.at(-1), ["trigger-edge-source-0", false]);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(TRIGGER_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_trigger_setting_fields_help_descriptions_and_enum_labels_are_localized() -> None:
    trigger_commands = [entry for entry in COMMANDS if entry.get("editor") in {"trigger", "external-trigger"}]

    assert len(trigger_commands) == len(EXPECTED_TRIGGER_GROUPS)
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    for entry in trigger_commands:
        if entry["id"] in {"external-trigger-range", "trigger-edge-external-level"}:
            assert entry.get("browser_hidden") is True, entry["id"]
        else:
            assert entry.get("browser_hidden") is not True, entry["id"]
        assert f'"description.{entry["id"]}":' in english, entry["id"]
        assert f'"description.{entry["id"]}":' in chinese, entry["id"]
        for field in entry["fields"]:
            if field["name"] == "action":
                continue
            help_key = field.get("help_key")
            assert help_key, (entry["id"], field["name"])
            assert f'"help.{help_key}":' in english, (entry["id"], field["name"])
            assert f'"help.{help_key}":' in chinese, (entry["id"], field["name"])
    for key in ("enum.off", "enum.volts", "enum.amps"):
        assert f'"{key}":' in english, key
        assert f'"{key}":' in chinese, key


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_trigger_level_div_quick_fill(tmp_path: Path) -> None:
    catalog_json = json.dumps(command_catalog())
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.checked = false;
            this.className = "";
            this.textContent = "";
            this.type = "";
            this.value = "";
            this.multiple = false;
            this.options = [];
            this.style = {};
            this.attributes = {};
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) {
            for (const node of nodes) {
              node.remove();
              node.parent = this;
              this.children.push(node);
              if (node.tagName === "OPTION") this.options.push(node);
            }
          }
          remove() { if (this.parent) this.parent.children = this.parent.children.filter((n) => n !== this); this.parent = null; }
          setAttribute(k, v) { this.attributes[k] = String(v); }
          querySelector(sel) {
            const match = /^\[data-field="([^"]+)"\]$/.exec(sel || "");
            if (!match) return null;
            const find = (list) => {
              for (const node of list || []) {
                if (node.dataset && node.dataset.field === match[1]) return node;
                const found = find(node.children);
                if (found) return found;
              }
              return null;
            };
            return find(this.children);
          }
          querySelectorAll(sel) {
            const out = [];
            const collect = (list) => {
              for (const node of list || []) {
                if (node.dataset && node.dataset.field) out.push(node);
                collect(node.children);
              }
            };
            collect(this.children);
            if (sel === "[data-field]") return out;
            const match = /^\[data-field="([^"]+)"\]$/.exec(sel || "");
            if (match) return out.filter((node) => node.dataset.field === match[1]);
            return [];
          }
          closest() { return null; }
          get validity() { return { badInput: false }; }
          setCustomValidity() {}
          reportValidity() {}
          checkValidity() { return true; }
        }
        globalThis.Option = class {
          constructor(text, value) {
            this.tagName = "OPTION";
            this.textContent = text;
            this.value = String(value);
            this.selected = false;
            this.children = [];
            this.dataset = {};
          }
          remove() {}
        };
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.queueMicrotask = (fn) => { fn(); };
        // Template shapes mirror the composition contract only, not locale prose.
        const TEMPLATES = {
          "trigger.editor.divCurrent": "CH={{channel}}|S={{scale}}|O={{offset}}",
          "trigger.editor.divSelection": "D={{div}}|V={{value}}",
        };
        globalThis.translate = (key, values = {}) => {
          let text = TEMPLATES[key] || key;
          for (const [name, value] of Object.entries(values)) {
            text = text.replaceAll(`{{${name}}}`, String(value));
          }
          return text;
        };
        globalThis.hasTranslation = () => true;
        globalThis.formatEngineering = (value, unit) => `F:${String(value)}:${unit}`;

        const strip = (name) => fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static", name), "utf8",
        ).replace(/^import[^\n]*\r?\n/gm, "").replace(/^export /gm, "");
        let source = strip("command-form.js");
        source += "\nfunction applyNumericFieldConstraints(input, field) { if (field.minimum !== undefined) input.min = String(field.minimum); if (field.maximum !== undefined) input.max = String(field.maximum); }\n";
        source += strip("trigger-editor.js");
        source += "\nglobalThis.TriggerEditor = TriggerEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const commands = __CATALOG__;
        const catalog = {
          commands,
          supported: () => true,
          fieldsFor: (command) => command.fields || [],
          optionsFor: (field) => field.options || [],
          commandLabel: (command) => command.id,
        };
        const SUMMARY = [
          { channel: 1, scale: 0.5, range: 4, offset: 1.0, units: "volt" },
          { channel: 2, scale: 1, range: 8, offset: -0.5, units: "amp" },
        ];
        let summaryOverride = null;
        let selectedId = "trigger-edge-level";
        const calls = [];
        const hooks = {
          headerActions: new FakeNode("div"),
          contextKey: () => "ctx",
          mode: () => "live",
          selectedCommand: () => commands.find((command) => command.id === selectedId),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          executeCommand: async (id, parameters, options) => {
            calls.push([id, parameters, options?.intent]);
            if (id === "channel-summary") {
              return { status: "completed", result: { result: { channels: summaryOverride || SUMMARY } } };
            }
            if (id === "trigger-edge-level" && parameters.action === "set") {
              return { status: "completed", result: { result: { level_volts: parameters.level } } };
            }
            if (id === "trigger-edge-level") {
              return { status: "completed", result: { result: { level_volts: 0.4 } } };
            }
            return { status: "completed", result: { result: {} } };
          },
        };

        const drain = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
        };
        const findAll = (node, pred, out = []) => {
          for (const child of node.children || []) {
            if (pred(child)) out.push(child);
            findAll(child, pred, out);
          }
          return out;
        };

        const editor = new globalThis.TriggerEditor(new FakeNode("div"), catalog, hooks);
        await editor.refresh(true, true);
        await drain();
        const section = editor.sectionsHost.children[0];
        const slider = findAll(section, (node) => node.tagName === "INPUT" && node.type === "range")[0];
        const ticks = findAll(section, (node) => node.className === "div-slider-ticks")[0];
        const levelInput = () => editor.entry.form.container.querySelector('[data-field="level"]');
        const sourceInput = () => editor.entry.form.container.querySelector('[data-field="source_channel"]');
        const outputs = () => findAll(section, (node) => node.tagName === "OUTPUT");
        const infoText = () => outputs()[0].textContent;
        const selectionText = () => outputs()[1].textContent;
        const statusText = () => outputs()[2].textContent;

        // 1. Slider exposes the Div range but stays disabled before a successful read.
        assert.equal(slider.type, "range");
        assert.equal(slider.min, "-4");
        assert.equal(slider.max, "4");
        assert.equal(slider.step, "1");
        assert.equal(slider.value, "0");
        assert.equal(slider.disabled, true);
        assert.equal(slider.attributes["aria-label"], "trigger.editor.divHeading");
        assert.equal(ticks.children.length, 9);
        assert.deepEqual(
          ticks.children.map((tick) => tick.textContent),
          ["-4", "-3", "-2", "-1", "0", "+1", "+2", "+3", "+4"],
        );
        assert.equal(selectionText(), "");
        assert.equal(statusText(), "");
        assert.equal(levelInput().value, "0.4");
        assert.ok(!calls.some(([id]) => id === "channel-summary"));

        // 2. Picking a source then reading enables Div quick-fill for that channel.
        sourceInput().value = "1";
        sourceInput().dispatch("change");
        assert.equal(levelInput().value, "");
        assert.equal(slider.disabled, true);
        await editor.refresh(true, true);
        await drain();
        assert.deepEqual(calls.filter(([id]) => id === "channel-summary").length, 1);
        assert.equal(calls[calls.length - 1][0], "channel-summary");
        assert.equal(calls[calls.length - 1][2], "readback");
        assert.equal(slider.disabled, false);
        assert.equal(infoText(), "CH=1|S=F:0.5:V|O=F:1:V");

        // 3. Slider +2 on offset 1.0 V with 0.5 V/div fills 2 V without any write.
        const callsBeforeFill = calls.length;
        slider.value = "2";
        slider.dispatch("input");
        assert.equal(levelInput().value, "2");
        assert.equal(levelInput().dataset.dirty, "true");
        assert.equal(selectionText(), "D=+2|V=F:2:V");
        assert.equal(calls.length, callsBeforeFill);

        // 4. Manual level edits clear the quick-fill selection and reset the slider.
        levelInput().value = "0.75";
        levelInput().dispatch("input");
        assert.equal(selectionText(), "");
        assert.equal(slider.value, "0");
        assert.equal(levelInput().value, "0.75");
        assert.equal(slider.disabled, false);

        // 5. Switching source drops the draft and requires a fresh read.
        sourceInput().value = "2";
        sourceInput().dispatch("change");
        assert.equal(levelInput().value, "");
        assert.equal(slider.disabled, true);
        assert.equal(selectionText(), "");
        await editor.refresh(true, true);
        await drain();
        assert.equal(slider.disabled, true);
        assert.equal(statusText(), "trigger.editor.divReadIncomplete");

        // 6. An incomplete summary never enables the slider and never guesses.
        sourceInput().value = "1";
        sourceInput().dispatch("change");
        summaryOverride = [{ channel: 1, scale: 0.5, range: 4, offset: null, units: "volt" }];
        await editor.refresh(true, true);
        await drain();
        summaryOverride = null;
        assert.equal(slider.disabled, true);
        assert.equal(selectionText(), "");
        assert.equal(statusText(), "trigger.editor.divReadIncomplete");

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)

    harness_path = tmp_path / "trigger-level-div-harness.mjs"
    harness_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout
    assert json.loads(completed.stdout) == {"ok": True}


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_trigger_edge_div_coherence_keeps_draft_source(tmp_path: Path) -> None:
    catalog_json = json.dumps(command_catalog())
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.checked = false;
            this.className = "";
            this.textContent = "";
            this.type = "";
            this.value = "";
            this.multiple = false;
            this.options = [];
            this.style = {};
            this.attributes = {};
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) {
            for (const node of nodes) {
              node.remove();
              node.parent = this;
              this.children.push(node);
              if (node.tagName === "OPTION") this.options.push(node);
            }
          }
          remove() { if (this.parent) this.parent.children = this.parent.children.filter((n) => n !== this); this.parent = null; }
          setAttribute(k, v) { this.attributes[k] = String(v); }
          querySelector(sel) {
            const match = /^\[data-field="([^"]+)"\]$/.exec(sel || "");
            if (!match) return null;
            const find = (list) => {
              for (const node of list || []) {
                if (node.dataset && node.dataset.field === match[1]) return node;
                const found = find(node.children);
                if (found) return found;
              }
              return null;
            };
            return find(this.children);
          }
          querySelectorAll(sel) {
            const out = [];
            const collect = (list) => {
              for (const node of list || []) {
                if (node.dataset && node.dataset.field) out.push(node);
                collect(node.children);
              }
            };
            collect(this.children);
            if (sel === "[data-field]") return out;
            const match = /^\[data-field="([^"]+)"\]$/.exec(sel || "");
            if (match) return out.filter((node) => node.dataset.field === match[1]);
            return [];
          }
          closest() { return null; }
          get validity() { return { badInput: false }; }
          setCustomValidity() {}
          reportValidity() {}
          checkValidity() { return true; }
        }
        globalThis.Option = class {
          constructor(text, value) {
            this.tagName = "OPTION";
            this.textContent = text;
            this.value = String(value);
            this.selected = false;
            this.children = [];
            this.dataset = {};
          }
          remove() {}
        };
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.queueMicrotask = (fn) => { fn(); };
        // Template shapes mirror the composition contract only, not locale prose.
        const TEMPLATES = {
          "trigger.editor.divCurrent": "CH={{channel}}|S={{scale}}|O={{offset}}",
          "trigger.editor.divSelection": "D={{div}}|V={{value}}",
        };
        globalThis.translate = (key, values = {}) => {
          let text = TEMPLATES[key] || key;
          for (const [name, value] of Object.entries(values)) {
            text = text.replaceAll(`{{${name}}}`, String(value));
          }
          return text;
        };
        globalThis.hasTranslation = () => true;
        globalThis.formatEngineering = (value, unit) => `F:${String(value)}:${unit}`;

        const strip = (name) => fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static", name), "utf8",
        ).replace(/^import[^\n]*\r?\n/gm, "").replace(/^export /gm, "");
        let source = strip("command-form.js");
        source += "\nfunction applyNumericFieldConstraints(input, field) { if (field.minimum !== undefined) input.min = String(field.minimum); if (field.maximum !== undefined) input.max = String(field.maximum); }\n";
        source += strip("trigger-editor.js");
        source += "\nglobalThis.TriggerEditor = TriggerEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const commands = __CATALOG__;
        const catalog = {
          commands,
          supported: () => true,
          fieldsFor: (command) => command.fields || [],
          optionsFor: (field) => field.options || [],
          commandLabel: (command) => command.id,
        };
        const SUMMARY = [
          { channel: 1, scale: 0.5, range: 4, offset: 0.4, units: "volt" },
          { channel: 2, scale: 2, range: 16, offset: 10, units: "volt" },
        ];
        const selectedId = "trigger-edge";
        const calls = [];
        const hooks = {
          headerActions: new FakeNode("div"),
          contextKey: () => "ctx",
          mode: () => "live",
          selectedCommand: () => commands.find((command) => command.id === selectedId),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          executeCommand: async (id, parameters, options) => {
            calls.push([id, parameters, options?.intent]);
            if (id === "channel-summary") {
              return { status: "completed", result: { result: { channels: SUMMARY } } };
            }
            // The instrument still holds the old CH1 state; the query is not
            // source-scoped for trigger-edge.
            return { status: "completed", result: { result: { level_volts: 0.4 } } };
          },
        };

        const drain = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
        };
        const findAll = (node, pred, out = []) => {
          for (const child of node.children || []) {
            if (pred(child)) out.push(child);
            findAll(child, pred, out);
          }
          return out;
        };

        const editor = new globalThis.TriggerEditor(new FakeNode("div"), catalog, hooks);
        const edgeBurst = commands.find((command) => command.id === "trigger-edge-burst");
        assert.equal(editor.divQualifies(edgeBurst), true);
        await editor.refresh(true, true);
        await drain();
        const section = editor.sectionsHost.children[0];
        const slider = findAll(section, (node) => node.tagName === "INPUT" && node.type === "range")[0];
        const levelInput = () => editor.entry.form.container.querySelector('[data-field="level"]');
        const sourceInput = () => editor.entry.form.container.querySelector('[data-field="source_channel"]');
        const outputs = () => findAll(section, (node) => node.tagName === "OUTPUT");

        // Initial read fills the instrument level; no source draft exists yet.
        assert.equal(levelInput().value, "0.4");
        assert.equal(slider.disabled, true);
        assert.ok(!calls.some(([id]) => id === "channel-summary"));

        // Draft CH2 without applying, then read the stale CH1 instrument state.
        sourceInput().value = "2";
        sourceInput().dispatch("change");
        assert.equal(levelInput().value, "");
        await editor.refresh(true, true);
        await drain();
        // The draft source is kept, the stale CH1 level is not attributed to
        // it, and the CH2 Div context is still established.
        assert.equal(sourceInput().value, "2");
        assert.equal(levelInput().value, "");
        assert.equal(slider.disabled, false);
        assert.equal(outputs()[0].textContent, "CH=2|S=F:2:V|O=F:10:V");
        assert.deepEqual(calls.filter(([id]) => id === "channel-summary").length, 1);

        // The slider computes from the CH2 context and never writes.
        const callsBeforeFill = calls.length;
        slider.value = "1";
        slider.dispatch("input");
        assert.equal(levelInput().value, "12");
        assert.equal(calls.length, callsBeforeFill);

        // A manually typed dirty level survives the next stale readback.
        levelInput().value = "1.25";
        levelInput().dispatch("input");
        await editor.refresh(true, true);
        await drain();
        assert.equal(sourceInput().value, "2");
        assert.equal(levelInput().value, "1.25");
        assert.equal(slider.disabled, false);

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)

    harness_path = tmp_path / "trigger-edge-div-coherence-harness.mjs"
    harness_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(harness_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout
    assert json.loads(completed.stdout) == {"ok": True}
