"""CLI pre-open argument validation."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from scopes_tool_core.acquisition import (
    normalize_acquisition_type,
    validate_acquisition_count,
)
from scopes_tool_core.segmented import validate_segmented_count
from scopes_tool_core.segmented_capture import (
    SegmentedCaptureRequest,
    validate_segmented_capture_output_path,
    validate_segmented_capture_request,
)
from scopes_tool_core.advanced import (
    fft_configure_commands,
    fft_advanced_query_commands,
    fft_query_commands,
    math_display_command,
    math_display_query,
    math_clear_command,
    math_composite_source_commands,
    math_composite_source_query_commands,
    math_operator_commands,
    math_operator_query_commands,
    math_filter_commands,
    math_filter_query_commands,
    math_transform_commands,
    math_transform_query_commands,
    math_visualization_commands,
    math_visualization_query_commands,
    math_vertical_commands,
    math_vertical_query_commands,
)
from scopes_tool_core.capabilities import (
    ScopeCapabilities,
    capabilities_for_model_id,
)
from scopes_tool_core.channel import validate_analog_channel
from scopes_tool_core.display import (
    validate_display_intensity,
    validate_display_persistence,
)
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError
from scopes_tool_core.reference import (
    validate_reference_label,
    validate_reference_slot,
)
from scopes_tool_core.demo import validate_demo_function, validate_demo_phase
from scopes_tool_core.wgen import (
    validate_wgen_amplitude,
    validate_wgen_frequency,
    validate_wgen_function,
    validate_wgen_offset,
)
from scopes_tool_core.save_export import (
    validate_save_filename_base,
    validate_save_quoted_string,
    validate_save_waveform_length,
)
from scopes_tool_core.search import (
    require_search_basic,
    validate_can_data_length,
    validate_can_id_mode,
    validate_can_search_criteria,
    validate_can_search_mode,
    validate_i2c_pattern_value,
    validate_i2c_search_mode,
    validate_pattern_hex_x,
    validate_search_event,
    validate_search_mode,
    validate_search_qualifier,
    validate_serial_search_bus,
    validate_spi_search_pattern_width,
    validate_spi_search_mode,
    validate_spi_width,
    validate_uart_data,
    validate_uart_search_mode,
)
from scopes_tool_core.serial import (
    serial_can_configure_commands,
    serial_i2c_configure_commands,
    serial_spi_configure_commands,
    serial_uart_configure_commands,
    validate_serial_uart_trigger_request,
    validate_serial_i2c_trigger_request,
    validate_serial_spi_trigger_request,
    validate_serial_can_trigger_request,
    normalize_can_signal_definition,
    normalize_i2c_address_size,
    normalize_serial_bit_order,
    normalize_serial_source,
    normalize_spi_clock_slope,
    normalize_spi_framing,
    normalize_uart_parity,
    normalize_uart_polarity,
    validate_can_baud_rate,
    validate_can_sample_point,
    validate_uart_baud_rate,
    validate_serial_bus,
    validate_serial_mode,
    validate_serial_lister_display,
    validate_serial_lister_reference,
    validate_spi_framing_clock_timeout,
    require_serial_decode,
)
from scopes_tool_core.screenshot import (
    ScreenshotOptions,
    normalize_screenshot_options,
)
from scopes_tool_core.trigger import (
    normalize_edge_burst_slope,
    normalize_delay_slope,
    normalize_glitch_qualifier,
    normalize_runt_qualifier,
    normalize_setup_hold_slope,
    normalize_transition_qualifier,
    normalize_transition_slope,
    normalize_trigger_sweep,
    tv_trigger_configure_commands,
    validate_delay_trigger_count,
    validate_delay_trigger_time,
    validate_edge_burst_count,
    validate_edge_burst_idle_time,
    validate_external_trigger_range,
    validate_external_trigger_probe_attenuation,
    validate_external_trigger_units,
    validate_or_trigger_pattern,
    validate_pattern_trigger_pattern,
    validate_setup_hold_trigger_time,
    validate_trigger_level,
    validate_trigger_time,
)
def _screenshot_options(args: argparse.Namespace) -> ScreenshotOptions:
    return normalize_screenshot_options(
        ScreenshotOptions(
            format=getattr(args, "format", None),
            ink_saver=getattr(args, "ink_saver", None),
            palette=getattr(args, "palette", None),
            layout=getattr(args, "layout", None),
        )
    )

def _uses_screenshot_format_pack(args: argparse.Namespace) -> bool:
    options = _screenshot_options(args)
    return bool(
        getattr(args, "query_hardcopy", False)
        or options.format is not None
        or options.ink_saver is not None
        or options.palette is not None
        or options.layout is not None
    )

def _validate_screenshot_args(args: argparse.Namespace) -> None:
    options = _screenshot_options(args)
    if getattr(args, "query_hardcopy", False):
        conflicting = (
            getattr(args, "output_path", None) is not None
            or getattr(args, "background", None) is not None
            or any(
                value is not None
                for value in (
                    options.format,
                    options.ink_saver,
                    options.palette,
                    options.layout,
                )
            )
        )
        if conflicting:
            raise ParameterValidationError(
                "--query-hardcopy cannot be combined with screenshot capture or setting options."
            )
    if getattr(args, "background", None) is not None and options.ink_saver is not None:
        raise ParameterValidationError("--background cannot be combined with --ink-saver.")
    if options.format is not None and getattr(args, "output_path", None) is not None:
        expected = ".png" if options.format == "png" else ".bmp"
        if Path(args.output_path).suffix.lower() != expected:
            raise ParameterValidationError(
                f"--format {options.format} requires an output path ending in {expected}."
            )
    if _uses_screenshot_format_pack(args):
        capabilities = _pre_open_capabilities(args)
        if (
            capabilities is not None
            and not capabilities.supports_screenshot_format_pack
        ):
            raise ParameterValidationError(
                "Screenshot Format Pack v1 requires a 4000X model profile."
            )

def _validate_fft_args(args: argparse.Namespace) -> None:
    capabilities = _pre_open_capabilities(args)
    configure_values = (
        args.source_channel,
        args.units,
        args.window,
        args.center_hz,
        args.span_hz,
        args.fft_operation,
        args.start_hz,
        args.stop_hz,
        args.gate,
        args.phase_reference,
        args.detection_type,
        args.detection_points,
        args.display,
    )
    if args.fft_query:
        if any(value is not None for value in configure_values):
            raise ParameterValidationError(
                "--query cannot be combined with FFT configuration options."
            )
        fft_query_commands(args.function, capabilities=capabilities)
        if capabilities is not None and capabilities.supports_advanced_fft:
            fft_advanced_query_commands(
                args.function, capabilities=capabilities
            )
        return
    if args.source_channel is None:
        raise ParameterValidationError(
            "fft configure requires --source-channel unless --query is used."
        )
    fft_configure_commands(
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

def _segmented_capture_request(args: argparse.Namespace) -> SegmentedCaptureRequest:
    return SegmentedCaptureRequest(
        channel=args.channel,
        segments=args.segments,
        points=args.points,
        waveform_format=args.waveform_format,
        timeout_ms=args.timeout_ms,
        poll_interval_ms=args.poll_interval_ms,
        output_dir=args.output_dir,
        log_scpi=bool(getattr(args, "log_scpi", False)),
    )

def _validate_pre_open_args(args: argparse.Namespace) -> None:
    if getattr(args, "command", None) == "acquisition":
        if (
            getattr(args, "acq_count", None) is not None
            and not getattr(args, "acq_query", False)
        ):
            if (
                getattr(args, "acq_type", None) is None
                or normalize_acquisition_type(args.acq_type) != "AVERage"
            ):
                raise OscilloscopeError("--count can only be used with --type average")
            validate_acquisition_count(args.acq_count)
    if getattr(args, "command", None) == "segmented-memory":
        if getattr(args, "enable", False) and args.segments is None:
            raise ParameterValidationError("segmented-memory --enable requires --segments")
        if not getattr(args, "enable", False) and args.segments is not None:
            raise ParameterValidationError(
                "--segments is only valid with segmented-memory --enable"
            )
        if (
            args.segments is not None
            and (getattr(args, "simulate", False) or getattr(args, "dry_run", False))
        ):
            validate_segmented_count(
                args.segments, capabilities_for_model_id(args.model)
            )
    if getattr(args, "command", None) == "segmented-capture":
        request = _segmented_capture_request(args)
        validate_segmented_capture_request(request)
        validate_segmented_capture_output_path(request.output_dir)
        capabilities = _pre_open_capabilities(args)
        if capabilities is not None:
            validate_segmented_capture_request(request, capabilities)
    if getattr(args, "command", None) == "fft":
        _validate_fft_args(args)
    if getattr(args, "command", None) == "screenshot":
        _validate_screenshot_args(args)
    if getattr(args, "command", None) == "channel-impedance":
        if (
            getattr(args, "impedance_value", None) == "fifty"
            and not getattr(args, "allow_50_ohm", False)
        ):
            raise ParameterValidationError(
                "setting 50 ohm input impedance requires --allow-50-ohm."
            )
    if getattr(args, "command", None) == "display-persistence":
        actions = [
            bool(getattr(args, "query", False)),
            getattr(args, "mode", None) is not None,
            getattr(args, "seconds", None) is not None,
        ]
        if sum(actions) != 1:
            raise ParameterValidationError(
                "display-persistence requires exactly one of --query, --mode, or --seconds."
            )
        if getattr(args, "mode", None) is not None:
            validate_display_persistence(args.mode)
        if getattr(args, "seconds", None) is not None:
            validate_display_persistence(args.seconds)
    if getattr(args, "command", None) == "display-intensity":
        actions = [
            bool(getattr(args, "query", False)),
            getattr(args, "value", None) is not None,
        ]
        if sum(actions) != 1:
            raise ParameterValidationError(
                "display-intensity requires exactly one of --query or --value."
            )
        if getattr(args, "value", None) is not None:
            validate_display_intensity(args.value)
    if getattr(args, "command", None) == "display-vectors":
        actions = [
            bool(getattr(args, "query", False)),
            bool(getattr(args, "on", False)),
            bool(getattr(args, "off", False)),
        ]
        if sum(actions) != 1:
            raise ParameterValidationError(
                "display-vectors requires exactly one of --query or --on."
            )
        if getattr(args, "off", False):
            raise ParameterValidationError("display-vectors set OFF is not supported.")
    if getattr(args, "command", None) in {
        "measure-show",
        "measure-source",
        "measure-window",
        "reference-save",
        "reference-display",
        "reference-label",
        "reference-clear",
        "reference-query",
    }:
        _validate_measurement_reference_args(args)
    if getattr(args, "command", None) in {
        "dvm-enable",
        "dvm-source",
        "dvm-mode",
        "dvm-auto-range",
    }:
        _validate_dvm_args(args)
    if getattr(args, "command", None) in {
        "demo-query",
        "demo-output",
        "demo-function",
        "demo-phase",
    }:
        _validate_demo_args(args)
    if getattr(args, "command", None) in {
        "wgen-query",
        "wgen-output",
        "wgen-function",
        "wgen-frequency",
        "wgen-voltage",
        "wgen-offset",
        "wgen-load",
    }:
        _validate_wgen_args(args)
    if getattr(args, "command", None) in {
        "serial-query",
        "serial-mode",
        "serial-display",
        "serial-uart",
        "serial-trigger-uart",
        "serial-i2c",
        "serial-spi",
        "serial-can",
        "serial-lister-query",
        "serial-lister-display",
        "serial-lister-reference",
        "serial-lister-export",
    }:
        _validate_serial_args(args)
    if getattr(args, "command", None) in {
        "search-state",
        "search-mode",
        "search-count",
        "search-event",
    }:
        _validate_search_args(args)
    if getattr(args, "command", None) in {
        "serial-search-uart",
        "serial-search-i2c",
        "serial-search-spi",
        "serial-search-can",
    }:
        _validate_serial_search_args(args)
    if getattr(args, "command", None) in {
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
    }:
        _validate_save_export_args(args)
    if getattr(args, "command", None) == "trigger-edge":
        _validate_trigger_edge_args(args)
    if getattr(args, "command", None) == "trigger-edge-source":
        _validate_trigger_edge_source_args(args)
    if getattr(args, "command", None) == "trigger-edge-slope":
        _validate_trigger_edge_slope_args(args)
    if getattr(args, "command", None) == "trigger-edge-level":
        _validate_trigger_edge_level_args(args)
    if getattr(args, "command", None) == "external-trigger-range":
        _validate_external_trigger_range_args(args)
    if getattr(args, "command", None) == "trigger-edge-external-level":
        _validate_trigger_edge_external_level_args(args)
    if getattr(args, "command", None) == "external-trigger-probe":
        _validate_external_trigger_probe_args(args)
    if getattr(args, "command", None) == "external-trigger-units":
        _validate_external_trigger_units_args(args)
    if getattr(args, "command", None) == "external-trigger-settings":
        _validate_external_trigger_settings_args(args)
    if getattr(args, "command", None) == "trigger-sweep":
        _validate_trigger_sweep_args(args)
    if getattr(args, "command", None) == "trigger-noise-reject":
        _validate_trigger_reject_args(args, "trigger-noise-reject")
    if getattr(args, "command", None) == "trigger-hf-reject":
        _validate_trigger_reject_args(args, "trigger-hf-reject")
    if getattr(args, "command", None) == "trigger-edge-coupling":
        _validate_edge_coupling_args(args)
    if getattr(args, "command", None) == "trigger-edge-reject":
        _validate_edge_reject_args(args)
    if getattr(args, "command", None) == "trigger-pulse-width":
        _validate_trigger_glitch_args(args)
    if getattr(args, "command", None) == "trigger-runt":
        _validate_trigger_runt_args(args)
    if getattr(args, "command", None) == "trigger-transition":
        _validate_trigger_transition_args(args)
    if getattr(args, "command", None) == "trigger-delay":
        _validate_trigger_delay_args(args)
    if getattr(args, "command", None) == "trigger-setup-hold":
        _validate_trigger_setup_hold_args(args)
    if getattr(args, "command", None) == "trigger-edge-burst":
        _validate_trigger_edge_burst_args(args)
    if getattr(args, "command", None) == "trigger-tv":
        _validate_trigger_tv_args(args)
    if getattr(args, "command", None) == "trigger-pattern":
        _validate_trigger_pattern_args(args)
    if getattr(args, "command", None) == "trigger-or":
        _validate_trigger_or_args(args)
    if getattr(args, "command", None) in {
        "math-display",
        "math-vertical",
        "math-operator",
        "math-composite-source",
        "math-transform",
        "math-filter",
        "math-visualization",
        "math-clear",
    }:
        _validate_math_args(args)

def _validate_math_args(args: argparse.Namespace) -> None:
    capabilities = _pre_open_capabilities(args)
    if args.command == "math-composite-source":
        configure_values = (
            args.math_composite_operation,
            args.source1,
            args.source2,
        )
        if args.math_composite_query:
            if any(value is not None for value in configure_values):
                raise ParameterValidationError(
                    "math-composite-source --query cannot be combined with "
                    "configure options."
                )
            math_composite_source_query_commands(capabilities=capabilities)
            return
        if any(value is None for value in configure_values):
            raise ParameterValidationError(
                "math-composite-source configure requires --operation, "
                "--source1, and --source2."
            )
        math_composite_source_commands(
            args.math_composite_operation,
            args.source1,
            args.source2,
            capabilities=capabilities,
        )
        return

    if args.command == "math-display":
        if args.math_display_action == "query":
            math_display_query(args.function, capabilities=capabilities)
        else:
            math_display_command(
                args.function,
                args.math_display_action == "on",
                capabilities=capabilities,
            )
        return

    if args.command == "math-vertical":
        if args.math_vertical_query:
            if any(
                value is not None
                for value in (args.scale, args.range_value, args.offset)
            ):
                raise ParameterValidationError(
                    "math-vertical --query cannot be combined with configure options."
                )
            math_vertical_query_commands(args.function, capabilities=capabilities)
            return
        math_vertical_commands(
            args.function,
            scale=args.scale,
            range_value=args.range_value,
            offset=args.offset,
            capabilities=capabilities,
        )
        return

    if args.command == "math-transform":
        configure_values = (
            args.math_transform_operation,
            args.source,
            args.input_offset,
            args.gain,
            args.linear_offset,
        )
        if args.math_transform_query:
            if any(value is not None for value in configure_values):
                raise ParameterValidationError(
                    "math-transform --query cannot be combined with configure options."
                )
            math_transform_query_commands(
                args.function, capabilities=capabilities
            )
            return
        if args.math_transform_operation is None or args.source is None:
            raise ParameterValidationError(
                "math-transform configure requires --operation and --source."
            )
        math_transform_commands(
            args.function,
            args.math_transform_operation,
            args.source,
            input_offset=args.input_offset,
            gain=args.gain,
            linear_offset=args.linear_offset,
            capabilities=capabilities,
        )
        return

    if args.command == "math-filter":
        configure_values = (
            args.math_filter_operation,
            args.source,
            args.cutoff_hz,
            args.average_count,
            args.smooth_points,
        )
        if args.math_filter_query:
            if any(value is not None for value in configure_values):
                raise ParameterValidationError(
                    "math-filter --query cannot be combined with configure options."
                )
            math_filter_query_commands(args.function, capabilities=capabilities)
            return
        if args.math_filter_operation is None or args.source is None:
            raise ParameterValidationError(
                "math-filter configure requires --operation and --source."
            )
        math_filter_commands(
            args.function,
            args.math_filter_operation,
            args.source,
            cutoff_hz=args.cutoff_hz,
            average_count=args.average_count,
            smooth_points=args.smooth_points,
            capabilities=capabilities,
        )
        return

    if args.command == "math-visualization":
        configure_values = (
            args.math_visualization_operation,
            args.source,
            args.source2,
            args.measurement,
            args.measurement_slot,
        )
        if args.math_visualization_query:
            if any(value is not None for value in configure_values):
                raise ParameterValidationError(
                    "math-visualization --query cannot be combined with "
                    "configure options."
                )
            math_visualization_query_commands(
                args.function, capabilities=capabilities
            )
            return
        if args.math_visualization_operation is None:
            raise ParameterValidationError(
                "math-visualization configure requires --operation."
            )
        math_visualization_commands(
            args.function,
            args.math_visualization_operation,
            source=args.source,
            source2=args.source2,
            measurement=args.measurement,
            measurement_slot=args.measurement_slot,
            capabilities=capabilities,
        )
        return

    if args.command == "math-clear":
        math_clear_command(args.function, capabilities=capabilities)
        return

    configure_values = (args.math_operation, args.source1, args.source2)
    if args.math_operator_query:
        if any(value is not None for value in configure_values):
            raise ParameterValidationError(
                "math-operator --query cannot be combined with configure options."
            )
        math_operator_query_commands(args.function, capabilities=capabilities)
        return
    if any(value is None for value in configure_values):
        raise ParameterValidationError(
            "math-operator configure requires --operation, --source1, and --source2."
        )
    math_operator_commands(
        args.function,
        args.math_operation,
        args.source1,
        args.source2,
        capabilities=capabilities,
    )

def _pre_open_capabilities(
    args: argparse.Namespace,
) -> ScopeCapabilities | None:
    if (
        bool(getattr(args, "simulate", False))
        or bool(getattr(args, "dry_run", False))
        or bool(getattr(args, "_worker_live_validation", False))
    ):
        return capabilities_for_model_id(args.model)
    return None

def _validate_dvm_args(args: argparse.Namespace) -> None:
    command = args.command
    query = bool(getattr(args, "query", False))
    configure_key = {
        "dvm-enable": "enabled",
        "dvm-source": "channel",
        "dvm-mode": "mode",
        "dvm-auto-range": "enabled",
    }[command]
    value = getattr(args, configure_key, None)
    if query:
        if value is not None:
            raise ParameterValidationError(
                f"{command} --query cannot be combined with configure options."
            )
        return
    if value is None:
        raise ParameterValidationError(
            f"{command} configure requires --{configure_key.replace('_', '-')}."
        )
    if command == "dvm-source":
        capabilities = _pre_open_capabilities(args)
        if capabilities is not None:
            validate_analog_channel(value, capabilities)

def _validate_demo_args(args: argparse.Namespace) -> None:
    capabilities = _pre_open_capabilities(args)
    if capabilities is not None and not capabilities.supports_demo:
        raise ParameterValidationError(
            "Demo Output Pack v1 is not supported by the selected model profile."
        )
    if (
        capabilities is not None
        and args.command == "demo-function"
        and not args.query
    ):
        validate_demo_function(args.function, capabilities)
    if args.command == "demo-phase" and not args.query:
        validate_demo_phase(args.degrees)

def _validate_wgen_args(args: argparse.Namespace) -> None:
    capabilities = _pre_open_capabilities(args)
    if capabilities is not None and not capabilities.supports_wgen:
        raise ParameterValidationError(
            "WGEN Basic P1 is not supported by the selected model profile."
        )
    if args.command == "wgen-query" or args.query:
        return
    if args.command == "wgen-function":
        validate_wgen_function(args.function)
    elif args.command == "wgen-frequency":
        validate_wgen_frequency(args.hz)
    elif args.command == "wgen-voltage":
        validate_wgen_amplitude(args.amplitude)
    elif args.command == "wgen-offset":
        validate_wgen_offset(args.volts)

def _validate_serial_args(args: argparse.Namespace) -> None:
    if args.command in {
        "serial-lister-query",
        "serial-lister-display",
        "serial-lister-reference",
        "serial-lister-export",
    }:
        _validate_serial_lister_args(args)
        return
    capabilities = _pre_open_capabilities(args)
    if args.command == "serial-trigger-uart":
        validate_serial_uart_trigger_request(
            args.bus,
            query=args.query,
            type=args.type,
            data=args.data,
            qualifier=args.qualifier,
            capabilities=capabilities,
        )
        return
    trigger_validators = {
        "serial-trigger-i2c": validate_serial_i2c_trigger_request,
        "serial-trigger-spi": validate_serial_spi_trigger_request,
        "serial-trigger-can": validate_serial_can_trigger_request,
    }
    if args.command in trigger_validators:
        trigger_validators[args.command](
            args.bus,
            query=args.query,
            **{
                key: getattr(args, key)
                for key in {
                    "serial-trigger-i2c": {"type", "address", "data", "data2", "qualifier"},
                    "serial-trigger-spi": {"type", "width", "data"},
                    "serial-trigger-can": {"type", "id", "id_mode", "data", "data_length"},
                }[args.command]
            },
            capabilities=capabilities,
        )
        return
    if capabilities is not None:
        validate_serial_bus(args.bus, capabilities)
        if args.command == "serial-mode" and not args.query:
            validate_serial_mode(args.mode, capabilities)
    if args.command in {"serial-uart", "serial-i2c", "serial-spi", "serial-can"}:
        _validate_serial_protocol_args(args, capabilities)

def _validate_serial_lister_args(args: argparse.Namespace) -> None:
    capabilities = _pre_open_capabilities(args)
    if capabilities is None:
        return
    require_serial_decode(capabilities)
    if args.command == "serial-lister-display" and not args.query:
        validate_serial_lister_display(args.selection, capabilities)
    elif args.command == "serial-lister-reference" and not args.query:
        validate_serial_lister_reference(args.reference, capabilities)

def _validate_serial_protocol_args(
    args: argparse.Namespace, capabilities: ScopeCapabilities | None
) -> None:
    fields_by_command = {
        "serial-uart": ("rx_source", "tx_source", "baud_rate", "data_bits", "parity", "polarity", "bit_order"),
        "serial-i2c": ("clock_source", "data_source", "address_size"),
        "serial-spi": ("clock_source", "mosi_source", "miso_source", "frame_source", "clock_slope", "bit_order", "word_width", "framing", "clock_timeout"),
        "serial-can": ("source", "baud_rate", "signal_definition", "sample_point"),
    }
    fields = fields_by_command[args.command]
    supplied = {field: getattr(args, field) for field in fields if getattr(args, field) is not None}
    if args.query:
        if supplied:
            raise ParameterValidationError(
                f"{args.command} --query cannot be combined with configure arguments."
            )
        return
    if not supplied:
        raise ParameterValidationError(
            f"{args.command} configure requires at least one setting."
        )
    if capabilities is None:
        return
    protocol_mode = {
        "serial-uart": "uart",
        "serial-i2c": "i2c",
        "serial-spi": "spi",
        "serial-can": "can",
    }[args.command]
    validate_serial_mode(protocol_mode, capabilities)
    if args.command == "serial-uart":
        serial_uart_configure_commands(
            args.bus,
            _serial_cli_values(
                capabilities,
                protocol=args.command,
                rx_source=args.rx_source,
                tx_source=args.tx_source,
                baud_rate=args.baud_rate,
                data_bits=args.data_bits,
                parity=args.parity,
                polarity=args.polarity,
                bit_order=args.bit_order,
            ),
        )
    elif args.command == "serial-i2c":
        serial_i2c_configure_commands(
            args.bus,
            _serial_cli_values(
                capabilities,
                protocol=args.command,
                clock_source=args.clock_source,
                data_source=args.data_source,
                address_size=args.address_size,
            ),
        )
    elif args.command == "serial-spi":
        serial_spi_configure_commands(
            args.bus,
            _serial_cli_values(
                capabilities,
                protocol=args.command,
                clock_source=args.clock_source,
                mosi_source=args.mosi_source,
                miso_source=args.miso_source,
                frame_source=args.frame_source,
                clock_slope=args.clock_slope,
                bit_order=args.bit_order,
                word_width=args.word_width,
                framing=args.framing,
                clock_timeout=args.clock_timeout,
            ),
        )
    else:
        serial_can_configure_commands(
            args.bus,
            _serial_cli_values(
                capabilities,
                protocol=args.command,
                source=args.source,
                baud_rate=args.baud_rate,
                signal_definition=args.signal_definition,
                sample_point=args.sample_point,
            ),
        )

def _serial_cli_values(
    capabilities: ScopeCapabilities, *, protocol: str | None = None, **values: object
) -> dict[str, object]:
    normalized = dict(values)
    source_fields = {
        "rx_source", "tx_source", "clock_source", "data_source", "mosi_source",
        "miso_source", "frame_source", "source",
    }
    for field in source_fields:
        if normalized.get(field) is not None:
            normalized[field] = normalize_serial_source(normalized[field], capabilities)
    if normalized.get("parity") is not None:
        normalized["parity"] = normalize_uart_parity(normalized["parity"])
    if normalized.get("polarity") is not None:
        normalized["polarity"] = normalize_uart_polarity(normalized["polarity"])
    if normalized.get("bit_order") is not None:
        normalized["bit_order"] = normalize_serial_bit_order(normalized["bit_order"])
    if normalized.get("address_size") is not None:
        normalized["address_size"] = normalize_i2c_address_size(normalized["address_size"])
    if normalized.get("clock_slope") is not None:
        normalized["clock_slope"] = normalize_spi_clock_slope(normalized["clock_slope"])
    if normalized.get("framing") is not None:
        normalized["framing"] = normalize_spi_framing(normalized["framing"])
    if normalized.get("signal_definition") is not None:
        normalized["signal_definition"] = normalize_can_signal_definition(normalized["signal_definition"])
    if normalized.get("baud_rate") is not None:
        if protocol == "serial-can":
            normalized["baud_rate"] = validate_can_baud_rate(normalized["baud_rate"])
        else:
            normalized["baud_rate"] = validate_uart_baud_rate(normalized["baud_rate"], capabilities)
    if normalized.get("data_bits") is not None:
        if isinstance(normalized["data_bits"], bool) or not isinstance(normalized["data_bits"], int) or not 5 <= normalized["data_bits"] <= 9:
            raise ParameterValidationError("UART data bits must be an integer in range 5-9.")
    if normalized.get("word_width") is not None:
        if isinstance(normalized["word_width"], bool) or not isinstance(normalized["word_width"], int) or not 4 <= normalized["word_width"] <= 16:
            raise ParameterValidationError("SPI word width must be an integer in range 4-16.")
    if normalized.get("clock_timeout") is not None:
        value = normalized["clock_timeout"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1e-7 <= float(value) <= 10.0 or not math.isfinite(float(value)):
            raise ParameterValidationError("SPI clock timeout must be a number in range 1e-07-10.0.")
    if protocol == "serial-spi":
        validate_spi_framing_clock_timeout(
            normalized.get("framing"), normalized.get("clock_timeout")
        )
    if normalized.get("sample_point") is not None:
        normalized["sample_point"] = validate_can_sample_point(normalized["sample_point"], capabilities)
    return normalized

def _validate_search_args(args: argparse.Namespace) -> None:
    command = args.command
    capabilities = _pre_open_capabilities(args)
    if command == "search-event":
        if capabilities is not None and not capabilities.supports_search_event_navigation:
            raise ParameterValidationError(
                "Search event navigation is not supported by the selected model profile."
            )
        if args.query and args.event is not None:
            raise ParameterValidationError(
                "search-event --query cannot be combined with configure options."
            )
        if not args.query and args.event is None:
            raise ParameterValidationError(
                "search-event configure requires --event."
            )
        if not args.query and args.event is not None:
            validate_search_event(args.event)
        return

    if capabilities is not None and not capabilities.supports_search_basic:
        raise ParameterValidationError(
            "Search Basic Pack v1 is not supported by the selected model profile."
        )
    if command == "search-count":
        return
    query = bool(getattr(args, "query", False))
    configure_key = "enabled" if command == "search-state" else "mode"
    value = getattr(args, configure_key, None)
    if query:
        if value is not None:
            raise ParameterValidationError(
                f"{command} --query cannot be combined with configure options."
            )
        return
    if value is None:
        raise ParameterValidationError(
            f"{command} configure requires --{configure_key}."
        )
    if command == "search-mode" and capabilities is not None:
        validate_search_mode(value, capabilities)

def _extract_serial_search_settings(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "serial-search-can":
        settings = {}
        if getattr(args, "mode", None) is not None:
            settings["mode"] = args.mode
        if getattr(args, "data", None) is not None:
            settings["data"] = args.data
        if getattr(args, "data_length", None) is not None:
            settings["data_length"] = args.data_length
        if getattr(args, "id", None) is not None:
            settings["id_val"] = args.id
        if getattr(args, "id_mode", None) is not None:
            settings["id_mode"] = args.id_mode
        return settings
    fields = {
        "serial-search-uart": ("mode", "data", "qualifier"),
        "serial-search-i2c": ("mode", "address", "data", "data2", "qualifier"),
        "serial-search-spi": ("mode", "data", "width"),
    }[args.command]
    return {f: getattr(args, f) for f in fields if getattr(args, f) is not None}

def _canonical_serial_search_settings(
    args: argparse.Namespace,
) -> dict[str, object]:
    settings = _extract_serial_search_settings(args)
    if "mode" not in settings or settings["mode"] is None:
        raise ParameterValidationError(f"{args.command} configure requires --mode.")

    protocol = args.command.removeprefix("serial-search-")
    canonical_settings = dict(settings)
    if protocol == "uart":
        canonical_settings["mode"] = validate_uart_search_mode(settings["mode"])
        if "data" in settings:
            canonical_settings["data"] = validate_uart_data(settings["data"])
        if "qualifier" in settings:
            canonical_settings["qualifier"] = validate_search_qualifier(settings["qualifier"])
    elif protocol == "i2c":
        canonical_settings["mode"] = validate_i2c_search_mode(settings["mode"])
        if "address" in settings:
            canonical_settings["address"] = validate_i2c_pattern_value(settings["address"], "address")
        if "data" in settings:
            canonical_settings["data"] = validate_i2c_pattern_value(settings["data"], "data")
        if "data2" in settings:
            canonical_settings["data2"] = validate_i2c_pattern_value(settings["data2"], "data2")
        if "qualifier" in settings:
            canonical_settings["qualifier"] = validate_search_qualifier(settings["qualifier"])
    elif protocol == "spi":
        canonical_settings["mode"] = validate_spi_search_mode(settings["mode"])
        if "data" in settings:
            canonical_settings["data"] = validate_pattern_hex_x(settings["data"], "data")
        if "width" in settings:
            canonical_settings["width"] = validate_spi_width(settings["width"])
        validate_spi_search_pattern_width(
            canonical_settings.get("data"), canonical_settings.get("width")
        )
    elif protocol == "can":
        canonical_settings["mode"] = validate_can_search_mode(settings["mode"])
        if "data" in settings:
            canonical_settings["data"] = validate_pattern_hex_x(settings["data"], "data")
        if "data_length" in settings:
            canonical_settings["data_length"] = validate_can_data_length(settings["data_length"])
        if "id_val" in settings:
            canonical_settings["id_val"] = validate_pattern_hex_x(settings["id_val"], "id")
        if "id_mode" in settings:
            canonical_settings["id_mode"] = validate_can_id_mode(settings["id_mode"])
        validate_can_search_criteria(
            canonical_settings["mode"],
            data=canonical_settings.get("data"),
            data_length=canonical_settings.get("data_length"),
            id_val=canonical_settings.get("id_val"),
            id_mode=canonical_settings.get("id_mode"),
        )
    return canonical_settings

def _validate_serial_search_args(args: argparse.Namespace) -> None:
    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        require_search_basic(capabilities)
        validate_serial_search_bus(args.bus, capabilities)
        protocol = args.command.removeprefix("serial-search-")
        validate_serial_mode(protocol, capabilities)

    query = bool(getattr(args, "query", False))
    settings = _extract_serial_search_settings(args)
    if query:
        if settings:
            raise ParameterValidationError(
                f"{args.command} --query cannot be combined with configure options."
            )
        return

    if "mode" not in settings:
        raise ParameterValidationError(f"{args.command} configure requires --mode.")

    protocol = args.command.removeprefix("serial-search-")
    if protocol == "uart":
        validate_uart_search_mode(settings["mode"])
        if "data" in settings:
            validate_uart_data(settings["data"])
        if "qualifier" in settings:
            validate_search_qualifier(settings["qualifier"])
    elif protocol == "i2c":
        validate_i2c_search_mode(settings["mode"])
        if "address" in settings:
            validate_i2c_pattern_value(settings["address"], "address")
        if "data" in settings:
            validate_i2c_pattern_value(settings["data"], "data")
        if "data2" in settings:
            validate_i2c_pattern_value(settings["data2"], "data2")
        if "qualifier" in settings:
            validate_search_qualifier(settings["qualifier"])
    elif protocol == "spi":
        validate_spi_search_mode(settings["mode"])
        canonical_data = None
        canonical_width = None
        if "data" in settings:
            canonical_data = validate_pattern_hex_x(settings["data"], "data")
        if "width" in settings:
            canonical_width = validate_spi_width(settings["width"])
        validate_spi_search_pattern_width(canonical_data, canonical_width)
    elif protocol == "can":
        canonical_mode = validate_can_search_mode(settings["mode"])
        canonical_data = None
        canonical_data_length = None
        canonical_id = None
        canonical_id_mode = None
        if "data" in settings:
            canonical_data = validate_pattern_hex_x(settings["data"], "data")
        if "data_length" in settings:
            canonical_data_length = validate_can_data_length(settings["data_length"])
        if "id_val" in settings:
            canonical_id = validate_pattern_hex_x(settings["id_val"], "id")
        if "id_mode" in settings:
            canonical_id_mode = validate_can_id_mode(settings["id_mode"])
        validate_can_search_criteria(
            canonical_mode,
            data=canonical_data,
            data_length=canonical_data_length,
            id_val=canonical_id,
            id_mode=canonical_id_mode,
        )

def _validate_save_export_args(args: argparse.Namespace) -> None:
    if args.command == "save-pwd" and not args.query:
        validate_save_quoted_string(args.path, label="Save path")
    elif args.command == "save-filename" and not args.query:
        validate_save_filename_base(args.name)
    elif args.command == "save-image":
        validate_save_quoted_string(args.filename, label="Save image filename")
    elif args.command == "save-waveform-length" and not args.query:
        validate_save_waveform_length(args.points)
    elif args.command == "save-waveform":
        validate_save_quoted_string(args.filename, label="Save waveform filename")

def _validate_measurement_reference_args(args: argparse.Namespace) -> None:
    command = args.command
    if command == "measure-show" and getattr(args, "off", False):
        raise ParameterValidationError(
            "measure-show OFF is not supported in v1; use --on or --query."
        )
    if command == "measure-source":
        query = bool(getattr(args, "query", False))
        source1 = getattr(args, "source_channel", None)
        source2 = getattr(args, "source2_channel", None)
        if query and (source1 is not None or source2 is not None):
            raise ParameterValidationError(
                "measure-source --query cannot be combined with source arguments."
            )
        if not query and source1 is None:
            raise ParameterValidationError(
                "measure-source configure requires --source-channel."
            )
    if command.startswith("reference-"):
        capabilities = _pre_open_capabilities(args)
        if capabilities is not None:
            validate_reference_slot(args.slot, capabilities)
            if command == "reference-save":
                validate_analog_channel(args.source_channel, capabilities)
        if command == "reference-label" and not args.query:
            validate_reference_label(args.text)

def _validate_trigger_edge_args(args: argparse.Namespace) -> None:
    configure_values = (
        getattr(args, "source_channel", None),
        getattr(args, "level", None),
        getattr(args, "slope", None),
    )
    if getattr(args, "edge_query", False):
        if any(value is not None for value in configure_values):
            raise ParameterValidationError(
                "trigger-edge --query cannot be combined with configure options."
            )
        return
    if not all(value is not None for value in configure_values):
        raise ParameterValidationError(
            "trigger-edge configure requires --source-channel, --level, and --slope."
        )

def _validate_trigger_edge_source_args(args: argparse.Namespace) -> None:
    source_channel = getattr(args, "source_channel", None)
    source = getattr(args, "source", None)
    if getattr(args, "trigger_edge_source_query", False):
        if source_channel is not None or source is not None:
            raise ParameterValidationError(
                "trigger-edge-source --query cannot be combined with configure options."
            )
        return
    if source_channel is not None and source is not None:
        raise ParameterValidationError(
            "trigger-edge-source --source-channel cannot be combined with --source."
        )
    if source_channel is None and source is None:
        raise ParameterValidationError(
            "trigger-edge-source requires --query, --source-channel, or --source."
        )

def _validate_trigger_edge_slope_args(args: argparse.Namespace) -> None:
    query = getattr(args, "trigger_edge_slope_query", False)
    slope = getattr(args, "slope", None)
    if query:
        if slope is not None:
            raise ParameterValidationError(
                "trigger-edge-slope --query cannot be combined with --slope."
            )
        return
    if slope is None:
        raise ParameterValidationError("trigger-edge-slope requires --query or --slope.")

def _validate_trigger_edge_level_args(args: argparse.Namespace) -> None:
    source_channel = getattr(args, "source_channel", None)
    query = getattr(args, "trigger_edge_level_query", False)
    level_volts = getattr(args, "level_volts", None)
    if source_channel is None:
        raise ParameterValidationError("trigger-edge-level requires --source-channel.")
    if query:
        if level_volts is not None:
            raise ParameterValidationError(
                "trigger-edge-level --query cannot be combined with --level-volts."
            )
        return
    if level_volts is None:
        raise ParameterValidationError(
            "trigger-edge-level requires --query or --level-volts."
        )
    validate_trigger_level(level_volts)

def _validate_external_trigger_range_args(args: argparse.Namespace) -> None:
    query = getattr(args, "external_trigger_range_query", False)
    range_volts = getattr(args, "range_volts", None)
    if query:
        if range_volts is not None:
            raise ParameterValidationError(
                "external-trigger-range --query cannot be combined with --range-volts."
            )
        return
    if range_volts is None:
        raise ParameterValidationError(
            "external-trigger-range requires --query or --range-volts."
        )
    validate_external_trigger_range(range_volts)

def _validate_trigger_edge_external_level_args(args: argparse.Namespace) -> None:
    query = getattr(args, "trigger_edge_external_level_query", False)
    level_volts = getattr(args, "level_volts", None)
    if query:
        if level_volts is not None:
            raise ParameterValidationError(
                "trigger-edge-external-level --query cannot be combined with --level-volts."
            )
        return
    if level_volts is None:
        raise ParameterValidationError(
            "trigger-edge-external-level requires --query or --level-volts."
        )
    validate_trigger_level(level_volts)

def _validate_external_trigger_probe_args(args: argparse.Namespace) -> None:
    query = getattr(args, "external_trigger_probe_query", False)
    attenuation = getattr(args, "attenuation", None)
    if query:
        if attenuation is not None:
            raise ParameterValidationError(
                "external-trigger-probe --query cannot be combined with --attenuation."
            )
        return
    if attenuation is None:
        raise ParameterValidationError(
            "external-trigger-probe requires --query or --attenuation."
        )
    validate_external_trigger_probe_attenuation(attenuation)

def _validate_external_trigger_units_args(args: argparse.Namespace) -> None:
    query = getattr(args, "external_trigger_units_query", False)
    units = getattr(args, "units", None)
    if query:
        if units is not None:
            raise ParameterValidationError(
                "external-trigger-units --query cannot be combined with --units."
            )
        return
    if units is None:
        raise ParameterValidationError("external-trigger-units requires --query or --units.")
    validate_external_trigger_units(units)

def _validate_external_trigger_settings_args(args: argparse.Namespace) -> None:
    if not getattr(args, "query", False):
        raise ParameterValidationError("external-trigger-settings requires --query.")

def _validate_trigger_sweep_args(args: argparse.Namespace) -> None:
    if getattr(args, "trigger_sweep_query", False):
        if getattr(args, "mode", None) is not None:
            raise ParameterValidationError(
                "trigger-sweep --query cannot be combined with configure options."
            )
        return
    if getattr(args, "mode", None) is None:
        raise ParameterValidationError("trigger-sweep configure requires --mode.")
    normalize_trigger_sweep(args.mode)

def _validate_trigger_reject_args(args: argparse.Namespace, command: str) -> None:
    query_attr = (
        "trigger_noise_reject_query"
        if command == "trigger-noise-reject"
        else "trigger_hf_reject_query"
    )
    if getattr(args, query_attr, False):
        if getattr(args, "enabled", None) is not None:
            raise ParameterValidationError(
                f"{command} --query cannot be combined with configure options."
            )
        return
    if getattr(args, "enabled", None) is None:
        raise ParameterValidationError(f"{command} configure requires --enabled.")
    if not isinstance(args.enabled, bool):
        raise ParameterValidationError(f"{command} --enabled must be true or false.")

def _validate_edge_coupling_args(args: argparse.Namespace) -> None:
    if getattr(args, "trigger_edge_coupling_query", False):
        if getattr(args, "coupling", None) is not None:
            raise ParameterValidationError(
                "trigger-edge-coupling --query cannot be combined with configure options."
            )
        return
    if getattr(args, "coupling", None) is None:
        raise ParameterValidationError(
            "trigger-edge-coupling configure requires --coupling."
        )

def _validate_edge_reject_args(args: argparse.Namespace) -> None:
    if getattr(args, "trigger_edge_reject_query", False):
        if getattr(args, "reject", None) is not None:
            raise ParameterValidationError(
                "trigger-edge-reject --query cannot be combined with configure options."
            )
        return
    if getattr(args, "reject", None) is None:
        raise ParameterValidationError(
            "trigger-edge-reject configure requires --reject."
        )

def _validate_trigger_glitch_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "channel", None),
        getattr(args, "polarity", None),
        getattr(args, "qualifier", None),
        getattr(args, "time_seconds", None),
        getattr(args, "min_time_seconds", None),
        getattr(args, "max_time_seconds", None),
        getattr(args, "level_volts", None),
    )
    if getattr(args, "glitch_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-pulse-width --query cannot be combined with configure options."
            )
        return

    if args.channel is None or args.polarity is None or args.qualifier is None:
        raise ParameterValidationError(
            "trigger-pulse-width configure requires --channel, --polarity, and --qualifier."
        )

    qualifier = normalize_glitch_qualifier(args.qualifier)
    if qualifier in {"GREaterthan", "LESSthan"}:
        if args.time_seconds is None:
            raise ParameterValidationError(
                "trigger-pulse-width greater-than and less-than require --time-seconds."
            )
        if args.min_time_seconds is not None or args.max_time_seconds is not None:
            raise ParameterValidationError(
                "trigger-pulse-width greater-than and less-than reject range timing options."
            )
        validate_trigger_time(args.time_seconds)
        return

    if args.time_seconds is not None:
        raise ParameterValidationError("trigger-pulse-width range rejects --time-seconds.")
    if args.min_time_seconds is None or args.max_time_seconds is None:
        raise ParameterValidationError(
            "trigger-pulse-width range requires --min-time-seconds and --max-time-seconds."
        )
    min_time = validate_trigger_time(args.min_time_seconds)
    max_time = validate_trigger_time(args.max_time_seconds)
    if min_time >= max_time:
        raise ParameterValidationError(
            "trigger-pulse-width --min-time-seconds must be less than --max-time-seconds."
        )

def _validate_trigger_runt_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "channel", None),
        getattr(args, "polarity", None),
        getattr(args, "qualifier", None),
        getattr(args, "time_seconds", None),
        getattr(args, "low_level_volts", None),
        getattr(args, "high_level_volts", None),
    )
    if getattr(args, "runt_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-runt --query cannot be combined with configure options."
            )
        return

    if (
        args.channel is None
        or args.polarity is None
        or args.qualifier is None
        or args.low_level_volts is None
        or args.high_level_volts is None
    ):
        raise ParameterValidationError(
            "trigger-runt configure requires --channel, --polarity, --qualifier, "
            "--low-level-volts, and --high-level-volts."
        )

    qualifier = normalize_runt_qualifier(args.qualifier)
    low_level = validate_trigger_level(args.low_level_volts)
    high_level = validate_trigger_level(args.high_level_volts)
    if low_level >= high_level:
        raise ParameterValidationError(
            "trigger-runt --low-level-volts must be less than --high-level-volts."
        )

    if qualifier in {"GREaterthan", "LESSthan"}:
        if args.time_seconds is None:
            raise ParameterValidationError(
                "trigger-runt greater-than and less-than require --time-seconds."
            )
        validate_trigger_time(args.time_seconds)
        return

    if args.time_seconds is not None:
        raise ParameterValidationError("trigger-runt qualifier none rejects --time-seconds.")

def _validate_trigger_transition_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "channel", None),
        getattr(args, "slope", None),
        getattr(args, "qualifier", None),
        getattr(args, "time_seconds", None),
        getattr(args, "low_level_volts", None),
        getattr(args, "high_level_volts", None),
    )
    if getattr(args, "transition_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-transition --query cannot be combined with configure options."
            )
        return

    if (
        args.channel is None
        or args.slope is None
        or args.qualifier is None
        or args.time_seconds is None
        or args.low_level_volts is None
        or args.high_level_volts is None
    ):
        raise ParameterValidationError(
            "trigger-transition configure requires --channel, --slope, --qualifier, "
            "--time-seconds, --low-level-volts, and --high-level-volts."
        )

    normalize_transition_slope(args.slope)
    normalize_transition_qualifier(args.qualifier)
    validate_trigger_time(args.time_seconds)
    low_level = validate_trigger_level(args.low_level_volts)
    high_level = validate_trigger_level(args.high_level_volts)
    if low_level >= high_level:
        raise ParameterValidationError(
            "trigger-transition --low-level-volts must be less than --high-level-volts."
        )

def _validate_trigger_delay_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "arm_channel", None),
        getattr(args, "arm_slope", None),
        getattr(args, "trigger_channel", None),
        getattr(args, "trigger_slope", None),
        getattr(args, "time_seconds", None),
        getattr(args, "count", None),
    )
    if getattr(args, "delay_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-delay --query cannot be combined with configure options."
            )
        return

    if (
        args.arm_channel is None
        or args.arm_slope is None
        or args.trigger_channel is None
        or args.trigger_slope is None
        or args.time_seconds is None
        or args.count is None
    ):
        raise ParameterValidationError(
            "trigger-delay configure requires --arm-channel, --arm-slope, "
            "--trigger-channel, --trigger-slope, --time-seconds, and --count."
        )

    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        validate_analog_channel(args.arm_channel, capabilities)
        validate_analog_channel(args.trigger_channel, capabilities)
    normalize_delay_slope(args.arm_slope)
    normalize_delay_slope(args.trigger_slope)
    validate_delay_trigger_time(args.time_seconds)
    validate_delay_trigger_count(args.count)

def _validate_trigger_setup_hold_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "clock_channel", None),
        getattr(args, "data_channel", None),
        getattr(args, "slope", None),
        getattr(args, "setup_time", None),
        getattr(args, "hold_time", None),
    )
    if getattr(args, "setup_hold_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-setup-hold --query cannot be combined with configure options."
            )
        return

    if (
        args.clock_channel is None
        or args.data_channel is None
        or args.slope is None
        or args.setup_time is None
        or args.hold_time is None
    ):
        raise ParameterValidationError(
            "trigger-setup-hold configure requires --clock-channel, --data-channel, "
            "--slope, --setup-time, and --hold-time."
        )

    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        validate_analog_channel(args.clock_channel, capabilities)
        validate_analog_channel(args.data_channel, capabilities)
    normalize_setup_hold_slope(args.slope)
    validate_setup_hold_trigger_time(args.setup_time, "setup")
    validate_setup_hold_trigger_time(args.hold_time, "hold")

def _validate_trigger_edge_burst_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "source_channel", None),
        getattr(args, "slope", None),
        getattr(args, "count", None),
        getattr(args, "idle_time", None),
        getattr(args, "level_volts", None),
    )
    if getattr(args, "edge_burst_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-edge-burst --query cannot be combined with configure options."
            )
        return

    if (
        args.source_channel is None
        or args.slope is None
        or args.count is None
        or args.idle_time is None
    ):
        raise ParameterValidationError(
            "trigger-edge-burst configure requires --source-channel, --slope, "
            "--count, and --idle-time."
        )

    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        validate_analog_channel(args.source_channel, capabilities)
    normalize_edge_burst_slope(args.slope)
    validate_edge_burst_count(args.count)
    validate_edge_burst_idle_time(args.idle_time)
    if args.level_volts is not None:
        validate_trigger_level(args.level_volts)

def _validate_trigger_tv_args(args: argparse.Namespace) -> None:
    set_values = (
        getattr(args, "source_channel", None),
        getattr(args, "standard", None),
        getattr(args, "mode", None),
        getattr(args, "polarity", None),
        getattr(args, "line", None),
    )
    if getattr(args, "tv_query", False):
        if any(value is not None for value in set_values):
            raise ParameterValidationError(
                "trigger-tv --query cannot be combined with configure options."
            )
        return

    if (
        args.source_channel is None
        or args.standard is None
        or args.mode is None
        or args.polarity is None
    ):
        raise ParameterValidationError(
            "trigger-tv configure requires --source-channel, --standard, --mode, and --polarity."
        )

    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        tv_trigger_configure_commands(
            source_channel=args.source_channel,
            standard=args.standard,
            mode=args.mode,
            polarity=args.polarity,
            capabilities=capabilities,
            line=args.line,
        )

def _validate_trigger_pattern_args(args: argparse.Namespace) -> None:
    if getattr(args, "pattern_query", False):
        if args.pattern is not None:
            raise ParameterValidationError(
                "trigger-pattern --query cannot be combined with --pattern."
            )
        return
    if args.pattern is None:
        raise ParameterValidationError("trigger-pattern configure requires --pattern.")
    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        validate_pattern_trigger_pattern(args.pattern, capabilities)

def _validate_trigger_or_args(args: argparse.Namespace) -> None:
    if getattr(args, "or_query", False):
        if args.pattern is not None:
            raise ParameterValidationError(
                "trigger-or --query cannot be combined with --pattern."
            )
        return
    if args.pattern is None:
        raise ParameterValidationError("trigger-or configure requires --pattern.")
    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        validate_or_trigger_pattern(args.pattern, capabilities)

def validate_pre_open_args(args: argparse.Namespace) -> None:
    _validate_pre_open_args(args)
