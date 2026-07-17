"""Tests for the previously-'Future' features: Gemini judge, dataset adapters,
SQLite persistence, and the static multi-run dashboard. All offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_eval import dashboard
from agent_eval.adapters import from_csv, from_records
from agent_eval.datasets import Example
from agent_eval.judges import GeminiJudge, make_judge
from agent_eval.scorecard import Scorecard
from agent_eval.store import (
    list_runs_sqlite,
    load_run_sqlite,
    save_run_sqlite,
)

# --- Gemini provider ---------------------------------------------------------


class _FakeGeminiResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeGeminiModel:
    def __init__(self, text: str) -> None:
        self._text = text

    def generate_content(self, prompt: str) -> _FakeGeminiResponse:
        return _FakeGeminiResponse(self._text)


def test_gemini_judge_parses_response():
    payload = '{"faithfulness": 0.4, "relevance": 0.5, "not_hallucinated": 0.6}'
    judge = GeminiJudge(model="test", client=_FakeGeminiModel(payload))
    scores = judge.score("q", "a", ["ctx"], "ref")
    assert (scores.faithfulness, scores.relevance, scores.not_hallucinated) == (0.4, 0.5, 0.6)


def test_make_judge_supports_gemini():
    assert isinstance(make_judge("gemini"), GeminiJudge)


# --- Dataset adapters --------------------------------------------------------


def test_from_records_maps_default_keys():
    records = [{"question": "q1", "reference": "r1"}, {"question": "q2", "reference": "r2"}]
    examples = from_records(records)
    assert [e.question for e in examples] == ["q1", "q2"]
    assert all(isinstance(e, Example) for e in examples)


def test_from_records_custom_keys_and_lists():
    records = [{"q": "question?", "a": "answer", "terms": ["x", "y"], "ctx": "one context"}]
    examples = from_records(
        records,
        question_key="q",
        reference_key="a",
        must_include_key="terms",
        contexts_key="ctx",
    )
    ex = examples[0]
    assert ex.question == "question?"
    assert ex.reference == "answer"
    assert ex.must_include == ["x", "y"]
    assert ex.contexts == ["one context"]  # single string coerced to a list


def test_from_records_rejects_missing_field():
    with pytest.raises(ValueError, match="reference"):
        from_records([{"question": "q only"}])


def test_from_csv_splits_list_columns(tmp_path: Path):
    path = tmp_path / "data.csv"
    path.write_text(
        "question,reference,must_include\nWhat is X?,X is a thing,x;thing\n",
        encoding="utf-8",
    )
    examples = from_csv(str(path), must_include_key="must_include")
    assert len(examples) == 1
    assert examples[0].must_include == ["x", "thing"]


# --- SQLite persistence ------------------------------------------------------


def _card(passed: bool = True) -> Scorecard:
    return Scorecard(
        per_item=[],
        aggregate={"relevance": 0.7, "faithfulness": 0.8},
        thresholds={},
        passed=passed,
    )


def test_sqlite_roundtrip(tmp_path: Path):
    db = str(tmp_path / "runs.db")
    save_run_sqlite(_card(), db, "baseline")
    loaded = load_run_sqlite(db, "baseline")
    assert loaded == {"relevance": 0.7, "faithfulness": 0.8}


def test_sqlite_overwrites_same_name(tmp_path: Path):
    db = str(tmp_path / "runs.db")
    save_run_sqlite(_card(), db, "r")
    save_run_sqlite(
        Scorecard(per_item=[], aggregate={"relevance": 0.1}, thresholds={}, passed=False),
        db,
        "r",
    )
    assert load_run_sqlite(db, "r") == {"relevance": 0.1}
    assert list_runs_sqlite(db) == [("r", False)]


def test_sqlite_missing_name_raises(tmp_path: Path):
    db = str(tmp_path / "runs.db")
    save_run_sqlite(_card(), db, "exists")
    with pytest.raises(KeyError):
        load_run_sqlite(db, "nope")


def test_sqlite_missing_db(tmp_path: Path):
    assert list_runs_sqlite(str(tmp_path / "absent.db")) == []
    with pytest.raises(FileNotFoundError):
        load_run_sqlite(str(tmp_path / "absent.db"), "x")


# --- Static dashboard --------------------------------------------------------


def _write_run(directory: Path, name: str, passed: bool, aggregate: dict[str, float]) -> None:
    (directory / f"{name}.json").write_text(
        json.dumps({"passed": passed, "aggregate": aggregate}), encoding="utf-8"
    )


def test_dashboard_lists_runs(tmp_path: Path):
    _write_run(tmp_path, "alpha", True, {"relevance": 0.6})
    _write_run(tmp_path, "beta", False, {"relevance": 0.3})
    html_out = dashboard.build_dashboard(str(tmp_path))
    assert "alpha" in html_out and "beta" in html_out
    assert "PASS" in html_out and "FAIL" in html_out
    assert "relevance" in html_out


def test_dashboard_empty_dir(tmp_path: Path):
    html_out = dashboard.build_dashboard(str(tmp_path))
    assert "No runs" in html_out


def test_dashboard_skips_malformed(tmp_path: Path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    _write_run(tmp_path, "ok", True, {"relevance": 0.5})
    html_out = dashboard.build_dashboard(str(tmp_path))
    assert "ok" in html_out
    assert "broken" not in html_out


def test_dashboard_cli_writes_file(tmp_path: Path):
    _write_run(tmp_path, "run1", True, {"relevance": 0.9})
    out = tmp_path / "dash.html"
    code = dashboard.main([str(tmp_path), "-o", str(out)])
    assert code == 0
    assert out.exists()
    assert "run1" in out.read_text(encoding="utf-8")
