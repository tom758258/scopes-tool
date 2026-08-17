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
from scopes_tool_core.channel import (
    normalize_channel_coupling,
    normalize_channel_impedance,
    normalize_channel_units,
    validate_analog_channel,
    validate_channel_impedance_supported,
    validate_channel_label,
    validate_channel_offset,
    validate_channel_range,
    validate_channel_scale,
    validate_probe_ratio,
    validate_probe_skew,
)
from scopes_tool_core.display import validate_display_intensity, validate_display_persistence
from scopes_tool_core.dvm import DVM_MODES, normalize_dvm_mode
from scopes_tool_core.fft import normalize_fft_units, normalize_fft_window
from scopes_tool_core.identity import PHYSICAL_MODEL_REGISTRY, physical_model_for_id
from scopes_tool_core.math import (
    MATH_COMPOSITE_OPERATIONS,
    MATH_OPERATIONS,
    MATH_SOURCES,
    normalize_math_composite_operation,
    normalize_math_operation,
    normalize_math_source,
    validate_finite_number,
    validate_positive,
)
from scopes_tool_core.measurements import (
    MEASUREMENT_WINDOW_CHOICES,
    SUPPORTED_MEASUREMENT_ITEMS,
    normalize_measurement_item,
    normalize_measurement_window,
)
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
            {
                "name": "action",
                "type": "enum",
                "options": ("query", "set"),
                "mode_options": {
                    "live": ("query", "set"),
                    "simulate": ("query", "set"),
                    "dry-run": ("query",),
                },
                "default": "query",
            },
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
        "id": "channel-summary",
        "category": "Channel",
        "label": "Channel summary",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "channel-label",
        "category": "Channel",
        "label": "Channel label",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "text", "type": "string"},
        ),
    },
    {
        "id": "channel-offset",
        "category": "Channel",
        "label": "Channel offset",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "volts", "type": "number"},
        ),
    },
    {
        "id": "channel-coupling",
        "category": "Channel",
        "label": "Channel coupling",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "coupling", "type": "enum", "options": ("ac", "dc")},
        ),
    },
    {
        "id": "channel-probe",
        "category": "Channel",
        "label": "Channel probe ratio",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "ratio", "type": "number", "minimum": 0},
        ),
    },
    {
        "id": "channel-bandwidth-limit",
        "category": "Channel",
        "label": "Channel bandwidth limit",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "channel-impedance",
        "category": "Channel",
        "label": "Channel impedance",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "impedance", "type": "enum", "options": ("one_meg", "fifty")},
        ),
    },
    {
        "id": "channel-invert",
        "category": "Channel",
        "label": "Channel invert",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "channel-range",
        "category": "Channel",
        "label": "Channel range",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "volts", "type": "number", "minimum": 0},
        ),
    },
    {
        "id": "channel-units",
        "category": "Channel",
        "label": "Channel units",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "units", "type": "enum", "options": ("volt", "amp")},
        ),
    },
    {
        "id": "channel-vernier",
        "category": "Channel",
        "label": "Channel vernier",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "channel-probe-skew",
        "category": "Channel",
        "label": "Channel probe skew",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "seconds", "type": "number"},
        ),
    },
    {
        "id": "display-label",
        "category": "Display",
        "label": "Display label",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "display-clear",
        "category": "Display",
        "label": "Clear display",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "display-persistence",
        "category": "Display",
        "label": "Display persistence",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "value", "type": "string"},
        ),
    },
    {
        "id": "display-intensity",
        "category": "Display",
        "label": "Display intensity",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "value", "type": "integer", "minimum": 0, "maximum": 100},
        ),
    },
    {
        "id": "display-vectors",
        "category": "Display",
        "label": "Display vectors",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
        ),
    },
    {
        "id": "measure",
        "category": "Measurement",
        "label": "Measure",
        "modes": ("live", "simulate", "dry-run"),
        "fields": (
            {"name": "item", "type": "enum", "options": SUPPORTED_MEASUREMENT_ITEMS, "default": "vpp"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "reference_channel", "type": "integer", "minimum": 1, "maximum": 4},
            {"name": "time_s", "type": "number"},
            {"name": "level", "type": "number"},
            {"name": "slope", "type": "enum", "options": ("positive", "negative")},
            {"name": "occurrence", "type": "integer", "minimum": 1},
        ),
    },
    {
        "id": "measure-results",
        "category": "Measurement",
        "label": "Measurement results",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "measure-clear",
        "category": "Measurement",
        "label": "Clear measurements",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "measure-show",
        "category": "Measurement",
        "label": "Measurement display",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
        ),
    },
    {
        "id": "measure-source",
        "category": "Measurement",
        "label": "Measurement source",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "source_channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "source2_channel", "type": "integer", "minimum": 1, "maximum": 4},
        ),
    },
    {
        "id": "measure-window",
        "category": "Measurement",
        "label": "Measurement window",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "window", "type": "enum", "options": MEASUREMENT_WINDOW_CHOICES},
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
    {
        "id": "system-clear-status",
        "category": "System",
        "label": "Clear status",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "system-opc",
        "category": "System",
        "label": "Operation complete",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "system-standard-event",
        "category": "System",
        "label": "Standard event status",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "system-options",
        "category": "System",
        "label": "System options",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "dvm-enable",
        "category": "DVM",
        "label": "DVM enable",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "dvm-source",
        "category": "DVM",
        "label": "DVM source",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
        ),
    },
    {
        "id": "dvm-mode",
        "category": "DVM",
        "label": "DVM mode",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "mode", "type": "enum", "options": DVM_MODES},
        ),
    },
    {
        "id": "dvm-auto-range",
        "category": "DVM",
        "label": "DVM auto range",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "dvm-current",
        "category": "DVM",
        "label": "DVM current reading",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "dvm-query",
        "category": "DVM",
        "label": "DVM state",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "fft",
        "category": "FFT / MATH",
        "label": "FFT",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "function", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "source_channel", "type": "integer", "minimum": 1, "maximum": 4},
            {"name": "units", "type": "string"},
            {"name": "window", "type": "string"},
            {"name": "center_hz", "type": "number", "minimum": 0},
            {"name": "span_hz", "type": "number", "minimum": 0},
            {"name": "display", "type": "boolean"},
        ),
    },
    {
        "id": "math-display",
        "category": "FFT / MATH",
        "label": "Math display",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "function", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "math-vertical",
        "category": "FFT / MATH",
        "label": "Math vertical",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "function", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "scale", "type": "number", "minimum": 0},
            {"name": "range_value", "type": "number", "minimum": 0},
            {"name": "offset", "type": "number"},
        ),
    },
    {
        "id": "math-operator",
        "category": "FFT / MATH",
        "label": "Math operator",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "function", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "operation", "type": "enum", "options": MATH_OPERATIONS},
            {"name": "source1", "type": "enum", "options": MATH_SOURCES},
            {"name": "source2", "type": "enum", "options": MATH_SOURCES},
        ),
    },
    {
        "id": "math-composite-source",
        "category": "FFT / MATH",
        "label": "Math composite source",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "operation", "type": "enum", "options": MATH_COMPOSITE_OPERATIONS},
            {"name": "source1", "type": "enum", "options": MATH_SOURCES},
            {"name": "source2", "type": "enum", "options": MATH_SOURCES},
        ),
    },
    {
        "id": "math-clear",
        "category": "FFT / MATH",
        "label": "Clear math",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "function", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
        ),
    },
)

_COMMAND_BY_ID = {entry["id"]: entry for entry in COMMANDS}
_COMMAND_FIELDS = {
    command_id: frozenset(field["name"] for field in entry["fields"])
    for command_id, entry in _COMMAND_BY_ID.items()
}


class WebUIRequestError(ValueError):
    """Raised when a WebUI command request is invalid before queueing."""


class ScopeSessionCloseError(RuntimeError):
    """Raised when a job-owned scope session cannot be closed."""


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
        try:
            scope.close()
        except Exception as exc:
            raise ScopeSessionCloseError(f"scope session close failed: {exc}") from exc


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
    if scope.capabilities is None:
        scope.query_idn()
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
    if command == "channel-summary":
        return _state_scope_result("channels", scope.query_channel_summary())
    if command == "channel-label":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_label,
            getter=scope.query_channel_label,
            value_name="text",
            result_name="text",
        )
    if command == "channel-offset":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_offset,
            getter=scope.query_channel_offset,
            value_name="volts",
            result_name="volts",
        )
    if command == "channel-coupling":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_coupling,
            getter=scope.query_channel_coupling,
            value_name="coupling",
            result_name="coupling",
        )
    if command == "channel-probe":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_probe_ratio,
            getter=scope.query_channel_probe_ratio,
            value_name="ratio",
            result_name="ratio",
        )
    if command == "channel-bandwidth-limit":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_bandwidth_limit,
            getter=scope.query_channel_bandwidth_limit,
            value_name="enabled",
            result_name="enabled",
        )
    if command == "channel-impedance":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_impedance,
            getter=scope.query_channel_impedance,
            value_name="impedance",
            result_name="impedance",
        )
    if command == "channel-invert":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_invert,
            getter=scope.query_channel_invert,
            value_name="enabled",
            result_name="enabled",
        )
    if command == "channel-range":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_range,
            getter=scope.query_channel_range,
            value_name="volts",
            result_name="volts",
        )
    if command == "channel-units":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_units,
            getter=scope.query_channel_units,
            value_name="units",
            result_name="units",
        )
    if command == "channel-vernier":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_vernier,
            getter=scope.query_channel_vernier,
            value_name="enabled",
            result_name="enabled",
        )
    if command == "channel-probe-skew":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_probe_skew,
            getter=scope.query_channel_probe_skew,
            value_name="seconds",
            result_name="seconds",
        )
    if command == "display-label":
        return _execute_display_setting(parameters, scope.set_display_label, scope.query_display_label, "enabled")
    if command == "display-clear":
        scope.clear_display()
        return _simple_scope_result("display-clear")
    if command == "display-persistence":
        if parameters["action"] == "set":
            scope.set_display_persistence(parameters["value"])
        return _state_scope_result("persistence", scope.query_display_persistence())
    if command == "display-intensity":
        if parameters["action"] == "set":
            scope.set_display_intensity(parameters["value"])
        intensity, raw = scope.query_display_intensity()
        return _state_scope_result("intensity", {"value": intensity, "raw": raw})
    if command == "display-vectors":
        if parameters["action"] == "set":
            scope.set_display_vectors_on()
        enabled, raw = scope.query_display_vectors()
        return _state_scope_result("vectors", {"enabled": enabled, "raw": raw})
    if command == "measure":
        result = run_measure(scope, resource, _measure_request(parameters))
        return _operation_payload(result)
    if command == "measure-results":
        return _state_scope_result("measurements", scope.query_measurement_results())
    if command == "measure-clear":
        scope.clear_measurements()
        return _simple_scope_result("measure-clear")
    if command == "measure-show":
        if parameters["action"] == "set":
            scope.configure_measurement_show()
        return _state_scope_result("show", scope.query_measurement_show())
    if command == "measure-source":
        if parameters["action"] == "set":
            scope.configure_measurement_source(
                parameters["source_channel"], parameters.get("source2_channel")
            )
        return _state_scope_result("source", scope.query_measurement_source())
    if command == "measure-window":
        if parameters["action"] == "set":
            scope.configure_measurement_window(parameters["window"])
        return _state_scope_result("window", scope.query_measurement_window())
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
    if command == "system-clear-status":
        scope.clear_status()
        return _simple_scope_result("system-clear-status")
    if command == "system-opc":
        return _state_scope_result("operation_complete", scope.query_operation_complete())
    if command == "system-standard-event":
        return {"exit_code": 0, "result": scope.query_standard_event_status().to_json(), "artifacts": []}
    if command == "system-options":
        return {"exit_code": 0, "result": scope.query_system_options().to_json(), "artifacts": []}
    if command == "dvm-enable":
        return _execute_state_setting(parameters, scope.configure_dvm_enable, scope.query_dvm_enable)
    if command == "dvm-source":
        return _execute_state_setting(parameters, scope.configure_dvm_source, scope.query_dvm_source, "channel")
    if command == "dvm-mode":
        return _execute_state_setting(parameters, scope.configure_dvm_mode, scope.query_dvm_mode, "mode")
    if command == "dvm-auto-range":
        return _execute_state_setting(parameters, scope.configure_dvm_auto_range, scope.query_dvm_auto_range)
    if command == "dvm-current":
        return _state_scope_result("reading", scope.query_dvm_current())
    if command == "dvm-query":
        return _state_scope_result("dvm", scope.query_dvm())
    if command == "fft":
        return _execute_fft(scope, parameters)
    if command == "math-display":
        return _execute_math_display(scope, parameters)
    if command == "math-vertical":
        return _execute_math_vertical(scope, parameters)
    if command == "math-operator":
        return _execute_math_operator(scope, parameters)
    if command == "math-composite-source":
        return _execute_math_composite_source(scope, parameters)
    if command == "math-clear":
        scope.clear_math(parameters["function"])
        return _simple_scope_result("math-clear")
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


def _execute_channel_setting(
    scope: Any,
    parameters: Mapping[str, Any],
    *,
    setter: Any,
    getter: Any,
    value_name: str,
    result_name: str,
) -> dict[str, Any]:
    channel = parameters["channel"]
    if parameters["action"] == "set":
        setter(channel, parameters[value_name])
    return {
        "exit_code": 0,
        "result": {
            "channel": channel,
            result_name: _jsonable(getter(channel)),
        },
        "artifacts": [],
    }


def _execute_display_setting(
    parameters: Mapping[str, Any],
    setter: Any,
    getter: Any,
    value_name: str,
) -> dict[str, Any]:
    if parameters["action"] == "set":
        setter(parameters[value_name])
    return _state_scope_result("state", getter())


def _execute_state_setting(
    parameters: Mapping[str, Any],
    setter: Any,
    getter: Any,
    value_name: str = "enabled",
) -> dict[str, Any]:
    if parameters["action"] == "set":
        setter(parameters[value_name])
    return _state_scope_result("state", getter())


def _execute_fft(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_fft(
            function,
            parameters["source_channel"],
            units=parameters.get("units"),
            window=parameters.get("window"),
            center_hz=parameters.get("center_hz"),
            span_hz=parameters.get("span_hz"),
            display=parameters.get("display"),
        )
    return _state_scope_result("fft", scope.query_fft(function))


def _execute_math_display(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_display(function, parameters["enabled"])
    return _state_scope_result("math_display", scope.query_math_display(function))


def _execute_math_vertical(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_vertical(
            function,
            scale=parameters.get("scale"),
            range_value=parameters.get("range_value"),
            offset=parameters.get("offset"),
        )
    return _state_scope_result("math_vertical", scope.query_math_vertical(function))


def _execute_math_operator(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_operator(
            function,
            parameters["operation"],
            parameters["source1"],
            parameters["source2"],
        )
    return _state_scope_result("math_operator", scope.query_math_operator(function))


def _execute_math_composite_source(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    if parameters["action"] == "set":
        scope.configure_math_composite_source(
            parameters["operation"],
            parameters["source1"],
            parameters["source2"],
        )
    return _state_scope_result("math_composite_source", scope.query_math_composite_source())


def _state_scope_result(name: str, value: Any) -> dict[str, Any]:
    return {"exit_code": 0, "result": {name: _jsonable(value)}, "artifacts": []}


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
    elif command in {
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
    }:
        action = _action(parameters, command)
        channel = _integer(parameters.get("channel", 1), "channel")
        parameters["channel"] = validate_analog_channel(channel, capabilities)
        value_name = {
            "channel-label": "text",
            "channel-offset": "volts",
            "channel-coupling": "coupling",
            "channel-probe": "ratio",
            "channel-bandwidth-limit": "enabled",
            "channel-impedance": "impedance",
            "channel-invert": "enabled",
            "channel-range": "volts",
            "channel-units": "units",
            "channel-vernier": "enabled",
            "channel-probe-skew": "seconds",
        }[command]
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if command == "channel-label":
                    parameters[value_name] = validate_channel_label(parameters[value_name], capabilities)
                elif command == "channel-offset":
                    parameters[value_name] = validate_channel_offset(
                        _finite_number(parameters[value_name], value_name)
                    )
                elif command == "channel-coupling":
                    parameters[value_name] = normalize_channel_coupling(parameters[value_name])
                elif command == "channel-probe":
                    parameters[value_name] = validate_probe_ratio(
                        _finite_number(parameters[value_name], value_name)
                    )
                elif command in {"channel-bandwidth-limit", "channel-invert", "channel-vernier"}:
                    _require_boolean(parameters[value_name], value_name)
                elif command == "channel-impedance":
                    parameters[value_name] = normalize_channel_impedance(parameters[value_name])
                    validate_channel_impedance_supported(parameters[value_name], capabilities)
                elif command == "channel-range":
                    parameters[value_name] = validate_channel_range(
                        _finite_number(parameters[value_name], value_name)
                    )
                elif command == "channel-units":
                    parameters[value_name] = normalize_channel_units(parameters[value_name])
                elif command == "channel-probe-skew":
                    parameters[value_name] = validate_probe_skew(
                        _finite_number(parameters[value_name], value_name)
                    )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command in {"display-label", "display-persistence", "display-intensity", "display-vectors"}:
        action = _action(parameters, command)
        value_name = {
            "display-label": "enabled",
            "display-persistence": "value",
            "display-intensity": "value",
        }.get(command)
        if action == "set":
            if value_name is not None:
                _require_parameter(parameters, value_name, command)
            try:
                if command == "display-label":
                    _require_boolean(parameters[value_name], value_name)
                elif command == "display-persistence":
                    mode, seconds = validate_display_persistence(parameters[value_name])
                    parameters[value_name] = mode if mode is not None else seconds
                elif command == "display-intensity":
                    parameters[value_name] = validate_display_intensity(
                        _integer(parameters[value_name], value_name)
                    )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,) if value_name else (), command)
    elif command in {"measure-show", "measure-source", "measure-window"}:
        action = _action(parameters, command)
        if command == "measure-show":
            if action == "set":
                pass
            else:
                _reject_query_parameters(parameters, (), command)
        elif command == "measure-source":
            if action == "set":
                _require_parameter(parameters, "source_channel", command)
                parameters["source_channel"] = validate_analog_channel(
                    _integer(parameters["source_channel"], "source_channel"), capabilities
                )
                if "source2_channel" in parameters:
                    parameters["source2_channel"] = validate_analog_channel(
                        _integer(parameters["source2_channel"], "source2_channel"), capabilities
                    )
            else:
                _reject_query_parameters(parameters, ("source_channel", "source2_channel"), command)
        else:
            if action == "set":
                _require_parameter(parameters, "window", command)
                try:
                    parameters["window"] = normalize_measurement_window(parameters["window"])
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, ("window",), command)
    elif command in {"dvm-enable", "dvm-source", "dvm-mode", "dvm-auto-range"}:
        action = _action(parameters, command)
        value_name = {
            "dvm-enable": "enabled",
            "dvm-source": "channel",
            "dvm-mode": "mode",
            "dvm-auto-range": "enabled",
        }[command]
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if value_name == "enabled":
                    _require_boolean(parameters[value_name], value_name)
                elif command == "dvm-source":
                    parameters[value_name] = validate_analog_channel(
                        _integer(parameters[value_name], value_name), capabilities
                    )
                else:
                    normalize_dvm_mode(parameters[value_name])
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command == "fft":
        action = _action(parameters, command)
        parameters["function"] = _integer(parameters.get("function", 1), "function")
        if action == "set":
            _require_parameter(parameters, "source_channel", command)
            parameters["source_channel"] = validate_analog_channel(
                _integer(parameters["source_channel"], "source_channel"), capabilities
            )
            for name in ("center_hz", "span_hz"):
                if name in parameters:
                    parameters[name] = _finite_number(parameters[name], name)
            if "center_hz" in parameters and parameters["center_hz"] < 0:
                raise WebUIRequestError("center_hz must be non-negative")
            if "span_hz" in parameters and parameters["span_hz"] <= 0:
                raise WebUIRequestError("span_hz must be greater than zero")
            if "units" in parameters:
                try:
                    normalize_fft_units(parameters["units"])
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            if "window" in parameters:
                try:
                    normalize_fft_window(parameters["window"])
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            if "display" in parameters:
                _require_boolean(parameters["display"], "display")
        else:
            _reject_query_parameters(
                parameters,
                ("source_channel", "units", "window", "center_hz", "span_hz", "display"),
                command,
            )
    elif command in {"math-display", "math-vertical", "math-operator", "math-composite-source"}:
        action = _action(parameters, command)
        if command != "math-composite-source":
            parameters["function"] = _integer(parameters.get("function", 1), "function")
        if command == "math-display":
            if action == "set":
                _require_parameter(parameters, "enabled", command)
                _require_boolean(parameters["enabled"], "enabled")
            else:
                _reject_query_parameters(parameters, ("enabled",), command)
        elif command == "math-vertical":
            names = ("scale", "range_value", "offset")
            if action == "set":
                if not any(name in parameters for name in names):
                    raise WebUIRequestError("math-vertical set requires scale, range_value, or offset")
                try:
                    for name in ("scale", "range_value"):
                        if name in parameters:
                            parameters[name] = validate_positive(
                                _finite_number(parameters[name], name), name
                            )
                    if "offset" in parameters:
                        parameters["offset"] = validate_finite_number(
                            _finite_number(parameters["offset"], "offset"), "offset"
                        )
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, names, command)
        elif command == "math-operator":
            names = ("operation", "source1", "source2")
            if action == "set":
                for name in names:
                    _require_parameter(parameters, name, command)
                try:
                    parameters["operation"] = normalize_math_operation(parameters["operation"])
                    parameters["source1"] = normalize_math_source(
                        parameters["source1"], capabilities=capabilities
                    )
                    parameters["source2"] = normalize_math_source(
                        parameters["source2"], capabilities=capabilities
                    )
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, names, command)
        else:
            names = ("operation", "source1", "source2")
            if action == "set":
                for name in names:
                    _require_parameter(parameters, name, command)
                try:
                    parameters["operation"] = normalize_math_composite_operation(parameters["operation"])
                    parameters["source1"] = normalize_math_source(
                        parameters["source1"], capabilities=capabilities
                    )
                    parameters["source2"] = normalize_math_source(
                        parameters["source2"], capabilities=capabilities
                    )
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, names, command)
    elif command == "math-clear":
        parameters["function"] = _integer(parameters.get("function", 1), "function")
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


def _action(parameters: dict[str, Any], command: str) -> str:
    action = parameters.setdefault("action", "query")
    if action not in {"query", "set"}:
        raise WebUIRequestError(f"{command} action must be query or set")
    return action


def _require_parameter(parameters: Mapping[str, Any], name: str, command: str) -> None:
    if name not in parameters:
        raise WebUIRequestError(f"{command} set requires {name}")


def _reject_query_parameters(
    parameters: Mapping[str, Any], names: tuple[str, ...], command: str
) -> None:
    for name in names:
        if name in parameters:
            raise WebUIRequestError(f"{command} query cannot include {name}")


def _require_boolean(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise WebUIRequestError(f"{name} must be a boolean")


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
