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
  let emitState = () => {};
  let bus = 1;
  let maxBus = 1;
  let protocols = [...EDITOR_PROTOCOLS];
  let selectedProtocol = EDITOR_PROTOCOLS[0];
  let confirmedMode = null;
  let rawMode = null;
  let dirtyConfig = false;
  let dirtyDisplay = false;
  let dirtyTrigger = false;
  let dirtyListerDisplay = false;
  let dirtyListerReference = false;
  let busyCount = 0;
  let refreshQueued = false;
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
    emitState(state());
  }
  const modeFromJob = (job) => {
    if (!isCompleted(job)) return { mode: null, rawMode: null };
    const payload = job.result?.result?.mode || {};
    return { mode: payload.mode ?? null, rawMode: payload.raw_mode ?? null };
  };

  function syncSelectedProtocol() {
    if (confirmedMode && protocols.includes(confirmedMode)) {
      selectedProtocol = confirmedMode;
    }
  }

  async function runQuery(command, parameters) {
    const job = await execute(command, parameters, { intent: "readback" });
    return isCompleted(job) ? job : null;
  }

  async function readProtocolSections() {
    const configCommand = configCommandFor(confirmedMode);
    jobs.config = null;
    jobs.trigger = null;
    if (!configCommand) {
      notifyState();
      return;
    }
    const configJob = await runQuery(configCommand, { action: "query", bus });
    jobs.config = configJob ? { job: configJob, applied: false } : null;
    notifyState();
    const triggerCommand = triggerCommandFor(confirmedMode);
    const triggerJob = await runQuery(triggerCommand, { action: "query", bus });
    jobs.trigger = triggerJob ? { job: triggerJob, applied: false } : null;
    notifyState();
  }

  async function readDisplayAndConfig() {
    const displayJob = await runQuery("serial-display", { action: "query", bus });
    jobs.display = displayJob ? { job: displayJob, applied: false } : null;
    notifyState();
    await readProtocolSections();
  }

  async function readListerState() {
    const listerJob = await runQuery("serial-lister-query", {});
    const entry = listerJob ? { job: listerJob, applied: false } : null;
    jobs.listerDisplay = entry;
    jobs.listerReference = entry;
    notifyState();
  }

  async function readBusState() {
    const modeJob = await runQuery("serial-mode", { action: "query", bus });
    jobs.mode = modeJob ? { job: modeJob, applied: false } : null;
    const reported = modeFromJob(modeJob);
    confirmedMode = reported.mode;
    rawMode = reported.rawMode;
    syncSelectedProtocol();
    notifyState();
    await readDisplayAndConfig();
    await readListerState();
  }

  async function refresh() {
    if (busyCount > 0) {
      refreshQueued = true;
      return;
    }
    if (!available()) return;
    busyCount += 1;
    try {
      await readBusState();
    } finally {
      busyCount -= 1;
      notifyState();
      if (refreshQueued) {
        refreshQueued = false;
        await refresh();
      }
    }
  }

  function beginBusy() {
    busyCount += 1;
    notifyState();
  }

  function endBusy() {
    busyCount -= 1;
    notifyState();
  }

  function scheduleRefresh() {
    queueMicrotask(() => {
      void refresh();
    });
  }

  return {
    get state() {
      return state();
    },
    onStateChange(callback) {
      emitState = callback;
    },
    reset({ maxBus: busLimit = 1, protocolChoices = [...EDITOR_PROTOCOLS] } = {}) {
      bus = 1;
      maxBus = busLimit;
      protocols = [...protocolChoices];
      selectedProtocol = protocols[0] || null;
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
    scheduleRefresh() {
      scheduleRefresh();
    },
    selectBus(nextBus) {
      const candidate = Number(nextBus);
      if (busyCount > 0 || candidate === bus) return;
      if (!busOptions(maxBus).includes(candidate)) return;
      if ((dirtyConfig || dirtyDisplay || dirtyTrigger) && !confirmDiscard()) {
        notifyState();
        return;
      }
      bus = candidate;
      confirmedMode = null;
      rawMode = null;
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
      selectedProtocol = protocol;
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
    applyMode: async function applyMode() {
      if (busyCount > 0 || !available() || !selectedProtocol) return null;
      if (selectedProtocol === confirmedMode) return null;
      if ((dirtyConfig || dirtyTrigger) && !confirmDiscard()) return null;
      const target = selectedProtocol;
      beginBusy();
      try {
        const job = await execute(
          "serial-mode",
          { action: "set", bus, mode: target },
          { intent: "apply" },
        );
        if (isCompleted(job)) {
          const reported = modeFromJob(job);
          if (reported.mode === target) {
            confirmedMode = target;
            rawMode = reported.rawMode;
            dirtyConfig = false;
            dirtyTrigger = false;
            jobs.config = null;
            jobs.trigger = null;
            jobs.mode = { job, applied: true };
            notifyState();
            await readProtocolSections();
          } else {
            await readBusState();
          }
        }
        return job;
      } finally {
        endBusy();
      }
    },
    applyDisplay: async function applyDisplay(parameters) {
      if (busyCount > 0 || !available()) return null;
      const values = parameters || {};
      if (!Object.keys(values).length) return null;
      beginBusy();
      try {
        const job = await execute(
          "serial-display",
          { action: "set", bus, ...values },
          { intent: "apply" },
        );
        if (isCompleted(job)) {
          dirtyDisplay = false;
          jobs.display = { job, applied: true };
          notifyState();
        }
        return job;
      } finally {
        endBusy();
      }
    },
    applyConfig: async function applyConfig(values) {
      const command = configCommandFor(confirmedMode);
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
          dirtyConfig = false;
          dirtyTrigger = false;
          jobs.config = null;
          jobs.trigger = null;
          syncSelectedProtocol();
          notifyState();
          await readDisplayAndConfig();
          return modeJob;
        }
        const job = await execute(
          command,
          { action: "set", bus, ...payload },
          { intent: "apply" },
        );
        if (isCompleted(job)) {
          dirtyConfig = false;
          jobs.config = { job, applied: true };
          notifyState();
        }
        return job;
      } finally {
        endBusy();
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
          dirtyConfig = false;
          dirtyTrigger = false;
          jobs.config = null;
          jobs.trigger = null;
          syncSelectedProtocol();
          notifyState();
          await readDisplayAndConfig();
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
        endBusy();
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
        endBusy();
      }
    },
    exportLister: async function exportLister(output) {
      if (busyCount > 0 || !available()) return null;
      const filename = typeof output === "string" ? output.trim() : "";
      if (!filename) return null;
      beginBusy();
      try {
        return await execute(
          "serial-lister-export",
          { output: filename },
          {},
        );
      } finally {
        endBusy();
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

export class SerialEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.controller = createSerialEditorController({
      execute: (command, parameters, options) => hooks.executeCommand(command, parameters, options),
      confirmDiscard: () => window.confirm(translate("serial.editor.discardConfirm")),
      available: () => hooks.isAvailable() && !hooks.isExecutionBusy?.(),
    });
    this.controller.onStateChange((stateSnapshot) => this.render(stateSnapshot));
    this.syncedJobs = {
      display: null,
      config: null,
      trigger: null,
      listerDisplay: null,
      listerReference: null,
    };
    this.renderedBusLimit = null;
    this.renderedProtocols = null;
    this.renderedConfigCommand = undefined;
    this.renderedTriggerCommand = undefined;
    this.renderedFormEpoch = null;
    this.renderedListerEpoch = null;
    this.buildDom();
  }

  rebuildForms() {
    this.displayFormContainer.replaceChildren();
    this.displayForm = new CommandForm(this.displayFormContainer, this.catalog);
    this.displayFormReady = false;
    this.clearConfigForm();
    this.clearTriggerForm();
    this.syncedJobs.display = null;
  }

  buildDom() {
    this.refreshButton?.remove?.();
    this.container.replaceChildren();

    this.busSelect = document.createElement("select");
    this.busSelect.addEventListener("change", () => {
      this.controller.selectBus(this.busSelect.value);
    });

    this.currentValue = document.createElement("output");
    this.currentValue.className = "readonly-value serial-editor-current-value";

    this.protocolSelect = document.createElement("select");
    this.protocolSelect.addEventListener("change", () => {
      this.controller.selectProtocol(this.protocolSelect.value);
    });

    this.applyModeButton = document.createElement("button");
    this.applyModeButton.type = "button";
    this.applyModeButton.className = "primary serial-editor-action";
    this.applyModeButton.textContent = translate("serial.editor.applyMode");
    this.applyModeButton.addEventListener("click", () => {
      void this.controller.applyMode();
    });

    const topRow = document.createElement("div");
    topRow.className = "serial-editor-row";
    topRow.append(
      this.labeledField("serial.editor.bus", this.busSelect),
      this.labeledField("serial.editor.currentProtocol", this.currentValue),
      this.labeledField("serial.editor.protocol", this.protocolSelect),
      this.applyModeButton,
    );

    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary serial-editor-refresh";
    this.refreshButton.textContent = translate("serial.editor.refresh");
    this.refreshButton.addEventListener("click", () => {
      this.controller.scheduleRefresh();
    });
    if (this.hooks.headerActions) {
      this.refreshButton.hidden = true;
      this.hooks.headerActions.append(this.refreshButton);
    }

    this.displayFormContainer = document.createElement("div");
    this.applyDisplayButton = document.createElement("button");
    this.applyDisplayButton.type = "button";
    this.applyDisplayButton.className = "secondary serial-editor-action";
    this.applyDisplayButton.textContent = translate("serial.editor.applyDisplay");
    this.applyDisplayButton.addEventListener("click", () => {
      void this.submitDisplay();
    });
    const displaySection = this.section(
      "serial.editor.displaySection",
      this.displayFormContainer,
      this.applyDisplayButton,
    );

    this.configNote = document.createElement("p");
    this.configNote.className = "muted compact-note";
    this.configFormContainer = document.createElement("div");
    this.applyConfigButton = document.createElement("button");
    this.applyConfigButton.type = "button";
    this.applyConfigButton.className = "secondary serial-editor-action";
    this.applyConfigButton.textContent = translate("serial.editor.applyConfiguration");
    this.applyConfigButton.addEventListener("click", () => {
      void this.submitConfig();
    });
    const configSection = this.section(
      "serial.editor.configuration",
      [this.configNote, this.configFormContainer],
      this.applyConfigButton,
    );

    this.triggerFormContainer = document.createElement("div");
    this.applyTriggerButton = this.actionButton(
      translate("serial.editor.applyTrigger"),
      () => void this.submitTrigger(),
    );
    this.triggerSection = this.section(
      "serial.editor.triggerSection",
      this.triggerFormContainer,
      this.applyTriggerButton,
    );

    const listerSection = this.buildListerSection();

    this.container.append(
      topRow,
      ...(this.hooks.headerActions ? [] : [this.refreshButton]),
      displaySection,
      configSection,
      this.triggerSection,
      listerSection,
    );
    this.displayForm = new CommandForm(this.displayFormContainer, this.catalog);
  }

  actionButton(labelText, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary serial-editor-action";
    button.textContent = labelText;
    button.addEventListener("click", onClick);
    return button;
  }

  buildListerSection() {
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
    return root;
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
    root.append(actionButton);
    return root;
  }

  editorDefinition(commandId) {
    return editorSubDefinition(this.catalog, commandId);
  }

  ensureDisplayForm() {
    if (this.displayFormReady) return;
    const definition = this.editorDefinition("serial-display");
    if (!definition) return;
    this.displayForm.render(definition, {
      onDirty: () => this.controller.setDirty("display", this.displayForm.isDirty()),
    });
    this.displayFormReady = true;
  }

  ensureConfigForm(commandId) {
    if (this.renderedConfigCommand === commandId) return;
    this.renderedConfigCommand = commandId;
    this.configFormContainer.replaceChildren();
    this.configForm = new CommandForm(this.configFormContainer, this.catalog);
    const definition = this.editorDefinition(commandId);
    if (!definition) return;
    this.configForm.render(definition, {
      onDirty: () => this.controller.setDirty("config", this.configForm.isDirty()),
    });
  }

  clearConfigForm() {
    this.renderedConfigCommand = null;
    this.configFormContainer.replaceChildren();
    this.configForm = null;
    this.syncedJobs.config = null;
  }

  ensureTriggerForm(commandId) {
    if (this.renderedTriggerCommand === commandId) return;
    this.renderedTriggerCommand = commandId;
    this.triggerFormContainer.replaceChildren();
    this.triggerForm = new CommandForm(this.triggerFormContainer, this.catalog);
    const definition = this.editorDefinition(commandId);
    if (!definition) return;
    this.triggerForm.render(definition, {
      onDirty: () => this.controller.setDirty("trigger", this.triggerForm.isDirty()),
    });
  }

  clearTriggerForm() {
    this.renderedTriggerCommand = null;
    this.triggerFormContainer?.replaceChildren();
    this.triggerForm = null;
    this.syncedJobs.trigger = null;
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

  async submitDisplay() {
    if (!this.displayForm || this.controller.state.busy || this.hooks.isExecutionBusy?.()) return;
    const values = this.displayForm.values();
    if (values === null) return;
    delete values.action;
    if (!Object.keys(values).length) return;
    await this.controller.applyDisplay(values);
  }

  async submitConfig() {
    if (!this.configForm || this.controller.state.busy || this.hooks.isExecutionBusy?.()) return;
    const values = this.configForm.values();
    if (values === null) return;
    delete values.action;
    if (!Object.keys(values).length) return;
    await this.controller.applyConfig(values);
  }

  async submitTrigger() {
    if (!this.triggerForm || this.controller.state.busy || this.hooks.isExecutionBusy?.()) return;
    const values = this.triggerForm.values();
    if (values === null) return;
    delete values.action;
    if (!Object.keys(values).length) return;
    await this.controller.applyTrigger(values);
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
    await this.controller.exportLister(values.output);
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

  renderOptions(select, options, selectedValue) {
    select.replaceChildren();
    options.forEach((option) => {
      select.append(new Option(option.label, option.value));
    });
    if (selectedValue !== null && selectedValue !== undefined) {
      select.value = String(selectedValue);
    }
  }

  scheduleRefresh(force = false) {
    const changed = this.schedulePresentation();
    if (!force && !changed) return;
    const info = this.hooks.modelInfo();
    if (info.supported && !this.hooks.isExecutionBusy?.()) this.controller.scheduleRefresh();
  }

  schedulePresentation() {
    const key = `${this.hooks.contextKey()}|${this.hooks.isAvailable()}`;
    if (key === this.lastAvailabilityKey) return false;
    this.lastAvailabilityKey = key;
    const info = this.hooks.modelInfo();
    this.controller.reset({
      maxBus: info.supported ? info.maxBus : 0,
      protocolChoices: info.protocols,
    });
    return true;
  }

  rerender() {
    this.renderedBusLimit = null;
    this.renderedProtocols = null;
    this.render(this.controller.state);
  }

  render(stateSnapshot) {
    const unavailable = !this.hooks.isAvailable();
    const disabled = stateSnapshot.busy || this.hooks.isExecutionBusy?.() || unavailable;

    if (this.renderedFormEpoch !== stateSnapshot.formEpoch) {
      this.renderedFormEpoch = stateSnapshot.formEpoch;
      this.rebuildForms();
    }
    if (this.renderedListerEpoch !== stateSnapshot.listerEpoch) {
      this.renderedListerEpoch = stateSnapshot.listerEpoch;
      this.rebuildListerForms();
    }

    this.container.querySelectorAll("[data-i18n-key]").forEach((node) => {
      node.textContent = translate(node.dataset.i18nKey);
    });
    this.applyModeButton.textContent = translate("serial.editor.applyMode");
    this.refreshButton.textContent = translate("serial.editor.refresh");
    this.applyDisplayButton.textContent = translate("serial.editor.applyDisplay");
    this.applyConfigButton.textContent = translate("serial.editor.applyConfiguration");
    this.applyTriggerButton.textContent = translate("serial.editor.applyTrigger");
    this.applyListerDisplayButton.textContent = translate("actions.apply");
    this.applyListerReferenceButton.textContent = translate("actions.apply");
    this.exportButton.textContent = translate("serial.editor.export");

    if (this.renderedBusLimit !== stateSnapshot.maxBus) {
      this.renderedBusLimit = stateSnapshot.maxBus;
      this.renderOptions(
        this.busSelect,
        busOptions(stateSnapshot.maxBus).map((value) => ({
          value: String(value),
          label: translate("serial.editor.busOption", { bus: value }),
        })),
        stateSnapshot.bus,
      );
    }
    this.busSelect.disabled = disabled;
    this.busSelect.value = String(stateSnapshot.bus);

    if (
      this.renderedProtocols?.join("|") !== stateSnapshot.protocols.join("|")
    ) {
      this.renderedProtocols = [...stateSnapshot.protocols];
      this.renderOptions(
        this.protocolSelect,
        stateSnapshot.protocols.map((protocol) => ({
          value: protocol,
          label: protocol.toUpperCase(),
        })),
        stateSnapshot.selectedProtocol,
      );
    }
    this.protocolSelect.value = String(stateSnapshot.selectedProtocol);
    this.protocolSelect.disabled = disabled;

    this.currentValue.textContent = stateSnapshot.currentLabel || "-";

    this.applyModeButton.disabled =
      disabled
      || !stateSnapshot.selectedProtocol
      || stateSnapshot.selectedProtocol === stateSnapshot.confirmedMode;
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
      this.clearConfigForm();
    } else if (stateSnapshot.supported) {
      this.configNote.hidden = true;
      this.ensureConfigForm(stateSnapshot.configCommand);
      this.configForm?.setDisabled(disabled);
    } else {
      this.configNote.hidden = true;
      this.clearConfigForm();
    }

    this.applyDisplayButton.disabled = disabled;
    this.applyConfigButton.disabled = disabled || !stateSnapshot.supported;
    this.applyTriggerButton.disabled = disabled || !stateSnapshot.supported;
    this.applyListerDisplayButton.disabled = disabled;
    this.applyListerReferenceButton.disabled = disabled;
    this.exportButton.disabled = disabled;

    this.syncFormSlot(this.displayForm, "display", stateSnapshot.jobs);
    if (!showUnsupported) {
      this.syncFormSlot(this.configForm, "config", stateSnapshot.jobs);
    }
    if (stateSnapshot.supported) {
      this.triggerSection.hidden = false;
      this.ensureTriggerForm(stateSnapshot.triggerCommand);
      this.triggerForm?.setDisabled(disabled);
      this.syncFormSlot(this.triggerForm, "trigger", stateSnapshot.jobs);
    } else {
      this.triggerSection.hidden = true;
      this.clearTriggerForm();
    }

    this.listerDisplayForm?.setDisabled(disabled);
    this.listerReferenceForm?.setDisabled(disabled);
    this.exportForm?.setDisabled(disabled);
    this.syncFormSlot(this.listerDisplayForm, "listerDisplay", stateSnapshot.jobs);
    this.syncFormSlot(this.listerReferenceForm, "listerReference", stateSnapshot.jobs);
  }
}
