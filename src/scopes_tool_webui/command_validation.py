"""WebUI request admission, parameter validation, and normalization."""

from __future__ import annotations

from typing import Any, Mapping

from scopes_tool_core import capabilities_for_model_id, normalize_sequence_document
from scopes_tool_core.capabilities import operation_supported
from scopes_tool_core.identity import physical_model_for_id
from scopes_tool_core.trigger import TriggerWaitConfig, validate_trigger_wait_config

from ._validation_shared import (
    WebUIRequestError,
    _finite_number,
    _integer,
    _require_boolean,
)
from ._validation_advanced import (
    _segmented_capture_request,
    _validate_measure_sweep_parameters,
    _validate_trigger_search_serial_segmented_workflow_parameters,
)
from ._validation_analysis import _validate_analysis_parameters
from ._validation_controls import _validate_control_parameters

from .command_catalog import (
    _COMMAND_BY_ID,
    _COMMAND_FIELDS,
    _TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMAND_IDS,
)


DEFAULT_MODEL_ID = "keysight-dsox4024a"
DEFAULT_PC_OUTPUT_DIR = "data"


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
    pc_output_dir = payload.get("pc_output_dir", DEFAULT_PC_OUTPUT_DIR)
    output_optional = (
        command in {
            "measure-log",
            "measure-until",
            "triggered-measure-loop",
            "capture-monitor",
            "sequence",
        }
        and parameters.get("save_results") is False
    )
    if not isinstance(pc_output_dir, str) or (not pc_output_dir.strip() and not output_optional):
        raise WebUIRequestError("pc_output_dir must be a non-empty string")
    model_id = None if mode == "live" else payload.get("model_id", DEFAULT_MODEL_ID)
    if mode != "live":
        if not isinstance(model_id, str) or not model_id.strip():
            raise WebUIRequestError("model_id must be a non-empty registered model ID")
        try:
            physical_model_for_id(model_id)
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
    if mode == "live" and command != "list-resources" and resource is None:
        raise WebUIRequestError("live execution requires an explicit VISA resource")

    normalized = dict(parameters)
    if command == "smoke":
        normalized.setdefault("save_artifacts", False)
    if command == "single-wait":
        _single_wait_config(normalized)
    if command in {
        "annotation-query",
        "annotation-set",
        "annotation-on",
        "annotation-off",
        "annotation-clear",
    }:
        normalized.setdefault("slot", 1)
    _validate_exclusive_minimum_fields(command, normalized)
    if mode == "live" and command != "list-resources":
        _validate_parameter_shapes(command, normalized, mode)
    else:
        _validate_parameters(command, normalized, mode, model_id)
    return {
        "command": command,
        "mode": mode,
        "resource": resource.strip() if isinstance(resource, str) else None,
        "model_id": model_id,
        "pc_output_dir": pc_output_dir.strip() or DEFAULT_PC_OUTPUT_DIR,
        "parameters": normalized,
    }


def _validate_parameter_shapes(
    command: str,
    parameters: Mapping[str, Any],
    mode: str,
) -> None:
    if command == "sequence":
        try:
            normalize_sequence_document(parameters.get("document"))
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        if "save_results" in parameters:
            _require_boolean(parameters["save_results"], "save_results")
        return
    fields = {field["name"]: field for field in _COMMAND_BY_ID[command]["fields"]}
    for name, field in fields.items():
        if name not in parameters:
            if field.get("required") is True:
                raise WebUIRequestError(f"{name} is required")
            continue
        value = parameters[name]
        field_type = field["type"]
        if field_type == "integer":
            parsed = _integer(value, name)
            options = field.get("mode_options", {}).get(mode, field.get("options"))
            if options is not None and parsed not in options:
                raise WebUIRequestError(f"{name} must be one of: {', '.join(map(str, options))}")
        elif field_type == "number":
            parsed = _finite_number(value, name)
        elif field_type == "boolean":
            _require_boolean(value, name)
            continue
        elif field_type == "string":
            if name == "pairs":
                if isinstance(value, str):
                    continue
                if isinstance(value, (list, tuple)) and all(
                    isinstance(item, str) for item in value
                ):
                    continue
                raise WebUIRequestError(
                    "pairs must be a comma-separated string or list of strings"
                )
            if not isinstance(value, str):
                raise WebUIRequestError(f"{name} must be a string")
            continue
        elif field_type == "enum":
            options = field.get("mode_options", {}).get(mode, field.get("options", ()))
            if value not in options:
                raise WebUIRequestError(f"{name} must be one of: {', '.join(map(str, options))}")
            continue
        elif field_type == "multi-enum":
            if isinstance(value, str):
                if field.get("required") is True and not value.strip():
                    raise WebUIRequestError(f"{name} is required")
                continue

            if isinstance(value, (list, tuple)):
                if field.get("required") is True and not any(
                    str(item).strip() for item in value
                ):
                    raise WebUIRequestError(f"{name} is required")
                if all(
                    isinstance(item, (str, int, float)) and not isinstance(item, bool)
                    for item in value
                ):
                    continue

            raise WebUIRequestError(f"{name} must be a comma-separated string or list")
        else:
            continue
        if "minimum" in field and parsed < field["minimum"]:
            raise WebUIRequestError(f"{name} must be at least {field['minimum']}")
        if "maximum" in field and parsed > field["maximum"]:
            raise WebUIRequestError(f"{name} must be at most {field['maximum']}")


def _validate_exclusive_minimum_fields(
    command: str,
    parameters: Mapping[str, Any],
) -> None:
    fields = {field["name"]: field for field in _COMMAND_BY_ID[command]["fields"]}
    for name, value in parameters.items():
        exclusive_minimum = fields[name].get("exclusive_minimum")
        if exclusive_minimum is None:
            continue
        if _finite_number(value, name) <= exclusive_minimum:
            raise WebUIRequestError(
                f"{name} must be greater than {exclusive_minimum}"
            )


def _validate_parameters(
    command: str,
    parameters: dict[str, Any],
    mode: str,
    model_id: str | None,
) -> None:
    if model_id is not None and not operation_supported(
        capabilities_for_model_id(model_id), command
    ):
        raise WebUIRequestError(f"{command} is unsupported for {model_id}")
    if command == "sequence":
        try:
            parameters["document"] = normalize_sequence_document(
                parameters.get("document")
            ).to_json()
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        _require_boolean(parameters.setdefault("save_results", True), "save_results")
        return
    if command == "list-resources":
        parameters.setdefault("live_only", False)
        _require_boolean(parameters["live_only"], "live_only")
        return
    if command == "doctor":
        return
    if command == "smoke":
        _require_boolean(parameters.setdefault("save_artifacts", False), "save_artifacts")
        return
    if model_id is None:
        raise WebUIRequestError("detected model identity is required for live validation")
    capabilities = capabilities_for_model_id(model_id)
    if command == "single-wait":
        _single_wait_config(parameters)
        return
    if command == "measure-sweep":
        _validate_measure_sweep_parameters(parameters, capabilities)
        return
    if command in _TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMAND_IDS:
        _validate_trigger_search_serial_segmented_workflow_parameters(command, parameters, mode, model_id)
        return
    if _validate_control_parameters(command, parameters, capabilities, mode):
        return
    if _validate_analysis_parameters(command, parameters, capabilities):
        return



def _single_wait_config(parameters: dict[str, Any]) -> TriggerWaitConfig:
    try:
        timeout_seconds = _finite_number(
            parameters.setdefault("trigger_timeout_seconds", 5.0),
            "trigger_timeout_seconds",
        )
        if timeout_seconds <= 0:
            raise WebUIRequestError("trigger_timeout_seconds must be greater than 0")
        poll_interval_ms = _integer(
            parameters.setdefault("trigger_poll_interval_ms", 100),
            "trigger_poll_interval_ms",
        )
        force_on_timeout = parameters.setdefault("force_trigger_on_timeout", False)
        _require_boolean(force_on_timeout, "force_trigger_on_timeout")
        parameters["trigger_timeout_seconds"] = timeout_seconds
        parameters["trigger_poll_interval_ms"] = poll_interval_ms
        config = TriggerWaitConfig(
            timeout_ms=max(1, int(round(timeout_seconds * 1000.0))),
            poll_interval_ms=poll_interval_ms,
            force_on_timeout=force_on_timeout,
        )
        return validate_trigger_wait_config(config)
    except WebUIRequestError:
        raise
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc
