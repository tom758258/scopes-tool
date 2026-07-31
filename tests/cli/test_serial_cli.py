import json

import pytest

from scopes_tool_cli import cli
from scopes_tool_core.fake_backend import FakeBackend
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


def _patch_live_scope(monkeypatch, idn: str):
    backend = FakeBackend(
        responses={
            "*IDN?": idn,
            ":SYSTem:ERRor?": '+0,"No error"',
        }
    )
    scope = Oscilloscope(backend)
    monkeypatch.setattr(
        cli.Oscilloscope,
        "open",
        lambda *unused, **kwargs: scope,
    )
    return backend


def test_serial_live_uses_detected_4000x_capabilities_not_planning_model(
    monkeypatch, capsys
):
    backend = _patch_live_scope(
        monkeypatch,
        "KEYSIGHT TECHNOLOGIES,DSOX4034A,MY00000000,02.50",
    )

    assert (
        cli.main(
            [
                "serial-mode",
                "--bus",
                "2",
                "--mode",
                "usb-pd",
                "--resource",
                "FAKE::SCOPE",
                "--model",
                "keysight-dsox2004a",
                "--json",
            ]
        )
        == 0
    )

    payload = _payload(capsys)
    assert payload["ok"] is True
    assert payload["result"]["mode"] == "usb-pd"
    assert backend.history == [
        "*IDN?",
        ":SBUS2:MODE USBPd",
        ":SYSTem:ERRor?",
    ]


def test_serial_live_uses_detected_2000x_capabilities_before_target_scpi(
    monkeypatch, capsys
):
    backend = _patch_live_scope(
        monkeypatch,
        "KEYSIGHT TECHNOLOGIES,DSOX2004A,MY00000000,02.50",
    )

    assert (
        cli.main(
            [
                "serial-query",
                "--bus",
                "2",
                "--resource",
                "FAKE::SCOPE",
                "--json",
            ]
        )
        == 1
    )

    payload = _payload(capsys)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "ParameterValidationError"
    assert backend.history == ["*IDN?"]


@pytest.mark.parametrize(
    "args",
    [
        ["serial-query", "--bus", "2"],
        ["serial-mode", "--bus", "1", "--mode", "usb-pd"],
    ],
)
@pytest.mark.parametrize("run_flags", [["--simulate"], ["--dry-run"]])
def test_serial_2000x_profile_rejection_happens_before_open(
    monkeypatch, capsys, args, run_flags
):
    monkeypatch.setattr(cli, "_open_scope", lambda *unused: pytest.fail("opened scope"))
    assert (
        cli.main(
            [
                *args,
                *run_flags,
                "--json",
                "--model",
                "keysight-dsox2004a",
            ]
        )
        == 1
    )
    assert _payload(capsys)["ok"] is False
