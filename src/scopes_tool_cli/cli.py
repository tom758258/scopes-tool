"""Command line interface for oscilloscope checks."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from scopes_tool_core.capabilities import (
    ScopeCapabilities,
    capabilities_for_model_id,
    operation_supported,
)
from scopes_tool_core.cleanup import plan_cleanup
from scopes_tool_core.drivers import driver_for_physical_model
from scopes_tool_core.errors import (
    OscilloscopeError,
    ParameterValidationError,
)
from scopes_tool_core.identity import physical_model_for_id
from scopes_tool_core.idn import parse_idn
from scopes_tool_core.planning import (
    plan_doctor,
)
from scopes_tool_core.scope import Oscilloscope
from scopes_tool_core.simulator_backend import simulator_idn
from scopes_tool_core.status import (
    system_clear_status_command,
    system_opc_query,
    system_operation_status_query,
    system_options_query,
    system_standard_event_query,
    system_status_byte_query,
)
from scopes_tool_core.trigger import (
    operation_condition_query,
)
from scopes_tool_core.visa_backend import (
    is_asrl_resource,
    list_visa_resources,
    verify_asrl_resource_live,
)
from scopes_tool_core.workflow import StopRequested

from . import dispatch as cli_dispatch
from . import parser as cli_parser
from . import preflight, runtime
from ._dry_run_acquisition_math import _plan_acquisition_math
from ._dry_run_channel_analysis import _plan_channel_analysis
from ._dry_run_serial_search import _plan_serial_search
from ._dry_run_trigger import _plan_trigger
from ._dry_run_workflows import _plan_workflows
from .commands import (
    introspection,
    system,
    workflows,
)
CLI_SCHEMA_VERSION = 2


def main(argv: Sequence[str] | None = None) -> int:
    """Run the `scopes-tool` command line interface."""

    parser = cli_parser._build_parser()
    args = parser.parse_args(argv)

    try:
        preflight.validate_pre_open_args(args)
    except OscilloscopeError as exc:
        if getattr(args, "json_output", False):
            payload = _json_envelope(args, ok=False, mode=_safe_mode(args))
            payload["error"] = _json_error(exc)
            _write_json(payload)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "lifecycle_command", False):
        try:
            from .worker import dispatch_lifecycle_command

            return dispatch_lifecycle_command(args)
        except OscilloscopeError as exc:
            if getattr(args, "client_json", False):
                _write_json(
                    {
                        "schema_version": CLI_SCHEMA_VERSION,
                        "timestamp_utc": _utc_timestamp(),
                        "ok": False,
                        "status": "error",
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    }
                )
            else:
                print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.command == "manifest":
        return introspection.cmd_manifest(args)

    if args.command == "capabilities":
        return introspection.cmd_capabilities(args)

    if getattr(args, "json_output", False):
        return _run_json_command(args)

    try:
        if runtime._resolve_cli_mode(args) == "dry_run":
            return _run_text_dry_run_command(args)
        return _dispatch_command(args)
    except OscilloscopeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error("missing command")
    return 2



def _dispatch_command(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> int:
    if args.command == "list-resources":
        return _cmd_list_resources(args)
    if args.command == "hardware-report":
        return _cmd_hardware_report(args)
    return cli_dispatch._dispatch_command(
        args,
        stop_requested=stop_requested,
    )

def _run_json_command(args: argparse.Namespace) -> int:
    payload, code = _execute_json_command(args)
    _write_json(payload)
    return code


def _execute_json_command(
    args: argparse.Namespace,
    *,
    stop_requested: StopRequested | None = None,
) -> tuple[dict[str, object], int]:
    try:
        mode = runtime._resolve_cli_mode(args)
        if mode == "dry_run":
            payload = _dry_run_payload(args)
            return payload, 0

        runtime._JSON_RECORD = {"result": {}, "files": [], "system_error": None}
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = _dispatch_command(args, stop_requested=stop_requested)
        payload = _json_envelope(args, ok=(code == 0), mode=mode)
        _apply_json_record(payload)
        result = payload.setdefault("result", {})
        if isinstance(result, dict):
            result["human_output"] = buffer.getvalue().splitlines()
        payload["scpi"]["sent"] = runtime._backend_history()
        return payload, code
    except OscilloscopeError as exc:
        payload = _json_envelope(args, ok=False, mode=_safe_mode(args))
        _apply_json_record(payload)
        payload["error"] = _json_error(exc)
        payload["scpi"]["sent"] = runtime._backend_history()
        return payload, 3 if payload["error"].get("type") == "identity_mismatch" else 1
    finally:
        runtime._JSON_RECORD = None


def _run_text_dry_run_command(args: argparse.Namespace) -> int:
    payload = _dry_run_payload(args)
    _print_text_dry_run_payload(payload)
    return 0


def _print_text_dry_run_payload(payload: dict[str, object]) -> None:
    resource = payload.get("resource")
    if resource is not None:
        print(f"Resource: {resource}")

    idn = payload.get("idn")
    if isinstance(idn, dict):
        model = idn.get("model")
        series = idn.get("series")
        if model is not None:
            print(f"Model: {model}")
        print(f"Series: {series or 'unknown'}")

    result = payload.get("result")
    if isinstance(result, dict):
        _print_text_dry_run_summary(str(payload.get("command")), result)
        commands = result.get("commands")
        if not isinstance(commands, list):
            command = result.get("command")
            commands = [command] if isinstance(command, str) else None
    else:
        commands = None

    if not isinstance(commands, list):
        scpi = payload.get("scpi")
        if isinstance(scpi, dict):
            commands = scpi.get("planned")

    if isinstance(commands, list):
        for command in commands:
            print(f"Command: {command}")

    files = payload.get("files")
    if isinstance(files, list):
        for file_info in files:
            if isinstance(file_info, dict):
                kind = file_info.get("kind")
                path = file_info.get("path")
                if kind is not None and path is not None:
                    print(f"Planned file: {kind}: {path}")


def _print_text_dry_run_summary(command: str, result: dict[str, object]) -> None:
    if command == "capture-until":
        print(
            "Planned capture until condition: "
            f"CH{result.get('condition_channel')} {result.get('metric')} "
            f"{result.get('operator')} {result.get('threshold')}"
        )
        return
    if command == "capture-monitor":
        print(
            "Planned capture monitor: "
            f"{result.get('requested_count')} capture(s), "
            f"{result.get('retention_points')} retained points per channel"
        )
        return
    if command == "measure-until":
        print(
            "Planned measure until condition: "
            f"CH{result.get('channel')} {result.get('item')} "
            f"{result.get('operator')} {result.get('threshold')}"
        )
        return
    if command == "triggered-capture-series":
        print(
            "Planned triggered capture series: "
            f"{result.get('requested_count')} cycle(s)"
        )
        return
    if command == "triggered-measure-loop":
        print(
            "Planned triggered measurement loop: "
            f"{result.get('requested_count')} cycle(s)"
        )
        return
    if command == "sequence":
        print(
            "Planned sequence: "
            f"{result.get('loop_count')} loop(s), "
            f"{result.get('step_count')} step(s), "
            f"{result.get('total_step_executions')} execution(s)"
        )
        steps = result.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    print(
                        f"Planned step {step.get('step_index')}: "
                        f"{step.get('action')} {step.get('parameters')}"
                    )
        return
    operation = result.get("operation")
    if command == "trigger-edge-burst":
        if operation == "query":
            print("Planned query: Nth Edge Burst trigger state")
            return
        source_channel = result.get("source_channel")
        slope = result.get("slope")
        count = result.get("count")
        print(
            f"Planned change: Nth Edge Burst trigger CH{source_channel}, "
            f"{slope}, count {count}"
        )
        return

    if operation == "query":
        print(f"Planned query: {command}")
    elif operation is not None:
        print(f"Planned change: {command}")
    else:
        print(f"Planned command: {command}")


def _safe_mode(args: argparse.Namespace) -> str:
    try:
        return runtime._resolve_cli_mode(args)
    except OscilloscopeError:
        return "dry_run" if getattr(args, "dry_run", False) else "simulate" if getattr(args, "simulate", False) else "live"


def _json_error(exc: OscilloscopeError) -> dict[str, object]:
    message = str(exc)
    if message.startswith("identity_mismatch: "):
        details = {"type": "identity_mismatch", "message": message}
        for item in message.removeprefix("identity_mismatch: ").split("; "):
            key, _, value = item.partition("=")
            if key == "expected_model":
                details["expected_model"] = value
            elif key == "actual_idn":
                details["actual_idn"] = value
        return details
    return {"type": type(exc).__name__, "message": message}


def _json_envelope(args: argparse.Namespace, *, ok: bool, mode: str) -> dict[str, object]:
    resource = None
    if hasattr(args, "resource"):
        resource = args.resource or (f"SIM::{args.model}::INSTR" if mode == "simulate" else f"DRY::{args.model}::INSTR" if mode == "dry_run" else os.environ.get("SCOPES_TOOL_RESOURCE"))
    idn = None
    capabilities = None
    if mode in {"simulate", "dry_run"} and hasattr(args, "model"):
        try:
            idn = _idn_json(simulator_idn(args.model))
            capabilities = runtime._capabilities_json(capabilities_for_model_id(args.model))
        except OscilloscopeError:
            idn = None
            capabilities = None
    return {
        "schema_version": CLI_SCHEMA_VERSION,
        "timestamp_utc": _utc_timestamp(),
        "ok": ok,
        "command": args.command,
        "mode": mode,
        "resource": resource,
        "backend": None,
        "idn": idn,
        "capabilities": capabilities,
        "scpi": {"planned": [], "sent": []},
        "result": {},
        "files": [],
        "system_error": None,
        "error": None,
    }


def _dry_run_payload(args: argparse.Namespace) -> dict[str, object]:
    payload = _json_envelope(args, ok=True, mode="dry_run")
    capabilities = capabilities_for_model_id(args.model)
    if not operation_supported(capabilities, args.command):
        raise ParameterValidationError(f"{args.command} is unsupported for {args.model}")
    driver = driver_for_physical_model(physical_model_for_id(args.model))
    driver_plan = driver.plan_cli_operation(args, capabilities)
    planned, files, result = driver_plan if driver_plan is not None else _dry_run_plan(args, capabilities)
    payload["scpi"]["planned"] = planned
    payload["files"] = files
    payload["result"] = result
    return payload


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dry_run_plan(args: argparse.Namespace, capabilities: ScopeCapabilities) -> tuple[list[str], list[dict[str, str]], dict[str, object]]:
    command = args.command
    plan = _plan_workflows(args, capabilities)
    if plan is not None:
        return plan
    plan = _plan_channel_analysis(args, capabilities)
    if plan is not None:
        return plan
    plan = _plan_serial_search(args, capabilities)
    if plan is not None:
        return plan
    plan = _plan_trigger(args, capabilities)
    if plan is not None:
        return plan
    plan = _plan_acquisition_math(args, capabilities)
    if plan is not None:
        return plan
    if command == "doctor":
        plan = plan_doctor(capabilities)
        return list(plan.planned_scpi), list(plan.files), plan.result

    if command == "cleanup":
        plan = plan_cleanup(args.profile, capabilities)
        return ["*IDN?", *plan.commands], [], plan.to_json()

    if command == "identify":
        return ["*IDN?"], [], {
            "idn": _idn_json(simulator_idn(args.model)),
            "capabilities": runtime._capabilities_json(capabilities),
            "backend": None,
            "timeout_ms": None,
        }

    if command == "check-error":
        count = args.max_reads if args.drain else 1
        return [":SYSTem:ERRor?"] * count, [], {"drain": bool(args.drain), "max_reads": count, "entries": []}

    if command == "system-clear-status":
        target = system_clear_status_command()
        return [target, ":SYSTem:ERRor?"], [], {
            "operation": "clear",
            "command": target,
            "cleared": True,
        }

    system_queries = {
        "system-opc": system_opc_query,
        "system-status-byte": system_status_byte_query,
        "system-standard-event": system_standard_event_query,
        "system-operation-status": system_operation_status_query,
        "system-options": system_options_query,
    }

    if command in system_queries:
        target = system_queries[command]()
        return [target, ":SYSTem:ERRor?"], [], {
            "operation": "query",
            "command": target,
        }

    if command in system._CONTROL_COMMANDS:
        action, scpi = system._CONTROL_COMMANDS[command]
        return [scpi, ":SYSTem:ERRor?"], [], {"action": action, "command": scpi}

    if command in {
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
        if command == "save-waveform" and args.source_channel is not None:
            raise ParameterValidationError("source_channel is unsupported for this model save-waveform")
        target, result, waits_for_completion = workflows._save_export_plan(args)
        planned = ["*IDN?", target]
        if waits_for_completion:
            planned.append(system_opc_query())
        if command == "save-waveform" and capabilities.series == "4000X":
            planned.append(operation_condition_query())
        planned.append(":SYSTem:ERRor?")
        return planned, [], result
    return [], [], {}

def _idn_json(raw: str) -> dict[str, str | None]:
    idn = parse_idn(raw)
    return {"raw": idn.raw, "vendor": idn.vendor, "model": idn.model, "serial": idn.serial, "firmware": idn.firmware, "series": idn.series}


def _write_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _apply_json_record(payload: dict[str, object]) -> None:
    if runtime._JSON_RECORD is None:
        return
    result = runtime._JSON_RECORD.get("result")
    if isinstance(result, dict):
        payload_result = payload.setdefault("result", {})
        if isinstance(payload_result, dict):
            payload_result.update(result)
    for key in ("idn", "capabilities", "backend", "system_error"):
        if key in runtime._JSON_RECORD:
            payload[key] = runtime._JSON_RECORD[key]
    files = runtime._JSON_RECORD.get("files")
    if isinstance(files, list):
        payload["files"] = files


def _cmd_list_resources(args: argparse.Namespace) -> int:
    listing = list_visa_resources(visa_library=args.visa_library)
    print(f"PyVISA backend: {listing.backend}")
    runtime._json_update_result(
        backend=listing.backend,
        resources=list(listing.resources),
        live_only=bool(args.live_only),
        live_resources=[],
    )
    if runtime._JSON_RECORD is not None:
        runtime._JSON_RECORD["backend"] = listing.backend
    if args.live_only:
        runtime._configure_scpi_logging(args)
        return _print_live_resources(
            listing.resources,
            visa_library=args.visa_library,
            serial_read_termination=args.serial_read_termination,
            serial_write_termination=args.serial_write_termination,
        )

    print("Resources:")
    if not listing.resources:
        print("  <none>")
        return 0

    for resource in listing.resources:
        print(f"  {resource}")
    return 0


def _print_live_resources(
    resources: tuple[str, ...],
    visa_library: str | None,
    *,
    serial_read_termination: str | None = None,
    serial_write_termination: str | None = None,
) -> int:
    print("Live resources:")
    live_count = 0
    live_resources = []
    verification_failures = []
    for resource in resources:
        if is_asrl_resource(resource):
            verification = verify_asrl_resource_live(
                resource,
                visa_library=visa_library,
                serial_read_termination=serial_read_termination,
                serial_write_termination=serial_write_termination,
            )
            if not verification.live or verification.raw_idn is None:
                verification_failures.append(_visa_verification_json(verification))
                continue
            try:
                idn = parse_idn(verification.raw_idn)
            except OscilloscopeError as exc:
                verification_failures.append(
                    _visa_verification_json(verification, detail=str(exc))
                )
                continue
        else:
            try:
                with Oscilloscope.open(resource, visa_library=visa_library) as scope:
                    idn = scope.query_idn()
            except OscilloscopeError:
                continue

        live_count += 1
        idn_json = runtime._idn_object_json(idn, include_model_id=True)
        live_resources.append({
            "resource": resource,
            "model_id": idn_json.pop("model_id"),
            "idn": idn_json,
        })
        print(f"  {resource}")
        print(f"    IDN: {idn.raw}")

    if live_count == 0:
        print("  <none>")
    result_update = {"live_resources": live_resources}
    if verification_failures:
        result_update["verification_failures"] = verification_failures
    runtime._json_update_result(**result_update)
    return 0


def _visa_verification_json(
    verification,
    *,
    detail: str | None = None,
) -> dict[str, object]:
    return {
        "resource": verification.resource,
        "live": verification.live,
        "raw_idn": verification.raw_idn,
        "detail": detail if detail is not None else verification.detail,
    }

def _cmd_hardware_report(args: argparse.Namespace) -> int:
    for index, path_text in enumerate(args.report_paths):
        path = Path(path_text)
        report = _load_report_json(path)
        if index:
            print()
        print(_render_hardware_report(report, path))
    return 0


def _load_report_json(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise OscilloscopeError(
            _format_plain_output_file_error("report JSON", path, exc)
        ) from exc
    except json.JSONDecodeError as exc:
        raise OscilloscopeError(f"could not parse report JSON {path}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise OscilloscopeError(f"report JSON must contain an object: {path}")
    return data


def _render_hardware_report(report: dict[str, object], path: Path) -> str:
    report_type = _detect_hardware_report_type(report)
    lines = [f"# Hardware Report: {path}"]
    lines.append(f"- Type: {report_type}")
    lines.append(f"- Status: {report.get('status')}")
    lines.append(f"- Model: {_report_model(report)}")
    lines.append(f"- Firmware: {_report_firmware(report)}")
    lines.append(f"- Resource: {_report_resource(report)}")
    lines.append(f"- Backend: {_report_backend(report)}")
    lines.append("")
    lines.append("## Commands")
    for command in _report_commands(report):
        lines.append(f"- {command}")
    lines.append("")
    lines.append("## Output Files")
    for kind, file_path in _report_files(report):
        lines.append(f"- {kind}: {file_path}")
    lines.append("")
    lines.append("## Result")
    lines.extend(_render_report_result(report))
    errors = _report_errors(report)
    if errors:
        lines.append("")
        lines.append("## Errors")
        lines.extend(errors)
    cleanup = _report_cleanup(report)
    if cleanup:
        lines.append("")
        lines.append("## Cleanup")
        lines.extend(cleanup)
    return "\n".join(lines)


def _detect_hardware_report_type(report: dict[str, object]) -> str:
    if "doctor" in report or "capture" in report or "screenshot" in report:
        return "smoke"
    if "steps" in report or "average_count" in report or "check_only" in report:
        return "acquisition-check"
    return "unknown"


def _report_model(report: dict[str, object]) -> str:
    idn = report.get("idn")
    if isinstance(idn, dict):
        model = idn.get("model")
        if isinstance(model, str) and model:
            return model
    return "unknown"


def _report_firmware(report: dict[str, object]) -> str:
    idn = report.get("idn")
    if isinstance(idn, dict):
        firmware = idn.get("firmware")
        if isinstance(firmware, str) and firmware:
            return firmware
    return "unknown"


def _report_resource(report: dict[str, object]) -> str:
    value = report.get("resource")
    return str(value) if value is not None else "unknown"


def _report_backend(report: dict[str, object]) -> str:
    value = report.get("backend")
    return str(value) if value is not None else "unknown"


def _report_commands(report: dict[str, object]) -> list[str]:
    commands: list[str] = []
    if report.get("idn") is not None:
        commands.append("*IDN?")
    steps = report.get("steps")
    saw_final_error_query = False
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_commands = step.get("commands")
            if isinstance(step_commands, list):
                commands.extend(str(command) for command in step_commands)
            if step.get("name") in {"final-query", "final-system-error"}:
                saw_final_error_query = True
    if isinstance(report.get("capture"), dict):
        commands.extend(["<capture waveform>", "<capture screenshot>"])
    if saw_final_error_query and ":SYSTem:ERRor?" not in commands:
        commands.append(":SYSTem:ERRor?")
    return commands or ["unknown"]


def _report_files(report: dict[str, object]) -> list[tuple[str, str]]:
    files = []
    for entry in report.get("files", []):
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        path = entry.get("path")
        if isinstance(kind, str) and isinstance(path, str):
            files.append((kind, path))
    if not files:
        if "report" in report:
            files.append(("report", str(report.get("report"))))
    return files


def _render_report_result(report: dict[str, object]) -> list[str]:
    lines: list[str] = []
    status = report.get("status")
    lines.append(f"- Status: {status}")
    if "average_count" in report:
        lines.append(f"- Average Count: {report.get('average_count')}")
    if "check_only" in report:
        lines.append(f"- Check Only: {report.get('check_only')}")
    if "stopped_on_error" in report:
        lines.append(f"- Stopped On Error: {report.get('stopped_on_error')}")
    if report.get("initial_acquisition") is not None:
        lines.append(f"- Initial Acquisition: {report.get('initial_acquisition')}")
    if report.get("final_acquisition") is not None:
        lines.append(f"- Final Acquisition: {report.get('final_acquisition')}")
    if report.get("termination_reason") is not None:
        lines.append(f"- Termination Reason: {report.get('termination_reason')}")
    if isinstance(report.get("doctor"), dict):
        lines.append(f"- Doctor: {report.get('doctor')}")
    if isinstance(report.get("measurements"), list):
        lines.append(f"- Measurements: {len(report.get('measurements', []))}")
    if isinstance(report.get("capture"), dict):
        lines.append(f"- Capture: {report.get('capture')}")
    if isinstance(report.get("screenshot"), dict):
        lines.append(f"- Screenshot: {report.get('screenshot')}")
    if report.get("post_check_error") is not None:
        lines.append(f"- Post Check Error: {report.get('post_check_error')}")
    return lines


def _report_errors(report: dict[str, object]) -> list[str]:
    lines: list[str] = []
    error = report.get("error")
    if error is not None:
        lines.append(f"- Report Error: {error}")
    restore = report.get("restore")
    if isinstance(restore, dict):
        restore_error = restore.get("error")
        if restore_error is not None:
            lines.append(f"- Restore Error: {restore_error}")
    for step in report.get("steps", []):
        if not isinstance(step, dict):
            continue
        system_error = step.get("system_error")
        if isinstance(system_error, dict) and system_error.get("is_error"):
            lines.append(
                f"- {step.get('name')}: {system_error.get('code')} {system_error.get('message')}"
            )
    return lines


def _report_cleanup(report: dict[str, object]) -> list[str]:
    lines: list[str] = []
    restore = report.get("restore")
    if isinstance(restore, dict):
        lines.append(f"- Restore Requested: {restore.get('requested')}")
        lines.append(f"- Restore Attempted: {restore.get('attempted')}")
        lines.append(f"- Restore Succeeded: {restore.get('succeeded')}")
    return lines


def _format_plain_output_file_error(file_kind: str, path: Path, exc: OSError) -> str:
    reason = exc.strerror or str(exc)
    message = f"could not write {file_kind} file {path}: {reason}"
    if isinstance(exc, PermissionError):
        message += ". The file may be open in another program, or the folder may not be writable."
    return message


if __name__ == "__main__":
    raise SystemExit(main())
