import { translate } from "/static/i18n.js";

export function initializeSupportedDevices({ button, panel, body, status, settings, onOpen }) {
  const owner = button.ownerDocument;
  let loaded = false;
  let loading = false;
  let statusKey = null;
  let devices = [];

  const renderStatus = () => {
    status.hidden = !statusKey;
    status.textContent = statusKey ? translate(statusKey) : "";
  };
  const renderDevices = () => {
    body.replaceChildren();
    devices.forEach((device) => {
      const row = owner.createElement("tr");
      const connections = device.connections.map((connection) => {
        if (connection === "USB") return translate("supported_devices.connection.usb");
        if (connection === "TCPIP") return translate("supported_devices.connection.tcpip");
        return connection;
      }).join(translate("supported_devices.connection_separator"));
      [device.vendor, device.model, connections].forEach((value) => {
        const cell = owner.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      body.append(row);
    });
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
      devices = await response.json();
      renderDevices();
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
  owner.addEventListener("localechange", () => {
    renderStatus();
    if (loaded) renderDevices();
  });
}
