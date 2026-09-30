"""CLI dry-run planning for acquisition, setup, FFT, and Math commands."""

from __future__ import annotations

import argparse

from scopes_tool_core.acquisition import (
    acquisition_count_command,
    acquisition_count_query,
    acquisition_points_query,
    acquisition_type_command,
    acquisition_type_query,
    normalize_acquisition_type,
    record_length_query,
    validate_acquisition_count,
)
from scopes_tool_core.capabilities import ScopeCapabilities
from scopes_tool_core.channel import validate_analog_channel
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError
from scopes_tool_core.fft import (
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
    math_vertical_commands,
    math_vertical_query_commands,
    math_visualization_commands,
    math_visualization_query_commands,
)
from scopes_tool_core.planning import AcquisitionCheckPlanRequest, plan_acquisition_check
from scopes_tool_core.segmented import (
    ensure_segmented_memory_supported,
    segmented_count_command,
    segmented_mode_command,
    segmented_mode_query,
    validate_segmented_count,
)
from scopes_tool_core.segmented_capture import plan_segmented_capture
from scopes_tool_core.setup import (
    autoscale_commands,
    setup_recall_command,
    setup_save_command,
)
from scopes_tool_core.status import system_opc_query

from . import preflight
from .commands import acquisition


def _plan_acquisition_math(
    args: argparse.Namespace, capabilities: ScopeCapabilities
) -> tuple[list[str], list[dict[str, str]], dict[str, object]] | None:
    command = args.command
    if command == "acquisition-check":
        plan = plan_acquisition_check(
            AcquisitionCheckPlanRequest(
                output_dir=args.output_dir,
                average_count=args.average_count,
                check_only=bool(getattr(args, "check_only", False)),
                stop_on_error=bool(getattr(args, "stop_on_error", False)),
                restore_type=bool(getattr(args, "restore_type", False)),
            ),
            capabilities,
        )
        return list(plan.planned_scpi), list(plan.files), plan.result

    if command == "sample-rate":
        query_command = acquisition._sample_rate_query_command(args)
        planned = ["*IDN?", query_command, ":SYSTem:ERRor?"]
        result = {
            "operation": "query",
            "scpi_command": query_command,
            "planned_scpi": list(planned),
            "unit": "Hz",
        }
        if getattr(args, "sample_rate_maximum", False):
            result["query_kind"] = "maximum"
        return planned, [], result

    if command == "segmented-memory":
        if args.query:
            ensure_segmented_memory_supported(capabilities)
            return ["*IDN?", segmented_mode_query(), ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "mode": None,
                "configured_segments": None,
                "acquired_segments": None,
                "selected_segment": None,
                "time_tag_s": None,
                "raw_mode": None,
                "raw_configured_segments": None,
                "raw_acquired_segments": None,
                "raw_selected_segment": None,
                "raw_time_tag": None,
            }
        if args.enable:
            validated_segments = validate_segmented_count(
                args.segments, capabilities
            )
            return [
                "*IDN?",
                acquisition_type_query(),
                segmented_mode_command("segmented"),
                segmented_count_command(validated_segments),
                ":SYSTem:ERRor?",
            ], [], {
                "operation": "enable",
                "mode": "segmented",
                "configured_segments": validated_segments,
            }
        ensure_segmented_memory_supported(capabilities)
        return ["*IDN?", segmented_mode_command("realtime"), ":SYSTem:ERRor?"], [], {
            "operation": "disable",
            "mode": "realtime",
            "configured_segments": None,
        }

    if command == "segmented-capture":
        return plan_segmented_capture(preflight._segmented_capture_request(args), capabilities)

    if command == "acquisition-points":
        planned = ["*IDN?", acquisition_points_query(), ":SYSTem:ERRor?"]
        return planned, [], {
            "operation": "query",
            "scpi_command": acquisition_points_query(),
            "planned_scpi": list(planned),
            "unit": "points",
        }

    if command == "record-length":
        if capabilities.series != "4000X":
            raise ParameterValidationError(
                "record-length requires a 4000X capability profile."
            )
        planned = ["*IDN?", record_length_query(), ":SYSTem:ERRor?"]
        return planned, [], {
            "operation": "query",
            "scpi_command": record_length_query(),
            "planned_scpi": list(planned),
            "unit": "points",
        }

    if command == "acquisition":
        if args.acq_query and (args.acq_type is not None or args.acq_count is not None):
            raise OscilloscopeError("--query cannot be combined with --type or --count")
        if args.acq_query:
            commands = [acquisition_type_query(), acquisition_count_query()]
            return commands + [":SYSTem:ERRor?"], [], {"operation": "query", "commands": commands}
        if args.acq_type is None:
            raise OscilloscopeError("acquisition command requires --query or --type")
        normalized = normalize_acquisition_type(args.acq_type)
        planned = [acquisition_type_command(normalized)]
        count = None
        if args.acq_count is not None:
            count = validate_acquisition_count(args.acq_count)
            planned.append(acquisition_count_command(count))
        return planned + [":SYSTem:ERRor?"], [], {"operation": "set", "commands": planned, "type": args.acq_type, "scpi_type": normalized, "count": count}

    if command == "autoscale":
        channels = None if not args.source_channel else tuple(validate_analog_channel(channel, capabilities) for channel in args.source_channel)
        planned = autoscale_commands(channels, acquire_mode=args.acquire_mode, channels_mode=args.channels, capabilities=capabilities)
        return planned + [":SYSTem:ERRor?"], [], {"operation": "run", "commands": planned, "source_channels": None if channels is None else list(channels), "acquire_mode": args.acquire_mode, "channels": args.channels}

    if command == "setup-save":
        planned = [setup_save_command(slot=args.slot, file_spec=args.setup_file)]
        return planned + [system_opc_query(), ":SYSTem:ERRor?"], [], {"operation": "save", "command": planned[0], "slot": args.slot, "file": args.setup_file}

    if command == "setup-recall":
        planned = [setup_recall_command(slot=args.slot, file_spec=args.setup_file)]
        return planned + [system_opc_query(), ":SYSTem:ERRor?"], [], {"operation": "recall", "command": planned[0], "slot": args.slot, "file": args.setup_file}

    if command == "fft":
        if args.fft_query:
            commands = fft_query_commands(args.function, capabilities=capabilities)
            if capabilities.supports_advanced_fft:
                commands += fft_advanced_query_commands(
                    args.function, capabilities=capabilities
                )
            return commands + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "commands": commands,
                "function": args.function,
                "fft_operation": None,
                "fft_operation_canonical": None,
                "start_hz": None,
                "stop_hz": None,
                "gate": None,
                "phase_reference": None,
                "detection_type": None,
                "detection_points": None,
                "bin_size_hz": None,
                "sample_rate_hz": None,
                "resolution_bandwidth_hz": None,
            }
        assert args.source_channel is not None
        commands = fft_configure_commands(
            args.function,
            args.source_channel,
            units=args.units,
            window=args.window,
            center_hz=args.center_hz,
            span_hz=args.span_hz,
            display=None if args.display is None else args.display == "on",
            fft_operation=args.fft_operation or "fft",
            start_hz=args.start_hz,
            stop_hz=args.stop_hz,
            gate=args.gate,
            phase_reference=args.phase_reference,
            detection_type=args.detection_type,
            detection_points=args.detection_points,
            capabilities=capabilities,
        )
        return commands + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "commands": commands,
            "function": args.function,
            "source_channel": args.source_channel,
            "fft_operation_canonical": args.fft_operation or "fft",
            "units": args.units,
            "window": args.window,
            "center_hz": args.center_hz,
            "span_hz": args.span_hz,
            "start_hz": args.start_hz,
            "stop_hz": args.stop_hz,
            "gate": args.gate,
            "phase_reference": args.phase_reference,
            "detection_type": args.detection_type,
            "detection_points": args.detection_points,
            "display": args.display,
        }

    if command == "math-display":
        if args.math_display_action == "query":
            planned = math_display_query(args.function, capabilities=capabilities)
            return [planned, ":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "enabled": None,
                "raw": None,
            }
        enabled = args.math_display_action == "on"
        planned = math_display_command(
            args.function, enabled, capabilities=capabilities
        )
        return [planned, ":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "enabled": enabled,
            "command": planned,
        }
    if command == "math-vertical":
        if args.math_vertical_query:
            planned = math_vertical_query_commands(
                args.function, capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "scale": None,
                "range": None,
                "offset": None,
            }
        planned = math_vertical_commands(
            args.function,
            scale=args.scale,
            range_value=args.range_value,
            offset=args.offset,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "scale": args.scale,
            "range": args.range_value,
            "offset": args.offset,
            "commands": planned,
        }
    if command == "math-composite-source":
        if args.math_composite_query:
            planned = math_composite_source_query_commands(
                capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "math_operation": None,
                "operation_raw": None,
                "source1": None,
                "source1_raw": None,
                "source2": None,
                "source2_raw": None,
            }
        planned = math_composite_source_commands(
            args.math_composite_operation,
            args.source1,
            args.source2,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "math_operation": args.math_composite_operation,
            "source1": args.source1,
            "source2": args.source2,
            "commands": planned,
        }
    if command == "math-operator":
        if args.math_operator_query:
            planned = math_operator_query_commands(
                args.function, capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "math_operation": None,
                "operation_raw": None,
                "source1": None,
                "source1_raw": None,
                "source2": None,
                "source2_raw": None,
            }
        planned = math_operator_commands(
            args.function,
            args.math_operation,
            args.source1,
            args.source2,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "math_operation": args.math_operation,
            "source1": args.source1,
            "source2": args.source2,
            "commands": planned,
        }
    if command == "math-transform":
        if args.math_transform_query:
            planned = math_transform_query_commands(
                args.function, capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "math_operation": None,
                "operation_raw": None,
                "source": None,
                "source_raw": None,
                "input_offset": None,
                "gain": None,
                "linear_offset": None,
            }
        planned = math_transform_commands(
            args.function,
            args.math_transform_operation,
            args.source,
            input_offset=args.input_offset,
            gain=args.gain,
            linear_offset=args.linear_offset,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "math_operation": args.math_transform_operation,
            "source": args.source,
            "input_offset": args.input_offset,
            "gain": args.gain,
            "linear_offset": args.linear_offset,
            "commands": planned,
        }
    if command == "math-filter":
        if args.math_filter_query:
            planned = math_filter_query_commands(
                args.function, capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "math_operation": None,
                "operation_raw": None,
                "source": None,
                "source_raw": None,
                "cutoff_hz": None,
                "average_count": None,
                "smooth_points": None,
            }
        planned = math_filter_commands(
            args.function,
            args.math_filter_operation,
            args.source,
            cutoff_hz=args.cutoff_hz,
            average_count=args.average_count,
            smooth_points=args.smooth_points,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "math_operation": args.math_filter_operation,
            "source": args.source,
            "cutoff_hz": args.cutoff_hz,
            "average_count": args.average_count,
            "smooth_points": args.smooth_points,
            "commands": planned,
        }
    if command == "math-visualization":
        if args.math_visualization_query:
            planned = math_visualization_query_commands(
                args.function, capabilities=capabilities
            )
            return planned + [":SYSTem:ERRor?"], [], {
                "operation": "query",
                "function": args.function,
                "math_operation": None,
                "operation_raw": None,
                "source": None,
                "source_raw": None,
                "source2": None,
                "source2_raw": None,
                "measurement": None,
                "measurement_raw": None,
                "measurement_slot": None,
            }
        planned = math_visualization_commands(
            args.function,
            args.math_visualization_operation,
            source=args.source,
            source2=args.source2,
            measurement=args.measurement,
            measurement_slot=args.measurement_slot,
            capabilities=capabilities,
        )
        return planned + [":SYSTem:ERRor?"], [], {
            "operation": "set",
            "function": args.function,
            "math_operation": args.math_visualization_operation,
            "source": args.source,
            "source2": args.source2,
            "measurement": args.measurement,
            "measurement_slot": args.measurement_slot,
            "commands": planned,
        }
    if command == "math-clear":
        planned = math_clear_command(args.function, capabilities=capabilities)
        return [planned, ":SYSTem:ERRor?"], [], {
            "operation": "clear",
            "function": args.function,
            "cleared": True,
            "command": planned,
        }
    return None
