import json

import pytest

from scopes_tool_cli import cli


def _payload(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


@pytest.mark.parametrize("profile", ("minimal", "safe"))
def test_cleanup_dry_run_json_plans_without_hardware(
    monkeypatch, capsys, profile
):
    monkeypatch.setattr(
        cli,
        "_open_scope",
        lambda *unused: pytest.fail("dry-run opened a scope"),
    )

    assert (
        cli.main(["cleanup", "--profile", profile, "--dry-run", "--json"])
        == 0
    )

    payload = _payload(capsys)
    assert payload["result"]["profile"] == profile
    assert payload["result"]["actions"]
    assert payload["result"]["final_error_queue_clean"] is None
    assert payload["scpi"]["sent"] == []
    assert payload["scpi"]["planned"][0] == "*IDN?"
    assert payload["scpi"]["planned"][-2:] == ["*OPC?", ":SYSTem:ERRor?"]
    assert "*RST" not in payload["scpi"]["planned"]
    assert ":SYSTem:PRESet" not in payload["scpi"]["planned"]


def test_cleanup_safe_reports_wgen_skip(capsys):
    assert cli.main(["cleanup", "--profile", "safe", "--dry-run", "--json"]) == 0

    payload = _payload(capsys)
    assert {
        "action": "disable_wgen",
        "reason": "wgen_not_implemented",
    } in payload["result"]["skipped"]


def test_cleanup_defaults_to_minimal_profile(capsys):
    assert cli.main(["cleanup", "--dry-run", "--json"]) == 0

    assert _payload(capsys)["result"]["profile"] == "minimal"


def test_cleanup_safe_simulator_runs_existing_helpers(capsys):
    assert cli.main(["cleanup", "--profile", "safe", "--simulate", "--json"]) == 0

    payload = _payload(capsys)
    assert payload["result"]["profile"] == "safe"
    assert payload["result"]["final_error_queue_clean"] is True
    assert payload["scpi"]["sent"][0] == "*IDN?"
    assert payload["scpi"]["sent"][-2:] == ["*OPC?", ":SYSTem:ERRor?"]
    assert all(
        command not in {"*RST", ":SYSTem:PRESet", ":AUToscale"}
        for command in payload["scpi"]["sent"]
    )


def test_cleanup_rejects_invalid_profile(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["cleanup", "--profile", "unknown", "--dry-run", "--json"])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "invalid choice" in captured.err
