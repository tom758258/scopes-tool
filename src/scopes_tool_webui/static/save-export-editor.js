import { translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

const SAVE_EXPORT_GROUPS = ["path-filename", "image", "waveform"];

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
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary trigger-editor-refresh";
    this.refreshButton.textContent = translate("actions.refresh");
    this.refreshButton.addEventListener("click", () => {
      this.scheduleRefresh(true);
    });
    this.headRow.append(this.groupHeading);
    if (this.hooks.headerActions) {
      this.refreshButton.hidden = true;
      this.hooks.headerActions.append(this.refreshButton);
    } else {
      this.headRow.append(this.refreshButton);
    }
    this.readStatus = document.createElement("output");
    this.readStatus.className = "muted compact-note";
    this.sectionsHost = document.createElement("div");
    this.sectionsHost.className = "trigger-editor-sections";
    this.container.append(
      this.storageNote,
      this.headRow,
      this.readStatus,
      this.sectionsHost,
    );
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "save-export" ? selected : null;
  }

  currentStateKey() {
    const selected = this.selectedDefinition();
    return [
      this.hooks.contextKey(),
      selected ? "save-export" : "",
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
    this.groupHeading.textContent = translate("save-export.editor.workspaceLabel");
    if (this.renderedKey !== key) this.rebuildSections(key);
    this.applyBusyState();
    if (!read || !this.hooks.isAvailable()) return;
    if (read) this.setBusy(true);
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
    const epoch = this.epoch;
    this.renderedKey = key;
    this.entries = [];
    this.readStatus.textContent = "";
    this.sectionsHost.replaceChildren();
    if (!this.selectedDefinition()) return;
    for (const group of SAVE_EXPORT_GROUPS) {
      const commands = this.catalog.commands.filter(
        (command) => command.editor === "save-export"
          && command.group === group
          && this.catalog.supported(command),
      );
      if (!commands.length) continue;
      const section = document.createElement("section");
      section.className = "trigger-editor-section save-export-group";
      const heading = document.createElement("strong");
      heading.className = "trigger-editor-heading";
      heading.textContent = this.catalog.groupLabel(group);
      section.append(heading);
      this.sectionsHost.append(section);
      for (const command of commands) {
        this.entries.push(this.buildCommand(command, epoch, section));
      }
    }
  }

  buildCommand(command, epoch, section) {
    const commandBlock = document.createElement("div");
    commandBlock.className = "save-export-command";
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = this.catalog.commandLabel(command);
    commandBlock.append(heading);
    const description = this.catalog.description?.(command);
    if (description) {
      const note = document.createElement("p");
      note.className = "muted compact-note";
      note.textContent = description;
      commandBlock.append(note);
    }
    section.append(commandBlock);

    if (command.id === "save-waveform-length-max") {
      const output = document.createElement("output");
      output.className = "readonly-value";
      output.textContent = "-";
      const readError = this.buildReadError();
      commandBlock.append(output, readError);
      return { id: command.id, group: command.group, kind: "readonly", output, readError, epoch };
    }

    const formContainer = document.createElement("div");
    const actionButton = document.createElement("button");
    actionButton.type = "button";
    actionButton.className = "secondary trigger-editor-action";
    const kind = command.presentation?.kind || "command";
    const action = command.presentation?.action || "run";
    actionButton.textContent = translate(
      kind === "setting" ? "actions.apply" : `actions.${action}`,
    );
    commandBlock.append(formContainer, actionButton);
    const form = new CommandForm(formContainer, this.catalog);
    form.render(command, {});
    const entry = {
      id: command.id,
      group: command.group,
      kind,
      action,
      form,
      button: actionButton,
      epoch,
    };
    if (kind === "setting") {
      entry.readError = this.buildReadError();
      commandBlock.append(entry.readError);
    }
    actionButton.addEventListener("click", () => {
      void this.submit(entry);
    });
    return entry;
  }

  buildReadError() {
    const error = document.createElement("p");
    error.className = "error-summary";
    error.textContent = translate("save-export.editor.currentValueUnavailable");
    error.hidden = true;
    return error;
  }

  setReadError(entry, failed) {
    if (!entry.readError) return;
    entry.readError.hidden = !failed;
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

  async readEntry(entry) {
    const parameters = entry.kind === "readonly" ? {} : entry.form.queryValues();
    if (parameters === null) return false;
    const job = await this.hooks.executeCommand(
      entry.id,
      parameters,
      { intent: "readback" },
    );
    if (job?.status !== "completed" || entry.epoch !== this.epoch) return false;
    if (entry.kind === "readonly") {
      const enabled = resultValue(job.result, "enabled");
      if (enabled === undefined) return false;
      entry.output.textContent = translate(enabled ? "status.enabled" : "status.disabled");
      return true;
    }
    entry.form.syncResult(job, true);
    return true;
  }

  async readEntries(entries, group) {
    const epoch = this.epoch;
    const readable = entries.filter(
      (entry) => ["setting", "readonly"].includes(entry.kind),
    );
    readable.forEach((entry) => this.setReadError(entry, false));
    let failed = 0;
    for (const [index, entry] of readable.entries()) {
      if (epoch !== this.epoch) return;
      this.setReadStatus("reading", {
        group,
        current: index + 1,
        total: readable.length,
      });
      const succeeded = await this.readEntry(entry);
      if (epoch !== this.epoch) return;
      this.setReadError(entry, !succeeded);
      if (!succeeded) failed += 1;
    }
    this.setReadStatus(failed ? "failed" : "loaded", {
      group,
      failed,
      total: readable.length,
    });
  }

  async readWorkspace() {
    await this.readEntries(
      this.entries,
      translate("save-export.editor.workspaceName"),
    );
  }

  async readGroup(group) {
    await this.readEntries(
      this.entries.filter((entry) => entry.group === group),
      this.catalog.groupLabel(group),
    );
  }

  async submit(entry) {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    if (!this.entries.includes(entry) || entry.kind === "readonly") return;
    const submissionKey = this.currentStateKey();
    const parameters = entry.form.values();
    if (parameters === null) return;
    const isSetting = entry.kind === "setting";
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        entry.id,
        parameters,
        { intent: isSetting ? "apply" : "command" },
      );
      if (
        !isSetting
        || job?.status !== "completed"
        || entry.epoch !== this.epoch
        || submissionKey !== this.currentStateKey()
      ) return;
      entry.form.clearDirty();
      entry.form.syncResult(job, false);
      await this.readGroup(entry.group);
    } finally {
      this.setBusy(false);
    }
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
    for (const entry of this.entries) {
      if (entry.button) entry.button.disabled = disabled;
      entry.form?.setDisabled(disabled);
    }
  }
}
