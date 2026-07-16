# agent-eval-kit

Point it at anything that answers a question — a RAG, an agent, a bare LLM call —
and get back a **quality scorecard** (faithfulness, relevance, hallucination
detection, plus deterministic metrics) with a **pass/fail verdict** you can wire
straight into CI.

## Why this exists

Traditional testing assumes a deterministic output: given input X, assert the
result equals Y. LLM systems break that assumption — the same prompt yields
different, non-verbatim answers, all potentially correct. `assert answer == "..."`
either flakes or tests nothing.

So quality needs *evaluation*, not equality: score each answer on rubric-style
axes, aggregate across a golden dataset, and fail the run when quality drops
below a threshold. That is what this kit does, and it treats eval as a
first-class testing layer rather than a one-off notebook.

## The approach in three lines

1. Load a **golden dataset** (questions + reference answers) and run the system
   under test on each item.
2. Score every answer with **deterministic metrics** (no LLM) and an
   **LLM-as-judge** (faithfulness / relevance / not-hallucinated).
3. Aggregate into a **scorecard**, compare against thresholds, emit Markdown +
   JSON, and exit non-zero if quality is below bar.

## Mock-judge-first

By default the kit runs with a **deterministic mock judge** — no API key, no
network, identical results everywhere. Clone, one command, green CI. Flip on the
real Claude judge with an environment variable when you want it. Reproducibility
is the default; the LLM is the upgrade.

## Run it

```bash
# Deterministic mock judge — no API key needed.
python -m agent_eval \
  --dataset examples/golden.jsonl \
  --sut examples.tiny_rag:answer \
  --judge mock \
  --report out/
```

`--sut` is a `module:function` reference imported dynamically, so you can point
the kit at your own system without touching its code. The command prints a
scorecard, writes `out/report.md` and `out/report.json`, and exits `0` on pass /
`1` on fail — ready for CI.

### Turn on the real Claude judge (optional)

```bash
pip install "agent-eval-kit[anthropic]"
export ANTHROPIC_API_KEY=sk-...            # never commit this
python -m agent_eval --dataset examples/golden.jsonl \
  --sut examples.tiny_rag:answer --judge anthropic
```

The model defaults to a current Claude model and is overridable with
`AGENT_EVAL_JUDGE_MODEL`. The `anthropic` SDK is an optional extra — it is never
required to run the kit.

## Metrics

Every score is `0..1`, **higher is better**. Latency is reported, not scored.

| Metric | What it measures |
| --- | --- |
| `exact_match` | 1 if the normalized answer equals the normalized reference. |
| `keyword_recall` | Fraction of required `must_include` terms present in the answer. |
| `groundedness_proxy` | Fraction of answer content tokens found in the retrieved contexts — a cheap, no-LLM hallucination proxy. |
| `faithfulness` (judge) | Is the answer supported by the retrieved contexts? |
| `relevance` (judge) | Does the answer actually address the question? |
| `not_hallucinated` (judge) | 1 = nothing fabricated, 0 = invented content. |
| `latency_ms` | Wall-clock time reported by the SUT (reported, not scored). |

## Design decisions

The architecture and the "why not do it another way" reasoning live in
[DESIGN.md](DESIGN.md): mock-judge-first, a decoupled SUT contract, and
deterministic metrics alongside the judge.

## Result

A run against the deliberately-naive `examples/tiny_rag` SUT:

```
Scorecard - PASS (6 example(s))
------------------------------------------------
  faithfulness            1.000   >= 0.250  [ok ]
  keyword_recall          0.667   >= 0.400  [ok ]
  not_hallucinated        1.000   >= 0.250  [ok ]
  relevance               0.436   >= 0.250  [ok ]
  exact_match             0.333   (no threshold)
  groundedness_proxy      1.000   (no threshold)
  latency_ms              0.000   (no threshold)
------------------------------------------------
```

The example SUT is a keyword-overlap "RAG" that parrots the best-matching
document. It is mediocre **on purpose**: notice how it scores `relevance` 0.68 on
the sleep question it can answer, but `0.00` on the vitamin-D question outside its
knowledge base. That localized drop is the eval catching a weakness — a perfect
SUT would prove nothing about the kit.

## Future (out of scope for v0, on purpose)

v0 is the smallest complete slice that runs end-to-end. Deliberately deferred:

- Web UI / dashboard.
- Persistence / a results database.
- Multiple LLM provider backends.
- Large datasets or public benchmarks.
- Concurrency, caching, and cost optimization.

## Development

```bash
pip install -e ".[dev]"
pytest
```

The test suite runs entirely on the mock judge — no network, no key — and its
most important test asserts that a knowingly bad SUT scores *lower* than a decent
one. If eval can't tell good from bad, it isn't eval.

## License

MIT — see [LICENSE](LICENSE).
