"""Tests for shared display one-shot CLI commands."""

import json

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.display import (
    display_clear_command,
    display_intensity_command,
    display_intensity_query,
    display_persistence_command,
    display_persistence_query,
    display_vectors_command,
    display_vectors_query,
)


@pytest.mark.parametrize(
    ("argv", "expected_command", "expected_result"),
    [
        (
            ["display-clear", "--dry-run", "--json"],
            display_clear_command(),
            {"operation": "display-clear", "command": display_clear_command()},
        ),
        (
            ["display-persistence", "--dry-run", "--json", "--mode", "minimum"],
            display_persistence_command("minimum"),
            {
                "operation": "display-persistence",
                "command": display_persistence_command("minimum"),
                "mode": "minimum",
                "seconds": None,
            },
        ),
        (
            ["display-persistence", "--dry-run", "--json", "--seconds", "0.5"],
            display_persistence_command(0.5),
            {
                "operation": "display-persistence",
                "command": display_persistence_command(0.5),
                "mode": None,
                "seconds": 0.5,
            },
        ),
        (
            ["display-intensity", "--dry-run", "--json", "--value", "75"],
            display_intensity_command(75),
            {
                "operation": "display-intensity",
                "command": display_intensity_command(75),
                "value": 75,
            },
        ),
        (
            ["display-vectors", "--dry-run", "--json", "--on"],
            display_vectors_command(True),
            {
                "operation": "display-vectors",
                "command": display_vectors_command(True),
                "value": True,
            },
        ),
    ],
)
def test_display_common_dry_run_includes_one_shot_scpi_without_visa(
    argv, expected_command, expected_result, monkeypatch, capsys
):
    def fail_open(resource, visa_library=None):
        raise AssertionError("dry-run must not open VISA")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main(argv) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["scpi"]["planned"] == ["*IDN?", expected_command, ":SYSTem:ERRor?"]
    assert payload["scpi"]["sent"] == []
    for key, value in expected_result.items():
        assert payload["result"][key] == value
    assert "raw_value" not in payload["result"]


@pytest.mark.parametrize(
    ("argv", "expected_message"),
    [
        (
            ["display-persistence", "--dry-run", "--json"],
            "display-persistence requires exactly one",
        ),
        (
            ["display-persistence", "--dry-run", "--json", "--query", "--seconds", "1"],
            "display-persistence requires exactly one",
        ),
        (
            ["display-persistence", "--dry-run", "--json", "--seconds", "60.1"],
            "display persistence seconds must be in range 0.1-60.0",
        ),
        (
            ["display-intensity", "--dry-run", "--json"],
            "display-intensity requires exactly one",
        ),
        (
            ["display-intensity", "--dry-run", "--json", "--value", "101"],
            "display intensity must be in range 0-100",
        ),
        (
            ["display-vectors", "--dry-run", "--json"],
            "display-vectors requires exactly one",
        ),
        (
            ["display-vectors", "--dry-run", "--json", "--off"],
            "display-vectors set OFF is not supported",
        ),
    ],
)
def test_display_common_json_dry_run_validation_errors_are_single_json(
    argv, expected_message, monkeypatch, capsys
):
    def fail_open(resource, visa_library=None):
        raise AssertionError("invalid dry-run must not open VISA")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main(argv) == 1

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert payload["ok"] is False
    assert expected_message in payload["error"]["message"]
    assert payload["scpi"]["sent"] == []


@pytest.mark.parametrize(
    ("argv", "target_command", "result_fields"),
    [
        (
            ["display-clear", "--simulate", "--json"],
            display_clear_command(),
            {"operation": "display-clear", "command": display_clear_command()},
        ),
        (
            ["display-persistence", "--simulate", "--json", "--query"],
            display_persistence_query(),
            {"operation": "display-persistence", "mode": "minimum", "seconds": None},
        ),
        (
            ["display-persistence", "--simulate", "--json", "--seconds", "1.25"],
            display_persistence_command(1.25),
            {"operation": "display-persistence", "mode": None, "seconds": 1.25},
        ),
        (
            ["display-intensity", "--simulate", "--json", "--query"],
            display_intensity_query(),
            {"operation": "display-intensity", "value": 50},
        ),
        (
            ["display-vectors", "--simulate", "--json", "--query"],
            display_vectors_query(),
            {"operation": "display-vectors", "value": True},
        ),
        (
            ["display-vectors", "--simulate", "--json", "--on"],
            display_vectors_command(True),
            {"operation": "display-vectors", "value": True},
        ),
    ],
)
def test_display_common_simulate_json_runs_expected_scpi_order(
    argv, target_command, result_fields, capsys
):
    assert cli.main(argv) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["scpi"]["sent"] == ["*IDN?", target_command, ":SYSTem:ERRor?"]
    assert payload["result"]["command"] == target_command
    for key, value in result_fields.items():
        assert payload["result"][key] == value
    if argv[-1] == "--query":
        assert "raw_value" in payload["result"]
    else:
        assert "raw_value" not in payload["result"]
