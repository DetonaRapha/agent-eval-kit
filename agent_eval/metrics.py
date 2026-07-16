"""Deterministic metrics — pure functions, no network, no LLM.

Each metric maps a :class:`~agent_eval.sut.SUTResult` and an
:class:`~agent_eval.datasets.Example` to a score. Scores are on a 0..1 scale
where **higher is better**, the one convention shared across the whole kit.
Latency is the exception: it is a raw measurement, reported separately.
"""

from __future__ import annotations

from agent_eval.datasets import Example
from agent_eval.sut import SUTResult
from agent_eval.text import content_tokens, normalize, overlap_fraction

# Metric names, centralized so runner, scorecard, and CLI never drift apart.
EXACT_MATCH = "exact_match"
KEYWORD_RECALL = "keyword_recall"
GROUNDEDNESS_PROXY = "groundedness_proxy"

#: Deterministic metrics reported on the 0..1 scale, in display order.
DETERMINISTIC_METRICS: tuple[str, ...] = (
    EXACT_MATCH,
    KEYWORD_RECALL,
    GROUNDEDNESS_PROXY,
)


def exact_match(result: SUTResult, example: Example) -> float:
    """1.0 if the normalized answer equals the normalized reference, else 0.0.

    Strict by design: a blunt signal of "verbatim correct" that only fires for
    short, canonical answers. Most real answers score 0 here — that is expected,
    and why it sits alongside softer metrics.
    """
    return 1.0 if normalize(result.answer) == normalize(example.reference) else 0.0


def keyword_recall(result: SUTResult, example: Example) -> float:
    """Fraction of ``must_include`` terms present in the answer.

    Returns 1.0 when the example specifies no required terms — there is nothing
    to miss, so it cannot penalize. Matching is on normalized content tokens, so
    punctuation and casing do not matter and stopword-only terms are ignored.
    """
    required = example.must_include
    if not required:
        return 1.0

    answer_tokens = content_tokens(result.answer)
    hits = sum(1 for term in required if _term_present(term, answer_tokens))
    return hits / len(required)


def groundedness_proxy(result: SUTResult, example: Example) -> float:
    """Fraction of answer content tokens found in the retrieved contexts.

    A cheap, no-LLM proxy for hallucination: a low value means the answer used
    words that appear nowhere in what the system actually retrieved, suggesting
    it made things up. Returns 0.0 when there are no contexts — an ungrounded
    answer, by construction.
    """
    return overlap_fraction(result.answer, result.contexts)


def latency_ms(result: SUTResult, example: Example) -> float:
    """Pass through the SUT's measured latency. Reported, not scored."""
    return result.latency_ms


def _term_present(term: str, answer_tokens: set[str]) -> bool:
    """Whether every content token of ``term`` appears in the answer.

    A multi-word required term counts as present only if all of its content
    tokens are — a stricter, more honest recall than substring matching.
    """
    term_tokens = content_tokens(term)
    if not term_tokens:
        return False
    return term_tokens <= answer_tokens
