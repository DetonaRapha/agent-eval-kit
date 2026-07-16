"""Judges — the graded, subjective layer of evaluation.

A judge scores an answer on three axes that deterministic metrics cannot capture
well: is it faithful to the retrieved context, does it actually answer the
question, and did it avoid hallucinating. All scores are 0..1, higher is better.

Two implementations ship:

* :class:`MockJudge` — deterministic, no LLM, no network. The default. It makes
  the whole kit runnable anywhere: clone, one command, green CI, no API key.
* :class:`AnthropicJudge` — the real thing, backed by Claude, opt-in. Its SDK is
  imported lazily so it is never a required dependency.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from agent_eval.text import content_tokens, overlap_fraction

# Judge score axes, centralized so every consumer agrees on the names.
FAITHFULNESS = "faithfulness"
RELEVANCE = "relevance"
NOT_HALLUCINATED = "not_hallucinated"

#: Judge score axes, in display order.
JUDGE_METRICS: tuple[str, ...] = (FAITHFULNESS, RELEVANCE, NOT_HALLUCINATED)


@dataclass
class JudgeScores:
    """A judge's verdict on a single answer. All axes are 0..1, higher better.

    Attributes:
        faithfulness: Is the answer supported by the provided contexts?
        relevance: Does the answer actually address the question?
        not_hallucinated: 1.0 = no hallucination, 0.0 = fabricated content
            (the inverse of hallucination risk, kept on the higher-is-better
            scale like everything else).
        rationale: Short human-readable justification.
    """

    faithfulness: float
    relevance: float
    not_hallucinated: float
    rationale: str = ""

    def as_metrics(self) -> dict[str, float]:
        """Return only the numeric axes, keyed by metric name."""
        return {
            FAITHFULNESS: self.faithfulness,
            RELEVANCE: self.relevance,
            NOT_HALLUCINATED: self.not_hallucinated,
        }


@runtime_checkable
class Judge(Protocol):
    """Anything that can score an answer against a question and references."""

    def score(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        reference: str,
    ) -> JudgeScores:
        """Grade one answer. See :class:`JudgeScores` for the axes."""
        ...


def _clamp01(value: float) -> float:
    """Clamp a score into the [0, 1] range."""
    return max(0.0, min(1.0, value))


class MockJudge:
    """Deterministic judge derived from simple text overlap. No LLM.

    The scores are heuristic, not accurate in absolute terms — but they are
    *stable* and they *discriminate*: a relevant, grounded answer scores higher
    than an off-topic or fabricated one, every time, on any machine. That is
    exactly what CI and tests need. The rationale spells out the derivation so
    the numbers are never a black box.

    Derivation:
        * relevance ≈ overlap of the answer with the question + reference.
        * faithfulness ≈ overlap of the answer with the retrieved contexts
          (falling back to the reference when no contexts are supplied, so
          retrieval-free systems are still judged on substance).
        * not_hallucinated ≈ how much of the answer is anchored in *some*
          trusted source (contexts or reference); an answer full of tokens that
          appear nowhere trusted reads as fabricated.
    """

    def score(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        reference: str,
    ) -> JudgeScores:
        if not answer.strip():
            return JudgeScores(0.0, 0.0, 0.0, rationale="empty answer")

        # Relevance: does the answer track the question and its known answer?
        relevance = _clamp01(
            0.5 * overlap_fraction(answer, question)
            + 0.5 * overlap_fraction(answer, reference)
        )

        # Faithfulness: is the answer supported by what was retrieved?
        if contexts:
            faithfulness = overlap_fraction(answer, contexts)
        else:
            faithfulness = overlap_fraction(answer, reference)

        # Hallucination: fraction of the answer NOT anchored in any trusted
        # source. Trusted = retrieved contexts plus the reference.
        trusted = list(contexts) + [reference]
        anchored = overlap_fraction(answer, trusted)
        not_hallucinated = _clamp01(anchored)

        rationale = (
            f"overlap-based mock: relevance={relevance:.2f}, "
            f"faithfulness={faithfulness:.2f}, not_hallucinated={not_hallucinated:.2f}; "
            f"answer content tokens={len(content_tokens(answer))}, "
            f"contexts={len(contexts)}"
        )
        return JudgeScores(
            faithfulness=_clamp01(faithfulness),
            relevance=relevance,
            not_hallucinated=not_hallucinated,
            rationale=rationale,
        )


# Default Claude model for the real judge. Overridable via env var so upgrades
# need no code change.
_DEFAULT_JUDGE_MODEL = "claude-sonnet-5"
_MODEL_ENV_VAR = "AGENT_EVAL_JUDGE_MODEL"

_RUBRIC = """\
You are a strict evaluation judge for question-answering systems. Score the \
ANSWER on three axes, each a float from 0.0 to 1.0 where higher is better:

- faithfulness: Is every claim in the ANSWER supported by the CONTEXTS? If the \
  answer asserts things not present in the contexts, lower this score.
- relevance: Does the ANSWER actually address the QUESTION? Off-topic or evasive \
  answers ("I don't know") score low.
- not_hallucinated: 1.0 means nothing is fabricated; 0.0 means the answer \
  invents facts. Judge against the CONTEXTS and the REFERENCE.

Respond with ONLY a JSON object, no prose, no code fences, in exactly this shape:
{"faithfulness": <float>, "relevance": <float>, "not_hallucinated": <float>, "rationale": "<one short sentence>"}
"""


class AnthropicJudge:
    """LLM-as-judge backed by Claude. Opt-in; the SDK is imported lazily.

    Requires ``ANTHROPIC_API_KEY`` in the environment and the ``anthropic``
    extra installed (``pip install agent-eval-kit[anthropic]``). The model is
    read from the ``AGENT_EVAL_JUDGE_MODEL`` env var, defaulting to a current
    Claude model.
    """

    def __init__(self, model: str | None = None, client: object | None = None) -> None:
        self.model = model or os.environ.get(_MODEL_ENV_VAR, _DEFAULT_JUDGE_MODEL)
        self._client = client  # injectable for testing; otherwise built lazily

    def _get_client(self) -> object:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on optional extra
                raise RuntimeError(
                    "AnthropicJudge requires the 'anthropic' package. Install it with "
                    "`pip install agent-eval-kit[anthropic]`, or use the default mock judge."
                ) from exc
            self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        return self._client

    def score(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        reference: str,
    ) -> JudgeScores:
        client = self._get_client()
        prompt = self._build_prompt(question, answer, contexts, reference)

        message = client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=512,
            system=_RUBRIC,
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(message)
        return self._parse(text)

    @staticmethod
    def _build_prompt(
        question: str, answer: str, contexts: list[str], reference: str
    ) -> str:
        joined_contexts = "\n".join(f"- {c}" for c in contexts) if contexts else "(none)"
        return (
            f"QUESTION:\n{question}\n\n"
            f"CONTEXTS:\n{joined_contexts}\n\n"
            f"REFERENCE ANSWER:\n{reference}\n\n"
            f"ANSWER TO JUDGE:\n{answer}\n"
        )

    @staticmethod
    def _parse(text: str) -> JudgeScores:
        payload = _extract_json_object(text)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"judge did not return valid JSON: {text!r}") from exc

        try:
            return JudgeScores(
                faithfulness=_clamp01(float(data["faithfulness"])),
                relevance=_clamp01(float(data["relevance"])),
                not_hallucinated=_clamp01(float(data["not_hallucinated"])),
                rationale=str(data.get("rationale", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"judge JSON missing/invalid fields: {payload!r}") from exc


def _extract_text(message: object) -> str:
    """Pull the text out of an Anthropic Messages API response."""
    content = getattr(message, "content", None)
    if not content:
        return ""
    parts = [getattr(block, "text", "") for block in content]
    return "".join(parts).strip()


def _extract_json_object(text: str) -> str:
    """Best-effort extraction of the first ``{...}`` block from model output.

    Guards against a model that wraps JSON in prose or code fences despite the
    rubric asking for bare JSON.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


def make_judge(name: str) -> Judge:
    """Factory: build a judge by name (``"mock"`` or ``"anthropic"``)."""
    normalized = name.strip().casefold()
    if normalized == "mock":
        return MockJudge()
    if normalized == "anthropic":
        return AnthropicJudge()
    raise ValueError(f"unknown judge {name!r}; expected 'mock' or 'anthropic'")
