"""The runner — the orchestration core.

For each example it calls the system under test, computes the deterministic
metrics, asks the judge for its verdict, and collects a per-item row. Then it
averages every 0..1 metric into an aggregate and asks whether that aggregate
clears the thresholds. The result is a :class:`~agent_eval.scorecard.Scorecard`.
"""

from __future__ import annotations

from collections.abc import Mapping

from agent_eval import metrics as m
from agent_eval.datasets import Example
from agent_eval.judges import Judge
from agent_eval.scorecard import LATENCY_KEY, Scorecard
from agent_eval.sut import SUT

# Deterministic metric functions, keyed by the name they report under.
_DETERMINISTIC = {
    m.EXACT_MATCH: m.exact_match,
    m.KEYWORD_RECALL: m.keyword_recall,
    m.GROUNDEDNESS_PROXY: m.groundedness_proxy,
}


def evaluate(
    sut: SUT,
    dataset: list[Example],
    judge: Judge,
    thresholds: Mapping[str, float],
) -> Scorecard:
    """Run ``sut`` over ``dataset``, grade each item, and aggregate.

    Args:
        sut: The system under test — any callable ``question -> SUTResult``.
        dataset: The golden examples to evaluate against.
        judge: The judge providing faithfulness/relevance/hallucination scores.
        thresholds: Minimum acceptable mean per metric. Metrics not listed are
            reported but do not affect the pass/fail verdict.

    Returns:
        A populated :class:`Scorecard`.

    Raises:
        ValueError: If ``dataset`` is empty.
    """
    if not dataset:
        raise ValueError("cannot evaluate an empty dataset")

    per_item = [_evaluate_one(sut, judge, example) for example in dataset]
    aggregate = _aggregate(per_item)
    thresholds = dict(thresholds)
    passed = _verdict(aggregate, thresholds)

    return Scorecard(
        per_item=per_item,
        aggregate=aggregate,
        thresholds=thresholds,
        passed=passed,
    )


def _evaluate_one(sut: SUT, judge: Judge, example: Example) -> dict:
    """Evaluate a single example into one per-item row."""
    result = sut(example.question)

    row: dict[str, object] = {"question": example.question}

    for name, fn in _DETERMINISTIC.items():
        row[name] = fn(result, example)

    scores = judge.score(
        question=example.question,
        answer=result.answer,
        contexts=result.contexts,
        reference=example.reference,
    )
    row.update(scores.as_metrics())
    row["rationale"] = scores.rationale
    row[LATENCY_KEY] = result.latency_ms

    return row


def _aggregate(per_item: list[dict]) -> dict[str, float]:
    """Mean of every numeric 0..1 metric across items.

    Latency is excluded from the 0..1 aggregate and averaged separately so it
    stays reportable without polluting the score space.
    """
    if not per_item:
        return {}

    score_keys = [
        key
        for key, value in per_item[0].items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        and key != LATENCY_KEY
    ]

    aggregate = {
        key: sum(float(item[key]) for item in per_item) / len(per_item)
        for key in score_keys
    }
    aggregate[LATENCY_KEY] = sum(
        float(item[LATENCY_KEY]) for item in per_item
    ) / len(per_item)
    return aggregate


def _verdict(aggregate: Mapping[str, float], thresholds: Mapping[str, float]) -> bool:
    """True when every thresholded metric meets or exceeds its bar.

    An empty threshold set means "report only": the run passes. A threshold on a
    metric that was never produced fails safe (treated as 0.0).
    """
    return all(
        aggregate.get(metric, 0.0) >= minimum
        for metric, minimum in thresholds.items()
    )
