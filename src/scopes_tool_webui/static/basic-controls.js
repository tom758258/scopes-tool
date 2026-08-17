export function bindBasicControls(container, execute, available) {
  container.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-command]");
    if (button) execute(button.dataset.command, {});
  });
  const update = () => container.querySelectorAll("button[data-command]").forEach((button) => {
    button.disabled = !available(button.dataset.command);
  });
  update();
  return update;
}
