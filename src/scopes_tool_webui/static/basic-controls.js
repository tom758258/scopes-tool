export function bindBasicControls(container, execute) {
  container.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-command]");
    if (button) execute(button.dataset.command, {});
  });
}
