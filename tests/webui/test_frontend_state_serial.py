from __future__ import annotations

import json
import shutil
import subprocess
import textwrap

import pytest

from scopes_tool_webui.command_catalog import command_catalog

from tests.webui._frontend_state_test_support import (
    STATIC_ROOT,
    NUMERIC_INPUT_PATH,
    read_static,
    extract_function,
)

_SERIAL_REAL_FORM_HARNESS = textwrap.dedent(
    r'''
    import assert from "node:assert/strict";
    import fs from "node:fs";

    function datasetKeyName(name) {
      return name.split("-").map((part, index) => (
        index === 0 ? part : part.charAt(0).toUpperCase() + part.slice(1)
      )).join("");
    }
    function matchesAttributeSelector(node, selector) {
      const match = selector.match(/^\[data-([a-z-]+)(?:="([^"]*)")?\]$/);
      if (!match || !node || !node.dataset) return false;
      const actual = node.dataset[datasetKeyName(match[1])];
      if (match[2] === undefined) return actual !== undefined;
      return String(actual) === match[2];
    }

    class FakeNode {
      constructor(tag = "div") {
        this.tagName = tag.toUpperCase();
        this.children = [];
        this.parentNode = null;
        this.dataset = {};
        this.listeners = {};
        this.attributes = {};
        this.hidden = false;
        this.disabled = false;
        this.required = false;
        this.checked = false;
        this.multiple = false;
        this.value = "";
        this.type = "";
        this.min = "";
        this.max = "";
        this.step = "";
        this.textContent = "";
        this.className = "";
        this.options = [];
        this.validity = { badInput: false };
        this.reported = false;
        this.customMessage = "";
        this.classList = { add: () => {}, remove: () => {}, contains: () => false };
      }
      setAttribute(name, value) { this.attributes[name] = String(value); }
      getAttribute(name) { return this.attributes[name]; }
      addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
      dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
      replaceChildren(...nodes) { this.children = []; this.options = []; this.append(...nodes); }
      append(...nodes) {
        for (const node of nodes) {
          if (!node || typeof node !== "object") continue;
          this.children.push(node);
          node.parentNode = this;
          if (this.tagName === "SELECT" && node.tagName === "OPTION") this.options.push(node);
        }
      }
      closest(selector) {
        let node = this;
        while (node) {
          if (matchesAttributeSelector(node, selector)) return node;
          node = node.parentNode;
        }
        return null;
      }
      querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
      querySelectorAll(selector) {
        const matches = [];
        const visit = (node) => {
          for (const child of node?.children || []) {
            if (matchesAttributeSelector(child, selector)) matches.push(child);
            visit(child);
          }
        };
        visit(this);
        return matches;
      }
      checkValidity() {
        if (this.required && String(this.value ?? "") === "") return false;
        if (this.type === "number" && String(this.value ?? "") !== "") {
          const num = Number(this.value);
          if (!Number.isFinite(num)) return false;
          if (this.min !== "" && this.min !== undefined && num < Number(this.min)) return false;
          if (this.max !== "" && this.max !== undefined && num > Number(this.max)) return false;
        }
        return true;
      }
      reportValidity() { this.reported = true; return this.checkValidity(); }
      setCustomValidity(message) { this.customMessage = String(message); }
    }
    globalThis.document = { createElement: (tag) => new FakeNode(tag) };
    globalThis.Option = function Option(text, value) {
      const option = new FakeNode("option");
      option.textContent = text;
      option.value = String(value);
      return option;
    };
    globalThis.window = { confirm: () => true };

    const source = [
      "let runtimeLocale = \"en\";",
      fs.readFileSync(process.argv[4], "utf8"),
      fs.readFileSync(process.argv[5], "utf8"),
      "const testDicts = { en, zhTW, \"zh-TW\": zhTW };",
      "const translate = (key, values = {}) => {",
      "  const table = testDicts[runtimeLocale] || {};",
      "  let text = Object.prototype.hasOwnProperty.call(table, key) ? table[key] : key;",
      "  for (const [name, value] of Object.entries(values)) {",
      "    text = String(text).split(\"{\" + name + \"}\").join(String(value));",
      "  }",
      "  return text;",
      "};",
      "const hasTranslation = (key) => Object.prototype.hasOwnProperty.call(testDicts[runtimeLocale] || {}, key);",
      "globalThis.setRuntimeLocale = (value) => { runtimeLocale = value; };",
      fs.readFileSync(process.argv[3], "utf8"),
      fs.readFileSync(process.argv[2], "utf8"),
      fs.readFileSync(process.argv[1], "utf8"),
    ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
      .replace(/^export function /gm, "function ")
      .replace(/^export class /gm, "class ")
      .replace(/^export const /gm, "const ")
      + "\nglobalThis.serialApi = { SerialTriggerEditor, createSerialEditorController, CommandForm, testDicts };";
    await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
    const { SerialTriggerEditor, createSerialEditorController, testDicts } = globalThis.serialApi;

    const settle = async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
    };

    const triggerDefinition = JSON.parse(process.argv[6]);
    const catalog = {
      commands: [triggerDefinition],
      fieldsFor: (definition) => definition.fields,
      optionsFor: (field) => field.options || [],
      description: () => "",
    };
    const submitted = [];
    const respond = (command, parameters) => {
      if (command === "serial-mode") {
        return {
          job_id: "mode-1",
          status: "completed",
          result: { result: { mode: { bus: parameters.bus ?? 1, mode: "i2c", raw_mode: "I2C" } } },
        };
      }
      if (command === "serial-trigger-i2c") {
        return {
          job_id: "trigger-1",
          status: "completed",
          result: { result: { trigger: { bus: parameters.bus ?? 1 } } },
        };
      }
      return { job_id: `${command}-1`, status: "completed", result: { result: {} } };
    };
    const hooks = {
      executeCommand: async (command, parameters) => {
        submitted.push({ command, parameters });
        return respond(command, parameters);
      },
      isAvailable: () => true,
      isExecutionBusy: () => false,
      contextKey: () => "ctx",
      headerActions: new FakeNode(),
      modelInfo: () => ({ supported: true, maxBus: 2, protocols: ["uart", "i2c", "spi", "can"] }),
    };
    const controller = createSerialEditorController({
      execute: hooks.executeCommand,
      confirmDiscard: () => true,
      available: () => true,
    });
    const editor = new SerialTriggerEditor(new FakeNode(), catalog, hooks, controller);

    async function bootTriggerForm() {
      editor.schedulePresentation();
      await settle();
      assert.deepEqual(submitted, []);
      editor.refreshButton.dispatch("click");
      await settle();
      assert.deepEqual(submitted.map((entry) => entry.command), ["serial-mode", "serial-trigger-i2c"]);
      const readCalls = submitted.length;
      assert.ok(editor.triggerForm);
      assert.equal(editor.triggerForm.command.id, "serial-trigger-i2c");
      assert.equal(editor.applyTriggerButton.disabled, false);
      return {
        typeInput: editor.triggerForm.container.querySelector('[data-field="type"]'),
        addressInput: editor.triggerForm.container.querySelector('[data-field="address"]'),
        dataInput: editor.triggerForm.container.querySelector('[data-field="data"]'),
        readCalls,
      };
    }
    '''
)

def test_serial_workspaces_replace_generic_form_with_task_navigation() -> None:
    app_source = read_static("app.js")
    bootstrap_source = read_static("editor-bootstrap.js")
    html = read_static("index.html")
    editor_source = read_static("serial-editor.js")
    styles_source = read_static("styles.css")

    assert 'import { SerialDecodeEditor, SerialListerEditor, SerialTriggerEditor, createSerialEditorController } from "/static/serial-editor.js";' in bootstrap_source
    assert 'id="form-heading"' in html
    assert 'id="serial-decode-editor" class="serial-editor" hidden' in html
    assert 'id="serial-trigger-editor" class="serial-editor" hidden' in html
    assert 'id="serial-lister-editor" class="serial-editor" hidden' in html
    assert 'id="serial-editor"' not in html
    routing = extract_function(bootstrap_source, "function editorKindFor(command)")
    assert "command?.editor" in routing
    assert "editorRenderers[kind]" in routing
    renderer_map = bootstrap_source.split("const editorRenderers = {", 1)[1].split("};", 1)[0]
    assert '"serial-decode": () => serialDecodeEditor,' in renderer_map
    assert '"serial-trigger": () => serialTriggerEditor,' in renderer_map
    assert '"serial-lister": () => serialListerEditor,' in renderer_map
    assert "serial: () => serialEditor," not in renderer_map
    assert "function scheduleEditorRead()" not in app_source
    presentation = extract_function(app_source, "function syncEditorPresentation(editorKind)")
    assert "serialDecodeEditor?.schedulePresentation();" in presentation
    assert "serialTriggerEditor?.schedulePresentation();" in presentation
    assert "serialListerEditor?.schedulePresentation();" in presentation
    assert "serialEditor?.schedulePresentation();" not in presentation
    assert "elements.formHeading.hidden = (editorOwned && ![\"channel-display\", \"timebase-position\", \"channel-scale-range\", \"external-trigger\"].includes(editorKind)) || systemInformationSelected;" in app_source
    assert "elements.form.hidden = editorOwned || systemInformationSelected;" in app_source
    assert 'elements.serialDecodeEditor.hidden = editorKind !== "serial-decode";' in app_source
    assert 'elements.serialTriggerEditor.hidden = editorKind !== "serial-trigger";' in app_source
    assert 'elements.serialListerEditor.hidden = editorKind !== "serial-lister";' in app_source
    assert "syncWorkspaceHeaderActions(editorKind);" in app_source
    assert "serialDecodeEditor?.applyDecodeButton" in app_source
    assert "serialTriggerEditor?.applyTriggerButton" in app_source
    assert 'className = `${primary ? "primary" : "secondary"} serial-editor-action`' in editor_source
    assert "SERIAL_EDITOR_COMMANDS" not in app_source
    assert "serialDecodeEditor?.rerender();" in app_source
    assert "serialTriggerEditor?.rerender();" in app_source
    assert "serialListerEditor?.rerender();" in app_source
    assert "renderPcOutputNote: (note)" in bootstrap_source
    assert "serial-lister-row" in editor_source
    assert editor_source.count('className = "command-form";') >= 5
    assert ".serial-lister-row { display: grid; gap: 8px; width: 50%; }" in styles_source
    assert ".serial-lister-row > .serial-editor-action { justify-self: start; }" in styles_source
    assert ".serial-lister-row > .command-form" in styles_source
    assert ".serial-lister-row { width: 100%; align-items: stretch; }" in styles_source
    assert 'translate(`${editorKind}.editor.title`)' in app_source
    for command_id in (
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
    ):
        assert f'"{command_id}"' in editor_source

    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    for key in (
        "serial.editor.busOption",
        "serial.editor.busHelp",
        "serial.editor.protocol",
        "serial.editor.applyTrigger",
        "serial.editor.export",
        "serial.editor.triggerSection",
        "serial.editor.listerSection",
        "serial.editor.unsupported",
        "serial.editor.discardConfirm",
        "serial-decode.editor.title",
        "serial-trigger.editor.title",
        "serial-lister.editor.title",
        "serial.decode.readSettings",
        "serial.decode.applySettings",
        "serial.decode.currentProtocol",
        "serial.decode.currentProtocolHelp",
        "serial.decode.protocolToApply",
        "serial.decode.protocolHelp",
        "serial.decode.readbackHint",
        "serial.decode.pendingProtocol",
        "serial.decode.unreadConfiguration",
        "serial.trigger.readSettings",
        "serial.trigger.currentProtocol",
        "serial.trigger.currentProtocolHelp",
        "serial.trigger.unreadConfiguration",
        "serial.lister.readSettings",
        "serial.lister.usage",
        "serial.lister.unreadPrerequisite",
        "serial.lister.selectDisplay",
        "serial.lister.unknownPrerequisite",
        "serial.lister.decodeDisabled",
        "serial.lister.allDecodeDisabled",
        "serial.lister.partialPrerequisite",
        "serial.lister.applyDisplayFirst",
    ):
        assert f'"{key}":' in english, key
        assert f'"{key}":' in chinese, key
    for key in (
        "serial.editor.title",
        "serial.editor.applyMode",
        "serial.editor.applyDisplay",
        "serial.editor.applyConfiguration",
    ):
        assert f'"{key}":' not in english, key
        assert f'"{key}":' not in chinese, key

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_serial_editor_controller_sequences_reads_and_discard_gating() -> None:
    serial_editor_path = STATIC_ROOT / "serial-editor.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.serialApi = { SERIAL_EDITOR_COMMANDS, configCommandFor, triggerCommandFor, busOptions, createSerialEditorController };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const {
          SERIAL_EDITOR_COMMANDS,
          configCommandFor,
          triggerCommandFor,
          busOptions,
          createSerialEditorController,
        } = globalThis.serialApi;

        const settle = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
          await new Promise((resolve) => setTimeout(resolve, 0));
        };

        const makeHarness = ({
          initialMode = "can",
          maxBus = 1,
          confirmResult = true,
          setTakesEffect = true,
          listerDisplay = "off",
          serialDisplays = { 1: true, 2: true },
          failedSerialDisplays = new Set(),
        } = {}) => {
          const submitted = [];
          let currentMode = initialMode;
          let modeQueryFails = false;
          const respond = (command, parameters) => {
            if (command === "serial-mode") {
              if (parameters.action === "query" && modeQueryFails) {
                return {
                  job_id: `mode-${submitted.length}`,
                  status: "failed",
                  error: "temporary VISA failure",
                };
              }
              if (parameters.action === "set" && setTakesEffect) currentMode = parameters.mode;
              return {
                job_id: `mode-${submitted.length}`,
                status: "completed",
                result: { result: { mode: {
                  bus: parameters.bus,
                  mode: currentMode,
                  raw_mode: String(currentMode).toUpperCase(),
                } } },
              };
            }
            if (command === "serial-display") {
              if (failedSerialDisplays.has(parameters.bus)) {
                return {
                  job_id: `display-${submitted.length}`,
                  status: "failed",
                  error: "temporary VISA failure",
                };
              }
              return {
                job_id: `display-${submitted.length}`,
                status: "completed",
                result: { result: { display: {
                  bus: parameters.bus,
                  enabled: serialDisplays[parameters.bus] ?? false,
                } } },
              };
            }
            if (command.startsWith("serial-trigger-")) {
              const triggerProtocol = command.replace("serial-trigger-", "");
              return {
                job_id: `trigger-${submitted.length}`,
                status: "completed",
                result: { result: { trigger: {
                  protocol: triggerProtocol,
                  bus: parameters.bus,
                  mode: currentMode,
                  selected: true,
                } } },
              };
            }
            if (command === "serial-lister-display" || command === "serial-lister-reference") {
              const slot = command === "serial-lister-display" ? "display" : "reference";
              const value = slot === "display"
                ? (parameters.display ?? "off")
                : (parameters.reference ?? "trigger");
              return {
                job_id: `${slot}-${submitted.length}`,
                status: "completed",
                result: { result: { [slot]: { [slot]: value } } },
              };
            }
            if (command === "serial-lister-query") {
              return {
                job_id: `lister-${submitted.length}`,
                status: "completed",
                result: { result: { lister: {
                  display: listerDisplay,
                  reference: "trigger",
                } } },
              };
            }
            const protocol = command.replace("serial-", "");
            return {
              job_id: `${protocol}-${submitted.length}`,
              status: "completed",
              result: { result: { [protocol]: { bus: parameters.bus } } },
            };
          };
          const execute = async (command, parameters, options) => {
            submitted.push({ command, action: parameters.action, intent: options?.intent, parameters });
            return respond(command, parameters);
          };
          const confirmations = [];
          let confirmValue = confirmResult;
          const controller = createSerialEditorController({
            execute,
            confirmDiscard: () => { confirmations.push("asked"); return confirmValue; },
            available: () => true,
          });
          controller.reset({
            maxBus,
            protocolChoices: ["uart", "i2c", "spi", "can"],
          });
          return {
            controller,
            submitted,
            confirmations,
              setCurrentMode: (mode) => { currentMode = mode; },
              setModeQueryFails: (value) => { modeQueryFails = Boolean(value); },
              setConfirmResult: (value) => { confirmValue = Boolean(value); },
              setListerDisplay: (value) => { listerDisplay = value; },
            };
        };

        const commandsOf = (harness) =>
          harness.submitted.map((entry) => `${entry.command}${entry.action ? `:${entry.action}` : ""}`);

        const decodeRefreshCommands = (configCommand) => [
          "serial-mode:query",
          "serial-display:query",
          `${configCommand}:query`,
        ];
        const triggerRefreshCommands = (triggerCommand) => [
          "serial-mode:query",
          `${triggerCommand}:query`,
        ];
        const listerRefreshCommands = (maxBus) => [
          "serial-lister-query",
          ...Array.from({ length: maxBus }, () => "serial-display:query"),
        ];

        assert.deepEqual(busOptions(1), [1]);
        assert.deepEqual(busOptions(2), [1, 2]);
        assert.equal(configCommandFor("uart"), "serial-uart");
        assert.equal(configCommandFor("i2c"), "serial-i2c");
        assert.equal(configCommandFor("spi"), "serial-spi");
        assert.equal(configCommandFor("can"), "serial-can");
        assert.equal(configCommandFor("lin"), null);
        assert.equal(configCommandFor(null), null);
        assert.equal(triggerCommandFor("uart"), "serial-trigger-uart");
        assert.equal(triggerCommandFor("i2c"), "serial-trigger-i2c");
        assert.equal(triggerCommandFor("spi"), "serial-trigger-spi");
        assert.equal(triggerCommandFor("can"), "serial-trigger-can");
        assert.equal(triggerCommandFor("lin"), null);
        assert.equal(triggerCommandFor(null), null);
        assert.equal(SERIAL_EDITOR_COMMANDS.includes("serial-query"), false);
        assert.equal(SERIAL_EDITOR_COMMANDS.includes("serial-search-uart"), false);
        assert.equal(SERIAL_EDITOR_COMMANDS.includes("serial-trigger-can"), true);
        assert.equal(SERIAL_EDITOR_COMMANDS.includes("serial-lister-export"), true);

        {
          const single = makeHarness({ initialMode: "uart", maxBus: 1 });
          single.controller.selectBus(2);
          await settle();
          assert.deepEqual(single.submitted, []);
          assert.equal(single.controller.state.bus, 1);
        }

        {
          const dual = makeHarness({ initialMode: "can", maxBus: 2 });
          await dual.controller.refreshDecode();
          await settle();
          assert.deepEqual(commandsOf(dual), decodeRefreshCommands("serial-can"));
          dual.controller.selectBus(2);
          await settle();
          assert.equal(dual.controller.state.bus, 2);
          assert.deepEqual(commandsOf(dual).slice(3), []);
          await dual.controller.refreshDecode();
          await settle();
          assert.deepEqual(commandsOf(dual).slice(3), decodeRefreshCommands("serial-can"));
          assert.equal(dual.controller.state.formEpoch, 2);
        }

        {
          const triggerBus = makeHarness({ initialMode: "can", maxBus: 2 });
          await triggerBus.controller.refreshTrigger();
          await settle();
          assert.deepEqual(commandsOf(triggerBus), triggerRefreshCommands("serial-trigger-can"));
          await triggerBus.controller.refreshLister();
          await settle();
          assert.deepEqual(commandsOf(triggerBus).slice(2), listerRefreshCommands(2));
        }

        {
          const canBus = makeHarness({ initialMode: "can" });
          await canBus.controller.refreshDecode();
          await settle();
          const canCommands = commandsOf(canBus);
          assert.equal(canCommands.includes("serial-uart:query"), false);
          assert.equal(canCommands.includes("serial-lister-query"), false);
          assert.deepEqual(canCommands, decodeRefreshCommands("serial-can"));
          assert.equal(canCommands.some((entry) =>
            entry.startsWith("serial-trigger-")
            && entry !== "serial-trigger-can:query"), false);
          assert.equal(canBus.controller.state.configCommand, "serial-can");
          assert.equal(canBus.controller.state.triggerCommand, "serial-trigger-can");
          assert.equal(canBus.controller.state.selectedProtocol, "can");
        }

        {
          const uartBus = makeHarness({ initialMode: "uart" });
          await uartBus.controller.refreshDecode();
          await settle();
          assert.deepEqual(commandsOf(uartBus), decodeRefreshCommands("serial-uart"));
          assert.equal(uartBus.controller.state.configCommand, "serial-uart");
          assert.equal(uartBus.controller.state.triggerCommand, "serial-trigger-uart");
        }

        {
          for (const protocol of ["i2c", "spi"]) {
            const scoped = makeHarness({ initialMode: protocol });
            await scoped.controller.refreshDecode();
            await settle();
            assert.deepEqual(
              commandsOf(scoped),
              decodeRefreshCommands(`serial-${protocol}`),
              protocol,
            );
          }
        }

        {
          const linBus = makeHarness({ initialMode: "lin" });
          await linBus.controller.refreshDecode();
          await settle();
          assert.deepEqual(commandsOf(linBus), [
            "serial-mode:query",
            "serial-display:query",
          ]);
          assert.equal(commandsOf(linBus).some((entry) =>
            entry.startsWith("serial-trigger-")), false);
          assert.equal(linBus.controller.state.supported, false);
          assert.equal(linBus.controller.state.triggerCommand, null);
          assert.equal(linBus.controller.state.currentLabel, "LIN");
          assert.equal(linBus.controller.state.selectedProtocol, null);
              assert.equal(linBus.controller.state.protocolPending, false);
              linBus.controller.selectProtocol("spi");
          assert.equal(linBus.controller.state.selectedProtocol, "spi");
          assert.equal(linBus.controller.state.protocolPending, true);
          await linBus.controller.refreshTrigger();
          await settle();
          assert.deepEqual(commandsOf(linBus).slice(2), ["serial-mode:query"]);
        }

        {
          const switched = makeHarness({ initialMode: "uart" });
          await switched.controller.refreshDecode();
          await settle();
          switched.controller.selectProtocol("can");
          await settle();
          assert.deepEqual(switched.confirmations, []);
          assert.equal(switched.controller.state.protocolPending, true);
          switched.controller.setDirty("config", true);
          await switched.controller.applyDecode({}, { source: "channel1" });
          await settle();
          const commands = commandsOf(switched);
          assert.deepEqual(commands, [
            "serial-mode:query",
            "serial-display:query",
            "serial-uart:query",
            "serial-mode:set",
            "serial-mode:query",
            "serial-can:set",
            "serial-mode:query",
            "serial-display:query",
            "serial-can:query",
          ]);
          assert.equal(switched.controller.state.confirmedMode, "can");
          assert.equal(switched.controller.state.protocolPending, false);
          assert.equal(switched.controller.state.dirtyConfig, false);
          assert.equal(switched.controller.state.dirtyTrigger, false);
          assert.equal(switched.controller.state.triggerCommand, "serial-trigger-can");
          const setEntry = switched.submitted[3];
          assert.equal(setEntry.intent, "apply");
          assert.equal(setEntry.action, "set");
          assert.equal(setEntry.parameters.mode, "can");
          const configEntry = switched.submitted[5];
          assert.equal(configEntry.command, "serial-can");
          assert.equal(configEntry.action, "set");
          assert.equal(configEntry.parameters.source, "channel1");
          const readEntry = switched.submitted[6];
          assert.equal(readEntry.intent, "readback");
          switched.controller.selectProtocol("can");
          await settle();
          assert.equal(switched.controller.state.protocolPending, false);
          assert.deepEqual(switched.confirmations, []);
          assert.equal(switched.submitted.length, 9);
        }

        {
          const mismatch = makeHarness({ initialMode: "can", setTakesEffect: false });
          await mismatch.controller.refreshDecode();
          await settle();
          mismatch.controller.selectProtocol("uart");
          mismatch.controller.setDirty("config", true);
          await mismatch.controller.applyDecode({}, { baud_rate: 115200 });
          await settle();
          const commands = commandsOf(mismatch);
          assert.deepEqual(commands, [
            "serial-mode:query",
            "serial-display:query",
            "serial-can:query",
            "serial-mode:set",
            "serial-mode:query",
            "serial-display:query",
            "serial-can:query",
          ]);
          assert.equal(commands.includes("serial-uart:set"), false);
          assert.equal(commands.includes("serial-uart:query"), false);
          assert.equal(mismatch.controller.state.confirmedMode, "can");
          assert.equal(mismatch.controller.state.selectedProtocol, "uart");
          assert.equal(mismatch.controller.state.protocolPending, true);
        }

        {
          const cancelled = makeHarness({ initialMode: "uart", maxBus: 2, confirmResult: false });
          await cancelled.controller.refreshDecode();
          await settle();
          const before = cancelled.submitted.length;
          const epochBefore = cancelled.controller.state.formEpoch;
          cancelled.controller.setDirty("trigger", true);
          cancelled.controller.selectProtocol("can");
          await cancelled.controller.applyDecode({}, { source: "channel1" });
          await settle();
          assert.deepEqual(cancelled.confirmations, ["asked"]);
          assert.equal(cancelled.controller.state.confirmedMode, "uart");
          assert.equal(cancelled.controller.state.dirtyTrigger, true);
          assert.equal(cancelled.controller.state.protocolPending, true);
          assert.equal(cancelled.submitted.length, before);
          assert.equal(cancelled.controller.state.formEpoch, epochBefore);
        }

        {
          const triggerDraft = makeHarness({ initialMode: "can" });
          await triggerDraft.controller.refreshTrigger();
          await settle();
          const epochBefore = triggerDraft.controller.state.formEpoch;
          triggerDraft.controller.setDirty("trigger", true);
          triggerDraft.controller.selectProtocol("uart");
          await settle();
          assert.deepEqual(triggerDraft.confirmations, []);
          assert.equal(triggerDraft.controller.state.dirtyTrigger, true);
          assert.equal(triggerDraft.controller.state.formEpoch, epochBefore);
          assert.equal(triggerDraft.controller.state.protocolPending, false);
          assert.equal(triggerDraft.controller.state.selectedProtocol, null);
          assert.equal(triggerDraft.controller.state.decodeModeReady, false);
          assert.equal(triggerDraft.controller.state.triggerModeReady, true);
          assert.deepEqual(commandsOf(triggerDraft), [
            "serial-mode:query",
            "serial-trigger-can:query",
          ]);
        }

        {
          const pendingBus = makeHarness({ initialMode: "can", maxBus: 2 });
          await pendingBus.controller.refreshDecode();
          await settle();
          pendingBus.controller.selectProtocol("uart");
          await pendingBus.controller.refreshTrigger();
          await settle();
          assert.deepEqual(pendingBus.confirmations, []);
          assert.equal(pendingBus.controller.state.confirmedMode, "can");
          assert.equal(pendingBus.controller.state.selectedProtocol, "uart");
          assert.equal(pendingBus.controller.state.protocolPending, true);
          assert.deepEqual(commandsOf(pendingBus).slice(3), [
            "serial-mode:query",
            "serial-trigger-can:query",
          ]);
          pendingBus.controller.selectBus(2);
          await settle();
          assert.deepEqual(pendingBus.confirmations, ["asked"]);
          assert.equal(pendingBus.controller.state.bus, 2);
          assert.equal(pendingBus.controller.state.protocolPending, false);
          assert.equal(pendingBus.controller.state.selectedProtocol, null);
        }

        {
          const linDisplay = makeHarness({ initialMode: "lin" });
          await linDisplay.controller.refreshDecode();
          await settle();
          assert.equal(linDisplay.controller.state.selectedProtocol, null);
          assert.equal(linDisplay.controller.state.protocolPending, false);
          linDisplay.controller.setDirty("display", true);
          await linDisplay.controller.applyDecode({ enabled: true }, {});
          await settle();
          assert.deepEqual(commandsOf(linDisplay), [
            "serial-mode:query",
            "serial-display:query",
            "serial-display:set",
            "serial-mode:query",
            "serial-display:query",
          ]);
          assert.equal(commandsOf(linDisplay).some((entry) => entry === "serial-mode:set"), false);
          assert.equal(linDisplay.controller.state.confirmedMode, "lin");
          linDisplay.controller.selectProtocol("uart");
          await linDisplay.controller.applyDecode({}, {});
          await settle();
          const after = commandsOf(linDisplay);
          assert.equal(after.includes("serial-mode:set"), true);
          assert.equal(after.some((entry) => entry === "serial-uart:set"), false);
          assert.equal(linDisplay.controller.state.confirmedMode, "uart");
          assert.equal(linDisplay.controller.state.protocolPending, false);
        }

        {
          const submitted = [];
          let releaseDisplay = null;
          let busyDuringTrigger = "unset";
          let ctrl = null;
          const execute = async (command, parameters) => {
            submitted.push(command);
            if (command === "serial-display" && releaseDisplay === null) {
              let release = null;
              const gate = new Promise((resolve) => { release = resolve; });
              releaseDisplay = release;
              await gate;
            }
            if (command === "serial-trigger-can") busyDuringTrigger = ctrl.state.busy;
            const completed = (suffix, result) => ({
              job_id: `${suffix}-${submitted.length}`,
              status: "completed",
              result: { result },
            });
            if (command === "serial-mode") {
              return completed("mode", { mode: { bus: 1, mode: "can", raw_mode: "CAN" } });
            }
            if (command === "serial-display") {
              return completed("display", { display: { bus: 1, enabled: true } });
            }
            if (command === "serial-can") {
              return completed("can", { can: { bus: 1 } });
            }
            return completed("trigger", { trigger: { protocol: "can", bus: 1, mode: "can", selected: true } });
          };
          ctrl = createSerialEditorController({
            execute,
            confirmDiscard: () => true,
            available: () => true,
          });
          ctrl.reset({ maxBus: 1, protocolChoices: ["uart", "i2c", "spi", "can"] });
          const decodePromise = ctrl.refreshDecode();
          await settle();
          assert.deepEqual(submitted, ["serial-mode", "serial-display"]);
          await ctrl.refreshTrigger();
          assert.deepEqual(submitted, ["serial-mode", "serial-display"]);
          releaseDisplay();
          await decodePromise;
          await settle();
          assert.deepEqual(submitted, [
            "serial-mode",
            "serial-display",
            "serial-can",
            "serial-mode",
            "serial-trigger-can",
          ]);
          assert.equal(busyDuringTrigger, true);
          assert.equal(ctrl.state.busy, false);
        }

        {
          const submitted = [];
          let releaseModeSet = null;
          let busyDuringTrigger = "unset";
          let ctrl = null;
          let currentMode = "can";
          const execute = async (command, parameters) => {
            submitted.push(`${command}:${parameters.action}`);
            if (command === "serial-mode" && parameters.action === "set" && releaseModeSet === null) {
              let release = null;
              const gate = new Promise((resolve) => { release = resolve; });
              releaseModeSet = release;
              await gate;
              currentMode = parameters.mode;
            }
            if (command === "serial-trigger-uart") busyDuringTrigger = ctrl.state.busy;
            return {
              job_id: `job-${submitted.length}`,
              status: "completed",
              result: { result: {
                mode: { bus: 1, mode: currentMode, raw_mode: String(currentMode).toUpperCase() },
                display: { bus: 1, enabled: true },
                uart: { bus: 1 },
              } },
            };
          };
          ctrl = createSerialEditorController({
            execute,
            confirmDiscard: () => true,
            available: () => true,
          });
          ctrl.reset({ maxBus: 1, protocolChoices: ["uart", "i2c", "spi", "can"] });
          await ctrl.refreshDecode();
          await settle();
          ctrl.selectProtocol("uart");
          const applyPromise = ctrl.applyDecode({}, {});
          await settle();
          assert.deepEqual(submitted.slice(3), ["serial-mode:set"]);
          await ctrl.refreshTrigger();
          assert.deepEqual(submitted.slice(3), ["serial-mode:set"]);
          releaseModeSet();
          await applyPromise;
          await settle();
          assert.deepEqual(submitted.slice(3), [
            "serial-mode:set",
            "serial-mode:query",
            "serial-display:query",
            "serial-uart:query",
            "serial-mode:query",
            "serial-trigger-uart:query",
          ]);
          assert.equal(busyDuringTrigger, true);
          assert.equal(ctrl.state.busy, false);
        }

        {
          const idle = makeHarness({ initialMode: "can" });
          await idle.controller.refreshDecode();
          await settle();
          idle.controller.selectProtocol("can");
          await idle.controller.applyDecode({}, {});
          await settle();
          assert.deepEqual(idle.confirmations, []);
          assert.equal(idle.submitted.length, 3);
        }

        {
          const dualModes = makeHarness({
            initialMode: "can",
            maxBus: 2,
          });
          await dualModes.controller.refreshDecode();
          await settle();
          assert.equal(dualModes.controller.state.selectedProtocol, "can");
          dualModes.setCurrentMode("uart");
          dualModes.controller.selectBus(2);
          await settle();
          assert.equal(dualModes.controller.state.confirmedMode, null);
          await dualModes.controller.refreshDecode();
          await settle();
          assert.equal(dualModes.controller.state.confirmedMode, "uart");
          assert.equal(dualModes.controller.state.selectedProtocol, "uart");
        }

        {
          const displayOnly = makeHarness({ initialMode: "can" });
          await displayOnly.controller.refreshDecode();
          await settle();
          displayOnly.controller.setDirty("display", true);
          await displayOnly.controller.applyDecode({ enabled: true }, {});
          await settle();
          assert.deepEqual(displayOnly.confirmations, []);
          assert.equal(displayOnly.controller.state.dirtyDisplay, false);
          const commands = commandsOf(displayOnly);
          assert.deepEqual(commands, [
            "serial-mode:query",
            "serial-display:query",
            "serial-can:query",
            "serial-display:set",
            "serial-mode:query",
            "serial-display:query",
            "serial-can:query",
          ]);
        }

        {
          const external = makeHarness({ initialMode: "uart" });
          await external.controller.refreshDecode();
          await settle();
          external.setCurrentMode("can");
          external.controller.setDirty("config", true);
          await external.controller.applyDecode({}, { baud_rate: 115200 });
          await settle();
          const tail = commandsOf(external).slice(3);
          assert.equal(tail[0], "serial-mode:query");
          assert.equal(tail.some((entry) => entry === "serial-uart:set"), false);
          assert.deepEqual(tail.slice(1), [
            "serial-mode:query",
            "serial-display:query",
            "serial-can:query",
          ]);
          assert.equal(external.controller.state.confirmedMode, "can");
          assert.equal(external.controller.state.selectedProtocol, "can");
          assert.equal(external.controller.state.dirtyConfig, false);
        }

        {
          const stable = makeHarness({ initialMode: "can" });
          await stable.controller.refreshDecode();
          await settle();
          stable.controller.setDirty("config", true);
          await stable.controller.applyDecode({}, { baud_rate: 500000 });
          await settle();
          assert.deepEqual(commandsOf(stable).slice(3), [
            "serial-mode:query",
            "serial-can:set",
            "serial-mode:query",
            "serial-display:query",
            "serial-can:query",
          ]);
          assert.equal(stable.submitted[4].intent, "apply");
          assert.equal(stable.submitted[4].parameters.baud_rate, 500000);
          assert.equal(stable.controller.state.dirtyConfig, false);
          assert.equal(stable.controller.state.confirmedMode, "can");
        }

        {
          const failedRecheck = makeHarness({ initialMode: "uart" });
          await failedRecheck.controller.refreshDecode();
          await settle();
          failedRecheck.controller.setDirty("config", true);
          failedRecheck.setModeQueryFails(true);
          await failedRecheck.controller.applyDecode({}, { baud_rate: 115200 });
          await settle();
          assert.deepEqual(commandsOf(failedRecheck).slice(3), [
            "serial-mode:query",
          ]);
          assert.equal(failedRecheck.controller.state.confirmedMode, "uart");
          assert.equal(failedRecheck.controller.state.selectedProtocol, "uart");
          assert.equal(failedRecheck.controller.state.dirtyConfig, true);

          failedRecheck.setModeQueryFails(false);
          await failedRecheck.controller.applyDecode({}, { baud_rate: 115200 });
          await settle();
          assert.deepEqual(commandsOf(failedRecheck).slice(4), [
            "serial-mode:query",
            "serial-uart:set",
            "serial-mode:query",
            "serial-display:query",
            "serial-uart:query",
          ]);
          assert.equal(failedRecheck.controller.state.dirtyConfig, false);
        }

        {
          const triggerApply = makeHarness({ initialMode: "can" });
          await triggerApply.controller.refreshTrigger();
          await settle();
          assert.deepEqual(commandsOf(triggerApply), [
            "serial-mode:query",
            "serial-trigger-can:query",
          ]);
          triggerApply.controller.setDirty("trigger", true);
          await triggerApply.controller.applyTrigger({ type: "start-of-frame" });
          await settle();
          assert.deepEqual(commandsOf(triggerApply).slice(2), [
            "serial-mode:query",
            "serial-trigger-can:set",
          ]);
          assert.equal(triggerApply.submitted[3].intent, "apply");
          assert.equal(triggerApply.controller.state.dirtyTrigger, false);
          assert.equal(triggerApply.controller.state.confirmedMode, "can");
        }

        {
          const failedTriggerRecheck = makeHarness({ initialMode: "uart" });
          await failedTriggerRecheck.controller.refreshTrigger();
          await settle();
          failedTriggerRecheck.controller.setDirty("trigger", true);
          failedTriggerRecheck.setModeQueryFails(true);
          await failedTriggerRecheck.controller.applyTrigger({ type: "rx-start" });
          await settle();
          assert.deepEqual(commandsOf(failedTriggerRecheck).slice(2), [
            "serial-mode:query",
          ]);
          assert.equal(failedTriggerRecheck.controller.state.confirmedMode, "uart");
          assert.equal(failedTriggerRecheck.controller.state.selectedProtocol, null);
          assert.equal(failedTriggerRecheck.controller.state.dirtyTrigger, true);

          failedTriggerRecheck.setModeQueryFails(false);
          failedTriggerRecheck.controller.setDirty("trigger", true);
          failedTriggerRecheck.setCurrentMode("can");
          await failedTriggerRecheck.controller.applyTrigger({ type: "rx-start" });
          await settle();
          const tail = commandsOf(failedTriggerRecheck).slice(2);
          assert.equal(tail[0], "serial-mode:query");
          assert.equal(tail.some((entry) => entry === "serial-trigger-uart:set"), false);
          assert.deepEqual(tail.slice(1), [
            "serial-mode:query",
            "serial-trigger-can:query",
          ]);
          assert.equal(failedTriggerRecheck.controller.state.confirmedMode, "can");
          assert.equal(failedTriggerRecheck.controller.state.selectedProtocol, "can");
          assert.equal(failedTriggerRecheck.controller.state.dirtyTrigger, false);
          assert.equal(failedTriggerRecheck.controller.state.dirtyConfig, false);
        }

        {
          const dirtyBusCancel = makeHarness({
            initialMode: "can", maxBus: 2, confirmResult: false,
          });
          dirtyBusCancel.controller.refreshDecode();
          await settle();
          const before = dirtyBusCancel.submitted.length;
          dirtyBusCancel.controller.setDirty("trigger", true);
          dirtyBusCancel.controller.selectBus(2);
          await settle();
          assert.deepEqual(dirtyBusCancel.confirmations, ["asked"]);
          assert.equal(dirtyBusCancel.controller.state.bus, 1);
          assert.equal(dirtyBusCancel.controller.state.dirtyTrigger, true);
          assert.equal(dirtyBusCancel.submitted.length, before);

          const dirtyBusDiscard = makeHarness({ initialMode: "can", maxBus: 2 });
          dirtyBusDiscard.controller.refreshDecode();
          await settle();
          dirtyBusDiscard.controller.setDirty("trigger", true);
          dirtyBusDiscard.controller.selectBus(2);
          await settle();
          assert.deepEqual(dirtyBusDiscard.confirmations, ["asked"]);
          assert.equal(dirtyBusDiscard.controller.state.bus, 2);
          assert.equal(dirtyBusDiscard.controller.state.dirtyTrigger, false);
          assert.equal(dirtyBusDiscard.submitted.length, 3);
          await dirtyBusDiscard.controller.refreshDecode();
          await settle();
          assert.equal(commandsOf(dirtyBusDiscard)[3], "serial-mode:query");
        }

        {
          const dirtyProtocol = makeHarness({ initialMode: "can", confirmResult: false });
          await dirtyProtocol.controller.refreshDecode();
          await settle();
          const before = dirtyProtocol.submitted.length;
          dirtyProtocol.controller.setDirty("config", true);
          dirtyProtocol.controller.selectProtocol("uart");
          await settle();
          assert.deepEqual(dirtyProtocol.confirmations, ["asked"]);
          assert.equal(dirtyProtocol.controller.state.selectedProtocol, "can");
          assert.equal(dirtyProtocol.controller.state.dirtyConfig, true);
          assert.equal(dirtyProtocol.submitted.length, before);
        }

        {
          const listerKept = makeHarness({ initialMode: "can" });
          await listerKept.controller.refreshDecode();
          await settle();
          listerKept.controller.setDirty("listerDisplay", true);
          listerKept.controller.selectProtocol("uart");
          await listerKept.controller.applyDecode({}, {});
          await settle();
          assert.deepEqual(listerKept.confirmations, []);
          assert.equal(listerKept.controller.state.confirmedMode, "uart");
          assert.equal(listerKept.controller.state.dirtyListerDisplay, true);

          const busTwoLister = makeHarness({
            initialMode: "can", maxBus: 2,
          });
          busTwoLister.controller.refreshDecode();
          await settle();
          busTwoLister.controller.setDirty("display", true);
          busTwoLister.controller.setDirty("listerReference", true);
          busTwoLister.controller.selectBus(2);
          await settle();
          assert.deepEqual(busTwoLister.confirmations, ["asked"]);
          assert.equal(busTwoLister.controller.state.dirtyDisplay, false);
          assert.equal(busTwoLister.controller.state.dirtyListerReference, true);
        }

        {
          const listerRouting = makeHarness({ initialMode: "can" });
          await listerRouting.controller.refreshDecode();
          await settle();
          listerRouting.controller.setDirty("listerDisplay", true);
          await listerRouting.controller.applyListerSetting("display", { display: "all" });
          await settle();
          const lastDisplay = listerRouting.submitted[listerRouting.submitted.length - 1];
          assert.equal(lastDisplay.command, "serial-lister-display");
          assert.equal(lastDisplay.action, "set");
          assert.equal(lastDisplay.intent, "apply");
          assert.equal(listerRouting.controller.state.dirtyListerDisplay, false);

          listerRouting.controller.setDirty("listerReference", true);
          await listerRouting.controller.applyListerSetting("reference", { reference: "previous" });
          await settle();
          const lastReference = listerRouting.submitted[listerRouting.submitted.length - 1];
          assert.equal(lastReference.command, "serial-lister-reference");
          assert.equal(lastReference.action, "set");
          assert.equal(lastReference.intent, "apply");
          assert.equal(listerRouting.controller.state.dirtyListerReference, false);

          const beforeExport = listerRouting.submitted.length;
          assert.equal(await listerRouting.controller.exportLister(""), null);
          assert.equal(listerRouting.submitted.length, beforeExport);
          const exported = await listerRouting.controller.exportLister("capture.csv");
          await settle();
          assert.equal(exported.status, "completed");
          const lastExport = listerRouting.submitted[listerRouting.submitted.length - 1];
          assert.equal(lastExport.command, "serial-lister-export");
          assert.equal(lastExport.intent, undefined);
        }

        {
          const relister = makeHarness({ initialMode: "can" });
          await relister.controller.refreshDecode();
          await settle();
          const firstCommands = commandsOf(relister);
          assert.equal(firstCommands.includes("serial-lister-query"), false);
          assert.equal(firstCommands.includes("serial-trigger-can:query"), false);
          await relister.controller.refreshLister();
          await settle();
          assert.deepEqual(commandsOf(relister).slice(3), listerRefreshCommands(1));
          const before = relister.submitted.length;
          await relister.controller.refreshLister();
          await settle();
          const refreshed = relister.submitted.slice(before);
          assert.deepEqual(refreshed.map((entry) => entry.command), [
            "serial-lister-query",
            "serial-display",
          ]);
        }

        {
          const partial = makeHarness({
            initialMode: "can",
            maxBus: 2,
            listerDisplay: "all",
            serialDisplays: { 1: true, 2: false },
            failedSerialDisplays: new Set([2]),
          });
          await partial.controller.refreshLister();
          await settle();
          assert.equal(partial.controller.state.listerDisplay, "all");
          assert.equal(partial.controller.state.decodeDisplayByBus[1], true);
          assert.equal(partial.controller.state.decodeDisplayByBus[2], "unknown");
          assert.equal(partial.controller.state.confirmedMode, null);
          assert.equal(partial.controller.state.jobs.display, null);
          assert.deepEqual(commandsOf(partial), [
            "serial-lister-query",
            "serial-display:query",
            "serial-display:query",
          ]);
        }
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(serial_editor_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_serial_readiness_partial_failures_and_pending_read_behavior() -> None:
    serial_editor_path = STATIC_ROOT / "serial-editor.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.serialApi = { createSerialEditorController };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const harness = ({ mode = "uart", failures = new Set(), maxBus = 1 } = {}) => {
          const calls = [];
          const execute = async (command, parameters, options = {}) => {
            calls.push({ command, parameters, options });
            if (failures.has(command)) {
              return { job_id: `failed-${calls.length}`, status: "failed", error: "read failed" };
            }
            let result;
            if (command === "serial-mode") {
              result = { mode: { bus: parameters.bus, mode, raw_mode: mode.toUpperCase() } };
            } else if (command === "serial-display") {
              result = { display: { bus: parameters.bus, enabled: true } };
            } else if (command === "serial-lister-query") {
              result = { lister: { display: "bus1", reference: "trigger" } };
            } else if (command.startsWith("serial-trigger-")) {
              result = { trigger: { protocol: mode, bus: parameters.bus } };
            } else {
              result = { [command.replace("serial-", "")]: { bus: parameters.bus } };
            }
            return { job_id: `job-${calls.length}`, status: "completed", result: { result } };
          };
          const controller = serialApi.createSerialEditorController({
            execute,
            confirmDiscard: () => true,
            available: () => true,
          });
          controller.reset({ maxBus, protocolChoices: ["uart", "i2c", "spi", "can"] });
          return { controller, calls, setMode: (value) => { mode = value; } };
        };

        const decode = harness({ failures: new Set(["serial-display"]) });
        assert.equal(decode.controller.state.decodeModeReady, false);
        assert.equal(decode.controller.state.triggerModeReady, false);
        await decode.controller.refreshDecode();
        assert.equal(decode.controller.state.decodeModeReady, true);
        assert.equal(decode.controller.state.decodeDisplayReady, false);
        assert.equal(decode.controller.state.decodeConfigReady, true);
        assert.equal(decode.controller.state.triggerModeReady, false);
        assert.equal(decode.controller.state.triggerConfigReady, false);

        const trigger = harness({ failures: new Set(["serial-trigger-uart"]) });
        await trigger.controller.refreshTrigger();
        assert.equal(trigger.controller.state.triggerModeReady, true);
        assert.equal(trigger.controller.state.triggerConfigReady, false);
        assert.equal(trigger.controller.state.decodeModeReady, false);
        assert.equal(trigger.controller.state.decodeDisplayReady, false);
        assert.equal(trigger.controller.state.decodeConfigReady, false);

        const unsupported = harness({ mode: "lin" });
        await unsupported.controller.refreshTrigger();
        assert.deepEqual(unsupported.calls.map((entry) => entry.command), ["serial-mode"]);
        assert.equal(unsupported.controller.state.triggerModeReady, true);
        assert.equal(unsupported.controller.state.triggerConfigReady, false);
        assert.equal(unsupported.controller.state.supported, false);

        const lister = harness({ maxBus: 2 });
        await lister.controller.refreshLister();
        assert.equal(lister.calls[0].command, "serial-lister-query");
        assert.equal(lister.calls[0].options.captureWorkspaceResult, undefined);
        assert.equal(lister.calls[1].options.captureWorkspaceResult, false);
        assert.equal(lister.calls[2].options.captureWorkspaceResult, false);
        assert.equal(lister.controller.state.decodeModeReady, false);
        assert.equal(lister.controller.state.triggerModeReady, false);

        const cleanPending = harness({ mode: "uart" });
        await cleanPending.controller.refreshDecode();
        cleanPending.controller.selectProtocol("can");
        await cleanPending.controller.refreshDecode();
        assert.equal(cleanPending.controller.state.protocolPending, false);
        assert.equal(cleanPending.controller.state.selectedProtocol, "uart");
        assert.equal(cleanPending.controller.state.jobs.config.protocol, "uart");

        const dirtyPending = harness({ mode: "uart" });
        await dirtyPending.controller.refreshDecode();
        dirtyPending.controller.selectProtocol("can");
        dirtyPending.controller.setDirty("config", true);
        await dirtyPending.controller.refreshDecode();
        assert.equal(dirtyPending.controller.state.protocolPending, true);
        assert.equal(dirtyPending.controller.state.selectedProtocol, "can");
        assert.equal(dirtyPending.controller.state.dirtyConfig, true);
        assert.equal(dirtyPending.controller.state.jobs.config.protocol, "uart");
        ''')
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(serial_editor_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_serial_workspace_views_keep_selected_bus_and_follow_mode_readback() -> None:
    serial_editor_path = STATIC_ROOT / "serial-editor.js"
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
            this.value = "";
            this.className = "";
            this.options = [];
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) { this.children = []; this.options = []; this.append(...nodes); }
          append(...nodes) {
            this.children.push(...nodes);
            if (this.tagName === "SELECT") {
              this.options.push(...nodes.filter((node) => node.tagName === "OPTION"));
            }
          }
          querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
          querySelectorAll(selector) {
            const matches = [];
            const fieldMatch = selector.match(/^\[data-field="([^"]+)"\]$/);
            const visit = (node) => {
              if (selector === "[data-field]" && node?.dataset?.field) matches.push(node);
              if (fieldMatch && node?.dataset?.field === fieldMatch[1]) matches.push(node);
              for (const child of node?.children || []) visit(child);
            };
            for (const child of this.children) visit(child);
            return matches;
          }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.Option = function Option(text, value) {
          const option = new FakeNode("option");
          option.textContent = text;
          option.value = String(value);
          return option;
        };
        globalThis.window = { confirm: () => true };
        globalThis.testLocale = "en";
        globalThis.translate = (key) => {
          if (key === "form.selectValue") {
            return globalThis.testLocale === "zh-TW" ? "請選擇值" : "Select a value";
          }
          const protocol = /^enum\.serial-protocol\.(.+)$/.exec(key);
          if (protocol) {
            return {
              uart: "UART", i2c: "I2C", spi: "SPI", can: "CAN",
              flexray: "FlexRay", manchester: "Manchester",
            }[protocol[1]] || protocol[1].toUpperCase();
          }
          return key;
        };
        globalThis.hasTranslation = (key) =>
          key === "form.selectValue" || /^enum\.serial-protocol\./.test(key);
        globalThis.CommandForm = class CommandForm {
          constructor(container) {
            this.container = container;
            this.dirty = false;
            this.lastSyncArgs = null;
            this.clearedDirty = false;
          }
          render(definition) {
            this.container.replaceChildren();
            for (const field of definition.fields) {
              const input = new FakeNode(field.type === "enum" ? "select" : "input");
              input.dataset.field = field.name;
              for (const optionValue of field.options || []) {
                const option = new Option(optionValue, optionValue);
                option.disabled = (field.disabled_options || []).includes(optionValue);
                input.append(option);
              }
              this.container.append(input);
            }
          }
          values() { return {}; }
          setDisabled(disabled) {
            for (const input of this.container.querySelectorAll("[data-field]")) {
              input.disabled = disabled;
            }
          }
          clearDirty() { this.clearedDirty = true; this.dirty = false; }
          syncResult(job, preserveDirty) { this.lastSyncArgs = [job, preserveDirty]; }
          isDirty() { return this.dirty; }
          refreshLocale() {}
        };

        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.serialApi = { SerialDecodeEditor, SerialTriggerEditor, SerialListerEditor, createSerialEditorController };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { SerialDecodeEditor, SerialTriggerEditor, SerialListerEditor, createSerialEditorController } = globalThis.serialApi;

        const settle = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
          await new Promise((resolve) => setTimeout(resolve, 0));
        };

        const settingFields = [{ name: "action", type: "enum", options: ["query", "set"] }];
        const definitionFor = (id, queryFields = ["bus"], fields = [
          ...settingFields,
          { name: "value", type: "string" },
        ]) => ({
          id,
          category: "Serial",
          modes: ["live"],
          presentation: { kind: "setting", action_field: "action", apply_value: "set", query_value: "query", query_fields: queryFields },
          fields,
        });
        const catalog = {
          commands: [
            definitionFor("serial-mode"),
            definitionFor("serial-display"),
            definitionFor("serial-uart"),
            definitionFor("serial-i2c"),
            definitionFor("serial-spi"),
            definitionFor("serial-can"),
            definitionFor("serial-trigger-uart"),
            definitionFor("serial-trigger-i2c"),
            definitionFor("serial-trigger-spi"),
            definitionFor("serial-trigger-can"),
            definitionFor("serial-lister-query", []),
            definitionFor("serial-lister-display", [], [
              ...settingFields,
              { name: "display", type: "enum", options: ["off", "bus1", "bus2", "all"] },
            ]),
            definitionFor("serial-lister-reference", [], [
              ...settingFields,
              { name: "reference", type: "enum", options: ["trigger", "previous"] },
            ]),
            definitionFor("serial-lister-export", [], [
              { name: "filename", type: "string" },
            ]),
          ],
          fieldsFor: (definition) => definition.fields,
          optionsFor: (field) => field.options || [],
        };

        const submitted = [];
        let executionBusy = false;
        let runtimeLocale = "en";
        let currentMode = "can";
        let listerDisplay = "bus1";
        const serialDisplays = { 1: false, 2: false };
        const failedSerialDisplays = new Set();
        const failedCommands = new Set();
        const setCurrentMode = (mode) => { currentMode = mode; };
        const setListerDisplay = (display) => { listerDisplay = display; };
        const respond = (command, parameters) => {
          if (failedCommands.has(command)) {
            return {
              job_id: `failed-${submitted.length}`,
              status: "failed",
              error: "temporary VISA failure",
            };
          }
          if (command === "serial-mode") {
            if (parameters.action === "set") currentMode = parameters.mode;
            return {
              job_id: `mode-${submitted.length}`,
              status: "completed",
              result: { result: { mode: {
                bus: parameters.bus,
                mode: currentMode,
                raw_mode: String(currentMode).toUpperCase(),
              } } },
            };
          }
          if (command === "serial-display") {
            if (failedSerialDisplays.has(parameters.bus)) {
              return {
                job_id: `display-${submitted.length}`,
                status: "failed",
                error: "temporary VISA failure",
              };
            }
            return {
              job_id: `display-${submitted.length}`,
              status: "completed",
              result: { result: { display: {
                bus: parameters.bus,
                enabled: serialDisplays[parameters.bus] ?? false,
              } } },
            };
          }
          if (command === "serial-lister-query") {
            return {
              job_id: `lister-${submitted.length}`,
              status: "completed",
              result: { result: { lister: { display: listerDisplay, reference: "trigger" } } },
            };
          }
          if (command === "serial-lister-display") {
            listerDisplay = parameters.display;
            return {
              job_id: `lister-display-${submitted.length}`,
              status: "completed",
              result: { result: { display: { display: listerDisplay } } },
            };
          }
          if (command === "serial-lister-reference") {
            return {
              job_id: `lister-reference-${submitted.length}`,
              status: "completed",
              result: { result: { reference: { reference: parameters.reference } } },
            };
          }
          const protocol = command.replace("serial-", "");
          return {
            job_id: `${protocol}-${submitted.length}`,
            status: "completed",
            result: { result: { [protocol]: { bus: parameters.bus } } },
          };
        };
        const hooks = {
          executeCommand: async (command, parameters) => {
            const job = respond(command, parameters);
            submitted.push({ command, bus: parameters.bus, action: parameters.action });
            return job;
          },
          isAvailable: () => true,
          isExecutionBusy: () => executionBusy,
          contextKey: () => "ctx",
          headerActions: new FakeNode(),
          renderPcOutputNote: (note) => {
            note.textContent = runtimeLocale === "zh-TW"
              ? "PC 輸出資料夾：data  請至基本控制統一設定。"
              : "PC output folder: data  Managed in Basic Controls.";
          },
          modelInfo: () => ({ supported: true, maxBus: 2, protocols: ["uart", "i2c", "spi", "can"] }),
        };
        const controller = createSerialEditorController({
          execute: hooks.executeCommand,
          confirmDiscard: () => true,
          available: () => true,
        });
        const decodeEditor = new SerialDecodeEditor(new FakeNode(), catalog, hooks, controller);
        const triggerEditor = new SerialTriggerEditor(new FakeNode(), catalog, hooks, controller);
        const listerEditor = new SerialListerEditor(new FakeNode(), catalog, hooks, controller);

        decodeEditor.schedulePresentation();
        await settle();
        assert.equal(decodeEditor.protocolSelect.value, "");
        assert.deepEqual(submitted, []);
        assert.equal(decodeEditor.protocolSelect.children[0].value, "");
        assert.equal(decodeEditor.protocolSelect.children[0].disabled, true);
        assert.equal(decodeEditor.protocolSelect.children[0].textContent, "Select a value");
        globalThis.testLocale = "zh-TW";
        decodeEditor.rerender();
        assert.equal(decodeEditor.protocolSelect.children[0].textContent, "請選擇值");
        globalThis.testLocale = "en";
        decodeEditor.rerender();
        assert.equal(decodeEditor.protocolSelect.children[0].textContent, "Select a value");
        assert.equal(decodeEditor.protocolSelect.disabled, true);
        assert.equal(decodeEditor.configUnreadPresentation.hidden, false);
        const decodePreviewFields = decodeEditor.configFormContainer.querySelectorAll("[data-field]");
        assert.ok(decodePreviewFields.length > 0);
        assert.equal(decodePreviewFields.every((field) => field.disabled), true);
        assert.equal(decodeEditor.displayForm.lastSyncArgs, null);
        assert.equal(decodeEditor.applyDecodeButton.disabled, true);
        assert.ok(decodeEditor.applyDecodeButton.className.startsWith("primary"));
        assert.ok(hooks.headerActions.children.includes(decodeEditor.refreshButton));
        assert.ok(hooks.headerActions.children.includes(decodeEditor.applyDecodeButton));

        triggerEditor.schedulePresentation();
        await settle();
        assert.equal(triggerEditor.triggerSection.hidden, false);
        assert.ok(triggerEditor.triggerForm);
        const triggerPreviewFields = triggerEditor.triggerFormContainer.querySelectorAll("[data-field]");
        assert.ok(triggerPreviewFields.length > 0);
        assert.equal(triggerPreviewFields.every((field) => field.disabled), true);
        assert.equal(triggerEditor.triggerNote.hidden, false);
        assert.equal(triggerEditor.applyTriggerButton.disabled, true);
        assert.ok(triggerEditor.applyTriggerButton.className.startsWith("primary"));
        assert.ok(hooks.headerActions.children.includes(triggerEditor.applyTriggerButton));
        assert.deepEqual(submitted, []);

        listerEditor.schedulePresentation();
        await settle();
        assert.ok(listerEditor.listerDisplayForm);
        assert.ok(listerEditor.listerReferenceForm);
        assert.ok(listerEditor.exportForm);
        assert.equal(listerEditor.listerDisplayFormContainer.className, "command-form");
        assert.equal(listerEditor.listerReferenceFormContainer.className, "command-form");
        assert.equal(listerEditor.exportFormContainer.className, "command-form");
        assert.deepEqual(listerEditor.listerDisplayRow.children, [
          listerEditor.listerDisplayFormContainer,
          listerEditor.applyListerDisplayButton,
        ]);
        assert.deepEqual(listerEditor.listerReferenceRow.children, [
          listerEditor.listerReferenceFormContainer,
          listerEditor.applyListerReferenceButton,
        ]);
        assert.deepEqual(listerEditor.exportRow.children, [
          listerEditor.exportFormContainer,
          listerEditor.pcOutputNote,
          listerEditor.exportButton,
        ]);
        assert.equal(listerEditor.listerDisplayRow.className, listerEditor.exportRow.className);
        assert.ok(listerEditor.pcOutputNote.className.includes("pc-output-note-box"));
        assert.equal(listerEditor.listerDisplayForm.lastSyncArgs, null);
        assert.equal(listerEditor.listerReferenceForm.lastSyncArgs, null);
        assert.equal(listerEditor.applyListerDisplayButton.disabled, true);
        assert.equal(listerEditor.applyListerReferenceButton.disabled, true, "unknown prerequisite reference");
        assert.equal(listerEditor.exportButton.disabled, true, "unknown prerequisite export");
        assert.equal(
          listerEditor.listerDisplayFormContainer.querySelector('[data-field="display"]').disabled,
          true,
        );
        assert.equal(
          listerEditor.listerReferenceFormContainer.querySelector('[data-field="reference"]').disabled,
          true,
        );
        assert.equal(
          listerEditor.exportFormContainer.querySelector('[data-field="filename"]').disabled,
          true,
        );
        assert.equal(listerEditor.pcOutputNote.textContent, "PC output folder: data  Managed in Basic Controls.");
        runtimeLocale = "zh-TW";
        listerEditor.rerender();
        assert.equal(listerEditor.pcOutputNote.textContent, "PC 輸出資料夾：data  請至基本控制統一設定。");
        assert.deepEqual(submitted, []);

        decodeEditor.refreshButton.dispatch("click");
        await settle();
        assert.equal(decodeEditor.protocolSelect.value, "can");
        assert.equal(decodeEditor.protocolSelect.disabled, false);
        assert.equal(decodeEditor.configUnreadPresentation.hidden, true);
        assert.ok(decodeEditor.displayForm.lastSyncArgs);
        assert.ok(decodeEditor.configForm.lastSyncArgs);
        assert.equal(decodeEditor.configForm.lastSyncArgs[1], true);
        assert.equal(decodeEditor.applyDecodeButton.disabled, false);
        assert.equal(triggerEditor.triggerNote.hidden, false);
        assert.equal(triggerEditor.applyTriggerButton.disabled, true);
        assert.equal(
          triggerEditor.triggerFormContainer.querySelectorAll("[data-field]")
            .every((field) => field.disabled),
          true,
        );

        triggerEditor.refreshButton.dispatch("click");
        await settle();
        assert.equal(triggerEditor.triggerSection.hidden, false);
        assert.ok(triggerEditor.triggerForm);
        assert.equal(triggerEditor.triggerNote.hidden, true);
        assert.equal(triggerEditor.applyTriggerButton.disabled, false);

        listerEditor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "serial-mode",
          "serial-display",
          "serial-can",
          "serial-mode",
          "serial-trigger-can",
          "serial-lister-query",
          "serial-display",
          "serial-display",
        ]);
        assert.equal(controller.state.listerDisplay, "bus1");
        assert.equal(controller.state.decodeDisplayByBus[1], false);
        assert.equal(controller.state.decodeDisplayByBus[2], false);
        assert.equal(listerEditor.listerDisplayForm.lastSyncArgs?.[1], true);
        assert.equal(listerEditor.listerReferenceForm.lastSyncArgs?.[1], true);
        assert.equal(listerEditor.applyListerDisplayButton.disabled, true, "all decode displays off");
        assert.equal(listerEditor.applyListerReferenceButton.disabled, true, "all decode displays off");
        assert.equal(listerEditor.exportButton.disabled, true, "all decode displays off");
        assert.equal(
          listerEditor.listerDisplayFormContainer.querySelector('[data-field="display"]').disabled,
          true,
        );
        assert.equal(
          listerEditor.listerReferenceFormContainer.querySelector('[data-field="reference"]').disabled,
          true,
        );
        assert.equal(
          listerEditor.exportFormContainer.querySelector('[data-field="filename"]').disabled,
          true,
        );
        assert.equal(listerEditor.prerequisiteNote.hidden, false);
        assert.equal(listerEditor.prerequisiteNote.textContent, "serial.lister.allDecodeDisabled");

        serialDisplays[1] = true;
        listerEditor.refreshButton.dispatch("click");
        await settle();
        const displaySelect = listerEditor.listerDisplayFormContainer
          .querySelector('[data-field="display"]');
        const displayOptions = new Map(
          displaySelect.options.map((option) => [option.value, option]),
        );
        assert.equal(displaySelect.disabled, false);
        assert.equal(listerEditor.applyListerDisplayButton.disabled, false);
        assert.equal(displayOptions.get("off").disabled, false);
        assert.equal(displayOptions.get("bus1").disabled, false);
        assert.equal(displayOptions.get("bus2").disabled, true);
        assert.equal(displayOptions.get("all").disabled, false);
        assert.equal(listerEditor.applyListerReferenceButton.disabled, false);
        assert.equal(listerEditor.exportButton.disabled, false);

        serialDisplays[2] = true;
        listerEditor.refreshButton.dispatch("click");
        await settle();
        assert.equal(displayOptions.get("bus2").disabled, false, "two-bus model Bus 2");

        decodeEditor.protocolSelect.value = "uart";
        decodeEditor.protocolSelect.dispatch("change");
        controller.setDirty("config", true);
        const decodeStateBeforeListerRead = {
          selectedProtocol: controller.state.selectedProtocol,
          confirmedMode: controller.state.confirmedMode,
          dirtyConfig: controller.state.dirtyConfig,
          modeJob: controller.state.jobs.mode,
          displayJob: controller.state.jobs.display,
        };
        listerEditor.refreshButton.dispatch("click");
        await settle();
        assert.equal(controller.state.selectedProtocol, decodeStateBeforeListerRead.selectedProtocol);
        assert.equal(controller.state.confirmedMode, decodeStateBeforeListerRead.confirmedMode);
        assert.equal(controller.state.dirtyConfig, decodeStateBeforeListerRead.dirtyConfig);
        assert.equal(controller.state.jobs.mode, decodeStateBeforeListerRead.modeJob);
        assert.equal(controller.state.jobs.display, decodeStateBeforeListerRead.displayJob);

        setListerDisplay("off");
        listerEditor.refreshButton.dispatch("click");
        await settle();
        assert.equal(controller.state.listerDisplay, "off");
        assert.equal(listerEditor.applyListerDisplayButton.disabled, false, "off lister display apply");
        assert.equal(listerEditor.applyListerReferenceButton.disabled, true);
        assert.equal(listerEditor.exportButton.disabled, true);
        controller.setDirty("listerDisplay", true);
        listerEditor.render(controller.state);
        assert.equal(listerEditor.applyListerDisplayButton.disabled, false, "dirty lister display apply");
        assert.equal(listerEditor.applyListerReferenceButton.disabled, true);
        assert.equal(listerEditor.exportButton.disabled, true);
        await controller.applyListerSetting("display", { display: "bus1" });
        await settle();
        assert.equal(controller.state.listerDisplay, "bus1");
        listerEditor.render(controller.state);
        assert.equal(listerEditor.applyListerReferenceButton.disabled, false, "applied display reference");
        assert.equal(listerEditor.exportButton.disabled, false, "applied display export");

        failedSerialDisplays.add(1);
        listerEditor.refreshButton.dispatch("click");
        await settle();
        assert.equal(controller.state.decodeDisplayByBus[1], "unknown");
        listerEditor.render(controller.state);
        assert.equal(listerEditor.applyListerReferenceButton.disabled, true, "unknown prerequisite reference");
        assert.equal(listerEditor.exportButton.disabled, true, "unknown prerequisite export");
        failedSerialDisplays.delete(1);
        listerEditor.refreshButton.dispatch("click");
        await settle();
        assert.equal(controller.state.decodeDisplayByBus[1], true);
        listerEditor.render(controller.state);
        assert.equal(listerEditor.applyListerReferenceButton.disabled, false, "restored prerequisite reference");
        assert.equal(listerEditor.exportButton.disabled, false, "restored prerequisite export");

        listerEditor.listerDisplayForm.dirty = true;
        listerEditor.listerReferenceForm.dirty = true;

        const busSwitchBase = submitted.length;
        decodeEditor.busSelect.value = "2";
        decodeEditor.busSelect.dispatch("change");
        await settle();
        assert.equal(controller.state.bus, 2);
        assert.equal(controller.state.selectedProtocol, null);
        assert.equal(decodeEditor.protocolSelect.value, "");
        assert.equal(submitted.length, busSwitchBase);

        decodeEditor.refreshButton.dispatch("click");
        await settle();
        assert.equal(decodeEditor.protocolSelect.value, "can");

        assert.equal(listerEditor.listerDisplayForm.lastSyncArgs?.[1], true);
        assert.equal(listerEditor.listerReferenceForm.lastSyncArgs?.[1], true);

        const laterSubmissions = submitted.slice(busSwitchBase);
        assert.equal(laterSubmissions.length > 0, true);
        assert.equal(laterSubmissions.every((entry) =>
          entry.bus === 2 || entry.command === "serial-lister-query"), true);
        assert.equal(laterSubmissions.some((entry) =>
          entry.command === "serial-mode" && entry.action === "query"), true);
        assert.equal(laterSubmissions.some((entry) =>
          entry.command === "serial-display" && entry.action === "query"), true);
        assert.equal(laterSubmissions.some((entry) =>
          entry.command.startsWith("serial-trigger-")), false);
        assert.equal(laterSubmissions.some((entry) =>
          entry.command === "serial-lister-query"), false);

        decodeEditor.displayForm.values = () => ({ enabled: true });
        listerEditor.exportForm.values = () => ({ filename: "serial.csv" });
        executionBusy = true;
        decodeEditor.render(controller.state);
        listerEditor.render(controller.state);
        assert.equal(decodeEditor.applyDecodeButton.disabled, true);
        assert.equal(listerEditor.exportButton.disabled, true);
        const blockedAt = submitted.length;
        await decodeEditor.submitDecode();
        await listerEditor.submitExport();
        assert.equal(submitted.length, blockedAt);

        executionBusy = false;
        decodeEditor.render(controller.state);
        listerEditor.render(controller.state);
        assert.equal(decodeEditor.applyDecodeButton.disabled, false, "idle decode apply");
        assert.equal(listerEditor.exportButton.disabled, false, "idle lister export");
        await listerEditor.submitExport();
        assert.equal(submitted[blockedAt].command, "serial-lister-export");

        const cleanBase = submitted.length;
        decodeEditor.displayForm.values = () => ({ enabled: true });
        await decodeEditor.submitDecode();
        assert.equal(submitted.length, cleanBase);

        decodeEditor.displayForm.dirty = true;
        await decodeEditor.submitDecode();
        assert.deepEqual(submitted.slice(cleanBase).map((entry) => entry.command), [
          "serial-display",
          "serial-mode",
          "serial-display",
          "serial-can",
        ]);

        setCurrentMode("lin");
        await controller.refreshDecode();
        await settle();
        assert.equal(controller.state.selectedProtocol, null);
        assert.equal(decodeEditor.protocolSelect.value, "");
        const linBase = submitted.length;
        decodeEditor.displayForm.values = () => ({ enabled: true });
        decodeEditor.displayForm.dirty = true;
        await decodeEditor.submitDecode();
        assert.deepEqual(submitted.slice(linBase).map((entry) => entry.command), [
          "serial-display",
          "serial-mode",
          "serial-display",
        ]);

        decodeEditor.protocolSelect.value = "uart";
        decodeEditor.protocolSelect.dispatch("change");
        assert.equal(controller.state.protocolPending, true);
        decodeEditor.displayForm.dirty = false;
        await decodeEditor.submitDecode();
        assert.deepEqual(submitted.slice(linBase + 3).map((entry) => entry.command), [
          "serial-mode",
          "serial-mode",
          "serial-display",
          "serial-uart",
        ]);
        assert.equal(controller.state.protocolPending, false);

        setCurrentMode("uart");
        await controller.refreshDecode();
        await settle();

        decodeEditor.protocolSelect.value = "can";
        decodeEditor.protocolSelect.dispatch("change");
        assert.equal(controller.state.protocolPending, true);
        decodeEditor.refreshButton.dispatch("click");
        await settle();
        assert.equal(controller.state.protocolPending, false);
        assert.equal(controller.state.selectedProtocol, "uart");
        assert.equal(decodeEditor.protocolSelect.value, "uart");
        assert.ok(decodeEditor.configForm.lastSyncArgs);

        decodeEditor.protocolSelect.value = "can";
        decodeEditor.protocolSelect.dispatch("change");
        decodeEditor.configForm.values = () => ({ baud_rate: 9600 });
        decodeEditor.configForm.dirty = true;
        controller.setDirty("config", true);
        const draftBefore = decodeEditor.configForm.values();
        await controller.refreshDecode();
        await settle();
        assert.equal(decodeEditor.configForm.lastSyncArgs, null);
        assert.deepEqual(decodeEditor.configForm.values(), draftBefore);
        assert.equal(controller.state.protocolPending, true);
        assert.equal(controller.state.selectedProtocol, "can");

        executionBusy = true;
        const schedBase = submitted.length;
        const decodeInFlight = controller.refreshDecode();
        triggerEditor.schedulePresentation();
        await decodeInFlight;
        await settle();
        executionBusy = false;
        assert.deepEqual(submitted.slice(schedBase).map((entry) => entry.command), [
          "serial-mode",
          "serial-display",
          "serial-uart",
        ]);

        failedSerialDisplays.add(2);
        await controller.refreshDecode();
        await settle();
        assert.equal(controller.state.decodeModeReady, true);
        assert.equal(controller.state.decodeDisplayReady, false);
        assert.equal(
          decodeEditor.displayFormContainer.querySelectorAll("[data-field]")
            .every((field) => field.disabled),
          true,
        );
        failedSerialDisplays.delete(2);

        failedCommands.add("serial-trigger-uart");
        await controller.refreshTrigger();
        await settle();
        assert.equal(controller.state.triggerModeReady, true);
        assert.equal(controller.state.triggerConfigReady, false);
        assert.equal(triggerEditor.triggerNote.hidden, false);
        assert.equal(triggerEditor.applyTriggerButton.disabled, true);
        assert.equal(
          triggerEditor.triggerFormContainer.querySelectorAll("[data-field]")
            .every((field) => field.disabled),
          true,
        );
        failedCommands.delete("serial-trigger-uart");

        setCurrentMode("lin");
        await controller.refreshTrigger();
        await settle();
        assert.equal(triggerEditor.triggerSection.hidden, false);
        assert.equal(triggerEditor.triggerNote.hidden, false);
        assert.equal(triggerEditor.applyTriggerButton.disabled, true);
        assert.equal(
          triggerEditor.triggerFormContainer.querySelectorAll("[data-field]")
            .every((field) => field.disabled),
          true,
        );

        controller.reset({ maxBus: 1, protocolChoices: ["uart", "i2c", "spi", "can"] });
        listerEditor.render(controller.state);
        const oneBusOptions = new Map(
          listerEditor.listerDisplayFormContainer
            .querySelector('[data-field="display"]')
            .options.map((option) => [option.value, option]),
        );
        assert.equal(oneBusOptions.get("bus2").disabled, true, "one-bus model Bus 2");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(serial_editor_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

def test_serial_editor_locale_keys_are_localized() -> None:
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert '"serial.editor.unavailable": "Identify a supported instrument to configure Serial."' in english
    assert '"serial.editor.unsupported": "{{protocol}} is recognized by the instrument' in english
    assert '"serial.editor.discardConfirm": "Discard unapplied Serial changes?"' in english
    assert '"serial.editor.unavailable": "請先連接並識別支援的儀器，再設定串列。"' in chinese
    assert '"serial.editor.discardConfirm": "要捨棄未套用的串列變更嗎？"' in chinese
    assert '"serial-decode.editor.title": "Serial Decode"' in english
    assert '"serial-trigger.editor.title": "Serial Trigger"' in english
    assert '"serial-lister.editor.title": "Serial Lister"' in english
    assert '"serial-decode.editor.title": "串列解碼設定"' in chinese
    assert '"serial-trigger.editor.title": "串列觸發"' in chinese
    assert '"serial-lister.editor.title": "串列資料清單（Lister）"' in chinese
    assert '"serial.decode.applySettings": "Apply decode settings"' in english
    assert '"help.serial-trigger-uart.data": "8-bit data value compared by RX Data or TX Data trigger types, from 0 to 255. For example, 1 represents 0x01."' in english
    assert '"help.serial-lister.reference": "Trigger: each row time is relative to the trigger. Previous Row: each row time is the interval from the previous Lister event."' in english
    assert '"help.serial-trigger-uart.data": "RX Data 或 TX Data 要比對的 8-bit 資料值，範圍 0～255。例如 1 代表 0x01。"' in chinese
    assert '"help.serial-lister.reference": "Trigger：每列時間表示該事件相對於觸發點的時間。上一列：每列時間表示該事件與前一筆 Lister 事件的時間差。"' in chinese
    assert '"serial.decode.applySettings": "套用解碼設定"' in chinese

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_i2c_trigger_type_controls_visible_and_submitted_fields_without_io() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    command = next(
        entry for entry in command_catalog() if entry["id"] == "serial-trigger-i2c"
    )
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
          + "\nglobalThis.CommandForm = CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const metadata = JSON.parse(process.argv[3]);
        const values = {
          action: "set",
          bus: "1",
          type: "start",
          address: "80",
          data: "165",
          data2: "90",
          qualifier: "equal",
        };
        const inputs = new Map();
        const wrappers = [];
        for (const field of metadata.fields) {
          const wrapper = {
            hidden: false,
            dataset: field.visible_if
              ? { visibleIf: JSON.stringify(field.visible_if), visibleIfHidden: "false" }
              : {},
          };
          const input = {
            value: values[field.name] ?? "",
            required: field.required === true,
            type: ["integer", "number"].includes(field.type) ? "number" : "select-one",
            dataset: {
              field: field.name,
              type: field.type,
              required: String(field.required === true),
              ...(field.required_if ? { requiredIf: JSON.stringify(field.required_if) } : {}),
            },
            validity: { badInput: false },
            closest: (selector) => (
              selector === '[data-visible-if-hidden="true"]'
              && wrapper.dataset.visibleIfHidden === "true" ? wrapper : null
            ),
            setCustomValidity() {},
            checkValidity() { return true; },
            reportValidity() { return false; },
          };
          inputs.set(field.name, input);
          if (field.visible_if) wrappers.push(wrapper);
        }
        const container = {
          querySelectorAll(selector) {
            if (selector === "[data-help-by-value]") return [];
            if (selector === "[data-visible-if]") return wrappers;
            if (selector === "[data-field]") return [...inputs.values()];
            return [];
          },
          querySelector(selector) {
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return inputs.get(match?.[1]) ?? null;
          },
        };
        const form = new globalThis.CommandForm(container, null);
        form.command = metadata;
        let ioCalls = 0;
        form.onQueryFieldChange = () => { ioCalls += 1; };

        const cases = [
          ["start", []],
          ["address-no-ack", ["address"]],
          ["read7", ["address", "data"]],
          ["read7-data2", ["address", "data", "data2"]],
          ["read-eeprom", ["address", "data", "qualifier"]],
        ];
        for (const [type, expected] of cases) {
          inputs.get("type").value = type;
          form.refreshVisibility();
          const submitted = form.values();
          const optionalNames = ["address", "data", "data2", "qualifier"];
          assert.deepEqual(optionalNames.filter((name) => name in submitted), expected, type);
          assert.deepEqual(
            optionalNames.filter((name) => !inputs.get(name).closest('[data-visible-if-hidden="true"]')),
            expected,
            type,
          );
        }
        assert.equal(ioCalls, 0);
        '''
    )
    completed = subprocess.run(
        [
            "node",
            "--input-type=module",
            "--eval",
            script,
            str(command_form_path),
            str(NUMERIC_INPUT_PATH),
            json.dumps(command),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_i2c_trigger_address_maximum_follows_type_without_io() -> None:
    command = next(
        entry for entry in command_catalog() if entry["id"] == "serial-trigger-i2c"
    )
    address = next(field for field in command["fields"] if field["name"] == "address")
    assert address["minimum"] == 0
    assert address["maximum"] == 1023
    assert address["maximum_by_type"]["write10"] == 1023
    assert address["maximum_by_type"]["read7"] == 127
    script = _SERIAL_REAL_FORM_HARNESS + textwrap.dedent(
        r'''
        const { typeInput, addressInput, dataInput, readCalls } = await bootTriggerForm();
        assert.ok(typeInput && addressInput && dataInput);
        assert.equal(addressInput.min, "0");
        assert.equal(addressInput.max, "1023");
        assert.equal(dataInput.min, "0");
        assert.equal(dataInput.max, "255");

        typeInput.value = "write10";
        typeInput.dispatch("change");
        assert.equal(addressInput.max, "1023");

        addressInput.value = "500";
        addressInput.dispatch("change");
        dataInput.value = "165";
        dataInput.dispatch("change");

        const accepted = editor.triggerForm.values();
        assert.equal(accepted.type, "write10");
        assert.equal(accepted.address, 500);
        assert.equal(accepted.data, 165);
        assert.ok(!("data2" in accepted));

        const applyCalls = [];
        controller.applyTrigger = async (values) => { applyCalls.push(values); return null; };
        await editor.submitTrigger();
        assert.equal(applyCalls.length, 1);
        assert.deepEqual(applyCalls[0], { type: "write10", address: 500, data: 165 });
        assert.equal(submitted.length, readCalls);

        typeInput.value = "read7";
        typeInput.dispatch("change");
        assert.equal(addressInput.max, "127");
        assert.equal(addressInput.value, "500");

        addressInput.reported = false;
        assert.equal(editor.triggerForm.values(), null);
        assert.equal(addressInput.reported, true);
        assert.ok(editor.triggerForm.isDirty());
        await editor.submitTrigger();
        assert.equal(applyCalls.length, 1);
        assert.equal(submitted.length, readCalls);

        typeInput.value = "start";
        typeInput.dispatch("change");
        assert.equal(addressInput.value, "500");
        const hiddenValues = editor.triggerForm.values();
        assert.ok(!("address" in hiddenValues));
        await editor.submitTrigger();
        assert.equal(applyCalls.length, 2);
        assert.deepEqual(applyCalls[1], { type: "start" });
        assert.equal(submitted.length, readCalls);
        '''
    )
    completed = subprocess.run(
        [
            "node",
            "--input-type=module",
            "--eval",
            script,
            str(STATIC_ROOT / "serial-editor.js"),
            str(STATIC_ROOT / "command-form.js"),
            str(NUMERIC_INPUT_PATH),
            str(STATIC_ROOT / "locale_en.js"),
            str(STATIC_ROOT / "locale_zh_tw.js"),
            json.dumps(command),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_serial_trigger_form_refreshes_locale_without_io() -> None:
    command = next(
        entry for entry in command_catalog() if entry["id"] == "serial-trigger-i2c"
    )
    script = _SERIAL_REAL_FORM_HARNESS + textwrap.dedent(
        r'''
        const { typeInput, addressInput, dataInput, readCalls } = await bootTriggerForm();

        typeInput.value = "read7";
        typeInput.dispatch("change");
        addressInput.value = "80";
        addressInput.dispatch("change");
        dataInput.value = "165";
        dataInput.dispatch("change");

        const helpFor = (name) => editor.triggerForm.container.querySelectorAll("[data-field-help]")
          .find((node) => node.dataset.fieldHelp === name);
        const labelFor = (name) => editor.triggerForm.container.querySelectorAll("[data-field-label]")
          .find((node) => node.dataset.fieldLabel === name);
        const addressHelp = helpFor("address");
        const addressLabel = labelFor("address");
        assert.ok(addressHelp && addressLabel);
        assert.equal(
          addressHelp.textContent,
          testDicts.en["help.serial-trigger-i2c.address"],
        );
        assert.equal(addressLabel.textContent, testDicts.en["field.address"]);

        globalThis.setRuntimeLocale("zh-TW");
        editor.rerender();

        assert.equal(
          addressHelp.textContent,
          testDicts.zhTW["help.serial-trigger-i2c.address"],
        );
        assert.equal(addressLabel.textContent, testDicts.zhTW["field.address"]);
        assert.equal(addressInput.value, "80");
        assert.ok(editor.triggerForm.isDirty());
        assert.equal(submitted.length, readCalls);
        '''
    )
    completed = subprocess.run(
        [
            "node",
            "--input-type=module",
            "--eval",
            script,
            str(STATIC_ROOT / "serial-editor.js"),
            str(STATIC_ROOT / "command-form.js"),
            str(NUMERIC_INPUT_PATH),
            str(STATIC_ROOT / "locale_en.js"),
            str(STATIC_ROOT / "locale_zh_tw.js"),
            json.dumps(command),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
