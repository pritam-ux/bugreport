"""Bug report lifecycle. The submission pipeline from the brief lives in ``create_bug``."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from gridfs import GridFSBucket
from gridfs.errors import NoFile
from pymongo.database import Database

from nlp.pipeline import NlpEngine

from ..config import get_settings
from ..database import ATTACHMENTS, BUGS, DEVELOPERS, MATCHES, next_id
from ..schemas import PRIORITY_RANK, BugCreate, BugStatus, BugUpdate
from . import duplicates as duplicate_service
from . import triage as triage_service
from .developers import developer_names, sync_developer_stats

HIDDEN_FIELDS = {"_id": 0, "embedding": 0, "document": 0}
TEXT_FIELDS = {"title", "description", "steps_to_reproduce", "expected_behavior", "actual_behavior", "stack_trace"}
ALLOWED_SORTS = {
    "date_desc": [("created_at", -1)],
    "date_asc": [("created_at", 1)],
    "priority": [("priority_rank", 1), ("created_at", -1)],
}

# Extension -> leading bytes. Text logs have no signature, and every download is forced
# to save rather than render, so a mislabelled file cannot run in the app's origin.
ATTACHMENT_TYPES = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
    ".pdf": (b"%PDF-",),
    ".txt": (),
    ".log": (),
}


def public_bug(bug: dict, names: dict[str, str]) -> dict:
    return {
        **bug,
        "assigned_developer_name": names.get(bug.get("assigned_developer")),
        "recommended_developer_name": names.get(bug.get("recommended_developer")),
    }


def get_bug_or_404(db: Database, bug_id: str) -> dict:
    bug = db[BUGS].find_one({"bug_id": bug_id}, HIDDEN_FIELDS)
    if bug is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Bug {bug_id} was not found.")
    return bug


def create_bug(
    db: Database,
    engine: NlpEngine,
    payload: BugCreate,
    user: dict,
    source: str = "web",
    external_id: str | None = None,
) -> dict:
    """Validated report -> clean text -> TF-IDF and BERT -> top 5 matches ->
    predictions -> developer recommendation -> saved report.

    Predictions are saved beside the report and stay pending until a person
    reviews them. ``source`` and ``external_id`` let tracker imports reuse this path.
    """
    fields = payload.model_dump(mode="json")
    document = engine.document_for(fields)
    embedding = engine.embed_document(document)

    candidates = duplicate_service.load_candidates(db)
    scored = engine.find_duplicates(document, embedding, candidates)
    prediction = triage_service.predict(db, engine, document, embedding, fields.get("component"))

    def predicted(name: str) -> str | None:
        return (prediction.get(name) or {}).get("label")

    recommended = prediction["recommended_developers"]
    component = fields.get("component") or predicted("component") or "Backend"
    priority = predicted("priority") or "Medium"
    severity = fields.get("severity") or predicted("severity") or "Minor"
    now = datetime.now(timezone.utc)
    bug = {
        **fields,
        "bug_id": next_id(db, "BUG"),
        "component": component,
        "predicted_component": predicted("component"),
        "priority": priority,
        "priority_rank": PRIORITY_RANK[priority],
        "predicted_priority": predicted("priority"),
        "severity": severity,
        "predicted_severity": predicted("severity"),
        "reported_component": fields.get("component"),
        "reported_severity": fields.get("severity"),
        "assigned_developer": None,
        "recommended_developer": recommended[0]["developer_id"] if recommended else None,
        "prediction_details": prediction,
        "triage_status": "pending" if prediction["component"] else "unavailable",
        "duplicate_review": "pending" if scored else "not_needed",
        "status": BugStatus.new.value,
        "embedding": None if embedding is None else [float(x) for x in embedding],
        "embedding_model": engine.status["semantic_engine"] if embedding is not None else None,
        "document": document,
        "duplicate_of": None,
        "attachments": [],
        "reporter_id": user["user_id"],
        "reporter_name": user["name"],
        "source": source,
        "external_id": external_id,
        "seeded": False,
        "created_at": now,
        "updated_at": now,
        "resolved_at": None,
    }
    db[BUGS].insert_one(bug)
    bug.pop("_id", None)
    duplicate_service.save_matches(db, engine, bug["bug_id"], scored)
    return get_bug_or_404(db, bug["bug_id"])


def list_bugs(
    db: Database,
    search: str | None,
    priority: str | None,
    severity: str | None,
    component: str | None,
    status_filter: str | None,
    developer: str | None,
    triage_status: str | None,
    duplicate_review: str | None,
    sort: str,
    page: int,
    page_size: int,
) -> dict:
    query: dict = {}
    for field, value in (
        ("priority", priority), ("severity", severity), ("component", component),
        ("status", status_filter), ("assigned_developer", developer), ("triage_status", triage_status), ("duplicate_review", duplicate_review),
    ):
        if value:
            query[field] = value
    if search:
        pattern = re.escape(search.strip())
        query["$or"] = [
            {"bug_id": {"$regex": pattern, "$options": "i"}},
            {"title": {"$regex": pattern, "$options": "i"}},
        ]
    total = db[BUGS].count_documents(query)
    projection = {
        **HIDDEN_FIELDS, "prediction_details": 0, "steps_to_reproduce": 0, "stack_trace": 0,
        "expected_behavior": 0, "actual_behavior": 0,
    }
    cursor = (
        db[BUGS].find(query, projection)
        .sort(ALLOWED_SORTS.get(sort, ALLOWED_SORTS["date_desc"]))
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    names = developer_names(db)
    return {
        "items": [public_bug(b, names) for b in cursor],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def update_bug(db: Database, engine: NlpEngine, bug_id: str, payload: BugUpdate) -> dict:
    bug = get_bug_or_404(db, bug_id)
    changes = payload.model_dump(mode="json", exclude_unset=True)
    if not changes:
        return bug

    now = datetime.now(timezone.utc)
    new_status = changes.get("status")
    if new_status == "Duplicate" and bug.get("status") != "Duplicate":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Mark duplicates from the duplicate review, so the original report is recorded.",
        )
    if new_status and new_status != bug.get("status"):
        if new_status in ("Resolved", "Closed"):
            changes["resolved_at"] = bug.get("resolved_at") or now
        else:
            changes["resolved_at"] = None
        if bug.get("status") == "Duplicate":
            changes["duplicate_of"] = None
    if "priority" in changes:
        if changes["priority"] is None:
            changes.pop("priority")
        else:
            changes["priority_rank"] = PRIORITY_RANK[changes["priority"]]
    developer = changes.get("assigned_developer")
    if developer and not db[DEVELOPERS].find_one({"developer_id": developer}, {"_id": 1}):
        raise HTTPException(422, f"Developer {developer} was not found.")

    # Text edits change what the report means, so its vectors must follow.
    if TEXT_FIELDS & set(changes):
        merged = {**bug, **changes}
        document = engine.document_for(merged)
        embedding = engine.embed_document(document)
        changes["document"] = document
        changes["embedding"] = None if embedding is None else [float(x) for x in embedding]

    changes["updated_at"] = now
    db[BUGS].update_one({"bug_id": bug_id}, {"$set": changes})
    sync_developer_stats(db)
    return get_bug_or_404(db, bug_id)


def delete_bug(db: Database, bug_id: str) -> None:
    bug = get_bug_or_404(db, bug_id)
    now = datetime.now(timezone.utc)
    # Reports that pointed at this one have no original any more: reopen them.
    db[BUGS].update_many(
        {"duplicate_of": bug_id},
        {"$set": {"duplicate_of": None, "status": "Open", "duplicate_review": "pending", "updated_at": now}},
    )
    db[MATCHES].delete_many({"$or": [{"bug_id": bug_id}, {"matched_bug_id": bug_id}]})
    db[BUGS].delete_one({"bug_id": bug_id})
    for attachment in bug.get("attachments", []):
        try:
            _attachments(db).delete(attachment["attachment_id"])
        except NoFile:
            pass
    sync_developer_stats(db)


def _attachments(db: Database) -> GridFSBucket:
    return GridFSBucket(db, bucket_name=ATTACHMENTS)


def add_attachment(db: Database, bug_id: str, upload: UploadFile) -> dict:
    get_bug_or_404(db, bug_id)
    settings = get_settings()
    original_name = Path(upload.filename or "attachment").name[:150]
    extension = Path(original_name).suffix.lower()
    if extension not in ATTACHMENT_TYPES:
        allowed = ", ".join(sorted(e.lstrip(".") for e in ATTACHMENT_TYPES))
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Upload one of these file types: {allowed}.")

    limit = settings.max_upload_mb * 1024 * 1024
    content = upload.file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"Files can be up to {settings.max_upload_mb} MB.")
    if not content:
        raise HTTPException(422, "The file is empty.")
    signatures = ATTACHMENT_TYPES[extension]
    if signatures and not content.startswith(signatures):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"This file's contents do not match {extension}.")

    attachment_id = uuid.uuid4().hex
    _attachments(db).upload_from_stream_with_id(
        attachment_id, original_name, content, metadata={"bug_id": bug_id}
    )
    attachment = {
        "attachment_id": attachment_id,
        "filename": original_name,
        "extension": extension,
        "size": len(content),
        "uploaded_at": datetime.now(timezone.utc),
    }
    db[BUGS].update_one({"bug_id": bug_id}, {"$push": {"attachments": attachment}})
    return attachment


def read_attachment(db: Database, bug_id: str, attachment_id: str) -> tuple[bytes, str]:
    """Return ``(content, filename)``. The id must be listed on this bug, not just exist."""
    bug = get_bug_or_404(db, bug_id)
    for attachment in bug.get("attachments", []):
        if attachment["attachment_id"] == attachment_id:
            try:
                return _attachments(db).open_download_stream(attachment_id).read(), attachment["filename"]
            except NoFile:
                break
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found.")
