import { translate } from "/static/i18n.js";

export function initializeSupportedDevices({ button, panel, body, status, settings, tabs, content, pendingNote, onOpen }) {
  const owner = button.ownerDocument;
  let backend = "system_visa";
  const devices = new Map();
  const loading = new Set();
  const errors = new Set();

  const render = () => {
    tabs.forEach((tab) => {
      const selected = tab.dataset.backend === backend;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected) content.setAttribute("aria-labelledby", tab.id);
    });
    pendingNote.hidden = backend !== "@py";
    const rows = devices.get(backend) || [];
    const statusKey = loading.has(backend) ? "supported_devices.loading"
      : errors.has(backend) ? "supported_devices.error"
        : devices.has(backend) && !rows.length ? "supported_devices.empty" : null;
    status.hidden = !statusKey;
    status.textContent = statusKey ? translate(statusKey) : "";
    body.replaceChildren();
    const groups = new Map();
    rows.forEach((device) => {
      let list = groups.get(device.vendor);
      if (!list) {
        const section = owner.createElement("section");
        section.className = "supported-devices-group";
        const heading = owner.createElement("h3");
        heading.textContent = device.vendor;
        list = owner.createElement("ul");
        section.append(heading, list);
        body.append(section);
        groups.set(device.vendor, list);
      }
      const row = owner.createElement("li");
      const model = owner.createElement("span");
      model.textContent = device.model;
      const connections = owner.createElement("span");
      connections.textContent = device.connections.map((connection) => {
        if (connection === "USB") return translate("supported_devices.connection.usb");
        if (connection === "TCPIP") return translate("supported_devices.connection.tcpip");
        return connection;
      }).join(translate("supported_devices.connection_separator"));
      row.append(model, connections);
      list.append(row);
    });
  };
  const setExpanded = (expanded) => {
    panel.hidden = !expanded;
    button.setAttribute("aria-expanded", String(expanded));
  };
  const load = async () => {
    const requested = backend;
    if (devices.has(requested) || loading.has(requested)) return;
    loading.add(requested);
    errors.delete(requested);
    render();
    try {
      const query = requested === "system_visa" ? "" : `?backend=${encodeURIComponent(requested)}`;
      const response = await fetch(`/api/supported-devices${query}`);
      if (!response.ok) throw new Error("Unable to load supported devices");
      devices.set(requested, await response.json());
    } catch (_error) {
      errors.add(requested);
    } finally {
      loading.delete(requested);
      render();
    }
  };
  const selectTab = (tab) => {
    backend = tab.dataset.backend;
    render();
    void load();
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (event) => {
      const next = { ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1 }[event.key];
      if (next === undefined) return;
      event.preventDefault();
      tabs[next].focus();
      selectTab(tabs[next]);
    });
  });
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    const expanded = panel.hidden;
    setExpanded(expanded);
    if (expanded) {
      onOpen?.();
      void load();
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
  owner.addEventListener("localechange", render);
  render();
}
