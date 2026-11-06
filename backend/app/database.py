from __future__ import annotations

from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.database import Database

from .config import get_settings

USERS = "users"
BUGS = "bug_reports"
DEVELOPERS = "developers"
MATCHES = "duplicate_matches"
COUNTERS = "counters"


@lru_cache
def _client() -> MongoClient:
    return MongoClient(get_settings().mongodb_uri, serverSelectionTimeoutMS=3000, tz_aware=True)


def get_database() -> Database:
    return _client()[get_settings().mongodb_db]


def ensure_indexes(db: Database) -> None:
    db[USERS].create_index("user_id", unique=True)
    db[USERS].create_index("email", unique=True)
    db[BUGS].create_index("bug_id", unique=True)
    db[BUGS].create_index([("created_at", DESCENDING)])
    for field in ("status", "priority_rank", "component", "severity", "assigned_developer", "triage_status"):
        db[BUGS].create_index(field)
    db[DEVELOPERS].create_index("developer_id", unique=True)
    db[DEVELOPERS].create_index("email", unique=True)
    db[MATCHES].create_index("match_id", unique=True)
    db[MATCHES].create_index([("bug_id", ASCENDING), ("matched_bug_id", ASCENDING)], unique=True)
    db[MATCHES].create_index("matched_bug_id")


def next_id(db: Database, prefix: str, start: int = 1000) -> str:
    """Atomic sequence, safe across several API workers."""
    db[COUNTERS].update_one({"_id": prefix}, {"$setOnInsert": {"value": start}}, upsert=True)
    counter = db[COUNTERS].find_one_and_update(
        {"_id": prefix}, {"$inc": {"value": 1}}, return_document=ReturnDocument.AFTER
    )
    return f"{prefix}-{counter['value']}"
