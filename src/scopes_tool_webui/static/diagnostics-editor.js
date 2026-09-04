import { translate } from "/static/i18n.js";

export class DiagnosticsEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.mode = "doctor";
    this.saveArtifacts = false;
    this.busy = false;
    this.renderedKey = null;
    this.renderedContextKey = null;
    this.buildHeaderAction();
  }

  buildHeaderAction() {
    this.runButton?.remove?.();
    this.runButton = document.createElement("button");
    this.runButton.type = "button";
    this.runButton.className = "primary diagnostics-editor-run";
    this.runButton.textContent = translate("actions.run");
    this.runButton.hidden = true;
    this.runButton.addEventListener("click", () => void this.submit());
    this.hooks.headerActions?.append(this.runButton);
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "diagnostics" ? selected : null;
  }

  currentKey(contextKey = this.hooks.contextKey?.() || "") {
    return `${contextKey}|${this.selectedDefinition()?.id || ""}`;
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    this.buildHeaderAction();
    this.renderedKey = null;
    this.schedulePresentation();
  }

  present() {
    const contextKey = this.hooks.contextKey?.() || "";
    if (this.renderedContextKey !== null && contextKey !== this.renderedContextKey) {
      this.mode = "doctor";
      this.saveArtifacts = false;
    }
    this.renderedContextKey = contextKey;

    const definition = this.selectedDefinition();
    if (!definition) {
      this.renderedKey = null;
      this.container.replaceChildren();
      this.applyBusyState();
      return;
    }
    const key = this.currentKey(contextKey);
    if (key !== this.renderedKey) {
      this.renderedKey = key;
      this.buildWorkspace();
    }
    this.applyBusyState();
  }

  buildWorkspace() {
    this.container.replaceChildren();

    const modeField = document.createElement("label");
    modeField.className = "diagnostics-editor-field";
    const modeLabel = document.createElement("span");
    modeLabel.textContent = translate("diagnostics.mode");
    this.modeSelect = document.createElement("select");
    this.modeSelect.setAttribute("aria-label", translate("diagnostics.mode"));
    for (const value of ["doctor", "smoke"]) {
      const option = new Option(translate(`diagnostics.${value}`), value);
      this.modeSelect.append(option);
    }
    this.modeSelect.value = this.mode;
    this.modeSelect.addEventListener("change", () => {
      this.mode = this.modeSelect.value;
      this.renderMode();
      this.applyBusyState();
    });
    modeField.append(modeLabel, this.modeSelect);

    this.saveArtifactsField = document.createElement("label");
    this.saveArtifactsField.className = "diagnostics-editor-checkbox";
    this.saveArtifactsInput = document.createElement("input");
    this.saveArtifactsInput.type = "checkbox";
    this.saveArtifactsInput.checked = this.saveArtifacts;
    this.saveArtifactsInput.addEventListener("change", () => {
      this.saveArtifacts = this.saveArtifactsInput.checked;
      this.applyBusyState();
    });
    const saveArtifactsLabel = document.createElement("span");
    saveArtifactsLabel.textContent = translate("diagnostics.saveArtifacts");
    this.saveArtifactsField.append(this.saveArtifactsInput, saveArtifactsLabel);

    this.help = document.createElement("p");
    this.help.className = "compact-note diagnostics-editor-help";
    this.container.append(modeField, this.saveArtifactsField, this.help);
    this.renderMode();
  }

  renderMode() {
    if (!this.modeSelect) return;
    this.modeSelect.value = this.mode;
    this.saveArtifactsField.hidden = this.mode !== "smoke";
    this.help.textContent = translate(
      this.mode === "smoke" ? "diagnostics.smokeHelp" : "diagnostics.doctorHelp",
    );
  }

  async submit() {
    if (this.busy || this.hooks.isExecutionBusy?.()) return null;
    const command = this.mode;
    const parameters = command === "smoke"
      ? { save_artifacts: this.saveArtifacts }
      : {};
    if (!this.hooks.isAvailable?.(command)) return null;
    this.busy = true;
    this.applyBusyState();
    try {
      return await this.hooks.executeCommand(command, parameters);
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  applyBusyState() {
    const available = this.hooks.isAvailable?.(this.mode) !== false;
    const disabled = this.busy || Boolean(this.hooks.isExecutionBusy?.()) || !available;
    if (this.runButton) this.runButton.disabled = disabled;
    if (this.modeSelect) this.modeSelect.disabled = disabled;
    if (this.saveArtifactsInput) this.saveArtifactsInput.disabled = disabled;
  }
}
