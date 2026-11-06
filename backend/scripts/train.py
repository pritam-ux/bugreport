"""Train the classifiers and duplicate calibrator, and record their measured quality.

Usage: python -m scripts.train [--dataset path.psv]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np

from app.config import get_settings
from nlp.classifier import TARGETS, train_target
from nlp.dataset import load_dataset
from nlp.embeddings import load_encoder
from nlp.evaluation import evaluate_scores, pairwise_scores, train_calibrator
from nlp.pipeline import METRICS_FILE, MODEL_FILE
from nlp.preprocess import build_document, clean_for_embedding

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = BACKEND_DIR / "data" / "seed_bugs.psv"


def train(dataset_path: Path = DEFAULT_DATASET, artifacts_dir: Path | None = None) -> dict:
    settings = get_settings()
    artifacts_dir = Path(artifacts_dir or settings.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    records = load_dataset(dataset_path)
    documents = [build_document(r) for r in records]
    groups = np.array([r["group"] for r in records])

    encoder, error = load_encoder(settings.embedding_model)
    if encoder is None:
        print(f"WARNING: {error}\nTraining the TF-IDF baseline only.")
    embeddings = None if encoder is None else encoder.encode([clean_for_embedding(d) for d in documents])

    models = {}
    for target in TARGETS:
        labels = [r[target] for r in records]
        models[target] = train_target(target, documents, embeddings, labels, list(groups))
        m = models[target].metrics
        print(f"{target:10s} {m['selected_features']:9s} accuracy={m['accuracy']:.3f} macro_f1={m['macro_f1']:.3f}")

    scores = pairwise_scores(documents, embeddings)
    duplicate_metrics = {"tfidf": evaluate_scores(scores.tfidf, groups)}
    if scores.bert is not None:
        duplicate_metrics["bert"] = evaluate_scores(scores.bert, groups)
    for name, values in duplicate_metrics.items():
        print(f"{name:6s} recall@1={values['recall_at_1']:.3f} recall@5={values['recall_at_5']:.3f} "
              f"precision={values['precision']:.3f} recall={values['recall']:.3f} f1={values['f1']:.3f}")

    calibrator, calibrator_metrics = train_calibrator(scores, groups)
    print(f"calibrator pairs={calibrator_metrics['pairs']} precision={calibrator_metrics['precision']:.3f} "
          f"recall={calibrator_metrics['recall']:.3f}")

    joblib.dump(
        {"models": models, "calibrator": calibrator, "encoder_name": encoder.name if encoder else None},
        artifacts_dir / MODEL_FILE,
    )
    metrics = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "file": dataset_path.name,
            "reports": len(records),
            "duplicate_groups": int(sum((groups == g).sum() > 1 for g in set(groups))),
            "synthetic": dataset_path.resolve() == DEFAULT_DATASET.resolve(),
        },
        "embedding_model": encoder.name if encoder else None,
        "classifiers": {name: model.metrics for name, model in models.items()},
        "duplicates": duplicate_metrics,
        "calibrator": calibrator_metrics,
    }
    (artifacts_dir / METRICS_FILE).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    train(parser.parse_args().dataset)
