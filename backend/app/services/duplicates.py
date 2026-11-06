"""Duplicate search and review. Scoring itself lives in the nlp package."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from fastapi import HTTPException, status
from pymongo.database import Database

from nlp.pipeline import Candidate, NlpEngine

from ..database import BUGS, MATCHES, next_id
from .developers import developer_names


def display_text(bug: dict) -> str:
    """The readable text shown and aligned in the comparison view."""
    parts = []
    for field in ("title", "description", "actual_behavior"):
        value = (bug.get(field) or "").strip()
        if value:
            parts.append(value if value[-1] in ".!?" else f"{value}.")
    return "\n".join(parts)


def load_candidates(db: Database, exclude: str | None = None) -> list[Candidate]:
    """Existing reports to match against.

    Confirmed duplicates are left out so results point at the original report.
    """
    query: dict = {"status": {"$ne": "Duplicate"}}
    if exclude:
        query["bug_id"] = {"$ne": exclude}
    candidates = []
    for bug in db[BUGS].find(query, {"bug_id": 1, "document": 1, "embedding": 1}):
        vector = bug.get("embedding")
        candidates.append(Candidate(
            bug_id=bug["bug_id"],
            document=bug.get("document", ""),
            embedding=None if not vector else np.asarray(vector, dtype=np.float32),
        ))
    return candidates


def _bug_summary(bug: dict, names: dict[str, str]) -> dict:
    return {
        "bug_id": bug["bug_id"],
        "title": bug["title"],
        "description": bug.get("description", ""),
        "status": bug.get("status"),
        "priority": bug.get("priority"),
        "component": bug.get("component"),
        "assigned_developer": bug.get("assigned_developer"),
        "assigned_developer_name": names.get(bug.get("assigned_developer")),
        "created_at": bug.get("created_at"),
    }


def enrich_matches(db: Database, engine: NlpEngine, source_text: str, matches: list[dict]) -> list[dict]:
    """Attach bug details and the sentence-level explanation to scored matches."""
    ids = [m.get("matched_bug_id") or m["bug_id"] for m in matches]
    bugs = {b["bug_id"]: b for b in db[BUGS].find({"bug_id": {"$in": ids}}, {"_id": 0, "embedding": 0, "document": 0})}
    names = developer_names(db)
    enriched = []
    for match, bug_id in zip(matches, ids):
        bug = bugs.get(bug_id)
        if bug is None:
            continue
        enriched.append({
            **match,
            "matched_bug_id": bug_id,
            "bug": _bug_summary(bug, names),
            "comparison": engine.compare(source_text, display_text(bug)),
        })
    return enriched


def search_text(db: Database, engine: NlpEngine, text: str) -> dict:
    """Search without saving anything."""
    document = engine.document_for({"title": text})
    embedding = engine.embed_document(document)
    matches = engine.find_duplicates(document, embedding, load_candidates(db))
    return {"query": text, "engine": engine.status, "matches": enrich_matches(db, engine, text, matches)}


def run_check(db: Database, engine: NlpEngine, bug: dict) -> list[dict]:
    """Score a saved bug and store its top matches.

    Decisions a person already made are kept. Only unreviewed matches are replaced.
    """
    vector = bug.get("embedding")
    embedding = None if not vector else np.asarray(vector, dtype=np.float32)
    if embedding is None:
        embedding = engine.embed_document(bug.get("document", ""))
    scored = engine.find_duplicates(bug.get("document", ""), embedding, load_candidates(db, exclude=bug["bug_id"]))
    return save_matches(db, engine, bug["bug_id"], scored)


def save_matches(db: Database, engine: NlpEngine, bug_id: str, scored: list[dict], seeded: bool = False) -> list[dict]:
    now = datetime.now(timezone.utc)
    db[MATCHES].delete_many({"bug_id": bug_id, "user_confirmed": None})
    reviewed = {m["matched_bug_id"] for m in db[MATCHES].find({"bug_id": bug_id}, {"matched_bug_id": 1})}
    engine_name = engine.status["semantic_engine"]
    for match in scored:
        if match["bug_id"] in reviewed:
            continue
        db[MATCHES].insert_one({
            "match_id": next_id(db, "MATCH"),
            "bug_id": bug_id,
            "matched_bug_id": match["bug_id"],
            "similarity_score": match["similarity_score"],
            "bert_score": match["bert_score"],
            "tfidf_score": match["tfidf_score"],
            "duplicate_probability": match["duplicate_probability"],
            "match_strength": match["match_strength"],
            "recommended_action": match["recommended_action"],
            "engine": engine_name,
            "user_confirmed": None,
            "seeded": seeded,
            "created_at": now,
        })
    return get_matches(db, bug_id)


def get_matches(db: Database, bug_id: str) -> list[dict]:
    cursor = db[MATCHES].find({"bug_id": bug_id}, {"_id": 0}).sort("similarity_score", -1)
    return list(cursor.limit(5))


def _get_bug(db: Database, bug_id: str) -> dict:
    bug = db[BUGS].find_one({"bug_id": bug_id}, {"_id": 0, "embedding": 0, "document": 0})
    if bug is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Bug {bug_id} was not found.")
    return bug


def confirm_duplicate(db: Database, bug_id: str, target_id: str, user: dict) -> dict:
    """Record a person's decision that ``bug_id`` duplicates ``target_id``."""
    if bug_id == target_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A report cannot be a duplicate of itself.")
    _get_bug(db, bug_id)
    target = _get_bug(db, target_id)

    # Always link to the original report, so chains cannot form.
    root_id = target.get("duplicate_of") or target_id
    if root_id == bug_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{target_id} is already a duplicate of {bug_id}.")

    now = datetime.now(timezone.utc)
    db[BUGS].update_one(
        {"bug_id": bug_id},
        {"$set": {"status": "Duplicate", "duplicate_of": root_id, "duplicate_review": "duplicate", "updated_at": now}},
    )
    # Reports that pointed here now point at the new original.
    db[BUGS].update_many({"duplicate_of": bug_id}, {"$set": {"duplicate_of": root_id, "updated_at": now}})
    decision = {"confirmed_by": user["user_id"], "confirmed_at": now}
    db[MATCHES].update_one(
        {"bug_id": bug_id, "matched_bug_id": target_id},
        {
            "$set": {"user_confirmed": True, **decision},
            "$setOnInsert": {
                "match_id": next_id(db, "MATCH"), "similarity_score": None, "seeded": False, "created_at": now,
            },
        },
        upsert=True,
    )
    return _get_bug(db, bug_id)


def confirm_unique(db: Database, bug_id: str, user: dict) -> dict:
    """Record that a report is unique. Reopens it if it was marked as a duplicate."""
    bug = _get_bug(db, bug_id)
    now = datetime.now(timezone.utc)
    updates = {"duplicate_review": "unique", "duplicate_of": None, "updated_at": now}
    if bug.get("status") == "Duplicate":
        updates["status"] = "Open"
    db[BUGS].update_one({"bug_id": bug_id}, {"$set": updates})
    db[MATCHES].update_many(
        {"bug_id": bug_id},
        {"$set": {"user_confirmed": False, "confirmed_by": user["user_id"], "confirmed_at": now}},
    )
    return _get_bug(db, bug_id)
