"""Display-only supported connections, independent of runtime admission."""

from scopes_tool_core.identity import PHYSICAL_MODEL_REGISTRY, VENDOR_REGISTRY
from scopes_tool_core.support_policy import PYVISA_PY_PENDING_SCOPES


# Approved display scope; never use this list to admit or reject operations.
DISPLAY_CONNECTIONS = {
    "keysight-dsox2004a": ("USB",),
    "keysight-dsox3024a": ("USB",),
    "keysight-dsox4024a": ("USB", "TCPIP"),
    "keysight-dsox4034a": ("USB",),
}


def supported_devices_payload(backend: str = "system_visa") -> list[dict[str, str | list[str]]]:
    connections = DISPLAY_CONNECTIONS
    if backend == "@py":
        connections = {
            model.model_id: tuple(
                transport.upper() for transport in ("usb", "tcpip")
                if (model.model_id, transport) in PYVISA_PY_PENDING_SCOPES
            )
            for model in PHYSICAL_MODEL_REGISTRY
        }
    vendors = {vendor.vendor_id: vendor.display_name for vendor in VENDOR_REGISTRY}
    return [
        {
            "vendor": vendors[model.vendor_id],
            "model": model.canonical_model,
            "connections": list(connections[model.model_id]),
            **({"status": "pending"} if backend == "@py" else {}),
        }
        for model in PHYSICAL_MODEL_REGISTRY
        if connections.get(model.model_id)
    ]
