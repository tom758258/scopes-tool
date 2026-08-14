import json

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.simulator_backend import SimulatorBackend


def _json_stdout(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_trigger_runt_query_dry_run_json(capsys):
    assert cli.main(["trigger-runt", "--query", "--dry-run", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"] == {
        "operation": "query",
        "commands": [
            ":TRIGger:MODE?",
            ":TRIGger:RUNT:SOURce?",
            ":TRIGger:RUNT:POLarity?",
            ":TRIGger:RUNT:QUALifier?",
            ":TRIGger:RUNT:TIME?",
        ],
    }
    assert payload["scpi"]["planned"] == payload["result"]["commands"] + [":SYSTem:ERRor?"]


def test_trigger_runt_none_dry_run_json_skips_time(capsys):
    assert (
        cli.main(
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
        ":TRIGger:MODE RUNT",
        ":TRIGger:RUNT:SOURce CHANnel1",
        ":TRIGger:LEVel:LOW -0.5,CHANnel1",
        ":TRIGger:LEVel:HIGH 0.5,CHANnel1",
        ":TRIGger:RUNT:POLarity EITHer",
        ":TRIGger:RUNT:QUALifier NONE",
    ]


def test_trigger_runt_greater_than_dry_run_json(capsys):
    assert (
        cli.main(
            [
                "trigger-runt",
                "--channel",
                "1",
                "--polarity",
                "positive",
                "--qualifier",
                "greater-than",
                "--time-seconds",
                "5e-6",
                "--low-level-volts",
                "-0.25",
                "--high-level-volts",
                "0.75",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["commands"] == [
        ":TRIGger:MODE RUNT",
        ":TRIGger:RUNT:SOURce CHANnel1",
        ":TRIGger:LEVel:LOW -0.25,CHANnel1",
        ":TRIGger:LEVel:HIGH 0.75,CHANnel1",
        ":TRIGger:RUNT:POLarity POSitive",
        ":TRIGger:RUNT:TIME 5e-06",
        ":TRIGger:RUNT:QUALifier GREaterthan",
    ]


def test_trigger_runt_less_than_dry_run_json(capsys):
    assert (
        cli.main(
            [
                "trigger-runt",
                "--channel",
                "1",
                "--polarity",
                "negative",
                "--qualifier",
                "less-than",
                "--time-seconds",
                "2e-6",
                "--low-level-volts",
                "-0.25",
                "--high-level-volts",
                "0.75",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    assert payload["result"]["commands"][-2:] == [
        ":TRIGger:RUNT:TIME 2e-06",
        ":TRIGger:RUNT:QUALifier LESSthan",
    ]


def test_trigger_runt_query_simulate_json_reports_default_levels(capsys):
    assert cli.main(["trigger-runt", "--query", "--simulate", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"]["mode"] == "edge"
    assert payload["result"]["source"] == "CHAN1"
    assert payload["result"]["low_level_volts"] == -0.5
    assert payload["result"]["high_level_volts"] == 0.5
    assert payload["result"]["commands"] == [
        ":TRIGger:MODE?",
        ":TRIGger:RUNT:SOURce?",
        ":TRIGger:RUNT:POLarity?",
        ":TRIGger:RUNT:QUALifier?",
        ":TRIGger:RUNT:TIME?",
        ":TRIGger:LEVel:LOW? CHANnel1",
        ":TRIGger:LEVel:HIGH? CHANnel1",
    ]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE?",
        ":TRIGger:RUNT:SOURce?",
        ":TRIGger:RUNT:POLarity?",
        ":TRIGger:RUNT:QUALifier?",
        ":TRIGger:RUNT:TIME?",
        ":TRIGger:LEVel:LOW? CHANnel1",
        ":TRIGger:LEVel:HIGH? CHANnel1",
        ":SYSTem:ERRor?",
    ]


def test_trigger_runt_query_simulate_json_skips_levels_for_non_analog_source(
    monkeypatch, capsys
):
    backend = SimulatorBackend(runt_source_channel=None, runt_source_raw="DIGital7")
    monkeypatch.setattr(runtime, "SimulatorBackend", lambda **kwargs: backend)

    assert cli.main(["trigger-runt", "--query", "--simulate", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["source"] == "DIGital7"
    assert payload["result"]["source_kind"] is None
    assert payload["result"]["channel"] is None
    assert payload["result"]["low_level_volts"] is None
    assert payload["result"]["high_level_volts"] is None
    assert payload["result"]["commands"] == [
        ":TRIGger:MODE?",
        ":TRIGger:RUNT:SOURce?",
        ":TRIGger:RUNT:POLarity?",
        ":TRIGger:RUNT:QUALifier?",
        ":TRIGger:RUNT:TIME?",
    ]
    assert ":TRIGger:LEVel:LOW? CHANnel1" not in payload["scpi"]["sent"]
    assert ":TRIGger:LEVel:HIGH? CHANnel1" not in payload["scpi"]["sent"]


@pytest.mark.parametrize(
    "argv",
    [
        ["trigger-runt", "--query", "--channel", "1", "--dry-run", "--json"],
        [
            "trigger-runt",
            "--channel",
            "1",
            "--polarity",
            "positive",
            "--qualifier",
            "greater-than",
            "--low-level-volts",
            "-0.5",
            "--high-level-volts",
            "0.5",
            "--dry-run",
            "--json",
        ],
        [
            "trigger-runt",
            "--channel",
            "1",
            "--polarity",
            "positive",
            "--qualifier",
            "none",
            "--time-seconds",
            "1e-6",
            "--low-level-volts",
            "-0.5",
            "--high-level-volts",
            "0.5",
            "--dry-run",
            "--json",
        ],
        [
            "trigger-runt",
            "--channel",
            "1",
            "--polarity",
            "positive",
            "--qualifier",
            "none",
            "--low-level-volts",
            "0.5",
            "--high-level-volts",
            "0.5",
            "--dry-run",
            "--json",
        ],
    ],
)
def test_trigger_runt_rejects_invalid_argument_combinations(argv, capsys):
    assert cli.main(argv) == 1
    payload = _json_stdout(capsys)
    assert payload["ok"] is False


@pytest.mark.parametrize("command", ["runt-trigger", "trigger-runt-width"])
def test_trigger_runt_rejects_unsupported_aliases(command):
    with pytest.raises(SystemExit):
        cli.main([command, "--query", "--dry-run", "--json"])


def test_trigger_runt_rejects_underscore_qualifier():
    with pytest.raises(SystemExit):
        cli.main(
            [
                "trigger-runt",
                "--channel",
                "1",
                "--polarity",
                "positive",
                "--qualifier",
                "greater_than",
                "--time-seconds",
                "1e-6",
                "--low-level-volts",
                "-0.5",
                "--high-level-volts",
                "0.5",
                "--dry-run",
                "--json",
            ]
        )


def test_trigger_runt_rejects_digital_source_options():
    with pytest.raises(SystemExit):
        cli.main(["trigger-runt", "--digital", "0", "--dry-run", "--json"])


def test_trigger_runt_does_not_emit_acquisition_or_capture_scpi(capsys):
    assert (
        cli.main(
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
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )

    payload = _json_stdout(capsys)
    planned = payload["scpi"]["planned"]
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
        assert all(item != command and not item.startswith(f"{command} ") for item in planned)
