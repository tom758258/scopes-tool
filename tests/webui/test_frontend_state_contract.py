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
    assert 'let context = { mode: "live", resource: null, model_id: null };' in app_source
    availability = extract_function(app_source, "function commandAvailable(command)")
    assert 'if (command === "identify") return true;' in availability
    assert "deviceResource?.hasCurrentIdentity(context)" in availability
    assert 'id="detected-model"' in html
    assert 'data-command="identify"' not in html
    assert '"command.identify": "Read device information"' in english
    assert '"description.identify": "Read instrument identification information"' in english
    assert '"command.identify": "讀取裝置資訊"' in chinese
    assert '"description.identify": "讀取儀器識別資訊"' in chinese


def test_identify_has_a_dedicated_workspace_result_area() -> None:
    app_source = read_static("app.js")
    html = read_static("index.html")
    english = read_static("locale_en.js")
    chinese = read_static("locale_zh_tw.js")

    assert 'id="identity-workspace-result"' in html
    assert 'id="identity-workspace-result-content"' in html
    assert 'data-i18n="workspace.latestSuccessfulResult"' in html
    assert 'selected?.id === "identify"' in app_source
    assert 'renderIdentityWorkspaceResult(elements.identityWorkspaceContent, job);' in app_source
    assert '"workspace.latestSuccessfulResult": "Latest successful result"' in english
    assert '"workspace.latestSuccessfulResult": "最新成功結果"' in chinese


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for frontend behavior checks")
def test_identify_workspace_keeps_latest_success_after_a_later_failure() -> None:
    app_source = read_static("app.js")
    declarations = "\n".join(
        extract_function_declaration(app_source, signature)
        for signature in (
            "function identityWorkspaceKey(commandContext)",
            "function captureIdentityWorkspaceResult(job, commandContext)",
            "function renderIdentityWorkspace()",
        )
    )
    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";

        class FakeNode {
          constructor() { this.children = []; this.hidden = true; }
          append(...nodes) { this.children.push(...nodes); }
          replaceChildren(...nodes) { this.children = [...nodes]; }
        }

        let selectedCommand = "identify";
        let context = { mode: "live", resource: "USB0::SCOPE-A::INSTR", model_id: null };
        const catalog = { selected: () => ({ id: selectedCommand }) };
        const elements = {
          identityWorkspace: new FakeNode(),
          identityWorkspaceContent: new FakeNode(),
        };
        const latestSuccessfulIdentityResults = new Map();
        const translate = (key) => key;
        const renderIdentityWorkspaceResult = (container, job) => container.append({ job });
        globalThis.document = { createElement: () => ({ className: "", textContent: "" }) };
        '''
    ) + declarations + textwrap.dedent(
        r'''

        const completed = {
          job_id: "identify-success",
          command: "identify",
          status: "completed",
          resource: context.resource,
          result: { result: { idn: { model: "DSO-X 4024A" } } },
        };
        assert.equal(captureIdentityWorkspaceResult(completed, context), true);
        assert.equal(elements.identityWorkspace.hidden, false);
        assert.equal(elements.identityWorkspaceContent.children[0].job.job_id, "identify-success");

        const failed = {
          job_id: "identify-failed",
          command: "identify",
          status: "failed",
          error: "temporary failure",
        };
        assert.equal(captureIdentityWorkspaceResult(failed, context), false);
        renderIdentityWorkspace();
        assert.equal(elements.identityWorkspaceContent.children[0].job.job_id, "identify-success");

        selectedCommand = "run";
        renderIdentityWorkspace();
        assert.equal(elements.identityWorkspace.hidden, true);

        selectedCommand = "identify";
        context = { ...context, resource: "USB0::SCOPE-B::INSTR" };
        renderIdentityWorkspace();
        assert.equal(elements.identityWorkspace.hidden, false);
        assert.equal(elements.identityWorkspaceContent.children[0].textContent, "workspace.identifyResultEmpty");
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
        const captureIdentityWorkspaceResult = () => {};
        const renderLiveData = () => {};
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
        let pendingResourceLiveSupport = null;
        let resultPresentation = { kind: "empty", job: null, message: null };
        const elements = { results: {} };
        const events = [];
        const submissions = [];
        const states = [];
        const clientErrors = [];
        const backendJobs = new Set();
        const identities = [];
        const captureIdentityWorkspaceResult = () => {};
        let rejectA;
        const renderLiveData = () => {};
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
    source = (REPO_ROOT / "src" / "scopes_tool_webui" / "commands.py").read_text(encoding="utf-8")

    assert '"id": "list-resources"' in source
    assert '{"name": "live_only", "type": "boolean", "default": False}' in source
    assert 'parameters.setdefault("live_only", False)' in source
    assert '_require_boolean(parameters["live_only"], "live_only")' in source
    assert "discover_visa_resources(live_only=live_only)" in source
    assert '"backend": listing.backend' in source


def test_scan_failure_is_included_in_the_compact_device_presentation() -> None:
    source = read_static("device-resource.js")

    assert 'this.scanStatus = "failed";' in source
    assert '"device.detection.scanFailed"' in source
    assert "this.elements.summary.title = summary;" in source


def test_workspace_and_live_command_states_have_separate_owners() -> None:
    source = read_static("app.js")

    assert "let workspaceExecutionState = { key: \"device.ready\" };" in source
    assert "let liveCommandState = { key: \"device.ready\" };" in source
    assert "workspaceExecutionState = { ...state };" in source
    assert "liveCommandState = { ...state };" in source
    command_state_handler = source.split("function setCommandState(state) {", 1)[1].split("\n}", 1)[0]
    assert "liveCommandState = { ...state };" in command_state_handler
    assert "workspaceExecutionState =" not in command_state_handler
    assert "renderExecutionStatus();" in source
    assert "const commandStatus = liveCommandState.status;" in source


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
