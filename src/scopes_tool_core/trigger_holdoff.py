"""Trigger holdoff controls."""

from __future__ import annotations

from .math import _format_scpi_number, validate_finite_number
from .errors import ParameterValidationError
from .scpi import SCPIClient


TRIGGER_HOLDOFF_MIN_SECONDS = 40e-9

TRIGGER_HOLDOFF_MAX_SECONDS = 10.0

class TriggerHoldoffController:
    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def set_seconds(self, seconds: float) -> None:
        for command in trigger_holdoff_commands(seconds):
            self.scpi.write(command)

    def query_seconds(self) -> float:
        return self.scpi.query_float(trigger_holdoff_query())

def trigger_holdoff_command(seconds: float) -> str:
    seconds = validate_trigger_holdoff(seconds)
    return f":TRIGger:HOLDoff {_format_scpi_number(seconds)}"

def trigger_holdoff_commands(seconds: float) -> list[str]:
    return [":TRIGger:HOLDoff:RANDom OFF", trigger_holdoff_command(seconds)]

def trigger_holdoff_query() -> str:
    return ":TRIGger:HOLDoff?"

def validate_trigger_holdoff(seconds: float) -> float:
    seconds = validate_finite_number(seconds, "--seconds")
    if seconds < TRIGGER_HOLDOFF_MIN_SECONDS or seconds > TRIGGER_HOLDOFF_MAX_SECONDS:
        raise ParameterValidationError("--seconds must be between 40e-9 and 10.")
    return seconds
