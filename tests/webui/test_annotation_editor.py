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


def test_annotation_commands_carry_annotation_editor_metadata() -> None:
    legacy = next(
        item for item in commands_module.COMMANDS if item["id"] == "annotation"
    )
    assert legacy.get("hidden") is True

    public = {
        entry["id"]: entry for entry in commands_module.command_catalog()
    }
    assert {
        "annotation-query",
        "annotation-set",
        "annotation-on",
        "annotation-off",
        "annotation-clear",
    } <= set(public)
    assert "annotation" not in public

    for command_id in (
        "annotation-query",
        "annotation-set",
        "annotation-on",
        "annotation-off",
        "annotation-clear",
    ):
        entry = public[command_id]
        assert entry["category"] == "Annotation"
        assert "group" not in entry
        assert entry["editor"] == "annotation"
        assert entry.get("browser_hidden") is not True
        assert entry.get("hidden") is not True
        assert list(entry["modes"]) == ["live", "simulate"]

    assert [field["name"] for field in public["annotation-query"]["fields"]] == ["slot"]
    assert public["annotation-query"]["presentation"]["action"] == "read"
    assert public["annotation-clear"]["presentation"]["action"] == "clear"
    setters = public["annotation-set"]["fields"]
    assert [field["name"] for field in setters] == [
        "slot",
        "text",
        "color",
        "background",
        "x",
        "y",
    ]
    color = next(field for field in setters if field["name"] == "color")
    assert color["type"] == "enum"
    assert list(color["options"]) == [
        "CH1", "CH2", "CH3", "CH4", "DIG", "MATH", "REF", "MARK", "WHITE", "RED",
    ]
    background = next(field for field in setters if field["name"] == "background")
    assert background["type"] == "enum"
    assert list(background["options"]) == ["OPAQ", "INV", "TRAN"]


def test_annotation_live_slot_admission_uses_capabilities_not_static_options() -> None:
    resource = "SIM::INSTR"
    admitted = validate_job_request({
        "command": "annotation-set",
        "mode": "live",
        "resource": resource,
        "parameters": {"slot": 2, "text": "hello"},
    })
    assert admitted["parameters"]["slot"] == 2
    with pytest.raises(WebUIRequestError, match="at most"):
        validate_job_request({
            "command": "annotation-set",
            "mode": "live",
            "resource": resource,
            "parameters": {"slot": 99, "text": "hello"},
        })
    with pytest.raises(WebUIRequestError, match="range 1-1"):
        validate_job_request({
            "command": "annotation-set",
            "mode": "simulate",
            "model_id": "keysight-dsox2004a",
            "parameters": {"slot": 2, "text": "hello"},
        })
    defaulted = validate_job_request({
        "command": "annotation-on",
        "mode": "live",
        "resource": resource,
        "parameters": {},
    })
    assert defaulted["parameters"]["slot"] == 1


def test_annotation_model_projection_gates_slot_and_position() -> None:
    catalog = {
        entry["id"]: entry for entry in commands_module.command_catalog()
    }
    for command_id in (
        "annotation-query",
        "annotation-set",
        "annotation-on",
        "annotation-off",
        "annotation-clear",
    ):
        models = catalog[command_id]["presentation"]["models"]
        slot_2000x = models["keysight-dsox2004a"]["fields"]["slot"]
        slot_4000x = models["keysight-dsox4024a"]["fields"]["slot"]

        assert slot_2000x.get("hidden") is True
        assert list(slot_2000x.get("options", [])) == [1]
        assert list(slot_4000x.get("options", [])) == list(range(1, 11))
        assert slot_4000x.get("hidden") is not True
    position_2000x = catalog["annotation-set"]["presentation"]["models"]["keysight-dsox2004a"]["fields"]
    position_4000x = catalog["annotation-set"]["presentation"]["models"]["keysight-dsox4024a"]["fields"]
    assert position_2000x["x"].get("hidden") is True
    assert position_2000x["y"].get("hidden") is True
    assert position_4000x.get("x", {}).get("hidden") is not True
    assert position_4000x.get("y", {}).get("hidden") is not True


def test_annotation_set_command_validation_requires_at_least_one_setter() -> None:
    request = validate_job_request({
        "command": "annotation-set",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {"slot": 1, "text": "hello"},
    })

    assert request["parameters"]["text"] == "hello"
    with pytest.raises(WebUIRequestError, match="at least one"):
        validate_job_request({
            "command": "annotation-set",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"slot": 1},
        })
    with pytest.raises(WebUIRequestError, match="unknown parameter"):
        validate_job_request({
            "command": "annotation-off",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"slot": 1, "text": "hello"},
        })


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


def test_annotation_split_execution_applies_only_provided_setters(tmp_path: Path) -> None:
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
                "enabled": False,
                "text": "hello",
                "color": "CH1",
                "background": "OPAQ",
                "x": None,
                "y": None,
            }

    scope = FakeScope()
    result = command_execution_module._execute_scope_command(
        scope,
        "annotation-set",
        "SIM::INSTR",
        {"slot": 1, "text": "hello"},
        tmp_path,
    )

    assert calls == [("text", "hello", 1), ("query", 1)]
    assert result["result"]["annotation"]["text"] == "hello"

    calls.clear()
    command_execution_module._execute_scope_command(
        scope, "annotation-on", "SIM::INSTR", {"slot": 2}, tmp_path
    )

    assert calls == [("enabled", True, 2), ("query", 2)]

    calls.clear()
    command_execution_module._execute_scope_command(
        scope, "annotation-off", "SIM::INSTR", {"slot": 2}, tmp_path
    )

    assert calls == [("enabled", False, 2), ("query", 2)]

    calls.clear()
    command_execution_module._execute_scope_command(
        scope, "annotation-clear", "SIM::INSTR", {"slot": 2}, tmp_path
    )

    assert calls == [("clear", 2), ("query", 2)]

    calls.clear()
    command_execution_module._execute_scope_command(
        scope, "annotation-query", "SIM::INSTR", {"slot": 3}, tmp_path
    )

    assert calls == [("query", 3)]


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
    # annotation-query/set/on/off/clear shows its own label/description.
    assert '["annotation", "cursor", "measurement", "reference-display", "save-export"].includes(editorKind)' in app_source
    assert '["annotation", "cursor", "measurement", "reference", "reference-display", "save-export"].includes(editorKind)' in app_source
    assert '"annotation-set": ["annotation-query", "annotation-set"]' in app_source
    assert '"annotation-clear": ["annotation-query", "annotation-clear"]' in app_source
    assert 'id="annotation-editor"' in index_source
    for key in (
        '"command.annotation-query": "Annotation state"',
        '"description.annotation-query":',
        '"command.annotation-set": "Set annotation"',
        '"description.annotation-set":',
        '"command.annotation-on": "Turn on annotation"',
        '"description.annotation-on":',
        '"command.annotation-off": "Turn off annotation"',
        '"description.annotation-off":',
        '"command.annotation-clear": "Clear annotation text"',
        '"description.annotation-clear":',
        '"annotation.editor.read": "Read annotation settings"',
        '"annotation.state.enabled":',
        '"annotation.state.background":',
        '"enum.annotation-color.CH1": "CH1"',
        '"enum.annotation-background.OPAQ": "Opaque"',
        '"help.annotation.x": "4000X annotation X position.',
    ):
        assert key in english, key
    for key in (
        '"command.annotation-query": "註解狀態"',
        '"description.annotation-query":',
        '"command.annotation-set": "設定註解"',
        '"description.annotation-set":',
        '"command.annotation-on": "開啟註解"',
        '"description.annotation-on":',
        '"command.annotation-off": "關閉註解"',
        '"description.annotation-off":',
        '"command.annotation-clear": "清除註解文字"',
        '"description.annotation-clear":',
        '"annotation.editor.read": "讀取註解設定"',
        '"annotation.state.enabled":',
        '"annotation.state.background":',
        '"enum.annotation-background.OPAQ": "不透明"',
        '"enum.annotation-background.INV": "反相"',
        '"help.annotation.x": "4000X 註解 X 位置。',
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
          get classList() {
            const node = this;
            return {
              add(...tokens) {
                const current = new Set(node.className.split(" ").filter(Boolean));
                for (const token of tokens) current.add(token);
                node.className = [...current].join(" ");
              },
              contains(token) { return node.className.split(" ").includes(token); },
            };
          }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.queueMicrotask = (fn) => { fn(); };

        globalThis.translate = (key) => key;
        let selectedId = "annotation-query";
        globalThis.CommandForm = class CommandForm {
          constructor(container, _catalog) { this.container = container; this.command = null; this.disabled = false; }
          render(command) { this.command = command; }
          values() {
            if (selectedId === "annotation-set") return { slot: 3, text: "note" };
            if (selectedId === "annotation-query") return {};
            return { slot: 3 };
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
          description: (command) => `description.${command.id}`,
          supported: () => true,
          // Single-slot projection hides the slot field, leaving query with
          // no visible fields.
          fieldsFor: (command) => command.id === "annotation-query" ? [] : command.fields,
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

        // Non-annotation selection clears the workspace.
        const idle = new globalThis.AnnotationEditor(new FakeNode("div"), catalog, {
          ...hooks, selectedCommand: () => ({ id: "measure", editor: null }),
        });
        await idle.refresh(true, true);
        assert.equal(calls.length, 0);

        const editor = new globalThis.AnnotationEditor(new FakeNode("div"), catalog, hooks);
        await editor.refresh(true, true);
        assert.ok(hooks.headerActions.children.includes(editor.refreshButton));
        assert.ok(hooks.headerActions.children.includes(editor.entry.button));
        assert.equal(editor.entry.form.container.classList.contains("command-form"), true);
        assert.ok(!editor.sectionsHost.children[0].children.includes(editor.entry.button));

        assert.deepEqual(calls[0], ["annotation-query", { slot: 1 }]);
        // No inline annotation-state panel; state surfaces through Workspace Result.
        // No inner heading row; the page header already shows the command label.
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
        assert.ok(!classNames.includes("annotation-editor-state"));
        assert.ok(!classNames.includes("trigger-editor-head"));
        assert.ok(!classNames.includes("trigger-editor-heading"));
        assert.ok(!classNames.includes("muted compact-note"));
        // annotation-query has no visible fields on a single-slot model; its
        // empty section stays hidden.
        assert.equal(editor.sectionsHost.children[0].hidden, true);
        assert.equal(editor.entry.form.container.hidden, true);
        // annotation-query reuses the header Read action; no second query button.
        assert.equal(editor.entry.button.hidden, true);

        selectedId = "annotation-set";
        const beforeSetRead = calls.length;
        await editor.refresh(true, true);
        assert.deepEqual(calls.slice(beforeSetRead), [["annotation-query", { slot: 1 }]]);
        assert.equal(editor.entry.button.hidden, false);
        assert.equal(editor.entry.button.textContent, "actions.apply");
        assert.equal(editor.sectionsHost.children[0].hidden, false);
        assert.equal(editor.entry.form.container.hidden, false);

        const beforeSet = calls.length;
        await editor.submit();
        const setCalls = calls.slice(beforeSet);
        assert.equal(setCalls.length, 1);
        assert.deepEqual(setCalls[0], ["annotation-set", { slot: 3, text: "note" }]);

        for (const [id, label] of [["annotation-on", "annotation-on"], ["annotation-off", "annotation-off"], ["annotation-clear", "actions.clear"]]) {
          selectedId = id;
          const beforeActionRead = calls.length;
          await editor.refresh(true, true);
          assert.deepEqual(calls.slice(beforeActionRead), [["annotation-query", { slot: 1 }]]);
          assert.equal(editor.entry.button.hidden, false);
          assert.equal(editor.entry.button.textContent, label);
          assert.equal(editor.sectionsHost.children[0].hidden, false);
          const beforeAction = calls.length;
          await editor.submit();
          const actionCalls = calls.slice(beforeAction);
          assert.equal(actionCalls.length, 1);
          assert.deepEqual(actionCalls[0], [id, { slot: 3 }]);
        }

        // Switching back to annotation-query hides the section button again.
        selectedId = "annotation-query";
        const callsBeforeBack = calls.length;
        await editor.refresh(true, false);
        assert.equal(calls.length, callsBeforeBack);
        assert.equal(editor.entry.button.hidden, true);
        assert.equal(editor.sectionsHost.children[0].hidden, true);

        const headerCount = hooks.headerActions.children.length;
        const oldApply = editor.entry.button;
        const callsBeforeLayout = calls.length;
        editor.rerender();
        assert.equal(hooks.headerActions.children.length, headerCount);
        assert.ok(!hooks.headerActions.children.includes(oldApply));
        assert.ok(hooks.headerActions.children.includes(editor.entry.button));
        const local = new globalThis.AnnotationEditor(new FakeNode("div"), catalog, {
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
