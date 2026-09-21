import { hasTranslation, translate } from "/static/i18n.js";
import { applyNumericFieldConstraints } from "/static/numeric-input.js";

const DECIMAL_NUMBER_PATTERN = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
const FFT_FREQUENCY_FIELDS = new Set(["center_hz", "span_hz", "start_hz", "stop_hz"]);
const TIMEBASE_SCALE_PRESETS = [
  { label: "100 ns/div", value: "0.0000001" },
  { label: "1 µs/div", value: "0.000001" },
  { label: "10 µs/div", value: "0.00001" },
  { label: "100 µs/div", value: "0.0001" },
  { label: "1 ms/div", value: "0.001" },
  { label: "10 ms/div", value: "0.01" },
  { label: "20 ms/div", value: "0.02" },
  { label: "100 ms/div", value: "0.1" },
  { label: "200 ms/div", value: "0.2" },
  { label: "1 s/div", value: "1" },
];

function translateEnum(value, optionLabel = null) {
  const scopedKey = optionLabel ? `enum.${optionLabel}.${String(value)}` : null;
  if (scopedKey && hasTranslation(scopedKey)) return translate(scopedKey);
  const scopedTemplate = optionLabel ? `enum.${optionLabel}` : null;
  if (scopedTemplate && hasTranslation(scopedTemplate)) {
    return translate(scopedTemplate, { value });
  }
  const key = `enum.${String(value)}`;
  return hasTranslation(key) ? translate(key) : String(value);
}

function optionDisplayText(option, field) {
  if (field.option_label === "channel") {
    const channelKey = `enum.channel${option}`;
    return hasTranslation(channelKey) ? translate(channelKey) : String(option);
  }
  return translateEnum(option, field.option_label);
}

function selectOptionTexts(field, presentation, optionsFor) {
  const texts = [];
  const required = field.required === true || Boolean(field.required_if);
  const pushPlaceholder = () => {
    texts.push({
      value: "",
      text: translate(required ? "form.selectValue" : "form.leaveUnchanged"),
    });
  };
  if (field.type === "boolean" && field.default === undefined) {
    pushPlaceholder();
    if (field.option_label === "enabled" || field.name === "enabled") {
      texts.push({ value: "true", text: translate("enum.enable") });
      texts.push({ value: "false", text: translate("enum.disable") });
    } else {
      texts.push({ value: "true", text: translate("enum.true") });
      texts.push({ value: "false", text: translate("enum.false") });
    }
    return texts;
  }
  if (field.default === undefined && field.type !== "multi-enum") {
    pushPlaceholder();
  }
  const actionChoices = field.name === presentation?.action_field
    ? presentation?.action_choices
    : null;
  const options = actionChoices || (optionsFor ? optionsFor(field) : []);
  options.forEach((option) => {
    texts.push({ value: String(option), text: optionDisplayText(option, field) });
  });
  return texts;
}

export class CommandForm {
  constructor(container, catalog) {
    this.container = container;
    this.catalog = catalog;
    this.command = null;
    this.presentation = null;
    this.onDirty = () => {};
    this.onQueryFieldChange = () => {};
  }

  render(command, options = {}) {
    this.command = command;
    this.presentation = command?.presentation || null;
    this.onDirty = options.onDirty || (() => {});
    this.onQueryFieldChange = options.onQueryFieldChange || (() => {});
    this.container.replaceChildren();
    if (!command) {
      this.appendEmpty("status.noCommands");
      return;
    }

    const fields = this.catalog.fieldsFor ? this.catalog.fieldsFor(command) : command.fields;
    const visibleFields = fields.filter((field) => !this.isManagedActionField(field));
    if (!visibleFields.length) this.appendEmpty("form.noParameters");
    fields.filter((field) => !field.advanced).forEach(
      (field) => this.container.append(this.field(field)),
    );
    const advancedFields = fields.filter((field) => field.advanced);
    if (advancedFields.length) {
      const disclosure = document.createElement("details");
      disclosure.className = "command-form-advanced";
      const summary = document.createElement("summary");
      summary.textContent = translate("form.advanced");
      const fieldsHost = document.createElement("div");
      fieldsHost.className = "command-form-advanced-fields";
      advancedFields.forEach((field) => fieldsHost.append(this.field(field)));
      disclosure.append(summary, fieldsHost);
      this.container.append(disclosure);
    }
    if (options.draft) this.restoreDraft(options.draft);
    this.appendTimebaseScalePresets();
    this.appendChannelProbePresets();
    this.container.querySelectorAll("[data-field]").forEach((input) => {
      if (input.type === "hidden") return;
      const changed = () => {
        if (input.dataset.queryField === "true") {
          this.clearDirty(false);
          this.onQueryFieldChange(input.dataset.field);
        } else {
          input.dataset.dirty = "true";
          this.onDirty(input.dataset.field);
        }
        this.refreshVisibility();
      };
      input.addEventListener("input", changed);
      input.addEventListener("change", changed);
    });
    this.refreshVisibility();
  }

  appendEmpty(key) {
    const empty = document.createElement("p");
    empty.className = "muted compact-note";
    empty.textContent = translate(key);
    this.container.append(empty);
  }

  appendTimebaseScalePresets() {
    if (this.command?.id !== "timebase-scale") return;
    const input = this.container.querySelector('[data-field="seconds_per_division"]');
    if (!input) return;
    const presets = document.createElement("div");
    presets.className = "timebase-scale-presets";
    TIMEBASE_SCALE_PRESETS.forEach((preset) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = preset.label;
      button.addEventListener("click", () => {
        const target = this.container.querySelector('[data-field="seconds_per_division"]');
        if (!target || target.disabled) return;
        target.value = preset.value;
        target.dispatchEvent(new Event("input", { bubbles: true }));
      });
      presets.append(button);
    });
    this.container.append(presets);
  }

  appendChannelProbePresets() {
    if (this.command?.id !== "channel-probe") return;
    const input = this.container.querySelector('[data-field="ratio"]');
    if (!input) return;
    const presets = document.createElement("div");
    presets.className = "channel-probe-presets";
    [1, 10, 20, 100, 1000].forEach((ratio) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = `${ratio}:1`;
      button.addEventListener("click", () => {
        const target = this.container.querySelector('[data-field="ratio"]');
        if (!target || target.disabled) return;
        target.value = String(ratio);
        target.dispatchEvent(new Event("input", { bubbles: true }));
      });
      presets.append(button);
    });
    this.container.append(presets);
  }

  isSettingEditor() {
    if (this.presentation?.kind !== "setting") return false;
    if (this.presentation.action_choices?.length) return true;
    const action = this.command?.fields.find(
      (field) => field.name === this.presentation.action_field,
    );
    return this.catalog.optionsFor(action).includes(this.presentation.apply_value);
  }

  isManagedActionField(field) {
    return ["setting", "one-way"].includes(this.presentation?.kind)
      && !this.presentation?.action_choices?.length
      && field.name === this.presentation.action_field;
  }

  setDisabled(disabled) {
    this.container.querySelectorAll("[data-field]").forEach((input) => {
      if (input.type !== "hidden") {
        input.disabled = disabled || input.dataset.capabilityDisabled === "true";
      }
    });
    this.container.querySelectorAll(".timebase-scale-presets button").forEach((button) => {
      button.disabled = disabled;
    });
    this.container.querySelectorAll(".channel-probe-presets button").forEach((button) => {
      button.disabled = disabled;
    });
    this.container.querySelectorAll("[data-multi-for]").forEach((box) => {
      box.disabled = disabled;
    });
  }

  values() {
    const values = {};
    for (const element of this.container.querySelectorAll("[data-field]")) {
      if (element.dataset.capabilityDisabled === "true") continue;
      if (element.closest?.("[data-visible-if-hidden=\"true\"]")) continue;
      if (
        this.command?.id === "fft"
        && FFT_FREQUENCY_FIELDS.has(element.dataset.field)
        && element.dataset.dirty !== "true"
      ) {
        continue;
      }
      element.setCustomValidity?.("");
      const rawValue = typeof element.value === "string" ? element.value.trim() : element.value;
      if (element.validity?.badInput || (element.required && rawValue === "")) {
        element.reportValidity?.();
        return null;
      }
      if (rawValue === "" && element.type !== "checkbox") continue;
      const value = this.parseElement(element);
      if (value === null) return null;
      values[element.dataset.field] = element.type === "checkbox" ? element.checked : value;
      if (element.checkValidity && !element.checkValidity()) {
        element.reportValidity?.();
        return null;
      }
    }
    return values;
  }

  queryValues() {
    if (this.presentation?.kind !== "setting") return null;
    const values = {
      [this.presentation.action_field]: this.presentation.query_value,
    };
    for (const name of this.presentation.query_fields || []) {
      const element = this.container.querySelector(`[data-field="${name}"]`);
      if (!element || element.value === "") continue;
      if (element.validity?.badInput || (element.checkValidity && !element.checkValidity())) {
        return null;
      }
      const value = this.parseElement(element, false);
      if (value === null) return null;
      values[name] = value;
    }
    return values;
  }

  syncResult(job, preserveDirty = true) {
    const payload = job?.result?.result !== undefined ? job.result.result : job?.result;
    if (payload === null || payload === undefined) return;
    const fields = [...this.container.querySelectorAll("[data-field]")]
      .filter((input) => input.type !== "hidden");
    const writableCount = fields.filter((input) => input.dataset.queryField !== "true").length;
    fields.forEach((input) => {
      if (preserveDirty && input.dataset.dirty === "true") return;
      const onlyWritableField = input.dataset.queryField !== "true" && writableCount === 1;
      const readbackAlias = this.presentation?.readback_fields?.[input.dataset.field];
      const readbackField = readbackAlias === undefined
        ? input.dataset.field
        : resolveReadbackField(payload, readbackAlias);
      if (!readbackField) return;
      const value = findResultValue(payload, readbackField, onlyWritableField);
      if (value === undefined || value === null || typeof value === "object") return;
      if (input.type === "checkbox") {
        input.checked = Boolean(value);
      } else {
        input.value = input.dataset.type === "boolean" ? String(Boolean(value)) : String(value);
        if (input.multiple) this.syncMultiChoices(input);
      }
      delete input.dataset.dirty;
    });
    this.refreshVisibility();
  }

  clearDirty(includeQueryFields = true) {
    this.container.querySelectorAll("[data-field]").forEach((input) => {
      if (includeQueryFields || input.dataset.queryField !== "true") delete input.dataset.dirty;
    });
  }

  draft() {
    return [...this.container.querySelectorAll("[data-field]")].map((input) => ({
      name: input.dataset.field,
      value: input.type === "checkbox"
        ? input.checked
        : input.multiple
          ? [...input.selectedOptions].map((option) => option.value)
          : input.value,
      dirty: input.dataset.dirty === "true",
    }));
  }

  restoreDraft(draft) {
    draft.forEach((entry) => {
      const input = this.container.querySelector(`[data-field="${entry.name}"]`);
      if (!input) return;
      if (input.type === "checkbox") {
        input.checked = Boolean(entry.value);
      } else if (input.multiple) {
        const selected = new Set(Array.isArray(entry.value) ? entry.value.map(String) : []);
        [...input.options].forEach((option) => {
          option.selected = selected.has(option.value);
        });
        this.syncMultiChoices(input);
      } else {
        if (input.tagName === "SELECT" && !input.multiple) {
          const validValues = new Set([...input.options].map((o) => o.value));
          if (entry.value !== "" && !validValues.has(String(entry.value))) {
            return;
          }
        }
        input.value = entry.value;
      }
      if (entry.dirty) input.dataset.dirty = "true";
    });
  }

  syncMultiChoices(select) {
    const selected = new Set(
      [...select.options].filter((option) => option.selected).map((option) => option.value),
    );
    this.container.querySelectorAll("[data-multi-for]").forEach((box) => {
      if (box.dataset.multiFor !== select.dataset.field) return;
      box.checked = selected.has(box.value);
    });
  }

  isDirty() {
    return Boolean(this.container.querySelector('[data-dirty="true"]'));
  }

  field(field) {
    if (this.isManagedActionField(field)) {
      const input = document.createElement("input");
      input.type = "hidden";
      input.dataset.field = field.name;
      input.dataset.type = field.type;
      input.value = this.presentation.kind === "one-way" || this.isSettingEditor()
        ? this.presentation.apply_value
        : this.presentation.query_value;
      return input;
    }

    const isMultiEnum = field.type === "multi-enum";
    const wrapper = document.createElement(isMultiEnum ? "div" : "label");
    wrapper.className = isMultiEnum ? "field field-multi" : "field";
    if (field.visible_if) wrapper.dataset.visibleIf = JSON.stringify(field.visible_if);
    const label = document.createElement("span");
    const labelKey = field.label_key ? `field.${field.label_key}` : `field.${field.name}`;
    label.textContent = hasTranslation(labelKey) ? translate(labelKey) : translate(`field.${field.name}`);
    label.dataset.fieldLabel = field.name;
    wrapper.append(label);
    let input;
    if (["enum", "multi-enum"].includes(field.type)) {
      input = document.createElement("select");
      input.multiple = field.type === "multi-enum";
      const actionChoices = field.name === this.presentation?.action_field
        ? this.presentation.action_choices
        : null;
      if (!input.multiple && field.default === undefined) {
        const required = field.required === true || Boolean(field.required_if);
        input.append(new Option(translate(required ? "form.selectValue" : "form.leaveUnchanged"), ""));
      }
      const disabledOptions = new Set((field.disabled_options || []).map(String));
      const options = actionChoices || this.catalog.optionsFor(field);
      options.forEach((option) => {
        const label = optionDisplayText(option, field);
        const opt = new Option(label, String(option));
        if (disabledOptions.has(String(option))) opt.disabled = true;
        input.append(opt);
      });
      if (input.multiple) {
        input.size = Math.min(Math.max(options.length, 2), 6);
        input.className = "visually-hidden";
        input.tabIndex = -1;
        input.setAttribute("aria-hidden", "true");
        input.dataset.multiSource = "true";
      }
      if (actionChoices?.length) input.value = String(actionChoices[0]);
    } else if (["integer", "number"].includes(field.type)
        && this.catalog.optionsFor(field).length) {
      input = document.createElement("select");
      if (field.default === undefined) {
        const required = field.required === true || Boolean(field.required_if);
        input.append(new Option(translate(required ? "form.selectValue" : "form.leaveUnchanged"), ""));
      }
      const disabledOptions = new Set((field.disabled_options || []).map(String));
      const options = this.catalog.optionsFor(field);
      options.forEach((option) => {
        const label = optionDisplayText(option, field);
        const opt = new Option(label, String(option));
        if (disabledOptions.has(String(option))) opt.disabled = true;
        input.append(opt);
      });
    } else if (field.type === "boolean") {
      if (field.default !== undefined) {
        input = document.createElement("input");
        input.type = "checkbox";
        input.checked = Boolean(field.default);
        wrapper.classList.add("field-boolean");
      } else {
        input = document.createElement("select");
        const required = field.required === true || Boolean(field.required_if);
        input.append(new Option(translate(required ? "form.selectValue" : "form.leaveUnchanged"), ""));
        if (field.option_label === "enabled" || field.name === "enabled") {
          input.append(
            new Option(translate("enum.enable"), "true"),
            new Option(translate("enum.disable"), "false"),
          );
        } else {
          input.append(
            new Option(translate("enum.true"), "true"),
            new Option(translate("enum.false"), "false"),
          );
        }
      }
    } else {
      input = document.createElement("input");
      if (["integer", "number"].includes(field.type)) {
        applyNumericFieldConstraints(input, field);
      } else {
        input.type = "text";
      }
    }
    input.dataset.field = field.name;
    input.dataset.type = field.type;
    if (field.disabled === true) {
      input.disabled = true;
      input.dataset.capabilityDisabled = "true";
    }
    if (field.serialize) input.dataset.serialize = field.serialize;
    input.dataset.queryField = String(
      (this.presentation?.query_fields || []).includes(field.name),
    );
    if (field.required_if) input.dataset.requiredIf = JSON.stringify(field.required_if);
    input.dataset.required = String(field.required === true);
    input.required = field.required === true;
    const managedActionChoice = field.name === this.presentation?.action_field
      && this.presentation?.action_choices?.length;
    if (field.default !== undefined && !managedActionChoice) {
      if (input.multiple && Array.isArray(field.default)) {
        const defaults = new Set(field.default.map(String));
        [...input.options].forEach((option) => {
          option.selected = defaults.has(option.value);
        });
      } else {
        input.value = String(field.default);
      }
    }
    if (isMultiEnum) {
      const choices = document.createElement("div");
      choices.className = "multi-choice";
      [...input.options].forEach((option) => {
        const choice = document.createElement("label");
        choice.className = "multi-choice-option";
        const box = document.createElement("input");
        box.type = "checkbox";
        box.value = option.value;
        box.checked = option.selected;
        box.dataset.multiFor = field.name;
        const text = document.createElement("span");
        text.textContent = option.textContent;
        choice.append(box, text);
        box.addEventListener("change", () => {
          option.selected = box.checked;
          input.dispatchEvent(new Event("change"));
        });
        choices.append(choice);
      });
      wrapper.append(choices);
    }
    wrapper.append(input);
    if (field.help || field.help_key || field.help_by_value) {
      const help = document.createElement("small");
      help.className = "field-help";
      if (field.help_by_value) {
        help.dataset.helpByValue = JSON.stringify(field.help_by_value);
        help.dataset.helpFor = field.name;
        if (field.help_key) help.dataset.helpFallback = field.help_key;
      } else {
        const helpKey = field.help_key ? `help.${field.help_key}` : `help.${field.name}`;
        help.textContent = hasTranslation(helpKey) ? translate(helpKey) : field.help;
        help.dataset.fieldHelp = field.name;
      }
      wrapper.append(help);
    }
    return wrapper;
  }

  parseElement(element, report = true) {
    const rawValue = typeof element.value === "string" ? element.value.trim() : element.value;
    if (rawValue === "") return undefined;
    if (element.dataset.type === "multi-enum") {
      const values = [...element.selectedOptions].map((option) => option.value);
      return element.dataset.serialize === "csv" ? values.join(",") : values;
    }
    if (["integer", "number"].includes(element.dataset.type)) {
      const parsed = Number(rawValue);
      const valid = DECIMAL_NUMBER_PATTERN.test(rawValue) && Number.isFinite(parsed)
        && (element.dataset.type !== "integer" || Number.isInteger(parsed));
      if (!valid) {
        if (report) {
          element.setCustomValidity?.(translate(
            element.dataset.type === "integer" ? "form.invalidInteger" : "form.invalidNumber",
          ));
          element.reportValidity?.();
        }
        return null;
      }
      if (element.dataset.exclusiveMinimum !== undefined
          && parsed <= Number(element.dataset.exclusiveMinimum)) {
        if (report) {
          element.setCustomValidity?.(translate("form.greaterThan", {
            value: element.dataset.exclusiveMinimum,
          }));
          element.reportValidity?.();
        }
        return null;
      }
      return parsed;
    }
    if (element.dataset.type === "boolean") return element.value === "true";
    return element.value;
  }

  refreshVisibility() {
    this.container.querySelectorAll("[data-help-by-value]").forEach((help) => {
      let helpByValue;
      try {
        helpByValue = JSON.parse(help.dataset.helpByValue);
      } catch (_error) {
        helpByValue = {};
      }
      const input = this.container.querySelector(`[data-field="${help.dataset.helpFor}"]`);
      const helpName = input ? helpByValue[input.value] : undefined;
      const baseKey = help.dataset.helpFallback ? `help.${help.dataset.helpFallback}` : "";
      const specificKey = helpName ? `help.${helpName}` : "";
      help.textContent = [baseKey, specificKey]
        .filter((key) => key && hasTranslation(key))
        .map((key) => translate(key))
        .join("\n");
      help.hidden = !help.textContent;
    });
    this.container.querySelectorAll("[data-visible-if]").forEach((wrapper) => {
      let predicates;
      try {
        predicates = JSON.parse(wrapper.dataset.visibleIf);
      } catch (_error) {
        predicates = [];
      }
      const conditions = Array.isArray(predicates) ? predicates : [predicates];
      const visible = conditions.every((predicate) => {
        const controlling = this.container.querySelector(`[data-field="${predicate.field}"]`);
        if (!controlling) return false;
        const value = controlling.type === "checkbox" ? controlling.checked : controlling.value;
        if (Object.prototype.hasOwnProperty.call(predicate, "equals")) {
          return String(value) === String(predicate.equals);
        }
        if (Array.isArray(predicate.in)) {
          return predicate.in.map(String).includes(String(value));
        }
        return false;
      });
      wrapper.hidden = !visible;
      wrapper.dataset.visibleIfHidden = String(!visible);
    });
    this.container.querySelectorAll("[data-field]").forEach((input) => {
      const hidden = Boolean(input.closest?.("[data-visible-if-hidden=\"true\"]"));
      let conditionallyRequired = false;
      if (input.dataset.requiredIf) {
        try {
          const predicates = JSON.parse(input.dataset.requiredIf);
          const conditions = Array.isArray(predicates) ? predicates : [predicates];
          conditionallyRequired = conditions.every((predicate) => {
            const controlling = this.container.querySelector(`[data-field="${predicate.field}"]`);
            if (!controlling) return false;
            const value = controlling.type === "checkbox" ? controlling.checked : controlling.value;
            if (Object.prototype.hasOwnProperty.call(predicate, "equals")) {
              return String(value) === String(predicate.equals);
            }
            if (Array.isArray(predicate.in)) {
              return predicate.in.map(String).includes(String(value));
            }
            return false;
          });
        } catch (_error) {
          conditionallyRequired = false;
        }
      }
      input.required = !hidden && (input.dataset.required === "true" || conditionallyRequired);
    });
  }

  refreshLocale() {
    if (!this.command) return;
    const fields = this.catalog?.fieldsFor
      ? this.catalog.fieldsFor(this.command)
      : this.command.fields;
    const byName = new Map((fields || []).map((field) => [field.name, field]));
    this.container.querySelectorAll("[data-field-label]").forEach((label) => {
      const field = byName.get(label.dataset.fieldLabel);
      if (!field) return;
      const labelKey = field.label_key ? `field.${field.label_key}` : `field.${field.name}`;
      label.textContent = hasTranslation(labelKey)
        ? translate(labelKey)
        : translate(`field.${field.name}`);
    });
    this.container.querySelectorAll("[data-field-help]").forEach((help) => {
      const field = byName.get(help.dataset.fieldHelp);
      if (!field || field.help_by_value) return;
      const helpKey = field.help_key ? `help.${field.help_key}` : `help.${field.name}`;
      help.textContent = hasTranslation(helpKey) ? translate(helpKey) : field.help;
    });
    const optionsFor = this.catalog?.optionsFor
      ? (field) => this.catalog.optionsFor(field)
      : null;
    this.container.querySelectorAll("[data-field]").forEach((input) => {
      const field = byName.get(input.dataset.field);
      if (!field || input.tagName !== "SELECT") return;
      const expected = new Map(
        selectOptionTexts(field, this.presentation, optionsFor)
          .map((entry) => [entry.value, entry.text]),
      );
      [...input.options].forEach((option) => {
        if (expected.has(option.value)) option.textContent = expected.get(option.value);
      });
    });
    this.refreshVisibility();
  }
}

function resolveReadbackField(payload, alias) {
  if (!alias || typeof alias === "string") return alias;
  const selector = findResultValue(payload, alias.selector_field, false);
  return alias.fields?.[selector];
}

function findResultValue(result, fieldName, onlyWritableField, depth = 0) {
  if (result === null || result === undefined || depth > 4) return undefined;
  if (typeof result !== "object") return onlyWritableField ? result : undefined;
  if (Object.prototype.hasOwnProperty.call(result, fieldName)) {
    const direct = result[fieldName];
    if (
      direct !== null
      && typeof direct === "object"
      && Object.prototype.hasOwnProperty.call(direct, fieldName)
    ) {
      const nested = direct[fieldName];
      if (nested === null || typeof nested !== "object") return nested;
    }
    return direct;
  }
  if (fieldName === "enabled" && typeof result.state === "boolean") return result.state;
  const entries = Object.entries(result).filter(([name]) => name !== "raw");
  if (onlyWritableField && entries.length === 1 && typeof entries[0][1] !== "object") {
    return entries[0][1];
  }
  for (const [_name, value] of entries) {
    const found = findResultValue(value, fieldName, onlyWritableField, depth + 1);
    if (found !== undefined) return found;
  }
  return undefined;
}
