"""Display-only Product Live connections projected from Core support policy."""

from scopes_tool_core.identity import PHYSICAL_MODEL_REGISTRY, VENDOR_REGISTRY
from scopes_tool_core.support_policy import product_live_transport_scopes


def supported_devices_payload(backend: str = "system_visa") -> list[dict[str, str | list[str]]]:
    # This projection never authorizes execution; Core checks detected IDN.
    approved = product_live_transport_scopes(backend)
    vendors = {vendor.vendor_id: vendor.display_name for vendor in VENDOR_REGISTRY}
    return [
        {
            "vendor": vendors[model.vendor_id],
            "model": model.canonical_model,
            "connections": [
                transport.upper()
                for transport in ("usb", "tcpip")
                if (model.model_id, transport) in approved
            ],
        }
        for model in PHYSICAL_MODEL_REGISTRY
        if any(model.model_id == model_id for model_id, _ in approved)
    ]
