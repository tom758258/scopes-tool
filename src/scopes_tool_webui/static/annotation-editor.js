import { translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

const STATE_ROWS = [
  ["slot", "slot"],
  ["enabled", "enabled"],
  ["text", "text"],
  ["color", "color"],
  ["background", "background"],
  ["x", "x"],
  ["y", "y"],
];

export class AnnotationEditor {
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
    this.headRow.append(this.groupHeading);
    if (this.hooks.headerActions) {
      this.refreshButton.hidden = true;
      this.hooks.headerActions.append(this.refreshButton);
    } else {
      this.headRow.append(this.refreshButton);
    }
    this.sectionsHost = document.createElement("div");
    this.sectionsHost.className = "trigger-editor-sections";
    this.container.append(this.headRow, this.sectionsHost);
  }

  definition() {
    return this.catalog.commands.find((command) => command.id === "annotation") || null;
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "annotation" ? selected : null;
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
    this.groupHeading.textContent = this.catalog.groupLabel(definition.group);
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
    this.entry = null;
    this.sectionsHost.replaceChildren();
    this.groupHeading.textContent = "";
    this.refreshButton.disabled = true;
  }

  rebuildSections(key) {
    this.epoch += 1;
    const epoch = this.epoch;
    this.renderedKey = key;
    this.entry = null;
    this.sectionsHost.replaceChildren();
    const command = this.definition();
    if (!command || !this.catalog.supported(command)) return;
    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = this.catalog.commandLabel(command);
    const formContainer = document.createElement("div");
    const actionButton = document.createElement("button");
    actionButton.type = "button";
    actionButton.className = "secondary trigger-editor-action";
    actionButton.textContent = translate("actions.apply");
    const statePanel = document.createElement("div");
    statePanel.className = "annotation-editor-state";
    section.append(heading, formContainer, actionButton, statePanel);
    this.sectionsHost.append(section);
    const form = new CommandForm(formContainer, this.catalog);
    this.entry = { form, button: actionButton, panel: statePanel, epoch };
    form.render(command, {});
    actionButton.addEventListener("click", () => {
      void this.submit();
    });
  }

  statePayload(job) {
    const payload = job?.result?.result !== undefined ? job.result.result : job?.result;
    return payload?.annotation || null;
  }

  currentSlot() {
    const raw = this.entry?.form?.container?.querySelector?.('[data-field="slot"]')?.value;
    const slot = Number.parseInt(raw, 10);
    return Number.isInteger(slot) && slot >= 1 ? slot : 1;
  }

  async readState() {
    if (!this.entry || this.entry.epoch !== this.epoch) return;
    const job = await this.hooks.executeCommand(
      "annotation",
      { action: "query", slot: this.currentSlot() },
      { intent: "readback" },
    );
    if (job?.status === "completed" && this.entry.epoch === this.epoch) {
      this.renderState(this.statePayload(job));
    }
  }

  renderState(state) {
    const { panel } = this.entry;
    panel.replaceChildren();
    if (!state) return;
    for (const [resultKey, labelSuffix] of STATE_ROWS) {
      const value = state[resultKey];
      if (value === undefined || value === null) continue;
      const row = document.createElement("div");
      row.className = "annotation-editor-state-row";
      const label = document.createElement("span");
      label.textContent = translate(`annotation.state.${labelSuffix}`);
      const shown = document.createElement("span");
      shown.textContent = typeof value === "boolean" ? translate(value ? "enum.enable" : "enum.disable") : String(value);
      row.append(label, shown);
      panel.append(row);
    }
  }

  async submit() {
    const entry = this.entry;
    if (!entry || this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    const submissionKey = this.currentStateKey();
    const parameters = entry.form.values();
    if (parameters === null) return;
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        "annotation",
        parameters,
        { intent: "apply" },
      );
      if (
        job?.status === "completed"
        && entry.epoch === this.epoch
        && submissionKey === this.currentStateKey()
      ) {
        entry.form.clearDirty();
        this.renderState(this.statePayload(job));
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
