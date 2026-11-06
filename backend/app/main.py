from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from .config import get_settings
from .database import ensure_indexes, get_database
from .deps import get_engine, load_engine
from .routers import analytics, bugs, developers, duplicates, triage

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ensure_indexes(get_database())
    except PyMongoError as exc:
        # Keep starting: /api/health and each request then explain what is missing.
        # The URI is left out of the log because it can contain a password.
        logger.error("MongoDB is not reachable: %s", type(exc).__name__)
    load_engine(app)
    yield


app = FastAPI(title="BugSense AI API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(PyMongoError)
async def database_error(_: Request, exc: PyMongoError) -> JSONResponse:
    logger.error("Database error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is unavailable. Check the MONGODB_URI setting and that MongoDB is reachable."},
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "The server hit an unexpected error. Check the API logs."})


for module in (bugs, duplicates, triage, developers, analytics):
    app.include_router(module.router)


@app.get("/api/health", tags=["System"])
def health(request: Request) -> dict:
    try:
        get_database().command("ping")
        database = True
    except PyMongoError:
        database = False
    return {"status": "ok" if database else "degraded", "database": database, "nlp": get_engine(request).status}


@app.get("/api/system/status", tags=["System"])
def system_status(request: Request) -> dict:
    engine = get_engine(request)
    return {**engine.status, "trained_at": engine.metrics.get("trained_at"), "dataset": engine.metrics.get("dataset")}
