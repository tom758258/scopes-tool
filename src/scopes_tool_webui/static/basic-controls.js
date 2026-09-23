export function bindBasicControls(container, execute, available) {
  container.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-command]");
    if (!button) return;
    const parameters = button.dataset.command === "screenshot" && button.dataset.background
      ? { background: button.dataset.background }
      : {};
    execute(button.dataset.command, parameters);
  });
  const update = () => container.querySelectorAll("button[data-command]").forEach((button) => {
    button.disabled = !available(button.dataset.command);
  });
  update();
  return update;
}
