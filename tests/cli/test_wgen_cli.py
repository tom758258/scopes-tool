import json

from scopes_tool_cli import cli


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_normal_live_pre_open_does_not_false_reject_model_valid_values():
    # Direct validation of the pre-open path when capabilities is None
    # (normal one-shot live before instrument session open). The legacy
    # series=None 5 V / 2.5 V ceiling must not false-reject 4000X-valid
    # values; basic finite checks are sufficient.
    import argparse
    from scopes_tool_cli.preflight import _validate_wgen_args

    # Frequency basic check (finite, >0)
    args = argparse.Namespace(
        command="wgen-frequency", hz=100.0, query=False,
        simulate=False, dry_run=False, model=None,
    )
    _validate_wgen_args(args)

    # Amplitude: 6 Vpp should not be rejected by legacy 5 V ceiling.
    args = argparse.Namespace(
        command="wgen-voltage", amplitude=6.0, query=False,
        simulate=False, dry_run=False, model=None,
    )
    _validate_wgen_args(args)

    # Offset: 3 V should not be rejected by legacy +/-2.5 V ceiling.
    args = argparse.Namespace(
        command="wgen-offset", volts=3.0, query=False,
        simulate=False, dry_run=False, model=None,
    )
    _validate_wgen_args(args)


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
