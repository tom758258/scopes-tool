import json

import pytest

from scopes_tool_cli import cli
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_serial_query_simulator_json_preserves_bus_and_raw(capsys):
    assert (
        cli.main(
            [
                "serial-query",
                "--bus",
                "1",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
            ]
        )
        == 0
    )
    result = _payload(capsys)["result"]
    assert result["bus"] == 1
    assert result["raw"] == ":SBUS1:DISP 0;MODE UART;"


def test_serial_simulator_mode_and_display_round_trip():
    backend = SimulatorBackend(physical_model_id="keysight-dsox4034a")
    scope = Oscilloscope(backend)
    scope.query_idn()

    scope.configure_serial_mode(2, "usb-pd")
    assert scope.query_serial_mode(2).to_json() == {
        "bus": 2,
        "mode": "usb-pd",
        "raw_mode": "USBPd",
    }
    scope.configure_serial_display(2, True)
    assert scope.query_serial_display(2).to_json() == {
        "bus": 2,
        "enabled": True,
        "raw_state": "1",
    }
    scope.configure_serial_display(2, False)
    assert scope.query_serial_display(2).enabled is False


@pytest.mark.parametrize(
    "args",
    [
        ["serial-query", "--bus", "2"],
        ["serial-mode", "--bus", "1", "--mode", "usb-pd"],
    ],
)
def test_serial_2000x_profile_rejection_happens_before_open(
    monkeypatch, capsys, args
):
    monkeypatch.setattr(cli, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    assert (
        cli.main(
            [
                *args,
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
            ]
        )
        == 1
    )
    assert _payload(capsys)["ok"] is False
