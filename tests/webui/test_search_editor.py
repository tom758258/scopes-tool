from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_webui.commands import COMMANDS, command_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
SEARCH_EDITOR_SOURCE = STATIC_ROOT / "search-editor.js"
COMMAND_FORM_SOURCE = STATIC_ROOT / "command-form.js"


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


EXPECTED_SEARCH_GROUPS = {
    "search-state": "basic",
    "search-mode": "basic",
    "search-count": "basic",
    "search-event": "event",
    "serial-search-uart": "serial",
    "serial-search-i2c": "serial",
    "serial-search-spi": "serial",
    "serial-search-can": "serial",
}


def test_search_commands_keep_groups_and_carry_search_editor_metadata() -> None:
    search_commands = [entry for entry in COMMANDS if entry["category"] == "Search"]

    assert {entry["id"] for entry in search_commands} == set(EXPECTED_SEARCH_GROUPS)
    for entry in search_commands:
        assert entry.get("editor") == "search", entry["id"]
        assert entry["group"] == EXPECTED_SEARCH_GROUPS[entry["id"]], entry["id"]
    assert [entry["group"] for entry in COMMANDS if entry.get("editor") == "serial"] != []
    trigger_commands = [entry for entry in COMMANDS if entry.get("editor") == "trigger"]
    assert len(trigger_commands) == 24


def test_command_catalog_exposes_search_editor_presentation() -> None:
    catalog = {entry["id"]: entry for entry in command_catalog()}

    assert catalog["search-state"]["presentation"]["kind"] == "setting"
    assert catalog["search-count"]["presentation"]["kind"] == "command"
    assert catalog["search-count"]["presentation"]["action"] == "read"
    assert catalog["serial-search-i2c"]["presentation"]["query_fields"] == ["bus"]


def test_search_event_apply_validation_is_unchanged() -> None:
    entry = next(item for item in COMMANDS if item["id"] == "search-event")
    event_field = next(field for field in entry["fields"] if field["name"] == "event")

    assert event_field["minimum"] == 1


def test_app_routes_editors_by_command_metadata() -> None:
    app_source = read_static("app.js")
    html = read_static("index.html")

    assert 'import { SearchEditor } from "/static/search-editor.js";' in app_source
    assert 'id="search-editor" class="search-editor" hidden' in html
    assert (
        "searchEditor = new SearchEditor(elements.searchEditor, catalog, {"
        in app_source
    )
    routing_map = app_source.split("const EDITOR_RENDERERS = {", 1)[1].split("};", 1)[0]
    assert 'serial: () => serialEditor,' in routing_map
    assert 'trigger: () => triggerEditor,' in routing_map
    assert 'search: () => searchEditor,' in routing_map
    routing = extract_function(app_source, "function editorKindFor(command)")
    assert "EDITOR_RENDERERS[kind]" in routing
    assert 'elements.searchEditor.hidden = editorKind !== "search";' in app_source
    assert "searchEditor?.schedulePresentation();" in app_source
    assert "searchEditor?.rerender();" in app_source


def test_search_editor_locale_keys_are_localized() -> None:
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert '"search.editor.title": "Search editor"' in english
    assert '"search.editor.description"' in english
    assert '"group.serial": "Serial"' in english
    assert '"search.editor.title": "搜尋編輯器"' in chinese
    assert '"search.editor.description"' in chinese
    assert '"group.serial": "串列"' in chinese


def test_serial_search_projection_follows_core_capabilities() -> None:
    catalog = {entry["id"]: entry for entry in command_catalog()}

    for command_id in (
        "serial-search-uart",
        "serial-search-i2c",
        "serial-search-spi",
        "serial-search-can",
    ):
        models = catalog[command_id]["presentation"]["models"]
        for model_id, presentation in models.items():
            capabilities = capabilities_for_model_id(model_id)
            assert presentation["supported"] is True
            assert presentation["fields"]["bus"] == {
                "maximum": capabilities.serial_bus_count,
            }

    event_models = catalog["search-event"]["presentation"]["models"]
    for model_id, presentation in event_models.items():
        expected = capabilities_for_model_id(model_id).supports_search_event_navigation
        assert presentation["supported"] is expected, model_id


SEARCH_EDITOR_HARNESS = r'''
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
            this.value = "";
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) { this.children.push(...nodes); }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.Option = function Option(label, value) {
          return { textContent: label, value: String(value) };
        };
        globalThis.translate = (key) => key;
        globalThis.hasTranslation = () => false;
        globalThis.CommandForm = class CommandForm {
          constructor(container) {
            this.container = container;
            this.renderedCommand = null;
            this.queryValuesResult = {};
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
          isDirty() { return false; }
        };

        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.searchApi = { SearchEditor, serialSearchCommand, buildBusOptions };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const settle = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
          await new Promise((resolve) => setTimeout(resolve, 0));
        };

        const settingPresentation = {
          kind: "setting", action_field: "action", apply_value: "set",
          query_value: "query", query_fields: [],
        };
        const busQueryPresentation = {
          kind: "setting", action_field: "action", apply_value: "set",
          query_value: "query", query_fields: ["bus"],
        };
        const readPresentation = { kind: "command", action: "read" };
        const def = (id, group, presentation = settingPresentation, fields = []) => ({
          id,
          editor: "search",
          category: "Search",
          label: id,
          modes: ["live"],
          group,
          presentation,
          fields,
        });
        const serialFields = (maxBus = 2) => ([
          { name: "bus", type: "integer", minimum: 1, maximum: maxBus },
          { name: "mode", type: "enum", options: ["rx-data", "tx-data"] },
        ]);

        const originalCommands = [
          def("search-state", "basic"),
          def("search-mode", "basic"),
          def("search-count", "basic", readPresentation),
          def("search-event", "event"),
          def("serial-search-uart", "serial", busQueryPresentation, serialFields()),
          def("serial-search-i2c", "serial", busQueryPresentation, serialFields()),
          def("serial-search-spi", "serial", busQueryPresentation, serialFields()),
          def("serial-search-can", "serial", busQueryPresentation, serialFields()),
        ];
        const catalog = {
          commands: originalCommands,
          supported: () => true,
          groupLabel: (group) => group,
          commandLabel: (command) => command.label,
          fieldsFor: (command) => command.fields,
        };
        const env = {
          available: true,
          executionBusy: false,
          contextKey: "ctx",
          selectedId: "search-state",
        };
        const submitted = [];
        const recordJob = (command, parameters, options, payload = {}) => {
          const job = {
            job_id: `${command}-${submitted.length}`,
            status: "completed",
            result: { result: payload },
          };
          submitted.push({ command, parameters, intent: options?.intent, job });
          return job;
        };
        const makeRecordingExecute = () => async (command, parameters, options) =>
          recordJob(command, parameters, options);
        const selectedCommand = () => catalog.commands.find(
          (command) => command.id === env.selectedId,
        );
        const hooks = {
          executeCommand: makeRecordingExecute(),
          isAvailable: () => {
            const selected = selectedCommand();
            return Boolean(env.available && selected && catalog.supported(selected));
          },
          isExecutionBusy: () => env.executionBusy,
          contextKey: () => env.contextKey,
          selectedCommand,
        };
        const buildEditor = () =>
          new globalThis.searchApi.SearchEditor(new FakeNode(), catalog, hooks);
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_runtime_unavailable_view_stays_visible_and_recovers() -> None:
    script = textwrap.dedent(SEARCH_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.available = false;
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "search-state", "search-mode",
        ]);
        assert.ok(editor.readouts.count);
        assert.equal(editor.refreshButton.disabled, true);
        assert.ok(editor.entries.every((entry) => entry.button.disabled));
        assert.deepEqual(submitted, []);

        env.available = true;
        editor.schedulePresentation();
        await settle();
        assert.equal(editor.refreshButton.disabled, false);
        assert.ok(editor.entries.every((entry) => !entry.button.disabled));
        assert.deepEqual(submitted, []);
        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "search-state", "search-mode", "search-count",
        ]);
        ''')
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SEARCH_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_actions_follow_global_execution_admission_and_recover() -> None:
    script = textwrap.dedent(SEARCH_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        const entry = editor.entries[0];

        env.executionBusy = true;
        editor.applyBusyState();
        assert.equal(editor.refreshButton.disabled, true);
        assert.equal(entry.button.disabled, true);
        await editor.submit(entry);
        assert.deepEqual(submitted, []);

        env.executionBusy = false;
        editor.applyBusyState();
        assert.equal(entry.button.disabled, false);
        await editor.submit(entry);
        await settle();
        assert.equal(submitted[0].command, entry.id);
        assert.equal(submitted[0].intent, "apply");
        assert.equal(submitted.slice(1).some((item) => item.intent === "readback"), true);
        ''')
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SEARCH_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_basic_view_reads_only_basic_commands_with_readonly_count() -> None:
    script = textwrap.dedent(SEARCH_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();

        assert.equal(editor.groupHeading.textContent, "basic");
        assert.deepEqual(submitted, []);
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "search-state",
          "search-mode",
        ]);
        assert.ok(editor.readouts.count);

        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.intent ?? ""}`), [
          "search-state:readback",
          "search-mode:readback",
          "search-count:",
        ]);
        assert.equal(editor.readouts.count.textContent, "-");

        // Count becomes visible once the read result carries it.
        hooks.executeCommand = async (command, parameters, options) =>
          recordJob(command, parameters, options,
            command === "search-count" ? { count: 7 } : {});
        editor.refreshButton.dispatch("click");
        await settle();
        assert.equal(editor.readouts.count.textContent, "7");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SEARCH_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_basic_apply_writes_once_then_reconciles_the_group() -> None:
    script = textwrap.dedent(SEARCH_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        submitted.length = 0;

        const stateEntry = editor.entries[0];
        stateEntry.form.valuesResult = { action: "set", enabled: true };
        stateEntry.button.dispatch("click");
        await settle();

        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.intent ?? ""}`), [
          "search-state:apply",
          "search-state:readback",
          "search-mode:readback",
          "search-count:",
        ]);
        assert.deepEqual(submitted[0].parameters, { action: "set", enabled: true });
        assert.equal(stateEntry.form.clearedDirty, 1);
        assert.deepEqual(stateEntry.form.syncCalls.at(-2), [submitted[0].job.job_id, false]);
        assert.equal(editor.pendingRefresh, false);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SEARCH_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_event_view_queries_applies_and_hides_when_unsupported() -> None:
    script = textwrap.dedent(SEARCH_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.selectedId = "search-event";
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), ["search-event"]);

        submitted.length = 0;
        const eventEntry = editor.entries[0];
        eventEntry.form.valuesResult = { action: "set", event: 5 };
        eventEntry.button.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.intent ?? ""}`), [
          "search-event:apply",
          "search-event:readback",
        ]);
        assert.equal(eventEntry.form.clearedDirty, 1);

        // Unsupported model: no controls, no reads, explicit unavailable note.
        submitted.length = 0;
        catalog.supported = (command) => command.id !== "search-event";
        env.contextKey = "ctx-unavailable";
        editor.scheduleRefresh();
        await settle();
        assert.deepEqual(editor.entries, []);
        assert.deepEqual(submitted, []);
        const note = editor.bodyHost.children.find((node) => node.tagName === "P");
        assert.equal(note.textContent, "search.editor.eventUnavailable");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SEARCH_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_real_command_form_displays_zero_event_readback() -> None:
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.testTranslate = (key) => key;
        globalThis.testHasTranslation = () => false;

        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.CommandForm = CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const eventField = {
          value: "",
          type: "number",
          dataset: { field: "event", type: "integer", queryField: "false" },
          validity: { badInput: false },
          closest: () => null,
          setCustomValidity() {},
          checkValidity() { return true; },
          reportValidity() {},
        };
        const container = {
          querySelectorAll(selector) {
            return selector === "[data-field]" ? [eventField] : [];
          },
          querySelector(selector) {
            return selector === '[data-field="event"]' ? eventField : null;
          },
        };
        const form = new globalThis.CommandForm(container, null);
        form.presentation = {};

        form.syncResult({ result: { result: { event: 0, raw: "0" } } }, true);
        assert.equal(eventField.value, "0");

        form.syncResult({ result: { result: { event: 3 } } }, true);
        assert.equal(eventField.value, "3");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(COMMAND_FORM_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_event_capability_loss_shows_unavailable_state_and_recovers() -> None:
    script = textwrap.dedent(SEARCH_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        // The harness isAvailable mirrors the real app contract: it folds
        // catalog.supported into availability, exactly like commandAvailable.
        env.selectedId = "search-event";
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), ["search-event"]);
        assert.equal(editor.entries.length, 1);
        assert.equal(editor.refreshButton.disabled, false);

        // Capability loss on model switch: the view stays presentable with an
        // explicit unavailable note, disabled controls, and no new jobs.
        submitted.length = 0;
        catalog.supported = (command) => command.id !== "search-event";
        env.contextKey = "ctx-3000x";
        editor.scheduleRefresh();
        await settle();
        assert.deepEqual(editor.entries, []);
        assert.deepEqual(submitted, []);
        const note = editor.bodyHost.children.find((node) => node.tagName === "P");
        assert.equal(note.textContent, "search.editor.eventUnavailable");
        assert.equal(editor.groupHeading.textContent, "event");
        assert.equal(editor.refreshButton.disabled, true);

        // Recovery re-renders the form and re-reads the event.
        catalog.supported = () => true;
        env.contextKey = "ctx-back-4000x";
        editor.scheduleRefresh();
        await settle();
        assert.equal(editor.entries.length, 1);
        assert.deepEqual(submitted.map((entry) => entry.command), ["search-event"]);
        assert.equal(editor.refreshButton.disabled, false);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SEARCH_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_serial_view_scopes_reads_to_active_bus_and_protocol() -> None:
    script = textwrap.dedent(SEARCH_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        // Mapping table contract.
        assert.deepEqual(
          ["uart", "i2c", "spi", "can"].map(
            (protocol) => globalThis.searchApi.serialSearchCommand(protocol),
          ),
          [
            "serial-search-uart",
            "serial-search-i2c",
            "serial-search-spi",
            "serial-search-can",
          ],
        );
        assert.equal(globalThis.searchApi.serialSearchCommand("lin"), null);
        assert.deepEqual(globalThis.searchApi.buildBusOptions(0), []);
        assert.deepEqual(globalThis.searchApi.buildBusOptions(2), [1, 2]);

        // Clicking serial-search-i2c opens the Serial Search view on I2C.
        env.selectedId = "serial-search-i2c";
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        assert.equal(editor.groupHeading.textContent, "serial");
        assert.equal(editor.protocol, "i2c");
        assert.deepEqual(editor.busSelect.children.map((option) => option.value), ["1", "2"]);
        assert.deepEqual(editor.protocolSelect.children.map((option) => option.value), [
          "uart", "i2c", "spi", "can",
        ]);
        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.parameters.bus}`), [
          "serial-search-i2c:1",
        ]);
        const criteriaEntry = editor.entries[0];
        assert.deepEqual(
          criteriaEntry.form.renderedCommand.fields.map((field) => field.name),
          ["mode"],
        );
        assert.deepEqual(
          originalCommands.find((command) => command.id === "serial-search-i2c")
            .fields.map((field) => field.name),
          ["bus", "mode"],
        );

        // Protocol switch only changes presentation.
        submitted.length = 0;
        editor.selectProtocol("uart");
        await settle();
        assert.equal(editor.protocol, "uart");
        assert.deepEqual(submitted, []);

        // Bus switch is also passive; Refresh reads the selected view.
        editor.selectProtocol("i2c");
        await settle();
        editor.selectBus("2");
        await settle();
        assert.deepEqual(submitted, []);
        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.parameters.bus}`), [
          "serial-search-i2c:2",
        ]);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SEARCH_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_serial_view_reports_unavailable_without_fake_buses() -> None:
    script = textwrap.dedent(SEARCH_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        // No supported serial-search protocols at all.
        catalog.supported = () => false;
        env.selectedId = "serial-search-can";
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        assert.deepEqual(editor.entries, []);
        assert.deepEqual(submitted, []);
        assert.equal(editor.busSelect, null);
        let note = editor.bodyHost.children.find((node) => node.tagName === "P");
        assert.equal(note.textContent, "search.editor.serialUnavailable");

        // Protocols supported but the projected bus maximum is zero.
        catalog.supported = () => true;
        catalog.fieldsFor = (command) => command.fields.map((field) => (
          field.name === "bus" ? { ...field, maximum: 0 } : field
        ));
        env.contextKey = "ctx-zero-bus";
        editor.scheduleRefresh();
        await settle();
        assert.deepEqual(submitted, []);
        assert.deepEqual(editor.entries, []);
        note = editor.bodyHost.children.find((node) => node.tagName === "P");
        assert.equal(note.textContent, "search.editor.serialUnavailable");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SEARCH_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_serial_apply_writes_once_then_reconciles_state_mode_criteria() -> None:
    script = textwrap.dedent(SEARCH_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        env.selectedId = "serial-search-i2c";
        const editor = buildEditor();
        editor.scheduleRefresh();
        await settle();
        submitted.length = 0;

        const criteriaEntry = editor.entries[0];
        criteriaEntry.form.valuesResult = { action: "set", mode: "rx-data", data: 85 };
        criteriaEntry.button.dispatch("click");
        await settle();

        // Exactly one write; no search-state/search-mode writes anywhere.
        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.intent ?? ""}`), [
          "serial-search-i2c:apply",
          "search-state:readback",
          "search-mode:readback",
          "serial-search-i2c:readback",
        ]);
        assert.deepEqual(submitted[0].parameters, {
          action: "set", mode: "rx-data", data: 85, bus: 1,
        });
        assert.equal(criteriaEntry.form.clearedDirty, 1);
        assert.equal(editor.pendingRefresh, false);

        // Failed Apply: no reconciliation, draft handling untouched.
        submitted.length = 0;
        const recordingExecute = hooks.executeCommand;
        hooks.executeCommand = async (command, parameters, options) => {
          const job = {
            job_id: `failed-${submitted.length}`,
            status: "failed",
            error: "temporary VISA failure",
          };
          submitted.push({ command, parameters, intent: options?.intent, job });
          return job;
        };
        const syncCountBefore = criteriaEntry.form.syncCalls.length;
        criteriaEntry.form.clearedDirty = 0;
        criteriaEntry.button.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.intent ?? ""}`), [
          "serial-search-i2c:apply",
        ]);
        assert.equal(criteriaEntry.form.clearedDirty, 0);
        assert.equal(criteriaEntry.form.syncCalls.length, syncCountBefore);
        assert.equal(editor.pendingRefresh, false);
        hooks.executeCommand = recordingExecute;
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SEARCH_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_editor_serializes_lifecycle_and_suppresses_same_state_refresh() -> None:
    script = textwrap.dedent(SEARCH_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        // Deferred readback holds the busy gate and disables every control.
        env.selectedId = "serial-search-uart";
        const editor = buildEditor();
        let queries = 0;
        let releaseQuery;
        hooks.executeCommand = (command, parameters, options) => {
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
        assert.equal(queries, 1);
        assert.equal(editor.busy, true);
        assert.equal(editor.refreshButton.disabled, true);
        assert.equal(editor.entries[0].button.disabled, true);
        assert.equal(editor.busSelect.disabled, true);
        assert.equal(editor.protocolSelect.disabled, true);

        // Same-state ordinary notifications do not queue anything.
        editor.scheduleRefresh();
        await settle();
        assert.equal(queries, 1);
        assert.equal(editor.pendingRefresh, false);

        // A genuine selection change while busy queues exactly one refresh.
        env.selectedId = "serial-search-spi";
        editor.scheduleRefresh();
        await settle();
        assert.equal(queries, 1);
        assert.equal(editor.pendingRefresh, true);

        releaseQuery();
        hooks.executeCommand = makeRecordingExecute();
        await settle();
        assert.equal(queries, 1);
        assert.equal(editor.busy, false);
        assert.equal(editor.pendingRefresh, false);
        assert.equal(editor.protocol, "spi");
        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.intent ?? ""}`), [
          "serial-search-spi:readback",
        ]);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SEARCH_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_search_editor_auto_notifications_do_not_restart_group_readback() -> None:
    script = textwrap.dedent(SEARCH_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        // Simulate the real app contract: every completed executeCommand ends
        // with a plain unforced refresh notification. The Basic readback must
        // run exactly once and end idle.
        env.selectedId = "search-state";
        let editor;
        hooks.executeCommand = async (command, parameters, options) => {
          if (submitted.length > 6) {
            throw new Error("Search readback refresh loop detected");
          }
          const job = recordJob(command, parameters, options,
            command === "search-count" ? { count: 4 } : {});
          editor.scheduleRefresh();
          return job;
        };
        editor = buildEditor();
        editor.scheduleRefresh();
        await settle();

        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.intent ?? ""}`), [
          "search-state:readback",
          "search-mode:readback",
          "search-count:",
        ]);
        assert.equal(editor.readouts.count.textContent, "4");
        assert.equal(editor.busy, false);
        assert.equal(editor.pendingRefresh, false);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(SEARCH_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
