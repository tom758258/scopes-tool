"""Focused parser regression tests for shared CLI option helpers."""

from __future__ import annotations

import argparse

import pytest

from scopes_tool_cli import parser


WAVEFORM_CASES = (
    ("segmented-capture", ("--channel", "1", "--segments", "2")),
    ("capture", ("--channel", "1")),
    ("capture-batch", ("--channel", "1", "--count", "1")),
    (
        "capture-until",
        (
            "--channel",
            "1",
            "--condition-channel",
            "1",
            "--metric",
            "max",
            "--operator",
            "gt",
            "--threshold",
            "0",
            "--timeout-seconds",
            "1",
        ),
    ),
    ("capture-monitor", ("--channel", "1", "--count", "1")),
    (
        "triggered-capture-series",
        ("--channel", "1", "--count", "1", "--trigger-timeout-seconds", "1"),
    ),
)

CAPTURE_CHANNEL_CASES = (
    ("capture", ()),
    ("capture-batch", ("--count", "1")),
    (
        "capture-until",
        (
            "--condition-channel",
            "1",
            "--metric",
            "max",
            "--operator",
            "gt",
            "--threshold",
            "0",
            "--timeout-seconds",
            "1",
        ),
    ),
    ("capture-monitor", ("--count", "1")),
    (
        "triggered-capture-series",
        ("--count", "1", "--trigger-timeout-seconds", "1"),
    ),
)

WORKER_CLIENT_CASES = (
    ("send-command", ("--port", "8765", "--command", "identify"), 5000),
    ("status", ("--port", "8765"), 5000),
    ("stop", ("--port", "8765"), 5000),
    ("wait-ready", ("--port", "8765"), 10000),
)


def _subcommand_parser(command: str) -> argparse.ArgumentParser:
    root = parser._build_parser()
    subparsers = next(
        action
        for action in root._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return subparsers.choices[command]


@pytest.mark.parametrize(("command", "required_args"), WAVEFORM_CASES)
def test_waveform_transfer_shared_defaults_and_explicit_values(
    command: str,
    required_args: tuple[str, ...],
) -> None:
    root = parser._build_parser()

    defaults = root.parse_args([command, *required_args])
    assert defaults.points == 1000
    assert defaults.waveform_format == "byte"

    explicit = root.parse_args(
        [command, *required_args, "--points", "5000", "--format", "word"]
    )
    assert explicit.points == 5000
    assert explicit.waveform_format == "word"


@pytest.mark.parametrize(("command", "extra_args"), CAPTURE_CHANNEL_CASES)
def test_capture_channels_shared_repeat_and_all_behavior(
    command: str,
    extra_args: tuple[str, ...],
) -> None:
    root = parser._build_parser()

    repeated = root.parse_args(
        [command, "--channel", "1", "--channel", "2", *extra_args]
    )
    assert repeated.channel == [1, 2]

    all_channels = root.parse_args([command, "--channel", "all", *extra_args])
    assert all_channels.channel == ["all"]


@pytest.mark.parametrize(("command", "_required_args"), WAVEFORM_CASES)
def test_waveform_transfer_help_is_consistent(
    command: str,
    _required_args: tuple[str, ...],
) -> None:
    help_text = " ".join(_subcommand_parser(command).format_help().split())

    assert "waveform point count; supported values: 1000, 5000, 10000" in help_text
    assert "waveform transfer format; defaults to byte" in help_text


@pytest.mark.parametrize(("command", "_extra_args"), CAPTURE_CHANNEL_CASES)
def test_capture_channel_help_is_consistent(
    command: str,
    _extra_args: tuple[str, ...],
) -> None:
    help_text = " ".join(_subcommand_parser(command).format_help().split())

    assert "analog channel number; repeat for aligned" in help_text
    assert "or use all for every analog channel on the detected model" in help_text


@pytest.mark.parametrize(
    ("command", "required_args", "timeout_ms"),
    WORKER_CLIENT_CASES,
)
def test_worker_client_shared_defaults(
    command: str,
    required_args: tuple[str, ...],
    timeout_ms: int,
) -> None:
    args = parser._build_parser().parse_args([command, *required_args])

    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.timeout_ms == timeout_ms
    assert args.format == "text"
    assert args.client_json is False


@pytest.mark.parametrize(
    ("command", "required_args", "_timeout_ms"),
    WORKER_CLIENT_CASES,
)
def test_worker_client_shared_explicit_values(
    command: str,
    required_args: tuple[str, ...],
    _timeout_ms: int,
) -> None:
    args = parser._build_parser().parse_args(
        [
            command,
            *required_args,
            "--host",
            "127.0.0.2",
            "--timeout-ms",
            "1234",
            "--format",
            "json",
            "--json",
        ]
    )

    assert args.host == "127.0.0.2"
    assert args.timeout_ms == 1234
    assert args.format == "json"
    assert args.client_json is True


@pytest.mark.parametrize(
    ("command", "_required_args", "timeout_ms"),
    WORKER_CLIENT_CASES,
)
def test_worker_client_help_is_consistent(
    command: str,
    _required_args: tuple[str, ...],
    timeout_ms: int,
) -> None:
    help_text = " ".join(_subcommand_parser(command).format_help().split())

    assert "Worker host; defaults to 127.0.0.1" in help_text
    assert "Worker HTTP port" in help_text
    assert (
        f"Worker request timeout in milliseconds; defaults to {timeout_ms}"
        in help_text
    )
    assert "output format; defaults to text" in help_text
    assert "write worker client output as JSON" in help_text
