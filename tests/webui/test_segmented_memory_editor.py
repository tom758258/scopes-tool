from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from scopes_tool_webui import command_execution as command_execution_module
from scopes_tool_webui.command_validation import WebUIRequestError, validate_job_request
from scopes_tool_webui.commands import COMMANDS, command_catalog


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"
EDITOR_SOURCE = STATIC_ROOT / "segmented-editor.js"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_segmented_memory_uses_dedicated_editor_and_existing_command_contract() -> None:
    definition = next(entry for entry in COMMANDS if entry["id"] == "segmented-memory")
    projected = next(
        entry for entry in command_catalog() if entry["id"] == "segmented-memory"
    )

    assert definition["editor"] == "segmented"
    assert [field["name"] for field in definition["fields"]] == [
        "action",
        "segments",
        "index",
    ]
    assert projected["presentation"]["query_value"] == "query"
    assert projected["presentation"]["action_choices"] == [
        "enable",
        "disable",
        "select",
    ]


def test_app_routes_segmented_editor_and_localizes_its_controls() -> None:
    app = read_static("app.js")
    html = read_static("index.html")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert 'import { SegmentedEditor } from "/static/segmented-editor.js";' in app
    assert 'segmented: () => segmentedEditor,' in app
    assert 'id="segmented-editor" class="segmented-editor" hidden' in html
    assert 'elements.segmentedEditor.hidden = editorKind !== "segmented";' in app
    assert '"segmented.editor.enter": "Enter Segmented"' in english
    assert '"segmented.editor.exit": "Exit Segmented"' in english
    for key in (
        "segmented.editor.title",
        "segmented.editor.mode",
        "segmented.editor.configuredSegments",
        "segmented.editor.acquiredSegments",
        "segmented.editor.segment",
        "segmented.editor.previous",
        "segmented.editor.next",
        "segmented.editor.select",
        "segmented.editor.timeTag",
        "segmented.editor.enter",
        "segmented.editor.exit",
        "segmented.editor.unavailable",
    ):
        assert f'"{key}"' in chinese


EDITOR_HARNESS = r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.className = "";
            this.textContent = "";
            this.value = "";
            this.min = "";
            this.max = "";
            this.required = false;
            this.parentNode = null;
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) {
            this.children = [...nodes];
            for (const node of nodes) node.parentNode = this;
          }
          append(...nodes) {
            this.children.push(...nodes);
            for (const node of nodes) node.parentNode = this;
          }
          remove() {
            if (!this.parentNode) return;
            this.parentNode.children = this.parentNode.children.filter((node) => node !== this);
            this.parentNode = null;
          }
          setAttribute() {}
          setCustomValidity(message) { this.customValidity = message; }
          checkValidity() {
            const value = Number(this.value);
            return !(this.required && this.value === "")
              && Number.isFinite(value)
              && (!this.min || value >= Number(this.min))
              && (!this.max || value <= Number(this.max))
              && (!this.step || Number.isInteger(value));
          }
          reportValidity() { this.reported = true; }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.translate = (key) => ({
          "enum.realtime": "Realtime",
          "enum.segmented": "Segmented",
        })[key] || key;
        globalThis.hasTranslation = (key) => key.startsWith("enum.");

        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.SegmentedEditor = SegmentedEditor;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const settle = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
          await new Promise((resolve) => setTimeout(resolve, 0));
        };

        const definition = {
          id: "segmented-memory",
          editor: "segmented",
          fields: [
            { name: "action", type: "enum" },
            { name: "segments", type: "integer", minimum: 2, maximum: 250 },
            { name: "index", type: "integer", minimum: 1 },
          ],
        };
        let supported = true;
        let available = true;
        let contextKey = "simulate||keysight-dsox2004a";
        const catalog = {
          supported: () => supported,
          fieldsFor: (command) => command.fields,
        };
        const submitted = [];
        const responses = [];
        const hooks = {
          executeCommand: async (command, parameters, options) => {
            submitted.push({ command, parameters, intent: options?.intent });
            return responses.shift();
          },
          headerActions: new FakeNode(),
          isExecutionBusy: () => false,
          isAvailable: () => available,
          contextKey: () => contextKey,
          selectedCommand: () => definition,
        };
        const editor = new globalThis.SegmentedEditor(new FakeNode(), catalog, hooks);
'''


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js is required for frontend behavior checks",
)
def test_segmented_editor_refresh_renders_realtime_and_segmented_state() -> None:
    script = textwrap.dedent(EDITOR_HARNESS) + textwrap.dedent(
        r'''
        editor.schedulePresentation();
        await settle();
        assert.deepEqual(submitted, []);
        assert.equal(editor.countInput.min, "2");
        assert.equal(editor.countInput.max, "250");

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "realtime", configured_segments: null, acquired_segments: null,
          } } },
        });
        editor.refreshButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted, [{
          command: "segmented-memory",
          parameters: { action: "query" },
          intent: "readback",
        }]);
        assert.equal(editor.statusText.textContent, "status.inactive");
        assert.equal(editor.modeOutput.output.textContent, "Realtime");
        assert.equal(editor.configuredRow.output.hidden, true);
        assert.equal(editor.acquiredRow.output.hidden, true);
        assert.equal(editor.exitButton.hidden, true);

        editor.countInput.value = "80";
        editor.countInput.dispatch("input");
        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 63,
          } } },
        });
        editor.refreshButton.dispatch("click");
        await settle();
        assert.equal(editor.statusText.textContent, "status.active");
        assert.equal(editor.modeOutput.output.textContent, "Segmented");
        assert.equal(editor.configuredRow.output.textContent, "100");
        assert.equal(editor.acquiredRow.output.textContent, "63");
        assert.equal(editor.configuredRow.output.hidden, false);
        assert.equal(editor.exitButton.hidden, false);
        assert.equal(editor.countInput.value, "80");
        ''',
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js is required for frontend behavior checks",
)
def test_segmented_editor_rerender_preserves_segment_count() -> None:
    script = textwrap.dedent(EDITOR_HARNESS) + textwrap.dedent(
        r'''
        editor.schedulePresentation();
        await settle();

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 63,
          } } },
        });
        editor.refreshButton.dispatch("click");
        await settle();
        assert.equal(editor.countInput.value, "100");
        assert.equal(editor.dirty, false);
        assert.equal(editor.configuredRow.output.textContent, "100");

        editor.rerender();
        await settle();
        assert.equal(editor.countInput.value, "100");
        assert.equal(editor.configuredRow.output.textContent, "100");

        editor.countInput.value = "80";
        editor.countInput.dispatch("input");
        assert.equal(editor.dirty, true);
        editor.rerender();
        await settle();
        assert.equal(editor.countInput.value, "80");
        ''',
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js is required for frontend behavior checks",
)
def test_segmented_editor_browses_acquired_segments_from_readback() -> None:
    script = textwrap.dedent(EDITOR_HARNESS) + textwrap.dedent(
        r'''
        editor.schedulePresentation();
        await settle();

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 63,
            selected_segment: 37, time_tag_s: 0.00128472,
          } } },
        });
        editor.refreshButton.dispatch("click");
        await settle();
        assert.equal(editor.segmentBrowser.hidden, false);
        assert.equal(editor.segmentInput.value, "37");
        assert.equal(editor.segmentInput.min, "1");
        assert.equal(editor.segmentInput.max, "63");
        assert.equal(editor.segmentTotal.textContent, "/ 63");
        assert.equal(editor.timeTagOutput.textContent, "0.00128472 s");
        assert.equal(editor.previousButton.disabled, false);
        assert.equal(editor.nextButton.disabled, false);

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 63,
            selected_segment: 36, time_tag_s: 0.0012,
          } } },
        });
        editor.previousButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.at(-1), {
          command: "segmented-memory",
          parameters: { action: "select", index: 36 },
          intent: "apply",
        });
        assert.equal(editor.segmentInput.value, "36");
        assert.equal(editor.timeTagOutput.textContent, "0.0012 s");

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 63,
            selected_segment: 37, time_tag_s: 0.00128472,
          } } },
        });
        editor.nextButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.at(-1).parameters, { action: "select", index: 37 });

        const countBeforeInput = submitted.length;
        editor.segmentInput.value = "20";
        editor.segmentInput.dispatch("input");
        await settle();
        assert.equal(submitted.length, countBeforeInput);

        const countBeforeRerender = submitted.length;
        editor.schedulePresentation();
        editor.rerender();
        await settle();
        assert.equal(editor.segmentInput.value, "20");
        assert.equal(submitted.length, countBeforeRerender);

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 63,
            selected_segment: 20, time_tag_s: 0.00075,
          } } },
        });
        editor.selectButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted.at(-1).parameters, { action: "select", index: 20 });
        assert.equal(editor.segmentInput.value, "20");
        assert.equal(editor.timeTagOutput.textContent, "0.00075 s");

        editor.acceptJob({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 63,
            selected_segment: 1, time_tag_s: 0,
          } } },
        }, true);
        editor.applyBusyState();
        assert.equal(editor.previousButton.disabled, true);
        assert.equal(editor.nextButton.disabled, false);

        editor.acceptJob({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 63,
            selected_segment: 63, time_tag_s: 0.062,
          } } },
        }, true);
        editor.applyBusyState();
        assert.equal(editor.previousButton.disabled, false);
        assert.equal(editor.nextButton.disabled, true);

        editor.acceptJob({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 0,
            selected_segment: null, time_tag_s: null,
          } } },
        }, true);
        editor.applyBusyState();
        assert.equal(editor.segmentBrowser.hidden, true);
        const countWithoutSegments = submitted.length;
        editor.previousButton.dispatch("click");
        editor.nextButton.dispatch("click");
        editor.selectButton.dispatch("click");
        await settle();
        assert.equal(submitted.length, countWithoutSegments);

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 63,
            selected_segment: 37, time_tag_s: 0.00128472,
          } } },
        });
        editor.refreshButton.dispatch("click");
        await settle();
        assert.equal(editor.segmentInput.value, "37");
        editor.segmentInput.value = "20";
        editor.segmentInput.dispatch("input");
        contextKey = "simulate||keysight-dsox3024a";
        const countBeforeContextRerender = submitted.length;
        editor.schedulePresentation();
        editor.rerender();
        await settle();
        assert.equal(editor.segmentInput.value, "");
        assert.equal(submitted.length, countBeforeContextRerender);
        ''',
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_segmented_memory_select_validation_and_execution_use_core(tmp_path: Path) -> None:
    request = validate_job_request({
        "command": "segmented-memory",
        "mode": "simulate",
        "model_id": "keysight-dsox4024a",
        "parameters": {"action": "select", "index": 20},
    })
    assert request["parameters"] == {"action": "select", "index": 20}

    with pytest.raises(WebUIRequestError, match="index must be an integer"):
        validate_job_request({
            "command": "segmented-memory",
            "mode": "simulate",
            "model_id": "keysight-dsox4024a",
            "parameters": {"action": "select", "index": "20"},
        })

    calls: list[tuple[str, int | None]] = []

    class FakeScope:
        def select_segmented_memory(self, index: int) -> None:
            calls.append(("select", index))

        def query_segmented_memory(self) -> dict[str, object]:
            calls.append(("query", None))
            return {
                "mode": "segmented",
                "configured_segments": 100,
                "acquired_segments": 63,
                "selected_segment": 20,
                "time_tag_s": 0.00075,
            }

    result = command_execution_module._execute_trigger_search_serial_segmented_workflow_command(
        FakeScope(),
        "segmented-memory",
        "SIM::INSTR",
        request["parameters"],
        tmp_path,
    )

    assert calls == [("select", 20), ("query", None)]
    assert result["result"]["segmented"]["selected_segment"] == 20
    assert result["result"]["segmented"]["time_tag_s"] == 0.00075


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js is required for frontend behavior checks",
)
def test_segmented_editor_enter_exit_and_capability_gating() -> None:
    script = textwrap.dedent(EDITOR_HARNESS) + textwrap.dedent(
        r'''
        editor.schedulePresentation();
        await settle();
        editor.countInput.value = "100";
        editor.countInput.dispatch("input");
        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 0,
          } } },
        });
        editor.enterButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted[0], {
          command: "segmented-memory",
          parameters: { action: "enable", segments: 100 },
          intent: "apply",
        });
        assert.equal(editor.statusText.textContent, "status.active");
        assert.equal(editor.countInput.value, "100");

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "realtime", configured_segments: null, acquired_segments: null,
          } } },
        });
        editor.exitButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted[1], {
          command: "segmented-memory",
          parameters: { action: "disable" },
          intent: "apply",
        });
        assert.equal(editor.statusText.textContent, "status.inactive");
        assert.equal(editor.exitButton.hidden, true);

        supported = false;
        available = false;
        contextKey = "simulate||unsupported-model";
        editor.schedulePresentation();
        await settle();
        assert.equal(editor.unavailableNote.hidden, false);
        assert.equal(editor.readouts.hidden, true);
        assert.equal(editor.segmentBrowser.hidden, true);
        assert.equal(editor.segmentInput.value, "");
        assert.equal(editor.timeTagOutput.textContent, "");
        assert.equal(editor.refreshButton.disabled, true);
        editor.refreshButton.dispatch("click");
        editor.enterButton.dispatch("click");
        editor.exitButton.dispatch("click");
        await settle();
        assert.equal(submitted.length, 2);
        ''',
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
