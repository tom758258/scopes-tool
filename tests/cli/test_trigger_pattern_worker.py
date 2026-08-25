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
        ({"query": True}, ["trigger-pattern", "--query"]),
        ({"pattern": "XXX1"}, ["trigger-pattern", "--pattern", "XXX1"]),
    ],
)
def test_worker_trigger_pattern_arguments_parse(tmp_path, arguments, expected):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command("trigger-pattern", arguments, runtime)

    assert parsed.command == "trigger-pattern"
    assert worker.arguments_to_argv(
        worker._normalize_trigger_pattern_worker_arguments(
            "trigger-pattern",
            arguments,
        )
    ) == expected[1:]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": False},
        {"query": True, "pattern": "XXX1"},
        {},
        {"pattern": "XXXR"},
        {"source": "CHANnel1", "pattern": "XXX1"},
        {"level": 0.5, "pattern": "XXX1"},
        {"format": "hex", "pattern": "XXX1"},
        {"edge": "positive", "pattern": "XXX1"},
        {"edge_source": "CHANnel1", "pattern": "XXX1"},
        {"qualifier": "entered", "pattern": "XXX1"},
        {"time_seconds": 1e-6, "pattern": "XXX1"},
        {"greater_than_seconds": 1e-6, "pattern": "XXX1"},
        {"less_than_seconds": 1e-6, "pattern": "XXX1"},
        {"range_min_seconds": 1e-6, "pattern": "XXX1"},
        {"range_max_seconds": 2e-6, "pattern": "XXX1"},
    ],
)
def test_worker_trigger_pattern_rejects_invalid_arguments(tmp_path, arguments):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("trigger-pattern", arguments, runtime)


@pytest.mark.parametrize("command", ["pattern-trigger", "trigger-pattern-hex"])
def test_worker_rejects_trigger_pattern_aliases(command):
    with pytest.raises(OscilloscopeError):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": command,
                "arguments": {"query": True},
            }
        )


def test_worker_trigger_pattern_simulator_execution_sends_expected_scpi(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-pattern",
        {"pattern": "XXX1"},
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE PATTern",
        ":TRIGger:PATTern:FORMat ASCii",
        ':TRIGger:PATTern "XXX1"',
        ":TRIGger:PATTern:QUALifier ENTered",
        ":SYSTem:ERRor?",
    ]
