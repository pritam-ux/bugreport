from __future__ import annotations

from fastapi import APIRouter, Depends
from pymongo.database import Database

from nlp.pipeline import NlpEngine

from ..deps import get_db, get_engine
from ..services import analytics as service

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/dashboard")
def dashboard(db: Database = Depends(get_db)) -> dict:
    return service.dashboard(db)


@router.get("/duplicates")
def duplicates(db: Database = Depends(get_db), engine: NlpEngine = Depends(get_engine)) -> dict:
    return service.duplicate_stats(db, engine)


@router.get("/triage")
def triage(db: Database = Depends(get_db), engine: NlpEngine = Depends(get_engine)) -> dict:
    return service.triage_stats(db, engine)
