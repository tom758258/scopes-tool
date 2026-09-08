import { translate } from "/static/i18n.js";
import { formatEngineering } from "/static/live-data.js";

const DIV_STEPS = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5];
const HORIZONTAL_DIVISIONS = 10;

function divLabel(div) {
  return div > 0 ? `+${div}` : String(div);
}

function divValueText(div, scale) {
  return cleanFloatText(div * scale);
}

function cleanFloatText(value) {
  return String(Number(value.toPrecision(12)));
}

export class TimebasePositionEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.stateKey = null;
    this.divScale = null;
    this.divReference = null;
    this.lastPosition = null;
    this.selectedDiv = null;
    this.divIncomplete = false;
    this.buildDom();
  }

  definition() {
    return this.catalog.commands.find((command) => command.id === "timebase-position") || null;
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "timebase-position" ? selected : null;
  }

  currentStateKey() {
    return `${this.hooks.contextKey()}|${this.selectedDefinition()?.id || ""}`;
  }

  buildDom() {
    this.container.replaceChildren();

    this.positionField = document.createElement("label");
    this.positionField.className = "field";
    this.positionFieldLabel = document.createElement("span");
    this.positionFieldLabel.textContent = translate("field.position_seconds");
    this.positionInput = document.createElement("input");
    this.positionInput.type = "text";
    this.positionInput.inputMode = "decimal";
    this.positionInput.dataset.field = "position_seconds";
    this.positionInput.addEventListener("input", () => {
      this.selectedDiv = null;
      this.syncInfo();
    });
    this.positionHelp = document.createElement("small");
    this.positionHelp.className = "field-help";
    this.positionHelp.textContent = translate("timebase-position.editor.positionHelp");
    this.positionField.append(this.positionFieldLabel, this.positionInput, this.positionHelp);

    this.divSection = document.createElement("div");
    this.divSection.className = "trigger-editor-section";

    this.divHeading = document.createElement("strong");
    this.divHeading.className = "trigger-editor-heading";
    this.divHeading.textContent = translate("timebase-position.editor.divHeading");

    this.divHint = document.createElement("small");
    this.divHint.className = "field-help";
    this.divHint.textContent = translate("timebase-position.editor.divHint");

    this.referenceNote = document.createElement("small");
    this.referenceNote.className = "field-help";
    this.referenceNote.textContent = translate("timebase-position.editor.referenceNote");

    this.divButtonsHost = document.createElement("div");
    this.divButtonsHost.className = "div-slider-block";
    this.divSlider = document.createElement("input");
    this.divSlider.type = "range";
    this.divSlider.min = String(DIV_STEPS[0]);
    this.divSlider.max = String(DIV_STEPS[DIV_STEPS.length - 1]);
    this.divSlider.step = "1";
    this.divSlider.value = "0";
    this.divSlider.setAttribute("aria-label", translate("timebase-position.editor.divHeading"));
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
    this.selection.className = "muted compact-note div-slider-selection";
    this.divStatus = document.createElement("output");
    this.divStatus.className = "muted compact-note";
    this.divSection.append(
      this.divHeading,
      this.divHint,
      this.referenceNote,
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

    const formContainer = document.createElement("div");
    formContainer.className = "command-form";
    formContainer.append(this.positionField);
    this.container.append(formContainer, this.divSection);
    if (this.hooks.headerActions) {
      this.readButton.hidden = true;
      this.applyButton.hidden = true;
      this.hooks.headerActions.append(this.readButton, this.applyButton);
    } else {
      this.actions.append(this.readButton, this.applyButton);
      this.container.append(this.actions);
    }

    this.stateKey = null;
    this.syncInfo();
    this.schedulePresentation();
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    this.positionFieldLabel.textContent = translate("field.position_seconds");
    this.positionHelp.textContent = translate("timebase-position.editor.positionHelp");
    this.divHeading.textContent = translate("timebase-position.editor.divHeading");
    this.divHint.textContent = translate("timebase-position.editor.divHint");
    this.referenceNote.textContent = translate("timebase-position.editor.referenceNote");
    this.divSlider.setAttribute("aria-label", translate("timebase-position.editor.divHeading"));
    this.readButton.textContent = translate("actions.readSettings");
    this.applyButton.textContent = translate("actions.apply");
    this.syncInfo();
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
    this.positionInput.value = "";
    this.divIncomplete = false;
    this.clearDivState();
    this.rebuild();
    this.applyBusyState();
  }

  rebuild() {
    this.syncInfo();
  }

  clearDivState() {
    this.divScale = null;
    this.divReference = null;
    this.lastPosition = null;
    this.selectedDiv = null;
    this.syncInfo();
  }

  syncInfo() {
    this.divSlider.value = this.selectedDiv === null ? "0" : String(this.selectedDiv);
    if (this.divScale === null || this.divReference === null) {
      this.info.textContent = "";
    } else {
      const scaleText = formatEngineering(this.divScale, "s", { perDivision: true });
      this.info.textContent = translate("timebase-position.editor.currentSettings", {
        scale: scaleText,
        reference: translate(`enum.${this.divReference}`),
        position: formatEngineering(this.lastPosition, "s", { signed: true }),
        span: formatEngineering(Number(cleanFloatText(this.divScale * HORIZONTAL_DIVISIONS)), "s", {}),
      });
    }
    if (this.selectedDiv === null || this.divScale === null) {
      this.selection.textContent = "";
    } else {
      this.selection.textContent = translate("timebase-position.editor.divSelection", {
        div: divLabel(this.selectedDiv),
        value: formatEngineering(Number(cleanFloatText(this.selectedDiv * this.divScale)), "s", { signed: true }),
      });
    }
    this.divStatus.textContent = this.divIncomplete
      ? translate("timebase-position.editor.divReadIncomplete")
      : "";
  }

  selectDiv(div) {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return;
    if (this.divScale === null || this.positionInput.disabled) return;
    this.selectedDiv = div;
    this.positionInput.value = divValueText(div, this.divScale);
    this.syncInfo();
  }

  async read() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return null;
    if (!this.selectedDefinition()) return null;

    const contextKey = this.hooks.contextKey();

    this.busy = true;
    this.applyBusyState();
    try {
      const scaleJob = await this.hooks.executeCommand(
        "timebase-scale",
        { action: "query" },
        { intent: "readback" },
      );
      if (this.hooks.contextKey() !== contextKey || !this.selectedDefinition()) {
        return scaleJob;
      }
      if (scaleJob?.status !== "completed") {
        this.divIncomplete = true;
        this.clearDivState();
        return scaleJob;
      }
      const scale = scaleJob?.result?.result?.timebase?.seconds_per_division
        ?? scaleJob?.result?.timebase?.seconds_per_division;
      if (typeof scale !== "number" || !Number.isFinite(scale) || scale <= 0) {
        this.divIncomplete = true;
        this.clearDivState();
        return scaleJob;
      }

      const positionJob = await this.hooks.executeCommand(
        "timebase-position",
        { action: "query" },
        { intent: "readback" },
      );
      if (this.hooks.contextKey() !== contextKey || !this.selectedDefinition()) {
        return positionJob;
      }
      if (positionJob?.status !== "completed") {
        this.divIncomplete = true;
        this.clearDivState();
        return positionJob;
      }
      const position = positionJob?.result?.result?.timebase?.position_seconds
        ?? positionJob?.result?.timebase?.position_seconds;
      if (typeof position !== "number" || !Number.isFinite(position)) {
        this.divIncomplete = true;
        this.clearDivState();
        return positionJob;
      }

      const referenceJob = await this.hooks.executeCommand(
        "timebase-reference",
        { action: "query" },
        { intent: "readback" },
      );
      if (this.hooks.contextKey() !== contextKey || !this.selectedDefinition()) {
        return referenceJob;
      }
      if (referenceJob?.status !== "completed") {
        this.divIncomplete = true;
        this.clearDivState();
        return referenceJob;
      }
      const reference = referenceJob?.result?.result?.timebase?.reference
        ?? referenceJob?.result?.timebase?.reference;
      if (reference !== "left" && reference !== "center" && reference !== "right") {
        this.divIncomplete = true;
        this.clearDivState();
        return referenceJob;
      }

      this.positionInput.value = String(position);
      this.divScale = scale;
      this.divReference = reference;
      this.lastPosition = position;
      this.selectedDiv = null;
      this.divIncomplete = false;
      this.syncInfo();
      return referenceJob;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  async apply() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return null;
    if (!this.selectedDefinition()) return null;

    const value = Number(this.positionInput.value);
    if (!Number.isFinite(value)) return null;

    const contextKey = this.hooks.contextKey();

    this.busy = true;
    this.applyBusyState();
    try {
      const job = await this.hooks.executeCommand(
        "timebase-position",
        { action: "set", position_seconds: value },
        { intent: "apply" },
      );

      if (
        job?.status !== "completed" ||
        this.hooks.contextKey() !== contextKey ||
        !this.selectedDefinition()
      ) {
        return job;
      }

      // Use readback from the successful set command to update the same field
      const actual = job?.result?.result?.timebase?.position_seconds
        ?? job?.result?.timebase?.position_seconds;
      if (typeof actual === "number" && Number.isFinite(actual)) {
        this.positionInput.value = String(actual);
        this.lastPosition = actual;
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
      || !this.hooks.isAvailable?.();
    this.positionInput.disabled = unavailable;
    this.readButton.disabled = unavailable;
    this.applyButton.disabled = unavailable;
    const divDisabled = unavailable || this.divScale === null;
    this.divSlider.disabled = divDisabled;
  }
}
