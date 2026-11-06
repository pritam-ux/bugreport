"""Explains a match by aligning similar sentences and listing shared keywords."""
from __future__ import annotations

from .embeddings import Encoder
from .preprocess import normalize, split_sentences, word_stems

# Below this, MiniLM sentence pairs are usually only loosely related.
SENTENCE_MATCH_THRESHOLD = 0.45


def shared_keywords(source: str, target: str, limit: int = 12) -> list[str]:
    """Words whose stems occur in both texts, in every surface form used."""
    source_stems, target_stems = word_stems(source), word_stems(target)
    shared = sorted(source_stems.keys() & target_stems.keys())
    words: set[str] = set()
    for stem in shared[:limit]:
        words |= source_stems[stem] | target_stems[stem]
    return sorted(words, key=str.lower)


def compare_texts(source: str, target: str, encoder: Encoder | None) -> dict:
    """Sentence alignment for the comparison view.

    Each sentence's ``match`` is the index of its closest partner in the other text,
    or null when nothing clears the threshold. Without BERT only keywords are returned.
    """
    source_sentences = split_sentences(normalize(source))[:30]
    target_sentences = split_sentences(normalize(target))[:30]
    result = {
        "source_sentences": [{"text": s, "match": None, "score": None} for s in source_sentences],
        "target_sentences": [{"text": s, "match": None, "score": None} for s in target_sentences],
        "shared_keywords": shared_keywords(source, target),
    }
    if encoder is None or not source_sentences or not target_sentences:
        return result

    scores = encoder.encode(source_sentences) @ encoder.encode(target_sentences).T
    for i, row in enumerate(scores):
        j = int(row.argmax())
        if float(row[j]) >= SENTENCE_MATCH_THRESHOLD:
            result["source_sentences"][i].update(match=j, score=round(float(row[j]), 3))
    for j, column in enumerate(scores.T):
        i = int(column.argmax())
        if float(column[i]) >= SENTENCE_MATCH_THRESHOLD:
            result["target_sentences"][j].update(match=i, score=round(float(column[i]), 3))
    return result
