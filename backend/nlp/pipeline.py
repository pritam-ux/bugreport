"""The single entry point the API uses for NLP work.

Routes and services call ``NlpEngine``. They never touch scikit-learn or
sentence-transformers, so any model can be replaced behind this class.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np

from .classifier import TargetModel
from .embeddings import Encoder, load_encoder
from .highlight import compare_texts
from .preprocess import build_document, clean_for_embedding, tokens_for_tfidf
from .recommender import DeveloperProfile, recommend
from .similarity import DuplicateCalibrator, bert_scores, match_strength, tfidf_scores

logger = logging.getLogger(__name__)
MODEL_FILE = "models.joblib"
METRICS_FILE = "metrics.json"
# An estimate is never shown as certain, even for near-identical text.
MAX_PROBABILITY = 0.99


@dataclass
class Candidate:
    """An existing bug that can be matched against."""
    bug_id: str
    document: str
    embedding: np.ndarray | None


@dataclass
class NlpEngine:
    encoder: Encoder | None
    encoder_error: str | None
    models: dict[str, TargetModel] = field(default_factory=dict)
    calibrator: DuplicateCalibrator | None = None
    metrics: dict = field(default_factory=dict)
    model_error: str | None = None

    @classmethod
    def load(cls, model_name: str, artifacts_dir: Path) -> "NlpEngine":
        encoder, error = load_encoder(model_name)
        engine = cls(encoder=encoder, encoder_error=error)
        path = Path(artifacts_dir) / MODEL_FILE
        if path.exists():
            # A bad model file must not take the API down. Reports still save without predictions.
            try:
                bundle = joblib.load(path)
                engine.models = bundle["models"]
                engine.calibrator = bundle["calibrator"]
                if encoder is not None and bundle.get("encoder_name") not in (None, encoder.name):
                    logger.warning("Models were trained with %s but %s is loaded. Run scripts.train.",
                                   bundle.get("encoder_name"), encoder.name)
            except Exception as exc:
                engine.model_error = f"Could not load {MODEL_FILE}: {exc}"
                logger.exception(engine.model_error)
        metrics_path = Path(artifacts_dir) / METRICS_FILE
        if metrics_path.exists():
            engine.metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        return engine

    @property
    def status(self) -> dict:
        return {
            "semantic_engine": self.encoder.name if self.encoder else "tfidf-baseline",
            "semantic_available": self.encoder is not None,
            "semantic_error": self.encoder_error,
            "classifiers_trained": bool(self.models),
            "calibrated": self.calibrator is not None,
            "classifier_error": self.model_error,
        }

    def embed_document(self, document: str) -> np.ndarray | None:
        if self.encoder is None:
            return None
        return self.encoder.encode([clean_for_embedding(document)])[0]

    def embed_many(self, documents: list[str]) -> np.ndarray | None:
        if self.encoder is None:
            return None
        return self.encoder.encode([clean_for_embedding(d) for d in documents])

    @staticmethod
    def document_for(bug: Mapping) -> str:
        return build_document(bug)

    def find_duplicates(
        self,
        document: str,
        embedding: np.ndarray | None,
        candidates: list[Candidate],
        limit: int = 5,
    ) -> list[dict]:
        """Rank candidates by BERT cosine, or by TF-IDF when BERT is unavailable."""
        if not candidates:
            return []
        tfidf = tfidf_scores(document, [c.document for c in candidates])

        usable = embedding is not None and all(c.embedding is not None for c in candidates)
        bert = None
        if usable:
            bert = bert_scores(embedding, np.vstack([c.embedding for c in candidates]))

        ranking = bert if bert is not None else tfidf
        probability = None
        if self.calibrator is not None and self.calibrator.uses_bert == (bert is not None):
            probability = self.calibrator.probability(bert, tfidf)

        results = []
        for index in np.argsort(ranking)[::-1][:limit]:
            prob = None if probability is None else round(min(float(probability[index]), MAX_PROBABILITY), 3)
            strength, action = match_strength(prob if prob is not None else float(ranking[index]))
            results.append({
                "bug_id": candidates[index].bug_id,
                "similarity_score": round(float(max(ranking[index], 0.0)), 4),
                "bert_score": None if bert is None else round(float(bert[index]), 4),
                "tfidf_score": round(float(tfidf[index]), 4),
                "duplicate_probability": prob,
                "match_strength": strength,
                "recommended_action": action,
            })
        return results

    def trace(self, document: str, embedding: np.ndarray | None, candidates_compared: int) -> dict:
        """What each pipeline step produced for a report, for display in the UI."""
        tokens = tokens_for_tfidf(document)
        return {
            "clean_text": document,
            "token_count": len(tokens),
            "tokens_preview": tokens[:30],
            "embedding_dimensions": None if embedding is None else int(embedding.shape[0]),
            "embedding_preview": None if embedding is None else [round(float(x), 3) for x in embedding[:8]],
            "semantic_engine": self.status["semantic_engine"],
            "candidates_compared": candidates_compared,
        }

    def compare(self, source_text: str, target_text: str) -> dict:
        return compare_texts(source_text, target_text, self.encoder)

    def classify(self, document: str, embedding: np.ndarray | None) -> dict[str, dict]:
        if not self.models:
            return {}
        return {name: model.predict(document, embedding) for name, model in self.models.items()}

    def recommend_developers(
        self,
        document: str,
        component: str,
        embedding: np.ndarray | None,
        developers: list[DeveloperProfile],
    ) -> list[dict]:
        return recommend(document, component, embedding, developers)
