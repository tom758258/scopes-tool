# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_data_files, copy_metadata


REPO_ROOT = Path(SPECPATH).resolve().parent
SRC_ROOT = REPO_ROOT / "src"
SCOPES_ICON = REPO_ROOT / "desktop" / "assets" / "scopes-icon.ico"
METADATA = [
    *copy_metadata("scopes-tool", recursive=True),
    *copy_metadata("fastapi", recursive=True),
    *copy_metadata("uvicorn", recursive=True),
]
WEBUI_STATIC = collect_data_files("scopes_tool_webui", includes=["static/*"])

cli_analysis = Analysis(
    [str(REPO_ROOT / "scripts" / "windows_cli_entry.py")],
    pathex=[str(SRC_ROOT)],
    datas=METADATA,
)
launcher_analysis = Analysis(
    [str(REPO_ROOT / "scripts" / "windows_launcher_entry.py")],
    pathex=[str(SRC_ROOT)],
    datas=[*METADATA, *WEBUI_STATIC],
)
host_analysis = Analysis(
    [str(REPO_ROOT / "scripts" / "windows_host_entry.py")],
    pathex=[str(SRC_ROOT)],
    datas=[*METADATA, *WEBUI_STATIC],
)

cli_exe = EXE(
    PYZ(cli_analysis.pure),
    cli_analysis.scripts,
    exclude_binaries=True,
    name="scopes-tool",
    console=True,
    contents_directory="_internal",
    icon=str(SCOPES_ICON),
)
launcher_exe = EXE(
    PYZ(launcher_analysis.pure),
    launcher_analysis.scripts,
    exclude_binaries=True,
    name="scopes-tool-webui-launcher",
    console=False,
    contents_directory="_internal",
    icon=str(SCOPES_ICON),
)
host_exe = EXE(
    PYZ(host_analysis.pure),
    host_analysis.scripts,
    exclude_binaries=True,
    name="scopes-tool-webui-host",
    console=True,
    contents_directory="_internal",
)

COLLECT(
    cli_exe,
    launcher_exe,
    host_exe,
    cli_analysis.binaries,
    cli_analysis.datas,
    launcher_analysis.binaries,
    launcher_analysis.datas,
    host_analysis.binaries,
    host_analysis.datas,
    name="scopes-tool",
)
