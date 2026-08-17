import { getCommands, getHealth } from "/static/api.js";
import { bindBasicControls } from "/static/basic-controls.js";
import { CommandCatalog } from "/static/command-catalog.js";
import { CommandForm } from "/static/command-form.js";
import { DeviceResource } from "/static/device-resource.js";
import { initializeI18n, setLocale, translate, translateJobStatus } from "/static/i18n.js";
import { requestCancel, runJob } from "/static/jobs.js";
import { renderEmpty, renderError, renderJob } from "/static/results.js";

const SERVICE_NAME = "scopes-tool-webui";
const elements = {
  health: document.querySelector("#health-status"),
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
let latestJob;
let executing = false;
let advancedVisible = false;
let resultsVisible = false;
let healthState = { key: "status.checking" };
let executionState = { key: "device.ready" };
let updateBasicAvailability = () => {};

initializeI18n();
document.querySelectorAll(".locale-button").forEach((button) => {
  button.addEventListener("click", () => setLocale(button.dataset.locale));
});

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
    resultsVisible = false;
    renderEmpty(elements.results, elements.resultDetail);
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
  setExecutionStatus({ key: "status.submitting" });
  try {
    const job = await runJob(command, parameters, context, (updated) => {
      currentJobId = updated.job_id;
      latestJob = updated;
      resultsVisible = true;
      setExecutionStatus({ status: updated.status });
      renderJob(elements.results, updated, elements.resultDetail);
      updateIdentity(updated);
    });
    latestJob = job;
    resultsVisible = true;
    setExecutionStatus({ status: job.status });
    renderJob(elements.results, job, elements.resultDetail);
    updateIdentity(job);
  } catch (error) {
    setExecutionStatus({ status: "failed" });
    resultsVisible = true;
    renderError(elements.results, elements.resultDetail, error.message);
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
  try {
    const health = await getHealth();
    if (health.status !== "ok" || health.package !== SERVICE_NAME) throw new Error(translate("status.unexpected"));
    healthState = { key: "status.healthy" };
    elements.health.classList.add("healthy");
  } catch (error) {
    healthState = { key: "status.failed", error: error.message };
    elements.health.classList.add("error");
  }
  renderHealth();
}

document.addEventListener("localechange", () => {
  renderHealth();
  renderExecutionStatus();
  renderCollapseLabels();
  if (deviceResource) deviceResource.refresh();
  if (catalog) {
    catalog.render();
    syncCommandSelection();
  }
  if (resultsVisible && latestJob) renderJob(elements.results, latestJob, elements.resultDetail);
  if (!resultsVisible) renderEmpty(elements.results, elements.resultDetail);
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
}

function renderExecutionStatus() {
  const statusClass = executionState.status ? `badge-${executionState.status}` : "badge-idle";
  elements.executionStatus.className = `badge ${statusClass}`;
  elements.executionStatus.textContent = executionState.status
    ? translateJobStatus(executionState.status)
    : translate(executionState.key);
}

function renderHealth() {
  const message = translate(healthState.key);
  elements.health.textContent = healthState.error ? `${message}: ${healthState.error}` : message;
}

initialize().catch((error) => {
  elements.health.textContent = `${translate("status.failed")}: ${error.message}`;
});
