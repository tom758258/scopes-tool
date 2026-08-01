import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model="keysight-dsox4024a",
        resource=None,
        artifact_root=tmp_path,
        queue_max=1,
        output_format="jsonl",
    )


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"query": True}, ["trigger-runt", "--query"]),
        (
            {
                "channel": 1,
                "polarity": "positive",
                "qualifier": "greater_than",
                "time_seconds": 5e-6,
                "low_level_volts": -0.25,
                "high_level_volts": 0.75,
            },
            [
                "trigger-runt",
                "--channel",
                "1",
                "--polarity",
                "positive",
                "--qualifier",
                "greater-than",
                "--time-seconds",
                "5e-06",
                "--low-level-volts",
                "-0.25",
                "--high-level-volts",
                "0.75",
            ],
        ),
        (
            {
                "channel": 1,
                "polarity": "negative",
                "qualifier": "less_than",
                "time_seconds": 2e-6,
                "low_level_volts": -0.25,
                "high_level_volts": 0.75,
            },
            [
                "trigger-runt",
                "--channel",
                "1",
                "--polarity",
                "negative",
                "--qualifier",
                "less-than",
                "--time-seconds",
                "2e-06",
                "--low-level-volts",
                "-0.25",
                "--high-level-volts",
                "0.75",
            ],
        ),
        (
            {
                "channel": 1,
                "polarity": "either",
                "qualifier": "none",
                "low_level_volts": -0.5,
                "high_level_volts": 0.5,
            },
            [
                "trigger-runt",
                "--channel",
                "1",
                "--polarity",
                "either",
                "--qualifier",
                "none",
                "--low-level-volts",
                "-0.5",
                "--high-level-volts",
                "0.5",
            ],
        ),
    ],
)
def test_worker_trigger_runt_arguments_parse(tmp_path, arguments, expected):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command("trigger-runt", arguments, runtime)

    assert parsed.command == "trigger-runt"
    assert worker.arguments_to_argv(
        worker._normalize_trigger_runt_worker_arguments("trigger-runt", arguments)
    ) == expected[1:]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": False},
        {"query": True, "channel": 1},
        {
            "channel": 1,
            "polarity": "positive",
            "qualifier": "greater_than",
            "low_level_volts": -0.5,
            "high_level_volts": 0.5,
        },
        {
            "channel": 1,
            "polarity": "positive",
            "qualifier": "none",
            "time_seconds": 1e-6,
            "low_level_volts": -0.5,
            "high_level_volts": 0.5,
        },
        {
            "channel": 1,
            "polarity": "positive",
            "qualifier": "invalid",
            "time_seconds": 1e-6,
            "low_level_volts": -0.5,
            "high_level_volts": 0.5,
        },
        {
            "digital": 0,
            "polarity": "positive",
            "qualifier": "greater_than",
            "time_seconds": 1e-6,
            "low_level_volts": -0.5,
            "high_level_volts": 0.5,
        },
        {
            "channel": 1,
            "polarity": "positive",
            "qualifier": "none",
            "low_level_volts": 0.5,
            "high_level_volts": 0.5,
        },
    ],
)
def test_worker_trigger_runt_rejects_invalid_arguments(tmp_path, arguments):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("trigger-runt", arguments, runtime)


@pytest.mark.parametrize("command", ["runt-trigger", "trigger-runt-width"])
def test_worker_rejects_trigger_runt_aliases(command):
    with pytest.raises(OscilloscopeError):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": command,
                "arguments": {"query": True},
            }
        )


def test_worker_trigger_runt_simulator_execution_sends_expected_scpi(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-runt",
        {
            "channel": 1,
            "polarity": "either",
            "qualifier": "none",
            "low_level_volts": -0.5,
            "high_level_volts": 0.5,
        },
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE RUNT",
        ":TRIGger:RUNT:SOURce CHANnel1",
        ":TRIGger:LEVel:LOW -0.5,CHANnel1",
        ":TRIGger:LEVel:HIGH 0.5,CHANnel1",
        ":TRIGger:RUNT:POLarity EITHer",
        ":TRIGger:RUNT:QUALifier NONE",
        ":SYSTem:ERRor?",
    ]
