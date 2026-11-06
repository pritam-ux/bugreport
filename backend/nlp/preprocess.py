"""Text cleaning shared by every model.

Two outputs on purpose:
- ``clean_for_embedding`` keeps natural sentences, because BERT uses word order
  and context.
- ``tokens_for_tfidf`` stems and drops stop words, because TF-IDF only counts terms.
"""
from __future__ import annotations

import html
import re
from collections.abc import Mapping

from nltk.stem.snowball import SnowballStemmer
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

_stemmer = SnowballStemmer("english")

_HTML_TAG = re.compile(r"<[^>\n]{1,200}>")
_CODE_FENCE = re.compile(r"```")
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_HEX = re.compile(r"\b0x[0-9a-f]+\b", re.I)
_TIMESTAMP = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?\b")
_WINDOWS_PATH = re.compile(r"\b[A-Za-z]:\\[^\s:]+")
_UNIX_PATH = re.compile(r"(?<![\w/])/(?:[\w.-]+/){2,}[\w.-]*")
_WHITESPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z][a-z0-9_]+|\d{3}")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")

# Python, Java/JS and generic "SomeError: message" lines all carry the useful signal.
_EXCEPTION = re.compile(r"\b([A-Z]?[\w.]*(?:Error|Exception|Failure|Fault))\b(?::\s*([^\n]{0,160}))?")
_STOP_WORDS = frozenset(ENGLISH_STOP_WORDS) - {"not", "no", "never", "cannot"}


def normalize(text: str | None) -> str:
    """Remove markup and volatile values that make identical bugs look different."""
    if not text:
        return ""
    value = html.unescape(str(text))
    value = _CODE_FENCE.sub(" ", value)
    value = _HTML_TAG.sub(" ", value)
    value = _URL.sub(" url ", value)
    value = _EMAIL.sub(" email ", value)
    value = _UUID.sub(" id ", value)
    value = _TIMESTAMP.sub(" ", value)
    value = _HEX.sub(" address ", value)
    value = _WINDOWS_PATH.sub(" path ", value)
    value = _UNIX_PATH.sub(" path ", value)
    return _WHITESPACE.sub(" ", value).strip()


def summarize_stack_trace(stack_trace: str | None, max_items: int = 3) -> str:
    """Keep exception names and messages. Line numbers and frames are mostly noise."""
    if not stack_trace:
        return ""
    seen: list[str] = []
    for name, message in _EXCEPTION.findall(html.unescape(stack_trace)):
        item = normalize(f"{name} {message}".strip())
        if item and item not in seen:
            seen.append(item)
        if len(seen) == max_items:
            break
    if seen:
        return ". ".join(seen)
    # No recognisable exception: fall back to the first line of the log.
    first_line = stack_trace.strip().splitlines()[0] if stack_trace.strip() else ""
    return normalize(first_line)[:200]


def build_document(bug: Mapping) -> str:
    """Combine a report's fields into the single text the models read.

    The title comes first because embedding models weight early tokens most and
    can truncate long text. Environment and component are left out on purpose:
    they say where a bug was seen, not what it is, and the reporter's component
    would leak the classifier's target.
    """
    title = normalize(bug.get("title"))
    parts = [f"{title}." if title and title[-1] not in ".!?" else title]
    for field in ("description", "actual_behavior", "expected_behavior", "steps_to_reproduce"):
        value = normalize(bug.get(field))
        if value:
            parts.append(value if value[-1] in ".!?" else f"{value}.")
    trace = summarize_stack_trace(bug.get("stack_trace"))
    if trace:
        parts.append(f"{trace}.")
    return " ".join(p for p in parts if p)


def clean_for_embedding(text: str | None) -> str:
    return normalize(text)


def tokens_for_tfidf(text: str | None) -> list[str]:
    """Lowercase, split identifiers, drop stop words and stem.

    Three-digit numbers survive because they are often HTTP status codes.
    """
    value = _CAMEL.sub(" ", normalize(text)).lower().replace("_", " ")
    return [_stemmer.stem(t) for t in _TOKEN.findall(value) if t not in _STOP_WORDS]


def split_sentences(text: str | None) -> list[str]:
    if not text:
        return []
    pieces = _SENTENCE_END.split(html.unescape(str(text)).strip())
    return [p.strip() for p in pieces if len(p.strip()) >= 3]


def word_stems(text: str | None) -> dict[str, set[str]]:
    """Map each stem to the surface words that produced it, for highlighting."""
    result: dict[str, set[str]] = {}
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text or ""):
        lower = word.lower()
        if lower in _STOP_WORDS or len(lower) < 3:
            continue
        result.setdefault(_stemmer.stem(lower), set()).add(word)
    return result
