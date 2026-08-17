"""WebUI command catalog and Core-backed command execution."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import math
from pathlib import Path
from typing import Any, Mapping

from scopes_tool_core import (
    CaptureBatchRequest,
    CaptureRequest,
    MeasureLogRequest,
    MeasureRequest,
    OperationResult,
    ResolvedRunConfig,
    RunModeOptions,
    capabilities_for_model_id,
    open_scope_for_run,
    plan_acquisition_check,
    plan_capture,
    plan_measure,
    run_capture,
    run_capture_batch,
    run_measure_log,
    run_measure,
    run_measure_until,
    run_triggered_capture_series,
    run_triggered_measure_loop,
    plan_measure_until,
    plan_triggered_capture_series,
    plan_triggered_measure_loop,
    MeasureUntilRequest,
    TriggeredCaptureSeriesRequest,
    TriggeredMeasureLoopRequest,
)
from scopes_tool_core.acquisition import (
    normalize_acquisition_type,
    validate_acquisition_count,
)
from scopes_tool_core.channel import (
    normalize_channel_coupling,
    normalize_channel_impedance,
    normalize_channel_units,
    validate_analog_channel,
    validate_channel_impedance_supported,
    validate_channel_label,
    validate_channel_offset,
    validate_channel_range,
    validate_channel_scale,
    validate_probe_ratio,
    validate_probe_skew,
)
from scopes_tool_core.display import validate_display_intensity, validate_display_persistence
from scopes_tool_core.dvm import DVM_MODES, normalize_dvm_mode
from scopes_tool_core.fft import normalize_fft_units, normalize_fft_window
from scopes_tool_core.identity import PHYSICAL_MODEL_REGISTRY, physical_model_for_id
from scopes_tool_core.math import (
    MATH_COMPOSITE_OPERATIONS,
    MATH_OPERATIONS,
    MATH_SOURCES,
    normalize_math_composite_operation,
    normalize_math_operation,
    normalize_math_source,
    validate_finite_number,
    validate_positive,
)
from scopes_tool_core.measurements import (
    MEASUREMENT_WINDOW_CHOICES,
    SUPPORTED_MEASUREMENT_ITEMS,
    normalize_measurement_item,
    normalize_measurement_window,
)
from scopes_tool_core.output_files import write_serial_lister_csv, write_screenshot_png_file
from scopes_tool_core.planning import (
    AcquisitionCheckPlanRequest,
    CapturePlanRequest,
    MeasurePlanRequest,
    parse_measurement_item_list,
    parse_pair_specs,
    resolve_sweep_channels,
)
from scopes_tool_core.reference import validate_reference_label, validate_reference_slot
from scopes_tool_core.search import (
    CAN_SEARCH_ID_MODES,
    CAN_SEARCH_MODES,
    I2C_SEARCH_MODES,
    SEARCH_MODES,
    SEARCH_QUALIFIERS,
    SPI_SEARCH_MODES,
    UART_SEARCH_MODES,
    validate_can_search_criteria,
    validate_can_search_mode,
    validate_i2c_pattern_value,
    validate_i2c_search_mode,
    validate_search_event,
    validate_search_mode,
    validate_search_qualifier,
    validate_serial_search_bus,
    validate_spi_search_mode,
    validate_spi_search_pattern_width,
    validate_uart_data,
    validate_uart_search_mode,
)
from scopes_tool_core.serial import (
    CAN_SIGNAL_DEFINITIONS,
    CAN_TRIGGER_ID_MODES,
    CAN_TRIGGER_TYPES,
    I2C_ADDRESS_SIZES,
    I2C_TRIGGER_QUALIFIERS,
    I2C_TRIGGER_TYPES,
    SERIAL_BIT_ORDERS,
    SERIAL_LISTER_DISPLAYS,
    SERIAL_LISTER_REFERENCES,
    SERIAL_MODES,
    SPI_CLOCK_SLOPES,
    SPI_FRAMINGS,
    SPI_TRIGGER_TYPES,
    UART_PARITIES,
    UART_POLARITIES,
    UART_TRIGGER_QUALIFIERS,
    UART_TRIGGER_TYPES,
    normalize_can_signal_definition,
    normalize_i2c_address_size,
    normalize_serial_bit_order,
    normalize_serial_mode,
    normalize_serial_source,
    normalize_spi_clock_slope,
    normalize_spi_framing,
    normalize_uart_parity,
    normalize_uart_polarity,
    validate_can_baud_rate,
    validate_can_sample_point,
    validate_serial_bus,
    validate_serial_can_trigger_request,
    validate_serial_i2c_trigger_request,
    validate_serial_mode,
    validate_serial_spi_trigger_request,
    validate_serial_uart_trigger_request,
    validate_serial_lister_display,
    validate_serial_lister_reference,
    validate_spi_framing_clock_timeout,
    validate_uart_baud_rate,
)
from scopes_tool_core.segmented_capture import (
    SegmentedCaptureRequest,
    plan_segmented_capture,
    run_segmented_capture,
    validate_segmented_capture_request,
)
from scopes_tool_core.trigger import (
    normalize_delay_slope,
    normalize_edge_burst_slope,
    normalize_edge_slope,
    normalize_glitch_polarity,
    normalize_glitch_qualifier,
    normalize_runt_polarity,
    normalize_runt_qualifier,
    normalize_setup_hold_slope,
    normalize_transition_qualifier,
    normalize_transition_slope,
    normalize_trigger_edge_coupling,
    normalize_trigger_edge_reject,
    normalize_trigger_sweep,
    normalize_tv_mode,
    normalize_tv_polarity,
    normalize_tv_standard,
    validate_delay_trigger_count,
    validate_delay_trigger_time,
    validate_edge_burst_count,
    validate_edge_burst_idle_time,
    validate_edge_burst_source_channel,
    validate_external_trigger_probe_attenuation,
    validate_external_trigger_range,
    validate_external_trigger_units,
    validate_or_trigger_pattern,
    validate_pattern_trigger_pattern,
    validate_setup_hold_trigger_channel,
    validate_setup_hold_trigger_time,
    validate_trigger_level,
    validate_trigger_time,
    validate_tv_line,
    validate_tv_source_channel,
)
from scopes_tool_core.save_export import (
    SAVE_IMAGE_FORMATS,
    SAVE_IMAGE_PALETTES,
    SAVE_WAVEFORM_FORMATS,
    validate_save_filename_base,
    validate_save_quoted_string,
    validate_save_waveform_length,
)
from scopes_tool_core.visa_backend import list_visa_resources


DEFAULT_MODEL_ID = "keysight-dsox4024a"
COMMANDS = (
    {
        "id": "list-resources",
        "category": "Device",
        "label": "List resources",
        "modes": ("live", "simulate", "dry-run"),
        "fields": (),
    },
    {
        "id": "identify",
        "category": "Identity",
        "label": "Identify",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "run",
        "category": "Acquisition",
        "label": "Run",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "single",
        "category": "Acquisition",
        "label": "Single",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "stop-acquisition",
        "category": "Acquisition",
        "label": "Stop",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "acquisition",
        "category": "Acquisition",
        "label": "Acquisition",
        "modes": ("live", "simulate", "dry-run"),
        "fields": (
            {
                "name": "action",
                "type": "enum",
                "options": ("query", "set"),
                "mode_options": {
                    "live": ("query", "set"),
                    "simulate": ("query", "set"),
                    "dry-run": ("query",),
                },
                "default": "query",
            },
            {"name": "type", "type": "enum", "options": ("normal", "average", "high_resolution", "peak")},
            {"name": "count", "type": "integer", "minimum": 2, "maximum": 65536},
        ),
    },
    {
        "id": "channel-display",
        "category": "Channel",
        "label": "Channel display",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "channel-scale",
        "category": "Channel",
        "label": "Channel scale",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "volts_per_division", "type": "number", "minimum": 0},
        ),
    },
    {
        "id": "channel-summary",
        "category": "Channel",
        "label": "Channel summary",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "channel-label",
        "category": "Channel",
        "label": "Channel label",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "text", "type": "string"},
        ),
    },
    {
        "id": "channel-offset",
        "category": "Channel",
        "label": "Channel offset",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "volts", "type": "number"},
        ),
    },
    {
        "id": "channel-coupling",
        "category": "Channel",
        "label": "Channel coupling",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "coupling", "type": "enum", "options": ("ac", "dc")},
        ),
    },
    {
        "id": "channel-probe",
        "category": "Channel",
        "label": "Channel probe ratio",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "ratio", "type": "number", "minimum": 0},
        ),
    },
    {
        "id": "channel-bandwidth-limit",
        "category": "Channel",
        "label": "Channel bandwidth limit",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "channel-impedance",
        "category": "Channel",
        "label": "Channel impedance",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "impedance", "type": "enum", "options": ("one_meg", "fifty")},
        ),
    },
    {
        "id": "channel-invert",
        "category": "Channel",
        "label": "Channel invert",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "channel-range",
        "category": "Channel",
        "label": "Channel range",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "volts", "type": "number", "minimum": 0},
        ),
    },
    {
        "id": "channel-units",
        "category": "Channel",
        "label": "Channel units",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "units", "type": "enum", "options": ("volt", "amp")},
        ),
    },
    {
        "id": "channel-vernier",
        "category": "Channel",
        "label": "Channel vernier",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "channel-probe-skew",
        "category": "Channel",
        "label": "Channel probe skew",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "seconds", "type": "number"},
        ),
    },
    {
        "id": "display-label",
        "category": "Display",
        "label": "Display label",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "display-clear",
        "category": "Display",
        "label": "Clear display",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "display-persistence",
        "category": "Display",
        "label": "Display persistence",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "value", "type": "string"},
        ),
    },
    {
        "id": "display-intensity",
        "category": "Display",
        "label": "Display intensity",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "value", "type": "integer", "minimum": 0, "maximum": 100},
        ),
    },
    {
        "id": "display-vectors",
        "category": "Display",
        "label": "Display vectors",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
        ),
    },
    {
        "id": "measure",
        "category": "Measurement",
        "label": "Measure",
        "modes": ("live", "simulate", "dry-run"),
        "fields": (
            {"name": "item", "type": "enum", "options": SUPPORTED_MEASUREMENT_ITEMS, "default": "vpp"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "reference_channel", "type": "integer", "minimum": 1, "maximum": 4},
            {"name": "time_s", "type": "number"},
            {"name": "level", "type": "number"},
            {"name": "slope", "type": "enum", "options": ("positive", "negative")},
            {"name": "occurrence", "type": "integer", "minimum": 1},
        ),
    },
    {
        "id": "measure-results",
        "category": "Measurement",
        "label": "Measurement results",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "measure-clear",
        "category": "Measurement",
        "label": "Clear measurements",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "measure-show",
        "category": "Measurement",
        "label": "Measurement display",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
        ),
    },
    {
        "id": "measure-source",
        "category": "Measurement",
        "label": "Measurement source",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "source_channel", "type": "integer", "minimum": 1, "maximum": 4},
            {"name": "source2_channel", "type": "integer", "minimum": 1, "maximum": 4},
        ),
    },
    {
        "id": "measure-window",
        "category": "Measurement",
        "label": "Measurement window",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "window", "type": "enum", "options": MEASUREMENT_WINDOW_CHOICES},
        ),
    },
    {
        "id": "screenshot",
        "category": "Capture",
        "label": "Screenshot",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "background", "type": "enum", "options": ("black", "white"), "default": "black"},
        ),
    },
    {
        "id": "reference-save",
        "category": "Reference",
        "label": "Save reference waveform",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "slot", "type": "integer", "minimum": 1, "maximum": 2},
            {"name": "source_channel", "type": "integer", "minimum": 1, "maximum": 4},
        ),
    },
    {
        "id": "reference-display",
        "category": "Reference",
        "label": "Reference waveform display",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "slot", "type": "integer", "minimum": 1, "maximum": 2, "default": 1},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "reference-label",
        "category": "Reference",
        "label": "Reference waveform label",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "slot", "type": "integer", "minimum": 1, "maximum": 2, "default": 1},
            {"name": "label", "type": "string"},
        ),
    },
    {
        "id": "reference-clear",
        "category": "Reference",
        "label": "Clear reference waveform",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "slot", "type": "integer", "minimum": 1, "maximum": 2, "default": 1},
        ),
    },
    {
        "id": "reference-query",
        "category": "Reference",
        "label": "Reference waveform state",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "slot", "type": "integer", "minimum": 1, "maximum": 2, "default": 1},
        ),
    },
    {
        "id": "save-pwd",
        "category": "Save / Export",
        "label": "Save path",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "path", "type": "string"},
        ),
    },
    {
        "id": "save-filename",
        "category": "Save / Export",
        "label": "Save filename",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "name", "type": "string"},
        ),
    },
    {
        "id": "save-image-format",
        "category": "Save / Export",
        "label": "Image save format",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "format", "type": "enum", "options": SAVE_IMAGE_FORMATS},
        ),
    },
    {
        "id": "save-image-palette",
        "category": "Save / Export",
        "label": "Image save palette",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "palette", "type": "enum", "options": SAVE_IMAGE_PALETTES},
        ),
    },
    {
        "id": "save-image-ink-saver",
        "category": "Save / Export",
        "label": "Image ink saver",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "save-image-factors",
        "category": "Save / Export",
        "label": "Image measurement factors",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "save-image",
        "category": "Save / Export",
        "label": "Save image",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "filename", "type": "string"},
        ),
    },
    {
        "id": "save-waveform-format",
        "category": "Save / Export",
        "label": "Waveform save format",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "format", "type": "enum", "options": SAVE_WAVEFORM_FORMATS},
        ),
    },
    {
        "id": "save-waveform-length",
        "category": "Save / Export",
        "label": "Waveform save length",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "points", "type": "integer", "minimum": 100},
        ),
    },
    {
        "id": "save-waveform-length-max",
        "category": "Save / Export",
        "label": "Maximum waveform save length",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "save-waveform",
        "category": "Save / Export",
        "label": "Save waveform",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "filename", "type": "string"},
        ),
    },
    {
        "id": "capture",
        "category": "Capture",
        "label": "Waveform capture",
        "modes": ("live", "simulate", "dry-run"),
        "fields": (
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "points", "type": "enum", "options": (1000, 5000, 10000), "default": 1000},
            {"name": "format", "type": "enum", "options": ("byte", "word"), "default": "byte"},
        ),
    },
    {
        "id": "check-error",
        "category": "System",
        "label": "System error",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "system-status-byte",
        "category": "System",
        "label": "Status byte",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "system-operation-status",
        "category": "System",
        "label": "Operation status",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "system-clear-status",
        "category": "System",
        "label": "Clear status",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "system-opc",
        "category": "System",
        "label": "Operation complete",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "system-standard-event",
        "category": "System",
        "label": "Standard event status",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "system-options",
        "category": "System",
        "label": "System options",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "dvm-enable",
        "category": "DVM",
        "label": "DVM enable",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "dvm-source",
        "category": "DVM",
        "label": "DVM source",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4},
        ),
    },
    {
        "id": "dvm-mode",
        "category": "DVM",
        "label": "DVM mode",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "mode", "type": "enum", "options": DVM_MODES},
        ),
    },
    {
        "id": "dvm-auto-range",
        "category": "DVM",
        "label": "DVM auto range",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "dvm-current",
        "category": "DVM",
        "label": "DVM current reading",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "dvm-query",
        "category": "DVM",
        "label": "DVM state",
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "fft",
        "category": "FFT / MATH",
        "label": "FFT",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "function", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "source_channel", "type": "integer", "minimum": 1, "maximum": 4},
            {"name": "units", "type": "string"},
            {"name": "window", "type": "string"},
            {"name": "center_hz", "type": "number", "minimum": 0},
            {"name": "span_hz", "type": "number", "minimum": 0},
            {"name": "display", "type": "boolean"},
        ),
    },
    {
        "id": "math-display",
        "category": "FFT / MATH",
        "label": "Math display",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "function", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "enabled", "type": "boolean"},
        ),
    },
    {
        "id": "math-vertical",
        "category": "FFT / MATH",
        "label": "Math vertical",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "function", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "scale", "type": "number", "minimum": 0},
            {"name": "range_value", "type": "number", "minimum": 0},
            {"name": "offset", "type": "number"},
        ),
    },
    {
        "id": "math-operator",
        "category": "FFT / MATH",
        "label": "Math operator",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "function", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
            {"name": "operation", "type": "enum", "options": MATH_OPERATIONS},
            {"name": "source1", "type": "enum", "options": MATH_SOURCES},
            {"name": "source2", "type": "enum", "options": MATH_SOURCES},
        ),
    },
    {
        "id": "math-composite-source",
        "category": "FFT / MATH",
        "label": "Math composite source",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "operation", "type": "enum", "options": MATH_COMPOSITE_OPERATIONS},
            {"name": "source1", "type": "enum", "options": MATH_SOURCES},
            {"name": "source2", "type": "enum", "options": MATH_SOURCES},
        ),
    },
    {
        "id": "math-clear",
        "category": "FFT / MATH",
        "label": "Clear math",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "function", "type": "integer", "minimum": 1, "maximum": 4, "default": 1},
        ),
    },
)


def _p3c_field(name: str, field_type: str, *, visible_if: list[dict[str, Any]] | None = None, **kwargs: Any) -> dict[str, Any]:
    field = {"name": name, "type": field_type, **kwargs}
    if visible_if is not None:
        field["visible_if"] = visible_if
    return field


def _p3c_action() -> dict[str, Any]:
    return {
        "name": "action",
        "type": "enum",
        "options": ("query", "set"),
        "default": "query",
    }


def _p3c_set_visibility(*conditions: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"field": "action", "equals": "set"}, *conditions]


def _p3c_action_command(
    command_id: str,
    category: str,
    label: str,
    fields: tuple[dict[str, Any], ...],
    *,
    modes: tuple[str, ...] = ("live", "simulate"),
) -> dict[str, Any]:
    return {
        "id": command_id,
        "category": category,
        "label": label,
        "modes": modes,
        "fields": (_p3c_action(), *fields),
    }


_P3C_TRIGGER_SLOPES = ("positive", "negative", "either", "alternate")
_P3C_BINARY_SLOPES = ("positive", "negative")
_P3C_TV_LINE_MODES = ("line-field1", "line-field2", "line-alternate")

P3C_COMMANDS = (
    _p3c_action_command(
        "trigger-edge", "Trigger", "Edge trigger", (
            _p3c_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_p3c_set_visibility()),
            _p3c_field("level", "number", visible_if=_p3c_set_visibility()),
            _p3c_field("slope", "enum", options=_P3C_TRIGGER_SLOPES, visible_if=_p3c_set_visibility()),
        ),
    ),
    _p3c_action_command(
        "trigger-edge-source", "Trigger", "Edge trigger source", (
            _p3c_field("source", "enum", options=("analog-channel", "external", "line"), visible_if=_p3c_set_visibility()),
            _p3c_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_p3c_set_visibility({"field": "source", "equals": "analog-channel"})),
        ),
    ),
    _p3c_action_command("trigger-edge-slope", "Trigger", "Edge trigger slope", (_p3c_field("slope", "enum", options=_P3C_TRIGGER_SLOPES, visible_if=_p3c_set_visibility()),)),
    _p3c_action_command(
        "trigger-edge-level", "Trigger", "Edge trigger level", (
            _p3c_field("source_channel", "integer", minimum=1, maximum=4),
            _p3c_field("level", "number", visible_if=_p3c_set_visibility()),
        ),
    ),
    _p3c_action_command("external-trigger-range", "Trigger", "External trigger range", (_p3c_field("range_volts", "number", visible_if=_p3c_set_visibility()),)),
    _p3c_action_command("trigger-edge-external-level", "Trigger", "External trigger level", (_p3c_field("level", "number", visible_if=_p3c_set_visibility()),)),
    _p3c_action_command("external-trigger-probe", "Trigger", "External trigger probe", (_p3c_field("attenuation", "number", visible_if=_p3c_set_visibility()),)),
    _p3c_action_command("external-trigger-units", "Trigger", "External trigger units", (_p3c_field("units", "enum", options=("volts", "amps"), visible_if=_p3c_set_visibility()),)),
    {"id": "external-trigger-settings", "category": "Trigger", "label": "External trigger settings", "modes": ("live", "simulate"), "fields": ()},
    _p3c_action_command("trigger-edge-coupling", "Trigger", "Edge trigger coupling", (_p3c_field("coupling", "enum", options=("ac", "dc", "lf-reject"), visible_if=_p3c_set_visibility()),)),
    _p3c_action_command("trigger-edge-reject", "Trigger", "Edge trigger reject", (_p3c_field("reject", "enum", options=("off", "lf-reject", "hf-reject"), visible_if=_p3c_set_visibility()),)),
    _p3c_action_command(
        "trigger-pulse-width", "Trigger", "Glitch / pulse-width trigger", (
            _p3c_field("channel", "integer", minimum=1, maximum=4, visible_if=_p3c_set_visibility()),
            _p3c_field("polarity", "enum", options=("positive", "negative"), visible_if=_p3c_set_visibility()),
            _p3c_field("qualifier", "enum", options=("greater-than", "less-than", "range"), visible_if=_p3c_set_visibility()),
            _p3c_field("time_seconds", "number", visible_if=_p3c_set_visibility({"field": "qualifier", "in": ("greater-than", "less-than")})),
            _p3c_field("min_time_seconds", "number", visible_if=_p3c_set_visibility({"field": "qualifier", "equals": "range"})),
            _p3c_field("max_time_seconds", "number", visible_if=_p3c_set_visibility({"field": "qualifier", "equals": "range"})),
            _p3c_field("level", "number", visible_if=_p3c_set_visibility()),
        ),
    ),
    _p3c_action_command(
        "trigger-runt", "Trigger", "Runt trigger", (
            _p3c_field("channel", "integer", minimum=1, maximum=4, visible_if=_p3c_set_visibility()),
            _p3c_field("polarity", "enum", options=("positive", "negative", "either"), visible_if=_p3c_set_visibility()),
            _p3c_field("qualifier", "enum", options=("greater-than", "less-than", "none"), visible_if=_p3c_set_visibility()),
            _p3c_field("low_level", "number", visible_if=_p3c_set_visibility()),
            _p3c_field("high_level", "number", visible_if=_p3c_set_visibility()),
            _p3c_field("time_seconds", "number", visible_if=_p3c_set_visibility({"field": "qualifier", "in": ("greater-than", "less-than")})),
        ),
    ),
    _p3c_action_command(
        "trigger-transition", "Trigger", "Transition trigger", (
            _p3c_field("channel", "integer", minimum=1, maximum=4, visible_if=_p3c_set_visibility()),
            _p3c_field("slope", "enum", options=_P3C_BINARY_SLOPES, visible_if=_p3c_set_visibility()),
            _p3c_field("qualifier", "enum", options=("greater-than", "less-than"), visible_if=_p3c_set_visibility()),
            _p3c_field("low_level", "number", visible_if=_p3c_set_visibility()),
            _p3c_field("high_level", "number", visible_if=_p3c_set_visibility()),
            _p3c_field("time_seconds", "number", visible_if=_p3c_set_visibility()),
        ),
    ),
    _p3c_action_command(
        "trigger-delay", "Trigger", "Delay trigger", (
            _p3c_field("arm_channel", "integer", minimum=1, maximum=4, visible_if=_p3c_set_visibility()),
            _p3c_field("arm_slope", "enum", options=_P3C_BINARY_SLOPES, visible_if=_p3c_set_visibility()),
            _p3c_field("trigger_channel", "integer", minimum=1, maximum=4, visible_if=_p3c_set_visibility()),
            _p3c_field("trigger_slope", "enum", options=_P3C_BINARY_SLOPES, visible_if=_p3c_set_visibility()),
            _p3c_field("time_seconds", "number", visible_if=_p3c_set_visibility()),
            _p3c_field("count", "integer", minimum=1, visible_if=_p3c_set_visibility()),
        ),
    ),
    _p3c_action_command(
        "trigger-setup-hold", "Trigger", "Setup and hold trigger", (
            _p3c_field("clock_channel", "integer", minimum=1, maximum=4, visible_if=_p3c_set_visibility()),
            _p3c_field("data_channel", "integer", minimum=1, maximum=4, visible_if=_p3c_set_visibility()),
            _p3c_field("slope", "enum", options=_P3C_BINARY_SLOPES, visible_if=_p3c_set_visibility()),
            _p3c_field("setup_time_seconds", "number", visible_if=_p3c_set_visibility()),
            _p3c_field("hold_time_seconds", "number", visible_if=_p3c_set_visibility()),
        ),
    ),
    _p3c_action_command(
        "trigger-edge-burst", "Trigger", "Nth edge burst trigger", (
            _p3c_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_p3c_set_visibility()),
            _p3c_field("slope", "enum", options=_P3C_BINARY_SLOPES, visible_if=_p3c_set_visibility()),
            _p3c_field("count", "integer", minimum=1, visible_if=_p3c_set_visibility()),
            _p3c_field("idle_time", "number", visible_if=_p3c_set_visibility()),
            _p3c_field("level", "number", visible_if=_p3c_set_visibility()),
        ),
    ),
    _p3c_action_command(
        "trigger-tv", "Trigger", "TV trigger", (
            _p3c_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_p3c_set_visibility()),
            _p3c_field("standard", "enum", options=("ntsc", "pal", "palm", "secam"), visible_if=_p3c_set_visibility()),
            _p3c_field("mode", "enum", options=("field1", "field2", "all-fields", "all-lines", *_P3C_TV_LINE_MODES), visible_if=_p3c_set_visibility()),
            _p3c_field("polarity", "enum", options=("positive", "negative"), visible_if=_p3c_set_visibility()),
            _p3c_field("line", "integer", minimum=1, visible_if=_p3c_set_visibility({"field": "mode", "in": _P3C_TV_LINE_MODES})),
        ),
    ),
    _p3c_action_command("trigger-pattern", "Trigger", "Pattern trigger", (_p3c_field("pattern", "string", visible_if=_p3c_set_visibility()),)),
    _p3c_action_command("trigger-or", "Trigger", "OR trigger", (_p3c_field("pattern", "string", visible_if=_p3c_set_visibility()),)),
    _p3c_action_command("trigger-sweep", "Trigger", "Trigger sweep", (_p3c_field("mode", "enum", options=("auto", "normal"), visible_if=_p3c_set_visibility()),)),
    _p3c_action_command("trigger-noise-reject", "Trigger", "Noise reject", (_p3c_field("enabled", "boolean", visible_if=_p3c_set_visibility()),)),
    _p3c_action_command("trigger-hf-reject", "Trigger", "HF reject", (_p3c_field("enabled", "boolean", visible_if=_p3c_set_visibility()),)),
    _p3c_action_command("trigger-holdoff", "Trigger", "Trigger holdoff", (_p3c_field("seconds", "number", visible_if=_p3c_set_visibility()),)),

    _p3c_action_command("search-state", "Search", "Search state", (_p3c_field("enabled", "boolean", visible_if=_p3c_set_visibility()),)),
    _p3c_action_command("search-mode", "Search", "Search mode", (_p3c_field("mode", "enum", options=SEARCH_MODES, visible_if=_p3c_set_visibility()),)),
    {"id": "search-count", "category": "Search", "label": "Search count", "modes": ("live", "simulate"), "fields": ()},
    _p3c_action_command("search-event", "Search", "Search event", (_p3c_field("event", "integer", minimum=1, visible_if=_p3c_set_visibility()),)),
    _p3c_action_command(
        "serial-search-uart", "Search", "UART serial search", (
            _p3c_field("bus", "integer", minimum=1),
            _p3c_field("mode", "enum", options=UART_SEARCH_MODES, visible_if=_p3c_set_visibility()),
            _p3c_field("data", "integer", visible_if=_p3c_set_visibility({"field": "mode", "in": ("rx-data", "tx-data")})),
            _p3c_field("qualifier", "enum", options=SEARCH_QUALIFIERS, visible_if=_p3c_set_visibility({"field": "mode", "in": ("rx-data", "tx-data")})),
        ),
    ),
    _p3c_action_command(
        "serial-search-i2c", "Search", "I2C serial search", (
            _p3c_field("bus", "integer", minimum=1),
            _p3c_field("mode", "enum", options=I2C_SEARCH_MODES, visible_if=_p3c_set_visibility()),
            _p3c_field("address", "integer", visible_if=_p3c_set_visibility()),
            _p3c_field("data", "integer", visible_if=_p3c_set_visibility()),
            _p3c_field("data2", "integer", visible_if=_p3c_set_visibility({"field": "mode", "in": ("read7-data2", "write7-data2")})),
            _p3c_field("qualifier", "enum", options=SEARCH_QUALIFIERS, visible_if=_p3c_set_visibility({"field": "mode", "equals": "eeprom-read"})),
        ),
    ),
    _p3c_action_command(
        "serial-search-spi", "Search", "SPI serial search", (
            _p3c_field("bus", "integer", minimum=1),
            _p3c_field("mode", "enum", options=SPI_SEARCH_MODES, visible_if=_p3c_set_visibility()),
            _p3c_field("data", "string", visible_if=_p3c_set_visibility()),
            _p3c_field("width", "integer", minimum=1, visible_if=_p3c_set_visibility()),
        ),
    ),
    _p3c_action_command(
        "serial-search-can", "Search", "CAN serial search", (
            _p3c_field("bus", "integer", minimum=1),
            _p3c_field("mode", "enum", options=CAN_SEARCH_MODES, visible_if=_p3c_set_visibility()),
            _p3c_field("data", "string", visible_if=_p3c_set_visibility()),
            _p3c_field("data_length", "integer", minimum=0, visible_if=_p3c_set_visibility()),
            _p3c_field("id", "string", visible_if=_p3c_set_visibility({"field": "mode", "in": ("id-data", "id-either", "id-remote")})),
            _p3c_field("id_mode", "enum", options=CAN_SEARCH_ID_MODES, visible_if=_p3c_set_visibility({"field": "mode", "in": ("id-data", "id-either", "id-remote")})),
        ),
    ),

    _p3c_action_command("serial-query", "Serial", "Serial query", (_p3c_field("bus", "integer", minimum=1),)),
    _p3c_action_command("serial-mode", "Serial", "Serial mode", (_p3c_field("bus", "integer", minimum=1), _p3c_field("mode", "enum", options=SERIAL_MODES, visible_if=_p3c_set_visibility()))),
    _p3c_action_command("serial-display", "Serial", "Serial display", (_p3c_field("bus", "integer", minimum=1), _p3c_field("enabled", "boolean", visible_if=_p3c_set_visibility()))),
    _p3c_action_command(
        "serial-uart", "Serial", "UART configuration", (
            _p3c_field("bus", "integer", minimum=1),
            _p3c_field("rx_source", "string", visible_if=_p3c_set_visibility()), _p3c_field("tx_source", "string", visible_if=_p3c_set_visibility()),
            _p3c_field("baud_rate", "integer", visible_if=_p3c_set_visibility()), _p3c_field("data_bits", "integer", minimum=5, maximum=9, visible_if=_p3c_set_visibility()),
            _p3c_field("parity", "enum", options=UART_PARITIES, visible_if=_p3c_set_visibility()), _p3c_field("polarity", "enum", options=UART_POLARITIES, visible_if=_p3c_set_visibility()),
            _p3c_field("bit_order", "enum", options=SERIAL_BIT_ORDERS, visible_if=_p3c_set_visibility()),
        ),
    ),
    _p3c_action_command("serial-i2c", "Serial", "I2C configuration", (_p3c_field("bus", "integer", minimum=1), _p3c_field("clock_source", "string", visible_if=_p3c_set_visibility()), _p3c_field("data_source", "string", visible_if=_p3c_set_visibility()), _p3c_field("address_size", "enum", options=I2C_ADDRESS_SIZES, visible_if=_p3c_set_visibility()))),
    _p3c_action_command("serial-spi", "Serial", "SPI configuration", (_p3c_field("bus", "integer", minimum=1), _p3c_field("clock_source", "string", visible_if=_p3c_set_visibility()), _p3c_field("mosi_source", "string", visible_if=_p3c_set_visibility()), _p3c_field("miso_source", "string", visible_if=_p3c_set_visibility()), _p3c_field("frame_source", "string", visible_if=_p3c_set_visibility()), _p3c_field("clock_slope", "enum", options=SPI_CLOCK_SLOPES, visible_if=_p3c_set_visibility()), _p3c_field("bit_order", "enum", options=SERIAL_BIT_ORDERS, visible_if=_p3c_set_visibility()), _p3c_field("word_width", "integer", minimum=4, maximum=16, visible_if=_p3c_set_visibility()), _p3c_field("framing", "enum", options=SPI_FRAMINGS, visible_if=_p3c_set_visibility()), _p3c_field("clock_timeout", "number", visible_if=_p3c_set_visibility()))),
    _p3c_action_command("serial-can", "Serial", "CAN configuration", (_p3c_field("bus", "integer", minimum=1), _p3c_field("source", "string", visible_if=_p3c_set_visibility()), _p3c_field("baud_rate", "integer", visible_if=_p3c_set_visibility()), _p3c_field("signal_definition", "enum", options=CAN_SIGNAL_DEFINITIONS, visible_if=_p3c_set_visibility()), _p3c_field("sample_point", "number", visible_if=_p3c_set_visibility()))),
    _p3c_action_command("serial-trigger-uart", "Serial", "UART serial trigger", (_p3c_field("bus", "integer", minimum=1), _p3c_field("type", "enum", options=UART_TRIGGER_TYPES, visible_if=_p3c_set_visibility()), _p3c_field("data", "integer", visible_if=_p3c_set_visibility({"field": "type", "in": ("rx-data", "tx-data")})), _p3c_field("qualifier", "enum", options=UART_TRIGGER_QUALIFIERS, visible_if=_p3c_set_visibility({"field": "type", "in": ("rx-data", "tx-data")})))),
    _p3c_action_command("serial-trigger-i2c", "Serial", "I2C serial trigger", (_p3c_field("bus", "integer", minimum=1), _p3c_field("type", "enum", options=I2C_TRIGGER_TYPES, visible_if=_p3c_set_visibility()), _p3c_field("address", "integer", visible_if=_p3c_set_visibility()), _p3c_field("data", "integer", visible_if=_p3c_set_visibility()), _p3c_field("data2", "integer", visible_if=_p3c_set_visibility({"field": "type", "in": ("read7-data2", "write7-data2")})), _p3c_field("qualifier", "enum", options=I2C_TRIGGER_QUALIFIERS, visible_if=_p3c_set_visibility({"field": "type", "equals": "read-eeprom"})))),
    _p3c_action_command("serial-trigger-spi", "Serial", "SPI serial trigger", (_p3c_field("bus", "integer", minimum=1), _p3c_field("type", "enum", options=SPI_TRIGGER_TYPES, visible_if=_p3c_set_visibility()), _p3c_field("width", "integer", minimum=1, visible_if=_p3c_set_visibility()), _p3c_field("data", "string", visible_if=_p3c_set_visibility()))),
    _p3c_action_command("serial-trigger-can", "Serial", "CAN serial trigger", (_p3c_field("bus", "integer", minimum=1), _p3c_field("type", "enum", options=CAN_TRIGGER_TYPES, visible_if=_p3c_set_visibility()), _p3c_field("id", "string", visible_if=_p3c_set_visibility({"field": "type", "in": ("data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data")})), _p3c_field("id_mode", "enum", options=CAN_TRIGGER_ID_MODES, visible_if=_p3c_set_visibility({"field": "type", "in": ("data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data")})), _p3c_field("data", "string", visible_if=_p3c_set_visibility({"field": "type", "equals": "id-and-data"})), _p3c_field("data_length", "integer", minimum=0, visible_if=_p3c_set_visibility({"field": "type", "equals": "id-and-data"})))),
    {"id": "serial-lister-query", "category": "Serial", "label": "Serial Lister state", "modes": ("live", "simulate"), "fields": ()},
    _p3c_action_command("serial-lister-display", "Serial", "Serial Lister display", (_p3c_field("display", "enum", options=SERIAL_LISTER_DISPLAYS, visible_if=_p3c_set_visibility()),)),
    _p3c_action_command("serial-lister-reference", "Serial", "Serial Lister reference", (_p3c_field("reference", "enum", options=SERIAL_LISTER_REFERENCES, visible_if=_p3c_set_visibility()),)),
    {"id": "serial-lister-export", "category": "Serial", "label": "Export Serial Lister", "modes": ("live", "simulate"), "fields": (_p3c_field("output", "string"),)},

    {
        "id": "segmented-memory", "category": "Segmented Memory", "label": "Segmented memory", "modes": ("live", "simulate"),
        "fields": ({"name": "action", "type": "enum", "options": ("query", "enable", "disable"), "default": "query"}, _p3c_field("segments", "integer", minimum=1, visible_if=[{"field": "action", "equals": "enable"}])),
    },
    {
        "id": "segmented-capture", "category": "Segmented Memory", "label": "Segmented capture", "modes": ("live", "simulate", "dry-run"),
        "fields": (_p3c_field("channel", "integer", minimum=1, maximum=4, default=1), _p3c_field("segments", "integer", minimum=1), _p3c_field("points", "integer", minimum=100, default=1000), _p3c_field("format", "enum", options=("byte", "word"), default="byte"), _p3c_field("timeout_ms", "integer", minimum=1, default=30000), _p3c_field("poll_interval_ms", "integer", minimum=1, default=100)),
    },
    {
        "id": "capture-batch", "category": "Workflow", "label": "Capture batch", "modes": ("live", "simulate"),
        "fields": (_p3c_field("channels", "string"), _p3c_field("points", "integer", minimum=100, default=1000), _p3c_field("format", "enum", options=("byte", "word"), default="byte"), _p3c_field("count", "integer", minimum=1, default=1), _p3c_field("interval_seconds", "number", minimum=0, default=0)),
    },
    {
        "id": "measure-log", "category": "Workflow", "label": "Measurement log", "modes": ("live", "simulate"),
        "fields": (_p3c_field("channels", "string"), _p3c_field("items", "string", default="vpp,frequency"), _p3c_field("pairs", "string"), _p3c_field("pair_items", "string", default="phase,delay"), _p3c_field("interval_seconds", "number", minimum=0, default=1), _p3c_field("count", "integer", minimum=1), _p3c_field("duration_seconds", "number", minimum=0), _p3c_field("stop_on_error", "boolean")),
    },
    {
        "id": "measure-until", "category": "Workflow", "label": "Measure until", "modes": ("live", "simulate", "dry-run"),
        "fields": (_p3c_field("channel", "integer", minimum=1, maximum=4, default=1), _p3c_field("item", "enum", options=SUPPORTED_MEASUREMENT_ITEMS, default="vpp"), _p3c_field("operator", "enum", options=("gt", "gte", "lt", "lte")), _p3c_field("threshold", "number"), _p3c_field("timeout_seconds", "number", minimum=0), _p3c_field("interval_seconds", "number", minimum=0, default=1)),
    },
    {
        "id": "triggered-measure-loop", "category": "Workflow", "label": "Triggered measurement loop", "modes": ("live", "simulate", "dry-run"),
        "fields": (_p3c_field("channels", "string"), _p3c_field("items", "string", default="vpp,frequency"), _p3c_field("pairs", "string"), _p3c_field("pair_items", "string", default="phase,delay"), _p3c_field("count", "integer", minimum=1), _p3c_field("trigger_timeout_seconds", "number", minimum=0), _p3c_field("interval_seconds", "number", minimum=0, default=0)),
    },
    {
        "id": "triggered-capture-series", "category": "Workflow", "label": "Triggered capture series", "modes": ("live", "simulate", "dry-run"),
        "fields": (_p3c_field("channels", "string"), _p3c_field("count", "integer", minimum=1), _p3c_field("trigger_timeout_seconds", "number", minimum=0), _p3c_field("points", "integer", minimum=100, default=1000), _p3c_field("format", "enum", options=("byte", "word"), default="byte"), _p3c_field("interval_seconds", "number", minimum=0, default=0)),
    },
)

COMMANDS = COMMANDS + P3C_COMMANDS
_P3C_COMMAND_IDS = frozenset(entry["id"] for entry in P3C_COMMANDS)

_COMMAND_BY_ID = {entry["id"]: entry for entry in COMMANDS}
_COMMAND_FIELDS = {
    command_id: frozenset(field["name"] for field in entry["fields"])
    for command_id, entry in _COMMAND_BY_ID.items()
}


class WebUIRequestError(ValueError):
    """Raised when a WebUI command request is invalid before queueing."""


class ScopeSessionCloseError(RuntimeError):
    """Raised when a job-owned scope session cannot be closed."""


def command_catalog() -> list[dict[str, Any]]:
    return [_jsonable(entry) for entry in COMMANDS]


def model_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": model.model_id,
            "label": model.display_name,
            "series": model.series,
        }
        for model in PHYSICAL_MODEL_REGISTRY
    ]


def validate_job_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise WebUIRequestError("request body must be an object")
    command = payload.get("command")
    if not isinstance(command, str) or command not in _COMMAND_BY_ID:
        raise WebUIRequestError("command is not supported by the Scopes Tool WebUI")
    mode = payload.get("mode", "live")
    if mode not in {"live", "simulate", "dry-run"}:
        raise WebUIRequestError("mode must be live, simulate, or dry-run")
    if mode not in _COMMAND_BY_ID[command]["modes"]:
        raise WebUIRequestError(f"command {command!r} is not available in {mode} mode")
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise WebUIRequestError("parameters must be an object")
    unknown = sorted(set(parameters) - _COMMAND_FIELDS[command])
    if unknown:
        raise WebUIRequestError(f"unknown parameter for {command}: {unknown[0]}")

    resource = payload.get("resource")
    if resource is not None and (not isinstance(resource, str) or not resource.strip()):
        raise WebUIRequestError("resource must be a non-empty string when provided")
    model_id = payload.get("model_id", DEFAULT_MODEL_ID)
    if not isinstance(model_id, str) or not model_id.strip():
        raise WebUIRequestError("model_id must be a non-empty registered model ID")
    try:
        physical_model_for_id(model_id)
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc
    if mode == "live" and command != "list-resources" and resource is None:
        raise WebUIRequestError("live execution requires an explicit VISA resource")

    normalized = dict(parameters)
    _validate_parameters(command, normalized, mode, model_id)
    return {
        "command": command,
        "mode": mode,
        "resource": resource.strip() if isinstance(resource, str) else None,
        "model_id": model_id,
        "parameters": normalized,
    }


def execute_command(
    command: str,
    *,
    mode: str,
    resource: str | None,
    model_id: str,
    parameters: Mapping[str, Any],
    artifact_dir: Path,
) -> dict[str, Any]:
    """Execute one validated request through the public Core APIs."""

    if command == "list-resources":
        listing = list_visa_resources()
        return {
            "exit_code": 0,
            "result": {"resources": listing.resources, "backend": listing.backend},
            "artifacts": [],
        }

    config = _run_config(mode, resource, model_id)
    if mode == "dry-run":
        return _execute_dry_run(command, parameters, model_id, artifact_dir)

    scope = open_scope_for_run(config)
    try:
        return _execute_scope_command(
            scope,
            command,
            resource or config.resource or "",
            parameters,
            artifact_dir,
        )
    finally:
        try:
            scope.close()
        except Exception as exc:
            raise ScopeSessionCloseError(f"scope session close failed: {exc}") from exc


def _execute_dry_run(
    command: str,
    parameters: Mapping[str, Any],
    model_id: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    capabilities = capabilities_for_model_id(model_id)
    if command == "measure":
        request = _measure_request(parameters)
        plan = plan_measure(
            MeasurePlanRequest(
                item=request.item,
                channel=request.channel,
                source_channel=request.source_channel,
                reference_channel=request.reference_channel,
                time_s=request.time_s,
                level=request.level,
                slope=request.slope,
                occurrence=request.occurrence,
            ),
            capabilities,
        )
    elif command == "capture":
        csv_path = artifact_dir / "capture.csv"
        meta_path = artifact_dir / "capture_meta.json"
        plan = plan_capture(
            CapturePlanRequest(
                channels=(parameters["channel"],),
                points=parameters["points"],
                waveform_format=parameters["format"],
                csv_path=csv_path,
                meta_path=meta_path,
            ),
            capabilities,
        )
    elif command == "acquisition":
        plan = plan_acquisition_check(
            AcquisitionCheckPlanRequest(
                average_count=parameters.get("count", 16),
                check_only=True,
            )
        )
    elif command == "measure-until":
        request = _measure_until_request(parameters, artifact_dir)
        plan = plan_measure_until(request, capabilities)
    elif command == "triggered-measure-loop":
        request = _triggered_measure_loop_request(parameters, artifact_dir)
        plan = plan_triggered_measure_loop(request, capabilities)
    elif command == "triggered-capture-series":
        request = _triggered_capture_series_request(parameters, artifact_dir)
        plan = plan_triggered_capture_series(request, capabilities)
    elif command == "segmented-capture":
        request = _segmented_capture_request(parameters, artifact_dir)
        planned_scpi, files, result = plan_segmented_capture(request, capabilities)
        return {
            "exit_code": 0,
            "result": {"status": "planned", "model_id": model_id, "planned_scpi": planned_scpi, **_jsonable(result)},
            "artifacts": [{**file, "path": str(file["path"])} for file in files],
        }
    else:
        raise WebUIRequestError(f"dry-run is not supported for {command}")
    return {
        "exit_code": 0,
        "result": {
            "status": "planned",
            "model_id": model_id,
            "planned_scpi": list(plan.planned_scpi),
            "files": [
                {"kind": file["kind"], "name": Path(file["path"]).name}
                for file in plan.files
            ],
            **{
                key: _jsonable(value)
                for key, value in plan.result.items()
                if key != "files"
            },
        },
        "artifacts": [
            {**file, "path": str(file["path"])}
            for file in plan.files
        ],
    }


def _execute_scope_command(
    scope: Any,
    command: str,
    resource: str,
    parameters: Mapping[str, Any],
    artifact_dir: Path,
) -> dict[str, Any]:
    if scope.capabilities is None:
        scope.query_idn()
    if command in _P3C_COMMAND_IDS:
        return _execute_p3c_scope_command(scope, command, resource, parameters, artifact_dir)
    if command == "identify":
        idn = scope.idn or scope.query_idn()
        return {"exit_code": 0, "result": {"idn": _jsonable(idn)}, "artifacts": []}
    if command == "run":
        scope.run()
        return _simple_scope_result("run")
    if command == "single":
        scope.single()
        return _simple_scope_result("single")
    if command == "stop-acquisition":
        scope.stop()
        return _simple_scope_result("stop-acquisition")
    if command == "acquisition":
        return _execute_acquisition(scope, parameters)
    if command == "channel-display":
        return _execute_channel_display(scope, parameters)
    if command == "channel-scale":
        return _execute_channel_scale(scope, parameters)
    if command == "channel-summary":
        return _state_scope_result("channels", scope.query_channel_summary())
    if command == "channel-label":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_label,
            getter=scope.query_channel_label,
            value_name="text",
            result_name="text",
        )
    if command == "channel-offset":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_offset,
            getter=scope.query_channel_offset,
            value_name="volts",
            result_name="volts",
        )
    if command == "channel-coupling":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_coupling,
            getter=scope.query_channel_coupling,
            value_name="coupling",
            result_name="coupling",
        )
    if command == "channel-probe":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_probe_ratio,
            getter=scope.query_channel_probe_ratio,
            value_name="ratio",
            result_name="ratio",
        )
    if command == "channel-bandwidth-limit":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_bandwidth_limit,
            getter=scope.query_channel_bandwidth_limit,
            value_name="enabled",
            result_name="enabled",
        )
    if command == "channel-impedance":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_impedance,
            getter=scope.query_channel_impedance,
            value_name="impedance",
            result_name="impedance",
        )
    if command == "channel-invert":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_invert,
            getter=scope.query_channel_invert,
            value_name="enabled",
            result_name="enabled",
        )
    if command == "channel-range":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_range,
            getter=scope.query_channel_range,
            value_name="volts",
            result_name="volts",
        )
    if command == "channel-units":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_units,
            getter=scope.query_channel_units,
            value_name="units",
            result_name="units",
        )
    if command == "channel-vernier":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_vernier,
            getter=scope.query_channel_vernier,
            value_name="enabled",
            result_name="enabled",
        )
    if command == "channel-probe-skew":
        return _execute_channel_setting(
            scope,
            parameters,
            setter=scope.set_channel_probe_skew,
            getter=scope.query_channel_probe_skew,
            value_name="seconds",
            result_name="seconds",
        )
    if command == "display-label":
        return _execute_display_setting(parameters, scope.set_display_label, scope.query_display_label, "enabled")
    if command == "display-clear":
        scope.clear_display()
        return _simple_scope_result("display-clear")
    if command == "display-persistence":
        if parameters["action"] == "set":
            scope.set_display_persistence(parameters["value"])
        return _state_scope_result("persistence", scope.query_display_persistence())
    if command == "display-intensity":
        if parameters["action"] == "set":
            scope.set_display_intensity(parameters["value"])
        intensity, raw = scope.query_display_intensity()
        return _state_scope_result("intensity", {"value": intensity, "raw": raw})
    if command == "display-vectors":
        if parameters["action"] == "set":
            scope.set_display_vectors_on()
        enabled, raw = scope.query_display_vectors()
        return _state_scope_result("vectors", {"enabled": enabled, "raw": raw})
    if command == "measure":
        result = run_measure(scope, resource, _measure_request(parameters))
        return _operation_payload(result)
    if command == "measure-results":
        return _state_scope_result("measurements", scope.query_measurement_results())
    if command == "measure-clear":
        scope.clear_measurements()
        return _simple_scope_result("measure-clear")
    if command == "measure-show":
        if parameters["action"] == "set":
            scope.configure_measurement_show()
        return _state_scope_result("show", scope.query_measurement_show())
    if command == "measure-source":
        if parameters["action"] == "set":
            scope.configure_measurement_source(
                parameters["source_channel"], parameters.get("source2_channel")
            )
        return _state_scope_result("source", scope.query_measurement_source())
    if command == "measure-window":
        if parameters["action"] == "set":
            scope.configure_measurement_window(parameters["window"])
        return _state_scope_result("window", scope.query_measurement_window())
    if command == "capture":
        result = run_capture(
            scope,
            resource,
            CaptureRequest(
                channels=(parameters["channel"],),
                points=parameters["points"],
                waveform_format=parameters["format"],
                csv_path=artifact_dir / "capture.csv",
                meta_path=artifact_dir / "capture_meta.json",
            ),
        )
        return _operation_payload(result)
    if command == "screenshot":
        capture = scope.capture_screenshot_png(background=parameters["background"])
        path = write_screenshot_png_file(capture, artifact_dir / "screenshot.png")
        return {
            "exit_code": 0,
            "result": {
                "format": capture.format_name,
                "background": capture.background,
                "artifact": path.name,
            },
            "artifacts": [{"kind": "screenshot", "path": str(path)}],
        }
    if command == "reference-save":
        scope.save_reference_waveform(parameters["slot"], parameters["source_channel"])
        return _simple_scope_result("reference-save")
    if command == "reference-display":
        if parameters["action"] == "set":
            scope.configure_reference_display(parameters["slot"], parameters["enabled"])
        enabled, raw = scope.query_reference_display(parameters["slot"])
        return _state_scope_result(
            "display",
            {"slot": parameters["slot"], "enabled": enabled, "raw": raw},
        )
    if command == "reference-label":
        if parameters["action"] == "set":
            scope.configure_reference_label(parameters["slot"], parameters["label"])
        label, raw = scope.query_reference_label(parameters["slot"])
        return _state_scope_result(
            "label",
            {"slot": parameters["slot"], "label": label, "raw": raw},
        )
    if command == "reference-clear":
        scope.clear_reference_waveform(parameters["slot"])
        return _simple_scope_result("reference-clear")
    if command == "reference-query":
        return _state_scope_result(
            "reference", scope.query_reference_waveform(parameters["slot"])
        )
    if command == "save-pwd":
        return _execute_state_setting(
            parameters, scope.configure_save_pwd, scope.query_save_pwd, "path"
        )
    if command == "save-filename":
        return _execute_state_setting(
            parameters, scope.configure_save_filename, scope.query_save_filename, "name"
        )
    if command == "save-image-format":
        return _execute_state_setting(
            parameters,
            scope.configure_save_image_format,
            scope.query_save_image_format,
            "format",
        )
    if command == "save-image-palette":
        return _execute_state_setting(
            parameters,
            scope.configure_save_image_palette,
            scope.query_save_image_palette,
            "palette",
        )
    if command == "save-image-ink-saver":
        return _execute_state_setting(
            parameters,
            scope.configure_save_image_ink_saver,
            scope.query_save_image_ink_saver,
        )
    if command == "save-image-factors":
        return _execute_state_setting(
            parameters,
            scope.configure_save_image_factors,
            scope.query_save_image_factors,
        )
    if command == "save-image":
        return _state_scope_result("save", scope.save_image(parameters["filename"]).to_json())
    if command == "save-waveform-format":
        return _execute_state_setting(
            parameters,
            scope.configure_save_waveform_format,
            scope.query_save_waveform_format,
            "format",
        )
    if command == "save-waveform-length":
        return _execute_state_setting(
            parameters,
            scope.configure_save_waveform_length,
            scope.query_save_waveform_length,
            "points",
        )
    if command == "save-waveform-length-max":
        return _state_scope_result("state", scope.query_save_waveform_length_max())
    if command == "save-waveform":
        return _state_scope_result(
            "save", scope.save_waveform(parameters["filename"]).to_json()
        )
    if command == "check-error":
        entry = scope.query_system_error()
        return {
            "exit_code": 1 if entry.is_error else 0,
            "result": {"system_error": _jsonable(entry)},
            "artifacts": [],
        }
    if command == "system-status-byte":
        return {"exit_code": 0, "result": scope.query_status_byte().to_json(), "artifacts": []}
    if command == "system-operation-status":
        return {"exit_code": 0, "result": scope.query_operation_status().to_json(), "artifacts": []}
    if command == "system-clear-status":
        scope.clear_status()
        return _simple_scope_result("system-clear-status")
    if command == "system-opc":
        return _state_scope_result("operation_complete", scope.query_operation_complete())
    if command == "system-standard-event":
        return {"exit_code": 0, "result": scope.query_standard_event_status().to_json(), "artifacts": []}
    if command == "system-options":
        return {"exit_code": 0, "result": scope.query_system_options().to_json(), "artifacts": []}
    if command == "dvm-enable":
        return _execute_state_setting(parameters, scope.configure_dvm_enable, scope.query_dvm_enable)
    if command == "dvm-source":
        return _execute_state_setting(parameters, scope.configure_dvm_source, scope.query_dvm_source, "channel")
    if command == "dvm-mode":
        return _execute_state_setting(parameters, scope.configure_dvm_mode, scope.query_dvm_mode, "mode")
    if command == "dvm-auto-range":
        return _execute_state_setting(parameters, scope.configure_dvm_auto_range, scope.query_dvm_auto_range)
    if command == "dvm-current":
        return _state_scope_result("reading", scope.query_dvm_current())
    if command == "dvm-query":
        return _state_scope_result("dvm", scope.query_dvm())
    if command == "fft":
        return _execute_fft(scope, parameters)
    if command == "math-display":
        return _execute_math_display(scope, parameters)
    if command == "math-vertical":
        return _execute_math_vertical(scope, parameters)
    if command == "math-operator":
        return _execute_math_operator(scope, parameters)
    if command == "math-composite-source":
        return _execute_math_composite_source(scope, parameters)
    if command == "math-clear":
        scope.clear_math(parameters["function"])
        return _simple_scope_result("math-clear")
    raise WebUIRequestError(f"command is not supported by the Scopes Tool WebUI: {command}")


def _execute_p3c_scope_command(
    scope: Any,
    command: str,
    resource: str,
    parameters: Mapping[str, Any],
    artifact_dir: Path,
) -> dict[str, Any]:
    action = parameters.get("action", "query")
    if command == "trigger-edge":
        if action == "set":
            scope.configure_trigger_edge(parameters["source_channel"], parameters["level"], parameters["slope"])
        return _state_scope_result("trigger", scope.query_trigger_edge())
    if command == "trigger-edge-source":
        if action == "set":
            scope.configure_trigger_edge_source(source=parameters["source"], source_channel=parameters.get("source_channel"))
        return _state_scope_result("source", scope.query_trigger_edge_source())
    if command == "trigger-edge-slope":
        if action == "set":
            scope.configure_trigger_edge_slope(slope=parameters["slope"])
        return _state_scope_result("slope", scope.query_trigger_edge_slope())
    if command == "trigger-edge-level":
        if action == "set":
            scope.configure_trigger_edge_level(source_channel=parameters["source_channel"], level_volts=parameters["level"])
        return _state_scope_result("level", scope.query_trigger_edge_level(source_channel=parameters["source_channel"]))
    if command == "external-trigger-range":
        if action == "set":
            scope.configure_external_trigger_range(parameters["range_volts"])
        return _state_scope_result("range", scope.query_external_trigger_range())
    if command == "trigger-edge-external-level":
        if action == "set":
            scope.configure_trigger_edge_external_level(level_volts=parameters["level"])
        return _state_scope_result("level", scope.query_trigger_edge_external_level())
    if command == "external-trigger-probe":
        if action == "set":
            scope.configure_external_trigger_probe(parameters["attenuation"])
        return _state_scope_result("probe", scope.query_external_trigger_probe())
    if command == "external-trigger-units":
        if action == "set":
            scope.configure_external_trigger_units(parameters["units"])
        return _state_scope_result("units", scope.query_external_trigger_units())
    if command == "external-trigger-settings":
        return _state_scope_result("settings", scope.query_external_trigger_settings())
    if command == "trigger-edge-coupling":
        if action == "set":
            scope.configure_trigger_edge_coupling(parameters["coupling"])
        return _state_scope_result("coupling", scope.query_trigger_edge_coupling())
    if command == "trigger-edge-reject":
        if action == "set":
            scope.configure_trigger_edge_reject(parameters["reject"])
        return _state_scope_result("reject", scope.query_trigger_edge_reject())
    if command == "trigger-pulse-width":
        if action == "set":
            scope.configure_glitch_trigger(
                channel=parameters["channel"], polarity=parameters["polarity"], qualifier=parameters["qualifier"],
                time_seconds=parameters.get("time_seconds"), min_time_seconds=parameters.get("min_time_seconds"),
                max_time_seconds=parameters.get("max_time_seconds"), level_volts=parameters.get("level"),
            )
        return _state_scope_result("trigger", scope.query_glitch_trigger())
    if command == "trigger-runt":
        if action == "set":
            scope.configure_runt_trigger(
                channel=parameters["channel"], polarity=parameters["polarity"], qualifier=parameters["qualifier"],
                low_level_volts=parameters["low_level"], high_level_volts=parameters["high_level"],
                time_seconds=parameters.get("time_seconds"),
            )
        return _state_scope_result("trigger", scope.query_runt_trigger())
    if command == "trigger-transition":
        if action == "set":
            scope.configure_transition_trigger(
                channel=parameters["channel"], slope=parameters["slope"], qualifier=parameters["qualifier"],
                low_level_volts=parameters["low_level"], high_level_volts=parameters["high_level"],
                time_seconds=parameters["time_seconds"],
            )
        return _state_scope_result("trigger", scope.query_transition_trigger())
    if command == "trigger-delay":
        if action == "set":
            scope.configure_delay_trigger(
                arm_channel=parameters["arm_channel"], arm_slope=parameters["arm_slope"],
                trigger_channel=parameters["trigger_channel"], trigger_slope=parameters["trigger_slope"],
                time_seconds=parameters["time_seconds"], count=parameters["count"],
            )
        return _state_scope_result("trigger", scope.query_delay_trigger())
    if command == "trigger-setup-hold":
        if action == "set":
            scope.configure_setup_hold_trigger(
                clock_channel=parameters["clock_channel"], data_channel=parameters["data_channel"],
                slope=parameters["slope"], setup_time_seconds=parameters["setup_time_seconds"],
                hold_time_seconds=parameters["hold_time_seconds"],
            )
        return _state_scope_result("trigger", scope.query_setup_hold_trigger())
    if command == "trigger-edge-burst":
        if action == "set":
            scope.configure_edge_burst_trigger(
                source_channel=parameters["source_channel"], slope=parameters["slope"], count=parameters["count"],
                idle_time=parameters["idle_time"], level_volts=parameters.get("level"),
            )
        return _state_scope_result("trigger", scope.query_edge_burst_trigger())
    if command == "trigger-tv":
        if action == "set":
            scope.configure_tv_trigger(
                source_channel=parameters["source_channel"], standard=parameters["standard"], mode=parameters["mode"],
                polarity=parameters["polarity"], line=parameters.get("line"),
            )
        return _state_scope_result("trigger", scope.query_tv_trigger())
    if command == "trigger-pattern":
        if action == "set":
            scope.configure_pattern_trigger(parameters["pattern"])
        return _state_scope_result("trigger", scope.query_pattern_trigger())
    if command == "trigger-or":
        if action == "set":
            scope.configure_or_trigger(parameters["pattern"])
        return _state_scope_result("trigger", scope.query_or_trigger())
    if command == "trigger-sweep":
        if action == "set":
            scope.configure_trigger_sweep(parameters["mode"])
        return _state_scope_result("sweep", scope.query_trigger_sweep())
    if command == "trigger-noise-reject":
        if action == "set":
            scope.configure_trigger_noise_reject(parameters["enabled"])
        return _state_scope_result("state", scope.query_trigger_noise_reject())
    if command == "trigger-hf-reject":
        if action == "set":
            scope.configure_trigger_hf_reject(parameters["enabled"])
        return _state_scope_result("state", scope.query_trigger_hf_reject())
    if command == "trigger-holdoff":
        if action == "set":
            scope.set_trigger_holdoff(parameters["seconds"])
        return _state_scope_result("seconds", scope.query_trigger_holdoff())

    if command == "search-state":
        if action == "set":
            scope.configure_search_state(parameters["enabled"])
        return _state_scope_result("state", scope.query_search_state())
    if command == "search-mode":
        if action == "set":
            scope.configure_search_mode(parameters["mode"])
        return _state_scope_result("mode", scope.query_search_mode())
    if command == "search-count":
        return _state_scope_result("count", scope.query_search_count())
    if command == "search-event":
        if action == "set":
            scope.configure_search_event(parameters["event"])
        return _state_scope_result("event", scope.query_search_event())
    if command.startswith("serial-search-"):
        protocol = command.removeprefix("serial-search-")
        bus = parameters["bus"]
        if action == "set":
            if protocol == "uart":
                scope.configure_serial_search_uart(bus, parameters["mode"], parameters.get("data"), parameters.get("qualifier"))
            elif protocol == "i2c":
                scope.configure_serial_search_i2c(bus, parameters["mode"], parameters.get("address"), parameters.get("data"), parameters.get("data2"), parameters.get("qualifier"))
            elif protocol == "spi":
                scope.configure_serial_search_spi(bus, parameters["mode"], parameters.get("data"), parameters.get("width"))
            else:
                scope.configure_serial_search_can(bus, parameters["mode"], parameters.get("data"), parameters.get("data_length"), parameters.get("id"), parameters.get("id_mode"))
        getter = getattr(scope, f"query_serial_search_{protocol}")
        return _state_scope_result("search", getter(bus))

    if command == "serial-query":
        return _state_scope_result("serial", scope.query_serial(parameters["bus"]))
    if command == "serial-mode":
        if action == "set":
            scope.configure_serial_mode(parameters["bus"], parameters["mode"])
        return _state_scope_result("mode", scope.query_serial_mode(parameters["bus"]))
    if command == "serial-display":
        if action == "set":
            scope.configure_serial_display(parameters["bus"], parameters["enabled"])
        return _state_scope_result("display", scope.query_serial_display(parameters["bus"]))
    if command in {"serial-uart", "serial-i2c", "serial-spi", "serial-can"}:
        protocol = command.removeprefix("serial-")
        bus = parameters["bus"]
        if action == "set":
            configure = getattr(scope, f"configure_serial_{protocol}")
            configure(**{key: value for key, value in parameters.items() if key not in {"action", "bus"}} , bus=bus)
        return _state_scope_result(protocol, getattr(scope, f"query_serial_{protocol}")(bus))
    if command in {"serial-trigger-uart", "serial-trigger-i2c", "serial-trigger-spi", "serial-trigger-can"}:
        protocol = command.removeprefix("serial-trigger-")
        bus = parameters["bus"]
        if action == "set":
            configure = getattr(scope, f"configure_serial_{protocol}_trigger")
            configure(**{key: value for key, value in parameters.items() if key not in {"action", "bus"}}, bus=bus)
        return _state_scope_result("trigger", getattr(scope, f"query_serial_{protocol}_trigger")(bus))
    if command == "serial-lister-query":
        return _state_scope_result("lister", scope.query_serial_lister())
    if command == "serial-lister-display":
        if action == "set":
            scope.configure_serial_lister_display(parameters["display"])
        return _state_scope_result("display", scope.query_serial_lister_display())
    if command == "serial-lister-reference":
        if action == "set":
            scope.configure_serial_lister_reference(parameters["reference"])
        return _state_scope_result("reference", scope.query_serial_lister_reference())
    if command == "serial-lister-export":
        path = write_serial_lister_csv(scope.query_serial_lister_data(), artifact_dir / parameters["output"])
        return {"exit_code": 0, "result": {"output": path.name}, "artifacts": [{"kind": "serial-lister", "path": str(path)}]}

    if command == "segmented-memory":
        if action == "enable":
            scope.enable_segmented_memory(parameters["segments"])
        elif action == "disable":
            scope.disable_segmented_memory()
        return _state_scope_result("segmented", scope.query_segmented_memory())
    if command == "segmented-capture":
        return _operation_payload(run_segmented_capture(scope, resource, _segmented_capture_request(parameters, artifact_dir)))
    if command == "capture-batch":
        return _operation_payload(run_capture_batch(scope, resource, _capture_batch_request(parameters, artifact_dir)))
    if command == "measure-log":
        return _operation_payload(run_measure_log(scope, resource, _measure_log_request(parameters, artifact_dir)))
    if command == "measure-until":
        return _operation_payload(run_measure_until(scope, resource, _measure_until_request(parameters, artifact_dir)))
    if command == "triggered-measure-loop":
        return _operation_payload(run_triggered_measure_loop(scope, resource, _triggered_measure_loop_request(parameters, artifact_dir)))
    if command == "triggered-capture-series":
        return _operation_payload(run_triggered_capture_series(scope, resource, _triggered_capture_series_request(parameters, artifact_dir)))
    raise WebUIRequestError(f"command is not supported by the Scopes Tool WebUI: {command}")


def _execute_acquisition(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    action = parameters["action"]
    if action == "set":
        if "type" in parameters:
            scope.set_acquisition_type(parameters["type"])
        if "count" in parameters:
            scope.set_acquisition_count(parameters["count"])
    config = scope.query_acquisition_config()
    return {
        "exit_code": 0,
        "result": {"action": action, "acquisition": _jsonable(config)},
        "artifacts": [],
    }


def _execute_channel_display(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    channel = parameters["channel"]
    if parameters["action"] == "set":
        scope.set_channel_display(channel, parameters["enabled"])
    enabled = scope.query_channel_display(channel)
    return {
        "exit_code": 0,
        "result": {"channel": channel, "enabled": enabled},
        "artifacts": [],
    }


def _execute_channel_scale(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    channel = parameters["channel"]
    if parameters["action"] == "set":
        scope.set_channel_scale(channel, parameters["volts_per_division"])
    scale = scope.query_channel_scale(channel)
    return {
        "exit_code": 0,
        "result": {"channel": channel, "volts_per_division": scale},
        "artifacts": [],
    }


def _execute_channel_setting(
    scope: Any,
    parameters: Mapping[str, Any],
    *,
    setter: Any,
    getter: Any,
    value_name: str,
    result_name: str,
) -> dict[str, Any]:
    channel = parameters["channel"]
    if parameters["action"] == "set":
        setter(channel, parameters[value_name])
    return {
        "exit_code": 0,
        "result": {
            "channel": channel,
            result_name: _jsonable(getter(channel)),
        },
        "artifacts": [],
    }


def _execute_display_setting(
    parameters: Mapping[str, Any],
    setter: Any,
    getter: Any,
    value_name: str,
) -> dict[str, Any]:
    if parameters["action"] == "set":
        setter(parameters[value_name])
    return _state_scope_result("state", getter())


def _execute_state_setting(
    parameters: Mapping[str, Any],
    setter: Any,
    getter: Any,
    value_name: str = "enabled",
) -> dict[str, Any]:
    if parameters["action"] == "set":
        setter(parameters[value_name])
    return _state_scope_result("state", getter())


def _execute_fft(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_fft(
            function,
            parameters["source_channel"],
            units=parameters.get("units"),
            window=parameters.get("window"),
            center_hz=parameters.get("center_hz"),
            span_hz=parameters.get("span_hz"),
            display=parameters.get("display"),
        )
    return _state_scope_result("fft", scope.query_fft(function))


def _execute_math_display(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_display(function, parameters["enabled"])
    return _state_scope_result("math_display", scope.query_math_display(function))


def _execute_math_vertical(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_vertical(
            function,
            scale=parameters.get("scale"),
            range_value=parameters.get("range_value"),
            offset=parameters.get("offset"),
        )
    return _state_scope_result("math_vertical", scope.query_math_vertical(function))


def _execute_math_operator(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    function = parameters["function"]
    if parameters["action"] == "set":
        scope.configure_math_operator(
            function,
            parameters["operation"],
            parameters["source1"],
            parameters["source2"],
        )
    return _state_scope_result("math_operator", scope.query_math_operator(function))


def _execute_math_composite_source(scope: Any, parameters: Mapping[str, Any]) -> dict[str, Any]:
    if parameters["action"] == "set":
        scope.configure_math_composite_source(
            parameters["operation"],
            parameters["source1"],
            parameters["source2"],
        )
    return _state_scope_result("math_composite_source", scope.query_math_composite_source())


def _state_scope_result(name: str, value: Any) -> dict[str, Any]:
    return {"exit_code": 0, "result": {name: _jsonable(value)}, "artifacts": []}


def _simple_scope_result(action: str) -> dict[str, Any]:
    return {"exit_code": 0, "result": {"action": action}, "artifacts": []}


def _operation_payload(result: OperationResult) -> dict[str, Any]:
    result_payload = _jsonable(result.result)
    if isinstance(result_payload, dict) and isinstance(result_payload.get("files"), list):
        result_payload["files"] = [
            {"kind": item.get("kind"), "name": Path(item["path"]).name}
            if isinstance(item, dict) and isinstance(item.get("path"), str)
            else item
            for item in result_payload["files"]
        ]
    return {
        "exit_code": result.exit_code,
        "result": result_payload,
        "system_error": _jsonable(result.system_error),
        "diagnostics": {"human_lines": list(result.human_lines)},
        "idn": _jsonable(result.idn),
        "backend": result.backend,
        "timeout_ms": result.timeout_ms,
        "artifacts": [dict(item) for item in result.files],
    }


def _run_config(mode: str, resource: str | None, model_id: str) -> ResolvedRunConfig:
    options = RunModeOptions(
        simulate=mode == "simulate",
        dry_run=mode == "dry-run",
        planning_physical_model_id=model_id if mode != "live" else None,
    )
    resolved_resource = resource
    if mode == "simulate":
        resolved_resource = resource or f"SIM::{model_id}::INSTR"
    elif mode == "dry-run":
        resolved_resource = resource or f"DRY::{model_id}::INSTR"
    return ResolvedRunConfig(
        mode="dry_run" if mode == "dry-run" else mode,
        planning_physical_model_id=model_id if mode != "live" else None,
        expected_physical_model_id=None,
        capabilities=(capabilities_for_model_id(model_id) if mode != "live" else None),
        resource=resolved_resource,
        options=options,
    )


def _measure_request(parameters: Mapping[str, Any]) -> MeasureRequest:
    return MeasureRequest(
        item=parameters["item"],
        channel=parameters.get("channel"),
        reference_channel=parameters.get("reference_channel"),
        time_s=parameters.get("time_s"),
        level=parameters.get("level"),
        slope=parameters.get("slope"),
        occurrence=parameters.get("occurrence"),
    )


def _csv_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    raise WebUIRequestError("workflow list fields must be comma-separated strings")


def _workflow_channels(value: Any, capabilities: Any, *, required: bool) -> list[int] | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise WebUIRequestError("channels are required")
        return None
    try:
        raw = [int(item) if item.isdigit() else item for item in _csv_values(value)]
        return list(resolve_sweep_channels(raw, capabilities))
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc


def _workflow_pairs(value: Any, capabilities: Any) -> list[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return []
    values = _csv_values(value)
    try:
        parse_pair_specs(values, capabilities)
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc
    return values


def _capture_batch_request(parameters: Mapping[str, Any], artifact_dir: Path) -> CaptureBatchRequest:
    return CaptureBatchRequest(
        channels=parameters["channels"], points=parameters["points"], waveform_format=parameters["format"],
        requested_count=parameters["count"], interval_seconds=parameters["interval_seconds"], output_dir=artifact_dir,
    )


def _measure_log_request(parameters: Mapping[str, Any], artifact_dir: Path) -> MeasureLogRequest:
    return MeasureLogRequest(
        channels=parameters.get("channels"), items=parameters["items"], pairs=parameters.get("pairs", []),
        pair_items=parameters["pair_items"], interval_seconds=parameters["interval_seconds"],
        requested_count=parameters.get("count"), requested_duration_seconds=parameters.get("duration_seconds"),
        output_dir=artifact_dir, stop_on_error=parameters.get("stop_on_error", False),
    )


def _measure_until_request(parameters: Mapping[str, Any], artifact_dir: Path) -> MeasureUntilRequest:
    return MeasureUntilRequest(
        channel=parameters["channel"], item=parameters["item"], operator=parameters["operator"],
        threshold=parameters["threshold"], timeout_seconds=parameters["timeout_seconds"],
        interval_seconds=parameters["interval_seconds"], output_dir=artifact_dir,
    )


def _triggered_measure_loop_request(parameters: Mapping[str, Any], artifact_dir: Path) -> TriggeredMeasureLoopRequest:
    return TriggeredMeasureLoopRequest(
        count=parameters["count"], trigger_timeout_seconds=parameters["trigger_timeout_seconds"],
        channels=parameters.get("channels"), items=parameters["items"], pairs=parameters.get("pairs", []),
        pair_items=parameters["pair_items"], interval_seconds=parameters["interval_seconds"], output_dir=artifact_dir,
    )


def _triggered_capture_series_request(parameters: Mapping[str, Any], artifact_dir: Path) -> TriggeredCaptureSeriesRequest:
    return TriggeredCaptureSeriesRequest(
        channels=parameters["channels"], count=parameters["count"],
        trigger_timeout_seconds=parameters["trigger_timeout_seconds"], points=parameters["points"],
        waveform_format=parameters["format"], interval_seconds=parameters["interval_seconds"], output_dir=artifact_dir,
    )


def _segmented_capture_request(parameters: Mapping[str, Any], artifact_dir: Path) -> SegmentedCaptureRequest:
    return SegmentedCaptureRequest(
        channel=parameters["channel"], segments=parameters["segments"], points=parameters["points"],
        waveform_format=parameters["format"], timeout_ms=parameters["timeout_ms"],
        poll_interval_ms=parameters["poll_interval_ms"], output_dir=artifact_dir,
    )


def _validate_action_fields(parameters: dict[str, Any], command: str, names: tuple[str, ...]) -> str:
    action = _action(parameters, command)
    if action == "query":
        _reject_query_parameters(parameters, names, command)
    return action


def _validate_p3c_parameters(command: str, parameters: dict[str, Any], mode: str, model_id: str) -> None:
    capabilities = capabilities_for_model_id(model_id)
    if command == "segmented-memory":
        action = parameters.setdefault("action", "query")
        if action not in {"query", "enable", "disable"}:
            raise WebUIRequestError("segmented-memory action must be query, enable, or disable")
        if action == "enable":
            parameters["segments"] = _integer(parameters.get("segments"), "segments")
        elif action == "query":
            _reject_query_parameters(parameters, ("segments",), command)
        else:
            _reject_query_parameters(parameters, ("segments",), command)
        return
    if command == "segmented-capture":
        parameters["channel"] = validate_analog_channel(_integer(parameters.get("channel", 1), "channel"), capabilities)
        parameters["segments"] = _integer(parameters.get("segments"), "segments")
        parameters["points"] = _integer(parameters.get("points", 1000), "points")
        parameters["timeout_ms"] = _integer(parameters.get("timeout_ms", 30000), "timeout_ms")
        parameters["poll_interval_ms"] = _integer(parameters.get("poll_interval_ms", 100), "poll_interval_ms")
        parameters["format"] = str(parameters.get("format", "byte")).lower()
        if parameters["format"] not in {"byte", "word"}:
            raise WebUIRequestError("format must be byte or word")
        if mode == "dry-run" and not capabilities.supports_segmented_memory:
            raise WebUIRequestError("segmented capture is not supported by this model")
        try:
            validate_segmented_capture_request(_segmented_capture_request(parameters, Path(".")), capabilities)
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        return
    if command in {"capture-batch", "measure-log", "measure-until", "triggered-measure-loop", "triggered-capture-series"}:
        if command == "capture-batch":
            parameters["channels"] = _workflow_channels(parameters.get("channels"), capabilities, required=True)
            parameters["points"] = _integer(parameters.get("points", 1000), "points")
            parameters["count"] = _integer(parameters.get("count", 1), "count")
            parameters["interval_seconds"] = _finite_number(parameters.get("interval_seconds", 0), "interval_seconds")
            if parameters["interval_seconds"] < 0:
                raise WebUIRequestError("interval_seconds must be non-negative")
            parameters["format"] = str(parameters.get("format", "byte")).lower()
            if parameters["format"] not in {"byte", "word"}:
                raise WebUIRequestError("format must be byte or word")
        elif command == "measure-log":
            parameters["channels"] = _workflow_channels(parameters.get("channels"), capabilities, required=False)
            parameters["items"] = str(parameters.get("items", "vpp,frequency"))
            parameters["pairs"] = _workflow_pairs(parameters.get("pairs"), capabilities)
            parameters["pair_items"] = str(parameters.get("pair_items", "phase,delay"))
            try:
                parse_measurement_item_list(parameters["items"], allow_pair=False)
                parse_measurement_item_list(parameters["pair_items"], allow_pair=True)
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
            if "count" not in parameters and "duration_seconds" not in parameters:
                raise WebUIRequestError("measure-log requires count or duration_seconds")
            if "count" in parameters:
                parameters["count"] = _integer(parameters["count"], "count")
            if "duration_seconds" in parameters:
                parameters["duration_seconds"] = _finite_number(parameters["duration_seconds"], "duration_seconds")
            parameters["interval_seconds"] = _finite_number(parameters.get("interval_seconds", 1), "interval_seconds")
            parameters["stop_on_error"] = bool(parameters.get("stop_on_error", False))
        elif command == "measure-until":
            parameters["channel"] = validate_analog_channel(_integer(parameters.get("channel", 1), "channel"), capabilities)
            parameters["item"] = normalize_measurement_item(parameters.get("item", "vpp"))
            if parameters.get("operator") not in {"gt", "gte", "lt", "lte"}:
                raise WebUIRequestError("operator must be gt, gte, lt, or lte")
            parameters["threshold"] = _finite_number(parameters.get("threshold"), "threshold")
            parameters["timeout_seconds"] = _finite_number(parameters.get("timeout_seconds"), "timeout_seconds")
            parameters["interval_seconds"] = _finite_number(parameters.get("interval_seconds", 1), "interval_seconds")
        elif command == "triggered-measure-loop":
            parameters["channels"] = _workflow_channels(parameters.get("channels"), capabilities, required=False)
            parameters["items"] = str(parameters.get("items", "vpp,frequency"))
            parameters["pairs"] = _workflow_pairs(parameters.get("pairs"), capabilities)
            parameters["pair_items"] = str(parameters.get("pair_items", "phase,delay"))
            parameters["count"] = _integer(parameters.get("count"), "count")
            parameters["trigger_timeout_seconds"] = _finite_number(parameters.get("trigger_timeout_seconds"), "trigger_timeout_seconds")
            parameters["interval_seconds"] = _finite_number(parameters.get("interval_seconds", 0), "interval_seconds")
            try:
                parse_measurement_item_list(parameters["items"], allow_pair=False)
                parse_measurement_item_list(parameters["pair_items"], allow_pair=True)
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            parameters["channels"] = _workflow_channels(parameters.get("channels"), capabilities, required=True)
            parameters["count"] = _integer(parameters.get("count"), "count")
            parameters["trigger_timeout_seconds"] = _finite_number(parameters.get("trigger_timeout_seconds"), "trigger_timeout_seconds")
            parameters["points"] = _integer(parameters.get("points", 1000), "points")
            parameters["interval_seconds"] = _finite_number(parameters.get("interval_seconds", 0), "interval_seconds")
            parameters["format"] = str(parameters.get("format", "byte")).lower()
            if parameters["format"] not in {"byte", "word"}:
                raise WebUIRequestError("format must be byte or word")
        if mode == "dry-run" and command in {"capture-batch", "measure-log"}:
            raise WebUIRequestError(f"dry-run is not supported for {command}")
        return
    if command.startswith("serial-search-"):
        protocol = command.removeprefix("serial-search-")
        action = _validate_action_fields(parameters, command, tuple(key for key in parameters if key not in {"action", "bus", "mode"}))
        parameters["bus"] = validate_serial_search_bus(_integer(parameters.get("bus", 1), "bus"), capabilities)
        if action == "set":
            if protocol == "uart":
                parameters["mode"] = validate_uart_search_mode(parameters["mode"])
                if "data" in parameters: parameters["data"] = validate_uart_data(parameters["data"])
                if "qualifier" in parameters: parameters["qualifier"] = validate_search_qualifier(parameters["qualifier"])
            elif protocol == "i2c":
                parameters["mode"] = validate_i2c_search_mode(parameters["mode"])
                for name in ("address", "data", "data2"):
                    if name in parameters: parameters[name] = validate_i2c_pattern_value(_integer(parameters[name], name), name)
                if "qualifier" in parameters: parameters["qualifier"] = validate_search_qualifier(parameters["qualifier"])
            elif protocol == "spi":
                parameters["mode"] = validate_spi_search_mode(parameters["mode"])
                if "width" in parameters: parameters["width"] = _integer(parameters["width"], "width")
                validate_spi_search_pattern_width(parameters.get("data"), parameters.get("width"))
            else:
                parameters["mode"] = validate_can_search_mode(parameters["mode"])
                validate_can_search_criteria(parameters["mode"], data=parameters.get("data"), data_length=parameters.get("data_length"), id_val=parameters.get("id"), id_mode=parameters.get("id_mode"))
        return
    if command in {"search-state", "search-mode", "search-event"}:
        names = {"search-state": ("enabled",), "search-mode": ("mode",), "search-event": ("event",)}[command]
        action = _validate_action_fields(parameters, command, names)
        if action == "set":
            if command == "search-state": _require_boolean(parameters["enabled"], "enabled")
            elif command == "search-mode": parameters["mode"] = validate_search_mode(parameters["mode"], capabilities)
            else: parameters["event"] = validate_search_event(_integer(parameters["event"], "event"))
        return
    if command == "search-count":
        return
    if command.startswith("trigger-") or command.startswith("external-trigger-"):
        _validate_p3c_trigger(command, parameters, capabilities)
        return
    if command.startswith("serial-"):
        _validate_p3c_serial(command, parameters, capabilities)
        return


def _validate_p3c_trigger(command: str, parameters: dict[str, Any], capabilities: Any) -> None:
    if command == "external-trigger-settings":
        return
    action = _action(parameters, command)
    names_by_command = {
        "trigger-edge": ("source_channel", "level", "slope"),
        "trigger-edge-source": ("source", "source_channel"),
        "trigger-edge-slope": ("slope",),
        "trigger-edge-level": ("level",),
        "external-trigger-range": ("range_volts",),
        "trigger-edge-external-level": ("level",),
        "external-trigger-probe": ("attenuation",),
        "external-trigger-units": ("units",),
        "trigger-edge-coupling": ("coupling",),
        "trigger-edge-reject": ("reject",),
        "trigger-pulse-width": ("channel", "polarity", "qualifier", "time_seconds", "min_time_seconds", "max_time_seconds", "level"),
        "trigger-runt": ("channel", "polarity", "qualifier", "low_level", "high_level", "time_seconds"),
        "trigger-transition": ("channel", "slope", "qualifier", "low_level", "high_level", "time_seconds"),
        "trigger-delay": ("arm_channel", "arm_slope", "trigger_channel", "trigger_slope", "time_seconds", "count"),
        "trigger-setup-hold": ("clock_channel", "data_channel", "slope", "setup_time_seconds", "hold_time_seconds"),
        "trigger-edge-burst": ("source_channel", "slope", "count", "idle_time", "level"),
        "trigger-tv": ("source_channel", "standard", "mode", "polarity", "line"),
        "trigger-pattern": ("pattern",),
        "trigger-or": ("pattern",),
        "trigger-sweep": ("mode",),
        "trigger-noise-reject": ("enabled",),
        "trigger-hf-reject": ("enabled",),
        "trigger-holdoff": ("seconds",),
    }
    names = names_by_command[command]
    if command == "trigger-edge-level":
        parameters["source_channel"] = validate_analog_channel(_integer(parameters.get("source_channel", 1), "source_channel"), capabilities)
    if action == "query":
        _reject_query_parameters(parameters, names, command)
        return
    optional_names = {
        "trigger-pulse-width": {"time_seconds", "min_time_seconds", "max_time_seconds", "level"},
        "trigger-runt": {"time_seconds"},
        "trigger-edge-burst": {"level"},
        "trigger-tv": {"line"},
    }.get(command, set())
    for name in names:
        if name in optional_names:
            continue
        if command == "trigger-edge-source" and name == "source_channel":
            continue
        _require_parameter(parameters, name, command)
    if command == "trigger-edge":
        parameters["source_channel"] = validate_analog_channel(_integer(parameters["source_channel"], "source_channel"), capabilities)
        parameters["level"] = validate_trigger_level(_finite_number(parameters["level"], "level"))
        parameters["slope"] = normalize_edge_slope(parameters["slope"])
    elif command == "trigger-edge-source":
        if parameters["source"] == "analog-channel":
            _require_parameter(parameters, "source_channel", command)
            parameters["source_channel"] = validate_analog_channel(_integer(parameters["source_channel"], "source_channel"), capabilities)
    elif command == "trigger-edge-slope":
        parameters["slope"] = normalize_edge_slope(parameters["slope"])
    elif command == "trigger-edge-level":
        parameters["level"] = validate_trigger_level(_finite_number(parameters["level"], "level"))
    elif command == "external-trigger-range":
        parameters["range_volts"] = validate_external_trigger_range(_finite_number(parameters["range_volts"], "range_volts"))
    elif command == "trigger-edge-external-level":
        parameters["level"] = validate_trigger_level(_finite_number(parameters["level"], "level"))
    elif command == "external-trigger-probe":
        parameters["attenuation"] = validate_external_trigger_probe_attenuation(_finite_number(parameters["attenuation"], "attenuation"))
    elif command == "external-trigger-units":
        parameters["units"] = validate_external_trigger_units(parameters["units"])
    elif command == "trigger-edge-coupling":
        parameters["coupling"] = normalize_trigger_edge_coupling(parameters["coupling"])
    elif command == "trigger-edge-reject":
        parameters["reject"] = normalize_trigger_edge_reject(parameters["reject"])
    elif command == "trigger-pulse-width":
        parameters["channel"] = validate_analog_channel(_integer(parameters["channel"], "channel"), capabilities)
        parameters["polarity"] = normalize_glitch_polarity(parameters["polarity"])
        qualifier = parameters["qualifier"]
        parameters["qualifier"] = normalize_glitch_qualifier(qualifier)
        if qualifier == "range":
            _require_parameter(parameters, "min_time_seconds", command)
            _require_parameter(parameters, "max_time_seconds", command)
            parameters["min_time_seconds"] = validate_trigger_time(_finite_number(parameters["min_time_seconds"], "min_time_seconds"))
            parameters["max_time_seconds"] = validate_trigger_time(_finite_number(parameters["max_time_seconds"], "max_time_seconds"))
        else:
            _require_parameter(parameters, "time_seconds", command)
            parameters["time_seconds"] = validate_trigger_time(_finite_number(parameters["time_seconds"], "time_seconds"))
        if "level" in parameters: parameters["level"] = validate_trigger_level(_finite_number(parameters["level"], "level"))
    elif command == "trigger-runt":
        parameters["channel"] = validate_analog_channel(_integer(parameters["channel"], "channel"), capabilities)
        parameters["polarity"] = normalize_runt_polarity(parameters["polarity"])
        qualifier = parameters["qualifier"]
        parameters["qualifier"] = normalize_runt_qualifier(qualifier)
        parameters["low_level"] = validate_trigger_level(_finite_number(parameters["low_level"], "low_level"))
        parameters["high_level"] = validate_trigger_level(_finite_number(parameters["high_level"], "high_level"))
        if qualifier != "none":
            _require_parameter(parameters, "time_seconds", command)
            parameters["time_seconds"] = validate_trigger_time(_finite_number(parameters["time_seconds"], "time_seconds"))
    elif command == "trigger-transition":
        parameters["channel"] = validate_analog_channel(_integer(parameters["channel"], "channel"), capabilities)
        parameters["slope"] = normalize_transition_slope(parameters["slope"])
        parameters["qualifier"] = normalize_transition_qualifier(parameters["qualifier"])
        for name in ("low_level", "high_level"):
            parameters[name] = validate_trigger_level(_finite_number(parameters[name], name))
        parameters["time_seconds"] = validate_trigger_time(_finite_number(parameters["time_seconds"], "time_seconds"))
    elif command == "trigger-delay":
        for name in ("arm_channel", "trigger_channel"):
            parameters[name] = validate_analog_channel(_integer(parameters[name], name), capabilities)
        parameters["arm_slope"] = normalize_delay_slope(parameters["arm_slope"])
        parameters["trigger_slope"] = normalize_delay_slope(parameters["trigger_slope"])
        parameters["time_seconds"] = validate_delay_trigger_time(_finite_number(parameters["time_seconds"], "time_seconds"))
        parameters["count"] = validate_delay_trigger_count(_integer(parameters["count"], "count"))
    elif command == "trigger-setup-hold":
        parameters["clock_channel"] = validate_setup_hold_trigger_channel(_integer(parameters["clock_channel"], "clock_channel"), capabilities, "clock_channel")
        parameters["data_channel"] = validate_setup_hold_trigger_channel(_integer(parameters["data_channel"], "data_channel"), capabilities, "data_channel")
        parameters["slope"] = normalize_setup_hold_slope(parameters["slope"])
        parameters["setup_time_seconds"] = validate_setup_hold_trigger_time(_finite_number(parameters["setup_time_seconds"], "setup_time_seconds"), "setup_time_seconds")
        parameters["hold_time_seconds"] = validate_setup_hold_trigger_time(_finite_number(parameters["hold_time_seconds"], "hold_time_seconds"), "hold_time_seconds")
    elif command == "trigger-edge-burst":
        parameters["source_channel"] = validate_edge_burst_source_channel(_integer(parameters["source_channel"], "source_channel"), capabilities)
        parameters["slope"] = normalize_edge_burst_slope(parameters["slope"])
        parameters["count"] = validate_edge_burst_count(_integer(parameters["count"], "count"))
        parameters["idle_time"] = validate_edge_burst_idle_time(_finite_number(parameters["idle_time"], "idle_time"))
        if "level" in parameters: parameters["level"] = validate_trigger_level(_finite_number(parameters["level"], "level"))
    elif command == "trigger-tv":
        parameters["source_channel"] = validate_tv_source_channel(_integer(parameters["source_channel"], "source_channel"), capabilities)
        parameters["standard"] = normalize_tv_standard(parameters["standard"])
        parameters["mode"] = normalize_tv_mode(parameters["mode"])
        parameters["polarity"] = normalize_tv_polarity(parameters["polarity"])
        parameters["line"] = validate_tv_line(parameters["standard"], parameters["mode"], parameters.get("line"))
    elif command == "trigger-pattern":
        parameters["pattern"] = validate_pattern_trigger_pattern(parameters["pattern"], capabilities)
    elif command == "trigger-or":
        parameters["pattern"] = validate_or_trigger_pattern(parameters["pattern"], capabilities)
    elif command == "trigger-sweep":
        parameters["mode"] = normalize_trigger_sweep(parameters["mode"])
    elif command in {"trigger-noise-reject", "trigger-hf-reject"}:
        _require_boolean(parameters["enabled"], "enabled")
    elif command == "trigger-holdoff":
        parameters["seconds"] = _finite_number(parameters["seconds"], "seconds")


def _validate_p3c_serial(command: str, parameters: dict[str, Any], capabilities: Any) -> None:
    if command == "serial-lister-export":
        _require_parameter(parameters, "output", command)
        try:
            parameters["output"] = validate_save_filename_base(parameters["output"])
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        return
    if command == "serial-lister-query":
        return
    if command in {"serial-lister-display", "serial-lister-reference"}:
        action = _action(parameters, command)
        name = "display" if command.endswith("display") else "reference"
        if action == "set":
            _require_parameter(parameters, name, command)
            try:
                parameters[name] = validate_serial_lister_display(parameters[name], capabilities) if name == "display" else validate_serial_lister_reference(parameters[name], capabilities)
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (name,), command)
        return
    parameters["bus"] = validate_serial_bus(_integer(parameters.get("bus", 1), "bus"), capabilities)
    if command == "serial-query":
        return
    if command == "serial-mode":
        action = _validate_action_fields(parameters, command, ("mode",))
        if action == "set": parameters["mode"] = validate_serial_mode(parameters["mode"], capabilities)
        return
    if command == "serial-display":
        action = _validate_action_fields(parameters, command, ("enabled",))
        if action == "set": _require_boolean(parameters["enabled"], "enabled")
        return
    if command.startswith("serial-trigger-"):
        protocol = command.removeprefix("serial-trigger-")
        names = ("type", "data", "qualifier", "address", "data2", "width", "id", "id_mode", "data_length")
        action = _validate_action_fields(parameters, command, names)
        if action != "set": return
        try:
            if protocol == "uart":
                validate_serial_uart_trigger_request(parameters["bus"], type=parameters.get("type"), data=parameters.get("data"), qualifier=parameters.get("qualifier"), capabilities=capabilities)
            elif protocol == "i2c":
                validate_serial_i2c_trigger_request(parameters["bus"], type=parameters.get("type"), address=parameters.get("address"), data=parameters.get("data"), data2=parameters.get("data2"), qualifier=parameters.get("qualifier"), capabilities=capabilities)
            elif protocol == "spi":
                validate_serial_spi_trigger_request(parameters["bus"], type=parameters.get("type"), width=parameters.get("width"), data=parameters.get("data"), capabilities=capabilities)
            else:
                validate_serial_can_trigger_request(parameters["bus"], type=parameters.get("type"), id=parameters.get("id"), id_mode=parameters.get("id_mode"), data=parameters.get("data"), data_length=parameters.get("data_length"), capabilities=capabilities)
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        return
    protocol = command.removeprefix("serial-")
    action = _validate_action_fields(parameters, command, tuple(key for key in parameters if key not in {"action", "bus"}))
    if action != "set": return
    values = {key: value for key, value in parameters.items() if key not in {"action", "bus"}}
    if not values:
        raise WebUIRequestError(f"{command} set requires at least one setting")
    try:
        if protocol == "uart":
            if "rx_source" in values: values["rx_source"] = normalize_serial_source(values["rx_source"], capabilities)
            if "tx_source" in values: values["tx_source"] = normalize_serial_source(values["tx_source"], capabilities)
            if "baud_rate" in values: values["baud_rate"] = validate_uart_baud_rate(values["baud_rate"], capabilities)
            if "parity" in values: values["parity"] = normalize_uart_parity(values["parity"])
            if "polarity" in values: values["polarity"] = normalize_uart_polarity(values["polarity"])
            if "bit_order" in values: values["bit_order"] = normalize_serial_bit_order(values["bit_order"])
        elif protocol == "i2c":
            for name in ("clock_source", "data_source"):
                if name in values: values[name] = normalize_serial_source(values[name], capabilities)
            if "address_size" in values: values["address_size"] = normalize_i2c_address_size(values["address_size"])
        elif protocol == "spi":
            for name in ("clock_source", "mosi_source", "miso_source", "frame_source"):
                if name in values: values[name] = normalize_serial_source(values[name], capabilities)
            if "clock_slope" in values: values["clock_slope"] = normalize_spi_clock_slope(values["clock_slope"])
            if "bit_order" in values: values["bit_order"] = normalize_serial_bit_order(values["bit_order"])
            if "framing" in values: values["framing"] = normalize_spi_framing(values["framing"])
            if "clock_timeout" in values: validate_spi_framing_clock_timeout(values.get("framing"), values.get("clock_timeout"))
        else:
            if "source" in values: values["source"] = normalize_serial_source(values["source"], capabilities)
            if "baud_rate" in values: values["baud_rate"] = validate_can_baud_rate(values["baud_rate"])
            if "sample_point" in values: values["sample_point"] = validate_can_sample_point(values["sample_point"], capabilities)
            if "signal_definition" in values: values["signal_definition"] = normalize_can_signal_definition(values["signal_definition"])
    except Exception as exc:
        raise WebUIRequestError(str(exc)) from exc
    parameters.update(values)


def _validate_parameters(
    command: str,
    parameters: dict[str, Any],
    mode: str,
    model_id: str,
) -> None:
    capabilities = capabilities_for_model_id(model_id)
    if command in _P3C_COMMAND_IDS:
        _validate_p3c_parameters(command, parameters, mode, model_id)
        return
    if command == "acquisition":
        action = parameters.setdefault("action", "query")
        if action not in {"query", "set"}:
            raise WebUIRequestError("acquisition action must be query or set")
        if action == "set" and "type" not in parameters and "count" not in parameters:
            raise WebUIRequestError("acquisition set requires type or count")
        if "type" in parameters:
            try:
                parameters["type"] = _normalize_acquisition_type(parameters["type"])
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        if "count" in parameters:
            parameters["count"] = _integer(parameters["count"], "count")
            try:
                validate_acquisition_count(parameters["count"])
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        if mode == "dry-run" and action != "query":
            raise WebUIRequestError("dry-run acquisition supports query only")
    elif command in {"channel-display", "channel-scale"}:
        action = parameters.setdefault("action", "query")
        if action not in {"query", "set"}:
            raise WebUIRequestError(f"{command} action must be query or set")
        channel = _integer(parameters.get("channel", 1), "channel")
        parameters["channel"] = validate_analog_channel(channel, capabilities)
        if action == "set":
            if command == "channel-display":
                if not isinstance(parameters.get("enabled"), bool):
                    raise WebUIRequestError("enabled must be a boolean for channel-display set")
            else:
                if "volts_per_division" not in parameters:
                    raise WebUIRequestError("channel-scale set requires volts_per_division")
                try:
                    parameters["volts_per_division"] = validate_channel_scale(
                        _finite_number(parameters["volts_per_division"], "volts_per_division")
                    )
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
    elif command in {
        "channel-label",
        "channel-offset",
        "channel-coupling",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
    }:
        action = _action(parameters, command)
        channel = _integer(parameters.get("channel", 1), "channel")
        parameters["channel"] = validate_analog_channel(channel, capabilities)
        value_name = {
            "channel-label": "text",
            "channel-offset": "volts",
            "channel-coupling": "coupling",
            "channel-probe": "ratio",
            "channel-bandwidth-limit": "enabled",
            "channel-impedance": "impedance",
            "channel-invert": "enabled",
            "channel-range": "volts",
            "channel-units": "units",
            "channel-vernier": "enabled",
            "channel-probe-skew": "seconds",
        }[command]
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if command == "channel-label":
                    parameters[value_name] = validate_channel_label(parameters[value_name], capabilities)
                elif command == "channel-offset":
                    parameters[value_name] = validate_channel_offset(
                        _finite_number(parameters[value_name], value_name)
                    )
                elif command == "channel-coupling":
                    parameters[value_name] = normalize_channel_coupling(parameters[value_name])
                elif command == "channel-probe":
                    parameters[value_name] = validate_probe_ratio(
                        _finite_number(parameters[value_name], value_name)
                    )
                elif command in {"channel-bandwidth-limit", "channel-invert", "channel-vernier"}:
                    _require_boolean(parameters[value_name], value_name)
                elif command == "channel-impedance":
                    parameters[value_name] = normalize_channel_impedance(parameters[value_name])
                    validate_channel_impedance_supported(parameters[value_name], capabilities)
                elif command == "channel-range":
                    parameters[value_name] = validate_channel_range(
                        _finite_number(parameters[value_name], value_name)
                    )
                elif command == "channel-units":
                    parameters[value_name] = normalize_channel_units(parameters[value_name])
                elif command == "channel-probe-skew":
                    parameters[value_name] = validate_probe_skew(
                        _finite_number(parameters[value_name], value_name)
                    )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command in {"display-label", "display-persistence", "display-intensity", "display-vectors"}:
        action = _action(parameters, command)
        value_name = {
            "display-label": "enabled",
            "display-persistence": "value",
            "display-intensity": "value",
        }.get(command)
        if action == "set":
            if value_name is not None:
                _require_parameter(parameters, value_name, command)
            try:
                if command == "display-label":
                    _require_boolean(parameters[value_name], value_name)
                elif command == "display-persistence":
                    mode, seconds = validate_display_persistence(parameters[value_name])
                    parameters[value_name] = mode if mode is not None else seconds
                elif command == "display-intensity":
                    parameters[value_name] = validate_display_intensity(
                        _integer(parameters[value_name], value_name)
                    )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,) if value_name else (), command)
    elif command in {"measure-show", "measure-source", "measure-window"}:
        action = _action(parameters, command)
        if command == "measure-show":
            if action == "set":
                pass
            else:
                _reject_query_parameters(parameters, (), command)
        elif command == "measure-source":
            if action == "set":
                _require_parameter(parameters, "source_channel", command)
                parameters["source_channel"] = validate_analog_channel(
                    _integer(parameters["source_channel"], "source_channel"), capabilities
                )
                if "source2_channel" in parameters:
                    parameters["source2_channel"] = validate_analog_channel(
                        _integer(parameters["source2_channel"], "source2_channel"), capabilities
                    )
            else:
                _reject_query_parameters(parameters, ("source_channel", "source2_channel"), command)
        else:
            if action == "set":
                _require_parameter(parameters, "window", command)
                try:
                    parameters["window"] = normalize_measurement_window(parameters["window"])
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, ("window",), command)
    elif command == "reference-save":
        _require_parameter(parameters, "slot", command)
        _require_parameter(parameters, "source_channel", command)
        try:
            parameters["slot"] = validate_reference_slot(
                _integer(parameters["slot"], "slot"), capabilities
            )
            parameters["source_channel"] = validate_analog_channel(
                _integer(parameters["source_channel"], "source_channel"), capabilities
            )
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
    elif command in {"reference-display", "reference-label"}:
        action = _action(parameters, command)
        try:
            parameters["slot"] = validate_reference_slot(
                _integer(parameters.get("slot", 1), "slot"), capabilities
            )
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        value_name = "enabled" if command == "reference-display" else "label"
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if command == "reference-display":
                    _require_boolean(parameters[value_name], value_name)
                else:
                    parameters[value_name] = validate_reference_label(parameters[value_name])
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command in {"reference-clear", "reference-query"}:
        try:
            parameters["slot"] = validate_reference_slot(
                _integer(parameters.get("slot", 1), "slot"), capabilities
            )
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
    elif command in {
        "save-pwd",
        "save-filename",
        "save-image-format",
        "save-image-palette",
        "save-image-ink-saver",
        "save-image-factors",
        "save-waveform-format",
        "save-waveform-length",
    }:
        action = _action(parameters, command)
        value_name = {
            "save-pwd": "path",
            "save-filename": "name",
            "save-image-format": "format",
            "save-image-palette": "palette",
            "save-image-ink-saver": "enabled",
            "save-image-factors": "enabled",
            "save-waveform-format": "format",
            "save-waveform-length": "points",
        }[command]
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if command == "save-pwd":
                    parameters[value_name] = validate_save_quoted_string(
                        parameters[value_name], label="Save path"
                    )
                elif command == "save-filename":
                    parameters[value_name] = validate_save_filename_base(parameters[value_name])
                elif command == "save-image-format":
                    if parameters[value_name] not in SAVE_IMAGE_FORMATS:
                        raise ValueError(
                            f"image format must be one of: {', '.join(SAVE_IMAGE_FORMATS)}"
                        )
                elif command == "save-image-palette":
                    if parameters[value_name] not in SAVE_IMAGE_PALETTES:
                        raise ValueError(
                            f"image palette must be one of: {', '.join(SAVE_IMAGE_PALETTES)}"
                        )
                elif command in {"save-image-ink-saver", "save-image-factors"}:
                    _require_boolean(parameters[value_name], value_name)
                elif command == "save-waveform-format":
                    if parameters[value_name] not in SAVE_WAVEFORM_FORMATS:
                        raise ValueError(
                            f"waveform format must be one of: {', '.join(SAVE_WAVEFORM_FORMATS)}"
                        )
                else:
                    parameters[value_name] = validate_save_waveform_length(
                        _integer(parameters[value_name], value_name)
                    )
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command in {"save-image", "save-waveform"}:
        _require_parameter(parameters, "filename", command)
        try:
            parameters["filename"] = validate_save_quoted_string(
                parameters["filename"],
                label="Save image filename" if command == "save-image" else "Save waveform filename",
            )
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
    elif command in {"dvm-enable", "dvm-source", "dvm-mode", "dvm-auto-range"}:
        action = _action(parameters, command)
        value_name = {
            "dvm-enable": "enabled",
            "dvm-source": "channel",
            "dvm-mode": "mode",
            "dvm-auto-range": "enabled",
        }[command]
        if action == "set":
            _require_parameter(parameters, value_name, command)
            try:
                if value_name == "enabled":
                    _require_boolean(parameters[value_name], value_name)
                elif command == "dvm-source":
                    parameters[value_name] = validate_analog_channel(
                        _integer(parameters[value_name], value_name), capabilities
                    )
                else:
                    normalize_dvm_mode(parameters[value_name])
            except Exception as exc:
                raise WebUIRequestError(str(exc)) from exc
        else:
            _reject_query_parameters(parameters, (value_name,), command)
    elif command == "fft":
        action = _action(parameters, command)
        parameters["function"] = _integer(parameters.get("function", 1), "function")
        if action == "set":
            _require_parameter(parameters, "source_channel", command)
            parameters["source_channel"] = validate_analog_channel(
                _integer(parameters["source_channel"], "source_channel"), capabilities
            )
            for name in ("center_hz", "span_hz"):
                if name in parameters:
                    parameters[name] = _finite_number(parameters[name], name)
            if "center_hz" in parameters and parameters["center_hz"] < 0:
                raise WebUIRequestError("center_hz must be non-negative")
            if "span_hz" in parameters and parameters["span_hz"] <= 0:
                raise WebUIRequestError("span_hz must be greater than zero")
            if "units" in parameters:
                try:
                    normalize_fft_units(parameters["units"])
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            if "window" in parameters:
                try:
                    normalize_fft_window(parameters["window"])
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            if "display" in parameters:
                _require_boolean(parameters["display"], "display")
        else:
            _reject_query_parameters(
                parameters,
                ("source_channel", "units", "window", "center_hz", "span_hz", "display"),
                command,
            )
    elif command in {"math-display", "math-vertical", "math-operator", "math-composite-source"}:
        action = _action(parameters, command)
        if command != "math-composite-source":
            parameters["function"] = _integer(parameters.get("function", 1), "function")
        if command == "math-display":
            if action == "set":
                _require_parameter(parameters, "enabled", command)
                _require_boolean(parameters["enabled"], "enabled")
            else:
                _reject_query_parameters(parameters, ("enabled",), command)
        elif command == "math-vertical":
            names = ("scale", "range_value", "offset")
            if action == "set":
                if not any(name in parameters for name in names):
                    raise WebUIRequestError("math-vertical set requires scale, range_value, or offset")
                try:
                    for name in ("scale", "range_value"):
                        if name in parameters:
                            parameters[name] = validate_positive(
                                _finite_number(parameters[name], name), name
                            )
                    if "offset" in parameters:
                        parameters["offset"] = validate_finite_number(
                            _finite_number(parameters["offset"], "offset"), "offset"
                        )
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, names, command)
        elif command == "math-operator":
            names = ("operation", "source1", "source2")
            if action == "set":
                for name in names:
                    _require_parameter(parameters, name, command)
                try:
                    parameters["operation"] = normalize_math_operation(parameters["operation"])
                    parameters["source1"] = normalize_math_source(
                        parameters["source1"], capabilities=capabilities
                    )
                    parameters["source2"] = normalize_math_source(
                        parameters["source2"], capabilities=capabilities
                    )
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, names, command)
        else:
            names = ("operation", "source1", "source2")
            if action == "set":
                for name in names:
                    _require_parameter(parameters, name, command)
                try:
                    parameters["operation"] = normalize_math_composite_operation(parameters["operation"])
                    parameters["source1"] = normalize_math_source(
                        parameters["source1"], capabilities=capabilities
                    )
                    parameters["source2"] = normalize_math_source(
                        parameters["source2"], capabilities=capabilities
                    )
                except Exception as exc:
                    raise WebUIRequestError(str(exc)) from exc
            else:
                _reject_query_parameters(parameters, names, command)
    elif command == "math-clear":
        parameters["function"] = _integer(parameters.get("function", 1), "function")
    elif command == "measure":
        try:
            parameters["item"] = normalize_measurement_item(parameters.get("item", "vpp"))
        except Exception as exc:
            raise WebUIRequestError(str(exc)) from exc
        parameters["channel"] = validate_analog_channel(
            _integer(parameters.get("channel", 1), "channel"), capabilities
        )
        if "reference_channel" in parameters:
            parameters["reference_channel"] = validate_analog_channel(
                _integer(parameters["reference_channel"], "reference_channel"), capabilities
            )
        for name in ("time_s", "level"):
            if name in parameters:
                parameters[name] = _finite_number(parameters[name], name)
        if "occurrence" in parameters:
            parameters["occurrence"] = _integer(parameters["occurrence"], "occurrence")
        if "slope" in parameters and parameters["slope"] not in {"positive", "negative"}:
            raise WebUIRequestError("slope must be positive or negative")
    elif command == "capture":
        parameters["channel"] = validate_analog_channel(
            _integer(parameters.get("channel", 1), "channel"), capabilities
        )
        parameters["points"] = _integer(parameters.get("points", 1000), "points")
        if parameters["points"] not in {1000, 5000, 10000}:
            raise WebUIRequestError("points must be one of: 1000, 5000, 10000")
        parameters["format"] = str(parameters.get("format", "byte")).lower()
        if parameters["format"] not in {"byte", "word"}:
            raise WebUIRequestError("format must be byte or word")
        if parameters["format"] == "word" and not capabilities.supports_word_format:
            raise WebUIRequestError("word waveform format is not supported by this model")
    elif command == "screenshot":
        parameters["background"] = str(parameters.get("background", "black")).lower()
        if parameters["background"] not in {"black", "white"}:
            raise WebUIRequestError("background must be black or white")


def _normalize_acquisition_type(value: Any) -> str:
    normalized = normalize_acquisition_type(value)
    return {
        "NORMal": "normal",
        "AVERage": "average",
        "HRESolution": "high_resolution",
        "PEAK": "peak",
    }[normalized]


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WebUIRequestError(f"{name} must be an integer")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WebUIRequestError(f"{name} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise WebUIRequestError(f"{name} must be finite")
    return parsed


def _action(parameters: dict[str, Any], command: str) -> str:
    action = parameters.setdefault("action", "query")
    if action not in {"query", "set"}:
        raise WebUIRequestError(f"{command} action must be query or set")
    return action


def _require_parameter(parameters: Mapping[str, Any], name: str, command: str) -> None:
    if name not in parameters:
        raise WebUIRequestError(f"{command} set requires {name}")


def _reject_query_parameters(
    parameters: Mapping[str, Any], names: tuple[str, ...], command: str
) -> None:
    for name in names:
        if name in parameters:
            raise WebUIRequestError(f"{command} query cannot include {name}")


def _require_boolean(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise WebUIRequestError(f"{name} must be a boolean")


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"byte_length": len(value)}
    return value
