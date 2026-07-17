"""Tests for the Trilha B features: second provider, persistence, large-dataset
controls, concurrency/cache, and the HTML report. All offline and deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_eval import cli
from agent_eval.datasets import (
    Example,
    iter_golden,
    load_golden,
    sample_dataset,
)
from agent_eval.judges import CachingJudge, JudgeScores, MockJudge, OpenAIJudge, make_judge
from agent_eval.runner import evaluate
from agent_eval.store import Regression, compare_runs, load_run, save_run
from agent_eval.sut import SUTResult

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
GOLDEN = str(EXAMPLES_DIR / "golden.jsonl")


def _good_sut(question: str) -> SUTResult:
    return SUTResult(
        answer="Adults should aim for 7 to 9 hours of sleep per night.",
        contexts=["Adults should aim for 7 to 9 hours of sleep per night for good health."],
        latency_ms=5.0,
    )


# --- B1: OpenAIJudge + factory -----------------------------------------------


class _FakeChatMessage:
    def __init__(self, content: str) -> None:
        self.message = type("M", (), {"content": content})()


class _FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = type(
            "C",
            (),
            {
                "create": lambda _self, **kw: type(
                    "R", (), {"choices": [_FakeChatMessage(content)]}
                )()
            },
        )()


class _FakeOpenAIClient:
    def __init__(self, content: str) -> None:
        self.chat = _FakeChat(content)


def test_openai_judge_parses_response():
    payload = '{"faithfulness": 0.7, "relevance": 0.6, "not_hallucinated": 0.9}'
    judge = OpenAIJudge(model="test", client=_FakeOpenAIClient(payload))
    scores = judge.score("q", "a", ["ctx"], "ref")
    assert scores.faithfulness == 0.7
    assert scores.relevance == 0.6
    assert scores.not_hallucinated == 0.9


def test_make_judge_supports_openai_and_rejects_unknown():
    assert isinstance(make_judge("openai"), OpenAIJudge)
    assert isinstance(make_judge("mock"), MockJudge)
    with pytest.raises(ValueError, match="unknown judge"):
        make_judge("cohere")


# --- B4: CachingJudge --------------------------------------------------------


class _CountingJudge:
    def __init__(self) -> None:
        self.calls = 0

    def score(self, question, answer, contexts, reference):
        self.calls += 1
        return JudgeScores(1.0, 1.0, 1.0, rationale="counted")


def test_caching_judge_memoizes_identical_inputs():
    inner = _CountingJudge()
    judge = CachingJudge(inner)
    args = ("q", "a", ["c"], "ref")
    first = judge.score(*args)
    second = judge.score(*args)
    assert first == second
    assert inner.calls == 1  # second call served from cache


def test_caching_judge_distinguishes_inputs():
    inner = _CountingJudge()
    judge = CachingJudge(inner)
    judge.score("q1", "a", [], "ref")
    judge.score("q2", "a", [], "ref")
    assert inner.calls == 2


# --- B4: concurrency ---------------------------------------------------------


def test_concurrency_matches_sequential():
    dataset = load_golden(GOLDEN)
    judge = MockJudge()
    seq = evaluate(_good_sut, dataset, judge, {}, concurrency=1)
    par = evaluate(_good_sut, dataset, judge, {}, concurrency=4)
    assert par.aggregate == seq.aggregate
    assert [r["question"] for r in par.per_item] == [r["question"] for r in seq.per_item]


def test_concurrency_must_be_positive():
    dataset = load_golden(GOLDEN)
    with pytest.raises(ValueError, match="concurrency"):
        evaluate(_good_sut, dataset, MockJudge(), {}, concurrency=0)


# --- B3: large-dataset controls ----------------------------------------------


def test_load_golden_limit():
    assert len(load_golden(GOLDEN, limit=3)) == 3


def test_load_golden_rejects_nonpositive_limit():
    with pytest.raises(ValueError, match="limit"):
        load_golden(GOLDEN, limit=0)


def test_iter_golden_is_lazy_and_complete():
    items = list(iter_golden(GOLDEN))
    assert all(isinstance(e, Example) for e in items)
    assert len(items) == len(load_golden(GOLDEN))


def test_sample_dataset_is_deterministic():
    dataset = load_golden(GOLDEN)
    a = sample_dataset(dataset, 4, seed=42)
    b = sample_dataset(dataset, 4, seed=42)
    assert len(a) == 4
    assert [e.question for e in a] == [e.question for e in b]


def test_sample_dataset_full_when_n_exceeds_size():
    dataset = load_golden(GOLDEN)
    assert len(sample_dataset(dataset, len(dataset) + 5)) == len(dataset)


def test_sample_dataset_rejects_nonpositive():
    dataset = load_golden(GOLDEN)
    with pytest.raises(ValueError, match="sample size"):
        sample_dataset(dataset, 0)


# --- B2: persistence + regression --------------------------------------------


def test_save_and_load_run_roundtrip(tmp_path: Path):
    dataset = load_golden(GOLDEN)
    card = evaluate(_good_sut, dataset, MockJudge(), {})
    path = save_run(card, str(tmp_path), "baseline")
    assert path.endswith("baseline.json")
    loaded = load_run(path)
    assert loaded["relevance"] == pytest.approx(card.aggregate["relevance"])


def test_load_run_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_run(str(tmp_path / "nope.json"))


def test_compare_runs_detects_drop():
    baseline = {"relevance": 0.8, "faithfulness": 0.9, "latency_ms": 10.0}
    current = {"relevance": 0.6, "faithfulness": 0.95, "latency_ms": 999.0}
    regressions = compare_runs(baseline, current)
    metrics = {r.metric for r in regressions}
    assert metrics == {"relevance"}  # faithfulness improved; latency is ignored
    assert regressions[0] == Regression("relevance", 0.8, 0.6)


def test_compare_runs_respects_tolerance():
    baseline = {"relevance": 0.80}
    current = {"relevance": 0.78}
    assert compare_runs(baseline, current, tolerance=0.05) == []
    assert compare_runs(baseline, current, tolerance=0.0)


# --- B5: HTML report ---------------------------------------------------------


def test_html_report_contains_verdict_and_metrics():
    dataset = load_golden(GOLDEN)
    card = evaluate(_good_sut, dataset, MockJudge(), {"relevance": 0.0})
    html_out = card.to_html()
    assert "<!doctype html>" in html_out.lower()
    assert "PASS" in html_out
    assert "relevance" in html_out


def test_html_report_escapes_question(tmp_path: Path):
    path = tmp_path / "d.jsonl"
    path.write_text(
        json.dumps({"question": "<script>x</script>", "reference": "r"}) + "\n",
        encoding="utf-8",
    )
    card = evaluate(_good_sut, load_golden(str(path)), MockJudge(), {})
    html_out = card.to_html()
    assert "<script>x</script>" not in html_out
    assert "&lt;script&gt;" in html_out


# --- CLI wiring for the new flags --------------------------------------------


def test_cli_limit_and_reports(tmp_path: Path):
    out = tmp_path / "out"
    code = cli.main(
        [
            "--dataset",
            GOLDEN,
            "--sut",
            "examples.tiny_rag:answer",
            "--limit",
            "5",
            "--report",
            str(out),
        ]
    )
    assert code == 0
    assert (out / "report.html").exists()


def test_cli_baseline_regression_fails(tmp_path: Path):
    runs = tmp_path / "runs"
    # Baseline from the stronger SUT.
    cli.main(
        [
            "--dataset",
            GOLDEN,
            "--sut",
            "examples.better_rag:answer",
            "--no-default-thresholds",
            "--save-run",
            str(runs),
            "--run-name",
            "base",
        ]
    )
    # The weaker SUT should regress against it and fail.
    code = cli.main(
        [
            "--dataset",
            GOLDEN,
            "--sut",
            "examples.tiny_rag:answer",
            "--no-default-thresholds",
            "--baseline",
            str(runs / "base.json"),
        ]
    )
    assert code == 1
