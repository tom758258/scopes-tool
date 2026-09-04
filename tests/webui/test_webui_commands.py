from __future__ import annotations

import asyncio
import time
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scopes_tool_core.dvm import DVM_MODES
from scopes_tool_core.fft import (
    FFT_DETECTION_TYPES,
    FFT_GATES,
    FFT_OPERATIONS,
    FFT_PHASE_REFERENCES,
)
from scopes_tool_core.math import (
    MATH_COMPOSITE_OPERATIONS,
    MATH_FILTER_OPERATIONS,
    MATH_OPERATIONS,
    MATH_SOURCES,
    MATH_TRANSFORMS,
    MATH_TRANSFORM_SOURCES,
    MATH_TREND_MEASUREMENTS,
    MATH_VISUALIZATION_OPERATIONS,
)
from scopes_tool_core.measurements import (
    MEASUREMENT_WINDOW_CHOICES,
    SUPPORTED_MEASUREMENT_ITEMS,
    validate_statistics_items,
)
from scopes_tool_core.trigger import TriggerWaitResult
import scopes_tool_webui.app as app_module
import scopes_tool_webui.command_execution as command_execution_module
import scopes_tool_webui.commands as commands_module
from scopes_tool_webui.app import app
from scopes_tool_webui.commands import (
    ScopeSessionCloseError,
    WebUIRequestError,
    validate_job_request,
)
from scopes_tool_webui.jobs import JobManager, JobManagerShuttingDown


MODEL_ID = "keysight-dsox4024a"
STATIC_ROOT = Path(__file__).resolve().parents[2] / "src" / "scopes_tool_webui" / "static"


def wait_for_job(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.02)
    raise AssertionError("WebUI job did not reach a terminal state")


def submit(
    client: TestClient,
    command: str,
    mode: str,
    parameters: dict,
    *,
    pc_output_dir: Path | None = None,
) -> dict:
    payload = {
        "command": command,
        "mode": mode,
        "model_id": MODEL_ID,
        "parameters": parameters,
    }
    if pc_output_dir is not None:
        payload["pc_output_dir"] = str(pc_output_dir)
    response = client.post(
        "/api/jobs",
        json=payload,
    )
    assert response.status_code == 202
    return wait_for_job(client, response.json()["job_id"])


def test_commands_expose_acquisition_channel_measurement_and_status_subset() -> None:
    client = TestClient(app)

    response = client.get("/api/commands")

    assert response.status_code == 200
    command_ids = {entry["id"] for entry in response.json()}
    assert {
        "force-trigger",
        "single-wait",
        "acquisition",
        "channel-display",
        "channel-scale",
        "measure",
        "screenshot",
        "capture",
        "check-error",
        "system-status-byte",
        "system-operation-status",
    } <= command_ids
    assert "identify" not in command_ids
    assert "trigger" not in command_ids
    acquisition = next(entry for entry in response.json() if entry["id"] == "acquisition")
    force_trigger = next(
        entry for entry in response.json() if entry["id"] == "force-trigger"
    )
    assert force_trigger["category"] == "Acquisition"
    assert force_trigger["fields"] == []
    assert force_trigger["modes"] == ["live", "simulate"]
    single_wait = next(
        entry for entry in response.json() if entry["id"] == "single-wait"
    )
    single_wait_fields = {field["name"]: field for field in single_wait["fields"]}
    assert single_wait["category"] == "Acquisition"
    assert single_wait["modes"] == ["live", "simulate"]
    assert single_wait_fields["trigger_timeout_seconds"]["default"] == 5.0
    assert single_wait_fields["force_trigger_on_timeout"]["default"] is False
    assert single_wait_fields["trigger_poll_interval_ms"]["default"] == 100
    assert single_wait_fields["trigger_poll_interval_ms"]["advanced"] is True
    action = next(field for field in acquisition["fields"] if field["name"] == "action")
    assert action["mode_options"]["dry-run"] == ["query"]
    acquisition_type = next(field for field in acquisition["fields"] if field["name"] == "type")
    assert acquisition_type["options"] == ["normal", "average", "high_resolution", "peak"]
    assert acquisition_type["required_if"] == [{"field": "action", "equals": "set"}]
    average_count = next(field for field in acquisition["fields"] if field["name"] == "count")
    assert average_count["visible_if"] == [{"field": "type", "equals": "average"}]
    assert average_count["help_key"] == "acquisition.average_count"
    assert average_count["minimum"] == 2
    assert average_count["maximum"] == 65536
    measure = next(entry for entry in response.json() if entry["id"] == "measure")
    item = next(field for field in measure["fields"] if field["name"] == "item")
    assert item["options"] == list(SUPPORTED_MEASUREMENT_ITEMS)


def test_execute_force_trigger_calls_core_action(tmp_path: Path) -> None:
    calls: list[str] = []

    class FakeScope:
        capabilities = object()

        def force_trigger(self) -> None:
            calls.append("force-trigger")

    result = command_execution_module._execute_scope_command(
        FakeScope(),
        "force-trigger",
        "SIM::INSTR",
        {},
        tmp_path,
    )

    assert calls == ["force-trigger"]
    assert result == {
        "exit_code": 0,
        "result": {"action": "force-trigger"},
        "artifacts": [],
    }


def test_autoscale_catalog_exposes_optional_parameters() -> None:
    client = TestClient(app)

    response = client.get("/api/commands")

    assert response.status_code == 200
    autoscale = next(entry for entry in response.json() if entry["id"] == "autoscale")
    assert autoscale["category"] == "Acquisition"
    assert autoscale["label"] == "Autoscale"
    assert autoscale["modes"] == ["live", "simulate"]
    assert "editor" not in autoscale
    fields = {field["name"]: field for field in autoscale["fields"]}
    assert set(fields) == {"channels", "acquire_mode", "channels_mode"}
    channels = fields["channels"]
    assert channels["type"] == "multi-enum"
    assert channels["options"] == [1, 2, 3, 4]
    assert channels.get("required") is not True
    assert "default" not in channels
    assert "required_if" not in channels
    acquire_mode = fields["acquire_mode"]
    assert acquire_mode["type"] == "enum"
    assert acquire_mode["options"] == ["normal", "current"]
    assert acquire_mode.get("required") is not True
    assert "default" not in acquire_mode
    assert "required_if" not in acquire_mode
    channels_mode = fields["channels_mode"]
    assert channels_mode["type"] == "enum"
    assert channels_mode["options"] == ["all", "displayed"]
    assert channels_mode.get("required") is not True
    assert "default" not in channels_mode
    assert "required_if" not in channels_mode


def test_autoscale_execution_forwards_none_for_unspecified_parameters(
    tmp_path: Path,
) -> None:
    calls: list[dict] = []

    class FakeScope:
        capabilities = object()

        def autoscale(self, channels, *, acquire_mode=None, channels_mode=None) -> None:
            calls.append({
                "channels": channels,
                "acquire_mode": acquire_mode,
                "channels_mode": channels_mode,
            })

    normalized = validate_job_request({
        "command": "autoscale",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {},
    })["parameters"]
    result = command_execution_module._execute_scope_command(
        FakeScope(),
        "autoscale",
        "SIM::INSTR",
        normalized,
        tmp_path,
    )

    assert calls == [{"channels": None, "acquire_mode": None, "channels_mode": None}]
    assert result == {
        "exit_code": 0,
        "result": {"action": "autoscale"},
        "artifacts": [],
    }


def test_autoscale_validation_normalizes_and_execution_forwards_parameters(
    tmp_path: Path,
) -> None:
    calls: list[dict] = []

    class FakeScope:
        capabilities = object()

        def autoscale(self, channels, *, acquire_mode=None, channels_mode=None) -> None:
            calls.append({
                "channels": channels,
                "acquire_mode": acquire_mode,
                "channels_mode": channels_mode,
            })

    normalized = validate_job_request({
        "command": "autoscale",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {
            "channels": "1,2",
            "acquire_mode": "current",
            "channels_mode": "displayed",
        },
    })["parameters"]
    assert normalized["channels"] == [1, 2]
    result = command_execution_module._execute_scope_command(
        FakeScope(),
        "autoscale",
        "SIM::INSTR",
        normalized,
        tmp_path,
    )

    assert calls == [{
        "channels": [1, 2],
        "acquire_mode": "current",
        "channels_mode": "displayed",
    }]
    assert result == {
        "exit_code": 0,
        "result": {"action": "autoscale"},
        "artifacts": [],
    }
    with pytest.raises(WebUIRequestError):
        validate_job_request({
            "command": "autoscale",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"acquire_mode": "bogus"},
        })
    with pytest.raises(WebUIRequestError):
        validate_job_request({
            "command": "autoscale",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"channels_mode": "bogus"},
        })


def test_autoscale_rejects_non_source_channel_aliases_and_empty_selection() -> None:
    normalized = validate_job_request({
        "command": "autoscale",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {"channels": []},
    })["parameters"]

    assert normalized["channels"] is None

    with pytest.raises(WebUIRequestError):
        validate_job_request({
            "command": "autoscale",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"channels": "all"},
        })

    with pytest.raises(WebUIRequestError):
        validate_job_request({
            "command": "autoscale",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"channels": "ch1"},
        })


def test_setup_save_recall_catalog_and_slot_presentation() -> None:
    commands = {
        entry["id"]: entry for entry in TestClient(app).get("/api/commands").json()
    }

    for command_id, label in (
        ("setup-save", "Save setup"),
        ("setup-recall", "Recall setup"),
    ):
        entry = commands[command_id]
        assert entry["category"] == "Save / Export"
        assert entry["label"] == label
        assert entry["modes"] == ["live", "simulate"]
        assert entry["browser_hidden"] is True
        assert entry["editor"] == "save-export"
        assert "group" not in entry
        fields = {field["name"]: field for field in entry["fields"]}
        assert set(fields) == {"target", "slot", "file"}
        assert fields["target"]["type"] == "enum"
        assert fields["target"]["options"] == ["slot", "file"]
        assert fields["target"].get("required") is True
        assert fields["slot"]["type"] == "integer"
        assert fields["slot"]["options"] == list(range(10))
        assert fields["slot"]["visible_if"] == [{"field": "target", "equals": "slot"}]
        assert fields["slot"]["required_if"] == [{"field": "target", "equals": "slot"}]
        assert fields["file"]["type"] == "string"
        assert fields["file"]["visible_if"] == [{"field": "target", "equals": "file"}]
        assert fields["file"]["required_if"] == [{"field": "target", "equals": "file"}]
        for model in entry["presentation"]["models"].values():
            assert "slot" not in model["fields"]

    reference_slot = commands["reference-save"]["presentation"]["models"][MODEL_ID][
        "fields"
    ]["slot"]
    assert reference_slot["options"] == [1, 2]


@pytest.mark.parametrize(
    ("command", "parameters", "expected"),
    [
        ("setup-save", {"target": "slot", "slot": 1}, {"target": "slot", "slot": 1}),
        ("setup-recall", {"target": "slot", "slot": 0}, {"target": "slot", "slot": 0}),
        (
            "setup-save",
            {"target": "file", "file": "\\usb\\baseline.scp"},
            {"target": "file", "file": "\\usb\\baseline.scp"},
        ),
        (
            "setup-recall",
            {"target": "file", "file": "\\usb\\baseline.scp"},
            {"target": "file", "file": "\\usb\\baseline.scp"},
        ),
        (
            "setup-save",
            {"target": "slot", "slot": 2, "file": "\\usb\\stale.scp"},
            {"target": "slot", "slot": 2},
        ),
        (
            "setup-recall",
            {"target": "file", "file": "\\usb\\baseline.scp", "slot": 3},
            {"target": "file", "file": "\\usb\\baseline.scp"},
        ),
    ],
)
def test_setup_save_recall_validation_normalizes_target(
    command: str, parameters: dict, expected: dict
) -> None:
    normalized = validate_job_request({
        "command": command,
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": dict(parameters),
    })["parameters"]

    assert normalized == expected


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"target": "bogus"},
        {"target": "slot"},
        {"target": "file"},
        {"target": "file", "file": "   "},
    ],
)
def test_setup_save_recall_validation_rejects_bad_target(parameters: dict) -> None:
    with pytest.raises(WebUIRequestError):
        validate_job_request({
            "command": "setup-save",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": dict(parameters),
        })


@pytest.mark.parametrize(
    ("command", "method", "parameters", "expected"),
    [
        ("setup-save", "save_setup", {"target": "slot", "slot": 1}, (1, None)),
        (
            "setup-save",
            "save_setup",
            {"target": "file", "file": "\\usb\\baseline.scp"},
            (None, "\\usb\\baseline.scp"),
        ),
        ("setup-recall", "recall_setup", {"target": "slot", "slot": 0}, (0, None)),
        (
            "setup-recall",
            "recall_setup",
            {"target": "file", "file": "\\usb\\baseline.scp"},
            (None, "\\usb\\baseline.scp"),
        ),
    ],
)
def test_setup_save_recall_execution_routes_to_core(
    command: str,
    method: str,
    parameters: dict,
    expected: tuple,
    tmp_path: Path,
) -> None:
    calls: list[tuple] = []

    class FakeScope:
        capabilities = object()

        def save_setup(self, *, slot=None, file_spec=None) -> None:
            calls.append(("save_setup", slot, file_spec))

        def recall_setup(self, *, slot=None, file_spec=None) -> None:
            calls.append(("recall_setup", slot, file_spec))

    normalized = validate_job_request({
        "command": command,
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": dict(parameters),
    })["parameters"]
    result = command_execution_module._execute_scope_command(
        FakeScope(),
        command,
        "SIM::INSTR",
        normalized,
        tmp_path,
    )

    assert calls == [(method, *expected)]
    assert result == {
        "exit_code": 0,
        "result": {"action": command},
        "artifacts": [],
    }


def test_setup_save_recall_simulate_jobs_complete_without_artifacts() -> None:
    client = TestClient(app)
    target = {"target": "file", "file": "\\usb\\baseline.scp"}

    for command in ("setup-save", "setup-recall"):
        job = submit(client, command, "simulate", dict(target))
        assert job["status"] == "completed", (command, job)
        assert job["result"]["result"] == {"action": command}
        assert job["artifacts"] == []


def test_measure_menu_calls_core_action(tmp_path: Path) -> None:
    calls: list[str] = []

    class FakeScope:
        capabilities = object()

        def open_measurement_menu(self) -> None:
            calls.append("open-menu")

        def clear_measurements(self) -> None:
            calls.append("clear")

    result = command_execution_module._execute_scope_command(
        FakeScope(),
        "measure-menu",
        "SIM::INSTR",
        {},
        tmp_path,
    )

    assert calls == ["open-menu"]
    assert result == {
        "exit_code": 0,
        "result": {"action": "measure-menu"},
        "artifacts": [],
    }


def test_single_wait_validation_and_execution_use_core_config(tmp_path: Path) -> None:
    request = validate_job_request({
        "command": "single-wait",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {},
    })
    assert request["parameters"] == {
        "trigger_timeout_seconds": 5.0,
        "trigger_poll_interval_ms": 100,
        "force_trigger_on_timeout": False,
    }

    calls = []

    class FakeScope:
        capabilities = object()

        def single_wait(self, config, *, stop_requested=None):
            calls.append((config, stop_requested))
            return TriggerWaitResult(
                outcome="natural",
                forced=False,
                timed_out=False,
                poll_count=1,
                elapsed_ms=10.0,
                capture_allowed=True,
            )

    stop_requested = lambda: False
    result = command_execution_module._execute_scope_command(
        FakeScope(),
        "single-wait",
        "SIM::INSTR",
        request["parameters"],
        tmp_path,
        stop_requested=stop_requested,
    )

    config, callback = calls[0]
    assert config.timeout_ms == 5000
    assert config.poll_interval_ms == 100
    assert config.force_on_timeout is False
    assert callback is stop_requested
    assert result["result"]["operation"] == "single-wait"
    assert result["result"]["outcome"] == "natural"
    assert result["artifacts"] == []


def test_measure_catalog_declares_item_specific_fields_and_guidance() -> None:
    measure = next(
        entry for entry in TestClient(app).get("/api/commands").json()
        if entry["id"] == "measure"
    )
    fields = {field["name"]: field for field in measure["fields"]}

    assert measure["label"] == "Single Measurement"
    assert fields["item"]["label_key"] == "measure.item"
    assert fields["item"]["help_by_value"] == {
        item: f"measure.item.{item}" for item in SUPPORTED_MEASUREMENT_ITEMS
    }
    assert fields["slope"]["option_label"] == "measure.slope"
    assert fields["slope"]["default"] == "positive"
    assert fields["occurrence"]["type"] == "integer"
    assert fields["occurrence"]["minimum"] == 1
    assert fields["occurrence"]["default"] == 1
    assert fields["occurrence"]["label_key"] == "measure.occurrence"
    assert "minimum" not in fields["time_s"]
    assert "maximum" not in fields["time_s"]
    assert "minimum" not in fields["level"]
    assert "maximum" not in fields["level"]
    assert fields["reference_channel"]["visible_if"] == [
        {"field": "item", "in": ["phase", "delay"]}
    ]
    assert fields["reference_channel"]["required_if"] == [
        {"field": "item", "in": ["phase", "delay"]}
    ]
    assert fields["time_s"]["visible_if"] == [
        {"field": "item", "equals": "y_at_x"}
    ]
    assert fields["time_s"]["required_if"] == [
        {"field": "item", "equals": "y_at_x"}
    ]
    assert fields["level"]["visible_if"] == [
        {"field": "item", "equals": "time_at_value"}
    ]
    assert fields["level"]["required_if"] == [
        {"field": "item", "equals": "time_at_value"}
    ]
    assert fields["slope"]["visible_if"] == [
        {"field": "item", "in": ["time_at_edge", "time_at_value"]}
    ]
    assert fields["occurrence"]["visible_if"] == [
        {"field": "item", "in": ["time_at_edge", "time_at_value"]}
    ]
    for field_name in fields:
        assert fields[field_name]["help_key"] == f"measure.{field_name}"

    def applies(field: dict, item: str, key: str) -> bool:
        predicates = field.get(key, [])
        return all(
            item == predicate.get("equals")
            if "equals" in predicate
            else item in predicate["in"]
            for predicate in predicates
        )

    for item in SUPPORTED_MEASUREMENT_ITEMS:
        expected = {"item", "channel"}
        if item in {"phase", "delay"}:
            expected.add("reference_channel")
        elif item == "y_at_x":
            expected.add("time_s")
        elif item == "time_at_edge":
            expected.update({"slope", "occurrence"})
        elif item == "time_at_value":
            expected.update({"level", "slope", "occurrence"})
        visible = {
            name for name, field in fields.items()
            if applies(field, item, "visible_if")
        }
        assert visible == expected, item

        required = {
            name for name, field in fields.items()
            if applies(field, item, "required_if") and field.get("required_if")
        }
        expected_required = {
            "reference_channel" if item in {"phase", "delay"} else
            "time_s" if item == "y_at_x" else
            "level" if item == "time_at_value" else
            ""
        } - {""}
        assert required == expected_required, item

    english = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    chinese = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    assert '"command.measure": "Single Measurement"' in english
    assert '"command.measure": "單項量測"' in chinese
    assert '"command.front-panel-measurements": "Front Panel Measurements"' in english
    assert '"command.front-panel-measurements": "前面板量測"' in chinese
    assert '"command.measure-results": "Front-panel measurement results"' in english
    assert '"command.measure-results": "前面板量測結果"' in chinese
    assert '"measurement.frontPanel.add": "Add measurement"' in english
    assert '"measurement.frontPanel.add": "新增量測"' in chinese
    assert '"command.measure-show": "Measurement marker display"' in english
    assert '"command.measure-show": "量測標記顯示"' in chinese
    assert '"measurement.frontPanel.show": "Show measurement markers"' in english
    assert '"measurement.frontPanel.show": "顯示量測標記"' in chinese
    assert '"measurement.frontPanel.hide": "Hide measurement markers"' in english
    assert '"measurement.frontPanel.hide": "隱藏量測標記"' in chinese
    assert '"measurement.frontPanel.markersAlwaysOn":' in english
    assert '"measurement.frontPanel.markersAlwaysOn":' in chinese
    assert '"description.measure-results":' in english
    assert 'Latest successful result' in english
    assert '"description.measure-results":' in chinese
    assert "最新成功結果" in chinese
    assert '"field.measure.item": "Measurement item"' in english
    assert '"field.measure.item": "量測項目"' in chinese
    assert '"field.measure.occurrence": "Edge/crossing number"' in english
    assert '"field.measure.occurrence": "第幾次邊緣／交越"' in chinese
    for key in (
        "measure.item",
        "measure.channel",
        "measure.reference_channel",
        "measure.time_s",
        "measure.level",
        "measure.slope",
        "measure.occurrence",
    ):
        assert f'"help.{key}":' in english
        assert f'"help.{key}":' in chinese
    for item in SUPPORTED_MEASUREMENT_ITEMS:
        key = f"measure.item.{item}"
        assert f'"help.{key}":' in english
        assert f'"help.{key}":' in chinese
    for locale in (english, chinese):
        help_values = "\n".join(
            line.split('": ', 1)[1]
            for line in locale.splitlines()
            if '"help.measure.' in line and '": ' in line
        )
        assert "y_at_x" not in help_values
        assert "time_at_edge" not in help_values
        assert "time_at_value" not in help_values
    assert '"enum.measure.slope.positive": "Positive"' in english
    assert '"enum.measure.slope.positive": "上升"' in chinese
    assert '"enum.measure.slope.negative": "Negative"' in english
    assert '"enum.measure.slope.negative": "下降"' in chinese
    for key in (
        "measure-window.window",
        "measure-window.window.main",
        "measure-window.window.zoom",
        "measure-window.window.auto",
        "measure-window.window.gate",
    ):
        assert f'"help.{key}":' in english
        assert f'"help.{key}":' in chinese
    assert '"field.measure-window.window": "Range"' in english
    assert '"field.measure-window.window": "範圍"' in chinese
    assert (
        '"description.measure": "Configure the measurement item, channel, required conditions, '
        'and measurement range for this run."' in english
    )
    assert '"description.measure": "設定本次量測的項目、通道、必要條件與量測範圍。"' in chinese
    for key in (
        "measurement.frontPanel.unread",
        "measurement.frontPanel.empty",
        "measurement.frontPanel.cleared",
        "measurement.frontPanel.readFailed",
        "measurement.frontPanel.readFailedStale",
    ):
        assert f'"{key}":' in english
        assert f'"{key}":' in chinese
    for option in MEASUREMENT_WINDOW_CHOICES:
        assert f'"enum.measure-window.window.{option}":' in english
        assert f'"enum.measure-window.window.{option}":' in chinese


def test_measure_sweep_validation_normalizes_core_request_fields() -> None:
    request = validate_job_request(
        {
            "command": "measure-sweep",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {
                "channels": "1,2",
                "items": ["vpp", "frequency", "period", "vrms"],
                "pairs": ["1:2"],
                "pair_items": ["phase", "delay"],
            },
        }
    )

    assert request["parameters"] == {
        "channels": [1, 2],
        "items": "vpp,frequency,period,vrms",
        "pairs": ["1:2"],
        "pair_items": "phase,delay",
    }
    defaults = validate_job_request(
        {
            "command": "measure-sweep",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {},
        }
    )
    assert defaults["parameters"] == {
        "channels": None,
        "items": "vpp,frequency,period,vrms",
        "pairs": [],
        "pair_items": "phase,delay",
    }


def test_measure_sweep_validation_rejects_unsupported_pair_measurement() -> None:
    with pytest.raises(WebUIRequestError, match="delay pair measurement is not supported"):
        validate_job_request(
            {
                "command": "measure-sweep",
                "mode": "simulate",
                "model_id": "keysight-dsox2004a",
                "parameters": {"pair_items": "phase,delay"},
            }
        )


def test_live_measurement_pairs_prequeue_accepts_csv_and_list() -> None:
    # Live prequeue shape should accept both csv string and list of pair strings for all workflows using pairs.
    for command, extra in [
        ("measure-sweep", {}),
        ("measure-log", {"count": 1}),
        (
            "triggered-measure-loop",
            {"count": 1, "trigger_timeout_seconds": 1},
        ),
    ]:
        for pairs_value in ["1:2,3:4", ["1:2", "3:4"], ["1:2"]]:
            request = validate_job_request(
                {
                    "command": command,
                    "mode": "live",
                    "resource": "USB0::TEST::INSTR",
                    "parameters": {"pairs": pairs_value, **extra},
                }
            )
            # prequeue must not reject shape; pairs preserved for backend/Core validation
            assert request["parameters"]["pairs"] == pairs_value


@pytest.mark.parametrize(
    "invalid_pairs",
    [123, {"a": 1}, [1, 2], ["1:2", 2]],
)
def test_live_measurement_pairs_prequeue_rejects_invalid_types(invalid_pairs) -> None:
    with pytest.raises(WebUIRequestError, match="pairs must be a comma-separated string or list of strings"):
        validate_job_request(
            {
                "command": "measure-sweep",
                "mode": "live",
                "resource": "USB0::TEST::INSTR",
                "parameters": {"pairs": invalid_pairs},
            }
        )


def test_measure_sweep_execution_delegates_to_core_request(monkeypatch, tmp_path: Path) -> None:
    received = []

    def fake_run_measure_sweep(scope, resource, request, **kwargs):  # type: ignore[no-untyped-def]
        received.append((scope, resource, request))
        return command_execution_module.OperationResult(
            exit_code=0,
            result={"measurements": [], "summary": {"valid_count": 0}},
        )

    monkeypatch.setattr(
        command_execution_module, "run_measure_sweep", fake_run_measure_sweep
    )
    scope = type("FakeScope", (), {"capabilities": object()})()
    result = command_execution_module._execute_scope_command(
        scope,
        "measure-sweep",
        "USB0::TEST::INSTR",
        {
            "channels": [1, 2],
            "items": "vpp,frequency,period,vrms",
            "pairs": ["1:2"],
            "pair_items": "phase,delay",
        },
        tmp_path,
    )

    assert result["exit_code"] == 0
    assert len(received) == 1
    assert received[0][0] is scope
    assert received[0][1] == "USB0::TEST::INSTR"
    request = received[0][2]
    assert request.channels == [1, 2]
    assert request.items == "vpp,frequency,period,vrms"
    assert request.pairs == ["1:2"]
    assert request.pair_items == "phase,delay"


def test_measure_sweep_execution_forwards_stop_requested(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run_measure_sweep(scope, resource, request, *, stop_requested=None):  # type: ignore[no-untyped-def]
        captured["stop_requested"] = stop_requested
        return command_execution_module.OperationResult(
            exit_code=0,
            result={"measurements": [], "summary": {"valid_count": 0}},
        )

    monkeypatch.setattr(command_execution_module, "run_measure_sweep", fake_run_measure_sweep)
    scope = type("FakeScope", (), {"capabilities": object()})()
    sentinel = lambda: False
    result = command_execution_module._execute_scope_command(
        scope,
        "measure-sweep",
        "USB0::TEST::INSTR",
        {
            "channels": [1],
            "items": "vpp",
            "pairs": [],
            "pair_items": "phase,delay",
        },
        tmp_path,
        stop_requested=sentinel,
    )

    assert result["exit_code"] == 0
    assert captured["stop_requested"] is sentinel


def test_measure_sweep_dry_run_uses_core_planner(monkeypatch, tmp_path: Path) -> None:
    received = []
    real_planner = command_execution_module.plan_measure_sweep

    def recording_planner(request, capabilities):  # type: ignore[no-untyped-def]
        received.append(request)
        return real_planner(request, capabilities)

    monkeypatch.setattr(command_execution_module, "plan_measure_sweep", recording_planner)
    result = command_execution_module._execute_dry_run(
        "measure-sweep",
        {
            "channels": [1, 2],
            "items": "vpp,frequency,period,vrms",
            "pairs": ["1:2"],
            "pair_items": "phase,delay",
        },
        MODEL_ID,
        tmp_path,
    )

    assert len(received) == 1
    assert received[0].channels == [1, 2]
    assert received[0].pairs == ["1:2"]
    assert result["result"]["status"] == "planned"
    assert result["result"]["channels"] == [1, 2]


def test_live_data_snapshot_is_hidden_and_runs_through_simulated_jobs() -> None:
    client = TestClient(app)

    assert "live-data-snapshot" not in {
        entry["id"] for entry in client.get("/api/commands").json()
    }
    job = submit(client, "live-data-snapshot", "simulate", {})

    assert job["status"] == "completed"
    summary = job["result"]["result"]["live_data"]
    assert len(summary["channels"]) == 4
    assert {"display", "units", "scale", "offset"} <= summary["channels"][0].keys()
    assert summary["timebase"] == {"scale": 0.001, "position": 0.0}
    assert summary["trigger"] == {
        "type": "edge",
        "source": "analog-channel",
        "source_channel": 1,
        "level": 0.0,
        "units": "volt",
        "slope": "positive",
        "sweep": "auto",
    }

    rejected = client.post(
        "/api/jobs",
        json={
            "command": "live-data-snapshot",
            "mode": "dry-run",
            "model_id": MODEL_ID,
            "parameters": {},
        },
    )
    assert rejected.status_code == 400


def test_command_catalog_projects_setting_and_model_presentation() -> None:
    commands = {
        entry["id"]: entry
        for entry in TestClient(app).get("/api/commands").json()
    }

    channel_scale = commands["channel-scale"]
    assert channel_scale["presentation"]["kind"] == "setting"
    assert channel_scale["presentation"]["action"] == "apply"
    assert channel_scale["presentation"]["query_fields"] == ["channel"]
    for command_id, value_name in (
        ("timebase-scale", "seconds_per_division"),
        ("timebase-position", "position_seconds"),
        ("timebase-reference", "reference"),
    ):
        timebase = commands[command_id]
        assert timebase["presentation"]["kind"] == "setting"
        assert timebase["presentation"]["action"] == "apply"
        assert timebase["presentation"]["query_fields"] == []
        assert next(
            field for field in timebase["fields"] if field["name"] == value_name
        )["required_if"] == [{"field": "action", "equals": "set"}]
        assert next(
            field for field in timebase["fields"] if field["name"] == value_name
        )["help_key"] == f"timebase.{value_name}"
        if value_name == "seconds_per_division":
            field = next(field for field in timebase["fields"] if field["name"] == value_name)
            assert field["exclusive_minimum"] == 0
            assert "minimum" not in field

    reference_field = next(
        field for field in commands["timebase-reference"]["fields"]
        if field["name"] == "reference"
    )
    assert reference_field["type"] == "enum"
    assert reference_field["options"] == ["left", "center", "right"]

    model_2000x = "keysight-dsox2004a"
    model_3000x = "keysight-dsox3024a"
    for command_id in (
        "reference-save",
        "reference-display",
        "reference-label",
        "reference-clear",
        "reference-query",
    ):
        command = commands[command_id]
        base_slot = next(field for field in command["fields"] if field["name"] == "slot")
        assert base_slot["options"] == [1, 2]
        slot = commands[command_id]["presentation"]["models"][model_2000x]["fields"]["slot"]
        assert slot["maximum"] == 2
        assert slot["options"] == [1, 2]
    impedance = commands["channel-impedance"]["presentation"]["models"][model_2000x]
    assert impedance["fields"]["impedance"]["options"] == ["one_meg"]
    math_display = commands["math-display"]["presentation"]["models"][model_2000x]
    assert math_display["fields"]["function"]["maximum"] == 1
    assert commands["measure-results"]["presentation"]["models"][model_2000x]["supported"] is False
    serial_mode = commands["serial-mode"]["presentation"]["models"][model_2000x]
    assert serial_mode["fields"]["mode"]["options"] == ["can", "i2c", "lin", "spi", "uart"]
    search_mode = commands["search-mode"]["presentation"]["models"][model_2000x]
    assert search_mode["fields"]["mode"]["options"] == ["serial1"]
    assert commands["segmented-capture"]["presentation"]["models"][model_2000x]["fields"]["segments"]["maximum"] == 250
    assert "delay" not in commands["measure"]["presentation"]["models"][model_2000x]["fields"]["item"]["options"]
    assert "area" not in commands["measure"]["presentation"]["models"][model_2000x]["fields"]["item"]["options"]
    assert "area" not in commands["measure-log"]["presentation"]["models"][model_2000x]["fields"]["items"]["options"]
    segmented = commands["segmented-memory"]["presentation"]
    assert segmented["kind"] == "setting"
    assert segmented["query_value"] == "query"
    assert segmented["action_choices"] == ["enable", "disable", "select"]
    assert commands["math-vertical"]["presentation"]["readback_fields"] == {
        "range_value": "range"
    }
    assert commands["trigger-pulse-width"]["presentation"]["readback_fields"] == {
        "time_seconds": {
            "selector_field": "qualifier",
            "fields": {
                "greater-than": "greater_than_seconds",
                "less-than": "less_than_seconds",
            },
        },
        "min_time_seconds": "range_min_seconds",
        "max_time_seconds": "range_max_seconds",
        "level": "level_volts",
    }
    assert commands["trigger-tv"]["presentation"]["readback_fields"] == {
        "mode": "tv_mode"
    }
    vectors = commands["display-vectors"]["presentation"]
    assert {key: value for key, value in vectors.items() if key != "models"} == {
        "kind": "one-way",
        "action": "enable",
        "action_field": "action",
        "apply_value": "set",
    }
    assert commands["measure-show"]["presentation"]["kind"] == "setting"
    assert commands["measure-show"]["presentation"]["action"] == "apply"
    assert commands["measure-show"]["presentation"]["action_field"] == "action"
    assert commands["measure-show"]["presentation"]["query_value"] == "query"
    assert commands["measure-show"]["presentation"]["apply_value"] == "set"
    measure_show = commands["measure-show"]
    assert measure_show["presentation"]["models"][model_2000x]["fields"]["enabled"]["hidden"] is True
    assert measure_show["presentation"]["models"][model_3000x]["fields"]["enabled"]["hidden"] is True
    assert "enabled" not in measure_show["presentation"]["models"][MODEL_ID]["fields"]

    measure_window = commands["measure-window"]
    window_field = next(field for field in measure_window["fields"] if field["name"] == "window")
    assert window_field["help_key"] == "measure-window.window"
    assert window_field["label_key"] == "measure-window.window"
    assert window_field["option_label"] == "measure-window.window"
    assert window_field["help_by_value"] == {
        option: f"measure-window.window.{option}"
        for option in MEASUREMENT_WINDOW_CHOICES
    }
    assert measure_window["presentation"]["models"][model_2000x]["fields"]["window"]["options"] == [
        "main", "zoom", "auto"
    ]
    assert measure_window["presentation"]["models"][model_3000x]["fields"]["window"]["options"] == [
        "main", "zoom", "auto"
    ]
    assert measure_window["presentation"]["models"][MODEL_ID]["fields"]["window"]["options"] == [
        "main", "zoom", "auto", "gate"
    ]

    acquisition_type = next(
        field for field in commands["acquisition"]["fields"] if field["name"] == "type"
    )
    assert acquisition_type["label_key"] == "acquisition.type"
    assert acquisition_type["help_by_value"] == {
        "normal": "acquisition.type.normal",
        "average": "acquisition.type.average",
        "high_resolution": "acquisition.type.high_resolution",
        "peak": "acquisition.type.peak",
    }

    intensity_value = next(
        field for field in commands["display-intensity"]["fields"] if field["name"] == "value"
    )
    assert intensity_value["label_key"] == "display-intensity.value"
    assert intensity_value["help_key"] == "display-intensity.value"
    zh = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    en = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    assert '"command.display-intensity": "波形顯示強度"' in zh
    assert '"field.display-intensity.value": "亮度"' in zh
    assert '"field.display-intensity.value": "Brightness"' in en

    persistence_fields = {
        field["name"]: field for field in commands["display-persistence"]["fields"]
    }
    assert persistence_fields["mode"]["options"] == ["minimum", "infinite", "timed"]
    assert persistence_fields["seconds"]["visible_if"][-1] == {
        "field": "mode",
        "equals": "timed",
    }

    workflow_fields = {
        field["name"]: field for field in commands["measure-log"]["fields"]
    }
    assert workflow_fields["channels"]["type"] == "multi-enum"
    assert workflow_fields["channels"]["serialize"] == "csv"
    assert all(
        validate_statistics_items((item,)) == (item,)
        for item in workflow_fields["items"]["options"]
    )
    assert not {"y_at_x", "time_at_edge", "time_at_value", "phase", "delay"}.intersection(
        workflow_fields["items"]["options"]
    )
    assert workflow_fields["pairs"]["help"]
    workflow_model = commands["measure-log"]["presentation"]["models"][MODEL_ID]
    assert workflow_model["fields"]["channels"]["options"] == [1, 2, 3, 4]

    for command_id, field_name in (("triggered-measure-loop", "items"), ("measure-until", "item")):
        field = next(field for field in commands[command_id]["fields"] if field["name"] == field_name)
        assert all(validate_statistics_items((item,)) == (item,) for item in field["options"])
        assert not {"y_at_x", "time_at_edge", "time_at_value", "phase", "delay"}.intersection(
            field["options"]
        )


def test_command_catalog_projects_fixed_numeric_constraints() -> None:
    commands = {
        entry["id"]: entry
        for entry in TestClient(app).get("/api/commands").json()
    }
    cases = (
        ("timebase-scale", "seconds_per_division", {"exclusive_minimum": 0}),
        ("channel-scale", "volts_per_division", {"exclusive_minimum": 0}),
        ("channel-probe-skew", "seconds", {"minimum": -1e-7, "maximum": 1e-7}),
        ("fft", "span_hz", {"exclusive_minimum": 0}),
        ("math-vertical", "scale", {"exclusive_minimum": 0}),
        ("trigger-delay", "time_seconds", {"minimum": 4e-9, "maximum": 10}),
        ("trigger-edge-burst", "idle_time", {"minimum": 1e-8, "maximum": 10}),
        ("serial-uart", "baud_rate", {"minimum": 100, "maximum": 12_000_000, "spinner": False}),
        ("serial-can", "baud_rate", {"minimum": 10_000, "maximum": 5_000_000, "spinner": False}),
        ("serial-can", "sample_point", {"minimum": 30, "maximum": 90}),
        ("serial-trigger-spi", "width", {"minimum": 4, "maximum": 64}),
        ("serial-trigger-can", "data_length", {"minimum": 1, "maximum": 8}),
        ("serial-search-uart", "data", {"minimum": 0, "maximum": 255}),
        ("serial-search-spi", "width", {"minimum": 1, "maximum": 10}),
        ("serial-search-can", "data_length", {"minimum": 1, "maximum": 8}),
        ("segmented-memory", "segments", {"minimum": 2}),
        ("segmented-capture", "segments", {"minimum": 2}),
    )
    for command_id, field_name, expected in cases:
        field = next(
            field for field in commands[command_id]["fields"]
            if field["name"] == field_name
        )
        assert {key: field[key] for key in expected} == expected

    for command_id in (
        "capture",
        "segmented-capture",
        "capture-batch",
        "triggered-capture-series",
    ):
        points = next(
            field for field in commands[command_id]["fields"]
            if field["name"] == "points"
        )
        assert points == {
            "name": "points",
            "type": "integer",
            "options": [1000, 5000, 10000],
            "default": 1000,
            "help_key": "capture.points",
        }


def test_capture_points_integer_options_rejected_pre_queue() -> None:
    # valid fixed choices pass pre-queue
    for points in (1000, 5000, 10000):
        request = validate_job_request({
            "command": "capture",
            "mode": "live",
            "model_id": MODEL_ID,
            "resource": "USB0::TEST::INSTR",
            "parameters": {"channels": "1", "points": points, "format": "byte"},
        })
        assert request["parameters"]["points"] == points

    # fixed illegal value rejected before queue (integer+options membership)
    with pytest.raises(WebUIRequestError, match="points must be one of: 1000, 5000, 10000"):
        validate_job_request({
            "command": "capture",
            "mode": "live",
            "model_id": MODEL_ID,
            "resource": "USB0::TEST::INSTR",
            "parameters": {"channels": "1", "points": 1001, "format": "byte"},
        })

    # string still rejected as integer type
    with pytest.raises(WebUIRequestError, match="points must be an integer"):
        validate_job_request({
            "command": "capture",
            "mode": "live",
            "model_id": MODEL_ID,
            "resource": "USB0::TEST::INSTR",
            "parameters": {"channels": "1", "points": "5000", "format": "byte"},
        })


def test_simulated_timebase_and_display_persistence_use_setting_readback() -> None:
    client = TestClient(app)

    scale = submit(
        client,
        "timebase-scale",
        "simulate",
        {"action": "set", "seconds_per_division": 0.002},
    )
    assert scale["status"] == "completed"
    assert scale["result"]["result"]["timebase"] == {
        "seconds_per_division": 0.002
    }

    position = submit(
        client,
        "timebase-position",
        "simulate",
        {"action": "set", "position_seconds": -0.0005},
    )
    assert position["status"] == "completed"
    assert position["result"]["result"]["timebase"] == {
        "position_seconds": -0.0005
    }

    reference = submit(
        client,
        "timebase-reference",
        "simulate",
        {"action": "set", "reference": "left"},
    )
    assert reference["status"] == "completed"
    assert reference["result"]["result"]["timebase"] == {"reference": "left"}

    persistence = submit(
        client,
        "display-persistence",
        "simulate",
        {"action": "set", "mode": "timed", "seconds": 2.5},
    )
    assert persistence["status"] == "completed"
    assert persistence["result"]["result"]["persistence"]["mode"] == "timed"
    assert persistence["result"]["result"]["persistence"]["seconds"] == 2.5


@pytest.mark.parametrize(
    "model_id",
    (
        "keysight-dsox2004a",
        "keysight-dsox3024a",
        "keysight-dsox4024a",
        "keysight-dsox4034a",
    ),
)
def test_timebase_reference_is_available_for_registered_models(model_id: str) -> None:
    commands = {
        entry["id"]: entry
        for entry in TestClient(app).get("/api/commands").json()
    }

    assert commands["timebase-reference"]["presentation"]["models"][model_id][
        "supported"
    ] is True


def test_commands_expose_channel_display_measurement_dvm_and_math_subset() -> None:
    client = TestClient(app)

    response = client.get("/api/commands")

    assert response.status_code == 200
    command_ids = {entry["id"] for entry in response.json()}
    assert {
        "channel-summary",
        "channel-label",
        "channel-offset",
        "channel-coupling",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
        "display-label",
        "display-clear",
        "display-persistence",
        "display-intensity",
        "display-vectors",
        "measure-install",
        "measure-results",
        "measure-clear",
        "measure-show",
        "measure-window",
        "system-clear-status",
        "system-opc",
        "system-standard-event",
        "system-options",
        "dvm-enable",
        "dvm-source",
        "dvm-mode",
        "dvm-auto-range",
        "dvm-current",
        "dvm-query",
        "fft",
        "math-display",
        "math-vertical",
        "math-operator",
        "math-transform",
        "math-filter",
        "math-visualization",
        "math-composite-source",
        "math-clear",
    } <= command_ids
    assert "measure-source" not in command_ids
    assert "front-panel-measurements" in command_ids
    helpers = {
        entry["id"]: entry for entry in response.json()
        if entry["id"] in {
            "measure-install", "measure-results", "measure-clear", "measure-show",
            "measure-window", "measure-menu",
        }
    }
    assert all(entry["browser_hidden"] is True for entry in helpers.values())
    composite = next(
        entry for entry in response.json()
        if entry["id"] == "front-panel-measurements"
    )
    assert composite["presentation_only"] is True
    assert composite["editor"] == "measurement"
    assert "trigger" not in command_ids

    dvm_mode = next(entry for entry in response.json() if entry["id"] == "dvm-mode")
    assert next(field for field in dvm_mode["fields"] if field["name"] == "mode")["options"] == list(DVM_MODES)
    measure_window = next(entry for entry in response.json() if entry["id"] == "measure-window")
    assert next(field for field in measure_window["fields"] if field["name"] == "window")["options"] == list(
        MEASUREMENT_WINDOW_CHOICES
    )
    math_operator = next(entry for entry in response.json() if entry["id"] == "math-operator")
    assert next(field for field in math_operator["fields"] if field["name"] == "operation")["options"] == list(
        MATH_OPERATIONS
    )
    assert next(field for field in math_operator["fields"] if field["name"] == "source1")["options"] == list(
        MATH_SOURCES
    )
    math_composite = next(entry for entry in response.json() if entry["id"] == "math-composite-source")
    assert next(field for field in math_composite["fields"] if field["name"] == "operation")["options"] == list(
        MATH_COMPOSITE_OPERATIONS
    )


def test_fft_catalog_projects_advanced_fields_by_model_capability() -> None:
    fft = next(
        entry for entry in TestClient(app).get("/api/commands").json()
        if entry["id"] == "fft"
    )
    fields = {field["name"]: field for field in fft["fields"]}
    advanced_fields = {
        "fft_operation",
        "start_hz",
        "stop_hz",
        "gate",
        "phase_reference",
        "detection_type",
        "detection_points",
    }

    assert fields["fft_operation"]["options"] == list(FFT_OPERATIONS)
    assert fields["fft_operation"]["default"] == "fft"
    assert fields["gate"]["options"] == list(FFT_GATES)
    assert fields["phase_reference"]["options"] == list(FFT_PHASE_REFERENCES)
    assert fields["detection_type"]["options"] == list(FFT_DETECTION_TYPES)
    assert fields["phase_reference"]["visible_if"] == [
        {"field": "action", "equals": "set"},
        {"field": "fft_operation", "equals": "fft-phase"},
    ]
    basic = fft["presentation"]["models"]["keysight-dsox2004a"]["fields"]
    advanced = fft["presentation"]["models"][MODEL_ID]["fields"]
    assert all(basic[name]["hidden"] is True for name in advanced_fields)
    assert advanced_fields.isdisjoint(advanced)
    assert "units" not in basic
    assert advanced["units"]["visible_if"] == [
        {"field": "fft_operation", "equals": "fft"},
    ]


def test_advanced_math_catalog_exposes_operation_specific_fields() -> None:
    commands = {
        entry["id"]: entry for entry in TestClient(app).get("/api/commands").json()
    }
    transform = {field["name"]: field for field in commands["math-transform"]["fields"]}
    math_filter = {field["name"]: field for field in commands["math-filter"]["fields"]}
    visualization = {
        field["name"]: field for field in commands["math-visualization"]["fields"]
    }

    assert transform["operation"]["options"] == list(MATH_TRANSFORMS)
    assert transform["input_offset"]["visible_if"][-1] == {
        "field": "operation", "equals": "integrate"
    }
    assert transform["gain"]["visible_if"][-1] == {
        "field": "operation", "equals": "linear"
    }
    assert transform["linear_offset"]["visible_if"][-1] == {
        "field": "operation", "equals": "linear"
    }
    assert math_filter["operation"]["options"] == list(MATH_FILTER_OPERATIONS)
    assert math_filter["cutoff_hz"]["visible_if"][-1] == {
        "field": "operation", "in": ["low-pass", "high-pass"]
    }
    assert math_filter["average_count"]["visible_if"][-1] == {
        "field": "operation", "equals": "average"
    }
    assert visualization["operation"]["options"] == list(
        MATH_VISUALIZATION_OPERATIONS
    )
    assert visualization["measurement"]["options"] == list(MATH_TREND_MEASUREMENTS)
    assert visualization["source2"]["visible_if"][-1] == {
        "field": "measurement", "equals": "vratio"
    }


def test_advanced_math_catalog_projects_model_capabilities_and_trend_fields() -> None:
    commands = {
        entry["id"]: entry for entry in TestClient(app).get("/api/commands").json()
    }
    basic_id = "keysight-dsox2004a"
    advanced_id = "keysight-dsox4034a"

    transform_models = commands["math-transform"]["presentation"]["models"]
    assert transform_models[basic_id]["fields"]["source"]["options"] == [
        *MATH_SOURCES, "composite"
    ]
    assert transform_models[advanced_id]["fields"]["source"]["options"] == [
        option for option in MATH_TRANSFORM_SOURCES if option != "composite"
    ]

    filter_models = commands["math-filter"]["presentation"]["models"]
    assert filter_models[basic_id]["fields"]["operation"]["options"] == [
        "low-pass", "high-pass"
    ]
    assert filter_models[advanced_id]["fields"]["operation"]["options"] == list(
        MATH_FILTER_OPERATIONS
    )

    visualization_models = commands["math-visualization"]["presentation"]["models"]
    basic = visualization_models[basic_id]["fields"]
    advanced = visualization_models[advanced_id]["fields"]
    assert basic["operation"]["options"] == ["magnify", "trend"]
    assert basic["measurement_slot"]["hidden"] is True
    assert advanced["operation"]["options"] == list(MATH_VISUALIZATION_OPERATIONS)
    assert advanced["measurement"]["hidden"] is True
    assert advanced["source2"]["hidden"] is True
    assert advanced["measurement_slot"]["required_if"] == [
        {"field": "action", "equals": "set"},
        {"field": "operation", "equals": "trend"},
    ]
    assert advanced["source"]["required_if"][-1] == {
        "field": "operation",
        "in": ["magnify", "maximum", "minimum", "peak", "max-hold", "min-hold"],
    }


def test_advanced_math_validation_reuses_core_series_rules() -> None:
    basic_trend = validate_job_request({
        "command": "math-visualization",
        "mode": "simulate",
        "model_id": "keysight-dsox2004a",
        "parameters": {
            "action": "set",
            "function": 1,
            "operation": "trend",
            "source": "channel1",
            "measurement": "vavg",
        },
    })
    assert basic_trend["parameters"]["measurement"] == "vavg"

    advanced_trend = validate_job_request({
        "command": "math-visualization",
        "mode": "simulate",
        "model_id": "keysight-dsox4034a",
        "parameters": {
            "action": "set",
            "function": 2,
            "operation": "trend",
            "measurement_slot": 3,
        },
    })
    assert advanced_trend["parameters"]["measurement_slot"] == 3

    cascade = validate_job_request({
        "command": "math-filter",
        "mode": "simulate",
        "model_id": "keysight-dsox4034a",
        "parameters": {
            "action": "set",
            "function": 2,
            "operation": "average",
            "source": "math1",
            "average_count": 64,
        },
    })
    assert cascade["parameters"]["source"] == "math1"

    with pytest.raises(WebUIRequestError, match="only valid for 4000X Trend"):
        validate_job_request({
            "command": "math-visualization",
            "mode": "simulate",
            "model_id": "keysight-dsox2004a",
            "parameters": {
                "action": "set",
                "function": 1,
                "operation": "trend",
                "measurement_slot": 3,
            },
        })
    with pytest.raises(WebUIRequestError, match="does not accept --source"):
        validate_job_request({
            "command": "math-visualization",
            "mode": "simulate",
            "model_id": "keysight-dsox4034a",
            "parameters": {
                "action": "set",
                "function": 2,
                "operation": "trend",
                "source": "channel1",
                "measurement_slot": 3,
            },
        })


def test_execute_advanced_math_set_and_query_paths_call_core() -> None:
    calls: list[tuple] = []

    class FakeScope:
        def configure_math_transform(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(("transform-set", args, kwargs))

        def query_math_transform(self, function):  # type: ignore[no-untyped-def]
            calls.append(("transform-query", function))
            return {"function": function, "operation": "linear", "gain": 2.0}

        def configure_math_filter(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(("filter-set", args, kwargs))

        def query_math_filter(self, function):  # type: ignore[no-untyped-def]
            calls.append(("filter-query", function))
            return {"function": function, "operation": "average", "average_count": 64}

        def configure_math_visualization(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(("visualization-set", args, kwargs))

        def query_math_visualization(self, function):  # type: ignore[no-untyped-def]
            calls.append(("visualization-query", function))
            return {"function": function, "operation": "trend", "measurement_slot": 3}

    scope = FakeScope()
    transform = command_execution_module._execute_math_transform(scope, {
        "action": "set", "function": 2, "operation": "linear", "source": "math1",
        "gain": 2.0, "linear_offset": -1.0,
    })
    command_execution_module._execute_math_transform(
        scope, {"action": "query", "function": 2}
    )
    math_filter = command_execution_module._execute_math_filter(scope, {
        "action": "set", "function": 2, "operation": "average", "source": "math1",
        "average_count": 64,
    })
    command_execution_module._execute_math_filter(
        scope, {"action": "query", "function": 2}
    )
    visualization = command_execution_module._execute_math_visualization(scope, {
        "action": "set", "function": 2, "operation": "trend", "measurement_slot": 3,
    })
    command_execution_module._execute_math_visualization(
        scope, {"action": "query", "function": 2}
    )

    assert calls == [
        ("transform-set", (2, "linear", "math1"), {
            "input_offset": None, "gain": 2.0, "linear_offset": -1.0,
        }),
        ("transform-query", 2),
        ("transform-query", 2),
        ("filter-set", (2, "average", "math1"), {
            "cutoff_hz": None, "average_count": 64, "smooth_points": None,
        }),
        ("filter-query", 2),
        ("filter-query", 2),
        ("visualization-set", (2, "trend"), {
            "source": None, "source2": None, "measurement": None, "measurement_slot": 3,
        }),
        ("visualization-query", 2),
        ("visualization-query", 2),
    ]
    assert transform["result"]["math_transform"]["gain"] == 2.0
    assert math_filter["result"]["math_filter"]["average_count"] == 64
    assert visualization["result"]["math_visualization"]["measurement_slot"] == 3


def test_fft_advanced_validation_reuses_core_range_mode_rule() -> None:
    with pytest.raises(
        WebUIRequestError,
        match="--center-hz/--span-hz cannot be combined with --start-hz/--stop-hz",
    ):
        validate_job_request({
            "command": "fft",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {
                "action": "set",
                "function": 1,
                "source_channel": 1,
                "center_hz": 1_000,
                "start_hz": 100,
            },
        })


def test_execute_fft_passes_advanced_parameters_and_preserves_query_state() -> None:
    received: dict[str, object] = {}

    class FakeScope:
        def configure_fft(self, function, source_channel, **kwargs):  # type: ignore[no-untyped-def]
            received.update(function=function, source_channel=source_channel, **kwargs)

        def query_fft(self, function):  # type: ignore[no-untyped-def]
            return {
                "function": function,
                "bin_size_hz": 125.0,
                "sample_rate_hz": 1_000_000.0,
                "resolution_bandwidth_hz": 250.0,
            }

    result = command_execution_module._execute_fft(
        FakeScope(),
        {
            "action": "set",
            "function": 2,
            "source_channel": 1,
            "fft_operation": "fft-phase",
            "start_hz": 100.0,
            "stop_hz": 1_000_000.0,
            "gate": "zoom",
            "phase_reference": "display",
            "detection_type": "average",
            "detection_points": 4096,
        },
    )

    assert received == {
        "function": 2,
        "source_channel": 1,
        "units": None,
        "window": None,
        "center_hz": None,
        "span_hz": None,
        "display": None,
        "fft_operation": "fft-phase",
        "start_hz": 100.0,
        "stop_hz": 1_000_000.0,
        "gate": "zoom",
        "phase_reference": "display",
        "detection_type": "average",
        "detection_points": 4096,
    }
    assert result["result"]["fft"] == {
        "function": 2,
        "bin_size_hz": 125.0,
        "sample_rate_hz": 1_000_000.0,
        "resolution_bandwidth_hz": 250.0,
    }


def test_commands_expose_reference_and_save_subset() -> None:
    client = TestClient(app)

    response = client.get("/api/commands")

    assert response.status_code == 200
    commands = {entry["id"]: entry for entry in response.json()}
    expected = {
        "reference-save",
        "reference-display",
        "reference-label",
        "reference-clear",
        "reference-query",
        "save-pwd",
        "save-filename",
        "save-image-format",
        "save-image-palette",
        "save-image-ink-saver",
        "save-image-factors",
        "save-image",
        "save-waveform-format",
        "save-waveform-length",
        "save-waveform-length-max",
        "save-waveform",
    }

    assert expected <= commands.keys()
    for command in expected:
        assert commands[command]["modes"] == ["live", "simulate"]
        assert commands[command]["browser_hidden"] is True
    assert commands["reference-waveform"]["presentation_only"] is True
    assert commands["reference-waveform"]["editor"] == "reference"
    assert commands["save-export"]["presentation_only"] is True
    assert commands["save-export"]["editor"] == "save-export"
    assert expected <= {entry["id"] for entry in commands_module.COMMANDS}
    assert {"reference-waveform", "save-export"}.isdisjoint(
        commands_module._COMMAND_BY_ID
    )

    browser_commands = [
        entry for entry in response.json() if not entry.get("browser_hidden")
    ]
    assert [
        entry["id"]
        for entry in browser_commands
        if entry["category"] == "Reference"
    ] == ["reference-waveform"]
    assert [
        entry["id"]
        for entry in browser_commands
        if entry["category"] == "Save / Export"
    ] == ["save-export"]
    categories = list(dict.fromkeys(entry["category"] for entry in browser_commands))
    assert categories.index("Capture") < categories.index("Reference")
    assert categories.index("Reference") < categories.index("Save / Export")
    assert categories.index("Save / Export") < categories.index("System")


def test_representative_reference_and_save_simulated_commands_complete_without_artifacts() -> None:
    client = TestClient(app)

    reference = submit(
        client,
        "reference-label",
        "simulate",
        {"action": "set", "slot": 1, "label": "BASELINE"},
    )
    assert reference["status"] == "completed"
    assert reference["result"]["result"]["label"]["label"] == "BASELINE"

    save_setting = submit(
        client,
        "save-image-format",
        "simulate",
        {"action": "set", "format": "bmp24"},
    )
    assert save_setting["status"] == "completed"
    assert save_setting["result"]["result"]["state"]["format"] == "bmp24"

    save = submit(client, "save-image", "simulate", {"filename": "screen.png"})
    assert save["status"] == "completed"
    assert save["artifacts"] == []
    assert save["result"]["result"]["save"]["instrument_side"] is True


def test_save_filename_validation_is_preserved() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        json={
            "command": "save-image",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"filename": "screen;bad.png"},
        },
    )

    assert response.status_code == 400
    assert "filename" in response.json()["detail"].lower()


def test_query_only_commands_do_not_default_set_only_channels() -> None:
    client = TestClient(app)

    response = client.get("/api/commands")

    assert response.status_code == 200
    commands = {entry["id"]: entry for entry in response.json()}
    measure_source_command = next(
        entry for entry in commands_module.COMMANDS if entry["id"] == "measure-source"
    )
    measure_source = next(
        field for field in measure_source_command["fields"]
        if field["name"] == "source_channel"
    )
    dvm_source = next(field for field in commands["dvm-source"]["fields"] if field["name"] == "channel")
    assert "default" not in measure_source
    assert "default" not in dvm_source


def test_measure_source_remains_in_backend_validation_contract() -> None:
    backend_ids = {entry["id"] for entry in commands_module.COMMANDS}
    assert {
        "measure", "measure-install", "measure-results", "measure-clear", "measure-show",
        "measure-source", "measure-window", "measurement-statistics",
    } <= backend_ids
    assert "front-panel-measurements" not in commands_module._COMMAND_BY_ID

    request = validate_job_request({
        "command": "measure-source",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {"action": "query"},
    })

    assert request["command"] == "measure-source"
    assert request["parameters"] == {"action": "query"}


def test_measure_install_validation_and_execution_use_core_path(tmp_path: Path) -> None:
    request = validate_job_request({
        "command": "measure-install",
        "mode": "simulate",
        "model_id": "keysight-dsox2004a",
        "parameters": {"source_channel": 2, "item": "frequency"},
    })

    assert request["parameters"] == {"source_channel": 2, "item": "frequency"}
    with pytest.raises(WebUIRequestError, match="front-panel measurement"):
        validate_job_request({
            "command": "measure-install",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"source_channel": 1, "item": "phase"},
        })

    calls = []

    class FakeScope:
        capabilities = object()

        def install_measurement(self, source_channel: int, item: str) -> None:
            calls.append((source_channel, item))

    result = command_execution_module._execute_scope_command(
        FakeScope(),
        "measure-install",
        "SIM::INSTR",
        request["parameters"],
        tmp_path,
    )

    assert calls == [(2, "frequency")]
    assert result == {
        "exit_code": 0,
        "result": {"action": "measure-install"},
        "artifacts": [],
    }


def test_measurement_statistics_validation_and_reset_execution(tmp_path: Path) -> None:
    with pytest.raises(WebUIRequestError, match="not supported"):
        validate_job_request({
            "command": "measurement-statistics",
            "mode": "simulate",
            "model_id": "keysight-dsox2004a",
            "parameters": {"action": "query"},
        })

    for parameters, message in (
        ({"action": "increment"}, "query, set, or reset"),
        ({
            "action": "set",
            "mode": "current",
            "display_enabled": False,
            "max_count_mode": "infinite",
            "relative_stddev_enabled": False,
        }, "mode must be all"),
    ):
        with pytest.raises(WebUIRequestError, match=message):
            validate_job_request({
                "command": "measurement-statistics",
                "mode": "simulate",
                "model_id": MODEL_ID,
                "parameters": parameters,
            })

    statistics_definition = next(
        entry for entry in commands_module.COMMANDS
        if entry["id"] == "measurement-statistics"
    )
    statistics_fields = {
        field["name"]: field for field in statistics_definition["fields"]
    }
    assert statistics_fields["action"]["options"] == ("query", "set", "reset")
    assert statistics_fields["mode"]["options"] == ("all",)

    request = validate_job_request({
        "command": "measurement-statistics",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {
            "action": "set",
            "mode": "all",
            "display_enabled": False,
            "max_count_mode": "numeric",
            "max_count": 2000,
            "relative_stddev_enabled": True,
        },
    })
    assert request["parameters"]["max_count"] == 2000

    calls = []

    class FakeScope:
        capabilities = object()

        def reset_measurement_statistics(self):
            calls.append("reset")

        def query_measurement_statistics_state(self):
            return {"mode": "all", "max_count": None}

        def query_measurement_results(self):
            return {"statistics_items": [{"label": "Vpp(1)", "current": 1.0}]}

    result = command_execution_module._execute_scope_command(
        FakeScope(),
        "measurement-statistics",
        "SIM::INSTR",
        {"action": "reset"},
        tmp_path,
    )

    assert calls == ["reset"]
    assert result["result"]["statistics"]["results"]["statistics_items"][0]["label"] == "Vpp(1)"


@pytest.mark.parametrize(
    ("model_id", "accepted"),
    (
        ("keysight-dsox2004a", False),
        ("keysight-dsox3024a", False),
        (MODEL_ID, True),
    ),
)
def test_measurement_window_gate_validation_follows_model_series(
    model_id: str, accepted: bool
) -> None:
    payload = {
        "command": "measure-window",
        "mode": "simulate",
        "model_id": model_id,
        "parameters": {"action": "set", "window": "gate"},
    }

    if not accepted:
        with pytest.raises(WebUIRequestError, match="measurement window gate is not supported"):
            validate_job_request(payload)
        return

    request = validate_job_request(payload)
    assert request["parameters"] == {"action": "set", "window": "GATE"}


@pytest.mark.parametrize("model_id", ("keysight-dsox2004a", "keysight-dsox3024a"))
def test_measurement_show_off_validation_follows_model_series(model_id: str) -> None:
    with pytest.raises(WebUIRequestError, match="measure-show OFF is not supported"):
        validate_job_request({
            "command": "measure-show",
            "mode": "simulate",
            "model_id": model_id,
            "parameters": {"action": "set", "enabled": False},
        })


def test_measurement_show_enabled_is_backward_compatible_and_4000x_supports_off() -> None:
    omitted = validate_job_request({
        "command": "measure-show",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {"action": "set"},
    })
    assert omitted["parameters"] == {"action": "set"}
    enabled = validate_job_request({
        "command": "measure-show",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {"action": "set", "enabled": True},
    })
    assert enabled["parameters"]["enabled"] is True
    disabled = validate_job_request({
        "command": "measure-show",
        "mode": "simulate",
        "model_id": MODEL_ID,
        "parameters": {"action": "set", "enabled": False},
    })
    assert disabled["parameters"]["enabled"] is False
    with pytest.raises(WebUIRequestError, match="query cannot include enabled"):
        validate_job_request({
            "command": "measure-show",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "query", "enabled": True},
        })


def test_measure_and_dvm_query_requests_complete_without_set_only_channels() -> None:
    client = TestClient(app)

    for command in ("measure-source", "dvm-source"):
        job = submit(client, command, "simulate", {"action": "query"})
        assert job["status"] == "completed", (command, job)


def test_representative_channel_display_dvm_math_and_fft_simulated_commands_complete() -> None:
    client = TestClient(app)

    for command, parameters in (
        ("channel-offset", {"action": "set", "channel": 1, "volts": 0.25}),
        ("display-intensity", {"action": "set", "value": 75}),
        ("measure-window", {"action": "set", "window": "zoom"}),
        ("dvm-mode", {"action": "set", "mode": "dc-rms"}),
        (
            "fft",
            {
                "action": "set",
                "function": 1,
                "source_channel": 1,
                "units": "vrms",
                "window": "hanning",
                "display": True,
            },
        ),
        (
            "math-operator",
            {
                "action": "set",
                "function": 1,
                "operation": "add",
                "source1": "channel1",
                "source2": "channel2",
            },
        ),
        (
            "math-transform",
            {
                "action": "set",
                "function": 1,
                "operation": "linear",
                "source": "channel1",
                "gain": 2.0,
                "linear_offset": -1.0,
            },
        ),
        (
            "math-filter",
            {
                "action": "set",
                "function": 1,
                "operation": "average",
                "source": "channel1",
                "average_count": 64,
            },
        ),
        (
            "math-visualization",
            {
                "action": "set",
                "function": 1,
                "operation": "trend",
                "measurement_slot": 3,
            },
        ),
    ):
        job = submit(client, command, "simulate", parameters)
        assert job["status"] == "completed", (command, job)


def test_channel_display_dvm_math_and_fft_invalid_and_unsupported_requests_are_rejected() -> None:
    client = TestClient(app)

    invalid = client.post(
        "/api/jobs",
        json={
            "command": "channel-coupling",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "set", "channel": 1, "coupling": "invalid"},
        },
    )
    assert invalid.status_code == 400

    fft_query = client.post(
        "/api/jobs",
        json={
            "command": "fft",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "query", "function": 1, "source_channel": 1},
        },
    )
    assert fft_query.status_code == 400
    assert "cannot include" in fft_query.json()["detail"]

    invalid_math_query = client.post(
        "/api/jobs",
        json={
            "command": "math-transform",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "query", "function": 1, "source": "channel1"},
        },
    )
    assert invalid_math_query.status_code == 400
    assert "query cannot include source" in invalid_math_query.json()["detail"]


def test_channel_display_dvm_math_and_fft_capability_rejection_remains_core_owned() -> None:
    client = TestClient(app)

    job = submit(
        client,
        "math-composite-source",
        "simulate",
        {"action": "set", "operation": "add", "source1": "channel1", "source2": "channel2"},
    )

    assert job["status"] == "failed"
    assert "not supported by this capability profile" in job["error"]


def test_simulated_measure_and_dry_run_capture_complete() -> None:
    client = TestClient(app)

    simulated = submit(client, "measure", "simulate", {"item": "vpp", "channel": 1})
    assert simulated["status"] == "completed"
    assert simulated["result"]["result"]["valid"] is True

    dry_run = submit(
        client,
        "capture",
        "dry-run",
        {"channels": "1", "points": 1000, "format": "byte"},
    )
    assert dry_run["status"] == "completed"
    assert dry_run["result"]["result"]["status"] == "planned"
    assert dry_run["result"]["result"]["planned_scpi"]


def test_dry_run_acquisition_query_is_planned() -> None:
    client = TestClient(app)

    job = submit(client, "acquisition", "dry-run", {"action": "query"})

    assert job["status"] == "completed"
    assert job["result"]["result"]["status"] == "planned"
    assert job["result"]["result"]["planned_scpi"]


def test_dry_run_acquisition_set_is_rejected_before_queueing(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(
        app_module.job_manager,
        "submit",
        lambda _request: pytest.fail("unsupported dry-run acquisition was queued"),
    )

    response = client.post(
        "/api/jobs",
        json={
            "command": "acquisition",
            "mode": "dry-run",
            "model_id": MODEL_ID,
            "parameters": {"action": "set", "type": "normal"},
        },
    )

    assert response.status_code == 400
    assert "query only" in response.json()["detail"]


def test_job_submission_returns_503_during_manager_shutdown(monkeypatch) -> None:
    manager = JobManager()
    asyncio.run(manager.shutdown())
    monkeypatch.setattr(app_module, "job_manager", manager)
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        json={
            "command": "measure",
            "mode": "dry-run",
            "model_id": MODEL_ID,
            "parameters": {"item": "vpp", "channel": 1},
        },
    )

    assert response.status_code == 503
    assert "not accepted" in response.json()["detail"]


def test_running_cancel_api_stays_running_until_cleanup(monkeypatch, tmp_path) -> None:
    manager = JobManager()
    started = threading.Event()
    cancellation_observed = threading.Event()
    release = threading.Event()

    def blocking_execute(*_args, artifact_dir, stop_requested, **_kwargs):
        started.set()
        deadline = time.monotonic() + 2
        while not stop_requested():
            if time.monotonic() >= deadline:
                raise AssertionError("cancellation was not observed")
            time.sleep(0.01)
        artifact_path = artifact_dir / "waveform_0001.csv"
        artifact_path.write_text("time,CH1\n0,0\n", encoding="utf-8")
        cancellation_observed.set()
        release.wait(timeout=2)
        return {
            "exit_code": 130,
            "result": {"status": "cancelled", "completed_count": 1},
            "artifacts": [{"kind": "csv", "path": str(artifact_path)}],
        }

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", blocking_execute)
    monkeypatch.setattr(app_module, "job_manager", manager)
    output_root = tmp_path / "cancel-output"
    output_root.mkdir()
    client = TestClient(app)
    response = client.post(
        "/api/jobs",
        json={
            "command": "capture-batch",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "pc_output_dir": str(output_root),
            "parameters": {
                "channels": "1",
                "points": 1000,
                "format": "byte",
                "count": 2,
                "interval_seconds": 0,
            },
        },
    )
    job_id = response.json()["job_id"]
    try:
        assert started.wait(timeout=2)
        cancelled = client.post(f"/api/jobs/{job_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "running"
        assert cancellation_observed.wait(timeout=2)
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "running"

        release.set()
        terminal = wait_for_job(client, job_id)
        assert terminal["status"] == "cancelled"
        assert terminal["result"]["result"] == {
            "status": "cancelled",
            "completed_count": 1,
        }
        assert [artifact["name"] for artifact in terminal["artifacts"]] == [
            "waveform_0001.csv"
        ]
        artifact = client.get(terminal["artifacts"][0]["url"])
        assert artifact.status_code == 200
        assert artifact.text.splitlines() == ["time,CH1", "0,0"]
    finally:
        release.set()
        asyncio.run(manager.shutdown(timeout_s=2))


def test_simulated_capture_artifact_is_registered_and_downloadable(tmp_path) -> None:
    client = TestClient(app)

    job = submit(
        client,
        "capture",
        "simulate",
        {"channels": "1", "points": 1000, "format": "byte"},
        pc_output_dir=tmp_path / "capture-output",
    )

    assert job["status"] == "completed"
    artifact = next(item for item in job["artifacts"] if item["kind"] == "csv")
    response = client.get(artifact["url"])
    assert response.status_code == 200
    assert response.content


def test_invalid_request_is_rejected_before_queueing() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/jobs",
        json={
            "command": "capture",
            "mode": "live",
            "parameters": {"channels": "1", "points": 1000, "format": "byte"},
        },
    )

    assert response.status_code == 400
    assert "resource" in response.json()["detail"]


def test_queued_and_running_job_cancellation_requests_are_accepted(monkeypatch) -> None:
    manager = JobManager()
    started = threading.Event()
    release = threading.Event()
    started_count = 0
    count_lock = threading.Lock()

    def blocking_execute(*_args, **_kwargs):
        nonlocal started_count
        with count_lock:
            started_count += 1
            if started_count == 4:
                started.set()
        release.wait(timeout=2)
        return {"exit_code": 0, "result": {"ok": True}, "artifacts": []}

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", blocking_execute)
    request = {
        "command": "identify",
        "mode": "simulate",
        "resource": None,
        "model_id": MODEL_ID,
        "parameters": {},
    }
    jobs = [manager.submit(request) for _ in range(4)]
    try:
        assert started.wait(timeout=2)
        running_state, running_message, running_accepted = manager.cancel(jobs[0].job_id)
        assert running_state == "running"
        assert "waiting for cleanup" in running_message
        assert running_accepted is True
        assert manager.get(jobs[0].job_id).status == "running"
        assert manager.get(jobs[0].job_id).cancel_requested is True

        queued = manager.submit(request)
        queued_state, _queued_message, queued_accepted = manager.cancel(queued.job_id)
        assert queued_state == "cancelled"
        assert queued_accepted is True
        assert manager.get(queued.job_id).status == "cancelled"
    finally:
        release.set()
        asyncio.run(manager.shutdown(timeout_s=2))


def test_shutdown_rejects_new_jobs_and_waits_for_running_jobs(monkeypatch) -> None:
    manager = JobManager()
    started = threading.Event()
    release = threading.Event()
    started_count = 0
    count_lock = threading.Lock()

    def blocking_execute(*_args, **_kwargs):
        nonlocal started_count
        with count_lock:
            started_count += 1
            if started_count == 4:
                started.set()
        release.wait(timeout=2)
        return {"exit_code": 0, "result": {"ok": True}, "artifacts": []}

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", blocking_execute)
    request = {
        "command": "identify",
        "mode": "simulate",
        "resource": None,
        "model_id": MODEL_ID,
        "parameters": {},
    }
    jobs = [manager.submit(request) for _ in range(5)]
    shutdown_errors = []
    shutdown_thread = threading.Thread(
        target=lambda: _capture_exception(
            shutdown_errors, _run_manager_shutdown, manager=manager, timeout_s=2
        )
    )
    try:
        assert started.wait(timeout=2)
        shutdown_thread.start()
        time.sleep(0.05)
        assert all(manager.get(job.job_id).status == "running" for job in jobs[:4])
        assert manager.get(jobs[4].job_id).status == "cancelled"
        with pytest.raises(JobManagerShuttingDown):
            manager.submit(request)
        assert shutdown_thread.is_alive()
        release.set()
        shutdown_thread.join(timeout=2)
        assert shutdown_errors == []
        assert all(manager.get(job.job_id).status == "cancelled" for job in jobs[:4])
    finally:
        release.set()
        shutdown_thread.join(timeout=2)
        if not manager._executor_shutdown:
            manager._executor.shutdown(wait=True)


def test_shutdown_timeout_leaves_executor_for_retry(monkeypatch) -> None:
    manager = JobManager()
    started = threading.Event()
    release = threading.Event()
    shutdown_calls = []
    original_shutdown = manager._executor.shutdown

    def blocking_execute(*_args, **_kwargs):
        started.set()
        release.wait(timeout=2)
        return {"exit_code": 0, "result": {"ok": True}, "artifacts": []}

    def recording_shutdown(*args, **kwargs):
        shutdown_calls.append((args, kwargs))
        return original_shutdown(*args, **kwargs)

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", blocking_execute)
    monkeypatch.setattr(manager._executor, "shutdown", recording_shutdown)
    request = {
        "command": "identify",
        "mode": "simulate",
        "resource": None,
        "model_id": MODEL_ID,
        "parameters": {},
    }
    job = manager.submit(request)
    try:
        assert started.wait(timeout=2)
        with pytest.raises(TimeoutError):
            asyncio.run(manager.shutdown(timeout_s=0.05))
        assert shutdown_calls == []
        release.set()
        asyncio.run(manager.shutdown(timeout_s=2))
        assert shutdown_calls == [((), {"wait": True})]
        assert manager.get(job.job_id).status == "cancelled"
    finally:
        release.set()
        if not manager._executor_shutdown:
            manager._executor.shutdown(wait=True)


def test_scope_close_failure_is_preserved_and_blocks_shutdown(monkeypatch) -> None:
    manager = JobManager()
    started = threading.Event()
    release = threading.Event()

    def close_failure(*_args, **_kwargs):
        started.set()
        release.wait(timeout=2)
        raise ScopeSessionCloseError("close failed")

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", close_failure)
    request = {
        "command": "identify",
        "mode": "simulate",
        "resource": None,
        "model_id": MODEL_ID,
        "parameters": {},
    }
    job = manager.submit(request)
    shutdown_errors = []
    shutdown_thread = threading.Thread(
        target=lambda: _capture_exception(
            shutdown_errors, _run_manager_shutdown, manager=manager, timeout_s=2
        )
    )
    try:
        assert started.wait(timeout=2)
        shutdown_thread.start()
        for _ in range(100):
            if manager.get(job.job_id).cancel_requested:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("shutdown did not request cancellation")
        release.set()
        shutdown_thread.join(timeout=2)
        assert len(shutdown_errors) == 1
        assert isinstance(shutdown_errors[0], RuntimeError)
        assert "cleanup failed" in str(shutdown_errors[0])
        completed = _wait_for_manager_job(manager, job.job_id)
        assert completed.status == "failed"
        assert "close failed" in completed.error
        with pytest.raises(RuntimeError, match="cleanup failed"):
            asyncio.run(manager.shutdown(timeout_s=2))
    finally:
        release.set()
        shutdown_thread.join(timeout=2)
        if not manager._executor_shutdown:
            manager._executor.shutdown(wait=True)


def _capture_exception(target, function, **kwargs):
    try:
        function(**kwargs)
    except BaseException as exc:
        target.append(exc)


def _run_manager_shutdown(manager, timeout_s):
    asyncio.run(manager.shutdown(timeout_s=timeout_s))


def _wait_for_manager_job(manager, job_id):
    for _ in range(100):
        job = manager.get(job_id)
        if job.status not in {"queued", "running"}:
            return job
        time.sleep(0.02)
    raise AssertionError("manager job did not reach a terminal state")


@pytest.mark.parametrize(
    ("command", "runner_name", "parameters"),
    (
        ("capture-batch", "run_capture_batch", {"channels": (1,), "points": 1000, "format": "byte", "count": 2, "interval_seconds": 0}),
        ("measure-log", "run_measure_log", {"channels": (1,), "items": ("vpp",), "pairs": (), "pair_items": (), "interval_seconds": 0, "count": 2}),
        ("measure-until", "run_measure_until", {"channel": 1, "item": "vpp", "operator": "gt", "threshold": 0.1, "timeout_seconds": 1, "interval_seconds": 0}),
        ("triggered-measure-loop", "run_triggered_measure_loop", {"count": 2, "trigger_timeout_seconds": 1, "channels": (1,), "items": ("vpp",), "pairs": (), "pair_items": (), "interval_seconds": 0}),
        ("triggered-capture-series", "run_triggered_capture_series", {"channels": (1,), "count": 2, "trigger_timeout_seconds": 1, "points": 1000, "format": "byte", "interval_seconds": 0}),
    ),
)
def test_long_workflows_receive_existing_core_stop_callback(
    monkeypatch,
    tmp_path,
    command,
    runner_name,
    parameters,
) -> None:
    stop_requested = lambda: True
    received_stop = []
    received_progress = []

    def fake_runner(
        _scope,
        _resource,
        _request,
        *,
        stop_requested=None,
        progress_reporter=None,
    ):
        received_stop.append(stop_requested)
        received_progress.append(progress_reporter)
        return command_execution_module.OperationResult(
            exit_code=0, result={"status": "cancelled"}
        )

    monkeypatch.setattr(command_execution_module, runner_name, fake_runner)

    command_execution_module._execute_trigger_search_serial_segmented_workflow_command(
        object(),
        command,
        "USB0::TEST::INSTR",
        parameters,
        tmp_path,
        stop_requested=stop_requested,
    )

    assert received_stop == [stop_requested]
    assert received_progress == [None]


def test_commands_expose_trigger_search_serial_segmented_and_workflow_families() -> None:
    client = TestClient(app)
    response = client.get("/api/commands")
    assert response.status_code == 200
    commands = {entry["id"]: entry for entry in response.json()}
    expected = {
        "trigger-edge",
        "trigger-pulse-width",
        "trigger-delay",
        "trigger-tv",
        "search-mode",
        "serial-search-uart",
        "serial-uart",
        "serial-trigger-can",
        "serial-lister-export",
        "segmented-memory",
        "segmented-capture",
        "capture-batch",
        "measure-log",
        "measure-until",
        "triggered-measure-loop",
        "triggered-capture-series",
    }
    assert expected <= commands.keys()
    assert commands["segmented-capture"]["modes"] == ["live", "simulate", "dry-run"]
    assert commands["capture-batch"]["modes"] == ["live", "simulate"]
    pulse_fields = {field["name"]: field for field in commands["trigger-pulse-width"]["fields"]}
    assert pulse_fields["time_seconds"]["visible_if"] == [
        {"field": "action", "equals": "set"},
        {"field": "qualifier", "in": ["greater-than", "less-than"]},
    ]


def test_command_catalog_exposes_required_field_contracts() -> None:
    client = TestClient(app)
    commands = {entry["id"]: entry for entry in client.get("/api/commands").json()}

    reference_fields = {
        field["name"]: field for field in commands["reference-save"]["fields"]
    }
    assert reference_fields["slot"]["required"] is True
    assert reference_fields["slot"]["label_key"] == "reference.slot"
    assert reference_fields["slot"]["option_label"] == "reference-waveform"
    assert reference_fields["slot"]["help_key"] == "reference.slot"
    assert reference_fields["source_channel"]["required"] is True
    assert reference_fields["source_channel"]["help_key"] == "reference-save.source_channel"

    english = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    chinese = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")
    assert '"field.reference.slot": "Reference waveform"' in english
    assert '"enum.reference-waveform": "Reference waveform {{value}}"' in english
    assert '"field.reference.slot": "參考波形"' in chinese
    assert '"enum.reference-waveform": "參考波形 {{value}}"' in chinese
    assert "參考波形插槽" not in chinese

    scale_fields = {
        field["name"]: field for field in commands["channel-scale"]["fields"]
    }
    assert scale_fields["volts_per_division"]["required_if"] == [
        {"field": "action", "equals": "set"}
    ]
    assert "required" not in scale_fields["volts_per_division"]

    measure_log_fields = {
        field["name"]: field for field in commands["measure-log"]["fields"]
    }
    assert measure_log_fields["stop_on_error"]["default"] is False
    capture_batch_fields = {
        field["name"]: field for field in commands["capture-batch"]["fields"]
    }
    assert capture_batch_fields["channels"]["required"] is True
    assert "default" not in capture_batch_fields["channels"]


def test_workflow_timeout_catalog_uses_exclusive_lower_bounds() -> None:
    commands = {
        entry["id"]: entry
        for entry in TestClient(app).get("/api/commands").json()
    }

    for command_id, field_name in (
        ("measure-until", "timeout_seconds"),
        ("triggered-measure-loop", "trigger_timeout_seconds"),
        ("triggered-capture-series", "trigger_timeout_seconds"),
    ):
        fields = {field["name"]: field for field in commands[command_id]["fields"]}
        assert fields[field_name]["exclusive_minimum"] == 0
        assert "minimum" not in fields[field_name]


def test_command_catalog_group_metadata_contract() -> None:
    commands = {
        entry["id"]: entry
        for entry in TestClient(app).get("/api/commands").json()
    }

    expected_groups = {
        "trigger-edge": "edge",
        "trigger-edge-coupling": "edge",
        "trigger-sweep": "common",
        "trigger-holdoff": "common",
        "external-trigger-settings": "external",
        "trigger-pulse-width": "pulse-width",
        "trigger-runt": "runt",
        "trigger-transition": "transition",
        "trigger-delay": "delay",
        "trigger-setup-hold": "setup-hold",
        "trigger-edge-burst": "edge-burst",
        "trigger-tv": "tv",
        "trigger-or": "pattern-or",
        "search-state": "basic",
        "search-event": "event",
        "serial-search-uart": "serial",
        "serial-search-can": "serial",
        "serial-mode": "bus",
        "serial-uart": "uart",
        "serial-trigger-i2c": "i2c",
        "serial-lister-display": "lister",
        "serial-lister-export": "lister",
        "save-pwd": "path-filename",
        "save-image": "image",
        "save-waveform": "waveform",
        "capture-batch": "capture",
        "measure-log": "measurement",
        "measure-until": "measurement",
        "triggered-measure-loop": "triggered",
        "channel-scale": "channel-basic",
        "channel-coupling": "channel-advanced",
    }
    for command_id, group in expected_groups.items():
        assert commands[command_id]["group"] == group, command_id

    for command_id in ("acquisition", "screenshot"):
        assert "group" not in commands[command_id], command_id


def test_serial_editor_marks_dedicated_editor_commands() -> None:
    commands = {
        entry["id"]: entry
        for entry in TestClient(app).get("/api/commands").json()
    }

    for command_id in (
        "serial-mode",
        "serial-display",
        "serial-uart",
        "serial-i2c",
        "serial-spi",
        "serial-can",
        "serial-trigger-uart",
        "serial-trigger-i2c",
        "serial-trigger-spi",
        "serial-trigger-can",
    ):
        entry = commands[command_id]
        assert entry["editor"] == "serial", command_id
        assert entry["presentation"]["kind"] == "setting", command_id
        assert entry["presentation"]["query_fields"] == ["bus"], command_id

    for command_id in ("serial-lister-display", "serial-lister-reference"):
        entry = commands[command_id]
        assert entry["editor"] == "serial", command_id
        assert entry["presentation"]["kind"] == "setting", command_id
        assert entry["presentation"]["query_fields"] == [], command_id

    for command_id in ("serial-lister-query", "serial-lister-export"):
        entry = commands[command_id]
        assert entry["editor"] == "serial", command_id

    assert "editor" not in commands["serial-query"]


def test_catalog_group_keys_stay_scoped_and_localized() -> None:
    client = TestClient(app)
    entries = client.get("/api/commands").json()
    grouped = [entry for entry in entries if "group" in entry]

    assert {entry["category"] for entry in grouped} <= {
        "Channel", "Trigger", "Search", "Serial", "Save / Export", "Workflow",
        "Cursor", "Annotation", "WGEN", "DEMO",
    }
    assert {entry["group"] for entry in grouped} == {
        "edge", "common", "external", "pulse-width", "runt", "transition",
        "delay", "setup-hold", "edge-burst", "tv", "pattern-or",
        "channel-basic", "channel-advanced",
        "basic", "event", "serial",
        "uart", "i2c", "spi", "can",
        "bus", "lister",
        "path-filename", "image", "waveform",
        "measurement", "capture", "triggered", "automation",
        "cursor", "annotation", "wgen", "demo",
    }

    static_root = Path(__file__).resolve().parents[2] / "src" / "scopes_tool_webui" / "static"
    english = (static_root / "locale_en.js").read_text(encoding="utf-8")
    chinese = (static_root / "locale_zh_tw.js").read_text(encoding="utf-8")
    for group in sorted({entry["group"] for entry in grouped}):
        key = f'"group.{group}":'
        assert key in english, key
        assert key in chinese, key


def test_trigger_search_serial_and_workflow_request_validation_regressions() -> None:
    client = TestClient(app)
    commands = {entry["id"]: entry for entry in client.get("/api/commands").json()}
    assert [field["name"] for field in commands["serial-query"]["fields"]] == ["bus"]

    serial_query = client.post(
        "/api/jobs",
        json={
            "command": "serial-query",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"bus": 1, "action": "query"},
        },
    )
    assert serial_query.status_code == 400
    assert "unknown parameter" in serial_query.json()["detail"]

    for parameters in (
        {"action": "query", "bus": 1, "mode": "async"},
        {"action": "query", "bus": 1, "data": 1},
    ):
        serial_search = client.post(
            "/api/jobs",
            json={
                "command": "serial-search-uart",
                "mode": "simulate",
                "model_id": MODEL_ID,
                "parameters": parameters,
            },
        )
        assert serial_search.status_code == 400
        assert "query cannot include" in serial_search.json()["detail"]

    invalid_measure_log = client.post(
        "/api/jobs",
        json={
            "command": "measure-log",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"count": 1, "stop_on_error": "false"},
        },
    )
    assert invalid_measure_log.status_code == 400
    assert "stop_on_error must be a boolean" in invalid_measure_log.json()["detail"]

    accepted = validate_job_request(
        {
            "command": "measure-log",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"count": 1, "stop_on_error": True},
        }
    )
    assert accepted["parameters"]["stop_on_error"] is True

    defaulted = validate_job_request(
        {
            "command": "measure-log",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"count": 1},
        }
    )
    assert defaulted["parameters"]["stop_on_error"] is False
    assert defaulted["parameters"]["save_results"] is True

    no_save = validate_job_request(
        {
            "command": "measure-until",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "pc_output_dir": "",
            "parameters": {
                "channel": 1,
                "item": "vpp",
                "operator": "gt",
                "threshold": 0,
                "timeout_seconds": 1,
                "save_results": False,
            },
        }
    )
    assert no_save["parameters"]["save_results"] is False


def test_live_multi_enum_shape_is_checked_before_scope_open() -> None:
    base = {
        "command": "capture-batch",
        "mode": "live",
        "resource": "USB::TEST::INSTR",
    }

    with pytest.raises(WebUIRequestError, match="comma-separated string or list"):
        validate_job_request({**base, "parameters": {"channels": {"value": "1"}}})

    accepted = validate_job_request(
        {**base, "parameters": {"channels": "1,2"}}
    )
    assert accepted["parameters"]["channels"] == "1,2"


def test_workflow_measurement_validation_matches_catalog_choices() -> None:
    invalid_requests = (
        ("measure-log", {"items": "y_at_x", "count": 1}),
        ("triggered-measure-loop", {"items": "delay", "count": 1, "trigger_timeout_seconds": 1}),
        ("measure-until", {"item": "time_at_value", "operator": "gt", "threshold": 0, "timeout_seconds": 1}),
    )
    for command, parameters in invalid_requests:
        with pytest.raises(WebUIRequestError, match="single-channel|non-parameterized"):
            validate_job_request(
                {
                    "command": command,
                    "mode": "simulate",
                    "model_id": MODEL_ID,
                    "parameters": parameters,
                }
            )

    accepted = validate_job_request(
        {
            "command": "measure-log",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"items": ["vpp", "frequency"], "count": 1},
        }
    )
    assert accepted["parameters"]["items"] == "vpp,frequency"

    accepted_tuple = validate_job_request(
        {
            "command": "measure-log",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"items": ("vpp", "frequency"), "count": 1},
        }
    )
    assert accepted_tuple["parameters"]["items"] == "vpp,frequency"


@pytest.mark.parametrize(
    ("command", "timeout_name", "parameters"),
    (
        (
            "measure-until",
            "timeout_seconds",
            {"channel": 1, "item": "vpp", "operator": "gt", "threshold": 0},
        ),
        (
            "triggered-measure-loop",
            "trigger_timeout_seconds",
            {"count": 1},
        ),
        (
            "triggered-capture-series",
            "trigger_timeout_seconds",
            {"channels": "1", "count": 1},
        ),
    ),
)
def test_workflow_timeout_zero_is_rejected_before_queueing_in_every_mode(
    monkeypatch,
    command: str,
    timeout_name: str,
    parameters: dict[str, object],
) -> None:
    client = TestClient(app)
    monkeypatch.setattr(
        app_module.job_manager,
        "submit",
        lambda _request: pytest.fail("invalid Workflow timeout was queued"),
    )

    for mode in ("live", "simulate", "dry-run"):
        payload = {
            "command": command,
            "mode": mode,
            "parameters": {**parameters, timeout_name: 0},
        }
        if mode == "live":
            payload["resource"] = "USB::TEST::INSTR"
        else:
            payload["model_id"] = MODEL_ID

        response = client.post("/api/jobs", json=payload)
        assert response.status_code == 400
        assert response.json()["detail"] == f"{timeout_name} must be greater than 0"

        accepted = validate_job_request(
            {**payload, "parameters": {**parameters, timeout_name: 1e-12}}
        )
        assert accepted["parameters"][timeout_name] == 1e-12


def test_representative_trigger_search_serial_segmented_and_workflow_simulated_commands_complete(tmp_path) -> None:
    client = TestClient(app)
    for command, parameters in (
        ("trigger-edge", {"action": "set", "source_channel": 1, "level": 0.1, "slope": "positive"}),
        ("search-mode", {"action": "set", "mode": "edge"}),
        ("serial-mode", {"action": "set", "bus": 1, "mode": "uart"}),
        ("serial-uart", {"action": "set", "bus": 1, "baud_rate": 9600, "data_bits": 8, "parity": "none"}),
        ("segmented-memory", {"action": "enable", "segments": 2}),
        ("capture-batch", {"channels": "1", "points": 1000, "format": "byte", "count": 1, "interval_seconds": 0}),
    ):
        job = submit(
            client,
            command,
            "simulate",
            parameters,
            pc_output_dir=(tmp_path / "batch-output") if command == "capture-batch" else None,
        )
        assert job["status"] == "completed", (command, job)


def test_trigger_search_serial_segmented_and_workflow_dry_run_planners_and_conditional_validation() -> None:
    client = TestClient(app)
    job = submit(
        client,
        "measure-until",
        "dry-run",
        {"channel": 1, "item": "vpp", "operator": "gt", "threshold": 0.1, "timeout_seconds": 1, "interval_seconds": 0},
    )
    assert job["status"] == "completed"
    assert job["result"]["result"]["status"] == "planned"

    no_save = submit(
        client,
        "measure-until",
        "simulate",
        {
            "channel": 1,
            "item": "vpp",
            "operator": "gt",
            "threshold": 0,
            "timeout_seconds": 1,
            "interval_seconds": 0,
            "save_results": False,
        },
    )
    assert no_save["status"] == "completed"
    assert no_save["artifacts"] == []
    assert no_save["result"]["result"]["last_measurement"]["index"] == 1

    rejected = client.post(
        "/api/jobs",
        json={
            "command": "trigger-pulse-width",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"action": "query", "time_seconds": 1},
        },
    )
    assert rejected.status_code == 400
    assert "query" in rejected.json()["detail"].lower()


def test_serial_lister_export_registers_only_its_host_artifact(tmp_path) -> None:
    client = TestClient(app)
    job = submit(
        client,
        "serial-lister-export",
        "simulate",
        {"filename": "lister.csv"},
        pc_output_dir=tmp_path / "lister-output",
    )
    assert job["status"] == "completed"
    assert [artifact["name"] for artifact in job["artifacts"]] == ["lister.csv"]
    artifact = client.get(job["artifacts"][0]["url"])
    assert artifact.status_code == 200
    assert artifact.content


def test_channel_display_and_scale_query_and_set_validation_semantics() -> None:
    accepted_display_query = validate_job_request(
        {
            "command": "channel-display",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"channel": 1, "action": "query", "enabled": True},
        }
    )
    assert accepted_display_query["parameters"]["channel"] == 1

    accepted_scale_query = validate_job_request(
        {
            "command": "channel-scale",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"channel": 1, "action": "query", "volts_per_division": 1.0},
        }
    )
    assert accepted_scale_query["parameters"]["channel"] == 1

    client = TestClient(app)
    missing_enabled = client.post(
        "/api/jobs",
        json={
            "command": "channel-display",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"channel": 1, "action": "set"},
        },
    )
    assert missing_enabled.status_code == 400
    assert (
        missing_enabled.json()["detail"]
        == "enabled must be a boolean for channel-display set"
    )

    non_bool_enabled = client.post(
        "/api/jobs",
        json={
            "command": "channel-display",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"channel": 1, "action": "set", "enabled": "true"},
        },
    )
    assert non_bool_enabled.status_code == 400
    assert (
        non_bool_enabled.json()["detail"]
        == "enabled must be a boolean for channel-display set"
    )


def test_check_error_catalog_exposes_max_reads_field() -> None:
    command = next(
        entry for entry in TestClient(app).get("/api/commands").json()
        if entry["id"] == "check-error"
    )
    field = next(
        field for field in command["fields"]
        if field["name"] == "max_reads"
    )

    assert field["type"] == "integer"
    assert field["minimum"] == 1
    assert field["default"] == 20


def test_check_error_execution_passes_max_reads_and_preserves_entries(tmp_path: Path) -> None:
    from scopes_tool_core.status import SystemErrorEntry

    class FakeScope:
        capabilities = object()

        def __init__(self) -> None:
            self.called: dict[str, int] = {}

        def drain_system_errors(self, max_reads: int = 20):  # type: ignore[no-untyped-def]
            self.called["max_reads"] = max_reads
            return (
                SystemErrorEntry(-113, "Undefined header", '-113,"Undefined header"'),
                SystemErrorEntry(-221, "Settings conflict", '-221,"Settings conflict"'),
                SystemErrorEntry(0, "No error", '0,"No error"'),
            )

    scope = FakeScope()

    result = command_execution_module._execute_scope_command(
        scope,
        "check-error",
        "USB0::TEST::INSTR",
        {"max_reads": 5},
        tmp_path,
    )

    assert scope.called["max_reads"] == 5
    assert result["result"]["drain"] is True
    assert result["result"]["max_reads"] == 5
    assert [entry["code"] for entry in result["result"]["entries"]] == [-113, -221, 0]
    assert result["result"]["system_error"] == result["result"]["entries"][-1]
    assert result["exit_code"] == 1


def test_capture_multi_channel_catalog_contract() -> None:
    capture = next(
        entry for entry in TestClient(app).get("/api/commands").json()
        if entry["id"] == "capture"
    )
    field = next(entry for entry in capture["fields"] if entry["name"] == "channels")
    assert field["type"] == "multi-enum"
    assert field["options"] == [1, 2, 3, 4]
    assert field["default"] == [1]
    assert field["serialize"] == "csv"
    assert field["required"] is True
    assert field["option_label"] == "channel"
    assert field["label_key"] == "capture.channels"
    assert field["help_key"] == "capture.channels"


def test_capture_multi_channel_simulate_and_dry_run(tmp_path) -> None:
    client = TestClient(app)
    simulate = submit(
        client,
        "capture",
        "simulate",
        {"channels": "1,2", "points": 1000, "format": "byte"},
        pc_output_dir=tmp_path / "capture-multi",
    )
    assert simulate["status"] == "completed"
    assert simulate["result"]["result"]["channels"] == [1, 2]
    assert any(artifact["kind"] == "csv" for artifact in simulate["artifacts"])
    assert any(artifact["kind"] == "metadata" for artifact in simulate["artifacts"])

    dry_run = submit(client, "capture", "dry-run", {"channels": "1,2", "points": 1000, "format": "byte"})
    assert dry_run["status"] == "completed"
    assert dry_run["result"]["result"]["channels"] == [1, 2]


@pytest.mark.parametrize("channels", ["", "   ", []])
def test_live_capture_rejects_empty_required_channels_before_queue(channels) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/jobs",
        json={
            "command": "capture",
            "mode": "live",
            "resource": "USB::TEST::INSTR",
            "parameters": {"channels": channels, "points": 1000, "format": "byte"},
        },
    )
    assert response.status_code == 400
    assert "channels is required" in response.json()["detail"]


def test_system_information_snapshot_returns_idn_and_acquisition_readouts() -> None:
    """Snapshot combines existing identify and acquisition readouts in one session."""
    client = TestClient(app)
    response = client.post(
        "/api/jobs",
        json={
            "command": "system-information-snapshot",
            "mode": "simulate",
            "parameters": {},
        },
    )
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert job["status"] in ("completed", "running", "queued")
    # When completed, result must contain both idn and acquisition keys.
    if job.get("status") == "completed":
        result = job.get("result", {}).get("result", {})
        assert "idn" in result
        assert "acquisition" in result
        acq = result.get("acquisition", {})
        assert "sample_rate" in acq or acq.get("sample_rate") is None
        assert "acquisition_points" in acq or acq.get("acquisition_points") is None
        assert "record_length" in acq or acq.get("record_length") is None


def test_identify_hidden_from_catalog_but_backend_preserved() -> None:
    """Identify is hidden from browser presentation; backend execution remains."""
    client = TestClient(app)
    catalog_response = client.get("/api/commands")
    command_ids = {entry["id"] for entry in catalog_response.json()}
    assert "identify" not in command_ids
    # Backend execution of identify must still work through direct API call.
    response = client.post(
        "/api/jobs",
        json={
            "command": "identify",
            "mode": "simulate",
            "parameters": {},
        },
    )
    assert response.status_code == 202
