"""Core-owned backend-only live support policy (not a release matrix)."""

from __future__ import annotations

from .errors import OscilloscopeError
from .visa_backend import (
    BACKEND_PYVISA_BT,
    BACKEND_PYVISA_PY,
    normalize_backend,
)

SUPPORT_POLICY_MODE_PRODUCT = "product"
SUPPORT_POLICY_MODE_VALIDATION = "validation"

# Pending contributor validation candidates; NOT Product-open or live evidence.
PYVISA_PY_PENDING_SCOPES = frozenset({
    ("keysight-dsox2004a", "usb"),
    ("keysight-dsox3024a", "usb"),
    ("keysight-dsox4024a", "usb"),
    ("keysight-dsox4034a", "usb"),
    ("tektronix-tbs1052b", "usb"),
    ("keysight-dsox4024a", "tcpip"),
    ("keysight-dsox4034a", "tcpip"),
    ("tektronix-tbs2074", "tcpip"),
})

# Connection diagnostics are not a declaration of Product Live support.
BACKEND_POLICY_DIAGNOSTICS = frozenset({"identify", "list-resources"})


def infer_transport_scope(resource: str | None) -> str:
    """Classify a caller-provided VISA resource without opening it."""

    prefix = (resource or "").strip().split("::", 1)[0].upper()
    if prefix == "USB" or (prefix.startswith("USB") and prefix[3:].isdigit()):
        return "usb"
    if prefix == "TCPIP" or (prefix.startswith("TCPIP") and prefix[5:].isdigit()):
        return "tcpip"
    return "unknown"


def ensure_backend_live_support(
    *,
    visa_library: str | None,
    resource: str | None,
    policy_mode: str = SUPPORT_POLICY_MODE_PRODUCT,
    command: str | None = None,
    detected_model_id: str | None = None,
) -> None:
    """Apply backend restrictions before opening VISA and after live IDN.

    Pending @py Validation Mode calls this first to check transport, and then
    again with the *detected* physical model ID before command-specific SCPI.
    Never substitute a planning model or an expected-model hint for live IDN.
    """

    if policy_mode not in {SUPPORT_POLICY_MODE_PRODUCT, SUPPORT_POLICY_MODE_VALIDATION}:
        raise OscilloscopeError(f"unsupported backend support policy mode: {policy_mode}")

    backend = normalize_backend(visa_library)
    if policy_mode == SUPPORT_POLICY_MODE_VALIDATION and backend != BACKEND_PYVISA_PY:
        raise OscilloscopeError("Contributor Validation Mode is restricted to @py")
    if command in BACKEND_POLICY_DIAGNOSTICS:
        return

    if backend == BACKEND_PYVISA_BT:
        raise OscilloscopeError(
            "@bt live backend is not open for Product or contributor validation"
        )
    if backend != BACKEND_PYVISA_PY:
        # Preserve existing System VISA and custom VISA behavior.
        return
    if policy_mode == SUPPORT_POLICY_MODE_PRODUCT:
        raise OscilloscopeError(
            "@py Product Live support is Pending; use registered contributor validation"
        )

    transport = infer_transport_scope(resource)
    if transport not in {"usb", "tcpip"}:
        raise OscilloscopeError(
            f"@py contributor validation has no registered transport scope: {transport}"
        )
    if detected_model_id is not None and (
        detected_model_id, transport
    ) not in PYVISA_PY_PENDING_SCOPES:
        raise OscilloscopeError(
            "@py contributor validation has no registered Pending scope for "
            f"model={detected_model_id}, transport={transport}"
        )
