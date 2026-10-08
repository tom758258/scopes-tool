from __future__ import annotations

import shutil
import subprocess
import textwrap

import pytest

from tests.webui._frontend_state_test_support import (
    STATIC_ROOT,
    read_static,
    extract_function,
    extract_function_declaration,
)

def extract_css_rule(source: str, selector: str) -> str:
    start = source.index(selector)
    body_start = source.index("{", start)
    end = source.index("}", body_start)
    return source[body_start:end + 1]

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_live_data_engineering_formatter_uses_readable_si_units() -> None:
    live_data_path = STATIC_ROOT / "live-data.js"
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    assert '"live_data.type.glitch": "脈波寬度"' in chinese
    assert '"live_data.type.runt": "最窄脈波"' in chinese
    assert '"live_data.source.line": "線路"' in chinese
    assert '"live_data.mode.segmented": "分段記憶"' in chinese
    assert '"live_data.mode.realtime": "即時"' in chinese
    assert '"live_data.mode.unknown": "未知"' in chinese
    assert '"live_data.statusWithLastUpdate": "{{status}} - last update {{time}}"' in english
    assert '"live_data.statusWithLastUpdate": "{{status}} - 上次更新 {{time}}"' in chinese
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        globalThis.document = {
          createElement: (tag) => ({
            tagName: tag, className: "", textContent: "", dataset: {}, children: [],
            append: function(...kids) { this.children.push(...kids); },
          }),
        };
        const source = fs.readFileSync(process.argv[1], "utf8")
          .replaceAll("export function ", "function ")
          + "\nglobalThis.liveDataApi = { formatEngineering, renderInstrumentSummary, liveStateText };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { formatEngineering, renderInstrumentSummary, liveStateText } = globalThis.liveDataApi;

        assert.equal(formatEngineering(0.5, "V", { perDivision: true }), "500 mV/div");
        assert.equal(formatEngineering(2, "A", { perDivision: true }), "2.00 A/div");
        assert.equal(formatEngineering(-0.0024, "s", { signed: true }), "-2.40 ms");
        assert.equal(formatEngineering(null, "V"), "—");
        assert.equal(formatEngineering(undefined, "V"), "—");
        assert.equal(formatEngineering(0, "V", { signed: true }), "+0.00 V");

        const node = () => ({
          hidden: false,
          textContent: "",
          title: "",
          children: [],
          append: function(...children) { this.children.push(...children); },
          replaceChildren: function(...children) { this.children = [...children]; },
        });
        const elements = {
          status: node(), channels: node(), timebaseScale: node(), timebasePosition: node(),
          triggerType: node(), triggerSource: node(), triggerLevel: node(), triggerSlope: node(),
          triggerSweep: node(), acquisitionMode: node(), acquisitionType: node(), acquisitionSegmentedHint: node(),
        };
        const translate = (key) => ({
          "live_data.acquisition_type.normal": "Normal",
          "live_data.type.glitch": "\u8108\u6ce2\u5bec\u5ea6",
          "live_data.source.line": "\u7dda\u8def",
          "live_data.mode.segmented": "\u5206\u6bb5\u8a18\u61b6",
          "enum.channel1": "\u901a\u9053 1",
          "enum.channel2": "\u901a\u9053 2",
          "enum.channel4": "\u901a\u9053 4",
        })[key] || key;
        renderInstrumentSummary(elements, {
          channels: [],
          timebase: {},
          trigger: { type: "glitch", source: "line" },
          acquisition: { mode: "segmented", type: "normal" },
        }, translate);
        assert.equal(elements.triggerType.textContent, "\u8108\u6ce2\u5bec\u5ea6");
        assert.notEqual(elements.triggerType.textContent, "Glitch");
        assert.equal(elements.triggerSource.textContent, "\u7dda\u8def");
        assert.equal(elements.acquisitionMode.textContent, "\u5206\u6bb5\u8a18\u61b6");
        assert.equal(elements.acquisitionType.textContent, "Normal");
        assert.equal(elements.acquisitionSegmentedHint.hidden, false);
        renderInstrumentSummary(elements, {
          channels: [],
          timebase: {},
          trigger: { type: "glitch", source: "line" },
          acquisition: { mode: "realtime" },
        }, translate);
        assert.equal(elements.acquisitionSegmentedHint.hidden, true);

        const statusTranslate = (key, values = {}) => {
          const messages = {
            "live_data.ready": "Ready",
            "live_data.statusWithLastUpdate": "{{status}} - last update {{time}}",
          };
          let text = messages[key] || key;
          Object.entries(values).forEach(([name, value]) => {
            text = text.replaceAll(`{{${name}}}`, String(value));
          });
          return text;
        };
        const updatedAt = "2026-09-23T03:04:05+00:00";
        const expectedTime = new Date(updatedAt).toLocaleTimeString();
        assert.equal(
          liveStateText("live_data.ready", updatedAt, statusTranslate),
          `Ready - last update ${expectedTime}`,
        );
        assert.equal(liveStateText("live_data.ready", null, statusTranslate), "Ready");
        assert.equal(liveStateText("live_data.ready", "not-a-timestamp", statusTranslate), "Ready");

        renderInstrumentSummary(elements, {
          channels: [
            { channel: 2, display: true, scale: 1, offset: 0, units: "volt" },
            { channel: 4, display: false, scale: 1, offset: 0, units: "volt" },
          ],
          timebase: {},
          trigger: {},
          acquisition: { mode: "realtime" },
        }, translate);
        const channelCards = elements.channels.children;
        assert.equal(channelCards.length, 2);
        assert.equal(channelCards[0].dataset.channel, "2");
        assert.equal(channelCards[1].dataset.channel, "4");
        assert.equal(channelCards[0].children[0].children[0].textContent, "\u901a\u9053 2");
        assert.equal(channelCards[1].children[0].children[0].textContent, "\u901a\u9053 4");

        renderInstrumentSummary(elements, {
          channels: [],
          timebase: {},
          trigger: { source: "analog-channel", source_channel: 1 },
          acquisition: { mode: "realtime" },
        }, translate);
        assert.equal(elements.triggerSource.textContent, "\u901a\u9053 1");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(live_data_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_live_data_snapshot_updated_at_lifecycle() -> None:
    app_source = read_static("app.js")
    sync_context = extract_function_declaration(app_source, "function syncLiveDataContext()")
    refresh_snapshot = extract_function_declaration(app_source, "async function refreshLiveDataSnapshot()")
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";

        let liveDataSnapshot = { contextKey: null, value: null, error: null, loading: false, updatedAt: null };
        let currentKey = "live|resource|model";
        function liveDataContextKey() { return currentKey; }
        const isExecutionBusy = () => false;
        const commandAvailable = () => true;
        const renderLiveData = () => {};
        const updateAvailability = () => {};
        const translate = (key) => key;
        let nextJob = null;
        let releasePending = null;
        async function executeCommand() {
          if (releasePending) await releasePending.promise;
          return nextJob;
        }
        '''
    ) + sync_context + "\n" + refresh_snapshot + textwrap.dedent(
        r'''
        const snapshot1 = { acquisition: { mode: "realtime" } };
        const snapshot2 = { acquisition: { mode: "segmented" } };
        const completedJob = (tag, snapshot) => ({ status: "completed", finished_at: tag, result: { live_data: snapshot } });

        currentKey = "A";
        nextJob = completedJob("T1", snapshot1);
        await refreshLiveDataSnapshot();
        assert.deepStrictEqual(liveDataSnapshot.value, snapshot1);
        assert.equal(liveDataSnapshot.updatedAt, "T1");

        nextJob = completedJob("T2", snapshot2);
        await refreshLiveDataSnapshot();
        assert.deepStrictEqual(liveDataSnapshot.value, snapshot2);
        assert.equal(liveDataSnapshot.updatedAt, "T2");

        nextJob = { status: "failed", finished_at: "T3", error: "boom" };
        await refreshLiveDataSnapshot();
        assert.deepStrictEqual(liveDataSnapshot.value, snapshot2);
        assert.equal(liveDataSnapshot.updatedAt, "T2");
        assert.equal(liveDataSnapshot.error, "boom");

        currentKey = "B";
        syncLiveDataContext();
        assert.equal(liveDataSnapshot.value, null);
        assert.equal(liveDataSnapshot.updatedAt, null);

        currentKey = "A";
        syncLiveDataContext();
        let resolveStale = null;
        releasePending = { promise: new Promise((resolve) => { resolveStale = resolve; }) };
        const pendingRefresh = refreshLiveDataSnapshot();
        currentKey = "B";
        syncLiveDataContext();
        nextJob = completedJob("TA", snapshot1);
        resolveStale();
        await pendingRefresh;
        assert.equal(liveDataSnapshot.contextKey, "B");
        assert.equal(liveDataSnapshot.value, null);
        assert.equal(liveDataSnapshot.updatedAt, null);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

def test_basic_controls_expose_force_trigger_shared_command_shortcut() -> None:
    html = read_static("index.html")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert html.count('data-command="force-trigger"') == 1
    assert 'data-i18n="basic.forceTrigger"' in html
    assert '"basic.forceTrigger": "Force Trigger"' in english
    assert '"basic.forceTrigger": "強制觸發"' in chinese
    assert '"command.force-trigger": "Force Trigger"' in english
    assert '"command.force-trigger": "強制觸發"' in chinese

def test_single_wait_remains_advanced_only() -> None:
    html = read_static("index.html")
    form = read_static("command-form.js")
    basic_controls = read_static("basic-controls.js")
    app_source = read_static("app.js")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert html.count('data-command="single-wait"') == 0
    assert 'data-i18n="basic.singleWait"' not in html
    assert '"basic.singleWait"' not in english
    assert '"basic.singleWait"' not in chinese
    assert html.count('data-command="run"') == 1
    assert html.count('data-command="stop-acquisition"') == 1
    assert html.count('data-command="single"') == 1
    assert html.count('data-command="force-trigger"') == 1
    assert html.count('data-command="screenshot"') == 2
    assert 'data-background="black"' in html
    assert 'data-background="white"' in html
    assert '"command.single-wait"' in english
    assert '"command.single-wait"' in chinese
    assert '"description.single-wait"' in english
    assert '"description.single-wait"' in chinese
    assert '"acquisition-control": ["run", "single", "single-wait", "stop-acquisition", "force-trigger"]' in app_source
    assert 'button.dataset.command === "screenshot" && button.dataset.background' in basic_controls
    assert "execute(button.dataset.command, parameters)" in basic_controls
    assert "bindBasicControls(elements.basic, executeCommand, basicAvailable)" in app_source
    assert 'document.createElement("details")' in form
    assert "fields.filter((field) => field.advanced)" in form
    assert 'summary.textContent = translate("form.advanced")' in form
    assert "disclosure.open" not in form
    assert '"form.advanced": "Advanced"' in english
    assert '"form.advanced": "進階"' in chinese

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_basic_controls_dispatch_screenshot_background() -> None:
    basic_controls_path = STATIC_ROOT / "basic-controls.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        const source = fs.readFileSync(process.argv[1], "utf8")
          .replaceAll("export function ", "function ")
          + "\nglobalThis.basicApi = { bindBasicControls };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { bindBasicControls } = globalThis.basicApi;

        const makeButton = (command, background) => ({
          dataset: background === undefined ? { command } : { command, background },
          disabled: false,
        });
        const runButton = makeButton("run");
        const blackButton = makeButton("screenshot", "black");
        const whiteButton = makeButton("screenshot", "white");
        const buttons = [runButton, blackButton, whiteButton];
        const listeners = {};
        const container = {
          addEventListener: (type, fn) => { listeners[type] = fn; },
          querySelectorAll: (selector) => selector === "button[data-command]" ? buttons : [],
        };
        const calls = [];
        let denied = new Set();
        let deniedBackgrounds = new Set();
        const update = bindBasicControls(
          container,
          (command, parameters) => { calls.push([command, parameters]); },
          (command, parameters) => !denied.has(command)
            && !(command === "screenshot" && deniedBackgrounds.has(parameters.background)),
        );
        const click = (button) => listeners.click({ target: { closest: () => button } });
        click(runButton);
        assert.deepStrictEqual(calls[0], ["run", {}]);
        click(blackButton);
        assert.deepStrictEqual(calls[1], ["screenshot", { background: "black" }]);
        click(whiteButton);
        assert.deepStrictEqual(calls[2], ["screenshot", { background: "white" }]);

        deniedBackgrounds = new Set(["white"]);
        update();
        assert.equal(runButton.disabled, false);
        assert.equal(blackButton.disabled, false);
        assert.equal(whiteButton.disabled, true);

        denied = new Set(["screenshot"]);
        update();
        assert.equal(runButton.disabled, false);
        assert.equal(blackButton.disabled, true);
        assert.equal(whiteButton.disabled, true);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(basic_controls_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

def test_identify_uses_the_shared_workspace_result_area() -> None:
    app_source = read_static("app.js")
    html = read_static("index.html")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert 'id="identity-workspace-result"' in html
    assert 'id="identity-workspace-result-content"' in html
    assert 'data-i18n="workspace.latestSuccessfulResult"' in html
    assert 'selected.id === "identify"' in app_source
    assert 'renderWorkspaceResult(elements.identityWorkspaceContent, job, workspaceContext);' in app_source
    assert '"workspace.latestSuccessfulResult": "Latest successful result"' in english
    assert '"workspace.latestSuccessfulResult": "最新成功結果"' in chinese

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_identify_workspace_keeps_latest_success_after_a_later_failure() -> None:
    execution_context_path = STATIC_ROOT / "execution-context.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        const pcOutputDirectory = (input) => input?.value.trim() || "data";
        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replaceAll("export function ", "function ")
          + "\nglobalThis.contextApi = { buildWorkspaceContext, workspaceContextForCompletedJob, workspaceContextKey, findWorkspaceResult };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const contextApi = globalThis.contextApi;

        const completed = {
          job_id: "identify-success",
          command: "identify",
          status: "completed",
          result: { result: { idn: { model: "DSO-X 4024A", model_id: "keysight-dsox4024a" } } },
        };
        const requested = contextApi.buildWorkspaceContext("identify", {
          mode: "live", resource: "USB0::SCOPE-A::INSTR", model_id: null,
        });
        const completedContext = contextApi.workspaceContextForCompletedJob(completed, requested);
        const results = new Map([[contextApi.workspaceContextKey(completedContext), {
          context: completedContext, job: completed,
        }]]);
        assert.equal(contextApi.findWorkspaceResult(results, completedContext).job_id, "identify-success");

        const failed = {
          job_id: "identify-failed",
          command: "identify",
          status: "failed",
          error: "temporary failure",
        };
        assert.equal(failed.status, "failed");
        assert.equal(results.size, 1);
        const pendingContext = { ...requested, detected_model_id: null };
        assert.equal(
          contextApi.findWorkspaceResult(results, pendingContext, true).job_id,
          "identify-success",
        );
        const otherResource = { ...pendingContext, resource: "USB0::SCOPE-B::INSTR" };
        assert.equal(contextApi.findWorkspaceResult(results, otherResource, true), null);
        const simulateContext = contextApi.buildWorkspaceContext("identify", {
          mode: "simulate", resource: null, model_id: "keysight-dsox4024a",
        });
        assert.equal(contextApi.findWorkspaceResult(results, simulateContext, true), null);
        const otherModel = { ...completedContext, detected_model_id: "keysight-dsox4034a" };
        assert.equal(contextApi.findWorkspaceResult(results, otherModel), null);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(execution_context_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

def test_workspace_header_actions_replace_the_local_execution_badge() -> None:
    source = read_static("app.js")
    html = read_static("index.html")
    styles = read_static("styles.css")

    panel_header = html.split('<div class="panel-title">', 1)[1].split(
        '<div class="workspace-content">', 1,
    )[0]
    workspace_body = html.split('<div class="workspace-content">', 1)[1].split(
        '</section>\n      </div>', 1,
    )[0]
    assert 'id="execution-status"' not in html
    assert "workspaceExecutionState" not in source
    assert "renderExecutionStatus" not in source
    assert 'id="command-state"' in html
    assert 'id="workspace-header-actions"' in panel_header
    assert 'id="refresh-button"' in panel_header
    assert 'id="execute-button"' in panel_header
    assert 'id="cancel-button"' in panel_header
    assert 'id="execute-button"' not in workspace_body
    assert 'id="cancel-button"' not in workspace_body
    assert ".workspace-header-actions" in styles

    execute_handler = source.split('elements.execute.addEventListener("click"', 1)[1].split(
        'elements.cancel.addEventListener("click"', 1,
    )[0]
    assert "const parameters = commandForm.values();" in execute_handler
    assert "executeCommand(selected.id, parameters" in execute_handler
    assert 'intent: commandForm.isSettingEditor() ? "apply" : "command"' in execute_handler

    refresh_handler = source.split('elements.refresh.addEventListener("click"', 1)[1].split(
        'elements.cancel.addEventListener("click"', 1,
    )[0]
    assert "commandForm.isSettingEditor()" in refresh_handler
    assert "const parameters = commandForm.queryValues();" in refresh_handler
    assert 'intent: "readback"' in refresh_handler
    assert "formRevision," in refresh_handler
    assert "const formRevision = genericFormRevision;" in refresh_handler
    assert "const submittedWorkspaceContext = currentWorkspaceContext(selected.id);" in refresh_handler
    assert "const job = await executeCommand(selected.id, parameters," in refresh_handler
    assert 'selected.id === "channel-label"' in refresh_handler
    assert "job?.status === \"completed\"" in refresh_handler
    assert "formRevision === genericFormRevision" in refresh_handler
    assert "isCurrentEditorJob(selected.id, submittedWorkspaceContext)" in refresh_handler
    assert "await channelLabelVisibility?.run(false);" in refresh_handler
    assert "function scheduleEditorRead()" not in source

    cancel_handler = source.split('elements.cancel.addEventListener("click"', 1)[1].split(
        "\n  });", 1,
    )[0]
    assert "await requestCancel(currentJobId);" in cancel_handler
    assert 'elements.cancel.classList.remove("hidden");' in source
    assert 'elements.cancel.classList.add("hidden");' in source

def test_shared_header_read_labels_use_dedicated_keys() -> None:
    app_source = read_static("app.js")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    header_actions = app_source.split("function syncWorkspaceHeaderActions(editorKind)", 1)[1].split(
        "function syncEditorPresentation(editorKind)", 1,
    )[0]
    assert '"system.readInformation"' in header_actions
    assert '"actions.readSettings"' in header_actions
    assert "elements.refresh.textContent" in header_actions
    for key in (
        "actions.readSettings",
        "system.readInformation",
        "live_data.read",
        "trigger.editor.read",
        "search.editor.read",
        "segmented.editor.read",
        "cursor.editor.read",
        "annotation.editor.read",
        "wgen.editor.read",
        "demo.editor.read",
        "reference.editor.read",
        "measurement.window.read",
        "measurement.statistics.read",
    ):
        assert f'"{key}":' in english, key
        assert f'"{key}":' in chinese, key

def test_live_data_auto_refresh_wiring() -> None:
    app_source = read_static("app.js")
    device_source = read_static("device-resource.js")

    assert 'elements.liveDataRefresh.addEventListener("click", refreshLiveDataSnapshot);' in app_source
    assert "await refreshLiveDataSnapshot();" in app_source
    assert "void refreshLiveDataSnapshot();" in app_source
    assert """  if (!completed.requestedContext
      && sameExecutionContext(context, completed.context)
      && deviceResource?.hasCurrentIdentity?.(context)) {
    await refreshLiveDataSnapshot();
  }""" in app_source
    assert "onModelChange = () => {}," in device_source
    assert "this.onModelChange(this.context());" in device_source
    assert "modelContext?.mode === \"simulate\"" in app_source

def test_system_information_is_a_read_only_workspace_view() -> None:
    app_source = read_static("app.js")
    html = read_static("index.html")

    assert 'id="system-info-section"' not in html
    assert 'id="system-refresh"' not in html
    assert html.index('class="live-data-section"') < html.index('class="basic-command-section"')
    assert html.count('id="system-information-workspace"') == 1
    assert html.count('id="sys-manufacturer"') == 1
    assert 'id="system-information-workspace"' in html.split('<div class="workspace-content">', 1)[1]
    assert "scrollIntoView" not in app_source
    assert "const systemInformationSelected = selected?.id === \"system-information\";" in app_source
    assert "elements.execute.hidden = systemInformationSelected" in app_source
    assert "elements.form.hidden = editorOwned || systemInformationSelected;" in app_source

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_system_information_refresh_runs_only_the_hidden_snapshot_command() -> None:
    app_source = read_static("app.js")
    declarations = "\n".join(
        extract_function_declaration(app_source, signature)
        for signature in (
            "function systemInformationContextKey()",
            "async function refreshSystemInformationSnapshot()",
        )
    )
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";

        let context = { mode: "live", resource: "RESOURCE-A", model_id: "keysight-dsox4024a" };
        let systemSnapshot = { contextKey: null, value: null, loading: false, error: null };
        const calls = [];
        let renders = 0;
        let availabilityUpdates = 0;
        const currentModelId = () => context.model_id;
        const isExecutionBusy = () => false;
        const commandAvailable = (command) => {
          assert.equal(command, "system-information-snapshot");
          return true;
        };
        const renderSystemInformation = () => { renders += 1; };
        const updateAvailability = () => { availabilityUpdates += 1; };
        const translate = (key) => key;
        const executeCommand = async (command, parameters) => {
          calls.push({ command, parameters });
          return {
            status: "completed",
            result: {
              result: {
                idn: { vendor: "Keysight Technologies", model: "DSO-X 4034A" },
                acquisition: { sample_rate: 5e9, acquisition_points: 1000000, record_length: 1000000 },
              },
            },
          };
        };
        '''
    ) + declarations + textwrap.dedent(
        r'''

        await refreshSystemInformationSnapshot();
        assert.deepEqual(calls, [{ command: "system-information-snapshot", parameters: {} }]);
        assert.equal(systemSnapshot.value.idn.model, "DSO-X 4034A");
        assert.equal(systemSnapshot.loading, false);
        assert.equal(systemSnapshot.error, null);
        assert.equal(renders, 2);
        assert.equal(availabilityUpdates, 2);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_foreground_execution_rejects_overlap_without_changing_job_ownership() -> None:
    source = read_static("app.js")
    executable_source = source.replace("options = {}", "options = null", 1)
    declarations = "\n".join(
        extract_function_declaration(executable_source, signature)
        for signature in (
            "async function executeCommand(command, parameters, options = null)",
            "function isExecutionBusy()",
        )
    )
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";

        let executing = false;
        let genericFormRevision = 0;
        let currentJobId = null;
        let pendingResourceLiveSupport = null;
        let deviceResource = null;
        let resultPresentation = { kind: "empty", job: null, message: null };
        const context = { mode: "simulate", resource: null, model_id: "model" };
        const commands = [{ id: "run", modes: ["simulate"] }];
        const elements = {
          deviceStatus: { textContent: "" },
          execute: { disabled: false },
          cancel: { classList: { add() {}, remove() {} } },
        };
        const states = [];
        const presentations = [];
        const submissions = [];
        const translate = (key) => key;
        const pcOutputContext = (value) => ({ ...value, pc_output_dir: "data" });
        const commandAvailable = () => true;
        const currentWorkspaceContext = () => ({});
        const isCurrentEditorJob = () => false;
        const updateAvailability = () => {};
        const setExecutionStatus = (state) => states.push(state.status);
        const renderCurrentResult = () => presentations.push(resultPresentation.job?.job_id || null);
        const updateIdentity = () => {};
        const capturedWorkspaceResults = [];
        const captureWorkspaceResult = (job) => capturedWorkspaceResults.push(job.job_id);
        const commandForm = { setDisabled() {}, clearDirty() {}, syncResult() {} };
        let resolveFirst;
        const runJob = (command, parameters, commandContext, onUpdate) => {
          submissions.push({ command, parameters, commandContext });
          const jobId = `job-${submissions.length}`;
          onUpdate({ job_id: jobId, command, status: "queued" });
          if (submissions.length === 1) {
            return new Promise((resolve) => { resolveFirst = resolve; });
          }
          return Promise.resolve({ job_id: jobId, command, status: "completed" });
        };
        '''
    ) + declarations + textwrap.dedent(
        r'''

        const first = executeCommand("run", { source: 1 }, {});
        await Promise.resolve();
        assert.equal(currentJobId, "job-1");
        const ownedState = states.at(-1);
        const ownedPresentation = presentations.at(-1);

        const blocked = await executeCommand("run", { source: 2 }, {});
        assert.equal(blocked, null);
        assert.equal(submissions.length, 1);
        assert.equal(currentJobId, "job-1");
        assert.equal(states.at(-1), ownedState);
        assert.equal(presentations.at(-1), ownedPresentation);

        resolveFirst({ job_id: "job-1", command: "run", status: "completed" });
        await first;
        assert.equal(executing, false);
        assert.equal(currentJobId, null);
        assert.deepEqual(capturedWorkspaceResults, ["job-1"]);

        deviceResource = { scanInProgress: true };
        assert.equal(await executeCommand("run", { source: 3 }, {}), null);
        assert.equal(submissions.length, 1);
        deviceResource.scanInProgress = false;
        pendingResourceLiveSupport = {};
        assert.equal(await executeCommand("run", { source: 4 }, {}), null);
        assert.equal(submissions.length, 1);
        pendingResourceLiveSupport = null;

        const second = await executeCommand("run", { source: 5 }, {
          captureWorkspaceResult: false,
        });
        assert.equal(second.job_id, "job-2");
        assert.equal(submissions.length, 2);
        assert.deepEqual(capturedWorkspaceResults, ["job-1"]);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

def test_global_command_state_keeps_the_existing_execution_lifecycle() -> None:
    source = read_static("app.js")

    assert "let liveCommandState = { key: \"device.ready\" };" in source
    execution_state_handler = source.split("function setExecutionStatus(state) {", 1)[1].split(
        "\n}", 1,
    )[0]
    assert "liveCommandState = { ...state };" in execution_state_handler
    assert "renderLiveData();" in execution_state_handler
    assert 'setExecutionStatus({ status: "queued" });' in source
    assert "setExecutionStatus({ status: updated.status });" in source
    assert "setExecutionStatus({ status: job.status });" in source
    assert 'setExecutionStatus({ status: "failed" });' in source
    assert "const commandStatus = liveCommandState.status;" in source

def test_dedicated_editor_actions_use_the_workspace_header() -> None:
    bootstrap_source = read_static("editor-bootstrap.js")
    html = read_static("index.html")

    for editor in (
        "referenceEditor", "referenceLabelsEditor", "referenceDisplayEditor",
        "saveExportEditor", "serialWorkspaceHooks", "triggerEditor", "searchEditor",
        "segmentedEditor", "workflowEditor", "sequenceEditor", "channelDisplayEditor",
        "channelScaleRangeEditor", "externalTriggerEditor", "timebasePositionEditor",
        "channelOffsetEditor", "cursorEditor", "annotationEditor", "wgenEditor",
        "demoEditor", "diagnosticsEditor",
    ):
        hooks = extract_function(bootstrap_source, f"const {editor} =")
        assert "headerActions: elements.workspaceHeaderActions," in hooks, editor
        assert "executeCommand," in hooks, editor
    assert 'id="refresh-button"' not in html.split('<div class="workspace-content">', 1)[1]

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_acquisition_control_workspace_latest_result() -> None:
    app = read_static("app.js")
    functions = "\n".join(extract_function_declaration(app, signature) for signature in (
        "function renderWorkspace()",
        "function currentWorkspaceContext(",
        "function captureWorkspaceResult(",
    ))
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        import vm from "node:vm";
        const content = {
          children: [],
          replaceChildren() { this.children = []; },
          append(child) { this.children.push(child); },
        };
        let selected = { id: "acquisition-control", presentation_only: true };
        const context = { mode: "live", resource: "scope-a", model_id: null };
        let model = "model-a";
        const sandbox = {
          context,
          catalog: { selected: () => selected },
          currentModelId: () => model,
          state: { workspaceResults: new Map() },
          elements: { identityWorkspace: {}, identityWorkspaceContent: content },
          document: { createElement: () => ({}) },
          translate: (key) => key,
          renderWorkspaceResult: (container, job) => container.append(job),
        };
        vm.createContext(sandbox);
        vm.runInContext(
          fs.readFileSync(process.argv[1], "utf8")
            .replace(/^import[^\n]*\r?\n/gm, "")
            .replaceAll("export function ", "function ") + process.argv[2],
          sandbox,
        );
        sandbox.renderWorkspace();
        assert.equal(sandbox.elements.identityWorkspace.hidden, false);
        for (const command of ["run", "stop-acquisition"]) {
          const job = { command, status: "completed", result: { action: command } };
          sandbox.captureWorkspaceResult(job, sandbox.currentWorkspaceContext(command));
          assert.deepEqual(content.children, [job]);
        }
        const original = { ...context };
        for (const changed of [
          { ...original, mode: "simulate", model_id: "model-a" },
          { ...original, resource: "scope-b" },
        ]) {
          Object.assign(context, changed);
          sandbox.renderWorkspace();
          assert.equal(content.children[0].textContent, "workspace.resultEmpty");
        }
        Object.assign(context, original);
        model = "model-b";
        sandbox.renderWorkspace();
        assert.equal(content.children[0].textContent, "workspace.resultEmpty");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(STATIC_ROOT / "execution-context.js"), functions],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
