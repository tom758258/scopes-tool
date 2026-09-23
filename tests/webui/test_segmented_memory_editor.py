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
    capture_definition = next(
        entry for entry in COMMANDS if entry["id"] == "segmented-capture"
    )
    projected = next(
        entry for entry in command_catalog() if entry["id"] == "segmented-memory"
    )

    assert definition["editor"] == "segmented"
    assert capture_definition["editor"] == "segmented"
    assert capture_definition.get("browser_hidden") is not True
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
    assert {field["name"]: field.get("help_key") for field in definition["fields"]} == {
        "action": "segmented-memory.action",
        "segments": "segmented-memory.segments",
        "index": "segmented-memory.index",
    }
    assert {
        field["name"]: field.get("help_key") for field in capture_definition["fields"]
    } == {
        "channel": "capture.channel",
        "segments": "segmented-capture.segments",
        "points": "capture.points",
        "format": "capture.format",
        "timeout_ms": "segmented-capture.timeout_ms",
        "poll_interval_ms": "segmented-capture.poll_interval_ms",
    }


def test_app_routes_segmented_editor_and_localizes_its_controls() -> None:
    app = read_static("app.js")
    editor_source = read_static("segmented-editor.js")
    html = read_static("index.html")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert 'import { SegmentedEditor } from "/static/segmented-editor.js";' in app
    assert 'segmented: () => segmentedEditor,' in app
    assert 'id="segmented-editor" class="segmented-editor" hidden' in html
    assert 'elements.segmentedEditor.hidden = editorKind !== "segmented";' in app
    assert '"segmented-memory": ["segmented-memory"]' not in app
    assert '"segmented-memory", "segmented-capture"' not in app
    assert app.count('"search", "segmented"].includes(editorKind)') == 2
    assert "segmentedMemorySelected" in app
    assert "segmentedCaptureSelected" in app
    assert (
        "catalog?.selected()?.id === \"segmented-memory\""
        in app
    )
    assert (
        "catalog?.selected()?.id === \"segmented-capture\""
        in app
    )
    assert "segmentedEditor.captureButton.hidden = !segmentedCaptureSelected" in app
    assert "this.hooks.headerActions.append(this.captureButton)" in editor_source
    assert '"segmented.editor.enter": "Enter Segmented"' in english
    assert '"segmented.editor.exit": "Exit Segmented"' in english
    assert '"segmented.editor.applySegments": "Apply Count"' in english
    assert '"segmented.editor.applySegments": "套用分段數"' in chinese
    assert '"segmented.editor.targetSegments": "Target segments"' in english
    assert '"segmented.editor.targetSegments": "目標分段數"' in chinese
    assert '"segmented.editor.captureTitle": "Start segmented capture"' in english
    assert '"segmented.editor.captureTitle": "開始分段擷取"' in chinese
    assert '"segmented.editor.capture": "Start capture"' in english
    assert '"segmented.editor.capture": "開始擷取"' in chinese
    assert "does not download previously acquired segments" in english
    assert "不是下載先前已擷取的分段" in chinese
    assert "segmented.editor.applyEnter" not in english
    assert "segmented.editor.applyEnter" not in chinese
    assert "applyEnter" not in editor_source
    for key in (
        "help.segmented-memory.action",
        "help.segmented-memory.segments",
        "help.segmented-memory.index",
        "help.segmented-capture.segments",
        "help.segmented-capture.timeout_ms",
        "help.segmented-capture.poll_interval_ms",
        "segmented.editor.stateHelp",
        "segmented.capture.notReady",
        "segmented.capture.planningSegments",
    ):
        assert f'"{key}"' in english
        assert f'"{key}"' in chinese
    assert "target segment count above" not in english
    assert "finite segmented capture below" not in english
    assert "capture reapplies" not in english.lower()
    assert "下方有限分段擷取" not in chinese
    assert "共用的目標分段數" not in chinese
    for key in (
        "segmented.editor.title",
        "segmented.editor.targetSegments",
        "segmented.editor.captureTitle",
        "segmented.editor.captureDescription",
        "segmented.editor.capture",
        "segmented.editor.mode",
        "segmented.editor.configuredSegments",
        "segmented.editor.acquiredSegments",
        "segmented.editor.segment",
        "segmented.editor.previous",
        "segmented.editor.next",
        "segmented.editor.select",
        "segmented.editor.timeTag",
        "segmented.editor.enter",
        "segmented.editor.applySegments",
        "segmented.editor.exit",
        "segmented.editor.unavailable",
    ):
        assert f'"{key}"' in chinese


def test_segmented_editor_removes_standalone_status_indicator() -> None:
    editor_source = read_static("segmented-editor.js")
    styles = read_static("styles.css")

    assert "state-indicator" not in editor_source
    assert "segmented-editor-status" not in editor_source
    assert ".segmented-editor-status" not in styles
    assert "statusText" not in editor_source
    assert "enterButton" not in editor_source
    assert "exitButton" not in editor_source
    assert "captureChannelInput" not in editor_source
    assert "captureSegmentsInput" not in editor_source
    assert "captureConfiguredOutput" not in editor_source
    assert "captureConfigured" not in editor_source
    assert "this.modeButton" in editor_source
    assert "this.applySegmentsButton" in editor_source
    overview_rule = styles.split(".segmented-editor-overview {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns:" not in overview_rule
    state_section_rule = styles.split(".segmented-editor-state-section {", 1)[1].split("}", 1)[0]
    assert "width: 50%;" in state_section_rule
    divider_rule = styles.split(".segmented-editor-divider {", 1)[1].split("}", 1)[0]
    assert "border-top: 1px solid var(--line);" in divider_rule
    state_rule = styles.split(".segmented-editor-state {", 1)[1].split("}", 1)[0]
    assert "width: 100%;" in state_rule
    assert "width: fit-content;" not in state_rule
    count_row_rule = styles.split(
        ".segmented-editor-actions.segmented-editor-count-row {", 1
    )[1].split("}", 1)[0]
    assert "align-items: end;" in count_row_rule
    overview_count_rule = styles.split(
        ".segmented-editor-overview .segmented-editor-count-row {", 1
    )[1].split("}", 1)[0]
    assert "width: 50%;" in overview_count_rule
    count_help_rule = styles.split(
        ".segmented-editor-count-row > .field-help {", 1
    )[1].split("}", 1)[0]
    assert "flex-basis: 100%;" in count_help_rule
    assert "this.stateSection.append(this.readouts, stateHelp)" in editor_source
    assert "this.overview.append(this.stateSection, this.memoryDivider, countRow)" in editor_source


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
            if (this.disabled) return true;
            return this.validity.valid;
          }
          get validity() {
            const empty = this.value === "";
            const value = Number(this.value);
            return {
              valid: !(this.required && empty && !this.disabled)
                && (empty || (
                  Number.isFinite(value)
                  && (!this.min || value >= Number(this.min))
                  && (!this.max || value <= Number(this.max))
                  && (!this.step || Number.isInteger(value))
                )),
            };
          }
          reportValidity() { this.reported = true; }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.translate = (key) => ({
          "enum.realtime": "Realtime",
          "enum.segmented": "Segmented",
        })[key] || key;
        globalThis.hasTranslation = (key) => key.startsWith("enum.") || key.startsWith("help.");

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
            { name: "action", type: "enum", help_key: "segmented-memory.action" },
            { name: "segments", type: "integer", minimum: 2, maximum: 250, help_key: "segmented-memory.segments" },
            { name: "index", type: "integer", minimum: 1, help_key: "segmented-memory.index" },
          ],
        };
        let supported = true;
        let available = true;
        let contextKey = "simulate||keysight-dsox2004a";
        let selection = definition;
        const catalog = {
          activeMode: "simulate",
          commands: [definition],
          supported: () => supported,
          fieldsFor: (command) => command.fields,
          optionsFor: (field) => field?.options || [],
        };
        const submitted = [];
        const responses = [];
        const hooks = {
          executeCommand: async (command, parameters, options) => {
            submitted.push({
              command,
              parameters,
              intent: options?.intent,
              ...(options?.captureWorkspaceResult === false
                ? { captureWorkspaceResult: false }
                : {}),
            });
            return responses.shift();
          },
          headerActions: new FakeNode(),
          isExecutionBusy: () => false,
          isAvailable: () => available,
          contextKey: () => contextKey,
          selectedCommand: () => selection,
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
        assert.equal(editor.modeButton.hidden, true);
        assert.equal(editor.applySegmentsButton.hidden, true);
        assert.equal(editor.modeOutput.output.textContent, "segmented.editor.unknown");
        assert.equal(editor.container.children[0].children.length, 1);
        assert.equal("status" in editor, false);
        assert.equal("statusText" in editor, false);

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
        assert.equal(editor.modeOutput.output.textContent, "Realtime");
        assert.equal(editor.configuredRow.output.hidden, true);
        assert.equal(editor.acquiredRow.output.hidden, true);
        assert.equal(editor.modeButton.hidden, false);
        assert.equal(editor.modeButton.textContent, "segmented.editor.enter");
        assert.equal(editor.modeButton.className, "primary");
        assert.equal(editor.applySegmentsButton.hidden, true);

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
        assert.equal(editor.modeOutput.output.textContent, "Segmented");
        assert.equal(editor.configuredRow.output.textContent, "100");
        assert.equal(editor.acquiredRow.output.textContent, "63");
        assert.equal(editor.configuredRow.output.hidden, false);
        assert.equal(editor.modeButton.hidden, false);
        assert.equal(editor.modeButton.textContent, "segmented.editor.exit");
        assert.equal(editor.modeButton.className, "secondary");
        assert.equal(editor.applySegmentsButton.hidden, false);
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


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js is required for frontend behavior checks",
)
def test_segmented_editor_runs_finite_capture_with_existing_command() -> None:
    script = textwrap.dedent(EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const captureDefinition = {
          id: "segmented-capture",
          editor: "segmented",
          fields: [
            { name: "channel", type: "integer", minimum: 1, maximum: 4, default: 1, help_key: "capture.channel" },
            { name: "segments", type: "integer", minimum: 2, maximum: 5000, help_key: "segmented-capture.segments" },
            { name: "points", type: "integer", options: [1000, 5000, 10000], default: 1000, help_key: "capture.points" },
            { name: "format", type: "enum", options: ["byte", "word"], default: "byte", help_key: "capture.format" },
          ],
        };
        catalog.commands = [definition, captureDefinition];
        selection = captureDefinition;
        editor.buildDom();
        editor.present();
        await settle();

        // The capture workspace owns only retrieval inputs: no editable
        // segment count in Live/Simulate.
        assert.equal(editor.selectedView(), "capture");
        assert.equal(editor.captureSection.hidden, false);
        assert.equal(editor.readouts.hidden, true);
        assert.equal(editor.countRow.hidden, true);
        assert.equal(editor.segmentBrowser.hidden, true);
        assert.equal(editor.planningRow.hidden, true);
        assert.equal("captureConfiguredOutput" in editor, false);
        assert.equal(editor.captureNote.hidden, true);
        assert.equal(editor.countInput.max, "250");
        assert.equal(editor.planningSegmentsInput.max, "5000");
        assert.equal(editor.captureChannelSelect.tagName, "SELECT");
        assert.deepEqual(
          editor.captureChannelSelect.children.map((option) => option.value),
          ["1", "2", "3", "4"],
        );
        assert.equal(editor.captureChannelSelect.value, "1");
        assert.equal(editor.capturePointsSelect.value, "1000");
        assert.equal(editor.captureFormatSelect.value, "byte");
        assert.deepEqual({
          fieldCount: editor.captureForm.children.length,
          helpClasses: editor.captureForm.children.map((field) => field.children.at(-1).className),
          buttonOutsideGrid: editor.captureButton.parentNode !== editor.captureForm,
          buttonInHeader: editor.captureButton.parentNode === hooks.headerActions,
          localActionRows: editor.captureSection.children.filter(
            (node) => node.className === "segmented-editor-actions",
          ).length,
        }, {
          fieldCount: 3,
          helpClasses: ["field-help", "field-help", "field-help"],
          buttonOutsideGrid: true,
          buttonInHeader: true,
          localActionRows: 0,
        });

        const countBeforeInput = submitted.length;
        editor.captureChannelSelect.value = "2";
        editor.capturePointsSelect.value = "5000";
        editor.captureFormatSelect.value = "word";
        await settle();
        assert.equal(submitted.length, countBeforeInput);

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 63,
          } } },
        });
        responses.push({
          status: "completed",
          result: { result: {
            operation: "segmented-capture",
            final_mode: "segmented",
            configured_segments: 100,
            acquired_segments: 100,
          } },
        });
        editor.captureButton.dispatch("click");
        await settle();
        // Start first queries segmented-memory, then passes that same
        // configured count to the existing segmented-capture command.
        assert.deepEqual(submitted, [
          {
            command: "segmented-memory",
            parameters: { action: "query" },
            intent: "readback",
            captureWorkspaceResult: false,
          },
          {
            command: "segmented-capture",
            parameters: { channel: 2, segments: 100, points: 5000, format: "word" },
            intent: "command",
          },
        ]);
        const submittedCapture = submitted.at(-1);
        assert.equal(typeof submittedCapture.parameters.channel, "number");
        assert.equal(typeof submittedCapture.parameters.segments, "number");
        assert.equal("timeout_ms" in submittedCapture.parameters, false);
        assert.equal("poll_interval_ms" in submittedCapture.parameters, false);
        // Capture never adopts prerequisite/capture results as Memory state.
        assert.equal(editor.state, null);
        assert.equal(editor.captureNote.hidden, true);

        // Not in Segmented mode: block capture with guidance.
        submitted.length = 0;
        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "realtime", configured_segments: null, acquired_segments: null,
          } } },
        });
        editor.captureButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted, [
          {
            command: "segmented-memory",
            parameters: { action: "query" },
            intent: "readback",
            captureWorkspaceResult: false,
          },
        ]);
        assert.equal(editor.captureBlocked, true);
        assert.equal(editor.captureNote.hidden, false);
        assert.equal(editor.captureNote.textContent, "segmented.capture.notReady");
        assert.equal(editor.state, null);

        // Visiting Memory clears stale Capture guidance without performing I/O.
        selection = definition;
        editor.present();
        await settle();
        assert.equal(editor.captureBlocked, false);
        assert.equal(editor.captureNote.hidden, true);

        // A failed prerequisite query does not pretend Memory is misconfigured.
        selection = captureDefinition;
        editor.present();
        editor.state = {
          mode: "segmented",
          configured_segments: 25,
          acquired_segments: 25,
          selected_segment: 1,
          time_tag_s: 0,
        };
        submitted.length = 0;
        responses.push({ status: "failed", error: "boom" });
        editor.captureButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted, [
          {
            command: "segmented-memory",
            parameters: { action: "query" },
            intent: "readback",
            captureWorkspaceResult: false,
          },
        ]);
        assert.equal(editor.state, null);
        assert.equal(editor.captureBlocked, false);
        assert.equal(editor.captureNote.hidden, true);

        editor.setBusy(true);
        assert.equal(editor.captureButton.disabled, true);
        editor.setBusy(false);
        assert.equal(editor.captureButton.disabled, false);

        // Rerender preserves retrieval inputs without re-submitting.
        const countBeforeRerender = submitted.length;
        editor.rerender();
        await settle();
        assert.equal(editor.captureChannelSelect.value, "2");
        assert.equal(editor.capturePointsSelect.value, "5000");
        assert.equal(editor.captureFormatSelect.value, "word");
        assert.equal(submitted.length, countBeforeRerender);
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
def test_segmented_memory_workspace_hides_capture_controls() -> None:
    script = textwrap.dedent(EDITOR_HARNESS) + textwrap.dedent(
        r'''
        // selection defaults to the segmented-memory definition.
        editor.schedulePresentation();
        await settle();

        assert.equal(editor.selectedView(), "memory");
        assert.equal(editor.captureSection.hidden, true);
        assert.equal(editor.readouts.hidden, false);
        assert.equal(editor.countRow.hidden, false);

        // Capture actions are unreachable from the memory workspace.
        const countBefore = submitted.length;
        editor.captureButton.dispatch("click");
        await settle();
        assert.equal(submitted.length, countBefore);
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
def test_segmented_capture_dry_run_uses_planning_input() -> None:
    script = textwrap.dedent(EDITOR_HARNESS) + textwrap.dedent(
        r'''
        const captureDefinition = {
          id: "segmented-capture",
          editor: "segmented",
          fields: [
            { name: "channel", type: "integer", minimum: 1, maximum: 4, default: 1, help_key: "capture.channel" },
            { name: "segments", type: "integer", minimum: 2, maximum: 5000, help_key: "segmented-capture.segments" },
            { name: "points", type: "integer", options: [1000, 5000, 10000], default: 1000, help_key: "capture.points" },
            { name: "format", type: "enum", options: ["byte", "word"], default: "byte", help_key: "capture.format" },
          ],
        };
        catalog.commands = [definition, captureDefinition];
        catalog.activeMode = "dry-run";
        selection = captureDefinition;
        editor.buildDom();
        editor.present();
        await settle();

        assert.equal(editor.selectedView(), "capture");
        assert.equal(editor.isDryRun(), true);
        assert.equal(editor.captureSection.hidden, false);
        assert.equal(editor.planningRow.hidden, false);
        assert.equal("captureConfiguredOutput" in editor, false);
        assert.equal(editor.planningSegmentsInput.min, "2");

        editor.captureChannelSelect.value = "1";
        editor.capturePointsSelect.value = "1000";
        editor.captureFormatSelect.value = "byte";
        editor.planningSegmentsInput.value = "50";
        responses.push({
          status: "completed",
          result: { result: { operation: "segmented-capture" } },
        });
        editor.captureButton.dispatch("click");
        await settle();
        // Dry-run never queries segmented-memory: there is no instrument
        // state, so the planning-only count feeds the capture contract.
        assert.deepEqual(submitted, [
          {
            command: "segmented-capture",
            parameters: { channel: 1, segments: 50, points: 1000, format: "byte" },
            intent: "command",
          },
        ]);

        // Back in simulate the planning input is hidden again.
        catalog.activeMode = "simulate";
        editor.present();
        await settle();
        assert.equal(editor.isDryRun(), false);
        assert.equal(editor.planningRow.hidden, true);
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
def test_segmented_editor_builds_field_help_before_command_selected() -> None:
    script = textwrap.dedent(EDITOR_HARNESS) + textwrap.dedent(
        r'''
        selection = null;
        catalog.commands = [definition];
        const fresh = new globalThis.SegmentedEditor(new FakeNode(), catalog, {
          ...hooks,
          selectedCommand: () => selection,
        });
        await settle();

        const countField = fresh.countInput.parentNode;
        assert.equal(countField.tagName, "LABEL");
        assert.deepEqual(
          countField.children.map((node) => node.tagName),
          ["SPAN", "INPUT"],
        );
        const countRow = countField.parentNode;
        assert.equal(countRow.className, "segmented-editor-actions segmented-editor-count-row");
        assert.equal(fresh.applySegmentsButton.parentNode, countRow);
        const countHelp = countRow.children.find((node) => node.tagName === "SMALL");
        assert.ok(countHelp);
        assert.equal(countHelp.className, "field-help");
        assert.equal(countHelp.textContent, "help.segmented-memory.segments");
        const indexHelp = fresh.segmentBrowser.children.find((node) => node.tagName === "SMALL");
        assert.ok(indexHelp);
        assert.equal(indexHelp.className, "field-help");
        assert.equal(indexHelp.textContent, "help.segmented-memory.index");
        assert.ok(fresh.stateHelp);

        selection = definition;
        fresh.present();
        await settle();
        assert.equal(fresh.countInput.min, "2");
        assert.equal(fresh.countInput.max, "250");
        assert.ok(countRow.children.includes(countHelp));
        assert.equal(countHelp.textContent, "help.segmented-memory.segments");
        assert.ok(fresh.segmentBrowser.children.includes(indexHelp));
        assert.equal(indexHelp.textContent, "help.segmented-memory.index");
        assert.equal(countField.hidden, false);
        ''',
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js is required for frontend behavior checks",
)
def test_segmented_editor_state_help_visibility() -> None:
    script = textwrap.dedent(EDITOR_HARNESS) + textwrap.dedent(
        r'''
        editor.schedulePresentation();
        await settle();
        assert.ok(editor.stateHelp);
        assert.equal(editor.stateHelp.hidden, true);

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "realtime", configured_segments: null, acquired_segments: null,
          } } },
        });
        editor.refreshButton.dispatch("click");
        await settle();
        assert.equal(editor.stateHelp.hidden, true);

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 63,
          } } },
        });
        editor.refreshButton.dispatch("click");
        await settle();
        assert.equal(editor.stateHelp.hidden, false);

        const countBeforePresent = submitted.length;
        supported = false;
        available = false;
        contextKey = "simulate||unsupported-model";
        editor.schedulePresentation();
        await settle();
        assert.equal(editor.stateHelp.hidden, true);
        assert.equal(submitted.length, countBeforePresent);
        ''',
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        encoding="utf-8",
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
        assert.equal(editor.modeButton.hidden, true);
        assert.equal(editor.applySegmentsButton.hidden, true);
        assert.equal(editor.modeOutput.output.textContent, "segmented.editor.unknown");

        editor.modeButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted, []);

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "realtime", configured_segments: null, acquired_segments: null,
          } } },
        });
        editor.refreshButton.dispatch("click");
        await settle();
        assert.equal(editor.modeButton.hidden, false);
        assert.equal(editor.modeButton.textContent, "segmented.editor.enter");
        assert.equal(editor.modeButton.className, "primary");
        assert.equal(editor.applySegmentsButton.hidden, true);
        assert.equal(editor.modeOutput.output.textContent, "Realtime");

        editor.countInput.value = "999";
        editor.modeButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted, [{
          command: "segmented-memory",
          parameters: { action: "query" },
          intent: "readback",
        }]);
        assert.equal(editor.countInput.reported, true);

        editor.countInput.value = "100";
        editor.countInput.dispatch("input");
        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 100, acquired_segments: 0,
          } } },
        });
        editor.modeButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted[1], {
          command: "segmented-memory",
          parameters: { action: "enable", segments: 100 },
          intent: "apply",
        });
        assert.equal(editor.modeButton.hidden, false);
        assert.equal(editor.modeButton.textContent, "segmented.editor.exit");
        assert.equal(editor.modeButton.className, "secondary");
        assert.equal(editor.applySegmentsButton.hidden, false);
        assert.equal(editor.countRow.hidden, false);
        assert.equal(editor.modeOutput.output.textContent, "Segmented");
        assert.equal(editor.countInput.value, "100");
        assert.equal(editor.applySegmentsButton.disabled, true);
        assert.equal(editor.applySegmentsButton.className, "secondary");

        editor.countInput.value = "50";
        editor.countInput.dispatch("input");
        assert.equal(editor.applySegmentsButton.disabled, false);
        assert.equal(editor.applySegmentsButton.className, "primary");

        editor.countInput.value = "999";
        editor.countInput.dispatch("input");
        assert.equal(editor.applySegmentsButton.disabled, true);
        assert.equal(editor.applySegmentsButton.className, "secondary");

        editor.setBusy(true);
        assert.equal(editor.countInput.disabled, true);
        assert.equal(editor.applySegmentsButton.disabled, true);
        assert.equal(editor.applySegmentsButton.className, "secondary");
        editor.setBusy(false);
        assert.equal(editor.countInput.disabled, false);
        assert.equal(editor.applySegmentsButton.disabled, true);
        assert.equal(editor.applySegmentsButton.className, "secondary");

        editor.countInput.value = "";
        editor.countInput.dispatch("input");
        assert.equal(editor.countInput.validity.valid, false);
        assert.equal(editor.applySegmentsButton.disabled, true);
        assert.equal(editor.applySegmentsButton.className, "secondary");

        editor.setBusy(true);
        assert.equal(editor.countInput.disabled, true);
        assert.equal(editor.countInput.validity.valid, true);
        assert.equal(editor.applySegmentsButton.disabled, true);
        assert.equal(editor.applySegmentsButton.className, "secondary");
        editor.setBusy(false);
        assert.equal(editor.countInput.disabled, false);
        assert.equal(editor.countInput.validity.valid, false);
        assert.equal(editor.applySegmentsButton.disabled, true);
        assert.equal(editor.applySegmentsButton.className, "secondary");

        editor.countInput.value = "50";
        editor.countInput.dispatch("input");
        assert.equal(editor.applySegmentsButton.disabled, false);
        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "segmented", configured_segments: 50, acquired_segments: 0,
          } } },
        });
        editor.applySegmentsButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted[2], {
          command: "segmented-memory",
          parameters: { action: "enable", segments: 50 },
          intent: "apply",
        });
        assert.equal(editor.modeButton.textContent, "segmented.editor.exit");
        assert.equal(editor.applySegmentsButton.disabled, true);
        assert.equal(editor.applySegmentsButton.className, "secondary");

        responses.push({
          status: "completed",
          result: { result: { segmented: {
            mode: "realtime", configured_segments: null, acquired_segments: null,
          } } },
        });
        editor.modeButton.dispatch("click");
        await settle();
        assert.deepEqual(submitted[3], {
          command: "segmented-memory",
          parameters: { action: "disable" },
          intent: "apply",
        });
        assert.equal(editor.modeButton.textContent, "segmented.editor.enter");
        assert.equal(editor.modeButton.className, "primary");
        assert.equal(editor.applySegmentsButton.hidden, true);

        supported = false;
        available = false;
        contextKey = "simulate||unsupported-model";
        editor.schedulePresentation();
        await settle();
        assert.equal(editor.modeButton.hidden, true);
        assert.equal(editor.applySegmentsButton.hidden, true);
        assert.equal(editor.countRow.hidden, true);
        assert.equal(editor.unavailableNote.hidden, false);
        assert.equal(editor.readouts.hidden, true);
        assert.equal(editor.segmentBrowser.hidden, true);
        assert.equal(editor.segmentInput.value, "");
        assert.equal(editor.timeTagOutput.textContent, "");
        assert.equal(editor.refreshButton.disabled, true);
        editor.refreshButton.dispatch("click");
        editor.modeButton.dispatch("click");
        editor.applySegmentsButton.dispatch("click");
        await settle();
        assert.equal(submitted.length, 4);
        ''',
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(EDITOR_SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
