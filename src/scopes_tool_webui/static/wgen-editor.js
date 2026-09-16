import { translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";

export class WgenEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.epoch = 0;
    this.stateKey = null;
    this.renderedKey = null;
    this.entry = null;
    this.frequencyFunction = null;
    this.frequencyContextKey = null;
    this.frequencyNote = null;
    this.pendingRefresh = false;
    this.pendingPresentation = false;
    this.buildDom();
  }

  buildDom() {
    this.refreshButton?.remove?.();
    this.entry?.button.remove?.();
    this.entry = null;
    this.frequencyNote = null;
    this.container.replaceChildren();
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary trigger-editor-refresh";
    this.refreshButton.textContent = translate("wgen.editor.read");
    this.refreshButton.addEventListener("click", () => {
      this.scheduleRefresh(true);
    });
    if (this.hooks.headerActions) {
      this.refreshButton.hidden = true;
      this.hooks.headerActions.append(this.refreshButton);
    } else {
      this.container.append(this.refreshButton);
    }
    this.sectionsHost = document.createElement("div");
    this.sectionsHost.className = "trigger-editor-sections";
    this.container.append(this.sectionsHost);
  }

  definition() {
    return this.selectedDefinition();
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "wgen" ? selected : null;
  }

  currentStateKey() {
    const selected = this.selectedDefinition();
    return [
      this.hooks.contextKey(),
      selected?.id || "",
      selected?.group || "",
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
    const key = this.currentStateKey();
    if (!force && key === this.stateKey) {
      this.applyBusyState();
      return;
    }
    // Execution context (mode/resource/model) changed: drop the cached
    // waveform so the range warning never uses another context's state.
    // Command navigation alone must not clear it.
    const contextKey = this.hooks.contextKey();
    if (contextKey !== this.frequencyContextKey) {
      this.frequencyContextKey = contextKey;
      this.frequencyFunction = null;
    }
    this.stateKey = key;
    if (this.renderedKey !== key) this.rebuildSections(key);
    this.applyBusyState();
    if (!read || !this.hooks.isAvailable()) return;
    this.setBusy(true);
    try {
      await this.readState();
    } finally {
      this.setBusy(false);
    }
  }

  clearSections() {
    this.renderedKey = null;
    this.entry?.button.remove?.();
    this.entry = null;
    this.frequencyNote = null;
    this.sectionsHost.replaceChildren();
    this.refreshButton.disabled = true;
  }

  rebuildSections(key) {
    this.epoch += 1;
    const epoch = this.epoch;
    this.renderedKey = key;
    this.entry?.button.remove?.();
    this.entry = null;
    this.frequencyNote = null;
    this.sectionsHost.replaceChildren();
    const command = this.definition();
    if (!command || !this.catalog.supported(command)) return;
    const section = document.createElement("section");
    section.className = "trigger-editor-section";
    const formContainer = document.createElement("div");
    formContainer.className = "command-form";
    const actionButton = document.createElement("button");
    actionButton.type = "button";
    const kind = command.presentation?.kind || "command";
    const action = command.presentation?.action || "run";
    actionButton.className = `${kind === "setting" ? "primary" : "secondary"} trigger-editor-action`;
    actionButton.textContent = translate(
      kind === "setting" ? "actions.apply" : `actions.${action}`,
    );
    // wgen-query reuses the header Read action; a second query button would
    // duplicate it. The button is recreated on every rebuild, so hidden state
    // always follows the selection.
    actionButton.hidden = command.id === "wgen-query";
    section.append(formContainer);
    if (this.hooks.headerActions) {
      this.hooks.headerActions.append(actionButton);
    } else {
      section.append(actionButton);
    }
    this.sectionsHost.append(section);
    const form = new CommandForm(formContainer, this.catalog);
    this.entry = { form, button: actionButton, epoch };
    form.render(command, { onDirty: () => this.updateFrequencyWarning() });
    if (command.id === "wgen-frequency") {
      const note = document.createElement("p");
      note.className = "muted compact-note";
      note.hidden = true;
      formContainer.append(note);
      this.frequencyNote = note;
    }
    this.updateFrequencyWarning();
    const fields = this.catalog.fieldsFor?.(command) ?? command.fields ?? [];
    section.hidden = fields.length === 0;
    formContainer.hidden = fields.length === 0;
    actionButton.addEventListener("click", () => {
      void this.submit();
    });
  }

  async readState() {
    if (!this.entry || this.entry.epoch !== this.epoch) return;
    const epoch = this.epoch;
    const job = await this.hooks.executeCommand(
      "wgen-query",
      {},
      { intent: "readback" },
    );
    if (!this.entry || this.entry.epoch !== epoch) return;
    this.setFrequencyFunction(job?.result?.result?.wgen?.function);
    this.updateFrequencyWarning();
  }

  setFrequencyFunction(value) {
    if (value === undefined) return;
    this.frequencyFunction = value;
  }

  frequencyRange() {
    const command = this.definition();
    if (!command || command.id !== "wgen-frequency") return null;
    const fields = this.catalog.fieldsFor?.(command) ?? command.fields ?? [];
    const field = fields.find((item) => item?.name === "frequency_hz");
    const limits = field?.frequency_limits;
    if (!limits || typeof limits !== "object") return null;
    const current = this.frequencyFunction;
    // Recognized waveforms use their own limits; noise/dc and unknown
    // non-null readbacks have no displayable range. A null readback falls
    // back to the series envelope across the projected waveforms.
    if (typeof current === "string") return limits[current] || null;
    if (current !== null) return null;
    let envelope = null;
    for (const entry of Object.values(limits)) {
      if (!entry) continue;
      if (!envelope) {
        envelope = {
          min_hz: entry.min_hz,
          max_hz: entry.max_hz,
          min_label: entry.min_label,
          max_label: entry.max_label,
        };
      } else {
        if (entry.min_hz < envelope.min_hz) {
          envelope.min_hz = entry.min_hz;
          envelope.min_label = entry.min_label;
        }
        if (entry.max_hz > envelope.max_hz) {
          envelope.max_hz = entry.max_hz;
          envelope.max_label = entry.max_label;
        }
      }
    }
    return envelope;
  }

  updateFrequencyWarning() {
    const note = this.frequencyNote;
    if (!note) return;
    let show = false;
    const input = this.entry?.form?.container?.querySelector?.('[data-field="frequency_hz"]');
    const raw = typeof input?.value === "string" ? input.value.trim() : "";
    if (raw !== "") {
      const value = Number(raw);
      const range = this.frequencyRange();
      show = Boolean(range) && Number.isFinite(value)
        && (value < range.min_hz || value > range.max_hz);
      if (show) {
        note.textContent = translate("wgen.frequency.rangeWarning", {
          min: range.min_label,
          max: range.max_label,
        });
      }
    }
    note.hidden = !show;
  }

  async submit() {
    const entry = this.entry;
    if (!entry || this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    const command = this.definition();
    if (!command) return;
    const submissionKey = this.currentStateKey();
    const kind = command.presentation?.kind || "command";
    const isSetting = kind === "setting";
    let parameters = {};
    if (isSetting) {
      const values = entry.form.values();
      if (values === null) return;
      parameters = values;
    }
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        command.id,
        parameters,
        isSetting ? { intent: "apply" } : {},
      );
      if (
        job?.status === "completed"
        && entry.epoch === this.epoch
        && submissionKey === this.currentStateKey()
      ) {
        if (command.id === "wgen-function") {
          this.setFrequencyFunction(job?.result?.result?.function?.function);
        }
        if (isSetting) {
          entry.form.clearDirty();
          if (
            command.id === "wgen-load"
            && this.hooks.mode?.() === "live"
          ) {
            this.pendingRefresh = true;
          }
        }
      }
    } finally {
      this.setBusy(false);
    }
    this.updateFrequencyWarning();
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
    const disabled = this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable();
    this.refreshButton.disabled = disabled;
    if (this.entry) {
      this.entry.button.disabled = disabled;
      this.entry.form?.setDisabled(disabled);
    }
  }
}
