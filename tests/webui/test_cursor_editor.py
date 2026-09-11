from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

import scopes_tool_webui.command_execution as command_execution_module
import scopes_tool_webui.commands as commands_module
from scopes_tool_webui.command_validation import WebUIRequestError, validate_job_request


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
MODEL_ID = "keysight-dsox4024a"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_cursor_command_carries_cursor_editor_metadata() -> None:
    legacy = next(
        entry for entry in commands_module.COMMANDS if entry["id"] == "cursor"
    )
    assert legacy.get("hidden") is True

    public = {
        entry["id"]: entry for entry in commands_module.command_catalog()
    }
    assert {"cursor-query", "cursor-set", "cursor-off"} <= set(public)
    assert "cursor" not in public

    for command_id in ("cursor-query", "cursor-set", "cursor-off"):
        entry = public[command_id]
        assert entry["category"] == "Cursor"
        assert "group" not in entry
        assert entry["editor"] == "cursor"
        assert entry.get("browser_hidden") is not True
        assert entry.get("hidden") is not True

    assert public["cursor-query"]["fields"] == []
    assert public["cursor-off"]["fields"] == []
    assert public["cursor-query"]["presentation"]["action"] == "read"
    setters = public["cursor-set"]["fields"]
    assert [field["name"] for field in setters] == [
        "source_channel",
        "x1",
        "x2",
        "y1",
        "y2",
    ]
    assert {
        field["name"] for field in setters if field.get("required") is True
    } == {"source_channel", "x1", "x2"}
    assert {field["help_key"] for field in setters} == {
        "cursor.source_channel",
        "cursor.x1",
        "cursor.x2",
        "cursor.y1",
        "cursor.y2",
    }


def test_cursor_set_validation_requires_source_and_x_positions() -> None:
    request = validate_job_request({
        "command": "cursor",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {
            "action": "set",
            "source_channel": 1,
            "x1": 0.0,
            "x2": 0.001,
            "y1": 0.0,
            "y2": 0.5,
        },
    })

    assert request["parameters"]["source_channel"] == 1
    with pytest.raises(WebUIRequestError, match="source_channel"):
        validate_job_request({
            "command": "cursor",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "set", "x1": 0.0, "x2": 0.001},
        })
    with pytest.raises(WebUIRequestError, match="query, set, or off"):
        validate_job_request({
            "command": "cursor",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "run"},
        })
    with pytest.raises(WebUIRequestError, match="cursor off cannot include"):
        validate_job_request({
            "command": "cursor",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "off", "x1": 0.0},
        })


def test_cursor_set_command_validation_requires_source_and_x_positions() -> None:
    request = validate_job_request({
        "command": "cursor-set",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {
            "source_channel": 1,
            "x1": 0.0,
            "x2": 0.001,
            "y1": 0.0,
            "y2": 0.5,
        },
    })

    assert request["parameters"]["source_channel"] == 1
    with pytest.raises(WebUIRequestError, match="source_channel"):
        validate_job_request({
            "command": "cursor-set",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"x1": 0.0, "x2": 0.001},
        })
    with pytest.raises(WebUIRequestError, match="unknown parameter"):
        validate_job_request({
            "command": "cursor-query",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"x1": 0.0},
        })


def test_cursor_execution_calls_core_without_auto_adjustment(tmp_path: Path) -> None:
    calls: list[tuple] = []

    class FakeScope:
        capabilities = object()

        def configure_cursor(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(("configure", args, kwargs))

        def cursor_off(self) -> None:
            calls.append(("off", (), {}))

        def query_cursor(self):  # type: ignore[no-untyped-def]
            calls.append(("query", (), {}))
            return {
                "mode": "MANual",
                "x1_seconds": 0.0,
                "x2_seconds": 0.001,
                "y1_volts": 0.0,
                "y2_volts": 0.5,
                "x_delta_seconds": 0.001,
                "y_delta_volts": 0.5,
                "dydx": None,
            }

    scope = FakeScope()
    result = command_execution_module._execute_scope_command(
        scope,
        "cursor-set",
        "SIM::INSTR",
        {
            "source_channel": 1,
            "x1": 0.0,
            "x2": 0.001,
            "y1": 0.0,
            "y2": 0.5,
        },
        tmp_path,
    )

    assert calls[0] == (
        "configure",
        (1, 0.0, 0.001),
        {"y1_volts": 0.0, "y2_volts": 0.5},
    )
    assert "auto_timebase" not in calls[0][2]
    assert "auto_vertical" not in calls[0][2]
    assert result["result"]["cursor"]["x_delta_seconds"] == 0.001

    calls.clear()
    command_execution_module._execute_scope_command(
        scope, "cursor-query", "SIM::INSTR", {}, tmp_path
    )

    assert calls == [("query", (), {})]

    calls.clear()
    command_execution_module._execute_scope_command(
        scope, "cursor-off", "SIM::INSTR", {}, tmp_path
    )

    assert calls == [("off", (), {}), ("query", (), {})]

    calls.clear()
    command_execution_module._execute_scope_command(
        scope, "cursor", "SIM::INSTR", {"action": "off"}, tmp_path
    )

    assert calls == [("off", (), {}), ("query", (), {})]


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_cursor_editor_routing_refresh_and_apply(tmp_path: Path) -> None:
    catalog_json = json.dumps(commands_module.command_catalog())
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    app_source = read_static("app.js")
    index_source = read_static("index.html")

    assert "cursor: () => cursorEditor," in app_source
    assert "elements.cursorEditor.hidden = editorKind !== " in app_source
    assert 'if (editorKind === "cursor") cursorEditor?.schedulePresentation();' in app_source
    assert 'cursorEditor.refreshButton.hidden = editorKind !== "cursor";' in app_source
    assert "cursorEditor?.rerender();" in app_source
    assert 'id="cursor-editor"' in index_source
    for key in (
        '"command.cursor-query": "Cursor state"',
        '"description.cursor-query":',
        '"command.cursor-set": "Set cursors"',
        '"description.cursor-set":',
        '"command.cursor-off": "Turn off cursors"',
        '"description.cursor-off":',
        '"cursor.editor.title": "Cursor editor"',
        '"cursor.editor.description":',
        '"cursor.state.xDelta":',
        '"cursor.state.dydx":',
        '"enum.cursor-mode.MAN": "Manual"',
        '"enum.cursor-mode.MANual": "Manual"',
        '"enum.cursor-mode.OFF": "Off"',
    ):
        assert key in english, key
    for key in (
        '"command.cursor-query": "游標狀態"',
        '"description.cursor-query":',
        '"command.cursor-set": "設定游標"',
        '"description.cursor-set":',
        '"command.cursor-off": "關閉游標"',
        '"description.cursor-off":',
        '"cursor.editor.title": "游標編輯器"',
        '"cursor.editor.description":',
        '"cursor.state.xDelta":',
        '"cursor.state.dydx":',
        '"enum.cursor-mode.MAN": "手動"',
        '"enum.cursor-mode.MANual": "手動"',
        '"enum.cursor-mode.OFF": "關閉"',
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
        let selectedId = "cursor-query";
        globalThis.CommandForm = class CommandForm {
          constructor(container, _catalog) { this.container = container; this.command = null; this.disabled = false; }
          render(command) { this.command = command; }
          values() {
            if (selectedId === "cursor-set") return { source_channel: 1, x1: 0, x2: 0.001 };
            return {};
          }
          setDisabled(disabled) { this.disabled = disabled; }
          clearDirty() {}
        };

        const calls = [];
        const hooks = {
          calls,
          contextKey: () => "simulate||keysight-dsox4024a",
          selectedCommand: () => catalog.commands.find((command) => command.id === selectedId),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          headerActions: new FakeNode("div"),
          async executeCommand(id, parameters, _options) {
            calls.push([id, parameters]);
            return {
              status: "completed",
              result: {
                result: {
                  cursor: {
                    mode: "MANual", x1_seconds: 0, x2_seconds: 0.001,
                    y1_volts: null, y2_volts: null,
                    x_delta_seconds: 0.001, y_delta_volts: null, dydx: 500,
                  },
                },
              },
            };
          },
        };
        const catalog = {
          commands: __CATALOG__,
          groupLabel: (group) => group,
          commandLabel: (command) => command.id,
          description: (command) => `description.${command.id}`,
          supported: () => true,
        };

        let editorSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/cursor-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class CursorEditor", "class CursorEditor")
          + "\nglobalThis.CursorEditor = CursorEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        // Non-cursor selection clears the workspace.
        const idle = new globalThis.CursorEditor(new FakeNode("div"), catalog, {
          ...hooks, selectedCommand: () => ({ id: "measure", editor: null }),
        });
        await idle.refresh(true, true);
        assert.equal(calls.length, 0);

        const editor = new globalThis.CursorEditor(new FakeNode("div"), catalog, hooks);
        await editor.refresh(true, true);
        assert.ok(hooks.headerActions.children.includes(editor.refreshButton));
        assert.ok(hooks.headerActions.children.includes(editor.entry.button));
        assert.equal(editor.entry.form.container.className, "command-form");
        assert.ok(!editor.sectionsHost.children[0].children.includes(editor.entry.button));

        assert.deepEqual(calls[0], ["cursor-query", {}]);
        // No inline cursor-state panel; state surfaces through Workspace Result.
        // No inner heading row; the page header already shows the editor title.
        assert.equal(editor.entry.panel, undefined);
        const classNames = [];
        {
          const walk = (node) => {
            for (const child of node.children || []) {
              if (child.className) classNames.push(child.className);
              walk(child);
            }
          };
          walk(editor.container);
        }
        assert.ok(!classNames.includes("cursor-editor-state"));
        assert.ok(!classNames.includes("trigger-editor-head"));
        // cursor-query has no fields; its empty form stays hidden.
        assert.equal(editor.entry.form.container.hidden, true);
        // cursor-query reuses the header Read action; no second query button.
        assert.equal(editor.entry.button.hidden, true);

        selectedId = "cursor-set";
        const beforeSetRead = calls.length;
        await editor.refresh(true, true);
        assert.deepEqual(calls.slice(beforeSetRead), [["cursor-query", {}]]);
        assert.equal(editor.entry.button.hidden, false);
        assert.equal(editor.entry.button.textContent, "actions.apply");
        assert.equal(editor.entry.form.container.hidden, false);
        const setSection = editor.sectionsHost.children[0];
        assert.ok(setSection.children.some((node) => node.className === "muted compact-note"));
        assert.ok(setSection.children.some((node) => node.textContent === "description.cursor-set"));

        const beforeSet = calls.length;
        await editor.submit();
        const setCalls = calls.slice(beforeSet);
        assert.equal(setCalls.length, 1);
        assert.deepEqual(setCalls[0], ["cursor-set", { source_channel: 1, x1: 0, x2: 0.001 }]);

        selectedId = "cursor-off";
        const beforeOffRead = calls.length;
        await editor.refresh(true, true);
        assert.deepEqual(calls.slice(beforeOffRead), [["cursor-query", {}]]);
        assert.equal(editor.entry.button.hidden, false);
        assert.equal(editor.entry.button.textContent, "actions.run");
        assert.equal(editor.entry.form.container.hidden, true);
        const beforeSubmit = calls.length;
        await editor.submit();
        const submittedCalls = calls.slice(beforeSubmit);
        assert.equal(submittedCalls.length, 1);
        assert.deepEqual(submittedCalls[0], ["cursor-off", {}]);

        // Switching back to cursor-query hides the section button again.
        selectedId = "cursor-query";
        const callsBeforeBack = calls.length;
        await editor.refresh(true, false);
        assert.equal(calls.length, callsBeforeBack);
        assert.equal(editor.entry.button.hidden, true);

        const headerCount = hooks.headerActions.children.length;
        const oldApply = editor.entry.button;
        const callsBeforeLayout = calls.length;
        editor.rerender();
        assert.equal(hooks.headerActions.children.length, headerCount);
        assert.ok(!hooks.headerActions.children.includes(oldApply));
        assert.ok(hooks.headerActions.children.includes(editor.entry.button));
        const local = new globalThis.CursorEditor(new FakeNode("div"), catalog, {
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
    harness_path = tmp_path / "cursor-editor-harness.mjs"
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
