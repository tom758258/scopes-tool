"""Simulated Annotation SCPI write and query handling."""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from .simulator_support import SimulatorBackendError, _parse_scpi_string_arg

if TYPE_CHECKING:
    from .simulator_backend import SimulatorBackend


def apply_annotation_write(backend: SimulatorBackend, command: str) -> bool:
    parsed = _parse_annotation_path(command)
    if parsed is None or parsed[2]:
        return False
    slot, field_name, _query = parsed
    state = _annotation_slot(backend, slot)
    upper = command.upper()
    if field_name == "STATE":
        state["enabled"] = upper.endswith(" ON")
    elif field_name == "TEXT":
        state["text"] = _parse_scpi_string_arg(command.split(" ", 1)[1])
    elif field_name == "COLOR":
        state["color"] = command.rsplit(" ", 1)[1].upper()
    elif field_name == "BACKGROUND":
        state["background"] = command.rsplit(" ", 1)[1].upper()
    elif field_name == "X1POSITION":
        state["x"] = int(command.rsplit(" ", 1)[1])
    elif field_name == "Y1POSITION":
        state["y"] = int(command.rsplit(" ", 1)[1])
    else:
        return False
    return True


def query_annotation(backend: SimulatorBackend, command: str) -> str | None:
    parsed = _parse_annotation_path(command)
    if parsed is None or not parsed[2]:
        return None
    slot, field_name, _query = parsed
    state = _annotation_slot(backend, slot)
    if field_name == "STATE":
        return "1" if state["enabled"] else "0"
    if field_name == "TEXT":
        return f'"{state["text"]}"'
    if field_name == "COLOR":
        return str(state["color"])
    if field_name == "BACKGROUND":
        return str(state["background"])
    if field_name == "X1POSITION":
        return str(state["x"])
    if field_name == "Y1POSITION":
        return str(state["y"])
    return None


def _annotation_slot(backend: SimulatorBackend, slot: int) -> dict[str, Any]:
    max_slot = backend._capabilities.annotation_slots
    if slot < 1 or slot > max_slot:
        raise SimulatorBackendError(f"Simulator annotation slot must be in range 1-{max_slot}.")
    return backend.annotation_state.setdefault(
        slot,
        {
            "enabled": False,
            "text": "",
            "color": "WHITE",
            "background": "OPAQ",
            "x": 0,
            "y": 0,
        },
    )


def _parse_annotation_path(command: str) -> tuple[int, str, bool] | None:
    match = re.fullmatch(
        r":DISPlay:ANNotation(\d*)(?:(?::(TEXT|COLor|BACKground|X1Position|Y1Position))?(\?)?(?:\s+.*)?)",
        command,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    raw_slot, field_name, query = match.groups()
    slot = int(raw_slot) if raw_slot else 1
    return slot, (field_name or "STATE").upper(), query == "?"
