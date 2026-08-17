from __future__ import annotations

from scopes_tool_core import discovery
from scopes_tool_core.visa_backend import VisaLiveVerification, VisaResourceListing


def test_raw_discovery_preserves_resources_and_backend(monkeypatch) -> None:
    listing = VisaResourceListing(
        resources=("USB0::A::INSTR", "TCPIP0::192.0.2.1::INSTR"),
        backend="fake backend",
    )
    monkeypatch.setattr(discovery, "list_visa_resources", lambda **_: listing)

    result = discovery.discover_visa_resources()

    assert result is listing
    assert result.resources == ("USB0::A::INSTR", "TCPIP0::192.0.2.1::INSTR")
    assert result.backend == "fake backend"


def test_live_discovery_keeps_responders_and_skips_failed_candidates(monkeypatch) -> None:
    listing = VisaResourceListing(
        resources=(
            "USB0::A::INSTR",
            "TCPIP0::192.0.2.1::INSTR",
            "ASRL1::INSTR",
        ),
        backend="fake backend",
    )
    verifications = {
        "USB0::A::INSTR": VisaLiveVerification(
            "USB0::A::INSTR",
            True,
            "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY123,01.00",
            None,
        ),
        "TCPIP0::192.0.2.1::INSTR": VisaLiveVerification(
            "TCPIP0::192.0.2.1::INSTR", False, None, "timeout"
        ),
        "ASRL1::INSTR": VisaLiveVerification(
            "ASRL1::INSTR",
            True,
            "ACME,MODEL-UNKNOWN,SERIAL,1.0",
            None,
        ),
    }
    calls = []

    def verify(resource, **kwargs):
        calls.append(("generic", resource, kwargs))
        return verifications[resource]

    def verify_asrl(resource, **kwargs):
        calls.append(("asrl", resource, kwargs))
        return verifications[resource]

    monkeypatch.setattr(discovery, "list_visa_resources", lambda **_: listing)
    monkeypatch.setattr(discovery, "verify_visa_resource_live", verify)
    monkeypatch.setattr(discovery, "verify_asrl_resource_live", verify_asrl)

    result = discovery.discover_visa_resources(
        live_only=True,
        serial_read_termination="CRLF",
        serial_write_termination="LF",
    )

    assert result.backend == "fake backend"
    assert [resource.name for resource in result.resources] == [
        "USB0::A::INSTR",
        "ASRL1::INSTR",
    ]
    assert result.resources[0].interface == "USB"
    assert result.resources[0].model_id == "keysight-dsox4024a"
    assert result.resources[1].interface == "ASRL"
    assert result.resources[1].model_id is None
    assert calls == [
        (
            "generic",
            "USB0::A::INSTR",
            {"visa_library": None, "serial_read_termination": "CRLF", "serial_write_termination": "LF"},
        ),
        (
            "generic",
            "TCPIP0::192.0.2.1::INSTR",
            {"visa_library": None, "serial_read_termination": "CRLF", "serial_write_termination": "LF"},
        ),
        (
            "asrl",
            "ASRL1::INSTR",
            {"visa_library": None, "serial_read_termination": "CRLF", "serial_write_termination": "LF"},
        ),
    ]


def test_live_discovery_zero_responders_is_successful_empty_result(monkeypatch) -> None:
    listing = VisaResourceListing(resources=("USB0::A::INSTR",), backend="fake backend")
    monkeypatch.setattr(discovery, "list_visa_resources", lambda **_: listing)
    monkeypatch.setattr(
        discovery,
        "verify_visa_resource_live",
        lambda resource, **_: VisaLiveVerification(resource, False, None, "not reachable"),
    )

    result = discovery.discover_visa_resources(live_only=True)

    assert result.resources == ()
    assert result.backend == "fake backend"


def test_resource_interface_classification_is_core_owned() -> None:
    assert discovery.resource_interface("USB0::INSTR") == "USB"
    assert discovery.resource_interface("TCPIP0::192.0.2.1::INSTR") == "TCPIP"
    assert discovery.resource_interface("ASRL1::INSTR") == "ASRL"
    assert discovery.resource_interface("GPIB0::1::INSTR") == "GPIB"
    assert discovery.resource_interface("INSTR0") == "UNKNOWN"
