"""Focused checks for the shared Windows bundle specification and entries."""

from pathlib import Path
import runpy
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_spec_collects_three_onedir_entries_with_static_assets_and_metadata(monkeypatch):
    analyses = []

    def analysis(scripts, **kwargs):
        item = SimpleNamespace(
            scripts=scripts, pure=[], binaries=[("runtime.dll",)], datas=kwargs["datas"],
        )
        assert kwargs["pathex"] == [str(ROOT / "src")]
        assert kwargs["hiddenimports"] == ["pyvisa_py"]
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
    hooks.collect_data_files = Mock(side_effect=lambda package, **kwargs: [
        ("cli.html", "scopes_tool_cli/help") if package == "scopes_tool_cli"
        else ("index.html", "scopes_tool_webui/static")
    ])
    for module in (api, build_main, hooks):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    runpy.run_path(
        str(ROOT / "scripts" / "scopes-tool-windows.spec"),
        init_globals={"SPECPATH": str(ROOT / "scripts")},
    )
    assert len(analyses) == api.EXE.call_count == 3
    assert [item.scripts for item in analyses] == [
        [str(ROOT / "src" / "scopes_tool_cli" / "cli.py")],
        [str(ROOT / "src" / "scopes_tool_webui" / "launcher.py")],
        [str(ROOT / "src" / "scopes_tool_webui" / "_desktop_host.py")],
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
    hooks.collect_data_files.assert_any_call("scopes_tool_cli", includes=["help/*"])
    hooks.collect_data_files.assert_any_call("scopes_tool_webui", includes=["static/*", "static/help/*"])
    assert ("cli.html", "scopes_tool_cli/help") in analyses[0].datas
    for item in analyses[1:]:
        assert ("index.html", "scopes_tool_webui/static") in item.datas
    icon_data = (str(ROOT / "desktop" / "assets" / "scopes-icon.ico"), "desktop/assets")
    assert icon_data in analyses[1].datas
    assert icon_data not in analyses[0].datas
    assert icon_data not in analyses[2].datas
    assert api.EXE.call_args_list[1].kwargs["icon"] == icon_data[0]
    api.COLLECT.assert_called_once()
    collect = api.COLLECT.call_args
    assert collect.kwargs["name"] == "scopes-tool"
    assert [exe["name"] for exe in collect.args[:3]] == [
        "scopes-tool", "scopes-tool-webui-launcher", "scopes-tool-webui-host",
    ]
    for item in analyses:
        assert item.binaries in collect.args[3:]
        assert item.datas in collect.args[3:]


def test_pyvisa_py_backend_loads_without_resource_or_network_io(monkeypatch):
    import socket

    import pyvisa

    def unexpected_io(*args, **kwargs):
        pytest.fail("backend import test must not access hardware or the network")

    monkeypatch.setattr(pyvisa, "ResourceManager", unexpected_io)
    for method in ("connect", "connect_ex", "bind", "sendto"):
        monkeypatch.setattr(socket.socket, method, unexpected_io)
    wrapper = pyvisa.highlevel.get_wrapper_class("py")
    from pyvisa_py import PyVisaLibrary, tcpip
    import psutil
    import zeroconf

    assert wrapper is PyVisaLibrary
    assert wrapper.TCPIPInstrSession is tcpip.TCPIPInstrSession
    assert tcpip.psutil is psutil
    assert tcpip.zeroconf is zeroconf
