"""Common reference waveform slot controls."""

from __future__ import annotations

from dataclasses import dataclass

from .capabilities import ScopeCapabilities
from .channel import validate_analog_channel
from .display import parse_display_label
from .errors import ParameterValidationError
from .scpi import SCPIClient
from .status import parse_operation_complete, system_opc_query


_REFERENCE_SAVE_COMPLETION_TIMEOUT_MS = 15000


@dataclass(frozen=True)
class ReferenceWaveformState:
    """Display and label state for one reference waveform slot."""

    slot: int
    displayed: bool
    raw_displayed: str
    label: str
    raw_label: str


class ReferenceWaveformController:
    """Controls for common reference waveform slot operations."""

    def __init__(self, scpi: SCPIClient, capabilities: ScopeCapabilities) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def save(self, slot: int, source_channel: int) -> None:
        self.scpi.write(
            reference_save_command(slot, source_channel, capabilities=self.capabilities)
        )
        original_timeout = self.scpi.timeout
        self.scpi.set_timeout(_REFERENCE_SAVE_COMPLETION_TIMEOUT_MS)
        try:
            parse_operation_complete(self.scpi.query(system_opc_query()))
        finally:
            self.scpi.set_timeout(original_timeout)

    def set_display(self, slot: int, enabled: bool) -> None:
        self.scpi.write(
            reference_display_command(slot, enabled, capabilities=self.capabilities)
        )

    def query_display(self, slot: int) -> tuple[bool, str]:
        raw = self.scpi.query(
            reference_display_query(slot, capabilities=self.capabilities)
        ).strip()
        return parse_display_label(raw), raw

    def set_label(self, slot: int, label: str) -> None:
        self.scpi.write(
            reference_label_command(slot, label, capabilities=self.capabilities)
        )

    def query_label(self, slot: int) -> tuple[str, str]:
        raw = self.scpi.query(
            reference_label_query(slot, capabilities=self.capabilities)
        ).strip()
        return parse_reference_label(raw), raw

    def clear(self, slot: int) -> None:
        self.scpi.write(reference_clear_command(slot, capabilities=self.capabilities))

    def query(self, slot: int) -> ReferenceWaveformState:
        slot = validate_reference_slot(slot, self.capabilities)
        displayed, raw_displayed = self.query_display(slot)
        label, raw_label = self.query_label(slot)
        return ReferenceWaveformState(
            slot=slot,
            displayed=displayed,
            raw_displayed=raw_displayed,
            label=label,
            raw_label=raw_label,
        )


def validate_reference_slot(slot: int, capabilities: ScopeCapabilities) -> int:
    if slot < 1 or slot > capabilities.reference_waveforms:
        raise ParameterValidationError(
            f"reference waveform slot must be in range 1-{capabilities.reference_waveforms}."
        )
    return slot


def validate_reference_label(label: str) -> str:
    if not isinstance(label, str) or not label:
        raise ParameterValidationError("reference waveform label must not be empty.")
    if len(label) > 10:
        raise ParameterValidationError(
            "reference waveform label must be at most 10 characters."
        )
    if '"' in label:
        raise ParameterValidationError(
            "reference waveform label must not contain a double quote."
        )
    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in label):
        raise ParameterValidationError(
            "reference waveform label must contain printable ASCII characters only."
        )
    return label


def parse_reference_label(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def reference_save_command(
    slot: int, source_channel: int, *, capabilities: ScopeCapabilities
) -> str:
    slot = validate_reference_slot(slot, capabilities)
    source_channel = validate_analog_channel(source_channel, capabilities)
    return f":WMEMory{slot}:SAVE CHANnel{source_channel}"


def reference_display_command(
    slot: int, enabled: bool, *, capabilities: ScopeCapabilities
) -> str:
    slot = validate_reference_slot(slot, capabilities)
    return f":WMEMory{slot}:DISPlay {'ON' if enabled else 'OFF'}"


def reference_display_query(slot: int, *, capabilities: ScopeCapabilities) -> str:
    slot = validate_reference_slot(slot, capabilities)
    return f":WMEMory{slot}:DISPlay?"


def reference_label_command(
    slot: int, label: str, *, capabilities: ScopeCapabilities
) -> str:
    slot = validate_reference_slot(slot, capabilities)
    label = validate_reference_label(label)
    return f':WMEMory{slot}:LABel "{label}"'


def reference_label_query(slot: int, *, capabilities: ScopeCapabilities) -> str:
    slot = validate_reference_slot(slot, capabilities)
    return f":WMEMory{slot}:LABel?"


def reference_clear_command(slot: int, *, capabilities: ScopeCapabilities) -> str:
    slot = validate_reference_slot(slot, capabilities)
    return f":WMEMory{slot}:CLEar"


def reference_query_commands(
    slot: int, *, capabilities: ScopeCapabilities
) -> tuple[str, str]:
    return (
        reference_display_query(slot, capabilities=capabilities),
        reference_label_query(slot, capabilities=capabilities),
    )
