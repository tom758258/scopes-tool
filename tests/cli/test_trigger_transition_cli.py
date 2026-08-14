import json

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_core.simulator_backend import SimulatorBackend


def _json_stdout(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_trigger_transition_query_dry_run_json(capsys):
    assert cli.main(["trigger-transition", "--query", "--dry-run", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"] == {
        "operation": "query",
        "commands": [
            ":TRIGger:MODE?",
            ":TRIGger:TRANsition:SOURce?",
            ":TRIGger:TRANsition:SLOPe?",
            ":TRIGger:TRANsition:QUALifier?",
            ":TRIGger:TRANsition:TIME?",
        ],
    }
    assert payload["scpi"]["planned"] == payload["result"]["commands"] + [
        ":SYSTem:ERRor?"
    ]


def test_trigger_transition_greater_than_dry_run_json(capsys):
    assert (
        cli.main(
            [
                "trigger-transition",
                "--channel",
                "1",
                "--slope",
                "positive",
                "--qualifier",
                "greater-than",
                "--time-seconds",
                "5e-6",
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
        ":TRIGger:MODE TRANsition",
        ":TRIGger:TRANsition:SOURce CHANnel1",
        ":TRIGger:LEVel:LOW -0.5,CHANnel1",
        ":TRIGger:LEVel:HIGH 0.5,CHANnel1",
        ":TRIGger:TRANsition:SLOPe POSitive",
        ":TRIGger:TRANsition:TIME 5e-06",
        ":TRIGger:TRANsition:QUALifier GREaterthan",
    ]


def test_trigger_transition_less_than_dry_run_json(capsys):
    assert (
        cli.main(
            [
                "trigger-transition",
                "--channel",
                "1",
                "--slope",
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
    assert payload["result"]["commands"] == [
        ":TRIGger:MODE TRANsition",
        ":TRIGger:TRANsition:SOURce CHANnel1",
        ":TRIGger:LEVel:LOW -0.25,CHANnel1",
        ":TRIGger:LEVel:HIGH 0.75,CHANnel1",
        ":TRIGger:TRANsition:SLOPe NEGative",
        ":TRIGger:TRANsition:TIME 2e-06",
        ":TRIGger:TRANsition:QUALifier LESSthan",
    ]


def test_trigger_transition_query_simulate_json_reports_default_levels(capsys):
    assert cli.main(["trigger-transition", "--query", "--simulate", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["ok"] is True
    assert payload["result"]["mode"] == "edge"
    assert payload["result"]["source"] == "CHAN1"
    assert payload["result"]["slope"] == "positive"
    assert payload["result"]["qualifier"] == "greater-than"
    assert payload["result"]["time_seconds"] == 1e-6
    assert payload["result"]["low_level_volts"] == -0.5
    assert payload["result"]["high_level_volts"] == 0.5
    assert payload["result"]["commands"] == [
        ":TRIGger:MODE?",
        ":TRIGger:TRANsition:SOURce?",
        ":TRIGger:TRANsition:SLOPe?",
        ":TRIGger:TRANsition:QUALifier?",
        ":TRIGger:TRANsition:TIME?",
        ":TRIGger:LEVel:LOW? CHANnel1",
        ":TRIGger:LEVel:HIGH? CHANnel1",
    ]
    assert payload["scpi"]["sent"] == [
        "*IDN?",
        ":TRIGger:MODE?",
        ":TRIGger:TRANsition:SOURce?",
        ":TRIGger:TRANsition:SLOPe?",
        ":TRIGger:TRANsition:QUALifier?",
        ":TRIGger:TRANsition:TIME?",
        ":TRIGger:LEVel:LOW? CHANnel1",
        ":TRIGger:LEVel:HIGH? CHANnel1",
        ":SYSTem:ERRor?",
    ]


def test_trigger_transition_query_simulate_json_skips_levels_for_non_analog_source(
    monkeypatch, capsys
):
    backend = SimulatorBackend(
        transition_source_channel=None,
        transition_source_raw="EXTernal",
    )
    monkeypatch.setattr(runtime, "SimulatorBackend", lambda **kwargs: backend)

    assert cli.main(["trigger-transition", "--query", "--simulate", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["result"]["source"] == "EXTernal"
    assert payload["result"]["source_kind"] is None
    assert payload["result"]["channel"] is None
    assert payload["result"]["low_level_volts"] is None
    assert payload["result"]["high_level_volts"] is None
    assert payload["result"]["commands"] == [
        ":TRIGger:MODE?",
        ":TRIGger:TRANsition:SOURce?",
        ":TRIGger:TRANsition:SLOPe?",
        ":TRIGger:TRANsition:QUALifier?",
        ":TRIGger:TRANsition:TIME?",
    ]
    assert ":TRIGger:LEVel:LOW? CHANnel1" not in payload["scpi"]["sent"]
    assert ":TRIGger:LEVel:HIGH? CHANnel1" not in payload["scpi"]["sent"]


@pytest.mark.parametrize(
    "argv",
    [
        ["trigger-transition", "--query", "--channel", "1", "--dry-run", "--json"],
        [
            "trigger-transition",
            "--channel",
            "1",
            "--slope",
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
            "trigger-transition",
            "--channel",
            "1",
            "--slope",
            "positive",
            "--qualifier",
            "greater-than",
            "--time-seconds",
            "1e-6",
            "--high-level-volts",
            "0.5",
            "--dry-run",
            "--json",
        ],
        [
            "trigger-transition",
            "--channel",
            "1",
            "--slope",
            "positive",
            "--qualifier",
            "greater-than",
            "--time-seconds",
            "1e-6",
            "--low-level-volts",
            "0.5",
            "--high-level-volts",
            "0.5",
            "--dry-run",
            "--json",
        ],
        [
            "trigger-transition",
            "--channel",
            "1",
            "--slope",
            "positive",
            "--qualifier",
            "greater-than",
            "--time-seconds",
            "1e-6",
            "--low-level-volts",
            "0.75",
            "--high-level-volts",
            "0.5",
            "--dry-run",
            "--json",
        ],
    ],
)
def test_trigger_transition_rejects_invalid_argument_combinations(argv, capsys):
    assert cli.main(argv) == 1
    payload = _json_stdout(capsys)
    assert payload["ok"] is False


@pytest.mark.parametrize(
    "argv",
    [
        [
            "trigger-transition",
            "--channel",
            "1",
            "--slope",
            "either",
            "--qualifier",
            "greater-than",
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
            "trigger-transition",
            "--channel",
            "1",
            "--slope",
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
        ],
    ],
)
def test_trigger_transition_argparse_rejects_invalid_choices(argv):
    with pytest.raises(SystemExit):
        cli.main(argv)


@pytest.mark.parametrize("command", ["transition-trigger", "trigger-rise-fall", "trigger-rise-time"])
def test_trigger_transition_rejects_unsupported_aliases(command):
    with pytest.raises(SystemExit):
        cli.main([command, "--query", "--dry-run", "--json"])


def test_trigger_transition_rejects_digital_source_options():
    with pytest.raises(SystemExit):
        cli.main(["trigger-transition", "--digital", "0", "--dry-run", "--json"])


def test_trigger_transition_does_not_emit_acquisition_or_capture_scpi(capsys):
    assert (
        cli.main(
            [
                "trigger-transition",
                "--channel",
                "1",
                "--slope",
                "positive",
                "--qualifier",
                "greater-than",
                "--time-seconds",
                "5e-6",
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
