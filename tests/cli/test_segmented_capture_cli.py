import json

import pytest

from scopes_tool_cli import cli


def test_segmented_capture_simulate_json_writes_artifacts_and_order(tmp_path, capsys):
    assert (
        cli.main(
            [
                "segmented-capture",
                "--simulate",
                "--json",
                "--channel",
                "1",
                "--segments",
                "2",
                "--points",
                "1000",
                "--format",
                "byte",
                "--timeout-ms",
                "30000",
                "--poll-interval-ms",
                "1",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["operation"] == "segmented-capture"
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["configured_segments"] == 2
    assert payload["result"]["acquired_segments"] == 2
    assert payload["result"]["exported_segments"] == 2
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "scpi.log").exists()
    assert (tmp_path / "segment_0001.csv").exists()
    assert (tmp_path / "segment_0002.csv").exists()
    assert payload["scpi"]["sent"][:7] == [
        "*IDN?",
        ":ACQuire:MODE?",
        ":ACQuire:TYPE?",
        ":ACQuire:MODE SEGMented",
        ":ACQuire:SEGMented:COUNt 2",
        ":SINGle",
        ":WAVeform:SEGMented:COUNt?",
    ]
    assert payload["scpi"]["sent"].count(":WAVeform:SEGMented:ALL OFF") == 0
    assert payload["scpi"]["sent"].index(":ACQuire:SEGMented:INDex 1") > 6
    assert payload["scpi"]["sent"][-2:] == [
        ":ACQuire:MODE?",
        ":SYSTem:ERRor?",
    ]


def test_segmented_capture_dry_run_is_concrete_and_creates_no_artifacts(tmp_path, capsys):
    output_dir = tmp_path / "output"
    assert (
        cli.main(
            [
                "segmented-capture",
                "--dry-run",
                "--json",
                "--channel",
                "1",
                "--segments",
                "2",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["scpi"]["sent"] == []
    assert payload["scpi"]["planned"][:7] == [
        "*IDN?",
        ":ACQuire:MODE?",
        ":ACQuire:TYPE?",
        ":ACQuire:MODE SEGMented",
        ":ACQuire:SEGMented:COUNt 2",
        ":SINGle",
        ":WAVeform:SEGMented:COUNt?",
    ]
    assert payload["scpi"]["planned"].count(":WAVeform:SEGMented:ALL OFF") == 0
    assert payload["scpi"]["planned"].index(":ACQuire:SEGMented:INDex 1") > 6
    assert payload["scpi"]["planned"][-2:] == [
        ":ACQuire:MODE?",
        ":SYSTem:ERRor?",
    ]
    assert payload["result"]["polling"]["runtime_behavior"]
    assert not output_dir.exists()


@pytest.mark.parametrize(
    ("option", "value", "fragment"),
    [
        ("--segments", "1", "between 2"),
        ("--timeout-ms", "0", "at least 1"),
        ("--poll-interval-ms", "0", "at least 1"),
    ],
)
def test_segmented_capture_rejects_invalid_static_arguments(
    option, value, fragment, tmp_path, capsys
):
    output_dir = tmp_path / "output"
    arguments = [
        "segmented-capture",
        "--simulate",
        "--json",
        "--channel",
        "1",
        "--segments",
        "2",
        option,
        value,
        "--output-dir",
        str(output_dir),
    ]
    if option != "--segments":
        with pytest.raises(SystemExit) as excinfo:
            cli.main(arguments)
        assert excinfo.value.code == 2
        assert fragment in capsys.readouterr().err
        assert not output_dir.exists()
        return
    assert (
        cli.main(arguments)
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert fragment in payload["error"]["message"]
    assert not output_dir.exists()
