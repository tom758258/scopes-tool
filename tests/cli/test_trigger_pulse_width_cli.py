import json

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.simulator_backend import SimulatorBackend


def _json_stdout(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_trigger_pulse_width_query_dry_run_json(capsys):
    assert cli.main(["trigger-pulse-width", "--query", "--dry-run", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"] == {
        "operation": "query",
        "commands": [
            ":TRIGger:MODE?",
            ":TRIGger:GLITch:SOURce?",
            ":TRIGger:GLITch:POLarity?",
            ":TRIGger:GLITch:QUALifier?",
            ":TRIGger:GLITch:GREaterthan?",
            ":TRIGger:GLITch:LESSthan?",
            ":TRIGger:GLITch:RANGe?",
            ":TRIGger:GLITch:LEVel?",
        ],
    }
    assert payload["scpi"]["planned"] == payload["result"]["commands"] + [":SYSTem:ERRor?"]


def test_trigger_pulse_width_less_than_dry_run_json(capsys):
    assert (
        cli.main(
            [
                "trigger-pulse-width",
                "--channel",
                "1",
                "--polarity",
                "positive",
                "--qualifier",
                "less-than",
                "--time-seconds",
                "1e-6",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["operation"] == "set"
    assert payload["result"]["state_changing"] is True
    assert payload["result"]["commands"] == [
        ":TRIGger:MODE GLITch",
        ":TRIGger:GLITch:SOURce CHANnel1",
        ":TRIGger:GLITch:POLarity POSitive",
        ":TRIGger:GLITch:LESSthan 1e-06",
        ":TRIGger:GLITch:QUALifier LESSthan",
    ]


def test_trigger_pulse_width_greater_than_with_level_dry_run_json(capsys):
    assert (
        cli.main(
            [
                "trigger-pulse-width",
                "--channel",
                "1",
                "--polarity",
                "negative",
                "--qualifier",
                "greater-than",
                "--time-seconds",
                "5e-6",
                "--level-volts",
                "0.5",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["commands"] == [
        ":TRIGger:MODE GLITch",
        ":TRIGger:GLITch:SOURce CHANnel1",
        ":TRIGger:GLITch:LEVel 0.5,CHANnel1",
        ":TRIGger:GLITch:POLarity NEGative",
        ":TRIGger:GLITch:GREaterthan 5e-06",
        ":TRIGger:GLITch:QUALifier GREaterthan",
    ]


def test_trigger_pulse_width_range_dry_run_json_maps_max_min(capsys):
    assert (
        cli.main(
            [
                "trigger-pulse-width",
                "--channel",
                "1",
                "--polarity",
                "positive",
                "--qualifier",
                "range",
                "--min-time-seconds",
                "1e-6",
                "--max-time-seconds",
                "10e-6",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["commands"] == [
        ":TRIGger:MODE GLITch",
        ":TRIGger:GLITch:SOURce CHANnel1",
        ":TRIGger:GLITch:POLarity POSitive",
        ":TRIGger:GLITch:RANGe 1e-05,1e-06",
        ":TRIGger:GLITch:QUALifier RANGe",
    ]


def test_trigger_pulse_width_query_simulate_json_reports_default_level(capsys):
    assert cli.main(["trigger-pulse-width", "--query", "--simulate", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"]["mode"] == "edge"
    assert payload["result"]["source"] == "CHAN1"
    assert payload["result"]["level_volts"] == 0.0
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE?",
        ":TRIGger:GLITch:SOURce?",
        ":TRIGger:GLITch:POLarity?",
        ":TRIGger:GLITch:QUALifier?",
        ":TRIGger:GLITch:GREaterthan?",
        ":TRIGger:GLITch:LESSthan?",
        ":TRIGger:GLITch:RANGe?",
        ":TRIGger:GLITch:LEVel?",
        ":SYSTem:ERRor?",
    ]


def test_trigger_pulse_width_query_simulate_json_handles_digital_source_and_none_level(
    monkeypatch, capsys
):
    backend = SimulatorBackend(glitch_source_channel=None, glitch_source_raw="DIGital7", glitch_level=None)
    monkeypatch.setattr(runtime, "SimulatorBackend", lambda **kwargs: backend)

    assert cli.main(["trigger-pulse-width", "--query", "--simulate", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["source_kind"] == "digital"
    assert payload["result"]["digital"] == 7
    assert payload["result"]["channel"] is None
    assert payload["result"]["level_volts"] is None
    assert payload["result"]["raw"]["level"] == "NONE"


@pytest.mark.parametrize(
    "argv",
    [
        ["trigger-pulse-width", "--query", "--channel", "1", "--dry-run", "--json"],
        [
            "trigger-pulse-width",
            "--channel",
            "1",
            "--polarity",
            "positive",
            "--qualifier",
            "less-than",
            "--dry-run",
            "--json",
        ],
        [
            "trigger-pulse-width",
            "--channel",
            "1",
            "--polarity",
            "positive",
            "--qualifier",
            "range",
            "--min-time-seconds",
            "1e-6",
            "--max-time-seconds",
            "1e-6",
            "--dry-run",
            "--json",
        ],
    ],
)
def test_trigger_pulse_width_rejects_invalid_argument_combinations(argv, capsys):
    assert cli.main(argv) == 1
    payload = _json_stdout(capsys)
    assert payload["ok"] is False


@pytest.mark.parametrize(
    "command",
    ["trigger-glitch", "trigger-pulse", "pulse-width", "glitch-trigger", "trigger-width"],
)
def test_trigger_pulse_width_rejects_unsupported_aliases(command):
    with pytest.raises(SystemExit):
        cli.main([command, "--query", "--dry-run", "--json"])


def test_trigger_pulse_width_rejects_digital_source_options():
    with pytest.raises(SystemExit):
        cli.main(["trigger-pulse-width", "--digital", "0", "--dry-run", "--json"])


def test_trigger_pulse_width_does_not_emit_acquisition_or_capture_scpi(capsys):
    assert (
        cli.main(
            [
                "trigger-pulse-width",
                "--channel",
                "1",
                "--polarity",
                "positive",
                "--qualifier",
                "range",
                "--min-time-seconds",
                "1e-6",
                "--max-time-seconds",
                "10e-6",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    planned = "\n".join(payload["scpi"]["planned"])
    forbidden = [
        ":RUN",
        ":STOP",
        ":SINGle",
        ":TRIGger:FORCe",
        ":DIGitize",
        ":WAVeform:DATA?",
        ":ACQuire",
        ":CAPTure",
    ]
    for command in forbidden:
        assert command not in planned
