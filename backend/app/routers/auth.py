from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..config import get_settings
from ..database import USERS, next_id
from ..deps import current_user, get_db
from ..schemas import ForgotPasswordRequest, LoginRequest, RegisterRequest, ResetPasswordRequest
from ..security import create_access_token, hash_password, hash_reset_token, new_reset_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

MAX_FAILED_LOGINS = 8
FAILED_LOGIN_WINDOW_SECONDS = 300
_failed_logins: dict[str, deque[float]] = defaultdict(deque)
_failed_lock = threading.Lock()


def public_user(user: dict) -> dict:
    return {key: user.get(key) for key in ("user_id", "name", "email", "role", "created_at")}


def _recent_failures(email: str) -> int:
    with _failed_lock:
        attempts = _failed_logins[email]
        cutoff = time.monotonic() - FAILED_LOGIN_WINDOW_SECONDS
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if not attempts:
            _failed_logins.pop(email, None)
            return 0
        return len(attempts)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Database = Depends(get_db)) -> dict:
    """Public sign-up always creates a Reporter. Administrators grant other roles."""
    user = {
        "user_id": next_id(db, "USR"),
        "name": payload.name.strip(),
        "email": payload.email.lower(),
        "password_hash": hash_password(payload.password),
        "role": "Reporter",
        "token_version": 0,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        db[USERS].insert_one(user)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.") from None
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": public_user(user)}


@router.post("/login")
def login(payload: LoginRequest, db: Database = Depends(get_db)) -> dict:
    email = payload.email.lower()
    if _recent_failures(email) >= MAX_FAILED_LOGINS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again in a few minutes.")
    user = db[USERS].find_one({"email": email}, {"_id": 0})
    if not verify_password(payload.password, user.get("password_hash") if user else None):
        with _failed_lock:
            _failed_logins[email].append(time.monotonic())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")
    with _failed_lock:
        _failed_logins.pop(email, None)
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": public_user(user)}


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    return public_user(user)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Database = Depends(get_db)) -> dict:
    """The same message is returned either way, so this cannot be used to probe for accounts."""
    settings = get_settings()
    response = {"message": "If that email has an account, a reset link is on its way."}
    user = db[USERS].find_one({"email": payload.email.lower()}, {"user_id": 1})
    token = None
    if user:
        token, token_hash = new_reset_token()
        db[USERS].update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "reset_token_hash": token_hash,
                "reset_token_expires": datetime.now(timezone.utc) + timedelta(hours=1),
            }},
        )
    if settings.reset_token_visible:
        # Mail delivery is not configured, so development mode returns the token directly.
        # That does reveal whether an email exists, which is why production never does it.
        response["development_reset_token"] = token
    return response


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Database = Depends(get_db)) -> dict:
    token_hash = hash_reset_token(payload.token)
    user = db[USERS].find_one({
        "reset_token_hash": token_hash,
        "reset_token_expires": {"$gt": datetime.now(timezone.utc)},
    }, {"user_id": 1})
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired. Request a new one.")
    db[USERS].update_one(
        {"user_id": user["user_id"]},
        {
            "$set": {"password_hash": hash_password(payload.password)},
            "$unset": {"reset_token_hash": "", "reset_token_expires": ""},
            "$inc": {"token_version": 1},
        },
    )
    return {"message": "Password updated. Sign in with your new password."}
