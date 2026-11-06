from __future__ import annotations

import threading

from fastapi import FastAPI, Request
from pymongo.database import Database

from nlp.pipeline import NlpEngine

from .config import get_settings
from .database import get_database

# The app has no sign-in. Every visitor shares this one identity and has full access.
WORKSPACE_USER = {"user_id": "USR-WORKSPACE", "name": "Team member"}

_engine_lock = threading.Lock()


def get_db() -> Database:
    return get_database()


def current_user() -> dict:
    return WORKSPACE_USER


def load_engine(app: FastAPI) -> NlpEngine:
    state = app.state
    engine = getattr(state, "nlp", None)
    if engine is None:
        with _engine_lock:
            engine = getattr(state, "nlp", None)
            if engine is None:
                settings = get_settings()
                engine = state.nlp = NlpEngine.load(settings.embedding_model, settings.artifacts_dir)
    return engine


def get_engine(request: Request) -> NlpEngine:
    """Also loads the models here in case the host did not run startup events."""
    return load_engine(request.app)
