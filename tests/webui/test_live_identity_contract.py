from __future__ import annotations

from pathlib import Path

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.idn import IDN
import scopes_tool_webui.commands as commands
from scopes_tool_webui.commands import WebUIRequestError
from scopes_tool_webui.jobs import Job


class FakeLiveScope:
    def __init__(self, model: str) -> None:
        self.idn = IDN(
            vendor="KEYSIGHT TECHNOLOGIES",
            model=model,
            serial="TEST-SERIAL",
            firmware="1.0",
            raw=f"KEYSIGHT TECHNOLOGIES,{model},TEST-SERIAL,1.0",
        )
        self.capabilities = capabilities_for_model_id(self.idn.model_id)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def live_impedance_request(browser_model: str) -> dict:
    return commands.validate_job_request(
        {
            "command": "channel-impedance",
            "mode": "live",
            "resource": "USB0::TEST::INSTR",
            "model_id": browser_model,
            "parameters": {"action": "set", "channel": 1, "impedance": "fifty"},
        }
    )


def test_live_request_discards_browser_model_and_job_payload_is_nullable(tmp_path: Path) -> None:
    request = live_impedance_request("not-a-registered-model")

    assert request["model_id"] is None
    job = Job(job_id="job", artifact_dir=tmp_path, **request)
    assert job.to_payload()["model_id"] is None


def test_live_capability_validation_uses_detected_model(monkeypatch, tmp_path: Path) -> None:
    scope = FakeLiveScope("DSOX2004A")
    request = live_impedance_request("keysight-dsox4024a")
    monkeypatch.setattr(commands, "open_scope_for_run", lambda config: scope)
    monkeypatch.setattr(
        commands,
        "_execute_scope_command",
        lambda *_args, **_kwargs: {"exit_code": 0, "result": {}, "artifacts": []},
    )

    with pytest.raises(WebUIRequestError, match="50 ohm is not supported"):
        commands.execute_command(
            request["command"],
            mode=request["mode"],
            resource=request["resource"],
            model_id=request["model_id"],
            parameters=request["parameters"],
            artifact_dir=tmp_path,
        )

    assert scope.closed is True


def test_live_detected_model_can_accept_capability_browser_model_lacks(monkeypatch, tmp_path: Path) -> None:
    scope = FakeLiveScope("DSOX4024A")
    request = live_impedance_request("keysight-dsox2004a")
    configs = []
    monkeypatch.setattr(commands, "open_scope_for_run", lambda config: configs.append(config) or scope)
    monkeypatch.setattr(
        commands,
        "_execute_scope_command",
        lambda *_args, **_kwargs: {"exit_code": 0, "result": {"ok": True}, "artifacts": []},
    )

    result = commands.execute_command(
        request["command"],
        mode=request["mode"],
        resource=request["resource"],
        model_id=request["model_id"],
        parameters=request["parameters"],
        artifact_dir=tmp_path,
    )

    assert result["exit_code"] == 0
    assert configs[0].planning_physical_model_id is None
    assert configs[0].capabilities is None
    assert scope.closed is True


def test_live_admission_keeps_model_independent_validation() -> None:
    with pytest.raises(WebUIRequestError, match="action must be one of"):
        commands.validate_job_request(
            {
                "command": "channel-impedance",
                "mode": "live",
                "resource": "USB0::TEST::INSTR",
                "parameters": {"action": "invalid", "channel": 1, "impedance": "fifty"},
            }
        )

    with pytest.raises(WebUIRequestError, match="channel must be an integer"):
        commands.validate_job_request(
            {
                "command": "channel-impedance",
                "mode": "live",
                "resource": "USB0::TEST::INSTR",
                "parameters": {"action": "set", "channel": 1.9, "impedance": "fifty"},
            }
        )


def test_planning_modes_keep_registered_model_selection() -> None:
    for mode, command in (("simulate", "identify"), ("dry-run", "measure")):
        parameters = {} if command == "identify" else {"item": "vpp", "channel": 1}
        request = commands.validate_job_request(
            {
                "command": command,
                "mode": mode,
                "model_id": "keysight-dsox2004a",
                "parameters": parameters,
            }
        )
        assert request["model_id"] == "keysight-dsox2004a"


def test_list_resources_is_hidden_but_identify_remains_user_facing() -> None:
    catalog = {entry["id"]: entry for entry in commands.command_catalog()}

    assert "list-resources" not in catalog
    assert catalog["identify"]["label"] == "Read device information"
    assert catalog["identify"]["description"] == "Read instrument identification information"
    request = commands.validate_job_request(
        {"command": "list-resources", "mode": "live", "parameters": {"live_only": True}}
    )
    assert request["command"] == "list-resources"
    assert request["model_id"] is None


def test_identify_result_projects_detected_physical_model_id(tmp_path: Path) -> None:
    scope = FakeLiveScope("DSOX4024A")

    result = commands._execute_scope_command(
        scope,
        "identify",
        "USB0::TEST::INSTR",
        {},
        tmp_path,
    )

    assert result["result"]["idn"]["model_id"] == "keysight-dsox4024a"
