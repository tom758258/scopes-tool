import { hasTranslation, translate } from "/static/i18n.js";

function translatedChoice(value) {
  const key = `enum.${String(value)}`;
  return hasTranslation(key) ? translate(key) : String(value);
}

function fieldByName(fields, name) {
  return fields.find((field) => field.name === name) || {};
}

function channelLabel(value) {
  return `CH${String(value)}`;
}

function defaultChoices(field) {
  if (Array.isArray(field.default)) return field.default.map(String);
  if (typeof field.default === "string") {
    return field.default.split(",").map((value) => value.trim()).filter(Boolean);
  }
  return [];
}

export class WorkflowEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.renderedKey = null;
    this.drafts = new Map();
    this.controls = {};
    this.pairRows = [];
    this.buildHeaderAction();
  }

  buildHeaderAction() {
    this.runButton?.remove?.();
    this.runButton = document.createElement("button");
    this.runButton.type = "button";
    this.runButton.className = "primary workflow-editor-run";
    this.runButton.textContent = translate("actions.run");
    this.runButton.hidden = true;
    this.runButton.addEventListener("click", () => {
      void this.submit();
    });
    this.hooks.headerActions?.append(this.runButton);
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "workflow" ? selected : null;
  }

  currentKey() {
    const selected = this.selectedDefinition();
    return `${this.hooks.contextKey()}|${selected?.id || ""}`;
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    this.captureDraft();
    this.buildHeaderAction();
    this.renderedKey = null;
    this.schedulePresentation();
  }

  present() {
    const definition = this.selectedDefinition();
    if (!definition || !this.hooks.isAvailable()) {
      this.captureDraft();
      this.renderedKey = null;
      this.controls = {};
      this.pairRows = [];
      this.container.replaceChildren();
      this.applyBusyState();
      return;
    }
    const key = this.currentKey();
    if (key === this.renderedKey) {
      this.applyBusyState();
      return;
    }
    this.captureDraft();
    this.renderedKey = key;
    this.renderDefinition(definition, key);
    this.applyBusyState();
  }

  renderDefinition(definition, key) {
    const fields = this.catalog.fieldsFor(definition);
    const draft = this.sanitizeDraft(
      this.drafts.get(key) || this.defaultDraft(fields),
      fields,
    );
    this.drafts.set(key, draft);
    this.controls = {};
    this.pairRows = [];
    this.container.replaceChildren();

    const channelField = fieldByName(fields, "channels");
    const channels = (channelField.options || []).map(String);
    this.container.append(
      this.buildChoiceSection(
        "workflow.editor.channels",
        "channels",
        channels,
        draft.channels,
      ),
      this.buildChoiceSection(
        "workflow.editor.measurements",
        "items",
        fieldByName(fields, "items").options || [],
        draft.items,
      ),
      this.buildPairsSection(channels, draft.pairs),
      this.buildChoiceSection(
        "workflow.editor.pairMeasurements",
        "pair_items",
        fieldByName(fields, "pair_items").options || [],
        draft.pair_items,
      ),
      this.buildLimitsSection(definition, fields, draft),
    );
  }

  defaultDraft(fields) {
    const values = {
      channels: defaultChoices(fieldByName(fields, "channels")),
      items: defaultChoices(fieldByName(fields, "items")),
      pairs: [],
      pair_items: defaultChoices(fieldByName(fields, "pair_items")),
    };
    for (const name of [
      "count", "duration_seconds", "trigger_timeout_seconds", "interval_seconds",
    ]) {
      const value = fieldByName(fields, name).default;
      values[name] = value === undefined ? "" : String(value);
    }
    values.stop_on_error = Boolean(fieldByName(fields, "stop_on_error").default);
    return values;
  }

  sanitizeDraft(draft, fields) {
    const channelOptions = new Set(
      (fieldByName(fields, "channels").options || []).map(String),
    );
    const itemOptions = new Set(
      (fieldByName(fields, "items").options || []).map(String),
    );
    const pairItemOptions = new Set(
      (fieldByName(fields, "pair_items").options || []).map(String),
    );
    return {
      ...draft,
      channels: (draft.channels || []).map(String).filter((value) => channelOptions.has(value)),
      items: (draft.items || []).map(String).filter((value) => itemOptions.has(value)),
      pairs: (draft.pairs || []).filter(
        (pair) => channelOptions.has(String(pair.source))
          && channelOptions.has(String(pair.reference)),
      ).map((pair) => ({
        source: String(pair.source),
        reference: String(pair.reference),
      })),
      pair_items: (draft.pair_items || []).map(String).filter(
        (value) => pairItemOptions.has(value),
      ),
    };
  }

  buildSection(titleKey) {
    const section = document.createElement("section");
    section.className = "workflow-editor-section";
    const heading = document.createElement("strong");
    heading.className = "workflow-editor-heading";
    heading.textContent = translate(titleKey);
    section.append(heading);
    return section;
  }

  buildChoiceSection(titleKey, name, options, selected) {
    const section = this.buildSection(titleKey);
    const choices = document.createElement("div");
    choices.className = "workflow-editor-choices";
    const selectedValues = new Set((selected || []).map(String));
    this.controls[name] = [];
    for (const option of options) {
      const choice = document.createElement("label");
      choice.className = "multi-choice-option";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = String(option);
      input.checked = selectedValues.has(input.value);
      input.dataset.workflowField = name;
      const text = document.createElement("span");
      text.textContent = name === "channels"
        ? channelLabel(option)
        : translatedChoice(option);
      choice.append(input, text);
      choices.append(choice);
      this.controls[name].push(input);
      input.addEventListener("change", () => this.captureDraft());
    }
    section.append(choices);
    return section;
  }

  buildPairsSection(channels, pairs) {
    const section = this.buildSection("workflow.editor.pairs");
    this.pairsHost = document.createElement("div");
    this.pairsHost.className = "workflow-editor-pairs";
    section.append(this.pairsHost);
    for (const pair of pairs) this.appendPairRow(channels, pair);
    this.addPairButton = document.createElement("button");
    this.addPairButton.type = "button";
    this.addPairButton.className = "secondary trigger-editor-action";
    this.addPairButton.textContent = translate("workflow.editor.addPair");
    this.addPairButton.addEventListener("click", () => {
      this.captureDraft();
      const source = channels[0] || "";
      const reference = channels.find((channel) => channel !== source) || source;
      this.appendPairRow(channels, { source, reference });
      this.captureDraft();
      this.applyBusyState();
    });
    section.append(this.addPairButton);
    return section;
  }

  appendPairRow(channels, pair) {
    const row = document.createElement("div");
    row.className = "workflow-editor-pair";
    const source = this.buildChannelSelect("source_channel", channels, pair.source);
    const reference = this.buildChannelSelect(
      "reference_channel", channels, pair.reference,
    );
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "secondary workflow-editor-pair-remove";
    remove.textContent = translate("workflow.editor.removePair");
    remove.setAttribute("aria-label", translate("workflow.editor.removePair"));
    const entry = { row, source: source.input, reference: reference.input, remove };
    remove.addEventListener("click", () => {
      row.remove();
      this.pairRows = this.pairRows.filter((item) => item !== entry);
      this.captureDraft();
    });
    source.input.addEventListener("change", () => this.captureDraft());
    reference.input.addEventListener("change", () => this.captureDraft());
    row.append(source.wrapper, reference.wrapper, remove);
    this.pairRows.push(entry);
    this.pairsHost.append(row);
  }

  buildChannelSelect(name, channels, selected) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const label = document.createElement("span");
    label.textContent = translate(`field.${name}`);
    const input = document.createElement("select");
    input.dataset.workflowField = name;
    for (const channel of channels) {
      input.append(new Option(channelLabel(channel), channel));
    }
    input.value = String(selected || "");
    wrapper.append(label, input);
    return { wrapper, input };
  }

  buildLimitsSection(definition, fields, draft) {
    const section = this.buildSection("workflow.editor.runLimits");
    const limits = document.createElement("div");
    limits.className = "workflow-editor-limits";
    const names = definition.id === "measure-log"
      ? ["count", "duration_seconds", "interval_seconds"]
      : ["count", "trigger_timeout_seconds", "interval_seconds"];
    for (const name of names) {
      const field = fieldByName(fields, name);
      const control = this.buildNumberField(field, draft[name]);
      this.controls[name] = control.input;
      limits.append(control.wrapper);
    }
    if (definition.id === "measure-log") {
      const wrapper = document.createElement("label");
      wrapper.className = "field field-boolean workflow-editor-stop";
      const label = document.createElement("span");
      label.textContent = translate("field.stop_on_error");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = Boolean(draft.stop_on_error);
      input.dataset.workflowField = "stop_on_error";
      input.addEventListener("change", () => this.captureDraft());
      wrapper.append(label, input);
      this.controls.stop_on_error = input;
      limits.append(wrapper);
    }
    section.append(limits);
    return section;
  }

  buildNumberField(field, value) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const label = document.createElement("span");
    label.textContent = translate(`field.${field.name}`);
    const input = document.createElement("input");
    input.type = "number";
    input.step = field.type === "integer" ? "1" : "any";
    if (field.minimum !== undefined) input.min = String(field.minimum);
    if (field.maximum !== undefined) input.max = String(field.maximum);
    input.required = field.required === true;
    input.value = value || "";
    input.dataset.workflowField = field.name;
    input.addEventListener("input", () => this.captureDraft());
    wrapper.append(label, input);
    return { wrapper, input };
  }

  captureDraft() {
    if (!this.renderedKey || !this.controls.channels) return;
    const draft = {
      channels: this.checkedValues("channels"),
      items: this.checkedValues("items"),
      pairs: this.pairRows.map((row) => ({
        source: row.source.value,
        reference: row.reference.value,
      })),
      pair_items: this.checkedValues("pair_items"),
      count: this.controls.count?.value || "",
      duration_seconds: this.controls.duration_seconds?.value || "",
      trigger_timeout_seconds: this.controls.trigger_timeout_seconds?.value || "",
      interval_seconds: this.controls.interval_seconds?.value || "",
      stop_on_error: Boolean(this.controls.stop_on_error?.checked),
    };
    this.drafts.set(this.renderedKey, draft);
  }

  checkedValues(name) {
    return (this.controls[name] || []).filter((input) => input.checked).map(
      (input) => input.value,
    );
  }

  values() {
    this.captureDraft();
    const definition = this.selectedDefinition();
    const draft = this.drafts.get(this.currentKey());
    if (!definition || !draft) return null;
    for (const name of [
      "count", "duration_seconds", "trigger_timeout_seconds", "interval_seconds",
    ]) {
      const input = this.controls[name];
      input?.setCustomValidity?.("");
      if (input && !input.checkValidity()) {
        input.reportValidity?.();
        return null;
      }
    }
    if (definition.id === "measure-log" && !draft.count && !draft.duration_seconds) {
      this.controls.count.setCustomValidity(translate("workflow.editor.limitRequired"));
      this.controls.count.reportValidity?.();
      return null;
    }
    for (const row of this.pairRows) {
      row.reference.setCustomValidity("");
      if (row.source.value === row.reference.value) {
        row.reference.setCustomValidity(translate("workflow.editor.distinctPair"));
        row.reference.reportValidity?.();
        return null;
      }
    }
    if (!draft.items.length) return null;
    const pairItemControl = this.controls.pair_items[0];
    pairItemControl?.setCustomValidity?.("");
    if (!draft.pair_items.length) {
      pairItemControl?.setCustomValidity?.(
        translate("workflow.editor.pairMeasurementRequired"),
      );
      pairItemControl?.reportValidity?.();
      return null;
    }
    const parameters = {
      items: draft.items.join(","),
      pair_items: draft.pair_items.join(","),
    };
    if (draft.interval_seconds !== "") {
      parameters.interval_seconds = Number(draft.interval_seconds);
    }
    if (draft.channels.length) parameters.channels = draft.channels.join(",");
    if (draft.pairs.length) {
      parameters.pairs = draft.pairs.map(
        (pair) => `${pair.source}:${pair.reference}`,
      );
    }
    for (const name of ["count", "duration_seconds", "trigger_timeout_seconds"]) {
      if (draft[name] !== "") parameters[name] = Number(draft[name]);
    }
    if (definition.id === "measure-log") {
      parameters.stop_on_error = draft.stop_on_error;
    }
    return parameters;
  }

  async submit() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return null;
    const definition = this.selectedDefinition();
    const parameters = this.values();
    if (!definition || parameters === null) return null;
    this.setBusy(true);
    try {
      return await this.hooks.executeCommand(
        definition.id,
        parameters,
        { intent: "command" },
      );
    } finally {
      this.setBusy(false);
    }
  }

  setBusy(value) {
    this.busy = value;
    this.applyBusyState();
  }

  applyBusyState() {
    const disabled = this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable();
    this.runButton.disabled = disabled;
    this.container.querySelectorAll("input, select, button").forEach((control) => {
      control.disabled = disabled;
    });
  }
}
