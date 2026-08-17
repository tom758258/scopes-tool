"""FastAPI application for the local Scopes Tool WebUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from . import __version__
from .commands import command_catalog, model_catalog, validate_job_request
from .jobs import JobManager


PACKAGE_NAME = "scopes-tool-webui"
STATIC_DIR = Path(__file__).with_name("static")

app = FastAPI(title="Scopes Tool WebUI")
job_manager = JobManager()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


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


@app.post("/api/jobs", status_code=202)
async def submit_job(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        request = validate_job_request(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = job_manager.submit(request)
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
    state, message = outcome
    if state == "running":
        raise HTTPException(status_code=409, detail=message)
    if state in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "status": state, "message": message}


@app.get("/api/jobs/{job_id}/artifacts/{name}")
async def get_artifact(job_id: str, name: str) -> FileResponse:
    artifact = job_manager.artifact_path(job_id, name)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    _job, path = artifact
    return FileResponse(path)
