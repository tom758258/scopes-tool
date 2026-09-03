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
LOCALE_EN_JS = REPO_ROOT / "src" / "scopes_tool_webui" / "static" / "locale_en.js"
LOCALE_ZH_TW_JS = REPO_ROOT / "src" / "scopes_tool_webui" / "static" / "locale_zh_tw.js"


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


def test_identify_detail_is_localized_and_keeps_raw_json() -> None:
    source = RESULTS_JS.read_text(encoding="utf-8")
    english = LOCALE_EN_JS.read_text(encoding="utf-8")
    chinese = LOCALE_ZH_TW_JS.read_text(encoding="utf-8")

    assert 'job.command === "identify" && job.status === "completed"' in source
    assert 'result.textContent = JSON.stringify(job.result, null, 2);' in source
    assert '"results.identity.manufacturer": "Manufacturer"' in english
    assert '"results.identity.resource": "Resource"' in english
    assert '"results.identity.manufacturer": "製造商"' in chinese
    assert '"results.identity.resource": "資源"' in chinese


def test_result_ui_reuses_job_artifact_download_entries() -> None:
    source = RESULTS_JS.read_text(encoding="utf-8")
    locales = (
        LOCALE_EN_JS.read_text(encoding="utf-8"),
        LOCALE_ZH_TW_JS.read_text(encoding="utf-8"),
    )

    assert "job.artifacts" in source
    assert "artifact.url" in source
    assert "job.result?.artifacts" not in source
    assert "results.summary.artifact_one" not in source
    assert "results.summary.artifact_many" not in source
    for locale in locales:
        assert "results.summary.artifact_one" not in locale
        assert "results.summary.artifact_many" not in locale
        assert "results.artifacts" in locale
        assert "results.download" not in locale
        assert "results.artifactSize" not in locale
        assert '"results.field.files":' in locale
    assert "appendWorkspaceArtifacts" not in source
    assert 'result.textContent = JSON.stringify(job.result, null, 2);' in source


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
    english = LOCALE_EN_JS.read_text(encoding="utf-8")
    chinese = LOCALE_ZH_TW_JS.read_text(encoding="utf-8")
    assert '"enum.vpp": "Vp-p"' in english
    assert '"enum.vpp": "Vp-p"' in chinese
    assert '"results.status.planned": "Planned"' in english
    assert '"results.status.instrument_error": "Instrument error"' in english
    assert '"results.status.planned": "已規劃"' in chinese
    assert '"results.status.instrument_error": "儀器錯誤"' in chinese
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
            identify: "Read device information", run: "Run", screenshot: "Screenshot", capture: "Capture", listResources: "List resources", completed: "Completed", failed: "Failed", queued: "Queued", running: "Running", cancelled: "Cancelled",
            queuedSummary: "Waiting to run...", runningSummary: "Executing command...", completedSummary: "Command completed successfully", screenshotCaptured: "Screenshot captured", resourceNone: "No resources found", resourceMany: "4 resources found",
            serial: "serial {{serial}}", firmware: "firmware {{firmware}}", empty: "No command has been run yet.",
            period: "Period", phase: "Phase", vpp: "Vp-p", channel1: "Channel 1", channel2: "Channel 2",
            measurement: "Measurement", channel: "Channel", referenceChannel: "Reference channel", value: "Value", unit: "Unit", status: "Status", result: "Result", plannedScpi: "Planned SCPI",
            validCount: "Valid count", invalidCount: "Invalid count", errorCount: "Error count", valid: "Valid", invalid: "Invalid", error: "Error",
            noValidStatus: "No valid measurement", noValidSummary: "No valid measurement value", planned: "Planned", instrumentError: "Instrument error", integrate: "Integrate", fftPhase: "FFT phase", fftZoom: "Zoom",
          },
          "zh-TW": {
            identify: "\u8b80\u53d6\u88dd\u7f6e\u8cc7\u8a0a", run: "\u57f7\u884c", screenshot: "\u64f7\u53d6\u756b\u9762", capture: "\u64f7\u53d6\u6ce2\u5f62", listResources: "\u5217\u51fa\u8cc7\u6e90", completed: "\u5b8c\u6210", failed: "\u5931\u6557", queued: "\u6392\u968a\u4e2d", running: "\u57f7\u884c\u4e2d", cancelled: "\u5df2\u53d6\u6d88",
            queuedSummary: "\u7b49\u5f85\u57f7\u884c", runningSummary: "\u6b63\u5728\u57f7\u884c\u6307\u4ee4", completedSummary: "\u6307\u4ee4\u5df2\u6210\u529f\u5b8c\u6210", screenshotCaptured: "\u756b\u9762\u5df2\u64f7\u53d6", resourceNone: "\u627e\u4e0d\u5230\u8cc7\u6e90", resourceMany: "\u627e\u5230 4 \u500b\u8cc7\u6e90",
            serial: "\u5e8f\u865f {{serial}}", firmware: "\u97cc\u9ad4 {{firmware}}", empty: "\u5c1a\u672a\u57f7\u884c\u6307\u4ee4\u3002",
            period: "Period", phase: "Phase", vpp: "Vp-p", channel1: "Channel 1", channel2: "Channel 2",
            measurement: "Measurement", channel: "Channel", referenceChannel: "Reference channel", value: "Value", unit: "Unit", status: "Status", result: "Result", plannedScpi: "Planned SCPI",
            validCount: "Valid count", invalidCount: "Invalid count", errorCount: "Error count", valid: "Valid", invalid: "Invalid", error: "Error",
            noValidStatus: "\u7121\u6548\u91cf\u6e2c\u503c", noValidSummary: "\u7121\u6548\u91cf\u6e2c\u503c", planned: "\u5df2\u898f\u5283", instrumentError: "\u5100\u5668\u932f\u8aa4", integrate: "\u7a4d\u5206", fftPhase: "FFT \u76f8\u4f4d", fftZoom: "\u7e2e\u653e\u8996\u7a97",
          },
        };
        const translate = (key, values = {}) => {
          const locale = labels[globalThis.testLocale];
          const text = key === "command.identify" ? locale.identify
            : key === "command.run" ? locale.run
              : key === "command.screenshot" ? locale.screenshot
                : key === "command.capture" ? locale.capture
                  : key === "command.list-resources" ? locale.listResources
                    : key === "status.completed" ? locale.completed
                      : key === "results.status.planned" ? locale.planned
                        : key === "results.status.instrument_error" ? locale.instrumentError
                      : key === "status.failed" ? locale.failed
                        : key === "status.queued" ? locale.queued
                          : key === "status.running" ? locale.running
                            : key === "status.cancelled" ? locale.cancelled
                            : key === "results.summary.queued" ? locale.queuedSummary
                              : key === "results.summary.running" ? locale.runningSummary
                                : key === "results.summary.completed" ? locale.completedSummary
                                  : key === "results.summary.screenshotCaptured" ? locale.screenshotCaptured
                                    : key === "results.summary.resource_none" ? locale.resourceNone
                                      : key === "results.summary.resource_many" ? locale.resourceMany
                                        : key === "results.summary.serial" ? locale.serial
                                          : key === "results.summary.firmware" ? locale.firmware
                                         : key === "results.empty" ? locale.empty
                                           : key === "enum.period" ? locale.period
                                            : key === "enum.phase" ? locale.phase
                                              : key === "enum.vpp" ? locale.vpp
                                               : key === "enum.channel1" ? locale.channel1
                                               : key === "enum.channel2" ? locale.channel2
                                                 : key === "enum.math-transform.integrate" ? locale.integrate
                                                   : key === "enum.fft-operation.fft-phase" ? locale.fftPhase
                                                     : key === "enum.fft-gate.zoom" ? locale.fftZoom
                                                   : key === "results.field.measurement" ? locale.measurement
                                                     : key === "results.field.channel" ? locale.channel
                                                        : key === "results.field.reference_channel" ? locale.referenceChannel
                                                          : key === "results.field.value" ? locale.value
                                                            : key === "results.field.unit" ? locale.unit
                                                              : key === "results.field.status" ? locale.status
                                                                : key === "results.field.valid_count" ? locale.validCount
                                                                  : key === "results.field.invalid_count" ? locale.invalidCount
                                                                    : key === "results.field.error_count" ? locale.errorCount
                                                         : key === "results.field.result" ? locale.result
                            : key === "results.field.planned_scpi" ? locale.plannedScpi
                               : key === "results.status.noValidMeasurement" ? locale.noValidStatus
                                 : key === "results.status.valid" ? locale.valid
                                   : key === "results.status.invalid" ? locale.invalid
                                     : key === "results.status.error" ? locale.error
                                : key === "results.summary.noValidMeasurement" ? locale.noValidSummary
                                                              : key;
          return Object.entries(values).reduce(
            (value, [name, replacement]) => value.replaceAll(`{{${name}}}`, String(replacement)),
            text,
          );
        };
        const hasTranslation = (key) => [
          "command.identify", "command.run", "command.screenshot", "command.capture", "command.list-resources",
          "enum.period", "enum.phase", "enum.vpp", "enum.channel1", "enum.channel2",
          "enum.math-transform.integrate", "enum.fft-operation.fft-phase", "enum.fft-gate.zoom",
          "results.status.planned", "results.status.instrument_error", "status.completed",
          "results.field.measurement", "results.field.channel", "results.field.reference_channel", "results.field.value", "results.field.unit", "results.field.status", "results.field.valid_count", "results.field.invalid_count", "results.field.error_count", "results.field.result", "results.field.planned_scpi",
          "results.status.noValidMeasurement", "results.status.valid", "results.status.invalid", "results.status.error", "results.summary.noValidMeasurement",
        ].includes(key);
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
          + "\nglobalThis.resultApi = { renderEmpty, renderError, renderIdentityWorkspaceResult, renderJob, renderWorkspaceResult };";
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
        assert.deepEqual(rowTexts().map((row) => row[0]), ["Run", "Read device information"]);
        assert.equal(rowTexts()[1][1], "Completed");

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("status-job", "identify", "queued"), detail);
        assert.deepEqual(rowTexts()[0], ["Read device information", "Queued", "Waiting to run..."]);
        api.renderJob(summary, makeJob("status-job", "identify", "running"), detail);
        assert.deepEqual(rowTexts()[0], ["Read device information", "Running", "Executing command..."]);

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("state-job", "identify", "queued"), detail);
        api.renderJob(summary, makeJob("state-job", "identify", "running"), detail);
        api.renderJob(summary, makeJob("state-job", "identify", "completed", {
          resource: "USB0::SCOPE::INSTR",
          result: { result: { idn: { vendor: "KEYSIGHT TECHNOLOGIES", model: "DSO-X 4034A", serial: "SYNTH12345", firmware: "0.0" } } },
        }), detail);
        assert.deepEqual(rowTexts(), [["Read device information", "Completed", "DSO-X 4034A - serial SYNTH12345 - firmware 0.0"]]);
        assert.equal(detail.children[0].className, "identity-result");
        assert.equal(detail.children[0].children.length, 10);
        assert.equal(detail.children[1].className, "result-block");

        const workspace = new FakeNode("div");
        api.renderIdentityWorkspaceResult(workspace, makeJob("workspace-identity", "identify", "completed", {
          resource: "USB0::SCOPE::INSTR",
          result: { result: { idn: { vendor: "KEYSIGHT TECHNOLOGIES", model: "DSO-X 4034A", serial: "SYNTH12345", firmware: "0.0" } } },
        }));
        assert.equal(workspace.children.length, 5);
        assert.deepEqual(
          workspace.children.map((field) => field.children.map((node) => node.textContent)),
          [
            ["KEYSIGHT TECHNOLOGIES", "results.identity.manufacturer"],
            ["DSO-X 4034A", "results.identity.model"],
            ["SYNTH12345", "results.identity.serial"],
            ["0.0", "results.identity.firmware"],
            ["USB0::SCOPE::INSTR", "results.identity.resource"],
          ],
        );

        const filteredWorkspace = new FakeNode("div");
        const diagnosticJob = makeJob("diagnostic", "search-mode", "completed", {
          result: { result: { mode: "serial1", raw_mode: "SBUS1", raw_value: "1", operation_raw: "1" } },
        });
        api.renderWorkspaceResult(filteredWorkspace, diagnosticJob);
        assert.equal(filteredWorkspace.children.length, 1);
        assert.equal(filteredWorkspace.children[0].children[0].textContent, "serial1");
        api.renderJob(summary, diagnosticJob, detail);
        assert.match(detail.children[0].textContent, /raw_mode/);
        assert.match(detail.children[0].textContent, /raw_value/);
        assert.match(detail.children[0].textContent, /operation_raw/);

        const artifactJob = makeJob("artifact-job", "screenshot", "completed", {
          result: { result: { artifact: "capture.png" } },
          artifacts: [{ name: "capture.png", kind: "screenshot", size: 10, url: "/api/jobs/artifact-job/artifacts/capture.png" }],
        });
        api.renderJob(summary, artifactJob, detail);
        assert.equal(rowTexts()[0][2], "Screenshot captured");
        assert.equal(detail.children.length, 3);
        assert.equal(detail.children[0].tagName, "PRE");
        assert.equal(detail.children[2].children[0].children[0].textContent, "capture.png");
        assert.equal(detail.children[2].children[0].children[0].href, "/api/jobs/artifact-job/artifacts/capture.png");
        const artifactWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(artifactWorkspace, artifactJob);
        assert.equal(artifactWorkspace.children.length, 1);
        assert.equal(artifactWorkspace.children[0].children[0].tagName, "SPAN");

        const captureJob = makeJob("capture-job", "capture", "completed", {
          result: { result: { artifact: "capture.csv", metadata_artifact: "capture_meta.json" } },
          artifacts: [
            { name: "capture.csv", kind: "waveform", size: 10 },
            { name: "capture_meta.json", kind: "metadata", size: 20 },
          ],
        });
        api.renderJob(summary, captureJob, detail);
        assert.equal(rowTexts()[0][2], "Command completed successfully");

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
        assert.equal(summary.children.length, 7);
        assert.equal(rowTexts()[0][2], "\u627e\u5230 4 \u500b\u8cc7\u6e90");
        assert(rowTexts().some((row) => row[2] === "\u6307\u4ee4\u5df2\u6210\u529f\u5b8c\u6210"));
        assert(rowTexts().some((row) => row[2] === "DSO-X 4034A - \u5e8f\u865f SYNTH12345 - \u97cc\u9ad4 0.0"));

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("zh-status-job", "identify", "queued"), detail);
        assert.deepEqual(rowTexts()[0], ["\u8b80\u53d6\u88dd\u7f6e\u8cc7\u8a0a", "\u6392\u968a\u4e2d", "\u7b49\u5f85\u57f7\u884c"]);
        api.renderJob(summary, makeJob("zh-status-job", "identify", "running"), detail);
        assert.deepEqual(rowTexts()[0], ["\u8b80\u53d6\u88dd\u7f6e\u8cc7\u8a0a", "\u57f7\u884c\u4e2d", "\u6b63\u5728\u57f7\u884c\u6307\u4ee4"]);

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

        // Invalid measurement sentinel should be presented as warning, not generic failure
        globalThis.testLocale = "en";
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("invalid-measure-job", "measure", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: { item: "vpp", channel: 1, valid: false, reason: "invalid measurement sentinel", value: null, raw_value: "+99E+36", unit: "V" }, system_error: { code: 0, is_error: false, message: "No error" } },
        }), detail);
        assert.equal(summary.children[0].children[1].className, "badge badge-warning");
        assert.equal(summary.children[0].children[1].textContent, "No valid measurement");
        assert.equal(summary.children[0].children[2].textContent, "No valid measurement value");
        assert.equal(detail.children.length, 1);
        assert.equal(detail.children[0].className, "result-block");
        assert.match(detail.children[0].textContent, /\+99E\+36/);
        assert.match(detail.children[0].textContent, /No error/);
        // Cancelled job must not be presented as invalid measurement warning
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("cancelled-measure-job", "measure", "cancelled", {
          result: { exit_code: 1, result: { item: "vpp", channel: 1, valid: false, reason: "invalid measurement sentinel", value: null, raw_value: "+99E+36", unit: "V" }, system_error: { code: 0, is_error: false, message: "No error" } },
        }), detail);
        assert.equal(summary.children[0].children[1].className, "badge badge-cancelled");
        assert.equal(summary.children[0].children[1].textContent, "Cancelled");
        assert.equal(summary.children[0].children[2].textContent, "Cancelled");
        assert.equal(detail.children.length, 1);
        assert.equal(detail.children[0].className, "result-block");
        // Invalid sentinel with real system error must not be presented as warning
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("invalid-measure-system-error-job", "measure", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: { item: "vpp", channel: 1, valid: false, reason: "invalid measurement sentinel", value: null, raw_value: "+99E+36", unit: "V" }, system_error: { code: -113, is_error: true, message: "Undefined header" } },
        }), detail);
        assert.equal(summary.children[0].children[1].className, "badge badge-failed");
        assert.equal(summary.children[0].children[2].textContent, "Core command returned a non-zero exit code.");
        assert.equal(detail.children[0].className, "error-block");
        // Generic failed job still shows error block
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("generic-failed-job", "measure", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { result: { item: "vpp", channel: 1, valid: true, value: 1.2 } },
        }), detail);
        assert.equal(summary.children[0].children[1].className, "badge badge-failed");
        assert.equal(detail.children[0].className, "error-block");

        const measurementJob = (result) => makeJob("measurement-job", "measure", "completed", { result: { result } });
        const fieldTexts = (container) => container.children.map((field) => field.children.map((node) => node.textContent));
        globalThis.testLocale = "zh-TW";
        api.renderEmpty(summary, detail);
        const plannedStatusJob = makeJob("planned-status", "run", "completed", {
          result: { result: { status: "planned" } },
        });
        api.renderJob(summary, plannedStatusJob, detail);
        assert.equal(rowTexts()[0][2], "\u5df2\u898f\u5283");
        const plannedStatus = new FakeNode("div");
        api.renderWorkspaceResult(plannedStatus, plannedStatusJob);
        assert.equal(fieldTexts(plannedStatus)[0][0], "\u5df2\u898f\u5283");

        const instrumentError = new FakeNode("div");
        api.renderWorkspaceResult(instrumentError, makeJob("instrument-error", "capture", "completed", {
          result: { result: { status: "instrument_error" } },
        }));
        assert.equal(fieldTexts(instrumentError)[0][0], "\u5100\u5668\u932f\u8aa4");

        const completedStatus = new FakeNode("div");
        api.renderWorkspaceResult(completedStatus, makeJob("completed-status", "capture", "completed", {
          result: { result: { status: "completed" } },
        }));
        assert.equal(fieldTexts(completedStatus)[0][0], "\u5b8c\u6210");

        const mathTransform = new FakeNode("div");
        const mathTransformJob = makeJob("math-transform", "math-transform", "completed", {
          result: { result: { math_transform: { operation: "integrate", operation_raw: "INTegRate" } } },
        });
        api.renderWorkspaceResult(mathTransform, mathTransformJob);
        assert.deepEqual(fieldTexts(mathTransform), [["\u7a4d\u5206", "Operation"]]);
        api.renderJob(summary, mathTransformJob, detail);
        assert.match(detail.children[0].textContent, /"operation": "integrate"/);
        assert.match(detail.children[0].textContent, /"operation_raw": "INTegRate"/);

        const fft = new FakeNode("div");
        api.renderWorkspaceResult(fft, makeJob("fft", "fft", "completed", {
          result: { result: { fft: { operation: "FFTPhase", operation_canonical: "fft-phase", gate: "zoom" } } },
        }));
        assert.deepEqual(fieldTexts(fft).map((field) => field[0]), ["FFTPhase", "FFT \u76f8\u4f4d", "\u7e2e\u653e\u8996\u7a97"]);

        globalThis.testLocale = "en";
        const singleMeasurement = new FakeNode("div");
        api.renderWorkspaceResult(singleMeasurement, measurementJob({
          item: "period", channel: 1, reference_channel: null, value: 0.001, unit: "s", valid: true,
          command: ":MEASure:PERiod? CHANnel1", parameters: { item: "period" },
        }));
        assert.deepEqual(fieldTexts(singleMeasurement), [
          ["Period", "Measurement"], ["Channel 1", "Channel"], ["0.001 s", "Result"],
        ]);
        assert(!JSON.stringify(fieldTexts(singleMeasurement)).includes(":MEASure:"));
        const pairMeasurement = new FakeNode("div");
        api.renderWorkspaceResult(pairMeasurement, measurementJob({
          item: "phase", channel: 1, reference_channel: 2, value: 32.4, unit: "deg", valid: true,
          command: ":MEASure:PHASe? CHANnel1,CHANnel2",
        }));
        assert.deepEqual(fieldTexts(pairMeasurement), [
          ["Phase", "Measurement"], ["Channel 1", "Channel"],
          ["Channel 2", "Reference channel"], ["32.4 deg", "Result"],
        ]);
        const sweep = new FakeNode("div");
        api.renderWorkspaceResult(sweep, makeJob("sweep", "measure-sweep", "completed", {
          result: { result: {
            channels: [1], items: ["vpp"], pairs: [], pair_items: [],
            summary: { valid_count: 1, invalid_count: 1, error_count: 1 },
            measurements: [
              { item: "vpp", channel: 1, reference_channel: null, value: 3.2, unit: "V", valid: true, command: ":MEASure:VPP? CHANnel1" },
              { item: "phase", channel: 1, reference_channel: 2, value: null, unit: "deg", valid: false, system_error: { code: 0 } },
              { item: "phase", channel: 2, reference_channel: 1, value: null, unit: "deg", valid: false, error: { type: "VisaBackendError" }, command: ":MEASure:PHASe?" },
            ],
          } },
        }));
        assert.deepEqual(fieldTexts(sweep).slice(0, 3), [
          ["1", "Valid count"], ["1", "Invalid count"], ["1", "Error count"],
        ]);
        const table = sweep.children[3];
        assert.equal(table.tagName, "TABLE");
        assert.deepEqual(table.children[0].children[0].children.map((cell) => cell.textContent), [
          "Measurement", "Channel", "Reference channel", "Value", "Unit", "Status",
        ]);
        const rows = table.children[1].children.map(
          (row) => row.children.map((cell) => cell.textContent),
        );
        assert.deepEqual(rows, [
          ["Vp-p", "CH1", "—", "3.2", "V", "Valid"],
          ["Phase", "CH1", "CH2", "—", "deg", "Invalid"],
          ["Phase", "CH2", "CH1", "—", "deg", "Error"],
        ]);
        const simpleTableText = JSON.stringify(rows);
        assert.equal(simpleTableText.includes(":MEASure:"), false);
        assert.equal(simpleTableText.includes("system_error"), false);
        const dryRunMeasurement = new FakeNode("div");
        api.renderWorkspaceResult(dryRunMeasurement, measurementJob({
          planned_scpi: [":MEASure:PERiod? CHANnel1"],
        }), { mode: "dry-run" });
        const dryRunText = JSON.stringify(fieldTexts(dryRunMeasurement));
        assert(dryRunText.includes("Planned SCPI"));
        assert(dryRunText.includes(":MEASure:PERiod? CHANnel1"));
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(RESULTS_JS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_channel_summary_workspace_result_focused_behavior() -> None:
    english = LOCALE_EN_JS.read_text(encoding="utf-8")
    chinese = LOCALE_ZH_TW_JS.read_text(encoding="utf-8")
    assert '"results.field.termination_reason": "Termination reason"' in english
    assert '"results.field.acquisition": "擷取"' in chinese
    assert '"enum.condition_met": "條件成立"' in chinese
    assert '"results.field.completed_count": "完成數量"' in chinese
    assert '"results.field.last_measurement": "最後量測"' in chinese
    assert '"results.field.index": "索引"' in chinese
    assert '"results.field.matched": "符合"' in chinese
    script = textwrap.dedent(
        r"""
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag) {
            this.tagName = tag.toUpperCase(); this.children = []; this.childElementCount = 0; this.className = ""; this.textContent = "";
          }
          append(...nodes) { this.children.push(...nodes); this.childElementCount = this.children.length; }
          replaceChildren(...nodes) { this.children = [...nodes]; this.childElementCount = this.children.length; }
        }

        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.testLocale = "en";

        const enLabels = {
          "command.channel-summary": "Channel summary",
          "enum.channel1": "Channel 1",
          "enum.channel2": "Channel 2",
          "status.enabled": "Enabled",
          "status.disabled": "Disabled",
          "status.yes": "Yes",
          "status.no": "No",
          "enum.query": "Query",
          "enum.normal": "Normal",
          "actions.run": "Run",
          "status.completed": "Completed",
          "enum.condition_met": "Condition met",
          "results.field.acquisition": "Acquisition",
          "results.field.completed_count": "Completed count",
          "results.field.last_measurement": "Last measurement",
          "results.field.index": "Index",
          "results.field.matched": "Matched",
          "results.field.scale": "Scale",
          "results.field.impedance": "Impedance",
          "results.field.probe_ratio": "Probe ratio",
          "results.field.label": "Label",
          "results.field.units": "Units",
          "results.channelSummary.field.scale": "Vertical scale",
        };
        const zhLabels = {
          "status.yes": "\u662f",
          "status.no": "\u5426",
          "enum.query": "\u67e5\u8a62",
          "enum.normal": "\u6b63\u5e38",
          "actions.run": "\u57f7\u884c",
          "status.completed": "\u5df2\u5b8c\u6210",
          "enum.condition_met": "\u689d\u4ef6\u6210\u7acb",
          "results.field.acquisition": "\u64f7\u53d6",
          "results.field.completed_count": "\u5b8c\u6210\u6578\u91cf",
          "results.field.last_measurement": "\u6700\u5f8c\u91cf\u6e2c",
          "results.field.index": "\u7d22\u5f15",
          "results.field.matched": "\u7b26\u5408",
          "command.channel-summary": "通道設定摘要",
          "enum.channel1": "通道 1",
          "status.enabled": "已啟用",
          "status.disabled": "已停用",
          "results.field.scale": "刻度",
          "results.field.impedance": "輸入阻抗",
          "results.field.probe_ratio": "探棒衰減比",
          "results.field.label": "標籤",
          "results.field.units": "單位",
          "results.channelSummary.field.scale": "垂直刻度",
        };

        const translate = (key, values = {}) => {
          const dict = globalThis.testLocale === "zh-TW" ? zhLabels : enLabels;
          const text = dict[key] || key;
          return Object.entries(values).reduce(
            (value, [name, replacement]) => value.replaceAll(`{{${name}}}`, String(replacement)),
            text,
          );
        };
        const hasTranslation = (key) => {
          const dict = globalThis.testLocale === "zh-TW" ? zhLabels : enLabels;
          return key in dict;
        };
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
          + "\nglobalThis.resultApi = { renderEmpty, renderError, renderIdentityWorkspaceResult, renderJob, renderWorkspaceResult };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const api = globalThis.resultApi;
        const makeJob = (cmd, resultPayload, status = "completed") => ({
          job_id: "j1", command: cmd, status,
          result: { exit_code: 0, result: resultPayload },
        });

        // A: two independent cards, not a single semicolon-delimited text wall
        const workspace = new FakeNode("div");
        api.renderWorkspaceResult(workspace, makeJob("channel-summary", {
          channels: [
            { channel: 1, display: true, label: "", scale: 1.0, range: 8.0, offset: 0.0,
              coupling: "dc", impedance: "one_meg", invert: false, bandwidth_limit: false,
              units: "volt", vernier: false, probe_ratio: 10.0, probe_skew: 0.0 },
            { channel: 2, display: false, label: "CLK", scale: 0.5, range: 4.0, offset: 1.2,
              coupling: "ac", impedance: "fifty", invert: true, bandwidth_limit: true,
              units: "amp", vernier: true, probe_ratio: 1.0, probe_skew: 1e-9 },
          ],
        }));
        assert.equal(workspace.children.length, 2, "expect 2 independent cards");
        assert.equal(workspace.children[0].className, "workspace-channel-card");
        assert.equal(workspace.children[1].className, "workspace-channel-card");

        // B: representative formatting assertions
        const card1 = workspace.children[0];
        const fields1 = card1.children[1];
        const dd1 = fields1.children.filter((n) => n.tagName === "DD").map((n) => n.textContent);
        assert(dd1.some((t) => t === "Enabled"), "boolean enabled");
        assert(dd1.some((t) => t === "1 MΩ"), "one_meg");
        assert(dd1.some((t) => t === "1 V/div"), "scale with volt");
        assert(dd1.some((t) => t === "10:1"), "probe_ratio");
        assert(dd1.some((t) => t === "—"), "empty label");

        // C: zh-TW title and boolean translation
        globalThis.testLocale = "zh-TW";
        const zhWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(zhWorkspace, makeJob("channel-summary", {
          channels: [{ channel: 1, display: true, label: "", scale: 1.0, range: 8.0, offset: 0.0,
            coupling: "dc", impedance: "one_meg", invert: false, bandwidth_limit: false,
            units: "volt", vernier: false, probe_ratio: 10.0, probe_skew: 0.0 }],
        }));
        assert.equal(zhWorkspace.children.length, 1);
        assert.equal(zhWorkspace.children[0].children[0].textContent, "通道 1", "zh-TW title");
        const zhFields = zhWorkspace.children[0].children[1];
        const zhDt = zhFields.children.filter((n) => n.tagName === "DT").map((n) => n.textContent);
        const zhDd = zhFields.children.filter((n) => n.tagName === "DD").map((n) => n.textContent);
        assert(zhDt.some((t) => t === "垂直刻度"), "channel-summary-specific zh-TW label");
        assert(zhDd.some((t) => t === "已啟用"), "zh-TW boolean enabled");

        // D: unknown/missing unit must not fall back to V
        globalThis.testLocale = "en";
        const unknownWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(unknownWorkspace, makeJob("channel-summary", {
          channels: [{ channel: 1, display: false, label: "X", scale: 2.0, range: 10.0, offset: 0,
            coupling: "dc", impedance: "fifty", invert: false, bandwidth_limit: false,
            units: null, vernier: false, probe_ratio: 1.0, probe_skew: 0.5 }],
        }));
        const unknownFields = unknownWorkspace.children[0].children[1];
        const unknownDd = unknownFields.children.filter((n) => n.tagName === "DD").map((n) => n.textContent);
        assert(!unknownDd.some((t) => t.includes("V/div") || (t.includes(" V") && t !== "V")), "unknown unit must not be V");
        assert(unknownDd.some((t) => t === "2"), "scale without unit uses plain value");
        assert(unknownDd.some((t) => t === "10"), "range without unit uses plain value");

        // E: compact workflow result exposes its summary and final measurement
        const workflowWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(workflowWorkspace, makeJob("measure-until", {
          status: "completed",
          action: "query",
          enabled: true,
          completed_count: 2,
          last_measurement: { index: 2, value: "4", matched: true },
        }));
        const workflowText = workflowWorkspace.children.flatMap((field) =>
          field.children.map((node) => node.textContent)
        );
        assert(workflowText.includes("2"), "completed count");
        assert(workflowText.some((text) => text.includes("Index: 2")), "last measurement");
        assert(workflowText.includes("Query"), "canonical enum is localized in English");
        assert(workflowText.includes("Enabled"), "enabled boolean keeps enabled semantics");
        assert(workflowText.some((text) => text.includes("Matched: Yes")), "generic boolean uses neutral semantics");

        globalThis.testLocale = "zh-TW";
        const zhWorkflowWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(zhWorkflowWorkspace, makeJob("measure-until", {
          action: "query",
          enabled: false,
          completed_count: 2,
          last_measurement: { index: 2, value: "4", matched: true },
        }));
        const zhWorkflowText = zhWorkflowWorkspace.children.flatMap((field) =>
          field.children.map((node) => node.textContent)
        );
        assert(zhWorkflowText.includes("\u67e5\u8a62"), "canonical enum is localized in zh-TW");
        assert(zhWorkflowText.includes(zhLabels["status.disabled"]), "enabled boolean keeps zh-TW disabled semantics");
        assert(zhWorkflowText.some((text) => text.includes("\u7b26\u5408: \u662f")), "generic boolean uses zh-TW yes/no");

        const acquisitionWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(acquisitionWorkspace, makeJob("acquisition", {
          action: "run",
          acquisition: { type: "normal", count: 8 },
          text: "normal",
          label: "query",
        }));
        const acquisitionFields = acquisitionWorkspace.children.map((field) =>
          field.children.map((node) => node.textContent)
        );
        assert.deepEqual(acquisitionFields[0], ["\u57f7\u884c", "Action"]);
        assert(acquisitionFields[1][0].includes("\u6b63\u5e38"), "acquisition type is localized");
        assert.equal(acquisitionFields[1][1], "\u64f7\u53d6");
        assert.deepEqual(acquisitionFields[2], ["normal", "Text"]);
        assert.deepEqual(acquisitionFields[3], ["query", zhLabels["results.field.label"]]);

        const terminatedWorkflow = new FakeNode("div");
        api.renderWorkspaceResult(terminatedWorkflow, makeJob("measure-until", {
          status: "completed",
          termination_reason: "condition_met",
        }));
        const terminatedText = terminatedWorkflow.children.flatMap((field) =>
          field.children.map((node) => node.textContent)
        );
        assert(terminatedText.includes("\u5df2\u5b8c\u6210"));
        assert(terminatedText.includes("\u689d\u4ef6\u6210\u7acb"));
        globalThis.testLocale = "en";

        // A. command-scoped dispatch: non-channel-summary command must not use card renderer
        // even when result contains a channels array
        const otherWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(otherWorkspace, makeJob("some-other-command", {
          channels: [{ channel: 1, value: 123 }],
          count: 1,
        }));
        assert.equal(otherWorkspace.children.length, 2, "generic renderer should present count and channels fields");
        assert(!otherWorkspace.children.some((n) => n.className === "workspace-channel-card"), "non-channel-summary must not use card renderer");
        // The sibling field `count` should still be presented by generic workspace renderer
        // Because the command is not channel-summary, the renderer falls through to generic fields
        // (In this synthetic test we just protect that no `.workspace-channel-card` appears.)

        // B. single-key structured result unwrap preserves inner fields directly
        const unwrapWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(unwrapWorkspace, makeJob("timebase-scale", {
          timebase: { seconds_per_division: 0.001 },
        }));
        // After unwrap, the inner object fields should be presented directly,
        // not nested as a single semicolon-delimited text wall.
        const unwrapTexts = unwrapWorkspace.children.flatMap((field) =>
          field.children.map((node) => node.textContent),
        );
        assert(unwrapTexts.includes("0.001"), "unwrap must present inner numeric value directly");
        assert(unwrapTexts.includes("Seconds per division"), "unwrap must present inner field label directly");
        assert(!unwrapTexts.includes("Timebase"), "unwrap must not present outer wrapper as field");
        """
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(RESULTS_JS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
