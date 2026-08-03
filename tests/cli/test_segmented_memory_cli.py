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


def test_segmented_memory_simulate_enable_configures_count(capsys):
    assert (
        cli.main(
            [
                "segmented-memory",
                "--enable",
                "--segments",
                "25",
                "--simulate",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["operation"] == "enable"
    assert payload["result"]["mode"] == "segmented"
    assert payload["result"]["configured_segments"] == 25
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":ACQuire:TYPE?",
        ":ACQuire:MODE SEGMented",
        ":ACQuire:SEGMented:COUNt 25",
        ":SYSTem:ERRor?",
    ]


def test_segmented_memory_simulate_disable_only_sets_realtime(capsys):
    assert (
        cli.main(
            ["segmented-memory", "--disable", "--simulate", "--json"]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["operation"] == "disable"
    assert payload["result"]["mode"] == "realtime"
    assert payload["result"]["configured_segments"] is None
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":ACQuire:MODE RTIMe",
        ":SYSTem:ERRor?",
    ]


def test_segmented_memory_enable_dry_run_has_concrete_scpi(capsys):
    assert (
        cli.main(
            [
                "segmented-memory",
                "--enable",
                "--segments",
                "25",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["scpi"]["planned"] == [
        "*IDN?",
        ":ACQuire:TYPE?",
        ":ACQuire:MODE SEGMented",
        ":ACQuire:SEGMented:COUNt 25",
        ":SYSTem:ERRor?",
    ]
    assert payload["scpi"]["sent"] == []


def test_segmented_memory_disable_dry_run_has_concrete_scpi(capsys):
    assert (
        cli.main(["segmented-memory", "--disable", "--dry-run", "--json"]) == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["scpi"]["planned"] == [
        "*IDN?",
        ":ACQuire:MODE RTIMe",
        ":SYSTem:ERRor?",
    ]
    assert payload["scpi"]["sent"] == []


@pytest.mark.parametrize(
    ("arguments", "fragment"),
    [
        (["--enable", "--simulate"], "requires --segments"),
        (["--query", "--segments", "2", "--simulate"], "only valid"),
        (["--disable", "--segments", "2", "--simulate"], "only valid"),
    ],
)
def test_segmented_memory_rejects_invalid_operation_arguments(
    arguments, fragment, capsys
):
    assert cli.main(["segmented-memory", *arguments]) == 1
    assert fragment in capsys.readouterr().err


def test_segmented_memory_requires_query_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["segmented-memory", "--simulate"])

    assert excinfo.value.code == 2
    assert "one of the arguments --query --enable --disable is required" in capsys.readouterr().err
