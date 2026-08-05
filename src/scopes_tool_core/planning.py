"""Dry-run planning APIs for agent and Python integrations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .acquisition import (
    acquisition_count_command,
    acquisition_count_query,
    acquisition_type_command,
    acquisition_type_query,
    validate_acquisition_count,
)
from .capabilities import ScopeCapabilities
from .channel import channel_units_query, validate_analog_channel
from .errors import OscilloscopeError
from .measurements import (
    is_pair_measurement_item,
    measurement_query,
    normalize_measurement_item,
    pair_measurement_query,
)
from .output_files import capture_output_paths
from .screenshot import hardcopy_inksaver_command, hardcopy_inksaver_for_background, screenshot_data_query
from .waveform import (
    WORD_BYTE_ORDER,
    WORD_UNSIGNED,
    validate_word_format_supported,
    validate_waveform_channels,
    validate_waveform_points,
    waveform_byte_order_command,
    waveform_data_query,
    waveform_format_byte_command,
    waveform_format_word_command,
    waveform_points_command,
    waveform_preamble_query,
    waveform_source_command,
    waveform_unsigned_command,
)


@dataclass(frozen=True)
class OperationPlan:
    planned_scpi: tuple[str, ...]
    files: tuple[dict[str, str], ...]
    result: dict[str, object]


@dataclass(frozen=True)
class CapturePlanRequest:
    channels: Sequence[int | str]
    points: int
    waveform_format: str = "byte"
    csv_path: str | Path | None = None
    meta_path: str | Path | None = None
    plot_path: str | Path | None = None


@dataclass(frozen=True)
class MeasurePlanRequest:
    item: str
    channel: int | None = None
    source_channel: int | None = None
    reference_channel: int | None = None
    time_s: float | None = None
    level: float | None = None
    slope: str | None = None
    occurrence: int | None = None


@dataclass(frozen=True)
class MeasureSweepPlanRequest:
    channels: Sequence[int | str] | None = None
    items: str = "vpp,frequency,period,vrms"
    pairs: Sequence[str] = ()
    pair_items: str = "phase,delay"


@dataclass(frozen=True)
class SmokePlanRequest:
    output_dir: str | Path | None = None


@dataclass(frozen=True)
class AcquisitionCheckPlanRequest:
    output_dir: str | Path | None = None
    average_count: int = 16
    check_only: bool = False
    stop_on_error: bool = False
    restore_type: bool = False


def plan_capture(request: CapturePlanRequest, capabilities: ScopeCapabilities) -> OperationPlan:
    """Plan a waveform capture without opening an instrument."""

    channels = resolve_capture_channels(request.channels, capabilities)
    points = validate_waveform_points(request.points, capabilities)
    if request.waveform_format.lower() == "word":
        validate_word_format_supported(capabilities)
    files = _capture_files(request)
    result = {
        "channels": list(channels),
        "points": points,
        "format": request.waveform_format.upper(),
        "files": list(files),
        "requested_points": points,
    }
    return OperationPlan(
        tuple(planned_waveform_scpi(channels, request.waveform_format, points) + [":SYSTem:ERRor?"]),
        files,
        result,
    )


def plan_doctor(capabilities: ScopeCapabilities) -> OperationPlan:
    """Plan a read-only diagnostic snapshot."""

    return OperationPlan(
        tuple(doctor_planned_scpi(capabilities)),
        (),
        {
            "backend": None,
            "timeout_ms": None,
            "acquisition": {},
            "channels": [],
            "timebase": {},
            "edge_trigger": {},
        },
    )


def plan_measure(request: MeasurePlanRequest, capabilities: ScopeCapabilities) -> OperationPlan:
    """Plan one read-only measurement query."""

    item = normalize_measurement_item(request.item)
    kwargs = measurement_query_kwargs(request, item)
    result: dict[str, object] = {"item": item, "parameters": kwargs}
    if is_pair_measurement_item(item):
        source, reference = resolve_pair_measurement_channels(request, capabilities, item)
        planned = [pair_measurement_query(item, source, reference, capabilities=capabilities, **kwargs)]
        result.update({"channel": source, "reference_channel": reference})
    else:
        channel = resolve_single_measurement_channel(request, capabilities)
        planned = [measurement_query(item, channel, capabilities=capabilities, **kwargs)]
        result["channel"] = channel
    return OperationPlan(tuple(planned + [":SYSTem:ERRor?"]), (), result)


def plan_measure_sweep(
    request: MeasureSweepPlanRequest,
    capabilities: ScopeCapabilities,
) -> OperationPlan:
    """Plan a multi-channel measurement sweep."""

    channels = resolve_sweep_channels(request.channels, capabilities)
    items = parse_measurement_item_list(request.items, allow_pair=False)
    pairs = parse_pair_specs(request.pairs, capabilities)
    pair_items = parse_measurement_item_list(request.pair_items, allow_pair=True)
    planned = measure_sweep_planned_scpi(channels, items, pairs, pair_items, capabilities)
    return OperationPlan(
        tuple(planned),
        (),
        {
            "channels": list(channels),
            "items": list(items),
            "pairs": [
                {"source_channel": source, "reference_channel": reference}
                for source, reference in pairs
            ],
            "pair_items": list(pair_items),
            "measurements": [],
            "summary": {"valid_count": 0, "invalid_count": 0, "error_count": 0},
        },
    )


def plan_smoke(request: SmokePlanRequest, capabilities: ScopeCapabilities) -> OperationPlan:
    """Plan the capture-safe smoke workflow and its artifacts."""

    output_dir = (
        Path(request.output_dir)
        if request.output_dir is not None
        else Path("data") / "hardware_smoke" / "DRY-RUN"
    )
    files = smoke_file_list(output_dir)
    planned = (
        doctor_planned_scpi(capabilities)
        + [
            measurement_query("vpp", 1, capabilities=capabilities),
            measurement_query("vrms", 1, capabilities=capabilities),
        ]
        + planned_waveform_scpi((1,), "byte", 1000)
        + [
            hardcopy_inksaver_command(hardcopy_inksaver_for_background("black")),
            screenshot_data_query(),
            ":SYSTem:ERRor?",
        ]
    )
    return OperationPlan(
        tuple(planned),
        files,
        {
            "status": "planned",
            "output_dir": str(output_dir),
            "files": list(files),
            "doctor": {},
            "measurements": [],
            "capture": {},
            "screenshot": {},
            "warnings": [],
        },
    )


def plan_acquisition_check(request: AcquisitionCheckPlanRequest) -> OperationPlan:
    """Plan an acquisition configuration check workflow."""

    average_count = validate_acquisition_count(request.average_count)
    if request.check_only and request.restore_type:
        raise OscilloscopeError("--check-only cannot be combined with --restore-type")
    output_dir = (
        Path(request.output_dir)
        if request.output_dir is not None
        else Path("data") / "hardware_acquisition" / "DRY-RUN"
    )
    files = acquisition_check_file_list(output_dir)
    return OperationPlan(
        tuple(
            acquisition_check_planned_scpi(
                average_count,
                check_only=request.check_only,
                stop_on_error=request.stop_on_error,
                restore_type=request.restore_type,
            )
        ),
        files,
        {
            "status": "planned",
            "output_dir": str(output_dir),
            "report_path": str(output_dir / "report.json"),
            "scpi_log_path": str(output_dir / "scpi.log"),
            "average_count": average_count,
            "check_only": bool(request.check_only),
            "stopped_on_error": False,
            "initial_acquisition": None,
            "restore": {
                "requested": bool(request.restore_type),
                "attempted": False,
                "succeeded": None,
                "error": None,
            },
            "termination_reason": None,
            "steps": [],
            "final_acquisition": None,
            "files": list(files),
        },
    )


def acquisition_check_planned_scpi(
    average_count: int,
    *,
    check_only: bool = False,
    stop_on_error: bool = False,
    restore_type: bool = False,
) -> list[str]:
    del stop_on_error, restore_type
    if check_only:
        return ["*IDN?", acquisition_type_query(), acquisition_count_query(), ":SYSTem:ERRor?"]
    return [
        "*IDN?",
        acquisition_type_query(),
        acquisition_count_query(),
        ":SYSTem:ERRor?",
        acquisition_type_command("NORMal"),
        ":SYSTem:ERRor?",
        acquisition_type_command("AVERage"),
        acquisition_count_command(average_count),
        ":SYSTem:ERRor?",
        acquisition_type_query(),
        acquisition_count_query(),
        ":SYSTem:ERRor?",
        acquisition_type_command("HRESolution"),
        ":SYSTem:ERRor?",
        acquisition_type_command("PEAK"),
        ":SYSTem:ERRor?",
        acquisition_type_query(),
        acquisition_count_query(),
        ":SYSTem:ERRor?",
    ]


def planned_waveform_scpi(
    channels: Sequence[int],
    waveform_format: str,
    points: int,
) -> list[str]:
    planned: list[str] = []
    for channel in channels:
        planned.append(waveform_source_command(channel))
        planned.append(channel_units_query(channel))
        if waveform_format == "word":
            planned.extend(
                [
                    waveform_format_word_command(),
                    waveform_byte_order_command(WORD_BYTE_ORDER),
                    waveform_unsigned_command(WORD_UNSIGNED),
                ]
            )
        else:
            planned.append(waveform_format_byte_command())
        planned.extend(
            [waveform_points_command(points), waveform_preamble_query(), waveform_data_query()]
        )
    return planned


def doctor_planned_scpi(capabilities: ScopeCapabilities) -> list[str]:
    from .channel import (
        channel_bandwidth_limit_query,
        channel_coupling_query,
        channel_display_query,
        channel_offset_query,
        channel_probe_ratio_query,
        channel_scale_query,
    )
    from .timebase import timebase_position_query, timebase_scale_query
    from .trigger import (
        edge_trigger_level_query,
        edge_trigger_slope_query,
        edge_trigger_source_query,
    )

    planned = ["*IDN?", acquisition_type_query(), acquisition_count_query()]
    for channel in range(1, capabilities.analog_channels + 1):
        planned.extend(
            [
                channel_display_query(channel),
                channel_scale_query(channel),
                channel_offset_query(channel),
                channel_coupling_query(channel),
                channel_probe_ratio_query(channel),
                channel_bandwidth_limit_query(channel),
            ]
        )
    planned.extend(
        [
            timebase_scale_query(),
            timebase_position_query(),
            edge_trigger_source_query(),
            edge_trigger_level_query(),
            edge_trigger_slope_query(),
            ":SYSTem:ERRor?",
        ]
    )
    return planned


def measure_sweep_planned_scpi(
    channels: Sequence[int],
    items: Sequence[str],
    pairs: Sequence[tuple[int, int]],
    pair_items: Sequence[str],
    capabilities: ScopeCapabilities,
) -> list[str]:
    planned = ["*IDN?"]
    for channel in channels:
        for item in items:
            planned.append(measurement_query(item, channel, capabilities=capabilities))
            planned.append(":SYSTem:ERRor?")
    for source_channel, reference_channel in pairs:
        for item in pair_items:
            try:
                planned.append(
                    pair_measurement_query(
                        item,
                        source_channel,
                        reference_channel,
                        capabilities=capabilities,
                    )
                )
                planned.append(":SYSTem:ERRor?")
            except OscilloscopeError:
                continue
    return planned


def resolve_capture_channels(
    raw_channels: Sequence[int | str],
    capabilities: ScopeCapabilities,
) -> tuple[int, ...]:
    if any(channel == "all" for channel in raw_channels):
        if len(raw_channels) != 1:
            raise OscilloscopeError(
                "error: --channel all cannot be combined with explicit channel numbers"
            )
        return validate_waveform_channels(
            tuple(range(1, capabilities.analog_channels + 1)), capabilities
        )
    return validate_waveform_channels(raw_channels, capabilities)


def resolve_sweep_channels(
    raw_channels: Sequence[int | str] | None,
    capabilities: ScopeCapabilities,
) -> tuple[int, ...]:
    return resolve_capture_channels(raw_channels or ("all",), capabilities)


def parse_measurement_item_list(value: str, *, allow_pair: bool) -> tuple[str, ...]:
    items = []
    for token in value.split(","):
        stripped = token.strip()
        if not stripped:
            continue
        item = normalize_measurement_item(stripped)
        if allow_pair:
            if not is_pair_measurement_item(item):
                raise OscilloscopeError(
                    "--pair-items can only contain phase or delay measurements"
                )
        elif is_pair_measurement_item(item):
            raise OscilloscopeError("--items can only contain single-channel measurements")
        items.append(item)
    if not items:
        option = "--pair-items" if allow_pair else "--items"
        raise OscilloscopeError(f"{option} must contain at least one measurement item")
    return tuple(items)


def parse_pair_specs(
    values: Sequence[str],
    capabilities: ScopeCapabilities,
) -> tuple[tuple[int, int], ...]:
    pairs = []
    for value in values:
        parts = value.split(":")
        if len(parts) != 2:
            raise OscilloscopeError("--pair must use SRC:REF, for example 1:2")
        try:
            source = int(parts[0])
            reference = int(parts[1])
        except ValueError as exc:
            raise OscilloscopeError("--pair channels must be integers") from exc
        source = validate_analog_channel(source, capabilities)
        reference = validate_analog_channel(reference, capabilities)
        if source == reference:
            raise OscilloscopeError("--pair source and reference channels must differ")
        pairs.append((source, reference))
    return tuple(pairs)


def measurement_query_kwargs(
    request: MeasurePlanRequest,
    item: str,
) -> dict[str, object]:
    values: dict[str, object] = {}
    if request.time_s is not None:
        values["time_s"] = request.time_s
    if request.level is not None:
        values["level"] = request.level
    if request.slope is not None:
        values["slope"] = request.slope
    if request.occurrence is not None:
        values["occurrence"] = request.occurrence

    if is_pair_measurement_item(item):
        if values:
            raise OscilloscopeError(
                "--time, --level, --slope, and --occurrence cannot be used with "
                "phase or delay measurements"
            )
        return {}

    if item == "y_at_x":
        if request.time_s is None:
            raise OscilloscopeError("y_at_x measurement requires --time")
        if any(
            value is not None
            for value in (request.level, request.slope, request.occurrence)
        ):
            raise OscilloscopeError(
                "--level, --slope, and --occurrence cannot be used with y_at_x"
            )
        return values

    if item == "time_at_edge":
        if request.time_s is not None or request.level is not None:
            raise OscilloscopeError("--time and --level cannot be used with time_at_edge")
        values.setdefault("slope", "positive")
        values.setdefault("occurrence", 1)
        return values

    if item == "time_at_value":
        if request.level is None:
            raise OscilloscopeError("time_at_value measurement requires --level")
        if request.time_s is not None:
            raise OscilloscopeError("--time cannot be used with time_at_value")
        values.setdefault("slope", "positive")
        values.setdefault("occurrence", 1)
        return values

    if values:
        raise OscilloscopeError(
            "--time, --level, --slope, and --occurrence can only be used with "
            "y_at_x, time_at_edge, or time_at_value"
        )
    return {}


def resolve_measurement_source_channel(request: MeasurePlanRequest) -> int | None:
    if request.channel is not None and request.source_channel is not None:
        raise OscilloscopeError("--channel cannot be combined with --source-channel")
    return request.source_channel if request.source_channel is not None else request.channel


def resolve_single_measurement_channel(
    request: MeasurePlanRequest,
    capabilities: ScopeCapabilities,
) -> int:
    if request.reference_channel is not None:
        raise OscilloscopeError(
            "--reference-channel can only be used with phase or delay measurements"
        )
    channel = resolve_measurement_source_channel(request)
    if channel is None:
        raise OscilloscopeError("measure requires --channel or --source-channel")
    return validate_analog_channel(channel, capabilities)


def resolve_pair_measurement_channels(
    request: MeasurePlanRequest,
    capabilities: ScopeCapabilities,
    item: str,
) -> tuple[int, int]:
    source_channel = resolve_measurement_source_channel(request)
    if source_channel is None or request.reference_channel is None:
        raise OscilloscopeError(
            f"{item} measurement requires --source-channel or --channel, "
            "plus --reference-channel"
        )
    source_channel = validate_analog_channel(source_channel, capabilities)
    reference_channel = validate_analog_channel(request.reference_channel, capabilities)
    if source_channel == reference_channel:
        raise OscilloscopeError("source channel and reference channel must be different")
    return source_channel, reference_channel


def smoke_file_list(output_dir: Path) -> tuple[dict[str, str], ...]:
    return (
        {"kind": "report", "path": str(output_dir / "report.json")},
        {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
        {"kind": "csv", "path": str(output_dir / "capture.csv")},
        {"kind": "metadata", "path": str(output_dir / "capture_meta.json")},
        {"kind": "png", "path": str(output_dir / "screen.png")},
    )


def acquisition_check_file_list(output_dir: Path) -> tuple[dict[str, str], ...]:
    return (
        {"kind": "report", "path": str(output_dir / "report.json")},
        {"kind": "scpi_log", "path": str(output_dir / "scpi.log")},
    )


def _capture_files(request: CapturePlanRequest) -> tuple[dict[str, str], ...]:
    csv_path, meta_path, plot_path = capture_output_paths(
        request.csv_path,
        request.meta_path,
        request.plot_path,
    )
    files = [
        {"kind": "csv", "path": str(csv_path)},
        {"kind": "metadata", "path": str(meta_path)},
    ]
    if plot_path is not None:
        files.append({"kind": "plot_png", "path": str(plot_path)})
    return tuple(files)
