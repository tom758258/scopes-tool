import { getCommands, getHealth } from "/static/api.js";
import { bindBasicControls } from "/static/basic-controls.js";
import { CommandCatalog } from "/static/command-catalog.js";
import { CommandForm } from "/static/command-form.js";
import { DeviceResource } from "/static/device-resource.js";
import { initializeI18n, setLocale, translate } from "/static/i18n.js";
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
  catalog.renderCategories();
  commandForm = new CommandForm(elements.form, catalog);
  catalog.updateMode(context.mode);
  commandForm.render(catalog.selected());
  elements.command.addEventListener("change", () => commandForm.render(catalog.selected()));
  new DeviceResource({
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
  });
  bindBasicControls(elements.basic, executeCommand);
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
  elements.execute.disabled = true;
  elements.cancel.classList.remove("hidden");
  elements.executionStatus.textContent = translate("status.submitting");
  try {
    const job = await runJob(command, parameters, context, (updated) => {
      currentJobId = updated.job_id;
      elements.executionStatus.textContent = updated.status;
      renderJob(elements.results, updated);
      const idn = updated.result?.result?.idn || updated.result?.idn;
      if (idn) elements.identity.textContent = `${idn.vendor} ${idn.model} (${idn.serial})`;
    });
    elements.executionStatus.textContent = job.status;
    renderJob(elements.results, job);
  } catch (error) {
    elements.executionStatus.textContent = translate("status.failedJob");
    elements.results.textContent = error.message;
  } finally {
    elements.execute.disabled = false;
    elements.cancel.classList.add("hidden");
  }
}

async function updateHealth() {
  try {
    const health = await getHealth();
    if (health.status !== "ok" || health.package !== SERVICE_NAME) throw new Error(translate("status.unexpected"));
    elements.health.textContent = translate("status.healthy");
    elements.health.classList.add("healthy");
  } catch (error) {
    elements.health.textContent = `${translate("status.failed")}: ${error.message}`;
    elements.health.classList.add("error");
  }
}

document.addEventListener("localechange", () => {
  if (catalog) catalog.renderCategories();
});

initialize().catch((error) => {
  elements.health.textContent = `${translate("status.failed")}: ${error.message}`;
});
