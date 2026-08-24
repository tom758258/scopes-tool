"""FastAPI application for the local Scopes Tool WebUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from . import __version__
from .commands import command_catalog, model_catalog, validate_job_request
from .desktop import (
    FolderOpenUnavailable,
    FolderSelectionUnavailable,
    open_directory_in_shell,
    select_directory_with_dialog,
)
from .jobs import JobManagerShuttingDown, job_manager


PACKAGE_NAME = "scopes-tool-webui"
STATIC_DIR = Path(__file__).with_name("static")


class NoStoreStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


def _asset_version(filename: str) -> str:
    path = STATIC_DIR / filename
    if not path.exists():
        return "0"
    return str(path.stat().st_mtime_ns)


app = FastAPI(title="Scopes Tool WebUI")
app.mount("/static", NoStoreStaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace(
        "/static/styles.css",
        f"/static/styles.css?v={_asset_version('styles.css')}",
    )
    html = html.replace(
        "/static/app.js",
        f"/static/app.js?v={_asset_version('app.js')}",
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "package": PACKAGE_NAME,
        "version": __version__,
    }


@app.get("/api/commands")
async def commands() -> list[dict[str, Any]]:
    return command_catalog()


@app.get("/api/models")
async def models() -> list[dict[str, str]]:
    return model_catalog()


@app.post("/api/pc-output/select-folder")
def select_pc_output_folder() -> dict[str, Any]:
    try:
        selected = select_directory_with_dialog()
    except FolderSelectionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc) or "folder selection dialog is unavailable"
        raise HTTPException(status_code=503, detail=detail) from exc
    if selected is None or not str(selected).strip():
        return {"selected": False, "folder_path": None}
    return {"selected": True, "folder_path": str(selected)}


@app.post("/api/pc-output/open-folder")
def open_pc_output_folder(payload: dict[str, Any] = Body(...)) -> dict[str, bool]:
    raw_path = payload.get("pc_output_dir", "data")
    if not isinstance(raw_path, str):
        raise HTTPException(status_code=400, detail="pc_output_dir must be a string")
    effective_path = raw_path.strip() or "data"
    try:
        open_directory_in_shell(Path(effective_path))
    except FolderOpenUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc) or "folder opening is unavailable"
        raise HTTPException(status_code=503, detail=detail) from exc
    return {"ok": True}


@app.post("/api/jobs", status_code=202)
async def submit_job(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        request = validate_job_request(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        job = job_manager.submit(request)
    except JobManagerShuttingDown as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, "job_id": job.job_id, "status": job.status}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_payload()


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, Any]:
    outcome = job_manager.cancel(job_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Job not found")
    state, message, accepted = outcome
    if not accepted:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "status": state, "message": message}


@app.get("/api/jobs/{job_id}/artifacts/{name}")
async def get_artifact(job_id: str, name: str) -> FileResponse:
    artifact = job_manager.artifact_path(job_id, name)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    _job, path = artifact
    return FileResponse(path)
