"""Canonical vendor and physical model identities."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .errors import UnsupportedModelError


@dataclass(frozen=True)
class VendorInfo:
    """Canonical identity for an oscilloscope vendor."""

    vendor_id: str
    display_name: str
    canonical_manufacturer: str
    manufacturer_aliases: tuple[str, ...] = ()
    require_registered_model_for_identify: bool = False


@dataclass(frozen=True)
class PhysicalModelInfo:
    """Canonical identity for a physical oscilloscope model."""

    model_id: str
    vendor_id: str
    canonical_model: str
    display_name: str
    series: str
    capability_profile_id: str
    driver_id: str
    model_aliases: tuple[str, ...] = ()


VENDOR_REGISTRY = (
    VendorInfo(
        vendor_id="keysight",
        display_name="Keysight",
        canonical_manufacturer="KEYSIGHT TECHNOLOGIES",
        manufacturer_aliases=(
            "KEYSIGHT",
            "AGILENT TECHNOLOGIES",
            "AGILENT",
        ),
    ),
    VendorInfo(
        vendor_id="tektronix",
        display_name="Tektronix",
        canonical_manufacturer="TEKTRONIX",
        require_registered_model_for_identify=True,
    ),
)

PHYSICAL_MODEL_REGISTRY = (
    PhysicalModelInfo(
        model_id="tektronix-tbs2074b",
        vendor_id="tektronix",
        canonical_model="TBS2074B",
        display_name="Tektronix TBS2074B",
        series="TBS2000B",
        capability_profile_id="tektronix-tbs2074b",
        driver_id="tektronix",
    ),
    PhysicalModelInfo(
        model_id="tektronix-tds2024b",
        vendor_id="tektronix",
        canonical_model="TDS2024B",
        display_name="Tektronix TDS2024B",
        series="TDS2000B",
        capability_profile_id="tektronix-tds2024b",
        driver_id="tektronix",
    ),
    PhysicalModelInfo(
        model_id="tektronix-tbs1052b",
        vendor_id="tektronix",
        canonical_model="TBS1052B",
        display_name="Tektronix TBS1052B",
        series="TBS1000B",
        capability_profile_id="tektronix-tbs1052b",
        driver_id="tektronix",
    ),
    PhysicalModelInfo(
        model_id="keysight-dsox2004a",
        vendor_id="keysight",
        canonical_model="DSOX2004A",
        display_name="Keysight DSO-X 2004A",
        series="2000X",
        capability_profile_id="keysight-infiniivision-2000x",
        driver_id="keysight-infiniivision",
    ),
    PhysicalModelInfo(
        model_id="keysight-dsox3024a",
        vendor_id="keysight",
        canonical_model="DSOX3024A",
        display_name="Keysight DSO-X 3024A",
        series="3000X",
        capability_profile_id="keysight-infiniivision-3000x",
        driver_id="keysight-infiniivision",
    ),
    PhysicalModelInfo(
        model_id="keysight-dsox4024a",
        vendor_id="keysight",
        canonical_model="DSOX4024A",
        display_name="Keysight DSO-X 4024A",
        series="4000X",
        capability_profile_id="keysight-infiniivision-4000x",
        driver_id="keysight-infiniivision",
    ),
    PhysicalModelInfo(
        model_id="keysight-dsox4034a",
        vendor_id="keysight",
        canonical_model="DSOX4034A",
        display_name="Keysight DSO-X 4034A",
        series="4000X",
        capability_profile_id="keysight-infiniivision-4000x",
        driver_id="keysight-infiniivision",
    ),
)

_MODEL_KEY_RE = re.compile(r"[^A-Z0-9]")


def _normalize_manufacturer_key(manufacturer: str) -> str:
    return " ".join(manufacturer.strip().upper().split())


def _normalize_model_key(model: str) -> str:
    return _MODEL_KEY_RE.sub("", model.strip().upper())


def _build_vendor_index(
    vendors: tuple[VendorInfo, ...],
) -> dict[str, VendorInfo]:
    index: dict[str, VendorInfo] = {}
    vendor_ids: set[str] = set()
    for vendor in vendors:
        if vendor.vendor_id in vendor_ids:
            raise RuntimeError(f"Duplicate vendor ID: {vendor.vendor_id}")
        vendor_ids.add(vendor.vendor_id)
        for manufacturer in (
            vendor.canonical_manufacturer,
            *vendor.manufacturer_aliases,
        ):
            key = _normalize_manufacturer_key(manufacturer)
            existing = index.get(key)
            if existing is not None and existing != vendor:
                raise RuntimeError(f"Ambiguous manufacturer identity: {manufacturer}")
            index[key] = vendor
    return index


def _build_model_index(
    vendors: tuple[VendorInfo, ...],
    models: tuple[PhysicalModelInfo, ...],
) -> dict[tuple[str, str], PhysicalModelInfo]:
    vendor_ids = {vendor.vendor_id for vendor in vendors}
    model_ids: set[str] = set()
    index: dict[tuple[str, str], PhysicalModelInfo] = {}
    for model in models:
        if model.vendor_id not in vendor_ids:
            raise RuntimeError(
                f"Physical model {model.model_id} references unknown vendor "
                f"{model.vendor_id}"
            )
        if model.model_id in model_ids:
            raise RuntimeError(f"Duplicate physical model ID: {model.model_id}")
        model_ids.add(model.model_id)
        for model_name in (model.canonical_model, *model.model_aliases):
            key = (model.vendor_id, _normalize_model_key(model_name))
            existing = index.get(key)
            if existing is not None and existing != model:
                raise RuntimeError(
                    "Ambiguous physical model identity for vendor "
                    f"{model.vendor_id}: {model_name}"
                )
            index[key] = model
    return index


def _build_model_id_index(
    models: tuple[PhysicalModelInfo, ...],
) -> dict[str, PhysicalModelInfo]:
    index: dict[str, PhysicalModelInfo] = {}
    for model in models:
        if model.model_id in index:
            raise RuntimeError(f"Duplicate physical model ID: {model.model_id}")
        index[model.model_id] = model
    return index


def _build_model_name_index(
    models: tuple[PhysicalModelInfo, ...],
) -> dict[str, tuple[PhysicalModelInfo, ...]]:
    matches: dict[str, list[PhysicalModelInfo]] = {}
    for model in models:
        for model_name in (model.canonical_model, *model.model_aliases):
            key = _normalize_model_key(model_name)
            candidates = matches.setdefault(key, [])
            if model not in candidates:
                candidates.append(model)
    return {key: tuple(candidates) for key, candidates in matches.items()}


_VENDOR_BY_MANUFACTURER = _build_vendor_index(VENDOR_REGISTRY)
_PHYSICAL_MODEL_BY_VENDOR_AND_MODEL = _build_model_index(
    VENDOR_REGISTRY,
    PHYSICAL_MODEL_REGISTRY,
)
_PHYSICAL_MODEL_BY_ID = _build_model_id_index(PHYSICAL_MODEL_REGISTRY)
_PHYSICAL_MODELS_BY_MODEL_NAME = _build_model_name_index(PHYSICAL_MODEL_REGISTRY)


def identify_requires_registered_model(manufacturer: str) -> bool:
    """Return whether identify must reject an unregistered model for this vendor."""

    vendor = _VENDOR_BY_MANUFACTURER.get(_normalize_manufacturer_key(manufacturer))
    return vendor is not None and vendor.require_registered_model_for_identify


def resolve_physical_model_identity(
    manufacturer: str,
    model: str,
) -> PhysicalModelInfo:
    """Resolve manufacturer and model strings to a canonical physical model."""

    vendor = _VENDOR_BY_MANUFACTURER.get(
        _normalize_manufacturer_key(manufacturer)
    )
    if vendor is None:
        raise UnsupportedModelError(
            f"Unsupported oscilloscope manufacturer: {manufacturer}"
        )

    physical_model = _PHYSICAL_MODEL_BY_VENDOR_AND_MODEL.get(
        (vendor.vendor_id, _normalize_model_key(model))
    )
    if physical_model is None:
        raise UnsupportedModelError(
            f"Unsupported physical oscilloscope model: {model}"
        )
    return physical_model


def canonical_physical_model_id(manufacturer: str, model: str) -> str:
    """Return the canonical physical model ID for an instrument identity."""

    return resolve_physical_model_identity(manufacturer, model).model_id


def physical_model_for_id(model_id: str) -> PhysicalModelInfo:
    """Return the registered physical model for a canonical model ID."""

    physical_model = _PHYSICAL_MODEL_BY_ID.get(model_id)
    if physical_model is None:
        raise UnsupportedModelError(
            f"Unsupported physical oscilloscope model ID: {model_id}"
        )
    return physical_model


def resolve_registered_model_name(model: str) -> PhysicalModelInfo:
    """Resolve a model-only name when it identifies exactly one registered model."""

    matches = _PHYSICAL_MODELS_BY_MODEL_NAME.get(_normalize_model_key(model), ())
    if len(matches) != 1:
        raise UnsupportedModelError(
            f"Unsupported or ambiguous registered oscilloscope model: {model}"
        )
    return matches[0]
