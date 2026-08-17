"""WebUI command catalog and Core-backed command execution."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import math
from pathlib import Path
from typing import Any, Mapping

from scopes_tool_core import (
    CaptureRequest,
    MeasureRequest,
    OperationResult,
    ResolvedRunConfig,
    RunModeOptions,
    capabilities_for_model_id,
    open_scope_for_run,
    plan_acquisition_check,
    plan_capture,
    plan_measure,
    run_capture,
    run_measure,
)
from scopes_tool_core.acquisition import (
    normalize_acquisition_type,
    validate_acquisition_count,
)
from scopes_tool_core.channel import validate_analog_channel, validate_channel_scale
from scopes_tool_core.identity import PHYSICAL_MODEL_REGISTRY, physical_model_for_id
from scopes_tool_core.measurements import MEASUREMENT_ITEM_CHOICES, normalize_measurement_item
from scopes_tool_core.output_files import write_screenshot_png_file
from scopes_tool_core.planning import (
    AcquisitionCheckPlanRequest,
    CapturePlanRequest,
    MeasurePlanRequest,
)
from scopes_tool_core.visa_backend import list_visa_resources


DEFAULT_MODEL_ID = "keysight-dsox4024a"
COMMANDS = (
    {
        "id": "list-resources",
        "category": "Device",
        "label": "List resources",
        "modes": ("live", "simulate", "dry-run"),
        "fields": (),
    },
    {
        "id": "identify",
        "category": "Identity",
        "label": "Identify",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "run",
        "category": "Acquisition",
        "label": "Run",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "single",
        "category": "Acquisition",
        "label": "Single",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "stop-acquisition",
        "category": "Acquisition",
        "label": "Stop",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "acquisition",
        "category": "Acquisition",
        "label": "Acquisition",
        "modes": ("live", "simulate", "dry-run"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "type", "type": "enum", "options": ("normal", "average", "high_resolution", "peak")},
            {"name": "count", "type": "integer", "minimum": 2, "maximum": 65536},
        ),
    },
    {
        "id": "channel-display",
        "category": "Channel",
        "label": "Channel display",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "channel-scale",
        "category": "Channel",
        "label": "Channel scale",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "volts_per_division", "type": "number", "minimum": 0},
        ),
    },
    {
        "id": "measure",
        "category": "Measurement",
        "label": "Measure",
        "modes": ("live", "simulate", "dry-run"),
        "fields": (
            {"name": "item", "type": "enum", "options": MEASUREMENT_ITEM_CHOICES, "default": "vpp"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "reference_channel", "type": "integer", "minimum": 1, "maximum": 4},
            {"name": "time_s", "type": "number"},
            {"name": "level", "type": "number"},
            {"name": "slope", "type": "enum", "options": ("positive", "negative")},
            {"name": "occurrence", "type": "integer", "minimum": 1},
        ),
    },
    {
        "id": "screenshot",
        "category": "Capture",
        "label": "Screenshot",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "background", "type": "enum", "options": ("black", "white"), "default": "black"},
        ),
    },
    {
        "id": "capture",
        "category": "Capture",
        "label": "Waveform capture",
        "modes": ("live", "simulate", "dry-run"),
        "fields": (
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "points", "type": "enum", "options": (1000, 5000, 10000), "default": 1000},
            {"name": "format", "type": "enum", "options": ("byte", "word"), "default": "byte"},
        ),
    },
    {
        "id": "check-error",
        "category": "System",
        "label": "System error",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "system-status-byte",
        "category": "System",
        "label": "Status byte",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "system-operation-status",
        "category": "System",
        "label": "Operation status",
        "modes": ("live", "simulate"),
        "fields": (),
    },
)

_COMMAND_BY_ID = {entry["id"]: entry for entry in COMMANDS}
_COMMAND_FIELDS = {
    command_id: frozenset(field["name"] for field in entry["fields"])
    for command_id, entry in _COMMAND_BY_ID.items()
}


class WebUIRequestError(ValueError):
    """Raised when a WebUI command request is invalid before queueing."""


def command_catalog() -> list[dict[str, Any]]:
    return [_jsonable(entry) for entry in COMMANDS]


def model_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": model.model_id,
            "label": model.display_name,
            "series": model.series,
        }
        for model in PHYSICAL_MODEL_REGISTRY
    ]


def validate_job_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise WebUIRequestError("request body must be an object")
    command = payload.get("command")
    if not isinstance(command, str) or command not in _COMMAND_BY_ID:
        raise WebUIRequestError("command is not supported by the Scopes Tool WebUI")
    mode = payload.get("mode", "live")
    if mode not in {"live", "simulate", "dry-run"}:
        raise WebUIRequestError("mode must be live, simulate, or dry-run")
    if mode not in _COMMAND_BY_ID[command]["modes"]:
        raise WebUIRequestError(f"command {command!r} is not available in {mode} mode")
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise WebUIRequestError("parameters must be an object")
    unknown = sorted(set(parameters) - _COMMAND_FIELDS[command])
    if unknown:
        raise WebUIRequestError(f"unknown parameter for {command}: {unknown[0]}")

    resource = payload.get("resource")
    if resource is not None and (not isinstance(resource, str) or not resource.strip()):
        raise WebUIRequestError("resource must be a non-empty string when provided")
    model_id = payload.get("model_id", DEFAULT_MODEL_ID)
    if not isinstance(model_id, str) or not model_id.strip():
        raise WebUIRequestError("model_id must be a non-empty registered model ID")
    try:
        physical_model_for_id(model_id)
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc
    if mode == "live" and command != "list-resources" and resource is None:
        raise WebUIRequestError("live execution requires an explicit VISA resource")

    normalized = dict(parameters)
    _validate_parameters(command, normalized, mode, model_id)
    return {
        "command": command,
        "mode": mode,
        "resource": resource.strip() if isinstance(resource, str) else None,
        "model_id": model_id,
        "parameters": normalized,
    }


def execute_command(
    command: str,
    *,
    mode: str,
    resource: str | None,
    model_id: str,
    parameters: Mapping[str, Any],
    artifact_dir: Path,
) -> dict[str, Any]:
    """Execute one validated request through the public Core APIs."""

    if command == "list-resources":
        listing = list_visa_resources()
        return {
            "exit_code": 0,
            "result": {"resources": listing.resources, "backend": listing.backend},
            "artifacts": [],
        }

    config = _run_config(mode, resource, model_id)
    if mode == "dry-run":
        return _execute_dry_run(command, parameters, model_id, artifact_dir)

    scope = open_scope_for_run(config)
    try:
        return _execute_scope_command(
            scope,
            command,
            resource or config.resource or "",
            parameters,
            artifact_dir,
        )
    finally:
        scope.close()


def _execute_dry_run(
    command: str,
    parameters: Mapping[str, Any],
    model_id: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    capabilities = capabilities_for_model_id(model_id)
    if command == "measure":
        request = _measure_request(parameters)
        plan = plan_measure(
            MeasurePlanRequest(
                item=request.item,
                channel=request.channel,
                source_channel=request.source_channel,
                reference_channel=request.reference_channel,
                time_s=request.time_s,
                level=request.level,
                slope=request.slope,
                occurrence=request.occurrence,
            ),
            capabilities,
        )
    elif command == "capture":
        csv_path = artifact_dir / "capture.csv"
        meta_path = artifact_dir / "capture_meta.json"
        plan = plan_capture(
            CapturePlanRequest(
                channels=(parameters["channel"],),
                points=parameters["points"],
                waveform_format=parameters["format"],
                csv_path=csv_path,
                meta_path=meta_path,
            ),
            capabilities,
        )
    elif command == "acquisition":
        plan = plan_acquisition_check(
            AcquisitionCheckPlanRequest(
                average_count=parameters.get("count", 16),
                check_only=True,
            )
        )
    else:
        raise WebUIRequestError(f"dry-run is not supported for {command}")
    return {
        "exit_code": 0,
        "result": {
            "status": "planned",
            "model_id": model_id,
            "planned_scpi": list(plan.planned_scpi),
            "files": [
                {"kind": file["kind"], "name": Path(file["path"]).name}
                for file in plan.files
            ],
            **{
                key: _jsonable(value)
                for key, value in plan.result.items()
                if key != "files"
            },
        },
        "artifacts": [
            {**file, "path": str(file["path"])}
            for file in plan.files
        ],
    }


def _execute_scope_command(
    scope: Any,
    command: str,
    resource: str,
    parameters: Mapping[str, Any],
    artifact_dir: Path,
) -> dict[str, Any]:
    if command == "identify":
        idn = scope.idn or scope.query_idn()
        return {"exit_code": 0, "result": {"idn": _jsonable(idn)}, "artifacts": []}
    if command == "run":
        scope.run()
        return _simple_scope_result("run")
    if command == "single":
        scope.single()
        return _simple_scope_result("single")
    if command == "stop-acquisition":
        scope.stop()
        return _simple_scope_result("stop-acquisition")
    if command == "acquisition":
        return _execute_acquisition(scope, parameters)
    if command == "channel-display":
        return _execute_channel_display(scope, parameters)
    if command == "channel-scale":
        return _execute_channel_scale(scope, parameters)
    if command == "measure":
        result = run_measure(scope, resource, _measure_request(parameters))
        return _operation_payload(result)
    if command == "capture":
        result = run_capture(
            scope,
            resource,
            CaptureRequest(
                channels=(parameters["channel"],),
                points=parameters["points"],
                waveform_format=parameters["format"],
                csv_path=artifact_dir / "capture.csv",
                meta_path=artifact_dir / "capture_meta.json",
            ),
        )
        return _operation_payload(result)
    if command == "screenshot":
        capture = scope.capture_screenshot_png(background=parameters["background"])
        path = write_screenshot_png_file(capture, artifact_dir / "screenshot.png")
        return {
            "exit_code": 0,
            "result": {
                "format": capture.format_name,
                "background": capture.background,
                "artifact": path.name,
            },
            "artifacts": [{"kind": "screenshot", "path": str(path)}],
        }
    if command == "check-error":
        entry = scope.query_system_error()
        return {
            "exit_code": 1 if entry.is_error else 0,
            "result": {"system_error": _jsonable(entry)},
            "artifacts": [],
        }
    if command == "system-status-byte":
        return {"exit_code": 0, "result": scope.query_status_byte().to_json(), "artifacts": []}
    if command == "system-operation-status":
        return {"exit_code": 0, "result": scope.query_operation_status().to_json(), "artifacts": []}
    raise WebUIRequestError(f"command is not supported by the Scopes Tool WebUI: {command}")


def _execute_acquisition(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    action = parameters["action"]
    if action == "set":
        if "type" in parameters:
            scope.set_acquisition_type(parameters["type"])
        if "count" in parameters:
            scope.set_acquisition_count(parameters["count"])
    config = scope.query_acquisition_config()
    return {
        "exit_code": 0,
        "result": {"action": action, "acquisition": _jsonable(config)},
        "artifacts": [],
    }


def _execute_channel_display(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    channel = parameters["channel"]
    if parameters["action"] == "set":
        scope.set_channel_display(channel, parameters["enabled"])
    enabled = scope.query_channel_display(channel)
    return {
        "exit_code": 0,
        "result": {"channel": channel, "enabled": enabled},
        "artifacts": [],
    }


def _execute_channel_scale(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    channel = parameters["channel"]
    if parameters["action"] == "set":
        scope.set_channel_scale(channel, parameters["volts_per_division"])
    scale = scope.query_channel_scale(channel)
    return {
        "exit_code": 0,
        "result": {"channel": channel, "volts_per_division": scale},
        "artifacts": [],
    }


def _simple_scope_result(action: str) -> dict[str, Any]:
    return {"exit_code": 0, "result": {"action": action}, "artifacts": []}


def _operation_payload(result: OperationResult) -> dict[str, Any]:
    result_payload = _jsonable(result.result)
    if isinstance(result_payload, dict) and isinstance(result_payload.get("files"), list):
        result_payload["files"] = [
            {"kind": item.get("kind"), "name": Path(item["path"]).name}
            if isinstance(item, dict) and isinstance(item.get("path"), str)
            else item
            for item in result_payload["files"]
        ]
    return {
        "exit_code": result.exit_code,
        "result": result_payload,
        "system_error": _jsonable(result.system_error),
        "diagnostics": {"human_lines": list(result.human_lines)},
        "idn": _jsonable(result.idn),
        "backend": result.backend,
        "timeout_ms": result.timeout_ms,
        "artifacts": [dict(item) for item in result.files],
    }


def _run_config(mode: str, resource: str | None, model_id: str) -> ResolvedRunConfig:
    options = RunModeOptions(
        simulate=mode == "simulate",
        dry_run=mode == "dry-run",
        planning_physical_model_id=model_id if mode != "live" else None,
    )
    resolved_resource = resource
    if mode == "simulate":
        resolved_resource = resource or f"SIM::{model_id}::INSTR"
    elif mode == "dry-run":
        resolved_resource = resource or f"DRY::{model_id}::INSTR"
    return ResolvedRunConfig(
        mode="dry_run" if mode == "dry-run" else mode,
        planning_physical_model_id=model_id if mode != "live" else None,
        expected_physical_model_id=None,
        capabilities=(capabilities_for_model_id(model_id) if mode != "live" else None),
        resource=resolved_resource,
        options=options,
    )


def _measure_request(parameters: Mapping[str, Any]) -> MeasureRequest:
    return MeasureRequest(
        item=parameters["item"],
        channel=parameters.get("channel"),
        reference_channel=parameters.get("reference_channel"),
        time_s=parameters.get("time_s"),
        level=parameters.get("level"),
        slope=parameters.get("slope"),
        occurrence=parameters.get("occurrence"),
    )


def _validate_parameters(
    command: str,
    parameters: dict[str, Any],
    mode: str,
    model_id: str,
) -> None:
    capabilities = capabilities_for_model_id(model_id)
    if command == "acquisition":
        action = parameters.setdefault("action", "query")
        if action not in {"query", "set"}:
            raise WebUIRequestError("acquisition action must be query or set")
        if action == "set" and "type" not in parameters and "count" not in parameters:
            raise WebUIRequestError("acquisition set requires type or count")
        if "type" in parameters:
            try:
                parameters["type"] = _normalize_acquisition_type(parameters["type"])
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        if "count" in parameters:
            parameters["count"] = _integer(parameters["count"], "count")
            try:
                validate_acquisition_count(parameters["count"])
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        if mode == "dry-run" and action != "query":
            raise WebUIRequestError("dry-run acquisition supports query only")
    elif command in {"channel-display", "channel-scale"}:
        action = parameters.setdefault("action", "query")
        if action not in {"query", "set"}:
            raise WebUIRequestError(f"{command} action must be query or set")
        channel = _integer(parameters.get("channel", 1), "channel")
        parameters["channel"] = validate_analog_channel(channel, capabilities)
        if action == "set":
            if command == "channel-display":
                if not isinstance(parameters.get("enabled"), bool):
                    raise WebUIRequestError("enabled must be a boolean for channel-display set")
            else:
                if "volts_per_division" not in parameters:
                    raise WebUIRequestError("channel-scale set requires volts_per_division")
                try:
                    parameters["volts_per_division"] = validate_channel_scale(
                        _finite_number(parameters["volts_per_division"], "volts_per_division")
                    )
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
    elif command == "measure":
        try:
            parameters["item"] = normalize_measurement_item(parameters.get("item", "vpp"))
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        parameters["channel"] = validate_analog_channel(
            _integer(parameters.get("channel", 1), "channel"), capabilities
        )
        if "reference_channel" in parameters:
            parameters["reference_channel"] = validate_analog_channel(
                _integer(parameters["reference_channel"], "reference_channel"), capabilities
            )
        for name in ("time_s", "level"):
            if name in parameters:
                parameters[name] = _finite_number(parameters[name], name)
        if "occurrence" in parameters:
            parameters["occurrence"] = _integer(parameters["occurrence"], "occurrence")
        if "slope" in parameters and parameters["slope"] not in {"positive", "negative"}:
            raise WebUIRequestError("slope must be positive or negative")
    elif command == "capture":
        parameters["channel"] = validate_analog_channel(
            _integer(parameters.get("channel", 1), "channel"), capabilities
        )
        parameters["points"] = _integer(parameters.get("points", 1000), "points")
        if parameters["points"] not in {1000, 5000, 10000}:
            raise WebUIRequestError("points must be one of: 1000, 5000, 10000")
        parameters["format"] = str(parameters.get("format", "byte")).lower()
        if parameters["format"] not in {"byte", "word"}:
            raise WebUIRequestError("format must be byte or word")
        if parameters["format"] == "word" and not capabilities.supports_word_format:
            raise WebUIRequestError("word waveform format is not supported by this model")
    elif command == "screenshot":
        parameters["background"] = str(parameters.get("background", "black")).lower()
        if parameters["background"] not in {"black", "white"}:
            raise WebUIRequestError("background must be black or white")


def _normalize_acquisition_type(value: Any) -> str:
    normalized = normalize_acquisition_type(value)
    return {
        "NORMal": "normal",
        "AVERage": "average",
        "HRESolution": "high_resolution",
        "PEAK": "peak",
    }[normalized]


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WebUIRequestError(f"{name} must be an integer")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WebUIRequestError(f"{name} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise WebUIRequestError(f"{name} must be finite")
    return parsed


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"byte_length": len(value)}
    return value
