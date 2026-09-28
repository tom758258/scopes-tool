"""Driver selection for canonical physical models."""

from __future__ import annotations

from .errors import UnsupportedModelError
from .identity import PhysicalModelInfo
from .scope import Oscilloscope
from .tektronix import TektronixOscilloscope
from .scpi import SCPIBackend

DriverImplementation = type[Oscilloscope]

DRIVER_REGISTRY: dict[str, DriverImplementation] = {
    "keysight-infiniivision": Oscilloscope,
    "tektronix": TektronixOscilloscope,
}


def driver_for_physical_model(
    physical_model: PhysicalModelInfo,
) -> DriverImplementation:
    """Return the registered driver implementation for a physical model."""

    driver = DRIVER_REGISTRY.get(physical_model.driver_id)
    if driver is None:
        raise UnsupportedModelError(
            f"Physical model {physical_model.model_id} references unknown or "
            f"unregistered driver ID: {physical_model.driver_id!r}"
        )
    return driver


def scope_for_physical_model(
    physical_model: PhysicalModelInfo,
    backend: SCPIBackend,
    *,
    existing_scope: Oscilloscope | None = None,
) -> Oscilloscope:
    """Return or construct the registered implementation for a physical model."""

    driver = driver_for_physical_model(physical_model)
    if existing_scope is not None and isinstance(existing_scope, driver):
        return existing_scope
    selected_scope = driver(backend)
    if existing_scope is not None:
        selected_scope.idn = getattr(existing_scope, "idn", None)
        selected_scope.capabilities = getattr(
            existing_scope,
            "capabilities",
            None,
        )
    return selected_scope


def driver_for_capabilities(capabilities):
    """Resolve a selected physical identity; legacy profiles use the base driver."""
    if capabilities.physical_model_id is None:
        if capabilities.series not in {"2000X", "3000X", "4000X", "6000X"}:
            raise UnsupportedModelError("Planning requires a registered physical model")
        return Oscilloscope
    from .identity import physical_model_for_id
    return driver_for_physical_model(physical_model_for_id(capabilities.physical_model_id))
