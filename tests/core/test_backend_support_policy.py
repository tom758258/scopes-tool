"""No-hardware acceptance tests for the backend-only support policy."""

from __future__ import annotations

import pytest

from scopes_tool_core.errors import OscilloscopeError
from scopes_tool_core.support_policy import (
    PYVISA_PY_PENDING_SCOPES,
    SUPPORT_POLICY_MODE_VALIDATION,
    ensure_backend_live_support,
    infer_transport_scope,
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


def test_pending_scope_inventory_has_eight_explicit_pairs():
    assert PYVISA_PY_PENDING_SCOPES == {
        ("keysight-dsox2004a", "usb"),
        ("keysight-dsox3024a", "usb"),
        ("keysight-dsox4024a", "usb"),
        ("keysight-dsox4034a", "usb"),
        ("tektronix-tbs1052b", "usb"),
        ("keysight-dsox4024a", "tcpip"),
        ("keysight-dsox4034a", "tcpip"),
        ("tektronix-tbs2074", "tcpip"),
    }


@pytest.mark.parametrize(("model_id", "transport"), sorted(PYVISA_PY_PENDING_SCOPES))
@pytest.mark.parametrize("interface_number", ("", "0"))
def test_registered_pyvisa_py_pending_scope_allows_validation(
    model_id, transport, interface_number
):
    resource = f"{'USB' if transport == 'usb' else 'TCPIP'}{interface_number}::FAKE::INSTR"
    ensure_backend_live_support(
        visa_library="@py",
        resource=resource,
        policy_mode=SUPPORT_POLICY_MODE_VALIDATION,
    )
    ensure_backend_live_support(
        visa_library="@py",
        resource=resource,
        policy_mode=SUPPORT_POLICY_MODE_VALIDATION,
        detected_model_id=model_id,
    )


@pytest.mark.parametrize("selector", ("@py", "@bt"))
def test_unopened_backend_rejects_product_live(selector):
    with pytest.raises(OscilloscopeError, match="Pending|not open"):
        ensure_backend_live_support(visa_library=selector, resource="USB0::FAKE::INSTR")


@pytest.mark.parametrize("selector", (None, "", "@ivi"))
def test_existing_system_and_custom_visa_unchanged(selector):
    ensure_backend_live_support(
        visa_library=selector,
        resource="GPIB0::FAKE::INSTR",
        detected_model_id="tektronix-tds2024b",
    )


@pytest.mark.parametrize(
    ("model_id", "resource"),
    [
        ("tektronix-tbs2074", "USB0::FAKE::INSTR"),
        ("tektronix-tbs1052b", "TCPIP0::FAKE::INSTR"),
        ("tektronix-tds2024b", "USB0::FAKE::INSTR"),
        ("keysight-dsox2004a", "TCPIP0::FAKE::INSTR"),
        ("keysight-dsox2004a", "TCPIP::FAKE::INSTR"),
    ],
)
def test_unregistered_pyvisa_py_scope_rejects_after_live_idn(model_id, resource):
    with pytest.raises(OscilloscopeError, match="no registered Pending scope"):
        ensure_backend_live_support(
            visa_library="@py",
            resource=resource,
            policy_mode=SUPPORT_POLICY_MODE_VALIDATION,
            detected_model_id=model_id,
        )


def test_pyvisa_py_unknown_transport_rejects_before_open():
    with pytest.raises(OscilloscopeError, match="no registered transport"):
        ensure_backend_live_support(
            visa_library="@py",
            resource="ASRL1::INSTR",
            policy_mode=SUPPORT_POLICY_MODE_VALIDATION,
        )


@pytest.mark.parametrize("selector", (None, "@bt", "@ivi"))
def test_contributor_validation_rejects_other_backends(selector):
    with pytest.raises(OscilloscopeError, match="restricted to @py"):
        ensure_backend_live_support(
            visa_library=selector,
            resource="USB0::FAKE::INSTR",
            policy_mode=SUPPORT_POLICY_MODE_VALIDATION,
        )


@pytest.mark.parametrize("selector", ("@py", "@bt"))
def test_identify_remains_diagnostic_not_product_open(selector):
    ensure_backend_live_support(
        visa_library=selector,
        resource="USB0::FAKE::INSTR",
        command="identify",
    )


def test_policy_mode_is_not_a_general_force_escape():
    with pytest.raises(OscilloscopeError, match="unsupported backend support policy mode"):
        ensure_backend_live_support(
            visa_library=None,
            resource="USB0::FAKE::INSTR",
            policy_mode="force",
        )
