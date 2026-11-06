"""Semantic embedding backend. Replace the model through settings or a new Encoder."""
from __future__ import annotations

import logging
import threading
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)


class Encoder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return one L2-normalised row per input text."""


class SentenceBertEncoder:
    """Sentence-BERT wrapper. The model loads once, on first use."""

    def __init__(self, model_name: str):
        self.name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    logger.info("Loading embedding model %s", self.name)
                    self._model = SentenceTransformer(self.name)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return np.asarray(
            self._load().encode(
                texts,
                batch_size=32,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            ),
            dtype=np.float32,
        )


def load_encoder(model_name: str) -> tuple[Encoder | None, str | None]:
    """Return ``(encoder, None)``, or ``(None, reason)`` when BERT cannot be used.

    Callers then run the TF-IDF baseline and report that state to the user
    instead of pretending semantic matching took place.
    """
    try:
        encoder = SentenceBertEncoder(model_name)
        encoder.encode(["warm up"])
        return encoder, None
    except Exception as exc:  # missing package, no network for first download, bad model
        reason = f"Could not load embedding model '{model_name}': {exc}"
        logger.warning(reason)
        return None, reason
