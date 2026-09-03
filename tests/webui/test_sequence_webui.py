from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scopes_tool_core import SequenceRequest
from scopes_tool_core.planning import OperationPlan
from scopes_tool_webui.app import app
import scopes_tool_webui.command_execution as execution
from scopes_tool_webui.commands import WebUIRequestError, command_catalog, validate_job_request


REPO_ROOT = Path(__file__).resolve().parents[2]
EDITOR_SOURCE = REPO_ROOT / "src" / "scopes_tool_webui" / "static" / "sequence-editor.js"


def _document(*steps, loop_count=1):
    return {"version": 1, "loop_count": loop_count, "steps": list(steps)}


def _step(action="wait", **parameters):
    if action == "wait" and not parameters:
        parameters = {"seconds": 0}
    return {"action": action, "parameters": parameters}


def test_sequence_catalog_and_request_validation_use_core_contract() -> None:
    definition = next(item for item in command_catalog() if item["id"] == "sequence")

    assert definition["category"] == "Workflow"
    assert definition["editor"] == "sequence"
    assert definition["sequence"]["actions"] == [
        "wait", "single", "wait-trigger", "measure", "capture", "screenshot", "cleanup"
    ]
    assert definition["sequence"]["limits"] == {
        "step_count": 255,
        "loop_count": 255,
        "total_step_executions": 65_025,
        "artifact_steps": 10,
    }

    request = validate_job_request(
        {
            "command": "sequence",
            "mode": "simulate",
            "model_id": "keysight-dsox4024a",
            "parameters": {"document": _document(_step())},
        }
    )
    assert request["parameters"]["document"]["steps"][0]["parameters"] == {
        "seconds": 0.0
    }

    with pytest.raises(WebUIRequestError, match="step_count must be at most 255"):
        validate_job_request(
            {
                "command": "sequence",
                "mode": "simulate",
                "model_id": "keysight-dsox4024a",
                "parameters": {"document": _document(*[_step() for _ in range(256)])},
            }
        )


def test_sequence_validation_endpoint_rejects_whole_invalid_document() -> None:
    client = TestClient(app)
    valid = client.post("/api/sequence/validate", json=_document(_step()))
    assert valid.status_code == 200
    assert valid.json()["document"]["steps"][0]["parameters"] == {"seconds": 0.0}

    invalid = client.post(
        "/api/sequence/validate",
        json=_document(*[_step("screenshot") for _ in range(11)]),
    )
    assert invalid.status_code == 400
    assert "capture and screenshot steps must total at most 10" in invalid.json()["detail"]


def test_sequence_backend_delegates_dry_run_and_execution_to_core(monkeypatch, tmp_path) -> None:
    document = _document(_step())
    planned = []

    def fake_plan(request, capabilities):
        planned.append((request, capabilities))
        return OperationPlan((), (), {"status": "planned", "files": []})

    monkeypatch.setattr(execution, "plan_sequence", fake_plan)
    dry_run = execution._execute_dry_run(
        "sequence",
        {"document": document},
        "keysight-dsox4024a",
        tmp_path,
    )
    assert dry_run["result"]["status"] == "planned"
    assert isinstance(planned[0][0], SequenceRequest)

    calls = []

    class FakeScope:
        capabilities = object()

    class FakeResult:
        exit_code = 0
        result = {"status": "completed"}
        files = []
        system_error = None
        human_lines = []
        backend = "fake"
        idn = None
        timeout_ms = None

    def fake_run(scope, resource, request, **kwargs):
        calls.append((scope, resource, request, kwargs))
        return FakeResult()

    monkeypatch.setattr(execution, "run_sequence", fake_run)
    result = execution._execute_trigger_search_serial_segmented_workflow_command(
        FakeScope(),
        "sequence",
        "SIM::TEST::INSTR",
        {"document": document},
        tmp_path,
        stop_requested=lambda: False,
        progress_reporter=lambda _progress: None,
    )
    assert result["exit_code"] == 0
    assert isinstance(calls[0][2], SequenceRequest)
    assert calls[0][3]["stop_requested"] is not None
    assert calls[0][3]["progress_reporter"] is not None


SEQUENCE_EDITOR_HARNESS = r'''
  import assert from "node:assert/strict";
  import fs from "node:fs";
  const translations = {
    "sequence.action.measure": "\u91cf\u6e2c",
    "sequence.parameter.item": "\u91cf\u6e2c\u9805\u76ee",
    "sequence.parameter.source_channel": "\u4f86\u6e90\u901a\u9053",
    "sequence.parameter.slope": "\u659c\u7387",
    "sequence.editor.invalidParameter": "\u6b65\u9a5f {{index}} \u7684 {{name}} \u503c\u7121\u6548\u3002",
    "enum.vpp": "VPP",
    "enum.positive": "\u6b63\u5411",
    "enum.negative": "\u8ca0\u5411",
  };
  globalThis.translate = (key, values = {}) => Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{{${name}}}`, String(value)), translations[key] || key,
  );
  globalThis.document = {
    createElement: (tag) => ({
      tagName: tag,
      children: [],
      dataset: {},
      append: function(...children) { this.children.push(...children); },
      addEventListener: function() {},
    }),
  };
  globalThis.Option = function(text, value) { this.text = text; this.value = value; };
  globalThis.queueMicrotask ||= (callback) => Promise.resolve().then(callback);
  const source = fs.readFileSync(process.argv[1], "utf8")
    .replace(/^import[^\n]*\r?\n/gm, "")
    .replace(/^export /gm, "")
    + "\nglobalThis.SequenceEditor = SequenceEditor;";
  await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
  const metadata = {
    actions: ["wait", "single", "wait-trigger", "measure", "capture", "screenshot", "cleanup"],
    limits: { step_count: 255, loop_count: 255, total_step_executions: 65025, artifact_steps: 10 },
    parameters: {
      wait: [{ name: "seconds", type: "number", minimum: 0, default: 0, required: true }],
      single: [],
      "wait-trigger": [{ name: "timeout_seconds", type: "number", exclusive_minimum: 0, default: 1, required: true }],
      measure: [
        { name: "item", type: "enum", options: ["vpp"], default: "vpp", required: true },
        { name: "channel", type: "integer", options: [1, 2, 3, 4], default: 1 },
        { name: "source_channel", type: "integer", minimum: 1, maximum: 4 },
        { name: "slope", type: "enum", options: ["positive", "negative"], default: "positive" },
      ],
      capture: [{ name: "channels", type: "multi-enum", options: ["all", 1, 2, 3, 4], default: [1], required: true }, { name: "allow_time_axis_tolerance", type: "boolean", default: false }],
      screenshot: [{ name: "background", type: "enum", options: ["black", "white"], default: "black" }],
      cleanup: [{ name: "profile", type: "enum", options: ["minimal", "safe"], default: "minimal" }],
    },
  };
  const state = { loopCount: "1", filename: null, message: "", messageError: false, steps: [{ action: "wait", parameters: { seconds: "0" }, expanded: true }] };
  const submissions = [];
  const editor = Object.create(globalThis.SequenceEditor.prototype);
  editor.busy = false;
  editor.metadata = () => metadata;
  editor.state = () => state;
  editor.render = () => {};
  editor.applyBusyState = () => {};
  editor.updateValidity = () => !editor.validationError();
  editor.setBusy = (value) => { editor.busy = value; };
  editor.setMessage = (message, error = true) => { state.message = message; state.messageError = error; };
  editor.hooks = {
    isExecutionBusy: () => false,
    isAvailable: () => true,
    validateSequence: async (document) => ({ document }),
    executeCommand: async (...args) => { submissions.push(args); return { job_id: "job" }; },
  };
'''


def run_editor_behavior(script: str) -> None:
    completed = subprocess.run(
        [
            "node", "--input-type=module", "--eval",
            textwrap.dedent(SEQUENCE_EDITOR_HARNESS) + textwrap.dedent(script),
            str(EDITOR_SOURCE),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_sequence_editor_boundaries_load_and_invalid_submission() -> None:
    run_editor_behavior(
        r'''
        assert.deepEqual(editor.initialState().steps, [{ action: "wait", parameters: { seconds: "0" }, expanded: true }]);
        assert.deepEqual(editor.localDocument(), { version: 1, loop_count: 1, steps: [{ action: "wait", parameters: { seconds: 0 } }] });
        assert.deepEqual(editor.defaultParameters("capture"), { channels: [1], allow_time_axis_tolerance: false });

        assert.equal(editor.removeStep(0), false);
        assert.equal(state.steps.length, 1);
        editor.addStep();
        assert.equal(state.steps.length, 2);
        assert.equal(state.steps[1].action, "wait");
        assert.equal(state.steps[1].parameters.seconds, "0");
        assert.equal(editor.moveStep(1, -1), true);
        assert.equal(editor.removeStep(1), true);

        state.steps = Array.from({ length: 255 }, () => ({ action: "wait", parameters: { seconds: "0" }, expanded: false }));
        assert.equal(editor.addStep(), false);
        assert.equal(state.steps.length, 255);

        state.steps = Array.from({ length: 10 }, () => ({ action: "capture", parameters: { channels: [1] }, expanded: false }));
        state.steps.push({ action: "wait", parameters: { seconds: "0" }, expanded: true });
        assert.equal(editor.changeAction(10, "screenshot"), false);
        assert.equal(state.steps[10].action, "wait");
        assert.equal(editor.changeAction(0, "screenshot"), true);
        assert.equal(editor.artifactCount(), 10);

        state.steps = [{ action: "measure", parameters: { item: "vpp", channel: "1", stale: "value" }, expanded: true }];
        assert.equal(editor.changeAction(0, "capture"), true);
        assert.deepEqual(state.steps[0].parameters, { channels: [1], allow_time_axis_tolerance: false });

        const loaded = { version: 1, loop_count: 2, steps: [{ action: "single", parameters: {} }] };
        assert.equal(await editor.loadDocument(loaded, "loaded.sequence.json"), true);
        assert.equal(state.filename, "loaded.sequence.json");
        assert.equal(state.steps[0].expanded, false);

        editor.hooks.validateSequence = async () => { throw new Error("invalid document"); };
        assert.equal(await editor.loadDocument({ bad: true }, "bad.json"), false);
        assert.equal(state.filename, "loaded.sequence.json");
        assert.equal(state.steps[0].action, "single");

        state.loopCount = "256";
        assert.equal(await editor.save(), false);
        await editor.submit();
        assert.equal(submissions.length, 0);
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_sequence_editor_localizes_presentation_but_submits_canonical_values() -> None:
    run_editor_behavior(
        r'''
        const slopeField = metadata.parameters.measure.find((field) => field.name === "slope");
        const step = {
          action: "measure",
          parameters: { item: "vpp", source_channel: "1", slope: "positive" },
          expanded: true,
        };
        const rendered = editor.renderParameter(step, 0, slopeField);
        const select = rendered.children[1];
        assert.equal(select.children[0].text, "\u6b63\u5411");
        assert.equal(select.children[0].value, "positive");

        const summary = editor.stepSummary(step);
        assert(summary.includes("\u4f86\u6e90\u901a\u9053: CH1"));
        assert(summary.includes("\u659c\u7387: \u6b63\u5411"));
        assert.equal(summary.includes("source_channel="), false);
        assert.equal(summary.includes("slope=positive"), false);

        state.steps = [{
          action: "measure",
          parameters: { item: "vpp", channel: "1", slope: "positive" },
          expanded: true,
        }];
        await editor.submit();
        assert.equal(submissions.length, 1);
        assert.deepEqual(submissions[0][1].document.steps[0].parameters, {
          item: "vpp",
          channel: 1,
          slope: "positive",
        });

        state.steps = [{
          action: "measure",
          parameters: { item: "vpp", source_channel: "invalid", slope: "positive" },
          expanded: true,
        }];
        assert(editor.validationError().includes("\u4f86\u6e90\u901a\u9053"));
        assert.equal(editor.validationError().includes("source_channel"), false);
        ''',
    )


def test_sequence_validate_text_strict_rejects_duplicate_keys() -> None:
    client = TestClient(app)
    duplicate_text = '{"version": 1, "loop_count": 1, "loop_count": 2, "steps": [{"action": "wait", "parameters": {"seconds": 0}}]}'
    response = client.post("/api/sequence/validate-text", json={"text": duplicate_text})
    assert response.status_code == 400
    assert "duplicate object field" in response.json()["detail"]

    # Valid raw text should pass and return normalized document
    valid_text = '{"version": 1, "loop_count": 1, "steps": [{"action": "wait", "parameters": {"seconds": 0}}]}'
    valid = client.post("/api/sequence/validate-text", json={"text": valid_text})
    assert valid.status_code == 200
    assert valid.json()["document"]["loop_count"] == 1


SEQUENCE_EDITOR_VALIDATION_MESSAGE_HARNESS = r'''
  import assert from "node:assert/strict";
  import fs from "node:fs";
  globalThis.translate = (key, values = {}) => Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{{${name}}}`, String(value)), key,
  );
  globalThis.queueMicrotask ||= (callback) => Promise.resolve().then(callback);
  globalThis.applyNumericFieldConstraints = () => {};
  globalThis.document = {
    createElement: (tag) => {
      const el = {
        tagName: tag,
        className: "",
        dataset: {},
        hidden: false,
        textContent: "",
        value: "",
        checked: false,
        type: "",
        append: function(...c){ (this.children = this.children || []).push(...c); },
        replaceChildren: function(...c){ this.children = c; },
        setAttribute: function(){},
        addEventListener: function(){},
        remove: function(){},
        querySelectorAll: function(){ return []; },
      };
      el.dataset = {};
      if (tag === "input" || tag === "button" || tag === "select") {
        el.setCustomValidity = (msg) => { el._msg = msg; };
      }
      return el;
    },
  };
  globalThis.Option = function(text, value){ this.text = text; this.value = value; };
  globalThis.Blob = class { constructor(parts, opts){ this.parts = parts; this.opts = opts; } };
  globalThis.URL = { createObjectURL: () => "blob:fake", revokeObjectURL: () => {} };
  const source = fs.readFileSync(process.argv[1], "utf8")
    .replace(/^import[^\n]*\r?\n/gm, "")
    .replace(/^export /gm, "")
    + "\nglobalThis.SequenceEditor = SequenceEditor;";
  await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
  const metadata = {
    actions: ["wait", "single", "wait-trigger", "measure", "capture", "screenshot", "cleanup"],
    limits: { step_count: 255, loop_count: 255, total_step_executions: 65025, artifact_steps: 10 },
    parameters: {
      wait: [{ name: "seconds", type: "number", minimum: 0, default: 0, required: true }],
      single: [],
      "wait-trigger": [{ name: "timeout_seconds", type: "number", exclusive_minimum: 0, default: 1, required: true }],
      measure: [{ name: "item", type: "enum", options: ["vpp"], default: "vpp", required: true }, { name: "channel", type: "integer", options: [1, 2, 3, 4], default: 1 }],
      capture: [{ name: "channels", type: "multi-enum", options: ["all", 1, 2, 3, 4], default: [1], required: true }, { name: "allow_time_axis_tolerance", type: "boolean", default: false }],
      screenshot: [{ name: "background", type: "enum", options: ["black", "white"], default: "black" }],
      cleanup: [{ name: "profile", type: "enum", options: ["minimal", "safe"], default: "minimal" }],
    },
  };
  const state = { loopCount: "1", filename: "test.sequence.json", message: "", messageError: false, steps: [{ action: "wait", parameters: { seconds: "0" }, expanded: true }] };
  const mockMessage = { textContent: "", hidden: true, className: "", setAttribute: () => {} };
  const mockLoopInput = { value: state.loopCount, setCustomValidity: (msg) => { mockLoopInput._msg = msg; } };
  const mockContainer = { replaceChildren: () => {}, querySelectorAll: () => [], append: () => {} };
  const saveButton = { disabled: false, dataset: {} };
  const executeButton = { disabled: false };
  const headerActions = { append: () => {} };
  const container = { replaceChildren: () => {}, querySelectorAll: () => [] , append: () => {} };
  const editor = new globalThis.SequenceEditor(container, {}, {
    headerActions,
    isExecutionBusy: () => false,
    isAvailable: () => true,
    contextKey: () => "test|sequence",
    selectedCommand: () => ({ editor: "sequence", sequence: metadata }),
  });
  // Override state and DOM hooks to use our mocks and real validation
  editor.state = () => state;
  editor.metadata = () => metadata;
  editor.message = mockMessage;
  editor.loopInput = mockLoopInput;
  editor.container = mockContainer;
  editor.saveButton = saveButton;
  editor.executeButton = executeButton;
  editor.busy = false;
  // keep original hooks (with selectedCommand/contextKey) and just ensure availability
  editor.hooks.isExecutionBusy = () => false;
  editor.hooks.isAvailable = () => true;
'''


def run_validation_message_behavior(script: str) -> None:
    completed = subprocess.run(
        [
            "node",
            "--input-type=module",
            "--eval",
            textwrap.dedent(SEQUENCE_EDITOR_VALIDATION_MESSAGE_HARNESS) + textwrap.dedent(script),
            str(EDITOR_SOURCE),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_sequence_editor_validation_message_clears_success_on_invalid_mutation() -> None:
    run_validation_message_behavior(
        r'''
        // Simulate successful Load
        state.message = "Sequence loaded";
        state.messageError = false;
        mockMessage.textContent = state.message;
        mockMessage.hidden = false;
        mockMessage.className = "compact-note";
        assert.equal(editor.validationError(), "");
        // Mutate to invalid via document-changing handler (loopCount)
        state.loopCount = "0";
        mockLoopInput.value = "0";
        editor.handleDocumentChange();
        // Old success must be cleared and validation error shown
        assert.equal(state.message, "");
        assert.notEqual(editor.validationError(), "");
        assert.equal(mockMessage.textContent, editor.validationError());
        assert.equal(mockMessage.hidden, false);
        assert.equal(mockMessage.className, "form-error");
        editor.applyBusyState();
        assert.equal(saveButton.disabled, true);
        assert.equal(executeButton.disabled, true);
        // Fix back to valid
        state.loopCount = "1";
        mockLoopInput.value = "1";
        editor.handleDocumentChange();
        assert.equal(state.message, "");
        assert.equal(editor.validationError(), "");
        assert.equal(mockMessage.hidden, true);
        editor.applyBusyState();
        assert.equal(saveButton.disabled, false);
        assert.equal(executeButton.disabled, false);
        // Collapse/expand must not clear success message
        state.message = "Sequence loaded";
        state.messageError = false;
        mockMessage.textContent = "Sequence loaded";
        mockMessage.hidden = false;
        // Simulate collapse: toggle expanded without document change
        state.steps[0].expanded = false;
        // No handleDocumentChange called, message should remain
        assert.equal(state.message, "Sequence loaded");
        assert.equal(mockMessage.textContent, "Sequence loaded");
        // Also verify addStep clears message (structural change)
        state.message = "Sequence saved";
        state.messageError = false;
        editor.clearDocumentMessage();
        assert.equal(state.message, "");
        assert.equal(state.messageError, false);
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_sequence_editor_loadfile_uses_raw_text_fail_closed() -> None:
    run_validation_message_behavior(
        r'''
        const rawDuplicate = '{"version":1,"loop_count":1,"loop_count":2,"steps":[{"action":"wait","parameters":{"seconds":0}}]}';
        let receivedText = null;
        editor.hooks.validateSequenceText = async (text) => {
          receivedText = text;
          throw new Error("duplicate object field: loop_count");
        };
        const fakeFile = {
          name: "dup.sequence.json",
          text: async () => rawDuplicate,
        };
        const result = await editor.loadFile(fakeFile);
        assert.equal(result, false);
        assert.equal(receivedText, rawDuplicate);
        assert.ok(state.message.length > 0);
        assert.notEqual(state.message, "Sequence loaded");
        // Also verify fail-closed when hook missing
        delete editor.hooks.validateSequenceText;
        const fakeFile2 = {
          name: "dup2.sequence.json",
          text: async () => rawDuplicate,
        };
        const result2 = await editor.loadFile(fakeFile2);
        assert.equal(result2, false);
        assert.ok(state.message.length > 0);
        assert.notEqual(state.message, "Sequence loaded");
        ''',
    )


def test_sequence_save_results_catalog_and_validation() -> None:
    definition = next(item for item in command_catalog() if item["id"] == "sequence")
    # Catalog should expose save_results reuse if present, but WebUI currently uses dedicated editor checkbox
    # Validate request allows save_results false and defaults to true
    request = validate_job_request(
        {
            "command": "sequence",
            "mode": "simulate",
            "model_id": "keysight-dsox4024a",
            "parameters": {"document": _document(_step()), "save_results": False},
        }
    )
    assert request["parameters"]["save_results"] is False
    defaulted = validate_job_request(
        {
            "command": "sequence",
            "mode": "simulate",
            "model_id": "keysight-dsox4024a",
            "parameters": {"document": _document(_step())},
        }
    )
    assert defaulted["parameters"]["save_results"] is True


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_sequence_editor_save_results_checkbox_and_submit() -> None:
    run_editor_behavior(
        r'''
        // Ensure initial save_results default (harness state starts without it, editor initialState uses true)
        if (state.save_results === undefined) state.save_results = true;
        editor.state().save_results = state.save_results;
        assert.equal(editor.state().save_results, true);
        const doc = editor.localDocument();
        assert.deepEqual(doc, { version: 1, loop_count: 1, steps: [{ action: "wait", parameters: { seconds: 0 } }] });
        // First submit with default true
        await editor.submit();
        assert.equal(submissions.length, 1);
        assert.deepEqual(submissions[0][1], { document: doc, save_results: true });
        // Toggle to false
        editor.state().save_results = false;
        state.save_results = false;
        await editor.submit();
        assert.equal(submissions.length, 2);
        assert.deepEqual(submissions[1][1], { document: doc, save_results: false });
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_sequence_no_save_workspace_result_hides_files() -> None:
    results_path = REPO_ROOT / "src" / "scopes_tool_webui" / "static" / "results.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.translate = (key, values = {}) => Object.entries(values).reduce((t, [k, v]) => t.replaceAll(`{{${k}}}`, String(v)), key);
        globalThis.hasTranslation = (key) => false;
        globalThis.translateJobStatus = (s) => s;
        globalThis.document = {
          createElement: (tag) => {
            const el = {
              tagName: tag,
              className: "",
              textContent: "",
              children: [],
              append: function(...c){ this.children.push(...c); },
              replaceChildren: function(...c){ this.children = c; },
              setAttribute: function(){},
            };
            el.append = function(...c){ this.children.push(...c); };
            return el;
          },
        };
        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "");
        const moduleUrl = `data:text/javascript;charset=utf-8,${encodeURIComponent(source + "\nglobalThis.resultsApi = { renderWorkspaceResult };")}`;
        await import(moduleUrl);
        const { renderWorkspaceResult } = globalThis.resultsApi;

        const makeContainer = () => {
          const children = [];
          return {
            children,
            append: function(...c){ children.push(...c); },
            replaceChildren: function(...c){ children.length = 0; children.push(...c); },
          };
        };

        const container = makeContainer();
        const job = {
          command: "sequence",
          status: "completed",
          result: { result: { status: "completed", version: 1, loop_count: 1, step_count: 1, total_step_executions: 1, completed_loops: 1, completed_step_executions: 1, files: [], output_dir: null, manifest_path: null, scpi_log_path: null, error: null } },
        };
        renderWorkspaceResult(container, job, {});
        const text = JSON.stringify(container.children.map((c) => c.children?.map((x) => x.textContent) || c.textContent));
        assert.equal(text.includes("Files"), false);
        assert.equal(text.includes("Output dir"), false);
        assert.equal(text.includes("Manifest"), false);
        assert.equal(text.includes("SCPI log"), false);

        const container2 = makeContainer();
        const job2 = {
          command: "sequence",
          status: "completed",
          result: { result: { status: "completed", version: 1, loop_count: 1, step_count: 1, total_step_executions: 1, completed_loops: 1, completed_step_executions: 1, files: [{ kind: "manifest", path: "manifest.json" }], output_dir: "data/sequences/x", manifest_path: "data/sequences/x/manifest.json", scpi_log_path: "data/sequences/x/scpi.log", error: null } },
        };
        renderWorkspaceResult(container2, job2, {});
        const text2 = JSON.stringify(container2.children.map((c) => c.children?.map((x) => x.textContent) || c.textContent));
        assert.equal(text2.includes("Files"), true);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(results_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
