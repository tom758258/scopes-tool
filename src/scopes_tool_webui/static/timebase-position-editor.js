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
    this.positionField.append(this.positionFieldLabel, this.positionInput);

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
    this.divButtonsHost.className = "div-quick-fill";
    this.divButtons = [];
    for (const div of DIV_STEPS) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = divLabel(div);
      button.addEventListener("click", () => {
        this.selectDiv(div);
      });
      this.divButtonsHost.append(button);
      this.divButtons.push(button);
    }

    this.info = document.createElement("output");
    this.info.className = "muted compact-note";
    this.selection = document.createElement("output");
    this.selection.className = "muted compact-note";
    this.divSection.append(
      this.divHeading,
      this.divHint,
      this.referenceNote,
      this.divButtonsHost,
      this.info,
      this.selection,
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
    this.container.append(this.positionField, this.divSection, this.actions);

    this.stateKey = null;
    this.syncInfo();
    this.schedulePresentation();
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    this.positionFieldLabel.textContent = translate("field.position_seconds");
    this.divHeading.textContent = translate("timebase-position.editor.divHeading");
    this.divHint.textContent = translate("timebase-position.editor.divHint");
    this.referenceNote.textContent = translate("timebase-position.editor.referenceNote");
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
      if (
        scaleJob?.status !== "completed" ||
        this.hooks.contextKey() !== contextKey ||
        !this.selectedDefinition()
      ) {
        this.clearDivState();
        return scaleJob;
      }
      const scale = scaleJob?.result?.result?.timebase?.seconds_per_division
        ?? scaleJob?.result?.timebase?.seconds_per_division;
      if (typeof scale !== "number" || !Number.isFinite(scale) || scale <= 0) {
        this.clearDivState();
        return scaleJob;
      }

      const positionJob = await this.hooks.executeCommand(
        "timebase-position",
        { action: "query" },
        { intent: "readback" },
      );
      if (
        positionJob?.status !== "completed" ||
        this.hooks.contextKey() !== contextKey ||
        !this.selectedDefinition()
      ) {
        this.clearDivState();
        return positionJob;
      }
      const position = positionJob?.result?.result?.timebase?.position_seconds
        ?? positionJob?.result?.timebase?.position_seconds;
      if (typeof position !== "number" || !Number.isFinite(position)) {
        this.clearDivState();
        return positionJob;
      }

      const referenceJob = await this.hooks.executeCommand(
        "timebase-reference",
        { action: "query" },
        { intent: "readback" },
      );
      if (
        referenceJob?.status !== "completed" ||
        this.hooks.contextKey() !== contextKey ||
        !this.selectedDefinition()
      ) {
        this.clearDivState();
        return referenceJob;
      }
      const reference = referenceJob?.result?.result?.timebase?.reference
        ?? referenceJob?.result?.timebase?.reference;
      if (reference !== "left" && reference !== "center" && reference !== "right") {
        this.clearDivState();
        return referenceJob;
      }

      this.positionInput.value = String(position);
      this.divScale = scale;
      this.divReference = reference;
      this.lastPosition = position;
      this.selectedDiv = null;
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
    for (const button of this.divButtons) button.disabled = divDisabled;
  }
}
