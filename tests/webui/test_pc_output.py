from __future__ import annotations

import asyncio
from pathlib import Path
import re
import shutil
import subprocess
import textwrap
import time

from fastapi.testclient import TestClient
import pytest

import scopes_tool_webui.app as app_module
from scopes_tool_webui.app import app
from scopes_tool_webui.commands import validate_job_request
from scopes_tool_webui.desktop import FolderSelectionUnavailable
from scopes_tool_webui.jobs import JobManager


MODEL_ID = "keysight-dsox4024a"
STATIC_ROOT = Path(__file__).parents[2] / "src" / "scopes_tool_webui" / "static"


def _wait_for_job(manager: JobManager, job_id: str):
    for _ in range(100):
        job = manager.get(job_id)
        assert job is not None
        if job.status not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError("WebUI job did not reach a terminal state")


@pytest.mark.parametrize(
    ("selection", "expected"),
    ((Path("C:/ScopeData"), {"selected": True, "folder_path": "C:\\ScopeData"}),
     (None, {"selected": False, "folder_path": None})),
)
def test_pc_output_folder_selector_selected_and_cancelled(
    monkeypatch, selection, expected
) -> None:
    monkeypatch.setattr(app_module, "select_directory_with_dialog", lambda: selection)

    response = TestClient(app).post("/api/pc-output/select-folder")

    assert response.status_code == 200
    assert response.json() == expected


def test_pc_output_folder_selector_unavailable(monkeypatch) -> None:
    def unavailable():
        raise FolderSelectionUnavailable("folder selection dialog is unavailable")

    monkeypatch.setattr(app_module, "select_directory_with_dialog", unavailable)

    response = TestClient(app).post("/api/pc-output/select-folder")

    assert response.status_code == 503
    assert response.json()["detail"] == "folder selection dialog is unavailable"


def test_non_output_job_does_not_create_or_validate_pc_output_root(
    monkeypatch, tmp_path
) -> None:
    manager = JobManager()
    output_root = tmp_path / "not-a-folder"
    output_root.write_text("unchanged", encoding="utf-8")
    monkeypatch.setattr(
        "scopes_tool_webui.jobs.execute_command",
        lambda *_args, **_kwargs: {"exit_code": 0, "result": {}, "artifacts": []},
    )
    request = validate_job_request(
        {
            "command": "identify",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "pc_output_dir": str(output_root),
            "parameters": {},
        }
    )
    job = manager.submit(request)
    try:
        job = _wait_for_job(manager, job.job_id)
        assert job.status == "completed"
        assert job.to_payload()["pc_output_dir"] == str(output_root)
        assert output_root.read_text(encoding="utf-8") == "unchanged"
    finally:
        asyncio.run(manager.shutdown())


def test_omitted_pc_output_root_uses_data_without_creating_it(monkeypatch, tmp_path) -> None:
    manager = JobManager()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "scopes_tool_webui.jobs.execute_command",
        lambda *_args, **_kwargs: {"exit_code": 0, "result": {}, "artifacts": []},
    )
    request = validate_job_request(
        {
            "command": "identify",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {},
        }
    )
    job = manager.submit(request)
    try:
        job = _wait_for_job(manager, job.job_id)
        assert request["pc_output_dir"] == "data"
        assert job.pc_output_root == (tmp_path / "data").resolve()
        assert not (tmp_path / "data").exists()
    finally:
        asyncio.run(manager.shutdown())


def test_screenshot_writes_directly_to_root_without_overwriting_and_downloads(
    monkeypatch, tmp_path
) -> None:
    manager = JobManager()
    monkeypatch.setattr(app_module, "job_manager", manager)
    output_root = tmp_path / "screenshots"
    request = validate_job_request(
        {
            "command": "screenshot",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "pc_output_dir": str(output_root),
            "parameters": {"background": "black"},
        }
    )
    first = manager.submit(request)
    try:
        first = _wait_for_job(manager, first.job_id)
        second = _wait_for_job(manager, manager.submit(request).job_id)

        assert first.status == second.status == "completed"
        first_path = first.artifact_paths[first.artifacts[0]["name"]]
        second_path = second.artifact_paths[second.artifacts[0]["name"]]
        assert first_path.parent == second_path.parent == output_root.resolve()
        assert first_path != second_path
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}(?:-\d+)?\.png",
            first_path.name,
        )
        assert not list(output_root.glob("scopes-tool-webui-*"))

        response = TestClient(app).get(first.to_payload()["artifacts"][0]["url"])
        assert response.status_code == 200
        assert response.content == first_path.read_bytes()
    finally:
        asyncio.run(manager.shutdown())


def test_capture_uses_timestamp_stem_directly_under_selected_root(tmp_path) -> None:
    manager = JobManager()
    output_root = tmp_path / "captures"
    request = validate_job_request(
        {
            "command": "capture",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "pc_output_dir": str(output_root),
            "parameters": {"channel": 1, "points": 1000, "format": "byte"},
        }
    )
    job = manager.submit(request)
    try:
        job = _wait_for_job(manager, job.job_id)
        paths = set(job.artifact_paths.values())
        csv_path = next(path for path in paths if path.suffix == ".csv")
        meta_path = next(path for path in paths if path.name.endswith("_meta.json"))
        assert job.status == "completed"
        assert csv_path.parent == meta_path.parent == output_root.resolve()
        assert meta_path.name == f"{csv_path.stem}_meta.json"
        assert not list(output_root.glob("scopes-tool-webui-*"))
    finally:
        asyncio.run(manager.shutdown())


def test_capture_batch_uses_core_command_directory_under_selected_root(tmp_path) -> None:
    manager = JobManager()
    output_root = tmp_path / "workflow-output"
    request = validate_job_request(
        {
            "command": "capture-batch",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "pc_output_dir": str(output_root),
            "parameters": {
                "channels": "1",
                "points": 1000,
                "format": "byte",
                "count": 1,
                "interval_seconds": 0,
            },
        }
    )
    job = manager.submit(request)
    try:
        job = _wait_for_job(manager, job.job_id)
        artifact_dirs = {path.parent for path in job.artifact_paths.values()}
        assert job.status == "completed"
        assert len(artifact_dirs) == 1
        output_dir = artifact_dirs.pop()
        assert output_dir.parent == output_root.resolve() / "captures"
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}(?:-\d+)?",
            output_dir.name,
        )
    finally:
        asyncio.run(manager.shutdown())


def test_artifact_registration_is_job_owned_and_root_contained(monkeypatch, tmp_path) -> None:
    manager = JobManager()
    output_root = tmp_path / "selected-output"
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    def fake_execute(command, *_args, artifact_dir, **_kwargs):
        if command != "screenshot":
            return {"exit_code": 0, "result": {}, "artifacts": []}
        artifact_dir.mkdir(parents=True)
        artifact = artifact_dir / "owned.txt"
        artifact.write_text("owned", encoding="utf-8")
        return {
            "exit_code": 0,
            "result": {},
            "artifacts": [
                {"kind": "file", "path": str(artifact)},
                {"kind": "file", "path": str(outside)},
            ],
        }

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", fake_execute)
    monkeypatch.setattr(app_module, "job_manager", manager)
    base_request = {
        "mode": "simulate",
        "model_id": MODEL_ID,
        "pc_output_dir": str(output_root),
        "parameters": {},
    }
    first = manager.submit(validate_job_request({"command": "screenshot", **base_request}))
    second = manager.submit(validate_job_request({"command": "identify", **base_request}))
    try:
        first = _wait_for_job(manager, first.job_id)
        second = _wait_for_job(manager, second.job_id)
        assert [item["name"] for item in first.artifacts] == ["owned.txt"]
        assert manager.artifact_path(first.job_id, "owned.txt") is not None
        assert manager.artifact_path(first.job_id, "outside.txt") is None
        assert manager.artifact_path(first.job_id, "../owned.txt") is None
        assert manager.artifact_path(second.job_id, "owned.txt") is None
        client = TestClient(app)
        assert client.get(f"/api/jobs/{first.job_id}/artifacts/owned.txt").status_code == 200
        assert client.get(f"/api/jobs/{second.job_id}/artifacts/owned.txt").status_code == 404
    finally:
        asyncio.run(manager.shutdown())


def test_dry_run_plans_selected_root_without_creating_it(tmp_path) -> None:
    manager = JobManager()
    output_root = tmp_path / "planned-output"
    request = validate_job_request(
        {
            "command": "capture",
            "mode": "dry-run",
            "model_id": MODEL_ID,
            "pc_output_dir": str(output_root),
            "parameters": {"channel": 1, "points": 1000, "format": "byte"},
        }
    )
    job = manager.submit(request)
    try:
        job = _wait_for_job(manager, job.job_id)
        planned_paths = [Path(item["path"]) for item in job.result["result"]["files"]]
        assert job.status == "completed"
        assert all(path.parent == output_root.resolve() for path in planned_paths)
        assert not output_root.exists()
    finally:
        asyncio.run(manager.shutdown())


def test_serial_lister_export_filename_cannot_escape_pc_output_root() -> None:
    response = TestClient(app).post(
        "/api/jobs",
        json={
            "command": "serial-lister-export",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"filename": "../escape.csv"},
        },
    )

    assert response.status_code == 400
    assert "filename" in response.json()["detail"].lower()


def test_pc_output_command_reports_unusable_root_when_it_writes(tmp_path) -> None:
    output_file = tmp_path / "not-a-folder"
    output_file.write_text("occupied", encoding="utf-8")
    manager = JobManager()
    request = validate_job_request(
        {
            "command": "screenshot",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "pc_output_dir": str(output_file),
            "parameters": {"background": "black"},
        }
    )
    job = manager.submit(request)
    try:
        job = _wait_for_job(manager, job.job_id)
        assert job.status == "failed"
        assert "screenshot PNG" in job.error
        assert str(output_file) in job.error
    finally:
        asyncio.run(manager.shutdown())


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_pc_output_frontend_controls_context_and_command_note() -> None:
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    app_source = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    jobs_source = (STATIC_ROOT / "jobs.js").read_text(encoding="utf-8")
    module_path = STATIC_ROOT / "pc-output.js"

    assert 'id="pc-output-dir" value="data"' in html
    assert 'id="pc-output-select"' in html
    assert 'id="pc-output-default"' in html
    assert 'id="pc-output-command-note"' in html
    assert "const commandContext = pcOutputContext(context, elements.pcOutput);" in app_source
    assert "submitJob({ command, parameters, ...context })" in jobs_source
    default_handler = app_source.split(
        'elements.pcOutputDefault.addEventListener("click"', 1
    )[1].split('elements.pcOutputSelect.addEventListener("click"', 1)[0]
    assert "resetPcOutputDirectory(elements.pcOutput);" in default_handler
    assert "selectPcOutputFolder" not in default_handler

    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        globalThis.translate = (key, values = {}) => `${key}:${values.path ?? ""}`;
        const source = fs.readFileSync(process.argv[1], "utf8")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.pcOutput = { pcOutputContext, resetPcOutputDirectory, renderPcOutputCommandNote };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const input = { value: "D:\\ScopeData" };
        const context = pcOutput.pcOutputContext({ mode: "simulate" }, input);
        assert.equal(context.pc_output_dir, "D:\\ScopeData");
        pcOutput.resetPcOutputDirectory(input);
        assert.equal(input.value, "data");

        const note = { hidden: true, textContent: "" };
        pcOutput.renderPcOutputCommandNote(note, { pc_output: true }, input);
        assert.equal(note.hidden, false);
        assert.equal(note.textContent, "pcOutput.commandNote:data");
        pcOutput.renderPcOutputCommandNote(note, { pc_output: false }, input);
        assert.equal(note.hidden, true);
        assert.equal(note.textContent, "");
        ''')
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script, str(module_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_pc_output_catalog_and_locale_keys_are_centralized() -> None:
    catalog = TestClient(app).get("/api/commands").json()
    pc_output_commands = {entry["id"] for entry in catalog if entry["pc_output"]}
    assert pc_output_commands == {
        "screenshot",
        "capture",
        "serial-lister-export",
        "segmented-capture",
        "capture-batch",
        "measure-log",
        "measure-until",
        "triggered-measure-loop",
        "triggered-capture-series",
    }
    for locale_name in ("locale_en.js", "locale_zh_tw.js"):
        locale_source = (STATIC_ROOT / locale_name).read_text(encoding="utf-8")
        for key in (
            "pcOutput.label",
            "pcOutput.helper",
            "pcOutput.commandNote",
            "pcOutput.selectionFailed",
            "actions.select",
            "actions.default",
        ):
            assert f'"{key}"' in locale_source
