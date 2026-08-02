import json

import pytest

from scopes_tool_cli import cli


def test_segmented_memory_simulate_json_returns_realtime_query(capsys):
    assert cli.main(["segmented-memory", "--query", "--simulate", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["mode"] == "realtime"
    assert payload["result"]["configured_segments"] is None
    assert payload["result"]["raw_mode"] == "RTIM"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":ACQuire:MODE?",
        ":SYSTem:ERRor?",
    ]


def test_segmented_memory_dry_run_has_no_conditional_queries(capsys):
    assert cli.main(["segmented-memory", "--query", "--dry-run", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["mode"] is None
    assert payload["scpi"]["planned"] == [
        "*IDN?",
        ":ACQuire:MODE?",
        ":SYSTem:ERRor?",
    ]
    assert all("SEGMented" not in command for command in payload["scpi"]["planned"])
    assert all("TTAG" not in command for command in payload["scpi"]["planned"])
    assert payload["scpi"]["sent"] == []


def test_segmented_memory_requires_query_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["segmented-memory", "--simulate"])

    assert excinfo.value.code == 2
    assert "the following arguments are required: --query" in capsys.readouterr().err
