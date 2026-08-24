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
