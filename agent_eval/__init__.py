"""agent-eval-kit — automated, reproducible quality evaluation for LLM systems.

Point it at anything that answers a question (a RAG, an agent, a bare LLM call)
and it returns a scorecard: faithfulness, relevance, hallucination detection,
and deterministic metrics — with a pass/fail verdict against thresholds.

The public surface is intentionally small. The core runs with zero third-party
dependencies via a deterministic mock judge; the real Claude judge is opt-in.
"""

from __future__ import annotations

from agent_eval.datasets import Example, load_golden
from agent_eval.judges import AnthropicJudge, Judge, JudgeScores, MockJudge
from agent_eval.runner import evaluate
from agent_eval.scorecard import Scorecard
from agent_eval.sut import SUT, SUTResult

__version__ = "0.1.0"

__all__ = [
    "Example",
    "load_golden",
    "SUT",
    "SUTResult",
    "Judge",
    "JudgeScores",
    "MockJudge",
    "AnthropicJudge",
    "evaluate",
    "Scorecard",
    "__version__",
]
