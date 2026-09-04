import { CommandForm } from "/static/command-form.js";
import { hasTranslation, translate } from "/static/i18n.js";

function fieldByName(fields, name) {
  return fields.find((field) => field.name === name) || {};
}

function defaultChoices(field) {
  if (Array.isArray(field.default)) return field.default.map(String);
  if (typeof field.default === "string") {
    return field.default.split(",").map((value) => value.trim()).filter(Boolean);
  }
  return [];
}

function choiceLabel(value) {
  const key = `enum.${String(value)}`;
  return hasTranslation(key) ? translate(key) : String(value);
}

function measurementPayload(job) {
  return job?.result?.result?.measurements || job?.result?.measurements || null;
}

function statisticsPayload(job) {
  return job?.result?.result?.statistics || job?.result?.statistics || null;
}

function windowValue(job) {
  const value = job?.result?.result?.window?.window
    ?? job?.result?.window?.window
    ?? job?.result?.result?.window;
  return typeof value === "string" ? value.toLowerCase() : "";
}

export class MeasurementEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.contextKey = null;
    this.renderedKey = null;
    this.measureDraft = null;
    this.sweepDrafts = new Map();
    this.sweepRenderedKey = null;
    this.sweepControls = {};
    this.sweepPairRows = [];
    this.windowCurrent = "";
    this.windowReadback = "";
    this.windowDirty = false;
    this.frontPanelState = { kind: "unread", payload: null };
    this.frontPanelReadError = null;
    this.statisticsState = { kind: "unread", payload: null };
    this.statisticsReadError = null;
    this.controls = {};
  }

  definition(id) {
    return this.catalog.commands.find((command) => command.id === id) || null;
  }

  markerToggleSupported() {
    if (!this.catalog?.activeModelId) return null;
    const definition = this.definition("measure-show");
    const fields = this.catalog?.fieldsFor
      ? this.catalog.fieldsFor(definition)
      : definition?.fields || [];
    return fields.some((field) => field.name === "enabled");
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "measurement" ? selected : null;
  }

  syncContext() {
    const key = this.hooks.contextKey();
    if (key === this.contextKey) return false;
    this.contextKey = key;
    this.windowCurrent = "";
    this.windowReadback = "";
    this.windowDirty = false;
    this.frontPanelState = { kind: "unread", payload: null };
    this.frontPanelReadError = null;
    this.statisticsState = { kind: "unread", payload: null };
    this.statisticsReadError = null;
    this.renderedKey = null;
    return true;
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    if (this.measureForm) this.measureDraft = this.measureForm.draft();
    this.captureSweepDraft();
    this.renderedKey = null;
    this.schedulePresentation();
  }

  present() {
    this.syncContext();
    const selected = this.selectedDefinition();
    if (!selected) {
      this.container.replaceChildren();
      this.renderedKey = null;
      this.controls = {};
      return;
    }
    const key = `${this.contextKey}|${selected.id}`;
    if (key !== this.renderedKey) {
      if (this.measureForm) this.measureDraft = this.measureForm.draft();
      this.captureSweepDraft();
      this.renderedKey = key;
      if (selected.id === "measure") this.renderSettings();
      else if (selected.id === "measure-sweep") this.renderSweep(key);
      else if (selected.id === "front-panel-measurements") this.renderFrontPanel();
    }
    this.applyBusyState();
  }

  renderSettings() {
    this.container.replaceChildren();
    this.controls = {};
    const measure = this.definition("measure");
    const formHost = document.createElement("form");
    formHost.className = "command-form measurement-editor-form";
    this.measureForm = new CommandForm(formHost, this.catalog);
    this.measureForm.render(measure, {
      draft: this.measureDraft,
      onDirty: () => {
        this.measureDraft = this.measureForm.draft();
      },
    });
    this.container.append(formHost);

    if (this.hooks.mode() === "dry-run") {
      const note = document.createElement("p");
      note.className = "compact-note measurement-editor-note";
      note.textContent = translate("measurement.window.dryRun");
      this.container.append(note);
      this.windowForm = null;
    } else {
      this.container.append(this.buildWindowSection());
    }
  }

  buildWindowSection() {
    const section = document.createElement("section");
    section.className = "measurement-editor-section";
    const head = document.createElement("div");
    head.className = "measurement-editor-section-head";
    const heading = document.createElement("strong");
    heading.textContent = translate("measurement.window.title");
    this.controls.windowRefresh = document.createElement("button");
    this.controls.windowRefresh.type = "button";
    this.controls.windowRefresh.className = "secondary";
    this.controls.windowRefresh.textContent = translate("actions.refresh");
    this.controls.windowRefresh.addEventListener("click", () => void this.refreshWindow());
    head.append(heading, this.controls.windowRefresh);

    const formHost = document.createElement("form");
    formHost.className = "command-form measurement-window-form";
    this.windowForm = new CommandForm(formHost, this.catalog);
    const draft = this.windowCurrent
      ? [{ name: "window", value: this.windowCurrent, dirty: this.windowDirty }]
      : null;
    this.windowForm.render(this.definition("measure-window"), {
      draft,
      onDirty: () => {
        const select = formHost.querySelector('[data-field="window"]');
        this.windowCurrent = select?.value || "";
        this.windowDirty = Boolean(this.windowCurrent)
          && this.windowCurrent !== this.windowReadback;
        this.applyBusyState();
      },
    });
    const select = formHost.querySelector('[data-field="window"]');
    const placeholder = select?.querySelector('option[value=""]');
    if (placeholder) placeholder.textContent = translate("measurement.window.notRead");
    section.append(head, formHost);
    return section;
  }

  async refreshWindow() {
    if (!this.hooks.isCommandAvailable("measure-window")) return;
    const requestedContext = this.contextKey;
    const job = await this.hooks.executeCommand("measure-window", { action: "query" });
    if (requestedContext !== this.contextKey || job?.status !== "completed") return;
    const value = windowValue(job);
    if (!value || this.windowDirty) return;
    this.windowCurrent = value;
    this.windowReadback = value;
    this.renderedKey = null;
    this.present();
  }

  async runMeasurement() {
    const parameters = this.measureForm?.values();
    if (parameters === null || !this.hooks.isCommandAvailable("measure")) return;
    const requestedContext = this.contextKey;
    if (this.hooks.mode() !== "dry-run" && this.windowDirty) {
      const windowParameters = this.windowForm?.values();
      if (windowParameters === null) return;
      const windowJob = await this.hooks.executeCommand("measure-window", windowParameters);
      if (requestedContext !== this.contextKey || windowJob?.status !== "completed") return;
      this.windowReadback = this.windowCurrent;
      this.windowDirty = false;
      this.windowForm?.clearDirty();
    }
    if (requestedContext !== this.contextKey) return;
    await this.hooks.executeCommand("measure", parameters);
  }

  renderSweep(key) {
    const fields = this.catalog.fieldsFor(this.definition("measure-sweep"));
    const draft = this.sanitizeSweepDraft(
      this.sweepDrafts.get(key) || this.defaultSweepDraft(fields),
      fields,
    );
    this.sweepDrafts.set(key, draft);
    this.sweepRenderedKey = key;
    this.sweepControls = {};
    this.sweepPairRows = [];
    this.sweepPairItemsSection = this.buildSweepChoiceSection(
      "workflow.editor.pairMeasurements",
      "pair_items",
      fieldByName(fields, "pair_items").options || [],
      draft.pair_items,
      "workflow.editor.pairMeasurementsHelper",
    );
    this.container.replaceChildren(
      this.buildSweepChoiceSection(
        "workflow.editor.channels",
        "channels",
        fieldByName(fields, "channels").options || [],
        draft.channels,
      ),
      this.buildSweepChoiceSection(
        "workflow.editor.measurements",
        "items",
        fieldByName(fields, "items").options || [],
        draft.items,
      ),
      this.sweepPairItemsSection,
      this.buildSweepPairsSection(
        (fieldByName(fields, "channels").options || []).map(String),
        draft.pairs,
      ),
    );
    this.updateSweepAddPairState();
  }

  defaultSweepDraft(fields) {
    return {
      channels: (fieldByName(fields, "channels").options || []).map(String),
      items: defaultChoices(fieldByName(fields, "items")),
      pairs: [],
      pair_items: [],
    };
  }

  sanitizeSweepDraft(draft, fields) {
    const channels = new Set((fieldByName(fields, "channels").options || []).map(String));
    const items = new Set((fieldByName(fields, "items").options || []).map(String));
    const pairItems = new Set(
      (fieldByName(fields, "pair_items").options || []).map(String),
    );
    return {
      channels: (draft.channels || []).map(String).filter((value) => channels.has(value)),
      items: (draft.items || []).map(String).filter((value) => items.has(value)),
      pairs: (draft.pairs || []).filter(
        (pair) => channels.has(String(pair.source))
          && channels.has(String(pair.reference)),
      ).map((pair) => ({
        source: String(pair.source),
        reference: String(pair.reference),
      })),
      pair_items: (draft.pair_items || []).map(String).filter(
        (value) => pairItems.has(value),
      ),
    };
  }

  buildSweepSection(titleKey) {
    const section = document.createElement("section");
    section.className = "workflow-editor-section";
    const heading = document.createElement("strong");
    heading.className = "workflow-editor-heading";
    heading.textContent = translate(titleKey);
    section.append(heading);
    return section;
  }

  buildSweepChoiceSection(titleKey, name, options, selected, noteKey = null) {
    const section = this.buildSweepSection(titleKey);
    if (noteKey) {
      const note = document.createElement("p");
      note.className = "compact-note measurement-editor-note";
      note.textContent = translate(noteKey);
      section.append(note);
    }
    const choices = document.createElement("div");
    choices.className = "workflow-editor-choices";
    const selectedValues = new Set((selected || []).map(String));
    this.sweepControls[name] = [];
    for (const option of options) {
      const choice = document.createElement("label");
      choice.className = "multi-choice-option";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = String(option);
      input.checked = selectedValues.has(input.value);
      const text = document.createElement("span");
      text.textContent = name === "channels" ? `CH${option}` : choiceLabel(option);
      choice.append(input, text);
      choices.append(choice);
      this.sweepControls[name].push(input);
      input.addEventListener("change", () => {
        this.captureSweepDraft();
        if (name === "pair_items") {
          this.sweepControls.pair_items?.[0]?.setCustomValidity?.("");
          this.updateSweepAddPairState();
        }
      });
    }
    section.append(choices);
    return section;
  }

  buildSweepPairsSection(channels, pairs) {
    const section = this.buildSweepSection("workflow.editor.pairs");
    this.sweepPairsHost = document.createElement("div");
    this.sweepPairsHost.className = "workflow-editor-pairs";
    section.append(this.sweepPairsHost);
    for (const pair of pairs) this.appendSweepPairRow(channels, pair);
    this.sweepAddPairButton = document.createElement("button");
    this.sweepAddPairButton.type = "button";
    this.sweepAddPairButton.className = "secondary trigger-editor-action";
    this.sweepAddPairButton.textContent = translate("workflow.editor.addPair");
    this.sweepAddPairButton.addEventListener("click", () => {
      const source = channels[0] || "";
      const reference = channels.find((channel) => channel !== source) || source;
      this.appendSweepPairRow(channels, { source, reference });
      this.captureSweepDraft();
      this.sweepControls.pair_items?.[0]?.setCustomValidity?.("");
      this.applyBusyState();
    });
    section.append(this.sweepAddPairButton);
    return section;
  }

  appendSweepPairRow(channels, pair) {
    const row = document.createElement("div");
    row.className = "workflow-editor-pair";
    const source = this.buildSweepChannelSelect("source_channel", channels, pair.source);
    const reference = this.buildSweepChannelSelect(
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
      this.sweepPairRows = this.sweepPairRows.filter((item) => item !== entry);
      this.captureSweepDraft();
      if (this.sweepPairRows.length === 0) {
        this.sweepControls.pair_items?.[0]?.setCustomValidity?.("");
      }
    });
    source.input.addEventListener("change", () => this.captureSweepDraft());
    reference.input.addEventListener("change", () => this.captureSweepDraft());
    row.append(source.wrapper, reference.wrapper, remove);
    this.sweepPairRows.push(entry);
    this.sweepPairsHost.append(row);
  }

  updateSweepAddPairState() {
    if (!this.sweepAddPairButton) return;
    const hasPairItem = (this.sweepControls.pair_items || []).some((input) => input.checked);
    this.sweepAddPairButton.disabled = this.hooks.isExecutionBusy() || !hasPairItem;
  }

  buildSweepChannelSelect(name, channels, selected) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const label = document.createElement("span");
    label.textContent = translate(`field.${name}`);
    const input = document.createElement("select");
    for (const channel of channels) input.append(new Option(`CH${channel}`, channel));
    input.value = String(selected || "");
    wrapper.append(label, input);
    return { wrapper, input };
  }

  captureSweepDraft() {
    if (!this.sweepRenderedKey) return;
    const checked = (name) => (this.sweepControls[name] || [])
      .filter((input) => input.checked)
      .map((input) => input.value);
    this.sweepDrafts.set(this.sweepRenderedKey, {
      channels: checked("channels"),
      items: checked("items"),
      pairs: this.sweepPairRows.map((row) => ({
        source: row.source.value,
        reference: row.reference.value,
      })),
      pair_items: checked("pair_items"),
    });
  }

  sweepValues() {
    this.captureSweepDraft();
    const draft = this.sweepDrafts.get(this.sweepRenderedKey);
    if (!draft || !draft.items.length) return null;
    for (const row of this.sweepPairRows) {
      row.reference.setCustomValidity("");
      if (row.source.value === row.reference.value) {
        row.reference.setCustomValidity(translate("workflow.editor.distinctPair"));
        row.reference.reportValidity?.();
        return null;
      }
    }
    const pairItemControl = this.sweepControls.pair_items?.[0];
    pairItemControl?.setCustomValidity?.("");
    if (draft.pairs.length && !draft.pair_items.length) {
      pairItemControl?.setCustomValidity?.(
        translate("workflow.editor.pairMeasurementRequired"),
      );
      pairItemControl?.reportValidity?.();
      return null;
    }
    if (!draft.pairs.length && draft.pair_items.length) {
      pairItemControl?.setCustomValidity?.(
        translate("workflow.editor.channelPairRequired"),
      );
      pairItemControl?.reportValidity?.();
      return null;
    }
    const pairItems = draft.pair_items.length
      ? draft.pair_items
      : (this.sweepControls.pair_items || []).slice(0, 1).map((input) => input.value);
    const parameters = {
      items: draft.items.join(","),
      pair_items: pairItems.join(","),
    };
    if (draft.channels.length) parameters.channels = draft.channels.join(",");
    if (draft.pairs.length) {
      parameters.pairs = draft.pairs.map(
        (pair) => `${pair.source}:${pair.reference}`,
      );
    }
    return parameters;
  }

  async runMeasureSweep() {
    const parameters = this.sweepValues();
    if (parameters === null || !this.hooks.isCommandAvailable("measure-sweep")) return;
    await this.hooks.executeCommand("measure-sweep", parameters);
  }

  renderFrontPanel() {
    this.container.replaceChildren();
    this.controls = {};
    const actions = document.createElement("div");
    actions.className = "measurement-front-panel-actions";
    const buttons = document.createElement("div");
    buttons.className = "measurement-front-panel-buttons";
    const notes = document.createElement("div");
    notes.className = "measurement-front-panel-notes";
    const actionDefinitions = [
      ["frontPanelRefresh", "measure-results", "measurement.frontPanel.refresh", "primary"],
      ...(this.markerToggleSupported() !== false
        ? [
          ["frontPanelShow", "measure-show", "measurement.frontPanel.show", "secondary", true],
          ["frontPanelHide", "measure-show", "measurement.frontPanel.hide", "secondary", false],
        ]
        : []),
      ["frontPanelClear", "measure-clear", "measurement.frontPanel.clear", "danger"],
      ["frontPanelMenu", "measure-menu", "measurement.frontPanel.menu", "secondary"],
    ];
    for (const [name, command, key, className, enabled] of actionDefinitions) {
      const wrapper = document.createElement("div");
      wrapper.className = "measurement-front-panel-action";
      const button = document.createElement("button");
      button.type = "button";
      button.className = className;
      button.textContent = translate(key);
      button.addEventListener("click", () => {
        if (command === "measure-results") void this.refreshFrontPanel();
        else if (command === "measure-show") void this.showFrontPanel(enabled);
        else if (command === "measure-menu") void this.openMeasurementMenu();
        else void this.clearFrontPanel();
      });
      this.controls[name] = button;
      wrapper.append(button);
      const reason = this.catalog.supportReason(this.definition(command));
      if (reason) {
        const note = document.createElement("small");
        note.className = "command-support-reason";
        note.textContent = command === "measure-results"
          ? translate("measurement.frontPanel.resultsUnsupported")
          : reason;
        notes.append(note);
      }
      buttons.append(wrapper);
    }
    if (this.markerToggleSupported() === false) {
      const note = document.createElement("p");
      note.className = "compact-note measurement-front-panel-marker-note";
      note.textContent = translate("measurement.frontPanel.markersAlwaysOn");
      notes.append(note);
    }
    actions.append(buttons);
    if (notes.children.length) actions.append(notes);
    this.container.append(actions);
    const installDefinition = this.definition("measure-install");
    if (installDefinition && this.catalog.supported(installDefinition)) {
      this.container.append(this.buildInstallSection(installDefinition));
    }
    this.frontPanelContent = null;
    const resultsDefinition = this.definition("measure-results");
    if (resultsDefinition && this.catalog.supported(resultsDefinition)) {
      const result = document.createElement("section");
      result.className = "measurement-front-panel-results";
      const heading = document.createElement("strong");
      heading.textContent = translate("measurement.frontPanel.resultsTitle");
      this.frontPanelContent = document.createElement("div");
      this.frontPanelContent.className = "measurement-front-panel-content";
      this.frontPanelContent.setAttribute("aria-live", "polite");
      result.append(heading, this.frontPanelContent);
      this.container.append(result);
      this.renderFrontPanelReadback();
    }
    const statisticsDefinition = this.definition("measurement-statistics");
    if (statisticsDefinition && this.catalog.supported(statisticsDefinition)) {
      this.container.append(this.buildStatisticsSection());
      this.renderStatisticsReadback();
    }
  }

  buildInstallSection(definition) {
    const section = document.createElement("section");
    section.className = "measurement-editor-section measurement-install-section";
    const heading = document.createElement("strong");
    heading.textContent = translate("measurement.frontPanel.add");
    const form = document.createElement("form");
    form.className = "command-form measurement-install-form";
    this.installForm = new CommandForm(form, this.catalog);
    this.installForm.render(definition);
    const actions = document.createElement("div");
    actions.className = "measurement-front-panel-buttons";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "primary";
    button.textContent = translate("measurement.frontPanel.add");
    button.addEventListener("click", () => void this.addFrontPanelMeasurement());
    this.controls.frontPanelInstall = button;
    actions.append(button);
    section.append(heading, form, actions);
    return section;
  }

  buildStatisticsSection() {
    const section = document.createElement("section");
    section.className = "measurement-editor-section measurement-statistics-section";
    const heading = document.createElement("strong");
    heading.textContent = translate("measurement.statistics.title");
    const form = document.createElement("div");
    form.className = "measurement-statistics-form";

    this.controls.statisticsMode = this.statisticsFixedValue(
      "measurement.statistics.mode", choiceLabel("all"),
    );
    this.controls.statisticsDisplay = this.statisticsCheckbox(
      "measurement.statistics.display",
    );
    this.controls.statisticsMaxCountMode = this.statisticsSelect(
      "measurement.statistics.maximumCount",
      ["infinite", "numeric"],
    );
    this.controls.statisticsMaxCount = document.createElement("input");
    this.controls.statisticsMaxCount.type = "number";
    this.controls.statisticsMaxCount.min = "2";
    this.controls.statisticsMaxCount.max = "2000";
    this.controls.statisticsMaxCount.value = "2";
    const maxCountField = document.createElement("label");
    maxCountField.className = "field";
    const maxCountLabel = document.createElement("span");
    maxCountLabel.textContent = translate("measurement.statistics.numericCount");
    maxCountField.append(maxCountLabel, this.controls.statisticsMaxCount);
    this.controls.statisticsRsd = this.statisticsCheckbox(
      "measurement.statistics.relativeStddev",
    );
    form.append(
      this.controls.statisticsMode.wrapper,
      this.controls.statisticsDisplay.wrapper,
      this.controls.statisticsMaxCountMode.wrapper,
      maxCountField,
      this.controls.statisticsRsd.wrapper,
    );
    this.controls.statisticsMaxCountMode.input.addEventListener(
      "change", () => this.updateStatisticsMaxCountState(),
    );

    const actions = document.createElement("div");
    actions.className = "measurement-front-panel-buttons";
    for (const [name, key, className, handler] of [
      ["statisticsApply", "actions.apply", "primary", () => this.applyStatistics()],
      ["statisticsRefresh", "actions.refresh", "secondary", () => this.refreshStatistics()],
      ["statisticsReset", "measurement.statistics.reset", "secondary", () => this.runStatisticsAction("reset")],
    ]) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = className;
      button.textContent = translate(key);
      button.addEventListener("click", () => void handler());
      this.controls[name] = button;
      actions.append(button);
    }
    this.statisticsContent = document.createElement("div");
    this.statisticsContent.className = "measurement-front-panel-content";
    this.statisticsContent.setAttribute("aria-live", "polite");
    section.append(heading, form, actions, this.statisticsContent);
    this.updateStatisticsMaxCountState();
    return section;
  }

  statisticsSelect(labelKey, options) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    const label = document.createElement("span");
    label.textContent = translate(labelKey);
    const input = document.createElement("select");
    for (const value of options) input.append(new Option(choiceLabel(value), value));
    wrapper.append(label, input);
    return { wrapper, input };
  }

  statisticsFixedValue(labelKey, text) {
    const wrapper = document.createElement("div");
    wrapper.className = "field";
    const label = document.createElement("span");
    label.textContent = translate(labelKey);
    const value = document.createElement("strong");
    value.textContent = text;
    wrapper.append(label, value);
    return { wrapper, value };
  }

  statisticsCheckbox(labelKey) {
    const wrapper = document.createElement("label");
    wrapper.className = "field measurement-statistics-checkbox";
    const input = document.createElement("input");
    input.type = "checkbox";
    const label = document.createElement("span");
    label.textContent = translate(labelKey);
    wrapper.append(input, label);
    return { wrapper, input };
  }

  updateStatisticsMaxCountState() {
    if (!this.controls.statisticsMaxCountMode) return;
    const numeric = this.controls.statisticsMaxCountMode.input.value === "numeric";
    this.controls.statisticsMaxCount.disabled = this.hooks.isExecutionBusy() || !numeric;
  }

  statisticsParameters() {
    const maxCountMode = this.controls.statisticsMaxCountMode.input.value;
    const parameters = {
      action: "set",
      mode: "all",
      display_enabled: this.controls.statisticsDisplay.input.checked,
      max_count_mode: maxCountMode,
      relative_stddev_enabled: this.controls.statisticsRsd.input.checked,
    };
    if (maxCountMode === "numeric") {
      if (!this.controls.statisticsMaxCount.checkValidity?.()) {
        this.controls.statisticsMaxCount.reportValidity?.();
        return null;
      }
      parameters.max_count = Number(this.controls.statisticsMaxCount.value);
    }
    return parameters;
  }

  async applyStatistics() {
    if (this.statisticsState.kind === "unread") return;
    const parameters = this.statisticsParameters();
    if (!parameters) return;
    await this.executeStatistics(parameters);
  }

  async refreshStatistics() {
    await this.executeStatistics({ action: "query" });
  }

  async runStatisticsAction(action) {
    await this.executeStatistics({ action });
  }

  async executeStatistics(parameters) {
    if (!this.hooks.isCommandAvailable("measurement-statistics")) return;
    const requestedContext = this.contextKey;
    const job = await this.hooks.executeCommand("measurement-statistics", parameters);
    if (requestedContext !== this.contextKey) return;
    if (job?.status !== "completed") {
      this.statisticsReadError = "measurement.statistics.readFailed";
    } else {
      const payload = statisticsPayload(job);
      const rows = payload?.results?.statistics_items || [];
      this.statisticsState = {
        kind: payload?.settings?.mode && payload.settings.mode !== "all"
          ? "mode-required"
          : (rows.length ? "results" : "empty"),
        payload,
      };
      this.statisticsReadError = null;
      this.applyStatisticsReadback(payload?.settings);
    }
    this.renderStatisticsReadback();
    this.applyBusyState();
  }

  applyStatisticsReadback(settings) {
    if (!settings || !this.controls.statisticsDisplay) return;
    this.controls.statisticsDisplay.input.checked = Boolean(settings.display_enabled);
    this.controls.statisticsMaxCountMode.input.value = settings.max_count == null
      ? "infinite" : "numeric";
    if (settings.max_count != null) {
      this.controls.statisticsMaxCount.value = String(settings.max_count);
    }
    this.controls.statisticsRsd.input.checked = Boolean(settings.relative_stddev_enabled);
    this.updateStatisticsMaxCountState();
  }

  renderStatisticsReadback() {
    if (!this.statisticsContent) return;
    this.statisticsContent.replaceChildren();
    if (this.statisticsReadError) {
      const error = document.createElement("p");
      error.className = "measurement-front-panel-error";
      error.textContent = translate(this.statisticsReadError);
      this.statisticsContent.append(error);
      if (this.statisticsState.kind !== "results") return;
    }
    if (this.statisticsState.kind !== "results") {
      const note = document.createElement("p");
      note.className = "muted";
      note.textContent = translate(
        this.statisticsState.kind === "empty"
          ? "measurement.statistics.empty"
          : this.statisticsState.kind === "mode-required"
            ? "measurement.statistics.allRequired"
          : "measurement.statistics.unread",
      );
      this.statisticsContent.append(note);
      return;
    }
    this.statisticsContent.append(this.resultTable(
      this.statisticsState.payload.results.statistics_items,
      [
        ["label", "measurement"],
        ["current", "current"],
        ["minimum", "minimum"],
        ["maximum", "maximum"],
        ["mean", "mean"],
        ["stddev", "stddev"],
        ["count", "count"],
      ],
    ));
  }

  async refreshFrontPanel() {
    if (!this.hooks.isCommandAvailable("measure-results")) return;
    const requestedContext = this.contextKey;
    const job = await this.hooks.executeCommand("measure-results", {});
    if (requestedContext !== this.contextKey) return;
    if (job?.status !== "completed") {
      this.frontPanelReadError = "measurement.frontPanel.readFailed";
    } else {
      const payload = measurementPayload(job);
      const hasRows = Boolean(payload?.items?.length || payload?.statistics_items?.length);
      this.frontPanelState = { kind: hasRows ? "results" : "empty", payload };
      this.frontPanelReadError = null;
    }
    this.renderFrontPanelReadback();
  }

  async addFrontPanelMeasurement() {
    if (!this.hooks.isCommandAvailable("measure-install")) return;
    const requestedContext = this.contextKey;
    const job = await this.hooks.executeCommand(
      "measure-install", this.installForm.values(),
    );
    if (requestedContext !== this.contextKey || job?.status !== "completed") return;
    if (this.hooks.isCommandAvailable("measure-results")) {
      await this.refreshFrontPanel();
    }
  }

  async showFrontPanel(enabled = true) {
    if (!this.hooks.isCommandAvailable("measure-show")) return;
    await this.hooks.executeCommand("measure-show", { action: "set", enabled });
  }

  async clearFrontPanel() {
    if (!this.hooks.isCommandAvailable("measure-clear")) return;
    const requestedContext = this.contextKey;
    const job = await this.hooks.executeCommand("measure-clear", {});
    if (requestedContext !== this.contextKey || job?.status !== "completed") return;
    this.frontPanelState = { kind: "cleared", payload: null };
    this.frontPanelReadError = null;
    this.renderFrontPanelReadback();
  }

  async openMeasurementMenu() {
    if (!this.hooks.isCommandAvailable("measure-menu")) return;
    await this.hooks.executeCommand("measure-menu", {});
  }

  renderFrontPanelReadback() {
    if (!this.frontPanelContent) return;
    this.frontPanelContent.replaceChildren();
    if (this.frontPanelReadError) {
      const error = document.createElement("p");
      error.className = "measurement-front-panel-error";
      error.textContent = translate(
        this.frontPanelState.kind === "results"
          ? "measurement.frontPanel.readFailedStale"
          : this.frontPanelState.kind === "empty"
            ? "measurement.frontPanel.readFailedEmpty"
            : this.frontPanelState.kind === "cleared"
              ? "measurement.frontPanel.readFailedCleared"
              : this.frontPanelReadError,
      );
      this.frontPanelContent.append(error);
      if (this.frontPanelState.kind !== "results") return;
    }
    if (this.frontPanelState.kind !== "results") {
      const note = document.createElement("p");
      note.className = "muted";
      const key = this.frontPanelState.kind === "cleared"
        ? "measurement.frontPanel.cleared"
        : this.frontPanelState.kind === "empty"
          ? "measurement.frontPanel.empty"
          : "measurement.frontPanel.unread";
      note.textContent = translate(key);
      this.frontPanelContent.append(note);
      return;
    }
    const payload = this.frontPanelState.payload;
    if (payload.statistics_items?.length) {
      this.frontPanelContent.append(this.resultTable(payload.statistics_items, [
        ["label", "measurement"],
        ["current", "current"],
        ["minimum", "minimum"],
        ["maximum", "maximum"],
        ["mean", "mean"],
        ["stddev", "stddev"],
        ["count", "count"],
      ]));
      return;
    }
    this.frontPanelContent.append(this.resultTable(payload.items || [], [
      ["label", "measurement"],
      ["value", "value"],
    ]));
  }

  resultTable(rows, columns) {
    const table = document.createElement("table");
    table.className = "measurement-results-table";
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    for (const [_field, label] of columns) {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = translate(`measurement.results.${label}`);
      headRow.append(cell);
    }
    head.append(headRow);
    const body = document.createElement("tbody");
    for (const row of rows) {
      const tr = document.createElement("tr");
      for (const [field] of columns) {
        const cell = document.createElement("td");
        const value = row?.[field];
        cell.textContent = value === undefined || value === null ? "—" : String(value);
        tr.append(cell);
      }
      body.append(tr);
    }
    table.append(head, body);
    return table;
  }

  applyBusyState() {
    const busy = this.hooks.isExecutionBusy();
    this.measureForm?.setDisabled(busy);
    this.windowForm?.setDisabled(busy);
    for (const inputs of Object.values(this.sweepControls)) {
      for (const input of inputs) input.disabled = busy;
    }
    for (const row of this.sweepPairRows) {
      row.source.disabled = busy;
      row.reference.disabled = busy;
      row.remove.disabled = busy;
    }
    this.updateSweepAddPairState();
    if (this.controls.windowRefresh) {
      this.controls.windowRefresh.disabled = busy
        || !this.hooks.isCommandAvailable("measure-window");
    }
    for (const [name, command] of [
      ["frontPanelRefresh", "measure-results"],
      ["frontPanelInstall", "measure-install"],
      ["frontPanelShow", "measure-show"],
      ["frontPanelHide", "measure-show"],
      ["frontPanelClear", "measure-clear"],
      ["frontPanelMenu", "measure-menu"],
      ["statisticsApply", "measurement-statistics"],
      ["statisticsRefresh", "measurement-statistics"],
      ["statisticsReset", "measurement-statistics"],
    ]) {
      if (this.controls[name]) {
        this.controls[name].disabled = busy
          || !this.hooks.isCommandAvailable(command)
          || (name === "statisticsApply" && this.statisticsState.kind === "unread");
      }
    }
    this.installForm?.setDisabled(
      busy || !this.hooks.isCommandAvailable("measure-install"),
    );
    for (const control of [
      this.controls.statisticsDisplay?.input,
      this.controls.statisticsMaxCountMode?.input,
      this.controls.statisticsRsd?.input,
    ]) {
      if (control) control.disabled = busy;
    }
    this.updateStatisticsMaxCountState();
  }
}
