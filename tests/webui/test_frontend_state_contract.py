from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "scopes_tool_webui" / "static"


def read_static(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    body_start = source.index("{", start)
    depth = 0
    for index in range(body_start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[body_start:index + 1]
    raise AssertionError(f"Unclosed function: {signature}")


def extract_function_declaration(source: str, signature: str) -> str:
    start = source.index(signature)
    body = extract_function(source, signature)
    return source[start : source.index(body, start) + len(body)]


def extract_css_rule(source: str, selector: str) -> str:
    start = source.index(selector)
    body_start = source.index("{", start)
    end = source.index("}", body_start)
    return source[body_start:end + 1]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_live_data_engineering_formatter_uses_readable_si_units() -> None:
    live_data_path = STATIC_ROOT / "live-data.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        const source = fs.readFileSync(process.argv[1], "utf8")
          .replaceAll("export function ", "function ")
          + "\nglobalThis.liveDataApi = { formatEngineering };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { formatEngineering } = globalThis.liveDataApi;

        assert.equal(formatEngineering(0.5, "V", { perDivision: true }), "500 mV/div");
        assert.equal(formatEngineering(2, "A", { perDivision: true }), "2.00 A/div");
        assert.equal(formatEngineering(-0.0024, "s", { signed: true }), "-2.40 ms");
        assert.equal(formatEngineering(null, "V"), "—");
        assert.equal(formatEngineering(undefined, "V"), "—");
        assert.equal(formatEngineering(0, "V", { signed: true }), "+0.00 V");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(live_data_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def run_generic_form_ownership_behavior(assertions: str) -> None:
    source = read_static("app.js").replace("options = {}", "options = null", 1)
    declarations = "\n".join(
        extract_function_declaration(source, signature)
        for signature in (
            "async function executeCommand(command, parameters, options = null)",
            "function isExecutionBusy()",
            "function invalidateGenericFormOwnership()",
            "function syncCommandSelection(draft = null)",
        )
    )
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";

        let genericFormRevision = 0;
        let executing = false;
        let currentJobId = null;
        let pendingResourceLiveSupport = null;
        let deviceResource = null;
        let resultPresentation = { kind: "empty", job: null, message: null };
        const context = { mode: "simulate", resource: null, model_id: "model" };
        const channelScale = { id: "channel-scale", modes: ["simulate"] };
        const otherCommand = { id: "channel-offset", modes: ["simulate"] };
        const commands = [channelScale, otherCommand];
        const elements = {
          deviceStatus: { textContent: "" },
          execute: { disabled: false },
          formHeading: {},
          form: {},
          saveExportEditor: {},
          serialEditor: {},
          triggerEditor: {},
          searchEditor: {},
          workflowEditor: {},
          selectedCommand: {},
          commandDescription: {},
          commandSupportReason: {},
          cancel: { classList: { add() {}, remove() {} } },
        };
        const state = { selectedCommand: null };
        let selectedCommand = channelScale;
        const catalog = {
          selected: () => selectedCommand,
          commandLabel: (command) => command.id,
          description: (command) => `${command.id} description`,
          supportReason: () => "",
        };
        const completedResults = [];
        const workspaceResults = [];
        const submissions = [];
        const controllers = [];
        const translate = (key) => key;
        const pcOutputContext = (value) => ({ ...value, pc_output_dir: "data" });
        const renderPcOutputNote = () => {};
        const commandAvailable = () => true;
        const currentWorkspaceContext = () => ({ command: "channel-scale", mode: "simulate" });
        const isCurrentEditorJob = () => true;
        const editorKindFor = () => null;
        const syncWorkspaceHeaderActions = () => {};
        const renderWorkspace = () => {};
        const syncEditorPresentation = () => {};
        const commandAction = () => "apply";
        const updateAvailability = () => {};
        const setExecutionStatus = () => {};
        const renderCurrentResult = () => {
          if (resultPresentation.job?.status === "completed") {
            completedResults.push(resultPresentation.job.job_id);
          }
        };
        const updateIdentity = () => {};
        const captureWorkspaceResult = (job) => workspaceResults.push(job.job_id);
        const makeForm = () => ({
          disabledCalls: [],
          clearCalls: 0,
          syncCalls: [],
          dirty: false,
          render(_command, options) {
            this.renderOptions = options;
            this.disabledCalls = [];
            this.clearCalls = 0;
            this.syncCalls = [];
            this.dirty = true;
          },
          setDisabled(value) { this.disabledCalls.push(value); },
          clearDirty() { this.clearCalls += 1; },
          syncResult(job, preserveDirty) { this.syncCalls.push([job.job_id, preserveDirty]); },
        });
        let commandForm = makeForm();
        const runJob = (command, parameters, commandContext, onUpdate) => {
          const jobId = `job-${submissions.length + 1}`;
          submissions.push({ command, parameters, commandContext, jobId });
          onUpdate({ job_id: jobId, command, status: "queued" });
          return new Promise((resolve) => controllers.push({ jobId, resolve }));
        };
        const complete = (index) => {
          const controller = controllers[index];
          controller.resolve({
            job_id: controller.jobId,
            command: "channel-scale",
            status: "completed",
            result: { result: { channel: 1, volts_per_division: 0.5 } },
          });
        };
        '''
    ) + declarations + textwrap.dedent(assertions)
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_identity_is_bound_to_the_current_execution_context() -> None:
    source = read_static("device-resource.js")

    assert "this.identityContext = null;" in source
    assert "function sameContext(left, right)" in source
    context_snapshot = extract_function(source, "function contextSnapshot(context)")
    assert 'mode: context?.mode || null' in context_snapshot
    assert 'resource: context?.resource || null' in context_snapshot
    assert 'model_id: context?.model_id || null' in context_snapshot
    assert "this.clearIdentity();" in source
    assert "changed(true);" in source
    assert "setIdentity(identity, associatedContext = this.context())" in source
    assert "sameContext(this.context(), associatedContext)" in source
    changed = extract_function(source, "changed(forceIdentityClear = false)")
    assert "if (forceIdentityClear || contextChanged)" in changed
    assert "this.clearIdentity();" in changed
    assert "this.clearIdentity();" in extract_function(source, "async scan()")


def test_live_context_and_controls_use_detected_identity() -> None:
    execution_context = read_static("execution-context.js")
    app_source = read_static("app.js")
    html = read_static("index.html")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert 'model_id: mode === "live" ? null : elements.model.value' in execution_context
    assert 'const state = createInitialState();' in app_source
    assert 'let context = state.executionContext;' in app_source
    availability = extract_function(app_source, "function commandAvailable(command)")
    assert 'if (command === "identify") return true;' in availability
    assert "deviceResource?.hasCurrentIdentity(context)" in availability
    assert 'id="detected-model"' in html
    assert 'data-command="identify"' not in html
    assert '"command.identify": "Read device information"' in english
    assert '"description.identify": "Read instrument identification information"' in english
    assert '"command.identify": "讀取裝置資訊"' in chinese
    assert '"description.identify": "讀取儀器識別資訊"' in chinese


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


def test_serial_editor_replaces_generic_form_with_passive_selection() -> None:
    app_source = read_static("app.js")
    html = read_static("index.html")
    editor_source = read_static("serial-editor.js")

    assert 'import { SerialEditor } from "/static/serial-editor.js";' in app_source
    assert 'id="form-heading"' in html
    assert 'id="serial-editor" class="serial-editor" hidden' in html
    routing = extract_function(app_source, "function editorKindFor(command)")
    assert "command?.editor" in routing
    assert "EDITOR_RENDERERS[kind]" in routing
    renderer_map = app_source.split("const EDITOR_RENDERERS = {", 1)[1].split("};", 1)[0]
    assert 'serial: () => serialEditor,' in renderer_map
    assert 'trigger: () => triggerEditor,' in renderer_map
    assert "function scheduleEditorRead()" not in app_source
    presentation = extract_function(app_source, "function syncEditorPresentation(editorKind)")
    assert "serialEditor?.schedulePresentation();" in presentation
    assert "elements.formHeading.hidden = editorOwned;" in app_source
    assert "elements.form.hidden = editorOwned;" in app_source
    assert 'elements.serialEditor.hidden = editorKind !== "serial";' in app_source
    assert "syncWorkspaceHeaderActions(editorKind);" in app_source
    assert "elements.serialEditor.hidden = !editorOwned;" not in app_source
    assert "SERIAL_EDITOR_COMMANDS" not in app_source
    assert "serialEditor?.rerender();" in app_source
    assert 'translate(`${editorKind}.editor.title`)' in app_source
    for command_id in (
        "serial-mode",
        "serial-display",
        "serial-uart",
        "serial-i2c",
        "serial-spi",
        "serial-can",
        "serial-trigger-uart",
        "serial-trigger-i2c",
        "serial-trigger-spi",
        "serial-trigger-can",
        "serial-lister-query",
        "serial-lister-display",
        "serial-lister-reference",
        "serial-lister-export",
    ):
        assert f'"{command_id}"' in editor_source

    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")
    for key in (
        "serial.editor.title",
        "serial.editor.description",
        "serial.editor.busOption",
        "serial.editor.currentProtocol",
        "serial.editor.protocol",
        "serial.editor.applyMode",
        "serial.editor.applyDisplay",
        "serial.editor.applyConfiguration",
        "serial.editor.applyTrigger",
        "serial.editor.export",
        "serial.editor.triggerSection",
        "serial.editor.listerSection",
        "serial.editor.unsupported",
        "serial.editor.discardConfirm",
    ):
        assert f'"{key}":' in english, key
        assert f'"{key}":' in chinese, key


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_serial_editor_controller_sequences_reads_and_discard_gating() -> None:
    serial_editor_path = STATIC_ROOT / "serial-editor.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.serialApi = { SERIAL_EDITOR_COMMANDS, configCommandFor, triggerCommandFor, busOptions, createSerialEditorController };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const {
          SERIAL_EDITOR_COMMANDS,
          configCommandFor,
          triggerCommandFor,
          busOptions,
          createSerialEditorController,
        } = globalThis.serialApi;

        const settle = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
          await new Promise((resolve) => setTimeout(resolve, 0));
        };

        const makeHarness = ({
          initialMode = "can",
          maxBus = 1,
          confirmResult = true,
          setTakesEffect = true,
        } = {}) => {
          const submitted = [];
          let currentMode = initialMode;
          let modeQueryFails = false;
          const respond = (command, parameters) => {
            if (command === "serial-mode") {
              if (parameters.action === "query" && modeQueryFails) {
                return {
                  job_id: `mode-${submitted.length}`,
                  status: "failed",
                  error: "temporary VISA failure",
                };
              }
              if (parameters.action === "set" && setTakesEffect) currentMode = parameters.mode;
              return {
                job_id: `mode-${submitted.length}`,
                status: "completed",
                result: { result: { mode: {
                  bus: parameters.bus,
                  mode: currentMode,
                  raw_mode: String(currentMode).toUpperCase(),
                } } },
              };
            }
            if (command === "serial-display") {
              return {
                job_id: `display-${submitted.length}`,
                status: "completed",
                result: { result: { display: { bus: parameters.bus, enabled: true } } },
              };
            }
            if (command.startsWith("serial-trigger-")) {
              const triggerProtocol = command.replace("serial-trigger-", "");
              return {
                job_id: `trigger-${submitted.length}`,
                status: "completed",
                result: { result: { trigger: {
                  protocol: triggerProtocol,
                  bus: parameters.bus,
                  mode: currentMode,
                  selected: true,
                } } },
              };
            }
            if (command === "serial-lister-display" || command === "serial-lister-reference") {
              const slot = command === "serial-lister-display" ? "display" : "reference";
              const value = slot === "display"
                ? (parameters.display ?? "off")
                : (parameters.reference ?? "trigger");
              return {
                job_id: `${slot}-${submitted.length}`,
                status: "completed",
                result: { result: { [slot]: { [slot]: value } } },
              };
            }
            const protocol = command.replace("serial-", "");
            return {
              job_id: `${protocol}-${submitted.length}`,
              status: "completed",
              result: { result: { [protocol]: { bus: parameters.bus } } },
            };
          };
          const execute = async (command, parameters, options) => {
            submitted.push({ command, action: parameters.action, intent: options?.intent });
            return respond(command, parameters);
          };
          const confirmations = [];
          const controller = createSerialEditorController({
            execute,
            confirmDiscard: () => { confirmations.push("asked"); return confirmResult; },
            available: () => true,
          });
          controller.reset({
            maxBus,
            protocolChoices: ["uart", "i2c", "spi", "can"],
          });
          return {
            controller,
            submitted,
            confirmations,
            setCurrentMode: (mode) => { currentMode = mode; },
            setModeQueryFails: (value) => { modeQueryFails = Boolean(value); },
          };
        };

        const commandsOf = (harness) =>
          harness.submitted.map((entry) => `${entry.command}${entry.action ? `:${entry.action}` : ""}`);

        const initialRefreshCommands = (configCommand, triggerCommand) => [
          "serial-mode:query",
          "serial-display:query",
          `${configCommand}:query`,
          `${triggerCommand}:query`,
          "serial-lister-query",
        ];

        assert.deepEqual(busOptions(1), [1]);
        assert.deepEqual(busOptions(2), [1, 2]);
        assert.equal(configCommandFor("uart"), "serial-uart");
        assert.equal(configCommandFor("i2c"), "serial-i2c");
        assert.equal(configCommandFor("spi"), "serial-spi");
        assert.equal(configCommandFor("can"), "serial-can");
        assert.equal(configCommandFor("lin"), null);
        assert.equal(configCommandFor(null), null);
        assert.equal(triggerCommandFor("uart"), "serial-trigger-uart");
        assert.equal(triggerCommandFor("i2c"), "serial-trigger-i2c");
        assert.equal(triggerCommandFor("spi"), "serial-trigger-spi");
        assert.equal(triggerCommandFor("can"), "serial-trigger-can");
        assert.equal(triggerCommandFor("lin"), null);
        assert.equal(triggerCommandFor(null), null);
        assert.equal(SERIAL_EDITOR_COMMANDS.includes("serial-query"), false);
        assert.equal(SERIAL_EDITOR_COMMANDS.includes("serial-search-uart"), false);
        assert.equal(SERIAL_EDITOR_COMMANDS.includes("serial-trigger-can"), true);
        assert.equal(SERIAL_EDITOR_COMMANDS.includes("serial-lister-export"), true);

        {
          const single = makeHarness({ initialMode: "uart", maxBus: 1 });
          single.controller.selectBus(2);
          await settle();
          assert.deepEqual(single.submitted, []);
          assert.equal(single.controller.state.bus, 1);
        }

        {
          const dual = makeHarness({ initialMode: "can", maxBus: 2 });
          dual.controller.scheduleRefresh();
          await settle();
          assert.deepEqual(commandsOf(dual), initialRefreshCommands(
            "serial-can",
            "serial-trigger-can",
          ));
          dual.controller.selectBus(2);
          await settle();
          assert.equal(dual.controller.state.bus, 2);
          assert.deepEqual(commandsOf(dual).slice(5), []);
          dual.controller.scheduleRefresh();
          await settle();
          assert.deepEqual(commandsOf(dual).slice(5), [
            "serial-mode:query",
            "serial-display:query",
            "serial-can:query",
            "serial-trigger-can:query",
            "serial-lister-query",
          ]);
          assert.equal(dual.controller.state.formEpoch, 2);
        }

        {
          const canBus = makeHarness({ initialMode: "can" });
          canBus.controller.scheduleRefresh();
          await settle();
          const canCommands = commandsOf(canBus);
          assert.equal(canCommands.includes("serial-uart:query"), false);
          assert.deepEqual(canCommands, initialRefreshCommands(
            "serial-can",
            "serial-trigger-can",
          ));
          assert.equal(canCommands.some((entry) =>
            entry.startsWith("serial-trigger-")
            && entry !== "serial-trigger-can:query"), false);
          assert.equal(canBus.controller.state.configCommand, "serial-can");
          assert.equal(canBus.controller.state.triggerCommand, "serial-trigger-can");
          assert.equal(canBus.controller.state.selectedProtocol, "can");
        }

        {
          const uartBus = makeHarness({ initialMode: "uart" });
          uartBus.controller.scheduleRefresh();
          await settle();
          assert.deepEqual(commandsOf(uartBus), initialRefreshCommands(
            "serial-uart",
            "serial-trigger-uart",
          ));
          assert.equal(uartBus.controller.state.configCommand, "serial-uart");
          assert.equal(uartBus.controller.state.triggerCommand, "serial-trigger-uart");
        }

        {
          for (const protocol of ["i2c", "spi"]) {
            const scoped = makeHarness({ initialMode: protocol });
            scoped.controller.scheduleRefresh();
            await settle();
            assert.deepEqual(
              commandsOf(scoped),
              initialRefreshCommands(`serial-${protocol}`, `serial-trigger-${protocol}`),
              protocol,
            );
          }
        }

        {
          const linBus = makeHarness({ initialMode: "lin" });
          linBus.controller.scheduleRefresh();
          await settle();
          assert.deepEqual(commandsOf(linBus), [
            "serial-mode:query",
            "serial-display:query",
            "serial-lister-query",
          ]);
          assert.equal(commandsOf(linBus).some((entry) =>
            entry.startsWith("serial-trigger-")), false);
          assert.equal(linBus.controller.state.supported, false);
          assert.equal(linBus.controller.state.triggerCommand, null);
          assert.equal(linBus.controller.state.currentLabel, "LIN");
          linBus.controller.selectProtocol("spi");
          assert.equal(linBus.controller.state.selectedProtocol, "spi");
        }

        {
          const switched = makeHarness({ initialMode: "can" });
          switched.controller.scheduleRefresh();
          await settle();
          switched.controller.setDirty("config", true);
          switched.controller.selectProtocol("uart");
          await switched.controller.applyMode();
          await settle();
          const commands = commandsOf(switched);
          assert.equal(switched.confirmations.length, 1);
          assert.equal(commands[5], "serial-mode:set");
          assert.deepEqual(commands.slice(-3), [
            "serial-mode:set",
            "serial-uart:query",
            "serial-trigger-uart:query",
          ]);
          assert.equal(commands.includes("serial-i2c:query"), false);
          assert.equal(switched.controller.state.confirmedMode, "uart");
          assert.equal(switched.controller.state.dirtyConfig, false);
          assert.equal(switched.controller.state.dirtyTrigger, false);
          assert.equal(switched.controller.state.triggerCommand, "serial-trigger-uart");
          const setEntry = switched.submitted[5];
          assert.equal(setEntry.intent, "apply");
          assert.equal(setEntry.action, "set");
          const readEntry = switched.submitted[6];
          assert.equal(readEntry.intent, "readback");
        }

        {
          const mismatch = makeHarness({ initialMode: "can", setTakesEffect: false });
          mismatch.controller.scheduleRefresh();
          await settle();
          mismatch.controller.setDirty("config", true);
          mismatch.controller.selectProtocol("uart");
          await mismatch.controller.applyMode();
          await settle();
          const commands = commandsOf(mismatch);
          assert.equal(mismatch.confirmations.length, 1);
          assert.equal(commands[5], "serial-mode:set");
          assert.deepEqual(commands.slice(-5), [
            "serial-mode:query",
            "serial-display:query",
            "serial-can:query",
            "serial-trigger-can:query",
            "serial-lister-query",
          ]);
          assert.equal(commands.includes("serial-uart:query"), false);
          assert.equal(commands.includes("serial-trigger-uart:query"), false);
          assert.equal(mismatch.controller.state.confirmedMode, "can");
          assert.equal(mismatch.controller.state.selectedProtocol, "can");
          assert.equal(mismatch.controller.state.dirtyConfig, true);
        }

        {
          const cancelled = makeHarness({ initialMode: "can", maxBus: 2, confirmResult: false });
          cancelled.controller.scheduleRefresh();
          await settle();
          const before = cancelled.submitted.length;
          const epochBefore = cancelled.controller.state.formEpoch;
          cancelled.controller.setDirty("config", true);
          cancelled.controller.selectBus(2);
          await settle();
          assert.deepEqual(cancelled.confirmations, ["asked"]);
          assert.equal(cancelled.controller.state.bus, 1);
          assert.equal(cancelled.controller.state.dirtyConfig, true);
          assert.equal(cancelled.controller.state.formEpoch, epochBefore);
          assert.equal(cancelled.submitted.length, before);

          const discarded = makeHarness({ initialMode: "can", maxBus: 2 });
          discarded.controller.scheduleRefresh();
          await settle();
          discarded.controller.setDirty("config", true);
          discarded.controller.selectBus(2);
          await settle();
          assert.deepEqual(discarded.confirmations, ["asked"]);
          assert.equal(discarded.controller.state.bus, 2);
          assert.equal(discarded.controller.state.dirtyConfig, false);
          assert.equal(discarded.submitted.length, 5);
          discarded.controller.scheduleRefresh();
          await settle();
          assert.equal(commandsOf(discarded)[5], "serial-mode:query");
        }

        {
          const cancelled = makeHarness({ initialMode: "can", confirmResult: false });
          cancelled.controller.scheduleRefresh();
          await settle();
          const before = cancelled.submitted.length;
          cancelled.controller.setDirty("config", true);
          cancelled.controller.selectProtocol("uart");
          await cancelled.controller.applyMode();
          await settle();
          assert.deepEqual(cancelled.confirmations, ["asked"]);
          assert.equal(cancelled.controller.state.confirmedMode, "can");
          assert.equal(cancelled.controller.state.dirtyConfig, true);
          assert.equal(cancelled.submitted.length, before);
        }

        {
          const idle = makeHarness({ initialMode: "can" });
          idle.controller.scheduleRefresh();
          await settle();
          idle.controller.selectProtocol("can");
          await idle.controller.applyMode();
          await settle();
          assert.deepEqual(idle.confirmations, []);
          assert.equal(idle.submitted.length, 5);
        }

        {
          const dualModes = makeHarness({
            initialMode: "can",
            maxBus: 2,
          });
          dualModes.controller.scheduleRefresh();
          await settle();
          assert.equal(dualModes.controller.state.selectedProtocol, "can");
          dualModes.setCurrentMode("uart");
          dualModes.controller.selectBus(2);
          await settle();
          assert.equal(dualModes.controller.state.confirmedMode, null);
          dualModes.controller.scheduleRefresh();
          await settle();
          assert.equal(dualModes.controller.state.confirmedMode, "uart");
          assert.equal(dualModes.controller.state.selectedProtocol, "uart");
        }

        {
          const displayOnly = makeHarness({ initialMode: "can" });
          displayOnly.controller.scheduleRefresh();
          await settle();
          displayOnly.controller.setDirty("display", true);
          displayOnly.controller.selectProtocol("uart");
          await displayOnly.controller.applyMode();
          await settle();
          assert.deepEqual(displayOnly.confirmations, []);
          assert.equal(displayOnly.controller.state.confirmedMode, "uart");
          assert.equal(displayOnly.controller.state.dirtyDisplay, true);
          const commands = commandsOf(displayOnly);
          assert.deepEqual(commands.slice(-3), [
            "serial-mode:set",
            "serial-uart:query",
            "serial-trigger-uart:query",
          ]);
        }

        {
          const external = makeHarness({ initialMode: "uart" });
          external.controller.scheduleRefresh();
          await settle();
          external.setCurrentMode("can");
          external.controller.setDirty("config", true);
          await external.controller.applyConfig({ baud_rate: 115200 });
          await settle();
          const tail = commandsOf(external).slice(5);
          assert.equal(tail[0], "serial-mode:query");
          assert.equal(tail.some((entry) => entry === "serial-uart:set"), false);
          assert.deepEqual(tail.slice(1), [
            "serial-display:query",
            "serial-can:query",
            "serial-trigger-can:query",
          ]);
          assert.equal(external.controller.state.confirmedMode, "can");
          assert.equal(external.controller.state.selectedProtocol, "can");
          assert.equal(external.controller.state.dirtyConfig, false);
        }

        {
          const stable = makeHarness({ initialMode: "can" });
          stable.controller.scheduleRefresh();
          await settle();
          stable.controller.setDirty("config", true);
          await stable.controller.applyConfig({ baud_rate: 500000 });
          await settle();
          assert.deepEqual(commandsOf(stable).slice(5), [
            "serial-mode:query",
            "serial-can:set",
          ]);
          assert.equal(stable.submitted[6].intent, "apply");
          assert.equal(stable.controller.state.dirtyConfig, false);
          assert.equal(stable.controller.state.confirmedMode, "can");
        }

        {
          const failedRecheck = makeHarness({ initialMode: "uart" });
          failedRecheck.controller.scheduleRefresh();
          await settle();
          failedRecheck.controller.setDirty("config", true);
          failedRecheck.setModeQueryFails(true);
          await failedRecheck.controller.applyConfig({ baud_rate: 115200 });
          await settle();
          assert.deepEqual(commandsOf(failedRecheck).slice(5), [
            "serial-mode:query",
          ]);
          assert.equal(failedRecheck.controller.state.confirmedMode, "uart");
          assert.equal(failedRecheck.controller.state.selectedProtocol, "uart");
          assert.equal(failedRecheck.controller.state.dirtyConfig, true);

          failedRecheck.setModeQueryFails(false);
          await failedRecheck.controller.applyConfig({ baud_rate: 115200 });
          await settle();
          assert.deepEqual(commandsOf(failedRecheck).slice(6), [
            "serial-mode:query",
            "serial-uart:set",
          ]);
          assert.equal(failedRecheck.controller.state.dirtyConfig, false);
        }

        {
          const triggerApply = makeHarness({ initialMode: "can" });
          triggerApply.controller.scheduleRefresh();
          await settle();
          triggerApply.controller.setDirty("trigger", true);
          await triggerApply.controller.applyTrigger({ type: "start-of-frame" });
          await settle();
          assert.deepEqual(commandsOf(triggerApply).slice(5), [
            "serial-mode:query",
            "serial-trigger-can:set",
          ]);
          assert.equal(triggerApply.submitted[6].intent, "apply");
          assert.equal(triggerApply.controller.state.dirtyTrigger, false);
          assert.equal(triggerApply.controller.state.confirmedMode, "can");
        }

        {
          const failedTriggerRecheck = makeHarness({ initialMode: "uart" });
          failedTriggerRecheck.controller.scheduleRefresh();
          await settle();
          failedTriggerRecheck.controller.setDirty("trigger", true);
          failedTriggerRecheck.setModeQueryFails(true);
          await failedTriggerRecheck.controller.applyTrigger({ type: "rx-start" });
          await settle();
          assert.deepEqual(commandsOf(failedTriggerRecheck).slice(5), [
            "serial-mode:query",
          ]);
          assert.equal(failedTriggerRecheck.controller.state.confirmedMode, "uart");
          assert.equal(failedTriggerRecheck.controller.state.selectedProtocol, "uart");
          assert.equal(failedTriggerRecheck.controller.state.dirtyTrigger, true);

          failedTriggerRecheck.setModeQueryFails(false);
          failedTriggerRecheck.controller.setDirty("trigger", true);
          failedTriggerRecheck.setCurrentMode("can");
          await failedTriggerRecheck.controller.applyTrigger({ type: "rx-start" });
          await settle();
          const tail = commandsOf(failedTriggerRecheck).slice(6);
          assert.equal(tail[0], "serial-mode:query");
          assert.equal(tail.some((entry) => entry === "serial-trigger-uart:set"), false);
          assert.deepEqual(tail.slice(1), [
            "serial-display:query",
            "serial-can:query",
            "serial-trigger-can:query",
          ]);
          assert.equal(failedTriggerRecheck.controller.state.confirmedMode, "can");
          assert.equal(failedTriggerRecheck.controller.state.selectedProtocol, "can");
          assert.equal(failedTriggerRecheck.controller.state.dirtyTrigger, false);
          assert.equal(failedTriggerRecheck.controller.state.dirtyConfig, false);
        }

        {
          const dirtyBusCancel = makeHarness({
            initialMode: "can", maxBus: 2, confirmResult: false,
          });
          dirtyBusCancel.controller.scheduleRefresh();
          await settle();
          const before = dirtyBusCancel.submitted.length;
          dirtyBusCancel.controller.setDirty("trigger", true);
          dirtyBusCancel.controller.selectBus(2);
          await settle();
          assert.deepEqual(dirtyBusCancel.confirmations, ["asked"]);
          assert.equal(dirtyBusCancel.controller.state.bus, 1);
          assert.equal(dirtyBusCancel.controller.state.dirtyTrigger, true);
          assert.equal(dirtyBusCancel.submitted.length, before);

          const dirtyBusDiscard = makeHarness({ initialMode: "can", maxBus: 2 });
          dirtyBusDiscard.controller.scheduleRefresh();
          await settle();
          dirtyBusDiscard.controller.setDirty("trigger", true);
          dirtyBusDiscard.controller.selectBus(2);
          await settle();
          assert.deepEqual(dirtyBusDiscard.confirmations, ["asked"]);
          assert.equal(dirtyBusDiscard.controller.state.bus, 2);
          assert.equal(dirtyBusDiscard.controller.state.dirtyTrigger, false);
          assert.equal(dirtyBusDiscard.submitted.length, 5);
          dirtyBusDiscard.controller.scheduleRefresh();
          await settle();
          assert.equal(commandsOf(dirtyBusDiscard)[5], "serial-mode:query");
        }

        {
          const dirtyProtocol = makeHarness({ initialMode: "can", confirmResult: false });
          dirtyProtocol.controller.scheduleRefresh();
          await settle();
          const before = dirtyProtocol.submitted.length;
          dirtyProtocol.controller.setDirty("trigger", true);
          dirtyProtocol.controller.selectProtocol("uart");
          await dirtyProtocol.controller.applyMode();
          await settle();
          assert.deepEqual(dirtyProtocol.confirmations, ["asked"]);
          assert.equal(dirtyProtocol.controller.state.confirmedMode, "can");
          assert.equal(dirtyProtocol.controller.state.dirtyTrigger, true);
          assert.equal(dirtyProtocol.submitted.length, before);
        }

        {
          const listerKept = makeHarness({ initialMode: "can" });
          listerKept.controller.scheduleRefresh();
          await settle();
          listerKept.controller.setDirty("listerDisplay", true);
          listerKept.controller.selectProtocol("uart");
          await listerKept.controller.applyMode();
          await settle();
          assert.deepEqual(listerKept.confirmations, []);
          assert.equal(listerKept.controller.state.confirmedMode, "uart");
          assert.equal(listerKept.controller.state.dirtyListerDisplay, true);

          const busTwoLister = makeHarness({
            initialMode: "can", maxBus: 2,
          });
          busTwoLister.controller.scheduleRefresh();
          await settle();
          busTwoLister.controller.setDirty("display", true);
          busTwoLister.controller.setDirty("listerReference", true);
          busTwoLister.controller.selectBus(2);
          await settle();
          assert.deepEqual(busTwoLister.confirmations, ["asked"]);
          assert.equal(busTwoLister.controller.state.dirtyDisplay, false);
          assert.equal(busTwoLister.controller.state.dirtyListerReference, true);
        }

        {
          const listerRouting = makeHarness({ initialMode: "can" });
          listerRouting.controller.scheduleRefresh();
          await settle();
          listerRouting.controller.setDirty("listerDisplay", true);
          await listerRouting.controller.applyListerSetting("display", { display: "all" });
          await settle();
          const lastDisplay = listerRouting.submitted[listerRouting.submitted.length - 1];
          assert.equal(lastDisplay.command, "serial-lister-display");
          assert.equal(lastDisplay.action, "set");
          assert.equal(lastDisplay.intent, "apply");
          assert.equal(listerRouting.controller.state.dirtyListerDisplay, false);

          listerRouting.controller.setDirty("listerReference", true);
          await listerRouting.controller.applyListerSetting("reference", { reference: "previous" });
          await settle();
          const lastReference = listerRouting.submitted[listerRouting.submitted.length - 1];
          assert.equal(lastReference.command, "serial-lister-reference");
          assert.equal(lastReference.action, "set");
          assert.equal(lastReference.intent, "apply");
          assert.equal(listerRouting.controller.state.dirtyListerReference, false);

          const beforeExport = listerRouting.submitted.length;
          assert.equal(await listerRouting.controller.exportLister(""), null);
          assert.equal(listerRouting.submitted.length, beforeExport);
          const exported = await listerRouting.controller.exportLister("capture.csv");
          await settle();
          assert.equal(exported.status, "completed");
          const lastExport = listerRouting.submitted[listerRouting.submitted.length - 1];
          assert.equal(lastExport.command, "serial-lister-export");
          assert.equal(lastExport.intent, undefined);
        }

        {
          const relister = makeHarness({ initialMode: "can" });
          relister.controller.scheduleRefresh();
          await settle();
          const firstCommands = commandsOf(relister);
          assert.equal(firstCommands.includes("serial-lister-query"), true);
          assert.equal(firstCommands.includes("serial-lister-display:query"), false);
          assert.equal(firstCommands.includes("serial-lister-reference:query"), false);
          const before = relister.submitted.length;
          relister.controller.scheduleRefresh();
          await settle();
          const refreshed = relister.submitted.slice(before);
          assert.deepEqual(refreshed.map((entry) => entry.command), [
            "serial-mode",
            "serial-display",
            "serial-can",
            "serial-trigger-can",
            "serial-lister-query",
          ]);
        }
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(serial_editor_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_serial_editor_view_refresh_keeps_selected_bus_and_follows_mode_readback() -> None:
    serial_editor_path = STATIC_ROOT / "serial-editor.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.value = "";
            this.className = "";
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) { this.children.push(...nodes); }
          querySelectorAll() { return []; }
        }
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
        globalThis.Option = function Option(text, value) {
          return { textContent: text, value: String(value) };
        };
        globalThis.window = { confirm: () => true };
        globalThis.translate = (key) => key;
        globalThis.hasTranslation = () => true;
        globalThis.CommandForm = class CommandForm {
          constructor() {
            this.dirty = false;
            this.lastSyncArgs = null;
            this.clearedDirty = false;
          }
          render() {}
          values() { return {}; }
          setDisabled() {}
          clearDirty() { this.clearedDirty = true; this.dirty = false; }
          syncResult(job, preserveDirty) { this.lastSyncArgs = [job, preserveDirty]; }
          isDirty() { return this.dirty; }
        };

        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.serialApi = { SerialEditor };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const { SerialEditor } = globalThis.serialApi;

        const settle = async () => {
          await new Promise((resolve) => setTimeout(resolve, 0));
          await new Promise((resolve) => setTimeout(resolve, 0));
        };

        const settingFields = [{ name: "action", type: "enum", options: ["query", "set"] }];
        const definitionFor = (id, queryFields = ["bus"]) => ({
          id,
          category: "Serial",
          modes: ["live"],
          presentation: { kind: "setting", action_field: "action", apply_value: "set", query_value: "query", query_fields: queryFields },
          fields: [...settingFields],
        });
        const catalog = {
          commands: [
            definitionFor("serial-mode"),
            definitionFor("serial-display"),
            definitionFor("serial-uart"),
            definitionFor("serial-i2c"),
            definitionFor("serial-spi"),
            definitionFor("serial-can"),
            definitionFor("serial-trigger-uart"),
            definitionFor("serial-trigger-i2c"),
            definitionFor("serial-trigger-spi"),
            definitionFor("serial-trigger-can"),
            definitionFor("serial-lister-query", []),
            definitionFor("serial-lister-display", []),
            definitionFor("serial-lister-reference", []),
          ],
          fieldsFor: (definition) => definition.fields,
          optionsFor: (field) => field.options || [],
        };

        const submitted = [];
        let executionBusy = false;
        let currentMode = "can";
        let editor = null;
        const respond = (command, parameters) => {
          if (command === "serial-mode") {
            if (parameters.action === "set") currentMode = parameters.mode;
            return {
              job_id: `mode-${submitted.length}`,
              status: "completed",
              result: { result: { mode: {
                bus: parameters.bus,
                mode: currentMode,
                raw_mode: String(currentMode).toUpperCase(),
              } } },
            };
          }
          if (command === "serial-display") {
            return {
              job_id: `display-${submitted.length}`,
              status: "completed",
              result: { result: { display: { bus: parameters.bus, enabled: false } } },
            };
          }
          const protocol = command.replace("serial-", "");
          return {
            job_id: `${protocol}-${submitted.length}`,
            status: "completed",
            result: { result: { [protocol]: { bus: parameters.bus } } },
          };
        };
        const executeCommand = async (command, parameters) => {
          const job = respond(command, parameters);
          submitted.push({ command, bus: parameters.bus, action: parameters.action });
          queueMicrotask(() => editor.scheduleRefresh());
          return job;
        };

        editor = new SerialEditor(new FakeNode(), catalog, {
          executeCommand,
          isAvailable: () => true,
          isExecutionBusy: () => executionBusy,
          contextKey: () => "ctx",
          modelInfo: () => ({ supported: true, maxBus: 2, protocols: ["uart", "i2c", "spi", "can"] }),
        });

        editor.scheduleRefresh();
        await settle();
        assert.equal(editor.protocolSelect.value, "can");
        assert.equal(editor.triggerSection.hidden, false);
        assert.ok(editor.triggerForm);
        assert.ok(editor.listerDisplayForm);
        assert.ok(editor.listerReferenceForm);
        assert.ok(editor.exportForm);
        assert.equal(submitted.length, 5);
        assert.deepEqual(submitted.slice(0, 4).map((entry) => entry.bus), [1, 1, 1, 1]);
        assert.equal(submitted[4].command, "serial-lister-query");
        assert.equal(editor.listerDisplayForm.lastSyncArgs?.[1], true);
        assert.equal(editor.listerReferenceForm.lastSyncArgs?.[1], true);

        editor.listerDisplayForm.dirty = true;
        editor.listerReferenceForm.dirty = true;

        editor.busSelect.value = "2";
        editor.busSelect.dispatch("change");
        await settle();
        assert.equal(editor.controller.state.bus, 2);
        assert.equal(editor.protocolSelect.value, "can");
        assert.equal(submitted.length, 5);

        const listerDirtyBefore = {
          display: editor.listerDisplayForm.dirty,
          reference: editor.listerReferenceForm.dirty,
        };

        editor.refreshButton.dispatch("click");
        await settle();

        assert.deepEqual(listerDirtyBefore, { display: true, reference: true });
        assert.equal(editor.listerDisplayForm.lastSyncArgs?.[1], true);
        assert.equal(editor.listerReferenceForm.lastSyncArgs?.[1], true);

        const laterSubmissions = submitted.slice(5);
        assert.equal(laterSubmissions.length > 0, true);
        assert.equal(laterSubmissions.every((entry) =>
          entry.bus === 2 || entry.command === "serial-lister-query"), true);
        assert.equal(laterSubmissions.some((entry) =>
          entry.command === "serial-mode" && entry.action === "query"), true);
        assert.equal(laterSubmissions.some((entry) =>
          entry.command === "serial-display" && entry.action === "query"), true);
        assert.equal(laterSubmissions.some((entry) =>
          entry.command.startsWith("serial-trigger-") && entry.action === "query"), true);
        assert.equal(laterSubmissions.filter((entry) =>
          entry.command === "serial-lister-query").length >= 1, true);

        editor.displayForm.values = () => ({ enabled: true });
        editor.exportForm.values = () => ({ filename: "serial.csv" });
        executionBusy = true;
        editor.render(editor.controller.state);
        assert.equal(editor.applyDisplayButton.disabled, true);
        assert.equal(editor.exportButton.disabled, true);
        const blockedAt = submitted.length;
        await editor.submitDisplay();
        await editor.submitExport();
        assert.equal(submitted.length, blockedAt);

        executionBusy = false;
        editor.render(editor.controller.state);
        assert.equal(editor.applyDisplayButton.disabled, false);
        assert.equal(editor.exportButton.disabled, false);
        await editor.submitExport();
        assert.equal(submitted[blockedAt].command, "serial-lister-export");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(serial_editor_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_serial_editor_locale_keys_are_localized() -> None:
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert '"serial.editor.unavailable": "Identify a supported instrument to configure Serial."' in english
    assert '"serial.editor.unsupported": "{{protocol}} is recognized by the instrument' in english
    assert '"serial.editor.discardConfirm": "Discard unapplied Serial changes?"' in english
    assert '"serial.editor.unavailable": "請先連接並識別支援的儀器，再設定串列。"' in chinese
    assert '"serial.editor.discardConfirm": "要捨棄未套用的串列變更嗎？"' in chinese
    assert '"serial.editor.title": "Serial editor"' in english
    assert '"serial.editor.title": "串列編輯器"' in chinese


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_generic_form_multi_choice_and_two_state_boolean_presentation() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.testTranslate = (key) => key;
        globalThis.testHasTranslation = () => false;

        class FakeElement {
          constructor(tag) {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.dataset = {};
            this.attributes = {};
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.required = false;
            this.multiple = false;
            this.tabIndex = 0;
            this.type = "";
            this.value = "";
            this.checked = false;
            this.textContent = "";
            this.className = "";
            this.options = [];
            this.validity = { badInput: false };
            if (tag === "select") {
              const owner = this;
              Object.defineProperty(this, "value", {
                get() {
                  return owner.options.find((option) => option.selected)?.value ?? "";
                },
                set(next) {
                  owner.options.forEach((option) => {
                    option.selected = option.value === String(next);
                  });
                },
              });
            } else {
              this.value = "";
            }
            const self = this;
            this.classList = {
              add: (...names) => {
                const set = new Set(self.className.split(/\s+/).filter(Boolean));
                names.forEach((name) => set.add(name));
                self.className = [...set].join(" ");
              },
              contains: (name) => self.className.split(/\s+/).includes(name),
            };
          }
          get classListContains() { return null; }
          append(...nodes) {
            for (const node of nodes) {
              this.children.push(node);
              if (this.tagName === "SELECT" && node.selected !== undefined) this.options.push(node);
            }
          }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          setAttribute(name, value) { this.attributes[name] = String(value); }
          getAttribute(name) { return this.attributes[name]; }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatchEvent(event) { for (const handler of this.listeners[event.type] || []) handler(event); return true; }
          dispatch(name) { for (const handler of this.listeners[name] || []) handler({ type: name }); }
          get selectedOptions() { return this.options.filter((option) => option.selected); }
          closest() { return null; }
          setCustomValidity() {}
          reportValidity() {}
          checkValidity() { return true; }
        }

        globalThis.document = { createElement: (tag) => new FakeElement(tag) };
        globalThis.Option = function Option(text, value) {
          return { textContent: text, value: String(value), selected: false };
        };

        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.CommandForm = CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const matches = (element, selector) => {
          const match = selector.match(/^\[data-([a-zA-Z-]+)(?:="([^"]*)")?\]$/);
          if (!match || !element.dataset) return false;
          const property = match[1].replace(/-([a-z])/g, (_all, char) => char.toUpperCase());
          if (match[2] === undefined) return element.dataset[property] !== undefined;
          return element.dataset[property] === match[2];
        };
        const collect = (node, out = []) => {
          for (const child of node.children || []) {
            out.push(child);
            collect(child, out);
          }
          return out;
        };
        const container = new FakeElement("div");
        container.querySelectorAll = (selector) => collect(container).filter((node) => matches(node, selector));
        container.querySelector = (selector) => container.querySelectorAll(selector)[0] || null;

        const catalog = { fieldsFor: (command) => command.fields, optionsFor: (field) => field.options };
        const command = {
          id: "measure-log",
          presentation: null,
          fields: [
            { name: "channels", type: "multi-enum", options: ["1", "2", "3", "4"], serialize: "csv" },
            { name: "items", type: "multi-enum", options: ["vpp", "frequency", "period"], serialize: "csv", default: ["vpp", "frequency"] },
            { name: "pairs", type: "string" },
            { name: "stop_on_error", type: "boolean", default: false },
            { name: "enabled_setting", type: "boolean" },
          ],
        };
        const form = new globalThis.CommandForm(container, catalog);
        form.render(command);

        const byField = (name) => collect(container).find((node) => node.dataset?.field === name);
        const boxesFor = (name) => collect(container).filter((node) => node.dataset?.multiFor === name);
        const toggleChip = (box) => { box.checked = !box.checked; box.dispatchEvent({ type: "change" }); };

        const channelsWrapper = container.children.find((node) => node.classList.contains("field-multi"));
        assert.ok(channelsWrapper, "multi-enum wrapper should carry the full-width class");
        assert.equal(channelsWrapper.tagName, "DIV");

        const channelsSelect = byField("channels");
        assert.equal(channelsSelect.multiple, true);
        assert.equal(channelsSelect.dataset.multiSource, "true");
        assert.equal(channelsSelect.getAttribute("aria-hidden"), "true");
        assert.equal(channelsSelect.tabIndex, -1);
        assert.equal(channelsSelect.className, "visually-hidden");

        const channelBoxes = boxesFor("channels");
        assert.deepEqual(channelBoxes.map((box) => box.value), ["1", "2", "3", "4"]);
        assert.equal(channelBoxes.every((box) => box.checked === false), true);

        const itemBoxes = boxesFor("items");
        assert.deepEqual(
          itemBoxes.filter((box) => box.checked).map((box) => box.value),
          ["vpp", "frequency"],
        );

        const stopError = byField("stop_on_error");
        assert.equal(stopError.tagName, "INPUT");
        assert.equal(stopError.type, "checkbox");
        assert.equal(stopError.checked, false);
        const booleanWrapper = collect(container).find((node) =>
          node.classList?.contains("field-boolean"));
        assert.ok(booleanWrapper, "plain two-state boolean should carry the compact class");
        assert.equal(
          booleanWrapper.children.find((node) => node.type === "checkbox"),
          stopError,
        );
        assert.equal(booleanWrapper.children.some((node) => node.tagName === "SPAN"), true);

        const settingBoolean = byField("enabled_setting");
        assert.equal(settingBoolean.tagName, "SELECT");
        assert.deepEqual(settingBoolean.options.map((option) => option.value), ["", "true", "false"]);

        toggleChip(channelBoxes[0]);
        toggleChip(channelBoxes[2]);
        toggleChip(itemBoxes[1]);
        assert.equal(channelsSelect.dataset.dirty, "true");
        assert.equal(form.isDirty(), true);
        assert.deepEqual(form.values(), {
          channels: "1,3",
          items: "vpp",
          stop_on_error: false,
        });

        stopError.checked = true;
        stopError.dispatchEvent({ type: "change" });
        assert.deepEqual(form.values().stop_on_error, true);
        stopError.checked = false;
        stopError.dispatchEvent({ type: "change" });

        const snapshot = form.draft();
        toggleChip(channelBoxes[0]);
        form.restoreDraft(snapshot);
        assert.deepEqual(
          channelsSelect.selectedOptions.map((option) => option.value),
          ["1", "3"],
        );
        assert.deepEqual(
          boxesFor("channels").filter((box) => box.checked).map((box) => box.value),
          ["1", "3"],
        );

        form.setDisabled(true);
        assert.equal(channelsSelect.disabled, true);
        assert.equal(channelBoxes.every((box) => box.disabled), true);
        form.setDisabled(false);
        assert.equal(channelBoxes.some((box) => box.disabled), false);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(command_form_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_live_command_gating_allows_identify_retry_until_identity_is_ready() -> None:
    app_source = read_static("app.js")
    command_available = extract_function_declaration(app_source, "function commandAvailable(command)")
    script = textwrap.dedent(
        f'''
        import assert from "node:assert/strict";
        const catalog = {{}};
        const commands = [
          {{ id: "identify", modes: ["live", "simulate"] }},
          {{ id: "run", modes: ["live", "simulate"] }},
          {{ id: "list-resources", modes: ["live", "simulate", "dry-run"] }},
        ];
        let context = {{ mode: "live", resource: "USB0::TEST::INSTR", model_id: null }};
        let identityReady = false;
        const deviceResource = {{ hasCurrentIdentity: () => identityReady }};
        {command_available}

        assert.equal(commandAvailable("list-resources"), true);
        assert.equal(commandAvailable("identify"), true);
        assert.equal(commandAvailable("run"), false);
        identityReady = true;
        assert.equal(commandAvailable("run"), true);
        context = {{ ...context, resource: null }};
        assert.equal(commandAvailable("identify"), false);
        assert.equal(commandAvailable("run"), false);
        context = {{ mode: "simulate", resource: null, model_id: "keysight-dsox4024a" }};
        assert.equal(commandAvailable("run"), true);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_empty_scan_has_a_distinct_compact_detection_presentation() -> None:
    source = read_static("device-resource.js")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    detection_summary = extract_function(source, "  detectionSummary(context)")
    empty_branch = 'this.scanStatus === "empty"'
    assert empty_branch in detection_summary
    assert 'translate("device.detection.noResources")' in detection_summary
    assert detection_summary.index("hasCurrentIdentity") < detection_summary.index(empty_branch)
    assert 'this.scanStatus = resources.length ? "scanned" : "empty";' in source
    assert '"device.detection.noResources": "Detection status: no resources found"' in english
    assert '"device.detection.noResources": "偵測狀態：未找到資源"' in chinese
    assert '"device.detection.notIdentified"' in detection_summary


def test_resource_controls_match_the_powers_initial_presentation() -> None:
    html = read_static("index.html")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert 'data-i18n="device.resource">VISA Resource</span>' in html
    assert 'data-i18n-placeholder="device.resourcePlaceholder" placeholder="Waiting Scan"' in html
    assert 'data-i18n="device.liveResourcePlaceholder">Scan to load live resources</option>' in html
    assert 'data-i18n="device.liveResource">Live Resource</span>' in html
    assert 'data-i18n="device.scan">Scan Device</button>' in html
    assert '"device.resourcePlaceholder": "Waiting Scan"' in english
    assert '"device.resource": "VISA Resource"' in english
    assert '"device.liveResource": "Live Resource"' in english
    assert '"device.liveResourcePlaceholder": "Scan to load live resources"' in english
    assert '"device.scan": "Scan Device"' in english
    assert '"device.resourcePlaceholder": "等待掃描"' in chinese
    assert '"device.liveResource": "即時資源"' in chinese
    assert '"device.liveResourcePlaceholder": "掃描後載入即時資源"' in chinese
    assert '"device.scan": "掃描裝置"' in chinese


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_resource_controls_follow_execution_mode_and_scan_guard() -> None:
    device_path = STATIC_ROOT / "device-resource.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor() {
            this.children = [];
            this.hidden = false;
            this.disabled = false;
            this.value = "";
            this.checked = true;
            this.selectedOptions = [{ textContent: "" }];
          }
          addEventListener() {}
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) { this.children.push(...nodes); }
          setAttribute() {}
        }

        let mode = "live";
        let submissions = 0;
        let resolveScan;
        const runJob = async (command, parameters, context) => {
          assert.equal(command, "list-resources");
          assert.deepEqual(parameters, { live_only: true });
          assert.equal(context.mode, "live");
          submissions += 1;
          return new Promise((resolve) => { resolveScan = resolve; });
        };
        const getExecutionContext = () => ({
          mode,
          resource: null,
          model_id: "keysight-dsox4024a",
        });
        const translate = (key) => key;
        globalThis.testRunJob = runJob;
        globalThis.testGetExecutionContext = getExecutionContext;
        globalThis.testTranslate = translate;
        globalThis.document = { addEventListener() {} };
        globalThis.Option = function Option(text, value) {
          return { textContent: text, value: String(value), dataset: {} };
        };

        const source = [
          "const runJob = globalThis.testRunJob;",
          "const getExecutionContext = globalThis.testGetExecutionContext;",
          "const translate = globalThis.testTranslate;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.deviceApi = { DeviceResource };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const node = () => new FakeNode();
        const elements = {
          mode: [node()],
          model: node(),
          resource: node(),
          resourceList: node(),
          scan: node(),
          settings: node(),
          settingsPanel: node(),
          body: node(),
          deviceCollapse: node(),
          modeBadge: node(),
          summary: node(),
          status: node(),
        };
        elements.settingsPanel.hidden = true;
        const device = new globalThis.deviceApi.DeviceResource(
          elements,
          () => {},
          () => {},
          () => {},
          () => {},
        );
        const assertControls = (disabled) => {
          assert.equal(elements.resource.disabled, disabled);
          assert.equal(elements.resourceList.disabled, disabled);
          assert.equal(elements.scan.disabled, disabled);
        };

        assertControls(false);
        assert.equal(elements.model.disabled, true);

        mode = "simulate";
        device.refresh();
        assertControls(true);
        assert.equal(elements.model.disabled, false);
        await device.scan();
        assert.equal(submissions, 0);

        mode = "dry-run";
        device.refresh();
        assertControls(true);
        await device.scan();
        assert.equal(submissions, 0);

        mode = "live";
        device.refresh();
        assertControls(false);

        device.setExternalBusy(true);
        assertControls(true);
        assert.equal(elements.mode[0].disabled, true);
        await device.scan();
        assert.equal(submissions, 0);
        device.setExternalBusy(false);
        assertControls(false);

        const scanPromise = device.scan();
        assert.equal(elements.scan.disabled, true);
        mode = "simulate";
        device.refresh();
        assert.equal(elements.scan.disabled, true);
        resolveScan({
          status: "completed",
          result: { result: { resources: [] } },
        });
        await scanPromise;
        assert.equal(elements.scan.disabled, true);
        assert.equal(submissions, 1);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(device_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_empty_scan_keeps_a_localized_non_resource_option() -> None:
    source = read_static("device-resource.js")
    render_resource_list = extract_function(source, "  renderResourceList(resources) {")

    assert "this.elements.resourceList.replaceChildren();" in render_resource_list
    assert 'if (!resources.length)' in render_resource_list
    assert 'new Option(translate("device.liveResourceNoResources"), "")' in render_resource_list
    assert 'option.dataset.i18n = "device.liveResourceNoResources";' in render_resource_list
    assert "function resourceName(resource)" in source
    assert "function resourceLabel(resource)" in source
    assert "new Option(resourceLabel(resource), name)" in render_resource_list


def test_scan_requests_live_only_and_preserves_structured_resource_identity() -> None:
    source = read_static("device-resource.js")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    scan = extract_function(source, "async scan()")
    assert '"list-resources",' in scan
    assert "{ live_only: true }," in scan
    assert "resourceName(resources[0])" in scan
    assert '"device.liveResourceNoResources": "No live resources found"' in english
    assert '"device.liveResourceNoResources": "未找到即時資源"' in chinese


def test_scan_uses_the_common_job_history_flow_before_resource_updates() -> None:
    device_source = read_static("device-resource.js")
    jobs_source = read_static("jobs.js")
    app_source = read_static("app.js")
    scan = extract_function(device_source, "async scan()")

    assert 'import { runJob } from "/static/jobs.js";' in device_source
    assert "const job = await runJob(" in scan
    assert '"list-resources",' in scan
    assert "this.onCommandStateChange({ status: updated.status });" in scan
    assert "this.onJobUpdate(updated);" in scan
    assert "let backendJobReceived = false;" in scan
    assert "if (!backendJobReceived) this.onScanError(error.message || String(error));" in scan
    assert "submitJob(" not in scan
    assert "getJob(" not in scan
    assert "const resources = job.result?.result?.resources || [];" in scan

    assert "onUpdate({" in jobs_source
    assert "job_id: submitted.job_id" in jobs_source
    assert "command," in jobs_source
    assert 'status: submitted.status || "queued"' in jobs_source
    assert '}, (scanJob) => {' in app_source
    assert 'resultPresentation = { kind: "job", job: scanJob, message: null };' in app_source
    assert '}, (scanError) => {' in app_source
    assert 'command: "list-resources"' in app_source
    assert "renderCurrentResult();" in app_source


def test_selected_resource_refresh_uses_a_formal_identify_job_flow() -> None:
    device_source = read_static("device-resource.js")
    app_source = read_static("app.js")
    refresh = extract_function(app_source, "async function evaluateResourceLiveSupport(commandContext)")
    present = extract_function(app_source, "function presentSelectedResourceJob(job, commandContext)")

    assert "onSelectedResourceChange = () => {}," in device_source
    assert "this.onSelectedResourceChange(this.context());" in device_source
    assert "refreshSelectedResourceContext(selectedContext);" in app_source
    assert "let pendingResourceLiveSupport = null;" in app_source
    assert 'runJob("identify", {}, commandContext' in refresh
    assert "sameExecutionContext(context, commandContext)" in app_source
    assert "presentSelectedResourceJob(updated, commandContext);" in refresh
    assert "updateIdentity(job, commandContext);" in present
    assert "renderCurrentResult();" in present
    assert "renderJob(elements.results, job, null);" in present
    assert "resources[1]" not in extract_function(device_source, "async scan()")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_selected_resource_identify_serializes_latest_requested_context() -> None:
    app_source = read_static("app.js")
    declarations = "\n".join(
        extract_function_declaration(app_source, signature)
        for signature in (
            "async function refreshSelectedResourceContext(selectedContext)",
            "async function evaluateResourceLiveSupport(commandContext)",
            "async function finishResourceLiveSupportEvaluation(jobId)",
            "async function refreshRequestedResourceLiveSupport(completed)",
            "function updateIdentity(job, commandContext)",
            "function presentSelectedResourceJob(job, commandContext)",
            "function sameExecutionContext(left, right)",
        )
    )
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";

        const contextFor = (resource) => ({
          mode: "live",
          resource,
          model_id: "keysight-dsox4024a",
        });
        let context = contextFor("RESOURCE-A");
        let executing = false;
        let pendingResourceLiveSupport = null;
        let resultPresentation = { kind: "empty", job: null, message: null };
        const elements = { results: {} };
        const submissions = [];
        const controllers = [];
        const states = [];
        const history = new Set();
        const currentResults = [];
        const clientErrors = [];
        const identities = [];
        const updateCommandSupport = () => {};
        const renderWorkspace = () => {};
        const scheduleEditorRead = () => {};
        const captureWorkspaceResult = () => {};
        const buildWorkspaceContext = () => ({});
        const renderLiveData = () => {};
        const updateAvailability = () => {};
        const setCommandState = (state) => states.push({ resource: context.resource, ...state });
        const renderCurrentResult = () => {
          const job = resultPresentation.job;
          if (job) history.add(job.job_id);
          if (resultPresentation.kind === "error") clientErrors.push(resultPresentation);
          currentResults.push({
            resource: context.resource,
            jobId: job?.job_id || null,
            status: job?.status || null,
          });
        };
        const renderJob = (_target, job) => history.add(job.job_id);
        const deviceResource = {
          setIdentity(idn, associatedContext) {
            identities.push({ resource: associatedContext.resource, model: idn.model });
          },
        };
        const runJob = (command, parameters, commandContext, onUpdate) => {
          assert.equal(command, "identify");
          assert.deepEqual(parameters, {});
          submissions.push(commandContext.resource);
          const jobId = `identify-${commandContext.resource}`;
          onUpdate({ job_id: jobId, command, status: "queued" });
          onUpdate({ job_id: jobId, command, status: "running" });
          return new Promise((resolve) => controllers.push({ jobId, onUpdate, resolve }));
        };
        const settle = async () => {
          await Promise.resolve();
          await Promise.resolve();
        };
        '''
    ) + declarations + textwrap.dedent(
        r'''

        executing = true;
        await refreshSelectedResourceContext(contextFor("RESOURCE-A"));
        assert.deepEqual(submissions, []);
        executing = false;

        const identifyA = refreshSelectedResourceContext(contextFor("RESOURCE-A"));
        await settle();
        assert.deepEqual(submissions, ["RESOURCE-A"]);

        context = contextFor("RESOURCE-B");
        await refreshSelectedResourceContext(context);
        assert.deepEqual(submissions, ["RESOURCE-A"]);
        assert.equal(states.at(-1).resource, "RESOURCE-B");
        assert.equal(states.at(-1).status, "queued");

        const failedA = {
          job_id: "identify-RESOURCE-A",
          command: "identify",
          status: "failed",
          error: { type: "UnsupportedModelError", message: "Unsupported physical oscilloscope model: E3646A" },
        };
        controllers[0].onUpdate(failedA);
        controllers[0].resolve(failedA);
        await settle();
        assert.deepEqual(submissions, ["RESOURCE-A", "RESOURCE-B"]);
        assert.notEqual(states.at(-1).status, "failed");
        assert.equal(states.at(-1).resource, "RESOURCE-B");
        assert.equal(history.has("identify-RESOURCE-A"), true);
        assert.deepEqual(identities, []);

        const completedB = {
          job_id: "identify-RESOURCE-B",
          command: "identify",
          status: "completed",
          result: { result: { idn: { model: "DSO-X 4034A" } } },
        };
        controllers[1].onUpdate(completedB);
        controllers[1].resolve(completedB);
        await identifyA;

        assert.deepEqual(submissions, ["RESOURCE-A", "RESOURCE-B"]);
        assert.equal(history.has("identify-RESOURCE-B"), true);
        assert.equal(identities.length > 0, true);
        assert.equal(
          identities.every((item) => item.resource === "RESOURCE-B" && item.model === "DSO-X 4034A"),
          true,
        );
        assert.equal(
          currentResults.some((item) => item.resource === "RESOURCE-B"
            && item.jobId === "identify-RESOURCE-A"
            && item.status === "failed"),
          false,
        );
        assert.equal(currentResults.at(-1).jobId, "identify-RESOURCE-B");
        assert.equal(states.at(-1).status, "completed");
        assert.equal(submissions.includes("RESOURCE-C"), false);
        assert.deepEqual(clientErrors, []);
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
def test_stale_identify_submission_failure_is_kept_before_requested_identify_runs() -> None:
    app_source = read_static("app.js")
    declarations = "\n".join(
        extract_function_declaration(app_source, signature)
        for signature in (
            "async function refreshSelectedResourceContext(selectedContext)",
            "async function evaluateResourceLiveSupport(commandContext)",
            "async function finishResourceLiveSupportEvaluation(jobId)",
            "async function refreshRequestedResourceLiveSupport(completed)",
            "function updateIdentity(job, commandContext)",
            "function presentSelectedResourceJob(job, commandContext)",
            "function sameExecutionContext(left, right)",
        )
    )
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";

        const contextFor = (resource) => ({
          mode: "live",
          resource,
          model_id: "keysight-dsox4024a",
        });
        let context = contextFor("RESOURCE-A");
        let executing = false;
        let pendingResourceLiveSupport = null;
        let resultPresentation = { kind: "empty", job: null, message: null };
        const elements = { results: {} };
        const events = [];
        const submissions = [];
        const states = [];
        const clientErrors = [];
        const backendJobs = new Set();
        const identities = [];
        const updateCommandSupport = () => {};
        const renderWorkspace = () => {};
        const scheduleEditorRead = () => {};
        const captureWorkspaceResult = () => {};
        const buildWorkspaceContext = () => ({});
        let rejectA;
        const renderLiveData = () => {};
        const updateAvailability = () => {};
        const setCommandState = (state) => states.push({ resource: context.resource, ...state });
        const renderCurrentResult = () => {
          if (resultPresentation.kind === "error") {
            events.push("client-error-A");
            clientErrors.push({ ...resultPresentation });
          } else if (resultPresentation.job) {
            backendJobs.add(resultPresentation.job.job_id);
          }
        };
        const renderJob = (_target, job) => backendJobs.add(job.job_id);
        const deviceResource = {
          setIdentity(idn, associatedContext) {
            identities.push({ resource: associatedContext.resource, model: idn.model });
          },
        };
        const runJob = (command, parameters, commandContext, onUpdate) => {
          assert.equal(command, "identify");
          assert.deepEqual(parameters, {});
          submissions.push(commandContext.resource);
          events.push(`submit-${commandContext.resource}`);
          if (commandContext.resource === "RESOURCE-A") {
            return new Promise((_resolve, reject) => { rejectA = reject; });
          }
          const completed = {
            job_id: "identify-RESOURCE-B",
            command,
            status: "completed",
            result: { result: { idn: { model: "DSO-X 4034A" } } },
          };
          onUpdate({ job_id: completed.job_id, command, status: "queued" });
          onUpdate(completed);
          return Promise.resolve(completed);
        };
        '''
    ) + declarations + textwrap.dedent(
        r'''

        const identifyA = refreshSelectedResourceContext(contextFor("RESOURCE-A"));
        await Promise.resolve();
        assert.deepEqual(submissions, ["RESOURCE-A"]);

        context = contextFor("RESOURCE-B");
        await refreshSelectedResourceContext(context);
        assert.deepEqual(submissions, ["RESOURCE-A"]);
        assert.equal(states.at(-1).resource, "RESOURCE-B");
        assert.equal(states.at(-1).status, "queued");

        rejectA(new Error("HTTP 503: temporary failure"));
        await identifyA;

        assert.deepEqual(events.slice(0, 3), ["submit-RESOURCE-A", "client-error-A", "submit-RESOURCE-B"]);
        assert.deepEqual(submissions, ["RESOURCE-A", "RESOURCE-B"]);
        assert.equal(clientErrors.length, 1);
        assert.equal(clientErrors[0].kind, "error");
        assert.equal(clientErrors[0].command, "identify");
        assert.equal(clientErrors[0].message, "HTTP 503: temporary failure");
        assert.equal(clientErrors[0].job, null);
        assert.equal("job_id" in clientErrors[0], false);
        assert.equal(
          states.some((state) => state.resource === "RESOURCE-B" && state.status === "failed"),
          false,
        );
        assert.deepEqual([...backendJobs], ["identify-RESOURCE-B"]);
        assert.equal(identities.length > 0, true);
        assert.equal(
          identities.every((item) => item.resource === "RESOURCE-B" && item.model === "DSO-X 4034A"),
          true,
        );
        assert.equal(states.at(-1).status, "completed");
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
def test_common_job_runner_reports_scan_submission_and_terminal_state() -> None:
    jobs_path = STATIC_ROOT / "jobs.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const submitJob = async (payload) => {
          assert.equal(payload.command, "list-resources");
          assert.deepEqual(payload.parameters, { live_only: true });
          return { job_id: "scan-job", status: "queued" };
        };
        const getJob = async (jobId) => ({
          job_id: jobId,
          command: "list-resources",
          status: "completed",
          result: { result: { resources: ["USB0::1", "USB0::2"] } },
        });
        const cancelJob = async () => ({});
        globalThis.testSubmitJob = submitJob;
        globalThis.testGetJob = getJob;
        globalThis.testCancelJob = cancelJob;

        const source = [
          "const submitJob = globalThis.testSubmitJob;",
          "const getJob = globalThis.testGetJob;",
          "const cancelJob = globalThis.testCancelJob;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export async function /gm, "async function ")
          + "\nglobalThis.jobsApi = { runJob };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const updates = [];
        const job = await globalThis.jobsApi.runJob(
          "list-resources",
          { live_only: true },
          { mode: "live", resource: null, model_id: "keysight-dsox4024a" },
          (updated) => updates.push(updated),
        );
        assert.equal(job.job_id, "scan-job");
        assert.deepEqual(
          updates.map(({ job_id, command, status }) => ({ job_id, command, status })),
          [
            { job_id: "scan-job", command: "list-resources", status: "queued" },
            { job_id: "scan-job", command: "list-resources", status: "completed" },
          ],
        );
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(jobs_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_scan_submit_failure_reports_raw_error_and_preserves_scan_failure_state() -> None:
    device_path = STATIC_ROOT / "device-resource.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor() {
            this.children = [];
            this.hidden = false;
            this.disabled = false;
            this.value = "";
            this.checked = true;
            this.selectedOptions = [{ textContent: "" }];
          }
          addEventListener() {}
          replaceChildren(...nodes) { this.children = [...nodes]; }
          setAttribute() {}
        }

        const rawError = "HTTP 503 raw submit failure";
        const runJob = async () => { throw new Error(rawError); };
        const getExecutionContext = () => ({ mode: "live", resource: null, model_id: "keysight-dsox4024a" });
        const translate = (key) => key;
        globalThis.testRunJob = runJob;
        globalThis.testGetExecutionContext = getExecutionContext;
        globalThis.testTranslate = translate;
        globalThis.document = { addEventListener() {} };

        const source = [
          "const runJob = globalThis.testRunJob;",
          "const getExecutionContext = globalThis.testGetExecutionContext;",
          "const translate = globalThis.testTranslate;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.deviceApi = { DeviceResource };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const node = () => new FakeNode();
        const elements = {
          mode: [node()],
          model: node(),
          resource: node(),
          resourceList: node(),
          scan: node(),
          settings: node(),
          settingsPanel: node(),
          body: node(),
          deviceCollapse: node(),
          modeBadge: node(),
          summary: node(),
          status: node(),
        };
        elements.settingsPanel.hidden = true;
        const states = [];
        const errors = [];
        const device = new globalThis.deviceApi.DeviceResource(
          elements,
          () => {},
          (state) => states.push(state),
          () => {},
          (error) => errors.push(error),
        );
        await device.scan();

        assert.deepEqual(errors, [rawError]);
        assert.equal(device.scanStatus, "failed");
        assert.equal(device.statusError, rawError);
        assert.equal(elements.scan.disabled, false);
        assert(states.some((state) => state.status === "failed"));
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(device_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_scan_selection_notifies_identify_refresh_for_scan_and_manual_selection() -> None:
    device_path = STATIC_ROOT / "device-resource.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(value = "") {
            this.children = [];
            this.listeners = {};
            this.hidden = false;
            this.disabled = false;
            this.value = value;
            this.checked = true;
            this.selectedOptions = [{ textContent: "" }];
          }
          addEventListener(name, handler) {
            (this.listeners[name] ||= []).push(handler);
          }
          dispatch(name) {
            for (const handler of this.listeners[name] || []) handler();
          }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) { this.children.push(...nodes); }
          setAttribute() {}
        }

        const runJob = async (_command, _parameters, _context, onUpdate) => {
          const completed = {
            job_id: "scan-job",
            command: "list-resources",
            status: "completed",
            result: { result: { resources: [
              {
                name: "ASRL7::INSTR",
                interface: "ASRL",
                idn: { manufacturer: "Agilent Technologies", model: "E3646A" },
              },
              {
                name: "USB0::A::INSTR",
                interface: "USB",
                idn: { manufacturer: "AGILENT TECHNOLOGIES", model: "DSO-X 4034A" },
              },
              {
                name: "USB0::B::INSTR",
                interface: "USB",
                idn: { manufacturer: "Agilent Technologies", model: "33512B" },
              },
            ] } },
          };
          onUpdate({ job_id: completed.job_id, command: completed.command, status: "queued" });
          onUpdate(completed);
          return completed;
        };
        const getExecutionContext = () => ({
          mode: "live",
          resource: globalThis.currentResource.value.trim() || null,
          model_id: "keysight-dsox4024a",
        });
        const translate = (key) => key;
        globalThis.currentResource = new FakeNode();
        globalThis.testRunJob = runJob;
        globalThis.testGetExecutionContext = getExecutionContext;
        globalThis.testTranslate = translate;
        globalThis.document = { addEventListener() {} };
        globalThis.Option = function Option(text, value) {
          return { textContent: text, value: String(value) };
        };

        const source = [
          "const runJob = globalThis.testRunJob;",
          "const getExecutionContext = globalThis.testGetExecutionContext;",
          "const translate = globalThis.testTranslate;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.deviceApi = { DeviceResource };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const node = () => new FakeNode();
        const elements = {
          mode: [node()],
          model: node(),
          resource: globalThis.currentResource,
          resourceList: node(),
          scan: node(),
          settings: node(),
          settingsPanel: node(),
          body: node(),
          deviceCollapse: node(),
          modeBadge: node(),
          summary: node(),
          status: node(),
        };
        elements.settingsPanel.hidden = true;
        const selectedResources = [];
        const device = new globalThis.deviceApi.DeviceResource(
          elements,
          () => {},
          () => {},
          () => {},
          () => {},
          (context) => selectedResources.push(context.resource),
        );

        await device.scan();
        assert.equal(elements.resource.value, "ASRL7::INSTR");
        assert.deepEqual(selectedResources, ["ASRL7::INSTR"]);
        assert.deepEqual(
          elements.resourceList.children.map(({ value, textContent }) => ({ value, textContent })),
          [
            {
              value: "ASRL7::INSTR",
              textContent: "ASRL7::INSTR - Agilent Technologies - E3646A",
            },
            {
              value: "USB0::A::INSTR",
              textContent: "USB0::A::INSTR - AGILENT TECHNOLOGIES - DSO-X 4034A",
            },
            {
              value: "USB0::B::INSTR",
              textContent: "USB0::B::INSTR - Agilent Technologies - 33512B",
            },
          ],
        );

        elements.resourceList.value = "USB0::A::INSTR";
        elements.resourceList.dispatch("change");
        assert.equal(elements.resource.value, "USB0::A::INSTR");
        assert.deepEqual(selectedResources, ["ASRL7::INSTR", "USB0::A::INSTR"]);
        assert.equal(selectedResources.includes("USB0::B::INSTR"), false);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(device_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_list_resources_command_exposes_a_boolean_live_only_parameter() -> None:
    from scopes_tool_webui.command_catalog import COMMANDS
    from scopes_tool_webui.commands import WebUIRequestError, validate_job_request

    list_resources = next(entry for entry in COMMANDS if entry["id"] == "list-resources")
    assert list_resources["hidden"] is True
    live_only_field = next(field for field in list_resources["fields"] if field["name"] == "live_only")
    assert live_only_field["type"] == "boolean"
    assert live_only_field["default"] is False

    accepted_default = validate_job_request({"command": "list-resources", "mode": "live"})
    assert accepted_default["parameters"]["live_only"] is False

    accepted_true = validate_job_request({"command": "list-resources", "mode": "live", "parameters": {"live_only": True}})
    assert accepted_true["parameters"]["live_only"] is True

    with pytest.raises(WebUIRequestError, match="live_only must be a boolean"):
        validate_job_request({"command": "list-resources", "mode": "live", "parameters": {"live_only": "false"}})


def test_scan_failure_is_included_in_the_compact_device_presentation() -> None:
    source = read_static("device-resource.js")

    assert 'this.scanStatus = "failed";' in source
    assert '"device.detection.scanFailed"' in source
    assert "this.elements.summary.title = summary;" in source


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
    assert "formRevision: genericFormRevision" in refresh_handler
    assert "function scheduleEditorRead()" not in source

    cancel_handler = source.split('elements.cancel.addEventListener("click"', 1)[1].split(
        "\n  });", 1,
    )[0]
    assert "await requestCancel(currentJobId);" in cancel_handler
    assert 'elements.cancel.classList.remove("hidden");' in source
    assert 'elements.cancel.classList.add("hidden");' in source


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_query_selector_change_invalidates_pending_generic_refresh() -> None:
    run_generic_form_ownership_behavior(
        r'''
        syncCommandSelection();
        const submittedRevision = genericFormRevision;
        const refresh = executeCommand("channel-scale", { action: "query", channel: 1 }, {
          intent: "readback",
          formRevision: submittedRevision,
        });
        await Promise.resolve();
        commandForm.renderOptions.onQueryFieldChange("channel");
        assert.equal(submissions.length, 1);

        complete(0);
        await refresh;

        assert.deepEqual(commandForm.syncCalls, []);
        assert.deepEqual(workspaceResults, ["job-1"]);
        assert.deepEqual(completedResults, ["job-1"]);
        '''
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_generic_rerender_rejects_stale_apply_form_updates() -> None:
    run_generic_form_ownership_behavior(
        r'''
        syncCommandSelection();
        const apply = executeCommand("channel-scale", {
          action: "set", channel: 1, volts_per_division: 0.5,
        }, { intent: "apply", formRevision: genericFormRevision });
        await Promise.resolve();
        assert.deepEqual(commandForm.disabledCalls, [true]);

        selectedCommand = otherCommand;
        syncCommandSelection();
        selectedCommand = channelScale;
        syncCommandSelection();
        complete(0);
        await apply;

        assert.equal(commandForm.clearCalls, 0);
        assert.deepEqual(commandForm.syncCalls, []);
        assert.deepEqual(commandForm.disabledCalls, []);
        assert.equal(commandForm.dirty, true);
        assert.deepEqual(workspaceResults, ["job-1"]);
        assert.deepEqual(completedResults, ["job-1"]);
        '''
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_current_generic_form_still_syncs_refresh_and_apply() -> None:
    run_generic_form_ownership_behavior(
        r'''
        syncCommandSelection();
        const refresh = executeCommand("channel-scale", { action: "query", channel: 1 }, {
          intent: "readback",
          formRevision: genericFormRevision,
        });
        await Promise.resolve();
        complete(0);
        await refresh;
        assert.deepEqual(commandForm.syncCalls, [["job-1", true]]);
        assert.equal(commandForm.clearCalls, 0);

        const apply = executeCommand("channel-scale", {
          action: "set", channel: 1, volts_per_division: 0.5,
        }, { intent: "apply", formRevision: genericFormRevision });
        await Promise.resolve();
        complete(1);
        await apply;
        assert.deepEqual(commandForm.syncCalls, [["job-1", true], ["job-2", false]]);
        assert.equal(commandForm.clearCalls, 1);
        assert.deepEqual(commandForm.disabledCalls, [true, false]);
        assert.deepEqual(workspaceResults, ["job-1", "job-2"]);
        assert.deepEqual(completedResults, ["job-1", "job-2"]);
        '''
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_submission_without_form_revision_cannot_update_generic_form() -> None:
    run_generic_form_ownership_behavior(
        r'''
        syncCommandSelection();
        const apply = executeCommand("channel-scale", {
          action: "set", channel: 1, volts_per_division: 0.5,
        }, { intent: "apply" });
        await Promise.resolve();
        assert.deepEqual(commandForm.disabledCalls, []);

        complete(0);
        await apply;

        assert.equal(commandForm.clearCalls, 0);
        assert.deepEqual(commandForm.syncCalls, []);
        assert.deepEqual(commandForm.disabledCalls, []);
        assert.deepEqual(workspaceResults, ["job-1"]);
        assert.deepEqual(completedResults, ["job-1"]);
        '''
    )


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
        const captureWorkspaceResult = () => {};
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

        deviceResource = { scanInProgress: true };
        assert.equal(await executeCommand("run", { source: 3 }, {}), null);
        assert.equal(submissions.length, 1);
        deviceResource.scanInProgress = false;
        pendingResourceLiveSupport = {};
        assert.equal(await executeCommand("run", { source: 4 }, {}), null);
        assert.equal(submissions.length, 1);
        pendingResourceLiveSupport = null;

        const second = await executeCommand("run", { source: 5 }, {});
        assert.equal(second.job_id, "job-2");
        assert.equal(submissions.length, 2);
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
    app_source = read_static("app.js")
    html = read_static("index.html")

    assert app_source.count("headerActions: elements.workspaceHeaderActions,") == 5
    assert 'id="refresh-button"' not in html.split('<div class="workspace-content">', 1)[1]


def test_live_mode_badge_is_neutral_and_utility_glyphs_are_centered() -> None:
    styles = read_static("styles.css")
    icon_button = extract_css_rule(styles, ".icon-button")
    utility_button = extract_css_rule(styles, ".utility-icon-button")

    assert "display: inline-flex;" in icon_button
    assert "align-items: center;" in icon_button
    assert "justify-content: center;" in icon_button
    assert "width: 32px;" in icon_button
    assert "min-width: 32px;" in icon_button
    assert "height: 32px;" in icon_button
    assert "min-height: 32px;" in icon_button
    assert "padding: 0;" in icon_button
    assert "font-size:" not in icon_button
    assert "line-height:" not in icon_button
    assert "border-radius: 50%;" in utility_button
    assert ".execution-mode-badge.mode-live { border-color: var(--line-strong); background: transparent; color: var(--muted); }" in styles


def test_hidden_elements_override_component_display_rules() -> None:
    styles = read_static("styles.css")

    assert "[hidden] { display: none !important; }" in styles


def test_number_fields_allow_fractional_html_values() -> None:
    source = read_static("command-form.js")

    assert 'if (field.type === "number") input.step = "any";' in source


def test_summary_uses_only_scopes_supported_states() -> None:
    english = read_static("locale_en.js")

    assert '"device.summary.live": "{{mode}} / VISA resource: {{resource}} / {{detection}}"' in english
    assert '"device.detection.notScanned": "Detection status: not scanned"' in english
    assert '"device.detection.scanFailed": "Detection status: scan failed: {{error}}"' in english
    assert '"device.summary.planning": "{{mode}} / Planning model: {{model}} / Real VISA resource: not used"' in english
    assert "Expected Model guard" not in english
    assert "Connection scope" not in english


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_generic_form_rejects_partial_numbers_and_fractional_integers() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        const translate = (key) => key;
        const hasTranslation = () => false;
        globalThis.testTranslate = translate;
        globalThis.testHasTranslation = hasTranslation;

        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.formApi = { CommandForm };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const input = (name, type, value, required = false) => ({
          value,
          required,
          type: "number",
          dataset: { field: name, type },
          validity: { badInput: false },
          customValidity: "",
          reported: false,
          closest: () => null,
          setCustomValidity(message) { this.customValidity = message; },
          checkValidity() { return this.customValidity === ""; },
          reportValidity() { this.reported = true; return false; },
        });
        const valuesFor = (...elements) => {
          const container = { querySelectorAll: () => elements };
          return new globalThis.formApi.CommandForm(container, null).values();
        };

        const trailing = input("value", "number", "1abc");
        assert.equal(valuesFor(trailing), null);
        assert.equal(trailing.reported, true);

        assert.equal(valuesFor(input("value", "number", "0x10")), null);

        const fractional = input("count", "integer", "1.9");
        assert.equal(valuesFor(fractional), null);

        const required = input("count", "integer", "", true);
        assert.equal(valuesFor(required), null);

        assert.deepEqual(
          valuesFor(input("value", "number", "-1.25e2"), input("count", "integer", "19")),
          { value: -125, count: 19 },
        );

        globalThis.document = {
          createElement: (tag) => ({
            tagName: tag.toUpperCase(),
            children: [],
            dataset: {},
            value: "",
            type: "",
            required: false,
            customValidity: "",
            append(...nodes) { this.children.push(...nodes); },
            setCustomValidity(message) { this.customValidity = message; },
            checkValidity() { return this.customValidity === ""; },
            reportValidity() { this.reported = true; return false; },
            closest: () => null,
          }),
        };
        const renderedForm = new globalThis.formApi.CommandForm({}, null);
        const wrapper = renderedForm.field({
          name: "timeout_seconds",
          type: "number",
          exclusive_minimum: 0,
          required: true,
        });
        const timeout = wrapper.children[1];
        assert.equal(timeout.dataset.exclusiveMinimum, "0");
        timeout.value = "0";
        assert.equal(valuesFor(timeout), null);
        assert.equal(timeout.customValidity, "form.greaterThan");
        assert.equal(timeout.reported, true);

        timeout.value = "1e-12";
        assert.deepEqual(valuesFor(timeout), { timeout_seconds: 1e-12 });
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(command_form_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_command_help_and_common_result_labels_are_localized() -> None:
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    for key in (
        "description.action.apply",
        "description.timebase-scale",
        "form.greaterThan",
        "help.pairs",
        "help.timebase.seconds_per_division",
        "help.timebase.position_seconds",
        "results.field.seconds_per_division",
        "results.field.planned_scpi",
    ):
        assert f'"{key}":' in english
        assert f'"{key}":' in chinese


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_generic_form_applies_conditional_required_fields() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.testTranslate = (key) => key;
        globalThis.testHasTranslation = () => false;
        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.CommandForm = CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const input = (name, type, value, requiredIf = null) => ({
          value,
          required: false,
          type: type === "integer" || type === "number" ? "number" : "select-one",
          dataset: {
            field: name,
            type,
            required: "false",
            ...(requiredIf ? { requiredIf: JSON.stringify(requiredIf) } : {}),
          },
          validity: { badInput: false },
          closest: () => null,
          setCustomValidity() {},
          checkValidity() { return true; },
          reportValidity() { this.reported = true; return false; },
        });
        const action = input("action", "enum", "query");
        const value = input("volts_per_division", "number", "", [
          { field: "action", equals: "set" },
        ]);
        const hiddenValue = input("hidden_value", "number", "", [
          { field: "action", equals: "set" },
        ]);
        hiddenValue.closest = (selector) => (
          selector === "[data-visible-if-hidden=\"true\"]" ? {} : null
        );
        const fields = [action, value, hiddenValue];
        const container = {
          querySelectorAll(selector) {
            if (selector === "[data-visible-if]") return [];
            if (selector === "[data-field]") return fields;
            return [];
          },
          querySelector(selector) {
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return fields.find((field) => field.dataset.field === match?.[1]) ?? null;
          },
        };
        const form = new globalThis.CommandForm(container, null);

        form.refreshVisibility();
        assert.equal(value.required, false);
        assert.equal(hiddenValue.required, false);
        assert.deepEqual(form.values(), { action: "query" });

        action.value = "set";
        form.refreshVisibility();
        assert.equal(value.required, true);
        assert.equal(hiddenValue.required, false);
        assert.equal(form.values(), null);
        assert.equal(value.reported, true);

        value.value = "2.5";
        assert.deepEqual(form.values(), { action: "set", volts_per_division: 2.5 });
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(command_form_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_stateful_editor_readback_dirty_and_verification_flow() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.testTranslate = (key) => key;
        globalThis.testHasTranslation = () => false;
        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.CommandForm = CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const field = (name, type, value, queryField = false) => ({
          value,
          type: name === "action" ? "hidden" : "number",
          disabled: false,
          required: false,
          dataset: { field: name, type, queryField: String(queryField) },
          validity: { badInput: false },
          closest: () => null,
          setCustomValidity() {},
          checkValidity() { return true; },
          reportValidity() {},
        });
        const action = field("action", "enum", "set");
        const channel = field("channel", "integer", "1", true);
        const scale = field("volts_per_division", "number", "");
        const fields = [action, channel, scale];
        const container = {
          querySelectorAll(selector) {
            if (selector === "[data-field]") return fields;
            return [];
          },
          querySelector(selector) {
            if (selector === '[data-dirty="true"]') {
              return fields.find((item) => item.dataset.dirty === "true") || null;
            }
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return fields.find((item) => item.dataset.field === match?.[1]) || null;
          },
        };
        const form = new globalThis.CommandForm(container, null);
        form.presentation = {
          kind: "setting", action_field: "action", query_value: "query",
          apply_value: "set", query_fields: ["channel"],
        };

        assert.deepEqual(form.queryValues(), { action: "query", channel: 1 });
        form.syncResult({ result: { result: { channel: 1, volts_per_division: 0.5 } } });
        assert.equal(scale.value, "0.5");

        scale.value = "0.8";
        scale.dataset.dirty = "true";
        form.syncResult({ result: { result: { channel: 1, volts_per_division: 1 } } }, true);
        assert.equal(scale.value, "0.8");
        assert.equal(form.isDirty(), true);

        form.clearDirty();
        form.syncResult({ result: { result: { channel: 1, volts_per_division: 1 } } }, false);
        assert.equal(scale.value, "1");
        assert.equal(form.isDirty(), false);
        assert.deepEqual(form.values(), { action: "set", channel: 1, volts_per_division: 1 });

        form.setDisabled(true);
        assert.equal(channel.disabled, true);
        assert.equal(scale.disabled, true);
        assert.equal(action.disabled, false);
        form.setDisabled(false);
        assert.equal(channel.disabled, false);
        assert.equal(scale.disabled, false);

        const source1 = field("source_channel", "integer", "");
        const source2 = field("source2_channel", "integer", "");
        const aliasFields = [source1, source2];
        const aliasContainer = {
          querySelectorAll(selector) { return selector === "[data-field]" ? aliasFields : []; },
          querySelector(selector) {
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return aliasFields.find((item) => item.dataset.field === match?.[1]) || null;
          },
        };
        const aliasForm = new globalThis.CommandForm(aliasContainer, null);
        aliasForm.presentation = { readback_fields: { source_channel: "source1_channel" } };
        aliasForm.syncResult({ result: { result: {
          source: { source1_channel: 2, source2_channel: 3 },
        } } });
        assert.equal(source1.value, "2");
        assert.equal(source2.value, "3");

        const rangeValue = field("range_value", "number", "");
        const mathContainer = {
          querySelectorAll(selector) { return selector === "[data-field]" ? [rangeValue] : []; },
          querySelector() { return rangeValue; },
        };
        const mathForm = new globalThis.CommandForm(mathContainer, null);
        mathForm.presentation = { readback_fields: { range_value: "range" } };
        mathForm.syncResult({ result: { result: { math_vertical: { range: 4 } } } });
        assert.equal(rangeValue.value, "4");

        const pulseField = (name) => field(name, "number", "");
        const pulseQualifier = field("qualifier", "enum", "");
        pulseQualifier.type = "select-one";
        const pulseTime = pulseField("time_seconds");
        const pulseMin = pulseField("min_time_seconds");
        const pulseMax = pulseField("max_time_seconds");
        const pulseLevel = pulseField("level");
        const pulseFields = [pulseQualifier, pulseTime, pulseMin, pulseMax, pulseLevel];
        const pulseContainer = {
          querySelectorAll(selector) { return selector === "[data-field]" ? pulseFields : []; },
          querySelector(selector) {
            const match = selector.match(/^\[data-field="(.+)"\]$/);
            return pulseFields.find((item) => item.dataset.field === match?.[1]) || null;
          },
        };
        const pulseForm = new globalThis.CommandForm(pulseContainer, null);
        pulseForm.presentation = { readback_fields: {
          time_seconds: {
            selector_field: "qualifier",
            fields: {
              "greater-than": "greater_than_seconds",
              "less-than": "less_than_seconds",
            },
          },
          min_time_seconds: "range_min_seconds",
          max_time_seconds: "range_max_seconds",
          level: "level_volts",
        } };
        pulseForm.syncResult({ result: { result: {
          qualifier: "greater-than", greater_than_seconds: 0.001,
          range_min_seconds: null, range_max_seconds: null, level_volts: 1.5,
        } } });
        assert.equal(pulseTime.value, "0.001");
        assert.equal(pulseLevel.value, "1.5");
        assert.equal(pulseMin.value, "");
        assert.equal(pulseMax.value, "");

        pulseForm.syncResult({ result: { result: {
          qualifier: "range", greater_than_seconds: null,
          range_min_seconds: 0.002, range_max_seconds: 0.003,
        } } });
        assert.equal(pulseMin.value, "0.002");
        assert.equal(pulseMax.value, "0.003");

        const tvMode = field("mode", "enum", "");
        const tvContainer = {
          querySelectorAll(selector) { return selector === "[data-field]" ? [tvMode] : []; },
          querySelector() { return tvMode; },
        };
        const tvForm = new globalThis.CommandForm(tvContainer, null);
        tvForm.presentation = { readback_fields: { mode: "tv_mode" } };
        tvForm.syncResult({ result: { result: { mode: "tv", tv_mode: "field2" } } });
        assert.equal(tvMode.value, "field2");

        const bus = field("bus", "integer", "2", true);
        bus.checkValidity = () => Number(bus.value) <= 1;
        const busContainer = {
          querySelectorAll(selector) { return selector === "[data-field]" ? [bus] : []; },
          querySelector() { return bus; },
        };
        const busForm = new globalThis.CommandForm(busContainer, null);
        busForm.presentation = {
          kind: "setting", action_field: "action", query_value: "query", query_fields: ["bus"],
        };
        assert.equal(busForm.queryValues(), null);
        bus.value = "1";
        assert.deepEqual(busForm.queryValues(), { action: "query", bus: 1 });
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(command_form_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_workflow_multi_select_serializes_the_existing_csv_contract() -> None:
    command_form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.testTranslate = (key) => key;
        globalThis.testHasTranslation = () => false;
        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.CommandForm = CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const channels = {
          value: "1",
          type: "select-multiple",
          multiple: true,
          selectedOptions: [{ value: "1" }, { value: "2" }],
          dataset: { field: "channels", type: "multi-enum", serialize: "csv" },
          required: true,
          validity: { badInput: false },
          closest: () => null,
          setCustomValidity() {},
          checkValidity() { return this.selectedOptions.length > 0; },
          reportValidity() {},
        };
        const container = {
          querySelectorAll(selector) { return selector === "[data-field]" ? [channels] : []; },
        };
        const form = new globalThis.CommandForm(container, null);
        assert.deepEqual(form.values(), { channels: "1,2" });

        channels.value = "";
        channels.selectedOptions = [];
        assert.equal(form.values(), null);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(command_form_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_command_support_consumes_backend_model_projection() -> None:
    support_path = STATIC_ROOT / "command-support.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        const source = "const translate = (key, values) => `${key}:${values?.model || ''}`;\n"
          + fs.readFileSync(process.argv[1], "utf8").replace(/^import[^\n]*\r?\n/gm, "");
        const support = await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);
        const command = {
          fields: [
            { name: "channel", type: "integer", maximum: 4 },
            { name: "impedance", type: "enum", options: ["one_meg", "fifty"] },
          ],
          presentation: { models: { two_channel: {
            supported: false,
            fields: {
              channel: { maximum: 2 },
              impedance: { options: ["one_meg"] },
            },
          } } },
        };
        assert.equal(support.commandSupported(command, "two_channel"), false);
        assert.match(support.commandSupportReason(command, "two_channel", "Two Channel"), /Two Channel/);
        assert.deepEqual(support.fieldsForModel(command, "two_channel"), [
          { name: "channel", type: "integer", maximum: 2 },
          { name: "impedance", type: "enum", options: ["one_meg"] },
        ]);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(support_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_command_editor_and_result_presentation_contract() -> None:
    app_source = read_static("app.js")
    form_source = read_static("command-form.js")
    results_source = read_static("results.js")

    assert 'input.type = "hidden";' in form_source
    assert 'field.help_key ? `help.${field.help_key}` : `help.${field.name}`' in form_source
    assert 'field.label_key ? `field.${field.label_key}`' in form_source
    assert 'translate("enum.enable")' in form_source
    assert 'translate("enum.disable")' in form_source
    assert 'translate("enum.true")' in form_source
    assert 'translate("enum.false")' in form_source
    assert 'new Option(translate("status.enabled")' not in form_source
    assert "commandForm.queryValues()" in app_source
    assert 'intent: "readback"' in app_source
    assert 'if (options.intent === "apply") commandForm.clearDirty();' in app_source
    assert 'const draft = changed && rerender && commandForm ? commandForm.draft() : null;' in app_source
    assert 'if (changed && rerender && commandForm) syncCommandSelection(draft);' in app_source
    assert 'if (lockEditor) commandForm.setDisabled(true);' in app_source
    assert 'commandForm.setDisabled(false);' in app_source
    assert "}, () => syncCommandSelection());" in app_source
    assert "renderWorkspaceResult" in results_source
    assert 'job.command === "identify"' in results_source
    assert "appendWorkspaceFields(container, fields);" in results_source
    assert "JSON.stringify(job.result, null, 2)" in results_source


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_acquisition_form_shows_average_count_only_after_readback() -> None:
    form_path = STATIC_ROOT / "command-form.js"
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        globalThis.testTranslate = (key) => key;
        globalThis.testHasTranslation = () => false;
        globalThis.Option = class {
          constructor(text, value) { this.textContent = text; this.value = value; }
        };
        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          fs.readFileSync(process.argv[1], "utf8"),
        ].join("\n").replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export class /gm, "class ")
          + "\nglobalThis.CommandForm = CommandForm;";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const type = {
          dataset: { field: "type", type: "enum" },
          type: "select-one", value: "", closest: () => null,
        };
        const count = {
          dataset: { field: "count", type: "integer", queryField: "false" },
          type: "number", value: "", closest: () => null,
        };
        const wrapper = {
          dataset: { visibleIf: JSON.stringify([{ field: "type", equals: "average" }]) },
          hidden: false,
        };
        const container = {
          querySelectorAll(selector) {
            if (selector === "[data-visible-if]") return [wrapper];
            if (selector === "[data-field]") return [type, count];
            return [];
          },
          querySelector(selector) {
            return selector.includes('"type"') ? type : null;
          },
        };
        const form = new globalThis.CommandForm(container, null);
        form.presentation = { readback_fields: {} };
        form.syncResult({ result: { type: "normal", count: 16 } });
        assert.equal(type.value, "normal");
        assert.equal(wrapper.hidden, true);
        form.syncResult({ result: { type: "average", count: 16 } });
        assert.equal(type.value, "average");
        assert.equal(count.value, "16");
        assert.equal(wrapper.hidden, false);
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(form_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


COMMAND_CATALOG_HARNESS = r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";

        class FakeNode {
          constructor(tag = "div") {
            this.tagName = tag.toUpperCase();
            this.children = [];
            this.listeners = {};
            this.dataset = {};
            this.attributes = {};
            const classSet = new Set();
            this.classList = {
              add: (...names) => { for (const name of names) classSet.add(name); },
              contains: (name) => classSet.has(name),
            };
            this.hidden = false;
            this.disabled = false;
            this.title = "";
            this.value = "";
            this.type = "";
            this.textContent = "";
            this.className = "";
          }
          addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
          dispatch(name, event = {}) { for (const handler of this.listeners[name] || []) handler(event); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
          append(...nodes) { this.children.push(...nodes); }
          setAttribute(name, value) { this.attributes[name] = String(value); }
          closest(selector) {
            const match = selector.match(/data-([a-z-]+)\]$/);
            if (!match) return null;
            const property = match[1].replace(/-([a-z])/g, (_all, char) => char.toUpperCase());
            return this.dataset[property] !== undefined ? this : null;
          }
        }

        const translations = {
          "group.edge": "Edge",
          "group.common": "Common",
          "group.runt": "Runt",
          "group.basic": "Basic",
          "group.uart": "UART",
          "commands.noMatches": "No matching commands.",
        };
        globalThis.testTranslate = (key) => translations[key] ?? key;
        globalThis.testHasTranslation = (key) => key in translations;
        globalThis.testCommandSupported = () => true;
        globalThis.testCommandSupportReason = () => "";
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };

        const source = [
          "const translate = globalThis.testTranslate;",
          "const hasTranslation = globalThis.testHasTranslation;",
          "const commandSupported = (...args) => globalThis.testCommandSupported(...args);",
          "const commandSupportReason = (...args) => globalThis.testCommandSupportReason(...args);",
          "const fieldsForModel = globalThis.testFieldsForModel;",
          fs.readFileSync(process.argv[1], "utf8")
            .replace('import { hasTranslation, translate } from "/static/i18n.js";', "")
            .replace(/import \{[^}]*\} from "\/static\/command-support\.js";/, ""),
        ].join("\n").replace(/^export class /gm, "class ")
          + "\nglobalThis.catalogApi = { CommandCatalog };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const commands = [
          { id: "trigger-edge", category: "Trigger", label: "Edge trigger", modes: ["live"], group: "edge" },
          { id: "trigger-edge-source", category: "Trigger", label: "Edge trigger source", modes: ["live"], group: "edge" },
          { id: "trigger-sweep", category: "Trigger", label: "Trigger sweep", modes: ["live"], group: "common" },
          { id: "trigger-runt", category: "Trigger", label: "Runt trigger", modes: ["live"], group: "runt" },
          { id: "search-state", category: "Search", label: "Search state", modes: ["live"], group: "basic" },
          { id: "serial-search-uart", category: "Search", label: "UART serial search", modes: ["live"], group: "uart" },
          { id: "serial-mode", category: "Serial", label: "Serial mode", modes: ["live"], group: "uart" },
          { id: "acquisition", category: "Acquisition", label: "Acquisition", modes: ["live"] },
        ];
        const buildCatalog = () => {
          const elements = {
            filter: new FakeNode("input"),
            categories: new FakeNode(),
            list: new FakeNode(),
          };
          const selections = [];
          const catalog = new globalThis.catalogApi.CommandCatalog(
            commands,
            elements,
            (selected) => selections.push(selected?.id || ""),
          );
          return { elements, selections, catalog };
        };
        const sections = (list) => list.children.filter((node) => node.className === "command-group");
        const sectionFor = (list, group) =>
          sections(list).find((node) => node.children[0].dataset.commandGroup === group);
        const flatButtons = (list) => list.children.filter((node) => node.className === "command-button");
        const clickGroupHeader = (list, section) =>
          list.dispatch("click", { target: section.children[0] });
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_command_catalog_renders_collapsible_groups_with_flat_fallback() -> None:
    catalog_path = STATIC_ROOT / "command-catalog.js"
    script = textwrap.dedent(COMMAND_CATALOG_HARNESS) + textwrap.dedent(
        r'''
        {
          const { elements, catalog } = buildCatalog();
          catalog.render();

          const groups = sections(elements.list).map((node) => node.children[0].dataset.commandGroup);
          assert.deepEqual(groups, ["edge", "common", "runt"]);
          const expectedLabels = { edge: "Edge", common: "Common", runt: "Runt" };
          for (const section of sections(elements.list)) {
            const toggle = section.children[0];
            assert.equal(toggle.tagName, "BUTTON");
            assert.equal(toggle.type, "button");
            assert.equal(toggle.attributes["aria-expanded"], "true");
            assert.equal(toggle.children[0].textContent, "▾");
            assert.equal(toggle.children[1].textContent, expectedLabels[toggle.dataset.commandGroup]);
            assert.equal(section.children[1].hidden, false);
          }
          assert.deepEqual(
            sectionFor(elements.list, "edge").children[1].children.map((node) => node.dataset.command),
            ["trigger-edge", "trigger-edge-source"],
          );

          catalog.select("acquisition");
          assert.equal(flatButtons(elements.list).length, 1);
          assert.equal(sections(elements.list).length, 0);
          assert.equal(flatButtons(elements.list)[0].dataset.command, "acquisition");

          globalThis.testCommandSupported = () => false;
          globalThis.testCommandSupportReason = () => "Unavailable for Model X";
          catalog.updateModel("model-x", "Model X");
          catalog.select("trigger-edge");
          const edgeItems = sectionFor(elements.list, "edge").children[1].children;
          assert.equal(edgeItems[0].disabled, true);
          assert.equal(edgeItems[0].title, "Unavailable for Model X");
          assert.equal(edgeItems[0].children[1].tagName, "SMALL");
          globalThis.testCommandSupported = () => true;
          globalThis.testCommandSupportReason = () => "";
          catalog.updateModel(null);

          let commonSection = sectionFor(elements.list, "common");
          clickGroupHeader(elements.list, commonSection);
          commonSection = sectionFor(elements.list, "common");
          assert.equal(commonSection.children[0].attributes["aria-expanded"], "false");
          assert.equal(commonSection.children[0].children[0].textContent, "▸");
          assert.equal(commonSection.children[1].hidden, true);
          assert.equal(catalog.selectedId, "trigger-edge");
          clickGroupHeader(elements.list, commonSection);
          assert.equal(sectionFor(elements.list, "common").children[0].attributes["aria-expanded"], "true");

          catalog.select("search-state");
          clickGroupHeader(elements.list, sectionFor(elements.list, "uart"));
          assert.equal(sectionFor(elements.list, "uart").children[0].attributes["aria-expanded"], "false");
          catalog.select("serial-mode");
          assert.equal(sectionFor(elements.list, "uart").children[0].attributes["aria-expanded"], "true");
          catalog.select("search-state");
          assert.equal(sectionFor(elements.list, "uart").children[0].attributes["aria-expanded"], "false");

          catalog.select("trigger-edge");
          clickGroupHeader(elements.list, sectionFor(elements.list, "runt"));
          assert.equal(sectionFor(elements.list, "runt").children[1].hidden, true);
          catalog.select("trigger-runt");
          const runtSection = sectionFor(elements.list, "runt");
          assert.equal(runtSection.children[0].attributes["aria-expanded"], "true");
          assert.equal(runtSection.children[1].hidden, false);
          const runtButton = runtSection.children[1].children[0];
          assert.equal(runtButton.dataset.command, "trigger-runt");
          assert.equal(runtButton.attributes["aria-pressed"], "true");
          assert.equal(runtButton.classList.contains("active"), true);
        }

        {
          const { elements, selections, catalog } = buildCatalog();
          catalog.render();
          const baselineSelections = selections.length;
          clickGroupHeader(elements.list, sectionFor(elements.list, "common"));
          assert.equal(selections.length, baselineSelections);
          assert.equal(catalog.selectedId, "trigger-edge");
        }
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(catalog_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_command_catalog_filter_keeps_matching_groups_visible() -> None:
    catalog_path = STATIC_ROOT / "command-catalog.js"
    script = textwrap.dedent(COMMAND_CATALOG_HARNESS) + textwrap.dedent(
        r'''
        const { elements, catalog } = buildCatalog();
        catalog.render();
        assert.equal(sectionFor(elements.list, "common").children[0].attributes["aria-expanded"], "true");

        elements.filter.value = "sweep";
        elements.filter.dispatch("input");
        const visibleGroups = sections(elements.list).map((node) => node.children[0].dataset.commandGroup);
        assert.deepEqual(visibleGroups, ["common"]);
        const forcedSection = sectionFor(elements.list, "common");
        assert.equal(forcedSection.children[0].attributes["aria-expanded"], "true");
        assert.equal(forcedSection.children[1].hidden, false);
        assert.deepEqual(
          forcedSection.children[1].children.map((node) => node.dataset.command),
          ["trigger-sweep"],
        );

        clickGroupHeader(elements.list, sectionFor(elements.list, "common"));
        const clickedSection = sectionFor(elements.list, "common");
        assert.equal(clickedSection.children[0].attributes["aria-expanded"], "true");
        assert.equal(clickedSection.children[1].hidden, false);
        assert.equal(catalog.collapsedGroups.size, 0);

        elements.filter.value = "";
        elements.filter.dispatch("input");
        assert.deepEqual(
          sections(elements.list).map((node) => node.children[0].dataset.commandGroup),
          ["edge", "common", "runt"],
        );
        assert.equal(sectionFor(elements.list, "common").children[0].attributes["aria-expanded"], "true");
        assert.equal(sectionFor(elements.list, "common").children[1].hidden, false);

        clickGroupHeader(elements.list, sectionFor(elements.list, "common"));
        assert.equal(sectionFor(elements.list, "common").children[1].hidden, true);

        elements.filter.value = "sweep";
        elements.filter.dispatch("input");
        assert.equal(sectionFor(elements.list, "common").children[0].attributes["aria-expanded"], "true");
        assert.equal(sectionFor(elements.list, "common").children[1].hidden, false);

        elements.filter.value = "";
        elements.filter.dispatch("input");
        assert.deepEqual(
          sections(elements.list).map((node) => node.children[0].dataset.commandGroup),
          ["edge", "common", "runt"],
        );
        assert.equal(sectionFor(elements.list, "common").children[0].attributes["aria-expanded"], "false");
        assert.equal(sectionFor(elements.list, "common").children[1].hidden, true);

        elements.filter.value = "runt";
        elements.filter.dispatch("input");
        catalog.select("trigger-runt");
        assert.equal(sectionFor(elements.list, "runt").children[0].attributes["aria-expanded"], "true");
        assert.equal(catalog.collapsedGroups.size, 1);

        elements.filter.value = "";
        elements.filter.dispatch("input");
        assert.equal(sectionFor(elements.list, "runt").children[0].attributes["aria-expanded"], "true");
        assert.equal(sectionFor(elements.list, "runt").children[1].hidden, false);
        assert.equal(catalog.selectedId, "trigger-runt");

        elements.filter.value = "zzz-no-match";
        elements.filter.dispatch("input");
        assert.equal(elements.list.children.length, 1);
        assert.equal(elements.list.children[0].className, "muted command-list-empty");
        assert.equal(elements.list.children[0].textContent, "No matching commands.");
        '''
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(catalog_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
