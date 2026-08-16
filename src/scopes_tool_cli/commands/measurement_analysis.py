from __future__ import annotations

import argparse
from typing import Sequence

from scopes_tool_core.cursor import (
    cursor_auto_timebase_json,
    cursor_auto_timebase_plan,
    cursor_auto_vertical_json,
    cursor_auto_vertical_plan,
    cursor_configure_commands,
)
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
)
from scopes_tool_core.capabilities import ScopeCapabilities
from scopes_tool_core.channel import (
    channel_offset_command,
    channel_offset_query,
    channel_scale_command,
    channel_scale_query,
    validate_analog_channel,
)
from scopes_tool_core.demo import (
    demo_function_command,
    demo_function_query,
    demo_output_command,
    demo_output_query,
    demo_phase_command,
    demo_phase_query,
    demo_query_commands,
    validate_demo_phase,
)
from scopes_tool_core.dvm import (
    dvm_auto_range_command,
    dvm_auto_range_query,
    dvm_current_query,
    dvm_enable_command,
    dvm_enable_query,
    dvm_mode_command,
    dvm_mode_query,
    dvm_query_commands,
    dvm_source_command,
    dvm_source_query,
)
from scopes_tool_core.errors import OscilloscopeError, ParameterValidationError
from scopes_tool_core.measurements import (
    MeasurementStatisticsResult,
    measurement_clear_command,
    measurement_results_query,
    measurement_show_command,
    measurement_show_query,
    measurement_source_command,
    measurement_source_query,
    measurement_window_command,
    measurement_window_query,
    statistics_install_command,
    statistics_mode_scpi,
    validate_statistics_items,
    validate_statistics_max_count,
    validate_statistics_settle_seconds,
)
from scopes_tool_core.reference import (
    reference_clear_command,
    reference_display_command,
    reference_display_query,
    reference_label_command,
    reference_label_query,
    reference_query_commands,
    reference_save_command,
    validate_reference_label,
    validate_reference_slot,
)
from scopes_tool_core.timebase import (
    timebase_position_query,
    timebase_scale_command,
    timebase_scale_query,
)
from scopes_tool_core.wgen import (
    validate_wgen_amplitude,
    validate_wgen_frequency,
    validate_wgen_function,
    validate_wgen_offset,
    wgen_frequency_command,
    wgen_frequency_query,
    wgen_function_command,
    wgen_function_query,
    wgen_load_command,
    wgen_load_query,
    wgen_offset_command,
    wgen_offset_query,
    wgen_output_command,
    wgen_output_query,
    wgen_query_commands,
    wgen_voltage_command,
    wgen_voltage_query,
)

from .. import runtime


def _measurement_control_plan(
    args: argparse.Namespace, capabilities: ScopeCapabilities
) -> tuple[list[str], dict[str, object]]:
    if args.command == "measure-clear":
        command = measurement_clear_command()
        return [command], {"operation": "clear", "command": command}
    if args.command == "measure-show":
        command = measurement_show_query() if args.query else measurement_show_command()
        return [command], {
            "operation": "query" if args.query else "set",
            "command": command,
            "enabled": None if args.query else True,
        }
    if args.command == "measure-source":
        command = (
            measurement_source_query()
            if args.query
            else measurement_source_command(
                args.source_channel, args.source2_channel, capabilities=capabilities
            )
        )
        return [command], {
            "operation": "query" if args.query else "set",
            "command": command,
            "source1_channel": None if args.query else args.source_channel,
            "source2_channel": None if args.query else args.source2_channel,
        }
    if args.command == "measure-window":
        command = measurement_window_query() if args.query else measurement_window_command(args.window)
        return [command], {
            "operation": "query" if args.query else "set",
            "command": command,
            "window": None if args.query else args.window.upper(),
        }
    raise ParameterValidationError(f"unsupported measurement control command: {args.command}")


def _reference_waveform_plan(
    args: argparse.Namespace, capabilities: ScopeCapabilities
) -> tuple[list[str], dict[str, object]]:
    slot = validate_reference_slot(args.slot, capabilities)
    if args.command == "reference-save":
        command = reference_save_command(slot, args.source_channel, capabilities=capabilities)
        return [command], {"operation": "save", "command": command, "slot": slot, "source_channel": args.source_channel}
    if args.command == "reference-display":
        query = bool(args.query)
        displayed = None if query else args.state == "on"
        command = reference_display_query(slot, capabilities=capabilities) if query else reference_display_command(slot, displayed, capabilities=capabilities)
        return [command], {"operation": "query" if query else "set", "command": command, "slot": slot, "displayed": displayed}
    if args.command == "reference-label":
        query = bool(args.query)
        label = None if query else validate_reference_label(args.text)
        command = reference_label_query(slot, capabilities=capabilities) if query else reference_label_command(slot, label, capabilities=capabilities)
        return [command], {"operation": "query" if query else "set", "command": command, "slot": slot, "label": label}
    if args.command == "reference-clear":
        command = reference_clear_command(slot, capabilities=capabilities)
        return [command], {"operation": "clear", "command": command, "slot": slot}
    if args.command == "reference-query":
        commands = list(reference_query_commands(slot, capabilities=capabilities))
        return commands, {"operation": "query", "commands": commands, "slot": slot, "displayed": None, "label": None}
    raise ParameterValidationError(f"unsupported reference waveform command: {args.command}")


def _cursor_query_commands() -> list[str]:
    return [
        ":MARKer:MODE?",
        ":MARKer:X1Position?",
        ":MARKer:X2Position?",
        ":MARKer:Y1Position?",
        ":MARKer:Y2Position?",
        ":MARKer:XDELta?",
        ":MARKer:YDELta?",
        ":MARKer:DYDX?",
    ]


def _cursor_range_diagnostic(args: argparse.Namespace, entry) -> str | None:
    if (
        getattr(args, "command", None) != "cursor"
        or getattr(args, "cursor_query", False)
        or getattr(args, "cursor_off", False)
        or entry.code != -222
        or "data out of range" not in entry.message.lower()
    ):
        return None
    auto_timebase = getattr(args, "auto_timebase", False)
    auto_vertical = getattr(args, "auto_vertical", False)
    if auto_timebase and auto_vertical:
        return (
            "cursor position was rejected as out of range after auto adjustment; "
            "check instrument limits or manually adjust timebase scale and channel "
            "scale/offset"
        )
    if auto_timebase:
        return (
            "cursor Y position may be outside the current vertical display range; "
            "retry with cursor --auto-vertical, manually adjust channel scale/offset, "
            "or choose smaller Y cursor positions"
        )
    if auto_vertical:
        return (
            "cursor X position may be outside the current horizontal display range; "
            "retry with cursor --auto-timebase, use a wider timebase scale, or choose "
            "smaller X cursor positions"
        )
    return (
        "cursor position was rejected as out of range; retry with cursor "
        "--auto-timebase for X positions or cursor --auto-vertical for Y positions, "
        "or manually adjust the display range"
    )


def _measure_stats_planned_scpi(
    channel: int,
    items: Sequence[str],
    mode: str,
    *,
    reset: bool = False,
    max_count: int | None = None,
) -> list[str]:
    commands = [":MEASure:CLEar", f":MEASure:SOURce CHANnel{channel}"]
    commands.extend(statistics_install_command(item) for item in items)
    if reset:
        commands.append(":MEASure:STATistics:RESet")
    if max_count is not None:
        commands.append(f":MEASure:STATistics:COUNt {validate_statistics_max_count(max_count)}")
    commands.extend([f":MEASure:STATistics {statistics_mode_scpi(mode)}", ":MEASure:RESults?"])
    return commands


def _measurement_statistics_json(result: MeasurementStatisticsResult) -> dict[str, object]:
    return {
        "channel": result.channel,
        "mode": result.mode,
        "raw_response": result.raw_response,
        "records": [
            {
                "item": record.item,
                "current": record.current,
                "minimum": record.minimum,
                "maximum": record.maximum,
                "mean": record.mean,
                "stddev": record.stddev,
                "count": record.count,
                "raw_values": list(record.raw_values),
            }
            for record in result.records
        ],
    }


def _cmd_measurement_control(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        if scope.capabilities is None:
            print("Capabilities: unavailable for this model")
            return 1
        commands, result = _measurement_control_plan(args, scope.capabilities)
        if args.command == "measure-clear":
            scope.clear_measurements()
        elif args.command == "measure-show":
            if args.query:
                state = scope.query_measurement_show()
                result.update(enabled=state.enabled, raw_enabled=state.raw_enabled)
            else:
                scope.configure_measurement_show()
        elif args.command == "measure-source":
            if args.query:
                state = scope.query_measurement_source()
                result.update(
                    source1=state.source1,
                    source2=state.source2,
                    source1_channel=state.source1_channel,
                    source2_channel=state.source2_channel,
                    raw=state.raw,
                )
            else:
                scope.configure_measurement_source(args.source_channel, args.source2_channel)
        elif args.command == "measure-window":
            if args.query:
                state = scope.query_measurement_window()
                result.update(window=state.window, raw_window=state.raw_window)
            else:
                scope.configure_measurement_window(args.window)
        runtime._json_update_result(**result)
        for command in commands:
            print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_reference_waveform(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        if scope.capabilities is None:
            print("Capabilities: unavailable for this model")
            return 1
        commands, result = _reference_waveform_plan(args, scope.capabilities)
        if args.command == "reference-save":
            scope.save_reference_waveform(args.slot, args.source_channel)
        elif args.command == "reference-display":
            if args.query:
                displayed, raw = scope.query_reference_display(args.slot)
                result.update(displayed=displayed, raw_displayed=raw)
            else:
                scope.configure_reference_display(args.slot, args.state == "on")
        elif args.command == "reference-label":
            if args.query:
                label, raw = scope.query_reference_label(args.slot)
                result.update(label=label, raw_label=raw)
            else:
                scope.configure_reference_label(args.slot, args.text)
        elif args.command == "reference-clear":
            scope.clear_reference_waveform(args.slot)
        elif args.command == "reference-query":
            state = scope.query_reference_waveform(args.slot)
            result.update(
                displayed=state.displayed,
                raw_displayed=state.raw_displayed,
                label=state.label,
                raw_label=state.raw_label,
            )
        runtime._json_update_result(**result)
        for command in commands:
            print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_dvm(args: argparse.Namespace) -> int:
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

        if args.command == "dvm-enable":
            if args.query:
                command = dvm_enable_query()
                state = scope.query_dvm_enable()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"DVM enabled: {state.enabled}")
            else:
                command = dvm_enable_command(args.enabled)
                scope.configure_dvm_enable(args.enabled)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    enabled=args.enabled,
                    state_changing=True,
                )
                print(f"DVM enabled: {args.enabled}")
            print(f"Command: {command}")
        elif args.command == "dvm-source":
            if args.query:
                command = dvm_source_query()
                state = scope.query_dvm_source()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"DVM source channel: {state.source_channel}")
            else:
                channel = validate_analog_channel(args.channel, scope.capabilities)
                command = dvm_source_command(channel, capabilities=scope.capabilities)
                scope.configure_dvm_source(channel)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    source_channel=channel,
                    state_changing=True,
                )
                print(f"DVM source channel: {channel}")
            print(f"Command: {command}")
        elif args.command == "dvm-mode":
            if args.query:
                command = dvm_mode_query()
                state = scope.query_dvm_mode()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"DVM mode: {state.mode}")
            else:
                command = dvm_mode_command(args.mode)
                scope.configure_dvm_mode(args.mode)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    mode=args.mode,
                    state_changing=True,
                )
                print(f"DVM mode: {args.mode}")
            print(f"Command: {command}")
        elif args.command == "dvm-auto-range":
            if args.query:
                command = dvm_auto_range_query()
                state = scope.query_dvm_auto_range()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"DVM auto range enabled: {state.auto_range_enabled}")
            else:
                command = dvm_auto_range_command(args.enabled)
                scope.configure_dvm_auto_range(args.enabled)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    auto_range_enabled=args.enabled,
                    state_changing=True,
                )
                print(f"DVM auto range enabled: {args.enabled}")
            print(f"Command: {command}")
        elif args.command == "dvm-current":
            command = dvm_current_query()
            reading = scope.query_dvm_current()
            runtime._json_update_result(operation="query", command=command, **reading.to_json())
            print(f"Command: {command}")
            print(f"DVM current value: {reading.value}")
        else:
            commands = dvm_query_commands()
            state = scope.query_dvm()
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            print(f"DVM enabled: {state.enabled}")
            print(f"DVM source channel: {state.source_channel}")
            print(f"DVM mode: {state.mode}")
            print(f"DVM auto range enabled: {state.auto_range_enabled}")
            print(f"DVM current value: {state.value}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_demo(args: argparse.Namespace) -> int:
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

        if args.command == "demo-query":
            commands = demo_query_commands()
            state = scope.query_demo()
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            print(f"DEMO function: {state.function or 'unknown'}")
            print(f"DEMO output enabled: {state.enabled}")
            print(f"DEMO phase degrees: {state.phase_degrees}")
        elif args.command == "demo-output":
            if args.query:
                command = demo_output_query()
                state = scope.query_demo_output()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"DEMO output enabled: {state.enabled}")
            else:
                command = demo_output_command(args.enabled)
                scope.configure_demo_output(args.enabled)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    enabled=args.enabled,
                    state_changing=True,
                )
                print(f"DEMO output enabled: {args.enabled}")
            print(f"Command: {command}")
        elif args.command == "demo-function":
            if args.query:
                command = demo_function_query()
                state = scope.query_demo_function()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"DEMO function: {state.function or 'unknown'}")
            else:
                function = args.function
                command = demo_function_command(function, capabilities=scope.capabilities)
                scope.configure_demo_function(function)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    function=function,
                    state_changing=True,
                )
                print(f"DEMO function: {function}")
            print(f"Command: {command}")
        else:
            if args.query:
                command = demo_phase_query()
                state = scope.query_demo_phase()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"DEMO phase degrees: {state.phase_degrees}")
            else:
                degrees = validate_demo_phase(args.degrees)
                command = demo_phase_command(degrees)
                scope.configure_demo_phase(degrees)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    degrees=degrees,
                    state_changing=True,
                )
                print(f"DEMO phase degrees: {degrees}")
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_wgen(args: argparse.Namespace) -> int:
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
        capabilities = scope.capabilities

        if args.command == "wgen-query":
            commands = wgen_query_commands(capabilities)
            state = scope.query_wgen()
            runtime._json_update_result(operation="query", commands=commands, **state.to_json())
            for command in commands:
                print(f"Command: {command}")
            print(f"WGEN output enabled: {state.enabled}")
            print(f"WGEN function: {state.function or 'unknown'}")
            print(f"WGEN frequency Hz: {state.frequency_hz}")
            print(f"WGEN amplitude volts: {state.amplitude_volts}")
            print(f"WGEN offset volts: {state.offset_volts}")
            print(f"WGEN load: {state.load}")
        elif args.command == "wgen-output":
            if args.query:
                command = wgen_output_query(capabilities)
                state = scope.query_wgen_output()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"WGEN output enabled: {state.enabled}")
            else:
                command = wgen_output_command(args.enabled, capabilities)
                scope.configure_wgen_output(args.enabled)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    enabled=args.enabled,
                    state_changing=True,
                )
                print(f"WGEN output enabled: {args.enabled}")
            print(f"Command: {command}")
        elif args.command == "wgen-function":
            if args.query:
                command = wgen_function_query(capabilities)
                state = scope.query_wgen_function()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"WGEN function: {state.function or 'unknown'}")
            else:
                function = validate_wgen_function(args.function)
                command = wgen_function_command(function, capabilities)
                scope.configure_wgen_function(function)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    function=function,
                    state_changing=True,
                )
                print(f"WGEN function: {function}")
            print(f"Command: {command}")
        elif args.command == "wgen-frequency":
            if args.query:
                command = wgen_frequency_query(capabilities)
                state = scope.query_wgen_frequency()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"WGEN frequency Hz: {state.frequency_hz}")
            else:
                value = validate_wgen_frequency(args.hz)
                command = wgen_frequency_command(value, capabilities)
                scope.configure_wgen_frequency(value)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    frequency_hz=value,
                    state_changing=True,
                )
                print(f"WGEN frequency Hz: {value}")
            print(f"Command: {command}")
        elif args.command == "wgen-voltage":
            if args.query:
                command = wgen_voltage_query(capabilities)
                state = scope.query_wgen_voltage()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"WGEN amplitude volts: {state.amplitude_volts}")
            else:
                value = validate_wgen_amplitude(args.amplitude)
                command = wgen_voltage_command(value, capabilities)
                scope.configure_wgen_voltage(value)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    amplitude_volts=value,
                    state_changing=True,
                )
                print(f"WGEN amplitude volts: {value}")
            print(f"Command: {command}")
        elif args.command == "wgen-offset":
            if args.query:
                command = wgen_offset_query(capabilities)
                state = scope.query_wgen_offset()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"WGEN offset volts: {state.offset_volts}")
            else:
                value = validate_wgen_offset(args.volts)
                command = wgen_offset_command(value, capabilities)
                scope.configure_wgen_offset(value)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    offset_volts=value,
                    state_changing=True,
                )
                print(f"WGEN offset volts: {value}")
            print(f"Command: {command}")
        else:
            if args.query:
                command = wgen_load_query(capabilities)
                state = scope.query_wgen_load()
                runtime._json_update_result(operation="query", command=command, **state.to_json())
                print(f"WGEN load: {state.load}")
            else:
                command = wgen_load_command(args.load, capabilities)
                scope.configure_wgen_load(args.load)
                runtime._json_update_result(
                    operation="configure",
                    command=command,
                    load=args.load,
                    state_changing=True,
                )
                print(f"WGEN load: {args.load}")
            print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_measure_results(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        result = scope.query_measurement_results()
        items = [
            {"label": item.label, "value": item.value}
            for item in result.items
        ]
        statistics_items = [
            {
                "label": item.label,
                "current": item.current,
                "minimum": item.minimum,
                "maximum": item.maximum,
                "mean": item.mean,
                "stddev": item.stddev,
                "count": item.count,
            }
            for item in result.statistics_items
        ]
        runtime._json_update_result(
            operation="query",
            command=measurement_results_query(),
            raw=result.raw,
            items=items,
            statistics_items=statistics_items,
        )
        print(f"Raw response: {result.raw}")
        if not items:
            print("Parsed items: none")
        else:
            for item in items:
                print(f"{item['label']}: {item['value']}")
        if statistics_items:
            print(f"Parsed statistics items: {len(statistics_items)}")
        return 0


def _cmd_measure_stats(args: argparse.Namespace) -> int:
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
        channel = validate_analog_channel(args.channel, scope.capabilities)
        items = _parse_stats_items(args.items)
        if args.max_count is not None:
            validate_statistics_max_count(args.max_count)
        if args.settle_seconds is not None:
            validate_statistics_settle_seconds(args.settle_seconds)
        print(f"Planned statistics: CH{channel}; items {', '.join(items)}")
        result = scope.query_measurement_statistics(
            channel,
            items,
            mode=args.mode,
            reset=args.reset,
            max_count=args.max_count,
            settle_seconds=args.settle_seconds,
        )
        runtime._json_update_result(**_measurement_statistics_json(result))
        for command in _measure_stats_planned_scpi(
            channel,
            items,
            args.mode,
            reset=args.reset,
            max_count=args.max_count,
        ):
            print(f"Command: {command}")
        for record in result.records:
            print(
                f"{record.item}: current={_format_optional_number(record.current)}, "
                f"min={_format_optional_number(record.minimum)}, "
                f"max={_format_optional_number(record.maximum)}, "
                f"mean={_format_optional_number(record.mean)}, "
                f"stddev={_format_optional_number(record.stddev)}, "
                f"count={record.count}"
            )
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_cursor(args: argparse.Namespace) -> int:
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
        if args.cursor_query:
            state = scope.query_cursor()
            runtime._json_update_result(operation="query", **state.__dict__)
            for command in _cursor_query_commands():
                print(f"Command: {command}")
            print(f"Mode: {state.mode}")
            print(f"X delta s: {state.x_delta_seconds:.12g}")
            print(f"Y delta V: {state.y_delta_volts:.12g}")
        elif args.cursor_off:
            scope.cursor_off()
            runtime._json_update_result(operation="off", command=":MARKer:MODE OFF")
            print("Command: :MARKer:MODE OFF")
        else:
            if args.source_channel is None or args.x2 is None:
                raise OscilloscopeError("cursor configure requires --source-channel, --x1, and --x2")
            channel = validate_analog_channel(args.source_channel, scope.capabilities)
            if getattr(args, "auto_vertical", False) and args.y1 is None and args.y2 is None:
                raise ParameterValidationError("--auto-vertical requires --y1 or --y2.")
            cursor_configure_commands(
                channel,
                args.x1,
                args.x2,
                y1_volts=args.y1,
                y2_volts=args.y2,
                capabilities=scope.capabilities,
            )
            auto_timebase = None
            if getattr(args, "auto_timebase", False):
                scale = scope.query_timebase_scale()
                position = scope.query_timebase_position()
                auto_timebase = cursor_auto_timebase_plan(scale, position, args.x1, args.x2)
                for command in (timebase_scale_query(), timebase_position_query()):
                    print(f"Command: {command}")
                if auto_timebase.changed and auto_timebase.target_scale_seconds_per_division is not None:
                    scope.set_timebase_scale(auto_timebase.target_scale_seconds_per_division)
                    print(
                        "Command: "
                        f"{timebase_scale_command(auto_timebase.target_scale_seconds_per_division)}"
                    )
            auto_vertical = None
            if getattr(args, "auto_vertical", False):
                scale = scope.query_channel_scale(channel)
                offset = scope.query_channel_offset(channel)
                auto_vertical = cursor_auto_vertical_plan(
                    channel,
                    scale,
                    offset,
                    y1_volts=args.y1,
                    y2_volts=args.y2,
                    capabilities=scope.capabilities,
                )
                for command in (channel_scale_query(channel), channel_offset_query(channel)):
                    print(f"Command: {command}")
                if auto_vertical.changed:
                    assert auto_vertical.target_scale_volts_per_division is not None
                    assert auto_vertical.target_offset_volts is not None
                    scope.set_channel_scale(
                        channel,
                        auto_vertical.target_scale_volts_per_division,
                    )
                    print(
                        "Command: "
                        f"{channel_scale_command(channel, auto_vertical.target_scale_volts_per_division)}"
                    )
                    if auto_vertical.offset_changed:
                        scope.set_channel_offset(channel, auto_vertical.target_offset_volts)
                        print(
                            "Command: "
                            f"{channel_offset_command(channel, auto_vertical.target_offset_volts)}"
                        )
            scope.configure_cursor(channel, args.x1, args.x2, y1_volts=args.y1, y2_volts=args.y2)
            commands = cursor_configure_commands(
                channel,
                args.x1,
                args.x2,
                y1_volts=args.y1,
                y2_volts=args.y2,
                capabilities=scope.capabilities,
            )
            result = {
                "operation": "set",
                "commands": commands,
                "source_channel": channel,
                "x1_seconds": args.x1,
                "x2_seconds": args.x2,
                "y1_volts": args.y1,
                "y2_volts": args.y2,
            }
            if auto_timebase is not None:
                result["auto_timebase"] = cursor_auto_timebase_json(auto_timebase)
            if auto_vertical is not None:
                result["auto_vertical"] = cursor_auto_vertical_json(auto_vertical)
            runtime._json_update_result(**result)
            for command in commands:
                print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        diagnostic = _cursor_range_diagnostic(args, entry)
        if diagnostic is not None:
            runtime._json_update_result(diagnostic=diagnostic)
            print(f"Diagnostic: {diagnostic}")
        return 1 if entry.is_error else 0


def _cmd_fft(args: argparse.Namespace) -> int:
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
        if args.fft_query:
            state = scope.query_fft(args.function)
            runtime._json_update_result(
                operation="query",
                function=state.function,
                fft_operation=state.operation,
                fft_operation_canonical=state.operation_canonical,
                source_channel=state.source_channel,
                units=state.units,
                window=state.window,
                center_hz=state.center_hz,
                span_hz=state.span_hz,
                display=state.display,
                start_hz=state.start_hz,
                stop_hz=state.stop_hz,
                gate=state.gate,
                phase_reference=state.phase_reference,
                detection_type=state.detection_type,
                detection_points=state.detection_points,
                bin_size_hz=state.bin_size_hz,
                sample_rate_hz=state.sample_rate_hz,
                resolution_bandwidth_hz=state.resolution_bandwidth_hz,
            )
            commands = fft_query_commands(
                args.function, capabilities=scope.capabilities
            )
            if scope.capabilities.supports_advanced_fft:
                commands += fft_advanced_query_commands(
                    args.function,
                    include_phase_reference=(
                        state.operation_canonical == "fft-phase"
                    ),
                    capabilities=scope.capabilities,
                )
            for command in commands:
                print(f"Command: {command}")
            print(f"Function: {state.function}")
            print(f"Source: CH{state.source_channel}")
        else:
            assert args.source_channel is not None
            display = None if args.display is None else args.display == "on"
            fft_operation = args.fft_operation or "fft"
            scope.configure_fft(
                args.function,
                args.source_channel,
                units=args.units,
                window=args.window,
                center_hz=args.center_hz,
                span_hz=args.span_hz,
                display=display,
                fft_operation=fft_operation,
                start_hz=args.start_hz,
                stop_hz=args.stop_hz,
                gate=args.gate,
                phase_reference=args.phase_reference,
                detection_type=args.detection_type,
                detection_points=args.detection_points,
            )
            commands = fft_configure_commands(
                args.function,
                args.source_channel,
                units=args.units,
                window=args.window,
                center_hz=args.center_hz,
                span_hz=args.span_hz,
                display=display,
                fft_operation=fft_operation,
                start_hz=args.start_hz,
                stop_hz=args.stop_hz,
                gate=args.gate,
                phase_reference=args.phase_reference,
                detection_type=args.detection_type,
                detection_points=args.detection_points,
                capabilities=scope.capabilities,
            )
            runtime._json_update_result(
                operation="set",
                commands=commands,
                function=args.function,
                source_channel=args.source_channel,
                fft_operation_canonical=fft_operation,
                units=args.units,
                window=args.window,
                center_hz=args.center_hz,
                span_hz=args.span_hz,
                start_hz=args.start_hz,
                stop_hz=args.stop_hz,
                gate=args.gate,
                phase_reference=args.phase_reference,
                detection_type=args.detection_type,
                detection_points=args.detection_points,
                display=args.display,
            )
            for command in commands:
                print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_math_display(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        if args.math_display_action == "query":
            state = scope.query_math_display(args.function)
            runtime._json_update_result(
                operation="query",
                function=state.function,
                enabled=state.enabled,
                raw=state.raw,
            )
            print(
                f"Command: {math_display_query(args.function, capabilities=scope.capabilities)}"
            )
            print(f"Math display: {'ON' if state.enabled else 'OFF'}")
        else:
            enabled = args.math_display_action == "on"
            scope.configure_math_display(args.function, enabled)
            command = math_display_command(
                args.function, enabled, capabilities=scope.capabilities
            )
            runtime._json_update_result(
                operation="set",
                function=args.function,
                enabled=enabled,
                command=command,
            )
            print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_math_vertical(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        if args.math_vertical_query:
            state = scope.query_math_vertical(args.function)
            runtime._json_update_result(
                operation="query",
                function=state.function,
                scale=state.scale,
                range=state.range,
                offset=state.offset,
            )
            commands = math_vertical_query_commands(
                args.function, capabilities=scope.capabilities
            )
            for command in commands:
                print(f"Command: {command}")
            print(f"Scale: {state.scale:.12g}")
            print(f"Range: {state.range:.12g}")
            print(f"Offset: {state.offset:.12g}")
        else:
            scope.configure_math_vertical(
                args.function,
                scale=args.scale,
                range_value=args.range_value,
                offset=args.offset,
            )
            commands = math_vertical_commands(
                args.function,
                scale=args.scale,
                range_value=args.range_value,
                offset=args.offset,
                capabilities=scope.capabilities,
            )
            runtime._json_update_result(
                operation="set",
                function=args.function,
                scale=args.scale,
                range=args.range_value,
                offset=args.offset,
                commands=commands,
            )
            for command in commands:
                print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_math_operator(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        if args.math_operator_query:
            state = scope.query_math_operator(args.function)
            runtime._json_update_result(
                operation="query",
                function=state.function,
                math_operation=state.operation,
                operation_raw=state.operation_raw,
                source1=state.source1,
                source1_raw=state.source1_raw,
                source2=state.source2,
                source2_raw=state.source2_raw,
            )
            commands = math_operator_query_commands(
                args.function, capabilities=scope.capabilities
            )
            for command in commands:
                print(f"Command: {command}")
            print(f"Math operation: {state.operation}")
            print(f"Source 1: {state.source1}")
            print(f"Source 2: {state.source2}")
        else:
            scope.configure_math_operator(
                args.function,
                args.math_operation,
                args.source1,
                args.source2,
            )
            commands = math_operator_commands(
                args.function,
                args.math_operation,
                args.source1,
                args.source2,
                capabilities=scope.capabilities,
            )
            runtime._json_update_result(
                operation="set",
                function=args.function,
                math_operation=args.math_operation,
                source1=args.source1,
                source2=args.source2,
                commands=commands,
            )
            for command in commands:
                print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_math_composite_source(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        if args.math_composite_query:
            state = scope.query_math_composite_source()
            runtime._json_update_result(
                operation="query",
                math_operation=state.operation,
                operation_raw=state.operation_raw,
                source1=state.source1,
                source1_raw=state.source1_raw,
                source2=state.source2,
                source2_raw=state.source2_raw,
            )
            commands = math_composite_source_query_commands(
                capabilities=scope.capabilities
            )
            for command in commands:
                print(f"Command: {command}")
            print(f"Composite operation: {state.operation}")
            print(f"Source 1: {state.source1}")
            print(f"Source 2: {state.source2}")
        else:
            scope.configure_math_composite_source(
                args.math_composite_operation,
                args.source1,
                args.source2,
            )
            commands = math_composite_source_commands(
                args.math_composite_operation,
                args.source1,
                args.source2,
                capabilities=scope.capabilities,
            )
            runtime._json_update_result(
                operation="set",
                math_operation=args.math_composite_operation,
                source1=args.source1,
                source2=args.source2,
                commands=commands,
            )
            for command in commands:
                print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_math_transform(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        if args.math_transform_query:
            state = scope.query_math_transform(args.function)
            runtime._json_update_result(
                operation="query",
                function=state.function,
                math_operation=state.operation,
                operation_raw=state.operation_raw,
                source=state.source,
                source_raw=state.source_raw,
                input_offset=state.input_offset,
                gain=state.gain,
                linear_offset=state.linear_offset,
            )
            commands = math_transform_query_commands(
                args.function, capabilities=scope.capabilities
            )
            for command in commands:
                print(f"Command: {command}")
            print(f"Math transform: {state.operation}")
            print(f"Source: {state.source}")
            if state.input_offset is not None:
                print(f"Input offset: {state.input_offset:.12g}")
            if state.gain is not None:
                print(f"Gain: {state.gain:.12g}")
            if state.linear_offset is not None:
                print(f"Linear offset: {state.linear_offset:.12g}")
        else:
            scope.configure_math_transform(
                args.function,
                args.math_transform_operation,
                args.source,
                input_offset=args.input_offset,
                gain=args.gain,
                linear_offset=args.linear_offset,
            )
            commands = math_transform_commands(
                args.function,
                args.math_transform_operation,
                args.source,
                input_offset=args.input_offset,
                gain=args.gain,
                linear_offset=args.linear_offset,
                capabilities=scope.capabilities,
            )
            runtime._json_update_result(
                operation="set",
                function=args.function,
                math_operation=args.math_transform_operation,
                source=args.source,
                input_offset=args.input_offset,
                gain=args.gain,
                linear_offset=args.linear_offset,
                commands=commands,
            )
            for command in commands:
                print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_math_filter(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        if args.math_filter_query:
            state = scope.query_math_filter(args.function)
            runtime._json_update_result(
                operation="query",
                function=state.function,
                math_operation=state.operation,
                operation_raw=state.operation_raw,
                source=state.source,
                source_raw=state.source_raw,
                cutoff_hz=state.cutoff_hz,
                average_count=state.average_count,
                smooth_points=state.smooth_points,
            )
            commands = math_filter_query_commands(
                args.function, capabilities=scope.capabilities
            )
            for command in commands:
                print(f"Command: {command}")
            print(f"Math filter: {state.operation}")
            print(f"Source: {state.source}")
            if state.cutoff_hz is not None:
                print(f"Cutoff: {state.cutoff_hz:.12g} Hz")
            if state.average_count is not None:
                print(f"Average count: {state.average_count}")
            if state.smooth_points is not None:
                print(f"Smooth points: {state.smooth_points}")
        else:
            scope.configure_math_filter(
                args.function,
                args.math_filter_operation,
                args.source,
                cutoff_hz=args.cutoff_hz,
                average_count=args.average_count,
                smooth_points=args.smooth_points,
            )
            commands = math_filter_commands(
                args.function,
                args.math_filter_operation,
                args.source,
                cutoff_hz=args.cutoff_hz,
                average_count=args.average_count,
                smooth_points=args.smooth_points,
                capabilities=scope.capabilities,
            )
            runtime._json_update_result(
                operation="set",
                function=args.function,
                math_operation=args.math_filter_operation,
                source=args.source,
                cutoff_hz=args.cutoff_hz,
                average_count=args.average_count,
                smooth_points=args.smooth_points,
                commands=commands,
            )
            for command in commands:
                print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_math_visualization(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        if args.math_visualization_query:
            state = scope.query_math_visualization(args.function)
            runtime._json_update_result(
                operation="query",
                function=state.function,
                math_operation=state.operation,
                operation_raw=state.operation_raw,
                source=state.source,
                source_raw=state.source_raw,
                source2=state.source2,
                source2_raw=state.source2_raw,
                measurement=state.measurement,
                measurement_raw=state.measurement_raw,
                measurement_slot=state.measurement_slot,
            )
            print(f"Math visualization: {state.operation}")
            if state.source is not None:
                print(f"Source: {state.source}")
            if state.source2 is not None:
                print(f"Source 2: {state.source2}")
            if state.measurement is not None:
                print(f"Trend measurement: {state.measurement}")
            if state.measurement_slot is not None:
                print(f"Trend measurement slot: {state.measurement_slot}")
        else:
            scope.configure_math_visualization(
                args.function,
                args.math_visualization_operation,
                source=args.source,
                source2=args.source2,
                measurement=args.measurement,
                measurement_slot=args.measurement_slot,
            )
            commands = math_visualization_commands(
                args.function,
                args.math_visualization_operation,
                source=args.source,
                source2=args.source2,
                measurement=args.measurement,
                measurement_slot=args.measurement_slot,
                capabilities=scope.capabilities,
            )
            runtime._json_update_result(
                operation="set",
                function=args.function,
                math_operation=args.math_visualization_operation,
                source=args.source,
                source2=args.source2,
                measurement=args.measurement,
                measurement_slot=args.measurement_slot,
                commands=commands,
            )
            for command in commands:
                print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_math_clear(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2
    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        scope.clear_math(args.function)
        command = math_clear_command(
            args.function, capabilities=scope.capabilities
        )
        runtime._json_update_result(
            operation="clear",
            function=args.function,
            cleared=True,
            command=command,
        )
        print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _format_optional_number(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.12g}"


def _parse_stats_items(value: str) -> tuple[str, ...]:
    items = tuple(token.strip() for token in value.split(",") if token.strip())
    try:
        return validate_statistics_items(items)
    except OscilloscopeError:
        raise
