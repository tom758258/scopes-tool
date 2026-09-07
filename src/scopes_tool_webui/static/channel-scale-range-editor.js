import { hasTranslation, translate } from "/static/i18n.js";

const SCALE_PRESETS = [
  { label: "0.001", value: "0.001" },
  { label: "0.002", value: "0.002" },
  { label: "0.005", value: "0.005" },
  { label: "0.01", value: "0.01" },
  { label: "0.02", value: "0.02" },
  { label: "0.05", value: "0.05" },
  { label: "0.1", value: "0.1" },
  { label: "0.2", value: "0.2" },
  { label: "0.5", value: "0.5" },
  { label: "1", value: "1" },
];

const RANGE_PRESETS = [
  { label: "0.008", value: "0.008" },
  { label: "0.016", value: "0.016" },
  { label: "0.04", value: "0.04" },
  { label: "0.08", value: "0.08" },
  { label: "0.16", value: "0.16" },
  { label: "0.4", value: "0.4" },
  { label: "0.8", value: "0.8" },
  { label: "1.6", value: "1.6" },
  { label: "4", value: "4" },
  { label: "8", value: "8" },
];

function channelLabel(channel) {
  const key = `enum.channel${channel}`;
  return hasTranslation(key) ? translate(key) : `CH${channel}`;
}

export class ChannelScaleRangeEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.stateKey = null;
    this.channels = [];
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
    });
    this.channelField.append(this.channelFieldLabel, this.channelSelect);

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
      button.textContent = preset.label;
      button.addEventListener("click", () => {
        if (this.scaleInput.disabled) return;
        this.scaleInput.value = preset.value;
      });
      this.scalePresets.append(button);
      this.scalePresetButtons.push(button);
    }

    this.scaleActions = document.createElement("div");
    this.scaleActions.style.display = "flex";
    this.scaleActions.style.gap = "8px";
    this.scaleActions.style.marginTop = "6px";

    this.readScaleButton = document.createElement("button");
    this.readScaleButton.type = "button";
    this.readScaleButton.className = "secondary";
    this.readScaleButton.textContent = translate("channel-scale-range.editor.readScale");
    this.readScaleButton.addEventListener("click", () => {
      void this.readScale();
    });

    this.applyScaleButton = document.createElement("button");
    this.applyScaleButton.type = "button";
    this.applyScaleButton.className = "primary";
    this.applyScaleButton.textContent = translate("channel-scale-range.editor.applyScale");
    this.applyScaleButton.addEventListener("click", () => {
      void this.applyScale();
    });

    this.scaleActions.append(this.readScaleButton, this.applyScaleButton);
    this.scaleSection.append(this.scaleHeading, this.scaleField, this.scaleHelp, this.scalePresets, this.scaleActions);

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
      button.textContent = preset.label;
      button.addEventListener("click", () => {
        if (this.rangeInput.disabled) return;
        this.rangeInput.value = preset.value;
      });
      this.rangePresets.append(button);
      this.rangePresetButtons.push(button);
    }

    this.rangeActions = document.createElement("div");
    this.rangeActions.style.display = "flex";
    this.rangeActions.style.gap = "8px";
    this.rangeActions.style.marginTop = "6px";

    this.readRangeButton = document.createElement("button");
    this.readRangeButton.type = "button";
    this.readRangeButton.className = "secondary";
    this.readRangeButton.textContent = translate("channel-scale-range.editor.readRange");
    this.readRangeButton.addEventListener("click", () => {
      void this.readRange();
    });

    this.applyRangeButton = document.createElement("button");
    this.applyRangeButton.type = "button";
    this.applyRangeButton.className = "primary";
    this.applyRangeButton.textContent = translate("channel-scale-range.editor.applyRange");
    this.applyRangeButton.addEventListener("click", () => {
      void this.applyRange();
    });

    this.rangeActions.append(this.readRangeButton, this.applyRangeButton);
    this.rangeSection.append(this.rangeHeading, this.rangeField, this.rangeHelp, this.rangePresets, this.rangeActions);

    this.container.append(
      this.channelField,
      this.scaleSection,
      this.rangeSection,
    );

    this.stateKey = null;
    this.syncHelpText();
    this.schedulePresentation();
  }

  syncHelpText() {
    this.scaleHelp.textContent = `${translate("help.channel-scale.volts_per_division")}\n${translate("channel-scale-range.editor.quickFillHelp")}`;
    this.rangeHelp.textContent = `${translate("help.channel-range.volts")}\n${translate("channel-scale-range.editor.quickFillHelp")}`;
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    this.channelFieldLabel.textContent = translate("field.channel");
    this.scaleHeading.textContent = translate("channel-scale-range.editor.scale");
    this.scaleFieldLabel.textContent = translate("field.volts_per_division");
    this.readScaleButton.textContent = translate("channel-scale-range.editor.readScale");
    this.applyScaleButton.textContent = translate("channel-scale-range.editor.applyScale");
    this.rangeHeading.textContent = translate("channel-scale-range.editor.range");
    this.rangeFieldLabel.textContent = translate("field.channel-range.value");
    this.readRangeButton.textContent = translate("channel-scale-range.editor.readRange");
    this.applyRangeButton.textContent = translate("channel-scale-range.editor.applyRange");
    this.syncHelpText();

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
        job?.status !== "completed" ||
        this.hooks.contextKey() !== contextKey ||
        this.selectedChannel() !== channel ||
        !this.selectedDefinition()
      ) {
        return job;
      }

      const val = job?.result?.result?.volts_per_division ?? job?.result?.volts_per_division;
      if (val !== undefined && val !== null) {
        this.scaleInput.value = String(val);
      }
      return job;
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
        job?.status !== "completed" ||
        this.hooks.contextKey() !== contextKey ||
        this.selectedChannel() !== channel ||
        !this.selectedDefinition()
      ) {
        return job;
      }

      const val = job?.result?.result?.volts ?? job?.result?.volts;
      if (val !== undefined && val !== null) {
        this.rangeInput.value = String(val);
      }
      return job;
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
    this.readScaleButton.disabled = disabled;
    this.applyScaleButton.disabled = disabled;
    this.readRangeButton.disabled = disabled;
    this.applyRangeButton.disabled = disabled;
    for (const button of this.scalePresetButtons) button.disabled = disabled;
    for (const button of this.rangePresetButtons) button.disabled = disabled;
  }
}
