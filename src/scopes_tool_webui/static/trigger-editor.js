import { hasTranslation, translate } from "/static/i18n.js";
import { CommandForm } from "/static/command-form.js";
import { formatEngineering } from "/static/live-data.js";

const DIV_STEPS = [-4, -3, -2, -1, 0, 1, 2, 3, 4];

// OR trigger per-channel edge options; the select value is the SCPI pattern
// character itself, so encode/decode is a join/split around the channel order.
const OR_EDGE_OPTIONS = [
  { value: "R", labelKey: "enum.or-edge.rising" },
  { value: "F", labelKey: "enum.or-edge.falling" },
  { value: "E", labelKey: "enum.or-edge.either" },
  { value: "X", labelKey: "enum.or-edge.ignore" },
];

// Pattern trigger per-channel level options; same mechanics, digits only.
const PATTERN_LEVEL_OPTIONS = [
  { value: "1", labelKey: "enum.pattern-level.high" },
  { value: "0", labelKey: "enum.pattern-level.low" },
  { value: "X", labelKey: "enum.pattern-level.ignore" },
];

function divLabel(div) {
  return div > 0 ? `+${div}` : String(div);
}

function cleanFloatText(value) {
  return String(Number(value.toPrecision(12)));
}

export class TriggerEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.epoch = 0;
    this.stateKey = null;
    this.renderedKey = null;
    this.entry = null;
    this.pendingRefresh = false;
    this.pendingPresentation = false;
    this.buildDom();
  }

  buildDom() {
    this.refreshButton?.remove?.();
    this.entry?.button.remove?.();
    this.entry = null;
    this.container.replaceChildren();
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary trigger-editor-refresh";
    this.refreshButton.textContent = translate("trigger.editor.read");
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

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "trigger" ? selected : null;
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
    this.stateKey = key;
    if (this.renderedKey !== key) this.rebuildSections(key);
    this.applyBusyState();
    if (!read || !this.hooks.isAvailable()) return;
    this.setBusy(true);
    try {
      await this.readSelected();
    } finally {
      this.setBusy(false);
    }
  }

  clearSections() {
    this.renderedKey = null;
    this.entry?.button.remove?.();
    this.entry = null;
    this.sectionsHost.replaceChildren();
    this.refreshButton.disabled = true;
  }

  rebuildSections(key) {
    this.epoch += 1;
    const epoch = this.epoch;
    this.renderedKey = key;
    this.entry?.button.remove?.();
    this.entry = null;
    this.sectionsHost.replaceChildren();
    const command = this.selectedDefinition();
    if (!command || !this.catalog.supported(command)) return;
    this.entry = this.buildSection(command, epoch);
  }

  buildSection(command, epoch) {
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
    // Informational read commands reuse the header Read action; a second
    // inline Read button would duplicate it. The button is recreated on
    // every rebuild, so hidden state always follows the selection.
    actionButton.hidden = kind === "command" && action === "read";
    section.append(formContainer);
    if (this.hooks.headerActions) {
      this.hooks.headerActions.append(actionButton);
    } else {
      section.append(actionButton);
    }
    const fields = this.catalog.fieldsFor?.(command) ?? command.fields ?? [];
    section.hidden = fields.length === 0;
    formContainer.hidden = fields.length === 0;
    this.sectionsHost.append(section);
    const form = new CommandForm(formContainer, this.catalog);
    const entry = { id: command.id, kind, action, form: null, button: actionButton, epoch, div: null, channelPattern: null };
    const divCapable = this.divQualifies(command);
    if (divCapable) {
      const onDivField = (field) => this.handleDivField(entry, field);
      form.render(command, { onDirty: onDivField, onQueryFieldChange: onDivField });
    } else {
      form.render(command, {});
    }
    entry.form = form;
    if (divCapable) this.buildDivSection(section, entry);
    const patternChannels = command.id === "trigger-or" || command.id === "trigger-pattern"
      ? this.analogChannels()
      : [];
    if (patternChannels.length > 0) {
      entry.channelPattern = command.id === "trigger-or"
        ? this.buildOrSection(section, entry, patternChannels)
        : this.buildPatternSection(section, entry, patternChannels);
    }
    actionButton.addEventListener("click", () => {
      void this.submit();
    });
    return entry;
  }

  // Explicit, documented channel source shared by the OR and pattern channel
  // editors: the model-projected analog channel options of the core
  // channel-scale command. Returns [] when unavailable so the caller falls
  // back to the generic pattern field.
  analogChannels() {
    const definition = this.catalog.commands.find((command) => command.id === "channel-scale") || null;
    if (!definition) return [];
    const fields = this.catalog.fieldsFor?.(definition) ?? definition.fields ?? [];
    const field = fields.find((entry) => entry?.name === "channel");
    const options = field ? (this.catalog.optionsFor?.(field) ?? field.options ?? []) : [];
    const channels = [...new Set(
      [...options].map(Number).filter((value) => Number.isInteger(value) && value > 0),
    )].sort((a, b) => a - b);
    return channels;
  }

  channelLabel(channel) {
    const key = `enum.channel${channel}`;
    return hasTranslation(key) ? translate(key) : `CH${channel}`;
  }

  buildOrSection(section, entry, channels) {
    // The free-text pattern field stays out of the way: detach its wrapper so
    // generic visibility handling cannot resurface it, and drive the pattern
    // purely from the per-channel button groups below.
    const patternInput = entry.form.container?.querySelector?.('[data-field="pattern"]');
    patternInput?.closest?.("label")?.remove?.();
    const box = document.createElement("div");
    box.className = "trigger-or-channels";
    const groups = this.buildChannelPatternGroups(box, channels, OR_EDGE_OPTIONS);
    const help = document.createElement("small");
    help.className = "field-help";
    help.textContent = translate("help.trigger-or.pattern");
    box.append(help);
    section.append(box);
    return { groups, charset: "RFEX" };
  }

  buildPatternSection(section, entry, channels) {
    // Same detach mechanics as the OR section; the pattern vocabulary is
    // digits only (1/0/X), validated against the channel count on apply.
    const patternInput = entry.form.container?.querySelector?.('[data-field="pattern"]');
    patternInput?.closest?.("label")?.remove?.();
    const box = document.createElement("div");
    box.className = "trigger-pattern-channels";
    const groups = this.buildChannelPatternGroups(box, channels, PATTERN_LEVEL_OPTIONS);
    const help = document.createElement("small");
    help.className = "field-help";
    help.textContent = translate("help.trigger-pattern.pattern");
    box.append(help);
    const note = document.createElement("output");
    note.className = "muted compact-note";
    note.hidden = true;
    box.append(note);
    section.append(box);
    return { groups, charset: "01X", note };
  }

  // One mutually-exclusive button group per channel. Buttons share the
  // scale/range segmented look (secondary + selected + aria-pressed); only
  // the row layout is trigger-specific.
  buildChannelPatternGroups(box, channels, options) {
    const groups = [];
    for (const channel of channels) {
      const label = this.channelLabel(channel);
      const row = document.createElement("div");
      row.className = "trigger-channel-row";
      const name = document.createElement("span");
      name.className = "field-label";
      name.textContent = label;
      const group = document.createElement("div");
      group.className = "trigger-editor-segmented trigger-channel-options";
      group.setAttribute("role", "group");
      group.setAttribute("aria-label", label);
      const entry = { channel, buttons: [], value: "" };
      for (const option of options) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "secondary";
        button.dataset.channel = String(channel);
        button.dataset.value = option.value;
        button.textContent = translate(option.labelKey);
        button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", () => {
          this.setChannelPatternGroupValue(entry, option.value);
        });
        group.append(button);
        entry.buttons.push(button);
      }
      row.append(name, group);
      box.append(row);
      groups.push(entry);
    }
    return groups;
  }

  // Single place that keeps group.value, .selected, and aria-pressed in
  // sync; click, reset, and readback all go through it so an empty value
  // never leaves a stale highlight behind.
  setChannelPatternGroupValue(group, value) {
    group.value = value;
    for (const button of group.buttons) {
      const selected = button.dataset.value === value;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    }
  }

  // Raw Keysight strings run MSB-first (CH4..CH1 on 4-channel models), while
  // the groups stay in ascending channel order, so encode reverses. Any
  // unselected channel blocks the encode with null instead of guessing X.
  channelPatternValue(entry) {
    const values = (entry?.channelPattern?.groups || []).map((group) => group.value);
    if (values.some((value) => value === "")) return null;
    return values.reverse().join("");
  }

  syncChannelPatternGroups(entry, job) {
    const patternEntry = entry?.channelPattern || null;
    const groups = patternEntry?.groups || [];
    if (patternEntry === null || groups.length === 0) return;
    const reset = () => {
      for (const group of groups) this.setChannelPatternGroupValue(group, "");
      if (patternEntry.note) patternEntry.note.hidden = true;
    };
    if (job?.status !== "completed") {
      reset();
      return;
    }
    const payload = job?.result?.result ?? job?.result;
    const raw = payload?.pattern ?? payload?.trigger?.pattern;
    const pattern = typeof raw === "string" ? raw.trim().toUpperCase() : "";
    if (pattern.length !== groups.length
      || [...pattern].some((char) => !patternEntry.charset.includes(char))) {
      reset();
      // A completed readback with channel-count length but an unrepresentable
      // vocabulary (e.g. XXXR) is only described, never claimed as valid.
      if (patternEntry.note && pattern.length === groups.length && pattern !== "") {
        patternEntry.note.textContent = translate("trigger.pattern.unsupportedNote");
        patternEntry.note.hidden = false;
      }
      return;
    }
    groups.forEach((group, index) => {
      this.setChannelPatternGroupValue(group, pattern[groups.length - 1 - index]);
    });
    if (patternEntry.note) patternEntry.note.hidden = true;
  }

  divQualifies(command) {
    if (command?.presentation?.kind !== "setting") return false;
    const fields = this.catalog.fieldsFor?.(command) ?? command.fields ?? [];
    return fields.some((field) => field?.name === "level" && field?.type === "number")
      && fields.some((field) => field?.name === "source_channel" && field?.type === "integer");
  }

  buildDivSection(section, entry) {
    const heading = document.createElement("strong");
    heading.className = "trigger-editor-heading";
    heading.textContent = translate("trigger.editor.divHeading");
    const hint = document.createElement("small");
    hint.className = "field-help";
    hint.textContent = translate("trigger.editor.divHint");
    const host = document.createElement("div");
    host.className = "div-slider-block";
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = String(DIV_STEPS[0]);
    slider.max = String(DIV_STEPS[DIV_STEPS.length - 1]);
    slider.step = "1";
    slider.value = "0";
    slider.disabled = true;
    slider.setAttribute("aria-label", translate("trigger.editor.divHeading"));
    slider.addEventListener("input", () => {
      this.selectDiv(entry, Number(slider.value));
    });
    host.append(slider);
    const ticks = document.createElement("div");
    ticks.className = "div-slider-ticks";
    ticks.style.gridTemplateColumns = `repeat(${DIV_STEPS.length}, minmax(0, 1fr))`;
    for (const div of DIV_STEPS) {
      const tick = document.createElement("span");
      tick.textContent = divLabel(div);
      ticks.append(tick);
    }
    const info = document.createElement("output");
    info.className = "muted compact-note";
    const selection = document.createElement("output");
    selection.className = "muted compact-note div-slider-selection";
    const status = document.createElement("output");
    status.className = "muted compact-note";
    section.append(heading, hint, host, ticks, info, selection, status);
    entry.div = {
      slider, info, selection, status,
      scale: null, channel: null, units: null, offset: null,
      selected: null, incomplete: false,
    };
    this.syncDivInfo(entry);
  }

  divLevelInput(entry) {
    return entry?.form?.container?.querySelector?.('[data-field="level"]') || null;
  }

  divSourceValue(entry) {
    const input = entry?.form?.container?.querySelector?.('[data-field="source_channel"]');
    const value = Number(input?.value);
    return Number.isInteger(value) && value > 0 ? value : null;
  }

  handleDivField(entry, field) {
    if (!entry?.div || entry !== this.entry || entry.epoch !== this.epoch) return;
    if (field === "source_channel") {
      // The level draft belongs to the previous source; drop it and require
      // a fresh read before Div quick-fill is available again.
      const input = this.divLevelInput(entry);
      if (input) {
        input.value = "";
        if (input.dataset) delete input.dataset.dirty;
      }
      entry.div.incomplete = false;
      this.clearDivState(entry);
    } else if (field === "level") {
      entry.div.selected = null;
      this.syncDivInfo(entry);
    }
  }

  clearDivState(entry) {
    if (!entry?.div) return;
    entry.div.scale = null;
    entry.div.channel = null;
    entry.div.units = null;
    entry.div.offset = null;
    entry.div.selected = null;
    this.syncDivInfo(entry);
  }

  syncDivInfo(entry) {
    const div = entry?.div;
    if (!div) return;
    div.slider.value = div.selected === null ? "0" : String(div.selected);
    if (div.scale === null || div.channel === null) {
      div.info.textContent = "";
    } else {
      div.info.textContent = translate("trigger.editor.divCurrent", {
        channel: div.channel,
        scale: formatEngineering(div.scale, "V", { perDivision: true }),
        offset: formatEngineering(div.offset, "V", { signed: true }),
      });
    }
    if (div.selected === null || div.scale === null) {
      div.selection.textContent = "";
    } else {
      div.selection.textContent = translate("trigger.editor.divSelection", {
        div: divLabel(div.selected),
        value: formatEngineering(Number(cleanFloatText(div.offset + div.selected * div.scale)), "V", { signed: true }),
      });
    }
    div.status.textContent = div.incomplete ? translate("trigger.editor.divReadIncomplete") : "";
    this.applyDivBusyState(entry);
  }

  applyDivBusyState(entry) {
    const div = entry?.div;
    if (!div) return;
    div.slider.disabled = this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()
      || div.scale === null || div.channel === null || div.channel !== this.divSourceValue(entry);
  }

  selectDiv(entry, div) {
    if (!entry?.div || entry !== this.entry || entry.epoch !== this.epoch) return;
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable?.()) return;
    const state = entry.div;
    if (state.scale === null || state.channel === null) return;
    if (state.channel !== this.divSourceValue(entry)) return;
    const input = this.divLevelInput(entry);
    if (!input || input.disabled) return;
    state.selected = div;
    input.value = cleanFloatText(state.offset + div * state.scale);
    if (input.dataset) input.dataset.dirty = "true";
    this.syncDivInfo(entry);
  }

  async refreshDivContext(entry) {
    const contextKey = this.hooks.contextKey();
    const source = this.divSourceValue(entry);
    if (source === null) {
      this.clearDivState(entry);
      return;
    }
    const job = await this.hooks.executeCommand("channel-summary", {}, { intent: "readback" });
    if (entry !== this.entry || entry.epoch !== this.epoch
      || this.hooks.contextKey() !== contextKey || this.divSourceValue(entry) !== source) {
      return;
    }
    if (job?.status !== "completed") {
      entry.div.incomplete = true;
      this.clearDivState(entry);
      return;
    }
    const channels = job?.result?.result?.channels ?? job?.result?.channels;
    const item = Array.isArray(channels)
      ? channels.find((candidate) => Number(candidate?.channel) === source)
      : undefined;
    const scale = item?.scale;
    const range = item?.range;
    const offset = item?.offset;
    const units = item?.units;
    const complete = typeof scale === "number" && Number.isFinite(scale) && scale > 0
      && typeof range === "number" && Number.isFinite(range) && range > 0
      && typeof offset === "number" && Number.isFinite(offset)
      && units === "volt";
    if (!complete) {
      entry.div.incomplete = true;
      this.clearDivState(entry);
      return;
    }
    entry.div.scale = scale;
    entry.div.channel = source;
    entry.div.units = units;
    entry.div.offset = offset;
    entry.div.selected = null;
    entry.div.incomplete = false;
    this.syncDivInfo(entry);
  }

  async readEntry(entry) {
    const parameters = entry.form.queryValues();
    if (parameters === null) return;
    const job = await this.hooks.executeCommand(
      entry.id,
      parameters,
      { intent: "readback" },
    );
    if (job?.status === "completed") entry.form.syncResult(job, true);
    if ((entry.id === "trigger-or" || entry.id === "trigger-pattern")
      && entry === this.entry && entry.epoch === this.epoch) {
      this.syncChannelPatternGroups(entry, job);
    }
    if (!entry.div || entry !== this.entry || entry.epoch !== this.epoch) return;
    if (job?.status !== "completed") {
      entry.div.incomplete = true;
      this.clearDivState(entry);
      return;
    }
    this.reconcileDivLevel(entry);
    await this.refreshDivContext(entry);
  }

  reconcileDivLevel(entry) {
    if (!entry?.div) return;
    const queryFields = entry.form?.presentation?.query_fields || [];
    if (queryFields.includes("source_channel")) return;
    // A dirty source with a non-query source field means an unapplied draft
    // source exists, so a generic readback level cannot be safely attributed
    // to it. Blank a non-dirty level; the draft source itself is kept.
    const source = entry.form.container?.querySelector?.(
      '[data-field="source_channel"]',
    );
    const level = this.divLevelInput(entry);
    if (
      source?.dataset?.dirty === "true"
      && level
      && level.dataset?.dirty !== "true"
    ) {
      level.value = "";
    }
  }

  async readSelected() {
    const entry = this.entry;
    if (!entry || entry.epoch !== this.epoch) return;
    if (entry.kind === "setting") {
      await this.readEntry(entry);
    } else {
      await this.hooks.executeCommand(entry.id, {}, {});
    }
  }

  async submit() {
    const entry = this.entry;
    if (!entry || this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return;
    const submissionKey = this.currentStateKey();
    const isSetting = entry.kind === "setting";
    let parameters = {};
    if (isSetting) {
      const values = entry.form.values();
      if (values === null) return;
      parameters = values;
      // The channel pattern field is driven by the per-channel button groups,
      // which are not form fields; encode them here so the generic flow stays
      // untouched. An unselected channel focuses its group and blocks the
      // submit before any busy state or I/O.
      if (entry.channelPattern) {
        const pattern = this.channelPatternValue(entry);
        if (pattern === null) {
          const missing = entry.channelPattern.groups.find((group) => group.value === "");
          missing?.buttons[0]?.focus?.();
          return;
        }
        parameters.pattern = pattern;
      }
    }
    this.setBusy(true);
    try {
      const job = await this.hooks.executeCommand(
        entry.id,
        parameters,
        isSetting ? { intent: "apply" } : {},
      );
      if (
        isSetting
        && job?.status === "completed"
        && entry.epoch === this.epoch
        && submissionKey === this.currentStateKey()
      ) {
        entry.form.clearDirty();
        entry.form.syncResult(job, false);
        if (entry.id === "trigger-or" || entry.id === "trigger-pattern") {
          this.syncChannelPatternGroups(entry, job);
        }
        if (entry.div) {
          entry.div.selected = null;
          this.syncDivInfo(entry);
        }
      }
    } finally {
      this.setBusy(false);
    }
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
      for (const group of this.entry.channelPattern?.groups || []) {
        for (const button of group.buttons) button.disabled = disabled;
      }
      this.applyDivBusyState(this.entry);
    }
  }
}
