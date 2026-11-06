from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from nlp.pipeline import NlpEngine

from ..deps import current_user, get_db, get_engine
from ..schemas import DuplicateConfirm, DuplicateSearch
from ..services import bugs as bug_service
from ..services import duplicates as service

router = APIRouter(prefix="/api/duplicates", tags=["Duplicate Detection"])


def _response(db: Database, engine: NlpEngine, bug: dict, matches: list[dict]) -> dict:
    return {
        "bug_id": bug["bug_id"],
        "query": service.display_text(bug),
        "title": bug["title"],
        "status": bug.get("status"),
        "duplicate_of": bug.get("duplicate_of"),
        "duplicate_review": bug.get("duplicate_review"),
        "engine": engine.status,
        "matches": service.enrich_matches(db, engine, service.display_text(bug), matches),
    }


@router.post("/search")
def search(
    payload: DuplicateSearch,
    db: Database = Depends(get_db),
    engine: NlpEngine = Depends(get_engine),
    _: dict = Depends(current_user),
) -> dict:
    """Find similar reports for any text. Nothing is saved."""
    return service.search_text(db, engine, payload.text)


@router.post("/check/{bug_id}")
def check(
    bug_id: str,
    db: Database = Depends(get_db),
    engine: NlpEngine = Depends(get_engine),
    _: dict = Depends(current_user),
) -> dict:
    """Score a saved report against current reports and store the top 5."""
    bug = bug_service.get_bug_or_404(db, bug_id)
    # The hidden fields are needed for scoring, so reload them for this one call.
    full = {**bug, **db["bug_reports"].find_one({"bug_id": bug_id}, {"_id": 0, "embedding": 1, "document": 1})}
    return _response(db, engine, bug, service.run_check(db, engine, full))


@router.post("/confirm")
def confirm(
    payload: DuplicateConfirm,
    db: Database = Depends(get_db),
    engine: NlpEngine = Depends(get_engine),
    user: dict = Depends(current_user),
) -> dict:
    """Store a person's decision. This is the only way a report becomes a duplicate."""
    bug = bug_service.get_bug_or_404(db, payload.bug_id)
    if user["role"] == "Reporter" and bug.get("reporter_id") != user["user_id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only review reports you submitted.")
    if payload.is_duplicate:
        if not payload.matched_bug_id:
            raise HTTPException(422, "Choose the report this one duplicates.")
        bug = service.confirm_duplicate(db, payload.bug_id, payload.matched_bug_id, user)
    else:
        bug = service.confirm_unique(db, payload.bug_id, user)
    return _response(db, engine, bug, service.get_matches(db, payload.bug_id))


@router.get("/{bug_id}")
def stored_matches(
    bug_id: str,
    db: Database = Depends(get_db),
    engine: NlpEngine = Depends(get_engine),
    _: dict = Depends(current_user),
) -> dict:
    bug = bug_service.get_bug_or_404(db, bug_id)
    return _response(db, engine, bug, service.get_matches(db, bug_id))
