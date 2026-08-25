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
                queue_max=1,
        output_format="jsonl",
    )


def test_worker_trigger_setup_hold_command_is_accepted():
    command, arguments, job_id = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "trigger-setup-hold",
            "arguments": {"query": True},
        }
    )

    assert command == "trigger-setup-hold"
    assert arguments == {"query": True}
    assert job_id is None


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"query": True}, ["--query"]),
        (
            {
                "clock_channel": 1,
                "data_channel": 2,
                "slope": "positive",
                "setup_time": 1e-9,
                "hold_time": 1e-9,
            },
            [
                "--clock-channel",
                "1",
                "--data-channel",
                "2",
                "--slope",
                "positive",
                "--setup-time",
                "1e-09",
                "--hold-time",
                "1e-09",
            ],
        ),
    ],
)
def test_worker_trigger_setup_hold_arguments_parse(tmp_path, arguments, expected):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command("trigger-setup-hold", arguments, runtime)

    assert parsed.command == "trigger-setup-hold"
    assert worker.arguments_to_argv(
        worker._normalize_trigger_setup_hold_worker_arguments(
            "trigger-setup-hold", arguments
        )
    ) == expected


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": False},
        {"query": None},
        {"query": True, "clock_channel": 1},
        {"clock_channel": 1},
        {
            "clock_channel": 1,
            "data_channel": 2,
            "slope": "positive",
            "setup_time": 1e-9,
        },
        {
            "clock_channel": 1,
            "data_channel": 2,
            "slope": "rising",
            "setup_time": 1e-9,
            "hold_time": 1e-9,
        },
        {
            "clock_channel": 1,
            "data_channel": 5,
            "slope": "positive",
            "setup_time": 1e-9,
            "hold_time": 1e-9,
        },
        {
            "clock_channel": 1,
            "data_channel": 2,
            "slope": "positive",
            "setup_time": 0,
            "hold_time": 1e-9,
        },
        {"clock_source": "CHANnel1"},
        {"clock_channel": 1, "unknown": None},
        {"data_channel": 2, "digital": False},
        {"setup_time_seconds": 1e-9},
        {"hold_time_seconds": 1e-9},
    ],
)
def test_worker_trigger_setup_hold_rejects_invalid_arguments(tmp_path, arguments):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("trigger-setup-hold", arguments, runtime)


def test_worker_trigger_setup_hold_simulator_execution_sends_expected_scpi(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-setup-hold",
        {
            "clock_channel": 1,
            "data_channel": 2,
            "slope": "positive",
            "setup_time": 1e-9,
            "hold_time": 1e-9,
        },
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["files"] == []
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE SHOLd",
        ":TRIGger:SHOLd:SOURce:CLOCk CHANnel1",
        ":TRIGger:SHOLd:SOURce:DATA CHANnel2",
        ":TRIGger:SHOLd:SLOPe POSitive",
        ":TRIGger:SHOLd:TIME:SETup 1e-09",
        ":TRIGger:SHOLd:TIME:HOLD 1e-09",
        ":SYSTem:ERRor?",
    ]


def test_worker_trigger_setup_hold_live_route_builds_cli_args(tmp_path):
    runtime = _runtime(tmp_path, mode="live")
    parsed = worker.parse_domain_command(
        "trigger-setup-hold",
        {
            "clock_channel": 1,
            "data_channel": 2,
            "slope": "positive",
            "setup_time": 1e-9,
            "hold_time": 1e-9,
        },
        runtime,
    )

    assert parsed.command == "trigger-setup-hold"
    assert parsed.live is True
    assert parsed.resource == "USB0::SIM::INSTR"
    assert parsed.clock_channel == 1
    assert parsed.data_channel == 2
    assert parsed.slope == "positive"
    assert parsed.setup_time == 1e-9
    assert parsed.hold_time == 1e-9
