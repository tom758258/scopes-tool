from __future__ import annotations

import dataclasses
import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.wgen import WGEN_FUNCTIONS, WGEN_LOADS
import scopes_tool_webui.command_execution as command_execution_module
import scopes_tool_webui.commands as commands_module
from scopes_tool_webui.command_catalog import _command_supported_by_capabilities
from scopes_tool_webui.command_validation import WebUIRequestError, validate_job_request


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
MODEL_ID = "keysight-dsox4024a"

WGEN_COMMAND_IDS = [
    "wgen-query",
    "wgen-output",
    "wgen-function",
    "wgen-frequency",
    "wgen-voltage",
    "wgen-offset",
    "wgen-load",
]


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_wgen_command_family_routes_to_one_editor() -> None:
    entries = [entry for entry in commands_module.COMMANDS if entry["id"] in WGEN_COMMAND_IDS]

    assert [entry["id"] for entry in entries] == WGEN_COMMAND_IDS
    for entry in entries:
        assert entry["category"] == "WGEN", entry["id"]
        assert entry["group"] == "wgen", entry["id"]
        assert entry["editor"] == "wgen", entry["id"]
        assert entry.get("browser_hidden") is not True, entry["id"]
        assert entry.get("hidden") is not True, entry["id"]


def test_wgen_options_come_from_core_constants() -> None:
    entries = {entry["id"]: entry for entry in commands_module.COMMANDS}

    function = next(
        field for field in entries["wgen-function"]["fields"] if field["name"] == "function"
    )
    load = next(
        field for field in entries["wgen-load"]["fields"] if field["name"] == "load"
    )

    assert tuple(function["options"]) == WGEN_FUNCTIONS
    assert tuple(load["options"]) == WGEN_LOADS


def test_wgen_commands_follow_model_support_flag() -> None:
    entries = {entry["id"]: entry for entry in commands_module.COMMANDS}
    supported = capabilities_for_model_id(MODEL_ID)
    unsupported = dataclasses.replace(supported, supports_wgen=False)

    for command_id in WGEN_COMMAND_IDS:
        assert _command_supported_by_capabilities(entries[command_id], supported) is True
        assert _command_supported_by_capabilities(entries[command_id], unsupported) is False


def test_wgen_set_validation_uses_core_rules() -> None:
    request = validate_job_request({
        "command": "wgen-frequency",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {"action": "set", "frequency_hz": 1000.0},
    })

    assert request["parameters"]["frequency_hz"] == 1000.0
    with pytest.raises(WebUIRequestError, match="frequency"):
        validate_job_request({
            "command": "wgen-frequency",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "set"},
        })
    with pytest.raises(WebUIRequestError, match="function"):
        validate_job_request({
            "command": "wgen-function",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "set", "function": "triangle"},
        })


def test_wgen_frequency_set_does_not_touch_output(tmp_path: Path) -> None:
    calls: list[tuple] = []

    class FakeScope:
        capabilities = object()

        def configure_wgen_output(self, enabled):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_output", enabled))

        def query_wgen_output(self):  # type: ignore[no-untyped-def]
            return {"enabled": False, "output_raw": "0"}

        def configure_wgen_function(self, function):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_function", function))

        def query_wgen_function(self):  # type: ignore[no-untyped-def]
            return {"function": "sine", "function_scpi": "SINusoid", "function_raw": "SIN"}

        def configure_wgen_frequency(self, frequency_hz):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_frequency", frequency_hz))

        def query_wgen_frequency(self):  # type: ignore[no-untyped-def]
            calls.append(("query_wgen_frequency",))
            return {"frequency_hz": 1000.0, "frequency_raw": "1.0E+3"}

        def configure_wgen_voltage(self, amplitude_volts):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_voltage", amplitude_volts))

        def query_wgen_voltage(self):  # type: ignore[no-untyped-def]
            return {"amplitude_volts": 1.0, "voltage_raw": "1.0E+0"}

        def configure_wgen_offset(self, offset_volts):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_offset", offset_volts))

        def query_wgen_offset(self):  # type: ignore[no-untyped-def]
            return {"offset_volts": 0.0, "offset_raw": "0.0E+0"}

        def configure_wgen_load(self, load):  # type: ignore[no-untyped-def]
            calls.append(("configure_wgen_load", load))

        def query_wgen_load(self):  # type: ignore[no-untyped-def]
            return {"load": "fifty", "load_scpi": "FIFTy", "load_raw": "FIFT"}

        def query_wgen(self):  # type: ignore[no-untyped-def]
            return {
                "enabled": False,
                "output_raw": "0",
                "function": "sine",
                "function_scpi": "SINusoid",
                "function_raw": "SIN",
                "frequency_hz": 1000.0,
                "frequency_raw": "1.0E+3",
                "amplitude_volts": 1.0,
                "voltage_raw": "1.0E+0",
                "offset_volts": 0.0,
                "offset_raw": "0.0E+0",
                "load": "fifty",
                "load_scpi": "FIFTy",
                "load_raw": "FIFT",
            }

    scope = FakeScope()
    result = command_execution_module._execute_scope_command(
        scope,
        "wgen-frequency",
        "SIM::INSTR",
        {"action": "set", "frequency_hz": 1000.0},
        tmp_path,
    )

    assert ("configure_wgen_frequency", 1000.0) in calls
    assert all(name != "configure_wgen_output" for name, *_ in calls)
    assert result["result"]["frequency"]["frequency_hz"] == 1000.0

    aggregate = command_execution_module._execute_scope_command(
        scope, "wgen-query", "SIM::INSTR", {}, tmp_path
    )

    assert aggregate["result"]["wgen"]["load"] == "fifty"
    assert aggregate["result"]["wgen"]["enabled"] is False


@pytest.mark.skipif(
    subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
    reason="Node.js is required for frontend behavior checks",
)
def test_wgen_editor_aggregate_refresh_and_setter(tmp_path: Path) -> None:
    catalog_json = json.dumps(commands_module.command_catalog())
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    app_source = read_static("app.js")
    index_source = read_static("index.html")

    assert "wgen: () => wgenEditor," in app_source
    assert "elements.wgenEditor.hidden = editorKind !== " in app_source
    assert 'if (editorKind === "wgen") wgenEditor?.schedulePresentation();' in app_source
    assert 'wgenEditor.refreshButton.hidden = editorKind !== "wgen";' in app_source
    assert "wgenEditor?.rerender();" in app_source
    assert 'id="wgen-editor"' in index_source
    for key in (
        '"command.wgen-query": "Waveform generator state"',
        '"command.wgen-load": "Generator load"',
        '"description.wgen-query":',
        '"wgen.editor.title": "Waveform generator"',
        '"wgen.editor.description":',
        '"wgen.state.amplitude":',
        '"enum.wgen-function.sine":',
        '"enum.wgen-load.fifty":',
    ):
        assert key in english, key
    for key in (
        '"command.wgen-query": "波形產生器狀態"',
        '"command.wgen-load": "產生器負載"',
        '"description.wgen-query":',
        '"wgen.editor.title": "波形產生器"',
        '"wgen.editor.description":',
        '"wgen.state.amplitude":',
        '"enum.wgen-function.sine":',
        '"enum.wgen-load.fifty":',
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
          values() { return { action: "set", frequency_hz: 1000 }; }
          setDisabled(disabled) { this.disabled = disabled; }
          clearDirty() {}
        };

        const calls = [];
        const aggregate = {
          enabled: false, output_raw: "0", function: "sine",
          function_scpi: "SINusoid", function_raw: "SIN",
          frequency_hz: 1000, frequency_raw: "1.0E+3",
          amplitude_volts: 1.0, voltage_raw: "1.0E+0",
          offset_volts: 0.0, offset_raw: "0.0E+0",
          load: "fifty", load_scpi: "FIFTy", load_raw: "FIFT",
        };
        const hooks = {
          calls,
          contextKey: () => "simulate||keysight-dsox4024a",
          selectedCommand: () => ({ id: "wgen-frequency", editor: "wgen", group: "wgen" }),
          isAvailable: () => true,
          isExecutionBusy: () => false,
          headerActions: new FakeNode("div"),
          async executeCommand(id, parameters, _options) {
            calls.push([id, parameters]);
            if (id === "wgen-query") {
              return { status: "completed", result: { result: { wgen: aggregate } } };
            }
            return { status: "completed", result: { result: { frequency: { frequency_hz: 1000 } } } };
          },
        };
        const catalog = {
          commands: __CATALOG__,
          groupLabel: (group) => group,
          commandLabel: (command) => command.id,
          supported: () => true,
        };

        let editorSource = fs.readFileSync(
          path.join(process.cwd(), "src/scopes_tool_webui/static/wgen-editor.js"),
          "utf8",
        );
        editorSource = editorSource
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace("export class WgenEditor", "class WgenEditor")
          + "\nglobalThis.WgenEditor = WgenEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(editorSource)}`);

        const editor = new globalThis.WgenEditor(new FakeNode("div"), catalog, hooks);
        await editor.refresh(true, true);
        assert.deepEqual(calls[0], ["wgen-query", {}]);
        assert.equal(editor.entries.length, 7);
        const panelText = (id) => editor.entryFor(id).panel.children.map(
          (row) => [row.children[0].textContent, row.children[1].textContent],
        );
        assert.deepEqual(panelText("wgen-output"), [["wgen.state.output", "enum.disable"]]);
        assert.deepEqual(panelText("wgen-frequency"), [["wgen.state.frequency", "1000"]]);
        assert.deepEqual(panelText("wgen-voltage"), [["wgen.state.amplitude", "1"]]);
        assert.deepEqual(panelText("wgen-load"), [["wgen.state.load", "fifty"]]);

        const frequency = editor.entryFor("wgen-frequency");
        const beforeSubmit = calls.length;
        await editor.submit(frequency);
        const setterCalls = calls.slice(beforeSubmit);
        assert.equal(setterCalls.length, 1);
        assert.deepEqual(setterCalls[0], ["wgen-frequency", { action: "set", frequency_hz: 1000 }]);
        assert.ok(!calls.slice(beforeSubmit).some((call) => call[0] === "wgen-output"));
        assert.ok(!calls.slice(beforeSubmit).some((call) => call[0] === "wgen-query"));
        const frequencyPanel = editor.entryFor("wgen-frequency").panel.children.map(
          (row) => [row.children[0].textContent, row.children[1].textContent],
        );
        assert.deepEqual(frequencyPanel, [["wgen.state.frequency", "1000"]]);

        const beforeRefresh = calls.length;
        await editor.refresh(true, true);
        const refreshCalls = calls.slice(beforeRefresh).filter((call) => call[0] === "wgen-query");
        assert.equal(refreshCalls.length, 1);

        const queryEntry = editor.entryFor("wgen-query");
        const beforeQuerySubmit = calls.length;
        await editor.submit(queryEntry);
        const querySubmitCalls = calls.slice(beforeQuerySubmit).filter((call) => call[0] === "wgen-query");
        assert.equal(querySubmitCalls.length, 1);

        console.log(JSON.stringify({ ok: true }));
        '''
    ).replace("__CATALOG__", catalog_json)
    harness_path = tmp_path / "wgen-editor-harness.mjs"
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
