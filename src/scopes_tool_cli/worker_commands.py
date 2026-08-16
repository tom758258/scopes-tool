"""Worker command contract and CLI adaptation helpers."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError
from scopes_tool_core.search import (
    validate_can_data_length,
    validate_can_id_mode,
    validate_can_search_criteria,
    validate_can_search_mode,
    validate_i2c_pattern_value,
    validate_i2c_search_mode,
    validate_pattern_hex_x,
    validate_search_qualifier,
    validate_serial_search_bus,
    validate_spi_search_mode,
    validate_spi_search_pattern_width,
    validate_spi_width,
    validate_uart_data,
    validate_uart_search_mode,
)
from scopes_tool_core.fft import (
    FFT_DETECTION_TYPES,
    FFT_GATES,
    FFT_OPERATIONS,
    FFT_PHASE_REFERENCES,
    fft_advanced_query_commands,
    fft_configure_commands,
    fft_query_commands,
)
from scopes_tool_core.math import (
    math_clear_command,
    math_composite_source_commands,
    math_composite_source_query_commands,
    math_display_command,
    math_display_query,
    math_filter_commands,
    math_filter_query_commands,
    math_operator_commands,
    math_operator_query_commands,
    math_transform_commands,
    math_transform_query_commands,
    math_visualization_commands,
    math_visualization_query_commands,
    math_vertical_commands,
    math_vertical_query_commands,
)
from scopes_tool_core.capabilities import ScopeCapabilities, capabilities_for_model_id
from scopes_tool_core.channel import validate_analog_channel
from scopes_tool_core.demo import validate_demo_function, validate_demo_phase
from scopes_tool_core.identity import physical_model_for_id
from scopes_tool_core.save_export import (
    SAVE_IMAGE_FORMATS,
    SAVE_IMAGE_PALETTES,
    SAVE_WAVEFORM_FORMATS,
    validate_save_filename_base,
    validate_save_quoted_string,
    validate_save_waveform_length,
)
from scopes_tool_core.segmented_capture import (
    SegmentedCaptureRequest,
    validate_segmented_capture_request,
)
from scopes_tool_core.waveform import SUPPORTED_WAVEFORM_POINTS
from scopes_tool_core.wgen import (
    WGEN_LOADS,
    validate_wgen_amplitude,
    validate_wgen_frequency,
    validate_wgen_function,
    validate_wgen_offset,
)
from scopes_tool_core.serial import (
    validate_serial_can_trigger_request,
    validate_serial_i2c_trigger_request,
    validate_serial_spi_trigger_request,
    validate_serial_uart_trigger_request,
)

from . import cli as scope_cli
from . import parser as cli_parser
from . import preflight, runtime as cli_runtime


WORKER_SCHEMA_VERSION = 2

_CORE_WORKFLOW_COMMANDS = {
    "measure-log",
    "measure-until",
    "capture-batch",
    "triggered-measure-loop",
    "triggered-capture-series",
}
_NON_MATH_DOMAIN_COMMANDS = {
    "identify",
    "check-error",
    "system-clear-status",
    "system-opc",
    "system-status-byte",
    "system-standard-event",
    "system-operation-status",
    "system-options",
    "cleanup",
    "doctor",
    "run",
    "single",
    "stop-acquisition",
    "force-trigger",
    "acquisition",
    "acquisition-check",
    "sample-rate",
    "acquisition-points",
    "record-length",
    "segmented-memory",
    "segmented-capture",
    "channel-summary",
    "capture",
    "capture-batch",
    "screenshot",
    "smoke",
    "measure",
    "measure-results",
    "measure-stats",
    "measure-sweep",
    "measure-log",
    "measure-until",
    "triggered-measure-loop",
    "triggered-capture-series",
    "measure-clear",
    "measure-show",
    "measure-source",
    "measure-window",
    "dvm-enable",
    "dvm-source",
    "dvm-mode",
    "dvm-auto-range",
    "dvm-current",
    "dvm-query",
    "demo-query",
    "demo-output",
    "demo-function",
    "demo-phase",
    "wgen-query",
    "wgen-output",
    "wgen-function",
    "wgen-frequency",
    "wgen-voltage",
    "wgen-offset",
    "wgen-load",
    "serial-query",
    "serial-mode",
    "serial-display",
    "serial-uart",
    "serial-trigger-uart",
    "serial-trigger-i2c",
    "serial-trigger-spi",
    "serial-trigger-can",
    "serial-i2c",
    "serial-spi",
    "serial-can",
    "serial-lister-query",
    "serial-lister-display",
    "serial-lister-reference",
    "serial-lister-export",
    "search-state",
    "search-mode",
    "search-count",
    "search-event",
    "serial-search-uart",
    "serial-search-i2c",
    "serial-search-spi",
    "serial-search-can",
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
    "reference-save",
    "reference-display",
    "reference-label",
    "reference-clear",
    "reference-query",
    "channel-display",
    "channel-label",
    "channel-scale",
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
    "annotation",
    "timebase-scale",
    "timebase-position",
    "trigger-edge",
    "trigger-edge-source",
    "trigger-edge-slope",
    "trigger-edge-level",
    "external-trigger-range",
    "trigger-edge-external-level",
    "external-trigger-probe",
    "external-trigger-units",
    "external-trigger-settings",
    "trigger-pulse-width",
    "trigger-runt",
    "trigger-transition",
    "trigger-delay",
    "trigger-setup-hold",
    "trigger-edge-burst",
    "trigger-tv",
    "trigger-pattern",
    "trigger-or",
    "trigger-sweep",
    "trigger-noise-reject",
    "trigger-hf-reject",
    "trigger-edge-coupling",
    "trigger-edge-reject",
    "trigger-holdoff",
    "cursor",
    "autoscale",
    "setup-save",
    "setup-recall",
}

_MATH_WORKER_ARGUMENTS = {
    "fft": frozenset(
        {
            "function",
            "query",
            "source_channel",
            "units",
            "window",
            "center_hz",
            "span_hz",
            "display",
            "fft_operation",
            "start_hz",
            "stop_hz",
            "gate",
            "phase_reference",
            "detection_type",
            "detection_points",
        }
    ),
    "math-display": frozenset({"function", "on", "off", "query"}),
    "math-vertical": frozenset(
        {"function", "query", "scale", "range", "offset"}
    ),
    "math-operator": frozenset(
        {"function", "query", "operation", "source1", "source2"}
    ),
    "math-composite-source": frozenset(
        {"query", "operation", "source1", "source2"}
    ),
    "math-transform": frozenset(
        {
            "function",
            "query",
            "operation",
            "source",
            "input_offset",
            "gain",
            "linear_offset",
        }
    ),
    "math-filter": frozenset(
        {
            "function",
            "query",
            "operation",
            "source",
            "cutoff_hz",
            "average_count",
            "smooth_points",
        }
    ),
    "math-visualization": frozenset(
        {
            "function",
            "query",
            "operation",
            "source",
            "source2",
            "measurement",
            "measurement_slot",
        }
    ),
    "math-clear": frozenset({"function"}),
}

_MATH_DOMAIN_COMMANDS = frozenset(_MATH_WORKER_ARGUMENTS)
DOMAIN_COMMANDS = _NON_MATH_DOMAIN_COMMANDS | _MATH_DOMAIN_COMMANDS


def validate_command_request(body: Any) -> tuple[str, dict[str, Any], str | None]:
    if not isinstance(body, dict):
        raise OscilloscopeError("request body must be a JSON object")
    unknown = set(body) - {
        "schema_version",
        "command",
        "arguments",
        "job_id",
    }
    if unknown:
        raise OscilloscopeError(f"unknown request field: {sorted(unknown)[0]}")
    schema_version = body.get("schema_version")
    if type(schema_version) is not int or schema_version != WORKER_SCHEMA_VERSION:
        raise OscilloscopeError(
            f"schema_version must be exactly {WORKER_SCHEMA_VERSION}"
        )
    command = body.get("command")
    if not isinstance(command, str) or not command:
        raise OscilloscopeError("command must be a non-empty string")
    if command not in DOMAIN_COMMANDS:
        raise OscilloscopeError(f"unknown command: {command}")
    arguments = body.get("arguments", {})
    if not isinstance(arguments, dict):
        raise OscilloscopeError("arguments must be a JSON object")
    arguments = _normalize_capture_batch_worker_arguments(command, arguments)
    arguments = _normalize_segmented_memory_worker_arguments(command, arguments)
    arguments = _normalize_segmented_capture_worker_arguments(command, arguments)
    arguments = _normalize_triggered_measure_loop_worker_arguments(command, arguments)
    arguments = _normalize_triggered_capture_series_worker_arguments(command, arguments)
    arguments = _normalize_measure_until_worker_arguments(command, arguments)
    job_id = body.get("job_id")
    if job_id is not None and not isinstance(job_id, str):
        raise OscilloscopeError("job_id must be a string when provided")
    return command, arguments, job_id


def parse_domain_command(
    command: str,
    arguments: dict[str, Any],
    runtime: WorkerRuntime,
    job_dir: Path | None = None,
) -> argparse.Namespace:
    arguments = _normalize_capture_batch_worker_arguments(command, arguments)
    arguments = _normalize_segmented_memory_worker_arguments(command, arguments)
    arguments = _normalize_segmented_capture_worker_arguments(command, arguments, runtime)
    arguments = _normalize_triggered_measure_loop_worker_arguments(command, arguments)
    arguments = _normalize_triggered_capture_series_worker_arguments(command, arguments)
    arguments = _normalize_measure_until_worker_arguments(command, arguments)
    arguments = _normalize_system_status_worker_arguments(command, arguments)
    arguments = _normalize_screenshot_worker_arguments(command, arguments)
    _validate_display_worker_arguments(command, arguments)
    arguments = _normalize_measurement_reference_worker_arguments(
        command, arguments, runtime
    )
    arguments = _normalize_dvm_worker_arguments(command, arguments, runtime)
    arguments = _normalize_demo_worker_arguments(command, arguments, runtime)
    arguments = _normalize_wgen_worker_arguments(command, arguments)
    arguments = _normalize_serial_worker_arguments(
        command, arguments, capabilities_for_model_id(runtime.model)
    )
    if command in {
        "serial-trigger-uart", "serial-trigger-i2c", "serial-trigger-spi", "serial-trigger-can"
    }:
        arguments = {"command": command, **arguments}
        return _serial_uart_trigger_worker_namespace(arguments, runtime, job_dir)
    arguments = _normalize_search_worker_arguments(command, arguments, runtime)
    arguments = _normalize_serial_search_worker_arguments(command, arguments, runtime)
    arguments = _normalize_save_export_worker_arguments(command, arguments)
    arguments = _normalize_math_worker_arguments(command, arguments, runtime)
    arguments = _normalize_trigger_edge_worker_arguments(command, arguments)
    arguments = _normalize_trigger_edge_source_worker_arguments(
        command, arguments, runtime
    )
    arguments = _normalize_trigger_edge_slope_worker_arguments(command, arguments)
    arguments = _normalize_trigger_edge_level_worker_arguments(
        command, arguments, runtime
    )
    arguments = _normalize_external_trigger_range_worker_arguments(command, arguments)
    arguments = _normalize_trigger_edge_external_level_worker_arguments(
        command, arguments
    )
    arguments = _normalize_external_trigger_probe_worker_arguments(command, arguments)
    arguments = _normalize_external_trigger_units_worker_arguments(command, arguments)
    arguments = _normalize_external_trigger_settings_worker_arguments(command, arguments)
    arguments = _normalize_trigger_glitch_worker_arguments(command, arguments)
    arguments = _normalize_trigger_runt_worker_arguments(command, arguments)
    arguments = _normalize_trigger_transition_worker_arguments(command, arguments)
    arguments = _normalize_trigger_delay_worker_arguments(command, arguments)
    arguments = _normalize_trigger_setup_hold_worker_arguments(command, arguments)
    arguments = _normalize_trigger_edge_burst_worker_arguments(command, arguments)
    arguments = _normalize_trigger_tv_worker_arguments(command, arguments)
    arguments = _normalize_trigger_pattern_worker_arguments(command, arguments)
    arguments = _normalize_trigger_or_worker_arguments(command, arguments)
    arguments = _normalize_trigger_holdoff_worker_arguments(command, arguments)
    arguments = _normalize_trigger_common_worker_arguments(command, arguments)
    argv = [command, *arguments_to_argv(arguments)]
    if runtime.mode == "simulate":
        argv += ["--simulate", "--model", runtime.model]
    else:
        argv += ["--live", "--resource", runtime.resource or "", "--model", runtime.model]
    argv.append("--json")
    parser = cli_parser._build_parser()
    try:
        parsed = parser.parse_args(argv)
    except SystemExit as exc:
        raise OscilloscopeError(f"invalid arguments for {command}") from exc
    if runtime.mode == "live":
        setattr(parsed, "_worker_live_validation", True)
    cli_runtime._resolve_cli_mode(parsed)
    preflight.validate_pre_open_args(parsed)
    if job_dir is not None:
        _apply_worker_job_paths(parsed, job_dir)
    dry_args = argparse.Namespace(
        **{**vars(parsed), "dry_run": True, "simulate": False, "live": False}
    )
    scope_cli._dry_run_payload(dry_args)
    return parsed


def _normalize_capture_batch_worker_arguments(
    command: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if command != "capture-batch":
        return arguments

    allowed = {
        "channel",
        "points",
        "format",
        "count",
        "interval_seconds",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"capture-batch unknown argument: {sorted(unknown)[0]}"
        )
    return dict(arguments)


def _normalize_segmented_memory_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "segmented-memory":
        return arguments
    if set(arguments) == {"query"} and arguments.get("query") is True:
        return {"query": True}
    if set(arguments) == {"enable", "segments"} and arguments.get("enable") is True:
        segments = arguments["segments"]
        if isinstance(segments, bool) or not isinstance(segments, int):
            raise OscilloscopeError(
                "segmented-memory enable segments must be an integer"
            )
        return {"enable": True, "segments": segments}
    if set(arguments) == {"disable"} and arguments.get("disable") is True:
        return {"disable": True}
    raise OscilloscopeError(
        "segmented-memory requires exactly one canonical operation"
    )


def _normalize_segmented_capture_worker_arguments(
    command: str,
    arguments: dict[str, Any],
    runtime: WorkerRuntime | None = None,
) -> dict[str, Any]:
    if command != "segmented-capture":
        return arguments

    allowed = {
        "channel",
        "segments",
        "points",
        "format",
        "timeout_ms",
        "poll_interval_ms",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"segmented-capture unknown argument: {sorted(unknown)[0]}"
        )

    for required in ("channel", "segments"):
        if required not in arguments:
            raise OscilloscopeError(
                f"segmented-capture requires argument {required}"
            )

    values = {
        "channel": arguments["channel"],
        "segments": arguments["segments"],
        "points": arguments.get("points", 1000),
        "format": arguments.get("format", "byte"),
        "timeout_ms": arguments.get("timeout_ms", 30000),
        "poll_interval_ms": arguments.get("poll_interval_ms", 100),
    }
    for name in ("channel", "segments", "points", "timeout_ms", "poll_interval_ms"):
        value = values[name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise OscilloscopeError(f"segmented-capture argument {name} must be an integer")
    if not isinstance(values["format"], str) or values["format"] not in {"byte", "word"}:
        raise OscilloscopeError(
            "segmented-capture argument format must be exactly byte or word"
        )

    request = SegmentedCaptureRequest(
        channel=values["channel"],
        segments=values["segments"],
        points=values["points"],
        waveform_format=values["format"],
        timeout_ms=values["timeout_ms"],
        poll_interval_ms=values["poll_interval_ms"],
    )
    capabilities = (
        capabilities_for_model_id(runtime.model) if runtime is not None else None
    )
    validate_segmented_capture_request(request, capabilities)
    return dict(values)


def _normalize_triggered_measure_loop_worker_arguments(
    command: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if command != "triggered-measure-loop":
        return arguments

    allowed = {
        "channel",
        "items",
        "pair",
        "pair_items",
        "count",
        "trigger_timeout_seconds",
        "interval_seconds",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"triggered-measure-loop unknown argument: {sorted(unknown)[0]}"
        )
    for required in ("count", "trigger_timeout_seconds"):
        if required not in arguments:
            raise OscilloscopeError(
                f"triggered-measure-loop requires argument {required}"
            )

    count = arguments["count"]
    if isinstance(count, bool) or not isinstance(count, int):
        raise OscilloscopeError(
            "triggered-measure-loop argument count must be an integer"
        )
    if count < 1:
        raise OscilloscopeError(
            "triggered-measure-loop argument count must be at least 1"
        )

    for name, positive in (
        ("trigger_timeout_seconds", True),
        ("interval_seconds", False),
    ):
        if name not in arguments:
            continue
        value = arguments[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OscilloscopeError(
                f"triggered-measure-loop argument {name} must be a finite number"
            )
        if not math.isfinite(float(value)):
            raise OscilloscopeError(
                f"triggered-measure-loop argument {name} must be a finite number"
            )
        if positive and value <= 0:
            raise OscilloscopeError(
                "triggered-measure-loop argument trigger_timeout_seconds "
                "must be greater than zero"
            )
        if not positive and value < 0:
            raise OscilloscopeError(
                "triggered-measure-loop argument interval_seconds must be non-negative"
            )

    for name in ("items", "pair_items"):
        if name in arguments and not isinstance(arguments[name], str):
            raise OscilloscopeError(
                f"triggered-measure-loop argument {name} must be a string"
            )

    if "channel" in arguments:
        channels = arguments["channel"]
        if not isinstance(channels, list) or not channels:
            raise OscilloscopeError(
                "triggered-measure-loop argument channel must be a non-empty array"
            )
        for channel in channels:
            if isinstance(channel, bool) or not (
                isinstance(channel, int) or channel == "all"
            ):
                raise OscilloscopeError(
                    "triggered-measure-loop channel values must be integers or all"
                )

    if "pair" in arguments:
        pairs = arguments["pair"]
        if not isinstance(pairs, list) or any(
            not isinstance(pair, str) for pair in pairs
        ):
            raise OscilloscopeError(
                "triggered-measure-loop argument pair must be an array of strings"
            )

    return dict(arguments)


def _normalize_triggered_capture_series_worker_arguments(
    command: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if command != "triggered-capture-series":
        return arguments

    allowed = {
        "channel",
        "points",
        "format",
        "count",
        "trigger_timeout_seconds",
        "interval_seconds",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"triggered-capture-series unknown argument: {sorted(unknown)[0]}"
        )
    for required in ("channel", "count", "trigger_timeout_seconds"):
        if required not in arguments:
            raise OscilloscopeError(
                f"triggered-capture-series requires argument {required}"
            )

    channels = arguments["channel"]
    if not isinstance(channels, list) or not channels:
        raise OscilloscopeError(
            "triggered-capture-series argument channel must be a non-empty array"
        )
    for channel in channels:
        if isinstance(channel, bool) or not (
            (isinstance(channel, int) and channel > 0) or channel == "all"
        ):
            raise OscilloscopeError(
                "triggered-capture-series channel values must be positive integers or all"
            )

    count = arguments["count"]
    if isinstance(count, bool) or not isinstance(count, int):
        raise OscilloscopeError(
            "triggered-capture-series argument count must be an integer"
        )
    if count < 1:
        raise OscilloscopeError(
            "triggered-capture-series argument count must be at least 1"
        )

    if "points" in arguments:
        points = arguments["points"]
        if isinstance(points, bool) or not isinstance(points, int):
            raise OscilloscopeError(
                "triggered-capture-series argument points must be an integer"
            )
        if points not in SUPPORTED_WAVEFORM_POINTS:
            raise OscilloscopeError(
                "triggered-capture-series argument points is not supported"
            )

    if "format" in arguments:
        waveform_format = arguments["format"]
        if not isinstance(waveform_format, str) or waveform_format not in {
            "byte",
            "word",
        }:
            raise OscilloscopeError(
                "triggered-capture-series argument format must be exactly byte or word"
            )

    for name, positive in (
        ("trigger_timeout_seconds", True),
        ("interval_seconds", False),
    ):
        if name not in arguments:
            continue
        value = arguments[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OscilloscopeError(
                f"triggered-capture-series argument {name} must be a finite number"
            )
        if not math.isfinite(float(value)):
            raise OscilloscopeError(
                f"triggered-capture-series argument {name} must be a finite number"
            )
        if positive and value <= 0:
            raise OscilloscopeError(
                "triggered-capture-series argument trigger_timeout_seconds "
                "must be greater than zero"
            )
        if not positive and value < 0:
            raise OscilloscopeError(
                "triggered-capture-series argument interval_seconds must be non-negative"
            )

    return dict(arguments)


def _normalize_measure_until_worker_arguments(
    command: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if command != "measure-until":
        return arguments

    allowed = {
        "channel",
        "item",
        "operator",
        "threshold",
        "timeout_seconds",
        "interval_seconds",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"measure-until unknown argument: {sorted(unknown)[0]}"
        )
    for required in ("channel", "item", "operator", "threshold", "timeout_seconds"):
        if required not in arguments:
            raise OscilloscopeError(f"measure-until requires argument {required}")

    channel = arguments["channel"]
    if isinstance(channel, bool) or not isinstance(channel, int):
        raise OscilloscopeError("measure-until argument channel must be an integer")
    if channel < 1:
        raise OscilloscopeError("measure-until argument channel must be at least 1")

    item = arguments["item"]
    if not isinstance(item, str) or not item:
        raise OscilloscopeError("measure-until argument item must be a non-empty string")

    operator = arguments["operator"]
    if not isinstance(operator, str) or operator not in {"gt", "gte", "lt", "lte"}:
        raise OscilloscopeError(
            "measure-until argument operator must be exactly gt, gte, lt, or lte"
        )

    for name in ("threshold", "timeout_seconds", "interval_seconds"):
        if name not in arguments:
            continue
        value = arguments[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OscilloscopeError(
                f"measure-until argument {name} must be a finite number"
            )
        if not math.isfinite(float(value)):
            raise OscilloscopeError(
                f"measure-until argument {name} must be a finite number"
            )
        if name == "timeout_seconds" and value <= 0:
            raise OscilloscopeError(
                "measure-until argument timeout_seconds must be greater than zero"
            )
        if name == "interval_seconds" and value < 0:
            raise OscilloscopeError(
                "measure-until argument interval_seconds must be non-negative"
            )

    return dict(arguments)


def _normalize_system_status_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command == "system-clear-status":
        if arguments:
            raise OscilloscopeError("system-clear-status accepts only an empty object")
        return {}

    query_commands = {
        "system-opc",
        "system-status-byte",
        "system-standard-event",
        "system-operation-status",
        "system-options",
    }
    if command not in query_commands:
        return arguments
    if set(arguments) != {"query"} or arguments.get("query") is not True:
        raise OscilloscopeError(f"{command} requires exactly query=true")
    return dict(arguments)


def _validate_display_worker_arguments(command: str, arguments: dict[str, Any]) -> None:
    allowed_by_command = {
        "display-clear": set(),
        "display-persistence": {"query", "mode", "seconds"},
        "display-intensity": {"query", "value"},
        "display-vectors": {"query", "on"},
    }
    if command not in allowed_by_command:
        return
    allowed = allowed_by_command[command]
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(f"unknown argument for {command}: {sorted(unknown)[0]}")
    if command == "display-clear" and arguments:
        raise OscilloscopeError("display-clear does not accept arguments")
    for key in ("query", "on"):
        if key in arguments and arguments[key] is not True:
            raise OscilloscopeError(f"{command} argument {key} must be exactly true")


def _normalize_measurement_reference_worker_arguments(
    command: str, arguments: dict[str, Any], runtime: WorkerRuntime
) -> dict[str, Any]:
    allowed_by_command = {
        "measure-clear": set(),
        "measure-show": {"on", "query"},
        "measure-source": {"source_channel", "source2_channel", "query"},
        "measure-window": {"window", "query"},
        "reference-save": {"slot", "source_channel"},
        "reference-display": {"slot", "state", "query"},
        "reference-label": {"slot", "text", "query"},
        "reference-clear": {"slot"},
        "reference-query": {"slot"},
    }
    if command not in allowed_by_command:
        return arguments
    unknown = set(arguments) - allowed_by_command[command]
    if unknown:
        raise OscilloscopeError(f"unknown argument for {command}: {sorted(unknown)[0]}")
    if command == "measure-clear" and arguments:
        raise OscilloscopeError("measure-clear does not accept arguments")
    for key in ("on", "query"):
        if key in arguments and arguments[key] is not True:
            raise OscilloscopeError(f"{command} argument {key} must be exactly true")
    if command == "reference-label" and "text" in arguments:
        if not isinstance(arguments["text"], str):
            raise OscilloscopeError("reference-label argument text must be a string")
    capabilities = capabilities_for_model_id(runtime.model)
    if "slot" in arguments:
        slot = arguments["slot"]
        if not isinstance(slot, int) or isinstance(slot, bool):
            raise OscilloscopeError(f"{command} argument slot must be an integer")
        if slot < 1 or slot > capabilities.reference_waveforms:
            raise OscilloscopeError(
                f"reference waveform slot must be in range 1-{capabilities.reference_waveforms}."
            )
    for key in ("source_channel", "source2_channel"):
        if key not in arguments:
            continue
        channel = arguments[key]
        if not isinstance(channel, int) or isinstance(channel, bool):
            raise OscilloscopeError(f"{command} argument {key} must be an integer")
        validate_analog_channel(channel, capabilities)
    return dict(arguments)


def _normalize_trigger_edge_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-edge":
        return arguments
    allowed = {"query", "source_channel", "level", "slope"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(f"unknown argument for trigger-edge: {sorted(unknown)[0]}")
    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError("trigger-edge argument query must be exactly true")
        configure_keys = {"source_channel", "level", "slope"} & set(arguments)
        if configure_keys:
            raise OscilloscopeError(
                "trigger-edge query cannot be combined with configure arguments"
            )
        return dict(arguments)
    return dict(arguments)


def _normalize_trigger_edge_source_worker_arguments(
    command: str,
    arguments: dict[str, Any],
    runtime: WorkerRuntime,
) -> dict[str, Any]:
    if command != "trigger-edge-source":
        return arguments
    allowed = {"query", "source", "source_channel"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for trigger-edge-source: {sorted(unknown)[0]}"
        )
    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                "trigger-edge-source argument query must be exactly true"
            )
        if {"source", "source_channel"} & set(arguments):
            raise OscilloscopeError(
                "trigger-edge-source query cannot be combined with configure arguments"
            )
        return {"query": True}
    has_source = "source" in arguments
    has_channel = "source_channel" in arguments
    if has_source == has_channel:
        raise OscilloscopeError(
            "trigger-edge-source configure requires exactly one of source or source_channel"
        )
    if has_source:
        source = arguments["source"]
        if not isinstance(source, str):
            raise OscilloscopeError("trigger-edge-source argument source must be a string")
        if source not in {"external", "line"}:
            raise OscilloscopeError(
                "trigger-edge-source argument source must be one of: external, line"
            )
        return {"source": source}
    source_channel = arguments["source_channel"]
    if isinstance(source_channel, bool) or not isinstance(source_channel, int):
        raise OscilloscopeError(
            "trigger-edge-source argument source_channel must be an integer"
        )
    try:
        source_channel = validate_analog_channel(
            source_channel, capabilities_for_model_id(runtime.model)
        )
    except OscilloscopeError as exc:
        raise OscilloscopeError(
            f"trigger-edge-source argument source_channel is invalid: {exc}"
        ) from exc
    return {"source_channel": source_channel}


def _normalize_trigger_edge_slope_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-edge-slope":
        return arguments
    allowed = {"query", "slope"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for trigger-edge-slope: {sorted(unknown)[0]}"
        )
    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                "trigger-edge-slope argument query must be exactly true"
            )
        if "slope" in arguments:
            raise OscilloscopeError(
                "trigger-edge-slope query cannot be combined with slope"
            )
        return {"query": True}
    slope = arguments.get("slope")
    if not isinstance(slope, str) or slope not in {
        "positive",
        "negative",
        "either",
        "alternate",
    }:
        raise OscilloscopeError(
            "trigger-edge-slope argument slope must be one of: positive, negative, either, alternate"
        )
    return {"slope": slope}


def _normalize_trigger_edge_level_worker_arguments(
    command: str,
    arguments: dict[str, Any],
    runtime: WorkerRuntime,
) -> dict[str, Any]:
    if command != "trigger-edge-level":
        return arguments
    allowed = {"query", "source_channel", "level_volts"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for trigger-edge-level: {sorted(unknown)[0]}"
        )
    if "source_channel" not in arguments:
        raise OscilloscopeError("trigger-edge-level requires source_channel")
    source_channel = arguments["source_channel"]
    if isinstance(source_channel, bool) or not isinstance(source_channel, int):
        raise OscilloscopeError("trigger-edge-level argument source_channel must be an integer")
    try:
        source_channel = validate_analog_channel(
            source_channel, capabilities_for_model_id(runtime.model)
        )
    except OscilloscopeError as exc:
        raise OscilloscopeError(
            f"trigger-edge-level argument source_channel is invalid: {exc}"
        ) from exc
    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                "trigger-edge-level argument query must be exactly true"
            )
        if "level_volts" in arguments:
            raise OscilloscopeError(
                "trigger-edge-level query cannot be combined with level_volts"
            )
        return {"query": True, "source_channel": source_channel}
    if "level_volts" not in arguments:
        raise OscilloscopeError(
            "trigger-edge-level configure requires level_volts"
        )
    level_volts = arguments["level_volts"]
    if (
        isinstance(level_volts, bool)
        or not isinstance(level_volts, (int, float))
        or not math.isfinite(float(level_volts))
    ):
        raise OscilloscopeError(
            "trigger-edge-level argument level_volts must be a finite number"
        )
    return {"source_channel": source_channel, "level_volts": level_volts}


def _normalize_external_trigger_range_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "external-trigger-range":
        return arguments
    allowed = {"query", "range_volts"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for external-trigger-range: {sorted(unknown)[0]}"
        )
    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                "external-trigger-range argument query must be exactly true"
            )
        if "range_volts" in arguments:
            raise OscilloscopeError(
                "external-trigger-range query cannot be combined with range_volts"
            )
        return {"query": True}
    if "range_volts" not in arguments:
        raise OscilloscopeError("external-trigger-range configure requires range_volts")
    range_volts = arguments["range_volts"]
    if isinstance(range_volts, bool) or not isinstance(range_volts, (int, float)):
        raise OscilloscopeError(
            "external-trigger-range argument range_volts must be a positive finite number"
        )
    try:
        finite_range_volts = math.isfinite(float(range_volts))
    except (TypeError, ValueError, OverflowError):
        finite_range_volts = False
    if not finite_range_volts or range_volts <= 0:
        raise OscilloscopeError(
            "external-trigger-range argument range_volts must be a positive finite number"
        )
    return {"range_volts": range_volts}


def _normalize_trigger_edge_external_level_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-edge-external-level":
        return arguments
    allowed = {"query", "level_volts"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for trigger-edge-external-level: {sorted(unknown)[0]}"
        )
    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                "trigger-edge-external-level argument query must be exactly true"
            )
        if "level_volts" in arguments:
            raise OscilloscopeError(
                "trigger-edge-external-level query cannot be combined with level_volts"
            )
        return {"query": True}
    if "level_volts" not in arguments:
        raise OscilloscopeError(
            "trigger-edge-external-level configure requires level_volts"
        )
    level_volts = arguments["level_volts"]
    if isinstance(level_volts, bool) or not isinstance(level_volts, (int, float)):
        raise OscilloscopeError(
            "trigger-edge-external-level argument level_volts must be a finite number"
        )
    try:
        finite_level_volts = math.isfinite(float(level_volts))
    except (TypeError, ValueError, OverflowError):
        finite_level_volts = False
    if not finite_level_volts:
        raise OscilloscopeError(
            "trigger-edge-external-level argument level_volts must be a finite number"
        )
    return {"level_volts": level_volts}


def _normalize_external_trigger_probe_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "external-trigger-probe":
        return arguments
    allowed = {"query", "attenuation"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for external-trigger-probe: {sorted(unknown)[0]}"
        )
    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                "external-trigger-probe argument query must be exactly true"
            )
        if "attenuation" in arguments:
            raise OscilloscopeError(
                "external-trigger-probe query cannot be combined with attenuation"
            )
        return {"query": True}
    if "attenuation" not in arguments:
        raise OscilloscopeError("external-trigger-probe configure requires attenuation")
    attenuation = arguments["attenuation"]
    if isinstance(attenuation, bool) or not isinstance(attenuation, (int, float)):
        raise OscilloscopeError(
            "external-trigger-probe argument attenuation must be a positive finite number"
        )
    try:
        finite_attenuation = math.isfinite(float(attenuation))
    except (TypeError, ValueError, OverflowError):
        finite_attenuation = False
    if not finite_attenuation or attenuation <= 0:
        raise OscilloscopeError(
            "external-trigger-probe argument attenuation must be a positive finite number"
        )
    return {"attenuation": attenuation}


def _normalize_external_trigger_units_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "external-trigger-units":
        return arguments
    allowed = {"query", "units"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for external-trigger-units: {sorted(unknown)[0]}"
        )
    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                "external-trigger-units argument query must be exactly true"
            )
        if "units" in arguments:
            raise OscilloscopeError(
                "external-trigger-units query cannot be combined with units"
            )
        return {"query": True}
    if arguments.get("units") not in {"volts", "amps"}:
        raise OscilloscopeError(
            "external-trigger-units configure requires units of volts or amps"
        )
    return {"units": arguments["units"]}


def _normalize_external_trigger_settings_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "external-trigger-settings":
        return arguments
    if set(arguments) - {"query"}:
        raise OscilloscopeError(
            f"unknown argument for external-trigger-settings: {sorted(set(arguments) - {'query'})[0]}"
        )
    if arguments.get("query") is not True:
        raise OscilloscopeError("external-trigger-settings requires query to be exactly true")
    return {"query": True}


def _normalize_trigger_glitch_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-pulse-width":
        return arguments
    allowed = {
        "query",
        "channel",
        "polarity",
        "qualifier",
        "time_seconds",
        "min_time_seconds",
        "max_time_seconds",
        "level_volts",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(f"unknown argument for trigger-pulse-width: {sorted(unknown)[0]}")
    if "query" in arguments and arguments["query"] is not True:
        raise OscilloscopeError("trigger-pulse-width argument query must be exactly true")
    normalized = dict(arguments)
    qualifier = normalized.get("qualifier")
    if qualifier == "greater_than":
        normalized["qualifier"] = "greater-than"
    elif qualifier == "less_than":
        normalized["qualifier"] = "less-than"
    return normalized


def _normalize_trigger_runt_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-runt":
        return arguments
    allowed = {
        "query",
        "channel",
        "polarity",
        "qualifier",
        "time_seconds",
        "low_level_volts",
        "high_level_volts",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(f"unknown argument for trigger-runt: {sorted(unknown)[0]}")
    if "query" in arguments and arguments["query"] is not True:
        raise OscilloscopeError("trigger-runt argument query must be exactly true")
    normalized = dict(arguments)
    qualifier = normalized.get("qualifier")
    if qualifier == "greater_than":
        normalized["qualifier"] = "greater-than"
    elif qualifier == "less_than":
        normalized["qualifier"] = "less-than"
    return normalized


def _normalize_trigger_transition_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-transition":
        return arguments
    allowed = {
        "query",
        "channel",
        "slope",
        "qualifier",
        "time_seconds",
        "low_level_volts",
        "high_level_volts",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(f"unknown argument for trigger-transition: {sorted(unknown)[0]}")
    if "query" in arguments and arguments["query"] is not True:
        raise OscilloscopeError("trigger-transition argument query must be exactly true")
    normalized = dict(arguments)
    qualifier = normalized.get("qualifier")
    if qualifier == "greater_than":
        normalized["qualifier"] = "greater-than"
    elif qualifier == "less_than":
        normalized["qualifier"] = "less-than"
    return normalized


def _normalize_trigger_delay_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-delay":
        return arguments
    allowed = {
        "query",
        "arm_channel",
        "arm_slope",
        "trigger_channel",
        "trigger_slope",
        "time_seconds",
        "count",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(f"unknown argument for trigger-delay: {sorted(unknown)[0]}")
    if "query" in arguments and arguments["query"] is not True:
        raise OscilloscopeError("trigger-delay argument query must be exactly true")
    return dict(arguments)


def _normalize_trigger_setup_hold_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-setup-hold":
        return arguments
    allowed = {
        "query",
        "clock_channel",
        "data_channel",
        "slope",
        "setup_time",
        "hold_time",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for trigger-setup-hold: {sorted(unknown)[0]}"
        )
    if "query" in arguments and arguments["query"] is not True:
        raise OscilloscopeError("trigger-setup-hold argument query must be exactly true")
    return dict(arguments)


def _normalize_trigger_edge_burst_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-edge-burst":
        return arguments
    allowed = {
        "query",
        "source_channel",
        "slope",
        "count",
        "idle_time",
        "level_volts",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for trigger-edge-burst: {sorted(unknown)[0]}"
        )
    if "query" in arguments and arguments["query"] is not True:
        raise OscilloscopeError("trigger-edge-burst argument query must be exactly true")
    return dict(arguments)


def _normalize_trigger_tv_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-tv":
        return arguments
    allowed = {
        "query",
        "source_channel",
        "standard",
        "mode",
        "line",
        "polarity",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(f"unknown argument for trigger-tv: {sorted(unknown)[0]}")
    if "query" in arguments and arguments["query"] is not True:
        raise OscilloscopeError("trigger-tv argument query must be exactly true")
    return dict(arguments)


def _normalize_trigger_pattern_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-pattern":
        return arguments
    allowed = {"query", "pattern"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(f"unknown argument for trigger-pattern: {sorted(unknown)[0]}")
    if "query" in arguments and arguments["query"] is not True:
        raise OscilloscopeError("trigger-pattern argument query must be exactly true")
    return dict(arguments)


def _normalize_trigger_or_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-or":
        return arguments
    allowed = {"query", "pattern"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(f"unknown argument for trigger-or: {sorted(unknown)[0]}")
    if "query" in arguments and arguments["query"] is not True:
        raise OscilloscopeError("trigger-or argument query must be exactly true")
    return dict(arguments)


def _normalize_trigger_holdoff_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "trigger-holdoff":
        return arguments
    allowed = {"query", "seconds"}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for trigger-holdoff: {sorted(unknown)[0]}"
        )
    if not arguments:
        raise OscilloscopeError("trigger-holdoff requires query or seconds")
    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                "trigger-holdoff argument query must be exactly true"
            )
        if "seconds" in arguments:
            raise OscilloscopeError(
                "trigger-holdoff query cannot be combined with configure arguments"
            )
        return dict(arguments)
    if set(arguments) != {"seconds"}:
        raise OscilloscopeError("trigger-holdoff requires query or seconds")
    seconds = arguments["seconds"]
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        raise OscilloscopeError("trigger-holdoff argument seconds must be a JSON number")
    if not math.isfinite(float(seconds)):
        raise OscilloscopeError("trigger-holdoff argument seconds must be finite")
    return dict(arguments)


def _normalize_trigger_common_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command == "trigger-sweep":
        allowed = {"query", "mode"}
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for trigger-sweep: {sorted(unknown)[0]}"
            )
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(
                    "trigger-sweep argument query must be exactly true"
                )
            if "mode" in arguments:
                raise OscilloscopeError(
                    "trigger-sweep query cannot be combined with configure arguments"
                )
            return dict(arguments)
        return dict(arguments)

    if command in {"trigger-noise-reject", "trigger-hf-reject"}:
        allowed = {"query", "enabled"}
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for {command}: {sorted(unknown)[0]}"
            )
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(f"{command} argument query must be exactly true")
            if "enabled" in arguments:
                raise OscilloscopeError(
                    f"{command} query cannot be combined with configure arguments"
                )
            return dict(arguments)
        normalized = dict(arguments)
        if "enabled" in normalized:
            if not isinstance(normalized["enabled"], bool):
                raise OscilloscopeError(f"{command} argument enabled must be a boolean")
            normalized["enabled"] = "true" if normalized["enabled"] else "false"
        return normalized

    if command == "trigger-edge-coupling":
        allowed = {"query", "coupling"}
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for trigger-edge-coupling: {sorted(unknown)[0]}"
            )
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError("trigger-edge-coupling argument query must be exactly true")
            if "coupling" in arguments:
                raise OscilloscopeError(
                    "trigger-edge-coupling query cannot be combined with configure arguments"
                )
            return dict(arguments)
        if "coupling" not in arguments:
            raise OscilloscopeError("trigger-edge-coupling configure requires coupling")
        coupling = arguments["coupling"]
        if not isinstance(coupling, str):
            raise OscilloscopeError("trigger-edge-coupling argument coupling must be a string")
        if coupling not in {"ac", "dc", "lf-reject"}:
            raise OscilloscopeError(
                "trigger-edge-coupling argument coupling must be one of: ac, dc, lf-reject"
            )
        return {"coupling": coupling}

    if command == "trigger-edge-reject":
        allowed = {"query", "reject"}
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for trigger-edge-reject: {sorted(unknown)[0]}"
            )
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError("trigger-edge-reject argument query must be exactly true")
            if "reject" in arguments:
                raise OscilloscopeError(
                    "trigger-edge-reject query cannot be combined with configure arguments"
                )
            return dict(arguments)
        if "reject" not in arguments:
            raise OscilloscopeError("trigger-edge-reject configure requires reject")
        reject = arguments["reject"]
        if not isinstance(reject, str):
            raise OscilloscopeError("trigger-edge-reject argument reject must be a string")
        if reject not in {"off", "lf-reject", "hf-reject"}:
            raise OscilloscopeError(
                "trigger-edge-reject argument reject must be one of: off, lf-reject, hf-reject"
            )
        return {"reject": reject}

    return arguments


def _normalize_screenshot_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command != "screenshot":
        return arguments
    allowed = {
        "output",
        "background",
        "format",
        "ink_saver",
        "palette",
        "layout",
        "query_hardcopy",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for screenshot: {sorted(unknown)[0]}"
        )
    if "query_hardcopy" in arguments:
        if arguments.get("query_hardcopy") is not True:
            raise OscilloscopeError(
                "screenshot argument query_hardcopy must be exactly true"
            )
        if set(arguments) != {"query_hardcopy"}:
            raise OscilloscopeError(
                "screenshot query_hardcopy cannot be combined with capture arguments"
            )
        return dict(arguments)
    for key in ("output", "background", "format", "palette", "layout"):
        if key in arguments and not isinstance(arguments[key], str):
            raise OscilloscopeError(f"screenshot argument {key} must be a string")
    if "ink_saver" in arguments and not isinstance(arguments["ink_saver"], bool):
        raise OscilloscopeError("screenshot argument ink_saver must be a boolean")
    if arguments.get("format") not in {None, "png", "bmp", "bmp8bit"}:
        raise OscilloscopeError(
            "screenshot argument format must be one of: png, bmp, bmp8bit"
        )
    if arguments.get("background") not in {None, "black", "white"}:
        raise OscilloscopeError(
            "screenshot argument background must be one of: black, white"
        )
    if arguments.get("palette") not in {None, "color", "grayscale", "none"}:
        raise OscilloscopeError(
            "screenshot argument palette must be one of: color, grayscale, none"
        )
    if arguments.get("layout") not in {None, "landscape", "portrait"}:
        raise OscilloscopeError(
            "screenshot argument layout must be one of: landscape, portrait"
        )
    normalized = dict(arguments)
    if "ink_saver" in normalized:
        normalized["ink_saver"] = "true" if normalized["ink_saver"] else "false"
    return normalized


def _normalize_dvm_worker_arguments(
    command: str, arguments: dict[str, Any], runtime: WorkerRuntime
) -> dict[str, Any]:
    if command not in {
        "dvm-enable",
        "dvm-source",
        "dvm-mode",
        "dvm-auto-range",
        "dvm-current",
        "dvm-query",
    }:
        return arguments

    if command in {"dvm-current", "dvm-query"}:
        if set(arguments) != {"query"} or arguments.get("query") is not True:
            raise OscilloscopeError(f"{command} requires exactly query=true")
        return dict(arguments)

    configure_key = {
        "dvm-enable": "enabled",
        "dvm-source": "channel",
        "dvm-mode": "mode",
        "dvm-auto-range": "enabled",
    }[command]
    allowed = {"query", configure_key}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for {command}: {sorted(unknown)[0]}"
        )
    if arguments.get("query") is True:
        if set(arguments) != {"query"}:
            raise OscilloscopeError(
                f"{command} query cannot be combined with configure arguments"
            )
        return dict(arguments)
    if "query" in arguments:
        raise OscilloscopeError(f"{command} argument query must be exactly true")
    if set(arguments) != {configure_key}:
        raise OscilloscopeError(
            f"{command} configure requires exactly {configure_key}"
        )

    value = arguments[configure_key]
    if command in {"dvm-enable", "dvm-auto-range"}:
        if not isinstance(value, bool):
            raise OscilloscopeError(f"{command} argument enabled must be a boolean")
        return {"enabled": "true" if value else "false"}
    if command == "dvm-source":
        if not isinstance(value, int) or isinstance(value, bool):
            raise OscilloscopeError("dvm-source argument channel must be an integer")
        validate_analog_channel(value, capabilities_for_model_id(runtime.model))
        return dict(arguments)
    if value not in {"dc", "dc-rms", "ac-rms"}:
        raise OscilloscopeError(
            "dvm-mode argument mode must be one of: dc, dc-rms, ac-rms"
        )
    return dict(arguments)


def _normalize_demo_worker_arguments(
    command: str, arguments: dict[str, Any], runtime: WorkerRuntime
) -> dict[str, Any]:
    if command not in {"demo-query", "demo-output", "demo-function", "demo-phase"}:
        return arguments

    if command == "demo-query":
        if arguments:
            raise OscilloscopeError("demo-query accepts only an empty arguments object")
        return {}

    configure_key = {
        "demo-output": "enabled",
        "demo-function": "function",
        "demo-phase": "degrees",
    }[command]
    allowed = {"query", configure_key}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(f"unknown argument for {command}: {sorted(unknown)[0]}")
    if arguments.get("query") is True:
        if set(arguments) != {"query"}:
            raise OscilloscopeError(
                f"{command} query cannot be combined with configure arguments"
            )
        return {"query": True}
    if "query" in arguments:
        raise OscilloscopeError(f"{command} argument query must be exactly true")
    if set(arguments) != {configure_key}:
        raise OscilloscopeError(f"{command} configure requires exactly {configure_key}")

    value = arguments[configure_key]
    if command == "demo-output":
        if not isinstance(value, bool):
            raise OscilloscopeError("demo-output argument enabled must be a boolean")
        return {"enabled": "true" if value else "false"}
    if command == "demo-function":
        if not isinstance(value, str):
            raise OscilloscopeError("demo-function argument function must be a string")
        validate_demo_function(value, capabilities_for_model_id(runtime.model))
        return dict(arguments)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OscilloscopeError("demo-phase argument degrees must be a finite number")
    validate_demo_phase(value)
    return dict(arguments)


def _normalize_wgen_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if command not in {
        "wgen-query",
        "wgen-output",
        "wgen-function",
        "wgen-frequency",
        "wgen-voltage",
        "wgen-offset",
        "wgen-load",
    }:
        return arguments

    if command == "wgen-query":
        if set(arguments) != {"query"} or arguments.get("query") is not True:
            raise OscilloscopeError("wgen-query requires exactly query=true")
        return {}

    configure_key = {
        "wgen-output": "enabled",
        "wgen-function": "function",
        "wgen-frequency": "hz",
        "wgen-voltage": "amplitude",
        "wgen-offset": "volts",
        "wgen-load": "load",
    }[command]
    allowed = {"query", configure_key}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for {command}: {sorted(unknown)[0]}"
        )
    if arguments.get("query") is True:
        if set(arguments) != {"query"}:
            raise OscilloscopeError(
                f"{command} query cannot be combined with configure arguments"
            )
        return {"query": True}
    if "query" in arguments:
        raise OscilloscopeError(f"{command} argument query must be exactly true")
    if set(arguments) != {configure_key}:
        raise OscilloscopeError(
            f"{command} configure requires exactly {configure_key}"
        )

    value = arguments[configure_key]
    if command == "wgen-output":
        if not isinstance(value, bool):
            raise OscilloscopeError("wgen-output argument enabled must be a boolean")
        return {"enabled": "true" if value else "false"}
    if command == "wgen-function":
        validate_wgen_function(value)
    elif command == "wgen-frequency":
        validate_wgen_frequency(value)
    elif command == "wgen-voltage":
        validate_wgen_amplitude(value)
    elif command == "wgen-offset":
        validate_wgen_offset(value)
    elif not isinstance(value, str) or value not in WGEN_LOADS:
        raise OscilloscopeError(
            "wgen-load argument load must be one of: one-meg, fifty"
        )
    return dict(arguments)


def _normalize_serial_search_worker_arguments(
    command: str, arguments: dict[str, Any], runtime: WorkerRuntime
) -> dict[str, Any]:
    if command not in {
        "serial-search-uart",
        "serial-search-i2c",
        "serial-search-spi",
        "serial-search-can",
    }:
        return arguments

    capabilities = capabilities_for_model_id(runtime.model)
    if not capabilities.supports_search_basic:
        raise OscilloscopeError(
            f"Search Basic Pack v1 is not supported by the selected "
            f"{capabilities.series} model profile."
        )

    protocol = command.removeprefix("serial-search-")
    if protocol not in capabilities.serial_modes:
        raise OscilloscopeError(
            f"Serial mode {protocol!r} is not supported by the selected "
            f"{capabilities.series} model profile."
        )

    if "bus" not in arguments:
        raise OscilloscopeError(f"{command} requires bus")
    bus = arguments["bus"]
    if isinstance(bus, bool) or not isinstance(bus, int):
        raise OscilloscopeError(f"{command} argument bus must be an integer")
    try:
        validate_serial_search_bus(bus, capabilities)
    except ParameterValidationError as exc:
        raise OscilloscopeError(str(exc)) from exc

    allowed_by_cmd = {
        "serial-search-uart": {"bus", "query", "mode", "data", "qualifier"},
        "serial-search-i2c": {"bus", "query", "mode", "address", "data", "data2", "qualifier"},
        "serial-search-spi": {"bus", "query", "mode", "data", "width"},
        "serial-search-can": {"bus", "query", "mode", "data", "data_length", "id", "id_mode"},
    }
    allowed = allowed_by_cmd[command]
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for {command}: {sorted(unknown)[0]}"
        )

    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                f"{command} argument query must be strictly boolean True"
            )
        if len(set(arguments) - {"bus", "query"}) > 0:
            raise OscilloscopeError(
                f"{command} query cannot be combined with configure options"
            )
        return dict(arguments)

    if "mode" not in arguments:
        raise OscilloscopeError(f"{command} configure requires mode")

    mode = arguments["mode"]
    if not isinstance(mode, str):
        raise OscilloscopeError(f"{command} argument mode must be a string")

    try:
        if protocol == "uart":
            validate_uart_search_mode(mode)
            if "data" in arguments:
                data = arguments["data"]
                if isinstance(data, bool) or not isinstance(data, int):
                    raise OscilloscopeError(f"{command} argument data must be an integer")
                validate_uart_data(data)
            if "qualifier" in arguments:
                q = arguments["qualifier"]
                if not isinstance(q, str):
                    raise OscilloscopeError(f"{command} argument qualifier must be a string")
                validate_search_qualifier(q)
        elif protocol == "i2c":
            validate_i2c_search_mode(mode)
            for f_name in ("address", "data", "data2"):
                if f_name in arguments:
                    val = arguments[f_name]
                    if isinstance(val, bool) or not isinstance(val, int):
                        raise OscilloscopeError(f"{command} argument {f_name} must be an integer")
                    validate_i2c_pattern_value(val, f_name)
            if "qualifier" in arguments:
                q = arguments["qualifier"]
                if not isinstance(q, str):
                    raise OscilloscopeError(f"{command} argument qualifier must be a string")
                validate_search_qualifier(q)
        elif protocol == "spi":
            validate_spi_search_mode(mode)
            canonical_data = None
            canonical_width = None
            if "data" in arguments:
                data = arguments["data"]
                if not isinstance(data, str):
                    raise OscilloscopeError(f"{command} argument data must be a string")
                canonical_data = validate_pattern_hex_x(data, "data")
            if "width" in arguments:
                width = arguments["width"]
                if isinstance(width, bool) or not isinstance(width, int):
                    raise OscilloscopeError(f"{command} argument width must be an integer")
                canonical_width = validate_spi_width(width)
            validate_spi_search_pattern_width(canonical_data, canonical_width)
        elif protocol == "can":
            canonical_mode = validate_can_search_mode(mode)
            canonical_data = None
            canonical_data_length = None
            canonical_id = None
            canonical_id_mode = None
            if "data" in arguments:
                data = arguments["data"]
                if not isinstance(data, str):
                    raise OscilloscopeError(f"{command} argument data must be a string")
                canonical_data = validate_pattern_hex_x(data, "data")
            if "data_length" in arguments:
                length = arguments["data_length"]
                if isinstance(length, bool) or not isinstance(length, int):
                    raise OscilloscopeError(f"{command} argument data_length must be an integer")
                canonical_data_length = validate_can_data_length(length)
            if "id" in arguments:
                cid = arguments["id"]
                if not isinstance(cid, str):
                    raise OscilloscopeError(f"{command} argument id must be a string")
                canonical_id = validate_pattern_hex_x(cid, "id")
            if "id_mode" in arguments:
                id_mode = arguments["id_mode"]
                if not isinstance(id_mode, str):
                    raise OscilloscopeError(f"{command} argument id_mode must be a string")
                canonical_id_mode = validate_can_id_mode(id_mode)
            validate_can_search_criteria(
                canonical_mode,
                data=canonical_data,
                data_length=canonical_data_length,
                id_val=canonical_id,
                id_mode=canonical_id_mode,
            )
    except ParameterValidationError as exc:
        raise OscilloscopeError(str(exc)) from exc

    return dict(arguments)


def _normalize_search_worker_arguments(
    command: str, arguments: dict[str, Any], runtime: WorkerRuntime
) -> dict[str, Any]:
    if command not in {"search-state", "search-mode", "search-count", "search-event"}:
        return arguments

    if command == "search-event":
        capabilities = capabilities_for_model_id(runtime.model)
        if not capabilities.supports_search_event_navigation:
            raise OscilloscopeError(
                f"Search event navigation is not supported by the selected "
                f"{capabilities.series} model profile."
            )
        allowed = {"query", "event"}
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for search-event: {sorted(unknown)[0]}"
            )
        if "query" in arguments and "event" in arguments:
            raise OscilloscopeError(
                "search-event query cannot be combined with configure options"
            )
        if arguments.get("query") is True:
            if set(arguments) != {"query"}:
                raise OscilloscopeError("search-event query requires exactly query=true")
            return dict(arguments)
        if "query" in arguments:
            raise OscilloscopeError("search-event argument query must be exactly true")
        if "event" not in arguments or set(arguments) != {"event"}:
            raise OscilloscopeError("search-event configure requires exactly event")
        event = arguments["event"]
        if isinstance(event, bool) or not isinstance(event, int):
            raise OscilloscopeError("search-event argument event must be an integer")
        if event <= 0:
            raise OscilloscopeError("search-event argument event must be a positive integer")
        return dict(arguments)

    if command == "search-count":
        if set(arguments) != {"query"} or arguments.get("query") is not True:
            raise OscilloscopeError("search-count requires exactly query=true")
        return dict(arguments)

    configure_key = "enabled" if command == "search-state" else "mode"
    allowed = {"query", configure_key}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for {command}: {sorted(unknown)[0]}"
        )
    if arguments.get("query") is True:
        if set(arguments) != {"query"}:
            raise OscilloscopeError(
                f"{command} query cannot be combined with configure arguments"
            )
        return dict(arguments)
    if "query" in arguments:
        raise OscilloscopeError(f"{command} argument query must be exactly true")
    if set(arguments) != {configure_key}:
        raise OscilloscopeError(
            f"{command} configure requires exactly {configure_key}"
        )

    value = arguments[configure_key]
    if command == "search-state":
        if not isinstance(value, bool):
            raise OscilloscopeError("search-state argument enabled must be a boolean")
        return {"enabled": "true" if value else "false"}

    if not isinstance(value, str):
        raise OscilloscopeError("search-mode argument mode must be a string")
    canonical_modes = {
        "serial1",
        "serial2",
        "edge",
        "glitch",
        "runt",
        "transition",
        "peak",
    }
    if value not in canonical_modes:
        raise OscilloscopeError(
            "search-mode argument mode must be one of: serial1, serial2, edge, "
            "glitch, runt, transition, peak"
        )
    capabilities = capabilities_for_model_id(runtime.model)
    if value not in capabilities.search_modes:
        raise OscilloscopeError(
            f"Search mode {value!r} is not supported by the selected "
            f"{capabilities.series} model profile."
        )
    return dict(arguments)


def _normalize_serial_worker_arguments(
    command: str,
    arguments: dict[str, Any],
    capabilities: ScopeCapabilities | None = None,
) -> dict[str, Any]:
    if command not in {
        "serial-query",
        "serial-mode",
        "serial-display",
        "serial-uart",
        "serial-trigger-uart",
        "serial-trigger-i2c",
        "serial-trigger-spi",
        "serial-trigger-can",
        "serial-i2c",
        "serial-spi",
        "serial-can",
        "serial-lister-query",
        "serial-lister-display",
        "serial-lister-reference",
        "serial-lister-export",
    }:
        return arguments

    if command == "serial-lister-query":
        if arguments:
            raise OscilloscopeError("serial-lister-query accepts only an empty object")
        return {}
    if command == "serial-lister-display":
        allowed = {"query", "selection"}
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for {command}: {sorted(unknown)[0]}"
            )
        if arguments.get("query") is True:
            if set(arguments) != {"query"}:
                raise OscilloscopeError(
                    f"{command} query cannot be combined with configure arguments"
                )
            return {"query": True}
        if "query" in arguments:
            raise OscilloscopeError(f"{command} argument query must be exactly true")
        if set(arguments) != {"selection"} or not isinstance(
            arguments["selection"], str
        ):
            raise OscilloscopeError(
                f"{command} configure requires exactly selection"
            )
        if arguments["selection"] not in {"off", "bus1", "bus2", "all"}:
            raise OscilloscopeError(
                f"{command} argument selection must be one of: off, bus1, bus2, all"
            )
        return dict(arguments)
    if command == "serial-lister-reference":
        allowed = {"query", "reference"}
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for {command}: {sorted(unknown)[0]}"
            )
        if arguments.get("query") is True:
            if set(arguments) != {"query"}:
                raise OscilloscopeError(
                    f"{command} query cannot be combined with configure arguments"
                )
            return {"query": True}
        if "query" in arguments:
            raise OscilloscopeError(f"{command} argument query must be exactly true")
        if set(arguments) != {"reference"} or not isinstance(
            arguments["reference"], str
        ):
            raise OscilloscopeError(
                f"{command} configure requires exactly reference"
            )
        if arguments["reference"] not in {"trigger", "previous"}:
            raise OscilloscopeError(
                f"{command} argument reference must be one of: trigger, previous"
            )
        return dict(arguments)
    if command == "serial-lister-export":
        if set(arguments) != {"output"} or not isinstance(arguments["output"], str):
            raise OscilloscopeError(
                "serial-lister-export requires exactly a string output"
            )
        if not arguments["output"]:
            raise OscilloscopeError("serial-lister-export output must not be empty")
        return dict(arguments)

    if command in {"serial-trigger-i2c", "serial-trigger-spi", "serial-trigger-can"}:
        fields_by_command = {
            "serial-trigger-i2c": {"type", "address", "data", "data2", "qualifier"},
            "serial-trigger-spi": {"type", "width", "data"},
            "serial-trigger-can": {"type", "id", "id_mode", "data", "data_length"},
        }
        allowed = {"bus", "query"} | fields_by_command[command]
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for {command}: {sorted(unknown)[0]}"
            )
        query = arguments.get("query", False)
        if "query" in arguments and query is not True:
            raise OscilloscopeError(f"{command} argument query must be exactly true")
        validator = {
            "serial-trigger-i2c": validate_serial_i2c_trigger_request,
            "serial-trigger-spi": validate_serial_spi_trigger_request,
            "serial-trigger-can": validate_serial_can_trigger_request,
        }[command]
        values = {
            key: arguments.get(key) for key in fields_by_command[command]
        }
        canonical = validator(
            arguments.get("bus"), query=query, capabilities=capabilities, **values
        )
        normalized: dict[str, Any] = {"bus": canonical[0]}
        if query:
            normalized["query"] = True
        elif command == "serial-trigger-i2c":
            _, trigger_type, address, data, data2, qualifier = canonical
            normalized.update(type=trigger_type)
            for key, value in {
                "address": address, "data": data, "data2": data2, "qualifier": qualifier
            }.items():
                if value is not None:
                    normalized[key] = value
        elif command == "serial-trigger-spi":
            _, trigger_type, width, data = canonical
            normalized.update(type=trigger_type, width=width, data=data)
        else:
            _, trigger_type, id_value, id_mode, data, data_length = canonical
            normalized.update(type=trigger_type)
            for key, value in {
                "id": id_value, "id_mode": id_mode, "data": data,
                "data_length": data_length,
            }.items():
                if value is not None:
                    normalized[key] = value
        return normalized

    if command == "serial-trigger-uart":
        allowed = {"bus", "query", "type", "data", "qualifier"}
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for {command}: {sorted(unknown)[0]}"
            )
        query = arguments.get("query", False)
        if "query" in arguments and query is not True:
            raise OscilloscopeError(
                f"{command} argument query must be exactly true"
            )
        bus, trigger_type, data, qualifier = validate_serial_uart_trigger_request(
            arguments.get("bus"),
            query=query,
            type=arguments.get("type"),
            data=arguments.get("data"),
            qualifier=arguments.get("qualifier"),
            capabilities=capabilities,
        )
        normalized: dict[str, Any] = {"bus": bus}
        if query:
            normalized["query"] = True
        else:
            normalized.update(
                type=trigger_type,
                **(
                    {"data": data, "qualifier": qualifier}
                    if data is not None
                    else {}
                ),
            )
        return normalized

    if command in {"serial-uart", "serial-i2c", "serial-spi", "serial-can"}:
        fields_by_command = {
            "serial-uart": {"rx_source", "tx_source", "baud_rate", "data_bits", "parity", "polarity", "bit_order"},
            "serial-i2c": {"clock_source", "data_source", "address_size"},
            "serial-spi": {"clock_source", "mosi_source", "miso_source", "frame_source", "clock_slope", "bit_order", "word_width", "framing", "clock_timeout"},
            "serial-can": {"source", "baud_rate", "signal_definition", "sample_point"},
        }
        allowed = {"bus", "query"} | fields_by_command[command]
        unknown = set(arguments) - allowed
        if unknown:
            raise OscilloscopeError(
                f"unknown argument for {command}: {sorted(unknown)[0]}"
            )
        bus = arguments.get("bus")
        if isinstance(bus, bool) or not isinstance(bus, int):
            raise OscilloscopeError(f"{command} argument bus must be an integer")
        if arguments.get("query") is True:
            if set(arguments) != {"bus", "query"}:
                raise OscilloscopeError(
                    f"{command} query cannot be combined with configure arguments"
                )
            return dict(arguments)
        if "query" in arguments:
            raise OscilloscopeError(f"{command} argument query must be exactly true")
        fields = fields_by_command[command]
        if not any(field in arguments for field in fields):
            raise OscilloscopeError(
                f"{command} configure requires at least one setting"
            )
        for field, value in arguments.items():
            if field in {"rx_source", "tx_source", "clock_source", "data_source", "mosi_source", "miso_source", "frame_source", "source", "parity", "polarity", "bit_order", "address_size", "clock_slope", "framing", "signal_definition"} and not isinstance(value, str):
                raise OscilloscopeError(f"{command} argument {field} must be a string")
            if field in {"baud_rate", "data_bits", "word_width"} and (isinstance(value, bool) or not isinstance(value, int)):
                raise OscilloscopeError(f"{command} argument {field} must be an integer")
            if field in {"clock_timeout", "sample_point"} and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise OscilloscopeError(f"{command} argument {field} must be a number")
        return dict(arguments)

    if command == "serial-query":
        if set(arguments) != {"bus"}:
            raise OscilloscopeError("serial-query requires exactly bus")
        bus = arguments["bus"]
        if isinstance(bus, bool) or not isinstance(bus, int):
            raise OscilloscopeError("serial-query argument bus must be an integer")
        return dict(arguments)

    configure_key = "mode" if command == "serial-mode" else "enabled"
    allowed = {"bus", "query", configure_key}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for {command}: {sorted(unknown)[0]}"
        )
    bus = arguments.get("bus")
    if isinstance(bus, bool) or not isinstance(bus, int):
        raise OscilloscopeError(f"{command} argument bus must be an integer")
    if arguments.get("query") is True:
        if set(arguments) != {"bus", "query"}:
            raise OscilloscopeError(
                f"{command} query cannot be combined with configure arguments"
            )
        return dict(arguments)
    if "query" in arguments:
        raise OscilloscopeError(f"{command} argument query must be exactly true")
    if set(arguments) != {"bus", configure_key}:
        raise OscilloscopeError(
            f"{command} configure requires exactly bus and {configure_key}"
        )

    value = arguments[configure_key]
    if command == "serial-mode":
        if not isinstance(value, str):
            raise OscilloscopeError("serial-mode argument mode must be a string")
        return dict(arguments)
    if not isinstance(value, bool):
        raise OscilloscopeError(
            "serial-display argument enabled must be a boolean"
        )
    return {"bus": bus, "enabled": "true" if value else "false"}


def _normalize_save_export_worker_arguments(
    command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    configure_keys = {
        "save-pwd": "path",
        "save-filename": "name",
        "save-image-format": "format",
        "save-image-palette": "palette",
        "save-image-ink-saver": "enabled",
        "save-image-factors": "enabled",
        "save-waveform-format": "format",
        "save-waveform-length": "points",
    }
    start_commands = {"save-image", "save-waveform"}
    query_only_commands = {"save-waveform-length-max"}
    if command not in set(configure_keys) | start_commands | query_only_commands:
        return arguments

    if command in query_only_commands:
        if set(arguments) != {"query"} or arguments.get("query") is not True:
            raise OscilloscopeError(f"{command} requires exactly query=true")
        return {"query": True}

    if command in start_commands:
        if set(arguments) != {"filename"}:
            unknown = set(arguments) - {"filename"}
            if unknown:
                raise OscilloscopeError(
                    f"unknown argument for {command}: {sorted(unknown)[0]}"
                )
            raise OscilloscopeError(f"{command} requires exactly filename")
        filename = arguments["filename"]
        if not isinstance(filename, str):
            raise OscilloscopeError(f"{command} argument filename must be a string")
        validate_save_quoted_string(filename, label=f"{command} filename")
        return dict(arguments)

    configure_key = configure_keys[command]
    allowed = {"query", configure_key}
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for {command}: {sorted(unknown)[0]}"
        )
    if arguments.get("query") is True:
        if set(arguments) != {"query"}:
            raise OscilloscopeError(
                f"{command} query cannot be combined with configure arguments"
            )
        return {"query": True}
    if "query" in arguments:
        raise OscilloscopeError(f"{command} argument query must be exactly true")
    if set(arguments) != {configure_key}:
        raise OscilloscopeError(
            f"{command} configure requires exactly {configure_key}"
        )

    value = arguments[configure_key]
    if command == "save-pwd":
        if not isinstance(value, str):
            raise OscilloscopeError("save-pwd argument path must be a string")
        validate_save_quoted_string(value, label="Save path")
    elif command == "save-filename":
        if not isinstance(value, str):
            raise OscilloscopeError("save-filename argument name must be a string")
        validate_save_filename_base(value)
    elif command == "save-image-format":
        if not isinstance(value, str) or value not in SAVE_IMAGE_FORMATS:
            raise OscilloscopeError(
                "save-image-format argument format must be one of: "
                + ", ".join(SAVE_IMAGE_FORMATS)
            )
    elif command == "save-image-palette":
        if not isinstance(value, str) or value not in SAVE_IMAGE_PALETTES:
            raise OscilloscopeError(
                "save-image-palette argument palette must be one of: "
                + ", ".join(SAVE_IMAGE_PALETTES)
            )
    elif command in {"save-image-ink-saver", "save-image-factors"}:
        if not isinstance(value, bool):
            raise OscilloscopeError(f"{command} argument enabled must be a boolean")
        return {"enabled": "true" if value else "false"}
    elif command == "save-waveform-format":
        if not isinstance(value, str) or value not in SAVE_WAVEFORM_FORMATS:
            raise OscilloscopeError(
                "save-waveform-format argument format must be one of: "
                + ", ".join(SAVE_WAVEFORM_FORMATS)
            )
    else:
        if isinstance(value, bool) or not isinstance(value, int):
            raise OscilloscopeError(
                "save-waveform-length argument points must be an integer"
            )
        validate_save_waveform_length(value)
    return dict(arguments)


def _serial_uart_trigger_worker_namespace(
    arguments: dict[str, Any], runtime: WorkerRuntime, job_dir: Path | None
) -> argparse.Namespace:
    """Build a serial trigger runtime namespace without CLI parsing."""

    namespace = argparse.Namespace(
        command=arguments["command"],
        bus=arguments["bus"],
        query=arguments.get("query", False),
        type=arguments.get("type"),
        data=arguments.get("data"),
        qualifier=arguments.get("qualifier"),
        data2=arguments.get("data2"),
        address=arguments.get("address"),
        width=arguments.get("width"),
        id=arguments.get("id"),
        id_mode=arguments.get("id_mode"),
        data_length=arguments.get("data_length"),
        simulate=runtime.mode == "simulate",
        dry_run=False,
        live=runtime.mode == "live",
        model=runtime.model,
        resource=runtime.resource,
        json=True,
        log_scpi=False,
        visa_library=None,
    )
    if job_dir is not None:
        _apply_worker_job_paths(namespace, job_dir)
    return namespace


def _normalize_math_worker_arguments(
    command: str, arguments: dict[str, Any], runtime: WorkerRuntime
) -> dict[str, Any]:
    if command not in _MATH_WORKER_ARGUMENTS:
        return arguments

    allowed = _MATH_WORKER_ARGUMENTS[command]
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"unknown argument for {command}: {sorted(unknown)[0]}"
        )
    capabilities = capabilities_for_model_id(runtime.model)

    if command == "fft":
        configure_keys = allowed - {"function", "query"}
        configure_arguments = configure_keys & set(arguments)
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError("fft argument query must be exactly true")
            if configure_arguments:
                raise OscilloscopeError(
                    "fft query cannot be combined with configure arguments"
                )
            fft_query_commands(
                arguments.get("function"), capabilities=capabilities
            )
            if capabilities.supports_advanced_fft:
                fft_advanced_query_commands(
                    arguments.get("function"), capabilities=capabilities
                )
            return dict(arguments)
        if "source_channel" not in arguments:
            raise OscilloscopeError(
                "fft configure requires source_channel unless query is used"
            )
        canonical_values = {
            "fft_operation": FFT_OPERATIONS,
            "gate": FFT_GATES,
            "phase_reference": FFT_PHASE_REFERENCES,
            "detection_type": FFT_DETECTION_TYPES,
            "units": ("decibel", "vrms"),
            "window": (
                "rectangular",
                "hanning",
                "flattop",
                "bharris",
                "bartlett",
            ),
            "display": ("on", "off"),
        }
        for key, choices in canonical_values.items():
            if key in arguments and arguments[key] not in choices:
                raise OscilloscopeError(
                    f"fft argument {key} must be one of: {', '.join(choices)}"
                )
        fft_configure_commands(
            arguments.get("function"),
            arguments["source_channel"],
            units=arguments.get("units"),
            window=arguments.get("window"),
            center_hz=arguments.get("center_hz"),
            span_hz=arguments.get("span_hz"),
            display=(
                None
                if "display" not in arguments
                else arguments["display"] == "on"
            ),
            fft_operation=arguments.get("fft_operation", "fft"),
            start_hz=arguments.get("start_hz"),
            stop_hz=arguments.get("stop_hz"),
            gate=arguments.get("gate"),
            phase_reference=arguments.get("phase_reference"),
            detection_type=arguments.get("detection_type"),
            detection_points=arguments.get("detection_points"),
            capabilities=capabilities,
        )
        return dict(arguments)

    if command == "math-composite-source":
        configure_keys = ("operation", "source1", "source2")
        configure_arguments = {
            key: arguments[key] for key in configure_keys if key in arguments
        }
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(
                    "math-composite-source argument query must be exactly true"
                )
            if configure_arguments:
                raise OscilloscopeError(
                    "math-composite-source query cannot be combined with "
                    "configure arguments"
                )
            math_composite_source_query_commands(capabilities=capabilities)
            return dict(arguments)
        if len(configure_arguments) != len(configure_keys):
            raise OscilloscopeError(
                "math-composite-source configure requires operation, "
                "source1, and source2"
            )
        math_composite_source_commands(
            arguments["operation"],
            arguments["source1"],
            arguments["source2"],
            capabilities=capabilities,
        )
        return dict(arguments)

    function = arguments.get("function")
    if not isinstance(function, int) or isinstance(function, bool):
        raise OscilloscopeError(f"{command} argument function must be an integer")

    if command == "math-display":
        actions = [key for key in ("on", "off", "query") if key in arguments]
        for key in actions:
            if arguments[key] is not True:
                raise OscilloscopeError(
                    f"math-display argument {key} must be exactly true"
                )
        if len(actions) != 1:
            raise OscilloscopeError(
                "math-display requires exactly one of on, off, or query"
            )
        if actions[0] == "query":
            math_display_query(function, capabilities=capabilities)
        else:
            math_display_command(
                function, actions[0] == "on", capabilities=capabilities
            )
        return dict(arguments)

    if command == "math-clear":
        math_clear_command(function, capabilities=capabilities)
        return dict(arguments)

    if command == "math-operator":
        configure_keys = ("operation", "source1", "source2")
        configure_arguments = {
            key: arguments[key] for key in configure_keys if key in arguments
        }
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(
                    "math-operator argument query must be exactly true"
                )
            if configure_arguments:
                raise OscilloscopeError(
                    "math-operator query cannot be combined with configure arguments"
                )
            math_operator_query_commands(function, capabilities=capabilities)
            return dict(arguments)
        if len(configure_arguments) != len(configure_keys):
            raise OscilloscopeError(
                "math-operator configure requires operation, source1, and source2"
            )
        math_operator_commands(
            function,
            arguments["operation"],
            arguments["source1"],
            arguments["source2"],
            capabilities=capabilities,
        )
        return dict(arguments)

    if command == "math-transform":
        configure_keys = (
            "operation",
            "source",
            "input_offset",
            "gain",
            "linear_offset",
        )
        configure_arguments = {
            key: arguments[key] for key in configure_keys if key in arguments
        }
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(
                    "math-transform argument query must be exactly true"
                )
            if configure_arguments:
                raise OscilloscopeError(
                    "math-transform query cannot be combined with configure arguments"
                )
            math_transform_query_commands(function, capabilities=capabilities)
            return dict(arguments)
        if "operation" not in arguments or "source" not in arguments:
            raise OscilloscopeError(
                "math-transform configure requires operation and source"
            )
        math_transform_commands(
            function,
            arguments["operation"],
            arguments["source"],
            input_offset=arguments.get("input_offset"),
            gain=arguments.get("gain"),
            linear_offset=arguments.get("linear_offset"),
            capabilities=capabilities,
        )
        return dict(arguments)

    if command == "math-filter":
        configure_keys = (
            "operation",
            "source",
            "cutoff_hz",
            "average_count",
            "smooth_points",
        )
        configure_arguments = {
            key: arguments[key] for key in configure_keys if key in arguments
        }
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(
                    "math-filter argument query must be exactly true"
                )
            if configure_arguments:
                raise OscilloscopeError(
                    "math-filter query cannot be combined with configure arguments"
                )
            math_filter_query_commands(function, capabilities=capabilities)
            return dict(arguments)
        if "operation" not in arguments or "source" not in arguments:
            raise OscilloscopeError(
                "math-filter configure requires operation and source"
            )
        math_filter_commands(
            function,
            arguments["operation"],
            arguments["source"],
            cutoff_hz=arguments.get("cutoff_hz"),
            average_count=arguments.get("average_count"),
            smooth_points=arguments.get("smooth_points"),
            capabilities=capabilities,
        )
        return dict(arguments)

    if command == "math-visualization":
        configure_keys = (
            "operation",
            "source",
            "source2",
            "measurement",
            "measurement_slot",
        )
        configure_arguments = {
            key: arguments[key] for key in configure_keys if key in arguments
        }
        if "query" in arguments:
            if arguments["query"] is not True:
                raise OscilloscopeError(
                    "math-visualization argument query must be exactly true"
                )
            if configure_arguments:
                raise OscilloscopeError(
                    "math-visualization query cannot be combined with "
                    "configure arguments"
                )
            math_visualization_query_commands(
                function, capabilities=capabilities
            )
            return dict(arguments)
        if "operation" not in arguments:
            raise OscilloscopeError(
                "math-visualization configure requires operation"
            )
        math_visualization_commands(
            function,
            arguments["operation"],
            source=arguments.get("source"),
            source2=arguments.get("source2"),
            measurement=arguments.get("measurement"),
            measurement_slot=arguments.get("measurement_slot"),
            capabilities=capabilities,
        )
        return dict(arguments)

    setters = {
        key: arguments[key]
        for key in ("scale", "range", "offset")
        if key in arguments
    }
    if "query" in arguments:
        if arguments["query"] is not True:
            raise OscilloscopeError(
                "math-vertical argument query must be exactly true"
            )
        if setters:
            raise OscilloscopeError(
                "math-vertical query cannot be combined with configure arguments"
            )
        math_vertical_query_commands(function, capabilities=capabilities)
        return dict(arguments)
    if not setters:
        raise OscilloscopeError(
            "math-vertical configure requires scale, range, or offset"
        )
    for key, value in setters.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OscilloscopeError(
                f"math-vertical argument {key} must be a finite number"
            )
        try:
            finite = math.isfinite(float(value))
        except (TypeError, ValueError, OverflowError):
            finite = False
        if not finite:
            raise OscilloscopeError(
                f"math-vertical argument {key} must be a finite number"
            )
        if key in {"scale", "range"} and value <= 0:
            raise OscilloscopeError(
                f"math-vertical argument {key} must be greater than zero"
            )
    math_vertical_commands(
        function,
        scale=setters.get("scale"),
        range_value=setters.get("range"),
        offset=setters.get("offset"),
        capabilities=capabilities,
    )
    return dict(arguments)


def arguments_to_argv(arguments: dict[str, Any]) -> list[str]:
    argv: list[str] = []
    for key, value in arguments.items():
        option = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                argv.append(option)
            continue
        if isinstance(value, list):
            for item in value:
                argv.extend([option, str(item)])
            continue
        if value is None:
            continue
        argv.extend([option, str(value)])
    return argv


def _apply_worker_job_paths(args: argparse.Namespace, job_dir: Path) -> None:
    command = args.command
    if command == "capture":
        csv_path = _worker_path(job_dir, getattr(args, "csv_path", None), "capture.csv")
        meta_value = getattr(args, "meta_path", None)
        meta_path = _worker_path(job_dir, meta_value, "capture_meta.json")
        setattr(args, "csv_path", str(csv_path))
        setattr(args, "meta_path", str(meta_path))
        plot_value = getattr(args, "plot_path", None)
        if plot_value is not None:
            setattr(args, "plot_path", str(_worker_path(job_dir, plot_value, None)))
    elif command == "screenshot":
        if not getattr(args, "query_hardcopy", False):
            default_name = "screen.png" if getattr(args, "format", None) in {None, "png"} else "screen.bmp"
            output_path = _worker_path(
                job_dir, getattr(args, "output_path", None), default_name
            )
            setattr(args, "output_path", str(output_path))
    elif command in {
        "capture-batch",
        "measure-log",
        "measure-until",
        "triggered-measure-loop",
        "triggered-capture-series",
        "smoke",
        "acquisition-check",
    }:
        output_dir = _worker_path(job_dir, getattr(args, "output_dir", None), ".")
        setattr(args, "output_dir", str(output_dir))
    elif command == "segmented-capture":
        setattr(args, "output_dir", str(job_dir / "segmented_capture"))
    elif command == "serial-lister-export":
        output_path = _worker_path(job_dir, args.output_path, None)
        setattr(args, "output_path", str(output_path))


def _worker_path(job_dir: Path, value: Any, default_name: str | None) -> Path:
    if value is None:
        if default_name is None:
            raise OscilloscopeError("worker output path default is unavailable")
        return job_dir if default_name == "." else job_dir / default_name
    path = Path(str(value))
    return path if path.is_absolute() else job_dir / path
