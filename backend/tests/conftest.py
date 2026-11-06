"""Tests use the real NLP engine and a real MongoDB, in a dedicated test database."""
from __future__ import annotations

import os

os.environ["MONGODB_DB"] = "bugsense_ai_test"
os.environ["ENVIRONMENT"] = "test"

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.database import get_database
from app.main import app
from nlp.pipeline import MODEL_FILE
from scripts.seed import seed
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


@pytest.fixture
def make_bug(client):
    def create(title="Export button throws an error when the table is empty", **fields):
        body = {
            "title": title,
            "description": fields.pop("description", "Clicking export on an empty table shows a raw error page."),
            **fields,
        }
        response = client.post("/api/bugs", json=body)
        assert response.status_code == 201, response.text
        return response.json()
    return create
