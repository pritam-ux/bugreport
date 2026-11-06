"""Component, priority and severity classifiers.

Each target tries TF-IDF, BERT embedding and combined features. Training keeps
whichever scored best in group-aware cross-validation. A TF-IDF model is always
kept as well: it works without BERT and its coefficients explain predictions.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import StratifiedGroupKFold

from .similarity import make_vectorizer

TARGETS = {
    "component": ["Authentication", "API", "Backend", "Database", "Frontend", "Infrastructure", "UI"],
    "priority": ["Critical", "High", "Medium", "Low"],
    "severity": ["Critical", "Major", "Minor", "Trivial"],
}
FEATURE_SETS = ("tfidf", "bert", "combined")
REGULARIZATION = (1.0, 4.0)


def _logistic(c: float = 4.0) -> LogisticRegression:
    return LogisticRegression(C=c, class_weight="balanced", max_iter=2000)


@dataclass
class TargetModel:
    target: str
    feature_set: str
    vectorizer: object
    model: LogisticRegression
    tfidf_vectorizer: object
    tfidf_model: LogisticRegression
    metrics: dict

    def _features(self, documents: list[str], embeddings: np.ndarray | None):
        if self.feature_set == "bert":
            return embeddings
        tfidf = self.vectorizer.transform(documents)
        if self.feature_set == "combined":
            return hstack([tfidf, csr_matrix(embeddings)]).tocsr()
        return tfidf

    def predict(self, document: str, embedding: np.ndarray | None) -> dict:
        """Label, confidence, alternatives, and the terms that pushed towards the label."""
        if self.feature_set == "tfidf" or embedding is not None:
            model = self.model
            features = self._features([document], None if embedding is None else embedding.reshape(1, -1))
            feature_set = self.feature_set
        else:
            model, feature_set = self.tfidf_model, "tfidf"
            features = self.tfidf_vectorizer.transform([document])

        probabilities = model.predict_proba(features)[0]
        order = np.argsort(probabilities)[::-1]
        label = str(model.classes_[order[0]])
        return {
            "label": label,
            "confidence": round(float(probabilities[order[0]]), 3),
            "alternatives": [
                {"label": str(model.classes_[i]), "confidence": round(float(probabilities[i]), 3)}
                for i in order[1:3]
            ],
            "feature_set": feature_set,
            "top_terms": self._top_terms(document, label),
        }

    def _top_terms(self, document: str, label: str, limit: int = 5) -> list[str]:
        row = self.tfidf_vectorizer.transform([document])
        class_index = list(self.tfidf_model.classes_).index(label)
        coefficients = self.tfidf_model.coef_[class_index]
        contributions = sorted(
            ((row.data[k] * coefficients[col], col) for k, col in enumerate(row.indices)),
            reverse=True,
        )
        names = self.tfidf_vectorizer.get_feature_names_out()
        return [str(names[col]) for value, col in contributions[:limit] if value > 0]


def _fit_features(feature_set: str, documents: list[str], embeddings: np.ndarray | None):
    """Return ``(vectorizer, training matrix, transform function)``."""
    if feature_set == "bert":
        return None, embeddings, lambda docs, emb: emb
    vectorizer = make_vectorizer()
    tfidf = vectorizer.fit_transform(documents)
    if feature_set == "combined":
        return (
            vectorizer,
            hstack([tfidf, csr_matrix(embeddings)]).tocsr(),
            lambda docs, emb: hstack([vectorizer.transform(docs), csr_matrix(emb)]).tocsr(),
        )
    return vectorizer, tfidf, lambda docs, emb: vectorizer.transform(docs)


def cross_validate(
    feature_set: str,
    documents: list[str],
    embeddings: np.ndarray | None,
    labels: np.ndarray,
    groups: np.ndarray,
    c: float = 4.0,
    n_splits: int = 5,
) -> np.ndarray:
    """Out-of-fold predictions. Paraphrases of one bug always stay in the same fold,
    otherwise the score would reward memorising the duplicate in the training split."""
    predictions = np.empty(len(labels), dtype=object)
    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42)
    for train, test in splitter.split(documents, labels, groups):
        train_docs = [documents[i] for i in train]
        test_docs = [documents[i] for i in test]
        train_emb = None if embeddings is None else embeddings[train]
        test_emb = None if embeddings is None else embeddings[test]
        _, matrix, transform = _fit_features(feature_set, train_docs, train_emb)
        model = _logistic(c).fit(matrix, labels[train])
        predictions[test] = model.predict(transform(test_docs, test_emb))
    return predictions


def _report(labels: np.ndarray, predictions: np.ndarray, classes: list[str]) -> dict:
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, predictions, labels=classes, zero_division=0
    )
    return {
        "accuracy": round(float(accuracy_score(labels, predictions)), 3),
        "macro_f1": round(float(f1_score(labels, predictions, labels=classes, average="macro", zero_division=0)), 3),
        "classes": classes,
        "per_class": [
            {
                "label": c,
                "precision": round(float(precision[i]), 3),
                "recall": round(float(recall[i]), 3),
                "f1": round(float(f1[i]), 3),
                "support": int(support[i]),
            }
            for i, c in enumerate(classes)
        ],
        "confusion_matrix": confusion_matrix(labels, predictions, labels=classes).tolist(),
    }


def train_target(
    target: str,
    documents: list[str],
    embeddings: np.ndarray | None,
    labels: list[str],
    groups: list[str],
) -> TargetModel:
    y, group_array = np.array(labels), np.array(groups)
    classes = [c for c in TARGETS[target] if c in set(labels)]
    candidates = [f for f in FEATURE_SETS if embeddings is not None or f == "tfidf"]

    comparison = {}
    reports = {}
    for feature_set in candidates:
        for c in REGULARIZATION:
            report = _report(y, cross_validate(feature_set, documents, embeddings, y, group_array, c), classes)
            reports[(feature_set, c)] = report
            current = comparison.get(feature_set)
            if current is None or report["macro_f1"] > current["macro_f1"]:
                comparison[feature_set] = {"accuracy": report["accuracy"], "macro_f1": report["macro_f1"]}
    best, best_c = max(reports, key=lambda key: reports[key]["macro_f1"])

    tfidf_vectorizer = make_vectorizer()
    tfidf_model = _logistic(best_c).fit(tfidf_vectorizer.fit_transform(documents), y)
    if best == "tfidf":
        vectorizer, model = tfidf_vectorizer, tfidf_model
    else:
        vectorizer, matrix, _ = _fit_features(best, documents, embeddings)
        model = _logistic(best_c).fit(matrix, y)

    # What always guessing the commonest label would score. Read accuracy against this.
    baseline = max(labels.count(c) for c in classes) / len(labels)
    metrics = {
        **reports[(best, best_c)],
        "selected_features": best,
        "feature_comparison": comparison,
        "baseline_accuracy": round(baseline, 3),
        "samples": len(labels),
    }
    return TargetModel(target, best, vectorizer, model, tfidf_vectorizer, tfidf_model, metrics)
