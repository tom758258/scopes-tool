"""WebUI workflow execution and model-derived parameter subsets."""

import pytest

from scopes_tool_core.capabilities import capabilities_for_model_id
from scopes_tool_webui.command_catalog import command_catalog
from scopes_tool_webui.command_execution import execute_command
from scopes_tool_webui.command_validation import _validate_parameters

MODELS = ("tektronix-tbs2074b", "tektronix-tds2024b", "tektronix-tbs1052b")


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("command,parameters", [
    ("doctor", {}),
    ("capture-batch", {"channels": [1], "count": 1}),
    ("capture-until", {"channels": [1], "condition_channel": 1, "metric": "max", "operator": "gt", "threshold": 0, "timeout_seconds": 1}),
    ("capture-monitor", {"channels": [1], "count": 1}),
    ("measure-sweep", {"channels": [1], "items": ["vpp", "frequency"]}),
    ("measure-log", {"channels": [1], "count": 1, "interval_seconds": 0}),
    ("measure-until", {"channel": 1, "item": "vpp", "operator": "gt", "threshold": 0, "timeout_seconds": 1}),
    ("triggered-capture-series", {"channels": [1], "count": 1, "trigger_timeout_seconds": 1}),
    ("triggered-measure-loop", {"channels": [1], "count": 1, "trigger_timeout_seconds": 1}),
    ("sequence", {"document": {"version": 1, "steps": [
        {"action": "single", "parameters": {}},
        {"action": "wait-trigger", "parameters": {"timeout_seconds": 1}},
        {"action": "measure", "parameters": {"item": "vpp", "channel": 1}},
    ]}}),
])
def test_model_workflow_end_to_end(model, command, parameters, tmp_path):
    definition = next(c for c in command_catalog(include_hidden=True) if c["id"] == command)
    for mode in (m for m in definition["modes"] if m != "live"):
        normalized = dict(parameters)
        _validate_parameters(command, normalized, mode, model)
        result = execute_command(command, mode=mode, resource=None, model_id=model,
                                 parameters=normalized, artifact_dir=tmp_path / mode)
        assert result["exit_code"] == 0, result
        if mode == "simulate":
            assert result.get("system_error") is None
            assert result["result"]["post_command_status"]["complete"] is True


@pytest.mark.parametrize("model", MODELS)
def test_catalog_projects_core_subsets(model):
    catalog = {c["id"]: c for c in command_catalog(include_hidden=True)}
    caps = capabilities_for_model_id(model)
    for command in ("measure", "measure-sweep", "measure-log", "measure-until", "triggered-measure-loop"):
        fields = catalog[command]["presentation"]["models"][model]["fields"]
        field = "item" if command in {"measure", "measure-until"} else "items"
        assert set(fields[field]["options"]) == set(caps.measurement_items)
    metadata = catalog["sequence"]["presentation"]["models"][model]["sequence"]
    assert tuple(metadata["actions"]) == caps.supported_sequence_actions
    capture = {f["name"]: f for f in metadata["parameters"]["capture"]}
    assert capture["channels"]["options"] == list(range(1, caps.analog_channels + 1))
    assert capture["waveform_format"]["options"] == ["byte"]
    assert catalog["smoke"]["presentation"]["models"][model]["supported"] is (model == MODELS[0])


def test_tbs2074b_smoke_keeps_png(tmp_path):
    result = execute_command("smoke", mode="simulate", resource=None, model_id=MODELS[0],
                             parameters={"save_artifacts": True}, artifact_dir=tmp_path)
    assert result["exit_code"] == 0, result
    assert result["result"]["post_command_status"]["complete"] is True
    assert any(a["path"].endswith(".png") for a in result["artifacts"])
