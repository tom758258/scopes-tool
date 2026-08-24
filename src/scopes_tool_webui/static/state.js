export function createInitialState() {
  return {
    executionContext: { mode: "live", resource: null, model_id: null, pc_output_dir: "data" },
    selectedCommand: null,
    workspaceResults: new Map(),
  };
}
