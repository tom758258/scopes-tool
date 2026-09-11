import { translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

export class CursorEditor {
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
    this.container.replaceChildren();
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary trigger-editor-refresh";
    this.refreshButton.textContent = translate("cursor.editor.read");
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

  definition() {
    return this.selectedDefinition();
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "cursor" ? selected : null;
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
      await this.readState();
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
    const command = this.definition();
    if (!command || !this.catalog.supported(command)) return;
    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    const formContainer = document.createElement("div");
    formContainer.className = "command-form";
    if (command.id === "cursor-set") {
      formContainer.classList.add("cursor-set-form");
    }
    const actionButton = document.createElement("button");
    actionButton.type = "button";
    actionButton.className = "secondary trigger-editor-action";
    actionButton.textContent = translate(
      command.id === "cursor-set" ? "actions.apply" : `actions.${command.presentation?.action || "run"}`,
    );
    // cursor-query reuses the header Read action; a second query button would
    // duplicate it, so only set/off keep a section button. The button is
    // recreated on every rebuild, so hidden state always follows the selection.
    actionButton.hidden = command.id === "cursor-query";
    section.append(formContainer);
    if (this.hooks.headerActions) {
      this.hooks.headerActions.append(actionButton);
    } else {
      section.append(actionButton);
    }
    this.sectionsHost.append(section);
    const form = new CommandForm(formContainer, this.catalog);
    this.entry = { form, button: actionButton, epoch };
    form.render(command, {});
    const fields = this.catalog.fieldsFor?.(command) ?? command.fields ?? [];
    section.hidden = fields.length === 0;
    formContainer.hidden = fields.length === 0;
    actionButton.addEventListener("click", () => {
      void this.submit();
    });
  }

  async readState() {
    if (!this.entry || this.entry.epoch !== this.epoch) return;
    await this.hooks.executeCommand(
      "cursor-query",
      {},
      { intent: "readback" },
    );
  }

  async submit() {
    const entry = this.entry;
    if (!entry || this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    const command = this.definition();
    if (!command) return;
    const submissionKey = this.currentStateKey();
    let parameters = {};
    if (command.id === "cursor-set") {
      const values = entry.form.values();
      if (values === null) return;
      parameters = values;
    }
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        command.id,
        parameters,
        { intent: "apply" },
      );
      if (
        job?.status === "completed"
        && entry.epoch === this.epoch
        && submissionKey === this.currentStateKey()
      ) {
        entry.form.clearDirty();
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
