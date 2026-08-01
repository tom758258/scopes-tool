import pytest

from scopes_tool_cli import cli, worker
from scopes_tool_core.errors import OscilloscopeError


def _runtime(tmp_path, *, mode="simulate"):
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode=mode,
        model="keysight-dsox4024a",
        resource="USB0::SIM::INSTR" if mode == "live" else None,
        artifact_root=tmp_path,
        queue_max=1,
        output_format="jsonl",
    )


def test_worker_trigger_delay_command_is_accepted():
    command, arguments, job_id = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "trigger-delay",
            "arguments": {"query": True},
        }
    )

    assert command == "trigger-delay"
    assert arguments == {"query": True}
    assert job_id is None


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"query": True}, ["trigger-delay", "--query"]),
        (
            {
                "arm_channel": 1,
                "arm_slope": "positive",
                "trigger_channel": 2,
                "trigger_slope": "negative",
                "time_seconds": 1e-6,
                "count": 2,
            },
            [
                "trigger-delay",
                "--arm-channel",
                "1",
                "--arm-slope",
                "positive",
                "--trigger-channel",
                "2",
                "--trigger-slope",
                "negative",
                "--time-seconds",
                "1e-06",
                "--count",
                "2",
            ],
        ),
    ],
)
def test_worker_trigger_delay_arguments_parse(tmp_path, arguments, expected):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command("trigger-delay", arguments, runtime)

    assert parsed.command == "trigger-delay"
    assert worker.arguments_to_argv(
        worker._normalize_trigger_delay_worker_arguments("trigger-delay", arguments)
    ) == expected[1:]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": False},
        {"query": True, "arm_channel": 1},
        {"arm_source": "CHANnel1"},
        {"trigger_source": "CHANnel1"},
        {"digital": 0},
        {"level_volts": 0.5},
        {"arm_level_volts": 0.5},
        {"trigger_level_volts": 0.5},
    ],
)
def test_worker_trigger_delay_rejects_invalid_arguments(tmp_path, arguments):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("trigger-delay", arguments, runtime)


def test_worker_trigger_delay_simulator_execution_sends_expected_scpi(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-delay",
        {
            "arm_channel": 1,
            "arm_slope": "positive",
            "trigger_channel": 2,
            "trigger_slope": "negative",
            "time_seconds": 1e-6,
            "count": 2,
        },
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE DELay",
        ":TRIGger:DELay:ARM:SOURce CHANnel1",
        ":TRIGger:DELay:ARM:SLOPe POSitive",
        ":TRIGger:DELay:TDELay:TIME 1e-06",
        ":TRIGger:DELay:TRIGger:COUNt 2",
        ":TRIGger:DELay:TRIGger:SOURce CHANnel2",
        ":TRIGger:DELay:TRIGger:SLOPe NEGative",
        ":SYSTem:ERRor?",
    ]


def test_worker_trigger_delay_live_route_builds_cli_args(tmp_path):
    runtime = _runtime(tmp_path, mode="live")
    parsed = worker.parse_domain_command(
        "trigger-delay",
        {
            "arm_channel": 1,
            "arm_slope": "positive",
            "trigger_channel": 2,
            "trigger_slope": "negative",
            "time_seconds": 1e-6,
            "count": 2,
        },
        runtime,
    )

    assert parsed.command == "trigger-delay"
    assert parsed.live is True
    assert parsed.resource == "USB0::SIM::INSTR"
    assert parsed.arm_channel == 1
    assert parsed.arm_slope == "positive"
    assert parsed.trigger_channel == 2
    assert parsed.trigger_slope == "negative"
    assert parsed.time_seconds == 1e-6
    assert parsed.count == 2
