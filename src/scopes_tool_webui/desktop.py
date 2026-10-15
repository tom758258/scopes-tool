"""Small Windows desktop integrations used by the local WebUI."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import threading


class FolderSelectionUnavailable(RuntimeError):
    """Raised when the native folder selection dialog cannot be opened."""


class FolderOpenUnavailable(RuntimeError):
    """Raised when a PC output folder cannot be opened."""


_FOLDER_PICKER_LOCK = threading.Lock()


def _is_windows() -> bool:
    return sys.platform == "win32"


def _ask_directory(title: str) -> str:
    """Show a native picker owned by an invisible, topmost Tk window."""
    import tkinter as tk
    from tkinter import filedialog

    owner = tk.Tk()
    try:
        # A mapped owner (rather than a withdrawn root) makes the native
        # dialog topmost and keeps it above the browser that requested it.
        # The transparent, borderless owner does not appear on the taskbar.
        owner.withdraw()
        owner.overrideredirect(True)
        owner.attributes("-alpha", 0.0)
        owner.attributes("-topmost", True)
        owner.geometry(
            f"1x1+{owner.winfo_screenwidth() // 2}+{owner.winfo_screenheight() // 2}"
        )
        owner.deiconify()
        owner.update()
        owner.lift()
        owner.focus_force()
        return filedialog.askdirectory(parent=owner, title=title, mustexist=True)
    finally:
        owner.destroy()


def select_directory_with_dialog() -> Path | None:
    """Select a Windows folder without spawning PowerShell or a console."""
    if not _is_windows():
        raise FolderSelectionUnavailable("folder selection dialog is unavailable")
    if not _FOLDER_PICKER_LOCK.acquire(blocking=False):
        raise FolderSelectionUnavailable("folder selection dialog is already open")
    try:
        try:
            selected = _ask_directory("Select PC output folder")
        except Exception as exc:  # pragma: no cover - native GUI/runtime dependent
            raise FolderSelectionUnavailable("folder selection dialog is unavailable") from exc
    finally:
        _FOLDER_PICKER_LOCK.release()
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
