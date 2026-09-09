import { CommandForm } from "/static/command-form.js";
import { LabelVisibility } from "/static/label-visibility.js";
import { translate } from "/static/i18n.js";

export class ReferenceLabelsEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.renderedKey = null;
    this.entry = null;
    this.buildHeaderAction();
  }

  buildHeaderAction() {
    this.refreshButton?.remove?.();
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary reference-labels-editor-refresh";
    this.refreshButton.textContent = translate("reference-labels.editor.read");
    this.refreshButton.hidden = true;
    this.refreshButton.addEventListener("click", () => void this.refresh());
    this.hooks.headerActions?.append(this.refreshButton);
  }

  definition(id) {
    return this.catalog.commands.find((command) => command.id === id) || null;
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "reference-labels" ? selected : null;
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
      this.entry = null;
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
    this.entry = null;

    // Shared two-column row: slot selector (left) + label text (right).
    // Both hosts are plain grid items; the forms keep their own containers.
    this.topRow = document.createElement("div");
    this.topRow.className = "command-form";
    const selectorHost = document.createElement("div");
    this.slotForm = new CommandForm(selectorHost, this.catalog);
    this.slotForm.render(this.definition("reference-query"));
    selectorHost.querySelector?.('[data-field="slot"]')?.addEventListener("change", () => {
      this.readStatus.textContent = "";
      this.buildLabelSection();
      this.applyBusyState();
    });
    this.labelFieldHost = document.createElement("div");
    this.topRow.append(selectorHost, this.labelFieldHost);

    this.readStatus = document.createElement("output");
    this.readStatus.className = "muted compact-note";
    this.labelHost = document.createElement("div");
    this.labelHost.className = "trigger-editor-sections";
    this.container.append(this.topRow, this.readStatus, this.labelHost);
    this.buildLabelSection();
  }

  labelDefinition() {
    const command = this.definition("reference-label");
    if (!command) return null;
    const presentation = { ...command.presentation };
    presentation.query_fields = (presentation.query_fields || []).filter(
      (name) => name !== "slot",
    );
    return {
      ...command,
      fields: this.catalog.fieldsFor(command).filter((field) => field.name !== "slot"),
      presentation,
    };
  }

  buildLabelSection() {
    this.entry = null;
    this.labelVisibility = null;
    this.labelHost.replaceChildren();
    this.labelFieldHost.replaceChildren();
    const command = this.labelDefinition();
    if (command && this.catalog.supported(command)) {
      const section = document.createElement("section");
      section.className = "trigger-editor-section";
      this.appendActionHeading(section, command);
      const form = new CommandForm(this.labelFieldHost, this.catalog);
      form.render(command);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "primary trigger-editor-action";
      button.textContent = translate("actions.apply");
      const entry = { id: command.id, form, button, kind: command.presentation.kind };
      button.addEventListener("click", () => void this.submit(entry));
      section.append(button);
      this.labelHost.append(section);
      this.entry = entry;
    }

    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    this.labelHost.append(section);
    this.labelVisibility = new LabelVisibility(section, this.catalog, {
      ...this.hooks,
      contextKey: () => `${this.currentKey()}|${this.selectedSlot()}`,
    });
    this.labelVisibility.render(true);
  }

  appendActionHeading(container, command) {
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = this.catalog.commandLabel(command);
    container.append(heading);
    const description = this.catalog.description?.(command);
    if (description) {
      const note = document.createElement("p");
      note.className = "muted compact-note";
      note.textContent = description;
      container.append(note);
    }
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
      this.readStatus.textContent = translate("reference-labels.editor.readFailed");
      return job;
    }
    this.entry?.form?.syncResult(job, true);
    this.readStatus.textContent = translate("reference-labels.editor.currentLoaded");
    await this.labelVisibility?.run(false);
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

  setBusy(value) {
    this.busy = value;
    this.applyBusyState();
  }

  applyBusyState() {
    const disabled = this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable();
    this.refreshButton.disabled = disabled;
    this.slotForm?.setDisabled(disabled);
    if (this.entry) {
      this.entry.button.disabled = disabled;
      this.entry.form?.setDisabled(disabled);
    }
    this.labelVisibility?.applyBusyState(disabled);
  }
}
