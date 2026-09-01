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
    ],
    saveCommandId: "save-waveform",
  },
};

function determineFileExtension(mode, formatValue) {
  const value = String(formatValue || "").trim().toLowerCase();
  if (mode === "image") {
    if (value === "png") return ".png";
    if (["bmp", "bmp8", "bmp24"].includes(value)) return ".bmp";
    return "";
  }
  if (value === "csv" || value === "ascii-xy") return ".csv";
  if (value === "binary") return ".bin";
  return "";
}

function hasExplicitSaveExtension(mode, filename) {
  const value = String(filename || "");
  return mode === "image"
    ? /\.(?:png|bmp)$/i.test(value)
    : /\.(?:csv|bin)$/i.test(value);
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
    this.pendingRefreshForce = false;
    this.pendingPresentation = false;
    this.mode = "image";
    this.pathEntry = null;
    this.filenameEntry = null;
    this.advancedEntry = null;
    this.saveButton = null;
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
        if (modeKey === this.mode) return;
        this.mode = modeKey;
        this.renderModeButtons();
        this.scheduleRefresh(false);
      });
      this.modeSelector.append(button);
      this.modeButtons.push(button);
    }
    this.applyBusyState();
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
      void this.refresh(false, true);
    });
  }

  rerender() {
    this.buildDom();
    this.stateKey = null;
    this.renderedKey = null;
    queueMicrotask(() => {
      void this.refresh(false, false);
    });
  }

  commandForId(commandId) {
    return this.catalog.commands.find((command) => command.id === commandId) || null;
  }

  async refresh(force = false, read = true) {
    if (this.busy) {
      if (read && (force || this.currentStateKey() !== this.stateKey)) {
        this.pendingRefresh = true;
        this.pendingRefreshForce ||= force;
      } else if (!read) {
        this.pendingPresentation = true;
      }
      return;
    }
    if (read && this.hooks.isExecutionBusy?.()) {
      if (force || this.currentStateKey() !== this.stateKey) {
        this.pendingRefresh = true;
        this.pendingRefreshForce ||= force;
      }
      return;
    }
    const definition = this.selectedDefinition();
    if (!definition) {
      this.stateKey = null;
      this.clearSections();
      return;
    }
    const key = this.currentStateKey();
    const needsRebuild = this.renderedKey !== key;
    if (needsRebuild) this.rebuildSections(key);
    this.applyBusyState();
    if (!force && !needsRebuild && key === this.stateKey) return;
    if (!read) return;
    if (!this.hooks.isAvailable()) return;
    this.pendingRefresh = false;
    this.pendingRefreshForce = false;
    this.stateKey = null;
    this.setBusy(true);
    try {
      const completed = await this.readWorkspace();
      if (completed && key === this.currentStateKey() && key === this.renderedKey) {
        this.stateKey = key;
      }
    } finally {
      this.setBusy(false);
    }
  }

  clearSections() {
    this.renderedKey = null;
    this.entries = [];
    this.pathEntry = null;
    this.filenameEntry = null;
    this.advancedEntry = null;
    this.saveButton = null;
    this.sectionsHost.replaceChildren();
    this.groupHeading.textContent = "";
    this.readStatus.textContent = "";
    this.refreshButton.disabled = true;
  }

  rebuildSections(key) {
    this.epoch += 1;
    this.renderedKey = key;
    this.entries = [];
    this.saveButton = null;
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

    if (modeConfig.id === "waveform") {
      const note = document.createElement("p");
      note.className = "muted compact-note";
      note.textContent = translate("save-export.editor.waveformLengthMaxNote");
      modeSection.append(note);
    }

    this.saveButton = document.createElement("button");
    this.saveButton.type = "button";
    this.saveButton.className = "primary trigger-editor-action";
    this.saveButton.textContent = translate(
      modeConfig.id === "image" ? "save-export.editor.saveImage" : "save-export.editor.saveWaveform",
    );
    this.saveButton.addEventListener("click", () => {
      void this.submitCurrentMode(modeConfig.saveCommandId);
    });
    modeSection.append(this.saveButton);

    const advanced = document.createElement("details");
    advanced.className = "trigger-editor-details";
    const summary = document.createElement("summary");
    summary.textContent = translate("save-export.editor.advancedSettings");
    const advancedHost = document.createElement("div");
    advancedHost.className = "trigger-editor-details-content";
    this.advancedEntry = this.buildAdvancedEntry();
    if (this.advancedEntry) {
      advancedHost.append(this.advancedEntry.container);
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
    form.render(command, { onDirty: () => this.updateDestinationPreview() });
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
    form.render(command, { onDirty: () => this.updateDestinationPreview() });
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
    form.render(command, { onDirty: () => this.updateDestinationPreview() });
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
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary trigger-editor-action";
    button.textContent = translate("actions.apply");
    form.render(command, { onDirty: () => this.applyBusyState() });
    const entry = { id: command.id, container, form, button, kind: "setting" };
    button.addEventListener("click", () => {
      void this.applyAdvancedFilename(entry);
    });
    container.append(note, formHost, button);
    return entry;
  }

  updateDestinationPreview() {
    if (!this.destinationPreview) return;
    const currentValues = (form) => {
      if (!form) return {};
      if (typeof form.draft === "function") {
        const draft = form.draft();
        if (Array.isArray(draft)) {
          return Object.fromEntries(
            draft
              .filter((entry) => entry.value !== "" && entry.value !== null && entry.value !== undefined)
              .map((entry) => [entry.name, entry.value]),
          );
        }
      }
      const values = form.values ? form.values() : {};
      if (values && Object.keys(values).length > 0) return values;
      const queryValues = form.queryValues ? form.queryValues() : null;
      return queryValues && Object.keys(queryValues).length > 0 ? queryValues : values || {};
    };
    const pathValues = currentValues(this.pathEntry?.form);
    const filenameValues = currentValues(this.filenameEntry?.form);
    const path = String(pathValues.path || "");
    const filename = String(filenameValues.filename || "");
    const mode = this.mode;
    const formatEntry = mode === "image"
      ? this.entries.find((entry) => entry.id === "save-image-format")
      : this.entries.find((entry) => entry.id === "save-waveform-format");
    const formatValue = currentValues(formatEntry?.form).format;
    const suffix = determineFileExtension(mode, formatValue);
    const normalizedPath = path ? (path.endsWith("\\") ? path : `${path}\\`) : "";
    if (!filename) {
      this.destinationPreview.textContent = normalizedPath;
    } else if (/[\\/:]/.test(filename)) {
      this.destinationPreview.textContent = filename;
    } else if (/(?:^|[\\/])[^\\/]*\.[^\\/.]+$/.test(filename)) {
      this.destinationPreview.textContent = `${normalizedPath}${filename}`;
    } else {
      this.destinationPreview.textContent = `${normalizedPath}${filename}${suffix}`;
    }
  }

  async readWorkspace() {
    const ids = ["save-pwd", "save-filename", ...this.modeConfig().settingIds];
    const entries = ids
      .map((id) => ({ id, entry: this.entryForId(id) }))
      .filter(({ entry }) => entry);
    let failed = 0;
    const total = entries.length;
    const epoch = this.epoch;
    const stateKey = this.currentStateKey();
    if (total === 0) {
      this.setReadStatus("reading", {
        group: translate(this.mode === "image" ? "save-export.editor.mode.image" : "save-export.editor.mode.waveform"),
        current: 0,
        total,
      });
    }
    for (const [index, { id, entry }] of entries.entries()) {
      if (epoch !== this.epoch || stateKey !== this.currentStateKey()) return false;
      this.setReadStatus("reading", {
        group: translate(this.mode === "image" ? "save-export.editor.mode.image" : "save-export.editor.mode.waveform"),
        current: index + 1,
        total,
      });
      const values = entry.form.queryValues();
      if (values === null) {
        failed += 1;
        if (id === "save-pwd" && this.pathStatus) this.pathStatus.textContent = translate("save-export.editor.pathUnavailable");
        continue;
      }
      const job = await this.hooks.executeCommand(id, values, { intent: "readback" });
      if (epoch !== this.epoch || stateKey !== this.currentStateKey()) return false;
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
    if (epoch !== this.epoch || stateKey !== this.currentStateKey()) return false;
    this.setReadStatus(failed ? "failed" : "loaded", {
      group: translate(this.mode === "image" ? "save-export.editor.mode.image" : "save-export.editor.mode.waveform"),
      failed,
      total,
    });
    this.updateDestinationPreview();
    return true;
  }

  entryForId(id) {
    if (id === "save-pwd") return this.pathEntry;
    if (id === "save-filename") return this.advancedEntry;
    return this.entries.find((entry) => entry.id === id) || null;
  }

  async applyAdvancedFilename(entry) {
    if (
      this.busy
      || this.hooks.isExecutionBusy?.()
      || !this.hooks.isAvailable()
      || !this.isDirty(entry.form)
    ) return null;
    const values = entry.form.values();
    if (values === null) return null;
    const epoch = this.epoch;
    const stateKey = this.currentStateKey();
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(entry.id, values, { intent: "apply" });
      if (
        job?.status === "completed"
        && epoch === this.epoch
        && stateKey === this.currentStateKey()
      ) {
        entry.form.clearDirty();
        entry.form.syncResult(job, false);
      }
      return job;
    } finally {
      this.setBusy(false);
    }
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

  async resyncCurrentFormat(mode, epoch, stateKey) {
    if (epoch !== this.epoch || stateKey !== this.currentStateKey()) {
      this.stateKey = null;
      return;
    }
    const formatId = mode === "image" ? "save-image-format" : "save-waveform-format";
    const entry = this.entryForId(formatId);
    if (!entry?.form) return;
    const values = entry.form.queryValues();
    const job = values === null
      ? null
      : await this.hooks.executeCommand(formatId, values, { intent: "readback" });
    if (epoch !== this.epoch || stateKey !== this.currentStateKey()) {
      this.stateKey = null;
      return;
    }
    if (job?.status === "completed") {
      entry.form.syncResult(job, true);
      this.updateDestinationPreview();
      return;
    }
    entry.form.render(this.commandForId(formatId), {
      onDirty: () => this.updateDestinationPreview(),
    });
    this.stateKey = null;
    this.setReadStatus("failed", {
      group: translate(mode === "image" ? "save-export.editor.mode.image" : "save-export.editor.mode.waveform"),
      failed: 1,
      total: 1,
    });
    this.updateDestinationPreview();
  }

  async submitCurrentMode(saveCommandId) {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    const executionOrder = [];
    if (this.pathEntry && this.isDirty(this.pathEntry.form)) {
      const pathValues = this.pathEntry.form.values();
      if (pathValues === null) return;
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
    const mode = this.mode;
    const epoch = this.epoch;
    const stateKey = this.currentStateKey();
    const resyncFormat = hasExplicitSaveExtension(mode, saveValues?.filename);
    this.setBusy(true);
    try {
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
      if (resyncFormat) await this.resyncCurrentFormat(mode, epoch, stateKey);
    } finally {
      this.setBusy(false);
    }
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
    if (!value && this.pendingPresentation && !this.pendingRefresh) {
      this.pendingPresentation = false;
      this.schedulePresentation();
    }
  }

  applyBusyState() {
    const executionBusy = this.hooks.isExecutionBusy?.() || false;
    const available = this.hooks.isAvailable();
    const disabled = this.busy || executionBusy || !available;
    this.refreshButton.disabled = disabled;
    this.modeButtons.forEach((button) => {
      button.disabled = disabled;
    });
    if (this.pathEntry?.form) this.pathEntry.form.setDisabled(disabled);
    if (this.filenameEntry?.form) this.filenameEntry.form.setDisabled(disabled);
    if (this.advancedEntry?.form) this.advancedEntry.form.setDisabled(disabled);
    if (this.advancedEntry?.button) {
      this.advancedEntry.button.disabled = disabled || !this.isDirty(this.advancedEntry.form);
    }
    if (this.saveButton) this.saveButton.disabled = disabled;
    for (const entry of this.entries) {
      entry.form?.setDisabled(disabled);
    }
    if (!this.busy && !executionBusy && available && this.pendingRefresh) {
      const force = this.pendingRefreshForce;
      this.pendingRefresh = false;
      this.pendingRefreshForce = false;
      this.pendingPresentation = false;
      this.scheduleRefresh(force);
    }
  }
}
