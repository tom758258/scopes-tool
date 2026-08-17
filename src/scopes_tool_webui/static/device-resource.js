import { getJob, submitJob } from "/static/api.js";
import { getExecutionContext } from "/static/execution-context.js";
import { translate } from "/static/i18n.js";

export class DeviceResource {
  constructor(elements, onContextChange, onCommandStateChange = () => {}) {
    this.elements = elements;
    this.onContextChange = onContextChange;
    this.onCommandStateChange = onCommandStateChange;
    this.resourceCount = null;
    this.statusKey = "device.ready";
    this.statusError = null;
    this.identity = null;
    elements.settings.addEventListener("click", (event) => {
      event.stopPropagation();
      this.setSettingsExpanded(elements.settingsPanel.hidden);
    });
    elements.settingsPanel.addEventListener("click", (event) => event.stopPropagation());
    document.addEventListener("click", () => this.setSettingsExpanded(false));
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || elements.settingsPanel.hidden) return;
      this.setSettingsExpanded(false);
      elements.settings.focus();
    });
    elements.deviceCollapse.addEventListener("click", () => this.toggleBody());
    elements.mode.forEach((input) => input.addEventListener("change", () => this.changed()));
    elements.model.addEventListener("change", () => this.changed());
    elements.resource.addEventListener("input", () => this.changed());
    elements.resourceList.addEventListener("change", () => {
      elements.resource.value = elements.resourceList.value;
      this.changed();
    });
    elements.scan.addEventListener("click", () => this.scan());
    this.changed();
  }

  context() {
    return getExecutionContext({
      mode: this.elements.mode.find((input) => input.checked),
      resource: this.elements.resource,
      model: this.elements.model,
    });
  }

  changed() {
    const context = this.context();
    const live = context.mode === "live";
    this.elements.model.disabled = live;
    this.renderMode(context);
    this.renderStatus(context);
    this.onContextChange(context);
  }

  refresh() {
    this.changed();
  }

  setSettingsExpanded(expanded) {
    this.elements.settingsPanel.hidden = !expanded;
    this.elements.settings.setAttribute("aria-expanded", String(expanded));
  }

  renderMode(context) {
    const labels = { live: "device.live", simulate: "device.simulate", "dry-run": "device.dryRun" };
    this.elements.modeBadge.className = `execution-mode-badge mode-${context.mode}`;
    this.elements.modeBadge.textContent = translate(labels[context.mode] || context.mode);
  }

  renderSummary(context) {
    const labels = { live: "device.live", simulate: "device.simulate", "dry-run": "device.dryRun" };
    const mode = translate(labels[context.mode] || context.mode);
    const resource = context.resource || translate("device.noResource");
    const identity = this.identity || translate("device.identityNotDetected");
    this.elements.summary.textContent = translate("device.summary", { mode, resource, identity });
  }

  renderStatus(context = this.context()) {
    if (this.resourceCount !== null) {
      this.elements.status.textContent = translate(
        this.resourceCount === 1 ? "device.resourceCount.one" : "device.resourceCount.many",
        { count: this.resourceCount },
      );
    } else {
      const message = translate(this.statusKey);
      this.elements.status.textContent = this.statusError ? `${message}: ${this.statusError}` : message;
    }
    this.renderSummary(context);
  }

  setIdentity(identity) {
    this.identity = identity || null;
    this.renderSummary(this.context());
  }

  toggleBody() {
    const expanded = !this.elements.body.hidden;
    this.elements.body.hidden = expanded;
    this.elements.deviceCollapse.setAttribute("aria-expanded", String(!expanded));
    const key = expanded ? "device.expand" : "device.collapse";
    this.elements.deviceCollapse.title = translate(key);
    this.elements.deviceCollapse.setAttribute("aria-label", translate(key));
    this.elements.deviceCollapse.textContent = expanded ? "+" : "-";
  }

  async scan() {
    this.elements.scan.disabled = true;
    this.resourceCount = null;
    this.statusKey = "status.waiting";
    this.statusError = null;
    this.renderStatus();
    this.onCommandStateChange({ status: "queued" });
    try {
      const context = this.context();
      const submitted = await submitJob({ command: "list-resources", ...context });
      let job = await getJob(submitted.job_id);
      this.onCommandStateChange({ status: job.status });
      while (["queued", "running"].includes(job.status)) {
        await new Promise((resolve) => setTimeout(resolve, 200));
        job = await getJob(submitted.job_id);
        this.onCommandStateChange({ status: job.status });
      }
      if (job.status !== "completed") throw new Error(job.error || translate("status.scanFailed"));
      const resources = job.result?.result?.resources || [];
      this.elements.resourceList.replaceChildren();
      resources.forEach((resource) => this.elements.resourceList.append(new Option(resource, resource)));
      if (resources.length) this.elements.resource.value = resources[0];
      this.resourceCount = resources.length;
      this.statusKey = "device.ready";
      this.changed();
    } catch (error) {
      this.onCommandStateChange({ status: "failed" });
      this.resourceCount = null;
      this.statusKey = "status.scanFailed";
      this.statusError = error.message;
      this.renderStatus();
    } finally {
      this.elements.scan.disabled = false;
    }
  }
}
