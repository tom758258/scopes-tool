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


def test_worker_trigger_tv_command_is_accepted():
    command, arguments, job_id = worker.validate_command_request(
        {
            "schema_version": worker.WORKER_SCHEMA_VERSION,
            "command": "trigger-tv",
            "arguments": {"query": True},
        }
    )

    assert command == "trigger-tv"
    assert arguments == {"query": True}
    assert job_id is None


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"query": True}, ["--query"]),
        (
            {
                "source_channel": 1,
                "standard": "ntsc",
                "mode": "field1",
                "polarity": "negative",
            },
            [
                "--source-channel",
                "1",
                "--standard",
                "ntsc",
                "--mode",
                "field1",
                "--polarity",
                "negative",
            ],
        ),
        (
            {
                "source_channel": 1,
                "standard": "ntsc",
                "mode": "line-field1",
                "line": 20,
                "polarity": "negative",
            },
            [
                "--source-channel",
                "1",
                "--standard",
                "ntsc",
                "--mode",
                "line-field1",
                "--line",
                "20",
                "--polarity",
                "negative",
            ],
        ),
    ],
)
def test_worker_trigger_tv_arguments_parse(tmp_path, arguments, expected):
    runtime = _runtime(tmp_path)

    parsed = worker.parse_domain_command("trigger-tv", arguments, runtime)

    assert parsed.command == "trigger-tv"
    assert worker.arguments_to_argv(
        worker._normalize_trigger_tv_worker_arguments("trigger-tv", arguments)
    ) == expected


def test_worker_trigger_tv_simulator_execution_sends_expected_scpi(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command(
        "trigger-tv",
        {
            "source_channel": 1,
            "standard": "ntsc",
            "mode": "line-field1",
            "line": 20,
            "polarity": "negative",
        },
        runtime,
    )

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["result"]["source_channel"] == 1
    assert payload["result"]["tv_mode"] == "line-field1"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE TV",
        ":TRIGger:TV:SOURce CHANnel1",
        ":TRIGger:TV:STANdard NTSC",
        ":TRIGger:TV:MODE LFIeld1",
        ":TRIGger:TV:LINE 20",
        ":TRIGger:TV:POLarity NEGative",
        ":SYSTem:ERRor?",
    ]


def test_worker_trigger_tv_query_simulator_execution(tmp_path):
    runtime = _runtime(tmp_path)
    parsed = worker.parse_domain_command("trigger-tv", {"query": True}, runtime)

    payload, exit_code = cli._execute_json_command(parsed)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["result"]["operation"] == "query"
    assert payload["result"]["source_raw"] == "CHAN1"
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE?",
        ":TRIGger:TV:SOURce?",
        ":TRIGger:TV:STANdard?",
        ":TRIGger:TV:MODE?",
        ":TRIGger:TV:LINE?",
        ":TRIGger:TV:POLarity?",
        ":SYSTem:ERRor?",
    ]


@pytest.mark.parametrize(
    "alias",
    [
        "channel",
        "source",
        "tv_source",
        "tv_standard",
        "trigger_standard",
        "tv_mode",
        "trigger_mode",
        "line_number",
        "field",
        "pol",
        "trigger_polarity",
        "polarity_raw",
        "sourceChannel",
        "source_channel_number",
    ],
)
def test_worker_trigger_tv_rejects_alias_keys(tmp_path, alias):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("trigger-tv", {alias: 1}, runtime)


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": False},
        {"query": True, "source_channel": 1},
        {
            "source_channel": 1,
            "standard": "ntsc",
            "mode": "field1",
        },
        {
            "source_channel": 1,
            "standard": "p1080",
            "mode": "field1",
            "polarity": "negative",
        },
        {
            "source_channel": 1,
            "standard": "ntsc",
            "mode": "all-lines",
            "line": 1,
            "polarity": "negative",
        },
        {
            "source_channel": 1,
            "standard": "ntsc",
            "mode": "line-field1",
            "polarity": "negative",
        },
    ],
)
def test_worker_trigger_tv_rejects_invalid_arguments(tmp_path, arguments):
    runtime = _runtime(tmp_path)

    with pytest.raises(OscilloscopeError):
        worker.parse_domain_command("trigger-tv", arguments, runtime)
