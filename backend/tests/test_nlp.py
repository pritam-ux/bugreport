from pathlib import Path

import numpy as np
import pytest

from nlp.classifier import cross_validate
from nlp.evaluation import evaluate_scores
from nlp.pipeline import Candidate, NlpEngine
from nlp.preprocess import build_document, normalize, summarize_stack_trace, tokens_for_tfidf
from nlp.recommender import DeveloperProfile, recommend
from nlp.similarity import make_vectorizer, match_strength, tfidf_scores


@pytest.fixture(scope="module")
def engine():
    from app.config import get_settings

    settings = get_settings()
    return NlpEngine.load(settings.embedding_model, settings.artifacts_dir)


def test_normalize_removes_volatile_noise():
    text = normalize("<b>Failed</b> at 2026-01-02T03:04:05Z at 0xDEADBEEF see https://a.example/x from a@b.io")
    assert "<b>" not in text and "2026" not in text and "DEADBEEF" not in text
    assert "a.example" not in text and "a@b.io" not in text


def test_stack_trace_keeps_exception_not_frames():
    trace = 'Traceback:\n  File "/srv/app/x.py", line 9\nValueError: month must be in 1..12'
    summary = summarize_stack_trace(trace)
    assert "ValueError" in summary and "line 9" not in summary


def test_tfidf_tokens_stem_and_keep_status_codes():
    tokens = tokens_for_tfidf("Crashes while crashing returned 500 and the userName")
    assert tokens.count("crash") == 2 and "500" in tokens and "user" in tokens and "the" not in tokens


def test_document_excludes_component_label():
    document = build_document({"title": "Slow page", "description": "It is slow", "component": "Database"})
    assert "Database" not in document and document.startswith("Slow page.")


def test_paraphrase_from_brief_outranks_unrelated_reports(engine):
    """No shared wording apart from 'button'. Only semantic matching ranks this first."""
    query = "Application crashes when I click the login button."
    target = "System stops working after pressing the sign-in button."
    others = ["Invoice PDF shows the wrong tax rate for Canada.", "Dark mode text is unreadable on the billing table."]
    documents = [target, *others]
    vectors = engine.embed_many(documents)
    candidates = [Candidate(f"B{i}", d, vectors[i]) for i, d in enumerate(documents)]
    results = engine.find_duplicates(query, engine.embed_document(query), candidates)
    assert results[0]["bug_id"] == "B0"
    assert results[0]["bert_score"] > results[1]["bert_score"] + 0.2


def test_scores_are_computed_and_repeatable(engine):
    documents = ["Login fails with a server error", "Tooltip is clipped by the sidebar"]
    vectors = engine.embed_many(documents)
    candidates = [Candidate(f"B{i}", d, vectors[i]) for i, d in enumerate(documents)]
    first = engine.find_duplicates("cannot log in", engine.embed_document("cannot log in"), candidates)
    second = engine.find_duplicates("cannot log in", engine.embed_document("cannot log in"), candidates)
    other = engine.find_duplicates("sidebar tooltip", engine.embed_document("sidebar tooltip"), candidates)
    assert first == second
    assert first[0]["bug_id"] == "B0" and other[0]["bug_id"] == "B1"


def test_tfidf_baseline_runs_when_bert_is_unavailable(tmp_path):
    engine = NlpEngine(encoder=None, encoder_error="package missing")
    results = engine.find_duplicates(
        "login crash on submit",
        None,
        [Candidate("A", "login crash after submit", None), Candidate("B", "invoice tax rate wrong", None)],
    )
    assert results[0]["bug_id"] == "A" and results[0]["bert_score"] is None
    assert engine.status["semantic_available"] is False and engine.status["semantic_error"] == "package missing"


def test_comparison_aligns_sentences_with_different_wording(engine):
    result = engine.compare(
        "Application crashes when I click the login button.",
        "System stops working after pressing the sign-in button. The invoice total looks wrong.",
    )
    assert result["source_sentences"][0]["match"] == 0
    assert result["target_sentences"][1]["match"] is None
    assert "button" in result["shared_keywords"]


def test_match_labels_never_claim_certainty():
    for probability in (0.0, 0.3, 0.99):
        strength, action = match_strength(probability)
        assert strength in ("Strong", "Possible", "Weak")
        assert "guarantee" not in action.lower() and "is a duplicate" not in action.lower()


def test_classifier_explains_with_terms_from_the_report(engine):
    text = "Password reset token still works after being used, account takeover risk."
    prediction = engine.classify(text, engine.embed_document(text))
    assert prediction["component"]["label"] == "Authentication"
    assert 0 < prediction["component"]["confidence"] <= 1
    assert prediction["component"]["top_terms"]


def test_cross_validation_keeps_duplicate_groups_together():
    """A group split across folds would leak paraphrases into the training data."""
    documents = [f"alpha report {i}" if i % 2 else f"beta report {i}" for i in range(20)]
    labels = np.array(["A" if i % 2 else "B" for i in range(20)])
    groups = np.array([f"g{i // 2}" for i in range(20)])
    predictions = cross_validate("tfidf", documents, None, labels, groups, n_splits=2)
    assert set(predictions) <= {"A", "B"} and None not in predictions


def test_evaluation_scores_a_perfect_matrix_as_perfect():
    groups = np.array(["a", "a", "b", "b", "c", "d"])
    scores = np.full((6, 6), 0.1)
    scores[0, 1] = scores[1, 0] = scores[2, 3] = scores[3, 2] = 0.9
    metrics = evaluate_scores(scores, groups, n_splits=2)
    assert metrics["recall_at_1"] == 1.0 and metrics["mrr"] == 1.0 and metrics["queries"] == 4


def test_tfidf_handles_documents_with_no_terms():
    assert tfidf_scores("login", ["...", "!!!"]).tolist() == [0.0, 0.0]
    assert make_vectorizer() is not None


def _profile(developer_id, components=(), resolved=None, open_bugs=0, skills=()):
    return DeveloperProfile(
        developer_id=developer_id, name=developer_id, skills=list(skills),
        assigned_components=list(components), open_bugs=open_bugs, resolved_by_component=resolved or {},
    )


def test_recommender_prefers_history_and_expertise():
    people = [
        _profile("expert", ["Authentication"], {"Authentication": 12}, skills=["oauth"]),
        _profile("other", ["UI"], {"UI": 20}, skills=["css"]),
    ]
    best = recommend("oauth login fails", "Authentication", None, people)[0]
    assert best["developer_id"] == "expert"
    assert "Resolved 12 Authentication bugs" in best["reason"]


def test_recommender_balances_workload_between_equal_developers():
    people = [
        _profile("busy", ["API"], {"API": 5}, open_bugs=10),
        _profile("free", ["API"], {"API": 5}, open_bugs=1),
    ]
    assert recommend("endpoint error", "API", None, people)[0]["developer_id"] == "free"


def test_recommender_reason_is_honest_without_history():
    best = recommend("anything", "Database", None, [_profile("new", [])])[0]
    assert "No Database history" in best["reason"]


def test_corrupt_model_file_leaves_engine_usable(tmp_path: Path, engine):
    (tmp_path / "models.joblib").write_bytes(b"this is not a model")
    broken = NlpEngine.load(engine.status["semantic_engine"], tmp_path)
    assert broken.status["classifiers_trained"] is False
    assert "models.joblib" in broken.status["classifier_error"]
    assert broken.status["semantic_available"] is True


def test_missing_artifacts_leave_engine_usable(tmp_path: Path, engine):
    empty = NlpEngine.load(engine.status["semantic_engine"], tmp_path)
    assert empty.status["classifiers_trained"] is False
    assert empty.classify("anything at all", None) == {}
