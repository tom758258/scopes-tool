"""WebUI command catalog metadata: trigger, search, serial, segmented memory,
and workflow commands, plus the field helpers owned by that block."""

from __future__ import annotations

from typing import Any

from scopes_tool_core import (
    SEQUENCE_ACTIONS,
    SEQUENCE_MAX_ARTIFACT_STEPS,
    SEQUENCE_MAX_LOOPS,
    SEQUENCE_MAX_STEPS,
    SEQUENCE_MAX_TOTAL_STEP_EXECUTIONS,
)
from scopes_tool_core.cleanup import CLEANUP_PROFILES
from scopes_tool_core.measurements import (
    INSTALLABLE_MEASUREMENT_ITEMS,
    PAIR_MEASUREMENT_ITEMS,
    SUPPORTED_MEASUREMENT_ITEMS,
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
    I2C_TRIGGER_ADDRESS_MAXIMUM_BY_TYPE,
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
from scopes_tool_core.trigger import TRIGGER_MODES
from scopes_tool_core.waveform import SUPPORTED_WAVEFORM_POINTS


_DIRECT_MEASUREMENT_ITEMS = INSTALLABLE_MEASUREMENT_ITEMS
_SERIAL_SOURCE_OPTIONS = ("channel1", "channel2", "channel3", "channel4", "external")
_TRIGGER_SLOPES = ("positive", "negative", "either", "alternate")
_BINARY_SLOPES = ("positive", "negative")
_TV_LINE_MODES = ("line-field1", "line-field2", "line-alternate")


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
    browser_hidden: bool = False,
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
    if browser_hidden:
        entry["browser_hidden"] = True
    return entry


_TRIGGER_SLOPES = ("positive", "negative", "either", "alternate")
_BINARY_SLOPES = ("positive", "negative")
_TV_LINE_MODES = ("line-field1", "line-field2", "line-alternate")


TRIGGER_SEARCH_SERIAL_SEGMENTED_WORKFLOW_COMMANDS = (
    _action_command(
        "trigger-edge", "Trigger", "Edge trigger", (
            _command_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge.source_channel"),
            _command_field("level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge.level"),
            _command_field("slope", "enum", options=_TRIGGER_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge.slope"),
        ),
        group="edge",
        editor="trigger",
    ),
    _action_command(
        "trigger-edge-source", "Trigger", "Edge trigger source", (
            _command_field("source", "enum", options=("analog-channel", "external", "line"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge-source.source"),
            _command_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility({"field": "source", "equals": "analog-channel"}), required_if=_set_action_visibility({"field": "source", "equals": "analog-channel"}), help_key="trigger-edge.source_channel"),
        ),
        group="edge",
        editor="trigger",
    ),
    _action_command("trigger-edge-slope", "Trigger", "Edge trigger slope", (_command_field("slope", "enum", options=_TRIGGER_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge.slope"),), group="edge", editor="trigger"),
    _action_command(
        "trigger-edge-level", "Trigger", "Edge trigger level", (
            _command_field("source_channel", "integer", minimum=1, maximum=4, help_key="trigger-edge-level.source_channel"),
            _command_field("level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge.level"),
        ),
        group="edge",
        editor="trigger",
    ),
    {
        **_action_command("external-trigger-range", "Trigger", "External trigger range", (_command_field("range_volts", "number", exclusive_minimum=0, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="external-trigger-range.range_volts"),), group="external", editor="external-trigger"),
        "browser_hidden": True,
    },
    {
        **_action_command("trigger-edge-external-level", "Trigger", "External trigger level", (_command_field("level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge-external-level.level"),), group="external", editor="external-trigger"),
        "browser_hidden": True,
    },
    _action_command("external-trigger-probe", "Trigger", "External trigger probe", (_command_field("attenuation", "number", exclusive_minimum=0, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="external-trigger-probe.attenuation"),), group="external", editor="trigger"),
    _action_command("external-trigger-units", "Trigger", "External trigger units", (_command_field("units", "enum", options=("volts", "amps"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="external-trigger-units.units"),), group="external", editor="trigger"),
    {"id": "external-trigger-settings", "category": "Trigger", "label": "External trigger settings", "modes": ("live", "simulate"), "fields": (), "group": "external", "editor": "trigger"},
    _action_command("trigger-edge-coupling", "Trigger", "Edge trigger coupling", (_command_field("coupling", "enum", options=("ac", "dc", "lf-reject"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge-coupling.coupling"),), group="edge", editor="trigger"),
    _action_command("trigger-edge-reject", "Trigger", "Edge trigger reject", (_command_field("reject", "enum", options=("off", "lf-reject", "hf-reject"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge-reject.reject"),), group="edge", editor="trigger"),
    _action_command(
        "trigger-pulse-width", "Trigger", "Glitch / pulse-width trigger", (
            _command_field("channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-pulse-width.channel"),
            _command_field("polarity", "enum", options=("positive", "negative"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-pulse-width.polarity"),
            _command_field("qualifier", "enum", options=("greater-than", "less-than", "range"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-pulse-width.qualifier"),
            _command_field("time_seconds", "number", exclusive_minimum=0, visible_if=_set_action_visibility({"field": "qualifier", "in": ("greater-than", "less-than")}), required_if=_set_action_visibility({"field": "qualifier", "in": ("greater-than", "less-than")}), help_key="trigger-pulse-width.time_seconds"),
            _command_field("min_time_seconds", "number", exclusive_minimum=0, visible_if=_set_action_visibility({"field": "qualifier", "equals": "range"}), required_if=_set_action_visibility({"field": "qualifier", "equals": "range"}), help_key="trigger-pulse-width.min_time_seconds"),
            _command_field("max_time_seconds", "number", exclusive_minimum=0, visible_if=_set_action_visibility({"field": "qualifier", "equals": "range"}), required_if=_set_action_visibility({"field": "qualifier", "equals": "range"}), help_key="trigger-pulse-width.max_time_seconds"),
            _command_field("level", "number", visible_if=_set_action_visibility(), help_key="trigger-pulse-width.level"),
        ),
        group="pulse-width",
        editor="trigger",
    ),
    _action_command(
        "trigger-runt", "Trigger", "Runt trigger", (
            _command_field("channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-runt.channel"),
            _command_field("polarity", "enum", options=("positive", "negative", "either"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-runt.polarity"),
            _command_field("qualifier", "enum", options=("greater-than", "less-than", "none"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-runt.qualifier"),
            _command_field("low_level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-runt.low_level"),
            _command_field("high_level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-runt.high_level"),
            _command_field("time_seconds", "number", exclusive_minimum=0, visible_if=_set_action_visibility({"field": "qualifier", "in": ("greater-than", "less-than")}), required_if=_set_action_visibility({"field": "qualifier", "in": ("greater-than", "less-than")}), help_key="trigger-runt.time_seconds"),
        ),
        group="runt",
        editor="trigger",
    ),
    _action_command(
        "trigger-transition", "Trigger", "Transition trigger", (
            _command_field("channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-transition.channel"),
            _command_field("slope", "enum", options=_BINARY_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-transition.slope"),
            _command_field("qualifier", "enum", options=("greater-than", "less-than"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-transition.qualifier"),
            _command_field("low_level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-transition.low_level"),
            _command_field("high_level", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-transition.high_level"),
            _command_field("time_seconds", "number", exclusive_minimum=0, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-transition.time_seconds"),
        ),
        group="transition",
        editor="trigger",
    ),
    _action_command(
        "trigger-delay", "Trigger", "Delay trigger", (
            _command_field("arm_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-delay.arm_channel"),
            _command_field("arm_slope", "enum", options=_BINARY_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-delay.arm_slope"),
            _command_field("trigger_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-delay.trigger_channel"),
            _command_field("trigger_slope", "enum", options=_BINARY_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-delay.trigger_slope"),
            _command_field("time_seconds", "number", minimum=4e-9, maximum=10, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-delay.time_seconds"),
            _command_field("count", "integer", minimum=1, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-delay.count"),
        ),
        group="delay",
        editor="trigger",
    ),
    _action_command(
        "trigger-setup-hold", "Trigger", "Setup and hold trigger", (
            _command_field("clock_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-setup-hold.clock_channel"),
            _command_field("data_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-setup-hold.data_channel"),
            _command_field("slope", "enum", options=_BINARY_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-setup-hold.slope"),
            _command_field("setup_time_seconds", "number", exclusive_minimum=0, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-setup-hold.setup_time_seconds"),
            _command_field("hold_time_seconds", "number", exclusive_minimum=0, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-setup-hold.hold_time_seconds"),
        ),
        group="setup-hold",
        editor="trigger",
    ),
    _action_command(
        "trigger-edge-burst", "Trigger", "Nth edge burst trigger", (
            _command_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge-burst.source_channel"),
            _command_field("slope", "enum", options=_BINARY_SLOPES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge-burst.slope"),
            _command_field("count", "integer", minimum=1, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge-burst.count"),
            _command_field("idle_time", "number", minimum=1e-8, maximum=10, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-edge-burst.idle_time"),
            _command_field("level", "number", visible_if=_set_action_visibility(), help_key="trigger-edge-burst.level"),
        ),
        group="edge-burst",
        editor="trigger",
    ),
    _action_command(
        "trigger-tv", "Trigger", "TV trigger", (
            _command_field("source_channel", "integer", minimum=1, maximum=4, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-tv.source_channel"),
            _command_field("standard", "enum", options=("ntsc", "pal", "palm", "secam"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-tv.standard"),
            _command_field("mode", "enum", options=("field1", "field2", "all-fields", "all-lines", *_TV_LINE_MODES), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-tv.mode"),
            _command_field("polarity", "enum", options=("positive", "negative"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-tv.polarity"),
            _command_field("line", "integer", minimum=1, visible_if=_set_action_visibility({"field": "mode", "in": _TV_LINE_MODES}), required_if=_set_action_visibility({"field": "mode", "in": _TV_LINE_MODES}), help_key="trigger-tv.line"),
        ),
        group="tv",
        editor="trigger",
    ),
    _action_command("trigger-mode", "Trigger", "Trigger type", (_command_field("mode", "enum", options=TRIGGER_MODES, option_label="trigger-mode", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-mode.mode"),), group="pattern-or", editor="trigger"),
    _action_command("trigger-pattern", "Trigger", "Pattern trigger", (_command_field("pattern", "string", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-pattern.pattern"),), group="pattern-or", editor="trigger"),
    _action_command("trigger-or", "Trigger", "OR trigger", (_command_field("pattern", "string", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-or.pattern"),), group="pattern-or", editor="trigger"),
    _action_command("trigger-sweep", "Trigger", "Trigger sweep", (_command_field("mode", "enum", options=("auto", "normal"), visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-sweep.mode"),), group="common", editor="trigger"),
    _action_command("trigger-noise-reject", "Trigger", "Noise reject", (_command_field("enabled", "boolean", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-noise-reject.enabled"),), group="common", editor="trigger"),
    _action_command("trigger-hf-reject", "Trigger", "HF reject", (_command_field("enabled", "boolean", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-hf-reject.enabled"),), group="common", editor="trigger"),
    _action_command("trigger-holdoff", "Trigger", "Trigger holdoff", (_command_field("seconds", "number", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="trigger-holdoff.seconds"),), group="common", editor="trigger"),

    _action_command("search-state", "Search", "Search state", (_command_field("enabled", "boolean", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="search-state.enabled"),), editor="search"),
    _action_command("search-mode", "Search", "Search mode", (_command_field("mode", "enum", options=SEARCH_MODES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="search-mode.mode", option_label="search-mode"),), editor="search"),
    {"id": "search-count", "category": "Search", "label": "Search count", "modes": ("live", "simulate"), "fields": (), "editor": "search"},
    _action_command("search-event", "Search", "Search event", (_command_field("event", "integer", minimum=1, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="search-event.event"),), editor="search"),
    _action_command(
        "serial-search-uart", "Search", "UART Serial Search", (
            _command_field("bus", "integer", minimum=1),
            _command_field("mode", "enum", options=UART_SEARCH_MODES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-search-uart.mode", option_label="serial-search-uart-mode"),
            _command_field("data", "integer", minimum=0, maximum=255, visible_if=_set_action_visibility({"field": "mode", "in": ("rx-data", "rx-1", "rx-0", "rx-any", "tx-data", "tx-1", "tx-0", "tx-any")}), help_key="serial-search-uart.data"),
            _command_field("qualifier", "enum", options=SEARCH_QUALIFIERS, visible_if=_set_action_visibility({"field": "mode", "in": ("rx-data", "rx-1", "rx-0", "rx-any", "tx-data", "tx-1", "tx-0", "tx-any")}), help_key="serial-search-uart.qualifier", option_label="search-qualifier"),
        ),
        editor="search",
    ),
    _action_command(
        "serial-search-i2c", "Search", "I2C Serial Search", (
            _command_field("bus", "integer", minimum=1),
            _command_field("mode", "enum", options=I2C_SEARCH_MODES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-search-i2c.mode", option_label="serial-search-i2c-mode"),
            _command_field("address", "integer", visible_if=_set_action_visibility(), help_key="serial-search-i2c.address"),
            _command_field("data", "integer", visible_if=_set_action_visibility(), help_key="serial-search-i2c.data"),
            _command_field("data2", "integer", visible_if=_set_action_visibility({"field": "mode", "in": ("read7-data2", "write7-data2")}), help_key="serial-search-i2c.data2"),
            _command_field("qualifier", "enum", options=SEARCH_QUALIFIERS, visible_if=_set_action_visibility({"field": "mode", "equals": "eeprom-read"}), help_key="serial-search-i2c.qualifier", option_label="search-qualifier"),
        ),
        editor="search",
    ),
    _action_command(
        "serial-search-spi", "Search", "SPI Serial Search", (
            _command_field("bus", "integer", minimum=1),
            _command_field("mode", "enum", options=SPI_SEARCH_MODES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-search-spi.mode", option_label="serial-search-spi-mode"),
            _command_field("data", "string", visible_if=_set_action_visibility(), help_key="serial-search-spi.data"),
            _command_field("width", "integer", options=tuple(range(1, 11)), minimum=1, maximum=10, visible_if=_set_action_visibility(), help_key="serial-search-spi.width"),
        ),
        editor="search",
    ),
    _action_command(
        "serial-search-can", "Search", "CAN Serial Search", (
            _command_field("bus", "integer", minimum=1),
            _command_field("mode", "enum", options=CAN_SEARCH_MODES, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-search-can.mode", option_label="serial-search-can-mode"),
            _command_field("data", "string", visible_if=_set_action_visibility({"field": "mode", "equals": "data"}), help_key="serial-search-can.data"),
            _command_field("data_length", "integer", options=tuple(range(1, 9)), minimum=1, maximum=8, visible_if=_set_action_visibility({"field": "mode", "equals": "data"}), help_key="serial-search-can.data_length"),
            _command_field("id", "string", visible_if=_set_action_visibility({"field": "mode", "in": ("data", "id-data", "id-either", "id-remote")}), help_key="serial-search-can.id"),
            _command_field("id_mode", "enum", options=CAN_SEARCH_ID_MODES, visible_if=_set_action_visibility({"field": "mode", "in": ("data", "id-data", "id-either", "id-remote")}), help_key="serial-search-can.id_mode", option_label="serial-search-can-id-mode"),
        ),
        editor="search",
    ),

    {
        "id": "serial-query", "category": "Serial", "label": "Serial query",
        "modes": ("live", "simulate"), "fields": (_command_field("bus", "integer", minimum=1),),
        "group": "bus", "browser_hidden": True,
    },
    _action_command(
        "serial-mode", "Serial", "Serial mode", (
            _command_field("bus", "integer", minimum=1),
            _command_field(
                "mode", "enum", options=SERIAL_MODES,
                visible_if=_set_action_visibility(),
                required_if=_set_action_visibility(),
                option_label="serial-protocol",
            ),
        ),
        group="bus", editor="serial", browser_hidden=True,
    ),
    _action_command(
        "serial-display", "Serial", "Serial display", (
            _command_field("bus", "integer", minimum=1),
            _command_field(
                "enabled", "boolean",
                visible_if=_set_action_visibility(),
                required_if=_set_action_visibility(),
                help_key="serial-display.enabled",
            ),
        ),
        group="bus", editor="serial", browser_hidden=True,
    ),
    _action_command(
        "serial-uart", "Serial", "UART configuration", (
            _command_field("bus", "integer", minimum=1),
            _command_field("rx_source", "enum", options=_SERIAL_SOURCE_OPTIONS, visible_if=_set_action_visibility(), help_key="serial-uart.rx_source"),
            _command_field("tx_source", "enum", options=_SERIAL_SOURCE_OPTIONS, visible_if=_set_action_visibility(), help_key="serial-uart.tx_source"),
            _command_field("baud_rate", "integer", minimum=100, maximum=12_000_000, spinner=False, visible_if=_set_action_visibility(), help_key="serial-uart.baud_rate"),
            _command_field("data_bits", "integer", options=(5, 6, 7, 8, 9), minimum=5, maximum=9, visible_if=_set_action_visibility(), help_key="serial-uart.data_bits"),
            _command_field("parity", "enum", options=UART_PARITIES, option_label="serial-uart-parity", visible_if=_set_action_visibility(), help_key="serial-uart.parity"),
            _command_field("polarity", "enum", options=UART_POLARITIES, option_label="serial-uart-polarity", visible_if=_set_action_visibility(), help_key="serial-uart.polarity"),
            _command_field("bit_order", "enum", options=SERIAL_BIT_ORDERS, option_label="serial-bit-order", visible_if=_set_action_visibility(), help_key="serial-uart.bit_order"),
        ),
        group="uart",
        editor="serial",
        browser_hidden=True,
    ),
    _action_command(
        "serial-i2c", "Serial", "I2C configuration", (
            _command_field("bus", "integer", minimum=1),
            _command_field("clock_source", "enum", options=_SERIAL_SOURCE_OPTIONS, visible_if=_set_action_visibility(), help_key="serial-i2c.clock_source"),
            _command_field("data_source", "enum", options=_SERIAL_SOURCE_OPTIONS, visible_if=_set_action_visibility(), help_key="serial-i2c.data_source"),
            _command_field("address_size", "enum", options=I2C_ADDRESS_SIZES, option_label="serial-i2c-address-size", visible_if=_set_action_visibility(), help_key="serial-i2c.address_size"),
        ),
        group="i2c", editor="serial", browser_hidden=True,
    ),
    _action_command(
        "serial-spi", "Serial", "SPI configuration", (
            _command_field("bus", "integer", minimum=1),
            _command_field("clock_source", "enum", options=_SERIAL_SOURCE_OPTIONS, visible_if=_set_action_visibility(), help_key="serial-spi.clock_source"),
            _command_field("mosi_source", "enum", options=_SERIAL_SOURCE_OPTIONS, visible_if=_set_action_visibility(), help_key="serial-spi.mosi_source"),
            _command_field("miso_source", "enum", options=_SERIAL_SOURCE_OPTIONS, visible_if=_set_action_visibility(), help_key="serial-spi.miso_source"),
            _command_field("frame_source", "enum", options=_SERIAL_SOURCE_OPTIONS, visible_if=_set_action_visibility(), help_key="serial-spi.frame_source"),
            _command_field("clock_slope", "enum", options=SPI_CLOCK_SLOPES, option_label="serial-spi-clock-slope", visible_if=_set_action_visibility(), help_key="serial-spi.clock_slope"),
            _command_field("bit_order", "enum", options=SERIAL_BIT_ORDERS, option_label="serial-bit-order", visible_if=_set_action_visibility(), help_key="serial-spi.bit_order"),
            _command_field("word_width", "integer", options=tuple(range(4, 17)), minimum=4, maximum=16, visible_if=_set_action_visibility(), help_key="serial-spi.word_width"),
            _command_field("framing", "enum", options=SPI_FRAMINGS, option_label="serial-spi-framing", visible_if=_set_action_visibility(), help_key="serial-spi.framing"),
            _command_field("clock_timeout", "number", minimum=1e-7, maximum=10, visible_if=_set_action_visibility(), help_key="serial-spi.clock_timeout"),
        ),
        group="spi", editor="serial", browser_hidden=True,
    ),
    _action_command(
        "serial-can", "Serial", "CAN configuration", (
            _command_field("bus", "integer", minimum=1),
            _command_field("source", "enum", options=_SERIAL_SOURCE_OPTIONS, visible_if=_set_action_visibility(), help_key="serial-can.source"),
            _command_field("baud_rate", "integer", minimum=10_000, maximum=5_000_000, spinner=False, visible_if=_set_action_visibility(), help_key="serial-can.baud_rate"),
            _command_field("signal_definition", "enum", options=CAN_SIGNAL_DEFINITIONS, option_label="serial-can-signal-definition", visible_if=_set_action_visibility(), help_key="serial-can.signal_definition"),
            _command_field("sample_point", "number", minimum=30, maximum=90, visible_if=_set_action_visibility(), help_key="serial-can.sample_point"),
        ),
        group="can", editor="serial", browser_hidden=True,
    ),
    _action_command(
        "serial-trigger-uart", "Serial", "UART serial trigger", (
            _command_field("bus", "integer", minimum=1),
            _command_field("type", "enum", options=UART_TRIGGER_TYPES, option_label="serial-trigger-uart-type", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-trigger-uart.type"),
            _command_field("data", "integer", minimum=0, maximum=255, visible_if=_set_action_visibility({"field": "type", "in": ("rx-data", "tx-data")}), required_if=_set_action_visibility({"field": "type", "in": ("rx-data", "tx-data")}), help_key="serial-trigger-uart.data"),
            _command_field("qualifier", "enum", options=UART_TRIGGER_QUALIFIERS, option_label="serial-trigger-qualifier", visible_if=_set_action_visibility({"field": "type", "in": ("rx-data", "tx-data")}), required_if=_set_action_visibility({"field": "type", "in": ("rx-data", "tx-data")}), help_key="serial-trigger-uart.qualifier"),
        ),
        group="uart", editor="serial", browser_hidden=True,
    ),
    _action_command(
        "serial-trigger-i2c", "Serial", "I2C serial trigger", (
            _command_field("bus", "integer", minimum=1),
            _command_field("type", "enum", options=I2C_TRIGGER_TYPES, option_label="serial-trigger-i2c-type", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-trigger-i2c.type"),
            _command_field("address", "integer", minimum=0, maximum=1023, maximum_by_type=dict(I2C_TRIGGER_ADDRESS_MAXIMUM_BY_TYPE), visible_if=_set_action_visibility({"field": "type", "in": ("address-no-ack", "read7", "write7", "write10", "read7-data2", "write7-data2", "read-eeprom")}), required_if=_set_action_visibility({"field": "type", "in": ("address-no-ack", "read7", "write7", "write10", "read7-data2", "write7-data2", "read-eeprom")}), help_key="serial-trigger-i2c.address"),
            _command_field("data", "integer", minimum=0, maximum=255, visible_if=_set_action_visibility({"field": "type", "in": ("read7", "write7", "write10", "read7-data2", "write7-data2", "read-eeprom")}), required_if=_set_action_visibility({"field": "type", "in": ("read7", "write7", "write10", "read7-data2", "write7-data2", "read-eeprom")}), help_key="serial-trigger-i2c.data"),
            _command_field("data2", "integer", minimum=0, maximum=255, visible_if=_set_action_visibility({"field": "type", "in": ("read7-data2", "write7-data2")}), required_if=_set_action_visibility({"field": "type", "in": ("read7-data2", "write7-data2")}), help_key="serial-trigger-i2c.data2"),
            _command_field("qualifier", "enum", options=I2C_TRIGGER_QUALIFIERS, option_label="serial-trigger-qualifier", visible_if=_set_action_visibility({"field": "type", "equals": "read-eeprom"}), required_if=_set_action_visibility({"field": "type", "equals": "read-eeprom"}), help_key="serial-trigger-i2c.qualifier"),
        ),
        group="i2c", editor="serial", browser_hidden=True,
    ),
    _action_command(
        "serial-trigger-spi", "Serial", "SPI serial trigger", (
            _command_field("bus", "integer", minimum=1),
            _command_field("type", "enum", options=SPI_TRIGGER_TYPES, option_label="serial-trigger-spi-type", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-trigger-spi.type"),
            _command_field("width", "integer", options=tuple(range(4, 65)), minimum=4, maximum=64, visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-trigger-spi.width"),
            _command_field("data", "string", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-trigger-spi.data"),
        ),
        group="spi", editor="serial", browser_hidden=True,
    ),
    _action_command(
        "serial-trigger-can", "Serial", "CAN serial trigger", (
            _command_field("bus", "integer", minimum=1),
            _command_field("type", "enum", options=CAN_TRIGGER_TYPES, option_label="serial-trigger-can-type", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-trigger-can.type"),
            _command_field("id", "string", visible_if=_set_action_visibility({"field": "type", "in": ("data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data")}), required_if=_set_action_visibility({"field": "type", "in": ("data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data")}), help_key="serial-trigger-can.id"),
            _command_field("id_mode", "enum", options=CAN_TRIGGER_ID_MODES, option_label="serial-trigger-can-id-mode", visible_if=_set_action_visibility({"field": "type", "in": ("data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data")}), required_if=_set_action_visibility({"field": "type", "in": ("data-frame-id", "any-frame-id", "remote-frame-id", "id-and-data")}), help_key="serial-trigger-can.id_mode"),
            _command_field("data", "string", visible_if=_set_action_visibility({"field": "type", "equals": "id-and-data"}), required_if=_set_action_visibility({"field": "type", "equals": "id-and-data"}), help_key="serial-trigger-can.data"),
            _command_field("data_length", "integer", options=tuple(range(1, 9)), minimum=1, maximum=8, visible_if=_set_action_visibility({"field": "type", "equals": "id-and-data"}), required_if=_set_action_visibility({"field": "type", "equals": "id-and-data"}), help_key="serial-trigger-can.data_length"),
        ),
        group="can", editor="serial", browser_hidden=True,
    ),
    {
        "id": "serial-lister-query", "category": "Serial", "label": "Serial Lister state",
        "modes": ("live", "simulate"), "fields": (), "group": "lister",
        "editor": "serial", "browser_hidden": True,
    },
    _action_command(
        "serial-lister-display", "Serial", "Serial Lister display", (
            _command_field("display", "enum", options=SERIAL_LISTER_DISPLAYS, option_label="serial-lister-display", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-lister.display"),
        ),
        group="lister", editor="serial", browser_hidden=True,
    ),
    _action_command(
        "serial-lister-reference", "Serial", "Serial Lister reference", (
            _command_field("reference", "enum", options=SERIAL_LISTER_REFERENCES, option_label="serial-lister-reference", visible_if=_set_action_visibility(), required_if=_set_action_visibility(), help_key="serial-lister.reference"),
        ),
        group="lister", editor="serial", browser_hidden=True,
    ),
    {
        "id": "serial-lister-export", "category": "Serial", "label": "Export Serial Lister",
        "modes": ("live", "simulate"),
        "fields": (_command_field("filename", "string", required=True, help_key="serial-lister.filename"),),
        "group": "lister", "editor": "serial", "browser_hidden": True,
    },

    {
        "id": "segmented-memory", "category": "Segmented Memory", "label": "Segmented memory", "modes": ("live", "simulate"),
        "editor": "segmented",
        "fields": ({"name": "action", "type": "enum", "options": ("query", "enable", "disable", "select"), "default": "query", "help_key": "segmented-memory.action"}, _command_field("segments", "integer", minimum=2, visible_if=[{"field": "action", "equals": "enable"}], required_if=[{"field": "action", "equals": "enable"}], help_key="segmented-memory.segments"), _command_field("index", "integer", minimum=1, visible_if=[{"field": "action", "equals": "select"}], required_if=[{"field": "action", "equals": "select"}], help_key="segmented-memory.index")),
    },
    {
        "id": "segmented-capture", "category": "Segmented Memory", "label": "Segmented capture", "modes": ("live", "simulate", "dry-run"),
        "editor": "segmented",
        "fields": (_command_field("channel", "integer", minimum=1, maximum=4, default=1, help_key="capture.channel"), _command_field("segments", "integer", minimum=2, required=True, help_key="segmented-capture.segments"), _command_field("points", "integer", options=(1000, 5000, 10000), default=1000, help_key="capture.points"), _command_field("format", "enum", options=("byte", "word"), default="byte", help_key="capture.format"), _command_field("timeout_ms", "integer", minimum=1, default=30000, help_key="segmented-capture.timeout_ms"), _command_field("poll_interval_ms", "integer", minimum=1, default=100, help_key="segmented-capture.poll_interval_ms")),
    },
    {
        "id": "capture-batch", "category": "Workflow", "label": "Periodic Capture", "modes": ("live", "simulate"),
        "group": "capture",
        "editor": "workflow",
        "fields": (_command_field("channels", "multi-enum", options=(1, 2, 3, 4), serialize="csv", required=True, help_key="capture.channels"), _command_field("points", "integer", options=(1000, 5000, 10000), default=1000, help_key="capture.points"), _command_field("format", "enum", options=("byte", "word"), default="byte", help_key="capture.format"), _command_field("count", "integer", minimum=1, default=1, help_key="workflow.capture-batch.count"), _command_field("interval_seconds", "number", minimum=0, default=0, help_key="workflow.capture.interval_seconds")),
    },
    {
        "id": "capture-until", "category": "Workflow", "label": "Capture until", "modes": ("live", "simulate", "dry-run"),
        "group": "capture",
        "editor": "workflow",
        "fields": (_command_field("channels", "multi-enum", options=(1, 2, 3, 4), serialize="csv", default=(1,), required=True, help_key="capture.channels"), _command_field("condition_channel", "enum", options=(1, 2, 3, 4), default=1, required=True, help_key="workflow.capture-until.condition_channel"), _command_field("points", "integer", options=(1000, 5000, 10000), default=1000, help_key="capture.points"), _command_field("format", "enum", options=("byte", "word"), default="byte", help_key="capture.format"), _command_field("metric", "enum", options=("max", "min", "peak-to-peak", "abs-max"), default="max", required=True, help_key="workflow.capture-until.metric"), _command_field("operator", "enum", options=("gt", "gte", "lt", "lte"), default="gt", required=True, help_key="workflow.condition.operator"), _command_field("threshold", "number", required=True, help_key="workflow.capture-until.threshold"), _command_field("count", "integer", minimum=1, maximum=255, default=1, required=True, help_key="workflow.capture-until.count"), _command_field("timeout_seconds", "number", exclusive_minimum=0, required=True, help_key="workflow.condition.timeout_seconds"), _command_field("interval_seconds", "number", minimum=0, default=0, help_key="workflow.capture.interval_seconds")),
    },
    {
        "id": "capture-monitor", "category": "Workflow", "label": "Capture monitor", "modes": ("live", "simulate", "dry-run"),
        "group": "capture",
        "editor": "workflow",
        "fields": (_command_field("channels", "multi-enum", options=(1, 2, 3, 4), serialize="csv", default=(1,), required=True, help_key="capture.channels"), _command_field("points", "integer", options=(1000, 5000, 10000), default=1000, help_key="capture.points"), _command_field("format", "enum", options=("byte", "word"), default="byte", help_key="capture.format"), _command_field("count", "integer", minimum=1, required=True, help_key="workflow.capture-monitor.count"), _command_field("interval_seconds", "number", minimum=0, default=0, help_key="workflow.capture.interval_seconds"), _command_field("retention_points", "integer", minimum=1000, default=250000, required=True, help_key="workflow.capture-monitor.retention_points"), _command_field("save_results", "boolean", default=True, help_key="workflow.save_results")),
    },
    {
        "id": "measure-log", "category": "Workflow", "label": "Measurement log", "modes": ("live", "simulate"),
        "group": "measurement",
        "editor": "workflow",
        "fields": (_command_field("channels", "multi-enum", options=(1, 2, 3, 4), serialize="csv", help_key="workflow.measurement.channels"), _command_field("items", "multi-enum", options=_DIRECT_MEASUREMENT_ITEMS, serialize="csv", default=("vpp", "frequency"), help_key="workflow.measurement.items"), _command_field("pairs", "string", help="Example: 1:2, 3:4", help_key="workflow.measurement.pairs"), _command_field("pair_items", "string", options=PAIR_MEASUREMENT_ITEMS, default="phase,delay", help="Comma-separated pair measurements, for example phase,delay", help_key="workflow.measurement.pair_items"), _command_field("interval_seconds", "number", minimum=0, default=1, help_key="workflow.measurement.interval_seconds"), _command_field("count", "integer", minimum=1, help_key="workflow.measure-log.count"), _command_field("duration_seconds", "number", minimum=0, help_key="workflow.measure-log.duration_seconds"), _command_field("save_results", "boolean", default=True, help_key="workflow.save_results"), _command_field("stop_on_error", "boolean", default=False, help_key="workflow.measure-log.stop_on_error")),
    },
    {
        "id": "measure-until", "category": "Workflow", "label": "Measure until", "modes": ("live", "simulate", "dry-run"),
        "group": "measurement",
        "editor": "workflow",
        "fields": (_command_field("channel", "integer", minimum=1, maximum=4, default=1, help_key="measure.channel"), _command_field("item", "enum", options=_DIRECT_MEASUREMENT_ITEMS, default="vpp", help_key="workflow.measure-until.item"), _command_field("operator", "enum", options=("gt", "gte", "lt", "lte"), required=True, help_key="workflow.condition.operator"), _command_field("threshold", "number", required=True, help_key="workflow.measure-until.threshold"), _command_field("timeout_seconds", "number", exclusive_minimum=0, required=True, help_key="workflow.condition.timeout_seconds"), _command_field("interval_seconds", "number", minimum=0, default=1, help_key="workflow.measurement.interval_seconds"), _command_field("save_results", "boolean", default=True, help_key="workflow.save_results")),
    },
    {
        "id": "triggered-measure-loop", "category": "Workflow", "label": "Triggered measurement loop", "modes": ("live", "simulate", "dry-run"),
        "group": "triggered",
        "editor": "workflow",
        "fields": (_command_field("channels", "multi-enum", options=(1, 2, 3, 4), serialize="csv", help_key="workflow.measurement.channels"), _command_field("items", "multi-enum", options=_DIRECT_MEASUREMENT_ITEMS, serialize="csv", default=("vpp", "frequency"), help_key="workflow.measurement.items"), _command_field("pairs", "string", help="Example: 1:2, 3:4", help_key="workflow.measurement.pairs"), _command_field("pair_items", "string", options=PAIR_MEASUREMENT_ITEMS, default="phase,delay", help="Comma-separated pair measurements, for example phase,delay", help_key="workflow.measurement.pair_items"), _command_field("count", "integer", minimum=1, required=True, help_key="workflow.triggered-measure-loop.count"), _command_field("trigger_timeout_seconds", "number", exclusive_minimum=0, required=True, help_key="workflow.trigger.timeout_seconds"), _command_field("interval_seconds", "number", minimum=0, default=0, help_key="workflow.triggered-measure-loop.interval_seconds"), _command_field("save_results", "boolean", default=True, help_key="workflow.save_results")),
    },
    {
        "id": "triggered-capture-series", "category": "Workflow", "label": "Triggered capture series", "modes": ("live", "simulate", "dry-run"),
        "group": "triggered",
        "editor": "workflow",
        "fields": (_command_field("channels", "multi-enum", options=(1, 2, 3, 4), serialize="csv", required=True, help_key="workflow.triggered-capture-series.channels"), _command_field("count", "integer", minimum=1, required=True, help_key="workflow.triggered-capture-series.count"), _command_field("trigger_timeout_seconds", "number", exclusive_minimum=0, required=True, help_key="workflow.trigger.timeout_seconds"), _command_field("points", "integer", options=(1000, 5000, 10000), default=1000, help_key="capture.points"), _command_field("format", "enum", options=("byte", "word"), default="byte", help_key="capture.format"), _command_field("interval_seconds", "number", minimum=0, default=0, help_key="workflow.capture.interval_seconds")),
    },
    {
        "id": "sequence",
        "category": "Workflow",
        "label": "Sequence",
        "modes": ("live", "simulate", "dry-run"),
        "group": "automation",
        "editor": "sequence",
        "fields": (
            {"name": "document", "type": "object", "required": True, "help_key": "workflow.sequence.document"},
            {"name": "save_results", "type": "boolean", "default": True, "help_key": "workflow.save_results"},
        ),
        "sequence": {
            "version": 1,
            "actions": SEQUENCE_ACTIONS,
            "limits": {
                "step_count": SEQUENCE_MAX_STEPS,
                "loop_count": SEQUENCE_MAX_LOOPS,
                "total_step_executions": SEQUENCE_MAX_TOTAL_STEP_EXECUTIONS,
                "artifact_steps": SEQUENCE_MAX_ARTIFACT_STEPS,
            },
            "parameters": {
                "wait": ({"name": "seconds", "type": "number", "minimum": 0, "default": 0, "required": True, "help_key": "workflow.sequence.wait.seconds"},),
                "single": (),
                "wait-trigger": ({"name": "timeout_seconds", "type": "number", "exclusive_minimum": 0, "default": 1, "required": True, "help_key": "workflow.trigger.timeout_seconds"},),
                "measure": (
                    {"name": "item", "type": "enum", "options": SUPPORTED_MEASUREMENT_ITEMS, "default": "vpp", "required": True, "help_key": "workflow.sequence.measure.item"},
                    {"name": "channel", "type": "integer", "minimum": 1, "maximum": 4, "default": 1, "required": True, "help_key": "measure.channel"},
                    {"name": "reference_channel", "type": "integer", "options": (1, 2, 3, 4), "visible_if": [{"field": "item", "in": ("phase", "delay")}], "required_if": [{"field": "item", "in": ("phase", "delay")}], "help_key": "measure.reference_channel"},
                    {"name": "time_s", "type": "number", "visible_if": [{"field": "item", "equals": "y_at_x"}], "required_if": [{"field": "item", "equals": "y_at_x"}], "help_key": "measure.time_s"},
                    {"name": "level", "type": "number", "visible_if": [{"field": "item", "equals": "time_at_value"}], "required_if": [{"field": "item", "equals": "time_at_value"}], "help_key": "measure.level"},
                    {"name": "slope", "type": "enum", "options": ("positive", "negative"), "default": "positive", "visible_if": [{"field": "item", "in": ("time_at_edge", "time_at_value")}], "help_key": "measure.slope"},
                    {"name": "occurrence", "type": "integer", "minimum": 1, "default": 1, "visible_if": [{"field": "item", "in": ("time_at_edge", "time_at_value")}], "help_key": "measure.occurrence"},
                ),
                "capture": (
                    {"name": "channels", "type": "multi-enum", "options": ("all", 1, 2, 3, 4), "default": (1,), "required": True, "help_key": "capture.channels"},
                    {"name": "points", "type": "integer", "options": SUPPORTED_WAVEFORM_POINTS, "default": 1000, "help_key": "capture.points"},
                    {"name": "waveform_format", "type": "enum", "options": ("byte", "word"), "default": "byte", "help_key": "capture.format"},
                    {"name": "allow_time_axis_tolerance", "type": "boolean", "default": False, "help_key": "workflow.sequence.capture.allow_time_axis_tolerance"},
                ),
                "screenshot": ({"name": "background", "type": "enum", "options": ("black", "white"), "default": "black", "help_key": "workflow.sequence.screenshot.background"},),
                "cleanup": ({"name": "profile", "type": "enum", "options": CLEANUP_PROFILES, "default": "minimal", "help_key": "workflow.sequence.cleanup.profile"},),
            },
        },
    },
)
