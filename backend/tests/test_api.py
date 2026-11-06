import uuid

import pytest

from app.config import get_settings
from app.database import BUGS, MATCHES, get_database


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


# Submission pipeline


def test_submission_runs_and_stores_the_pipeline(client, make_bug):
    result = make_bug(
        title="Application crashes when I click the login button",
        description="The whole app closes as soon as the login button is clicked.",
        severity="Major",
    )
    bug = result["bug"]
    assert bug["bug_id"].startswith("BUG-") and bug["status"] == "New"
    assert bug["predicted_component"] and bug["predicted_priority"] and bug["recommended_developer"]
    assert bug["severity"] == "Major"
    assert bug["triage_status"] == "pending"
    assert bug["assigned_developer"] is None
    assert "embedding" not in bug and "document" not in bug

    stored = get_database()[BUGS].find_one({"bug_id": bug["bug_id"]})
    assert len(stored["embedding"]) == 384 and stored["document"]

    assert len(result["duplicates"]) == 5
    titles = [m["bug"]["title"] for m in result["duplicates"][:3]]
    assert any("sign-in" in t or "Login page crashes" in t for t in titles)
    scores = [m["similarity_score"] for m in result["duplicates"]]
    assert scores == sorted(scores, reverse=True) and len(set(scores)) > 1
    assert get_database()[MATCHES].count_documents({"bug_id": bug["bug_id"]}) == 5


@pytest.mark.parametrize("body", [
    {"title": "abc", "description": "long enough description here"},
    {"title": "A valid title", "description": "short"},
    {"title": "A valid title", "description": "long enough description here", "severity": "Catastrophic"},
    {"title": "A valid title", "description": "long enough description here", "component": "Nope"},
    {"title": "       ", "description": "long enough description here"},
])
def test_invalid_reports_are_rejected(client, body):
    assert client.post("/api/bugs", json=body).status_code == 422


def test_editing_text_updates_embedding(client, make_bug):
    bug_id = make_bug()["bug"]["bug_id"]
    before = get_database()[BUGS].find_one({"bug_id": bug_id})["embedding"]
    response = client.put(f"/api/bugs/{bug_id}", json={"title": "Payment worker charges customers twice"})
    assert response.status_code == 200
    assert get_database()[BUGS].find_one({"bug_id": bug_id})["embedding"] != before


# Listing


def test_filters_sort_and_pagination(client):
    page = client.get("/api/bugs", params={"priority": "High", "page_size": 5}).json()
    assert page["total"] > 5 and len(page["items"]) == 5
    assert all(b["priority"] == "High" for b in page["items"])

    ordered = client.get("/api/bugs", params={"sort": "priority", "page_size": 100}).json()["items"]
    ranks = [b["priority_rank"] for b in ordered]
    assert ranks == sorted(ranks)

    assert client.get("/api/bugs", params={"search": "BUG-1001"}).json()["items"][0]["bug_id"] == "BUG-1001"
    assert client.get("/api/bugs", params={"search": "deadlocks"}).json()["total"] >= 1


def test_search_treats_input_as_literal_text(client):
    assert client.get("/api/bugs", params={"search": ".*"}).json()["total"] == 0
    assert client.get("/api/bugs", params={"search": "(["}).status_code == 200


def test_operator_injection_in_filter_is_harmless(client):
    response = client.get("/api/bugs", params={"priority": '{"$ne": null}'})
    assert response.status_code == 200 and response.json()["total"] == 0


def test_unknown_bug_is_404(client):
    assert client.get("/api/bugs/BUG-0").status_code == 404


def test_status_changes_track_resolution(client, make_bug):
    bug_id = make_bug()["bug"]["bug_id"]
    resolved = client.put(f"/api/bugs/{bug_id}", json={"status": "Resolved"}).json()
    assert resolved["resolved_at"]
    reopened = client.put(f"/api/bugs/{bug_id}", json={"status": "Open"}).json()
    assert reopened["resolved_at"] is None


def test_assignment_updates_developer_counts(client, make_bug):
    bug_id = make_bug()["bug"]["bug_id"]
    before = client.get("/api/developers/DEV-101").json()["open_bugs"]
    client.put(f"/api/bugs/{bug_id}", json={"assigned_developer": "DEV-101", "status": "Open"})
    assert client.get("/api/developers/DEV-101").json()["open_bugs"] == before + 1
    missing = client.put(f"/api/bugs/{bug_id}", json={"assigned_developer": "DEV-999"})
    assert missing.status_code == 422


# Duplicate review


def test_search_does_not_save(client):
    before = get_database()[BUGS].count_documents({})
    response = client.post("/api/duplicates/search", json={"text": "Dark theme makes the invoice table unreadable"})
    assert response.status_code == 200
    data = response.json()
    assert "contrast" in data["matches"][0]["bug"]["title"] or "Dark mode" in data["matches"][0]["bug"]["title"]
    assert data["matches"][0]["comparison"]["source_sentences"]
    assert get_database()[BUGS].count_documents({}) == before


def test_nothing_becomes_a_duplicate_without_confirmation(make_bug):
    result = make_bug(
        title="Dark mode text unreadable on the billing table",
        description="Table cells keep dark text on the dark background when dark theme is enabled.",
    )
    assert result["duplicates"][0]["bug"]["title"] == "Dark mode text unreadable on the billing table"
    assert result["bug"]["status"] == "New" and result["bug"]["duplicate_of"] is None


def test_confirm_duplicate_then_unique(client, make_bug):
    a = make_bug()["bug"]["bug_id"]
    b = make_bug(title="Empty table export raises an error page")["bug"]["bug_id"]

    marked = client.post("/api/duplicates/confirm", json={"bug_id": b, "is_duplicate": True, "matched_bug_id": a})
    assert marked.status_code == 200
    assert marked.json()["status"] == "Duplicate" and marked.json()["duplicate_of"] == a
    assert get_database()[MATCHES].find_one({"bug_id": b, "matched_bug_id": a})["user_confirmed"] is True

    restored = client.post("/api/duplicates/confirm", json={"bug_id": b, "is_duplicate": False})
    assert restored.json()["status"] == "Open" and restored.json()["duplicate_of"] is None
    assert restored.json()["duplicate_review"] == "unique"


def test_duplicate_chains_and_cycles_are_prevented(client, make_bug):
    a, b, c = (make_bug(title=f"Report variant {i} for chain testing")["bug"]["bug_id"] for i in range(3))
    def confirm(bug, target):
        return client.post("/api/duplicates/confirm", json={"bug_id": bug, "is_duplicate": True, "matched_bug_id": target})

    assert confirm(a, a).status_code == 400
    assert confirm(b, a).status_code == 200
    assert confirm(c, b).json()["duplicate_of"] == a
    assert confirm(a, b).status_code == 409


def test_merging_an_original_repoints_its_duplicates(client, make_bug):
    a, b, c = (make_bug(title=f"Repoint scenario report number {i}")["bug"]["bug_id"] for i in range(3))
    client.post("/api/duplicates/confirm", json={"bug_id": b, "is_duplicate": True, "matched_bug_id": a})
    client.post("/api/duplicates/confirm", json={"bug_id": a, "is_duplicate": True, "matched_bug_id": c})
    assert client.get(f"/api/bugs/{b}").json()["duplicate_of"] == c


def test_deleting_an_original_reopens_its_duplicates(client, make_bug):
    a, b = (make_bug(title=f"Delete scenario report number {i}")["bug"]["bug_id"] for i in range(2))
    client.post("/api/duplicates/confirm", json={"bug_id": b, "is_duplicate": True, "matched_bug_id": a})
    client.delete(f"/api/bugs/{a}")
    bug = client.get(f"/api/bugs/{b}").json()
    assert bug["status"] == "Open" and bug["duplicate_of"] is None


def test_put_cannot_set_duplicate_without_review(client, make_bug):
    bug_id = make_bug()["bug"]["bug_id"]
    assert client.put(f"/api/bugs/{bug_id}", json={"status": "Duplicate"}).status_code == 400


def test_recheck_keeps_human_decisions(client, make_bug):
    bug_id = make_bug()["bug"]["bug_id"]
    client.post("/api/duplicates/confirm", json={"bug_id": bug_id, "is_duplicate": False})
    check = client.post(f"/api/duplicates/check/{bug_id}")
    assert check.status_code == 200
    reviewed = [m for m in get_database()[MATCHES].find({"bug_id": bug_id}) if m["user_confirmed"] is False]
    assert len(reviewed) == 5


def test_stored_matches_exclude_confirmed_duplicates(client):
    duplicate_id = get_database()[BUGS].find_one({"status": "Duplicate"})["bug_id"]
    data = client.post("/api/duplicates/search", json={"text": "System stops working after pressing the sign-in button"}).json()
    assert duplicate_id not in [m["bug"]["bug_id"] for m in data["matches"]]


# Triage


def test_triage_decision_records_what_changed(client, make_bug):
    bug = make_bug()["bug"]
    bug_id = bug["bug_id"]
    keep = {
        "component": bug["predicted_component"], "priority": bug["predicted_priority"],
        "severity": bug["predicted_severity"], "assigned_developer": bug["recommended_developer"],
    }

    approved = client.post(f"/api/triage/{bug_id}/decision", json=keep).json()
    assert approved["triage_status"] == "approved" and approved["status"] == "Open"
    assert approved["current"]["assigned_developer"] == keep["assigned_developer"]

    other = "Low" if keep["priority"] != "Low" else "High"
    modified = client.post(f"/api/triage/{bug_id}/decision", json={**keep, "priority": other}).json()
    assert modified["triage_status"] == "modified"
    assert modified["triage_decision"]["changed_fields"] == ["priority"]


def test_predict_does_not_save(client):
    before = get_database()[BUGS].count_documents({})
    response = client.post("/api/triage/predict", json={
        "title": "Login page crashes after entering valid credentials",
        "description": "The login page crashes after correct credentials are submitted.",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["component"]["label"] == "Authentication"
    assert data["recommended_developers"][0]["reason"]
    assert get_database()[BUGS].count_documents({}) == before


# Developers


def test_developer_creation_and_visibility(client):
    body = {"name": "New Dev", "email": _email(), "skills": ["rust"], "assigned_components": ["Backend"]}
    created = client.post("/api/developers", json=body)
    assert created.status_code == 201
    assert created.json()["developer_id"].startswith("DEV-") and created.json()["assigned_bugs"] == 0
    assert client.post("/api/developers", json=body).status_code == 409


# Attachments


def test_attachment_rules(client, make_bug):
    bug_id = make_bug()["bug"]["bug_id"]
    url = f"/api/bugs/{bug_id}/attachments"
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32

    assert client.post(url, files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 415
    assert client.post(url, files={"file": ("x.svg", b"<svg onload=alert(1)>", "image/svg+xml")}).status_code == 415
    assert client.post(url, files={"file": ("fake.png", b"<script>", "image/png")}).status_code == 415
    assert client.post(url, files={"file": ("empty.txt", b"", "text/plain")}).status_code == 422

    uploaded = client.post(url, files={"file": ("../../evil.png", png, "image/png")})
    assert uploaded.status_code == 201
    assert uploaded.json()["filename"] == "evil.png"

    download_url = f"{url}/{uploaded.json()['attachment_id']}"
    download = client.get(download_url)
    assert download.status_code == 200 and download.content == png
    assert "attachment" in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"


def test_attachments_live_in_mongodb_and_leave_with_their_report(client, make_bug):
    db = get_database()
    bug_id = make_bug()["bug"]["bug_id"]
    other_id = make_bug()["bug"]["bug_id"]
    body = b"\x89PNG\r\n\x1a\n" + b"1" * 1024
    uploaded = client.post(
        f"/api/bugs/{bug_id}/attachments", files={"file": ("résumé shot.png", body, "image/png")}
    ).json()
    attachment_id = uploaded["attachment_id"]
    assert db["attachments.files"].find_one({"_id": attachment_id})["metadata"]["bug_id"] == bug_id

    # An id only works through the report it belongs to.
    assert client.get(f"/api/bugs/{other_id}/attachments/{attachment_id}").status_code == 404
    download = client.get(f"/api/bugs/{bug_id}/attachments/{attachment_id}")
    assert download.content == body
    assert "r%C3%A9sum%C3%A9%20shot.png" in download.headers["content-disposition"]

    assert client.delete(f"/api/bugs/{bug_id}").status_code == 204
    assert db["attachments.files"].find_one({"_id": attachment_id}) is None
    assert db["attachments.chunks"].find_one({"files_id": attachment_id}) is None


def test_default_upload_limit_fits_vercel_body_limit():
    assert get_settings().max_upload_mb * 1024 * 1024 < 4.5 * 1000 * 1000


def test_oversized_attachment_rejected(client, make_bug, monkeypatch):
    bug_id = make_bug()["bug"]["bug_id"]
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    big = b"x" * (1024 * 1024 + 1)
    response = client.post(f"/api/bugs/{bug_id}/attachments", files={"file": ("big.log", big, "text/plain")})
    assert response.status_code == 413


# Analytics


def test_dashboard_counts_match_the_database(client):
    data = client.get("/api/analytics/dashboard").json()
    db = get_database()
    assert data["totals"]["total"] == db[BUGS].count_documents({})
    assert data["totals"]["duplicates"] == db[BUGS].count_documents({"status": "Duplicate"})
    assert sum(c["count"] for c in data["by_status"]) == data["totals"]["total"]
    assert len(data["weekly_trend"]) == 12 and len(data["monthly_trend"]) == 6
    assert len(data["recent"]) == 8 and "embedding" not in data["recent"][0]


def test_analytics_reflect_new_reports_immediately(client, make_bug):
    before = client.get("/api/analytics/dashboard").json()["totals"]["total"]
    make_bug()
    assert client.get("/api/analytics/dashboard").json()["totals"]["total"] == before + 1


def test_model_metrics_come_from_training_artifacts(client):
    triage = client.get("/api/analytics/triage").json()
    component = triage["classifiers"]["component"]
    assert 0 < component["accuracy"] <= 1 and component["baseline_accuracy"] < component["accuracy"]
    assert len(component["confusion_matrix"]) == len(component["classes"])

    duplicates = client.get("/api/analytics/duplicates").json()
    assert {"bert", "tfidf"} <= set(duplicates["evaluation"])
    assert duplicates["evaluation"]["bert"]["curve"]


def test_seeded_reviews_are_not_counted_as_live_feedback(client):
    db = get_database()
    seeded_reviewed = db[MATCHES].count_documents({"seeded": True, "user_confirmed": True})
    live_confirmed = db[MATCHES].count_documents({"seeded": {"$ne": True}, "user_confirmed": True})
    live = client.get("/api/analytics/duplicates").json()["live_reviews"]
    assert seeded_reviewed > 0 and live["confirmed"] == live_confirmed


def test_seed_refuses_production(monkeypatch):
    from scripts.seed import seed

    monkeypatch.setattr(get_settings(), "environment", "production")
    with pytest.raises(SystemExit):
        seed(reset=True)
    assert get_database()[BUGS].estimated_document_count() > 0


def test_health_reports_database_and_nlp(client):
    data = client.get("/api/health").json()
    assert data["database"] is True and data["nlp"]["semantic_available"] is True


# No sign-in


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/register", "/api/auth/forgot-password"])
def test_sign_in_routes_are_gone(client, path):
    assert client.post(path, json={}).status_code == 404


@pytest.mark.parametrize("path", ["/api/bugs", "/api/developers", "/api/analytics/dashboard", "/api/system/status"])
def test_routes_work_without_a_token(client, path):
    assert client.get(path).status_code == 200


def test_settings_need_no_secret():
    assert not hasattr(get_settings(), "jwt_secret")


def test_reports_are_credited_to_the_shared_workspace(make_bug):
    assert make_bug()["bug"]["reporter_name"] == "Team member"


# Failing safely


def test_unexpected_errors_return_a_readable_json_error(client, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import analytics

    def explode(*_):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(analytics, "dashboard", explode)
    response = TestClient(app, raise_server_exceptions=False).get("/api/analytics/dashboard")
    assert response.status_code == 500
    assert "unexpected error" in response.json()["detail"]
    assert "secret internal detail" not in response.text


def test_database_outage_returns_a_readable_503(client, monkeypatch):
    from pymongo.errors import ServerSelectionTimeoutError

    from app.services import developers

    def explode(*_):
        raise ServerSelectionTimeoutError("connection details")

    monkeypatch.setattr(developers, "list_developers", explode)
    monkeypatch.setattr("app.routers.developers.list_developers", explode)
    response = client.get("/api/developers")
    assert response.status_code == 503
    assert "database" in response.json()["detail"].lower()
    assert "connection details" not in response.text


def test_engine_loads_lazily_if_startup_events_did_not_run(client):
    from app.main import app

    engine = app.state.nlp
    del app.state.nlp
    try:
        assert client.get("/api/health").json()["nlp"]["semantic_available"] is True
        assert app.state.nlp is not None
    finally:
        app.state.nlp = engine
