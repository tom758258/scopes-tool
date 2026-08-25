"""Worker HTTP client helpers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import time
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from scopes_tool_core.errors import OscilloscopeError

from . import cli as scope_cli
from .worker_commands import WORKER_SCHEMA_VERSION


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
    except Exception as exc:
        return _client_error(args, 3, "worker request failed", exc)
    _client_print(args, response)
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
    while time.monotonic() < deadline:
        try:
            response, status = _http_request(args, "/status", method="GET")
            response = _validate_client_response(response)
            if status == 200:
                _client_print(args, response)
                return 0
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
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), response.status
    except urlerror.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        return payload, exc.code


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
    result.setdefault("schema_version", WORKER_SCHEMA_VERSION)
    result.setdefault("timestamp_utc", _now())
    if getattr(args, "command", None) == "send-command":
        result.setdefault("command", getattr(args, "worker_command", None))
    else:
        result.setdefault("command", getattr(args, "command", None))
    return result


def _status_exit(status: int) -> int:
    return 2 if status == 400 else 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
