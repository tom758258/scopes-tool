"""Worker command contract and CLI adaptation helpers."""

from __future__ import annotations

import argparse
from typing import Any

from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.capabilities import capabilities_for_model_id
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
from scopes_tool_core.wgen import (
    WGEN_LOADS,
    validate_wgen_amplitude,
    validate_wgen_frequency,
    validate_wgen_function,
    validate_wgen_offset,
)

from . import cli as scope_cli
from . import parser as cli_parser
from . import preflight, runtime as cli_runtime

from ._worker_commands_math import _MATH_DOMAIN_COMMANDS, _normalize_math_worker_arguments
from ._worker_commands_serial_search import (
    _normalize_search_worker_arguments,
    _normalize_serial_search_worker_arguments,
    _normalize_serial_worker_arguments,
    _serial_uart_trigger_worker_namespace,
)
from ._worker_commands_trigger import (
    _normalize_external_trigger_probe_worker_arguments,
    _normalize_external_trigger_range_worker_arguments,
    _normalize_external_trigger_settings_worker_arguments,
    _normalize_external_trigger_units_worker_arguments,
    _normalize_trigger_common_worker_arguments,
    _normalize_trigger_delay_worker_arguments,
    _normalize_trigger_edge_burst_worker_arguments,
    _normalize_trigger_edge_external_level_worker_arguments,
    _normalize_trigger_edge_level_worker_arguments,
    _normalize_trigger_edge_slope_worker_arguments,
    _normalize_trigger_edge_source_worker_arguments,
    _normalize_trigger_edge_worker_arguments,
    _normalize_trigger_glitch_worker_arguments,
    _normalize_trigger_holdoff_worker_arguments,
    _normalize_trigger_or_worker_arguments,
    _normalize_trigger_pattern_worker_arguments,
    _normalize_trigger_runt_worker_arguments,
    _normalize_trigger_setup_hold_worker_arguments,
    _normalize_trigger_transition_worker_arguments,
    _normalize_trigger_tv_worker_arguments,
)
from ._worker_commands_workflows import (
    _normalize_capture_batch_worker_arguments,
    _normalize_capture_monitor_worker_arguments,
    _normalize_capture_until_worker_arguments,
    _normalize_measure_until_worker_arguments,
    _normalize_optional_persistence_worker_arguments,
    _normalize_segmented_capture_worker_arguments,
    _normalize_segmented_memory_worker_arguments,
    _normalize_triggered_capture_series_worker_arguments,
    _normalize_triggered_measure_loop_worker_arguments,
)


WORKER_SCHEMA_VERSION = 2

_CORE_WORKFLOW_COMMANDS = {
    "segmented-capture",
    "measure-log",
    "measure-until",
    "capture-batch",
    "capture-until",
    "capture-monitor",
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
    "single-wait",
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
    "capture-until",
    "capture-monitor",
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
    "serial-status",
    "serial-mode",
    "serial-enable",
    "serial-disable",
    "serial-uart-set",
    "serial-uart-show",
    "serial-trigger-uart-set",
    "serial-trigger-uart-show",
    "serial-trigger-i2c-set",
    "serial-trigger-i2c-show",
    "serial-trigger-spi-set",
    "serial-trigger-spi-show",
    "serial-trigger-can-set",
    "serial-trigger-can-show",
    "serial-i2c-set",
    "serial-i2c-show",
    "serial-spi-set",
    "serial-spi-show",
    "serial-can-set",
    "serial-can-show",
    "serial-lister-status",
    "serial-lister-display",
    "serial-lister-reference",
    "serial-data",
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
    "timebase-reference",
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
    arguments = _normalize_optional_persistence_worker_arguments(command, arguments)
    arguments = _normalize_capture_batch_worker_arguments(command, arguments)
    arguments = _normalize_capture_until_worker_arguments(command, arguments)
    arguments = _normalize_capture_monitor_worker_arguments(command, arguments)
    arguments = _normalize_segmented_memory_worker_arguments(command, arguments)
    arguments = _normalize_segmented_capture_worker_arguments(command, arguments)
    arguments = _normalize_triggered_measure_loop_worker_arguments(command, arguments)
    arguments = _normalize_triggered_capture_series_worker_arguments(command, arguments)
    arguments = _normalize_measure_until_worker_arguments(command, arguments)
    job_id = body.get("job_id")
    if job_id is not None and not isinstance(job_id, str):
        raise OscilloscopeError("job_id must be a string when provided")
    return command, arguments, job_id


_REQUIRED_WORKER_OUTPUT_ARGUMENTS = {
    "capture": ("csv", "meta"),
    "screenshot": ("output",),
    "capture-batch": ("output_dir",),
    "capture-until": ("output_dir",),
    "capture-monitor": ("output_dir",),
    "measure-log": ("output_dir",),
    "measure-until": ("output_dir",),
    "triggered-measure-loop": ("output_dir",),
    "triggered-capture-series": ("output_dir",),
    "segmented-capture": ("output_dir",),
    "smoke": ("output_dir",),
    "acquisition-check": ("output_dir",),
}


def _validate_required_worker_outputs(
    command: str, arguments: dict[str, Any]
) -> None:
    required = _REQUIRED_WORKER_OUTPUT_ARGUMENTS.get(command)
    if required is None:
        return
    if command == "screenshot" and arguments.get("query_hardcopy") is True:
        return
    if command in {
        "measure-log",
        "measure-until",
        "triggered-measure-loop",
        "capture-monitor",
    }:
        if arguments.get("save_results", True) is False:
            return
    for key in required:
        value = arguments.get(key)
        if not isinstance(value, str) or not value:
            raise OscilloscopeError(f"{command} requires argument {key}")


def parse_domain_command(
    command: str,
    arguments: dict[str, Any],
    runtime: WorkerRuntime,
) -> argparse.Namespace:
    arguments = _normalize_optional_persistence_worker_arguments(command, arguments)
    arguments = _normalize_capture_batch_worker_arguments(command, arguments)
    arguments = _normalize_capture_until_worker_arguments(command, arguments)
    arguments = _normalize_capture_monitor_worker_arguments(command, arguments)
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
    arguments = _normalize_wgen_worker_arguments(
        command, arguments, capabilities_for_model_id(runtime.model).series
    )
    arguments = _normalize_serial_worker_arguments(
        command, arguments, capabilities_for_model_id(runtime.model)
    )
    if command in {
        "serial-trigger-uart-set", "serial-trigger-uart-show",
        "serial-trigger-i2c-set", "serial-trigger-i2c-show",
        "serial-trigger-spi-set", "serial-trigger-spi-show",
        "serial-trigger-can-set", "serial-trigger-can-show",
    }:
        arguments = {"command": command, **arguments}
        return _serial_uart_trigger_worker_namespace(arguments, runtime)
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
    _validate_required_worker_outputs(command, arguments)
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
    dry_args = argparse.Namespace(
        **{**vars(parsed), "dry_run": True, "simulate": False, "live": False}
    )
    scope_cli._dry_run_payload(dry_args)
    return parsed


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
    command: str, arguments: dict[str, Any], series: str | None = None
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
        validate_wgen_frequency(value, series=series)
    elif command == "wgen-voltage":
        validate_wgen_amplitude(value, series=series)
    elif command == "wgen-offset":
        validate_wgen_offset(value, series=series)
    elif not isinstance(value, str) or value not in WGEN_LOADS:
        raise OscilloscopeError(
            "wgen-load argument load must be one of: one-meg, fifty"
        )
    return dict(arguments)


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
        allowed = {"filename", "source_channel"} if command == "save-waveform" else {"filename"}
        if "filename" not in arguments or set(arguments) - allowed:
            unknown = set(arguments) - allowed
            if unknown:
                raise OscilloscopeError(
                    f"unknown argument for {command}: {sorted(unknown)[0]}"
                )
            raise OscilloscopeError(f"{command} requires exactly filename")
        if "source_channel" in arguments:
            source = arguments["source_channel"]
            if isinstance(source, bool) or not isinstance(source, int):
                raise OscilloscopeError("save-waveform source_channel must be an integer")
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


def arguments_to_argv(arguments: dict[str, Any]) -> list[str]:
    argv: list[str] = []
    for key, value in arguments.items():
        if key == "save_results":
            if value is False:
                argv.append("--no-save")
            continue
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
