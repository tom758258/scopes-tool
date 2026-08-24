"""Small Windows desktop integrations used by the local WebUI."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


class FolderSelectionUnavailable(RuntimeError):
    """Raised when the native folder selection dialog cannot be opened."""


class FolderOpenUnavailable(RuntimeError):
    """Raised when a PC output folder cannot be opened."""


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


def open_directory_in_shell(folder: Path) -> Path:
    """Create a directory when needed and open it with the Windows shell."""

    path = folder.resolve()
    if path.exists() and not path.is_dir():
        raise FolderOpenUnavailable(f"PC output path is not a directory: {path}")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FolderOpenUnavailable(
            f"Could not create PC output folder {path}: {exc}"
        ) from exc

    opener = getattr(os, "startfile", None)
    if opener is None:
        raise FolderOpenUnavailable("folder opening is unavailable on this platform")
    try:
        opener(str(path))
    except OSError as exc:
        raise FolderOpenUnavailable(
            f"Could not open PC output folder {path}: {exc}"
        ) from exc
    return path
