"""Support definitions shared by the split simulator modules."""

from __future__ import annotations

from .errors import OscilloscopeError


class SimulatorBackendError(OscilloscopeError):
    """Raised when the simulator receives unsupported SCPI."""


def _parse_scpi_bool_write(command: str) -> bool:
    value = command.rsplit(" ", 1)[1].strip().upper()
    if value in {"1", "ON"}:
        return True
    if value in {"0", "OFF"}:
        return False
    raise SimulatorBackendError(f"Unsupported simulator write: {command}")
