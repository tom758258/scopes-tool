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


def test_single_wait_and_screenshot_result_fields_have_zh_tw_labels() -> None:
    english = LOCALE_EN_JS.read_text(encoding="utf-8")
    chinese = LOCALE_ZH_TW_JS.read_text(encoding="utf-8")
    expected = {
        "results.field.wait_enabled": ("Wait enabled", "啟用等待"),
        "results.field.arm_command": ("Arm command", "啟動指令"),
        "results.field.poll_source": ("Poll source", "輪詢來源"),
        "results.field.poll_command": ("Poll command", "輪詢指令"),
        "results.field.timeout_ms": ("Timeout ms", "逾時時間（毫秒）"),
        "results.field.poll_interval_ms": ("Poll interval ms", "輪詢間隔（毫秒）"),
        "results.field.force_on_timeout": ("Force on timeout", "逾時時強制觸發"),
        "results.field.force_command": ("Force command", "強制觸發指令"),
        "results.field.outcome": ("Outcome", "結果狀態"),
        "results.field.forced": ("Forced", "已強制觸發"),
        "results.field.timed_out": ("Timed out", "已逾時"),
        "results.field.poll_count": ("Poll count", "輪詢次數"),
        "results.field.elapsed_ms": ("Elapsed ms", "經過時間（毫秒）"),
        "results.field.condition_values": ("Condition values", "條件值"),
        "results.field.capture_allowed": ("Capture allowed", "允許擷取"),
        "results.field.capture_block_reason": ("Capture block reason", "禁止擷取原因"),
        "results.field.artifact": ("Artifact", "檔案"),
        "results.field.source_kind": ("Source kind", "來源種類"),
    }
    for key, (en_value, zh_value) in expected.items():
        assert f'"{key}": "{en_value}"' in english, key
        assert f'"{key}": "{zh_value}"' in chinese, key


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


def test_measurement_statistics_result_command_label_is_localized() -> None:
    english = LOCALE_EN_JS.read_text(encoding="utf-8")
    chinese = LOCALE_ZH_TW_JS.read_text(encoding="utf-8")

    assert english.count(
        '"command.measurement-statistics": "Advanced Measurement Statistics"'
    ) == 1
    assert chinese.count(
        '"command.measurement-statistics": "進階量測統計"'
    ) == 1


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
def test_result_history_runtime_behaviour(tmp_path: Path) -> None:
    english = LOCALE_EN_JS.read_text(encoding="utf-8")
    chinese = LOCALE_ZH_TW_JS.read_text(encoding="utf-8")
    assert '"enum.vpp": "Vp-p"' in english
    assert '"enum.vpp": "Vp-p"' in chinese
    assert '"results.status.planned": "Planned"' in english
    assert '"results.status.instrument_error": "Instrument error"' in english
    assert '"results.status.planned": "已規劃"' in chinese
    assert '"results.status.instrument_error": "儀器錯誤"' in chinese
    assert '"results.summary.triggerWaitTimedOut": "Trigger wait timed out."' in english
    assert '"results.summary.triggerWaitTimedOut": "等待觸發逾時。"' in chinese
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
            summary: "Summary", channels: "Channels", actualPoints: "Actual points", format: "Format", files: "Files",
            captureCompleted: "Waveform capture completed", capturePoints: "{{actual}} points (requested {{requested}})", capturePointsPerChannel: "{{actual}} (requested {{requested}} per channel)", outputFileCount: "{{count}} output files", waveformReadTimedOut: "Waveform data read timed out. The instrument may not have usable waveform data, or it did not respond in time. Confirm the selected channel is enabled and an acquisition has completed, then try again.",
            validCount: "Valid count", invalidCount: "Invalid count", errorCount: "Error count", valid: "Valid", invalid: "Invalid", error: "Error",
            noValidStatus: "No valid measurement", noValidSummary: "No valid measurement value", measurementTimedOut: "{{channel}} {{measurement}} measurement timed out.", measurementFailed: "{{channel}} {{measurement}} measurement failed.", measurementFailedWithReason: "{{channel}} {{measurement}} measurement failed: {{message}}", sweepInvalid: "Measurement sweep contains invalid results: {{valid}} valid, {{invalid}} invalid.", triggerWaitTimedOut: "Trigger wait timed out.", captureTriggerTimedOut: "Trigger wait timed out; waveform was not captured.", triggerWaitFailed: "Trigger wait failed.", reportedInstrumentError: "The instrument reported an error.", workflowInstrumentError: "The instrument reported an error while the workflow was running.", planned: "Planned", instrumentError: "Instrument error", integrate: "Integrate", fftPhase: "FFT phase", fftZoom: "Zoom",
          },
          "zh-TW": {
            identify: "\u8b80\u53d6\u88dd\u7f6e\u8cc7\u8a0a", run: "\u57f7\u884c", screenshot: "\u64f7\u53d6\u756b\u9762", capture: "\u64f7\u53d6\u6ce2\u5f62", listResources: "\u5217\u51fa\u8cc7\u6e90", completed: "\u5b8c\u6210", failed: "\u5931\u6557", queued: "\u6392\u968a\u4e2d", running: "\u57f7\u884c\u4e2d", cancelled: "\u5df2\u53d6\u6d88",
            queuedSummary: "\u7b49\u5f85\u57f7\u884c", runningSummary: "\u6b63\u5728\u57f7\u884c\u6307\u4ee4", completedSummary: "\u6307\u4ee4\u5df2\u6210\u529f\u5b8c\u6210", screenshotCaptured: "\u756b\u9762\u5df2\u64f7\u53d6", resourceNone: "\u627e\u4e0d\u5230\u8cc7\u6e90", resourceMany: "\u627e\u5230 4 \u500b\u8cc7\u6e90",
            serial: "\u5e8f\u865f {{serial}}", firmware: "\u97cc\u9ad4 {{firmware}}", empty: "\u5c1a\u672a\u57f7\u884c\u6307\u4ee4\u3002",
            period: "Period", phase: "Phase", vpp: "Vp-p", channel1: "\u901a\u9053 1", channel2: "\u901a\u9053 2",
            measurement: "Measurement", channel: "Channel", referenceChannel: "Reference channel", value: "Value", unit: "Unit", status: "Status", result: "Result", plannedScpi: "Planned SCPI",
            summary: "\u6458\u8981", channels: "\u901a\u9053", actualPoints: "\u5be6\u969b\u9ede\u6578", format: "\u683c\u5f0f", files: "\u6a94\u6848",
            captureCompleted: "\u6ce2\u5f62\u64f7\u53d6\u5b8c\u6210", capturePoints: "{{actual}} \u9ede\uff08\u8981\u6c42 {{requested}} \u9ede\uff09", capturePointsPerChannel: "{{actual}}\uff08\u6bcf\u901a\u9053\u8981\u6c42 {{requested}} \u9ede\uff09", outputFileCount: "{{count}} \u500b\u8f38\u51fa\u6a94\u6848", waveformReadTimedOut: "\u8b80\u53d6\u6ce2\u5f62\u8cc7\u6599\u903e\u6642\u3002\u5100\u5668\u76ee\u524d\u53ef\u80fd\u6c92\u6709\u53ef\u7528\u7684\u6ce2\u5f62\u8cc7\u6599\uff0c\u6216\u672a\u5728\u6642\u9593\u5167\u56de\u61c9\uff1b\u8acb\u78ba\u8a8d\u6240\u9078\u901a\u9053\u5df2\u958b\u555f\u4e14\u5df2\u5b8c\u6210\u6709\u6548\u64f7\u53d6\u5f8c\u518d\u8a66\u4e00\u6b21\u3002",
            validCount: "Valid count", invalidCount: "Invalid count", errorCount: "Error count", valid: "Valid", invalid: "Invalid", error: "Error",
            noValidStatus: "\u7121\u6548\u91cf\u6e2c\u503c", noValidSummary: "\u7121\u6548\u91cf\u6e2c\u503c", measurementTimedOut: "{{channel}} {{measurement}} \u91cf\u6e2c\u67e5\u8a62\u903e\u6642\u3002", measurementFailed: "{{channel}} {{measurement}} \u91cf\u6e2c\u5931\u6557\u3002", measurementFailedWithReason: "{{channel}} {{measurement}} \u91cf\u6e2c\u5931\u6557\uff1a{{message}}", sweepInvalid: "\u91cf\u6e2c\u6383\u63cf\u5305\u542b\u7121\u6548\u7d50\u679c\uff1a{{valid}} \u7b46\u6709\u6548\uff0c{{invalid}} \u7b46\u7121\u6548\u3002", triggerWaitTimedOut: "\u7b49\u5f85\u89f8\u767c\u903e\u6642\u3002", captureTriggerTimedOut: "\u7b49\u5f85\u89f8\u767c\u903e\u6642\uff0c\u672a\u64f7\u53d6\u6ce2\u5f62\u3002", triggerWaitFailed: "\u7b49\u5f85\u89f8\u767c\u5931\u6557\u3002", reportedInstrumentError: "\u5100\u5668\u56de\u5831\u932f\u8aa4\u3002", workflowInstrumentError: "\u5de5\u4f5c\u6d41\u7a0b\u57f7\u884c\u671f\u9593\uff0c\u5100\u5668\u56de\u5831\u932f\u8aa4\u3002", planned: "\u5df2\u898f\u5283", instrumentError: "\u5100\u5668\u932f\u8aa4", integrate: "\u7a4d\u5206", fftPhase: "FFT \u76f8\u4f4d", fftZoom: "\u7e2e\u653e\u8996\u7a97",
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
                                    : key === "results.summary.captureCompleted" ? locale.captureCompleted
                                      : key === "results.summary.capturePoints" ? locale.capturePoints
                                        : key === "results.summary.capturePointsPerChannel" ? locale.capturePointsPerChannel
                                          : key === "results.summary.outputFileCount" ? locale.outputFileCount
                                            : key === "results.summary.waveformReadTimedOut" ? locale.waveformReadTimedOut
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
                                                     : key === "results.field.summary" ? locale.summary
                                                       : key === "results.field.channels" ? locale.channels
                                                         : key === "results.field.actual_points" ? locale.actualPoints
                                                           : key === "results.field.format" ? locale.format
                                                             : key === "results.field.files" ? locale.files
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
                                   : key === "results.summary.measurementTimedOut" ? locale.measurementTimedOut
                                     : key === "results.summary.measurementFailed" ? locale.measurementFailed
                                       : key === "results.summary.measurementFailedWithReason" ? locale.measurementFailedWithReason
                                         : key === "results.summary.measureSweepInvalid" ? locale.sweepInvalid
                                           : key === "results.summary.triggerWaitTimedOut" ? locale.triggerWaitTimedOut
                                             : key === "results.summary.captureTriggerTimedOut" ? locale.captureTriggerTimedOut
                                               : key === "results.summary.triggerWaitFailed" ? locale.triggerWaitFailed
                                                 : key === "results.summary.instrumentError" ? locale.reportedInstrumentError
                                                   : key === "results.summary.workflowInstrumentError" ? locale.workflowInstrumentError
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
          "results.field.measurement", "results.field.summary", "results.field.channels", "results.field.actual_points", "results.field.format", "results.field.files", "results.field.channel", "results.field.reference_channel", "results.field.value", "results.field.unit", "results.field.status", "results.field.valid_count", "results.field.invalid_count", "results.field.error_count", "results.field.result", "results.field.planned_scpi",
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
        assert.equal(rowTexts()[0][2], "Waveform capture completed");

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
        // Invalid sentinel with real system error must use the instrument error
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("invalid-measure-system-error-job", "measure", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: { item: "vpp", channel: 1, valid: false, reason: "invalid measurement sentinel", value: null, raw_value: "+99E+36", unit: "V" }, system_error: { code: -113, is_error: true, message: "Undefined header" } },
        }), detail);
        assert.equal(summary.children[0].children[1].className, "badge badge-failed");
        assert.equal(summary.children[0].children[2].textContent, "Undefined header");
        assert.equal(detail.children[0].className, "error-block");
        // Generic failed job still shows error block
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("generic-failed-job", "measure", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { result: { item: "vpp", channel: 1, valid: true, value: 1.2 } },
        }), detail);
        assert.equal(summary.children[0].children[1].className, "badge badge-failed");
        assert.equal(detail.children[0].className, "error-block");

        // Structured command failures should take precedence over the generic job error
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("sweep-timeout", "measure-sweep", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: {
            measurements: [{ item: "vpp", channel: 1, reference_channel: null, valid: false, reason: "VISA query failed", error: { type: "VisaBackendError", message: "VISA query failed for ':MEASure:VPP? CHANnel1': VI_ERROR_TMO (-1073807339): Timeout expired before operation completed." } }],
            summary: { valid_count: 0, invalid_count: 0, error_count: 1 },
          } },
        }), detail);
        assert.equal(rowTexts()[0][2], "Channel 1 Vp-p measurement timed out.");
        assert.doesNotMatch(rowTexts()[0][2], /VISA|SCPI|VI_ERROR_TMO/);

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("sweep-invalid", "measure-sweep", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: {
            measurements: [{ item: "vpp", channel: 2, valid: false, reason: "invalid measurement sentinel", error: null }],
            summary: { valid_count: 15, invalid_count: 1, error_count: 0 },
          } },
        }), detail);
        assert.equal(rowTexts()[0][2], "Measurement sweep contains invalid results: 15 valid, 1 invalid.");

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("single-wait-timeout", "single-wait", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: { outcome: "timeout", timed_out: true, capture_block_reason: "timeout", error: null } },
        }), detail);
        assert.equal(rowTexts()[0][2], "Trigger wait timed out.");

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("capture-timeout", "capture", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: { files: [], trigger: { outcome: "timeout", timed_out: true, capture_allowed: false, capture_block_reason: "timeout", error: null } } },
        }), detail);
        assert.equal(rowTexts()[0][2], "Trigger wait timed out; waveform was not captured.");

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("capture-trigger-error", "capture", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: { files: [], trigger: { outcome: "unknown", timed_out: false, capture_allowed: false, capture_block_reason: "unknown", error: "configured query failure" } }, system_error: { code: -113, is_error: true, message: "Undefined header" } },
        }), detail);
        assert.equal(rowTexts()[0][2], "configured query failure");

        const rawWaveformTimeout = "VisaBackendError: VISA query failed for ':WAVeform:PREamble?': VI_ERROR_TMO (-1073807339): Timeout expired before operation completed.";
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("capture-waveform-timeout", "capture", "failed", {
          error: rawWaveformTimeout,
        }), detail);
        assert.equal(rowTexts()[0][2], "Waveform data read timed out. The instrument may not have usable waveform data, or it did not respond in time. Confirm the selected channel is enabled and an acquisition has completed, then try again.");
        assert.doesNotMatch(rowTexts()[0][2], /VISA|SCPI|VI_ERROR_TMO/);
        assert.equal(detail.children[0].textContent, rawWaveformTimeout);

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("batch-waveform-timeout", "capture-batch", "failed", {
          error: `_OperationError: ${rawWaveformTimeout}`,
        }), detail);
        assert.equal(rowTexts()[0][2], "Waveform data read timed out. The instrument may not have usable waveform data, or it did not respond in time. Confirm the selected channel is enabled and an acquisition has completed, then try again.");
        assert.doesNotMatch(rowTexts()[0][2], /VISA|SCPI|VI_ERROR_TMO/);

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("outer-system-error", "capture-batch", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: { status: "instrument_error" }, system_error: { code: -113, is_error: true, message: "Undefined header" } },
        }), detail);
        assert.equal(rowTexts()[0][2], "The instrument reported an error while the workflow was running.");

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("root-error-precedence", "capture", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: { error: { message: "Root capture failure" }, files: [], trigger: { outcome: "timeout", timed_out: true, capture_allowed: false, capture_block_reason: "timeout", error: null } }, system_error: { code: -113, is_error: true, message: "Undefined header" } },
        }), detail);
        assert.equal(rowTexts()[0][2], "Root capture failure");

        globalThis.testLocale = "zh-TW";
        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("capture-waveform-timeout-zh", "capture", "failed", {
          error: rawWaveformTimeout,
        }), detail);
        assert.equal(rowTexts()[0][2], "\u8b80\u53d6\u6ce2\u5f62\u8cc7\u6599\u903e\u6642\u3002\u5100\u5668\u76ee\u524d\u53ef\u80fd\u6c92\u6709\u53ef\u7528\u7684\u6ce2\u5f62\u8cc7\u6599\uff0c\u6216\u672a\u5728\u6642\u9593\u5167\u56de\u61c9\uff1b\u8acb\u78ba\u8a8d\u6240\u9078\u901a\u9053\u5df2\u958b\u555f\u4e14\u5df2\u5b8c\u6210\u6709\u6548\u64f7\u53d6\u5f8c\u518d\u8a66\u4e00\u6b21\u3002");
        assert.doesNotMatch(rowTexts()[0][2], /VISA|SCPI|VI_ERROR_TMO/);

        api.renderEmpty(summary, detail);
        api.renderJob(summary, makeJob("single-wait-timeout-zh", "single-wait", "failed", {
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: { outcome: "timeout", timed_out: true, capture_block_reason: "timeout", error: null } },
        }), detail);
        assert.equal(rowTexts()[0][2], "\u7b49\u5f85\u89f8\u767c\u903e\u6642\u3002");

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

        const fftMagnitude = new FakeNode("div");
        api.renderWorkspaceResult(fftMagnitude, makeJob("fft", "fft", "completed", {
          result: { result: { fft: {
            operation: "FFT",
            operation_canonical: "fft",
            units: "DEC",
            units_canonical: "decibel",
            window: "HANN",
            window_canonical: "hanning",
          } } },
        }));
        const magnitudeValues = fieldTexts(fftMagnitude).map((field) => field[0]);
        assert.equal(magnitudeValues.length, 4);
        assert.ok(magnitudeValues.includes("FFT"));
        assert.ok(magnitudeValues.includes("DEC"));
        assert.ok(magnitudeValues.includes("HANN"));
            assert.ok(!magnitudeValues.includes("decibel"));
            assert.ok(!magnitudeValues.includes("hanning"));
            assert.ok(!magnitudeValues.some((value) => value.includes("canonical")));

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
        const tableWrap = sweep.children[3];
        assert.equal(tableWrap.tagName, "DIV");
        assert.equal(tableWrap.className, "workspace-result-table-wrap");
        const table = tableWrap.children[0];
        assert.equal(table.tagName, "TABLE");
        assert.deepEqual(table.children[0].children[0].children.map((cell) => cell.textContent), [
          "Measurement", "Channel", "Reference channel", "Value", "Unit", "Status",
        ]);
        const rows = table.children[1].children.map(
          (row) => row.children.map((cell) => cell.textContent),
        );
        assert.deepEqual(rows, [
          ["Vp-p", "Channel 1", "—", "3.2", "V", "Valid"],
          ["Phase", "Channel 1", "Channel 2", "—", "deg", "Invalid"],
          ["Phase", "Channel 2", "Channel 1", "—", "deg", "Error"],
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
    script_path = tmp_path / "result-history-runtime.mjs"
    script_path.write_text(
        script.replace("process.argv[1]", "process.argv[2]"),
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["node", str(script_path), str(RESULTS_JS)],
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
          "results.field.summary": "Summary",
          "results.field.last_measurement": "Last measurement",
          "results.summary.measureUntilConditionMet": "Condition met after {{completed}} measurements",
          "results.summary.measureUntilCompleted": "{{completed}} measurements completed",
          "results.summary.captureBatchCompleted": "{{completed}} / {{total}} captures completed",
          "results.summary.captureUntilCompleted": "{{completed}} / {{total}} matching captures saved after {{captures}} acquisitions",
          "results.summary.captureMonitorCompleted": "{{completed}} / {{total}} captures monitored",
          "results.summary.measureLogCompletedKnown": "{{completed}} / {{total}} measurement rows recorded",
          "results.summary.measureLogCompleted": "{{completed}} measurement rows recorded",
          "results.summary.triggeredMeasureLoopCompleted": "{{completed}} / {{total}} triggered measurement cycles completed",
          "results.summary.triggeredCaptureSeriesCompleted": "{{completed}} / {{total}} triggered captures completed",
          "results.summary.sequenceCompleted": "{{completed}} / {{total}} step executions completed; {{loops}} loop(s), {{steps}} step(s)",
          "results.workflow.retention": "{{observed}} points observed per channel · {{retained}} retained · {{dropped}} dropped",
          "results.field.channels": "Channels",
          "results.field.actual_points": "Actual points",
          "results.field.format": "Format",
          "results.field.files": "Files",
          "results.summary.captureCompleted": "Waveform capture completed",
          "results.summary.capturePoints": "{{actual}} points (requested {{requested}})",
          "results.summary.capturePointsPerChannel": "{{actual}} (requested {{requested}} per channel)",
          "results.summary.outputFileCount": "{{count}} output files",
          "results.field.retention": "Retention",
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
          "results.field.summary": "\u6458\u8981",
          "results.field.channels": "\u901a\u9053",
          "results.field.actual_points": "\u5be6\u969b\u9ede\u6578",
          "results.field.format": "\u683c\u5f0f",
          "results.field.files": "\u6a94\u6848",
          "results.summary.captureCompleted": "\u6ce2\u5f62\u64f7\u53d6\u5b8c\u6210",
          "results.summary.capturePoints": "{{actual}} \u9ede\uff08\u8981\u6c42 {{requested}} \u9ede\uff09",
          "results.summary.capturePointsPerChannel": "{{actual}}\uff08\u6bcf\u901a\u9053\u8981\u6c42 {{requested}} \u9ede\uff09",
          "results.summary.outputFileCount": "{{count}} \u500b\u8f38\u51fa\u6a94\u6848",
          "results.field.last_measurement": "\u6700\u5f8c\u91cf\u6e2c",
          "results.summary.measureUntilConditionMet": "\u689d\u4ef6\u6210\u7acb\uff0c\u5171\u91cf\u6e2c {{completed}} \u6b21",
          "results.summary.measureUntilCompleted": "\u5df2\u5b8c\u6210 {{completed}} \u6b21\u91cf\u6e2c",
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

        // E: workflow results expose semantic summaries without nested payload dumps
        const workflowWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(workflowWorkspace, makeJob("measure-until", {
          status: "completed",
          channel: 1,
          item: "vpp",
          completed_count: 2,
          matched: true,
          termination_reason: "condition_met",
          last_measurement: { index: 2, value: "4", matched: true },
        }));
        const workflowText = workflowWorkspace.children.flatMap((field) =>
          field.children.map((node) => node.textContent)
        );
        assert(workflowText.some((text) => text.includes("Condition met after 2 measurements")));
        assert(workflowText.includes("Channel 1"));
        assert(workflowText.some((text) => text.includes("vpp: 4")));
        assert.equal(workflowText.some((text) => text.includes("Index: 2")), false);

        globalThis.testLocale = "zh-TW";
        const zhWorkflowWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(zhWorkflowWorkspace, makeJob("measure-until", {
          status: "completed",
          channel: 1,
          item: "vpp",
          completed_count: 2,
          matched: true,
          termination_reason: "condition_met",
          last_measurement: { index: 2, value: "4", matched: true },
        }));
        const zhWorkflowText = zhWorkflowWorkspace.children.flatMap((field) =>
          field.children.map((node) => node.textContent)
        );
        assert(zhWorkflowText.some((text) => text.includes("\u689d\u4ef6\u6210\u7acb")));
        assert(zhWorkflowText.includes("\u901a\u9053 1"));
        assert.equal(zhWorkflowText.some((text) => text.includes("\u7d22\u5f15")), false);

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
          channel: 1,
          item: "vpp",
          completed_count: 3,
          matched: true,
          termination_reason: "condition_met",
        }));
        const terminatedText = terminatedWorkflow.children.flatMap((field) =>
          field.children.map((node) => node.textContent)
        );
        assert(terminatedText.some((text) => text.includes("\u689d\u4ef6\u6210\u7acb")));
        assert.equal(terminatedText.some((text) => text.includes("condition_met")), false);
        globalThis.testLocale = "en";

        // F: every Workflow command keeps the workspace result compact
        const workflowCases = [
          ["capture-batch", {
            status: "completed", channels: [2], requested_count: 3, completed_count: 3,
            captures: [{ index: 1, csv: "waveform_0001.csv", metadata: "waveform_0001_meta.json",
              actual_points: { CH2: 985 }, system_error: { code: 0, message: "No error" } }],
            manifest_path: "data/manifest.json", scpi_log_path: "data/scpi.log",
          }, "3 / 3 captures completed"],
          ["capture-until", {
            status: "completed", channels: [1, 2], requested_count: 2, completed_count: 2,
            capture_count: 7, termination_reason: "condition_met",
          }, "2 / 2 matching captures saved after 7 acquisitions"],
          ["capture-monitor", {
            status: "completed", channels: [1], requested_count: 100, completed_count: 100,
            total_observed_points: 100000, retained_points: 25000, dropped_points: 75000,
            metrics: { CH1: { maximum: 1.0 } }, manifest_path: "data/monitor/manifest.json",
          }, "100 / 100 captures monitored"],
          ["measure-log", {
            status: "completed", channels: [1, 2], requested_count: 4, completed_rows: 4,
            last_measurement: { index: 4, values: { ch1_vpp: "2.5", ch2_frequency: "1000" } },
            csv_path: "data/measure.csv",
          }, "4 / 4 measurement rows recorded"],
          ["measure-until", {
            status: "completed", channel: 1, item: "vpp", completed_count: 2, matched: true,
            termination_reason: "condition_met", last_measurement: { index: 2, value: "4", matched: true },
          }, "Condition met after 2 measurements"],
          ["triggered-measure-loop", {
            status: "completed", channels: [1], requested_count: 3, completed_count: 3,
            last_measurement: { index: 3, values: { ch1_vpp: "2.1" } },
          }, "3 / 3 triggered measurement cycles completed"],
          ["triggered-capture-series", {
            status: "completed", channels: [1], requested_count: 2, completed_count: 2,
            cycles: [{ index: 1, csv: "capture_1.csv" }], manifest_path: "data/series/manifest.json",
          }, "2 / 2 triggered captures completed"],
          ["sequence", {
            status: "completed", loop_count: 2, step_count: 3, total_step_executions: 6,
            completed_step_executions: 6, files: [{ kind: "manifest", path: "manifest.json" }],
            steps: [{ step_index: 1, last_result: { value: 1 } }],
            manifest_path: "data/sequence/manifest.json", scpi_log_path: "data/sequence/scpi.log",
          }, "6 / 6 step executions completed; 2 loop(s), 3 step(s)"],
        ];
        for (const [command, payload, expectedSummary] of workflowCases) {
          const compact = new FakeNode("div");
          api.renderWorkspaceResult(compact, makeJob(command, payload));
          const visible = compact.children.flatMap((field) =>
            field.children.map((node) => node.textContent)
          );
          assert(visible.includes(expectedSummary), command + " semantic summary");
          const joined = visible.join(" | ");
          for (const forbidden of [
            "waveform_0001.csv", "waveform_0001_meta.json", "Actual points", "No error",
            "manifest.json", "scpi.log", "capture_1.csv", "last_result",
          ]) {
            assert.equal(joined.includes(forbidden), false, command + " leaked " + forbidden);
          }
          assert(visible.length <= 6, command + " result should stay compact");
        }

        globalThis.testLocale = "en";
        const captureWorkspace = new FakeNode("div");
        const capturePayload = {
          channels: [1],
          requested_points: 1000,
          actual_points: 992,
          format: "BYTE",
          files: [
            { kind: "csv", path: "2026-09-23-17-00-11.csv" },
            { kind: "metadata", path: "2026-09-23-17-00-11_meta.json" },
          ],
          captures: [{
            channel: 1, requested_points: 1000, actual_points: 992, format: "BYTE",
            preamble: { format_code: 0, x_increment: 0.000002016 },
            byte_order: null, unsigned: null,
          }],
        };
        const captureWorkspaceJob = makeJob("capture", capturePayload);
        api.renderWorkspaceResult(captureWorkspace, captureWorkspaceJob);
        const captureVisible = captureWorkspace.children.flatMap((field) =>
          field.children.map((node) => node.textContent)
        );
        assert.deepEqual(captureVisible, [
          "Waveform capture completed", "Summary",
          "Channel 1", "Channels",
          "992 points (requested 1000)", "Actual points",
          "BYTE", "Format",
          "2 output files", "Files",
        ]);
        assert.equal(captureVisible.some((text) => text.includes("Preamble")), false);
        assert.equal(captureVisible.some((text) => text.includes("x_increment")), false);
        assert.equal(captureVisible.some((text) => text.includes("2026-09-23")), false);

        const rawCaptureDetail = new FakeNode("div");
        const rawCaptureSummary = new FakeNode("div");
        api.renderJob(rawCaptureSummary, captureWorkspaceJob, rawCaptureDetail);
        assert(rawCaptureDetail.children[0].textContent.includes("2026-09-23-17-00-11.csv"));
        assert(rawCaptureDetail.children[0].textContent.includes("x_increment"));

        globalThis.testLocale = "zh-TW";
        const zhCaptureWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(zhCaptureWorkspace, captureWorkspaceJob);
        const zhCaptureVisible = zhCaptureWorkspace.children.flatMap((field) =>
          field.children.map((node) => node.textContent)
        );
        assert.deepEqual(zhCaptureVisible, [
          "\u6ce2\u5f62\u64f7\u53d6\u5b8c\u6210", "\u6458\u8981",
          "\u901a\u9053 1", "\u901a\u9053",
          "992 \u9ede\uff08\u8981\u6c42 1000 \u9ede\uff09", "\u5be6\u969b\u9ede\u6578",
          "BYTE", "\u683c\u5f0f",
          "2 \u500b\u8f38\u51fa\u6a94\u6848", "\u6a94\u6848",
        ]);

        globalThis.testLocale = "en";
        const durationOnlyLog = new FakeNode("div");
        api.renderWorkspaceResult(durationOnlyLog, makeJob("measure-log", {
          status: "completed", channels: [1], requested_count: null, completed_rows: 5,
        }));
        const durationOnlyText = durationOnlyLog.children.flatMap((field) =>
          field.children.map((node) => node.textContent)
        );
        assert(durationOnlyText.includes("5 measurement rows recorded"));
        assert.equal(durationOnlyText.join(" ").includes("null"), false);

        const rawWorkflowDetail = new FakeNode("div");
        const rawWorkflowSummary = new FakeNode("div");
        api.renderJob(
          rawWorkflowSummary,
          makeJob("capture-batch", workflowCases[0][1]),
          rawWorkflowDetail,
        );
        assert(rawWorkflowDetail.children[0].textContent.includes("waveform_0001.csv"));
        assert(rawWorkflowDetail.children[0].textContent.includes("waveform_0001_meta.json"));
        assert(rawWorkflowDetail.children[0].textContent.includes("No error"));

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


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_output_filename_stays_literal_in_zh_tw() -> None:
    english = LOCALE_EN_JS.read_text(encoding="utf-8")
    chinese = LOCALE_ZH_TW_JS.read_text(encoding="utf-8")
    assert '"enum.normal": "Normal"' in english
    assert '"enum.normal": "正常"' in chinese
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
        globalThis.testLocale = "zh-TW";

        const labels = {
          "command.serial-lister-export": "匯出串列 Lister",
          "status.completed": "完成",
          "results.summary.completed": "指令已成功完成",
          "field.output": "輸出檔名",
          "enum.normal": "正常",
        };

        const translate = (key, values = {}) => {
          const text = labels[key] || key;
          return Object.entries(values).reduce(
            (value, [name, replacement]) => value.replaceAll(`{{${name}}}`, String(replacement)),
            text,
          );
        };
        const hasTranslation = (key) => key in labels;
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
        const summary = new FakeNode("div");
        const detail = new FakeNode("div");
        const workspace = new FakeNode("div");
        const job = {
          job_id: "output-literal", command: "serial-lister-export", status: "completed",
          result: { exit_code: 0, result: { output: "normal" } },
        };

        api.renderJob(summary, job, detail);
        const row = summary.children[0].children.map((node) => node.textContent);
        assert.equal(row[2], "normal", "Result History summary must keep output filename literal");

        api.renderWorkspaceResult(workspace, job);
        const fields = workspace.children.map((field) => field.children.map((node) => node.textContent));
        assert.equal(fields.length, 1);
        assert.equal(fields[0][0], "normal", "Workspace Result must keep output filename literal");
        """
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(RESULTS_JS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_measure_sweep_table_has_horizontal_scroll_wrapper() -> None:
    source = RESULTS_JS.read_text(encoding="utf-8")
    styles = STYLES_CSS.read_text(encoding="utf-8")

    assert "workspace-result-table-wrap" in source
    assert ".workspace-result-table-wrap {" in styles
    wrapper = styles.split(".workspace-result-table-wrap {", 1)[1].split("}", 1)[0]
    assert "grid-column: 1 / -1;" in wrapper
    assert "overflow-x: auto;" in wrapper


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_measure_sweep_dry_run_uses_generic_planned_presentation() -> None:
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

        const labels = {
          "command.measure-sweep": "Multiple Measurements",
          "status.completed": "Completed",
          "results.status.planned": "Planned",
          "results.field.status": "Status",
          "results.field.planned_scpi": "Planned SCPI",
        };

        const translate = (key, values = {}) => {
          const text = labels[key] || key;
          return Object.entries(values).reduce(
            (value, [name, replacement]) => value.replaceAll(`{{${name}}}`, String(replacement)),
            text,
          );
        };
        const hasTranslation = (key) => key in labels;
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
        const workspace = new FakeNode("div");
        api.renderWorkspaceResult(workspace, {
          job_id: "sweep-dry-run", command: "measure-sweep", status: "completed",
          result: { exit_code: 0, result: {
            status: "planned",
            model_id: "keysight-dsox4024a",
            planned_scpi: [":MEASure:VPP? CHANnel1"],
            channels: [1],
            items: ["vpp"],
            pairs: [],
            pair_items: [],
            measurements: [],
            summary: { valid_count: 0, invalid_count: 0, error_count: 0 },
          } },
        }, { mode: "dry-run" });
        const text = JSON.stringify(workspace.children.map((field) => field.children.map((node) => node.textContent)));
        assert(text.includes("Planned"), "dry-run must show localized planned status");
        assert(text.includes("keysight-dsox4024a"), "dry-run must show model ID");
        assert(text.includes("Planned SCPI"), "dry-run must show planned SCPI");
        assert(text.includes(":MEASure:VPP? CHANnel1"), "dry-run must show planned commands");
        const hasTable = (node) => node.tagName === "TABLE"
          || (node.children || []).some((child) => hasTable(child));
        assert.equal(hasTable(workspace), false, "dry-run must not render the dedicated measurement table");
        """
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(RESULTS_JS)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


SYSTEM_SEMANTIC_WORKSPACE_HARNESS = r"""
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
        globalThis.testLocale = "zh-TW";
        const actualLocales = process.argv[2] && process.argv[3] ? {
          en: (await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(fs.readFileSync(process.argv[2], "utf8"))}`)).en,
          "zh-TW": (await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(fs.readFileSync(process.argv[3], "utf8"))}`)).zhTW,
        } : null;
        const labels = {
          "zh-TW": {
            noErrors: "未偵測到儀器錯誤。",
            queueClear: "儀器錯誤佇列目前為空。",
            detected: "偵測到 {{count}} 筆儀器錯誤：",
            readFailed: "無法讀取儀器錯誤佇列；未取得儀器錯誤碼。",
            maxReads: "已達最大讀取數；錯誤佇列中可能仍有未讀取項目。",
            statusNone: "目前沒有狀態旗標",
            messageAvailable: "訊息可用",
            running: "執行中",
            standardNone: "目前沒有標準事件旗標。",
            clearedNote: "本次讀取已清除標準事件狀態暫存器。",
            commandError: "命令錯誤",
            queryError: "查詢錯誤",
            opcComplete: "所有待處理的儀器操作皆已完成。",
            clearDone: "儀器狀態已清除。",
            optionsEmpty: "儀器未回報已安裝的選配功能。",
            memup: "記憶體升級",
            failed: "失敗",
            instrumentError: "儀器錯誤",
          },
          en: {
            noErrors: "No instrument errors detected.",
            queueClear: "The instrument error queue is clear.",
            detected: "Instrument errors detected ({{count}}):",
            readFailed: "Could not read the instrument error queue. No instrument error code was obtained.",
            maxReads: "The maximum read count was reached; additional errors may remain.",
            statusNone: "Currently no status flags",
            messageAvailable: "Message available",
            running: "Running / Scope executing",
            standardNone: "No standard event flags are set.",
            clearedNote: "This read cleared the Standard Event Status Register.",
            commandError: "Command Error",
            queryError: "Query Error",
            opcComplete: "All pending instrument operations are complete.",
            clearDone: "Instrument status was cleared.",
            optionsEmpty: "No installed instrument options were reported.",
            memup: "Memory Upgrade",
            failed: "Failed",
            instrumentError: "Instrument error",
          },
        };
        const keyFor = (key) => ({
          "results.system.checkError.noErrors": "noErrors",
          "results.system.checkError.queueClear": "queueClear",
          "results.system.checkError.detected": "detected",
          "results.system.checkError.readFailed": "readFailed",
          "results.system.checkError.maxReadsReached": "maxReads",
          "system.statusByte.none": "statusNone",
          "system.statusByte.messageAvailable": "messageAvailable",
          "system.operationStatus.running": "running",
          "system.standardEvent.none": "standardNone",
          "system.standardEvent.clearedNote": "clearedNote",
          "system.standardEvent.commandError": "commandError",
          "system.standardEvent.queryError": "queryError",
          "system.opc.complete": "opcComplete",
          "system.clearStatus.done": "clearDone",
          "system.options.empty": "optionsEmpty",
          "system.option.MEMUP": "memup",
          "status.failedJob": "failed",
          "results.status.instrument_error": "instrumentError",
        })[key];
        const translate = (key, values = {}) => {
          const name = keyFor(key);
          const text = actualLocales
            ? actualLocales[globalThis.testLocale][key] || key
            : name ? labels[globalThis.testLocale][name] : key;
          return Object.entries(values).reduce(
            (value, [field, replacement]) => value.replaceAll(`{{${field}}}`, String(replacement)),
            text,
          );
        };
        const hasTranslation = (key) => actualLocales
          ? key in actualLocales[globalThis.testLocale]
          : keyFor(key) !== undefined;
        const translateJobStatus = (status) => translate(
          { failed: "status.failedJob" }[status] || `status.${status}`,
        );
        globalThis.testTranslate = translate;
        globalThis.testHasTranslation = hasTranslation;
        globalThis.testTranslateJobStatus = translateJobStatus;

        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          "const translateJobStatus = globalThis.testTranslateJobStatus;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "").replace(/^export function /gm, "function ")
          + "\nglobalThis.resultApi = { renderJob, renderWorkspaceResult, renderDiagnosticsWorkspaceResult };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const api = globalThis.resultApi;
        const workspaceLines = (job) => {
          const workspace = new FakeNode("div");
          api.renderWorkspaceResult(workspace, job, { mode: "simulate" });
          return workspace.children.map((line) => line.children.map((node) => node.textContent).join(""));
        };
        const historyLine = (job) => {
          const summary = new FakeNode("div");
          api.renderJob(summary, job, new FakeNode("div"));
          const line = summary.children[0].children;
          return { badge: line[1].textContent, badgeClass: line[1].className, summary: line[2].textContent };
        };
        const completed = (command, result) => ({
          job_id: `job-${command}`, command, status: "completed",
          result: { exit_code: 0, result, artifacts: [] },
        });
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_system_semantic_workspace_results() -> None:
    english = LOCALE_EN_JS.read_text(encoding="utf-8")
    chinese = LOCALE_ZH_TW_JS.read_text(encoding="utf-8")
    for key, en_value, zh_value in (
        ("system.standardEvent.none", "No standard event flags are set.", "目前沒有標準事件旗標。"),
        ("system.standardEvent.commandError", "Command Error", "命令錯誤"),
        ("system.standardEvent.queryError", "Query Error", "查詢錯誤"),
        ("system.opc.complete", "All pending instrument operations are complete.", "所有待處理的儀器操作皆已完成。"),
        ("system.clearStatus.done", "Instrument status was cleared.", "儀器狀態已清除。"),
        ("system.options.empty", "No installed instrument options were reported.", "儀器未回報已安裝的選配功能。"),
        ("results.system.checkError.noErrors", "No instrument errors detected.", "未偵測到儀器錯誤。"),
        ("results.system.checkError.readFailed", "Could not read the instrument error queue. No instrument error code was obtained.", "無法讀取儀器錯誤佇列；未取得儀器錯誤碼。"),
    ):
        assert f'"{key}": "{en_value}"' in english, key
        assert f'"{key}": "{zh_value}"' in chinese, key
    script = textwrap.dedent(SYSTEM_SEMANTIC_WORKSPACE_HARNESS) + textwrap.dedent(
        r'''
        assert.deepEqual(
          workspaceLines(completed("check-error", {
            drain: true, max_reads: 20,
            entries: [{ code: 0, message: "No error", raw: '0,"No error"' }],
            system_error: { code: 0, message: "No error", raw: '0,"No error"' },
          })),
          ["未偵測到儀器錯誤。", "儀器錯誤佇列目前為空。"],
        );
        assert.deepEqual(
          workspaceLines(completed("system-status-byte", { value: 0, raw: "0", set_bits: [] })),
          ["目前沒有狀態旗標"],
        );
        assert.deepEqual(
          workspaceLines(completed("system-status-byte", { value: 24, raw: "24", set_bits: [4, 3] })),
          ["訊息可用; Bit 3"],
        );
        assert.deepEqual(
          workspaceLines(completed("system-operation-status", { value: 8, raw: "8", set_bits: [3, 99] })),
          ["執行中; Bit 99"],
        );
        assert.deepEqual(
          workspaceLines(completed("system-standard-event", { value: 0, raw: "0", set_bits: [] })),
          ["目前沒有標準事件旗標。", "本次讀取已清除標準事件狀態暫存器。"],
        );
        assert.deepEqual(
          workspaceLines(completed("system-standard-event", { value: 36, raw: "36", set_bits: [5, 2] })),
          ["命令錯誤; 查詢錯誤", "本次讀取已清除標準事件狀態暫存器。"],
        );
        assert.deepEqual(
          workspaceLines(completed("system-opc", { operation_complete: { complete: true, raw: "1" } })),
          ["所有待處理的儀器操作皆已完成。"],
        );
        assert.deepEqual(
          workspaceLines(completed("system-clear-status", { action: "system-clear-status" })),
          ["儀器狀態已清除。"],
        );
        assert.deepEqual(
          workspaceLines(completed("system-options", { raw: "0,0", options: ["0", "0"] })),
          ["儀器未回報已安裝的選配功能。"],
        );
        assert.deepEqual(
          workspaceLines(completed("system-options", { raw: "0,MEMUP,FPGAX", options: ["0", "MEMUP", "FPGAX"] })),
          ["記憶體升級 — MEMUP; FPGAX"],
        );
        const failedLines = workspaceLines({
          job_id: "job-check-error-direct", command: "check-error", status: "failed",
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: {
            drain: true, max_reads: 20,
            entries: [
              { code: -113, message: "Undefined header", raw: '-113,"Undefined header"' },
              { code: -222, message: "Data out of range", raw: '-222,"Data out of range"' },
              { code: 0, message: "No error", raw: '0,"No error"' },
            ],
            system_error: { code: 0, message: "No error", raw: '0,"No error"' },
          }, artifacts: [] },
        }).join("\n");
        assert.equal(failedLines.split("-113").length - 1, 1);
        assert.equal(failedLines.split("-222").length - 1, 1);

        globalThis.testLocale = "en";
        assert.deepEqual(
          workspaceLines(completed("check-error", {
            drain: true, max_reads: 20,
            entries: [{ code: 0, message: "No error", raw: '0,"No error"' }],
            system_error: { code: 0, message: "No error", raw: '0,"No error"' },
          })),
          ["No instrument errors detected.", "The instrument error queue is clear."],
        );
        assert.deepEqual(
          workspaceLines(completed("system-standard-event", { value: 0, raw: "0", set_bits: [] })),
          ["No standard event flags are set.", "This read cleared the Standard Event Status Register."],
        );
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
def test_workflow_failure_summaries_are_localized_and_semantic() -> None:
    script = textwrap.dedent(SYSTEM_SEMANTIC_WORKSPACE_HARNESS) + textwrap.dedent(
        r"""
        const genericJobError = "Core command returned a non-zero exit code.";
        const cases = [
          {
            command: "capture-batch",
            result: {
              status: "error", requested_count: 3, completed_count: 1,
              error: "could not write capture batch manifest C:/internal/path/manifest.json",
            },
            en: "Periodic capture failed after 1 / 3 captures.",
            zh: "批次擷取在完成 1 / 3 次後失敗。",
          },
          {
            command: "capture-until",
            result: {
              status: "error", requested_count: 1, completed_count: 0, capture_count: 8,
              timeout_seconds: 5, termination_reason: "condition_timeout",
              error: {
                type: "condition_timeout",
                message: "waveform condition did not collect all requested matches within 5 seconds",
              },
            },
            en: "Not enough waveform-condition matches were collected within 5 s; 0 / 1 matching captures were collected.",
            zh: "5 秒內未收集到足夠的符合條件波形；已收集 0 / 1 次。",
          },
          {
            command: "capture-monitor",
            result: {
              status: "error", requested_count: 5, completed_count: 2,
              error: { type: "OscilloscopeError", message: "capture monitor channel time axes are not aligned" },
            },
            en: "Capture monitor failed after 2 / 5 captures.",
            zh: "擷取監看在完成 2 / 5 次後失敗。",
          },
          {
            command: "measure-log",
            result: {
              status: "error", requested_count: 4, completed_rows: 2,
              error: "could not write measurement log output C:/internal/path/measurements.csv",
            },
            en: "Measurement logging failed after 2 / 4 rows.",
            zh: "量測記錄在完成 2 / 4 筆後失敗。",
          },
          {
            command: "measure-until",
            result: {
              status: "error", completed_count: 3, timeout_seconds: 5,
              termination_reason: "condition_timeout",
              error: { type: "condition_timeout", message: "measurement condition was not met within 5 seconds" },
            },
            en: "Measurement condition was not met within 5 s after 3 measurements.",
            zh: "5 秒內未達成量測條件；已完成 3 次量測。",
          },
          {
            command: "triggered-measure-loop",
            result: {
              status: "error", requested_count: 4, completed_count: 1,
              error: {
                type: "trigger_timeout", cycle_index: 2, outcome: "timeout",
                message: "trigger wait timed out in cycle 2",
              },
            },
            en: "Trigger wait timed out on cycle 2; 1 / 4 cycles were completed.",
            zh: "第 2 輪等待觸發逾時；已完成 1 / 4 輪。",
          },
          {
            command: "triggered-capture-series",
            result: {
              status: "error", requested_count: 3, completed_count: 0,
              error: {
                type: "trigger_timeout", cycle_index: 1, outcome: "timeout",
                message: "trigger wait timed out in cycle 1",
              },
            },
            en: "Trigger wait timed out on capture 1; 0 / 3 captures were completed.",
            zh: "第 1 次擷取等待觸發逾時；已完成 0 / 3 次擷取。",
          },
          {
            command: "sequence",
            result: {
              status: "error", total_step_executions: 6, completed_step_executions: 4,
              failed_step: {
                loop_index: 2, step_index: 2, action: "wait-trigger",
                error: { type: "step_error", message: "trigger wait ended with outcome timeout" },
              },
              error: "trigger wait ended with outcome timeout",
            },
            en: "Sequence stopped at loop 2, step 2 (Wait for trigger).",
            zh: "序列在第 2 輪、第 2 步（等待觸發）停止。",
          },
        ];

        for (const locale of ["en", "zh-TW"]) {
          globalThis.testLocale = locale;
          for (const item of cases) {
            const job = {
              job_id: `workflow-failure-${locale}-${item.command}`,
              command: item.command,
              status: "failed",
              error: genericJobError,
              result: { exit_code: 1, result: item.result, artifacts: [] },
            };
            const summary = historyLine(job).summary;
            assert.equal(summary, locale === "en" ? item.en : item.zh, `${locale} ${item.command}`);
            assert.equal(summary.includes(genericJobError), false);
            const rawMessage = typeof item.result.error === "string"
              ? item.result.error
              : item.result.error?.message;
            if (rawMessage) assert.equal(summary.includes(rawMessage), false);
          }

          const unstructured = {
            job_id: `workflow-unstructured-${locale}`,
            command: "sequence",
            status: "failed",
            error: "OscilloscopeError: internal execution detail",
            result: null,
          };
          assert.equal(
            historyLine(unstructured).summary,
            actualLocales[locale]["results.summary.workflowFailed"],
          );

          const instrumentFailure = {
            job_id: `workflow-instrument-${locale}`,
            command: "capture-monitor",
            status: "failed",
            error: genericJobError,
            result: {
              exit_code: 1,
              result: {
                status: "instrument_error", requested_count: 5, completed_count: 2,
                error: { type: "instrument_error", message: '-113,"Undefined header"' },
              },
              system_error: { code: -113, is_error: true, message: "Undefined header" },
              artifacts: [],
            },
          };
          assert.equal(
            historyLine(instrumentFailure).summary,
            actualLocales[locale]["results.summary.workflowInstrumentError"],
          );
        }
        """
    )
    completed = subprocess.run(
        [
            "node", "--input-type=module", "--eval", script,
            str(RESULTS_JS), str(LOCALE_EN_JS), str(LOCALE_ZH_TW_JS),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_doctor_pending_errors_guidance() -> None:
    script = textwrap.dedent(SYSTEM_SEMANTIC_WORKSPACE_HARNESS) + textwrap.dedent(
        r'''
        const genericError = "Core command returned a non-zero exit code.";
        const systemError = { code: -113, is_error: true, message: "Undefined header", raw: '-113,"Undefined header"' };
        const job = {
          job_id: "doctor-pending", command: "doctor", status: "failed", error: genericError,
          result: { exit_code: 1, result: { failure_reason: "preexisting_system_error" }, system_error: systemError, artifacts: [] },
        };
        const original = JSON.stringify(job);
        for (const locale of ["en", "zh-TW"]) {
          globalThis.testLocale = locale;
          const commandName = translate("command.system-clear-status");
          const expected = translate("diagnostics.doctorPendingErrors", { command: commandName });
          assert.notEqual(expected, "diagnostics.doctorPendingErrors");
          assert.notEqual(expected, genericError);
          assert.ok(expected.includes(commandName));
          assert.ok(!expected.includes("{{command}}"));
          const summary = new FakeNode("div");
          const detail = new FakeNode("div");
          const workspace = new FakeNode("div");
          api.renderJob(summary, { ...job, job_id: `doctor-pending-${locale}` }, detail);
          const row = summary.children[0].children;
          assert.equal(row[2].textContent, expected);
          assert.equal(row[1].className, "badge badge-failed");
          assert.equal(row[1].textContent, actualLocales[locale]["status.failedJob"]);
          api.renderDiagnosticsWorkspaceResult(workspace, job);
          assert.equal(workspace.children[0].className, "error-block");
          assert.equal(workspace.children[0].textContent, expected);
          const systemField = workspace.children.at(-1).children;
          assert.ok(systemField[0].textContent.includes("-113"));
          assert.ok(systemField[0].textContent.includes("Undefined header"));
          assert.equal(systemField[1].textContent, translate("results.field.system_error"));
          assert.equal(detail.children[0].className, "error-block");
          assert.equal(detail.children[0].textContent, genericError);
          assert.equal(detail.children[1].textContent, JSON.stringify(job.result, null, 2));
          assert.deepEqual(JSON.parse(detail.children[1].textContent).system_error, systemError);
          assert.equal(JSON.stringify(job), original);

          for (const error of [undefined, "Final Doctor check failed."]) {
            const finalOnly = {
              ...job, job_id: `doctor-final-${locale}-${error}`,
              result: { ...job.result, result: error ? { error } : {} },
            };
            assert.equal(historyLine(finalOnly).summary, error || genericError);
            api.renderDiagnosticsWorkspaceResult(workspace, finalOnly);
            assert.equal(workspace.children[0].textContent, error || genericError);
          }
          const nonDoctor = { ...job, job_id: `other-${locale}`, command: "smoke" };
          assert.equal(historyLine(nonDoctor).summary, genericError);
          api.renderDiagnosticsWorkspaceResult(workspace, nonDoctor);
          assert.equal(workspace.children[0].textContent, genericError);
          const completedDoctor = { ...job, job_id: `doctor-completed-${locale}`, status: "completed" };
          assert.notEqual(historyLine(completedDoctor).summary, expected);
          api.renderDiagnosticsWorkspaceResult(workspace, completedDoctor);
          assert.ok(workspace.children.every((node) => node.className !== "error-block"));
        }
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(RESULTS_JS), str(LOCALE_EN_JS), str(LOCALE_ZH_TW_JS)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_check_error_failure_distinction() -> None:
    script = textwrap.dedent(SYSTEM_SEMANTIC_WORKSPACE_HARNESS) + textwrap.dedent(
        r'''
        const failedWithErrors = {
          job_id: "job-check-error-errors", command: "check-error", status: "failed",
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: {
            drain: true, max_reads: 20,
            entries: [
              { code: -113, message: "Undefined header", raw: '-113,"Undefined header"' },
              { code: -222, message: "Data out of range", raw: '-222,"Data out of range"' },
              { code: 0, message: "No error", raw: '0,"No error"' },
            ],
            system_error: { code: 0, message: "No error", raw: '0,"No error"' },
          }, artifacts: [] },
        };
        const found = historyLine(failedWithErrors);
        assert.equal(found.badge, "儀器錯誤");
        assert.ok(found.badgeClass.includes("badge-failed"));
        assert.ok(found.summary.includes("偵測到 2 筆儀器錯誤"));
        assert.ok(found.summary.includes("-113 — Undefined header"));
        assert.equal(found.summary.includes("non-zero exit code"), false);

        const unreadable = {
          job_id: "job-check-error-unreadable", command: "check-error", status: "failed",
          error: "VI_ERROR_TMO: timeout",
          result: null, artifacts: [],
        };
        const missing = historyLine(unreadable);
        assert.equal(missing.badge, "失敗");
        assert.equal(missing.summary, "無法讀取儀器錯誤佇列；未取得儀器錯誤碼。");

        globalThis.testLocale = "en";
        const foundEn = historyLine({ ...failedWithErrors, job_id: "job-check-error-errors-en" });
        assert.equal(foundEn.badge, "Instrument error");
        assert.ok(foundEn.summary.includes("Instrument errors detected (2):"));
        const singleEn = historyLine({
          job_id: "job-check-error-single-en", command: "check-error", status: "failed",
          error: "Core command returned a non-zero exit code.",
          result: { exit_code: 1, result: {
            drain: true, max_reads: 20,
            entries: [
              { code: -113, message: "Undefined header", raw: '-113,"Undefined header"' },
              { code: 0, message: "No error", raw: '0,"No error"' },
            ],
            system_error: { code: 0, message: "No error", raw: '0,"No error"' },
          }, artifacts: [] },
        });
        assert.ok(singleEn.summary.includes("Instrument errors detected (1):"));
        assert.equal(singleEn.summary.includes("1 instrument errors"), false);
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
def test_segmented_capture_workspace_result_labels_are_localized() -> None:
    english = LOCALE_EN_JS.read_text(encoding="utf-8")
    chinese = LOCALE_ZH_TW_JS.read_text(encoding="utf-8")
    expected = {
        "results.field.output_dir": ("Output directory", "輸出目錄"),
        "results.field.manifest_path": ("Manifest path", "Manifest 路徑"),
        "results.field.scpi_log_path": ("SCPI log path", "SCPI 記錄路徑"),
        "results.field.vertical_unit": ("Vertical unit", "垂直單位"),
        "results.field.requested_segments": ("Requested segments", "要求的分段數"),
        "results.field.configured_segments": ("Configured segments", "設定的分段數"),
        "results.field.acquired_segments": ("Acquired segments", "已擷取的分段數"),
        "results.field.exported_segments": ("Exported segments", "已匯出的分段數"),
        "results.field.initial_mode": ("Initial mode", "初始模式"),
        "results.field.final_mode": ("Final mode", "最終模式"),
        "results.field.polling": ("Polling", "輪詢"),
        "results.field.command": ("Command", "指令"),
        "results.field.runtime_behavior": ("Runtime behavior", "執行期間行為"),
        "results.field.error": ("Error", "錯誤"),
    }
    for key, (en_value, zh_value) in expected.items():
        assert f'"{key}": "{en_value}"' in english, key
        assert f'"{key}": "{zh_value}"' in chinese, key
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
          "command.segmented-capture": "Segmented Capture",
          "results.field.operation": "Operation",
          "results.field.status": "Status",
          "results.status.completed": "Completed",
          "results.field.output_dir": "Output directory",
          "results.field.manifest_path": "Manifest path",
          "results.field.scpi_log_path": "SCPI log path",
          "results.field.channel": "Channel",
          "results.field.vertical_unit": "Vertical unit",
          "results.field.requested_segments": "Requested segments",
          "results.field.configured_segments": "Configured segments",
          "results.field.acquired_segments": "Acquired segments",
          "results.field.exported_segments": "Exported segments",
          "field.points": "Points",
          "field.format": "Format",
          "results.field.initial_mode": "Initial mode",
          "results.field.final_mode": "Final mode",
          "results.field.polling": "Polling",
          "results.field.command": "Command",
          "results.field.timeout_ms": "Timeout ms",
          "results.field.poll_interval_ms": "Poll interval ms",
          "results.field.runtime_behavior": "Runtime behavior",
          "enum.realtime": "Realtime",
          "enum.segmented": "Segmented",
        };
        const zhLabels = {
          "command.segmented-capture": "分段擷取",
          "results.field.operation": "操作",
          "results.field.status": "狀態",
          "results.status.completed": "已完成",
          "results.field.output_dir": "輸出目錄",
          "results.field.manifest_path": "Manifest 路徑",
          "results.field.scpi_log_path": "SCPI 記錄路徑",
          "results.field.channel": "通道",
          "results.field.vertical_unit": "垂直單位",
          "results.field.requested_segments": "要求的分段數",
          "results.field.configured_segments": "設定的分段數",
          "results.field.acquired_segments": "已擷取的分段數",
          "results.field.exported_segments": "已匯出的分段數",
          "field.points": "點數",
          "field.format": "格式",
          "results.field.initial_mode": "初始模式",
          "results.field.final_mode": "最終模式",
          "results.field.polling": "輪詢",
          "results.field.command": "指令",
          "results.field.timeout_ms": "逾時時間（毫秒）",
          "results.field.poll_interval_ms": "輪詢間隔（毫秒）",
          "results.field.runtime_behavior": "執行期間行為",
          "enum.realtime": "即時",
          "enum.segmented": "分段",
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
        const payload = {
          operation: "segmented-capture",
          status: "completed",
          output_dir: "data/segmented_captures/2026-09-21T00-00-00",
          manifest_path: "data/segmented_captures/2026-09-21T00-00-00/manifest.json",
          scpi_log_path: "data/segmented_captures/2026-09-21T00-00-00/scpi.log",
          channel: 1,
          vertical_unit: "V",
          requested_segments: 5,
          configured_segments: 5,
          acquired_segments: 5,
          exported_segments: 5,
          points: 1000,
          format: "BYTE",
          initial_mode: "realtime",
          final_mode: "segmented",
          polling: {
            command: ":OPERegister:CONDition?",
            timeout_ms: 30000,
            poll_interval_ms: 100,
            runtime_behavior: "require two consecutive RUN-clear and RUI-enabled samples",
          },
        };
        const job = {
          job_id: "segmented-capture-job", command: "segmented-capture", status: "completed",
          result: { exit_code: 0, result: payload },
        };
        const fieldTexts = (container) => container.children.map(
          (field) => field.children.map((node) => node.textContent),
        );

        const workspace = new FakeNode("div");
        api.renderWorkspaceResult(workspace, job);
        const labels = fieldTexts(workspace).map(([content, label]) => label);
        for (const label of [
          "Operation", "Status", "Output directory", "Manifest path", "SCPI log path",
          "Channel", "Vertical unit", "Requested segments", "Configured segments",
          "Acquired segments", "Exported segments", "Points", "Format",
          "Initial mode", "Final mode", "Polling",
        ]) {
          assert.ok(labels.includes(label), `missing en label ${label}`);
        }

        globalThis.testLocale = "zh-TW";
        const zhWorkspace = new FakeNode("div");
        api.renderWorkspaceResult(zhWorkspace, job);
        const zhFields = fieldTexts(zhWorkspace);
        const zhLabelsRendered = zhFields.map(([content, label]) => label);
        const zhContents = zhFields.map(([content, label]) => content);
        for (const fallback of [
          "Output dir", "Manifest path", "Scpi log path", "Vertical unit",
          "Requested segments", "Configured segments", "Acquired segments",
          "Exported segments", "Initial mode", "Final mode", "Polling",
          "Runtime behavior", "Command",
        ]) {
          assert.ok(!zhLabelsRendered.includes(fallback), `zh-TW fallback label ${fallback}`);
        }
        for (const label of [
          "操作", "狀態", "輸出目錄", "Manifest 路徑", "SCPI 記錄路徑",
          "通道", "垂直單位", "要求的分段數", "設定的分段數",
          "已擷取的分段數", "已匯出的分段數", "點數", "格式",
          "初始模式", "最終模式", "輪詢",
        ]) {
          assert.ok(zhLabelsRendered.includes(label), `missing zh-TW label ${label}`);
        }
        assert.ok(zhContents.includes("data/segmented_captures/2026-09-21T00-00-00/manifest.json"), "manifest path verbatim");
        assert.ok(zhContents.some((text) => text.includes(":OPERegister:CONDition?")), "nested polling command verbatim");
        assert.ok(zhContents.some((text) => text.includes("require two consecutive RUN-clear")), "nested runtime behavior keeps technical wording");
        assert.ok(zhContents.includes("V"), "vertical unit verbatim");
        assert.ok(zhContents.includes("分段擷取"), "operation value localized");
        assert.ok(zhContents.includes("即時"), "initial mode value localized");
        assert.ok(zhContents.includes("分段"), "final mode value localized");
        assert.ok(zhContents.includes("已完成"), "status value localized");
        assert.ok(zhContents.includes("BYTE"), "format value keeps presentation");
        """
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(RESULTS_JS)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
