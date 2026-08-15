from __future__ import annotations

import argparse

from scopes_tool_core.acquisition import (
    acquisition_count_command,
    acquisition_count_query,
    acquisition_points_query,
    acquisition_type_command,
    acquisition_type_query,
    normalize_acquisition_type,
    parse_acquisition_points,
    parse_record_length,
    parse_sample_rate,
    record_length_query,
    sample_rate_maximum_query,
    sample_rate_query,
    validate_acquisition_count,
)
from scopes_tool_core.errors import OscilloscopeError

from .. import runtime


def _sample_rate_query_command(args: argparse.Namespace) -> str:
    if getattr(args, "sample_rate_maximum", False):
        return sample_rate_maximum_query()
    return sample_rate_query()


def _cmd_sample_rate(args: argparse.Namespace) -> int:
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

        query_command = _sample_rate_query_command(args)
        if getattr(args, "sample_rate_maximum", False):
            print("Planned query: maximum analog acquisition sample rate")
        else:
            print("Planned query: analog acquisition sample rate")
        raw = scope.scpi.query(query_command)
        sample_rate_hz = parse_sample_rate(raw)
        print("Command: " + query_command)
        if getattr(args, "sample_rate_maximum", False):
            print("Maximum sample rate: " + f"{sample_rate_hz:.6e}" + " Hz")
        else:
            print("Sample rate: " + f"{sample_rate_hz:.6e}" + " Hz")
        print("Raw value: " + raw.strip())
        result = {
            "operation": "query",
            "raw_value": raw.strip(),
            "unit": "Hz",
            "scpi_command": query_command,
        }
        if getattr(args, "sample_rate_maximum", False):
            result["query_kind"] = "maximum"
            result["maximum_sample_rate_hz"] = sample_rate_hz
        else:
            result["sample_rate_hz"] = sample_rate_hz
        runtime._json_update_result(**result)
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print("System error: " + entry.format())
        return 1 if entry.is_error else 0


def _cmd_segmented_memory(args: argparse.Namespace) -> int:
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
        if args.query:
            query_result = scope.query_segmented_memory()
            result = query_result.to_json()
            result["operation"] = "query"
            runtime._json_update_result(**result)
            print("Planned query: segmented memory state")
            print("Mode: " + query_result.mode)
            print("Configured segments: " + str(query_result.configured_segments))
            print("Acquired segments: " + str(query_result.acquired_segments))
            print("Selected segment: " + str(query_result.selected_segment))
            print("Time tag (s): " + str(query_result.time_tag_s))
        elif args.enable:
            scope.enable_segmented_memory(args.segments)
            runtime._json_update_result(
                operation="enable",
                mode="segmented",
                configured_segments=args.segments,
            )
            print(f"Configured segmented memory with {args.segments} segments")
        else:
            scope.disable_segmented_memory()
            runtime._json_update_result(
                operation="disable",
                mode="realtime",
                configured_segments=None,
            )
            print("Disabled segmented memory")
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print("System error: " + entry.format())
        return 1 if entry.is_error else 0


def _cmd_acquisition_points(args: argparse.Namespace) -> int:
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

        print("Planned query: analog acquisition points")
        raw = scope.scpi.query(acquisition_points_query())
        acquisition_points = parse_acquisition_points(raw)
        print("Command: " + acquisition_points_query())
        print("Acquisition points: " + str(acquisition_points) + " points")
        print("Raw value: " + raw.strip())
        runtime._json_update_result(
            operation="query",
            acquisition_points=acquisition_points,
            raw_value=raw.strip(),
            unit="points",
            scpi_command=acquisition_points_query(),
        )
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print("System error: " + entry.format())
        return 1 if entry.is_error else 0


def _cmd_record_length(args: argparse.Namespace) -> int:
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

        print("Planned query: analog acquisition record length")
        raw = scope.scpi.query(record_length_query())
        record_length_points = parse_record_length(raw)
        print("Command: " + record_length_query())
        print("Record length: " + str(record_length_points) + " points")
        print("Raw value: " + raw.strip())
        runtime._json_update_result(
            operation="query",
            record_length_points=record_length_points,
            raw_value=raw.strip(),
            unit="points",
            scpi_command=record_length_query(),
        )
        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print("System error: " + entry.format())
        return 1 if entry.is_error else 0


def _cmd_acquisition(args: argparse.Namespace) -> int:
    resource = runtime._require_resource(args)
    if resource is None:
        return 2

    runtime._configure_scpi_logging(args)
    if args.acq_query and (args.acq_type is not None or args.acq_count is not None):
        raise OscilloscopeError("--query cannot be combined with --type or --count")

    if args.acq_count is not None:
        if args.acq_type is None:
            raise OscilloscopeError("--count can only be used with --type average")
        if normalize_acquisition_type(args.acq_type) != "AVERage":
            raise OscilloscopeError("--count can only be used with --type average")

    with runtime._open_scope(args, resource) as scope:
        idn = scope.query_idn()
        runtime._json_record_scope(scope, idn)
        runtime._print_session_header(scope, resource)
        print(f"Model: {idn.model}")
        print(f"Series: {idn.series or 'unknown'}")
        if scope.capabilities is None:
            print("Capabilities: unavailable for this model")
            return 1

        if args.acq_query:
            print("Planned query: acquisition type and average count")
            config = scope.query_acquisition_config()
            runtime._json_update_result(operation="query", type=config.type, count=config.count, commands=[acquisition_type_query(), acquisition_count_query()])
            print(f"Acquisition type: {config.type}")
            print(f"Average count: {config.count}")
            print(f"Command: {acquisition_type_query()}")
            print(f"Command: {acquisition_count_query()}")
        elif args.acq_type is not None:
            normalized_type = normalize_acquisition_type(args.acq_type)
            print(f"Planned change: acquisition type {args.acq_type}")
            print(f"Command: {acquisition_type_command(normalized_type)}")
            scope.set_acquisition_type(args.acq_type)
            runtime._json_update_result(operation="set", type=args.acq_type, scpi_type=normalized_type, count=None, commands=[acquisition_type_command(normalized_type)])
            if args.acq_count is not None:
                validated_count = validate_acquisition_count(args.acq_count)
                print(f"Planned change: acquisition average count {validated_count}")
                print(f"Command: {acquisition_count_command(validated_count)}")
                scope.set_acquisition_count(validated_count)
                runtime._json_update_result(operation="set", type=args.acq_type, scpi_type=normalized_type, count=validated_count, commands=[acquisition_type_command(normalized_type), acquisition_count_command(validated_count)])
        else:
            raise OscilloscopeError("acquisition command requires --query or --type")

        entry = scope.query_system_error()
        runtime._json_record_system_error(entry)
        print(f"System error: {entry.format()}")
        return 1 if entry.is_error else 0
