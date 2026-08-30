import { translate } from "/static/i18n.js";

export function modelPresentation(command, modelId) {
  return command?.presentation?.models?.[modelId] || null;
}

export function commandSupported(command, modelId) {
  const presentation = modelPresentation(command, modelId);
  return presentation ? presentation.supported !== false : true;
}

export function commandSupportReason(command, modelId, modelLabel = modelId) {
  return commandSupported(command, modelId)
    ? ""
    : translate("support.commandUnavailable", { model: modelLabel || modelId || "" });
}

export function fieldsForModel(command, modelId) {
  const overrides = modelPresentation(command, modelId)?.fields || {};
  return (command?.fields || []).filter((field) => !overrides[field.name]?.hidden).map((field) => ({
    ...field,
    ...(overrides[field.name] || {}),
  }));
}
