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
  setup: {
    id: "setup",
    labelKey: "save-export.editor.mode.setup",
    settingIds: [],
    setupSaveCommandId: "setup-save",
    setupRecallCommandId: "setup-recall",
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
    this.setupEntry = null;
    this.setupSaveButton = null;
    this.setupRecallButton = null;
    this.saveButton = null;
    this.destinationPreview = null;
    this.readSettingsPrompt = null;
    this.modeButtons = [];
    this.buildDom();
  }

  buildDom() {
    this.refreshButton?.remove?.();
    this.container.replaceChildren();
    this.readSettingsPrompt = null;
    this.storageNote = document.createElement("p");
    this.storageNote.className = "muted compact-note pc-output-note-box";
    this.storageNote.textContent = translate("save-export.editor.storageNote");
    this.headRow = document.createElement("div");
    this.headRow.className = "trigger-editor-head";
    this.groupHeading = document.createElement("strong");
    this.groupHeading.className = "trigger-editor-heading";
    this.groupHeading.textContent = translate("save-export.editor.title");
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary trigger-editor-refresh";
    this.refreshButton.textContent = translate("actions.readSettings");
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
    this.modeSelector.hidden = true;
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
        this.schedulePresentation();
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

  updateModeFromSelection() {
    const selected = this.selectedDefinition();
    if (selected?.id === "save-waveform") this.mode = "waveform";
    else if (selected?.id === "setup-save") this.mode = "setup";
    else if (selected?.id === "save-image") this.mode = "image";
  }

  hasCurrentSettings() {
    return this.mode === "setup" || this.stateKey === this.currentStateKey();
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
    this.updateModeFromSelection();
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
    this.setupEntry = null;
    this.setupSaveButton = null;
    this.setupRecallButton = null;
    this.saveButton = null;
    this.readSettingsPrompt = null;
    this.sectionsHost.replaceChildren();
    this.groupHeading.textContent = "";
    this.readStatus.textContent = "";
    this.refreshButton.disabled = true;
  }

  rebuildSections(key) {
    const needsRebuildStateReset = this.renderedKey !== key;
    this.epoch += 1;
    if (needsRebuildStateReset) this.stateKey = null;
    this.renderedKey = key;
    this.entries = [];
    this.saveButton = null;
    this.readSettingsPrompt = null;
    this.readStatus.textContent = "";
    this.sectionsHost.replaceChildren();
    this.updateModeFromSelection();
    if (!this.selectedDefinition()) return;

    const modeConfig = SAVE_EXPORT_MODES[this.mode] || SAVE_EXPORT_MODES.image;
    this.refreshButton.hidden = modeConfig.id === "setup";
    if (modeConfig.id === "setup") {
      this.entries = [];
      this.pathEntry = null;
      this.filenameEntry = null;
      this.advancedEntry = null;
      this.saveButton = null;
      this.destinationPreview = null;
      this.buildSetupSection(modeConfig);
      return;
    }
    this.pathEntry = this.buildSharedPathForm();
    this.filenameEntry = this.buildModeFilenameForm(modeConfig.saveCommandId);

    // Settings first: fixed semantic pairs. Each pair keeps its own
    // supported() gating; a lone supported setting spans the full row.
    const settingsSection = document.createElement("section");
    settingsSection.className = "trigger-editor-section";
    const settingsHeading = document.createElement("strong");
    settingsHeading.className = "trigger-editor-heading";
    settingsHeading.textContent = translate(modeConfig.labelKey);
    settingsSection.append(settingsHeading);
    this.readSettingsPrompt = document.createElement("p");
    this.readSettingsPrompt.className = "muted compact-note";
    this.readSettingsPrompt.textContent = translate("save-export.editor.readSettingsPrompt");
    this.readSettingsPrompt.hidden = this.hasCurrentSettings();
    settingsSection.append(this.readSettingsPrompt);
    this.sectionsHost.append(settingsSection);

    const settingPairs = modeConfig.id === "image"
      ? [["save-image-format", "save-image-palette"], ["save-image-ink-saver", "save-image-factors"]]
      : [["save-waveform-format", "save-waveform-length"]];
    for (const pair of settingPairs) {
      const settingsPair = document.createElement("div");
      settingsPair.className = "save-export-pair";
      let rendered = 0;
      for (const commandId of pair) {
        const command = this.commandForId(commandId);
        if (!command || !this.catalog.supported(command)) continue;
        this.entries.push(this.buildSettingEntry(command, settingsPair));
        rendered += 1;
      }
      if (rendered === 1) settingsPair.classList.add("save-export-pair-single");
      if (rendered > 0) this.sectionsHost.append(settingsPair);
    }

    if (modeConfig.id === "waveform") {
      const note = document.createElement("p");
      note.className = "muted compact-note";
      note.textContent = translate("save-export.editor.waveformLengthMaxNote");
      this.sectionsHost.append(note);
    }

    // Destination second.
    const pairHost = document.createElement("div");
    pairHost.className = "save-export-pair";
    pairHost.append(this.pathEntry.section, this.filenameEntry.section);
    this.sectionsHost.append(pairHost);

    // Full-width destination preview (independent of filename half-column)
    if (this.filenameEntry?.form) {
      const previewNote = document.createElement("p");
      previewNote.className = "muted compact-note";
      previewNote.textContent = translate("save-export.editor.destinationPreviewLabel");
      const previewSection = document.createElement("section");
      previewSection.className = "trigger-editor-section";
      if (!this.destinationPreview) {
        this.destinationPreview = document.createElement("output");
        this.destinationPreview.className = "readonly-value";
        this.destinationPreview.textContent = "";
      }
      previewSection.append(previewNote, this.destinationPreview);
      this.sectionsHost.append(previewSection);
    }

    // Save action last (before advanced settings).
    const actionSection = document.createElement("section");
    actionSection.className = "trigger-editor-section";
    this.saveButton = document.createElement("button");
    this.saveButton.type = "button";
    this.saveButton.className = "primary trigger-editor-action";
    this.saveButton.textContent = translate(
      modeConfig.id === "image" ? "save-export.editor.saveImage" : "save-export.editor.saveWaveform",
    );
    this.saveButton.addEventListener("click", () => {
      void this.submitCurrentMode(modeConfig.saveCommandId);
    });
    actionSection.append(this.saveButton);
    this.sectionsHost.append(actionSection);

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
    formHost.className = "command-form";
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
    formHost.className = "command-form";
    const command = this.commandForId(saveCommandId);
    const form = new CommandForm(formHost, this.catalog);
    form.render(command, { onDirty: () => this.updateDestinationPreview() });
    this.destinationPreview = document.createElement("output");
    this.destinationPreview.className = "readonly-value";
    this.destinationPreview.textContent = "";
    // Preview will be appended separately as full-width section, not inside filename section
    section.append(heading, formHost);
    return { section, form, destinationPreview: this.destinationPreview };
  }

  buildSetupSection(modeConfig) {
    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = translate(modeConfig.labelKey);
    const note = document.createElement("p");
    note.className = "muted compact-note";
    note.textContent = translate("save-export.editor.setupNote");
    const formHost = document.createElement("div");
    formHost.className = "command-form";
    const command = this.commandForId(modeConfig.setupSaveCommandId);
    const form = new CommandForm(formHost, this.catalog);
    form.render(command);
    this.setupEntry = { form };
    this.setupSaveButton = document.createElement("button");
    this.setupSaveButton.type = "button";
    this.setupSaveButton.className = "primary trigger-editor-action";
    this.setupSaveButton.textContent = translate("save-export.editor.saveSetup");
    this.setupSaveButton.addEventListener("click", () => {
      void this.submitSetup(modeConfig.setupSaveCommandId, false);
    });
    const showRecall = this.selectedDefinition()?.id !== "setup-save";
    if (showRecall) {
      this.setupRecallButton = document.createElement("button");
      this.setupRecallButton.type = "button";
      this.setupRecallButton.className = "secondary trigger-editor-action";
      this.setupRecallButton.textContent = translate("save-export.editor.recallSetup");
      this.setupRecallButton.addEventListener("click", () => {
        void this.submitSetup(modeConfig.setupRecallCommandId, true);
      });
    }
    section.append(heading, note, formHost, this.setupSaveButton);
    if (showRecall && this.setupRecallButton) {
      section.append(this.setupRecallButton);
    }
    this.sectionsHost.append(section);
    this.applyBusyState();
  }

  async submitSetup(commandId, needsConfirm) {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    const form = this.setupEntry?.form;
    const values = form?.values?.();
    if (values === null || values === undefined) return;
    if (needsConfirm) {
      const target = values.target === "file"
        ? String(values.file || "")
        : translate("save-export.editor.setupSlotTarget", { slot: values.slot });
      if (!window.confirm(translate("save-export.editor.recallSetupConfirm", { target }))) return;
    }
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(commandId, values, { intent: "command" });
      if (job?.status === "completed") form.clearDirty();
    } finally {
      this.setBusy(false);
    }
  }

  buildSettingEntry(command, container) {
    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = this.catalog.commandLabel(command);
    section.append(heading);
    const formHost = document.createElement("div");
    formHost.className = "command-form";
    const form = new CommandForm(formHost, this.catalog);
    form.render(command, { onDirty: () => this.updateDestinationPreview() });
    section.append(formHost);
    // Description after the form: its line count must never push the
    // label/control of this or the paired column down.
    const description = this.catalog.description?.(command);
    if (description) {
      const note = document.createElement("p");
      note.className = "muted compact-note";
      note.textContent = description;
      section.append(note);
    }
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
    formHost.className = "command-form";
    const form = new CommandForm(formHost, this.catalog);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "primary trigger-editor-action";
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
    if (this.mode === "setup") return true;
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
    return failed === 0;
  }

  entryForId(id) {
    if (id === "save-pwd") return this.pathEntry;
    if (id === "save-filename") return this.advancedEntry;
    return this.entries.find((entry) => entry.id === id) || null;
  }

  async applyAdvancedFilename(entry) {
    if (this.mode !== "setup" && !this.hasCurrentSettings()) return null;
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
    if (this.mode !== "setup" && !this.hasCurrentSettings()) return;
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
          this.readStatus.className = "muted compact-note";
          this.readStatus.textContent = "";
          return;
        }
        item.form.clearDirty();
        item.form.syncResult(job, false);
      }
      const saveJob = await this.hooks.executeCommand(saveCommandId, saveValues, { intent: "command" });
      if (saveJob?.status !== "completed") {
        this.readStatus.className = "muted compact-note";
        this.readStatus.textContent = "";
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
    const executionDisabled = this.busy || executionBusy || !available;
    const settingsRequired = this.mode !== "setup" && !this.hasCurrentSettings();
    const editingDisabled = executionDisabled || settingsRequired;
    this.refreshButton.disabled = executionDisabled;
    this.modeButtons.forEach((button) => {
      button.disabled = executionDisabled;
    });
    if (this.pathEntry?.form) this.pathEntry.form.setDisabled(editingDisabled);
    if (this.filenameEntry?.form) this.filenameEntry.form.setDisabled(editingDisabled);
    if (this.setupEntry?.form) this.setupEntry.form.setDisabled(executionDisabled);
    if (this.setupSaveButton) this.setupSaveButton.disabled = executionDisabled;
    if (this.setupRecallButton) this.setupRecallButton.disabled = executionDisabled;
    if (this.advancedEntry?.form) this.advancedEntry.form.setDisabled(editingDisabled);
    if (this.advancedEntry?.button) {
      this.advancedEntry.button.disabled = editingDisabled || !this.isDirty(this.advancedEntry.form);
    }
    if (this.saveButton) this.saveButton.disabled = editingDisabled;
    for (const entry of this.entries) {
      entry.form?.setDisabled(editingDisabled);
    }
    if (this.readSettingsPrompt) this.readSettingsPrompt.hidden = !settingsRequired;
    if (!this.busy && !executionBusy && available && this.pendingRefresh) {
      const force = this.pendingRefreshForce;
      this.pendingRefresh = false;
      this.pendingRefreshForce = false;
      this.pendingPresentation = false;
      this.scheduleRefresh(force);
    }
  }
}
