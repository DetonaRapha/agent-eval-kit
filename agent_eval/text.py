"""Shared text normalization and tokenization.

Defined once and reused by every deterministic metric and by the mock judge so
that "does this text overlap that text?" is answered identically everywhere.
Consistency here is what makes scores reproducible and comparable across
metrics.
"""

from __future__ import annotations

import re
import string
from collections.abc import Iterable

# A small, opinionated English stopword set. Kept tiny on purpose: content-word
# overlap is a cheap proxy, and an aggressive list would hide real signal.
_STOPWORDS: frozenset[str] = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "else",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "without",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "i",
        "you",
        "he",
        "she",
        "they",
        "we",
        "me",
        "my",
        "your",
        "our",
        "their",
        "them",
        "his",
        "her",
    ]
)

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, strip punctuation, and collapse whitespace.

    This is the single canonical normalization used across the kit. Two strings
    that normalize to the same value are treated as equal.
    """
    lowered = text.casefold().translate(_PUNCT_TABLE)
    return _WHITESPACE_RE.sub(" ", lowered).strip()


def tokenize(text: str) -> list[str]:
    """Split normalized text into whitespace-delimited tokens."""
    normalized = normalize(text)
    return normalized.split() if normalized else []


def content_tokens(text: str) -> set[str]:
    """Return the set of content-bearing tokens (stopwords removed).

    Used by overlap-based metrics where function words would inflate the score
    without carrying meaning.
    """
    return {tok for tok in tokenize(text) if tok not in _STOPWORDS}


def overlap_fraction(source: str, target: Iterable[str] | str) -> float:
    """Fraction of ``source`` content tokens that also appear in ``target``.

    Returns 0.0 when ``source`` has no content tokens, so an empty answer never
    scores as fully grounded. Direction matters: this asks "how much of the
    source is supported by the target", not the reverse.
    """
    source_tokens = content_tokens(source)
    if not source_tokens:
        return 0.0

    if isinstance(target, str):
        target_tokens = content_tokens(target)
    else:
        target_tokens = set()
        for piece in target:
            target_tokens |= content_tokens(piece)

    matched = sum(1 for tok in source_tokens if tok in target_tokens)
    return matched / len(source_tokens)
