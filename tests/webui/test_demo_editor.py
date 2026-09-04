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
        assert entry["group"] == "demo", entry["id"]
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


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_demo_editor_aggregate_refresh_and_setter(tmp_path: Path) -> None:
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
        globalThis.CommandForm = class CommandForm {
          constructor(container, _catalog) { this.container = container; this.command = null; this.disabled = false; }
          render(command) { this.command = command; }
          values() {
            if (this.command?.id === "demo-output") return { action: "set", enabled: true };
            if (this.command?.id === "demo-function") return { action: "set", function: "sine" };
            if (this.command?.id === "demo-phase") return { action: "set", degrees: 90 };
            return { action: "query" };
          }
          setDisabled(disabled) { this.disabled = disabled; }
          clearDirty() {}
        };

        const calls = [];
        let aggregate = {
          enabled: false, output_raw: "0",
          function: "sine", function_scpi: "SIN", function_raw: "SIN",
          phase_degrees: 10, phase_raw: "10",
        };
        const hooks = {
          calls,
          contextKey: () => `live||keysight-dsox4024a`,
          mode: () => "live",
          selectedCommand: () => ({ id: "demo-output", editor: "demo", group: "demo" }),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          headerActions: new FakeNode("div"),
          async executeCommand(id, parameters, _options) {
            calls.push([id, parameters]);
            if (id === "demo-query") {
              return { status: "completed", result: { result: { demo: aggregate } } };
            }
            if (id === "demo-output") {
              aggregate = { ...aggregate, enabled: parameters.enabled };
              return { status: "completed", result: { result: { output: { enabled: parameters.enabled } } } };
            }
            if (id === "demo-function") {
              aggregate = { ...aggregate, function: parameters.function };
              return { status: "completed", result: { result: { function: { function: parameters.function } } } };
            }
            if (id === "demo-phase") {
              aggregate = { ...aggregate, phase_degrees: parameters.degrees };
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
        assert.deepEqual(calls[0], ["demo-query", {}]);
        assert.equal(editor.entries.length, 4);
        const panelText = (id) => editor.entryFor(id).panel.children.map(
          (row) => [row.children[0].textContent, row.children[1].textContent],
        );
        assert.deepEqual(panelText("demo-output"), [["demo.state.output", "enum.disable"]]);
        assert.deepEqual(panelText("demo-function"), [["demo.state.function", "sine"]]);
        assert.deepEqual(panelText("demo-phase"), [["demo.state.phase", "10"]]);

        const output = editor.entryFor("demo-output");
        const beforeSubmit = calls.length;
        await editor.submit(output);
        const setterCalls = calls.slice(beforeSubmit);
        assert.equal(setterCalls.length, 1);
        assert.deepEqual(setterCalls[0], ["demo-output", { action: "set", enabled: true }]);
        assert.ok(!calls.slice(beforeSubmit).some((call) => call[0] === "demo-function"));
        const outputPanel = editor.entryFor("demo-output").panel.children.map(
          (row) => [row.children[0].textContent, row.children[1].textContent],
        );
        assert.deepEqual(outputPanel, [["demo.state.output", "enum.enable"]]);

        const beforeRefresh = calls.length;
        await editor.refresh(true, true);
        const refreshCalls = calls.slice(beforeRefresh).filter((call) => call[0] === "demo-query");
        assert.equal(refreshCalls.length, 1);

        const queryEntry = editor.entryFor("demo-query");
        const beforeQuerySubmit = calls.length;
        await editor.submit(queryEntry);
        const querySubmitCalls = calls.slice(beforeQuerySubmit).filter((call) => call[0] === "demo-query");
        assert.equal(querySubmitCalls.length, 1);

        const phase = editor.entryFor("demo-phase");
        await editor.submit(phase);
        assert.deepEqual(calls.slice(-1)[0], ["demo-phase", { action: "set", degrees: 90 }]);

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
