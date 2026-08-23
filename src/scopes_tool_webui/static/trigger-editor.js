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
    this.entries = [];
    this.buildDom();
  }

  buildDom() {
    this.container.replaceChildren();
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
    this.sectionsHost = document.createElement("div");
    this.sectionsHost.className = "trigger-editor-sections";
    this.container.append(this.headRow, this.sectionsHost);
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "trigger" ? selected : null;
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
    const definition = this.selectedDefinition();
    if (!definition || !this.hooks.isAvailable()) {
      this.stateKey = null;
      this.clearSections();
      return;
    }
    const key = this.currentStateKey();
    if (!force && key === this.stateKey) return;
    this.stateKey = key;
    this.groupHeading.textContent = this.catalog.groupLabel(definition.group);
    if (this.renderedKey !== key) this.rebuildSections(key);
    await this.readActiveGroup();
  }

  clearSections() {
    this.renderedKey = null;
    this.entries = [];
    this.sectionsHost.replaceChildren();
    this.groupHeading.textContent = "";
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
      if (command.editor !== "trigger" || command.group !== definition.group) continue;
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
    const formContainer = document.createElement("div");
    const actionButton = document.createElement("button");
    actionButton.type = "button";
    actionButton.className = "secondary trigger-editor-action";
    const kind = command.presentation?.kind || "command";
    const action = command.presentation?.action || "run";
    actionButton.textContent = translate(
      kind === "setting" ? "actions.apply" : `actions.${action}`,
    );
    section.append(heading, formContainer, actionButton);
    this.sectionsHost.append(section);
    const form = new CommandForm(formContainer, this.catalog);
    form.render(command, {});
    const entry = { id: command.id, kind, action, form, button: actionButton, epoch };
    actionButton.addEventListener("click", () => {
      void this.submit(entry);
    });
    return entry;
  }

  async readActiveGroup() {
    const epoch = this.epoch;
    for (const entry of this.entries) {
      if (epoch !== this.epoch) return;
      if (entry.kind !== "setting") continue;
      const parameters = entry.form.queryValues();
      if (parameters === null) continue;
      const job = await this.hooks.executeCommand(
        entry.id,
        parameters,
        { intent: "readback" },
      );
      if (epoch !== this.epoch) return;
      if (job?.status === "completed") entry.form.syncResult(job, true);
    }
  }

  async submit(entry) {
    if (this.busy || !this.hooks.isAvailable()) return;
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
      if (isSetting && job?.status === "completed" && entry.epoch === this.epoch) {
        entry.form.clearDirty();
        entry.form.syncResult(job, false);
      }
    } finally {
      this.setBusy(false);
    }
  }

  setBusy(value) {
    this.busy = value;
    this.refreshButton.disabled = value || !this.hooks.isAvailable();
    for (const entry of this.entries) {
      entry.button.disabled = value;
      entry.form.setDisabled(value);
    }
  }
}
