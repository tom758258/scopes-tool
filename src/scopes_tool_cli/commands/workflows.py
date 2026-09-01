from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Mapping

from .. import preflight, runtime
from scopes_tool_core.setup import (
    autoscale_commands,
    setup_recall_command,
    setup_save_command,
)
from scopes_tool_core.channel import validate_analog_channel
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.measure_until import MeasureUntilRequest, run_measure_until
from scopes_tool_core.capture_until import CaptureUntilRequest, run_capture_until
from scopes_tool_core.capture_monitor import CaptureMonitorRequest, run_capture_monitor
from scopes_tool_core.operations import (
    AcquisitionCheckRequest,
    CaptureBatchRequest,
    CaptureRequest,
    MeasureLogRequest,
    MeasureRequest,
    MeasureSweepRequest,
    SmokeRequest,
    _OperationError,
    run_acquisition_check,
    run_capture,
    run_capture_batch,
    run_doctor,
    run_measure,
    run_measure_log,
    run_measure_sweep,
    run_smoke,
)
from scopes_tool_core.save_export import (
    save_filename_command,
    save_filename_query,
    save_image_command,
    save_image_factors_command,
    save_image_factors_query,
    save_image_format_command,
    save_image_format_query,
    save_image_ink_saver_command,
    save_image_ink_saver_query,
    save_image_palette_command,
    save_image_palette_query,
    save_pwd_command,
    save_pwd_query,
    save_waveform_command,
    save_waveform_format_command,
    save_waveform_format_query,
    save_waveform_length_command,
    save_waveform_length_max_query,
    save_waveform_length_query,
)
from scopes_tool_core.status import system_opc_query
from scopes_tool_core.screenshot import (
    DEFAULT_SCREENSHOT_BACKGROUND,
    SCREENSHOT_TIMEOUT_MS,
    hardcopy_inksaver_command,
    hardcopy_inksaver_for_background,
    hardcopy_layout_command,
    hardcopy_palette_command,
    hardcopy_screen_dump_data_query,
    screenshot_data_query,
    write_screenshot,
    write_screenshot_png,
)
from scopes_tool_core.segmented_capture import run_segmented_capture
from scopes_tool_core.sequence import SequenceRequest, load_sequence_document, run_sequence
from scopes_tool_core.trigger import TriggerWaitConfig
from scopes_tool_core.triggered_capture import TriggeredCaptureSeriesRequest, run_triggered_capture_series
from scopes_tool_core.triggered_measurement import TriggeredMeasureLoopRequest, run_triggered_measure_loop
from scopes_tool_core.workflow import StopRequested

_CAPTURE_DEFAULT_TIMEZONE = timezone(timedelta(hours=8), name="UTC+8")


AUTOSCALE_SYSTEM_ERROR_TIMEOUT_MS = 15000


def _apply_operation_result(result) -> None:
    if runtime._JSON_RECORD is None:
        return
    runtime._JSON_RECORD["result"] = result.result
    runtime._JSON_RECORD["files"] = result.files
    runtime._JSON_RECORD["system_error"] = result.system_error
    if result.backend is not None:
        runtime._JSON_RECORD["backend"] = result.backend


def _save_export_plan(
    args: argparse.Namespace,
) -> tuple[str, dict[str, object], bool]:
    command = args.command
    result: dict[str, object] = {"instrument_side": True}
    if command == "save-pwd":
        target = save_pwd_query() if args.query else save_pwd_command(args.path)
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(path=args.path, state_changing=True)
    elif command == "save-filename":
        target = save_filename_query() if args.query else save_filename_command(args.name)
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(name=args.name, state_changing=True)
    elif command == "save-image-format":
        target = (
            save_image_format_query()
            if args.query
            else save_image_format_command(args.format)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(format=args.format, state_changing=True)
    elif command == "save-image-palette":
        target = (
            save_image_palette_query()
            if args.query
            else save_image_palette_command(args.palette)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(palette=args.palette, state_changing=True)
    elif command == "save-image-ink-saver":
        target = (
            save_image_ink_saver_query()
            if args.query
            else save_image_ink_saver_command(args.enabled)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(enabled=args.enabled, state_changing=True)
    elif command == "save-image-factors":
        target = (
            save_image_factors_query()
            if args.query
            else save_image_factors_command(args.enabled)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(enabled=args.enabled, state_changing=True)
    elif command == "save-image":
        target = save_image_command(args.filename)
        result.update(
            operation="save-image",
            filename=args.filename,
            command=target,
            state_changing=True,
        )
        return target, result, True
    elif command == "save-waveform-format":
        target = (
            save_waveform_format_query()
            if args.query
            else save_waveform_format_command(args.format)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(format=args.format, state_changing=True)
    elif command == "save-waveform-length":
        target = (
            save_waveform_length_query()
            if args.query
            else save_waveform_length_command(args.points)
        )
        result.update(operation="query" if args.query else "configure", command=target)
        if not args.query:
            result.update(points=args.points, state_changing=True)
    elif command == "save-waveform-length-max":
        target = save_waveform_length_max_query()
        result.update(operation="query", command=target)
    else:
        target = save_waveform_command(args.filename)
        result.update(
            operation="save-waveform",
            filename=args.filename,
            command=target,
            state_changing=True,
        )
        return target, result, True
    return target, result, False


def _cmd_save_export(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        target, result, waits_for_completion = _save_export_plan(args)

        if args.command == "save-pwd":
            if args.query:
                state = scope.query_save_pwd()
                result.update(state.to_json())
                print(f"Instrument save directory: {state.path}")
            else:
                scope.configure_save_pwd(args.path)
                print(f"Instrument save directory: {args.path}")
        elif args.command == "save-filename":
            if args.query:
                state = scope.query_save_filename()
                result.update(state.to_json())
                print(f"Instrument save base name: {state.name}")
            else:
                scope.configure_save_filename(args.name)
                print(f"Instrument save base name: {args.name}")
        elif args.command == "save-image-format":
            if args.query:
                state = scope.query_save_image_format()
                result.update(state.to_json())
                print(f"Instrument image save format: {state.format}")
            else:
                scope.configure_save_image_format(args.format)
                print(f"Instrument image save format: {args.format}")
        elif args.command == "save-image-palette":
            if args.query:
                state = scope.query_save_image_palette()
                result.update(state.to_json())
                print(f"Instrument image save palette: {state.palette}")
            else:
                scope.configure_save_image_palette(args.palette)
                print(f"Instrument image save palette: {args.palette}")
        elif args.command == "save-image-ink-saver":
            if args.query:
                state = scope.query_save_image_ink_saver()
                result.update(state.to_json())
                print(f"Instrument image ink saver: {state.enabled}")
            else:
                scope.configure_save_image_ink_saver(args.enabled)
                print(f"Instrument image ink saver: {args.enabled}")
        elif args.command == "save-image-factors":
            if args.query:
                state = scope.query_save_image_factors()
                result.update(state.to_json())
                print(f"Instrument image factors: {state.enabled}")
            else:
                scope.configure_save_image_factors(args.enabled)
                print(f"Instrument image factors: {args.enabled}")
        elif args.command == "save-image":
            operation = scope.save_image(args.filename)
            result.update(operation.to_json(), state_changing=True)
            print(f"Instrument-side image saved as: {args.filename}")
        elif args.command == "save-waveform-format":
            if args.query:
                state = scope.query_save_waveform_format()
                result.update(state.to_json())
                print(f"Instrument waveform save format: {state.format}")
            else:
                scope.configure_save_waveform_format(args.format)
                print(f"Instrument waveform save format: {args.format}")
        elif args.command == "save-waveform-length":
            if args.query:
                state = scope.query_save_waveform_length()
                result.update(state.to_json())
                print(f"Instrument waveform save length: {state.points}")
            else:
                scope.configure_save_waveform_length(args.points)
                print(f"Instrument waveform save length: {args.points}")
        elif args.command == "save-waveform-length-max":
            state = scope.query_save_waveform_length_max()
            result.update(state.to_json())
            print(f"Maximum waveform save length enabled: {state.enabled}")
        else:
            operation = scope.save_waveform(args.filename)
            result.update(operation.to_json(), state_changing=True)
            print(f"Instrument-side waveform saved as: {args.filename}")

        runtime._json_update_result(**result)
        print(f"Command: {target}")
        if waits_for_completion:
            print(f"Operation complete query: {system_opc_query()}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        result = run_doctor(scope, resource)
        if result.idn is not None:
            runtime._json_record_scope(scope, result.idn)
        _apply_operation_result(result)
        for line in result.human_lines:
            print(line)
        return result.exit_code


def _cmd_measure_sweep(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        result = run_measure_sweep(
            scope,
            resource,
            MeasureSweepRequest(
                channels=args.channel,
                items=args.items,
                pairs=tuple(args.pair),
                pair_items=args.pair_items,
            ),
        )
        if result.idn is not None:
            runtime._json_record_scope(scope, result.idn)
        _apply_operation_result(result)
        for line in result.human_lines:
            print(line)
        return result.exit_code


def _measure_operation_request(args: argparse.Namespace) -> MeasureRequest:
    return MeasureRequest(
        item=args.item,
        channel=args.channel,
        source_channel=args.source_channel,
        reference_channel=args.reference_channel,
        time_s=args.time_s,
        level=args.level,
        slope=args.slope,
        occurrence=args.occurrence,
    )


def _cmd_measure(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_measure(scope, resource, _measure_operation_request(args))
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code


def _capture_trigger_wait_config(args: argparse.Namespace) -> TriggerWaitConfig | None:
    wait_trigger = bool(getattr(args, "wait_trigger", False))
    timeout_ms = getattr(args, "trigger_timeout_ms", None)
    poll_interval_ms = int(getattr(args, "trigger_poll_interval_ms", 100))
    force_on_timeout = bool(getattr(args, "force_trigger_on_timeout", False))
    if not wait_trigger:
        if timeout_ms is not None:
            raise OscilloscopeError("--trigger-timeout-ms requires --wait-trigger")
        if force_on_timeout:
            raise OscilloscopeError("--force-trigger-on-timeout requires --wait-trigger")
        return None
    if timeout_ms is None:
        raise OscilloscopeError("--trigger-timeout-ms is required with --wait-trigger")
    if poll_interval_ms > timeout_ms:
        raise OscilloscopeError(
            "--trigger-poll-interval-ms must be less than or equal to --trigger-timeout-ms"
        )
    return TriggerWaitConfig(
        timeout_ms=timeout_ms,
        poll_interval_ms=poll_interval_ms,
        force_on_timeout=force_on_timeout,
    )


def _cmd_capture(args: argparse.Namespace) -> int:
    trigger_wait = _capture_trigger_wait_config(args)
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    csv_path = Path(args.csv_path) if args.csv_path is not None else _default_capture_csv_path()
    meta_path = Path(args.meta_path) if args.meta_path is not None else csv_path.with_name(
        f"{csv_path.stem}_meta.json"
    )
    plot_path = Path(args.plot_path) if args.plot_path is not None else None

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_capture(
            scope,
            resource,
            CaptureRequest(
                channels=args.channel,
                points=args.points,
                waveform_format=args.waveform_format,
                csv_path=csv_path,
                meta_path=meta_path,
                plot_path=plot_path,
                allow_time_axis_tolerance=args.allow_time_axis_tolerance,
                trigger_wait=trigger_wait,
            ),
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code


def _cmd_capture_batch(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        try:
            operation_result = run_capture_batch(
                scope,
                resource,
                CaptureBatchRequest(
                    channels=args.channel,
                    points=args.points,
                    waveform_format=args.waveform_format,
                    requested_count=args.count,
                    interval_seconds=args.interval_seconds,
                    output_dir=args.output_dir,
                    log_scpi=args.log_scpi,
                ),
                stop_requested=stop_requested,
            )
        except _OperationError as exc:
            operation_result = exc.result
            if operation_result.idn is not None:
                runtime._json_record_scope(scope, operation_result.idn)
            _apply_operation_result(operation_result)
            for line in operation_result.human_lines:
                print(line)
            raise OscilloscopeError(str(exc)) from exc

        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _cmd_measure_log(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        try:
            operation_result = run_measure_log(
                scope,
                resource,
                MeasureLogRequest(
                    channels=args.channel,
                    items=args.items,
                    pairs=tuple(args.pair),
                    pair_items=args.pair_items,
                    interval_seconds=args.interval_seconds,
                    requested_count=args.count,
                    requested_duration_seconds=args.duration_seconds,
                    output_dir=args.output_dir,
                    save_results=not args.no_save,
                    stop_on_error=args.stop_on_error,
                    log_scpi=args.log_scpi,
                ),
                stop_requested=stop_requested,
            )
        except _OperationError as exc:
            operation_result = exc.result
            if operation_result.idn is not None:
                runtime._json_record_scope(scope, operation_result.idn)
            _apply_operation_result(operation_result)
            for line in operation_result.human_lines:
                print(line)
            raise OscilloscopeError(str(exc)) from exc
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code


def _cmd_measure_until(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_measure_until(
            scope,
            resource,
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
            stop_requested=stop_requested,
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _cmd_capture_until(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    with runtime._open_scope(args, resource) as scope:
        operation_result = run_capture_until(
            scope,
            resource,
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
            stop_requested=stop_requested,
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _monitor_human_reporter(update: Mapping[str, object]) -> None:
    try:
        completed = update.get("completed_count")
        requested = update.get("requested_count")
        total = update.get("total_observed_points")
        retained = update.get("retained_points")
        dropped = update.get("dropped_points")
        metrics = update.get("metrics") if isinstance(update.get("metrics"), Mapping) else {}
        print(f"Capture {completed}/{requested}: observed={total} retained={retained} dropped={dropped}")
        if isinstance(metrics, Mapping) and metrics:
            parts: list[str] = []
            for channel in sorted(metrics.keys(), key=lambda name: str(name)):
                values = metrics[channel]
                if not isinstance(values, Mapping):
                    continue
                maximum = values.get("maximum")
                minimum = values.get("minimum")
                p2p = values.get("peak_to_peak")
                abs_max = values.get("abs_max")
                unit = str(values.get("unit", "")).strip()

                def _fmt(value: object) -> str:
                    try:
                        return f"{float(value):g}"
                    except Exception:
                        return str(value)

                if unit:
                    parts.append(
                        f"{channel} max={_fmt(maximum)} {unit} min={_fmt(minimum)} {unit} p2p={_fmt(p2p)} {unit} abs-max={_fmt(abs_max)} {unit}"
                    )
                else:
                    parts.append(
                        f"{channel} max={_fmt(maximum)} min={_fmt(minimum)} p2p={_fmt(p2p)} abs-max={_fmt(abs_max)}"
                    )
            if parts:
                print(" | ".join(parts))
    except Exception:
        return


def _cmd_capture_monitor(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
    sample_reporter=None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    effective_reporter = sample_reporter
    if effective_reporter is None and runtime._JSON_RECORD is None:
        effective_reporter = _monitor_human_reporter
    with runtime._open_scope(args, resource) as scope:
        operation_result = run_capture_monitor(
            scope,
            resource,
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
            stop_requested=stop_requested,
            sample_reporter=effective_reporter,
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _cmd_triggered_measure_loop(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_triggered_measure_loop(
            scope,
            resource,
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
            stop_requested=stop_requested,
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _cmd_triggered_capture_series(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_triggered_capture_series(
            scope,
            resource,
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
            stop_requested=stop_requested,
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _cmd_sequence(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    document = load_sequence_document(args.sequence_file)
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        operation_result = run_sequence(
            scope,
            resource,
            SequenceRequest(
                document,
                output_dir=args.output_dir,
                log_scpi=bool(args.log_scpi),
            ),
            stop_requested=stop_requested,
        )
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        if operation_result.result.get("status") == "interrupted":
            print("error: interrupted", file=sys.stderr)
        return operation_result.exit_code


def _cmd_screenshot(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        print(f"Series: {idn.series or 'unknown'}")
        if scope.capabilities is None:
            print("Capabilities: unavailable for this model")
            return 1

        if args.query_hardcopy:
            state = scope.query_hardcopy_state()
            hardcopy = {
                "area": state.area,
                "ink_saver": state.ink_saver,
                "palette": state.palette,
                "layout": state.layout,
                "format": state.format,
                "raw_area": state.raw_area,
                "raw_ink_saver": state.raw_ink_saver,
                "raw_palette": state.raw_palette,
                "raw_layout": state.raw_layout,
                "raw_format": state.raw_format,
            }
            runtime._json_update_result(operation="query", hardcopy=hardcopy)
            print(f"Area: {state.area} (raw: {state.raw_area})")
            print(f"Ink saver: {state.ink_saver} (raw: {state.raw_ink_saver})")
            print(f"Palette: {state.palette} (raw: {state.raw_palette})")
            print(f"Layout: {state.layout} (raw: {state.raw_layout})")
            print(f"Format: {state.format} (raw: {state.raw_format})")
            entry = scope.query_system_error()
            runtime._json_record_system_error(entry)
            print(f"System error: {entry.format()}")
            return 1 if entry.is_error else 0

        options = preflight._screenshot_options(args)
        format_name = options.format or "png"
        output_path = _screenshot_output_path(args, format_name)
        background = args.background or DEFAULT_SCREENSHOT_BACKGROUND
        display_format = {"png": "PNG", "bmp": "BMP", "bmp8bit": "BMP8bit"}[
            format_name
        ]
        print(
            f"Planned capture: current screen {display_format} image with {background} background"
        )
        print(f"Screenshot timeout ms: {SCREENSHOT_TIMEOUT_MS} (temporary)")
        if preflight._uses_screenshot_hardcopy_controls(args):
            capture = scope.capture_screenshot(options=options, background=background)
            if options.ink_saver is not None:
                print(f"Command: {hardcopy_inksaver_command(options.ink_saver)}")
            else:
                print(
                    "Command: "
                    + hardcopy_inksaver_command(
                        hardcopy_inksaver_for_background(background)
                    )
                )
            if options.palette is not None:
                print(f"Command: {hardcopy_palette_command(options.palette)}")
            if options.layout is not None:
                print(f"Command: {hardcopy_layout_command(options.layout)}")
            print(f"Command: {hardcopy_screen_dump_data_query(format_name)}")
            written_image = _write_screenshot(capture, output_path, format_name)
        else:
            capture = scope.capture_screenshot_png(background=background)
            print(
                f"Command: {hardcopy_inksaver_command(hardcopy_inksaver_for_background(background))}"
            )
            print(f"Command: {screenshot_data_query()}")
            written_image = _write_screenshot_png(capture, output_path)
        file_kind = "png" if format_name == "png" else "bmp"
        files = [{"kind": file_kind, "path": str(written_image)}]
        runtime._json_set_files(files)
        result = dict(
            format=capture.format_name,
            palette=(options.palette if preflight._uses_screenshot_hardcopy_controls(args) else capture.palette),
            background=capture.background,
            ink_saver=options.ink_saver,
            layout=options.layout,
            options={
                "format": options.format,
                "ink_saver": options.ink_saver,
                "palette": options.palette,
                "layout": options.layout,
            },
            byte_count=len(capture.data),
            timeout_ms=SCREENSHOT_TIMEOUT_MS,
            image_path=str(written_image),
            files=files,
        )
        if format_name == "png":
            result["png_path"] = str(written_image)
        runtime._json_update_result(**result)
        print(f"Format: {capture.format_name}")
        if capture.palette is not None:
            print(f"Palette: {capture.palette}")
        print(f"Background: {capture.background}")
        print(f"Bytes: {len(capture.data)}")
        if format_name == "png":
            print(f"PNG: {written_image}")
        else:
            print(f"BMP: {written_image}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_smoke(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        try:
            operation_result = run_smoke(
                scope,
                resource,
                SmokeRequest(output_dir=args.output_dir, log_scpi=args.log_scpi),
            )
        except _OperationError as exc:
            operation_result = exc.result
            if operation_result.idn is not None:
                runtime._json_record_scope(scope, operation_result.idn)
            _apply_operation_result(operation_result)
            for line in operation_result.human_lines:
                print(line)
            raise OscilloscopeError(str(exc)) from exc
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code


def _cmd_segmented_capture(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    request = preflight._segmented_capture_request(args)
    with runtime._open_scope(args, resource) as scope:
        operation_result = run_segmented_capture(scope, resource, request)
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code


def _query_system_error_with_temporary_timeout(scope: Oscilloscope, timeout_ms: int):
    original_timeout = scope.scpi.timeout
    scope.scpi.set_timeout(timeout_ms)
    try:
        return scope.query_system_error()
    finally:
        scope.scpi.set_timeout(original_timeout)


def _cmd_simple_advanced(args: argparse.Namespace, command_name: str) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        if scope.capabilities is None:
            print("Capabilities: unavailable for this model")
            return 1
        if command_name == "autoscale":
            channels = None if not args.source_channel else tuple(validate_analog_channel(channel, scope.capabilities) for channel in args.source_channel)
            scope.autoscale(channels, acquire_mode=args.acquire_mode, channels_mode=args.channels)
            commands = autoscale_commands(channels, acquire_mode=args.acquire_mode, channels_mode=args.channels, capabilities=scope.capabilities)
            runtime._json_update_result(operation="run", commands=commands, source_channels=None if channels is None else list(channels))
        elif command_name == "setup-save":
            scope.save_setup(slot=args.slot, file_spec=args.setup_file)
            commands = [setup_save_command(slot=args.slot, file_spec=args.setup_file)]
            runtime._json_update_result(operation="save", command=commands[0], slot=args.slot, file=args.setup_file)
        else:
            scope.recall_setup(slot=args.slot, file_spec=args.setup_file)
            commands = [setup_recall_command(slot=args.slot, file_spec=args.setup_file)]
            runtime._json_update_result(operation="recall", command=commands[0], slot=args.slot, file=args.setup_file)
        for command in commands:
            print(f"Command: {command}")
        if command_name == "autoscale" and not getattr(args, "simulate", False):
            print(
                "System error timeout ms: "
                f"{AUTOSCALE_SYSTEM_ERROR_TIMEOUT_MS} (temporary)"
            )
            entry = _query_system_error_with_temporary_timeout(
                scope, AUTOSCALE_SYSTEM_ERROR_TIMEOUT_MS
            )
            if entry.code == -113 and getattr(args, "source_channel", None):
                fallback_command = ":AUToscale"
                print(
                    "Autoscale source form was rejected; "
                    f"retrying with {fallback_command}"
                )
                scope.scpi.write(fallback_command)
                commands.append(fallback_command)
                runtime._json_update_result(
                    commands=commands,
                    fallback="bare_autoscale_after_source_undefined_header",
                )
                entry = _query_system_error_with_temporary_timeout(
                    scope, AUTOSCALE_SYSTEM_ERROR_TIMEOUT_MS
                )
        else:
            entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_autoscale(args: argparse.Namespace) -> int:
    return _cmd_simple_advanced(args, "autoscale")


def _cmd_setup_save(args: argparse.Namespace) -> int:
    return _cmd_simple_advanced(args, "setup-save")


def _cmd_setup_recall(args: argparse.Namespace) -> int:
    return _cmd_simple_advanced(args, "setup-recall")


def _cmd_acquisition_check(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    with runtime._open_scope(args, resource) as scope:
        try:
            operation_result = run_acquisition_check(
                scope,
                resource,
                AcquisitionCheckRequest(
                    output_dir=args.output_dir,
                    average_count=args.average_count,
                    check_only=bool(getattr(args, "check_only", False)),
                    stop_on_error=bool(getattr(args, "stop_on_error", False)),
                    restore_type=bool(getattr(args, "restore_type", False)),
                    log_scpi=args.log_scpi,
                ),
            )
        except _OperationError as exc:
            operation_result = exc.result
            if operation_result.idn is not None:
                runtime._json_record_scope(scope, operation_result.idn)
            _apply_operation_result(operation_result)
            for line in operation_result.human_lines:
                print(line)
            raise OscilloscopeError(str(exc)) from exc
        if operation_result.idn is not None:
            runtime._json_record_scope(scope, operation_result.idn)
        _apply_operation_result(operation_result)
        for line in operation_result.human_lines:
            print(line)
        return operation_result.exit_code


def _default_capture_csv_path(now: datetime | None = None) -> Path:
    if now is None:
        capture_time = datetime.now(_CAPTURE_DEFAULT_TIMEZONE)
    elif now.tzinfo is None:
        capture_time = now.replace(tzinfo=_CAPTURE_DEFAULT_TIMEZONE)
    else:
        capture_time = now.astimezone(_CAPTURE_DEFAULT_TIMEZONE)

    return Path("data") / capture_time.strftime("%Y-%m-%d-%H-%M-%S.csv")


def _default_screenshot_path(
    now: datetime | None = None, *, extension: str = ".png"
) -> Path:
    if now is None:
        capture_time = datetime.now(_CAPTURE_DEFAULT_TIMEZONE)
    elif now.tzinfo is None:
        capture_time = now.replace(tzinfo=_CAPTURE_DEFAULT_TIMEZONE)
    else:
        capture_time = now.astimezone(_CAPTURE_DEFAULT_TIMEZONE)

    return Path("data") / (capture_time.strftime("%Y-%m-%d-%H-%M-%S") + extension)


def _screenshot_output_path(args: argparse.Namespace, format_name: str) -> Path:
    if args.output_path is not None:
        return Path(args.output_path)
    if format_name == "png":
        return _default_screenshot_path()
    return _default_screenshot_path(extension=".bmp")


def _write_screenshot_png(capture, output_path: Path) -> Path:
    try:
        return write_screenshot_png(capture, output_path)
    except OSError as exc:
        raise OscilloscopeError(
            _format_output_file_error("screenshot PNG", output_path, exc)
        ) from exc


def _write_screenshot(capture, output_path: Path, format_name: str) -> Path:
    try:
        return write_screenshot(capture, output_path)
    except OSError as exc:
        label = "screenshot PNG" if format_name == "png" else "screenshot BMP"
        raise OscilloscopeError(
            _format_output_file_error(label, output_path, exc)
        ) from exc


def _format_output_file_error(file_kind: str, path: Path, exc: OSError) -> str:
    reason = exc.strerror or str(exc)
    if file_kind.startswith("screenshot"):
        message = f"could not write {file_kind} file {path}: {reason}"
    else:
        message = f"could not write waveform {file_kind} file {path}: {reason}"
    if isinstance(exc, PermissionError):
        if file_kind.startswith("screenshot"):
            message += (
                ". The file may be open in another program, "
                "or the folder may not be writable."
            )
        else:
            message += (
                ". The file may be open in another program, such as Excel, "
                "or the folder may not be writable."
            )
    return message
