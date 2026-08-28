const PREFIXES = new Map([
  [-12, "p"],
  [-9, "n"],
  [-6, "µ"],
  [-3, "m"],
  [0, ""],
  [3, "k"],
  [6, "M"],
  [9, "G"],
]);

export function formatEngineering(value, unit, { signed = false, perDivision = false } = {}) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || !unit) return "—";

  const magnitude = Math.abs(numeric);
  const exponent = magnitude === 0
    ? 0
    : Math.max(-12, Math.min(9, Math.floor(Math.log10(magnitude) / 3) * 3));
  const scaled = numeric / (10 ** exponent);
  const scaledMagnitude = Math.abs(scaled);
  const decimals = scaledMagnitude >= 100 ? 0 : scaledMagnitude >= 10 ? 1 : 2;
  const sign = signed && numeric >= 0 ? "+" : "";
  const suffix = perDivision ? "/div" : "";
  return `${sign}${scaled.toFixed(decimals)} ${PREFIXES.get(exponent)}${unit}${suffix}`;
}

export function renderInstrumentSummary(elements, snapshot, translate, status = {}) {
  elements.status.hidden = !status.key;
  elements.status.textContent = status.key ? translate(status.key) : "";
  elements.status.title = status.error || elements.status.textContent;

  elements.channels.replaceChildren();
  if (snapshot?.channels?.length) {
    snapshot.channels.forEach((channel) => elements.channels.append(channelCard(channel, translate)));
  } else {
    elements.channels.append(unavailableMessage());
  }

  const unit = (value) => channelUnit(value);
  elements.timebaseScale.textContent = formatEngineering(snapshot?.timebase?.scale, "s", { perDivision: true });
  elements.timebasePosition.textContent = formatEngineering(snapshot?.timebase?.position, "s", { signed: true });
  elements.triggerType.textContent = enumLabel("type", snapshot?.trigger?.type, translate);
  elements.triggerSource.textContent = triggerSource(snapshot?.trigger, translate);
  elements.triggerLevel.textContent = formatEngineering(
    snapshot?.trigger?.level,
    unit(snapshot?.trigger?.units),
    { signed: true },
  );
  elements.triggerSlope.textContent = enumLabel("slope", snapshot?.trigger?.slope, translate);
  elements.triggerSweep.textContent = enumLabel("sweep", snapshot?.trigger?.sweep, translate);
}

function channelCard(channel, translate) {
  const card = document.createElement("article");
  card.className = "live-channel-card";

  const header = document.createElement("div");
  header.className = "live-channel-head";
  const heading = document.createElement("strong");
  heading.textContent = `CH${channel.channel}`;
  const display = document.createElement("span");
  display.className = `badge ${channel.display === true ? "badge-completed" : channel.display === false ? "badge-idle" : "badge-queued"}`;
  display.textContent = channel.display === true
    ? translate("live_data.on")
    : channel.display === false
      ? translate("live_data.off")
      : "—";
  header.append(heading, display);

  const fields = document.createElement("dl");
  fields.className = "live-summary-fields";
  appendField(fields, translate("live_data.scale"), formatEngineering(channel.scale, channelUnit(channel.units), { perDivision: true }));
  appendField(fields, translate("live_data.offset"), formatEngineering(channel.offset, channelUnit(channel.units), { signed: true }));
  card.append(header, fields);
  return card;
}

function appendField(container, label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const detail = document.createElement("dd");
  detail.textContent = value;
  container.append(term, detail);
}

function unavailableMessage() {
  const message = document.createElement("p");
  message.className = "muted live-data-unavailable";
  message.textContent = "—";
  return message;
}

function channelUnit(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "volt") return "V";
  if (normalized.startsWith("amp")) return "A";
  return "";
}

function triggerSource(trigger, translate) {
  if (!trigger?.source) return "—";
  if (trigger.source === "analog-channel" && trigger.source_channel) {
    return `CH${trigger.source_channel}`;
  }
  const key = `live_data.source.${trigger.source}`;
  const translated = translate(key);
  return translated === key ? String(trigger.source) : translated;
}

function enumLabel(kind, value, translate) {
  if (value === null || value === undefined || value === "") return "—";
  const key = `live_data.${kind}.${value}`;
  const translated = translate(key);
  if (translated !== key) return translated;
  const token = String(value);
  return /^[a-z0-9-]+$/.test(token)
    ? token.split("-").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ")
    : token;
}
