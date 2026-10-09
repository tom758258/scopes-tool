import { translate } from "/static/i18n.js";

export function initializeSupportedDevices({ button, panel, body, status, settings, onOpen }) {
  const owner = button.ownerDocument;
  let loaded = false;
  let loading = false;
  let statusKey = null;

  const renderStatus = () => {
    status.hidden = !statusKey;
    status.textContent = statusKey ? translate(statusKey) : "";
  };
  const setExpanded = (expanded) => {
    panel.hidden = !expanded;
    button.setAttribute("aria-expanded", String(expanded));
  };
  const load = async () => {
    if (loaded || loading) return;
    loading = true;
    statusKey = "supported_devices.loading";
    renderStatus();
    try {
      const response = await fetch("/api/supported-devices");
      if (!response.ok) throw new Error("Unable to load supported devices");
      const devices = await response.json();
      body.replaceChildren();
      devices.forEach((device) => {
        const row = owner.createElement("tr");
        [device.vendor, device.model, device.connections.join(", ")].forEach((value) => {
          const cell = owner.createElement("td");
          cell.textContent = value;
          row.append(cell);
        });
        body.append(row);
      });
      loaded = true;
      statusKey = devices.length ? null : "supported_devices.empty";
    } catch (_error) {
      statusKey = "supported_devices.error";
    } finally {
      loading = false;
      renderStatus();
    }
  };

  button.addEventListener("click", (event) => {
    event.stopPropagation();
    const expanded = panel.hidden;
    setExpanded(expanded);
    if (expanded) {
      onOpen?.();
      load();
    }
  });
  panel.addEventListener("click", (event) => event.stopPropagation());
  settings.addEventListener("click", () => setExpanded(false));
  owner.addEventListener("click", () => setExpanded(false));
  owner.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || panel.hidden) return;
    setExpanded(false);
    button.focus();
  });
  owner.addEventListener("localechange", renderStatus);
}
