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


def test_worker_allowlist_includes_trigger_or():
    worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "trigger-or",
            "arguments": {"query": True},
        }
    )


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"query": True}, ["trigger-or", "--query"]),
        ({"pattern": "XXXR"}, ["trigger-or", "--pattern", "XXXR"]),
    ],
)
def test_worker_trigger_or_arguments_parse(tmp_path, arguments, expected):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command("trigger-or", arguments, runtime)

    assert parsed.command == "trigger-or"
    assert worker.arguments_to_argv(
        worker._normalize_trigger_or_worker_arguments(
            "trigger-or",
            arguments,
        )
    ) == expected[1:]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": False},
        {"query": True, "pattern": "XXXR"},
        {},
        {"pattern": "XXX1"},
        {"mask": "XXXR"},
        {"channels": [1]},
        {"source": "CHANnel1", "pattern": "XXXR"},
        {"level": 0.5, "pattern": "XXXR"},
        {"format": "ascii", "pattern": "XXXR"},
        {"edge": "positive", "pattern": "XXXR"},
        {"edge_source": "CHANnel1", "pattern": "XXXR"},
        {"qualifier": "entered", "pattern": "XXXR"},
        {"time_seconds": 1e-6, "pattern": "XXXR"},
    ],
)
def test_worker_trigger_or_rejects_invalid_arguments(tmp_path, arguments):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("trigger-or", arguments, runtime)


@pytest.mark.parametrize("command", ["or-trigger", "trigger-or-mask"])
def test_worker_rejects_trigger_or_aliases(command):
    with pytest.raises(OscilloscopeError):
        worker.validate_command_request(
            {
                "schema_version": worker.WORKER_SCHEMA_VERSION,
                "command": command,
                "arguments": {"query": True},
            }
        )


def test_worker_trigger_or_simulator_execution_sends_expected_scpi(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-or",
        {"pattern": "XXXR"},
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["files"] == []
    assert payload["result"]["pattern"] == "XXXR"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE OR",
        ':TRIGger:OR "XXXR"',
        ":SYSTem:ERRor?",
    ]


def test_worker_trigger_or_query_simulator_execution(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-or",
        {"query": True},
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["raw_pattern"] == '"XXXX"'
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE?",
        ":TRIGger:OR?",
        ":SYSTem:ERRor?",
    ]
