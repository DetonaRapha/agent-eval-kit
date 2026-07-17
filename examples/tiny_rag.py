"""A deliberately naive RAG, used as the demo system under test.

It is *meant* to be mediocre. Retrieval is a bag-of-words keyword overlap over a
handful of in-memory documents, and the "answer" is just the best-matching
document sentence. It will miss paraphrases, get confused by thin questions, and
happily answer even when it retrieved nothing useful — exactly the failure modes
the eval kit exists to surface. A perfect SUT would prove nothing about the kit.
"""

from __future__ import annotations

import re

from agent_eval.sut import SUTResult

# A tiny synthetic health knowledge base. Intentionally small and shallow.
_DOCUMENTS: list[str] = [
    "Adults should aim for 7 to 9 hours of sleep per night for good health.",
    "Drinking water helps regulate body temperature and supports kidney function.",
    "Regular physical activity lowers the risk of heart disease and improves mood.",
    "A balanced diet includes fruits, vegetables, whole grains, and lean protein.",
    "Handwashing with soap for 20 seconds reduces the spread of common infections.",
    "Excessive added sugar intake is linked to weight gain and type 2 diabetes.",
]

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.casefold()))


def _retrieve(question: str, k: int = 1) -> list[str]:
    """Return the ``k`` documents with the most token overlap with the question.

    No embeddings, no ranking cleverness — just raw word overlap. Ties break by
    document order. If nothing overlaps at all, it still returns something, which
    is the naive behavior we want the eval to catch.
    """
    q_tokens = _tokens(question)
    scored = sorted(
        enumerate(_DOCUMENTS),
        key=lambda pair: (len(q_tokens & _tokens(pair[1])), -pair[0]),
        reverse=True,
    )
    return [doc for _, doc in scored[:k]]


def answer(question: str) -> SUTResult:
    """Answer a question by parroting the single best-matching document.

    The naive strategy: retrieve the top document and return it verbatim as the
    answer. It never synthesizes or hedges, so off-domain questions get a
    confidently wrong, ungrounded reply — which the groundedness and relevance
    metrics should punish.
    """
    contexts = _retrieve(question, k=1)
    best = contexts[0] if contexts else ""
    # latency_ms is left at 0.0: this SUT does no real I/O. A real SUT would
    # measure and report its own wall-clock time here.
    return SUTResult(answer=best, contexts=contexts, latency_ms=0.0)
