"""Small Windows desktop integrations used by the local WebUI."""

from __future__ import annotations

from pathlib import Path
import subprocess


class FolderSelectionUnavailable(RuntimeError):
    """Raised when the native folder selection dialog cannot be opened."""


def select_directory_with_dialog() -> Path | None:
    """Open the Windows folder picker and return its selection, if any."""

    script = (
        "$shell = New-Object -ComObject Shell.Application; "
        "$folder = $shell.BrowseForFolder(0, 'Select PC output folder', 0); "
        "if ($folder -ne $null) { [Console]::Out.Write($folder.Self.Path) }"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:  # pragma: no cover - platform/runtime dependent
        raise FolderSelectionUnavailable(
            "folder selection dialog is unavailable"
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "folder selection dialog is unavailable"
        raise FolderSelectionUnavailable(detail)

    selected = completed.stdout.strip()
    return Path(selected) if selected else None
