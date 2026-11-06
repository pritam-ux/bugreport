"""Runs classifiers and the recommender, and records administrator decisions."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from fastapi import HTTPException, status
from pymongo.database import Database

from nlp.pipeline import NlpEngine

from ..database import BUGS, DEVELOPERS
from ..schemas import PRIORITY_RANK, TriageDecision
from .developers import build_profiles, sync_developer_stats


def predict(
    db: Database,
    engine: NlpEngine,
    document: str,
    embedding: np.ndarray | None,
    component_override: str | None = None,
) -> dict:
    """Predictions plus ranked developers.

    The recommender uses the reporter's component when given. A person chose it, so
    it is more reliable than the prediction.
    """
    classes = engine.classify(document, embedding)
    component = component_override or (classes.get("component") or {}).get("label")
    recommendations = []
    if component:
        recommendations = engine.recommend_developers(document, component, embedding, build_profiles(db))
    return {
        "component": classes.get("component"),
        "priority": classes.get("priority"),
        "severity": classes.get("severity"),
        "recommended_developers": recommendations,
    }


def decide(db: Database, bug_id: str, decision: TriageDecision, user: dict) -> dict:
    """Apply an administrator's approved or edited triage."""
    bug = db[BUGS].find_one({"bug_id": bug_id}, {"_id": 0, "embedding": 0, "document": 0})
    if bug is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Bug {bug_id} was not found.")
    developer = decision.assigned_developer
    if developer and not db[DEVELOPERS].find_one({"developer_id": developer}, {"_id": 1}):
        raise HTTPException(422, f"Developer {developer} was not found.")

    predicted = {
        "component": bug.get("predicted_component"),
        "priority": bug.get("predicted_priority"),
        "severity": bug.get("predicted_severity"),
        "assigned_developer": bug.get("recommended_developer"),
    }
    chosen = {
        "component": decision.component.value,
        "priority": decision.priority.value,
        "severity": decision.severity.value,
        "assigned_developer": developer,
    }
    changed = [field for field, value in chosen.items() if value != predicted[field]]
    now = datetime.now(timezone.utc)
    updates = {
        **chosen,
        "priority_rank": PRIORITY_RANK[decision.priority.value],
        "triage_status": "modified" if changed else "approved",
        "triage_decision": {"by": user["user_id"], "at": now, "changed_fields": changed},
        "updated_at": now,
    }
    if bug.get("status") == "New":
        updates["status"] = "Open"
    db[BUGS].update_one({"bug_id": bug_id}, {"$set": updates})
    sync_developer_stats(db)
    return db[BUGS].find_one({"bug_id": bug_id}, {"_id": 0, "embedding": 0, "document": 0})
