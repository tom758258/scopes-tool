"""Display-only supported connections, independent of runtime admission."""

from scopes_tool_core.identity import PHYSICAL_MODEL_REGISTRY, VENDOR_REGISTRY


# Approved display scope; never use this list to admit or reject operations.
DISPLAY_CONNECTIONS = {
    "keysight-dsox2004a": ("USB",),
    "keysight-dsox3024a": ("USB",),
    "keysight-dsox4024a": ("USB", "TCPIP"),
    "keysight-dsox4034a": ("USB",),
}


def supported_devices_payload() -> list[dict[str, str | list[str]]]:
    vendors = {vendor.vendor_id: vendor.display_name for vendor in VENDOR_REGISTRY}
    return [
        {
            "vendor": vendors[model.vendor_id],
            "model": model.canonical_model,
            "connections": list(DISPLAY_CONNECTIONS[model.model_id]),
        }
        for model in PHYSICAL_MODEL_REGISTRY
        if DISPLAY_CONNECTIONS.get(model.model_id)
    ]
