"""Shared WebUI request-error type and primitive parameter helpers."""

from __future__ import annotations

import math
from typing import Any, Mapping


class WebUIRequestError(ValueError):
    """Raised when a WebUI command request is invalid before queueing."""


def _csv_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    raise WebUIRequestError("workflow list fields must be comma-separated strings")


def _validate_action_fields(parameters: dict[str, Any], command: str, names: tuple[str, ...]) -> str:
    action = _action(parameters, command)
    if action == "query":
        _reject_query_parameters(parameters, names, command)
    return action


def _action(parameters: dict[str, Any], command: str) -> str:
    action = parameters.setdefault("action", "query")
    if action not in {"query", "set"}:
        raise WebUIRequestError(f"{command} action must be query or set")
    return action


def _require_parameter(parameters: Mapping[str, Any], name: str, command: str) -> None:
    if name not in parameters:
        raise WebUIRequestError(f"{command} set requires {name}")


def _reject_query_parameters(
    parameters: Mapping[str, Any], names: tuple[str, ...], command: str
) -> None:
    for name in names:
        if name in parameters:
            raise WebUIRequestError(f"{command} query cannot include {name}")


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WebUIRequestError(f"{name} must be an integer")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WebUIRequestError(f"{name} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise WebUIRequestError(f"{name} must be finite")
    return parsed


def _require_boolean(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise WebUIRequestError(f"{name} must be a boolean")
