"""Tests that prove the kit is a quality layer, not decoration.

Everything here runs with the deterministic MockJudge: no network, no API key,
same result on every machine. The centerpiece is ``test_eval_discriminates_
quality`` — if a knowingly bad SUT did not score lower than a decent one, the
whole exercise would be theatre.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_eval import cli
from agent_eval.datasets import DatasetError, Example, load_golden
from agent_eval.judges import MockJudge
from agent_eval.metrics import DETERMINISTIC_METRICS
from agent_eval.judges import JUDGE_METRICS
from agent_eval.runner import evaluate
from agent_eval.sut import SUTResult

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
GOLDEN = str(EXAMPLES_DIR / "golden.jsonl")


# --- Fixtures / helpers -------------------------------------------------------


def _good_sut(question: str) -> SUTResult:
    """A decent SUT: answers on-topic and grounded in a matching context."""
    context = "Adults should aim for 7 to 9 hours of sleep per night for good health."
    return SUTResult(
        answer="Adults should aim for 7 to 9 hours of sleep per night.",
        contexts=[context],
        latency_ms=12.0,
    )


def _bad_sut(question: str) -> SUTResult:
    """A knowingly bad SUT: off-topic, evasive, ungrounded."""
    return SUTResult(answer="I don't know, sorry.", contexts=[], latency_ms=1.0)


@pytest.fixture
def sleep_example() -> Example:
    return Example(
        question="How many hours of sleep should adults aim for each night?",
        reference="Adults should aim for 7 to 9 hours of sleep per night.",
        must_include=["7", "9", "sleep"],
    )


# --- Dataset loading ----------------------------------------------------------


def test_load_golden_reads_all_examples():
    dataset = load_golden(GOLDEN)
    assert len(dataset) == 6
    assert all(isinstance(ex, Example) for ex in dataset)
    assert all(ex.question and ex.reference for ex in dataset)


def test_load_golden_skips_blank_lines(tmp_path: Path):
    path = tmp_path / "d.jsonl"
    path.write_text(
        '{"question": "q1", "reference": "r1"}\n'
        "\n"
        '   \n'
        '{"question": "q2", "reference": "r2"}\n',
        encoding="utf-8",
    )
    assert len(load_golden(str(path))) == 2


def test_load_golden_rejects_missing_fields(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"question": "q only"}\n', encoding="utf-8")
    with pytest.raises(DatasetError, match="reference"):
        load_golden(str(path))


def test_load_golden_rejects_empty_file(tmp_path: Path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n\n", encoding="utf-8")
    with pytest.raises(DatasetError, match="no examples"):
        load_golden(str(path))


# --- Test 1: the pipeline runs and produces every expected metric key ---------


def test_pipeline_runs_and_has_all_metric_keys():
    dataset = load_golden(GOLDEN)
    card = evaluate(_good_sut, dataset, MockJudge(), thresholds={})

    for metric in (*DETERMINISTIC_METRICS, *JUDGE_METRICS):
        assert metric in card.aggregate, f"missing aggregate metric {metric}"

    assert len(card.per_item) == len(dataset)
    assert "latency_ms" in card.aggregate
    # No thresholds => report-only => passes by definition.
    assert card.passed is True


# --- Test 2 (the important one): the eval discriminates quality ---------------


def test_eval_discriminates_quality():
    """A knowingly bad SUT must score lower than a decent one on the axes that
    matter: relevance and faithfulness. This is the repo's core claim."""
    dataset = load_golden(GOLDEN)
    judge = MockJudge()

    good = evaluate(_good_sut, dataset, judge, thresholds={})
    bad = evaluate(_bad_sut, dataset, judge, thresholds={})

    assert bad.aggregate["relevance"] < good.aggregate["relevance"]
    assert bad.aggregate["faithfulness"] < good.aggregate["faithfulness"]


def test_offtopic_item_scores_lower_than_ontopic():
    """Within one run, an off-domain question the SUT cannot answer should score
    lower on relevance than one it can — the eval localizes the weakness."""
    from examples.tiny_rag import answer as tiny_rag

    dataset = load_golden(GOLDEN)
    card = evaluate(tiny_rag, dataset, MockJudge(), thresholds={})

    relevance_by_q = {row["question"]: row["relevance"] for row in card.per_item}
    ontopic = next(q for q in relevance_by_q if "sleep" in q.lower())
    offtopic = next(q for q in relevance_by_q if "vitamin d" in q.lower())

    assert relevance_by_q[offtopic] < relevance_by_q[ontopic]


# --- Test 3: threshold pass/fail logic ---------------------------------------


def test_thresholds_high_fails_low_passes():
    dataset = load_golden(GOLDEN)
    judge = MockJudge()

    strict = evaluate(_good_sut, dataset, judge, thresholds={"relevance": 0.99})
    assert strict.passed is False
    assert "relevance" in strict.failures()

    lenient = evaluate(_good_sut, dataset, judge, thresholds={"relevance": 0.01})
    assert lenient.passed is True
    assert lenient.failures() == {}


def test_threshold_on_missing_metric_fails_safe():
    dataset = load_golden(GOLDEN)
    card = evaluate(_good_sut, dataset, MockJudge(), thresholds={"nonexistent": 0.5})
    assert card.passed is False


def test_evaluate_rejects_empty_dataset():
    with pytest.raises(ValueError, match="empty dataset"):
        evaluate(_good_sut, [], MockJudge(), thresholds={})


# --- MockJudge behavior -------------------------------------------------------


def test_mock_judge_is_deterministic(sleep_example: Example):
    judge = MockJudge()
    args = (
        sleep_example.question,
        "Adults should aim for 7 to 9 hours of sleep per night.",
        ["Adults should aim for 7 to 9 hours of sleep per night for good health."],
        sleep_example.reference,
    )
    first = judge.score(*args)
    second = judge.score(*args)
    assert first == second


def test_mock_judge_empty_answer_scores_zero():
    scores = MockJudge().score("q", "", [], "ref")
    assert scores.faithfulness == 0.0
    assert scores.relevance == 0.0
    assert scores.not_hallucinated == 0.0


def test_mock_judge_scores_in_range():
    scores = MockJudge().score(
        "Why is water important?",
        "Water helps regulate body temperature.",
        ["Drinking water helps regulate body temperature and kidney function."],
        "Water regulates body temperature and supports kidney function.",
    )
    for value in scores.as_metrics().values():
        assert 0.0 <= value <= 1.0


# --- AnthropicJudge (no network: an injected fake client) ---------------------


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    def __init__(self, text: str) -> None:
        self._text = text
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeMessage(self._text)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self.messages = _FakeMessages(text)


def test_anthropic_judge_parses_json_response():
    from agent_eval.judges import AnthropicJudge

    payload = (
        '{"faithfulness": 0.9, "relevance": 0.8, '
        '"not_hallucinated": 1.0, "rationale": "grounded and on-topic"}'
    )
    judge = AnthropicJudge(model="test-model", client=_FakeClient(payload))
    scores = judge.score("q", "a", ["ctx"], "ref")

    assert scores.faithfulness == 0.9
    assert scores.relevance == 0.8
    assert scores.not_hallucinated == 1.0
    assert scores.rationale == "grounded and on-topic"


def test_anthropic_judge_tolerates_fenced_json():
    from agent_eval.judges import AnthropicJudge

    payload = (
        "Here you go:\n```json\n"
        '{"faithfulness": 0.5, "relevance": 0.5, "not_hallucinated": 0.5}\n'
        "```"
    )
    judge = AnthropicJudge(client=_FakeClient(payload))
    scores = judge.score("q", "a", [], "ref")
    assert scores.faithfulness == 0.5


def test_anthropic_judge_raises_on_garbage():
    from agent_eval.judges import AnthropicJudge

    judge = AnthropicJudge(client=_FakeClient("no json here"))
    with pytest.raises(ValueError):
        judge.score("q", "a", [], "ref")


# --- Reporting ----------------------------------------------------------------


def test_scorecard_json_roundtrips():
    dataset = load_golden(GOLDEN)
    card = evaluate(_good_sut, dataset, MockJudge(), thresholds={"relevance": 0.1})
    payload = json.loads(card.to_json())
    assert payload["passed"] is True
    assert "aggregate" in payload and "per_item" in payload
    assert len(payload["per_item"]) == len(dataset)


def test_scorecard_markdown_contains_verdict():
    dataset = load_golden(GOLDEN)
    card = evaluate(_good_sut, dataset, MockJudge(), thresholds={"relevance": 0.99})
    md = card.to_markdown()
    assert "# Evaluation Scorecard" in md
    assert "FAIL" in md


# --- CLI end-to-end -----------------------------------------------------------


def test_cli_end_to_end_writes_reports_and_exits_zero(tmp_path: Path):
    report_dir = tmp_path / "out"
    exit_code = cli.main(
        [
            "--dataset",
            GOLDEN,
            "--sut",
            "examples.tiny_rag:answer",
            "--judge",
            "mock",
            "--report",
            str(report_dir),
        ]
    )
    assert exit_code == 0
    assert (report_dir / "report.md").exists()
    assert (report_dir / "report.json").exists()


def test_cli_fails_run_when_thresholds_not_met():
    exit_code = cli.main(
        [
            "--dataset",
            GOLDEN,
            "--sut",
            "examples.tiny_rag:answer",
            "--threshold",
            "relevance=0.99",
        ]
    )
    assert exit_code == 1


def test_cli_reports_bad_sut_spec():
    exit_code = cli.main(
        ["--dataset", GOLDEN, "--sut", "not_a_module:nope"]
    )
    assert exit_code == 2
