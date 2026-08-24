import { translate } from "/static/i18n.js";

export const DEFAULT_PC_OUTPUT_DIR = "data";

export function pcOutputDirectory(input) {
  return input ? input.value.trim() : DEFAULT_PC_OUTPUT_DIR;
}

export function pcOutputContext(context, input) {
  return { ...context, pc_output_dir: pcOutputDirectory(input) };
}

export function resetPcOutputDirectory(input) {
  input.value = DEFAULT_PC_OUTPUT_DIR;
}

export function renderPcOutputCommandNote(note, command, input) {
  const visible = command?.pc_output === true;
  note.hidden = !visible;
  note.textContent = visible
    ? translate("pcOutput.commandNote", { path: pcOutputDirectory(input) })
    : "";
}
