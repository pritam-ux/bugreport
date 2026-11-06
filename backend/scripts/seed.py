"""Load sample users, developers and bug reports, processed by the real NLP pipeline.

Usage: python -m scripts.seed [--reset]

Sample history (dates, assignments, resolutions) is simulated from a fixed random seed.
Embeddings, duplicate scores and predictions all come from the models. Seeded records
are flagged so live analytics never count them as human decisions.
"""
from __future__ import annotations

import argparse
import random
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import get_settings
from app.database import BUGS, COUNTERS, DEVELOPERS, MATCHES, USERS, ensure_indexes, get_database
from app.schemas import PRIORITY_RANK
from app.security import hash_password
from app.services import duplicates as duplicate_service
from app.services import triage as triage_service
from app.services.developers import sync_developer_stats
from nlp.dataset import load_dataset
from nlp.pipeline import MODEL_FILE, Candidate, NlpEngine

DATASET = Path(__file__).resolve().parents[1] / "data" / "seed_bugs.psv"
DEMO_PASSWORD = "BugSense2026!"
HISTORY_DAYS = 175
# Duplicate reports this recent stay unreviewed, so the review pages have real work to show.
UNREVIEWED_DUPLICATE_GROUPS = {"G30", "G31", "G33", "G34"}

DEVELOPERS_SEED = [
    ("Aisha Rahman", "aisha.rahman@bugsense.dev", ["oauth", "saml", "jwt", "session management", "password security"], ["Authentication", "API"], 1.0),
    ("Marco Rossi", "marco.rossi@bugsense.dev", ["postgres", "mongodb", "query optimization", "replication", "migrations"], ["Database"], 1.4),
    ("Priya Nair", "priya.nair@bugsense.dev", ["rest api", "graphql", "webhooks", "rate limiting", "openapi"], ["API", "Backend"], 0.9),
    ("Daniel Kim", "daniel.kim@bugsense.dev", ["python", "java", "queues", "workers", "payments"], ["Backend"], 1.2),
    ("Sofia Alvarez", "sofia.alvarez@bugsense.dev", ["react", "redux", "javascript", "webpack", "browser"], ["Frontend"], 0.8),
    ("Liam Chen", "liam.chen@bugsense.dev", ["css", "accessibility", "responsive layout", "design systems"], ["UI", "Frontend"], 0.7),
    ("Fatima Noor", "fatima.noor@bugsense.dev", ["kubernetes", "docker", "terraform", "nginx", "ci pipelines"], ["Infrastructure"], 1.1),
    ("Ethan Brooks", "ethan.brooks@bugsense.dev", ["monitoring", "aws", "tls certificates", "deployment", "postgres"], ["Infrastructure", "Database"], 1.5),
]

USERS_SEED = [
    ("Morgan Lee", "admin@bugsense.dev", "Admin"),
    ("Sofia Alvarez", "developer@bugsense.dev", "Developer"),
    ("Jordan Blake", "reporter@bugsense.dev", "Reporter"),
]

# Typical days to fix, by priority, before each developer's pace is applied.
BASE_DAYS = {"Critical": 1.0, "High": 3.0, "Medium": 7.0, "Low": 12.0}


def choose_status(age_days: float, rng: random.Random) -> str:
    """Older reports are more likely to be finished, as in a real backlog."""
    finished = min(0.92, age_days / 50)
    if rng.random() < finished:
        return "Closed" if rng.random() < 0.35 else "Resolved"
    return rng.choice(["Open", "Open", "In Progress"])


def seed(reset: bool) -> None:
    settings = get_settings()
    if settings.environment == "production":
        sys.exit("Refusing to load sample data with demo passwords when ENVIRONMENT=production.")
    db = get_database()
    if db[BUGS].estimated_document_count() and not reset:
        sys.exit(f"Database '{settings.mongodb_db}' already has data. Run again with --reset to replace it.")
    if not (Path(settings.artifacts_dir) / MODEL_FILE).exists():
        sys.exit("Models are not trained. Run first: python -m scripts.train")

    for name in (USERS, BUGS, DEVELOPERS, MATCHES, COUNTERS):
        db[name].drop()
    shutil.rmtree(settings.upload_dir, ignore_errors=True)  # attachments belonged to the dropped reports
    ensure_indexes(db)

    rng = random.Random(20260)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    engine = NlpEngine.load(settings.embedding_model, settings.artifacts_dir)
    print(f"NLP status: {engine.status}")

    db[COUNTERS].insert_many([
        {"_id": "USR", "value": 1000 + len(USERS_SEED)},
        {"_id": "DEV", "value": 100 + len(DEVELOPERS_SEED)},
    ])
    password_hash = hash_password(DEMO_PASSWORD)
    db[USERS].insert_many([
        {"user_id": f"USR-{1001 + i}", "name": name, "email": email, "role": role,
         "password_hash": password_hash, "token_version": 0, "created_at": now - timedelta(days=HISTORY_DAYS)}
        for i, (name, email, role) in enumerate(USERS_SEED)
    ])
    db[DEVELOPERS].insert_many([
        {"developer_id": f"DEV-{101 + i}", "name": name, "email": email, "skills": skills,
         "assigned_components": components, "assigned_bugs": 0, "open_bugs": 0, "resolved_bugs": 0,
         "average_resolution_time": None, "created_at": now - timedelta(days=HISTORY_DAYS)}
        for i, (name, email, skills, components, _) in enumerate(DEVELOPERS_SEED)
    ])
    pace = {f"DEV-{101 + i}": row[4] for i, row in enumerate(DEVELOPERS_SEED)}
    owners: dict[str, list[str]] = {}
    for i, row in enumerate(DEVELOPERS_SEED):
        for component in row[3]:
            owners.setdefault(component, []).append(f"DEV-{101 + i}")

    records = load_dataset(DATASET)
    rng.shuffle(records)
    # Unreviewed groups are placed last so they read as this week's reports.
    records.sort(key=lambda r: r["group"] in UNREVIEWED_DUPLICATE_GROUPS)
    _keep_listed_report_first(records, load_dataset(DATASET))

    documents = [engine.document_for(r) for r in records]
    embeddings = engine.embed_many(documents)

    total = len(records)
    # A steady rise in reports, with some noise, and nothing dated in the future.
    ages = sorted(
        (HISTORY_DAYS * (1 - (i + rng.random()) / total) ** 1.3 for i in range(total)), reverse=True
    )

    first_in_group: dict[str, str] = {}
    candidates: list[Candidate] = []
    bugs = []
    for index, record in enumerate(records):
        bug_id = f"BUG-{1001 + index}"
        age = ages[index]
        created_at = now - timedelta(days=age, minutes=rng.randint(0, 600))
        group = record["group"]
        original = first_in_group.get(group)
        is_grouped = not group.startswith("single-")
        unreviewed = group in UNREVIEWED_DUPLICATE_GROUPS

        document = documents[index]
        vector = None if embeddings is None else embeddings[index]
        classes = engine.classify(document, vector)
        predicted = {name: classes[name]["label"] for name in ("component", "priority", "severity")}
        developer = rng.choice(owners[record["component"]])

        if original and not unreviewed:
            status = "Duplicate"
        elif unreviewed or age < 6:
            status = "New"
        else:
            status = choose_status(age, rng)

        resolved_at = None
        if status in ("Resolved", "Closed"):
            days = BASE_DAYS[record["priority"]] * pace[developer] * rng.lognormvariate(0, 0.55)
            resolved_at = min(created_at + timedelta(days=days), now)

        pending = status == "New"
        bug = {
            "bug_id": bug_id,
            "title": record["title"],
            "description": record["description"],
            "steps_to_reproduce": record["steps_to_reproduce"],
            "expected_behavior": record["expected_behavior"],
            "actual_behavior": record["actual_behavior"],
            "stack_trace": record["stack_trace"],
            "environment": {
                "os": rng.choice(["Windows 11", "macOS 15", "Ubuntu 24.04", "Android 15", "iOS 18"]),
                "browser": rng.choice(["Chrome 141", "Firefox 144", "Safari 18", "Edge 141"]),
                "app_version": f"3.{rng.randint(2, 9)}.{rng.randint(0, 14)}",
            },
            "component": predicted["component"] if pending else record["component"],
            "predicted_component": predicted["component"],
            "priority": predicted["priority"] if pending else record["priority"],
            "priority_rank": PRIORITY_RANK[predicted["priority"] if pending else record["priority"]],
            "predicted_priority": predicted["priority"],
            "severity": predicted["severity"] if pending else record["severity"],
            "predicted_severity": predicted["severity"],
            "reported_component": None,
            "reported_severity": None,
            "assigned_developer": None if pending or status == "Duplicate" else developer,
            "recommended_developer": None,
            "prediction_details": {
                "component": classes["component"], "priority": classes["priority"], "severity": classes["severity"],
                "recommended_developers": [],
            },
            "triage_status": "pending" if pending else "approved",
            "duplicate_review": "pending" if pending else ("duplicate" if status == "Duplicate" else "not_needed"),
            "status": status,
            "embedding": None if vector is None else [float(x) for x in vector],
            "embedding_model": None if vector is None else engine.status["semantic_engine"],
            "document": document,
            "duplicate_of": original if status == "Duplicate" else None,
            "attachments": [],
            "reporter_id": "USR-1003",
            "reporter_name": "Jordan Blake",
            "source": "seed",
            "external_id": None,
            "seeded": True,
            "created_at": created_at,
            "updated_at": resolved_at or created_at,
            "resolved_at": resolved_at,
        }
        bugs.append(bug)
        if is_grouped and original is None:
            first_in_group[group] = bug_id

    db[BUGS].insert_many(bugs)
    sync_developer_stats(db)

    # Real scores for reports that have review history or are waiting for review.
    profiles_ready = 0
    for bug in bugs:
        if bug["status"] not in ("Duplicate", "New"):
            continue
        earlier = [
            Candidate(other["bug_id"], other["document"], None if other["embedding"] is None else _vector(other))
            for other in bugs
            if other["created_at"] < bug["created_at"] and other["status"] != "Duplicate"
        ]
        vector = None if bug["embedding"] is None else _vector(bug)
        scored = engine.find_duplicates(bug["document"], vector, earlier)
        duplicate_service.save_matches(db, engine, bug["bug_id"], scored, seeded=True)
        if bug["status"] == "Duplicate":
            db[MATCHES].update_one(
                {"bug_id": bug["bug_id"], "matched_bug_id": bug["duplicate_of"]},
                {"$set": {"user_confirmed": True, "confirmed_by": "USR-1001", "confirmed_at": bug["created_at"]}},
            )
        else:
            prediction = triage_service.predict(db, engine, bug["document"], vector)
            recommended = prediction["recommended_developers"]
            db[BUGS].update_one(
                {"bug_id": bug["bug_id"]},
                {"$set": {
                    "prediction_details": prediction,
                    "recommended_developer": recommended[0]["developer_id"] if recommended else None,
                }},
            )
            profiles_ready += 1

    db[COUNTERS].update_one({"_id": "BUG"}, {"$set": {"value": 1000 + total}}, upsert=True)
    sync_developer_stats(db)

    print(f"Loaded {total} reports, {len(DEVELOPERS_SEED)} developers, {len(USERS_SEED)} users. "
          f"{profiles_ready} reports await triage.")
    print(f"Sign in with admin@bugsense.dev, developer@bugsense.dev or reporter@bugsense.dev. Password: {DEMO_PASSWORD}")


def _keep_listed_report_first(records: list[dict], listed: list[dict]) -> None:
    """In each duplicate group, make the report listed first in the file the original.

    Confirmed duplicates are not offered as matches, so this decides which wording
    stays searchable, including the sign-in example from the project brief.
    """
    order = {record["title"]: index for index, record in enumerate(listed)}
    positions: dict[str, list[int]] = {}
    for index, record in enumerate(records):
        positions.setdefault(record["group"], []).append(index)
    for indices in positions.values():
        members = sorted((records[i] for i in indices), key=lambda r: order[r["title"]])
        for index, record in zip(indices, members):
            records[index] = record


def _vector(bug: dict):
    import numpy as np
    return np.asarray(bug["embedding"], dtype=np.float32)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Delete this app's existing data first.")
    seed(parser.parse_args().reset)
