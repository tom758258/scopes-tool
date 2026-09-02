from __future__ import annotations

import shutil
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

from scopes_tool_webui.jobs import Job, JobManager
from scopes_tool_core.workflow import WorkflowProgress


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_JS = REPO_ROOT / "src" / "scopes_tool_webui" / "static" / "results.js"
LOCALE_EN_JS = REPO_ROOT / "src" / "scopes_tool_webui" / "static" / "locale_en.js"
LOCALE_ZH_TW_JS = REPO_ROOT / "src" / "scopes_tool_webui" / "static" / "locale_zh_tw.js"


def test_job_manager_progress_keeps_none_and_fixed_total() -> None:
    manager = JobManager()
    job = Job(
        job_id="test-job",
        command="measure-until",
        mode="simulate",
        resource=None,
        model_id=None,
        pc_output_dir="data",
        parameters={},
        pc_output_root=Path("data"),
    )
    progress_unknown = WorkflowProgress(completed_count=3, total_count=None, elapsed_seconds=1.2)
    manager._set_progress(job, progress_unknown)
    assert job.progress["completed_count"] == 3
    assert job.progress["total_count"] is None
    assert job.progress["elapsed_seconds"] == pytest.approx(1.2)

    progress_known = WorkflowProgress(completed_count=4, total_count=10, elapsed_seconds=3.2)
    manager._set_progress(job, progress_known)
    assert job.progress["completed_count"] == 4
    assert job.progress["total_count"] == 10
    assert job.progress["elapsed_seconds"] == pytest.approx(3.2)


@pytest.mark.parametrize(
    "command",
    [
        "measure-log",
        "measure-until",
        "triggered-measure-loop",
        "capture-batch",
        "capture-until",
        "triggered-capture-series",
        "sequence",
    ],
)
def test_job_manager_progress_reporter_routing_for_workflows(monkeypatch, command: str) -> None:
    manager = JobManager()
    captured: dict[str, object] = {}

    def fake_execute(cmd, **kwargs):
        captured[cmd] = kwargs.get("progress_reporter")
        return {"exit_code": 0, "result": {}, "artifacts": []}

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", fake_execute)
    job = manager.submit(
        {
            "command": command,
            "mode": "simulate",
            "model_id": "keysight-dsox4024a",
            "parameters": {},
            "pc_output_dir": "data",
        }
    )
    for _ in range(100):
        if command in captured:
            break
        time.sleep(0.01)
    else:
        raise AssertionError(f"execute not called for {command}")
    assert captured[command] is not None, f"{command} should have progress_reporter"
    for _ in range(100):
        if manager.get(job.job_id).status in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.01)


def test_job_manager_capture_monitor_has_no_generic_progress_reporter(monkeypatch) -> None:
    manager = JobManager()
    captured: dict[str, object] = {}

    def fake_execute(cmd, **kwargs):
        captured[cmd] = kwargs.get("progress_reporter")
        return {"exit_code": 0, "result": {}, "artifacts": []}

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", fake_execute)
    job = manager.submit(
        {
            "command": "capture-monitor",
            "mode": "simulate",
            "model_id": "keysight-dsox4024a",
            "parameters": {},
            "pc_output_dir": "data",
        }
    )
    for _ in range(100):
        if "capture-monitor" in captured:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("execute not called for capture-monitor")
    assert captured["capture-monitor"] is None
    for _ in range(100):
        if manager.get(job.job_id).status in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.01)


def test_locale_contains_workflow_progress_keys() -> None:
    en = LOCALE_EN_JS.read_text(encoding="utf-8")
    zh = LOCALE_ZH_TW_JS.read_text(encoding="utf-8")
    for key in (
        "results.summary.workflowProgressKnown",
        "results.summary.workflowProgressUnknown",
        "results.progress.rows",
        "results.progress.samples",
        "results.progress.cycles",
        "results.progress.captures",
    ):
        assert f'"{key}":' in en, key
        assert f'"{key}":' in zh, key


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_workflow_result_progress_rendering() -> None:
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.childElementCount = 0; this.className = ""; this.textContent = ""; }
          append(...nodes) { this.children.push(...nodes); this.childElementCount = this.children.length; }
          replaceChildren(...nodes) { this.children = [...nodes]; this.childElementCount = this.children.length; }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.testLocale = "en";
        const en = {
          "command.measure-log": "Measurement log",
          "command.measure-until": "Measure until",
          "command.triggered-measure-loop": "Triggered measurement loop",
          "command.capture-batch": "Capture batch",
          "command.capture-until": "Capture until",
          "command.triggered-capture-series": "Triggered capture series",
          "command.capture-monitor": "Capture monitor",
          "command.sequence": "Sequence",
          "status.queued": "Queued",
          "status.running": "Running",
          "status.completed": "Completed",
          "status.cancelled": "Cancelled",
          "results.summary.queued": "Waiting to run...",
          "results.summary.running": "Executing command...",
          "results.summary.sequenceProgress": "{{completed}} / {{total}} step executions completed",
          "results.summary.workflowProgressKnown": "{{completed}} / {{total}} {{unit}} completed \u00b7 {{elapsed}} s elapsed",
          "results.summary.workflowProgressUnknown": "{{completed}} {{unit}} completed \u00b7 {{elapsed}} s elapsed",
          "results.progress.rows": "rows",
          "results.progress.samples": "samples",
          "results.progress.cycles": "cycles",
          "results.progress.captures": "captures",
          "results.empty": "No command has been run yet.",
        };
        const translate = (key, values = {}) => {
          const text = en[key] || key;
          return Object.entries(values).reduce((v,[k,r])=>v.replaceAll(`{{${k}}}`,String(r)), text);
        };
        const hasTranslation = (key) => key in en;
        const translateJobStatus = (status) => translate(`status.${status}`);
        globalThis.testTranslate = translate;
        globalThis.testHasTranslation = hasTranslation;
        globalThis.testTranslateJobStatus = translateJobStatus;

        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          "const translateJobStatus = globalThis.testTranslateJobStatus;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "").replace(/^export function /gm, "function ")
          + "\nglobalThis.resultApi = { renderJob, renderEmpty };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const summary = new FakeNode("div");
        const detail = new FakeNode("div");
        const api = globalThis.resultApi;
        const makeJob = (command, status, progress) => ({ job_id: `job-${command}`, command, status, progress });
        const rowTexts = () => summary.children.map((row) => row.children.map((n) => n.textContent).join(" | "));

        // fixed total: capture-batch 4/10
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("capture-batch", "running", { completed_count: 4, total_count: 10, elapsed_seconds: 3.2 }), detail);
        let text = rowTexts()[0];
        assert.match(text, /4 \/ 10/);
        assert.match(text, /captures/);
        assert.match(text, /3\.2/);
        assert.match(text, /s elapsed/);
        assert.equal(text.includes("Running \u2014"), false, "should not repeat Running");
        assert.equal(text.includes("/ 0"), false);

        // unknown total: measure-until 12 samples
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("measure-until", "running", { completed_count: 12, total_count: null, elapsed_seconds: 8.4 }), detail);
        text = rowTexts()[0];
        assert.match(text, /12/);
        assert.match(text, /samples/);
        assert.match(text, /8\.4/);
        assert.equal(text.includes("/ 0"), false);
        assert.equal(text.includes("/ null"), false);
        assert.equal(/\d+ \/ null/.test(text), false);

        // measure-log rows
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("measure-log", "running", { completed_count: 2, total_count: 5, elapsed_seconds: 1.0 }), detail);
        text = rowTexts()[0];
        assert.match(text, /rows/);
        assert.match(text, /2 \/ 5/);

        // triggered-measure-loop cycles unknown
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("triggered-measure-loop", "running", { completed_count: 7, total_count: null, elapsed_seconds: 2.5 }), detail);
        text = rowTexts()[0];
        assert.match(text, /cycles/);
        assert.match(text, /7/);

        // sequence retained
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("sequence", "running", { completed_count: 3, total_count: 8, elapsed_seconds: 5 }), detail);
        text = rowTexts()[0];
        assert.match(text, /3 \/ 8 step executions completed/);

        // capture-monitor must not use generic workflow progress
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("capture-monitor", "running", { completed_count: 4, total_count: 10, elapsed_seconds: 3.2 }), detail);
        text = rowTexts()[0];
        assert.equal(text.includes("captures"), false, "capture-monitor should not show generic captures progress");
        assert.match(text, /Executing command\.\.\./);

        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(RESULTS_JS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
