import { hasTranslation, translate } from "/static/i18n.js";
import { applyNumericFieldConstraints } from "/static/numeric-input.js";

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
    if (!definition) {
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
      this.drafts.get(key) || this.defaultDraft(fields, definition),
      fields,
    );
    this.drafts.set(key, draft);
    this.controls = {};
    this.pairRows = [];
    this.container.replaceChildren();

    if (definition.id === "measure-until") {
      this.renderMeasureUntilWorkflow(definition, fields, draft);
      return;
    }
    if (["capture-batch", "capture-until", "capture-monitor", "triggered-capture-series"].includes(definition.id)) {
      this.renderWaveformWorkflow(definition, fields, draft);
      return;
    }

    const channelField = fieldByName(fields, "channels");
    const channels = (channelField.options || []).map(String);
    this.pairItemsSection = this.buildChoiceSection(
      "workflow.editor.pairMeasurements",
      "pair_items",
      fieldByName(fields, "pair_items").options || [],
      draft.pair_items,
    );
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
      ...(definition.id === "measure-log"
        ? [this.pairItemsSection, this.buildPairsSection(channels, draft.pairs)]
        : [this.buildPairsSection(channels, draft.pairs), this.pairItemsSection]),
      this.buildLimitsSection(definition, fields, draft),
    );
    this.updatePairItemsVisibility();
  }

  defaultDraft(fields, definition) {
    const values = {
      channels: defaultChoices(fieldByName(fields, "channels")),
      items: defaultChoices(fieldByName(fields, "items")),
      pairs: [],
      pair_items: definition?.id === "measure-log"
        ? [] : defaultChoices(fieldByName(fields, "pair_items")),
    };
    for (const name of [
      "channel", "item", "count", "duration_seconds", "trigger_timeout_seconds", "interval_seconds",
      "condition_channel", "points", "format", "metric", "operator",
      "threshold", "timeout_seconds", "retention_points",
    ]) {
      const value = fieldByName(fields, name).default;
      values[name] = value === undefined ? "" : String(value);
    }
    if (values.channel === "" && fieldByName(fields, "channel").options) {
      const opts = fieldByName(fields, "channel").options.map(String);
      values.channel = opts[0] || "1";
    }
    if (values.item === "" && fieldByName(fields, "item").options) {
      values.item = String(fieldByName(fields, "item").options[0] || "vpp");
    }
    values.stop_on_error = Boolean(fieldByName(fields, "stop_on_error").default);
    values.save_results = fieldByName(fields, "save_results").default !== false;
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
    const singleChannelField = fieldByName(fields, "channel");
    const singleChannelOptions = new Set(
      (singleChannelField.options || []).map(String),
    );
    const singleItemField = fieldByName(fields, "item");
    const singleItemOptions = new Set(
      (singleItemField.options || []).map(String),
    );
    const sanitized = {
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
    if (singleChannelField.options) {
      const raw = String(draft.channel || "");
      sanitized.channel = singleChannelOptions.has(raw)
        ? raw
        : String(singleChannelField.default ?? singleChannelField.options[0] ?? "1");
    }
    if (singleItemField.options) {
      const raw = String(draft.item || "");
      sanitized.item = singleItemOptions.has(raw)
        ? raw
        : String(singleItemField.default ?? singleItemField.options[0] ?? "vpp");
    }
    return sanitized;
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
      input.addEventListener("change", () => {
        this.captureDraft();
        if (name === "pair_items") {
          this.controls.pair_items?.[0]?.setCustomValidity?.("");
          this.applyBusyState();
        }
      });
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
      this.controls.pair_items?.[0]?.setCustomValidity?.("");
      this.updatePairItemsVisibility();
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
      this.updatePairItemsVisibility();
    });
    source.input.addEventListener("change", () => this.captureDraft());
    reference.input.addEventListener("change", () => this.captureDraft());
    row.append(source.wrapper, reference.wrapper, remove);
    this.pairRows.push(entry);
    this.pairsHost.append(row);
  }

  updatePairItemsVisibility() {
    if (this.pairItemsSection) {
      this.pairItemsSection.hidden = this.selectedDefinition()?.id !== "measure-log"
        && this.pairRows.length === 0;
    }
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

  renderWaveformWorkflow(definition, fields, draft) {
    const channelField = fieldByName(fields, "channels");
    const channels = (channelField.options || []).map(String);
    const channelSection = this.buildChoiceSection(
      "workflow.editor.channels", "channels", channels, draft.channels,
    );
    this.container.append(channelSection);
    for (const input of this.controls.channels) {
      input.addEventListener("change", () => this.refreshConditionChannel());
    }

    const settings = this.buildSection("workflow.editor.captureSettings");
    const grid = document.createElement("div");
    grid.className = "workflow-editor-limits";
    const enumNames = definition.id === "capture-until"
      ? ["condition_channel", "points", "format", "metric", "operator"]
      : ["points", "format"];
    const numberNames = definition.id === "capture-until"
      ? ["threshold", "count", "timeout_seconds", "interval_seconds"]
      : definition.id === "capture-batch"
        ? ["count", "interval_seconds"]
        : definition.id === "triggered-capture-series"
          ? ["count", "trigger_timeout_seconds", "interval_seconds"]
          : ["count", "interval_seconds", "retention_points"];
    for (const name of enumNames) {
      const field = fieldByName(fields, name);
      const control = this.buildEnumField(field, draft[name]);
      this.controls[name] = control.input;
      grid.append(control.wrapper);
    }
    for (const name of numberNames) {
      const field = fieldByName(fields, name);
      const control = this.buildNumberField(field, draft[name]);
      this.controls[name] = control.input;
      grid.append(control.wrapper);
    }
    if (definition.id === "capture-monitor") {
      const saveWrapper = document.createElement("label");
      saveWrapper.className = "field field-boolean workflow-editor-save";
      const label = document.createElement("span");
      label.textContent = translate("field.save_results");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = draft.save_results !== false;
      input.addEventListener("change", () => this.captureDraft());
      saveWrapper.append(label, input);
      this.controls.save_results = input;
      grid.append(saveWrapper);
    }
    settings.append(grid);
    this.container.append(settings);

    if (definition.id === "capture-until") {
      this.refreshConditionChannel();
    } else if (definition.id === "capture-monitor") {
      const warning = document.createElement("p");
      warning.className = "compact-note workflow-monitor-warning";
      warning.textContent = translate("workflow.monitor.retentionWarning");
      this.monitorStatus = document.createElement("pre");
      this.monitorStatus.className = "workflow-monitor-status";
      this.monitorCanvas = document.createElement("canvas");
      this.monitorCanvas.className = "workflow-monitor-plot";
      this.monitorCanvas.width = 800;
      this.monitorCanvas.height = 260;
      this.monitorCanvas.setAttribute("aria-label", translate("workflow.monitor.plot"));
      this.container.append(warning, this.monitorStatus, this.monitorCanvas);
      this.monitorChunks ||= [];
      this.renderMonitorRuntime();
    }
  }

  buildEnumField(field, value) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const label = document.createElement("span");
    label.textContent = translate(`field.${field.name}`);
    const input = document.createElement("select");
    for (const option of field.options || []) {
      const text = field.name === "condition_channel"
        ? channelLabel(option)
        : translatedChoice(option);
      input.append(new Option(text, option));
    }
    input.value = String(value ?? field.default ?? "");
    input.required = field.required === true;
    input.addEventListener("change", () => this.captureDraft());
    wrapper.append(label, input);
    return { wrapper, input };
  }

  refreshConditionChannel() {
    const select = this.controls.condition_channel;
    if (!select) return;
    const selected = this.checkedValues("channels");
    const previous = select.value;
    select.replaceChildren(...selected.map(
      (channel) => new Option(channelLabel(channel), channel),
    ));
    select.value = selected.includes(previous) ? previous : (selected[0] || "");
    this.captureDraft();
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
    const saveWrapper = document.createElement("label");
    saveWrapper.className = "field field-boolean workflow-editor-save";
    const saveLabel = document.createElement("span");
    saveLabel.textContent = translate("field.save_results");
    const saveInput = document.createElement("input");
    saveInput.type = "checkbox";
    saveInput.checked = draft.save_results !== false;
    saveInput.dataset.workflowField = "save_results";
    saveInput.addEventListener("change", () => this.captureDraft());
    saveWrapper.append(saveLabel, saveInput);
    this.controls.save_results = saveInput;
    limits.append(saveWrapper);
    section.append(limits);
    return section;
  }

  buildNumberField(field, value) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const label = document.createElement("span");
    label.textContent = translate(`field.${field.name}`);
    const input = document.createElement("input");
    applyNumericFieldConstraints(input, field);
    input.required = field.required === true;
    input.value = value || "";
    input.dataset.workflowField = field.name;
    input.addEventListener("input", () => this.captureDraft());
    wrapper.append(label, input);
    return { wrapper, input };
  }

  captureDraft() {
    if (!this.renderedKey || (!this.controls.channels && !this.controls.channel)) return;
    const definition = this.selectedDefinition();
    if (definition?.id === "capture-batch") {
      const draft = {
        channels: this.checkedValues("channels"),
        points: this.controls.points?.value || "",
        format: this.controls.format?.value || "",
        count: this.controls.count?.value || "",
        interval_seconds: this.controls.interval_seconds?.value || "",
      };
      this.drafts.set(this.renderedKey, draft);
      return;
    }
    if (definition?.id === "triggered-capture-series") {
      const draft = {
        channels: this.checkedValues("channels"),
        points: this.controls.points?.value || "",
        format: this.controls.format?.value || "",
        count: this.controls.count?.value || "",
        trigger_timeout_seconds: this.controls.trigger_timeout_seconds?.value || "",
        interval_seconds: this.controls.interval_seconds?.value || "",
      };
      this.drafts.set(this.renderedKey, draft);
      return;
    }
    if (definition?.id === "measure-until") {
      const draft = {
        channel: this.controls.channel?.value || "",
        item: this.controls.item?.value || "",
        operator: this.controls.operator?.value || "",
        threshold: this.controls.threshold?.value || "",
        timeout_seconds: this.controls.timeout_seconds?.value || "",
        interval_seconds: this.controls.interval_seconds?.value || "",
        save_results: this.controls.save_results?.checked !== false,
      };
      this.drafts.set(this.renderedKey, draft);
      return;
    }
    if (["capture-until", "capture-monitor"].includes(definition?.id)) {
      const draft = {
        channels: this.checkedValues("channels"),
        condition_channel: this.controls.condition_channel?.value || "",
        points: this.controls.points?.value || "",
        format: this.controls.format?.value || "",
        metric: this.controls.metric?.value || "",
        operator: this.controls.operator?.value || "",
        threshold: this.controls.threshold?.value || "",
        count: this.controls.count?.value || "",
        timeout_seconds: this.controls.timeout_seconds?.value || "",
        interval_seconds: this.controls.interval_seconds?.value || "",
        retention_points: this.controls.retention_points?.value || "",
        save_results: this.controls.save_results?.checked !== false,
      };
      this.drafts.set(this.renderedKey, draft);
      return;
    }
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
      save_results: this.controls.save_results?.checked !== false,
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
    if (["capture-batch", "capture-until", "capture-monitor", "triggered-capture-series"].includes(definition.id)) {
      return this.waveformWorkflowValues(definition, draft);
    }
    if (definition.id === "measure-until") {
      return this.measureUntilValues(definition, draft);
    }
    for (const name of [
      "count", "duration_seconds", "trigger_timeout_seconds", "interval_seconds",
    ]) {
      const input = this.controls[name];
      input?.setCustomValidity?.("");
      if (input && input.value !== "" && input.dataset.exclusiveMinimum !== undefined
          && Number(input.value) <= Number(input.dataset.exclusiveMinimum)) {
        input.setCustomValidity(translate("form.greaterThan", {
          value: input.dataset.exclusiveMinimum,
        }));
      }
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
    const pairItemControl = this.controls.pair_items?.[0];
    pairItemControl?.setCustomValidity?.("");
    if (draft.pairs.length && !draft.pair_items.length) {
      pairItemControl?.setCustomValidity?.(
        translate("workflow.editor.pairMeasurementRequired"),
      );
      pairItemControl?.reportValidity?.();
      return null;
    }
    if (
      definition.id === "measure-log"
      && !draft.pairs.length
      && draft.pair_items.length
    ) {
      pairItemControl?.setCustomValidity?.(
        translate("workflow.editor.channelPairRequired"),
      );
      pairItemControl?.reportValidity?.();
      return null;
    }
    const pairItems = draft.pair_items.length
      ? draft.pair_items
      : (this.controls.pair_items || []).slice(0, 1).map((input) => input.value);
    const parameters = {
      items: draft.items.join(","),
      pair_items: pairItems.join(","),
      save_results: draft.save_results !== false,
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

  waveformWorkflowValues(definition, draft) {
    if (!draft.channels.length) return null;
    const numberNames = definition.id === "capture-until"
      ? ["threshold", "count", "timeout_seconds", "interval_seconds"]
      : definition.id === "capture-batch"
        ? ["count", "interval_seconds"]
        : definition.id === "triggered-capture-series"
          ? ["count", "trigger_timeout_seconds", "interval_seconds"]
          : ["count", "interval_seconds", "retention_points"];
    for (const name of numberNames) {
      const input = this.controls[name];
      input?.setCustomValidity?.("");
      if (input && input.value !== "" && input.dataset.exclusiveMinimum !== undefined
          && Number(input.value) <= Number(input.dataset.exclusiveMinimum)) {
        input.setCustomValidity(translate("form.greaterThan", {
          value: input.dataset.exclusiveMinimum,
        }));
      }
      if (input && !input.checkValidity()) {
        input.reportValidity?.();
        return null;
      }
    }
    const parameters = {
      channels: draft.channels.join(","),
      points: Number(draft.points),
      format: draft.format,
      count: Number(draft.count),
      interval_seconds: Number(draft.interval_seconds),
    };
    if (definition.id === "capture-until") {
      if (!draft.condition_channel) return null;
      Object.assign(parameters, {
        condition_channel: Number(draft.condition_channel),
        metric: draft.metric,
        operator: draft.operator,
        threshold: Number(draft.threshold),
        timeout_seconds: Number(draft.timeout_seconds),
      });
    } else if (definition.id === "triggered-capture-series") {
      parameters.trigger_timeout_seconds = Number(draft.trigger_timeout_seconds);
    } else if (definition.id === "capture-monitor") {
      parameters.retention_points = Number(draft.retention_points);
      parameters.save_results = draft.save_results !== false;
    }
    return parameters;
  }

  measureUntilValues(definition, draft) {
    const numberNames = ["threshold", "timeout_seconds", "interval_seconds"];
    for (const name of numberNames) {
      const input = this.controls[name];
      input?.setCustomValidity?.("");
      if (input && input.value !== "" && input.dataset.exclusiveMinimum !== undefined
          && Number(input.value) <= Number(input.dataset.exclusiveMinimum)) {
        input.setCustomValidity(translate("form.greaterThan", {
          value: input.dataset.exclusiveMinimum,
        }));
      }
      if (input && !input.checkValidity()) {
        input.reportValidity?.();
        return null;
      }
    }
    if (!draft.channel || !draft.item || !draft.operator || draft.threshold === "" || draft.timeout_seconds === "") {
      const missing = !draft.channel ? this.controls.channel
        : !draft.item ? this.controls.item
          : !draft.operator ? this.controls.operator
            : draft.threshold === "" ? this.controls.threshold
              : this.controls.timeout_seconds;
      missing?.reportValidity?.();
      return null;
    }
    return {
      channel: Number(draft.channel),
      item: draft.item,
      operator: draft.operator,
      threshold: Number(draft.threshold),
      timeout_seconds: Number(draft.timeout_seconds),
      interval_seconds: draft.interval_seconds === "" ? 1 : Number(draft.interval_seconds),
      save_results: draft.save_results !== false,
    };
  }

  renderMeasureUntilWorkflow(definition, fields, draft) {
    const channelField = fieldByName(fields, "channel");
    const channels = (channelField.options || []).map(String);
    const channelControl = this.buildChannelSelect("channel", channels, draft.channel);
    this.controls.channel = channelControl.input;
    const channelSection = this.buildSection("workflow.editor.channels");
    channelSection.append(channelControl.wrapper);
    this.container.append(channelSection);

    const itemField = fieldByName(fields, "item");
    const itemControl = this.buildEnumField(itemField, draft.item);
    this.controls.item = itemControl.input;
    const measurementSection = this.buildSection("workflow.editor.measurements");
    measurementSection.append(itemControl.wrapper);
    this.container.append(measurementSection);

    const conditionSection = this.buildSection("workflow.editor.condition");
    const conditionGrid = document.createElement("div");
    conditionGrid.className = "workflow-editor-limits";
    const operatorField = fieldByName(fields, "operator");
    const thresholdField = fieldByName(fields, "threshold");
    const operatorControl = this.buildEnumField(operatorField, draft.operator);
    const thresholdControl = this.buildNumberField(thresholdField, draft.threshold);
    this.controls.operator = operatorControl.input;
    this.controls.threshold = thresholdControl.input;
    conditionGrid.append(operatorControl.wrapper, thresholdControl.wrapper);
    conditionSection.append(conditionGrid);
    this.container.append(conditionSection);

    const limitsSection = this.buildSection("workflow.editor.runLimits");
    const limitsGrid = document.createElement("div");
    limitsGrid.className = "workflow-editor-limits";
    const timeoutField = fieldByName(fields, "timeout_seconds");
    const intervalField = fieldByName(fields, "interval_seconds");
    const timeoutControl = this.buildNumberField(timeoutField, draft.timeout_seconds);
    const intervalControl = this.buildNumberField(intervalField, draft.interval_seconds);
    this.controls.timeout_seconds = timeoutControl.input;
    this.controls.interval_seconds = intervalControl.input;
    limitsGrid.append(timeoutControl.wrapper, intervalControl.wrapper);

    const saveWrapper = document.createElement("label");
    saveWrapper.className = "field field-boolean workflow-editor-save";
    const saveLabel = document.createElement("span");
    saveLabel.textContent = translate("field.save_results");
    const saveInput = document.createElement("input");
    saveInput.type = "checkbox";
    saveInput.checked = draft.save_results !== false;
    saveInput.addEventListener("change", () => this.captureDraft());
    saveWrapper.append(saveLabel, saveInput);
    this.controls.save_results = saveInput;
    limitsGrid.append(saveWrapper);
    limitsSection.append(limitsGrid);
    this.container.append(limitsSection);
  }

  handleJobUpdate(job) {
    if (job?.command !== "capture-monitor" || !job.monitor_runtime) return;
    const reset = Boolean(job.monitor_runtime.reset);
    if (reset) this.monitorChunks = [];
    for (const update of job.monitor_runtime.updates || []) {
      const dropped = reset ? 0 : Number(update.dropped_capture_count || 0);
      if (dropped > 0) this.monitorChunks.splice(0, dropped);
      this.monitorChunks.push(update);
    }
    this.monitorSummary = job.monitor_runtime.summary || this.monitorSummary;
    this.renderMonitorRuntime();
  }

  renderMonitorRuntime() {
    if (this.monitorStatus) {
      const summary = this.monitorSummary || {};
      const metrics = Object.entries(summary.metrics || {}).map(
        ([channel, values]) => `${channel} max=${values.maximum} ${values.unit} min=${values.minimum} ${values.unit} p2p=${values.peak_to_peak} ${values.unit} abs-max=${values.abs_max} ${values.unit}`,
      ).join(" | ");
      this.monitorStatus.textContent = summary.completed_count
        ? `${summary.completed_count}/${summary.requested_count} observed=${summary.total_observed_points} retained=${summary.retained_points} dropped=${summary.dropped_points} ${metrics}`.trim()
        : translate("workflow.monitor.waiting");
    }
    const context = this.monitorCanvas?.getContext?.("2d");
    if (!context || !this.monitorChunks?.length) return;
    const width = this.monitorCanvas.width;
    const height = this.monitorCanvas.height;
    context.clearRect(0, 0, width, height);
    const series = {};
    for (const chunk of this.monitorChunks) {
      for (const [channel, data] of Object.entries(chunk.channels || {})) {
        const target = (series[channel] ||= []);
        for (let index = 0; index < data.values.length; index += 1) {
          target.push([chunk.global_start_index + index, data.values[index]]);
        }
      }
    }
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const values of Object.values(series)) {
      for (const [x, y] of values) {
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
      }
    }
    if (!Number.isFinite(minX)) return;
    const colors = ["#1769aa", "#c44d00", "#2e7d32", "#7b1fa2"];
    Object.values(series).forEach((values, channelIndex) => {
      context.beginPath();
      context.strokeStyle = colors[channelIndex % colors.length];
      values.forEach(([x, y], index) => {
        const px = 8 + ((x - minX) / Math.max(1, maxX - minX)) * (width - 16);
        const py = height - 8 - ((y - minY) / Math.max(1e-12, maxY - minY)) * (height - 16);
        if (index === 0) context.moveTo(px, py); else context.lineTo(px, py);
      });
      context.stroke();
    });
  }

  async submit() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return null;
    const definition = this.selectedDefinition();
    const parameters = this.values();
    if (!definition || parameters === null) return null;
    if (definition.id === "capture-monitor") {
      this.monitorChunks = [];
      this.monitorSummary = null;
      this.renderMonitorRuntime();
    }
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
    if (this.selectedDefinition()?.id === "measure-log" && this.addPairButton) {
      this.addPairButton.disabled = disabled || !this.checkedValues("pair_items").length;
    }
  }
}
