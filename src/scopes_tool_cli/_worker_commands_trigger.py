"""Worker argument normalization for Trigger commands."""

from __future__ import annotations

import math
from typing import Any

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.channel import validate_analog_channel
from scopes_tool_core.errors import OscilloscopeError


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
