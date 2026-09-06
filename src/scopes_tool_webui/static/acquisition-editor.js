import { CommandForm } from "/static/command-form.js";

const INSTANT_CONTROL_COMMANDS = ["run", "single", "stop-acquisition", "force-trigger"];

export class AcquisitionEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.renderedKey = null;
    this.controlButtons = [];
    this.singleWaitForm = null;
    this.singleWaitButton = null;
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "acquisition" ? selected : null;
  }

  currentKey() {
    const selected = this.selectedDefinition();
    return `${this.hooks.contextKey()}|${selected?.id || ""}`;
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    this.renderedKey = null;
    this.schedulePresentation();
  }

  present() {
    const definition = this.selectedDefinition();
    if (!definition) {
      this.renderedKey = null;
      this.controlButtons = [];
      this.singleWaitForm = null;
      this.singleWaitButton = null;
      this.container.replaceChildren();
      this.applyBusyState();
      return;
    }
    const key = this.currentKey();
    if (key === this.renderedKey) {
      this.applyBusyState();
      return;
    }
    this.renderedKey = key;
    this.render(definition);
    this.applyBusyState();
  }

  definition(commandId) {
    return this.catalog.commands.find((command) => command.id === commandId) || null;
  }

  render(definition) {
    this.controlButtons = [];
    this.singleWaitForm = null;
    this.singleWaitButton = null;
    this.container.replaceChildren(
      this.buildControlSection(definition),
      this.buildSingleWaitSection(),
    );
  }

  buildSection(title) {
    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = title;
    section.append(heading);
    return section;
  }

  buildControlSection(definition) {
    const section = this.buildSection(this.catalog.commandLabel(definition));
    const buttons = document.createElement("div");
    buttons.className = "measurement-front-panel-buttons";
    for (const commandId of INSTANT_CONTROL_COMMANDS) {
      const command = this.definition(commandId);
      if (!command) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = this.catalog.commandLabel(command);
      button.addEventListener("click", () => {
        void this.runInstantControl(commandId);
      });
      buttons.append(button);
      this.controlButtons.push({ id: commandId, button });
    }
    section.append(buttons);
    return section;
  }

  buildSingleWaitSection() {
    const command = this.definition("single-wait");
    const section = this.buildSection(this.catalog.commandLabel(command));
    const formContainer = document.createElement("div");
    formContainer.className = "command-form";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary trigger-editor-action";
    button.textContent = this.catalog.commandLabel(command);
    button.addEventListener("click", () => {
      void this.submitSingleWait();
    });
    section.append(formContainer, button);
    this.singleWaitButton = button;
    if (command) {
      const form = new CommandForm(formContainer, this.catalog);
      form.render(command, {});
      this.singleWaitForm = form;
    }
    return section;
  }

  async runInstantControl(commandId) {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    if (!this.hooks.isCommandAvailable?.(commandId)) return;
    await this.hooks.executeCommand(commandId, {});
  }

  async submitSingleWait() {
    if (!this.singleWaitForm) return;
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    if (!this.hooks.isCommandAvailable?.("single-wait")) return;
    const parameters = this.singleWaitForm.values();
    if (parameters === null) return;
    this.setBusy(true);
    try {
      await this.hooks.executeCommand("single-wait", parameters, { intent: "command" });
    } finally {
      this.setBusy(false);
    }
  }

  setBusy(value) {
    this.busy = value;
    this.applyBusyState();
  }

  applyBusyState() {
    const unavailable = !this.hooks.isAvailable();
    const busy = this.busy || this.hooks.isExecutionBusy?.() || unavailable;
    for (const entry of this.controlButtons) {
      entry.button.disabled = busy || !this.hooks.isCommandAvailable?.(entry.id);
    }
    if (this.singleWaitButton) {
      this.singleWaitButton.disabled = busy || !this.hooks.isCommandAvailable?.("single-wait");
    }
    this.singleWaitForm?.setDisabled?.(busy);
  }
}
