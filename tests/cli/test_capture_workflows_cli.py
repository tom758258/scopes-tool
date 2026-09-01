from __future__ import annotations

import json
from pathlib import Path

from scopes_tool_cli import cli, worker


def _runtime():
    return worker.WorkerRuntime(
        host="127.0.0.1",
        port=0,
        mode="simulate",
        model="keysight-dsox4024a",
        resource=None,
        queue_max=4,
        output_format="jsonl",
    )


def test_capture_until_dry_run_is_representative_and_uses_matching_count(
    tmp_path, capsys
):
    output_dir = tmp_path / "planned"
    code = cli.main(
        [
            "capture-until",
            "--dry-run",
            "--json",
            "--channel",
            "1",
            "--condition-channel",
            "1",
            "--metric",
            "max",
            "--operator",
            "gt",
            "--threshold",
            "1",
            "--count",
            "255",
            "--timeout-seconds",
            "10",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["result"]["requested_count"] == 255
    assert payload["scpi"]["planned"].count(":WAVeform:DATA?") == 1
    assert len([item for item in payload["files"] if item["kind"] == "csv"]) == 1
    assert not output_dir.exists()


def test_capture_workflows_simulator_results_are_compact(tmp_path, capsys):
    until_dir = tmp_path / "until"
    until_code = cli.main(
        [
            "capture-until",
            "--simulate",
            "--json",
            "--channel",
            "1",
            "--condition-channel",
            "1",
            "--metric",
            "max",
            "--operator",
            "gt",
            "--threshold",
            "-1000000",
            "--timeout-seconds",
            "2",
            "--output-dir",
            str(until_dir),
        ]
    )
    until_payload = json.loads(capsys.readouterr().out)
    monitor_dir = tmp_path / "monitor-not-created"
    monitor_code = cli.main(
        [
            "capture-monitor",
            "--simulate",
            "--json",
            "--channel",
            "1",
            "--count",
            "2",
            "--retention-points",
            "1000",
            "--output-dir",
            str(monitor_dir),
            "--no-save",
        ]
    )
    monitor_payload = json.loads(capsys.readouterr().out)

    assert until_code == 0
    assert until_payload["result"]["completed_count"] == 1
    assert "samples" not in until_payload["result"]
    assert monitor_code == 0
    assert monitor_payload["files"] == []
    assert monitor_payload["result"]["completed_count"] == 2
    assert monitor_payload["result"]["retained_points"] == 1000
    assert monitor_payload["result"]["dropped_points"] == 1000
    assert "samples" not in monitor_payload["result"]
    assert not monitor_dir.exists()


def test_capture_monitor_human_cli_reports_compact_telemetry(tmp_path, capsys):
    output_dir = tmp_path / "monitor-human"
    code = cli.main(
        [
            "capture-monitor",
            "--simulate",
            "--channel",
            "1",
            "--count",
            "2",
            "--retention-points",
            "1000",
            "--output-dir",
            str(output_dir),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    # each completed capture prints at most 2 lines: counters + metrics
    assert "Capture 1/2: observed=" in captured.out
    assert "Capture 2/2: observed=" in captured.out
    assert "max=" in captured.out
    assert "min=" in captured.out
    assert "p2p=" in captured.out
    assert "abs-max=" in captured.out
    assert "values" not in captured.out.lower()


def test_capture_monitor_json_mode_not_polluted_by_telemetry(tmp_path, capsys):
    output_dir = tmp_path / "monitor-json"
    code = cli.main(
        [
            "capture-monitor",
            "--simulate",
            "--json",
            "--channel",
            "1",
            "--count",
            "2",
            "--retention-points",
            "1000",
            "--output-dir",
            str(output_dir),
        ]
    )
    raw = capsys.readouterr().out
    payload = json.loads(raw)
    assert code == 0
    assert payload["ok"] is True
    assert "samples" not in payload["result"]
    assert raw.strip().startswith("{")
    human_output = "\n".join(payload["result"].get("human_output", []))
    assert "Capture 1/2:" not in human_output
    assert "Capture 2/2:" not in human_output


def test_worker_accepts_both_capture_workflows_and_optional_monitor_output(tmp_path):
    until_output = tmp_path / "until"
    until_args = worker.parse_domain_command(
        "capture-until",
        {
            "channel": [1, 2],
            "condition_channel": 1,
            "metric": "max",
            "operator": "gt",
            "threshold": 1.0,
            "count": 2,
            "timeout_seconds": 10.0,
            "output_dir": str(until_output),
        },
        _runtime(),
    )
    monitor_args = worker.parse_domain_command(
        "capture-monitor",
        {
            "channel": [1],
            "count": 2,
            "retention_points": 250000,
            "save_results": False,
        },
        _runtime(),
    )

    assert until_args.channel == [1, 2]
    assert until_args.count == 2
    assert Path(until_args.output_dir) == until_output
    assert monitor_args.no_save is True
    assert monitor_args.output_dir is None
