"""No-hardware acceptance tests for exact live connection support."""

from __future__ import annotations

import pytest

from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.support_policy import (
    PENDING_LIVE_CONNECTIONS,
    PRODUCT_LIVE_CONNECTIONS,
    SUPPORT_POLICY_MODE_VALIDATION,
    ensure_backend_live_support,
    infer_transport_scope,
    product_live_transport_scopes,
)


@pytest.mark.parametrize(
    ("resource", "transport"),
    [
        ("USB0::FAKE::INSTR", "usb"),
        ("usb1::FAKE::INSTR", "usb"),
        ("USB::FAKE::INSTR", "usb"),
        ("usb::FAKE::INSTR", "usb"),
        ("TCPIP0::FAKE::INSTR", "tcpip"),
        ("TCPIP::FAKE::INSTR", "tcpip"),
        ("tcpip::FAKE::INSTR", "tcpip"),
        ("USBX::FAKE::INSTR", "unknown"),
        ("TCPIPX::FAKE::INSTR", "unknown"),
        ("tcpip1::FAKE::INSTR", "tcpip"),
        ("GPIB0::1::INSTR", "unknown"),
        ("ASRL1::INSTR", "unknown"),
        ("", "unknown"),
    ],
)
def test_transport_scope_classification(resource, transport):
    assert infer_transport_scope(resource) == transport


def test_product_and_pending_connection_inventories_are_exact():
    assert product_live_transport_scopes("system_visa") == {
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
    }
    assert product_live_transport_scopes("@py") == {
        ("keysight-dsox4024a", "tcpip"),
        ("keysight-dsox4034a", "tcpip"),
        ("tektronix-tbs2074", "tcpip"),
    }
    assert PENDING_LIVE_CONNECTIONS == {
        "pyvisa_py": {
            ("keysight-dsox4024a", "usb"),
            ("keysight-dsox4034a", "usb"),
            ("tektronix-tbs2074", "usb"),
        },
    }
    assert not (PENDING_LIVE_CONNECTIONS["pyvisa_py"] & product_live_transport_scopes("@py"))


@pytest.mark.parametrize(
    ("model_id", "transport"),
    sorted(PENDING_LIVE_CONNECTIONS["pyvisa_py"]),
)
@pytest.mark.parametrize("interface_number", ("", "0"))
@pytest.mark.parametrize("selector", ("@py", "pyvisa_py"))
def test_registered_pending_scope_allows_validation(
    model_id, transport, interface_number, selector
):
    resource = f"{'USB' if transport == 'usb' else 'TCPIP'}{interface_number}::FAKE::INSTR"
    ensure_backend_live_support(
        visa_library=selector,
        resource=resource,
        policy_mode=SUPPORT_POLICY_MODE_VALIDATION,
    )
    ensure_backend_live_support(
        visa_library=selector,
        resource=resource,
        policy_mode=SUPPORT_POLICY_MODE_VALIDATION,
        detected_model_id=model_id,
    )


@pytest.mark.parametrize("selector", ("@bt", "@ivi", "custom"))
@pytest.mark.parametrize("policy_mode", ("product", "validation"))
def test_unregistered_backend_rejects_before_open(selector, policy_mode):
    with pytest.raises(OscilloscopeError, match="not open|no registered scope"):
        ensure_backend_live_support(
            visa_library=selector, resource="USB0::FAKE::INSTR", policy_mode=policy_mode,
        )


@pytest.mark.parametrize("selector", (None, "", "system_visa"))
@pytest.mark.parametrize("policy_mode", ("product", "validation"))
def test_system_visa_product_support(selector, policy_mode):
    ensure_backend_live_support(
        visa_library=selector,
        resource="USB0::FAKE::INSTR",
        detected_model_id="tektronix-tds2024b",
        policy_mode=policy_mode,
    )


@pytest.mark.parametrize("backend, connections", sorted(PRODUCT_LIVE_CONNECTIONS.items()))
@pytest.mark.parametrize("policy_mode", ("product", "validation"))
def test_all_product_connections_allow_detected_identity(backend, connections, policy_mode):
    for model_id, transport in connections:
        resource = f"{transport.upper()}0::FAKE::INSTR"
        ensure_backend_live_support(
            visa_library=backend, resource=resource, policy_mode=policy_mode,
        )
        ensure_backend_live_support(
            visa_library=backend, resource=resource, detected_model_id=model_id,
            policy_mode=policy_mode,
        )


@pytest.mark.parametrize("backend, model_id, transport", [
    ("system_visa", "keysight-dsox2004a", "tcpip"),
    ("system_visa", "keysight-dsox3024a", "tcpip"),
    ("system_visa", "tektronix-tbs1052b", "tcpip"),
    ("system_visa", "tektronix-tds2024b", "tcpip"),
    ("@py", "keysight-dsox2004a", "usb"),
    ("@py", "keysight-dsox2004a", "tcpip"),
    ("@py", "keysight-dsox3024a", "usb"),
    ("@py", "keysight-dsox3024a", "tcpip"),
    ("@py", "keysight-dsox4024a", "usb"),
    ("@py", "keysight-dsox4034a", "usb"),
    ("@py", "tektronix-tbs2074", "usb"),
    ("@py", "tektronix-tbs1052b", "usb"),
    ("@py", "tektronix-tbs1052b", "tcpip"),
    ("@py", "tektronix-tds2024b", "usb"),
    ("@py", "tektronix-tds2024b", "tcpip"),
])
def test_unreleased_model_connection_is_rejected_after_idn(backend, model_id, transport):
    with pytest.raises(OscilloscopeError, match="No Product Live support|no Product Live support"):
        ensure_backend_live_support(
            visa_library=backend,
            resource=f"{transport.upper()}0::FAKE::INSTR",
            detected_model_id=model_id,
        )


@pytest.mark.parametrize("selector, resource", [
    ("system_visa", "GPIB0::FAKE::INSTR"),
    ("@py", "USB0::FAKE::INSTR"),
    ("@py", "ASRL1::INSTR"),
])
def test_unreleased_product_transport_is_rejected_before_open(selector, resource):
    with pytest.raises(OscilloscopeError, match="no Product Live support"):
        ensure_backend_live_support(visa_library=selector, resource=resource)


@pytest.mark.parametrize(
    ("backend", "model_id", "transport"),
    [
        ("system_visa", "keysight-dsox2004a", "tcpip"),
        ("system_visa", "keysight-dsox3024a", "tcpip"),
        ("system_visa", "tektronix-tbs1052b", "tcpip"),
        ("system_visa", "tektronix-tds2024b", "tcpip"),
        ("@py", "keysight-dsox2004a", "usb"),
        ("@py", "keysight-dsox2004a", "tcpip"),
        ("@py", "keysight-dsox3024a", "usb"),
        ("@py", "keysight-dsox3024a", "tcpip"),
        ("@py", "tektronix-tbs1052b", "usb"),
        ("@py", "tektronix-tbs1052b", "tcpip"),
        ("@py", "tektronix-tds2024b", "usb"),
        ("@py", "tektronix-tds2024b", "tcpip"),
        ("system_visa", "", "usb"),
        ("@py", "unregistered-model", "usb"),
    ],
)
def test_unregistered_scope_rejects_after_live_idn(backend, model_id, transport):
    with pytest.raises(OscilloscopeError, match="no registered scope"):
        ensure_backend_live_support(
            visa_library=backend,
            resource=f"{transport.upper()}::FAKE::INSTR",
            policy_mode=SUPPORT_POLICY_MODE_VALIDATION,
            detected_model_id=model_id,
        )


@pytest.mark.parametrize("selector", (None, "@py"))
@pytest.mark.parametrize("resource", ("ASRL1::INSTR", None, ""))
def test_validation_unknown_transport_rejects_before_open(selector, resource):
    with pytest.raises(OscilloscopeError, match="no registered transport"):
        ensure_backend_live_support(
            visa_library=selector,
            resource=resource,
            policy_mode=SUPPORT_POLICY_MODE_VALIDATION,
        )


@pytest.mark.parametrize("selector", ("@py", "@bt"))
@pytest.mark.parametrize("command", ("identify", "list-resources"))
@pytest.mark.parametrize("policy_mode", ("product", "validation"))
def test_connection_diagnostics_do_not_grant_product_access(selector, command, policy_mode):
    ensure_backend_live_support(
        visa_library=selector,
        resource="USB0::FAKE::INSTR",
        command=command,
        policy_mode=policy_mode,
    )


def test_policy_mode_is_not_a_general_force_escape():
    with pytest.raises(OscilloscopeError, match="unsupported backend support policy mode"):
        ensure_backend_live_support(
            visa_library=None,
            resource="USB0::FAKE::INSTR",
            policy_mode="force",
        )
