import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_cli._worker_commands_trigger import (
    _normalize_trigger_glitch_worker_arguments,
)
from scopes_tool_cli.worker_commands import arguments_to_argv
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model="keysight-dsox4024a",
        resource=None,
                queue_max=1,
        output_format="jsonl",
    )


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"query": True}, ["trigger-pulse-width", "--query"]),
        (
            {"channel": 1, "polarity": "positive", "qualifier": "range", "min_time_seconds": 1e-6, "max_time_seconds": 10e-6},
            ["trigger-pulse-width", "--channel", "1", "--polarity", "positive", "--qualifier", "range", "--min-time-seconds", "1e-06", "--max-time-seconds", "1e-05"],
        ),
    ],
)
def test_worker_trigger_pulse_width_arguments_parse(tmp_path, arguments, expected):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command("trigger-pulse-width", arguments, runtime)

    assert parsed.command == "trigger-pulse-width"
    assert arguments_to_argv(
        _normalize_trigger_glitch_worker_arguments("trigger-pulse-width", arguments)
    ) == expected[1:]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": False},
        {"query": True, "channel": 1},
        {"channel": 1, "polarity": "positive", "qualifier": "less_than"},
        {"digital": 0, "polarity": "positive", "qualifier": "less_than", "time_seconds": 1e-6},
    ],
)
def test_worker_trigger_pulse_width_rejects_invalid_arguments(tmp_path, arguments):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("trigger-pulse-width", arguments, runtime)


@pytest.mark.parametrize("command", ["trigger-glitch"])
def test_worker_rejects_trigger_pulse_width_aliases(command):
    with pytest.raises(OscilloscopeError):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": command,
                "arguments": {"query": True},
            }
        )


def test_worker_trigger_pulse_width_simulator_execution_sends_expected_scpi(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-pulse-width",
        {
            "channel": 1,
            "polarity": "positive",
            "qualifier": "range",
            "min_time_seconds": 1e-6,
            "max_time_seconds": 10e-6,
        },
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE GLITch",
        ":TRIGger:GLITch:SOURce CHANnel1",
        ":TRIGger:GLITch:POLarity POSitive",
        ":TRIGger:GLITch:RANGe 1e-05,1e-06",
        ":TRIGger:GLITch:QUALifier RANGe",
        ":SYSTem:ERRor?",
    ]
