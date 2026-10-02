from __future__ import annotations

from types import SimpleNamespace

import pytest

from scopes_tool_cli import dispatch
from scopes_tool_core.errors import OscilloscopeError


@pytest.mark.parametrize(
    ("command", "module_name", "handler_name"),
    [
        ("system-opc", "system", "_cmd_system_status"),
        ("channel-impedance", "channel_display", "_cmd_channel_advanced_setting"),
        ("display-intensity", "channel_display", "_cmd_display_common"),
        ("measure-source", "measurement_analysis", "_cmd_measurement_control"),
        ("dvm-query", "measurement_analysis", "_cmd_dvm"),
        ("demo-phase", "measurement_analysis", "_cmd_demo"),
        ("wgen-frequency", "measurement_analysis", "_cmd_wgen"),
        ("serial-spi-show", "serial", "_cmd_serial"),
        ("serial-search-spi", "trigger_search", "_cmd_search"),
        ("save-waveform", "workflows", "_cmd_save_export"),
        ("reference-label", "measurement_analysis", "_cmd_reference_waveform"),
        ("external-trigger-units", "trigger_search", "_cmd_external_trigger_input"),
        ("trigger-edge-reject", "trigger_search", "_cmd_trigger_common"),
    ],
)
def test_grouped_commands_keep_existing_dispatch_routes(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    module_name: str,
    handler_name: str,
) -> None:
    module = getattr(dispatch, module_name)
    calls: list[str] = []

    def fake_handler(args) -> int:  # type: ignore[no-untyped-def]
        calls.append(args.command)
        return 37

    monkeypatch.setattr(module, handler_name, fake_handler)
    args = SimpleNamespace(command=command)

    assert dispatch._dispatch_command(args) == 37
    assert calls == [command]


def test_unknown_command_still_raises_missing_command() -> None:
    with pytest.raises(OscilloscopeError, match="missing command"):
        dispatch._dispatch_command(SimpleNamespace(command="not-a-command"))
