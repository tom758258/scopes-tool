from __future__ import annotations

import shutil

import pytest

from scopes_tool_webui.command_catalog import command_catalog
from scopes_tool_webui import command_execution as command_execution_module
from scopes_tool_webui.command_execution import execute_command
from scopes_tool_webui.command_validation import WebUIRequestError, validate_job_request
from scopes_tool_webui.jobs import Job, JobManager
from tests.webui.test_workflow_editor import run_editor_behavior


MODEL_ID = "keysight-dsox4024a"


def _payload(command, parameters):
    return {
        "command": command,
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": parameters,
    }


def test_catalog_and_validation_lock_waveform_workflow_contracts():
    commands = {item["id"]: item for item in command_catalog()}
    until_fields = {item["name"]: item for item in commands["capture-until"]["fields"]}
    monitor_fields = {item["name"]: item for item in commands["capture-monitor"]["fields"]}

    assert commands["capture-until"]["editor"] == "workflow"
    assert until_fields["count"]["default"] == 1
    assert until_fields["count"]["minimum"] == 1
    assert until_fields["count"]["maximum"] == 255
    assert commands["capture-monitor"]["editor"] == "workflow"
    assert monitor_fields["retention_points"]["default"] == 250000
    assert monitor_fields["save_results"]["default"] is True

    normalized = validate_job_request(
        _payload(
            "capture-until",
            {
                "channels": "1,2",
                "condition_channel": 1,
                "metric": "max",
                "operator": "gt",
                "threshold": 1.0,
                "timeout_seconds": 10.0,
            },
        )
    )
    assert normalized["parameters"]["count"] == 1
    with pytest.raises(WebUIRequestError, match="included in selected"):
        validate_job_request(
            _payload(
                "capture-until",
                {
                    "channels": "2",
                    "condition_channel": 1,
                    "metric": "max",
                    "operator": "gt",
                    "threshold": 1.0,
                    "count": 1,
                    "timeout_seconds": 10.0,
                },
            )
        )
    with pytest.raises(WebUIRequestError, match="between 1 and 255"):
        validate_job_request(
            _payload(
                "capture-until",
                {
                    "channels": "1",
                    "condition_channel": 1,
                    "metric": "max",
                    "operator": "gt",
                    "threshold": 1.0,
                    "count": 256,
                    "timeout_seconds": 10.0,
                },
            )
        )


def test_monitor_transient_job_updates_are_bounded_and_incremental(tmp_path):
    manager = JobManager()
    job = Job(
        job_id="monitor",
        command="capture-monitor",
        mode="simulate",
        resource=None,
        model_id=MODEL_ID,
        pc_output_dir=str(tmp_path),
        parameters={"points": 1000, "retention_points": 2000},
        pc_output_root=tmp_path,
    )
    try:
        for index in range(1, 4):
            manager._append_monitor_update(
                job,
                {
                    "capture_index": index,
                    "global_start_index": (index - 1) * 1000,
                    "time_s": [0.0],
                    "channels": {"CH1": {"unit": "V", "values": [float(index)]}},
                    "completed_count": index,
                    "requested_count": 3,
                    "total_observed_points": index * 1000,
                    "retained_points": min(index, 2) * 1000,
                    "dropped_points": max(0, index - 2) * 1000,
                    "dropped_capture_count": 1 if index == 3 else 0,
                    "metrics": {"CH1": {"maximum": 3.0}},
                },
            )
        payload = job.to_payload(after_sequence=2)
        reset_payload = job.to_payload(after_sequence=1)
        initial_reset_payload = job.to_payload()
    finally:
        manager._executor.shutdown(wait=True)

    assert [item["capture_index"] for item in job.monitor_updates] == [2, 3]
    assert [item["capture_index"] for item in payload["monitor_runtime"]["updates"]] == [3]
    assert reset_payload["monitor_runtime"]["reset"] is False
    assert initial_reset_payload["monitor_runtime"]["reset"] is True
    assert [
        item["capture_index"]
        for item in initial_reset_payload["monitor_runtime"]["updates"]
    ] == [2, 3]
    assert "channels" not in payload["monitor_runtime"]["summary"]
    assert "time_s" not in payload["monitor_runtime"]["summary"]


def test_terminal_monitor_payload_releases_transient_waveforms(tmp_path):
    manager = JobManager()
    job = Job(
        job_id="terminal-monitor",
        command="capture-monitor",
        mode="simulate",
        resource=None,
        model_id=MODEL_ID,
        pc_output_dir=str(tmp_path),
        parameters={"points": 1000, "retention_points": 1000},
        pc_output_root=tmp_path,
        status="completed",
    )
    try:
        manager._append_monitor_update(
            job,
            {
                "capture_index": 1,
                "global_start_index": 0,
                "time_s": [0.0],
                "channels": {"CH1": {"unit": "V", "values": [1.0]}},
                "completed_count": 1,
                "requested_count": 1,
                "total_observed_points": 1000,
                "retained_points": 1000,
                "dropped_points": 0,
                "dropped_capture_count": 0,
                "metrics": {"CH1": {"maximum": 1.0}},
            },
        )
        payload = job.to_payload()
    finally:
        manager._executor.shutdown(wait=True)

    assert len(payload["monitor_runtime"]["updates"]) == 1
    assert job.monitor_updates == []


def test_monitor_webui_execution_keeps_final_result_compact(tmp_path):
    execution = execute_command(
        "capture-monitor",
        mode="simulate",
        resource=None,
        model_id=MODEL_ID,
        parameters={
            "channels": [1],
            "points": 1000,
            "format": "byte",
            "count": 2,
            "interval_seconds": 0,
            "retention_points": 1000,
            "save_results": False,
        },
        artifact_dir=tmp_path,
    )

    assert execution["exit_code"] == 0
    assert execution["artifacts"] == []
    assert execution["result"]["retained_points"] == 1000
    assert "samples" not in execution["result"]
    assert not list(tmp_path.iterdir())


def test_monitor_webui_stop_and_transient_callbacks_reach_core(monkeypatch, tmp_path):
    stop_requested = lambda: True
    sample_reporter = lambda _update: None
    received = []

    def fake_runner(
        _scope,
        _resource,
        _request,
        *,
        stop_requested=None,
        sample_reporter=None,
    ):
        received.append((stop_requested, sample_reporter))
        return command_execution_module.OperationResult(
            exit_code=130,
            result={"status": "cancelled"},
        )

    monkeypatch.setattr(command_execution_module, "run_capture_monitor", fake_runner)
    result = command_execution_module._execute_trigger_search_serial_segmented_workflow_command(
        object(),
        "capture-monitor",
        "USB0::TEST::INSTR",
        {
            "channels": (1,),
            "points": 1000,
            "format": "byte",
            "count": 2,
            "interval_seconds": 0,
            "retention_points": 250000,
            "save_results": False,
        },
        tmp_path,
        stop_requested=stop_requested,
        sample_reporter=sample_reporter,
    )

    assert result["result"]["status"] == "cancelled"
    assert received == [(stop_requested, sample_reporter)]


def test_monitor_status_shows_full_metrics(tmp_path):
    manager = JobManager()
    job = Job(
        job_id="monitor-metrics",
        command="capture-monitor",
        mode="simulate",
        resource=None,
        model_id=MODEL_ID,
        pc_output_dir=str(tmp_path),
        parameters={"points": 1000, "retention_points": 2000},
        pc_output_root=tmp_path,
    )
    try:
        manager._append_monitor_update(
            job,
            {
                "capture_index": 1,
                "global_start_index": 0,
                "time_s": [0.0],
                "channels": {"CH1": {"unit": "V", "values": [1.0]}},
                "completed_count": 1,
                "requested_count": 2,
                "total_observed_points": 1000,
                "retained_points": 1000,
                "dropped_points": 0,
                "dropped_capture_count": 0,
                "metrics": {
                    "CH1": {
                        "maximum": 1.82,
                        "minimum": -0.31,
                        "peak_to_peak": 2.13,
                        "abs_max": 1.82,
                        "unit": "V",
                    }
                },
            },
        )
        payload = job.to_payload()
        # backend summary must contain full metrics, not just maximum
        summary = payload["monitor_runtime"]["summary"]
        assert summary["metrics"]["CH1"]["minimum"] == -0.31
        assert summary["metrics"]["CH1"]["peak_to_peak"] == 2.13
        assert summary["metrics"]["CH1"]["abs_max"] == 1.82
    finally:
        manager._executor.shutdown(wait=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_monitor_frontend_shows_min_p2p_absmax():
    run_editor_behavior(
        r'''
        definitions.push({
          id: "capture-monitor", editor: "workflow", fields: [
            { name: "channels", type: "multi-enum", options: [1], default: [1], required: true },
            { name: "points", type: "integer", options: [1000], default: 1000 },
            { name: "format", type: "enum", options: ["byte"], default: "byte" },
            { name: "count", type: "integer", minimum: 1, required: true },
            { name: "interval_seconds", type: "number", minimum: 0, default: 0 },
            { name: "retention_points", type: "integer", minimum: 1000, default: 2000 },
            { name: "save_results", type: "boolean", default: true },
          ],
        });
        env.selectedId = "capture-monitor";
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        editor.handleJobUpdate({ command: "capture-monitor", monitor_runtime: {
          reset: true, summary: {
            completed_count: 1, requested_count: 2,
            total_observed_points: 1000, retained_points: 1000, dropped_points: 0,
            metrics: { CH1: { maximum: 1.82, minimum: -0.31, peak_to_peak: 2.13, abs_max: 1.82, unit: "V" } }
          }, updates: []
        }});
        assert.ok(editor.monitorStatus.textContent.includes("max="));
        assert.ok(editor.monitorStatus.textContent.includes("min="));
        assert.ok(editor.monitorStatus.textContent.includes("p2p="));
        assert.ok(editor.monitorStatus.textContent.includes("abs-max="));
        ''',
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_waveform_editor_filters_condition_channel_and_bounds_plot_chunks():
    run_editor_behavior(
        r'''
        definitions.push({
          id: "capture-until", editor: "workflow", fields: [
            { name: "channels", type: "multi-enum", options: [1, 2], default: [1], required: true },
            { name: "condition_channel", type: "enum", options: [1, 2], default: 1, required: true },
            { name: "points", type: "integer", options: [1000], default: 1000 },
            { name: "format", type: "enum", options: ["byte"], default: "byte" },
            { name: "metric", type: "enum", options: ["max"], default: "max" },
            { name: "operator", type: "enum", options: ["gt"], default: "gt" },
            { name: "threshold", type: "number", required: true },
            { name: "count", type: "integer", minimum: 1, maximum: 255, default: 1 },
            { name: "timeout_seconds", type: "number", exclusive_minimum: 0, required: true },
            { name: "interval_seconds", type: "number", minimum: 0, default: 0 },
          ],
        });
        definitions.push({
          id: "capture-monitor", editor: "workflow", fields: [
            { name: "channels", type: "multi-enum", options: [1], default: [1], required: true },
            { name: "points", type: "integer", options: [1000], default: 1000 },
            { name: "format", type: "enum", options: ["byte"], default: "byte" },
            { name: "count", type: "integer", minimum: 1, required: true },
            { name: "interval_seconds", type: "number", minimum: 0, default: 0 },
            { name: "retention_points", type: "integer", minimum: 1000, default: 2000 },
            { name: "save_results", type: "boolean", default: true },
          ],
        });
        env.selectedId = "capture-until";
        const editor = buildEditor();
        editor.schedulePresentation();
        await settle();
        assert.equal(editor.controls.condition_channel.children.length, 1);
        assert.equal(editor.controls.condition_channel.value, "1");
        editor.controls.channels.find((input) => input.value === "2").checked = true;
        editor.refreshConditionChannel();
        assert.equal(editor.controls.condition_channel.children.length, 2);

        env.selectedId = "capture-monitor";
        editor.schedulePresentation();
        await settle();
        editor.handleJobUpdate({ command: "capture-monitor", monitor_runtime: {
          reset: false, summary: { completed_count: 1, requested_count: 3 }, updates: [
            { capture_index: 1, dropped_capture_count: 0, channels: {} },
            { capture_index: 2, dropped_capture_count: 0, channels: {} },
            { capture_index: 3, dropped_capture_count: 1, channels: {} },
          ],
        }});
        assert.deepEqual(editor.monitorChunks.map((item) => item.capture_index), [2, 3]);
        assert.ok(editor.container.children.some(
          (node) => node.className === "compact-note workflow-monitor-warning",
        ));
        ''',
    )
