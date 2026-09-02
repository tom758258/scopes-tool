"""Tests for the single-wait CLI command."""

import json

from scopes_tool_cli import cli, parser, runtime
from scopes_tool_core.trigger import (
    force_trigger_command,
    operation_condition_query,
    single_command,
)


def test_single_wait_parser_defaults() -> None:
    args = parser._build_parser().parse_args(["single-wait", "--simulate"])

    assert args.trigger_timeout_ms == 5000
    assert args.trigger_poll_interval_ms == 100
    assert args.force_trigger_on_timeout is False


def test_single_wait_simulate_uses_core_result_schema(capsys) -> None:
    assert cli.main(["single-wait", "--simulate", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    result = payload["result"]
    assert result["operation"] == "single-wait"
    assert result["outcome"] == "natural"
    assert result["timeout_ms"] == 5000
    assert result["poll_interval_ms"] == 100
    assert result["force_on_timeout"] is False
    assert payload["scpi"]["sent"][1:3] == [
        single_command(),
        operation_condition_query(),
    ]
    assert payload["files"] == []


def test_single_wait_rejects_poll_interval_above_timeout_before_opening(
    monkeypatch,
    capsys,
) -> None:
    def fail_open(resource, visa_library=None):
        raise AssertionError("invalid configuration must not open VISA")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main([
        "single-wait",
        "--dry-run",
        "--json",
        "--trigger-timeout-ms",
        "50",
        "--trigger-poll-interval-ms",
        "100",
    ]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "less than or equal" in payload["error"]["message"]


def test_single_wait_dry_run_uses_trigger_wait_plan_without_visa(
    monkeypatch,
    capsys,
) -> None:
    def fail_open(resource, visa_library=None):
        raise AssertionError("dry-run must not open VISA")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main([
        "single-wait",
        "--dry-run",
        "--json",
        "--force-trigger-on-timeout",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["scpi"]["planned"] == [
        "*IDN?",
        single_command(),
        operation_condition_query(),
        force_trigger_command(),
        operation_condition_query(),
        ":SYSTem:ERRor?",
    ]
    assert payload["result"]["force_on_timeout"] is True
    assert payload["scpi"]["sent"] == []
    assert payload["files"] == []
