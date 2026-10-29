"""Core-owned Product Live connection scopes and contributor validation policy."""

from __future__ import annotations

from .errors import OscilloscopeError
from .visa_backend import (
    BACKEND_PYVISA_BT,
    BACKEND_PYVISA_PY,
    BACKEND_SYSTEM_VISA,
    normalize_backend,
)

SUPPORT_POLICY_MODE_PRODUCT = "product"
SUPPORT_POLICY_MODE_VALIDATION = "validation"

# Product scope is exact by detected physical model, transport, and VISA backend.
# Capability and hardware-option validation remain independently authoritative.
PRODUCT_LIVE_CONNECTIONS = {
    BACKEND_SYSTEM_VISA: frozenset({
        ("keysight-dsox2004a", "usb"),
        ("keysight-dsox3024a", "usb"),
        ("keysight-dsox4024a", "usb"),
        ("keysight-dsox4024a", "tcpip"),
        ("keysight-dsox4034a", "usb"),
        ("keysight-dsox4034a", "tcpip"),
        ("tektronix-tbs2074", "usb"),
        ("tektronix-tbs2074", "tcpip"),
        ("tektronix-tbs1052b", "usb"),
        ("tektronix-tds2024b", "usb"),
    }),
    BACKEND_PYVISA_PY: frozenset({
        ("keysight-dsox4024a", "tcpip"),
        ("keysight-dsox4034a", "tcpip"),
        ("tektronix-tbs2074", "tcpip"),
    }),
}

# Validation-only connections are exact by backend, detected model, and transport.
# They do not grant Product access or bypass capabilities.
PENDING_LIVE_CONNECTIONS = {
    BACKEND_PYVISA_PY: frozenset({
        ("keysight-dsox4024a", "usb"),
        ("keysight-dsox4034a", "usb"),
        ("tektronix-tbs2074", "usb"),
    }),
}

# Connection diagnostics are not declarations of Product Live support.
BACKEND_POLICY_DIAGNOSTICS = frozenset({"identify", "list-resources"})


def infer_transport_scope(resource: str | None) -> str:
    """Classify a caller-provided VISA resource without opening it."""

    prefix = (resource or "").strip().split("::", 1)[0].upper()
    if prefix == "USB" or (prefix.startswith("USB") and prefix[3:].isdigit()):
        return "usb"
    if prefix == "TCPIP" or (prefix.startswith("TCPIP") and prefix[5:].isdigit()):
        return "tcpip"
    return "unknown"


def product_live_transport_scopes(visa_library: str | None) -> frozenset[tuple[str, str]]:
    """Return Product-open connections for display and Core admission."""

    return PRODUCT_LIVE_CONNECTIONS.get(normalize_backend(visa_library), frozenset())


def ensure_backend_live_support(
    *,
    visa_library: str | None,
    resource: str | None,
    policy_mode: str = SUPPORT_POLICY_MODE_PRODUCT,
    command: str | None = None,
    detected_model_id: str | None = None,
) -> None:
    """Gate live sessions before VISA open and again after detected *IDN?.

    Without a detected model, only backend/transport can be checked. A live
    operation must be checked again using the actual IDN before business SCPI.
    Diagnostics remain available without asserting Product support.
    """

    if policy_mode not in {SUPPORT_POLICY_MODE_PRODUCT, SUPPORT_POLICY_MODE_VALIDATION}:
        raise OscilloscopeError(f"unsupported backend support policy mode: {policy_mode}")

    backend = normalize_backend(visa_library)
    if command in BACKEND_POLICY_DIAGNOSTICS:
        return

    transport = infer_transport_scope(resource)
    connections = product_live_transport_scopes(visa_library)
    if policy_mode == SUPPORT_POLICY_MODE_VALIDATION:
        connections = connections | PENDING_LIVE_CONNECTIONS.get(backend, frozenset())
        if not connections:
            raise OscilloscopeError(
                f"VISA backend {backend} has no registered scope for contributor validation"
            )
        if transport not in {connection_transport for _, connection_transport in connections}:
            raise OscilloscopeError(
                f"VISA backend {backend} contributor validation has no registered transport "
                f"scope: {transport}"
            )
        if detected_model_id is not None and (detected_model_id, transport) not in connections:
            raise OscilloscopeError(
                "Contributor validation has no registered scope for "
                f"model={detected_model_id}, transport={transport}, backend={backend}"
            )
        return

    if backend == BACKEND_PYVISA_BT:
        raise OscilloscopeError("@bt live backend is not open for Product or contributor validation")
    if not connections:
        raise OscilloscopeError(f"VISA backend {backend} is not open for Product Live")
    if transport not in {connection_transport for _, connection_transport in connections}:
        raise OscilloscopeError(
            f"VISA backend {backend} has no Product Live support for transport={transport}"
        )
    if detected_model_id is not None and (detected_model_id, transport) not in connections:
        raise OscilloscopeError(
            "No Product Live support for "
            f"model={detected_model_id}, transport={transport}, backend={backend}"
        )
