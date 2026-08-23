import { hasTranslation, translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

const SERIAL_PROTOCOLS = ["uart", "i2c", "spi", "can"];
const SERIAL_SEARCH_PREFIX = "serial-search-";

export function serialSearchCommand(protocol) {
  return SERIAL_PROTOCOLS.includes(protocol)
    ? `${SERIAL_SEARCH_PREFIX}${protocol}`
    : null;
}

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

function enumLabel(value) {
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
    this.entries = [];
    this.readouts = {};
    this.bus = 1;
    this.maxBus = 0;
    this.protocols = [];
    this.protocol = null;
    this.selectedSerialCommandId = null;
    this.buildDom();
  }

  buildDom() {
    this.container.replaceChildren();
    this.headRow = document.createElement("div");
    this.headRow.className = "search-editor-head";
    this.groupHeading = document.createElement("strong");
    this.groupHeading.className = "search-editor-heading";
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary search-editor-refresh";
    this.refreshButton.textContent = translate("actions.refresh");
    this.refreshButton.addEventListener("click", () => {
      this.scheduleRefresh(true);
    });
    this.headRow.append(this.groupHeading, this.refreshButton);
    this.bodyHost = document.createElement("div");
    this.bodyHost.className = "search-editor-sections";
    this.container.append(this.headRow, this.bodyHost);
    this.busSelect = null;
    this.protocolSelect = null;
  }

  commandById(id) {
    return this.catalog.commands.find((command) => command.id === id) || null;
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "search" ? selected : null;
  }

  currentStateKey() {
    const selected = this.selectedDefinition();
    return [
      this.hooks.contextKey(),
      String(this.hooks.isAvailable()),
      selected?.id || "",
      selected?.group || "",
      String(this.bus),
      this.protocol || "",
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

  refreshSerialContext(definition) {
    if (!definition || definition.group !== "serial") {
      this.protocols = [];
      this.maxBus = 0;
      this.protocol = null;
      this.selectedSerialCommandId = null;
      return;
    }
    const supported = [];
    let maxBus = 0;
    for (const protocol of SERIAL_PROTOCOLS) {
      const command = this.commandById(serialSearchCommand(protocol));
      if (!command || !this.catalog.supported(command)) continue;
      supported.push(protocol);
      const busField = this.catalog
        .fieldsFor(command)
        .find((field) => field.name === "bus");
      maxBus = Math.max(maxBus, Number(busField?.maximum) || 0);
    }
    this.protocols = supported;
    this.maxBus = maxBus;
    if (this.bus < 1 || this.bus > maxBus) this.bus = 1;
    const derived = definition.id.slice(SERIAL_SEARCH_PREFIX.length);
    if (
      this.selectedSerialCommandId !== definition.id
      || !supported.includes(this.protocol)
    ) {
      this.protocol = derived;
    }
    this.selectedSerialCommandId = definition.id;
  }

  async refresh(force = false) {
    if (this.busy) {
      if (force || this.currentStateKey() !== this.stateKey) {
        this.pendingRefresh = true;
      }
      return;
    }
    const definition = this.selectedDefinition();
    if (!definition) {
      this.stateKey = null;
      this.clearView();
      return;
    }
    this.refreshSerialContext(definition);
    const key = this.currentStateKey();

    // Capability-unsupported selections stay presentable: the view renders
    // its own unavailable state with disabled controls instead of going
    // blank. Runtime unavailability (mode, resource, identity) keeps
    // clearing the view.
    if (!this.catalog.supported(definition)) {
      if (!force && key === this.stateKey) return;
      this.stateKey = key;
      this.groupHeading.textContent = this.catalog.groupLabel(definition.group);
      if (this.renderedKey !== key) this.rebuildView(definition);
      this.applyBusyState();
      return;
    }

    if (!this.hooks.isAvailable()) {
      this.stateKey = null;
      this.clearView();
      return;
    }
    if (!force && key === this.stateKey) return;
    this.setBusy(true);
    try {
      this.stateKey = key;
      this.groupHeading.textContent = this.catalog.groupLabel(definition.group);
      if (this.renderedKey !== key) this.rebuildView(definition);
      this.applyBusyState();
      await this.readActiveView();
    } finally {
      this.setBusy(false);
    }
  }

  clearView() {
    this.renderedKey = null;
    this.entries = [];
    this.readouts = {};
    this.busSelect = null;
    this.protocolSelect = null;
    this.bodyHost.replaceChildren();
    this.groupHeading.textContent = "";
    this.refreshButton.disabled = true;
  }

  rebuildView(definition) {
    this.epoch += 1;
    this.renderedKey = this.currentStateKey();
    this.entries = [];
    this.readouts = {};
    this.busSelect = null;
    this.protocolSelect = null;
    this.bodyHost.replaceChildren();
    if (definition.group === "basic") this.buildBasicView();
    else if (definition.group === "event") this.buildEventView();
    else if (definition.group === "serial") this.buildSerialView();
  }

  buildBasicView() {
    for (const id of ["search-state", "search-mode"]) {
      const command = this.commandById(id);
      if (command && this.catalog.supported(command)) {
        this.buildSettingSection(command, false);
      }
    }
    const countCommand = this.commandById("search-count");
    if (countCommand && this.catalog.supported(countCommand)) {
      this.readouts.count = this.buildReadonlyRow(countCommand);
    }
  }

  buildEventView() {
    const command = this.commandById("search-event");
    if (command && this.catalog.supported(command)) {
      this.buildSettingSection(command, false);
    } else {
      this.buildUnavailableNote("search.editor.eventUnavailable");
    }
  }

  buildSerialView() {
    if (!this.protocols.length || this.maxBus < 1) {
      this.buildUnavailableNote("search.editor.serialUnavailable");
      return;
    }
    const statusRow = document.createElement("div");
    statusRow.className = "search-editor-row";
    statusRow.append(
      this.labeledOutput("command.search-state", "state"),
      this.labeledOutput("command.search-mode", "mode"),
    );
    this.bodyHost.append(statusRow);

    const selectorRow = document.createElement("div");
    selectorRow.className = "search-editor-row";
    this.busSelect = document.createElement("select");
    this.busSelect.addEventListener("change", () => {
      this.selectBus(this.busSelect.value);
    });
    this.protocolSelect = document.createElement("select");
    this.protocolSelect.addEventListener("change", () => {
      this.selectProtocol(this.protocolSelect.value);
    });
    selectorRow.append(
      this.labeledField("field.bus", this.busSelect),
      this.labeledField("search.editor.protocol", this.protocolSelect),
    );
    this.bodyHost.append(selectorRow);

    this.renderOptions(
      this.busSelect,
      buildBusOptions(this.maxBus).map((value) => ({
        value: String(value),
        label: String(value),
      })),
      this.bus,
    );
    this.renderOptions(
      this.protocolSelect,
      this.protocols.map((protocol) => ({
        value: protocol,
        label: protocol.toUpperCase(),
      })),
      this.protocol,
    );

    const command = this.commandById(serialSearchCommand(this.protocol));
    if (command) this.buildSettingSection(this.criteriaDefinition(command), true);
  }

  criteriaDefinition(command) {
    return {
      ...command,
      fields: this.catalog.fieldsFor(command).filter((field) => field.name !== "bus"),
    };
  }

  buildSettingSection(command, isSerialCriteria) {
    const section = document.createElement("section");
    section.className = "search-editor-section";
    const heading = document.createElement("strong");
    heading.className = "search-editor-heading";
    heading.textContent = this.catalog.commandLabel(command);
    const formContainer = document.createElement("div");
    const applyButton = document.createElement("button");
    applyButton.type = "button";
    applyButton.className = "secondary search-editor-action";
    applyButton.textContent = translate("actions.apply");
    section.append(heading, formContainer, applyButton);
    this.bodyHost.append(section);
    const form = new CommandForm(formContainer, this.catalog);
    form.render(command, {});
    const entry = {
      id: command.id,
      view: isSerialCriteria ? "serial" : command.group,
      form,
      button: applyButton,
    };
    applyButton.addEventListener("click", () => {
      void this.submit(entry);
    });
    this.entries.push(entry);
    return entry;
  }

  buildReadonlyRow(command) {
    const section = document.createElement("section");
    section.className = "search-editor-section";
    const heading = document.createElement("strong");
    heading.className = "search-editor-heading";
    heading.textContent = this.catalog.commandLabel(command);
    const output = document.createElement("output");
    output.className = "readonly-value";
    section.append(heading, output);
    this.bodyHost.append(section);
    return output;
  }

  buildUnavailableNote(messageKey) {
    const note = document.createElement("p");
    note.className = "muted compact-note";
    note.textContent = translate(messageKey);
    this.bodyHost.append(note);
    return note;
  }

  labeledField(labelKey, input) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const label = document.createElement("span");
    label.textContent = translate(labelKey);
    wrapper.append(label, input);
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
    this.scheduleRefresh();
  }

  selectProtocol(value) {
    if (this.busy || !this.protocols.includes(value) || value === this.protocol) return;
    this.protocol = value;
    this.scheduleRefresh();
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
    const payload = job.result?.result ?? job.result ?? {};
    if (this.readouts.state) {
      this.readouts.state.textContent = enabledLabel(payload.search_enabled);
    }
    if (this.readouts.mode) {
      const mode = payload.search_mode;
      this.readouts.mode.textContent = mode ? enumLabel(mode) : "-";
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
    const epoch = this.epoch;
    if (definition.group === "serial") {
      for (const entry of this.entries) {
        if (epoch !== this.epoch) return;
        await this.readSerialEntry(entry);
      }
      return;
    }
    for (const entry of this.entries) {
      if (epoch !== this.epoch) return;
      await this.readEntry(entry);
    }
    if (definition.group === "basic") await this.readCount();
  }

  async submit(entry) {
    if (this.busy || !this.hooks.isAvailable()) return;
    if (!this.entries.includes(entry)) return;
    const values = entry.form.values();
    if (values === null) return;
    const parameters = entry.view === "serial"
      ? { ...values, bus: this.bus }
      : values;
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        entry.id,
        parameters,
        { intent: "apply" },
      );
      if (job?.status !== "completed" || !this.entries.includes(entry)) return;
      entry.form.clearDirty();
      entry.form.syncResult(job, false);
      if (entry.view === "serial") {
        await this.hooks.executeCommand("search-state", {}, { intent: "readback" });
        await this.hooks.executeCommand("search-mode", {}, { intent: "readback" });
        await this.readSerialEntry(entry);
      } else {
        this.pendingRefresh = true;
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
      this.scheduleRefresh(true);
    }
  }

  applyBusyState() {
    const unavailable = !this.hooks.isAvailable();
    this.refreshButton.disabled = this.busy || unavailable;
    for (const entry of this.entries) {
      entry.button.disabled = this.busy;
      entry.form?.setDisabled(this.busy);
    }
    if (this.busSelect) {
      this.busSelect.disabled = this.busy || unavailable;
    }
    if (this.protocolSelect) {
      this.protocolSelect.disabled = this.busy || unavailable;
    }
  }
}
