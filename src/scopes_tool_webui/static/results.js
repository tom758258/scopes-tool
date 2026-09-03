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

function isInvalidMeasurementSentinel(job) {
  const result = jobResultPayload(job);
  return job?.status === "failed"
    && job?.command === "measure"
    && job?.result?.system_error?.is_error === false
    && result?.valid === false
    && result?.reason === "invalid measurement sentinel";
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
  if (job.error && !isInvalidMeasurementSentinel(job)) appendError(detailContainer, job.error);
  if (job.command === "identify" && job.status === "completed") {
    appendIdentityDetail(detailContainer, job);
  }
  if (job.result) {
    const result = document.createElement("pre");
    result.className = "result-block";
    result.textContent = JSON.stringify(job.result, null, 2);
    detailContainer.append(result);
  }
  if (Array.isArray(job.artifacts) && job.artifacts.length) {
    const heading = document.createElement("strong");
    heading.textContent = translate("results.artifacts");
    const list = document.createElement("ul");
    job.artifacts.forEach((artifact) => {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = artifact.url;
      link.textContent = artifact.name;
      link.download = artifact.name;
      item.append(link);
      list.append(item);
    });
    detailContainer.append(heading, list);
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

    const invalidMeasurement =
      entry.kind === "job" && isInvalidMeasurementSentinel(entry.job);
    const statusValue = entry.kind === "job" ? entry.job.status : "failed";
    const status = document.createElement("span");
    status.className = invalidMeasurement
      ? "badge badge-warning"
      : `badge badge-${statusValue}`;
    status.textContent = invalidMeasurement
      ? translate("results.status.noValidMeasurement")
      : translateJobStatus(statusValue);
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
  if (isInvalidMeasurementSentinel(job)) return translate("results.summary.noValidMeasurement");
  if (job.status === "failed") return jobErrorSummary(job);
  if (job.status === "cancelled") return translate("status.cancelled");
  if (job.status === "queued") return translate("results.summary.queued");
  if (job.status === "running") {
    if (job.command === "sequence" && job.progress) {
      return translate("results.summary.sequenceProgress", {
        completed: job.progress.completed_count,
        total: job.progress.total_count,
      });
    }
    if (job.progress && isWorkflowProgressCommand(job.command)) {
      return workflowProgressSummary(job);
    }
    return translate("results.summary.running");
  }
  if (job.status !== "completed") return translateJobStatus(job.status);
  return successfulJobSummary(job);
}

function isWorkflowProgressCommand(command) {
  return (
    command === "measure-log" ||
    command === "measure-until" ||
    command === "triggered-measure-loop" ||
    command === "capture-batch" ||
    command === "capture-until" ||
    command === "triggered-capture-series"
  );
}

function workflowProgressUnit(command) {
  if (command === "measure-log") return translate("results.progress.rows");
  if (command === "measure-until") return translate("results.progress.samples");
  if (command === "triggered-measure-loop") return translate("results.progress.cycles");
  if (
    command === "capture-batch" ||
    command === "capture-until" ||
    command === "triggered-capture-series"
  ) {
    return translate("results.progress.captures");
  }
  return "";
}

function formatElapsed(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return "0.0";
  return value.toFixed(1);
}

function workflowProgressSummary(job) {
  const unit = workflowProgressUnit(job.command);
  const elapsed = formatElapsed(job.progress.elapsed_seconds);
  const completed = job.progress.completed_count;
  const total = job.progress.total_count;
  if (total === null || total === undefined) {
    return translate("results.summary.workflowProgressUnknown", {
      completed,
      unit,
      elapsed,
    });
  }
  return translate("results.summary.workflowProgressKnown", {
    completed,
    total,
    unit,
    elapsed,
  });
}

function jobErrorSummary(job) {
  const result = jobResultPayload(job);
  if (typeof result?.error === "string") return result.error;
  if (typeof result?.error?.message === "string") return result.error.message;

  const structuredSummary = commandErrorSummary(job.command, result);
  if (structuredSummary) return structuredSummary;

  const systemError = job?.result?.system_error;
  if (supportsOuterSystemError(job.command) && systemError?.is_error === true) {
    if (typeof systemError.message === "string" && systemError.message.trim()) {
      return systemError.message.trim();
    }
    return translate("results.summary.instrumentError");
  }
  return job.error || translate("results.summary.failed");
}

function commandErrorSummary(command, result) {
  if (command === "measure-sweep") return measureSweepErrorSummary(result);
  if (command === "single-wait") return triggerWaitErrorSummary(result, false);
  if (command === "capture") return triggerWaitErrorSummary(result?.trigger, true);
  return null;
}

function supportsOuterSystemError(command) {
  return command === "measure" || command === "capture" || command === "capture-batch";
}

function structuredErrorMessage(error) {
  if (typeof error === "string") return error;
  return typeof error?.message === "string" ? error.message : null;
}

function conciseStructuredError(message) {
  if (typeof message !== "string") return null;
  const firstLine = message.trim().split(/\r?\n/, 1)[0].replace(/\s+/g, " ");
  if (!firstLine || /(?:\bVISA\b|\bSCPI\b|\bVI_ERROR_)/i.test(firstLine)) return null;
  return firstLine.length > 160 ? `${firstLine.slice(0, 157)}...` : firstLine;
}

function isTimeoutMessage(message) {
  return typeof message === "string"
    && /timed?\s*out|timeout|VI_ERROR_TMO/i.test(message);
}

function measureSweepErrorSummary(result) {
  if (!Array.isArray(result?.measurements)) return null;
  const failed = result.measurements.find((measurement) => structuredErrorMessage(measurement?.error));
  if (failed) {
    const message = structuredErrorMessage(failed.error);
    const channel = failed.reference_channel === null || failed.reference_channel === undefined
      ? `CH${failed.channel}`
      : `CH${failed.channel}/CH${failed.reference_channel}`;
    const values = { channel, measurement: measurementItemLabel(failed.item) };
    if (isTimeoutMessage(message) || isTimeoutMessage(failed.reason)) {
      return translate("results.summary.measurementTimedOut", values);
    }
    const conciseMessage = conciseStructuredError(message);
    if (conciseMessage) {
      return translate("results.summary.measurementFailedWithReason", {
        ...values,
        message: conciseMessage,
      });
    }
    return translate("results.summary.measurementFailed", values);
  }

  const summary = result.summary;
  if (summary?.invalid_count > 0 && summary?.error_count === 0) {
    return translate("results.summary.measureSweepInvalid", {
      valid: summary.valid_count ?? 0,
      invalid: summary.invalid_count,
    });
  }
  return null;
}

function triggerWaitErrorSummary(trigger, capture) {
  const message = structuredErrorMessage(trigger?.error);
  if (message) {
    return conciseStructuredError(message) || translate("results.summary.triggerWaitFailed");
  }
  if (
    trigger?.outcome === "timeout"
    || trigger?.timed_out === true
    || trigger?.capture_block_reason === "timeout"
  ) {
    return translate(
      capture
        ? "results.summary.captureTriggerTimedOut"
        : "results.summary.triggerWaitTimedOut",
    );
  }
  return null;
}

function successfulJobSummary(job) {
  const result = jobResultPayload(job);
  if (job.command === "identify") return identifySummary(result);
  if (job.command === "list-resources") return resourceSummary(result);
  if (job.command === "screenshot") return translate("results.summary.screenshotCaptured");
  if (job.command === "sequence") {
    return translate("results.summary.sequenceCompleted", {
      completed: result?.completed_step_executions ?? 0,
      total: result?.total_step_executions ?? 0,
      loops: result?.loop_count ?? 0,
      steps: result?.step_count ?? 0,
    });
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

function appendIdentityDetail(container, job) {
  const fields = identityFields(job);
  if (!fields.length) return;

  const detail = document.createElement("dl");
  detail.className = "identity-result";
  fields.forEach(([name, value]) => {
    const label = document.createElement("dt");
    label.textContent = translate(`results.identity.${name}`);
    const content = document.createElement("dd");
    content.textContent = String(value);
    detail.append(label, content);
  });
  container.append(detail);
}

export function renderIdentityWorkspaceResult(container, job) {
  identityFields(job).forEach(([name, value]) => {
    const field = document.createElement("div");
    field.className = `identity-workspace-field${name === "resource" ? " identity-workspace-field-wide" : ""}`;
    const label = document.createElement("small");
    label.textContent = translate(`results.identity.${name}`);
    const content = document.createElement("span");
    content.textContent = String(value);
    field.append(content, label);
    container.append(field);
  });
}

const CHANNEL_SUMMARY_FIELDS = [
  "display",
  "label",
  "scale",
  "range",
  "offset",
  "coupling",
  "impedance",
  "invert",
  "bandwidth_limit",
  "units",
  "vernier",
  "probe_ratio",
  "probe_skew",
];

export function renderWorkspaceResult(container, job, context = {}) {
  if (job.command === "identify") {
    renderIdentityWorkspaceResult(container, job);
    return;
  }
  const result = jobResultPayload(job);
  if (job.command === "channel-summary" && Array.isArray(result?.channels)) {
    renderChannelSummaryWorkspaceResult(container, result.channels);
    return;
  }
  if (job.command === "measure" && isMeasurementResult(result)) {
    renderMeasurementWorkspaceResult(container, result);
    return;
  }
  if (
    job.command === "measure-sweep"
    && context.mode !== "dry-run"
    && Array.isArray(result?.measurements)
  ) {
    renderMeasureSweepWorkspaceResult(container, result);
    return;
  }
  if (result && typeof result === "object") {
    const { display, context: resultContext } = structuredResultDisplay(result);
    const fields = Object.entries(display).filter(([name, value]) => {
      if (isRawDiagnosticField(name)) return false;
      if (
        job.command === "sequence"
        && name === "files"
        && Array.isArray(value)
        && value.length === 0
      ) {
        return false;
      }
      return true;
    });
    if (fields.length) {
      appendWorkspaceFields(container, fields, resultContext);
      return;
    }
  }
  appendWorkspaceFields(container, [
    ["command", commandLabel(job.command)],
    ["execution_mode", context.mode || ""],
    ["summary", successfulJobSummary(job)],
  ]);
}

function channelTitle(channel) {
  const key = `enum.channel${channel}`;
  if (hasTranslation(key)) return translate(key);
  return `${resultFieldLabel("channel")} ${channel}`;
}

function channelUnitSymbol(entry) {
  if (entry?.units === "amp" || entry?.units === "A") return "A";
  if (entry?.units === "volt" || entry?.units === "V") return "V";
  return "";
}

function formatChannelValue(field, value, entry = {}) {
  if (value === null || value === undefined) return "—";
  if (field === "label") {
    return String(value).trim() === "" ? "—" : String(value);
  }
  if (typeof value === "boolean") {
    return translate(value ? "status.enabled" : "status.disabled");
  }
  const unitSymbol = channelUnitSymbol(entry);
  if (field === "scale") {
    return unitSymbol ? `${value} ${unitSymbol}/div` : String(value);
  }
  if (field === "range" || field === "offset") {
    return unitSymbol ? `${value} ${unitSymbol}` : String(value);
  }
  if (field === "coupling") {
    return String(value).toUpperCase();
  }
  if (field === "impedance") {
    if (value === "one_meg") return "1 MΩ";
    if (value === "fifty") return "50 Ω";
    return String(value);
  }
  if (field === "units") {
    if (value === "volt") return "V";
    if (value === "amp") return "A";
    return String(value);
  }
  if (field === "probe_ratio") {
    return String(value).includes(":") ? String(value) : `${value}:1`;
  }
  if (field === "probe_skew") {
    return `${value} s`;
  }
  return String(value);
}

function renderChannelSummaryWorkspaceResult(container, channels) {
  channels.forEach((entry) => {
    const card = document.createElement("div");
    card.className = "workspace-channel-card";

    const title = document.createElement("strong");
    title.className = "workspace-channel-title";
    title.textContent = channelTitle(entry.channel);
    card.append(title);

    const fieldsList = document.createElement("dl");
    fieldsList.className = "workspace-channel-fields";

    const keys = [
      ...CHANNEL_SUMMARY_FIELDS.filter((key) => key in entry && !isRawDiagnosticField(key)),
      ...Object.keys(entry).filter(
        (key) => key !== "channel" && !CHANNEL_SUMMARY_FIELDS.includes(key) && !isRawDiagnosticField(key),
      ),
    ];

    keys.forEach((key) => {
      const dt = document.createElement("dt");
      dt.textContent = channelSummaryFieldLabel(key);
      const dd = document.createElement("dd");
      dd.textContent = formatChannelValue(key, entry[key], entry);
      fieldsList.append(dt, dd);
    });

    card.append(fieldsList);
    container.append(card);
  });
}

function isMeasurementResult(result) {
  return Boolean(
    result
      && typeof result === "object"
      && typeof result.item === "string"
      && Number.isInteger(result.channel)
      && Object.prototype.hasOwnProperty.call(result, "value")
      && Object.prototype.hasOwnProperty.call(result, "valid"),
  );
}

function measurementItemLabel(item) {
  const key = `enum.${item}`;
  return hasTranslation(key) ? translate(key) : String(item);
}

function measurementResultValue(result) {
  if (result.value === null || result.value === undefined) return "";
  return result.unit ? `${result.value} ${result.unit}` : String(result.value);
}

function renderMeasurementWorkspaceResult(container, result) {
  const fields = [
    ["measurement", measurementItemLabel(result.item)],
    ["channel", channelTitle(result.channel)],
  ];
  if (result.reference_channel !== null && result.reference_channel !== undefined) {
    fields.push(["reference_channel", channelTitle(result.reference_channel)]);
  }
  const value = measurementResultValue(result);
  if (value) fields.push(["result", value]);
  appendWorkspaceFields(container, fields);
}

function renderMeasureSweepWorkspaceResult(container, result) {
  const summary = result.summary || {};
  appendWorkspaceFields(container, [
    ["valid_count", summary.valid_count ?? 0],
    ["invalid_count", summary.invalid_count ?? 0],
    ["error_count", summary.error_count ?? 0],
  ]);

  const tableWrap = document.createElement("div");
  tableWrap.className = "workspace-result-table-wrap";
  const table = document.createElement("table");
  table.className = "measurement-results-table";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const name of ["measurement", "channel", "reference_channel", "value", "unit", "status"]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = resultFieldLabel(name);
    headRow.append(cell);
  }
  head.append(headRow);

  const body = document.createElement("tbody");
  for (const record of result.measurements) {
    const hasError = Boolean(record?.error);
    const status = hasError
      ? translate("results.status.error")
      : translate(record?.valid ? "results.status.valid" : "results.status.invalid");
    const values = [
      measurementItemLabel(record?.item),
      record?.channel === null || record?.channel === undefined ? "—" : `CH${record.channel}`,
      record?.reference_channel === null || record?.reference_channel === undefined
        ? "—"
        : `CH${record.reference_channel}`,
      record?.value === null || record?.value === undefined ? "—" : String(record.value),
      record?.unit === null || record?.unit === undefined || record.unit === ""
        ? "—"
        : String(record.unit),
      status,
    ];
    const row = document.createElement("tr");
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    body.append(row);
  }
  table.append(head, body);
  tableWrap.append(table);
  container.append(tableWrap);
}

function channelSummaryFieldLabel(name) {
  const key = `results.channelSummary.field.${name}`;
  return hasTranslation(key) ? translate(key) : resultFieldLabel(name);
}

function structuredResultDisplay(result) {
  const entries = Object.entries(result);
  if (
    entries.length === 1
    && entries[0][1]
    && typeof entries[0][1] === "object"
    && !Array.isArray(entries[0][1])
  ) {
    return { display: entries[0][1], context: entries[0][0] };
  }
  return { display: result, context: null };
}

function appendWorkspaceFields(container, fields, resultContext = null) {
  fields.forEach(([name, value]) => {
    if (value === undefined || value === null || value === "") return;
    const field = document.createElement("div");
    field.className = "workspace-result-field";
    const label = document.createElement("small");
    label.textContent = resultFieldLabel(name);
    const content = document.createElement("span");
    content.textContent = formatWorkspaceValue(name, value, resultContext);
    field.append(content, label);
    container.append(field);
  });
}

function resultFieldLabel(name) {
  const resultKey = `results.field.${name}`;
  if (hasTranslation(resultKey)) return translate(resultKey);
  const fieldKey = `field.${name}`;
  if (hasTranslation(fieldKey)) return translate(fieldKey);
  return String(name).replaceAll("_", " ").replace(/^./, (value) => value.toUpperCase());
}

function isLiteralWorkspaceField(name) {
  return isRawDiagnosticField(name)
    || name === "output"
    || /(^|_)(file|files|filename|filenames|name|label|text|path|paths|resource|resources|model|models|scpi|protocol|protocols|artifact|artifacts|id)$/.test(name)
    || /^(file|path|resource|model|scpi|protocol|artifact)_/.test(name);
}

function isProtocolIdentifier(value) {
  return ["uart", "i2c", "spi", "can", "serial1", "serial2"].includes(value.toLowerCase());
}

function isEnabledWorkspaceField(name) {
  return name === "enabled" || name === "display" || name.endsWith("_enabled");
}

const RESULT_ENUM_CONTEXTS = {
  fft: {
    operation_canonical: "fft-operation",
    gate: "fft-gate",
    phase_reference: "fft-phase-reference",
    detection_type: "fft-detection-type",
  },
  math_transform: { operation: "math-transform" },
  math_filter: { operation: "math-filter" },
  math_visualization: {
    operation: "math-visualization",
    measurement: "math-trend-measurement",
  },
};

function formatWorkspaceValue(name, value, resultContext = null) {
  if (typeof value === "boolean") {
    if (isEnabledWorkspaceField(name)) {
      return translate(value ? "status.enabled" : "status.disabled");
    }
    return translate(value ? "status.yes" : "status.no");
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatWorkspaceValue(name, item, resultContext)).join("; ");
  }
  if (value && typeof value === "object") {
    return Object.entries(value)
      .filter(([name]) => !isRawDiagnosticField(name))
      .map(([itemName, item]) => `${resultFieldLabel(itemName)}: ${formatWorkspaceValue(itemName, item, resultContext)}`)
      .join("; ");
  }
  if (typeof value === "string" && !isLiteralWorkspaceField(name) && !isProtocolIdentifier(value)) {
    if (resultContext === "fft" && name === "operation") return String(value);
    const scopedEnum = RESULT_ENUM_CONTEXTS[resultContext]?.[name];
    const keys = name === "status"
      ? [`results.status.${value}`, `status.${value}`, `enum.${value}`]
      : [scopedEnum ? `enum.${scopedEnum}.${value}` : null, `enum.${value}`].filter(Boolean);
    if (name === "action") keys.push(`actions.${value}`, `command.${value}`);
    const key = keys.find((candidate) => hasTranslation(candidate));
    if (key) return translate(key);
  }
  return String(value);
}

function isRawDiagnosticField(name) {
  return name === "raw" || name.startsWith("raw_") || name.endsWith("_raw");
}

function identityFields(job) {
  const result = jobResultPayload(job);
  const idn = result?.idn || result?.resource?.idn || {};
  return [
    ["manufacturer", idn.manufacturer || idn.vendor],
    ["model", idn.model],
    ["serial", idn.serial],
    ["firmware", idn.firmware],
    ["resource", job.resource || result?.resource?.name],
  ].filter(([_name, value]) => value !== null && value !== undefined && value !== "");
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
  const name = entries[0][0];
  const value = entries[0][1];
  return value !== null && ["string", "number", "boolean"].includes(typeof value)
    ? formatWorkspaceValue(name, value)
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
