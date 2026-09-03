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


def test_annotation_command_carries_annotation_editor_metadata() -> None:
    entry = next(
        item for item in commands_module.COMMANDS if item["id"] == "annotation"
    )

    assert entry["category"] == "Annotation"
    assert entry["group"] == "annotation"
    assert entry["editor"] == "annotation"
    assert entry.get("browser_hidden") is not True
    assert entry.get("hidden") is not True
    action = next(field for field in entry["fields"] if field["name"] == "action")
    assert tuple(action["options"]) == ("query", "set", "on", "off", "clear")
    names = sorted(field["name"] for field in entry["fields"])
    assert names == ["action", "background", "color", "slot", "text", "x", "y"]


def test_annotation_model_projection_gates_slot_and_position() -> None:
    catalog = {
        entry["id"]: entry for entry in commands_module.command_catalog()
    }
    old_models = catalog["annotation"]["presentation"]["models"]
    slot_2000x = old_models["keysight-dsox2004a"]["fields"]["slot"]
    slot_4000x = old_models["keysight-dsox4024a"]["fields"]["slot"]

    assert slot_2000x.get("hidden") is True
    assert list(slot_2000x.get("options", [])) == [1]
    assert list(slot_4000x.get("options", [])) == list(range(1, 11))
    assert slot_4000x.get("hidden") is not True
    position_2000x = old_models["keysight-dsox2004a"]["fields"]
    position_4000x = old_models["keysight-dsox4024a"]["fields"]
    assert position_2000x["x"].get("hidden") is True
    assert position_2000x["y"].get("hidden") is True
    assert position_4000x.get("x", {}).get("hidden") is not True
    assert position_4000x.get("y", {}).get("hidden") is not True


def test_annotation_set_validation_requires_at_least_one_setter() -> None:
    request = validate_job_request({
        "command": "annotation",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {"action": "set", "slot": 1, "text": "hello"},
    })

    assert request["parameters"]["text"] == "hello"
    with pytest.raises(WebUIRequestError, match="at least one"):
        validate_job_request({
            "command": "annotation",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "set", "slot": 1},
        })
    with pytest.raises(WebUIRequestError, match="query, set, on, off, or clear"):
        validate_job_request({
            "command": "annotation",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "run"},
        })
    with pytest.raises(WebUIRequestError, match="annotation clear cannot include"):
        validate_job_request({
            "command": "annotation",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "clear", "slot": 1, "text": "hello"},
        })
    with pytest.raises(WebUIRequestError, match="annotation on cannot include"):
        validate_job_request({
            "command": "annotation",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "on", "slot": 1, "x": 10},
        })


def test_annotation_position_rejected_before_execution_on_unsupported_model() -> None:
    with pytest.raises(WebUIRequestError, match="annotation position is not supported"):
        validate_job_request({
            "command": "annotation",
            "mode": "simulate",
            "model_id": "keysight-dsox2004a",
            "parameters": {"action": "set", "slot": 1, "text": "hello", "x": 10},
        })


def test_annotation_execution_applies_only_provided_setters(tmp_path: Path) -> None:
    calls: list[tuple] = []

    class FakeScope:
        capabilities = object()

        def set_annotation_text(self, text, *, slot):  # type: ignore[no-untyped-def]
            calls.append(("text", text, slot))

        def set_annotation_color(self, color, *, slot):  # type: ignore[no-untyped-def]
            calls.append(("color", color, slot))

        def set_annotation_background(self, background, *, slot):  # type: ignore[no-untyped-def]
            calls.append(("background", background, slot))

        def set_annotation_position(self, x, y, *, slot):  # type: ignore[no-untyped-def]
            calls.append(("position", x, y, slot))

        def set_annotation_enabled(self, enabled, *, slot):  # type: ignore[no-untyped-def]
            calls.append(("enabled", enabled, slot))

        def clear_annotation(self, *, slot):  # type: ignore[no-untyped-def]
            calls.append(("clear", slot))

        def query_annotation(self, *, slot):  # type: ignore[no-untyped-def]
            calls.append(("query", slot))
            return {
                "slot": slot,
                "enabled": True,
                "text": "hello",
                "color": "CH1",
                "background": "OPAQ",
                "x": None,
                "y": None,
            }

    scope = FakeScope()
    result = command_execution_module._execute_scope_command(
        scope,
        "annotation",
        "SIM::INSTR",
        {"action": "set", "slot": 1, "text": "hello"},
        tmp_path,
    )

    assert calls == [("text", "hello", 1), ("query", 1)]
    assert result["result"]["annotation"]["text"] == "hello"

    calls.clear()
    command_execution_module._execute_scope_command(
        scope, "annotation", "SIM::INSTR", {"action": "clear", "slot": 2}, tmp_path
    )

    assert calls == [("clear", 2), ("query", 2)]


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_annotation_editor_routing_refresh_and_apply(tmp_path: Path) -> None:
    catalog_json = json.dumps(commands_module.command_catalog())
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    app_source = read_static("app.js")
    index_source = read_static("index.html")

    assert "annotation: () => annotationEditor," in app_source
    assert "elements.annotationEditor.hidden = editorKind !== " in app_source
    assert 'if (editorKind === "annotation") annotationEditor?.schedulePresentation();' in app_source
    assert 'annotationEditor.refreshButton.hidden = editorKind !== "annotation";' in app_source
    assert "annotationEditor?.rerender();" in app_source
    assert 'id="annotation-editor"' in index_source
    for key in (
        '"command.annotation": "Annotation"',
        '"description.annotation":',
        '"annotation.editor.title": "Annotation editor"',
        '"annotation.editor.description":',
        '"annotation.state.enabled":',
        '"annotation.state.background":',
    ):
        assert key in english, key
    for key in (
        '"command.annotation": "註解"',
        '"description.annotation":',
        '"annotation.editor.title": "註解編輯器"',
        '"annotation.editor.description":',
        '"annotation.state.enabled":',
        '"annotation.state.background":',
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
        let submittedAction = "set";
        globalThis.CommandForm = class CommandForm {
          constructor(container, _catalog) { this.container = container; this.command = null; this.disabled = false; }
          render(command) { this.command = command; }
          values() {
            if (submittedAction === "set") return { action: "set", slot: 3, text: "note" };
            return { action: submittedAction, slot: 3 };
          }
          setDisabled(disabled) { this.disabled = disabled; }
          clearDirty() {}
        };

        const calls = [];
        const hooks = {
          calls,
          contextKey: () => "simulate||keysight-dsox4024a",
          selectedCommand: () => ({ id: "annotation", editor: "annotation", group: "annotation" }),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          headerActions: new FakeNode("div"),
          async executeCommand(id, parameters, _options) {
            calls.push([id, parameters]);
            return {
              status: "completed",
              result: {
                result: {
                  annotation: {
                    slot: 3, enabled: true, text: "note", color: "WHITE",
                    background: "OPAQ", x: null, y: null,
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
          path.join(process.cwd(), "src/scopes_tool_webui/static/annotation-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class AnnotationEditor", "class AnnotationEditor")
          + "\nglobalThis.AnnotationEditor = AnnotationEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const editor = new globalThis.AnnotationEditor(new FakeNode("div"), catalog, hooks);
        await editor.refresh(true, true);
        assert.deepEqual(calls[0], ["annotation", { action: "query", slot: 1 }]);
        const panel = editor.entry.panel;
        const rows = Object.fromEntries(
          panel.children.map((row) => [row.children[0].textContent, row.children[1].textContent]),
        );
        assert.equal(rows["annotation.state.enabled"], "enum.enable");
        assert.equal(rows["annotation.state.text"], "note");
        assert.ok(!("annotation.state.x" in rows));

        const beforeSubmit = calls.length;
        await editor.submit();
        const submittedCalls = calls.slice(beforeSubmit);
        assert.equal(submittedCalls.length, 1);
        assert.deepEqual(submittedCalls[0], ["annotation", { action: "set", slot: 3, text: "note" }]);

        for (const action of ["on", "off", "clear"]) {
          submittedAction = action;
          const beforeAction = calls.length;
          await editor.submit();
          const actionCalls = calls.slice(beforeAction);
          assert.equal(actionCalls.length, 1);
          assert.deepEqual(actionCalls[0], ["annotation", { action, slot: 3 }]);
        }

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)
    harness_path = tmp_path / "annotation-editor-harness.mjs"
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
