from __future__ import annotations

import asyncio
from pathlib import Path
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


def test_explicit_pc_output_root_preserves_job_isolation_and_containment(
    monkeypatch, tmp_path
) -> None:
    manager = JobManager()
    output_root = tmp_path / "selected-output"
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    def fake_execute(*_args, artifact_dir, **_kwargs):
        artifact = artifact_dir / "same-name.txt"
        artifact.write_text(artifact_dir.name, encoding="utf-8")
        return {
            "exit_code": 0,
            "result": {},
            "artifacts": [
                {"kind": "file", "path": str(artifact)},
                {"kind": "file", "path": str(outside)},
            ],
        }

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", fake_execute)
    request = validate_job_request(
        {
            "command": "screenshot",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "pc_output_dir": str(output_root),
            "parameters": {},
        }
    )
    first = manager.submit(request)
    second = manager.submit(request)
    try:
        first = _wait_for_job(manager, first.job_id)
        second = _wait_for_job(manager, second.job_id)

        assert first.artifact_dir.resolve().is_relative_to(output_root.resolve())
        assert second.artifact_dir.resolve().is_relative_to(output_root.resolve())
        assert first.to_payload()["pc_output_dir"] == str(output_root)
        assert first.artifact_dir != second.artifact_dir
        assert [item["name"] for item in first.artifacts] == ["same-name.txt"]
        assert manager.artifact_path(first.job_id, "outside.txt") is None
        assert manager.artifact_path(first.job_id, "same-name.txt")[1].parent == first.artifact_dir
        assert manager.artifact_path(second.job_id, "same-name.txt")[1].parent == second.artifact_dir
    finally:
        asyncio.run(manager.shutdown())


def test_omitted_pc_output_root_uses_data(monkeypatch, tmp_path) -> None:
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
        assert job.artifact_dir.resolve().is_relative_to((tmp_path / "data").resolve())
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


def test_unusable_pc_output_root_returns_a_clear_error(tmp_path) -> None:
    output_file = tmp_path / "not-a-folder"
    output_file.write_text("occupied", encoding="utf-8")

    response = TestClient(app).post(
        "/api/jobs",
        json={
            "command": "identify",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "pc_output_dir": str(output_file),
            "parameters": {},
        },
    )

    assert response.status_code == 400
    assert "Cannot create or write the PC output folder" in response.json()["detail"]


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
