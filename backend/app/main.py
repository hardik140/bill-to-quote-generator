from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import bills, documents, scenarios
from app.core.config import settings
from app.core.database import Base, engine
from app.models import *  # noqa: F401,F403 - ensures all models are registered on Base

app = FastAPI(title="Local Bill-to-Quotation Scenario Generator", version="1.0.0")

# TRD §11: restrict to localhost origins only, no arbitrary CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allow_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    settings.ensure_storage_dirs()
    Base.metadata.create_all(bind=engine)


app.include_router(documents.router)
app.include_router(bills.router)
app.include_router(scenarios.router)

app.mount(
    "/files/generated",
    StaticFiles(directory=str(settings.generated_dir)),
    name="generated-files",
)
app.mount(
    "/files/uploads",
    StaticFiles(directory=str(settings.uploads_dir)),
    name="uploaded-files",
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
