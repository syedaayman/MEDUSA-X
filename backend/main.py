"""FastAPI application entry point for MEDUSA-X.

Start from the repository root with:
    uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
"""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import repository
from backend.api.dataset_routes import router as dataset_router
from backend.api.patient_routes import router as patient_router
from backend.api.report_routes import router as report_router
from backend.api.upload_routes import router as upload_router
from backend.config import settings
from backend.db import init_db

app = FastAPI(
    title="MEDUSA-X API",
    description=(
        "Clinical record intelligence, reconciliation and timeline prototype. "
        "Research prototype only: findings are potential discrepancies, not medical conclusions."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(patient_router)
app.include_router(report_router)
app.include_router(dataset_router)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health", tags=["system"])
def health_check() -> dict[str, object]:
    """Report process health and whether model-backed agents are configured."""
    return {
        "status": "ok",
        "prototype": True,
        "database": "sqlite",
        "database_path": str(settings.database_path),
        "llm_enabled": settings.llm_enabled,
        "model": settings.openai_model if settings.llm_enabled else None,
        "engine_mode": "agents_sdk" if settings.llm_enabled else "deterministic_pipeline",
        "patients": len(repository.list_patients()),
    }


FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if (FRONTEND_DIST / "index.html").is_file():
    _assets = FRONTEND_DIST / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_client(full_path: str) -> FileResponse:
        """Serve the built React app; unknown API paths still return a JSON 404."""
        if full_path.split("/", 1)[0] in {"api", "health", "docs", "redoc", "openapi.json"}:
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
