export function createInitialState() {
  return {
    executionContext: { mode: "live", resource: null, model_id: null },
    selectedCommand: null,
    workspaceResults: new Map(),
  };
}
