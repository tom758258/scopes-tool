"""Core-owned raw and live VISA resource discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .idn import IDN, parse_idn
from .identity import resolve_physical_model_identity
from .visa_backend import (
    VisaResourceListing,
    is_asrl_resource,
    list_visa_resources,
    verify_asrl_resource_live,
    verify_visa_resource_live,
)


@dataclass(frozen=True)
class VisaLiveResource:
    """A VISA resource that answered a valid read-only `*IDN?` probe."""

    name: str
    interface: str
    reachable: bool
    idn: IDN
    model_id: str | None

    def to_payload(self) -> dict[str, Any]:
        """Return the frontend-safe structured discovery representation."""

        return {
            "name": self.name,
            "interface": self.interface,
            "reachable": self.reachable,
            "idn": {
                "raw": self.idn.raw,
                "manufacturer": self.idn.vendor,
                "model": self.idn.model,
                "serial": self.idn.serial,
                "firmware": self.idn.firmware,
            },
            "model_id": self.model_id,
        }


@dataclass(frozen=True)
class VisaLiveResourceListing:
    """Live-only VISA resources and the backend used to enumerate them."""

    resources: tuple[VisaLiveResource, ...]
    backend: str


def resource_interface(resource: str) -> str:
    """Classify a VISA resource using stable Core-owned transport prefixes."""

    normalized = resource.strip().upper()
    for interface in ("USB", "TCPIP", "ASRL", "GPIB"):
        if normalized.startswith(interface):
            return interface
    return "UNKNOWN"


def discover_visa_resources(
    *,
    live_only: bool = False,
    visa_library: str | None = None,
    serial_read_termination: str | None = None,
    serial_write_termination: str | None = None,
) -> VisaResourceListing | VisaLiveResourceListing:
    """Enumerate VISA resources, optionally retaining only live responders."""

    listing = list_visa_resources(visa_library=visa_library)
    if not live_only:
        return listing

    live_resources: list[VisaLiveResource] = []
    for resource in listing.resources:
        verification = (
            verify_asrl_resource_live(
                resource,
                visa_library=visa_library,
                serial_read_termination=serial_read_termination,
                serial_write_termination=serial_write_termination,
            )
            if is_asrl_resource(resource)
            else verify_visa_resource_live(
                resource,
                visa_library=visa_library,
                serial_read_termination=serial_read_termination,
                serial_write_termination=serial_write_termination,
            )
        )
        if not verification.live or not verification.raw_idn:
            continue
        try:
            idn = parse_idn(verification.raw_idn)
        except ValueError:
            continue
        try:
            model_id = resolve_physical_model_identity(idn.vendor, idn.model).model_id
        except ValueError:
            model_id = None
        live_resources.append(
            VisaLiveResource(
                name=resource,
                interface=resource_interface(resource),
                reachable=True,
                idn=idn,
                model_id=model_id,
            )
        )
    return VisaLiveResourceListing(
        resources=tuple(live_resources),
        backend=listing.backend,
    )
