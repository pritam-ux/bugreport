import uuid

import jwt
import pytest

from app.config import get_settings
from app.database import BUGS, MATCHES, USERS, get_database


def _email() -> str:
    return f"{uuid.uuid4().hex}@example.com"


# Authentication and roles


def test_public_registration_cannot_grant_a_role(client):
    response = client.post("/api/auth/register", json={
        "name": "Mallory", "email": _email(), "password": "correct-horse-42", "role": "Admin",
    })
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "Reporter"


def test_password_hash_never_leaves_the_api(client, admin):
    assert "password_hash" not in client.get("/api/auth/me", headers=admin).json()
    assert all("password_hash" not in u for u in client.get("/api/users", headers=admin).json())


@pytest.mark.parametrize("password", ["short1", "nodigitsinthispassword", "x1" * 40])
def test_weak_passwords_are_rejected(client, password):
    response = client.post("/api/auth/register", json={"name": "A B", "email": _email(), "password": password})
    assert response.status_code == 422


def test_duplicate_email_conflicts(client):
    body = {"name": "A B", "email": _email(), "password": "correct-horse-42"}
    assert client.post("/api/auth/register", json=body).status_code == 201
    assert client.post("/api/auth/register", json=body).status_code == 409


def test_wrong_password_and_unknown_email_look_the_same(client):
    wrong = client.post("/api/auth/login", json={"email": "admin@bugsense.dev", "password": "nope"})
    unknown = client.post("/api/auth/login", json={"email": _email(), "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_repeated_failures_are_throttled(client):
    email = _email()
    codes = [client.post("/api/auth/login", json={"email": email, "password": "x"}).status_code for _ in range(9)]
    assert codes[:8] == [401] * 8 and codes[8] == 429


@pytest.mark.parametrize("path", [
    "/api/bugs", "/api/developers", "/api/analytics/dashboard", "/api/users", "/api/system/status",
])
def test_routes_require_sign_in(client, path):
    assert client.get(path).status_code == 401


def test_forged_token_is_rejected(client):
    token = jwt.encode({"sub": "USR-1001", "ver": 0}, "not-the-real-secret-" + "y" * 30, algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_password_reset_is_single_use_and_ends_old_sessions(client):
    email = _email()
    registered = client.post("/api/auth/register", json={"name": "A B", "email": email, "password": "correct-horse-42"})
    old_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    token = client.post("/api/auth/forgot-password", json={"email": email}).json()["development_reset_token"]
    body = {"token": token, "password": "brand-new-pass-77"}
    assert client.post("/api/auth/reset-password", json=body).status_code == 200
    assert client.post("/api/auth/reset-password", json=body).status_code == 400

    assert client.get("/api/auth/me", headers=old_headers).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "brand-new-pass-77"}).status_code == 200


def test_reset_token_is_hidden_in_production(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "production")
    response = client.post("/api/auth/forgot-password", json={"email": "admin@bugsense.dev"})
    assert "development_reset_token" not in response.json()


def test_role_changes_are_admin_only_and_keep_one_admin(client, admin, developer):
    assert client.put("/api/users/USR-1003/role", json={"role": "Admin"}, headers=developer).status_code == 403
    assert client.put("/api/users/USR-1001/role", json={"role": "Reporter"}, headers=admin).status_code == 409


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
def test_invalid_reports_are_rejected(client, reporter, body):
    assert client.post("/api/bugs", json=body, headers=reporter).status_code == 422


def test_editing_text_updates_embedding(client, make_bug, admin):
    bug_id = make_bug()["bug"]["bug_id"]
    before = get_database()[BUGS].find_one({"bug_id": bug_id})["embedding"]
    response = client.put(f"/api/bugs/{bug_id}", json={"title": "Payment worker charges customers twice"}, headers=admin)
    assert response.status_code == 200
    assert get_database()[BUGS].find_one({"bug_id": bug_id})["embedding"] != before


# Listing


def test_filters_sort_and_pagination(client, admin):
    page = client.get("/api/bugs", params={"priority": "High", "page_size": 5}, headers=admin).json()
    assert page["total"] > 5 and len(page["items"]) == 5
    assert all(b["priority"] == "High" for b in page["items"])

    ordered = client.get("/api/bugs", params={"sort": "priority", "page_size": 100}, headers=admin).json()["items"]
    ranks = [b["priority_rank"] for b in ordered]
    assert ranks == sorted(ranks)

    assert client.get("/api/bugs", params={"search": "BUG-1001"}, headers=admin).json()["items"][0]["bug_id"] == "BUG-1001"
    assert client.get("/api/bugs", params={"search": "deadlocks"}, headers=admin).json()["total"] >= 1


def test_search_treats_input_as_literal_text(client, admin):
    assert client.get("/api/bugs", params={"search": ".*"}, headers=admin).json()["total"] == 0
    assert client.get("/api/bugs", params={"search": "(["}, headers=admin).status_code == 200


def test_operator_injection_in_filter_is_harmless(client, admin):
    response = client.get("/api/bugs", params={"priority": '{"$ne": null}'}, headers=admin)
    assert response.status_code == 200 and response.json()["total"] == 0


def test_unknown_bug_is_404(client, admin):
    assert client.get("/api/bugs/BUG-0", headers=admin).status_code == 404


# Permissions on bugs


def test_reporter_edit_rules(client, make_bug, reporter, new_reporter):
    bug_id = make_bug()["bug"]["bug_id"]
    assert client.put(f"/api/bugs/{bug_id}", json={"expected_behavior": "No error."}, headers=reporter).status_code == 200
    assert client.put(f"/api/bugs/{bug_id}", json={"status": "Closed"}, headers=reporter).status_code == 403
    assert client.put(f"/api/bugs/{bug_id}", json={"expected_behavior": "x"}, headers=new_reporter).status_code == 403


def test_only_admin_deletes(client, make_bug, developer, admin):
    bug_id = make_bug()["bug"]["bug_id"]
    assert client.delete(f"/api/bugs/{bug_id}", headers=developer).status_code == 403
    assert client.delete(f"/api/bugs/{bug_id}", headers=admin).status_code == 204
    assert get_database()[MATCHES].count_documents({"bug_id": bug_id}) == 0


def test_status_changes_track_resolution(client, make_bug, developer):
    bug_id = make_bug()["bug"]["bug_id"]
    resolved = client.put(f"/api/bugs/{bug_id}", json={"status": "Resolved"}, headers=developer).json()
    assert resolved["resolved_at"]
    reopened = client.put(f"/api/bugs/{bug_id}", json={"status": "Open"}, headers=developer).json()
    assert reopened["resolved_at"] is None


def test_assignment_updates_developer_counts(client, make_bug, admin):
    bug_id = make_bug()["bug"]["bug_id"]
    before = client.get("/api/developers/DEV-101", headers=admin).json()["open_bugs"]
    client.put(f"/api/bugs/{bug_id}", json={"assigned_developer": "DEV-101", "status": "Open"}, headers=admin)
    assert client.get("/api/developers/DEV-101", headers=admin).json()["open_bugs"] == before + 1
    missing = client.put(f"/api/bugs/{bug_id}", json={"assigned_developer": "DEV-999"}, headers=admin)
    assert missing.status_code == 422


# Duplicate review


def test_search_does_not_save(client, admin):
    before = get_database()[BUGS].count_documents({})
    response = client.post("/api/duplicates/search", json={"text": "Dark theme makes the invoice table unreadable"}, headers=admin)
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


def test_confirm_duplicate_then_unique(client, make_bug, developer):
    a = make_bug()["bug"]["bug_id"]
    b = make_bug(title="Empty table export raises an error page")["bug"]["bug_id"]

    marked = client.post("/api/duplicates/confirm", json={"bug_id": b, "is_duplicate": True, "matched_bug_id": a}, headers=developer)
    assert marked.status_code == 200
    assert marked.json()["status"] == "Duplicate" and marked.json()["duplicate_of"] == a
    assert get_database()[MATCHES].find_one({"bug_id": b, "matched_bug_id": a})["user_confirmed"] is True

    restored = client.post("/api/duplicates/confirm", json={"bug_id": b, "is_duplicate": False}, headers=developer)
    assert restored.json()["status"] == "Open" and restored.json()["duplicate_of"] is None
    assert restored.json()["duplicate_review"] == "unique"


def test_duplicate_chains_and_cycles_are_prevented(client, make_bug, developer):
    a, b, c = (make_bug(title=f"Report variant {i} for chain testing")["bug"]["bug_id"] for i in range(3))
    def confirm(bug, target):
        return client.post("/api/duplicates/confirm", json={"bug_id": bug, "is_duplicate": True, "matched_bug_id": target}, headers=developer)

    assert confirm(a, a).status_code == 400
    assert confirm(b, a).status_code == 200
    assert confirm(c, b).json()["duplicate_of"] == a
    assert confirm(a, b).status_code == 409


def test_merging_an_original_repoints_its_duplicates(client, make_bug, developer):
    a, b, c = (make_bug(title=f"Repoint scenario report number {i}")["bug"]["bug_id"] for i in range(3))
    client.post("/api/duplicates/confirm", json={"bug_id": b, "is_duplicate": True, "matched_bug_id": a}, headers=developer)
    client.post("/api/duplicates/confirm", json={"bug_id": a, "is_duplicate": True, "matched_bug_id": c}, headers=developer)
    assert client.get(f"/api/bugs/{b}", headers=developer).json()["duplicate_of"] == c


def test_deleting_an_original_reopens_its_duplicates(client, make_bug, developer, admin):
    a, b = (make_bug(title=f"Delete scenario report number {i}")["bug"]["bug_id"] for i in range(2))
    client.post("/api/duplicates/confirm", json={"bug_id": b, "is_duplicate": True, "matched_bug_id": a}, headers=developer)
    client.delete(f"/api/bugs/{a}", headers=admin)
    bug = client.get(f"/api/bugs/{b}", headers=admin).json()
    assert bug["status"] == "Open" and bug["duplicate_of"] is None


def test_put_cannot_set_duplicate_without_review(client, make_bug, developer):
    bug_id = make_bug()["bug"]["bug_id"]
    assert client.put(f"/api/bugs/{bug_id}", json={"status": "Duplicate"}, headers=developer).status_code == 400


def test_reporter_cannot_review_someone_elses_report(client, make_bug, new_reporter):
    bug_id = make_bug()["bug"]["bug_id"]
    response = client.post("/api/duplicates/confirm", json={"bug_id": bug_id, "is_duplicate": False}, headers=new_reporter)
    assert response.status_code == 403


def test_recheck_keeps_human_decisions(client, make_bug, developer):
    bug_id = make_bug()["bug"]["bug_id"]
    client.post("/api/duplicates/confirm", json={"bug_id": bug_id, "is_duplicate": False}, headers=developer)
    check = client.post(f"/api/duplicates/check/{bug_id}", headers=developer)
    assert check.status_code == 200
    reviewed = [m for m in get_database()[MATCHES].find({"bug_id": bug_id}) if m["user_confirmed"] is False]
    assert len(reviewed) == 5


def test_stored_matches_exclude_confirmed_duplicates(client, admin):
    duplicate_id = get_database()[BUGS].find_one({"status": "Duplicate"})["bug_id"]
    data = client.post("/api/duplicates/search", json={"text": "System stops working after pressing the sign-in button"}, headers=admin).json()
    assert duplicate_id not in [m["bug"]["bug_id"] for m in data["matches"]]


# Triage


def test_triage_decision_records_what_changed(client, make_bug, admin, developer):
    bug = make_bug()["bug"]
    bug_id = bug["bug_id"]
    keep = {
        "component": bug["predicted_component"], "priority": bug["predicted_priority"],
        "severity": bug["predicted_severity"], "assigned_developer": bug["recommended_developer"],
    }
    assert client.post(f"/api/triage/{bug_id}/decision", json=keep, headers=developer).status_code == 403

    approved = client.post(f"/api/triage/{bug_id}/decision", json=keep, headers=admin).json()
    assert approved["triage_status"] == "approved" and approved["status"] == "Open"
    assert approved["current"]["assigned_developer"] == keep["assigned_developer"]

    other = "Low" if keep["priority"] != "Low" else "High"
    modified = client.post(f"/api/triage/{bug_id}/decision", json={**keep, "priority": other}, headers=admin).json()
    assert modified["triage_status"] == "modified"
    assert modified["triage_decision"]["changed_fields"] == ["priority"]


def test_predict_does_not_save(client, reporter):
    before = get_database()[BUGS].count_documents({})
    response = client.post("/api/triage/predict", json={
        "title": "Login page crashes after entering valid credentials",
        "description": "The login page crashes after correct credentials are submitted.",
    }, headers=reporter)
    assert response.status_code == 200
    data = response.json()
    assert data["component"]["label"] == "Authentication"
    assert data["recommended_developers"][0]["reason"]
    assert get_database()[BUGS].count_documents({}) == before


# Developers


def test_developer_creation_and_visibility(client, admin, reporter):
    body = {"name": "New Dev", "email": _email(), "skills": ["rust"], "assigned_components": ["Backend"]}
    assert client.post("/api/developers", json=body, headers=reporter).status_code == 403
    created = client.post("/api/developers", json=body, headers=admin)
    assert created.status_code == 201
    assert created.json()["developer_id"].startswith("DEV-") and created.json()["assigned_bugs"] == 0
    assert client.post("/api/developers", json=body, headers=admin).status_code == 409


# Attachments


def test_attachment_rules(client, make_bug, reporter, new_reporter):
    bug_id = make_bug()["bug"]["bug_id"]
    url = f"/api/bugs/{bug_id}/attachments"
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32

    assert client.post(url, files={"file": ("x.exe", b"MZ", "application/octet-stream")}, headers=reporter).status_code == 415
    assert client.post(url, files={"file": ("x.svg", b"<svg onload=alert(1)>", "image/svg+xml")}, headers=reporter).status_code == 415
    assert client.post(url, files={"file": ("fake.png", b"<script>", "image/png")}, headers=reporter).status_code == 415
    assert client.post(url, files={"file": ("empty.txt", b"", "text/plain")}, headers=reporter).status_code == 422
    assert client.post(url, files={"file": ("a.png", png, "image/png")}, headers=new_reporter).status_code == 403

    uploaded = client.post(url, files={"file": ("../../evil.png", png, "image/png")}, headers=reporter)
    assert uploaded.status_code == 201
    assert uploaded.json()["filename"] == "evil.png"

    download_url = f"{url}/{uploaded.json()['attachment_id']}"
    assert client.get(download_url).status_code == 401
    download = client.get(download_url, headers=reporter)
    assert download.status_code == 200 and download.content == png
    assert "attachment" in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"


def test_oversized_attachment_rejected(client, make_bug, reporter, monkeypatch):
    bug_id = make_bug()["bug"]["bug_id"]
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    big = b"x" * (1024 * 1024 + 1)
    response = client.post(f"/api/bugs/{bug_id}/attachments", files={"file": ("big.log", big, "text/plain")}, headers=reporter)
    assert response.status_code == 413


# Analytics


def test_dashboard_counts_match_the_database(client, admin):
    data = client.get("/api/analytics/dashboard", headers=admin).json()
    db = get_database()
    assert data["totals"]["total"] == db[BUGS].count_documents({})
    assert data["totals"]["duplicates"] == db[BUGS].count_documents({"status": "Duplicate"})
    assert sum(c["count"] for c in data["by_status"]) == data["totals"]["total"]
    assert len(data["weekly_trend"]) == 12 and len(data["monthly_trend"]) == 6
    assert len(data["recent"]) == 8 and "embedding" not in data["recent"][0]


def test_analytics_reflect_new_reports_immediately(client, admin, make_bug):
    before = client.get("/api/analytics/dashboard", headers=admin).json()["totals"]["total"]
    make_bug()
    assert client.get("/api/analytics/dashboard", headers=admin).json()["totals"]["total"] == before + 1


def test_model_metrics_come_from_training_artifacts(client, admin):
    triage = client.get("/api/analytics/triage", headers=admin).json()
    component = triage["classifiers"]["component"]
    assert 0 < component["accuracy"] <= 1 and component["baseline_accuracy"] < component["accuracy"]
    assert len(component["confusion_matrix"]) == len(component["classes"])

    duplicates = client.get("/api/analytics/duplicates", headers=admin).json()
    assert {"bert", "tfidf"} <= set(duplicates["evaluation"])
    assert duplicates["evaluation"]["bert"]["curve"]


def test_seeded_reviews_are_not_counted_as_live_feedback(client, admin):
    db = get_database()
    seeded_reviewed = db[MATCHES].count_documents({"seeded": True, "user_confirmed": True})
    live_confirmed = db[MATCHES].count_documents({"seeded": {"$ne": True}, "user_confirmed": True})
    live = client.get("/api/analytics/duplicates", headers=admin).json()["live_reviews"]
    assert seeded_reviewed > 0 and live["confirmed"] == live_confirmed


def test_seed_refuses_production(monkeypatch):
    from scripts.seed import seed

    monkeypatch.setattr(get_settings(), "environment", "production")
    with pytest.raises(SystemExit):
        seed(reset=True)
    assert get_database()[USERS].estimated_document_count() > 0


def test_health_reports_database_and_nlp(client):
    data = client.get("/api/health").json()
    assert data["database"] is True and data["nlp"]["semantic_available"] is True
