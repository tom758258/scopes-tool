import { hasTranslation, translate } from "/static/i18n.js";
import { formatEngineering } from "/static/live-data.js";

const DIV_STEPS = [-4, -3, -2, -1, 0, 1, 2, 3, 4];

function channelLabel(channel) {
  const key = `enum.channel${channel}`;
  return hasTranslation(key) ? translate(key) : `CH${channel}`;
}

function divLabel(div) {
  return div > 0 ? `+${div}` : String(div);
}

function divValueText(div, scale) {
  return cleanFloatText(div * scale);
}

function cleanFloatText(value) {
  return String(Number(value.toPrecision(12)));
}

function unitLetter(units) {
  return units === "amp" ? "A" : "V";
}

export class ChannelOffsetEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.stateKey = null;
    this.channels = [];
    this.divScale = null;
    this.divChannel = null;
    this.divUnits = null;
    this.divRange = null;
    this.lastOffset = null;
    this.selectedDiv = null;
    this.divIncomplete = false;
    this.buildDom();
  }

  definition() {
    return this.catalog.commands.find((command) => command.id === "channel-offset") || null;
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "channel-offset" ? selected : null;
  }

  currentStateKey() {
    return `${this.hooks.contextKey()}|${this.selectedDefinition()?.id || ""}`;
  }

  displayChannels() {
    const offsetDef = this.catalog.commands.find((command) => command.id === "channel-offset");
    if (!offsetDef) return [1, 2, 3, 4];
    const fields = this.catalog.fieldsFor
      ? this.catalog.fieldsFor(offsetDef)
      : offsetDef.fields || [];
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

    this.channelField = document.createElement("label");
    this.channelField.className = "field";
    this.channelFieldLabel = document.createElement("span");
    this.channelFieldLabel.textContent = translate("field.channel");
    this.channelSelect = document.createElement("select");
    this.channelSelect.dataset.field = "channel";
    this.channelSelect.addEventListener("change", () => {
      this.offsetInput.value = "";
      this.divIncomplete = false;
      this.clearDivState();
      this.applyBusyState();
    });
    this.channelField.append(this.channelFieldLabel, this.channelSelect);

    this.offsetField = document.createElement("label");
    this.offsetField.className = "field";
    this.offsetFieldLabel = document.createElement("span");
    this.offsetFieldLabel.textContent = translate("field.channel-offset.value");
    this.offsetInput = document.createElement("input");
    this.offsetInput.type = "text";
    this.offsetInput.inputMode = "decimal";
    this.offsetInput.dataset.field = "volts";
    this.offsetInput.addEventListener("input", () => {
      this.selectedDiv = null;
      this.syncInfo();
    });
    this.offsetField.append(this.offsetFieldLabel, this.offsetInput);

    this.divSection = document.createElement("div");
    this.divSection.className = "trigger-editor-section";

    this.divHeading = document.createElement("strong");
    this.divHeading.className = "trigger-editor-heading";
    this.divHeading.textContent = translate("channel-offset.editor.divHeading");

    this.divHint = document.createElement("small");
    this.divHint.className = "field-help";
    this.divHint.textContent = translate("channel-offset.editor.divHint");

    this.divButtonsHost = document.createElement("div");
    this.divButtonsHost.className = "div-slider-block";
    this.divSlider = document.createElement("input");
    this.divSlider.type = "range";
    this.divSlider.min = String(DIV_STEPS[0]);
    this.divSlider.max = String(DIV_STEPS[DIV_STEPS.length - 1]);
    this.divSlider.step = "1";
    this.divSlider.value = "0";
    this.divSlider.setAttribute("aria-label", translate("channel-offset.editor.divHeading"));
    this.divSlider.addEventListener("input", () => {
      this.selectDiv(Number(this.divSlider.value));
    });
    this.divButtonsHost.append(this.divSlider);
    this.divTicksHost = document.createElement("div");
    this.divTicksHost.className = "div-slider-ticks";
    this.divTicksHost.style.gridTemplateColumns = `repeat(${DIV_STEPS.length}, minmax(0, 1fr))`;
    this.divTicks = [];
    for (const div of DIV_STEPS) {
      const tick = document.createElement("span");
      tick.textContent = divLabel(div);
      this.divTicksHost.append(tick);
      this.divTicks.push(tick);
    }

    this.info = document.createElement("output");
    this.info.className = "muted compact-note";
    this.selection = document.createElement("output");
    this.selection.className = "muted compact-note";
    this.divStatus = document.createElement("output");
    this.divStatus.className = "muted compact-note";
    this.divSection.append(
      this.divHeading,
      this.divHint,
      this.divButtonsHost,
      this.divTicksHost,
      this.info,
      this.selection,
      this.divStatus,
    );

    this.actions = document.createElement("div");
    this.actions.style.display = "flex";
    this.actions.style.gap = "8px";
    this.actions.style.marginTop = "6px";

    this.readButton = document.createElement("button");
    this.readButton.type = "button";
    this.readButton.className = "secondary";
    this.readButton.textContent = translate("actions.readSettings");
    this.readButton.addEventListener("click", () => {
      void this.read();
    });

    this.applyButton = document.createElement("button");
    this.applyButton.type = "button";
    this.applyButton.className = "primary";
    this.applyButton.textContent = translate("actions.apply");
    this.applyButton.addEventListener("click", () => {
      void this.apply();
    });

    this.actions.append(this.readButton, this.applyButton);
    this.container.append(this.channelField, this.offsetField, this.divSection, this.actions);

    this.stateKey = null;
    this.syncInfo();
    this.schedulePresentation();
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    this.channelFieldLabel.textContent = translate("field.channel");
    this.offsetFieldLabel.textContent = translate("field.channel-offset.value");
    this.divHeading.textContent = translate("channel-offset.editor.divHeading");
    this.divHint.textContent = translate("channel-offset.editor.divHint");
    this.divSlider.setAttribute("aria-label", translate("channel-offset.editor.divHeading"));
    this.readButton.textContent = translate("actions.readSettings");
    this.applyButton.textContent = translate("actions.apply");
    this.syncInfo();

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
    this.offsetInput.value = "";
    this.divIncomplete = false;
    this.clearDivState();
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

  clearDivState() {
    this.divScale = null;
    this.divChannel = null;
    this.divUnits = null;
    this.divRange = null;
    this.lastOffset = null;
    this.selectedDiv = null;
    this.syncInfo();
  }

  syncInfo() {
    this.divSlider.value = this.selectedDiv === null ? "0" : String(this.selectedDiv);
    if (this.divScale === null || this.divChannel === null) {
      this.info.textContent = "";
    } else {
      const unit = unitLetter(this.divUnits);
      this.info.textContent = translate("channel-offset.editor.currentSettings", {
        scale: formatEngineering(this.divScale, unit, { perDivision: true }),
        range: formatEngineering(this.divRange, unit, {}),
        units: translate(`enum.${this.divUnits === "amp" ? "amp" : "volt"}`),
        offset: formatEngineering(this.lastOffset, unit, { signed: true }),
      });
    }
    if (this.selectedDiv === null || this.divScale === null) {
      this.selection.textContent = "";
    } else {
      const unit = unitLetter(this.divUnits);
      this.selection.textContent = translate("channel-offset.editor.divSelection", {
        div: divLabel(this.selectedDiv),
        value: formatEngineering(Number(cleanFloatText(this.selectedDiv * this.divScale)), unit, { signed: true }),
      });
    }
    this.divStatus.textContent = this.divIncomplete
      ? translate("channel-offset.editor.divReadIncomplete")
      : "";
  }

  selectDiv(div) {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return;
    if (this.divScale === null || this.divChannel !== this.selectedChannel()) return;
    if (this.offsetInput.disabled) return;
    this.selectedDiv = div;
    this.offsetInput.value = divValueText(div, this.divScale);
    this.syncInfo();
  }

  async read() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return null;
    if (!this.selectedDefinition()) return null;

    const contextKey = this.hooks.contextKey();
    const channel = this.selectedChannel();

    this.busy = true;
    this.applyBusyState();
    try {
      const job = await this.hooks.executeCommand(
        "channel-summary",
        {},
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
        this.divIncomplete = true;
        this.clearDivState();
        return job;
      }
      const channels = job?.result?.result?.channels ?? job?.result?.channels;
      const entry = Array.isArray(channels)
        ? channels.find((item) => Number(item?.channel) === channel)
        : undefined;
      const scale = entry?.scale;
      const range = entry?.range;
      const offset = entry?.offset;
      const units = entry?.units;
      const complete = typeof scale === "number" && Number.isFinite(scale) && scale > 0
        && typeof range === "number" && Number.isFinite(range) && range > 0
        && typeof offset === "number" && Number.isFinite(offset)
        && (units === "volt" || units === "amp");
      if (!complete) {
        this.divIncomplete = true;
        this.clearDivState();
        return job;
      }
      this.offsetInput.value = String(offset);
      this.lastOffset = offset;
      this.divScale = scale;
      this.divChannel = channel;
      this.divUnits = units;
      this.divRange = range;
      this.selectedDiv = null;
      this.divIncomplete = false;
      this.syncInfo();
      return job;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  async apply() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return null;
    if (!this.selectedDefinition()) return null;

    const value = Number(this.offsetInput.value);
    if (!Number.isFinite(value)) return null;

    const contextKey = this.hooks.contextKey();
    const channel = this.selectedChannel();

    this.busy = true;
    this.applyBusyState();
    try {
      const job = await this.hooks.executeCommand(
        "channel-offset",
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

      // Use readback from the successful set command to update the same field
      const actual = job?.result?.result?.volts ?? job?.result?.volts;
      if (typeof actual === "number" && Number.isFinite(actual)) {
        this.offsetInput.value = String(actual);
        this.lastOffset = actual;
      }
      this.selectedDiv = null;
      this.syncInfo();
      return job;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  applyBusyState() {
    const unavailable = this.busy
      || this.hooks.isExecutionBusy?.()
      || !this.hooks.isAvailable?.()
      || !this.channels.length;
    this.channelSelect.disabled = unavailable;
    this.offsetInput.disabled = unavailable;
    this.readButton.disabled = unavailable;
    this.applyButton.disabled = unavailable;
    const divDisabled = unavailable
      || this.divScale === null
      || this.divChannel !== this.selectedChannel();
    this.divSlider.disabled = divDisabled;
  }
}
