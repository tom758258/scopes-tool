import json

import pytest

from scopes_tool_cli import cli, runtime


@pytest.mark.parametrize(
    ("argv", "targets"),
    [
        (["reference-save", "--slot", "1", "--source-channel", "1"], [":WMEMory1:SAVE CHANnel1"]),
        (["reference-display", "--slot", "1", "--state", "on"], [":WMEMory1:DISPlay ON"]),
        (["reference-display", "--slot", "1", "--query"], [":WMEMory1:DISPlay?"]),
        (["reference-label", "--slot", "1", "--text", "BASELINE"], [':WMEMory1:LABel "BASELINE"']),
        (["reference-label", "--slot", "1", "--query"], [":WMEMory1:LABel?"]),
        (["reference-clear", "--slot", "2"], [":WMEMory2:CLEar"]),
        (["reference-query", "--slot", "1"], [":WMEMory1:DISPlay?", ":WMEMory1:LABel?"]),
    ],
)
@pytest.mark.parametrize("mode", ["--dry-run", "--simulate"])
def test_reference_waveform_json_modes(argv, targets, mode, capsys):
    assert cli.main([*argv, mode, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    scpi = payload["scpi"]["planned" if mode == "--dry-run" else "sent"]
    assert payload["ok"] is True
    for target in targets:
        assert target in scpi


def test_reference_save_dry_run_plans_complete_operation_in_order(capsys):
    assert cli.main(
        [
            "reference-save",
            "--slot",
            "1",
            "--source-channel",
            "1",
            "--dry-run",
            "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["scpi"]["planned"] == [
        "*IDN?",
        ":WMEMory1:SAVE CHANnel1",
        "*OPC?",
        ":SYSTem:ERRor?",
    ]


def test_reference_query_result_preserves_raw_fields(capsys):
    assert cli.main(["reference-query", "--slot", "1", "--simulate", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["raw_displayed"] == "0"
    assert result["raw_label"] == '""'


@pytest.mark.parametrize(
    "argv",
    [
        ["reference-save", "--slot", "3", "--source-channel", "1"],
        ["reference-save", "--slot", "1", "--source-channel", "5", "--model", "keysight-dsox2004a"],
        ["reference-label", "--slot", "1", "--text", "TOO-LONG-11"],
        ["reference-label", "--slot", "1", "--text", 'BAD"LABEL'],
    ],
)
def test_reference_validation_rejected_before_open(argv, monkeypatch, capsys):
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(lambda *args, **kwargs: pytest.fail("opened VISA")))
    assert cli.main([*argv, "--dry-run", "--json"]) != 0


def test_reference_slot_zero_rejected_by_parser():
    with pytest.raises(SystemExit):
        cli.main(["reference-save", "--slot", "0", "--source-channel", "1"])


@pytest.mark.parametrize("argv", [["reference-display", "--slot", "1"], ["reference-label", "--slot", "1"]])
def test_reference_missing_action_rejected(argv):
    with pytest.raises(SystemExit):
        cli.main(argv)


def test_reference_text_output_smoke(capsys):
    assert cli.main(["reference-query", "--slot", "1", "--simulate"]) == 0
    output = capsys.readouterr().out
    assert "Command: :WMEMory1:DISPlay?" in output
    assert "Command: :WMEMory1:LABel?" in output
