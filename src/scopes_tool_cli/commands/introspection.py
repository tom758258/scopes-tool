"""Offline tool introspection commands: manifest and capabilities."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from importlib import metadata
import sys

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.identity import physical_model_for_id

from .. import runtime

MANIFEST_EVENT = "tool_manifest"
CAPABILITIES_EVENT = "capabilities"
ERROR_EVENT = "error"
TOOL_ID = "scopes"
WORKER_COMPATIBILITY_POLICY = "v2-only"
SCHEMA_VERSION = 2
INTROSPECTION_EXIT_USAGE_ERROR = 2
DEFAULT_MODEL_ID = "keysight-dsox4024a"


def _package_version() -> str:
    try:
        return metadata.version("scopes-tool")
    except metadata.PackageNotFoundError:
        return "0+unknown"


def _write_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def build_manifest() -> dict[str, object]:
    # Lazy import: worker_commands imports cli at module level.
    from ..worker_commands import WORKER_SCHEMA_VERSION

    return {
        "event": MANIFEST_EVENT,
        "schema_version": SCHEMA_VERSION,
        "tool_id": TOOL_ID,
        "tool_version": _package_version(),
        "worker_protocol": {
            "schema_versions": [WORKER_SCHEMA_VERSION],
            "compatibility_policy": WORKER_COMPATIBILITY_POLICY,
        },
    }


def cmd_manifest(args: argparse.Namespace) -> int:
    manifest = build_manifest()
    if getattr(args, "json_output", False):
        _write_json(manifest)
        return 0
    protocol = manifest["worker_protocol"]
    print(f"tool id: {manifest['tool_id']}")
    print(f"tool version: {manifest['tool_version']}")
    print(
        "worker protocol: "
        f"schema versions {protocol['schema_versions']} "
        f"({protocol['compatibility_policy']})"
    )
    return 0


def cmd_capabilities(args: argparse.Namespace) -> int:
    requested_model = getattr(args, "model", None)
    model_id = requested_model if requested_model else DEFAULT_MODEL_ID
    try:
        physical_model = physical_model_for_id(model_id)
        capabilities = capabilities_for_model_id(physical_model.model_id)
    except OscilloscopeError as exc:
        return _capabilities_error(args, exc)

    payload: dict[str, object] = {
        "event": CAPABILITIES_EVENT,
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "selection": {
            "requested_model": requested_model,
            "source": "requested_model" if requested_model else "default_policy",
        },
        "runtime_identity": {
            "detection_performed": False,
        },
        "model": {
            "model_id": physical_model.model_id,
            "vendor_id": physical_model.vendor_id,
            "canonical_model": physical_model.canonical_model,
            "display_name": physical_model.display_name,
            "series": physical_model.series,
            "driver_id": physical_model.driver_id,
        },
        "capabilities": runtime._capabilities_json(capabilities),
    }
    if getattr(args, "json_output", False):
        _write_json(payload)
        return 0

    selection = payload["selection"]
    model = payload["model"]
    print(f"requested model: {requested_model or 'none'}")
    print(f"resolved source: {selection['source']}")
    print(f"model id: {model['model_id']}")
    print(f"vendor id: {model['vendor_id']}")
    print(f"canonical model: {model['canonical_model']}")
    print(f"series: {model['series']}")
    print(f"driver id: {model['driver_id']}")
    print("runtime identity detection: not performed")
    return 0


def _capabilities_error(args: argparse.Namespace, exc: OscilloscopeError) -> int:
    if getattr(args, "json_output", False):
        _write_json(
            {
                "event": ERROR_EVENT,
                "schema_version": SCHEMA_VERSION,
                "command": "capabilities",
                "ok": False,
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "exit_code": INTROSPECTION_EXIT_USAGE_ERROR,
            }
        )
    else:
        print(f"error: {exc}", file=sys.stderr)
    return INTROSPECTION_EXIT_USAGE_ERROR
