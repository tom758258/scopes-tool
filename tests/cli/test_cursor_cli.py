import json

import pytest

from scopes_tool_cli import cli


def test_cursor_query_simulate_off_returns_mode_without_position_queries(capsys):
    assert cli.main(["cursor", "--simulate", "--json", "--query"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    result = payload["result"]

    assert result["operation"] == "query"
    assert result["mode"] == "OFF"
    assert result["x1_seconds"] is None
    assert result["x2_seconds"] is None
    assert result["y1_volts"] is None
    assert result["y2_volts"] is None
    assert result["x_delta_seconds"] is None
    assert result["y_delta_volts"] is None
    assert result["dydx"] is None
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":MARKer:MODE?",
        ":SYSTem:ERRor?",
    ]
    assert payload["system_error"]["is_error"] is False


@pytest.mark.parametrize(
    ("model_id", "expects_dydx"),
    [
        ("keysight-dsox3024a", False),
        ("keysight-dsox4024a", True),
    ],
)
def test_cursor_query_dry_run_uses_series_aware_core_plan(
    capsys,
    model_id,
    expects_dydx,
):
    assert (
        cli.main(
            [
                "cursor",
                "--dry-run",
                "--json",
                "--model",
                model_id,
                "--query",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    commands = payload["result"]["commands"]

    assert payload["scpi"]["planned"] == commands + [":SYSTem:ERRor?"]
    assert (":MARKer:DYDX?" in commands) is expects_dydx


def _cursor_dry_run_payload(capsys, arguments):
    assert cli.main(["cursor", "--dry-run", "--json", "--model", "keysight-dsox4024a"] + arguments) == 0
    return json.loads(capsys.readouterr().out)


def _cursor_dry_run_error(capsys, arguments):
    assert cli.main(["cursor", "--dry-run", "--json", "--model", "keysight-dsox4024a"] + arguments) == 1
    return json.loads(capsys.readouterr().out)["error"]["message"]


def test_cursor_configure_x_only_reports_other_positions_null(capsys):
    payload = _cursor_dry_run_payload(capsys, ["--source-channel", "1", "--x1", "0.001"])
    result = payload["result"]

    assert result["operation"] == "set"
    assert result["commands"] == [
        ":MARKer:MODE MANual",
        ":MARKer:X1Y1source CHANnel1",
        ":MARKer:X2Y2source CHANnel1",
        ":MARKer:X1Position 0.001",
    ]
    assert result["x1_seconds"] == 0.001
    assert result["x2_seconds"] is None
    assert result["y1_volts"] is None
    assert result["y2_volts"] is None


def test_cursor_configure_y_only_reports_other_positions_null(capsys):
    payload = _cursor_dry_run_payload(capsys, ["--source-channel", "1", "--y2", "0"])
    result = payload["result"]

    assert result["commands"] == [
        ":MARKer:MODE MANual",
        ":MARKer:X1Y1source CHANnel1",
        ":MARKer:X2Y2source CHANnel1",
        ":MARKer:Y2Position 0",
    ]
    assert result["x1_seconds"] is None
    assert result["x2_seconds"] is None
    assert result["y1_volts"] is None
    assert result["y2_volts"] == 0.0


def test_cursor_configure_rejects_missing_source_and_positions(capsys):
    message = _cursor_dry_run_error(capsys, ["--source-channel", "1"])
    assert message == "cursor configure requires --source-channel and at least one of --x1, --x2, --y1, --y2"

    message = _cursor_dry_run_error(capsys, ["--x1", "0.001"])
    assert message == "cursor configure requires --source-channel and at least one of --x1, --x2, --y1, --y2"


def test_cursor_query_rejects_configure_arguments(capsys):
    message = _cursor_dry_run_error(capsys, ["--query", "--x1", "0.001"])
    assert message == "--query cannot be combined with --x1"

    message = _cursor_dry_run_error(capsys, ["--query", "--x1", "0"])
    assert message == "--query cannot be combined with --x1"

    message = _cursor_dry_run_error(capsys, ["--off", "--y2", "0"])
    assert message == "--off cannot be combined with --y2"

    message = _cursor_dry_run_error(capsys, ["--off", "--auto-timebase"])
    assert message == "--off cannot be combined with --auto-timebase"


def test_cursor_auto_timebase_rejects_missing_x(capsys):
    message = _cursor_dry_run_error(capsys, ["--source-channel", "1", "--y1", "0.5", "--auto-timebase"])
    assert message == "--auto-timebase requires --x1 or --x2."


def test_tek_b2_cursor_simulation_uses_native_scpi(capsys):
    assert cli.main(
        [
            "cursor",
            "--simulate",
            "--json",
            "--model",
            "tektronix-tbs2074b",
            "--source-channel",
            "2",
            "--x1",
            "0",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    commands = payload["scpi"]["sent"]
    assert "SELect:CONTROl CH2" in commands
    assert "CURSor:FUNCtion TIME" in commands
    assert "CURSor:VBArs:UNIts SECOnds" in commands
    assert not any(":MARKer:" in command for command in commands)


def test_tbs1052b_rejects_dual_axis_cursor_set_without_cursor_scpi(capsys):
    assert cli.main(
        [
            "cursor",
            "--simulate",
            "--json",
            "--model",
            "tektronix-tbs1052b",
            "--source-channel",
            "1",
            "--x1",
            "0",
            "--y1",
            "0",
        ]
    ) == 1

    payload = json.loads(capsys.readouterr().out)
    assert "single axis only" in payload["error"]["message"]
    assert not any("CURSor:" in command for command in payload["scpi"]["sent"])
