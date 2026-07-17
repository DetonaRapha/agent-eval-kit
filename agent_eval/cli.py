"""Command-line entry point.

Wires the pieces together: load the dataset, import the SUT dynamically, build
the judge, run the evaluation, write reports, print the scorecard, and exit with
a status code CI can act on (0 = passed, 1 = failed quality/regression).
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from agent_eval.datasets import DatasetError, load_golden, sample_dataset
from agent_eval.judges import JUDGE_METRICS, JUDGE_NAMES, make_judge
from agent_eval.metrics import DETERMINISTIC_METRICS
from agent_eval.runner import evaluate
from agent_eval.scorecard import Scorecard
from agent_eval.store import compare_runs, load_run, save_run
from agent_eval.sut import SUT

# Default pass bar per metric. Deliberately modest: the point of v0 is to show
# the mechanism, and to let a deliberately-mediocre example SUT still pass while
# a broken one fails. Override per metric with --threshold name=value.
_DEFAULT_THRESHOLDS: dict[str, float] = {
    "relevance": 0.25,
    "faithfulness": 0.25,
    "not_hallucinated": 0.25,
    "keyword_recall": 0.40,
}

_ALL_METRIC_NAMES = (*DETERMINISTIC_METRICS, *JUDGE_METRICS)

# Exit codes, named for clarity at the call sites.
_EXIT_PASSED = 0
_EXIT_FAILED = 1
_EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="agent_eval",
        description=(
            "Evaluate an LLM system against a golden dataset and emit a "
            "pass/fail quality scorecard."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "example:\n"
            "  python -m agent_eval \\\n"
            "    --dataset examples/golden.jsonl \\\n"
            "    --sut examples.tiny_rag:answer \\\n"
            "    --judge mock \\\n"
            "    --report out/\n"
        ),
    )
    parser.add_argument("--dataset", required=True, help="path to the golden dataset (JSONL).")
    parser.add_argument(
        "--sut",
        required=True,
        metavar="MODULE:FUNCTION",
        help="system under test as 'module.path:callable', imported dynamically.",
    )
    parser.add_argument(
        "--judge",
        default="mock",
        choices=JUDGE_NAMES,
        help="judge to use (default: mock; 'anthropic'/'openai' need an API key).",
    )
    parser.add_argument(
        "--report",
        metavar="DIR",
        help="directory to write report.md, report.json and report.html into.",
    )
    parser.add_argument(
        "--threshold",
        action="append",
        default=[],
        metavar="METRIC=VALUE",
        help=(
            "override a pass threshold, e.g. --threshold relevance=0.5. "
            "Repeatable. Known metrics: " + ", ".join(_ALL_METRIC_NAMES) + "."
        ),
    )
    parser.add_argument(
        "--no-default-thresholds",
        action="store_true",
        help="start from an empty threshold set (report-only unless --threshold given).",
    )

    # Dataset size controls.
    parser.add_argument(
        "--limit", type=int, metavar="N", help="evaluate only the first N examples."
    )
    parser.add_argument(
        "--sample", type=int, metavar="N", help="evaluate a deterministic random sample of N."
    )
    parser.add_argument(
        "--seed", type=int, default=0, help="seed for --sample (default: 0, reproducible)."
    )

    # Execution controls.
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        metavar="N",
        help="evaluate N items in parallel (default: 1). Speeds up real LLM judges.",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="memoize judge verdicts for identical (question, answer, contexts, reference).",
    )

    # Persistence and regression detection.
    parser.add_argument(
        "--save-run",
        metavar="DIR",
        help="save this run's scorecard as JSON into DIR (filename from --run-name).",
    )
    parser.add_argument(
        "--run-name",
        metavar="NAME",
        help="filename (without extension) for --save-run (default: UTC timestamp).",
    )
    parser.add_argument(
        "--baseline",
        metavar="PATH",
        help="compare against a previously saved run; fail on any regression.",
    )
    parser.add_argument(
        "--regression-tolerance",
        type=float,
        default=0.0,
        metavar="EPS",
        help="allowed drop vs --baseline before it counts as a regression (default: 0).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        dataset = load_golden(args.dataset, limit=args.limit)
        if args.sample:
            dataset = sample_dataset(dataset, args.sample, seed=args.seed)
    except FileNotFoundError:
        print(f"error: dataset not found: {args.dataset}", file=sys.stderr)
        return _EXIT_USAGE
    except (DatasetError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    try:
        sut = _import_sut(args.sut)
    except (ImportError, AttributeError, ValueError) as exc:
        print(f"error: could not load --sut {args.sut!r}: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    try:
        thresholds = _resolve_thresholds(args.threshold, args.no_default_thresholds)
        judge = make_judge(args.judge)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    try:
        scorecard = evaluate(
            sut, dataset, judge, thresholds, concurrency=args.concurrency, cache=args.cache
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    scorecard.print_table()

    if args.report:
        _write_reports(scorecard, args.report)
    if args.save_run:
        _save_run(scorecard, args.save_run, args.run_name)

    _print_failures(scorecard)

    regressed = _check_regression(scorecard, args.baseline, args.regression_tolerance)
    if not scorecard.passed or regressed:
        return _EXIT_FAILED
    return _EXIT_PASSED


def _import_sut(spec: str) -> SUT:
    """Import a SUT callable from a ``'module:function'`` specification."""
    if ":" not in spec:
        raise ValueError("expected format 'module.path:callable'")

    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise ValueError("expected format 'module.path:callable'")

    # Make the current working directory importable so example SUTs resolve
    # without installation (e.g. examples.tiny_rag from the repo root).
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    module = importlib.import_module(module_name)
    candidate = getattr(module, attr)
    if not callable(candidate):
        raise ValueError(f"{spec!r} is not callable")
    # The kit trusts the SUT contract structurally; the caller owns correctness.
    return cast("SUT", candidate)


def _resolve_thresholds(overrides: list[str], no_defaults: bool) -> dict[str, float]:
    """Merge CLI ``--threshold`` overrides onto the defaults."""
    thresholds: dict[str, float] = {} if no_defaults else dict(_DEFAULT_THRESHOLDS)

    for raw in overrides:
        if "=" not in raw:
            raise ValueError(f"invalid --threshold {raw!r}; expected METRIC=VALUE")
        name, _, value = raw.partition("=")
        name = name.strip()
        try:
            thresholds[name] = float(value)
        except ValueError as exc:
            raise ValueError(f"invalid threshold value in {raw!r}: {exc}") from exc

    return thresholds


def _write_reports(scorecard: Scorecard, report_dir: str) -> None:
    """Write ``report.md``, ``report.json`` and ``report.html`` into ``report_dir``."""
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)

    outputs = {
        "report.md": scorecard.to_markdown(),
        "report.json": scorecard.to_json(),
        "report.html": scorecard.to_html(),
    }
    for filename, content in outputs.items():
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        print(f"\nwrote {path}" if filename.endswith(".md") else f"wrote {path}")


def _save_run(scorecard: Scorecard, directory: str, run_name: str | None) -> None:
    """Persist the run's scorecard for later baseline comparison."""
    name = run_name or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    path = save_run(scorecard, directory, name)
    print(f"saved run to {path}")


def _print_failures(scorecard: Scorecard) -> None:
    """Explain, on stderr, which metrics fell short (if any)."""
    failures = scorecard.failures()
    if not failures:
        return
    print("\nfailing metrics:", file=sys.stderr)
    for metric, (actual, threshold) in sorted(failures.items()):
        print(f"  {metric}: {actual:.3f} < {threshold:.3f}", file=sys.stderr)


def _check_regression(scorecard: Scorecard, baseline_path: str | None, tolerance: float) -> bool:
    """Compare against a baseline run; report and return whether it regressed."""
    if not baseline_path:
        return False
    try:
        baseline = load_run(baseline_path)
    except FileNotFoundError:
        print(f"error: baseline not found: {baseline_path}", file=sys.stderr)
        return True
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return True

    regressions = compare_runs(baseline, scorecard.aggregate, tolerance=tolerance)
    if not regressions:
        return False

    print("\nregressions vs baseline:", file=sys.stderr)
    for reg in regressions:
        print(
            f"  {reg.metric}: {reg.current:.3f} < {reg.baseline:.3f} ({reg.delta:+.3f})",
            file=sys.stderr,
        )
    return True
