"""Compare two systems on the same golden dataset.

Runs ``tiny_rag`` and ``better_rag`` through the kit with the deterministic mock
judge and prints their aggregate metrics side by side. This is the kit's core
value made visible: telling two systems apart on the same yardstick.

Run from the repo root:

    python -m examples.compare
"""

from __future__ import annotations

from agent_eval.datasets import load_golden
from agent_eval.judges import JUDGE_METRICS, MockJudge
from agent_eval.metrics import DETERMINISTIC_METRICS
from agent_eval.runner import evaluate
from examples.better_rag import answer as better_rag
from examples.tiny_rag import answer as tiny_rag

_DATASET = "examples/golden.jsonl"
_METRICS = (*DETERMINISTIC_METRICS, *JUDGE_METRICS)


def main() -> None:
    dataset = load_golden(_DATASET)
    judge = MockJudge()

    systems = {
        "tiny_rag": evaluate(tiny_rag, dataset, judge, thresholds={}),
        "better_rag": evaluate(better_rag, dataset, judge, thresholds={}),
    }

    header = f"{'metric':<20}" + "".join(f"{name:>14}" for name in systems)
    print(header)
    print("-" * len(header))
    for metric in _METRICS:
        row = f"{metric:<20}" + "".join(
            f"{card.aggregate[metric]:>14.3f}" for card in systems.values()
        )
        print(row)


if __name__ == "__main__":
    main()
