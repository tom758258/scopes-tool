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
  globalThis.translate = (key, values = {}) => Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{{${name}}}`, String(value)), key,
  );
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
      measure: [{ name: "item", type: "enum", options: ["vpp"], default: "vpp", required: true }, { name: "channel", type: "integer", options: [1, 2, 3, 4], default: 1 }],
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
