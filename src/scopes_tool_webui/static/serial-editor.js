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

function availableBusOptions(maxBus) {
  const limit = Math.floor(Number(maxBus) || 0);
  return limit > 0 ? busOptions(limit) : [];
}

export function displayModeLabel(mode, rawMode) {
  if (mode) return String(mode).toUpperCase();
  return rawMode ? String(rawMode) : null;
}

function normalizedListerDisplay(value) {
  const normalized = String(value ?? "").toLowerCase();
  return ["off", "bus1", "bus2", "all"].includes(normalized) ? normalized : null;
}

function listerDisplayFromJob(job) {
  const result = job?.result?.result || {};
  return normalizedListerDisplay(result.lister?.display ?? result.display?.display);
}

function serialDisplayFromJob(job) {
  const enabled = job?.result?.result?.display?.enabled;
  return typeof enabled === "boolean" ? enabled : null;
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
  let decodeModeReady = false;
  let decodeDisplayReady = false;
  let decodeConfigReady = false;
  let triggerModeReady = false;
  let triggerConfigReady = false;
  let dirtyConfig = false;
  let dirtyDisplay = false;
  let dirtyTrigger = false;
  let dirtyListerDisplay = false;
  let dirtyListerReference = false;
  let busyCount = 0;
  let formEpoch = 0;
  let listerEpoch = 0;
  let listerDisplay = null;
  let decodeDisplayByBus = {};
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
    decodeModeReady,
    decodeDisplayReady,
    decodeConfigReady,
    triggerModeReady,
    triggerConfigReady,
    currentLabel: displayModeLabel(confirmedMode, rawMode),
    configCommand: configCommandFor(confirmedMode),
    triggerCommand: triggerCommandFor(confirmedMode),
    supported: configCommandFor(confirmedMode) !== null,
    dirtyConfig,
    dirtyDisplay,
    dirtyTrigger,
    dirtyListerDisplay,
    dirtyListerReference,
    listerDisplay,
    decodeDisplayByBus: { ...decodeDisplayByBus },
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

  async function runQuery(command, parameters, options = {}) {
    const job = await execute(command, parameters, { intent: "readback", ...options });
    return isCompleted(job) ? job : null;
  }

  async function readConfigForConfirmed() {
    jobs.config = null;
    decodeConfigReady = false;
    const configCommand = configCommandFor(confirmedMode);
    if (!configCommand) {
      notifyState();
      return;
    }
    const configJob = await runQuery(configCommand, { action: "query", bus });
    jobs.config = configJob ? { job: configJob, applied: false, protocol: confirmedMode } : null;
    decodeConfigReady = Boolean(configJob);
    notifyState();
  }

  async function readDecode() {
    decodeModeReady = false;
    decodeDisplayReady = false;
    decodeConfigReady = false;
    const modeJob = await runQuery("serial-mode", { action: "query", bus });
    jobs.mode = modeJob ? { job: modeJob, applied: false } : null;
    decodeModeReady = Boolean(modeJob);
    const reported = modeFromJob(modeJob);
    if (modeJob) {
      const modeChanged = confirmedMode !== null && confirmedMode !== reported.mode;
      confirmedMode = reported.mode;
      rawMode = reported.rawMode;
      if (modeChanged) {
        triggerModeReady = false;
        triggerConfigReady = false;
        jobs.trigger = null;
      }
      if (!protocolPending || !dirtyConfig) {
        protocolPending = false;
        syncSelectedProtocol();
      }
    }
    notifyState();
    const displayJob = await runQuery("serial-display", { action: "query", bus });
    jobs.display = displayJob ? { job: displayJob, applied: false } : null;
    decodeDisplayReady = Boolean(displayJob);
    notifyState();
    if (modeJob) await readConfigForConfirmed();
  }

  async function readTriggerForConfirmed() {
    jobs.trigger = null;
    triggerConfigReady = false;
    const triggerCommand = triggerCommandFor(confirmedMode);
    if (!triggerCommand) {
      notifyState();
      return;
    }
    const triggerJob = await runQuery(triggerCommand, { action: "query", bus });
    jobs.trigger = triggerJob ? { job: triggerJob, applied: false } : null;
    triggerConfigReady = Boolean(triggerJob);
    notifyState();
  }

  async function readTrigger() {
    triggerModeReady = false;
    triggerConfigReady = false;
    const modeJob = await runQuery("serial-mode", { action: "query", bus });
    jobs.mode = modeJob ? { job: modeJob, applied: false } : null;
    triggerModeReady = Boolean(modeJob);
    const reported = modeFromJob(modeJob);
    if (modeJob) {
      const modeChanged = confirmedMode !== null && confirmedMode !== reported.mode;
      confirmedMode = reported.mode;
      rawMode = reported.rawMode;
      if (modeChanged) {
        decodeModeReady = false;
        decodeConfigReady = false;
        jobs.config = null;
      }
    }
    notifyState();
    if (modeJob) await readTriggerForConfirmed();
  }

  async function readListerState() {
    const listerJob = await runQuery("serial-lister-query", {});
    if (listerJob) {
      const entry = { job: listerJob, applied: false };
      const reportedDisplay = listerDisplayFromJob(listerJob);
      if (reportedDisplay) listerDisplay = reportedDisplay;
      jobs.listerDisplay = entry;
      jobs.listerReference = entry;
    }
    notifyState();

    for (const prerequisiteBus of availableBusOptions(maxBus)) {
      const displayJob = await runQuery("serial-display", {
        action: "query",
        bus: prerequisiteBus,
      }, { captureWorkspaceResult: false });
      decodeDisplayByBus[prerequisiteBus] = displayJob
        ? (serialDisplayFromJob(displayJob) ?? "unknown")
        : "unknown";
      notifyState();
    }
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
    decodeModeReady = true;
    triggerModeReady = false;
    triggerConfigReady = false;
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
      decodeModeReady = false;
      decodeDisplayReady = false;
      decodeConfigReady = false;
      triggerModeReady = false;
      triggerConfigReady = false;
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
      listerDisplay = null;
      decodeDisplayByBus = Object.fromEntries(
        availableBusOptions(maxBus).map((availableBus) => [availableBus, "unknown"]),
      );
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
      decodeModeReady = false;
      decodeDisplayReady = false;
      decodeConfigReady = false;
      triggerModeReady = false;
      triggerConfigReady = false;
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
      if (busyCount > 0 || !decodeModeReady || !protocols.includes(protocol)) return;
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
          decodeDisplayReady = true;
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
            decodeModeReady = true;
            decodeConfigReady = false;
            triggerModeReady = false;
            triggerConfigReady = false;
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
          decodeConfigReady = true;
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
          triggerModeReady = true;
          triggerConfigReady = false;
          decodeModeReady = false;
          decodeConfigReady = false;
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
          triggerConfigReady = true;
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
          if (kind === "display") {
            listerDisplay = listerDisplayFromJob(job)
              || normalizedListerDisplay(payload.display)
              || listerDisplay;
          }
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

  labeledField(labelKey, input, helpKey = null) {
    const wrapper = document.createElement("label");
    wrapper.className = "field serial-editor-field";
    const label = document.createElement("span");
    label.dataset.i18nKey = labelKey;
    label.textContent = translate(labelKey);
    wrapper.append(label, input);
    if (helpKey) {
      const help = document.createElement("small");
      help.className = "field-help";
      help.dataset.i18nKey = helpKey;
      help.textContent = translate(helpKey);
      wrapper.append(help);
    }
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

  actionButton(labelText, onClick, primary = false) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `${primary ? "primary" : "secondary"} serial-editor-action`;
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
    topRow.className = "command-form";
    topRow.append(
      this.labeledField("serial.editor.bus", this.busSelect, "serial.editor.busHelp"),
      this.labeledField("serial.decode.currentProtocol", this.currentValue, "serial.decode.currentProtocolHelp"),
      this.labeledField("serial.decode.protocolToApply", this.protocolSelect, "serial.decode.protocolHelp"),
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
    this.pendingProtocolNote = document.createElement("p");
    this.pendingProtocolNote.className = "muted compact-note";
    this.pendingProtocolNote.hidden = true;
    this.readbackHint = document.createElement("small");
    this.readbackHint.className = "field-help";
    this.readbackHint.dataset.i18nKey = "serial.decode.readbackHint";
    this.readbackHint.textContent = translate("serial.decode.readbackHint");
    this.configDescription = document.createElement("p");
    this.configDescription.className = "muted compact-note";
    this.configUnreadPresentation = document.createElement("p");
    this.configUnreadPresentation.className = "muted compact-note serial-editor-unread-config";
    this.configUnreadPresentation.dataset.state = "unread";
    this.configUnreadPresentation.dataset.i18nKey = "serial.decode.unreadConfiguration";
    this.configUnreadPresentation.textContent = translate("serial.decode.unreadConfiguration");
    this.configFormContainer = document.createElement("div");
    this.configFormContainer.className = "command-form";
    this.applyDecodeButton = this.actionButton(
      translate("serial.decode.applySettings"),
      () => void this.submitDecode(),
      true,
    );
    if (this.hooks.headerActions) {
      this.applyDecodeButton.hidden = true;
      this.hooks.headerActions.append(this.applyDecodeButton);
    }
    this.configSection = this.section(
      "serial.editor.configuration",
      [
        this.configNote,
        this.pendingProtocolNote,
        this.readbackHint,
        this.configDescription,
        this.configUnreadPresentation,
        this.configFormContainer,
      ],
      this.hooks.headerActions ? null : this.applyDecodeButton,
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
    this.configDescription.textContent = "";
    this.configDescription.hidden = true;
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
    this.displayForm?.refreshLocale();
    this.configForm?.refreshLocale();
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
    this.protocolSelect.disabled = disabled || !stateSnapshot.decodeModeReady;

    this.currentValue.textContent = stateSnapshot.currentLabel || "-";

    this.refreshButton.disabled = disabled;

    this.ensureDisplayForm();
    this.displayForm?.setDisabled(disabled || !stateSnapshot.decodeDisplayReady);

    const showUnsupported = !unavailable
      && stateSnapshot.decodeModeReady
      && !stateSnapshot.supported;
    if (showUnsupported) {
      const protocolName = stateSnapshot.currentLabel || "-";
      this.configNote.hidden = false;
      this.configNote.textContent = hasTranslation("serial.editor.unsupported")
        ? translate("serial.editor.unsupported", { protocol: protocolName })
        : protocolName;
    } else {
      this.configNote.hidden = true;
    }
    const hasPendingProtocol = Boolean(
      stateSnapshot.protocolPending
      && stateSnapshot.selectedProtocol
      && stateSnapshot.selectedProtocol !== stateSnapshot.confirmedMode
    );
    this.pendingProtocolNote.hidden = !hasPendingProtocol;
    if (hasPendingProtocol) {
      this.pendingProtocolNote.textContent = translate("serial.decode.pendingProtocol", {
        pending: String(stateSnapshot.selectedProtocol).toUpperCase(),
        current: stateSnapshot.currentLabel || "-",
      });
    }

    const previewProtocol = stateSnapshot.selectedProtocol
      || (stateSnapshot.protocols.includes(stateSnapshot.confirmedMode)
        ? stateSnapshot.confirmedMode
        : stateSnapshot.protocols[0]);
    this.ensureDecodeConfigForm(previewProtocol);
    this.configUnreadPresentation.hidden = unavailable
      || stateSnapshot.decodeConfigReady
      || stateSnapshot.protocolPending
      || showUnsupported;
    const configEditable = stateSnapshot.decodeModeReady
      && (stateSnapshot.protocolPending || stateSnapshot.decodeConfigReady);
    this.configForm?.setDisabled(disabled || !configEditable);

    this.applyDecodeButton.disabled = disabled
      || !stateSnapshot.decodeModeReady
      || (!stateSnapshot.decodeDisplayReady
        && !(stateSnapshot.selectedProtocol && configEditable));

    this.syncFormSlot(this.displayForm, "display", stateSnapshot.jobs);
    if (!showUnsupported && previewProtocol === stateSnapshot.selectedProtocol) {
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
      this.labeledField("serial.editor.bus", this.busSelect, "serial.editor.busHelp"),
      this.labeledField("serial.trigger.currentProtocol", this.currentValue, "serial.trigger.currentProtocolHelp"),
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
      true,
    );
    if (this.hooks.headerActions) {
      this.applyTriggerButton.hidden = true;
      this.hooks.headerActions.append(this.applyTriggerButton);
    }
    this.triggerSection = this.section(
      "serial.editor.triggerSection",
      [this.triggerNote, this.triggerDescription, this.triggerFormContainer],
      this.hooks.headerActions ? null : this.applyTriggerButton,
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
    if (!definition) {
      this.triggerDescription.textContent = "";
      this.triggerDescription.hidden = true;
      return;
    }
    this.triggerDescription.textContent = this.catalog.description?.(definition) || "";
    this.triggerDescription.hidden = !this.triggerDescription.textContent;
    this.triggerForm.render(definition, {
      onDirty: (fieldName) => {
        this.controller.setDirty("trigger", this.triggerForm.isDirty());
        if (fieldName === "type") this.syncI2cTriggerAddressMaximum();
      },
    });
  }

  syncI2cTriggerAddressMaximum() {
    const form = this.triggerForm;
    if (!form || form.command?.id !== "serial-trigger-i2c") return;
    const fields = form.catalog?.fieldsFor
      ? form.catalog.fieldsFor(form.command)
      : form.command.fields;
    const addressField = (fields || []).find((field) => field.name === "address");
    if (!addressField) return;
    const typeInput = form.container.querySelector('[data-field="type"]');
    const addressInput = form.container.querySelector('[data-field="address"]');
    if (!typeInput || !addressInput) return;
    const maximumByType = addressField.maximum_by_type || {};
    const maximum = Object.prototype.hasOwnProperty.call(maximumByType, typeInput.value)
      ? maximumByType[typeInput.value]
      : addressField.maximum;
    if (maximum === undefined || maximum === null) return;
    addressInput.max = String(maximum);
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
    this.triggerForm?.refreshLocale();
    this.applyTriggerButton.textContent = translate("serial.editor.applyTrigger");
    this.refreshButton.textContent = translate("serial.trigger.readSettings");

    this.syncBusSelect(this.busSelect, stateSnapshot, disabled);
    this.currentValue.textContent = stateSnapshot.currentLabel || "-";
    this.refreshButton.disabled = disabled;

    const showUnsupported = !unavailable
      && stateSnapshot.triggerModeReady
      && !stateSnapshot.supported;
    this.triggerSection.hidden = unavailable;
    if (showUnsupported) {
      const protocolName = stateSnapshot.currentLabel || "-";
      this.triggerNote.hidden = false;
      this.triggerNote.textContent = hasTranslation("serial.editor.unsupported")
        ? translate("serial.editor.unsupported", { protocol: protocolName })
        : protocolName;
      const previewProtocol = stateSnapshot.protocols.includes(stateSnapshot.confirmedMode)
        ? stateSnapshot.confirmedMode
        : (stateSnapshot.selectedProtocol || stateSnapshot.protocols[0]);
      this.ensureTriggerForm(triggerCommandFor(previewProtocol));
      this.triggerForm?.setDisabled(true);
    } else {
      const hasReadbackForm = stateSnapshot.triggerModeReady
        && stateSnapshot.triggerConfigReady
        && stateSnapshot.supported;
      this.triggerNote.hidden = hasReadbackForm;
      this.triggerNote.textContent = unavailable
        ? translate("serial.editor.unavailable")
        : translate("serial.trigger.unreadConfiguration");
      const previewProtocol = hasReadbackForm
        ? stateSnapshot.confirmedMode
        : (stateSnapshot.selectedProtocol
          || (stateSnapshot.protocols.includes(stateSnapshot.confirmedMode)
            ? stateSnapshot.confirmedMode
            : stateSnapshot.protocols[0]));
      this.ensureTriggerForm(triggerCommandFor(previewProtocol));
      this.triggerForm?.setDisabled(disabled || !hasReadbackForm);
      if (hasReadbackForm) this.syncFormSlot(this.triggerForm, "trigger", stateSnapshot.jobs);
    }

    this.syncI2cTriggerAddressMaximum();

    this.applyTriggerButton.disabled = disabled
      || !stateSnapshot.triggerModeReady
      || !stateSnapshot.triggerConfigReady
      || !stateSnapshot.supported;
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
    this.usageNote = document.createElement("p");
    this.usageNote.className = "muted compact-note";
    this.usageNote.dataset.i18nKey = "serial.lister.usage";
    this.usageNote.textContent = translate("serial.lister.usage");
    root.append(this.usageNote);
    this.prerequisiteNote = document.createElement("p");
    this.prerequisiteNote.className = "compact-note serial-lister-prerequisite";
    root.append(this.prerequisiteNote);
    this.pcOutputNote = document.createElement("p");
    this.pcOutputNote.className = "compact-note pc-output-command-note pc-output-note-box";
    this.hooks.renderPcOutputNote?.(this.pcOutputNote);

    const addRow = (container, button, notes = []) => {
      const row = document.createElement("div");
      row.className = "serial-editor-row serial-lister-row";
      row.append(container, ...notes, button);
      root.append(row);
      return row;
    };

    this.listerDisplayFormContainer = document.createElement("div");
    this.listerDisplayFormContainer.className = "command-form";
    this.applyListerDisplayButton = this.actionButton(
      translate("actions.apply"),
      () => void this.submitListerSetting("display"),
      true,
    );
    this.listerDisplayRow = addRow(
      this.listerDisplayFormContainer,
      this.applyListerDisplayButton,
    );

    this.listerReferenceFormContainer = document.createElement("div");
    this.listerReferenceFormContainer.className = "command-form";
    this.applyListerReferenceButton = this.actionButton(
      translate("actions.apply"),
      () => void this.submitListerSetting("reference"),
      true,
    );
    this.listerReferenceRow = addRow(
      this.listerReferenceFormContainer,
      this.applyListerReferenceButton,
    );

    this.exportFormContainer = document.createElement("div");
    this.exportFormContainer.className = "command-form";
    this.exportButton = this.actionButton(
      translate("serial.editor.export"),
      () => void this.submitExport(),
      true,
    );
    this.exportRow = addRow(
      this.exportFormContainer,
      this.exportButton,
      [this.pcOutputNote],
    );

    this.listerDisplayForm = new CommandForm(this.listerDisplayFormContainer, this.catalog);
    this.listerReferenceForm = new CommandForm(this.listerReferenceFormContainer, this.catalog);
    this.exportForm = new CommandForm(this.exportFormContainer, this.catalog);

    this.container.append(
      ...(this.hooks.headerActions ? [] : [this.refreshButton]),
      root,
    );
  }

  refreshPcOutputNote() {
    this.hooks.renderPcOutputNote?.(this.pcOutputNote);
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
  }

  syncListerDisplayOptions(stateSnapshot) {
    const select = this.listerDisplayFormContainer.querySelector?.('[data-field="display"]');
    if (!select?.options) return;
    const availableBuses = availableBusOptions(stateSnapshot.maxBus);
    const hasUsableBus = availableBuses.some(
      (availableBus) => stateSnapshot.decodeDisplayByBus?.[availableBus] === true,
    );
    for (const option of select.options) {
      const busForOption = option.value?.startsWith("bus")
        ? Number(option.value.slice(3))
        : null;
      if (busForOption !== null) {
        option.disabled = !availableBuses.includes(busForOption)
          || stateSnapshot.decodeDisplayByBus?.[busForOption] !== true;
      } else if (option.value === "all") {
        option.disabled = !hasUsableBus;
      }
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
    this.listerDisplayForm?.refreshLocale();
    this.listerReferenceForm?.refreshLocale();
    this.exportForm?.refreshLocale();
    this.refreshPcOutputNote();
    this.applyListerDisplayButton.textContent = translate("actions.apply");
    this.applyListerReferenceButton.textContent = translate("actions.apply");
    this.exportButton.textContent = translate("serial.editor.export");
    this.refreshButton.textContent = translate("serial.lister.readSettings");
    this.refreshButton.disabled = disabled;

    const hasListerReadback = stateSnapshot.listerDisplay !== null;
    const target = stateSnapshot.listerDisplay;
    const busForTarget = target?.startsWith("bus") ? Number(target.slice(3)) : null;
    const availableBuses = availableBusOptions(stateSnapshot.maxBus);
    const busStates = availableBuses.map((availableBus) => (
      stateSnapshot.decodeDisplayByBus?.[availableBus] ?? "unknown"
    ));
    const hasUsableBus = busStates.some((value) => value === true);
    const allKnownOff = busStates.length > 0 && busStates.every((value) => value === false);
    let prerequisiteEnabled = false;
    let prerequisiteKey = "serial.lister.unreadPrerequisite";
    let prerequisiteValues = {};

    if (hasListerReadback && allKnownOff) {
      prerequisiteKey = "serial.lister.allDecodeDisabled";
    } else if (target === "off") {
      prerequisiteKey = "serial.lister.selectDisplay";
    } else if (busForTarget !== null) {
      const busState = stateSnapshot.decodeDisplayByBus?.[busForTarget] ?? "unknown";
      prerequisiteEnabled = busState === true;
      prerequisiteKey = busState === true
        ? ""
        : busState === false
          ? "serial.lister.decodeDisabled"
          : "serial.lister.unknownPrerequisite";
      prerequisiteValues = { bus: busForTarget };
    } else if (target === "all") {
      prerequisiteEnabled = hasUsableBus;
      const partial = prerequisiteEnabled && busStates.some((value) => value !== true);
      prerequisiteKey = prerequisiteEnabled
        ? partial ? "serial.lister.partialPrerequisite" : ""
        : allKnownOff ? "serial.lister.allDecodeDisabled" : "serial.lister.unknownPrerequisite";
    }

    const dirtyTarget = stateSnapshot.dirtyListerDisplay;
    if (dirtyTarget) {
      prerequisiteEnabled = false;
      prerequisiteKey = "serial.lister.applyDisplayFirst";
      prerequisiteValues = {};
    }
    const dependentDisabled = disabled
      || !hasListerReadback
      || !prerequisiteEnabled;
    const displayDisabled = disabled || !hasListerReadback || !hasUsableBus;
    this.applyListerDisplayButton.disabled = displayDisabled;
    this.applyListerReferenceButton.disabled = dependentDisabled;
    this.exportButton.disabled = dependentDisabled;

    this.prerequisiteNote.hidden = !prerequisiteKey || unavailable;
    this.prerequisiteNote.textContent = prerequisiteKey
      ? translate(prerequisiteKey, prerequisiteValues)
      : "";

    this.listerDisplayForm?.setDisabled(displayDisabled);
    this.syncListerDisplayOptions(stateSnapshot);
    this.listerReferenceForm?.setDisabled(dependentDisabled);
    this.exportForm?.setDisabled(dependentDisabled);
    this.syncFormSlot(this.listerDisplayForm, "listerDisplay", stateSnapshot.jobs);
    this.syncFormSlot(this.listerReferenceForm, "listerReference", stateSnapshot.jobs);
  }
}
