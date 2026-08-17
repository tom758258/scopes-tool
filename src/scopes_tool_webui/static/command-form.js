import { hasTranslation, translate } from "/static/i18n.js";

function translateEnum(value) {
  const key = `enum.${String(value)}`;
  return hasTranslation(key) ? translate(key) : String(value);
}

export class CommandForm {
  constructor(container, catalog) {
    this.container = container;
    this.catalog = catalog;
  }

  render(command) {
    this.container.replaceChildren();
    if (!command) {
      const empty = document.createElement("p");
      empty.className = "muted compact-note";
      empty.textContent = translate("status.noCommands");
      this.container.append(empty);
      return;
    }
    if (!command.fields.length) {
      const empty = document.createElement("p");
      empty.className = "muted compact-note";
      empty.textContent = translate("form.noParameters");
      this.container.append(empty);
      return;
    }
    command.fields.forEach((field) => this.container.append(this.field(field)));
    this.container.querySelectorAll("[data-field]").forEach((input) => {
      input.addEventListener("change", () => this.refreshVisibility());
    });
    this.refreshVisibility();
  }

  values() {
    const values = {};
    this.container.querySelectorAll("[data-field]").forEach((element) => {
      if (element.closest("[data-visible-if-hidden=\"true\"]")) return;
      if (!element.value && element.type !== "checkbox") return;
      const name = element.dataset.field;
      if (element.type === "checkbox") values[name] = element.checked;
      else if (element.dataset.type === "integer") values[name] = Number.parseInt(element.value, 10);
      else if (element.dataset.type === "number") values[name] = Number.parseFloat(element.value);
      else if (element.dataset.type === "boolean") values[name] = element.value === "true";
      else values[name] = element.value;
    });
    return values;
  }

  field(field) {
    const wrapper = document.createElement("label");
    wrapper.className = "field";
    if (field.visible_if) wrapper.dataset.visibleIf = JSON.stringify(field.visible_if);
    const label = document.createElement("span");
    label.textContent = translate(`field.${field.name}`);
    wrapper.append(label);
    let input;
    if (field.type === "enum") {
      input = document.createElement("select");
      if (field.default === undefined) input.append(new Option(translate("form.emptyOption"), ""));
      this.catalog.optionsFor(field).forEach((option) => {
        input.append(new Option(translateEnum(option), String(option)));
      });
    } else if (field.type === "boolean") {
      input = document.createElement("select");
      input.append(new Option(translate("form.emptyOption"), ""));
      input.append(
        new Option(translate("enum.true"), "true"),
        new Option(translate("enum.false"), "false"),
      );
    } else {
      input = document.createElement("input");
      input.type = field.type === "integer" ? "number" : "text";
      if (field.type === "integer") input.step = "1";
      if (field.type === "number") input.inputMode = "decimal";
      if (field.minimum !== undefined) input.min = field.minimum;
      if (field.maximum !== undefined) input.max = field.maximum;
    }
    input.dataset.field = field.name;
    input.dataset.type = field.type;
    input.required = false;
    if (field.default !== undefined) input.value = String(field.default);
    wrapper.append(input);
    return wrapper;
  }

  refreshVisibility() {
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
  }
}
