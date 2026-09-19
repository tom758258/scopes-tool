import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from scopes_tool_cli import cli
from scopes_tool_cli import parser as cli_parser, runtime
from scopes_tool_cli.commands import serial
from tests.cli.support import install_scope
from scopes_tool_core.fake_backend import FakeBackend
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import SimulatorBackend


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_serial_status_simulator_json_locks_aggregate_shape(capsys):
    assert (
        cli.main(
            [
                "serial-status",
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
    payload = _payload(capsys)
    result = payload["result"]
    assert result["operation"] == "status"
    assert result["bus"] == 1
    assert result["mode"] == "uart"
    assert result["raw_mode"] == "UART"
    assert result["display"] is False
    assert result["protocol"] == "uart"
    assert result["config"]["baud_rate"] == 115200
    assert result["config"]["rx_source"] == "channel1"
    assert "bus" not in result["config"]
    assert "mode" not in result["config"]
    expected_commands = [
        ":SBUS1:MODE?",
        ":SBUS1:DISPlay?",
        ":SBUS1:MODE?",
        ":SBUS1:UART:SOURce:RX?",
        ":SBUS1:UART:SOURce:TX?",
        ":SBUS1:UART:BAUDrate?",
        ":SBUS1:UART:WIDTh?",
        ":SBUS1:UART:PARity?",
        ":SBUS1:UART:POLarity?",
        ":SBUS1:UART:BITorder?",
    ]
    assert result["commands"] == expected_commands
    sent_serial = [
        command
        for command in payload["scpi"]["sent"]
        if command.startswith(":SBUS")
    ]
    assert sent_serial == expected_commands


def test_serial_status_unsupported_protocol_mode_reports_null_config(
    monkeypatch, capsys
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox4034a")
    backend.serial_modes[1] = "USBPd"
    scope = Oscilloscope(backend)
    monkeypatch.setattr(runtime, "_open_scope", lambda args, resource: nullcontext(scope))

    assert (
        cli.main(
            [
                "serial-status",
                "--bus",
                "1",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4034a",
            ]
        )
        == 0
    )
    payload = _payload(capsys)
    result = payload["result"]
    assert result["operation"] == "status"
    assert result["mode"] == "usb-pd"
    assert result["raw_mode"] == "USBPd"
    assert result["protocol"] is None
    assert result["config"] is None
    assert result["commands"] == [":SBUS1:MODE?", ":SBUS1:DISPlay?"]
    sent_serial = [
        command for command in backend.history if command.startswith(":SBUS")
    ]
    assert sent_serial == [":SBUS1:MODE?", ":SBUS1:DISPlay?"]
    assert not any(
        command.startswith(
            (":SBUS1:UART", ":SBUS1:IIC", ":SBUS1:SPI", ":SBUS1:CAN")
        )
        for command in sent_serial
    )


def test_serial_status_fails_closed_when_display_query_fails(monkeypatch, capsys):
    backend = FakeBackend(
        responses={
            "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4034A,MY00000000,02.50",
            ":SBUS1:MODE?": "UART",
            ":SYSTem:ERRor?": '+0,"No error"',
        }
    )
    scope = Oscilloscope(backend)
    install_scope(monkeypatch, scope)

    assert (
        cli.main(
            [
                "serial-status",
                "--bus",
                "1",
                "--resource",
                "FAKE::SCOPE",
                "--json",
            ]
        )
        == 1
    )
    payload = _payload(capsys)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "FakeBackendError"
    assert backend.history == ["*IDN?", ":SBUS1:MODE?", ":SBUS1:DISPlay?"]
    assert not any(
        command.startswith(":SBUS1:UART") for command in backend.history
    )


def test_serial_uart_trigger_simulator_json_configure_preserves_readback_and_order(
    capsys,
):
    assert (
        cli.main(
            [
                "serial-trigger-uart-set",
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

    monkeypatch.setattr(runtime, "_open_scope", fail_open)
    assert (
        cli.main(
            [
                "serial-trigger-uart-set",
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


def test_serial_uart_trigger_query_dry_run_plans_only_unconditional_queries(capsys):
    assert (
        cli.main(
            [
                "serial-trigger-uart-show",
                "--bus",
                "1",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox2004a",
            ]
        )
        == 0
    )
    result = _payload(capsys)["result"]
    assert result["operation"] == "query"
    assert result["protocol"] == "uart"
    assert result["bus"] == 1
    assert result["commands"] == [":SBUS1:MODE?", ":TRIGger:MODE?"]
    assert ":SBUS1:UART:TRIGger:TYPE?" not in result["commands"]
    assert ":SBUS1:UART:TRIGger:DATA?" not in result["commands"]
    assert ":SBUS1:UART:TRIGger:QUALifier?" not in result["commands"]


@pytest.mark.parametrize(
    "command, show_command, mode, configure_args, protocol",
    [
        (
            "serial-trigger-i2c-set",
            "serial-trigger-i2c-show",
            "IIC",
            ["--type", "read-eeprom", "--address", "0x50", "--data", "0x10", "--qualifier", "greater-than"],
            "i2c",
        ),
        (
            "serial-trigger-spi-set",
            "serial-trigger-spi-show",
            "SPI",
            ["--type", "mosi", "--width", "8", "--data", "1010XX01"],
            "spi",
        ),
        (
            "serial-trigger-can-set",
            "serial-trigger-can-show",
            "CAN",
            ["--type", "id-and-data", "--id", "0x1", "--id-mode", "standard", "--data", "1010XX01", "--data-length", "1"],
            "can",
        ),
    ],
)
def test_serial_trigger_simulator_configure_query_roundtrip(
    monkeypatch, capsys, command, show_command, mode, configure_args, protocol
):
    backend = SimulatorBackend(physical_model_id="keysight-dsox2004a")
    backend.serial_modes[1] = mode
    scope = Oscilloscope(backend)
    monkeypatch.setattr(runtime, "_open_scope", lambda args, resource: nullcontext(scope))

    common = [command, "--bus", "1", "--simulate", "--json", "--model", "keysight-dsox2004a"]
    assert cli.main([*common, *configure_args]) == 0
    configured = _payload(capsys)["result"]
    assert configured["protocol"] == protocol
    assert configured["state_changing"] is True
    assert configured["selected"] is True
    if protocol == "i2c":
        assert configured["qualifier"] == "greater-than"
        assert configured["raw_qualifier"] == "GRE"

    assert cli.main([show_command, "--bus", "1", "--simulate", "--json", "--model", "keysight-dsox2004a"]) == 0
    queried = _payload(capsys)["result"]
    assert queried["protocol"] == protocol
    assert queried["selected"] is True
    if protocol == "i2c":
        assert queried["qualifier"] == "greater-than"
        assert queried["raw_qualifier"] == "GRE"


@pytest.mark.parametrize(
    "command, protocol_specific",
    [
        ("serial-trigger-i2c-show", ":SBUS1:IIC:TRIGger:TYPE?"),
        ("serial-trigger-spi-show", ":SBUS1:SPI:TRIGger:TYPE?"),
        ("serial-trigger-can-show", ":SBUS1:CAN:TRIGger?"),
    ],
)
def test_serial_trigger_query_dry_run_plans_only_unconditional_queries(
    capsys, command, protocol_specific
):
    assert cli.main(
        [
            command,
            "--bus",
            "1",
            "--dry-run",
            "--json",
            "--model",
            "keysight-dsox2004a",
        ]
    ) == 0
    result = _payload(capsys)["result"]
    assert result["operation"] == "query"
    assert result["commands"] == [":SBUS1:MODE?", ":TRIGger:MODE?"]
    assert protocol_specific not in result["commands"]


def test_serial_lister_status_simulator_json_does_not_query_data(capsys):
    assert (
        cli.main(
            [
                "serial-lister-status",
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


def test_serial_data_simulator_preserves_file_and_metadata(tmp_path, capsys):
    output = tmp_path / "lister.csv"
    assert (
        cli.main(
            [
                "serial-data",
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


def test_serial_data_simulator_uses_default_output(
    tmp_path, capsys, monkeypatch
):
    default_output = Path("data/2026-08-24-15-35-10-lister.csv")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        serial,
        "default_capture_csv_path",
        lambda: Path("data/2026-08-24-15-35-10.csv"),
    )

    assert (
        cli.main(
            [
                "serial-data",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
            ]
        )
        == 0
    )

    payload = _payload(capsys)
    assert (tmp_path / default_output).is_file()
    assert payload["result"]["output_path"] == str(default_output)
    assert payload["files"] == [{"kind": "csv", "path": str(default_output)}]


def test_serial_data_dry_run_uses_default_output_without_writing(
    tmp_path, capsys, monkeypatch
):
    default_output = Path("data/2026-08-24-15-35-10-lister.csv")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        serial,
        "default_capture_csv_path",
        lambda: Path("data/2026-08-24-15-35-10.csv"),
    )

    assert cli.main(["serial-data", "--dry-run", "--json"]) == 0

    payload = _payload(capsys)
    assert not (tmp_path / "data").exists()
    assert payload["result"]["output_path"] == str(default_output)
    assert payload["files"] == [{"kind": "csv", "path": str(default_output)}]


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
        ("serial-uart-set", ["--rx-source", "channel1", "--baud-rate", "115200"], "rx_source", "channel1"),
        ("serial-i2c-set", ["--clock-source", "external"], "clock_source", "external"),
        ("serial-spi-set", ["--framing", "timeout"], "framing", "timeout"),
        ("serial-can-set", ["--signal-definition", "difl"], "signal_definition", "difl"),
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


def test_serial_protocol_show_parser_and_json(capsys):
    parser = cli_parser._build_parser()
    parsed = parser.parse_args(["serial-can-show", "--bus", "1"])
    assert parsed.command == "serial-can-show"
    assert (
        cli.main(
            [
                "serial-uart-show",
                "--bus",
                "1",
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
                "serial-uart-set",
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
                "serial-spi-set",
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
                "serial-spi-set",
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
        cli.main(["serial-spi-set", "--help"])

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
    monkeypatch.setattr(runtime.Oscilloscope, "open", lambda *unused, **kwargs: scope)

    assert (
        cli.main(
            [
                "serial-uart-set",
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
    install_scope(monkeypatch, scope)
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
                "serial-status",
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
        ["serial-status", "--bus", "2"],
        ["serial-mode", "--bus", "1", "--mode", "usb-pd"],
    ],
)
@pytest.mark.parametrize("run_flags", [["--simulate"], ["--dry-run"]])
def test_serial_2000x_profile_rejection_happens_before_open(
    monkeypatch, capsys, args, run_flags
):
    monkeypatch.setattr(runtime, "_open_scope", lambda *unused: pytest.fail("opened scope"))
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


def test_serial_enable_simulator_json_configures_display(capsys):
    assert (
        cli.main(
            [
                "serial-enable",
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
    assert result["operation"] == "configure"
    assert result["enabled"] is True
    assert result["command"] == ":SBUS1:DISPlay 1"


def test_serial_uart_set_rejects_missing_settings_before_backend_open(
    monkeypatch, capsys
):
    opened = False

    def fail_open(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("backend must not open")

    monkeypatch.setattr(runtime, "_open_scope", fail_open)
    assert (
        cli.main(
            [
                "serial-uart-set",
                "--bus",
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


@pytest.mark.parametrize(
    "argv, accepted",
    [
        (["serial-status", "--bus", "1"], True),
        (["serial-mode", "--bus", "1", "--mode", "uart"], True),
        (["serial-mode", "--bus", "1", "--query"], True),
        (["serial-enable", "--bus", "1"], True),
        (["serial-disable", "--bus", "1"], True),
        (["serial-uart-set", "--bus", "1", "--baud-rate", "115200"], True),
        (["serial-uart-show", "--bus", "1"], True),
        (["serial-i2c-set", "--bus", "1", "--address-size", "bit7"], True),
        (["serial-i2c-show", "--bus", "1"], True),
        (["serial-spi-set", "--bus", "1", "--word-width", "8"], True),
        (["serial-spi-show", "--bus", "1"], True),
        (["serial-can-set", "--bus", "1", "--baud-rate", "500000"], True),
        (["serial-can-show", "--bus", "1"], True),
        (["serial-trigger-uart-set", "--bus", "1", "--type", "rx-start"], True),
        (["serial-trigger-uart-show", "--bus", "1"], True),
        (["serial-trigger-i2c-set", "--bus", "1", "--type", "start"], True),
        (["serial-trigger-i2c-show", "--bus", "1"], True),
        (["serial-trigger-spi-set", "--bus", "1", "--type", "mosi"], True),
        (["serial-trigger-spi-show", "--bus", "1"], True),
        (["serial-trigger-can-set", "--bus", "1", "--type", "start-of-frame"], True),
        (["serial-trigger-can-show", "--bus", "1"], True),
        (["serial-lister-status"], True),
        (["serial-lister-display", "--query"], True),
        (["serial-lister-reference", "--reference", "previous"], True),
        (["serial-data"], True),
        (["serial-query", "--bus", "1"], False),
        (["serial-display", "--bus", "1", "--query"], False),
        (["serial-display", "--bus", "1", "--enabled", "true"], False),
        (["serial-uart", "--bus", "1", "--query"], False),
        (["serial-i2c", "--bus", "1", "--query"], False),
        (["serial-spi", "--bus", "1", "--query"], False),
        (["serial-can", "--bus", "1", "--query"], False),
        (["serial-trigger-uart", "--bus", "1", "--query"], False),
        (["serial-trigger-i2c", "--bus", "1", "--query"], False),
        (["serial-trigger-spi", "--bus", "1", "--query"], False),
        (["serial-trigger-can", "--bus", "1", "--query"], False),
        (["serial-lister-query"], False),
        (["serial-lister-export"], False),
    ],
)
def test_serial_command_spellings_parser_acceptance(argv, accepted):
    parser = cli_parser._build_parser()
    if accepted:
        assert parser.parse_args(argv).command == argv[0]
    else:
        with pytest.raises(SystemExit):
            parser.parse_args(argv)
