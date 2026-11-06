from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from nlp.pipeline import NlpEngine

from .config import get_settings
from .database import ensure_indexes, get_database
from .deps import current_user
from .routers import analytics, auth, bugs, developers, duplicates, triage, users

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    try:
        ensure_indexes(get_database())
    except PyMongoError as exc:
        # Keep starting: /api/health and each request then explain what is missing.
        logger.error("MongoDB is not reachable at %s: %s", settings.mongodb_uri, exc)
    app.state.nlp = NlpEngine.load(settings.embedding_model, settings.artifacts_dir)
    yield


app = FastAPI(title="BugSense AI API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(PyMongoError)
async def database_error(_: Request, exc: PyMongoError) -> JSONResponse:
    logger.error("Database error: %s", exc)
    return JSONResponse(status_code=503, content={"detail": "The database is unavailable. Check that MongoDB is running."})


for module in (auth, users, bugs, duplicates, triage, developers, analytics):
    app.include_router(module.router)


@app.get("/api/health", tags=["System"])
def health(request: Request) -> dict:
    try:
        get_database().command("ping")
        database = True
    except PyMongoError:
        database = False
    return {"status": "ok" if database else "degraded", "database": database, "nlp": request.app.state.nlp.status}


@app.get("/api/system/status", tags=["System"], dependencies=[Depends(current_user)])
def system_status(request: Request) -> dict:
    engine: NlpEngine = request.app.state.nlp
    return {**engine.status, "trained_at": engine.metrics.get("trained_at"), "dataset": engine.metrics.get("dataset")}
