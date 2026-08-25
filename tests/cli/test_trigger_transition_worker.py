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
                queue_max=1,
        output_format="jsonl",
    )


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"query": True}, ["trigger-transition", "--query"]),
        (
            {
                "channel": 1,
                "slope": "positive",
                "qualifier": "greater_than",
                "time_seconds": 5e-6,
                "low_level_volts": -0.5,
                "high_level_volts": 0.5,
            },
            [
                "trigger-transition",
                "--channel",
                "1",
                "--slope",
                "positive",
                "--qualifier",
                "greater-than",
                "--time-seconds",
                "5e-06",
                "--low-level-volts",
                "-0.5",
                "--high-level-volts",
                "0.5",
            ],
        ),
        (
            {
                "channel": 1,
                "slope": "negative",
                "qualifier": "less_than",
                "time_seconds": 2e-6,
                "low_level_volts": -0.25,
                "high_level_volts": 0.75,
            },
            [
                "trigger-transition",
                "--channel",
                "1",
                "--slope",
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
    ],
)
def test_worker_trigger_transition_arguments_parse(tmp_path, arguments, expected):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command("trigger-transition", arguments, runtime)

    assert parsed.command == "trigger-transition"
    assert worker.arguments_to_argv(
        worker._normalize_trigger_transition_worker_arguments(
            "trigger-transition",
            arguments,
        )
    ) == expected[1:]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": False},
        {"query": True, "channel": 1},
        {
            "channel": 1,
            "slope": "positive",
            "qualifier": "greater_than",
            "low_level_volts": -0.5,
            "high_level_volts": 0.5,
        },
        {
            "channel": 1,
            "slope": "either",
            "qualifier": "greater_than",
            "time_seconds": 1e-6,
            "low_level_volts": -0.5,
            "high_level_volts": 0.5,
        },
        {
            "channel": 1,
            "slope": "positive",
            "qualifier": "invalid",
            "time_seconds": 1e-6,
            "low_level_volts": -0.5,
            "high_level_volts": 0.5,
        },
        {
            "digital": 0,
            "slope": "positive",
            "qualifier": "greater_than",
            "time_seconds": 1e-6,
            "low_level_volts": -0.5,
            "high_level_volts": 0.5,
        },
        {
            "channel": 1,
            "slope": "positive",
            "qualifier": "greater_than",
            "time_seconds": 0,
            "low_level_volts": -0.5,
            "high_level_volts": 0.5,
        },
        {
            "channel": 1,
            "slope": "positive",
            "qualifier": "greater_than",
            "time_seconds": 1e-6,
            "low_level_volts": 0.5,
            "high_level_volts": 0.5,
        },
    ],
)
def test_worker_trigger_transition_rejects_invalid_arguments(tmp_path, arguments):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("trigger-transition", arguments, runtime)


@pytest.mark.parametrize("command", ["transition-trigger", "trigger-rise-fall"])
def test_worker_rejects_trigger_transition_aliases(command):
    with pytest.raises(OscilloscopeError):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": command,
                "arguments": {"query": True},
            }
        )


def test_worker_trigger_transition_simulator_execution_sends_expected_scpi(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-transition",
        {
            "channel": 1,
            "slope": "negative",
            "qualifier": "less_than",
            "time_seconds": 2e-6,
            "low_level_volts": -0.25,
            "high_level_volts": 0.75,
        },
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE TRANsition",
        ":TRIGger:TRANsition:SOURce CHANnel1",
        ":TRIGger:LEVel:LOW -0.25,CHANnel1",
        ":TRIGger:LEVel:HIGH 0.75,CHANnel1",
        ":TRIGger:TRANsition:SLOPe NEGative",
        ":TRIGger:TRANsition:TIME 2e-06",
        ":TRIGger:TRANsition:QUALifier LESSthan",
        ":SYSTem:ERRor?",
    ]
