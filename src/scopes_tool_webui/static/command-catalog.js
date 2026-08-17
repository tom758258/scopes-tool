import { translate } from "/static/i18n.js";

export class CommandCatalog {
  constructor(commands, categoryElement, commandElement) {
    this.commands = commands;
    this.categoryElement = categoryElement;
    this.commandElement = commandElement;
    this.activeMode = "live";
    this.categoryElement.addEventListener("change", () => this.renderCommands());
  }

  categories() {
    return [...new Set(this.commands.map((command) => command.category))];
  }

  renderCategories() {
    const current = this.categoryElement.value;
    this.categoryElement.replaceChildren();
    this.categories().forEach((category) => {
      this.categoryElement.append(new Option(translate(`category.${category}`), category));
    });
    if (this.categories().includes(current)) this.categoryElement.value = current;
    this.renderCommands();
  }

  renderCommands() {
    const category = this.categoryElement.value;
    const current = this.commandElement.value;
    const available = this.commands.filter(
      (command) => command.category === category && command.modes.includes(this.activeMode),
    );
    this.commandElement.replaceChildren();
    available.forEach((command) => {
      this.commandElement.append(new Option(translate(`command.${command.id}`), command.id));
    });
    if (available.some((command) => command.id === current)) {
      this.commandElement.value = current;
    }
  }

  updateMode(mode) {
    this.activeMode = mode;
    this.renderCommands();
  }

  optionsFor(field) {
    return field.mode_options?.[this.activeMode] || field.options || [];
  }

  selected() {
    return this.commands.find((command) => command.id === this.commandElement.value) || null;
  }
}
