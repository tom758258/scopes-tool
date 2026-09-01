from __future__ import annotations

import asyncio
from pathlib import Path
import re
import shutil
import subprocess
import textwrap
import threading
import time

from fastapi.testclient import TestClient
import pytest

import scopes_tool_webui.app as app_module
import scopes_tool_webui.desktop as desktop_module
from scopes_tool_webui.app import app
from scopes_tool_webui.commands import validate_job_request
from scopes_tool_webui.desktop import (
    FolderOpenUnavailable,
    FolderSelectionUnavailable,
    open_directory_in_shell,
)
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


def test_pc_output_folder_selector_selected_and_cancelled(
    monkeypatch, tmp_path
) -> None:
    selection = tmp_path / "selected-output"
    monkeypatch.setattr(app_module, "select_directory_with_dialog", lambda: selection)
    response = TestClient(app).post("/api/pc-output/select-folder")
    assert response.status_code == 200
    assert response.json() == {"selected": True, "folder_path": str(selection)}

    monkeypatch.setattr(app_module, "select_directory_with_dialog", lambda: None)
    response = TestClient(app).post("/api/pc-output/select-folder")
    assert response.status_code == 200
    assert response.json() == {"selected": False, "folder_path": None}


def test_pc_output_folder_selector_unavailable(monkeypatch) -> None:
    def unavailable():
        raise FolderSelectionUnavailable("folder selection dialog is unavailable")

    monkeypatch.setattr(app_module, "select_directory_with_dialog", unavailable)

    response = TestClient(app).post("/api/pc-output/select-folder")

    assert response.status_code == 503
    assert response.json()["detail"] == "folder selection dialog is unavailable"


@pytest.mark.parametrize("raw_path", (None, ""))
def test_open_pc_output_folder_blank_uses_default(monkeypatch, raw_path) -> None:
    opened = []
    monkeypatch.setattr(app_module, "open_directory_in_shell", opened.append)
    payload = {} if raw_path is None else {"pc_output_dir": raw_path}

    response = TestClient(app).post("/api/pc-output/open-folder", json=payload)

    assert response.status_code == 200
    assert opened == [Path("data")]


def test_open_pc_output_folder_uses_explicit_path(monkeypatch, tmp_path) -> None:
    opened = []
    output_root = tmp_path / "explicit-output"
    monkeypatch.setattr(app_module, "open_directory_in_shell", opened.append)

    response = TestClient(app).post(
        "/api/pc-output/open-folder",
        json={"pc_output_dir": f"  {output_root}  "},
    )

    assert response.status_code == 200
    assert opened == [output_root]


def test_open_pc_output_folder_creates_missing_directory_and_calls_shell(
    monkeypatch, tmp_path
) -> None:
    opened = []
    output_root = tmp_path / "missing-output"
    monkeypatch.setattr(desktop_module.os, "startfile", opened.append, raising=False)

    resolved = open_directory_in_shell(output_root)

    assert resolved == output_root.resolve()
    assert output_root.is_dir()
    assert opened == [str(output_root.resolve())]


def test_open_pc_output_folder_rejects_non_directory(tmp_path) -> None:
    output_path = tmp_path / "output-file"
    output_path.write_text("occupied", encoding="utf-8")

    response = TestClient(app).post(
        "/api/pc-output/open-folder",
        json={"pc_output_dir": str(output_path)},
    )

    assert response.status_code == 503
    assert "not a directory" in response.json()["detail"]


def test_open_pc_output_folder_reports_shell_failure(monkeypatch, tmp_path) -> None:
    def unavailable(_path):
        raise FolderOpenUnavailable("shell could not open the folder")

    monkeypatch.setattr(app_module, "open_directory_in_shell", unavailable)

    response = TestClient(app).post(
        "/api/pc-output/open-folder",
        json={"pc_output_dir": str(tmp_path)},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "shell could not open the folder"


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


def test_screenshot_default_root_is_data_under_current_directory(
    monkeypatch, tmp_path
) -> None:
    manager = JobManager()
    monkeypatch.chdir(tmp_path)
    request = validate_job_request(
        {
            "command": "screenshot",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "parameters": {"background": "black"},
        }
    )
    job = manager.submit(request)
    try:
        job = _wait_for_job(manager, job.job_id)
        artifact_path = next(iter(job.artifact_paths.values()))
        assert job.status == "completed"
        assert artifact_path.parent == (tmp_path / "data").resolve()
    finally:
        asyncio.run(manager.shutdown())


def test_concurrent_pc_output_jobs_are_serialized_and_keep_owned_downloads(
    monkeypatch, tmp_path
) -> None:
    manager = JobManager()
    monkeypatch.setattr(app_module, "job_manager", manager)
    output_root = tmp_path / "concurrent-output"
    state_lock = threading.Lock()
    active = 0
    max_active = 0
    invocation = 0

    def fake_execute(*_args, artifact_dir, **_kwargs):
        nonlocal active, max_active, invocation
        with state_lock:
            active += 1
            max_active = max(max_active, active)
            invocation += 1
            content = f"job-{invocation}".encode()
        try:
            candidate = artifact_dir / "2026-08-24-14-00-48.png"
            if candidate.exists():
                candidate = artifact_dir / "2026-08-24-14-00-48-2.png"
            time.sleep(0.05)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(content)
            return {
                "exit_code": 0,
                "result": {"artifact": candidate.name},
                "artifacts": [{"kind": "screenshot", "path": str(candidate)}],
            }
        finally:
            with state_lock:
                active -= 1

    monkeypatch.setattr("scopes_tool_webui.jobs.execute_command", fake_execute)
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
    second = manager.submit(request)
    try:
        first = _wait_for_job(manager, first.job_id)
        second = _wait_for_job(manager, second.job_id)
        assert max_active == 1
        assert {item["name"] for job in (first, second) for item in job.artifacts} == {
            "2026-08-24-14-00-48.png",
            "2026-08-24-14-00-48-2.png",
        }
        client = TestClient(app)
        downloaded = {
            client.get(job.to_payload()["artifacts"][0]["url"]).content
            for job in (first, second)
        }
        assert downloaded == {b"job-1", b"job-2"}
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
            "parameters": {"channels": "1", "points": 1000, "format": "byte"},
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
            "parameters": {"channels": "1", "points": 1000, "format": "byte"},
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


def test_serial_lister_export_duplicate_filename_fails_without_changing_owner(
    monkeypatch, tmp_path
) -> None:
    manager = JobManager()
    monkeypatch.setattr(app_module, "job_manager", manager)
    output_root = tmp_path / "lister-output"
    request = validate_job_request(
        {
            "command": "serial-lister-export",
            "mode": "simulate",
            "model_id": MODEL_ID,
            "pc_output_dir": str(output_root),
            "parameters": {"filename": "lister.csv"},
        }
    )
    first = manager.submit(request)
    try:
        first = _wait_for_job(manager, first.job_id)
        assert first.status == "completed"
        client = TestClient(app)
        artifact_url = first.to_payload()["artifacts"][0]["url"]
        original = client.get(artifact_url).content
        assert original

        second = _wait_for_job(manager, manager.submit(request).job_id)
        assert second.status == "failed"
        assert "Serial Lister output file already exists" in second.error
        assert client.get(artifact_url).content == original
    finally:
        asyncio.run(manager.shutdown())


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
    results_source = (STATIC_ROOT / "results.js").read_text(encoding="utf-8")
    execution_context_source = (STATIC_ROOT / "execution-context.js").read_text(encoding="utf-8")
    state_source = (STATIC_ROOT / "state.js").read_text(encoding="utf-8")
    module_path = STATIC_ROOT / "pc-output.js"

    assert 'id="pc-output-dir"' in html
    assert 'id="pc-output-dir" value=' not in html
    assert 'data-i18n-placeholder="pcOutput.defaultPlaceholder"' in html
    assert 'id="pc-output-select"' in html
    assert 'id="pc-output-default"' not in html
    assert 'id="pc-output-open"' in html
    assert 'id="pc-output-command-note"' in html
    assert "const commandContext = pcOutputContext(context, elements.pcOutput);" in app_source
    assert "submitJob({ command, parameters, ...context })" in jobs_source
    assert 'elements.pcOutputOpen.addEventListener("click"' in app_source
    assert "openPcOutputFolder(path)" in app_source
    assert "job.artifacts" in results_source
    assert 'import { pcOutputDirectory } from "/static/pc-output.js";' in execution_context_source
    assert "pc_output_dir: pcOutputDirectory(elements.pcOutput)" in execution_context_source
    assert '"data"' not in execution_context_source
    assert 'import { DEFAULT_PC_OUTPUT_DIR } from "/static/pc-output.js";' in state_source
    assert "pc_output_dir: DEFAULT_PC_OUTPUT_DIR" in state_source
    assert '"data"' not in state_source

    script = textwrap.dedent(
        r'''
        import assert from "node:assert/strict";
        import fs from "node:fs";
        globalThis.translate = (key, values = {}) => `${key}:${values.path ?? ""}`;
        const source = [
          fs.readFileSync(process.argv[1], "utf8"),
          fs.readFileSync(process.argv[2], "utf8"),
          fs.readFileSync(process.argv[3], "utf8"),
        ].join("\n")
          .replace(/^import[^\n]*\r?\n/gm, "")
          .replace(/^export /gm, "")
          + "\nglobalThis.pcOutput = { createInitialState, getExecutionContext, pcOutputContext, pcOutputDirectory, renderPcOutputCommandNote };";
        await import(`data:text/javascript;charset=utf-8,${encodeURIComponent(source)}`);

        const input = { value: "" };
        assert.equal(pcOutput.createInitialState().executionContext.pc_output_dir, "data");
        assert.equal(pcOutput.pcOutputContext({ mode: "simulate" }, input).pc_output_dir, "data");
        const elements = {
          mode: { value: "simulate" },
          resource: { value: "" },
          model: { value: "keysight-dsox4024a" },
          pcOutput: input,
        };
        assert.equal(pcOutput.getExecutionContext(elements).pc_output_dir, "data");
        const note = { hidden: true, textContent: "" };
        pcOutput.renderPcOutputCommandNote(note, { pc_output: true }, input);
        assert.equal(note.textContent, "pcOutput.commandNote:pcOutput.defaultDisplay:");

        input.value = "  D:\\ScopeData  ";
        const context = pcOutput.pcOutputContext({ mode: "simulate" }, input);
        assert.equal(context.pc_output_dir, "D:\\ScopeData");
        assert.equal(pcOutput.getExecutionContext(elements).pc_output_dir, "D:\\ScopeData");
        pcOutput.renderPcOutputCommandNote(note, { pc_output: true }, input);
        assert.equal(note.hidden, false);
        assert.equal(note.textContent, "pcOutput.commandNote:D:\\ScopeData");
        pcOutput.renderPcOutputCommandNote(note, { pc_output: false }, input);
        assert.equal(note.hidden, true);
        assert.equal(note.textContent, "");
        ''')
    completed = subprocess.run(
        [
            "node", "--input-type=module", "--eval", script,
            str(module_path), str(STATIC_ROOT / "execution-context.js"),
            str(STATIC_ROOT / "state.js"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_pc_output_helper_text_is_plain_localized_text() -> None:
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    english = (STATIC_ROOT / "locale_en.js").read_text(encoding="utf-8")
    chinese = (STATIC_ROOT / "locale_zh_tw.js").read_text(encoding="utf-8")

    assert "Leave it blank to use the data folder." in html
    assert "Leave it blank to use the data folder." in english
    assert "留空時預設使用 data 資料夾。" in chinese
    for source in (html, english, chinese):
        helper_text = source.split("pcOutput.helper", 1)[1].split("\n", 1)[0]
        assert "`" not in helper_text


def test_pc_output_catalog_and_locale_keys_are_centralized() -> None:
    catalog = TestClient(app).get("/api/commands").json()
    pc_output_commands = {entry["id"] for entry in catalog if entry["pc_output"]}
    assert pc_output_commands == {
        "screenshot",
        "capture",
        "serial-lister-export",
        "segmented-capture",
        "capture-batch",
        "capture-until",
        "capture-monitor",
        "measure-log",
        "measure-until",
        "triggered-measure-loop",
        "triggered-capture-series",
        "sequence",
    }
    for locale_name in ("locale_en.js", "locale_zh_tw.js"):
        locale_source = (STATIC_ROOT / locale_name).read_text(encoding="utf-8")
        for key in (
            "pcOutput.label",
            "pcOutput.defaultPlaceholder",
            "pcOutput.defaultDisplay",
            "pcOutput.helper",
            "pcOutput.commandNote",
            "pcOutput.selectionFailed",
            "pcOutput.openFailed",
            "actions.selectFolder",
            "actions.openFolder",
        ):
            assert f'"{key}"' in locale_source
