import { CommandForm } from "/static/command-form.js";
import { translate } from "/static/i18n.js";

export class LabelVisibility {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.render(false);
  }

  render(visible) {
    this.container.replaceChildren();
    this.form = null;
    const command = this.catalog.commands.find((item) => item.id === "display-label");
    this.container.hidden = !visible || !command || !this.catalog.supported(command);
    if (this.container.hidden) return;
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = translate("labels.visibility");
    const note = document.createElement("p");
    note.className = "muted compact-note";
    note.textContent = translate("labels.shared");
    const host = document.createElement("div");
    this.form = new CommandForm(host, this.catalog);
    this.form.render(command);
    this.status = document.createElement("output");
    this.status.className = "muted compact-note";
    this.readButton = document.createElement("button");
    this.applyButton = document.createElement("button");
    for (const button of [this.readButton, this.applyButton]) {
      button.type = "button";
      button.className = "secondary trigger-editor-action";
    }
    this.readButton.textContent = translate("actions.readSettings");
    this.applyButton.textContent = translate("actions.apply");
    this.readButton.addEventListener("click", () => void this.run(false));
    this.applyButton.addEventListener("click", () => void this.run(true));
    this.container.append(heading, note, host, this.status, this.readButton, this.applyButton);
    this.applyBusyState();
  }

  async run(apply) {
    if (!this.form || this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return null;
    const form = this.form;
    const key = this.hooks.contextKey();
    const current = () => this.form === form && this.hooks.contextKey() === key;
    const parameters = apply ? form.values() : form.queryValues();
    if (parameters === null) return null;
    this.busy = true;
    this.applyBusyState();
    try {
      const job = await this.hooks.executeCommand(
        "display-label", parameters, { intent: apply ? "apply" : "readback" },
      );
      if (!current()) return job;
      if (job?.status === "completed") {
        if (apply) form.clearDirty();
        form.syncResult(job, true);
        this.status.textContent = "";
      } else if (!apply) {
        this.status.textContent = translate("labels.readFailed");
      }
      return job;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  applyBusyState(disabled = false) {
    if (!this.form) return;
    disabled ||= this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable();
    this.form.setDisabled(disabled);
    this.readButton.disabled = disabled;
    this.applyButton.disabled = disabled;
  }
}
