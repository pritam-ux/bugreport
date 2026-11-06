"""Duplicate candidate scoring: BERT cosine, TF-IDF baseline and a learned probability."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity

from .preprocess import tokens_for_tfidf


def make_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        tokenizer=tokens_for_tfidf,
        preprocessor=None,
        lowercase=False,
        token_pattern=None,
        ngram_range=(1, 2),
        sublinear_tf=True,
    )


def tfidf_scores(query: str, documents: list[str]) -> np.ndarray:
    """Baseline similarity. The vocabulary is fitted on the current corpus."""
    if not documents:
        return np.zeros(0)
    vectorizer = make_vectorizer()
    try:
        matrix = vectorizer.fit_transform(documents)
    except ValueError:  # every document was empty after preprocessing
        return np.zeros(len(documents))
    return cosine_similarity(vectorizer.transform([query]), matrix)[0]


def bert_scores(query_vector: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity. Vectors are already normalised, so this is a dot product."""
    if matrix.size == 0:
        return np.zeros(0)
    return np.clip(matrix @ query_vector, -1.0, 1.0)


@dataclass
class DuplicateCalibrator:
    """Maps raw similarity scores to an estimated probability of being a duplicate.

    Cosine similarity is not a probability: 0.6 can be a strong match. This logistic
    regression learns the mapping from labelled pairs. Its output is still an
    estimate, so the product always asks a person to confirm.
    """

    model: LogisticRegression
    uses_bert: bool

    def probability(self, bert: np.ndarray | None, tfidf: np.ndarray) -> np.ndarray:
        if self.uses_bert:
            if bert is None:
                raise ValueError("Calibrator needs BERT scores")
            features = np.column_stack([bert, tfidf])
        else:
            features = tfidf.reshape(-1, 1)
        return self.model.predict_proba(features)[:, 1]


def fit_calibrator(bert: np.ndarray | None, tfidf: np.ndarray, labels: np.ndarray) -> DuplicateCalibrator:
    features = np.column_stack([bert, tfidf]) if bert is not None else tfidf.reshape(-1, 1)
    model = LogisticRegression(C=10.0, max_iter=1000)
    model.fit(features, labels)
    return DuplicateCalibrator(model=model, uses_bert=bert is not None)


def match_strength(probability: float) -> tuple[str, str]:
    """Plain-language label and next step. Never claims a certain duplicate."""
    if probability >= 0.6:
        return "Strong", "Review the details. If they describe the same issue, mark this report as a duplicate."
    if probability >= 0.2:
        return "Possible", "Compare the two reports closely. They may share a root cause."
    return "Weak", "Probably a different issue. Keep it as unique unless the details say otherwise."
