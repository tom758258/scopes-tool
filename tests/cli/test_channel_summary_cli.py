import json

from scopes_tool_cli import cli
from scopes_tool_core import visa_backend


class _LiveResource:
    timeout = 2000

    def query(self, command):
        if command == "*IDN?":
            return "KEYSIGHT TECHNOLOGIES,DSOX4034A,MY00000000,07.20"
        if command.endswith(":DISPlay?"):
            return "1"
        if command.endswith(":LABel?"):
            return '"INPUT"'
        if command.endswith(":SCALe?"):
            return "0.5"
        if command.endswith(":RANGe?"):
            return "4.0"
        if command.endswith(":OFFSet?") or command.endswith(":PROBe:SKEW?"):
            return "0.0"
        if command.endswith(":COUPling?"):
            return "DC"
        if command.endswith(":IMPedance?"):
            return "ONEMeg"
        if command.endswith(":INVert?") or command.endswith(":BWLimit?"):
            return "0"
        if command.endswith(":UNITs?"):
            return "VOLT"
        if command.endswith(":VERNier?"):
            return "0"
        if command.endswith(":PROBe?"):
            return "10.0"
        raise AssertionError(f"unexpected query: {command}")

    def close(self):
        pass


class _LiveResourceManager:
    visalib = "fake live VISA"

    def __init__(self):
        self.resource = _LiveResource()

    def open_resource(self, resource_name):
        return self.resource

    def close(self):
        pass


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


def test_channel_summary_live_json_log_scpi_reports_sent_history(
    monkeypatch, capsys
):
    manager = _LiveResourceManager()
    monkeypatch.setattr(
        visa_backend,
        "_create_resource_manager",
        lambda visa_library=None: manager,
    )

    assert (
        cli.main(
            [
                "channel-summary",
                "--resource",
                "USB0::FAKE::INSTR",
                "--json",
                "--log-scpi",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert len(payload["result"]["channels"]) == 4
    assert payload["scpi"]["sent"][0] == "*IDN?"
    assert all(command.endswith("?") for command in payload["scpi"]["sent"])
    assert "planned" in payload["scpi"]
