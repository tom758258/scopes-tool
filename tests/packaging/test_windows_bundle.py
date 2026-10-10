"""Focused checks for the shared Windows bundle specification and entries."""

from pathlib import Path
import runpy
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("entry", "module"),
    [
        ("cli", "scopes_tool_cli.cli"),
        ("launcher", "scopes_tool_webui.launcher"),
        ("host", "scopes_tool_webui._desktop_host"),
    ],
)
def test_frozen_entry_calls_existing_main_and_preserves_exit_code(monkeypatch, entry, module):
    stub = ModuleType(module)
    stub.main = Mock(return_value=7)
    monkeypatch.setitem(sys.modules, module, stub)
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(ROOT / "scripts" / f"windows_{entry}_entry.py"), run_name="__main__")
    assert result.value.code == 7
    stub.main.assert_called_once_with()


def test_spec_collects_three_onedir_entries_with_static_assets_and_metadata(monkeypatch):
    analyses = []

    def analysis(scripts, **kwargs):
        item = SimpleNamespace(
            scripts=scripts, pure=[], binaries=[("runtime.dll",)], datas=kwargs["datas"],
        )
        assert kwargs["pathex"] == [str(ROOT / "src")]
        analyses.append(item)
        return item

    api = ModuleType("PyInstaller.building.api")
    api.EXE = Mock(side_effect=lambda *args, **kwargs: kwargs)
    api.PYZ = Mock(return_value="pyz")
    api.COLLECT = Mock()
    build_main = ModuleType("PyInstaller.building.build_main")
    build_main.Analysis = analysis
    hooks = ModuleType("PyInstaller.utils.hooks")
    hooks.copy_metadata = Mock(side_effect=lambda name, **kwargs: [(name, "metadata")])
    hooks.collect_data_files = Mock(return_value=[("index.html", "scopes_tool_webui/static")])
    for module in (api, build_main, hooks):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    runpy.run_path(
        str(ROOT / "scripts" / "scopes-tool-windows.spec"),
        init_globals={"SPECPATH": str(ROOT / "scripts")},
    )
    assert len(analyses) == api.EXE.call_count == api.PYZ.call_count == 3
    assert [Path(item.scripts[0]).name for item in analyses] == [
        "windows_cli_entry.py", "windows_launcher_entry.py", "windows_host_entry.py",
    ]
    assert [call.kwargs["name"] for call in api.EXE.call_args_list] == [
        "scopes-tool", "scopes-tool-webui-launcher", "scopes-tool-webui-host",
    ]
    assert [call.kwargs["console"] for call in api.EXE.call_args_list] == [True, False, True]
    for call in api.EXE.call_args_list:
        assert call.kwargs["exclude_binaries"] is True
        assert call.kwargs["contents_directory"] == "_internal"
    hooks.copy_metadata.assert_any_call("scopes-tool", recursive=True)
    hooks.copy_metadata.assert_any_call("fastapi", recursive=True)
    hooks.copy_metadata.assert_any_call("uvicorn", recursive=True)
    hooks.collect_data_files.assert_called_once_with("scopes_tool_webui", includes=["static/*"])
    for item in analyses[1:]:
        assert ("index.html", "scopes_tool_webui/static") in item.datas
    api.COLLECT.assert_called_once()
    collect = api.COLLECT.call_args
    assert collect.kwargs == {"name": "scopes-tool"}
    assert [exe["name"] for exe in collect.args[:3]] == [
        "scopes-tool", "scopes-tool-webui-launcher", "scopes-tool-webui-host",
    ]
    for item in analyses:
        assert item.binaries in collect.args[3:]
        assert item.datas in collect.args[3:]
