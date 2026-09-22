import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from scopes_tool_cli import cli, dispatch
from scopes_tool_cli.commands import workflows
from scopes_tool_core.operations import OperationResult


def test_segmented_capture_dispatch_forwards_stop_requested(monkeypatch) -> None:
    stop_requested = lambda: True
    received = {}

    def fake_command(args, *, stop_requested=None):
        received["args"] = args
        received["stop_requested"] = stop_requested
        return 130

    monkeypatch.setattr(dispatch.workflows, "_cmd_segmented_capture", fake_command)
    args = SimpleNamespace(command="segmented-capture")
    assert dispatch._dispatch_command(args, stop_requested=stop_requested) == 130
    assert received == {"args": args, "stop_requested": stop_requested}


def test_segmented_capture_command_forwards_stop_requested(monkeypatch) -> None:
    stop_requested = lambda: True
    request = object()
    scope = object()
    received = {}

    monkeypatch.setattr(workflows.runtime, "_require_resource", lambda _args: "SIM::TEST::INSTR")
    monkeypatch.setattr(workflows.preflight, "_segmented_capture_request", lambda _args: request)
    monkeypatch.setattr(
        workflows.runtime,
        "_open_scope",
        lambda _args, _resource: nullcontext(scope),
    )

    def fake_run(actual_scope, resource, actual_request, *, stop_requested=None):
        received["scope"] = actual_scope
        received["resource"] = resource
        received["request"] = actual_request
        received["stop_requested"] = stop_requested
        return OperationResult(130, {"status": "cancelled"})

    monkeypatch.setattr(workflows, "run_segmented_capture", fake_run)
    args = SimpleNamespace()
    assert workflows._cmd_segmented_capture(args, stop_requested=stop_requested) == 130
    assert received == {
        "scope": scope,
        "resource": "SIM::TEST::INSTR",
        "request": request,
        "stop_requested": stop_requested,
    }


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
    assert payload["result"]["vertical_unit"] == "V"
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "scpi.log").exists()
    assert (tmp_path / "segment_0001.csv").exists()
    assert (tmp_path / "segment_0002.csv").exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["vertical_unit"] == "V"
    assert (tmp_path / "segment_0001.csv").read_text(encoding="utf-8").splitlines()[0] == (
        "time_s,ch1_v"
    )
    assert payload["scpi"]["sent"][:12] == [
        "*IDN?",
        ":SYSTem:ERRor?",
        ":ACQuire:MODE?",
        ":ACQuire:TYPE?",
        ":CHANnel1:UNITs?",
        ":ACQuire:MODE SEGMented",
        ":ACQuire:SEGMented:COUNt 2",
        ":SINGle",
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
        ":OPERegister:CONDition?",
        ":WAVeform:SEGMented:COUNt?",
    ]
    assert payload["scpi"]["sent"].count(":WAVeform:SEGMented:ALL OFF") == 0
    assert payload["scpi"]["sent"].count(":WAVeform:SEGMented:COUNt?") == 1
    readiness_indexes = [
        index
        for index, command in enumerate(payload["scpi"]["sent"])
        if command == ":OPERegister:CONDition?"
    ]
    count_index = payload["scpi"]["sent"].index(
        ":WAVeform:SEGMented:COUNt?"
    )
    first_index = payload["scpi"]["sent"].index(":ACQuire:SEGMented:INDex 1")
    assert len(readiness_indexes) == 3
    assert readiness_indexes[-1] < count_index < first_index
    assert payload["result"]["polling"]["command"] == ":OPERegister:CONDition?"
    assert "two consecutive" in payload["result"]["polling"]["runtime_behavior"]
    assert "COUNt? once" in payload["result"]["polling"]["runtime_behavior"]
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
    assert payload["scpi"]["planned"][:9] == [
        "*IDN?",
        ":ACQuire:MODE?",
        ":ACQuire:TYPE?",
        ":CHANnel1:UNITs?",
        ":ACQuire:MODE SEGMented",
        ":ACQuire:SEGMented:COUNt 2",
        ":SINGle",
        ":OPERegister:CONDition?",
        ":WAVeform:SEGMented:COUNt?",
    ]
    assert payload["scpi"]["planned"].count(":WAVeform:SEGMented:ALL OFF") == 0
    readiness_index = payload["scpi"]["planned"].index(":OPERegister:CONDition?")
    count_index = payload["scpi"]["planned"].index(
        ":WAVeform:SEGMented:COUNt?"
    )
    first_index = payload["scpi"]["planned"].index(":ACQuire:SEGMented:INDex 1")
    assert readiness_index < count_index < first_index
    assert payload["scpi"]["planned"][-2:] == [
        ":ACQuire:MODE?",
        ":SYSTem:ERRor?",
    ]
    assert payload["result"]["polling"]["command"] == ":OPERegister:CONDition?"
    assert "two consecutive" in payload["result"]["polling"]["runtime_behavior"]
    assert "COUNt? once" in payload["result"]["polling"]["runtime_behavior"]
    assert payload["result"]["vertical_unit"] is None
    assert payload["scpi"]["planned"].count(":CHANnel1:UNITs?") == 1
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
