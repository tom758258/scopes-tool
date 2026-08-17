import { getJob, submitJob } from "/static/api.js";
import { getExecutionContext } from "/static/execution-context.js";
import { translate } from "/static/i18n.js";

export class DeviceResource {
  constructor(elements, onContextChange) {
    this.elements = elements;
    this.onContextChange = onContextChange;
    this.resourceCount = null;
    this.statusKey = "device.ready";
    this.statusError = null;
    elements.settings.addEventListener("click", () => elements.settingsPanel.classList.toggle("hidden"));
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
    this.elements.hint.textContent = live ? translate("device.liveHint") : "";
    this.renderStatus();
    this.onContextChange(context);
  }

  refresh() {
    this.changed();
  }

  renderStatus() {
    if (this.resourceCount !== null) {
      this.elements.status.textContent = translate(
        this.resourceCount === 1 ? "device.resourceCount.one" : "device.resourceCount.many",
        { count: this.resourceCount },
      );
      return;
    }
    const message = translate(this.statusKey);
    this.elements.status.textContent = this.statusError ? `${message}: ${this.statusError}` : message;
  }

  async scan() {
    this.elements.scan.disabled = true;
    this.resourceCount = null;
    this.statusKey = "status.waiting";
    this.statusError = null;
    this.renderStatus();
    try {
      const context = this.context();
      const submitted = await submitJob({ command: "list-resources", ...context });
      let job = await getJob(submitted.job_id);
      while (["queued", "running"].includes(job.status)) {
        await new Promise((resolve) => setTimeout(resolve, 200));
        job = await getJob(submitted.job_id);
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
      this.resourceCount = null;
      this.statusKey = "status.scanFailed";
      this.statusError = error.message;
      this.renderStatus();
    } finally {
      this.elements.scan.disabled = false;
    }
  }
}
