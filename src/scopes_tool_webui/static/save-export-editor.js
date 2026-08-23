import { translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

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
    this.buildDom();
  }

  buildDom() {
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
    this.headRow.append(this.groupHeading, this.refreshButton);
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
      String(this.hooks.isAvailable()),
      selected?.id || "",
      selected?.group || "",
    ].join("|");
  }

  scheduleRefresh(force = false) {
    queueMicrotask(() => {
      void this.refresh(force);
    });
  }

  rerender() {
    this.buildDom();
    this.stateKey = null;
    this.renderedKey = null;
    this.scheduleRefresh();
  }

  async refresh(force = false) {
    if (this.busy) {
      if (force || this.currentStateKey() !== this.stateKey) {
        this.pendingRefresh = true;
      }
      return;
    }
    const definition = this.selectedDefinition();
    if (!definition || !this.hooks.isAvailable()) {
      this.stateKey = null;
      this.clearSections();
      return;
    }
    const key = this.currentStateKey();
    if (!force && key === this.stateKey) return;
    this.setBusy(true);
    try {
      this.stateKey = key;
      this.groupHeading.textContent = this.catalog.groupLabel(definition.group);
      if (this.renderedKey !== key) this.rebuildSections(key);
      this.applyBusyState();
      await this.readActiveGroup();
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
    this.sectionsHost.replaceChildren();
    const definition = this.selectedDefinition();
    if (!definition) return;
    for (const command of this.catalog.commands) {
      if (command.editor !== "save-export" || command.group !== definition.group) continue;
      if (!this.catalog.supported(command)) continue;
      this.entries.push(this.buildSection(command, epoch));
    }
  }

  buildSection(command, epoch) {
    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = this.catalog.commandLabel(command);
    section.append(heading);
    this.sectionsHost.append(section);

    if (command.id === "save-waveform-length-max") {
      const output = document.createElement("output");
      output.className = "readonly-value";
      output.textContent = "-";
      const readError = this.buildReadError();
      section.append(output, readError);
      return { id: command.id, kind: "readonly", output, readError, epoch };
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
    section.append(formContainer, actionButton);
    const form = new CommandForm(formContainer, this.catalog);
    form.render(command, {});
    const entry = {
      id: command.id,
      kind,
      action,
      form,
      button: actionButton,
      epoch,
    };
    if (kind === "setting") {
      entry.readError = this.buildReadError();
      section.append(entry.readError);
    } else if (action === "save") {
      const help = document.createElement("p");
      help.className = "muted compact-note";
      help.textContent = translate("save-export.editor.filenameHelp");
      section.insertBefore(help, actionButton);
      entry.help = help;
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

  async readActiveGroup() {
    const epoch = this.epoch;
    const readable = this.entries.filter(
      (entry) => ["setting", "readonly"].includes(entry.kind),
    );
    const group = this.catalog.groupLabel(this.selectedDefinition()?.group || "");
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

  async submit(entry) {
    if (this.busy || !this.hooks.isAvailable()) return;
    if (!this.entries.includes(entry) || entry.kind === "readonly") return;
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
      if (!isSetting || job?.status !== "completed" || entry.epoch !== this.epoch) return;
      entry.form.clearDirty();
      entry.form.syncResult(job, false);
      this.pendingRefresh = true;
    } finally {
      this.setBusy(false);
    }
  }

  setBusy(value) {
    this.busy = value;
    this.applyBusyState();
    if (!value && this.pendingRefresh) {
      this.pendingRefresh = false;
      this.scheduleRefresh(true);
    }
  }

  applyBusyState() {
    this.refreshButton.disabled = this.busy || !this.hooks.isAvailable();
    for (const entry of this.entries) {
      if (entry.button) entry.button.disabled = this.busy;
      entry.form?.setDisabled(this.busy);
    }
  }
}
