import { translate } from "/static/i18n.js";
import { applyNumericFieldConstraints } from "/static/numeric-input.js";

const ARTIFACT_ACTIONS = new Set(["capture", "screenshot"]);

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function defaultFieldValue(field) {
  if (Array.isArray(field.default)) return [...field.default];
  if (field.type === "boolean") return Boolean(field.default);
  return String(field.default);
}

function predicatesMatch(predicates, parameters) {
  return (predicates || []).every((predicate) => {
    const value = parameters[predicate.field];
    if (Object.hasOwn(predicate, "equals")) return value === predicate.equals;
    if (Array.isArray(predicate.in)) return predicate.in.includes(value);
    return true;
  });
}

function timestampFilename() {
  const date = new Date();
  const part = (value) => String(value).padStart(2, "0");
  return `scopes-tool-sequence-${date.getFullYear()}${part(date.getMonth() + 1)}${part(date.getDate())}-${part(date.getHours())}${part(date.getMinutes())}${part(date.getSeconds())}.sequence.json`;
}

export class SequenceEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.renderedKey = null;
    this.states = new Map();
    this.buildHeaderAction();
  }

  buildHeaderAction() {
    this.executeButton?.remove?.();
    this.executeButton = document.createElement("button");
    this.executeButton.type = "button";
    this.executeButton.className = "primary sequence-editor-execute";
    this.executeButton.textContent = translate("sequence.editor.execute");
    this.executeButton.hidden = true;
    this.executeButton.addEventListener("click", () => void this.submit());
    this.hooks.headerActions?.append(this.executeButton);
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "sequence" ? selected : null;
  }

  currentKey() {
    return `${this.hooks.contextKey()}|sequence`;
  }

  metadata() {
    return this.selectedDefinition()?.sequence || {};
  }

  initialState() {
    return {
      loopCount: "1",
      filename: null,
      message: "",
      messageError: false,
      steps: [{ action: "wait", parameters: { seconds: "0" }, expanded: true }],
    };
  }

  state() {
    const key = this.currentKey();
    if (!this.states.has(key)) this.states.set(key, this.initialState());
    return this.states.get(key);
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
    if (!this.selectedDefinition()) {
      this.renderedKey = null;
      this.container.replaceChildren();
      this.applyBusyState();
      return;
    }
    const key = this.currentKey();
    if (key !== this.renderedKey) {
      this.renderedKey = key;
      this.render();
    } else {
      this.applyBusyState();
    }
  }

  defaultParameters(action) {
    const parameters = {};
    for (const field of this.metadata().parameters?.[action] || []) {
      if (field.default !== undefined && predicatesMatch(field.visible_if, parameters)) {
        parameters[field.name] = defaultFieldValue(field);
      }
    }
    return parameters;
  }

  ensureVisibleDefaults(step) {
    for (const field of this.metadata().parameters?.[step.action] || []) {
      if (predicatesMatch(field.visible_if, step.parameters)
          && step.parameters[field.name] === undefined
          && field.default !== undefined) {
        if (step.action === "measure"
            && field.name === "channel"
            && step.parameters.source_channel !== undefined) continue;
        step.parameters[field.name] = defaultFieldValue(field);
      }
    }
  }

  artifactCount() {
    return this.state().steps.filter((step) => ARTIFACT_ACTIONS.has(step.action)).length;
  }

  setMessage(message, error = true) {
    const state = this.state();
    state.message = message;
    state.messageError = error;
    this.render();
  }

  clearDocumentMessage() {
    const state = this.state();
    state.message = "";
    state.messageError = false;
  }

  handleDocumentChange() {
    this.clearDocumentMessage();
    this.updateValidity();
  }

  addStep() {
    const state = this.state();
    const maximum = this.metadata().limits.step_count;
    if (state.steps.length >= maximum) {
      this.setMessage(translate("sequence.editor.stepLimit", { maximum }));
      return false;
    }
    state.steps.push({ action: "wait", parameters: { seconds: "0" }, expanded: true });
    this.clearDocumentMessage();
    this.render();
    return true;
  }

  removeStep(index) {
    const state = this.state();
    if (state.steps.length === 1) {
      this.setMessage(translate("sequence.editor.minimumStep"));
      return false;
    }
    state.steps.splice(index, 1);
    this.clearDocumentMessage();
    this.render();
    return true;
  }

  moveStep(index, offset) {
    const state = this.state();
    const target = index + offset;
    if (target < 0 || target >= state.steps.length) return false;
    [state.steps[index], state.steps[target]] = [state.steps[target], state.steps[index]];
    this.clearDocumentMessage();
    this.render();
    return true;
  }

  changeAction(index, action) {
    const state = this.state();
    const step = state.steps[index];
    if (!step || step.action === action) return true;
    const increasesArtifacts = !ARTIFACT_ACTIONS.has(step.action) && ARTIFACT_ACTIONS.has(action);
    const maximum = this.metadata().limits.artifact_steps;
    if (increasesArtifacts && this.artifactCount() >= maximum) {
      this.setMessage(translate("sequence.editor.artifactLimit", { maximum }));
      return false;
    }
    step.action = action;
    step.parameters = this.defaultParameters(action);
    step.expanded = true;
    this.clearDocumentMessage();
    this.render();
    return true;
  }

  render() {
    if (!this.selectedDefinition()) return;
    const state = this.state();
    const limits = this.metadata().limits;
    this.container.replaceChildren();

    const toolbar = document.createElement("div");
    toolbar.className = "sequence-editor-toolbar";
    this.loadButton = this.actionButton("sequence.editor.load", () => this.fileInput.click());
    this.saveButton = this.actionButton("sequence.editor.save", () => void this.save());
    this.addButton = this.actionButton("sequence.editor.addStep", () => this.addStep());
    this.expandButton = this.actionButton("sequence.editor.expandAll", () => {
      state.steps.forEach((step) => { step.expanded = true; });
      this.render();
    });
    this.collapseButton = this.actionButton("sequence.editor.collapseAll", () => {
      state.steps.forEach((step) => { step.expanded = false; });
      this.render();
    });
    this.fileInput = document.createElement("input");
    this.fileInput.type = "file";
    this.fileInput.accept = ".json,.sequence.json,application/json";
    this.fileInput.hidden = true;
    this.fileInput.addEventListener("change", () => void this.loadFile(this.fileInput.files?.[0]));
    toolbar.append(
      this.loadButton, this.saveButton, this.addButton,
      this.expandButton, this.collapseButton, this.fileInput,
    );

    const overview = document.createElement("div");
    overview.className = "sequence-editor-overview";
    const loopLabel = document.createElement("label");
    loopLabel.className = "field sequence-editor-loop";
    const loopText = document.createElement("span");
    loopText.textContent = translate("sequence.editor.loopCount");
    this.loopInput = document.createElement("input");
    this.loopInput.type = "number";
    this.loopInput.step = "1";
    this.loopInput.min = "1";
    this.loopInput.max = String(limits.loop_count);
    this.loopInput.value = state.loopCount;
    this.loopInput.addEventListener("input", () => {
      state.loopCount = this.loopInput.value;
      this.handleDocumentChange();
    });
    loopLabel.append(loopText, this.loopInput);
    this.stepUsage = document.createElement("strong");
    this.stepUsage.textContent = translate("sequence.editor.stepUsage", {
      count: state.steps.length, maximum: limits.step_count,
    });
    this.artifactUsage = document.createElement("strong");
    this.artifactUsage.textContent = translate("sequence.editor.artifactUsage", {
      count: this.artifactCount(), maximum: limits.artifact_steps,
    });
    overview.append(loopLabel, this.stepUsage, this.artifactUsage);

    this.message = document.createElement("p");
    this.message.className = state.messageError ? "form-error" : "compact-note";
    this.message.setAttribute("aria-live", "polite");
    this.message.textContent = state.message;
    this.message.hidden = !state.message;

    this.stepsHost = document.createElement("div");
    this.stepsHost.className = "sequence-editor-steps";
    state.steps.forEach((step, index) => this.stepsHost.append(this.renderStep(step, index)));
    this.container.append(toolbar, overview, this.message, this.stepsHost);
    this.updateValidity();
  }

  actionButton(key, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = translate(key);
    button.addEventListener("click", handler);
    return button;
  }

  renderStep(step, index) {
    const card = document.createElement("section");
    card.className = "sequence-step-card";
    card.dataset.stepIndex = String(index + 1);
    const header = document.createElement("div");
    header.className = "sequence-step-header";
    const toggle = this.actionButton("sequence.editor.toggleStep", () => {
      step.expanded = !step.expanded;
      this.render();
    });
    toggle.className = "secondary sequence-step-toggle";
    toggle.textContent = `${step.expanded ? "−" : "+"} ${translate("sequence.editor.step", { index: index + 1 })}: ${this.stepSummary(step)}`;
    toggle.setAttribute("aria-expanded", String(step.expanded));
    const up = this.actionButton("sequence.editor.moveUp", () => this.moveStep(index, -1));
    const down = this.actionButton("sequence.editor.moveDown", () => this.moveStep(index, 1));
    const remove = this.actionButton("sequence.editor.remove", () => this.removeStep(index));
    up.dataset.structuralDisabled = String(index === 0);
    down.dataset.structuralDisabled = String(index === this.state().steps.length - 1);
    up.disabled = up.dataset.structuralDisabled === "true";
    down.disabled = down.dataset.structuralDisabled === "true";
    header.append(toggle, up, down, remove);
    card.append(header);
    if (!step.expanded) return card;

    const body = document.createElement("div");
    body.className = "sequence-step-body";
    const actionWrapper = document.createElement("label");
    actionWrapper.className = "field";
    const actionLabel = document.createElement("span");
    actionLabel.textContent = translate("sequence.editor.action");
    const actionSelect = document.createElement("select");
    actionSelect.dataset.sequenceAction = String(index + 1);
    for (const action of this.metadata().actions) {
      actionSelect.append(new Option(translate(`sequence.action.${action}`), action));
    }
    actionSelect.value = step.action;
    actionSelect.addEventListener("change", () => this.changeAction(index, actionSelect.value));
    actionWrapper.append(actionLabel, actionSelect);
    body.append(actionWrapper);
    this.ensureVisibleDefaults(step);
    for (const field of this.metadata().parameters?.[step.action] || []) {
      if (predicatesMatch(field.visible_if, step.parameters)) {
        body.append(this.renderParameter(step, index, field));
      }
    }
    card.append(body);
    return card;
  }

  renderParameter(step, index, field) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const label = document.createElement("span");
    label.textContent = translate(`sequence.parameter.${field.name}`);
    let input;
    if (field.type === "enum" || (field.type === "integer" && field.options)) {
      input = document.createElement("select");
      for (const option of field.options || []) {
        input.append(new Option(String(option), String(option)));
      }
      input.value = String(step.parameters[field.name] ?? "");
      input.addEventListener("change", () => {
        if (field.name === "item") {
          step.parameters = this.defaultParameters(step.action);
        }
        step.parameters[field.name] = input.value;
        this.ensureVisibleDefaults(step);
        this.clearDocumentMessage();
        this.render();
      });
    } else if (field.type === "multi-enum") {
      input = document.createElement("div");
      input.className = "sequence-multi-enum";
      const selected = new Set((step.parameters[field.name] || []).map(String));
      for (const option of field.options || []) {
        const choice = document.createElement("label");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = String(option);
        checkbox.checked = selected.has(String(option));
        checkbox.addEventListener("change", () => {
          if (checkbox.checked && checkbox.value === "all") {
            input.querySelectorAll("input").forEach((item) => {
              item.checked = item === checkbox;
            });
          } else if (checkbox.checked) {
            const allChoice = input.querySelector('input[value="all"]');
            if (allChoice) allChoice.checked = false;
          }
          const values = [...input.querySelectorAll("input")]
            .filter((item) => item.checked)
            .map((item) => item.value === "all" ? "all" : Number(item.value));
          step.parameters[field.name] = values;
          this.handleDocumentChange();
        });
        const text = document.createElement("span");
        text.textContent = option === "all"
          ? translate("sequence.editor.allChannels")
          : `CH${option}`;
        choice.append(checkbox, text);
        input.append(choice);
      }
    } else if (field.type === "boolean") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.checked = Boolean(step.parameters[field.name]);
      input.addEventListener("change", () => {
        step.parameters[field.name] = input.checked;
        this.handleDocumentChange();
      });
    } else {
      input = document.createElement("input");
      applyNumericFieldConstraints(input, field);
      input.required = field.required === true || (
        Array.isArray(field.required_if)
        && field.required_if.length > 0
        && predicatesMatch(field.required_if, step.parameters)
      );
      input.value = String(step.parameters[field.name] ?? "");
      input.addEventListener("input", () => {
        step.parameters[field.name] = input.value;
        this.handleDocumentChange();
      });
    }
    input.dataset.sequenceParameter = `${index + 1}:${field.name}`;
    wrapper.append(label, input);
    return wrapper;
  }

  stepSummary(step) {
    const values = Object.entries(step.parameters).filter(([, value]) => value !== "");
    if (!values.length) return translate(`sequence.action.${step.action}`);
    const detail = values.map(([name, value]) => `${name}=${Array.isArray(value) ? value.join(",") : value}`).join("; ");
    return `${translate(`sequence.action.${step.action}`)} — ${detail}`;
  }

  localDocument() {
    const state = this.state();
    const loopCount = Number(state.loopCount);
    if (!Number.isInteger(loopCount)) return null;
    const steps = [];
    for (const step of state.steps) {
      const parameters = {};
      for (const field of this.metadata().parameters?.[step.action] || []) {
        if (!predicatesMatch(field.visible_if, step.parameters)) continue;
        const value = step.parameters[field.name];
        if (field.type === "number" || (field.type === "integer" && !field.options)) {
          if ((value === "" || value === undefined) && field.required !== true) continue;
          if (value === "" || value === undefined || !Number.isFinite(Number(value))) return null;
          parameters[field.name] = Number(value);
        } else if (field.type === "integer" && field.options) {
          parameters[field.name] = Number(value);
        } else {
          parameters[field.name] = clone(value);
        }
      }
      steps.push({ action: step.action, parameters });
    }
    return { version: 1, loop_count: loopCount, steps };
  }

  validationError() {
    const state = this.state();
    const limits = this.metadata().limits;
    const loopCount = Number(state.loopCount);
    if (!Number.isInteger(loopCount) || loopCount < 1 || loopCount > limits.loop_count) {
      return translate("sequence.editor.invalidLoop", { maximum: limits.loop_count });
    }
    if (state.steps.length < 1 || state.steps.length > limits.step_count) {
      return translate("sequence.editor.invalidSteps", { maximum: limits.step_count });
    }
    if (this.artifactCount() > limits.artifact_steps) {
      return translate("sequence.editor.artifactLimit", { maximum: limits.artifact_steps });
    }
    for (let index = 0; index < state.steps.length; index += 1) {
      const step = state.steps[index];
      for (const field of this.metadata().parameters?.[step.action] || []) {
        if (!predicatesMatch(field.visible_if, step.parameters)) continue;
        const value = step.parameters[field.name];
        const required = field.required === true || (
          Array.isArray(field.required_if)
          && field.required_if.length > 0
          && predicatesMatch(field.required_if, step.parameters)
        );
        if (required && (value === undefined || value === "" || (Array.isArray(value) && !value.length))) {
          return translate("sequence.editor.invalidParameter", { index: index + 1, name: field.name });
        }
        if (field.type === "number" || (field.type === "integer" && !field.options)) {
          if ((value === undefined || value === "") && !required) continue;
          const number = Number(value);
          if (!Number.isFinite(number)
              || (field.type === "integer" && !Number.isInteger(number))
              || (field.minimum !== undefined && number < field.minimum)
              || (field.maximum !== undefined && number > field.maximum)
              || (field.exclusive_minimum !== undefined && number <= field.exclusive_minimum)) {
            return translate("sequence.editor.invalidParameter", { index: index + 1, name: field.name });
          }
        }
      }
      if (step.action === "measure"
          && ((step.parameters.channel === undefined || step.parameters.channel === "")
              === (step.parameters.source_channel === undefined || step.parameters.source_channel === ""))) {
        return translate("sequence.editor.measureSource", { index: index + 1 });
      }
      if (step.action === "measure"
          && ["phase", "delay"].includes(step.parameters.item)
          && String(step.parameters.source_channel ?? step.parameters.channel)
            === String(step.parameters.reference_channel)) {
        return translate("sequence.editor.distinctChannels", { index: index + 1 });
      }
    }
    return this.localDocument() ? "" : translate("sequence.editor.invalidDocument");
  }

  updateValidity() {
    const error = this.validationError();
    this.loopInput?.setCustomValidity?.(error && !Number.isInteger(Number(this.state().loopCount)) ? error : "");
    if (!this.state().message) {
      this.message.textContent = error;
      this.message.hidden = !error;
      this.message.className = "form-error";
    }
    this.applyBusyState();
    return !error;
  }

  async loadFile(file) {
    if (!file) return false;
    try {
      const text = await file.text();
      if (this.hooks.validateSequenceText) {
        const validated = await this.hooks.validateSequenceText(text);
        const state = this.state();
        state.loopCount = String(validated.document.loop_count);
        state.steps = validated.document.steps.map((step) => ({
          action: step.action,
          parameters: clone(step.parameters),
          expanded: false,
        }));
        state.filename = file.name;
        state.message = translate("sequence.editor.loaded");
        state.messageError = false;
        this.render();
        return true;
      }
      const payload = JSON.parse(text);
      return await this.loadDocument(payload, file.name);
    } catch (error) {
      this.setMessage(translate("sequence.editor.loadFailed", { error: error.message }));
      return false;
    }
  }

  async loadDocument(payload, filename = null) {
    try {
      const validated = await this.hooks.validateSequence(payload);
      const state = this.state();
      state.loopCount = String(validated.document.loop_count);
      state.steps = validated.document.steps.map((step) => ({
        action: step.action,
        parameters: clone(step.parameters),
        expanded: false,
      }));
      state.filename = filename;
      state.message = translate("sequence.editor.loaded");
      state.messageError = false;
      this.render();
      return true;
    } catch (error) {
      this.setMessage(translate("sequence.editor.loadFailed", { error: error.message }));
      return false;
    }
  }

  async save() {
    const documentValue = this.localDocument();
    if (!this.updateValidity() || !documentValue) return false;
    try {
      const validated = await this.hooks.validateSequence(documentValue);
      const filename = this.state().filename || timestampFilename();
      if (this.hooks.downloadSequence) {
        this.hooks.downloadSequence(validated.document, filename);
      } else {
        const blob = new Blob([`${JSON.stringify(validated.document, null, 2)}\n`], { type: "application/json" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
        URL.revokeObjectURL(link.href);
      }
      this.state().filename = filename;
      this.setMessage(translate("sequence.editor.saved", { filename }), false);
      return true;
    } catch (error) {
      this.setMessage(translate("sequence.editor.saveFailed", { error: error.message }));
      return false;
    }
  }

  async submit() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return null;
    const documentValue = this.localDocument();
    if (!this.updateValidity() || !documentValue) return null;
    this.setBusy(true);
    try {
      const validated = await this.hooks.validateSequence(documentValue);
      return await this.hooks.executeCommand(
        "sequence",
        { document: validated.document },
        { intent: "command" },
      );
    } catch (error) {
      this.setMessage(error.message);
      return null;
    } finally {
      this.setBusy(false);
    }
  }

  setBusy(value) {
    this.busy = value;
    this.applyBusyState();
  }

  applyBusyState() {
    if (!this.selectedDefinition()) {
      if (this.executeButton) this.executeButton.disabled = true;
      return;
    }
    const unavailable = this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable();
    const invalid = Boolean(this.validationError());
    if (this.executeButton) this.executeButton.disabled = unavailable || invalid;
    if (this.saveButton) this.saveButton.disabled = unavailable || invalid;
    this.container.querySelectorAll("input, select, button").forEach((control) => {
      if (control !== this.saveButton) {
        control.disabled = unavailable || control.dataset.structuralDisabled === "true";
      }
    });
  }
}
