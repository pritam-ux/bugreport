from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..database import BUGS, DEVELOPERS, next_id
from ..deps import current_user, get_db, require_roles
from ..schemas import DeveloperCreate
from ..services.developers import list_developers, public_developer

router = APIRouter(prefix="/api/developers", tags=["Developers"])


@router.get("")
def get_developers(db: Database = Depends(get_db), _: dict = Depends(current_user)) -> list[dict]:
    return list_developers(db)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_developer(
    payload: DeveloperCreate, db: Database = Depends(get_db), _: dict = Depends(require_roles("Admin"))
) -> dict:
    developer = {
        "developer_id": next_id(db, "DEV", start=100),
        "name": payload.name.strip(),
        "email": payload.email.lower(),
        "skills": [skill.strip() for skill in payload.skills if skill.strip()],
        "assigned_components": [c.value for c in payload.assigned_components],
        "assigned_bugs": 0,
        "open_bugs": 0,
        "resolved_bugs": 0,
        "average_resolution_time": None,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        db[DEVELOPERS].insert_one(developer)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A developer with this email already exists.") from None
    developer.pop("_id", None)
    return public_developer(developer)


@router.get("/{developer_id}")
def get_developer(developer_id: str, db: Database = Depends(get_db), _: dict = Depends(current_user)) -> dict:
    developer = db[DEVELOPERS].find_one({"developer_id": developer_id}, {"_id": 0})
    if developer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Developer {developer_id} was not found.")
    by_component: dict[str, int] = {}
    for bug in db[BUGS].find(
        {"assigned_developer": developer_id, "status": {"$in": ["Resolved", "Closed"]}}, {"component": 1}
    ):
        by_component[bug["component"]] = by_component.get(bug["component"], 0) + 1
    active = list(
        db[BUGS].find(
            {"assigned_developer": developer_id, "status": {"$in": ["New", "Open", "In Progress"]}},
            {"_id": 0, "bug_id": 1, "title": 1, "priority": 1, "status": 1, "created_at": 1},
        ).sort("priority_rank", 1)
    )
    return {**public_developer(developer), "resolved_by_component": by_component, "active_bugs": active}
