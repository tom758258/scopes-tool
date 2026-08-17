import { getJob, submitJob } from "/static/api.js";
import { getExecutionContext } from "/static/execution-context.js";
import { translate } from "/static/i18n.js";

function contextSnapshot(context) {
  return {
    mode: context?.mode || null,
    resource: context?.resource || null,
    model_id: context?.model_id || null,
  };
}

function sameContext(left, right) {
  const a = contextSnapshot(left);
  const b = contextSnapshot(right);
  return a.mode === b.mode && a.resource === b.resource && a.model_id === b.model_id;
}

function identityLabel(identity) {
  if (!identity) return "";
  if (typeof identity === "string") return identity;
  return [identity.vendor || identity.manufacturer, identity.model].filter(Boolean).join(" ") || identity.model || "";
}

function resourceName(resource) {
  return typeof resource === "string" ? resource : resource?.name || "";
}

function resourceLabel(resource) {
  if (typeof resource === "string") return resource;
  const idn = resource?.idn || {};
  return [resourceName(resource), idn.manufacturer || idn.vendor, idn.model]
    .filter(Boolean)
    .join(" - ");
}

export class DeviceResource {
  constructor(elements, onContextChange, onCommandStateChange = () => {}) {
    this.elements = elements;
    this.onContextChange = onContextChange;
    this.onCommandStateChange = onCommandStateChange;
    this.resourceCount = null;
    this.statusKey = "device.ready";
    this.statusError = null;
    this.identity = null;
    this.identityContext = null;
    this.lastContext = null;
    this.scanStatus = "not-scanned";
    this.scanInProgress = false;
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
      this.changed(true);
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

  changed(forceIdentityClear = false) {
    const context = this.context();
    const live = context.mode === "live";
    const contextChanged = !sameContext(this.lastContext, context);
    if (forceIdentityClear || contextChanged) {
      this.clearIdentity();
      if (contextChanged && !this.scanInProgress) {
        this.scanStatus = "not-scanned";
        this.statusError = null;
      }
    }
    this.elements.model.disabled = live;
    this.renderMode(context);
    this.renderStatus(context);
    this.lastContext = contextSnapshot(context);
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
    const labels = {
      live: "device.liveMode",
      simulate: "device.simulateMode",
      "dry-run": "device.dryRunMode",
    };
    const mode = translate(labels[context.mode] || context.mode);
    let summary;
    if (context.mode === "live") {
      const resource = context.resource || translate("device.resourceNotSelected");
      summary = translate("device.summary.live", {
        mode,
        resource,
        detection: this.detectionSummary(context),
      });
    } else {
      const model = this.elements.model.selectedOptions?.[0]?.textContent || context.model_id;
      summary = translate("device.summary.planning", { mode, model });
    }
    this.elements.summary.textContent = summary;
    this.elements.summary.title = summary;
  }

  detectionSummary(context) {
    if (this.hasCurrentIdentity(context)) {
      return translate("device.detection.detectedModel", { model: identityLabel(this.identity) });
    }
    if (this.scanStatus === "empty") return translate("device.detection.noResources");
    if (this.scanStatus === "failed") {
      return translate("device.detection.scanFailed", {
        error: this.statusError || translate("status.scanFailed"),
      });
    }
    if (this.scanStatus === "scanning") return translate("device.detection.scanning");
    if (context.resource || this.resourceCount !== null) {
      return translate("device.detection.notIdentified");
    }
    return translate("device.detection.notScanned");
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

  setIdentity(identity, associatedContext = this.context()) {
    if (!sameContext(this.context(), associatedContext)) {
      this.clearIdentity();
      this.renderSummary(this.context());
      return false;
    }
    this.identity = identity || null;
    this.identityContext = contextSnapshot(associatedContext);
    this.renderStatus(this.context());
    return Boolean(this.identity);
  }

  clearIdentity() {
    this.identity = null;
    this.identityContext = null;
  }

  hasCurrentIdentity(context = this.context()) {
    return Boolean(this.identity && this.identityContext && sameContext(context, this.identityContext));
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
    this.scanInProgress = true;
    this.clearIdentity();
    this.resourceCount = null;
    this.scanStatus = "scanning";
    this.statusKey = "status.waiting";
    this.statusError = null;
    this.renderStatus();
    this.onCommandStateChange({ status: "queued" });
    try {
      const context = this.context();
      const submitted = await submitJob({
        command: "list-resources",
        parameters: { live_only: true },
        ...context,
      });
      let job = await getJob(submitted.job_id);
      this.onCommandStateChange({ status: job.status });
      while (["queued", "running"].includes(job.status)) {
        await new Promise((resolve) => setTimeout(resolve, 200));
        job = await getJob(submitted.job_id);
        this.onCommandStateChange({ status: job.status });
      }
      if (job.status !== "completed") throw new Error(job.error || translate("status.scanFailed"));
      const resources = job.result?.result?.resources || [];
      this.renderResourceList(resources);
      if (resources.length) this.elements.resource.value = resourceName(resources[0]);
      this.resourceCount = resources.length;
      this.scanStatus = resources.length ? "scanned" : "empty";
      this.statusKey = "device.ready";
      this.changed();
    } catch (error) {
      this.onCommandStateChange({ status: "failed" });
      this.resourceCount = null;
      this.scanStatus = "failed";
      this.statusKey = "status.scanFailed";
      this.statusError = error.message;
      this.renderStatus();
    } finally {
      this.scanInProgress = false;
      this.elements.scan.disabled = false;
    }
  }

  renderResourceList(resources) {
    this.elements.resourceList.replaceChildren();
    if (!resources.length) {
      const option = new Option(translate("device.liveResourceNoResources"), "");
      option.dataset.i18n = "device.liveResourceNoResources";
      this.elements.resourceList.append(option);
      return;
    }
    resources.forEach((resource) => {
      const name = resourceName(resource);
      if (!name) return;
      this.elements.resourceList.append(new Option(resourceLabel(resource), name));
    });
  }
}
