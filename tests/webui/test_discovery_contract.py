from __future__ import annotations

from scopes_tool_core import discovery
from scopes_tool_core.visa_backend import VisaLiveVerification, VisaResourceListing
import scopes_tool_webui.commands as commands


def test_webui_live_resource_result_preserves_asrl_and_usb_discovery(monkeypatch, tmp_path) -> None:
    listing = VisaResourceListing(
        resources=("ASRL7::INSTR", "USB0::A::INSTR", "USB0::B::INSTR"),
        backend="fake backend",
    )
    verifications = {
        "ASRL7::INSTR": VisaLiveVerification(
            "ASRL7::INSTR",
            True,
            "Agilent Technologies,E3646A,MY123,1.0",
            None,
        ),
        "USB0::A::INSTR": VisaLiveVerification(
            "USB0::A::INSTR",
            True,
            "AGILENT TECHNOLOGIES,DSO-X 4034A,MY456,2.0",
            None,
        ),
        "USB0::B::INSTR": VisaLiveVerification(
            "USB0::B::INSTR",
            True,
            "Agilent Technologies,33512B,MY789,3.0",
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

    request = commands.validate_job_request(
        {
            "command": "list-resources",
            "mode": "live",
            "model_id": "keysight-dsox4024a",
            "parameters": {"live_only": True},
        }
    )
    result = commands.execute_command(
        request["command"],
        mode=request["mode"],
        resource=request["resource"],
        model_id=request["model_id"],
        parameters=request["parameters"],
        artifact_dir=tmp_path,
    )

    assert result["result"]["backend"] == "fake backend"
    assert result["result"]["resources"] == [
        {
            "name": "ASRL7::INSTR",
            "interface": "ASRL",
            "reachable": True,
            "idn": {
                "raw": "Agilent Technologies,E3646A,MY123,1.0",
                "manufacturer": "Agilent Technologies",
                "model": "E3646A",
                "serial": "MY123",
                "firmware": "1.0",
            },
            "model_id": None,
        },
        {
            "name": "USB0::A::INSTR",
            "interface": "USB",
            "reachable": True,
            "idn": {
                "raw": "AGILENT TECHNOLOGIES,DSO-X 4034A,MY456,2.0",
                "manufacturer": "AGILENT TECHNOLOGIES",
                "model": "DSO-X 4034A",
                "serial": "MY456",
                "firmware": "2.0",
            },
            "model_id": "keysight-dsox4034a",
        },
        {
            "name": "USB0::B::INSTR",
            "interface": "USB",
            "reachable": True,
            "idn": {
                "raw": "Agilent Technologies,33512B,MY789,3.0",
                "manufacturer": "Agilent Technologies",
                "model": "33512B",
                "serial": "MY789",
                "firmware": "3.0",
            },
            "model_id": None,
        },
    ]
    assert calls == [
        (
            "asrl",
            "ASRL7::INSTR",
            {
                "visa_library": None,
                "serial_read_termination": None,
                "serial_write_termination": None,
            },
        ),
        (
            "generic",
            "USB0::A::INSTR",
            {
                "visa_library": None,
                "serial_read_termination": None,
                "serial_write_termination": None,
            },
        ),
        (
            "generic",
            "USB0::B::INSTR",
            {
                "visa_library": None,
                "serial_read_termination": None,
                "serial_write_termination": None,
            },
        ),
    ]


def test_webui_list_resources_defaults_to_raw_mode(monkeypatch, tmp_path) -> None:
    calls = []

    class RawListing:
        resources = ("USB0::A::INSTR",)
        backend = "fake backend"

    monkeypatch.setattr(
        commands,
        "discover_visa_resources",
        lambda *, live_only: calls.append(live_only) or RawListing(),
    )

    request = commands.validate_job_request(
        {
            "command": "list-resources",
            "mode": "live",
            "model_id": "keysight-dsox4024a",
            "parameters": {},
        }
    )
    result = commands.execute_command(
        request["command"],
        mode=request["mode"],
        resource=request["resource"],
        model_id=request["model_id"],
        parameters=request["parameters"],
        artifact_dir=tmp_path,
    )

    assert calls == [False]
    assert result["result"] == {
        "resources": ["USB0::A::INSTR"],
        "backend": "fake backend",
    }
