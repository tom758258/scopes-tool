import { hasTranslation, translate } from "/static/i18n.js";
import {
  commandSupported,
  commandSupportReason,
  fieldsForModel,
} from "/static/command-support.js";

export class CommandCatalog {
  constructor(commands, elements, onSelectionChange = () => {}) {
    this.commands = commands;
    this.elements = elements;
    this.onSelectionChange = onSelectionChange;
    this.activeMode = "live";
    this.activeCategory = "";
    this.selectedId = "";
    this.filterText = "";
    this.activeModelId = null;
    this.activeModelLabel = "";
    this.collapsedGroups = new Set();

    this.elements.filter.addEventListener("input", () => {
      this.filterText = this.elements.filter.value.trim().toLowerCase();
      this.renderCommands();
    });
    this.elements.categories.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-category]");
      if (!button) return;
      this.activeCategory = button.dataset.category;
      this.renderCategories();
    });
    this.elements.list.addEventListener("click", (event) => {
      const toggle = event.target.closest("button[data-command-group]");
      if (toggle) {
        this.toggleGroup(toggle.dataset.commandGroup);
        return;
      }
      const button = event.target.closest("button[data-command]");
      if (!button) return;
      this.select(button.dataset.command);
    });
  }

  availableCommands() {
    return this.commands.filter((command) => command.modes.includes(this.activeMode));
  }

  categories() {
    return [...new Set(this.availableCommands().map((command) => command.category))];
  }

  categoryLabel(category) {
    const key = `category.${category}`;
    return hasTranslation(key) ? translate(key) : category;
  }

  groupLabel(group) {
    const key = `group.${group}`;
    return hasTranslation(key) ? translate(key) : group;
  }

  commandLabel(command) {
    const key = `command.${command.id}`;
    return hasTranslation(key) ? translate(key) : command.label || command.id;
  }

  description(command) {
    const key = `description.${command?.id}`;
    if (command && hasTranslation(key)) return translate(key);
    const actionKey = `description.action.${command?.presentation?.action}`;
    if (command && hasTranslation(actionKey)) return translate(actionKey);
    return command?.description || command?.label || command?.id || "";
  }

  render() {
    this.renderCategories();
  }

  renderCategories(notify = true) {
    const categories = this.categories();
    if (!categories.includes(this.activeCategory)) this.activeCategory = categories[0] || "";
    this.elements.categories.replaceChildren();
    categories.forEach((category) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "category-button";
      button.dataset.category = category;
      button.textContent = this.categoryLabel(category);
      button.setAttribute("aria-pressed", String(category === this.activeCategory));
      if (category === this.activeCategory) button.classList.add("active");
      this.elements.categories.append(button);
    });
    this.renderCommands(notify);
  }

  renderCommands(notify = true) {
    const previous = this.selectedId;
    const query = this.filterText;
    const available = this.availableCommands().filter((command) => command.category === this.activeCategory);
    const filtered = available.filter((command) => {
      if (!query) return true;
      const text = `${this.commandLabel(command)} ${command.id} ${command.label || ""}`.toLowerCase();
      return text.includes(query);
    });
    if (!filtered.some((command) => command.id === this.selectedId)) {
      this.selectedId = filtered[0]?.id || "";
    }

    this.elements.list.replaceChildren();
    if (!filtered.length) {
      const empty = document.createElement("p");
      empty.className = "muted command-list-empty";
      empty.textContent = translate("commands.noMatches");
      this.elements.list.append(empty);
    } else {
      const sections = new Map();
      filtered.forEach((command) => {
        if (!command.group) {
          this.elements.list.append(this.renderCommandButton(command));
          return;
        }
        let section = sections.get(command.group);
        if (!section) {
          section = this.renderGroup(command.group);
          sections.set(command.group, section);
          this.elements.list.append(section.root);
        }
        section.items.append(this.renderCommandButton(command));
      });
    }

    if (notify && previous !== this.selectedId) this.onSelectionChange(this.selected());
  }

  renderGroup(group) {
    const expanded = Boolean(this.filterText) || !this.collapsedGroups.has(this.groupStateKey(this.activeCategory, group));
    const root = document.createElement("div");
    root.className = "command-group";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "command-group-toggle";
    toggle.dataset.commandGroup = group;
    toggle.setAttribute("aria-expanded", String(expanded));
    const caret = document.createElement("span");
    caret.setAttribute("aria-hidden", "true");
    caret.textContent = expanded ? "▾" : "▸";
    const label = document.createElement("span");
    label.textContent = this.groupLabel(group);
    toggle.append(caret, label);
    const items = document.createElement("div");
    items.className = "command-group-items";
    items.hidden = !expanded;
    root.append(toggle, items);
    return { root, items };
  }

  renderCommandButton(command) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "command-button";
    button.dataset.command = command.id;
    const label = document.createElement("span");
    label.textContent = this.commandLabel(command);
    button.append(label);
    const reason = this.supportReason(command);
    if (reason) {
      const status = document.createElement("small");
      status.textContent = reason;
      button.append(status);
      button.disabled = true;
      button.title = reason;
    }
    button.setAttribute("aria-pressed", String(command.id === this.selectedId));
    if (command.id === this.selectedId) button.classList.add("active");
    return button;
  }

  groupStateKey(category, group) {
    return `${category}|${group}`;
  }

  toggleGroup(group) {
    if (this.filterText) return;
    const key = this.groupStateKey(this.activeCategory, group);
    if (this.collapsedGroups.has(key)) this.collapsedGroups.delete(key);
    else this.collapsedGroups.add(key);
    this.renderCommands(false);
  }

  select(commandId) {
    if (!this.availableCommands().some((command) => command.id === commandId)) return;
    const command = this.commands.find((item) => item.id === commandId);
    const previous = this.selectedId;
    if (command?.category !== this.activeCategory) this.activeCategory = command.category;
    if (command?.group && !this.filterText) {
      this.collapsedGroups.delete(this.groupStateKey(this.activeCategory, command.group));
    }
    this.selectedId = commandId;
    this.renderCategories(false);
    if (previous !== this.selectedId) this.onSelectionChange(this.selected());
  }

  updateMode(mode) {
    this.activeMode = mode;
    this.renderCategories();
  }

  updateModel(modelId, modelLabel = "") {
    this.activeModelId = modelId || null;
    this.activeModelLabel = modelLabel || modelId || "";
    this.renderCategories(false);
  }

  supported(command) {
    return !this.activeModelId || commandSupported(command, this.activeModelId);
  }

  supportReason(command) {
    return this.activeModelId
      ? commandSupportReason(command, this.activeModelId, this.activeModelLabel)
      : "";
  }

  fieldsFor(command) {
    return fieldsForModel(command, this.activeModelId);
  }

  optionsFor(field) {
    return field.mode_options?.[this.activeMode] || field.options || [];
  }

  selected() {
    return this.commands.find((command) => command.id === this.selectedId) || null;
  }
}
