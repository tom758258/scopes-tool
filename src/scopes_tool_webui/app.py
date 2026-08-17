"""FastAPI application for the local Scopes Tool WebUI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from . import __version__


PACKAGE_NAME = "scopes-tool-webui"
STATIC_DIR = Path(__file__).with_name("static")

app = FastAPI(title="Scopes Tool WebUI")
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
