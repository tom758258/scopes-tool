"""CLI runtime and scope-opening infrastructure."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from scopes_tool_core.capabilities import (
    ScopeCapabilities,
    capabilities_for_model_id,
)
from scopes_tool_core.drivers import scope_for_physical_model
from scopes_tool_core.errors import OscilloscopeError, UnsupportedModelError
from scopes_tool_core.identity import physical_model_for_id
from scopes_tool_core.run_config import RunModeOptions, resolve_resource, resolve_run_mode
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.search import SEARCH_MODES
from scopes_tool_core.serial import SERIAL_MODES
from scopes_tool_core.simulator_backend import SimulatorBackend
from scopes_tool_core.simulator_config import simulator_backend_kwargs

WORKER_IDN_TIMEOUT_MS = 2000
_DRIVER_OPTIONAL_LIVE_COMMANDS = {"identify"}
_LAST_BACKEND = None
_JSON_RECORD: dict[str, object] | None = None


def _resolve_cli_mode(args: argparse.Namespace) -> str:
    _validate_cursor_auto_args(args)
    _validate_measure_log_args(args)
    if hasattr(args, "model"):
        physical_model_for_id(args.model)
    return resolve_run_mode(_run_mode_options(args))

def _validate_cursor_auto_args(args: argparse.Namespace) -> None:
    if getattr(args, "command", None) != "cursor":
        return
    setting_cursor = not getattr(args, "cursor_query", False) and not getattr(args, "cursor_off", False)
    if getattr(args, "auto_timebase", False) and not setting_cursor:
        raise OscilloscopeError("--auto-timebase is only valid when setting cursor positions")
    if not getattr(args, "auto_vertical", False):
        return
    if not setting_cursor:
        raise OscilloscopeError("--auto-vertical is only valid when setting cursor positions")
    if getattr(args, "source_channel", None) is None or getattr(args, "x2", None) is None:
        raise OscilloscopeError(
            "--auto-vertical requires --source-channel, --x1, and --x2"
        )
    if getattr(args, "y1", None) is None and getattr(args, "y2", None) is None:
        raise OscilloscopeError("--auto-vertical requires --y1 or --y2")

def _validate_measure_log_args(args: argparse.Namespace) -> None:
    if getattr(args, "command", None) != "measure-log":
        return
    if args.count is None and args.duration_seconds is None:
        raise OscilloscopeError(
            "measure-log requires --count or --duration-seconds so the run is finite"
        )
    for value in args.pair:
        parts = value.split(":")
        if len(parts) != 2:
            raise OscilloscopeError("--pair must use SRC:REF, for example 1:2")
        try:
            source = int(parts[0])
            reference = int(parts[1])
        except ValueError as exc:
            raise OscilloscopeError("--pair channels must be integers") from exc
        if source == reference:
            raise OscilloscopeError("--pair source and reference channels must differ")

def _open_scope(args: argparse.Namespace, resource: str) -> Oscilloscope:
    global _LAST_BACKEND
    mode = _resolve_cli_mode(args)
    if mode == "simulate":
        backend = _make_simulator_backend(args, resource)
        _LAST_BACKEND = backend
        return Oscilloscope(backend)
    opened_scope = Oscilloscope.open(
        resource,
        visa_library=args.visa_library,
    )
    _LAST_BACKEND = getattr(opened_scope, "backend", None)
    try:
        scope = opened_scope
        if getattr(args, "_worker_live_validation", False):
            scope = _validate_worker_live_identity(args, scope)
        elif isinstance(scope, Oscilloscope):
            if args.command != "segmented-capture":
                scope = _select_one_shot_live_driver(args, scope)
        if _JSON_RECORD is not None:
            _JSON_RECORD["backend"] = getattr(scope.backend, "backend", None)
        return scope
    except Exception:
        try:
            opened_scope.close()
        except Exception:
            pass
        raise

def _select_one_shot_live_driver(
    args: argparse.Namespace,
    scope: Oscilloscope,
) -> Oscilloscope:
    try:
        idn = scope.query_idn()
        selected_scope = scope_for_physical_model(
            idn.physical_model,
            scope.backend,
            existing_scope=scope,
        )
    except UnsupportedModelError:
        if args.command not in _DRIVER_OPTIONAL_LIVE_COMMANDS:
            raise
        selected_scope = scope
        idn = scope.idn

    if idn is not None:
        selected_scope.idn = idn
        selected_scope.capabilities = scope.capabilities
        selected_scope._preloaded_idn = idn
    return selected_scope

def _validate_worker_live_identity(
    args: argparse.Namespace,
    scope: Oscilloscope,
) -> Oscilloscope:
    expected = physical_model_for_id(args.model)
    scope.scpi.set_timeout(WORKER_IDN_TIMEOUT_MS)
    idn = scope.query_idn()
    selected_scope = scope_for_physical_model(
        idn.physical_model,
        scope.backend,
        existing_scope=scope,
    )
    selected_scope.idn = idn
    selected_scope._preloaded_idn = idn
    _json_record_scope(selected_scope, idn)
    if idn.model_id != expected.model_id:
        raise OscilloscopeError(
            "identity_mismatch: "
            f"expected_model={expected.model_id}; actual_idn={idn.raw}"
        )
    return selected_scope

def _make_simulator_backend(args: argparse.Namespace, resource: str) -> SimulatorBackend:
    kwargs = simulator_backend_kwargs(
        _run_mode_options(args),
        resource,
        capabilities_for_model_id(args.model),
    )
    return SimulatorBackend(**kwargs)

def _run_mode_options(args: argparse.Namespace) -> RunModeOptions:
    planning_model_id = (
        getattr(args, "model", "keysight-dsox4024a")
        if bool(getattr(args, "simulate", False))
        or bool(getattr(args, "dry_run", False))
        else None
    )
    expected_model_id = (
        getattr(args, "model", "keysight-dsox4024a")
        if bool(getattr(args, "_worker_live_validation", False))
        else None
    )
    return RunModeOptions(
        simulate=bool(getattr(args, "simulate", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
        live=bool(getattr(args, "live", False)),
        planning_physical_model_id=planning_model_id,
        expected_physical_model_id=expected_model_id,
        simulate_signals=tuple(getattr(args, "simulate_signals", ()) or ()),
        simulate_preset=getattr(args, "simulate_preset", None),
        simulate_scenario=getattr(args, "simulate_scenario", None),
        simulate_system_errors=tuple(getattr(args, "simulate_system_errors", ()) or ()),
        simulate_binary_transfer_failure=bool(
            getattr(args, "simulate_binary_transfer_failure", False)
        ),
        simulate_invalid_measurement_channels=tuple(
            getattr(args, "simulate_invalid_measurement_channels", ()) or ()
        ),
        simulate_display_off_channels=tuple(
            getattr(args, "simulate_display_off_channels", ()) or ()
        ),
    )

def _backend_history() -> list[str]:
    if _LAST_BACKEND is None:
        return []
    return list(getattr(_LAST_BACKEND, "history", []))

def _capabilities_json(capabilities: ScopeCapabilities | None) -> dict[str, object] | None:
    if capabilities is None:
        return None
    return {
        "series": capabilities.series,
        "analog_channels": capabilities.analog_channels,
        "default_waveform_points": capabilities.default_waveform_points,
        "safe_max_waveform_points": capabilities.safe_max_waveform_points,
        "supports_word_format": capabilities.supports_word_format,
        "supports_raw_points_mode": capabilities.supports_raw_points_mode,
        "supports_measurements": capabilities.supports_measurements,
        "supports_delay_measurement": capabilities.supports_delay_measurement,
        "supports_measure_results_dump": capabilities.supports_measure_results_dump,
        "supports_demo": capabilities.supports_demo,
        "demo_functions": sorted(capabilities.demo_functions),
        "math_function_count": capabilities.math_function_count,
        "supports_math_goft": capabilities.supports_math_goft,
        "math_filter_operations": sorted(capabilities.math_filter_operations),
        "math_visualization_operations": sorted(
            capabilities.math_visualization_operations
        ),
        "supports_advanced_fft": capabilities.supports_advanced_fft,
        "supports_screenshot": capabilities.supports_screenshot,
        "supports_screenshot_format_pack": capabilities.supports_screenshot_format_pack,
        "supports_segmented_memory": capabilities.supports_segmented_memory,
        "segmented_max_segments": capabilities.segmented_max_segments,
        "supports_serial_decode": capabilities.supports_serial_decode,
        "serial_bus_count": capabilities.serial_bus_count,
        "serial_modes": [
            mode for mode in SERIAL_MODES if mode in capabilities.serial_modes
        ],
        "reference_waveforms": capabilities.reference_waveforms,
        "supports_channel_label": capabilities.supports_channel_label,
        "channel_label_max_length": capabilities.channel_label_max_length,
        "supports_display_label": capabilities.supports_display_label,
        "supports_annotation": capabilities.supports_annotation,
        "supports_annotation_position": capabilities.supports_annotation_position,
        "annotation_slots": capabilities.annotation_slots,
        "supports_indexed_annotation": capabilities.supports_indexed_annotation,
        "supports_50_ohm_impedance": capabilities.supports_50_ohm_impedance,
        "supports_search_basic": capabilities.supports_search_basic,
        "supports_search_event_navigation": capabilities.supports_search_event_navigation,
        "search_modes": [mode for mode in SEARCH_MODES if mode in capabilities.search_modes],
    }

def _json_record_scope(scope: Oscilloscope, idn) -> None:
    if _JSON_RECORD is None:
        return
    _JSON_RECORD["idn"] = _idn_object_json(idn)
    _JSON_RECORD["capabilities"] = _capabilities_json(scope.capabilities)
    _JSON_RECORD["backend"] = getattr(scope.backend, "backend", None)

def _idn_object_json(idn) -> dict[str, str | None]:
    return {
        "raw": idn.raw,
        "vendor": idn.vendor,
        "model": idn.model,
        "serial": idn.serial,
        "firmware": idn.firmware,
        "series": idn.series,
    }

def _json_update_result(**values: object) -> None:
    if _JSON_RECORD is None:
        return
    result = _JSON_RECORD.setdefault("result", {})
    if isinstance(result, dict):
        result.update(values)

def _json_set_files(files: list[dict[str, object]]) -> None:
    if _JSON_RECORD is not None:
        _JSON_RECORD["files"] = files

def _json_record_system_error(entry) -> None:
    data = _system_error_json(entry)
    if _JSON_RECORD is not None:
        _JSON_RECORD["system_error"] = data

def _system_error_json(entry) -> dict[str, object]:
    return {
        "code": entry.code,
        "message": entry.message,
        "raw": entry.raw,
        "is_error": entry.is_error,
    }

def _scope_backend_json(scope: Oscilloscope) -> dict[str, object]:
    return {
        "backend": getattr(scope.backend, "backend", None),
        "timeout_ms": getattr(scope.backend, "timeout", None),
    }

def _print_session_header(scope: Oscilloscope, resource: str) -> None:
    print(f"Resource: {resource}")
    backend = getattr(scope.backend, "backend", None)
    if backend is not None:
        print(f"PyVISA backend: {backend}")
    timeout = getattr(scope.backend, "timeout", None)
    if timeout is not None:
        print(f"Timeout ms: {timeout}")

def _require_resource(args: argparse.Namespace) -> str | None:
    mode = _resolve_cli_mode(args)
    resource = resolve_resource(mode, args.resource, args.model, os.environ)
    if resource:
        return resource

    print(
        "error: --resource is required unless SCOPES_TOOL_RESOURCE is set",
        file=sys.stderr,
    )
    return None

def _configure_scpi_logging(args: argparse.Namespace) -> None:
    if args.log_scpi:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
