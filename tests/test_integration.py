"""Opt-in integration tests that hit the real Claude judge.

These make real network calls and cost tokens, so they are:

* marked ``@pytest.mark.integration`` — excluded from the default run
  (see ``addopts`` in pyproject); invoke explicitly with ``pytest -m integration``;
* skipped unless ``ANTHROPIC_API_KEY`` is set and the ``anthropic`` SDK is
  installed, so a plain checkout never fails for lack of credentials.

The assertions are deliberately loose: the real model is non-deterministic, so we
verify the contract (valid ``JudgeScores`` in range) and a coarse discrimination
signal (a clearly good answer is not judged worse than a clearly bad one), not
exact numbers.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

_HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))

skip_without_key = pytest.mark.skipif(
    not _HAS_KEY,
    reason="ANTHROPIC_API_KEY not set; skipping real Claude judge call",
)


@skip_without_key
def test_anthropic_judge_real_call_returns_valid_scores():
    pytest.importorskip("anthropic", reason="anthropic SDK not installed")
    from agent_eval.judges import AnthropicJudge

    judge = AnthropicJudge()
    scores = judge.score(
        question="How many hours of sleep should adults aim for each night?",
        answer="Adults should aim for 7 to 9 hours of sleep per night.",
        contexts=["Adults should aim for 7 to 9 hours of sleep per night for good health."],
        reference="Adults should aim for 7 to 9 hours of sleep per night.",
    )

    for value in scores.as_metrics().values():
        assert 0.0 <= value <= 1.0
    assert scores.rationale  # the real judge should explain itself


@skip_without_key
def test_anthropic_judge_real_call_discriminates():
    pytest.importorskip("anthropic", reason="anthropic SDK not installed")
    from agent_eval.judges import AnthropicJudge

    judge = AnthropicJudge()
    question = "Why is drinking water important for the body?"
    contexts = ["Drinking water helps regulate body temperature and supports kidney function."]
    reference = "Water helps regulate body temperature and supports kidney function."

    good = judge.score(
        question,
        "Water helps regulate body temperature and supports kidney function.",
        contexts,
        reference,
    )
    bad = judge.score(question, "I don't know, sorry.", [], reference)

    # Loose: the good answer should not be judged less relevant than the evasive one.
    assert good.relevance >= bad.relevance
