"""WebUI command catalog: definitions, metadata, and catalog API payload builders."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from scopes_tool_core import capabilities_for_model_id
from scopes_tool_core.identity import PHYSICAL_MODEL_REGISTRY
from scopes_tool_core.dvm import DVM_MODES
from scopes_tool_core.math import (
    MATH_COMPOSITE_OPERATIONS,
    MATH_OPERATIONS,
    MATH_SOURCES,
)
from scopes_tool_core.measurements import (
    MEASUREMENT_WINDOW_CHOICES,
    PAIR_MEASUREMENT_ITEMS,
    SUPPORTED_MEASUREMENT_ITEMS,
    validate_statistics_items,
)
from scopes_tool_core.errors import ParameterValidationError
from scopes_tool_core.save_export import (
    SAVE_IMAGE_FORMATS,
    SAVE_IMAGE_PALETTES,
    SAVE_WAVEFORM_FORMATS,
)
from scopes_tool_core.search import (
    CAN_SEARCH_ID_MODES,
    CAN_SEARCH_MODES,
    I2C_SEARCH_MODES,
    SEARCH_MODES,
    SEARCH_QUALIFIERS,
    SPI_SEARCH_MODES,
    UART_SEARCH_MODES,
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
)


def _direct_measurement_items() -> tuple[str, ...]:
    """Project Core's statistics validation contract for simple workflows."""

    choices: list[str] = []
    for item in SUPPORTED_MEASUREMENT_ITEMS:
        try:
            choices.extend(validate_statistics_items((item,)))
        except ParameterValidationError:
            continue
    return tuple(dict.fromkeys(choices))


_DIRECT_MEASUREMENT_ITEMS = _direct_measurement_items()
COMMANDS = (
    {
        "id": "live-data-snapshot",
        "category": "Device",
        "label": "Live Data snapshot",
        "hidden": True,
        "modes": ("live", "simulate"),
        "fields": (),
    },
    {
        "id": "list-resources",
        "category": "Device",
        "label": "List resources",
        "hidden": True,
        "modes": ("live", "simulate", "dry-run"),
        "fields": (
            {"name": "live_only", "type": "boolean", "default": False},
        ),
    },
    {
        "id": "identify",
        "category": "Identity",
        "label": "Read device information",
        "description": "Read instrument identification information",
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
            {
                "name": "type",
                "type": "enum",
                "options": ("normal", "average", "high_resolution", "peak"),
                "required_if": [{"field": "action", "equals": "set"}],
            },
            {
                "name": "count",
                "type": "integer",
                "minimum": 2,
                "maximum": 65536,
                "visible_if": [{"field": "type", "equals": "average"}],
                "help_key": "acquisition.average_count",
            },
        ),
    },
    {
        "id": "timebase-scale",
        "category": "Timebase",
        "label": "Timebase scale",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {
                "name": "seconds_per_division",
                "type": "number",
                "minimum": 0,
                "required_if": [{"field": "action", "equals": "set"}],
                "help_key": "timebase.seconds_per_division",
            },
        ),
    },
    {
        "id": "timebase-position",
        "category": "Timebase",
        "label": "Timebase position",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {
                "name": "position_seconds",
                "type": "number",
                "required_if": [{"field": "action", "equals": "set"}],
                "help_key": "timebase.position_seconds",
            },
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
            {"name": "enabled", "type": "boolean", "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "volts_per_division", "type": "number", "minimum": 0, "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "text", "type": "string", "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "volts", "type": "number", "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "coupling", "type": "enum", "options": ("ac", "dc"), "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "ratio", "type": "number", "minimum": 0, "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "enabled", "type": "boolean", "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "impedance", "type": "enum", "options": ("one_meg", "fifty"), "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "enabled", "type": "boolean", "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "volts", "type": "number", "minimum": 0, "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "units", "type": "enum", "options": ("volt", "amp"), "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "enabled", "type": "boolean", "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "seconds", "type": "number", "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "display-label",
        "category": "Display",
        "label": "Display label",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean", "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "mode", "type": "enum", "options": ("minimum", "infinite", "timed"), "visible_if": [{"field": "action", "equals": "set"}], "required_if": [{"field": "action", "equals": "set"}]},
            {"name": "seconds", "type": "number", "minimum": 0.1, "maximum": 60.0, "visible_if": [{"field": "action", "equals": "set"}, {"field": "mode", "equals": "timed"}], "required_if": [{"field": "action", "equals": "set"}, {"field": "mode", "equals": "timed"}]},
        ),
    },
    {
        "id": "display-intensity",
        "category": "Display",
        "label": "Display intensity",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "value", "type": "integer", "minimum": 0, "maximum": 100, "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "source_channel", "type": "integer", "minimum": 1, "maximum": 4, "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "window", "type": "enum", "options": MEASUREMENT_WINDOW_CHOICES, "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "slot", "type": "integer", "minimum": 1, "maximum": 2, "required": True},
            {"name": "source_channel", "type": "integer", "minimum": 1, "maximum": 4, "required": True},
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
            {"name": "enabled", "type": "boolean", "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "label", "type": "string", "required_if": [{"field": "action", "equals": "set"}]},
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
        "group": "path-filename",
        "editor": "save-export",
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "path", "type": "string", "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "save-filename",
        "category": "Save / Export",
        "label": "Save filename",
        "modes": ("live", "simulate"),
        "group": "path-filename",
        "editor": "save-export",
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "name", "type": "string", "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "save-image-format",
        "category": "Save / Export",
        "label": "Image save format",
        "modes": ("live", "simulate"),
        "group": "image",
        "editor": "save-export",
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "format", "type": "enum", "options": SAVE_IMAGE_FORMATS, "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "save-image-palette",
        "category": "Save / Export",
        "label": "Image save palette",
        "modes": ("live", "simulate"),
        "group": "image",
        "editor": "save-export",
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "palette", "type": "enum", "options": SAVE_IMAGE_PALETTES, "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "save-image-ink-saver",
        "category": "Save / Export",
        "label": "Image ink saver",
        "modes": ("live", "simulate"),
        "group": "image",
        "editor": "save-export",
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean", "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "save-image-factors",
        "category": "Save / Export",
        "label": "Image measurement factors",
        "modes": ("live", "simulate"),
        "group": "image",
        "editor": "save-export",
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean", "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "save-image",
        "category": "Save / Export",
        "label": "Save image",
        "modes": ("live", "simulate"),
        "group": "image",
        "editor": "save-export",
        "fields": (
            {"name": "filename", "type": "string", "required": True},
        ),
    },
    {
        "id": "save-waveform-format",
        "category": "Save / Export",
        "label": "Waveform save format",
        "modes": ("live", "simulate"),
        "group": "waveform",
        "editor": "save-export",
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "format", "type": "enum", "options": SAVE_WAVEFORM_FORMATS, "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "save-waveform-length",
        "category": "Save / Export",
        "label": "Waveform save length",
        "modes": ("live", "simulate"),
        "group": "waveform",
        "editor": "save-export",
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "points", "type": "integer", "minimum": 100, "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "save-waveform-length-max",
        "category": "Save / Export",
        "label": "Maximum waveform save length",
        "modes": ("live", "simulate"),
        "group": "waveform",
        "editor": "save-export",
        "fields": (),
    },
    {
        "id": "save-waveform",
        "category": "Save / Export",
        "label": "Save waveform",
        "modes": ("live", "simulate"),
        "group": "waveform",
        "editor": "save-export",
        "fields": (
            {"name": "filename", "type": "string", "required": True},
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
            {"name": "enabled", "type": "boolean", "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "dvm-source",
        "category": "DVM",
        "label": "DVM source",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "dvm-mode",
        "category": "DVM",
        "label": "DVM mode",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "mode", "type": "enum", "options": DVM_MODES, "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "dvm-auto-range",
        "category": "DVM",
        "label": "DVM auto range",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "enabled", "type": "boolean", "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "source_channel", "type": "integer", "minimum": 1, "maximum": 4, "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "enabled", "type": "boolean", "required_if": [{"field": "action", "equals": "set"}]},
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
            {"name": "operation", "type": "enum", "options": MATH_OPERATIONS, "required_if": [{"field": "action", "equals": "set"}]},
            {"name": "source1", "type": "enum", "options": MATH_SOURCES, "required_if": [{"field": "action", "equals": "set"}]},
            {"name": "source2", "type": "enum", "options": MATH_SOURCES, "required_if": [{"field": "action", "equals": "set"}]},
        ),
    },
    {
        "id": "math-composite-source",
        "category": "FFT / MATH",
        "label": "Math composite source",
        "modes": ("live", "simulate"),
        "fields": (
            {"name": "action", "type": "enum", "options": ("query", "set"), "default": "query"},
            {"name": "operation", "type": "enum", "options": MATH_COMPOSITE_OPERATIONS, "required_if": [{"field": "action", "equals": "set"}]},
            {"name": "source1", "type": "enum", "options": MATH_SOURCES, "required_if": [{"field": "action", "equals": "set"}]},
            {"name": "source2", "type": "enum", "options": MATH_SOURCES, "required_if": [{"field": "action", "equals": "set"}]},
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


def _command_field(name: str, field_type: str, *, visible_if: list[dict[str, Any]] | None = None, **kwargs: Any) -> dict[str, Any]:
    field = {"name": name, "type": field_type, **kwargs}
    if visible_if is not None:
        field["visible_if"] = visible_if
    return field


def _action_field() -> dict[str, Any]:
    return {
        "name": "action",
        "type": "enum",
        "options": ("query", "set"),
        "default": "query",
    }


def _set_action_visibility(*conditions: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"field": "action", "equals": "set"}, *conditions]


def _action_command(
    command_id: str,
    category: str,
    label: str,
    fields: tuple[dict[str, Any], ...],
    *,
    modes: tuple[str, ...] = ("live", "simulate"),
    group: str | None = None,
    editor: str | None = None,
) -> dict[str, Any]:
    entry = {
        "id": command_id,
        "category": category,
        "label": label,
        "modes": modes,
        "fields": (_action_field(), *fields),
    }
    if group is not None:
        entry["group"] = group
    if editor is not None:
        entry["editor"] = editor
    return entry


_TRIGGER_SLOPES = ("positive", "negative", "either", "alternate")
_BINARY_SLOPES = ("positive", "negative")
_TV_LINE_MODES = ("line-field1", "line-field2", "line-alternate")

TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMANDS = (
    _action_command(
        "trigger-edge", "Trigger", "Edge trigger", (
            _command_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("slope", "enum", options=_TRIGGER_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
        ),
        group="edge",
        editor="trigger",
    ),
    _action_command(
        "trigger-edge-source", "Trigger", "Edge trigger source", (
            _command_field("source", "enum", options=("analog-channel", "external", "line"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility({"field": "source", "equals": "analog-channel"}), required_if=_set_action_visibility({"field": "source", "equals": "analog-channel"})),
        ),
        group="edge",
        editor="trigger",
    ),
    _action_command("trigger-edge-slope", "Trigger", "Edge trigger slope", (_command_field("slope", "enum", options=_TRIGGER_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="edge", editor="trigger"),
    _action_command(
        "trigger-edge-level", "Trigger", "Edge trigger level", (
            _command_field("source_channel", "integer", minimum=1, maximum=4),
            _command_field("level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
        ),
        group="edge",
        editor="trigger",
    ),
    _action_command("external-trigger-range", "Trigger", "External trigger range", (_command_field("range_volts", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="external", editor="trigger"),
    _action_command("trigger-edge-external-level", "Trigger", "External trigger level", (_command_field("level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="external", editor="trigger"),
    _action_command("external-trigger-probe", "Trigger", "External trigger probe", (_command_field("attenuation", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="external", editor="trigger"),
    _action_command("external-trigger-units", "Trigger", "External trigger units", (_command_field("units", "enum", options=("volts", "amps"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="external", editor="trigger"),
    {"id": "external-trigger-settings", "category": "Trigger", "label": "External trigger settings", "modes": ("live", "simulate"), "fields": (), "group": "external", "editor": "trigger"},
    _action_command("trigger-edge-coupling", "Trigger", "Edge trigger coupling", (_command_field("coupling", "enum", options=("ac", "dc", "lf-reject"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="edge", editor="trigger"),
    _action_command("trigger-edge-reject", "Trigger", "Edge trigger reject", (_command_field("reject", "enum", options=("off", "lf-reject", "hf-reject"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="edge", editor="trigger"),
    _action_command(
        "trigger-pulse-width", "Trigger", "Glitch / pulse-width trigger", (
            _command_field("channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("polarity", "enum", options=("positive", "negative"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("qualifier", "enum", options=("greater-than", "less-than", "range"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("time_seconds", "number", visible_if=_set_action_visibility({"field": "qualifier", "in": ("greater-than", "less-than")}), required_if=_set_action_visibility({"field": "qualifier", "in": ("greater-than", "less-than")})),
            _command_field("min_time_seconds", "number", visible_if=_set_action_visibility({"field": "qualifier", "equals": "range"}), required_if=_set_action_visibility({"field": "qualifier", "equals": "range"})),
            _command_field("max_time_seconds", "number", visible_if=_set_action_visibility({"field": "qualifier", "equals": "range"}), required_if=_set_action_visibility({"field": "qualifier", "equals": "range"})),
            _command_field("level", "number", visible_if=_set_action_visibility()),
        ),
        group="pulse-width",
        editor="trigger",
    ),
    _action_command(
        "trigger-runt", "Trigger", "Runt trigger", (
            _command_field("channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("polarity", "enum", options=("positive", "negative", "either"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("qualifier", "enum", options=("greater-than", "less-than", "none"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("low_level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("high_level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("time_seconds", "number", visible_if=_set_action_visibility({"field": "qualifier", "in": ("greater-than", "less-than")}), required_if=_set_action_visibility({"field": "qualifier", "in": ("greater-than", "less-than")})),
        ),
        group="runt",
        editor="trigger",
    ),
    _action_command(
        "trigger-transition", "Trigger", "Transition trigger", (
            _command_field("channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("slope", "enum", options=_BINARY_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("qualifier", "enum", options=("greater-than", "less-than"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("low_level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("high_level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("time_seconds", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
        ),
        group="transition",
        editor="trigger",
    ),
    _action_command(
        "trigger-delay", "Trigger", "Delay trigger", (
            _command_field("arm_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("arm_slope", "enum", options=_BINARY_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("trigger_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("trigger_slope", "enum", options=_BINARY_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("time_seconds", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("count", "integer", minimum=1, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
        ),
        group="delay",
        editor="trigger",
    ),
    _action_command(
        "trigger-setup-hold", "Trigger", "Setup and hold trigger", (
            _command_field("clock_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("data_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("slope", "enum", options=_BINARY_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("setup_time_seconds", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("hold_time_seconds", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
        ),
        group="setup-hold",
        editor="trigger",
    ),
    _action_command(
        "trigger-edge-burst", "Trigger", "Nth edge burst trigger", (
            _command_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("slope", "enum", options=_BINARY_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("count", "integer", minimum=1, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("idle_time", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("level", "number", visible_if=_set_action_visibility()),
        ),
        group="edge-burst",
        editor="trigger",
    ),
    _action_command(
        "trigger-tv", "Trigger", "TV trigger", (
            _command_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("standard", "enum", options=("ntsc", "pal", "palm", "secam"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("mode", "enum", options=("field1", "field2", "all-fields", "all-lines", *_TV_LINE_MODES), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("polarity", "enum", options=("positive", "negative"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("line", "integer", minimum=1, visible_if=_set_action_visibility({"field": "mode", "in": _TV_LINE_MODES}), required_if=_set_action_visibility({"field": "mode", "in": _TV_LINE_MODES})),
        ),
        group="tv",
        editor="trigger",
    ),
    _action_command("trigger-pattern", "Trigger", "Pattern trigger", (_command_field("pattern", "string", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="pattern-or", editor="trigger"),
    _action_command("trigger-or", "Trigger", "OR trigger", (_command_field("pattern", "string", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="pattern-or", editor="trigger"),
    _action_command("trigger-sweep", "Trigger", "Trigger sweep", (_command_field("mode", "enum", options=("auto", "normal"), visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="common", editor="trigger"),
    _action_command("trigger-noise-reject", "Trigger", "Noise reject", (_command_field("enabled", "boolean", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="common", editor="trigger"),
    _action_command("trigger-hf-reject", "Trigger", "HF reject", (_command_field("enabled", "boolean", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="common", editor="trigger"),
    _action_command("trigger-holdoff", "Trigger", "Trigger holdoff", (_command_field("seconds", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="common", editor="trigger"),

    _action_command("search-state", "Search", "Search state", (_command_field("enabled", "boolean", visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="basic", editor="search"),
    _action_command("search-mode", "Search", "Search mode", (_command_field("mode", "enum", options=SEARCH_MODES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="basic", editor="search"),
    {"id": "search-count", "category": "Search", "label": "Search count", "modes": ("live", "simulate"), "fields": (), "group": "basic", "editor": "search"},
    _action_command("search-event", "Search", "Search event", (_command_field("event", "integer", minimum=1, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="event", editor="search"),
    _action_command(
        "serial-search-uart", "Search", "UART serial search", (
            _command_field("bus", "integer", minimum=1),
            _command_field("mode", "enum", options=UART_SEARCH_MODES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("data", "integer", visible_if=_set_action_visibility({"field": "mode", "in": ("rx-data", "tx-data")})),
            _command_field("qualifier", "enum", options=SEARCH_QUALIFIERS, visible_if=_set_action_visibility({"field": "mode", "in": ("rx-data", "tx-data")})),
        ),
        group="serial",
        editor="search",
    ),
    _action_command(
        "serial-search-i2c", "Search", "I2C serial search", (
            _command_field("bus", "integer", minimum=1),
            _command_field("mode", "enum", options=I2C_SEARCH_MODES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("address", "integer", visible_if=_set_action_visibility()),
            _command_field("data", "integer", visible_if=_set_action_visibility()),
            _command_field("data2", "integer", visible_if=_set_action_visibility({"field": "mode", "in": ("read7-data2", "write7-data2")})),
            _command_field("qualifier", "enum", options=SEARCH_QUALIFIERS, visible_if=_set_action_visibility({"field": "mode", "equals": "eeprom-read"})),
        ),
        group="serial",
        editor="search",
    ),
    _action_command(
        "serial-search-spi", "Search", "SPI serial search", (
            _command_field("bus", "integer", minimum=1),
            _command_field("mode", "enum", options=SPI_SEARCH_MODES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("data", "string", visible_if=_set_action_visibility()),
            _command_field("width", "integer", minimum=1, visible_if=_set_action_visibility()),
        ),
        group="serial",
        editor="search",
    ),
    _action_command(
        "serial-search-can", "Search", "CAN serial search", (
            _command_field("bus", "integer", minimum=1),
            _command_field("mode", "enum", options=CAN_SEARCH_MODES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),
            _command_field("data", "string", visible_if=_set_action_visibility()),
            _command_field("data_length", "integer", minimum=0, visible_if=_set_action_visibility()),
            _command_field("id", "string", visible_if=_set_action_visibility({"field": "mode", "in": ("id-data", "id-either", "id-remote")})),
            _command_field("id_mode", "enum", options=CAN_SEARCH_ID_MODES, visible_if=_set_action_visibility({"field": "mode", "in": ("id-data", "id-either", "id-remote")})),
        ),
        group="serial",
        editor="search",
    ),

    {
        "id": "serial-query", "category": "Serial", "label": "Serial query",
        "modes": ("live", "simulate"), "fields": (_command_field("bus", "integer", minimum=1),),
        "group": "bus",
    },
    _action_command("serial-mode", "Serial", "Serial mode", (_command_field("bus", "integer", minimum=1), _command_field("mode", "enum", options=SERIAL_MODES, visible_if=_set_action_visibility(), required_if=_set_action_visibility())), group="bus", editor="serial"),
    _action_command("serial-display", "Serial", "Serial display", (_command_field("bus", "integer", minimum=1), _command_field("enabled", "boolean", visible_if=_set_action_visibility(), required_if=_set_action_visibility())), group="bus", editor="serial"),
    _action_command(
        "serial-uart", "Serial", "UART configuration", (
            _command_field("bus", "integer", minimum=1),
            _command_field("rx_source", "string", visible_if=_set_action_visibility()), _command_field("tx_source", "string", visible_if=_set_action_visibility()),
            _command_field("baud_rate", "integer", visible_if=_set_action_visibility()), _command_field("data_bits", "integer", minimum=5, maximum=9, visible_if=_set_action_visibility()),
            _command_field("parity", "enum", options=UART_PARITIES, visible_if=_set_action_visibility()), _command_field("polarity", "enum", options=UART_POLARITIES, visible_if=_set_action_visibility()),
            _command_field("bit_order", "enum", options=SERIAL_BIT_ORDERS, visible_if=_set_action_visibility()),
        ),
        group="uart",
        editor="serial",
    ),
    _action_command("serial-i2c", "Serial", "I2C configuration", (_command_field("bus", "integer", minimum=1), _command_field("clock_source", "string", visible_if=_set_action_visibility()), _command_field("data_source", "string", visible_if=_set_action_visibility()), _command_field("address_size", "enum", options=I2C_ADDRESS_SIZES, visible_if=_set_action_visibility())), group="i2c", editor="serial"),
    _action_command("serial-spi", "Serial", "SPI configuration", (_command_field("bus", "integer", minimum=1), _command_field("clock_source", "string", visible_if=_set_action_visibility()), _command_field("mosi_source", "string", visible_if=_set_action_visibility()), _command_field("miso_source", "string", visible_if=_set_action_visibility()), _command_field("frame_source", "string", visible_if=_set_action_visibility()), _command_field("clock_slope", "enum", options=SPI_CLOCK_SLOPES, visible_if=_set_action_visibility()), _command_field("bit_order", "enum", options=SERIAL_BIT_ORDERS, visible_if=_set_action_visibility()), _command_field("word_width", "integer", minimum=4, maximum=16, visible_if=_set_action_visibility()), _command_field("framing", "enum", options=SPI_FRAMINGS, visible_if=_set_action_visibility()), _command_field("clock_timeout", "number", visible_if=_set_action_visibility())), group="spi", editor="serial"),
    _action_command("serial-can", "Serial", "CAN configuration", (_command_field("bus", "integer", minimum=1), _command_field("source", "string", visible_if=_set_action_visibility()), _command_field("baud_rate", "integer", visible_if=_set_action_visibility()), _command_field("signal_definition", "enum", options=CAN_SIGNAL_DEFINITIONS, visible_if=_set_action_visibility()), _command_field("sample_point", "number", visible_if=_set_action_visibility())), group="can", editor="serial"),
    _action_command("serial-trigger-uart", "Serial", "UART serial trigger", (_command_field("bus", "integer", minimum=1), _command_field("type", "enum", options=UART_TRIGGER_TYPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()), _command_field("data", "integer", visible_if=_set_action_visibility({"field": "type", "in": ("rx-data", "tx-data")}), required_if=_set_action_visibility({"field": "type", "in": ("rx-data", "tx-data")})), _command_field("qualifier", "enum", options=UART_TRIGGER_QUALIFIERS, visible_if=_set_action_visibility({"field": "type", "in": ("rx-data", "tx-data")}), required_if=_set_action_visibility({"field": "type", "in": ("rx-data", "tx-data")}))), group="uart", editor="serial"),
    _action_command("serial-trigger-i2c", "Serial", "I2C serial trigger", (_command_field("bus", "integer", minimum=1), _command_field("type", "enum", options=I2C_TRIGGER_TYPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()), _command_field("address", "integer", visible_if=_set_action_visibility(), required_if=_set_action_visibility({"field": "type", "in": ("address-no-ack", "read7", "write7", "write10", "read7-data2", "write7-data2", "read-eeprom")})), _command_field("data", "integer", visible_if=_set_action_visibility(), required_if=_set_action_visibility({"field": "type", "in": ("read7", "write7", "write10", "read7-data2", "write7-data2", "read-eeprom")})), _command_field("data2", "integer", visible_if=_set_action_visibility({"field": "type", "in": ("read7-data2", "write7-data2")}), required_if=_set_action_visibility({"field": "type", "in": ("read7-data2", "write7-data2")})), _command_field("qualifier", "enum", options=I2C_TRIGGER_QUALIFIERS, visible_if=_set_action_visibility({"field": "type", "equals": "read-eeprom"}), required_if=_set_action_visibility({"field": "type", "equals": "read-eeprom"}))), group="i2c", editor="serial"),
    _action_command("serial-trigger-spi", "Serial", "SPI serial trigger", (_command_field("bus", "integer", minimum=1), _command_field("type", "enum", options=SPI_TRIGGER_TYPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()), _command_field("width", "integer", minimum=1, visible_if=_set_action_visibility(), required_if=_set_action_visibility()), _command_field("data", "string", visible_if=_set_action_visibility(), required_if=_set_action_visibility())), group="spi", editor="serial"),
    _action_command("serial-trigger-can", "Serial", "CAN serial trigger", (_command_field("bus", "integer", minimum=1), _command_field("type", "enum", options=CAN_TRIGGER_TYPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()), _command_field("id", "string", visible_if=_set_action_visibility({"field": "type", "in": ("data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data")}), required_if=_set_action_visibility({"field": "type", "in": ("data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data")})), _command_field("id_mode", "enum", options=CAN_TRIGGER_ID_MODES, visible_if=_set_action_visibility({"field": "type", "in": ("data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data")}), required_if=_set_action_visibility({"field": "type", "in": ("data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data")})), _command_field("data", "string", visible_if=_set_action_visibility({"field": "type", "equals": "id-and-data"}), required_if=_set_action_visibility({"field": "type", "equals": "id-and-data"})), _command_field("data_length", "integer", minimum=0, visible_if=_set_action_visibility({"field": "type", "equals": "id-and-data"}), required_if=_set_action_visibility({"field": "type", "equals": "id-and-data"}))), group="can", editor="serial"),
    {"id": "serial-lister-query", "category": "Serial", "label": "Serial Lister state", "modes": ("live", "simulate"), "fields": (), "group": "lister", "editor": "serial"},
    _action_command("serial-lister-display", "Serial", "Serial Lister display", (_command_field("display", "enum", options=SERIAL_LISTER_DISPLAYS, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="lister", editor="serial"),
    _action_command("serial-lister-reference", "Serial", "Serial Lister reference", (_command_field("reference", "enum", options=SERIAL_LISTER_REFERENCES, visible_if=_set_action_visibility(), required_if=_set_action_visibility()),), group="lister", editor="serial"),
    {"id": "serial-lister-export", "category": "Serial", "label": "Export Serial Lister", "modes": ("live", "simulate"), "fields": (_command_field("filename", "string", required=True),), "group": "lister", "editor": "serial"},

    {
        "id": "segmented-memory", "category": "Segmented Memory", "label": "Segmented memory", "modes": ("live", "simulate"),
        "fields": ({"name": "action", "type": "enum", "options": ("query", "enable", "disable"), "default": "query"}, _command_field("segments", "integer", minimum=1, visible_if=[{"field": "action", "equals": "enable"}], required_if=[{"field": "action", "equals": "enable"}])),
    },
    {
        "id": "segmented-capture", "category": "Segmented Memory", "label": "Segmented capture", "modes": ("live", "simulate", "dry-run"),
        "fields": (_command_field("channel", "integer", minimum=1, maximum=4, default=1), _command_field("segments", "integer", minimum=1, required=True), _command_field("points", "integer", minimum=100, default=1000), _command_field("format", "enum", options=("byte", "word"), default="byte"), _command_field("timeout_ms", "integer", minimum=1, default=30000), _command_field("poll_interval_ms", "integer", minimum=1, default=100)),
    },
    {
        "id": "capture-batch", "category": "Workflow", "label": "Capture batch", "modes": ("live", "simulate"),
        "group": "capture",
        "fields": (_command_field("channels", "multi-enum", options=(1, 2, 3, 4), serialize="csv", required=True), _command_field("points", "integer", minimum=100, default=1000), _command_field("format", "enum", options=("byte", "word"), default="byte"), _command_field("count", "integer", minimum=1, default=1), _command_field("interval_seconds", "number", minimum=0, default=0)),
    },
    {
        "id": "measure-log", "category": "Workflow", "label": "Measurement log", "modes": ("live", "simulate"),
        "group": "measurement",
        "editor": "workflow",
        "fields": (_command_field("channels", "multi-enum", options=(1, 2, 3, 4), serialize="csv"), _command_field("items", "multi-enum", options=_DIRECT_MEASUREMENT_ITEMS, serialize="csv", default=("vpp", "frequency")), _command_field("pairs", "string", help="Example: 1:2, 3:4"), _command_field("pair_items", "string", options=PAIR_MEASUREMENT_ITEMS, default="phase,delay", help="Comma-separated pair measurements, for example phase,delay"), _command_field("interval_seconds", "number", minimum=0, default=1), _command_field("count", "integer", minimum=1), _command_field("duration_seconds", "number", minimum=0), _command_field("stop_on_error", "boolean", default=False)),
    },
    {
        "id": "measure-until", "category": "Workflow", "label": "Measure until", "modes": ("live", "simulate", "dry-run"),
        "group": "measurement",
        "fields": (_command_field("channel", "integer", minimum=1, maximum=4, default=1), _command_field("item", "enum", options=_DIRECT_MEASUREMENT_ITEMS, default="vpp"), _command_field("operator", "enum", options=("gt", "gte", "lt", "lte"), required=True), _command_field("threshold", "number", required=True), _command_field("timeout_seconds", "number", exclusive_minimum=0, required=True), _command_field("interval_seconds", "number", minimum=0, default=1)),
    },
    {
        "id": "triggered-measure-loop", "category": "Workflow", "label": "Triggered measurement loop", "modes": ("live", "simulate", "dry-run"),
        "group": "triggered",
        "editor": "workflow",
        "fields": (_command_field("channels", "multi-enum", options=(1, 2, 3, 4), serialize="csv"), _command_field("items", "multi-enum", options=_DIRECT_MEASUREMENT_ITEMS, serialize="csv", default=("vpp", "frequency")), _command_field("pairs", "string", help="Example: 1:2, 3:4"), _command_field("pair_items", "string", options=PAIR_MEASUREMENT_ITEMS, default="phase,delay", help="Comma-separated pair measurements, for example phase,delay"), _command_field("count", "integer", minimum=1, required=True), _command_field("trigger_timeout_seconds", "number", exclusive_minimum=0, required=True), _command_field("interval_seconds", "number", minimum=0, default=0)),
    },
    {
        "id": "triggered-capture-series", "category": "Workflow", "label": "Triggered capture series", "modes": ("live", "simulate", "dry-run"),
        "group": "triggered",
        "fields": (_command_field("channels", "multi-enum", options=(1, 2, 3, 4), serialize="csv", required=True), _command_field("count", "integer", minimum=1, required=True), _command_field("trigger_timeout_seconds", "number", exclusive_minimum=0, required=True), _command_field("points", "integer", minimum=100, default=1000), _command_field("format", "enum", options=("byte", "word"), default="byte"), _command_field("interval_seconds", "number", minimum=0, default=0)),
    },
)

COMMANDS = COMMANDS + TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMANDS
_TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMAND_IDS = frozenset(entry["id"] for entry in TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMANDS)

PC_OUTPUT_COMMAND_IDS = frozenset(
    {
        "screenshot",
        "capture",
        "serial-lister-export",
        "segmented-capture",
        "capture-batch",
        "measure-log",
        "measure-until",
        "triggered-measure-loop",
        "triggered-capture-series",
    }
)

_COMMAND_BY_ID = {entry["id"]: entry for entry in COMMANDS}
_COMMAND_FIELDS = {
    command_id: frozenset(field["name"] for field in entry["fields"])
    for command_id, entry in _COMMAND_BY_ID.items()
}

_SETTING_QUERY_FIELDS = {
    **{
        command_id: ("channel",)
        for command_id in (
            "channel-display",
            "channel-scale",
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
        )
    },
    "reference-display": ("slot",),
    "reference-label": ("slot",),
    "fft": ("function",),
    "math-display": ("function",),
    "math-vertical": ("function",),
    "math-operator": ("function",),
    "trigger-edge-level": ("source_channel",),
    **{
        command_id: ("bus",)
        for command_id in (
            "serial-search-uart",
            "serial-search-i2c",
            "serial-search-spi",
            "serial-search-can",
            "serial-mode",
            "serial-display",
            "serial-uart",
            "serial-i2c",
            "serial-spi",
            "serial-can",
            "serial-trigger-uart",
            "serial-trigger-i2c",
            "serial-trigger-spi",
            "serial-trigger-can",
        )
    },
}

_SETTING_READBACK_FIELDS = {
    "measure-source": {"source_channel": "source1_channel"},
    "math-vertical": {"range_value": "range"},
    "dvm-auto-range": {"enabled": "auto_range_enabled"},
    "trigger-edge": {"level": "level_volts"},
    "trigger-edge-level": {"level": "level_volts"},
    "trigger-edge-external-level": {"level": "level_volts"},
    "trigger-pulse-width": {
        "time_seconds": {
            "selector_field": "qualifier",
            "fields": {
                "greater-than": "greater_than_seconds",
                "less-than": "less_than_seconds",
            },
        },
        "min_time_seconds": "range_min_seconds",
        "max_time_seconds": "range_max_seconds",
        "level": "level_volts",
    },
    "trigger-runt": {
        "low_level": "low_level_volts",
        "high_level": "high_level_volts",
    },
    "trigger-transition": {
        "low_level": "low_level_volts",
        "high_level": "high_level_volts",
    },
    "trigger-edge-burst": {"level": "level_volts"},
    "trigger-tv": {"mode": "tv_mode"},
}

_ONE_WAY_ACTIONS = {
    "display-vectors": "enable",
    "measure-show": "show",
}

_READ_COMMANDS = frozenset(
    {
        "identify",
        "channel-summary",
        "measure-results",
        "reference-query",
        "save-waveform-length-max",
        "check-error",
        "system-status-byte",
        "system-operation-status",
        "system-opc",
        "system-standard-event",
        "system-options",
        "dvm-current",
        "dvm-query",
        "external-trigger-settings",
        "search-count",
        "serial-query",
        "serial-lister-query",
    }
)


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


def command_catalog() -> list[dict[str, Any]]:
    return [
        _jsonable(_command_catalog_entry(entry))
        for entry in COMMANDS
        if not entry.get("hidden")
    ]


def model_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": model.model_id,
            "label": model.display_name,
            "series": model.series,
        }
        for model in PHYSICAL_MODEL_REGISTRY
    ]


def _command_catalog_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    catalog_entry = dict(entry)
    catalog_entry["pc_output"] = entry["id"] in PC_OUTPUT_COMMAND_IDS
    presentation = _command_presentation(entry)
    presentation["models"] = {
        model.model_id: _model_command_presentation(entry, model.model_id)
        for model in PHYSICAL_MODEL_REGISTRY
    }
    catalog_entry["presentation"] = presentation
    return catalog_entry


def _command_presentation(entry: Mapping[str, Any]) -> dict[str, Any]:
    action_field = next(
        (field for field in entry["fields"] if field["name"] == "action"),
        None,
    )
    action_options = set(action_field.get("options", ())) if action_field else set()
    if entry["id"] in _ONE_WAY_ACTIONS:
        return {
            "kind": "one-way",
            "action": _ONE_WAY_ACTIONS[entry["id"]],
            "action_field": "action",
            "apply_value": "set",
        }
    if action_options == {"query", "set"}:
        presentation = {
            "kind": "setting",
            "action": "apply",
            "action_field": "action",
            "query_value": "query",
            "apply_value": "set",
            "query_fields": _SETTING_QUERY_FIELDS.get(entry["id"], ()),
        }
        readback_fields = _SETTING_READBACK_FIELDS.get(entry["id"])
        if readback_fields:
            presentation["readback_fields"] = readback_fields
        return presentation
    if action_options == {"query", "enable", "disable"}:
        return {
            "kind": "setting",
            "action": "apply",
            "action_field": "action",
            "action_choices": ("enable", "disable"),
            "query_value": "query",
            "query_fields": (),
        }
    command_id = entry["id"]
    if command_id in _READ_COMMANDS:
        action = "read"
    elif "clear" in command_id:
        action = "clear"
    elif command_id in {"screenshot", "capture", "segmented-capture", "capture-batch"}:
        action = "capture"
    elif command_id in {"save-image", "save-waveform", "reference-save"}:
        action = "save"
    elif command_id == "serial-lister-export":
        action = "export"
    else:
        action = "run"
    return {"kind": "command", "action": action}


def _model_command_presentation(
    entry: Mapping[str, Any], model_id: str
) -> dict[str, Any]:
    capabilities = capabilities_for_model_id(model_id)
    supported = _command_supported_by_capabilities(entry, capabilities)
    fields: dict[str, dict[str, Any]] = {}
    analog_fields = {
        "channel",
        "source_channel",
        "source2_channel",
        "reference_channel",
        "arm_channel",
        "trigger_channel",
        "clock_channel",
        "data_channel",
    }
    for field in entry["fields"]:
        name = field["name"]
        override: dict[str, Any] = {}
        if field.get("type") == "integer" and name in analog_fields:
            override["maximum"] = capabilities.analog_channels
        if field.get("type") == "multi-enum" and name == "channels":
            override["options"] = tuple(range(1, capabilities.analog_channels + 1))
        if field.get("type") == "integer" and name == "function":
            override["maximum"] = capabilities.math_function_count
        if field.get("type") == "integer" and name == "bus":
            override["maximum"] = capabilities.serial_bus_count
        if name == "slot" and capabilities.reference_waveforms:
            override["maximum"] = capabilities.reference_waveforms
        if entry["id"] == "channel-impedance" and name == "impedance":
            override["options"] = (
                ("one_meg", "fifty")
                if capabilities.supports_50_ohm_impedance
                else ("one_meg",)
            )
        if entry["id"] == "serial-mode" and name == "mode":
            override["options"] = tuple(
                option for option in field.get("options", ())
                if option in capabilities.serial_modes
            )
        if entry["id"] == "search-mode" and name == "mode":
            override["options"] = tuple(
                option for option in field.get("options", ())
                if option in capabilities.search_modes
            )
        if name == "segments" and entry["id"] in {"segmented-memory", "segmented-capture"}:
            override["maximum"] = capabilities.segmented_max_segments
        if entry["id"] == "measure" and name == "item" and not capabilities.supports_delay_measurement:
            override["options"] = tuple(
                option for option in field.get("options", ()) if option != "delay"
            )
        if name == "pair_items" and not capabilities.supports_delay_measurement:
            override["options"] = tuple(
                option for option in field.get("options", ()) if option != "delay"
            )
        if name in ("item", "items") and not capabilities.supports_area_measurement:
            base_options = override.get("options", field.get("options", ()))
            if "area" in base_options:
                override["options"] = tuple(
                    option for option in base_options if option != "area"
                )
        if override:
            fields[name] = override
    return {"supported": supported, "fields": fields}


def _command_supported_by_capabilities(entry: Mapping[str, Any], capabilities: Any) -> bool:
    command_id = entry["id"]
    category = entry["category"]
    if command_id == "measure-results":
        return capabilities.supports_measure_results_dump
    if category == "Measurement":
        return capabilities.supports_measurements
    if command_id == "channel-label":
        return capabilities.supports_channel_label
    if command_id == "display-label":
        return capabilities.supports_display_label
    if category == "Search":
        if command_id == "search-event":
            return capabilities.supports_search_event_navigation
        return capabilities.supports_search_basic
    if category == "Serial":
        return capabilities.supports_serial_decode and capabilities.serial_bus_count > 0
    if category == "Segmented Memory":
        return capabilities.supports_segmented_memory
    if category == "FFT / MATH":
        if command_id == "math-composite-source":
            return capabilities.supports_math_goft
        return capabilities.math_function_count > 0
    return True
