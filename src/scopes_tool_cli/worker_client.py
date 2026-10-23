"""Worker HTTP client helpers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import time
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlsplit

from scopes_tool_core.errors import OscilloscopeError

from . import cli as scope_cli
from .worker_commands import WORKER_FEATURES, WORKER_SCHEMA_VERSION


def client_send_command(args: argparse.Namespace) -> int:
    try:
        arguments = json.loads(args.arguments_json)
    except json.JSONDecodeError as exc:
        return _client_error(args, 2, "invalid arguments JSON", exc)
    if not isinstance(arguments, dict):
        return _client_error(args, 2, "--arguments-json must decode to an object")
    body = {
        "schema_version": WORKER_SCHEMA_VERSION,
        "command": args.worker_command,
        "arguments": arguments,
    }
    if args.job_id is not None:
        body["job_id"] = args.job_id
    if args.dry_run:
        response = {
            "ok": True,
            "status": "dry_run",
            "command": args.worker_command,
            "request": body,
        }
        _client_print(args, response)
        return 0
    return client_post(args, "/command", body)


def client_get(args: argparse.Namespace, path: str) -> int:
    try:
        response, status = _http_request(args, path, method="GET")
        response = _validate_client_response(response)
        if status == 200 and path == "/status":
            _validate_status(response, args)
    except Exception as exc:
        return _client_error(args, 3, "worker request failed", exc)
    _client_print(args, response)
    if response.get("fatal_error") is not None:
        return 3
    return 0 if 200 <= status < 300 else _status_exit(status)


def client_post(args: argparse.Namespace, path: str, body: dict[str, Any]) -> int:
    try:
        response, status = _http_request(args, path, method="POST", body=body)
        response = _validate_client_response(response)
    except Exception as exc:
        return _client_error(args, 3, "worker request failed", exc)
    _client_print(args, response)
    return 0 if 200 <= status < 300 else _status_exit(status)


def client_wait_ready(args: argparse.Namespace) -> int:
    deadline = time.monotonic() + (args.timeout_ms / 1000)
    last_error: Exception | None = None
    run_id: str | None = None
    while time.monotonic() < deadline:
        try:
            response, status = _http_request(args, "/status", method="GET")
            response = _validate_client_response(response)
            if status == 200:
                _validate_status(response, args)
                if run_id is not None and response["run_id"] != run_id:
                    raise OscilloscopeError("worker run_id changed while waiting for readiness")
                run_id = response["run_id"]
                if response["fatal_error"] is not None or response["worker_state"] == "failed":
                    _client_print(args, response)
                    return 3
                if response["worker_state"] == "running":
                    _client_print(args, response)
                    return 0
            elif status >= 400:
                _client_print(args, response)
                return _status_exit(status)
        except OscilloscopeError as exc:
            return _client_error(args, 3, "invalid worker readiness response", exc)
        except Exception as exc:
            last_error = exc
        time.sleep(0.1)
    return _client_error(args, 3, "worker did not become ready", last_error)


def _http_request(
    args: argparse.Namespace,
    path: str,
    *,
    method: str,
    body: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    url = f"http://{args.host}:{args.port}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    timeout = args.timeout_ms / 1000
    started = time.monotonic()
    diagnostics = _client_diagnostics(args)
    diagnostics.update(method=method, url=url, endpoint=path, request_sent=True,
                       reachable=False, http_status=None, error_phase="request")
    args._worker_client_diagnostics = diagnostics
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            diagnostics.update(reachable=True, http_status=response.status, error_phase="response")
            return json.loads(response.read().decode("utf-8")), response.status
    except urlerror.HTTPError as exc:
        diagnostics.update(reachable=True, http_status=exc.code, error_phase="response")
        payload = json.loads(exc.read().decode("utf-8"))
        return payload, exc.code
    finally:
        diagnostics["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)


def _validate_client_response(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OscilloscopeError("invalid worker response: expected a JSON object")
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != WORKER_SCHEMA_VERSION:
        raise OscilloscopeError(
            "invalid worker response: "
            f"schema_version must be exactly {WORKER_SCHEMA_VERSION}"
        )
    return payload


def _validate_status(payload: dict[str, Any], args: argparse.Namespace) -> None:
    if not isinstance(payload.get("run_id"), str) or not payload["run_id"]:
        raise OscilloscopeError("invalid worker status run_id")
    if not _is_utc_timestamp(payload.get("timestamp_utc")):
        raise OscilloscopeError("invalid worker status timestamp_utc")
    if payload.get("worker_state") not in {"starting", "running", "stopping", "failed"}:
        raise OscilloscopeError("invalid worker status worker_state")
    if "fatal_error" not in payload:
        raise OscilloscopeError("missing worker status fatal_error")
    fatal_error = payload["fatal_error"]
    if fatal_error is not None:
        if not _is_common_error(fatal_error):
            raise OscilloscopeError("invalid worker status fatal_error")
    elif payload["worker_state"] == "failed":
        raise OscilloscopeError("failed worker status requires fatal_error")
    features = payload.get("features")
    if not isinstance(features, dict) or set(features) != set(WORKER_FEATURES):
        raise OscilloscopeError("invalid worker runtime features")
    for name, declaration in features.items():
        if not isinstance(declaration, dict) or (
            type(declaration.get("contract_version")) is not int
            or declaration["contract_version"] != WORKER_FEATURES[name]["contract_version"]
        ):
            raise OscilloscopeError("unsupported worker feature version")
    origin = urlsplit(f"http://{args.host}:{args.port}")
    for name in ("status_url", "command_url", "stop_url"):
        value = payload.get(name)
        if not isinstance(value, str) or not value:
            raise OscilloscopeError(f"missing worker status {name}")
        url = urlsplit(value)
        if (url.scheme, url.hostname, url.port or 80) != (
            origin.scheme, origin.hostname, origin.port or 80
        ) or url.username is not None or url.password is not None or url.fragment:
            raise OscilloscopeError(f"invalid worker status {name} origin")
    if "active_job" not in payload or "last_job" not in payload:
        raise OscilloscopeError("missing worker status job snapshots")
    for name, states in (("active_job", {"queued", "running"}),
                         ("last_job", {"succeeded", "failed", "cancelled"})):
        job = payload[name]
        if job is None:
            continue
        if not isinstance(job, dict) or not (
            isinstance(job.get("worker_job_id"), str) and job["worker_job_id"]
            and isinstance(job.get("command"), str) and job["command"]
            and "job_id" in job and (job["job_id"] is None or isinstance(job["job_id"], str))
            and _is_utc_timestamp(job.get("timestamp_utc"))
            and job.get("state") in states
        ):
            raise OscilloscopeError(f"invalid worker status {name}")
        if name == "last_job" and not (
            type(job.get("ok")) is bool and job["ok"] == (job["state"] == "succeeded")
            and "result" in job and "error" in job
            and (job["error"] is None if job["ok"] else
                 _is_common_error(job["error"]) or (
                     job["state"] == "cancelled" and job["error"] is None
                 ))
        ):
            raise OscilloscopeError("incomplete worker terminal snapshot")


def _is_common_error(value: Any) -> bool:
    return isinstance(value, dict) and (
        value.get("category") in {"validation", "admission", "execution", "worker"}
        and isinstance(value.get("code"), str) and bool(value["code"])
        and isinstance(value.get("message"), str) and bool(value["message"])
        and isinstance(value.get("details"), dict)
    )


def _is_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        offset = timestamp.utcoffset()
        return offset is not None and offset.total_seconds() == 0
    except ValueError:
        return False


def _client_print(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if getattr(args, "client_json", False) or getattr(args, "format", None) == "json":
        scope_cli._write_json(_client_json_payload(args, payload))
        return
    status = payload.get("status", "ok")
    print(f"status: {status}")
    for key in ("command", "job_id", "worker_job_id", "run_id"):
        if key in payload and payload[key] is not None:
            print(f"{key}: {payload[key]}")


def _client_error(
    args: argparse.Namespace,
    exit_code: int,
    message: str,
    exc: Exception | None = None,
) -> int:
    payload = {
        "ok": False,
        "status": "error",
        "command": getattr(args, "worker_command", None)
        if getattr(args, "command", None) == "send-command"
        else getattr(args, "command", None),
        "error": {
            "type": type(exc).__name__ if exc is not None else "ClientError",
            "message": message if exc is None else f"{message}: {exc}",
        },
    }
    _client_print(args, payload)
    return exit_code


def _client_json_payload(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.setdefault("schema_version", scope_cli.CLI_SCHEMA_VERSION)
    result.setdefault("timestamp_utc", _now())
    if getattr(args, "command", None) == "send-command":
        result.setdefault("command", getattr(args, "worker_command", None))
    else:
        result.setdefault("command", getattr(args, "command", None))
    result.update(_client_diagnostics(args))
    if payload.get("ok") is True or (
        result["http_status"] in {200, 202}
        and payload.get("error") is None and payload.get("fatal_error") is None
    ):
        result["error_phase"] = None
    return result


def _client_diagnostics(args: argparse.Namespace) -> dict[str, Any]:
    diagnostics = getattr(args, "_worker_client_diagnostics", None)
    if diagnostics is not None:
        return dict(diagnostics)
    command = getattr(args, "command", None)
    path = "/command" if command == "send-command" else (
        "/stop" if command == "stop" else "/status"
    )
    return {"client_command": command, "method": "POST" if path != "/status" else "GET",
            "url": f"http://{args.host}:{args.port}{path}", "endpoint": path,
            "timeout_ms": args.timeout_ms, "elapsed_ms": 0,
            "request_sent": False, "reachable": None, "http_status": None,
            "error_phase": "validation"}


def _status_exit(status: int) -> int:
    return 2 if status == 400 else 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
