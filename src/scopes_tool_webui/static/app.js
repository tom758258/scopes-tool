import { getCommands, getHealth } from "/static/api.js";
import { bindBasicControls } from "/static/basic-controls.js";
import { CommandCatalog } from "/static/command-catalog.js";
import { CommandForm } from "/static/command-form.js";
import { DeviceResource } from "/static/device-resource.js";
import { initializeI18n, locale, setLocale, translate, translateJobStatus } from "/static/i18n.js";
import { requestCancel, runJob } from "/static/jobs.js";
import { renderEmpty, renderError, renderJob } from "/static/results.js";

const SERVICE_NAME = "scopes-tool-webui";
const elements = {
  localeToggle: document.querySelector("#locale-toggle"),
  version: document.querySelector("#webui-version"),
  webuiState: document.querySelector("#webui-state"),
  commandState: document.querySelector("#command-state"),
  liveState: document.querySelector("#live-state"),
  mode: [...document.querySelectorAll("input[name=mode]")],
  model: document.querySelector("#model-select"),
  resource: document.querySelector("#resource-input"),
  resourceList: document.querySelector("#resource-list"),
  scan: document.querySelector("#scan-button"),
  settings: document.querySelector("#settings-button"),
  settingsPanel: document.querySelector("#settings-panel"),
  deviceBody: document.querySelector("#device-resource-body"),
  deviceCollapse: document.querySelector("#device-collapse"),
  modeBadge: document.querySelector("#device-mode-badge"),
  summary: document.querySelector("#device-summary"),
  hint: document.querySelector("#device-hint"),
  deviceStatus: document.querySelector("#device-status"),
  identity: document.querySelector("#identity-value"),
  filter: document.querySelector("#command-filter"),
  categories: document.querySelector("#command-categories"),
  commandList: document.querySelector("#command-list"),
  selectedCommand: document.querySelector("#selected-command"),
  commandDescription: document.querySelector("#command-description"),
  advanced: document.querySelector("#advanced-commands"),
  advancedToggle: document.querySelector("#advanced-command-toggle"),
  form: document.querySelector("#command-form"),
  execute: document.querySelector("#execute-button"),
  cancel: document.querySelector("#cancel-button"),
  executionStatus: document.querySelector("#execution-status"),
  resultsPanel: document.querySelector("#job-result-panel"),
  results: document.querySelector("#results"),
  resultClear: document.querySelector("#job-result-clear"),
  resultToggle: document.querySelector("#job-result-toggle"),
  resultDetailPanel: document.querySelector("#result-panel"),
  resultDetail: document.querySelector("#result-detail-content"),
  resultDetailToggle: document.querySelector("#result-toggle"),
  basic: document.querySelector("#basic-controls"),
};

let commands = [];
let currentJobId = null;
let context = { mode: "live", resource: null, model_id: "keysight-dsox4024a" };
let catalog;
let commandForm;
let deviceResource;
let executing = false;
let advancedVisible = false;
let resultPresentation = { kind: "empty", job: null, message: null };
let healthState = { status: "checking", version: null, error: null };
let executionState = { key: "device.ready" };
let updateBasicAvailability = () => {};

initializeI18n();
renderLocaleToggle();
elements.localeToggle.addEventListener("click", () => setLocale(locale() === "en" ? "zh-TW" : "en"));

async function initialize() {
  renderAdvancedToggle();
  renderCollapseLabels();
  bindPresentationControls();
  await updateHealth();
  const [loadedCommands, models] = await Promise.all([
    getCommands(),
    fetch("/api/models").then((response) => response.json()),
  ]);
  commands = loadedCommands;
  models.forEach((model) => elements.model.append(new Option(model.label, model.id)));
  elements.model.value = "keysight-dsox4024a";

  catalog = new CommandCatalog(commands, {
    filter: elements.filter,
    categories: elements.categories,
    list: elements.commandList,
  }, syncCommandSelection);
  commandForm = new CommandForm(elements.form, catalog);
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
    hint: elements.hint,
    status: elements.deviceStatus,
  }, (nextContext) => {
    context = nextContext;
    if (catalog) catalog.updateMode(context.mode);
    syncCommandSelection();
    renderLiveData();
  });
  updateBasicAvailability = bindBasicControls(elements.basic, executeCommand, basicAvailable);
  updateAvailability();
  elements.execute.addEventListener("click", (event) => {
    event.preventDefault();
    const selected = catalog.selected();
    if (selected) executeCommand(selected.id, commandForm.values());
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

async function executeCommand(command, parameters) {
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
  updateAvailability();
  elements.execute.disabled = true;
  elements.cancel.classList.remove("hidden");
  setExecutionStatus({ status: "queued" });
  try {
    const job = await runJob(command, parameters, context, (updated) => {
      currentJobId = updated.job_id;
      setExecutionStatus({ status: updated.status });
      resultPresentation = { kind: "job", job: updated, message: null };
      renderCurrentResult();
      updateIdentity(updated);
    });
    setExecutionStatus({ status: job.status });
    resultPresentation = { kind: "job", job, message: null };
    renderCurrentResult();
    updateIdentity(job);
  } catch (error) {
    setExecutionStatus({ status: "failed" });
    resultPresentation = { kind: "error", job: null, message: error.message };
    renderCurrentResult();
  } finally {
    executing = false;
    currentJobId = null;
    elements.cancel.classList.add("hidden");
    updateAvailability();
  }
}

function updateIdentity(job) {
  const idn = job.result?.result?.idn || job.result?.idn;
  if (idn) elements.identity.textContent = `${idn.vendor} ${idn.model} (${idn.serial})`;
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
  renderLocaleToggle();
  renderVersion();
  renderLiveData();
  renderExecutionStatus();
  renderCollapseLabels();
  if (deviceResource) deviceResource.refresh();
  if (catalog) {
    catalog.render();
    syncCommandSelection();
  }
  renderCurrentResult();
});

function syncCommandSelection() {
  if (!catalog || !commandForm) return;
  const selected = catalog.selected();
  commandForm.render(selected);
  elements.selectedCommand.textContent = selected
    ? catalog.commandLabel(selected)
    : translate("commands.selectCommand");
  elements.commandDescription.textContent = selected
    ? catalog.description(selected)
    : translate("commands.noDescription");
  updateAvailability();
}

function commandAvailable(command) {
  if (!catalog) return false;
  const definition = commands.find((item) => item.id === command);
  if (!definition || !definition.modes.includes(context.mode)) return false;
  return context.mode !== "live" || command === "list-resources" || Boolean(context.resource);
}

function basicAvailable(command) {
  return !executing && commandAvailable(command);
}

function updateAvailability() {
  if (!catalog) return;
  const selected = catalog.selected();
  elements.execute.disabled = executing || !selected || !commandAvailable(selected.id);
  updateBasicAvailability();
}

function setExecutionStatus(state) {
  executionState = state;
  renderExecutionStatus();
  renderLiveData();
}

function renderExecutionStatus() {
  const statusClass = executionState.status ? `badge-${executionState.status}` : "badge-idle";
  elements.executionStatus.className = `badge ${statusClass}`;
  elements.executionStatus.textContent = executionState.status
    ? translateJobStatus(executionState.status)
    : translate(executionState.key);
}

function renderCurrentResult() {
  if (resultPresentation.kind === "job") {
    renderJob(elements.results, resultPresentation.job, elements.resultDetail);
  } else if (resultPresentation.kind === "error") {
    renderError(elements.results, elements.resultDetail, resultPresentation.message);
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

  const commandStatus = executionState.status;
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
        ? "live_data.ready"
        : "live_data.noResource";
  setStateIndicator(
    elements.liveState,
    translate(liveKey),
    context.mode === "live" && !context.resource ? "state-warning" : "state-ok",
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
