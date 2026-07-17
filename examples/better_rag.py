"""A less-naive RAG, used to demonstrate the kit comparing two systems.

Where ``tiny_rag`` parrots the single best-matching document with raw token
overlap, this one improves in two honest, measurable ways:

1. **Content-word retrieval.** It ranks documents by overlap of *content* tokens
   (stopwords removed), which picks the right document more reliably than raw
   word overlap.
2. **Out-of-domain honesty.** If nothing in the knowledge base is a real match,
   it says so instead of confidently returning an irrelevant document. That is
   exactly the behavior the eval rewards on questions outside the KB.

It is still simple — no embeddings, no synthesis — but it is *better*, and the
scorecard should show that. That is the point: the kit's job is to tell two
systems apart.
"""

from __future__ import annotations

from agent_eval.sut import SUTResult
from agent_eval.text import content_tokens

# Same synthetic health knowledge base as tiny_rag, so the comparison is fair.
_DOCUMENTS: list[str] = [
    "Adults should aim for 7 to 9 hours of sleep per night for good health.",
    "Drinking water helps regulate body temperature and supports kidney function.",
    "Regular physical activity lowers the risk of heart disease and improves mood.",
    "A balanced diet includes fruits, vegetables, whole grains, and lean protein.",
    "Handwashing with soap for 20 seconds reduces the spread of common infections.",
    "Excessive added sugar intake is linked to weight gain and type 2 diabetes.",
]

# Below this many shared content words, we treat the question as out-of-domain.
_MIN_OVERLAP = 1

_OUT_OF_DOMAIN = (
    "My knowledge base does not cover that; a qualified professional should be consulted."
)


def _rank(question: str) -> list[tuple[int, str]]:
    """Documents scored by shared content-token count, best first."""
    q_tokens = content_tokens(question)
    scored = [(len(q_tokens & content_tokens(doc)), doc) for doc in _DOCUMENTS]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored


def answer(question: str) -> SUTResult:
    """Answer using content-word retrieval, declining when out of domain."""
    ranked = _rank(question)
    best_score, best_doc = ranked[0]

    if best_score < _MIN_OVERLAP:
        # Nothing relevant retrieved: be honest instead of guessing.
        return SUTResult(answer=_OUT_OF_DOMAIN, contexts=[], latency_ms=0.0)

    # Keep every document that shares the top score as supporting context.
    contexts = [doc for score, doc in ranked if score == best_score]
    return SUTResult(answer=best_doc, contexts=contexts, latency_ms=0.0)
