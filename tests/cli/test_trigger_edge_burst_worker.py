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


def test_worker_trigger_edge_burst_command_is_accepted():
    command, arguments, job_id = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "trigger-edge-burst",
            "arguments": {"query": True},
        }
    )

    assert command == "trigger-edge-burst"
    assert arguments == {"query": True}
    assert job_id is None


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"query": True}, ["trigger-edge-burst", "--query"]),
        (
            {
                "source_channel": 1,
                "slope": "positive",
                "count": 3,
                "idle_time": 1e-6,
            },
            [
                "trigger-edge-burst",
                "--source-channel",
                "1",
                "--slope",
                "positive",
                "--count",
                "3",
                "--idle-time",
                "1e-06",
            ],
        ),
        (
            {
                "source_channel": 1,
                "slope": "negative",
                "count": 5,
                "idle_time": 1e-5,
                "level_volts": 0.5,
            },
            [
                "trigger-edge-burst",
                "--source-channel",
                "1",
                "--slope",
                "negative",
                "--count",
                "5",
                "--idle-time",
                "1e-05",
                "--level-volts",
                "0.5",
            ],
        ),
    ],
)
def test_worker_trigger_edge_burst_arguments_parse(tmp_path, arguments, expected):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command("trigger-edge-burst", arguments, runtime)

    assert parsed.command == "trigger-edge-burst"
    assert worker.arguments_to_argv(
        worker._normalize_trigger_edge_burst_worker_arguments(
            "trigger-edge-burst",
            arguments,
        )
    ) == expected[1:]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": False},
        {"query": True, "source_channel": 1},
        {"channel": 1},
        {"source": "CHANnel1"},
        {"edge_count": 3},
        {"idle_time_seconds": 1e-6},
        {"time_seconds": 1e-6},
        {"trigger_level": 0.5},
        {"level": 0.5},
    ],
)
def test_worker_trigger_edge_burst_rejects_invalid_arguments(tmp_path, arguments):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("trigger-edge-burst", arguments, runtime)


def test_worker_trigger_edge_burst_simulator_execution_sends_expected_scpi(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-edge-burst",
        {
            "source_channel": 1,
            "slope": "positive",
            "count": 3,
            "idle_time": 1e-6,
            "level_volts": 0.5,
        },
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["files"] == []
    assert payload["result"]["source_channel"] == 1
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE EBURst",
        ":TRIGger:EBURst:SOURce CHANnel1",
        ":TRIGger:EBURst:SLOPe POSitive",
        ":TRIGger:EBURst:COUNt 3",
        ":TRIGger:EBURst:IDLE 1e-06",
        ":TRIGger:EDGE:LEVel 0.5, CHANnel1",
        ":SYSTem:ERRor?",
    ]


def test_worker_trigger_edge_burst_query_simulator_execution(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-edge-burst",
        {"query": True},
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["raw_source"] == "CHAN1"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE?",
        ":TRIGger:EBURst:SOURce?",
        ":TRIGger:EBURst:SLOPe?",
        ":TRIGger:EBURst:COUNt?",
        ":TRIGger:EBURst:IDLE?",
        ":TRIGger:EDGE:LEVel? CHANnel1",
        ":SYSTem:ERRor?",
    ]
