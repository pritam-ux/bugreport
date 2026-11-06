"""Semantic embedding backend. Replace the model through settings or a new Encoder.

Runs Sentence-BERT through ONNX Runtime, which needs no PyTorch and keeps the API
small enough for serverless hosting. The model files are stored in ``backend/models``.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
MAX_TOKENS = 256  # the limit all-MiniLM-L6-v2 was trained with
BATCH_SIZE = 32


class Encoder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return one L2-normalised row per input text."""


class OnnxSentenceEncoder:
    """Sentence-BERT inference with mean pooling. The model loads once, on first use."""

    def __init__(self, model_name: str):
        self.name = model_name
        self._directory = MODELS_DIR / model_name
        self._session = None
        self._tokenizer = None
        self._lock = threading.Lock()

    def _load(self):
        if self._session is None:
            with self._lock:
                if self._session is None:
                    import onnxruntime
                    from tokenizers import Tokenizer

                    logger.info("Loading embedding model %s", self.name)
                    tokenizer = Tokenizer.from_file(str(self._directory / "tokenizer.json"))
                    tokenizer.enable_truncation(max_length=MAX_TOKENS)
                    tokenizer.enable_padding()
                    self._tokenizer = tokenizer
                    self._session = onnxruntime.InferenceSession(
                        str(self._directory / "model.onnx"), providers=["CPUExecutionProvider"]
                    )
        return self._session, self._tokenizer

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        session, tokenizer = self._load()
        encoded = tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        available = {
            "input_ids": ids,
            "attention_mask": mask,
            "token_type_ids": np.zeros_like(ids),
        }
        inputs = {i.name: available[i.name] for i in session.get_inputs()}
        tokens = session.run(None, inputs)[0]

        # Average the token vectors, ignoring padding, then normalise for cosine similarity.
        weights = mask[..., np.newaxis].astype(np.float32)
        pooled = (tokens * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        return pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        batches = [self._encode_batch(texts[i:i + BATCH_SIZE]) for i in range(0, len(texts), BATCH_SIZE)]
        return np.vstack(batches).astype(np.float32)


def load_encoder(model_name: str) -> tuple[Encoder | None, str | None]:
    """Return ``(encoder, None)``, or ``(None, reason)`` when BERT cannot be used.

    Callers then run the TF-IDF baseline and report that state to the user
    instead of pretending semantic matching took place.
    """
    try:
        encoder = OnnxSentenceEncoder(model_name)
        encoder.encode(["warm up"])
        return encoder, None
    except Exception as exc:  # missing package, missing model files, bad model
        reason = f"Could not load embedding model '{model_name}': {exc}"
        logger.warning(reason)
        return None, reason
