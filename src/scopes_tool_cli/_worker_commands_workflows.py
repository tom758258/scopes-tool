"""Worker argument normalization for finite workflow commands."""

from __future__ import annotations

import math
from typing import Any

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.segmented_capture import (
    SegmentedCaptureRequest,
    validate_segmented_capture_request,
)
from scopes_tool_core.waveform import SUPPORTED_WAVEFORM_POINTS


_OPTIONAL_PERSISTENCE_COMMANDS = frozenset(
    {
        "measure-log",
        "measure-until",
        "triggered-measure-loop",
        "capture-monitor",
    }
)


def _normalize_optional_persistence_worker_arguments(
    command: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if command not in _OPTIONAL_PERSISTENCE_COMMANDS:
        return arguments
    values = dict(arguments)
    if "save_results" in values and not isinstance(values["save_results"], bool):
        raise OscilloscopeError(f"{command} argument save_results must be a boolean")
    return values


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
        "output_dir",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"capture-batch unknown argument: {sorted(unknown)[0]}"
        )
    return dict(arguments)


def _normalize_capture_until_worker_arguments(
    command: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if command != "capture-until":
        return arguments
    allowed = {
        "channel",
        "condition_channel",
        "points",
        "format",
        "metric",
        "operator",
        "threshold",
        "count",
        "timeout_seconds",
        "interval_seconds",
        "output_dir",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"capture-until unknown argument: {sorted(unknown)[0]}"
        )
    for required in (
        "channel",
        "condition_channel",
        "metric",
        "operator",
        "threshold",
        "timeout_seconds",
    ):
        if required not in arguments:
            raise OscilloscopeError(f"capture-until requires argument {required}")
    channels = arguments["channel"]
    if not isinstance(channels, list) or not channels:
        raise OscilloscopeError(
            "capture-until argument channel must be a non-empty array"
        )
    condition_channel = arguments["condition_channel"]
    if isinstance(condition_channel, bool) or not isinstance(condition_channel, int):
        raise OscilloscopeError(
            "capture-until argument condition_channel must be an integer"
        )
    count = arguments.get("count", 1)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 255:
        raise OscilloscopeError(
            "capture-until argument count must be an integer between 1 and 255"
        )
    return dict(arguments)


def _normalize_capture_monitor_worker_arguments(
    command: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if command != "capture-monitor":
        return arguments
    allowed = {
        "channel",
        "points",
        "format",
        "count",
        "interval_seconds",
        "retention_points",
        "save_results",
        "output_dir",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise OscilloscopeError(
            f"capture-monitor unknown argument: {sorted(unknown)[0]}"
        )
    for required in ("channel", "count"):
        if required not in arguments:
            raise OscilloscopeError(f"capture-monitor requires argument {required}")
    channels = arguments["channel"]
    if not isinstance(channels, list) or not channels:
        raise OscilloscopeError(
            "capture-monitor argument channel must be a non-empty array"
        )
    count = arguments["count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise OscilloscopeError(
            "capture-monitor argument count must be an integer of at least 1"
        )
    if "retention_points" in arguments:
        retention = arguments["retention_points"]
        if isinstance(retention, bool) or not isinstance(retention, int):
            raise OscilloscopeError(
                "capture-monitor argument retention_points must be an integer"
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
        "output_dir",
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
        "output_dir": arguments.get("output_dir"),
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
        "output_dir",
        "save_results",
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
        "output_dir",
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
        "output_dir",
        "save_results",
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
