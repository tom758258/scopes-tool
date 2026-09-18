from __future__ import annotations

import dataclasses
import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.demo import DEMO_FUNCTIONS
import scopes_tool_webui.command_execution as command_execution_module
import scopes_tool_webui.commands as commands_module
from scopes_tool_webui.command_catalog import _command_supported_by_capabilities
from scopes_tool_webui.command_validation import WebUIRequestError, validate_job_request


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
MODEL_ID = "keysight-dsox4024a"

DEMO_COMMAND_IDS = [
    "demo-query",
    "demo-output",
    "demo-function",
    "demo-phase",
]


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_demo_command_family_routes_to_one_editor() -> None:
    entries = [entry for entry in commands_module.COMMANDS if entry["id"] in DEMO_COMMAND_IDS]

    assert [entry["id"] for entry in entries] == DEMO_COMMAND_IDS
    for entry in entries:
        assert entry["category"] == "DEMO", entry["id"]
        assert entry.get("group") is None, entry["id"]
        assert entry["editor"] == "demo", entry["id"]
        assert entry.get("browser_hidden") is not True, entry["id"]
        assert entry.get("hidden") is not True, entry["id"]
        assert "live" in entry["modes"] and "simulate" in entry["modes"]
        assert "dry-run" not in entry["modes"]


def test_demo_options_come_from_core_constants() -> None:
    entries = {entry["id"]: entry for entry in commands_module.COMMANDS}

    function = next(
        field for field in entries["demo-function"]["fields"] if field["name"] == "function"
    )

    assert tuple(function["options"]) == DEMO_FUNCTIONS


def test_demo_function_options_project_by_model() -> None:
    # 2000X has only common functions, 3000X/4000X have extensions
    catalog_2000 = next(
        entry for entry in commands_module.command_catalog() if entry["id"] == "demo-function"
    )
    # Need to inspect per-model presentation
    from scopes_tool_webui.command_catalog import _model_command_presentation, _command_presentation

    # Find raw command entry
    raw_2000 = next(entry for entry in commands_module.COMMANDS if entry["id"] == "demo-function")
    raw_3000 = raw_2000
    cap_2000 = capabilities_for_model_id("keysight-dsox2004a")
    cap_3000 = capabilities_for_model_id("keysight-dsox3024a")
    cap_4000 = capabilities_for_model_id("keysight-dsox4024a")
    present_2000 = _model_command_presentation(raw_2000, "keysight-dsox2004a")
    present_3000 = _model_command_presentation(raw_3000, "keysight-dsox3024a")
    present_4000 = _model_command_presentation(raw_3000, "keysight-dsox4024a")

    opts_2000 = present_2000["fields"]["function"]["options"]
    opts_3000 = present_3000["fields"]["function"]["options"]
    opts_4000 = present_4000["fields"]["function"]["options"]

    # Extensions should be missing on 2000X
    for ext in ("i2s", "can-lin", "flexray", "arinc", "mil", "mil2"):
        assert ext not in opts_2000
        assert ext in opts_3000
        assert ext in opts_4000
    # Common should be present on all
    for common in ("sine", "phase", "am"):
        assert common in opts_2000
        assert common in opts_3000
    # Order should follow DEMO_FUNCTIONS canonical ordering
    assert opts_2000 == tuple(v for v in DEMO_FUNCTIONS if v in cap_2000.demo_functions)
    assert opts_3000 == tuple(v for v in DEMO_FUNCTIONS if v in cap_3000.demo_functions)


def test_demo_commands_follow_model_support_flag() -> None:
    entries = {entry["id"]: entry for entry in commands_module.COMMANDS}
    supported = capabilities_for_model_id(MODEL_ID)
    unsupported = dataclasses.replace(supported, supports_demo=False)

    for command_id in DEMO_COMMAND_IDS:
        assert _command_supported_by_capabilities(entries[command_id], supported) is True
        assert _command_supported_by_capabilities(entries[command_id], unsupported) is False


def test_demo_phase_validation_uses_core_rules() -> None:
    request = validate_job_request({
        "command": "demo-phase",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {"action": "set", "degrees": 180},
    })
    assert request["parameters"]["degrees"] == 180
    with pytest.raises(WebUIRequestError):
        validate_job_request({
            "command": "demo-phase",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "set", "degrees": 400},
        })
    with pytest.raises(WebUIRequestError):
        validate_job_request({
            "command": "demo-phase",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "set"},
        })


def test_demo_output_set_does_not_touch_function(tmp_path: Path) -> None:
    calls: list[tuple] = []

    class FakeScope:
        capabilities = capabilities_for_model_id(MODEL_ID)

        def __init__(self):
            self._phase = 0.0

        def configure_demo_output(self, enabled):  # type: ignore[no-untyped-def]
            calls.append(("configure_demo_output", enabled))

        def query_demo_output(self):  # type: ignore[no-untyped-def]
            return {"enabled": True, "output_raw": "1"}

        def configure_demo_function(self, function):  # type: ignore[no-untyped-def]
            calls.append(("configure_demo_function", function))

        def query_demo_function(self):  # type: ignore[no-untyped-def]
            return {"function": "sine", "function_scpi": "SIN", "function_raw": "SIN"}

        def configure_demo_phase(self, degrees):  # type: ignore[no-untyped-def]
            self._phase = float(degrees)
            calls.append(("configure_demo_phase", degrees))

        def query_demo_phase(self):  # type: ignore[no-untyped-def]
            return {"phase_degrees": self._phase, "phase_raw": str(self._phase)}

        def query_demo(self):  # type: ignore[no-untyped-def]
            return {
                "enabled": True,
                "output_raw": "1",
                "function": "sine",
                "function_scpi": "SIN",
                "function_raw": "SIN",
                "phase_degrees": 10.0,
                "phase_raw": "10",
            }

    scope = FakeScope()
    result = command_execution_module._execute_scope_command(
        scope,
        "demo-output",
        "SIM::INSTR",
        {"action": "set", "enabled": True},
        tmp_path,
    )
    assert ("configure_demo_output", True) in calls
    assert all(name != "configure_demo_function" for name, *_ in calls)
    assert result["result"]["output"]["enabled"] is True

    aggregate = command_execution_module._execute_scope_command(
        scope, "demo-query", "SIM::INSTR", {}, tmp_path
    )
    assert aggregate["result"]["demo"]["enabled"] is True
    assert aggregate["result"]["demo"]["function"] == "sine"

    # function
    calls.clear()
    result_fn = command_execution_module._execute_scope_command(
        scope, "demo-function", "SIM::INSTR", {"action": "set", "function": "sine"}, tmp_path
    )
    assert ("configure_demo_function", "sine") in calls
    assert result_fn["result"]["function"]["function"] == "sine"

    # phase
    calls.clear()
    result_phase = command_execution_module._execute_scope_command(
        scope, "demo-phase", "SIM::INSTR", {"action": "set", "degrees": 90}, tmp_path
    )
    assert ("configure_demo_phase", 90) in calls
    assert result_phase["result"]["phase"]["phase_degrees"] == 90


def test_demo_function_canonical_preserved_through_validation_and_execution(tmp_path: Path) -> None:
    request = validate_job_request({
        "command": "demo-function",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {"action": "set", "function": "sine"},
    })
    assert request["parameters"]["function"] == "sine"

    result = command_execution_module.execute_command(
        "demo-function",
        mode="simulate",
        resource=None,
        model_id=MODEL_ID,
        parameters=request["parameters"],
        artifact_dir=tmp_path,
    )
    assert result["result"]["function"]["function"] == "sine"


def test_demo_localization_keys() -> None:
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    assert '"field.demo-phase.degrees": "Phase (degrees)"' in english
    assert '"field.demo-phase.degrees": "相位（度）"' in chinese
    for key in ("sine", "phase", "setup-hold", "i2c", "can-lin"):
        assert f'"enum.demo-function.{key}":' in english, key
        assert f'"enum.demo-function.{key}":' in chinese, key


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_demo_editor_selected_command_presentation(tmp_path: Path) -> None:
    catalog_json = json.dumps(commands_module.command_catalog())
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    app_source = read_static("app.js")
    index_source = read_static("index.html")

    assert "demo: () => demoEditor," in app_source
    assert "elements.demoEditor.hidden = editorKind !== " in app_source
    assert 'if (editorKind === "demo") demoEditor?.schedulePresentation();' in app_source
    assert "demoEditor.refreshButton.hidden = editorKind !== \"demo\";" in app_source
    assert "demoEditor?.rerender();" in app_source
    # DEMO uses the existing command-specific header path, so each selected
    # DEMO command shows its own label/description.
    assert '["annotation", "cursor", "measurement", "reference-display", "save-export", "wgen", "demo", "trigger", "search"].includes(editorKind)' in app_source
    assert '["annotation", "cursor", "measurement", "reference", "reference-display", "save-export", "wgen", "demo", "trigger", "search"].includes(editorKind)' in app_source
    assert "demoEditor?.entry?.button" in app_source
    assert '"demo-output": ["demo-query", "demo-output"]' in app_source
    assert '"demo-function": ["demo-query", "demo-function"]' in app_source
    assert '"demo-phase": ["demo-query", "demo-phase"]' in app_source
    assert 'id="demo-editor"' in index_source
    for key in (
        '"command.demo-query": "Demo Signals state"',
        '"command.demo-output": "Demo output"',
        '"description.demo-query":',
        '"demo.editor.title": "Demo Signals"',
        '"demo.editor.description":',
        '"demo.state.phase":',
    ):
        assert key in english, key
    for key in (
        '"command.demo-query": "示範訊號狀態"',
        '"command.demo-output": "示範訊號輸出"',
        '"description.demo-query":',
        '"demo.editor.title": "示範訊號"',
        '"demo.editor.description":',
        '"demo.state.phase":',
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
        let selectedId = "demo-query";
        globalThis.CommandForm = class CommandForm {
          constructor(container, _catalog) { this.container = container; this.command = null; this.disabled = false; }
          render(command) { this.command = command; }
          values() {
            if (selectedId === "demo-output") return { action: "set", enabled: true };
            if (selectedId === "demo-function") return { action: "set", function: "sine" };
            if (selectedId === "demo-phase") return { action: "set", degrees: 90 };
            return {};
          }
          setDisabled(disabled) { this.disabled = disabled; }
          clearDirty() {}
        };

        const calls = [];
        const hooks = {
          calls,
          contextKey: () => `live||keysight-dsox4024a`,
          mode: () => "live",
          selectedCommand: () => catalog.commands.find((command) => command.id === selectedId),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          headerActions: new FakeNode("div"),
          async executeCommand(id, parameters, _options) {
            calls.push([id, parameters]);
            if (id === "demo-query") {
              return { status: "completed", result: { result: { demo: { enabled: false, function: "sine", phase_degrees: 10 } } } };
            }
            if (id === "demo-output") {
              return { status: "completed", result: { result: { output: { enabled: parameters.enabled } } } };
            }
            if (id === "demo-function") {
              return { status: "completed", result: { result: { function: { function: parameters.function } } } };
            }
            if (id === "demo-phase") {
              return { status: "completed", result: { result: { phase: { phase_degrees: parameters.degrees } } } };
            }
            return { status: "completed", result: { result: {} } };
          },
        };
        const catalog = {
          commands: __CATALOG__,
          groupLabel: (group) => group,
          commandLabel: (command) => command.id,
          supported: () => true,
        };

        let editorSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/demo-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class DemoEditor", "class DemoEditor")
          + "\nglobalThis.DemoEditor = DemoEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const editor = new globalThis.DemoEditor(new FakeNode("div"), catalog, hooks);
        await editor.refresh(true, true);
        assert.deepEqual(calls, [["demo-query", {}]]);
        assert.ok(hooks.headerActions.children.includes(editor.refreshButton));
        assert.ok(hooks.headerActions.children.includes(editor.entry.button));
        assert.equal(editor.entry.form.container.className, "command-form");
        assert.ok(!editor.sectionsHost.children[0].children.includes(editor.entry.button));
        // Only the selected command is rendered; demo-query has no fields.
        assert.equal(editor.sectionsHost.children.length, 1);
        assert.equal(editor.sectionsHost.children[0].hidden, true);
        assert.equal(editor.entry.form.container.hidden, true);
        // demo-query reuses the header Read action; no second query button.
        assert.equal(editor.entry.button.hidden, true);

        selectedId = "demo-phase";
        const queryButton = editor.entry.button;
        const beforePhaseRead = calls.length;
        await editor.refresh(true, true);
        assert.deepEqual(calls.slice(beforePhaseRead), [["demo-query", {}]]);
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
        assert.deepEqual(setterCalls[0], ["demo-phase", { action: "set", degrees: 90 }]);
        assert.ok(!calls.slice(beforeSubmit).some((call) => call[0] === "demo-output"));
        assert.ok(!calls.slice(beforeSubmit).some((call) => call[0] === "demo-function"));

        selectedId = "demo-output";
        await editor.refresh(true, true);
        const beforeOutput = calls.length;
        await editor.submit();
        const outputCalls = calls.slice(beforeOutput);
        assert.equal(outputCalls.length, 1);
        assert.deepEqual(outputCalls[0], ["demo-output", { action: "set", enabled: true }]);
        assert.ok(!outputCalls.some((call) => call[0] === "demo-function"));

        selectedId = "demo-function";
        await editor.refresh(true, true);
        const beforeFunction = calls.length;
        await editor.submit();
        const functionCalls = calls.slice(beforeFunction);
        assert.equal(functionCalls.length, 1);
        assert.deepEqual(functionCalls[0], ["demo-function", { action: "set", function: "sine" }]);
        assert.ok(!functionCalls.some((call) => call[0] === "demo-output"));

        // Switching back to demo-query hides the section button again.
        selectedId = "demo-query";
        await editor.refresh(true, true);
        assert.equal(editor.entry.button.hidden, true);
        assert.equal(editor.sectionsHost.children.length, 1);

        const headerCount = hooks.headerActions.children.length;
        const oldApply = editor.entry.button;
        editor.rerender();
        assert.equal(hooks.headerActions.children.length, headerCount);
        assert.ok(!hooks.headerActions.children.includes(oldApply));

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)
    harness_path = tmp_path / "demo-editor-harness.mjs"
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
