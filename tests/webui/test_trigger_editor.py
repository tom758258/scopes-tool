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
                assert presentation["fields"][name] == {"maximum": expected}


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
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) { this.children.push(...nodes); }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
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
def test_trigger_actions_follow_global_execution_admission_and_recover() -> None:
    script = textwrap.dedent(TRIGGER_EDITOR_HARNESS) + textwrap.dedent(
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
        assert.equal(editor.refreshButton.disabled, false);
        assert.equal(entry.button.disabled, false);
        await editor.submit(entry);
        await settle();
        assert.equal(submitted[0].command, entry.id);
        assert.equal(submitted[0].intent, "apply");
        assert.equal(submitted.slice(1).some((item) => item.intent === "readback"), true);
        ''')
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(TRIGGER_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_trigger_editor_renders_active_group_and_scopes_readback_to_it() -> None:
    script = textwrap.dedent(TRIGGER_EDITOR_HARNESS) + textwrap.dedent(
        r'''
        // Selecting an Edge command renders the whole group without reading it.
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();

        assert.equal(editor.groupHeading.textContent, "edge");
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "trigger-edge-slope",
          "trigger-edge-coupling",
        ]);
        assert.deepEqual(submitted, []);

        // Explicit Refresh reads only the active group.
        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "trigger-edge-slope",
          "trigger-edge-coupling",
        ]);
        assert.ok(submitted.every((entry) => entry.intent === "readback"));
        for (const entry of editor.entries) {
          assert.equal(entry.form.renderedCommand, commands.find((c) => c.id === entry.id));
          assert.deepEqual(entry.form.syncCalls.at(-1), [submitted.find(
            (item) => item.command === entry.id,
          ).job.job_id, true]);
        }

        // Manual refresh re-reads the same group without rebuilding forms.
        submitted.length = 0;
        const epochBeforeRefresh = editor.epoch;
        editor.refreshButton.dispatch("click");
        await settle();
        assert.equal(editor.epoch, epochBeforeRefresh);
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "trigger-edge-slope",
          "trigger-edge-coupling",
        ]);

        // Switching to Runt replaces the section list without reading it.
        submitted.length = 0;
        env.selectedId = "trigger-runt";
        editor.schedulePresentation();
        await settle();
        assert.equal(editor.groupHeading.textContent, "runt");
        assert.deepEqual(editor.entries.map((entry) => entry.id), ["trigger-runt"]);
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
        const runtEntry = editor.entries[0];

        // A rejected form submit executes nothing.
        submitted.length = 0;
        runtEntry.form.valuesResult = null;
        runtEntry.button.dispatch("click");
        await settle();
        assert.deepEqual(submitted, []);

        // Apply submits exactly this one existing command with action=set,
        // then a forced active-group readback reconciles the group.
        submitted.length = 0;
        runtEntry.form.valuesResult = { action: "set", channel: 1 };
        runtEntry.button.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "trigger-runt",
          "trigger-runt",
        ]);
        assert.equal(submitted[0].intent, "apply");
        assert.deepEqual(submitted[0].parameters, { action: "set", channel: 1 });
        assert.equal(submitted[1].intent, "readback");
        assert.equal(runtEntry.form.clearedDirty, 1);
        assert.deepEqual(runtEntry.form.syncCalls.at(-2), [submitted[0].job.job_id, false]);
        assert.deepEqual(runtEntry.form.syncCalls.at(-1), [submitted[1].job.job_id, true]);

        // No aggregate transaction: a second Apply still runs only this command
        // (plus its follow-up group readback).
        submitted.length = 0;
        runtEntry.button.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "trigger-runt",
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
        const runtEntry = editor.entries[0];

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

        // Informational commands keep explicit Read semantics and are not auto-queried.
        submitted.length = 0;
        env.selectedId = "external-trigger-settings";
        editor.scheduleRefresh();
        await settle();
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "external-trigger-settings",
        ]);
        assert.deepEqual(submitted, []);
        const readEntry = editor.entries[0];
        assert.equal(readEntry.kind, "command");
        assert.equal(readEntry.button.textContent, "actions.read");
        readEntry.button.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "external-trigger-settings",
        ]);
        assert.equal(submitted[0].intent, undefined);
        assert.deepEqual(submitted[0].parameters, {});
        assert.equal(readEntry.form.clearedDirty, 0);

        // Unavailable contexts clear the editor without submitting anything.
        submitted.length = 0;
        env.available = false;
        editor.scheduleRefresh();
        await settle();
        assert.deepEqual(editor.entries, []);
        assert.equal(editor.refreshButton.disabled, true);
        assert.deepEqual(submitted, []);
        env.available = true;
        editor.scheduleRefresh();
        await settle();
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "external-trigger-settings",
        ]);
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
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "trigger-edge-slope",
          "trigger-edge-coupling",
        ]);
        for (const entry of editor.entries) {
          assert.equal(
            entry.form.renderedCommand,
            commands.find((command) => command.id === entry.id),
          );
        }

        catalog.supported = (command) => command.id !== "trigger-edge-coupling";
        env.contextKey = "ctx-2";
        editor.scheduleRefresh();
        await settle();
        assert.deepEqual(editor.entries.map((entry) => entry.id), ["trigger-edge-slope"]);
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
        assert.deepEqual(editor.entries.map((entry) => entry.id), [
          "trigger-edge-level",
          "trigger-edge-slope",
        ]);
        const levelEntry = editor.entries[0];
        const slopeEntry = editor.entries[1];
        assert.equal(levelEntry.form.renderOptions.onQueryFieldChange, undefined);

        submitted.length = 0;
        const slopeSyncCount = slopeEntry.form.syncCalls.length;
        levelEntry.form.queryValuesResult = { action: "query", source_channel: 2 };
        await settle();

        assert.deepEqual(submitted, []);

        // Explicit Refresh reads the group using the changed query selector.
        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.map((entry) => entry.command), [
          "trigger-edge-level",
          "trigger-edge-slope",
        ]);
        assert.equal(submitted[0].intent, "readback");
        assert.deepEqual(submitted[0].parameters, { action: "query", source_channel: 2 });
        assert.equal(slopeEntry.form.syncCalls.length, slopeSyncCount + 1);
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

        // The active-group readback itself holds the busy gate.
        const runtEntry = editor.entries[0];
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
        // scheduleEditorRead). The active-group readback must not restart.
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
          "trigger-edge-coupling:readback",
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
def test_trigger_editor_apply_reconciles_sibling_forms_in_active_group() -> None:
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
        const aggregateEntry = editor.entries.find((entry) => entry.id === "trigger-edge");
        const sourceEntry = editor.entries.find((entry) => entry.id === "trigger-edge-source");
        sourceEntry.form.valuesResult = { action: "set", source_channel: 2 };

        submitted.length = 0;
        sourceEntry.button.dispatch("click");
        await settle();
        assert.equal(editor.busy, true);
        releaseApply();
        await settle();

        // Exactly one write, then a forced active-group readback so the
        // aggregate sibling form does not stay stale.
        assert.equal(editor.busy, false);
        assert.deepEqual(submitted.map((entry) => `${entry.command}:${entry.intent}`), [
          "trigger-edge-source:apply",
          "trigger-edge:readback",
          "trigger-edge-source:readback",
        ]);
        assert.deepEqual(
          sourceEntry.form.syncCalls.slice(-2).map((call) => call[1]),
          [false, true],
        );
        assert.equal(aggregateEntry.form.syncCalls.at(-1)[1], true);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(TRIGGER_EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
