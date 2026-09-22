import { hasTranslation, translate } from "/static/i18n.js";

function segmentedState(job) {
  return job?.result?.result?.segmented ?? job?.result?.segmented ?? null;
}

function modeLabel(mode) {
  const key = `enum.${String(mode)}`;
  return hasTranslation(key) ? translate(key) : String(mode);
}

function channelLabel(channel) {
  const key = `enum.channel${channel}`;
  return hasTranslation(key) ? translate(key) : `CH${channel}`;
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
    this.captureBlocked = false;
    this.buildDom();
  }

  buildDom() {
    this.refreshButton?.remove?.();
    this.modeButton?.remove?.();
    this.captureButton?.remove?.();
    this.container.replaceChildren();

    const head = document.createElement("div");
    head.className = "segmented-editor-head";
    const heading = document.createElement("strong");
    heading.textContent = translate("command.segmented-memory");
    this.heading = heading;
    head.append(heading);

    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary";
    this.refreshButton.textContent = translate("segmented.editor.read");
    this.refreshButton.addEventListener("click", () => void this.refresh());
    if (this.hooks.headerActions) {
      this.refreshButton.hidden = true;
      this.hooks.headerActions.append(this.refreshButton);
    } else {
      head.append(this.refreshButton);
    }

    this.modeButton = document.createElement("button");
    this.modeButton.type = "button";
    this.modeButton.className = "primary";
    this.modeButton.addEventListener("click", () => void this.toggleMode());
    if (this.hooks.headerActions) {
      this.modeButton.hidden = true;
      this.hooks.headerActions.append(this.modeButton);
    } else {
      head.append(this.modeButton);
    }

    this.readouts = document.createElement("dl");
    this.readouts.className = "segmented-editor-state";
    this.modeOutput = this.appendReadout("segmented.editor.mode");
    this.configuredRow = this.appendReadout("segmented.editor.configuredSegments");
    this.acquiredRow = this.appendReadout("segmented.editor.acquiredSegments");
    const stateHelp = document.createElement("small");
    stateHelp.className = "field-help";
    stateHelp.textContent = translate("segmented.editor.stateHelp");
    this.stateHelp = stateHelp;
    this.stateSection = document.createElement("div");
    this.stateSection.className = "segmented-editor-state-section";
    this.stateSection.append(this.readouts, stateHelp);

    const countRow = document.createElement("div");
    countRow.className = "segmented-editor-actions segmented-editor-count-row";
    this.countRow = countRow;
    const countField = document.createElement("label");
    countField.className = "field segmented-editor-count";
    const countLabel = document.createElement("span");
    countLabel.textContent = translate("segmented.editor.targetSegments");
    this.countInput = document.createElement("input");
    this.countInput.type = "number";
    this.countInput.step = "1";
    this.countInput.required = true;
    this.countInput.addEventListener("input", () => {
      this.dirty = true;
      this.applyBusyState();
    });
    countField.append(countLabel, this.countInput);
    this.applySegmentsButton = document.createElement("button");
    this.applySegmentsButton.type = "button";
    this.applySegmentsButton.className = "secondary";
    this.applySegmentsButton.textContent = translate("segmented.editor.applySegments");
    this.applySegmentsButton.addEventListener("click", () => void this.enter());
    countRow.append(countField, this.applySegmentsButton);
    this.appendFieldHelp(countRow, this.fieldDefinition(this.segmentedMemoryDefinition(), "segments"));

    this.overview = document.createElement("div");
    this.overview.className = "segmented-editor-overview";
    this.memoryDivider = document.createElement("div");
    this.memoryDivider.className = "segmented-editor-divider";
    this.overview.append(this.stateSection, this.memoryDivider, countRow);

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
    this.segmentBrowser.append(browserLabel, browserControls);
    this.appendFieldHelp(
      this.segmentBrowser,
      this.fieldDefinition(this.segmentedMemoryDefinition(), "index"),
    );
    this.segmentBrowser.append(timeTag);

    this.captureSection = document.createElement("section");
    this.captureSection.className = "segmented-editor-browser";
    const captureHeading = document.createElement("strong");
    captureHeading.textContent = translate("segmented.editor.captureTitle");
    this.captureForm = document.createElement("div");
    this.captureForm.className = "command-form segmented-editor-capture-form";
    const captureDefinition = this.captureDefinition();
    const captureChannelField = document.createElement("label");
    captureChannelField.className = "field";
    const captureChannelLabel = document.createElement("span");
    captureChannelLabel.textContent = translate("field.channel");
    this.captureChannelSelect = document.createElement("select");
    this.captureChannelSelect.required = true;
    captureChannelField.append(captureChannelLabel, this.captureChannelSelect);
    this.appendFieldHelp(
      captureChannelField,
      this.fieldDefinition(captureDefinition, "channel"),
    );
    const capturePointsField = document.createElement("label");
    capturePointsField.className = "field";
    const capturePointsLabel = document.createElement("span");
    capturePointsLabel.textContent = translate("field.points");
    this.capturePointsSelect = document.createElement("select");
    this.capturePointsSelect.required = true;
    capturePointsField.append(capturePointsLabel, this.capturePointsSelect);
    this.appendFieldHelp(
      capturePointsField,
      this.fieldDefinition(captureDefinition, "points"),
    );
    const captureFormatField = document.createElement("label");
    captureFormatField.className = "field";
    const captureFormatLabel = document.createElement("span");
    captureFormatLabel.textContent = translate("field.format");
    this.captureFormatSelect = document.createElement("select");
    this.captureFormatSelect.required = true;
    captureFormatField.append(captureFormatLabel, this.captureFormatSelect);
    this.appendFieldHelp(
      captureFormatField,
      this.fieldDefinition(captureDefinition, "format"),
    );
    this.captureButton = document.createElement("button");
    this.captureButton.type = "button";
    this.captureButton.className = "primary";
    this.captureButton.textContent = translate("segmented.editor.capture");
    this.captureButton.addEventListener("click", () => void this.capture());
    if (this.hooks.headerActions) {
      this.captureButton.hidden = true;
      this.hooks.headerActions.append(this.captureButton);
    }
    this.captureSection.append(captureHeading);
    const captureDescription = translate("segmented.editor.captureDescription");
    if (captureDescription) {
      const note = document.createElement("p");
      note.className = "muted compact-note";
      note.textContent = captureDescription;
      this.captureSection.append(note);
    }
    this.captureNote = document.createElement("p");
    this.captureNote.className = "muted compact-note";
    this.captureNote.hidden = true;
    this.captureSection.append(this.captureNote);
    const planningRow = document.createElement("div");
    planningRow.className = "segmented-editor-actions segmented-editor-count-row";
    this.planningRow = planningRow;
    const planningField = document.createElement("label");
    planningField.className = "field segmented-editor-count";
    const planningLabel = document.createElement("span");
    planningLabel.textContent = translate("segmented.capture.planningSegments");
    this.planningSegmentsInput = document.createElement("input");
    this.planningSegmentsInput.type = "number";
    this.planningSegmentsInput.step = "1";
    this.planningSegmentsInput.required = true;
    planningField.append(planningLabel, this.planningSegmentsInput);
    planningRow.append(planningField);
    this.appendFieldHelp(
      planningRow,
      this.fieldDefinition(this.captureDefinition(), "segments"),
    );
    this.captureSection.append(planningRow);
    this.captureForm.append(
      captureChannelField,
      capturePointsField,
      captureFormatField,
    );
    this.captureSection.append(this.captureForm);
    if (!this.hooks.headerActions) {
      const captureActions = document.createElement("div");
      captureActions.className = "segmented-editor-actions";
      captureActions.append(this.captureButton);
      this.captureSection.append(captureActions);
    }

    this.unavailableNote = document.createElement("p");
    this.unavailableNote.className = "muted compact-note";
    this.unavailableNote.textContent = translate("segmented.editor.unavailable");
    this.container.append(
      head,
      this.unavailableNote,
      this.overview,
      this.segmentBrowser,
      this.captureSection,
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

  fieldDefinition(definition, name) {
    if (!definition) return null;
    const fields = this.catalog.fieldsFor?.(definition) || definition.fields || [];
    return fields.find((field) => field.name === name) || null;
  }

  appendFieldHelp(container, field) {
    if (!field || (!field.help && !field.help_key)) return;
    const helpKey = field.help_key ? `help.${field.help_key}` : `help.${field.name}`;
    const text = hasTranslation(helpKey) ? translate(helpKey) : field.help;
    if (!text) return;
    const help = document.createElement("small");
    help.className = "field-help";
    help.textContent = text;
    container.append(help);
  }

  definition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "segmented" ? selected : null;
  }

  segmentedMemoryDefinition() {
    const commands = this.catalog?.commands;
    if (!Array.isArray(commands)) return null;
    return commands.find((command) => command.id === "segmented-memory") || null;
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

  selectedView() {
    const selected = this.hooks.selectedCommand?.();
    if (selected?.editor !== "segmented") return null;
    if (selected.id === "segmented-memory") return "memory";
    if (selected.id === "segmented-capture") return "capture";
    return null;
  }

  isDryRun() {
    return this.catalog?.activeMode === "dry-run";
  }

  captureChannels() {
    const definition = this.captureDefinition();
    const fields = definition ? this.catalog.fieldsFor(definition) : [];
    const channelField = fields.find((field) => field?.name === "channel") || {};
    const rawOptions = this.catalog.optionsFor
      ? this.catalog.optionsFor(channelField)
      : channelField.options || [];
    const projected = [...new Set(
      [...(rawOptions || [])].map(Number).filter((value) => Number.isInteger(value) && value > 0),
    )].sort((first, second) => first - second);
    if (projected.length) return projected;
    const minimum = Number(channelField.minimum);
    const maximum = Number(channelField.maximum);
    if (
      Number.isInteger(minimum) && Number.isInteger(maximum)
      && minimum > 0 && maximum >= minimum
    ) {
      return Array.from({ length: maximum - minimum + 1 }, (_, index) => minimum + index);
    }
    return [];
  }

  applyCaptureDefinition(contextChanged = false) {
    const definition = this.captureDefinition();
    const fields = definition ? this.catalog.fieldsFor(definition) : [];
    const fieldByName = (name) => fields.find((field) => field.name === name);
    const channelField = fieldByName("channel");
    const pointsField = fieldByName("points");
    const formatField = fieldByName("format");
    const channels = this.captureChannels();
    const previousChannel = this.captureChannelSelect.value;
    this.captureChannelSelect.replaceChildren(...channels.map((channel) => {
      const item = document.createElement("option");
      item.value = String(channel);
      item.textContent = channelLabel(channel);
      return item;
    }));
    if (!contextChanged && channels.map(String).includes(previousChannel)) {
      this.captureChannelSelect.value = previousChannel;
    } else {
      const initial = channelField?.default ?? channels[0] ?? "";
      this.captureChannelSelect.value = initial === "" ? "" : String(initial);
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
    const definition = this.segmentedMemoryDefinition();
    const segmentField = definition
      ? this.catalog.fieldsFor(definition).find((field) => field.name === "segments")
      : null;
    this.countInput.min = String(segmentField?.minimum ?? "");
    this.countInput.max = String(segmentField?.maximum ?? "");
    if (!this.countInput.value && segmentField?.minimum !== undefined) {
      this.countInput.value = String(segmentField.minimum);
    }
    const captureSegmentsField = this.fieldDefinition(this.captureDefinition(), "segments");
    this.planningSegmentsInput.min = String(captureSegmentsField?.minimum ?? "");
    this.planningSegmentsInput.max = String(captureSegmentsField?.maximum ?? "");
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    const countValue = this.countInput?.value || "";
    const segmentValue = this.segmentInput?.value || "";
    const captureChannel = this.captureChannelSelect?.value || "";
    const capturePoints = this.capturePointsSelect?.value || "";
    const captureFormat = this.captureFormatSelect?.value || "";
    const planningValue = this.planningSegmentsInput?.value || "";
    const contextKey = this.contextKey;
    this.buildDom();
    if (countValue !== "") this.countInput.value = countValue;
    if (planningValue !== "") this.planningSegmentsInput.value = planningValue;
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
          this.captureChannelSelect.value = captureChannel;
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
      this.captureBlocked = false;
      this.planningSegmentsInput.value = "";
    }
    if (this.selectedView() !== "capture") this.captureBlocked = false;
    this.applyDefinition();
    this.applyCaptureDefinition(contextChanged);
    this.renderState();
    this.applyBusyState();
  }

  async refresh() {
    if (this.selectedView() !== "memory" || !this.canExecute()) return;
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

  async toggleMode() {
    if (this.selectedView() !== "memory" || !this.canExecute()) return;
    if (this.state?.mode === "segmented") {
      await this.exit();
    } else if (this.state?.mode === "realtime") {
      await this.enter();
    }
  }

  async enter() {
    if (this.selectedView() !== "memory" || !this.canExecute()) return;
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
    if (this.selectedView() !== "memory" || !this.canExecute()) return;
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
    if (this.selectedView() !== "capture") return false;
    if (!this.captureSupported() || !this.canExecute()) return false;
    if (this.isDryRun()) {
      return this.captureChannelSelect?.value !== ""
        && this.capturePointsSelect?.value !== ""
        && this.captureFormatSelect?.value !== ""
        && this.planningSegmentsInput?.value !== ""
        && this.captureChannelSelect?.checkValidity()
        && this.planningSegmentsInput?.checkValidity();
    }
    return this.captureChannelSelect?.value !== ""
      && this.capturePointsSelect?.value !== ""
      && this.captureFormatSelect?.value !== ""
      && this.captureChannelSelect?.checkValidity();
  }

  planningSegments() {
    const segments = Number(this.planningSegmentsInput.value);
    return Number.isInteger(segments) ? segments : null;
  }

  async capture() {
    if (this.selectedView() !== "capture" || !this.canExecute()) return;
    if (!this.canCapture()) {
      this.captureChannelSelect?.reportValidity?.();
      if (this.isDryRun()) this.planningSegmentsInput?.reportValidity?.();
      return;
    }
    const channel = Number(this.captureChannelSelect.value);
    const points = Number(this.capturePointsSelect.value);
    const format = String(this.captureFormatSelect.value).toLowerCase();
    if (!Number.isInteger(channel) || !Number.isInteger(points)) {
      return;
    }
    if (this.isDryRun()) {
      // Dry-run has no instrument state: never query segmented-memory here.
      // The planning-only segment count feeds the existing dry-run capture
      // contract directly.
      const segments = this.planningSegments();
      if (segments === null) {
        this.planningSegmentsInput?.reportValidity?.();
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
      return;
    }
    this.setBusy(true);
    try {
      // Starting a capture invalidates the Memory workspace cache immediately.
      // The explicit prerequisite query is only the execution source for this
      // capture; it must not repopulate Memory state or its workspace result.
      this.state = null;
      this.captureBlocked = false;
      this.renderState();
      const submittedContextKey = this.contextKey;
      const queryJob = await this.hooks.executeCommand(
        "segmented-memory",
        { action: "query" },
        { intent: "readback", captureWorkspaceResult: false },
      );
      if (submittedContextKey !== this.hooks.contextKey()) return;
      if (queryJob?.status !== "completed") return;
      const memoryState = segmentedState(queryJob);
      const configured = memoryState?.configured_segments;
      if (memoryState?.mode !== "segmented" || !Number.isInteger(configured)) {
        this.captureBlocked = true;
        this.renderState();
        return;
      }
      await this.hooks.executeCommand(
        "segmented-capture",
        { channel, segments: configured, points, format },
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
    if (this.selectedView() !== "memory" || !this.browserAvailable() || !this.canExecute()) return;
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
    if (this.selectedView() !== "memory" || !this.browserAvailable() || !this.canExecute()) return;
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
    const view = this.selectedView();
    const segmented = this.state?.mode === "segmented";
    const realtime = this.state?.mode === "realtime";
    const known = segmented || realtime;
    this.heading.textContent = translate(
      view === "capture" ? "command.segmented-capture" : "command.segmented-memory",
    );
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
    this.modeButton.textContent = translate(
      segmented ? "segmented.editor.exit" : "segmented.editor.enter",
    );
    this.modeButton.className = segmented ? "secondary" : "primary";
    const unsupported = !this.definition() || !this.catalog.supported(this.definition());
    const memoryView = view === "memory" && !unsupported;
    const captureView = view === "capture" && !unsupported && this.captureSupported();
    this.modeButton.hidden = !memoryView || !known;
    this.applySegmentsButton.hidden = !memoryView || !segmented;
    this.stateHelp.hidden = !memoryView || !segmented;
    this.unavailableNote.hidden = !unsupported;
    this.overview.hidden = !memoryView;
    this.readouts.hidden = !memoryView;
    this.countRow.hidden = !memoryView;
    this.segmentBrowser.hidden = !memoryView || !browserAvailable;
    this.captureSection.hidden = !captureView;
    const dryRun = this.isDryRun();
    this.planningRow.hidden = !captureView || !dryRun;
    if (this.captureBlocked) {
      this.captureNote.textContent = translate("segmented.capture.notReady");
      this.captureNote.hidden = view !== "capture";
    } else {
      this.captureNote.hidden = true;
    }
  }

  browserAvailable() {
    return this.state?.mode === "segmented"
      && Number.isInteger(this.state?.acquired_segments)
      && this.state.acquired_segments > 0
      && Number.isInteger(this.state?.selected_segment);
  }

  countPending() {
    if (this.state?.mode !== "segmented") return false;
    const configuredRaw = this.state?.configured_segments;
    if (configuredRaw === null || configuredRaw === undefined) return false;
    const rawValue = this.countInput.value;
    if (rawValue === "") return false;

    const value = Number(rawValue);
    const configured = Number(configuredRaw);
    const validity = this.countInput.validity;
    const valid = validity ? validity.valid : this.countInput.checkValidity();
    return Number.isInteger(value)
      && Number.isInteger(configured)
      && valid
      && value !== configured;
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
    this.modeButton.disabled = disabled;
    const countPending = this.countPending();
    this.applySegmentsButton.disabled = disabled || !countPending;
    this.applySegmentsButton.className = countPending ? "primary" : "secondary";
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
    this.captureChannelSelect.disabled = captureDisabled;
    this.capturePointsSelect.disabled = captureDisabled;
    this.captureFormatSelect.disabled = captureDisabled;
    this.planningSegmentsInput.disabled = captureDisabled;
    this.captureButton.disabled = !this.canCapture();
  }
}
