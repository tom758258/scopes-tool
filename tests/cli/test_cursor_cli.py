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
