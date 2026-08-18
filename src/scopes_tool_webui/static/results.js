import { artifactUrl } from "/static/api.js";
import { hasTranslation, translate, translateJobStatus } from "/static/i18n.js";

const RESULT_HISTORY_LIMIT = 20;
let resultHistory = [];

export function renderEmpty(summaryContainer, detailContainer) {
  resultHistory = [];
  summaryContainer.replaceChildren(emptyMessage());
  if (detailContainer) detailContainer.replaceChildren(emptyMessage());
}

export function renderError(summaryContainer, detailContainer, message, command = null) {
  const current = resultHistory[0];
  if (!(current?.kind === "error" && current.message === message && current.command === command)) {
    resultHistory.unshift({ kind: "error", message, command });
    resultHistory = resultHistory.slice(0, RESULT_HISTORY_LIMIT);
  }
  renderHistory(summaryContainer);
  if (detailContainer) {
    detailContainer.replaceChildren();
    appendError(detailContainer, message);
  }
}

export function renderJob(summaryContainer, job, detailContainer) {
  const existingIndex = resultHistory.findIndex(
    (entry) => entry.kind === "job" && entry.job.job_id === job.job_id,
  );
  if (existingIndex >= 0) {
    resultHistory[existingIndex].job = job;
  } else {
    resultHistory.unshift({ kind: "job", job });
    resultHistory = resultHistory.slice(0, RESULT_HISTORY_LIMIT);
  }
  renderHistory(summaryContainer);

  if (!detailContainer) return;
  detailContainer.replaceChildren();
  if (job.error) appendError(detailContainer, job.error);
  if (job.result) {
    const result = document.createElement("pre");
    result.className = "result-block";
    result.textContent = JSON.stringify(job.result, null, 2);
    detailContainer.append(result);
  }
  if (job.artifacts?.length) {
    const heading = document.createElement("h3");
    heading.textContent = translate("results.artifacts");
    detailContainer.append(heading);
    const list = document.createElement("ul");
    job.artifacts.forEach((artifact) => {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = artifactUrl(job.job_id, artifact.name);
      link.textContent = translate("results.artifactSize", {
        name: artifact.name,
        size: artifact.size,
      });
      link.download = artifact.name;
      item.append(link);
      list.append(item);
    });
    detailContainer.append(list);
  }
  if (!detailContainer.childElementCount) detailContainer.append(emptyMessage());
}

function renderHistory(summaryContainer) {
  summaryContainer.replaceChildren();
  if (!resultHistory.length) {
    summaryContainer.append(emptyMessage());
    return;
  }
  resultHistory.forEach((entry) => {
    const statusLine = document.createElement("div");
    statusLine.className = "result-summary-line";

    const label = document.createElement("strong");
    if (entry.kind === "job") {
      label.textContent = commandLabel(entry.job.command);
    } else if (entry.command) {
      label.textContent = commandLabel(entry.command);
    } else {
      label.textContent = translate("results.error");
    }
    statusLine.append(label);

    const statusValue = entry.kind === "job" ? entry.job.status : "failed";
    const status = document.createElement("span");
    status.className = `badge badge-${statusValue}`;
    status.textContent = translateJobStatus(statusValue);
    statusLine.append(status);

    const summary = document.createElement("span");
    summary.className = "result-summary";
    summary.textContent = entry.kind === "job" ? jobSummary(entry.job) : entry.message;
    statusLine.append(summary);
    summaryContainer.append(statusLine);
  });
}

function commandLabel(command) {
  if (!command) return "";
  const key = `command.${command}`;
  return hasTranslation(key) ? translate(key) : command;
}

function jobSummary(job) {
  if (job.status === "failed") return jobErrorSummary(job);
  if (job.status === "cancelled") return translate("status.cancelled");
  if (job.status === "queued") return translate("results.summary.queued");
  if (job.status === "running") return translate("results.summary.running");
  if (job.status !== "completed") return translateJobStatus(job.status);
  return successfulJobSummary(job);
}

function jobErrorSummary(job) {
  const result = jobResultPayload(job);
  if (typeof result?.error === "string") return result.error;
  if (typeof result?.error?.message === "string") return result.error.message;
  return job.error || translate("results.summary.failed");
}

function successfulJobSummary(job) {
  const result = jobResultPayload(job);
  if (job.command === "identify") return identifySummary(result);
  if (job.command === "list-resources") return resourceSummary(result);
  if (job.command === "screenshot") return translate("results.summary.screenshotCaptured");

  const artifactCount = Math.max(
    Array.isArray(job.artifacts) ? job.artifacts.length : 0,
    Array.isArray(job.result?.artifacts) ? job.result.artifacts.length : 0,
  );
  if (artifactCount) {
    return translate(
      artifactCount === 1 ? "results.summary.artifact_one" : "results.summary.artifact_many",
      { count: artifactCount },
    );
  }

  return scalarResultSummary(result) || translate("results.summary.completed");
}

function jobResultPayload(job) {
  const result = job?.result;
  if (!result || typeof result !== "object") return result;
  return result.result !== undefined ? result.result : result;
}

function identifySummary(result) {
  const idn = result?.idn || result?.resource?.idn || {};
  const parts = [
    idn.model,
    idn.serial ? translate("results.summary.serial", { serial: idn.serial }) : "",
    idn.firmware ? translate("results.summary.firmware", { firmware: idn.firmware }) : "",
  ].filter(Boolean);
  return parts.length ? parts.join(" - ") : translate("results.summary.identificationRead");
}

function resourceSummary(result) {
  const count = Array.isArray(result?.resources) ? result.resources.length : 0;
  if (count === 0) return translate("results.summary.resource_none");
  return translate(
    count === 1 ? "results.summary.resource_one" : "results.summary.resource_many",
    { count },
  );
}

function scalarResultSummary(result) {
  if (result === null || result === undefined) return "";
  if (["string", "number", "boolean"].includes(typeof result)) return String(result);
  if (typeof result !== "object") return "";
  const entries = Object.entries(result);
  if (entries.length !== 1 || entries[0][0] === "action") return "";
  const value = entries[0][1];
  return value !== null && ["string", "number", "boolean"].includes(typeof value)
    ? String(value)
    : "";
}

function appendError(container, message) {
  const error = document.createElement("pre");
  error.className = "error-block";
  error.textContent = message;
  container.append(error);
}

function emptyMessage() {
  const empty = document.createElement("p");
  empty.className = "muted";
  empty.textContent = translate("results.empty");
  return empty;
}
