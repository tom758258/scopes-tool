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


def test_serial_uart_trigger_simulator_json_configure_preserves_readback_and_order(
    capsys,
):
    assert (
        cli.main(
            [
                "serial-trigger-uart",
                "--bus",
                "1",
                "--type",
                "rx-data",
                "--data",
                "85",
                "--qualifier",
                "equal",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
            ]
        )
        == 0
    )
    payload = _payload(capsys)
    result = payload["result"]
    assert result["protocol"] == "uart"
    assert result["type"] == "rx-data"
    assert result["raw_type"] == "RDAT"
    assert result["data"] == 85
    assert result["qualifier"] == "equal"
    assert result["selected"] is True
    sent = payload["scpi"]["sent"]
    assert sent.index(":TRIGger:MODE SBUS1") > sent.index(
        ":SBUS1:UART:TRIGger:QUALifier EQUal"
    )
    assert result["commands"][-5:] == [
        ":TRIGger:MODE SBUS1",
        ":TRIGger:MODE?",
        ":SBUS1:UART:TRIGger:TYPE?",
        ":SBUS1:UART:TRIGger:DATA?",
        ":SBUS1:UART:TRIGger:QUALifier?",
    ]


def test_serial_uart_trigger_rejects_non_data_qualifier_before_backend_open(
    monkeypatch, capsys
):
    opened = False

    def fail_open(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("backend must not open")

    monkeypatch.setattr(cli, "_open_scope", fail_open)
    assert (
        cli.main(
            [
                "serial-trigger-uart",
                "--bus",
                "1",
                "--type",
                "rx-start",
                "--data",
                "1",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
            ]
        )
        == 1
    )
    payload = _payload(capsys)
    assert payload["error"]["type"] == "ParameterValidationError"
    assert not opened
    assert payload["scpi"]["sent"] == []


def test_serial_lister_query_simulator_json_does_not_query_data(capsys):
    assert (
        cli.main(
            [
                "serial-lister-query",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
            ]
        )
        == 0
    )
    payload = _payload(capsys)
    assert payload["result"]["display"] == "off"
    assert payload["result"]["reference"] == "trigger"
    assert payload["result"]["commands"] == [
        ":LISTer:DISPlay?",
        ":LISTer:REFerence?",
    ]
    assert ":LISTer:DATA?" not in payload["scpi"]["sent"]


def test_serial_lister_display_simulator_configure(capsys):
    assert (
        cli.main(
            [
                "serial-lister-display",
                "--selection",
                "all",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
            ]
        )
        == 0
    )
    payload = _payload(capsys)
    assert payload["result"]["display"] == "all"
    assert payload["result"]["command"] == ":LISTer:DISPlay ALL"


def test_serial_lister_reference_simulator_configure(capsys):
    assert (
        cli.main(
            [
                "serial-lister-reference",
                "--reference",
                "previous",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
            ]
        )
        == 0
    )
    payload = _payload(capsys)
    assert payload["result"]["reference"] == "previous"
    assert payload["result"]["command"] == ":LISTer:REFerence PREVious"


def test_serial_lister_export_simulator_preserves_file_and_metadata(tmp_path, capsys):
    output = tmp_path / "lister.csv"
    assert (
        cli.main(
            [
                "serial-lister-export",
                "--output",
                str(output),
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
            ]
        )
        == 0
    )
    payload = _payload(capsys)
    expected = b"bus,time,value\r\nSBUS1,0,0\r\n"
    assert output.read_bytes() == expected
    assert payload["result"]["bytes_written"] == len(expected)
    assert payload["result"]["command"] == ":LISTer:DATA?"
    assert payload["files"] == [{"kind": "csv", "path": str(output)}]
    assert payload["scpi"]["sent"].count(":LISTer:DATA?") == 1
    assert "bus,time,value" not in json.dumps(payload)


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
    "command, options, field, expected",
    [
        ("serial-uart", ["--rx-source", "channel1", "--baud-rate", "115200"], "rx_source", "channel1"),
        ("serial-i2c", ["--clock-source", "external"], "clock_source", "external"),
        ("serial-spi", ["--framing", "timeout"], "framing", "timeout"),
        ("serial-can", ["--signal-definition", "difl"], "signal_definition", "difl"),
    ],
)
def test_serial_protocol_simulator_configure_json(command, options, field, expected, capsys):
    assert (
        cli.main(
            [
                command,
                "--bus",
                "1",
                *options,
                "--simulate",
                "--model",
                "keysight-dsox4034a",
                "--json",
            ]
        )
        == 0
    )
    result = _payload(capsys)["result"]
    assert result[field] == expected
    assert result["commands"][0].startswith(":SBUS1:MODE ")


def test_serial_protocol_query_parser_and_json(capsys):
    parser = cli._build_parser()
    parsed = parser.parse_args(["serial-can", "--bus", "1", "--query"])
    assert parsed.command == "serial-can"
    assert (
        cli.main(
            [
                "serial-uart",
                "--bus",
                "1",
                "--query",
                "--simulate",
                "--model",
                "keysight-dsox4034a",
                "--json",
            ]
        )
        == 0
    )
    result = _payload(capsys)["result"]
    assert result["mode"] == "uart"
    assert result["raw_mode"] == "UART"


def test_serial_cli_rejects_noncanonical_source_before_serial_scpi(capsys):
    assert (
        cli.main(
            [
                "serial-uart",
                "--bus",
                "1",
                "--rx-source",
                "CHANnel1",
                "--simulate",
                "--model",
                "keysight-dsox4034a",
                "--json",
            ]
        )
        == 1
    )
    payload = _payload(capsys)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "ParameterValidationError"
    assert payload["scpi"]["sent"] == []


def test_serial_spi_rejects_incompatible_framing_and_clock_timeout(capsys):
    assert (
        cli.main(
            [
                "serial-spi",
                "--bus",
                "1",
                "--framing",
                "chip-select",
                "--clock-timeout",
                "1e-6",
                "--simulate",
                "--model",
                "keysight-dsox4034a",
                "--json",
            ]
        )
        == 1
    )
    payload = _payload(capsys)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "ParameterValidationError"
    assert "framing is explicitly set to timeout" in payload["error"]["message"]
    assert payload["scpi"]["sent"] == []
    assert not any(command.startswith(":SBUS") for command in payload["scpi"]["sent"])


def test_serial_spi_live_rejects_before_serial_scpi(monkeypatch, capsys):
    backend = _patch_live_scope(
        monkeypatch,
        "KEYSIGHT TECHNOLOGIES,DSOX4034A,MY00000000,02.50",
    )

    assert (
        cli.main(
            [
                "serial-spi",
                "--bus",
                "2",
                "--framing",
                "no-chip-select",
                "--clock-timeout",
                "1e-6",
                "--resource",
                "FAKE::SCOPE",
                "--model",
                "keysight-dsox2004a",
                "--json",
            ]
        )
        == 1
    )

    payload = _payload(capsys)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "ParameterValidationError"
    assert backend.history == ["*IDN?"]
    assert not any(command.startswith(":SBUS") for command in backend.history)


def test_serial_spi_help_describes_timeout_framing_and_source_availability(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["serial-spi", "--help"])

    assert exc_info.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "--framing timeout" in help_text
    assert "chip-select, no-chip-select, or timeout" in help_text
    assert "source availability may depend on the other configured Serial bus" in help_text


def test_serial_settings_conflict_hint_preserves_system_error_json(
    monkeypatch, capsys
):
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4034A,MY00000000,02.50",
            ":SYSTem:ERRor?": '-221,"Settings conflict"',
        }
    )
    scope = Oscilloscope(backend)
    monkeypatch.setattr(cli.Oscilloscope, "open", lambda *unused, **kwargs: scope)

    assert (
        cli.main(
            [
                "serial-uart",
                "--bus",
                "2",
                "--rx-source",
                "channel3",
                "--resource",
                "FAKE::SCOPE",
                "--json",
            ]
        )
        == 1
    )

    payload = _payload(capsys)
    assert payload["system_error"] == {
        "code": -221,
        "message": "Settings conflict",
        "raw": '-221,"Settings conflict"',
        "is_error": True,
    }
    human_output = "\n".join(payload["result"]["human_output"])
    assert "Requested Serial settings conflict with current instrument state." in human_output
    assert "Query both Serial buses." in human_output
    assert "other bus already uses the requested analog channels or protocol resources." in human_output


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
