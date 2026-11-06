"""Tests use the real NLP engine and a real MongoDB, in a dedicated test database."""
from __future__ import annotations

import os

os.environ["MONGODB_DB"] = "bugsense_ai_test"
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ["ENVIRONMENT"] = "test"

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.database import get_database
from app.main import app
from nlp.pipeline import MODEL_FILE
from scripts.seed import DEMO_PASSWORD, seed
from scripts.train import train


@pytest.fixture(scope="session")
def client():
    settings = get_settings()
    assert settings.mongodb_db == "bugsense_ai_test"
    try:
        get_database().command("ping")
    except PyMongoError as exc:
        pytest.skip(f"MongoDB is not running: {exc}")
    if not (Path(settings.artifacts_dir) / MODEL_FILE).exists():
        train()
    seed(reset=True)
    with TestClient(app) as test_client:
        yield test_client
    get_database().client.drop_database(settings.mongodb_db)


def _login(client: TestClient, email: str) -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin@bugsense.dev")


@pytest.fixture(scope="session")
def developer(client):
    return _login(client, "developer@bugsense.dev")


@pytest.fixture(scope="session")
def reporter(client):
    return _login(client, "reporter@bugsense.dev")


@pytest.fixture
def new_reporter(client):
    """A fresh Reporter who owns nothing, for permission tests."""
    response = client.post("/api/auth/register", json={
        "name": "Test Person", "email": f"{uuid.uuid4().hex}@example.com", "password": "correct-horse-42",
    })
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def make_bug(client, reporter):
    def create(title="Export button throws an error when the table is empty", headers=None, **fields):
        body = {
            "title": title,
            "description": fields.pop("description", "Clicking export on an empty table shows a raw error page."),
            **fields,
        }
        response = client.post("/api/bugs", json=body, headers=headers or reporter)
        assert response.status_code == 201, response.text
        return response.json()
    return create
