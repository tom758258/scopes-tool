"""Parsing and model detection for `*IDN?` responses."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

from .errors import IDNParseError, UnsupportedModelError

if TYPE_CHECKING:
    from .identity import PhysicalModelInfo

_MODEL_RE = re.compile(r"^(?:DSO|MSO)X(?P<series>[234])\d{3}[A-Z]?$", re.IGNORECASE)
_MODEL_KEY_RE = re.compile(r"[^A-Z0-9]")


@dataclass(frozen=True)
class IDN:
    """Parsed fields from an oscilloscope `*IDN?` response."""

    vendor: str
    model: str
    serial: str
    firmware: str
    raw: str

    @property
    def series(self) -> str | None:
        """Return the registered series, if this model is recognized."""

        detected = detect_series(self.model)
        if detected is not None:
            return detected
        try:
            return self.physical_model.series
        except UnsupportedModelError:
            return None

    @property
    def physical_model(self) -> PhysicalModelInfo:
        """Return the registered canonical physical model identity."""

        from .identity import resolve_physical_model_identity

        return resolve_physical_model_identity(self.vendor, self.model)

    @property
    def model_id(self) -> str:
        """Return the registered canonical physical model ID."""

        return self.physical_model.model_id


def parse_idn(response: str) -> IDN:
    """Parse a standard four-field `*IDN?` response."""

    raw = response.strip()
    parts = [part.strip() for part in raw.split(",", 3)]
    if len(parts) != 4 or not all(parts):
        raise IDNParseError(
            "Expected `*IDN?` response with vendor, model, serial, and firmware fields."
        )

    vendor, model, serial, firmware = parts
    return IDN(
        vendor=vendor,
        model=model.upper(),
        serial=serial,
        firmware=firmware,
        raw=raw,
    )


def detect_series(model: str) -> str | None:
    """Detect 2000X, 3000X, or 4000X series from a Keysight model string."""

    match = _MODEL_RE.match(normalize_model_key(model))
    if match is None:
        return None
    return f"{match.group('series')}000X"


def normalize_model_key(model: str) -> str:
    """Return a punctuation-free model key for matching Keysight IDN variants."""

    return _MODEL_KEY_RE.sub("", model.strip().upper())
