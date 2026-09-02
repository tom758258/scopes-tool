from __future__ import annotations

import argparse

from scopes_tool_core.capabilities import ScopeCapabilities
from scopes_tool_core.status import (
    system_clear_status_command,
    system_opc_query,
    system_operation_status_query,
    system_options_query,
    system_standard_event_query,
    system_status_byte_query,
)
from scopes_tool_core.trigger import TriggerWaitConfig, force_trigger_command
from scopes_tool_core.workflow import StopRequested

from .. import runtime


_CONTROL_COMMANDS = {
    "run": ("run", ":RUN"),
    "stop-acquisition": ("stop", ":STOP"),
    "single": ("single", ":SINGle"),
}


def _cmd_verify(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._json_update_result(idn=runtime._idn_object_json(idn), capabilities=runtime._capabilities_json(scope.capabilities), **runtime._scope_backend_json(scope))
        runtime._print_session_header(scope, resource)
        print(f"Raw IDN: {idn.raw}")
        print(f"Vendor: {idn.vendor}")
        print(f"Model: {idn.model}")
        print(f"Serial: {idn.serial}")
        print(f"Firmware: {idn.firmware}")
        print(f"Series: {idn.series or 'unknown'}")
        _print_capabilities(scope.capabilities)
    return 0


def _cmd_check_error(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        runtime._print_session_header(scope, resource)
        if args.drain:
            entries = scope.drain_system_errors(max_reads=args.max_reads)
            entry_json = [runtime._system_error_json(entry) for entry in entries]
            runtime._json_update_result(drain=True, max_reads=args.max_reads, entries=entry_json)
            if entries:
                runtime._json_record_system_error(entries[-1])
            for index, entry in enumerate(entries, start=1):
                print(f"System error {index}: {entry.format()}")
            return 1 if any(entry.is_error for entry in entries) else 0

        entry = scope.query_system_error()
        runtime._json_update_result(drain=False, max_reads=1, entries=[runtime._system_error_json(entry)])
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_control(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)
    method_name, command = _CONTROL_COMMANDS[args.command]

    with runtime._open_scope(args, resource) as scope:
        runtime._print_session_header(scope, resource)
        getattr(scope, method_name)()
        runtime._json_update_result(action=method_name, command=command)
        print(f"Command: {command}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_cleanup(args: argparse.Namespace) -> int:
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

        result = scope.cleanup(args.profile)
        runtime._json_update_result(**result.to_json())
        runtime._json_record_system_error(result.final_error)
        print(
            f"Cleanup {result.profile}: {len(result.actions)} actions, "
            f"{len(result.skipped)} skipped; "
            f"final error queue clean: {result.final_error_queue_clean}"
        )
        return 0 if result.final_error_queue_clean else 1


def _cmd_system_status(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)
    with runtime._open_scope(args, resource) as scope:
        runtime._print_session_header(scope, resource)
        if args.command == "system-clear-status":
            command = system_clear_status_command()
            scope.clear_status()
            runtime._json_update_result(operation="clear", command=command, cleared=True)
            print("Status cleared: true")
        elif args.command == "system-opc":
            command = system_opc_query()
            state = scope.query_operation_complete()
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Operation complete: {state.complete}")
        elif args.command == "system-status-byte":
            command = system_status_byte_query()
            state = scope.query_status_byte()
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Status byte: {state.value}")
        elif args.command == "system-standard-event":
            command = system_standard_event_query()
            state = scope.query_standard_event_status()
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Standard event status: {state.value}")
        elif args.command == "system-operation-status":
            command = system_operation_status_query()
            state = scope.query_operation_status()
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"Operation condition status: {state.value}")
        else:
            command = system_options_query()
            state = scope.query_system_options()
            runtime._json_update_result(operation="query", command=command, **state.to_json())
            print(f"System options: {', '.join(state.options)}")
        print(f"Command: {command}")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0


def _cmd_force_trigger(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)

    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        print("Series: " + (idn.series or "unknown"))
        if scope.capabilities is None:
            print("Capabilities: unavailable for this model")
            return 1

        print("Planned change: force one trigger event")
        scope.force_trigger()
        runtime._json_update_result(
            operation="force-trigger",
            forced=True,
            scpi_command=force_trigger_command(),
        )
        print("Command: " + force_trigger_command())
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print("System error: " + entry.format())
        return 1 if entry.is_error else 0


def _cmd_single_wait(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)
    config = TriggerWaitConfig(
        timeout_ms=args.trigger_timeout_ms,
        poll_interval_ms=args.trigger_poll_interval_ms,
        force_on_timeout=args.force_trigger_on_timeout,
    )

    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        result = scope.single_wait(config, stop_requested=stop_requested)
        runtime._json_update_result(operation="single-wait", **result.to_json(config))
        print(f"Trigger wait outcome: {result.outcome}")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 0 if not entry.is_error and result.outcome in {"natural", "forced"} else 1


def _print_capabilities(capabilities: ScopeCapabilities | None) -> None:
    if capabilities is None:
        print("Capabilities: unavailable for this model")
        return

    print(f"Analog channels: {capabilities.analog_channels}")
    print(f"Default waveform points: {capabilities.default_waveform_points}")
    print(f"Safe max waveform points: {capabilities.safe_max_waveform_points}")
