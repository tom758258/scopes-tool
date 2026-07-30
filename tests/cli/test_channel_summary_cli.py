import json

from scopes_tool_cli import cli


def test_channel_summary_simulate_json_returns_channels(capsys):
    assert (
        cli.main(
            [
                "channel-summary",
                "--simulate",
                "--model",
                "keysight-dsox4034a",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    channels = payload["result"]["channels"]
    assert len(channels) == 4
    assert set(channels[0]) == {
        "channel",
        "display",
        "label",
        "scale",
        "range",
        "offset",
        "coupling",
        "impedance",
        "invert",
        "bandwidth_limit",
        "units",
        "vernier",
        "probe_ratio",
        "probe_skew",
    }


def test_channel_summary_dry_run_plans_queries_only(capsys):
    assert (
        cli.main(
            [
                "channel-summary",
                "--dry-run",
                "--model",
                "keysight-dsox4034a",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    planned = payload["scpi"]["planned"]
    assert planned[0] == "*IDN?"
    assert all(command.endswith("?") for command in planned)
    assert payload["scpi"]["sent"] == []
    assert payload["result"] == {"channels": []}
