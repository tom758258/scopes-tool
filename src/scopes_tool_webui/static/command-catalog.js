import { translate } from "/static/i18n.js";

export class CommandCatalog {
  constructor(commands, categoryElement, commandElement) {
    this.commands = commands;
    this.categoryElement = categoryElement;
    this.commandElement = commandElement;
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

  renderCommands(mode) {
    const category = this.categoryElement.value;
    const current = this.commandElement.value;
    const available = this.commands.filter(
      (command) => command.category === category && (!mode || command.modes.includes(mode)),
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
    const selected = this.selected();
    this.renderCommands(mode);
    if (selected && selected.modes.includes(mode)) {
      this.commandElement.value = selected.id;
    }
  }

  selected() {
    return this.commands.find((command) => command.id === this.commandElement.value) || null;
  }
}
