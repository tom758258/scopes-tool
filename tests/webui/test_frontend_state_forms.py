from __future__ import annotations

import shutil
import subprocess
import textwrap

import pytest

from tests.webui._frontend_state_test_support import (
    STATIC_ROOT,
    NUMERIC_INPUT_PATH,
    read_static,
    extract_function_declaration,
)

def run_generic_form_ownership_behavior(assertions: str) -> None:
    source = read_static("app.js").replace("options = {}", "options = null", 1)
    declarations = "\n".join(
        extract_function_declaration(source, signature)
        for signature in (
            "async function executeCommand(command, parameters, options = null)",
            "function isExecutionBusy()",
            "function invalidateGenericFormOwnership()",
            "function syncCommandSelection(draft = null)",
        )
    )
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";

        let genericFormRevision = 0;
        let channelLabelVisibility = null;
        let previousEditorKind = null;
        let executing = false;
        let currentJobId = null;
        let pendingResourceLiveSupport = null;
        let deviceResource = null;
        let resultPresentation = { kind: "empty", job: null, message: null };
        const context = { mode: "simulate", resource: null, model_id: "model" };
        const channelScale = { id: "channel-scale", modes: ["simulate"] };
        const otherCommand = { id: "channel-offset", modes: ["simulate"] };
        const commands = [channelScale, otherCommand];
        const elements = {
          deviceStatus: { textContent: "" },
          execute: { disabled: false },
          formHeading: {},
          form: {},
          referenceEditor: {},
          saveExportEditor: {},
          serialDecodeEditor: {},
          serialTriggerEditor: {},
          serialListerEditor: {},
          triggerEditor: {},
          searchEditor: {},
          segmentedEditor: {},
          workflowEditor: {},
          measurementEditor: {},
          cursorEditor: {},
          annotationEditor: {},
          wgenEditor: {},
          demoEditor: {},
          selectedCommand: {},
          commandDescription: {},
          commandSupportReason: {},
          cancel: { classList: { add() {}, remove() {} } },
        };
        const state = { selectedCommand: null };
        let selectedCommand = channelScale;
        const catalog = {
          selected: () => selectedCommand,
          commandLabel: (command) => command.id,
          description: (command) => `${command.id} description`,
          supportReason: () => "",
        };
        const completedResults = [];
        const workspaceResults = [];
        const submissions = [];
        const controllers = [];
        const translate = (key) => key;
        const pcOutputContext = (value) => ({ ...value, pc_output_dir: "data" });
        const renderPcOutputNote = () => {};
        const commandAvailable = () => true;
        const currentWorkspaceContext = () => ({ command: "channel-scale", mode: "simulate" });
        const isCurrentEditorJob = () => true;
        const editorKindFor = () => null;
        const syncWorkspaceHeaderActions = () => {};
        const renderWorkspace = () => {};
        const syncEditorPresentation = () => {};
        const commandAction = () => "apply";
        const updateAvailability = () => {};
        const setExecutionStatus = () => {};
        const renderCurrentResult = () => {
          if (resultPresentation.job?.status === "completed") {
            completedResults.push(resultPresentation.job.job_id);
          }
        };
        const updateIdentity = () => {};
        const captureWorkspaceResult = (job) => workspaceResults.push(job.job_id);
        const makeForm = () => ({
          disabledCalls: [],
          clearCalls: 0,
          syncCalls: [],
          dirty: false,
          render(_command, options) {
            this.renderOptions = options;
            this.disabledCalls = [];
            this.clearCalls = 0;
            this.syncCalls = [];
            this.dirty = true;
          },
          setDisabled(value) { this.disabledCalls.push(value); },
          clearDirty() { this.clearCalls += 1; },
          syncResult(job, preserveDirty) { this.syncCalls.push([job.job_id, preserveDirty]); },
        });
        let commandForm = makeForm();
        const runJob = (command, parameters, commandContext, onUpdate) => {
          const jobId = `job-${submissions.length + 1}`;
          submissions.push({ command, parameters, commandContext, jobId });
          onUpdate({ job_id: jobId, command, status: "queued" });
          return new Promise((resolve) => controllers.push({ jobId, resolve }));
        };
        const complete = (index) => {
          const controller = controllers[index];
          controller.resolve({
            job_id: controller.jobId,
            command: "channel-scale",
            status: "completed",
            result: { result: { channel: 1, volts_per_division: 0.5 } },
          });
        };
        '''
    ) + declarations + textwrap.dedent(assertions)
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_timebase_scale_presets_fill_value_without_execute() -> None:
    styles = read_static("styles.css")
    assert ".timebase-scale-presets, .channel-probe-presets {" in styles
    assert "grid-column: 1 / -1;" in styles
    assert "repeat(5, minmax(0, 1fr))" in styles
    assert "repeat(2, minmax(0, 1fr))" in styles

    command_form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeEl {
          constructor(tag) {
            this.tagName = String(tag).toUpperCase();
            this.children = [];
            this.dataset = {};
            this.attributes = {};
            this.style = {};
            this.className = "";
            this.textContent = "";
            this.hidden = false;
            this.disabled = false;
            this.checked = false;
            this.type = "";
            this.multiple = false;
            this.required = false;
            this.validity = {};
            this._value = "";
            this.options = [];
            this.selectedOptions = [];
            this.parentElement = null;
            this.listeners = {};
            const classes = new Set();
            this.classList = {
              add: (...names) => names.forEach((name) => classes.add(name)),
              contains: (name) => classes.has(name),
            };
          }
          get value() { return this._value; }
          set value(v) { this._value = String(v); }
          append(...nodes) {
            for (const n of nodes) {
              this.children.push(n);
              n.parentElement = this;
              if (n.tagName === "OPTION") {
                this.options.push(n);
                if (n.selected) this.selectedOptions.push(n);
              }
            }
          }
          replaceChildren(...nodes) {
            this.children = [];
            this.options = [];
            this.selectedOptions = [];
            if (nodes.length) this.append(...nodes);
          }
          setAttribute(k, v) { this.attributes[k] = String(v); }
          getAttribute(k) { return this.attributes[k]; }
          addEventListener(type, fn) {
            (this.listeners[type] = this.listeners[type] || []).push(fn);
          }
          dispatchEvent(event) {
            for (const fn of this.listeners[event.type] || []) fn(event);
            return true;
          }
          closest(sel) {
            if (sel === '[data-visible-if-hidden="true"]') {
              let node = this;
              while (node) {
                if (node.dataset?.visibleIfHidden === "true") return node;
                node = node.parentElement;
              }
            }
            return null;
          }
          setCustomValidity() {}
          checkValidity() { return true; }
          reportValidity() {}
          querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
          querySelectorAll(sel) {
            const out = [];
            const mField = sel.match(/^\[data-field="([^"]+)"\]$/);
            const walk = (node) => {
              for (const c of node.children || []) {
                if (sel === "[data-field]" && c.dataset && "field" in c.dataset) out.push(c);
                else if (mField && c.dataset && c.dataset.field === mField[1]) out.push(c);
                else if (sel === "button" && c.tagName === "BUTTON") out.push(c);
                else if (sel === ".timebase-scale-presets"
                  && c.className.split(" ").includes("timebase-scale-presets")) out.push(c);
                else if ([".timebase-scale-presets button", ".channel-probe-presets button"].includes(sel) && c.tagName === "BUTTON") {
                  let p = c.parentElement;
                  let inside = false;
                  while (p) {
                    if (p.className && p.className.split(" ").includes(sel.split(" ")[0].slice(1))) {
                      inside = true;
                      break;
                    }
                    p = p.parentElement;
                  }
                  if (inside) out.push(c);
                }
                else if (sel === "[data-multi-for]" && c.dataset && "multiFor" in c.dataset) out.push(c);
                else if (sel === "[data-visible-if]" && c.dataset && "visibleIf" in c.dataset) out.push(c);
                else if (sel === "[data-help-by-value]" && c.dataset && "helpByValue" in c.dataset) out.push(c);
                else if (sel === "span" && c.tagName === "SPAN") out.push(c);
                walk(c);
              }
            };
            walk(this);
            return out;
          }
        }
        globalThis.document = { createElement: (tag) => new FakeEl(tag) };
        globalThis.Option = function (text, value) {
          const o = new FakeEl("option");
          o.textContent = text;
          o.value = String(value);
          return o;
        };
        globalThis.Event = class Event {
          constructor(type, init) {
            this.type = type;
            this.bubbles = init?.bubbles;
          }
        };
        globalThis.HTMLElement = FakeEl;

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

        const expected = [
          ["100 ns/div", "0.0000001"],
          ["1 µs/div", "0.000001"],
          ["10 µs/div", "0.00001"],
          ["100 µs/div", "0.0001"],
          ["1 ms/div", "0.001"],
          ["10 ms/div", "0.01"],
          ["20 ms/div", "0.02"],
          ["100 ms/div", "0.1"],
          ["200 ms/div", "0.2"],
          ["1 s/div", "1"],
        ];
        const catalog = {
          fieldsFor: (cmd) => cmd.fields,
          optionsFor: (field) => field?.options || [],
        };
        const timebaseScale = {
          id: "timebase-scale",
          fields: [
            { name: "action", type: "enum", options: ["query", "set"] },
            {
              name: "seconds_per_division",
              type: "number",
              exclusive_minimum: 0,
              help_key: "timebase.seconds_per_division",
            },
          ],
          presentation: {
            kind: "setting",
            action_field: "action",
            query_value: "query",
            apply_value: "set",
            query_fields: [],
          },
        };

        const dirtyCalls = [];
        const queryCalls = [];
        const container = new FakeEl("form");
        const form = new globalThis.CommandForm(container, catalog);
        form.render(timebaseScale, {
          onDirty: (field) => dirtyCalls.push(field),
          onQueryFieldChange: (field) => queryCalls.push(field),
        });

        const presetHost = container.children.find((child) => child.className
          .split(" ")
          .includes("timebase-scale-presets"));
        assert.ok(presetHost, "presets render for timebase-scale");
        const fieldWrapper = container.children.find((child) => child.tagName === "LABEL");
        assert.ok(fieldWrapper, "seconds field wrapper renders");
        assert.ok(
          container.children.indexOf(presetHost) > container.children.indexOf(fieldWrapper),
          "presets sit after the field as a form sibling",
        );
        const labelButtons = [];
        {
          const walk = (node) => {
            for (const child of node.children || []) {
              if (child.tagName === "BUTTON") labelButtons.push(child);
              walk(child);
            }
          };
          walk(fieldWrapper);
        }
        assert.equal(labelButtons.length, 0);

        const buttons = presetHost.children.filter((child) => child.tagName === "BUTTON");
        assert.equal(buttons.length, 10);
        assert.deepEqual(buttons.map((button) => button.textContent), expected.map(([label]) => label));
        buttons.forEach((button) => assert.equal(button.type, "button"));

        const input = container.querySelector('[data-field="seconds_per_division"]');
        assert.ok(input);
        for (const [label, value] of expected) {
          const button = buttons.find((candidate) => candidate.textContent === label);
          assert.ok(button, label);
          const before = dirtyCalls.length;
          button.dispatchEvent(new globalThis.Event("click", { bubbles: true }));
          assert.equal(input.value, value);
          assert.equal(input.dataset.dirty, "true");
          assert.equal(dirtyCalls.length, before + 1);
          assert.equal(dirtyCalls[dirtyCalls.length - 1], "seconds_per_division");
          assert.equal(form.values().seconds_per_division, Number(value));
        }
        assert.equal(queryCalls.length, 0);
        assert.deepEqual(form.queryValues(), { action: "query" });

        form.setDisabled(true);
        assert.equal(input.disabled, true);
        buttons.forEach((button) => assert.equal(button.disabled, true));
        buttons[0].dispatchEvent(new globalThis.Event("click", { bubbles: true }));
        assert.equal(input.value, expected[expected.length - 1][1]);
        form.setDisabled(false);
        assert.equal(input.disabled, false);
        buttons.forEach((button) => assert.equal(button.disabled, false));

        form.render({
          id: "channel-probe",
          fields: [
            { name: "action", type: "enum", options: ["query", "set"] },
            { name: "channel", type: "integer", default: 1 },
            { name: "ratio", type: "number", exclusive_minimum: 0 },
          ],
          presentation: { ...timebaseScale.presentation, query_fields: ["channel"] },
        }, {
          onDirty: (field) => dirtyCalls.push(field),
          onQueryFieldChange: (field) => queryCalls.push(field),
        });
        const ratioInput = container.querySelector('[data-field="ratio"]');
        const probeButtons = container.querySelectorAll("button");
        const ratios = [1, 10, 20, 100, 1000];
        assert.equal(probeButtons.length, 5);
        assert.deepEqual(probeButtons.map((button) => button.textContent), ratios.map((ratio) => `${ratio}:1`));
        assert.ok(container.children.indexOf(probeButtons[0].parentElement) > container.children.indexOf(ratioInput.parentElement));
        probeButtons.forEach((button, index) => {
          assert.equal(button.type, "button");
          form.clearDirty();
          const before = dirtyCalls.length;
          button.dispatchEvent(new globalThis.Event("click", { bubbles: true }));
          assert.equal(ratioInput.value, String(ratios[index]));
          assert.equal(ratioInput.dataset.dirty, "true");
          assert.equal(dirtyCalls.length, before + 1);
          assert.equal(dirtyCalls.at(-1), "ratio");
        });
        assert.equal(queryCalls.length, 0);
        form.setDisabled(true);
        assert.equal(ratioInput.disabled, true);
        probeButtons.forEach((button) => assert.equal(button.disabled, true));
        probeButtons[0].dispatchEvent(new globalThis.Event("click"));
        assert.equal(ratioInput.value, "1000");
        form.setDisabled(false);
        probeButtons.forEach((button) => assert.equal(button.disabled, false));

        form.render({
          id: "timebase-position",
          fields: [
            { name: "action", type: "enum", options: ["query", "set"] },
            { name: "position_seconds", type: "number" },
          ],
          presentation: {
            kind: "setting",
            action_field: "action",
            query_value: "query",
            apply_value: "set",
            query_fields: [],
          },
        }, {});
        assert.equal(container.querySelectorAll("button").length, 0);
        assert.equal(container.querySelector(".timebase-scale-presets"), null);
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
def test_generic_form_multi_choice_and_two_state_boolean_presentation() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.testTranslate = (key) => key;
        globalThis.testHasTranslation = () => false;

        class FakeElement {
          constructor(tag) {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.attributes = {};
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.required = false;
            this.multiple = false;
            this.tabIndex = 0;
            this.type = "";
            this.value = "";
            this.checked = false;
            this.textContent = "";
            this.className = "";
            this.options = [];
            this.validity = { badInput: false };
            if (tag === "select") {
              const owner = this;
              Object.defineProperty(this, "value", {
                get() {
                  return owner.options.find((option) => option.selected)?.value ?? "";
                },
                set(next) {
                  owner.options.forEach((option) => {
                    option.selected = option.value === String(next);
                  });
                },
              });
            } else {
              this.value = "";
            }
            const self = this;
            this.classList = {
              add: (...names) => {
                const set = new Set(self.className.split(/\s+/).filter(Boolean));
                names.forEach((name) => set.add(name));
                self.className = [...set].join(" ");
              },
              contains: (name) => self.className.split(/\s+/).includes(name),
            };
          }
          get classListContains() { return null; }
          append(...nodes) {
            for (const node of nodes) {
              this.children.push(node);
              if (this.tagName === "SELECT" && node.selected !== undefined) this.options.push(node);
            }
          }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          setAttribute(name, value) { this.attributes[name] = String(value); }
          getAttribute(name) { return this.attributes[name]; }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatchEvent(event) { for (const handler of this.listeners[event.type] || []) handler(event); return true; }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          get selectedOptions() { return this.options.filter((option) => option.selected); }
          closest() { return null; }
          setCustomValidity() {}
          reportValidity() {}
          checkValidity() { return true; }
        }

        globalThis.document = { createElement: (tag) => new FakeElement(tag) };
        globalThis.Option = function Option(text, value) {
          return { textContent: text, value: String(value), selected: false };
        };

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

        const matches = (element, selector) => {
          const match = selector.match(/^\[data-([a-zA-Z-]+)(?:="([^"]*)")?\]$/);
          if (!match || !element.dataset) return false;
          const property = match[1].replace(/-([a-z])/g, (_all, char) => char.toUpperCase());
          if (match[2] === undefined) return element.dataset[property] !== undefined;
          return element.dataset[property] === match[2];
        };
        const collect = (node, out = []) => {
          for (const child of node.children || []) {
            out.push(child);
            collect(child, out);
          }
          return out;
        };
        const container = new FakeElement("div");
        container.querySelectorAll = (selector) => collect(container).filter((node) => matches(node, selector));
        container.querySelector = (selector) => container.querySelectorAll(selector)[0] || null;

        const catalog = { fieldsFor: (command) => command.fields, optionsFor: (field) => field.options };
        const command = {
          id: "measure-log",
          presentation: null,
          fields: [
            { name: "channels", type: "multi-enum", options: ["1", "2", "3", "4"], serialize: "csv" },
            { name: "items", type: "multi-enum", options: ["vpp", "frequency", "period"], serialize: "csv", default: ["vpp", "frequency"] },
            { name: "pairs", type: "string" },
            { name: "stop_on_error", type: "boolean", default: false },
            { name: "enabled_setting", type: "boolean" },
          ],
        };
        const form = new globalThis.CommandForm(container, catalog);
        form.render(command);

        const byField = (name) => collect(container).find((node) => node.dataset?.field === name);
        const boxesFor = (name) => collect(container).filter((node) => node.dataset?.multiFor === name);
        const toggleChip = (box) => { box.checked = !box.checked; box.dispatchEvent({ type: "change" }); };

        const channelsWrapper = container.children.find((node) => node.classList.contains("field-multi"));
        assert.ok(channelsWrapper, "multi-enum wrapper should carry the full-width class");
        assert.equal(channelsWrapper.tagName, "DIV");

        const channelsSelect = byField("channels");
        assert.equal(channelsSelect.multiple, true);
        assert.equal(channelsSelect.dataset.multiSource, "true");
        assert.equal(channelsSelect.getAttribute("aria-hidden"), "true");
        assert.equal(channelsSelect.tabIndex, -1);
        assert.equal(channelsSelect.className, "visually-hidden");

        const channelBoxes = boxesFor("channels");
        assert.deepEqual(channelBoxes.map((box) => box.value), ["1", "2", "3", "4"]);
        assert.equal(channelBoxes.every((box) => box.checked === false), true);

        const itemBoxes = boxesFor("items");
        assert.deepEqual(
          itemBoxes.filter((box) => box.checked).map((box) => box.value),
          ["vpp", "frequency"],
        );

        const stopError = byField("stop_on_error");
        assert.equal(stopError.tagName, "INPUT");
        assert.equal(stopError.type, "checkbox");
        assert.equal(stopError.checked, false);
        const booleanWrapper = collect(container).find((node) =>
          node.classList?.contains("field-boolean"));
        assert.ok(booleanWrapper, "plain two-state boolean should carry the compact class");
        assert.equal(
          booleanWrapper.children.find((node) => node.type === "checkbox"),
          stopError,
        );
        assert.equal(booleanWrapper.children.some((node) => node.tagName === "SPAN"), true);

        const settingBoolean = byField("enabled_setting");
        assert.equal(settingBoolean.tagName, "SELECT");
        assert.deepEqual(settingBoolean.options.map((option) => option.value), ["", "true", "false"]);

        toggleChip(channelBoxes[0]);
        toggleChip(channelBoxes[2]);
        toggleChip(itemBoxes[1]);
        assert.equal(channelsSelect.dataset.dirty, "true");
        assert.equal(form.isDirty(), true);
        assert.deepEqual(form.values(), {
          channels: "1,3",
          items: "vpp",
          stop_on_error: false,
        });

        stopError.checked = true;
        stopError.dispatchEvent({ type: "change" });
        assert.deepEqual(form.values().stop_on_error, true);
        stopError.checked = false;
        stopError.dispatchEvent({ type: "change" });

        const snapshot = form.draft();
        toggleChip(channelBoxes[0]);
        form.restoreDraft(snapshot);
        assert.deepEqual(
          channelsSelect.selectedOptions.map((option) => option.value),
          ["1", "3"],
        );
        assert.deepEqual(
          boxesFor("channels").filter((box) => box.checked).map((box) => box.value),
          ["1", "3"],
        );

        form.setDisabled(true);
        assert.equal(channelsSelect.disabled, true);
        assert.equal(channelBoxes.every((box) => box.disabled), true);
        form.setDisabled(false);
        assert.equal(channelBoxes.some((box) => box.disabled), false);
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
def test_query_selector_change_invalidates_pending_generic_refresh() -> None:
    run_generic_form_ownership_behavior(
        r'''
        syncCommandSelection();
        const submittedRevision = genericFormRevision;
        const refresh = executeCommand("channel-scale", { action: "query", channel: 1 }, {
          intent: "readback",
          formRevision: submittedRevision,
        });
        await Promise.resolve();
        commandForm.renderOptions.onQueryFieldChange("channel");
        assert.equal(submissions.length, 1);

        complete(0);
        await refresh;

        assert.deepEqual(commandForm.syncCalls, []);
        assert.deepEqual(workspaceResults, ["job-1"]);
        assert.deepEqual(completedResults, ["job-1"]);
        '''
    )

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_nested_same_name_readback_hydrates_scalar() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    numeric_input_path = STATIC_ROOT / "numeric-input.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.testTranslate = (key) => key;
        globalThis.testHasTranslation = () => false;

        class FakeElement {
          constructor(tag) {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.attributes = {};
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.required = false;
            this.multiple = false;
            this.tabIndex = 0;
            this.type = "";
            this.checked = false;
            this.textContent = "";
            this.className = "";
            this.options = [];
            this.validity = { badInput: false };
            if (tag === "select") {
              const owner = this;
              Object.defineProperty(this, "value", {
                get() {
                  return owner.options.find((option) => option.selected)?.value ?? "";
                },
                set(next) {
                  owner.options.forEach((option) => {
                    option.selected = option.value === String(next);
                  });
                },
              });
            } else {
              this.value = "";
            }
            const self = this;
            this.classList = {
              add: (...names) => {
                const set = new Set(self.className.split(/\s+/).filter(Boolean));
                names.forEach((name) => set.add(name));
                self.className = [...set].join(" ");
              },
              contains: (name) => self.className.split(/\s+/).includes(name),
            };
          }
          append(...nodes) {
            for (const node of nodes) {
              this.children.push(node);
              if (this.tagName === "SELECT" && node.selected !== undefined) this.options.push(node);
            }
          }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          setAttribute(name, value) { this.attributes[name] = String(value); }
          getAttribute(name) { return this.attributes[name]; }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatchEvent(event) { for (const handler of this.listeners[event.type] || []) handler(event); return true; }
          get selectedOptions() { return this.options.filter((option) => option.selected); }
          closest() { return null; }
          setCustomValidity() {}
          reportValidity() {}
          checkValidity() { return true; }
        }

        globalThis.document = { createElement: (tag) => new FakeElement(tag) };
        globalThis.Option = function Option(text, value) {
          return { textContent: text, value: String(value), selected: false };
        };
        globalThis.Event = function Event(type) { this.type = type; };

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

        const matches = (element, selector) => {
          const match = selector.match(/^\[data-([a-zA-Z-]+)(?:="([^"]*)")?\]$/);
          if (!match || !element.dataset) return false;
          const property = match[1].replace(/-([a-z])/g, (_all, char) => char.toUpperCase());
          if (match[2] === undefined) return element.dataset[property] !== undefined;
          return element.dataset[property] === match[2];
        };
        const collect = (node, out = []) => {
          for (const child of node.children || []) {
            out.push(child);
            collect(child, out);
          }
          return out;
        };
        const catalog = { fieldsFor: (command) => command.fields, optionsFor: (field) => field.options || [] };
        const setting = (id, fields) => ({
          id,
          presentation: { kind: "setting", action_field: "action", apply_value: "set", query_value: "query", query_fields: [] },
          fields: [{ name: "action", type: "enum", options: ["query", "set"], default: "query" }, ...fields],
        });
        const runCase = (fieldName, expected, fields, payload) => {
          const container = new FakeElement("div");
          container.querySelectorAll = (selector) => collect(container).filter((node) => matches(node, selector));
          container.querySelector = (selector) => container.querySelectorAll(selector)[0] || null;
          const form = new globalThis.formApi.CommandForm(container, catalog);
          form.render(setting(`test-${fieldName}`, fields), {});
          form.syncResult({ status: "completed", result: { result: payload } }, false);
          const input = collect(container).find((node) => node.dataset?.field === fieldName);
          assert.equal(input.value, expected);
        };

        const enumField = (name, options) => ({ name, type: "enum", options });
        // Production Trigger readbacks wrap the canonical field in a
        // same-name object; the scalar inside must hydrate the control.
        // The source case renders two writable fields so the fix cannot
        // rely on the single-writable-field fallback.
        const cases = [
          ["source", "external", [
            enumField("source", ["analog-channel", "external", "line"]),
            { name: "source_channel", type: "integer" },
          ], { source: { source: "external", source_channel: null, raw_source: "EXT" } }],
          ["slope", "negative", [
            enumField("slope", ["positive", "negative", "either", "alternate"]),
          ], { slope: { slope: "negative", raw_slope: "NEG" } }],
          ["units", "amps", [
            enumField("units", ["volts", "amps"]),
          ], { units: { units: "amps", raw_units: "AMP" } }],
          ["coupling", "dc", [
            enumField("coupling", ["ac", "dc", "lf-reject"]),
          ], { coupling: { coupling: "dc", raw_value: "DC" } }],
          ["reject", "off", [
            enumField("reject", ["off", "lf-reject", "hf-reject"]),
          ], { reject: { reject: "off", raw_value: "OFF" } }],
        ];
        for (const [fieldName, expected, fields, payload] of cases) {
          runCase(fieldName, expected, fields, payload);
        }

        // A deeper same-name match must not hydrate the control; only the
        // single-level wrapper collision is resolved.
        runCase("foo", "", [enumField("foo", ["a", "b"])], { foo: { bar: { foo: "value" } } });
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(command_form_path), str(numeric_input_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_generic_rerender_rejects_stale_apply_form_updates() -> None:
    run_generic_form_ownership_behavior(
        r'''
        syncCommandSelection();
        const apply = executeCommand("channel-scale", {
          action: "set", channel: 1, volts_per_division: 0.5,
        }, { intent: "apply", formRevision: genericFormRevision });
        await Promise.resolve();
        assert.deepEqual(commandForm.disabledCalls, [true]);

        selectedCommand = otherCommand;
        syncCommandSelection();
        selectedCommand = channelScale;
        syncCommandSelection();
        complete(0);
        await apply;

        assert.equal(commandForm.clearCalls, 0);
        assert.deepEqual(commandForm.syncCalls, []);
        assert.deepEqual(commandForm.disabledCalls, []);
        assert.equal(commandForm.dirty, true);
        assert.deepEqual(workspaceResults, ["job-1"]);
        assert.deepEqual(completedResults, ["job-1"]);
        '''
    )

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_current_generic_form_still_syncs_refresh_and_apply() -> None:
    run_generic_form_ownership_behavior(
        r'''
        syncCommandSelection();
        const refresh = executeCommand("channel-scale", { action: "query", channel: 1 }, {
          intent: "readback",
          formRevision: genericFormRevision,
        });
        await Promise.resolve();
        complete(0);
        await refresh;
        assert.deepEqual(commandForm.syncCalls, [["job-1", true]]);
        assert.equal(commandForm.clearCalls, 0);

        const apply = executeCommand("channel-scale", {
          action: "set", channel: 1, volts_per_division: 0.5,
        }, { intent: "apply", formRevision: genericFormRevision });
        await Promise.resolve();
        complete(1);
        await apply;
        assert.deepEqual(commandForm.syncCalls, [["job-1", true], ["job-2", false]]);
        assert.equal(commandForm.clearCalls, 1);
        assert.deepEqual(commandForm.disabledCalls, [true, false]);
        assert.deepEqual(workspaceResults, ["job-1", "job-2"]);
        assert.deepEqual(completedResults, ["job-1", "job-2"]);
        '''
    )

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_submission_without_form_revision_cannot_update_generic_form() -> None:
    run_generic_form_ownership_behavior(
        r'''
        syncCommandSelection();
        const apply = executeCommand("channel-scale", {
          action: "set", channel: 1, volts_per_division: 0.5,
        }, { intent: "apply" });
        await Promise.resolve();
        assert.deepEqual(commandForm.disabledCalls, []);

        complete(0);
        await apply;

        assert.equal(commandForm.clearCalls, 0);
        assert.deepEqual(commandForm.syncCalls, []);
        assert.deepEqual(commandForm.disabledCalls, []);
        assert.deepEqual(workspaceResults, ["job-1"]);
        assert.deepEqual(completedResults, ["job-1"]);
        '''
    )

def test_hidden_elements_override_component_display_rules() -> None:
    styles = read_static("styles.css")

    assert "[hidden] { display: none !important; }" in styles

def test_numeric_inputs_share_spinner_presentation_rules() -> None:
    command_form = read_static("command-form.js")
    workflow_editor = read_static("workflow-editor.js")
    helper = read_static("numeric-input.js")

    assert 'from "/static/numeric-input.js";' in command_form
    assert 'from "/static/numeric-input.js";' in workflow_editor
    assert 'input.step = "any";' in helper

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_generic_form_rejects_partial_numbers_and_fractional_integers() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const translate = (key) => key;
        const hasTranslation = () => false;
        globalThis.testTranslate = translate;
        globalThis.testHasTranslation = hasTranslation;

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

        const input = (name, type, value, required = false) => ({
          value,
          required,
          type: "number",
          dataset: { field: name, type },
          validity: { badInput: false },
          customValidity: "",
          reported: false,
          closest: () => null,
          setCustomValidity(message) { this.customValidity = message; },
          checkValidity() { return this.customValidity === ""; },
          reportValidity() { this.reported = true; return false; },
        });
        const valuesFor = (...elements) => {
          const container = { querySelectorAll: () => elements };
          return new globalThis.formApi.CommandForm(container, null).values();
        };

        const trailing = input("value", "number", "1abc");
        assert.equal(valuesFor(trailing), null);
        assert.equal(trailing.reported, true);

        assert.equal(valuesFor(input("value", "number", "0x10")), null);

        const fractional = input("count", "integer", "1.9");
        assert.equal(valuesFor(fractional), null);

        const required = input("count", "integer", "", true);
        assert.equal(valuesFor(required), null);

        assert.deepEqual(
          valuesFor(input("value", "number", "-1.25e2"), input("count", "integer", "19")),
          { value: -125, count: 19 },
        );

        globalThis.document = {
          createElement: (tag) => {
            const classes = new Set();
            return {
              tagName: tag.toUpperCase(),
              children: [],
              dataset: {},
              value: "",
              type: "",
              required: false,
              customValidity: "",
              classList: {
                add: (...names) => names.forEach((name) => classes.add(name)),
                contains: (name) => classes.has(name),
              },
              append(...nodes) { this.children.push(...nodes); },
              setCustomValidity(message) { this.customValidity = message; },
              checkValidity() {
                if (this.customValidity !== "") return false;
                if (this.required && this.value === "") return false;
                if (this.value !== "" && this.type === "number") {
                  const value = Number(this.value);
                  if (!Number.isFinite(value)) return false;
                  if (this.min !== undefined && value < Number(this.min)) return false;
                  if (this.max !== undefined && value > Number(this.max)) return false;
                  if (this.step === "1" && !Number.isInteger(value)) return false;
                }
                return true;
              },
              reportValidity() { this.reported = true; return false; },
              closest: () => null,
            };
          },
        };
        const renderedForm = new globalThis.formApi.CommandForm({}, { optionsFor: () => [] });
        const renderedInput = (field) => renderedForm.field(field).children[1];

        const timeout = renderedInput({
          name: "seconds_per_division",
          type: "number",
          exclusive_minimum: 0,
          required: true,
        });
        assert.equal(timeout.type, "number");
        assert.equal(timeout.step, "any");
        assert.equal(timeout.min, "0");
        assert.equal(timeout.dataset.exclusiveMinimum, "0");
        assert.equal(timeout.classList.contains("no-number-spinner"), true);
        timeout.value = "0";
        assert.equal(valuesFor(timeout), null);
        assert.equal(timeout.customValidity, "form.greaterThan");
        assert.equal(timeout.reported, true);

        timeout.value = "-1";
        assert.equal(valuesFor(timeout), null);

        timeout.value = "1e-12";
        assert.deepEqual(valuesFor(timeout), { seconds_per_division: 1e-12 });

        const skew = renderedInput({
          name: "seconds",
          type: "number",
          minimum: -1e-7,
          maximum: 1e-7,
        });
        assert.equal(skew.min, "-1e-7");
        assert.equal(skew.max, "1e-7");
        assert.equal(skew.classList.contains("no-number-spinner"), true);
        skew.value = "-5e-8";
        assert.deepEqual(valuesFor(skew), { seconds: -5e-8 });
        skew.value = "-2e-7";
        assert.equal(valuesFor(skew), null);

        const width = renderedInput({
          name: "width",
          type: "integer",
          minimum: 4,
          maximum: 64,
        });
        assert.equal(width.step, "1");
        assert.equal(width.min, "4");
        assert.equal(width.max, "64");
        assert.equal(width.classList.contains("no-number-spinner"), false);
        width.value = "8";
        assert.deepEqual(valuesFor(width), { width: 8 });
        width.value = "8.5";
        assert.equal(valuesFor(width), null);

        const baud = renderedInput({
          name: "baud_rate",
          type: "integer",
          minimum: 10000,
          maximum: 5000000,
          spinner: false,
        });
        assert.equal(baud.step, "1");
        assert.equal(baud.classList.contains("no-number-spinner"), true);
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
def test_generic_form_applies_conditional_required_fields() -> None:
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
          + "\nglobalThis.CommandForm = CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const input = (name, type, value, requiredIf = null) => ({
          value,
          required: false,
          type: type === "integer" || type === "number" ? "number" : "select-one",
          dataset: {
            field: name,
            type,
            required: "false",
            ...(requiredIf ? { requiredIf: JSON.stringify(requiredIf) } : {}),
          },
          validity: { badInput: false },
          closest: () => null,
          setCustomValidity() {},
          checkValidity() { return true; },
          reportValidity() { this.reported = true; return false; },
        });
        const action = input("action", "enum", "query");
        const value = input("volts_per_division", "number", "", [
          { field: "action", equals: "set" },
        ]);
        const hiddenValue = input("hidden_value", "number", "", [
          { field: "action", equals: "set" },
        ]);
        hiddenValue.closest = (selector) => (
          selector === "[data-visible-if-hidden=\"true\"]" ? {} : null
        );
        const fields = [action, value, hiddenValue];
        const container = {
          querySelectorAll(selector) {
            if (selector === "[data-visible-if]") return [];
            if (selector === "[data-field]") return fields;
            return [];
          },
          querySelector(selector) {
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return fields.find((field) => field.dataset.field === match?.[1]) ?? null;
          },
        };
        const form = new globalThis.CommandForm(container, null);

        form.refreshVisibility();
        assert.equal(value.required, false);
        assert.equal(hiddenValue.required, false);
        assert.deepEqual(form.values(), { action: "query" });

        action.value = "set";
        form.refreshVisibility();
        assert.equal(value.required, true);
        assert.equal(hiddenValue.required, false);
        assert.equal(form.values(), null);
        assert.equal(value.reported, true);

        value.value = "2.5";
        assert.deepEqual(form.values(), { action: "set", volts_per_division: 2.5 });
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
def test_stateful_editor_readback_dirty_and_verification_flow() -> None:
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
          + "\nglobalThis.CommandForm = CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const field = (name, type, value, queryField = false) => ({
          value,
          type: name === "action" ? "hidden" : "number",
          disabled: false,
          required: false,
          dataset: { field: name, type, queryField: String(queryField) },
          validity: { badInput: false },
          closest: () => null,
          setCustomValidity() {},
          checkValidity() { return true; },
          reportValidity() {},
        });
        const action = field("action", "enum", "set");
        const channel = field("channel", "integer", "1", true);
        const scale = field("volts_per_division", "number", "");
        const fields = [action, channel, scale];
        const container = {
          querySelectorAll(selector) {
            if (selector === "[data-field]") return fields;
            return [];
          },
          querySelector(selector) {
            if (selector === '[data-dirty="true"]') {
              return fields.find((item) => item.dataset.dirty === "true") || null;
            }
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return fields.find((item) => item.dataset.field === match?.[1]) || null;
          },
        };
        const form = new globalThis.CommandForm(container, null);
        form.presentation = {
          kind: "setting", action_field: "action", query_value: "query",
          apply_value: "set", query_fields: ["channel"],
        };

        assert.deepEqual(form.queryValues(), { action: "query", channel: 1 });
        form.syncResult({ result: { result: { channel: 1, volts_per_division: 0.5 } } });
        assert.equal(scale.value, "0.5");

        scale.value = "0.8";
        scale.dataset.dirty = "true";
        form.syncResult({ result: { result: { channel: 1, volts_per_division: 1 } } }, true);
        assert.equal(scale.value, "0.8");
        assert.equal(form.isDirty(), true);

        form.clearDirty();
        form.syncResult({ result: { result: { channel: 1, volts_per_division: 1 } } }, false);
        assert.equal(scale.value, "1");
        assert.equal(form.isDirty(), false);
        assert.deepEqual(form.values(), { action: "set", channel: 1, volts_per_division: 1 });

        form.setDisabled(true);
        assert.equal(channel.disabled, true);
        assert.equal(scale.disabled, true);
        assert.equal(action.disabled, false);
        form.setDisabled(false);
        assert.equal(channel.disabled, false);
        assert.equal(scale.disabled, false);

        const source1 = field("source_channel", "integer", "");
        const source2 = field("source2_channel", "integer", "");
        const aliasFields = [source1, source2];
        const aliasContainer = {
          querySelectorAll(selector) { return selector === "[data-field]" ? aliasFields : []; },
          querySelector(selector) {
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return aliasFields.find((item) => item.dataset.field === match?.[1]) || null;
          },
        };
        const aliasForm = new globalThis.CommandForm(aliasContainer, null);
        aliasForm.presentation = { readback_fields: { source_channel: "source1_channel" } };
        aliasForm.syncResult({ result: { result: {
          source: { source1_channel: 2, source2_channel: 3 },
        } } });
        assert.equal(source1.value, "2");
        assert.equal(source2.value, "3");

        const rangeValue = field("range_value", "number", "");
        const mathContainer = {
          querySelectorAll(selector) { return selector === "[data-field]" ? [rangeValue] : []; },
          querySelector() { return rangeValue; },
        };
        const mathForm = new globalThis.CommandForm(mathContainer, null);
        mathForm.presentation = { readback_fields: { range_value: "range" } };
        mathForm.syncResult({ result: { result: { math_vertical: { range: 4 } } } });
        assert.equal(rangeValue.value, "4");

        const pulseField = (name) => field(name, "number", "");
        const pulseQualifier = field("qualifier", "enum", "");
        pulseQualifier.type = "select-one";
        const pulseTime = pulseField("time_seconds");
        const pulseMin = pulseField("min_time_seconds");
        const pulseMax = pulseField("max_time_seconds");
        const pulseLevel = pulseField("level");
        const pulseFields = [pulseQualifier, pulseTime, pulseMin, pulseMax, pulseLevel];
        const pulseContainer = {
          querySelectorAll(selector) { return selector === "[data-field]" ? pulseFields : []; },
          querySelector(selector) {
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return pulseFields.find((item) => item.dataset.field === match?.[1]) || null;
          },
        };
        const pulseForm = new globalThis.CommandForm(pulseContainer, null);
        pulseForm.presentation = { readback_fields: {
          time_seconds: {
            selector_field: "qualifier",
            fields: {
              "greater-than": "greater_than_seconds",
              "less-than": "less_than_seconds",
            },
          },
          min_time_seconds: "range_min_seconds",
          max_time_seconds: "range_max_seconds",
          level: "level_volts",
        } };
        pulseForm.syncResult({ result: { result: {
          qualifier: "greater-than", greater_than_seconds: 0.001,
          range_min_seconds: null, range_max_seconds: null, level_volts: 1.5,
        } } });
        assert.equal(pulseTime.value, "0.001");
        assert.equal(pulseLevel.value, "1.5");
        assert.equal(pulseMin.value, "");
        assert.equal(pulseMax.value, "");

        pulseForm.syncResult({ result: { result: {
          qualifier: "range", greater_than_seconds: null,
          range_min_seconds: 0.002, range_max_seconds: 0.003,
        } } });
        assert.equal(pulseMin.value, "0.002");
        assert.equal(pulseMax.value, "0.003");

        const tvMode = field("mode", "enum", "");
        const tvContainer = {
          querySelectorAll(selector) { return selector === "[data-field]" ? [tvMode] : []; },
          querySelector() { return tvMode; },
        };
        const tvForm = new globalThis.CommandForm(tvContainer, null);
        tvForm.presentation = { readback_fields: { mode: "tv_mode" } };
        tvForm.syncResult({ result: { result: { mode: "tv", tv_mode: "field2" } } });
        assert.equal(tvMode.value, "field2");

        const bus = field("bus", "integer", "2", true);
        bus.checkValidity = () => Number(bus.value) <= 1;
        const busContainer = {
          querySelectorAll(selector) { return selector === "[data-field]" ? [bus] : []; },
          querySelector() { return bus; },
        };
        const busForm = new globalThis.CommandForm(busContainer, null);
        busForm.presentation = {
          kind: "setting", action_field: "action", query_value: "query", query_fields: ["bus"],
        };
        assert.equal(busForm.queryValues(), null);
        bus.value = "1";
        assert.deepEqual(busForm.queryValues(), { action: "query", bus: 1 });
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
def test_workflow_multi_select_serializes_the_existing_csv_contract() -> None:
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
          + "\nglobalThis.CommandForm = CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const channels = {
          value: "1",
          type: "select-multiple",
          multiple: true,
          selectedOptions: [{ value: "1" }, { value: "2" }],
          dataset: { field: "channels", type: "multi-enum", serialize: "csv" },
          required: true,
          validity: { badInput: false },
          closest: () => null,
          setCustomValidity() {},
          checkValidity() { return this.selectedOptions.length > 0; },
          reportValidity() {},
        };
        const container = {
          querySelectorAll(selector) { return selector === "[data-field]" ? [channels] : []; },
        };
        const form = new globalThis.CommandForm(container, null);
        assert.deepEqual(form.values(), { channels: "1,2" });

        channels.value = "";
        channels.selectedOptions = [];
        assert.equal(form.values(), null);
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
def test_acquisition_form_shows_average_count_only_after_readback() -> None:
    form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const translations = {
          "help.acquisition.type.average": "Average help",
          "help.acquisition.type.peak": "Peak help",
        };
        globalThis.testTranslate = (key) => translations[key] ?? key;
        globalThis.testHasTranslation = (key) => key in translations;
        globalThis.Option = class {
          constructor(text, value) { this.textContent = text; this.value = value; }
        };
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

        const type = {
          dataset: { field: "type", type: "enum" },
          type: "select-one", value: "", closest: () => null,
        };
        const count = {
          dataset: { field: "count", type: "integer", queryField: "false" },
          type: "number", value: "", closest: () => null,
        };
        const wrapper = {
          dataset: { visibleIf: JSON.stringify([{ field: "type", equals: "average" }]) },
          hidden: false,
        };
        const help = {
          dataset: {
            helpByValue: JSON.stringify({
              average: "acquisition.type.average",
              peak: "acquisition.type.peak",
            }),
            helpFor: "type",
          },
          textContent: "",
          hidden: false,
        };
        const container = {
          querySelectorAll(selector) {
            if (selector === "[data-help-by-value]") return [help];
            if (selector === "[data-visible-if]") return [wrapper];
            if (selector === "[data-field]") return [type, count];
            return [];
          },
          querySelector(selector) {
            return selector.includes('"type"') ? type : null;
          },
        };
        const form = new globalThis.CommandForm(container, null);
        form.presentation = { readback_fields: {} };
        form.syncResult({ result: { type: "normal", count: 16 } });
        assert.equal(type.value, "normal");
        assert.equal(wrapper.hidden, true);
        form.syncResult({ result: { type: "average", count: 16 } });
        assert.equal(type.value, "average");
        assert.equal(count.value, "16");
        assert.equal(wrapper.hidden, false);
        assert.equal(help.textContent, "Average help");
        assert.equal(help.hidden, false);
        form.syncResult({ result: { type: "peak", count: 16 } });
        assert.equal(type.value, "peak");
        assert.equal(wrapper.hidden, true);
        assert.equal(help.textContent, "Peak help");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(form_path), str(NUMERIC_INPUT_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
