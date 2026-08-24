import { DEFAULT_PC_OUTPUT_DIR } from "/static/pc-output.js";

export function createInitialState() {
  return {
    executionContext: {
      mode: "live", resource: null, model_id: null, pc_output_dir: DEFAULT_PC_OUTPUT_DIR,
    },
    selectedCommand: null,
    workspaceResults: new Map(),
  };
}
