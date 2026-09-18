import { hasTranslation, translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

const SERIAL_SEARCH_PREFIX = "serial-search-";

export function buildBusOptions(maxBus) {
  const limit = Math.max(0, Math.floor(Number(maxBus) || 0));
  return Array.from({ length: limit }, (_item, index) => index + 1);
}

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

function enumLabel(value, optionLabel = null) {
  const scopedKey = optionLabel ? `enum.${optionLabel}.${String(value)}` : null;
  if (scopedKey && hasTranslation(scopedKey)) return translate(scopedKey);
  const key = `enum.${String(value)}`;
  return hasTranslation(key) ? translate(key) : String(value);
}

function enabledLabel(value) {
  if (value === undefined || value === null) return "-";
  return translate(value ? "status.enabled" : "status.disabled");
}

export class SearchEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.epoch = 0;
    this.stateKey = null;
    this.renderedKey = null;
    this.pendingRefresh = false;
    this.pendingPresentation = false;
    this.entry = null;
    this.readouts = {};
    this.bus = 1;
    this.maxBus = 0;
    this.buildDom();
  }

  buildDom() {
    this.refreshButton?.remove?.();
    this.entry?.button.remove?.();
    this.entry = null;
    this.container.replaceChildren();
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary search-editor-refresh";
    this.refreshButton.textContent = translate("search.editor.read");
    this.refreshButton.addEventListener("click", () => {
      this.scheduleRefresh(true);
    });
    if (this.hooks.headerActions) {
      this.refreshButton.hidden = true;
      this.hooks.headerActions.append(this.refreshButton);
    } else {
      this.container.append(this.refreshButton);
    }
    this.bodyHost = document.createElement("div");
    this.bodyHost.className = "search-editor-sections";
    this.container.append(this.bodyHost);
    this.busSelect = null;
  }

  commandById(id) {
    return this.catalog.commands.find((command) => command.id === id) || null;
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "search" ? selected : null;
  }

  isSerialCommand(definition) {
    return (definition?.id || "").startsWith(SERIAL_SEARCH_PREFIX);
  }

  serialBusMaximum(definition) {
    const fields = this.catalog.fieldsFor?.(definition) ?? definition?.fields ?? [];
    const busField = fields.find((field) => field?.name === "bus");
    return Math.max(0, Number(busField?.maximum) || 0);
  }

  normalizeSerialBus(definition) {
    this.maxBus = this.serialBusMaximum(definition);
    if (this.bus < 1 || this.bus > this.maxBus) this.bus = 1;
  }

  currentStateKey() {
    const selected = this.selectedDefinition();
    const bus = selected && this.isSerialCommand(selected) ? this.bus : "";
    return [
      this.hooks.contextKey(),
      selected?.id || "",
      String(bus),
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
    if (this.isSerialCommand(definition)) {
      this.normalizeSerialBus(definition);
    }
    const key = this.currentStateKey();
    if (!force && key === this.stateKey) {
      this.applyBusyState();
      return;
    }
    this.stateKey = key;
    if (this.renderedKey !== key) this.rebuildSections(definition);
    this.applyBusyState();
    if (!read || !this.hooks.isAvailable()) return;
    this.setBusy(true);
    try {
      await this.readActiveView();
    } finally {
      this.setBusy(false);
    }
  }

  clearSections() {
    this.renderedKey = null;
    this.entry?.button.remove?.();
    this.entry = null;
    this.readouts = {};
    this.busSelect = null;
    this.bodyHost.replaceChildren();
    this.refreshButton.disabled = true;
  }

  rebuildSections(definition) {
    this.epoch += 1;
    this.renderedKey = this.currentStateKey();
    this.entry?.button.remove?.();
    this.entry = null;
    this.readouts = {};
    this.busSelect = null;
    this.bodyHost.replaceChildren();
    // Capability-unsupported selections render their own unavailable state
    // instead of controls. Nothing is read and nothing can be applied.
    if (!this.catalog.supported(definition)) {
      if (definition.id === "search-event") {
        this.buildUnavailableNote("search.editor.eventUnavailable");
      } else if (this.isSerialCommand(definition)) {
        this.buildUnavailableNote("search.editor.serialUnavailable");
      }
      return;
    }
    if (definition.id === "search-count") {
      this.buildCountView();
      return;
    }
    if (this.isSerialCommand(definition)) {
      this.buildSerialView(definition);
      return;
    }
    this.buildSettingSection(definition, false);
  }

  buildSerialView(definition) {
    this.normalizeSerialBus(definition);
    if (this.maxBus < 1) {
      this.buildUnavailableNote("search.editor.serialUnavailable");
      return;
    }
    const statusRow = document.createElement("div");
    statusRow.className = "search-editor-row search-editor-status-row";
    statusRow.append(
      this.labeledOutput("command.search-state", "state"),
      this.labeledOutput("command.search-mode", "mode"),
    );
    this.bodyHost.append(statusRow);

    const busRow = document.createElement("div");
    busRow.className = "search-editor-row";
    this.busSelect = document.createElement("select");
    this.busSelect.addEventListener("change", () => {
      this.selectBus(this.busSelect.value);
    });
    busRow.append(this.labeledField("field.bus", this.busSelect, "search.editor.busHelp"));
    this.bodyHost.append(busRow);
    this.renderOptions(
      this.busSelect,
      buildBusOptions(this.maxBus).map((value) => ({
        value: String(value),
        label: String(value),
      })),
      this.bus,
    );

    this.buildSettingSection(this.criteriaDefinition(definition), true);
  }

  criteriaDefinition(command) {
    return {
      ...command,
      fields: this.catalog.fieldsFor(command).filter((field) => field.name !== "bus"),
    };
  }

  buildSettingSection(command, isSerial) {
    const section = document.createElement("section");
    section.className = "search-editor-section";
    const formContainer = document.createElement("div");
    formContainer.className = "command-form";
    const applyButton = document.createElement("button");
    applyButton.type = "button";
    applyButton.className = "primary search-editor-action";
    applyButton.textContent = translate("actions.apply");
    section.append(formContainer);
    if (this.hooks.headerActions) {
      this.hooks.headerActions.append(applyButton);
    } else {
      section.append(applyButton);
    }
    this.bodyHost.append(section);
    const form = new CommandForm(formContainer, this.catalog);
    form.render(command, {});
    const entry = {
      id: command.id,
      form,
      button: applyButton,
      epoch: this.epoch,
      serial: isSerial,
    };
    applyButton.addEventListener("click", () => {
      void this.submit(entry);
    });
    const fields = this.catalog.fieldsFor?.(command) ?? command.fields ?? [];
    const editable = fields.filter(
      (field) => field?.name !== command.presentation?.action_field,
    );
    if (!isSerial && editable.length === 1) {
      section.className += " search-editor-single";
    }
    section.hidden = fields.length === 0;
    formContainer.hidden = fields.length === 0;
    this.entry = entry;
    return entry;
  }

  buildCountView() {
    const output = document.createElement("output");
    output.className = "readonly-value";
    this.bodyHost.append(output);
    this.readouts.count = output;
  }

  buildUnavailableNote(messageKey) {
    const note = document.createElement("p");
    note.className = "muted compact-note";
    note.textContent = translate(messageKey);
    this.bodyHost.append(note);
    return note;
  }

  labeledField(labelKey, input, helpKey = null) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const label = document.createElement("span");
    label.textContent = translate(labelKey);
    wrapper.append(label, input);
    if (helpKey) {
      const help = document.createElement("small");
      help.className = "field-help";
      help.textContent = translate(helpKey);
      wrapper.append(help);
    }
    return wrapper;
  }

  labeledOutput(labelKey, name) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const label = document.createElement("span");
    label.textContent = translate(labelKey);
    const output = document.createElement("output");
    output.className = "readonly-value";
    wrapper.append(label, output);
    this.readouts[name] = output;
    return wrapper;
  }

  renderOptions(select, options, selectedValue) {
    select.replaceChildren();
    options.forEach((option) => {
      select.append(new Option(option.label, option.value));
    });
    if (selectedValue !== null && selectedValue !== undefined) {
      select.value = String(selectedValue);
    }
  }

  selectBus(value) {
    if (this.busy) return;
    const next = Number(value);
    if (!Number.isInteger(next) || next === this.bus) return;
    if (!buildBusOptions(this.maxBus).includes(next)) return;
    this.bus = next;
    this.schedulePresentation();
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

  async readSerialEntry(entry) {
    const parameters = { ...(entry.form.queryValues() || {}), bus: this.bus };
    const job = await this.hooks.executeCommand(
      entry.id,
      parameters,
      { intent: "readback" },
    );
    if (job?.status !== "completed") return;
    entry.form.syncResult(job, true);
    this.syncSerialStatus(job);
  }

  syncSerialStatus(job) {
    const enabled = resultValue(job?.result, "search_enabled");
    if (this.readouts.state) {
      this.readouts.state.textContent = enabledLabel(enabled);
    }

    const mode = resultValue(job?.result, "search_mode");
    if (this.readouts.mode) {
      this.readouts.mode.textContent = mode ? enumLabel(mode, "search-mode") : "-";
    }
  }

  async readCount() {
    const command = this.commandById("search-count");
    if (!command || !this.catalog.supported(command) || !this.readouts.count) return;
    const job = await this.hooks.executeCommand("search-count", {}, {});
    if (job?.status !== "completed") return;
    const count = resultValue(job.result, "count");
    this.readouts.count.textContent = count === undefined ? "-" : String(count);
  }

  async readActiveView() {
    const definition = this.selectedDefinition();
    if (!definition) return;
    if (definition.id === "search-count") {
      await this.readCount();
      return;
    }
    const entry = this.entry;
    if (!entry || entry.epoch !== this.epoch) return;
    if (entry.serial) await this.readSerialEntry(entry);
    else await this.readEntry(entry);
  }

  async submit(entry) {
    if (!entry || entry !== this.entry || this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    const submissionKey = this.currentStateKey();
    const epoch = this.epoch;
    const values = entry.form.values();
    if (values === null) return;
    const parameters = entry.serial
      ? { ...values, bus: this.bus }
      : values;
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        entry.id,
        parameters,
        { intent: "apply" },
      );
      if (
        job?.status !== "completed"
        || entry !== this.entry
        || entry.epoch !== epoch
        || submissionKey !== this.currentStateKey()
      ) {
        return;
      }
      entry.form.clearDirty();
      entry.form.syncResult(job, false);
      if (entry.serial) this.syncSerialStatus(job);
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
    const unavailable = !this.hooks.isAvailable();
    const disabled = this.busy || this.hooks.isExecutionBusy?.() || unavailable;
    this.refreshButton.disabled = disabled;
    if (this.entry) {
      this.entry.button.disabled = disabled;
      this.entry.form?.setDisabled(disabled);
    }
    if (this.busSelect) {
      this.busSelect.disabled = disabled;
    }
  }
}
