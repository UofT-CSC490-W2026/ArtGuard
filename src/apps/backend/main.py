"""ArtGuard API -- FastAPI application entry point.

Creates the FastAPI app, configures CORS middleware, request logging,
and registers all route modules. This module is the target for Uvicorn::

    uvicorn src.apps.backend.main:app --host 0.0.0.0 --port 8000
"""

import json
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.apps.backend.logging_config import RequestLoggingMiddleware, setup_logging
from src.apps.backend.routes.auth_router import router as auth_router
from src.apps.backend.routes.inference_router import router as inference_router
from src.apps.backend.routes.inferences_router import router as inferences_router
from src.apps.backend.routes.process_data_router import router as process_data_router
from src.apps.backend.routes.rag_router import router as rag_router
from src.apps.backend.routes.train_router import router as train_router

# ---------------------------------------------------------------------------
# Structured logging (must be called before any logger usage)
# ---------------------------------------------------------------------------
setup_logging()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Modal auth: ECS injects MODAL_API_KEY as JSON
# ---------------------------------------------------------------------------
_modal_key = os.getenv("MODAL_API_KEY", "")
if _modal_key.startswith("{"):
    try:
        _mk = json.loads(_modal_key)
        os.environ["MODAL_TOKEN_ID"] = _mk["token_id"]
        os.environ["MODAL_TOKEN_SECRET"] = _mk["token_secret"]
    except (json.JSONDecodeError, KeyError):
        logger.warning("Failed to parse MODAL_API_KEY JSON")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="ArtGuard API", version="1.0.1")

# Request logging middleware (outermost — runs first, logs request/response)
app.add_middleware(RequestLoggingMiddleware)

# CORS: comma-separated origins, or * for any.
_cors_raw = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
if _cors_raw == "*":
    _cors_list = ["*"]
else:
    _cors_list = [o.strip() for o in _cors_raw.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(inference_router)
app.include_router(inferences_router)
app.include_router(process_data_router)
app.include_router(rag_router)
app.include_router(train_router)

logger.info(
    "ArtGuard API started",
    extra={"environment": os.getenv("ENVIRONMENT", "dev")},
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return a simple health-check response for load balancer probes."""
    return {"status": "ok"}


@app.get("/")
async def root() -> dict:
    """Return API metadata and a summary of available endpoints."""
    return {
        "message": "Welcome to ArtGuard API",
        "version": "1.0.1",
        "endpoints": {
            "/health": "Health check",
            "/auth/*": "Signup, login, profile, change-password (JWT)",
            "/inference": "Multipart image + artist/artwork (Bearer required)",
            "/inferences/*": "List, stats, get, delete inference history (Bearer)",
            "/train": "Start a training run (POST)",
            "/evaluate": "Start an evaluation run (POST)",
            "/process_data": "Kick off ECS data processing task (POST)",
            "/rag-query": "Query Bedrock Knowledge Base (POST)",
        },
    }
