"""Persist evaluation runs and detect quality regressions between them.

The first useful step toward persistence is not a database — it is *versioned
run files on disk*. Save each run's scorecard as JSON, then compare two runs to
catch a metric that dropped between commits. That turns the kit from a one-shot
check into a regression guard.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from agent_eval.scorecard import LATENCY_KEY, Scorecard


def save_run(scorecard: Scorecard, directory: str, name: str) -> str:
    """Write a run's scorecard to ``<directory>/<name>.json`` and return the path.

    ``name`` is required and used verbatim (no timestamp is generated here) so
    that saving is deterministic and testable; callers that want a timestamped
    filename pass one in.
    """
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{name}.json"
    path.write_text(scorecard.to_json(), encoding="utf-8")
    return str(path)


def load_run(path: str) -> dict[str, float]:
    """Load the aggregate metrics of a saved run.

    Returns the ``aggregate`` mapping (metric -> mean). Raises if the file is
    missing or malformed, with a clear message.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not a valid run file: {exc.msg}") from exc

    aggregate = payload.get("aggregate")
    if not isinstance(aggregate, dict):
        raise ValueError(f"{path}: run file has no 'aggregate' section")
    return {str(k): float(v) for k, v in aggregate.items()}


def save_run_sqlite(scorecard: Scorecard, db_path: str, name: str) -> None:
    """Persist a run into a SQLite database (stdlib ``sqlite3``, no dependency).

    A file-based JSON run is fine for a couple of comparisons; once many runs
    accumulate, a small local database queries better. Rows are keyed by ``name``
    (re-saving the same name overwrites it). This is "database persistence"
    without adding a heavyweight dependency to the core.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS runs "
            "(name TEXT PRIMARY KEY, passed INTEGER NOT NULL, aggregate TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO runs (name, passed, aggregate) VALUES (?, ?, ?)",
            (name, int(scorecard.passed), json.dumps(scorecard.aggregate)),
        )


def load_run_sqlite(db_path: str, name: str) -> dict[str, float]:
    """Load a saved run's aggregate metrics from a SQLite database.

    Raises:
        KeyError: If no run with ``name`` exists.
        FileNotFoundError: If the database file does not exist.
    """
    if not Path(db_path).exists():
        raise FileNotFoundError(db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT aggregate FROM runs WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise KeyError(f"no run named {name!r} in {db_path}")
    return {str(k): float(v) for k, v in json.loads(row[0]).items()}


def list_runs_sqlite(db_path: str) -> list[tuple[str, bool]]:
    """Return ``(name, passed)`` for every run in the database, newest last."""
    if not Path(db_path).exists():
        return []
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name, passed FROM runs ORDER BY rowid").fetchall()
    return [(str(name), bool(passed)) for name, passed in rows]


@dataclass(frozen=True)
class Regression:
    """One metric that dropped from a baseline beyond the allowed tolerance."""

    metric: str
    baseline: float
    current: float

    @property
    def delta(self) -> float:
        """Signed change (current - baseline); negative means a drop."""
        return self.current - self.baseline


def compare_runs(
    baseline: dict[str, float],
    current: dict[str, float],
    tolerance: float = 0.0,
) -> list[Regression]:
    """Return metrics that regressed from ``baseline`` to ``current``.

    A metric regresses when ``current < baseline - tolerance``. Latency is
    skipped (it is not a 0..1 score and "higher is better" does not apply). Only
    metrics present in both runs are compared. The result is sorted by severity
    (largest drop first).
    """
    regressions = [
        Regression(metric=metric, baseline=base, current=current[metric])
        for metric, base in baseline.items()
        if metric != LATENCY_KEY and metric in current and current[metric] < base - tolerance
    ]
    regressions.sort(key=lambda r: r.delta)
    return regressions
