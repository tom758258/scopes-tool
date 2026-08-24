const HEALTH_PATH = "/api/health";
const COMMANDS_PATH = "/api/commands";
const JOBS_PATH = "/api/jobs";
const PC_OUTPUT_FOLDER_PATH = "/api/pc-output/select-folder";
const PC_OUTPUT_OPEN_FOLDER_PATH = "/api/pc-output/open-folder";

export async function getHealth() {
  return getJson(HEALTH_PATH);
}

export async function getCommands() {
  return getJson(COMMANDS_PATH);
}

export async function submitJob(payload) {
  return requestJson(JOBS_PATH, "POST", payload);
}

export async function selectPcOutputFolder() {
  return requestJson(PC_OUTPUT_FOLDER_PATH, "POST", {});
}

export async function openPcOutputFolder(pcOutputDir) {
  return requestJson(PC_OUTPUT_OPEN_FOLDER_PATH, "POST", { pc_output_dir: pcOutputDir });
}

export async function getJob(jobId) {
  return getJson(`${JOBS_PATH}/${encodeURIComponent(jobId)}`);
}

export async function cancelJob(jobId) {
  return requestJson(`${JOBS_PATH}/${encodeURIComponent(jobId)}/cancel`, "POST", {});
}

export function artifactUrl(jobId, name) {
  return `${JOBS_PATH}/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(name)}`;
}

async function getJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return response.json();
}

async function requestJson(path, method, payload) {
  const response = await fetch(path, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return response.json();
}

async function responseError(response) {
  try {
    const payload = await response.json();
    return payload.detail || `Request failed with HTTP ${response.status}.`;
  } catch {
    return `Request failed with HTTP ${response.status}.`;
  }
}
