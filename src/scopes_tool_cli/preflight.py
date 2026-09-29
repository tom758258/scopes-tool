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
from scopes_tool_core.fft import (
    fft_configure_commands,
    fft_advanced_query_commands,
    fft_query_commands,
)
from scopes_tool_core.capabilities import capabilities_for_model_id
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
from scopes_tool_core.screenshot import (
    ScreenshotOptions,
    normalize_screenshot_options,
    validate_screenshot_capability,
)
from scopes_tool_core.trigger import (
    TriggerWaitConfig,
    validate_trigger_wait_config,
)

# This module stays the preflight facade. The private names below keep their
# existing preflight.* call sites working after the per-domain split.
from ._preflight_common import _pre_open_capabilities
from ._preflight_math import _validate_math_args
from ._preflight_serial import (
    _canonical_serial_search_settings,
    _extract_serial_search_settings,
    _serial_cli_values,
    _validate_search_args,
    _validate_serial_args,
    _validate_serial_lister_args,
    _validate_serial_protocol_args,
    _validate_serial_search_args,
)
from ._preflight_trigger import (
    _validate_edge_coupling_args,
    _validate_edge_reject_args,
    _validate_external_trigger_probe_args,
    _validate_external_trigger_range_args,
    _validate_external_trigger_settings_args,
    _validate_external_trigger_units_args,
    _validate_trigger_delay_args,
    _validate_trigger_edge_args,
    _validate_trigger_edge_burst_args,
    _validate_trigger_edge_external_level_args,
    _validate_trigger_edge_level_args,
    _validate_trigger_edge_slope_args,
    _validate_trigger_edge_source_args,
    _validate_trigger_glitch_args,
    _validate_trigger_mode_args,
    _validate_trigger_or_args,
    _validate_trigger_pattern_args,
    _validate_trigger_reject_args,
    _validate_trigger_runt_args,
    _validate_trigger_setup_hold_args,
    _validate_trigger_sweep_args,
    _validate_trigger_transition_args,
    _validate_trigger_tv_args,
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

def _uses_screenshot_hardcopy_controls(args: argparse.Namespace) -> bool:
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
    capabilities = _pre_open_capabilities(args)
    if capabilities is not None:
        validate_screenshot_capability(capabilities, options,
                                      query_hardcopy=getattr(args, "query_hardcopy", False))

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
    if getattr(args, "command", None) == "single-wait":
        validate_trigger_wait_config(
            TriggerWaitConfig(
                timeout_ms=args.trigger_timeout_ms,
                poll_interval_ms=args.trigger_poll_interval_ms,
                force_on_timeout=args.force_trigger_on_timeout,
            )
        )
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
        "serial-status",
        "serial-mode",
        "serial-enable",
        "serial-disable",
        "serial-uart-set",
        "serial-uart-show",
        "serial-trigger-uart-set",
        "serial-trigger-uart-show",
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
    if getattr(args, "command", None) == "trigger-mode":
        _validate_trigger_mode_args(args)
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
            "DEMO output is not supported by the selected model profile."
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
            "WGEN is not supported by the selected model profile."
        )
    if args.command == "wgen-query" or args.query:
        return
    if args.command == "wgen-function":
        validate_wgen_function(args.function)
    elif args.command == "wgen-frequency":
        if capabilities is not None:
            validate_wgen_frequency(
                args.hz, series=capabilities.series
            )
        else:
            # Normal one-shot live: model identity has not been detected
            # yet (no instrument session open). Only apply basic checks that
            # cannot false-reject a model-valid value. Exact series/function
            # dependent limits are deferred to execution-time validation.
            value = float(args.hz)
            if not math.isfinite(value) or value <= 0:
                raise ParameterValidationError(
                    "WGEN frequency must be a positive finite number."
                )
    elif args.command == "wgen-voltage":
        if capabilities is not None:
            validate_wgen_amplitude(
                args.amplitude, series=capabilities.series
            )
        else:
            # Normal one-shot live: avoid the legacy series=None 5 V / 2.5 V
            # ceiling so model-valid values (e.g. 4000X 6 Vpp) are not
            # rejected before the instrument session opens.
            value = float(args.amplitude)
            if not math.isfinite(value) or value <= 0:
                raise ParameterValidationError(
                    "WGEN amplitude must be a positive finite number."
                )
    elif args.command == "wgen-offset":
        if capabilities is not None:
            validate_wgen_offset(
                args.volts, series=capabilities.series
            )
        else:
            # Normal one-shot live: avoid the legacy series=None +/-2.5 V
            # ceiling; exact model/load/function limits remain deferred.
            value = float(args.volts)
            if not math.isfinite(value):
                raise ParameterValidationError(
                    "WGEN offset must be a finite number."
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

def validate_pre_open_args(args: argparse.Namespace) -> None:
    _validate_pre_open_args(args)
