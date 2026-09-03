from __future__ import annotations

import argparse

from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.workflow import StopRequested

from .commands import (
    acquisition,
    channel_display,
    measurement_analysis,
    serial,
    system,
    trigger_search,
    workflows,
)


def _dispatch_command(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    if args.command == "identify":
        return system._cmd_verify(args)
    if args.command == "check-error":
        return system._cmd_check_error(args)
    if args.command in {
        "system-clear-status",
        "system-opc",
        "system-status-byte",
        "system-standard-event",
        "system-operation-status",
        "system-options",
    }:
        return system._cmd_system_status(args)
    if args.command == "cleanup":
        return system._cmd_cleanup(args)
    if args.command in system._CONTROL_COMMANDS:
        return system._cmd_control(args)
    if args.command == "force-trigger":
        return system._cmd_force_trigger(args)
    if args.command == "single-wait":
        return system._cmd_single_wait(args, stop_requested=stop_requested)
    if args.command == "channel-summary":
        return channel_display._cmd_channel_summary(args)
    if args.command == "channel-display":
        return channel_display._cmd_channel_display(args)
    if args.command == "channel-label":
        return channel_display._cmd_channel_label(args)
    if args.command == "channel-scale":
        return channel_display._cmd_channel_scale(args)
    if args.command == "channel-offset":
        return channel_display._cmd_channel_offset(args)
    if args.command == "channel-coupling":
        return channel_display._cmd_channel_coupling(args)
    if args.command == "channel-probe":
        return channel_display._cmd_channel_probe(args)
    if args.command == "channel-bandwidth-limit":
        return channel_display._cmd_channel_bandwidth_limit(args)
    if args.command == "channel-impedance":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "channel-invert":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "channel-range":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "channel-units":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "channel-vernier":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "channel-probe-skew":
        return channel_display._cmd_channel_advanced_setting(args)
    if args.command == "display-label":
        return channel_display._cmd_display_label(args)
    if args.command in {
        "display-clear",
        "display-persistence",
        "display-intensity",
        "display-vectors",
    }:
        return channel_display._cmd_display_common(args)
    if args.command in {
        "measure-clear",
        "measure-install",
        "measure-show",
        "measure-source",
        "measure-window",
    }:
        return measurement_analysis._cmd_measurement_control(args)
    if args.command in {
        "dvm-enable",
        "dvm-source",
        "dvm-mode",
        "dvm-auto-range",
        "dvm-current",
        "dvm-query",
    }:
        return measurement_analysis._cmd_dvm(args)
    if args.command in {"demo-query", "demo-output", "demo-function", "demo-phase"}:
        return measurement_analysis._cmd_demo(args)
    if args.command in {
        "wgen-query",
        "wgen-output",
        "wgen-function",
        "wgen-frequency",
        "wgen-voltage",
        "wgen-offset",
        "wgen-load",
    }:
        return measurement_analysis._cmd_wgen(args)
    if args.command in {
        "serial-query",
        "serial-mode",
        "serial-display",
        "serial-uart",
        "serial-trigger-uart",
        "serial-trigger-i2c",
        "serial-trigger-spi",
        "serial-trigger-can",
        "serial-i2c",
        "serial-spi",
        "serial-can",
        "serial-lister-query",
        "serial-lister-display",
        "serial-lister-reference",
        "serial-lister-export",
    }:
        return serial._cmd_serial(args)
    if args.command in {
        "search-state",
        "search-mode",
        "search-count",
        "search-event",
        "serial-search-uart",
        "serial-search-i2c",
        "serial-search-spi",
        "serial-search-can",
    }:
        return trigger_search._cmd_search(args)
    if args.command in {
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
        return workflows._cmd_save_export(args)
    if args.command in {
        "reference-save",
        "reference-display",
        "reference-label",
        "reference-clear",
        "reference-query",
    }:
        return measurement_analysis._cmd_reference_waveform(args)
    if args.command == "annotation":
        return channel_display._cmd_annotation(args)
    if args.command == "timebase-scale":
        return channel_display._cmd_timebase_scale(args)
    if args.command == "timebase-position":
        return channel_display._cmd_timebase_position(args)
    if args.command == "timebase-reference":
        return channel_display._cmd_timebase_reference(args)
    if args.command == "trigger-edge":
        return trigger_search._cmd_trigger_edge(args)
    if args.command == "trigger-edge-source":
        return trigger_search._cmd_trigger_edge_source(args)
    if args.command == "trigger-edge-slope":
        return trigger_search._cmd_trigger_edge_slope(args)
    if args.command == "trigger-edge-level":
        return trigger_search._cmd_trigger_edge_level(args)
    if args.command == "external-trigger-range":
        return trigger_search._cmd_external_trigger_range(args)
    if args.command == "trigger-edge-external-level":
        return trigger_search._cmd_trigger_edge_external_level(args)
    if args.command in {
        "external-trigger-probe",
        "external-trigger-units",
        "external-trigger-settings",
    }:
        return trigger_search._cmd_external_trigger_input(args)
    if args.command in {
        "trigger-sweep",
        "trigger-noise-reject",
        "trigger-hf-reject",
        "trigger-edge-coupling",
        "trigger-edge-reject",
    }:
        return trigger_search._cmd_trigger_common(args)
    if args.command == "trigger-pulse-width":
        return trigger_search._cmd_trigger_glitch(args)
    if args.command == "trigger-runt":
        return trigger_search._cmd_trigger_runt(args)
    if args.command == "trigger-transition":
        return trigger_search._cmd_trigger_transition(args)
    if args.command == "trigger-delay":
        return trigger_search._cmd_trigger_delay(args)
    if args.command == "trigger-setup-hold":
        return trigger_search._cmd_trigger_setup_hold(args)
    if args.command == "trigger-edge-burst":
        return trigger_search._cmd_trigger_edge_burst(args)
    if args.command == "trigger-tv":
        return trigger_search._cmd_trigger_tv(args)
    if args.command == "trigger-pattern":
        return trigger_search._cmd_trigger_pattern(args)
    if args.command == "trigger-or":
        return trigger_search._cmd_trigger_or(args)
    if args.command == "cursor":
        return measurement_analysis._cmd_cursor(args)
    if args.command == "trigger-holdoff":
        return trigger_search._cmd_trigger_holdoff(args)
    if args.command == "measure":
        return workflows._cmd_measure(args)
    if args.command == "measure-results":
        return measurement_analysis._cmd_measure_results(args)
    if args.command == "measure-stats":
        return measurement_analysis._cmd_measure_stats(args)
    if args.command == "doctor":
        return workflows._cmd_doctor(args)
    if args.command == "measure-sweep":
        return workflows._cmd_measure_sweep(args)
    if args.command == "capture":
        return workflows._cmd_capture(args)
    if args.command == "capture-batch":
        return workflows._cmd_capture_batch(args, stop_requested=stop_requested)
    if args.command == "capture-until":
        return workflows._cmd_capture_until(args, stop_requested=stop_requested)
    if args.command == "capture-monitor":
        return workflows._cmd_capture_monitor(args, stop_requested=stop_requested)
    if args.command == "measure-log":
        return workflows._cmd_measure_log(args, stop_requested=stop_requested)
    if args.command == "measure-until":
        return workflows._cmd_measure_until(args, stop_requested=stop_requested)
    if args.command == "triggered-measure-loop":
        return workflows._cmd_triggered_measure_loop(args, stop_requested=stop_requested)
    if args.command == "triggered-capture-series":
        return workflows._cmd_triggered_capture_series(args, stop_requested=stop_requested)
    if args.command == "sequence":
        return workflows._cmd_sequence(args, stop_requested=stop_requested)
    if args.command == "screenshot":
        return workflows._cmd_screenshot(args)
    if args.command == "smoke":
        return workflows._cmd_smoke(args)
    if args.command == "sample-rate":
        return acquisition._cmd_sample_rate(args)

    if args.command == "segmented-memory":
        return acquisition._cmd_segmented_memory(args)

    if args.command == "segmented-capture":
        return workflows._cmd_segmented_capture(args)

    if args.command == "acquisition-points":
        return acquisition._cmd_acquisition_points(args)

    if args.command == "record-length":
        return acquisition._cmd_record_length(args)

    if args.command == "acquisition":
        return acquisition._cmd_acquisition(args)
    if args.command == "autoscale":
        return workflows._cmd_autoscale(args)
    if args.command == "setup-save":
        return workflows._cmd_setup_save(args)
    if args.command == "setup-recall":
        return workflows._cmd_setup_recall(args)
    if args.command == "fft":
        return measurement_analysis._cmd_fft(args)
    if args.command == "math-display":
        return measurement_analysis._cmd_math_display(args)
    if args.command == "math-vertical":
        return measurement_analysis._cmd_math_vertical(args)
    if args.command == "math-operator":
        return measurement_analysis._cmd_math_operator(args)
    if args.command == "math-composite-source":
        return measurement_analysis._cmd_math_composite_source(args)
    if args.command == "math-transform":
        return measurement_analysis._cmd_math_transform(args)
    if args.command == "math-filter":
        return measurement_analysis._cmd_math_filter(args)
    if args.command == "math-visualization":
        return measurement_analysis._cmd_math_visualization(args)
    if args.command == "math-clear":
        return measurement_analysis._cmd_math_clear(args)
    if args.command == "acquisition-check":
        return workflows._cmd_acquisition_check(args)
    raise OscilloscopeError("missing command")
