from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.database import Database

from nlp.pipeline import NlpEngine

from .database import USERS, get_database
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Database:
    return get_database()


def get_engine(request: Request) -> NlpEngine:
    return request.app.state.nlp


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Database = Depends(get_db),
) -> dict:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise unauthorized from None
    # Loaded on every request so role changes and resets apply immediately.
    user = db[USERS].find_one({"user_id": payload.get("sub")}, {"_id": 0})
    if user is None or user.get("token_version", 0) != payload.get("ver"):
        raise unauthorized
    return user


def require_roles(*roles: str):
    def checker(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This action needs one of these roles: {', '.join(roles)}.")
        return user
    return checker
