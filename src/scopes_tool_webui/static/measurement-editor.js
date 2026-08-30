import { CommandForm } from "/static/command-form.js";
import { translate } from "/static/i18n.js";

function measurementPayload(job) {
  return job?.result?.result?.measurements || job?.result?.measurements || null;
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
    this.windowCurrent = "";
    this.windowReadback = "";
    this.windowDirty = false;
    this.frontPanelState = { kind: "unread", payload: null };
    this.frontPanelReadError = null;
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
    this.renderedKey = null;
    return true;
  }

  schedulePresentation() {
    queueMicrotask(() => this.present());
  }

  rerender() {
    if (this.measureForm) this.measureDraft = this.measureForm.draft();
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
      this.renderedKey = key;
      if (selected.id === "measure") this.renderSettings();
      else this.renderFrontPanel();
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

  renderFrontPanel() {
    this.container.replaceChildren();
    this.controls = {};
    const actions = document.createElement("div");
    actions.className = "measurement-front-panel-actions";
    const actionDefinitions = [
      ["frontPanelRefresh", "measure-results", "measurement.frontPanel.refresh", "primary"],
      ...(this.markerToggleSupported() === true
        ? [
          ["frontPanelShow", "measure-show", "measurement.frontPanel.show", "secondary", true],
          ["frontPanelHide", "measure-show", "measurement.frontPanel.hide", "secondary", false],
        ]
        : []),
      ["frontPanelClear", "measure-clear", "measurement.frontPanel.clear", "danger"],
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
        else void this.clearFrontPanel();
      });
      this.controls[name] = button;
      wrapper.append(button);
      const reason = this.catalog.supportReason(this.definition(command));
      if (reason) {
        const note = document.createElement("small");
        note.className = "command-support-reason";
        note.textContent = reason;
        wrapper.append(note);
      }
      actions.append(wrapper);
    }
    if (this.markerToggleSupported() === false) {
      const note = document.createElement("p");
      note.className = "compact-note measurement-front-panel-marker-note";
      note.textContent = translate("measurement.frontPanel.markersAlwaysOn");
      actions.append(note);
    }
    const result = document.createElement("section");
    result.className = "measurement-front-panel-results";
    const heading = document.createElement("strong");
    heading.textContent = translate("measurement.frontPanel.resultsTitle");
    this.frontPanelContent = document.createElement("div");
    this.frontPanelContent.className = "measurement-front-panel-content";
    this.frontPanelContent.setAttribute("aria-live", "polite");
    result.append(heading, this.frontPanelContent);
    this.container.append(actions, result);
    this.renderFrontPanelReadback();
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
    if (this.controls.windowRefresh) {
      this.controls.windowRefresh.disabled = busy
        || !this.hooks.isCommandAvailable("measure-window");
    }
    for (const [name, command] of [
      ["frontPanelRefresh", "measure-results"],
      ["frontPanelShow", "measure-show"],
      ["frontPanelHide", "measure-show"],
      ["frontPanelClear", "measure-clear"],
    ]) {
      if (this.controls[name]) {
        this.controls[name].disabled = busy || !this.hooks.isCommandAvailable(command);
      }
    }
  }
}
