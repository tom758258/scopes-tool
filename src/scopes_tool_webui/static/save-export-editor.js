import { translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

const SAVE_EXPORT_MODES = {
  image: {
    id: "image",
    labelKey: "save-export.editor.mode.image",
    settingIds: [
      "save-image-format",
      "save-image-palette",
      "save-image-ink-saver",
      "save-image-factors",
    ],
    saveCommandId: "save-image",
  },
  waveform: {
    id: "waveform",
    labelKey: "save-export.editor.mode.waveform",
    settingIds: [
      "save-waveform-format",
      "save-waveform-length",
      "save-waveform-length-max",
    ],
    saveCommandId: "save-waveform",
  },
};

function resultValue(payload, key, depth = 0) {
  if (payload === null || typeof payload !== "object" || depth > 4) return undefined;
  if (Object.prototype.hasOwnProperty.call(payload, key)) {
    const value = payload[key];
    if (value === null || typeof value !== "object") return value;
  }
  for (const value of Object.values(payload)) {
    if (value && typeof value === "object") {
      const found = resultValue(value, key, depth + 1);
      if (found !== undefined) return found;
    }
  }
  return undefined;
}

function determineFileExtension(mode, formatValue) {
  const value = String(formatValue || "").toLowerCase();
  if (mode === "image") {
    if (value.includes("png")) return ".png";
    if (value.includes("bmp")) return ".bmp";
    return ".png";
  }
  if (value.includes("csv")) return ".csv";
  if (value.includes("bin")) return ".bin";
  if (value.includes("xy")) return ".xy";
  return ".csv";
}

export class SaveExportEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.epoch = 0;
    this.stateKey = null;
    this.renderedKey = null;
    this.entries = [];
    this.pendingRefresh = false;
    this.pendingPresentation = false;
    this.mode = "image";
    this.pathEntry = null;
    this.filenameEntry = null;
    this.destinationPreview = null;
    this.modeButtons = [];
    this.buildDom();
  }

  buildDom() {
    this.refreshButton?.remove?.();
    this.container.replaceChildren();
    this.storageNote = document.createElement("p");
    this.storageNote.className = "muted compact-note";
    this.storageNote.textContent = translate("save-export.editor.storageNote");
    this.headRow = document.createElement("div");
    this.headRow.className = "trigger-editor-head";
    this.groupHeading = document.createElement("strong");
    this.groupHeading.className = "trigger-editor-heading";
    this.groupHeading.textContent = translate("save-export.editor.title");
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary trigger-editor-refresh";
    this.refreshButton.textContent = translate("save-export.editor.reloadSettings");
    this.refreshButton.addEventListener("click", () => {
      this.scheduleRefresh(true);
    });
    this.headRow.append(this.groupHeading);
    if (this.hooks.headerActions) {
      this.hooks.headerActions.append(this.refreshButton);
    } else {
      this.headRow.append(this.refreshButton);
    }
    this.modeSelector = document.createElement("div");
    this.modeSelector.className = "trigger-editor-segmented";
    this.readStatus = document.createElement("output");
    this.readStatus.className = "muted compact-note";
    this.sectionsHost = document.createElement("div");
    this.sectionsHost.className = "trigger-editor-sections";
    this.container.append(
      this.storageNote,
      this.headRow,
      this.modeSelector,
      this.readStatus,
      this.sectionsHost,
    );
    this.renderModeButtons();
  }

  renderModeButtons() {
    this.modeSelector.replaceChildren();
    this.modeButtons = [];
    for (const [modeKey, config] of Object.entries(SAVE_EXPORT_MODES)) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      if (modeKey === this.mode) button.classList.add("selected");
      button.textContent = translate(config.labelKey);
      button.addEventListener("click", () => {
        this.mode = modeKey;
        this.renderModeButtons();
        this.rebuildSections(this.currentStateKey());
        this.scheduleRefresh(false);
      });
      this.modeSelector.append(button);
      this.modeButtons.push(button);
    }
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "save-export" ? selected : null;
  }

  currentStateKey() {
    const selected = this.selectedDefinition();
    return [
      this.hooks.contextKey(),
      selected ? `save-export:${this.mode}` : "",
    ].join("|");
  }

  scheduleRefresh(force = false) {
    queueMicrotask(() => {
      void this.refresh(force, true);
    });
  }

  schedulePresentation() {
    queueMicrotask(() => {
      void this.refresh(false, false);
    });
  }

  rerender() {
    this.buildDom();
    this.stateKey = null;
    this.renderedKey = null;
    this.schedulePresentation();
  }

  commandForId(commandId) {
    return this.catalog.commands.find((command) => command.id === commandId) || null;
  }

  formatCommand(command, includeAction = false) {
    if (!command) return command;
    const fields = (this.catalog.fieldsFor ? this.catalog.fieldsFor(command) : command.fields).filter(
      (field) => includeAction || field.name !== "action",
    );
    return { ...command, fields };
  }

  async refresh(force = false, read = true) {
    if (this.busy) {
      if (read && (force || this.currentStateKey() !== this.stateKey)) {
        this.pendingRefresh = true;
      } else if (!read) {
        this.pendingPresentation = true;
      }
      return;
    }
    if (read && this.hooks.isExecutionBusy?.()) return;
    const definition = this.selectedDefinition();
    if (!definition) {
      this.stateKey = null;
      this.clearSections();
      return;
    }
    const key = this.currentStateKey();
    if (!force && key === this.stateKey) {
      this.applyBusyState();
      return;
    }
    this.stateKey = key;
    if (this.renderedKey !== key) this.rebuildSections(key);
    this.applyBusyState();
    if (!read || !this.hooks.isAvailable()) return;
    this.setBusy(true);
    try {
      await this.readWorkspace();
    } finally {
      this.setBusy(false);
    }
  }

  clearSections() {
    this.renderedKey = null;
    this.entries = [];
    this.sectionsHost.replaceChildren();
    this.groupHeading.textContent = "";
    this.readStatus.textContent = "";
    this.refreshButton.disabled = true;
  }

  rebuildSections(key) {
    this.epoch += 1;
    this.renderedKey = key;
    this.entries = [];
    this.readStatus.textContent = "";
    this.sectionsHost.replaceChildren();
    if (!this.selectedDefinition()) return;

    const modeConfig = SAVE_EXPORT_MODES[this.mode] || SAVE_EXPORT_MODES.image;
    this.pathEntry = this.buildSharedPathForm();
    this.filenameEntry = this.buildModeFilenameForm(modeConfig.saveCommandId);
    this.sectionsHost.append(this.pathEntry.section, this.filenameEntry.section);

    const modeSection = document.createElement("section");
    modeSection.className = "trigger-editor-section";
    const modeHeading = document.createElement("strong");
    modeHeading.className = "trigger-editor-heading";
    modeHeading.textContent = translate(modeConfig.labelKey);
    modeSection.append(modeHeading);
    this.sectionsHost.append(modeSection);

    for (const commandId of modeConfig.settingIds) {
      const command = this.commandForId(commandId);
      if (!command || !this.catalog.supported(command)) continue;
      const entry = this.buildSettingEntry(command, modeSection);
      this.entries.push(entry);
    }

    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.className = "primary trigger-editor-action";
    saveButton.textContent = translate(
      modeConfig.id === "image" ? "save-export.editor.saveImage" : "save-export.editor.saveWaveform",
    );
    saveButton.addEventListener("click", () => {
      void this.submitCurrentMode(modeConfig.saveCommandId);
    });
    modeSection.append(saveButton);

    const advanced = document.createElement("details");
    advanced.className = "trigger-editor-details";
    const summary = document.createElement("summary");
    summary.textContent = translate("save-export.editor.advancedSettings");
    const advancedHost = document.createElement("div");
    advancedHost.className = "trigger-editor-details-content";
    const advancedEntry = this.buildAdvancedEntry();
    if (advancedEntry) {
      advancedHost.append(advancedEntry.container);
      advanced.append(summary, advancedHost);
      this.sectionsHost.append(advanced);
    }

    this.updateDestinationPreview();
  }

  buildSharedPathForm() {
    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = translate("field.save-pwd.path");
    const formHost = document.createElement("div");
    const command = this.commandForId("save-pwd");
    const form = new CommandForm(formHost, this.catalog);
    form.render(command ? this.formatCommand(command, false) : { id: "save-pwd", fields: [] });
    this.pathStatus = document.createElement("p");
    this.pathStatus.className = "muted compact-note";
    this.pathStatus.textContent = "";
    const note = document.createElement("p");
    note.className = "muted compact-note";
    note.textContent = translate("save-export.editor.pathHelper");
    section.append(heading, formHost, this.pathStatus, note);
    return { section, form };
  }

  buildModeFilenameForm(saveCommandId) {
    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = translate(
      saveCommandId === "save-image" ? "field.save-image.filename" : "field.save-waveform.filename",
    );
    const formHost = document.createElement("div");
    const command = this.commandForId(saveCommandId);
    const form = new CommandForm(formHost, this.catalog);
    form.render(this.formatCommand(command, false));
    const preview = document.createElement("p");
    preview.className = "muted compact-note";
    preview.textContent = translate("save-export.editor.destinationPreviewLabel");
    this.destinationPreview = document.createElement("output");
    this.destinationPreview.className = "readonly-value";
    this.destinationPreview.textContent = "";
    section.append(heading, formHost, preview, this.destinationPreview);
    return { section, form };
  }

  buildSettingEntry(command, container) {
    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = this.catalog.commandLabel(command);
    const description = this.catalog.description?.(command);
    if (description) {
      const note = document.createElement("p");
      note.className = "muted compact-note";
      note.textContent = description;
      section.append(note);
    }
    const formHost = document.createElement("div");
    const form = new CommandForm(formHost, this.catalog);
    form.render(this.formatCommand(command, false));
    section.append(heading, formHost);
    container.append(section);
    return { id: command.id, form, kind: "setting", section };
  }

  buildAdvancedEntry() {
    const command = this.commandForId("save-filename");
    if (!command || !this.catalog.supported(command)) return null;
    const container = document.createElement("div");
    const note = document.createElement("p");
    note.className = "muted compact-note";
    note.textContent = translate("save-export.editor.baseFilenameHelp");
    const formHost = document.createElement("div");
    const form = new CommandForm(formHost, this.catalog);
    form.render(this.formatCommand(command, false));
    container.append(note, formHost);
    return { container, form };
  }

  updateDestinationPreview() {
    if (!this.destinationPreview) return;
    const currentValues = (form) => {
      if (!form) return {};
      const values = form.values ? form.values() : {};
      if (values && Object.keys(values).length > 0) return values;
      const queryValues = form.queryValues ? form.queryValues() : null;
      return queryValues && Object.keys(queryValues).length > 0 ? queryValues : values;
    };
    const pathValues = currentValues(this.pathEntry?.form);
    const filenameValues = currentValues(this.filenameEntry?.form);
    const path = String(pathValues.path || "");
    const filename = String(filenameValues.filename || "scope");
    const mode = this.mode;
    const formatEntry = mode === "image"
      ? this.entries.find((entry) => entry.id === "save-image-format")
      : this.entries.find((entry) => entry.id === "save-waveform-format");
    const formatValue = currentValues(formatEntry?.form).format;
    const suffix = determineFileExtension(mode, formatValue);
    const normalizedPath = path ? (path.endsWith("\\") ? path : `${path}\\`) : "";
    this.destinationPreview.textContent = `${normalizedPath}${filename}${suffix}`;
  }

  async readWorkspace() {
    const ids = ["save-pwd", ...this.modeConfig().settingIds];
    if (this.mode === "waveform") ids.push("save-waveform-length-max");
    let failed = 0;
    const total = ids.length;
    this.setReadStatus("reading", {
      group: translate(this.mode === "image" ? "save-export.editor.mode.image" : "save-export.editor.mode.waveform"),
      current: 0,
      total,
    });
    for (const id of ids) {
      const entry = this.entries.find((item) => item.id === id)
        || (id === "save-pwd" && this.pathEntry ? { id, form: this.pathEntry.form, kind: "setting" } : null);
      if (!entry) continue;
      const values = entry.form.queryValues();
      if (values === null) {
        failed += 1;
        if (id === "save-pwd" && this.pathStatus) this.pathStatus.textContent = translate("save-export.editor.pathUnavailable");
        continue;
      }
      const job = await this.hooks.executeCommand(id, values, { intent: "readback" });
      if (job?.status !== "completed") {
        failed += 1;
        if (id === "save-pwd" && this.pathStatus) this.pathStatus.textContent = translate("save-export.editor.pathUnavailable");
        continue;
      }
      entry.form.syncResult(job, true);
      if (id === "save-pwd") {
        if (this.pathStatus) this.pathStatus.textContent = "";
        this.updateDestinationPreview();
      }
    }
    this.setReadStatus(failed ? "failed" : "loaded", {
      group: translate(this.mode === "image" ? "save-export.editor.mode.image" : "save-export.editor.mode.waveform"),
      failed,
      total,
    });
    this.updateDestinationPreview();
  }

  modeConfig() {
    return SAVE_EXPORT_MODES[this.mode] || SAVE_EXPORT_MODES.image;
  }

  setReadStatus(kind, values = {}) {
    const key = {
      reading: "save-export.editor.readingCurrent",
      loaded: "save-export.editor.currentLoaded",
      failed: "save-export.editor.currentReadFailed",
    }[kind];
    this.readStatus.className = kind === "failed" ? "error-summary" : "muted compact-note";
    this.readStatus.textContent = translate(key, values);
  }

  async submitCurrentMode(saveCommandId) {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    const executionOrder = [];
    const pathValues = this.pathEntry?.form?.values?.();
    if (this.pathEntry && pathValues !== null && this.isDirty(this.pathEntry.form)) {
      executionOrder.push({ id: "save-pwd", form: this.pathEntry.form, values: pathValues, intent: "apply" });
    }
    for (const entry of this.entries) {
      if (!entry.form || entry.id === saveCommandId) continue;
      if (!this.isDirty(entry.form)) continue;
      const values = entry.form.values();
      if (values === null) return;
      executionOrder.push({ id: entry.id, form: entry.form, values, intent: "apply" });
    }
    const saveValues = this.filenameEntry?.form?.values?.();
    if (saveValues === null) return;
    for (const item of executionOrder) {
      const job = await this.hooks.executeCommand(item.id, item.values, { intent: item.intent });
      if (job?.status !== "completed") {
        this.setReadStatus("failed", { group: translate(this.mode === "image" ? "save-export.editor.mode.image" : "save-export.editor.mode.waveform"), failed: 1, total: 1 });
        return;
      }
      item.form.clearDirty();
      item.form.syncResult(job, false);
    }
    const saveJob = await this.hooks.executeCommand(saveCommandId, saveValues, { intent: "command" });
    if (saveJob?.status !== "completed") {
      this.setReadStatus("failed", { group: translate(this.mode === "image" ? "save-export.editor.mode.image" : "save-export.editor.mode.waveform"), failed: 1, total: 1 });
      return;
    }
    this.filenameEntry.form.clearDirty();
    this.filenameEntry.form.syncResult(saveJob, false);
    this.updateDestinationPreview();
  }

  isDirty(form) {
    if (!form || typeof form.container?.querySelectorAll !== "function") return false;
    return [...form.container.querySelectorAll("[data-field]")].some(
      (input) => input.dataset.dirty === "true",
    );
  }

  setBusy(value) {
    this.busy = value;
    this.applyBusyState();
    if (!value && this.pendingRefresh) {
      this.pendingRefresh = false;
      this.pendingPresentation = false;
      this.scheduleRefresh(true);
    } else if (!value && this.pendingPresentation) {
      this.pendingPresentation = false;
      this.schedulePresentation();
    }
  }

  applyBusyState() {
    const disabled = this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable();
    this.refreshButton.disabled = disabled;
    this.modeButtons.forEach((button) => {
      button.disabled = disabled;
    });
    if (this.pathEntry?.form) this.pathEntry.form.setDisabled(disabled);
    if (this.filenameEntry?.form) this.filenameEntry.form.setDisabled(disabled);
    for (const entry of this.entries) {
      entry.form?.setDisabled(disabled);
    }
  }
}
