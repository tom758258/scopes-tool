import { getCommands, getHealth } from "/static/api.js";
import { bindBasicControls } from "/static/basic-controls.js";
import { CommandCatalog } from "/static/command-catalog.js";
import { CommandForm } from "/static/command-form.js";
import { DeviceResource } from "/static/device-resource.js";
import { initializeI18n, setLocale, translate, translateJobStatus } from "/static/i18n.js";
import { requestCancel, runJob } from "/static/jobs.js";
import { renderJob } from "/static/results.js";

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
  hint: document.querySelector("#device-hint"),
  deviceStatus: document.querySelector("#device-status"),
  identity: document.querySelector("#identity-value"),
  category: document.querySelector("#category-select"),
  command: document.querySelector("#command-select"),
  form: document.querySelector("#command-form"),
  execute: document.querySelector("#execute-button"),
  cancel: document.querySelector("#cancel-button"),
  executionStatus: document.querySelector("#execution-status"),
  results: document.querySelector("#results"),
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
let healthState = { key: "status.checking" };
let executionState = { key: "device.ready" };
let updateBasicAvailability = () => {};

initializeI18n();
document.querySelectorAll(".locale-button").forEach((button) => {
  button.addEventListener("click", () => setLocale(button.dataset.locale));
});

async function initialize() {
  await updateHealth();
  const [loadedCommands, models] = await Promise.all([getCommands(), fetch("/api/models").then((response) => response.json())]);
  commands = loadedCommands;
  models.forEach((model) => elements.model.append(new Option(model.label, model.id)));
  elements.model.value = "keysight-dsox4024a";
  catalog = new CommandCatalog(commands, elements.category, elements.command);
  commandForm = new CommandForm(elements.form, catalog);
  catalog.renderCategories();
  catalog.updateMode(context.mode);
  syncCommandSelection();
  elements.category.addEventListener("change", syncCommandSelection);
  elements.command.addEventListener("change", syncCommandSelection);
  deviceResource = new DeviceResource({
    mode: elements.mode,
    model: elements.model,
    resource: elements.resource,
    resourceList: elements.resourceList,
    scan: elements.scan,
    settings: elements.settings,
    settingsPanel: elements.settingsPanel,
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
    executeCommand(elements.command.value, commandForm.values());
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
      setExecutionStatus({ status: updated.status });
      renderJob(elements.results, updated);
      const idn = updated.result?.result?.idn || updated.result?.idn;
      if (idn) elements.identity.textContent = `${idn.vendor} ${idn.model} (${idn.serial})`;
    });
    latestJob = job;
    setExecutionStatus({ status: job.status });
    renderJob(elements.results, job);
  } catch (error) {
    setExecutionStatus({ status: "failed" });
    elements.results.textContent = error.message;
  } finally {
    executing = false;
    currentJobId = null;
    elements.cancel.classList.add("hidden");
    updateAvailability();
  }
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
  if (deviceResource) deviceResource.refresh();
  if (catalog) {
    catalog.renderCategories();
    syncCommandSelection();
  }
  if (latestJob) renderJob(elements.results, latestJob);
});

function syncCommandSelection() {
  if (!catalog || !commandForm) return;
  commandForm.render(catalog.selected());
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
  elements.execute.disabled = executing || !commandAvailable(elements.command.value);
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
