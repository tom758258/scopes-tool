import { translate } from "/static/i18n.js";

const RANGE_COMMAND = "external-trigger-range";
const LEVEL_COMMAND = "trigger-edge-external-level";

function payloadOf(job) {
  return job?.result?.result ?? job?.result;
}

function rangeFromPayload(payload) {
  const range = payload?.range?.range_volts ?? payload?.range_volts;
  return typeof range === "number" && Number.isFinite(range) && range > 0 ? range : null;
}

function levelFromPayload(payload) {
  const level = payload?.level?.level_volts ?? payload?.level_volts;
  return typeof level === "number" && Number.isFinite(level) ? level : null;
}

export class ExternalTriggerEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.stateKey = null;
    this.revision = 0;
    this.mode = "range";
    this.rangeRead = null;
    this.levelRead = null;
    this.rangeValue = null;
    this.buildDom();
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "external-trigger" ? selected : null;
  }

  currentStateKey() {
    return `${this.hooks.contextKey()}|${this.selectedDefinition()?.id || ""}`;
  }

  modeForCommand(id) {
    return id === LEVEL_COMMAND ? "level" : "range";
  }

  buildDom() {
    this.container.replaceChildren();

    // 0. Section intro with shared read-first help (no extra heading to avoid duplicate Parameters).
    this.introSection = document.createElement("div");
    this.introSection.className = "workflow-editor-section";
    this.introHelp = document.createElement("small");
    this.introHelp.className = "muted compact-note";
    this.introHelp.textContent = translate("external-trigger.editor.readFirstHelp");
    this.introSection.append(this.introHelp);

    // 1. Range / Level mode selector (mutually exclusive, follows the selected command)
    this.modeSelector = document.createElement("div");
    this.modeSelector.className = "trigger-editor-segmented external-trigger-mode";
    this.modeButtons = {};
    for (const key of ["range", "level"]) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.dataset.mode = key;
      button.textContent = translate(`external-trigger.editor.mode${key === "range" ? "Range" : "Level"}`);
      button.addEventListener("click", () => {
        this.setMode(key);
      });
      this.modeSelector.append(button);
      this.modeButtons[key] = button;
    }

    // 2. Range section
    this.rangeSection = document.createElement("div");
    this.rangeSection.className = "trigger-editor-section";

    this.rangeHeading = document.createElement("strong");
    this.rangeHeading.className = "trigger-editor-heading";
    this.rangeHeading.textContent = translate("external-trigger.editor.modeRange");

    this.rangeField = document.createElement("label");
    this.rangeField.className = "field external-trigger-value";
    this.rangeFieldLabel = document.createElement("span");
    this.rangeFieldLabel.textContent = translate("field.channel-range.value");
    this.rangeInput = document.createElement("input");
    this.rangeInput.type = "text";
    this.rangeInput.inputMode = "decimal";
    this.rangeInput.dataset.field = "range_volts";
    this.rangeField.append(this.rangeFieldLabel, this.rangeInput);

    this.rangeHelp = document.createElement("small");
    this.rangeHelp.className = "field-help";
    this.rangeHelp.textContent = translate("help.external-trigger-range.range_volts");

    this.rangeSection.append(this.rangeHeading, this.rangeField, this.rangeHelp);

    // 3. Level section
    this.levelSection = document.createElement("div");
    this.levelSection.className = "trigger-editor-section";

    this.levelHeading = document.createElement("strong");
    this.levelHeading.className = "trigger-editor-heading";
    this.levelHeading.textContent = translate("external-trigger.editor.modeLevel");

    this.levelField = document.createElement("label");
    this.levelField.className = "field external-trigger-value";
    this.levelFieldLabel = document.createElement("span");
    this.levelFieldLabel.textContent = translate("field.level");
    this.levelInput = document.createElement("input");
    this.levelInput.type = "text";
    this.levelInput.inputMode = "decimal";
    this.levelInput.dataset.field = "level";
    this.levelField.append(this.levelFieldLabel, this.levelInput);

    this.levelHelp = document.createElement("small");
    this.levelHelp.className = "field-help";
    this.levelHelp.textContent = translate("external-trigger.editor.levelDescription");

    this.levelSection.append(this.levelHeading, this.levelField, this.levelHelp);

    // 4. Single Read / Apply pair in the content area, routed by the current mode
    this.actions = document.createElement("div");
    this.actions.style.display = "flex";
    this.actions.style.gap = "8px";
    this.actions.style.marginTop = "6px";

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
      this.introSection,
      this.modeSelector,
      this.rangeSection,
      this.levelSection,
    );
    if (this.hooks.headerActions) {
      this.readButton.hidden = true;
      this.applyButton.hidden = true;
      this.hooks.headerActions.append(this.readButton, this.applyButton);
    } else {
      this.actions.append(this.readButton, this.applyButton);
      this.container.append(this.actions);
    }

    this.stateKey = null;
    this.renderMode();
    this.schedulePresentation();
  }

  setMode(mode) {
    if (mode === this.mode) return;
    this.revision += 1;
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
    this.rangeSection.hidden = this.mode !== "range";
    this.levelSection.hidden = this.mode !== "level";
  }

  readCurrent() {
    if (this.mode === "range") return this.readRange();
    return this.readLevel();
  }

  applyCurrent() {
    if (this.mode === "range") return this.applyRange();
    return this.applyLevel();
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  deactivate() {
    this.stateKey = null;
    this.revision += 1;
    this.mode = "range";
    this.rangeInput.value = "";
    this.levelInput.value = "";
    this.levelInput.setCustomValidity?.("");
    this.clearReadState();
    this.renderMode();
  }

  rerender() {
    this.introHelp.textContent = translate("external-trigger.editor.readFirstHelp");
    this.rangeHeading.textContent = translate("external-trigger.editor.modeRange");
    this.rangeFieldLabel.textContent = translate("field.channel-range.value");
    this.rangeHelp.textContent = translate("help.external-trigger-range.range_volts");
    this.levelHeading.textContent = translate("external-trigger.editor.modeLevel");
    this.levelFieldLabel.textContent = translate("field.level");
    this.levelHelp.textContent = translate("external-trigger.editor.levelDescription");
    this.readButton.textContent = translate("actions.readSettings");
    this.applyButton.textContent = translate("actions.apply");
    this.modeButtons.range.textContent = translate("external-trigger.editor.modeRange");
    this.modeButtons.level.textContent = translate("external-trigger.editor.modeLevel");
    this.renderMode();
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
    this.mode = this.modeForCommand(this.selectedDefinition().id);
    this.rangeInput.value = "";
    this.levelInput.value = "";
    this.levelInput.setCustomValidity?.("");
    this.clearReadState();
    this.renderMode();
    this.applyBusyState();
  }

  clearReadState() {
    this.rangeRead = null;
    this.levelRead = null;
    this.rangeValue = null;
  }

  clearLevelRead() {
    this.levelRead = null;
    this.levelInput.value = "";
    this.levelInput.setCustomValidity?.("");
  }

  currentCommandId() {
    return this.selectedDefinition()?.id || null;
  }

  async readRange() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return null;
    if (!this.selectedDefinition()) return null;

    const contextKey = this.hooks.contextKey();
    const commandId = this.currentCommandId();
    const revision = this.revision;

    this.busy = true;
    this.applyBusyState();
    try {
      const job = await this.hooks.executeCommand(
        RANGE_COMMAND,
        { action: "query" },
        { intent: "readback" },
      );

      if (
        revision !== this.revision
        || this.hooks.contextKey() !== contextKey
        || this.currentCommandId() !== commandId
        || !this.selectedDefinition()
      ) {
        return job;
      }
      if (job?.status !== "completed") {
        this.rangeRead = null;
        return job;
      }

      const value = rangeFromPayload(payloadOf(job));
      if (value === null) {
        this.rangeRead = null;
        return job;
      }
      this.rangeInput.value = String(value);
      this.rangeRead = value;
      this.rangeValue = value;
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
    const commandId = this.currentCommandId();
    const revision = this.revision;

    this.busy = true;
    this.applyBusyState();
    try {
      const job = await this.hooks.executeCommand(
        RANGE_COMMAND,
        { action: "set", range_volts: value },
        { intent: "apply" },
      );

      if (
        revision !== this.revision
        || job?.status !== "completed"
        || this.hooks.contextKey() !== contextKey
        || this.currentCommandId() !== commandId
        || !this.selectedDefinition()
      ) {
        return job;
      }

      // Use readback from the successful set command to update the same field
      const actual = rangeFromPayload(payloadOf(job));
      if (actual !== null) {
        this.rangeInput.value = String(actual);
        this.rangeRead = actual;
        this.rangeValue = actual;
      }
      // A new range can move a previously read level out of bounds, so the
      // level side must be read again before it can be trusted or applied.
      this.clearLevelRead();
      return job;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  async readLevel() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return null;
    if (!this.selectedDefinition()) return null;

    const contextKey = this.hooks.contextKey();
    const commandId = this.currentCommandId();
    const revision = this.revision;

    this.busy = true;
    this.applyBusyState();
    try {
      this.levelInput.setCustomValidity?.("");
      const job = await this.hooks.executeCommand(
        LEVEL_COMMAND,
        { action: "query" },
        { intent: "readback" },
      );

      if (
        revision !== this.revision
        || this.hooks.contextKey() !== contextKey
        || this.currentCommandId() !== commandId
        || !this.selectedDefinition()
      ) {
        return job;
      }
      if (job?.status !== "completed") {
        this.levelRead = null;
        return job;
      }

      const level = levelFromPayload(payloadOf(job));
      if (level === null) {
        this.levelRead = null;
        return job;
      }

      const rangeJob = await this.hooks.executeCommand(
        RANGE_COMMAND,
        { action: "query" },
        { intent: "readback" },
      );
      if (
        revision !== this.revision
        || this.hooks.contextKey() !== contextKey
        || this.currentCommandId() !== commandId
        || !this.selectedDefinition()
      ) {
        return rangeJob;
      }
      const range = rangeJob?.status === "completed" ? rangeFromPayload(payloadOf(rangeJob)) : null;
      if (range === null) {
        this.levelRead = null;
        this.rangeValue = null;
        this.levelInput.setCustomValidity?.(translate("system.readFailed"));
        this.levelInput.reportValidity?.();
        return rangeJob;
      }
      this.levelInput.value = String(level);
      this.levelRead = level;
      this.rangeValue = range;
      return rangeJob;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  async applyLevel() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return null;
    if (!this.selectedDefinition()) return null;

    this.levelInput.setCustomValidity?.("");

    const raw = this.levelInput.value.trim();
    if (!raw) return null;

    const value = Number(raw);
    if (!Number.isFinite(value)) return null;

    const contextKey = this.hooks.contextKey();
    const commandId = this.currentCommandId();
    const revision = this.revision;

    this.busy = true;
    this.applyBusyState();
    try {
      this.levelInput.setCustomValidity?.("");
      // Always validate against the currently reported range, never a cached one.
      const rangeJob = await this.hooks.executeCommand(
        RANGE_COMMAND,
        { action: "query" },
        { intent: "readback" },
      );
      if (
        revision !== this.revision
        || this.hooks.contextKey() !== contextKey
        || this.currentCommandId() !== commandId
        || !this.selectedDefinition()
      ) {
        return rangeJob;
      }
      const range = rangeJob?.status === "completed" ? rangeFromPayload(payloadOf(rangeJob)) : null;
      if (range === null) {
        this.rangeValue = null;
        this.levelInput.setCustomValidity?.(translate("system.readFailed"));
        this.levelInput.reportValidity?.();
        return rangeJob;
      }
      this.rangeValue = range;
      if (value < -range || value > range) {
        this.levelInput.setCustomValidity?.(translate("external-trigger.editor.levelOutOfRange", {
          min: String(-range),
          max: String(range),
        }));
        this.levelInput.reportValidity?.();
        return null;
      }

      const job = await this.hooks.executeCommand(
        LEVEL_COMMAND,
        { action: "set", level: value },
        { intent: "apply" },
      );

      if (
        revision !== this.revision
        || job?.status !== "completed"
        || this.hooks.contextKey() !== contextKey
        || this.currentCommandId() !== commandId
        || !this.selectedDefinition()
      ) {
        return job;
      }

      // Use readback from the successful set command to update the same field
      const actual = levelFromPayload(payloadOf(job));
      if (actual !== null) {
        this.levelInput.value = String(actual);
        this.levelRead = actual;
      }
      return job;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  applyBusyState() {
    const disabled = this.busy
      || this.hooks.isExecutionBusy?.()
      || !this.hooks.isAvailable?.()
      || !this.selectedDefinition();
    this.rangeInput.disabled = disabled;
    this.levelInput.disabled = disabled;
    this.readButton.disabled = disabled;
    this.applyButton.disabled = disabled;
    for (const button of Object.values(this.modeButtons)) {
      button.disabled = disabled;
    }
  }
}
