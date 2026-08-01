import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.measurements import measurement_results_query


def _runtime(tmp_path, model="keysight-dsox4024a"):
    return worker.WorkerRuntime(
        "127.0.0.1", 0, "simulate", model, None, tmp_path, 1, "jsonl"
    )


def test_measure_results_worker_accepts_empty_arguments_without_extra_flags(tmp_path):
    accepted = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "measure-results",
            "arguments": {},
        }
    )

    assert "measure-results" in worker.DOMAIN_COMMANDS
    assert accepted[:2] == ("measure-results", {})
    assert worker.arguments_to_argv({}) == []
    assert worker.parse_domain_command(
        accepted[0], accepted[1], _runtime(tmp_path)
    ).command == "measure-results"


@pytest.mark.parametrize(
    "model",
    ["keysight-dsox3024a", "keysight-dsox4034a"],
)
def test_measure_results_worker_reuses_read_only_cli_path(tmp_path, model):
    parsed = worker.parse_domain_command(
        "measure-results", {}, _runtime(tmp_path, model)
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["scpi"]["sent"] == ["*IDN?", measurement_results_query()]
    assert payload["result"]["raw"]
    assert payload["result"]["items"] == []
    assert payload["result"]["statistics_items"]


def test_measure_results_worker_rejects_2000x_through_capability_guard(tmp_path):
    with pytest.raises(OscilloscopeError, match="2000X"):
        worker.parse_domain_command(
            "measure-results", {}, _runtime(tmp_path, "keysight-dsox2004a")
        )


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("measure-clear", {}),
        ("measure-show", {"on": True}),
        ("measure-show", {"query": True}),
        ("measure-source", {"source_channel": 1}),
        ("measure-source", {"source_channel": 1, "source2_channel": 2}),
        ("measure-source", {"query": True}),
        ("measure-window", {"window": "main"}),
        ("measure-window", {"query": True}),
    ],
)
def test_measurement_worker_accepts_maps_and_routes_simulator(tmp_path, command, arguments):
    assert worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": command,
            "arguments": arguments,
        }
    )[:2] == (command, arguments)
    parsed = worker.parse_domain_command(command, arguments, _runtime(tmp_path))
    payload, exit_code = cli._execute_json_command(parsed)
    assert exit_code == 0
    assert payload["command"] == command
    assert payload["mode"] == "simulate"


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("measure-show", {"off": True}),
        ("measure-show", {"query": False}),
        ("measure-source", {}),
        ("measure-source", {"source_channel": 0}),
        ("measure-source", {"source_channel": 5}),
        ("measure-window", {}),
        ("measure-window", {"window": "screen"}),
    ],
)
def test_measurement_worker_rejects_invalid_arguments(tmp_path, command, arguments):
    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command(command, arguments, _runtime(tmp_path))

