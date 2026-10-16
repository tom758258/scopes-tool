from __future__ import annotations

import pytest

from scopes_tool_core import discovery
from scopes_tool_core.visa_backend import VisaLiveVerification, VisaResourceListing
import scopes_tool_webui.command_validation as command_validation_module
import scopes_tool_webui.command_execution as command_execution_module


@pytest.mark.parametrize("selector", [None, "@py"])
def test_webui_live_resource_result_preserves_asrl_and_usb_discovery(monkeypatch, tmp_path, selector) -> None:
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

    selectors = []
    monkeypatch.setattr(
        discovery, "list_visa_resources",
        lambda **kwargs: selectors.append(kwargs["visa_library"]) or listing,
    )
    monkeypatch.setattr(discovery, "verify_visa_resource_live", verify)
    monkeypatch.setattr(discovery, "verify_asrl_resource_live", verify_asrl)

    request = command_validation_module.validate_job_request(
        {
            "command": "list-resources",
            "mode": "live",
            "model_id": "keysight-dsox4024a",
            "parameters": {"live_only": True},
            "visa_library": selector,
        }
    )
    result = command_execution_module.execute_command(
        request["command"],
        mode=request["mode"],
        resource=request["resource"],
        visa_library=request["visa_library"],
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
    assert selectors == [selector]
    assert calls == [
        (
            "asrl",
            "ASRL7::INSTR",
            {
                "visa_library": selector,
                "serial_read_termination": None,
                "serial_write_termination": None,
            },
        ),
        (
            "generic",
            "USB0::A::INSTR",
            {
                "visa_library": selector,
                "serial_read_termination": None,
                "serial_write_termination": None,
            },
        ),
        (
            "generic",
            "USB0::B::INSTR",
            {
                "visa_library": selector,
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

    import scopes_tool_webui.command_execution as command_execution

    monkeypatch.setattr(
        command_execution,
        "discover_visa_resources",
        lambda *, live_only, visa_library: calls.append((live_only, visa_library)) or RawListing(),
    )

    request = command_validation_module.validate_job_request(
        {
            "command": "list-resources",
            "mode": "live",
            "model_id": "keysight-dsox4024a",
            "parameters": {},
        }
    )
    result = command_execution_module.execute_command(
        request["command"],
        mode=request["mode"],
        resource=request["resource"],
        visa_library=request["visa_library"],
        model_id=request["model_id"],
        parameters=request["parameters"],
        artifact_dir=tmp_path,
    )

    assert calls == [(False, None)]
    assert result["result"] == {
        "resources": ["USB0::A::INSTR"],
        "backend": "fake backend",
    }


@pytest.mark.parametrize("model_id", ["keysight-dsox4024a", "tektronix-tbs2074"])
@pytest.mark.parametrize("live_only", [False, True])
def test_simulate_resource_listing_never_touches_visa(monkeypatch, tmp_path, model_id, live_only) -> None:
    def unexpected_discovery(**_kwargs):
        pytest.fail("Simulate list-resources must not use real VISA discovery")

    monkeypatch.setattr(command_execution_module, "discover_visa_resources", unexpected_discovery)
    request = command_validation_module.validate_job_request({
        "command": "list-resources",
        "mode": "simulate",
        "model_id": model_id,
        "parameters": {"live_only": live_only},
    })
    result = command_execution_module.execute_command(
        request["command"],
        mode=request["mode"],
        resource=request["resource"],
        visa_library=request["visa_library"],
        model_id=request["model_id"],
        parameters=request["parameters"],
        artifact_dir=tmp_path,
    )

    assert result["exit_code"] == 0
    assert result["artifacts"] == []
    assert result["result"]["backend"] == "simulator"
    expected_resource = f"SIM::{model_id}::INSTR"
    if live_only:
        resources = result["result"]["resources"]
        assert len(resources) == 1
        resource = resources[0]
        assert resource["name"] == expected_resource
        assert resource["interface"] == "SIM"
        assert resource["reachable"] is True
        assert resource["model_id"] == model_id
        assert resource["idn"]["raw"]
        assert resource["idn"]["manufacturer"]
        assert resource["idn"]["model"]
    else:
        assert result["result"]["resources"] == [expected_resource]


@pytest.mark.parametrize("live_only", [False, True])
def test_dry_run_resource_listing_rejected_before_job(monkeypatch, live_only) -> None:
    from fastapi.testclient import TestClient
    from scopes_tool_webui.app import app, job_manager

    def unexpected_submit(_request):
        pytest.fail("Dry-run list-resources must be rejected before job admission")

    monkeypatch.setattr(job_manager, "submit", unexpected_submit)
    response = TestClient(app).post("/api/jobs", json={
        "command": "list-resources",
        "mode": "dry-run",
        "model_id": "keysight-dsox4024a",
        "parameters": {"live_only": live_only},
    })

    assert response.status_code == 400
    assert "not available in dry-run mode" in response.json()["detail"]


def test_webui_list_resources_modes_include_simulation_not_dry_run() -> None:
    from scopes_tool_webui.command_catalog import command_catalog

    entry = next(
        item for item in command_catalog(include_hidden=True)
        if item["id"] == "list-resources"
    )
    assert entry["modes"] == ["live", "simulate"]


def test_dry_run_resource_listing_direct_execution_does_not_touch_visa(monkeypatch, tmp_path) -> None:
    def unexpected_discovery(**_kwargs):
        pytest.fail("Dry-run must not touch VISA resources")

    monkeypatch.setattr(command_execution_module, "discover_visa_resources", unexpected_discovery)
    with pytest.raises(command_validation_module.WebUIRequestError):
        command_execution_module.execute_command(
            "list-resources",
            mode="dry-run",
            resource=None,
            model_id="keysight-dsox4024a",
            parameters={"live_only": True},
            artifact_dir=tmp_path,
        )
