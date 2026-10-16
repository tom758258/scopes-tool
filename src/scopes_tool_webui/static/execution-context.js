import { pcOutputDirectory } from "/static/pc-output.js";

export function getExecutionContext(elements) {
  const mode = elements.mode.value;
  return {
    mode,
    visa_library: mode === "live" ? elements.visaLibrary?.value || null : null,
    resource: elements.resource.value.trim() || null,
    model_id: mode === "live" ? null : elements.model.value,
    pc_output_dir: pcOutputDirectory(elements.pcOutput),
  };
}

export function buildWorkspaceContext(command, executionContext, liveModelId = null) {
  const mode = executionContext?.mode || "live";
  return {
    command: command || null,
    mode,
    visa_library: mode === "live" ? executionContext?.visa_library || null : null,
    resource: mode === "live" ? executionContext?.resource || null : null,
    detected_model_id: mode === "live" ? liveModelId || null : null,
    planning_model_id: mode === "live" ? null : executionContext?.model_id || null,
  };
}

export function workspaceContextKey(context) {
  return JSON.stringify({
    command: context?.command || null,
    mode: context?.mode || "live",
    visa_library: context?.mode === "live" ? context?.visa_library || null : null,
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
      && (entry.context.visa_library || null) === (context.visa_library || null)
  ))?.job || null;
}
