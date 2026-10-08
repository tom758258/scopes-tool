import json
from types import SimpleNamespace

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_cli.commands.measurement_analysis import _cursor_range_diagnostic
from scopes_tool_core.simulator_backend import SimulatorBackend
from tests.cli._agent_safe_cli_support import _json_stdout


def test_label_and_annotation_dry_run_json_reports_planned_scpi_without_opening(
    monkeypatch, capsys
):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert (
        cli.main(
            [
                "channel-label",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--channel",
                "1",
                "--text",
                "Input a",
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"] == [':CHANnel1:LABel "Input a"', ":SYSTem:ERRor?"]
    assert payload["result"]["text"] == "Input a"

    assert cli.main(["display-label", "--dry-run", "--json", "--off"]) == 0
    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"] == [":DISPlay:LABel OFF", ":SYSTem:ERRor?"]
    assert payload["result"]["display_label"] is False

    assert (
        cli.main(
            [
                "annotation",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--slot",
                "2",
                "--on",
                "--text",
                "Note",
                "--x",
                "10",
                "--y",
                "20",
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"] == [
        ':DISPlay:ANNotation2:TEXT "Note"',
        ":DISPlay:ANNotation2:X1Position 10",
        ":DISPlay:ANNotation2:Y1Position 20",
        ":DISPlay:ANNotation2 ON",
        ":SYSTem:ERRor?",
    ]


def test_annotation_validation_errors_do_not_open_backend(monkeypatch, capsys):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("validation failure must not open a scope")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert (
        cli.main(
            [
                "annotation",
                "--dry-run",
                "--json",
                "--query",
                "--text",
                "bad",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert "--query cannot be combined" in payload["error"]["message"]

    assert (
        cli.main(
            [
                "annotation",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox3024a",
                "--text",
                "Note",
                "--x",
                "10",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert "annotation x is supported only" in payload["error"]["message"]

    assert (
        cli.main(
            [
                "annotation",
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--text",
                "x" * 255,
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert "annotation text must be at most 254 characters" in payload["error"]["message"]


def test_annotation_simulate_json_roundtrip_4000x(capsys):
    assert (
        cli.main(
            [
                "annotation",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4024a",
                "--slot",
                "2",
                "--on",
                "--text",
                "Note",
                "--color",
                "red",
                "--background",
                "opaque",
                "--x",
                "10",
                "--y",
                "20",
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ':DISPlay:ANNotation2:TEXT "Note"',
        ":DISPlay:ANNotation2:COLor RED",
        ":DISPlay:ANNotation2:BACKground OPAQ",
        ":DISPlay:ANNotation2:X1Position 10",
        ":DISPlay:ANNotation2:Y1Position 20",
        ":DISPlay:ANNotation2 ON",
        ":SYSTem:ERRor?",
    ]


def test_annotation_query_simulate_json_3000x_reports_null_position(capsys):
    assert (
        cli.main(
            [
                "annotation",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox3024a",
                "--query",
            ]
        )
        == 0
    )
    payload = _json_stdout(capsys)
    assert payload["result"]["x"] is None
    assert payload["result"]["y"] is None
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":DISPlay:ANNotation?",
        ":DISPlay:ANNotation:TEXT?",
        ":DISPlay:ANNotation:COLor?",
        ":DISPlay:ANNotation:BACKground?",
        ":SYSTem:ERRor?",
    ]


def test_annotation_query_json_reports_canonical_readback_enums(monkeypatch, capsys):
    backend = SimulatorBackend(
        physical_model_id="keysight-dsox4034a",
        query_overrides={
            ":DISPlay:ANNotation1:COLor?": "WHIT",
            ":DISPlay:ANNotation1:BACKground?": "tran",
        },
    )
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

    assert (
        cli.main(
            [
                "annotation",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox4034a",
                "--query",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["color"] == "WHITE"
    assert payload["result"]["background"] == "TRAN"


def test_advanced_autoscale_dry_run_json_accepts_2000x_and_3000x(monkeypatch, capsys):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    for model in ("keysight-dsox2004a", "keysight-dsox3024a"):
        assert cli.main(["autoscale", "--dry-run", "--json", "--model", model]) == 0

        payload = _json_stdout(capsys)
        assert payload["capabilities"]["series"] in {"2000X", "3000X"}
        assert payload["scpi"]["planned"] == [":AUToscale", ":SYSTem:ERRor?"]


@pytest.mark.parametrize(
    ("command", "arguments", "expected_operation", "expected_command"),
    [
        (
            "setup-save",
            ["--file", "\\usb\\setup.scp"],
            "save",
            ':SAVE:SETup "\\usb\\setup.scp"',
        ),
        (
            "setup-recall",
            ["--slot", "3"],
            "recall",
            ":RECall:SETup 3",
        ),
    ],
)
def test_setup_dry_run_reports_completion_barrier(
    command, arguments, expected_operation, expected_command, capsys
):
    assert (
        cli.main(
            [
                command,
                "--dry-run",
                "--json",
                "--model",
                "keysight-dsox4034a",
                *arguments,
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"] == [
        expected_command,
        "*OPC?",
        ":SYSTem:ERRor?",
    ]
    assert payload["result"] == {
        "operation": expected_operation,
        "command": expected_command,
        "slot": 3 if command == "setup-recall" else None,
        "file": "\\usb\\setup.scp" if command == "setup-save" else None,
    }


def test_channel_timebase_trigger_json_results(capsys):
    assert cli.main(["channel-scale", "--simulate", "--json", "--channel", "1", "--volts-per-division", "0.5"]) == 0
    channel_payload = _json_stdout(capsys)
    assert channel_payload["result"]["operation"] == "set"
    assert channel_payload["result"]["channel"] == 1
    assert channel_payload["result"]["volts_per_division"] == 0.5

    assert cli.main(["timebase-position", "--simulate", "--json", "--seconds", "0.001"]) == 0
    timebase_payload = _json_stdout(capsys)
    assert timebase_payload["result"]["operation"] == "set"
    assert timebase_payload["result"]["position_seconds"] == 0.001

    assert cli.main(["timebase-reference", "--simulate", "--json", "--reference", "right"]) == 0
    reference_set = _json_stdout(capsys)
    assert reference_set["result"]["reference"] == "right"
    assert ":TIMebase:REFerence RIGHt" in reference_set["scpi"]["sent"]

    assert cli.main(["timebase-reference", "--simulate", "--json", "--query"]) == 0
    reference_query = _json_stdout(capsys)
    assert reference_query["result"]["reference"] == "center"
    assert ":TIMebase:REFerence?" in reference_query["scpi"]["sent"]

    assert cli.main(["trigger-edge", "--simulate", "--json", "--source-channel", "1", "--level", "0.2", "--slope", "positive"]) == 0
    trigger_payload = _json_stdout(capsys)
    assert trigger_payload["result"]["source_channel"] == 1
    assert trigger_payload["result"]["level_volts"] == 0.2
    assert trigger_payload["result"]["slope"] == "POSitive"


def test_timebase_reference_cli_rejects_invalid_enum_before_execution(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["timebase-reference", "--simulate", "--reference", "middle"])

    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_channel_advanced_simulate_json_results(capsys):
    assert (
        cli.main(
            [
                "channel-impedance",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox3024a",
                "--channel",
                "1",
                "--impedance",
                "fifty",
                "--allow-50-ohm",
            ]
        )
        == 0
    )
    impedance_payload = _json_stdout(capsys)
    assert impedance_payload["result"]["operation"] == "set"
    assert impedance_payload["result"]["impedance"] == "fifty"
    assert impedance_payload["scpi"]["sent"] == [
        "*IDN?",
        ":CHANnel1:IMPedance FIFTy",
        ":SYSTem:ERRor?",
    ]

    assert cli.main(["channel-units", "--simulate", "--json", "--channel", "1", "--query"]) == 0
    units_payload = _json_stdout(capsys)
    assert units_payload["result"]["operation"] == "query"
    assert units_payload["result"]["units"] == "volt"
    assert units_payload["scpi"]["sent"] == ["*IDN?", ":CHANnel1:UNITs?", ":SYSTem:ERRor?"]

    assert (
        cli.main(
            [
                "channel-range",
                "--simulate",
                "--json",
                "--channel",
                "1",
                "--volts-full-scale",
                "4",
            ]
        )
        == 0
    )
    range_payload = _json_stdout(capsys)
    assert range_payload["result"]["operation"] == "set"
    assert range_payload["result"]["range_volts"] == 4.0
    assert range_payload["scpi"]["sent"] == ["*IDN?", ":CHANnel1:RANGe 4", ":SYSTem:ERRor?"]


def test_channel_advanced_dry_run_json_reports_planned_scpi_without_opening(
    monkeypatch, capsys
):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("dry-run must not open a VISA scope")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert (
        cli.main(
            [
                "channel-probe-skew",
                "--dry-run",
                "--json",
                "--channel",
                "1",
                "--seconds",
                "1e-9",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["probe_skew_seconds"] == 1e-9
    assert payload["scpi"]["planned"] == [
        ":CHANnel1:PROBe:SKEW 1e-09",
        ":SYSTem:ERRor?",
    ]
    assert payload["scpi"]["sent"] == []

    assert (
        cli.main(
            [
                "channel-range",
                "--dry-run",
                "--json",
                "--channel",
                "1",
                "--volts-full-scale",
                "4",
            ]
        )
        == 0
    )
    range_payload = _json_stdout(capsys)
    assert range_payload["result"]["range_volts"] == 4.0
    assert range_payload["scpi"]["planned"] == [
        ":CHANnel1:RANGe 4",
        ":SYSTem:ERRor?",
    ]
    assert range_payload["scpi"]["sent"] == []


def test_channel_impedance_json_rejects_fifty_without_allow_before_open(monkeypatch, capsys):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("validation failure must not open a VISA scope")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert (
        cli.main(
            [
                "channel-impedance",
                "--json",
                "--resource",
                "USB0::FAKE::INSTR",
                "--channel",
                "1",
                "--impedance",
                "fifty",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "requires --allow-50-ohm" in payload["error"]["message"]
    assert payload["scpi"]["sent"] == []


def test_channel_impedance_simulate_rejects_2000x_fifty_after_idn(capsys):
    assert (
        cli.main(
            [
                "channel-impedance",
                "--simulate",
                "--json",
                "--model",
                "keysight-dsox2004a",
                "--channel",
                "1",
                "--impedance",
                "fifty",
                "--allow-50-ohm",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert (
        "DSO-X 2000X only supports one-meg input impedance; 50 ohm is not supported "
        "by the 2000X channel impedance spec."
    ) in payload["error"]["message"]
    assert payload["scpi"]["sent"] == ["*IDN?"]


def test_cursor_auto_timebase_dry_run_json_plans_queries(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--dry-run",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.01",
                "--auto-timebase",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"][:2] == [":TIMebase:SCALe?", ":TIMebase:POSition?"]
    assert not any(command.startswith(":TIMebase:SCALe ") for command in payload["scpi"]["planned"])
    assert payload["result"]["auto_timebase"]["enabled"] is True
    assert payload["result"]["auto_timebase"]["strategy"] == "scale_only"
    assert payload["result"]["auto_timebase"]["changed"] is None
    assert payload["result"]["auto_timebase"]["target_scale_seconds_per_division"] is None


def test_cursor_auto_timebase_simulate_widens_before_cursor_setup(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.01",
                "--auto-timebase",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    sent = payload["scpi"]["sent"]
    assert sent[1:4] == [
        ":TIMebase:SCALe?",
        ":TIMebase:POSition?",
        ":TIMebase:SCALe 0.0025",
    ]
    assert sent.index(":TIMebase:SCALe 0.0025") < sent.index(":MARKer:MODE MANual")
    assert payload["result"]["auto_timebase"]["changed"] is True
    assert payload["result"]["auto_timebase"]["original_position_seconds"] == 0.0


def test_cursor_auto_vertical_dry_run_json_plans_queries(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--dry-run",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.001",
                "--y1",
                "10",
                "--auto-vertical",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["scpi"]["planned"][:2] == [":CHANnel1:SCALe?", ":CHANnel1:OFFSet?"]
    assert not any(command.startswith(":CHANnel1:SCALe ") for command in payload["scpi"]["planned"])
    assert payload["result"]["auto_vertical"]["enabled"] is True
    assert payload["result"]["auto_vertical"]["strategy"] == "scale_then_offset"
    assert payload["result"]["auto_vertical"]["changed"] is None
    assert payload["result"]["auto_vertical"]["target_scale_volts_per_division"] is None


def test_cursor_auto_vertical_simulate_adjusts_before_cursor_setup(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.001",
                "--y1",
                "20",
                "--y2",
                "21",
                "--auto-vertical",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    sent = payload["scpi"]["sent"]
    assert sent[1:5] == [
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 1",
        ":CHANnel1:OFFSet 20.5",
    ]
    assert sent.index(":CHANnel1:OFFSet 20.5") < sent.index(":MARKer:MODE MANual")
    assert payload["result"]["auto_vertical"]["changed"] is True
    assert payload["result"]["auto_vertical"]["offset_changed"] is True


def test_cursor_auto_timebase_and_auto_vertical_can_combine(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.01",
                "--y1",
                "20",
                "--auto-timebase",
                "--auto-vertical",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    sent = payload["scpi"]["sent"]
    assert sent[1:4] == [
        ":TIMebase:SCALe?",
        ":TIMebase:POSition?",
        ":TIMebase:SCALe 0.0025",
    ]
    assert sent[4:8] == [
        ":CHANnel1:SCALe?",
        ":CHANnel1:OFFSet?",
        ":CHANnel1:SCALe 1",
        ":CHANnel1:OFFSet 20",
    ]
    assert "auto_timebase" in payload["result"]
    assert "auto_vertical" in payload["result"]


def test_cursor_auto_timebase_rejects_query_and_off(capsys):
    assert cli.main(["cursor", "--dry-run", "--json", "--query", "--auto-timebase"]) == 1
    payload = _json_stdout(capsys)
    assert payload["error"]["message"] == "--query cannot be combined with --auto-timebase"

    assert cli.main(["cursor", "--dry-run", "--json", "--off", "--auto-timebase"]) == 1
    payload = _json_stdout(capsys)
    assert payload["error"]["message"] == "--off cannot be combined with --auto-timebase"


def test_cursor_auto_vertical_rejects_query_off_and_missing_y(capsys):
    assert cli.main(["cursor", "--dry-run", "--json", "--query", "--auto-vertical"]) == 1
    payload = _json_stdout(capsys)
    assert payload["error"]["message"] == "--query cannot be combined with --auto-vertical"

    assert cli.main(["cursor", "--dry-run", "--json", "--off", "--auto-vertical"]) == 1
    payload = _json_stdout(capsys)
    assert payload["error"]["message"] == "--off cannot be combined with --auto-vertical"

    assert (
        cli.main(
            [
                "cursor",
                "--dry-run",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.001",
                "--auto-vertical",
            ]
        )
        == 1
    )
    payload = _json_stdout(capsys)
    assert "--auto-vertical requires --y1 or --y2" in payload["error"]["message"]


def test_cursor_without_auto_timebase_reports_range_diagnostic(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.01",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["system_error"]["code"] == -222
    assert "cursor --auto-timebase" in payload["result"]["diagnostic"]
    assert "cursor --auto-vertical" in payload["result"]["diagnostic"]
    assert ":TIMebase:SCALe?" not in payload["scpi"]["sent"]
    assert not any(command.startswith(":TIMebase:SCALe ") for command in payload["scpi"]["sent"])


def test_cursor_without_auto_vertical_reports_y_range_diagnostic(capsys):
    assert (
        cli.main(
            [
                "cursor",
                "--simulate",
                "--json",
                "--source-channel",
                "1",
                "--x1",
                "0",
                "--x2",
                "0.001",
                "--y1",
                "10",
            ]
        )
        == 1
    )

    payload = _json_stdout(capsys)
    assert payload["system_error"]["code"] == -222
    assert "cursor --auto-vertical" in payload["result"]["diagnostic"]


def _cursor_range_error_entry():
    return SimpleNamespace(code=-222, message='-222,"Data out of range"')


def _cursor_partial_args(**overrides):
    values = {
        "command": "cursor",
        "cursor_query": False,
        "cursor_off": False,
        "source_channel": 1,
        "x1": None,
        "x2": None,
        "y1": None,
        "y2": None,
        "auto_timebase": False,
        "auto_vertical": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_cursor_x_only_auto_timebase_diagnostic_omits_auto_vertical():
    args = _cursor_partial_args(x1=0.0, auto_timebase=True)

    diagnostic = _cursor_range_diagnostic(args, _cursor_range_error_entry())

    assert diagnostic is not None
    assert "--auto-vertical" not in diagnostic


def test_cursor_y_only_auto_vertical_diagnostic_omits_auto_timebase():
    args = _cursor_partial_args(y2=0.0, auto_vertical=True)

    diagnostic = _cursor_range_diagnostic(args, _cursor_range_error_entry())

    assert diagnostic is not None
    assert "--auto-timebase" not in diagnostic


def test_cursor_xy_auto_vertical_diagnostic_keeps_cross_axis_hint():
    args = _cursor_partial_args(x1=0.0, y1=10.0, auto_vertical=True)

    diagnostic = _cursor_range_diagnostic(args, _cursor_range_error_entry())

    assert diagnostic is not None
    assert "cursor --auto-timebase" in diagnostic


def test_acquisition_dry_run_json_reports_structured_plan(capsys):
    assert cli.main(["acquisition", "--dry-run", "--json", "--type", "average", "--count", "16"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["scpi_type"] == "AVERage"
    assert payload["result"]["count"] == 16
    assert payload["scpi"]["planned"] == [":ACQuire:TYPE AVERage", ":ACQuire:COUNt 16", ":SYSTem:ERRor?"]


def test_acquisition_simulate_json_query_reports_readback_and_sent_scpi(capsys):
    assert cli.main(["acquisition", "--simulate", "--json", "--query"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["type"] == "normal"
    assert payload["result"]["count"] == 8
    assert payload["result"]["commands"] == [":ACQuire:TYPE?", ":ACQuire:COUNt?"]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":ACQuire:TYPE?",
        ":ACQuire:COUNt?",
        ":SYSTem:ERRor?",
    ]


def test_acquisition_simulate_json_bad_readback_reports_error(monkeypatch, capsys):
    backend = SimulatorBackend(query_overrides={":ACQuire:TYPE?": "bad-type"})
    monkeypatch.setattr(runtime, "_make_simulator_backend", lambda args, resource: backend)

    assert cli.main(["acquisition", "--simulate", "--json", "--query"]) == 1

    payload = _json_stdout(capsys)
    assert payload["ok"] is False
    assert "Could not parse acquisition type" in payload["error"]["message"]
    assert payload["scpi"]["sent"] == ["*IDN?", ":ACQuire:TYPE?"]


def test_acquisition_simulate_json_normal_reports_sent_scpi(capsys):
    assert cli.main(["acquisition", "--simulate", "--json", "--type", "normal"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["type"] == "normal"
    assert payload["result"]["scpi_type"] == "NORMal"
    assert payload["result"]["count"] is None
    assert payload["result"]["commands"] == [":ACQuire:TYPE NORMal"]
    assert payload["scpi"]["sent"] == ["*IDN?", ":ACQuire:TYPE NORMal", ":SYSTem:ERRor?"]


def test_acquisition_simulate_json_average_count_reports_sent_scpi(capsys):
    assert (
        cli.main(
            [
                "acquisition",
                "--simulate",
                "--json",
                "--type",
                "average",
                "--count",
                "16",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["type"] == "average"
    assert payload["result"]["scpi_type"] == "AVERage"
    assert payload["result"]["count"] == 16
    assert payload["result"]["commands"] == [":ACQuire:TYPE AVERage", ":ACQuire:COUNt 16"]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":ACQuire:TYPE AVERage",
        ":ACQuire:COUNt 16",
        ":SYSTem:ERRor?",
    ]


def test_acquisition_simulate_json_high_resolution_reports_sent_scpi(capsys):
    assert (
        cli.main(
            ["acquisition", "--simulate", "--json", "--type", "high_resolution"]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["type"] == "high_resolution"
    assert payload["result"]["scpi_type"] == "HRESolution"
    assert payload["result"]["count"] is None
    assert payload["result"]["commands"] == [":ACQuire:TYPE HRESolution"]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":ACQuire:TYPE HRESolution",
        ":SYSTem:ERRor?",
    ]


def test_acquisition_simulate_json_peak_reports_sent_scpi(capsys):
    assert cli.main(["acquisition", "--simulate", "--json", "--type", "peak"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["type"] == "peak"
    assert payload["result"]["scpi_type"] == "PEAK"
    assert payload["result"]["count"] is None
    assert payload["result"]["commands"] == [":ACQuire:TYPE PEAK"]
    assert payload["scpi"]["sent"] == ["*IDN?", ":ACQuire:TYPE PEAK", ":SYSTem:ERRor?"]
