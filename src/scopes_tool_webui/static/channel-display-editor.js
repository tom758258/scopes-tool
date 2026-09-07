import { hasTranslation, translate } from "/static/i18n.js";

function channelLabel(channel) {
  const key = `enum.channel${channel}`;
  return hasTranslation(key) ? translate(key) : `CH${channel}`;
}

function summaryEntries(job) {
  return job?.result?.result?.channels ?? job?.result?.channels ?? null;
}

export class ChannelDisplayEditor {
  constructor(container, catalog, hooks) {
    this.container = container;
    this.catalog = catalog;
    this.hooks = hooks;
    this.busy = false;
    this.stateKey = null;
    this.channels = [];
    this.entries = [];
    this.buildDom();
  }

  definition() {
    return this.catalog.commands.find((command) => command.id === "channel-display") || null;
  }

  selectedDefinition() {
    const selected = this.hooks.selectedCommand?.();
    return selected?.editor === "channel-display" ? selected : null;
  }

  currentStateKey() {
    return `${this.hooks.contextKey()}|${this.selectedDefinition()?.id || ""}`;
  }

  displayChannels() {
    const definition = this.definition();
    if (!definition) return [];
    const fields = this.catalog.fieldsFor
      ? this.catalog.fieldsFor(definition)
      : definition.fields || [];
    const channelField = fields.find((field) => field.name === "channel") || {};
    const options = this.catalog.optionsFor
      ? this.catalog.optionsFor(channelField)
      : channelField.options || [];
    return [...options]
      .map(Number)
      .filter((channel) => Number.isInteger(channel) && channel > 0)
      .sort((left, right) => left - right);
  }

  buildDom() {
    this.refreshButton?.remove?.();
    this.container.replaceChildren();
    this.refreshButton = document.createElement("button");
    this.refreshButton.type = "button";
    this.refreshButton.className = "secondary trigger-editor-refresh";
    this.refreshButton.textContent = translate("actions.readSettings");
    this.refreshButton.addEventListener("click", () => {
      void this.read();
    });
    if (this.hooks.headerActions) {
      this.refreshButton.hidden = true;
      this.hooks.headerActions.append(this.refreshButton);
    } else {
      this.container.append(this.refreshButton);
    }
    this.choicesHost = document.createElement("div");
    this.choicesHost.className = "workflow-editor-choices";
    this.runButton = document.createElement("button");
    this.runButton.type = "button";
    this.runButton.className = "secondary trigger-editor-action";
    this.runButton.textContent = translate("actions.run");
    this.runButton.addEventListener("click", () => {
      void this.run();
    });
    this.status = document.createElement("output");
    this.status.className = "muted compact-note";
    this.container.append(this.choicesHost, this.runButton, this.status);
    this.stateKey = null;
    this.schedulePresentation();
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    this.refreshButton.textContent = translate("actions.readSettings");
    this.runButton.textContent = translate("actions.run");
    for (const entry of this.entries) entry.text.textContent = channelLabel(entry.channel);
  }

  present() {
    if (!this.selectedDefinition()) {
      this.stateKey = null;
      return;
    }
    const key = this.currentStateKey();
    if (key === this.stateKey) {
      this.applyBusyState();
      return;
    }
    this.stateKey = key;
    this.status.textContent = "";
    this.rebuild();
    this.applyBusyState();
  }

  rebuild() {
    this.channels = this.displayChannels();
    this.entries = [];
    this.choicesHost.replaceChildren();
    for (const channel of this.channels) {
      const choice = document.createElement("label");
      choice.className = "multi-choice-option";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = String(channel);
      box.checked = true;
      const text = document.createElement("span");
      text.textContent = channelLabel(channel);
      choice.append(box, text);
      this.choicesHost.append(choice);
      this.entries.push({ channel, box, text });
    }
  }

  boxFor(channel) {
    return this.entries.find((entry) => entry.channel === channel)?.box || null;
  }

  async run() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return null;
    if (!this.selectedDefinition()) return null;
    const channels = this.displayChannels();
    if (!channels.length) return null;
    const desired = channels.map((channel) => ({
      channel,
      enabled: this.boxFor(channel)?.checked === true,
    }));
    const key = this.hooks.contextKey();
    this.busy = true;
    this.applyBusyState();
    try {
      let job = null;
      for (const item of desired) {
        if (this.hooks.contextKey() !== key) return null;
        job = await this.hooks.executeCommand(
          "channel-display",
          { action: "set", channel: item.channel, enabled: item.enabled },
          { intent: "apply" },
        );
        if (this.hooks.contextKey() !== key) return null;
        const enabled = job?.result?.result?.enabled
          ?? job?.result?.enabled;
        if (
          job?.status !== "completed"
          || typeof enabled !== "boolean"
          || enabled !== item.enabled
        ) {
          this.status.textContent = translate("channel-display.editor.runIncomplete");
          return job;
        }
      }
      this.status.textContent = "";
      return job;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  async read() {
    if (this.busy || this.hooks.isExecutionBusy?.() || !this.hooks.isAvailable()) return null;
    if (!this.selectedDefinition()) return null;
    if (this.hooks.isCommandAvailable?.("channel-summary") === false) return null;
    const channels = this.displayChannels();
    if (!channels.length) return null;
    const key = this.hooks.contextKey();
    this.busy = true;
    this.applyBusyState();
    try {
      const job = await this.hooks.executeCommand("channel-summary", {}, { intent: "readback" });
      if (this.hooks.contextKey() !== key || !this.selectedDefinition()) return job;
      const states = new Map();
      const entries = summaryEntries(job);
      if (Array.isArray(entries)) {
        for (const entry of entries) states.set(Number(entry?.channel), entry?.display);
      }
      const complete = channels.every((channel) => typeof states.get(channel) === "boolean");
      if (job?.status !== "completed" || !complete) {
        this.status.textContent = translate("channel-display.editor.readFailed");
        return job;
      }
      for (const channel of channels) {
        const box = this.boxFor(channel);
        if (box) box.checked = states.get(channel);
      }
      this.status.textContent = "";
      return job;
    } finally {
      this.busy = false;
      this.applyBusyState();
    }
  }

  applyBusyState() {
    const disabled = this.busy
      || this.hooks.isExecutionBusy?.()
      || !this.hooks.isAvailable()
      || !this.channels.length;
    this.refreshButton.disabled = disabled;
    this.runButton.disabled = disabled;
    for (const entry of this.entries) entry.box.disabled = disabled;
  }
}
