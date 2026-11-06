"""Developer recommendation from expertise, assignment history and current workload.

Plain data in, plain data out: this module knows nothing about MongoDB. Every part
of the score is returned so the UI can show why someone was suggested.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .preprocess import tokens_for_tfidf

WEIGHTS = {"expertise": 0.3, "history": 0.35, "similar_work": 0.2, "availability": 0.15}
CAPACITY = 10  # open bugs at which a developer counts as fully loaded


@dataclass
class DeveloperProfile:
    developer_id: str
    name: str
    skills: list[str]
    assigned_components: list[str]
    open_bugs: int = 0
    resolved_by_component: dict[str, int] = field(default_factory=dict)
    avg_days_by_component: dict[str, float] = field(default_factory=dict)
    resolved_bug_ids: list[str] = field(default_factory=list)
    resolved_embeddings: np.ndarray | None = None


def _skill_score(document_tokens: set[str], developer: DeveloperProfile, component: str) -> tuple[float, list[str]]:
    matched = [
        skill for skill in developer.skills
        if set(tokens_for_tfidf(skill)) & document_tokens
    ]
    score = 0.6 if component in developer.assigned_components else 0.0
    score += min(0.4, 0.2 * len(matched))
    return score, matched


def _history_score(developer: DeveloperProfile, component: str, most_resolved: int) -> float:
    if most_resolved == 0:
        return 0.0
    return developer.resolved_by_component.get(component, 0) / most_resolved


def _similar_work(embedding: np.ndarray | None, developer: DeveloperProfile) -> tuple[float, str | None]:
    """Closest resolved bug. Rescaled because unrelated bugs still score about 0.2."""
    matrix = developer.resolved_embeddings
    if embedding is None or matrix is None or len(matrix) == 0:
        return 0.0, None
    similarities = matrix @ embedding
    best = int(similarities.argmax())
    score = float(np.clip((similarities[best] - 0.2) / 0.6, 0, 1))
    closest = developer.resolved_bug_ids[best] if best < len(developer.resolved_bug_ids) else None
    return score, closest if score >= 0.4 else None


def _reason(developer: DeveloperProfile, component: str, matched_skills: list[str], closest: str | None) -> str:
    parts = []
    resolved = developer.resolved_by_component.get(component, 0)
    if resolved:
        avg = developer.avg_days_by_component.get(component)
        pace = f" in an average of {avg:.1f} days" if avg is not None else ""
        parts.append(f"Resolved {resolved} {component} bug{'s' if resolved != 1 else ''}{pace}")
    elif component in developer.assigned_components:
        parts.append(f"Covers the {component} component, with no resolved bugs there yet")
    else:
        parts.append(f"No {component} history yet")
    if matched_skills:
        parts.append(f"skills match this report ({', '.join(matched_skills[:3])})")
    if closest:
        parts.append(f"fixed a similar bug ({closest})")
    parts.append(f"has {developer.open_bugs} open bug{'s' if developer.open_bugs != 1 else ''}")
    return "; ".join(parts) + "."


def recommend(
    document: str,
    component: str,
    embedding: np.ndarray | None,
    developers: list[DeveloperProfile],
    limit: int = 3,
) -> list[dict]:
    """Rank developers for a bug, best first."""
    if not developers:
        return []
    tokens = set(tokens_for_tfidf(document))
    most_resolved = max(d.resolved_by_component.get(component, 0) for d in developers)

    ranked = []
    for developer in developers:
        expertise, matched_skills = _skill_score(tokens, developer, component)
        history = _history_score(developer, component, most_resolved)
        similar, closest = _similar_work(embedding, developer)
        availability = max(0.0, 1 - developer.open_bugs / CAPACITY)
        parts = {
            "expertise": round(expertise, 3),
            "history": round(history, 3),
            "similar_work": round(similar, 3),
            "availability": round(availability, 3),
        }
        score = sum(WEIGHTS[key] * parts[key] for key in WEIGHTS)
        ranked.append({
            "developer_id": developer.developer_id,
            "name": developer.name,
            "score": round(score, 3),
            "breakdown": parts,
            "reason": _reason(developer, component, matched_skills, closest),
        })
    ranked.sort(key=lambda item: (-item["score"], item["developer_id"]))
    return ranked[:limit]
