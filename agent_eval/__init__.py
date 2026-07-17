"""agent-eval-kit — automated, reproducible quality evaluation for LLM systems.

Point it at anything that answers a question (a RAG, an agent, a bare LLM call)
and it returns a scorecard: faithfulness, relevance, hallucination detection,
and deterministic metrics — with a pass/fail verdict against thresholds.

The public surface is intentionally small. The core runs with zero third-party
dependencies via a deterministic mock judge; the real Claude judge is opt-in.
"""

from __future__ import annotations

from agent_eval.datasets import Example, load_golden
from agent_eval.judges import AnthropicJudge, Judge, JudgeScores, MockJudge, OpenAIJudge
from agent_eval.runner import evaluate
from agent_eval.scorecard import Scorecard
from agent_eval.store import compare_runs, load_run, save_run
from agent_eval.sut import SUT, SUTResult

__version__ = "0.1.0"

__all__ = [
    "SUT",
    "AnthropicJudge",
    "Example",
    "Judge",
    "JudgeScores",
    "MockJudge",
    "OpenAIJudge",
    "SUTResult",
    "Scorecard",
    "__version__",
    "compare_runs",
    "evaluate",
    "load_golden",
    "load_run",
    "save_run",
]
