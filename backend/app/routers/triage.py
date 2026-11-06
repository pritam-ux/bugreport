from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from nlp.pipeline import NlpEngine

from ..deps import current_user, get_db, get_engine, require_roles
from ..schemas import BugCreate, TriageDecision
from ..services import bugs as bug_service
from ..services import triage as service
from ..services.developers import developer_names

router = APIRouter(prefix="/api/triage", tags=["AI Triage"])


@router.post("/predict")
def predict(
    payload: BugCreate,
    db: Database = Depends(get_db),
    engine: NlpEngine = Depends(get_engine),
    _: dict = Depends(current_user),
) -> dict:
    """Predict without saving. Useful for previews and external integrations."""
    if not engine.models:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Classifiers are not trained. Run: python -m scripts.train",
        )
    fields = payload.model_dump(mode="json")
    document = engine.document_for(fields)
    prediction = service.predict(db, engine, document, engine.embed_document(document), fields.get("component"))
    return {**prediction, "engine": engine.status}


def _triage_view(db: Database, bug: dict) -> dict:
    names = developer_names(db)
    return {
        "bug_id": bug["bug_id"],
        "title": bug["title"],
        "description": bug.get("description"),
        "status": bug.get("status"),
        "reporter_name": bug.get("reporter_name"),
        "created_at": bug.get("created_at"),
        "triage_status": bug.get("triage_status"),
        "triage_decision": bug.get("triage_decision"),
        "current": {
            "component": bug.get("component"),
            "priority": bug.get("priority"),
            "severity": bug.get("severity"),
            "assigned_developer": bug.get("assigned_developer"),
            "assigned_developer_name": names.get(bug.get("assigned_developer")),
        },
        "reported": {"component": bug.get("reported_component"), "severity": bug.get("reported_severity")},
        "predictions": bug.get("prediction_details") or {},
    }


@router.get("/{bug_id}")
def get_triage(bug_id: str, db: Database = Depends(get_db), _: dict = Depends(current_user)) -> dict:
    return _triage_view(db, bug_service.get_bug_or_404(db, bug_id))


@router.post("/{bug_id}/decision")
def decide(
    bug_id: str,
    payload: TriageDecision,
    db: Database = Depends(get_db),
    user: dict = Depends(require_roles("Admin")),
) -> dict:
    """An administrator approves or edits the AI recommendation."""
    return _triage_view(db, service.decide(db, bug_id, payload, user))
