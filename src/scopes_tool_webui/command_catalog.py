"""WebUI command catalog: definitions, metadata, and catalog API payload builders."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from scopes_tool_core import capabilities_for_model_id
from scopes_tool_core.capabilities import operation_supported
from scopes_tool_core.demo import DEMO_FUNCTIONS
from scopes_tool_core.fft import FFT_WINDOWS
from scopes_tool_core.identity import PHYSICAL_MODEL_REGISTRY
from scopes_tool_core.math import (
    MATH_FILTER_OPERATIONS,
    MATH_SOURCES,
    MATH_TRANSFORM_SOURCES,
    MATH_VISUALIZATION_OPERATIONS,
)
from scopes_tool_core.wgen import wgen_frequency_limits

from ._catalog_controls import CONTROLS_COMMANDS
from ._catalog_extended import TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMANDS
from ._catalog_features import FEATURES_COMMANDS
from ._catalog_measurement_export import MEASUREMENT_EXPORT_COMMANDS


_ANALOG_CHANNEL_FIELDS = frozenset(
    {
        "channel",
        "source_channel",
        "source2_channel",
        "reference_channel",
        "arm_channel",
        "trigger_channel",
        "clock_channel",
        "data_channel",
    }
)
_ADVANCED_FFT_FIELDS = frozenset(
    {
        "fft_operation",
        "start_hz",
        "stop_hz",
        "gate",
        "phase_reference",
        "detection_type",
        "detection_points",
    }
)
_SERIAL_SOURCE_FIELDS = {
    "serial-uart": frozenset({"rx_source", "tx_source"}),
    "serial-i2c": frozenset({"clock_source", "data_source"}),
    "serial-spi": frozenset(
        {"clock_source", "mosi_source", "miso_source", "frame_source"}
    ),
    "serial-can": frozenset({"source"}),
}
_CAN_SAMPLE_POINT_OPTIONS = (60, 62.5, 68, 70, 75, 80, 87.5)

COMMANDS = (
    CONTROLS_COMMANDS
    + MEASUREMENT_EXPORT_COMMANDS
    + FEATURES_COMMANDS
    + TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMANDS
)

_TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMAND_IDS = frozenset(entry["id"] for entry in TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMANDS)

# Ensure analog channel selector fields are select-capable even without an active model.
for _entry in COMMANDS:
    for _field in _entry["fields"]:
        if _field.get("type") == "integer" and _field.get("name") in _ANALOG_CHANNEL_FIELDS:
            _field.setdefault("options", (1, 2, 3, 4))
            _field.setdefault("option_label", "channel")

PC_OUTPUT_COMMAND_IDS = frozenset(
    {
        "screenshot",
        "capture",
        "serial-lister-export",
        "segmented-capture",
        "capture-batch",
        "capture-until",
        "capture-monitor",
        "measure-log",
        "measure-until",
        "triggered-measure-loop",
        "triggered-capture-series",
        "sequence",
        "smoke",
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
    "math-transform": ("function",),
    "math-filter": ("function",),
    "math-visualization": ("function",),
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
    "fft": {
        "fft_operation": "operation_canonical",
        "units": "units_canonical",
        "window": "window_canonical",
    },
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
}

_READ_COMMANDS = frozenset(
    {
        "doctor",
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
        "cursor-query",
        "annotation-query",
        "wgen-query",
        "demo-query",
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


def command_catalog(*, include_hidden: bool = False) -> list[dict[str, Any]]:
    catalog = [
        _jsonable(_command_catalog_entry(entry))
        for entry in COMMANDS
        if include_hidden or not entry.get("hidden")
    ]
    catalog.extend(
        _jsonable(_command_catalog_entry(entry))
        for entry in (
            {
                "id": "front-panel-measurements",
                "category": "Measurement",
                "label": "Front Panel Measurements",
                "editor": "measurement",
                "presentation_only": True,
                "modes": ("live", "simulate"),
                "fields": (),
            },
            {
                "id": "acquisition-control",
                "category": "Acquisition",
                "label": "Acquisition Control",
                "editor": "acquisition",
                "presentation_only": True,
                "modes": ("live", "simulate"),
                "fields": (),
            },
            {
                "id": "reference-waveform",
                "category": "Reference",
                "label": "Reference waveform",
                "editor": "reference",
                "presentation_only": True,
                "modes": ("live", "simulate"),
                "fields": (),
            },
            {
                "id": "reference-labels",
                "category": "Reference",
                "label": "Reference labels",
                "editor": "reference-labels",
                "presentation_only": True,
                "modes": ("live", "simulate"),
                "fields": (),
            },
            {
                "id": "system-information",
                "category": "System",
                "label": "System Information",
                "presentation_only": True,
                "modes": ("live", "simulate"),
                "fields": (),
            },
            {
                "id": "diagnostics",
                "category": "System",
                "label": "Diagnostics",
                "editor": "diagnostics",
                "presentation_only": True,
                "modes": ("live", "simulate"),
                "fields": (),
            },
            {
                "id": "channel-scale-range",
                "category": "Channel",
                "label": "Vertical Scale / Range",
                "editor": "channel-scale-range",
                "presentation_only": True,
                "modes": ("live", "simulate"),
                "fields": (),
                "group": "channel-basic",
            },
            {
                "id": "external-trigger-range-level",
                "category": "Trigger",
                "label": "External Trigger Range / Level",
                "editor": "external-trigger",
                "presentation_only": True,
                "modes": ("live", "simulate"),
                "fields": (),
                "group": "external",
            },
            {
                "id": "serial-decode",
                "category": "Serial",
                "label": "Serial Decode",
                "editor": "serial-decode",
                "presentation_only": True,
                "modes": ("live", "simulate"),
                "fields": (),
            },
            {
                "id": "serial-trigger",
                "category": "Serial",
                "label": "Serial Trigger",
                "editor": "serial-trigger",
                "presentation_only": True,
                "modes": ("live", "simulate"),
                "fields": (),
            },
            {
                "id": "serial-lister",
                "category": "Serial",
                "label": "Serial Lister",
                "editor": "serial-lister",
                "presentation_only": True,
                "modes": ("live", "simulate"),
                "fields": (),
            },
        )
    )
    for presentation_id, first_underlying_id in (
        ("acquisition-control", "run"),
        ("reference-waveform", "reference-save"),
        ("channel-scale-range", "channel-scale"),
        ("external-trigger-range-level", "external-trigger-range"),
        ("serial-decode", "serial-query"),
        ("serial-trigger", "serial-query"),
        ("serial-lister", "serial-query"),
    ):
        presentation = next(entry for entry in catalog if entry["id"] == presentation_id)
        catalog.remove(presentation)
        insert_at = next(
            index for index, entry in enumerate(catalog)
            if entry["id"] == first_underlying_id
        )
        catalog.insert(insert_at, presentation)
    return catalog


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
    if entry["id"] == "segmented-memory" and action_options == {
        "query", "enable", "disable", "select"
    }:
        return {
            "kind": "setting",
            "action": "apply",
            "action_field": "action",
            "action_choices": ("enable", "disable", "select"),
            "query_value": "query",
            "query_fields": (),
        }
    command_id = entry["id"]
    if command_id in _READ_COMMANDS:
        action = "read"
    elif "clear" in command_id:
        action = "clear"
    elif command_id in {
        "screenshot",
        "capture",
        "segmented-capture",
        "capture-batch",
        "capture-until",
        "capture-monitor",
    }:
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
    for field in entry["fields"]:
        name = field["name"]
        override: dict[str, Any] = {}
        if field.get("type") == "integer" and name in _ANALOG_CHANNEL_FIELDS:
            override["maximum"] = capabilities.analog_channels
            override["options"] = tuple(range(1, capabilities.analog_channels + 1))
        if field.get("type") == "multi-enum" and name == "channels":
            override["options"] = tuple(range(1, capabilities.analog_channels + 1))
        if entry["id"] == "save-waveform" and name == "source_channel":
            override["hidden"] = not capabilities.save_waveform_requires_source
            override["required"] = capabilities.save_waveform_requires_source
        if entry["id"] == "screenshot" and name == "background" and capabilities.screenshot_backgrounds is not None:
            override["options"] = capabilities.screenshot_backgrounds
        if entry["id"] in {"capture", "capture-batch", "capture-until", "capture-monitor", "triggered-capture-series"}:
            if name == "points":
                override["options"] = tuple(value for value in field["options"]
                    if value <= capabilities.safe_max_waveform_points)
            elif name == "format" and not capabilities.supports_word_format:
                override["options"] = ("byte",)
        if entry["id"] == "acquisition" and name == "type" and capabilities.acquisition_modes is not None:
            override["options"] = capabilities.acquisition_modes
        if entry["id"] == "acquisition" and name == "count" and capabilities.average_counts is not None:
            override["options"] = capabilities.average_counts
            override["minimum"] = min(capabilities.average_counts)
            override["maximum"] = max(capabilities.average_counts)
        if entry["id"] == "autoscale" and not capabilities.autoscale_supports_optional_controls:
            override["disabled"] = True
        if entry["id"] in {"setup-save", "setup-recall"}:
            if name == "target" and not capabilities.supports_setup_file_target:
                override["options"] = ("slot",)
            elif name == "slot" and capabilities.setup_slots is not None:
                override["options"] = capabilities.setup_slots
                override["minimum"] = min(capabilities.setup_slots)
                override["maximum"] = max(capabilities.setup_slots)
            elif name == "file" and not capabilities.supports_setup_file_target:
                override["disabled"] = True
        subset = {
            ("channel-units", "channel"): capabilities.channel_units_channels,
            ("measure-install", "item"): capabilities.measurement_install_items,
            ("measure", "item"): capabilities.measurement_items,
            ("trigger-pulse-width", "qualifier"): capabilities.pulse_width_qualifiers,
            ("display-persistence", "seconds"): capabilities.display_persistence_seconds,
            ("save-image-format", "format"): capabilities.save_image_formats,
            ("save-waveform-format", "format"): capabilities.save_waveform_formats,
            ("trigger-runt", "channel"): capabilities.runt_channels,
            ("trigger-runt", "polarity"): capabilities.runt_polarities,
            ("trigger-runt", "qualifier"): capabilities.runt_qualifiers,
            ("trigger-tv", "standard"): capabilities.tv_standards,
            ("trigger-tv", "mode"): capabilities.tv_modes,
        }.get((entry["id"], name))
        if subset is not None:
            override["options"] = subset
            if field.get("type") in {"integer", "number"}:
                override["minimum"], override["maximum"] = min(subset), max(subset)
        if entry["id"] == "cursor" and name == "action":
            override["options"] = tuple(action for action in field.get("options", ())
                if operation_supported(capabilities, "cursor-" + action))
        if entry["id"] in {"cursor", "cursor-set"} and name == "function":
            # Only models that declare selectable cursor functions expose the choice.
            override["options"] = capabilities.cursor_functions
            override["hidden"] = not capabilities.cursor_functions
        if entry["id"] == "trigger-mode" and name == "mode" and capabilities.trigger_modes is not None:
            override["options"] = capabilities.trigger_modes
        if entry["id"] == "trigger-sweep" and name == "mode" and capabilities.trigger_sweep_modes is not None:
            override["options"] = capabilities.trigger_sweep_modes
        if entry["id"] == "trigger-edge-source" and name == "source" and capabilities.trigger_edge_sources is not None:
            override["options"] = capabilities.trigger_edge_sources
        if entry["id"] in {"trigger-edge", "trigger-edge-slope"} and name == "slope" and capabilities.trigger_edge_slopes is not None:
            override["options"] = capabilities.trigger_edge_slopes
        if entry["id"] == "trigger-edge-coupling" and name == "coupling" and capabilities.trigger_edge_couplings is not None:
            override["options"] = capabilities.trigger_edge_couplings
        if entry["id"] == "trigger-holdoff" and name == "seconds":
            if capabilities.trigger_holdoff_min_seconds is not None:
                override["minimum"] = capabilities.trigger_holdoff_min_seconds
            if capabilities.trigger_holdoff_max_seconds is not None:
                override["maximum"] = capabilities.trigger_holdoff_max_seconds
        if field.get("type") == "integer" and name == "function":
            override["maximum"] = capabilities.math_function_count
            if entry["category"] == "FFT / MATH":
                override["options"] = tuple(range(1, capabilities.math_function_count + 1))
        if field.get("type") == "integer" and name == "bus":
            override["maximum"] = capabilities.serial_bus_count
        if entry["category"] == "Reference" and name == "slot" and capabilities.reference_waveforms:
            override["maximum"] = capabilities.reference_waveforms
            override["options"] = tuple(range(1, capabilities.reference_waveforms + 1))
        if entry["id"] in {
            "annotation",
            "annotation-query",
            "annotation-set",
            "annotation-on",
            "annotation-off",
            "annotation-clear",
        } and name == "slot" and capabilities.annotation_slots:
            override["maximum"] = capabilities.annotation_slots
            override["options"] = tuple(range(1, capabilities.annotation_slots + 1))
            if capabilities.annotation_slots <= 1:
                override["hidden"] = True
        if entry["id"] in {
            "annotation",
            "annotation-query",
            "annotation-set",
            "annotation-on",
            "annotation-off",
            "annotation-clear",
        } and name in ("x", "y") and not capabilities.supports_annotation_position:
            override["disabled"] = True
        if name in _SERIAL_SOURCE_FIELDS.get(entry["id"], ()):
            max_channel = capabilities.analog_channels
            disabled_options = tuple(f"channel{i}" for i in range(max_channel + 1, 5))
            override["disabled_options"] = disabled_options
        if entry["id"] == "serial-can" and name == "sample_point":
            if capabilities.series != "4000X":
                override["options"] = _CAN_SAMPLE_POINT_OPTIONS
        if entry["id"] == "serial-lister-display" and name == "display":
            disabled_options = (
                ("bus2",) if capabilities.serial_bus_count < 2 else ()
            )
            override["disabled_options"] = disabled_options
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
        if entry["id"] == "measure" and name == "item" and capabilities.measurement_items is None and not capabilities.supports_delay_measurement:
            override["options"] = tuple(
                option for option in field.get("options", ()) if option != "delay"
            )
        if entry["id"] == "measure-window" and name == "window":
            override["options"] = tuple(
                option for option in field.get("options", ())
                if option != "gate" or capabilities.series == "4000X"
            )
        if entry["id"] == "fft" and name == "window":
            override["options"] = tuple(
                option for option in FFT_WINDOWS
                if option != "bartlett" or capabilities.series == "4000X"
            )
        if entry["id"] == "measure-show" and name == "enabled" and capabilities.series != "4000X":
            override["hidden"] = True
        if entry["id"] == "fft" and name in _ADVANCED_FFT_FIELDS and not capabilities.supports_advanced_fft:
            override["hidden"] = True
        if entry["id"] == "fft" and name == "units" and capabilities.supports_advanced_fft:
            override["visible_if"] = [{"field": "fft_operation", "equals": "fft"}]
        if entry["id"] in {"math-transform", "math-filter", "math-visualization"} and name == "source":
            override["options"] = tuple(
                option for option in MATH_TRANSFORM_SOURCES
                if option in MATH_SOURCES
                or (option == "composite" and capabilities.supports_math_goft)
                or (option.startswith("math") and capabilities.supports_math_cascade)
            )
        if entry["id"] == "math-filter" and name == "operation":
            override["options"] = tuple(
                option for option in MATH_FILTER_OPERATIONS
                if option in capabilities.math_filter_operations
            )
        if entry["id"] == "math-visualization" and name == "operation":
            override["options"] = tuple(
                option for option in MATH_VISUALIZATION_OPERATIONS
                if option in capabilities.math_visualization_operations
            )
        if entry["id"] == "math-visualization":
            if capabilities.series == "4000X":
                non_trend_operations = tuple(
                    option for option in MATH_VISUALIZATION_OPERATIONS
                    if option in capabilities.math_visualization_operations
                    and option != "trend"
                )
                if name == "source":
                    conditions = [
                        {"field": "action", "equals": "set"},
                        {"field": "operation", "in": non_trend_operations},
                    ]
                    override["visible_if"] = conditions
                    override["required_if"] = conditions
                elif name in {"source2", "measurement"}:
                    override["hidden"] = True
                elif name == "measurement_slot":
                    conditions = [
                        {"field": "action", "equals": "set"},
                        {"field": "operation", "equals": "trend"},
                    ]
                    override["visible_if"] = conditions
                    override["required_if"] = conditions
            elif name == "measurement_slot":
                override["hidden"] = True
        if entry["id"] == "demo-function" and name == "function":
            override["options"] = tuple(
                value for value in DEMO_FUNCTIONS if value in capabilities.demo_functions
            )
        if (entry["id"] == "wgen-frequency" and name == "frequency_hz"
                and capabilities.supports_wgen):
            # Presentation-only range hint projected from Core-owned limits.
            # Deliberately not named minimum/maximum so backend and frontend
            # constraint enforcement stay untouched.
            override["frequency_limits"] = wgen_frequency_limits(capabilities.series)
        if entry["id"] == "external-trigger-range" and name == "range_volts":
            # Presentation-only quick-fill hint projected from Core-owned limits.
            # Deliberately not named minimum/maximum so backend and frontend
            # constraint enforcement stay untouched.
            override["quick_fill_probe_1x_values"] = (
                capabilities.external_trigger_range_probe_1x_values
            )
        if name == "pair_items" and not capabilities.supports_delay_measurement:
            override["options"] = tuple(
                option for option in field.get("options", ()) if option != "delay"
            )
        if name in ("item", "items") and not capabilities.supports_area_measurement and not ((entry["id"] == "measure-install" and capabilities.measurement_install_items is not None) or (entry["id"] == "measure" and capabilities.measurement_items is not None)):
            base_options = override.get("options", field.get("options", ()))
            if "area" in base_options:
                override["options"] = tuple(
                    option for option in base_options if option != "area"
                )
        if entry["id"] in {"measure-sweep", "measure-log", "measure-until", "triggered-measure-loop"} and capabilities.measurement_items is not None:
            if name in {"item", "items"}:
                override["options"] = capabilities.measurement_items
            if name in {"pairs", "pair_items"}:
                override["hidden"] = True
        if override:
            fields[name] = override
    result = {"supported": supported, "fields": fields}
    if entry["id"] in {"cursor", "cursor-set"}:
        result["cursor_source_selection"] = capabilities.cursor_source_selection
    if entry["id"] == "timebase-position":
        result["timebase_position"] = {
            "display_divisions": capabilities.horizontal_display_divisions,
            "reference_mode": capabilities.timebase_reference_mode,
        }
    if entry["id"] == "sequence" and capabilities.supported_sequence_actions is not None:
        metadata = entry["sequence"]
        parameters = {}
        for action in capabilities.supported_sequence_actions:
            projected = []
            for field in metadata["parameters"][action]:
                value = dict(field)
                name = value["name"]
                if name in {"channel", "source_channel", "reference_channel"}:
                    value.update(maximum=capabilities.analog_channels, options=tuple(range(1, capabilities.analog_channels + 1)))
                elif name == "channels":
                    value["options"] = tuple(range(1, capabilities.analog_channels + 1))
                elif name == "item" and capabilities.measurement_items is not None:
                    value["options"] = capabilities.measurement_items
                elif name == "points":
                    value["options"] = tuple(v for v in value["options"] if v <= capabilities.safe_max_waveform_points)
                elif name == "waveform_format" and not capabilities.supports_word_format:
                    value["options"] = ("byte",)
                elif name == "background" and capabilities.screenshot_backgrounds is not None:
                    value["options"] = capabilities.screenshot_backgrounds
                projected.append(value)
            parameters[action] = projected
        result["sequence"] = {**metadata, "actions": capabilities.supported_sequence_actions, "parameters": parameters}
    return result


_PRESENTATION_OPERATIONS = {
    "acquisition-control": ("run", "single", "single-wait", "stop-acquisition", "force-trigger"),
    "channel-scale-range": ("channel-scale", "channel-range"),
    "reference-waveform": ("reference-query", "reference-save", "reference-clear"),
    "reference-labels": ("reference-query", "reference-label", "display-label"),
    "front-panel-measurements": ("measure", "measure-results", "measure-install", "measure-clear"),
    "system-information": ("system-information-snapshot",),
    "diagnostics": ("doctor", "smoke"),
    "external-trigger-range-level": ("external-trigger-range", "trigger-edge-external-level"),
    "serial-decode": ("serial-mode", "serial-display", "serial-uart", "serial-i2c", "serial-spi", "serial-can"),
    "serial-trigger": ("serial-mode", "serial-trigger-uart", "serial-trigger-i2c", "serial-trigger-spi", "serial-trigger-can"),
    "serial-lister": ("serial-lister-query", "serial-lister-display", "serial-lister-reference", "serial-lister-export"),
}


def _command_supported_by_capabilities(entry: Mapping[str, Any], capabilities: Any) -> bool:
    underlying = _PRESENTATION_OPERATIONS.get(entry["id"])
    if entry.get("presentation_only") and underlying is not None:
        return any(operation_supported(capabilities, operation) for operation in underlying)
    if not operation_supported(capabilities, entry["id"]):
        return False
    command_id = entry["id"]
    category = entry["category"]
    if command_id == "measure-results":
        return capabilities.supports_measure_results_dump
    if command_id == "measurement-statistics":
        return capabilities.supports_measure_statistics
    if command_id == "screenshot":
        return capabilities.supports_any_screenshot
    if command_id in {"measure-install", "measure-clear"} and capabilities.measurement_install_items is not None:
        return True
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
    if category == "Annotation":
        return capabilities.supports_annotation
    if category == "WGEN":
        return capabilities.supports_wgen
    if category == "DEMO":
        return capabilities.supports_demo
    if category == "FFT / MATH":
        if command_id == "math-composite-source":
            return capabilities.supports_math_goft
        return capabilities.math_function_count > 0
    return True
