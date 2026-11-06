from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from ..database import USERS
from ..deps import get_db, require_roles
from ..schemas import RoleUpdate
from .auth import public_user

router = APIRouter(prefix="/api/users", tags=["Users"], dependencies=[Depends(require_roles("Admin"))])


@router.get("")
def list_users(db: Database = Depends(get_db)) -> list[dict]:
    return [public_user(u) for u in db[USERS].find({}, {"_id": 0}).sort("name", 1)]


@router.put("/{user_id}/role")
def update_role(user_id: str, payload: RoleUpdate, db: Database = Depends(get_db)) -> dict:
    user = db[USERS].find_one({"user_id": user_id}, {"_id": 0})
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"User {user_id} was not found.")
    if user["role"] == "Admin" and payload.role.value != "Admin" and db[USERS].count_documents({"role": "Admin"}) == 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Add another administrator before changing this role.")
    db[USERS].update_one({"user_id": user_id}, {"$set": {"role": payload.role.value}})
    return public_user({**user, "role": payload.role.value})
