import { hasTranslation, translate } from "/static/i18n.js";

function slotLabel(slot) {
  const key = "enum.reference-waveform";
  return hasTranslation(key) ? translate(key, { value: slot }) : `Reference ${slot}`;
}

function displayState(job) {
  return job?.result?.result?.display ?? job?.result?.display ?? null;
}

export class ReferenceDisplayEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.stateKey = null;
    this.slots = [];
    this.entries = [];
    this.buildDom();
  }

  definition() {
    return this.catalog.commands.find((command) => command.id === "reference-display") || null;
  }

  displaySlots() {
    const definition = this.definition();
    if (!definition) return [];
    const fields = this.catalog.fieldsFor
      ? this.catalog.fieldsFor(definition)
      : definition.fields || [];
    const slotField = fields.find((field) => field.name === "slot") || {};
    const options = this.catalog.optionsFor
      ? this.catalog.optionsFor(slotField)
      : slotField.options || [];
    return [...options]
      .map(Number)
      .filter((slot) => Number.isInteger(slot) && slot > 0)
      .sort((left, right) => left - right);
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "reference-display" ? selected : null;
  }

  currentStateKey() {
    return `${this.hooks.contextKey()}|${this.selectedDefinition()?.id || ""}`;
  }

  buildDom() {
    this.refreshButton?.remove?.();
    this.runButton?.remove?.();
    this.container.replaceChildren();
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary trigger-editor-refresh";
    this.refreshButton.textContent = translate("actions.readSettings");
    this.refreshButton.addEventListener("click", () => {
      void this.read();
    });
    if (this.hooks.headerActions) {
      this.refreshButton.hidden = true;
      this.hooks.headerActions.append(this.refreshButton);
    } else {
      this.container.append(this.refreshButton);
    }
    this.section = document.createElement("div");
    this.section.className = "workflow-editor-section";
    this.heading = document.createElement("strong");
    this.heading.className = "workflow-editor-heading";
    this.heading.textContent = translate("reference-display.editor.displayedReferences");
    this.choicesHost = document.createElement("div");
    this.choicesHost.className = "workflow-editor-choices";
    this.helper = document.createElement("small");
    this.helper.className = "muted compact-note";
    this.helper.textContent = translate("reference-display.editor.displayHelper");
    this.section.append(this.heading, this.choicesHost, this.helper);
    this.runButton = document.createElement("button");
    this.runButton.type = "button";
    this.runButton.className = "primary trigger-editor-action";
    this.runButton.textContent = translate("actions.run");
    this.runButton.addEventListener("click", () => {
      void this.run();
    });
    this.status = document.createElement("output");
    this.status.className = "muted compact-note";
    if (this.hooks.headerActions) {
      this.runButton.hidden = true;
      this.hooks.headerActions.append(this.runButton);
      this.container.append(this.section, this.status);
    } else {
      this.container.append(this.section, this.runButton, this.status);
    }
    this.stateKey = null;
    this.schedulePresentation();
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    this.refreshButton.textContent = translate("actions.readSettings");
    this.runButton.textContent = translate("actions.run");
    this.heading.textContent = translate("reference-display.editor.displayedReferences");
    this.helper.textContent = translate("reference-display.editor.displayHelper");
    for (const entry of this.entries) entry.text.textContent = slotLabel(entry.slot);
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
    this.status.textContent = "";
    this.rebuild();
    this.applyBusyState();
  }

  rebuild() {
    this.slots = this.displaySlots();
    this.entries = [];
    this.choicesHost.replaceChildren();
    for (const slot of this.slots) {
      const choice = document.createElement("label");
      choice.className = "multi-choice-option";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = String(slot);
      box.checked = true;
      const text = document.createElement("span");
      text.textContent = slotLabel(slot);
      choice.append(box, text);
      this.choicesHost.append(choice);
      this.entries.push({ slot, box, text });
    }
  }

  boxFor(slot) {
    return this.entries.find((entry) => entry.slot === slot)?.box || null;
  }

  async readStates() {
    const key = this.hooks.contextKey();
    const slots = this.displaySlots();
    if (!slots.length) return null;
    const states = new Map();
    let job = null;
    for (const slot of slots) {
      if (this.hooks.contextKey() !== key || !this.selectedDefinition()) return null;
      job = await this.hooks.executeCommand(
        "reference-display",
        { action: "query", slot },
        { intent: "readback" },
      );
      if (this.hooks.contextKey() !== key || !this.selectedDefinition()) return null;
      const enabled = displayState(job)?.enabled;
      if (job?.status !== "completed" || typeof enabled !== "boolean") return { ok: false, job };
      states.set(slot, enabled);
    }
    return { ok: true, states, job };
  }

  applyStates(states) {
    for (const [slot, enabled] of states) {
      const box = this.boxFor(slot);
      if (box) box.checked = enabled;
    }
  }

  async run() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return null;
    if (!this.selectedDefinition()) return null;
    const slots = this.displaySlots();
    if (!slots.length) return null;
    const desired = slots.map((slot) => ({
      slot,
      enabled: this.boxFor(slot)?.checked === true,
    }));
    const key = this.hooks.contextKey();
    this.busy = true;
    this.applyBusyState();
    try {
      let job = null;
      for (const item of desired) {
        if (this.hooks.contextKey() !== key) return null;
        job = await this.hooks.executeCommand(
          "reference-display",
          { action: "set", slot: item.slot, enabled: item.enabled },
          { intent: "apply" },
        );
        if (this.hooks.contextKey() !== key) return null;
        const enabled = displayState(job)?.enabled;
        if (
          job?.status !== "completed"
          || typeof enabled !== "boolean"
          || enabled !== item.enabled
        ) {
          this.status.textContent = translate("reference-display.editor.runIncomplete");
          return job;
        }
      }
      const reread = await this.readStates();
      if (reread === null) return job;
      if (!reread.ok) {
        this.status.textContent = translate("reference-display.editor.readFailed");
        return reread.job;
      }
      this.applyStates(reread.states);
      this.status.textContent = "";
      return job;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  async read() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return null;
    if (!this.selectedDefinition()) return null;
    const key = this.hooks.contextKey();
    this.busy = true;
    this.applyBusyState();
    try {
      const reread = await this.readStates();
      if (reread === null || this.hooks.contextKey() !== key) return reread?.job || null;
      if (!reread.ok) {
        this.status.textContent = translate("reference-display.editor.readFailed");
        return reread.job;
      }
      this.applyStates(reread.states);
      this.status.textContent = "";
      return reread.job;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  applyBusyState() {
    const disabled = this.busy
      || this.hooks.isExecutionBusy?.()
      || !this.hooks.isAvailable()
      || !this.slots.length;
    this.refreshButton.disabled = disabled;
    this.runButton.disabled = disabled;
    for (const entry of this.entries) entry.box.disabled = disabled;
  }
}
