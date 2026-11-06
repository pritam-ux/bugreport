from __future__ import annotations

import time
from urllib.parse import quote

import numpy as np
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import Response
from pymongo.database import Database

from nlp.pipeline import NlpEngine

from ..database import BUGS
from ..deps import current_user, get_db, get_engine
from ..schemas import BugCreate, BugUpdate
from ..services import bugs as bug_service
from ..services import duplicates as duplicate_service
from ..services.developers import developer_names, sync_developer_stats

router = APIRouter(prefix="/api/bugs", tags=["Bug Reports"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_bug(
    payload: BugCreate,
    db: Database = Depends(get_db),
    engine: NlpEngine = Depends(get_engine),
    user: dict = Depends(current_user),
) -> dict:
    """Runs the whole NLP pipeline and returns the saved report with its AI results."""
    started = time.perf_counter()
    bug = bug_service.create_bug(db, engine, payload, user)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    sync_developer_stats(db)
    stored = db[BUGS].find_one({"bug_id": bug["bug_id"]}, {"document": 1, "embedding": 1})
    vector = None if not stored.get("embedding") else np.asarray(stored["embedding"], dtype=np.float32)
    compared = db[BUGS].count_documents({"status": {"$ne": "Duplicate"}, "bug_id": {"$ne": bug["bug_id"]}})
    matches = duplicate_service.enrich_matches(
        db, engine, duplicate_service.display_text(bug), duplicate_service.get_matches(db, bug["bug_id"])
    )
    return {
        "bug": bug_service.public_bug(bug, developer_names(db)),
        "duplicates": matches,
        "engine": engine.status,
        "processing": {**engine.trace(stored["document"], vector, compared), "elapsed_ms": elapsed_ms},
    }


@router.get("")
def list_bugs(
    search: str | None = Query(default=None, max_length=200),
    priority: str | None = None,
    severity: str | None = None,
    component: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    developer: str | None = None,
    triage_status: str | None = None,
    duplicate_review: str | None = None,
    sort: str = "date_desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_db),
) -> dict:
    return bug_service.list_bugs(
        db, search, priority, severity, component, status_filter, developer, triage_status, duplicate_review, sort, page, page_size
    )


@router.get("/{bug_id}")
def get_bug(bug_id: str, db: Database = Depends(get_db)) -> dict:
    return bug_service.public_bug(bug_service.get_bug_or_404(db, bug_id), developer_names(db))


@router.put("/{bug_id}")
def update_bug(
    bug_id: str,
    payload: BugUpdate,
    db: Database = Depends(get_db),
    engine: NlpEngine = Depends(get_engine),
) -> dict:
    return bug_service.public_bug(bug_service.update_bug(db, engine, bug_id, payload), developer_names(db))


@router.delete("/{bug_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bug(bug_id: str, db: Database = Depends(get_db)) -> None:
    bug_service.delete_bug(db, bug_id)


@router.post("/{bug_id}/attachments", status_code=status.HTTP_201_CREATED)
def upload_attachment(
    bug_id: str,
    file: UploadFile = File(...),
    db: Database = Depends(get_db),
) -> dict:
    return bug_service.add_attachment(db, bug_id, file)


@router.get("/{bug_id}/attachments/{attachment_id}")
def download_attachment(
    bug_id: str, attachment_id: str, db: Database = Depends(get_db)
) -> Response:
    content, filename = bug_service.read_attachment(db, bug_id, attachment_id)
    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Content-Type-Options": "nosniff",
        },
    )
