"""Horizontal timebase controls."""

from __future__ import annotations

import math
from typing import Literal

from .errors import ParameterValidationError, TimebaseResponseError
from .scpi import SCPIClient


TimebaseReference = Literal["left", "center", "right"]
TIMEBASE_REFERENCES: tuple[TimebaseReference, ...] = ("left", "center", "right")
_TIMEBASE_REFERENCE_TOKENS = {
    "left": "LEFT",
    "center": "CENTer",
    "right": "RIGHt",
}


class TimebaseController:
    """Controls for oscilloscope horizontal timebase settings."""

    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def set_scale(self, seconds_per_division: float) -> None:
        """Set the horizontal scale in seconds per division."""

        seconds_per_division = validate_timebase_scale(seconds_per_division)
        self.scpi.write(timebase_scale_command(seconds_per_division))

    def query_scale(self) -> float:
        """Query the horizontal scale in seconds per division."""

        return parse_timebase_float(self.scpi.query(timebase_scale_query()), "scale")

    def set_position(self, seconds: float) -> None:
        """Set the horizontal position in seconds."""

        seconds = validate_timebase_position(seconds)
        self.scpi.write(timebase_position_command(seconds))

    def query_position(self) -> float:
        """Query the horizontal position in seconds."""

        return parse_timebase_float(self.scpi.query(timebase_position_query()), "position")

    def set_reference(self, reference: str) -> None:
        """Set the horizontal timebase reference position."""

        reference = validate_timebase_reference(reference)
        self.scpi.write(timebase_reference_command(reference))

    def query_reference(self) -> TimebaseReference:
        """Query the horizontal timebase reference position."""

        return parse_timebase_reference(self.scpi.query(timebase_reference_query()))


def validate_timebase_scale(seconds_per_division: float) -> float:
    """Validate a horizontal scale value before sending it to the instrument."""

    try:
        value = float(seconds_per_division)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError("timebase scale must be a number.") from exc
    if not math.isfinite(value):
        raise ParameterValidationError("timebase scale must be a finite number.")
    if value <= 0:
        raise ParameterValidationError("timebase scale must be greater than 0 s/div.")
    return value


def validate_timebase_position(seconds: float) -> float:
    """Validate a horizontal position value before sending it to the instrument."""

    try:
        value = float(seconds)
    except (TypeError, ValueError) as exc:
        raise ParameterValidationError("timebase position must be a number.") from exc
    if not math.isfinite(value):
        raise ParameterValidationError("timebase position must be a finite number.")
    return value


def validate_timebase_reference(reference: str) -> TimebaseReference:
    """Validate a horizontal timebase reference value."""

    if reference not in TIMEBASE_REFERENCES:
        raise ParameterValidationError("timebase reference must be left, center, or right.")
    return reference


def timebase_scale_command(seconds_per_division: float) -> str:
    """Build the SCPI command for horizontal scale."""

    return f":TIMebase:SCALe {_format_scpi_float(seconds_per_division)}"


def timebase_scale_query() -> str:
    """Build the SCPI query for horizontal scale."""

    return ":TIMebase:SCALe?"


def timebase_position_command(seconds: float) -> str:
    """Build the SCPI command for horizontal position."""

    return f":TIMebase:POSition {_format_scpi_float(seconds)}"


def timebase_position_query() -> str:
    """Build the SCPI query for horizontal position."""

    return ":TIMebase:POSition?"


def timebase_reference_command(reference: str) -> str:
    """Build the SCPI command for horizontal timebase reference."""

    reference = validate_timebase_reference(reference)
    return f":TIMebase:REFerence {_TIMEBASE_REFERENCE_TOKENS[reference]}"


def timebase_reference_query() -> str:
    """Build the SCPI query for horizontal timebase reference."""

    return ":TIMebase:REFerence?"


def parse_timebase_reference(raw: str) -> TimebaseReference:
    """Parse a timebase reference query response."""

    normalized = raw.strip().upper()
    if normalized == "LEFT":
        return "left"
    if normalized in {"CENT", "CENTER"}:
        return "center"
    if normalized in {"RIGH", "RIGHT"}:
        return "right"
    raise TimebaseResponseError(
        f"Could not parse timebase reference response: {raw!r}"
    )


def parse_timebase_float(raw: str, setting_name: str) -> float:
    """Parse a numeric timebase query response."""

    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise TimebaseResponseError(
            f"Could not parse timebase {setting_name} response: {raw!r}"
        ) from exc
    if not math.isfinite(value):
        raise TimebaseResponseError(
            f"Could not parse timebase {setting_name} response: {raw!r}"
        )
    return value


def _format_scpi_float(value: float) -> str:
    return f"{value:.12g}"
