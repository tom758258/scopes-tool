import { getCommands, getHealth, openPcOutputFolder, selectPcOutputFolder } from "/static/api.js";
import { bindBasicControls } from "/static/basic-controls.js";
import { CommandCatalog } from "/static/command-catalog.js";
import { CommandForm } from "/static/command-form.js";
import { DeviceResource } from "/static/device-resource.js";
import {
  buildWorkspaceContext,
  findWorkspaceResult,
  sameWorkspaceContext,
  workspaceContextForCompletedJob,
  workspaceContextKey,
} from "/static/execution-context.js";
import { initializeI18n, locale, setLocale, translate, translateJobStatus } from "/static/i18n.js";
import { requestCancel, runJob } from "/static/jobs.js";
import {
  pcOutputContext,
  pcOutputDirectory,
  renderPcOutputCommandNote,
} from "/static/pc-output.js";
import { renderEmpty, renderError, renderJob, renderWorkspaceResult } from "/static/results.js";
import { SaveExportEditor } from "/static/save-export-editor.js";
import { SearchEditor } from "/static/search-editor.js";
import { SerialEditor } from "/static/serial-editor.js";
import { createInitialState } from "/static/state.js";
import { TriggerEditor } from "/static/trigger-editor.js";
import { WorkflowEditor } from "/static/workflow-editor.js";

const SERVICE_NAME = "scopes-tool-webui";
const elements = {
  localeToggle: document.querySelector("#locale-toggle"),
  version: document.querySelector("#webui-version"),
  webuiState: document.querySelector("#webui-state"),
  commandState: document.querySelector("#command-state"),
  liveState: document.querySelector("#live-state"),
  mode: [...document.querySelectorAll("input[name=mode]")],
  model: document.querySelector("#model-select"),
  modelField: document.querySelector("#planning-model-field"),
  detectedModelField: document.querySelector("#detected-model-field"),
  detectedModel: document.querySelector("#detected-model"),
  resource: document.querySelector("#resource-input"),
  resourceList: document.querySelector("#resource-list"),
  scan: document.querySelector("#scan-button"),
  settings: document.querySelector("#settings-button"),
  settingsPanel: document.querySelector("#settings-panel"),
  deviceBody: document.querySelector("#device-resource-body"),
  deviceCollapse: document.querySelector("#device-collapse"),
  modeBadge: document.querySelector("#device-mode-badge"),
  summary: document.querySelector("#device-summary"),
  deviceStatus: document.querySelector("#device-status"),
  filter: document.querySelector("#command-filter"),
  categories: document.querySelector("#command-categories"),
  commandList: document.querySelector("#command-list"),
  selectedCommand: document.querySelector("#selected-command"),
  commandDescription: document.querySelector("#command-description"),
  commandSupportReason: document.querySelector("#command-support-reason"),
  advanced: document.querySelector("#advanced-commands"),
  advancedToggle: document.querySelector("#advanced-command-toggle"),
  form: document.querySelector("#command-form"),
  formHeading: document.querySelector("#form-heading"),
  saveExportEditor: document.querySelector("#save-export-editor"),
  serialEditor: document.querySelector("#serial-editor"),
  triggerEditor: document.querySelector("#trigger-editor"),
  searchEditor: document.querySelector("#search-editor"),
  workflowEditor: document.querySelector("#workflow-editor"),
  workspaceHeaderActions: document.querySelector("#workspace-header-actions"),
  refresh: document.querySelector("#refresh-button"),
  execute: document.querySelector("#execute-button"),
  cancel: document.querySelector("#cancel-button"),
  identityWorkspace: document.querySelector("#identity-workspace-result"),
  identityWorkspaceContent: document.querySelector("#identity-workspace-result-content"),
  resultsPanel: document.querySelector("#job-result-panel"),
  results: document.querySelector("#results"),
  resultClear: document.querySelector("#job-result-clear"),
  resultToggle: document.querySelector("#job-result-toggle"),
  resultDetailPanel: document.querySelector("#result-panel"),
  resultDetail: document.querySelector("#result-detail-content"),
  resultDetailToggle: document.querySelector("#result-toggle"),
  basic: document.querySelector("#basic-controls"),
  pcOutput: document.querySelector("#pc-output-dir"),
  pcOutputSelect: document.querySelector("#pc-output-select"),
  pcOutputOpen: document.querySelector("#pc-output-open"),
  pcOutputStatus: document.querySelector("#pc-output-status"),
  pcOutputCommandNote: document.querySelector("#pc-output-command-note"),
};

let commands = [];
let models = [];
let currentJobId = null;
const state = createInitialState();
let context = state.executionContext;
let catalog;
let commandForm;
let genericFormRevision = 0;
let saveExportEditor;
let serialEditor;
let triggerEditor;
let searchEditor;
let workflowEditor;
let deviceResource;
let executing = false;
let advancedVisible = false;
let resultPresentation = { kind: "empty", job: null, message: null };
let healthState = { status: "checking", version: null, error: null };
let liveCommandState = { key: "device.ready" };
let pendingResourceLiveSupport = null;
let updateBasicAvailability = () => {};
let pcOutputSelectionStatus = null;

const EDITOR_RENDERERS = {
  "save-export": () => saveExportEditor,
  serial: () => serialEditor,
  trigger: () => triggerEditor,
  search: () => searchEditor,
  workflow: () => workflowEditor,
};

function editorKindFor(command) {
  const kind = command?.editor;
  return kind && EDITOR_RENDERERS[kind] ? kind : null;
}

initializeI18n();
renderLocaleToggle();
elements.localeToggle.addEventListener("click", () => setLocale(locale() === "en" ? "zh-TW" : "en"));

async function initialize() {
  renderAdvancedToggle();
  renderCollapseLabels();
  bindPresentationControls();
  await updateHealth();
  const [loadedCommands, loadedModels] = await Promise.all([
    getCommands(),
    fetch("/api/models").then((response) => response.json()),
  ]);
  commands = loadedCommands;
  models = loadedModels;
  models.forEach((model) => elements.model.append(new Option(model.label, model.id)));
  elements.model.value = "keysight-dsox4024a";

  catalog = new CommandCatalog(commands, {
    filter: elements.filter,
    categories: elements.categories,
    list: elements.commandList,
  }, () => syncCommandSelection());
  commandForm = new CommandForm(elements.form, catalog);
  saveExportEditor = new SaveExportEditor(elements.saveExportEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && commandAvailable(selected.id));
    },
    contextKey: () => `${context.mode}|${context.resource || ""}|${currentModelId() || ""}`,
    selectedCommand: () => catalog.selected(),
  });
  serialEditor = new SerialEditor(elements.serialEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && commandAvailable(selected.id));
    },
    contextKey: () => `${context.mode}|${context.resource || ""}|${currentModelId() || ""}`,
    modelInfo: serialEditorModelInfo,
  });
  triggerEditor = new TriggerEditor(elements.triggerEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && commandAvailable(selected.id));
    },
    contextKey: () => `${context.mode}|${context.resource || ""}|${currentModelId() || ""}`,
    selectedCommand: () => catalog.selected(),
  });
  searchEditor = new SearchEditor(elements.searchEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && commandAvailable(selected.id));
    },
    contextKey: () => `${context.mode}|${context.resource || ""}|${currentModelId() || ""}`,
    selectedCommand: () => catalog.selected(),
  });
  workflowEditor = new WorkflowEditor(elements.workflowEditor, catalog, {
    executeCommand,
    headerActions: elements.workspaceHeaderActions,
    isExecutionBusy,
    isAvailable: () => {
      const selected = catalog.selected();
      return Boolean(selected && commandAvailable(selected.id));
    },
    contextKey: () => `${context.mode}|${context.resource || ""}|${currentModelId() || ""}`,
    selectedCommand: () => catalog.selected(),
  });
  catalog.render();

  deviceResource = new DeviceResource({
    mode: elements.mode,
    model: elements.model,
    resource: elements.resource,
    resourceList: elements.resourceList,
    scan: elements.scan,
    settings: elements.settings,
    settingsPanel: elements.settingsPanel,
    body: elements.deviceBody,
    deviceCollapse: elements.deviceCollapse,
    modeBadge: elements.modeBadge,
    summary: elements.summary,
    status: elements.deviceStatus,
    pcOutput: elements.pcOutput,
  }, (nextContext) => {
    context = nextContext;
    state.executionContext = nextContext;
    if (catalog) catalog.updateMode(context.mode);
    if (!updateCommandSupport()) syncCommandSelection();
    renderLiveData();
  }, (scanState) => {
    setCommandState(scanState);
  }, (scanJob) => {
    resultPresentation = { kind: "job", job: scanJob, message: null };
    renderCurrentResult();
  }, (scanError) => {
    resultPresentation = {
      kind: "error",
      job: null,
      command: "list-resources",
      message: scanError,
    };
    renderCurrentResult();
  }, (selectedContext) => {
    return refreshSelectedResourceContext(selectedContext);
  }, () => {
    updateAvailability();
  });
  updateBasicAvailability = bindBasicControls(elements.basic, executeCommand, basicAvailable);
  bindPcOutputControls();
  updateAvailability();
  elements.execute.addEventListener("click", (event) => {
    event.preventDefault();
    const selected = catalog.selected();
    const parameters = commandForm.values();
    if (selected && parameters !== null) executeCommand(selected.id, parameters, {
      intent: commandForm.isSettingEditor() ? "apply" : "command",
      formRevision: genericFormRevision,
    });
  });
  elements.refresh.addEventListener("click", async (event) => {
    event.preventDefault();
    const selected = catalog.selected();
    if (!selected || !commandForm.isSettingEditor()) return;
    const parameters = commandForm.queryValues();
    if (parameters !== null) {
      await executeCommand(selected.id, parameters, {
        intent: "readback",
        formRevision: genericFormRevision,
      });
    }
  });
  elements.cancel.addEventListener("click", async () => {
    if (!currentJobId) return;
    try {
      await requestCancel(currentJobId);
    } catch (error) {
      elements.deviceStatus.textContent = error.message;
    }
  });
}

function bindPresentationControls() {
  elements.advancedToggle.addEventListener("click", () => {
    advancedVisible = !advancedVisible;
    elements.advanced.hidden = !advancedVisible;
    elements.advanced.classList.toggle("collapsed", !advancedVisible);
    elements.advancedToggle.setAttribute("aria-expanded", String(advancedVisible));
    renderAdvancedToggle();
  });
  elements.resultToggle.addEventListener("click", () => {
    togglePanel(elements.resultsPanel, elements.results, elements.resultToggle, "results");
  });
  elements.resultDetailToggle.addEventListener("click", () => {
    togglePanel(elements.resultDetailPanel, elements.resultDetail, elements.resultDetailToggle, "results");
  });
  elements.resultClear.addEventListener("click", () => {
    resultPresentation = { kind: "empty", job: null, message: null };
    renderCurrentResult();
  });
}

function bindPcOutputControls() {
  elements.pcOutput.addEventListener("input", () => renderPcOutputNote());
  elements.pcOutputSelect.addEventListener("click", async () => {
    elements.pcOutputSelect.disabled = true;
    pcOutputSelectionStatus = { key: "pcOutput.selecting", values: {}, error: false };
    renderPcOutputStatus();
    try {
      const selection = await selectPcOutputFolder();
      if (selection.selected && selection.folder_path) {
        elements.pcOutput.value = selection.folder_path;
        pcOutputSelectionStatus = {
          key: "pcOutput.selected",
          values: { path: selection.folder_path },
          error: false,
        };
        renderPcOutputNote();
      } else {
        pcOutputSelectionStatus = { key: "pcOutput.cancelled", values: {}, error: false };
      }
    } catch (error) {
      pcOutputSelectionStatus = {
        key: "pcOutput.selectionFailed",
        values: { error: error.message || String(error) },
        error: true,
      };
    } finally {
      elements.pcOutputSelect.disabled = false;
      renderPcOutputStatus();
    }
  });
  elements.pcOutputOpen.addEventListener("click", async () => {
    elements.pcOutputOpen.disabled = true;
    pcOutputSelectionStatus = { key: "pcOutput.opening", values: {}, error: false };
    renderPcOutputStatus();
    try {
      const path = pcOutputDirectory(elements.pcOutput);
      await openPcOutputFolder(path);
      pcOutputSelectionStatus = { key: "pcOutput.opened", values: { path }, error: false };
    } catch (error) {
      pcOutputSelectionStatus = {
        key: "pcOutput.openFailed",
        values: { error: error.message || String(error) },
        error: true,
      };
    } finally {
      elements.pcOutputOpen.disabled = false;
      renderPcOutputStatus();
    }
  });
}

function renderPcOutputStatus() {
  elements.pcOutputStatus.hidden = !pcOutputSelectionStatus;
  elements.pcOutputStatus.classList.toggle(
    "error-summary",
    Boolean(pcOutputSelectionStatus?.error),
  );
  elements.pcOutputStatus.textContent = pcOutputSelectionStatus
    ? translate(pcOutputSelectionStatus.key, pcOutputSelectionStatus.values)
    : "";
}

function renderPcOutputNote() {
  renderPcOutputCommandNote(
    elements.pcOutputCommandNote,
    catalog?.selected(),
    elements.pcOutput,
  );
}

function togglePanel(panel, content, button, labelKey) {
  const expanded = panel.classList.toggle("collapsed") === false;
  content.hidden = !expanded;
  button.setAttribute("aria-expanded", String(expanded));
  const key = expanded ? "results.collapse" : "results.expand";
  button.title = translate(key);
  button.setAttribute("aria-label", translate(key));
  button.textContent = expanded ? "-" : "+";
  if (labelKey) button.dataset.labelKey = labelKey;
}

function renderAdvancedToggle() {
  elements.advancedToggle.textContent = translate(
    advancedVisible ? "commands.showLess" : "commands.showMore",
  );
}

function renderCollapseLabels() {
  const resultExpanded = !elements.resultsPanel.classList.contains("collapsed");
  const detailExpanded = !elements.resultDetailPanel.classList.contains("collapsed");
  const resultKey = resultExpanded ? "results.collapse" : "results.expand";
  const detailKey = detailExpanded ? "results.collapse" : "results.expand";
  elements.resultToggle.title = translate(resultKey);
  elements.resultToggle.setAttribute("aria-label", translate(resultKey));
  elements.resultToggle.textContent = resultExpanded ? "-" : "+";
  elements.resultDetailToggle.title = translate(detailKey);
  elements.resultDetailToggle.setAttribute("aria-label", translate(detailKey));
  elements.resultDetailToggle.textContent = detailExpanded ? "-" : "+";
  renderAdvancedToggle();
}

async function executeCommand(command, parameters, options = {}) {
  if (isExecutionBusy()) return null;
  const definition = commands.find((item) => item.id === command);
  if (!definition || !definition.modes.includes(context.mode)) {
    elements.deviceStatus.textContent = translate("status.noCommands");
    return;
  }
  if (!commandAvailable(command)) {
    elements.deviceStatus.textContent = translate(
      context.mode === "live" && !context.resource
        ? "device.resourceRequired"
        : "status.noCommands",
    );
    return;
  }
  executing = true;
  const commandContext = pcOutputContext(context, elements.pcOutput);
  const submittedWorkspaceContext = currentWorkspaceContext(command);
  const ownsCommandForm = () => options.formRevision !== undefined
    && options.formRevision === genericFormRevision
    && isCurrentEditorJob(command, submittedWorkspaceContext);
  const lockEditor = options.intent === "apply"
    && ownsCommandForm();
  if (lockEditor) commandForm.setDisabled(true);
  if (command === "identify") deviceResource?.setIdentityPending?.(commandContext);
  updateAvailability();
  elements.execute.disabled = true;
  elements.cancel.classList.remove("hidden");
  setExecutionStatus({ status: "queued" });
  try {
    const job = await runJob(command, parameters, commandContext, (updated) => {
      currentJobId = updated.job_id;
      setExecutionStatus({ status: updated.status });
      resultPresentation = { kind: "job", job: updated, message: null };
      renderCurrentResult();
      updateIdentity(updated, commandContext);
    });
    setExecutionStatus({ status: job.status });
    resultPresentation = { kind: "job", job, message: null };
    renderCurrentResult();
    updateIdentity(job, commandContext);
    captureWorkspaceResult(job, submittedWorkspaceContext);
    if (job.status === "completed" && ownsCommandForm()) {
      if (options.intent === "apply") commandForm.clearDirty();
      commandForm.syncResult(job, options.intent !== "apply");
    }
    return job;
  } catch (error) {
    if (command === "identify") deviceResource?.setIdentityError?.(error.message, commandContext);
    setExecutionStatus({ status: "failed" });
    resultPresentation = { kind: "error", job: null, command, message: error.message };
    renderCurrentResult();
    return null;
  } finally {
    if (lockEditor && ownsCommandForm()) {
      commandForm.setDisabled(false);
    }
    executing = false;
    currentJobId = null;
    elements.cancel.classList.add("hidden");
    updateAvailability();
  }
}

function updateIdentity(job, commandContext) {
  if (job.command !== "identify" || !deviceResource || !sameExecutionContext(context, commandContext)) return;
  if (["queued", "running"].includes(job.status)) {
    deviceResource.setIdentityPending?.(commandContext);
    updateCommandSupport();
    renderWorkspace();
    renderLiveData();
    if (typeof updateAvailability === "function") updateAvailability();
    return;
  }
  const idn = job.result?.result?.idn || job.result?.idn;
  if (job.status === "completed" && idn) {
    deviceResource.setIdentity(idn, commandContext);
  } else if (["failed", "cancelled"].includes(job.status)) {
    deviceResource.setIdentityError?.(job.error || translate("status.identifyFailed"), commandContext);
  }
  updateCommandSupport();
  renderWorkspace();
  renderLiveData();
  if (typeof updateAvailability === "function") updateAvailability();
}

async function refreshSelectedResourceContext(selectedContext) {
  if (selectedContext?.mode !== "live" || !selectedContext.resource) return;
  if (executing) return;
  const commandContext = { ...selectedContext };
  if (pendingResourceLiveSupport) {
    pendingResourceLiveSupport.requestedContext = sameExecutionContext(
      commandContext,
      pendingResourceLiveSupport.context,
    )
      ? null
      : commandContext;
    setCommandState({
      status: sameExecutionContext(commandContext, pendingResourceLiveSupport.context)
        ? pendingResourceLiveSupport.status
        : "queued",
    });
    return;
  }
  await evaluateResourceLiveSupport(commandContext);
}

async function evaluateResourceLiveSupport(commandContext) {
  const pending = {
    context: commandContext,
    jobId: null,
    status: "queued",
    requestedContext: null,
  };
  pendingResourceLiveSupport = pending;
  updateAvailability();
  deviceResource?.setIdentityPending?.(commandContext);
  setCommandState({ status: pending.status });
  try {
    const job = await runJob("identify", {}, commandContext, (updated) => {
      pending.jobId = updated.job_id;
      pending.status = updated.status;
      if (sameExecutionContext(context, commandContext)) {
        setCommandState({ status: updated.status });
      }
      presentSelectedResourceJob(updated, commandContext);
    });
    pending.jobId = job.job_id;
    pending.status = job.status;
    if (sameExecutionContext(context, commandContext)) {
      setCommandState({ status: job.status });
    }
    presentSelectedResourceJob(job, commandContext);
  } catch (error) {
    deviceResource?.setIdentityError?.(error.message || String(error), commandContext);
    if (sameExecutionContext(context, commandContext)) {
      setCommandState({ status: "failed" });
    }
    if (pending.jobId === null) {
      resultPresentation = {
        kind: "error",
        job: null,
        command: "identify",
        message: error.message || String(error),
      };
      renderCurrentResult();
    }
  } finally {
    await finishResourceLiveSupportEvaluation(pending.jobId);
  }
}

async function finishResourceLiveSupportEvaluation(jobId) {
  if (pendingResourceLiveSupport?.jobId !== jobId) return false;
  const completed = pendingResourceLiveSupport;
  pendingResourceLiveSupport = null;
  updateAvailability();
  await refreshRequestedResourceLiveSupport(completed);
  return true;
}

async function refreshRequestedResourceLiveSupport(completed) {
  const requested = completed?.requestedContext;
  if (!requested || !sameExecutionContext(context, requested)) return;
  await refreshSelectedResourceContext(requested);
}

function presentSelectedResourceJob(job, commandContext) {
  updateIdentity(job, commandContext);
  captureWorkspaceResult(job, buildWorkspaceContext("identify", commandContext));
  if (sameExecutionContext(context, commandContext)) {
    resultPresentation = { kind: "job", job, message: null };
    renderCurrentResult();
  } else {
    renderJob(elements.results, job, null);
  }
}

function sameExecutionContext(left, right) {
  return left?.mode === right?.mode
    && left?.resource === right?.resource
    && left?.model_id === right?.model_id;
}

function renderWorkspace() {
  const selected = catalog?.selected();
  elements.identityWorkspace.hidden = !selected;
  if (!selected) return;

  elements.identityWorkspaceContent.replaceChildren();
  const workspaceContext = currentWorkspaceContext(selected.id);
  const job = findWorkspaceResult(
    state.workspaceResults,
    workspaceContext,
    selected.id === "identify",
  );
  if (job) {
    renderWorkspaceResult(elements.identityWorkspaceContent, job, workspaceContext);
    return;
  }
  const empty = document.createElement("p");
  empty.className = "muted";
  empty.textContent = translate(
    selected.id === "identify" ? "workspace.identifyResultEmpty" : "workspace.resultEmpty",
  );
  elements.identityWorkspaceContent.append(empty);
}

async function updateHealth() {
  healthState = { status: "checking", version: null, error: null };
  renderLiveData();
  try {
    const health = await getHealth();
    if (health.status !== "ok" || health.package !== SERVICE_NAME) throw new Error(translate("status.unexpected"));
    healthState = { status: "ready", version: health.version || null, error: null };
  } catch (error) {
    healthState = { status: "error", version: null, error: error.message };
  }
  renderVersion();
  renderLiveData();
}

document.addEventListener("localechange", () => {
  const commandDraft = commandForm?.draft();
  renderLocaleToggle();
  renderVersion();
  renderLiveData();
  renderCollapseLabels();
  renderPcOutputStatus();
  renderPcOutputNote();
  if (deviceResource) deviceResource.refresh();
  if (catalog) {
    catalog.render();
    syncCommandSelection(commandDraft);
  }
  saveExportEditor?.rerender();
  serialEditor?.rerender();
  triggerEditor?.rerender();
  searchEditor?.rerender();
  workflowEditor?.rerender();
  syncWorkspaceHeaderActions(editorKindFor(catalog?.selected()));
  renderCurrentResult();
});

function syncCommandSelection(draft = null) {
  if (!catalog || !commandForm) return;
  const selected = catalog.selected();
  state.selectedCommand = selected?.id || null;
  const editorKind = editorKindFor(selected);
  const editorOwned = editorKind !== null;
  invalidateGenericFormOwnership();
  commandForm.render(selected, {
    draft,
    onDirty: () => updateAvailability(),
    onQueryFieldChange: invalidateGenericFormOwnership,
  });
  elements.formHeading.hidden = editorOwned;
  elements.form.hidden = editorOwned;
  elements.saveExportEditor.hidden = editorKind !== "save-export";
  elements.serialEditor.hidden = editorKind !== "serial";
  elements.triggerEditor.hidden = editorKind !== "trigger";
  elements.searchEditor.hidden = editorKind !== "search";
  elements.workflowEditor.hidden = editorKind !== "workflow";
  syncWorkspaceHeaderActions(editorKind);
  elements.selectedCommand.textContent = selected
    ? editorOwned
      ? translate(`${editorKind}.editor.title`)
      : catalog.commandLabel(selected)
    : translate("commands.selectCommand");
  elements.commandDescription.textContent = selected
    ? editorOwned
      ? translate(`${editorKind}.editor.description`)
      : catalog.description(selected)
    : translate("commands.noDescription");
  const supportReason = selected ? catalog.supportReason(selected) : "";
  elements.commandSupportReason.hidden = !supportReason;
  elements.commandSupportReason.textContent = supportReason;
  renderPcOutputNote();
  elements.execute.textContent = translate(`actions.${commandAction(selected)}`);
  renderWorkspace();
  updateAvailability();
  syncEditorPresentation(editorKind);
}

function invalidateGenericFormOwnership() {
  genericFormRevision += 1;
}

function commandAvailable(command) {
  if (!catalog) return false;
  const definition = commands.find((item) => item.id === command);
  if (!definition || !definition.modes.includes(context.mode)) return false;
  if (typeof catalog.supported === "function" && !catalog.supported(definition)) return false;
  if (context.mode !== "live" || command === "list-resources") return true;
  if (!context.resource) return false;
  if (command === "identify") return true;
  return Boolean(deviceResource?.hasCurrentIdentity(context));
}

function basicAvailable(command) {
  return !isExecutionBusy() && commandAvailable(command);
}

function updateAvailability() {
  if (!catalog) return;
  const selected = catalog.selected();
  const busy = isExecutionBusy();
  elements.execute.disabled = busy || !selected || !commandAvailable(selected.id);
  elements.refresh.disabled = busy || !selected || !commandAvailable(selected.id);
  triggerEditor?.applyBusyState();
  searchEditor?.applyBusyState();
  saveExportEditor?.applyBusyState();
  serialEditor?.render(serialEditor.controller.state);
  workflowEditor?.applyBusyState();
  deviceResource?.setExternalBusy(executing || Boolean(pendingResourceLiveSupport));
  updateBasicAvailability();
}

function isExecutionBusy() {
  return executing
    || Boolean(pendingResourceLiveSupport)
    || Boolean(deviceResource?.scanInProgress);
}

function syncWorkspaceHeaderActions(editorKind) {
  const selected = catalog?.selected();
  elements.refresh.hidden = !selected || editorKind !== null || !commandForm?.isSettingEditor();
  elements.execute.hidden = !selected || editorKind !== null;
  if (saveExportEditor?.refreshButton) {
    saveExportEditor.refreshButton.hidden = editorKind !== "save-export";
  }
  if (serialEditor?.refreshButton) serialEditor.refreshButton.hidden = editorKind !== "serial";
  if (triggerEditor?.refreshButton) triggerEditor.refreshButton.hidden = editorKind !== "trigger";
  if (searchEditor?.refreshButton) searchEditor.refreshButton.hidden = editorKind !== "search";
  if (workflowEditor?.runButton) workflowEditor.runButton.hidden = editorKind !== "workflow";
}

function syncEditorPresentation(editorKind) {
  if (editorKind === "save-export") saveExportEditor?.schedulePresentation();
  if (editorKind === "serial") serialEditor?.schedulePresentation();
  if (editorKind === "trigger") triggerEditor?.schedulePresentation();
  if (editorKind === "search") searchEditor?.schedulePresentation();
  if (editorKind === "workflow") workflowEditor?.schedulePresentation();
}

function commandAction(command) {
  if (!command) return "run";
  if (command.presentation?.kind === "setting" && !commandForm?.isSettingEditor()) {
    return "read";
  }
  return command.presentation?.action || "run";
}

function currentModelId() {
  if (context.mode !== "live") return context.model_id;
  return deviceResource?.hasCurrentIdentity(context)
    ? deviceResource.identity?.model_id || null
    : null;
}

function currentModelLabel() {
  const modelId = currentModelId();
  return models.find((model) => model.id === modelId)?.label || modelId || "";
}

function serialEditorModelInfo() {
  const definition = commands.find((item) => item.id === "serial-mode");
  if (!definition) return { supported: false, maxBus: 0, protocols: [] };
  const fields = catalog.fieldsFor(definition);
  const busField = fields.find((field) => field.name === "bus");
  const modeField = fields.find((field) => field.name === "mode");
  const modeOptions = modeField?.options || [];
  return {
    supported: Boolean(currentModelId()) && catalog.supported(definition),
    maxBus: Number(busField?.maximum) || 1,
    protocols: ["uart", "i2c", "spi", "can"].filter(
      (protocol) => !modeOptions.length || modeOptions.includes(protocol),
    ),
  };
}

function updateCommandSupport(rerender = true) {
  if (!catalog) return false;
  const modelId = currentModelId();
  const changed = catalog.activeModelId !== modelId;
  const draft = changed && rerender && commandForm ? commandForm.draft() : null;
  catalog.updateModel(modelId, currentModelLabel());
  if (changed && rerender && commandForm) syncCommandSelection(draft);
  return changed && rerender && Boolean(commandForm);
}

function currentWorkspaceContext(command = catalog?.selected()?.id) {
  return buildWorkspaceContext(command, context, currentModelId());
}

function captureWorkspaceResult(job, submittedContext) {
  if (job?.status !== "completed" || !job.command || !job.result) return false;
  const effectiveContext = workspaceContextForCompletedJob(job, submittedContext);
  const key = workspaceContextKey(effectiveContext);
  state.workspaceResults.delete(key);
  state.workspaceResults.set(key, { context: effectiveContext, job });
  renderWorkspace();
  return true;
}

function isCurrentEditorJob(command, submittedContext) {
  return catalog?.selected()?.id === command
    && sameWorkspaceContext(currentWorkspaceContext(command), submittedContext);
}

function setExecutionStatus(state) {
  liveCommandState = { ...state };
  renderLiveData();
}

function setCommandState(state) {
  liveCommandState = { ...state };
  renderLiveData();
}

function renderCurrentResult() {
  if (resultPresentation.kind === "job") {
    renderJob(elements.results, resultPresentation.job, elements.resultDetail);
  } else if (resultPresentation.kind === "error") {
    renderError(
      elements.results,
      elements.resultDetail,
      resultPresentation.message,
      resultPresentation.command,
    );
  } else {
    renderEmpty(elements.results, elements.resultDetail);
  }
}

function renderLocaleToggle() {
  const nextLocale = locale() === "en" ? "zh-TW" : "en";
  const label = nextLocale === "zh-TW" ? "locale.toChinese" : "locale.toEnglish";
  elements.localeToggle.textContent = translate(label);
  elements.localeToggle.lang = nextLocale === "zh-TW" ? "zh-TW" : "en";
  elements.localeToggle.setAttribute("aria-label", translate(label));
}

function renderVersion() {
  elements.version.textContent = `v${healthState.version || "—"}`;
}

function renderLiveData() {
  const webuiReady = healthState.status === "ready";
  setStateIndicator(
    elements.webuiState,
    translate(webuiReady ? "live_data.ready" : healthState.status === "error" ? "live_data.error" : "live_data.checking"),
    webuiReady ? "state-ok" : healthState.status === "error" ? "state-error" : "state-warning",
    healthState.error || "",
  );

  const commandStatus = liveCommandState.status;
  const commandText = commandStatus
    ? translateJobStatus(commandStatus)
    : translate("live_data.ready");
  const commandClass = commandStatus === "failed"
    ? "state-error"
    : ["queued", "running"].includes(commandStatus)
      ? "state-warning"
      : "state-ok";
  setStateIndicator(elements.commandState, commandText, commandClass);

  const liveKey = context.mode === "simulate"
    ? "live_data.simulate"
    : context.mode === "dry-run"
      ? "live_data.dryRun"
      : context.resource
        ? deviceResource?.hasCurrentIdentity()
          ? "live_data.ready"
          : "live_data.notIdentified"
        : "live_data.noResource";
  setStateIndicator(
    elements.liveState,
    translate(liveKey),
    context.mode === "live" && (!context.resource || !deviceResource?.hasCurrentIdentity())
      ? "state-warning"
      : "state-ok",
  );
}

function setStateIndicator(indicator, text, stateClass, title = "") {
  if (!indicator) return;
  ["state-ok", "state-warning", "state-error", "state-idle"].forEach((name) => {
    indicator.classList.toggle(name, name === stateClass);
  });
  const textNode = indicator.querySelector(".state-text");
  if (textNode) textNode.textContent = text;
  indicator.title = title || text;
}

initialize().catch((error) => {
  healthState = { status: "error", version: null, error: error.message };
  renderVersion();
  renderLiveData();
});
