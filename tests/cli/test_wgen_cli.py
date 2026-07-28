import json

from scopes_tool_cli import cli


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_wgen_configure_and_query_dry_run_plan_concrete_scpi(capsys):
    assert cli.main([
        "wgen-frequency",
        "--hz",
        "1000",
        "--dry-run",
        "--json",
        "--model",
        "keysight-dsox4024a",
    ]) == 0
    assert _payload(capsys)["scpi"]["planned"][0] == ":WGEN1:FREQuency 1000"

    assert cli.main([
        "wgen-offset",
        "--query",
        "--dry-run",
        "--json",
        "--model",
        "keysight-dsox3024a",
    ]) == 0
    assert _payload(capsys)["scpi"]["planned"][0] == ":WGEN:VOLTage:OFFSet?"
