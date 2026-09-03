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

    this.unavailableNote = document.createElement("p");
    this.unavailableNote.className = "muted compact-note";
    this.unavailableNote.textContent = translate("segmented.editor.unavailable");
    this.container.append(head, this.unavailableNote, this.readouts, countField, actions);
    this.applyDefinition();
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
    const value = this.countInput?.value || "";
    this.buildDom();
    if (value !== "") this.countInput.value = value;
    this.present();
  }

  present() {
    const key = this.hooks.contextKey();
    if (key !== this.contextKey) {
      this.contextKey = key;
      this.state = null;
      this.dirty = false;
      this.countInput.value = "";
    }
    this.applyDefinition();
    this.renderState();
    this.applyBusyState();
  }

  async refresh() {
    if (!this.canExecute()) return;
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        "segmented-memory",
        { action: "query" },
        { intent: "readback" },
      );
      this.acceptJob(job, true);
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
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        "segmented-memory",
        { action: "enable", segments },
        { intent: "apply" },
      );
      this.acceptJob(job, false);
    } finally {
      this.setBusy(false);
    }
  }

  async exit() {
    if (!this.canExecute()) return;
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        "segmented-memory",
        { action: "disable" },
        { intent: "apply" },
      );
      this.acceptJob(job, true);
    } finally {
      this.setBusy(false);
    }
  }

  acceptJob(job, preserveDirty) {
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
    this.enterButton.textContent = translate(
      segmented ? "segmented.editor.applyEnter" : "segmented.editor.enter",
    );
    this.exitButton.hidden = !segmented;
    const unsupported = !this.definition() || !this.catalog.supported(this.definition());
    this.unavailableNote.hidden = !unsupported;
    this.readouts.hidden = unsupported;
    this.countInput.parentNode.hidden = unsupported;
    this.enterButton.parentNode.hidden = unsupported;
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
  }
}
