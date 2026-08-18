from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_JS = REPO_ROOT / "src" / "scopes_tool_webui" / "static" / "results.js"
APP_JS = REPO_ROOT / "src" / "scopes_tool_webui" / "static" / "app.js"
STYLES_CSS = REPO_ROOT / "src" / "scopes_tool_webui" / "static" / "styles.css"


def test_result_panel_preserves_powers_style_bounded_job_history() -> None:
    source = RESULTS_JS.read_text(encoding="utf-8")

    assert "const RESULT_HISTORY_LIMIT = 20;" in source
    assert "let resultHistory = [];" in source
    assert "resultHistory.findIndex(" in source
    assert 'entry.job.job_id === job.job_id' in source
    assert "resultHistory[existingIndex].job = job;" in source
    assert 'resultHistory.unshift({ kind: "job", job });' in source
    assert "resultHistory = resultHistory.slice(0, RESULT_HISTORY_LIMIT);" in source
    assert "resultHistory.forEach((entry) =>" in source
    assert "commandLabel(entry.job.command)" in source
    assert "commandLabel(entry.command)" in source
    assert "translateJobStatus(statusValue)" in source
    assert 'translate("results.summary.queued")' in source
    assert 'translate("results.summary.running")' in source
    assert "successfulJobSummary(job)" in source
    assert "results.detailAvailable" not in source


def test_result_clear_resets_history_and_detail() -> None:
    source = RESULTS_JS.read_text(encoding="utf-8")
    app_source = APP_JS.read_text(encoding="utf-8")

    render_empty = source.split("export function renderEmpty", 1)[1].split("\n}", 1)[0]
    assert "resultHistory = [];" in render_empty
    assert "summaryContainer.replaceChildren(emptyMessage());" in render_empty
    assert "detailContainer.replaceChildren(emptyMessage());" in render_empty
    assert 'elements.resultClear.addEventListener("click", () => {' in app_source
    assert 'resultPresentation = { kind: "empty", job: null, message: null };' in app_source
    assert "renderCurrentResult();" in app_source


def test_result_history_has_powers_like_viewport_and_item_presentation() -> None:
    source = STYLES_CSS.read_text(encoding="utf-8")
    viewport = source.split(".results-content {", 1)[1].split("}", 1)[0]
    item = source.split(".result-summary-line {", 1)[1].split("}", 1)[0]

    assert "display: grid;" in viewport
    assert "gap: 6px;" in viewport
    assert "max-height: 220px;" in viewport
    assert "overflow: auto;" in viewport
    assert "padding: 9px 12px;" in item
    assert "border: 1px solid var(--line);" in item
    assert "border-radius: var(--radius-sm);" in item
    assert "background: var(--panel-soft);" in item
    assert "box-shadow: var(--shadow-sm);" in item


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_result_history_runtime_behaviour() -> None:
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
        const labels = {
          en: {
            identify: "Identify", run: "Run", listResources: "List resources", completed: "Completed", failed: "Failed", queued: "Queued", running: "Running",
            queuedSummary: "Waiting to run...", runningSummary: "Executing command...", completedSummary: "Command completed successfully", resourceNone: "No resources found", resourceMany: "4 resources found",
            serial: "serial {{serial}}", firmware: "firmware {{firmware}}", empty: "No command has been run yet.",
          },
          "zh-TW": {
            identify: "\u8b58\u5225", run: "\u57f7\u884c", listResources: "\u5217\u51fa\u8cc7\u6e90", completed: "\u5b8c\u6210", failed: "\u5931\u6557", queued: "\u6392\u968a\u4e2d", running: "\u57f7\u884c\u4e2d",
            queuedSummary: "\u7b49\u5f85\u57f7\u884c", runningSummary: "\u6b63\u5728\u57f7\u884c\u6307\u4ee4", completedSummary: "\u6307\u4ee4\u5df2\u6210\u529f\u5b8c\u6210", resourceNone: "\u627e\u4e0d\u5230\u8cc7\u6e90", resourceMany: "\u627e\u5230 4 \u500b\u8cc7\u6e90",
            serial: "\u5e8f\u865f {{serial}}", firmware: "\u97cc\u9ad4 {{firmware}}", empty: "\u5c1a\u672a\u57f7\u884c\u6307\u4ee4\u3002",
          },
        };
        const translate = (key, values = {}) => {
          const locale = labels[globalThis.testLocale];
          const text = key === "command.identify" ? locale.identify
            : key === "command.run" ? locale.run
              : key === "command.list-resources" ? locale.listResources
                : key === "status.completed" ? locale.completed
                  : key === "status.failed" ? locale.failed
                    : key === "status.queued" ? locale.queued
                      : key === "status.running" ? locale.running
                        : key === "results.summary.queued" ? locale.queuedSummary
                          : key === "results.summary.running" ? locale.runningSummary
                            : key === "results.summary.completed" ? locale.completedSummary
                              : key === "results.summary.resource_none" ? locale.resourceNone
                                : key === "results.summary.resource_many" ? locale.resourceMany
                                  : key === "results.summary.serial" ? locale.serial
                                    : key === "results.summary.firmware" ? locale.firmware
                                      : key === "results.empty" ? locale.empty
                                        : key;
          return Object.entries(values).reduce(
            (value, [name, replacement]) => value.replaceAll(`{{${name}}}`, String(replacement)),
            text,
          );
        };
        const hasTranslation = (key) => ["command.identify", "command.run", "command.list-resources"].includes(key);
        const translateJobStatus = (status) => translate(`status.${status}`);
        globalThis.testArtifactUrl = () => "";
        globalThis.testTranslate = translate;
        globalThis.testHasTranslation = hasTranslation;
        globalThis.testTranslateJobStatus = translateJobStatus;

        const source = [
          "const artifactUrl = globalThis.testArtifactUrl;",
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          "const translateJobStatus = globalThis.testTranslateJobStatus;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "").replace(/^export function /gm, "function ")
          + "\nglobalThis.resultApi = { renderEmpty, renderError, renderJob };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const summary = new FakeNode("div");
        const detail = new FakeNode("div");
        const api = globalThis.resultApi;
        const makeJob = (jobId, command, status, extra = {}) => ({ job_id: jobId, command, status, ...extra });
        const rowTexts = () => summary.children.map((row) => row.children.map((node) => node.textContent));

        for (let index = 1; index <= 21; index += 1) {
          api.renderJob(summary, makeJob(`job-${index}`, `command-${index}`, "completed", { result: { index } }), detail);
        }
        assert.equal(summary.children.length, 20);
        assert.equal(rowTexts()[0][0], "command-21");
        assert.equal(rowTexts().at(-1)[0], "command-2");
        assert.equal(rowTexts().some((row) => row[0] === "command-1"), false);

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("order-a", "identify", "running"), detail);
        api.renderJob(summary, makeJob("order-b", "run", "queued"), detail);
        api.renderJob(summary, makeJob("order-a", "identify", "completed", {
          result: { result: { idn: { model: "DSO-X 4024A" } } },
        }), detail);
        assert.deepEqual(rowTexts().map((row) => row[0]), ["Run", "Identify"]);
        assert.equal(rowTexts()[1][1], "Completed");

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("status-job", "identify", "queued"), detail);
        assert.deepEqual(rowTexts()[0], ["Identify", "Queued", "Waiting to run..."]);
        api.renderJob(summary, makeJob("status-job", "identify", "running"), detail);
        assert.deepEqual(rowTexts()[0], ["Identify", "Running", "Executing command..."]);

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("state-job", "identify", "queued"), detail);
        api.renderJob(summary, makeJob("state-job", "identify", "running"), detail);
        api.renderJob(summary, makeJob("state-job", "identify", "completed", {
          result: { result: { idn: { model: "DSO-X 4034A", serial: "MY55440270", firmware: "07.20" } } },
        }), detail);
        assert.deepEqual(rowTexts(), [["Identify", "Completed", "DSO-X 4034A - serial MY55440270 - firmware 07.20"]]);

        api.renderJob(summary, makeJob("run-job", "run", "completed", { result: { result: { action: "run" } } }), detail);
        assert.equal(rowTexts()[0][2], "Command completed successfully");
        api.renderJob(summary, makeJob("empty-resource-job", "list-resources", "completed", {
          result: { result: { resources: [] } },
        }), detail);
        assert.equal(rowTexts()[0][2], "No resources found");
        api.renderJob(summary, makeJob("resource-job", "list-resources", "completed", {
          result: { result: { resources: ["USB0::1", "USB0::2", "USB0::3", "USB0::4"] } },
        }), detail);
        assert.equal(rowTexts()[0][2], "4 resources found");
        globalThis.testLocale = "zh-TW";
        api.renderJob(summary, makeJob("resource-job", "list-resources", "completed", {
          result: { result: { resources: ["USB0::1", "USB0::2", "USB0::3", "USB0::4"] } },
        }), detail);
        assert.equal(summary.children.length, 4);
        assert.equal(rowTexts()[0][2], "\u627e\u5230 4 \u500b\u8cc7\u6e90");
        assert(rowTexts().some((row) => row[2] === "\u6307\u4ee4\u5df2\u6210\u529f\u5b8c\u6210"));
        assert(rowTexts().some((row) => row[2] === "DSO-X 4034A - \u5e8f\u865f MY55440270 - \u97cc\u9ad4 07.20"));

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("zh-status-job", "identify", "queued"), detail);
        assert.deepEqual(rowTexts()[0], ["\u8b58\u5225", "\u6392\u968a\u4e2d", "\u7b49\u5f85\u57f7\u884c"]);
        api.renderJob(summary, makeJob("zh-status-job", "identify", "running"), detail);
        assert.deepEqual(rowTexts()[0], ["\u8b58\u5225", "\u57f7\u884c\u4e2d", "\u6b63\u5728\u57f7\u884c\u6307\u4ee4"]);

        const rawError = "VISA <raw> detail";
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("failed-job", "identify", "failed", { error: rawError }), detail);
        assert.equal(rowTexts()[0][2], rawError);
        assert.equal(detail.children[0].textContent, rawError);
        api.renderError(summary, detail, rawError, "list-resources");
        assert.deepEqual(rowTexts()[0], ["\u5217\u51fa\u8cc7\u6e90", "\u5931\u6557", rawError]);
        api.renderEmpty(summary, detail);
        assert.equal(summary.children.length, 1);
        assert.equal(summary.children[0].className, "muted");
        assert.equal(summary.children[0].textContent, "\u5c1a\u672a\u57f7\u884c\u6307\u4ee4\u3002");
        assert.equal(detail.children[0].className, "muted");
        assert.equal(detail.children[0].textContent, "\u5c1a\u672a\u57f7\u884c\u6307\u4ee4\u3002");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(RESULTS_JS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
