import { translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

export class TriggerEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.epoch = 0;
    this.stateKey = null;
    this.renderedKey = null;
    this.entry = null;
    this.pendingRefresh = false;
    this.pendingPresentation = false;
    this.buildDom();
  }

  buildDom() {
    this.refreshButton?.remove?.();
    this.entry?.button.remove?.();
    this.entry = null;
    this.container.replaceChildren();
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary trigger-editor-refresh";
    this.refreshButton.textContent = translate("trigger.editor.read");
    this.refreshButton.addEventListener("click", () => {
      this.scheduleRefresh(true);
    });
    if (this.hooks.headerActions) {
      this.refreshButton.hidden = true;
      this.hooks.headerActions.append(this.refreshButton);
    } else {
      this.container.append(this.refreshButton);
    }
    this.sectionsHost = document.createElement("div");
    this.sectionsHost.className = "trigger-editor-sections";
    this.container.append(this.sectionsHost);
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "trigger" ? selected : null;
  }

  currentStateKey() {
    const selected = this.selectedDefinition();
    return [
      this.hooks.contextKey(),
      selected?.id || "",
      selected?.group || "",
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
    if (this.renderedKey !== key) this.rebuildSections(key);
    this.applyBusyState();
    if (!read || !this.hooks.isAvailable()) return;
    this.setBusy(true);
    try {
      await this.readSelected();
    } finally {
      this.setBusy(false);
    }
  }

  clearSections() {
    this.renderedKey = null;
    this.entry?.button.remove?.();
    this.entry = null;
    this.sectionsHost.replaceChildren();
    this.refreshButton.disabled = true;
  }

  rebuildSections(key) {
    this.epoch += 1;
    const epoch = this.epoch;
    this.renderedKey = key;
    this.entry?.button.remove?.();
    this.entry = null;
    this.sectionsHost.replaceChildren();
    const command = this.selectedDefinition();
    if (!command || !this.catalog.supported(command)) return;
    this.entry = this.buildSection(command, epoch);
  }

  buildSection(command, epoch) {
    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    const formContainer = document.createElement("div");
    formContainer.className = "command-form";
    const actionButton = document.createElement("button");
    actionButton.type = "button";
    const kind = command.presentation?.kind || "command";
    const action = command.presentation?.action || "run";
    actionButton.className = `${kind === "setting" ? "primary" : "secondary"} trigger-editor-action`;
    actionButton.textContent = translate(
      kind === "setting" ? "actions.apply" : `actions.${action}`,
    );
    // Informational read commands reuse the header Read action; a second
    // inline Read button would duplicate it. The button is recreated on
    // every rebuild, so hidden state always follows the selection.
    actionButton.hidden = kind === "command" && action === "read";
    section.append(formContainer);
    if (this.hooks.headerActions) {
      this.hooks.headerActions.append(actionButton);
    } else {
      section.append(actionButton);
    }
    const fields = this.catalog.fieldsFor?.(command) ?? command.fields ?? [];
    section.hidden = fields.length === 0;
    formContainer.hidden = fields.length === 0;
    this.sectionsHost.append(section);
    const form = new CommandForm(formContainer, this.catalog);
    const entry = { id: command.id, kind, action, form: null, button: actionButton, epoch };
    form.render(command, {});
    entry.form = form;
    actionButton.addEventListener("click", () => {
      void this.submit();
    });
    return entry;
  }

  async readEntry(entry) {
    const parameters = entry.form.queryValues();
    if (parameters === null) return;
    const job = await this.hooks.executeCommand(
      entry.id,
      parameters,
      { intent: "readback" },
    );
    if (job?.status === "completed") entry.form.syncResult(job, true);
  }

  async readSelected() {
    const entry = this.entry;
    if (!entry || entry.epoch !== this.epoch) return;
    if (entry.kind === "setting") {
      await this.readEntry(entry);
    } else {
      await this.hooks.executeCommand(entry.id, {}, {});
    }
  }

  async submit() {
    const entry = this.entry;
    if (!entry || this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    const submissionKey = this.currentStateKey();
    const isSetting = entry.kind === "setting";
    let parameters = {};
    if (isSetting) {
      const values = entry.form.values();
      if (values === null) return;
      parameters = values;
    }
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        entry.id,
        parameters,
        isSetting ? { intent: "apply" } : {},
      );
      if (
        isSetting
        && job?.status === "completed"
        && entry.epoch === this.epoch
        && submissionKey === this.currentStateKey()
      ) {
        entry.form.clearDirty();
        entry.form.syncResult(job, false);
      }
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
    if (this.entry) {
      this.entry.button.disabled = disabled;
      this.entry.form?.setDisabled(disabled);
    }
  }
}
