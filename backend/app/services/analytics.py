"""Dashboard and analytics numbers, always computed from stored records and training metrics."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

import numpy as np
from pymongo.database import Database

from nlp.pipeline import NlpEngine

from ..database import BUGS, MATCHES
from ..schemas import Component, Priority, Severity
from .developers import OPEN_STATUSES, developer_names, list_developers, resolution_days

_SUMMARY_FIELDS = {
    "_id": 0, "bug_id": 1, "title": 1, "status": 1, "priority": 1, "severity": 1, "component": 1,
    "assigned_developer": 1, "created_at": 1, "resolved_at": 1,
}


def _counts(bugs: list[dict], field: str, order: list[str]) -> list[dict]:
    counter = Counter(b.get(field) for b in bugs)
    return [{"name": name, "count": counter.get(name, 0)} for name in order]


def _weekly(bugs: list[dict], now: datetime, weeks: int = 12) -> list[dict]:
    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    starts = [start_of_week - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    counts = dict.fromkeys(starts, 0)
    resolved = dict.fromkeys(starts, 0)
    for bug in bugs:
        for field, target in (("created_at", counts), ("resolved_at", resolved)):
            value = bug.get(field)
            if value:
                week = (value - timedelta(days=value.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                if week in target:
                    target[week] += 1
    return [{"period": s.strftime("%b %d"), "submitted": counts[s], "resolved": resolved[s]} for s in starts]


def _monthly(bugs: list[dict], now: datetime, months: int = 6) -> list[dict]:
    keys = []
    year, month = now.year, now.month
    for _ in range(months):
        keys.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    keys.reverse()
    counts = dict.fromkeys(keys, 0)
    resolved = dict.fromkeys(keys, 0)
    for bug in bugs:
        for field, target in (("created_at", counts), ("resolved_at", resolved)):
            value = bug.get(field)
            if value and (value.year, value.month) in target:
                target[(value.year, value.month)] += 1
    return [
        {"period": datetime(y, m, 1).strftime("%b %Y"), "submitted": counts[(y, m)], "resolved": resolved[(y, m)]}
        for y, m in keys
    ]


def _resolution_stats(bugs: list[dict]) -> dict:
    days = [(b, resolution_days(b)) for b in bugs]
    days = [(b, d) for b, d in days if d is not None]
    values = [d for _, d in days]
    by_priority = []
    for priority in [p.value for p in Priority]:
        subset = [d for b, d in days if b.get("priority") == priority]
        by_priority.append({
            "name": priority,
            "average_days": round(float(np.mean(subset)), 1) if subset else None,
            "resolved": len(subset),
        })
    buckets = [("Under 1 day", 0, 1), ("1-3 days", 1, 3), ("3-7 days", 3, 7), ("1-2 weeks", 7, 14), ("Over 2 weeks", 14, 10**6)]
    return {
        "average_days": round(float(np.mean(values)), 1) if values else None,
        "median_days": round(float(np.median(values)), 1) if values else None,
        "resolved_total": len(values),
        "by_priority": by_priority,
        "distribution": [
            {"name": name, "count": sum(1 for v in values if low <= v < high)} for name, low, high in buckets
        ],
    }


def dashboard(db: Database) -> dict:
    now = datetime.now(timezone.utc)
    bugs = list(db[BUGS].find({}, _SUMMARY_FIELDS))
    active = [b for b in bugs if b.get("status") != "Duplicate"]
    open_bugs = [b for b in bugs if b.get("status") in OPEN_STATUSES]
    resolution = _resolution_stats(active)
    names = developer_names(db)
    recent = sorted(bugs, key=lambda b: b["created_at"], reverse=True)[:8]
    return {
        "totals": {
            "total": len(bugs),
            "open": len(open_bugs),
            "resolved": sum(1 for b in bugs if b.get("status") in ("Resolved", "Closed")),
            "duplicates": sum(1 for b in bugs if b.get("status") == "Duplicate"),
            "high_priority": sum(1 for b in open_bugs if b.get("priority") in ("Critical", "High")),
            "average_resolution_days": resolution["average_days"],
            "pending_triage": db[BUGS].count_documents({"triage_status": "pending"}),
        },
        "by_priority": _counts(active, "priority", [p.value for p in Priority]),
        "by_component": sorted(
            _counts(active, "component", [c.value for c in Component]), key=lambda x: -x["count"]
        ),
        "by_severity": _counts(active, "severity", [s.value for s in Severity]),
        "by_status": _counts(bugs, "status", ["New", "Open", "In Progress", "Resolved", "Closed", "Duplicate"]),
        "weekly_trend": _weekly(bugs, now),
        "monthly_trend": _monthly(bugs, now),
        "developer_workload": [
            {"name": d["name"], "developer_id": d["developer_id"], "open": d.get("open_bugs", 0),
             "resolved": d.get("resolved_bugs", 0), "average_days": d.get("average_resolution_time")}
            for d in sorted(list_developers(db), key=lambda d: -d.get("open_bugs", 0))
        ],
        "resolution": resolution,
        "recent": [{**b, "assigned_developer_name": names.get(b.get("assigned_developer"))} for b in recent],
    }


def duplicate_stats(db: Database, engine: NlpEngine) -> dict:
    """Offline quality from training, and live review results from real users.

    Seeded sample matches are excluded from live results, because no person reviewed them.
    """
    live = list(db[MATCHES].find({"seeded": {"$ne": True}}, {"_id": 0, "user_confirmed": 1, "match_strength": 1}))
    reviewed = [m for m in live if m.get("user_confirmed") is not None]
    confirmed = sum(1 for m in reviewed if m["user_confirmed"] is True)

    by_strength = []
    for strength in ("Strong", "Possible", "Weak"):
        subset = [m for m in reviewed if m.get("match_strength") == strength]
        by_strength.append({
            "name": strength,
            "reviewed": len(subset),
            "confirmed": sum(1 for m in subset if m["user_confirmed"] is True),
        })

    return {
        "stored": {
            "duplicates_linked": db[BUGS].count_documents({"status": "Duplicate"}),
            "matches_scored": db[MATCHES].count_documents({}),
            "awaiting_review": db[BUGS].count_documents({"duplicate_review": "pending"}),
            "confirmed_unique": db[BUGS].count_documents({"duplicate_review": "unique"}),
        },
        "live_reviews": {
            "reviewed": len(reviewed),
            "confirmed": confirmed,
            "observed_precision": round(confirmed / len(reviewed), 3) if reviewed else None,
            "by_strength": by_strength,
        },
        "evaluation": engine.metrics.get("duplicates"),
        "calibrator": engine.metrics.get("calibrator"),
        "dataset": engine.metrics.get("dataset"),
        "trained_at": engine.metrics.get("trained_at"),
        "engine": engine.status,
    }


def triage_stats(db: Database, engine: NlpEngine) -> dict:
    """Cross-validated classifier quality, and how often administrators kept predictions."""
    decisions = list(db[BUGS].find(
        {"seeded": {"$ne": True}, "triage_status": {"$in": ["approved", "modified"]}},
        {"_id": 0, "triage_status": 1, "triage_decision.changed_fields": 1},
    ))
    changed = Counter(
        field for d in decisions for field in (d.get("triage_decision") or {}).get("changed_fields", [])
    )
    approved = sum(1 for d in decisions if d["triage_status"] == "approved")
    return {
        "classifiers": engine.metrics.get("classifiers"),
        "dataset": engine.metrics.get("dataset"),
        "trained_at": engine.metrics.get("trained_at"),
        "embedding_model": engine.metrics.get("embedding_model"),
        "live_decisions": {
            "reviewed": len(decisions),
            "approved_unchanged": approved,
            "acceptance_rate": round(approved / len(decisions), 3) if decisions else None,
            "changed_fields": [{"name": k, "count": v} for k, v in changed.most_common()],
        },
        "pending": db[BUGS].count_documents({"triage_status": "pending"}),
    }
