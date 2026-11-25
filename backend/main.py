"""FastAPI application entry point for MEDUSA-X."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.patient_routes import router as patient_router
from api.report_routes import router as report_router
from api.upload_routes import router as upload_router
from config import settings

app = FastAPI(
    title="MEDUSA-X API",
    description="Clinical Record Reconciliation System",
    version="1.0.0",
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


@app.get("/health")
def health_check() -> dict[str, str]:
    """Report whether the API process is responding."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
