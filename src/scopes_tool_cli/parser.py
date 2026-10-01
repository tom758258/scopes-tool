"""CLI argument parser definitions."""

from __future__ import annotations

import argparse

from scopes_tool_core.cleanup import CLEANUP_PROFILES
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
from scopes_tool_core.timebase import TIMEBASE_REFERENCES

# This module stays the parser facade. The private names below keep their
# existing parser.* call sites working after the per-domain split.
from ._parser_acquisition_math import _register_acquisition_math_parsers
from ._parser_channel_analysis import _register_channel_analysis_parsers
from ._parser_common import (
    _add_bus_arg,
    _add_scope_connection_args,
    _add_slot_arg,
    _finite_timebase_float,
    _integer_value,
    _nonnegative_int,
    _positive_int,
    _positive_timebase_float,
    _strict_bool_arg,
)
from ._parser_trigger import _register_trigger_parsers
from ._parser_workflows import _register_workflow_parsers


_SERIAL_SOURCE_HELP = (
    "channelN or external; source availability may depend on the other "
    "configured Serial bus; query both buses after an instrument settings conflict"
)


def _add_worker_client_endpoint_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Worker host; defaults to 127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="Worker HTTP port",
    )


def _add_worker_client_response_args(
    parser: argparse.ArgumentParser,
    *,
    timeout_ms: int,
) -> None:
    parser.add_argument(
        "--timeout-ms",
        type=_positive_int,
        default=timeout_ms,
        help="Worker request timeout in milliseconds; defaults to %(default)s",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format; defaults to text",
    )
    parser.add_argument(
        "--json",
        dest="client_json",
        action="store_true",
        help="write worker client output as JSON",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scopes-tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    worker_parser = subparsers.add_parser("worker", help="run the local Scopes worker")
    worker_parser.set_defaults(lifecycle_command=True)
    worker_parser.add_argument("--host", default="127.0.0.1")
    worker_parser.add_argument("--port", type=int, default=8765)
    mode_group = worker_parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--simulate", action="store_true")
    mode_group.add_argument("--live", action="store_true")
    worker_parser.add_argument("--model", default="keysight-dsox4024a")
    worker_parser.add_argument("--resource", default=None)
    worker_parser.add_argument("--queue-max", type=_positive_int, default=32)
    worker_parser.add_argument("--format", choices=("jsonl", "text"), default="jsonl")

    send_parser = subparsers.add_parser(
        "send-command", help="enqueue a command in a running Scopes worker"
    )
    send_parser.set_defaults(lifecycle_command=True)
    _add_worker_client_endpoint_args(send_parser)
    send_parser.add_argument("--command", dest="worker_command", required=True)
    send_parser.add_argument("--arguments-json", default="{}")
    send_parser.add_argument("--job-id", default=None)
    _add_worker_client_response_args(send_parser, timeout_ms=5000)
    send_parser.add_argument("--dry-run", action="store_true")

    status_parser = subparsers.add_parser("status", help="query worker runtime status")
    status_parser.set_defaults(lifecycle_command=True)
    _add_worker_client_endpoint_args(status_parser)
    _add_worker_client_response_args(status_parser, timeout_ms=5000)

    stop_parser = subparsers.add_parser("stop", help="request cooperative worker stop")
    stop_parser.set_defaults(lifecycle_command=True)
    _add_worker_client_endpoint_args(stop_parser)
    _add_worker_client_response_args(stop_parser, timeout_ms=5000)

    wait_parser = subparsers.add_parser(
        "wait-ready", help="wait until worker status is reachable"
    )
    wait_parser.set_defaults(lifecycle_command=True)
    _add_worker_client_endpoint_args(wait_parser)
    _add_worker_client_response_args(wait_parser, timeout_ms=10000)

    manifest_parser = subparsers.add_parser(
        "manifest",
        allow_abbrev=False,
        help=(
            "print static tool identity and Worker protocol compatibility "
            "without hardware access"
        ),
    )
    manifest_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="write a single machine-readable JSON object to stdout",
    )

    capabilities_parser = subparsers.add_parser(
        "capabilities",
        allow_abbrev=False,
        help=(
            "print registered model capability data from Core without "
            "hardware access"
        ),
    )
    capabilities_parser.add_argument(
        "--model",
        default=None,
        help=(
            "canonical physical model ID; defaults to keysight-dsox4024a "
            "following the existing CLI planning-model policy"
        ),
    )
    capabilities_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="write a single machine-readable JSON object to stdout",
    )

    list_resources_parser = subparsers.add_parser(
        "list-resources",
        help="list VISA resource strings reported by the selected backend",
    )
    list_resources_parser.add_argument(
        "--visa-library",
        default=None,
        help="optional PyVISA library argument, such as @py",
    )
    list_resources_parser.add_argument(
        "--live-only",
        action="store_true",
        help="only print resources that open and respond to *IDN?",
    )
    list_resources_parser.add_argument(
        "--log-scpi",
        action="store_true",
        help="write SCPI command and response logs to stderr when --live-only is used",
    )
    list_resources_parser.add_argument(
        "--serial-read-termination",
        choices=("CRLF", "LF", "CR", "NONE"),
        help="ASRL live discovery read termination compatibility setting",
    )
    list_resources_parser.add_argument(
        "--serial-write-termination",
        choices=("CRLF", "LF", "CR", "NONE"),
        help="ASRL live discovery write termination compatibility setting",
    )
    list_resources_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="write a single machine-readable JSON object to stdout",
    )

    hardware_report_parser = subparsers.add_parser(
        "hardware-report",
        help="render hardware report JSON files as a Markdown summary",
    )
    hardware_report_parser.add_argument(
        "report_paths",
        nargs="+",
        help="report JSON files from smoke or acquisition-check",
    )

    identify_parser = subparsers.add_parser(
        "identify",
        help="open one resource and verify basic communication with *IDN?",
    )
    _add_scope_connection_args(identify_parser)

    check_error_parser = subparsers.add_parser(
        "check-error",
        help="read the oscilloscope system error queue",
    )
    _add_scope_connection_args(check_error_parser)
    check_error_parser.add_argument(
        "--all",
        dest="drain",
        action="store_true",
        help="read until no error is returned or --max-reads is reached",
    )
    check_error_parser.add_argument(
        "--max-reads",
        type=_positive_int,
        default=30,
        help="maximum reads when --all is used",
    )

    system_clear_status_parser = subparsers.add_parser(
        "system-clear-status",
        allow_abbrev=False,
        help="clear status and event data with *CLS",
    )
    _add_scope_connection_args(system_clear_status_parser)

    cleanup_parser = subparsers.add_parser(
        "cleanup",
        allow_abbrev=False,
        help="clear common automation leftovers without resetting the instrument",
    )
    _add_scope_connection_args(cleanup_parser)
    cleanup_parser.add_argument(
        "--profile",
        choices=CLEANUP_PROFILES,
        default="minimal",
        help="cleanup profile; defaults to minimal",
    )

    for command, help_text in (
        ("system-opc", "query operation completion with *OPC?"),
        ("system-status-byte", "query the status byte with *STB?"),
        ("system-standard-event", "destructively read the standard event register"),
        ("system-operation-status", "query the operation condition register"),
        ("system-options", "query installed option tokens with *OPT?"),
    ):
        command_parser = subparsers.add_parser(
            command, allow_abbrev=False, help=help_text
        )
        _add_scope_connection_args(command_parser)
        command_parser.add_argument("--query", action="store_true", required=True)

    run_parser = subparsers.add_parser("run", help="start repetitive acquisitions")
    _add_scope_connection_args(run_parser)

    stop_acquisition_parser = subparsers.add_parser(
        "stop-acquisition", help="stop acquisitions"
    )
    _add_scope_connection_args(stop_acquisition_parser)

    single_parser = subparsers.add_parser(
        "single",
        help="start one single acquisition without waiting",
    )
    _add_scope_connection_args(single_parser)

    force_trigger_parser = subparsers.add_parser(
        "force-trigger",
        help="force one trigger event without waiting for acquisition completion",
    )
    _add_scope_connection_args(force_trigger_parser)

    single_wait_parser = subparsers.add_parser(
        "single-wait",
        help="start one single acquisition and wait finitely for trigger completion",
    )
    _add_scope_connection_args(single_wait_parser)
    single_wait_parser.add_argument(
        "--trigger-timeout-ms",
        type=_positive_int,
        default=5000,
        help="finite trigger wait timeout in milliseconds; defaults to 5000",
    )
    single_wait_parser.add_argument(
        "--trigger-poll-interval-ms",
        type=_positive_int,
        default=100,
        help="trigger wait polling interval in milliseconds; defaults to 100",
    )
    single_wait_parser.add_argument(
        "--force-trigger-on-timeout",
        action="store_true",
        help="after timeout, send :TRIGger:FORCe and continue finite polling",
    )

    _register_channel_analysis_parsers(subparsers)

    serial_status_parser = subparsers.add_parser(
        "serial-status",
        allow_abbrev=False,
        help="show readable serial bus status (mode, display, protocol config)",
    )
    _add_scope_connection_args(serial_status_parser)
    _add_bus_arg(serial_status_parser)

    serial_mode_parser = subparsers.add_parser(
        "serial-mode",
        allow_abbrev=False,
        help="configure or query serial decode bus mode",
    )
    _add_scope_connection_args(serial_mode_parser)
    _add_bus_arg(serial_mode_parser)
    serial_mode_action = serial_mode_parser.add_mutually_exclusive_group(required=True)
    serial_mode_action.add_argument("--query", action="store_true")
    serial_mode_action.add_argument("--mode", choices=SERIAL_MODES)

    for serial_switch_command, serial_switch_help in (
        ("serial-enable", "enable serial decode bus display"),
        ("serial-disable", "disable serial decode bus display"),
    ):
        serial_switch_parser = subparsers.add_parser(
            serial_switch_command,
            allow_abbrev=False,
            help=serial_switch_help,
        )
        _add_scope_connection_args(serial_switch_parser)
        _add_bus_arg(serial_switch_parser)

    serial_lister_status_parser = subparsers.add_parser(
        "serial-lister-status",
        allow_abbrev=False,
        help="show global Serial Lister display and reference state",
    )
    _add_scope_connection_args(serial_lister_status_parser)

    serial_lister_display_parser = subparsers.add_parser(
        "serial-lister-display",
        allow_abbrev=False,
        help="configure or query global Serial Lister display selection",
    )
    _add_scope_connection_args(serial_lister_display_parser)
    serial_lister_display_action = serial_lister_display_parser.add_mutually_exclusive_group(
        required=True
    )
    serial_lister_display_action.add_argument("--query", action="store_true")
    serial_lister_display_action.add_argument(
        "--selection",
        choices=SERIAL_LISTER_DISPLAYS,
        help="canonical selection: off, bus1, bus2, or all",
    )

    serial_lister_reference_parser = subparsers.add_parser(
        "serial-lister-reference",
        allow_abbrev=False,
        help="configure or query global Serial Lister reference",
    )
    _add_scope_connection_args(serial_lister_reference_parser)
    serial_lister_reference_action = serial_lister_reference_parser.add_mutually_exclusive_group(
        required=True
    )
    serial_lister_reference_action.add_argument("--query", action="store_true")
    serial_lister_reference_action.add_argument(
        "--reference", choices=SERIAL_LISTER_REFERENCES
    )

    serial_data_parser = subparsers.add_parser(
        "serial-data",
        allow_abbrev=False,
        help="export host-side Serial Lister CSV data",
    )
    _add_scope_connection_args(serial_data_parser)
    serial_data_parser.add_argument(
        "--output",
        dest="output_path",
        default=None,
        help=(
            "host CSV output path for :LISTer:DATA? payload; defaults to "
            "data/<UTC+8 timestamp>-lister.csv"
        ),
    )

    serial_uart_set_parser = subparsers.add_parser(
        "serial-uart-set", allow_abbrev=False, help="configure UART decode settings"
    )
    _add_scope_connection_args(serial_uart_set_parser)
    _add_bus_arg(serial_uart_set_parser)
    serial_uart_set_parser.add_argument("--rx-source", help=_SERIAL_SOURCE_HELP)
    serial_uart_set_parser.add_argument("--tx-source", help=_SERIAL_SOURCE_HELP)
    serial_uart_set_parser.add_argument("--baud-rate", type=int)
    serial_uart_set_parser.add_argument("--data-bits", type=int)
    serial_uart_set_parser.add_argument("--parity", choices=UART_PARITIES)
    serial_uart_set_parser.add_argument("--polarity", choices=UART_POLARITIES)
    serial_uart_set_parser.add_argument("--bit-order", choices=SERIAL_BIT_ORDERS)

    serial_uart_show_parser = subparsers.add_parser(
        "serial-uart-show", allow_abbrev=False, help="show UART decode settings"
    )
    _add_scope_connection_args(serial_uart_show_parser)
    _add_bus_arg(serial_uart_show_parser)

    serial_uart_trigger_set_parser = subparsers.add_parser(
        "serial-trigger-uart-set",
        allow_abbrev=False,
        help="configure UART trigger criteria",
    )
    _add_scope_connection_args(serial_uart_trigger_set_parser)
    _add_bus_arg(serial_uart_trigger_set_parser)
    serial_uart_trigger_set_parser.add_argument("--type", choices=UART_TRIGGER_TYPES)
    serial_uart_trigger_set_parser.add_argument("--data", type=int)
    serial_uart_trigger_set_parser.add_argument(
        "--qualifier", choices=UART_TRIGGER_QUALIFIERS
    )

    serial_uart_trigger_show_parser = subparsers.add_parser(
        "serial-trigger-uart-show",
        allow_abbrev=False,
        help="show UART trigger criteria",
    )
    _add_scope_connection_args(serial_uart_trigger_show_parser)
    _add_bus_arg(serial_uart_trigger_show_parser)

    serial_i2c_trigger_set_parser = subparsers.add_parser(
        "serial-trigger-i2c-set",
        allow_abbrev=False,
        help="configure I2C trigger criteria",
    )
    _add_scope_connection_args(serial_i2c_trigger_set_parser)
    _add_bus_arg(serial_i2c_trigger_set_parser)
    serial_i2c_trigger_set_parser.add_argument("--type", choices=I2C_TRIGGER_TYPES)
    serial_i2c_trigger_set_parser.add_argument("--address", type=_integer_value)
    serial_i2c_trigger_set_parser.add_argument("--data", type=_integer_value)
    serial_i2c_trigger_set_parser.add_argument("--data2", type=_integer_value)
    serial_i2c_trigger_set_parser.add_argument(
        "--qualifier", choices=I2C_TRIGGER_QUALIFIERS
    )

    serial_i2c_trigger_show_parser = subparsers.add_parser(
        "serial-trigger-i2c-show",
        allow_abbrev=False,
        help="show I2C trigger criteria",
    )
    _add_scope_connection_args(serial_i2c_trigger_show_parser)
    _add_bus_arg(serial_i2c_trigger_show_parser)

    serial_spi_trigger_set_parser = subparsers.add_parser(
        "serial-trigger-spi-set",
        allow_abbrev=False,
        help="configure SPI trigger criteria",
    )
    _add_scope_connection_args(serial_spi_trigger_set_parser)
    _add_bus_arg(serial_spi_trigger_set_parser)
    serial_spi_trigger_set_parser.add_argument("--type", choices=SPI_TRIGGER_TYPES)
    serial_spi_trigger_set_parser.add_argument("--width", type=int)
    serial_spi_trigger_set_parser.add_argument("--data")

    serial_spi_trigger_show_parser = subparsers.add_parser(
        "serial-trigger-spi-show",
        allow_abbrev=False,
        help="show SPI trigger criteria",
    )
    _add_scope_connection_args(serial_spi_trigger_show_parser)
    _add_bus_arg(serial_spi_trigger_show_parser)

    serial_can_trigger_set_parser = subparsers.add_parser(
        "serial-trigger-can-set",
        allow_abbrev=False,
        help="configure CAN trigger criteria",
    )
    _add_scope_connection_args(serial_can_trigger_set_parser)
    _add_bus_arg(serial_can_trigger_set_parser)
    serial_can_trigger_set_parser.add_argument("--type", choices=CAN_TRIGGER_TYPES)
    serial_can_trigger_set_parser.add_argument("--id")
    serial_can_trigger_set_parser.add_argument("--id-mode", choices=CAN_TRIGGER_ID_MODES)
    serial_can_trigger_set_parser.add_argument("--data")
    serial_can_trigger_set_parser.add_argument("--data-length", type=int)

    serial_can_trigger_show_parser = subparsers.add_parser(
        "serial-trigger-can-show",
        allow_abbrev=False,
        help="show CAN trigger criteria",
    )
    _add_scope_connection_args(serial_can_trigger_show_parser)
    _add_bus_arg(serial_can_trigger_show_parser)

    serial_i2c_set_parser = subparsers.add_parser(
        "serial-i2c-set", allow_abbrev=False, help="configure I2C decode settings"
    )
    _add_scope_connection_args(serial_i2c_set_parser)
    _add_bus_arg(serial_i2c_set_parser)
    serial_i2c_set_parser.add_argument("--clock-source", help=_SERIAL_SOURCE_HELP)
    serial_i2c_set_parser.add_argument("--data-source", help=_SERIAL_SOURCE_HELP)
    serial_i2c_set_parser.add_argument("--address-size", choices=I2C_ADDRESS_SIZES)

    serial_i2c_show_parser = subparsers.add_parser(
        "serial-i2c-show", allow_abbrev=False, help="show I2C decode settings"
    )
    _add_scope_connection_args(serial_i2c_show_parser)
    _add_bus_arg(serial_i2c_show_parser)

    serial_spi_set_parser = subparsers.add_parser(
        "serial-spi-set", allow_abbrev=False, help="configure SPI decode settings"
    )
    _add_scope_connection_args(serial_spi_set_parser)
    _add_bus_arg(serial_spi_set_parser)
    serial_spi_set_parser.add_argument("--clock-source", help=_SERIAL_SOURCE_HELP)
    serial_spi_set_parser.add_argument("--mosi-source", help=_SERIAL_SOURCE_HELP)
    serial_spi_set_parser.add_argument("--miso-source", help=_SERIAL_SOURCE_HELP)
    serial_spi_set_parser.add_argument("--frame-source", help=_SERIAL_SOURCE_HELP)
    serial_spi_set_parser.add_argument("--clock-slope", choices=SPI_CLOCK_SLOPES)
    serial_spi_set_parser.add_argument("--bit-order", choices=SERIAL_BIT_ORDERS)
    serial_spi_set_parser.add_argument("--word-width", type=int)
    serial_spi_set_parser.add_argument(
        "--framing",
        choices=SPI_FRAMINGS,
        help="canonical framing: chip-select, no-chip-select, or timeout",
    )
    serial_spi_set_parser.add_argument(
        "--clock-timeout",
        type=float,
        help=(
            "SPI clock timeout; only valid when the same configure request "
            "also provides --framing timeout"
        ),
    )

    serial_spi_show_parser = subparsers.add_parser(
        "serial-spi-show", allow_abbrev=False, help="show SPI decode settings"
    )
    _add_scope_connection_args(serial_spi_show_parser)
    _add_bus_arg(serial_spi_show_parser)

    serial_can_set_parser = subparsers.add_parser(
        "serial-can-set", allow_abbrev=False, help="configure CAN decode settings"
    )
    _add_scope_connection_args(serial_can_set_parser)
    _add_bus_arg(serial_can_set_parser)
    serial_can_set_parser.add_argument("--source", help=_SERIAL_SOURCE_HELP)
    serial_can_set_parser.add_argument("--baud-rate", type=int)
    serial_can_set_parser.add_argument("--signal-definition", choices=CAN_SIGNAL_DEFINITIONS)
    serial_can_set_parser.add_argument("--sample-point", type=float)

    serial_can_show_parser = subparsers.add_parser(
        "serial-can-show", allow_abbrev=False, help="show CAN decode settings"
    )
    _add_scope_connection_args(serial_can_show_parser)
    _add_bus_arg(serial_can_show_parser)

    search_state_parser = subparsers.add_parser(
        "search-state", allow_abbrev=False, help="configure or query waveform search state"
    )
    _add_scope_connection_args(search_state_parser)
    search_state_parser.add_argument("--query", action="store_true")
    search_state_parser.add_argument("--enabled", type=_strict_bool_arg)

    search_mode_parser = subparsers.add_parser(
        "search-mode", allow_abbrev=False, help="configure or query waveform search mode"
    )
    _add_scope_connection_args(search_mode_parser)
    search_mode_parser.add_argument("--query", action="store_true")
    search_mode_parser.add_argument("--mode", choices=SEARCH_MODES)

    search_count_parser = subparsers.add_parser(
        "search-count", allow_abbrev=False, help="query waveform search event count"
    )
    _add_scope_connection_args(search_count_parser)
    search_count_parser.add_argument("--query", action="store_true", required=True)

    search_event_parser = subparsers.add_parser(
        "search-event", allow_abbrev=False, help="configure or query selected search event"
    )
    _add_scope_connection_args(search_event_parser)
    search_event_action = search_event_parser.add_mutually_exclusive_group(required=True)
    search_event_action.add_argument("--query", action="store_true")
    search_event_action.add_argument("--event", type=_positive_int)

    serial_search_uart_parser = subparsers.add_parser(
        "serial-search-uart",
        allow_abbrev=False,
        help="configure or query UART search criteria",
    )
    _add_scope_connection_args(serial_search_uart_parser)
    _add_bus_arg(serial_search_uart_parser)
    serial_search_uart_parser.add_argument("--query", action="store_true")
    serial_search_uart_parser.add_argument("--mode", choices=UART_SEARCH_MODES)
    serial_search_uart_parser.add_argument("--data", type=int)
    serial_search_uart_parser.add_argument("--qualifier", choices=SEARCH_QUALIFIERS)

    serial_search_i2c_parser = subparsers.add_parser(
        "serial-search-i2c",
        allow_abbrev=False,
        help="configure or query I2C search criteria",
    )
    _add_scope_connection_args(serial_search_i2c_parser)
    _add_bus_arg(serial_search_i2c_parser)
    serial_search_i2c_parser.add_argument("--query", action="store_true")
    serial_search_i2c_parser.add_argument("--mode", choices=I2C_SEARCH_MODES)
    serial_search_i2c_parser.add_argument("--address", type=int)
    serial_search_i2c_parser.add_argument("--data", type=int)
    serial_search_i2c_parser.add_argument("--data2", type=int)
    serial_search_i2c_parser.add_argument("--qualifier", choices=SEARCH_QUALIFIERS)

    serial_search_spi_parser = subparsers.add_parser(
        "serial-search-spi",
        allow_abbrev=False,
        help="configure or query SPI search criteria",
    )
    _add_scope_connection_args(serial_search_spi_parser)
    _add_bus_arg(serial_search_spi_parser)
    serial_search_spi_parser.add_argument("--query", action="store_true")
    serial_search_spi_parser.add_argument("--mode", choices=SPI_SEARCH_MODES)
    serial_search_spi_parser.add_argument("--data")
    serial_search_spi_parser.add_argument("--width", type=int)

    serial_search_can_parser = subparsers.add_parser(
        "serial-search-can",
        allow_abbrev=False,
        help="configure or query CAN search criteria",
    )
    _add_scope_connection_args(serial_search_can_parser)
    _add_bus_arg(serial_search_can_parser)
    serial_search_can_parser.add_argument("--query", action="store_true")
    serial_search_can_parser.add_argument("--mode", choices=CAN_SEARCH_MODES)
    serial_search_can_parser.add_argument("--data")
    serial_search_can_parser.add_argument("--data-length", type=int)
    serial_search_can_parser.add_argument("--id")
    serial_search_can_parser.add_argument("--id-mode", choices=CAN_SEARCH_ID_MODES)

    save_pwd_parser = subparsers.add_parser(
        "save-pwd", allow_abbrev=False, help="configure or query the instrument save directory"
    )
    _add_scope_connection_args(save_pwd_parser)
    save_pwd_action = save_pwd_parser.add_mutually_exclusive_group(required=True)
    save_pwd_action.add_argument("--query", action="store_true")
    save_pwd_action.add_argument("--path")

    save_filename_parser = subparsers.add_parser(
        "save-filename", allow_abbrev=False, help="configure or query the instrument save base name"
    )
    _add_scope_connection_args(save_filename_parser)
    save_filename_action = save_filename_parser.add_mutually_exclusive_group(required=True)
    save_filename_action.add_argument("--query", action="store_true")
    save_filename_action.add_argument("--name")

    save_image_format_parser = subparsers.add_parser(
        "save-image-format", allow_abbrev=False, help="configure or query instrument image save format"
    )
    _add_scope_connection_args(save_image_format_parser)
    save_image_format_action = save_image_format_parser.add_mutually_exclusive_group(
        required=True
    )
    save_image_format_action.add_argument("--query", action="store_true")
    save_image_format_action.add_argument("--format", choices=SAVE_IMAGE_FORMATS)

    save_image_palette_parser = subparsers.add_parser(
        "save-image-palette", allow_abbrev=False, help="configure or query instrument image palette"
    )
    _add_scope_connection_args(save_image_palette_parser)
    save_image_palette_action = save_image_palette_parser.add_mutually_exclusive_group(
        required=True
    )
    save_image_palette_action.add_argument("--query", action="store_true")
    save_image_palette_action.add_argument("--palette", choices=SAVE_IMAGE_PALETTES)

    for command, help_text in (
        ("save-image-ink-saver", "configure or query instrument image ink saver"),
        ("save-image-factors", "configure or query instrument image factors"),
    ):
        setting_parser = subparsers.add_parser(
            command, allow_abbrev=False, help=help_text
        )
        _add_scope_connection_args(setting_parser)
        action = setting_parser.add_mutually_exclusive_group(required=True)
        action.add_argument("--query", action="store_true")
        action.add_argument("--enabled", type=_strict_bool_arg)

    save_image_parser = subparsers.add_parser(
        "save-image", allow_abbrev=False, help="save an image on instrument-side storage"
    )
    _add_scope_connection_args(save_image_parser)
    save_image_parser.add_argument("--filename", required=True)

    save_waveform_format_parser = subparsers.add_parser(
        "save-waveform-format",
        allow_abbrev=False,
        help="configure or query instrument waveform save format",
    )
    _add_scope_connection_args(save_waveform_format_parser)
    save_waveform_format_action = save_waveform_format_parser.add_mutually_exclusive_group(
        required=True
    )
    save_waveform_format_action.add_argument("--query", action="store_true")
    save_waveform_format_action.add_argument("--format", choices=SAVE_WAVEFORM_FORMATS)

    save_waveform_length_parser = subparsers.add_parser(
        "save-waveform-length",
        allow_abbrev=False,
        help="configure or query instrument waveform save length",
    )
    _add_scope_connection_args(save_waveform_length_parser)
    save_waveform_length_action = save_waveform_length_parser.add_mutually_exclusive_group(
        required=True
    )
    save_waveform_length_action.add_argument("--query", action="store_true")
    save_waveform_length_action.add_argument("--points", type=int)

    save_waveform_length_max_parser = subparsers.add_parser(
        "save-waveform-length-max",
        allow_abbrev=False,
        help="query maximum-length waveform save mode",
    )
    _add_scope_connection_args(save_waveform_length_max_parser)
    save_waveform_length_max_parser.add_argument(
        "--query", action="store_true", required=True
    )

    save_waveform_parser = subparsers.add_parser(
        "save-waveform", allow_abbrev=False, help="save waveform data on instrument-side storage"
    )
    _add_scope_connection_args(save_waveform_parser)
    save_waveform_parser.add_argument("--filename", required=True)
    save_waveform_parser.add_argument("--source-channel", type=int)

    reference_save_parser = subparsers.add_parser(
        "reference-save", help="copy an analog channel into a reference waveform slot"
    )
    _add_scope_connection_args(reference_save_parser)
    _add_slot_arg(reference_save_parser)
    reference_save_parser.add_argument("--source-channel", type=_positive_int, required=True)

    reference_display_parser = subparsers.add_parser(
        "reference-display", help="set or query reference waveform display state"
    )
    _add_scope_connection_args(reference_display_parser)
    _add_slot_arg(reference_display_parser)
    reference_display_action = reference_display_parser.add_mutually_exclusive_group(required=True)
    reference_display_action.add_argument("--query", action="store_true")
    reference_display_action.add_argument("--state", choices=("on", "off"))

    reference_label_parser = subparsers.add_parser(
        "reference-label", help="set or query a reference waveform label"
    )
    _add_scope_connection_args(reference_label_parser)
    _add_slot_arg(reference_label_parser)
    reference_label_action = reference_label_parser.add_mutually_exclusive_group(required=True)
    reference_label_action.add_argument("--query", action="store_true")
    reference_label_action.add_argument("--text")

    reference_clear_parser = subparsers.add_parser(
        "reference-clear", help="clear a reference waveform slot"
    )
    _add_scope_connection_args(reference_clear_parser)
    _add_slot_arg(reference_clear_parser)

    reference_query_parser = subparsers.add_parser(
        "reference-query", help="query reference waveform display and label state"
    )
    _add_scope_connection_args(reference_query_parser)
    _add_slot_arg(reference_query_parser)

    annotation_parser = subparsers.add_parser(
        "annotation",
        help="set, clear, or query display annotation text",
    )
    _add_scope_connection_args(annotation_parser)
    annotation_parser.add_argument(
        "--slot",
        type=_positive_int,
        default=1,
        help="annotation slot; 4000X supports 1-10, 2000X/3000X support 1",
    )
    annotation_parser.add_argument("--query", action="store_true", help="query annotation state")
    annotation_parser.add_argument("--on", action="store_true", help="turn annotation on")
    annotation_parser.add_argument("--off", action="store_true", help="turn annotation off")
    annotation_parser.add_argument("--text", help="annotation text")
    annotation_parser.add_argument("--clear", action="store_true", help="clear annotation text")
    annotation_parser.add_argument("--color", help="annotation text color")
    annotation_parser.add_argument("--background", help="annotation background color")
    annotation_parser.add_argument("--x", type=_nonnegative_int, help="4000X annotation x position, 0-800")
    annotation_parser.add_argument("--y", type=_nonnegative_int, help="4000X annotation y position, 0-480")

    timebase_scale_parser = subparsers.add_parser(
        "timebase-scale",
        help="set or query horizontal scale",
    )
    _add_scope_connection_args(timebase_scale_parser)
    scale_action = timebase_scale_parser.add_mutually_exclusive_group(required=True)
    scale_action.add_argument(
        "--seconds-per-division",
        dest="timebase_scale_value",
        type=_positive_timebase_float,
        help="horizontal scale in seconds per division",
    )
    scale_action.add_argument(
        "--query",
        dest="timebase_scale_query",
        action="store_true",
        help="query the horizontal scale",
    )

    timebase_position_parser = subparsers.add_parser(
        "timebase-position",
        help="set or query horizontal position",
    )
    _add_scope_connection_args(timebase_position_parser)
    position_action = timebase_position_parser.add_mutually_exclusive_group(required=True)
    position_action.add_argument(
        "--seconds",
        dest="timebase_position_value",
        type=_finite_timebase_float,
        help="horizontal position in seconds",
    )
    position_action.add_argument(
        "--query",
        dest="timebase_position_query",
        action="store_true",
        help="query the horizontal position",
    )

    timebase_reference_parser = subparsers.add_parser(
        "timebase-reference",
        help="set or query horizontal reference position",
    )
    _add_scope_connection_args(timebase_reference_parser)
    reference_action = timebase_reference_parser.add_mutually_exclusive_group(
        required=True
    )
    reference_action.add_argument(
        "--reference",
        dest="timebase_reference_value",
        choices=TIMEBASE_REFERENCES,
        help="horizontal reference position",
    )
    reference_action.add_argument(
        "--query",
        dest="timebase_reference_query",
        action="store_true",
        help="query the horizontal reference position",
    )

    _register_trigger_parsers(subparsers)

    _register_workflow_parsers(subparsers)

    _register_acquisition_math_parsers(subparsers)

    return parser
