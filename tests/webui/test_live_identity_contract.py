from __future__ import annotations

from pathlib import Path

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_core.idn import IDN
import scopes_tool_webui.command_execution as command_execution
import scopes_tool_webui.command_validation as command_validation_module
import scopes_tool_webui.command_catalog as command_catalog_module
from scopes_tool_webui.command_validation import WebUIRequestError
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

    def post_webui_operation_status(self, operation: str) -> None:
        pass


def live_impedance_request(browser_model: str) -> dict:
    return command_validation_module.validate_job_request(
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
    job = Job(job_id="job", pc_output_root=tmp_path, **request)
    assert job.to_payload()["model_id"] is None


def test_live_capability_validation_uses_detected_model(monkeypatch, tmp_path: Path) -> None:
    scope = FakeLiveScope("DSOX2004A")
    request = live_impedance_request("keysight-dsox4024a")
    monkeypatch.setattr(command_execution, "open_scope_for_run", lambda config: scope)
    monkeypatch.setattr(
        command_execution,
        "_execute_scope_command",
        lambda *_args, **_kwargs: {"exit_code": 0, "result": {}, "artifacts": []},
    )

    with pytest.raises(WebUIRequestError, match="50 ohm is not supported"):
        command_execution.execute_command(
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
    monkeypatch.setattr(command_execution, "open_scope_for_run", lambda config: configs.append(config) or scope)
    monkeypatch.setattr(
        command_execution,
        "_execute_scope_command",
        lambda *_args, **_kwargs: {"exit_code": 0, "result": {"ok": True}, "artifacts": []},
    )

    result = command_execution.execute_command(
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
        command_validation_module.validate_job_request(
            {
                "command": "channel-impedance",
                "mode": "live",
                "resource": "USB0::TEST::INSTR",
                "parameters": {"action": "invalid", "channel": 1, "impedance": "fifty"},
            }
        )

    with pytest.raises(WebUIRequestError, match="channel must be an integer"):
        command_validation_module.validate_job_request(
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
        request = command_validation_module.validate_job_request(
            {
                "command": command,
                "mode": mode,
                "model_id": "keysight-dsox2004a",
                "parameters": parameters,
            }
        )
        assert request["model_id"] == "keysight-dsox2004a"


def test_list_resources_is_hidden_and_identify_hidden_from_catalog() -> None:
    catalog = {entry["id"]: entry for entry in command_catalog_module.command_catalog()}

    assert "list-resources" not in catalog
    assert "identify" not in catalog
    # System snapshot is also hidden from presentation (internal command only).
    assert "system-information-snapshot" not in catalog
    request = command_validation_module.validate_job_request(
        {"command": "list-resources", "mode": "live", "parameters": {"live_only": True}}
    )
    assert request["command"] == "list-resources"
    assert request["model_id"] is None


def test_identify_result_projects_detected_physical_model_id(tmp_path: Path) -> None:
    scope = FakeLiveScope("DSOX4024A")

    result = command_execution._execute_scope_command(
        scope,
        "identify",
        "USB0::TEST::INSTR",
        {},
        tmp_path,
    )

    assert result["result"]["idn"]["model_id"] == "keysight-dsox4024a"


@pytest.mark.parametrize("selector", [None, "@py"])
@pytest.mark.parametrize("idn, model_id", [
    ("KEYSIGHT TECHNOLOGIES,DSOX4024A,TEST,1.0", "keysight-dsox4024a"),
    ("TEKTRONIX,TBS2074,TEST,1.0", "tektronix-tbs2074"),
])
def test_identify_job_keeps_backend_and_only_queries_idn(monkeypatch, tmp_path, selector, idn, model_id):
    import asyncio
    import threading

    from scopes_tool_core.fake_backend import FakeBackend
    from scopes_tool_core.scope import Oscilloscope
    from scopes_tool_webui.jobs import JobManager

    backend = FakeBackend(responses={"*IDN?": idn})
    opened = []

    gate = threading.Event()
    started = threading.Event()

    def open_fake(resource, visa_library=None):
        if resource == "USB0::BLOCKER::INSTR":
            started.set()
            assert gate.wait(5)
            return Oscilloscope(FakeBackend(responses={"*IDN?": idn}))
        opened.append((resource, visa_library))
        return Oscilloscope(backend)

    monkeypatch.setattr(Oscilloscope, "open", staticmethod(open_fake))
    manager = JobManager()
    blocker = manager.submit(command_validation_module.validate_job_request({
        "command": "identify", "mode": "live", "resource": "USB0::BLOCKER::INSTR",
        "pc_output_dir": str(tmp_path),
    }))
    assert started.wait(5)
    request = command_validation_module.validate_job_request({
        "command": "identify", "mode": "live", "resource": "USB0::FAKE::INSTR",
        "visa_library": selector, "pc_output_dir": str(tmp_path),
    })
    try:
        job = manager.submit(request)
        request["visa_library"] = "@py" if selector is None else None
        gate.set()
        job.future.result(timeout=5)
        assert job.status == "completed", job.error
        assert job.visa_library == selector
        assert opened == [("USB0::FAKE::INSTR", selector)]
        assert job.result["result"]["idn"]["model_id"] == model_id
        assert "visa_library" not in job.to_payload()
        assert backend.history == ["*IDN?"]
        assert backend.closed is True
    finally:
        gate.set()
        blocker.future.result(timeout=5)
        asyncio.run(manager.shutdown())


@pytest.mark.parametrize("command, parameters", [
    ("run", {}), ("single", {}), ("capture", {"channels": [1]}),
    ("measure", {"item": "vpp", "channel": 1}), ("screenshot", {}),
    ("channel-scale", {"action": "set", "channel": 1, "volts_per_division": 1}),
    ("live-data-snapshot", {}), ("system-information-snapshot", {}),
])
def test_direct_job_api_cannot_open_unreleased_py_usb_operations(monkeypatch, tmp_path, command, parameters):
    import asyncio
    import importlib

    from fastapi.testclient import TestClient
    from scopes_tool_core.scope import Oscilloscope
    from scopes_tool_webui.jobs import JobManager

    app_module = importlib.import_module("scopes_tool_webui.app")
    manager = JobManager()
    monkeypatch.setattr(app_module, "job_manager", manager)

    def unexpected_open(*args, **kwargs):
        pytest.fail("Product Live must fail before VISA open")

    monkeypatch.setattr(Oscilloscope, "open", staticmethod(unexpected_open))
    try:
        client = TestClient(app_module.app)
        response = client.post("/api/jobs", json={
            "command": command, "parameters": parameters, "mode": "live",
            "resource": "USB0::FAKE::INSTR", "visa_library": "@py",
            "pc_output_dir": str(tmp_path),
        })
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        manager.get(job_id).future.result(timeout=5)
        result = client.get(f"/api/jobs/{job_id}").json()
        assert result["status"] == "failed"
        assert "no Product Live support" in result["error"]
    finally:
        asyncio.run(manager.shutdown())


@pytest.mark.parametrize("selector", ["@bt", "@ivi", "custom", 1, [], {}])
def test_webui_backend_request_limits_selector_choices(selector):
    with pytest.raises(WebUIRequestError, match="visa_library"):
        command_validation_module.validate_job_request({
            "command": "identify", "mode": "live", "resource": "USB0::FAKE::INSTR",
            "visa_library": selector,
        })


def test_old_requests_and_planning_modes_do_not_select_py_backend():
    for mode, command, parameters in [
        ("live", "identify", {}), ("simulate", "identify", {}),
        ("dry-run", "measure", {"item": "vpp", "channel": 1}),
    ]:
        payload = {"mode": mode, "command": command, "parameters": parameters,
                   "resource": "USB0::FAKE::INSTR"}
        if mode != "live":
            payload["visa_library"] = "@py"
        request = command_validation_module.validate_job_request(payload)
        assert request["visa_library"] is None


def test_direct_job_api_opens_approved_py_tcpip_product_command(monkeypatch, tmp_path):
    import asyncio
    import importlib

    from fastapi.testclient import TestClient
    from scopes_tool_core.fake_backend import FakeBackend
    from scopes_tool_core.scope import Oscilloscope
    from scopes_tool_webui.jobs import JobManager

    app_module = importlib.import_module("scopes_tool_webui.app")
    manager = JobManager()
    monkeypatch.setattr(app_module, "job_manager", manager)
    backend = FakeBackend(responses={
        "*IDN?": "KEYSIGHT TECHNOLOGIES,DSOX4024A,TEST,1.0",
        ":SYSTem:ERRor?": '+0,"No error"',
    })
    monkeypatch.setattr(
        Oscilloscope, "open",
        staticmethod(lambda resource, visa_library=None: Oscilloscope(backend)),
    )
    try:
        client = TestClient(app_module.app)
        response = client.post("/api/jobs", json={
            "command": "run", "parameters": {}, "mode": "live",
            "resource": "TCPIP0::FAKE::INSTR", "visa_library": "@py",
            "pc_output_dir": str(tmp_path),
        })
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        manager.get(job_id).future.result(timeout=5)
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"
        assert backend.history == ["*IDN?", ":RUN", ":SYSTem:ERRor?"]
        assert backend.closed is True
    finally:
        asyncio.run(manager.shutdown())
