export function getExecutionContext(elements) {
  const mode = elements.mode.value;
  return {
    mode,
    resource: elements.resource.value.trim() || null,
    model_id: mode === "live" ? null : elements.model.value,
    pc_output_dir: elements.pcOutput?.value.trim() ?? "data",
  };
}

export function buildWorkspaceContext(command, executionContext, liveModelId = null) {
  const mode = executionContext?.mode || "live";
  return {
    command: command || null,
    mode,
    resource: mode === "live" ? executionContext?.resource || null : null,
    detected_model_id: mode === "live" ? liveModelId || null : null,
    planning_model_id: mode === "live" ? null : executionContext?.model_id || null,
  };
}

export function workspaceContextKey(context) {
  return JSON.stringify({
    command: context?.command || null,
    mode: context?.mode || "live",
    resource: context?.resource || null,
    detected_model_id: context?.detected_model_id || null,
    planning_model_id: context?.planning_model_id || null,
  });
}

export function sameWorkspaceContext(left, right) {
  return workspaceContextKey(left) === workspaceContextKey(right);
}

export function workspaceContextForCompletedJob(job, submittedContext) {
  const idn = job?.result?.result?.idn || job?.result?.idn;
  if (submittedContext?.mode !== "live" || !idn?.model_id) return submittedContext;
  return { ...submittedContext, detected_model_id: idn.model_id };
}

export function findWorkspaceResult(results, context, allowResourceFallback = false) {
  const exact = results.get(workspaceContextKey(context));
  if (exact || !allowResourceFallback || context?.mode !== "live" || !context?.resource) {
    return exact?.job || null;
  }
  const entries = [...results.values()].reverse();
  return entries.find((entry) => (
    entry.context.command === context.command
      && entry.context.mode === "live"
      && entry.context.resource === context.resource
  ))?.job || null;
}
