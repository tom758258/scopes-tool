import { hasTranslation, translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

export const SERIAL_EDITOR_COMMANDS = Object.freeze([
  "serial-mode",
  "serial-display",
  "serial-uart",
  "serial-i2c",
  "serial-spi",
  "serial-can",
]);

const EDITOR_PROTOCOLS = ["uart", "i2c", "spi", "can"];

export function configCommandFor(mode) {
  return EDITOR_PROTOCOLS.includes(mode) ? `serial-${mode}` : null;
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
  let busyCount = 0;
  let refreshQueued = false;
  let formEpoch = 0;
  const jobs = { mode: null, display: null, config: null };

  const state = () => ({
    bus,
    maxBus,
    protocols: [...protocols],
    selectedProtocol,
    confirmedMode,
    rawMode,
    currentLabel: displayModeLabel(confirmedMode, rawMode),
    configCommand: configCommandFor(confirmedMode),
    supported: configCommandFor(confirmedMode) !== null,
    dirtyConfig,
    dirtyDisplay,
    busy: busyCount > 0,
    formEpoch,
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

  async function readDisplayAndConfig() {
    const displayJob = await runQuery("serial-display", { action: "query", bus });
    jobs.display = displayJob ? { job: displayJob, applied: false } : null;
    notifyState();
    const configCommand = configCommandFor(confirmedMode);
    if (configCommand) {
      const configJob = await runQuery(configCommand, { action: "query", bus });
      jobs.config = configJob ? { job: configJob, applied: false } : null;
    } else {
      jobs.config = null;
    }
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
      jobs.mode = null;
      jobs.display = null;
      jobs.config = null;
      formEpoch += 1;
      notifyState();
    },
    scheduleRefresh() {
      scheduleRefresh();
    },
    selectBus(nextBus) {
      const candidate = Number(nextBus);
      if (busyCount > 0 || candidate === bus) return;
      if (!busOptions(maxBus).includes(candidate)) return;
      if ((dirtyConfig || dirtyDisplay) && !confirmDiscard()) {
        notifyState();
        return;
      }
      bus = candidate;
      confirmedMode = null;
      rawMode = null;
      dirtyConfig = false;
      dirtyDisplay = false;
      jobs.mode = null;
      jobs.display = null;
      jobs.config = null;
      formEpoch += 1;
      notifyState();
      scheduleRefresh();
    },
    selectProtocol(protocol) {
      if (busyCount > 0 || !protocols.includes(protocol)) return;
      selectedProtocol = protocol;
      notifyState();
    },
    setDirty(kind, value) {
      if (kind === "config") dirtyConfig = Boolean(value);
      if (kind === "display") dirtyDisplay = Boolean(value);
      notifyState();
    },
    isDirty() {
      return dirtyConfig || dirtyDisplay;
    },
    applyMode: async function applyMode() {
      if (busyCount > 0 || !available() || !selectedProtocol) return null;
      if (selectedProtocol === confirmedMode) return null;
      if (dirtyConfig && !confirmDiscard()) return null;
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
            jobs.config = null;
            jobs.mode = { job, applied: true };
            notifyState();
            const configJob = await runQuery(`serial-${target}`, { action: "query", bus });
            jobs.config = configJob ? { job: configJob, applied: false } : null;
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
        const reported = modeFromJob(modeJob);
        if (reported.mode !== confirmedMode) {
          confirmedMode = reported.mode;
          rawMode = reported.rawMode;
          dirtyConfig = false;
          jobs.config = null;
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
      available: () => hooks.isAvailable(),
    });
    this.controller.onStateChange((stateSnapshot) => this.render(stateSnapshot));
    this.syncedJobs = { display: null, config: null };
    this.renderedBusLimit = null;
    this.renderedProtocols = null;
    this.renderedConfigCommand = undefined;
    this.renderedFormEpoch = null;
    this.buildDom();
  }

  rebuildForms() {
    this.displayFormContainer.replaceChildren();
    this.displayForm = new CommandForm(this.displayFormContainer, this.catalog);
    this.displayFormReady = false;
    this.clearConfigForm();
    this.syncedJobs.display = null;
  }

  buildDom() {
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

    this.container.append(topRow, this.refreshButton, displaySection, configSection);
    this.displayForm = new CommandForm(this.displayFormContainer, this.catalog);
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

  async submitDisplay() {
    if (!this.displayForm || this.controller.state.busy) return;
    const values = this.displayForm.values();
    if (values === null) return;
    delete values.action;
    if (!Object.keys(values).length) return;
    await this.controller.applyDisplay(values);
  }

  async submitConfig() {
    if (!this.configForm || this.controller.state.busy) return;
    const values = this.configForm.values();
    if (values === null) return;
    delete values.action;
    if (!Object.keys(values).length) return;
    await this.controller.applyConfig(values);
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

  scheduleRefresh() {
    const key = `${this.hooks.contextKey()}|${this.hooks.isAvailable()}`;
    if (key === this.lastAvailabilityKey) return;
    this.lastAvailabilityKey = key;
    const info = this.hooks.modelInfo();
    this.controller.reset({
      maxBus: info.supported ? info.maxBus : 0,
      protocolChoices: info.protocols,
    });
    if (info.supported) this.controller.scheduleRefresh();
  }

  rerender() {
    this.renderedBusLimit = null;
    this.renderedProtocols = null;
    this.render(this.controller.state);
  }

  render(stateSnapshot) {
    const unavailable = !this.hooks.isAvailable();
    const disabled = stateSnapshot.busy || unavailable;

    if (this.renderedFormEpoch !== stateSnapshot.formEpoch) {
      this.renderedFormEpoch = stateSnapshot.formEpoch;
      this.rebuildForms();
    }

    this.container.querySelectorAll("[data-i18n-key]").forEach((node) => {
      node.textContent = translate(node.dataset.i18nKey);
    });
    this.applyModeButton.textContent = translate("serial.editor.applyMode");
    this.refreshButton.textContent = translate("serial.editor.refresh");
    this.applyDisplayButton.textContent = translate("serial.editor.applyDisplay");
    this.applyConfigButton.textContent = translate("serial.editor.applyConfiguration");

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

    this.syncFormSlot(this.displayForm, "display", stateSnapshot.jobs);
    if (!showUnsupported) {
      this.syncFormSlot(this.configForm, "config", stateSnapshot.jobs);
    }
  }
}
