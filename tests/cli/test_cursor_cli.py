import json

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
