import { hasTranslation, translate } from "/static/i18n.js";

function segmentedState(job) {
  return job?.result?.result?.segmented ?? job?.result?.segmented ?? null;
}

function modeLabel(mode) {
  const key = `enum.${String(mode)}`;
  return hasTranslation(key) ? translate(key) : String(mode);
}

export class SegmentedEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.contextKey = null;
    this.dirty = false;
    this.state = null;
    this.buildDom();
  }

  buildDom() {
    this.refreshButton?.remove?.();
    this.container.replaceChildren();

    const head = document.createElement("div");
    head.className = "segmented-editor-head";
    const heading = document.createElement("strong");
    heading.textContent = translate("command.segmented-memory");
    this.status = document.createElement("strong");
    this.status.className = "state-indicator state-idle segmented-editor-status";
    const dot = document.createElement("span");
    dot.className = "state-dot";
    dot.setAttribute("aria-hidden", "true");
    this.statusText = document.createElement("span");
    this.statusText.className = "state-text";
    this.status.append(dot, this.statusText);
    head.append(heading, this.status);

    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary";
    this.refreshButton.textContent = translate("actions.refresh");
    this.refreshButton.addEventListener("click", () => void this.refresh());
    if (this.hooks.headerActions) {
      this.refreshButton.hidden = true;
      this.hooks.headerActions.append(this.refreshButton);
    } else {
      head.append(this.refreshButton);
    }

    this.readouts = document.createElement("dl");
    this.readouts.className = "segmented-editor-state";
    this.modeOutput = this.appendReadout("segmented.editor.mode");
    this.configuredRow = this.appendReadout("segmented.editor.configuredSegments");
    this.acquiredRow = this.appendReadout("segmented.editor.acquiredSegments");

    const countField = document.createElement("label");
    countField.className = "field segmented-editor-count";
    const countLabel = document.createElement("span");
    countLabel.textContent = translate("field.segments");
    this.countInput = document.createElement("input");
    this.countInput.type = "number";
    this.countInput.step = "1";
    this.countInput.required = true;
    this.countInput.addEventListener("input", () => {
      this.dirty = true;
    });
    countField.append(countLabel, this.countInput);

    this.segmentBrowser = document.createElement("section");
    this.segmentBrowser.className = "segmented-editor-browser";
    const browserLabel = document.createElement("strong");
    browserLabel.textContent = translate("segmented.editor.segment");
    const browserControls = document.createElement("div");
    browserControls.className = "segmented-editor-browser-controls";
    this.previousButton = document.createElement("button");
    this.previousButton.type = "button";
    this.previousButton.className = "secondary";
    this.previousButton.textContent = translate("segmented.editor.previous");
    this.previousButton.addEventListener("click", () => void this.previous());
    this.segmentInput = document.createElement("input");
    this.segmentInput.type = "number";
    this.segmentInput.min = "1";
    this.segmentInput.step = "1";
    this.segmentInput.required = true;
    this.segmentInput.setAttribute("aria-label", translate("segmented.editor.segment"));
    this.segmentInput.addEventListener("input", () => this.applyBusyState());
    this.segmentTotal = document.createElement("span");
    this.segmentTotal.className = "segmented-editor-segment-total";
    this.nextButton = document.createElement("button");
    this.nextButton.type = "button";
    this.nextButton.className = "secondary";
    this.nextButton.textContent = translate("segmented.editor.next");
    this.nextButton.addEventListener("click", () => void this.next());
    this.selectButton = document.createElement("button");
    this.selectButton.type = "button";
    this.selectButton.className = "secondary";
    this.selectButton.textContent = translate("segmented.editor.select");
    this.selectButton.addEventListener("click", () => void this.selectIndex());
    browserControls.append(
      this.previousButton,
      this.segmentInput,
      this.segmentTotal,
      this.nextButton,
      this.selectButton,
    );
    const timeTag = document.createElement("dl");
    timeTag.className = "segmented-editor-browser-readout";
    const timeTagLabel = document.createElement("dt");
    timeTagLabel.textContent = translate("segmented.editor.timeTag");
    this.timeTagOutput = document.createElement("dd");
    timeTag.append(timeTagLabel, this.timeTagOutput);
    this.segmentBrowser.append(browserLabel, browserControls, timeTag);

    const actions = document.createElement("div");
    actions.className = "segmented-editor-actions";
    this.enterButton = document.createElement("button");
    this.enterButton.type = "button";
    this.enterButton.className = "primary";
    this.enterButton.addEventListener("click", () => void this.enter());
    this.exitButton = document.createElement("button");
    this.exitButton.type = "button";
    this.exitButton.className = "secondary";
    this.exitButton.textContent = translate("segmented.editor.exit");
    this.exitButton.addEventListener("click", () => void this.exit());
    actions.append(this.enterButton, this.exitButton);

    this.captureSection = document.createElement("section");
    this.captureSection.className = "segmented-editor-browser";
    const captureHeading = document.createElement("strong");
    captureHeading.textContent = translate("command.segmented-capture");
    const captureChannelField = document.createElement("label");
    captureChannelField.className = "field";
    const captureChannelLabel = document.createElement("span");
    captureChannelLabel.textContent = translate("field.channel");
    this.captureChannelInput = document.createElement("input");
    this.captureChannelInput.type = "number";
    this.captureChannelInput.step = "1";
    this.captureChannelInput.required = true;
    captureChannelField.append(captureChannelLabel, this.captureChannelInput);
    const captureSegmentsField = document.createElement("label");
    captureSegmentsField.className = "field";
    const captureSegmentsLabel = document.createElement("span");
    captureSegmentsLabel.textContent = translate("field.segments");
    this.captureSegmentsInput = document.createElement("input");
    this.captureSegmentsInput.type = "number";
    this.captureSegmentsInput.step = "1";
    this.captureSegmentsInput.required = true;
    captureSegmentsField.append(captureSegmentsLabel, this.captureSegmentsInput);
    const capturePointsField = document.createElement("label");
    capturePointsField.className = "field";
    const capturePointsLabel = document.createElement("span");
    capturePointsLabel.textContent = translate("field.points");
    this.capturePointsSelect = document.createElement("select");
    this.capturePointsSelect.required = true;
    capturePointsField.append(capturePointsLabel, this.capturePointsSelect);
    const captureFormatField = document.createElement("label");
    captureFormatField.className = "field";
    const captureFormatLabel = document.createElement("span");
    captureFormatLabel.textContent = translate("field.format");
    this.captureFormatSelect = document.createElement("select");
    this.captureFormatSelect.required = true;
    captureFormatField.append(captureFormatLabel, this.captureFormatSelect);
    this.captureButton = document.createElement("button");
    this.captureButton.type = "button";
    this.captureButton.className = "primary";
    this.captureButton.textContent = translate("actions.capture");
    this.captureButton.addEventListener("click", () => void this.capture());
    this.captureSection.append(
      captureHeading,
      captureChannelField,
      captureSegmentsField,
      capturePointsField,
      captureFormatField,
      this.captureButton,
    );

    this.unavailableNote = document.createElement("p");
    this.unavailableNote.className = "muted compact-note";
    this.unavailableNote.textContent = translate("segmented.editor.unavailable");
    this.container.append(
      head,
      this.unavailableNote,
      this.readouts,
      countField,
      this.segmentBrowser,
      this.captureSection,
      actions,
    );
    this.applyDefinition();
    this.applyCaptureDefinition(true);
    this.renderState();
  }

  appendReadout(labelKey) {
    const label = document.createElement("dt");
    label.textContent = translate(labelKey);
    const output = document.createElement("dd");
    this.readouts.append(label, output);
    return { label, output };
  }

  definition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "segmented" ? selected : null;
  }

  captureDefinition() {
    const commands = this.catalog?.commands;
    if (!Array.isArray(commands)) return null;
    return commands.find((command) => command.id === "segmented-capture") || null;
  }

  captureSupported() {
    const definition = this.captureDefinition();
    return Boolean(definition) && this.catalog.supported(definition);
  }

  applyCaptureDefinition(contextChanged = false) {
    const definition = this.captureDefinition();
    const fields = definition ? this.catalog.fieldsFor(definition) : [];
    const fieldByName = (name) => fields.find((field) => field.name === name);
    const channelField = fieldByName("channel");
    const segmentsField = fieldByName("segments");
    const pointsField = fieldByName("points");
    const formatField = fieldByName("format");
    if (channelField) {
      if (channelField.minimum !== undefined) {
        this.captureChannelInput.min = String(channelField.minimum);
      }
      if (channelField.maximum !== undefined) {
        this.captureChannelInput.max = String(channelField.maximum);
      }
      if (contextChanged || !this.captureChannelInput.value) {
        const initial = channelField.default ?? channelField.minimum ?? "";
        this.captureChannelInput.value = initial === "" ? "" : String(initial);
      }
    }
    if (segmentsField) {
      if (segmentsField.minimum !== undefined) {
        this.captureSegmentsInput.min = String(segmentsField.minimum);
      }
      if (segmentsField.maximum !== undefined) {
        this.captureSegmentsInput.max = String(segmentsField.maximum);
      }
      if (contextChanged || !this.captureSegmentsInput.value) {
        const initial = segmentsField.default ?? segmentsField.minimum ?? "";
        this.captureSegmentsInput.value = initial === "" ? "" : String(initial);
      }
    }
    if (pointsField) {
      const options = (pointsField.options || []).map(String);
      const previous = this.capturePointsSelect.value;
      this.capturePointsSelect.replaceChildren(...options.map((option) => {
        const item = document.createElement("option");
        item.value = option;
        item.textContent = option;
        return item;
      }));
      if (!contextChanged && options.includes(previous)) {
        this.capturePointsSelect.value = previous;
      } else {
        const initial = pointsField.default ?? options[0] ?? "";
        this.capturePointsSelect.value = initial === "" ? "" : String(initial);
      }
    }
    if (formatField) {
      const options = (formatField.options || []).map(String);
      const previous = this.captureFormatSelect.value;
      this.captureFormatSelect.replaceChildren(...options.map((option) => {
        const item = document.createElement("option");
        item.value = option;
        item.textContent = option.toUpperCase();
        return item;
      }));
      if (!contextChanged && options.includes(previous)) {
        this.captureFormatSelect.value = previous;
      } else {
        const initial = formatField.default ?? options[0] ?? "";
        this.captureFormatSelect.value = initial === "" ? "" : String(initial);
      }
    }
  }

  applyDefinition() {
    const definition = this.definition();
    const segmentField = definition
      ? this.catalog.fieldsFor(definition).find((field) => field.name === "segments")
      : null;
    this.countInput.min = String(segmentField?.minimum ?? "");
    this.countInput.max = String(segmentField?.maximum ?? "");
    if (!this.countInput.value && segmentField?.minimum !== undefined) {
      this.countInput.value = String(segmentField.minimum);
    }
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    const countValue = this.countInput?.value || "";
    const segmentValue = this.segmentInput?.value || "";
    const captureChannel = this.captureChannelInput?.value || "";
    const captureSegments = this.captureSegmentsInput?.value || "";
    const capturePoints = this.capturePointsSelect?.value || "";
    const captureFormat = this.captureFormatSelect?.value || "";
    const contextKey = this.contextKey;
    this.buildDom();
    if (countValue !== "") this.countInput.value = countValue;
    this.present();
    queueMicrotask(() => {
      if (contextKey !== this.contextKey) return;
      let restored = false;
      if (segmentValue !== "" && this.browserAvailable()) {
        this.segmentInput.value = segmentValue;
        restored = true;
      }
      if (this.captureSupported()) {
        if (captureChannel !== "") {
          this.captureChannelInput.value = captureChannel;
          restored = true;
        }
        if (captureSegments !== "") {
          this.captureSegmentsInput.value = captureSegments;
          restored = true;
        }
        if (capturePoints !== "") {
          this.capturePointsSelect.value = capturePoints;
          restored = true;
        }
        if (captureFormat !== "") {
          this.captureFormatSelect.value = captureFormat;
          restored = true;
        }
      }
      if (restored) this.applyBusyState();
    });
  }

  present() {
    const key = this.hooks.contextKey();
    const contextChanged = key !== this.contextKey;
    if (contextChanged) {
      this.contextKey = key;
      this.state = null;
      this.dirty = false;
      this.countInput.value = "";
    }
    this.applyDefinition();
    this.applyCaptureDefinition(contextChanged);
    this.renderState();
    this.applyBusyState();
  }

  async refresh() {
    if (!this.canExecute()) return;
    const submittedContextKey = this.contextKey;
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        "segmented-memory",
        { action: "query" },
        { intent: "readback" },
      );
      this.acceptJob(job, true, submittedContextKey);
    } finally {
      this.setBusy(false);
    }
  }

  async enter() {
    if (!this.canExecute()) return;
    if (!this.countInput.checkValidity()) {
      this.countInput.reportValidity();
      return;
    }
    const segments = Number(this.countInput.value);
    if (!Number.isInteger(segments)) {
      this.countInput.setCustomValidity(translate("segmented.editor.integer"));
      this.countInput.reportValidity();
      this.countInput.setCustomValidity("");
      return;
    }
    const submittedContextKey = this.contextKey;
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        "segmented-memory",
        { action: "enable", segments },
        { intent: "apply" },
      );
      this.acceptJob(job, false, submittedContextKey);
    } finally {
      this.setBusy(false);
    }
  }

  async exit() {
    if (!this.canExecute()) return;
    const submittedContextKey = this.contextKey;
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        "segmented-memory",
        { action: "disable" },
        { intent: "apply" },
      );
      this.acceptJob(job, true, submittedContextKey);
    } finally {
      this.setBusy(false);
    }
  }

  canCapture() {
    return this.captureSupported()
      && this.canExecute()
      && this.captureChannelInput?.value !== ""
      && this.captureSegmentsInput?.value !== ""
      && this.capturePointsSelect?.value !== ""
      && this.captureFormatSelect?.value !== ""
      && this.captureChannelInput?.checkValidity()
      && this.captureSegmentsInput?.checkValidity();
  }

  async capture() {
    if (!this.canCapture()) {
      this.captureChannelInput?.reportValidity?.();
      this.captureSegmentsInput?.reportValidity?.();
      return;
    }
    const channel = Number(this.captureChannelInput.value);
    const segments = Number(this.captureSegmentsInput.value);
    const points = Number(this.capturePointsSelect.value);
    const format = String(this.captureFormatSelect.value).toLowerCase();
    if (!Number.isInteger(channel) || !Number.isInteger(segments) || !Number.isInteger(points)) {
      return;
    }
    this.setBusy(true);
    try {
      await this.hooks.executeCommand(
        "segmented-capture",
        { channel, segments, points, format },
        { intent: "command" },
      );
    } finally {
      this.setBusy(false);
    }
  }

  async previous() {
    const selected = this.state?.selected_segment;
    if (!this.browserAvailable() || !Number.isInteger(selected) || selected <= 1) return;
    await this.selectSegment(selected - 1);
  }

  async next() {
    const selected = this.state?.selected_segment;
    const acquired = this.state?.acquired_segments;
    if (
      !this.browserAvailable()
      || !Number.isInteger(selected)
      || selected >= acquired
    ) return;
    await this.selectSegment(selected + 1);
  }

  async selectIndex() {
    if (!this.browserAvailable() || !this.canExecute()) return;
    if (!this.segmentInput.checkValidity()) {
      this.segmentInput.reportValidity();
      return;
    }
    const index = Number(this.segmentInput.value);
    if (!Number.isInteger(index)) {
      this.segmentInput.setCustomValidity(translate("segmented.editor.segmentInteger"));
      this.segmentInput.reportValidity();
      this.segmentInput.setCustomValidity("");
      return;
    }
    await this.selectSegment(index);
  }

  async selectSegment(index) {
    if (!this.browserAvailable() || !this.canExecute()) return;
    const submittedContextKey = this.contextKey;
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        "segmented-memory",
        { action: "select", index },
        { intent: "apply" },
      );
      this.acceptJob(job, true, submittedContextKey);
    } finally {
      this.setBusy(false);
    }
  }

  acceptJob(job, preserveDirty, submittedContextKey = this.contextKey) {
    if (submittedContextKey !== this.hooks.contextKey()) return;
    const state = job?.status === "completed" ? segmentedState(job) : null;
    if (!state) return;
    this.state = state;
    if (!preserveDirty) this.dirty = false;
    if (!this.dirty && state.configured_segments !== null) {
      this.countInput.value = String(state.configured_segments);
    }
    this.renderState();
  }

  renderState() {
    const segmented = this.state?.mode === "segmented";
    const known = this.state?.mode === "segmented" || this.state?.mode === "realtime";
    this.status.className = `state-indicator ${segmented ? "state-ok" : "state-idle"} segmented-editor-status`;
    this.statusText.textContent = known
      ? translate(segmented ? "status.active" : "status.inactive")
      : translate("segmented.editor.unknown");
    this.modeOutput.output.textContent = known
      ? modeLabel(this.state.mode)
      : translate("segmented.editor.unknown");
    this.configuredRow.label.hidden = !segmented;
    this.configuredRow.output.hidden = !segmented;
    this.acquiredRow.label.hidden = !segmented;
    this.acquiredRow.output.hidden = !segmented;
    this.configuredRow.output.textContent = segmented ? String(this.state.configured_segments) : "";
    this.acquiredRow.output.textContent = segmented ? String(this.state.acquired_segments) : "";
    const browserAvailable = this.browserAvailable();
    this.segmentBrowser.hidden = !browserAvailable;
    if (browserAvailable) {
      this.segmentInput.max = String(this.state.acquired_segments);
      this.segmentInput.value = String(this.state.selected_segment);
      this.segmentTotal.textContent = `/ ${this.state.acquired_segments}`;
      this.timeTagOutput.textContent = `${String(this.state.time_tag_s)} s`;
    } else {
      this.segmentInput.max = "";
      this.segmentInput.value = "";
      this.segmentTotal.textContent = "";
      this.timeTagOutput.textContent = "";
    }
    this.enterButton.textContent = translate(
      segmented ? "segmented.editor.applyEnter" : "segmented.editor.enter",
    );
    this.exitButton.hidden = !segmented;
    const unsupported = !this.definition() || !this.catalog.supported(this.definition());
    this.unavailableNote.hidden = !unsupported;
    this.readouts.hidden = unsupported;
    this.countInput.parentNode.hidden = unsupported;
    this.enterButton.parentNode.hidden = unsupported;
    if (unsupported) this.segmentBrowser.hidden = true;
    this.captureSection.hidden = unsupported || !this.captureSupported();
  }

  browserAvailable() {
    return this.state?.mode === "segmented"
      && Number.isInteger(this.state?.acquired_segments)
      && this.state.acquired_segments > 0
      && Number.isInteger(this.state?.selected_segment);
  }

  canExecute() {
    return !this.busy && !this.hooks.isExecutionBusy?.() && this.hooks.isAvailable();
  }

  setBusy(value) {
    this.busy = value;
    this.applyBusyState();
  }

  applyBusyState() {
    const disabled = this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable();
    this.refreshButton.disabled = disabled;
    this.countInput.disabled = disabled;
    this.enterButton.disabled = disabled;
    this.exitButton.disabled = disabled;
    const browserAvailable = this.browserAvailable();
    const selected = this.state?.selected_segment;
    const acquired = this.state?.acquired_segments;
    this.segmentInput.disabled = disabled || !browserAvailable;
    this.previousButton.disabled = disabled || !browserAvailable || selected <= 1;
    this.nextButton.disabled = disabled || !browserAvailable || selected >= acquired;
    this.selectButton.disabled = disabled
      || !browserAvailable
      || !this.segmentInput.checkValidity();
    const captureDisabled = disabled || !this.captureSupported();
    this.captureChannelInput.disabled = captureDisabled;
    this.captureSegmentsInput.disabled = captureDisabled;
    this.capturePointsSelect.disabled = captureDisabled;
    this.captureFormatSelect.disabled = captureDisabled;
    this.captureButton.disabled = !this.canCapture();
  }
}
