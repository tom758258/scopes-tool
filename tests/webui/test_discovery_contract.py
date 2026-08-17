from __future__ import annotations

from scopes_tool_core.discovery import VisaLiveResource, VisaLiveResourceListing
from scopes_tool_core.idn import IDN
import scopes_tool_webui.commands as commands


def test_webui_live_resource_result_keeps_backend_and_structured_identity(monkeypatch, tmp_path) -> None:
    resource = VisaLiveResource(
        name="USB0::A::INSTR",
        interface="USB",
        reachable=True,
        idn=IDN(
            vendor="KEYSIGHT TECHNOLOGIES",
            model="DSOX4024A",
            serial="MY123",
            firmware="01.00",
            raw="KEYSIGHT TECHNOLOGIES,DSOX4024A,MY123,01.00",
        ),
        model_id="keysight-dsox4024a",
    )
    monkeypatch.setattr(
        commands,
        "discover_visa_resources",
        lambda *, live_only: VisaLiveResourceListing(
            resources=(resource,) if live_only else (),
            backend="fake backend",
        ),
    )

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
            "name": "USB0::A::INSTR",
            "interface": "USB",
            "reachable": True,
            "idn": {
                "raw": "KEYSIGHT TECHNOLOGIES,DSOX4024A,MY123,01.00",
                "manufacturer": "KEYSIGHT TECHNOLOGIES",
                "model": "DSOX4024A",
                "serial": "MY123",
                "firmware": "01.00",
            },
            "model_id": "keysight-dsox4024a",
        }
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
