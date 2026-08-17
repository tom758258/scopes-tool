const HEALTH_PATH = "/api/health";

export async function getHealth() {
  const response = await fetch(HEALTH_PATH, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Health request failed with HTTP ${response.status}.`);
  }
  return response.json();
}
