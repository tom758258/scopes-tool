import { CommandForm } from "/static/command-form.js";
import { translate } from "/static/i18n.js";

const REFERENCE_MANAGEMENT_ACTIONS = [
  "reference-display",
  "reference-label",
  "reference-clear",
];

export class ReferenceEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.renderedKey = null;
    this.entries = [];
    this.buildHeaderAction();
  }

  buildHeaderAction() {
    this.refreshButton?.remove?.();
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary reference-editor-refresh";
    this.refreshButton.textContent = translate("actions.refresh");
    this.refreshButton.hidden = true;
    this.refreshButton.addEventListener("click", () => void this.refresh());
    this.hooks.headerActions?.append(this.refreshButton);
  }

  definition(id) {
    return this.catalog.commands.find((command) => command.id === id) || null;
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "reference" ? selected : null;
  }

  currentKey() {
    return `${this.hooks.contextKey()}|${this.selectedDefinition()?.id || ""}`;
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    this.buildHeaderAction();
    this.renderedKey = null;
    this.schedulePresentation();
  }

  present() {
    const definition = this.selectedDefinition();
    if (!definition) {
      this.renderedKey = null;
      this.entries = [];
      this.container.replaceChildren();
      this.applyBusyState();
      return;
    }
    const key = this.currentKey();
    if (key !== this.renderedKey) {
      this.renderedKey = key;
      this.buildWorkspace();
    }
    this.applyBusyState();
  }

  buildWorkspace() {
    this.container.replaceChildren();
    this.entries = [];

    const selectorSection = document.createElement("section");
    selectorSection.className = "trigger-editor-section reference-editor-selector";
    const selectorHost = document.createElement("div");
    selectorSection.append(selectorHost);
    this.slotForm = new CommandForm(selectorHost, this.catalog);
    this.slotForm.render(this.definition("reference-query"));
    selectorHost.querySelector?.('[data-field="slot"]')?.addEventListener("change", () => {
      this.readStatus.textContent = "";
      this.buildActionSections();
      this.applyBusyState();
    });

    this.readStatus = document.createElement("output");
    this.readStatus.className = "muted compact-note";
    this.actionsHost = document.createElement("div");
    this.actionsHost.className = "trigger-editor-sections";
    this.container.append(selectorSection, this.readStatus, this.actionsHost);
    this.buildActionSections();
  }

  actionDefinition(id) {
    const command = this.definition(id);
    if (!command) return null;
    const presentation = { ...command.presentation };
    presentation.query_fields = (presentation.query_fields || []).filter(
      (name) => name !== "slot",
    );
    if (id === "reference-display") {
      presentation.readback_fields = {
        ...(presentation.readback_fields || {}),
        enabled: "displayed",
      };
    }
    return {
      ...command,
      fields: this.catalog.fieldsFor(command).filter((field) => field.name !== "slot"),
      presentation,
    };
  }

  buildActionSections() {
    this.entries = [];
    this.actionsHost.replaceChildren();
    const save = this.buildActionEntry("reference-save", true);
    if (save) {
      const section = document.createElement("section");
      section.className = "trigger-editor-section";
      this.appendActionHeading(section, save.command);
      section.append(save.formHost, save.button);
      this.actionsHost.append(section);
      this.entries.push(save.entry);
    }

    const management = document.createElement("section");
    management.className = "trigger-editor-section";
    for (const id of REFERENCE_MANAGEMENT_ACTIONS) {
      const action = this.buildActionEntry(id, false);
      if (!action) continue;
      const control = document.createElement("div");
      control.className = "reference-editor-control";
      this.appendActionHeading(control, action.command);
      if (action.formHost) control.append(action.formHost);
      control.append(action.button);
      management.append(control);
      this.entries.push(action.entry);
    }
    if (management.children.length) this.actionsHost.append(management);
  }

  appendActionHeading(container, command) {
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = this.catalog.commandLabel(command);
    container.append(heading);
  }

  buildActionEntry(id, isSaveWorkflow) {
    const command = this.actionDefinition(id);
    if (!command || !this.catalog.supported(command)) return null;

    let form = null;
    let formHost = null;
    if (command.fields.length) {
      formHost = document.createElement("div");
      form = new CommandForm(formHost, this.catalog);
      form.render(command);
    }
    const button = document.createElement("button");
    button.type = "button";
    const style = isSaveWorkflow ? "primary" : id === "reference-clear" ? "danger" : "secondary";
    button.className = `${style} trigger-editor-action`;
    button.textContent = isSaveWorkflow
      ? translate("reference.editor.saveAndDisplay")
      : translate(
          command.presentation.kind === "setting"
            ? "actions.apply"
            : `actions.${command.presentation.action}`,
        );
    const entry = { id, form, button, kind: command.presentation.kind };
    button.addEventListener("click", () => void (
      isSaveWorkflow ? this.saveAndDisplay(entry) : this.submit(entry)
    ));
    return { command, entry, formHost, button };
  }

  selectedSlot() {
    const values = this.slotForm?.values();
    return values?.slot;
  }

  async readCurrentState() {
    const slot = this.selectedSlot();
    if (slot === null || slot === undefined) return null;
    const requestedKey = `${this.currentKey()}|${slot}`;
    const job = await this.hooks.executeCommand(
      "reference-query",
      { slot },
      { intent: "readback" },
    );
    if (`${this.currentKey()}|${this.selectedSlot()}` !== requestedKey) return job;
    if (job?.status !== "completed") {
      this.readStatus.textContent = translate("reference.editor.readFailed");
      return job;
    }
    for (const entry of this.entries) {
      if (["reference-display", "reference-label"].includes(entry.id)) {
        entry.form?.syncResult(job, true);
      }
    }
    this.readStatus.textContent = translate("reference.editor.currentLoaded");
    return job;
  }

  async refresh() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return null;
    this.setBusy(true);
    try {
      return await this.readCurrentState();
    } finally {
      this.setBusy(false);
    }
  }

  async submit(entry) {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return null;
    const slot = this.selectedSlot();
    const values = entry.form ? entry.form.values() : {};
    if (slot === null || slot === undefined || values === null) return null;
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        entry.id,
        { ...values, slot },
        { intent: entry.kind === "setting" ? "apply" : "command" },
      );
      if (job?.status === "completed") {
        entry.form?.clearDirty();
        await this.readCurrentState();
      }
      return job;
    } finally {
      this.setBusy(false);
    }
  }

  async saveAndDisplay(entry) {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return null;
    const slot = this.selectedSlot();
    const values = entry.form?.values();
    if (slot === null || slot === undefined || values === null) return null;
    this.setBusy(true);
    try {
      const saveJob = await this.hooks.executeCommand(
        "reference-save",
        { ...values, slot },
        { intent: "command" },
      );
      if (saveJob?.status !== "completed") return saveJob;
      entry.form.clearDirty();

      const displayJob = await this.hooks.executeCommand(
        "reference-display",
        { action: "set", slot, enabled: true },
        { intent: "apply" },
      );
      if (displayJob?.status !== "completed") return displayJob;
      await this.readCurrentState();
      return displayJob;
    } finally {
      this.setBusy(false);
    }
  }

  setBusy(value) {
    this.busy = value;
    this.applyBusyState();
  }

  applyBusyState() {
    const disabled = this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable();
    this.refreshButton.disabled = disabled;
    this.slotForm?.setDisabled(disabled);
    for (const entry of this.entries) {
      entry.button.disabled = disabled;
      entry.form?.setDisabled(disabled);
    }
  }
}
