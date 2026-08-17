import { getHealth } from "/static/api.js";

const SERVICE_NAME = "scopes-tool-webui";
const statusElement = document.querySelector("#health-status");

async function updateHealth() {
  try {
    const health = await getHealth();
    if (health.status !== "ok" || health.package !== SERVICE_NAME) {
      throw new Error("Unexpected service identity.");
    }
    statusElement.textContent = "Service is healthy.";
  } catch (error) {
    statusElement.textContent = `Service health check failed: ${error.message}`;
  }
}

updateHealth();
