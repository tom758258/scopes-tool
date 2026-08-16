"""Autoscale and instrument setup controls."""

from __future__ import annotations

from pathlib import PureWindowsPath
from typing import Sequence

from .capabilities import ScopeCapabilities
from .channel import validate_analog_channel
from .errors import ParameterValidationError
from .scpi import SCPIClient
from .status import parse_operation_complete, system_opc_query


_SETUP_COMPLETION_TIMEOUT_MS = 15000

_AUTOSCALE_ACQUIRE_MODES = {"normal": "NORMal", "current": "CURRent"}

_AUTOSCALE_CHANNEL_MODES = {"all": "ALL", "displayed": "DISPlayed"}

class SetupController:
    def __init__(self, scpi: SCPIClient) -> None:
        self.scpi = scpi

    def autoscale(
        self,
        channels: Sequence[int] | None,
        *,
        acquire_mode: str | None = None,
        channels_mode: str | None = None,
        capabilities: ScopeCapabilities | None = None,
    ) -> None:
        for command in autoscale_commands(
            channels,
            acquire_mode=acquire_mode,
            channels_mode=channels_mode,
            capabilities=capabilities,
        ):
            self.scpi.write(command)

    def save(self, *, slot: int | None = None, file_spec: str | None = None) -> None:
        self.scpi.write(setup_save_command(slot=slot, file_spec=file_spec))
        original_timeout = self.scpi.timeout
        self.scpi.set_timeout(_SETUP_COMPLETION_TIMEOUT_MS)
        try:
            parse_operation_complete(self.scpi.query(system_opc_query()))
        finally:
            self.scpi.set_timeout(original_timeout)

    def recall(self, *, slot: int | None = None, file_spec: str | None = None) -> None:
        self.scpi.write(setup_recall_command(slot=slot, file_spec=file_spec))
        original_timeout = self.scpi.timeout
        self.scpi.set_timeout(_SETUP_COMPLETION_TIMEOUT_MS)
        try:
            parse_operation_complete(self.scpi.query(system_opc_query()))
        finally:
            self.scpi.set_timeout(original_timeout)

def autoscale_commands(
    channels: Sequence[int] | None,
    *,
    acquire_mode: str | None = None,
    channels_mode: str | None = None,
    capabilities: ScopeCapabilities | None = None,
) -> list[str]:
    commands: list[str] = []
    if acquire_mode is not None:
        commands.append(f":AUToscale:AMODe {normalize_autoscale_acquire_mode(acquire_mode)}")
    if channels_mode is not None:
        commands.append(f":AUToscale:CHANnels {normalize_autoscale_channels_mode(channels_mode)}")
    if channels:
        validated = [
            validate_analog_channel(channel, capabilities) if capabilities is not None else channel
            for channel in channels
        ]
        joined = ",".join(f"CHANnel{channel}" for channel in validated)
        commands.append(f":AUToscale {joined}")
    else:
        commands.append(":AUToscale")
    return commands

def normalize_autoscale_acquire_mode(value: str) -> str:
    try:
        return _AUTOSCALE_ACQUIRE_MODES[value.strip().lower()]
    except KeyError as exc:
        raise ParameterValidationError("--acquire-mode must be normal or current.") from exc

def normalize_autoscale_channels_mode(value: str) -> str:
    try:
        return _AUTOSCALE_CHANNEL_MODES[value.strip().lower()]
    except KeyError as exc:
        raise ParameterValidationError("--channels must be all or displayed.") from exc

def setup_save_command(*, slot: int | None = None, file_spec: str | None = None) -> str:
    target = setup_target(slot=slot, file_spec=file_spec)
    return f":SAVE:SETup {target}"

def setup_recall_command(*, slot: int | None = None, file_spec: str | None = None) -> str:
    target = setup_target(slot=slot, file_spec=file_spec)
    return f":RECall:SETup {target}"

def setup_target(*, slot: int | None = None, file_spec: str | None = None) -> str:
    if (slot is None) == (file_spec is None):
        raise ParameterValidationError("setup commands require exactly one of --slot or --file.")
    if slot is not None:
        if slot < 0 or slot > 9:
            raise ParameterValidationError("--slot must be between 0 and 9.")
        return str(slot)
    assert file_spec is not None
    if '"' in file_spec or "'" in file_spec:
        raise ParameterValidationError("--file must not contain quotes.")
    suffix = PureWindowsPath(file_spec).suffix
    if suffix and suffix.lower() != ".scp":
        raise ParameterValidationError("--file extension must be .scp when provided.")
    return f'"{file_spec}"'
