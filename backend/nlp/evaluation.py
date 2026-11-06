"""Measures duplicate detection on labelled reports, for BERT and for the TF-IDF baseline.

Each report queries every other report. A query with a labelled partner should find
it; a query without one should raise no alarm. Thresholds and the calibrator are
fitted on some bug groups and scored on others, so results are out of sample.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.model_selection import GroupKFold

from .similarity import DuplicateCalibrator, fit_calibrator, make_vectorizer


@dataclass
class ScoreMatrices:
    tfidf: np.ndarray
    bert: np.ndarray | None


def pairwise_scores(documents: list[str], embeddings: np.ndarray | None) -> ScoreMatrices:
    tfidf_matrix = make_vectorizer().fit_transform(documents)
    tfidf = np.asarray((tfidf_matrix @ tfidf_matrix.T).todense())
    return ScoreMatrices(tfidf=tfidf, bert=None if embeddings is None else embeddings @ embeddings.T)


def _ranking_metrics(scores: np.ndarray, groups: np.ndarray, indices: np.ndarray) -> dict:
    """Recall@k and mean reciprocal rank over reports that have a true duplicate."""
    hits = {1: 0, 3: 0, 5: 0}
    reciprocal = 0.0
    total = 0
    for i in indices:
        partners = np.flatnonzero(groups == groups[i])
        partners = partners[partners != i]
        if len(partners) == 0:
            continue
        total += 1
        row = scores[i].copy()
        row[i] = -np.inf
        order = np.argsort(row)[::-1]
        rank = int(np.flatnonzero(np.isin(order, partners))[0]) + 1
        reciprocal += 1 / rank
        for k in hits:
            hits[k] += int(rank <= k)
    if total == 0:
        return {"queries": 0, "recall_at_1": 0.0, "recall_at_3": 0.0, "recall_at_5": 0.0, "mrr": 0.0}
    return {
        "queries": total,
        "recall_at_1": round(hits[1] / total, 3),
        "recall_at_3": round(hits[3] / total, 3),
        "recall_at_5": round(hits[5] / total, 3),
        "mrr": round(reciprocal / total, 3),
    }


def _top_candidates(scores: np.ndarray, groups: np.ndarray, indices: np.ndarray):
    """For each query: its best score, and whether that best hit is a true duplicate."""
    best, correct, has_partner = [], [], []
    for i in indices:
        row = scores[i].copy()
        row[i] = -np.inf
        j = int(row.argmax())
        best.append(float(row[j]))
        correct.append(groups[j] == groups[i])
        has_partner.append(int((groups == groups[i]).sum()) > 1)
    return np.array(best), np.array(correct), np.array(has_partner)


def _precision_recall(best, correct, has_partner, threshold: float) -> tuple[float, float, float]:
    flagged = best >= threshold
    true_positive = int((flagged & correct).sum())
    precision = true_positive / int(flagged.sum()) if flagged.any() else 1.0
    recall = true_positive / int(has_partner.sum()) if has_partner.any() else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _best_threshold(best, correct, has_partner, grid: np.ndarray) -> float:
    return float(max(grid, key=lambda t: _precision_recall(best, correct, has_partner, t)[2]))


def evaluate_scores(scores: np.ndarray, groups: np.ndarray, n_splits: int = 5) -> dict:
    """Ranking metrics plus out-of-sample precision and recall for one score matrix."""
    indices = np.arange(len(groups))
    grid = np.round(np.arange(0.05, 0.96, 0.01), 2)

    best, correct, has_partner = _top_candidates(scores, groups, indices)
    true_positive = false_positive = 0
    for train, test in GroupKFold(n_splits=n_splits).split(indices, groups=groups):
        threshold = _best_threshold(best[train], correct[train], has_partner[train], grid)
        flagged = best[test] >= threshold
        true_positive += int((flagged & correct[test]).sum())
        false_positive += int((flagged & ~correct[test]).sum())
    with_partner = int(has_partner.sum())
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / with_partner if with_partner else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    curve = []
    for threshold in np.round(np.arange(0.1, 0.96, 0.05), 2):
        p, r, _ = _precision_recall(best, correct, has_partner, float(threshold))
        curve.append({"threshold": float(threshold), "precision": round(p, 3), "recall": round(r, 3)})

    return {
        **_ranking_metrics(scores, groups, indices),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "threshold": round(_best_threshold(best, correct, has_partner, grid), 2),
        "curve": curve,
    }


def labelled_pairs(scores: ScoreMatrices, groups: np.ndarray, hard_negatives: int = 5):
    """Training pairs: every true duplicate pair, plus each report's closest non-duplicates."""
    ranker = scores.bert if scores.bert is not None else scores.tfidf
    rows, columns, labels = [], [], []
    for i in range(len(groups)):
        same = groups == groups[i]
        for j in np.flatnonzero(same):
            if j > i:
                rows.append(i)
                columns.append(j)
                labels.append(1)
        candidates = np.where(same, -np.inf, ranker[i])
        for j in np.argsort(candidates)[::-1][:hard_negatives]:
            rows.append(i)
            columns.append(int(j))
            labels.append(0)
    return np.array(rows), np.array(columns), np.array(labels)


def train_calibrator(scores: ScoreMatrices, groups: np.ndarray) -> tuple[DuplicateCalibrator, dict]:
    """Fit on all pairs. Quality is estimated on out-of-sample bug groups first."""
    rows, columns, labels = labelled_pairs(scores, groups)
    tfidf = scores.tfidf[rows, columns]
    bert = None if scores.bert is None else scores.bert[rows, columns]

    pair_groups = groups[rows]
    true_positive = false_positive = false_negative = 0
    for train, test in GroupKFold(n_splits=5).split(rows, groups=pair_groups):
        model = fit_calibrator(None if bert is None else bert[train], tfidf[train], labels[train])
        predicted = model.probability(None if bert is None else bert[test], tfidf[test]) >= 0.5
        true_positive += int((predicted & (labels[test] == 1)).sum())
        false_positive += int((predicted & (labels[test] == 0)).sum())
        false_negative += int((~predicted & (labels[test] == 1)).sum())
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0

    metrics = {
        "pairs": int(len(labels)),
        "positive_pairs": int(labels.sum()),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "note": "Pair-level scores at probability 0.5, including each report's five hardest non-duplicates.",
    }
    return fit_calibrator(bert, tfidf, labels), metrics
