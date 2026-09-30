"""CLI dry-run planning for capture, measurement log, and finite workflow commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from scopes_tool_core.batch import batch_capture_paths
from scopes_tool_core.capabilities import ScopeCapabilities
from scopes_tool_core.capture_monitor import CaptureMonitorRequest, plan_capture_monitor
from scopes_tool_core.capture_until import CaptureUntilRequest, plan_capture_until
from scopes_tool_core.channel import validate_analog_channel
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.measure_logger import measure_log_paths
from scopes_tool_core.measure_until import MeasureUntilRequest, plan_measure_until
from scopes_tool_core.measurements import (
    is_pair_measurement_item,
    normalize_measurement_item,
    pair_measurement_query,
)
from scopes_tool_core.planning import (
    CapturePlanRequest,
    SmokePlanRequest,
    plan_capture,
    plan_smoke,
)
from scopes_tool_core.screenshot import (
    DEFAULT_SCREENSHOT_BACKGROUND,
    SCREENSHOT_TIMEOUT_MS,
    hardcopy_area_query,
    hardcopy_format_query,
    hardcopy_inksaver_command,
    hardcopy_inksaver_for_background,
    hardcopy_inksaver_query,
    hardcopy_layout_command,
    hardcopy_layout_query,
    hardcopy_palette_command,
    hardcopy_palette_query,
    hardcopy_screen_dump_data_query,
    screenshot_data_query,
)
from scopes_tool_core.sequence import (
    SequenceRequest,
    load_sequence_document,
    plan_sequence,
)
from scopes_tool_core.trigger import (
    force_trigger_command,
    operation_condition_query,
    single_command,
)
from scopes_tool_core.triggered_capture import (
    TriggeredCaptureSeriesRequest,
    plan_triggered_capture_series,
)
from scopes_tool_core.triggered_measurement import (
    TriggeredMeasureLoopRequest,
    plan_triggered_measure_loop,
)
from scopes_tool_core.waveform import (
    validate_waveform_channels,
    validate_waveform_points,
    validate_word_format_supported,
)

from . import preflight
from .commands import workflows


def _plan_workflows(
    args: argparse.Namespace, capabilities: ScopeCapabilities
) -> tuple[list[str], list[dict[str, str]], dict[str, object]] | None:
    command = args.command
    if command == "capture-until":
        plan = plan_capture_until(
            CaptureUntilRequest(
                channels=args.channel,
                condition_channel=args.condition_channel,
                points=args.points,
                waveform_format=args.waveform_format,
                metric=args.metric,
                operator=args.operator,
                threshold=args.threshold,
                count=args.count,
                timeout_seconds=args.timeout_seconds,
                interval_seconds=args.interval_seconds,
                output_dir=args.output_dir,
                log_scpi=bool(args.log_scpi),
            ),
            capabilities,
        )
        return list(plan.planned_scpi), list(plan.files), plan.result

    if command == "capture-monitor":
        plan = plan_capture_monitor(
            CaptureMonitorRequest(
                channels=args.channel,
                points=args.points,
                waveform_format=args.waveform_format,
                count=args.count,
                interval_seconds=args.interval_seconds,
                retention_points=args.retention_points,
                save_results=not args.no_save,
                output_dir=args.output_dir,
                log_scpi=bool(args.log_scpi),
            ),
            capabilities,
        )
        return list(plan.planned_scpi), list(plan.files), plan.result

    if command == "measure-until":
        plan = plan_measure_until(
            MeasureUntilRequest(
                channel=args.channel,
                item=args.item,
                operator=args.operator,
                threshold=args.threshold,
                timeout_seconds=args.timeout_seconds,
                interval_seconds=args.interval_seconds,
                output_dir=args.output_dir,
                save_results=not args.no_save,
                log_scpi=bool(args.log_scpi),
            ),
            capabilities,
        )
        return list(plan.planned_scpi), list(plan.files), plan.result

    if command == "triggered-capture-series":
        plan = plan_triggered_capture_series(
            TriggeredCaptureSeriesRequest(
                channels=args.channel,
                points=args.points,
                waveform_format=args.waveform_format,
                count=args.count,
                trigger_timeout_seconds=args.trigger_timeout_seconds,
                interval_seconds=args.interval_seconds,
                output_dir=args.output_dir,
                log_scpi=bool(args.log_scpi),
            ),
            capabilities,
        )
        return list(plan.planned_scpi), list(plan.files), plan.result

    if command == "triggered-measure-loop":
        plan = plan_triggered_measure_loop(
            TriggeredMeasureLoopRequest(
                channels=args.channel,
                items=args.items,
                pairs=tuple(args.pair),
                pair_items=args.pair_items,
                count=args.count,
                trigger_timeout_seconds=args.trigger_timeout_seconds,
                interval_seconds=args.interval_seconds,
                output_dir=args.output_dir,
                save_results=not args.no_save,
                log_scpi=bool(args.log_scpi),
            ),
            capabilities,
        )
        return list(plan.planned_scpi), list(plan.files), plan.result

    if command == "sequence":
        request = SequenceRequest(
            load_sequence_document(args.sequence_file),
            output_dir=args.output_dir,
            log_scpi=bool(args.log_scpi),
            save_results=not args.no_save,
        )
        plan = plan_sequence(request, capabilities)
        return list(plan.planned_scpi), list(plan.files), plan.result

    if command == "capture":
        trigger_wait = workflows._capture_trigger_wait_config(args)
        plan = plan_capture(
            CapturePlanRequest(
                channels=args.channel,
                points=args.points,
                waveform_format=args.waveform_format,
                csv_path=args.csv_path,
                meta_path=args.meta_path,
                plot_path=args.plot_path,
            ),
            capabilities,
        )
        planned = list(plan.planned_scpi)
        result = dict(plan.result)
        if trigger_wait is not None:
            wait_scpi = [single_command(), operation_condition_query()]
            if trigger_wait.force_on_timeout:
                wait_scpi.extend([force_trigger_command(), operation_condition_query()])
            planned = wait_scpi + planned
            result["trigger"] = {
                "wait_enabled": True,
                "arm_command": single_command(),
                "poll_source": "operation_condition",
                "poll_command": operation_condition_query(),
                "timeout_ms": trigger_wait.timeout_ms,
                "poll_interval_ms": trigger_wait.poll_interval_ms,
                "force_on_timeout": trigger_wait.force_on_timeout,
                "force_command": force_trigger_command(),
                "outcome": "unknown",
                "forced": False,
                "timed_out": False,
                "poll_count": 0,
                "elapsed_ms": 0.0,
                "condition_values": [],
                "raw_values": [],
                "capture_allowed": False,
                "capture_block_reason": "dry_run",
                "error": None,
            }
        return planned, list(plan.files), result

    if command == "smoke":
        plan = plan_smoke(SmokePlanRequest(output_dir=args.output_dir), capabilities)
        return list(plan.planned_scpi), list(plan.files), plan.result

    if command == "capture-batch":
        channels = _resolve_capture_channels(args.channel, capabilities)
        points = validate_waveform_points(args.points, capabilities)
        if args.waveform_format == "word":
            validate_word_format_supported(capabilities)
        planned = list(plan_capture(CapturePlanRequest(channels, points, args.waveform_format), capabilities, workflow=True).planned_scpi)
        files = _planned_capture_files(args, command)
        result = {"channels": list(channels), "points": points, "format": args.waveform_format.upper(), "files": files}
        result.update({"status": "planned", "requested_count": args.count, "completed_count": 0, "captures": [], "manifest_path": files[0]["path"], "scpi_log_path": files[1]["path"]})
        return planned, files, result

    if command == "measure-log":
        channels = _resolve_capture_channels(args.channel or ("all",), capabilities)
        items = _parse_measurement_item_list(args.items, allow_pair=False)
        pairs = _parse_pair_specs(args.pair, capabilities)
        pair_items = _parse_measurement_item_list(args.pair_items, allow_pair=True)
        planned = _measure_log_planned_scpi(channels, items, pairs, pair_items, capabilities)
        files = _planned_measure_log_files(args)
        result = {
            "status": "planned",
            "channels": list(channels),
            "items": list(items),
            "pairs": [f"{src}:{ref}" for src, ref in pairs],
            "pair_items": list(pair_items),
            "interval_seconds": args.interval_seconds,
            "requested_count": args.count,
            "requested_duration_seconds": args.duration_seconds,
            "completed_rows": 0,
                "last_measurement": None,
                "files": files,
                "manifest_path": files[1]["path"] if files else None,
                "scpi_log_path": files[2]["path"] if files else None,
                "csv_path": files[0]["path"] if files else None,
            }
        return planned, files, result

    if command == "screenshot":
        if args.query_hardcopy:
            planned = [
                hardcopy_area_query(),
                hardcopy_inksaver_query(),
                hardcopy_palette_query(),
                hardcopy_layout_query(),
                hardcopy_format_query(),
                ":SYSTem:ERRor?",
            ]
            return planned, [], {"operation": "query", "hardcopy": None}
        options = preflight._screenshot_options(args)
        background = args.background or DEFAULT_SCREENSHOT_BACKGROUND
        format_name = options.format or "png"
        output_path = workflows._screenshot_output_path(args, format_name)
        file_kind = "png" if format_name == "png" else "bmp"
        files = [{"kind": file_kind, "path": str(output_path)}]
        ink_saver_plan = None
        if preflight._uses_screenshot_hardcopy_controls(args):
            planned = []
            if options.ink_saver is not None:
                planned.append(hardcopy_inksaver_command(options.ink_saver))
                ink_saver_plan = {
                    "mode": "explicit",
                    "target": options.ink_saver,
                    "restore": None,
                }
            else:
                background_ink_saver = hardcopy_inksaver_for_background(background)
                planned.extend(
                    [
                        hardcopy_inksaver_query(),
                        hardcopy_inksaver_command(background_ink_saver),
                    ]
                )
                ink_saver_plan = {
                    "mode": "temporary_background",
                    "target": background_ink_saver,
                    "restore": "queried_state_if_changed",
                }
            if options.palette is not None:
                planned.append(hardcopy_palette_command(options.palette))
            if options.layout is not None:
                planned.append(hardcopy_layout_command(options.layout))
            planned.append(hardcopy_screen_dump_data_query(format_name))
        else:
            planned = [
                hardcopy_inksaver_command(hardcopy_inksaver_for_background(background)),
                screenshot_data_query(),
            ]
        result = {
            "format": {"png": "PNG", "bmp": "BMP", "bmp8bit": "BMP8bit"}[format_name],
            "background": background,
            "ink_saver": options.ink_saver,
            "palette": options.palette,
            "layout": options.layout,
            "options": {
                "format": options.format,
                "ink_saver": options.ink_saver,
                "palette": options.palette,
                "layout": options.layout,
            },
            "timeout_ms": SCREENSHOT_TIMEOUT_MS,
            "files": files,
            "image_path": str(output_path),
        }
        if format_name == "png":
            result["png_path"] = str(output_path)
        if ink_saver_plan is not None:
            result["ink_saver_plan"] = ink_saver_plan
        return planned + [":SYSTem:ERRor?"], files, result
    return None


def _parse_measurement_item_list(value: str, *, allow_pair: bool) -> tuple[str, ...]:
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
            raise OscilloscopeError(
                "--items can only contain single-channel measurements"
            )
        items.append(item)
    if not items:
        option = "--pair-items" if allow_pair else "--items"
        raise OscilloscopeError(f"{option} must contain at least one measurement item")
    return tuple(items)


def _parse_pair_specs(
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


def _resolve_capture_channels(
    raw_channels: Sequence[int | str], capabilities: ScopeCapabilities
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


def _planned_capture_files(args: argparse.Namespace, command: str) -> list[dict[str, str]]:
    if command == "capture":
        csv_path = Path(args.csv_path) if args.csv_path is not None else workflows._default_capture_csv_path()
        meta_path = Path(args.meta_path) if args.meta_path is not None else csv_path.with_name(f"{csv_path.stem}_meta.json")
        files = [{"kind": "csv", "path": str(csv_path)}, {"kind": "metadata", "path": str(meta_path)}]
        if args.plot_path is not None:
            files.append({"kind": "plot_png", "path": str(Path(args.plot_path))})
        return files
    output_dir = Path(args.output_dir) if args.output_dir is not None else Path("data") / "captures" / "DRY-RUN"
    files = [{"kind": "manifest", "path": str(output_dir / "manifest.json")}, {"kind": "scpi_log", "path": str(output_dir / "scpi.log")}]
    for index in range(1, args.count + 1):
        csv_path, meta_path = batch_capture_paths(output_dir, index, args.count)
        files.extend([{"kind": "csv", "path": str(csv_path)}, {"kind": "metadata", "path": str(meta_path)}])
    return files


def _planned_measure_log_files(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.no_save:
        return []
    output_dir = (
        Path(args.output_dir)
        if args.output_dir is not None
        else Path("data") / "measure_logs" / "DRY-RUN"
    )
    csv_path, manifest_path, scpi_log_path = measure_log_paths(output_dir)
    return [
        {"kind": "csv", "path": str(csv_path)},
        {"kind": "manifest", "path": str(manifest_path)},
        {"kind": "scpi_log", "path": str(scpi_log_path)},
    ]


def _measure_log_planned_scpi(
    channels: Sequence[int],
    items: Sequence[str],
    pairs: Sequence[tuple[int, int]],
    pair_items: Sequence[str],
    capabilities: ScopeCapabilities,
) -> list[str]:
    from scopes_tool_core.planning import plan_measure, MeasurePlanRequest, workflow_step_scpi
    planned = []
    for channel in channels:
        for item in items:
            planned.extend(plan_measure(MeasurePlanRequest(item, channel), capabilities).planned_scpi[:-1])
    for source, reference in pairs:
        for item in pair_items:
            planned.append(pair_measurement_query(item, source, reference, capabilities=capabilities))
    return planned + workflow_step_scpi(capabilities, "status")
