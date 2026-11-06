"""Developer records, their workload statistics and recommendation profiles."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import numpy as np
from pymongo.database import Database

from nlp.recommender import CAPACITY, DeveloperProfile

from ..database import BUGS, DEVELOPERS

OPEN_STATUSES = ("New", "Open", "In Progress")
DONE_STATUSES = ("Resolved", "Closed")
MAX_HISTORY_VECTORS = 200


def resolution_days(bug: dict) -> float | None:
    created: datetime | None = bug.get("created_at")
    resolved: datetime | None = bug.get("resolved_at")
    if not created or not resolved:
        return None
    return max((resolved - created).total_seconds() / 86400, 0.0)


def sync_developer_stats(db: Database) -> None:
    """Recompute the stored counters from bug reports, the single source of truth."""
    assigned: dict[str, int] = defaultdict(int)
    open_count: dict[str, int] = defaultdict(int)
    resolved: dict[str, int] = defaultdict(int)
    days: dict[str, list[float]] = defaultdict(list)
    projection = {"assigned_developer": 1, "status": 1, "created_at": 1, "resolved_at": 1}
    for bug in db[BUGS].find({"assigned_developer": {"$ne": None}}, projection):
        developer = bug["assigned_developer"]
        if bug["status"] == "Duplicate":
            continue
        assigned[developer] += 1
        if bug["status"] in OPEN_STATUSES:
            open_count[developer] += 1
        elif bug["status"] in DONE_STATUSES:
            resolved[developer] += 1
            value = resolution_days(bug)
            if value is not None:
                days[developer].append(value)

    for developer in db[DEVELOPERS].find({}, {"developer_id": 1}):
        developer_id = developer["developer_id"]
        values = days[developer_id]
        db[DEVELOPERS].update_one(
            {"developer_id": developer_id},
            {"$set": {
                "assigned_bugs": assigned[developer_id],
                "open_bugs": open_count[developer_id],
                "resolved_bugs": resolved[developer_id],
                "average_resolution_time": round(float(np.mean(values)), 1) if values else None,
            }},
        )


def public_developer(developer: dict) -> dict:
    open_bugs = developer.get("open_bugs", 0)
    return {
        **developer,
        "current_workload": open_bugs,
        "workload_percent": min(100, round(100 * open_bugs / CAPACITY)),
    }


def list_developers(db: Database) -> list[dict]:
    return [public_developer(d) for d in db[DEVELOPERS].find({}, {"_id": 0}).sort("name", 1)]


def developer_names(db: Database) -> dict[str, str]:
    return {d["developer_id"]: d["name"] for d in db[DEVELOPERS].find({}, {"developer_id": 1, "name": 1})}


def build_profiles(db: Database) -> list[DeveloperProfile]:
    """Assemble each developer's skills and bug history for the recommender."""
    profiles = {
        d["developer_id"]: DeveloperProfile(
            developer_id=d["developer_id"],
            name=d["name"],
            skills=d.get("skills", []),
            assigned_components=d.get("assigned_components", []),
            open_bugs=d.get("open_bugs", 0),
        )
        for d in db[DEVELOPERS].find({}, {"_id": 0})
    }
    days: dict[tuple[str, str], list[float]] = defaultdict(list)
    vectors: dict[str, list] = defaultdict(list)
    cursor = db[BUGS].find(
        {"status": {"$in": list(DONE_STATUSES)}, "assigned_developer": {"$in": list(profiles)}},
        {"bug_id": 1, "assigned_developer": 1, "component": 1, "created_at": 1, "resolved_at": 1, "embedding": 1},
    ).sort("resolved_at", -1)
    for bug in cursor:
        profile = profiles[bug["assigned_developer"]]
        component = bug.get("component")
        profile.resolved_by_component[component] = profile.resolved_by_component.get(component, 0) + 1
        value = resolution_days(bug)
        if value is not None:
            days[(profile.developer_id, component)].append(value)
        if bug.get("embedding") and len(vectors[profile.developer_id]) < MAX_HISTORY_VECTORS:
            vectors[profile.developer_id].append(bug["embedding"])
            profile.resolved_bug_ids.append(bug["bug_id"])

    for (developer_id, component), values in days.items():
        profiles[developer_id].avg_days_by_component[component] = float(np.mean(values))
    for developer_id, rows in vectors.items():
        profiles[developer_id].resolved_embeddings = np.asarray(rows, dtype=np.float32)
    return list(profiles.values())
