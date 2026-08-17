import { artifactUrl } from "/static/api.js";
import { translate, translateJobStatus } from "/static/i18n.js";

export function renderEmpty(summaryContainer, detailContainer) {
  summaryContainer.replaceChildren(emptyMessage());
  if (detailContainer) detailContainer.replaceChildren(emptyMessage());
}

export function renderError(summaryContainer, detailContainer, message) {
  summaryContainer.replaceChildren();
  const summary = document.createElement("p");
  summary.className = "error-summary";
  summary.textContent = message;
  summaryContainer.append(summary);
  if (detailContainer) {
    detailContainer.replaceChildren();
    const detail = document.createElement("pre");
    detail.className = "error-block";
    detail.textContent = message;
    detailContainer.append(detail);
  }
}

export function renderJob(summaryContainer, job, detailContainer) {
  summaryContainer.replaceChildren();
  const statusLine = document.createElement("div");
  statusLine.className = "result-summary-line";
  const status = document.createElement("span");
  status.className = `badge badge-${job.status}`;
  status.textContent = translateJobStatus(job.status);
  statusLine.append(status);
  const summary = document.createElement("span");
  summary.className = "result-summary";
  summary.textContent = job.error
    ? translate("results.error")
    : job.result || job.artifacts?.length
      ? translate("results.detailAvailable")
      : translate("results.status");
  statusLine.append(summary);
  summaryContainer.append(statusLine);
  if (job.error) {
    const error = document.createElement("p");
    error.className = "error-summary";
    error.textContent = job.error;
    summaryContainer.append(error);
  }

  if (!detailContainer) return;
  detailContainer.replaceChildren();
  if (job.error) {
    const error = document.createElement("pre");
    error.className = "error-block";
    error.textContent = job.error;
    detailContainer.append(error);
  }
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

function emptyMessage() {
  const empty = document.createElement("p");
  empty.className = "muted";
  empty.textContent = translate("results.empty");
  return empty;
}
