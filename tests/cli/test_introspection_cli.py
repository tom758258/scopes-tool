"""Focused tests for offline tool introspection: manifest and capabilities."""

import json
from importlib import metadata
from pathlib import Path

import pytest

from scopes_tool_cli import cli, runtime
from scopes_tool_cli.worker_commands import WORKER_SCHEMA_VERSION
from scopes_tool_core.capabilities import capabilities_for_model_id


def _expected_package_version() -> str:
    try:
        return metadata.version("scopes-tool")
    except metadata.PackageNotFoundError:
        return "0+unknown"


def _json_stdout(capsys):
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert isinstance(payload, dict)
    return payload


def _forbid_visa(monkeypatch):
    import pyvisa

    def fail_resource_manager(*args, **kwargs):
        del args, kwargs
        raise AssertionError(
            "introspection must not create a VISA ResourceManager"
        )

    monkeypatch.setattr(pyvisa, "ResourceManager", fail_resource_manager)


def _snapshot_files(root: Path) -> set[str]:
    return {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if ".git" not in path.parts
    }


def _assert_no_files_created(tmp_path: Path, before: set[str]) -> None:
    assert _snapshot_files(tmp_path) == before


def test_manifest_json_reports_static_tool_identity(capsys):
    assert cli.main(["manifest", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["event"] == "tool_manifest"
    assert payload["schema_version"] == 2
    assert type(payload["schema_version"]) is int
    assert payload["tool_id"] == "scopes"
    assert payload["tool_version"] == _expected_package_version()
    assert payload["worker_protocol"]["schema_versions"] == [
        WORKER_SCHEMA_VERSION
    ]
    assert payload["worker_protocol"]["compatibility_policy"] == "v2-only"


def test_manifest_json_does_not_touch_visa_or_filesystem(
    monkeypatch, capsys, tmp_path
):
    _forbid_visa(monkeypatch)
    monkeypatch.chdir(tmp_path)
    before = _snapshot_files(tmp_path)

    assert cli.main(["manifest", "--json"]) == 0

    _json_stdout(capsys)
    _assert_no_files_created(tmp_path, before)


def test_manifest_text_mode_smoke(capsys):
    assert cli.main(["manifest"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "scopes" in captured.out
    assert "v2-only" in captured.out


def test_capabilities_json_default_model_uses_core_registry(
    monkeypatch, capsys, tmp_path
):
    _forbid_visa(monkeypatch)
    monkeypatch.chdir(tmp_path)
    before = _snapshot_files(tmp_path)

    assert cli.main(["capabilities", "--json"]) == 0

    payload = _json_stdout(capsys)
    assert payload["event"] == "capabilities"
    assert payload["schema_version"] == 2
    assert type(payload["schema_version"]) is int
    assert payload["runtime_identity"] == {"detection_performed": False}
    assert payload["selection"] == {
        "requested_model": None,
        "source": "default_policy",
    }
    assert payload["model"]["model_id"] == "keysight-dsox4024a"
    assert payload["model"]["canonical_model"] == "DSOX4024A"
    assert payload["capabilities"] == runtime._capabilities_json(
        capabilities_for_model_id("keysight-dsox4024a")
    )
    core_profile = capabilities_for_model_id("keysight-dsox4024a")
    for field in (
        "supports_wgen",
        "wgen_scpi_root",
        "supports_math_cascade",
        "supports_segmented_waveform_all",
    ):
        assert payload["capabilities"][field] == getattr(core_profile, field)
    _assert_no_files_created(tmp_path, before)


def test_capabilities_json_explicit_model_reports_requested_selection(capsys):
    assert cli.main(
        ["capabilities", "--model", "keysight-dsox2004a", "--json"]
    ) == 0

    payload = _json_stdout(capsys)
    assert payload["event"] == "capabilities"
    assert payload["selection"] == {
        "requested_model": "keysight-dsox2004a",
        "source": "requested_model",
    }
    assert payload["model"]["model_id"] == "keysight-dsox2004a"
    assert payload["model"]["series"] == "2000X"
    assert payload["capabilities"] == runtime._capabilities_json(
        capabilities_for_model_id("keysight-dsox2004a")
    )
    assert payload["capabilities"]["supports_area_measurement"] is False
    assert payload["capabilities"]["supports_measure_statistics"] is False


def test_capabilities_json_unknown_model_fails_closed(capsys):
    assert (
        cli.main(["capabilities", "--model", "keysight-dsox9999a", "--json"])
        == 2
    )

    payload = _json_stdout(capsys)
    assert payload["event"] == "error"
    assert payload["schema_version"] == 2
    assert payload["ok"] is False
    assert payload["command"] == "capabilities"
    assert payload["exit_code"] == 2
    assert payload["error"]["type"] == "UnsupportedModelError"


def test_capabilities_text_mode_unknown_model_fails_closed_to_stderr(capsys):
    assert cli.main(["capabilities", "--model", "bogus-model"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error:" in captured.err


@pytest.mark.parametrize("command", [["manifest"], ["capabilities"]])
def test_introspection_commands_do_not_open_scopes(monkeypatch, command):
    def fail_open(resource, visa_library=None):
        del resource, visa_library
        raise AssertionError("introspection must not open a scope")

    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_open))

    assert cli.main(command + ["--json"]) == 0


@pytest.mark.parametrize("model", [
    "keysight-dsox2004a", "keysight-dsox3024a", "keysight-dsox4024a",
    "keysight-dsox4034a", "tektronix-tbs2074", "tektronix-tds2024b",
    "tektronix-tbs1052b",
])
def test_capabilities_json_exposes_core_acquisition_values(model, monkeypatch, capsys, tmp_path):
    _forbid_visa(monkeypatch)
    monkeypatch.chdir(tmp_path)
    before = _snapshot_files(tmp_path)
    assert cli.main(["capabilities", "--model", model, "--json"]) == 0
    payload = _json_stdout(capsys)
    profile = capabilities_for_model_id(model)
    assert payload["schema_version"] == 2
    assert payload["capabilities"]["acquisition_modes"] == list(profile.acquisition_modes)
    assert payload["capabilities"]["average_counts"] == list(profile.average_counts)
    _assert_no_files_created(tmp_path, before)


def test_capabilities_json_unknown_acquisition_information_is_null():
    from dataclasses import replace
    profile = replace(capabilities_for_model_id("keysight-dsox4024a"),
                      acquisition_modes=None, average_counts=None)
    payload = runtime._capabilities_json(profile)
    assert payload["acquisition_modes"] is None
    assert payload["average_counts"] is None


@pytest.mark.parametrize("model", [
    "keysight-dsox2004a", "keysight-dsox3024a", "keysight-dsox4024a",
    "tektronix-tbs2074", "tektronix-tds2024b", "tektronix-tbs1052b",
])
def test_capabilities_json_exposes_setup_and_workflow_choices(model, monkeypatch, capsys):
    from scopes_tool_cli import worker
    from scopes_tool_core.capabilities import operation_supported
    from scopes_tool_core.channel import normalize_channel_coupling, normalize_channel_units
    from scopes_tool_core.measurements import direct_measurement_items
    from scopes_tool_core.trigger import normalize_edge_slope
    from scopes_tool_core.waveform import validate_waveform_points

    def fail_access(*args, **kwargs):
        raise AssertionError("introspection must not access instruments or start a Worker")

    _forbid_visa(monkeypatch)
    monkeypatch.setattr(runtime.Oscilloscope, "open", staticmethod(fail_access))
    monkeypatch.setattr(runtime, "_make_simulator_backend", fail_access)
    monkeypatch.setattr(worker, "run_worker", fail_access)
    assert cli.main(["capabilities", "--model", model, "--json"]) == 0
    payload = _json_stdout(capsys)
    profile = capabilities_for_model_id(model)
    values = payload["capabilities"]
    assert type(payload["schema_version"]) is int
    assert payload["schema_version"] == 2
    assert payload["runtime_identity"] == {"detection_performed": False}
    assert values["direct_measurement_items"] == list(direct_measurement_items(profile))
    assert values["capture_point_options"] == (
        [1000] if model.startswith("tektronix-") else [1000, 5000, 10000]
    )
    for points in values["capture_point_options"]:
        assert validate_waveform_points(points, profile) == points
    assert values["channel_coupling_choices"] == ["ac", "dc"]
    assert values["channel_units_choices"] == ["volt", "amp"]
    for choice in values["channel_coupling_choices"]:
        assert normalize_channel_coupling(choice) == choice
    for choice in values["channel_units_choices"]:
        assert normalize_channel_units(choice) == choice
    assert values["channel_units_channels"] == (
        list(profile.channel_units_channels) if profile.channel_units_channels is not None else None
    )
    assert values["trigger_edge_slopes"] == (
        ["positive", "negative"] if model.startswith("tektronix-")
        else ["positive", "negative", "either", "alternate"]
    )
    assert values["trigger_edge_slopes_source"] == (
        "model_profile" if profile.trigger_edge_slopes is not None else "core_validation"
    )
    for choice in values["trigger_edge_slopes"]:
        assert normalize_edge_slope(choice)
    assert values["supported_operations"] == (
        sorted(profile.supported_operations) if profile.supported_operations is not None else None
    )
    for operation in (
        "acquisition", "channel-coupling", "channel-probe", "channel-bandwidth-limit",
        "channel-invert", "channel-units", "channel-display", "channel-scale",
        "channel-offset", "timebase-scale", "timebase-position", "trigger-edge",
        "measure", "capture", "screenshot",
    ):
        if values["supported_operations"] is not None:
            assert (operation in values["supported_operations"]) == operation_supported(profile, operation)
    if profile.measurement_items is None:
        assert "measurement_items" not in values
    else:
        assert values["measurement_items"] == list(profile.measurement_items)
    assert values["analog_channels"] == profile.analog_channels
    assert values["default_waveform_points"] == profile.default_waveform_points
    assert values["safe_max_waveform_points"] == profile.safe_max_waveform_points
    assert values["screenshot_formats"] == list(profile.screenshot_formats)
    if model == "tektronix-tbs1052b":
        assert "screenshot" in values["supported_operations"]
        assert values["screenshot_formats"] == ["jpeg"]
    if model == "tektronix-tds2024b":
        assert "trigger-edge-level" not in values["supported_operations"]


@pytest.mark.parametrize("operations", [None, frozenset(), frozenset({"measure"})])
def test_capabilities_json_preserves_operation_allowlist_semantics(operations):
    from dataclasses import replace

    profile = replace(capabilities_for_model_id("keysight-dsox4024a"),
                      supported_operations=operations)
    values = runtime._capabilities_json(profile)
    assert values["supported_operations"] == (None if operations is None else sorted(operations))


def test_capabilities_json_preserves_explicit_option_restrictions():
    from dataclasses import replace

    profile = replace(capabilities_for_model_id("tektronix-tbs2074"),
                      trigger_edge_slopes=(), channel_units_channels=(),
                      safe_max_waveform_points=5000)
    values = runtime._capabilities_json(profile)
    assert values["trigger_edge_slopes"] == []
    assert values["trigger_edge_slopes_source"] == "model_profile"
    assert values["channel_units_channels"] == []
    assert values["capture_point_options"] == [1000, 5000]
