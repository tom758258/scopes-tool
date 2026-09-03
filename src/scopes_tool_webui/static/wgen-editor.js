import { translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

const COMMAND_IDS = [
  "wgen-query",
  "wgen-output",
  "wgen-function",
  "wgen-frequency",
  "wgen-voltage",
  "wgen-offset",
  "wgen-load",
];

// Aggregate wgen-query state key -> owning section command id + display label key.
const STATE_MAPPING = [
  ["enabled", "wgen-output", "output"],
  ["function", "wgen-function", "function"],
  ["frequency_hz", "wgen-frequency", "frequency"],
  ["amplitude_volts", "wgen-voltage", "amplitude"],
  ["offset_volts", "wgen-offset", "offset"],
  ["load", "wgen-load", "load"],
];

export class WgenEditor {
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

  definition(id) {
    return this.catalog.commands.find((command) => command.id === id) || null;
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "wgen" ? selected : null;
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
    for (const id of COMMAND_IDS) {
      const command = this.definition(id);
      if (!command || !this.catalog.supported(command)) continue;
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
    const statePanel = document.createElement("div");
    statePanel.className = "wgen-editor-state";
    section.append(heading, formContainer, actionButton, statePanel);
    this.sectionsHost.append(section);
    const form = new CommandForm(formContainer, this.catalog);
    const entry = { id: command.id, kind, form: null, button: actionButton, panel: statePanel, epoch };
    form.render(command, {});
    entry.form = form;
    actionButton.addEventListener("click", () => {
      void this.submit(entry);
    });
    return entry;
  }

  entryFor(id) {
    return this.entries.find((entry) => entry.id === id) || null;
  }

  async readState() {
    const epoch = this.epoch;
    const job = await this.hooks.executeCommand(
      "wgen-query",
      {},
      { intent: "readback" },
    );
    if (job?.status !== "completed" || epoch !== this.epoch) return;
    const payload = job?.result?.result !== undefined ? job.result.result : job?.result;
    const state = payload?.wgen || null;
    if (!state) return;
    this.renderAggregateState(state);
  }

  renderAggregateState(state) {
    for (const [resultKey, commandId, labelSuffix] of STATE_MAPPING) {
      const entry = this.entryFor(commandId);
      if (!entry || entry.epoch !== this.epoch) continue;
      const value = state[resultKey];
      entry.panel.replaceChildren();
      if (value === undefined || value === null) continue;
      const row = document.createElement("div");
      row.className = "wgen-editor-state-row";
      const label = document.createElement("span");
      label.textContent = translate(`wgen.state.${labelSuffix}`);
      const shown = document.createElement("span");
      shown.textContent = typeof value === "boolean"
        ? translate(value ? "enum.enable" : "enum.disable")
        : String(value);
      row.append(label, shown);
      entry.panel.append(row);
    }
  }

  setterValueFor(entryId, payload) {
    if (!payload) return undefined;
    switch (entryId) {
      case "wgen-output": return payload?.output?.enabled;
      case "wgen-function": return payload?.function?.function;
      case "wgen-frequency": return payload?.frequency?.frequency_hz;
      case "wgen-voltage": return payload?.voltage?.amplitude_volts;
      case "wgen-offset": return payload?.offset?.offset_volts;
      case "wgen-load": return payload?.load?.load;
      default: return undefined;
    }
  }

  renderSetterState(entry, payload) {
    const found = STATE_MAPPING.find(([, commandId]) => commandId === entry.id);
    if (!found) return;
    const value = this.setterValueFor(entry.id, payload);
    if (value === undefined || value === null) return;
    entry.panel.replaceChildren();
    const row = document.createElement("div");
    row.className = "wgen-editor-state-row";
    const label = document.createElement("span");
    label.textContent = translate(`wgen.state.${found[2]}`);
    const shown = document.createElement("span");
    shown.textContent = typeof value === "boolean"
      ? translate(value ? "enum.enable" : "enum.disable")
      : String(value);
    row.append(label, shown);
    entry.panel.append(row);
  }

  async submit(entry) {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
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
        job?.status === "completed"
        && entry.epoch === this.epoch
        && submissionKey === this.currentStateKey()
      ) {
        const payload = job?.result?.result !== undefined ? job.result.result : job?.result;
        if (isSetting) {
          entry.form.clearDirty();
          this.renderSetterState(entry, payload);
        } else if (entry.id === "wgen-query") {
          const state = payload?.wgen || null;
          if (state) this.renderAggregateState(state);
        }
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
    for (const entry of this.entries) {
      entry.button.disabled = disabled;
      entry.form?.setDisabled(disabled);
    }
  }
}
