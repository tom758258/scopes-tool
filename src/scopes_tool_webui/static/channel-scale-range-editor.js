import { hasTranslation, translate } from "/static/i18n.js";
import { formatEngineering } from "/static/live-data.js";

const SCALE_PRESETS = [
  { label: "1m", value: "0.001" },
  { label: "2m", value: "0.002" },
  { label: "5m", value: "0.005" },
  { label: "10m", value: "0.01" },
  { label: "20m", value: "0.02" },
  { label: "50m", value: "0.05" },
  { label: "100m", value: "0.1" },
  { label: "200m", value: "0.2" },
  { label: "500m", value: "0.5" },
  { label: "1", value: "1" },
];

const RANGE_PRESETS = [
  { label: "8m", value: "0.008" },
  { label: "16m", value: "0.016" },
  { label: "40m", value: "0.04" },
  { label: "80m", value: "0.08" },
  { label: "160m", value: "0.16" },
  { label: "400m", value: "0.4" },
  { label: "800m", value: "0.8" },
  { label: "1.6", value: "1.6" },
  { label: "4", value: "4" },
  { label: "8", value: "8" },
];

function channelLabel(channel) {
  const key = `enum.channel${channel}`;
  return hasTranslation(key) ? translate(key) : `CH${channel}`;
}

function unitLetter(units) {
  return units === "amp" ? "A" : "V";
}

function presetLabel(value, units) {
  if (units !== "volt" && units !== "amp") return String(value);
  return formatEngineering(Number(value), unitLetter(units));
}

export class ChannelScaleRangeEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.stateKey = null;
    this.channels = [];
    this.mode = "scale";
    this.scaleRead = null;
    this.rangeRead = null;
    this.divUnits = null;
    this.unitsChannel = null;
    this.buildDom();
  }

  definition() {
    return this.catalog.commands.find((command) => command.id === "channel-scale-range") || null;
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "channel-scale-range" ? selected : null;
  }

  currentStateKey() {
    return `${this.hooks.contextKey()}|${this.selectedDefinition()?.id || ""}`;
  }

  displayChannels() {
    const scaleDef = this.catalog.commands.find((command) => command.id === "channel-scale");
    if (!scaleDef) return [1, 2, 3, 4];
    const fields = this.catalog.fieldsFor
      ? this.catalog.fieldsFor(scaleDef)
      : scaleDef.fields || [];
    const channelField = fields.find((field) => field.name === "channel") || {};
    const options = this.catalog.optionsFor
      ? this.catalog.optionsFor(channelField)
      : channelField.options || [];
    const list = [...options]
      .map(Number)
      .filter((ch) => Number.isInteger(ch) && ch > 0)
      .sort((a, b) => a - b);
    return list.length ? list : [1, 2, 3, 4];
  }

  selectedChannel() {
    const value = Number(this.channelSelect?.value);
    return Number.isInteger(value) && value > 0 ? value : 1;
  }

  buildDom() {
    this.container.replaceChildren();

    // 1. Shared channel selector
    this.channelField = document.createElement("label");
    this.channelField.className = "field";
    this.channelFieldLabel = document.createElement("span");
    this.channelFieldLabel.textContent = translate("field.channel");
    this.channelSelect = document.createElement("select");
    this.channelSelect.dataset.field = "channel";
    this.channelSelect.addEventListener("change", () => {
      this.scaleInput.value = "";
      this.rangeInput.value = "";
      this.clearReadState();
      this.applyBusyState();
    });
    this.channelField.append(this.channelFieldLabel, this.channelSelect);

    // 2. Scale / Range mode selector (mutually exclusive, Scale by default)
    this.modeSelector = document.createElement("div");
    this.modeSelector.className = "trigger-editor-segmented channel-scale-range-mode";
    this.modeButtons = {};
    for (const key of ["scale", "range"]) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.dataset.mode = key;
      button.textContent = translate(`channel-scale-range.editor.mode${key === "scale" ? "Scale" : "Range"}`);
      button.addEventListener("click", () => {
        this.setMode(key);
      });
      this.modeSelector.append(button);
      this.modeButtons[key] = button;
    }

    // 2. Scale section
    this.scaleSection = document.createElement("div");
    this.scaleSection.className = "trigger-editor-section";

    this.scaleHeading = document.createElement("strong");
    this.scaleHeading.className = "trigger-editor-heading";
    this.scaleHeading.textContent = translate("channel-scale-range.editor.scale");

    this.scaleField = document.createElement("label");
    this.scaleField.className = "field channel-scale-range-value";
    this.scaleFieldLabel = document.createElement("span");
    this.scaleFieldLabel.textContent = translate("field.volts_per_division");
    this.scaleInput = document.createElement("input");
    this.scaleInput.type = "text";
    this.scaleInput.inputMode = "decimal";
    this.scaleInput.dataset.field = "volts_per_division";
    this.scaleField.append(this.scaleFieldLabel, this.scaleInput);

    this.scaleHelp = document.createElement("small");
    this.scaleHelp.className = "field-help";

    this.scalePresets = document.createElement("div");
    this.scalePresets.className = "channel-scale-range-presets";
    this.scalePresetButtons = [];
    for (const preset of SCALE_PRESETS) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = presetLabel(preset.value, null);
      button.addEventListener("click", () => {
        if (!this.modeReady("scale")) return;
        this.scaleInput.value = preset.value;
      });
      this.scalePresets.append(button);
      this.scalePresetButtons.push(button);
    }

    this.scaleSection.append(this.scaleHeading, this.scaleField, this.scaleHelp, this.scalePresets);

    // 3. Range section
    this.rangeSection = document.createElement("div");
    this.rangeSection.className = "trigger-editor-section";

    this.rangeHeading = document.createElement("strong");
    this.rangeHeading.className = "trigger-editor-heading";
    this.rangeHeading.textContent = translate("channel-scale-range.editor.range");

    this.rangeField = document.createElement("label");
    this.rangeField.className = "field channel-scale-range-value";
    this.rangeFieldLabel = document.createElement("span");
    this.rangeFieldLabel.textContent = translate("field.channel-range.value");
    this.rangeInput = document.createElement("input");
    this.rangeInput.type = "text";
    this.rangeInput.inputMode = "decimal";
    this.rangeInput.dataset.field = "volts";
    this.rangeField.append(this.rangeFieldLabel, this.rangeInput);

    this.rangeHelp = document.createElement("small");
    this.rangeHelp.className = "field-help";

    this.rangePresets = document.createElement("div");
    this.rangePresets.className = "channel-scale-range-presets";
    this.rangePresetButtons = [];
    for (const preset of RANGE_PRESETS) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = presetLabel(preset.value, null);
      button.addEventListener("click", () => {
        if (!this.modeReady("range")) return;
        this.rangeInput.value = preset.value;
      });
      this.rangePresets.append(button);
      this.rangePresetButtons.push(button);
    }

    this.rangeSection.append(this.rangeHeading, this.rangeField, this.rangeHelp, this.rangePresets);

    // 4. Single Read / Apply pair, routed by the current mode
    this.readButton = document.createElement("button");
    this.readButton.type = "button";
    this.readButton.className = "secondary";
    this.readButton.textContent = translate("actions.readSettings");
    this.readButton.addEventListener("click", () => {
      void this.readCurrent();
    });

    this.applyButton = document.createElement("button");
    this.applyButton.type = "button";
    this.applyButton.className = "primary";
    this.applyButton.textContent = translate("actions.apply");
    this.applyButton.addEventListener("click", () => {
      void this.applyCurrent();
    });

    this.container.append(
      this.channelField,
      this.modeSelector,
      this.scaleSection,
      this.rangeSection,
    );
    if (this.hooks.headerActions) {
      this.readButton.hidden = true;
      this.applyButton.hidden = true;
      this.hooks.headerActions.append(this.readButton, this.applyButton);
    } else {
      this.container.append(this.readButton, this.applyButton);
    }

    this.stateKey = null;
    this.syncHelpText();
    this.renderMode();
    this.schedulePresentation();
  }

  setMode(mode) {
    if (mode === this.mode) return;
    this.mode = mode;
    this.renderMode();
    this.applyBusyState();
  }

  renderMode() {
    for (const [key, button] of Object.entries(this.modeButtons)) {
      const active = key === this.mode;
      button.classList.toggle("selected", active);
      button.setAttribute("aria-pressed", String(active));
    }
    this.scaleSection.hidden = this.mode !== "scale";
    this.rangeSection.hidden = this.mode !== "range";
  }

  modeReady(mode) {
    const read = mode === "scale" ? this.scaleRead : this.rangeRead;
    return read !== null
      && read.channel === this.selectedChannel()
      && this.divUnits !== null
      && this.unitsChannel === this.selectedChannel();
  }

  quickFillReady() {
    return this.modeReady(this.mode);
  }

  clearModeRead(mode) {
    if (mode === "scale") {
      this.scaleRead = null;
    } else {
      this.rangeRead = null;
    }
    this.syncPresetLabels();
  }

  clearReadState() {
    this.scaleRead = null;
    this.rangeRead = null;
    this.divUnits = null;
    this.unitsChannel = null;
    this.syncPresetLabels();
  }

  syncPresetLabels() {
    const units = this.divUnits;
    for (let index = 0; index < this.scalePresetButtons.length; index += 1) {
      this.scalePresetButtons[index].textContent = presetLabel(SCALE_PRESETS[index].value, units);
    }
    for (let index = 0; index < this.rangePresetButtons.length; index += 1) {
      this.rangePresetButtons[index].textContent = presetLabel(RANGE_PRESETS[index].value, units);
    }
  }

  readCurrent() {
    if (this.mode === "scale") return this.readScale();
    return this.readRange();
  }

  applyCurrent() {
    if (this.mode === "scale") return this.applyScale();
    return this.applyRange();
  }

  syncHelpText() {
    this.scaleHelp.textContent = `${translate("channel-scale-range.editor.scaleDescription")}\n${translate("channel-scale-range.editor.readFirstHelp")}`;
    this.rangeHelp.textContent = `${translate("channel-scale-range.editor.rangeDescription")}\n${translate("channel-scale-range.editor.readFirstHelp")}`;
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    this.channelFieldLabel.textContent = translate("field.channel");
    this.scaleHeading.textContent = translate("channel-scale-range.editor.scale");
    this.scaleFieldLabel.textContent = translate("field.volts_per_division");
    this.rangeHeading.textContent = translate("channel-scale-range.editor.range");
    this.rangeFieldLabel.textContent = translate("field.channel-range.value");
    this.readButton.textContent = translate("actions.readSettings");
    this.applyButton.textContent = translate("actions.apply");
    this.modeButtons.scale.textContent = translate("channel-scale-range.editor.modeScale");
    this.modeButtons.range.textContent = translate("channel-scale-range.editor.modeRange");
    this.syncHelpText();
    this.renderMode();

    const currentVal = this.channelSelect.value;
    this.populateChannels();
    if (currentVal) this.channelSelect.value = currentVal;
  }

  present() {
    if (!this.selectedDefinition()) {
      this.stateKey = null;
      return;
    }
    const key = this.currentStateKey();
    if (key === this.stateKey) {
      this.applyBusyState();
      return;
    }
    this.stateKey = key;
    this.scaleInput.value = "";
    this.rangeInput.value = "";
    this.clearReadState();
    this.rebuild();
    this.applyBusyState();
  }

  rebuild() {
    this.channels = this.displayChannels();
    this.populateChannels();
  }

  populateChannels() {
    const previous = this.channelSelect.value;
    this.channelSelect.replaceChildren();
    for (const ch of this.channels) {
      const option = document.createElement("option");
      option.value = String(ch);
      option.textContent = channelLabel(ch);
      this.channelSelect.append(option);
    }
    if (previous && this.channels.map(String).includes(previous)) {
      this.channelSelect.value = previous;
    }
  }

  async readScale() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return null;
    if (!this.selectedDefinition()) return null;

    const contextKey = this.hooks.contextKey();
    const channel = this.selectedChannel();

    this.busy = true;
    this.applyBusyState();
    try {
      const job = await this.hooks.executeCommand(
        "channel-scale",
        { action: "query", channel },
        { intent: "readback" },
      );

      if (
        this.hooks.contextKey() !== contextKey ||
        this.selectedChannel() !== channel ||
        !this.selectedDefinition()
      ) {
        return job;
      }
      if (job?.status !== "completed") {
        this.clearModeRead("scale");
        return job;
      }

      const val = job?.result?.result?.volts_per_division ?? job?.result?.volts_per_division;
      if (typeof val !== "number" || !Number.isFinite(val)) {
        this.clearModeRead("scale");
        return job;
      }
      this.scaleInput.value = String(val);

      const unitsJob = await this.hooks.executeCommand(
        "channel-units",
        { action: "query", channel },
        { intent: "readback" },
      );
      if (
        this.hooks.contextKey() !== contextKey ||
        this.selectedChannel() !== channel ||
        !this.selectedDefinition()
      ) {
        return unitsJob;
      }
      const units = unitsJob?.result?.result?.units ?? unitsJob?.result?.units;
      if (unitsJob?.status !== "completed" || (units !== "volt" && units !== "amp")) {
        this.clearModeRead("scale");
        return unitsJob;
      }
      this.scaleRead = { channel, value: val };
      this.divUnits = units;
      this.unitsChannel = channel;
      this.syncPresetLabels();
      return unitsJob;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  async applyScale() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return null;
    if (!this.selectedDefinition()) return null;

    const value = Number(this.scaleInput.value);
    if (!Number.isFinite(value) || value <= 0) return null;

    const contextKey = this.hooks.contextKey();
    const channel = this.selectedChannel();

    this.busy = true;
    this.applyBusyState();
    try {
      const job = await this.hooks.executeCommand(
        "channel-scale",
        { action: "set", channel, volts_per_division: value },
        { intent: "apply" },
      );

      if (
        job?.status !== "completed" ||
        this.hooks.contextKey() !== contextKey ||
        this.selectedChannel() !== channel ||
        !this.selectedDefinition()
      ) {
        return job;
      }

      // Use readback from successful set command to update the same field
      const actual = job?.result?.result?.volts_per_division ?? job?.result?.volts_per_division;
      if (actual !== undefined && actual !== null) {
        this.scaleInput.value = String(actual);
      }
      return job;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  async readRange() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return null;
    if (!this.selectedDefinition()) return null;

    const contextKey = this.hooks.contextKey();
    const channel = this.selectedChannel();

    this.busy = true;
    this.applyBusyState();
    try {
      const job = await this.hooks.executeCommand(
        "channel-range",
        { action: "query", channel },
        { intent: "readback" },
      );

      if (
        this.hooks.contextKey() !== contextKey ||
        this.selectedChannel() !== channel ||
        !this.selectedDefinition()
      ) {
        return job;
      }
      if (job?.status !== "completed") {
        this.clearModeRead("range");
        return job;
      }

      const val = job?.result?.result?.volts ?? job?.result?.volts;
      if (typeof val !== "number" || !Number.isFinite(val)) {
        this.clearModeRead("range");
        return job;
      }
      this.rangeInput.value = String(val);

      const unitsJob = await this.hooks.executeCommand(
        "channel-units",
        { action: "query", channel },
        { intent: "readback" },
      );
      if (
        this.hooks.contextKey() !== contextKey ||
        this.selectedChannel() !== channel ||
        !this.selectedDefinition()
      ) {
        return unitsJob;
      }
      const units = unitsJob?.result?.result?.units ?? unitsJob?.result?.units;
      if (unitsJob?.status !== "completed" || (units !== "volt" && units !== "amp")) {
        this.clearModeRead("range");
        return unitsJob;
      }
      this.rangeRead = { channel, value: val };
      this.divUnits = units;
      this.unitsChannel = channel;
      this.syncPresetLabels();
      return unitsJob;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  async applyRange() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return null;
    if (!this.selectedDefinition()) return null;

    const value = Number(this.rangeInput.value);
    if (!Number.isFinite(value) || value <= 0) return null;

    const contextKey = this.hooks.contextKey();
    const channel = this.selectedChannel();

    this.busy = true;
    this.applyBusyState();
    try {
      const job = await this.hooks.executeCommand(
        "channel-range",
        { action: "set", channel, volts: value },
        { intent: "apply" },
      );

      if (
        job?.status !== "completed" ||
        this.hooks.contextKey() !== contextKey ||
        this.selectedChannel() !== channel ||
        !this.selectedDefinition()
      ) {
        return job;
      }

      // Use readback from successful set command to update the same field
      const actual = job?.result?.result?.volts ?? job?.result?.volts;
      if (actual !== undefined && actual !== null) {
        this.rangeInput.value = String(actual);
      }
      return job;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  applyBusyState() {
    const disabled =
      this.busy ||
      this.hooks.isExecutionBusy?.() ||
      !this.hooks.isAvailable?.() ||
      !this.channels.length;
    this.channelSelect.disabled = disabled;
    this.scaleInput.disabled = disabled;
    this.rangeInput.disabled = disabled;
    this.readButton.disabled = disabled;
    this.applyButton.disabled = disabled;
    for (const button of this.scalePresetButtons) button.disabled = disabled || !this.modeReady("scale");
    for (const button of this.rangePresetButtons) button.disabled = disabled || !this.modeReady("range");
  }
}
