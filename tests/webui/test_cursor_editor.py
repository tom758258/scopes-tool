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
    entry = next(
        entry for entry in commands_module.COMMANDS if entry["id"] == "cursor"
    )

    assert entry["category"] == "Cursor"
    assert entry["group"] == "cursor"
    assert entry["editor"] == "cursor"
    assert entry.get("browser_hidden") is not True
    assert entry.get("hidden") is not True
    action = next(field for field in entry["fields"] if field["name"] == "action")
    assert tuple(action["options"]) == ("query", "set", "off")
    assert {field["name"] for field in entry["fields"]} == {
        "action",
        "source_channel",
        "x1",
        "x2",
        "y1",
        "y2",
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
        "cursor",
        "SIM::INSTR",
        {
            "action": "set",
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
        '"command.cursor": "Cursor"',
        '"description.cursor":',
        '"cursor.editor.title": "Cursor editor"',
        '"cursor.editor.description":',
        '"cursor.state.xDelta":',
        '"cursor.state.dydx":',
    ):
        assert key in english, key
    for key in (
        '"command.cursor": "游標"',
        '"description.cursor":',
        '"cursor.editor.title": "游標編輯器"',
        '"cursor.editor.description":',
        '"cursor.state.xDelta":',
        '"cursor.state.dydx":',
    ):
        assert key in chinese, key

    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import path from "node:path";

        class FakeNode {
          constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.hidden = false; this.textContent = ""; this.className = ""; this.disabled = false; }
          append(...nodes) { this.children.push(...nodes); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          addEventListener(_name, handler) { this.handler = handler; }
          setAttribute() {}
          remove() {}
          querySelector() { return null; }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.queueMicrotask = (fn) => { fn(); };

        globalThis.translate = (key) => key;
        let submittedAction = "query";
        globalThis.CommandForm = class CommandForm {
          constructor(container, _catalog) { this.container = container; this.command = null; this.disabled = false; }
          render(command) { this.command = command; }
          values() {
            if (submittedAction === "query") return { action: "query" };
            if (submittedAction === "off") return { action: "off" };
            return { action: submittedAction, source_channel: 1, x1: 0, x2: 0.001 };
          }
          setDisabled(disabled) { this.disabled = disabled; }
          clearDirty() {}
        };

        const calls = [];
        const hooks = {
          calls,
          contextKey: () => "simulate||keysight-dsox4024a",
          selectedCommand: () => ({ id: "cursor", editor: "cursor", group: "cursor" }),
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
        assert.deepEqual(calls[0], ["cursor", { action: "query" }]);
        const panel = editor.entry.panel;
        const rows = Object.fromEntries(
          panel.children.map((row) => [row.children[0].textContent, row.children[1].textContent]),
        );
        assert.equal(rows["cursor.state.mode"], "MANual");
        assert.equal(rows["cursor.state.xDelta"], "0.001");
        assert.equal(rows["cursor.state.dydx"], "500");
        assert.ok(!("cursor.state.y1" in rows));

        submittedAction = "off";
        const beforeSubmit = calls.length;
        await editor.submit();
        const submittedCalls = calls.slice(beforeSubmit);
        assert.equal(submittedCalls.length, 1);
        assert.deepEqual(submittedCalls[0], ["cursor", { action: "off" }]);

        submittedAction = "set";
        const beforeSet = calls.length;
        await editor.submit();
        const setCalls = calls.slice(beforeSet);
        assert.equal(setCalls.length, 1);
        assert.deepEqual(setCalls[0], ["cursor", { action: "set", source_channel: 1, x1: 0, x2: 0.001 }]);

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
