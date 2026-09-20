import { hasTranslation, translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

export const SERIAL_EDITOR_COMMANDS = Object.freeze([
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
]);

const EDITOR_PROTOCOLS = ["uart", "i2c", "spi", "can"];

export function configCommandFor(mode) {
  return EDITOR_PROTOCOLS.includes(mode) ? `serial-${mode}` : null;
}

export function triggerCommandFor(mode) {
  return EDITOR_PROTOCOLS.includes(mode) ? `serial-trigger-${mode}` : null;
}

export function busOptions(maxBus) {
  const limit = Math.max(1, Math.floor(Number(maxBus) || 1));
  return Array.from({ length: limit }, (_item, index) => index + 1);
}

export function displayModeLabel(mode, rawMode) {
  if (mode) return String(mode).toUpperCase();
  return rawMode ? String(rawMode) : null;
}

export function createSerialEditorController({
  execute,
  confirmDiscard,
  available = () => true,
} = {}) {
  const stateListeners = new Set();
  let presentationKey = null;
  let queuedReader = null;
  let protocolPending = false;
  let bus = 1;
  let maxBus = 1;
  let protocols = [...EDITOR_PROTOCOLS];
  let selectedProtocol = null;
  let confirmedMode = null;
  let rawMode = null;
  let dirtyConfig = false;
  let dirtyDisplay = false;
  let dirtyTrigger = false;
  let dirtyListerDisplay = false;
  let dirtyListerReference = false;
  let busyCount = 0;
  let formEpoch = 0;
  let listerEpoch = 0;
  const jobs = {
    mode: null,
    display: null,
    config: null,
    trigger: null,
    listerDisplay: null,
    listerReference: null,
  };

  const state = () => ({
    bus,
    maxBus,
    protocols: [...protocols],
    selectedProtocol,
    protocolPending,
    confirmedMode,
    rawMode,
    currentLabel: displayModeLabel(confirmedMode, rawMode),
    configCommand: configCommandFor(confirmedMode),
    triggerCommand: triggerCommandFor(confirmedMode),
    supported: configCommandFor(confirmedMode) !== null,
    dirtyConfig,
    dirtyDisplay,
    dirtyTrigger,
    dirtyListerDisplay,
    dirtyListerReference,
    busy: busyCount > 0,
    formEpoch,
    listerEpoch,
    jobs: { ...jobs },
  });

  const isCompleted = (job) => job?.status === "completed";

  function notifyState() {
    const snapshot = state();
    stateListeners.forEach((listener) => listener(snapshot));
  }
  const modeFromJob = (job) => {
    if (!isCompleted(job)) return { mode: null, rawMode: null };
    const payload = job.result?.result?.mode || {};
    return { mode: payload.mode ?? null, rawMode: payload.raw_mode ?? null };
  };

  function syncSelectedProtocol() {
    if (protocolPending) {
      if (selectedProtocol === confirmedMode) {
        protocolPending = false;
      } else {
        return;
      }
    }
    if (confirmedMode && protocols.includes(confirmedMode)) {
      selectedProtocol = confirmedMode;
    } else {
      selectedProtocol = null;
    }
  }

  async function runQuery(command, parameters) {
    const job = await execute(command, parameters, { intent: "readback" });
    return isCompleted(job) ? job : null;
  }

  async function readConfigForConfirmed() {
    jobs.config = null;
    const configCommand = configCommandFor(confirmedMode);
    if (!configCommand) {
      notifyState();
      return;
    }
    const configJob = await runQuery(configCommand, { action: "query", bus });
    jobs.config = configJob ? { job: configJob, applied: false, protocol: confirmedMode } : null;
    notifyState();
  }

  async function readDecode() {
    const modeJob = await runQuery("serial-mode", { action: "query", bus });
    jobs.mode = modeJob ? { job: modeJob, applied: false } : null;
    const reported = modeFromJob(modeJob);
    confirmedMode = reported.mode;
    rawMode = reported.rawMode;
    syncSelectedProtocol();
    notifyState();
    const displayJob = await runQuery("serial-display", { action: "query", bus });
    jobs.display = displayJob ? { job: displayJob, applied: false } : null;
    notifyState();
    await readConfigForConfirmed();
  }

  async function readTriggerForConfirmed() {
    jobs.trigger = null;
    const triggerCommand = triggerCommandFor(confirmedMode);
    if (!triggerCommand) {
      notifyState();
      return;
    }
    const triggerJob = await runQuery(triggerCommand, { action: "query", bus });
    jobs.trigger = triggerJob ? { job: triggerJob, applied: false } : null;
    notifyState();
  }

  async function readTrigger() {
    const modeJob = await runQuery("serial-mode", { action: "query", bus });
    jobs.mode = modeJob ? { job: modeJob, applied: false } : null;
    const reported = modeFromJob(modeJob);
    confirmedMode = reported.mode;
    rawMode = reported.rawMode;
    syncSelectedProtocol();
    notifyState();
    await readTriggerForConfirmed();
  }

  async function readListerState() {
    const listerJob = await runQuery("serial-lister-query", {});
    const entry = listerJob ? { job: listerJob, applied: false } : null;
    jobs.listerDisplay = entry;
    jobs.listerReference = entry;
    notifyState();
  }

  async function drainQueuedRefresh() {
    if (busyCount > 0 || !queuedReader) return;
    const next = queuedReader;
    queuedReader = null;
    await runRefresh(next);
  }

  async function runRefresh(reader) {
    if (busyCount > 0) {
      queuedReader = reader;
      return;
    }
    if (!available()) return;
    busyCount += 1;
    try {
      await reader();
    } finally {
      busyCount -= 1;
      notifyState();
      await drainQueuedRefresh();
    }
  }

  function refreshDecode() {
    return runRefresh(readDecode);
  }

  function refreshTrigger() {
    return runRefresh(readTrigger);
  }

  function refreshLister() {
    return runRefresh(readListerState);
  }

  function beginBusy() {
    busyCount += 1;
    notifyState();
  }

  async function endBusy() {
    busyCount -= 1;
    notifyState();
    await drainQueuedRefresh();
  }

  async function changeMode(target) {
    // Low-level bus mode switch used by applyDecode. On success it updates
    // the confirmed mode and invalidates stale Trigger state WITHOUT
    // touching the pending Decode configuration draft for the target.
    const job = await execute(
      "serial-mode",
      { action: "set", bus, mode: target },
      { intent: "apply" },
    );
    if (!isCompleted(job)) return job;
    const reported = modeFromJob(job);
    if (reported.mode !== target) return job;
    confirmedMode = target;
    rawMode = reported.rawMode;
    protocolPending = false;
    dirtyTrigger = false;
    jobs.mode = { job, applied: true };
    jobs.trigger = null;
    syncSelectedProtocol();
    notifyState();
    return job;
  }

  return {
    get state() {
      return state();
    },
    onStateChange(callback) {
      if (typeof callback === "function") stateListeners.add(callback);
      return () => stateListeners.delete(callback);
    },
    refreshDecode() {
      return refreshDecode();
    },
    refreshTrigger() {
      return refreshTrigger();
    },
    refreshLister() {
      return refreshLister();
    },
    reset({ maxBus: busLimit = 1, protocolChoices = [...EDITOR_PROTOCOLS] } = {}) {
      presentationKey = null;
      protocolPending = false;
      bus = 1;
      maxBus = busLimit;
      protocols = [...protocolChoices];
      selectedProtocol = null;
      confirmedMode = null;
      rawMode = null;
      dirtyConfig = false;
      dirtyDisplay = false;
      dirtyTrigger = false;
      dirtyListerDisplay = false;
      dirtyListerReference = false;
      jobs.mode = null;
      jobs.display = null;
      jobs.config = null;
      jobs.trigger = null;
      jobs.listerDisplay = null;
      jobs.listerReference = null;
      formEpoch += 1;
      listerEpoch += 1;
      notifyState();
    },
    syncCaps({ maxBus: busLimit = 1, protocolChoices = [...EDITOR_PROTOCOLS], key = "" } = {}) {
      if (key === presentationKey) return false;
      this.reset({ maxBus: busLimit, protocolChoices });
      presentationKey = key;
      return true;
    },
    selectBus(nextBus) {
      const candidate = Number(nextBus);
      if (busyCount > 0 || candidate === bus) return;
      if (!busOptions(maxBus).includes(candidate)) return;
      if ((dirtyConfig || dirtyDisplay || dirtyTrigger || protocolPending) && !confirmDiscard()) {
        notifyState();
        return;
      }
      bus = candidate;
      confirmedMode = null;
      rawMode = null;
      selectedProtocol = null;
      protocolPending = false;
      dirtyConfig = false;
      dirtyDisplay = false;
      dirtyTrigger = false;
      jobs.mode = null;
      jobs.display = null;
      jobs.config = null;
      jobs.trigger = null;
      formEpoch += 1;
      notifyState();
    },
    selectProtocol(protocol) {
      if (busyCount > 0 || !protocols.includes(protocol)) return;
      if (protocol === selectedProtocol) return;
      if (dirtyConfig && !confirmDiscard()) {
        notifyState();
        return;
      }
      selectedProtocol = protocol;
      protocolPending = protocol !== confirmedMode;
      dirtyConfig = false;
      jobs.config = null;
      notifyState();
    },
    setDirty(kind, value) {
      if (kind === "config") dirtyConfig = Boolean(value);
      if (kind === "display") dirtyDisplay = Boolean(value);
      if (kind === "trigger") dirtyTrigger = Boolean(value);
      if (kind === "listerDisplay") dirtyListerDisplay = Boolean(value);
      if (kind === "listerReference") dirtyListerReference = Boolean(value);
      notifyState();
    },
    isDirty() {
      return (
        dirtyConfig
        || dirtyDisplay
        || dirtyTrigger
        || dirtyListerDisplay
        || dirtyListerReference
      );
    },
    applyDecode: async function applyDecode(displayValues, configValues) {
      if (busyCount > 0 || !available()) return null;
      const displayPayload = displayValues || {};
      const configPayload = configValues || {};
      const wantsDisplay = Object.keys(displayPayload).length > 0;
      const wantsConfig = Object.keys(configPayload).length > 0;
      const target = protocolPending
        ? selectedProtocol
        : (configCommandFor(confirmedMode) ? confirmedMode : null);
      if (!target && !wantsDisplay && !wantsConfig) return null;
      if (target && target === confirmedMode && !wantsDisplay && !wantsConfig) {
        protocolPending = false;
        return null;
      }
      const configCommand = target ? configCommandFor(target) : null;
      if (target && !configCommand) return null;
      beginBusy();
      try {
        if (target && target !== confirmedMode) {
          if (dirtyTrigger && !confirmDiscard()) {
            notifyState();
            return null;
          }
          const modeJob = await changeMode(target);
          if (!isCompleted(modeJob)) return modeJob;
          if (modeFromJob(modeJob).mode !== target) {
            await readDecode();
            return modeJob;
          }
        }
        if (wantsDisplay) {
          const displayJob = await execute(
            "serial-display",
            { action: "set", bus, ...displayPayload },
            { intent: "apply" },
          );
          if (!isCompleted(displayJob)) return displayJob;
          dirtyDisplay = false;
          jobs.display = { job: displayJob, applied: true };
          notifyState();
        }
        if (wantsConfig) {
          if (!configCommand) return null;
          const modeJob = await runQuery("serial-mode", { action: "query", bus });
          if (!modeJob) return null;
          const reported = modeFromJob(modeJob);
          if (reported.mode !== target) {
            confirmedMode = reported.mode;
            rawMode = reported.rawMode;
            dirtyConfig = false;
            dirtyTrigger = false;
            jobs.config = null;
            jobs.trigger = null;
            syncSelectedProtocol();
            notifyState();
            await readDecode();
            return modeJob;
          }
          const job = await execute(
            configCommand,
            { action: "set", bus, ...configPayload },
            { intent: "apply" },
          );
          if (!isCompleted(job)) return job;
          dirtyConfig = false;
          jobs.config = { job, applied: true, protocol: target };
          notifyState();
        }
        protocolPending = false;
        await readDecode();
        return jobs.config?.job ?? jobs.display?.job ?? jobs.mode?.job ?? null;
      } finally {
        await endBusy();
      }
    },
    applyTrigger: async function applyTrigger(values) {
      const command = triggerCommandFor(confirmedMode);
      if (busyCount > 0 || !command || !available()) return null;
      const payload = values || {};
      if (!Object.keys(payload).length) return null;
      beginBusy();
      try {
        const modeJob = await runQuery("serial-mode", { action: "query", bus });
        if (!modeJob) return null;
        const reported = modeFromJob(modeJob);
        if (reported.mode !== confirmedMode) {
          confirmedMode = reported.mode;
          rawMode = reported.rawMode;
          dirtyTrigger = false;
          jobs.trigger = null;
          syncSelectedProtocol();
          notifyState();
          await readTriggerForConfirmed();
          return modeJob;
        }
        const job = await execute(
          command,
          { action: "set", bus, ...payload },
          { intent: "apply" },
        );
        if (isCompleted(job)) {
          dirtyTrigger = false;
          jobs.trigger = { job, applied: true };
          notifyState();
        }
        return job;
      } finally {
        await endBusy();
      }
    },
    applyListerSetting: async function applyListerSetting(kind, values) {
      const command = kind === "reference"
        ? "serial-lister-reference"
        : "serial-lister-display";
      const dirtyFlag = kind === "reference"
        ? () => { dirtyListerReference = false; }
        : () => { dirtyListerDisplay = false; };
      const slot = kind === "reference" ? "listerReference" : "listerDisplay";
      if (busyCount > 0 || !available()) return null;
      const payload = values || {};
      if (!Object.keys(payload).length) return null;
      beginBusy();
      try {
        const job = await execute(
          command,
          { action: "set", ...payload },
          { intent: "apply" },
        );
        if (isCompleted(job)) {
          dirtyFlag();
          jobs[slot] = { job, applied: true };
          notifyState();
        }
        return job;
      } finally {
        await endBusy();
      }
    },
    exportLister: async function exportLister(filenameValue) {
      if (busyCount > 0 || !available()) return null;
      const filename = typeof filenameValue === "string" ? filenameValue.trim() : "";
      if (!filename) return null;
      beginBusy();
      try {
        return await execute(
          "serial-lister-export",
          { filename },
          {},
        );
      } finally {
        await endBusy();
      }
    },
  };
}

function editorSubDefinition(catalog, commandId) {
  const definition = catalog.commands.find((entry) => entry.id === commandId);
  if (!definition) return null;
  return {
    ...definition,
    fields: catalog.fieldsFor(definition).filter((field) => field.name !== "bus"),
    presentation: { ...definition.presentation, query_fields: [] },
  };
}

class SerialWorkspaceBase {
  constructor(container, catalog, hooks, controller) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.controller = controller;
    this.syncedJobs = {};
    this.renderedBusLimit = null;
    this.unsubscribe = controller.onStateChange((stateSnapshot) => this.render(stateSnapshot));
  }

  labeledField(labelKey, input) {
    const wrapper = document.createElement("label");
    wrapper.className = "field serial-editor-field";
    const label = document.createElement("span");
    label.dataset.i18nKey = labelKey;
    label.textContent = translate(labelKey);
    wrapper.append(label, input);
    return wrapper;
  }

  section(titleKey, content, actionButton) {
    const root = document.createElement("div");
    root.className = "serial-editor-section";
    const heading = document.createElement("strong");
    heading.className = "serial-editor-heading";
    heading.dataset.i18nKey = titleKey;
    heading.textContent = translate(titleKey);
    root.append(heading);
    for (const node of [].concat(content)) root.append(node);
    if (actionButton) root.append(actionButton);
    return root;
  }

  actionButton(labelText, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary serial-editor-action";
    button.textContent = labelText;
    button.addEventListener("click", onClick);
    return button;
  }

  makeReadButton(labelKey, onRead) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary serial-editor-refresh";
    button.textContent = translate(labelKey);
    button.addEventListener("click", () => {
      onRead();
    });
    if (this.hooks.headerActions) {
      button.hidden = true;
      this.hooks.headerActions.append(button);
    }
    return button;
  }

  makeBusSelect() {
    const select = document.createElement("select");
    select.addEventListener("change", () => {
      this.controller.selectBus(select.value);
    });
    return select;
  }

  renderOptions(select, options, selectedValue) {
    select.replaceChildren();
    options.forEach((option) => {
      const item = new Option(option.label, option.value);
      if (option.disabled) item.disabled = true;
      select.append(item);
    });
    if (selectedValue !== null && selectedValue !== undefined) {
      select.value = String(selectedValue);
    }
  }

  syncBusSelect(select, stateSnapshot, disabled) {
    if (this.renderedBusLimit !== stateSnapshot.maxBus) {
      this.renderedBusLimit = stateSnapshot.maxBus;
      this.renderOptions(
        select,
        busOptions(stateSnapshot.maxBus).map((value) => ({
          value: String(value),
          label: translate("serial.editor.busOption", { bus: value }),
        })),
        stateSnapshot.bus,
      );
    }
    select.disabled = disabled;
    select.value = String(stateSnapshot.bus);
  }

  editorDefinition(commandId) {
    return editorSubDefinition(this.catalog, commandId);
  }

  syncFormSlot(form, slotName, entries) {
    const entry = entries[slotName];
    if (!form || !entry) return;
    if (this.syncedJobs[slotName] === entry.job.job_id) return;
    this.syncedJobs[slotName] = entry.job.job_id;
    if (entry.applied) {
      form.clearDirty();
      form.syncResult(entry.job, false);
    } else {
      form.syncResult(entry.job, true);
    }
  }

  refreshI18n() {
    this.container.querySelectorAll("[data-i18n-key]").forEach((node) => {
      node.textContent = translate(node.dataset.i18nKey);
    });
  }

  rerender() {
    this.render(this.controller.state);
  }
}

export class SerialDecodeEditor extends SerialWorkspaceBase {
  constructor(container, catalog, hooks, controller) {
    super(container, catalog, hooks, controller);
    this.renderedFormEpoch = null;
    this.renderedProtocols = null;
    this.renderedSelectedProtocol = undefined;
    this.displayFormReady = false;
    this.buildDom();
  }

  buildDom() {
    this.container.replaceChildren();

    this.busSelect = this.makeBusSelect();

    this.currentValue = document.createElement("output");
    this.currentValue.className = "readonly-value serial-editor-current-value";

    this.protocolSelect = document.createElement("select");
    this.protocolSelect.addEventListener("change", () => {
      this.controller.selectProtocol(this.protocolSelect.value);
    });

    const topRow = document.createElement("div");
    topRow.className = "serial-editor-row";
    topRow.append(
      this.labeledField("serial.editor.bus", this.busSelect),
      this.labeledField("serial.decode.currentProtocol", this.currentValue),
      this.labeledField("serial.editor.protocol", this.protocolSelect),
    );

    this.refreshButton = this.makeReadButton("serial.decode.readSettings", () => {
      queueMicrotask(() => void this.controller.refreshDecode());
    });

    this.displayDescription = document.createElement("p");
    this.displayDescription.className = "muted compact-note";
    this.displayFormContainer = document.createElement("div");
    this.displayFormContainer.className = "command-form";
    this.displaySection = this.section(
      "serial.editor.displaySection",
      [this.displayDescription, this.displayFormContainer],
      null,
    );

    this.configNote = document.createElement("p");
    this.configNote.className = "muted compact-note";
    this.configDescription = document.createElement("p");
    this.configDescription.className = "muted compact-note";
    this.configFormContainer = document.createElement("div");
    this.configFormContainer.className = "command-form";
    this.applyDecodeButton = this.actionButton(
      translate("serial.decode.applySettings"),
      () => void this.submitDecode(),
    );
    this.configSection = this.section(
      "serial.editor.configuration",
      [this.configNote, this.configDescription, this.configFormContainer],
      this.applyDecodeButton,
    );

    this.container.append(
      topRow,
      ...(this.hooks.headerActions ? [] : [this.refreshButton]),
      this.displaySection,
      this.configSection,
    );
    this.displayForm = new CommandForm(this.displayFormContainer, this.catalog);
  }

  rebuildDecodeForms() {
    this.displayFormContainer.replaceChildren();
    this.displayForm = new CommandForm(this.displayFormContainer, this.catalog);
    this.displayFormReady = false;
    this.configFormContainer.replaceChildren();
    this.configForm = null;
    this.renderedSelectedProtocol = undefined;
    this.syncedJobs.display = null;
    this.syncedJobs.config = null;
  }

  ensureDisplayForm() {
    if (this.displayFormReady) return;
    const definition = this.editorDefinition("serial-display");
    if (!definition) return;
    this.displayDescription.textContent = this.catalog.description?.(definition) || "";
    this.displayDescription.hidden = !this.displayDescription.textContent;
    this.displayForm.render(definition, {
      onDirty: () => this.controller.setDirty("display", this.displayForm.isDirty()),
    });
    this.displayFormReady = true;
  }

  ensureDecodeConfigForm(selectedProtocol) {
    const commandId = selectedProtocol ? `serial-${selectedProtocol}` : null;
    if (this.renderedSelectedProtocol === selectedProtocol && this.renderedConfigCommand === commandId) return;
    this.renderedSelectedProtocol = selectedProtocol;
    this.renderedConfigCommand = commandId;
    this.configFormContainer.replaceChildren();
    this.configForm = commandId ? new CommandForm(this.configFormContainer, this.catalog) : null;
    this.syncedJobs.config = null;
    if (!commandId || !this.configForm) return;
    const definition = this.editorDefinition(commandId);
    if (!definition) return;
    this.configDescription.textContent = this.catalog.description?.(definition) || "";
    this.configDescription.hidden = !this.configDescription.textContent;
    this.configForm.render(definition, {
      onDirty: () => this.controller.setDirty("config", this.configForm.isDirty()),
    });
  }

  syncDecodeConfigForm(stateSnapshot) {
    const entry = stateSnapshot.jobs.config;
    if (!this.configForm || !entry) return;
    if (entry.protocol !== stateSnapshot.selectedProtocol) return;
    this.syncFormSlot(this.configForm, "config", stateSnapshot.jobs);
  }

  async submitDecode() {
    if (this.controller.state.busy || this.hooks.isExecutionBusy?.()) return;
    const pending = this.controller.state.protocolPending;
    let display = {};
    if (this.displayForm?.isDirty()) {
      const displayValues = this.displayForm.values();
      if (displayValues === null) return;
      display = { ...displayValues };
      delete display.action;
    }
    let config = {};
    if (this.configForm?.isDirty()) {
      const configValues = this.configForm.values();
      if (configValues === null) return;
      config = { ...configValues };
      delete config.action;
    }
    if (!Object.keys(display).length && !Object.keys(config).length && !pending) return;
    await this.controller.applyDecode(display, config);
  }

  schedulePresentation() {
    const info = this.hooks.modelInfo();
    this.controller.syncCaps({
      maxBus: info.supported ? info.maxBus : 0,
      protocolChoices: info.protocols,
      key: `${this.hooks.contextKey()}|${this.hooks.isAvailable()}`,
    });
    if (info.supported) {
      queueMicrotask(() => void this.controller.refreshDecode());
    }
  }

  render(stateSnapshot) {
    const unavailable = !this.hooks.isAvailable();
    const disabled = stateSnapshot.busy || this.hooks.isExecutionBusy?.() || unavailable;

    if (this.renderedFormEpoch !== stateSnapshot.formEpoch) {
      this.renderedFormEpoch = stateSnapshot.formEpoch;
      this.renderedSelectedProtocol = undefined;
      this.rebuildDecodeForms();
    }

    this.refreshI18n();
    this.applyDecodeButton.textContent = translate("serial.decode.applySettings");
    this.refreshButton.textContent = translate("serial.decode.readSettings");

    this.syncBusSelect(this.busSelect, stateSnapshot, disabled);

    if (this.renderedProtocols?.join("|") !== stateSnapshot.protocols.join("|")) {
      this.renderedProtocols = [...stateSnapshot.protocols];
      this.renderOptions(
        this.protocolSelect,
        [
          { value: "", label: translate("form.selectValue"), disabled: true },
          ...stateSnapshot.protocols.map((protocol) => ({
            value: protocol,
            label: protocol.toUpperCase(),
          })),
        ],
        stateSnapshot.selectedProtocol ?? "",
      );
    }
    this.protocolSelect.value = stateSnapshot.selectedProtocol ?? "";
    this.protocolSelect.disabled = disabled;

    this.currentValue.textContent = stateSnapshot.currentLabel || "-";

    this.refreshButton.disabled = disabled;

    this.ensureDisplayForm();
    this.displayForm?.setDisabled(disabled);

    const showUnsupported = !unavailable && !stateSnapshot.supported;
    if (showUnsupported) {
      const protocolName = stateSnapshot.currentLabel || "-";
      this.configNote.hidden = false;
      this.configNote.textContent = hasTranslation("serial.editor.unsupported")
        ? translate("serial.editor.unsupported", { protocol: protocolName })
        : protocolName;
    } else {
      this.configNote.hidden = true;
    }
    this.ensureDecodeConfigForm(stateSnapshot.selectedProtocol);
    this.configForm?.setDisabled(disabled);

    this.applyDecodeButton.disabled = disabled
      || (!stateSnapshot.selectedProtocol && !stateSnapshot.dirtyDisplay && !stateSnapshot.dirtyConfig);

    this.syncFormSlot(this.displayForm, "display", stateSnapshot.jobs);
    if (!showUnsupported) {
      this.syncDecodeConfigForm(stateSnapshot);
    }
  }
}

export class SerialTriggerEditor extends SerialWorkspaceBase {
  constructor(container, catalog, hooks, controller) {
    super(container, catalog, hooks, controller);
    this.renderedFormEpoch = null;
    this.renderedTriggerCommand = undefined;
    this.buildDom();
  }

  buildDom() {
    this.container.replaceChildren();

    this.busSelect = this.makeBusSelect();

    this.currentValue = document.createElement("output");
    this.currentValue.className = "readonly-value serial-editor-current-value";

    const topRow = document.createElement("div");
    topRow.className = "serial-editor-row";
    topRow.append(
      this.labeledField("serial.editor.bus", this.busSelect),
      this.labeledField("serial.trigger.currentProtocol", this.currentValue),
    );

    this.refreshButton = this.makeReadButton("serial.trigger.readSettings", () => {
      queueMicrotask(() => void this.controller.refreshTrigger());
    });

    this.triggerNote = document.createElement("p");
    this.triggerNote.className = "muted compact-note";
    this.triggerDescription = document.createElement("p");
    this.triggerDescription.className = "muted compact-note";
    this.triggerFormContainer = document.createElement("div");
    this.triggerFormContainer.className = "command-form";
    this.applyTriggerButton = this.actionButton(
      translate("serial.editor.applyTrigger"),
      () => void this.submitTrigger(),
    );
    this.triggerSection = this.section(
      "serial.editor.triggerSection",
      [this.triggerNote, this.triggerDescription, this.triggerFormContainer],
      this.applyTriggerButton,
    );

    this.container.append(
      topRow,
      ...(this.hooks.headerActions ? [] : [this.refreshButton]),
      this.triggerSection,
    );
  }

  ensureTriggerForm(commandId) {
    if (this.renderedTriggerCommand === commandId) return;
    this.renderedTriggerCommand = commandId;
    this.triggerFormContainer.replaceChildren();
    this.triggerForm = new CommandForm(this.triggerFormContainer, this.catalog);
    this.syncedJobs.trigger = null;
    const definition = commandId ? this.editorDefinition(commandId) : null;
    if (!definition) return;
    this.triggerDescription.textContent = this.catalog.description?.(definition) || "";
    this.triggerDescription.hidden = !this.triggerDescription.textContent;
    this.triggerForm.render(definition, {
      onDirty: () => this.controller.setDirty("trigger", this.triggerForm.isDirty()),
    });
  }

  async submitTrigger() {
    if (!this.triggerForm || this.controller.state.busy || this.hooks.isExecutionBusy?.()) return;
    const values = this.triggerForm.values();
    if (values === null) return;
    delete values.action;
    if (!Object.keys(values).length) return;
    await this.controller.applyTrigger(values);
  }

  schedulePresentation() {
    const info = this.hooks.modelInfo();
    this.controller.syncCaps({
      maxBus: info.supported ? info.maxBus : 0,
      protocolChoices: info.protocols,
      key: `${this.hooks.contextKey()}|${this.hooks.isAvailable()}`,
    });
    if (info.supported) {
      queueMicrotask(() => void this.controller.refreshTrigger());
    }
  }

  render(stateSnapshot) {
    const unavailable = !this.hooks.isAvailable();
    const disabled = stateSnapshot.busy || this.hooks.isExecutionBusy?.() || unavailable;

    if (this.renderedFormEpoch !== stateSnapshot.formEpoch) {
      this.renderedFormEpoch = stateSnapshot.formEpoch;
      this.renderedTriggerCommand = undefined;
      this.triggerFormContainer.replaceChildren();
      this.triggerForm = null;
      this.syncedJobs.trigger = null;
    }

    this.refreshI18n();
    this.applyTriggerButton.textContent = translate("serial.editor.applyTrigger");
    this.refreshButton.textContent = translate("serial.trigger.readSettings");

    this.syncBusSelect(this.busSelect, stateSnapshot, disabled);
    this.currentValue.textContent = stateSnapshot.currentLabel || "-";
    this.refreshButton.disabled = disabled;

    const showUnsupported = !unavailable && !stateSnapshot.supported;
    if (showUnsupported) {
      const protocolName = stateSnapshot.currentLabel || "-";
      this.triggerNote.hidden = false;
      this.triggerNote.textContent = hasTranslation("serial.editor.unsupported")
        ? translate("serial.editor.unsupported", { protocol: protocolName })
        : protocolName;
      this.triggerSection.hidden = true;
      this.triggerForm = null;
      this.renderedTriggerCommand = undefined;
    } else {
      this.triggerNote.hidden = true;
      this.triggerSection.hidden = !stateSnapshot.supported;
      this.ensureTriggerForm(stateSnapshot.supported ? stateSnapshot.triggerCommand : null);
      this.triggerForm?.setDisabled(disabled);
      this.syncFormSlot(this.triggerForm, "trigger", stateSnapshot.jobs);
    }

    this.applyTriggerButton.disabled = disabled || !stateSnapshot.supported;
  }
}

export class SerialListerEditor extends SerialWorkspaceBase {
  constructor(container, catalog, hooks, controller) {
    super(container, catalog, hooks, controller);
    this.renderedListerEpoch = null;
    this.buildDom();
  }

  buildDom() {
    this.container.replaceChildren();

    this.refreshButton = this.makeReadButton("serial.lister.readSettings", () => {
      queueMicrotask(() => void this.controller.refreshLister());
    });

    const root = document.createElement("div");
    root.className = "serial-editor-section";
    const heading = document.createElement("strong");
    heading.className = "serial-editor-heading";
    heading.dataset.i18nKey = "serial.editor.listerSection";
    heading.textContent = translate("serial.editor.listerSection");
    root.append(heading);

    const addRow = (container, button) => {
      const row = document.createElement("div");
      row.className = "serial-editor-row";
      row.append(container, button);
      root.append(row);
    };

    this.listerDisplayFormContainer = document.createElement("div");
    this.applyListerDisplayButton = this.actionButton(
      translate("actions.apply"),
      () => void this.submitListerSetting("display"),
    );
    addRow(this.listerDisplayFormContainer, this.applyListerDisplayButton);

    this.listerReferenceFormContainer = document.createElement("div");
    this.applyListerReferenceButton = this.actionButton(
      translate("actions.apply"),
      () => void this.submitListerSetting("reference"),
    );
    addRow(this.listerReferenceFormContainer, this.applyListerReferenceButton);

    this.exportFormContainer = document.createElement("div");
    this.exportButton = this.actionButton(
      translate("serial.editor.export"),
      () => void this.submitExport(),
    );
    addRow(this.exportFormContainer, this.exportButton);

    this.listerDisplayForm = new CommandForm(this.listerDisplayFormContainer, this.catalog);
    this.listerReferenceForm = new CommandForm(this.listerReferenceFormContainer, this.catalog);
    this.exportForm = new CommandForm(this.exportFormContainer, this.catalog);

    this.container.append(
      ...(this.hooks.headerActions ? [] : [this.refreshButton]),
      root,
    );
  }

  rebuildListerForms() {
    this.listerDisplayFormContainer.replaceChildren();
    this.listerReferenceFormContainer.replaceChildren();
    this.exportFormContainer.replaceChildren();
    this.listerDisplayForm = new CommandForm(this.listerDisplayFormContainer, this.catalog);
    this.listerReferenceForm = new CommandForm(this.listerReferenceFormContainer, this.catalog);
    this.exportForm = new CommandForm(this.exportFormContainer, this.catalog);
    const displayDefinition = this.editorDefinition("serial-lister-display");
    if (displayDefinition) {
      this.listerDisplayForm.render(displayDefinition, {
        onDirty: () => this.controller.setDirty("listerDisplay", this.listerDisplayForm.isDirty()),
      });
    }
    const referenceDefinition = this.editorDefinition("serial-lister-reference");
    if (referenceDefinition) {
      this.listerReferenceForm.render(referenceDefinition, {
        onDirty: () => this.controller.setDirty("listerReference", this.listerReferenceForm.isDirty()),
      });
    }
    const exportDefinition = this.editorDefinition("serial-lister-export");
    if (exportDefinition) {
      this.exportForm.render(exportDefinition, {});
    }
    this.syncedJobs.listerDisplay = null;
    this.syncedJobs.listerReference = null;
  }

  async submitListerSetting(kind) {
    const form = kind === "reference"
      ? this.listerReferenceForm
      : this.listerDisplayForm;
    if (!form || this.controller.state.busy || this.hooks.isExecutionBusy?.()) return;
    const values = form.values();
    if (values === null) return;
    delete values.action;
    if (!Object.keys(values).length) return;
    await this.controller.applyListerSetting(kind, values);
  }

  async submitExport() {
    if (!this.exportForm || this.controller.state.busy || this.hooks.isExecutionBusy?.()) return;
    const values = this.exportForm.values();
    if (values === null) return;
    await this.controller.exportLister(values.filename);
  }

  schedulePresentation() {
    const info = this.hooks.modelInfo();
    this.controller.syncCaps({
      maxBus: info.supported ? info.maxBus : 0,
      protocolChoices: info.protocols,
      key: `${this.hooks.contextKey()}|${this.hooks.isAvailable()}`,
    });
    if (info.supported) {
      queueMicrotask(() => void this.controller.refreshLister());
    }
  }

  render(stateSnapshot) {
    const unavailable = !this.hooks.isAvailable();
    const disabled = stateSnapshot.busy || this.hooks.isExecutionBusy?.() || unavailable;

    if (this.renderedListerEpoch !== stateSnapshot.listerEpoch) {
      this.renderedListerEpoch = stateSnapshot.listerEpoch;
      this.rebuildListerForms();
    }

    this.refreshI18n();
    this.applyListerDisplayButton.textContent = translate("actions.apply");
    this.applyListerReferenceButton.textContent = translate("actions.apply");
    this.exportButton.textContent = translate("serial.editor.export");
    this.refreshButton.textContent = translate("serial.lister.readSettings");
    this.refreshButton.disabled = disabled;

    this.applyListerDisplayButton.disabled = disabled;
    this.applyListerReferenceButton.disabled = disabled;
    this.exportButton.disabled = disabled;

    this.listerDisplayForm?.setDisabled(disabled);
    this.listerReferenceForm?.setDisabled(disabled);
    this.exportForm?.setDisabled(disabled);
    this.syncFormSlot(this.listerDisplayForm, "listerDisplay", stateSnapshot.jobs);
    this.syncFormSlot(this.listerReferenceForm, "listerReference", stateSnapshot.jobs);
  }
}
