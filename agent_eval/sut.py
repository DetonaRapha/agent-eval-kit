"""The System Under Test (SUT) contract.

A SUT is anything that answers a question. The kit knows nothing about its
internals — it calls ``sut(question)`` and reads back a :class:`SUTResult`. That
one-way contract is what makes the kit reusable across RAGs, agents, and bare
LLM calls alike.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class SUTResult:
    """What a system under test returns for a single question.

    Attributes:
        answer: The system's answer text.
        contexts: Snippets the system retrieved or otherwise used to answer.
            Empty for systems that do no retrieval; groundedness metrics then
            simply report 0.
        latency_ms: Wall-clock time the system took, in milliseconds. Reported
            alongside scores, not scored itself.
    """

    answer: str
    contexts: list[str] = field(default_factory=list)
    latency_ms: float = 0.0


# A SUT is any callable mapping a question to a SUTResult.
SUT = Callable[[str], SUTResult]
