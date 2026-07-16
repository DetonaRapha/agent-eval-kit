# DESIGN — agent-eval-kit

A light RFC for why the kit is shaped the way it is. One page. The interesting
part is not what it does but what it deliberately does *not* do.

## Context: evaluating an agent is not testing software

Normal software testing rests on determinism: input X must produce output Y, so
you assert equality and move on. LLM systems violate that at the core. The same
question yields different wording every time, and "different" is not "wrong" — a
paraphrase can be perfectly correct. `assert answer == expected` therefore either
flakes constantly or, softened into a substring check, tests almost nothing.

Quality of a non-deterministic system has to be *measured*, not asserted: score
each answer against a rubric, aggregate over a representative dataset, and gate on
the aggregate. That reframes evaluation as a testing layer — a CI-grade quality
gate — rather than an exploratory notebook. Everything below follows from taking
that reframing seriously on a small surface.

## Decision

**1. Mock-judge-first.** The default judge is deterministic and LLM-free,
deriving scores from text overlap. This is the load-bearing decision. It means
the entire kit — including the "does eval discriminate quality?" test — runs with
no API key, no network, and identical output on any machine. The real Claude
judge is an opt-in upgrade behind an environment variable and an optional
dependency, never a requirement to demonstrate or test the kit. Reproducibility
is the default; the LLM is the enhancement.

**2. Decoupled SUT contract.** The system under test is any callable
`question -> SUTResult`. The kit knows nothing about its internals — retrieval,
prompting, model choice are all opaque. This one-way contract is what makes the
kit reusable across a RAG, an agent, or a bare LLM call without modification, and
it is why `--sut module:function` can point at arbitrary user code.

**3. Deterministic metrics *and* a judge, not one or the other.** Deterministic
metrics (exact match, keyword recall, groundedness proxy) are cheap, fast, and
utterly stable, but blind to meaning — they can't tell whether an answer is
*faithful* or merely word-overlapping. The judge captures the semantic axes the
metrics miss. Neither is sufficient alone; the scorecard reports both and
thresholds any of them.

**4. The threshold verdict is the product.** Aggregating scores is a report;
comparing them to thresholds and exiting non-zero is a *test*. The pass/fail
verdict surfaced as a process exit code is what lets the kit block bad output in
CI — that is the difference between a dashboard and a quality gate.

## Alternatives considered

- **Use Ragas / DeepEval off the shelf.** Mature and feature-rich, but they pull
  in heavy dependencies, assume an LLM is always available, and hide the scoring
  logic behind abstractions. For a kit whose whole point is to *demonstrate*
  rigorous, reproducible eval on a small surface, an opaque dependency undercuts
  the message. Rolling a minimal core keeps the scoring auditable and the demo
  runnable with zero setup. (If this grew past v0, adopting one of them as an
  optional judge backend would be the natural move — the SUT/judge contracts are
  designed to allow it.)

- **Deterministic metrics only, no judge at all.** Fully reproducible and
  dependency-free, but it can't measure faithfulness or hallucination in any
  meaningful sense — the exact axes that matter most for LLM output. That throws
  away the hardest and most valuable half of the problem.

- **LLM judge only, no mock.** Simpler code, but every clone, test, and CI run
  would need an API key and network, and results would drift run to run. That
  fails the reproducibility bar the whole project is trying to model.

## Tradeoff — what was chosen and what was given up

The choice is **control, reproducibility, and pedagogy over out-of-the-box
breadth**. The mock judge's scores are heuristic and not accurate in absolute
terms — they are stable and *discriminating*, which is what a quality gate needs,
but they are not a substitute for the real judge's semantic understanding.
Deterministic metrics are shallow by construction. And by staying dependency-free
in the core, the kit reimplements a sliver of what mature frameworks already
offer.

What is bought with those concessions: a repo that clones and runs in one
command, a test suite that proves the eval discriminates good from bad without any
external service, and scoring logic small enough to read top to bottom. On a v0
whose job is to prove the *idea* of eval-as-a-testing-layer, that trade is the
point — sophistication here is clarity and rigor on a small surface, not size.
The "why not the other way" above is the actual deliverable.
