"""Instrument-side save and export controls."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .capabilities import ScopeCapabilities
from .errors import ParameterValidationError, SaveExportResponseError
from .scpi import SCPIClient
from .status import parse_operation_complete, system_opc_query
from .trigger import (
    OPERATION_CONDITION_RUI_ENAB_MASK,
    operation_condition_query,
    parse_operation_condition,
)


SAVE_IMAGE_FORMATS = ("png", "bmp", "bmp8", "bmp24")
SAVE_IMAGE_PALETTES = ("color", "grayscale")
SAVE_WAVEFORM_FORMATS = ("ascii-xy", "csv", "binary")

_SAVE_COMPLETION_TIMEOUT_MS = 15000
_SAVE_FORMAT_COMPLETION_TIMEOUT_MS = 5000
_SAVE_READINESS_POLL_INTERVAL_SECONDS = 0.1

_SAVE_IMAGE_FORMAT_COMMANDS = {
    "png": "PNG",
    "bmp": "BMP",
    "bmp8": "BMP8bit",
    "bmp24": "BMP24bit",
}
_SAVE_IMAGE_FORMAT_READBACKS = {
    "PNG": "png",
    "BMP": "bmp",
    "BMP8": "bmp8",
    "BMP8BIT": "bmp8",
    "BMP24": "bmp24",
    "BMP24BIT": "bmp24",
    "NONE": "none",
}
_SAVE_IMAGE_PALETTE_COMMANDS = {
    "color": "COLor",
    "grayscale": "GRAYscale",
}
_SAVE_IMAGE_PALETTE_READBACKS = {
    "COL": "color",
    "COLOR": "color",
    "GRAY": "grayscale",
    "GRAYSCALE": "grayscale",
}
_SAVE_WAVEFORM_FORMAT_COMMANDS = {
    "ascii-xy": "ASCiixy",
    "csv": "CSV",
    "binary": "BINary",
}
_SAVE_WAVEFORM_FORMAT_READBACKS = {
    "ASC": "ascii-xy",
    "ASCIIXY": "ascii-xy",
    "CSV": "csv",
    "BIN": "binary",
    "BINARY": "binary",
    "NONE": "none",
}


@dataclass(frozen=True)
class SavePwdState:
    """Current instrument-side save directory."""

    path: str
    raw_response: str

    def to_json(self) -> dict[str, object]:
        """Return the canonical JSON representation."""

        return {"path": self.path, "raw_response": self.raw_response}


@dataclass(frozen=True)
class SaveFilenameState:
    """Current default instrument-side save base name."""

    name: str
    raw_response: str

    def to_json(self) -> dict[str, object]:
        """Return the canonical JSON representation."""

        return {"name": self.name, "raw_response": self.raw_response}


@dataclass(frozen=True)
class SaveImageFormatState:
    """Current instrument-side image save format."""

    format: str
    raw_response: str

    def to_json(self) -> dict[str, object]:
        """Return the canonical JSON representation."""

        return {"format": self.format, "raw_response": self.raw_response}


@dataclass(frozen=True)
class SaveImagePaletteState:
    """Current instrument-side image palette."""

    palette: str
    raw_response: str

    def to_json(self) -> dict[str, object]:
        """Return the canonical JSON representation."""

        return {"palette": self.palette, "raw_response": self.raw_response}


@dataclass(frozen=True)
class SaveBooleanState:
    """Boolean instrument-side save setting with raw readback."""

    enabled: bool
    raw_response: str

    def to_json(self) -> dict[str, object]:
        """Return the canonical JSON representation."""

        return {"enabled": self.enabled, "raw_response": self.raw_response}


@dataclass(frozen=True)
class SaveWaveformFormatState:
    """Current instrument-side waveform save format."""

    format: str
    raw_response: str

    def to_json(self) -> dict[str, object]:
        """Return the canonical JSON representation."""

        return {"format": self.format, "raw_response": self.raw_response}


@dataclass(frozen=True)
class SaveWaveformLengthState:
    """Current instrument-side waveform save length."""

    points: int
    raw_response: str

    def to_json(self) -> dict[str, object]:
        """Return the canonical JSON representation."""

        return {"points": self.points, "raw_response": self.raw_response}


@dataclass(frozen=True)
class SaveOperationResult:
    """Completed instrument-side save start operation."""

    operation: str
    filename: str
    command: str
    raw_operation_complete: str
    instrument_side: bool = True

    def to_json(self) -> dict[str, object]:
        """Return the canonical JSON representation."""

        return {
            "instrument_side": self.instrument_side,
            "operation": self.operation,
            "filename": self.filename,
            "command": self.command,
            "operation_complete": True,
            "raw_operation_complete": self.raw_operation_complete,
        }


class SaveExportController:
    """Controller for common instrument-side SAVE commands."""

    def __init__(
        self,
        scpi: SCPIClient,
        capabilities: ScopeCapabilities | None = None,
    ) -> None:
        self.scpi = scpi
        self.capabilities = capabilities

    def configure_pwd(self, path: str) -> None:
        self.scpi.write(save_pwd_command(path))

    def query_pwd(self) -> SavePwdState:
        raw = self.scpi.query(save_pwd_query()).strip()
        return SavePwdState(parse_save_quoted_readback(raw), raw)

    def configure_filename(self, name: str) -> None:
        self.scpi.write(save_filename_command(name))

    def query_filename(self) -> SaveFilenameState:
        raw = self.scpi.query(save_filename_query()).strip()
        return SaveFilenameState(parse_save_quoted_readback(raw), raw)

    def configure_image_format(self, format: str) -> None:
        self.scpi.write(save_image_format_command(format))
        if self.capabilities is not None and self.capabilities.series == "4000X":
            original_timeout = self.scpi.timeout
            self.scpi.set_timeout(_SAVE_FORMAT_COMPLETION_TIMEOUT_MS)
            try:
                parse_operation_complete(self.scpi.query(system_opc_query()))
            finally:
                self.scpi.set_timeout(original_timeout)

    def query_image_format(self) -> SaveImageFormatState:
        raw = self.scpi.query(save_image_format_query()).strip()
        return SaveImageFormatState(parse_save_image_format(raw), raw)

    def configure_image_palette(self, palette: str) -> None:
        self.scpi.write(save_image_palette_command(palette))

    def query_image_palette(self) -> SaveImagePaletteState:
        raw = self.scpi.query(save_image_palette_query()).strip()
        return SaveImagePaletteState(parse_save_image_palette(raw), raw)

    def configure_image_ink_saver(self, enabled: bool) -> None:
        self.scpi.write(save_image_ink_saver_command(enabled))

    def query_image_ink_saver(self) -> SaveBooleanState:
        raw = self.scpi.query(save_image_ink_saver_query()).strip()
        return SaveBooleanState(parse_save_bool(raw), raw)

    def configure_image_factors(self, enabled: bool) -> None:
        self.scpi.write(save_image_factors_command(enabled))

    def query_image_factors(self) -> SaveBooleanState:
        raw = self.scpi.query(save_image_factors_query()).strip()
        return SaveBooleanState(parse_save_bool(raw), raw)

    def save_image(self, filename: str) -> SaveOperationResult:
        command = save_image_command(filename)
        self.scpi.write(command)
        original_timeout = self.scpi.timeout
        self.scpi.set_timeout(_SAVE_COMPLETION_TIMEOUT_MS)
        try:
            complete = parse_operation_complete(self.scpi.query(system_opc_query()))
        finally:
            self.scpi.set_timeout(original_timeout)
        return SaveOperationResult(
            operation="save-image",
            filename=filename,
            command=command,
            raw_operation_complete=complete.raw,
        )

    def configure_waveform_format(self, format: str) -> None:
        self.scpi.write(save_waveform_format_command(format))

    def query_waveform_format(self) -> SaveWaveformFormatState:
        raw = self.scpi.query(save_waveform_format_query()).strip()
        return SaveWaveformFormatState(parse_save_waveform_format(raw), raw)

    def configure_waveform_length(self, points: int) -> None:
        self.scpi.write(save_waveform_length_command(points))

    def query_waveform_length(self) -> SaveWaveformLengthState:
        raw = self.scpi.query(save_waveform_length_query()).strip()
        return SaveWaveformLengthState(parse_save_waveform_length(raw), raw)

    def query_waveform_length_max(self) -> SaveBooleanState:
        raw = self.scpi.query(save_waveform_length_max_query()).strip()
        return SaveBooleanState(parse_save_bool(raw), raw)

    def save_waveform(self, filename: str) -> SaveOperationResult:
        command = save_waveform_command(filename)
        self.scpi.write(command)
        original_timeout = self.scpi.timeout
        self.scpi.set_timeout(_SAVE_COMPLETION_TIMEOUT_MS)
        try:
            complete = parse_operation_complete(self.scpi.query(system_opc_query()))
        finally:
            self.scpi.set_timeout(original_timeout)
        if self.capabilities is not None and self.capabilities.series == "4000X":
            self._wait_for_remote_interface_readiness(original_timeout)
        return SaveOperationResult(
            operation="save-waveform",
            filename=filename,
            command=command,
            raw_operation_complete=complete.raw,
        )

    def _wait_for_remote_interface_readiness(
        self, original_timeout: int | None
    ) -> None:
        deadline = time.monotonic() + (_SAVE_COMPLETION_TIMEOUT_MS / 1000)
        try:
            while True:
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    raise SaveExportResponseError(
                        "4000X waveform save timed out waiting for "
                        "remote-interface readiness."
                    )
                self.scpi.set_timeout(
                    min(
                        _SAVE_COMPLETION_TIMEOUT_MS,
                        max(1, int(remaining_seconds * 1000)),
                    )
                )
                condition = parse_operation_condition(
                    self.scpi.query(operation_condition_query())
                )
                if condition & OPERATION_CONDITION_RUI_ENAB_MASK:
                    return
                time.sleep(
                    min(_SAVE_READINESS_POLL_INTERVAL_SECONDS, remaining_seconds)
                )
        finally:
            self.scpi.set_timeout(original_timeout)


def validate_save_quoted_string(value: str, *, label: str) -> str:
    """Validate a printable ASCII value for a quoted SAVE command."""

    if not isinstance(value, str):
        raise ParameterValidationError(f"{label} must be a string.")
    if not value.strip():
        raise ParameterValidationError(f"{label} must not be empty or whitespace-only.")
    for character in value:
        codepoint = ord(character)
        if codepoint < 0x20 or codepoint > 0x7E:
            raise ParameterValidationError(f"{label} must contain printable ASCII only.")
    if '"' in value:
        raise ParameterValidationError(f'{label} must not contain double quotes.')
    if ";" in value:
        raise ParameterValidationError(f"{label} must not contain semicolons.")
    return value


def validate_save_filename_base(name: str) -> str:
    """Validate a SAVE filename base without path or drive separators."""

    validate_save_quoted_string(name, label="Save filename")
    if any(separator in name for separator in ("/", "\\", ":")):
        raise ParameterValidationError(
            "Save filename must be a base name without path or drive separators."
        )
    return name


def quote_save_scpi_string(value: str, *, label: str) -> str:
    """Validate and quote one printable ASCII SAVE string value."""

    return f'"{validate_save_quoted_string(value, label=label)}"'


def save_pwd_command(path: str) -> str:
    return f":SAVE:PWD {quote_save_scpi_string(path, label='Save path')}"


def save_pwd_query() -> str:
    return ":SAVE:PWD?"


def save_filename_command(name: str) -> str:
    return f':SAVE:FILename "{validate_save_filename_base(name)}"'


def save_filename_query() -> str:
    return ":SAVE:FILename?"


def save_image_format_command(format: str) -> str:
    return f":SAVE:IMAGe:FORMat {_normalize_enum(format, _SAVE_IMAGE_FORMAT_COMMANDS, 'image format')}"


def save_image_format_query() -> str:
    return ":SAVE:IMAGe:FORMat?"


def save_image_palette_command(palette: str) -> str:
    return f":SAVE:IMAGe:PALette {_normalize_enum(palette, _SAVE_IMAGE_PALETTE_COMMANDS, 'image palette')}"


def save_image_palette_query() -> str:
    return ":SAVE:IMAGe:PALette?"


def save_image_ink_saver_command(enabled: bool) -> str:
    return f":SAVE:IMAGe:INKSaver {_save_bool_token(enabled)}"


def save_image_ink_saver_query() -> str:
    return ":SAVE:IMAGe:INKSaver?"


def save_image_factors_command(enabled: bool) -> str:
    return f":SAVE:IMAGe:FACTors {_save_bool_token(enabled)}"


def save_image_factors_query() -> str:
    return ":SAVE:IMAGe:FACTors?"


def save_image_command(filename: str) -> str:
    return f":SAVE:IMAGe {quote_save_scpi_string(filename, label='Save image filename')}"


def save_waveform_format_command(format: str) -> str:
    return f":SAVE:WAVeform:FORMat {_normalize_enum(format, _SAVE_WAVEFORM_FORMAT_COMMANDS, 'waveform format')}"


def save_waveform_format_query() -> str:
    return ":SAVE:WAVeform:FORMat?"


def save_waveform_length_command(points: int) -> str:
    return f":SAVE:WAVeform:LENGth {validate_save_waveform_length(points)}"


def save_waveform_length_query() -> str:
    return ":SAVE:WAVeform:LENGth?"


def save_waveform_length_max_query() -> str:
    return ":SAVE:WAVeform:LENGth:MAX?"


def save_waveform_command(filename: str) -> str:
    return f":SAVE:WAVeform {quote_save_scpi_string(filename, label='Save waveform filename')}"


def validate_save_waveform_length(points: int) -> int:
    """Validate the common minimum waveform save length."""

    if isinstance(points, bool) or not isinstance(points, int):
        raise ParameterValidationError("Save waveform length must be an integer.")
    if points < 100:
        raise ParameterValidationError("Save waveform length must be at least 100 points.")
    return points


def parse_save_quoted_readback(raw: str) -> str:
    normalized = raw.strip()
    if normalized.startswith('"') or normalized.endswith('"'):
        if len(normalized) < 2 or not (
            normalized.startswith('"') and normalized.endswith('"')
        ):
            raise SaveExportResponseError(f"Could not parse SAVE string response: {raw!r}")
        normalized = normalized[1:-1]
    return normalized


def parse_save_image_format(raw: str) -> str:
    return _parse_enum(raw, _SAVE_IMAGE_FORMAT_READBACKS, "image format")


def parse_save_image_palette(raw: str) -> str:
    return _parse_enum(raw, _SAVE_IMAGE_PALETTE_READBACKS, "image palette")


def parse_save_waveform_format(raw: str) -> str:
    return _parse_enum(raw, _SAVE_WAVEFORM_FORMAT_READBACKS, "waveform format")


def parse_save_bool(raw: str) -> bool:
    normalized = raw.strip().upper()
    if normalized in {"1", "+1", "ON"}:
        return True
    if normalized in {"0", "+0", "OFF"}:
        return False
    raise SaveExportResponseError(f"Could not parse SAVE boolean response: {raw!r}")


def parse_save_waveform_length(raw: str) -> int:
    normalized = raw.strip()
    try:
        points = int(normalized)
    except ValueError as exc:
        raise SaveExportResponseError(
            f"Could not parse SAVE waveform length response: {raw!r}"
        ) from exc
    if points < 100:
        raise SaveExportResponseError(
            f"Could not parse SAVE waveform length response: {raw!r}"
        )
    return points


def _normalize_enum(value: str, mapping: dict[str, str], label: str) -> str:
    if not isinstance(value, str) or value not in mapping:
        raise ParameterValidationError(
            f"Save {label} must be one of: {', '.join(mapping)}."
        )
    return mapping[value]


def _parse_enum(raw: str, mapping: dict[str, str], label: str) -> str:
    try:
        return mapping[raw.strip().upper()]
    except KeyError as exc:
        raise SaveExportResponseError(
            f"Could not parse SAVE {label} response: {raw!r}"
        ) from exc


def _save_bool_token(enabled: bool) -> str:
    if not isinstance(enabled, bool):
        raise ParameterValidationError("Save enabled value must be a boolean.")
    return "1" if enabled else "0"
