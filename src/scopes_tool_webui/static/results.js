import { artifactUrl } from "/static/api.js";
import { translate, translateJobStatus } from "/static/i18n.js";

export function renderJob(container, job) {
  container.replaceChildren();
  const status = document.createElement("p");
  status.innerHTML = `<span class="badge badge-${job.status}">${escapeHtml(translateJobStatus(job.status))}</span>`;
  container.append(status);
  if (job.error) {
    const error = document.createElement("pre");
    error.className = "error-block";
    error.textContent = job.error;
    container.append(error);
  }
  if (job.result) {
    const result = document.createElement("pre");
    result.className = "result-block";
    result.textContent = JSON.stringify(job.result, null, 2);
    container.append(result);
  }
  if (job.artifacts?.length) {
    const heading = document.createElement("h3");
    heading.textContent = translate("results.artifacts");
    container.append(heading);
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
    container.append(list);
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[character]));
}
