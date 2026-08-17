export function getExecutionContext(elements) {
  const mode = elements.mode.value;
  return {
    mode,
    resource: elements.resource.value.trim() || null,
    model_id: elements.model.value,
  };
}
