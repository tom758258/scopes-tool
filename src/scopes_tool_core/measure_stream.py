"""Native, read-only measurement stream cycles (no persistence or transport)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import time
from typing import Callable, Mapping

from .capabilities import ScopeCapabilities, operation_supported
from .errors import OscilloscopeError
from .measurements import (
    is_pair_measurement_item,
    measurement_query,
    normalize_measurement_item,
    pair_measurement_query,
)
from .operation_types import MeasureRequest
from .operations import _measurement_query_kwargs
from .planning import resolve_pair_measurement_channels, resolve_single_measurement_channel
from .scope import Oscilloscope


@dataclass(frozen=True)
class StreamField:
    field_id: str
    request: MeasureRequest


@dataclass(frozen=True)
class MeasureStreamOptions:
    fields: tuple[StreamField, ...]
    count: int | None
    interval_seconds: float


def validate_measure_stream_options(
    arguments: Mapping[str, object], capabilities: ScopeCapabilities,
) -> MeasureStreamOptions:
    """Validate every query using the existing Measure/Core model capabilities."""
    if not isinstance(arguments, dict):
        raise OscilloscopeError("measure-stream-start arguments must be an object")
    unknown = set(arguments) - {"measurements", "count", "interval_seconds"}
    if unknown:
        raise OscilloscopeError(f"unknown streaming argument: {sorted(unknown)[0]}")
    entries = arguments.get("measurements")
    if not isinstance(entries, list) or not entries:
        raise OscilloscopeError("measurements must be a non-empty list")
    if not operation_supported(capabilities, "measure"):
        raise OscilloscopeError("measure is unsupported for this model")
    fields: list[StreamField] = []
    ids: set[str] = set()
    optional = ("reference_channel", "time_s", "level", "slope", "occurrence")
    for entry in entries:
        if not isinstance(entry, dict):
            raise OscilloscopeError("each measurement must be an object")
        if set(entry) - {"id", "item", "channel", *optional}:
            raise OscilloscopeError("unknown measurement field")
        field_id = entry.get("id")
        if not isinstance(field_id, str) or not field_id or len(field_id) > 128:
            raise OscilloscopeError("measurement id must be a non-empty string (max 128)")
        if field_id in ids:
            raise OscilloscopeError(f"duplicate measurement id: {field_id}")
        if not isinstance(entry.get("item"), str):
            raise OscilloscopeError("measurement item must be a string")
        item = normalize_measurement_item(entry["item"])
        for key in ("channel", "reference_channel", "occurrence"):
            value = entry.get(key)
            if value is not None and (type(value) is not int):
                raise OscilloscopeError(f"{key} must be an integer")
        for key in ("time_s", "level"):
            value = entry.get(key)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise OscilloscopeError(f"{key} must be a finite number")
        if entry.get("slope") is not None and not isinstance(entry["slope"], str):
            raise OscilloscopeError("slope must be a string")
        request = MeasureRequest(
            item=item, channel=entry.get("channel"),
            reference_channel=entry.get("reference_channel"),
            time_s=entry.get("time_s"), level=entry.get("level"),
            slope=entry.get("slope"), occurrence=entry.get("occurrence"),
        )
        kwargs = _measurement_query_kwargs(request, item)
        if is_pair_measurement_item(item):
            source, reference = resolve_pair_measurement_channels(request, capabilities, item)
            pair_measurement_query(item, source, reference, capabilities=capabilities)
        else:
            channel = resolve_single_measurement_channel(request, capabilities)
            measurement_query(item, channel, capabilities=capabilities, **kwargs)
        fields.append(StreamField(field_id, request))
        ids.add(field_id)
    count = arguments.get("count")
    if count is not None and (type(count) is not int or count <= 0):
        raise OscilloscopeError("count must be a positive integer or null")
    interval = arguments.get("interval_seconds", 1.0)
    if type(interval) not in (int, float) or not math.isfinite(interval) or interval < 0:
        raise OscilloscopeError("interval_seconds must be a finite non-negative number")
    return MeasureStreamOptions(tuple(fields), count, float(interval))


def run_measure_stream(
    scope: Oscilloscope,
    options: MeasureStreamOptions,
    *,
    stop_requested: Callable[[], bool],
    wait_or_stop: Callable[[float], bool],
    sample_reporter: Callable[[Mapping[str, object]], None],
) -> tuple[int, int, str]:
    """Emit only fully completed cycles. Returns (cycles, invalid fields, reason)."""
    if scope.capabilities is None:
        raise OscilloscopeError("Capabilities unavailable for this model")
    # The stream owns one already-opened and identity-checked Scope session.
    for field in options.fields:
        validate_measure_stream_options(
            {"measurements": [
                {"id": field.field_id, **{
                    key: value for key, value in vars(field.request).items() if value is not None
                }}
            ]},
            scope.capabilities,
        )
    start = time.monotonic()
    completed = 0
    invalid_count = 0
    while options.count is None or completed < options.count:
        if stop_requested():
            return completed, invalid_count, "stop_requested"
        values: dict[str, object] = {}
        cycle_invalid = 0
        measurement_statuses = []
        for field in options.fields:
            if stop_requested():
                return completed, invalid_count, "stop_requested"
            request = field.request
            kwargs = _measurement_query_kwargs(request, request.item)
            if is_pair_measurement_item(request.item):
                result = scope.query_pair_measurement(
                    request.channel, request.reference_channel, request.item,
                )
            else:
                result = scope.query_measurement(
                    request.channel, request.item, **kwargs,
                )
            native_status = getattr(scope, "_stream_measurement_status", None)
            if native_status is None:
                native_status = getattr(scope, "_measurement_status", None)
            if native_status is not None:
                measurement_statuses.append(native_status(result))
                if not measurement_statuses[-1].complete:
                    raise OscilloscopeError(measurement_statuses[-1].format())
            valid = bool(result.valid and result.value is not None)
            number = float(result.value) if valid else None
            if number is not None and not math.isfinite(number):
                valid, number = False, None
            if not valid:
                cycle_invalid += 1
            values[field.field_id] = {
                "value": number,
                "unit": result.unit,
                "valid": valid,
                "reason": None if valid else (result.reason or "invalid measurement"),
            }
        cycle_status_fn = getattr(scope, "_measurement_cycle_status", None)
        if cycle_status_fn is not None:
            cycle_status = cycle_status_fn(measurement_statuses)
        else:
            workflow_status = getattr(scope, "workflow_status", None)
            cycle_status = workflow_status() if workflow_status is not None else None
        if cycle_status is not None and (
            cycle_status.is_error or not getattr(cycle_status, "complete", True)
        ):
            raise OscilloscopeError(cycle_status.format())
        if stop_requested():
            return completed, invalid_count, "stop_requested"
        completed += 1
        sample_reporter({
            "index": completed,
            "elapsed_seconds": time.monotonic() - start,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "values": values,
        })
        invalid_count += cycle_invalid
        if options.count is not None and completed >= options.count:
            break
        if wait_or_stop(options.interval_seconds):
            return completed, invalid_count, "stop_requested"
    return completed, invalid_count, "count_reached"
